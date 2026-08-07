"""ROI is derived entirely from usage events, so these tests check the emitters.

The failure this guards against is silent in both directions: on a page rendering "—",
an emitter that never fires and an emitter that fires twice look identical. Every test
here therefore asserts a *direction and an exact magnitude*, not just that a number moved.
"""

from fastapi.testclient import TestClient

ANALYZE_PAYLOAD = {
    "sample_id": "EtOH-ROI-001",
    "smiles": "CCO",
    "nmr_text": (
        "1H NMR (400 MHz, CDCl3) d 3.65 (q, J = 7.1 Hz, 2H), "
        "1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
    ),
    "solvent": "CDCl3",
}


def _roi(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.get("/analytics/roi", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _task_minutes(client: TestClient, headers: dict[str, str], task_key: str) -> float:
    res = client.get("/analytics/automation-tasks", headers=headers)
    assert res.status_code == 200, res.text
    matches = [task for task in res.json() if task["task_key"] == task_key]
    assert matches, f"{task_key} is not in the seeded catalogue"
    return float(matches[0]["default_minutes_saved"])


def _events(client: TestClient, headers: dict[str, str]) -> list[dict]:
    res = client.get("/analytics/events", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_one_analysis_emits_one_event_and_moves_roi_by_the_catalogue_baseline(
    client, api_headers
):
    with client:
        before = _roi(client, api_headers)
        baseline_minutes = _task_minutes(client, api_headers, "candidate_specific_nmr_matching")
        events_before = len(_events(client, api_headers))

        analyze = client.post("/analyze", json=ANALYZE_PAYLOAD, headers=api_headers)
        assert analyze.status_code == 200, analyze.text

        events_after = _events(client, api_headers)
        assert len(events_after) == events_before + 1

        event = events_after[0]
        assert event["event_type"] == "analysis_completed"
        assert event["status"] == "succeeded"
        assert event["metadata_json"]["task_key"] == "candidate_specific_nmr_matching"

        after = _roi(client, api_headers)
        assert after["analyses_completed"] == before["analyses_completed"] + 1
        assert after["tasks_automated"] == before["tasks_automated"] + 1
        # Exactly the catalogue baseline. Any other delta means an emitter passed
        # estimated_minutes_saved itself instead of letting the store resolve it, which
        # would put an uncontrolled number behind a figure a customer may quote.
        assert after["total_minutes_saved"] == round(
            before["total_minutes_saved"] + baseline_minutes, 2
        )


def test_running_the_same_analysis_twice_moves_roi_twice(client, api_headers):
    with client:
        baseline_minutes = _task_minutes(client, api_headers, "candidate_specific_nmr_matching")
        before = _roi(client, api_headers)

        for _ in range(2):
            res = client.post("/analyze", json=ANALYZE_PAYLOAD, headers=api_headers)
            assert res.status_code == 200, res.text

        after = _roi(client, api_headers)
        assert after["analyses_completed"] == before["analyses_completed"] + 2
        assert after["total_minutes_saved"] == round(
            before["total_minutes_saved"] + 2 * baseline_minutes, 2
        )


def test_report_generation_counts_as_a_report_and_not_as_a_second_analysis(
    client, api_headers
):
    with client:
        analyze = client.post("/analyze", json=ANALYZE_PAYLOAD, headers=api_headers)
        assert analyze.status_code == 200, analyze.text
        analyses = client.get("/history", headers=api_headers)
        assert analyses.status_code == 200, analyses.text
        analysis_id = analyses.json()[0]["id"]

        before = _roi(client, api_headers)
        report_minutes = _task_minutes(client, api_headers, "report_composer")

        report = client.post(f"/reports/from-analysis/{analysis_id}", headers=api_headers)
        assert report.status_code == 201, report.text

        after = _roi(client, api_headers)
        assert after["reports_generated"] == before["reports_generated"] + 1
        # _compute_roi buckets by substring, so an event named after both "report" and
        # "analysis" would be counted in both places from a single unit of work.
        assert after["analyses_completed"] == before["analyses_completed"]
        assert after["total_minutes_saved"] == round(
            before["total_minutes_saved"] + report_minutes, 2
        )


def test_a_failed_job_is_recorded_but_moves_no_roi(client, api_headers, app):
    from nmrcheck.database import update_job_progress
    from nmrcheck.orm import JobORM

    with client:
        session_factory = app.state.session_factory
        with session_factory() as session:
            job = JobORM(status="processing", total_items=1, completed_items=0)
            session.add(job)
            session.commit()
            job_id = job.id

        before = _roi(client, api_headers)
        update_job_progress(
            session_factory, job_id, completed_items=0, status="failed", error_message="boom"
        )
        after = _roi(client, api_headers)

        event = _events(client, api_headers)[0]
        assert event["event_type"] == "analysis_job_failed"
        assert event["status"] == "failed"

        assert after["failed_jobs"] == before["failed_jobs"] + 1
        assert after["analyses_completed"] == before["analyses_completed"]
        assert after["tasks_automated"] == before["tasks_automated"]
        assert after["total_minutes_saved"] == before["total_minutes_saved"]


def test_a_successful_job_is_not_counted_twice(client, api_headers, app):
    """One analysis per item, and no extra event for the job wrapping them.

    _compute_roi treats any succeeded event carrying a job_id as an analysis, so emitting
    a "job succeeded" event alongside the per-item events would inflate analyses_completed
    by one per job.
    """
    from nmrcheck.jobs import process_job_items
    from nmrcheck.models import AnalysisInputs
    from nmrcheck.orm import JobORM

    with client:
        session_factory = app.state.session_factory
        with session_factory() as session:
            job = JobORM(status="queued", total_items=2, completed_items=0)
            session.add(job)
            session.commit()
            job_id = job.id

        before = _roi(client, api_headers)
        process_job_items(
            session_factory,
            job_id=job_id,
            items=[AnalysisInputs(**ANALYZE_PAYLOAD), AnalysisInputs(**ANALYZE_PAYLOAD)],
        )
        after = _roi(client, api_headers)

        assert after["analyses_completed"] == before["analyses_completed"] + 2


def test_resolving_a_review_task_counts_once_however_often_it_is_edited(client, api_headers):
    with client:
        dossier = client.post(
            "/regulatory/dossiers",
            headers=api_headers,
            json={
                "title": "Filing",
                "product_name": "Example",
                "intended_use": "Decision support",
            },
        )
        assert dossier.status_code == 201, dossier.text
        task = client.post(
            "/review-tasks",
            headers=api_headers,
            json={
                "subject_type": "regulatory_dossier",
                "subject_id": dossier.json()["id"],
                "title": "Please review",
            },
        )
        assert task.status_code == 201, task.text
        task_id = task.json()["id"]

        before = _roi(client, api_headers)
        resolved = client.patch(
            f"/review-tasks/{task_id}", headers=api_headers, json={"status": "resolved"}
        )
        assert resolved.status_code == 200, resolved.text
        after_first = _roi(client, api_headers)
        assert after_first["review_tasks_completed"] == before["review_tasks_completed"] + 1

        # Editing a task that is already resolved is not a second review.
        for body in ({"title": "Renamed"}, {"status": "resolved"}):
            again = client.patch(f"/review-tasks/{task_id}", headers=api_headers, json=body)
            assert again.status_code == 200, again.text
        after_edits = _roi(client, api_headers)
        assert after_edits["review_tasks_completed"] == after_first["review_tasks_completed"]
        assert after_edits["total_minutes_saved"] == after_first["total_minutes_saved"]


def _workflow_session(client: TestClient, headers: dict[str, str], tag: str) -> dict:
    project = client.post(
        "/projects", headers=headers, json={"name": f"ROI Workflow Project {tag}"}
    )
    assert project.status_code == 201, project.text
    sample = client.post(
        f"/projects/{project.json()['id']}/samples",
        headers=headers,
        json={"sample_id": "WF-ROI-001", "solvent": "CDCl3"},
    )
    assert sample.status_code == 201, sample.text
    session = client.post(
        "/spectracheck/sessions",
        headers=headers,
        json={
            "project_id": project.json()["id"],
            "sample_pk": sample.json()["id"],
            "sample_id": sample.json()["sample_id"],
            "title": "ROI workflow session",
        },
    )
    assert session.status_code == 201, session.text
    return session.json()


def _start_workflow(client: TestClient, headers: dict[str, str], inputs: dict, tag: str) -> dict:
    session = _workflow_session(client, headers, tag)
    created = client.post(
        "/workflow-runs",
        headers=headers,
        json={
            "template_slug": "quick_nmr_text_candidate_check",
            "session_id": session["id"],
            "name": "ROI run",
            "inputs_json": inputs,
        },
    )
    assert created.status_code == 201, created.text
    started = client.post(f"/workflow-runs/{created.json()['id']}/start", headers=headers)
    assert started.status_code == 200, started.text
    return started.json()


def test_a_succeeding_workflow_run_counts_once_and_a_blocked_one_counts_nothing(
    client, api_headers
):
    complete_inputs = {
        "sample_id": "WF-ROI-001",
        "solvent": "CDCl3",
        "nmr_text": "1H NMR (400 MHz, CDCl3) delta 1.25 (t, 3H), 3.65 (q, 2H).",
        "candidates_text": "Candidate A CCO",
    }
    with client:
        workflow_minutes = _task_minutes(client, api_headers, "workflow_run_execution")
        before = _roi(client, api_headers)

        started = _start_workflow(client, api_headers, complete_inputs, "ok")
        assert started["status"] == "succeeded"
        after_success = _roi(client, api_headers)
        assert after_success["workflows_completed"] == before["workflows_completed"] + 1
        assert after_success["total_minutes_saved"] == round(
            before["total_minutes_saved"] + workflow_minutes, 2
        )

        # A run blocked before it executes anything is terminal too, so it is recorded --
        # but it finished no work, so it must not add to workflows_completed or to minutes.
        blocked_inputs = dict(complete_inputs)
        blocked_inputs.pop("candidates_text")
        blocked = _start_workflow(client, api_headers, blocked_inputs, "blocked")
        assert blocked["status"] == "requires_review"

        after_blocked = _roi(client, api_headers)
        assert after_blocked["workflows_completed"] == after_success["workflows_completed"]
        assert after_blocked["total_minutes_saved"] == after_success["total_minutes_saved"]
        blocked_event = next(
            event
            for event in _events(client, api_headers)
            if event["event_type"] == "workflow_run_completed" and event["status"] == "failed"
        )
        assert blocked_event["metadata_json"]["workflow_status"] == "requires_review"


def test_a_new_catalogue_entry_reaches_an_already_seeded_instance(app):
    """Seeding runs per missing key, not only into an empty table.

    A catalogue entry added in a later release must still land on an instance seeded by an
    earlier one. If it does not, _resolve_minutes_saved finds no definition and every event
    resolving to that key is silently worth zero minutes.
    """
    from sqlalchemy import select

    from nmrcheck.analytics_store import _ensure_default_tasks
    from nmrcheck.orm import AutomationTaskDefinitionORM

    session_factory = app.state.session_factory
    with session_factory() as session:
        session.execute(
            AutomationTaskDefinitionORM.__table__.delete().where(
                AutomationTaskDefinitionORM.task_key == "workflow_run_execution"
            )
        )
        session.commit()
        remaining = session.scalars(select(AutomationTaskDefinitionORM.task_key)).all()
        assert remaining, "the table must stay non-empty for this to be a real test"
        assert "workflow_run_execution" not in remaining

        _ensure_default_tasks(session)
        session.commit()

        refreshed = session.scalars(select(AutomationTaskDefinitionORM.task_key)).all()
        assert "workflow_run_execution" in refreshed


def test_seeding_does_not_overwrite_an_operator_edit(app):
    from sqlalchemy import select

    from nmrcheck.analytics_store import _ensure_default_tasks
    from nmrcheck.orm import AutomationTaskDefinitionORM

    session_factory = app.state.session_factory
    with session_factory() as session:
        row = session.scalar(
            select(AutomationTaskDefinitionORM).where(
                AutomationTaskDefinitionORM.task_key == "report_composer"
            )
        )
        assert row is not None
        row.default_minutes_saved = 3.0
        row.enabled = False
        session.commit()

        _ensure_default_tasks(session)
        session.commit()

        after = session.scalar(
            select(AutomationTaskDefinitionORM).where(
                AutomationTaskDefinitionORM.task_key == "report_composer"
            )
        )
        assert after is not None
        assert after.default_minutes_saved == 3.0
        assert after.enabled is False
