from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'frag.sqlite3'}", require_verified_email=False, api_key="test-key"))
    return TestClient(app), {"x-api-key": "test-key"}


def test_fragmentation_tree_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    payload = {
        "precursor_mz": 47.04914,
        "adduct": "[M+H]+",
        "peak_list_text": "m/z,intensity\n47.04914,10\n29.03858,100",
        "candidates": [{"name": "ethanol", "smiles": "CCO"}],
    }
    with client:
        res = client.post("/ms/msms/fragmentation-tree", headers=headers, json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["best_candidate"]["name"] == "ethanol"
    assert data["best_candidate"]["diagnostic_loss_count"] >= 1


def test_fragmentation_tree_evidence_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    data = {
        "precursor_mz": "47.04914",
        "adduct": "[M+H]+",
        "peak_list_text": "m/z,intensity\n47.04914,10\n29.03858,100",
        "candidates_text": "ethanol | CCO | proposed",
    }
    with client:
        res = client.post("/ms/msms/fragmentation-tree/evidence", headers=headers, data=data)
    assert res.status_code == 200, res.text
    assert res.json()["best_candidate"]["name"] == "ethanol"


def test_fragmentation_tree_invalid_peak_table_returns_400(tmp_path):
    client, headers = _client(tmp_path)
    payload = {
        "precursor_mz": 47.04914,
        "adduct": "[M+H]+",
        "peak_list_text": "m/z,intensity\n47.04914\n",
        "candidates": [{"name": "ethanol", "smiles": "CCO"}],
    }
    with client:
        res = client.post("/ms/msms/fragmentation-tree", headers=headers, json=payload)
    assert res.status_code == 400
    assert "must contain both m/z and intensity" in res.json()["detail"]
