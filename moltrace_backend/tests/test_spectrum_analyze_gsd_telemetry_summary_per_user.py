"""Per-user scoping coverage for the GSD telemetry rollup.

v0.6.6 added an admin-only ``?actor_user_id`` query param so admins can
graduate individual tenants out of ``experimental: true`` ahead of the
platform-wide flip.  These tests pin the per-user filtering contract:

* The scope is self-describing — ``scope_actor_user_id`` echoes the
  query param so a cached or replayed response always carries the
  scope it was computed against.
* The aggregation only sees the targeted user's events; events from
  other users are completely invisible.
* An empty per-user window returns ``insufficient_data`` against the
  *targeted* user's invocation count, not the global count.
* Unset (no query param) reproduces the v0.6.4 global behaviour.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path) -> tuple[object, TestClient]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'gsd-per-user.sqlite3'}",
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
    """Sign up a tenant user and return (user_id, bearer-token headers)."""
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


def _synthetic_cdcl3_1h_spectrum() -> tuple[list[float], list[float]]:
    n = 4096
    ppm_lo, ppm_hi = 0.0, 10.0
    ppm = [ppm_lo + (ppm_hi - ppm_lo) * i / (n - 1) for i in range(n)]
    intensity = [0.0] * n

    def _lorentzian(centre: float, fwhm_ppm: float, height: float) -> None:
        gamma = 0.5 * fwhm_ppm
        for i, x in enumerate(ppm):
            intensity[i] += height * (gamma * gamma) / (
                (x - centre) ** 2 + gamma * gamma
            )

    _lorentzian(centre=7.26, fwhm_ppm=0.005, height=100.0)
    _lorentzian(centre=3.50, fwhm_ppm=0.005, height=60.0)
    return ppm, intensity


def _fire_gsd_call(
    client: TestClient, headers: dict[str, str], nucleus: str = "1H"
) -> None:
    ppm, intensity = _synthetic_cdcl3_1h_spectrum()
    res = client.post(
        "/spectrum/analyze/gsd",
        headers=headers,
        json={
            "ppm_axis": ppm,
            "intensity": intensity,
            "nucleus": nucleus,
            "solvent": "CDCl3",
            "field_mhz": 500.0,
            "level": 2,
        },
    )
    assert res.status_code == 200, res.text


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_per_user_scope_filters_events_to_target_user(tmp_path) -> None:
    """alice runs 3 calls, bob runs 1; scoping to alice returns 3."""
    _, client = _client(tmp_path)

    with client:
        admin_headers = _sign_up_admin(client)
        alice_id, alice_headers = _sign_up_user(client, "alice@example.com")
        bob_id, bob_headers = _sign_up_user(client, "bob@example.com")

        for _ in range(3):
            _fire_gsd_call(client, alice_headers)
        _fire_gsd_call(client, bob_headers)

        # Global rollup sees all 4
        res_global = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=admin_headers,
            params={"window_days": 30},
        )
        assert res_global.status_code == 200, res_global.text
        assert res_global.json()["invocations"] == 4
        assert res_global.json()["scope_actor_user_id"] is None

        # Per-alice rollup sees only alice's 3
        res_alice = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=admin_headers,
            params={"window_days": 30, "actor_user_id": alice_id},
        )
        assert res_alice.status_code == 200, res_alice.text
        alice_body = res_alice.json()
        assert alice_body["invocations"] == 3
        assert alice_body["scope_actor_user_id"] == alice_id

        # Per-bob rollup sees only bob's 1
        res_bob = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=admin_headers,
            params={"window_days": 30, "actor_user_id": bob_id},
        )
        assert res_bob.status_code == 200, res_bob.text
        bob_body = res_bob.json()
        assert bob_body["invocations"] == 1
        assert bob_body["scope_actor_user_id"] == bob_id


def test_per_user_scope_with_zero_events_returns_insufficient_data(
    tmp_path,
) -> None:
    """Scoping to a user with no GSD calls returns insufficient_data."""
    _, client = _client(tmp_path)

    with client:
        admin_headers = _sign_up_admin(client)
        # Bob exists but never calls the GSD endpoint.
        bob_id, _ = _sign_up_user(client, "bob@example.com")

        res = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=admin_headers,
            params={"window_days": 30, "actor_user_id": bob_id},
        )
        assert res.status_code == 200, res.text
        body = res.json()

    assert body["scope_actor_user_id"] == bob_id
    assert body["invocations"] == 0
    assert body["flip_readiness_verdict"] == "insufficient_data"
    assert "got 0" in body["flip_readiness_reasons"][0]


def test_unset_actor_user_id_returns_global_rollup(tmp_path) -> None:
    """Without ``actor_user_id``, the rollup spans every user (backcompat)."""
    _, client = _client(tmp_path)

    with client:
        admin_headers = _sign_up_admin(client)
        _alice_id, alice_headers = _sign_up_user(client, "alice@example.com")
        _bob_id, bob_headers = _sign_up_user(client, "bob@example.com")

        _fire_gsd_call(client, alice_headers)
        _fire_gsd_call(client, bob_headers)

        res = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=admin_headers,
            params={"window_days": 30},
        )
        assert res.status_code == 200, res.text
        body = res.json()

    assert body["scope_actor_user_id"] is None
    assert body["invocations"] == 2


def test_actor_user_id_query_param_validates_positive_int(tmp_path) -> None:
    """``actor_user_id=0`` is rejected (Query ge=1) without firing the query."""
    _, client = _client(tmp_path)

    with client:
        admin_headers = _sign_up_admin(client)
        res = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=admin_headers,
            params={"window_days": 30, "actor_user_id": 0},
        )
    assert res.status_code == 422, res.text


def test_actor_user_id_requires_admin(tmp_path) -> None:
    """Non-admin caller cannot use the scope param (endpoint is admin-only)."""
    _, client = _client(tmp_path)

    with client:
        _alice_id, alice_headers = _sign_up_user(client, "alice@example.com")
        res = client.get(
            "/spectrum/analyze/gsd/telemetry-summary",
            headers=alice_headers,
            params={"window_days": 30, "actor_user_id": 1},
        )
    # The endpoint's require_admin dependency returns 403 for non-admins
    # regardless of which query params they pass, so the per-user scope
    # cannot be used to bypass the auth contract.
    assert res.status_code == 403, res.text
