"""Unit tests for the literature_data citation module."""

from __future__ import annotations

import pytest

from nmrcheck.literature_data import (
    DP4_NU_1H,
    DP4_NU_13C,
    DP4_SIGMA_1H,
    DP4_SIGMA_13C,
    HSQC_TOL_1H_PPM,
    HSQC_TOL_13C_PPM,
    LABILE_1H_WINDOWS,
    PREDICTOR_RMSE_1H_PPM,
    PREDICTOR_RMSE_13C_PPM,
    PROTON_GROUP_WINDOWS_1H,
    REFERENCES,
    TOL_1H_LOOSE_PPM,
    TOL_1H_STRICT_PPM,
    TOL_13C_LOOSE_PPM,
    TOL_13C_STRICT_PPM,
    dp4_nu,
    dp4_sigma,
    predictor_rmse,
    reference,
    references_for_keys,
    tolerance_loose,
    tolerance_strict,
)


class TestDp4Helpers:
    def test_dp4_sigma_per_nucleus(self) -> None:
        assert dp4_sigma("1H") == DP4_SIGMA_1H
        assert dp4_sigma("13C") == DP4_SIGMA_13C

    def test_dp4_nu_per_nucleus(self) -> None:
        assert dp4_nu("1H") == DP4_NU_1H
        assert dp4_nu("13C") == DP4_NU_13C


class TestTolerances:
    def test_strict_loose_relation(self) -> None:
        assert tolerance_strict("1H") < tolerance_loose("1H")
        assert tolerance_strict("13C") < tolerance_loose("13C")

    def test_hsqc_tolerances_within_expected_ranges(self) -> None:
        # Reher 2026 best-performing tolerances:
        assert HSQC_TOL_1H_PPM == pytest.approx(0.5)
        assert HSQC_TOL_13C_PPM == pytest.approx(2.5)

    def test_strict_tolerances_match_documented_values(self) -> None:
        assert TOL_1H_STRICT_PPM == pytest.approx(0.15)
        assert TOL_13C_STRICT_PPM == pytest.approx(2.0)

    def test_loose_tolerances_match_documented_values(self) -> None:
        assert TOL_1H_LOOSE_PPM == pytest.approx(0.5)
        assert TOL_13C_LOOSE_PPM == pytest.approx(6.0)


class TestPredictorRmse:
    def test_predictor_rmse_per_nucleus(self) -> None:
        assert predictor_rmse("1H") == PREDICTOR_RMSE_1H_PPM
        assert predictor_rmse("13C") == PREDICTOR_RMSE_13C_PPM
        # 1H must always be tighter than 13C.
        assert PREDICTOR_RMSE_1H_PPM < PREDICTOR_RMSE_13C_PPM


class TestFunctionalGroupWindows:
    def test_proton_windows_are_increasing_ranges(self) -> None:
        for low, high, label in PROTON_GROUP_WINDOWS_1H:
            assert low < high, f"{label}: low ({low}) must be < high ({high})"

    def test_labile_windows_present(self) -> None:
        labels = [label for _, _, label in LABILE_1H_WINDOWS]
        assert any("amide" in label for label in labels)
        assert any("alcohol" in label for label in labels)
        assert any("carboxylic acid" in label for label in labels)
        assert any("thiol" in label for label in labels)


class TestReferenceRegistry:
    def test_smith_goodman_2010_present(self) -> None:
        ref = reference("smith_goodman_2010_dp4")
        assert ref is not None
        assert ref["year"] == 2010
        assert "DP4" in ref["title"]
        assert ref["doi"] == "10.1021/ja105035r"

    def test_unknown_key_returns_none(self) -> None:
        assert reference("does_not_exist") is None

    def test_references_for_keys_deduplicates(self) -> None:
        result = references_for_keys([
            "smith_goodman_2010_dp4",
            "smith_goodman_2010_dp4",  # duplicate
            "silverstein_2014_8e",
            "missing_key",  # silently dropped
        ])
        assert len(result) == 2
        assert result[0]["key"] == "smith_goodman_2010_dp4"
        assert result[1]["key"] == "silverstein_2014_8e"

    def test_every_reference_has_required_fields(self) -> None:
        # All registered citations must carry the bibliographic minimum.
        for key, entry in REFERENCES.items():
            assert "title" in entry and entry["title"], f"{key} missing title"
            assert "authors" in entry and entry["authors"], f"{key} missing authors"
            assert "venue" in entry and entry["venue"], f"{key} missing venue"
            assert isinstance(entry["year"], int), f"{key} year must be int"

    def test_claridge_and_processing_references_present(self) -> None:
        # Phase-correction + apodization defaults trace back to these.
        assert reference("claridge_hr_nmr_techniques") is not None
        assert reference("nmrpipe") is not None
        assert reference("nanalysis_phase_correction") is not None
        assert reference("nanalysis_data_processing") is not None

    def test_tobramycin_pseudo_trisaccharide_publication_present(self) -> None:
        ref = reference("hotor_2025_sulfated_pseudo_trisaccharides")
        assert ref is not None
        assert ref["year"] == 2025
        assert "Tobramycin" in ref["title"]
        assert ref["doi"] == "10.1021/acs.jmedchem.5c00611"


class TestBrukerDefaults:
    def test_bruker_lb_defaults_match_claridge(self) -> None:
        from nmrcheck.literature_data import (
            BRUKER_LB_1H_HZ,
            BRUKER_LB_1H_RANGE,
            BRUKER_LB_13C_HZ,
            BRUKER_LB_13C_RANGE,
            BRUKER_LB_19F_HZ,
            MATCHED_FILTER_LINE_WIDTH_FRACTION,
        )

        # Claridge §3 / Bruker TopSpin defaults.
        assert BRUKER_LB_1H_HZ == pytest.approx(0.3)
        assert BRUKER_LB_13C_HZ == pytest.approx(1.0)
        assert BRUKER_LB_19F_HZ == pytest.approx(0.3)
        assert BRUKER_LB_1H_RANGE == (0.1, 1.0)
        assert BRUKER_LB_13C_RANGE == (1.0, 5.0)
        # "Practical 75%" matched-filter rule.
        assert MATCHED_FILTER_LINE_WIDTH_FRACTION == pytest.approx(0.75)


class TestDisplayConstants:
    def test_display_constants_align_with_viewer_defaults(self) -> None:
        from nmrcheck.literature_data import (
            DISPLAY_HEIGHT_COMPACT_PX,
            DISPLAY_HEIGHT_EXPANDED_PX,
            DISPLAY_MASK_DOMINANCE_RATIO,
            DISPLAY_MASK_MAX_WIDTH_FRACTION,
            DISPLAY_MASK_SPIKE_FLOOR_MULTIPLIER,
            DISPLAY_POINT_MARKER_THRESHOLD,
            DISPLAY_Y_HEADROOM_FACTOR,
            DISPLAY_Y_ROBUST_MAX_PERCENTILE,
        )

        # Industry-standard NMR display preferences / our viewer defaults.
        assert DISPLAY_POINT_MARKER_THRESHOLD == 128
        assert DISPLAY_Y_ROBUST_MAX_PERCENTILE == pytest.approx(0.99)
        assert DISPLAY_Y_HEADROOM_FACTOR == pytest.approx(1.20)
        # Compact is the default; expanded is the user opt-in.
        assert DISPLAY_HEIGHT_COMPACT_PX < DISPLAY_HEIGHT_EXPANDED_PX
        assert DISPLAY_HEIGHT_COMPACT_PX == 360
        # Mask thresholds keep the runaway solvent peak out of the view.
        assert DISPLAY_MASK_DOMINANCE_RATIO == pytest.approx(30.0)
        assert DISPLAY_MASK_SPIKE_FLOOR_MULTIPLIER == pytest.approx(3.0)
        assert 0 < DISPLAY_MASK_MAX_WIDTH_FRACTION < 0.25
