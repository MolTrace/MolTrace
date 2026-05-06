from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'reaction_execution.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    return TestClient(app)


def _sign_up(client: TestClient, email: str = "phase52@example.com") -> dict[str, str]:
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


def _project(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={
            "name": "Closed-loop execution screen",
            "objective": "maximize_yield",
            "status": "active",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _batch(client: TestClient, headers: dict[str, str], project_id: int, code: str = "BATCH-001") -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/execution-batches",
        headers=headers,
        json={
            "batch_code": code,
            "title": "Phase 52 planned experiment batch",
            "status": "draft",
            "created_by": "Reviewer",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _experiment(client: TestClient, headers: dict[str, str], project_id: int, code: str = "RXN-001") -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/experiments",
        headers=headers,
        json={
            "experiment_code": code,
            "status": "planned",
            "conditions_json": {
                "temperature_c": 60,
                "solvent": "MeCN",
                "catalyst": "Cat-A",
            },
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _item(
    client: TestClient,
    headers: dict[str, str],
    batch_id: int,
    *,
    experiment_id: int | None = None,
    item_code: str = "ITEM-001",
) -> dict:
    body = {
        "item_code": item_code,
        "conditions_json": {
            "temperature_c": 60,
            "solvent": "MeCN",
            "catalyst": "Cat-A",
        },
        "checklist_json": [{"label": "human review completed", "done": False}],
    }
    if experiment_id is not None:
        body["experiment_id"] = experiment_id
    res = client.post(
        f"/reaction-execution-batches/{batch_id}/items",
        headers=headers,
        json=body,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _approved_recommendation(client: TestClient, headers: dict[str, str], project_id: int) -> dict:
    rec = client.post(
        f"/reaction-projects/{project_id}/recommendations",
        headers=headers,
        json={
            "rank": 1,
            "conditions_json": {
                "temperature_c": 65,
                "solvent": "MeCN",
                "catalyst": "Cat-A",
            },
            "predicted_outcome_json": {"predicted_score": 72},
            "uncertainty_json": {"confidence_label": "requires_review"},
            "rationale": "Chemically reasonable planned experiment candidate for reviewer approval.",
            "label": "requires_human_review",
        },
    )
    assert rec.status_code == 201, rec.text
    approved = client.post(
        f"/reaction-recommendations/{rec.json()['id']}/approve",
        headers=headers,
        json={
            "reviewer_name": "Reviewer",
            "rationale": "Reviewed by a chemist before conversion to a planned experiment.",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    return approved.json()


def test_create_execution_batch_and_add_item(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "phase52-batch@example.com")
        project = _project(client, headers)

        batch = _batch(client, headers, project["id"])
        assert batch["reaction_project_id"] == project["id"]
        assert batch["human_review_required"] is True

        item = _item(client, headers, batch["id"])
        assert item["execution_batch_id"] == batch["id"]
        assert item["status"] == "planned"
        assert item["conditions_json"]["solvent"] == "MeCN"

        listed = client.get(f"/reaction-execution-batches/{batch['id']}/items", headers=headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()[0]["id"] == item["id"]


def test_convert_approved_recommendation_to_planned_experiment(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "phase52-convert@example.com")
        project = _project(client, headers)
        batch = _batch(client, headers, project["id"])
        rec = _approved_recommendation(client, headers, project["id"])

        converted = client.post(
            f"/reaction-recommendations/{rec['id']}/convert-to-experiment",
            headers=headers,
            json={
                "execution_batch_id": batch["id"],
                "item_code": "ITEM-CONVERTED",
                "reviewer_name": "Reviewer",
                "rationale": "Recommendation was approved and converted to a planned experiment.",
            },
        )
        assert converted.status_code == 201, converted.text
        body = converted.json()
        assert body["recommendation_id"] == rec["id"]
        assert body["experiment"]["status"] == "planned"
        assert body["execution_item"]["experiment_id"] == body["experiment"]["id"]
        assert body["event"]["event_type"] == "planned"


def test_mark_execution_item_running_completed_and_failed(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "phase52-status@example.com")
        project = _project(client, headers)
        batch = _batch(client, headers, project["id"])
        experiment = _experiment(client, headers, project["id"])
        item = _item(client, headers, batch["id"], experiment_id=experiment["id"])

        running = client.post(
            f"/reaction-execution-items/{item['id']}/mark-running",
            headers=headers,
            json={"operator_name": "Operator", "message": "Planned experiment started."},
        )
        assert running.status_code == 200, running.text
        assert running.json()["status"] == "running"

        completed = client.post(
            f"/reaction-execution-items/{item['id']}/mark-completed",
            headers=headers,
            json={"operator_name": "Operator", "message": "Completed experiment recorded."},
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "completed"

        failed_item = _item(client, headers, batch["id"], item_code="ITEM-FAILED")
        failed = client.post(
            f"/reaction-execution-items/{failed_item['id']}/mark-failed",
            headers=headers,
            json={"failure_reason": "Vial broke before workup."},
        )
        assert failed.status_code == 200, failed.text
        assert failed.json()["status"] == "failed"
        assert failed.json()["failure_reason"] == "Vial broke before workup."


def test_add_analytical_result_extract_and_confirm_outcome(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "phase52-outcome@example.com")
        project = _project(client, headers)
        batch = _batch(client, headers, project["id"])
        rec = _approved_recommendation(client, headers, project["id"])
        converted = client.post(
            f"/reaction-recommendations/{rec['id']}/convert-to-experiment",
            headers=headers,
            json={
                "execution_batch_id": batch["id"],
                "item_code": "ITEM-OUTCOME",
                "rationale": "Approved recommendation converted before execution tracking.",
            },
        )
        assert converted.status_code == 201, converted.text
        item = converted.json()["execution_item"]
        completed = client.post(
            f"/reaction-execution-items/{item['id']}/mark-completed",
            headers=headers,
            json={"message": "Completed experiment recorded before outcome confirmation."},
        )
        assert completed.status_code == 200, completed.text

        result = client.post(
            f"/reaction-execution-items/{item['id']}/analytical-results",
            headers=headers,
            json={
                "result_type": "lcms",
                "summary_json": {
                    "yield_percent": 66.4,
                    "conversion_percent": 81.2,
                    "selectivity_percent": 74.5,
                    "impurity_percent": 6.1,
                    "lcms_area_percent": 69.8,
                },
                "qc_status": "requires_review",
            },
        )
        assert result.status_code == 201, result.text
        assert result.json()["summary_json"]["yield_percent"] == 66.4

        extraction = client.post(
            f"/reaction-execution-items/{item['id']}/extract-outcome",
            headers=headers,
            json={"extraction_method": "lcms_area", "analytical_result_id": result.json()["id"]},
        )
        assert extraction.status_code == 201, extraction.text
        extracted = extraction.json()
        assert extracted["status"] == "requires_review"
        assert extracted["human_review_required"] is True
        assert extracted["proposed_outcome_json"]["yield_percent"] == 66.4
        assert "requires confirmation" in " ".join(extracted["notes"]).lower()

        fetched = client.get(
            f"/reaction-outcome-extraction-runs/{extracted['id']}",
            headers=headers,
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["id"] == extracted["id"]

        confirmed = client.post(
            f"/reaction-execution-items/{item['id']}/confirm-outcome",
            headers=headers,
            json={
                "extraction_run_id": extracted["id"],
                "reviewer_name": "Reviewer",
                "rationale": "Analytical evidence reviewed; outcome values accepted with caveats.",
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        body = confirmed.json()
        assert body["status"] == "completed"
        assert body["outcome_json"]["yield_percent"] == 66.4
        assert body["outcome"]["conversion_percent"] == 81.2


def test_optimization_cycle_can_be_created_listed_and_decision_requires_rationale(tmp_path):
    client = _client(tmp_path)
    with client:
        headers = _sign_up(client, "phase52-cycle@example.com")
        project = _project(client, headers)
        batch = _batch(client, headers, project["id"])

        cycle = client.post(
            f"/reaction-projects/{project['id']}/optimization-cycles",
            headers=headers,
            json={"execution_batch_id": batch["id"], "status": "requires_review"},
        )
        assert cycle.status_code == 201, cycle.text
        body = cycle.json()
        assert body["cycle_number"] == 1
        assert body["execution_batch_id"] == batch["id"]
        assert body["human_review_required"] is True

        listed = client.get(
            f"/reaction-projects/{project['id']}/optimization-cycles",
            headers=headers,
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()[0]["id"] == body["id"]

        missing_rationale = client.post(
            f"/reaction-optimization-cycles/{body['id']}/decision",
            headers=headers,
            json={"decision": "continue_optimization"},
        )
        assert missing_rationale.status_code == 422, missing_rationale.text

        decision = client.post(
            f"/reaction-optimization-cycles/{body['id']}/decision",
            headers=headers,
            json={
                "decision": "continue_optimization",
                "rationale": "Continue because additional reviewed outcomes are needed.",
                "reviewer_name": "Reviewer",
            },
        )
        assert decision.status_code == 201, decision.text
        assert decision.json()["decision"] == "continue_optimization"


def test_phase52_openapi_includes_execution_and_feedback_endpoints(tmp_path):
    client = _client(tmp_path)
    with client:
        res = client.get("/openapi.json")
    assert res.status_code == 200, res.text
    paths = res.json()["paths"]
    for path in [
        "/reaction-projects/{reaction_project_id}/execution-batches",
        "/reaction-execution-batches/{batch_id}",
        "/reaction-execution-batches/{batch_id}/items",
        "/reaction-execution-items/{item_id}",
        "/reaction-recommendations/{recommendation_id}/convert-to-experiment",
        "/reaction-execution-items/{item_id}/mark-running",
        "/reaction-execution-items/{item_id}/mark-completed",
        "/reaction-execution-items/{item_id}/mark-failed",
        "/reaction-execution-items/{item_id}/analytical-results",
        "/reaction-execution-items/{item_id}/extract-outcome",
        "/reaction-outcome-extraction-runs/{extraction_run_id}",
        "/reaction-execution-items/{item_id}/confirm-outcome",
        "/reaction-projects/{reaction_project_id}/optimization-cycles",
        "/reaction-optimization-cycles/{cycle_id}",
        "/reaction-optimization-cycles/{cycle_id}/decision",
    ]:
        assert path in paths
    assert "post" in paths["/reaction-projects/{reaction_project_id}/execution-batches"]
    assert "patch" in paths["/reaction-execution-items/{item_id}"]
