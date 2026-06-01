"""Regression test for the GSD ``_fallback_peak`` area-integration path.

``_fallback_peak`` integrates the local intensity window with the NumPy
trapezoid rule when the lmfit model fit is unavailable / fails.  NumPy 2.0
renamed ``np.trapz`` to ``np.trapezoid`` and later removed ``np.trapz``
entirely, so the old call raised ``AttributeError`` on modern NumPy.  Because
nothing in the suite exercised the fallback path, that crash was dormant.  This
test calls the path directly so the regression can't return silently.
"""

from __future__ import annotations

import math

import numpy as np

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.peaks import gsd
from moltrace.spectroscopy.peaks.gsd import Peak


def _lorentzian_spectrum() -> tuple[np.ndarray, np.ndarray, NMRSpectrum]:
    ppm = np.linspace(10.0, 0.0, 2048)  # descending, like NMRSpectrum
    center, hwhm = 5.0, 0.02
    intensity = 100.0 * hwhm * hwhm / ((ppm - center) ** 2 + hwhm * hwhm)
    spectrum = NMRSpectrum(
        data=intensity,
        ppm_axis=ppm,
        metadata={"source": "test_gsd_fallback_peak"},
        nucleus="1H",
        solvent="",
        field_mhz=500.0,
    )
    return ppm, intensity, spectrum


def test_fallback_peak_returns_finite_positive_area() -> None:
    ppm, intensity, spectrum = _lorentzian_spectrum()
    index = int(np.argmax(intensity))

    peak = gsd._fallback_peak(
        ppm,
        intensity,
        index,
        width_points=5.0,
        spectrum=spectrum,
        level=2,
        noise=1.0,
    )

    assert isinstance(peak, Peak)
    assert math.isfinite(peak.area) and peak.area > 0.0
    assert math.isfinite(peak.intensity) and peak.intensity > 0.0
    assert math.isclose(peak.position_ppm, 5.0, abs_tol=0.05)


def test_np_trapezoid_shim_integrates_correctly() -> None:
    # The version-robust binding must be present and numerically correct
    # (trapezoid of a unit-height window of width 2 ppm = 2.0).
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([1.0, 1.0, 1.0])
    assert abs(float(gsd._np_trapezoid(y, x=x)) - 2.0) < 1e-12
