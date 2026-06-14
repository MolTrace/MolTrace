"""MFA & passkeys (Prompt 3): per-tenant enforcement (AC#1), step-up before admin/signing (AC#2),
TOTP + WebAuthn ceremonies, recovery codes, and the SSO-safe step-up rules.

WebAuthn crypto is delegated to py_webauthn; tests substitute its two verify functions
(``mfa_webauthn.verify_registration`` / ``verify_authentication``) with a synthetic authenticator,
exercising the server's challenge lifecycle, sign_count clone detection, ownership, and step-up
stamping. TOTP uses real RFC-6238 codes parsed from the enrollment URI (no time mocking).
"""

from __future__ import annotations

import base64
import types
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pyotp
from fastapi.testclient import TestClient

from nmrcheck import mfa_store, mfa_totp, mfa_webauthn
from nmrcheck.api import create_app
from nmrcheck.database import init_db
from nmrcheck.orm import OrganizationORM, TeamMemberORM
from nmrcheck.settings import Settings

SYSTEM = {"x-api-key": "test-key"}
ADMIN_EMAIL = "admin@example.com"


def _app(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'mfa.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=(ADMIN_EMAIL,),
            mfa_encryption_key="unit-test-mfa-key",
            webauthn_rp_id="localhost",
            webauthn_rp_name="MolTrace",
            webauthn_origin="http://localhost:3000",
        )
    )
    init_db(app.state.session_factory)
    return app


def _signup(client: TestClient, email: str, password: str = "password123") -> dict:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": password, "password_confirm": password},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _login(client: TestClient, email: str, password: str = "password123"):
    return client.post("/auth/login", json={"email": email, "password": password})


def _make_org(app, name: str, member_email: str | None = None) -> int:
    with app.state.session_factory() as s:
        org = OrganizationORM(name=name)
        s.add(org)
        s.commit()
        s.refresh(org)
        oid = org.id
        if member_email:
            s.add(
                TeamMemberORM(
                    organization_id=oid,
                    user_email=member_email.strip().lower(),
                    role="viewer",
                    status="active",
                )
            )
            s.commit()
        return oid


def _set_policy(client: TestClient, org_id: int, *, required: bool, grace: int = 0):
    res = client.put(
        f"/admin/mfa/policy/{org_id}",
        headers=SYSTEM,
        json={
            "mfa_required": required,
            "grace_period_days": grace,
            "allowed_factors": ["webauthn", "totp"],
            "enforce_for_sso": False,
            "require_step_up_for_signing": True,
        },
    )
    assert res.status_code == 200, res.text


def _password_step_up(client: TestClient, bearer: dict, password: str = "password123"):
    res = client.post("/auth/step-up/password", headers=bearer, json={"password": password})
    assert res.status_code == 200, res.text
    return res.json()


def _secret_from_uri(uri: str) -> str:
    return parse_qs(urlparse(uri).query)["secret"][0]


def _fresh_totp(secret: str) -> str:
    """A code for the NEXT 30s step (accepted within the +1 drift window) so it isn't rejected as a
    replay of the step consumed at enrollment/confirm."""
    return pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))


def _enroll_totp(client: TestClient, bearer: dict) -> tuple[str, list[str]]:
    """Step-up (password) then enroll + confirm TOTP. Returns (secret, recovery_codes)."""
    _password_step_up(client, bearer)
    enroll = client.post("/auth/mfa/totp/enroll", headers=bearer)
    assert enroll.status_code == 200, enroll.text
    secret = _secret_from_uri(enroll.json()["otpauth_uri"])
    confirm = client.post(
        "/auth/mfa/totp/confirm", headers=bearer, json={"code": pyotp.TOTP(secret).now()}
    )
    assert confirm.status_code == 200, confirm.text
    return secret, confirm.json()["recovery_codes"]


# --------------------------------------------------------------------------- #
# TOTP ceremony + per-tenant enforcement (AC#1)
# --------------------------------------------------------------------------- #
def test_totp_enroll_confirm_and_recovery_codes(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "tess@acme.com")
        secret, codes = _enroll_totp(client, bearer)
        assert len(codes) == 10
        status = client.get("/auth/mfa/status", headers=bearer).json()
        assert status["totp_confirmed"] is True
        assert status["recovery_remaining"] == 10


