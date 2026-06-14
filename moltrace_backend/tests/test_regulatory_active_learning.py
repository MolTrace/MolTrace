"""Prompt 16 — active-learning loop on regulatory reviewer feedback.

Covers the four acceptance criteria: review capture with full provenance (append-only); the
borderline queue (classifications → toxicologist, narrative → disagreement sampling); the
narrative-only retrain trigger wired to a Prompt 15 hook; and the HARD-RULE guard that the loop
never silently changes a classification boundary. Everything runs offline.
"""

from __future__ import annotations

import pytest

from moltrace.regulatory.ai import active_learning as al
from moltrace.regulatory.ai.active_learning import (
    ClassificationCandidate,
    LabeledExample,
    NarrativeCandidate,
    ReviewerRole,
    ReviewKind,
    ReviewLog,
    ReviewSession,
    borderline_queue,
    capture_review,
    classification_ambiguity,
    evaluate_retraining,
    maybe_kickoff_narrative_retrain,
    narrative_disagreement,
    retraining_trigger,
)
from moltrace.regulatory.compliance.annex22_wrapper import Annex22Log
from moltrace.regulatory.impurities.m7_classifier import classify_m7

_NOW = "2026-01-01T00:00:00+00:00"


def _narrative_session(human_final="edited narrative") -> ReviewSession:
    return ReviewSession(
        review_kind=ReviewKind.NARRATIVE_EDIT,
        reviewer_id="rev-1",
        reviewer_role=ReviewerRole.REGULATORY_AFFAIRS,
        inputs={"dossier": "D-1", "section": "3.2.S.3.2"},
        ai_output="draft narrative",
        human_final=human_final,
        rule_set_version="rs-abc",
        model_versions={"narrative_adapter": "narrative_adapter:draft:1.0.0"},
        created_utc=_NOW,
    )


# --------------------------------------------------------------------------- #
# Acceptance 1: review capture with full provenance (append-only)
# --------------------------------------------------------------------------- #
def test_capture_records_full_provenance() -> None:
    log = ReviewLog()
    ex = capture_review(_narrative_session(), log=log)
    assert isinstance(ex, LabeledExample)
    assert ex.review_kind is ReviewKind.NARRATIVE_EDIT
    assert ex.reviewer_id == "rev-1" and ex.reviewer_role is ReviewerRole.REGULATORY_AFFAIRS
    assert ex.inputs == {"dossier": "D-1", "section": "3.2.S.3.2"}
    assert ex.ai_output == "draft narrative" and ex.human_final == "edited narrative"
    assert ex.rule_set_version == "rs-abc"
    assert ex.model_versions == {"narrative_adapter": "narrative_adapter:draft:1.0.0"}
    assert ex.created_utc == _NOW
    assert ex.example_id.startswith("sha256:")
    assert log.examples() == (ex,)


def test_review_log_is_append_only_and_idempotent() -> None:
    log = ReviewLog()
    capture_review(_narrative_session(), log=log)
    capture_review(_narrative_session(), log=log)  # identical -> same id -> idempotent
    assert len(log) == 1
    capture_review(_narrative_session(human_final="different edit"), log=log)
    assert len(log) == 2
    # append-only: no public mutation/deletion API, reads are immutable tuples
    assert isinstance(log.examples(), tuple)
    for forbidden in ("remove", "delete", "pop", "clear", "update"):
        assert not hasattr(log, forbidden)


def test_context_is_part_of_the_identity_so_distinct_reviews_dont_collide() -> None:
    log = ReviewLog()
    base = _narrative_session()
    e1 = capture_review(
        ReviewSession(**{**base.__dict__, "context": {"review_session": "RS-100"}}), log=log
    )
    e2 = capture_review(
        ReviewSession(**{**base.__dict__, "context": {"review_session": "RS-200"}}), log=log
    )
    assert e1.example_id != e2.example_id  # context is provenance -> changes the identity
    assert len(log) == 2  # neither event is silently dropped
    assert {e.context["review_session"] for e in log.examples()} == {"RS-100", "RS-200"}


def test_capture_mirrors_to_annex22_expert_review_log() -> None:
    audit = Annex22Log()
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.CLASSIFICATION_ADJUDICATION,
            reviewer_id="tox-1",
            reviewer_role=ReviewerRole.TOXICOLOGIST,
            inputs={"smiles": "CCO"},
            ai_output={"m7_class": 3},
            human_final={"m7_class": 3, "note": "confirmed"},
            model_versions={"rule_engine": "ich_m7"},
            created_utc=_NOW,
        ),
        log=ReviewLog(),
        audit_log=audit,
    )
    records = audit.records()
    assert len(records) == 1
    assert records[0].decision_type == "review:classification_adjudication"
    assert records[0].risk_level == "high"
    ok, breaks = audit.verify_chain()
    assert ok and not breaks


# --------------------------------------------------------------------------- #
# Acceptance 2: borderline queue
# --------------------------------------------------------------------------- #
def _m7(concordance="concordant_negative", *, coc=False, alerts=()) -> dict:
    return {
        "m7_class": 5,
        "in_silico_concordance": concordance,
        "coc_flag": coc,
        "structural_alerts": alerts,
        "expert_review_required": concordance == "discordant" or coc,
    }


def _cpca(*, activating=(), deactivating=(), coc=False, potency_score=2) -> dict:
    return {
        "category": 2,
        "activating_features": activating,
        "deactivating_features": deactivating,
        "coc_flag": coc,
        "potency_score": potency_score,
    }


def test_borderline_classification_routes_to_toxicologist() -> None:
    cands = [
        ClassificationCandidate("m7-disc", "m7", _m7("discordant")),
        ClassificationCandidate("cpca-conf", "cpca", _cpca(activating=("a",), deactivating=("d",))),
    ]
    q = borderline_queue(cands, budget=10)
    assert len(q) == 2
    assert all(item.route_to is ReviewerRole.TOXICOLOGIST for item in q)
    assert all(item.item_type == "classification" and item.ambiguity > 0 for item in q)
    assert any("discordant" in item.reason for item in q)


def test_non_borderline_classification_is_excluded() -> None:
    cands = [ClassificationCandidate("m7-clean", "m7", _m7("concordant_negative"))]
    assert borderline_queue(cands, budget=10) == []
    score, is_borderline, _ = classification_ambiguity("m7", _m7("concordant_negative"))
    assert score == 0.0 and is_borderline is False


def test_forced_category5_cpca_is_not_over_escalated() -> None:
    # potency_score=None means a forced Category 5 (lowest potency) — least in need of toxicology
    # time, so it must NOT be flagged borderline on that basis alone.
    score, is_borderline, _ = classification_ambiguity(
        "cpca",
        {"category": 5, "potency_score": None, "activating_features": (), "deactivating_features": ()},
    )
    assert score == 0.0 and is_borderline is False
    # but a genuine cohort-of-concern Cat-5 still escalates (on the CoC signal, not None-potency)
    score2, borderline2, reason2 = classification_ambiguity(
        "cpca", {"category": 5, "potency_score": None, "coc_flag": True}
    )
    assert borderline2 is True and "cohort of concern" in reason2 and "potency" not in reason2


def test_narrative_queue_uses_disagreement_sampling() -> None:
    high = NarrativeCandidate("n-high", ["draft A", "draft B", "draft C"])  # all differ
    low = NarrativeCandidate("n-low", ["same", "same", "different"])  # mostly agree
    agree = NarrativeCandidate("n-agree", ["same", "same", "same"])  # no disagreement
    q = borderline_queue([low, agree, high], budget=10)
    ids = [item.item_id for item in q]
    assert "n-agree" not in ids  # zero disagreement -> not informative -> excluded
    assert ids == ["n-high", "n-low"]  # ranked by disagreement, descending
    assert all(item.route_to is ReviewerRole.REGULATORY_AFFAIRS for item in q)
    assert narrative_disagreement(["x", "x", "x"]) == 0.0
    assert narrative_disagreement(["x", "y", "z"]) > narrative_disagreement(["x", "x", "y"])


def test_classifications_precede_narratives_and_budget_respected() -> None:
    cands = [
        NarrativeCandidate("n1", ["a", "b"]),
        ClassificationCandidate("m7-disc", "m7", _m7("discordant", coc=True)),
        ClassificationCandidate("cpca-conf", "cpca", _cpca(activating=("a",), deactivating=("d",))),
    ]
    q = borderline_queue(cands, budget=2)
    assert len(q) == 2  # budget respected
    assert all(item.item_type == "classification" for item in q)  # toxicologist cases first


def test_ambiguity_ranks_more_signals_higher() -> None:
    strong = ClassificationCandidate("strong", "m7", _m7("discordant", coc=True, alerts=("x", "y")))
    weak = ClassificationCandidate("weak", "m7", _m7("discordant"))
    q = borderline_queue([weak, strong], budget=10)
    assert [item.item_id for item in q] == ["strong", "weak"]


def test_budget_validation() -> None:
    with pytest.raises(ValueError):
        borderline_queue([], budget=-1)
    assert borderline_queue([NarrativeCandidate("n", ["a", "b"])], budget=0) == []


