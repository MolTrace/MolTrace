"""Invariants for AssignmentsTest's candidate radius and merit scale.

Written before the change. Both were σ-blind: a flat `3.0 * base_tol` radius
(12.0 ppm ¹³C / 0.90 ppm ¹H) and a merit Gaussian of flat width `base_tol`. Measured
on held-out NMRShiftDB2 the flat radius loses the true pairing for **5.0 % of ¹³C and
9.0 % of ¹H resonances**, and each loss is penalised twice — merit 0.0 *and* the
resonance's integral counted as unexplained impurity, which lowers the test's own
significance. A σ-adaptive radius raises retention to 99.1 % / 99.3 %.

The merit scale matters as much. On a fixed 4.0 ppm ruler an atom predicted to
±1.5 ppm scores 0.88 for a 2 ppm miss that is well outside its interval, while an atom
predicted to ±22 ppm scores 0.32 for a 6 ppm hit that is well inside its own. Scaling
by the interval makes "at the edge of the interval" score the same everywhere.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from moltrace.spectroscopy.eval.conformal import ConformalBin, ConformalCalibration
from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.verification.scorer import (
    _SHIFT_TOL_PPM,
    VerificationOptions,
    verify_structure,
)


def _calibration() -> ConformalCalibration:
    """The bands measured on held-out NMRShiftDB2 (2026-08-08)."""

    rows = {
        "13C": [
            (0.00, 0.31, 0.169, 1.460), (0.31, 0.62, 0.461, 1.883),
            (0.62, 1.04, 0.822, 2.531), (1.04, 1.61, 1.308, 3.422),
            (1.61, 2.41, 2.005, 4.722), (2.41, 3.23, 2.830, 5.929),
            (3.23, 4.11, 3.674, 7.062), (4.11, 5.26, 4.644, 8.300),
            (5.26, 8.04, 6.382, 11.683), (8.04, math.inf, 12.656, 22.365),
        ],
        "1H": [
            (0.00, 0.04, 0.021, 0.149), (0.04, 0.07, 0.056, 0.242),
            (0.07, 0.11, 0.095, 0.250), (0.11, 0.16, 0.138, 0.322),
            (0.16, 0.22, 0.189, 0.397), (0.22, 0.30, 0.261, 0.512),
            (0.30, 0.41, 0.357, 0.618), (0.41, 0.56, 0.477, 0.884),
            (0.56, 0.82, 0.666, 1.304), (0.82, math.inf, 1.368, 2.594),
        ],
    }
    bins = tuple(
        ConformalBin(nucleus=nuc, sigma_lo=lo, sigma_hi=hi, n=3890,
                     half_width_ppm=hw, mean_sigma_ppm=ms)
        for nuc, band in rows.items()
        for lo, hi, ms, hw in band
    )
    return ConformalCalibration(
        target_coverage=0.90, bins=bins,
        pooled={"13C": 8.395, "1H": 0.832},
        n_calibration={"13C": 38895, "1H": 12870},
    )


def _spectrum(center: float = 7.26, width: float = 0.01, npts: int = 20000) -> NMRSpectrum:
    ppm = np.linspace(10.0, 0.0, npts)
    data = (width**2) / ((ppm - center) ** 2 + width**2)
    return NMRSpectrum(data=data, ppm_axis=ppm, nucleus="1H", solvent="CDCl3", field_mhz=400.0)


def _assignments(result):
    return next(t for t in result.test_results if t.name == "assignments")


# --------------------------------------------------------------------------- #
# The no-regression guarantee
# --------------------------------------------------------------------------- #
def test_without_a_calibration_the_test_is_byte_identical_to_today() -> None:
    """The flat constants must still govern when nothing better is supplied.

    This is the guarantee that makes the change safe to land: a deployment with no
    fitted calibration sees exactly the behaviour it saw before.
    """

    spectrum = _spectrum()
    a = verify_structure(spectrum, "c1ccccc1", prior_confidence=0.5, tests=["assignments"])
    b = verify_structure(
        spectrum, "c1ccccc1", prior_confidence=0.5, tests=["assignments"],
        options=VerificationOptions(),
    )
    for left, right in ((a, b),):
        assert left.posterior_confidence == right.posterior_confidence
    details = _assignments(a).details
    assert details["window_basis"]["conformal"] == 0
    assert details["window_basis"]["flat"] > 0
    assert details["window_basis"]["calibration_fingerprint"] is None


def test_with_a_calibration_the_basis_and_provenance_are_recorded() -> None:
    calibration = _calibration()
    result = verify_structure(
        _spectrum(), "c1ccccc1", prior_confidence=0.5, tests=["assignments"],
        options=VerificationOptions(shift_calibration=calibration),
    )
    basis = _assignments(result).details["window_basis"]
    assert basis["conformal"] > 0
    assert basis["flat"] == 0
    assert basis["calibration_fingerprint"] == calibration.fingerprint()
    assert "conformal interval" in _assignments(result).diagnostic


def test_a_calibration_that_cannot_price_a_resonance_falls_back_to_the_flat_scale() -> None:
    """An empty calibration must not collapse the radius to zero and orphan everything."""

    empty = ConformalCalibration(
        target_coverage=0.90, bins=(), pooled={}, n_calibration={}
    )
    result = verify_structure(
        _spectrum(), "c1ccccc1", prior_confidence=0.5, tests=["assignments"],
        options=VerificationOptions(shift_calibration=empty),
    )
    details = _assignments(result).details
    assert details["window_basis"]["conformal"] == 0
    assert details["window_basis"]["flat"] > 0
    # And it still assigns, rather than reporting the whole spectrum as impurity.
    assert details["assigned"] > 0


# --------------------------------------------------------------------------- #
# Properties of the merit scale
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("nucleus", ["1H", "13C"])
def test_a_pairing_at_the_edge_of_its_scale_scores_the_same_everywhere(nucleus: str) -> None:
    """The point of scaling: 'one interval away' must mean one thing, not two.

    Under a flat ruler the same physical agreement scores differently by nucleus and
    by confidence. Under the interval it is exp(-0.5) whatever the atom.
    """

    from moltrace.spectroscopy.verification.scorer import _shift_merit

    for scale in (0.149, 0.250, 1.460, 4.722, 22.365):
        assert _shift_merit(scale, scale) == pytest.approx(math.exp(-0.5))
        assert _shift_merit(0.0, scale) == pytest.approx(1.0)


def test_merit_is_bounded_and_monotone_in_the_distance() -> None:
    from moltrace.spectroscopy.verification.scorer import _shift_merit

    scale = 4.722
    merits = [_shift_merit(d, scale) for d in (0.0, 0.5, 1.0, 2.0, 5.0, 20.0, 100.0)]
    assert merits == sorted(merits, reverse=True)
    assert all(0.0 <= m <= 1.0 for m in merits)


def test_a_non_finite_scale_does_not_produce_a_nan_merit() -> None:
    """A merit of NaN would poison the mean and silently break the whole test."""

    from moltrace.spectroscopy.verification.scorer import _shift_merit

    for scale in (0.0, -1.0, float("nan"), float("inf")):
        merit = _shift_merit(1.0, scale)
        assert math.isfinite(merit)
        assert 0.0 <= merit <= 1.0


# --------------------------------------------------------------------------- #
# Re-baseline — the constants that stay, and what they now mean
# --------------------------------------------------------------------------- #
def test_the_flat_constants_remain_the_documented_fallback() -> None:
    """They are no longer the only rule, but they are still the rule without a calibration."""

    assert _SHIFT_TOL_PPM == {"1H": 0.30, "13C": 4.0}


def test_the_calibration_changes_the_assignment_without_deciding_the_verdict() -> None:
    spectrum = _spectrum()
    without = verify_structure(spectrum, "c1ccccc1", prior_confidence=0.5)
    with_cal = verify_structure(
        spectrum, "c1ccccc1", prior_confidence=0.5,
        options=VerificationOptions(shift_calibration=_calibration()),
    )
    assert without.verdict == with_cal.verdict
    assert without.posterior_confidence > 0.5
    assert with_cal.posterior_confidence > 0.5
