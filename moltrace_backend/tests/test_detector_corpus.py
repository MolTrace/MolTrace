"""The synthetic corpus the peak detector can actually be calibrated against.

The corpus it was tuned on holds decimated traces — a median 1.5 points per
linewidth against 29.4 for an acquisition read off an instrument. Over-picking
cannot appear in data carrying barely one point per line, so that corpus was
structurally incapable of showing it.

These tests guard the corpus itself: that it spans the resolutions the old one
lacked, that its ground truth is really ground truth, and that scoring against it
is arithmetic rather than opinion.
"""

from __future__ import annotations

import numpy as np
import pytest

from moltrace.spectroscopy.eval.detector_corpus import (
    BANDS,
    SNR_LADDER,
    default_corpus,
    points_per_linewidth,
    score_detection,
    synthesise,
)


def test_the_corpus_spans_the_resolutions_the_old_one_could_not_reach() -> None:
    """The whole point. A corpus that is all decimated cannot show over-picking."""
    densities = [points_per_linewidth(a) for a in default_corpus()]
    assert min(densities) < 4, "nothing coarse enough to represent the old corpus"
    assert max(densities) > 50, (
        "nothing at instrument resolution — this is the axis the old corpus lacked"
    )


def test_a_planted_line_is_really_where_it_says_it_is() -> None:
    """Ground truth has to be true, or every number measured against it is noise."""
    acquisition = synthesise(
        nucleus="13C", field_mhz=100.0, points=65536, sweep_ppm=(200.0, -10.0),
        snrs=[500.0], fwhm_hz=3.23, seed=1,
    )
    x = np.asarray(acquisition.spectrum.ppm_axis, dtype=float)
    y = np.asarray(acquisition.spectrum.data, dtype=float)
    apex_ppm = float(x[int(np.argmax(y))])
    planted = acquisition.lines[0]
    # Within a linewidth: the apex of a Lorentzian in noise is where it was put.
    assert abs(apex_ppm - planted.position_ppm) <= planted.fwhm_hz / 100.0


def test_a_planted_snr_is_really_that_snr() -> None:
    """The height is measured in noise sigmas, so the noise has to be that wide."""
    acquisition = synthesise(
        nucleus="13C", field_mhz=100.0, points=65536, sweep_ppm=(200.0, -10.0),
        snrs=[100.0], fwhm_hz=3.23, noise_sigma=2.0, seed=2,
    )
    y = np.asarray(acquisition.spectrum.data, dtype=float)
    measured = float(y.max() - np.median(y)) / acquisition.noise_sigma
    assert measured == pytest.approx(100.0, rel=0.15), (
        f"a line planted at 100 sigma measures {measured:.1f}"
    )


def test_the_ladder_spans_the_decision_the_detector_makes() -> None:
    """Below 3 sigma should not be found; above 10 must be. A ladder that does not
    straddle both is a ladder that cannot fail a detector."""
    assert min(SNR_LADDER) < 3.0
    assert max(SNR_LADDER) > 1000.0
    assert any(3.0 <= s < 10.0 for s in SNR_LADDER), "nothing in the detectable-but-not-quantifiable band"


def test_scoring_counts_what_was_found_and_what_was_invented() -> None:
    acquisition = synthesise(
        nucleus="13C", field_mhz=100.0, points=32768, sweep_ppm=(200.0, -10.0),
        snrs=[50.0, 500.0], fwhm_hz=3.23, seed=3,
    )
    exact = [line.position_ppm for line in acquisition.lines]
    perfect = score_detection(acquisition, exact)
    assert perfect.false_positives == 0
    assert perfect.found_by_band["quantifiable >=10"] == (2, 2)

    # An invented peak is counted as invented.
    with_junk = score_detection(acquisition, [*exact, 123.456])
    assert with_junk.false_positives == 1

    # And a miss is counted as a miss.
    missing = score_detection(acquisition, exact[:1])
    assert missing.found_by_band["quantifiable >=10"] == (1, 2)


def test_the_bands_are_the_ones_this_platform_reasons_in() -> None:
    """Detection and quantitation are different claims, and the bands say so."""
    names = [name for name, _, _ in BANDS]
    assert any("<3" in n for n in names)
    assert any("3-10" in n for n in names)
    assert any(">=10" in n for n in names)
