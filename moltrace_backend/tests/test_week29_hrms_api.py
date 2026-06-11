def test_hrms_candidate_match_endpoint(client, api_headers):
    payload = {
        "observed_mz": 47.04914,
        "adduct": "[M+H]+",
        "ppm_tolerance": 5,
        "candidates": [
            {"name": "methanol", "smiles": "CO"},
            {"name": "ethanol", "smiles": "CCO"},
        ],
    }
    with client:
        res = client.post("/ms/hrms/candidates/match", headers=api_headers, json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["best_match"]["name"] == "ethanol"
    assert data["exact_match_count"] >= 1


def test_hrms_candidate_match_evidence_endpoint(client, api_headers):
    data = {
        "observed_mz": "47.04914",
        "adduct": "[M+H]+",
        "ppm_tolerance": "5",
        "candidates_text": "methanol | CO | alternate\nethanol | CCO | proposed",
    }
    with client:
        res = client.post("/ms/hrms/candidates/match/evidence", headers=api_headers, data=data)
    assert res.status_code == 200, res.text
    assert res.json()["best_match"]["name"] == "ethanol"


def test_hrms_formula_search_endpoint_finds_ethanol(client, api_headers):
    payload = {
        "observed_mz": 47.04914,
        "adduct": "[M+H]+",
        "ppm_tolerance": 10,
        "max_c": 5,
        "max_h": 20,
        "max_n": 2,
        "max_o": 3,
        "max_s": 0,
        "max_p": 0,
        "max_cl": 0,
        "max_br": 0,
        "max_results": 50,
    }
    with client:
        res = client.post("/ms/hrms/formulas/search", headers=api_headers, json=payload)
    assert res.status_code == 200, res.text
    assert "C2H6O" in {item["formula"] for item in res.json()["formulas"]}


def test_hrms_unsupported_adduct_returns_400(client, api_headers):
    payload = {
        "observed_mz": 47.04914,
        "adduct": "[M+Li]+",
        "candidates": [{"name": "ethanol", "smiles": "CCO"}],
    }
    with client:
        res = client.post("/ms/hrms/candidates/match", headers=api_headers, json=payload)
    assert res.status_code == 400
    assert "Unsupported HRMS adduct" in res.text
