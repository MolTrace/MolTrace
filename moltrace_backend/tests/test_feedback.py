"""Unit tests for the closed-loop feedback package (Prompt 23, feedback/).

Covers the four acceptance criteria end to end:

1. an in-app feedback control on *every* AI output kind (thumbs + free text +
   reason taxonomy), events stored with their Prompt 13 ``model_versions`` and
   fanning out to the Prompt 16 labeled-example store / active-learning queue;
2. usage + override analytics;
3. an RLHF preference dataset + a deterministic Bradley-Terry reward model whose
   ranking is *advisory* -- the Prompt 7 verifier still arbitrates; and
4. champion-vs-challenger A/B routing (shadow + canary), dominance-gated promotion
   with reviewer guards, no auto-deploy (human sign-off), and instant rollback.

The capture store round-trips through BOTH backends (in-memory + SQLite, the exact
code path that drives PostgreSQL) so persistence is proven backend-independent on a
CPU-only host.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from moltrace.spectroscopy.ai.finetune import ActiveLearningItem, InMemoryActiveLearningQueue
from moltrace.spectroscopy.ai.registry import (
    InMemoryRegistryStore,
    ModelRegistry,
    ModelRole,
    ModelStatus,
    TrainingDataLineage,
    build_model_entry,
)
from moltrace.spectroscopy.eval.harness import GoldMetricVector
from moltrace.spectroscopy.feedback import (
    ABTest,
    ABTestError,
    Arm,
    FeedbackCollector,
    FeedbackVerdict,
    InMemoryFeedbackStore,
    OutputKind,
    Preference,
    PromotionBlocked,
    ReasonCode,
    RewardModel,
    RewardModelError,
    RoutingMode,
    SqlAlchemyFeedbackStore,
    build_preference_dataset,
    default_candidate_features,
    evaluate_promotion,
    prioritize_annotation_queue,
    rank_candidates,
    reward_scorer,
    train_reward_model,
    usage_analytics,
)

_VERSIONS = {"shift_predictor": "lora_adapter:13C:1.0.0", "verifier": "scorer:2.1.0"}


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture(params=["memory", "sqlalchemy"])
def store(request, tmp_path):
    if request.param == "memory":
        return InMemoryFeedbackStore()
    return SqlAlchemyFeedbackStore(f"sqlite:///{tmp_path}/feedback.db")


def _shift_features(value, context):
    """Featurize a numeric output as its absolute error vs a reference in context."""

    ref = float(context.get("reference", 0.0))
    return {"abs_error": abs(float(value) - ref), "value": float(value)}


@dataclass
class _Cand:
    """A stand-in for a Prompt 14 rag.Candidate (same advisory attributes)."""

    smiles: str
    accepted: bool
    self_confidence: float = 0.5
    retrieval_supported: bool = False
    posterior_confidence: float | None = None
    cited_analogue_ids: tuple[str, ...] = ()


def _feedback_for(model_id, *, up, down, kind=OutputKind.PROPOSED_STRUCTURE):
    """A batch of accept/reject events attributable to ``model_id`` via model_versions."""

    coll = FeedbackCollector()
    out = []
    for i in range(up):
        out.append(
            coll.capture(
                output_kind=kind,
                output_ref=f"{model_id}:up:{i}",
                verdict=FeedbackVerdict.UP,
                model_versions={"adapter": model_id},
                created_utc=f"t-up-{i}",
            )
        )
    for i in range(down):
        out.append(
            coll.capture(
                output_kind=kind,
                output_ref=f"{model_id}:down:{i}",
                verdict=FeedbackVerdict.DOWN,
                model_versions={"adapter": model_id},
                created_utc=f"t-down-{i}",
            )
        )
    return out


_LINEAGE = TrainingDataLineage(
    dataset_snapshot_hash="sha256:dataset-abc",
    row_count=1000,
    dataset_tag="in-house-2026Q2",
    source="in_house",
)


def _registry_with_champion():
    """A registry with a production champion + a candidate challenger (same role/nucleus)."""

    reg = ModelRegistry(InMemoryRegistryStore())
    champ = build_model_entry(
        role=ModelRole.LORA_ADAPTER,
        nucleus="13C",
        semantic_version="1.0.0",
        artifact_sha256="sha256:champ",
        training_data_lineage=_LINEAGE,
        status=ModelStatus.CANDIDATE,
        created_utc=datetime(2026, 6, 7, 12, 0, tzinfo=UTC),
    )
    chal = build_model_entry(
        role=ModelRole.LORA_ADAPTER,
        nucleus="13C",
        semantic_version="1.1.0",
        artifact_sha256="sha256:chal",
        training_data_lineage=_LINEAGE,
        status=ModelStatus.CANDIDATE,
        created_utc=datetime(2026, 6, 7, 12, 5, tzinfo=UTC),
    )
    reg.register(champ)
    reg.register(chal)
    reg.promote(champ.model_id, reason="initial production")
    return reg, champ.model_id, chal.model_id


def _mv(**over) -> GoldMetricVector:
    base = dict(
        top1_accuracy=0.80,
        top3_accuracy=0.90,
        shift_mae_1h=0.10,
        shift_mae_13c=1.00,
        ece=0.05,
        false_confirmation_rate=0.02,
        recall_at_k=0.90,
        uncertainty_auroc=0.70,
        robustness=0.80,
        reviewer_agreement_rate=0.85,
        latency_p50_ms=100.0,
        latency_p95_ms=200.0,
        model_versions={"m": "sha"},
        gold_checksum="sha256:gc",
        gold_name="g",
        n_records=100,
        k=5,
    )
    base.update(over)
    return GoldMetricVector(**base)


# --------------------------------------------------------------------------- #
# Criterion 1: capture on every output kind, with provenance + Prompt 16 fan-out
# --------------------------------------------------------------------------- #
def test_capture_control_on_every_ai_output_kind(store) -> None:
    coll = FeedbackCollector(store)
    for i, kind in enumerate(OutputKind):
        coll.capture(
            output_kind=kind,
            output_ref=f"out:{kind.value}",
            verdict=FeedbackVerdict.UP if i % 2 == 0 else FeedbackVerdict.DOWN,
            model_versions=_VERSIONS,
            created_utc=f"t-{i}",
        )
    stored = coll.events()
    assert len(stored) == len(list(OutputKind))
    # every event keeps the exact model_versions that produced the rated output
    assert all(dict(e.model_versions) == _VERSIONS for e in stored)
    # the event is content-addressed
    assert all(e.event_id().startswith("sha256:") for e in stored)


def test_thumbs_freetext_and_reason_taxonomy_are_captured(store) -> None:
    coll = FeedbackCollector(store)
    event = coll.capture(
        output_kind=OutputKind.PREDICTED_SHIFT,
        output_ref="shift:atom-7",
        verdict=FeedbackVerdict.DOWN,
        model_versions=_VERSIONS,
        record_hash="sha256:rec-1",
        reason=ReasonCode.WRONG_SHIFT,
        correction_text="should be ~7.26 ppm (residual CHCl3)",
        corrected_value=7.26,
        context={"nucleus": "1H", "output_value": 5.10, "reference": 7.26},
    )
    assert event.verdict is FeedbackVerdict.DOWN
    assert event.reason is ReasonCode.WRONG_SHIFT
    assert event.correction_text.startswith("should be")
    assert event.is_override and event.is_correction and event.has_ground_truth
    # round-trips losslessly through the store (incl. the SQLite path)
    got = store.get_event(event.event_id())
    assert got is not None
    assert got.corrected_value == 7.26
    assert got.reason is ReasonCode.WRONG_SHIFT
    assert got.event_id() == event.event_id()


def test_correction_feeds_prompt16_labeled_example_store(store) -> None:
    coll = FeedbackCollector(store)
    coll.capture(
        output_kind=OutputKind.PREDICTED_SHIFT,
        output_ref="shift:1",
        verdict=FeedbackVerdict.DOWN,
        model_versions=_VERSIONS,
        record_hash="sha256:rec-1",
        reason=ReasonCode.WRONG_SHIFT,
        corrected_value=7.26,
        context={"output_value": 5.1},
    )
    examples = coll.labeled_examples()
    assert len(examples) == 1
    ex = examples[0]
    assert ex.record_hash == "sha256:rec-1"
    assert ex.corrected_value == 7.26
    # the labeled example carries the versions of the model that produced the error
    assert dict(ex.model_versions) == _VERSIONS


def test_bare_override_routes_to_active_learning_queue() -> None:
    queue = InMemoryActiveLearningQueue()
    coll = FeedbackCollector(InMemoryFeedbackStore(), queue=queue)
    # bare override: thumbs-down, a record_hash, but NO structured ground truth
    coll.capture(
        output_kind=OutputKind.PROPOSED_STRUCTURE,
        output_ref="struct:1",
        verdict=FeedbackVerdict.DOWN,
        model_versions=_VERSIONS,
        record_hash="sha256:rec-9",
        reason=ReasonCode.WRONG_STRUCTURE,
    )
    # a correction (with ground truth) should NOT be re-queued -- it becomes a label
    coll.capture(
        output_kind=OutputKind.PREDICTED_SHIFT,
        output_ref="shift:1",
        verdict=FeedbackVerdict.DOWN,
        model_versions=_VERSIONS,
        record_hash="sha256:rec-10",
        corrected_value=7.26,
        context={"output_value": 5.1},
    )
    assert [it.record_hash for it in queue.items] == ["sha256:rec-9"]
    assert queue.items[0].reason == "wrong_structure"
    assert coll.labeled_examples()[0].record_hash == "sha256:rec-10"


def test_store_is_append_only_and_idempotent(store) -> None:
    coll = FeedbackCollector(store)
    kwargs = dict(
        output_kind=OutputKind.PURITY_CALL,
        output_ref="purity:1",
        verdict=FeedbackVerdict.UP,
        model_versions=_VERSIONS,
        created_utc="2026-06-07T00:00:00+00:00",
    )
    a = coll.capture(**kwargs)
    b = coll.capture(**kwargs)  # byte-identical re-submission
    assert a.event_id() == b.event_id()
    assert len(coll.events()) == 1


# --------------------------------------------------------------------------- #
# Criterion 2: usage + override analytics
# --------------------------------------------------------------------------- #
def test_usage_and_override_analytics() -> None:
    coll = FeedbackCollector()
    # 3 structure ratings: 1 up, 2 down (one a correction)
    coll.capture(
        output_kind=OutputKind.PROPOSED_STRUCTURE, output_ref="s1",
        verdict=FeedbackVerdict.UP, model_versions=_VERSIONS, created_utc="t1",
    )
    coll.capture(
        output_kind=OutputKind.PROPOSED_STRUCTURE, output_ref="s2",
        verdict=FeedbackVerdict.DOWN, model_versions=_VERSIONS,
        reason=ReasonCode.WRONG_STRUCTURE, created_utc="t2",
    )
    coll.capture(
        output_kind=OutputKind.PROPOSED_STRUCTURE, output_ref="s3",
        verdict=FeedbackVerdict.DOWN, model_versions=_VERSIONS, record_hash="sha256:r3",
        reason=ReasonCode.MISSED_IMPURITY, corrected_value="CCO",
        context={"output_value": "CCN"}, created_utc="t3",
    )
    # 1 shift rating, up
    coll.capture(
        output_kind=OutputKind.PREDICTED_SHIFT, output_ref="sh1",
        verdict=FeedbackVerdict.UP, model_versions=_VERSIONS, created_utc="t4",
    )

    stats = coll.analytics()
    assert stats.n_events == 4
    assert stats.thumbs_up == 2
    assert stats.thumbs_down == 2
    assert stats.override_rate == pytest.approx(0.5)
    assert stats.n_corrections == 1  # only the one with a corrected_value + record_hash
    assert stats.by_output_kind == {"predicted_shift": 1, "proposed_structure": 3}
    # structure is overridden 2/3 of the time; shift never
    assert stats.override_rate_by_kind["proposed_structure"] == pytest.approx(2 / 3)
    assert stats.override_rate_by_kind["predicted_shift"] == pytest.approx(0.0)
    assert stats.reason_histogram == {"missed_impurity": 1, "wrong_structure": 1}

    # per-kind filter narrows the rollup
    only_shift = usage_analytics(coll.events(), output_kind=OutputKind.PREDICTED_SHIFT)
    assert only_shift.n_events == 1 and only_shift.override_rate == 0.0


# --------------------------------------------------------------------------- #
# Criterion 3: preference dataset + reward model (advisory; verifier arbitrates)
# --------------------------------------------------------------------------- #
def _correction_event(coll, rec, original, corrected, ref):
    return coll.capture(
        output_kind=OutputKind.PREDICTED_SHIFT,
        output_ref=f"shift:{rec}",
        verdict=FeedbackVerdict.DOWN,
        model_versions=_VERSIONS,
        record_hash=rec,
        reason=ReasonCode.WRONG_SHIFT,
        corrected_value=corrected,
        context={"output_value": original, "reference": ref},
        created_utc=f"t-{rec}",
    )


def test_build_preference_dataset_from_corrections_and_accept_reject() -> None:
    coll = FeedbackCollector()
    # corrections: corrected value is always closer to the reference than the original
    _correction_event(coll, "r1", original=5.0, corrected=7.2, ref=7.26)
    _correction_event(coll, "r2", original=3.0, corrected=2.1, ref=2.05)
    _correction_event(coll, "r3", original=9.0, corrected=4.0, ref=4.10)
    # an accept/reject pair on the SAME record (a good output up, a bad output down)
    coll.capture(
        output_kind=OutputKind.PREDICTED_SHIFT, output_ref="r4:good",
        verdict=FeedbackVerdict.UP, model_versions=_VERSIONS, record_hash="r4",
        context={"output_value": 4.05, "reference": 4.10}, created_utc="t-r4a",
    )
    coll.capture(
        output_kind=OutputKind.PREDICTED_SHIFT, output_ref="r4:bad",
        verdict=FeedbackVerdict.DOWN, model_versions=_VERSIONS, record_hash="r4",
        context={"output_value": 8.00, "reference": 4.10}, created_utc="t-r4b",
    )

    prefs = build_preference_dataset(coll.events(), feature_fn=_shift_features)
    sources = sorted(p.source for p in prefs)
    assert sources == ["accept_reject", "correction", "correction", "correction"]
    # in every pair the chosen output has the smaller absolute error
    assert all(
        p.chosen_features["abs_error"] < p.rejected_features["abs_error"] for p in prefs
    )


def test_reward_model_training_is_deterministic_and_separable() -> None:
    coll = FeedbackCollector()
    _correction_event(coll, "r1", original=5.0, corrected=7.2, ref=7.26)
    _correction_event(coll, "r2", original=3.0, corrected=2.1, ref=2.05)
    _correction_event(coll, "r3", original=9.0, corrected=4.0, ref=4.10)
    _correction_event(coll, "r4", original=0.5, corrected=1.9, ref=2.00)
    prefs = build_preference_dataset(coll.events(), feature_fn=_shift_features)

    run_a = train_reward_model(prefs, git_sha="deadbeef")
    run_b = train_reward_model(prefs, git_sha="deadbeef")
    # deterministic full-batch GD: identical weights across runs
    assert run_a.model.weights == run_b.model.weights
    # the signal is perfectly separable -> all pairs ordered correctly
    assert run_a.pairwise_accuracy == pytest.approx(1.0)
    # lower error scores strictly higher than higher error
    low = run_a.model.score({"abs_error": 0.0, "value": 2.0})
    high = run_a.model.score({"abs_error": 5.0, "value": 2.0})
    assert low > high
    assert run_a.as_dict()["source_histogram"] == {"correction": 4}


def test_train_reward_model_rejects_empty_dataset() -> None:
    with pytest.raises(RewardModelError):
        train_reward_model([])


def test_rank_candidates_never_overrides_the_verifier() -> None:
    # a reward model that loves self_confidence
    model = RewardModel(
        feature_names=("self_confidence",),
        weights=(1.0,),
        feature_means=(0.0,),
        feature_scales=(1.0,),
    )
    accepted = _Cand("CCO", accepted=True, self_confidence=0.01)  # low reward, verified
    rejected = _Cand("CCN", accepted=False, self_confidence=0.99)  # high reward, rejected

    ranked = rank_candidates([rejected, accepted], model)
    # verifier-accepted candidate is first DESPITE its lower reward -- science wins
    assert ranked[0].candidate is accepted
    assert ranked[0].accepted is True
    assert ranked[1].candidate is rejected

    # only with the verifier guard disabled does raw reward win (offline analysis)
    raw = rank_candidates([accepted, rejected], model, respect_verifier=False)
    assert raw[0].candidate is rejected


def test_rank_candidates_orders_within_accepted_set_by_reward() -> None:
    model = RewardModel(("self_confidence",), (1.0,), (0.0,), (1.0,))
    weak = _Cand("C1", accepted=True, self_confidence=0.2)
    strong = _Cand("C2", accepted=True, self_confidence=0.9)
    ranked = rank_candidates([weak, strong], model)
    assert [r.candidate for r in ranked] == [strong, weak]
    assert [r.rank for r in ranked] == [0, 1]


def test_default_candidate_features_uses_only_advisory_signals() -> None:
    cand = _Cand(
        "CCO", accepted=True, self_confidence=0.7, retrieval_supported=True,
        posterior_confidence=0.9, cited_analogue_ids=("a", "b"),
    )
    feats = default_candidate_features(cand)
    assert feats == {
        "self_confidence": 0.7,
        "retrieval_supported": 1.0,
        "posterior_confidence": 0.9,
        "n_cited_analogues": 2.0,
    }


def test_prioritize_annotation_queue_blends_severity_and_reward() -> None:
    model = RewardModel(("q",), (1.0,), (0.0,), (1.0,))
    # items carry a record_hash + severity; a side feature map drives the reward
    severe_wrong = ActiveLearningItem("rec-A", "override", 0.9, ("override",), "t1")
    severe_right = ActiveLearningItem("rec-B", "override", 0.9, ("override",), "t2")
    mild_wrong = ActiveLearningItem("rec-C", "override", 0.2, ("override",), "t3")
    feature_of = {"rec-A": {"q": -5.0}, "rec-B": {"q": 5.0}, "rec-C": {"q": -5.0}}

    scorer = reward_scorer(model, lambda it: feature_of[it.record_hash])
    ranked = prioritize_annotation_queue(
        [severe_right, mild_wrong, severe_wrong], reward_fn=scorer, reward_weight=0.5
    )
    # most informative first: high severity AND likely-wrong (low reward)
    assert ranked[0].item is severe_wrong
    assert ranked[0].rank == 0
    # severe-but-likely-right ranks below severe-and-likely-wrong
    order = [r.item for r in ranked]
    assert order.index(severe_wrong) < order.index(severe_right)

    # with no reward_fn it degrades to pure severity ordering
    by_severity = prioritize_annotation_queue([mild_wrong, severe_wrong])
    assert by_severity[0].item is severe_wrong
    assert by_severity[0].predicted_acceptance is None


def test_prioritize_annotation_queue_validates_weight() -> None:
    with pytest.raises(RewardModelError):
        prioritize_annotation_queue([], reward_weight=1.5)


# --------------------------------------------------------------------------- #
# Criterion 4: A/B champion vs challenger
# --------------------------------------------------------------------------- #
def test_canary_routing_is_sticky_and_splits_traffic() -> None:
    reg, _champ, chal = _registry_with_champion()
    ab = ABTest(reg, role=ModelRole.LORA_ADAPTER, nucleus="13C")
    router = ab.start(challenger_model_id=chal, mode=RoutingMode.CANARY, traffic_fraction=0.5)

    # sticky: the same routing key always lands in the same arm
    assert router.assign("req-1").arm == router.assign("req-1").arm

    keys = [f"req-{i}" for i in range(4000)]
    served_challenger = sum(1 for k in keys if router.assign(k).arm is Arm.CHALLENGER)
    assert 0.45 < served_challenger / len(keys) < 0.55  # ~50% to the challenger


def test_shadow_mode_never_serves_the_challenger() -> None:
    reg, _champ, chal = _registry_with_champion()
    ab = ABTest(reg, role=ModelRole.LORA_ADAPTER, nucleus="13C")
    router = ab.start(challenger_model_id=chal, mode=RoutingMode.SHADOW, traffic_fraction=1.0)

    asg = router.assign("anything")
    assert asg.arm is Arm.CHAMPION  # the user always gets the champion
    assert asg.served_model_id == router.champion_model_id
    assert asg.shadow_model_id == chal  # but the challenger is shadow-evaluated


def test_challenger_must_be_non_production_and_match_role_nucleus() -> None:
    reg, champ, _chal = _registry_with_champion()
    ab = ABTest(reg, role=ModelRole.LORA_ADAPTER, nucleus="13C")
    # the production champion cannot also be the challenger
    with pytest.raises(ABTestError):
        ab.start(challenger_model_id=champ)
    # an unknown model id is rejected
    with pytest.raises(KeyError):
        ab.start(challenger_model_id="lora_adapter:13C:9.9.9")


def test_no_production_champion_blocks_start() -> None:
    reg = ModelRegistry(InMemoryRegistryStore())
    chal = build_model_entry(
        role=ModelRole.LORA_ADAPTER, nucleus="13C", semantic_version="1.0.0",
        artifact_sha256="sha256:x", training_data_lineage=_LINEAGE,
    )
    reg.register(chal)
    ab = ABTest(reg, role=ModelRole.LORA_ADAPTER, nucleus="13C")
    with pytest.raises(ABTestError):
        ab.start(challenger_model_id=chal.model_id)


def test_promotion_decision_requires_dominance_guards_and_gate() -> None:
    reg, champ, chal = _registry_with_champion()
    ab = ABTest(reg, role=ModelRole.LORA_ADAPTER, nucleus="13C")
    ab.start(challenger_model_id=chal, mode=RoutingMode.CANARY, traffic_fraction=0.1)

    # challenger dominates on accuracy, no safety regression, better reviewer signals
    feedback = _feedback_for(champ, up=8, down=2) + _feedback_for(chal, up=9, down=1)
    good = ab.evaluate(
        champion_metrics=_mv(top1_accuracy=0.80),
        challenger_metrics=_mv(top1_accuracy=0.85),
        feedback_events=feedback,
        gate_exit_code=0,
    )
    assert good.dominates and good.safety_ok and good.override_ok and good.acceptance_ok
    assert good.gate_ok and good.promote is True
    assert good.requires_sign_off is True  # never auto-deploy
    assert good.challenger.override_rate == pytest.approx(0.1)
    assert good.champion.override_rate == pytest.approx(0.2)

    # a failed Prompt 18 gate blocks promotion even when the metrics dominate
    gated = ab.evaluate(
        champion_metrics=_mv(top1_accuracy=0.80),
        challenger_metrics=_mv(top1_accuracy=0.85),
        feedback_events=feedback,
        gate_exit_code=1,
    )
    assert gated.dominates and not gated.gate_ok and gated.promote is False


def test_promotion_blocked_on_safety_regression_and_override_spike() -> None:
    reg, champ, chal = _registry_with_champion()
    ab = ABTest(reg, role=ModelRole.LORA_ADAPTER, nucleus="13C")
    ab.start(challenger_model_id=chal, traffic_fraction=1.0)

    # better top-1 but a worse (higher) false-confirmation rate -- a safety regression
    unsafe = ab.evaluate(
        champion_metrics=_mv(top1_accuracy=0.80, false_confirmation_rate=0.02),
        challenger_metrics=_mv(top1_accuracy=0.90, false_confirmation_rate=0.05),
        gate_exit_code=0,
    )
    assert not unsafe.safety_ok and not unsafe.dominates and unsafe.promote is False

    # dominates on metrics, but reviewers override it far more than the champion
    feedback = _feedback_for(champ, up=9, down=1) + _feedback_for(chal, up=4, down=6)
    noisy = ab.evaluate(
        champion_metrics=_mv(top1_accuracy=0.80),
        challenger_metrics=_mv(top1_accuracy=0.85),
        feedback_events=feedback,
        gate_exit_code=0,
    )
    assert noisy.dominates and not noisy.override_ok and noisy.promote is False


def test_promote_requires_positive_decision_and_human_sign_off() -> None:
    reg, champ, chal = _registry_with_champion()
    ab = ABTest(reg, role=ModelRole.LORA_ADAPTER, nucleus="13C")
    ab.start(challenger_model_id=chal, traffic_fraction=1.0)
    decision = ab.evaluate(
        champion_metrics=_mv(top1_accuracy=0.80),
        challenger_metrics=_mv(top1_accuracy=0.85),
        gate_exit_code=0,
    )
    assert decision.promote is True
    # no auto-deploy: a positive decision alone is not enough
    with pytest.raises(PromotionBlocked):
        ab.promote(decision, signed_off_by="")
    # with sign-off, the registry promotes the challenger and retires the champion
    ab.promote(decision, signed_off_by="alice@lab")
    assert reg.resolve(ModelRole.LORA_ADAPTER, "13C").model_id == chal
    assert reg.current_status(champ) is ModelStatus.RETIRED
    assert reg.current_status(chal) is ModelStatus.PRODUCTION


def test_promote_refused_when_decision_is_negative() -> None:
    reg, _champ, chal = _registry_with_champion()
    ab = ABTest(reg, role=ModelRole.LORA_ADAPTER, nucleus="13C")
    ab.start(challenger_model_id=chal, traffic_fraction=1.0)
    bad = ab.evaluate(
        champion_metrics=_mv(top1_accuracy=0.80),
        challenger_metrics=_mv(top1_accuracy=0.70),  # worse -- no dominance
        gate_exit_code=0,
    )
    assert bad.promote is False
    with pytest.raises(PromotionBlocked):
        ab.promote(bad, signed_off_by="alice@lab")


def test_instant_rollback_is_a_routing_kill_not_a_registry_change() -> None:
    reg, champ, chal = _registry_with_champion()
    ab = ABTest(reg, role=ModelRole.LORA_ADAPTER, nucleus="13C")
    router = ab.start(challenger_model_id=chal, mode=RoutingMode.CANARY, traffic_fraction=0.5)
    # before rollback, some traffic reaches the challenger
    keys = [f"k-{i}" for i in range(500)]
    assert any(router.assign(k).arm is Arm.CHALLENGER for k in keys)

    ab.rollback(reason="elevated override rate")

    # after rollback every request goes to the champion -- instantly
    assert all(router.assign(k).arm is Arm.CHAMPION for k in keys)
    assert router.traffic_fraction == 0.0
    assert router.rolled_back is True
    # the registry is UNTOUCHED: champion still production, challenger still candidate
    assert reg.current_status(champ) is ModelStatus.PRODUCTION
    assert reg.current_status(chal) is ModelStatus.CANDIDATE
    assert reg.resolve(ModelRole.LORA_ADAPTER, "13C").model_id == champ


def test_evaluate_promotion_pure_function_with_armstats() -> None:
    # the decision logic is a pure function of two ArmStats (no registry needed)
    from moltrace.spectroscopy.feedback import ArmStats

    champ = ArmStats(Arm.CHAMPION, "champ", _mv(top1_accuracy=0.80), 10, 0.8, 0.2)
    chal = ArmStats(Arm.CHALLENGER, "chal", _mv(top1_accuracy=0.85), 10, 0.9, 0.1)
    decision = evaluate_promotion(champ, chal, gate_exit_code=0)
    assert decision.promote is True
    assert "champion" in decision.as_dict() and "challenger" in decision.as_dict()


def test_preference_dataclass_round_trips() -> None:
    pref = Preference({"a": 1.0}, {"a": 0.0}, source="correction", weight=2.0)
    payload = pref.as_dict()
    assert payload["source"] == "correction"
    assert payload["weight"] == 2.0
    assert pref.key().startswith("sha256:")