def test_enrolled_user_login_requires_second_factor(tmp_path):
    """AC#1 spine: once a user has a factor, password login yields a 202 challenge, not a bearer."""
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "tess@acme.com")
        secret, _ = _enroll_totp(client, bearer)
        # Re-login with password -> 202 (no bearer), because the user has a confirmed factor.
        res = _login(client, "tess@acme.com")
        assert res.status_code == 202, res.text
        body = res.json()
        assert body["mfa_required"] is True and "totp" in body["factors"]
        assert "access_token" not in body
        # The pending mfa_token cannot authorize an API call.
        assert client.get("/auth/mfa/status", headers={"Authorization": f"Bearer {body['mfa_token']}"}).status_code == 401
        # Trade it for a real session with a TOTP code.
        done = client.post(
            "/auth/mfa/login/totp", json={"mfa_token": body["mfa_token"], "code": _fresh_totp(secret)}
        )
        assert done.status_code == 200 and done.json()["access_token"]


def test_per_tenant_enforcement_contrast(tmp_path):
    """AC#1: a no-factor user logs in normally; with an enrolled factor + org policy the same
    login is gated. (Enforcement is the tenant policy + the factor challenge at login.)"""
    app = _app(tmp_path)
    with TestClient(app) as client:
        # No factor, no org policy -> normal 200 session.
        _signup(client, "free@other.com")
        assert _login(client, "free@other.com").status_code == 200
        # Org requires MFA; an enrolled member is challenged.
        bearer = _signup(client, "gov@acme.com")
        _make_org(app, "Acme", "gov@acme.com")
        _enroll_totp(client, bearer)
        _set_policy(client, _make_org_lookup(app, "Acme"), required=True, grace=0)
        assert _login(client, "gov@acme.com").status_code == 202


def _make_org_lookup(app, name: str) -> int:
    with app.state.session_factory() as s:
        from sqlalchemy import select

        return int(s.scalar(select(OrganizationORM.id).where(OrganizationORM.name == name)))


def test_totp_replay_guard_unit():
    secret = mfa_totp.generate_secret()
    code = pyotp.TOTP(secret).now()
    step = mfa_totp.verify(secret, code, last_used_step=None)
    assert step is not None
    assert mfa_totp.verify(secret, code, last_used_step=step) is None  # replay rejected
    assert mfa_totp.verify(secret, "000000", last_used_step=None) is None  # wrong code


def test_recovery_code_login_single_use(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "rec@acme.com")
        secret, codes = _enroll_totp(client, bearer)
        res = _login(client, "rec@acme.com")
        token = res.json()["mfa_token"]
        # Recovery-code login works once.
        ok = client.post("/auth/mfa/login/recovery", json={"mfa_token": token, "code": codes[0]})
        assert ok.status_code == 200
        # The same code cannot be reused (new login -> new token -> reuse rejected).
        token2 = _login(client, "rec@acme.com").json()["mfa_token"]
        again = client.post("/auth/mfa/login/recovery", json={"mfa_token": token2, "code": codes[0]})
        assert again.status_code == 401


# --------------------------------------------------------------------------- #
# Step-up (AC#2)
# --------------------------------------------------------------------------- #
def test_step_up_required_before_signing(tmp_path):
    """AC#2: the e-signature route demands a fresh step-up for a user bearer."""
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "signer@acme.com")
        # No step-up yet -> the signing route is gated before the body is even processed.
        blocked = client.post("/esignatures/records", headers=bearer, json={})
        assert blocked.status_code == 401 and blocked.json()["detail"] == "step_up_required"
        # System api key (operator break-glass) bypasses step-up — existing behavior preserved.
        # (A 422 for the empty body proves the step-up gate did NOT block the api-key path.)
        assert client.post("/esignatures/records", headers=SYSTEM, json={}).status_code in (400, 422)


def test_step_up_required_before_admin_mutation(tmp_path):
    """AC#2: an admin USER bearer must step up before an admin-mutating action."""
    app = _app(tmp_path)
    with TestClient(app) as client:
        # admin@example.com is in admin_emails -> login promotes to admin.
        _signup(client, ADMIN_EMAIL)
        login = _login(client, ADMIN_EMAIL)
        assert login.status_code == 200  # admin has no factor / no org policy
        admin_bearer = {"Authorization": f"Bearer {login.json()['access_token']}"}
        org_id = _make_org(app, "Acme")
        # Without step-up -> blocked.
        blocked = client.put(
            f"/admin/mfa/policy/{org_id}", headers=admin_bearer,
            json={"mfa_required": True, "grace_period_days": 0, "allowed_factors": ["totp"],
                  "enforce_for_sso": False, "require_step_up_for_signing": True},
        )
        assert blocked.status_code == 401 and blocked.json()["detail"] == "step_up_required"
        # Password step-up, then the same call succeeds.
        _password_step_up(client, admin_bearer)
        ok = client.put(
            f"/admin/mfa/policy/{org_id}", headers=admin_bearer,
            json={"mfa_required": True, "grace_period_days": 0, "allowed_factors": ["totp"],
                  "enforce_for_sso": False, "require_step_up_for_signing": True},
        )
        assert ok.status_code == 200 and ok.json()["mfa_required"] is True


