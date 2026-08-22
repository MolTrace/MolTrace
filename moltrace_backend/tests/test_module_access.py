"""Layer 0.C of the standalone-modules program: the deployment serves only what it sells.

Three layers of assurance, mirroring the reaction owner-gate suite:

* *classification completeness* — every route is deliberately assigned to a product or declared
  platform, so a new endpoint cannot drift in unclassified;
* *structural* — the gate is actually attached to the router, so classification is not merely
  decorative;
* *behavioural* — a single-module deployment really does refuse the other products, with a code
  the client can act on, while its own product and the shared platform keep working.

The classification map is what makes a single-module SKU enforceable, so it is worth failing a
build over.
"""

import pytest
from fastapi.testclient import TestClient

from nmrcheck import module_access as ma
from nmrcheck.settings import Settings, validate_startup_settings


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


# --------------------------------------------------------------------------- #
# Classification completeness
# --------------------------------------------------------------------------- #
def test_every_route_is_classified_as_a_product_or_as_platform(routed_app):
    """No route may be unclassified. An unclassified path is served at runtime (a forgotten entry
    must not be an outage), so this test is the only thing standing between a new module route and
    shipping ungated — which is exactly why it fails the build."""
    unclassified = [
        path
        for route in routed_app.routes
        if (path := getattr(route, "path", "")) and not ma.is_classified(path)
    ]
    assert unclassified == [], (
        "routes are neither assigned to a product nor declared platform — add each to "
        f"MODULE_ROUTE_PREFIXES or PLATFORM_ROUTE_PREFIXES in module_access.py: {unclassified}"
    )


def test_no_route_is_both_a_product_route_and_a_platform_route(routed_app):
    both = [
        path
        for route in routed_app.routes
        if (path := getattr(route, "path", ""))
        and ma.module_for_route(path) is not None
        and ma.is_platform_route(path)
    ]
    assert both == [], f"routes claimed by a product AND by the platform: {both}"


def test_each_product_owns_a_substantial_surface(routed_app):
    """A floor per product, so the map cannot silently shrink and quietly stop gating."""
    counts = {key: 0 for key in ma.ALL_MODULES}
    for route in routed_app.routes:
        module = ma.module_for_route(getattr(route, "path", ""))
        if module is not None:
            counts[module] += 1
    assert counts["spectracheck"] >= 150, counts
    assert counts["regulatory_hub"] >= 55, counts
    assert counts["reaction_optimization"] >= 70, counts


def test_prefix_matching_respects_path_segments():
    """``/benchmark`` must not swallow ``/benchmark-datasets`` — the ML substrate ships with every
    SKU, while the SpectraCheck benchmark runner does not."""
    assert ma.module_for_route("/benchmark/spectracheck/run") == "spectracheck"
    assert ma.module_for_route("/benchmark-datasets") is None
    assert ma.is_platform_route("/benchmark-datasets")
    # And the longest match wins rather than the first.
    assert ma.module_for_route("/reaction-projects/1/experiments") == "reaction_optimization"


# --------------------------------------------------------------------------- #
# Structural: the gate is wired
# --------------------------------------------------------------------------- #
def test_module_gate_is_attached_to_every_product_route(routed_app):
    missing = []
    for route in routed_app.routes:
        path = getattr(route, "path", "")
        if ma.module_for_route(path) is None:
            continue
        if "_module_licence_gate" not in _flatten(getattr(route, "dependant", None)):
            missing.append(path)
    assert missing == [], f"product routes with no module gate: {missing}"


def test_scim_is_deliberately_exempt_from_the_module_gate(routed_app):
    """SCIM is provisioning infrastructure with its own token, not a product surface. This pins
    the exemption so it stays a reviewed decision rather than an oversight."""
    scim = [
        path
        for route in routed_app.routes
        if (path := getattr(route, "path", "")).startswith("/scim")
        and "_module_licence_gate" in _flatten(getattr(route, "dependant", None))
    ]
    assert scim == [], f"SCIM routes unexpectedly carry the module gate: {scim}"


# --------------------------------------------------------------------------- #
# Behavioural: a single-module deployment
# --------------------------------------------------------------------------- #
@pytest.fixture()
def spectracheck_only(app):
    previous = app.state.enabled_modules
    app.state.enabled_modules = ("spectracheck",)
    try:
        yield app
    finally:
        app.state.enabled_modules = previous


def test_a_spectracheck_only_deployment_refuses_the_other_products(
    spectracheck_only, client, api_headers
):
    with client:
        for path in ("/regulatory/dossiers", "/reaction-projects"):
            res = client.get(path, headers=api_headers)
            assert res.status_code == 403, f"{path} -> {res.status_code} {res.text}"
            # The code survives sanitization, so the client can tell "not in this plan" from
            # "not allowed" and show the right thing.
            assert res.json()["code"] == ma.MODULE_NOT_LICENSED_DETAIL, res.text
            assert res.headers.get(ma.MODULE_HEADER) in {
                "regulatory_hub",
                "reaction_optimization",
            }


def test_a_spectracheck_only_deployment_still_serves_its_own_product_and_the_platform(
    spectracheck_only, client, api_headers
):
    with client:
        own = client.get("/spectracheck/sessions", headers=api_headers)
        assert own.status_code == 200, own.text

        # The compliance floor and the shared science substrate ship with every SKU — that is the
        # whole argument for buying one module rather than a point tool.
        for path in ("/compound-registry/compounds", "/controlled-records", "/esignatures/records"):
            res = client.get(path, headers=api_headers)
            assert res.status_code == 200, f"{path} -> {res.status_code} {res.text}"


def test_the_default_deployment_serves_all_three_products(client, api_headers):
    """The gate landing must not change an existing connected-platform deployment."""
    with client:
        for path in ("/spectracheck/sessions", "/regulatory/dossiers", "/reaction-projects"):
            res = client.get(path, headers=api_headers)
            assert res.status_code == 200, f"{path} -> {res.status_code} {res.text}"


# --------------------------------------------------------------------------- #
# Capability discovery
# --------------------------------------------------------------------------- #
def test_capabilities_reports_what_the_workspace_includes(spectracheck_only, client, api_headers):
    with client:
        res = client.get("/system/capabilities", headers=api_headers)
        assert res.status_code == 200, res.text
        included = {row["module"]: row["included"] for row in res.json()["modules"]}
        assert included == {
            "spectracheck": True,
            "regulatory_hub": False,
            "reaction_optimization": False,
        }
        # Every product is listed whether or not it is included, so the interface can offer an
        # honest "not in this plan" state instead of silently omitting it.
        assert len(res.json()["modules"]) == 3


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def test_a_typo_in_the_module_list_is_a_startup_issue():
    issues = validate_startup_settings(
        Settings(database_url="sqlite:///:memory:", enabled_modules=("spectracheck", "regentry"))
    )
    assert any("regentry" in issue for issue in issues), issues


def test_an_empty_module_list_is_a_startup_issue():
    issues = validate_startup_settings(
        Settings(database_url="sqlite:///:memory:", enabled_modules=())
    )
    assert any("at least one module" in issue for issue in issues), issues


def test_normalize_preserves_the_canonical_product_order():
    assert ma.normalize_enabled_modules(["reaction_optimization", "spectracheck"]) == (
        "spectracheck",
        "reaction_optimization",
    )
