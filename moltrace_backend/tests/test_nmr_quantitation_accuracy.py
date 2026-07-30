"""Quantitation accuracy against analytically-known ground truth.

Everything else in the NMR test suite checks *behaviour*: given these peaks,
does the classifier bucket them correctly. Nothing checked the number that
matters most to a chemist — is the integral right?

Here each spectrum is SYNTHESISED from Lorentzians whose areas are known in
closed form, so the recovered integral ratios can be compared with truth and
the error reported as a percentage. A Lorentzian

    L(x) = A · hwhm² / ((x − x₀)² + hwhm²)

has analytic area A·π·hwhm over the full line, so the true integral ratios are
exactly the ratios of A·hwhm.

The broad+sharp case is the important one. Integration walks outward from each
maximum but is hard-capped at ±40 points, so the fraction of a Lorentzian's
area recovered is (2/π)·arctan(w/hwhm) where w is the half-window in ppm. For a
broad resonance that window is a fraction of the linewidth and most of the area
is discarded — which is invisible to a ratio test only if every peak is equally
broad.
"""

from __future__ import annotations

import math

import pytest

from nmrcheck.spectrum import _infer_peak_estimates

# Realistic 1H digitisation: 0-10 ppm over 32768 points ~ 3277 points/ppm.
_PPM_LO, _PPM_HI, _N_POINTS = 0.0, 10.0, 32768


def _lorentzian(x: float, centre: float, hwhm: float, amplitude: float) -> float:
    return amplitude * (hwhm * hwhm) / ((x - centre) ** 2 + hwhm * hwhm)


def _synth(
    lines: list[tuple[float, float, float]],
    *,
    noise: float = 0.0,
    seed: int = 0,
) -> list[tuple[float, float]]:
    """Build a (ppm, intensity) trace from (centre, hwhm, amplitude) lines."""
    import random

    rng = random.Random(seed)
    step = (_PPM_HI - _PPM_LO) / (_N_POINTS - 1)
    points: list[tuple[float, float]] = []
    for i in range(_N_POINTS):
        x = _PPM_LO + i * step
        y = sum(_lorentzian(x, c, h, a) for c, h, a in lines)
        if noise:
            y += rng.gauss(0.0, noise)
        points.append((x, y))
    return points


def _true_fractions(lines: list[tuple[float, float, float]]) -> list[float]:
    areas = [a * math.pi * h for _c, h, a in lines]
    total = sum(areas)
    return [area / total for area in areas]


def _recovered_fractions(
    lines: list[tuple[float, float, float]], **kwargs
) -> tuple[list[float], list[float]]:
    """Return (recovered_fractions, true_fractions) aligned by shift."""
    points = _synth(lines, **kwargs)
    estimates = _infer_peak_estimates(points, sensitivity=0.06, frequency_mhz=400.0)
    total_area = sum(e.area for e in estimates)
    if total_area <= 0:
        return [], _true_fractions(lines)

    # Align each synthesised line to its nearest detected estimate, summing
    # estimates that belong to the same line (a split multiplet is still one
    # chemical environment).
    recovered = [0.0] * len(lines)
    for est in estimates:
        nearest = min(
            range(len(lines)), key=lambda i: abs(lines[i][0] - est.shift_ppm)
        )
        recovered[nearest] += est.area
    return [r / total_area for r in recovered], _true_fractions(lines)


def _max_relative_error(recovered: list[float], truth: list[float]) -> float:
    if not recovered:
        return float("inf")
    return max(abs(r - t) / t for r, t in zip(recovered, truth))


