"""Shared, worker-scoped app fixtures for the test suite.

Building the ~800-route NMRCheck app (``create_app``) costs ~1.4s and generating
its OpenAPI schema (``app.openapi()``) ~3s. Historically every test file built
its own app, so this cost was paid ~95× and dominated the suite wall-clock under
``pytest -n auto`` (CPU contention amplified each build well past its isolated
cost).

The app reads its database from ``app.state.session_factory`` *per request* (see
the many ``_state(request).session_factory`` call sites in ``api.py``), so we can
build the routed app **once per xdist worker** and swap a fresh, isolated SQLite
database onto it for each test — preserving the existing fresh-DB-per-test
isolation with none of the per-test route-building cost.

Fixtures
--------
* ``routed_app``     — the built app, shared per worker (session scope).
* ``openapi_schema`` — its OpenAPI schema, generated once per worker.
* ``app``            — ``routed_app`` with a fresh, seeded per-test database.
* ``client``         — a ``TestClient`` bound to ``app``.
* ``api_headers``    — the api-key header dict for authenticated requests.

Tests that need non-default ``Settings`` (a different api-key, verified-email on,
custom upload types, …) should keep building their own app; these fixtures serve
the common default case that most API tests use today.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker
from starlette.testclient import TestClient

from nmrcheck import (
    ai_inference_store,
    analytics_store,
    method_registry_store,
    ml_model_factory_store,
    product_orchestration_store,
)
from nmrcheck.api import create_app
from nmrcheck.database import create_session_factory, init_db
from nmrcheck.settings import Settings

TEST_API_KEY = "test-key"


def _test_settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        require_verified_email=False,
        api_key=TEST_API_KEY,
    )


def seed_database(session_factory: sessionmaker[Session]) -> None:
    """Create the schema and seed the built-in rows ``create_app`` would.

    Mirrors the seed sequence in ``create_app``'s lifespan so a swapped per-test
    database starts in the same state a freshly-created app would. The app's
    lifespan closes over its *build-time* session factory (the in-memory
    placeholder below), not ``app.state``, so the swapped DB must be seeded here
    explicitly. Keep in sync with the lifespan — a missing seed surfaces as a
    test failure, not silent drift.
    """
    init_db(session_factory)
    method_registry_store.ensure_builtin_methods(session_factory)
    analytics_store.ensure_default_tasks(session_factory)
    ml_model_factory_store.ensure_builtin_ml_tasks(session_factory)
    ai_inference_store.ensure_builtin_services(session_factory)
    product_orchestration_store.ensure_default_programs(session_factory)


@pytest.fixture(scope="session")
def routed_app() -> FastAPI:
    """The route-registered NMRCheck app, built once per worker.

    The in-memory URL is only a placeholder factory; real per-test databases are
    swapped onto ``app.state.session_factory`` by the ``app`` fixture, so this
    placeholder is never actually queried.
    """
    return create_app(_test_settings("sqlite:///:memory:"))


@pytest.fixture(scope="session")
def openapi_schema(routed_app: FastAPI) -> dict:
    """The OpenAPI schema, generated once per worker (FastAPI caches per app)."""
    return routed_app.openapi()


@pytest.fixture()
def app(routed_app: FastAPI, tmp_path: Path) -> Iterator[FastAPI]:
    """``routed_app`` with a fresh, seeded SQLite database for this test."""
    database_url = f"sqlite:///{tmp_path}/test.sqlite3"
    session_factory = create_session_factory(database_url)
    seed_database(session_factory)
    prev_factory = routed_app.state.session_factory
    prev_settings = routed_app.state.settings
    routed_app.state.session_factory = session_factory
    # Point settings at the per-test DB too, so request-time helpers that derive
    # filesystem paths from settings.database_url isolate per test. In particular
    # _orchestration_storage_root() resolves the /files/upload storage dir as
    # "<db parent>/storage"; with the shared app's ":memory:" URL that collapsed
    # to one fixed ./storage for EVERY test, so two tests uploading a same-named
    # file (IDs reset to 1 -> "1_<name>") collided on the writer's exclusive
    # open("xb"). Under tmp_path the storage dir is unique per test and cleaned up.
    routed_app.state.settings = _test_settings(database_url)
    try:
        yield routed_app
    finally:
        routed_app.state.session_factory = prev_factory
        routed_app.state.settings = prev_settings


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    """A ``TestClient`` on the shared app, bound to this test's database.

    No ``with`` block on purpose: the lifespan would re-seed the build-time
    (placeholder) factory rather than ``app.state``; the ``app`` fixture already
    seeds the swapped database, and routes resolve ``app.state.session_factory``
    per request.
    """
    return TestClient(app)


@pytest.fixture()
def api_headers() -> dict[str, str]:
    return {"x-api-key": TEST_API_KEY}
