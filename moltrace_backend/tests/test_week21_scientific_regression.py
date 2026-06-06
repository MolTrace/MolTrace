import json
from pathlib import Path

import pytest

from nmrcheck.analysis import analyze_inputs, validate_inputs
from nmrcheck.fid import FIDError, inspect_zip_members
from nmrcheck.models import AnalysisInputs
from nmrcheck.spectrum import parse_processed_spectrum

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "nmr"


def test_invalid_smiles_fails_validation() -> None:
    report = validate_inputs(
        AnalysisInputs(smiles="not_a_smiles", nmr_text="1.20 (t, 3H)", solvent="CDCl3")
    )
    assert report.structure_valid is False


def test_malformed_nmr_text_fails_validation() -> None:
    report = validate_inputs(
        AnalysisInputs(smiles="CCO", nmr_text="this is not NMR text", solvent="CDCl3")
    )
    assert report.nmr_text_valid is False


def test_ethanol_analysis_matches_expected_label() -> None:
    expected = json.loads((FIXTURE_DIR / "ethanol_expected.json").read_text())
    report = analyze_inputs(
        AnalysisInputs(
            smiles="CCO",
            nmr_text=(
                "1H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), "
                "1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
            ),
            solvent=expected["solvent"],
        )
    )
    assert report.label == expected["expected_label"]
    assert report.parsed_peak_count >= 3


def test_processed_csv_detects_more_than_water_only() -> None:
    expected = json.loads((FIXTURE_DIR / "ethanol_expected.json").read_text())
    preview = parse_processed_spectrum(
        filename="ethanol_processed.csv",
        content=(FIXTURE_DIR / "ethanol_processed.csv").read_bytes(),
        solvent=expected["solvent"],
        mask_solvent_regions=True,
        peak_sensitivity=0.08,
    )
    assert preview.point_count > 100
    assert len(preview.inferred_peaks) >= expected["expected_min_detected_peaks"]


def test_tobramycin_peak_table_fixture_has_expected_peak_count() -> None:
    expected = json.loads((FIXTURE_DIR / "tobramycin_expected.json").read_text())
    preview = parse_processed_spectrum(
        filename="tobramycin_peak_table.csv",
        content=(FIXTURE_DIR / "tobramycin_peak_table.csv").read_bytes(),
        solvent=expected["solvent"],
    )
    assert len(preview.inferred_peaks) == expected["expected_peak_count"]
    assert sum(peak.integration_h for peak in preview.inferred_peaks) == expected[
        "expected_reference_total_h"
    ]


def test_bruker_and_varian_detection_fixtures() -> None:
    bruker_expected = json.loads((FIXTURE_DIR / "bruker_expected.json").read_text())
    varian_expected = json.loads((FIXTURE_DIR / "varian_expected.json").read_text())

    bruker = inspect_zip_members((FIXTURE_DIR / "bruker_1d_detection.zip").read_bytes())
    varian = inspect_zip_members((FIXTURE_DIR / "varian_1d_detection.zip").read_bytes())

    assert bruker.vendor_detected == bruker_expected["vendor_detected"]
    assert bruker.required_files_present is bruker_expected["required_files_present"]
    assert varian.vendor_detected == varian_expected["vendor_detected"]
    assert varian.required_files_present is varian_expected["required_files_present"]


def test_bad_fid_archives_fail_safely() -> None:
    with pytest.raises(FIDError):
        inspect_zip_members((FIXTURE_DIR / "invalid_zip.zip").read_bytes())
    with pytest.raises(FIDError):
        inspect_zip_members((FIXTURE_DIR / "unsafe_zip.zip").read_bytes())
