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

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, sessionmaker

from . import org_membership
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


def project_scope_predicate(session: Session, owner_scope_id: int) -> Any:
    """The SQL predicate for reaction projects a user-scoped caller may see.

    The row-level counterpart of :func:`reaction_project_owned_by`, and it must stay in step with
    it: any query that scopes campaigns (or joins to them to scope their children) uses this, so a
    caller is never shown a campaign they cannot open, nor allowed to open one whose children are
    then invisible. Only call this for a user-scoped caller.
    """
    org_ids = org_membership.active_org_ids_for_user(session, owner_scope_id)
    owned = ReactionProjectORM.owner_id == owner_scope_id
    if not org_ids:
        return owned
    return or_(owned, ReactionProjectORM.organization_id.in_(org_ids))


def project_team_access(session: Session, project_id: int | None, user_id: int | None) -> bool:
    """Whether ``user_id`` reaches ``project_id`` through its owning organization."""
    if project_id is None:
        return False
    row = session.get(ReactionProjectORM, project_id)
    return row is not None and org_membership.user_shares_org(
        session, user_id, row.organization_id
    )


def _child_project_id(
    session: Session, orm: type, child_id: int | None, *, hop_attr: str | None
) -> int | None:
    """The owning project's id for a reaction child row, following one optional hop."""
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
    return project_id


def _child_owner(
    session: Session, orm: type, child_id: int | None, *, hop_attr: str | None
) -> int | None:
    return _project_owner(session, _child_project_id(session, orm, child_id, hop_attr=hop_attr))


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
    404 — unless the caller reaches it through the project's owning organization, which widens
    access the same way the path gate does.
    """
    if owner_scope_id is None:
        return True
    if _project_owner(session, project_id) == owner_scope_id:
        return True
    return project_team_access(session, project_id, owner_scope_id)


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
    return reaction_project_owned_by(session, experiment.reaction_project_id, owner_scope_id)


def reaction_route_access_facts(
    session_factory: sessionmaker[Session],
    route_path: str,
    path_params: dict[str, object],
    user_id: int | None,
) -> tuple[int | None, bool]:
    """``(owner_user_id, caller_has_team_access)`` for a reaction route, in one session.

    The policy engine's conditions are pure — they receive no database session — so both facts it
    needs are gathered here and handed in. Mirrors
    ``regulatory_intelligence.dossier_access_facts``; see that docstring for the reasoning.
    """
    with session_scope(session_factory) as session:
        project_id = _route_project_id(session, route_path, path_params)
        if project_id is None:
            return None, False
        row = session.get(ReactionProjectORM, project_id)
        if row is None:
            return None, False
        team_access = org_membership.user_shares_org(session, user_id, row.organization_id)
        return row.owner_id, team_access


def _route_project_id(
    session: Session, route_path: str, path_params: dict[str, object]
) -> int | None:
    """The owning project's id for a reaction route, or ``None`` when none is addressed."""
    if "reaction_project_id" in path_params:
        return _to_int(path_params.get("reaction_project_id"))
    for prefix, id_param, orm, hop_attr in _CHILD_RESOLVERS:
        if route_path.startswith(prefix):
            return _child_project_id(
                session, orm, _to_int(path_params.get(id_param)), hop_attr=hop_attr
            )
    return None


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
