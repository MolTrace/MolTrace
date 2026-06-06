from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

FAMILY_TABLE = """family_id,anchor_group_id,anchor_mz,anchor_rt_min,label,consensus_score,promoted,relationship_count,member_count
F001,G001,47.049141,1.250000,moderate_confidence_feature_family,0.8300,true,2,3
"""


def test_lcms_consensus_candidate_bridge_api_endpoint(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'week39_bridge.sqlite3'}", require_verified_email=False, api_key="test-key"))
    payload = {
        "candidates": [{"name": "ethanol", "smiles": "CCO"}, {"name": "methanol", "smiles": "CO"}],
        "lcms_family_table_text": FAMILY_TABLE,
        "adduct": "[M+H]+",
    }
    with TestClient(app) as client:
        res = client.post("/confidence/candidates/lcms-consensus-bridge", headers={"x-api-key": "test-key"}, json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["best_match"]["name"] == "ethanol"
        assert data["eligible_family_count"] == 1


def test_unified_lcms_bridge_api_endpoint(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'week39_unified.sqlite3'}", require_verified_email=False, api_key="test-key"))
    payload = {
        "candidates": [{"name": "ethanol", "smiles": "CCO"}, {"name": "methanol", "smiles": "CO"}],
        "lcms_family_table_text": FAMILY_TABLE,
        "lcms_anchor_adduct": "[M+H]+",
    }
    with TestClient(app) as client:
        res = client.post("/confidence/candidates/unified/lcms-bridge", headers={"x-api-key": "test-key"}, json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["best_candidate"]["name"] == "ethanol"
        assert "LC-MS feature-family consensus" in data["evidence_layers_used"]
