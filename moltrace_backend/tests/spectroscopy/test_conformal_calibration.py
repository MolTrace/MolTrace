"""L1/D1 — distribution-free prediction intervals over the shift predictor.

The defect under test, measured in B5: the predictor's reported ¹³C σ is optimistic
by ~3× in its tightest bin (σ ≤ 0.5 ppm carries a mean error of 0.76 ppm) and
conservative in the wide ones. That is the worst possible shape, because a tight σ
is exactly what the verifier's significance mapping weights highest.

These tests assert the property that makes conformal worth using — coverage holds
*even when σ is wrong* — and that a Mondrian fit repairs the tight bin specifically
rather than widening everything.
"""

from __future__ import annotations

import json
import math
import random

import pytest

from moltrace.spectroscopy.eval.conformal import (
    CALIBRATION_VERSION,
    ConformalCalibration,
    fit_conformal,
    measure_coverage,
    min_calibration_size,
)


def _miscalibrated(n: int, seed: int) -> list[tuple[float, float]]:
    """(reported σ, |error|) with the *measured* miscalibration shape.

    Tight-σ atoms err ~3× their claim; wide-σ atoms err well inside theirs. This is
    the B5 calibration table, not an invented pathology.
    """

    rng = random.Random(seed)
    pairs: list[tuple[float, float]] = []
    for _ in range(n):
        sigma = rng.choice([0.25, 0.75, 1.5, 3.4, 6.9, 13.6])
        inflation = 3.0 if sigma <= 0.5 else (1.7 if sigma <= 1.0 else 0.9)
        pairs.append((sigma, abs(rng.gauss(0.0, sigma * inflation))))
    return pairs


# --------------------------------------------------------------------------- #
# The guarantee
# --------------------------------------------------------------------------- #
def test_coverage_holds_on_a_disjoint_split_despite_a_wrong_sigma() -> None:
    """The whole reason for conformal: the guarantee does not depend on σ being right."""

    calibration = fit_conformal({"13C": _miscalibrated(4000, seed=1)}, target_coverage=0.90)
    report = measure_coverage(calibration, {"13C": _miscalibrated(4000, seed=2)})

    assert report.per_nucleus["13C"]["coverage"] >= 0.88, report.as_dict()
    assert report.worst_deficit <= 0.02, report.notes


@pytest.mark.parametrize("target", [0.80, 0.90, 0.95])
def test_a_higher_target_buys_coverage_with_width(target: float) -> None:
    calibration = fit_conformal({"13C": _miscalibrated(4000, seed=3)}, target_coverage=target)
    report = measure_coverage(calibration, {"13C": _miscalibrated(4000, seed=4)})
    stats = report.per_nucleus["13C"]
    assert stats["coverage"] >= target - 0.03, report.as_dict()
    assert stats["mean_half_width_ppm"] > 0.0


def test_the_conformal_quantile_uses_the_finite_sample_correction() -> None:
    """``ceil((n+1)·target)``-th residual, not the plain empirical quantile.

    Without the ``(n+1)`` the guarantee only holds asymptotically, which is not what
    a small per-nucleus calibration set has.
    """

    # 9 points is exactly the minimum for 90%: rank = ceil(10 * 0.9) = 9 = n, so the
    # interval is the largest residual. A plain 90th-percentile would take the 8th.
    assert min_calibration_size(0.90) == 9
    pairs = [(1.0, float(i)) for i in range(1, 10)]
    calibration = fit_conformal({"13C": pairs}, target_coverage=0.90, n_bins=1)
    assert calibration.pooled["13C"] == pytest.approx(9.0)


# --------------------------------------------------------------------------- #
# Mondrian binning — the actual repair
# --------------------------------------------------------------------------- #
def test_the_tight_sigma_band_gets_an_interval_wider_than_its_claim() -> None:
    """The measured defect, repaired where it lives.

    An atom claiming σ = 0.25 ppm truly errs ~3× that. Its band's half-width must
    exceed its mean reported σ, or the interval inherits the same overconfidence.
    """

    calibration = fit_conformal({"13C": _miscalibrated(6000, seed=5)}, target_coverage=0.90)
    tight = [b for b in calibration.bins if b.mean_sigma_ppm <= 0.5]
    assert tight, "the tightest σ band was not resolved"
    for band in tight:
        assert band.half_width_ppm > band.mean_sigma_ppm, (
            f"band [{band.sigma_lo}, {band.sigma_hi}] issues {band.half_width_ppm:.3f} ppm "
            f"for a mean claimed σ of {band.mean_sigma_ppm:.3f} — still overconfident"
        )


