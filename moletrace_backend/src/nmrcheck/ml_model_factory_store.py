from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    CalibrationAssessment,
    CalibrationAssessmentCreate,
    DeploymentCandidate,
    DeploymentCandidateApprovalRequest,
    DeploymentCandidateCreate,
    DeploymentCandidateRejectRequest,
    DeploymentCandidateResponse,
    ErrorAnalysisSlice,
    ErrorAnalysisSliceCreate,
    FeaturePipeline,
    FeaturePipelineCreate,
    MLEvaluationRun,
    MLEvaluationRunCreate,
    MLEvaluationRunResponse,
    MLModelHealthSummary,
    MLTaskDefinition,
    MLTaskDefinitionCreate,
    MLTrainingRun,
    MLTrainingRunCreate,
    MLTrainingRunResponse,
    ModelArtifact,
    ModelCard,
    ModelCardCreate,
    ModelCardUpdate,
    ModelMetric,
    OutOfDomainAssessment,
    OutOfDomainAssessmentCreate,
    PredictionServiceConfig,
    PredictionServiceConfigCreate,
)
from .orm import (
    AuditEventORM,
    CalibrationAssessmentORM,
    DatasetVersionORM,
    DeploymentCandidateORM,
    ErrorAnalysisSliceORM,
    FeaturePipelineORM,
    MLEvaluationRunORM,
    MLTaskDefinitionORM,
    MLTrainingRunORM,
    ModelArtifactORM,
    ModelCardORM,
    ModelMetricORM,
    OutOfDomainAssessmentORM,
    PredictionServiceConfigORM,
    utcnow,
)


class MLModelFactoryError(ValueError):
    pass


class MLModelFactoryNotFoundError(MLModelFactoryError):
    pass


@dataclass(frozen=True)
class MLModelFactoryActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


_REVIEW_NOTE = (
    "ML model factory records are provenance and review artifacts; no model becomes active "
    "without an approved deployment candidate and explicit prediction service configuration."
)
_EXPERIMENTAL_WARNING = (
    "Dataset version is not approved; this can only create an experimental model and "
    "requires review before any deployment candidate approval."
)
_MISSING_LABEL_WARNING = (
    "No labeled evaluation rows were available; metrics require review before model "
    "claims are made."
)
_PRIVATE_KEY_MARKERS = (
    "password",
    "token",
    "secret",
    "api_key",
    "raw_spectrum",
    "raw_spectra",
    "raw_data",
    "source_text",
    "document_text",
    "full_text",
    "full_source",
    "smiles",
)


BUILTIN_ML_TASKS: tuple[dict[str, Any], ...] = (
    {
        "task_key": "nmr_shift_prediction_baseline",
        "name": "NMR shift prediction baseline",
        "domain": "nmr",
        "task_type": "regression",
        "description": "Baseline model for reviewed NMR shift prediction dataset versions.",
        "default_metric": "mae_ppm",
        "required_dataset_type": "nmr_prediction",
    },
    {
        "task_key": "nmr_candidate_ranking_baseline",
        "name": "NMR candidate ranking baseline",
        "domain": "nmr",
        "task_type": "ranking",
        "description": "Baseline model for reviewed NMR candidate ranking datasets.",
        "default_metric": "ndcg",
        "required_dataset_type": "nmr_structure_elucidation",
    },
    {
        "task_key": "msms_similarity_scorer",
        "name": "MS/MS similarity scorer",
        "domain": "ms",
        "task_type": "scoring",
        "description": "Reviewed-data baseline scorer for processed MS/MS similarity evidence.",
        "default_metric": "top1_accuracy",
        "required_dataset_type": "msms_annotation",
    },
    {
        "task_key": "lcms_feature_family_classifier",
        "name": "LCMS feature family classifier",
        "domain": "lcms",
        "task_type": "classification",
        "description": "Baseline classifier for reviewed LCMS feature family dataset versions.",
        "default_metric": "macro_f1",
        "required_dataset_type": "lcms_feature",
    },
    {
        "task_key": "reaction_surrogate_baseline",
        "name": "Reaction surrogate baseline",
        "domain": "reaction",
        "task_type": "regression",
        "description": "Baseline surrogate model for reviewed reaction optimization datasets.",
        "default_metric": "mae",
        "required_dataset_type": "reaction_optimization",
    },
    {
        "task_key": "regulatory_extraction_classifier",
        "name": "Regulatory extraction classifier",
        "domain": "regulatory",
        "task_type": "classification",
        "description": "Classifier baseline for reviewed regulatory extraction datasets.",
        "default_metric": "macro_f1",
        "required_dataset_type": "regulatory_extraction",
    },
    {
        "task_key": "regulatory_citation_support_classifier",
        "name": "Regulatory citation support classifier",
        "domain": "regulatory",
        "task_type": "classification",
        "description": "Classifier baseline for citation support review in regulatory datasets.",
        "default_metric": "citation_support_f1",
        "required_dataset_type": "regulatory_extraction",
    },
    {
        "task_key": "knowledge_record_quality_classifier",
        "name": "Knowledge record quality classifier",
        "domain": "multimodal",
        "task_type": "classification",
        "description": (
            "Quality classifier for reviewed knowledge records and data flywheel curation."
        ),
        "default_metric": "review_agreement",
        "required_dataset_type": "ai_governance",
    },
)


