"""Route → product-module classification, and which modules this deployment serves.

MolTrace is sold three ways: SpectraCheck (analytical evidence), Regentry (regulatory insight)
and Repho (reaction optimization) — each standalone, or together as the connected platform. A
deployment declares what it serves via ``MOLTRACE_ENABLED_MODULES``; this module says which
product each route belongs to, and the gate in ``api.py`` refuses the rest.

Why a deployment setting rather than a database lookup: a request carries no server-derived
tenant today, and every paid deployment is dedicated to one customer, so the SKU boundary *is*
the deployment. That is also stronger than a database check — there is no tenant resolution to
get wrong. Per-tenant entitlements refine this later, for pooled deployments only.

Two exhaustive maps, and every route must match exactly one of them:

* ``MODULE_ROUTE_PREFIXES`` — routes owned by a single product.
* ``PLATFORM_ROUTE_PREFIXES`` — routes that ship with *every* SKU: identity, the compliance
  floor (audit, e-signatures, controlled records, validation), the compound registry, the
  model/method registries, interoperability, jobs, knowledge, admin and tenant operations.

A path matching neither is a classification gap, not a default. ``tests/test_module_access.py``
fails on any unmatched route, so classifying a new route is a deliberate, reviewed act — the
same discipline ``PUBLIC_ROUTE_PATHS`` applies to the public/authenticated split.

At *runtime* an unmatched path is treated as platform (served). That is deliberate: a forgotten
map entry should surface as a red build, never as a production outage on a core route.
"""

from __future__ import annotations

from typing import Literal

ModuleKey = Literal["spectracheck", "regulatory_hub", "reaction_optimization"]

#: Canonical order, matching ``ProductProgramKey`` in ``models.py``.
ALL_MODULES: tuple[ModuleKey, ...] = ("spectracheck", "regulatory_hub", "reaction_optimization")

MODULE_DISPLAY_NAMES: dict[ModuleKey, str] = {
    "spectracheck": "SpectraCheck",
    "regulatory_hub": "Regentry",
    "reaction_optimization": "Reaction Optimization",
}

#: Machine-readable denial code. Named in the response body and the ``X-MolTrace-Module`` header
#: so a client can tell "this plan does not include that" from "you may not do that".
MODULE_NOT_LICENSED_DETAIL = "module_not_licensed"
MODULE_HEADER = "X-MolTrace-Module"


# Prefixes are matched on whole path segments, so ``/benchmark`` never swallows
# ``/benchmark-datasets``. Order is irrelevant; a path may match at most one entry.
MODULE_ROUTE_PREFIXES: tuple[tuple[str, ModuleKey], ...] = (
    # ---- SpectraCheck: acquisition, processing, assignment, evidence, reporting -------------
    ("/spectracheck", "spectracheck"),
    ("/spectrum", "spectracheck"),
    ("/analyze", "spectracheck"),
    ("/fid", "spectracheck"),
    ("/raw-fid", "spectracheck"),
    ("/nmr", "spectracheck"),
    ("/nmr2d", "spectracheck"),
    ("/proton", "spectracheck"),
    ("/carbon13", "spectracheck"),
    ("/ms", "spectracheck"),
    ("/candidates", "spectracheck"),
    ("/prediction", "spectracheck"),
    ("/confidence", "spectracheck"),
    ("/similarity", "spectracheck"),
    ("/visualization", "spectracheck"),
    ("/benchmark/spectracheck", "spectracheck"),
    # The project/sample hierarchy under /projects is spectracheck_projects + project_samples,
    # not the legacy generic project. /workspaces is the legacy twin and links analyses.
    ("/projects", "spectracheck"),
    ("/samples", "spectracheck"),
    ("/workspaces", "spectracheck"),
    # Analysis history, review and reporting are keyed on analyses / SpectraCheck sessions.
    ("/history", "spectracheck"),
    ("/reviews", "spectracheck"),
    ("/reports", "spectracheck"),
    # Collaboration, workflow and QC all carry required foreign keys into spectracheck_projects
    # or spectracheck_sessions today, and every built-in workflow template is NMR/MS. They are
    # SpectraCheck features, not platform ones — until the polymorphic carve-out lands, at which
    # point they move to PLATFORM_ROUTE_PREFIXES in the same change that makes them subject-typed.
    ("/share-links", "spectracheck"),
    ("/workflow-runs", "spectracheck"),
    ("/workflow-templates", "spectracheck"),
    ("/quality-control", "spectracheck"),
    # ---- Regentry: regulatory calculators, dossiers, corpus, surveillance -------------------
    ("/regulatory", "regulatory_hub"),
    ("/ctd-module3-bundles", "regulatory_hub"),
    # ---- Repho: campaigns, optimization, execution, advisory -------------------------------
    # Only the hyphenated ``/reaction-*`` campaign surfaces are Repho. The plural
    # ``/reactions/structures`` validator is deliberately NOT here — see the platform list.
    ("/reaction-projects", "reaction_optimization"),
    ("/reaction-variables", "reaction_optimization"),
    ("/reaction-experiments", "reaction_optimization"),
    ("/reaction-recommendations", "reaction_optimization"),
    ("/reaction-recommendation-batches", "reaction_optimization"),
    ("/reaction-execution-batches", "reaction_optimization"),
    ("/reaction-execution-items", "reaction_optimization"),
    ("/reaction-optimization", "reaction_optimization"),
    ("/reaction-optimization-runs", "reaction_optimization"),
    ("/reaction-optimization-cycles", "reaction_optimization"),
    ("/reaction-outcome-extraction-runs", "reaction_optimization"),
    ("/reaction-advisor-runs", "reaction_optimization"),
    ("/reaction-mechanistic-hypotheses", "reaction_optimization"),
    ("/reaction-regulatory-constraints", "reaction_optimization"),
    ("/reaction-capabilities", "reaction_optimization"),
    ("/reaction-sdl", "reaction_optimization"),
)

