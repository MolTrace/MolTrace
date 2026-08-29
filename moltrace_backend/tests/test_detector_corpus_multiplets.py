"""Recall against planted multiplets, where spacing is the only variable.

Two measurements on the real corpus pointed at line separation as where the
detector loses lines: recall against the curated carbon shifts correlates -0.729
with a molecule's assigned-carbon count (93% mean recall at <=6 carbons against
42% above), and a survey of fitted-centre drift found the band immediately below
the half-gap cut empty. Neither could be tested on the planted corpus, because
every existing planted line sat further apart than the gap they implicate.

The real corpus cannot settle it either: 13 13C acquisitions exist on disk and 12
already carry curated shifts, so n=12 is the whole corpus and cannot grow. The
only way left to test a causal claim is to vary the suspected cause directly,
which is what these do.
"""

from __future__ import annotations

import pytest

from moltrace.spectroscopy.eval.detector_corpus import (
    score_detection,
    synthesise_multiplet,
)
from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

#: Measured 13C median linewidth, from the table in detector_corpus.
_FWHM_HZ = 3.23


def _recall_at(spacing_hz: float) -> float:
    acquisition = synthesise_multiplet(
        nucleus="13C",
        field_mhz=100.0,
        points=65536,
        sweep_ppm=(0.0, 200.0),
        fwhm_hz=_FWHM_HZ,
        spacing_hz=spacing_hz,
        seed=7,
    )
    picked = [peak.position_ppm for peak in gsd_peak_pick(acquisition.spectrum, level=2)]
    return score_detection(acquisition, picked).recall("quantifiable >=10")


class TestOnePickSatisfiesOneLine:
    """The scorer must not credit one merged peak to several planted lines.

    Each planted line used to take its own nearest pick, so below about one
    linewidth of separation — where the detector returns a single merged peak per
    multiplet — recall scored 100% against a truth of 33%. That is a 3x
    overstatement in precisely the regime this corpus exists to probe, and it
    would have made the spacing sweep below report a clean bill of health.
    """

    @pytest.mark.slow
    def test_merged_lines_are_not_counted_three_times(self) -> None:
        # 1.0 Hz against a 3.23 Hz linewidth: three lines inside one linewidth.
        recall = _recall_at(1.0)
        assert recall < 0.5, (
            f"recall {recall:.0%} on lines closer together than the linewidth — "
            "a merged peak is being credited to every line under it"
        )


class TestRecallDegradesWithLineSpacing:
    """The crowding hypothesis, tested where spacing is the only thing varied."""

    @pytest.mark.slow
    def test_well_separated_multiplets_are_fully_recovered(self) -> None:
        """3.7 linewidths apart: the genuinely easy case.

        Kept separate from the 2.48-linewidth case below, which shares none of
        its cause. A failure here is the peak picker losing lines that are not
        close to anything.
        """
        assert _recall_at(12.0) == pytest.approx(1.0)

    @pytest.mark.slow
    def test_lines_two_and_a_half_linewidths_apart_survive_the_fitter(self) -> None:
        """8.0 Hz at the measured 13C FWHM of 3.23 Hz is 2.48 linewidths, and it
        is NOT an easy case — it recalls 100% only because of the own-line
        judgement in ``gsd._fit_single_peak`` (13f9629). Measured with that
        judgement disabled and nothing else changed:

            J/FWHM   4.95  3.72  2.48  1.86  1.24
            with     100%  100%  100%   44%   33%
            without  100%  100%   56%   33%   33%

        So this assertion is what pins that fix. It sat under a name promising
        "well separated multiplets", which would have sent whoever saw it go red
        to read the peak picker; the cause is one line at a time in the fitter —
        a fitted centre free to walk onto its neighbour, then deduplicated away
        as a duplicate of the line it became. Same merged output as the picker
        produces below ~1.2 linewidths, entirely different code, so the name has
        to separate them.

        Reading it against its neighbours: red here with 12.0 Hz green is the
        fitter; red at 12.0 too is the picker; the 1/3 floor below is the picker
        and the fitter cannot reach it.
        """
        assert _recall_at(8.0) == pytest.approx(1.0)

    @pytest.mark.slow
    def test_recall_collapses_once_lines_close_to_within_two_linewidths(self) -> None:
        wide = _recall_at(8.0)
        tight = _recall_at(4.0)
        assert wide - tight > 0.5, (
            f"recall {wide:.0%} at 2.5 linewidths against {tight:.0%} at 1.2 — "
            "spacing is the only variable between these two acquisitions"
        )

    @pytest.mark.slow
    def test_the_floor_is_one_line_per_multiplet(self) -> None:
        """Three equal lines merging into one peak floors recall at 1/3.

        Pinned because it says WHAT the detector does when it fails here — it
        returns the multiplet as a single feature rather than dropping it — which
        is a different defect from a threshold rejecting a weak line.
        """
        assert _recall_at(1.5) == pytest.approx(1 / 3, abs=0.05)
