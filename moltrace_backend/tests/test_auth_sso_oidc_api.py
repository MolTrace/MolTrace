"""SSO (OIDC) — admin connection CRUD + the three-leg login flow against a mock IdP.

The three network legs of the OIDC flow (``discover`` / ``exchange_code`` /
``validate_id_token``) are module-level in :mod:`nmrcheck.oidc_client` precisely so they can
be monkeypatched here with a fake IdP — no real HTTP, no JWKS, deterministic claims. We still
exercise the real store/route logic: PKCE/state/nonce minting, secret encryption at rest, JIT
provisioning, single-use exchange codes, email-domain gating, and enforce-SSO.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import select

from nmrcheck import oidc_client
from nmrcheck.api import create_app
from nmrcheck.orm import OrganizationORM, SSOConnectionORM, TeamMemberORM
from nmrcheck.settings import Settings
from nmrcheck.sso_secret_crypto import decrypt_secret

SYSTEM = {"x-api-key": "test-key"}
ADMIN_EMAIL = "admin@example.com"
FRONTEND = "http://localhost:3000"

_META = oidc_client.OIDCMetadata(
    issuer="https://idp.example.com",
    authorization_endpoint="https://idp.example.com/authorize",
    token_endpoint="https://idp.example.com/token",
    jwks_uri="https://idp.example.com/jwks",
)


def _app(tmp_path):
    return create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'sso.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=(ADMIN_EMAIL,),
            frontend_base_url=FRONTEND,
            base_url="http://testserver",
            sso_encryption_key="unit-test-sso-key",
        )
    )


def _make_org(app, name: str = "Acme Pharma") -> int:
    factory = app.state.session_factory
    with factory() as session:
        org = OrganizationORM(name=name)
        session.add(org)
        session.commit()
        session.refresh(org)
        return org.id


def _connection_payload(org_id: int, **overrides) -> dict:
    payload = {
        "organization_id": org_id,
        "slug": "acme",
        "display_name": "Acme Okta",
        "issuer": "https://idp.example.com",
        "client_id": "client-abc",
        "client_secret": "s3cr3t-value",
        "email_domains": ["acme.com"],
        "enabled": True,
        "enforce_sso": False,
    }
    payload.update(overrides)
    return payload


def _install_fake_idp(monkeypatch, *, email="user@acme.com", email_verified=True):
    """Patch the three network legs to behave like a cooperating IdP."""

    def fake_discover(issuer):
        return _META

    def fake_exchange(meta, **kwargs):
        assert kwargs["code"] == "auth-code-123"
        assert kwargs["code_verifier"]  # PKCE verifier round-tripped from the flow
        return {"id_token": "fake.jwt.token", "access_token": "ignored"}

    def fake_validate(id_token, *, meta, client_id, nonce):
        # A real IdP echoes the nonce it was sent; mirror that so the store's check passes.
        claims = {"sub": "idp-subject-1", "email": email, "nonce": nonce}
        if email_verified is not None:
            claims["email_verified"] = email_verified
        return claims

    monkeypatch.setattr(oidc_client, "discover", fake_discover)
    monkeypatch.setattr(oidc_client, "exchange_code", fake_exchange)
    monkeypatch.setattr(oidc_client, "validate_id_token", fake_validate)


def _drive_login(client: TestClient, slug: str = "acme") -> str:
    """Run begin-login -> callback and return the one-time exchange code."""
    res = client.get(f"/auth/sso/{slug}/login", follow_redirects=False)
    assert res.status_code == 302, res.text
    auth_qs = parse_qs(urlparse(res.headers["location"]).query)
    assert auth_qs["code_challenge_method"] == ["S256"]
    state = auth_qs["state"][0]

    res = client.get(
        "/auth/sso/callback",
        params={"state": state, "code": "auth-code-123"},
        follow_redirects=False,
    )
    assert res.status_code == 302, res.text
    location = res.headers["location"]
    assert location.startswith(f"{FRONTEND}/auth/sso/callback")
    return parse_qs(urlparse(location).query)["code"][0]


# --------------------------------------------------------------------------- #
# Admin connection CRUD
# --------------------------------------------------------------------------- #
def test_admin_crud_never_leaks_secret_and_encrypts_at_rest(tmp_path):
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        org_id = _make_org(app)

        res = client.post(
            "/auth/sso/connections", headers=SYSTEM, json=_connection_payload(org_id)
        )
        assert res.status_code == 201, res.text
        body = res.json()
        cid = body["id"]
        assert "client_secret" not in body
        assert body["email_domains"] == ["acme.com"]

        # Secret is encrypted at rest and decrypts back to the plaintext.
        with app.state.session_factory() as session:
            row = session.get(SSOConnectionORM, cid)
            assert row.client_secret_encrypted != "s3cr3t-value"
            assert decrypt_secret(row.client_secret_encrypted, "unit-test-sso-key") == "s3cr3t-value"

        # List + get omit the secret too.
        listing = client.get("/auth/sso/connections", headers=SYSTEM).json()["connections"]
        assert [c["slug"] for c in listing] == ["acme"]
        got = client.get(f"/auth/sso/connections/{cid}", headers=SYSTEM).json()
        assert "client_secret" not in got

        # Patch rotates the secret (re-encrypted) and updates fields.
        res = client.patch(
            f"/auth/sso/connections/{cid}",
            headers=SYSTEM,
            json={"client_secret": "rotated-secret", "display_name": "Acme Okta v2"},
        )
        assert res.status_code == 200
        assert res.json()["display_name"] == "Acme Okta v2"
        with app.state.session_factory() as session:
            row = session.get(SSOConnectionORM, cid)
            assert decrypt_secret(row.client_secret_encrypted, "unit-test-sso-key") == "rotated-secret"

        # Delete.
        assert client.delete(f"/auth/sso/connections/{cid}", headers=SYSTEM).status_code == 200
        assert client.get(f"/auth/sso/connections/{cid}", headers=SYSTEM).status_code == 404


def test_connection_crud_requires_admin(tmp_path):
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        org_id = _make_org(app)
        # A normal (non-admin) bearer user is forbidden.
        signup = client.post(
            "/auth/sign-up",
            json={"email": "nobody@acme.com", "password": "password123", "password_confirm": "password123"},
        )
        assert signup.status_code == 201, signup.text
        user_headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
        res = client.post(
            "/auth/sso/connections", headers=user_headers, json=_connection_payload(org_id)
        )
        assert res.status_code == 403


def test_duplicate_slug_rejected(tmp_path):
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        org_id = _make_org(app)
        assert client.post(
            "/auth/sso/connections", headers=SYSTEM, json=_connection_payload(org_id)
        ).status_code == 201
        dup = client.post(
            "/auth/sso/connections", headers=SYSTEM, json=_connection_payload(org_id)
        )
        assert dup.status_code == 400


# --------------------------------------------------------------------------- #
# Login flow (mock IdP)
# --------------------------------------------------------------------------- #
def test_full_login_flow_jit_provisions_and_issues_bearer(tmp_path, monkeypatch):
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        org_id = _make_org(app)
        client.post("/auth/sso/connections", headers=SYSTEM, json=_connection_payload(org_id))
        _install_fake_idp(monkeypatch, email="newhire@acme.com")

        code = _drive_login(client)

        res = client.post("/auth/sso/exchange", json={"code": code})
        assert res.status_code == 200, res.text
        body = res.json()
        token = body["access_token"]
        assert body["user"]["email"] == "newhire@acme.com"

        # The minted bearer actually works.
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["email"] == "newhire@acme.com"

        # JIT created an active team membership in the connection's org.
        with app.state.session_factory() as session:
            member = session.scalar(
                select(TeamMemberORM)
                .where(TeamMemberORM.organization_id == org_id)
                .where(TeamMemberORM.user_email == "newhire@acme.com")
            )
            assert member is not None and member.status == "active"

        # The exchange code is single-use.
        assert client.post("/auth/sso/exchange", json={"code": code}).status_code == 400


def test_callback_rejects_email_outside_allowed_domains(tmp_path, monkeypatch):
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        org_id = _make_org(app)
        client.post("/auth/sso/connections", headers=SYSTEM, json=_connection_payload(org_id))
        _install_fake_idp(monkeypatch, email="intruder@evil.com")

        res = client.get("/auth/sso/acme/login", follow_redirects=False)
        state = parse_qs(urlparse(res.headers["location"]).query)["state"][0]
        cb = client.get(
            "/auth/sso/callback",
            params={"state": state, "code": "auth-code-123"},
            follow_redirects=False,
        )
        # Domain mismatch -> generic error redirect, no exchange code.
        assert cb.status_code == 302
        assert "sso_error=1" in cb.headers["location"]


def test_callback_with_idp_error_redirects_to_login(tmp_path):
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        cb = client.get(
            "/auth/sso/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )
        assert cb.status_code == 302
        assert "sso_error=1" in cb.headers["location"]


def test_unknown_exchange_code_is_rejected(tmp_path):
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        assert client.post("/auth/sso/exchange", json={"code": "not-a-real-code"}).status_code == 400


def test_login_unknown_slug_404(tmp_path):
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        assert client.get("/auth/sso/nope/login", follow_redirects=False).status_code == 404


# --------------------------------------------------------------------------- #
# enforce-SSO
# --------------------------------------------------------------------------- #
def test_enforce_sso_blocks_password_login_for_governed_domain(tmp_path):
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        org_id = _make_org(app)
        client.post(
            "/auth/sso/connections",
            headers=SYSTEM,
            json=_connection_payload(
                org_id, slug="locked", email_domains=["locked.com"], enforce_sso=True
            ),
        )
        # Create a password user on the governed domain first (sign-up is not blocked,
        # but subsequent password login is).
        signup = client.post(
            "/auth/sign-up",
            json={"email": "staff@locked.com", "password": "password123", "password_confirm": "password123"},
        )
        assert signup.status_code == 201

        res = client.post("/auth/login", json={"email": "staff@locked.com", "password": "password123"})
        assert res.status_code == 403

        # A user on a non-governed domain still logs in with a password.
        client.post(
            "/auth/sign-up",
            json={"email": "free@other.com", "password": "password123", "password_confirm": "password123"},
        )
        ok = client.post("/auth/login", json={"email": "free@other.com", "password": "password123"})
        assert ok.status_code == 200
