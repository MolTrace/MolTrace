from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.models import (
    NMR2DAnalyzeRequest,
    NMR2DAnalyzeResult,
    NMR2DCorrelationEvidence,
    NMR2DExperimentType,
    NMR2DPeak,
    NMR2DPreviewReport,
    NMR2DRunRecord,
)
from nmrcheck.nmr2d import parse_2d_matrix_preview, parse_nmr2d_upload
from nmrcheck.nmr2d_analyzer import analyze_nmr2d, analyze_nmr2d_preview
from nmrcheck.nmr2d_parser import parse_processed_2d_nmr
from nmrcheck.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "week25"
PROTON_TEXT = "¹H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
CARBON_TEXT = "¹³C NMR (101 MHz, CDCl3) δ 58.3, 18.2."


def test_required_2d_models_are_exported_from_models_module() -> None:
    peak = NMR2DPeak(experiment=NMR2DExperimentType.HSQC, f2_ppm=3.65, f1_ppm=58.3)
    preview = NMR2DPreviewReport(filename="hsqc.csv", experiment_detected=NMR2DExperimentType.HSQC, peaks=[peak], peak_count=1)
    request = NMR2DAnalyzeRequest(
        experiment_type=NMR2DExperimentType.HSQC,
        smiles="CCO",
        solvent="CDCl3",
        sample_id="ethanol",
    )
    correlation = NMR2DCorrelationEvidence(
        correlation_type="HSQC",
        observed_f2_ppm=3.65,
        observed_f1_ppm=58.3,
        matched_1h_peak=3.65,
        matched_13c_peak=58.3,
        plausibility_label="supportive",
        confidence=0.9,
    )
    result = NMR2DAnalyzeResult(
        preview=preview,
        evidence_score=0.9,
        correlation_summary={"experiment_counts": {"HSQC": 1}},
        matched_correlation_count=1,
        correlations=[correlation],
    )

    assert request.experiment_type == "HSQC"
    assert peak.f2_nucleus == "1H"
    assert peak.f1_nucleus == "13C"
    assert peak.f2_region == "heteroatom_or_water"
    assert peak.f1_region == "heteroatom_substituted"
    assert preview.experiment_detected == "HSQC"
    assert result.correlations[0].matched_13c_peak == 58.3
    assert NMR2DRunRecord.model_fields["sample_pk"].default is None


def _client(
    tmp_path,
    *,
    enabled: bool,
    contour_enabled: bool = True,
    raw_beta_enabled: bool = False,
) -> tuple[TestClient, dict[str, str]]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'week25_2d.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            enable_2d_nmr=enabled,
            enable_2d_contour_preview=contour_enabled,
            enable_raw_2d_fid_beta=raw_beta_enabled,
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _upload(filename: str) -> tuple[str, bytes, str]:
    return (filename, (FIXTURES / filename).read_bytes(), "text/csv")


def test_parse_processed_cosy_peak_table() -> None:
    preview = parse_processed_2d_nmr("cosy_ethanol.csv", (FIXTURES / "cosy_ethanol.csv").read_bytes())

    assert preview.experiments == ["COSY"]
    assert preview.experiment_detected == "COSY"
    assert preview.peak_count == 2
    assert preview.peaks[0].proton1_ppm == 3.65
    assert preview.peaks[0].proton2_ppm == 1.26
    assert preview.peaks[0].f2_nucleus == "1H"
    assert preview.peaks[0].f1_nucleus == "1H"
    assert preview.peaks[0].source_row == 1
    assert preview.metadata["duplicate_cross_peak_counts"]["symmetric_cosy"] == 1
    assert preview.metadata["raw_2d_fid_processing"] == "not_implemented_guarded_release"


def test_nmr2d_parser_accepts_csv_tsv_and_json_alias_columns() -> None:
    csv_content = b"exp,direct_ppm,indirect_ppm,area,label\nHMBC,3.65,18.2,91,CH2-to-CH3\n"
    tsv_content = b"ppm_h\tppm_c\tintensity\tannotation\n3.65\t58.3\t250\tCH2-O\n1.26\t18.2\t220\tCH3\n"
    json_content = b'{"cross_peaks":[{"experiment_type":"COSY","x1_ppm":1.26,"x2_ppm":3.65,"volume":45,"assignment":"CH3-CH2"}]}'

    hmbc = parse_nmr2d_upload("manual_hmbc.csv", csv_content)
    hsqc = parse_nmr2d_upload("manual_hsqc.tsv", tsv_content)
    cosy = parse_nmr2d_upload("manual_cosy.json", json_content)

    assert hmbc.experiment_detected == "HMBC"
    assert hmbc.peaks[0].f2_ppm == 3.65
    assert hmbc.peaks[0].f1_ppm == 18.2
    assert hmbc.peaks[0].volume == 91
    assert hmbc.peaks[0].assignment == "CH2-to-CH3"
    assert hsqc.experiment_detected == "HSQC"
    assert hsqc.metadata["missing_experiment_type_rows"] == 2
    assert any("Experiment type was missing" in warning for warning in hsqc.warnings)
    assert hsqc.peaks[0].f2_nucleus == "1H"
    assert hsqc.peaks[0].f1_nucleus == "13C"
    assert cosy.experiment_detected == "COSY"
    assert cosy.peaks[0].volume == 45


