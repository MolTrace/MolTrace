"""A match that any of five lines could have explained is not five-sixths of a match.

`PredictionBoundsTest` counted a matched resonance as corroboration regardless of how
many other experimental lines fell inside the same window. Measured on held-out
NMRShiftDB2, replicating the grouping the test actually uses: **26.5 % of in-window
¹³C resonances and 32.5 % of ¹H resonances have a rival line strictly closer to the
prediction than their own**, and narrowing the window cuts exposure 33 % while moving
misassignment only 2.3 pp. The ambiguity is intrinsic at this predictor's accuracy, so
it belongs in the scoring model rather than in the tolerance.

The discount is a **normalised likelihood**, not a penalty invented for the purpose:
under the same Gaussian the merit function already uses, it is the posterior that the
line the matcher chose is the right one, given the alternatives it could have chosen.
It therefore reduces to exactly 1.0 when there is nothing else in the window — which is
what makes it safe to land.

It attenuates **significance**, never score. Ambiguity is not refutation: five candidate
lines do not mean the structure is wrong, they mean the observation says little either
way. Significance is the channel the module docstring defines as "how much the verdict
should count", so this is the architecturally correct place for it.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.verification.scorer import (
    _AMBIGUITY_FLOOR,
    _ambiguity_weight,
    verify_structure,
)


# --------------------------------------------------------------------------- #
# The no-regression guarantee
# --------------------------------------------------------------------------- #
def test_a_lone_line_in_the_window_is_undiscounted() -> None:
    """The load-bearing invariant: no rivals means no change to today's behaviour."""

    assert _ambiguity_weight([0.4], chosen=0, scale_ppm=2.0) == pytest.approx(1.0)
    assert _ambiguity_weight([0.0], chosen=0, scale_ppm=2.0) == pytest.approx(1.0)


def test_the_weight_is_a_probability() -> None:
    for distances, chosen in (([0.1, 0.5], 0), ([0.0, 0.0, 0.0], 1), ([2.0, 0.3, 1.1], 1)):
        weight = _ambiguity_weight(distances, chosen=chosen, scale_ppm=2.0)
        assert 0.0 < weight <= 1.0


# --------------------------------------------------------------------------- #
# Shape
# --------------------------------------------------------------------------- #
def test_k_equidistant_candidates_give_one_over_k_until_the_floor() -> None:
    """Maximal ambiguity: the matcher's choice carries the evidence of a coin flip.

    Re-baselined when `_AMBIGUITY_FLOOR` landed: 1/k falls below the floor at k = 5,
    so from there on every equidistant set returns the floor rather than continuing
    down. That is the floor doing exactly what it is for — the extreme tail is the
    part of the curve the measurement extrapolates most.
    """

    for k in (2, 3, 4):
        assert _ambiguity_weight([1.0] * k, chosen=0, scale_ppm=2.0) == pytest.approx(1.0 / k)
    for k in (5, 8, 20):
        assert _ambiguity_weight([1.0] * k, chosen=0, scale_ppm=2.0) == pytest.approx(
            _AMBIGUITY_FLOOR
        )


def test_the_floor_is_the_measured_tenth_percentile_not_a_round_number() -> None:
    """0.20 sits between the measured p10 of 0.223 (¹³C) and 0.180 (¹H).

    Pinned so a future change has to restate the basis rather than nudge the constant.
    """

    assert _AMBIGUITY_FLOOR == 0.20


def test_the_floor_cannot_be_used_to_soften_the_discount() -> None:
    """Documented because it is the thing someone will try.

    Measured across the corpus, raising the floor to 0.50 — touching 41 % of ¹³C and
    51 % of ¹H matches — moves a fully corroborating test's posterior by only +0.012
    and +0.022. The tail carries almost none of the aggregate. Anything that
    meaningfully softens the discount must lift the whole distribution, which is a
    different decision. This test pins the mechanism: the floor never touches a
    weight already above it.
    """

    for raw_distances in ([0.0, 3.0], [0.1, 0.2], [0.0], [0.5, 0.6, 0.7]):
        weight = _ambiguity_weight(raw_distances, chosen=0, scale_ppm=1.0)
        assert weight >= _AMBIGUITY_FLOOR
        if weight > _AMBIGUITY_FLOOR:
            # Above the floor the value is the untouched normalised likelihood.
            scale = 1.0
            expected = math.exp(-0.5 * (raw_distances[0] / scale) ** 2) / sum(
                math.exp(-0.5 * (d / scale) ** 2) for d in raw_distances
            )
            assert weight == pytest.approx(expected)


