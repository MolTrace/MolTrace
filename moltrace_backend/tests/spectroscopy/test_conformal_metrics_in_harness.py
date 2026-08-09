"""Conformal coverage as a promotion metric, and the two traps in adding one.

The harness gates every model promotion. Adding a metric to it is therefore a change
to what can ship, and two failure modes have to be closed in the same commit:

1. **An unmeasured metric must not read as a perfect one.** If
   `conformal_coverage_deficit` defaulted to 0.0, a model that issues no intervals at
   all would compare as perfectly calibrated against one that measured itself. It is
   `None` instead, and `metric_items()` omits it so `dominates` skips it.
2. **A new safety-critical metric would refuse every promotion during rollout.** The
   deployment gate refuses when one evaluation reports a safety-critical metric and
   the other does not — the anti-asymmetry rule. A third such metric would therefore
   block everything until incumbents report it too. So coverage ships with a *zero
   tolerance* (same strictness) but stays out of `SAFETY_CRITICAL` until it is
   reported across the board.
"""

from __future__ import annotations

import math

import pytest

from moltrace.spectroscopy.eval.harness import (
    DEFAULT_TOLERANCES,
    METRIC_DIRECTIONS,
    SAFETY_CRITICAL,
    CallableBundle,
    GoldMetricVector,
    GoldRecord,
    GoldSet,
    MetricDirection,
    Prediction,
    dominates,
    evaluate,
)

_SHIFTS = {"13C": [10.0, 20.0, 30.0, 40.0]}


def _gold(n: int = 8) -> GoldSet:
    """Record 0 carries a *wrong* structure, so ``false_confirmation_rate`` is measurable.

    Without one, that metric has an empty denominator and is reported as ``None`` — which
    is correct (see ``test_false_confirmation_denominator.py``) but would make this
    fixture unable to exercise ``test_no_finite_metric_is_silently_dropped``, whose whole
    point is a *fully measured* vector.
    """

    return GoldSet(
        name="conformal-fixture",
        records=tuple(
            GoldRecord(
                identifier=f"r{i}",
                source="in_house",
                true_inchikey=f"KEY{i}",
                reference_shifts=_SHIFTS,
                reviewer_verdict=i != 0,
                proposed_inchikey=("KWRONG" if i == 0 else f"KEY{i}"),
            )
            for i in range(n)
        ),
    )


def _bundle(offsets: list[float], half_widths: list[float] | None):
    """A model whose ¹³C predictions miss by ``offsets`` and claim ``half_widths``."""

    def predict(rec: GoldRecord) -> Prediction:
        return Prediction(
            ranked_candidates=(rec.true_inchikey,),
            predicted_shifts={"13C": [s + o for s, o in zip(_SHIFTS["13C"], offsets, strict=True)]},
            confidence=0.9,
            confirmed=True,
            retrieved=(rec.true_inchikey,),
            intervals={"13C": list(half_widths)} if half_widths is not None else None,
        )

    return CallableBundle(predict_fn=predict, model_versions={"m": "sha"})


# --------------------------------------------------------------------------- #
# Trap 1 — unmeasured must not read as perfect
# --------------------------------------------------------------------------- #
def test_a_model_with_no_intervals_reports_no_coverage_rather_than_a_perfect_one() -> None:
    vector = evaluate(_bundle([0.1] * 4, None), _gold())
    assert vector.conformal_coverage_deficit is None
    assert vector.conformal_interval_width is None
    assert "conformal_coverage_deficit" not in vector.metric_items()
    assert "conformal_coverage_deficit" not in vector.as_dict()


def test_an_unmeasured_metric_is_skipped_rather_than_compared_as_zero() -> None:
    """The defect this guards: 0.0 deficit is the *best possible* score."""

    measured = evaluate(_bundle([0.1] * 4, [1.0] * 4), _gold())
    unmeasured = evaluate(_bundle([0.1] * 4, None), _gold())
    assert measured.conformal_coverage_deficit == pytest.approx(0.0)

    # Neither direction may treat the unmeasured model as having scored.
    for cand, inc in ((measured, unmeasured), (unmeasured, measured)):
        _passed, deltas = dominates(cand, inc)
        assert "conformal_coverage_deficit" not in {d.metric for d in deltas}


def test_a_non_finite_metric_is_dropped_not_compared() -> None:
    vector = GoldMetricVector(
        top1_accuracy=1.0, top3_accuracy=1.0, shift_mae_1h=0.1, shift_mae_13c=1.0,
        ece=0.01, false_confirmation_rate=0.0, recall_at_k=1.0, uncertainty_auroc=0.9,
        robustness=1.0, reviewer_agreement_rate=1.0, latency_p50_ms=1.0, latency_p95_ms=2.0,
        conformal_coverage_deficit=float("nan"), conformal_interval_width=float("inf"),
    )
    items = vector.metric_items()
    assert "conformal_coverage_deficit" not in items
    assert "conformal_interval_width" not in items


