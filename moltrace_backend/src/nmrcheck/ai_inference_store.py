from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    ActiveLearningCandidate,
    ActiveLearningCandidateCreate,
    ActiveLearningCandidateUpdate,
    AIModelMonitoringSummary,
    AIServiceRegistry,
    AIServiceRegistryCreate,
    AIServiceRegistryUpdate,
    CanaryDeploymentCreate,
    CanaryDeploymentRecord,
    CanaryReviewRequest,
    InferenceExplanation,
    InferenceExplanationCreate,
    ModelMonitoringEvent,
    ModelMonitoringEventCreate,
    ModelRoutingDecision,
    ModelRoutingDecisionCreate,
    PredictionAuditEntry,
    PredictionFeedback,
    PredictionFeedbackCreate,
    PredictionFeedbackResponse,
    PredictionRequest,
    PredictionResponse,
    PredictionResult,
    PredictionReviewRequest,
    PredictionRun,
    ShadowEvaluationRun,
    ShadowEvaluationRunCreate,
)
from .orm import (
    ActiveLearningCandidateORM,
    AIServiceRegistryORM,
    AuditEventORM,
    CanaryDeploymentRecordORM,
    DeploymentCandidateORM,
    InferenceExplanationORM,
    ModelArtifactORM,
    ModelImprovementQueueItemORM,
    ModelMonitoringEventORM,
    ModelRoutingDecisionORM,
    PredictionFeedbackORM,
    PredictionResultORM,
    PredictionRunORM,
    PredictionServiceConfigORM,
    ShadowEvaluationRunORM,
    utcnow,
)


class AIInferenceError(ValueError):
    pass


class AIInferenceNotFoundError(AIInferenceError):
    pass


@dataclass(frozen=True)
class AIInferenceActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


_REVIEW_NOTE = (
    "Predictions are model-supported suggestions for review; they are not scientific or "
    "regulatory approvals."
)
_NO_MODEL_WARNING = (
    "No approved executable model artifact was available; production prediction was not faked."
)
_DEV_WARNING = "Development-mode rule_based response requested explicitly; output requires review."
_PRIVATE_KEY_MARKERS = (
    "password",
    "token",
    "secret",
    "api_key",
    "raw_spectrum",
    "raw_spectra",
    "raw_source",
    "source_text",
    "document_text",
    "full_text",
    "full_source",
    "full_smiles",
    "smiles",
    "private_note",
    "private_notes",
    "uploaded_file",
    "file_bytes",
)
_DEFAULT_CONFIDENCE_THRESHOLD = 0.7


BUILTIN_AI_SERVICES: tuple[dict[str, str], ...] = (
    {
        "service_key": "nmr_shift_prediction",
        "name": "NMR shift prediction",
        "target_module": "spectracheck",
        "task_key": "nmr_shift_prediction_baseline",
    },
    {
        "service_key": "nmr_candidate_ranking",
        "name": "NMR candidate ranking",
        "target_module": "spectracheck",
        "task_key": "nmr_candidate_ranking_baseline",
    },
    {
        "service_key": "msms_annotation_scorer",
        "name": "MS/MS annotation scorer",
        "target_module": "msms",
        "task_key": "msms_similarity_scorer",
    },
    {
        "service_key": "lcms_feature_classifier",
        "name": "LCMS feature classifier",
        "target_module": "lcms",
        "task_key": "lcms_feature_family_classifier",
    },
    {
        "service_key": "reaction_outcome_predictor",
        "name": "Reaction outcome predictor",
        "target_module": "reaction_optimization",
        "task_key": "reaction_surrogate_baseline",
    },
    {
        "service_key": "reaction_recommendation_scorer",
        "name": "Reaction recommendation scorer",
        "target_module": "reaction_optimization",
        "task_key": "reaction_surrogate_baseline",
    },
    {
        "service_key": "regulatory_extraction_classifier",
        "name": "Regulatory extraction classifier",
        "target_module": "regulatory",
        "task_key": "regulatory_extraction_classifier",
    },
    {
        "service_key": "citation_support_classifier",
        "name": "Citation support classifier",
        "target_module": "regulatory",
        "task_key": "regulatory_citation_support_classifier",
    },
    {
        "service_key": "knowledge_quality_scorer",
        "name": "Knowledge quality scorer",
        "target_module": "multimodal",
        "task_key": "knowledge_record_quality_classifier",
    },
)

_RESULT_TYPE_BY_SERVICE = {
    "nmr_shift_prediction": "nmr_shift_prediction",
    "nmr_candidate_ranking": "nmr_candidate_ranking",
    "msms_annotation_scorer": "msms_annotation_score",
    "lcms_feature_classifier": "lcms_feature_classification",
    "reaction_outcome_predictor": "reaction_outcome_prediction",
    "reaction_recommendation_scorer": "reaction_recommendation_score",
    "regulatory_extraction_classifier": "regulatory_extraction",
    "citation_support_classifier": "citation_support",
    "knowledge_quality_scorer": "quality_score",
}