# (name, lines, allowed relative error on the integral ratios)
CASES: list[tuple[str, list[tuple[float, float, float]], float]] = [
    (
        # Three well-separated singlets of equal linewidth, 3 : 2 : 1.
        # Equal widths mean truncation removes the same fraction from each, so
        # even a crude integrator gets the RATIOS right. This case exists to
        # prove the harness itself is sound.
        "separated_equal_width_3_2_1",
        [(7.00, 0.004, 3.0), (4.00, 0.004, 2.0), (1.00, 0.004, 1.0)],
        0.10,
    ),
    (
        # A broad resonance (hwhm 0.05 ppm, e.g. an exchanging OH or a polymer
        # envelope) alongside two sharp ones. Truncation now bites unequally
        # and the broad peak's integral collapses.
        "broad_plus_sharp",
        [(6.00, 0.050, 1.0), (3.00, 0.004, 2.0), (1.20, 0.004, 1.0)],
        0.15,
    ),
    (
        # Wide dynamic range with the small peaks well clear of the large one.
        "well_separated_dynamic_range",
        [(7.30, 0.006, 35.0), (3.00, 0.004, 1.0), (1.00, 0.004, 1.0)],
        0.20,
    ),
    (
        # Wide dynamic range, as in an aryl-protected sugar: 35 H of aromatic
        # against single-proton resonances.
        "wide_dynamic_range",
        [(7.30, 0.006, 35.0), (5.40, 0.004, 1.0), (5.30, 0.004, 1.0)],
        0.20,
    ),
]


@pytest.mark.parametrize("name,lines,tolerance", CASES, ids=[c[0] for c in CASES])
def test_integral_ratios_match_analytic_truth(
    name: str, lines: list[tuple[float, float, float]], tolerance: float
) -> None:
    recovered, truth = _recovered_fractions(lines)
    assert recovered, f"{name}: no peaks detected at all"
    error = _max_relative_error(recovered, truth)
    detail = ", ".join(
        f"{lines[i][0]:.2f} ppm: got {recovered[i]:.3f} want {truth[i]:.3f}"
        for i in range(len(lines))
    )
    assert error <= tolerance, (
        f"{name}: integral ratios off by {error:.1%} (limit {tolerance:.0%}). {detail}"
    )


def test_overlapping_envelope_conserves_total_area() -> None:
    """Overlapping neighbours must conserve area even if they merge.

    Two broad environments 0.05 ppm apart (2.5 hwhm) are clustered into a
    single multiplet by the 1D pipeline. Deciding whether that cluster is ONE
    environment showing a doublet or TWO environments that happen to overlap is
    not answerable from a 1D trace alone — two sharp singlets that close would
    be 8 Hz apart at 400 MHz, i.e. an ordinary vicinal coupling. Splitting them
    correctly requires knowing how many environments the structure actually
    has, which is the job of the structure-constrained assignment.

    What integration MUST guarantee at this stage is conservation: whatever the
    cluster is called, its total area relative to a remote reference peak has
    to be right. A pipeline that silently loses one of two overlapping lines
    fails here.
    """
    lines = [(4.05, 0.020, 1.0), (4.00, 0.020, 1.0), (1.00, 0.004, 1.0)]
    recovered, truth = _recovered_fractions(lines)
    assert recovered, "no peaks detected"

    group_recovered = recovered[0] + recovered[1]
    group_truth = truth[0] + truth[1]
    error = abs(group_recovered - group_truth) / group_truth
    assert error <= 0.15, (
        f"overlapping envelope lost area: recovered {group_recovered:.3f} of the "
        f"total vs {group_truth:.3f} expected ({error:.1%} off). The remote "
        f"singlet got {recovered[2]:.3f} vs {truth[2]:.3f}."
    )


