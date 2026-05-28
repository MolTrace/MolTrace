"""Adoption-velocity coverage for the GSD rollup (v0.6.10).

``newly_graduated_in_window`` counts unique users who had an
``admin.gsd_graduate_user`` audit event inside the rollup window,
restricted to the rollup scope.  Complement to ``graduated_user_count``
(current state).

The new field unblocks adoption-velocity charts on the readiness panel
("3 tenants graduated this quarter") without filtering the global
audit-event stream client-side.

These tests pin three contract slices:

1. Empty window → 0 newly graduated, even if other users were
   graduated *before* the window.
2. Graduations inside the window count once per unique user, even if
   the admin re-graduated the same user multiple times.
3. ``?actor_user_id`` scope is respected — graduations of other
   tenants do not surface in the scoped rollup.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path) -> tuple[object, TestClient]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'gsd-velocity.sqlite3'}",
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


def _sign_up_user(client: TestClient, email: str) -> int:
    res = client.post(
        "/auth/sign-up",
        json={
            "email": email,
            "password": "password123",
            "password_confirm": "password123",
        },
    )
    assert res.status_code == 201, res.text
    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {res.json()['access_token']}"},
    )
    assert me.status_code == 200, me.text
    return int(me.json()["id"])


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


def _rollup(
    client: TestClient,
    admin: dict[str, str],
    *,
    actor_user_id: int | None = None,
    window_days: int = 30,
) -> dict[str, object]:
    params: dict[str, int] = {"window_days": window_days}
    if actor_user_id is not None:
        params["actor_user_id"] = actor_user_id
    res = client.get(
        "/spectrum/analyze/gsd/telemetry-summary",
        headers=admin,
        params=params,
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_velocity_zero_for_empty_window(tmp_path) -> None:
    """Empty window with no graduations returns 0 newly graduated."""
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        # Sign up two users but graduate neither.
        _sign_up_user(client, "alice@example.com")
        _sign_up_user(client, "bob@example.com")
        assert _rollup(client, admin)["newly_graduated_in_window"] == 0


def test_velocity_counts_each_graduated_user_once(tmp_path) -> None:
    """Two graduations of two distinct users → 2 newly graduated."""
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        alice_id = _sign_up_user(client, "alice@example.com")
        bob_id = _sign_up_user(client, "bob@example.com")

        _set_graduation(client, admin, alice_id, graduated=True, reason="a")
        _set_graduation(client, admin, bob_id, graduated=True, reason="b")

        body = _rollup(client, admin)
        assert body["newly_graduated_in_window"] == 2
        # And the v0.6.8 current-state count agrees.
        assert body["graduated_user_count"] == 2


def test_velocity_dedups_multiple_graduate_events_for_same_user(
    tmp_path,
) -> None:
    """Graduate → ungraduate → regraduate alice inside the window
    yields newly_graduated=1 (unique-user semantic), even though there
    were two ``admin.gsd_graduate_user`` events."""
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        alice_id = _sign_up_user(client, "alice@example.com")

        _set_graduation(client, admin, alice_id, graduated=True, reason="1")
        _set_graduation(client, admin, alice_id, graduated=False, reason="2")
        _set_graduation(client, admin, alice_id, graduated=True, reason="3")

        body = _rollup(client, admin)
        # Two ``admin.gsd_graduate_user`` events, one user → counted once.
        assert body["newly_graduated_in_window"] == 1
        # Current-state count is also 1 (alice is currently graduated).
        assert body["graduated_user_count"] == 1


def test_velocity_scoped_to_actor_user_id(tmp_path) -> None:
    """Scoped rollup must not surface graduations of other tenants."""
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        alice_id = _sign_up_user(client, "alice@example.com")
        bob_id = _sign_up_user(client, "bob@example.com")

        _set_graduation(client, admin, alice_id, graduated=True, reason="a")
        _set_graduation(client, admin, bob_id, graduated=True, reason="b")

        # Global: both alice and bob graduated in window.
        global_body = _rollup(client, admin)
        assert global_body["newly_graduated_in_window"] == 2

        # Scoped to alice: just alice.
        alice_body = _rollup(client, admin, actor_user_id=alice_id)
        assert alice_body["newly_graduated_in_window"] == 1

        # Scoped to bob: just bob.
        bob_body = _rollup(client, admin, actor_user_id=bob_id)
        assert bob_body["newly_graduated_in_window"] == 1


def test_velocity_ignores_ungraduate_events(tmp_path) -> None:
    """``admin.gsd_ungraduate_user`` events do not count toward
    newly_graduated_in_window — only graduations."""
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        alice_id = _sign_up_user(client, "alice@example.com")

        # Graduate alice; current state = 1 graduated.
        _set_graduation(client, admin, alice_id, graduated=True, reason="up")
        # Ungraduate alice; current state = 0 graduated, but one
        # graduation occurred inside the window so the velocity
        # number remains 1.
        _set_graduation(client, admin, alice_id, graduated=False, reason="down")

        body = _rollup(client, admin)
        assert body["graduated_user_count"] == 0  # alice is now ungraduated
        assert body["newly_graduated_in_window"] == 1  # but graduated in window
