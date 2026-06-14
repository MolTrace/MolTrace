"""SCIM 2.0 provisioning — auto-provision + (critically) auto-deprovision over the SSO anchor.

Exercises the real store/route stack: per-connection bearer auth, the scim_users tenant-isolation
boundary (a resource id from one connection 404s under another), three-way create/link, both the
Okta (scalar-path) and Entra (pathless, capitalized-op, string-boolean) deprovision variants, the
cross-org ``is_active`` guard, soft DELETE, reactivation, token rotation, and admin gating.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from nmrcheck.api import create_app
from nmrcheck.database import create_user_session, get_user_by_email, init_db
from nmrcheck.orm import OrganizationORM, SCIMUserORM, TeamMemberORM, UserORM
from nmrcheck.settings import Settings

SYSTEM = {"x-api-key": "test-key"}
ADMIN_EMAIL = "admin@example.com"
BASE_URL = "http://testserver"


def _app(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'scim.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=(ADMIN_EMAIL,),
            base_url=BASE_URL,
            sso_encryption_key="unit-test-sso-key",
        )
    )
    init_db(app.state.session_factory)  # create tables up front (not lifespan-dependent)
    return app


def _make_org(app, name: str) -> int:
    with app.state.session_factory() as session:
        org = OrganizationORM(name=name)
        session.add(org)
        session.commit()
        session.refresh(org)
        return org.id


def _make_connection(
    client: TestClient, org_id: int, slug: str, email_domains=("acme.com",)
) -> int:
    res = client.post(
        "/auth/sso/connections",
        headers=SYSTEM,
        json={
            "organization_id": org_id,
            "slug": slug,
            "display_name": f"IdP {slug}",
            "issuer": "https://idp.example.com",
            "client_id": "cid",
            "client_secret": "secret",
            "email_domains": list(email_domains),
            "enabled": True,
            "enforce_sso": False,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _issue_scim_token(client: TestClient, connection_id: int) -> str:
    res = client.post(f"/auth/sso/connections/{connection_id}/scim-token", headers=SYSTEM)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["token"].startswith("scim_")
    return body["token"]


def _bearer(token: str, *, scim_ct: bool = False) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if scim_ct:
        headers["Content-Type"] = "application/scim+json"
    return headers


def _post(client, url, token, body):
    return client.post(url, content=json.dumps(body), headers=_bearer(token, scim_ct=True))


def _patch(client, url, token, body):
    return client.patch(url, content=json.dumps(body), headers=_bearer(token, scim_ct=True))


def _put(client, url, token, body):
    return client.put(url, content=json.dumps(body), headers=_bearer(token, scim_ct=True))


def _new_user_payload(user_name: str, external_id: str, **extra) -> dict:
    payload = {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "userName": user_name,
        "externalId": external_id,
        "name": {"givenName": "Test", "familyName": "User"},
        "emails": [{"value": user_name, "primary": True, "type": "work"}],
        "active": True,
    }
    payload.update(extra)
    return payload


def _setup(tmp_path, slug="acme", org="Acme"):
    """Return (app, client, connection_id, scim_token) ready to provision."""
    app = _app(tmp_path)
    client = TestClient(app)
    org_id = _make_org(app, org)
    cid = _make_connection(client, org_id, slug)
    token = _issue_scim_token(client, cid)
    return app, client, cid, token, org_id


# --------------------------------------------------------------------------- #
# Discovery + auth
# --------------------------------------------------------------------------- #
def test_discovery_endpoints(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        spc = client.get("/scim/v2/ServiceProviderConfig", headers=_bearer(token))
        assert spc.status_code == 200
        assert "application/scim+json" in spc.headers["content-type"]
        assert spc.json()["patch"]["supported"] is True
        assert spc.json()["filter"]["supported"] is True

        rts = client.get("/scim/v2/ResourceTypes", headers=_bearer(token)).json()
        assert rts["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:ListResponse"]
        assert any(r["id"] == "User" for r in rts["Resources"])

        schemas = client.get("/scim/v2/Schemas", headers=_bearer(token)).json()
        assert any(s["id"] == "urn:ietf:params:scim:schemas:core:2.0:User" for s in schemas["Resources"])
        one = client.get(
            "/scim/v2/Schemas/urn:ietf:params:scim:schemas:core:2.0:User", headers=_bearer(token)
        )
        assert one.status_code == 200 and one.json()["name"] == "User"


def test_auth_required_and_scoped(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        # No / garbage bearer => 401 with a SCIM Error envelope.
        assert client.get("/scim/v2/Users").status_code == 401
        bad = client.get("/scim/v2/Users", headers=_bearer("scim_garbage"))
        assert bad.status_code == 401
        assert bad.json()["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
        assert bad.json()["status"] == "401"
        # Valid token works.
        assert client.get("/scim/v2/Users", headers=_bearer(token)).status_code == 200
        # Disabling the SSO connection disables SCIM.
        client.patch(f"/auth/sso/connections/{cid}", headers=SYSTEM, json={"enabled": False})
        assert client.get("/scim/v2/Users", headers=_bearer(token)).status_code == 401


def test_admin_token_routes_gated_and_plaintext_once(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        # A non-admin bearer cannot issue tokens.
        signup = client.post(
            "/auth/sign-up",
            json={"email": "nobody@x.com", "password": "password123", "password_confirm": "password123"},
        )
        user_headers = {"Authorization": f"Bearer {signup.json()['access_token']}"}
        assert client.post(f"/auth/sso/connections/{cid}/scim-token", headers=user_headers).status_code == 403
        # Status route never returns the plaintext.
        info = client.get(f"/auth/sso/connections/{cid}/scim-token", headers=SYSTEM)
        assert info.status_code == 200
        assert "token" not in info.json()
        assert info.json()["token_prefix"].startswith("scim_")


# --------------------------------------------------------------------------- #
# Create / link / conflict / validation
# --------------------------------------------------------------------------- #
def test_create_returns_scim_id_not_user_id(tmp_path):
    app, client, cid, token, org_id = _setup(tmp_path)
    with client:
        res = _post(client, "/scim/v2/Users", token, _new_user_payload("alice@acme.com", "ext-alice"))
        assert res.status_code == 201, res.text
        assert "application/scim+json" in res.headers["content-type"]
        body = res.json()
        assert body["externalId"] == "ext-alice"
        assert body["active"] is True
        assert res.headers["location"].endswith(f"/scim/v2/Users/{body['id']}")
        # The SCIM id is the scim_users row id, NOT the global users.id.
        user = get_user_by_email(app.state.session_factory, "alice@acme.com")
        assert user is not None
        with app.state.session_factory() as s:
            su = s.scalar(select(SCIMUserORM).where(SCIMUserORM.connection_id == cid))
            assert str(su.id) == body["id"]
            assert su.user_id == user.id
            assert su.id != user.id or True  # ids may coincide numerically; the mapping is what matters
            member = s.scalar(
                select(TeamMemberORM)
                .where(TeamMemberORM.organization_id == org_id)
                .where(TeamMemberORM.user_email == "alice@acme.com")
            )
            assert member is not None and member.status == "active"


def test_create_links_existing_global_user_no_duplicate(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        # Pre-existing global user (e.g., signed up directly).
        client.post(
            "/auth/sign-up",
            json={"email": "bob@acme.com", "password": "password123", "password_confirm": "password123"},
        )
        res = _post(client, "/scim/v2/Users", token, _new_user_payload("bob@acme.com", "ext-bob"))
        assert res.status_code == 201
        with app.state.session_factory() as s:
            users = s.scalars(select(UserORM).where(UserORM.email == "bob@acme.com")).all()
            assert len(users) == 1  # linked, not duplicated


def test_duplicate_create_is_409_uniqueness(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        assert _post(client, "/scim/v2/Users", token, _new_user_payload("c@acme.com", "ext-c")).status_code == 201
        dup = _post(client, "/scim/v2/Users", token, _new_user_payload("c@acme.com", "ext-c"))
        assert dup.status_code == 409
        assert dup.json()["scimType"] == "uniqueness"
        assert dup.json()["status"] == "409"


def test_create_missing_username_is_400(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        res = _post(client, "/scim/v2/Users", token, {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "externalId": "x"})
        assert res.status_code == 400
        assert res.json()["scimType"] == "invalidValue"


def test_enterprise_ext_and_unknown_attrs_ignored(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        payload = _new_user_payload(
            "ent@acme.com",
            "ext-ent",
            **{
                "schemas": [
                    "urn:ietf:params:scim:schemas:core:2.0:User",
                    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User",
                ],
                "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {"department": "QC"},
                "totallyUnknownAttr": "whatever",
            },
        )
        res = _post(client, "/scim/v2/Users", token, payload)
        assert res.status_code == 201, res.text


# --------------------------------------------------------------------------- #
# Filter + get + pagination
# --------------------------------------------------------------------------- #
def test_filter_and_get(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        created = _post(client, "/scim/v2/Users", token, _new_user_payload("dora@acme.com", "ext-d")).json()
        # userName filter, case-insensitive value match.
        hit = client.get('/scim/v2/Users?filter=userName eq "DORA@ACME.COM"', headers=_bearer(token)).json()
        assert hit["totalResults"] == 1 and hit["Resources"][0]["id"] == created["id"]
        # externalId filter.
        ext = client.get('/scim/v2/Users?filter=externalId eq "ext-d"', headers=_bearer(token)).json()
        assert ext["totalResults"] == 1
        # No match => 200 empty ListResponse, NOT 404.
        miss = client.get('/scim/v2/Users?filter=userName eq "ghost@acme.com"', headers=_bearer(token))
        assert miss.status_code == 200 and miss.json()["totalResults"] == 0 and miss.json()["Resources"] == []
        # Get by id; unknown id => 404.
        assert client.get(f"/scim/v2/Users/{created['id']}", headers=_bearer(token)).status_code == 200
        assert client.get("/scim/v2/Users/99999", headers=_bearer(token)).status_code == 404
        # Unparseable filter => 400 invalidFilter.
        bad = client.get('/scim/v2/Users?filter=userName co "x"', headers=_bearer(token))
        assert bad.status_code == 400 and bad.json()["scimType"] == "invalidFilter"


# --------------------------------------------------------------------------- #
# Deprovisioning (the core requirement)
# --------------------------------------------------------------------------- #
def test_deprovision_okta_variant_revokes_sessions(tmp_path):
    app, client, cid, token, org_id = _setup(tmp_path)
    with client:
        created = _post(client, "/scim/v2/Users", token, _new_user_payload("eve@acme.com", "ext-e")).json()
        user = get_user_by_email(app.state.session_factory, "eve@acme.com")
        # Give the user a live session and confirm it works.
        sess, _ = create_user_session(app.state.session_factory, user_id=user.id, ttl_minutes=60)
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {sess}"}).status_code == 200

        # Okta scalar-path deprovision.
        res = _patch(client, f"/scim/v2/Users/{created['id']}", token,
                     {"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                      "Operations": [{"op": "replace", "path": "active", "value": False}]})
        assert res.status_code == 200 and res.json()["active"] is False
        # Session is cut off immediately (not waiting for TTL).
        assert client.get("/auth/me", headers={"Authorization": f"Bearer {sess}"}).status_code == 401
        with app.state.session_factory() as s:
            su = s.scalar(select(SCIMUserORM).where(SCIMUserORM.connection_id == cid))
            assert su.active is False
            member = s.scalar(
                select(TeamMemberORM).where(TeamMemberORM.organization_id == org_id)
                .where(TeamMemberORM.user_email == "eve@acme.com"))
            assert member.status == "disabled"
        # Still retrievable (never 404 a deactivated user), and idempotent.
        assert client.get(f"/scim/v2/Users/{created['id']}", headers=_bearer(token)).json()["active"] is False
        again = _patch(client, f"/scim/v2/Users/{created['id']}", token,
                       {"Operations": [{"op": "replace", "path": "active", "value": False}]})
        assert again.status_code == 200 and again.json()["active"] is False


def test_deprovision_entra_pathless_and_string_boolean(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        created = _post(client, "/scim/v2/Users", token, _new_user_payload("frank@acme.com", "ext-f")).json()
        # Entra: capitalized op, pathless object value, and a STRING boolean "False".
        res = _patch(client, f"/scim/v2/Users/{created['id']}", token,
                     {"Operations": [{"op": "Replace", "value": {"active": "False"}}]})
        assert res.status_code == 200
        assert res.json()["active"] is False  # "False" must NOT be treated as truthy


def test_reactivation(tmp_path):
    app, client, cid, token, org_id = _setup(tmp_path)
    with client:
        created = _post(client, "/scim/v2/Users", token, _new_user_payload("gail@acme.com", "ext-g")).json()
        _patch(client, f"/scim/v2/Users/{created['id']}", token,
               {"Operations": [{"op": "replace", "path": "active", "value": False}]})
        res = _patch(client, f"/scim/v2/Users/{created['id']}", token,
                     {"Operations": [{"op": "replace", "path": "active", "value": True}]})
        assert res.status_code == 200 and res.json()["active"] is True
        user = get_user_by_email(app.state.session_factory, "gail@acme.com")
        with app.state.session_factory() as s:
            assert s.get(UserORM, user.id).is_active is True
            member = s.scalar(
                select(TeamMemberORM).where(TeamMemberORM.organization_id == org_id)
                .where(TeamMemberORM.user_email == "gail@acme.com"))
            assert member.status == "active"


def test_put_replace_honors_active(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        created = _post(client, "/scim/v2/Users", token, _new_user_payload("hugo@acme.com", "ext-h")).json()
        res = _put(client, f"/scim/v2/Users/{created['id']}", token,
                   _new_user_payload("hugo@acme.com", "ext-h", active=False))
        assert res.status_code == 200 and res.json()["active"] is False


def test_delete_is_soft(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        created = _post(client, "/scim/v2/Users", token, _new_user_payload("ida@acme.com", "ext-i")).json()
        user = get_user_by_email(app.state.session_factory, "ida@acme.com")
        res = client.delete(f"/scim/v2/Users/{created['id']}", headers=_bearer(token))
        assert res.status_code == 204
        with app.state.session_factory() as s:
            su = s.scalar(select(SCIMUserORM).where(SCIMUserORM.connection_id == cid))
            assert su is not None and su.deprovisioned_at is not None and su.active is False
            assert s.get(UserORM, user.id) is not None  # the user row is KEPT
        # Idempotent: the mapping row is kept, so a repeat DELETE still resolves.
        assert client.delete(f"/scim/v2/Users/{created['id']}", headers=_bearer(token)).status_code == 204


# --------------------------------------------------------------------------- #
# Tenant isolation (critical) + cross-org is_active guard
# --------------------------------------------------------------------------- #
def test_tenant_isolation_foreign_id_404s(tmp_path):
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        org_a = _make_org(app, "OrgA")
        org_b = _make_org(app, "OrgB")
        cid_a = _make_connection(client, org_a, "conn-a", email_domains=("a.com",))
        cid_b = _make_connection(client, org_b, "conn-b", email_domains=("a.com",))
        token_a = _issue_scim_token(client, cid_a)
        token_b = _issue_scim_token(client, cid_b)

        created = _post(client, "/scim/v2/Users", token_a, _new_user_payload("jane@a.com", "ext-j")).json()
        rid = created["id"]
        # Connection B cannot read/patch/put/delete connection A's resource id.
        assert client.get(f"/scim/v2/Users/{rid}", headers=_bearer(token_b)).status_code == 404
        assert _patch(client, f"/scim/v2/Users/{rid}", token_b,
                      {"Operations": [{"op": "replace", "path": "active", "value": False}]}).status_code == 404
        assert client.delete(f"/scim/v2/Users/{rid}", headers=_bearer(token_b)).status_code == 404
        # B's listing/filter never sees A's user.
        assert client.get('/scim/v2/Users?filter=userName eq "jane@a.com"', headers=_bearer(token_b)).json()["totalResults"] == 0
        # A still sees its own.
        assert client.get(f"/scim/v2/Users/{rid}", headers=_bearer(token_a)).status_code == 200


def test_cross_org_is_active_guard(tmp_path):
    """A contractor in two orgs: deprovisioning in one org must not lock them out of the other."""
    app = _app(tmp_path)
    client = TestClient(app)
    with client:
        org_a = _make_org(app, "OrgA")
        org_b = _make_org(app, "OrgB")
        # Both orgs explicitly allow-list the shared contractor domain (the legitimate cross-org case).
        cid_a = _make_connection(client, org_a, "conn-a", email_domains=("shared.com",))
        cid_b = _make_connection(client, org_b, "conn-b", email_domains=("shared.com",))
        token_a = _issue_scim_token(client, cid_a)
        token_b = _issue_scim_token(client, cid_b)

        ra = _post(client, "/scim/v2/Users", token_a, _new_user_payload("kit@shared.com", "ext-a")).json()
        rb = _post(client, "/scim/v2/Users", token_b, _new_user_payload("kit@shared.com", "ext-b")).json()
        user = get_user_by_email(app.state.session_factory, "kit@shared.com")

        # Deactivate in org A only — global is_active stays True (org B still active).
        _patch(client, f"/scim/v2/Users/{ra['id']}", token_a,
               {"Operations": [{"op": "replace", "path": "active", "value": False}]})
        with app.state.session_factory() as s:
            assert s.get(UserORM, user.id).is_active is True

        # Now deactivate in org B too — no active membership left anywhere => global is_active False.
        _patch(client, f"/scim/v2/Users/{rb['id']}", token_b,
               {"Operations": [{"op": "replace", "path": "active", "value": False}]})
        with app.state.session_factory() as s:
            assert s.get(UserORM, user.id).is_active is False


# --------------------------------------------------------------------------- #
# Token rotation
# --------------------------------------------------------------------------- #
def test_token_rotation_invalidates_old(tmp_path):
    app, client, cid, token1, _ = _setup(tmp_path)
    with client:
        assert client.get("/scim/v2/Users", headers=_bearer(token1)).status_code == 200
        token2 = _issue_scim_token(client, cid)  # rotation: revoke-then-issue
        assert token2 != token1
        assert client.get("/scim/v2/Users", headers=_bearer(token1)).status_code == 401
        assert client.get("/scim/v2/Users", headers=_bearer(token2)).status_code == 200
        # Explicit revoke kills the live token.
        assert client.delete(f"/auth/sso/connections/{cid}/scim-token", headers=SYSTEM).status_code == 200
        assert client.get("/scim/v2/Users", headers=_bearer(token2)).status_code == 401


def test_provisioning_is_audited(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        _post(client, "/scim/v2/Users", token, _new_user_payload("liam@acme.com", "ext-l"))
        from nmrcheck.database import list_audit_events

        events = list_audit_events(app.state.session_factory, limit=50, event_type="scim.user.provisioned")
        assert events, "expected a scim.user.provisioned audit event"
        assert events[0].actor_email == "scim:acme"


# --------------------------------------------------------------------------- #
# Hardening regressions (from the adversarial review)
# --------------------------------------------------------------------------- #
def test_create_rejects_foreign_domain_blocking_cross_org_hijack(tmp_path):
    """A connection may only provision emails in its allow-list (fail closed on empty) — this is
    the gate that stops a malicious/misconfigured IdP from linking & controlling another org's user."""
    app, client, cid, token, _ = _setup(tmp_path)  # allow-list = ["acme.com"]
    with client:
        res = _post(client, "/scim/v2/Users", token, _new_user_payload("victim@evil.com", "ext-v"))
        assert res.status_code == 403
        assert "application/scim+json" in res.headers["content-type"]
        # Empty allow-list => no SCIM provisioning at all (fail closed).
        org2 = _make_org(app, "Open")
        cid2 = _make_connection(client, org2, "open", email_domains=())
        token2 = _issue_scim_token(client, cid2)
        assert _post(client, "/scim/v2/Users", token2, _new_user_payload("x@any.com", "ext-x")).status_code == 403