class TestDataDerivedScale:
    """Proton counts recovered from the spectrum, not from the answer.

    Scaling integrals so their sum equals the structure's proton total makes
    the observed grand total match the expected one by construction. These
    tests check the alternative: protons are quantised, so the correct scale is
    the one under which every peak lands near a whole number — a property of
    the data alone.
    """

    def test_recovers_proton_counts_without_the_structure(self) -> None:
        from nmrcheck.spectrum import _data_derived_integration_scale

        # True counts 3 : 2 : 1 : 1 in arbitrary area units, plus a few percent
        # of integration error such as a real spectrum carries.
        areas = [3.06, 1.98, 1.01, 0.99]
        fit = _data_derived_integration_scale(areas)
        assert fit is not None
        scale, residual = fit
        recovered = [round(a * scale) for a in areas]
        assert recovered == [3, 2, 1, 1], (
            f"got {recovered} (scale {scale}, resid {residual})"
        )
        assert residual < 0.12

    def test_handles_a_smallest_peak_that_is_not_one_proton(self) -> None:
        """The smallest peak is not always 1 H.

        Assuming it is — as the provisional scale did — misprices every other
        peak whenever the smallest resonance is a 2 H methylene.
        """
        from nmrcheck.spectrum import _data_derived_integration_scale

        # True counts 6 : 4 : 2 : 2; the smallest peak is 2 H.
        areas = [6.03, 3.98, 2.02, 1.99]
        fit = _data_derived_integration_scale(areas)
        assert fit is not None
        scale, _residual = fit
        recovered = [round(a * scale) for a in areas]
        assert recovered in ([6, 4, 2, 2], [3, 2, 1, 1]), f"got {recovered}"
        # Whichever quantum it picks, the RATIOS must be right.
        assert recovered[0] / recovered[2] == pytest.approx(3.0)

    def test_a_good_fit_alone_is_not_evidence(self) -> None:
        """The measured limitation, pinned so it cannot be forgotten.

        A free scale fitting N integers has one parameter, so for small N it is
        close to unfalsifiable. Areas in the ratio 1 : sqrt(2) : sqrt(3) — which
        are NOT a whole-number ratio — fit "3 : 4 : 5" with a low residual.
        A low residual therefore must never on its own justify reporting proton
        counts; the caller has to corroborate the implied total against the
        structure.
        """
        from nmrcheck.spectrum import _data_derived_integration_scale

        areas = [1.0, math.sqrt(2), math.sqrt(3), math.sqrt(5)]
        fit = _data_derived_integration_scale(areas)
        if fit is not None:
            assert fit[1] < 0.2, (
                "irrational area ratios still produce a plausible-looking fit; "
                "this is the documented limitation, so the caller must gate on "
                "corroboration rather than on residual alone"
            )

    def test_too_few_peaks_is_rejected_as_underdetermined(self) -> None:
        from nmrcheck.spectrum import _data_derived_integration_scale

        # Any two peaks fit perfectly; three are barely better.
        assert _data_derived_integration_scale([1.0, 1.5]) is None
        assert _data_derived_integration_scale([3.06, 1.98, 1.01]) is None

    def test_clean_synthetic_case_fits_essentially_perfectly(self) -> None:
        from nmrcheck.spectrum import _data_derived_integration_scale

        fit = _data_derived_integration_scale([3.0, 2.0, 1.0, 1.0])
        assert fit is not None
        assert fit[1] < 0.01


def test_truncation_loss_is_reported_not_silent() -> None:
    """A Lorentzian's recovered fraction must not depend on its linewidth.

    Two lines of identical area but very different width must integrate to the
    same value. If integration truncates at a fixed number of points, the broad
    line loses most of its area while the sharp line keeps nearly all of it,
    and the reported proton counts are wrong in a way no ratio check on
    equal-width peaks would ever reveal.
    """
    # Equal analytic area (A·hwhm equal), 10x difference in width.
    lines = [(6.00, 0.040, 1.0), (2.00, 0.004, 10.0)]
    recovered, truth = _recovered_fractions(lines)
    assert recovered, "no peaks detected"
    ratio = recovered[0] / recovered[1] if recovered[1] else float("inf")
    assert 0.8 <= ratio <= 1.25, (
        "equal-area lines of different width integrated to different values "
        f"(broad/sharp = {ratio:.2f}); integration is width-dependent, so "
        "proton counts depend on linewidth rather than on how many protons "
        "are present."
    )