def _json_dump(value: Any, *, default: Any = None) -> str:
    return json.dumps(
        _public_json(default if value is None else value), sort_keys=True, separators=(",", ":")
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
    if isinstance(value, str) and len(value) > 1000:
        return value[:1000] + "...[truncated]"
    return value


def _audit(
    session: Session,
    *,
    actor: MLModelFactoryActor,
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


def ensure_builtin_ml_tasks(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as session:
        _ensure_builtin_ml_tasks(session)


def _ensure_builtin_ml_tasks(session: Session) -> None:
    existing = {task.task_key: task for task in session.scalars(select(MLTaskDefinitionORM)).all()}
    for task in BUILTIN_ML_TASKS:
        row = existing.get(task["task_key"])
        if row is None:
            session.add(
                MLTaskDefinitionORM(
                    task_key=task["task_key"],
                    name=task["name"],
                    domain=task["domain"],
                    task_type=task["task_type"],
                    description=task["description"],
                    default_metric=task["default_metric"],
                    required_dataset_type=task["required_dataset_type"],
                    status=task.get("status", "active"),
                    metadata_json=_json_dump(task.get("metadata_json", {})),
                )
            )
        else:
            row.name = task["name"]
            row.domain = task["domain"]
            row.task_type = task["task_type"]
            row.description = task["description"]
            row.default_metric = task["default_metric"]
            row.required_dataset_type = task["required_dataset_type"]
            row.updated_at = utcnow()


def create_task(
    session_factory: sessionmaker[Session],
    payload: MLTaskDefinitionCreate,
    *,
    actor: MLModelFactoryActor,
) -> MLTaskDefinition:
    with session_scope(session_factory) as session:
        row = MLTaskDefinitionORM(
            task_key=payload.task_key,
            name=payload.name,
            domain=payload.domain,
            task_type=payload.task_type,
            description=payload.description,
            default_metric=payload.default_metric,
            required_dataset_type=payload.required_dataset_type,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise MLModelFactoryError(
                "ML task definition already exists for this task_key."
            ) from exc
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.task.create",
            message="ML task definition created.",
            entity_type="ml_task_definition",
            entity_id=row.id,
            metadata={"task_key": row.task_key, "status": row.status},
        )
        return _task_to_record(row)


def list_tasks(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    limit: int = 500,
) -> list[MLTaskDefinition]:
    with session_scope(session_factory) as session:
        _ensure_builtin_ml_tasks(session)
        stmt = select(MLTaskDefinitionORM).order_by(MLTaskDefinitionORM.task_key.asc()).limit(limit)
        if status is not None:
            stmt = stmt.where(MLTaskDefinitionORM.status == status)
        return [_task_to_record(row) for row in session.scalars(stmt).all()]


def create_feature_pipeline(
    session_factory: sessionmaker[Session],
    payload: FeaturePipelineCreate,
    *,
    actor: MLModelFactoryActor,
) -> FeaturePipeline:
    with session_scope(session_factory) as session:
        _require_task(session, payload.task_key)
        row = FeaturePipelineORM(
            name=payload.name,
            version=payload.version,
            task_key=payload.task_key,
            input_schema_json=_json_dump(payload.input_schema_json),
            output_schema_json=_json_dump(payload.output_schema_json),
            feature_steps_json=_json_dump(payload.feature_steps_json),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise MLModelFactoryError(
                "Feature pipeline already exists for this task, name, and version."
            ) from exc
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.feature_pipeline.create",
            message="Feature pipeline created for ML model factory.",
            entity_type="feature_pipeline",
            entity_id=row.id,
            metadata={"task_key": row.task_key, "status": row.status},
        )
        return _feature_pipeline_to_record(row)


def list_feature_pipelines(
    session_factory: sessionmaker[Session],
    *,
    task_key: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[FeaturePipeline]:
    with session_scope(session_factory) as session:
        stmt = select(FeaturePipelineORM).order_by(FeaturePipelineORM.id.desc()).limit(limit)
        if task_key is not None:
            stmt = stmt.where(FeaturePipelineORM.task_key == task_key)
        if status is not None:
            stmt = stmt.where(FeaturePipelineORM.status == status)
        return [_feature_pipeline_to_record(row) for row in session.scalars(stmt).all()]


def get_feature_pipeline(
    session_factory: sessionmaker[Session], pipeline_id: int
) -> FeaturePipeline | None:
    with session_scope(session_factory) as session:
        row = session.get(FeaturePipelineORM, pipeline_id)
        return _feature_pipeline_to_record(row) if row is not None else None


def create_training_run(
    session_factory: sessionmaker[Session],
    payload: MLTrainingRunCreate,
    *,
    actor: MLModelFactoryActor,
) -> MLTrainingRunResponse:
    with session_scope(session_factory) as session:
        _ensure_builtin_ml_tasks(session)
        if payload.dataset_version_id is None:
            _audit(
                session,
                actor=actor,
                event_type="ml_factory.training_run.reject",
                message="ML training run rejected because dataset_version_id was missing.",
                entity_type="ml_training_run",
                metadata={"task_key": payload.task_key},
            )
            raise MLModelFactoryError("dataset_version_id is required for ML training runs.")
        task = _require_task(session, payload.task_key)
        dataset = session.get(DatasetVersionORM, payload.dataset_version_id)
        if dataset is None:
            _audit(
                session,
                actor=actor,
                event_type="ml_factory.training_run.reject",
                message="ML training run rejected because dataset version was not found.",
                entity_type="ml_training_run",
                metadata={
                    "task_key": payload.task_key,
                    "dataset_version_id": payload.dataset_version_id,
                },
            )
            raise MLModelFactoryNotFoundError("Dataset version not found.")
        if payload.feature_pipeline_id is not None:
            pipeline = session.get(FeaturePipelineORM, payload.feature_pipeline_id)
            if pipeline is None:
                raise MLModelFactoryNotFoundError("Feature pipeline not found.")
            if pipeline.task_key != payload.task_key:
                raise MLModelFactoryError(
                    "Feature pipeline task_key does not match training task_key."
                )

        now = utcnow()
        warnings = (
            list(payload.metadata_json.get("warnings", []))
            if isinstance(payload.metadata_json.get("warnings"), list)
            else []
        )
        notes = list(payload.notes_json)
        metadata = dict(payload.metadata_json)
        parameters = _public_json(payload.parameters_json)
        metrics = _training_metrics_for_dataset(dataset, task, payload.model_family, warnings)
        status = "succeeded"
        artifact: ModelArtifactORM | None = None

        if dataset.dataset_type != task.required_dataset_type:
            warnings.append(
                "Dataset version type does not match task required_dataset_type; "
                "requires review before model use."
            )
        if dataset.status != "approved":
            warnings.append(_EXPERIMENTAL_WARNING)
            metadata["experimental"] = True
            if not payload.experimental:
                status = "failed"
                notes.append("Training failed because the dataset version is not approved.")
        if payload.experimental:
            metadata["experimental"] = True
            notes.append("Experimental model training was explicitly requested.")
        if payload.model_family in {"graph_neural_network", "transformer", "external"}:
            status = "requires_review"
            warnings.append(
                "Requested model family is registered as planned or external; "
                "no training was performed."
            )
            notes.append(
                "Use a reviewed external artifact registration flow before deployment "
                "candidate review."
            )

        row = MLTrainingRunORM(
            task_key=payload.task_key,
            dataset_version_id=payload.dataset_version_id,
            feature_pipeline_id=payload.feature_pipeline_id,
            model_family=payload.model_family,
            model_name=payload.model_name,
            model_version=payload.model_version,
            status=status,
            parameters_json=_json_dump(parameters),
            training_metrics_json=_json_dump(metrics),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(notes or [_REVIEW_NOTE]),
            started_at=now,
            finished_at=now,
            metadata_json=_json_dump(metadata),
        )
        session.add(row)
        session.flush()
        if status == "succeeded":
            model_hash = _model_hash(
                {
                    "training_run_id": row.id,
                    "task_key": row.task_key,
                    "dataset_version_id": row.dataset_version_id,
                    "model_family": row.model_family,
                    "model_name": row.model_name,
                    "model_version": row.model_version,
                    "metrics": metrics,
                    "experimental": bool(metadata.get("experimental")),
                }
            )
            artifact = ModelArtifactORM(
                training_run_id=row.id,
                model_name=row.model_name,
                model_version=row.model_version,
                model_family=row.model_family,
                artifact_uri=None,
                artifact_sha256=None,
                model_hash=model_hash,
                task_key=row.task_key,
                status="trained",
                metadata_json=_json_dump(
                    {
                        "dataset_version_id": row.dataset_version_id,
                        "dataset_version_status": dataset.status,
                        "experimental": bool(metadata.get("experimental")),
                        "human_review_required": True,
                    }
                ),
            )
            session.add(artifact)
            session.flush()
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.training_run.create",
            message="ML training run created and recorded.",
            entity_type="ml_training_run",
            entity_id=row.id,
            metadata={
                "task_key": row.task_key,
                "status": row.status,
                "model_artifact_id": artifact.id if artifact is not None else None,
                "dataset_version_id": row.dataset_version_id,
            },
        )
        return _training_response(row, artifact_id=artifact.id if artifact is not None else None)


def list_training_runs(
    session_factory: sessionmaker[Session],
    *,
    task_key: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[MLTrainingRun]:
    with session_scope(session_factory) as session:
        stmt = select(MLTrainingRunORM).order_by(MLTrainingRunORM.id.desc()).limit(limit)
        if task_key is not None:
            stmt = stmt.where(MLTrainingRunORM.task_key == task_key)
        if status is not None:
            stmt = stmt.where(MLTrainingRunORM.status == status)
        return [_training_to_record(row, session) for row in session.scalars(stmt).all()]


def get_training_run(
    session_factory: sessionmaker[Session], training_run_id: int
) -> MLTrainingRunResponse | None:
    with session_scope(session_factory) as session:
        row = session.get(MLTrainingRunORM, training_run_id)
        if row is None:
            return None
        artifact_id = _artifact_id_for_training_run(session, row.id)
        return _training_response(row, artifact_id=artifact_id)


def cancel_training_run(
    session_factory: sessionmaker[Session],
    training_run_id: int,
    *,
    actor: MLModelFactoryActor,
) -> MLTrainingRunResponse | None:
    with session_scope(session_factory) as session:
        row = session.get(MLTrainingRunORM, training_run_id)
        if row is None:
            return None
        if row.status in {"queued", "running", "requires_review"}:
            row.status = "canceled"
            row.finished_at = utcnow()
        else:
            warnings = _json_list(row.warnings_json)
            warnings.append("Training run was already terminal when cancel was requested.")
            row.warnings_json = _json_dump(warnings)
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.training_run.cancel",
            message="ML training run cancel requested.",
            entity_type="ml_training_run",
            entity_id=row.id,
            metadata={"status": row.status},
        )
        return _training_response(row, artifact_id=_artifact_id_for_training_run(session, row.id))


def create_evaluation_run(
    session_factory: sessionmaker[Session],
    payload: MLEvaluationRunCreate,
    *,
    actor: MLModelFactoryActor,
) -> MLEvaluationRunResponse:
    with session_scope(session_factory) as session:
        training = _optional_training_run(session, payload.training_run_id)
        artifact = _optional_model_artifact(session, payload.model_artifact_id)
        if artifact is None and training is not None:
            artifact = _artifact_for_training_run(session, training.id)
        dataset_id = payload.dataset_version_id or (
            training.dataset_version_id if training is not None else None
        )
        dataset = _optional_dataset_version(session, dataset_id)
        metrics = dict(_public_json(payload.metrics_json))
        warnings = list(payload.warnings_json)
        notes = list(payload.notes_json)
        status = payload.status
        if not metrics:
            computed = _evaluation_metrics_for_dataset(dataset, warnings)
            metrics.update(computed)
        if not metrics:
            status = "requires_review"
            if _MISSING_LABEL_WARNING not in warnings:
                warnings.append(_MISSING_LABEL_WARNING)
        elif status in {"queued", "running"}:
            status = "succeeded"
        if status == "requires_review" and not notes:
            notes.append("Evaluation run requires review before model claims are made.")

        now = utcnow()
        row = MLEvaluationRunORM(
            training_run_id=training.id if training is not None else None,
            model_artifact_id=artifact.id if artifact is not None else None,
            benchmark_dataset_id=payload.benchmark_dataset_id,
            dataset_version_id=dataset.id if dataset is not None else dataset_id,
            status=status,
            metrics_json=_json_dump(metrics),
            slice_metrics_json=_json_dump(payload.slice_metrics_json),
            confusion_summary_json=_json_dump(payload.confusion_summary_json)
            if payload.confusion_summary_json is not None
            else None,
            calibration_summary_json=_json_dump(payload.calibration_summary_json)
            if payload.calibration_summary_json is not None
            else None,
            error_examples_json=_json_dump(payload.error_examples_json),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(notes or [_REVIEW_NOTE]),
            started_at=now,
            finished_at=now,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _create_metric_rows(session, row.id, metrics)
        if artifact is not None and status == "succeeded" and artifact.status == "trained":
            artifact.status = "evaluated"
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.evaluation_run.create",
            message="ML evaluation run created and stored.",
            entity_type="ml_evaluation_run",
            entity_id=row.id,
            metadata={
                "status": row.status,
                "model_artifact_id": row.model_artifact_id,
                "dataset_version_id": row.dataset_version_id,
            },
        )
        return _evaluation_response(row)


def list_evaluation_runs(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    limit: int = 500,
) -> list[MLEvaluationRun]:
    with session_scope(session_factory) as session:
        stmt = select(MLEvaluationRunORM).order_by(MLEvaluationRunORM.id.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(MLEvaluationRunORM.status == status)
        return [_evaluation_to_record(row, session) for row in session.scalars(stmt).all()]


def get_evaluation_run(
    session_factory: sessionmaker[Session], evaluation_run_id: int
) -> MLEvaluationRunResponse | None:
    with session_scope(session_factory) as session:
        row = session.get(MLEvaluationRunORM, evaluation_run_id)
        return _evaluation_response(row) if row is not None else None


def list_model_artifacts(
    session_factory: sessionmaker[Session],
    *,
    task_key: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[ModelArtifact]:
    with session_scope(session_factory) as session:
        stmt = select(ModelArtifactORM).order_by(ModelArtifactORM.id.desc()).limit(limit)
        if task_key is not None:
            stmt = stmt.where(ModelArtifactORM.task_key == task_key)
        if status is not None:
            stmt = stmt.where(ModelArtifactORM.status == status)
        return [_artifact_to_record(row) for row in session.scalars(stmt).all()]


def get_model_artifact(
    session_factory: sessionmaker[Session], model_artifact_id: int
) -> ModelArtifact | None:
    with session_scope(session_factory) as session:
        row = session.get(ModelArtifactORM, model_artifact_id)
        return _artifact_to_record(row) if row is not None else None


def create_model_card(
    session_factory: sessionmaker[Session],
    payload: ModelCardCreate,
    *,
    actor: MLModelFactoryActor,
) -> ModelCard:
    with session_scope(session_factory) as session:
        artifact = _require_model_artifact(session, payload.model_artifact_id)
        if artifact.task_key != payload.task_key:
            raise MLModelFactoryError("Model card task_key must match the model artifact task_key.")
        row = ModelCardORM(
            model_artifact_id=payload.model_artifact_id,
            task_key=payload.task_key,
            intended_use=payload.intended_use,
            limitations=payload.limitations,
            training_data_summary_json=_json_dump(payload.training_data_summary_json),
            evaluation_summary_json=_json_dump(payload.evaluation_summary_json),
            bias_risk_summary_json=_json_dump(payload.bias_risk_summary_json),
            out_of_domain_summary_json=_json_dump(payload.out_of_domain_summary_json),
            calibration_summary_json=_json_dump(payload.calibration_summary_json),
            human_review_summary_json=_json_dump(payload.human_review_summary_json),
            approval_status=payload.approval_status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.model_card.create",
            message="Model card created for ML model artifact.",
            entity_type="model_card",
            entity_id=row.id,
            metadata={
                "model_artifact_id": row.model_artifact_id,
                "approval_status": row.approval_status,
            },
        )
        return _model_card_to_record(row)


def list_model_cards(
    session_factory: sessionmaker[Session],
    *,
    model_artifact_id: int | None = None,
    limit: int = 500,
) -> list[ModelCard]:
    with session_scope(session_factory) as session:
        stmt = select(ModelCardORM).order_by(ModelCardORM.id.desc()).limit(limit)
        if model_artifact_id is not None:
            stmt = stmt.where(ModelCardORM.model_artifact_id == model_artifact_id)
        return [_model_card_to_record(row) for row in session.scalars(stmt).all()]


def get_model_card(session_factory: sessionmaker[Session], model_card_id: int) -> ModelCard | None:
    with session_scope(session_factory) as session:
        row = session.get(ModelCardORM, model_card_id)
        return _model_card_to_record(row) if row is not None else None


def update_model_card(
    session_factory: sessionmaker[Session],
    model_card_id: int,
    payload: ModelCardUpdate,
    *,
    actor: MLModelFactoryActor,
) -> ModelCard | None:
    with session_scope(session_factory) as session:
        row = session.get(ModelCardORM, model_card_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in ("intended_use", "limitations", "approval_status"):
            if field in update:
                setattr(row, field, update[field])
        for field in (
            "training_data_summary_json",
            "evaluation_summary_json",
            "bias_risk_summary_json",
            "out_of_domain_summary_json",
            "calibration_summary_json",
            "human_review_summary_json",
            "metadata_json",
        ):
            if field in update:
                setattr(row, field, _json_dump(update[field]))
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.model_card.update",
            message="Model card updated.",
            entity_type="model_card",
            entity_id=row.id,
            metadata={"approval_status": row.approval_status},
        )
        return _model_card_to_record(row)


def create_calibration_assessment(
    session_factory: sessionmaker[Session],
    payload: CalibrationAssessmentCreate,
    *,
    actor: MLModelFactoryActor,
) -> CalibrationAssessment:
    with session_scope(session_factory) as session:
        _require_model_artifact(session, payload.model_artifact_id)
        _optional_evaluation_run(session, payload.evaluation_run_id)
        row = CalibrationAssessmentORM(
            model_artifact_id=payload.model_artifact_id,
            evaluation_run_id=payload.evaluation_run_id,
            calibration_method=payload.calibration_method,
            calibration_metrics_json=_json_dump(payload.calibration_metrics_json),
            status=payload.status,
            warnings_json=_json_dump(payload.warnings_json),
            notes_json=_json_dump(payload.notes_json),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.calibration.create",
            message="Calibration assessment created.",
            entity_type="calibration_assessment",
            entity_id=row.id,
            metadata={"model_artifact_id": row.model_artifact_id, "status": row.status},
        )
        return _calibration_to_record(row)


def list_calibration_assessments(
    session_factory: sessionmaker[Session], *, limit: int = 500
) -> list[CalibrationAssessment]:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(CalibrationAssessmentORM)
            .order_by(CalibrationAssessmentORM.id.desc())
            .limit(limit)
        ).all()
        return [_calibration_to_record(row) for row in rows]


def get_calibration_assessment(
    session_factory: sessionmaker[Session], assessment_id: int
) -> CalibrationAssessment | None:
    with session_scope(session_factory) as session:
        row = session.get(CalibrationAssessmentORM, assessment_id)
        return _calibration_to_record(row) if row is not None else None


def create_error_analysis(
    session_factory: sessionmaker[Session],
    payload: ErrorAnalysisSliceCreate,
    *,
    actor: MLModelFactoryActor,
) -> ErrorAnalysisSlice:
    with session_scope(session_factory) as session:
        _require_evaluation_run(session, payload.evaluation_run_id)
        representative_errors = _public_json(payload.representative_errors_json)
        row = ErrorAnalysisSliceORM(
            evaluation_run_id=payload.evaluation_run_id,
            slice_name=payload.slice_name,
            slice_type=payload.slice_type,
            sample_count=payload.sample_count,
            metrics_json=_json_dump(payload.metrics_json),
            representative_errors_json=_json_dump(representative_errors),
            severity=payload.severity,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.error_analysis.create",
            message="Error analysis slice created.",
            entity_type="error_analysis_slice",
            entity_id=row.id,
            metadata={"evaluation_run_id": row.evaluation_run_id, "severity": row.severity},
        )
        return _error_slice_to_record(row)


def list_error_analysis(
    session_factory: sessionmaker[Session], *, limit: int = 500
) -> list[ErrorAnalysisSlice]:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(ErrorAnalysisSliceORM).order_by(ErrorAnalysisSliceORM.id.desc()).limit(limit)
        ).all()
        return [_error_slice_to_record(row) for row in rows]


def get_error_analysis(
    session_factory: sessionmaker[Session], error_analysis_id: int
) -> ErrorAnalysisSlice | None:
    with session_scope(session_factory) as session:
        row = session.get(ErrorAnalysisSliceORM, error_analysis_id)
        return _error_slice_to_record(row) if row is not None else None


def create_ood_assessment(
    session_factory: sessionmaker[Session],
    payload: OutOfDomainAssessmentCreate,
    *,
    actor: MLModelFactoryActor,
) -> OutOfDomainAssessment:
    with session_scope(session_factory) as session:
        _require_model_artifact(session, payload.model_artifact_id)
        _optional_dataset_version(session, payload.dataset_version_id)
        row = OutOfDomainAssessmentORM(
            model_artifact_id=payload.model_artifact_id,
            dataset_version_id=payload.dataset_version_id,
            method=payload.method,
            ood_summary_json=_json_dump(payload.ood_summary_json),
            high_risk_regions_json=_json_dump(payload.high_risk_regions_json),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.ood.create",
            message="Out-of-domain assessment created.",
            entity_type="out_of_domain_assessment",
            entity_id=row.id,
            metadata={"model_artifact_id": row.model_artifact_id, "status": row.status},
        )
        return _ood_to_record(row)


def list_ood_assessments(
    session_factory: sessionmaker[Session], *, limit: int = 500
) -> list[OutOfDomainAssessment]:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(OutOfDomainAssessmentORM)
            .order_by(OutOfDomainAssessmentORM.id.desc())
            .limit(limit)
        ).all()
        return [_ood_to_record(row) for row in rows]


def get_ood_assessment(
    session_factory: sessionmaker[Session], ood_assessment_id: int
) -> OutOfDomainAssessment | None:
    with session_scope(session_factory) as session:
        row = session.get(OutOfDomainAssessmentORM, ood_assessment_id)
        return _ood_to_record(row) if row is not None else None


def create_deployment_candidate(
    session_factory: sessionmaker[Session],
    payload: DeploymentCandidateCreate,
    *,
    actor: MLModelFactoryActor,
) -> DeploymentCandidateResponse:
    with session_scope(session_factory) as session:
        artifact = _require_model_artifact(session, payload.model_artifact_id)
        if payload.status in {"approved_for_internal_use", "approved_for_production", "rejected"}:
            raise MLModelFactoryError(
                "Use the deployment candidate review endpoints for approval or rejection."
            )
        if payload.model_card_id is None:
            raise MLModelFactoryError(
                "Model card is required before creating a deployment candidate."
            )
        card = session.get(ModelCardORM, payload.model_card_id)
        if card is None:
            raise MLModelFactoryNotFoundError("Model card not found.")
        if card.model_artifact_id != artifact.id:
            raise MLModelFactoryError("Model card must belong to the requested model artifact.")
        row = DeploymentCandidateORM(
            model_artifact_id=payload.model_artifact_id,
            model_card_id=payload.model_card_id,
            target_module=payload.target_module,
            target_endpoint=payload.target_endpoint,
            status=payload.status,
            metadata_json=_json_dump(
                {
                    **payload.metadata_json,
                    "human_review_required": True,
                    "model_card_approval_status": card.approval_status,
                }
            ),
        )
        session.add(row)
        artifact.status = "deployment_candidate"
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.deployment_candidate.create",
            message="Deployment candidate created; human approval remains required.",
            entity_type="deployment_candidate",
            entity_id=row.id,
            metadata={
                "model_artifact_id": row.model_artifact_id,
                "target_module": row.target_module,
            },
        )
        return _deployment_response(row)


def list_deployment_candidates(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    limit: int = 500,
) -> list[DeploymentCandidate]:
    with session_scope(session_factory) as session:
        stmt = (
            select(DeploymentCandidateORM).order_by(DeploymentCandidateORM.id.desc()).limit(limit)
        )
        if status is not None:
            stmt = stmt.where(DeploymentCandidateORM.status == status)
        return [_deployment_to_record(row) for row in session.scalars(stmt).all()]


def get_deployment_candidate(
    session_factory: sessionmaker[Session], candidate_id: int
) -> DeploymentCandidateResponse | None:
    with session_scope(session_factory) as session:
        row = session.get(DeploymentCandidateORM, candidate_id)
        return _deployment_response(row) if row is not None else None


def approve_deployment_candidate(
    session_factory: sessionmaker[Session],
    candidate_id: int,
    payload: DeploymentCandidateApprovalRequest,
    *,
    actor: MLModelFactoryActor,
) -> DeploymentCandidateResponse | None:
    with session_scope(session_factory) as session:
        row = session.get(DeploymentCandidateORM, candidate_id)
        if row is None:
            return None
        artifact = _require_model_artifact(session, row.model_artifact_id)
        if not _has_succeeded_evaluation(session, artifact.id):
            raise MLModelFactoryError(
                "Deployment candidate approval requires a succeeded evaluation run."
            )
        row.status = payload.status
        row.reviewer_name = payload.reviewer_name
        row.reviewer_comment = payload.reviewer_comment
        row.updated_at = utcnow()
        row.metadata_json = _json_dump(
            {
                **_json_dict(row.metadata_json),
                **payload.metadata_json,
                "human_approval_recorded": True,
            }
        )
        artifact.status = "approved"
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.deployment_candidate.approve",
            message="Deployment candidate approved by human reviewer.",
            entity_type="deployment_candidate",
            entity_id=row.id,
            metadata={"status": row.status, "reviewer_name": row.reviewer_name},
        )
        return _deployment_response(row)


