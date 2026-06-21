"""Owner-scoping for routes whose owner-relevant id is carried in the request BODY.

The path-based ``require_reaction_access`` gate and the ``/regulatory/dossiers/{id}`` gates
cannot reach body ids, so an adversarial review confirmed five cross-tenant holes remain after
the landed cross-module fix (commit ``7a8a52d``). Each test below pins the contract: a non-owner
user gets a non-leaking 404; the owner is not over-restricted; the system api-key remains
unrestricted (the broader ``test_phase60_product_orchestration_api`` / system-key suites cover
that already, but the cases below pin the user-flow contract that 7a8a52d's tests do not).
"""

import json as _json
import uuid as _uuid

from fastapi.testclient import TestClient


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _me(client: TestClient, headers: dict[str, str]) -> int:
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200, res.text
    return int(res.json()["id"])


# --------------------------------------------------------------------------- #
# Hole 1: POST /reaction-projects — body ``owner_id`` is honored unchecked. A user could
# create a project owned by another user. The fix forces ``owner_id = caller.user_id`` when the
# caller is user-scoped; a system api-key / admin (covered by phase60) stays unrestricted.
# --------------------------------------------------------------------------- #
def test_user_cannot_create_a_reaction_project_owned_by_another_user(client):
    with client:
        attacker = _sign_up(client, "attacker@example.com")
        victim = _sign_up(client, "victim@example.com")
        victim_id = _me(client, victim)

        # The attacker tries to plant a project owned by the victim.
        res = client.post(
            "/reaction-projects",
            headers=attacker,
            json={
                "name": "Stolen",
                "objective": "maximize_yield",
                "status": "active",
                "owner_id": victim_id,
            },
        )
        assert res.status_code == 201, res.text
        attacker_id = _me(client, attacker)
        assert res.json()["owner_id"] == attacker_id, (
            "body owner_id must be ignored for a user-scoped caller — the project is forced "
            "to the caller. Returning owner_id == victim_id would mean an attacker can plant "
            "rows in the victim's tenant."
        )

        # The list endpoint must NOT show the project under the victim's scope.
        v_list = client.get("/reaction-projects", headers=victim).json()
        assert all(p["id"] != res.json()["id"] for p in v_list), (
            "the planted project must not appear in the victim's owner-scoped list"
        )


def test_user_can_still_create_a_reaction_project_with_no_owner_id_in_body(client):
    """The body-owner_id-omitted path stays the happy path (owner == caller)."""
    with client:
        owner = _sign_up(client, "happy-owner@example.com")
        owner_id = _me(client, owner)
        res = client.post(
            "/reaction-projects",
            headers=owner,
            json={"name": "Mine", "objective": "maximize_yield", "status": "active"},
        )
        assert res.status_code == 201, res.text
        assert res.json()["owner_id"] == owner_id


def test_user_can_create_a_reaction_project_with_their_own_owner_id_in_body(client):
    """A user-scoped caller passing their OWN id as body owner_id is fine (no-op)."""
    with client:
        owner = _sign_up(client, "selfid@example.com")
        owner_id = _me(client, owner)
        res = client.post(
            "/reaction-projects",
            headers=owner,
            json={
                "name": "Self",
                "objective": "maximize_yield",
                "status": "active",
                "owner_id": owner_id,
            },
        )
        assert res.status_code == 201, res.text
        assert res.json()["owner_id"] == owner_id


# --------------------------------------------------------------------------- #
# Shared fixture helpers for the interop trio (Holes 2 / 3 / 5). Mirror the canonical shapes
# from test_reaction_cross_module_owner_scoping_api.py / test_phase62_interoperability_api.py /
# test_spectracheck_persistence_api.py so the setup matches every other suite that exercises
# these endpoints.
# --------------------------------------------------------------------------- #


