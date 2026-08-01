"""Layer 0.F of the standalone-modules program: single-module mode must keep working.

Layer 0.C proved a deployment *refuses* what it does not serve. This proves the other half — that
what it *does* serve still works when a sibling product's data can never exist. That is the rot
risk: the cross-module surfaces (bridges, the command centre, the product registry, the mobile
aggregation) were all written when three products were always present, and they are exactly the
code that would start throwing once one of them is absent.

Two tiers, because exhaustiveness costs about two minutes:

* a fast guard over the surfaces that aggregate across products, which runs on every commit;
* an exhaustive sweep of every parameterless GET, marked ``slow`` so it runs in the sharded CI job.

A 403 is a pass here — refusing an unlicensed product is the point. Only a 5xx or an unhandled
exception is a failure.
"""

import pytest
from fastapi.testclient import TestClient

from nmrcheck import (
    ai_inference_store,
    analytics_store,
    method_registry_store,
    ml_model_factory_store,
    product_orchestration_store,
)
from nmrcheck.api import create_app
from nmrcheck.database import create_session_factory, init_db
from nmrcheck.module_access import ALL_MODULES
from nmrcheck.settings import Settings

API_HEADERS = {"x-api-key": "single-module-key"}

# The surfaces that read across products, and would be the first to break. Every one of these is
# served in all three configurations — they are platform by classification precisely because they
# exist to join products, so each has to degrade rather than assume.
CROSS_PRODUCT_SURFACES = (
    "/cross-module/command-center",
    "/cross-module/action-items",
    "/product/programs",
    "/product/module-priority",
    "/product/cross-module/workflow-templates",
    "/bridges/spectroscopy-to-regulatory",
    "/bridges/regulatory-to-reaction",
    "/mobile/command-center",
    "/system/capabilities",
)


def _single_module_app(module: str, tmp_path):
    """A fully seeded app that serves exactly one product."""
    database_url = f"sqlite:///{tmp_path}/{module}.sqlite3"
    settings = Settings(
        database_url=database_url,
        require_verified_email=False,
        api_key=API_HEADERS["x-api-key"],
        enabled_modules=(module,),
    )
    app = create_app(settings)
    session_factory = create_session_factory(database_url)
    init_db(session_factory)
    # Mirrors conftest.seed_database / the lifespan seed sequence.
    method_registry_store.ensure_builtin_methods(session_factory)
    analytics_store.ensure_default_tasks(session_factory)
    ml_model_factory_store.ensure_builtin_ml_tasks(session_factory)
    ai_inference_store.ensure_builtin_services(session_factory)
    product_orchestration_store.ensure_default_programs(session_factory)
    app.state.session_factory = session_factory
    app.state.settings = settings
    return app


@pytest.mark.parametrize("module", ALL_MODULES)
def test_cross_product_surfaces_degrade_instead_of_breaking(module, tmp_path):
    """A one-product deployment must not throw on the surfaces built to join three."""
    app = _single_module_app(module, tmp_path)
    assert app.state.enabled_modules == (module,)
    client = TestClient(app)
    failures = []
    with client:
        for path in CROSS_PRODUCT_SURFACES:
            try:
                response = client.get(path, headers=API_HEADERS)
            except Exception as exc:  # noqa: BLE001 - the failure mode under test
                failures.append(f"{path} raised {type(exc).__name__}: {exc}")
                continue
            if response.status_code >= 500:
                failures.append(f"{path} -> {response.status_code} {response.text[:160]}")
    assert failures == [], f"{module}-only deployment broke on cross-product surfaces: {failures}"


@pytest.mark.parametrize("module", ALL_MODULES)
def test_a_single_product_deployment_still_serves_the_platform(module, tmp_path):
    """Guard the opposite failure: gating so broadly that the shared platform stops working.

    Without a floor, a map that accidentally claimed everything for one product would still pass
    the "no 5xx" test — every route would simply be refused.
    """
    app = _single_module_app(module, tmp_path)
    client = TestClient(app)
    with client:
        for path in ("/compound-registry/compounds", "/controlled-records", "/esignatures/records"):
            response = client.get(path, headers=API_HEADERS)
            assert response.status_code == 200, f"{path} -> {response.status_code} {response.text}"


@pytest.mark.slow
@pytest.mark.parametrize("module", ALL_MODULES)
def test_no_parameterless_get_returns_a_server_error(module, tmp_path):
    """Exhaustive sweep: every GET that needs no path parameter, in every single-product mode.

    ~163 routes per configuration. A 403 is a pass (that is the gate doing its job); only a 5xx or
    an unhandled exception fails. Also asserts a floor of served routes so the sweep cannot pass
    by refusing everything.
    """
    app = _single_module_app(module, tmp_path)
    client = TestClient(app)
    paths = sorted(
        {
            path
            for route in app.routes
            if "GET" in (getattr(route, "methods", None) or set())
            and "{" not in (path := getattr(route, "path", ""))
            and path not in {"/openapi.json", "/docs", "/redoc", "/metrics"}
        }
    )
    assert len(paths) > 120, f"expected a broad GET surface to sweep, found {len(paths)}"

    failures = []
    served = 0
    with client:
        for path in paths:
            try:
                response = client.get(path, headers=API_HEADERS)
            except Exception as exc:  # noqa: BLE001 - the failure mode under test
                failures.append(f"{path} raised {type(exc).__name__}: {exc}")
                continue
            if response.status_code >= 500:
                failures.append(f"{path} -> {response.status_code} {response.text[:160]}")
            elif response.status_code < 400:
                served += 1

    assert failures == [], f"{module}-only deployment returned server errors: {failures}"
    assert served >= 100, f"{module}-only deployment served only {served} routes; gating too broad"
