from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

NMR2D_FIXTURES = Path(__file__).parent / "fixtures" / "nmr2d"
STATE_FIXTURES = Path(__file__).parent / "fixtures" / "current_state"
PROTON_TEXT = "¹H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
CARBON_TEXT = "¹³C NMR (101 MHz, CDCl3) δ 58.3, 18.2."


def _client(tmp_path) -> tuple[TestClient, dict[str, str]]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'nmr2d_report.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            enable_2d_nmr=True,
            enable_2d_contour_preview=True,
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _ethanol_analysis_id(client: TestClient, headers: dict[str, str]) -> int:
    payload = json.loads((STATE_FIXTURES / "ethanol_inputs.json").read_text())
    analysis = client.post("/analyze", headers=headers, json=payload)
    assert analysis.status_code == 200, analysis.text
    history = client.get("/history?limit=1", headers=headers)
    assert history.status_code == 200, history.text
    return int(history.json()[0]["id"])


def _save_linked_2d_run(client: TestClient, headers: dict[str, str], analysis_id: int) -> int:
    response = client.post(
        "/nmr2d/analyze",
        headers=headers,
        data={
            "smiles": "CCO",
            "sample_id": "ethanol-report-2d",
            "solvent": "CDCl3",
            "proton_nmr_text": PROTON_TEXT,
            "carbon13_text": CARBON_TEXT,
            "analysis_id": str(analysis_id),
        },
        files={"file": ("ethanol_hsqc.csv", (NMR2D_FIXTURES / "ethanol_hsqc.csv").read_bytes(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return int(response.json()["run_id"])


def test_2d_evidence_section_appears_in_json_and_html_report(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        analysis_id = _ethanol_analysis_id(client, headers)
        run_id = _save_linked_2d_run(client, headers, analysis_id)
        report = client.get(f"/reports/{analysis_id}.json", headers=headers)
        html = client.get(f"/reports/{analysis_id}.html", headers=headers)

    assert report.status_code == 200, report.text
    data = report.json()
    assert len(data["nmr2d_evidence"]) == 1
    section = data["nmr2d_evidence"][0]
    assert section["run_id"] == run_id
    assert section["experiment_type"] == "HSQC"
    assert section["peak_count"] == 2
    assert section["matched_correlations"] == 2
    assert section["human_review_status"] == "pending_review"
    assert data["audit_metadata"]["nmr2d_evidence_links"][0]["report_url"] == f"/nmr2d/runs/{run_id}/report"
    assert html.status_code == 200, html.text
    assert "2D NMR Evidence" in html.text
    assert "HSQC/HMQC direct attachment notes" in html.text


def test_2d_report_includes_score_components_and_warnings(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        analysis_id = _ethanol_analysis_id(client, headers)
        _save_linked_2d_run(client, headers, analysis_id)
        report = client.get(f"/reports/{analysis_id}.json", headers=headers)

    section = report.json()["nmr2d_evidence"][0]
    assert "dimension_match_score" in section["score_components"]
    assert section["warnings"]
    assert any("human review" in warning.lower() for warning in section["warnings"])