def test_password_step_up_rejected_when_stronger_factor_exists(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "strong@acme.com")
        _enroll_totp(client, bearer)  # now has a TOTP factor
        # Password step-up must be refused (no downgrade); TOTP step-up is required instead.
        res = client.post("/auth/step-up/password", headers=bearer, json={"password": "password123"})
        assert res.status_code == 400


def test_totp_step_up(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "tot@acme.com")
        secret, _ = _enroll_totp(client, bearer)
        res = client.post("/auth/step-up/totp", headers=bearer, json={"code": _fresh_totp(secret)})
        assert res.status_code == 200 and res.json()["aal"] == "aal1"


# --------------------------------------------------------------------------- #
# WebAuthn / passkeys (synthetic authenticator via the verify seams)
# --------------------------------------------------------------------------- #
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _install_fake_authenticator(monkeypatch, *, cred_id=b"passkey-1"):
    """Replace py_webauthn's verify_* with a synthetic authenticator that always succeeds with UV."""
    counter = {"n": 0}

    def fake_reg(credential, *, expected_challenge, settings):
        return types.SimpleNamespace(
            credential_id=cred_id,
            credential_public_key=b"cose-public-key",
            sign_count=0,
            aaguid="00000000-0000-0000-0000-000000000000",
            credential_device_type="multi_device",
            credential_backed_up=True,
            user_verified=True,
        )

    def fake_auth(credential, *, expected_challenge, public_key, current_sign_count, settings):
        counter["n"] += 1
        return types.SimpleNamespace(
            credential_id=cred_id,
            new_sign_count=current_sign_count + counter["n"],
            credential_device_type="multi_device",
            credential_backed_up=True,
            user_verified=True,
        )

    monkeypatch.setattr(mfa_webauthn, "verify_registration", fake_reg)
    monkeypatch.setattr(mfa_webauthn, "verify_authentication", fake_auth)
    return cred_id


def _assertion(cred_id: bytes) -> dict:
    rid = _b64(cred_id)
    return {"id": rid, "rawId": rid, "type": "public-key", "response": {}}


def test_webauthn_register_and_login(tmp_path, monkeypatch):
    app = _app(tmp_path)
    cred_id = _install_fake_authenticator(monkeypatch)
    with TestClient(app) as client:
        bearer = _signup(client, "passkey@acme.com")
        _password_step_up(client, bearer)
        # Register: options then verify.
        opts = client.post("/auth/mfa/webauthn/register/options", headers=bearer)
        assert opts.status_code == 200 and "challenge" in opts.json()
        verify = client.post(
            "/auth/mfa/webauthn/register/verify",
            headers=bearer,
            json={"credential": {"id": _b64(cred_id), "rawId": _b64(cred_id), "type": "public-key",
                                 "response": {}}, "nickname": "My Key"},
        )
        assert verify.status_code == 200, verify.text
        creds = client.get("/auth/mfa/webauthn/credentials", headers=bearer).json()["credentials"]
        assert len(creds) == 1 and creds[0]["nickname"] == "My Key"
        # Login now challenges for the passkey; assertion completes it.
        res = _login(client, "passkey@acme.com")
        assert res.status_code == 202 and "webauthn" in res.json()["factors"]
        done = client.post(
            "/auth/mfa/login/webauthn",
            json={"mfa_token": res.json()["mfa_token"], "assertion": _assertion(cred_id)},
        )
        assert done.status_code == 200 and done.json()["access_token"]


def test_webauthn_step_up_and_clone_detection(tmp_path, monkeypatch):
    app = _app(tmp_path)
    cred_id = _install_fake_authenticator(monkeypatch)
    with TestClient(app) as client:
        bearer = _signup(client, "clone@acme.com")
        _password_step_up(client, bearer)
        client.post("/auth/mfa/webauthn/register/options", headers=bearer)
        client.post(
            "/auth/mfa/webauthn/register/verify", headers=bearer,
            json={"credential": _assertion(cred_id), "nickname": "K"},
        )
        # Passkey step-up (aal2).
        client.post("/auth/step-up/options", headers=bearer)
        up = client.post("/auth/step-up/webauthn", headers=bearer, json={"assertion": _assertion(cred_id)})
        assert up.status_code == 200 and up.json()["aal"] == "aal2"

        # Clone detection: force the verify seam to return a NON-advancing sign_count.
        monkeypatch.setattr(
            mfa_webauthn, "verify_authentication",
            lambda credential, **kw: types.SimpleNamespace(
                credential_id=cred_id, new_sign_count=0, credential_device_type="multi_device",
                credential_backed_up=True, user_verified=True),
        )
        client.post("/auth/step-up/options", headers=bearer)
        cloned = client.post("/auth/step-up/webauthn", headers=bearer, json={"assertion": _assertion(cred_id)})
        assert cloned.status_code == 401  # sign_count did not advance -> rejected


