"""Adoption telemetry coverage for the GSD rollup (v0.6.8).

The rollup carries ``graduated_user_count`` so the readiness panel can
render "X tenants have graduated" without round-tripping
``/admin/users``.  These tests pin three slices of the contract:

1. **Global aggregation** — count climbs as admins graduate tenants
   and falls back when they ungraduate.
2. **Per-tenant scope returns 0 / 1** — when the rollup is scoped via
   ``?actor_user_id``, the count cleanly answers "is this tenant
   graduated?".
3. **Scoped to a different tenant** — graduations of other tenants do
   not leak into the scoped count.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path) -> tuple[object, TestClient]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'gsd-adoption.sqlite3'}",
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


def _graduate(
    client: TestClient,
    admin: dict[str, str],
    user_id: int,
    graduated: bool = True,
) -> None:
    res = client.post(
        f"/admin/users/{user_id}/gsd-graduation",
        headers=admin,
        json={
            "graduated": graduated,
            "reason": "Test fixture sets graduation state.",
        },
    )
    assert res.status_code == 200, res.text


def _rollup_count(
    client: TestClient,
    admin: dict[str, str],
    *,
    actor_user_id: int | None = None,
) -> int:
    params: dict[str, int] = {"window_days": 30}
    if actor_user_id is not None:
        params["actor_user_id"] = actor_user_id
    res = client.get(
        "/spectrum/analyze/gsd/telemetry-summary",
        headers=admin,
        params=params,
    )
    assert res.status_code == 200, res.text
    return int(res.json()["graduated_user_count"])


def test_global_adoption_count_climbs_as_admins_graduate_users(tmp_path) -> None:
    """0 → 1 → 2 graduated as alice + bob graduate, drops back to 1
    when bob ungraduates."""
    _, client = _client(tmp_path)

    with client:
        admin = _sign_up_admin(client)
        alice_id = _sign_up_user(client, "alice@example.com")
        bob_id = _sign_up_user(client, "bob@example.com")

        # Baseline: zero graduated.
        assert _rollup_count(client, admin) == 0

        # Graduate alice.
        _graduate(client, admin, alice_id, graduated=True)
        assert _rollup_count(client, admin) == 1

        # Graduate bob too.
        _graduate(client, admin, bob_id, graduated=True)
        assert _rollup_count(client, admin) == 2

        # Ungraduate bob — count falls back to 1.
        _graduate(client, admin, bob_id, graduated=False)
        assert _rollup_count(client, admin) == 1


def test_scoped_rollup_returns_zero_or_one_per_tenant(tmp_path) -> None:
    """``?actor_user_id`` scope returns 0 or 1 depending on the
    targeted tenant's state — cleanly answers "is this tenant
    graduated?"."""
    _, client = _client(tmp_path)

    with client:
        admin = _sign_up_admin(client)
        alice_id = _sign_up_user(client, "alice@example.com")

        # Pre-graduation: scoped count is 0.
        assert _rollup_count(client, admin, actor_user_id=alice_id) == 0

        # Post-graduation: scoped count is 1.
        _graduate(client, admin, alice_id, graduated=True)
        assert _rollup_count(client, admin, actor_user_id=alice_id) == 1


def test_scoped_count_does_not_leak_other_tenants_graduations(tmp_path) -> None:
    """A scoped rollup for an ungraduated bob shows 0 even when alice
    is graduated (the global count would be 1, the scoped count is
    0)."""
    _, client = _client(tmp_path)

    with client:
        admin = _sign_up_admin(client)
        alice_id = _sign_up_user(client, "alice@example.com")
        bob_id = _sign_up_user(client, "bob@example.com")

        _graduate(client, admin, alice_id, graduated=True)

        assert _rollup_count(client, admin) == 1
        assert _rollup_count(client, admin, actor_user_id=alice_id) == 1
        assert _rollup_count(client, admin, actor_user_id=bob_id) == 0
