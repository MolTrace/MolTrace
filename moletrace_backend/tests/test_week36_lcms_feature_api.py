from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'lcms_features.sqlite3'}", require_verified_email=False, api_key="test-key"))
    return TestClient(app), {"x-api-key": "test-key"}


def _source_text():
    return "scan_id,ms_level,rt_min,mz,intensity,precursor_mz\nms1a,1,0.0,47.04914,5,\nms1b,1,0.1,47.04914,100,\nms1c,1,0.2,47.04914,7,\nms2a,2,0.1,29.03858,100,47.04914\n"


def test_lcms_feature_detection_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    payload = {
        "filename": "feature.csv",
        "source_text": _source_text(),
        "target_mz_text": "47.04914",
        "min_scans_per_feature": 1,
    }
    with client:
        res = client.post("/ms/lcms/features/detect", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["source_format"] == "processed_peak_table"
    assert data["feature_count"] >= 1
    assert data["best_feature"]["target_mz"] == 47.04914


def test_lcms_feature_detection_evidence_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        res = client.post(
            "/ms/lcms/features/detect/evidence",
            headers=headers,
            data={
                "filename": "feature.csv",
                "source_text": _source_text(),
                "target_mz_text": "47.04914",
                "min_scans_per_feature": "1",
            },
        )
    assert res.status_code == 200
    assert res.json()["feature_count"] >= 1


def test_lcms_feature_detection_upload_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    source = _source_text().encode()
    with client:
        res = client.post(
            "/ms/lcms/features/detect/upload",
            headers=headers,
            data={"target_mz_text": "47.04914", "min_scans_per_feature": "1"},
            files={"file": ("feature.csv", source, "text/csv")},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["feature_count"] >= 1
    assert len(data["file_sha256"]) == 64


def test_lcms_feature_detection_bad_input_returns_400(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        res = client.post(
            "/ms/lcms/features/detect",
            headers=headers,
            json={"filename": "bad.csv", "source_text": "not a peak table"},
        )
    assert res.status_code == 400