def test_webauthn_uv_required(tmp_path, monkeypatch):
    """An assertion where UV was not performed is rejected at our layer (defense in depth)."""
    app = _app(tmp_path)
    cred_id = b"uvkey"
    _install_fake_authenticator(monkeypatch, cred_id=cred_id)
    with TestClient(app) as client:
        bearer = _signup(client, "uv@acme.com")
        _password_step_up(client, bearer)
        client.post("/auth/mfa/webauthn/register/options", headers=bearer)
        client.post(
            "/auth/mfa/webauthn/register/verify", headers=bearer,
            json={"credential": _assertion(cred_id), "nickname": "K"},
        )
        monkeypatch.setattr(
            mfa_webauthn, "verify_authentication",
            lambda credential, **kw: types.SimpleNamespace(
                credential_id=cred_id, new_sign_count=99, credential_device_type="multi_device",
                credential_backed_up=True, user_verified=False),
        )
        client.post("/auth/step-up/options", headers=bearer)
        res = client.post("/auth/step-up/webauthn", headers=bearer, json={"assertion": _assertion(cred_id)})
        assert res.status_code == 400  # UV not performed


# --------------------------------------------------------------------------- #
# Policy admin + enforcement evaluation
# --------------------------------------------------------------------------- #
def test_policy_get_default_and_set(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        org_id = _make_org(app, "Acme")
        default = client.get(f"/admin/mfa/policy/{org_id}", headers=SYSTEM).json()
        assert default["mfa_required"] is False
        _set_policy(client, org_id, required=True, grace=14)
        updated = client.get(f"/admin/mfa/policy/{org_id}", headers=SYSTEM).json()
        assert updated["mfa_required"] is True and updated["grace_period_days"] == 14


def test_mfa_token_is_single_attempt_no_bruteforce(tmp_path):
    """A wrong factor attempt BURNS the pending mfa_token (no unlimited-retry brute-force oracle)."""
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "bf@acme.com")
        secret, _ = _enroll_totp(client, bearer)
        token = _login(client, "bf@acme.com").json()["mfa_token"]
        wrong = client.post("/auth/mfa/login/totp", json={"mfa_token": token, "code": "000000"})
        assert wrong.status_code == 401
        # Same token with a now-correct code must be rejected — it was burned by the failed attempt.
        retry = client.post("/auth/mfa/login/totp", json={"mfa_token": token, "code": _fresh_totp(secret)})
        assert retry.status_code == 400  # invalid/already-used token


def test_per_tenant_mfa_blocks_product_routes(tmp_path):
    """AC#1: a no-factor user in an MFA-required org is blocked on product routes (but /auth/* stays
    open so they can enroll)."""
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "blocked@acme.com")
        _make_org(app, "Acme", "blocked@acme.com")
        _set_policy(client, _make_org_lookup(app, "Acme"), required=True, grace=0)
        # A product route (require_access_context) is blocked until MFA is satisfied.
        blocked = client.get("/esignatures/records", headers=bearer)
        assert blocked.status_code == 403 and blocked.json()["detail"] == "mfa_enrollment_required"
        # The MFA/enrollment surface stays reachable.
        assert client.get("/auth/mfa/status", headers=bearer).status_code == 200
        # After enrolling a factor + a fresh step-up, the product route is allowed.
        _enroll_totp(client, bearer)
        assert client.get("/esignatures/records", headers=bearer).status_code == 200


def test_mfa_satisfied_for_session_unit(tmp_path):
    """The require_mfa_satisfied evaluation: required org + no strong amr/step-up -> blocked."""
    app = _app(tmp_path)
    settings = app.state.settings
    sf = app.state.session_factory
    with TestClient(app) as client:
        bearer = _signup(client, "ev@acme.com")
        org_id = _make_org(app, "Acme", "ev@acme.com")
        _set_policy(client, org_id, required=True, grace=0)
        from nmrcheck.database import get_user_by_token

        raw = bearer["Authorization"].split(" ", 1)[1]
        user = get_user_by_token(sf, raw)
        ok, detail = mfa_store.mfa_satisfied_for_session(
            sf, settings, user_id=user.id, email=user.email, raw_token=raw
        )
        assert ok is False and detail == "mfa_enrollment_required"
        # After enrolling + a fresh step-up, the session is satisfied.
        _enroll_totp(client, bearer)
        ok2, _ = mfa_store.mfa_satisfied_for_session(
            sf, settings, user_id=user.id, email=user.email, raw_token=raw
        )
        assert ok2 is True  # the password step-up during enroll stamped a fresh step-up
