"""R9 wiring API tests — feedback capture, advisory preference ranking, A/B promotion gate.

Owner-scoped (non-leaking 404); the A/B gate is decision-support and deploys nothing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _headers(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _seed_project_with_bo(client: TestClient, headers: dict[str, str]) -> dict:
    project = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Feedback screen", "objective": "maximize_yield", "status": "active"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    ds = client.post(
        f"/reaction-projects/{project_id}/design-space",
        headers=headers,
        json={
            "numeric_variables_json": {"temperature_c": {"values": [40, 60, 80]}},
            "categorical_variables_json": {"solvent": ["MeCN", "THF"]},
        },
    )
    assert ds.status_code == 201, ds.text
    for i, (temp, solvent, y) in enumerate(
        [(40, "MeCN", 42), (60, "MeCN", 58), (80, "THF", 64), (60, "THF", 71), (80, "MeCN", 67)],
        start=1,
    ):
        exp = client.post(
            f"/reaction-projects/{project_id}/experiments",
            headers=headers,
            json={
                "experiment_code": f"FB-{i:03d}",
                "status": "completed",
                "conditions_json": {"temperature_c": temp, "solvent": solvent},
                "outcome_json": {"yield_percent": y},
            },
        )
        assert exp.status_code == 201, exp.text
    bo = client.post(
        f"/reaction-projects/{project_id}/optimization/bo/run",
        headers=headers,
        json={"algorithm": "tpe_like", "batch_size": 3},
    )
    assert bo.status_code == 201, bo.text
    return {"project_id": project_id, "bo_run_id": bo.json()["bo_run_id"]}


def test_feedback_capture_and_safety_routing(client):
    with client:
        headers = _headers(client, "fb-capture@example.com")
        seed = _seed_project_with_bo(client, headers)
        pid = seed["project_id"]

        accept = client.post(
            f"/reaction-projects/{pid}/feedback",
            headers=headers,
            json={
                "proposal_ref": "cand-1",
                "decision": "accept",
                "model_version": "bo.v1",
                "features": {"solvent": "MeCN"},
            },
        )
        assert accept.status_code == 201, accept.text
        body = accept.json()
        assert body["is_safety_signal"] is False
        assert body["is_preference_learnable"] is True
        assert body["model_version"] == "bo.v1"

        # A non-safety reject is preference-learnable.
        cost = client.post(
            f"/reaction-projects/{pid}/feedback",
            headers=headers,
            json={"proposal_ref": "cand-2", "decision": "reject", "reason": "cost"},
        )
        assert cost.status_code == 201
        assert cost.json()["is_preference_learnable"] is True

        # An unsafe reject routes to R6 hardening and is excluded from preference learning.
        unsafe = client.post(
            f"/reaction-projects/{pid}/feedback",
            headers=headers,
            json={"proposal_ref": "cand-3", "decision": "reject", "reason": "unsafe"},
        )
        assert unsafe.status_code == 201
        u = unsafe.json()
        assert u["is_safety_signal"] is True
        assert u["routes_to_safety_hardening"] is True
        assert u["is_preference_learnable"] is False

        listed = client.get(f"/reaction-projects/{pid}/feedback", headers=headers)
        assert listed.status_code == 200
        assert len(listed.json()) == 3


def test_reject_without_reason_is_422(client):
    with client:
        headers = _headers(client, "fb-422@example.com")
        seed = _seed_project_with_bo(client, headers)
        res = client.post(
            f"/reaction-projects/{seed['project_id']}/feedback",
            headers=headers,
            json={"proposal_ref": "c", "decision": "reject"},
        )
        assert res.status_code == 422, res.text


def test_preference_ranking_is_advisory_and_preserves_bo_rank(client):
    with client:
        headers = _headers(client, "fb-rank@example.com")
        seed = _seed_project_with_bo(client, headers)
        pid = seed["project_id"]
        # Some feedback so the model has signal.
        client.post(
            f"/reaction-projects/{pid}/feedback",
            headers=headers,
            json={"proposal_ref": "x", "decision": "accept", "features": {"solvent": "MeCN"}},
        )
        res = client.get(f"/reaction-projects/{pid}/preference-ranking", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["advisory"] is True
        assert body["bo_run_id"] == seed["bo_run_id"]
        assert body["model_summary"]["engine"] == "reaction_feedback.v1"
        # Ranked items carry the optimiser's original rank (annotated, not overridden).
        assert all("original_rank" in item for item in body["ranked"])


def test_ab_promotion_gate_blocks_safety_regression(client):
    with client:
        headers = _headers(client, "fb-ab@example.com")
        seed = _seed_project_with_bo(client, headers)
        pid = seed["project_id"]
        res = client.post(
            f"/reaction-projects/{pid}/ab-promotion/evaluate",
            headers=headers,
            json={
                "champion": {
                    "model_version": "v1",
                    "metrics": {"yield_percent": 70, "e_factor": 12},
                    "safety_flag_recall": 0.95,
                },
                "challenger": {
                    "model_version": "v2",
                    "metrics": {"yield_percent": 85, "e_factor": 9},
                    "safety_flag_recall": 0.90,  # regressed
                },
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["safety_regression"] is True
        assert body["promotable"] is False
        assert body["requires_human_signoff"] is True
        assert body["rollback_available"] is True


def test_ab_promotion_eligible_still_needs_signoff(client):
    with client:
        headers = _headers(client, "fb-ab2@example.com")
        seed = _seed_project_with_bo(client, headers)
        res = client.post(
            f"/reaction-projects/{seed['project_id']}/ab-promotion/evaluate",
            headers=headers,
            json={
                "champion": {
                    "model_version": "v1",
                    "metrics": {"yield_percent": 70, "e_factor": 12},
                    "safety_flag_recall": 0.95,
                },
                "challenger": {
                    "model_version": "v2",
                    "metrics": {"yield_percent": 82, "e_factor": 10},
                    "safety_flag_recall": 0.97,
                },
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["promotable"] is True
        assert body["requires_human_signoff"] is True  # never auto-deploy


def test_feedback_is_owner_scoped(client):
    with client:
        owner = _headers(client, "fb-owner@example.com")
        seed = _seed_project_with_bo(client, owner)
        pid = seed["project_id"]
        other = _headers(client, "fb-intruder@example.com")
        # A non-owner gets a non-leaking 404 on capture, list, and ranking.
        assert client.post(
            f"/reaction-projects/{pid}/feedback",
            headers=other,
            json={"proposal_ref": "c", "decision": "accept"},
        ).status_code == 404
        assert client.get(f"/reaction-projects/{pid}/feedback", headers=other).status_code == 404
        assert client.get(
            f"/reaction-projects/{pid}/preference-ranking", headers=other
        ).status_code == 404