def reject_deployment_candidate(
    session_factory: sessionmaker[Session],
    candidate_id: int,
    payload: DeploymentCandidateRejectRequest,
    *,
    actor: MLModelFactoryActor,
) -> DeploymentCandidateResponse | None:
    with session_scope(session_factory) as session:
        row = session.get(DeploymentCandidateORM, candidate_id)
        if row is None:
            return None
        artifact = _require_model_artifact(session, row.model_artifact_id)
        row.status = "rejected"
        row.reviewer_name = payload.reviewer_name
        row.reviewer_comment = payload.reviewer_comment
        row.updated_at = utcnow()
        row.metadata_json = _json_dump(
            {
                **_json_dict(row.metadata_json),
                **payload.metadata_json,
                "human_rejection_recorded": True,
            }
        )
        artifact.status = "rejected"
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.deployment_candidate.reject",
            message="Deployment candidate rejected by human reviewer.",
            entity_type="deployment_candidate",
            entity_id=row.id,
            metadata={"reviewer_name": row.reviewer_name},
        )
        return _deployment_response(row)


def create_prediction_service_config(
    session_factory: sessionmaker[Session],
    payload: PredictionServiceConfigCreate,
    *,
    actor: MLModelFactoryActor,
) -> PredictionServiceConfig:
    with session_scope(session_factory) as session:
        _optional_model_artifact(session, payload.active_model_artifact_id)
        _optional_model_artifact(session, payload.fallback_model_artifact_id)
        if payload.status == "active" and payload.active_model_artifact_id is not None:
            if not _has_approved_candidate(session, payload.active_model_artifact_id):
                raise MLModelFactoryError(
                    "Active prediction service configs require an approved deployment candidate."
                )
        row = PredictionServiceConfigORM(
            service_key=payload.service_key,
            target_module=payload.target_module,
            active_model_artifact_id=payload.active_model_artifact_id,
            fallback_model_artifact_id=payload.fallback_model_artifact_id,
            routing_rules_json=_json_dump(payload.routing_rules_json),
            confidence_thresholds_json=_json_dump(payload.confidence_thresholds_json),
            ood_rules_json=_json_dump(payload.ood_rules_json),
            fallback_rules_json=_json_dump(payload.fallback_rules_json),
            human_review_rules_json=_json_dump(payload.human_review_rules_json),
            max_batch_size=payload.max_batch_size,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="ml_factory.prediction_config.create",
            message="Prediction service config created.",
            entity_type="prediction_service_config",
            entity_id=row.id,
            metadata={"target_module": row.target_module, "status": row.status},
        )
        return _prediction_config_to_record(row)


