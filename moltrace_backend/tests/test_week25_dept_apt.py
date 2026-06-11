from __future__ import annotations

import json
from pathlib import Path

import pytest

from nmrcheck.dept import DeptAptParseError, analyze_dept_apt_preview, parse_dept_apt_table
from nmrcheck.models import DeptAptAnalyzeResult, DeptAptPeak, DeptAptPreviewReport
from nmrcheck.nmr2d import analyze_nmr2d, analyze_nmr2d_preview, parse_nmr2d_upload

DEPT_FIXTURES = Path(__file__).parent / "fixtures" / "dept"
NMR2D_FIXTURES = Path(__file__).parent / "fixtures" / "nmr2d"
STATE_FIXTURES = Path(__file__).parent / "fixtures" / "current_state"

ETHANOL_PROTON = "1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
ETHANOL_CARBON = "13C NMR (101 MHz, CDCl3) δ 58.3, 18.2."
GLYCOSIDE_PROTON = "1H NMR (400 MHz, D2O) delta 4.82 (d, J = 7.8 Hz, 1H), 3.74 (m, 1H), 3.55 (m, 2H)"
GLYCOSIDE_CARBON = "13C NMR (101 MHz, D2O) δ 101.2, 75.3, 72.4, 62.1."
GLYCOSIDE_SMILES = "COC1OC(CO)C(O)C(O)C1O"


def _dept(name: str) -> bytes:
    return (DEPT_FIXTURES / name).read_bytes()


def _nmr2d(name: str) -> bytes:
    return (NMR2D_FIXTURES / name).read_bytes()


def test_dept_apt_models_accept_required_fields_and_labels() -> None:
    peak = DeptAptPeak(
        experiment="DEPT135",
        shift_ppm=58.3,
        intensity=900.0,
        phase="negative",
        carbon_type="CH2",
        assignment="CH2-OH",
        matched_carbon13_shift_ppm=58.3,
        warnings=["review"],
    )
    preview = DeptAptPreviewReport(
        filename="ethanol_dept135.csv",
        experiment_detected="DEPT135",
        peak_count=1,
        peaks=[peak],
    )
    result = DeptAptAnalyzeResult(
        preview=preview,
        matched_carbon13_count=1,
        typed_peak_count=1,
        dept_apt_consistency_score=1.0,
        type_summary={"CH2": 1},
    )

    assert result.preview.peaks[0].carbon_type == "CH2"
    assert result.preview.peaks[0].matched_carbon13_shift_ppm == 58.3


def test_dept90_positive_peak_supports_ch() -> None:
    preview = parse_dept_apt_table("ethanol_dept90.csv", _dept("ethanol_dept90.csv"))

    assert preview.experiment_detected == "DEPT90"
    assert preview.peaks[0].carbon_type == "CH"


def test_dept135_negative_and_positive_peaks_are_typed_scientifically() -> None:
    preview = parse_dept_apt_table("ethanol_dept135.csv", _dept("ethanol_dept135.csv"))
    types = {round(peak.shift_ppm, 1): peak.carbon_type for peak in preview.peaks}

    assert preview.experiment_detected == "DEPT135"
    assert types[58.3] == "CH2"
    assert types[18.2] == "CH_OR_CH3"
    assert any("do not separate" in warning for warning in preview.warnings)


def test_apt_positive_negative_peaks_remain_ambiguous_by_convention() -> None:
    default_preview = parse_dept_apt_table("apt_example.csv", _dept("apt_example.csv"), experiment_type="APT")
    reversed_preview = parse_dept_apt_table(
        "apt_example.csv",
        _dept("apt_example.csv"),
        experiment_type="APT",
        apt_positive="CH2_C",
    )

    default_types = {round(peak.shift_ppm, 1): peak.carbon_type for peak in default_preview.peaks}
    reversed_types = {round(peak.shift_ppm, 1): peak.carbon_type for peak in reversed_preview.peaks}
    assert default_types[18.2] == "CH_OR_CH3"
    assert default_types[58.3] == "CH2_OR_C"
    assert reversed_types[18.2] == "CH2_OR_C"
    assert reversed_types[58.3] == "CH_OR_CH3"
    assert any("sign convention" in warning for warning in default_preview.warnings)


def test_explicit_carbon_type_overrides_phase_inference() -> None:
    content = b"experiment,shift_ppm,phase,carbon_type\nDEPT135,18.2,negative,CH3\n"
    preview = parse_dept_apt_table("explicit_dept.csv", content)

    assert preview.peaks[0].carbon_type == "CH3"
    assert preview.peaks[0].phase == "negative"


def test_csv_tsv_and_json_aliases_parse() -> None:
    csv_preview = parse_dept_apt_table(
        "aliases.csv",
        b"experiment,delta,sign,type_label\nDEPT135,58.3,-,CH2\n",
    )
    tsv_preview = parse_dept_apt_table(
        "aliases.tsv",
        b"experiment\tcarbon_ppm\tpolarity\tattached_h\nDEPT135\t18.2\tpositive\t3\n",
    )
    payload = {"peaks": [{"experiment_type": "APT", "c_ppm": 101.2, "direction": "up", "carbon_type": "CH"}]}
    json_preview = parse_dept_apt_table("aliases.json", json.dumps(payload).encode())

    assert csv_preview.peaks[0].shift_ppm == 58.3
    assert csv_preview.peaks[0].carbon_type == "CH2"
    assert tsv_preview.peaks[0].carbon_type == "CH3"
    assert json_preview.peaks[0].experiment == "APT"
    assert json_preview.peaks[0].carbon_type == "CH"


def test_invalid_dept_table_fails_with_clear_error() -> None:
    with pytest.raises(DeptAptParseError, match="No valid DEPT/APT peaks"):
        parse_dept_apt_table("invalid_dept.csv", _dept("invalid_dept.csv"))


def test_out_of_range_13c_shift_warns_without_failing() -> None:
    preview = parse_dept_apt_table("out_of_range_dept.csv", _dept("out_of_range_dept.csv"))

    assert preview.peak_count == 1
    assert any("outside the usual 13C range" in warning for warning in preview.peaks[0].warnings)


def test_ethanol_dept135_matches_ethanol_carbon13_text() -> None:
    preview = parse_dept_apt_table("ethanol_dept135.csv", _dept("ethanol_dept135.csv"))
    result = analyze_dept_apt_preview(preview, carbon13_text=ETHANOL_CARBON, solvent="CDCl3")

    assert result.matched_carbon13_count == 2
    assert result.missing_carbon13_count == 0
    assert result.extra_dept_apt_count == 0
    assert result.dept_apt_consistency_score == 1.0
    assert result.type_summary == {"CH2": 1, "CH_OR_CH3": 1}
    assert all(peak.matched_carbon13_shift_ppm is not None for peak in result.preview.peaks)


def test_glucose_like_apt_reports_multiple_o_bearing_typed_carbon_notes() -> None:
    preview = parse_dept_apt_table("glycoside_apt.csv", _dept("glycoside_apt.csv"), experiment_type="APT")
    result = analyze_dept_apt_preview(preview, carbon13_text=GLYCOSIDE_CARBON, solvent="D2O")

    assert result.matched_carbon13_count == 4
    assert result.type_summary["CH_OR_CH3"] == 3
    assert any("O-bearing carbon-type evidence" in note for note in result.notes)


def test_extra_dept_peak_is_reported() -> None:
    content = b"experiment,shift_ppm,phase\nDEPT135,58.3,negative\nDEPT135,18.2,positive\nDEPT135,140.0,positive\n"
    preview = parse_dept_apt_table("extra_dept.csv", content)
    result = analyze_dept_apt_preview(preview, carbon13_text=ETHANOL_CARBON, solvent="CDCl3")

    assert result.matched_carbon13_count == 2
    assert result.extra_dept_apt_count == 1
    assert any("DEPT/APT peak(s) were not matched" in note for note in result.notes)


def test_missing_carbon13_peak_is_reported_but_not_fatal() -> None:
    content = b"experiment,shift_ppm,phase\nDEPT135,58.3,negative\n"
    preview = parse_dept_apt_table("missing_dept.csv", content)
    result = analyze_dept_apt_preview(preview, carbon13_text=ETHANOL_CARBON, solvent="CDCl3")

    assert result.matched_carbon13_count == 1
    assert result.missing_carbon13_count == 1
    assert result.dept_apt_consistency_score is not None
    assert any("not represented in the DEPT/APT table" in note for note in result.notes)


def test_ethanol_hsqc_with_dept135_supports_ch2_and_ch3_correlations() -> None:
    hsqc = parse_nmr2d_upload("ethanol_hsqc.csv", _nmr2d("ethanol_hsqc.csv"))
    dept = parse_dept_apt_table("ethanol_dept135.csv", _dept("ethanol_dept135.csv"))
    report = analyze_nmr2d(
        smiles="CCO",
        preview=hsqc,
        sample_id="ethanol-hsqc-dept",
        solvent="CDCl3",
        proton_nmr_text=ETHANOL_PROTON,
        carbon13_text=ETHANOL_CARBON,
        dept_apt_peaks=dept.peaks,
    )

    assert report.correlation_summary["dept_apt_supported_correlations"] == 2
    assert report.correlation_summary["dept_apt_conflicting_correlations"] == 0
    assert any("DEPT/APT supports" in note for correlation in report.correlations for note in correlation.notes)