# --------------------------------------------------------------------------- #
# Trap 2 — the rollout hazard
# --------------------------------------------------------------------------- #
def test_coverage_is_not_safety_critical_yet_but_carries_a_zero_tolerance() -> None:
    """Same strictness, without blocking every promotion during rollout."""

    assert "conformal_coverage_deficit" not in SAFETY_CRITICAL
    assert SAFETY_CRITICAL == frozenset({"false_confirmation_rate", "ece"})
    assert DEFAULT_TOLERANCES["conformal_coverage_deficit"] == 0.0


def test_any_coverage_shortfall_blocks_promotion() -> None:
    base = dict(
        top1_accuracy=0.8, top3_accuracy=0.9, shift_mae_1h=0.1, shift_mae_13c=1.0,
        ece=0.02, false_confirmation_rate=0.01, recall_at_k=0.9, uncertainty_auroc=0.8,
        robustness=0.9, reviewer_agreement_rate=0.9, latency_p50_ms=10.0, latency_p95_ms=20.0,
    )
    incumbent = GoldMetricVector(**base, conformal_coverage_deficit=0.0)
    candidate = GoldMetricVector(
        **{**base, "top1_accuracy": 0.99}, conformal_coverage_deficit=0.001
    )
    passed, deltas = dominates(candidate, incumbent)
    assert not passed
    regressed = {d.metric for d in deltas if d.regressed}
    assert "conformal_coverage_deficit" in regressed


# --------------------------------------------------------------------------- #
# The metrics themselves
# --------------------------------------------------------------------------- #
def test_both_metrics_are_lower_better() -> None:
    """Deficit and width both improve downward — coverage is expressed as a shortfall
    precisely so that 'more is better' never applies to it."""

    assert METRIC_DIRECTIONS["conformal_coverage_deficit"] is MetricDirection.LOWER_BETTER
    assert METRIC_DIRECTIONS["conformal_interval_width"] is MetricDirection.LOWER_BETTER


def test_coverage_deficit_is_measured_against_the_target() -> None:
    # Half the shifts are outside their interval -> 50 % coverage, 40 pp short of 0.90.
    vector = evaluate(_bundle([0.1, 0.1, 5.0, 5.0], [1.0] * 4), _gold(), conformal_target=0.90)
    assert vector.conformal_coverage_deficit == pytest.approx(0.40)
    assert vector.conformal_interval_width == pytest.approx(1.0)


def test_over_coverage_is_not_a_deficit() -> None:
    """Exceeding the target is not a shortfall; the width metric is what prices it."""

    vector = evaluate(_bundle([0.1] * 4, [50.0] * 4), _gold(), conformal_target=0.90)
    assert vector.conformal_coverage_deficit == pytest.approx(0.0)
    assert vector.conformal_interval_width == pytest.approx(50.0)


def test_an_abstained_interval_is_excluded_not_scored_as_a_miss() -> None:
    """A calibration that declined to bound an atom has not answered wrongly."""

    vector = evaluate(
        _bundle([0.1, 0.1, 99.0, 99.0], [1.0, 1.0, float("nan"), float("nan")]),
        _gold(),
        conformal_target=0.90,
    )
    assert vector.conformal_coverage_deficit == pytest.approx(0.0)
    assert vector.conformal_interval_width == pytest.approx(1.0)


def test_the_width_tolerance_is_three_percent_of_the_measured_mean() -> None:
    """0.16 ppm = 3 % of 5.371 ppm, the count-weighted mean half-width measured on
    held-out NMRShiftDB2 (6.952 over 36,844 ¹³C, 0.714 over 12,508 ¹H). Three per cent
    is the same fraction of scale `shift_mae_13c`'s 0.10 represents of its 3.44 ppm MAE."""

    pooled = (36844 * 6.952 + 12508 * 0.714) / (36844 + 12508)
    assert pooled == pytest.approx(5.371, abs=0.002)
    assert DEFAULT_TOLERANCES["conformal_interval_width"] == pytest.approx(
        0.03 * pooled, abs=0.01
    )


def test_a_sharper_interval_at_equal_coverage_is_an_improvement() -> None:
    """The only honest definition of sharper."""

    base = dict(
        top1_accuracy=0.8, top3_accuracy=0.9, shift_mae_1h=0.1, shift_mae_13c=1.0,
        ece=0.02, false_confirmation_rate=0.01, recall_at_k=0.9, uncertainty_auroc=0.8,
        robustness=0.9, reviewer_agreement_rate=0.9, latency_p50_ms=10.0, latency_p95_ms=20.0,
        conformal_coverage_deficit=0.0,
    )
    incumbent = GoldMetricVector(**base, conformal_interval_width=6.0)
    candidate = GoldMetricVector(**base, conformal_interval_width=4.0)
    passed, _deltas = dominates(candidate, incumbent)
    assert passed


def test_no_finite_metric_is_silently_dropped() -> None:
    """Every direction key must survive metric_items on a fully measured vector."""

    vector = evaluate(_bundle([0.1] * 4, [1.0] * 4), _gold())
    items = vector.metric_items()
    assert set(items) == set(METRIC_DIRECTIONS)
    assert all(math.isfinite(v) for v in items.values())
