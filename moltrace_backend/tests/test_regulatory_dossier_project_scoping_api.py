"""Project links on a regulatory dossier are user-scoped.

``create_dossier`` / ``patch_dossier`` validate a referenced ``project_id`` against the
acting user: a bearer-token caller may only link a project they own, while a system api
key (internal / admin ops) may reference any project. Absent vs. owned-by-another-user
both yield the same non-leaking ``404 Project not found.`` so cross-tenant existence is
never disclosed.
"""

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

SYSTEM = {"x-api-key": "test-key"}


def _app(tmp_path):
    return create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'dossier_project_scope.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )


def _sign_up(client: TestClient, email: str):
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict, name: str) -> int:
    # Workspace projects (ProjectORM, table "projects", user_id-owned) are what a dossier's
    # project_id references — distinct from the SpectraCheck "/projects" endpoint (owner_id).
    res = client.post("/workspaces/projects", headers=headers, json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _create_dossier(client: TestClient, headers: dict, **body):
    return client.post(
        "/regulatory/dossiers", headers=headers, json={"title": "Scope dossier", **body}
    )


def test_user_cannot_link_another_users_project(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        alice_project = _project(client, alice, "Alice project")
        res = _create_dossier(client, bob, project_id=alice_project)
        assert res.status_code == 404, res.text
        assert "Project not found." in res.json()["detail"]  # non-leaking — same as absent


def test_user_can_link_own_project(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        alice_project = _project(client, alice, "Alice project")
        res = _create_dossier(client, alice, project_id=alice_project)
        assert res.status_code == 201, res.text
        assert res.json()["project_id"] == alice_project


def test_system_api_key_may_reference_any_project(tmp_path):
    # The internal/admin system key is intentionally not user-scoped.
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        alice_project = _project(client, alice, "Alice project")
        res = _create_dossier(client, SYSTEM, project_id=alice_project)
        assert res.status_code == 201, res.text
        assert res.json()["project_id"] == alice_project


def test_missing_project_is_404_for_user(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        res = _create_dossier(client, alice, project_id=999_999)
        assert res.status_code == 404, res.text
        assert "Project not found." in res.json()["detail"]


def test_patch_cannot_assign_another_users_project(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        alice_project = _project(client, alice, "Alice project")
        dossier_id = _create_dossier(client, SYSTEM).json()["id"]  # created with no project link
        res = client.patch(
            f"/regulatory/dossiers/{dossier_id}",
            headers=bob,
            json={"project_id": alice_project},
        )
        assert res.status_code == 404, res.text
        assert "Project not found." in res.json()["detail"]


def test_patch_unrelated_field_does_not_recheck_inherited_project(tmp_path):
    # Ownership is enforced only when project_id is (re)assigned this request — a patch that
    # doesn't touch project_id must not be rejected over an already-established link.
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        alice_project = _project(client, alice, "Alice project")
        dossier_id = _create_dossier(client, SYSTEM, project_id=alice_project).json()["id"]
        res = client.patch(
            f"/regulatory/dossiers/{dossier_id}",
            headers=bob,
            json={"title": "Renamed without touching the project link"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["title"] == "Renamed without touching the project link"
        assert res.json()["project_id"] == alice_project


def test_owner_can_patch_assign_own_project(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        alice_project = _project(client, alice, "Alice project")
        dossier_id = _create_dossier(client, alice).json()["id"]
        res = client.patch(
            f"/regulatory/dossiers/{dossier_id}",
            headers=alice,
            json={"project_id": alice_project},
        )
        assert res.status_code == 200, res.text
        assert res.json()["project_id"] == alice_project


def test_patch_cannot_mutate_existing_link_to_unowned_project(tmp_path):
    # The takeover shape: a dossier already linked to one of Alice's projects must not be
    # re-pointed by Bob to ANOTHER project he does not own, and the stored link is preserved.
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        alice_p1 = _project(client, alice, "Alice project one")
        alice_p2 = _project(client, alice, "Alice project two")
        dossier_id = _create_dossier(client, SYSTEM, project_id=alice_p1).json()["id"]
        res = client.patch(
            f"/regulatory/dossiers/{dossier_id}",
            headers=bob,
            json={"project_id": alice_p2},
        )
        assert res.status_code == 404, res.text
        assert "Project not found." in res.json()["detail"]
        got = client.get(f"/regulatory/dossiers/{dossier_id}", headers=bob)
        assert got.status_code == 200, got.text
        assert got.json()["project_id"] == alice_p1  # link unchanged


def test_owner_can_repoint_between_own_projects(tmp_path):
    # A legitimate owner may move the link between two projects they own.
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        alice_p1 = _project(client, alice, "Alice project one")
        alice_p2 = _project(client, alice, "Alice project two")
        dossier_id = _create_dossier(client, alice, project_id=alice_p1).json()["id"]
        res = client.patch(
            f"/regulatory/dossiers/{dossier_id}",
            headers=alice,
            json={"project_id": alice_p2},
        )
        assert res.status_code == 200, res.text
        assert res.json()["project_id"] == alice_p2
