"""API tests for Repho R5 wiring: the human-gated propose-next step of the DMTA loop.

Only a 'continue_optimization' cycle decision may propose the next batch; the proposal produces a
NEW DRAFT cycle (decision-support) and executes nothing. A held/stopped/undecided loop returns 409.
"""

from fastapi.testclient import TestClient


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client, headers) -> int:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Loop", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _make_runnable(client, headers, pid):
    """Design space + objective + one completed experiment so a BO run can produce a proposal."""
    assert client.post(
        f"/reaction-projects/{pid}/design-space",
        headers=headers,
        json={
            "numeric_variables_json": {"temperature_c": {"values": [40, 60, 80]}},
            "categorical_variables_json": {"solvent": ["MeCN", "THF"], "catalyst": ["Cat-A", "Cat-B"]},
            "fixed_conditions_json": {"base": "K2CO3"},
        },
    ).status_code == 201
    assert client.post(
        f"/reaction-projects/{pid}/objective-profile",
        headers=headers,
        json={"objective_type": "maximize_yield", "weights_json": {"yield_weight": 1.0}},
    ).status_code == 201
    assert client.post(
        f"/reaction-projects/{pid}/experiments",
        headers=headers,
        json={
            "experiment_code": "L-001",
            "status": "completed",
            "conditions_json": {"temperature_c": 60, "solvent": "MeCN", "catalyst": "Cat-A"},
            "outcome_json": {"yield_percent": 55.0, "impurity_percent": 6.0},
        },
    ).status_code == 201


def _cycle(client, headers, pid) -> int:
    res = client.post(
        f"/reaction-projects/{pid}/optimization-cycles", headers=headers, json={"status": "running"}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _decide(client, headers, cycle_id, decision):
    return client.post(
        f"/reaction-optimization-cycles/{cycle_id}/decision",
        headers=headers,
        json={"decision": decision, "rationale": "test"},
    )


def _propose(client, headers, cycle_id):
    return client.post(
        f"/reaction-optimization-cycles/{cycle_id}/propose-next", headers=headers, json={}
    )


def test_propose_next_blocked_without_a_continue_decision(client):
    with client:
        headers = _sign_up(client, "loop-block@example.com")
        pid = _project(client, headers)
        cycle_id = _cycle(client, headers, pid)

        # no decision recorded yet -> blocked
        none_yet = _propose(client, headers, cycle_id)
        assert none_yet.status_code == 409, none_yet.text
        assert "No cycle decision" in none_yet.json()["detail"]

        # a pause decision -> blocked
        assert _decide(client, headers, cycle_id, "pause").status_code == 201
        paused = _propose(client, headers, cycle_id)
        assert paused.status_code == 409, paused.text
        assert "pause" in paused.json()["detail"]


def test_continue_decision_proposes_a_draft_cycle_without_executing(client):
    with client:
        headers = _sign_up(client, "loop-go@example.com")
        pid = _project(client, headers)
        _make_runnable(client, headers, pid)
        cycle_id = _cycle(client, headers, pid)
        assert _decide(client, headers, cycle_id, "continue_optimization").status_code == 201

        proposed = _propose(client, headers, cycle_id)
        assert proposed.status_code == 201, proposed.text
        body = proposed.json()
        # a NEW draft cycle — nothing auto-executed
        assert body["id"] != cycle_id
        assert body["status"] == "draft"
        assert body["bo_run_id"] is not None
        meta = body["metadata_json"]
        assert meta["proposed_from_cycle_id"] == cycle_id
        assert meta["propose_next"]["requires_human_signoff_before_execution"] is True
        assert "cycle_metrics" in meta
        assert meta["cycle_metrics"]["provenance"]["bo_run_id"] == body["bo_run_id"]


def test_propose_next_is_owner_scoped(client):
    with client:
        owner = _sign_up(client, "loop-owner@example.com")
        intruder = _sign_up(client, "loop-intruder@example.com")
        pid = _project(client, owner)
        cycle_id = _cycle(client, owner, pid)
        assert _decide(client, owner, cycle_id, "continue_optimization").status_code == 201
        # non-owner cannot reach another tenant's cycle -> non-leaking 404
        assert _propose(client, intruder, cycle_id).status_code == 404
