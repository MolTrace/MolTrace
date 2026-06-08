"""Unit tests for the closed active-learning loop (Prompt 16, ai/active_learning.py).

Covers the five acceptance criteria end to end:

1. override capture with complete provenance, append-only;
2. disagreement scoring across >= 3 model variants (pretrained / fine-tuned / RAG);
3. an annotation queue ranked by disagreement, de-duplicated, respecting a budget;
4. a retraining trigger (schedule OR volume) wired to the Prompt 15 pipeline; and
5. loop-yield metrics (labeled/month, override-rate trend, accuracy lift) emitted to
   the audit trail.

Every heavy path (model variants, the retrain kick-off, the audit recorder) is
injected with a fake, so the whole loop is exercised on a CPU-only host.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import moltrace.spectroscopy.ai.active_learning as al
from moltrace.spectroscopy.ai.active_learning import (
    ActiveLearningError,
    LoopYieldMetrics,
    OverrideSession,
    RetrainEvent,
    VariantPrediction,
    build_annotation_queue,
    capture_override,
    disagreement_score,
    emit_loop_yield,
    evaluate_retraining,
    kickoff_finetune,
    loop_yield_metrics,
    maybe_kickoff_retrain,
    rag_variant,
    retraining_trigger,
    routed_variant,
    score_disagreement,
    set_default_collector,
)
from moltrace.spectroscopy.audit.trail import (
    AuditRecorder,
    InMemoryAuditLog,
    reset_default_recorder,
    static_key,
)
from moltrace.spectroscopy.feedback.capture import (
    FeedbackCollector,
    FeedbackEvent,
    FeedbackVerdict,
    InMemoryFeedbackStore,
    LabeledExample,
    OutputKind,
    ReasonCode,
)
from moltrace.spectroscopy.infra.contract import content_hash

_VERSIONS = {"shift_predictor": "lora_adapter:13C:1.0.0", "verifier": "scorer:2.1.0"}
_SPECTRUM = {"nucleus": "13C", "field_mhz": 100.6, "peaks_ppm": [55.1, 18.4]}


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@dataclass
class _Cand:
    """A candidate spectrum awaiting annotation (duck-typed pool member)."""

    record_hash: str
    spectrum: Any = None
    fingerprint: str | None = None
    group: str | None = None
    created_utc: str | None = None


class _Atom:
    def __init__(self, ppm: float, unc: float) -> None:
        self.predicted_ppm = ppm
        self.uncertainty_ppm = unc


class _Routed:
    def __init__(self, predictions: list[_Atom]) -> None:
        self.predictions = predictions


class _FakeRouter:
    """Stands in for an InferenceRouter: returns fixed per-atom predictions."""

    def __init__(self, predictions: list[_Atom]) -> None:
        self._predictions = predictions

    def predict_shifts_routed(self, smiles: str, nuclei: Any, device: Any = None) -> _Routed:
        return _Routed(self._predictions)


class _RagCand:
    def __init__(self, smiles: str, posterior: float) -> None:
        self.smiles = smiles
        self.posterior_confidence = posterior


class _RagProposal:
    def __init__(self, accepted: list[_RagCand]) -> None:
        self.accepted = accepted


def _event(
    *,
    verdict: FeedbackVerdict,
    created_utc: str,
    correction: bool = False,
    record_hash: str | None = None,
    kind: OutputKind = OutputKind.PREDICTED_SHIFT,
) -> FeedbackEvent:
    """A feedback event; a ``correction`` carries ground truth so it labels."""

    return FeedbackEvent(
        output_kind=kind,
        output_ref=f"out:{created_utc}:{verdict}",
        verdict=verdict,
        model_versions=_VERSIONS,
        record_hash=record_hash or (f"rec:{created_utc}" if correction else None),
        corrected_value={"ppm": 55.0} if correction else None,
        created_utc=created_utc,
    )


# --------------------------------------------------------------------------- #
# Criterion 1: override capture with complete provenance (append-only)
# --------------------------------------------------------------------------- #
def test_capture_override_persists_labeled_example_with_full_provenance():
    collector = FeedbackCollector(InMemoryFeedbackStore())
    session = OverrideSession(
        record_hash="sha256:spec-1",
        output_kind=OutputKind.PREDICTED_SHIFT,
        model_versions=_VERSIONS,
        ai_output={"ppm": 60.2},  # the original (wrong) value
        corrected_value={"ppm": 55.1},  # the reviewer's ground truth
        reviewer_id="reviewer-7",
        raw_fid_hash="sha256:rawfid-abc",
        processed_spectrum=_SPECTRUM,
        reason=ReasonCode.WRONG_SHIFT,
        correction_text="should be the methine carbon",
        tenant_id="tenant-x",
        created_utc="2026-06-01T00:00:00+00:00",
    )

    example = capture_override(session, collector=collector)

    # The returned label carries the correction + the provenance of the original.
    assert isinstance(example, LabeledExample)
    assert example.record_hash == "sha256:spec-1"
    assert example.corrected_value == {"ppm": 55.1}
    assert example.reason is ReasonCode.WRONG_SHIFT
    assert dict(example.model_versions) == _VERSIONS

    # The stored event keeps the FULL learning context.
    events = collector.events()
    assert len(events) == 1
    stored = events[0]
    assert stored.verdict is FeedbackVerdict.DOWN
    assert stored.reviewer_id == "reviewer-7"
    assert stored.tenant_id == "tenant-x"
    assert stored.created_utc == "2026-06-01T00:00:00+00:00"
    assert stored.context["ai_output"] == {"ppm": 60.2}
    assert stored.context["raw_fid_hash"] == "sha256:rawfid-abc"
    assert stored.context["processed_spectrum"] == _SPECTRUM
    assert stored.context["processed_spectrum_hash"] == content_hash(_SPECTRUM)


def test_capture_override_is_append_only_idempotent():
    collector = FeedbackCollector(InMemoryFeedbackStore())
    session = OverrideSession(
        record_hash="sha256:spec-2",
        output_kind="proposed_structure",
        model_versions=_VERSIONS,
        ai_output="CCO",
        corrected_value="CCOC",
        reviewer_id="reviewer-1",
        created_utc="2026-06-02T00:00:00+00:00",
    )
    # Re-submitting the byte-identical override is a no-op in the append-only store.
    first = capture_override(session, collector=collector)
    second = capture_override(session, collector=collector)
    assert first.source_event_id == second.source_event_id
    assert len(collector.events()) == 1
    assert len(collector.labeled_examples()) == 1


def test_capture_override_requires_ground_truth_and_record_hash():
    collector = FeedbackCollector(InMemoryFeedbackStore())
    no_gt = OverrideSession(
        record_hash="sha256:spec-3",
        output_kind=OutputKind.PURITY_CALL,
        model_versions=_VERSIONS,
        ai_output={"purity": 0.97},
        corrected_value=None,  # a bare override is queued, not labeled
        reviewer_id="reviewer-1",
    )
    with pytest.raises(ActiveLearningError):
        capture_override(no_gt, collector=collector)

    no_hash = OverrideSession(
        record_hash="",
        output_kind=OutputKind.PURITY_CALL,
        model_versions=_VERSIONS,
        ai_output={"purity": 0.97},
        corrected_value={"purity": 0.991},
        reviewer_id="reviewer-1",
    )
    with pytest.raises(ActiveLearningError):
        capture_override(no_hash, collector=collector)


def test_capture_override_uses_default_collector():
    collector = FeedbackCollector(InMemoryFeedbackStore())
    set_default_collector(collector)
    try:
        session = OverrideSession(
            record_hash="sha256:spec-4",
            output_kind=OutputKind.PEAK_LABEL,
            model_versions=_VERSIONS,
            ai_output="aromatic CH",
            corrected_value="olefinic CH",
            reviewer_id="reviewer-2",
            created_utc="2026-06-03T00:00:00+00:00",
        )
        example = capture_override(session)  # no explicit collector
        assert example.record_hash == "sha256:spec-4"
        assert len(collector.events()) == 1
    finally:
        set_default_collector(None)


# --------------------------------------------------------------------------- #
# Criterion 2: disagreement scoring across >= 3 model variants
# --------------------------------------------------------------------------- #
def _variant(name, structure, shifts, confidence):
    return lambda spectrum: VariantPrediction(
        variant=name, top1_structure=structure, predicted_shifts=shifts, confidence=confidence
    )


def test_disagreement_score_three_variants_in_unit_interval():
    variants = [
        _variant("nmrnet_pretrained", "CCO", (1.2, 3.6), 0.8),
        _variant("lora_finetuned", "CCO", (1.25, 3.7), 0.7),
        _variant("rag_reasoner", "CCOC", (), 0.4),
    ]
    score = disagreement_score("spectrum", variants=variants)
    assert 0.0 < score < 1.0


def test_disagreement_high_vs_low():
    high = [
        _variant("a", "A", (10.0,), 0.9),
        _variant("b", "B", (40.0,), 0.5),
        _variant("c", "C", (70.0,), 0.1),
    ]
    low = [
        _variant("a", "X", (10.0,), 0.8),
        _variant("b", "X", (10.1,), 0.79),
        _variant("c", "X", (10.0,), 0.81),
    ]
    assert disagreement_score("s", variants=high) > disagreement_score("s", variants=low)


def test_disagreement_unanimous_is_zero():
    same = [
        _variant("a", "CCO", (1.0, 2.0), 0.5),
        _variant("b", "CCO", (1.0, 2.0), 0.5),
        _variant("c", "CCO", (1.0, 2.0), 0.5),
    ]
    assert disagreement_score("s", variants=same) == 0.0


def test_score_disagreement_components():
    preds = [
        VariantPrediction("a", top1_structure="CCO", predicted_shifts=(1.0, 2.0), confidence=0.9),
        VariantPrediction("b", top1_structure="CCO", predicted_shifts=(1.0, 2.0), confidence=0.7),
        VariantPrediction("c", top1_structure="CCOC", predicted_shifts=(), confidence=0.3),
    ]
    report = score_disagreement(preds)
    # 2x CCO vs 1x CCOC -> plurality 2/3 -> normalised vote split 0.5.
    assert report.structure_disagreement == pytest.approx(0.5)
    # identical shift vectors among the two that predicted -> no shift spread.
    assert report.shift_disagreement == pytest.approx(0.0)
    # confidence range 0.9 - 0.3.
    assert report.confidence_spread == pytest.approx(0.6)
    assert report.n_variants == 3
    assert report.top1_structures == ("CCO", "CCO", "CCOC")
    assert 0.0 < report.score < 1.0


def test_disagreement_requires_two_variants():
    with pytest.raises(ActiveLearningError):
        disagreement_score("s", variants=[_variant("only", "CCO", (1.0,), 0.5)])


def test_disagreement_weights_renormalize_to_available_components():
    # No structures, no shifts -> only the confidence component is defined, and the
    # score must equal the confidence spread (weights renormalise onto it).
    preds = [
        VariantPrediction("a", top1_structure=None, predicted_shifts=(), confidence=0.2),
        VariantPrediction("b", top1_structure=None, predicted_shifts=(), confidence=0.9),
    ]
    report = score_disagreement(preds)
    assert report.structure_disagreement is None
    assert report.shift_disagreement is None
    assert report.confidence_spread == pytest.approx(0.7)
    assert report.score == pytest.approx(0.7)


def test_routed_and_rag_variant_adapters_compose():
    pretrained = routed_variant(
        _FakeRouter([_Atom(20.0, 0.10), _Atom(40.0, 0.20)]),
        "CCO",
        name="nmrnet_pretrained",
    )
    finetuned = routed_variant(
        _FakeRouter([_Atom(20.4, 0.05), _Atom(41.1, 0.06)]),
        "CCO",
        name="lora_finetuned",
    )
    rag = rag_variant(
        context=object(),
        propose_fn=lambda spectrum, context, **kw: _RagProposal([_RagCand("CCOC", 0.55)]),
    )

    p_pred = pretrained("spectrum")
    assert p_pred.variant == "nmrnet_pretrained"
    assert p_pred.top1_structure == "CCO"
    assert p_pred.predicted_shifts == (20.0, 40.0)
    assert 0.0 < p_pred.confidence < 1.0  # exp(-mean uncertainty)

    r_pred = rag("spectrum")
    assert r_pred.top1_structure == "CCOC"
    assert r_pred.confidence == pytest.approx(0.55)

    # Three real-shaped variants -> a single disagreement number.
    score = disagreement_score("spectrum", variants=[pretrained, finetuned, rag])
    assert 0.0 < score <= 1.0


def test_rag_variant_handles_no_accepted_candidate():
    rag = rag_variant(
        context=object(),
        propose_fn=lambda spectrum, context, **kw: _RagProposal([]),
    )
    pred = rag("spectrum")
    assert pred.top1_structure is None
    assert pred.confidence == 0.0


# --------------------------------------------------------------------------- #
# Criterion 3: annotation queue ranked + de-duplicated, respects budget
# --------------------------------------------------------------------------- #
def test_build_annotation_queue_ranks_by_severity_and_respects_budget():
    pool = [
        _Cand("h1", fingerprint="A"),
        _Cand("h2", fingerprint="B"),
        _Cand("h3", fingerprint="C"),
        _Cand("h4", fingerprint="D"),
    ]
    severity = {"h1": 0.9, "h2": 0.2, "h3": 0.7, "h4": 0.5}
    queue = build_annotation_queue(pool, budget=3, score_fn=lambda c: severity[c.record_hash])

    assert len(queue) == 3  # budget respected
    assert [pi.item.record_hash for pi in queue] == ["h1", "h3", "h4"]  # highest first
    assert [pi.rank for pi in queue] == [0, 1, 2]
    assert queue[0].severity == pytest.approx(0.9)


def test_build_annotation_queue_dedups_by_fingerprint():
    pool = [
        _Cand("h1", fingerprint="dup"),
        _Cand("h2", fingerprint="dup"),  # near-identical to h1, lower severity
        _Cand("h3", fingerprint="unique"),
    ]
    severity = {"h1": 0.9, "h2": 0.5, "h3": 0.7}
    queue = build_annotation_queue(pool, budget=10, score_fn=lambda c: severity[c.record_hash])

    kept = {pi.item.record_hash for pi in queue}
    assert kept == {"h1", "h3"}  # the lower-severity duplicate h2 is dropped
    assert [pi.item.record_hash for pi in queue] == ["h1", "h3"]


def test_build_annotation_queue_dedups_via_similarity_fn():
    pool = [
        _Cand("h1", group="g1"),
        _Cand("h2", group="g1"),  # same cluster as h1
        _Cand("h3", group="g2"),
    ]
    severity = {"h1": 0.9, "h2": 0.6, "h3": 0.7}
    queue = build_annotation_queue(
        pool,
        budget=10,
        score_fn=lambda c: severity[c.record_hash],
        similarity_fn=lambda a, b: 1.0 if a.group == b.group else 0.0,
        dedup_threshold=1.0,
    )
    assert {pi.item.record_hash for pi in queue} == {"h1", "h3"}


def test_build_annotation_queue_scores_with_variants():
    pool = [
        _Cand("hi", spectrum={"structs": ("A", "B", "C"), "confs": (0.9, 0.5, 0.1)}),
        _Cand("lo", spectrum={"structs": ("A", "A", "A"), "confs": (0.8, 0.8, 0.8)}),
    ]
    variants = [
        (lambda s, i=i: VariantPrediction(f"v{i}", top1_structure=s["structs"][i], confidence=s["confs"][i]))
        for i in range(3)
    ]
    queue = build_annotation_queue(pool, budget=2, variants=variants)
    assert [pi.item.record_hash for pi in queue] == ["hi", "lo"]
    assert queue[0].severity > queue[1].severity
    assert queue[1].severity == pytest.approx(0.0)


def test_build_annotation_queue_budget_and_scorer_guards():
    pool = [_Cand("h1", fingerprint="A")]
    assert build_annotation_queue(pool, budget=0, score_fn=lambda c: 0.5) == []
    with pytest.raises(ActiveLearningError):
        build_annotation_queue(pool, budget=-1, score_fn=lambda c: 0.5)
    with pytest.raises(ActiveLearningError):
        build_annotation_queue(pool, budget=3)  # neither variants nor score_fn


def test_build_annotation_queue_reward_blend_populates_acceptance():
    pool = [_Cand("h1", fingerprint="A"), _Cand("h2", fingerprint="B")]
    severity = {"h1": 0.8, "h2": 0.6}
    queue = build_annotation_queue(
        pool,
        budget=2,
        score_fn=lambda c: severity[c.record_hash],
        reward_fn=lambda item: 0.0,
        reward_weight=0.5,
    )
    assert len(queue) == 2
    assert all(pi.predicted_acceptance is not None for pi in queue)


# --------------------------------------------------------------------------- #
# Criterion 4: retraining trigger (schedule + volume) wired to Prompt 15
# --------------------------------------------------------------------------- #
def test_retraining_trigger_volume():
    decision = evaluate_retraining(
        new_labeled_examples=60,
        last_finetune_utc="2026-05-25T00:00:00+00:00",
        now_utc="2026-06-01T00:00:00+00:00",
        min_new_labels=50,
        schedule_days=30,
    )
    assert decision.should_retrain is True
    assert decision.reason == "volume"


def test_retraining_trigger_bootstrap_when_never_trained():
    decision = evaluate_retraining(
        new_labeled_examples=80,
        last_finetune_utc=None,
        min_new_labels=50,
    )
    assert decision.should_retrain is True
    assert decision.reason == "bootstrap"
    assert decision.days_since_last is None


def test_retraining_trigger_schedule():
    decision = evaluate_retraining(
        new_labeled_examples=5,
        last_finetune_utc="2026-04-20T00:00:00+00:00",
        now_utc="2026-06-01T00:00:00+00:00",  # ~42 days later
        min_new_labels=50,
        schedule_days=30,
    )
    assert decision.should_retrain is True
    assert decision.reason == "schedule"
    assert decision.days_since_last == pytest.approx(42.0, abs=1.0)


def test_retraining_trigger_not_yet():
    assert (
        retraining_trigger(
            new_labeled_examples=5,
            last_finetune_utc="2026-05-28T00:00:00+00:00",
            now_utc="2026-06-01T00:00:00+00:00",
            min_new_labels=50,
            schedule_days=30,
        )
        is False
    )


def test_retraining_trigger_volume_and_schedule():
    decision = evaluate_retraining(
        new_labeled_examples=100,
        last_finetune_utc="2026-04-01T00:00:00+00:00",
        now_utc="2026-06-01T00:00:00+00:00",
        min_new_labels=50,
        schedule_days=30,
    )
    assert decision.reason == "volume+schedule"


def test_maybe_kickoff_retrain_runs_only_when_fired():
    fired = evaluate_retraining(new_labeled_examples=100, last_finetune_utc=None)
    not_fired = evaluate_retraining(new_labeled_examples=1, last_finetune_utc=None)

    calls: list[str] = []

    def kickoff():
        calls.append("ran")
        return "model_id:1"

    assert maybe_kickoff_retrain(fired, kickoff=kickoff) == "model_id:1"
    assert maybe_kickoff_retrain(not_fired, kickoff=kickoff) is None
    assert calls == ["ran"]  # invoked exactly once (only when fired)


def test_kickoff_finetune_wires_prompt15_chain(monkeypatch):
    calls: list[tuple] = []
    snapshot_sentinel = object()
    run_sentinel = object()

    def fake_build(examples, *, splits, gold_checksum, git_sha, created_utc):
        calls.append(("snapshot", gold_checksum, list(examples)))
        return snapshot_sentinel

    def fake_finetune(snapshot, base_model_id, **kwargs):
        calls.append(("finetune", snapshot is snapshot_sentinel, base_model_id))
        return run_sentinel

    def fake_register(run, *, registry, gold_set, candidate_bundle, **kwargs):
        calls.append(("register", run is run_sentinel))
        return "lora_adapter:13C:2.0.0"

    monkeypatch.setattr(al, "build_training_snapshot", fake_build)
    monkeypatch.setattr(al, "finetune_lora", fake_finetune)
    monkeypatch.setattr(al, "register_if_eligible", fake_register)

    class _Gold:
        def checksum(self) -> str:
            return "sha256:gold-xyz"

    model_id = kickoff_finetune(
        ["ex1", "ex2"],
        base_model_id="nmrnet:1.0.0",
        registry=object(),
        gold_set=_Gold(),
        candidate_bundle=object(),
    )

    assert model_id == "lora_adapter:13C:2.0.0"
    assert [c[0] for c in calls] == ["snapshot", "finetune", "register"]
    assert calls[0][1] == "sha256:gold-xyz"  # gold checksum threaded into the snapshot
    assert calls[0][2] == ["ex1", "ex2"]
    assert calls[1][1] is True  # finetune received the snapshot
    assert calls[2][1] is True  # register received the run


# --------------------------------------------------------------------------- #
# Criterion 5: loop-yield metrics emitted
# --------------------------------------------------------------------------- #
_NOW = "2026-06-01T00:00:00+00:00"
_RECENT = "2026-05-20T00:00:00+00:00"  # inside the trailing 30-day window
_PRIOR = "2026-04-20T00:00:00+00:00"  # inside the prior 30-day window


def _loop_events() -> list[FeedbackEvent]:
    events: list[FeedbackEvent] = []
    # Recent window: mostly accepted (override rate 2/5 = 0.4); 2 corrections.
    events += [_event(verdict=FeedbackVerdict.UP, created_utc=_RECENT) for _ in range(3)]
    events += [
        _event(verdict=FeedbackVerdict.DOWN, created_utc=_RECENT, correction=True, record_hash=f"r{i}")
        for i in range(2)
    ]
    # Prior window: mostly overridden (override rate 3/4 = 0.75); bare downs.
    events += [_event(verdict=FeedbackVerdict.UP, created_utc=_PRIOR)]
    events += [_event(verdict=FeedbackVerdict.DOWN, created_utc=_PRIOR) for _ in range(3)]
    return events


def test_loop_yield_metrics_rates_and_trend():
    metrics = loop_yield_metrics(_loop_events(), now_utc=_NOW, window_days=30)

    assert isinstance(metrics, LoopYieldMetrics)
    assert metrics.n_events == 9
    assert metrics.labeled_examples_total == 2  # only the 2 recent corrections label
    assert metrics.labeled_examples_per_month == pytest.approx(2.0)
    assert metrics.override_rate_recent == pytest.approx(0.4)
    assert metrics.override_rate_prior == pytest.approx(0.75)
    # Negative trend == reviewers overriding less == the model is improving.
    assert metrics.override_rate_trend == pytest.approx(-0.35)
    assert metrics.override_rate == pytest.approx(5 / 9)


def test_loop_yield_accuracy_lift_lower_is_better():
    retrains = [
        RetrainEvent("v1", "2026-01-01T00:00:00+00:00", primary_metric=0.30),
        RetrainEvent("v2", "2026-02-01T00:00:00+00:00", primary_metric=0.25),
        RetrainEvent("v3", "2026-03-01T00:00:00+00:00", primary_metric=0.20),
    ]
    metrics = loop_yield_metrics([], retrains=retrains, now_utc=_NOW)
    assert metrics.n_retrains == 3
    assert metrics.accuracy_lift_last_retrain == pytest.approx(0.05)  # 0.25 -> 0.20
    assert metrics.accuracy_lift_total == pytest.approx(0.10)  # 0.30 -> 0.20


def test_loop_yield_accuracy_lift_higher_is_better():
    retrains = [
        RetrainEvent("v1", "2026-01-01T00:00:00+00:00", primary_metric=0.80, higher_is_better=True),
        RetrainEvent("v2", "2026-02-01T00:00:00+00:00", primary_metric=0.88, higher_is_better=True),
    ]
    metrics = loop_yield_metrics([], retrains=retrains, now_utc=_NOW)
    assert metrics.accuracy_lift_last_retrain == pytest.approx(0.08)


def test_loop_yield_tolerates_unparseable_timestamps():
    # Opaque markers count toward totals but are excluded from windowed rates.
    events = [
        _event(verdict=FeedbackVerdict.DOWN, created_utc="t-0", correction=True, record_hash="x"),
        _event(verdict=FeedbackVerdict.UP, created_utc="t-1"),
    ]
    metrics = loop_yield_metrics(events, now_utc=_NOW)
    assert metrics.labeled_examples_total == 1
    assert metrics.override_rate_recent is None
    assert metrics.override_rate_trend is None


def test_emit_loop_yield_writes_audit_entry():
    recorder = AuditRecorder(log=InMemoryAuditLog(), key_provider=static_key(b"k" * 32))
    metrics = loop_yield_metrics(_loop_events(), now_utc=_NOW)

    entry = emit_loop_yield(metrics, recorder=recorder, user_id="reviewer-1")
    assert entry is not None
    assert entry.operation == "ai.active_learning.loop_yield"
    assert len(recorder.log) == 1


def test_emit_loop_yield_is_noop_without_recorder():
    reset_default_recorder()
    metrics = loop_yield_metrics([], now_utc=_NOW)
    assert emit_loop_yield(metrics) is None
