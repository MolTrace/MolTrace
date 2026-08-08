"""Invariants for the verifier's significance mapping, across the σ→interval switch.

Written *before* the switch. `_significance_from_sigma` fed the arbiter a claimed
uncertainty that held-out measurement showed is differentially mis-scaled — the
half-width/σ ratio runs 8.66× in the tightest ¹³C band down to 1.77× in the widest,
where a correctly-scaled σ would give a constant. Feeding the arbiter a guaranteed
interval instead changes every posterior in the system, so the properties that must
survive the change are pinned here first, and the numbers that legitimately move are
re-baselined visibly in `test_significance_rebaseline`.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from moltrace.spectroscopy.eval.conformal import ConformalBin, ConformalCalibration
from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.verification.scorer import (
    _SIG_DEFAULT,
    _SIG_MAX,
    _SIGMA_REF_PPM,
    VerificationOptions,
    _significance_from_half_width,
    _significance_from_sigma,
    verify_structure,
)


def _calibration() -> ConformalCalibration:
    """The bands measured on held-out NMRShiftDB2 (see the 2026-08-08 measurement)."""

    edges_13c = [
        (0.00, 0.31, 0.169, 1.460),
        (0.31, 0.62, 0.461, 1.883),
        (0.62, 1.04, 0.822, 2.531),
        (1.04, 1.61, 1.308, 3.422),
        (1.61, 2.41, 2.005, 4.722),
        (2.41, 3.23, 2.830, 5.929),
        (3.23, 4.11, 3.674, 7.062),
        (4.11, 5.26, 4.644, 8.300),
        (5.26, 8.04, 6.382, 11.683),
        (8.04, math.inf, 12.656, 22.365),
    ]
    edges_1h = [
        (0.00, 0.04, 0.021, 0.149),
        (0.04, 0.07, 0.056, 0.242),
        (0.07, 0.11, 0.095, 0.250),
        (0.11, 0.16, 0.138, 0.322),
        (0.16, 0.22, 0.189, 0.397),
        (0.22, 0.30, 0.261, 0.512),
        (0.30, 0.41, 0.357, 0.618),
        (0.41, 0.56, 0.477, 0.884),
        (0.56, 0.82, 0.666, 1.304),
        (0.82, math.inf, 1.368, 2.594),
    ]
    bins = tuple(
        ConformalBin(nucleus=nuc, sigma_lo=lo, sigma_hi=hi, n=3890, half_width_ppm=hw,
                     mean_sigma_ppm=ms)
        for nuc, rows in (("13C", edges_13c), ("1H", edges_1h))
        for lo, hi, ms, hw in rows
    )
    return ConformalCalibration(
        target_coverage=0.90,
        bins=bins,
        pooled={"13C": 8.395, "1H": 0.832},
        n_calibration={"13C": 38895, "1H": 12870},
    )


# --------------------------------------------------------------------------- #
# Invariants — these must hold on BOTH sides of the switch
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("nucleus", ["1H", "13C"])
def test_significance_stays_inside_the_declared_range(nucleus: str) -> None:
    cal = _calibration()
    ref = cal.reference_half_width(nucleus, _SIGMA_REF_PPM[nucleus])
    assert ref is not None
    for width in (0.0, 1e-9, 0.5, 2.0, 10.0, 1e6):
        sig = _significance_from_half_width(width, reference_half_width=ref)
        assert 0.0 <= sig <= _SIG_MAX


@pytest.mark.parametrize("nucleus", ["1H", "13C"])
def test_significance_is_monotone_decreasing_in_the_width(nucleus: str) -> None:
    """Less certainty must never buy more evidence. The direction is the whole point."""

    cal = _calibration()
    ref = cal.reference_half_width(nucleus, _SIGMA_REF_PPM[nucleus])
    assert ref is not None
    widths = [0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 20.0, 100.0]
    sigs = [_significance_from_half_width(w, reference_half_width=ref) for w in widths]
    assert sigs == sorted(sigs, reverse=True)
    assert sigs[0] > sigs[-1], "the mapping is flat; it carries no information"


@pytest.mark.parametrize("nucleus", ["1H", "13C"])
def test_the_reference_anchors_at_the_medium_band(nucleus: str) -> None:
    """An atom at the reference scores 4 — 'medium' — on both bases.

    This is the anchor that makes the two mappings comparable at all, and it is why
    the reference half-width is read off the calibration rather than restated as a
    constant: refitting moves the bands, and the anchor has to move with them.
    """

    cal = _calibration()
    ref = cal.reference_half_width(nucleus, _SIGMA_REF_PPM[nucleus])
    assert ref is not None
    assert _significance_from_half_width(ref, reference_half_width=ref) == pytest.approx(
        _SIG_MAX / 2.0
    )
    assert _significance_from_sigma(
        _SIGMA_REF_PPM[nucleus], nucleus
    ) == pytest.approx(_SIG_MAX / 2.0)


def test_an_unusable_width_abstains_rather_than_scoring_zero_or_full() -> None:
    """No interval is an abstention, and must land on the same default σ used."""

    for width in (None, float("nan"), float("inf"), -1.0):
        assert _significance_from_half_width(width, reference_half_width=1.0) == _SIG_DEFAULT
    assert _significance_from_sigma(float("nan"), "13C") == _SIG_DEFAULT


def test_a_missing_reference_abstains() -> None:
    """A calibration that cannot anchor must not silently score everything as certain."""

    assert _significance_from_half_width(1.0, reference_half_width=None) == _SIG_DEFAULT
    assert _significance_from_half_width(1.0, reference_half_width=0.0) == _SIG_DEFAULT


# --------------------------------------------------------------------------- #
# Re-baseline — the numbers that legitimately move, recorded visibly
# --------------------------------------------------------------------------- #
def test_significance_rebaseline_13c() -> None:
    """What the switch does, band by band, on the measured ¹³C calibration.

    The mapping *compresses*: tight atoms lose significance they had not earned, wide
    atoms gain some back. That is the intended correction — σ's range was 4.90× too
    spread, so scoring off it over-rewarded confidence and over-punished honesty.
    """

    cal = _calibration()
    ref = cal.reference_half_width("13C", 2.0)
    assert ref == pytest.approx(4.722)

    # (mean σ, expected significance from σ, expected significance from the interval)
    expected = [
        (0.169, 7.376671, 6.110644),
        (2.005, 3.995006, 4.000000),
        (12.656, 1.091703, 1.394617),
    ]
    for sigma, from_sigma, from_interval in expected:
        assert _significance_from_sigma(sigma, "13C") == pytest.approx(from_sigma, abs=1e-3)
        width = cal.interval("13C", sigma).half_width_ppm
        assert width is not None
        assert _significance_from_half_width(
            width, reference_half_width=ref
        ) == pytest.approx(from_interval, abs=1e-3)

    # The compression, stated as the property rather than the numbers: the ratio of
    # most- to least-significant shrinks, because σ's spread was the artefact.
    sigma_spread = _significance_from_sigma(0.169, "13C") / _significance_from_sigma(
        12.656, "13C"
    )
    interval_spread = 6.110644 / 1.394617
    assert sigma_spread > interval_spread
    assert sigma_spread == pytest.approx(6.757, abs=0.001)
    assert interval_spread == pytest.approx(4.382, abs=0.001)


def test_significance_rebaseline_1h() -> None:
    cal = _calibration()
    ref = cal.reference_half_width("1H", 0.10)
    assert ref == pytest.approx(0.250)

    for sigma, from_sigma, from_interval in [
        (0.021, 6.611570, 5.012531),
        (0.095, 4.102564, 4.000000),
        (1.368, 0.544959, 0.703235),
    ]:
        assert _significance_from_sigma(sigma, "1H") == pytest.approx(from_sigma, abs=1e-3)
        width = cal.interval("1H", sigma).half_width_ppm
        assert width is not None
        assert _significance_from_half_width(
            width, reference_half_width=ref
        ) == pytest.approx(from_interval, abs=1e-3)


# --------------------------------------------------------------------------- #
# End to end through verify_structure
# --------------------------------------------------------------------------- #
def _synthetic_1h(center: float = 7.26, width: float = 0.01, npts: int = 20000) -> NMRSpectrum:
    ppm = np.linspace(10.0, 0.0, npts)
    data = (width**2) / ((ppm - center) ** 2 + width**2)
    return NMRSpectrum(data=data, ppm_axis=ppm, nucleus="1H", solvent="CDCl3", field_mhz=400.0)


def _bounds_details(result) -> dict:
    return next(t for t in result.test_results if t.name == "prediction_bounds").details


def test_without_a_calibration_every_match_is_scored_on_sigma_and_says_so() -> None:
    """The verdict is still produced on the weaker basis, never withheld — but labelled."""

    result = verify_structure(_synthetic_1h(), "c1ccccc1", prior_confidence=0.5)
    basis = _bounds_details(result)["significance_basis"]
    assert basis["conformal_interval"] == 0
    assert basis["predicted_sigma"] > 0
    assert basis["calibration_fingerprint"] is None
    bounds = next(t for t in result.test_results if t.name == "prediction_bounds")
    assert "weighted by predicted σ" in bounds.diagnostic


def test_with_a_calibration_the_interval_scores_the_match_and_provenance_is_recorded() -> None:
    calibration = _calibration()
    result = verify_structure(
        _synthetic_1h(),
        "c1ccccc1",
        prior_confidence=0.5,
        options=VerificationOptions(shift_calibration=calibration),
    )
    basis = _bounds_details(result)["significance_basis"]
    assert basis["conformal_interval"] > 0
    assert basis["predicted_sigma"] == 0
    assert basis["calibration_fingerprint"] == calibration.fingerprint()
    assert basis["calibration_target_coverage"] == pytest.approx(0.90)
    assert basis["reference_half_width_ppm"] == pytest.approx(0.250)
    bounds = next(t for t in result.test_results if t.name == "prediction_bounds")
    assert "weighted by conformal interval" in bounds.diagnostic


def test_the_calibration_changes_the_posterior_it_does_not_decide_the_verdict() -> None:
    """The arbiter still arbitrates. Re-weighting evidence must not flip a clear call."""

    spectrum = _synthetic_1h()
    without = verify_structure(spectrum, "c1ccccc1", prior_confidence=0.5)
    with_cal = verify_structure(
        spectrum,
        "c1ccccc1",
        prior_confidence=0.5,
        options=VerificationOptions(shift_calibration=_calibration()),
    )
    assert without.posterior_confidence != with_cal.posterior_confidence
    assert without.verdict == with_cal.verdict
    # Both remain on the corroborating side of the prior; the interval changes how
    # much the evidence is worth, not which way it points.
    assert without.posterior_confidence > 0.5
    assert with_cal.posterior_confidence > 0.5


def test_a_calibration_that_cannot_anchor_falls_back_rather_than_scoring_everything_certain() -> (
    None
):
    """An empty calibration must not read as 'no uncertainty'."""

    empty = ConformalCalibration(
        target_coverage=0.90, bins=(), pooled={}, n_calibration={}
    )
    result = verify_structure(
        _synthetic_1h(),
        "c1ccccc1",
        prior_confidence=0.5,
        options=VerificationOptions(shift_calibration=empty),
    )
    basis = _bounds_details(result)["significance_basis"]
    assert basis["conformal_interval"] == 0
    assert basis["predicted_sigma"] > 0
    assert basis["reference_half_width_ppm"] is None
