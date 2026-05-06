from __future__ import annotations

from pathlib import Path

from nmrcheck.nmr2d import analyze_nmr2d, parse_nmr2d_upload

FIXTURES = Path(__file__).parent / "fixtures" / "nmr2d"
ETHANOL_PROTON = "¹H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
ETHANOL_CARBON = "¹³C NMR (101 MHz, CDCl3) δ 58.3, 18.2."
GLYCOSIDE_PROTON = "¹H NMR (400 MHz, D2O) δ 4.82 (d, J = 7.8 Hz, 1H), 3.74 (m, 1H), 3.55 (m, 2H)"
GLYCOSIDE_CARBON = "¹³C NMR (101 MHz, D2O) δ 101.2, 75.3, 72.4, 62.1."
GLYCOSIDE_SMILES = "COC1OC(CO)C(O)C(O)C1O"


def _preview(name: str):
    return parse_nmr2d_upload(name, (FIXTURES / name).read_bytes())


def test_ethanol_cosy_matches_ethanol_1h_evidence() -> None:
    report = analyze_nmr2d(
        smiles="CCO",
        preview=_preview("ethanol_cosy.csv"),
        sample_id="ethanol-cosy",
        solvent="CDCl3",
        proton_nmr_text=ETHANOL_PROTON,
    )

    assert report.experiments == ["COSY"]
    assert report.matched_correlation_count >= 2
    assert report.correlation_summary["cosy_connectivity_graph"]["edges"]
    assert any("COSY proton connectivity graph" in note for note in report.notes)


def test_ethanol_hsqc_matches_ethanol_1h_and_13c_evidence() -> None:
    report = analyze_nmr2d(
        smiles="CCO",
        preview=_preview("ethanol_hsqc.csv"),
        sample_id="ethanol-hsqc",
        solvent="CDCl3",
        proton_nmr_text=ETHANOL_PROTON,
        carbon13_text=ETHANOL_CARBON,
    )

    assert report.experiments == ["HSQC"]
    assert report.matched_correlation_count == 2
    assert report.linked_1d_peak_count == 2
    assert all(correlation.plausibility_label == "supportive" for correlation in report.correlations)


def test_glycoside_hsqc_detects_anomeric_hc_evidence() -> None:
    report = analyze_nmr2d(
        smiles=GLYCOSIDE_SMILES,
        preview=_preview("glycoside_hsqc.csv"),
        sample_id="glycoside-hsqc",
        solvent="D2O",
        proton_nmr_text=GLYCOSIDE_PROTON,
        carbon13_text=GLYCOSIDE_CARBON,
    )

    notes = [note for correlation in report.correlations for note in correlation.notes]
    assert report.experiments == ["HSQC"]
    assert any("anomeric/acetal" in note for note in notes)
    assert any(correlation.matched_13c_peak == 101.2 for correlation in report.correlations)


def test_hmbc_returns_supportive_long_range_evidence_without_overclaiming() -> None:
    report = analyze_nmr2d(
        smiles=GLYCOSIDE_SMILES,
        preview=_preview("glycoside_hmbc.csv"),
        sample_id="glycoside-hmbc",
        solvent="D2O",
        proton_nmr_text=GLYCOSIDE_PROTON,
        carbon13_text=GLYCOSIDE_CARBON,
    )

    assert report.experiments == ["HMBC"]
    assert report.evidence_score >= 0.45
    assert any(correlation.plausibility_label == "long_range_support" for correlation in report.correlations)
    assert any("should not be treated as direct attachment" in note for correlation in report.correlations for note in correlation.notes)


def test_solvent_artifact_cross_peaks_are_flagged() -> None:
    content = b"experiment,f2_ppm,f1_ppm,intensity\nHSQC,7.26,77.16,100\n"
    report = analyze_nmr2d(
        smiles="CCO",
        preview=parse_nmr2d_upload("solvent_hsqc.csv", content),
        sample_id="solvent-artifact",
        solvent="CDCl3",
        proton_nmr_text=ETHANOL_PROTON,
        carbon13_text=ETHANOL_CARBON,
    )

    assert report.suspicious_peak_count == 1
    assert report.peaks[0].is_solvent_artifact is True
    assert any("Solvent/artifact overlap" in note for note in report.correlations[0].notes)
