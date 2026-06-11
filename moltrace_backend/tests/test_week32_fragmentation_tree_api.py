def test_fragmentation_tree_endpoint(client, api_headers):
    headers = api_headers
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


def test_fragmentation_tree_evidence_endpoint(client, api_headers):
    headers = api_headers
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


def test_fragmentation_tree_invalid_peak_table_returns_400(client, api_headers):
    headers = api_headers
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
