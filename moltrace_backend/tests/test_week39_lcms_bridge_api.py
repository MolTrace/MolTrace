FAMILY_TABLE = """family_id,anchor_group_id,anchor_mz,anchor_rt_min,label,consensus_score,promoted,relationship_count,member_count
F001,G001,47.049141,1.250000,moderate_confidence_feature_family,0.8300,true,2,3
"""


def test_lcms_consensus_candidate_bridge_api_endpoint(client, api_headers):
    payload = {
        "candidates": [{"name": "ethanol", "smiles": "CCO"}, {"name": "methanol", "smiles": "CO"}],
        "lcms_family_table_text": FAMILY_TABLE,
        "adduct": "[M+H]+",
    }
    with client:
        res = client.post("/confidence/candidates/lcms-consensus-bridge", headers=api_headers, json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["best_match"]["name"] == "ethanol"
        assert data["eligible_family_count"] == 1


def test_unified_lcms_bridge_api_endpoint(client, api_headers):
    payload = {
        "candidates": [{"name": "ethanol", "smiles": "CCO"}, {"name": "methanol", "smiles": "CO"}],
        "lcms_family_table_text": FAMILY_TABLE,
        "lcms_anchor_adduct": "[M+H]+",
    }
    with client:
        res = client.post("/confidence/candidates/unified/lcms-bridge", headers=api_headers, json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["best_candidate"]["name"] == "ethanol"
        assert "LC-MS feature-family consensus" in data["evidence_layers_used"]
