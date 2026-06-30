"""Repho R9 wiring — persistence + API models for chemist feedback, preference, A/B.

The frozen math lives in :mod:`nmrcheck.reaction_feedback`; this module is the DB-bound seam:
it persists feedback rows (with the model version that produced the proposal), fits the advisory
preference re-ranker from a project's feedback history, and exposes the A/B promotion gate as
decision-support. Response/request models are co-located here (off the contended ``models.py``,
per the R4 precedent). Owner-scoping is enforced at the route layer (``require_reaction_access``).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import reaction_feedback
from .database import session_scope
from .orm import (
    AuditEventORM,
    ReactionAcquisitionCandidateORM,
    ReactionBayesianOptimizationRunORM,
    ReactionFeedbackORM,
    ReactionProjectORM,
)
from .reaction_feedback import REJECTION_REASONS
from .reaction_store import ReactionActor

_DISCLAIMER = (
    "Reaction feedback feeds an advisory preference re-ranker and an A/B promotion gate; it never "
    "auto-deploys a model and never overrides the optimiser. A safety (unsafe) rejection routes to "
    "the R6 safety screen for hardening and is excluded from preference learning."
)


# --------------------------------------------------------------------------- #
# API models (co-located).
# --------------------------------------------------------------------------- #
class ReactionFeedbackCreateRequest(BaseModel):
    proposal_ref: str = Field(min_length=1, max_length=200)
    decision: Literal["accept", "edit", "reject"]
    reason: str | None = None
    free_text: str = ""
    model_version: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_reason(self) -> ReactionFeedbackCreateRequest:
        if self.decision == "reject" and self.reason is None:
            raise ValueError("a reject requires a reason")
        if self.reason is not None and self.reason not in REJECTION_REASONS:
            raise ValueError(f"reason must be one of {REJECTION_REASONS}")
        return self


class ReactionFeedbackRecord(BaseModel):
    id: int
    reaction_project_id: int
    proposal_ref: str
    decision: str
    reason: str | None
    free_text: str
    model_version: str | None
    features: dict[str, Any]
    is_safety_signal: bool
    routes_to_safety_hardening: bool
    is_preference_learnable: bool
    created_at: datetime
    metadata_json: dict[str, Any]
    disclaimer: str = _DISCLAIMER


class ReactionPreferenceRankedItem(BaseModel):
    proposal_ref: str
    acceptance_score: float
    original_rank: int | None
    conditions_json: dict[str, Any]


class ReactionPreferenceRanking(BaseModel):
    reaction_project_id: int
    bo_run_id: int | None
    model_summary: dict[str, Any]
    ranked: list[ReactionPreferenceRankedItem]
    advisory: bool = True
    disclaimer: str = _DISCLAIMER


class ReactionModelMetricsInput(BaseModel):
    model_version: str = Field(min_length=1)
    metrics: dict[str, float]
    safety_flag_recall: float


class ReactionABEvaluateRequest(BaseModel):
    champion: ReactionModelMetricsInput
    challenger: ReactionModelMetricsInput
    directions: dict[str, str] | None = None
    tolerance: float = 0.0


class ReactionABPromotionVerdict(BaseModel):
    champion_version: str
    challenger_version: str
    promotable: bool
    safety_regression: bool
    dominates: bool
    requires_human_signoff: bool
    rollback_available: bool
    reasons: list[str]
    excluded_metrics: list[str]
    disclaimer: str = _DISCLAIMER


# --------------------------------------------------------------------------- #
# Store functions.
# --------------------------------------------------------------------------- #
def create_feedback(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionFeedbackCreateRequest,
    *,
    actor: ReactionActor,
) -> ReactionFeedbackRecord:
    # The pure engine classifies routing (safety vs preference-learnable); inputs are pre-validated.
    record = reaction_feedback.record_feedback(
        decision=payload.decision,
        proposal_ref=payload.proposal_ref,
        reason=payload.reason,
        free_text=payload.free_text,
        model_version=payload.model_version,
        features=payload.features,
    )
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionFeedbackORM(
            reaction_project_id=project_id,
            proposal_ref=record.proposal_ref,
            decision=record.decision,
            reason=record.reason,
            free_text=record.free_text,
            model_version=record.model_version,
            features_json=_json_dump(record.features),
            is_safety_signal=record.is_safety_signal,
            is_preference_learnable=record.is_preference_learnable,
            created_by_user_id=actor.user_id,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.feedback.create",
            message="Reaction proposal feedback recorded.",
            entity_id=row.id,
            metadata={
                "project_id": project_id,
                "decision": record.decision,
                "reason": record.reason,
                "is_safety_signal": record.is_safety_signal,
                "is_preference_learnable": record.is_preference_learnable,
            },
        )
        if record.is_safety_signal:
            # A safety rejection is high-signal: mark it for R6 hardening, never learned-around.
            _audit(
                session,
                actor=actor,
                event_type="reaction.feedback.safety_routed",
                message=(
                    "Unsafe feedback routed to safety-screening review (R6); "
                    "excluded from preference learning."
                ),
                entity_id=row.id,
                metadata={"project_id": project_id, "proposal_ref": record.proposal_ref},
            )
        return _feedback_to_record(row)


def list_feedback(
    session_factory: sessionmaker[Session], project_id: int
) -> list[ReactionFeedbackRecord]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionFeedbackORM)
            .where(ReactionFeedbackORM.reaction_project_id == project_id)
            .order_by(ReactionFeedbackORM.id.desc())
        ).all()
        return [_feedback_to_record(row) for row in rows]


def preference_ranking(
    session_factory: sessionmaker[Session], project_id: int
) -> ReactionPreferenceRanking:
    """Fit the advisory preference model from feedback and re-rank the latest BO batch.

    The optimiser's own rank is preserved on each item — this is a suggestion, not an override.
    """

    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        feedback_rows = session.scalars(
            select(ReactionFeedbackORM).where(
                ReactionFeedbackORM.reaction_project_id == project_id
            )
        ).all()
        records = [
            reaction_feedback.record_feedback(
                decision=row.decision,
                proposal_ref=row.proposal_ref,
                reason=row.reason,
                features=_json_dict(row.features_json),
            )
            for row in feedback_rows
        ]
        bo_run = session.scalar(
            select(ReactionBayesianOptimizationRunORM)
            .where(ReactionBayesianOptimizationRunORM.reaction_project_id == project_id)
            .order_by(ReactionBayesianOptimizationRunORM.id.desc())
        )
        bo_run_id: int | None = None
        candidates: list[dict[str, Any]] = []
        if bo_run is not None:
            bo_run_id = bo_run.id
            candidate_rows = session.scalars(
                select(ReactionAcquisitionCandidateORM)
                .where(ReactionAcquisitionCandidateORM.bo_run_id == bo_run.id)
                .order_by(ReactionAcquisitionCandidateORM.rank.asc())
            ).all()
            candidates = [
                {
                    "proposal_ref": str(candidate.id),
                    "rank": candidate.rank,
                    "features": _json_dict(candidate.conditions_json),
                }
                for candidate in candidate_rows
            ]

    model = reaction_feedback.fit_preference_model(records)
    ranked = reaction_feedback.rank_by_acceptance(model, candidates)
    return ReactionPreferenceRanking(
        reaction_project_id=project_id,
        bo_run_id=bo_run_id,
        model_summary=model.as_dict(),
        ranked=[
            ReactionPreferenceRankedItem(
                proposal_ref=item.proposal_ref,
                acceptance_score=item.acceptance_score,
                original_rank=item.original_rank,
                conditions_json=item.features,
            )
            for item in ranked
        ],
    )


def evaluate_ab_promotion(payload: ReactionABEvaluateRequest) -> ReactionABPromotionVerdict:
    """Pure decision-support: gate a challenger model against the champion (no DB, no deploy)."""

    champion = reaction_feedback.ModelMetrics(
        model_version=payload.champion.model_version,
        metrics=dict(payload.champion.metrics),
        safety_flag_recall=payload.champion.safety_flag_recall,
    )
    challenger = reaction_feedback.ModelMetrics(
        model_version=payload.challenger.model_version,
        metrics=dict(payload.challenger.metrics),
        safety_flag_recall=payload.challenger.safety_flag_recall,
    )
    verdict = reaction_feedback.evaluate_ab_promotion(
        champion, challenger, directions=payload.directions, tolerance=payload.tolerance
    )
    return ReactionABPromotionVerdict(
        champion_version=champion.model_version,
        challenger_version=challenger.model_version,
        promotable=verdict.promotable,
        safety_regression=verdict.safety_regression,
        dominates=verdict.dominates,
        requires_human_signoff=verdict.requires_human_signoff,
        rollback_available=verdict.rollback_available,
        reasons=verdict.reasons,
        excluded_metrics=verdict.excluded_metrics,
    )


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _feedback_to_record(row: ReactionFeedbackORM) -> ReactionFeedbackRecord:
    return ReactionFeedbackRecord(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        proposal_ref=row.proposal_ref,
        decision=row.decision,
        reason=row.reason,
        free_text=row.free_text,
        model_version=row.model_version,
        features=_json_dict(row.features_json),
        is_safety_signal=row.is_safety_signal,
        routes_to_safety_hardening=row.is_safety_signal,
        is_preference_learnable=row.is_preference_learnable,
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
            entity_type="reaction_feedback",
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