def test_nmr2d_parser_flags_diagonal_out_of_range_and_duplicate_cross_peaks() -> None:
    content = "\n".join(
        [
            "experiment,f2_ppm,f1_ppm,intensity",
            "COSY,3.650,3.670,10",
            "COSY,1.260,3.650,20",
            "COSY,1.268,3.656,18",
            "COSY,17.200,1.260,5",
        ]
    ).encode()

    preview = parse_nmr2d_upload("cosy_flags.csv", content)

    assert preview.peaks[0].is_diagonal is True
    assert any("diagonal" in warning.lower() for warning in preview.peaks[0].warnings)
    assert preview.metadata["diagonal_peak_count"] == 1
    assert preview.metadata["duplicate_cross_peak_counts"]["exact"] == 1
    assert any("duplicate 2D cross-peak" in warning for warning in preview.warnings)
    assert preview.metadata["out_of_range_peak_count"] == 1
    assert any("outside the usual nucleus range" in warning for warning in preview.peaks[-1].warnings)


def test_parse_hsqc_and_hmbc_with_contour_preview() -> None:
    hsqc = parse_processed_2d_nmr(
        "hsqc_ethanol.csv",
        (FIXTURES / "hsqc_ethanol.csv").read_bytes(),
        include_contour_preview=True,
    )
    hmbc = parse_processed_2d_nmr("hmbc_ethanol.csv", (FIXTURES / "hmbc_ethanol.csv").read_bytes())

    assert hsqc.experiments == ["HSQC"]
    assert hsqc.experiment_detected == "HSQC"
    assert hsqc.peaks[0].proton1_ppm == 3.65
    assert hsqc.peaks[0].carbon_ppm == 58.3
    assert hsqc.peaks[0].f2_ppm == 3.65
    assert hsqc.peaks[0].f1_ppm == 58.3
    assert hsqc.peaks[0].f2_nucleus == "1H"
    assert hsqc.peaks[0].f1_nucleus == "13C"
    assert hsqc.peaks[0].f2_region == "heteroatom_or_water"
    assert hsqc.peaks[0].f1_region == "heteroatom_substituted"
    assert len(hsqc.contour_preview) == 2
    assert hmbc.experiments == ["HMBC"]


def test_parse_2d_matrix_preview_json_downsamples_display_only() -> None:
    payload = {
        "experiment": "HSQC",
        "f2_axis": [3.65, 1.26, 2.10, 7.26],
        "f1_axis": [58.3, 18.2, 77.16],
        "intensity": [
            [10, 4, 0, 1],
            [2, 12, 1, 0],
            [0, 1, 20, 3],
        ],
    }

    preview = parse_2d_matrix_preview("hsqc_matrix.json", json.dumps(payload).encode(), max_points=5)
    result = analyze_nmr2d_preview(
        preview,
        proton_nmr_text=PROTON_TEXT,
        carbon13_text=CARBON_TEXT,
        smiles="CCO",
        solvent="CDCl3",
    )

    assert preview.source_mode == "processed_matrix_preview"
    assert preview.experiment_detected == "HSQC"
    assert preview.peak_count == 0
    assert preview.peaks == []
    assert len(preview.contour_preview) == 5
    assert preview.metadata["matrix_format"] == "json_axes_intensity"
    assert preview.metadata["intensity_shape"] == [3, 4]
    assert preview.metadata["original_point_count"] == 12
    assert preview.metadata["returned_point_count"] == 5
    assert preview.metadata["downsampling_method"] == "top_abs_intensity"
    assert preview.metadata["contour_preview_affects_evidence_score"] is False
    assert result.evidence_score == 0.0
    assert result.correlations == []
    assert result.metadata["score_components"]["dimension_match_score"] == 0.0


