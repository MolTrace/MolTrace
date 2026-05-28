"""Per-tenant graduation history endpoint (v0.6.9).

``GET /admin/users/{user_id}/gsd-graduation-history`` returns the
``admin.gsd_graduate_user`` / ``admin.gsd_ungraduate_user`` audit
events for one user, newest-first.  These tests pin the contract:

1. Empty history for a freshly-created user.
2. Graduating once → one event with the documented reason + structured
   before/after state in the metadata blob.
3. Graduate → ungraduate → regraduate yields three events in
   newest-first order, each carrying the right reason and state pair.
4. Admin-only auth contract.

The history view is the auditor's primary read surface: "show me the
full graduation history for tenant alice@example.com, with the
documented reason at each transition."
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path) -> tuple[object, TestClient]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'gsd-grad-history.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=("admin@example.com",),
        )
    )
    return app, TestClient(app)


def _sign_up_admin(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={
            "email": "admin@example.com",
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _sign_up_user(client: TestClient, email: str) -> tuple[int, dict[str, str]]:
    res = client.post(
        "/auth/sign-up",
        json={
            "email": email,
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert res.status_code == 201, res.text
    bearer = {"Authorization": f"Bearer {res.json()['access_token']}"}
    me = client.get("/auth/me", headers=bearer)
    assert me.status_code == 200, me.text
    return int(me.json()["id"]), bearer


def _set_graduation(
    client: TestClient,
    admin: dict[str, str],
    user_id: int,
    *,
    graduated: bool,
    reason: str,
) -> None:
    res = client.post(
        f"/admin/users/{user_id}/gsd-graduation",
        headers=admin,
        json={"graduated": graduated, "reason": reason},
    )
    assert res.status_code == 200, res.text


def _history(
    client: TestClient,
    admin: dict[str, str],
    user_id: int,
) -> list[dict[str, object]]:
    res = client.get(
        f"/admin/users/{user_id}/gsd-graduation-history",
        headers=admin,
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_history_empty_for_fresh_user(tmp_path) -> None:
    """A user with no graduation events returns an empty list."""
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        alice_id, _ = _sign_up_user(client, "alice@example.com")
        assert _history(client, admin, alice_id) == []


def test_history_single_graduation_records_reason_and_state(tmp_path) -> None:
    """One graduation → one event with the documented reason +
    before/after state pair."""
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        alice_id, _ = _sign_up_user(client, "alice@example.com")

        _set_graduation(
            client,
            admin,
            alice_id,
            graduated=True,
            reason="500-invocation soak window cleared.",
        )

        events = _history(client, admin, alice_id)
        assert len(events) == 1
        ev = events[0]
        assert ev["event_type"] == "admin.gsd_graduate_user"
        assert ev["entity_type"] == "user"
        assert ev["entity_id"] == alice_id
        assert ev["metadata"]["graduated"] is True
        assert ev["metadata"]["reason"] == "500-invocation soak window cleared."
        assert ev["metadata"]["previous_gsd_graduated_at"] is None
        assert ev["metadata"]["new_gsd_graduated_at"] is not None


def test_history_full_sequence_newest_first_with_reasons(tmp_path) -> None:
    """Graduate → ungraduate → regraduate yields 3 events newest-first."""
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        alice_id, _ = _sign_up_user(client, "alice@example.com")

        _set_graduation(
            client, admin, alice_id, graduated=True, reason="First."
        )
        _set_graduation(
            client, admin, alice_id, graduated=False, reason="CR-1234 regression."
        )
        _set_graduation(
            client, admin, alice_id, graduated=True, reason="Regression fixed in CR-1238."
        )

        events = _history(client, admin, alice_id)
        assert len(events) == 3

        # Newest-first ordering: regraduation → ungraduation → first
        # graduation.  Reasons should land in reverse-chronological
        # order.
        reasons = [ev["metadata"]["reason"] for ev in events]
        assert reasons == [
            "Regression fixed in CR-1238.",
            "CR-1234 regression.",
            "First.",
        ]

        # Each event correctly identifies graduate vs ungraduate.
        types = [ev["event_type"] for ev in events]
        assert types == [
            "admin.gsd_graduate_user",
            "admin.gsd_ungraduate_user",
            "admin.gsd_graduate_user",
        ]


def test_history_does_not_include_other_users_events(tmp_path) -> None:
    """Querying alice's history must not surface bob's graduation."""
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        alice_id, _ = _sign_up_user(client, "alice@example.com")
        bob_id, _ = _sign_up_user(client, "bob@example.com")

        _set_graduation(client, admin, bob_id, graduated=True, reason="bob.")

        # Alice's history is empty; bob's has one event.
        assert _history(client, admin, alice_id) == []
        assert len(_history(client, admin, bob_id)) == 1


def test_history_requires_admin(tmp_path) -> None:
    """Non-admin caller is rejected with 403."""
    _, client = _client(tmp_path)
    with client:
        alice_id, alice_bearer = _sign_up_user(client, "alice@example.com")
        res = client.get(
            f"/admin/users/{alice_id}/gsd-graduation-history",
            headers=alice_bearer,
        )
        assert res.status_code == 403, res.text
