"""Repho R12 wiring — yield-prediction runs over the project's own completed experiments.

The DB-bound seam for :mod:`nmrcheck.reaction_yield_models`. A run fits the *governed lightweight
surrogate* (sklearn GP when installed, else the zero-dependency k-NN) on the calling project's
completed experiments and predicts the requested condition sets. The heavy torch MPNN is **never
fit inline**: training is a long loop with no off-request home in this deployment, and activation
additionally requires a benchmark-gate artifact — so this surface always resolves the fallback and
says so in ``capability_provenance`` rather than pretending otherwise.

Response/request models are co-located here (off the contended ``models.py``, per the R4
precedent).
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import reaction_yield_models
from .database import session_scope
from .orm import (
    AuditEventORM,
    ReactionExperimentORM,
    ReactionProjectORM,
    ReactionYieldPredictionRunORM,
)
from .reaction_store import ReactionActor, ReactionError

_DISCLAIMER = (
    "Yield predictions are advisory decision support from a surrogate fit on this project's own "
    "recorded experiments. They rank candidate conditions for review and are never a synthesis "
    "instruction or a guarantee; a qualified chemist reviews every prediction. The backend that "
    "produced each number is recorded in capability_provenance."
)


# --------------------------------------------------------------------------- #
# API models (co-located).
# --------------------------------------------------------------------------- #
class ReactionYieldPredictionRequest(BaseModel):
    conditions: list[dict[str, Any]] = Field(min_length=1, max_length=200)
    require_verified: bool = False
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionYieldPredictionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conditions: dict[str, Any]
    mean: float
    std: float
    backend: str
    n_samples: int
    warnings: list[str] = Field(default_factory=list)


class ReactionYieldPredictionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    reaction_project_id: int
    backend: str
    trained_n: int
    require_verified: bool
    predictions: list[ReactionYieldPredictionItem]
    capability_provenance: dict[str, Any]
    created_at: datetime
    metadata_json: dict[str, Any]
    disclaimer: str = _DISCLAIMER


# --------------------------------------------------------------------------- #
# Store functions.
# --------------------------------------------------------------------------- #
def create_prediction_run(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionYieldPredictionRequest,
    *,
    actor: ReactionActor,
) -> ReactionYieldPredictionRun:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        examples = _training_examples(
            session, project_id, require_verified=payload.require_verified
        )
        predictor, decision = reaction_yield_models.select_yield_predictor(env=os.environ)
        if isinstance(predictor, reaction_yield_models.TorchMPNNPredictor):
            # Defensive: no promotion evidence is passed above, so the heavy path cannot
            # legitimately resolve here — and even a legitimate activation must not train a
            # 200-epoch torch loop inside a request. Refuse loudly rather than block the worker.
            raise ReactionError(
                "The heavy yield backend cannot be fit inline; use the lightweight surrogate "
                "surface (train the GNN off-request against the benchmark gate)."
            )
        try:
            predictor.fit(examples)
            items = [
                _prediction_item(predictor.predict(conditions), conditions)
                for conditions in payload.conditions
            ]
        except ValueError as exc:
            # A client-data problem (no completed experiments, non-finite yield, unfitted
            # featurizer input) -> 400, never a 500.
            raise ReactionError(str(exc)) from exc

        row = ReactionYieldPredictionRunORM(
            reaction_project_id=project_id,
            backend=predictor.backend_name,
            trained_n=len(examples),
            require_verified=payload.require_verified,
            request_json=_json_dump({"conditions": payload.conditions}),
            predictions_json=_json_dump([item.model_dump() for item in items]),
            capability_provenance_json=_json_dump(decision.as_dict()),
            created_by_user_id=actor.user_id,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.yield_prediction.create",
            message="Reaction yield-prediction run recorded (lightweight surrogate).",
            entity_id=row.id,
            metadata={
                "project_id": project_id,
                "backend": predictor.backend_name,
                "trained_n": len(examples),
                "predicted_n": len(items),
                "require_verified": payload.require_verified,
            },
        )
        return _run_to_record(row)


def list_prediction_runs(
    session_factory: sessionmaker[Session], project_id: int
) -> list[ReactionYieldPredictionRun]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionYieldPredictionRunORM)
            .where(ReactionYieldPredictionRunORM.reaction_project_id == project_id)
            .order_by(ReactionYieldPredictionRunORM.created_at.desc())
        ).all()
        return [_run_to_record(row) for row in rows]


def get_prediction_run(
    session_factory: sessionmaker[Session], project_id: int, run_id: int
) -> ReactionYieldPredictionRun | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = session.scalars(
            select(ReactionYieldPredictionRunORM).where(
                ReactionYieldPredictionRunORM.reaction_project_id == project_id,
                ReactionYieldPredictionRunORM.id == run_id,
            )
        ).first()
        return _run_to_record(row) if row is not None else None


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _training_examples(
    session: Session, project_id: int, *, require_verified: bool
) -> list[reaction_yield_models.YieldExample]:
    rows = session.scalars(
        select(ReactionExperimentORM).where(
            ReactionExperimentORM.reaction_project_id == project_id
        )
    ).all()
    examples: list[reaction_yield_models.YieldExample] = []
    for exp in rows:
        if exp.status != "completed":
            continue
        outcome = _json_dict(exp.outcome_json)
        # Coerce exactly like the platform's canonical outcome read (reaction_store
        # _float_or_none): ingest stores outcome_json raw, so a legitimate row can carry "85"
        # as a string. The surrogate must train on the same value BO scoring reads for that
        # experiment — a stricter local gate would silently drop rows the optimiser uses.
        raw = _float_or_none(outcome.get("yield_percent"))
        if raw is None or not math.isfinite(raw):
            continue
        if require_verified:
            # The R10 verified gate: SpectraCheck-linked or reviewer-confirmed outcomes only.
            verified = exp.linked_spectracheck_session_id is not None or (
                "outcome_confirmation" in _json_dict(exp.metadata_json)
            )
            if not verified:
                continue
        examples.append(
            reaction_yield_models.YieldExample(
                conditions=_json_dict(exp.conditions_json),
                yield_percent=float(raw),
            )
        )
    return examples


def _prediction_item(
    prediction: reaction_yield_models.YieldPrediction, conditions: dict[str, Any]
) -> ReactionYieldPredictionItem:
    return ReactionYieldPredictionItem(
        conditions=conditions,
        mean=prediction.mean,
        std=prediction.std,
        backend=prediction.backend,
        n_samples=prediction.n_samples,
        warnings=list(prediction.warnings),
    )


def _run_to_record(row: ReactionYieldPredictionRunORM) -> ReactionYieldPredictionRun:
    return ReactionYieldPredictionRun(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        backend=row.backend,
        trained_n=row.trained_n,
        require_verified=row.require_verified,
        predictions=[
            ReactionYieldPredictionItem(**item)
            for item in _json_list(row.predictions_json)
            if isinstance(item, dict)
        ],
        capability_provenance=_json_dict(row.capability_provenance_json),
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
            entity_type="reaction_yield_prediction_run",
            entity_id=entity_id,
            metadata_json=_json_dump(metadata or {}),
        )
    )


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []

