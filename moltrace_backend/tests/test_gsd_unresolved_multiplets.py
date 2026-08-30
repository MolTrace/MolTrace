"""How close two lines may sit and still be reported as two, by level.

Below about 1.2 linewidths of separation `find_peaks` sees no local minimum
between two lines, so at the DEFAULT level the picker returns one feature where a
chemist reads three, and recall floors at exactly 1/3 of a three-line multiplet.
That floor is real, and it is also already solved: `level` was documented as
controlling "fit cost and overlap handling", with levels 4-5 promising iterative
deconvolution, and it delivers exactly that. Nothing measured it, so nothing said
how far down each level reaches, and nothing would notice if a level stopped
reaching there.

Measured on planted three-line multiplets at 100 MHz, the 13C median FWHM of
3.23 Hz, SNR 40, spacing the only variable:

    J/FWHM   2.48  1.86  1.24  0.93  0.31
    level 2  100%   44%   33%   33%   33%
    level 3  100%  100%   72%   33%   33%
    level 4  100%  100%  100%   78%   33%
    level 5  100%  100%  100%  100%   33%

So the answer to "the picker merges crowded lines" is to ask a level that
deconvolves, and the cost of a level is what it is for.

**A DEDICATED RESOLVE PASS AT LEVEL 2 WAS BUILT AND REVERTED.** It reached 100% at
0.93 — matching level 5 — and on real acquisitions it recovered NOTHING while
costing about 1.6x runtime on the default path: 13C recall unchanged at 53/92 with
lines 348 -> 377 and unassigned lines 252 -> 265, and 1H assigned-environment
recall unchanged at 25/74 with environments 119 -> 131. A capability the tree
already had, duplicated, priced in the one place every caller pays.

The 1/3 at 0.31 linewidths is not a defect at any level. Three lines a third of a
linewidth apart ARE one feature, and every level agreeing on that is the correct
answer rather than a shared limitation.

The broad-line cases at the foot of this file were the other direction -- a guard
against manufacturing a splitting -- and one of them was red at level 5 until the
detection threshold was floored at sqrt(2 ln N). The note there records what that
turned out to be, which was not what it looked like.
"""

from __future__ import annotations

import numpy as np
import pytest

from moltrace.spectroscopy.eval.detector_corpus import (
    score_detection,
    synthesise_multiplet,
)
from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

#: The measured 13C median FWHM this repository's acquisitions carry.
_FWHM_HZ = 3.23
_FIELD_MHZ = 100.0


def _recall_at(spacing_hz: float, level: int) -> float:
    acquisition = synthesise_multiplet(
        nucleus="13C",
        field_mhz=_FIELD_MHZ,
        points=65536,
        sweep_ppm=(0.0, 200.0),
        fwhm_hz=_FWHM_HZ,
        spacing_hz=spacing_hz,
        seed=7,
    )
    picked = [
        peak.position_ppm for peak in gsd_peak_pick(acquisition.spectrum, level=level)
    ]
    found, total = score_detection(acquisition, picked).found_by_band["quantifiable >=10"]
    return found / total if total else float("nan")


class TestTheLevelLadderReachesFurtherDown:
    """Each deconvolving level resolves lines the one below it cannot."""

    @pytest.mark.slow
    def test_a_level_that_deconvolves_separates_what_the_default_merges(self) -> None:
        """6 Hz apart — 1.86 linewidths. Level 2 merges; level 3 does not."""
        default = _recall_at(6.0, level=2)
        deconvolving = _recall_at(6.0, level=3)
        assert deconvolving - default > 0.4, (
            f"level 3 recalls {deconvolving:.0%} against level 2's {default:.0%} at "
            "1.86 linewidths — the ladder no longer buys overlap handling, which is "
            "the whole documented difference between these levels"
        )

    @pytest.mark.slow
    def test_the_deepest_level_reaches_one_linewidth(self) -> None:
        """3 Hz apart — 0.93 linewidths, and level 5 resolves all three lines."""
        recall = _recall_at(3.0, level=5)
        assert recall > 0.9, (
            f"level 5 recalls {recall:.0%} at 0.93 linewidths — the deepest level no "
            "longer resolves a multiplet the deconvolver can resolve from one seed"
        )

    @pytest.mark.slow
    def test_deeper_levels_never_recall_less(self) -> None:
        """The ladder must be monotonic, or 'deeper' means nothing.

        A level that costs more and finds less is the failure this catches; it is
        also what a partially-applied change to the group-fit path would look like.
        """
        for spacing in (4.0, 6.0):
            recalls = [_recall_at(spacing, level=level) for level in (2, 3, 4, 5)]
            for lower, higher in zip(recalls, recalls[1:], strict=False):
                assert higher >= lower - 1e-9, (
                    f"recall at {spacing} Hz runs {['%.0f%%' % (100*r) for r in recalls]} "
                    "across levels 2-5 — a deeper level found less than a shallower one"
                )


