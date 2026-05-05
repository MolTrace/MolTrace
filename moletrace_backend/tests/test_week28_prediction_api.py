from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

ETHANOL_1H = "1H NMR delta 3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)"
ETHANOL_13C = "13C NMR delta 58.3, 18.2."


def client_with_key(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'pred.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def test_prediction_nmr_preview_endpoint(tmp_path):
    client, headers = client_with_key(tmp_path)
    with client:
        res = client.post(
            "/prediction/nmr/preview",
            headers=headers,
            json={"name": "ethanol", "smiles": "CCO"},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["formula"] == "C2H6O"
    assert data["proton_peaks"]
    assert data["carbon13_peaks"]


def test_prediction_nmr_match_endpoint_ranks_candidates(tmp_path):
    client, headers = client_with_key(tmp_path)
    with client:
        res = client.post(
            "/prediction/nmr/match",
            headers=headers,
            json={
                "solvent": "CDCl3",
                "observed_proton_text": ETHANOL_1H,
                "observed_carbon13_text": ETHANOL_13C,
                "candidates": [
                    {"name": "methanol", "smiles": "CO"},
                    {"name": "ethanol", "smiles": "CCO"},
                    {"name": "propanol", "smiles": "CCCO"},
                ],
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["best_candidate"]["name"] == "ethanol"
    assert data["evidence_layers_used"] == ["1H predicted-match", "13C predicted-match"]


def test_prediction_nmr_match_evidence_accepts_hsqc_file(tmp_path):
    client, headers = client_with_key(tmp_path)
    files = {
        "observed_nmr2d_file": (
            "ethanol_hsqc.csv",
            b"experiment,f2_ppm,f1_ppm,intensity\nHSQC,3.65,58.3,1\nHSQC,1.26,18.2,1\n",
            "text/csv",
        )
    }
    data = {
        "candidates_text": "methanol | CO | alternate\nethanol | CCO | proposed",
        "observed_proton_text": ETHANOL_1H,
        "observed_carbon13_text": ETHANOL_13C,
        "nmr2d_experiment_type": "HSQC",
    }
    with client:
        res = client.post("/prediction/nmr/match/evidence", headers=headers, data=data, files=files)
    assert res.status_code == 200
    body = res.json()
    assert body["best_candidate"]["name"] == "ethanol"
    assert body["best_candidate"]["evidence_label"] == "best_supported"
    assert body["human_review_required"] is True
    assert body["human_review_status"] == "pending_review"
    assert "HSQC predicted-HSQC-context" in body["evidence_layers_used"]
    assert body["best_candidate"]["nmr2d_similarity"] is not None
    assert body["limitations"]
    provenance = {entry["field_name"]: entry for entry in body["input_provenance"]}
    assert set(provenance) == {
        "candidates_text",
        "observed_proton_text",
        "observed_carbon13_text",
        "observed_nmr2d_file",
    }
    assert provenance["observed_nmr2d_file"]["filename"] == "ethanol_hsqc.csv"
    assert len(provenance["candidates_text"]["sha256"]) == 64


def test_prediction_nmr_match_evidence_rejects_malformed_2d_file(tmp_path):
    client, headers = client_with_key(tmp_path)
    files = {"observed_nmr2d_file": ("bad.csv", b"not,a,valid,table\n1,2,3,4\n", "text/csv")}
    data = {"candidates_text": "ethanol | CCO | proposed", "nmr2d_experiment_type": "HSQC"}
    with client:
        res = client.post("/prediction/nmr/match/evidence", headers=headers, data=data, files=files)
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["error"]["code"] == "invalid_observed_nmr2d_file"
    assert detail["warnings"]
    assert detail["limitations"]


def test_prediction_nmr_match_evidence_accepts_frontend_formdata_payload(tmp_path):
    client, headers = client_with_key(tmp_path)
    data = {
        "candidates_text": (
            "Ethanol | CCO | proposed\n"
            "Methanol | CO | starting material\n"
            "Propanol | CCCO | possible impurity"
        ),
        "observed_proton_text": ETHANOL_1H,
        "observed_carbon13_text": ETHANOL_13C,
        "solvent": "CDCl3",
        "sample_id": "frontend-test-001",
    }
    with client:
        res = client.post("/prediction/nmr/match/evidence", headers=headers, data=data)
    assert res.status_code == 200
    body = res.json()
    assert body["sample_id"] == "frontend-test-001"
    assert body["solvent"] == "CDCl3"
    assert body["candidate_count"] == 3
    assert body["best_candidate"]["name"] == "Ethanol"
    assert body["best_candidate"]["smiles"] == "CCO"
    assert body["best_candidate"]["role"] == "proposed"
    assert body["best_candidate"]["prediction"]["proton_peaks"]
    assert body["best_candidate"]["prediction"]["carbon13_peaks"]
    assert body["best_candidate"]["proton_similarity"] is not None
    assert body["best_candidate"]["carbon13_similarity"] is not None
    assert len(body["ranked_candidates"]) == 3
    assert [candidate["name"] for candidate in body["ranked_candidates"]] == [
        "Ethanol",
        "Methanol",
        "Propanol",
    ]
    assert body["evidence_layers_used"] == ["1H predicted-match", "13C predicted-match"]
    assert isinstance(body["ambiguity_alerts"], list)
    assert isinstance(body["warnings"], list)
    assert body["notes"]


def test_prediction_nmr_match_evidence_rejects_empty_candidate_form_with_structured_error(tmp_path):
    client, headers = client_with_key(tmp_path)
    with client:
        res = client.post(
            "/prediction/nmr/match/evidence",
            headers=headers,
            data={"candidates_text": "   ", "observed_proton_text": ETHANOL_1H},
        )
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["error"]["code"] == "invalid_nmr_match_evidence_request"
    assert "requires human review" in detail["notes"][0]


def test_prediction_nmr_match_evidence_openapi_includes_moltrace_contract_fields(tmp_path):
    client, _headers = client_with_key(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200
    schemas = res.json()["components"]["schemas"]
    result_schema = schemas["CandidatePredictedNMRMatchResult"]
    item_schema = schemas["CandidatePredictedNMRMatchItem"]
    assert "input_provenance" in result_schema["properties"]
    assert "limitations" in result_schema["properties"]
    assert "human_review_status" in result_schema["properties"]
    assert "evidence_label" in item_schema["properties"]