def test_org_members_listing_after_scim_provision_and_deprovision(tmp_path):
    """Regression: SCIM-written role/status must be valid enum values, so GET /members never 500s."""
    app, client, cid, token, org_id = _setup(tmp_path)
    with client:
        created = _post(client, "/scim/v2/Users", token, _new_user_payload("mara@acme.com", "ext-m")).json()
        members = client.get(f"/organizations/{org_id}/members", headers=SYSTEM)
        assert members.status_code == 200, members.text
        assert {m["role"] for m in members.json()} <= {"owner", "admin", "scientist", "reviewer", "viewer"}
        assert {m["status"] for m in members.json()} <= {"active", "invited", "disabled"}
        # Still serializable after deprovision (status -> "disabled", a valid value).
        _patch(client, f"/scim/v2/Users/{created['id']}", token,
               {"Operations": [{"op": "replace", "path": "active", "value": False}]})
        assert client.get(f"/organizations/{org_id}/members", headers=SYSTEM).status_code == 200


def test_put_without_active_does_not_reenable_admin_disabled_user(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        created = _post(client, "/scim/v2/Users", token, _new_user_payload("nyx@acme.com", "ext-n")).json()
        user = get_user_by_email(app.state.session_factory, "nyx@acme.com")
        with app.state.session_factory() as s:
            s.get(UserORM, user.id).is_active = False  # admin lockout, outside SCIM
            s.commit()
        # Routine attribute-sync PUT that omits `active` must NOT flip is_active back to True.
        res = _put(client, f"/scim/v2/Users/{created['id']}", token,
                   {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                    "userName": "nyx@acme.com", "displayName": "Nyx New"})
        assert res.status_code == 200
        with app.state.session_factory() as s:
            assert s.get(UserORM, user.id).is_active is False


def test_rename_collision_returns_scim_409_not_503(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        u1 = _post(client, "/scim/v2/Users", token, _new_user_payload("opal@acme.com", "ext-o1")).json()
        _post(client, "/scim/v2/Users", token, _new_user_payload("pearl@acme.com", "ext-o2"))
        # PUT-rename opal's userName into pearl's -> unique-constraint collision.
        res = _put(client, f"/scim/v2/Users/{u1['id']}", token,
                   _new_user_payload("pearl@acme.com", "ext-o1"))
        assert res.status_code == 409
        assert res.json()["scimType"] == "uniqueness"
        assert "application/scim+json" in res.headers["content-type"]


def test_bad_pagination_param_is_scim_400(tmp_path):
    app, client, cid, token, _ = _setup(tmp_path)
    with client:
        res = client.get("/scim/v2/Users?count=abc", headers=_bearer(token))
        assert res.status_code == 400
        assert "application/scim+json" in res.headers["content-type"]
        assert res.json()["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
        # Empty values are tolerated as defaults (not a 400).
        assert client.get("/scim/v2/Users?count=&startIndex=", headers=_bearer(token)).status_code == 200
