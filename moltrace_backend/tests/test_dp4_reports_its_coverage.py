"""A DP4 row must say how much of the spectrum it actually explains.

`dp4_probabilities` pairs predicted to observed peaks within a window (±0.3 ppm
for 1H) and computes ``mean_abs_error_ppm`` / ``rms_error_ppm`` over **the pairs
that survived**. Peaks the prediction missed by more than the window are dropped
from the error statistics entirely.

The result is an error figure that stops responding to error. Measured on twelve
well-separated 1H shifts, one candidate, observed = truth + N(0, err):

    true RMSE   0.140  ->  reported  0.118   matched 11/12
    true RMSE   0.540  ->  reported  0.203   matched  8/12
    true RMSE   1.068  ->  reported  0.151   matched  6/12
    true RMSE   1.402  ->  reported  0.164   matched  7/12
    true RMSE   2.418  ->  reported  0.154   matched  6/12

A seventeen-fold degradation in the real fit moves the reported number from 0.118
to 0.154. A chemist reading "RMS error 0.15 ppm" concludes the candidate fits;
the only thing that actually moved was the matched count, and the row emitted
``matched_peaks`` with **no denominator**, so 6 was indistinguishable from 6 of 6.

The likelihood itself is not blind here -- unmatched peaks take a soft
`log(0.5)` penalty, so the *ranking* is defensible. This is a reporting defect,
not a scoring one, which is why the fix adds coverage and labels rather than
touching the arithmetic.

Separately and independently: the σ/ν are Smith & Goodman's DFT/GIAO residuals
(1H σ=0.185, ν=14.18) while production predicts shifts with an empirical RDKit
atom-environment model whose measured error on real paired spectra is 2.25x σ
censored / 7.72x σ uncensored. The posterior is therefore a *relative ranking*,
not a calibrated probability, and must not be presented as the published DP4
number. No σ is invented here to fix that -- the true value is bracketed, not
pinned, and picking one would be the round-number guess this codebase has been
bitten by before.
"""

from __future__ import annotations

import math
import random

import pytest

from nmrcheck.dp4_scoring import dp4_probabilities
from nmrcheck.peak_categorization import build_dp4_candidate_ranking


def _shifts(n: int = 12) -> list[float]:
    return [1.0 + 0.6 * i for i in range(n)]


def _observed(truth: list[float], err: float, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [t + rng.gauss(0, err) for t in truth]


class TestTheErrorFigureCarriesItsCoverage:
    def test_a_row_reports_how_many_peaks_it_could_have_matched(self) -> None:
        """`matched_peaks` without a denominator cannot be read."""
        truth = _shifts()
        observed = _observed(truth, 1.5, seed=3)
        rows = build_dp4_candidate_ranking(
            observed_peaks=[{"shift_ppm": s} for s in observed],
            candidate_predicted=[[_FakePeak(s) for s in truth]],
            candidate_labels=["candidate"],
            nucleus="1H",
        )
        assert rows, "no ranking produced"
        row = rows[0]
        assert "observed_peak_count" in row, (
            "the row reports matched_peaks with nothing to compare it against"
        )
        assert row["observed_peak_count"] == len(observed)
        assert 0.0 <= row["matched_fraction"] <= 1.0
        assert row["matched_fraction"] == pytest.approx(
            row["matched_peaks"] / row["observed_peak_count"]
        )

    def test_the_error_says_it_covers_only_the_matched_peaks(self) -> None:
        truth = _shifts()
        rows = build_dp4_candidate_ranking(
            observed_peaks=[{"shift_ppm": s} for s in _observed(truth, 1.5, seed=4)],
            candidate_predicted=[[_FakePeak(s) for s in truth]],
            candidate_labels=["candidate"],
            nucleus="1H",
        )
        assert rows[0]["error_basis"] == "matched_peaks_only", (
            "the error statistics do not declare what they are computed over"
        )

    def test_a_badly_fitting_candidate_is_flagged_not_flattered(self) -> None:
        """The measured case: a 2.4 ppm misfit reporting 0.15 ppm.

        The reported RMSE is allowed to stay small -- that is what it means --
        but the row must not let that number stand alone as the verdict.
        """
        truth = _shifts()
        rows = build_dp4_candidate_ranking(
            observed_peaks=[{"shift_ppm": s} for s in _observed(truth, 2.0, seed=5)],
            candidate_predicted=[[_FakePeak(s) for s in truth]],
            candidate_labels=["candidate"],
            nucleus="1H",
        )
        row = rows[0]
        assert row["matched_fraction"] < 0.75, "the fixture did not produce a poor fit"
        blob = " ".join(row["notes"]).lower()
        assert "unmatched" in blob or "coverage" in blob, (
            f"a poorly-covered fit carried no warning: {row['notes']}"
        )
        assert row.get("low_coverage") is True, (
            "nothing on the row marks it as a fit that explains little of the spectrum"
        )

    def test_a_good_fit_is_not_flagged(self) -> None:
        """The flag must be a measurement, not a banner on every row."""
        truth = _shifts()
        rows = build_dp4_candidate_ranking(
            observed_peaks=[{"shift_ppm": s} for s in _observed(truth, 0.03, seed=6)],
            candidate_predicted=[[_FakePeak(s) for s in truth]],
            candidate_labels=["candidate"],
            nucleus="1H",
        )
        row = rows[0]
        assert row["matched_fraction"] == 1.0
        assert row.get("low_coverage") is False


class TestTheProbabilityDoesNotClaimToBeCalibrated:
    def test_each_row_declares_its_calibration_state(self) -> None:
        truth = _shifts()
        rows = build_dp4_candidate_ranking(
            observed_peaks=[{"shift_ppm": s} for s in _observed(truth, 0.1, seed=7)],
            candidate_predicted=[[_FakePeak(s) for s in truth]],
            candidate_labels=["candidate"],
            nucleus="1H",
        )
        row = rows[0]
        assert row["probability_is_calibrated"] is False, (
            "the row presents its probability as a calibrated DP4 posterior"
        )
        assert row["probability_basis"], "nothing says what the number actually is"

    def test_the_ranking_still_ranks(self) -> None:
        """Uncalibrated is not useless. The ordering is the product.

        The correct candidate must still come first -- if withdrawing the
        calibration claim also broke the ranking there would be nothing left to
        ship, and the honest move would be to remove the feature instead.
        """
        truth = _shifts()
        wrong = [t + 0.9 for t in truth]
        rows = build_dp4_candidate_ranking(
            observed_peaks=[{"shift_ppm": s} for s in _observed(truth, 0.08, seed=8)],
            candidate_predicted=[
                [_FakePeak(s) for s in wrong],
                [_FakePeak(s) for s in truth],
            ],
            candidate_labels=["wrong", "right"],
            nucleus="1H",
        )
        assert rows[0]["candidate_label"] == "right", (
            f"the ranking no longer identifies the correct candidate: {rows}"
        )


def test_the_censoring_this_guards_against_is_real() -> None:
    """Pins the measurement the change is built on, so it cannot silently drift.

    If the pairing window or the error basis ever changes, this is the test that
    should fail first -- it asserts the *gap* between the true error and the
    reported one, which is the whole reason coverage has to be reported.
    """
    truth = _shifts()
    observed = _observed(truth, 2.0, seed=9)
    true_rmse = math.sqrt(
        sum((o - t) ** 2 for o, t in zip(observed, truth, strict=True)) / len(truth)
    )
    score = dp4_probabilities(
        observed_shifts_ppm=observed,
        candidate_predicted_shifts_ppm=[truth],
        nucleus="1H",
    )[0]

    assert true_rmse > 1.0, "the fixture is not a misfit"
    assert score.rms_error_ppm < true_rmse / 4, (
        "the reported error no longer understates the real one -- if the pairing "
        "or error basis changed deliberately, re-baseline this test and the "
        "coverage reporting it justifies"
    )


class _FakePeak:
    """Minimal stand-in for PredictedNMRPeak: the builder reads two attributes."""

    def __init__(self, shift_ppm: float, nucleus: str = "1H") -> None:
        self.shift_ppm = shift_ppm
        self.nucleus = nucleus
