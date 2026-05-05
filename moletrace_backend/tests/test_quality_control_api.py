import json

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'quality_control.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _create_session(client: TestClient, headers: dict):
    project_res = client.post(
        "/projects",
        headers=headers,
        json={"name": "QC Project", "metadata_json": {"suite": "quality-control"}},
    )
    assert project_res.status_code == 201, project_res.text
    project = project_res.json()

    sample_res = client.post(
        f"/projects/{project['id']}/samples",
        headers=headers,
        json={"sample_id": "QC-SAMPLE-001", "solvent": "CDCl3"},
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
            "title": "QC readiness session",
            "shared_inputs_json": {"solvent": "CDCl3"},
        },
    )
    assert session_res.status_code == 201, session_res.text
    return project, sample, session_res.json()


def _upload_file(
    client: TestClient,
    headers: dict,
    *,
    filename: str,
    content: bytes,
    file_kind: str,
    metadata: dict | None = None,
):
    res = client.post(
        "/files/upload",
        headers=headers,
        data={"file_kind": file_kind, "metadata_json": json.dumps(metadata or {})},
        files={"file": (filename, content, "text/csv")},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_quality_control_assesses_artifacts_files_evidence_session_and_override(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        _project, _sample, session = _create_session(client, headers)

        processed = _upload_file(
            client,
            headers,
            filename="processed-1h.csv",
            content=b"ppm,intensity\n0.8,2\n1.2,50\n2.4,5\n7.26,1\n",
            file_kind="processed_nmr",
            metadata={"nucleus": "1H"},
        )
        link_res = client.post(
            f"/spectracheck/sessions/{session['id']}/files",
            headers=headers,
            json={"file_id": processed["id"], "role": "processed_1h"},
        )
        assert link_res.status_code == 201, link_res.text

        job_res = client.post(
            "/jobs",
            headers=headers,
            json={
                "session_id": session["id"],
                "job_type": "nmr_processed_preview",
                "input_file_ids_json": [processed["id"]],
                "parameters_json": {"solvent": "CDCl3"},
            },
        )
        assert job_res.status_code == 201, job_res.text
        artifact_id = job_res.json()["artifact_ids"][0]

        artifact_qc_res = client.post(f"/quality-control/artifacts/{artifact_id}/assess", headers=headers)
        assert artifact_qc_res.status_code == 200, artifact_qc_res.text
        artifact_qc = artifact_qc_res.json()
        assert artifact_qc["target_type"] == "artifact"
        assert artifact_qc["modality"] == "nmr_1h_processed"
        assert artifact_qc["metrics_json"]["point_count"] == 4
        assert artifact_qc["readiness_status"] in {"ready_for_unified_evidence", "usable_with_warnings"}
        assert artifact_qc["warnings"] == artifact_qc["warnings_json"]
        assert artifact_qc["recommended_actions"]

        artifact_get = client.get(f"/quality-control/artifacts/{artifact_id}", headers=headers)
        assert artifact_get.status_code == 200, artifact_get.text
        assert artifact_get.json()["id"] == artifact_qc["id"]

        raw_file = _upload_file(
            client,
            headers,
            filename="raw-fid.zip",
            content=b"raw fid bytes",
            file_kind="raw_fid",
            metadata={
                "vendor_detected": "bruker",
                "required_files_present": True,
                "acquisition_parameters": {"sw_hz": 6400},
            },
        )
        raw_qc_res = client.post(f"/quality-control/files/{raw_file['id']}/assess", headers=headers)
        assert raw_qc_res.status_code == 200, raw_qc_res.text
        raw_qc = raw_qc_res.json()
        assert raw_qc["modality"] == "raw_fid_nmr"
        assert raw_qc["metrics_json"]["raw_sha256_present"] is True
        assert raw_qc["metrics_json"]["raw_file_immutable"] is True

        unknown = _upload_file(
            client,
            headers,
            filename="unknown.bin",
            content=b"not a scientific format",
            file_kind="other",
        )
        unknown_qc_res = client.post(f"/quality-control/files/{unknown['id']}/assess", headers=headers)
        assert unknown_qc_res.status_code == 200, unknown_qc_res.text
        assert unknown_qc_res.json()["qc_status"] in {"not_assessed", "qc_warning"}

        evidence_res = client.post(
            f"/spectracheck/sessions/{session['id']}/evidence",
            headers=headers,
            json={
                "layer": "msms_annotation",
                "title": "MS/MS annotation",
                "source_tab": "ms_evidence_studio",
                "status": "ready",
                "response_json": {"precursor_mz": 123.4, "peak_count": 3},
                "contradictions_json": ["Neutral-loss pattern contradicts candidate fragment proposal."],
                "selected_for_unified": True,
            },
        )
        assert evidence_res.status_code == 201, evidence_res.text
        evidence = evidence_res.json()

        evidence_qc_res = client.post(f"/quality-control/evidence/{evidence['id']}/assess", headers=headers)
        assert evidence_qc_res.status_code == 200, evidence_qc_res.text
        evidence_qc = evidence_qc_res.json()
        assert evidence_qc["qc_status"] == "requires_human_review"
        assert evidence_qc["readiness_status"] == "blocked_until_review"
        assert evidence_qc["human_review_required"] is True
        assert evidence_qc["metrics_json"]["contradiction_count"] == 1

        finding_id = evidence_qc["findings_json"][0]["id"]
        review_res = client.post(
            f"/quality-control/findings/{finding_id}/review",
            headers=headers,
            json={"reviewer_name": "QC Reviewer", "reason": "Reviewed contradiction.", "decision": "acknowledged"},
        )
        assert review_res.status_code == 200, review_res.text
        assert review_res.json()["metadata_json"]["review"]["decision"] == "acknowledged"

        missing_reason_res = client.post(
            f"/quality-control/evidence/{evidence['id']}/override",
            headers=headers,
            json={"decision": "allow_with_warning"},
        )
        assert missing_reason_res.status_code == 422, missing_reason_res.text

        override_res = client.post(
            f"/quality-control/evidence/{evidence['id']}/override",
            headers=headers,
            json={
                "decision": "allow_with_warning",
                "reason": "Reviewer accepts the contradiction as explainable for exploratory evidence only.",
                "reviewer_name": "QC Reviewer",
            },
        )
        assert override_res.status_code == 200, override_res.text
        override = override_res.json()
        assert override["override_status"] == "allow_with_warning"
        assert override["readiness_status"] == "usable_with_warnings"
        assert override["metadata_json"]["latest_override"]["decision"] == "allow_with_warning"

        session_qc_res = client.post(f"/quality-control/sessions/{session['id']}/assess", headers=headers)
        assert session_qc_res.status_code == 200, session_qc_res.text
        session_qc = session_qc_res.json()
        assert session_qc["target_type"] == "session"
        assert session_qc["metrics_json"]["total_items"] >= 3
        assert session_qc["metrics_json"]["requires_review"] >= 1


def test_quality_control_endpoints_appear_in_openapi(tmp_path):
    client, _headers = _client(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    required_paths = [
        "/quality-control/files/{file_id}/assess",
        "/quality-control/artifacts/{artifact_id}/assess",
        "/quality-control/evidence/{evidence_id}/assess",
        "/quality-control/sessions/{session_id}/assess",
        "/quality-control/files/{file_id}",
        "/quality-control/artifacts/{artifact_id}",
        "/quality-control/evidence/{evidence_id}",
        "/quality-control/sessions/{session_id}",
        "/quality-control/findings/{finding_id}/review",
        "/quality-control/evidence/{evidence_id}/override",
    ]
    for path in required_paths:
        assert path in paths
    assert "post" in paths["/quality-control/evidence/{evidence_id}/override"]
