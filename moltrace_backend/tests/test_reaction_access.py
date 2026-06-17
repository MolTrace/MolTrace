"""Owner-scoping (per-user access control) for reaction (Repho) endpoints.

Two layers of assurance:
* a *structural completeness* test that enumerates every route and proves each gated
  reaction route runs ``require_reaction_access`` (and no other route does), so no route
  can be silently missed;
* *behavioral* tests that a non-owner gets a non-leaking 404 on a project and its children,
  the owner and the system api key are not blocked, and the project list is owner-scoped.
"""

from fastapi.testclient import TestClient

from nmrcheck import reaction_access as ra


def _flatten(dep) -> set[str]:
    names: set[str] = set()
    if dep is None:
        return names
    call = getattr(dep, "call", None)
    if call is not None and getattr(call, "__name__", ""):
        names.add(call.__name__)
    for sub in getattr(dep, "dependencies", []):
        names |= _flatten(sub)
    return names


def test_every_gated_reaction_route_is_owner_gated(routed_app):
    """Completeness: every reaction project/child route carries require_reaction_access,
    and no non-reaction route does."""
    gated = 0
    missing: list[str] = []
    leaked: list[str] = []
    for route in routed_app.routes:
        path = getattr(route, "path", "")
        names = _flatten(getattr(route, "dependant", None))
        if ra.is_reaction_gated_path(path):
            gated += 1
            if "require_reaction_access" not in names:
                missing.append(path)
        elif "require_reaction_access" in names:
            leaked.append(path)
    assert gated >= 80, f"expected the full reaction surface to be gated, found {gated}"
    assert missing == [], f"gated routes missing the owner gate: {missing}"
    assert leaked == [], f"non-reaction routes wrongly gated: {leaked}"


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str], name: str = "Owned project") -> dict:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": name, "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _experiment(client: TestClient, headers: dict[str, str], project_id: int) -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/experiments",
        headers=headers,
        json={
            "experiment_code": "ACC-001",
            "status": "planned",
            "conditions_json": {"temperature_c": 60, "solvent": "MeCN"},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def _batch(client: TestClient, headers: dict[str, str], project_id: int) -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/execution-batches",
        headers=headers,
        json={"batch_code": "ACC-BATCH-1", "title": "batch", "status": "draft"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _item(client: TestClient, headers: dict[str, str], batch_id: int) -> dict:
    res = client.post(
        f"/reaction-execution-batches/{batch_id}/items",
        headers=headers,
        json={
            "item_code": "ACC-ITEM-1",
            "conditions_json": {"temperature_c": 60, "solvent": "MeCN"},
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_non_owner_gets_404_on_project_and_children(client):
    with client:
        owner = _sign_up(client, "owner-a@example.com")
        intruder = _sign_up(client, "intruder-b@example.com")
        project = _project(client, owner)
        pid = project["id"]
        experiment = _experiment(client, owner, pid)
        batch = _batch(client, owner, pid)
        item = _item(client, owner, batch["id"])

        # A non-owner gets a non-leaking 404 on the project, its nested routes, and its
        # bare-child routes (covering reaction_project_id, experiment_id, batch_id, item_id).
        denied_gets = [
            f"/reaction-projects/{pid}",
            f"/reaction-projects/{pid}/experiments",
            f"/reaction-projects/{pid}/cost-profile",
            f"/reaction-experiments/{experiment['id']}",
            f"/reaction-execution-batches/{batch['id']}",
            f"/reaction-execution-batches/{batch['id']}/items",
            f"/reaction-execution-items/{item['id']}/analytical-results",
        ]
        for url in denied_gets:
            res = client.get(url, headers=intruder)
            assert res.status_code == 404, f"intruder GET {url} -> {res.status_code}: {res.text}"

        # A write as the intruder is also a 404 (read == write scope).
        res = client.patch(f"/reaction-projects/{pid}", headers=intruder, json={"status": "paused"})
        assert res.status_code == 404, res.text

        # The owner is NOT blocked.
        for url in [
            f"/reaction-projects/{pid}",
            f"/reaction-projects/{pid}/experiments",
            f"/reaction-experiments/{experiment['id']}",
            f"/reaction-execution-batches/{batch['id']}",
        ]:
            res = client.get(url, headers=owner)
            assert res.status_code == 200, f"owner GET {url} -> {res.status_code}: {res.text}"


def test_project_list_is_owner_scoped(client, api_headers):
    with client:
        owner = _sign_up(client, "list-owner@example.com")
        project = _project(client, owner, name="Private A")
        other = _sign_up(client, "list-other@example.com")

        other_list = client.get("/reaction-projects", headers=other)
        assert other_list.status_code == 200
        assert all(p["id"] != project["id"] for p in other_list.json())

        owner_list = client.get("/reaction-projects", headers=owner)
        assert any(p["id"] == project["id"] for p in owner_list.json())

        # The system api key (unrestricted) sees every project.
        sys_list = client.get("/reaction-projects", headers=api_headers)
        assert any(p["id"] == project["id"] for p in sys_list.json())


def test_system_api_key_is_unrestricted(client, api_headers):
    with client:
        owner = _sign_up(client, "sys-owner@example.com")
        project = _project(client, owner)
        res = client.get(f"/reaction-projects/{project['id']}", headers=api_headers)
        assert res.status_code == 200, res.text


def test_reaction_route_owner_id_resolver(client, app):
    """Unit: the resolver returns the project owner for project + child paths, None when absent."""
    with client:
        owner = _sign_up(client, "resolver-owner@example.com")
        project = _project(client, owner)
        experiment = _experiment(client, owner, project["id"])
    sf = app.state.session_factory
    owner_id = ra.reaction_owner_id(sf, project["id"])
    assert owner_id is not None
    # project path
    assert (
        ra.reaction_route_owner_id(
            sf, "/reaction-projects/{reaction_project_id}", {"reaction_project_id": project["id"]}
        )
        == owner_id
    )
    # bare child path
    assert (
        ra.reaction_route_owner_id(
            sf, "/reaction-experiments/{experiment_id}", {"experiment_id": experiment["id"]}
        )
        == owner_id
    )
    # missing resource -> None (PDP renders as non-leaking 404 for a user)
    assert ra.reaction_route_owner_id(sf, "/reaction-experiments/{experiment_id}", {"experiment_id": 10**9}) is None
    assert ra.reaction_owner_id(sf, None) is None
