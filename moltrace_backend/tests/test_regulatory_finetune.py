"""Prompt 15 — narrative LoRA fine-tuning (the regulated math stays frozen).

Covers the acceptance criteria: an approved-only, masked, provenance-tagged snapshot; leak-proof
K-fold CV with narrative-quality metrics; the math-frozen guards (no numeric/classification model is
ever touched); and adapter registration with lineage + gated promotion. The heavy training backend
is replaced by an injected fake trainer, so everything runs offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from moltrace.regulatory.ai import finetune as ft
from moltrace.regulatory.ai.active_learning import (
    ReviewerRole,
    ReviewKind,
    ReviewLog,
    ReviewSession,
    capture_review,
)
from moltrace.regulatory.ai.finetune import (
    FinalAdapter,
    FineTuneError,
    FineTuneUnavailable,
    FoldMetrics,
    NarrativeExample,
    NarrativeOnlyError,
    Snapshot,
    build_snapshot,
    finetune_narrative,
    mask_identifiers,
    narrative_promotion_gate,
    register_narrative_adapter,
)
from moltrace.regulatory.ai.registry import (
    ArtifactKind,
    ArtifactStatus,
    default_regulatory_registry,
)
from moltrace.regulatory.infra import RegulatoryMetricVector

_NOW = "2026-01-01T00:00:00+00:00"


def _narrative(log, *, dossier, text, reviewer="ra-1", draft="draft text") -> None:
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.NARRATIVE_EDIT,
            reviewer_id=reviewer,
            reviewer_role=ReviewerRole.REGULATORY_AFFAIRS,
            inputs={"dossier": dossier, "section": "3.2.S.3.2"},
            ai_output=draft,
            human_final=text,
            context={"decision_type": "ctd_section", "citations": ["ICH M7(R2)"]},
        ),
        log=log,
    )


def _corpus() -> ReviewLog:
    """Six approved narrative edits across three dossiers (groups) + two non-narrative reviews."""

    log = ReviewLog()
    for i, dossier in enumerate(["D-1", "D-1", "D-2", "D-2", "D-3", "D-3"]):
        _narrative(log, dossier=dossier, text=f"Approved narrative {i} for {dossier}.")
    # a classification adjudication and a triage override that must NEVER train
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.CLASSIFICATION_ADJUDICATION,
            reviewer_id="tox-1",
            reviewer_role=ReviewerRole.TOXICOLOGIST,
            inputs={"smiles": "CN(C)N=O"},
            ai_output={"m7_class": 3},
            human_final={"m7_class": 3},
            context={"decision_type": "m7_classification"},
        ),
        log=log,
    )
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.TRIAGE_OVERRIDE,
            reviewer_id="ra-2",
            reviewer_role=ReviewerRole.REGULATORY_AFFAIRS,
            inputs={"item": "x"},
            ai_output="route A",
            human_final="route B",
        ),
        log=log,
    )
    return log


class _RecordingTrainer:
    """A fake trainer that records what it was trained on (offline; no heavy deps)."""

    def __init__(self, *, acceptance=0.92, edit=0.10, citation=0.99) -> None:
        self.metrics = (acceptance, edit, citation)
        self.fold_groups: list[tuple[set, set]] = []  # (eval_groups, train_groups) per fold
        self.seen_decision_types: set[str] = set()

    def train_and_eval(self, *, fold, train, eval, base_model_id, lora_config) -> FoldMetrics:
        self.fold_groups.append(({e.group_key for e in eval}, {e.group_key for e in train}))
        self.seen_decision_types |= {e.decision_type for e in (*train, *eval)}
        a, e, c = self.metrics
        return FoldMetrics(fold, len(train), len(eval), a, e, c, 0.5)

    def fit_final(self, *, train, base_model_id, lora_config, out_dir) -> FinalAdapter:
        self.seen_decision_types |= {e.decision_type for e in train}
        return FinalAdapter(path=str(out_dir), sha256="sha256:fakeadapter", gpu_hours=0.5)


# --------------------------------------------------------------------------- #
# Acceptance 1: approved-only snapshot with provenance + identifier masking
# --------------------------------------------------------------------------- #
def test_snapshot_is_approved_only_with_provenance_and_masking() -> None:
    log = ReviewLog()
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.NARRATIVE_EDIT,
            reviewer_id="ra-1",
            reviewer_role=ReviewerRole.REGULATORY_AFFAIRS,
            inputs={"dossier": "D-1"},
            ai_output="Draft for batch B-2026-014.",
            human_final="Approved narrative for batch B-2026-014; contact jane@acme.com.",
            context={"decision_type": "ctd_section"},
        ),
        log=log,
    )
    # a classification adjudication that must be excluded
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.CLASSIFICATION_ADJUDICATION,
            reviewer_id="tox-1",
            reviewer_role=ReviewerRole.TOXICOLOGIST,
            inputs={"smiles": "CN(C)N=O"},
            ai_output={"m7_class": 3},
            human_final={"m7_class": 3},
            context={"decision_type": "m7_classification"},
        ),
        log=log,
    )
    snap = build_snapshot(log, extra_identifiers=["Examplinib"], git_sha="abc", created_utc=_NOW)
    assert snap.row_count == 1  # only the approved narrative edit
    assert snap.per_decision_type == {"ctd_section": 1}
    example = snap.examples[0]
    # identifiers masked (email + batch id) before storage
    assert "jane@acme.com" not in example.approved_text and "[EMAIL]" in example.approved_text
    assert "B-2026-014" not in example.approved_text and "[ID]" in example.approved_text
    # provenance captured
    assert snap.provenance[0]["reviewer_id"] == "ra-1"
    assert snap.snapshot_hash.startswith("sha256:") and snap.masked is True
    # the serialized snapshot carries NO narrative bodies (no confidential text in logs/git)
    d = snap.as_dict()
    assert "examples" not in d and "approved_text" not in d
    # deterministic: same input -> same snapshot hash
    assert build_snapshot(log, extra_identifiers=["Examplinib"], git_sha="x", created_utc=_NOW).snapshot_hash == snap.snapshot_hash


def test_snapshot_excludes_rejected_without_correction() -> None:
    log = ReviewLog()
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.NARRATIVE_EDIT,
            reviewer_id="ra-1",
            reviewer_role=ReviewerRole.REGULATORY_AFFAIRS,
            inputs={"dossier": "D-1"},
            ai_output="a draft the reviewer rejected without writing a correction",
            human_final="",  # no approved text -> not training data
            context={"decision_type": "ctd_section"},
        ),
        log=log,
    )
    assert build_snapshot(log, created_utc=_NOW).row_count == 0


def test_mask_identifiers() -> None:
    masked = mask_identifiers(
        "Batch B-2026-014 / LOT 778; email a.b@c.io; product Examplinib",
        extra_identifiers=["Examplinib"],
    )
    assert "B-2026-014" not in masked and "a.b@c.io" not in masked and "Examplinib" not in masked
    assert "[ID]" in masked and "[EMAIL]" in masked and "[REDACTED]" in masked


# --------------------------------------------------------------------------- #
# Acceptance 2: K-fold CV with narrative-quality metrics
# --------------------------------------------------------------------------- #
def test_kfold_cv_tracks_narrative_metrics_and_cost() -> None:
    snap = build_snapshot(_corpus(), git_sha="abc", created_utc=_NOW)
    assert snap.row_count == 6 and snap.n_groups == 3  # six narratives, three dossiers
    trainer = _RecordingTrainer()
    run = finetune_narrative(
        snap, "base-llm", k_folds=3, trainer=trainer, gpu_cost_per_hour=2.0,
        git_sha="abc", created_utc=_NOW,
    )
    # >= 2 non-empty folds (3 groups distribute across folds by seeded hash, not evenly)
    assert len(run.fold_metrics) >= 2
    assert run.acceptance_mean == 0.92 and run.edit_distance_mean == 0.10
    assert run.citation_correctness_mean == 0.99
    assert run.cost_usd == run.gpu_hours * 2.0 and run.gpu_hours > 0
    assert run.adapter_sha256 == "sha256:fakeadapter"
    # narrative metric vector for the promotion gate
    mv = run.metric_vector()
    assert mv.narrative_acceptance_rate == 0.92 and mv.citation_correctness == 0.99


def test_kfold_is_leak_proof_by_group() -> None:
    snap = build_snapshot(_corpus(), git_sha="abc", created_utc=_NOW)
    trainer = _RecordingTrainer()
    finetune_narrative(snap, "base-llm", k_folds=3, trainer=trainer, git_sha="abc", created_utc=_NOW)
    # within every fold, no dossier (group) appears in both train and eval
    for eval_groups, train_groups in trainer.fold_groups:
        assert eval_groups.isdisjoint(train_groups)


def test_finetune_needs_at_least_two_groups() -> None:
    log = ReviewLog()
    _narrative(log, dossier="D-1", text="one")  # single group -> cannot cross-validate
    snap = build_snapshot(log, created_utc=_NOW)
    with pytest.raises(FineTuneError, match="CV groups"):
        finetune_narrative(snap, "base-llm", trainer=_RecordingTrainer(), created_utc=_NOW)


def test_training_backend_unavailable_without_injected_trainer() -> None:
    snap = build_snapshot(_corpus(), created_utc=_NOW)
    with pytest.raises(FineTuneUnavailable):
        finetune_narrative(snap, "base-llm", k_folds=3, created_utc=_NOW)


# --------------------------------------------------------------------------- #
# Acceptance 3 / HARD RULES: no numeric/classification model is ever touched
# --------------------------------------------------------------------------- #
def test_frozen_decision_type_is_refused_at_snapshot() -> None:
    log = ReviewLog()
    # a NARRATIVE_EDIT mislabelled with a frozen (deterministic) decision type
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.NARRATIVE_EDIT,
            reviewer_id="ra-1",
            reviewer_role=ReviewerRole.REGULATORY_AFFAIRS,
            inputs={"dossier": "D-1"},
            ai_output="x",
            human_final="y",
            context={"decision_type": "m7_classification"},  # frozen!
        ),
        log=log,
    )
    with pytest.raises(NarrativeOnlyError, match="m7_classification"):
        build_snapshot(log, created_utc=_NOW)


@pytest.mark.parametrize(
    "smuggled",
    [
        "M7_classification",  # case variant of a frozen type
        " m7_classification ",  # whitespace-padded
        "cpca",  # classification alias
        "m7",  # classification alias
        "q6a",  # specification alias
        "totally_unknown_type",  # unknown label
    ],
)
def test_allowlist_rejects_non_narrative_decision_types(smuggled: str) -> None:
    # the math-frozen guard is a fail-closed ALLOWLIST: anything not an approved narrative
    # decision type (incl. case/alias/whitespace variants of a classification) is refused.
    log = ReviewLog()
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.NARRATIVE_EDIT,
            reviewer_id="ra-1",
            reviewer_role=ReviewerRole.REGULATORY_AFFAIRS,
            inputs={"dossier": "D-1"},
            ai_output="x",
            human_final="y",
            context={"decision_type": smuggled},
        ),
        log=log,
    )
    with pytest.raises(NarrativeOnlyError):
        build_snapshot(log, created_utc=_NOW)


def test_caller_identifier_redacted_whole_before_builtin_regex() -> None:
    # extra_identifiers are redacted FIRST, so the built-in id regex can't fragment a codename
    masked = mask_identifiers("AB-12-Phoenix program", extra_identifiers=["AB-12-Phoenix"])
    assert "Phoenix" not in masked and "[REDACTED]" in masked
    log = ReviewLog()
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.NARRATIVE_EDIT,
            reviewer_id="ra-1",
            reviewer_role=ReviewerRole.REGULATORY_AFFAIRS,
            inputs={"dossier": "D-1"},
            ai_output="The AB-12-Phoenix program draft.",
            human_final="Approved: the AB-12-Phoenix program.",
            context={"decision_type": "ctd_section"},
        ),
        log=log,
    )
    snap = build_snapshot(log, mask=True, extra_identifiers=["AB-12-Phoenix"], created_utc=_NOW)
    assert "Phoenix" not in snap.examples[0].draft
    assert "Phoenix" not in snap.examples[0].approved_text


def test_citations_are_masked() -> None:
    log = ReviewLog()
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.NARRATIVE_EDIT,
            reviewer_id="ra-1",
            reviewer_role=ReviewerRole.REGULATORY_AFFAIRS,
            inputs={"dossier": "D-1"},
            ai_output="d",
            human_final="approved",
            context={"decision_type": "ctd_section", "citations": ["see jane@x.io re NDA-211234"]},
        ),
        log=log,
    )
    snap = build_snapshot(log, mask=True, created_utc=_NOW)
    citation = snap.examples[0].citations[0]
    assert "jane@x.io" not in citation and "NDA-211234" not in citation


def test_finetune_decision_types_importable_from_ai_package() -> None:
    from moltrace.regulatory.ai import (  # noqa: PLC0415 - import-in-test by design
        FROZEN_DECISION_TYPES,
        NARRATIVE_DECISION_TYPES,
        FineTuneError,
    )

    assert "m7_classification" in FROZEN_DECISION_TYPES
    assert "ctd_section" in NARRATIVE_DECISION_TYPES
    assert issubclass(FineTuneError, Exception)


def test_promotion_blocked_when_candidate_citation_unmeasured() -> None:
    incumbent = RegulatoryMetricVector(
        narrative_acceptance_rate=0.80, mean_edit_distance=0.20, citation_correctness=0.99
    )
    candidate = RegulatoryMetricVector(
        narrative_acceptance_rate=0.99, mean_edit_distance=0.01, citation_correctness=None
    )
    ok, reasons = narrative_promotion_gate(candidate, incumbent)
    assert ok is False and any("citation_correctness" in r for r in reasons)


def test_finetune_reasserts_narrative_only() -> None:
    frozen = NarrativeExample(
        train_hash="sha256:1", source_example_id="e1", decision_type="cpca_classification",
        draft="d", approved_text="a", citations=(), reviewer_id="r", approved_utc=_NOW,
        group_key="g1",
    )
    snap = Snapshot(
        snapshot_hash="sha256:s", row_count=1, examples=(frozen,), train_hashes=("sha256:1",),
        per_decision_type={"cpca_classification": 1}, record_groups={"sha256:1": "g1"},
        n_groups=1, masked=True, provenance=(), git_sha="x", created_utc=_NOW,
    )
    with pytest.raises(NarrativeOnlyError):
        finetune_narrative(snap, "base-llm", trainer=_RecordingTrainer(), created_utc=_NOW)


def test_trainer_only_ever_sees_narrative_text() -> None:
    # a mixed corpus -> the fake trainer must only ever receive narrative decision types
    snap = build_snapshot(_corpus(), git_sha="abc", created_utc=_NOW)
    trainer = _RecordingTrainer()
    finetune_narrative(snap, "base-llm", k_folds=3, trainer=trainer, git_sha="abc", created_utc=_NOW)
    assert trainer.seen_decision_types <= ft.NARRATIVE_DECISION_TYPES
    assert not (trainer.seen_decision_types & ft.FROZEN_DECISION_TYPES)


def test_module_never_imports_the_deterministic_engines() -> None:
    # structural guard: the fine-tune module cannot touch a number/classification engine
    src = Path(ft.__file__).read_text()
    for engine in ("classify_m7", "classify_cpca", "calculate_q3ab", "q3d_elements",
                   "q3c_solvents", "calculate_cumulative_risk", "build_specification"):
        assert engine not in src, f"finetune.py must not reference the deterministic engine {engine}"


# --------------------------------------------------------------------------- #
# Acceptance 4: adapter registered with lineage; promotion gated (Prompt 17)
# --------------------------------------------------------------------------- #
def _run(citation=0.99, acceptance=0.92, edit=0.10) -> ft.FineTuneRun:
    snap = build_snapshot(_corpus(), git_sha="abc", created_utc=_NOW)
    trainer = _RecordingTrainer(acceptance=acceptance, edit=edit, citation=citation)
    return finetune_narrative(snap, "base-llm", k_folds=3, trainer=trainer, git_sha="abc", created_utc=_NOW)


def test_adapter_registered_with_lineage_as_candidate() -> None:
    reg = default_regulatory_registry()
    entry = register_narrative_adapter(_run(), registry=reg, name="house_style_v1")
    assert entry.kind is ArtifactKind.NARRATIVE_ADAPTER
    assert reg.current_status(entry.entry_id) is ArtifactStatus.CANDIDATE  # no incumbent -> candidate
    assert entry.extra["snapshot_hash"].startswith("sha256:")
    assert entry.extra["base_model_id"] == "base-llm"
    assert "metrics" in entry.extra and "cost_usd" in entry.extra


def test_promotion_gated_on_improvement_with_citation_no_regression() -> None:
    reg = default_regulatory_registry()
    incumbent = RegulatoryMetricVector(
        narrative_acceptance_rate=0.85, mean_edit_distance=0.15, citation_correctness=0.99
    )
    entry = register_narrative_adapter(
        _run(citation=0.99, acceptance=0.92, edit=0.10),  # acceptance up, edit down, citation equal
        registry=reg, name="improved", incumbent_metrics=incumbent,
    )
    assert reg.current_status(entry.entry_id) is ArtifactStatus.SHADOW  # promoted (gated)


def test_promotion_blocked_on_citation_regression() -> None:
    reg = default_regulatory_registry()
    incumbent = RegulatoryMetricVector(
        narrative_acceptance_rate=0.85, mean_edit_distance=0.15, citation_correctness=0.999
    )
    entry = register_narrative_adapter(
        _run(citation=0.99, acceptance=0.99, edit=0.05),  # better drafting BUT citation regressed
        registry=reg, name="cite_regressed", incumbent_metrics=incumbent,
    )
    assert reg.current_status(entry.entry_id) is ArtifactStatus.CANDIDATE  # NOT promoted


def test_narrative_promotion_gate_logic() -> None:
    base = RegulatoryMetricVector(
        narrative_acceptance_rate=0.85, mean_edit_distance=0.15, citation_correctness=0.95
    )
    better = RegulatoryMetricVector(
        narrative_acceptance_rate=0.90, mean_edit_distance=0.12, citation_correctness=0.96
    )
    assert narrative_promotion_gate(better, base)[0] is True
    # citation regression is a hard blocker even if drafting improves
    cite_down = RegulatoryMetricVector(
        narrative_acceptance_rate=0.99, mean_edit_distance=0.01, citation_correctness=0.90
    )
    ok, reasons = narrative_promotion_gate(cite_down, base)
    assert ok is False and any("citation_correctness" in r for r in reasons)
    # no improvement -> not promotable
    assert narrative_promotion_gate(base, base)[0] is False
