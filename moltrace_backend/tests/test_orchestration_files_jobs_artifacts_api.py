import hashlib
import json

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'orchestration.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _create_session(client: TestClient, headers: dict):
    project_res = client.post(
        "/projects",
        headers=headers,
        json={"name": "Orchestration Project", "metadata_json": {"suite": "files-jobs-artifacts"}},
    )
    assert project_res.status_code == 201, project_res.text
    project = project_res.json()

    sample_res = client.post(
        f"/projects/{project['id']}/samples",
        headers=headers,
        json={"sample_id": "ORCH-SAMPLE-001", "solvent": "CDCl3"},
    )
    assert sample_res.status_code == 201, sample_res.text
    sample = sample_res.json()

    session_res = client.post(
        "/spectracheck/sessions",
        headers=headers,
        json={
            "project_id": project["id"],
            "sample_pk": sample["id"],
            "sample_id": sample["sample_id"],
            "title": "Orchestration session",
            "shared_inputs_json": {"solvent": "CDCl3"},
        },
    )
    assert session_res.status_code == 201, session_res.text
    return project, sample, session_res.json()


def _upload_file(client: TestClient, headers: dict, *, content: bytes, filename: str, file_kind: str = "processed_nmr"):
    res = client.post(
        "/files/upload",
        headers=headers,
        data={"file_kind": file_kind, "metadata_json": json.dumps({"source": "pytest"})},
        files={"file": (filename, content, "text/csv")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_file_upload_retrieve_link_job_events_artifacts_and_immutability(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        _project, _sample, session = _create_session(client, headers)

        content = b"ppm,intensity\n0.80,10\n1.20,45\n2.40,12\n7.26,3\n"
        uploaded = _upload_file(client, headers, content=content, filename="spectrum.csv")
        assert uploaded["file_id"] == uploaded["id"]
        assert uploaded["sha256"] == hashlib.sha256(content).hexdigest()
        assert uploaded["file_size_bytes"] == len(content)
        assert uploaded["file_kind"] == "processed_nmr"
        assert uploaded["storage_backend"] == "local"

        file_get = client.get(f"/files/{uploaded['id']}", headers=headers)
        assert file_get.status_code == 200, file_get.text
        assert file_get.json()["sha256"] == uploaded["sha256"]

        download = client.get(f"/files/{uploaded['id']}/download", headers=headers)
        assert download.status_code == 200, download.text
        assert download.content == content

        link_res = client.post(
            f"/spectracheck/sessions/{session['id']}/files",
            headers=headers,
            json={"file_id": uploaded["id"], "role": "processed_1h", "metadata_json": {"nucleus": "1H"}},
        )
        assert link_res.status_code == 201, link_res.text
        assert link_res.json()["file"]["sha256"] == uploaded["sha256"]

        links_res = client.get(f"/spectracheck/sessions/{session['id']}/files", headers=headers)
        assert links_res.status_code == 200, links_res.text
        assert links_res.json()[0]["file_id"] == uploaded["id"]

        job_res = client.post(
            "/jobs",
            headers=headers,
            json={
                "session_id": session["id"],
                "job_type": "nmr_processed_preview",
                "input_file_ids_json": [uploaded["id"]],
                "parameters_json": {"solvent": "CDCl3", "spectrometer_frequency_mhz": 400.0},
            },
        )
        assert job_res.status_code == 201, job_res.text
        job = job_res.json()
        assert job["job_id"] == job["id"]
        assert job["status"] == "succeeded"
        assert job["progress_percent"] == 100.0
        assert job["result_json"]["point_count"] == 4
        assert job["artifact_ids"]

        listed_jobs = client.get("/jobs", headers=headers)
        assert listed_jobs.status_code == 200, listed_jobs.text
        assert any(row.get("job_id") == job["id"] for row in listed_jobs.json())

        job_get = client.get(f"/jobs/{job['id']}", headers=headers)
        assert job_get.status_code == 200, job_get.text
        assert job_get.json()["status"] == "succeeded"

        events_res = client.get(f"/jobs/{job['id']}/events", headers=headers)
        assert events_res.status_code == 200, events_res.text
        event_types = [event["event_type"] for event in events_res.json()]
        assert event_types == ["queued", "running", "succeeded"]

        artifact_id = job["artifact_ids"][0]
        artifact_res = client.get(f"/artifacts/{artifact_id}", headers=headers)
        assert artifact_res.status_code == 200, artifact_res.text
        artifact = artifact_res.json()
        assert artifact["artifact_id"] == artifact_id
        assert artifact["artifact_type"] == "spectrum_preview"
        assert artifact["artifact_json"]["point_count"] == 4

        session_artifacts = client.get(f"/spectracheck/sessions/{session['id']}/artifacts", headers=headers)
        assert session_artifacts.status_code == 200, session_artifacts.text
        assert session_artifacts.json()[0]["artifact_id"] == artifact_id

        artifact_download = client.get(f"/artifacts/{artifact_id}/download", headers=headers)
        assert artifact_download.status_code == 200, artifact_download.text
        assert json.loads(artifact_download.content)["point_count"] == 4

        analyze_job_res = client.post(
            "/jobs",
            headers=headers,
            json={
                "session_id": session["id"],
                "job_type": "nmr_processed_analyze",
                "input_file_ids_json": [uploaded["id"]],
                "parameters_json": {"solvent": "CDCl3"},
            },
        )
        assert analyze_job_res.status_code == 201, analyze_job_res.text
        analyze_job = analyze_job_res.json()
        assert analyze_job["status"] == "succeeded"
        assert "peak_count" in analyze_job["result_json"]
        assert analyze_job["artifact_ids"]

        unsupported_res = client.post(
            "/jobs",
            headers=headers,
            json={"session_id": session["id"], "job_type": "not_yet_real", "input_file_ids_json": []},
        )
        assert unsupported_res.status_code == 201, unsupported_res.text
        unsupported = unsupported_res.json()
        assert unsupported["status"] == "failed"
        assert "Unsupported job_type" in unsupported["error_message"]

        raw_bytes = b"immutable raw fid bytes"
        raw_file = _upload_file(client, headers, content=raw_bytes, filename="raw-fid.zip", file_kind="raw_fid")
        raw_hash = raw_file["sha256"]
        raw_process_res = client.post(
            "/jobs",
            headers=headers,
            json={
                "session_id": session["id"],
                "job_type": "nmr_raw_fid_process",
                "input_file_ids_json": [raw_file["id"]],
                "parameters_json": {"processing_preset": "default"},
            },
        )
        assert raw_process_res.status_code == 201, raw_process_res.text
        assert raw_process_res.json()["status"] == "failed"

        raw_after = client.get(f"/files/{raw_file['id']}", headers=headers)
        assert raw_after.status_code == 200, raw_after.text
        assert raw_after.json()["sha256"] == raw_hash
        raw_download = client.get(f"/files/{raw_file['id']}/download", headers=headers)
        assert raw_download.status_code == 200, raw_download.text
        assert raw_download.content == raw_bytes


def test_provenance_metadata_aliases_are_accepted_for_formdata_and_strict_json(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        _project, _sample, session = _create_session(client, headers)

        content = b"ppm,intensity\n1.0,10\n2.0,20\n"
        upload_res = client.post(
            "/files/upload",
            headers=headers,
            data={
                "file_kind": "processed_nmr",
                "provenance_metadata_json": json.dumps({"frontend_bundle_id": "bundle-form"}),
            },
            files={"file": ("alias-spectrum.csv", content, "text/csv")},
        )
        assert upload_res.status_code == 201, upload_res.text
        uploaded = upload_res.json()
        assert uploaded["metadata_json"]["provenance_metadata"]["frontend_bundle_id"] == "bundle-form"

        link_res = client.post(
            f"/spectracheck/sessions/{session['id']}/files",
            headers=headers,
            json={
                "file_id": uploaded["id"],
                "role": "processed_1h",
                "provenance_metadata": {"frontend_link_id": "link-json"},
            },
        )
        assert link_res.status_code == 201, link_res.text
        assert link_res.json()["metadata_json"]["provenance_metadata"]["frontend_link_id"] == "link-json"

        evidence_res = client.post(
            f"/spectracheck/sessions/{session['id']}/evidence",
            headers=headers,
            json={
                "layer": "predicted_nmr",
                "title": "Predicted NMR",
                "source_tab": "spectracheck",
                "status": "ready",
                "response_json": {"sample_id": session["sample_id"]},
                "provenance_metadata_json": {"frontend_evidence_id": "evidence-json"},
            },
        )
        assert evidence_res.status_code == 201, evidence_res.text
        assert evidence_res.json()["provenance_json"]["provenance_metadata"]["frontend_evidence_id"] == "evidence-json"

        job_res = client.post(
            "/jobs",
            headers=headers,
            json={
                "session_id": session["id"],
                "job_type": "nmr_processed_preview",
                "input_file_ids_json": [uploaded["id"]],
                "provenance_metadata": {"frontend_job_id": "job-json"},
            },
        )
        assert job_res.status_code == 201, job_res.text
        assert job_res.json()["metadata_json"]["provenance_metadata"]["frontend_job_id"] == "job-json"


def test_orchestration_endpoints_appear_in_openapi(tmp_path):
    client, _headers = _client(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    required_paths = [
        "/files/upload",
        "/files",
        "/files/{file_id}",
        "/files/{file_id}/download",
        "/spectracheck/sessions/{session_id}/files",
        "/spectracheck/sessions/{session_id}/files/{file_id}",
        "/jobs",
        "/jobs/{job_id}",
        "/jobs/{job_id}/cancel",
        "/jobs/{job_id}/events",
        "/spectracheck/sessions/{session_id}/jobs",
        "/artifacts/{artifact_id}",
        "/artifacts/{artifact_id}/download",
        "/spectracheck/sessions/{session_id}/artifacts",
    ]
    for path in required_paths:
        assert path in paths
    assert "post" in paths["/files/upload"]
    assert "post" in paths["/jobs"]
    assert "get" in paths["/jobs/{job_id}/events"]
