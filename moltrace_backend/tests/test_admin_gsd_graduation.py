"""Per-tenant GSD graduation flag — admin endpoint + response wiring.

v0.6.7 added ``users.gsd_graduated_at`` plus the
``POST /admin/users/{user_id}/gsd-graduation`` endpoint so admins can
graduate individual tenants out of ``experimental: true`` on the opt-in
GSD analysis backend.  These tests cover three slices:

1. The admin endpoint sets/clears the column atomically and writes a
   matching audit event with before/after state + reason.
2. The graduated tenant sees ``experimental: false`` on
   ``/spectrum/analyze/gsd`` (and in the soak telemetry event); an
   ungraduated tenant still sees ``True`` (backwards-compatible).
3. The endpoint is admin-only — a non-admin caller cannot use it.

The graduation knob is the actual action that the v0.6.6 readiness
verdict was designed to feed: read the per-tenant rollup → see
``clear`` → POST to this endpoint with a documented reason.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path) -> tuple[object, TestClient]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'gsd-graduation.sqlite3'}",
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


def _synthetic_cdcl3_1h_spectrum() -> tuple[list[float], list[float]]:
    n = 4096
    ppm_lo, ppm_hi = 0.0, 10.0
    ppm = [ppm_lo + (ppm_hi - ppm_lo) * i / (n - 1) for i in range(n)]
    intensity = [0.0] * n
    gamma = 0.5 * 0.005
    for i, x in enumerate(ppm):
        intensity[i] += 100.0 * (gamma * gamma) / (
            (x - 7.26) ** 2 + gamma * gamma
        )
        intensity[i] += 60.0 * (gamma * gamma) / (
            (x - 3.50) ** 2 + gamma * gamma
        )
    return ppm, intensity


def _fire_gsd_call(
    client: TestClient, headers: dict[str, str]
) -> dict[str, object]:
    ppm, intensity = _synthetic_cdcl3_1h_spectrum()
    res = client.post(
        "/spectrum/analyze/gsd",
        headers=headers,
        json={
            "ppm_axis": ppm,
            "intensity": intensity,
            "nucleus": "1H",
            "solvent": "CDCl3",
            "field_mhz": 500.0,
            "level": 2,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Admin endpoint contract
# ---------------------------------------------------------------------------


def test_admin_graduation_endpoint_sets_timestamp_and_audits(tmp_path) -> None:
    """``graduated=true`` writes the timestamp + an audit event."""
    _, client = _client(tmp_path)

    with client:
        admin = _sign_up_admin(client)
        alice_id, _alice_bearer = _sign_up_user(client, "alice@example.com")

        # Initially ungraduated
        res_admin_view = client.get(
            "/admin/users",
            headers=admin,
        )
        assert res_admin_view.status_code == 200, res_admin_view.text
        alice_row = next(u for u in res_admin_view.json() if u["id"] == alice_id)
        assert alice_row["gsd_graduated_at"] is None

        res = client.post(
            f"/admin/users/{alice_id}/gsd-graduation",
            headers=admin,
            json={
                "graduated": True,
                "reason": "Cleared verdict + 600 invocations soak window.",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["id"] == alice_id
        assert body["gsd_graduated_at"] is not None

        # Audit event written with structured before/after
        audit = client.get(
            "/audit/events",
            headers=admin,
            params={"event_type": "admin.gsd_graduate_user"},
        )
        assert audit.status_code == 200, audit.text
        events = audit.json()
        assert len(events) == 1
        ev = events[0]
        assert ev["entity_type"] == "user"
        assert ev["entity_id"] == alice_id
        assert ev["metadata"]["graduated"] is True
        assert ev["metadata"]["reason"].startswith("Cleared verdict")
        assert ev["metadata"]["previous_gsd_graduated_at"] is None
        assert ev["metadata"]["new_gsd_graduated_at"] is not None


def test_admin_graduation_endpoint_clears_timestamp_and_audits(tmp_path) -> None:
    """``graduated=false`` clears the column + writes the ungraduate event."""
    _, client = _client(tmp_path)

    with client:
        admin = _sign_up_admin(client)
        alice_id, _ = _sign_up_user(client, "alice@example.com")

        # Graduate, then ungraduate.
        client.post(
            f"/admin/users/{alice_id}/gsd-graduation",
            headers=admin,
            json={"graduated": True, "reason": "Initial graduation."},
        )
        res = client.post(
            f"/admin/users/{alice_id}/gsd-graduation",
            headers=admin,
            json={
                "graduated": False,
                "reason": "Demoted after CR-1234 regression.",
            },
        )
        assert res.status_code == 200, res.text
        assert res.json()["gsd_graduated_at"] is None

        audit = client.get(
            "/audit/events",
            headers=admin,
            params={"event_type": "admin.gsd_ungraduate_user"},
        )
        assert audit.status_code == 200, audit.text
        events = audit.json()
        assert len(events) == 1
        ev = events[0]
        assert ev["metadata"]["graduated"] is False
        assert ev["metadata"]["previous_gsd_graduated_at"] is not None
        assert ev["metadata"]["new_gsd_graduated_at"] is None


def test_admin_graduation_endpoint_is_idempotent_on_repeat(tmp_path) -> None:
    """Repeated ``graduated=true`` does not move the timestamp."""
    _, client = _client(tmp_path)

    with client:
        admin = _sign_up_admin(client)
        alice_id, _ = _sign_up_user(client, "alice@example.com")

        res1 = client.post(
            f"/admin/users/{alice_id}/gsd-graduation",
            headers=admin,
            json={"graduated": True, "reason": "First."},
        )
        assert res1.status_code == 200
        ts_first = res1.json()["gsd_graduated_at"]

        res2 = client.post(
            f"/admin/users/{alice_id}/gsd-graduation",
            headers=admin,
            json={"graduated": True, "reason": "Retry."},
        )
        assert res2.status_code == 200
        ts_second = res2.json()["gsd_graduated_at"]

        # Stable timestamp on idempotent re-set so dashboards' "since
        # YYYY-MM-DD" labels don't churn.
        assert ts_first == ts_second


def test_admin_graduation_endpoint_returns_404_for_unknown_user(tmp_path) -> None:
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        res = client.post(
            "/admin/users/99999/gsd-graduation",
            headers=admin,
            json={"graduated": True, "reason": "Unknown user smoke."},
        )
    assert res.status_code == 404, res.text


def test_admin_graduation_endpoint_requires_reason(tmp_path) -> None:
    """Empty / missing ``reason`` is rejected (Pydantic min_length=1)."""
    _, client = _client(tmp_path)
    with client:
        admin = _sign_up_admin(client)
        alice_id, _ = _sign_up_user(client, "alice@example.com")
        res = client.post(
            f"/admin/users/{alice_id}/gsd-graduation",
            headers=admin,
            json={"graduated": True, "reason": ""},
        )
    assert res.status_code == 422, res.text


def test_admin_graduation_endpoint_requires_admin(tmp_path) -> None:
    """Non-admin caller is rejected with 403."""
    _, client = _client(tmp_path)
    with client:
        alice_id, alice_bearer = _sign_up_user(client, "alice@example.com")
        res = client.post(
            f"/admin/users/{alice_id}/gsd-graduation",
            headers=alice_bearer,
            json={"graduated": True, "reason": "self-graduate"},
        )
    assert res.status_code == 403, res.text


# ---------------------------------------------------------------------------
# Response + telemetry wiring
# ---------------------------------------------------------------------------


def test_graduated_user_sees_experimental_false_in_response(tmp_path) -> None:
    """Alice graduates → her ``/spectrum/analyze/gsd`` call carries
    ``experimental: false``; bob stays at ``True``."""
    _, client = _client(tmp_path)

    with client:
        admin = _sign_up_admin(client)
        alice_id, alice_bearer = _sign_up_user(client, "alice@example.com")
        _bob_id, bob_bearer = _sign_up_user(client, "bob@example.com")

        # Graduate alice
        client.post(
            f"/admin/users/{alice_id}/gsd-graduation",
            headers=admin,
            json={"graduated": True, "reason": "Phase 32 smoke test."},
        )

        alice_result = _fire_gsd_call(client, alice_bearer)
        bob_result = _fire_gsd_call(client, bob_bearer)

        assert alice_result["experimental"] is False
        assert bob_result["experimental"] is True

        # Telemetry also reflects the split — admins can slice by
        # ``experimental`` in the audit stream to see graduated vs
        # still-experimental call counts.
        audit = client.get(
            "/audit/events",
            headers=admin,
            params={"event_type": "spectrum.analyze_gsd"},
        )
        assert audit.status_code == 200, audit.text
        events = audit.json()
        flags = sorted(ev["metadata"]["experimental"] for ev in events)
        assert flags == [False, True]


def test_ungraduating_returns_experimental_true(tmp_path) -> None:
    """Graduating then ungraduating restores ``experimental: true``."""
    _, client = _client(tmp_path)

    with client:
        admin = _sign_up_admin(client)
        alice_id, alice_bearer = _sign_up_user(client, "alice@example.com")

        client.post(
            f"/admin/users/{alice_id}/gsd-graduation",
            headers=admin,
            json={"graduated": True, "reason": "Try."},
        )
        graduated = _fire_gsd_call(client, alice_bearer)
        assert graduated["experimental"] is False

        client.post(
            f"/admin/users/{alice_id}/gsd-graduation",
            headers=admin,
            json={"graduated": False, "reason": "Revert."},
        )
        reverted = _fire_gsd_call(client, alice_bearer)
        assert reverted["experimental"] is True


def test_api_key_caller_stays_experimental(tmp_path) -> None:
    """An api-key caller has no user attached → response stays
    ``experimental: true`` (graduation is a per-user knob and api-key
    paths have no user to look up)."""
    _, client = _client(tmp_path)
    with client:
        res = client.post(
            "/spectrum/analyze/gsd",
            headers={"x-api-key": "test-key"},
            json={
                "ppm_axis": [float(i) for i in range(64)],
                "intensity": [1.0 for _ in range(64)],
                "nucleus": "1H",
                "solvent": "CDCl3",
                "field_mhz": 500.0,
                "level": 2,
            },
        )
        assert res.status_code == 200, res.text
        assert res.json()["experimental"] is True
