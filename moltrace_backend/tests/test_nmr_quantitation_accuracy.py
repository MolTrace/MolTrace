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
from dataclasses import dataclass

import pytest

from nmrcheck.spectrum import (
    _estimates_to_peaks,
    _infer_peak_estimates,
    _PeakEstimate,
    _provisional_integrations,
    _normalize_integrations_to_target,
    _round_half_integrations,
)

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


# ---------------------------------------------------------------------------
# Integration SCALE.
#
# The tests above check that fitted areas are recovered from a lineshape. These
# check what the pipeline then does with those areas, which is a separate thing
# and was separately wrong.
#
# `_provisional_integrations` used to set its reference to
# ``max(min(basis), max(basis) * 0.08)``. The floor took over whenever a
# spectrum's dynamic range exceeded 12.5 — i.e. for any molecule with a large
# multiplet — and pinned the largest peak at exactly 1/0.08 = 12.5 H, which
# ``_round_half_integrations`` then clipped to 12.0. Measured on a real 500 MHz
# spectrum of a protected sugar: a multiplet of ~37 protons reported 12.0 H,
# and the reported largest/smallest ratio was 24.0 against a true fitted-area
# ratio of 41.6 — a 42% error in a quantity that is supposed to be a proton
# count.
#
# The invariant asserted here is scale-free on purpose. An absolute proton
# count cannot be recovered from one spectrum without an anchor (a structure or
# an internal standard), so these do not assert absolute values. What must hold
# regardless of the anchor is that RATIOS between reported integrations equal
# ratios between fitted areas.
# ---------------------------------------------------------------------------

@dataclass
class _Area:
    """Minimal stand-in for _PeakEstimate: only `area` is read by the scaler."""

    area: float
    shift_ppm: float = 5.0


def _reported(areas: list[float]) -> list[float]:
    ests = [_Area(a) for a in areas]
    return _round_half_integrations(_provisional_integrations(ests), minimum=0.5)


@pytest.mark.parametrize("largest", [5, 10, 13, 20, 37, 63, 120])
def test_large_multiplets_are_not_all_reported_as_the_same_value(largest: int) -> None:
    """A 13, 37 and 120 proton multiplet must not all report 12.00 H.

    Under the old 8% reference floor they did: every one of them came back as
    exactly 12.00, because the value was a constant of the algorithm rather
    than a measurement of the spectrum.
    """
    reported = _reported([1.0, 2.0, float(largest)])

    assert reported[-1] == pytest.approx(largest, rel=0.05), (
        f"a {largest} H multiplet reported {reported[-1]} H"
    )


def test_distinct_small_signals_do_not_collapse_onto_one_value() -> None:
    """1 H, 2 H and 3 H must stay distinguishable next to a large envelope.

    The old reference floor scaled by the LARGEST peak, so in a molecule with a
    63 H envelope (three TIPS groups) a 1 H, a 2 H and a 3 H signal all landed
    on 0.5 H — three different proton counts rendered as one number.
    """
    reported = _reported([1.0, 2.0, 3.0, 63.0])

    assert len(set(reported[:3])) == 3, f"1/2/3 H collapsed onto {reported[:3]}"
    assert reported[0] < reported[1] < reported[2]


@pytest.mark.parametrize("dynamic_range", [3.0, 12.0, 12.6, 41.6, 100.0])
def test_reported_ratios_track_fitted_area_ratios(dynamic_range: float) -> None:
    """The scale-free invariant: reported ratio == area ratio.

    12.6 and above are the cases the old floor broke; 41.6 is the ratio
    measured on the real protected-sugar spectrum, where the old pipeline
    reported 24.0.
    """
    areas = [1.0, dynamic_range / 2.0, dynamic_range]
    reported = _reported(areas)

    assert reported[-1] / reported[0] == pytest.approx(dynamic_range, rel=0.08)


def test_reference_is_not_pinned_to_a_fraction_of_the_largest_peak() -> None:
    """Doubling only the largest peak must not rescale the others.

    Under the 8% floor the reference was derived from the maximum, so growing
    the largest peak shrank every other reported integration — a change in one
    resonance silently rewrote the rest of the spectrum.
    """
    base = _reported([1.0, 2.0, 4.0, 30.0])
    grown = _reported([1.0, 2.0, 4.0, 60.0])

    assert base[:3] == grown[:3], (
        f"growing the largest peak rewrote the others: {base[:3]} -> {grown[:3]}"
    )


