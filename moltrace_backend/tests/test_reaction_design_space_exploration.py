"""Per-variable exploration-state (free/fixed/excluded) on the reaction design space.

Covers the round-trip the design-space editor depends on — POST/PATCH with
``{"entries": [{"reaction_variable_id", "exploration_state"}]}`` and GET echoing the
same shape — plus the optimizer wiring: an ``excluded`` variable is dropped from the
search domain and a ``fixed`` variable is pinned at its default value.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck import reaction_bo
from nmrcheck.orm import ReactionDesignSpaceORM, ReactionVariableORM


def _sign_up(client: TestClient, email: str = "explore@example.com") -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Exploration-state screen", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _variable(client: TestClient, headers: dict[str, str], project_id: int, body: dict) -> dict:
    res = client.post(
        f"/reaction-projects/{project_id}/variables",
        headers=headers,
        json=body,
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_design_space_entries_round_trip(client):
    """The exact shape the FE sends (POST {entries}) round-trips through GET and PATCH."""
    with client:
        headers = _sign_up(client)
        project = _project(client, headers)
        temp = _variable(
            client,
            headers,
            project["id"],
            {"name": "temperature_c", "variable_type": "numeric", "min_value": 40, "max_value": 80},
        )
        solvent = _variable(
            client,
            headers,
            project["id"],
            {"name": "solvent", "variable_type": "categorical", "allowed_values_json": ["MeCN", "THF"]},
        )

        created = client.post(
            f"/reaction-projects/{project['id']}/design-space",
            headers=headers,
            json={
                "entries": [
                    {"reaction_variable_id": temp["id"], "exploration_state": "free"},
                    {"reaction_variable_id": solvent["id"], "exploration_state": "excluded"},
                ]
            },
        )
        assert created.status_code == 201, created.text
        # ``free`` is the default and is not persisted; ``excluded`` round-trips.
        assert created.json()["entries"] == [
            {"reaction_variable_id": solvent["id"], "exploration_state": "excluded"}
        ]

        fetched = client.get(
            f"/reaction-projects/{project['id']}/design-space", headers=headers
        )
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["entries"] == [
            {"reaction_variable_id": solvent["id"], "exploration_state": "excluded"}
        ]

        patched = client.patch(
            f"/reaction-projects/{project['id']}/design-space",
            headers=headers,
            json={
                "entries": [
                    {"reaction_variable_id": temp["id"], "exploration_state": "fixed"},
                    {"reaction_variable_id": solvent["id"], "exploration_state": "free"},
                ]
            },
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["entries"] == [
            {"reaction_variable_id": temp["id"], "exploration_state": "fixed"}
        ]


def test_design_space_rejects_unknown_exploration_state(client):
    with client:
        headers = _sign_up(client, "badstate@example.com")
        project = _project(client, headers)
        var = _variable(
            client,
            headers,
            project["id"],
            {"name": "temperature_c", "variable_type": "numeric", "min_value": 40, "max_value": 80},
        )
        res = client.post(
            f"/reaction-projects/{project['id']}/design-space",
            headers=headers,
            json={"entries": [{"reaction_variable_id": var["id"], "exploration_state": "maybe"}]},
        )
        assert res.status_code == 422, res.text


def _numeric_variable(vid: int, name: str, *, default: str | None = None) -> ReactionVariableORM:
    return ReactionVariableORM(
        id=vid,
        reaction_project_id=1,
        name=name,
        variable_type="numeric",
        min_value=40.0,
        max_value=80.0,
        default_value=default,
        allowed_values_json=None,
        metadata_json="{}",
    )


def _design_space(exploration_states_json: str) -> ReactionDesignSpaceORM:
    return ReactionDesignSpaceORM(
        id=1,
        reaction_project_id=1,
        variables_json="{}",
        categorical_variables_json="{}",
        numeric_variables_json="{}",
        boolean_variables_json="{}",
        fixed_conditions_json="{}",
        excluded_conditions_json="[]",
        exploration_states_json=exploration_states_json,
        metadata_json="{}",
    )


def test_build_domain_excludes_and_fixes_variables():
    """excluded → dropped from the domain; fixed → pinned at its default value."""
    variables = [
        _numeric_variable(10, "temperature_c"),
        _numeric_variable(11, "loading_mol_pct", default="15"),
        _numeric_variable(12, "atmosphere_bar"),
    ]
    design_space = _design_space(
        '[{"reaction_variable_id": 11, "exploration_state": "fixed"},'
        ' {"reaction_variable_id": 12, "exploration_state": "excluded"}]'
    )

    domain = reaction_bo._build_domain(design_space, variables, [])

    # free variable still varies
    assert "temperature_c" in domain.numeric
    # fixed variable is pinned at its default and does not vary
    assert domain.fixed.get("loading_mol_pct") == 15
    assert "loading_mol_pct" not in domain.numeric
    # excluded variable is absent from every part of the domain
    assert "atmosphere_bar" not in domain.numeric
    assert "atmosphere_bar" not in domain.fixed


def test_build_domain_all_free_is_unchanged():
    """An empty/all-free exploration list reproduces the prior domain exactly."""
    variables = [_numeric_variable(10, "temperature_c"), _numeric_variable(11, "loading_mol_pct")]
    baseline = reaction_bo._build_domain(_design_space("[]"), variables, [])
    assert set(baseline.numeric) == {"temperature_c", "loading_mol_pct"}
    assert baseline.fixed == {}


def test_build_domain_fixed_without_default_stays_free():
    """A 'fixed' variable with no default value cannot be pinned, so it stays free."""
    variables = [_numeric_variable(11, "loading_mol_pct", default=None)]
    design_space = _design_space(
        '[{"reaction_variable_id": 11, "exploration_state": "fixed"}]'
    )
    domain = reaction_bo._build_domain(design_space, variables, [])
    assert "loading_mol_pct" not in domain.fixed
    assert "loading_mol_pct" in domain.numeric