PLATFORM_ROUTE_PREFIXES: tuple[str, ...] = (
    # Reading a drawn structure with RDKit is a shared chemistry primitive, not a Repho
    # feature: Regentry needs it to show a chemist what was read back from an impurity
    # drawing before that structure becomes an ICH M7 verdict, and the compound registry's
    # own structure surface is already platform for the same reason. Filed under Repho it
    # returned 403 module_not_licensed on a Regentry-only deployment, which blocked the
    # round-trip confirmation outright. The path keeps its ``/reactions/`` spelling because
    # the frontend already calls it; the name is the misleading part, not the placement.
    "/reactions/structures",
    # service surface
    "/",
    "/health",
    "/metrics",
    "/queue",
    "/system",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/.well-known",
    # identity, access and provisioning
    "/auth",
    "/organizations",
    "/scim",
    "/security",
    "/admin",
    # tenant operations and commerce
    "/tenants",
    "/tenant-audit-exports",
    "/tenant-data-boundaries",
    "/tenant-entitlements",
    "/tenant-environments",
    "/tenant-security-profiles",
    "/tenant-validation-profiles",
    "/subscription-plans",
    "/feature-flags",
    "/procurement-packages",
    "/onboarding-projects",
    "/implementation-tasks",
    "/pilot",
    "/pilot-programs",
    # the compliance floor — ships with every SKU, which is the point of it
    "/audit",
    "/esignatures",
    "/controlled-records",
    "/record-retention-policies",
    "/data-integrity",
    "/inspection-packages",
    "/system-releases",
    "/deviations",
    "/capa",
    "/validation-center",
    # science substrate shared by all three products
    "/compound-registry",
    "/files",
    "/artifacts",
    "/jobs",
    "/knowledge",
    "/analytics",
    # model / method registries and AI governance
    "/ai",
    "/ml",
    "/method-registry",
    "/method-comparisons",
    "/model-versions",
    "/model-health",
    "/scoring-profiles",
    "/threshold-profiles",
    "/benchmark-datasets",
    "/validation-runs",
    # interoperability
    "/connectors",
    "/integrations",
    "/instrument-watch-folders",
    "/ingestion-runs",
    "/normalization-runs",
    "/external-records",
    "/external-object-links",
    "/mapping-templates",
    "/outbound-sync-jobs",
    "/webhooks",
    # Cross-module orchestration. Deliberately NOT owned by one product: these surfaces exist to
    # join two of them, and their stores already degrade when a side is missing (the
    # spectroscopy→regulatory bridge returns a "blocked" record with a warning rather than an
    # error). Gating them on a single module would be arbitrary; they are served everywhere and
    # report honestly. The mobile command centre aggregates whatever modules are present.
    "/bridges",
    "/cross-module",
    "/product",
    "/mobile",
    # Subject-addressed review tasks reach whichever products a deployment serves, and their
    # authorization is the subject's own rule — so on a single-product deployment there is simply
    # nothing of the other products to address, and the surface degrades to empty rather than
    # needing a gate of its own.
    "/review-tasks",
)


def _matches(path: str, prefix: str) -> bool:
    """Whole-segment prefix match, so ``/benchmark`` does not swallow ``/benchmark-datasets``."""
    if prefix == "/":
        return path == "/"
    return path == prefix or path.startswith(prefix + "/")


def module_for_route(path: str) -> ModuleKey | None:
    """The product that owns ``path``, or ``None`` for platform and unclassified routes.

    Longest match wins, so ``/benchmark/spectracheck`` beats a shorter competing entry.
    """
    best: tuple[int, ModuleKey] | None = None
    for prefix, module in MODULE_ROUTE_PREFIXES:
        if _matches(path, prefix) and (best is None or len(prefix) > best[0]):
            best = (len(prefix), module)
    return best[1] if best else None


def is_platform_route(path: str) -> bool:
    """Whether ``path`` is explicitly classified as shipping with every SKU."""
    return any(_matches(path, prefix) for prefix in PLATFORM_ROUTE_PREFIXES)


def is_classified(path: str) -> bool:
    """Whether ``path`` has been deliberately assigned to a product or to the platform."""
    return module_for_route(path) is not None or is_platform_route(path)


def normalize_enabled_modules(values: tuple[str, ...] | list[str]) -> tuple[ModuleKey, ...]:
    """Validate a configured module list, preserving the canonical product order.

    Raises ``ValueError`` on an unknown key so a typo in ``MOLTRACE_ENABLED_MODULES`` fails at
    startup rather than silently serving nothing.
    """
    requested = {str(value).strip() for value in values if str(value).strip()}
    unknown = sorted(requested - set(ALL_MODULES))
    if unknown:
        raise ValueError(
            f"Unknown module(s) in MOLTRACE_ENABLED_MODULES: {', '.join(unknown)}. "
            f"Valid modules: {', '.join(ALL_MODULES)}."
        )
    if not requested:
        raise ValueError("MOLTRACE_ENABLED_MODULES must name at least one module.")
    return tuple(module for module in ALL_MODULES if module in requested)