def test_hsqc_quaternary_carbon_label_flags_conflict() -> None:
    hsqc = parse_nmr2d_upload("ethanol_hsqc.csv", _nmr2d("ethanol_hsqc.csv"))
    dept = parse_dept_apt_table(
        "quaternary_label.csv",
        b"experiment,shift_ppm,carbon_type\nAPT,58.3,C\n",
        experiment_type="APT",
    )
    result = analyze_nmr2d_preview(
        hsqc,
        proton_nmr_text=ETHANOL_PROTON,
        carbon13_text=ETHANOL_CARBON,
        dept_apt_peaks=dept.peaks,
    )

    assert result.correlation_summary["dept_apt_conflicting_correlations"] == 1
    assert any("quaternary carbon label" in note for correlation in result.correlations for note in correlation.notes)


def test_hmbc_quaternary_carbon_label_is_context_not_conflict() -> None:
    hmbc = parse_nmr2d_upload("glycoside_hmbc.csv", _nmr2d("glycoside_hmbc.csv"))
    dept = parse_dept_apt_table(
        "hmbc_quaternary.csv",
        b"experiment,shift_ppm,carbon_type\nAPT,101.2,C\n",
        experiment_type="APT",
    )
    result = analyze_nmr2d_preview(
        hmbc,
        proton_nmr_text=GLYCOSIDE_PROTON,
        carbon13_text=GLYCOSIDE_CARBON,
        dept_apt_peaks=dept.peaks,
    )

    assert result.correlation_summary["dept_apt_conflicting_correlations"] == 0
    assert result.correlation_summary["dept_apt_contextual_correlations"] == 1
    assert any("quaternary carbon labels can be valid HMBC" in note for correlation in result.correlations for note in correlation.notes)


def test_cosy_ignores_dept_apt_peaks() -> None:
    cosy = parse_nmr2d_upload("ethanol_cosy.csv", _nmr2d("ethanol_cosy.csv"))
    dept = parse_dept_apt_table("ethanol_dept135.csv", _dept("ethanol_dept135.csv"))
    result = analyze_nmr2d_preview(cosy, proton_nmr_text=ETHANOL_PROTON, dept_apt_peaks=dept.peaks)

    assert result.correlation_summary["dept_apt_supported_correlations"] == 0
    assert result.correlation_summary["dept_apt_conflicting_correlations"] == 0
    assert not any("DEPT/APT cross-check" in note for note in result.notes)


def test_hmqc_is_treated_like_hsqc_for_dept_apt_support() -> None:
    hmqc = parse_nmr2d_upload(
        "ethanol_hmqc.csv",
        b"experiment,f2_ppm,f1_ppm,intensity\nHMQC,3.65,58.3,250\nHMQC,1.26,18.2,220\n",
    )
    dept = parse_dept_apt_table("ethanol_dept135.csv", _dept("ethanol_dept135.csv"))
    result = analyze_nmr2d_preview(
        hmqc,
        proton_nmr_text=ETHANOL_PROTON,
        carbon13_text=ETHANOL_CARBON,
        dept_apt_peaks=dept.peaks,
    )

    assert result.correlation_summary["dept_apt_supported_correlations"] == 2
    assert any("DEPT/APT cross-check for HSQC/HMQC" in note for note in result.notes)


def test_dept_preview_endpoint_works(client, api_headers) -> None:
    with client:
        response = client.post(
            "/carbon13/dept/preview",
            headers=api_headers,
            data={"experiment_type": "DEPT135"},
            files={"file": ("ethanol_dept135.csv", _dept("ethanol_dept135.csv"), "text/csv")},
        )

    assert response.status_code == 200, response.text
    assert response.json()["experiment_detected"] == "DEPT135"
    assert response.json()["metadata"]["typed_peak_count"] == 2


def test_dept_analyze_endpoint_works_with_carbon13_text(client, api_headers) -> None:
    with client:
        response = client.post(
            "/carbon13/dept/analyze",
            headers=api_headers,
            data={"experiment_type": "DEPT135", "carbon13_text": ETHANOL_CARBON, "solvent": "CDCl3"},
            files={"file": ("ethanol_dept135.csv", _dept("ethanol_dept135.csv"), "text/csv")},
        )

    assert response.status_code == 200, response.text
    assert response.json()["matched_carbon13_count"] == 2
    assert response.json()["dept_apt_consistency_score"] == 1.0


