from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures" / "nmr2d"
PROTON_TEXT = "¹H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
CARBON_TEXT = "¹³C NMR (101 MHz, CDCl3) δ 58.3, 18.2."


def _client(tmp_path, *, enabled: bool = True) -> tuple[TestClient, dict[str, str]]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'nmr2d_api.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            enable_2d_nmr=enabled,
            enable_2d_contour_preview=True,
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _upload(name: str) -> tuple[str, bytes, str]:
    return (name, (FIXTURES / name).read_bytes(), "text/csv")


def test_nmr2d_preview_works(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post("/nmr2d/preview", headers=headers, files={"file": _upload("ethanol_cosy.csv")})

    assert response.status_code == 200, response.text
    assert response.json()["experiment_detected"] == "COSY"
    assert response.json()["peak_count"] == 3


def test_nmr2d_analyze_works(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/nmr2d/analyze",
            headers=headers,
            data={
                "smiles": "CCO",
                "sample_id": "ethanol-hsqc-api",
                "solvent": "CDCl3",
                "proton_nmr_text": PROTON_TEXT,
                "carbon13_text": CARBON_TEXT,
                "save_run": "false",
            },
            files={"file": _upload("ethanol_hsqc.csv")},
        )

    assert response.status_code == 200, response.text
    assert response.json()["run_id"] is None
    assert response.json()["matched_correlation_count"] == 2


def test_nmr2d_feature_flag_disabled_returns_clear_error(tmp_path) -> None:
    client, headers = _client(tmp_path, enabled=False)
    with client:
        response = client.post("/nmr2d/preview", headers=headers, files={"file": _upload("ethanol_hsqc.csv")})

    assert response.status_code == 404
    assert "disabled by feature flag" in response.json()["detail"]


def test_nmr2d_runs_can_be_saved_and_retrieved(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        analysis = client.post(
            "/nmr2d/analyze",
            headers=headers,
            data={
                "smiles": "CCO",
                "sample_id": "ethanol-hsqc-saved",
                "solvent": "CDCl3",
                "proton_nmr_text": PROTON_TEXT,
                "carbon13_text": CARBON_TEXT,
            },
            files={"file": _upload("ethanol_hsqc.csv")},
        )
        run_id = analysis.json()["run_id"]
        run = client.get(f"/nmr2d/runs/{run_id}", headers=headers)
        report = client.get(f"/nmr2d/runs/{run_id}/report", headers=headers)

    assert analysis.status_code == 200, analysis.text
    assert run.status_code == 200, run.text
    assert report.status_code == 200, report.text
    assert run.json()["id"] == run_id
    assert report.json()["run_id"] == run_id


def test_nmr2d_review_status_can_be_updated(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        analysis = client.post(
            "/nmr2d/analyze",
            headers=headers,
            data={
                "smiles": "CCO",
                "sample_id": "ethanol-hsqc-review",
                "solvent": "CDCl3",
                "proton_nmr_text": PROTON_TEXT,
                "carbon13_text": CARBON_TEXT,
            },
            files={"file": _upload("ethanol_hsqc.csv")},
        )
        run_id = analysis.json()["run_id"]
        updated = client.post(
            f"/nmr2d/runs/{run_id}/review",
            headers=headers,
            json={"review_status": "approved", "comment": "reviewed in API regression"},
        )
        report = client.get(f"/nmr2d/runs/{run_id}/report", headers=headers)

    assert updated.status_code == 200, updated.text
    assert updated.json()["review_status"] == "approved"
    assert updated.json()["report"]["evidence_summary"]["human_review_status"] == "approved"
    assert report.json()["evidence_summary"]["human_review_status"] == "approved"
