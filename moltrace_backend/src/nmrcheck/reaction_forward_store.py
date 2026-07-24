"""Repho R14 wiring — cross-check a supplied forward prediction against the frozen engines.

The DB-bound seam for :mod:`nmrcheck.reaction_forward`'s *pure* half. The client supplies a
forward prediction (predicted products + optional confidence/conditions, from any external model
or a chemist's own hypothesis); the store runs the frozen R6 safety screen and CHEM21 solvent
greenness over it — a transformer's confident product prediction is not a safety opinion — and
persists the annotated record. Genuinely usable with no heavy dependency installed.

The *generative* half (``predict_forward`` — IBM RXN / transformers) is deliberately NOT wired:
both backends need site-installed extras or remote credentials that no deployment carries, so the
endpoint would be a 503 for every customer. The capability readout is its honest face.

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

from . import reaction_forward
from .database import session_scope
from .orm import AuditEventORM, ReactionForwardCheckORM, ReactionProjectORM
from .reaction_store import ReactionActor, ReactionError


# --------------------------------------------------------------------------- #
# API models (co-located).
# --------------------------------------------------------------------------- #
class ReactionForwardCheckRequest(BaseModel):
    reactants_smiles: list[str] = Field(min_length=1, max_length=50)
    products_smiles: list[str] = Field(min_length=1, max_length=50)
    reagents_smiles: list[str] = Field(default_factory=list, max_length=50)
    confidence: float | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="external", max_length=120)
    label: str = Field(default="", max_length=200)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionForwardCheckRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    label: str
    reactants_smiles: list[str]
    reagents_smiles: list[str]
    result: dict[str, Any]
    human_review_required: bool = True
    created_at: datetime
    metadata_json: dict[str, Any]
    disclaimer: str = reaction_forward.FORWARD_DISCLAIMER


# --------------------------------------------------------------------------- #
# Store functions.
# --------------------------------------------------------------------------- #
def create_forward_check(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionForwardCheckRequest,
    *,
    actor: ReactionActor,
) -> ReactionForwardCheckRecord:
    prediction = reaction_forward.ForwardPrediction(
        products_smiles=list(payload.products_smiles),
        confidence=payload.confidence,
        conditions=dict(payload.conditions),
        source=payload.source,
    )
    try:
        result = reaction_forward.cross_check_prediction(
            payload.reactants_smiles,
            prediction,
            reagents_smiles=payload.reagents_smiles,
        )
    except reaction_forward.ReactionForwardError as exc:
        # A malformed prediction payload is a client-data problem -> 400, never a 500.
        raise ReactionError(str(exc)) from exc

    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionForwardCheckORM(
            reaction_project_id=project_id,
            label=payload.label,
            request_json=_json_dump(payload.model_dump()),
            result_json=_json_dump(result),
            created_by_user_id=actor.user_id,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.forward_check.create",
            message="Forward prediction cross-checked against the frozen safety/green engines.",
            entity_id=row.id,
            metadata={
                "project_id": project_id,
                "label": payload.label,
                "source": payload.source,
                "overall_risk": (result.get("safety") or {}).get("overall_risk"),
                "product_count": len(payload.products_smiles),
            },
        )
        return _check_to_record(row)


def list_forward_checks(
    session_factory: sessionmaker[Session], project_id: int
) -> list[ReactionForwardCheckRecord]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionForwardCheckORM)
            .where(ReactionForwardCheckORM.reaction_project_id == project_id)
            .order_by(ReactionForwardCheckORM.created_at.desc())
        ).all()
        return [_check_to_record(row) for row in rows]


def get_forward_check(
    session_factory: sessionmaker[Session], project_id: int, check_id: int
) -> ReactionForwardCheckRecord | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        # Confine the row to THIS project (see reaction_retro_store.get_route_score): filtering on
        # check_id alone would return another tenant's row to a caller who owns the path project.
        row = session.scalars(
            select(ReactionForwardCheckORM).where(
                ReactionForwardCheckORM.reaction_project_id == project_id,
                ReactionForwardCheckORM.id == check_id,
            )
        ).first()
        return _check_to_record(row) if row is not None else None


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _check_to_record(row: ReactionForwardCheckORM) -> ReactionForwardCheckRecord:
    request = _json_dict(row.request_json)
    return ReactionForwardCheckRecord(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        label=row.label,
        reactants_smiles=[str(x) for x in request.get("reactants_smiles") or []],
        reagents_smiles=[str(x) for x in request.get("reagents_smiles") or []],
        result=_json_dict(row.result_json),
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
            entity_type="reaction_forward_check",
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
