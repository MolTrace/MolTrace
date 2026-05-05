from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'spectracheck_persistence.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _create_project_sample_session(client: TestClient, headers: dict):
    project_res = client.post(
        "/projects",
        headers=headers,
        json={
            "name": "Persistence Study",
            "description": "Save and reload SpectraCheck evidence.",
            "metadata_json": {"program": "moltrace"},
        },
    )
    assert project_res.status_code == 201, project_res.text
    project = project_res.json()
    assert project["status"] == "active"
    assert project["metadata_json"]["program"] == "moltrace"

    sample_res = client.post(
        f"/projects/{project['id']}/samples",
        headers=headers,
        json={
            "sample_id": "MT-SAMPLE-001",
            "display_name": "Batch 1 fraction A",
            "molecule_name": "candidate A",
            "solvent": "CDCl3",
            "notes": "Human review pending.",
            "metadata_json": {"plate": "A1"},
        },
    )
    assert sample_res.status_code == 201, sample_res.text
    sample = sample_res.json()
    assert sample["project_id"] == project["id"]
    assert sample["sample_id"] == "MT-SAMPLE-001"

    session_res = client.post(
        "/spectracheck/sessions",
        headers=headers,
        json={
            "project_id": project["id"],
            "sample_pk": sample["id"],
            "sample_id": sample["sample_id"],
            "title": "Evidence Queue review",
            "shared_inputs_json": {"solvent": "CDCl3", "nucleus": "1H"},
            "metadata_json": {"source": "frontend-evidence-queue"},
        },
    )
    assert session_res.status_code == 201, session_res.text
    session = session_res.json()
    assert session["project_id"] == project["id"]
    assert session["sample_pk"] == sample["id"]
    assert session["shared_inputs_json"]["solvent"] == "CDCl3"
    return project, sample, session


