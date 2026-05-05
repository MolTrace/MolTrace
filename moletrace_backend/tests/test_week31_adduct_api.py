from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'adduct.sqlite3'}", require_verified_email=False, api_key="test-key"))
    return TestClient(app), {"x-api-key": "test-key"}


def test_adduct_inference_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    payload = {
        "peak_list_text": "m/z,intensity\n47.04914,100\n48.05249,2.3\n69.03109,24\n",
        "target_mz": 47.04914,
        "ion_mode": "positive",
        "ppm_tolerance": 10,
        "max_c": 5,
        "max_h": 20,
        "max_n": 2,
        "max_o": 3,
        "max_s": 0,
        "max_p": 0,
        "max_cl": 0,
        "max_br": 0,
    }
    with client:
        res = client.post("/ms/adducts/infer", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["best_adduct_candidate"]["adduct"]["name"] == "[M+H]+"
    assert data["best_adduct_candidate"]["top_formulas"][0]["formula"] == "C2H6O"


def test_adduct_inference_evidence_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        res = client.post(
            "/ms/adducts/infer/evidence",
            headers=headers,
            data={
                "peak_list_text": "m/z,intensity\n47.04914,100\n48.05249,2.3\n69.03109,24\n",
                "target_mz": "47.04914",
                "ion_mode": "positive",
                "ppm_tolerance": "10",
                "max_c": "5",
                "max_h": "20",
                "max_n": "2",
                "max_o": "3",
                "max_s": "0",
                "max_p": "0",
                "max_cl": "0",
                "max_br": "0",
            },
        )
    assert res.status_code == 200
    assert res.json()["best_adduct_candidate"]["adduct"]["name"] == "[M+H]+"


def test_adduct_inference_invalid_peak_table_returns_400(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        res = client.post(
            "/ms/adducts/infer",
            headers=headers,
            json={"peak_list_text": "m/z,intensity\n47.04914\n", "target_mz": 47.04914},
        )
    assert res.status_code == 400
    assert "must contain both m/z and intensity" in res.json()["detail"]
