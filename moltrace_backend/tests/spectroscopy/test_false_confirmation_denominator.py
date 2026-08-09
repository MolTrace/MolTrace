"""A safety metric with an empty denominator must not read as a perfect score.

`false_confirmation_rate` is in `SAFETY_CRITICAL` with a zero tolerance: it may never
regress. It is computed as `false_confirms / wrong_total` over the gold records whose
proposed structure is *wrong*. A gold set containing no wrong structures therefore has
no denominator — and returning 0.0 there hands the best possible value on a metric that
may never regress to a model that was never shown a wrong answer. `false_confirmation.py`
already states the rule this file enforces: "None, never 0.0, when nothing was scored.
Zero evidence is not a perfect score."

The trap, and why the obvious fix is worse than the bug
------------------------------------------------------
Simply widening the field to `float | None` makes it *invisible* rather than merely
wrong. `metric_items()` omits a `None`, and `dominates` skipped any metric absent from
either side, so a candidate with a 0.9 false-confirmation rate promoted over an incumbent
that had not measured it — passing, with the metric not even appearing in the deltas. A
vacuous pass at least left a 0.0 in the record.

So absence is fail-closed for safety-critical metrics specifically, in all three
directions (candidate missing, incumbent missing, both missing). Non-safety metrics keep
skipping — that is the deliberate rollout accommodation `conformal_coverage_deficit`
ships with, and this file pins it so the two rules do not get merged later.

This closes the harness half of the rule `nmrcheck.ai_engine_adapter.dominance_verdict`
already applies to the *asymmetric* case. The two gates still diverge when **neither** side
reports the metric: the adapter's check is `_is_number(candidate) != _is_number(incumbent)`,
which is False when both are absent, so it returns passed=True there while this gate refuses.
Closing that is a change to the adapter and is deliberately not made here.
"""

from __future__ import annotations

import pytest

from moltrace.spectroscopy.eval.harness import (
    SAFETY_CRITICAL,
    CallableBundle,
    GoldMetricVector,
    GoldRecord,
    GoldSet,
    Prediction,
    dominates,
    evaluate,
)

_SHIFTS = {"13C": [10.0, 20.0, 30.0, 40.0]}


def _gold(*, wrong: int = 0, n: int = 8) -> GoldSet:
    """A gold set whose first ``wrong`` records carry a structure that is *wrong*."""

    return GoldSet(
        name="fc-denominator-fixture",
        records=tuple(
            GoldRecord(
                identifier=f"r{i}",
                source="in_house",
                true_inchikey=f"KEY{i}",
                reference_shifts=_SHIFTS,
                reviewer_verdict=i >= wrong,
                proposed_inchikey=(f"WRONG{i}" if i < wrong else f"KEY{i}"),
            )
            for i in range(n)
        ),
    )


def _bundle(*, confirmed: bool = True):
    def predict(rec: GoldRecord) -> Prediction:
        return Prediction(
            ranked_candidates=(rec.true_inchikey,),
            predicted_shifts=dict(_SHIFTS),
            confidence=0.9,
            confirmed=confirmed,
            retrieved=(rec.true_inchikey,),
        )

    return CallableBundle(predict_fn=predict, model_versions={"m": "sha"})


def _vector(**overrides) -> GoldMetricVector:
    base = dict(
        top1_accuracy=0.9,
        top3_accuracy=0.95,
        shift_mae_1h=0.10,
        shift_mae_13c=1.0,
        ece=0.05,
        false_confirmation_rate=0.10,
        recall_at_k=0.9,
        uncertainty_auroc=0.8,
        robustness=0.9,
        reviewer_agreement_rate=0.9,
        latency_p50_ms=10.0,
        latency_p95_ms=20.0,
    )
    base.update(overrides)
    return GoldMetricVector(**base)


def _delta_for(deltas, metric: str):
    return next((d for d in deltas if d.metric == metric), None)


# --------------------------------------------------------------------------- #
# The metric itself — zero evidence is not a perfect score
# --------------------------------------------------------------------------- #
def test_a_gold_set_with_no_wrong_structures_reports_no_rate_rather_than_a_perfect_one() -> None:
    vector = evaluate(_bundle(), _gold(wrong=0))

    assert vector.false_confirmation_rate is None
    assert "false_confirmation_rate" not in vector.metric_items()
    assert "false_confirmation_rate" not in vector.as_dict()


def test_the_denominator_is_reported_so_an_unmeasured_rate_is_visible() -> None:
    """A rate whose coverage is not emitted cannot be told apart from a measured one."""

    assert evaluate(_bundle(), _gold(wrong=0)).n_wrong_structures == 0
    assert evaluate(_bundle(), _gold(wrong=3)).n_wrong_structures == 3


def test_a_measured_rate_is_still_a_float() -> None:
    vector = evaluate(_bundle(confirmed=True), _gold(wrong=2))

    assert vector.false_confirmation_rate == 1.0  # both wrong structures confirmed
    assert vector.metric_items()["false_confirmation_rate"] == 1.0


# --------------------------------------------------------------------------- #
# Absence is fail-closed — all three directions
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("candidate_rate", "incumbent_rate", "case"),
    [
        (None, 0.10, "candidate stopped measuring it"),
        (0.05, None, "incumbent never measured it"),
        (None, None, "neither measured it"),
    ],
)
def test_an_unmeasured_safety_metric_refuses_promotion(
    candidate_rate: float | None, incumbent_rate: float | None, case: str
) -> None:
    passed, deltas = dominates(
        _vector(false_confirmation_rate=candidate_rate, top1_accuracy=0.99),
        _vector(false_confirmation_rate=incumbent_rate),
    )

    assert passed is False, case
    delta = _delta_for(deltas, "false_confirmation_rate")
    assert delta is not None, "the refusal must name its cause, not drop the metric"
    assert delta.measured is False
    assert delta.regressed is True
    assert delta.safety_critical is True
    assert delta.delta is None and delta.improvement is None


