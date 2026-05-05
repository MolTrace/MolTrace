from __future__ import annotations

from pathlib import Path

from nmrcheck.nmr2d import analyze_nmr2d, parse_nmr2d_upload

FIXTURES = Path(__file__).parent / "fixtures" / "nmr2d"
ETHANOL_PROTON = "1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
ETHANOL_CARBON = "13C NMR (101 MHz, CDCl3) δ 58.3, 18.2."
GLYCOSIDE_PROTON = "1H NMR (400 MHz, D2O) delta 4.82 (d, J = 7.8 Hz, 1H), 3.74 (m, 1H), 3.55 (m, 2H)"
GLYCOSIDE_CARBON = "13C NMR (101 MHz, D2O) δ 101.2, 75.3, 72.4, 62.1."
GLYCOSIDE_SMILES = "COC1OC(CO)C(O)C(O)C1O"


def _upload(name: str):
    return parse_nmr2d_upload(name, (FIXTURES / name).read_bytes())


def test_week23_hsqc_peak_table_still_parses() -> None:
    preview = _upload("ethanol_hsqc.csv")

    assert preview.experiment_detected == "HSQC"
    assert preview.peak_count == 2
    assert [round(peak.f1_ppm, 1) for peak in preview.peaks] == [58.3, 18.2]


def test_week23_hsqc_evidence_still_matches_1d_references() -> None:
    report = analyze_nmr2d(
        smiles="CCO",
        preview=_upload("ethanol_hsqc.csv"),
        sample_id="week23-ethanol-hsqc",
        solvent="CDCl3",
        proton_nmr_text=ETHANOL_PROTON,
        carbon13_text=ETHANOL_CARBON,
    )

    assert report.experiments == ["HSQC"]
    assert report.matched_correlation_count == 2
    assert report.correlation_summary["dept_apt_supported_correlations"] == 0


def test_week23_hmbc_still_reports_long_range_support_without_dept() -> None:
    report = analyze_nmr2d(
        smiles=GLYCOSIDE_SMILES,
        preview=_upload("glycoside_hmbc.csv"),
        sample_id="week23-glycoside-hmbc",
        solvent="D2O",
        proton_nmr_text=GLYCOSIDE_PROTON,
        carbon13_text=GLYCOSIDE_CARBON,
    )

    assert report.experiments == ["HMBC"]
    assert report.correlation_summary["dept_apt_conflicting_correlations"] == 0
    assert any("long-range" in note.lower() for correlation in report.correlations for note in correlation.notes)
