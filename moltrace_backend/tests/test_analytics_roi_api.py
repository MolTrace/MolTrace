from fastapi.testclient import TestClient


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={
            "email": email,
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_analytics_roi_feedback_and_renewal_workflow(client, api_headers):
    admin_headers = api_headers

    with client:
        viewer_headers = _sign_up(client, "viewer@example.com")

        seeded_tasks = client.get("/analytics/automation-tasks", headers=admin_headers)
        assert seeded_tasks.status_code == 200, seeded_tasks.text
        task_keys = {task["task_key"] for task in seeded_tasks.json()}
        assert "report_composer" in task_keys
        assert "human_review_task_completion" in task_keys
        assert len(task_keys) >= 15

        custom_task = client.post(
            "/analytics/automation-tasks",
            headers=admin_headers,
            json={
                "task_key": "safe_custom_metadata_task",
                "name": "Safe custom metadata task",
                "category": "system",
                "default_minutes_saved": 12,
                "description": "Tracks safe backend metadata automation.",
            },
        )
        assert custom_task.status_code == 201, custom_task.text
        patched_task = client.patch(
            f"/analytics/automation-tasks/{custom_task.json()['id']}",
            headers=admin_headers,
            json={"default_minutes_saved": 14, "enabled": True},
        )
        assert patched_task.status_code == 200, patched_task.text
        assert patched_task.json()["default_minutes_saved"] == 14

        report_event = client.post(
            "/analytics/events",
            headers=admin_headers,
            json={
                "event_type": "report_composed",
                "project_id": 101,
                "session_id": 202,
                "job_id": 303,
                "report_id": 404,
                "status": "succeeded",
                "duration_seconds": 3.5,
                "event_source": "backend",
                "metadata_json": {
                    "task_key": "report_composer",
                    "safe_count": 3,
                    "password": "never-store-me",
                    "raw_nmr_text": "1.0 2.0\n2.0 3.0",
                    "full_smiles": "CCOC(=O)C1=CC=CC=C1",
                },
            },
        )
        assert report_event.status_code == 201, report_event.text
        report_payload = report_event.json()
        assert report_payload["estimated_minutes_saved"] == 60
        assert report_payload["metadata_json"]["safe_count"] == 3
        assert report_payload["metadata_json"]["password"] == "[redacted]"
        assert report_payload["metadata_json"]["raw_nmr_text"] == "[redacted]"
        assert report_payload["metadata_json"]["full_smiles"] == "[redacted]"
        assert "never-store-me" not in report_event.text
        assert "CCOC(=O)" not in report_event.text

        workflow_event = client.post(
            "/analytics/events",
            headers=admin_headers,
            json={
                "event_type": "workflow_completed",
                "project_id": 101,
                "session_id": 202,
                "workflow_run_id": 505,
                "status": "succeeded",
                "event_source": "worker",
                "metadata_json": {"task_key": "unified_evidence_synthesis"},
            },
        )
        assert workflow_event.status_code == 201, workflow_event.text

        qc_event = client.post(
            "/analytics/events",
            headers=admin_headers,
            json={
                "event_type": "qc_readiness_assessment",
                "project_id": 101,
                "session_id": 202,
                "status": "warning",
                "event_source": "backend",
                "metadata_json": {"task_key": "qc_readiness_assessment"},
            },
        )
        assert qc_event.status_code == 201, qc_event.text

        listed = client.get("/analytics/events", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        assert len(listed.json()) >= 3

        summary = client.get("/analytics/summary", headers=admin_headers)
        assert summary.status_code == 200, summary.text
        assert summary.json()["total_minutes_saved"] >= 105
        assert summary.json()["reports_generated"] >= 1
        assert summary.json()["workflows_completed"] >= 1
        assert summary.json()["qc_warnings"] >= 1

        global_roi = client.get("/analytics/roi", headers=admin_headers)
        assert global_roi.status_code == 200, global_roi.text
        assert global_roi.json()["total_hours_saved"] >= 1.75

        project_roi = client.get("/analytics/projects/101/roi", headers=admin_headers)
        assert project_roi.status_code == 200, project_roi.text
        assert project_roi.json()["scope"] == "project"
        assert project_roi.json()["scope_id"] == "101"
        assert project_roi.json()["total_minutes_saved"] >= 105

        session_roi = client.get("/analytics/sessions/202/roi", headers=admin_headers)
        assert session_roi.status_code == 200, session_roi.text
        assert session_roi.json()["scope"] == "session"
        assert session_roi.json()["total_minutes_saved"] >= 105

        workflows = client.get("/analytics/workflows/summary", headers=admin_headers)
        assert workflows.status_code == 200, workflows.text
        assert workflows.json()["workflows_completed"] >= 1

        feedback = client.post(
            "/analytics/feedback",
            headers=viewer_headers,
            json={
                "project_id": 101,
                "session_id": 202,
                "feedback_type": "useful",
                "rating": 5,
                "comment": "Useful dashboard summary.",
                "metadata_json": {"raw_spectrum_text": "1 2\n3 4"},
            },
        )
        assert feedback.status_code == 201, feedback.text
        assert feedback.json()["feedback_type"] == "useful"
        assert "1 2" not in feedback.text

        feedback_list = client.get("/analytics/feedback", headers=admin_headers)
        assert feedback_list.status_code == 200, feedback_list.text
        assert any(item["feedback_type"] == "useful" for item in feedback_list.json())

        renewal = client.post(
            "/analytics/renewal-report",
            headers=admin_headers,
            json={
                "scope": "project",
                "scope_id": "101",
                "title": "Project 101 renewal value",
                "metadata_json": {"token": "do-not-store"},
            },
        )
        assert renewal.status_code == 201, renewal.text
        renewal_payload = renewal.json()
        assert renewal_payload["summary_json"]["total_hours_saved"] >= 1.75
        assert renewal_payload["report_json"]["privacy"]["contains_secrets"] is False
        assert "do-not-store" not in renewal.text

        fetched_renewal = client.get(
            f"/analytics/renewal-report/{renewal_payload['id']}",
            headers=admin_headers,
        )
        assert fetched_renewal.status_code == 200, fetched_renewal.text
        assert fetched_renewal.json()["report_sha256"] == renewal_payload["report_sha256"]

        audit = client.get(
            "/admin/audit/search",
            headers=admin_headers,
            params={"event_type": "analytics.renewal_report.create"},
        )
        assert audit.status_code == 200, audit.text
        assert audit.json()

        viewer_admin = client.get("/analytics/summary", headers=viewer_headers)
        assert viewer_admin.status_code == 403, viewer_admin.text


def test_core_module_events_are_sanitized_filterable_and_admin_only(client, api_headers):
    admin_headers = api_headers

    with client:
        viewer_headers = _sign_up(client, "viewer@example.com")

        spectracheck_event = client.post(
            "/analytics/events",
            headers=admin_headers,
            json={
                "event_type": " core_module_opened ",
                "project_id": 42,
                "session_id": 9001,
                "status": "succeeded",
                "event_source": "frontend",
                "metadata_json": {
                    "module": "spectracheck",
                    "surface": "programs_workspace",
                    "smiles": "CCOC(=O)C1=CC=CC=C1",
                    "nmr_text": "1H NMR raw private text",
                },
            },
        )
        assert spectracheck_event.status_code == 201, spectracheck_event.text
        spectracheck_payload = spectracheck_event.json()
        assert spectracheck_payload["event_type"] == "core_module_opened"
        assert spectracheck_payload["metadata_json"]["module"] == "spectracheck"
        assert spectracheck_payload["metadata_json"]["surface"] == "programs_workspace"
        assert spectracheck_payload["metadata_json"]["smiles"] == "[redacted]"
        assert spectracheck_payload["metadata_json"]["nmr_text"] == "[redacted]"
        assert "CCOC(=O)" not in spectracheck_event.text
        assert "raw private text" not in spectracheck_event.text

        for module in ("regulatory_hub", "reactioniq"):
            created = client.post(
                "/analytics/events",
                headers=admin_headers,
                json={
                    "event_type": "core_module_opened",
                    "project_id": 42,
                    "session_id": 9001,
                    "status": "succeeded",
                    "event_source": "frontend",
                    "metadata_json": {
                        "module": module,
                        "surface": "programs_workspace",
                    },
                },
            )
            assert created.status_code == 201, created.text

        other_event = client.post(
            "/analytics/events",
            headers=admin_headers,
            json={
                "event_type": "report_composed",
                "project_id": 42,
                "session_id": 9001,
                "status": "succeeded",
                "event_source": "backend",
                "metadata_json": {"task_key": "report_composer"},
            },
        )
        assert other_event.status_code == 201, other_event.text

        viewer_list = client.get(
            "/analytics/events",
            headers=viewer_headers,
            params={"event_type": "core_module_opened"},
        )
        assert viewer_list.status_code == 403, viewer_list.text

        listed = client.get(
            "/analytics/events",
            headers=admin_headers,
            params={"event_type": "core_module_opened", "limit": 10},
        )
        assert listed.status_code == 200, listed.text
        events = listed.json()
        assert len(events) == 3
        assert {event["event_type"] for event in events} == {"core_module_opened"}
        assert {event["metadata_json"]["module"] for event in events} == {
            "spectracheck",
            "regulatory_hub",
            "reactioniq",
        }
        assert "report_composed" not in listed.text
        assert "CCOC(=O)" not in listed.text
        assert "raw private text" not in listed.text

        limited = client.get(
            "/analytics/events",
            headers=admin_headers,
            params={"event_type": "core_module_opened", "limit": 2},
        )
        assert limited.status_code == 200, limited.text
        assert len(limited.json()) == 2

        by_status = client.get(
            "/analytics/events",
            headers=admin_headers,
            params={"event_type": "core_module_opened", "status": "succeeded"},
        )
        assert by_status.status_code == 200, by_status.text
        assert len(by_status.json()) == 3


def test_analytics_endpoints_appear_in_openapi(client):
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    for path in [
        "/analytics/events",
        "/analytics/summary",
        "/analytics/roi",
        "/analytics/automation-tasks",
        "/analytics/automation-tasks/{task_id}",
        "/analytics/projects/{project_id}/roi",
        "/analytics/sessions/{session_id}/roi",
        "/analytics/workflows/summary",
        "/analytics/feedback",
        "/analytics/renewal-report",
        "/analytics/renewal-report/{report_id}",
    ]:
        assert path in paths
    assert "post" in paths["/analytics/events"]
    assert "get" in paths["/analytics/events"]
    assert "patch" in paths["/analytics/automation-tasks/{task_id}"]
    assert "post" in paths["/analytics/renewal-report"]
