"""API tests for Repho R6 wiring: structural process-safety screening + review gate.

Covers create/list/get, the fail-safe expert-review gate (clear / review_pending / blocked),
the reviewer verdict workflow, and owner/project-scoping (non-owner gets a non-leaking 404).
"""

from fastapi.testclient import TestClient

# Ethyl azide — matches the energetic-azide SMARTS (critical) -> requires expert review.
_AZIDE = "CCN=[N+]=[N-]"
_BENIGN = "CCO"  # ethanol -> no energetic group -> review not required


def _sign_up(client: TestClient, email: str = "safety@example.com") -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Safety screen", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _screen(client, headers, pid, smiles, label="s"):
    return client.post(
        f"/reaction-projects/{pid}/safety-screenings",
        headers=headers,
        json={"reactant_smiles": [smiles], "label": label},
    )


def test_benign_screen_needs_no_review_and_gate_clear(client):
    with client:
        headers = _sign_up(client)
        pid = _project(client, headers)["id"]

        created = _screen(client, headers, pid, _BENIGN)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["overall_risk"] == "low"
        assert body["requires_expert_review"] is False
        assert body["review_status"] == "not_required"
        assert body["disclaimer"]

        gate = client.get(f"/reaction-projects/{pid}/safety-gate", headers=headers)
        assert gate.status_code == 200
        assert gate.json()["status"] == "clear"


def test_energetic_screen_blocks_gate_until_reviewed(client):
    with client:
        headers = _sign_up(client, "safety-energetic@example.com")
        pid = _project(client, headers)["id"]

        created = _screen(client, headers, pid, _AZIDE, label="nitration")
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["overall_risk"] == "critical"
        assert body["requires_expert_review"] is True
        assert body["review_status"] == "pending"
        screening_id = body["id"]
        assert "azide" in body["result_json"]["energetic_groups_found"]

        # gate is held pending review
        gate = client.get(f"/reaction-projects/{pid}/safety-gate", headers=headers).json()
        assert gate["status"] == "review_pending"
        assert screening_id in gate["blocking_screening_ids"]

        # list + get
        listed = client.get(f"/reaction-projects/{pid}/safety-screenings", headers=headers)
        assert any(s["id"] == screening_id for s in listed.json())
        fetched = client.get(
            f"/reaction-projects/{pid}/safety-screenings/{screening_id}", headers=headers
        )
        assert fetched.status_code == 200

        # approval clears the gate
        approved = client.post(
            f"/reaction-projects/{pid}/safety-screenings/{screening_id}/review",
            headers=headers,
            json={"decision": "approved", "note": "PHA completed; conditions safe at scale."},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["review_status"] == "approved"
        assert approved.json()["reviewed_at"] is not None
        gate = client.get(f"/reaction-projects/{pid}/safety-gate", headers=headers).json()
        assert gate["status"] == "clear"


def test_rejected_screen_hard_blocks_gate(client):
    with client:
        headers = _sign_up(client, "safety-reject@example.com")
        pid = _project(client, headers)["id"]
        sid = _screen(client, headers, pid, _AZIDE).json()["id"]

        rejected = client.post(
            f"/reaction-projects/{pid}/safety-screenings/{sid}/review",
            headers=headers,
            json={"decision": "rejected", "note": "Too energetic for this vessel."},
        )
        assert rejected.status_code == 200, rejected.text
        gate = client.get(f"/reaction-projects/{pid}/safety-gate", headers=headers).json()
        assert gate["status"] == "blocked"
        assert sid in gate["blocking_screening_ids"]


def test_invalid_review_decision_is_422(client):
    with client:
        headers = _sign_up(client, "safety-422@example.com")
        pid = _project(client, headers)["id"]
        sid = _screen(client, headers, pid, _AZIDE).json()["id"]
        bad = client.post(
            f"/reaction-projects/{pid}/safety-screenings/{sid}/review",
            headers=headers,
            json={"decision": "maybe"},
        )
        assert bad.status_code == 422


def test_safety_screening_is_owner_and_project_scoped(client):
    with client:
        owner = _sign_up(client, "safety-owner@example.com")
        intruder = _sign_up(client, "safety-intruder@example.com")
        pid = _project(client, owner)["id"]
        sid = _screen(client, owner, pid, _AZIDE).json()["id"]

        # non-owner -> non-leaking 404 across the surface
        assert (
            client.get(f"/reaction-projects/{pid}/safety-screenings", headers=intruder).status_code
            == 404
        )
        assert (
            client.get(f"/reaction-projects/{pid}/safety-gate", headers=intruder).status_code == 404
        )
        assert (
            client.get(
                f"/reaction-projects/{pid}/safety-screenings/{sid}", headers=intruder
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/reaction-projects/{pid}/safety-screenings/{sid}/review",
                headers=intruder,
                json={"decision": "approved"},
            ).status_code
            == 404
        )

        # a different project of the SAME owner must not reach this screening
        other_pid = _project(client, owner)["id"]
        assert (
            client.get(
                f"/reaction-projects/{other_pid}/safety-screenings/{sid}", headers=owner
            ).status_code
            == 404
        )
