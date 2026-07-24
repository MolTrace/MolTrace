"""API tests for the Phase-C capability readout + SDL site status + the 503 error mapping."""

from __future__ import annotations

import importlib.util

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from nmrcheck import reaction_ml
from nmrcheck.api import _raise_reaction_http_error


def _headers(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_capabilities_readout_requires_auth(client):
    with client:
        assert client.get("/reaction-capabilities").status_code == 401


def test_capabilities_readout_lists_all_four(client):
    with client:
        headers = _headers(client, "cap-list@example.com")
        res = client.get("/reaction-capabilities", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        names = [item["name"] for item in body["capabilities"]]
        assert names == sorted(reaction_ml.CAPABILITIES)
        for item in body["capabilities"]:
            assert item["engine"] == "reaction_ml.v1"
            assert set(item) >= {
                "name",
                "enabled",
                "available",
                "active",
                "missing_modules",
                "reason",
                "provenance",
            }
        assert "disclaimer" in body


def test_availability_matches_a_live_probe(client):
    """Expected availability is DERIVED at test time, never a hard-coded literal.

    The local venv and CI install different optional-extra sets, so pinning e.g.
    ``available == False`` for retrosynthesis would break on any host with the extra present.
    """

    with client:
        headers = _headers(client, "cap-probe@example.com")
        body = client.get("/reaction-capabilities", headers=headers).json()
        by_name = {item["name"]: item for item in body["capabilities"]}
        for name, spec in reaction_ml.CAPABILITIES.items():
            probed = {
                module: importlib.util.find_spec(module) is not None
                for module in spec.required_modules
            }
            if not spec.required_modules:
                expected = True
            elif name in reaction_ml._ANY_ONE_MODULE:
                expected = any(probed.values())
            else:
                expected = all(probed.values())
            assert by_name[name]["available"] is expected, (name, probed)


def test_yield_gnn_never_reads_active_without_promotion_evidence(client, monkeypatch):
    """Flag on + torch present is NOT enough — the readout passes no gate artifact, by design."""

    monkeypatch.setenv("MOLTRACE_REACTION_YIELD_GNN", "1")
    with client:
        headers = _headers(client, "cap-gnn@example.com")
        body = client.get("/reaction-capabilities", headers=headers).json()
        gnn = next(i for i in body["capabilities"] if i["name"] == "yield_gnn")
        assert gnn["active"] is False


def test_sdl_status_disabled_by_default(client, monkeypatch):
    monkeypatch.delenv("MOLTRACE_REACTION_SDL", raising=False)
    with client:
        headers = _headers(client, "sdl-off@example.com")
        res = client.get("/reaction-sdl/status", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["enabled"] is False
        assert body["execution_surface_wired"] is False
        assert "MOLTRACE_REACTION_SDL=1" in body["detail"]
        assert "disclaimer" in body


def test_sdl_status_reflects_the_site_flag(client, monkeypatch):
    monkeypatch.setenv("MOLTRACE_REACTION_SDL", "1")
    with client:
        headers = _headers(client, "sdl-on@example.com")
        body = client.get("/reaction-sdl/status", headers=headers).json()
        assert body["enabled"] is True
        # Even with the site flag on, no execution surface exists.
        assert body["execution_surface_wired"] is False


def test_no_sdl_execution_surface_is_registered(routed_app):
    """Encodes 'nothing auto-executes' as a regression guard: read-only status only."""

    for route in routed_app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/reaction-sdl/"):
            assert path == "/reaction-sdl/status", f"unexpected SDL surface: {path}"
            methods = getattr(route, "methods", set()) or set()
            assert methods <= {"GET", "HEAD"}, f"non-read SDL route: {path} {methods}"


def test_capability_unavailable_maps_to_503():
    with pytest.raises(HTTPException) as excinfo:
        _raise_reaction_http_error(reaction_ml.CapabilityUnavailableError("retrosynthesis: off"))
    assert excinfo.value.status_code == 503
    assert "retrosynthesis" in excinfo.value.detail


def test_migration_0031_upgrade_downgrade_idempotent():
    """Drive 0031 in isolation on a scratch SQLite engine (alembic never runs in the suite)."""

    import importlib.util as _ilu
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    eng = sa.create_engine("sqlite:///:memory:")
    with eng.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE reaction_projects (id INTEGER PRIMARY KEY, owner_id INTEGER)"
        )
        spec = _ilu.spec_from_file_location(
            "m0031",
            str(
                Path(__file__).resolve().parents[1]
                / "alembic/versions/0031_reaction_phase_c_wiring.py"
            ),
        )
        m = _ilu.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.op = Operations(MigrationContext.configure(conn))

        m.upgrade()
        tables = set(sa.inspect(conn).get_table_names())
        assert {
            "reaction_yield_prediction_runs",
            "reaction_proposed_route_scores",
            "reaction_forward_checks",
        } <= tables
        m.upgrade()  # idempotent
        m.downgrade()
        tables = set(sa.inspect(conn).get_table_names())
        assert "reaction_yield_prediction_runs" not in tables
        assert "reaction_proposed_route_scores" not in tables
        assert "reaction_forward_checks" not in tables
        m.downgrade()  # idempotent