def test_a_clearly_nearest_line_keeps_almost_all_its_evidence() -> None:
    """A rival far outside the scale should barely dilute a good match."""

    weight = _ambiguity_weight([0.05, 6.0], chosen=0, scale_ppm=1.0)
    assert weight > 0.98


def test_more_rivals_and_closer_rivals_both_lower_the_weight() -> None:
    base = _ambiguity_weight([0.2, 2.0], chosen=0, scale_ppm=1.0)
    more = _ambiguity_weight([0.2, 2.0, 2.0], chosen=0, scale_ppm=1.0)
    closer = _ambiguity_weight([0.2, 0.4], chosen=0, scale_ppm=1.0)
    assert more < base
    assert closer < base


def test_the_weight_is_order_independent() -> None:
    """Ambiguity is a property of the spectrum, not of the greedy matcher's order."""

    a = _ambiguity_weight([0.2, 1.0, 3.0], chosen=0, scale_ppm=1.5)
    b = _ambiguity_weight([3.0, 1.0, 0.2], chosen=2, scale_ppm=1.5)
    assert a == pytest.approx(b)


# --------------------------------------------------------------------------- #
# Refusals — never a NaN, never a zero-evidence surprise
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("scale", [0.0, -1.0, float("nan"), float("inf")])
def test_an_unusable_scale_falls_back_to_counting_the_candidates(scale: float) -> None:
    """Without a usable scale the honest discount is the uniform one, not a NaN."""

    weight = _ambiguity_weight([0.2, 0.4, 5.0], chosen=0, scale_ppm=scale)
    assert math.isfinite(weight)
    assert weight == pytest.approx(max(_AMBIGUITY_FLOOR, 1.0 / 3.0))


def test_degenerate_inputs_do_not_produce_nan_or_zero() -> None:
    for distances, chosen in (([], 0), ([float("nan")], 0), ([1e9, 1e9], 0)):
        weight = _ambiguity_weight(distances, chosen=chosen, scale_ppm=1.0)
        assert math.isfinite(weight)
        assert 0.0 < weight <= 1.0


# --------------------------------------------------------------------------- #
# End to end
# --------------------------------------------------------------------------- #
def _spectrum(centers: tuple[float, ...], width: float = 0.05, npts: int = 24000) -> NMRSpectrum:
    """A ¹³C spectrum. ¹³C is used because its 4.0 ppm match window has room for several
    *resolved* lines; at ¹H's 0.30 ppm the rivals merge into one multiplet unit and there
    is no ambiguity to measure."""

    ppm = np.linspace(200.0, 0.0, npts)
    data = np.zeros_like(ppm)
    for c in centers:
        data = data + (width**2) / ((ppm - c) ** 2 + width**2)
    return NMRSpectrum(data=data, ppm_axis=ppm, nucleus="13C", solvent="CDCl3", field_mhz=100.0)


def test_a_crowded_spectrum_scores_the_same_match_as_weaker_evidence() -> None:
    """Same structure, same match — but surrounded by lines it could equally have taken."""

    clean = verify_structure(
        _spectrum((128.5,)), "c1ccccc1", prior_confidence=0.5, tests=["prediction_bounds"]
    )
    crowded = verify_structure(
        _spectrum((128.5, 126.5, 130.5, 125.5, 131.5)),
        "c1ccccc1",
        prior_confidence=0.5,
        tests=["prediction_bounds"],
    )
    clean_test = clean.test_results[0]
    crowded_test = crowded.test_results[0]

    assert crowded_test.significance < clean_test.significance, (
        "a match among five candidate lines carried the same weight as an unambiguous one"
    )
    # Ambiguity attenuates; it does not refute.
    assert crowded_test.score == pytest.approx(clean_test.score)
    assert crowded.posterior_confidence < clean.posterior_confidence
    assert crowded.posterior_confidence > 0.5


def test_the_discount_is_recorded_for_audit() -> None:
    result = verify_structure(
        _spectrum((128.5, 126.5, 130.5)),
        "c1ccccc1",
        prior_confidence=0.5,
        tests=["prediction_bounds"],
    )
    details = result.test_results[0].details
    assert "mean_ambiguity_weight" in details
    assert 0.0 < details["mean_ambiguity_weight"] <= 1.0
    matched = [row for row in details["resonances"] if row.get("matched")]
    assert matched and all("ambiguity_weight" in row for row in matched)