def test_binning_is_sharper_than_one_pooled_interval_at_equal_coverage() -> None:
    """Why Mondrian rather than pooled: a single quantile punishes the good atoms."""

    train = {"13C": _miscalibrated(6000, seed=6)}
    test = {"13C": _miscalibrated(6000, seed=7)}

    binned = measure_coverage(fit_conformal(train, target_coverage=0.90), test)
    pooled = measure_coverage(fit_conformal(train, target_coverage=0.90, n_bins=1), test)

    assert binned.per_nucleus["13C"]["coverage"] >= 0.88
    assert pooled.per_nucleus["13C"]["coverage"] >= 0.88
    assert (
        binned.per_nucleus["13C"]["mean_half_width_ppm"]
        < pooled.per_nucleus["13C"]["mean_half_width_ppm"]
    ), "binning bought no sharpness, so it is not earning its complexity"


def test_a_confident_atom_still_gets_a_narrower_interval_than_an_uncertain_one() -> None:
    """Repairing the tight band must not flatten the σ signal entirely."""

    calibration = fit_conformal({"13C": _miscalibrated(6000, seed=8)}, target_coverage=0.90)
    narrow = calibration.interval("13C", 0.25)
    wide = calibration.interval("13C", 13.6)
    assert narrow.available and wide.available
    assert narrow.half_width_ppm < wide.half_width_ppm


# --------------------------------------------------------------------------- #
# Refusals — stated, never silently widened
# --------------------------------------------------------------------------- #
def test_an_atom_with_no_usable_sigma_gets_no_interval() -> None:
    """An element-prior abstention has no claim to put a guarantee on."""

    calibration = fit_conformal({"13C": _miscalibrated(2000, seed=9)}, target_coverage=0.90)
    for sigma in (float("nan"), float("inf"), -1.0):
        interval = calibration.interval("13C", sigma)
        assert not interval.available
        assert "no usable predicted uncertainty" in interval.reason


def test_a_nucleus_below_the_minimum_yields_no_interval_and_says_why() -> None:
    calibration = fit_conformal({"13C": [(1.0, 0.5)] * 5}, target_coverage=0.90)
    assert calibration.interval("13C", 1.0).available is False
    assert any("below the 9 needed" in note for note in calibration.notes)


def test_an_unknown_nucleus_is_refused_by_name() -> None:
    calibration = fit_conformal({"13C": _miscalibrated(2000, seed=10)}, target_coverage=0.90)
    interval = calibration.interval("15N", 1.0)
    assert not interval.available
    assert "15N" in interval.reason


def test_a_thin_band_folds_into_the_nucleus_interval_rather_than_inventing_one() -> None:
    pairs = [(0.2, 0.1)] * 400 + [(50.0, 30.0)] * 3
    calibration = fit_conformal({"13C": pairs}, target_coverage=0.90)
    interval = calibration.interval("13C", 50.0)
    assert interval.available
    assert interval.basis == "nucleus_pooled"
    assert "nucleus-wide" in interval.reason


def test_no_interval_is_not_counted_as_a_coverage_miss() -> None:
    """An abstention is not a failed prediction; folding them together hides both."""

    calibration = fit_conformal({"13C": _miscalibrated(2000, seed=11)}, target_coverage=0.90)
    report = measure_coverage(
        calibration, {"13C": [(float("nan"), 99.0)] * 50 + _miscalibrated(500, seed=12)}
    )
    assert report.n_no_interval == 50
    assert report.per_nucleus["13C"]["n"] == 500
    assert report.per_nucleus["13C"]["coverage"] >= 0.85


def test_an_impossible_target_is_rejected() -> None:
    for target in (0.0, 1.0, 1.5, -0.1):
        with pytest.raises(ValueError, match="target_coverage"):
            min_calibration_size(target)


