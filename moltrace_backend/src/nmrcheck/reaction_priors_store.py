"""Repho R10 wiring — persistence + API models for warm-start transfer-learning priors.

The frozen math lives in :mod:`nmrcheck.reaction_priors`; this module is the DB-bound seam. It
gathers **verified** (SpectraCheck-linked or reviewer-confirmed) experiments across the caller's
**owned** source campaigns, scalarises each outcome with the target project's objective profile
(reusing the BO's scoring), builds a content-hashed, gold-excluded snapshot, fits the prior, and
persists it (weights in the DB, not git). It also serves an advisory warm-start ranking of the
latest BO candidates.

Security: source project ids arrive in the request **body**, beyond the reach of the path-based
``require_reaction_access`` gate, so each is owner-checked here (``reaction_project_owned_by``) — a
non-owner source yields a non-leaking 404. Mirrors the cross-module body-id scoping precedent.
Response/request models are co-located here (off the contended ``models.py``, per the R4 precedent).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import reaction_access, reaction_bo, reaction_priors
from .database import session_scope
from .orm import (
    AuditEventORM,
    ReactionAcquisitionCandidateORM,
    ReactionBayesianOptimizationRunORM,
    ReactionExperimentORM,
    ReactionProjectORM,
    ReactionWarmStartPriorORM,
)
from .reaction_store import ReactionActor, ReactionError

_DISCLAIMER = (
    "Warm-start priors are advisory: they bias a new campaign toward conditions that worked on "
    "related, verified campaigns to reach the target in fewer experiments. The prior is fit only "
    "from owned, SpectraCheck-verified data, never the frozen evaluation gold set, and it never "
    "overrides the optimiser or a human decision."
)
_NATIVE = (str, int, float, bool)


# --------------------------------------------------------------------------- #
# API models (co-located).
# --------------------------------------------------------------------------- #
class ReactionWarmStartBuildRequest(BaseModel):
    source_project_ids: list[int] = Field(default_factory=list)
    gold_set_observation_ids: list[str] = Field(default_factory=list)
    objective_target: float | None = None
    require_verified: bool = True
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ReactionWarmStartPriorRecord(BaseModel):
    id: int
    reaction_project_id: int
    snapshot_hash: str
    objective_target: float | None
    global_mean: float
    trained_n: int
    excluded_gold_count: int
    excluded_unverified_count: int
    source_project_ids: list[int]
    lineage: dict[str, Any]
    feature_offsets: dict[str, Any]
    augmentation_count: int
    created_at: datetime
    metadata_json: dict[str, Any]
    disclaimer: str = _DISCLAIMER


class ReactionWarmStartRankedItem(BaseModel):
    proposal_ref: str
    prior_mean: float
    original_rank: int | None
    conditions_json: dict[str, Any]


class ReactionWarmStartRanking(BaseModel):
    reaction_project_id: int
    prior_id: int | None
    bo_run_id: int | None
    global_mean: float | None
    ranked: list[ReactionWarmStartRankedItem]
    advisory: bool = True
    disclaimer: str = _DISCLAIMER


# --------------------------------------------------------------------------- #
# Store functions.
# --------------------------------------------------------------------------- #
def build_prior(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionWarmStartBuildRequest,
    *,
    actor: ReactionActor,
    owner_scope_id: int | None,
) -> ReactionWarmStartPriorRecord:
    """Build + fit + persist a warm-start prior from the caller's owned, verified campaigns."""

    sources = payload.source_project_ids or [project_id]
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        # Owner-scope every body-supplied source campaign (non-leaking 404 if any not owned).
        for source_id in sources:
            if not reaction_access.reaction_project_owned_by(session, source_id, owner_scope_id):
                raise KeyError("Reaction project not found.")

        objective_type, weights = _objective_spec(session, project_id)
        observations = _gather_observations(session, sources, objective_type, weights)
        try:
            snapshot = reaction_priors.build_snapshot(
                observations,
                gold_set_ids=payload.gold_set_observation_ids,
                objective_target=payload.objective_target,
                require_verified=payload.require_verified,
                source=f"warm_start:project:{project_id}",
            )
            prior = reaction_priors.fit_warm_start_prior(snapshot)
        except reaction_priors.ReactionPriorError as exc:
            # A client-data problem (no verified data, duplicate ids, non-native conditions) -> 400.
            raise ReactionError(str(exc)) from exc

        prior_blob = {
            "feature_offsets": prior.feature_offsets,
            "augmentation": prior.augmentation,
            "prior_strength": prior.prior_strength,
            "observation_ids": [row["observation_id"] for row in snapshot.observations],
        }
        row = ReactionWarmStartPriorORM(
            reaction_project_id=project_id,
            snapshot_hash=snapshot.content_hash,
            objective_target=snapshot.objective_target,
            global_mean=prior.global_mean,
            trained_n=prior.trained_n,
            excluded_gold_count=snapshot.excluded_gold_count,
            excluded_unverified_count=snapshot.excluded_unverified_count,
            source_project_ids_json=_json_dump(sorted(set(sources))),
            lineage_json=_json_dump(prior.lineage),
            prior_json=_json_dump(prior_blob),
            created_by_user_id=actor.user_id,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.warm_start.build",
            message="Reaction warm-start prior fit from verified campaign data.",
            entity_id=row.id,
            metadata={
                "project_id": project_id,
                "snapshot_hash": snapshot.content_hash,
                "trained_n": prior.trained_n,
                "excluded_gold_count": snapshot.excluded_gold_count,
                "source_project_ids": sorted(set(sources)),
            },
        )
        return _prior_to_record(row)