def test_nmr2d_analyze_endpoint_accepts_dept_apt_file(client, api_headers) -> None:
    with client:
        response = client.post(
            "/nmr2d/analyze",
            headers=api_headers,
            data={
                "smiles": "CCO",
                "sample_id": "ethanol-hsqc-api-dept",
                "solvent": "CDCl3",
                "proton_nmr_text": ETHANOL_PROTON,
                "carbon13_text": ETHANOL_CARBON,
                "save_run": "false",
                "dept_apt_experiment_type": "DEPT135",
            },
            files={
                "file": ("ethanol_hsqc.csv", _nmr2d("ethanol_hsqc.csv"), "text/csv"),
                "dept_apt_file": ("ethanol_dept135.csv", _dept("ethanol_dept135.csv"), "text/csv"),
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["correlation_summary"]["dept_apt_supported_correlations"] == 2
    assert payload["metadata"]["dept_apt_evidence"]["experiment_detected"] == "DEPT135"


def test_invalid_dept_file_in_nmr2d_analyze_returns_400(client, api_headers) -> None:
    with client:
        response = client.post(
            "/nmr2d/analyze",
            headers=api_headers,
            data={
                "smiles": "CCO",
                "proton_nmr_text": ETHANOL_PROTON,
                "carbon13_text": ETHANOL_CARBON,
                "save_run": "false",
            },
            files={
                "file": ("ethanol_hsqc.csv", _nmr2d("ethanol_hsqc.csv"), "text/csv"),
                "dept_apt_file": ("invalid_dept.csv", _dept("invalid_dept.csv"), "text/csv"),
            },
        )

    assert response.status_code == 400
    assert "No valid DEPT/APT peaks" in response.json()["detail"]


def test_malformed_2d_file_still_returns_400(client, api_headers) -> None:
    with client:
        response = client.post(
            "/nmr2d/analyze",
            headers=api_headers,
            data={"smiles": "CCO", "save_run": "false"},
            files={"file": ("bad_2d.csv", b"foo,bar\nnope,nope\n", "text/csv")},
        )

    assert response.status_code == 400
    assert "No valid 2D NMR cross-peaks" in response.json()["detail"]


def test_nmr2d_analyze_without_dept_file_still_works(client, api_headers) -> None:
    with client:
        response = client.post(
            "/nmr2d/analyze",
            headers=api_headers,
            data={
                "smiles": "CCO",
                "sample_id": "ethanol-hsqc-no-dept",
                "solvent": "CDCl3",
                "proton_nmr_text": ETHANOL_PROTON,
                "carbon13_text": ETHANOL_CARBON,
                "save_run": "false",
            },
            files={"file": ("ethanol_hsqc.csv", _nmr2d("ethanol_hsqc.csv"), "text/csv")},
        )

    assert response.status_code == 200, response.text
    assert response.json()["matched_correlation_count"] == 2
    assert response.json()["metadata"]["dept_apt_evidence"] is None


def test_report_includes_dept_apt_section_fields_when_2d_uses_dept(client, api_headers) -> None:
    with client:
        analysis_payload = json.loads((STATE_FIXTURES / "ethanol_inputs.json").read_text())
        analysis = client.post("/analyze", headers=api_headers, json=analysis_payload)
        assert analysis.status_code == 200, analysis.text
        history = client.get("/history?limit=1", headers=api_headers)
        analysis_id = int(history.json()[0]["id"])
        saved = client.post(
            "/nmr2d/analyze",
            headers=api_headers,
            data={
                "smiles": "CCO",
                "sample_id": "ethanol-report-dept",
                "solvent": "CDCl3",
                "proton_nmr_text": ETHANOL_PROTON,
                "carbon13_text": ETHANOL_CARBON,
                "analysis_id": str(analysis_id),
                "dept_apt_experiment_type": "DEPT135",
            },
            files={
                "file": ("ethanol_hsqc.csv", _nmr2d("ethanol_hsqc.csv"), "text/csv"),
                "dept_apt_file": ("ethanol_dept135.csv", _dept("ethanol_dept135.csv"), "text/csv"),
            },
        )
        assert saved.status_code == 200, saved.text
        report = client.get(f"/reports/{analysis_id}.json", headers=api_headers)
        html = client.get(f"/reports/{analysis_id}.html", headers=api_headers)

    assert report.status_code == 200, report.text
    section = report.json()["nmr2d_evidence"][0]
    assert section["dept_apt_experiment_type"] == "DEPT135"
    assert section["dept_apt_typed_peak_count"] == 2
    assert section["dept_apt_matched_carbon13_count"] == 2
    assert section["hsqc_hmqc_dept_apt_supported_correlations"] == 2
    assert section["hsqc_hmqc_dept_apt_conflicting_correlations"] == 0
    assert html.status_code == 200, html.text
    assert "DEPT/APT experiment" in html.text
    assert "HSQC/HMQC DEPT support" in html.text