# --------------------------------------------------------------------------- #
# Reproducibility
# --------------------------------------------------------------------------- #
def test_a_calibration_is_content_addressed_and_reproducible() -> None:
    a = fit_conformal({"13C": _miscalibrated(2000, seed=13)}, target_coverage=0.90)
    b = fit_conformal({"13C": _miscalibrated(2000, seed=13)}, target_coverage=0.90)
    assert a.fingerprint() == b.fingerprint()
    assert a.version == CALIBRATION_VERSION

    c = fit_conformal({"13C": _miscalibrated(2000, seed=14)}, target_coverage=0.90)
    assert c.fingerprint() != a.fingerprint(), "different calibration data, same fingerprint"


def test_a_calibration_round_trips_through_json_unchanged() -> None:
    """It ships as deployed state, so the wire form must be lossless."""

    original = fit_conformal({"13C": _miscalibrated(3000, seed=17)}, target_coverage=0.90)
    restored = ConformalCalibration.from_json(original.to_json())
    assert restored.fingerprint() == original.fingerprint()
    assert restored.target_coverage == original.target_coverage
    assert len(restored.bins) == len(original.bins)
    for sigma in (0.25, 1.5, 13.6, 1e6):
        a = original.interval("13C", sigma)
        b = restored.interval("13C", sigma)
        assert a.half_width_ppm == b.half_width_ppm
        assert a.basis == b.basis


def test_an_unbounded_band_survives_the_round_trip() -> None:
    """The last band runs to +inf, which JSON cannot hold — it travels as null.

    Needs a *continuous* σ: with only a handful of discrete σ values the top quantile
    cut lands on the maximum, leaving the unbounded band empty and correctly folded
    into the pooled interval instead.
    """

    rng = random.Random(18)
    pairs = [(s, abs(rng.gauss(0.0, s))) for s in (rng.uniform(0.05, 15.0) for _ in range(3000))]
    original = fit_conformal({"13C": pairs}, target_coverage=0.90)
    assert any(math.isinf(b.sigma_hi) for b in original.bins), "no unbounded band was fitted"
    restored = ConformalCalibration.from_json(original.to_json())
    assert any(math.isinf(b.sigma_hi) for b in restored.bins)
    assert restored.interval("13C", 1e9).available


def test_a_calibration_from_a_different_fitting_version_is_refused() -> None:
    """Its numbers cannot detect a change in how they were produced, so the version does."""

    original = fit_conformal({"13C": _miscalibrated(2000, seed=19)}, target_coverage=0.90)
    payload = json.loads(original.to_json())
    payload["version"] = "conformal-v0"
    with pytest.raises(ValueError, match="refit rather than reinterpreting"):
        ConformalCalibration.from_json(json.dumps(payload))


def test_an_edited_calibration_is_refused() -> None:
    original = fit_conformal({"13C": _miscalibrated(2000, seed=20)}, target_coverage=0.90)
    payload = json.loads(original.to_json())
    payload["bins"][0]["half_width_ppm"] = 0.001  # someone tightens a band by hand
    with pytest.raises(ValueError, match="fingerprint does not match"):
        ConformalCalibration.from_json(json.dumps(payload))


def test_the_reference_half_width_is_read_off_the_bands() -> None:
    """Consumers anchor on this, so it must track the fit rather than a constant."""

    calibration = fit_conformal({"13C": _miscalibrated(4000, seed=21)}, target_coverage=0.90)
    ref = calibration.reference_half_width("13C", 2.0)
    assert ref is not None
    assert ref == calibration.interval("13C", 2.0).half_width_ppm
    assert calibration.reference_half_width("15N", 2.0) is None


def test_coverage_and_width_are_both_reported() -> None:
    """Coverage alone is not a quality measure — an infinite interval covers everything."""

    calibration = fit_conformal({"13C": _miscalibrated(2000, seed=15)}, target_coverage=0.90)
    stats = measure_coverage(calibration, {"13C": _miscalibrated(2000, seed=16)}).per_nucleus[
        "13C"
    ]
    assert set(stats) >= {"coverage", "mean_half_width_ppm", "median_half_width_ppm"}
    assert math.isfinite(stats["mean_half_width_ppm"])