def _connector(client: TestClient, headers: dict[str, str]) -> int:
    """Unique-per-call connector — connector_key has a uniqueness constraint."""
    key = f"body-id-conn-{_uuid.uuid4().hex[:8]}"
    res = client.post(
        "/connectors",
        headers=headers,
        json={
            "connector_key": key,
            "display_name": "Body-id owner-scope test connector",
            "connector_type": "instrument_watch_folder",
            "target_program": "cross_module",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _managed_file(client: TestClient, headers: dict[str, str]) -> int:
    res = client.post(
        "/files/upload",
        headers=headers,
        data={"file_kind": "processed_nmr", "metadata_json": _json.dumps({"source": "owner-scope-test"})},
        files={"file": ("evidence.csv", b"ppm,intensity\n1.0,10\n", "text/csv")},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _dossier(client: TestClient, headers: dict[str, str], title: str = "Owned dossier") -> int:
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={
            "title": title,
            "product_name": "p",
            "compound_name": "c",
            "intended_use": "fixture",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _reaction_project(client: TestClient, headers: dict[str, str]) -> int:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Owned RX", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _spectracheck_session(client: TestClient, headers: dict[str, str]) -> int:
    """Open a SpectraCheck session by chaining the project + sample creates first."""
    project_res = client.post(
        "/projects",
        headers=headers,
        json={"name": f"sc-project-{_uuid.uuid4().hex[:6]}", "description": "fixture"},
    )
    assert project_res.status_code == 201, project_res.text
    project = project_res.json()
    sample_res = client.post(
        f"/projects/{project['id']}/samples",
        headers=headers,
        json={
            "sample_id": f"sample-{_uuid.uuid4().hex[:6]}",
            "display_name": "fixture sample",
            "molecule_name": "fixture",
            "solvent": "CDCl3",
        },
    )
    assert sample_res.status_code == 201, sample_res.text
    sample = sample_res.json()
    session_res = client.post(
        "/spectracheck/sessions",
        headers=headers,
        json={
            "project_id": project["id"],
            "sample_pk": sample["id"],
            "sample_id": sample["sample_id"],
            "title": "fixture session",
        },
    )
    assert session_res.status_code == 201, session_res.text
    return session_res.json()["id"]


# --------------------------------------------------------------------------- #
# Hole 2: POST /integrations/regulatory/import-source — body dossier_id unscoped. A non-owner
# can stitch an external link onto another tenant's dossier. The fix validates dossier
# ownership in import_regulatory_source; a non-owner gets a non-leaking 404.
# --------------------------------------------------------------------------- #
def test_non_owner_cannot_import_regulatory_source_to_another_tenants_dossier(client):
    with client:
        owner = _sign_up(client, "doss-owner@example.com")
        intruder = _sign_up(client, "doss-intruder@example.com")
        dossier_id = _dossier(client, owner)
        connector_id = _connector(client, intruder)
        file_id = _managed_file(client, intruder)

        res = client.post(
            "/integrations/regulatory/import-source",
            headers=intruder,
            json={
                "connector_id": connector_id,
                "file_id": file_id,
                "dossier_id": dossier_id,
                "source_citation_json": {"source": "test"},
            },
        )
        assert res.status_code == 404, (
            f"non-owner stitched an external link onto another tenant's dossier; got {res.status_code} {res.text}"
        )


def test_owner_can_import_regulatory_source_to_their_own_dossier(client):
    with client:
        owner = _sign_up(client, "doss-self@example.com")
        dossier_id = _dossier(client, owner)
        connector_id = _connector(client, owner)
        file_id = _managed_file(client, owner)
        res = client.post(
            "/integrations/regulatory/import-source",
            headers=owner,
            json={
                "connector_id": connector_id,
                "file_id": file_id,
                "dossier_id": dossier_id,
                "source_citation_json": {"source": "test"},
            },
        )
        assert res.status_code == 201, res.text


# --------------------------------------------------------------------------- #
# Hole 3: POST/GET /outbound-sync-jobs — body source_resource_id unscoped. A non-owner can
# create an outbound sync job referencing another tenant's reaction project / dossier / etc.
# Fix: validate by source_resource_type on create; owner-filter the list in SQL before .limit().
# --------------------------------------------------------------------------- #
def test_non_owner_cannot_create_outbound_sync_job_for_another_tenants_reaction_project(client):
    with client:
        owner = _sign_up(client, "outb-owner@example.com")
        intruder = _sign_up(client, "outb-intruder@example.com")
        project_id = _reaction_project(client, owner)
        connector_id = _connector(client, intruder)

        res = client.post(
            "/outbound-sync-jobs",
            headers=intruder,
            json={
                "connector_id": connector_id,
                "target_system": "lims",
                "source_resource_type": "reaction_project",
                "source_resource_id": project_id,
            },
        )
        assert res.status_code == 404, res.text


def test_non_owner_cannot_create_outbound_sync_job_for_another_tenants_dossier(client):
    with client:
        owner = _sign_up(client, "outb-doss-owner@example.com")
        intruder = _sign_up(client, "outb-doss-intruder@example.com")
        dossier_id = _dossier(client, owner)
        connector_id = _connector(client, intruder)

        res = client.post(
            "/outbound-sync-jobs",
            headers=intruder,
            json={
                "connector_id": connector_id,
                "target_system": "lims",
                "source_resource_type": "regulatory_dossier",
                "source_resource_id": dossier_id,
            },
        )
        assert res.status_code == 404, res.text


def test_owner_can_create_outbound_sync_job_for_their_own_reaction_project(client):
    with client:
        owner = _sign_up(client, "outb-self@example.com")
        project_id = _reaction_project(client, owner)
        connector_id = _connector(client, owner)
        res = client.post(
            "/outbound-sync-jobs",
            headers=owner,
            json={
                "connector_id": connector_id,
                "target_system": "lims",
                "source_resource_type": "reaction_project",
                "source_resource_id": project_id,
            },
        )
        assert res.status_code == 201, res.text


def test_outbound_sync_jobs_list_is_owner_filtered(client):
    """The list endpoint must owner-filter at the SQL layer — a victim's jobs cannot leak to
    an attacker's listing, regardless of the (status, limit) query params."""
    with client:
        owner = _sign_up(client, "list-owner@example.com")
        other = _sign_up(client, "list-other@example.com")
        proj_owner = _reaction_project(client, owner)
        proj_other = _reaction_project(client, other)
        c_owner = _connector(client, owner)
        c_other = _connector(client, other)
        owner_job = client.post(
            "/outbound-sync-jobs",
            headers=owner,
            json={
                "connector_id": c_owner,
                "target_system": "lims",
                "source_resource_type": "reaction_project",
                "source_resource_id": proj_owner,
            },
        ).json()
        other_job = client.post(
            "/outbound-sync-jobs",
            headers=other,
            json={
                "connector_id": c_other,
                "target_system": "lims",
                "source_resource_type": "reaction_project",
                "source_resource_id": proj_other,
            },
        ).json()

        owner_list = client.get("/outbound-sync-jobs", headers=owner).json()
        owner_ids = {job["id"] for job in owner_list}
        assert owner_job["id"] in owner_ids
        assert other_job["id"] not in owner_ids, (
            "another tenant's sync job leaked into the user's list — owner filter missing or "
            "applied post-.limit() (which silently drops owned rows on a busy table)"
        )


# --------------------------------------------------------------------------- #
# Hole 5: POST /integrations/spectracheck/import-file — body spectracheck_session_id unscoped.
# A non-owner can stitch an external link onto another tenant's spectracheck session.
# --------------------------------------------------------------------------- #
def test_non_owner_cannot_import_spectracheck_file_into_another_tenants_session(client):
    with client:
        owner = _sign_up(client, "sc-owner@example.com")
        intruder = _sign_up(client, "sc-intruder@example.com")
        session_id = _spectracheck_session(client, owner)
        connector_id = _connector(client, intruder)
        file_id = _managed_file(client, intruder)
        res = client.post(
            "/integrations/spectracheck/import-file",
            headers=intruder,
            json={
                "connector_id": connector_id,
                "file_id": file_id,
                "spectracheck_session_id": session_id,
                "route": "processed_nmr",
            },
        )
        assert res.status_code == 404, res.text


def test_owner_can_import_spectracheck_file_into_their_own_session(client):
    with client:
        owner = _sign_up(client, "sc-self@example.com")
        session_id = _spectracheck_session(client, owner)
        connector_id = _connector(client, owner)
        file_id = _managed_file(client, owner)
        res = client.post(
            "/integrations/spectracheck/import-file",
            headers=owner,
            json={
                "connector_id": connector_id,
                "file_id": file_id,
                "spectracheck_session_id": session_id,
                "route": "processed_nmr",
            },
        )
        assert res.status_code == 201, res.text
