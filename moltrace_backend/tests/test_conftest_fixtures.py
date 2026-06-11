"""Validates the shared worker-scoped app fixtures defined in conftest.py.

These guard the contract the rest of the suite migrates onto: the app is built
once per worker, the OpenAPI schema is the real contract, and each test gets a
fresh, seeded database swapped onto the shared app.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import inspect
from starlette.testclient import TestClient


def test_openapi_schema_fixture_is_the_full_contract(openapi_schema: dict) -> None:
    assert isinstance(openapi_schema, dict)
    # The shared schema is the real, fully-built contract — not a stub.
    assert len(openapi_schema["paths"]) > 100


def test_client_fixture_serves_on_the_shared_app(client: TestClient) -> None:
    # The TestClient is bound to the worker-shared app and reaches a route.
    assert client.get("/health").status_code == 200


def test_app_fixture_binds_a_seeded_per_test_database(app: FastAPI) -> None:
    # A fresh session factory is swapped onto the shared app, and seed_database
    # ran init_db so the schema is present.
    engine = app.state.session_factory.kw["bind"]
    tables = set(inspect(engine).get_table_names())
    assert "users" in tables
