from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'workflow_automation.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _create_session(client: TestClient, headers: dict):
    project_res = client.post(
        "/projects",
        headers=headers,
        json={"name": "Workflow Project", "metadata_json": {"suite": "workflow-automation"}},
    )
    assert project_res.status_code == 201, project_res.text
    project = project_res.json()

    sample_res = client.post(
        f"/projects/{project['id']}/samples",
        headers=headers,
        json={"sample_id": "WF-SAMPLE-001", "solvent": "CDCl3"},
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
            "title": "Workflow session",
            "shared_inputs_json": {"solvent": "CDCl3"},
        },
    )
    assert session_res.status_code == 201, session_res.text
    return project, sample, session_res.json()


def test_builtin_templates_are_listed_and_fetchable(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        res = client.get("/workflow-templates", headers=headers)
        assert res.status_code == 200, res.text
        templates = res.json()
        slugs = {template["slug"] for template in templates}
        assert {
            "quick_nmr_text_candidate_check",
            "processed_1h_13c_evidence",
            "raw_fid_to_evidence",
            "hrms_msms_candidate_support",
            "lcms_feature_consensus",
            "full_spectracheck_evidence_to_report",
        }.issubset(slugs)
        quick = next(template for template in templates if template["slug"] == "quick_nmr_text_candidate_check")
        assert quick["steps"]
        assert quick["required_inputs"] == ["nmr_text", "candidates_text"]

        detail = client.get("/workflow-templates/quick_nmr_text_candidate_check", headers=headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["slug"] == "quick_nmr_text_candidate_check"


def test_workflow_run_create_missing_input_blocks_quick_workflow(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        _project, _sample, session = _create_session(client, headers)
        create_res = client.post(
            "/workflow-runs",
            headers=headers,
            json={
                "template_slug": "quick_nmr_text_candidate_check",
                "session_id": session["id"],
                "inputs_json": {"nmr_text": "1H NMR (400 MHz, CDCl3) delta 1.25."},
            },
        )
        assert create_res.status_code == 201, create_res.text
        workflow = create_res.json()
        assert workflow["status"] == "draft"
        assert workflow["steps"][0]["status"] == "pending"

        start_res = client.post(f"/workflow-runs/{workflow['id']}/start", headers=headers)
        assert start_res.status_code == 200, start_res.text
        started = start_res.json()
        assert started["status"] == "requires_review"
        assert started["progress_percent"] == 100.0
        assert started["steps"][0]["status"] == "blocked"
        assert "candidates_text" in started["warnings"][0]


def test_quick_nmr_workflow_start_records_events_steps_artifacts_and_session_listing(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        _project, _sample, session = _create_session(client, headers)
        create_res = client.post(
            "/workflow-runs",
            headers=headers,
            json={
                "template_slug": "quick_nmr_text_candidate_check",
                "session_id": session["id"],
                "name": "Quick candidate review",
                "inputs_json": {
                    "sample_id": "WF-SAMPLE-001",
                    "solvent": "CDCl3",
                    "nmr_text": "1H NMR (400 MHz, CDCl3) delta 1.25 (t, 3H), 3.65 (q, 2H).",
                    "candidates_text": "Candidate A CCO",
                },
            },
        )
        assert create_res.status_code == 201, create_res.text
        workflow = create_res.json()

        start_res = client.post(f"/workflow-runs/{workflow['id']}/start", headers=headers)
        assert start_res.status_code == 200, start_res.text
        started = start_res.json()
        assert started["status"] == "succeeded"
        assert started["progress_percent"] == 100.0
        assert started["outputs"]["human_review_required"] is True
        assert all(step["status"] == "succeeded" for step in started["steps"])
        assert started["artifacts"]

        events_res = client.get(f"/workflow-runs/{workflow['id']}/events", headers=headers)
        assert events_res.status_code == 200, events_res.text
        event_types = [event["event_type"] for event in events_res.json()]
        assert "created" in event_types
        assert "started" in event_types
        assert "succeeded" in event_types

        steps_res = client.get(f"/workflow-runs/{workflow['id']}/steps", headers=headers)
        assert steps_res.status_code == 200, steps_res.text
        assert [step["step_id"] for step in steps_res.json()] == [
            "predicted_nmr_match",
            "quality_control_evidence",
            "add_to_evidence_queue",
        ]

        artifacts_res = client.get(f"/workflow-runs/{workflow['id']}/artifacts", headers=headers)
        assert artifacts_res.status_code == 200, artifacts_res.text
        assert artifacts_res.json()[0]["evidence_id"] is not None

        session_runs = client.get(f"/spectracheck/sessions/{session['id']}/workflow-runs", headers=headers)
        assert session_runs.status_code == 200, session_runs.text
        assert any(run["id"] == workflow["id"] for run in session_runs.json())


def test_workflow_run_can_be_canceled_before_start(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        _project, _sample, session = _create_session(client, headers)
        create_res = client.post(
            "/workflow-runs",
            headers=headers,
            json={
                "template_slug": "quick_nmr_text_candidate_check",
                "session_id": session["id"],
                "inputs_json": {
                    "nmr_text": "1H NMR delta 1.25.",
                    "candidates_text": "Candidate A CCO",
                },
            },
        )
        assert create_res.status_code == 201, create_res.text
        workflow = create_res.json()

        cancel_res = client.post(f"/workflow-runs/{workflow['id']}/cancel", headers=headers)
        assert cancel_res.status_code == 200, cancel_res.text
        canceled = cancel_res.json()
        assert canceled["status"] == "canceled"
        assert all(step["status"] == "skipped" for step in canceled["steps"])


def test_workflow_template_create_patch_and_openapi(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        create_res = client.post(
            "/workflow-templates",
            headers=headers,
            json={
                "name": "Manual Review Template",
                "slug": "manual_review_template",
                "description": "Manual review-only workflow template.",
                "category": "report",
                "steps_json": [{"step_id": "manual_review", "step_name": "Manual review", "step_type": "manual"}],
                "required_inputs_json": ["session_id"],
            },
        )
        assert create_res.status_code == 201, create_res.text
        template = create_res.json()
        assert template["slug"] == "manual_review_template"

        patch_res = client.patch(
            f"/workflow-templates/{template['id']}",
            headers=headers,
            json={"description": "Updated manual review-only workflow template."},
        )
        assert patch_res.status_code == 200, patch_res.text
        assert patch_res.json()["description"].startswith("Updated")

        openapi_res = client.get("/openapi.json")
        assert openapi_res.status_code == 200, openapi_res.text
        paths = openapi_res.json()["paths"]
        required_paths = [
            "/workflow-templates",
            "/workflow-templates/{template_id}",
            "/workflow-runs",
            "/workflow-runs/{workflow_run_id}",
            "/workflow-runs/{workflow_run_id}/start",
            "/workflow-runs/{workflow_run_id}/cancel",
            "/workflow-runs/{workflow_run_id}/events",
            "/workflow-runs/{workflow_run_id}/steps",
            "/workflow-runs/{workflow_run_id}/artifacts",
            "/spectracheck/sessions/{session_id}/workflow-runs",
        ]
        for path in required_paths:
            assert path in paths
