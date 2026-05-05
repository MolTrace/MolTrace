from nmrcheck.carbon13 import analyze_carbon13_text, parse_carbon13_table
from nmrcheck.proton import analyze_proton_evidence


def test_proton_evidence_excludes_cdcl3_solvent_peak() -> None:
    report = analyze_proton_evidence(
        smiles="CCO",
        nmr_text="1H NMR (400 MHz, CDCl3) δ 7.26 (s, 1H), 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)",
        solvent="CDCl3",
        sample_id="ethanol",
    )
    assert report.solvent_or_water_h >= 1
    assert any(peak.is_likely_solvent for peak in report.peaks)
    assert report.overall_score > 0.5


def test_carbon13_evidence_scores_and_solvent_exclusion() -> None:
    report = analyze_carbon13_text(
        "CCO",
        "13C NMR (101 MHz, CDCl3) δ 77.0, 58.3, 18.2.",
        solvent="CDCl3",
        sample_id="ethanol",
    )
    assert report.expected_carbon_atoms == 2
    assert report.observed_carbon_signals == 2
    assert report.carbon13_match_score is not None
    assert report.solvent_exclusion_score is not None
    assert report.solvent_warnings


def test_carbon13_table_accepts_dept_or_apt_carbon_type() -> None:
    content = b"shift_ppm,dept,assignment\n58.3,CH2,ethanol CH2\n18.2,CH3,ethanol CH3\n"
    preview = parse_carbon13_table("ethanol_dept.csv", content, solvent="CDCl3")
    assert [peak.carbon_type for peak in preview.peaks] == ["CH2", "CH3"]
