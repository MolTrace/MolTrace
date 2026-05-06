from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'structure_report.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _unified_payload():
    best = {
        "rank": 1,
        "name": "Ethanol",
        "role": "proposed",
        "smiles": "CCO",
        "formula": "C2H6O",
        "exact_mass": 46.041865,
        "label": "high_confidence_candidate",
        "confidence_band": "high",
        "confidence_score": 0.91,
        "raw_weighted_score": 0.91,
        "evidence_completeness": 0.75,
        "agreement_count": 1,
        "contradiction_count": 0,
        "missing_layers": [],
        "layers": [
            {
                "layer": "hrms_exact_mass",
                "label": "HRMS exact mass",
                "used": True,
                "score": 0.99,
                "weight": 0.2,
                "status": "strong_agreement",
                "agreement": True,
                "contradiction": False,
                "evidence_count": 1,
                "evidence_summary": ["HRMS supports candidate."],
                "warnings": [],
                "metadata": {},
            }
        ],
        "layer_scores": {"hrms_exact_mass": 0.99},
        "evidence_summary": ["HRMS supports candidate."],
        "contradictions": [],
        "warnings": [],
        "metadata": {},
    }
    return {
        "sample_id": "api-sample",
        "solvent": "CDCl3",
        "selected_adduct": "[M+H]+",
        "candidate_count": 1,
        "evidence_layers_used": ["hrms_exact_mass"],
        "global_contradictions": [],
        "ambiguity_alerts": [],
        "notes": [],
        "warnings": [],
        "component_metadata": {},
        "best_candidate": best,
        "ranked_candidates": [best],
    }


def test_structure_report_compose_endpoint_accepts_unified_result(tmp_path):
    client, headers = _client(tmp_path)
    payload = {
        "report_title": "Regulatory-ready Structure Elucidation Report",
        "require_human_approval": True,
        "unified_confidence_result": _unified_payload(),
    }
    with client:
        response = client.post("/reports/structure-elucidation/compose", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["report_id"].startswith("SER-")
    assert data["release_gate"] == "requires_human_review"
    assert data["best_candidate"]["smiles"] == "CCO"
    assert data["provenance"]["report_sha256"]
    assert data["provenance"]["html_report_sha256"]


def test_structure_report_evidence_endpoint_runs_unified_request(tmp_path):
    client, headers = _client(tmp_path)
    data = {
        "candidates_text": "methanol | CO | alternate\nethanol | CCO | proposed",
        "hrms_observed_mz": "47.04914",
        "hrms_adduct": "[M+H]+",
        "hrms_ppm_tolerance": "5",
        "report_title": "API Evidence Report",
        "source_files_text": "ethanol_hrms.csv",
        "processing_history_text": "Processed HRMS exact mass evidence.",
    }
    with client:
        response = client.post("/reports/structure-elucidation/compose/evidence", headers=headers, data=data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["best_candidate"]["name"] == "ethanol"
    assert body["provenance"]["source_files"] == ["ethanol_hrms.csv"]


def test_structure_report_html_endpoint_escapes_payload(tmp_path):
    client, headers = _client(tmp_path)
    payload = {
        "report_title": "<script>alert('x')</script>",
        "project_name": "<b>Project</b>",
        "unified_confidence_result": _unified_payload(),
    }
    with client:
        response = client.post("/reports/structure-elucidation/compose/html", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;" in response.text
