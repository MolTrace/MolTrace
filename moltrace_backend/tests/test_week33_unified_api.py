def test_unified_confidence_endpoint(client, api_headers):
    headers = api_headers
    payload = {
        "candidates": [
            {"name": "methanol", "smiles": "CO"},
            {"name": "ethanol", "smiles": "CCO"},
        ],
        "observed_proton_text": (
            "1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), "
            "1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
        ),
        "observed_carbon13_text": "13C NMR (101 MHz, CDCl3) delta 58.3, 18.2.",
        "hrms_observed_mz": 47.04914,
        "hrms_adduct": "[M+H]+",
        "msms_precursor_mz": 47.04914,
        "msms_peak_list_text": "m/z,intensity\n47.04914,10\n29.03858,100\n31.01839,25\n",
        "msms_adduct": "[M+H]+",
    }
    with client:
        res = client.post("/confidence/candidates/unified", headers=headers, json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["best_candidate"]["name"] == "ethanol"
    assert data["best_candidate"]["confidence_score"] > 0.6


def test_unified_confidence_evidence_endpoint(client, api_headers):
    headers = api_headers
    data = {
        "candidates_text": "methanol | CO | alternate\nethanol | CCO | proposed",
        "observed_proton_text": "1H NMR delta 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H)",
        "observed_carbon13_text": "13C NMR delta 58.3, 18.2.",
        "hrms_observed_mz": "47.04914",
        "hrms_adduct": "[M+H]+",
        "hrms_ppm_tolerance": "5",
        "ms1_peak_list_text": "m/z,intensity\n47.04914,100\n48.05249,2.3\n",
        "msms_precursor_mz": "47.04914",
        "msms_peak_list_text": "m/z,intensity\n47.04914,10\n29.03858,100\n",
        "msms_adduct": "[M+H]+",
    }
    with client:
        res = client.post("/confidence/candidates/unified/evidence", headers=headers, data=data)
    assert res.status_code == 200, res.text
    assert res.json()["best_candidate"]["name"] == "ethanol"


def test_unified_confidence_invalid_2d_text_returns_400(client, api_headers):
    headers = api_headers
    with client:
        res = client.post(
            "/confidence/candidates/unified/evidence",
            headers=headers,
            data={
                "candidates_text": "ethanol | CCO | proposed",
                "observed_nmr2d_text": "not,enough\n1.2\n",
                "observed_nmr2d_experiment_type": "HSQC",
            },
        )
    assert res.status_code == 400
