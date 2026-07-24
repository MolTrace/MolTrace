"""Repho R13 wiring — score chemist-supplied routes with the frozen safety + green engines.

The DB-bound seam for :mod:`nmrcheck.reaction_retro`'s *pure* half. A chemist (or an external
tool) supplies a route tree; the store scores it — R6 structural safety on every molecule AND
reagent, Trost atom economy, CHEM21 solvent greenness, brevity — and persists the full scored
record with provenance. This is genuinely usable with no heavy dependency installed.

The *generative* half (``propose_routes`` — AiZynthFinder MCTS) is deliberately NOT wired: the
extra is site-installed-only and the search is long-running with no off-request home in this
deployment. The capability readout (``/admin/ops/reaction-capabilities``) is its honest face
until a worker exists.

Response/request models are co-located here (off the contended ``models.py``, per the R4
precedent).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import reaction_retro
from .database import session_scope
from .orm import AuditEventORM, ReactionProjectORM, ReactionProposedRouteScoreORM
from .reaction_store import ReactionActor, ReactionError


# --------------------------------------------------------------------------- #
# API models (co-located).
# --------------------------------------------------------------------------- #
class ReactionRouteScoreRequest(BaseModel):
    route: dict[str, Any]
    label: str = Field(default="", max_length=200)
    route_format: str = Field(default="native", pattern="^(native|aizynth)$")
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionRouteScoreRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    label: str
    route: dict[str, Any]
    score: dict[str, Any]
    mermaid: str
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any]
    disclaimer: str = reaction_retro.ROUTE_DISCLAIMER


# --------------------------------------------------------------------------- #
# Store functions.
# --------------------------------------------------------------------------- #
def create_route_score(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionRouteScoreRequest,
    *,
    actor: ReactionActor,
) -> ReactionRouteScoreRecord:
    try:
        parser = (
            reaction_retro.route_from_aizynth_dict
            if payload.route_format == "aizynth"
            else reaction_retro.route_from_dict
        )
        route = parser(payload.route)
        score = reaction_retro.score_route(route)
        mermaid = reaction_retro.to_mermaid(route)
    except reaction_retro.ReactionRetroError as exc:
        # A malformed route tree is a client-data problem -> 400, never a 500.
        raise ReactionError(str(exc)) from exc

    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionProposedRouteScoreORM(
            reaction_project_id=project_id,
            label=payload.label,
            route_json=_json_dump(route.as_dict()),
            score_json=_json_dump(score),
            mermaid_text=mermaid,
            created_by_user_id=actor.user_id,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.route_score.create",
            message="Proposed synthesis route scored by the frozen safety and green engines.",
            entity_id=row.id,
            metadata={
                "project_id": project_id,
                "label": payload.label,
                "route_score": score.get("route_score"),
                "worst_risk": (score.get("safety") or {}).get("worst_risk"),
                "step_count": score.get("step_count"),
            },
        )
        return _score_to_record(row)


def list_route_scores(
    session_factory: sessionmaker[Session], project_id: int
) -> list[ReactionRouteScoreRecord]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionProposedRouteScoreORM)
            .where(ReactionProposedRouteScoreORM.reaction_project_id == project_id)
            .order_by(ReactionProposedRouteScoreORM.created_at.desc())
        ).all()
        return [_score_to_record(row) for row in rows]


def get_route_score(
    session_factory: sessionmaker[Session], project_id: int, score_id: int
) -> ReactionRouteScoreRecord | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        # Confine the row to THIS project: the path gate proves the caller owns project_id, but a
        # bare get() by score_id would return another tenant's row when the caller passes their
        # own project on the path and a foreign score_id — a cross-tenant leak.
        row = session.scalars(
            select(ReactionProposedRouteScoreORM).where(
                ReactionProposedRouteScoreORM.reaction_project_id == project_id,
                ReactionProposedRouteScoreORM.id == score_id,
            )
        ).first()
        return _score_to_record(row) if row is not None else None


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _score_to_record(row: ReactionProposedRouteScoreORM) -> ReactionRouteScoreRecord:
    return ReactionRouteScoreRecord(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        label=row.label,
        route=_json_dict(row.route_json),
        score=_json_dict(row.score_json),
        mermaid=row.mermaid_text,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _project_or_raise(session: Session, project_id: int) -> ReactionProjectORM:
    row = session.get(ReactionProjectORM, project_id)
    if row is None:
        raise KeyError("Reaction project not found.")
    return row


def _audit(
    session: Session,
    *,
    actor: ReactionActor,
    event_type: str,
    message: str,
    entity_id: int | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEventORM(
            event_type=event_type,
            message=message,
            actor_user_id=actor.user_id,
            actor_email=actor.email,
            entity_type="reaction_proposed_route_score",
            entity_id=entity_id,
            metadata_json=_json_dump(metadata or {}),
        )
    )


def _json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, default=str)


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
