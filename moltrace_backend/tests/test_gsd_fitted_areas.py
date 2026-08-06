"""A4: the production deconvolution fits lineshapes and throws the areas away.

``deconvolve_region`` (``nmrcheck/gsd.py``) fits a sum of pseudo-Voigt lines,
each parameterised ``[amp, centre, hwhm, eta]``. The area of such a line is
analytic::

    area = amp * (eta * pi * hwhm + (1 - eta) * hwhm * sqrt(pi / ln 2))

so every fitted area is already available at the moment of the fit. The function
returns ``(centre, height, hwhm)`` and drops ``eta``, and its only consumer
(``spectrum.py:1263``) reads ``line[0]`` — the centre — and nothing else. The
area a chemist reads comes from ``total_area = sum(component.area ...)``, the
PRE-deconvolution sum over raw local maxima.

So the deconvolution informs multiplicity and never touches quantitation. That
is the entire purpose of deconvolving an overlapped region.

These tests are written BEFORE the fix, per the science gate, and define the
contract it has to meet: given two overlapping lines of known area, the fit must
recover those areas. Synthetic on purpose — the point is a case where the truth
is known in closed form, not a case that looks realistic.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from nmrcheck.gsd import deconvolve_region

_LN2 = math.log(2.0)


def _lorentzian(x: np.ndarray, centre: float, height: float, hwhm: float) -> np.ndarray:
    return height * hwhm**2 / ((x - centre) ** 2 + hwhm**2)


def _lorentzian_area(height: float, hwhm: float) -> float:
    """Analytic area of a Lorentzian with the given peak height and HWHM."""
    return height * math.pi * hwhm


def _pseudo_voigt_area(amp: float, hwhm: float, eta: float) -> float:
    return amp * (eta * math.pi * hwhm + (1.0 - eta) * hwhm * math.sqrt(math.pi / _LN2))


def test_the_return_type_still_carries_no_area() -> None:
    """Pins the defect. When the fix lands this fails and is re-baselined.

    Kept deliberately blunt: the tuple width IS the contract, and widening it is
    the smallest change that lets a caller use the fit for quantitation.
    """
    x = np.linspace(0.0, 2.0, 400)
    y = _lorentzian(x, 0.8, 100.0, 0.02) + _lorentzian(x, 1.2, 300.0, 0.02)
    lines = deconvolve_region(
        list(x), list(y), [0.8, 1.2], noise_sigma=0.5, max_lines=8
    )
    assert lines, "deconvolution declined a clean two-line region"
    assert all(len(line) == 3 for line in lines), (
        "deconvolve_region now returns more than (centre, height, hwhm) — if it "
        "carries an area, re-baseline this test and wire it into spectrum.py"
    )


def test_fitted_height_and_width_already_imply_the_right_area_ratio() -> None:
    """The information is present; only the plumbing is missing.

    Two Lorentzians of equal width whose heights are in 1:3 hold areas in 1:3.
    The fit recovers that from ``(height, hwhm)`` alone, which is what makes the
    discard wasteful rather than merely incomplete.
    """
    x = np.linspace(0.0, 2.0, 600)
    hwhm = 0.02
    y = _lorentzian(x, 0.8, 100.0, hwhm) + _lorentzian(x, 1.2, 300.0, hwhm)
    lines = sorted(
        deconvolve_region(list(x), list(y), [0.8, 1.2], noise_sigma=0.5, max_lines=8)
    )
    assert len(lines) >= 2, f"expected two resolved lines, got {lines}"

    left = min(lines, key=lambda line: abs(line[0] - 0.8))
    right = min(lines, key=lambda line: abs(line[0] - 1.2))
    area_left = _lorentzian_area(left[1], left[2])
    area_right = _lorentzian_area(right[1], right[2])

    assert area_right / area_left == pytest.approx(3.0, rel=0.15), (
        f"fitted areas are in ratio {area_right / area_left:.2f}, expected 3.0 "
        f"(left={area_left:.4g}, right={area_right:.4g})"
    )


def test_overlapping_lines_of_unequal_width_are_separated_by_the_fit() -> None:
    """The case a raw local-maximum sum cannot handle.

    A broad, short line and a sharp, tall one can carry the SAME area while
    looking nothing alike. Summing raw maxima gets this wrong by construction;
    the fit gets it right, and the fit is what is discarded.
    """
    x = np.linspace(0.0, 2.0, 800)
    broad = _lorentzian(x, 0.95, 50.0, 0.06)
    sharp = _lorentzian(x, 1.05, 150.0, 0.02)
    lines = deconvolve_region(
        list(x), list(broad + sharp), [0.95, 1.05], noise_sigma=0.5, max_lines=8
    )
    assert len(lines) >= 2, f"the fit merged two resolvable lines: {lines}"

    a = min(lines, key=lambda line: abs(line[0] - 0.95))
    b = min(lines, key=lambda line: abs(line[0] - 1.05))
    # True areas: 50*pi*0.06 = 9.42 and 150*pi*0.02 = 9.42 — equal.
    ratio = _lorentzian_area(a[1], a[2]) / _lorentzian_area(b[1], b[2])
    assert ratio == pytest.approx(1.0, rel=0.25), (
        f"two lines of equal area but different width came back in ratio {ratio:.2f}; "
        "the fit should separate them even though their heights differ 3x"
    )


def test_the_production_peak_area_ignores_the_fit_entirely() -> None:
    """The consequence, at the level a chemist sees.

    ``_cluster_peak_components`` (spectrum.py:1204) emits one estimate per
    cluster with ``area=total_area``, summed from raw components before any
    deconvolution runs. Whether the fit succeeded or not cannot change that
    number.
    """
    import inspect

    from nmrcheck import spectrum

    source = inspect.getsource(spectrum._cluster_peak_components)
    assert "area=total_area" in source, (
        "the cluster area is no longer total_area — if it now comes from the "
        "fitted lines, this test has served its purpose and should be replaced "
        "by one asserting the recovered areas"
    )
    assert "resolved_lines" in source
    # The fit's only consumer takes the centres.
    assert "line[0] for line in resolved_lines" in source, (
        "resolved_lines is consumed differently now; re-check whether heights "
        "and widths reach quantitation"
    )
