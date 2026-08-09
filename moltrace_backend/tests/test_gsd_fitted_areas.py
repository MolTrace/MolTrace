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


def test_the_return_type_now_carries_the_fitted_area() -> None:
    """RE-BASELINED. This asserted `len(line) == 3` and was written to fail here.

    Its own message said: "if it carries an area, re-baseline this test and wire
    it into spectrum.py". That is what happened. The tuple is now
    ``(centre, height, hwhm, area)``.

    Widening the return is the whole point. Every fitted area exists at the
    moment of the fit, where ``eta`` is in scope; dropping it forced any consumer
    to reconstruct the area from height and width alone, which silently assumes a
    pure Lorentzian and overstates a pseudo-Voigt line by up to ~32 %. The
    reconstruction could not be corrected from outside the function, because the
    parameter it needs was the one being discarded.
    """
    x = np.linspace(0.0, 2.0, 400)
    y = _lorentzian(x, 0.8, 100.0, 0.02) + _lorentzian(x, 1.2, 300.0, 0.02)
    lines = deconvolve_region(
        list(x), list(y), [0.8, 1.2], noise_sigma=0.5, max_lines=8
    )
    assert lines, "deconvolution declined a clean two-line region"
    assert all(len(line) == 4 for line in lines), (
        f"expected (centre, height, hwhm, area) per line, got widths "
        f"{sorted({len(line) for line in lines})}"
    )
    assert all(line[3] > 0.0 for line in lines), "a fitted line reported no area"


def test_the_reported_area_is_the_analytic_pseudo_voigt_area() -> None:
    """The area must come from inside the fit, not be re-derived outside it.

    Checked against the closed form for the shape the module actually fits --
    ``amp * (eta * Lorentzian + (1 - eta) * Gaussian)`` sharing one hwhm, so
    ``area = amp * (eta * pi * w + (1 - eta) * w * sqrt(pi / ln 2))``. A pure
    Lorentzian is the one case where the naive ``h * pi * w`` reconstruction is
    also correct, so it is used here as the anchor that ties the two together.
    """
    x = np.linspace(0.0, 2.0, 600)
    height, hwhm = 200.0, 0.02
    y = _lorentzian(x, 1.0, height, hwhm)
    lines = deconvolve_region(list(x), list(y), [1.0], noise_sigma=0.5, max_lines=4)
    assert len(lines) == 1, f"a single clean Lorentzian resolved into {len(lines)} lines"

    _, fitted_height, fitted_hwhm, area = lines[0]
    lorentzian_area = fitted_height * math.pi * fitted_hwhm
    assert area == pytest.approx(lorentzian_area, rel=0.05), (
        f"reported area {area:.4g} does not match the analytic Lorentzian area "
        f"{lorentzian_area:.4g} for the same fitted height and width"
    )


def test_a_gaussian_line_is_not_billed_as_a_lorentzian() -> None:
    """The 32 % overstatement this change exists to remove.

    For one height and width, a Gaussian holds ``sqrt(pi/ln2)/pi`` ~ 0.6 of a
    Lorentzian's area. A consumer reconstructing ``h * pi * w`` from the old
    3-tuple would bill a Gaussian line ~66 % too high; the reported area must
    track the shape that was actually fitted.
    """
    x = np.linspace(0.0, 2.0, 600)
    height, hwhm = 200.0, 0.02
    y = height * np.exp(-_LN2 * ((x - 1.0) / hwhm) ** 2)
    lines = deconvolve_region(list(x), list(y), [1.0], noise_sigma=0.5, max_lines=4)
    assert len(lines) == 1, f"a single clean Gaussian resolved into {len(lines)} lines"

    _, fitted_height, fitted_hwhm, area = lines[0]
    naive_lorentzian = fitted_height * math.pi * fitted_hwhm
    gaussian_area = fitted_height * fitted_hwhm * math.sqrt(math.pi / _LN2)

    assert area == pytest.approx(gaussian_area, rel=0.10), (
        f"reported area {area:.4g} is not the Gaussian area {gaussian_area:.4g}"
    )
    assert area < naive_lorentzian * 0.75, (
        "the reported area is indistinguishable from the pure-Lorentzian "
        "reconstruction, so eta is not reaching the area calculation"
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
