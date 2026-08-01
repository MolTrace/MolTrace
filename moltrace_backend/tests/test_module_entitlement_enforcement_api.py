"""Module entitlements actually enforce (handoff: handoff_entitlement_enforcement.md).

The tenant is resolved server-side from the caller's ORGANIZATION MEMBERSHIP — never from a
self-asserted ``x-tenant-id`` header. Semantics are ALLOW-BY-DEFAULT honoring explicit denials:

* an org unbound to a tenant, or a tenant with no entitlement row, stays open;
* an explicit ``enabled=false`` entitlement blocks WRITES to that module (403 ``module_not_entitled``);
* READS are always preserved (ALCOA+/Part 11 retention);
* operators (system api key / admin) are unrestricted.

Also pins the item-1 security fix: a non-member can no longer read a tenant's entitlements by
asserting a matching ``x-tenant-id`` header.
"""

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

SYSTEM = {"x-api-key": "test-key"}
ADMIN_EMAIL = "admin@example.com"


def _app(tmp_path):
    return create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'entitlement_enforce.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=(ADMIN_EMAIL,),
        )
    )


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_tenant(client: TestClient, key: str = "pilot-alpha") -> int:
    res = client.post(
        "/tenants",
        headers=SYSTEM,
        json={
            "tenant_key": key,
            "display_name": "Pilot Alpha",
            "tenant_type": "pilot",
            "status": "onboarding",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _create_org(client: TestClient, headers: dict[str, str], name: str) -> int:
    res = client.post("/organizations", headers=headers, json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _link(client: TestClient, tenant_id: int, org_id: int) -> dict:
    res = client.put(f"/tenants/{tenant_id}/organizations/{org_id}", headers=SYSTEM)
    assert res.status_code == 200, res.text
    return res.json()


def _deny(client: TestClient, tenant_id: int, program: str) -> None:
    res = client.post(
        f"/tenants/{tenant_id}/entitlements",
        headers=SYSTEM,
        json={"feature_key": f"{program}.workspace", "program": program, "enabled": False},
    )
    assert res.status_code == 201, res.text


def _new_reaction_project(client: TestClient, headers: dict[str, str], name: str = "screen"):
    return client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": name, "objective": "maximize_yield", "status": "active"},
    )


# --------------------------------------------------------------------------- #
# Tenant is resolved from membership; GET /tenants is scoped to the caller
# --------------------------------------------------------------------------- #
def test_tenant_list_is_scoped_to_membership(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        tid = _create_tenant(client)
        oid = _create_org(client, alice, "Alice Org")
        assert _link(client, tid, oid)["tenant_id"] == tid

        alice_tenants = client.get("/tenants", headers=alice)
        assert alice_tenants.status_code == 200, alice_tenants.text
        assert {row["id"] for row in alice_tenants.json()} == {tid}

        # A non-member sees no tenants (not a blanket 403 anymore).
        bob_tenants = client.get("/tenants", headers=bob)
        assert bob_tenants.status_code == 200, bob_tenants.text
        assert bob_tenants.json() == []

        # Operator still sees every tenant.
        assert tid in {row["id"] for row in client.get("/tenants", headers=SYSTEM).json()}


# --------------------------------------------------------------------------- #
# Item 1: a self-asserted x-tenant-id no longer grants cross-tenant access
# --------------------------------------------------------------------------- #
def test_self_asserted_tenant_header_is_rejected_for_non_member(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        tid = _create_tenant(client)
        _link(client, tid, _create_org(client, alice, "Alice Org"))

        header = {"x-tenant-id": str(tid)}
        # Member reads their own tenant's entitlements.
        assert client.get(f"/tenants/{tid}/entitlements", headers={**alice, **header}).status_code == 200
        # Non-member asserting the same header is refused (was a hole before enforcement).
        assert client.get(f"/tenants/{tid}/entitlements", headers={**bob, **header}).status_code == 403
        assert client.get(f"/tenants/{tid}/effective-entitlements", headers={**bob, **header}).status_code == 403


# --------------------------------------------------------------------------- #
# Item 3: allow-by-default, explicit deny blocks writes, reads preserved
# --------------------------------------------------------------------------- #
def test_allow_by_default_then_explicit_deny_blocks_writes_but_not_reads(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        tid = _create_tenant(client)
        _link(client, tid, _create_org(client, alice, "Alice Org"))

        # Allow-by-default: no entitlement row yet, so the write succeeds.
        first = _new_reaction_project(client, alice, "before-deny")
        assert first.status_code == 201, first.text
        project_id = first.json()["id"]

        # Explicitly deny the reaction module for this tenant.
        _deny(client, tid, "reaction_optimization")

        # A WRITE to the denied module is now refused, with a machine-readable signal.
        blocked = _new_reaction_project(client, alice, "after-deny")
        assert blocked.status_code == 403, blocked.text
        assert blocked.json()["detail"] == {
            "code": "module_not_entitled",
            "program": "reaction_optimization",
        }
        assert blocked.headers.get("X-Module-Not-Entitled") == "reaction_optimization"

        # READS are preserved — the tenant keeps access to work it already created (retention).
        assert client.get("/reaction-projects", headers=alice).status_code == 200
        assert client.get(f"/reaction-projects/{project_id}", headers=alice).status_code == 200

        # A DIFFERENT module is unaffected (allow-by-default) — enforcement is per-program.
        dossier = client.post("/regulatory/dossiers", headers=alice, json={"title": "still allowed"})
        assert dossier.status_code == 201, dossier.text


def test_operator_and_admin_bypass_module_entitlement(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        admin = _sign_up(client, ADMIN_EMAIL)
        tid = _create_tenant(client)
        _link(client, tid, _create_org(client, alice, "Alice Org"))
        _deny(client, tid, "reaction_optimization")

        # System key and admin are unrestricted even when a tenant is denied the module.
        assert _new_reaction_project(client, SYSTEM, "op-write").status_code == 201
        assert _new_reaction_project(client, admin, "admin-write").status_code == 201


# --------------------------------------------------------------------------- #
# Item 4: effective entitlement distinguishes denied from unconfigured
# --------------------------------------------------------------------------- #
def test_effective_entitlements_reports_default_policy_and_explicitness(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        tid = _create_tenant(client)
        _link(client, tid, _create_org(client, alice, "Alice Org"))
        _deny(client, tid, "reaction_optimization")

        res = client.get(
            f"/tenants/{tid}/effective-entitlements",
            headers={**alice, "x-tenant-id": str(tid)},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["tenant_id"] == tid
        assert body["default_policy"] == "allow"
        by_program = {row["program"]: row for row in body["programs"]}
        # Denied module: entitled False, and it is an explicit decision.
        assert by_program["reaction_optimization"] == {
            "program": "reaction_optimization",
            "display_name": "Reaction Optimization",
            "entitled": False,
            "explicit": True,
        }
        # Unconfigured module: entitled True (default), not explicit.
        assert by_program["spectracheck"]["entitled"] is True
        assert by_program["spectracheck"]["explicit"] is False


def test_migration_0032_upgrade_downgrade_idempotent():
    """Drive 0032 in isolation on a scratch SQLite engine (alembic never runs in the suite)."""

    import importlib.util as _ilu
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    eng = sa.create_engine("sqlite:///:memory:")
    with eng.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE organizations (id INTEGER PRIMARY KEY, name VARCHAR)")
        spec = _ilu.spec_from_file_location(
            "m0032",
            str(Path(__file__).resolve().parents[1] / "alembic/versions/0032_organization_tenant_id.py"),
        )
        m = _ilu.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.op = Operations(MigrationContext.configure(conn))

        m.upgrade()
        cols = {c["name"] for c in sa.inspect(conn).get_columns("organizations")}
        idx = {i["name"] for i in sa.inspect(conn).get_indexes("organizations")}
        assert "tenant_id" in cols
        assert "ix_organizations_tenant_id" in idx
        m.upgrade()  # idempotent
        m.downgrade()
        cols = {c["name"] for c in sa.inspect(conn).get_columns("organizations")}
        assert "tenant_id" not in cols
        m.downgrade()  # idempotent