def _json_dump(value: Any, *, default: Any = None) -> str:
    return json.dumps(
        _public_json(default if value is None else value),
        sort_keys=True,
        separators=(",", ":"),
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


def _public_json(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if key_lower.startswith("_") or any(
                marker in key_lower for marker in _PRIVATE_KEY_MARKERS
            ):
                continue
            output[key_text] = _public_json(item)
        return output
    if isinstance(value, list):
        return [_public_json(item) for item in value]
    if isinstance(value, str) and len(value) > 800:
        return value[:800] + "...[truncated]"
    return value


def _input_hash(summary: dict[str, Any]) -> str:
    normalized = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _audit(
    session: Session,
    *,
    actor: AIInferenceActor,
    event_type: str,
    message: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
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


def ensure_builtin_services(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as session:
        _ensure_builtin_services(session)


def _ensure_builtin_services(session: Session) -> None:
    existing = {
        service.service_key: service
        for service in session.scalars(select(AIServiceRegistryORM)).all()
    }
    for service in BUILTIN_AI_SERVICES:
        row = existing.get(service["service_key"])
        if row is None:
            session.add(
                AIServiceRegistryORM(
                    service_key=service["service_key"],
                    name=service["name"],
                    target_module=service["target_module"],
                    task_key=service["task_key"],
                    status="draft",
                    metadata_json=_json_dump({"builtin": True}),
                )
            )
        else:
            row.name = service["name"]
            row.target_module = service["target_module"]
            row.task_key = service["task_key"]
            row.updated_at = utcnow()


def list_services(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    limit: int = 500,
) -> list[AIServiceRegistry]:
    with session_scope(session_factory) as session:
        _ensure_builtin_services(session)
        stmt = select(AIServiceRegistryORM).order_by(AIServiceRegistryORM.service_key.asc())
        if status is not None:
            stmt = stmt.where(AIServiceRegistryORM.status == status)
        return [_service_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def create_service(
    session_factory: sessionmaker[Session],
    payload: AIServiceRegistryCreate,
    *,
    actor: AIInferenceActor,
) -> AIServiceRegistry:
    with session_scope(session_factory) as session:
        _validate_service_models(session, payload)
        row = AIServiceRegistryORM(
            service_key=payload.service_key,
            name=payload.name,
            target_module=payload.target_module,
            task_key=payload.task_key,
            active_model_artifact_id=payload.active_model_artifact_id,
            fallback_model_artifact_id=payload.fallback_model_artifact_id,
            prediction_service_config_id=payload.prediction_service_config_id,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise AIInferenceError("AI service already exists for this service_key.") from exc
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.service.create",
            message="AI service registry entry created.",
            entity_type="ai_service",
            entity_id=row.id,
            metadata={"service_key": row.service_key, "status": row.status},
        )
        return _service_to_record(row)


def get_service(
    session_factory: sessionmaker[Session], service_id: int
) -> AIServiceRegistry | None:
    with session_scope(session_factory) as session:
        row = session.get(AIServiceRegistryORM, service_id)
        return _service_to_record(row) if row is not None else None


def update_service(
    session_factory: sessionmaker[Session],
    service_id: int,
    payload: AIServiceRegistryUpdate,
    *,
    actor: AIInferenceActor,
) -> AIServiceRegistry | None:
    with session_scope(session_factory) as session:
        row = session.get(AIServiceRegistryORM, service_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        prospective = AIServiceRegistryCreate(
            service_key=row.service_key,
            name=update.get("name", row.name),
            target_module=update.get("target_module", row.target_module),
            task_key=update.get("task_key", row.task_key),
            active_model_artifact_id=update.get(
                "active_model_artifact_id", row.active_model_artifact_id
            ),
            fallback_model_artifact_id=update.get(
                "fallback_model_artifact_id", row.fallback_model_artifact_id
            ),
            prediction_service_config_id=update.get(
                "prediction_service_config_id", row.prediction_service_config_id
            ),
            status=update.get("status", row.status),
            metadata_json=update.get("metadata_json", _json_dict(row.metadata_json)),
        )
        _validate_service_models(session, prospective)
        for field in (
            "name",
            "target_module",
            "task_key",
            "active_model_artifact_id",
            "fallback_model_artifact_id",
            "prediction_service_config_id",
            "status",
        ):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(update["metadata_json"])
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.service.update",
            message="AI service registry entry updated.",
            entity_type="ai_service",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _service_to_record(row)


def create_prediction(
    session_factory: sessionmaker[Session],
    payload: PredictionRequest,
    *,
    actor: AIInferenceActor,
) -> PredictionResponse:
    with session_scope(session_factory) as session:
        _ensure_builtin_services(session)
        service = _require_service_by_key(session, payload.service_key)
        config = _service_config(session, service)
        decision = _decide_route_row(
            session,
            service=service,
            config=config,
            requested_model_artifact_id=payload.model_artifact_id,
            experimental=payload.experimental,
            metadata=payload.metadata_json,
        )
        selected_artifact_id = decision.selected_model_artifact_id
        deployment_candidate_id = _approved_candidate_id(session, selected_artifact_id)
        warnings = _json_list(decision.warnings_json)
        notes = [_REVIEW_NOTE]
        if decision.fallback_model_artifact_id:
            _monitor_event(
                session,
                service_key=service.service_key,
                model_artifact_id=decision.fallback_model_artifact_id,
                event_type="fallback_used",
                severity="warning",
                message="Fallback model artifact used for prediction routing.",
                metadata={"routing_decision_id": decision.id},
            )
        if selected_artifact_id is None:
            if not payload.development_mode:
                _monitor_event(
                    session,
                    service_key=service.service_key,
                    model_artifact_id=None,
                    event_type="service_failure",
                    severity="warning",
                    message="Prediction rejected because no approved model artifact was available.",
                    metadata={"service_key": service.service_key},
                )
                raise AIInferenceError(_NO_MODEL_WARNING)
            warnings.extend([_NO_MODEL_WARNING, _DEV_WARNING])

        request_summary = _safe_request_summary(payload)
        confidence = _extract_confidence(payload, selected_artifact_id)
        threshold = _confidence_threshold(config)
        ood_status = _extract_ood_status(payload, config)
        uncertainty = _extract_uncertainty(payload, confidence, ood_status)
        human_review_required = True
        status = "succeeded"
        low_confidence = confidence is not None and confidence < threshold
        if low_confidence:
            status = "requires_review"
            warnings.append("Prediction is low confidence and requires review.")
        if ood_status in {"possible_ood", "out_of_domain"}:
            status = "requires_review"
            warnings.append("Prediction input is possible out-of-domain and requires review.")
        if service.target_module == "regulatory":
            status = "requires_review"
            notes.append("Regulatory prediction output requires human review.")

        now = utcnow()
        run = PredictionRunORM(
            service_key=service.service_key,
            target_module=service.target_module,
            task_key=service.task_key,
            model_artifact_id=selected_artifact_id,
            deployment_candidate_id=deployment_candidate_id,
            dataset_version_id=payload.dataset_version_id,
            request_summary_json=_json_dump(request_summary),
            input_hash=_input_hash(request_summary),
            status=status,
            confidence_score=confidence,
            uncertainty_json=_json_dump(uncertainty),
            ood_status=ood_status,
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(notes),
            created_at=now,
            finished_at=now,
            metadata_json=_json_dump(
                {
                    **payload.metadata_json,
                    "routing_decision_id": decision.id,
                    "experimental": payload.experimental,
                    "development_mode": payload.development_mode,
                }
            ),
        )
        session.add(run)
        session.flush()

        explanation = _create_prediction_explanation(
            session,
            run=run,
            confidence=confidence,
            ood_status=ood_status,
            warnings=warnings,
        )
        output = _prediction_output(
            service, payload, selected_artifact_id, development_mode=payload.development_mode
        )
        result = PredictionResultORM(
            prediction_run_id=run.id,
            result_type=payload.requested_result_type
            or _RESULT_TYPE_BY_SERVICE.get(service.service_key, "other"),
            output_json=_json_dump(output),
            confidence_score=confidence,
            uncertainty_json=_json_dump(uncertainty),
            explanation_id=explanation.id,
            human_review_required=human_review_required,
            metadata_json=_json_dump({"routing_decision_id": decision.id}),
        )
        session.add(result)
        session.flush()
        run.prediction_result_id = result.id

        _monitor_event(
            session,
            service_key=service.service_key,
            model_artifact_id=selected_artifact_id,
            event_type="prediction_completed",
            severity="info" if status == "succeeded" else "warning",
            message="Prediction completed and stored for review.",
            metadata={"prediction_run_id": run.id, "status": status},
        )
        active_learning_id = None
        if low_confidence:
            _monitor_event(
                session,
                service_key=service.service_key,
                model_artifact_id=selected_artifact_id,
                event_type="low_confidence",
                severity="warning",
                message="Low confidence prediction requires review.",
                metadata={"prediction_run_id": run.id, "confidence_score": confidence},
            )
            active_learning_id = _create_active_learning_candidate_row(
                session,
                prediction_run_id=run.id,
                source_module=service.target_module,
                reason="low_confidence",
                priority="high",
                metadata={"confidence_score": confidence},
            ).id
        if ood_status in {"possible_ood", "out_of_domain"}:
            _monitor_event(
                session,
                service_key=service.service_key,
                model_artifact_id=selected_artifact_id,
                event_type="out_of_domain",
                severity="high" if ood_status == "out_of_domain" else "warning",
                message="Prediction input triggered possible out-of-domain handling.",
                metadata={"prediction_run_id": run.id, "ood_status": ood_status},
            )
            if active_learning_id is None:
                active_learning_id = _create_active_learning_candidate_row(
                    session,
                    prediction_run_id=run.id,
                    source_module=service.target_module,
                    reason="out_of_domain",
                    priority="high",
                    metadata={"ood_status": ood_status},
                ).id
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.prediction.create",
            message="AI prediction created and stored for review.",
            entity_type="prediction_run",
            entity_id=run.id,
            metadata={
                "service_key": run.service_key,
                "status": run.status,
                "active_learning_candidate_id": active_learning_id,
            },
        )
        return _prediction_response(run, result, explanation)


def list_predictions(
    session_factory: sessionmaker[Session],
    *,
    service_key: str | None = None,
    limit: int = 500,
) -> list[PredictionRun]:
    with session_scope(session_factory) as session:
        stmt = select(PredictionRunORM).order_by(PredictionRunORM.id.desc())
        if service_key is not None:
            stmt = stmt.where(PredictionRunORM.service_key == service_key)
        return [_prediction_run_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def get_prediction(
    session_factory: sessionmaker[Session], prediction_id: int
) -> PredictionResponse | None:
    with session_scope(session_factory) as session:
        run = session.get(PredictionRunORM, prediction_id)
        if run is None:
            return None
        result = _result_for_run(session, run)
        explanation = _explanation_for_result(session, result)
        return _prediction_response(run, result, explanation)


def create_feedback(
    session_factory: sessionmaker[Session],
    prediction_id: int,
    payload: PredictionFeedbackCreate,
    *,
    actor: AIInferenceActor,
) -> PredictionFeedbackResponse:
    with session_scope(session_factory) as session:
        run = _require_prediction_run(session, prediction_id)
        feedback = PredictionFeedbackORM(
            prediction_run_id=run.id,
            feedback_type=payload.feedback_type,
            reason_code=payload.reason_code,
            reviewer_name=payload.reviewer_name,
            reviewer_comment=payload.reviewer_comment,
            corrected_output_json=_json_dump(payload.corrected_output_json)
            if payload.corrected_output_json is not None
            else None,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(feedback)
        session.flush()
        warnings: list[str] = []
        notes = [_REVIEW_NOTE]
        active_learning_id: int | None = None
        queue_item_id: int | None = None
        if payload.feedback_type in {"rejected", "corrected", "error_case", "uncertain"}:
            active_learning_id = _create_active_learning_candidate_row(
                session,
                prediction_run_id=run.id,
                source_module=run.target_module,
                reason="human_correction"
                if payload.feedback_type == "corrected"
                else "model_disagreement",
                priority="high",
                metadata={
                    "feedback_id": feedback.id,
                    "feedback_type": payload.feedback_type,
                    "reason_code": payload.reason_code,
                },
            ).id
            queue_item_id = _create_model_improvement_item(
                session,
                run=run,
                feedback=feedback,
                actor=actor,
            )
            candidate = session.get(ActiveLearningCandidateORM, active_learning_id)
            if candidate is not None:
                candidate.linked_model_improvement_item_id = queue_item_id
        if payload.feedback_type in {"rejected", "error_case"}:
            _monitor_event(
                session,
                service_key=run.service_key,
                model_artifact_id=run.model_artifact_id,
                event_type="human_rejection",
                severity="warning",
                message="Prediction feedback reported a rejected or error-case output.",
                metadata={"prediction_run_id": run.id, "feedback_id": feedback.id},
            )
        _monitor_event(
            session,
            service_key=run.service_key,
            model_artifact_id=run.model_artifact_id,
            event_type="feedback_received",
            severity="info",
            message="Prediction feedback received.",
            metadata={"prediction_run_id": run.id, "feedback_id": feedback.id},
        )
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.feedback.create",
            message="Prediction feedback created.",
            entity_type="prediction_feedback",
            entity_id=feedback.id,
            metadata={
                "prediction_run_id": run.id,
                "feedback_type": feedback.feedback_type,
                "reason_code": feedback.reason_code,
                "model_improvement_item_id": queue_item_id,
            },
        )
        return PredictionFeedbackResponse(
            feedback_id=feedback.id,
            prediction_run_id=run.id,
            feedback_type=feedback.feedback_type,  # type: ignore[arg-type]
            reason_code=feedback.reason_code,  # type: ignore[arg-type]
            active_learning_candidate_id=active_learning_id,
            model_improvement_item_id=queue_item_id,
            warnings=warnings,
            notes=notes,
        )


def review_prediction(
    session_factory: sessionmaker[Session],
    prediction_id: int,
    payload: PredictionReviewRequest,
    *,
    actor: AIInferenceActor,
) -> PredictionFeedbackResponse:
    feedback = PredictionFeedbackCreate(
        feedback_type=payload.decision,
        reason_code=payload.reason_code,
        reviewer_name=payload.reviewer_name,
        reviewer_comment=payload.reviewer_comment,
        corrected_output_json=payload.corrected_output_json,
        metadata_json=payload.metadata_json,
    )
    return create_feedback(session_factory, prediction_id, feedback, actor=actor)


def decide_routing(
    session_factory: sessionmaker[Session],
    payload: ModelRoutingDecisionCreate,
    *,
    actor: AIInferenceActor,
) -> ModelRoutingDecision:
    with session_scope(session_factory) as session:
        _ensure_builtin_services(session)
        service = _require_service_by_key(session, payload.service_key)
        decision = _decide_route_row(
            session,
            service=service,
            config=_service_config(session, service),
            requested_model_artifact_id=None,
            experimental=payload.experimental,
            metadata=payload.metadata_json,
        )
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.routing_decision.create",
            message="Model routing decision created.",
            entity_type="model_routing_decision",
            entity_id=decision.id,
            metadata={"service_key": decision.service_key},
        )
        return _routing_to_record(decision)


def list_routing_decisions(
    session_factory: sessionmaker[Session], *, limit: int = 500
) -> list[ModelRoutingDecision]:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(ModelRoutingDecisionORM).order_by(ModelRoutingDecisionORM.id.desc()).limit(limit)
        ).all()
        return [_routing_to_record(row) for row in rows]


def get_routing_decision(
    session_factory: sessionmaker[Session], decision_id: int
) -> ModelRoutingDecision | None:
    with session_scope(session_factory) as session:
        row = session.get(ModelRoutingDecisionORM, decision_id)
        return _routing_to_record(row) if row is not None else None


def create_explanation(
    session_factory: sessionmaker[Session],
    payload: InferenceExplanationCreate,
    *,
    actor: AIInferenceActor,
) -> InferenceExplanation:
    with session_scope(session_factory) as session:
        if payload.prediction_run_id is not None:
            _require_prediction_run(session, payload.prediction_run_id)
        row = InferenceExplanationORM(
            prediction_run_id=payload.prediction_run_id,
            explanation_type=payload.explanation_type,
            explanation_json=_json_dump(payload.explanation_json),
            summary=payload.summary,
            warnings_json=_json_dump(payload.warnings_json),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.explanation.create",
            message="Inference explanation created.",
            entity_type="inference_explanation",
            entity_id=row.id,
        )
        return _explanation_to_record(row)


def get_explanation(
    session_factory: sessionmaker[Session], explanation_id: int
) -> InferenceExplanation | None:
    with session_scope(session_factory) as session:
        row = session.get(InferenceExplanationORM, explanation_id)
        return _explanation_to_record(row) if row is not None else None


def create_active_learning_candidate(
    session_factory: sessionmaker[Session],
    payload: ActiveLearningCandidateCreate,
    *,
    actor: AIInferenceActor,
) -> ActiveLearningCandidate:
    with session_scope(session_factory) as session:
        if payload.prediction_run_id is not None:
            _require_prediction_run(session, payload.prediction_run_id)
        row = _create_active_learning_candidate_row(
            session,
            prediction_run_id=payload.prediction_run_id,
            source_module=payload.source_module,
            reason=payload.reason,
            priority=payload.priority,
            status=payload.status,
            linked_model_improvement_item_id=payload.linked_model_improvement_item_id,
            metadata=payload.metadata_json,
        )
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.active_learning.create",
            message="Active-learning candidate created.",
            entity_type="active_learning_candidate",
            entity_id=row.id,
        )
        return _active_learning_to_record(row)


def list_active_learning_candidates(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    limit: int = 500,
) -> list[ActiveLearningCandidate]:
    with session_scope(session_factory) as session:
        stmt = select(ActiveLearningCandidateORM).order_by(ActiveLearningCandidateORM.id.desc())
        if status is not None:
            stmt = stmt.where(ActiveLearningCandidateORM.status == status)
        return [_active_learning_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def update_active_learning_candidate(
    session_factory: sessionmaker[Session],
    candidate_id: int,
    payload: ActiveLearningCandidateUpdate,
    *,
    actor: AIInferenceActor,
) -> ActiveLearningCandidate | None:
    with session_scope(session_factory) as session:
        row = session.get(ActiveLearningCandidateORM, candidate_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in ("priority", "status", "linked_model_improvement_item_id"):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(update["metadata_json"])
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.active_learning.update",
            message="Active-learning candidate updated.",
            entity_type="active_learning_candidate",
            entity_id=row.id,
            metadata={"status": row.status},
        )
        return _active_learning_to_record(row)


def create_shadow_evaluation(
    session_factory: sessionmaker[Session],
    payload: ShadowEvaluationRunCreate,
    *,
    actor: AIInferenceActor,
) -> ShadowEvaluationRun:
    with session_scope(session_factory) as session:
        _require_service_by_key(session, payload.service_key)
        _optional_model_artifact(session, payload.production_model_artifact_id)
        _require_model_artifact(session, payload.candidate_model_artifact_id)
        warnings = list(payload.warnings_json)
        if not _approved_candidate_id(session, payload.candidate_model_artifact_id):
            warnings.append(
                "Candidate model artifact is not approved; shadow evaluation requires review."
            )
        row = ShadowEvaluationRunORM(
            service_key=payload.service_key,
            production_model_artifact_id=payload.production_model_artifact_id,
            candidate_model_artifact_id=payload.candidate_model_artifact_id,
            dataset_version_id=payload.dataset_version_id,
            status=payload.status,
            comparison_metrics_json=_json_dump(payload.comparison_metrics_json),
            disagreement_examples_json=_json_dump(payload.disagreement_examples_json),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(payload.notes_json or [_REVIEW_NOTE]),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.shadow_evaluation.create",
            message="Shadow evaluation created without changing active service routing.",
            entity_type="shadow_evaluation_run",
            entity_id=row.id,
        )
        return _shadow_to_record(row)


def list_shadow_evaluations(
    session_factory: sessionmaker[Session], *, limit: int = 500
) -> list[ShadowEvaluationRun]:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(ShadowEvaluationRunORM).order_by(ShadowEvaluationRunORM.id.desc()).limit(limit)
        ).all()
        return [_shadow_to_record(row) for row in rows]


def get_shadow_evaluation(
    session_factory: sessionmaker[Session], shadow_run_id: int
) -> ShadowEvaluationRun | None:
    with session_scope(session_factory) as session:
        row = session.get(ShadowEvaluationRunORM, shadow_run_id)
        return _shadow_to_record(row) if row is not None else None


def create_canary_deployment(
    session_factory: sessionmaker[Session],
    payload: CanaryDeploymentCreate,
    *,
    actor: AIInferenceActor,
) -> CanaryDeploymentRecord:
    with session_scope(session_factory) as session:
        _require_service_by_key(session, payload.service_key)
        _require_model_artifact(session, payload.candidate_model_artifact_id)
        if payload.status in {"approved", "rejected"}:
            raise AIInferenceError("Use canary review endpoints for approval or rejection.")
        row = CanaryDeploymentRecordORM(
            service_key=payload.service_key,
            candidate_model_artifact_id=payload.candidate_model_artifact_id,
            target_module=payload.target_module,
            traffic_percent=payload.traffic_percent,
            status=payload.status,
            monitoring_summary_json=_json_dump(payload.monitoring_summary_json),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.canary.create",
            message="Canary deployment record created; no active model was changed.",
            entity_type="canary_deployment",
            entity_id=row.id,
        )
        return _canary_to_record(row)


def list_canary_deployments(
    session_factory: sessionmaker[Session], *, limit: int = 500
) -> list[CanaryDeploymentRecord]:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(CanaryDeploymentRecordORM)
            .order_by(CanaryDeploymentRecordORM.id.desc())
            .limit(limit)
        ).all()
        return [_canary_to_record(row) for row in rows]


def get_canary_deployment(
    session_factory: sessionmaker[Session], canary_id: int
) -> CanaryDeploymentRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(CanaryDeploymentRecordORM, canary_id)
        return _canary_to_record(row) if row is not None else None


def review_canary_deployment(
    session_factory: sessionmaker[Session],
    canary_id: int,
    payload: CanaryReviewRequest,
    *,
    actor: AIInferenceActor,
    approve: bool,
) -> CanaryDeploymentRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(CanaryDeploymentRecordORM, canary_id)
        if row is None:
            return None
        row.status = "approved" if approve else "rejected"
        row.reviewer_name = payload.reviewer_name
        row.reviewer_comment = payload.reviewer_comment
        row.updated_at = utcnow()
        row.metadata_json = _json_dump({**_json_dict(row.metadata_json), **payload.metadata_json})
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.canary.approve" if approve else "ai_inference.canary.reject",
            message="Canary deployment reviewed by human reviewer; no active model was changed.",
            entity_type="canary_deployment",
            entity_id=row.id,
            metadata={"status": row.status, "reviewer_name": row.reviewer_name},
        )
        return _canary_to_record(row)


def create_monitoring_event(
    session_factory: sessionmaker[Session],
    payload: ModelMonitoringEventCreate,
    *,
    actor: AIInferenceActor,
) -> ModelMonitoringEvent:
    with session_scope(session_factory) as session:
        row = _monitor_event(
            session,
            service_key=payload.service_key,
            model_artifact_id=payload.model_artifact_id,
            event_type=payload.event_type,
            severity=payload.severity,
            message=payload.message,
            metadata=payload.metadata_json,
        )
        _audit(
            session,
            actor=actor,
            event_type="ai_inference.monitoring_event.create",
            message="Model monitoring event created.",
            entity_type="model_monitoring_event",
            entity_id=row.id,
        )
        return _monitoring_to_record(row)


def list_monitoring_events(
    session_factory: sessionmaker[Session],
    *,
    service_key: str | None = None,
    limit: int = 500,
) -> list[ModelMonitoringEvent]:
    with session_scope(session_factory) as session:
        stmt = select(ModelMonitoringEventORM).order_by(ModelMonitoringEventORM.id.desc())
        if service_key is not None:
            stmt = stmt.where(ModelMonitoringEventORM.service_key == service_key)
        return [_monitoring_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def model_monitoring_summary(session_factory: sessionmaker[Session]) -> AIModelMonitoringSummary:
    with session_scope(session_factory) as session:
        recent_events = session.scalars(
            select(ModelMonitoringEventORM).order_by(ModelMonitoringEventORM.id.desc()).limit(10)
        ).all()
        return AIModelMonitoringSummary(
            service_count=_count(session, AIServiceRegistryORM.id),
            active_service_count=_count_where(
                session, AIServiceRegistryORM.id, AIServiceRegistryORM.status == "active"
            ),
            prediction_count=_count(session, PredictionRunORM.id),
            requires_review_count=_count_where(
                session, PredictionRunORM.id, PredictionRunORM.status == "requires_review"
            ),
            low_confidence_event_count=_count_where(
                session,
                ModelMonitoringEventORM.id,
                ModelMonitoringEventORM.event_type == "low_confidence",
            ),
            ood_event_count=_count_where(
                session,
                ModelMonitoringEventORM.id,
                ModelMonitoringEventORM.event_type == "out_of_domain",
            ),
            feedback_count=_count(session, PredictionFeedbackORM.id),
            active_learning_candidate_count=_count(session, ActiveLearningCandidateORM.id),
            recent_events=[_monitoring_to_record(row) for row in recent_events],
            notes=[_REVIEW_NOTE],
            metadata_json={"builtin_ai_service_count": len(BUILTIN_AI_SERVICES)},
        )


def prediction_audit(
    session_factory: sessionmaker[Session], *, limit: int = 200
) -> list[PredictionAuditEntry]:
    with session_scope(session_factory) as session:
        runs = session.scalars(
            select(PredictionRunORM).order_by(PredictionRunORM.id.desc()).limit(limit)
        ).all()
        entries: list[PredictionAuditEntry] = []
        for run in runs:
            result = _result_for_run(session, run)
            feedback_rows = session.scalars(
                select(PredictionFeedbackORM)
                .where(PredictionFeedbackORM.prediction_run_id == run.id)
                .order_by(PredictionFeedbackORM.id.asc())
            ).all()
            candidate_rows = session.scalars(
                select(ActiveLearningCandidateORM)
                .where(ActiveLearningCandidateORM.prediction_run_id == run.id)
                .order_by(ActiveLearningCandidateORM.id.asc())
            ).all()
            entries.append(
                PredictionAuditEntry(
                    prediction_run=_prediction_run_to_record(run),
                    result=_result_to_record(result) if result is not None else None,
                    feedback=[_feedback_to_record(row) for row in feedback_rows],
                    active_learning_candidates=[
                        _active_learning_to_record(row) for row in candidate_rows
                    ],
                )
            )
        return entries


def _count(session: Session, column: Any) -> int:
    return int(session.scalar(select(func.count(column))) or 0)


def _count_where(session: Session, column: Any, criterion: Any) -> int:
    return int(session.scalar(select(func.count(column)).where(criterion)) or 0)


def _validate_service_models(session: Session, payload: AIServiceRegistryCreate) -> None:
    _optional_model_artifact(session, payload.active_model_artifact_id)
    _optional_model_artifact(session, payload.fallback_model_artifact_id)
    if payload.prediction_service_config_id is not None:
        if session.get(PredictionServiceConfigORM, payload.prediction_service_config_id) is None:
            raise AIInferenceNotFoundError("Prediction service config not found.")
    if payload.status == "active" and payload.active_model_artifact_id is not None:
        if not _approved_candidate_id(session, payload.active_model_artifact_id):
            raise AIInferenceError("Active AI services require an approved deployment candidate.")
    if payload.status == "active" and payload.active_model_artifact_id is None:
        raise AIInferenceError("Active AI services require an active_model_artifact_id.")


def _require_service_by_key(session: Session, service_key: str) -> AIServiceRegistryORM:
    row = session.scalar(
        select(AIServiceRegistryORM).where(AIServiceRegistryORM.service_key == service_key)
    )
    if row is None:
        raise AIInferenceNotFoundError("AI service not found.")
    if row.status == "disabled":
        raise AIInferenceError("AI service is disabled.")
    return row


def _require_model_artifact(session: Session, artifact_id: int) -> ModelArtifactORM:
    row = session.get(ModelArtifactORM, artifact_id)
    if row is None:
        raise AIInferenceNotFoundError("Model artifact not found.")
    return row


def _optional_model_artifact(session: Session, artifact_id: int | None) -> ModelArtifactORM | None:
    if artifact_id is None:
        return None
    return _require_model_artifact(session, artifact_id)


def _require_prediction_run(session: Session, prediction_id: int) -> PredictionRunORM:
    row = session.get(PredictionRunORM, prediction_id)
    if row is None:
        raise AIInferenceNotFoundError("Prediction run not found.")
    return row


def _service_config(
    session: Session, service: AIServiceRegistryORM
) -> PredictionServiceConfigORM | None:
    if service.prediction_service_config_id is not None:
        return session.get(PredictionServiceConfigORM, service.prediction_service_config_id)
    return session.scalar(
        select(PredictionServiceConfigORM)
        .where(PredictionServiceConfigORM.service_key == service.service_key)
        .order_by(PredictionServiceConfigORM.id.desc())
        .limit(1)
    )


def _approved_candidate_id(session: Session, artifact_id: int | None) -> int | None:
    if artifact_id is None:
        return None
    return session.scalar(
        select(DeploymentCandidateORM.id)
        .where(
            DeploymentCandidateORM.model_artifact_id == artifact_id,
            DeploymentCandidateORM.status.in_(
                ["approved_for_internal_use", "approved_for_production"]
            ),
        )
        .order_by(DeploymentCandidateORM.id.desc())
        .limit(1)
    )


def _artifact_is_experimental(session: Session, artifact_id: int | None) -> bool:
    if artifact_id is None:
        return False
    artifact = session.get(ModelArtifactORM, artifact_id)
    return bool(artifact and _json_dict(artifact.metadata_json).get("experimental"))


def _decide_route_row(
    session: Session,
    *,
    service: AIServiceRegistryORM,
    config: PredictionServiceConfigORM | None,
    requested_model_artifact_id: int | None,
    experimental: bool,
    metadata: dict[str, Any],
) -> ModelRoutingDecisionORM:
    warnings: list[str] = []
    selected = requested_model_artifact_id or service.active_model_artifact_id
    fallback = service.fallback_model_artifact_id
    if config is not None:
        selected = requested_model_artifact_id or selected or config.active_model_artifact_id
        fallback = fallback or config.fallback_model_artifact_id
    reason = "selected approved model artifact"
    if selected is not None:
        _require_model_artifact(session, selected)
        if _approved_candidate_id(session, selected) is None:
            if experimental and _artifact_is_experimental(session, selected):
                reason = "selected experimental model artifact by explicit request"
                warnings.append("Experimental model was selected explicitly and requires review.")
            elif fallback is not None and _approved_candidate_id(session, fallback) is not None:
                warnings.append("Requested or active model was not approved; fallback used.")
                selected = fallback
                reason = "fallback model artifact selected because primary was unavailable"
            else:
                raise AIInferenceError("Unapproved model artifact cannot be served by default.")
    elif fallback is not None and _approved_candidate_id(session, fallback) is not None:
        selected = fallback
        reason = "fallback model artifact selected"
        warnings.append("Fallback model artifact used.")
    else:
        reason = "no approved model artifact available"
        warnings.append(_NO_MODEL_WARNING)
    row = ModelRoutingDecisionORM(
        service_key=service.service_key,
        target_module=service.target_module,
        selected_model_artifact_id=selected,
        fallback_model_artifact_id=fallback if selected == fallback else None,
        reason=reason,
        routing_metadata_json=_json_dump(
            {
                "requested_model_artifact_id": requested_model_artifact_id,
                "service_status": service.status,
                "config_id": config.id if config is not None else None,
            }
        ),
        warnings_json=_json_dump(warnings),
        metadata_json=_json_dump(metadata),
    )
    session.add(row)
    session.flush()
    return row


def _safe_request_summary(payload: PredictionRequest) -> dict[str, Any]:
    summary = {
        "service_key": payload.service_key,
        "dataset_version_id": payload.dataset_version_id,
        "request_json": _public_json(payload.request_json),
        "candidate_summaries_json": _safe_candidates(payload.candidate_summaries_json),
        "development_mode": payload.development_mode,
        "experimental": payload.experimental,
    }
    return _public_json(summary)


def _safe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed = {
        "candidate_id",
        "id",
        "label",
        "name",
        "summary",
        "score",
        "rank",
        "artifact_id",
        "evidence_id",
    }
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        output.append(
            {key: _public_json(value) for key, value in candidate.items() if key in allowed}
        )
    return output


def _extract_confidence(payload: PredictionRequest, model_artifact_id: int | None) -> float | None:
    for key in ("confidence_score", "mock_confidence_score", "score"):
        value = payload.request_json.get(key)
        if isinstance(value, int | float):
            return max(0.0, min(1.0, float(value)))
    return 0.82 if model_artifact_id is not None else (0.5 if payload.development_mode else None)


def _confidence_threshold(config: PredictionServiceConfigORM | None) -> float:
    if config is None:
        return _DEFAULT_CONFIDENCE_THRESHOLD
    thresholds = _json_dict(config.confidence_thresholds_json)
    value = thresholds.get("min_confidence", thresholds.get("default"))
    if isinstance(value, int | float):
        return float(value)
    return _DEFAULT_CONFIDENCE_THRESHOLD


def _extract_ood_status(
    payload: PredictionRequest, config: PredictionServiceConfigORM | None
) -> str:
    value = payload.request_json.get("ood_status") or payload.metadata_json.get("ood_status")
    if value in {"in_domain", "possible_ood", "out_of_domain", "not_assessed"}:
        return str(value)
    if config is not None:
        rules = _json_dict(config.ood_rules_json)
        if rules.get("force_review"):
            return "possible_ood"
    return "not_assessed"


def _extract_uncertainty(
    payload: PredictionRequest, confidence: float | None, ood_status: str
) -> dict[str, Any]:
    uncertainty = payload.request_json.get("uncertainty_json")
    if isinstance(uncertainty, dict):
        return _public_json(uncertainty)
    return {
        "confidence_gap": None if confidence is None else round(1.0 - confidence, 6),
        "ood_status": ood_status,
    }


def _prediction_output(
    service: AIServiceRegistryORM,
    payload: PredictionRequest,
    model_artifact_id: int | None,
    *,
    development_mode: bool,
) -> dict[str, Any]:
    result_type = payload.requested_result_type or _RESULT_TYPE_BY_SERVICE.get(
        service.service_key, "other"
    )
    return {
        "result_type": result_type,
        "service_key": service.service_key,
        "model_supported_suggestion": model_artifact_id is not None,
        "development_mode": development_mode,
        "candidate_summaries": _safe_candidates(payload.candidate_summaries_json),
        "message": "Prediction generated for review.",
    }


def _create_prediction_explanation(
    session: Session,
    *,
    run: PredictionRunORM,
    confidence: float | None,
    ood_status: str,
    warnings: list[str],
) -> InferenceExplanationORM:
    explanation_type = "ood" if ood_status in {"possible_ood", "out_of_domain"} else "rules"
    row = InferenceExplanationORM(
        prediction_run_id=run.id,
        explanation_type=explanation_type,
        explanation_json=_json_dump(
            {
                "confidence_score": confidence,
                "ood_status": ood_status,
                "routing": "approved_or_explicit_experimental_model_only",
            }
        ),
        summary="Explanation is limited to routing, confidence, and OOD review signals.",
        warnings_json=_json_dump(warnings),
        metadata_json=_json_dump({}),
    )
    session.add(row)
    session.flush()
    return row


def _create_active_learning_candidate_row(
    session: Session,
    *,
    prediction_run_id: int | None,
    source_module: str,
    reason: str,
    priority: str,
    status: str = "proposed",
    linked_model_improvement_item_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> ActiveLearningCandidateORM:
    row = ActiveLearningCandidateORM(
        prediction_run_id=prediction_run_id,
        source_module=_active_learning_source_module(source_module),
        reason=reason,
        priority=priority,
        status=status,
        linked_model_improvement_item_id=linked_model_improvement_item_id,
        metadata_json=_json_dump(metadata or {}),
    )
    session.add(row)
    session.flush()
    return row


def _create_model_improvement_item(
    session: Session,
    *,
    run: PredictionRunORM,
    feedback: PredictionFeedbackORM,
    actor: AIInferenceActor,
) -> int:
    row = ModelImprovementQueueItemORM(
        source_type="error_case"
        if feedback.feedback_type in {"rejected", "error_case"}
        else "human_override",
        target_module=_model_queue_target(run.target_module),
        linked_record_type=None,
        linked_record_id=None,
        priority="high",
        status="open",
        summary=(
            f"Prediction feedback {feedback.feedback_type} for service {run.service_key} "
            "requires model improvement review."
        ),
        metadata_json=_json_dump(
            {
                "prediction_run_id": run.id,
                "feedback_id": feedback.id,
                "human_review_required": True,
            }
        ),
    )
    session.add(row)
    session.flush()
    _audit(
        session,
        actor=actor,
        event_type="knowledge.model_improvement_queue.create",
        message="Model improvement queue item created from prediction feedback.",
        entity_type="model_improvement_queue_item",
        entity_id=row.id,
        metadata={"prediction_run_id": run.id, "feedback_id": feedback.id},
    )
    return row.id


def _model_queue_target(target_module: str) -> str:
    if target_module in {
        "spectracheck",
        "msms",
        "lcms",
        "reaction_optimization",
        "regulatory",
        "report",
    }:
        return target_module
    return "report"


def _active_learning_source_module(target_module: str) -> str:
    if target_module in {
        "spectracheck",
        "msms",
        "lcms",
        "reaction_optimization",
        "regulatory",
        "knowledge_extraction",
        "report",
    }:
        return target_module
    return "knowledge_extraction"


def _monitor_event(
    session: Session,
    *,
    service_key: str,
    model_artifact_id: int | None,
    event_type: str,
    severity: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> ModelMonitoringEventORM:
    row = ModelMonitoringEventORM(
        service_key=service_key,
        model_artifact_id=model_artifact_id,
        event_type=event_type,
        severity=severity,
        message=message,
        metadata_json=_json_dump(metadata or {}),
    )
    session.add(row)
    session.flush()
    return row


def _result_for_run(session: Session, run: PredictionRunORM) -> PredictionResultORM | None:
    if run.prediction_result_id is not None:
        row = session.get(PredictionResultORM, run.prediction_result_id)
        if row is not None:
            return row
    return session.scalar(
        select(PredictionResultORM)
        .where(PredictionResultORM.prediction_run_id == run.id)
        .order_by(PredictionResultORM.id.desc())
        .limit(1)
    )


def _explanation_for_result(
    session: Session, result: PredictionResultORM | None
) -> InferenceExplanationORM | None:
    if result is None or result.explanation_id is None:
        return None
    return session.get(InferenceExplanationORM, result.explanation_id)


def _service_to_record(row: AIServiceRegistryORM) -> AIServiceRegistry:
    return AIServiceRegistry(
        id=row.id,
        service_key=row.service_key,
        name=row.name,
        target_module=row.target_module,  # type: ignore[arg-type]
        task_key=row.task_key,
        active_model_artifact_id=row.active_model_artifact_id,
        fallback_model_artifact_id=row.fallback_model_artifact_id,
        prediction_service_config_id=row.prediction_service_config_id,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _prediction_run_to_record(row: PredictionRunORM) -> PredictionRun:
    return PredictionRun(
        id=row.id,
        service_key=row.service_key,
        target_module=row.target_module,  # type: ignore[arg-type]
        task_key=row.task_key,
        model_artifact_id=row.model_artifact_id,
        deployment_candidate_id=row.deployment_candidate_id,
        dataset_version_id=row.dataset_version_id,
        request_summary_json=_json_dict(row.request_summary_json),
        input_hash=row.input_hash,
        status=row.status,  # type: ignore[arg-type]
        prediction_result_id=row.prediction_result_id,
        confidence_score=row.confidence_score,
        uncertainty_json=_json_dict(row.uncertainty_json),
        ood_status=row.ood_status,  # type: ignore[arg-type]
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_list(row.notes_json),
        created_at=row.created_at,
        finished_at=row.finished_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _result_to_record(row: PredictionResultORM) -> PredictionResult:
    return PredictionResult(
        id=row.id,
        prediction_run_id=row.prediction_run_id,
        result_type=row.result_type,  # type: ignore[arg-type]
        output_json=_json_dict(row.output_json),
        confidence_score=row.confidence_score,
        uncertainty_json=_json_dict(row.uncertainty_json),
        explanation_id=row.explanation_id,
        human_review_required=row.human_review_required,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _prediction_response(
    run: PredictionRunORM,
    result: PredictionResultORM | None,
    explanation: InferenceExplanationORM | None,
) -> PredictionResponse:
    return PredictionResponse(
        prediction_run_id=run.id,
        service_key=run.service_key,
        model_artifact_id=run.model_artifact_id,
        deployment_candidate_id=run.deployment_candidate_id,
        status=run.status,  # type: ignore[arg-type]
        result=_json_dict(result.output_json) if result is not None else {},
        confidence_score=run.confidence_score,
        uncertainty=_json_dict(run.uncertainty_json),
        ood_status=run.ood_status,  # type: ignore[arg-type]
        explanation=_explanation_to_record(explanation) if explanation is not None else None,
        warnings=[str(item) for item in _json_list(run.warnings_json)],
        notes=[str(item) for item in _json_list(run.notes_json)],
        human_review_required=True if result is None else result.human_review_required,
    )


def _routing_to_record(row: ModelRoutingDecisionORM) -> ModelRoutingDecision:
    return ModelRoutingDecision(
        id=row.id,
        service_key=row.service_key,
        target_module=row.target_module,  # type: ignore[arg-type]
        selected_model_artifact_id=row.selected_model_artifact_id,
        fallback_model_artifact_id=row.fallback_model_artifact_id,
        reason=row.reason,
        routing_metadata_json=_json_dict(row.routing_metadata_json),
        warnings_json=_json_list(row.warnings_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _explanation_to_record(row: InferenceExplanationORM) -> InferenceExplanation:
    return InferenceExplanation(
        id=row.id,
        prediction_run_id=row.prediction_run_id,
        explanation_type=row.explanation_type,  # type: ignore[arg-type]
        explanation_json=_json_dict(row.explanation_json),
        summary=row.summary,
        warnings_json=_json_list(row.warnings_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _feedback_to_record(row: PredictionFeedbackORM) -> PredictionFeedback:
    return PredictionFeedback(
        id=row.id,
        prediction_run_id=row.prediction_run_id,
        feedback_type=row.feedback_type,  # type: ignore[arg-type]
        reason_code=row.reason_code,  # type: ignore[arg-type]
        reviewer_name=row.reviewer_name,
        reviewer_comment=row.reviewer_comment,
        corrected_output_json=_json_dict(row.corrected_output_json)
        if row.corrected_output_json is not None
        else None,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _active_learning_to_record(row: ActiveLearningCandidateORM) -> ActiveLearningCandidate:
    return ActiveLearningCandidate(
        id=row.id,
        prediction_run_id=row.prediction_run_id,
        source_module=row.source_module,  # type: ignore[arg-type]
        reason=row.reason,  # type: ignore[arg-type]
        priority=row.priority,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        linked_model_improvement_item_id=row.linked_model_improvement_item_id,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _shadow_to_record(row: ShadowEvaluationRunORM) -> ShadowEvaluationRun:
    return ShadowEvaluationRun(
        id=row.id,
        service_key=row.service_key,
        production_model_artifact_id=row.production_model_artifact_id,
        candidate_model_artifact_id=row.candidate_model_artifact_id,
        dataset_version_id=row.dataset_version_id,
        status=row.status,  # type: ignore[arg-type]
        comparison_metrics_json=_json_dict(row.comparison_metrics_json),
        disagreement_examples_json=_json_list(row.disagreement_examples_json),
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_list(row.notes_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _canary_to_record(row: CanaryDeploymentRecordORM) -> CanaryDeploymentRecord:
    return CanaryDeploymentRecord(
        id=row.id,
        service_key=row.service_key,
        candidate_model_artifact_id=row.candidate_model_artifact_id,
        target_module=row.target_module,  # type: ignore[arg-type]
        traffic_percent=row.traffic_percent,
        status=row.status,  # type: ignore[arg-type]
        monitoring_summary_json=_json_dict(row.monitoring_summary_json),
        reviewer_name=row.reviewer_name,
        reviewer_comment=row.reviewer_comment,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _monitoring_to_record(row: ModelMonitoringEventORM) -> ModelMonitoringEvent:
    return ModelMonitoringEvent(
        id=row.id,
        service_key=row.service_key,
        model_artifact_id=row.model_artifact_id,
        event_type=row.event_type,  # type: ignore[arg-type]
        severity=row.severity,  # type: ignore[arg-type]
        message=row.message,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )
