"""Prompt 22 — feedback capture, narrative RLHF reward & A/B rollout (math stays frozen).

Covers the three acceptance criteria: the in-app feedback control (accept/edit + free-text + reason
taxonomy, stored with versions, classification overrides routed to a toxicologist and NEVER silently
learned); the NARRATIVE-only preference + reward model (guard: no numeric/classification influence);
and champion/challenger A/B (zero calc-error + citation no-regression + dominance gated, no
auto-deploy, instant rollback). Everything runs offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from moltrace.regulatory.ai.active_learning import ReviewerRole, ReviewKind, ReviewLog
from moltrace.regulatory.feedback import (
    NARRATIVE_FEATURE_NAMES,
    ABTest,
    Arm,
    ArmStats,
    FeedbackVerdict,
    InMemoryFeedbackStore,
    OutputKind,
    PromotionBlocked,
    ReasonCode,
    RewardModelError,
    RoutingMode,
    build_preference_dataset,
    capture_feedback,
    default_narrative_features,
    evaluate_promotion,
    rank_narratives,
    train_narrative_reward_model,
)
from moltrace.regulatory.feedback import narrative_reward as nr
from moltrace.regulatory.infra import RegulatoryMetricVector


# --------------------------------------------------------------------------- #
# Acceptance 1: feedback control — taxonomy, versions, classification routing
# --------------------------------------------------------------------------- #
def test_reason_taxonomy_members() -> None:
    assert {r.value for r in ReasonCode} == {
        "wrong_classification",
        "citation_missing",
        "citation_wrong",
        "tone_format",
        "factual_edit",
        "scope",
        "other",
    }


def test_event_stored_with_versions() -> None:
    store = InMemoryFeedbackStore()
    result = capture_feedback(
        output_kind=OutputKind.NARRATIVE,
        output_ref="n-1",
        verdict=FeedbackVerdict.ACCEPT,
        model_versions={"narrative_adapter": "v1"},
        rule_set_version="sha256:rs",
        reason=None,
        free_text="looks good",
        store=store,
    )
    events = store.all_events()
    assert len(events) == 1
    e = events[0]
    assert e.model_versions == {"narrative_adapter": "v1"} and e.rule_set_version == "sha256:rs"
    assert e.event_id().startswith("sha256:") and result.event is e
    # idempotent: the same event is not double-stored
    store.add_event(e)
    assert len(store.all_events()) == 1


def test_classification_override_routes_to_toxicologist_never_silently_learned() -> None:
    store = InMemoryFeedbackStore()
    log = ReviewLog()
    result = capture_feedback(
        output_kind=OutputKind.CLASSIFICATION,
        output_ref="m7-1",
        verdict=FeedbackVerdict.REJECT,
        model_versions={"rule_engine": "ich_m7"},
        reason=ReasonCode.WRONG_CLASSIFICATION,
        classification_result={
            "m7_class": 3,
            "in_silico_concordance": "discordant",
            "coc_flag": True,
            "structural_alerts": ["alert"],
        },
        context={"engine": "m7"},
        reviewer_id="ra-1",
        store=store,
        review_log=log,
    )
    assert result.routed_to is ReviewerRole.TOXICOLOGIST
    assert result.is_classification_override
    assert result.review_queue and result.review_queue[0].route_to is ReviewerRole.TOXICOLOGIST
    # recorded as an adjudication that NEVER feeds narrative learning
    adjudications = log.examples(review_kind=ReviewKind.CLASSIFICATION_ADJUDICATION)
    assert len(adjudications) == 1 and adjudications[0].feeds_narrative_retrain is False
    assert log.narrative_examples() == ()  # the override never becomes a narrative training signal


def test_event_id_includes_context_so_distinct_overrides_dont_collide() -> None:
    store = InMemoryFeedbackStore()
    common = dict(
        output_kind=OutputKind.CLASSIFICATION,
        output_ref="m7-1",
        verdict=FeedbackVerdict.REJECT,
        model_versions={"rule_engine": "ich_m7"},
        classification_result={"m7_class": 3},
        reviewer_id="ra-1",
        store=store,
        now="2026-01-01T00:00:00+00:00",  # pinned identical timestamp
    )
    capture_feedback(**common, context={"engine": "m7", "note": "alpha"})
    capture_feedback(**common, context={"engine": "m7", "note": "beta-different"})
    assert len(store.all_events()) == 2  # context is part of the identity -> no silent drop


def test_narrative_edit_becomes_a_learning_signal() -> None:
    log = ReviewLog()
    result = capture_feedback(
        output_kind=OutputKind.NARRATIVE,
        output_ref="n-1",
        verdict=FeedbackVerdict.EDIT,
        model_versions={"narrative_adapter": "v1"},
        reason=ReasonCode.CITATION_MISSING,
        corrected_text="Mutagenic impurities follow the TTC basis [S1].",
        context={"draft": "Mutagenic impurities follow the TTC basis.", "decision_type": "ctd_section"},
        reviewer_id="ra-1",
        review_log=log,
    )
    assert result.review_example is not None
    assert result.review_example.review_kind is ReviewKind.NARRATIVE_EDIT
    assert result.review_example.feeds_narrative_retrain is True
    assert len(log.narrative_examples()) == 1


# --------------------------------------------------------------------------- #
# Acceptance 2: NARRATIVE-only preference + reward model (no numeric influence)
# --------------------------------------------------------------------------- #
def _narrative_feedback(store, ref, draft, corrected) -> None:
    capture_feedback(
        output_kind=OutputKind.NARRATIVE,
        output_ref=ref,
        verdict=FeedbackVerdict.EDIT,
        model_versions={"narrative_adapter": "v1"},
        corrected_text=corrected,
        context={"draft": draft},
        store=store,
    )


def test_preference_dataset_is_narrative_only() -> None:
    store = InMemoryFeedbackStore()
    _narrative_feedback(store, "n-1", "no citation", "well cited [S1].")
    # a classification override must NOT contribute any preference
    capture_feedback(
        output_kind=OutputKind.CLASSIFICATION,
        output_ref="m7-1",
        verdict=FeedbackVerdict.REJECT,
        model_versions={"rule_engine": "ich_m7"},
        classification_result={"m7_class": 3},
        context={"engine": "m7"},
        store=store,
    )
    prefs = build_preference_dataset(store.all_events())
    assert len(prefs) == 1  # only the narrative edit
    # the preference features are TEXT-only
    for p in prefs:
        assert set(p.chosen_features) <= set(NARRATIVE_FEATURE_NAMES)


def test_reward_model_ranks_well_cited_higher() -> None:
    store = InMemoryFeedbackStore()
    for i in range(5):
        _narrative_feedback(store, f"n-{i}", f"Draft {i} no citation.", f"Draft {i} cited [S1] [S2].")
    run = train_narrative_reward_model(build_preference_dataset(store.all_events()), epochs=300)
    assert run.pairwise_accuracy >= 0.8 and run.feature_names == NARRATIVE_FEATURE_NAMES
    ranked = rank_narratives(["plain text, no citation.", "thorough, cited [S1] [S2] [S3]."], run.model)
    assert ranked[0].text.startswith("thorough")  # the cited draft ranks first


def test_reward_model_refuses_numeric_or_classification_features() -> None:
    store = InMemoryFeedbackStore()
    for i in range(3):
        _narrative_feedback(store, f"n-{i}", "no cite", f"cited [S1] number {i}.")
    run = train_narrative_reward_model(build_preference_dataset(store.all_events()), epochs=100)
    # the model scores TEXT only — a numeric/classification feature is rejected
    for bad in ({"m7_class": 3.0}, {"ai_limit_ng_per_day": 26.5}, {"category": 1.0}):
        with pytest.raises(RewardModelError):
            run.model.score(bad)
    # default features are exactly the text allowlist
    assert set(default_narrative_features("some text [S1].")) == set(NARRATIVE_FEATURE_NAMES)


def test_train_rejects_non_text_feature_names() -> None:
    store = InMemoryFeedbackStore()
    for i in range(3):
        _narrative_feedback(store, f"n-{i}", "no cite", f"cited [S1] {i}.")
    prefs = build_preference_dataset(store.all_events())
    with pytest.raises(RewardModelError):
        train_narrative_reward_model(prefs, feature_names=(*NARRATIVE_FEATURE_NAMES, "m7_class"))


def test_reward_module_never_imports_deterministic_engines() -> None:
    src = Path(nr.__file__).read_text()
    for engine in ("classify_m7", "classify_cpca", "calculate_q3ab", "q3d_elements",
                   "q3c_solvents", "calculate_cumulative_risk", "build_specification"):
        assert engine not in src, f"narrative_reward must not reference {engine}"


# --------------------------------------------------------------------------- #
# Acceptance 3: A/B champion/challenger — gated, no auto-deploy, instant rollback
# --------------------------------------------------------------------------- #
def _arm(arm, model_id, *, acc, edit, cite, calc=0.0, accept_rate=0.9) -> ArmStats:
    return ArmStats(
        arm,
        model_id,
        RegulatoryMetricVector(
            narrative_acceptance_rate=acc,
            mean_edit_distance=edit,
            citation_correctness=cite,
            calculation_error_rate=calc,
        ),
        reviewer_acceptance_rate=accept_rate,
    )


_CHAMP = _arm(Arm.CHAMPION, "champ", acc=0.85, edit=0.15, cite=0.99, accept_rate=0.85)
_BETTER = _arm(Arm.CHALLENGER, "chal", acc=0.92, edit=0.10, cite=0.99, accept_rate=0.92)


def test_promotion_all_gates_pass() -> None:
    d = evaluate_promotion(_CHAMP, _BETTER, deploy_allowed=True)
    assert d.promote and d.calc_ok and d.narrative_dominates and d.acceptance_ok and d.gate_ok
    assert d.requires_sign_off is True


def test_promotion_blocked_on_calc_error_regression() -> None:
    bad_calc = _arm(Arm.CHALLENGER, "chal", acc=0.92, edit=0.10, cite=0.99, calc=0.01)
    d = evaluate_promotion(_CHAMP, bad_calc, deploy_allowed=True)
    assert d.promote is False and d.calc_ok is False


def test_promotion_blocked_on_citation_regression() -> None:
    cite_down = _arm(Arm.CHALLENGER, "chal", acc=0.99, edit=0.01, cite=0.95)  # citation regressed
    d = evaluate_promotion(_CHAMP, cite_down, deploy_allowed=True)
    assert d.promote is False and d.narrative_dominates is False


def test_promotion_blocked_when_gate_not_green() -> None:
    d = evaluate_promotion(_CHAMP, _BETTER, deploy_allowed=False)  # Prompt 18 gate red
    assert d.promote is False and d.gate_ok is False


def test_promotion_blocked_on_acceptance_regression() -> None:
    worse_accept = _arm(Arm.CHALLENGER, "chal", acc=0.92, edit=0.10, cite=0.99, accept_rate=0.70)
    d = evaluate_promotion(_CHAMP, worse_accept, deploy_allowed=True)
    assert d.promote is False and d.acceptance_ok is False


def test_no_auto_deploy_requires_human_sign_off() -> None:
    ab = ABTest(champion_model_id="champ")
    ab.start(challenger_model_id="chal", mode=RoutingMode.SHADOW)
    decision = ab.evaluate(_CHAMP, _BETTER, deploy_allowed=True)
    with pytest.raises(PromotionBlocked, match="sign-off"):
        ab.promote(decision, signed_off_by="")  # never auto-deploy
    promotion = ab.promote(decision, signed_off_by="QA-Jane")
    assert promotion.new_champion_model_id == "chal" and ab.champion_model_id == "chal"


def test_blocked_decision_cannot_be_promoted() -> None:
    ab = ABTest(champion_model_id="champ")
    ab.start(challenger_model_id="chal")
    decision = ab.evaluate(_CHAMP, _BETTER, deploy_allowed=False)  # gate red -> not promotable
    with pytest.raises(PromotionBlocked):
        ab.promote(decision, signed_off_by="QA-Jane")


def test_shadow_serves_champion_and_rollback_is_instant() -> None:
    ab = ABTest(champion_model_id="champ")
    router = ab.start(challenger_model_id="chal", mode=RoutingMode.SHADOW)
    # SHADOW: the user is always served the champion; the challenger is computed in the background
    assignment = router.assign("user-123")
    assert assignment.arm is Arm.CHAMPION and assignment.served_model_id == "champ"
    assert assignment.shadow_model_id == "chal"
    # CANARY with full traffic would serve the challenger...
    canary = ab.start(challenger_model_id="chal", mode=RoutingMode.CANARY, traffic_fraction=1.0)
    assert canary.assign("user-123").arm is Arm.CHALLENGER
    # ...until an instant rollback flips 100% back to the champion (lossless)
    ab.rollback(reason="elevated override rate")
    assert canary.rolled_back is True
    rolled = canary.assign("user-123")
    assert rolled.arm is Arm.CHAMPION and rolled.served_model_id == "champ"