def test_a_lone_proton_beside_a_large_envelope_is_not_discarded_as_noise() -> None:
    """A 1 H signal in a molecule with a 63 H envelope must survive.

    The noise test used to be written on the provisional integrations
    (``value >= 0.25``), which under the old reference floor worked out to
    "area is at least 2% of the largest peak". That threshold is defined by the
    biggest multiplet, so the larger the molecule the more real protons it
    deleted: beside three TIPS groups a lone proton is 1.6% of the maximum and
    was thrown away as noise. The criterion is now on area alone, sited inside
    a measured gap between the noise and signal populations.
    """
    def est(shift: float, area: float) -> _PeakEstimate:
        return _PeakEstimate(
            shift_ppm=shift, area=area, intensity=area, multiplicity="s",
            width_ppm=0.01, component_count=1, j_values_hz=(),
        )

    estimates = [
        est(7.30, 63.0),   # the TIPS envelope
        est(5.20, 1.0),    # a lone proton: 1.6% of the largest area
        est(4.10, 2.0),
        est(3.90, 0.05),   # genuine noise: 0.08% of the largest area
    ]
    peaks, meta = _estimates_to_peaks(estimates, solvent="CDCl3", nucleus="1H")

    shifts = [p.shift_ppm for p in peaks]
    assert 5.20 in shifts, f"the lone proton was dropped as noise; kept {shifts}"
    assert 3.90 not in shifts, f"noise was kept as a peak; kept {shifts}"
    assert meta["noise_peaks_dropped"] == 1


# ---------------------------------------------------------------------------
# Integration ALLOCATION.
#
# The scale tests above ask what number a peak's area becomes. These ask a
# different question that was separately wrong: how the fixed proton budget of
# a known structure gets DIVIDED among the detected peaks.
#
# `_normalize_integrations_to_target` used to allocate with a per-peak floor::
#
#     scaled_units = [max(1.0, value / total * target_units) for value in values]
#     base_units   = [max(1, int(math.floor(value))) for value in scaled_units]
#
# so every detected maximum was guaranteed at least one half-proton unit no
# matter how little signal it carried. Measured on nmrshiftdb2 spectrum
# 40255417 (allyl glycidyl ether, C6H10O2, 10 H, 15 detected peaks against a
# budget of 20 half-proton units): seven peaks carried 6.3% of the signal
# between them and the floor awarded them 35% of the molecule -- 5.6x -- while
# consuming 5.75 of the 20 units that belonged to the peaks that did carry
# signal. The reported total was exactly 10.00 H, which looked like a perfect
# result and was in fact 55% quantiser output.
#
# The invariant: a reported proton count is a MEASUREMENT, so a peak's share of
# the protons must track its share of the signal. A peak carrying a fraction of
# a percent of the integral is noise or an impurity, and the honest report is
# to drop it and say so -- never to promote it to half a proton.
# ---------------------------------------------------------------------------

#: The real area list from nmrshiftdb2 spectrum 40255417, largest first.
_SPECTRUM_40255417_AREAS = [
    128.7102, 100.0468, 90.1796, 88.7092, 72.7462, 70.7444,
    40.2768, 39.4886, 27.7171, 5.8135, 2.7000, 1.7964, 1.6344, 1.4303, 1.0000,
]


def test_noise_peaks_are_not_awarded_protons_they_did_not_carry() -> None:
    """The defect that made a 10.00 H total 55% fabrication."""
    areas = _SPECTRUM_40255417_AREAS
    total_area = sum(areas)
    allocated = _normalize_integrations_to_target(areas, 10.0)
    assert allocated is not None
    assert sum(allocated) == pytest.approx(10.0), "the structural budget must be honoured"

    # Peaks carrying under 1% of the signal each -- unambiguously not protons.
    noise = [got for area, got in zip(areas, allocated) if area / total_area < 0.01]
    assert len(noise) == 6, "fixture drifted; re-derive the areas"
    true_share = sum(a for a in areas if a / total_area < 0.01) / total_area
    got_share = sum(noise) / sum(allocated)
    assert got_share <= 2.0 * true_share, (
        f"peaks carrying {true_share:.1%} of the signal were awarded "
        f"{got_share:.1%} of the protons ({got_share / max(true_share, 1e-9):.1f}x). "
        "A proton count must be measured, not allocated."
    )


def test_a_peak_carrying_no_measurable_signal_gets_no_protons() -> None:
    """One dominant resonance plus detector noise: the noise gets zero, not 0.5 H."""
    allocated = _normalize_integrations_to_target([500.0, 480.0, 1.0, 0.8, 0.5], 4.0)
    assert allocated is not None
    assert sum(allocated) == pytest.approx(4.0)
    assert allocated[-3:] == [0.0, 0.0, 0.0], (
        f"noise peaks were awarded {allocated[-3:]} H rather than nothing"
    )
    assert allocated[0] > 0 and allocated[1] > 0


def test_allocation_still_tracks_signal_when_every_peak_is_real() -> None:
    """The fix must not disturb a clean spectrum: 1:2:3 areas -> 1:2:3 protons."""
    allocated = _normalize_integrations_to_target([10.0, 20.0, 30.0], 6.0)
    assert allocated == [1.0, 2.0, 3.0]


def test_more_peaks_than_protons_no_longer_abandons_the_structural_budget() -> None:
    """Previously refused (returned None) and fell back to the floored path.

    That routed exactly the most over-picked spectra -- the ones where the floor
    does the most damage -- into the code that applies it.
    """
    allocated = _normalize_integrations_to_target([100.0, 90.0] + [0.5] * 20, 2.0)
    assert allocated is not None
    assert sum(allocated) == pytest.approx(2.0)
    assert all(value == 0.0 for value in allocated[2:])