def test_parse_2d_matrix_preview_csv_long_format_is_display_only() -> None:
    content = "\n".join(
        [
            "f2_ppm,f1_ppm,intensity",
            "3.65,58.3,10",
            "1.26,18.2,12",
            "2.10,58.3,2",
            "7.26,77.16,20",
        ]
    ).encode()

    preview = parse_nmr2d_upload(
        "hsqc_matrix.csv",
        content,
        include_contour_preview=True,
        contour_limit=3,
    )

    assert preview.source_mode == "processed_matrix_preview"
    assert preview.experiment_detected == "HSQC"
    assert preview.peak_count == 0
    assert len(preview.contour_preview) == 3
    assert preview.metadata["matrix_format"] == "csv_long"
    assert preview.metadata["max_point_limit"] == 3
    assert preview.metadata["contour_preview_affects_evidence_score"] is False


def test_2d_analyzer_links_current_1d_context_and_requires_review() -> None:
    preview = parse_processed_2d_nmr("hsqc_ethanol.csv", (FIXTURES / "hsqc_ethanol.csv").read_bytes())

    report = analyze_nmr2d(
        smiles="CCO",
        preview=preview,
        sample_id="ethanol-2d",
        solvent="CDCl3",
        proton_nmr_text=PROTON_TEXT,
        carbon13_text=CARBON_TEXT,
    )

    assert report.label in {"supportive", "review"}
    assert report.preview.experiment_detected == "HSQC"
    assert report.evidence_score == report.overall_score
    assert report.linked_1d_peak_count == 2
    assert report.matched_correlation_count == 2
    assert report.suspicious_peak_count >= 0
    assert report.correlations[0].correlation_type == "HSQC"
    assert report.correlations[0].matched_1h_peak == 3.65
    assert report.correlations[0].matched_13c_peak == 58.3
    assert report.evidence_summary["human_review_required"] is True
    assert all(peak.evidence_label == "supportive" for peak in report.peaks)
    assert any("human review" in note.lower() for note in report.notes)


def test_analyze_nmr2d_preview_scores_cosy_connectivity_duplicates_and_diagonal_without_mutation() -> None:
    preview = NMR2DPreviewReport(
        filename="cosy_manual.csv",
        experiment_detected=NMR2DExperimentType.COSY,
        peaks=[
            NMR2DPeak(experiment=NMR2DExperimentType.COSY, f2_ppm=3.65, f1_ppm=1.26),
            NMR2DPeak(experiment=NMR2DExperimentType.COSY, f2_ppm=1.26, f1_ppm=3.65),
            NMR2DPeak(experiment=NMR2DExperimentType.COSY, f2_ppm=3.65, f1_ppm=3.65),
        ],
        peak_count=3,
    )
    before = preview.model_dump(mode="json")

    result = analyze_nmr2d_preview(
        preview,
        proton_nmr_text=PROTON_TEXT,
        smiles="CCO",
        solvent="CDCl3",
    )

    assert preview.model_dump(mode="json") == before
    assert result.evidence_score > 0.45
    assert result.correlation_summary["cosy_connectivity_graph"]["edges"] == [["1.26", "3.65"]]
    assert result.metadata["score_components"]["non_diagonal_cosy_cross_peak_count"] == 2
    assert result.metadata["score_components"]["duplicate_symmetric_pair_count"] == 1
    assert any(correlation.plausibility_label == "supportive_duplicate" for correlation in result.correlations)
    assert any(correlation.plausibility_label == "diagonal_artifact" for correlation in result.correlations)


def test_analyze_nmr2d_preview_scores_hsqc_direct_attachment_region_support() -> None:
    preview = parse_processed_2d_nmr("hsqc_ethanol.csv", (FIXTURES / "hsqc_ethanol.csv").read_bytes())

    result = analyze_nmr2d_preview(
        preview,
        proton_nmr_text=PROTON_TEXT,
        carbon13_text=CARBON_TEXT,
        smiles="CCO",
        solvent="CDCl3",
    )

    components = result.metadata["score_components"]
    assert result.evidence_score > 0.65
    assert result.matched_correlation_count == 2
    assert components["dimension_match_score"] == 1.0
    assert components["reference_support_score"] == 1.0
    assert components["experiment_specific_score"] > 0.9
    assert all(correlation.plausibility_label == "supportive" for correlation in result.correlations)
    assert any("O/N-bearing" in note for note in result.correlations[0].notes)


def test_analyze_nmr2d_preview_treats_hmbc_as_long_range_review_support() -> None:
    preview = NMR2DPreviewReport(
        filename="hmbc_manual.csv",
        experiment_detected=NMR2DExperimentType.HMBC,
        peaks=[NMR2DPeak(experiment=NMR2DExperimentType.HMBC, f2_ppm=3.65, f1_ppm=18.2)],
        peak_count=1,
    )

    result = analyze_nmr2d_preview(preview, proton_nmr_text=PROTON_TEXT, smiles="CCO", solvent="CDCl3")

    assert result.evidence_score >= 0.45
    assert result.missing_reference_count == 0
    assert result.metadata["score_components"]["artifact_penalty"] == 0.0
    assert result.correlations[0].plausibility_label == "long_range_support"
    assert any("long-range heteronuclear connectivity" in note for note in result.notes)
    assert any("expert review" in note for note in result.correlations[0].notes)


def test_2d_feature_flag_disabled_blocks_preview(tmp_path) -> None:
    client, headers = _client(tmp_path, enabled=False)
    with client:
        status = client.get("/nmr2d/status")
        blocked = client.post("/nmr2d/preview", headers=headers, files={"file": _upload("cosy_ethanol.csv")})

    assert status.status_code == 200
    assert status.json()["enabled"] is False
    assert status.json()["feature_flag"] == "ENABLE_2D_NMR"
    assert blocked.status_code == 404
    assert "disabled by feature flag" in blocked.json()["detail"]


def test_2d_contour_preview_flag_blocks_requested_contours(tmp_path) -> None:
    client, headers = _client(tmp_path, enabled=True, contour_enabled=False)
    with client:
        status = client.get("/nmr2d/status")
        blocked = client.post(
            "/nmr2d/preview",
            headers=headers,
            data={"include_contour_preview": "true"},
            files={"file": _upload("hsqc_ethanol.csv")},
        )

    assert status.status_code == 200
    assert status.json()["enabled"] is True
    assert status.json()["contour_preview_enabled"] is False
    assert status.json()["contour_preview_feature_flag"] == "ENABLE_2D_CONTOUR_PREVIEW"
    assert blocked.status_code == 403
    assert "ENABLE_2D_CONTOUR_PREVIEW" in blocked.json()["detail"]


def test_2d_feature_flag_enabled_preview_analyze_and_run_lookup(tmp_path) -> None:
    client, headers = _client(tmp_path, enabled=True)
    with client:
        status = client.get("/nmr2d/status")
        preview = client.post(
            "/nmr2d/preview",
            headers=headers,
            data={"include_contour_preview": "true"},
            files={"file": _upload("hsqc_ethanol.csv")},
        )
        analysis = client.post(
            "/nmr2d/analyze",
            headers=headers,
            data={
                "smiles": "CCO",
                "sample_id": "ethanol-2d",
                "solvent": "CDCl3",
                "proton_nmr_text": PROTON_TEXT,
                "carbon13_text": CARBON_TEXT,
            },
            files={"file": _upload("hsqc_ethanol.csv")},
        )
        run_id = analysis.json()["run_id"]
        run = client.get(f"/nmr2d/runs/{run_id}", headers=headers)
        report = client.get(f"/nmr2d/runs/{run_id}/report", headers=headers)

    assert status.json()["enabled"] is True
    assert status.json()["contour_preview_enabled"] is True
    assert status.json()["raw_2d_fid_beta_enabled"] is False
    assert preview.status_code == 200, preview.text
    assert preview.json()["experiment_detected"] == "HSQC"
    assert preview.json()["experiments"] == ["HSQC"]
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["run_id"] == run_id
    assert analysis.json()["preview"]["experiment_detected"] == "HSQC"
    assert analysis.json()["evidence_score"] == analysis.json()["overall_score"]
    assert analysis.json()["matched_correlation_count"] == 2
    assert analysis.json()["metadata"]["raw_2d_fid_processing"] == "not_implemented"
    assert run.status_code == 200, run.text
    assert run.json()["filename"] == "hsqc_ethanol.csv"
    assert run.json()["experiment_detected"] == "HSQC"
    assert run.json()["evidence_score"] == analysis.json()["overall_score"]
    assert run.json()["suspicious_peak_count"] == analysis.json()["suspicious_peak_count"]
    assert run.json()["metadata"]["raw_2d_fid_processing"] == "not_implemented"
    assert run.json()["report"]["run_id"] == run_id
    assert run.json()["review_status"] == "pending_review"
    assert report.status_code == 200, report.text
    assert report.json()["run_id"] == run_id
    assert report.json()["evidence_summary"]["human_review_required"] is True


def test_nmr2d_analyze_can_run_without_saving_when_requested(tmp_path) -> None:
    db_path = tmp_path / "week25_2d.sqlite3"
    client, headers = _client(tmp_path, enabled=True)
    with client:
        analysis = client.post(
            "/nmr2d/analyze",
            headers=headers,
            data={
                "smiles": "CCO",
                "sample_id": "ethanol-unsaved-2d",
                "solvent": "CDCl3",
                "proton_nmr_text": PROTON_TEXT,
                "carbon13_text": CARBON_TEXT,
                "save_run": "false",
            },
            files={"file": _upload("hsqc_ethanol.csv")},
        )

    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["run_id"] is None
    assert analysis.json()["evidence_summary"]["human_review_required"] is True
    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM nmr2d_runs").fetchone()
    assert row == (0,)


def test_nmr2d_run_table_has_additive_canonical_columns_and_saved_json(tmp_path) -> None:
    db_path = tmp_path / "week25_2d.sqlite3"
    client, headers = _client(tmp_path, enabled=True)
    with client:
        analysis = client.post(
            "/nmr2d/analyze",
            headers=headers,
            data={
                "smiles": "CCO",
                "sample_id": "ethanol-2d",
                "solvent": "CDCl3",
                "proton_nmr_text": PROTON_TEXT,
                "carbon13_text": CARBON_TEXT,
            },
            files={"file": _upload("hsqc_ethanol.csv")},
        )

    assert analysis.status_code == 200, analysis.text
    run_id = analysis.json()["run_id"]
    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(nmr2d_runs)").fetchall()}
        row = connection.execute(
            "SELECT sample_pk, filename, experiment_detected, peak_count, evidence_score, suspicious_peak_count, metadata_json, preview_json, result_json FROM nmr2d_runs WHERE id = ?",
            (run_id,),
        ).fetchone()

    assert {
        "id",
        "created_at",
        "user_id",
        "sample_pk",
        "filename",
        "experiment_detected",
        "peak_count",
        "evidence_score",
        "suspicious_peak_count",
        "review_status",
        "metadata_json",
        "preview_json",
        "result_json",
    } <= columns
    assert row is not None
    assert row[0] is None
    assert row[1] == "hsqc_ethanol.csv"
    assert row[2] == "HSQC"
    assert row[3] == analysis.json()["peak_count"]
    assert row[4] == analysis.json()["evidence_score"]
    assert row[5] == analysis.json()["suspicious_peak_count"]
    assert json.loads(row[6])["raw_2d_fid_processing"] == "not_implemented"
    assert json.loads(row[7])["experiment_detected"] == "HSQC"
    assert json.loads(row[8])["run_id"] is None


def test_2d_raw_fid_beta_flag_blocks_raw_route_by_default(tmp_path) -> None:
    client, headers = _client(tmp_path, enabled=True)
    with client:
        status = client.get("/nmr2d/status")
        raw_stub = client.post("/nmr2d/raw/preview", headers=headers)

    assert status.status_code == 200
    assert status.json()["raw_2d_fid_beta_enabled"] is False
    assert status.json()["raw_2d_fid_beta_feature_flag"] == "ENABLE_RAW_2D_FID_BETA"
    assert status.json()["raw_2d_fid_processing"] == "disabled"
    assert raw_stub.status_code == 403
    assert "ENABLE_RAW_2D_FID_BETA" in raw_stub.json()["detail"]


def test_2d_raw_fid_beta_flag_enabled_returns_guarded_stub(tmp_path) -> None:
    client, headers = _client(tmp_path, enabled=True, raw_beta_enabled=True)
    with client:
        status = client.get("/nmr2d/status")
        raw_stub = client.post("/nmr2d/raw/preview", headers=headers)

    assert status.status_code == 200
    assert status.json()["raw_2d_fid_beta_enabled"] is True
    assert status.json()["raw_2d_fid_processing"] == "beta_enabled_stub"
    assert raw_stub.status_code == 200, raw_stub.text
    assert raw_stub.json()["implemented"] is False


def test_2d_preview_route_accepts_json_matrix_preview_without_picked_peaks(tmp_path) -> None:
    payload = {
        "experiment": "HSQC",
        "f2_axis": [3.65, 1.26],
        "f1_axis": [58.3, 18.2],
        "intensity": [[10, 1], [2, 12]],
    }
    client, headers = _client(tmp_path, enabled=True)
    with client:
        response = client.post(
            "/nmr2d/preview",
            headers=headers,
            files={"file": ("matrix.json", json.dumps(payload).encode(), "application/json")},
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source_mode"] == "processed_matrix_preview"
    assert data["peak_count"] == 0
    assert data["peaks"] == []
    assert data["metadata"]["contour_preview_affects_evidence_score"] is False
    assert data["metadata"]["returned_point_count"] == 4