def test_dropping_the_metric_is_not_a_way_to_stop_being_measured_on_it() -> None:
    """The case the fail-closed rule exists for: a bad candidate hiding its rate."""

    passed, _ = dominates(
        _vector(false_confirmation_rate=None, top1_accuracy=0.999),
        _vector(false_confirmation_rate=0.01),
    )

    assert passed is False


# --------------------------------------------------------------------------- #
# The non-safety accommodation must survive — these two rules are not the same rule
# --------------------------------------------------------------------------- #
def test_an_unmeasured_non_safety_metric_still_skips() -> None:
    passed, deltas = dominates(
        _vector(top1_accuracy=0.99, conformal_coverage_deficit=None),
        _vector(conformal_coverage_deficit=0.02),
    )

    assert passed is True
    assert _delta_for(deltas, "conformal_coverage_deficit") is None


def test_conformal_coverage_is_still_not_safety_critical() -> None:
    assert "conformal_coverage_deficit" not in SAFETY_CRITICAL
    assert "false_confirmation_rate" in SAFETY_CRITICAL


# --------------------------------------------------------------------------- #
# Pre-existing dominance behaviour is unchanged
# --------------------------------------------------------------------------- #
def test_a_measured_improvement_still_promotes() -> None:
    passed, deltas = dominates(_vector(top1_accuracy=0.99), _vector())

    assert passed is True
    assert _delta_for(deltas, "false_confirmation_rate").measured is True


def test_a_safety_regression_still_blocks() -> None:
    passed, _ = dominates(
        _vector(false_confirmation_rate=0.20, top1_accuracy=0.99), _vector()
    )

    assert passed is False


def test_an_identical_candidate_does_not_promote() -> None:
    assert dominates(_vector(), _vector())[0] is False


# --------------------------------------------------------------------------- #
# The other side of nullability — a real snapshot must stay readable
# --------------------------------------------------------------------------- #
def test_a_real_snapshot_rebuilds_into_a_usable_incumbent() -> None:
    """Nullable metrics must not make a stored incumbent unreadable.

    ``_vector_from_snapshot`` required every ``METRIC_DIRECTIONS`` key, but
    ``metric_items()`` omits whatever was not measured — so once nullable metrics joined
    that mapping, no real snapshot carried all of them. It returned ``None`` for every
    incumbent, and its caller reads ``None`` as "no incumbent, nothing to beat" and
    promotes without comparing anything. A fail-OPEN in the promotion gate, and one that
    widens with each nullable metric added.
    """

    from moltrace.spectroscopy.ai.finetune import _vector_from_snapshot

    measured = evaluate(_bundle(), _gold(wrong=2))  # no intervals => conformal is None
    assert "conformal_coverage_deficit" not in measured.metric_items()

    rebuilt = _vector_from_snapshot(measured.metric_items())

    assert rebuilt is not None, "a real incumbent snapshot must not read as 'no incumbent'"
    assert rebuilt.false_confirmation_rate == measured.false_confirmation_rate
    assert rebuilt.conformal_coverage_deficit is None


def test_a_snapshot_missing_an_always_measured_metric_is_still_rejected() -> None:
    from moltrace.spectroscopy.ai.finetune import _vector_from_snapshot

    assert _vector_from_snapshot({"ece": 0.1}) is None


# --------------------------------------------------------------------------- #
# The refusal must name the right cause — blocking is not enough
# --------------------------------------------------------------------------- #
def test_an_unmeasured_metric_is_not_reported_as_a_regression() -> None:
    """Both block, but they need different remedies.

    "Regressed" sends the operator to the model; "not measured" sends them to the gold
    set. `regressed` is set on an unmeasured delta so every existing consumer blocks
    without an edit — which means every consumer that *renders a reason* has to read
    `measured` too, or it asserts a regression that never happened.
    """

    from moltrace.spectroscopy.feedback.ab_testing import Arm, ArmStats, evaluate_promotion
    from moltrace.spectroscopy.ops.monitoring import check_dominance

    unmeasured = _vector(false_confirmation_rate=None, top1_accuracy=0.99)
    incumbent = _vector(false_confirmation_rate=None)

    check = check_dominance(candidate_metrics=unmeasured, incumbent_metrics=incumbent)
    assert check.passed is False
    assert "not measured" in check.detail
    assert "regressed / no strict gain" not in check.detail

    def _arm(arm, metrics):
        return ArmStats(
            arm=arm,
            model_id="m",
            metrics=metrics,
            n_feedback=10,
            reviewer_acceptance_rate=0.9,
            override_rate=0.1,
        )

    decision = evaluate_promotion(
        _arm(Arm.CHAMPION, incumbent),
        _arm(Arm.CHALLENGER, unmeasured),
        require_gate=False,
    )
    assert decision.safety_ok is False
    assert any("was not measured" in r for r in decision.reasons)
    assert not any("safety-critical regression" in r for r in decision.reasons)
    delta = next(d for d in decision.as_dict()["deltas"] if d["metric"] == "false_confirmation_rate")
    assert delta["measured"] is False


def test_a_real_regression_is_still_reported_as_one() -> None:
    from moltrace.spectroscopy.ops.monitoring import check_dominance

    check = check_dominance(
        candidate_metrics=_vector(false_confirmation_rate=0.20, top1_accuracy=0.99),
        incumbent_metrics=_vector(),
    )

    assert check.passed is False
    assert "regressed" in check.detail
    assert "not measured" not in check.detail