def get_latest_prior(
    session_factory: sessionmaker[Session], project_id: int
) -> ReactionWarmStartPriorRecord | None:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = session.scalar(
            select(ReactionWarmStartPriorORM)
            .where(ReactionWarmStartPriorORM.reaction_project_id == project_id)
            .order_by(ReactionWarmStartPriorORM.id.desc())
        )
        return _prior_to_record(row) if row is not None else None


def warm_start_ranking(
    session_factory: sessionmaker[Session], project_id: int
) -> ReactionWarmStartRanking:
    """Advisory: rank the latest BO candidates by the latest warm-start prior-mean (best-first)."""

    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        prior_row = session.scalar(
            select(ReactionWarmStartPriorORM)
            .where(ReactionWarmStartPriorORM.reaction_project_id == project_id)
            .order_by(ReactionWarmStartPriorORM.id.desc())
        )
        bo_run = session.scalar(
            select(ReactionBayesianOptimizationRunORM)
            .where(ReactionBayesianOptimizationRunORM.reaction_project_id == project_id)
            .order_by(ReactionBayesianOptimizationRunORM.id.desc())
        )
        candidates: list[dict[str, Any]] = []
        bo_run_id: int | None = None
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
                    "features": _native_features(_json_dict(candidate.conditions_json)),
                    "conditions_json": _json_dict(candidate.conditions_json),
                }
                for candidate in candidate_rows
            ]

    if prior_row is None:
        return ReactionWarmStartRanking(
            reaction_project_id=project_id,
            prior_id=None,
            bo_run_id=bo_run_id,
            global_mean=None,
            ranked=[],
        )

    prior = _prior_from_row(prior_row)
    ranked = reaction_priors.rank_candidates_by_prior(prior, candidates)
    return ReactionWarmStartRanking(
        reaction_project_id=project_id,
        prior_id=prior_row.id,
        bo_run_id=bo_run_id,
        global_mean=prior.global_mean,
        ranked=[
            ReactionWarmStartRankedItem(
                proposal_ref=str(item.get("proposal_ref")),
                prior_mean=float(item.get("prior_mean", prior.global_mean)),
                original_rank=item.get("rank"),
                conditions_json=item.get("conditions_json") or {},
            )
            for item in ranked
        ],
    )


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _objective_spec(session: Session, project_id: int) -> tuple[str, dict[str, Any]]:
    profile = reaction_bo._latest_objective_profile(session, project_id)
    if profile is None:
        return "multi_objective", {}
    return profile.objective_type, _json_dict(profile.weights_json)


def _gather_observations(
    session: Session,
    source_ids: list[int],
    objective_type: str,
    weights: dict[str, Any],
) -> list[reaction_priors.CampaignObservation]:
    observations: list[reaction_priors.CampaignObservation] = []
    for source_id in source_ids:
        rows = session.scalars(
            select(ReactionExperimentORM).where(
                ReactionExperimentORM.reaction_project_id == source_id
            )
        ).all()
        for exp in rows:
            if exp.status != "completed":
                continue
            outcome = _json_dict(exp.outcome_json)
            score = reaction_bo._score_outcome(outcome, objective_type, weights)
            if score is None:
                continue
            verified = exp.linked_spectracheck_session_id is not None or (
                "outcome_confirmation" in _json_dict(exp.metadata_json)
            )
            observations.append(
                reaction_priors.CampaignObservation(
                    observation_id=f"{source_id}:{exp.id}",
                    features=_native_features(_json_dict(exp.conditions_json)),
                    objective=float(score),
                    verified=verified,
                    source_campaign=str(source_id),
                )
            )
    return observations


def _native_features(conditions: dict[str, Any]) -> dict[str, Any]:
    """Coerce condition values to JSON-native scalars so the snapshot engine accepts them.

    Non-scalar values (lists/dicts) are deterministically serialised to a string so they remain a
    usable feature without tripping the engine's fail-loud non-native guard.
    """

    native: dict[str, Any] = {}
    for name, value in conditions.items():
        if value is None or isinstance(value, _NATIVE):
            native[str(name)] = value
        else:
            native[str(name)] = json.dumps(value, sort_keys=True, default=str)
    return native


def _prior_from_row(row: ReactionWarmStartPriorORM) -> reaction_priors.WarmStartPrior:
    blob = _json_dict(row.prior_json)
    offsets = blob.get("feature_offsets")
    augmentation = blob.get("augmentation")
    return reaction_priors.WarmStartPrior(
        snapshot_hash=row.snapshot_hash,
        global_mean=row.global_mean,
        feature_offsets=offsets if isinstance(offsets, dict) else {},
        augmentation=augmentation if isinstance(augmentation, list) else [],
        prior_strength=float(blob.get("prior_strength") or 0.0),
        lineage=_json_dict(row.lineage_json),
        trained_n=row.trained_n,
    )


def _prior_to_record(row: ReactionWarmStartPriorORM) -> ReactionWarmStartPriorRecord:
    blob = _json_dict(row.prior_json)
    offsets = blob.get("feature_offsets")
    augmentation = blob.get("augmentation")
    return ReactionWarmStartPriorRecord(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        snapshot_hash=row.snapshot_hash,
        objective_target=row.objective_target,
        global_mean=row.global_mean,
        trained_n=row.trained_n,
        excluded_gold_count=row.excluded_gold_count,
        excluded_unverified_count=row.excluded_unverified_count,
        source_project_ids=[int(x) for x in _json_list(row.source_project_ids_json)],
        lineage=_json_dict(row.lineage_json),
        feature_offsets=offsets if isinstance(offsets, dict) else {},
        augmentation_count=len(augmentation) if isinstance(augmentation, list) else 0,
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
            entity_type="reaction_warm_start_prior",
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


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []
