from __future__ import annotations

from pathlib import Path

import pytest

from nmrcheck.nmr2d import NMR2DParseError, parse_nmr2d_upload

FIXTURES = Path(__file__).parent / "fixtures" / "nmr2d"


def _bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_cosy_table_parses() -> None:
    preview = parse_nmr2d_upload("ethanol_cosy.csv", _bytes("ethanol_cosy.csv"))

    assert preview.experiment_detected == "COSY"
    assert preview.peak_count == 3
    assert preview.peaks[0].f2_nucleus == "1H"
    assert preview.peaks[0].f1_nucleus == "1H"


def test_hsqc_table_parses() -> None:
    preview = parse_nmr2d_upload("ethanol_hsqc.csv", _bytes("ethanol_hsqc.csv"))

    assert preview.experiment_detected == "HSQC"
    assert preview.peak_count == 2
    assert preview.peaks[0].f2_nucleus == "1H"
    assert preview.peaks[0].f1_nucleus == "13C"


def test_hmbc_table_parses() -> None:
    preview = parse_nmr2d_upload("glycoside_hmbc.csv", _bytes("glycoside_hmbc.csv"))

    assert preview.experiment_detected == "HMBC"
    assert preview.peak_count == 3
    assert all(peak.experiment == "HMBC" for peak in preview.peaks)


def test_invalid_columns_fail() -> None:
    with pytest.raises(NMR2DParseError, match="No valid 2D NMR cross-peaks"):
        parse_nmr2d_upload("invalid_2d.csv", _bytes("invalid_2d.csv"))


def test_out_of_range_ppm_warns() -> None:
    preview = parse_nmr2d_upload("out_of_range_2d.csv", _bytes("out_of_range_2d.csv"))

    assert preview.metadata["out_of_range_peak_count"] == 1
    assert any("outside the usual nucleus range" in warning for peak in preview.peaks for warning in peak.warnings)
    assert any("require review" in warning for warning in preview.warnings)


def test_cosy_diagonal_peaks_are_flagged() -> None:
    preview = parse_nmr2d_upload("ethanol_cosy.csv", _bytes("ethanol_cosy.csv"))

    diagonals = [peak for peak in preview.peaks if peak.is_diagonal]
    assert len(diagonals) == 1
    assert diagonals[0].is_suspicious is True


def test_duplicate_cross_peaks_are_flagged() -> None:
    preview = parse_nmr2d_upload("duplicate_crosspeaks.csv", _bytes("duplicate_crosspeaks.csv"))

    assert preview.metadata["duplicate_cross_peak_counts"]["exact"] == 1
    assert preview.metadata["duplicate_cross_peak_counts"]["symmetric_cosy"] == 1
    assert any("duplicate 2d cross-peak" in warning.lower() for warning in preview.warnings)
