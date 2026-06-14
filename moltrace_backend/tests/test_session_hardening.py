"""Session & token hardening (Prompt 4): rotating refresh tokens, reuse detection, idle/absolute
timeouts, immediate revocation, device binding, and backward compatibility.

AC#1 = a revoked session is unusable immediately; AC#2 = lifetimes/rotation are configurable +
tested. Idle/absolute timeouts are exercised by mutating the persisted rows (deterministic, no
sleep); configurability is exercised via Settings overrides.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from nmrcheck.api import create_app
from nmrcheck.database import create_user_session, get_user_by_token, init_db, revoke_token
from nmrcheck.orm import RefreshTokenORM, SessionFamilyORM, SessionTokenORM
from nmrcheck.security import token_digest
from nmrcheck.settings import Settings


def _app(tmp_path, **overrides):
    base = dict(
        database_url=f"sqlite:///{tmp_path / 'sess.sqlite3'}",
        api_key="test-key",
        require_verified_email=False,
    )
    base.update(overrides)
    app = create_app(Settings(**base))
    init_db(app.state.session_factory)
    return app


def _signup(client: TestClient, email: str) -> dict:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _login(client: TestClient, email: str, headers: dict | None = None) -> dict:
    res = client.post("/auth/login", json={"email": email, "password": "password123"}, headers=headers or {})
    assert res.status_code == 200, res.text
    return res.json()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Mint + back-compat
# --------------------------------------------------------------------------- #
def test_login_and_signup_return_refresh_token(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        su = _signup(client, "a@x.com")
        assert su["refresh_token"] and su["access_token"]  # sign-up issues both
        body = _login(client, "a@x.com")
        assert body["refresh_token"] and body["refresh_expires_at"]
        assert get_user_by_token  # access bearer still authorizes
        assert client.get("/auth/me", headers=_bearer(body["access_token"])).status_code == 200


def test_legacy_null_family_token_still_works_and_revocable(tmp_path):
    """A directly-minted (pre-0020 style, NULL family) access token validates and is revocable."""
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "leg@x.com")
        user = get_user_by_token  # noqa
        from nmrcheck.database import get_user_by_email

        uid = get_user_by_email(app.state.session_factory, "leg@x.com").id
        token, _ = create_user_session(app.state.session_factory, user_id=uid, ttl_minutes=60)
        assert client.get("/auth/me", headers=_bearer(token)).status_code == 200
        revoke_token(app.state.session_factory, token)
        assert client.get("/auth/me", headers=_bearer(token)).status_code == 401


# --------------------------------------------------------------------------- #
# Rotation + reuse detection
# --------------------------------------------------------------------------- #
def test_rotation_issues_new_pair_and_invalidates_old(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "rot@x.com")
        first = _login(client, "rot@x.com")
        res = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
        assert res.status_code == 200, res.text
        second = res.json()
        assert second["access_token"] != first["access_token"]
        assert second["refresh_token"] != first["refresh_token"]
        # Old access bearer is dead; new one works.
        assert client.get("/auth/me", headers=_bearer(first["access_token"])).status_code == 401
        assert client.get("/auth/me", headers=_bearer(second["access_token"])).status_code == 200


def test_reuse_detection_revokes_family(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "reuse@x.com")
        first = _login(client, "reuse@x.com")
        second = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
        # Replay the already-rotated (old) refresh -> reuse -> family revoked.
        replay = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
        assert replay.status_code == 401 and replay.json()["detail"] == "token_reuse_detected"
        # The whole family is dead, incl. the access from the legitimate rotation.
        assert client.get("/auth/me", headers=_bearer(second["access_token"])).status_code == 401
        # An audit event was written.
        from nmrcheck.database import list_audit_events

        assert list_audit_events(app.state.session_factory, limit=20, event_type="auth.refresh_reuse")


def test_reuse_flag_off_does_not_nuke_family(tmp_path):
    app = _app(tmp_path, refresh_reuse_revokes_family=False)
    with TestClient(app) as client:
        _signup(client, "off@x.com")
        first = _login(client, "off@x.com")
        second = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
        replay = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
        assert replay.status_code == 401  # rotated token rejected
        # ...but the family is NOT revoked: the legitimate new access still works.
        assert client.get("/auth/me", headers=_bearer(second["access_token"])).status_code == 200


def test_rotation_disabled_keeps_same_refresh(tmp_path):
    app = _app(tmp_path, refresh_rotation_enabled=False)
    with TestClient(app) as client:
        _signup(client, "norot@x.com")
        first = _login(client, "norot@x.com")
        r1 = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
        assert r1.status_code == 200 and r1.json()["refresh_token"] == first["refresh_token"]
        # The same refresh can be used again (not single-use when rotation is off).
        assert client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 200


def test_rotation_disabled_yields_single_live_bearer(tmp_path):
    """Regression: rotation-off reuses one refresh, but each refresh must SUPERSEDE the prior
    access bearer — never leave a fan-out of simultaneously-live tokens (review finding #1)."""
    app = _app(tmp_path, refresh_rotation_enabled=False)
    with TestClient(app) as client:
        _signup(client, "single@x.com")
        first = _login(client, "single@x.com")
        a1 = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
        a2 = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
        # Only the newest access bearer is live; the original and the first-refresh one are dead.
        assert client.get("/auth/me", headers=_bearer(first["access_token"])).status_code == 401
        assert client.get("/auth/me", headers=_bearer(a1["access_token"])).status_code == 401
        assert client.get("/auth/me", headers=_bearer(a2["access_token"])).status_code == 200
        # Exactly one un-revoked access row exists for the (single) login family.
        with app.state.session_factory() as s:
            fam = s.scalar(select(SessionFamilyORM).order_by(SessionFamilyORM.id.desc()))
            live = s.scalars(
                select(SessionTokenORM)
                .where(SessionTokenORM.family_id == fam.id)
                .where(SessionTokenORM.revoked_at.is_(None))
            ).all()
            assert len(live) == 1


def test_mfa_state_carried_forward_on_rotation(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "carry@x.com")
        first = _login(client, "carry@x.com")  # password login -> amr includes pwd
        second = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
        with app.state.session_factory() as s:
            row = s.scalar(
                select(SessionTokenORM).where(
                    SessionTokenORM.token_hash == token_digest(second["access_token"])
                )
            )
            assert row.amr is not None and "pwd" in row.amr


# --------------------------------------------------------------------------- #
# Immediate revocation (AC#1)
# --------------------------------------------------------------------------- #
def test_logout_revokes_family_immediately(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "lo@x.com")
        body = _login(client, "lo@x.com")
        assert client.post("/auth/logout", headers=_bearer(body["access_token"])).status_code == 200
        # Immediate (no clock advance): access dead AND the refresh can't mint a new session.
        assert client.get("/auth/me", headers=_bearer(body["access_token"])).status_code == 401
        assert client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401


def test_refresh_revoke_endpoint_kills_family(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "rv@x.com")
        body = _login(client, "rv@x.com")
        assert client.post("/auth/refresh/revoke", json={"refresh_token": body["refresh_token"]}).status_code == 200
        assert client.get("/auth/me", headers=_bearer(body["access_token"])).status_code == 401


def test_password_reset_revokes_all_families(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "pw@x.com")
        body = _login(client, "pw@x.com")
        from nmrcheck.database import get_user_by_email, revoke_all_user_tokens

        uid = get_user_by_email(app.state.session_factory, "pw@x.com").id
        revoke_all_user_tokens(app.state.session_factory, uid)  # what password-reset calls
        assert client.get("/auth/me", headers=_bearer(body["access_token"])).status_code == 401
        # The held refresh can't resurrect a session either.
        assert client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401


# --------------------------------------------------------------------------- #
# Idle + absolute timeouts (deterministic via row mutation)
# --------------------------------------------------------------------------- #
def _past(minutes: int) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


def test_idle_timeout_rejects_without_revoking_family(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "idle@x.com")
        body = _login(client, "idle@x.com")
        with app.state.session_factory() as s:
            rt = s.scalar(select(RefreshTokenORM).order_by(RefreshTokenORM.id.desc()))
            rt.expires_at = _past(1)  # idle window elapsed
            s.commit()
        res = client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
        assert res.status_code == 401 and res.json()["detail"] == "token_expired"
        with app.state.session_factory() as s:
            fam = s.scalar(select(SessionFamilyORM))
            assert fam.revoked_at is None  # idle expiry is benign, not a theft signal


def test_absolute_cap_rejects_even_with_activity(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "abs@x.com")
        body = _login(client, "abs@x.com")
        with app.state.session_factory() as s:
            # target the LOGIN family (latest), not the sign-up one
            fam = s.scalar(select(SessionFamilyORM).order_by(SessionFamilyORM.id.desc()))
            fam.absolute_expires_at = _past(1)  # hard cap exceeded
            s.commit()
        res = client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
        assert res.status_code == 401 and res.json()["detail"] == "token_expired"


# --------------------------------------------------------------------------- #
# Configurability (AC#2) + device binding
# --------------------------------------------------------------------------- #
def test_lifetimes_are_configurable(tmp_path):
    app = _app(tmp_path, access_token_ttl_minutes=15, refresh_token_absolute_minutes=120)
    with TestClient(app) as client:
        _signup(client, "cfg@x.com")
        body = _login(client, "cfg@x.com")
        access_exp = datetime.fromisoformat(body["expires_at"])
        # Access expiry honors the configured 15-minute TTL (allow a minute of slack).
        assert timedelta(minutes=14) <= access_exp - datetime.now(UTC) <= timedelta(minutes=16)
        with app.state.session_factory() as s:
            fam = s.scalar(select(SessionFamilyORM))
            cap = fam.absolute_expires_at
            cap = cap if cap.tzinfo else cap.replace(tzinfo=UTC)
            assert timedelta(minutes=118) <= cap - datetime.now(UTC) <= timedelta(minutes=122)


def test_device_binding_enforced_when_enabled(tmp_path):
    app = _app(tmp_path, session_device_binding_enabled=True)
    with TestClient(app) as client:
        ua_a = {"user-agent": "MolTraceApp/1.0 (device-A)"}
        # Same device -> refresh succeeds.
        _signup(client, "dev@x.com")
        good = _login(client, "dev@x.com", headers=ua_a)
        assert client.post(
            "/auth/refresh", json={"refresh_token": good["refresh_token"]}, headers=ua_a
        ).status_code == 200
        # Different device fingerprint on a separate login -> rejected + that family revoked.
        _signup(client, "dev2@x.com")
        victim = _login(client, "dev2@x.com", headers={"user-agent": "device-A"})
        bad = client.post(
            "/auth/refresh",
            json={"refresh_token": victim["refresh_token"]},
            headers={"user-agent": "device-B-attacker"},
        )
        assert bad.status_code == 401
        assert client.get("/auth/me", headers=_bearer(victim["access_token"])).status_code == 401


def test_invalid_refresh_token_rejected(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "inv@x.com")
        res = client.post("/auth/refresh", json={"refresh_token": "nonexistent-token-value"})
        assert res.status_code == 401 and res.json()["detail"] == "token_invalid"
