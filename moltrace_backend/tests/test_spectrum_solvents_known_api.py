"""Tests for the canonical solvent catalog endpoint.

``GET /spectrum/solvents/known`` exposes the solvent keys the auto-
classification machinery in ``peak_categorization`` recognizes, so the FE
can render a validated solvent dropdown instead of a typo-vulnerable
free-text input.
"""

from __future__ import annotations

import asyncio
from tempfile import mkdtemp

from starlette.requests import Request

from nmrcheck.api import AccessContext, create_app, spectrum_solvents_known
from nmrcheck.database import init_db
from nmrcheck.settings import Settings


def _request() -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-solvents-api-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/solvents_api.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    init_db(app.state.session_factory)
    return Request(
        {
            "type": "http",
            "app": app,
            "headers": [],
            "method": "GET",
            "path": "/spectrum/solvents/known",
            "query_string": b"",
        }
    )


def test_solvents_known_returns_canonical_catalog() -> None:
    async def run() -> None:
        result = await spectrum_solvents_known(
            context=AccessContext(system_api_key=True),
        )

        keys = {entry.key for entry in result.solvents}
        # Core solvents that auto_classify supports.
        for required in ("CDCl3", "DMSO-d6", "CD3OD", "D2O", "C6D6", "CD3CN"):
            assert required in keys, f"{required} missing from solvent catalog"

        # CDCl3 -- the lock-in case used by the GSD validation harness.
        cdcl3 = next(entry for entry in result.solvents if entry.key == "CDCl3")
        assert cdcl3.label == "CDCl3"
        # Known canonical aliases the categorization module accepts.
        assert "cdcl3" in cdcl3.aliases
        assert "chloroform-d" in cdcl3.aliases
        # Residual 1H centre falls in the 7.26 region the FE displays.
        assert cdcl3.residual_1h_ppm is not None
        assert 7.20 <= cdcl3.residual_1h_ppm <= 7.32, cdcl3.residual_1h_ppm
        # Residual 13C centre falls in the 77.16 region.
        assert cdcl3.residual_13c_ppm is not None
        assert 76.5 <= cdcl3.residual_13c_ppm <= 77.7, cdcl3.residual_13c_ppm

    asyncio.run(run())


def test_solvents_known_is_sorted_alphabetically() -> None:
    """FE renders the list as-is; sorted order keeps the dropdown stable."""

    async def run() -> None:
        result = await spectrum_solvents_known(
            context=AccessContext(system_api_key=True),
        )
        keys = [entry.key for entry in result.solvents]
        assert keys == sorted(keys, key=str.lower), keys

    asyncio.run(run())


def test_solvents_known_d2o_has_no_13c_residual() -> None:
    """D2O has no 13C residual solvent peak (the categorization table is empty
    for D2O 13C).  Catalog must reflect that with a null residual_13c_ppm
    so the FE doesn't surface a phantom carbon-solvent shift."""

    async def run() -> None:
        result = await spectrum_solvents_known(
            context=AccessContext(system_api_key=True),
        )
        d2o = next(entry for entry in result.solvents if entry.key == "D2O")
        assert d2o.residual_13c_ppm is None, (
            "D2O must not declare a 13C residual centre."
        )
        # 1H residual (HOD/water) IS present.
        assert d2o.residual_1h_ppm is not None
        assert 4.55 <= d2o.residual_1h_ppm <= 5.05

    asyncio.run(run())


def test_openapi_schema_includes_solvents_endpoint() -> None:
    tmpdir = mkdtemp(prefix="nmrcheck-solvents-openapi-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/solvents_openapi.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    schema = app.openapi()
    assert "/spectrum/solvents/known" in schema["paths"], (
        "/spectrum/solvents/known must appear in the OpenAPI schema so "
        "`npm run generate:openapi` picks it up for the FE dropdown."
    )
    operation = schema["paths"]["/spectrum/solvents/known"]["get"]
    assert operation["operationId"] == "spectrum_solvents_known_spectrum_solvents_known_get"
