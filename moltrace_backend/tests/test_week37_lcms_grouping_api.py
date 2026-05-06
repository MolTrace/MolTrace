from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'lcms_grouping.sqlite3'}", require_verified_email=False, api_key="test-key"))
    return TestClient(app), {"x-api-key": "test-key"}


def _source_text():
    return "scan_id,ms_level,rt_min,mz,intensity,precursor_mz\ns1,1,0.0,47.04914,5,\ns2,1,0.1,47.04914,100,\ns3,1,0.2,47.04914,7,\n"


def _blank_text():
    return "scan_id,ms_level,rt_min,mz,intensity,precursor_mz\nb1,1,0.0,47.04914,2,\nb2,1,0.1,47.04914,5,\nb3,1,0.2,47.04914,2,\n"


def test_lcms_feature_grouping_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    payload = {
        "runs": [{"run_id": "sample", "role": "sample", "source_text": _source_text()}],
        "target_mz_text": "47.04914",
        "min_scans_per_feature": 1,
    }
    with client:
        res = client.post("/ms/lcms/features/group", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["group_count"] >= 1
    assert data["groups"][0]["representative_mz"] == 47.04914
    assert data["feature_table_text"].startswith("group_id")


def test_lcms_feature_grouping_evidence_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        res = client.post(
            "/ms/lcms/features/group/evidence",
            headers=headers,
            data={
                "sample_source_text": _source_text(),
                "blank_source_text": _blank_text(),
                "target_mz_text": "47.04914",
                "min_scans_per_feature": "1",
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["run_count"] == 2
    assert data["group_count"] >= 1
    assert data["groups"][0]["blank_area"] > 0


def test_lcms_feature_grouping_upload_endpoint(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        res = client.post(
            "/ms/lcms/features/group/upload",
            headers=headers,
            data={"target_mz_text": "47.04914", "min_scans_per_feature": "1"},
            files={
                "sample_file": ("sample.csv", _source_text().encode(), "text/csv"),
                "blank_file": ("blank.csv", _blank_text().encode(), "text/csv"),
            },
        )
    assert res.status_code == 200
    data = res.json()
    assert data["run_count"] == 2
    assert len(data["alignment_summaries"][0]["file_sha256"]) == 64


def test_lcms_feature_grouping_bad_input_returns_400(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        res = client.post(
            "/ms/lcms/features/group",
            headers=headers,
            json={
                "runs": [{"run_id": "sample", "role": "sample", "source_text": "not a peak table"}],
                "target_mz_text": "47.04914",
            },
        )
    assert res.status_code == 400
