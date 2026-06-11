def test_msms_annotation_endpoint(client, api_headers):
    headers = api_headers
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


def test_msms_annotation_evidence_endpoint_without_candidates(client, api_headers):
    headers = api_headers
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


def test_msms_unsupported_adduct_returns_400(client, api_headers):
    headers = api_headers
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