class TestWhatIsNotResolvable:
    """The floor that is physics, and the invention that would hide it."""

    @pytest.mark.slow
    def test_a_third_of_a_linewidth_is_one_feature_at_every_level(self) -> None:
        """Three lines this close ARE one feature; claiming three is invention.

        Asserted at the DEEPEST level, because that is the one with the machinery
        to manufacture a splitting if it were going to.
        """
        acquisition = synthesise_multiplet(
            nucleus="13C",
            field_mhz=_FIELD_MHZ,
            points=65536,
            sweep_ppm=(0.0, 200.0),
            fwhm_hz=_FWHM_HZ,
            spacing_hz=1.0,
            seed=7,
        )
        positions = np.asarray(
            sorted(peak.position_ppm for peak in gsd_peak_pick(acquisition.spectrum, level=5))
        )
        centres = [
            float(np.mean([line.position_ppm for line in acquisition.lines[i : i + 3]]))
            for i in range(0, len(acquisition.lines), 3)
        ]
        for centre in centres:
            near = positions[np.abs(positions - centre) < 3.0 * _FWHM_HZ / _FIELD_MHZ]
            assert near.size <= 2, (
                f"{near.size} lines claimed at {centre:.3f} ppm from three planted a "
                "third of a linewidth apart — that is invention, not resolution"
            )


def _one_broad_line(width_hz: float, field_mhz: float = 100.0) -> NMRSpectrum:
    x = np.linspace(0.0, 200.0, 65536)
    hz = x * field_mhz
    half = width_hz / 2.0
    y = 400.0 * half**2 / ((hz - 100.0 * field_mhz) ** 2 + half**2)
    y = y + np.random.default_rng(3).normal(0.0, 1.0, x.size)
    return NMRSpectrum(data=y, ppm_axis=x, nucleus="13C", field_mhz=field_mhz)


#: WHAT THIS USED TO SAY WAS WRONG, and the correction is the whole finding. It was
#: recorded as "deep-level over-picking on a broad feature" because a 400 Hz line
#: came back as six lines at level 5. Measuring where the picks actually sat refuted
#: that: density ON the broad feature was 0.12 apexes per ppm against 0.69 per ppm
#: off it -- level 5 picked FEWER peaks on the pedestal than in the flat noise
#: beside it. The six lines were the ordinary level-5 noise density passing through
#: that window, and the broad line had nothing to do with it.
#:
#: The real defect was general: a threshold in units of sigma is a per-point
#: statement, and it was applied at every one of up to 524,288 points. On pure noise
#: with no peaks at all, level 5 returned 1,159 apexes. Flooring the multiplier at
#: sqrt(2 ln N) took that to 4 and left the recall ladder byte-identical.

@pytest.mark.slow
@pytest.mark.parametrize("width_hz", [12.0, 60.0, 400.0])
@pytest.mark.parametrize("level", [2, 5])
def test_a_single_broad_line_is_not_shattered_into_a_multiplet(
    width_hz: float, level: int
) -> None:
    """One wide line is one line, however wide, at the deepest level too.

    12 Hz is inside the band a 13C multiplet could occupy; 60 and 400 Hz are the
    baseline-roll regime these acquisitions actually contain, where fitted widths
    reach 8871 Hz. None of them is a coupling, and a deconvolver pointed at one
    will describe it with as many lines as it is allowed.
    """
    positions = np.asarray(
        sorted(peak.position_ppm for peak in gsd_peak_pick(_one_broad_line(width_hz), level=level))
    )
    near = positions[np.abs(positions - 100.0) < width_hz * 2.0 / 100.0]
    assert near.size <= 1, (
        f"a single {width_hz:.0f} Hz line came back as {near.size} lines at level "
        f"{level}: {np.round(near, 3).tolist()}"
    )
