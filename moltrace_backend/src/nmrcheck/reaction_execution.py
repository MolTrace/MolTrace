from __future__ import annotations

import json
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import reaction_bo, reaction_loop, reaction_safety
from .database import session_scope
from .models import (
    ReactionAnalyticalResult,
    ReactionAnalyticalResultCreate,
    ReactionBayesianOptimizationRunRequest,
    ReactionCycleDecisionCreate,
    ReactionCycleDecisionRecord,
    ReactionExecutionBatch,
    ReactionExecutionBatchCreate,
    ReactionExecutionBatchUpdate,
    ReactionExecutionEvent,
    ReactionExecutionItem,
    ReactionExecutionItemCreate,
    ReactionExecutionItemUpdate,
    ReactionExecutionStatusUpdate,
    ReactionExperiment,
    ReactionOptimizationCycle,
    ReactionOptimizationCycleCreate,
    ReactionOutcome,
    ReactionOutcomeConfirmRequest,
    ReactionOutcomeExtractionRequest,
    ReactionOutcomeExtractionRun,
    ReactionRecommendationConvertRequest,
    ReactionRecommendationConvertResponse,
)
from .orm import (
    AuditEventORM,
    ReactionAnalyticalResultORM,
    ReactionBayesianOptimizationRunORM,
    ReactionCycleDecisionRecordORM,
    ReactionExecutionBatchORM,
    ReactionExecutionEventORM,
    ReactionExecutionItemORM,
    ReactionExperimentORM,
    ReactionOptimizationAdvisorRunORM,
    ReactionOptimizationCycleORM,
    ReactionOutcomeExtractionRunORM,
    ReactionProjectORM,
    ReactionRecommendationBatchORM,
    ReactionRecommendationORM,
    SpectraCheckEvidenceRecordORM,
    SpectraCheckSessionORM,
    utcnow,
)
from .reaction_store import ReactionActor, ReactionError

# Statuses that commit a batch to physical execution — gated by the R6 safety hard-block.
# 'draft' (planning) and terminal/record-keeping states (completed/failed/canceled/…) are not.
_EXECUTION_COMMIT_STATUSES = frozenset({"planned", "running"})

_SAFE_NOTE = (
    "Execution records are planning and analytical feedback records. A reaction becomes a "
    "completed experiment only when the user marks the execution item completed, and each "
    "extracted outcome requires confirmation before updating the official experiment outcome."
)
_OUTCOME_FIELDS = {
    "yield_percent",
    "conversion_percent",
    "selectivity_percent",
    "impurity_percent",
    "nmr_purity_percent",
    "lcms_area_percent",
}
_EXPERIMENT_OUTCOME_FIELDS = _OUTCOME_FIELDS | {"isolated_yield_percent", "notes"}


def create_execution_batch(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionExecutionBatchCreate,
    *,
    actor: ReactionActor,
) -> ReactionExecutionBatch:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        if payload.status in _EXECUTION_COMMIT_STATUSES:
            reaction_safety.assert_execution_allowed(session, project_id)
        row = ReactionExecutionBatchORM(
            reaction_project_id=project_id,
            batch_code=payload.batch_code,
            title=payload.title,
            status=payload.status,
            planned_start=payload.planned_start,
            planned_end=payload.planned_end,
            created_by=payload.created_by or actor.email,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ReactionError(f"Execution batch code already exists: {payload.batch_code}") from exc
        _audit(
            session,
            actor=actor,
            event_type="reaction.execution_batch.create",
            message="Reaction execution batch created as a planning record.",
            entity_type="reaction_execution_batch",
            entity_id=row.id,
            metadata={"project_id": project_id, "status": row.status},
        )
        return _batch_to_record(row)


def list_execution_batches(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionExecutionBatch]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionExecutionBatchORM)
            .where(ReactionExecutionBatchORM.reaction_project_id == project_id)
            .order_by(ReactionExecutionBatchORM.id.desc())
        ).all()
        return [_batch_to_record(row) for row in rows]


def get_execution_batch(
    session_factory: sessionmaker[Session],
    batch_id: int,
) -> ReactionExecutionBatch | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionExecutionBatchORM, batch_id)
        return _batch_to_record(row) if row is not None else None