def list_prediction_service_configs(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    limit: int = 500,
) -> list[PredictionServiceConfig]:
    with session_scope(session_factory) as session:
        stmt = (
            select(PredictionServiceConfigORM)
            .order_by(PredictionServiceConfigORM.id.desc())
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(PredictionServiceConfigORM.status == status)
        return [_prediction_config_to_record(row) for row in session.scalars(stmt).all()]


def model_health(session_factory: sessionmaker[Session]) -> MLModelHealthSummary:
    with session_scope(session_factory) as session:
        _ensure_builtin_ml_tasks(session)
        latest_training = session.scalars(
            select(MLTrainingRunORM).order_by(MLTrainingRunORM.id.desc()).limit(5)
        ).all()
        latest_eval = session.scalars(
            select(MLEvaluationRunORM).order_by(MLEvaluationRunORM.id.desc()).limit(5)
        ).all()
        artifacts = session.scalars(select(ModelArtifactORM)).all()
        active_model_count = _count_where(
            session, PredictionServiceConfigORM.id, PredictionServiceConfigORM.status == "active"
        )
        return MLModelHealthSummary(
            task_count=_count(session, MLTaskDefinitionORM.id),
            active_task_count=_count_where(
                session, MLTaskDefinitionORM.id, MLTaskDefinitionORM.status == "active"
            ),
            experimental_task_count=_count_where(
                session, MLTaskDefinitionORM.id, MLTaskDefinitionORM.status == "experimental"
            ),
            feature_pipeline_count=_count(session, FeaturePipelineORM.id),
            training_run_count=_count(session, MLTrainingRunORM.id),
            evaluation_run_count=_count(session, MLEvaluationRunORM.id),
            model_artifact_count=_count(session, ModelArtifactORM.id),
            active_model_count=active_model_count,
            experimental_model_count=sum(
                1
                for artifact in artifacts
                if bool(_json_dict(artifact.metadata_json).get("experimental"))
            ),
            trained_model_count=_count_where(
                session, ModelArtifactORM.id, ModelArtifactORM.status == "trained"
            ),
            evaluated_model_count=_count_where(
                session, ModelArtifactORM.id, ModelArtifactORM.status == "evaluated"
            ),
            deployment_candidate_count=_count(session, DeploymentCandidateORM.id),
            approved_deployment_candidate_count=_count_where(
                session,
                DeploymentCandidateORM.id,
                DeploymentCandidateORM.status.in_(
                    ["approved_for_internal_use", "approved_for_production"]
                ),
            ),
            deprecated_model_count=_count_where(
                session, ModelArtifactORM.id, ModelArtifactORM.status == "deprecated"
            ),
            active_prediction_config_count=active_model_count,
            latest_training_runs=[
                _training_response(row, artifact_id=_artifact_id_for_training_run(session, row.id))
                for row in latest_training
            ],
            latest_evaluation_runs=[_evaluation_response(row) for row in latest_eval],
            notes=[_REVIEW_NOTE],
            metadata_json={"builtin_ml_task_count": len(BUILTIN_ML_TASKS)},
        )


def _count(session: Session, column: Any) -> int:
    return int(session.scalar(select(func.count(column))) or 0)


def _count_where(session: Session, column: Any, criterion: Any) -> int:
    return int(session.scalar(select(func.count(column)).where(criterion)) or 0)


def _require_task(session: Session, task_key: str) -> MLTaskDefinitionORM:
    row = session.scalar(
        select(MLTaskDefinitionORM).where(MLTaskDefinitionORM.task_key == task_key)
    )
    if row is None:
        raise MLModelFactoryNotFoundError("ML task definition not found.")
    if row.status == "disabled":
        raise MLModelFactoryError("ML task definition is disabled.")
    return row


def _require_model_artifact(session: Session, artifact_id: int) -> ModelArtifactORM:
    row = session.get(ModelArtifactORM, artifact_id)
    if row is None:
        raise MLModelFactoryNotFoundError("Model artifact not found.")
    return row


def _require_evaluation_run(session: Session, evaluation_run_id: int) -> MLEvaluationRunORM:
    row = session.get(MLEvaluationRunORM, evaluation_run_id)
    if row is None:
        raise MLModelFactoryNotFoundError("Evaluation run not found.")
    return row


def _optional_training_run(
    session: Session, training_run_id: int | None
) -> MLTrainingRunORM | None:
    if training_run_id is None:
        return None
    row = session.get(MLTrainingRunORM, training_run_id)
    if row is None:
        raise MLModelFactoryNotFoundError("Training run not found.")
    return row


def _optional_evaluation_run(
    session: Session, evaluation_run_id: int | None
) -> MLEvaluationRunORM | None:
    if evaluation_run_id is None:
        return None
    return _require_evaluation_run(session, evaluation_run_id)


def _optional_model_artifact(session: Session, artifact_id: int | None) -> ModelArtifactORM | None:
    if artifact_id is None:
        return None
    return _require_model_artifact(session, artifact_id)


def _optional_dataset_version(
    session: Session, dataset_version_id: int | None
) -> DatasetVersionORM | None:
    if dataset_version_id is None:
        return None
    row = session.get(DatasetVersionORM, dataset_version_id)
    if row is None:
        raise MLModelFactoryNotFoundError("Dataset version not found.")
    return row


def _artifact_id_for_training_run(session: Session, training_run_id: int) -> int | None:
    return session.scalar(
        select(ModelArtifactORM.id)
        .where(ModelArtifactORM.training_run_id == training_run_id)
        .order_by(ModelArtifactORM.id.desc())
        .limit(1)
    )


def _artifact_for_training_run(session: Session, training_run_id: int) -> ModelArtifactORM | None:
    return session.scalar(
        select(ModelArtifactORM)
        .where(ModelArtifactORM.training_run_id == training_run_id)
        .order_by(ModelArtifactORM.id.desc())
        .limit(1)
    )


def _has_succeeded_evaluation(session: Session, artifact_id: int) -> bool:
    return bool(
        session.scalar(
            select(MLEvaluationRunORM.id)
            .where(
                MLEvaluationRunORM.model_artifact_id == artifact_id,
                MLEvaluationRunORM.status == "succeeded",
            )
            .limit(1)
        )
    )


def _has_approved_candidate(session: Session, artifact_id: int) -> bool:
    return bool(
        session.scalar(
            select(DeploymentCandidateORM.id)
            .where(
                DeploymentCandidateORM.model_artifact_id == artifact_id,
                DeploymentCandidateORM.status.in_(
                    ["approved_for_internal_use", "approved_for_production"]
                ),
            )
            .limit(1)
        )
    )


def _training_metrics_for_dataset(
    dataset: DatasetVersionORM,
    task: MLTaskDefinitionORM,
    model_family: str,
    warnings: list[str],
) -> dict[str, Any]:
    examples = _dataset_examples(dataset)
    labels = _labels_from_examples(examples)
    source_records = _json_list(dataset.source_record_ids_json)
    metrics: dict[str, Any] = {
        "dataset_version_id": dataset.id,
        "dataset_version_status": dataset.status,
        "evaluated_on_dataset_version": dataset.version,
        "source_record_count": len(source_records),
        "example_count": len(examples),
        "labeled_example_count": len(labels),
        "model_family": model_family,
        "default_metric": task.default_metric,
        "sklearn_available": importlib.util.find_spec("sklearn") is not None,
    }
    if labels:
        if task.task_type == "regression" and all(_is_number(label) for label in labels):
            numeric_labels = [float(label) for label in labels]
            mean_value = sum(numeric_labels) / len(numeric_labels)
            metrics["baseline_prediction_mean"] = mean_value
            metrics["baseline_mae"] = sum(
                abs(value - mean_value) for value in numeric_labels
            ) / len(numeric_labels)
        else:
            counts = Counter(str(label) for label in labels)
            majority_count = counts.most_common(1)[0][1]
            metrics["baseline_majority_fraction"] = majority_count / len(labels)
            metrics["class_count"] = len(counts)
    else:
        warnings.append(
            "Training dataset version did not include label examples; "
            "baseline artifact requires review."
        )
    sklearn_metrics = _try_sklearn_training_metrics(
        examples, labels, task.task_type, model_family, warnings
    )
    metrics.update(sklearn_metrics)
    return _public_json(metrics)


def _evaluation_metrics_for_dataset(
    dataset: DatasetVersionORM | None,
    warnings: list[str],
) -> dict[str, Any]:
    if dataset is None:
        warnings.append("Evaluation run did not include a dataset version.")
        return {}
    examples = _dataset_examples(dataset)
    labels = _labels_from_examples(examples)
    if not labels:
        warnings.append(_MISSING_LABEL_WARNING)
        return {}
    metrics: dict[str, Any] = {
        "evaluated_on_dataset_version": dataset.version,
        "dataset_version_id": dataset.id,
        "labeled_example_count": len(labels),
    }
    if all(_is_number(label) for label in labels):
        numeric_labels = [float(label) for label in labels]
        mean_value = sum(numeric_labels) / len(numeric_labels)
        metrics["baseline_mae"] = sum(abs(value - mean_value) for value in numeric_labels) / len(
            numeric_labels
        )
    else:
        counts = Counter(str(label) for label in labels)
        metrics["baseline_majority_fraction"] = counts.most_common(1)[0][1] / len(labels)
        metrics["class_count"] = len(counts)
    warnings.append("Evaluation used label-only baseline summary; requires review.")
    return _public_json(metrics)


def _dataset_examples(dataset: DatasetVersionORM) -> list[dict[str, Any]]:
    for source in (
        _json_dict(dataset.metadata_json).get("examples_json"),
        _json_dict(dataset.metadata_json).get("training_examples_json"),
        _json_dict(dataset.quality_summary_json).get("examples_json"),
        _json_dict(dataset.quality_summary_json).get("examples"),
        _json_dict(dataset.split_json).get("examples_json"),
    ):
        if isinstance(source, list):
            return [item for item in source if isinstance(item, dict)]
    return []


def _labels_from_examples(examples: list[dict[str, Any]]) -> list[Any]:
    labels: list[Any] = []
    for example in examples:
        label = example.get("label", example.get("target", example.get("y")))
        if label is not None:
            labels.append(label)
    return labels


def _features_from_examples(examples: list[dict[str, Any]]) -> list[list[float]]:
    rows: list[list[float]] = []
    numeric_keys: list[str] | None = None
    for example in examples:
        features = example.get("features_json") or example.get("features") or {}
        if not isinstance(features, dict):
            rows.append([])
            continue
        if numeric_keys is None:
            numeric_keys = sorted(key for key, value in features.items() if _is_number(value))
        rows.append([float(features.get(key, 0.0)) for key in numeric_keys])
    return rows


def _try_sklearn_training_metrics(
    examples: list[dict[str, Any]],
    labels: list[Any],
    task_type: str,
    model_family: str,
    warnings: list[str],
) -> dict[str, Any]:
    if model_family not in {"linear", "random_forest", "gradient_boosting"}:
        return {}
    if importlib.util.find_spec("sklearn") is None:
        warnings.append("sklearn is unavailable; stored a baseline model summary instead.")
        return {}
    features = _features_from_examples(examples)
    if not features or not labels or any(not row for row in features):
        warnings.append(
            "sklearn baseline was skipped because numeric features or labels were missing."
        )
        return {}
    try:
        if task_type == "regression" and all(_is_number(label) for label in labels):
            if model_family == "random_forest":
                from sklearn.ensemble import RandomForestRegressor

                model = RandomForestRegressor(n_estimators=10, random_state=0)
            elif model_family == "gradient_boosting":
                from sklearn.ensemble import GradientBoostingRegressor

                model = GradientBoostingRegressor(random_state=0)
            else:
                from sklearn.linear_model import LinearRegression

                model = LinearRegression()
            y = [float(label) for label in labels]
            model.fit(features, y)
            predictions = [float(value) for value in model.predict(features)]
            mae = sum(abs(pred - truth) for pred, truth in zip(predictions, y, strict=False)) / len(
                y
            )
            return {"sklearn_training_mae": mae, "sklearn_baseline_family": model_family}
        if model_family == "random_forest":
            from sklearn.ensemble import RandomForestClassifier

            classifier = RandomForestClassifier(n_estimators=10, random_state=0)
        elif model_family == "gradient_boosting":
            from sklearn.ensemble import GradientBoostingClassifier

            classifier = GradientBoostingClassifier(random_state=0)
        else:
            from sklearn.linear_model import LogisticRegression

            classifier = LogisticRegression(max_iter=200)
        classifier.fit(features, [str(label) for label in labels])
        predictions = [str(value) for value in classifier.predict(features)]
        accuracy = sum(
            pred == str(label) for pred, label in zip(predictions, labels, strict=False)
        ) / len(labels)
        return {"sklearn_training_accuracy": accuracy, "sklearn_baseline_family": model_family}
    except Exception as exc:  # pragma: no cover - dependency behavior differs by environment
        warnings.append(f"sklearn baseline was skipped: {exc}")
        return {}


def _is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _model_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(_public_json(payload), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(normalized).hexdigest()


def _create_metric_rows(session: Session, evaluation_run_id: int, metrics: dict[str, Any]) -> None:
    for name, value in metrics.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        session.add(
            ModelMetricORM(
                evaluation_run_id=evaluation_run_id,
                metric_name=str(name)[:120],
                metric_value=float(value),
                split="unknown",
                metadata_json=_json_dump({}),
            )
        )


def _task_to_record(row: MLTaskDefinitionORM) -> MLTaskDefinition:
    return MLTaskDefinition(
        id=row.id,
        task_key=row.task_key,
        name=row.name,
        domain=row.domain,  # type: ignore[arg-type]
        task_type=row.task_type,  # type: ignore[arg-type]
        description=row.description,
        default_metric=row.default_metric,
        required_dataset_type=row.required_dataset_type,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _feature_pipeline_to_record(row: FeaturePipelineORM) -> FeaturePipeline:
    return FeaturePipeline(
        id=row.id,
        name=row.name,
        version=row.version,
        task_key=row.task_key,
        input_schema_json=_json_dict(row.input_schema_json),
        output_schema_json=_json_dict(row.output_schema_json),
        feature_steps_json=_json_list(row.feature_steps_json),
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _training_to_record(row: MLTrainingRunORM, session: Session) -> MLTrainingRun:
    return MLTrainingRun(
        id=row.id,
        task_key=row.task_key,
        dataset_version_id=row.dataset_version_id,
        feature_pipeline_id=row.feature_pipeline_id,
        model_family=row.model_family,  # type: ignore[arg-type]
        model_name=row.model_name,
        model_version=row.model_version,
        status=row.status,  # type: ignore[arg-type]
        parameters_json=_json_dict(row.parameters_json),
        training_metrics_json=_json_dict(row.training_metrics_json),
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_list(row.notes_json),
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        model_artifact_id=_artifact_id_for_training_run(session, row.id),
        human_review_required=True,
    )


def _training_response(row: MLTrainingRunORM, *, artifact_id: int | None) -> MLTrainingRunResponse:
    return MLTrainingRunResponse(
        training_run_id=row.id,
        task_key=row.task_key,
        dataset_version_id=row.dataset_version_id,
        status=row.status,  # type: ignore[arg-type]
        model_family=row.model_family,  # type: ignore[arg-type]
        model_artifact_id=artifact_id,
        metrics=_json_dict(row.training_metrics_json),
        warnings=[str(item) for item in _json_list(row.warnings_json)],
        notes=[str(item) for item in _json_list(row.notes_json)],
        human_review_required=True,
    )


def _evaluation_to_record(row: MLEvaluationRunORM, session: Session) -> MLEvaluationRun:
    metric_rows = session.scalars(
        select(ModelMetricORM)
        .where(ModelMetricORM.evaluation_run_id == row.id)
        .order_by(ModelMetricORM.id.asc())
    ).all()
    return MLEvaluationRun(
        id=row.id,
        training_run_id=row.training_run_id,
        model_artifact_id=row.model_artifact_id,
        benchmark_dataset_id=row.benchmark_dataset_id,
        dataset_version_id=row.dataset_version_id,
        status=row.status,  # type: ignore[arg-type]
        metrics_json=_json_dict(row.metrics_json),
        slice_metrics_json=_json_dict(row.slice_metrics_json),
        confusion_summary_json=_json_dict(row.confusion_summary_json)
        if row.confusion_summary_json is not None
        else None,
        calibration_summary_json=_json_dict(row.calibration_summary_json)
        if row.calibration_summary_json is not None
        else None,
        error_examples_json=_json_list(row.error_examples_json),
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_list(row.notes_json),
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
        metric_records=[_metric_to_record(metric) for metric in metric_rows],
    )


def _evaluation_response(row: MLEvaluationRunORM) -> MLEvaluationRunResponse:
    return MLEvaluationRunResponse(
        evaluation_run_id=row.id,
        status=row.status,  # type: ignore[arg-type]
        metrics=_json_dict(row.metrics_json),
        slice_metrics=_json_dict(row.slice_metrics_json),
        error_examples=_json_list(row.error_examples_json),
        calibration_summary=_json_dict(row.calibration_summary_json)
        if row.calibration_summary_json is not None
        else None,
        warnings=[str(item) for item in _json_list(row.warnings_json)],
        notes=[str(item) for item in _json_list(row.notes_json)],
    )


def _artifact_to_record(row: ModelArtifactORM) -> ModelArtifact:
    return ModelArtifact(
        id=row.id,
        training_run_id=row.training_run_id,
        model_name=row.model_name,
        model_version=row.model_version,
        model_family=row.model_family,  # type: ignore[arg-type]
        artifact_uri=row.artifact_uri,
        artifact_sha256=row.artifact_sha256,
        model_hash=row.model_hash,
        task_key=row.task_key,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _model_card_to_record(row: ModelCardORM) -> ModelCard:
    return ModelCard(
        id=row.id,
        model_artifact_id=row.model_artifact_id,
        task_key=row.task_key,
        intended_use=row.intended_use,
        limitations=row.limitations,
        training_data_summary_json=_json_dict(row.training_data_summary_json),
        evaluation_summary_json=_json_dict(row.evaluation_summary_json),
        bias_risk_summary_json=_json_dict(row.bias_risk_summary_json),
        out_of_domain_summary_json=_json_dict(row.out_of_domain_summary_json),
        calibration_summary_json=_json_dict(row.calibration_summary_json),
        human_review_summary_json=_json_dict(row.human_review_summary_json),
        approval_status=row.approval_status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _metric_to_record(row: ModelMetricORM) -> ModelMetric:
    return ModelMetric(
        id=row.id,
        evaluation_run_id=row.evaluation_run_id,
        metric_name=row.metric_name,
        metric_value=row.metric_value,
        metric_unit=row.metric_unit,
        split=row.split,  # type: ignore[arg-type]
        passed=row.passed,
        threshold=row.threshold,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _calibration_to_record(row: CalibrationAssessmentORM) -> CalibrationAssessment:
    return CalibrationAssessment(
        id=row.id,
        model_artifact_id=row.model_artifact_id,
        evaluation_run_id=row.evaluation_run_id,
        calibration_method=row.calibration_method,  # type: ignore[arg-type]
        calibration_metrics_json=_json_dict(row.calibration_metrics_json),
        status=row.status,  # type: ignore[arg-type]
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_list(row.notes_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _error_slice_to_record(row: ErrorAnalysisSliceORM) -> ErrorAnalysisSlice:
    return ErrorAnalysisSlice(
        id=row.id,
        evaluation_run_id=row.evaluation_run_id,
        slice_name=row.slice_name,
        slice_type=row.slice_type,  # type: ignore[arg-type]
        sample_count=row.sample_count,
        metrics_json=_json_dict(row.metrics_json),
        representative_errors_json=_json_list(row.representative_errors_json),
        severity=row.severity,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _ood_to_record(row: OutOfDomainAssessmentORM) -> OutOfDomainAssessment:
    return OutOfDomainAssessment(
        id=row.id,
        model_artifact_id=row.model_artifact_id,
        dataset_version_id=row.dataset_version_id,
        method=row.method,  # type: ignore[arg-type]
        ood_summary_json=_json_dict(row.ood_summary_json),
        high_risk_regions_json=_json_list(row.high_risk_regions_json),
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _deployment_to_record(row: DeploymentCandidateORM) -> DeploymentCandidate:
    response = _deployment_response(row)
    return DeploymentCandidate(
        id=row.id,
        model_artifact_id=row.model_artifact_id,
        model_card_id=row.model_card_id,
        target_module=row.target_module,  # type: ignore[arg-type]
        target_endpoint=row.target_endpoint,
        status=row.status,  # type: ignore[arg-type]
        reviewer_name=row.reviewer_name,
        reviewer_comment=row.reviewer_comment,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=response.warnings,
        notes=response.notes,
    )


def _deployment_response(row: DeploymentCandidateORM) -> DeploymentCandidateResponse:
    warnings: list[str] = []
    notes = [_REVIEW_NOTE]
    if row.status in {"proposed", "in_review"}:
        warnings.append("Deployment candidate requires review and human approval before any use.")
    return DeploymentCandidateResponse(
        candidate_id=row.id,
        model_artifact_id=row.model_artifact_id,
        target_module=row.target_module,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        reviewer_name=row.reviewer_name,
        warnings=warnings,
        notes=notes,
    )


def _prediction_config_to_record(row: PredictionServiceConfigORM) -> PredictionServiceConfig:
    return PredictionServiceConfig(
        id=row.id,
        service_key=row.service_key or row.target_module,
        target_module=row.target_module,  # type: ignore[arg-type]
        active_model_artifact_id=row.active_model_artifact_id,
        fallback_model_artifact_id=row.fallback_model_artifact_id,
        routing_rules_json=_json_dict(row.routing_rules_json),
        confidence_thresholds_json=_json_dict(row.confidence_thresholds_json),
        ood_rules_json=_json_dict(row.ood_rules_json),
        fallback_rules_json=_json_dict(row.fallback_rules_json),
        human_review_rules_json=_json_dict(row.human_review_rules_json),
        max_batch_size=row.max_batch_size,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )
