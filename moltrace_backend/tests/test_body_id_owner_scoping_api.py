"""Owner-scoping for routes whose owner-relevant id is carried in the request BODY.

The path-based ``require_reaction_access`` gate and the ``/regulatory/dossiers/{id}`` gates
cannot reach body ids, so an adversarial review confirmed five cross-tenant holes remain after
the landed cross-module fix (commit ``7a8a52d``). Each test below pins the contract: a non-owner
user gets a non-leaking 404; the owner is not over-restricted; the system api-key remains
unrestricted (the broader ``test_phase60_product_orchestration_api`` / system-key suites cover
that already, but the cases below pin the user-flow contract that 7a8a52d's tests do not).
"""

from fastapi.testclient import TestClient


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _me(client: TestClient, headers: dict[str, str]) -> int:
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200, res.text
    return int(res.json()["id"])


# --------------------------------------------------------------------------- #
# Hole 1: POST /reaction-projects — body ``owner_id`` is honored unchecked. A user could
# create a project owned by another user. The fix forces ``owner_id = caller.user_id`` when the
# caller is user-scoped; a system api-key / admin (covered by phase60) stays unrestricted.
# --------------------------------------------------------------------------- #
def test_user_cannot_create_a_reaction_project_owned_by_another_user(client):
    with client:
        attacker = _sign_up(client, "attacker@example.com")
        victim = _sign_up(client, "victim@example.com")
        victim_id = _me(client, victim)

        # The attacker tries to plant a project owned by the victim.
        res = client.post(
            "/reaction-projects",
            headers=attacker,
            json={
                "name": "Stolen",
                "objective": "maximize_yield",
                "status": "active",
                "owner_id": victim_id,
            },
        )
        assert res.status_code == 201, res.text
        attacker_id = _me(client, attacker)
        assert res.json()["owner_id"] == attacker_id, (
            "body owner_id must be ignored for a user-scoped caller — the project is forced "
            "to the caller. Returning owner_id == victim_id would mean an attacker can plant "
            "rows in the victim's tenant."
        )

        # The list endpoint must NOT show the project under the victim's scope.
        v_list = client.get("/reaction-projects", headers=victim).json()
        assert all(p["id"] != res.json()["id"] for p in v_list), (
            "the planted project must not appear in the victim's owner-scoped list"
        )


def test_user_can_still_create_a_reaction_project_with_no_owner_id_in_body(client):
    """The body-owner_id-omitted path stays the happy path (owner == caller)."""
    with client:
        owner = _sign_up(client, "happy-owner@example.com")
        owner_id = _me(client, owner)
        res = client.post(
            "/reaction-projects",
            headers=owner,
            json={"name": "Mine", "objective": "maximize_yield", "status": "active"},
        )
        assert res.status_code == 201, res.text
        assert res.json()["owner_id"] == owner_id


def test_user_can_create_a_reaction_project_with_their_own_owner_id_in_body(client):
    """A user-scoped caller passing their OWN id as body owner_id is fine (no-op)."""
    with client:
        owner = _sign_up(client, "selfid@example.com")
        owner_id = _me(client, owner)
        res = client.post(
            "/reaction-projects",
            headers=owner,
            json={
                "name": "Self",
                "objective": "maximize_yield",
                "status": "active",
                "owner_id": owner_id,
            },
        )
        assert res.status_code == 201, res.text
        assert res.json()["owner_id"] == owner_id
