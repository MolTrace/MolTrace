from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def client_with_key(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'msms.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def test_msms_annotation_endpoint(tmp_path):
    client, headers = client_with_key(tmp_path)
    payload = {
        "precursor_mz": 47.04914,
        "adduct": "[M+H]+",
        "peak_list_text": "47.04914,10\n29.03913,100\n",
        "candidates": [
            {"name": "methanol", "smiles": "CO"},
            {"name": "ethanol", "smiles": "CCO"},
        ],
    }
    with client:
        res = client.post("/ms/msms/annotate", headers=headers, json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["best_candidate"]["name"] == "ethanol"
    assert data["best_candidate"]["fragment_match_count"] >= 1


def test_msms_annotation_evidence_endpoint_without_candidates(tmp_path):
    client, headers = client_with_key(tmp_path)
    data = {
        "precursor_mz": "181.07066",
        "adduct": "[M+H]+",
        "peak_list_text": "163.06010,100\n135.04500,30\n",
    }
    with client:
        res = client.post("/ms/msms/annotate/evidence", headers=headers, data=data)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["candidate_count"] == 0
    assert any(hit["loss_name"] == "H2O" for hit in body["neutral_loss_hits"])


def test_msms_unsupported_adduct_returns_400(tmp_path):
    client, headers = client_with_key(tmp_path)
    payload = {
        "precursor_mz": 100.0,
        "adduct": "[M+Foo]+",
        "peak_list_text": "80.0,100\n",
        "candidates": [],
    }
    with client:
        res = client.post("/ms/msms/annotate", headers=headers, json=payload)
    assert res.status_code == 400
    assert "Unsupported HRMS adduct" in res.text
