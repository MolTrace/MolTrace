"""Per-user ownership resolution for reaction (Repho) endpoints.

Mirrors the regulatory-dossier owner-scoping model: a reaction project is owned by
``ReactionProjectORM.owner_id``; the owner, a system api-key, or an admin may access it
and all of its children, and everyone else gets a non-leaking 404. This module is the
pure, FastAPI-agnostic resolver — it maps a request's route + path params to the owning
project's ``owner_id`` so the central PDP (:mod:`nmrcheck.authz`) can decide. The route
dependency that calls it lives in ``api.require_reaction_access``.

Almost every reaction child carries ``reaction_project_id`` directly; outcome-extraction
runs and analytical results hop through the execution item. ``batch_id`` is reused by both
execution-batches and recommendation-batches, so child dispatch keys on the route-path
prefix, not the param name alone.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .orm import (
    ReactionBayesianOptimizationRunORM,
    ReactionExecutionBatchORM,
    ReactionExecutionItemORM,
    ReactionExperimentORM,
    ReactionMechanisticHypothesisORM,
    ReactionOptimizationAdvisorRunORM,
    ReactionOptimizationCycleORM,
    ReactionOptimizationRunORM,
    ReactionOutcomeExtractionRunORM,
    ReactionProjectORM,
    ReactionRecommendationBatchORM,
    ReactionRecommendationORM,
    ReactionVariableORM,
    RegulatoryConstraintSetORM,
)

# Bare-child routes (no reaction_project_id in the path): match the route-path prefix to
# the child ORM, the path param carrying its id, and an optional hop attribute for children
# that reach the project via the execution item rather than a direct reaction_project_id.
# (prefix, id_param, ORM, hop_attr)
_CHILD_RESOLVERS: tuple[tuple[str, str, type, str | None], ...] = (
    ("/reaction-experiments/", "experiment_id", ReactionExperimentORM, None),
    ("/reaction-variables/", "variable_id", ReactionVariableORM, None),
    ("/reaction-optimization-runs/", "run_id", ReactionOptimizationRunORM, None),
    ("/reaction-optimization/bo-runs/", "bo_run_id", ReactionBayesianOptimizationRunORM, None),
    ("/reaction-advisor-runs/", "advisor_run_id", ReactionOptimizationAdvisorRunORM, None),
    ("/reaction-recommendations/", "recommendation_id", ReactionRecommendationORM, None),
    ("/reaction-recommendation-batches/", "batch_id", ReactionRecommendationBatchORM, None),
    ("/reaction-execution-batches/", "batch_id", ReactionExecutionBatchORM, None),
    ("/reaction-execution-items/", "item_id", ReactionExecutionItemORM, None),
    ("/reaction-mechanistic-hypotheses/", "hypothesis_id", ReactionMechanisticHypothesisORM, None),
    ("/reaction-optimization-cycles/", "cycle_id", ReactionOptimizationCycleORM, None),
    (
        "/reaction-outcome-extraction-runs/",
        "extraction_run_id",
        ReactionOutcomeExtractionRunORM,
        "execution_item_id",
    ),
    ("/reaction-regulatory-constraints/", "constraint_id", RegulatoryConstraintSetORM, None),
)


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _project_owner(session: Session, project_id: int | None) -> int | None:
    if project_id is None:
        return None
    row = session.get(ReactionProjectORM, project_id)
    return row.owner_id if row is not None else None


def _child_owner(
    session: Session, orm: type, child_id: int | None, *, hop_attr: str | None
) -> int | None:
    if child_id is None:
        return None
    child = session.get(orm, child_id)
    if child is None:
        return None
    project_id = getattr(child, "reaction_project_id", None)
    if project_id is None and hop_attr is not None:
        item_id = getattr(child, hop_attr, None)
        item = session.get(ReactionExecutionItemORM, item_id) if item_id is not None else None
        project_id = getattr(item, "reaction_project_id", None) if item is not None else None
    return _project_owner(session, project_id)


def reaction_owner_id(
    session_factory: sessionmaker[Session], project_id: int | None
) -> int | None:
    """Resolve a reaction project's ``owner_id`` (None for missing/NULL-owner/unknown).

    The reaction analogue of :func:`nmrcheck.regulatory_intelligence.dossier_owner_id`. A
    missing project, a ``None`` id, and a NULL-owner row all collapse to ``None`` so the PDP's
    ownership condition treats them as not-owned for a user-scoped caller (non-leaking 404).
    """
    if project_id is None:
        return None
    with session_scope(session_factory) as session:
        return _project_owner(session, project_id)


def reaction_project_owned_by(
    session: Session, project_id: int | None, owner_scope_id: int | None
) -> bool:
    """Whether a caller scoped to ``owner_scope_id`` may act on a reaction project.

    For **body-supplied** project ids that the path-based ``require_reaction_access`` gate cannot
    reach (cross-module import/export/bridge routes). ``owner_scope_id is None`` means a system
    api-key / admin (unrestricted). Otherwise the project must exist and be owned by the caller; a
    missing project, ``None`` id, or owner mismatch is False, so the route returns a non-leaking
    404.
    """
    if owner_scope_id is None:
        return True
    return _project_owner(session, project_id) == owner_scope_id


def reaction_experiment_owned_by(
    session: Session, experiment_id: int | None, owner_scope_id: int | None
) -> bool:
    """Whether the caller owns a reaction experiment, resolved via its parent project."""
    if owner_scope_id is None:
        return True
    if experiment_id is None:
        return False
    experiment = session.get(ReactionExperimentORM, experiment_id)
    if experiment is None:
        return False
    return _project_owner(session, experiment.reaction_project_id) == owner_scope_id


def reaction_route_owner_id(
    session_factory: sessionmaker[Session],
    route_path: str,
    path_params: dict[str, object],
) -> int | None:
    """Resolve the owning project's ``owner_id`` for a reaction route + its path params.

    Prefers ``reaction_project_id`` when present (covers every nested route); otherwise
    dispatches on the route-path prefix to the child ORM. Returns ``None`` when no reaction
    resource id is present or the resource is missing — which the PDP renders as a non-leaking
    404 for a user-scoped caller (system/admin remain unrestricted).
    """
    with session_scope(session_factory) as session:
        if "reaction_project_id" in path_params:
            return _project_owner(session, _to_int(path_params.get("reaction_project_id")))
        for prefix, id_param, orm, hop_attr in _CHILD_RESOLVERS:
            if route_path.startswith(prefix):
                return _child_owner(
                    session, orm, _to_int(path_params.get(id_param)), hop_attr=hop_attr
                )
    return None


def is_reaction_gated_path(route_path: str) -> bool:
    """Whether a route path must be owner-gated by ``require_reaction_access``.

    True for any route carrying ``{reaction_project_id}`` or matching a bare-child prefix,
    EXCEPT the ``/reaction-projects`` collection (create sets the owner; list is owner-filtered
    in the store). Single source of truth shared by the route wiring and the exhaustive test.
    """
    if route_path == "/reaction-projects":
        return False
    if "{reaction_project_id}" in route_path:
        return True
    return any(route_path.startswith(prefix) for prefix, *_ in _CHILD_RESOLVERS)