def patch_execution_batch(
    session_factory: sessionmaker[Session],
    batch_id: int,
    payload: ReactionExecutionBatchUpdate,
    *,
    actor: ReactionActor,
) -> ReactionExecutionBatch | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionExecutionBatchORM, batch_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        if update.get("status") in _EXECUTION_COMMIT_STATUSES:
            reaction_safety.assert_execution_allowed(session, row.reaction_project_id)
        previous_status = row.status
        for field in ("batch_code", "title", "status", "planned_start", "planned_end", "created_by"):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(update["metadata_json"] or {})
        row.updated_at = utcnow()
        try:
            session.flush()
        except IntegrityError as exc:
            raise ReactionError(f"Execution batch code already exists: {row.batch_code}") from exc
        if "status" in update and row.status != previous_status:
            _event(
                session,
                execution_batch_id=row.id,
                event_type="note",
                message=f"Execution batch status changed from {previous_status} to {row.status}.",
                actor_name=_actor_name(actor),
                metadata={"previous_status": previous_status, "status": row.status},
            )
        _audit(
            session,
            actor=actor,
            event_type="reaction.execution_batch.update",
            message="Reaction execution batch updated.",
            entity_type="reaction_execution_batch",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _batch_to_record(row)


def create_execution_item(
    session_factory: sessionmaker[Session],
    batch_id: int,
    payload: ReactionExecutionItemCreate,
    *,
    actor: ReactionActor,
) -> ReactionExecutionItem:
    with session_scope(session_factory) as session:
        batch = _batch_or_raise(session, batch_id)
        recommendation = _recommendation_for_project(
            session,
            batch.reaction_project_id,
            payload.recommendation_id,
        )
        experiment = _experiment_for_project(session, batch.reaction_project_id, payload.experiment_id)
        conditions = dict(payload.conditions_json)
        if not conditions and recommendation is not None:
            conditions = _json_dict(recommendation.conditions_json)
        if not conditions and experiment is not None:
            conditions = _json_dict(experiment.conditions_json)
        row = ReactionExecutionItemORM(
            execution_batch_id=batch.id,
            reaction_project_id=batch.reaction_project_id,
            recommendation_id=payload.recommendation_id,
            experiment_id=payload.experiment_id,
            item_code=payload.item_code,
            status=payload.status,
            conditions_json=_json_dump(conditions),
            checklist_json=_json_dump(payload.checklist_json),
            operator_name=payload.operator_name,
            started_at=payload.started_at,
            completed_at=payload.completed_at,
            failure_reason=payload.failure_reason,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ReactionError(f"Execution item code already exists: {payload.item_code}") from exc
        event_row = _event(
            session,
            execution_item_id=row.id,
            execution_batch_id=batch.id,
            event_type="planned",
            message="Planned experiment execution item created.",
            actor_name=payload.operator_name or _actor_name(actor),
            metadata={"recommendation_id": payload.recommendation_id, "experiment_id": payload.experiment_id},
        )
        _refresh_batch_status(session, batch)
        _audit(
            session,
            actor=actor,
            event_type="reaction.execution_item.create",
            message="Reaction execution item created.",
            entity_type="reaction_execution_item",
            entity_id=row.id,
            metadata={"batch_id": batch.id, "project_id": batch.reaction_project_id},
        )
        session.flush()
        metadata = _json_dict(row.metadata_json)
        metadata["latest_event_id"] = event_row.id
        row.metadata_json = _json_dump(metadata)
        session.flush()
        return _item_to_record(row)


def list_execution_items(
    session_factory: sessionmaker[Session],
    batch_id: int,
) -> list[ReactionExecutionItem]:
    with session_scope(session_factory) as session:
        _batch_or_raise(session, batch_id)
        rows = session.scalars(
            select(ReactionExecutionItemORM)
            .where(ReactionExecutionItemORM.execution_batch_id == batch_id)
            .order_by(ReactionExecutionItemORM.id.asc())
        ).all()
        return [_item_to_record(row) for row in rows]


def patch_execution_item(
    session_factory: sessionmaker[Session],
    item_id: int,
    payload: ReactionExecutionItemUpdate,
    *,
    actor: ReactionActor,
) -> ReactionExecutionItem | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionExecutionItemORM, item_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        previous_status = row.status
        if "recommendation_id" in update:
            _recommendation_for_project(session, row.reaction_project_id, update["recommendation_id"])
            row.recommendation_id = update["recommendation_id"]
        if "experiment_id" in update:
            _experiment_for_project(session, row.reaction_project_id, update["experiment_id"])
            row.experiment_id = update["experiment_id"]
        for field in (
            "item_code",
            "status",
            "operator_name",
            "started_at",
            "completed_at",
            "failure_reason",
        ):
            if field in update:
                setattr(row, field, update[field])
        if "conditions_json" in update:
            row.conditions_json = _json_dump(update["conditions_json"] or {})
        if "checklist_json" in update:
            row.checklist_json = _json_dump(update["checklist_json"] or [])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(update["metadata_json"] or {})
        row.updated_at = utcnow()
        try:
            session.flush()
        except IntegrityError as exc:
            raise ReactionError(f"Execution item code already exists: {row.item_code}") from exc
        if "status" in update and row.status != previous_status:
            _event(
                session,
                execution_item_id=row.id,
                execution_batch_id=row.execution_batch_id,
                event_type=_status_event_type(row.status),
                message=f"Execution item status changed from {previous_status} to {row.status}.",
                actor_name=row.operator_name or _actor_name(actor),
                metadata={"previous_status": previous_status, "status": row.status},
            )
            _sync_experiment_status(session, row)
        batch = session.get(ReactionExecutionBatchORM, row.execution_batch_id)
        if batch is not None:
            _refresh_batch_status(session, batch)
        _audit(
            session,
            actor=actor,
            event_type="reaction.execution_item.update",
            message="Reaction execution item updated.",
            entity_type="reaction_execution_item",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _item_to_record(row)


def convert_recommendation_to_experiment(
    session_factory: sessionmaker[Session],
    recommendation_id: int,
    payload: ReactionRecommendationConvertRequest,
    *,
    actor: ReactionActor,
) -> ReactionRecommendationConvertResponse | None:
    with session_scope(session_factory) as session:
        recommendation = session.get(ReactionRecommendationORM, recommendation_id)
        if recommendation is None:
            return None
        if recommendation.status != "approved":
            raise ReactionError("Only approved recommendations can be converted to planned experiments.")
        metadata = _json_dict(recommendation.metadata_json)
        existing_experiment_id = _int_or_none(metadata.get("converted_experiment_id"))
        experiment = (
            session.get(ReactionExperimentORM, existing_experiment_id)
            if existing_experiment_id is not None
            else None
        )
        if experiment is not None and experiment.reaction_project_id != recommendation.reaction_project_id:
            experiment = None
        if experiment is None:
            experiment_code = payload.experiment_code or f"RXN-REC-{recommendation.id:04d}"
            experiment = ReactionExperimentORM(
                reaction_project_id=recommendation.reaction_project_id,
                experiment_code=experiment_code,
                status="planned",
                conditions_json=recommendation.conditions_json,
                outcome_json="{}",
                metadata_json=_json_dump(
                    {
                        "source_recommendation_id": recommendation.id,
                        "conversion_rationale": payload.rationale,
                        "converted_by": payload.reviewer_name or actor.email,
                        "human_review_required": True,
                        **payload.metadata_json,
                    }
                ),
            )
            session.add(experiment)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ReactionError(f"Experiment code already exists: {experiment_code}") from exc
        metadata.update(
            {
                "converted_experiment_id": experiment.id,
                "converted_at": utcnow().isoformat(),
                "conversion_rationale": payload.rationale,
                "converted_by": payload.reviewer_name or actor.email,
                "conversion_metadata_json": payload.metadata_json,
            }
        )
        recommendation.metadata_json = _json_dump(metadata)
        recommendation.updated_at = utcnow()

        execution_item: ReactionExecutionItemORM | None = None
        event_row: ReactionExecutionEventORM | None = None
        if payload.execution_batch_id is not None:
            batch = _batch_or_raise(session, payload.execution_batch_id)
            if batch.reaction_project_id != recommendation.reaction_project_id:
                raise KeyError("Reaction execution batch not found.")
            item_code = payload.item_code or f"ITEM-REC-{recommendation.id:04d}"
            execution_item = ReactionExecutionItemORM(
                execution_batch_id=batch.id,
                reaction_project_id=recommendation.reaction_project_id,
                recommendation_id=recommendation.id,
                experiment_id=experiment.id,
                item_code=item_code,
                status="planned",
                conditions_json=recommendation.conditions_json,
                checklist_json="[]",
                operator_name=payload.reviewer_name or actor.email,
                metadata_json=_json_dump(
                    {
                        "source": "approved_recommendation_conversion",
                        "conversion_rationale": payload.rationale,
                        "human_review_required": True,
                    }
                ),
            )
            session.add(execution_item)
            try:
                session.flush()
            except IntegrityError as exc:
                raise ReactionError(f"Execution item code already exists: {item_code}") from exc
            event_row = _event(
                session,
                execution_item_id=execution_item.id,
                execution_batch_id=batch.id,
                event_type="planned",
                message="Approved recommendation converted to a planned experiment execution item.",
                actor_name=payload.reviewer_name or _actor_name(actor),
                metadata={"recommendation_id": recommendation.id, "experiment_id": experiment.id},
            )
            _refresh_batch_status(session, batch)

        _audit(
            session,
            actor=actor,
            event_type="reaction.recommendation.convert_to_experiment",
            message="Approved reaction recommendation converted to a planned experiment.",
            entity_type="reaction_recommendation",
            entity_id=recommendation.id,
            metadata={"project_id": recommendation.reaction_project_id, "experiment_id": experiment.id},
        )
        return ReactionRecommendationConvertResponse(
            recommendation_id=recommendation.id,
            reaction_project_id=recommendation.reaction_project_id,
            experiment=_experiment_to_record(experiment),
            execution_item=_item_to_record(execution_item) if execution_item is not None else None,
            event=_event_to_record(event_row) if event_row is not None else None,
            notes=[_SAFE_NOTE],
            human_review_required=True,
        )


def mark_execution_item_running(
    session_factory: sessionmaker[Session],
    item_id: int,
    payload: ReactionExecutionStatusUpdate,
    *,
    actor: ReactionActor,
) -> ReactionExecutionItem | None:
    return _mark_execution_status(
        session_factory,
        item_id,
        status="running",
        event_type="started",
        default_message="Execution item marked running by the user.",
        payload=payload,
        actor=actor,
    )


def mark_execution_item_completed(
    session_factory: sessionmaker[Session],
    item_id: int,
    payload: ReactionExecutionStatusUpdate,
    *,
    actor: ReactionActor,
) -> ReactionExecutionItem | None:
    return _mark_execution_status(
        session_factory,
        item_id,
        status="completed",
        event_type="completed",
        default_message="Execution item marked completed by the user.",
        payload=payload,
        actor=actor,
    )


def mark_execution_item_failed(
    session_factory: sessionmaker[Session],
    item_id: int,
    payload: ReactionExecutionStatusUpdate,
    *,
    actor: ReactionActor,
) -> ReactionExecutionItem | None:
    if not payload.failure_reason and not payload.message:
        raise ReactionError("Marking an execution item failed requires failure_reason or message.")
    return _mark_execution_status(
        session_factory,
        item_id,
        status="failed",
        event_type="failed",
        default_message="Execution item marked failed by the user.",
        payload=payload,
        actor=actor,
    )


def add_analytical_result(
    session_factory: sessionmaker[Session],
    item_id: int,
    payload: ReactionAnalyticalResultCreate,
    *,
    actor: ReactionActor,
) -> ReactionAnalyticalResult | None:
    with session_scope(session_factory) as session:
        item = session.get(ReactionExecutionItemORM, item_id)
        if item is None:
            return None
        _verify_spectracheck_session(session, payload.spectracheck_session_id)
        row = ReactionAnalyticalResultORM(
            execution_item_id=item.id,
            spectracheck_session_id=payload.spectracheck_session_id,
            file_id=payload.file_id,
            artifact_id=payload.artifact_id,
            result_type=payload.result_type,
            summary_json=_json_dump(payload.summary_json),
            qc_status=payload.qc_status,
            source_hash=payload.source_hash,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _event(
            session,
            execution_item_id=item.id,
            execution_batch_id=item.execution_batch_id,
            event_type="analytical_result_added",
            message="Analytical evidence linked to execution item.",
            actor_name=_actor_name(actor),
            metadata={"analytical_result_id": row.id, "result_type": row.result_type},
        )
        _audit(
            session,
            actor=actor,
            event_type="reaction.analytical_result.add",
            message="Reaction analytical evidence linked.",
            entity_type="reaction_analytical_result",
            entity_id=row.id,
            metadata={"execution_item_id": item.id, "result_type": row.result_type},
        )
        return _analytical_result_to_record(row)


def list_analytical_results(
    session_factory: sessionmaker[Session],
    item_id: int,
) -> list[ReactionAnalyticalResult]:
    with session_scope(session_factory) as session:
        item = session.get(ReactionExecutionItemORM, item_id)
        if item is None:
            raise KeyError("Reaction execution item not found.")
        rows = session.scalars(
            select(ReactionAnalyticalResultORM)
            .where(ReactionAnalyticalResultORM.execution_item_id == item_id)
            .order_by(ReactionAnalyticalResultORM.id.asc())
        ).all()
        return [_analytical_result_to_record(row) for row in rows]


def extract_outcome(
    session_factory: sessionmaker[Session],
    item_id: int,
    payload: ReactionOutcomeExtractionRequest,
    *,
    actor: ReactionActor,
) -> ReactionOutcomeExtractionRun | None:
    with session_scope(session_factory) as session:
        item = session.get(ReactionExecutionItemORM, item_id)
        if item is None:
            return None
        result_rows = _analytical_results_for_extraction(session, item_id, payload.analytical_result_id)
        proposed: dict[str, Any] = {}
        sources: list[dict[str, Any]] = []
        for result in result_rows:
            summary = _json_dict(result.summary_json)
            fields = _collect_outcome_fields(summary)
            if fields:
                proposed.update(fields)
                sources.append(
                    {
                        "source": "analytical_result_summary",
                        "analytical_result_id": result.id,
                        "result_type": result.result_type,
                    }
                )
            if result.spectracheck_session_id is not None:
                evidence_fields = _spectracheck_outcome_fields(session, result.spectracheck_session_id)
                if evidence_fields:
                    for key, value in evidence_fields.items():
                        proposed.setdefault(key, value)
                    sources.append(
                        {
                            "source": "spectracheck_evidence",
                            "spectracheck_session_id": result.spectracheck_session_id,
                        }
                    )

        warnings: list[str] = []
        notes = [_SAFE_NOTE, "Proposed outcome values require confirmation before official update."]
        if not result_rows:
            warnings.append("No analytical evidence linked; proposed outcome requires confirmation.")
        if not proposed:
            warnings.append(
                "No extractable analytical outcome fields were found; proposed outcome requires confirmation."
            )
            confidence = "requires_review"
        elif any(key in proposed for key in ("yield_percent", "conversion_percent", "selectivity_percent")):
            confidence = "medium"
            notes.append("Analytical evidence linked with yield, conversion, or selectivity-like fields.")
        else:
            confidence = "low"
            notes.append("Analytical evidence linked with purity or area-like fields only.")

        row = ReactionOutcomeExtractionRunORM(
            execution_item_id=item.id,
            status="requires_review",
            extraction_method=payload.extraction_method,
            proposed_outcome_json=_json_dump(proposed),
            confidence_label=confidence,
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(notes),
            finished_at=utcnow(),
            metadata_json=_json_dump(
                {
                    **payload.metadata_json,
                    "sources": sources,
                    "human_confirmation_required": True,
                }
            ),
        )
        session.add(row)
        session.flush()
        _event(
            session,
            execution_item_id=item.id,
            execution_batch_id=item.execution_batch_id,
            event_type="outcome_extracted",
            message="Proposed outcome extracted from analytical evidence; confirmation is required.",
            actor_name=_actor_name(actor),
            metadata={"extraction_run_id": row.id, "field_count": len(proposed)},
        )
        _audit(
            session,
            actor=actor,
            event_type="reaction.outcome.extract",
            message="Reaction outcome extraction proposed values for review.",
            entity_type="reaction_outcome_extraction_run",
            entity_id=row.id,
            metadata={"execution_item_id": item.id, "field_count": len(proposed)},
        )
        return _extraction_run_to_record(row)


def get_extraction_run(
    session_factory: sessionmaker[Session],
    extraction_run_id: int,
) -> ReactionOutcomeExtractionRun | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionOutcomeExtractionRunORM, extraction_run_id)
        return _extraction_run_to_record(row) if row is not None else None


def confirm_outcome(
    session_factory: sessionmaker[Session],
    item_id: int,
    payload: ReactionOutcomeConfirmRequest,
    *,
    actor: ReactionActor,
) -> ReactionExperiment | None:
    with session_scope(session_factory) as session:
        item = session.get(ReactionExecutionItemORM, item_id)
        if item is None:
            return None
        if item.experiment_id is None:
            raise ReactionError("Outcome confirmation requires a linked reaction experiment.")
        if item.status != "completed":
            raise ReactionError("Outcome confirmation requires the execution item to be marked completed first.")
        experiment = session.get(ReactionExperimentORM, item.experiment_id)
        if experiment is None:
            raise KeyError("Reaction experiment not found.")
        extraction_run = _extraction_run_for_item(session, item.id, payload.extraction_run_id)
        confirmed = dict(payload.confirmed_outcome_json or {})
        if not confirmed and extraction_run is not None:
            confirmed = _json_dict(extraction_run.proposed_outcome_json)
        if not confirmed:
            raise ReactionError("Outcome confirmation requires confirmed_outcome_json or an extraction run.")
        _validate_outcome(confirmed)
        previous = _json_dict(experiment.outcome_json)
        official = {**previous, **confirmed}
        experiment.outcome_json = _json_dump(official)
        experiment.status = "completed"
        metadata = _json_dict(experiment.metadata_json)
        metadata["outcome_confirmation"] = {
            "execution_item_id": item.id,
            "extraction_run_id": extraction_run.id if extraction_run is not None else None,
            "reviewer_name": payload.reviewer_name or actor.email,
            "rationale": payload.rationale,
            "confirmed_at": utcnow().isoformat(),
            "metadata_json": payload.metadata_json,
        }
        experiment.metadata_json = _json_dump(metadata)
        experiment.updated_at = utcnow()
        if extraction_run is not None:
            extraction_metadata = _json_dict(extraction_run.metadata_json)
            extraction_metadata["confirmation"] = {
                "reviewer_name": payload.reviewer_name or actor.email,
                "rationale": payload.rationale,
                "confirmed_at": utcnow().isoformat(),
            }
            extraction_run.metadata_json = _json_dump(extraction_metadata)
        _event(
            session,
            execution_item_id=item.id,
            execution_batch_id=item.execution_batch_id,
            event_type="outcome_confirmed",
            message="Extracted outcome confirmed by reviewer and applied to official experiment outcome.",
            actor_name=payload.reviewer_name or _actor_name(actor),
            metadata={"experiment_id": experiment.id, "extraction_run_id": payload.extraction_run_id},
        )
        batch = session.get(ReactionExecutionBatchORM, item.execution_batch_id)
        if batch is not None:
            _refresh_batch_status(session, batch)
        _audit(
            session,
            actor=actor,
            event_type="reaction.outcome.confirm",
            message="Reaction outcome confirmed by reviewer.",
            entity_type="reaction_experiment",
            entity_id=experiment.id,
            metadata={"execution_item_id": item.id, "field_count": len(confirmed)},
        )
        return _experiment_to_record(experiment)


def create_optimization_cycle(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ReactionOptimizationCycleCreate,
    *,
    actor: ReactionActor,
) -> ReactionOptimizationCycle:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        cycle_number = payload.cycle_number or _next_cycle_number(session, project_id)
        bo_run = _bo_run_for_project(session, project_id, payload.bo_run_id) or _latest_bo_run(session, project_id)
        advisor_run = (
            _advisor_run_for_project(session, project_id, payload.advisor_run_id)
            or _latest_advisor_run(session, project_id)
        )
        recommendation_batch = (
            _recommendation_batch_for_project(session, project_id, payload.recommendation_batch_id)
            or _latest_recommendation_batch(session, project_id)
        )
        execution_batch = _execution_batch_for_project(session, project_id, payload.execution_batch_id)
        summary, warnings, notes, input_count, new_count = _cycle_summary(
            session,
            project_id,
            bo_run=bo_run,
            advisor_run=advisor_run,
            recommendation_batch=recommendation_batch,
            execution_batch=execution_batch,
        )
        status = payload.status
        row = ReactionOptimizationCycleORM(
            reaction_project_id=project_id,
            cycle_number=cycle_number,
            status=status,
            input_experiment_count=input_count,
            new_experiment_count=new_count,
            bo_run_id=bo_run.id if bo_run is not None else None,
            advisor_run_id=advisor_run.id if advisor_run is not None else None,
            recommendation_batch_id=recommendation_batch.id if recommendation_batch is not None else None,
            execution_batch_id=execution_batch.id if execution_batch is not None else None,
            summary_json=_json_dump(summary),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(notes),
            completed_at=utcnow() if status == "completed" else None,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ReactionError(f"Optimization cycle number already exists: {cycle_number}") from exc
        _audit(
            session,
            actor=actor,
            event_type="reaction.optimization_cycle.create",
            message="Reaction optimization cycle summary created.",
            entity_type="reaction_optimization_cycle",
            entity_id=row.id,
            metadata={"project_id": project_id, "cycle_number": row.cycle_number},
        )
        return _cycle_to_record(row)


def list_optimization_cycles(
    session_factory: sessionmaker[Session],
    project_id: int,
) -> list[ReactionOptimizationCycle]:
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        rows = session.scalars(
            select(ReactionOptimizationCycleORM)
            .where(ReactionOptimizationCycleORM.reaction_project_id == project_id)
            .order_by(ReactionOptimizationCycleORM.cycle_number.desc(), ReactionOptimizationCycleORM.id.desc())
        ).all()
        return [_cycle_to_record(row) for row in rows]


def get_optimization_cycle(
    session_factory: sessionmaker[Session],
    cycle_id: int,
) -> ReactionOptimizationCycle | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionOptimizationCycleORM, cycle_id)
        return _cycle_to_record(row) if row is not None else None


def create_cycle_decision(
    session_factory: sessionmaker[Session],
    cycle_id: int,
    payload: ReactionCycleDecisionCreate,
    *,
    actor: ReactionActor,
) -> ReactionCycleDecisionRecord | None:
    with session_scope(session_factory) as session:
        cycle = session.get(ReactionOptimizationCycleORM, cycle_id)
        if cycle is None:
            return None
        row = ReactionCycleDecisionRecordORM(
            optimization_cycle_id=cycle.id,
            decision=payload.decision,
            rationale=payload.rationale,
            reviewer_name=payload.reviewer_name or actor.email,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        metadata = _json_dict(cycle.metadata_json)
        metadata["latest_decision"] = {
            "decision": payload.decision,
            "rationale": payload.rationale,
            "reviewer_name": payload.reviewer_name or actor.email,
            "created_at": utcnow().isoformat(),
        }
        cycle.metadata_json = _json_dump(metadata)
        if payload.decision == "requires_review":
            cycle.status = "requires_review"
        if payload.decision in {"pause", "stop_success", "stop_insufficient_progress"}:
            cycle.status = "completed"
            cycle.completed_at = cycle.completed_at or utcnow()
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.optimization_cycle.decision",
            message="Reaction optimization cycle decision recorded.",
            entity_type="reaction_optimization_cycle",
            entity_id=cycle.id,
            metadata={"decision": payload.decision},
        )
        return _decision_to_record(row)


class ReactionLoopGateError(ReactionError):
    """The DMTA loop may not propose the next batch in its current state (mapped to HTTP 409).

    Subclass of ``ReactionError`` — checked first in ``_raise_reaction_http_error`` so it maps to
    409 (conflict with the loop's state), not the plain 400.
    """


def propose_next_cycle(
    session_factory: sessionmaker[Session],
    cycle_id: int,
    payload: ReactionBayesianOptimizationRunRequest,
    *,
    actor: ReactionActor,
) -> ReactionOptimizationCycle | None:
    """R5 human-gated "propose the next batch" — the half-closed loop's only automated step.

    Only a cycle whose latest decision is ``continue_optimization`` may propose; otherwise raise
    ``ReactionLoopGateError`` (409). When permitted, run a BO batch (PROPOSE) and record a NEW
    **draft** cycle metered with loop metrics + provenance. Nothing is executed: the safety gate is
    consulted (advisory here; the R6 hard-block enforces it at the make/commit boundary) and the
    proposed cycle stays draft until a human commits an execution batch.
    """
    with session_scope(session_factory) as session:
        cycle = session.get(ReactionOptimizationCycleORM, cycle_id)
        if cycle is None:
            return None
        project_id = cycle.reaction_project_id
        latest_decision = _json_dict(cycle.metadata_json).get("latest_decision", {}).get("decision")

    gate = reaction_safety.gate_status(session_factory, project_id)
    verdict = reaction_loop.evaluate_propose_next(latest_decision, gate.status)
    if not verdict.allowed:
        raise ReactionLoopGateError(verdict.reason)

    # PROPOSE (own session); decision-support only — produces recommendations, executes nothing.
    bo_run = reaction_bo.run_bayesian_optimization(
        session_factory, project_id, payload, actor=actor
    )

    metrics = reaction_loop.compute_loop_metrics(new_experiment_count=payload.batch_size)
    cycle_metrics = reaction_loop.build_cycle_metrics_payload(
        metrics,
        bo_run_id=bo_run.id,
        surrogate_model_version=getattr(bo_run, "model_type", None)
        or getattr(bo_run, "model_version", None),
    )
    return create_optimization_cycle(
        session_factory,
        project_id,
        ReactionOptimizationCycleCreate(
            status="draft",
            bo_run_id=bo_run.id,
            metadata_json={
                "cycle_metrics": cycle_metrics,
                "proposed_from_cycle_id": cycle_id,
                "propose_next": verdict.as_dict(),
                "note": (
                    "Proposed next batch (decision-support). Execution requires human signoff "
                    "and a clear safety gate; nothing was executed."
                ),
            },
        ),
        actor=actor,
    )


def _mark_execution_status(
    session_factory: sessionmaker[Session],
    item_id: int,
    *,
    status: str,
    event_type: str,
    default_message: str,
    payload: ReactionExecutionStatusUpdate,
    actor: ReactionActor,
) -> ReactionExecutionItem | None:
    with session_scope(session_factory) as session:
        item = session.get(ReactionExecutionItemORM, item_id)
        if item is None:
            return None
        item.status = status
        item.operator_name = payload.operator_name or item.operator_name
        now = utcnow()
        if status == "running":
            item.started_at = item.started_at or now
        if status == "completed":
            item.completed_at = item.completed_at or now
        if status == "failed":
            item.completed_at = item.completed_at or now
            item.failure_reason = payload.failure_reason or payload.message or item.failure_reason
        metadata = _json_dict(item.metadata_json)
        metadata.update(payload.metadata_json)
        item.metadata_json = _json_dump(metadata)
        item.updated_at = now
        _sync_experiment_status(session, item)
        _event(
            session,
            execution_item_id=item.id,
            execution_batch_id=item.execution_batch_id,
            event_type=event_type,
            message=payload.message or default_message,
            actor_name=payload.operator_name or item.operator_name or _actor_name(actor),
            metadata={"status": status, "failure_reason": item.failure_reason},
        )
        batch = session.get(ReactionExecutionBatchORM, item.execution_batch_id)
        if batch is not None:
            _refresh_batch_status(session, batch)
        _audit(
            session,
            actor=actor,
            event_type=f"reaction.execution_item.{status}",
            message=default_message,
            entity_type="reaction_execution_item",
            entity_id=item.id,
            metadata={"batch_id": item.execution_batch_id, "status": status},
        )
        return _item_to_record(item)


def _project_or_raise(session: Session, project_id: int) -> ReactionProjectORM:
    row = session.get(ReactionProjectORM, project_id)
    if row is None:
        raise KeyError("Reaction project not found.")
    return row


def _batch_or_raise(session: Session, batch_id: int) -> ReactionExecutionBatchORM:
    row = session.get(ReactionExecutionBatchORM, batch_id)
    if row is None:
        raise KeyError("Reaction execution batch not found.")
    return row


def _recommendation_for_project(
    session: Session,
    project_id: int,
    recommendation_id: int | None,
) -> ReactionRecommendationORM | None:
    if recommendation_id is None:
        return None
    row = session.get(ReactionRecommendationORM, recommendation_id)
    if row is None or row.reaction_project_id != project_id:
        raise KeyError("Reaction recommendation not found.")
    return row


def _experiment_for_project(
    session: Session,
    project_id: int,
    experiment_id: int | None,
) -> ReactionExperimentORM | None:
    if experiment_id is None:
        return None
    row = session.get(ReactionExperimentORM, experiment_id)
    if row is None or row.reaction_project_id != project_id:
        raise KeyError("Reaction experiment not found.")
    return row


def _verify_spectracheck_session(session: Session, session_id: int | None) -> None:
    if session_id is None:
        return
    if session.get(SpectraCheckSessionORM, session_id) is None:
        raise KeyError("SpectraCheck session not found.")


def _bo_run_for_project(
    session: Session,
    project_id: int,
    bo_run_id: int | None,
) -> ReactionBayesianOptimizationRunORM | None:
    if bo_run_id is None:
        return None
    row = session.get(ReactionBayesianOptimizationRunORM, bo_run_id)
    if row is None or row.reaction_project_id != project_id:
        raise KeyError("Reaction Bayesian optimization run not found.")
    return row


def _advisor_run_for_project(
    session: Session,
    project_id: int,
    advisor_run_id: int | None,
) -> ReactionOptimizationAdvisorRunORM | None:
    if advisor_run_id is None:
        return None
    row = session.get(ReactionOptimizationAdvisorRunORM, advisor_run_id)
    if row is None or row.reaction_project_id != project_id:
        raise KeyError("Reaction advisor run not found.")
    return row


def _recommendation_batch_for_project(
    session: Session,
    project_id: int,
    batch_id: int | None,
) -> ReactionRecommendationBatchORM | None:
    if batch_id is None:
        return None
    row = session.get(ReactionRecommendationBatchORM, batch_id)
    if row is None or row.reaction_project_id != project_id:
        raise KeyError("Reaction recommendation batch not found.")
    return row


def _execution_batch_for_project(
    session: Session,
    project_id: int,
    batch_id: int | None,
) -> ReactionExecutionBatchORM | None:
    if batch_id is None:
        return None
    row = session.get(ReactionExecutionBatchORM, batch_id)
    if row is None or row.reaction_project_id != project_id:
        raise KeyError("Reaction execution batch not found.")
    return row


def _latest_bo_run(session: Session, project_id: int) -> ReactionBayesianOptimizationRunORM | None:
    return session.scalar(
        select(ReactionBayesianOptimizationRunORM)
        .where(ReactionBayesianOptimizationRunORM.reaction_project_id == project_id)
        .order_by(ReactionBayesianOptimizationRunORM.id.desc())
    )


def _latest_advisor_run(session: Session, project_id: int) -> ReactionOptimizationAdvisorRunORM | None:
    return session.scalar(
        select(ReactionOptimizationAdvisorRunORM)
        .where(ReactionOptimizationAdvisorRunORM.reaction_project_id == project_id)
        .order_by(ReactionOptimizationAdvisorRunORM.id.desc())
    )


def _latest_recommendation_batch(session: Session, project_id: int) -> ReactionRecommendationBatchORM | None:
    return session.scalar(
        select(ReactionRecommendationBatchORM)
        .where(ReactionRecommendationBatchORM.reaction_project_id == project_id)
        .order_by(ReactionRecommendationBatchORM.id.desc())
    )


def _next_cycle_number(session: Session, project_id: int) -> int:
    latest = session.scalar(
        select(ReactionOptimizationCycleORM)
        .where(ReactionOptimizationCycleORM.reaction_project_id == project_id)
        .order_by(ReactionOptimizationCycleORM.cycle_number.desc())
    )
    return 1 if latest is None else latest.cycle_number + 1


def _cycle_summary(
    session: Session,
    project_id: int,
    *,
    bo_run: ReactionBayesianOptimizationRunORM | None,
    advisor_run: ReactionOptimizationAdvisorRunORM | None,
    recommendation_batch: ReactionRecommendationBatchORM | None,
    execution_batch: ReactionExecutionBatchORM | None,
) -> tuple[dict[str, Any], list[str], list[str], int, int]:
    experiments = session.scalars(
        select(ReactionExperimentORM)
        .where(ReactionExperimentORM.reaction_project_id == project_id)
        .order_by(ReactionExperimentORM.id.asc())
    ).all()
    completed = [row for row in experiments if row.status == "completed"]
    new_count = 0
    item_status_counts: dict[str, int] = {}
    if execution_batch is not None:
        items = session.scalars(
            select(ReactionExecutionItemORM)
            .where(ReactionExecutionItemORM.execution_batch_id == execution_batch.id)
            .order_by(ReactionExecutionItemORM.id.asc())
        ).all()
        item_status_counts = dict(Counter(item.status for item in items))
        new_count = sum(1 for item in items if item.experiment_id is not None)
    warnings: list[str] = []
    if not completed:
        warnings.append("No completed experiment outcomes are available for this cycle summary.")
    notes = [
        _SAFE_NOTE,
        "Optimization cycle summarizes linked records and does not schedule experiments.",
    ]
    summary = {
        "completed_experiment_count": len(completed),
        "new_outcome_count": sum(1 for row in completed if _json_dict(row.outcome_json)),
        "latest_bo_run_id": bo_run.id if bo_run is not None else None,
        "latest_advisor_run_id": advisor_run.id if advisor_run is not None else None,
        "recommendation_batch_id": recommendation_batch.id if recommendation_batch is not None else None,
        "execution_batch_id": execution_batch.id if execution_batch is not None else None,
        "execution_batch_status": execution_batch.status if execution_batch is not None else None,
        "execution_item_status_counts": item_status_counts,
        "human_review_required": True,
    }
    return summary, warnings, notes, len(completed), new_count


def _analytical_results_for_extraction(
    session: Session,
    item_id: int,
    analytical_result_id: int | None,
) -> list[ReactionAnalyticalResultORM]:
    if analytical_result_id is not None:
        row = session.get(ReactionAnalyticalResultORM, analytical_result_id)
        if row is None or row.execution_item_id != item_id:
            raise KeyError("Reaction analytical result not found.")
        return [row]
    return session.scalars(
        select(ReactionAnalyticalResultORM)
        .where(ReactionAnalyticalResultORM.execution_item_id == item_id)
        .order_by(ReactionAnalyticalResultORM.id.asc())
    ).all()


def _extraction_run_for_item(
    session: Session,
    item_id: int,
    extraction_run_id: int | None,
) -> ReactionOutcomeExtractionRunORM | None:
    if extraction_run_id is None:
        return None
    row = session.get(ReactionOutcomeExtractionRunORM, extraction_run_id)
    if row is None or row.execution_item_id != item_id:
        raise KeyError("Reaction outcome extraction run not found.")
    return row


def _sync_experiment_status(session: Session, item: ReactionExecutionItemORM) -> None:
    if item.experiment_id is None:
        return
    experiment = session.get(ReactionExperimentORM, item.experiment_id)
    if experiment is None:
        return
    if item.status in {"running", "completed", "failed", "planned"}:
        experiment.status = item.status
        experiment.updated_at = utcnow()
    if item.status == "failed":
        metadata = _json_dict(experiment.metadata_json)
        metadata["execution_failure_reason"] = item.failure_reason
        experiment.metadata_json = _json_dump(metadata)


def _refresh_batch_status(session: Session, batch: ReactionExecutionBatchORM) -> None:
    rows = session.scalars(
        select(ReactionExecutionItemORM).where(ReactionExecutionItemORM.execution_batch_id == batch.id)
    ).all()
    if not rows:
        return
    statuses = {row.status for row in rows}
    target = batch.status
    if "running" in statuses:
        target = "running"
    elif statuses <= {"completed", "skipped", "canceled"}:
        target = "completed" if "completed" in statuses else "canceled"
    elif statuses <= {"failed"}:
        target = "failed"
    elif statuses & {"completed", "failed", "skipped", "canceled"}:
        target = "partially_completed"
    elif statuses <= {"planned"} and batch.status == "draft":
        target = "planned"
    if target != batch.status:
        # An item-driven auto-promotion INTO a commit status (planned/running) is itself a
        # bench commitment — gate it exactly like the direct batch endpoints, so item-level
        # paths (add/patch item, mark-running, recommendation→experiment) cannot bypass the
        # rejected-screening hard-block. Completing/failing items and already-active batches
        # carry no new commitment and are not re-gated.
        if target in _EXECUTION_COMMIT_STATUSES:
            reaction_safety.assert_execution_allowed(session, batch.reaction_project_id)
        batch.status = target
    batch.updated_at = utcnow()


def _status_event_type(status: str) -> str:
    return {
        "planned": "planned",
        "running": "started",
        "completed": "completed",
        "failed": "failed",
        "skipped": "skipped",
        "canceled": "skipped",
    }.get(status, "note")


def _event(
    session: Session,
    *,
    event_type: str,
    message: str,
    execution_item_id: int | None = None,
    execution_batch_id: int | None = None,
    actor_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ReactionExecutionEventORM:
    row = ReactionExecutionEventORM(
        execution_item_id=execution_item_id,
        execution_batch_id=execution_batch_id,
        event_type=event_type,
        message=message,
        actor=actor_name,
        metadata_json=_json_dump(metadata or {}),
    )
    session.add(row)
    session.flush()
    return row


def _spectracheck_outcome_fields(session: Session, session_id: int) -> dict[str, Any]:
    rows = session.scalars(
        select(SpectraCheckEvidenceRecordORM)
        .where(SpectraCheckEvidenceRecordORM.session_id == session_id)
        .order_by(SpectraCheckEvidenceRecordORM.id.asc())
    ).all()
    proposed: dict[str, Any] = {}
    for row in rows:
        for source in (
            _json_dict(row.response_json),
            _json_value(row.evidence_summary_json),
        ):
            fields = _collect_outcome_fields(source)
            for key, value in fields.items():
                proposed.setdefault(key, value)
    return proposed


def _collect_outcome_fields(value: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text in _OUTCOME_FIELDS and _percent_or_none(item) is not None:
                fields[key_text] = _percent_or_none(item)
            elif isinstance(item, (dict, list)):
                for nested_key, nested_value in _collect_outcome_fields(item).items():
                    fields.setdefault(nested_key, nested_value)
    elif isinstance(value, list):
        for item in value:
            for key, nested_value in _collect_outcome_fields(item).items():
                fields.setdefault(key, nested_value)
    return fields


def _validate_outcome(outcome: dict[str, Any]) -> None:
    for key, value in outcome.items():
        if key not in _EXPERIMENT_OUTCOME_FIELDS:
            continue
        if key == "notes":
            continue
        if _percent_or_none(value) is None:
            raise ReactionError(f"Outcome {key} must be a percentage from 0 to 100.")


def _percent_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number > 100:
        return None
    return round(number, 6)


def _batch_to_record(row: ReactionExecutionBatchORM) -> ReactionExecutionBatch:
    return ReactionExecutionBatch(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        batch_code=row.batch_code,
        title=row.title,
        status=row.status,  # type: ignore[arg-type]
        planned_start=row.planned_start,
        planned_end=row.planned_end,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _item_to_record(row: ReactionExecutionItemORM) -> ReactionExecutionItem:
    metadata = _json_dict(row.metadata_json)
    return ReactionExecutionItem(
        id=row.id,
        execution_batch_id=row.execution_batch_id,
        reaction_project_id=row.reaction_project_id,
        recommendation_id=row.recommendation_id,
        experiment_id=row.experiment_id,
        item_code=row.item_code,
        status=row.status,  # type: ignore[arg-type]
        conditions_json=_json_dict(row.conditions_json),
        checklist_json=_json_value(row.checklist_json) or [],
        operator_name=row.operator_name,
        started_at=row.started_at,
        completed_at=row.completed_at,
        failure_reason=row.failure_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=metadata,
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _event_to_record(row: ReactionExecutionEventORM) -> ReactionExecutionEvent:
    return ReactionExecutionEvent(
        id=row.id,
        execution_item_id=row.execution_item_id,
        execution_batch_id=row.execution_batch_id,
        event_type=row.event_type,  # type: ignore[arg-type]
        message=row.message,
        actor=row.actor,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _analytical_result_to_record(row: ReactionAnalyticalResultORM) -> ReactionAnalyticalResult:
    return ReactionAnalyticalResult(
        id=row.id,
        execution_item_id=row.execution_item_id,
        spectracheck_session_id=row.spectracheck_session_id,
        file_id=row.file_id,
        artifact_id=row.artifact_id,
        result_type=row.result_type,  # type: ignore[arg-type]
        summary_json=_json_dict(row.summary_json),
        qc_status=row.qc_status,
        source_hash=row.source_hash,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _extraction_run_to_record(row: ReactionOutcomeExtractionRunORM) -> ReactionOutcomeExtractionRun:
    warnings = [str(item) for item in _json_list(row.warnings_json)]
    notes = [str(item) for item in _json_list(row.notes_json)] or [_SAFE_NOTE]
    return ReactionOutcomeExtractionRun(
        id=row.id,
        execution_item_id=row.execution_item_id,
        status=row.status,  # type: ignore[arg-type]
        extraction_method=row.extraction_method,  # type: ignore[arg-type]
        proposed_outcome_json=_json_dict(row.proposed_outcome_json),
        confidence_label=row.confidence_label,  # type: ignore[arg-type]
        warnings_json=warnings,
        notes_json=notes,
        created_at=row.created_at,
        finished_at=row.finished_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=notes,
        human_review_required=True,
    )


def _cycle_to_record(row: ReactionOptimizationCycleORM) -> ReactionOptimizationCycle:
    warnings = [str(item) for item in _json_list(row.warnings_json)]
    notes = [str(item) for item in _json_list(row.notes_json)] or [_SAFE_NOTE]
    return ReactionOptimizationCycle(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        cycle_number=row.cycle_number,
        status=row.status,  # type: ignore[arg-type]
        input_experiment_count=row.input_experiment_count,
        new_experiment_count=row.new_experiment_count,
        bo_run_id=row.bo_run_id,
        advisor_run_id=row.advisor_run_id,
        recommendation_batch_id=row.recommendation_batch_id,
        execution_batch_id=row.execution_batch_id,
        summary_json=_json_dict(row.summary_json),
        warnings_json=warnings,
        notes_json=notes,
        created_at=row.created_at,
        completed_at=row.completed_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=notes,
        human_review_required=True,
    )


def _decision_to_record(row: ReactionCycleDecisionRecordORM) -> ReactionCycleDecisionRecord:
    return ReactionCycleDecisionRecord(
        id=row.id,
        optimization_cycle_id=row.optimization_cycle_id,
        decision=row.decision,  # type: ignore[arg-type]
        rationale=row.rationale,
        reviewer_name=row.reviewer_name,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _experiment_to_record(row: ReactionExperimentORM) -> ReactionExperiment:
    outcome_json = _json_dict(row.outcome_json)
    return ReactionExperiment(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        experiment_code=row.experiment_code,
        status=row.status,  # type: ignore[arg-type]
        conditions_json=_json_dict(row.conditions_json),
        outcome_json=outcome_json,
        outcome=_outcome_from_json(outcome_json),
        linked_spectracheck_session_id=row.linked_spectracheck_session_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        metadata={"spectracheck_linked": row.linked_spectracheck_session_id is not None},
        human_review_required=True,
    )


def _outcome_from_json(value: dict[str, Any]) -> ReactionOutcome:
    return ReactionOutcome(**{key: value[key] for key in _EXPERIMENT_OUTCOME_FIELDS if key in value})


def _audit(
    session: Session,
    *,
    actor: ReactionActor,
    event_type: str,
    message: str,
    entity_type: str,
    entity_id: int | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEventORM(
            event_type=event_type,
            message=message,
            actor_user_id=actor.user_id,
            actor_email=actor.email,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=_json_dump(metadata or {}),
        )
    )


def _actor_name(actor: ReactionActor) -> str | None:
    return actor.email or ("system_api_key" if actor.system_api_key else None)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_dump(value: Any) -> str:
    return json.dumps(
        value if value is not None else {},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


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


def _json_value(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
