"""Unit tests for the Repho R9 feedback → preference → A/B engine (pure: no DB/HTTP/clock)."""

from __future__ import annotations

import pytest

from nmrcheck.reaction_feedback import (
    FEEDBACK_DECISIONS,
    REJECTION_REASONS,
    ModelMetrics,
    dominates,
    evaluate_ab_promotion,
    fit_preference_model,
    predict_acceptance,
    rank_by_acceptance,
    record_feedback,
)


# --- 1. feedback capture + safety routing ----------------------------------------------------
def test_taxonomy_constants():
    assert FEEDBACK_DECISIONS == ("accept", "edit", "reject")
    assert "unsafe" in REJECTION_REASONS


def test_accept_is_preference_learnable_not_safety():
    r = record_feedback(decision="accept", proposal_ref="p1", features={"solvent": "MeCN"})
    assert r.is_safety_signal is False
    assert r.routes_to_safety_hardening is False
    assert r.is_preference_learnable is True


def test_unsafe_reject_is_safety_signal_not_learnable():
    r = record_feedback(decision="reject", reason="unsafe", proposal_ref="p2")
    assert r.is_safety_signal is True
    assert r.routes_to_safety_hardening is True
    assert r.is_preference_learnable is False  # never auto-learned-around


def test_non_safety_reject_is_learnable():
    r = record_feedback(decision="reject", reason="cost", proposal_ref="p3")
    assert r.is_safety_signal is False
    assert r.is_preference_learnable is True


def test_reject_requires_valid_reason():
    with pytest.raises(ValueError):
        record_feedback(decision="reject", proposal_ref="p4")  # no reason
    with pytest.raises(ValueError):
        record_feedback(decision="reject", reason="bogus", proposal_ref="p4")


def test_invalid_decision_raises():
    with pytest.raises(ValueError):
        record_feedback(decision="maybe", proposal_ref="p5")


# --- 2. preference re-ranker -----------------------------------------------------------------
def _fb(decision: str, solvent: str, reason: str | None = None):
    return record_feedback(
        decision=decision, reason=reason, proposal_ref=f"{decision}-{solvent}",
        features={"solvent": solvent},
    )


def test_preference_model_learns_accept_rate_per_feature():
    records = [
        _fb("accept", "MeCN"),
        _fb("accept", "MeCN"),
        _fb("reject", "THF", reason="cost"),
        _fb("reject", "THF", reason="cost"),
    ]
    model = fit_preference_model(records)
    assert model.trained_n == 4
    # MeCN (all accepts) should score higher than THF (all rejects).
    assert predict_acceptance(model, {"solvent": "MeCN"}) > predict_acceptance(
        model, {"solvent": "THF"}
    )


def test_preference_model_excludes_safety_signals_from_training():
    records = [
        _fb("accept", "MeCN"),
        record_feedback(decision="reject", reason="unsafe", proposal_ref="x",
                        features={"solvent": "MeCN"}),
    ]
    model = fit_preference_model(records)
    assert model.trained_n == 1  # only the accept
    assert model.excluded_safety_signals == 1


def test_predict_falls_back_to_global_for_unseen_feature():
    model = fit_preference_model([_fb("accept", "MeCN")])
    # An unseen solvent value -> no per-feature evidence -> global rate.
    assert predict_acceptance(model, {"solvent": "DMSO"}) == model.global_rate


def test_rank_by_acceptance_reorders_and_preserves_original_rank():
    model = fit_preference_model([_fb("accept", "MeCN"), _fb("reject", "THF", reason="cost")])
    candidates = [
        {"proposal_ref": "c1", "rank": 1, "features": {"solvent": "THF"}},
        {"proposal_ref": "c2", "rank": 2, "features": {"solvent": "MeCN"}},
    ]
    ranked = rank_by_acceptance(model, candidates)
    assert [r.proposal_ref for r in ranked] == ["c2", "c1"]  # MeCN preferred
    assert ranked[0].original_rank == 2  # optimiser's own rank preserved, not overwritten


# --- 3. A/B promotion gate -------------------------------------------------------------------
def _mm(version: str, *, yield_percent: float, e_factor: float, recall: float) -> ModelMetrics:
    return ModelMetrics(
        model_version=version,
        metrics={"yield_percent": yield_percent, "e_factor": e_factor},
        safety_flag_recall=recall,
    )


def test_dominance_higher_and_lower_directions():
    # challenger: higher yield, lower e_factor -> dominates
    dom, excluded = dominates({"yield_percent": 80, "e_factor": 10}, {"yield_percent": 70, "e_factor": 12})
    assert dom is True and excluded == []


def test_dominance_requires_no_worse_on_all():
    # higher yield but WORSE (higher) e_factor -> not dominant
    dom, _ = dominates({"yield_percent": 80, "e_factor": 15}, {"yield_percent": 70, "e_factor": 12})
    assert dom is False


def test_promotion_blocked_on_safety_regression_even_if_dominant():
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    challenger = _mm("v2", yield_percent=85, e_factor=9, recall=0.90)  # better metrics, worse recall
    verdict = evaluate_ab_promotion(champion, challenger)
    assert verdict.dominates is True
    assert verdict.safety_regression is True
    assert verdict.promotable is False
    assert verdict.requires_human_signoff is True
    assert verdict.rollback_available is True


def test_promotion_blocked_when_not_dominant():
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    challenger = _mm("v2", yield_percent=72, e_factor=14, recall=0.95)  # mixed, no recall regression
    verdict = evaluate_ab_promotion(champion, challenger)
    assert verdict.safety_regression is False
    assert verdict.dominates is False
    assert verdict.promotable is False


def test_promotion_eligible_with_dominance_and_no_regression_still_needs_signoff():
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    challenger = _mm("v2", yield_percent=82, e_factor=10, recall=0.97)
    verdict = evaluate_ab_promotion(champion, challenger)
    assert verdict.promotable is True
    assert verdict.safety_regression is False
    assert verdict.dominates is True
    assert verdict.requires_human_signoff is True  # never auto-deploy
    assert verdict.rollback_available is True


def test_unknown_metric_direction_is_excluded_and_reported():
    champion = ModelMetrics("v1", {"yield_percent": 70, "mystery": 1.0}, 0.95)
    challenger = ModelMetrics("v2", {"yield_percent": 80, "mystery": 2.0}, 0.95)
    verdict = evaluate_ab_promotion(champion, challenger)
    assert "mystery" in verdict.excluded_metrics
    # Still dominant on the known metric (yield up), so promotable with the unknown excluded.
    assert verdict.dominates is True


# --- A/B gate fail-safe hardening (adversarial-review regressions) ----------------------------
def test_omitting_a_champion_metric_is_not_dominance():
    # Challenger drops e_factor (a regression could hide there) — must NOT be dominant/promotable.
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    challenger = ModelMetrics("v2", {"yield_percent": 80}, 0.95)  # no e_factor
    verdict = evaluate_ab_promotion(champion, challenger)
    assert verdict.dominates is False
    assert verdict.promotable is False
    assert "e_factor" in verdict.excluded_metrics


def test_non_finite_metric_refuses_dominance():
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    challenger = _mm("v2", yield_percent=80, e_factor=float("nan"), recall=0.95)
    verdict = evaluate_ab_promotion(champion, challenger)
    assert verdict.dominates is False
    assert verdict.promotable is False


def test_non_finite_safety_recall_fails_closed():
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    challenger = _mm("v2", yield_percent=85, e_factor=9, recall=float("nan"))  # great metrics, NaN recall
    verdict = evaluate_ab_promotion(champion, challenger)
    assert verdict.safety_regression is True  # fail closed
    assert verdict.promotable is False


def test_out_of_range_safety_recall_fails_closed():
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    challenger = _mm("v2", yield_percent=85, e_factor=9, recall=5.0)  # impossible recall
    verdict = evaluate_ab_promotion(champion, challenger)
    assert verdict.safety_regression is True
    assert verdict.promotable is False


def test_metric_tolerance_does_not_widen_the_safety_gate():
    # A tiny recall regression must still block even with a large METRIC tolerance.
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    challenger = _mm("v2", yield_percent=90, e_factor=5, recall=0.94)  # recall down 0.01
    verdict = evaluate_ab_promotion(champion, challenger, tolerance=0.1)
    assert verdict.safety_regression is True  # exact safety check, tolerance not applied
    assert verdict.promotable is False


# --- the reason prose names the measure that was actually gated ------------------------------
# `reasons` reach a reviewer's screen verbatim (the frontend is under contract not to summarise
# them), so which measure they name is part of the gate's output, not incidental wording.
def test_repho_reasons_still_name_safety_flag_recall_by_default():
    # The label is a parameter now; for the two Repho call sites, which pass nothing, the text
    # must be unchanged. This is what keeps it a parameterisation and not a silent rename.
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    blocked = evaluate_ab_promotion(champion, _mm("v2", yield_percent=85, e_factor=9, recall=0.90))
    assert blocked.reasons[0] == (
        "Safety-flag recall regressed (0.9 < 0.95); blocked."
    )

    failed_closed = evaluate_ab_promotion(
        champion, _mm("v2", yield_percent=85, e_factor=9, recall=float("nan"))
    )
    assert failed_closed.reasons[0] == (
        "Safety-flag recall is missing or out of range [0, 1]; failing closed."
    )

    eligible = evaluate_ab_promotion(champion, _mm("v2", yield_percent=82, e_factor=10, recall=0.97))
    assert eligible.promotable is True
    assert eligible.reasons[0] == (
        "Eligible: Safety-flag recall did not regress and the metric vector dominates — "
        "human sign-off required."
    )


def test_a_caller_with_a_different_blocking_measure_gets_its_name_in_the_reasons():
    # The corpus conveyor reuses this gate with a blocking measure of its own. Naming the
    # reaction model's measure in its refusal would tell the reader to go look at a number
    # that is not on the screen.
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    challenger = _mm("v2", yield_percent=85, e_factor=9, recall=0.90)
    verdict = evaluate_ab_promotion(
        champion, challenger, blocking_metric_label="Citation support recall"
    )
    assert verdict.reasons[0] == "Citation support recall regressed (0.9 < 0.95); blocked."
    assert not any("Safety-flag recall" in reason for reason in verdict.reasons)


def test_the_label_never_changes_the_decision():
    # Only the noun changes: same inputs, same verdict, whatever the measure is called.
    champion = _mm("v1", yield_percent=70, e_factor=12, recall=0.95)
    challenger = _mm("v2", yield_percent=85, e_factor=9, recall=0.90)
    default = evaluate_ab_promotion(champion, challenger)
    labelled = evaluate_ab_promotion(champion, challenger, blocking_metric_label="F1 on citations")
    assert (default.promotable, default.safety_regression, default.dominates) == (
        labelled.promotable,
        labelled.safety_regression,
        labelled.dominates,
    )


def test_unsafe_tag_on_non_reject_routes_to_safety_and_is_excluded():
    # A contradictory accept/edit + "unsafe" must still route to R6 and stay out of preference.
    for decision in ("accept", "edit"):
        r = record_feedback(decision=decision, reason="unsafe", proposal_ref="p")
        assert r.is_safety_signal is True
        assert r.routes_to_safety_hardening is True
        assert r.is_preference_learnable is False
