"""Repho R6 hard-block: a rejected safety screening blocks committing reactions to execution.

The project safety gate is advisory at the banner level (clear / review_pending / blocked); this
covers the *enforced* server-side precondition: moving an execution batch to planned/running is
rejected with HTTP 409 while any screening for the project stands rejected. Draft batches and
record-keeping transitions stay allowed, and a project with no screenings is unaffected.
"""

from fastapi.testclient import TestClient

_AZIDE = "CCN=[N+]=[N-]"  # energetic azide -> screening flags critical -> reviewable


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str]) -> int:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Gate", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _reject_a_screening(client, headers, pid) -> int:
    sid = client.post(
        f"/reaction-projects/{pid}/safety-screenings",
        headers=headers,
        json={"reactant_smiles": [_AZIDE], "label": "azide step"},
    ).json()["id"]
    res = client.post(
        f"/reaction-projects/{pid}/safety-screenings/{sid}/review",
        headers=headers,
        json={"decision": "rejected", "note": "Too energetic for this vessel."},
    )
    assert res.status_code == 200, res.text
    return sid


def _post_batch(client, headers, pid, code, status):
    return client.post(
        f"/reaction-projects/{pid}/execution-batches",
        headers=headers,
        json={"batch_code": code, "title": "t", "status": status},
    )


def _patch_batch(client, headers, batch_id, status):
    return client.patch(
        f"/reaction-execution-batches/{batch_id}", headers=headers, json={"status": status}
    )


def test_rejected_screening_blocks_committing_a_batch(client):
    with client:
        headers = _sign_up(client, "gate-block@example.com")
        pid = _project(client, headers)
        sid = _reject_a_screening(client, headers, pid)
        assert client.get(f"/reaction-projects/{pid}/safety-gate", headers=headers).json()[
            "status"
        ] == "blocked"

        # creating a batch already committed to execution is blocked (409)
        blocked = _post_batch(client, headers, pid, "B-planned-1", "planned")
        assert blocked.status_code == 409, blocked.text
        assert "safety gate" in blocked.json()["detail"].lower()
        assert str(sid) in blocked.json()["detail"]

        # a draft batch is planning, not a commitment -> allowed
        draft = _post_batch(client, headers, pid, "B-draft-1", "draft")
        assert draft.status_code == 201, draft.text
        draft_id = draft.json()["id"]

        # promoting the draft to planned is the commit point -> blocked (409)
        promote = _patch_batch(client, headers, draft_id, "planned")
        assert promote.status_code == 409, promote.text


def test_clearing_the_gate_unblocks_execution(client):
    with client:
        headers = _sign_up(client, "gate-clear@example.com")
        pid = _project(client, headers)
        sid = _reject_a_screening(client, headers, pid)
        draft_id = _post_batch(client, headers, pid, "B-draft-2", "draft").json()["id"]
        assert _patch_batch(client, headers, draft_id, "running").status_code == 409

        # a reviewer re-reviews the screening to approved -> gate clears
        approve = client.post(
            f"/reaction-projects/{pid}/safety-screenings/{sid}/review",
            headers=headers,
            json={"decision": "approved", "note": "Revised conditions; PHA complete."},
        )
        assert approve.status_code == 200, approve.text
        assert client.get(f"/reaction-projects/{pid}/safety-gate", headers=headers).json()[
            "status"
        ] == "clear"

        # now the commit goes through
        assert _post_batch(client, headers, pid, "B-planned-2", "planned").status_code == 201
        assert _patch_batch(client, headers, draft_id, "running").status_code == 200


def test_project_without_screenings_is_unaffected(client):
    with client:
        headers = _sign_up(client, "gate-none@example.com")
        pid = _project(client, headers)
        # no screenings -> gate clear -> committing a batch is allowed
        assert _post_batch(client, headers, pid, "B-clean-1", "running").status_code == 201


def _add_item(client, headers, batch_id, code, status="planned"):
    return client.post(
        f"/reaction-execution-batches/{batch_id}/items",
        headers=headers,
        json={"item_code": code, "status": status},
    )


def test_item_driven_batch_promotion_is_also_blocked(client):
    # Adding a 'planned' item to a draft batch auto-promotes the batch to 'planned'
    # (_refresh_batch_status). That INDIRECT commit must be gated too — not just the direct
    # batch endpoints — else the hard-block is trivially bypassed via the item endpoints.
    with client:
        headers = _sign_up(client, "gate-item@example.com")
        pid = _project(client, headers)
        _reject_a_screening(client, headers, pid)
        draft_id = _post_batch(client, headers, pid, "B-item-1", "draft").json()["id"]
        blocked = _add_item(client, headers, draft_id, "I-1", "planned")
        assert blocked.status_code == 409, blocked.text
        # the rolled-back transaction left the batch a draft (no partial commit)
        batch = client.get(
            f"/reaction-projects/{pid}/execution-batches", headers=headers
        ).json()[0]
        assert batch["status"] == "draft"


def test_mark_running_blocked_after_later_rejection(client):
    # A batch legitimately planned while the gate was clear cannot be *started* once a
    # screening is later rejected (planned -> running is a fresh bench commitment).
    with client:
        headers = _sign_up(client, "gate-run@example.com")
        pid = _project(client, headers)
        draft_id = _post_batch(client, headers, pid, "B-run-1", "draft").json()["id"]
        item = _add_item(client, headers, draft_id, "I-run-1", "planned")
        assert item.status_code == 201, item.text  # gate clear -> auto-promotes to planned
        item_id = item.json()["id"]

        _reject_a_screening(client, headers, pid)
        started = client.post(
            f"/reaction-execution-items/{item_id}/mark-running", headers=headers, json={}
        )
        assert started.status_code == 409, started.text


def test_pending_screening_does_not_block_execution(client):
    # Only a *rejected* screening hard-blocks; a pending (unreviewed) one stays advisory.
    with client:
        headers = _sign_up(client, "gate-pending@example.com")
        pid = _project(client, headers)
        client.post(
            f"/reaction-projects/{pid}/safety-screenings",
            headers=headers,
            json={"reactant_smiles": [_AZIDE], "label": "unreviewed"},
        )
        assert client.get(f"/reaction-projects/{pid}/safety-gate", headers=headers).json()[
            "status"
        ] == "review_pending"
        # commit still allowed — pending is advisory, not enforced
        assert _post_batch(client, headers, pid, "B-pending-1", "planned").status_code == 201
