"""Unit tests for the DP4 scoring module."""

from __future__ import annotations

import math

import pytest

from nmrcheck.dp4_scoring import (
    DP4_NU_13C,
    DP4_NU_1H,
    DP4_SIGMA_13C,
    DP4_SIGMA_1H,
    _student_t_cdf,
    dp4_probabilities,
    pair_residual_dp4_score,
)


class TestStudentTCdf:
    def test_zero_is_centred(self) -> None:
        # Two-tailed CDF at t=0 is 0 (no tail beyond 0).
        assert _student_t_cdf(0.0, 14.18) == pytest.approx(0.0, abs=1e-6)

    def test_large_t_approaches_one(self) -> None:
        assert _student_t_cdf(50.0, 11.0) == pytest.approx(1.0, abs=1e-4)

    def test_symmetric_in_t(self) -> None:
        assert _student_t_cdf(1.5, 12.0) == _student_t_cdf(-1.5, 12.0)

    def test_higher_dof_narrower(self) -> None:
        # Higher DoF concentrates the mass → larger CDF at a fixed |t|.
        low_dof = _student_t_cdf(1.0, 2.0)
        high_dof = _student_t_cdf(1.0, 100.0)
        assert high_dof > low_dof


class TestDp4Probabilities:
    def test_correct_candidate_wins_ethanol(self) -> None:
        # Observed ethanol-like 1H peaks; ethanol prediction should win.
        result = dp4_probabilities(
            observed_shifts_ppm=[3.65, 1.26, 2.10],
            candidate_predicted_shifts_ppm=[
                [3.6, 1.2, 2.0],  # ethanol-like (correct)
                [3.4, 0.8, 1.1],  # methanol-like (wrong skeleton)
            ],
            nucleus="1H",
        )
        assert result[0].probability > result[1].probability
        assert result[0].matched_peaks == 3
        # Probabilities sum to 1.
        assert sum(c.probability for c in result) == pytest.approx(1.0, abs=1e-3)

    def test_probabilities_sum_to_one(self) -> None:
        result = dp4_probabilities(
            observed_shifts_ppm=[7.25, 1.25, 11.0],
            candidate_predicted_shifts_ppm=[
                [7.2, 1.3, 10.9],
                [7.1, 1.1, 10.5],
                [3.5, 1.0, 4.0],
            ],
            nucleus="1H",
        )
        assert sum(c.probability for c in result) == pytest.approx(1.0, abs=1e-3)

    def test_empty_candidates_returns_empty(self) -> None:
        assert dp4_probabilities(
            observed_shifts_ppm=[3.5],
            candidate_predicted_shifts_ppm=[],
            nucleus="1H",
        ) == []

    def test_no_matched_peaks_zero_probability(self) -> None:
        # All predicted peaks far outside tolerance → no matches → 0 prob.
        result = dp4_probabilities(
            observed_shifts_ppm=[3.5, 1.2],
            candidate_predicted_shifts_ppm=[
                [50.0, 60.0],  # nothing within ±0.3 ppm
            ],
            nucleus="1H",
        )
        assert result[0].probability == 0.0
        assert result[0].matched_peaks == 0

    def test_13c_uses_13c_sigma(self) -> None:
        # 13C peaks 2 ppm apart should still match easily.
        result = dp4_probabilities(
            observed_shifts_ppm=[58.3, 18.2, 77.0],
            candidate_predicted_shifts_ppm=[
                [58.0, 18.0, 77.5],  # close
                [200.0, 150.0, 100.0],  # nowhere near
            ],
            nucleus="13C",
        )
        assert result[0].probability > result[1].probability

    def test_linear_scaling_applied_when_enough_pairs(self) -> None:
        # Apply a deliberate bias to all predicted shifts; DP4 should fit it.
        observed = [3.0, 4.0, 5.0, 6.0]
        biased_pred = [3.5, 4.5, 5.5, 6.5]  # constant +0.5 offset
        result = dp4_probabilities(
            observed_shifts_ppm=observed,
            candidate_predicted_shifts_ppm=[biased_pred],
            nucleus="1H",
            apply_linear_scaling=True,
        )
        # After linear scaling, residuals are ~0 — RMSE should be very small.
        assert result[0].rms_error_ppm < 0.05

    def test_linear_scaling_skipped_with_few_pairs(self) -> None:
        result = dp4_probabilities(
            observed_shifts_ppm=[3.5, 1.2],
            candidate_predicted_shifts_ppm=[[3.5, 1.2]],
            nucleus="1H",
            apply_linear_scaling=True,
        )
        # With 2 pairs, scaling is skipped — note is present.
        assert any("linear scaling skipped" in n for n in result[0].notes)


class TestPairResidualDP4Score:
    def test_zero_residual_max_tail_probability(self) -> None:
        scored = pair_residual_dp4_score(observed_ppm=3.5, predicted_ppm=3.5, nucleus="1H")
        assert scored["z_dp4"] == 0.0
        assert scored["tail_probability"] == pytest.approx(1.0, abs=1e-3)

    def test_one_sigma_for_1h_uses_published_value(self) -> None:
        scored = pair_residual_dp4_score(
            observed_ppm=3.5, predicted_ppm=3.5 + DP4_SIGMA_1H, nucleus="1H"
        )
        assert scored["z_dp4"] == pytest.approx(1.0, abs=1e-3)

    def test_one_sigma_for_13c_uses_published_value(self) -> None:
        scored = pair_residual_dp4_score(
            observed_ppm=128.0, predicted_ppm=128.0 + DP4_SIGMA_13C, nucleus="13C"
        )
        assert scored["z_dp4"] == pytest.approx(1.0, abs=1e-3)


class TestPublishedParameters:
    def test_sigma_and_nu_match_smith_goodman_2010(self) -> None:
        # Documented values, Smith & Goodman JACS 2010 Table 2.
        assert DP4_SIGMA_1H == pytest.approx(0.185)
        assert DP4_NU_1H == pytest.approx(14.18)
        assert DP4_SIGMA_13C == pytest.approx(2.306)
        assert DP4_NU_13C == pytest.approx(11.38)