# --------------------------------------------------------------------------- #
# Acceptance 3: retrain trigger wired to Prompt 15; classifications excluded
# --------------------------------------------------------------------------- #
def test_retraining_trigger_fires_on_volume() -> None:
    assert retraining_trigger(new_approved_narratives=50, now_utc=_NOW) is True
    assert retraining_trigger(new_approved_narratives=10, now_utc=_NOW) is False


def test_retraining_trigger_fires_on_schedule() -> None:
    assert retraining_trigger(
        new_approved_narratives=1, last_retrain_utc="2025-11-01T00:00:00+00:00", now_utc=_NOW
    ) is True  # > 30 days elapsed
    assert retraining_trigger(
        new_approved_narratives=1, last_retrain_utc="2025-12-25T00:00:00+00:00", now_utc=_NOW
    ) is False  # < 30 days


def test_retrain_trigger_tolerates_a_naive_last_retrain_timestamp() -> None:
    # a caller-supplied naive ISO timestamp is assumed UTC, not a TypeError crash
    assert retraining_trigger(
        new_approved_narratives=1, last_retrain_utc="2025-11-01T00:00:00", now_utc=_NOW
    ) is True  # > 30 days
    assert retraining_trigger(
        new_approved_narratives=1, last_retrain_utc="2025-12-25T00:00:00", now_utc=_NOW
    ) is False  # < 30 days


def test_maybe_kickoff_invokes_prompt15_hook_only_when_fired() -> None:
    received: list = []

    def hook(examples):
        received.append(list(examples))
        return "model-v2"

    no = evaluate_retraining(new_approved_narratives=1, now_utc=_NOW)
    assert maybe_kickoff_narrative_retrain(no, [], hook=hook) is None and received == []

    yes = evaluate_retraining(new_approved_narratives=99, now_utc=_NOW)
    out = maybe_kickoff_narrative_retrain(yes, [], hook=hook)
    assert out == "model-v2" and received == [[]]


def test_classification_examples_never_reach_the_retrain_hook() -> None:
    narrative = capture_review(_narrative_session(), log=(log := ReviewLog()))
    classification = capture_review(
        ReviewSession(
            review_kind=ReviewKind.CLASSIFICATION_ADJUDICATION,
            reviewer_id="tox-1",
            reviewer_role=ReviewerRole.TOXICOLOGIST,
            inputs={"smiles": "CCO"},
            ai_output={"m7_class": 3},
            human_final={"m7_class": 3},
            created_utc=_NOW,
        ),
        log=log,
    )
    assert narrative.feeds_narrative_retrain is True
    assert classification.feeds_narrative_retrain is False
    # the trigger counts only narrative examples
    assert log.narrative_examples() == (narrative,)
    delivered: list = []
    yes = evaluate_retraining(new_approved_narratives=99, now_utc=_NOW)
    maybe_kickoff_narrative_retrain(yes, log.examples(), hook=lambda ex: delivered.extend(ex))
    assert classification not in delivered and narrative in delivered


# --------------------------------------------------------------------------- #
# Acceptance 4: guard — no model silently changes a classification boundary
# --------------------------------------------------------------------------- #
def test_loop_never_changes_a_real_classification() -> None:
    result = classify_m7("CCO")  # real deterministic classification
    before = result.as_dict()
    cand = ClassificationCandidate("c1", "m7", result)
    # run it through every loop path that touches a classification
    classification_ambiguity("m7", result)
    queue = borderline_queue([cand], budget=5)
    capture_review(
        ReviewSession(
            review_kind=ReviewKind.CLASSIFICATION_ADJUDICATION,
            reviewer_id="tox-1",
            reviewer_role=ReviewerRole.TOXICOLOGIST,
            inputs={"smiles": "CCO"},
            ai_output=result.as_dict(),
            human_final=result.as_dict(),
            created_utc=_NOW,
        ),
        log=ReviewLog(),
    )
    assert result.as_dict() == before  # the m7_class / boundary is byte-identical, untouched
    # if it surfaced for review, the queued payload is the SAME object, unchanged
    for item in queue:
        assert item.payload.result is result


def test_no_classification_retrain_path_exists() -> None:
    # structural guard: nothing in the module retrains or re-derives a classification boundary
    names = dir(al)
    assert not any(
        ("classif" in n.lower() and ("retrain" in n.lower() or "finetune" in n.lower()))
        for n in names
    )
    # the only retrain entry points are narrative-scoped
    assert "retraining_trigger" in names and "maybe_kickoff_narrative_retrain" in names