def test_spectracheck_project_sample_session_persistence_flow(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        project, sample, session = _create_project_sample_session(client, headers)

        projects_res = client.get("/projects", headers=headers)
        assert projects_res.status_code == 200
        assert projects_res.json()[0]["id"] == project["id"]

        project_patch = client.patch(
            f"/projects/{project['id']}",
            headers=headers,
            json={"description": "Updated persistence description."},
        )
        assert project_patch.status_code == 200, project_patch.text
        assert project_patch.json()["description"] == "Updated persistence description."

        sample_get = client.get(f"/samples/{sample['sample_id']}", headers=headers)
        assert sample_get.status_code == 200, sample_get.text
        assert sample_get.json()["id"] == sample["id"]

        sample_patch = client.patch(
            f"/samples/{sample['id']}",
            headers=headers,
            json={"status": "analyzing", "metadata_json": {"plate": "A1", "slot": "03"}},
        )
        assert sample_patch.status_code == 200, sample_patch.text
        assert sample_patch.json()["status"] == "analyzing"

        evidence_payload = {
            "layer": "hrms_exact_mass",
            "title": "HRMS candidate match",
            "source_tab": "ms_evidence_studio",
            "status": "ready",
            "score": 0.91,
            "label": "exact_mass_supports_candidate",
            "summary": "Exact mass supports the candidate for review.",
            "evidence_summary_json": ["Observed m/z is within tolerance."],
            "contradictions_json": [],
            "warnings_json": ["Exact mass alone is not identity confirmation."],
            "notes_json": ["Human review required."],
            "endpoint": "/ms/hrms/candidates/match/evidence",
            "request_preview_json": {"candidate_count": 1},
            "response_json": {
                "sample_id": "MT-SAMPLE-001",
                "ranked_candidates": [{"name": "candidate A", "smiles": "CCO", "ppm_score": 0.91}],
                "warnings": ["Exact mass alone is not identity confirmation."],
            },
            "selected_for_unified": True,
            "provenance_json": {"source_file_sha256": "a" * 64},
        }
        evidence_res = client.post(
            f"/spectracheck/sessions/{session['id']}/evidence",
            headers=headers,
            json=evidence_payload,
        )
        assert evidence_res.status_code == 201, evidence_res.text
        evidence = evidence_res.json()
        assert evidence["response_json"] == evidence_payload["response_json"]
        assert evidence["selected_for_unified"] is True

        evidence_patch = client.patch(
            f"/spectracheck/sessions/{session['id']}/evidence/{evidence['id']}",
            headers=headers,
            json={"selected_for_unified": False},
        )
        assert evidence_patch.status_code == 200, evidence_patch.text
        assert evidence_patch.json()["selected_for_unified"] is False

        unified_res = client.post(
            f"/spectracheck/sessions/{session['id']}/unified-evidence",
            headers=headers,
            json={
                "unified_evidence_json": {
                    "sample_id": "MT-SAMPLE-001",
                    "label": "moderate_confidence_candidate",
                    "human_review_required": True,
                },
                "status": "review_required",
            },
        )
        assert unified_res.status_code == 200, unified_res.text
        assert unified_res.json()["latest_unified_evidence_json"]["human_review_required"] is True

        session_after_unified = client.get(f"/spectracheck/sessions/{session['id']}", headers=headers)
        assert session_after_unified.status_code == 200
        assert session_after_unified.json()["latest_unified_evidence_json"]["label"] == "moderate_confidence_candidate"

        review_res = client.post(
            f"/spectracheck/sessions/{session['id']}/review",
            headers=headers,
            json={
                "status": "approved_plausible",
                "reviewer_name": "Dr. Reviewer",
                "reviewer_comment": "Plausible candidate; keep review language.",
            },
        )
        assert review_res.status_code == 201, review_res.text
        assert review_res.json()["status"] == "approved_plausible"

        reviewed_session = client.get(f"/spectracheck/sessions/{session['id']}", headers=headers)
        assert reviewed_session.status_code == 200
        assert reviewed_session.json()["status"] == "approved"

        report_res = client.post(
            f"/spectracheck/sessions/{session['id']}/reports",
            headers=headers,
            json={
                "report_title": "Structure Elucidation Review Draft",
                "status": "draft_requires_review",
                "report_json": {"sample_id": "MT-SAMPLE-001", "human_review_required": True},
                "report_html": "<h1>Review draft</h1>",
                "report_sha256": "b" * 64,
                "metadata_json": {"format": "html"},
            },
        )
        assert report_res.status_code == 201, report_res.text
        report = report_res.json()
        assert report["report_sha256"] == "b" * 64

        audit_res = client.get(f"/spectracheck/sessions/{session['id']}/audit", headers=headers)
        assert audit_res.status_code == 200, audit_res.text
        audit_events = audit_res.json()
        event_types = {event["event_type"] for event in audit_events}
        assert "spectracheck.session.create" in event_types
        assert "spectracheck.evidence.create" in event_types
        assert "spectracheck.evidence.update" in event_types
        assert "spectracheck.unified_evidence.save" in event_types
        assert "spectracheck.review.create" in event_types
        assert "spectracheck.report.create" in event_types

        reports_res = client.get(f"/spectracheck/sessions/{session['id']}/reports", headers=headers)
        assert reports_res.status_code == 200
        assert reports_res.json()[0]["id"] == report["id"]


def test_spectracheck_persistence_endpoints_appear_in_openapi(tmp_path):
    client, _headers = _client(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200
    paths = res.json()["paths"]
    required_paths = [
        "/projects",
        "/projects/{project_id}",
        "/projects/{project_id}/samples",
        "/samples/{sample_id}",
        "/spectracheck/sessions",
        "/spectracheck/sessions/{session_id}",
        "/spectracheck/sessions/{session_id}/evidence",
        "/spectracheck/sessions/{session_id}/evidence/{evidence_id}",
        "/spectracheck/sessions/{session_id}/unified-evidence",
        "/spectracheck/sessions/{session_id}/review",
        "/spectracheck/sessions/{session_id}/audit",
        "/spectracheck/sessions/{session_id}/reports",
    ]
    for path in required_paths:
        assert path in paths
    assert "post" in paths["/projects"]
    assert "get" in paths["/projects"]
    assert "get" in paths["/projects/{project_id}"]
    assert "patch" in paths["/projects/{project_id}"]
    assert "post" in paths["/projects/{project_id}/samples"]
    assert "get" in paths["/projects/{project_id}/samples"]
    assert "patch" in paths["/samples/{sample_id}"]
    assert "delete" in paths["/spectracheck/sessions/{session_id}"]
