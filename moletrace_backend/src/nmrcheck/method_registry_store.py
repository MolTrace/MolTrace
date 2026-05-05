from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    BenchmarkDataset,
    BenchmarkDatasetCreate,
    DriftAlert,
    MethodComparisonRun,
    MethodComparisonRunCreate,
    MethodRegistryEntry,
    MethodRegistryEntryCreate,
    MethodRegistryEntryUpdate,
    ModelHealthSummary,
    ModelVersion,
    ModelVersionCreate,
    ModelVersionUpdate,
    ScoringProfile,
    ScoringProfileCreate,
    ScoringProfileUpdate,
    ThresholdProfile,
    ThresholdProfileCreate,
    ThresholdProfileUpdate,
    ValidationMetric,
    ValidationRun,
    ValidationRunCreate,
)
from .orm import (
    AuditEventORM,
    BenchmarkDatasetORM,
    DriftAlertORM,
    MethodComparisonRunORM,
    MethodRegistryEntryORM,
    ModelVersionORM,
    ScoringProfileORM,
    ThresholdProfileORM,
    ValidationMetricORM,
    ValidationRunORM,
    utcnow,
)


class MethodRegistryError(ValueError):
    pass


@dataclass(frozen=True)
class RegistryActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


_REVIEW_NOTE = (
    "Registry and validation records describe method provenance and benchmark behavior; "
    "they do not establish chemical identity."
)


BUILTIN_METHODS: tuple[dict[str, Any], ...] = (
    {
        "slug": "candidate_specific_predicted_nmr_matching",
        "name": "candidate_specific_predicted_nmr_matching",
        "category": "nmr",
        "description": (
            "Candidate-specific predicted NMR matching for review-oriented evidence ranking."
        ),
        "implementation_module": "nmrcheck.candidate_predicted",
        "endpoint_paths_json": [
            "/candidates/predicted-nmr/match",
            "/candidates/predicted-nmr/match/evidence",
        ],
    },
    {
        "slug": "spectral_similarity_scoring",
        "name": "spectral_similarity_scoring",
        "category": "nmr",
        "description": "Spectral similarity scoring for NMR evidence comparison.",
        "implementation_module": "nmrcheck.spectral_similarity",
        "endpoint_paths_json": ["/spectral-similarity/score", "/spectral-similarity/evidence"],
    },
    {
        "slug": "hrms_exact_mass_matching",
        "name": "hrms_exact_mass_matching",
        "category": "ms",
        "description": "HRMS exact-mass candidate matching with tolerance-based scoring.",
        "implementation_module": "nmrcheck.hrms",
        "endpoint_paths_json": ["/ms/hrms/candidates/match", "/ms/hrms/candidates/match/evidence"],
    },
    {
        "slug": "adduct_isotope_inference",
        "name": "adduct_isotope_inference",
        "category": "ms",
        "description": "MS1 adduct and isotope-pattern inference for review workflows.",
        "implementation_module": "nmrcheck.adduct_inference",
        "endpoint_paths_json": ["/ms/adducts/infer", "/ms/adducts/infer/evidence"],
    },
    {
        "slug": "msms_annotation",
        "name": "msms_annotation",
        "category": "ms",
        "description": "Processed MS/MS annotation against candidate fragments.",
        "implementation_module": "nmrcheck.msms",
        "endpoint_paths_json": ["/ms/msms/annotate", "/ms/msms/annotate/evidence"],
    },
    {
        "slug": "fragmentation_tree_reasoning",
        "name": "fragmentation_tree_reasoning",
        "category": "ms",
        "description": "Fragmentation-tree reasoning over processed MS/MS evidence.",
        "implementation_module": "nmrcheck.fragmentation_tree",
        "endpoint_paths_json": [
            "/ms/msms/fragmentation-tree",
            "/ms/msms/fragmentation-tree/evidence",
        ],
    },
    {
        "slug": "lcms_import_bridge",
        "name": "lcms_import_bridge",
        "category": "lcms",
        "description": "LCMS import bridge for feature-table and mzML style inputs.",
        "implementation_module": "nmrcheck.lcms_import",
        "endpoint_paths_json": ["/lcms/import"],
    },
    {
        "slug": "lcms_feature_detection",
        "name": "lcms_feature_detection",
        "category": "lcms",
        "description": "LCMS feature detection for chromatographic evidence preparation.",
        "implementation_module": "nmrcheck.lcms_features",
        "endpoint_paths_json": ["/lcms/features/detect"],
    },
    {
        "slug": "lcms_feature_grouping",
        "name": "lcms_feature_grouping",
        "category": "lcms",
        "description": "LCMS feature grouping into reviewable feature families.",
        "implementation_module": "nmrcheck.lcms_grouping",
        "endpoint_paths_json": ["/lcms/features/group"],
    },
    {
        "slug": "lcms_feature_family_consensus",
        "name": "lcms_feature_family_consensus",
        "category": "lcms",
        "description": "LCMS family consensus scoring for candidate support.",
        "implementation_module": "nmrcheck.lcms_consensus",
        "endpoint_paths_json": ["/lcms/feature-families/consensus"],
    },
    {
        "slug": "lcms_dereplication",
        "name": "lcms_dereplication",
        "category": "lcms",
        "description": "LCMS dereplication against library-style candidate evidence.",
        "implementation_module": "nmrcheck.lcms_confidence_bridge",
        "endpoint_paths_json": ["/lcms/dereplication"],
    },
    {
        "slug": "unified_candidate_confidence",
        "name": "unified_candidate_confidence",
        "category": "unified_confidence",
        "description": "Unified candidate confidence aggregation across available evidence layers.",
        "implementation_module": "nmrcheck.unified_confidence",
        "endpoint_paths_json": [
            "/confidence/candidates/unified",
            "/confidence/candidates/unified/evidence",
        ],
    },
    {
        "slug": "regulatory_ready_report_composer",
        "name": "regulatory_ready_report_composer",
        "category": "report",
        "description": "Regulatory-ready report composition with cautious human-review language.",
        "implementation_module": "nmrcheck.regulatory_report",
        "endpoint_paths_json": ["/reports/structure-elucidation"],
    },
    {
        "slug": "quality_control_readiness_gate",
        "name": "quality_control_readiness_gate",
        "category": "qc",
        "description": (
            "Quality-control readiness gate for files, artifacts, evidence, and sessions."
        ),
        "implementation_module": "nmrcheck.quality_control_store",
        "endpoint_paths_json": ["/quality-control/files/{file_id}/assess"],
    },
    {
        "slug": "workflow_orchestration",
        "name": "workflow_orchestration",
        "category": "workflow",
        "description": "Workflow orchestration for multi-step reviewable analysis pipelines.",
        "implementation_module": "nmrcheck.workflow_store",
        "endpoint_paths_json": ["/workflow-runs", "/workflow-runs/{workflow_run_id}/start"],
    },
)


def ensure_builtin_methods(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as session:
        _ensure_builtin_methods(session)


def list_method_registry(
    session_factory: sessionmaker[Session],
    *,
    category: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[MethodRegistryEntry]:
    with session_scope(session_factory) as session:
        _ensure_builtin_methods(session)
        stmt = select(MethodRegistryEntryORM).order_by(MethodRegistryEntryORM.slug.asc())
        if category is not None:
            stmt = stmt.where(MethodRegistryEntryORM.category == category)
        if status is not None:
            stmt = stmt.where(MethodRegistryEntryORM.status == status)
        rows = session.scalars(stmt.limit(limit)).all()
        return [_method_to_record(row) for row in rows]


def create_method_entry(
    session_factory: sessionmaker[Session],
    payload: MethodRegistryEntryCreate,
    *,
    actor: RegistryActor,
) -> MethodRegistryEntry:
    with session_scope(session_factory) as session:
        _ensure_builtin_methods(session)
        _ensure_optional_profile(
            session, ScoringProfileORM, payload.default_scoring_profile_id, "scoring profile"
        )
        _ensure_optional_profile(
            session, ThresholdProfileORM, payload.default_threshold_profile_id, "threshold profile"
        )
        row = MethodRegistryEntryORM(
            name=payload.name,
            slug=payload.slug,
            category=payload.category,
            version=payload.version,
            description=payload.description,
            implementation_module=payload.implementation_module,
            endpoint_paths_json=_json_dump(payload.endpoint_paths_json),
            default_scoring_profile_id=payload.default_scoring_profile_id,
            default_threshold_profile_id=payload.default_threshold_profile_id,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise MethodRegistryError(
                "A method with that slug and version already exists."
            ) from exc
        _audit(
            session,
            actor=actor,
            event_type="method_registry.method.create",
            message="Method registry entry created.",
            entity_type="method_registry_entry",
            entity_id=row.id,
            metadata={"slug": row.slug, "version": row.version, "category": row.category},
        )
        session.refresh(row)
        return _method_to_record(row)


def get_method_entry(
    session_factory: sessionmaker[Session],
    method_id: int,
) -> MethodRegistryEntry | None:
    with session_scope(session_factory) as session:
        _ensure_builtin_methods(session)
        row = session.get(MethodRegistryEntryORM, method_id)
        return _method_to_record(row) if row is not None else None


def update_method_entry(
    session_factory: sessionmaker[Session],
    method_id: int,
    payload: MethodRegistryEntryUpdate,
    *,
    actor: RegistryActor,
) -> MethodRegistryEntry | None:
    with session_scope(session_factory) as session:
        _ensure_builtin_methods(session)
        row = session.get(MethodRegistryEntryORM, method_id)
        if row is None:
            return None
        for field in (
            "name",
            "slug",
            "category",
            "version",
            "description",
            "implementation_module",
            "default_scoring_profile_id",
            "default_threshold_profile_id",
            "status",
        ):
            if field in payload.model_fields_set:
                setattr(row, field, getattr(payload, field))
        if payload.endpoint_paths_json is not None:
            row.endpoint_paths_json = _json_dump(payload.endpoint_paths_json)
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.updated_at = utcnow()
        try:
            session.flush()
        except IntegrityError as exc:
            raise MethodRegistryError(
                "A method with that slug and version already exists."
            ) from exc
        _audit(
            session,
            actor=actor,
            event_type="method_registry.method.update",
            message="Method registry entry updated.",
            entity_type="method_registry_entry",
            entity_id=row.id,
            metadata={"updated_fields": sorted(payload.model_fields_set)},
        )
        return _method_to_record(row)


def list_model_versions(
    session_factory: sessionmaker[Session],
    *,
    method_id: int | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[ModelVersion]:
    with session_scope(session_factory) as session:
        _ensure_builtin_methods(session)
        stmt = select(ModelVersionORM).order_by(ModelVersionORM.id.desc())
        if method_id is not None:
            stmt = stmt.where(ModelVersionORM.method_id == method_id)
        if status is not None:
            stmt = stmt.where(ModelVersionORM.status == status)
        return [_model_version_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def create_model_version(
    session_factory: sessionmaker[Session],
    payload: ModelVersionCreate,
    *,
    actor: RegistryActor,
) -> ModelVersion:
    with session_scope(session_factory) as session:
        _ensure_builtin_methods(session)
        _ensure_optional_method(session, payload.method_id)
        row = ModelVersionORM(**payload.model_dump(exclude={"metadata_json"}))
        row.metadata_json = _json_dump(payload.metadata_json)
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="method_registry.model_version.create",
            message="Model version created.",
            entity_type="model_version",
            entity_id=row.id,
            metadata={
                "method_id": row.method_id,
                "model_name": row.model_name,
                "version": row.version,
            },
        )
        return _model_version_to_record(row)


def get_model_version(
    session_factory: sessionmaker[Session],
    model_version_id: int,
) -> ModelVersion | None:
    with session_scope(session_factory) as session:
        row = session.get(ModelVersionORM, model_version_id)
        return _model_version_to_record(row) if row is not None else None


def update_model_version(
    session_factory: sessionmaker[Session],
    model_version_id: int,
    payload: ModelVersionUpdate,
    *,
    actor: RegistryActor,
) -> ModelVersion | None:
    with session_scope(session_factory) as session:
        row = session.get(ModelVersionORM, model_version_id)
        if row is None:
            return None
        if "method_id" in payload.model_fields_set:
            _ensure_optional_method(session, payload.method_id)
        _apply_model_update(row, payload)
        row.updated_at = utcnow()
        _audit_update(session, actor, "model_version", row.id, payload.model_fields_set)
        return _model_version_to_record(row)


def list_scoring_profiles(
    session_factory: sessionmaker[Session],
    *,
    method_id: int | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[ScoringProfile]:
    with session_scope(session_factory) as session:
        stmt = select(ScoringProfileORM).order_by(ScoringProfileORM.id.desc())
        if method_id is not None:
            stmt = stmt.where(ScoringProfileORM.method_id == method_id)
        if status is not None:
            stmt = stmt.where(ScoringProfileORM.status == status)
        return [_scoring_profile_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def create_scoring_profile(
    session_factory: sessionmaker[Session],
    payload: ScoringProfileCreate,
    *,
    actor: RegistryActor,
) -> ScoringProfile:
    with session_scope(session_factory) as session:
        _ensure_optional_method(session, payload.method_id)
        row = ScoringProfileORM(
            name=payload.name,
            slug=payload.slug,
            version=payload.version,
            method_id=payload.method_id,
            weights_json=_json_dump(payload.weights_json),
            scoring_rules_json=_json_dump(payload.scoring_rules_json),
            label_thresholds_json=_json_dump(payload.label_thresholds_json),
            description=payload.description,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise MethodRegistryError(
                "A scoring profile with that slug and version already exists."
            ) from exc
        _audit_create(
            session, actor, "scoring_profile", row.id, {"slug": row.slug, "version": row.version}
        )
        return _scoring_profile_to_record(row)


def get_scoring_profile(
    session_factory: sessionmaker[Session], profile_id: int
) -> ScoringProfile | None:
    with session_scope(session_factory) as session:
        row = session.get(ScoringProfileORM, profile_id)
        return _scoring_profile_to_record(row) if row is not None else None


def update_scoring_profile(
    session_factory: sessionmaker[Session],
    profile_id: int,
    payload: ScoringProfileUpdate,
    *,
    actor: RegistryActor,
) -> ScoringProfile | None:
    with session_scope(session_factory) as session:
        row = session.get(ScoringProfileORM, profile_id)
        if row is None:
            return None
        if "method_id" in payload.model_fields_set:
            _ensure_optional_method(session, payload.method_id)
        for field in ("name", "slug", "version", "method_id", "description", "status"):
            if field in payload.model_fields_set:
                setattr(row, field, getattr(payload, field))
        if payload.weights_json is not None:
            row.weights_json = _json_dump(payload.weights_json)
        if payload.scoring_rules_json is not None:
            row.scoring_rules_json = _json_dump(payload.scoring_rules_json)
        if payload.label_thresholds_json is not None:
            row.label_thresholds_json = _json_dump(payload.label_thresholds_json)
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.updated_at = utcnow()
        _audit_update(session, actor, "scoring_profile", row.id, payload.model_fields_set)
        return _scoring_profile_to_record(row)


def list_threshold_profiles(
    session_factory: sessionmaker[Session],
    *,
    category: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[ThresholdProfile]:
    with session_scope(session_factory) as session:
        stmt = select(ThresholdProfileORM).order_by(ThresholdProfileORM.id.desc())
        if category is not None:
            stmt = stmt.where(ThresholdProfileORM.category == category)
        if status is not None:
            stmt = stmt.where(ThresholdProfileORM.status == status)
        return [
            _threshold_profile_to_record(row) for row in session.scalars(stmt.limit(limit)).all()
        ]


def create_threshold_profile(
    session_factory: sessionmaker[Session],
    payload: ThresholdProfileCreate,
    *,
    actor: RegistryActor,
) -> ThresholdProfile:
    with session_scope(session_factory) as session:
        row = ThresholdProfileORM(
            name=payload.name,
            slug=payload.slug,
            version=payload.version,
            category=payload.category,
            thresholds_json=_json_dump(payload.thresholds_json),
            description=payload.description,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise MethodRegistryError(
                "A threshold profile with that slug and version already exists."
            ) from exc
        _audit_create(
            session, actor, "threshold_profile", row.id, {"slug": row.slug, "version": row.version}
        )
        return _threshold_profile_to_record(row)


def get_threshold_profile(
    session_factory: sessionmaker[Session], profile_id: int
) -> ThresholdProfile | None:
    with session_scope(session_factory) as session:
        row = session.get(ThresholdProfileORM, profile_id)
        return _threshold_profile_to_record(row) if row is not None else None


def update_threshold_profile(
    session_factory: sessionmaker[Session],
    profile_id: int,
    payload: ThresholdProfileUpdate,
    *,
    actor: RegistryActor,
) -> ThresholdProfile | None:
    with session_scope(session_factory) as session:
        row = session.get(ThresholdProfileORM, profile_id)
        if row is None:
            return None
        for field in ("name", "slug", "version", "category", "description", "status"):
            if field in payload.model_fields_set:
                setattr(row, field, getattr(payload, field))
        if payload.thresholds_json is not None:
            row.thresholds_json = _json_dump(payload.thresholds_json)
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.updated_at = utcnow()
        _audit_update(session, actor, "threshold_profile", row.id, payload.model_fields_set)
        return _threshold_profile_to_record(row)


def list_benchmark_datasets(
    session_factory: sessionmaker[Session],
    *,
    category: str | None = None,
    limit: int = 500,
) -> list[BenchmarkDataset]:
    with session_scope(session_factory) as session:
        stmt = select(BenchmarkDatasetORM).order_by(BenchmarkDatasetORM.id.desc())
        if category is not None:
            stmt = stmt.where(BenchmarkDatasetORM.category == category)
        return [_benchmark_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def create_benchmark_dataset(
    session_factory: sessionmaker[Session],
    payload: BenchmarkDatasetCreate,
    *,
    actor: RegistryActor,
) -> BenchmarkDataset:
    with session_scope(session_factory) as session:
        row = BenchmarkDatasetORM(
            name=payload.name,
            slug=payload.slug,
            version=payload.version,
            category=payload.category,
            description=payload.description,
            dataset_hash=payload.dataset_hash,
            sample_count=payload.sample_count,
            ground_truth_summary=payload.ground_truth_summary,
            data_uri=payload.data_uri,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise MethodRegistryError(
                "A benchmark dataset with that slug and version already exists."
            ) from exc
        _audit_create(
            session, actor, "benchmark_dataset", row.id, {"slug": row.slug, "version": row.version}
        )
        return _benchmark_to_record(row)


def get_benchmark_dataset(
    session_factory: sessionmaker[Session], benchmark_id: int
) -> BenchmarkDataset | None:
    with session_scope(session_factory) as session:
        row = session.get(BenchmarkDatasetORM, benchmark_id)
        return _benchmark_to_record(row) if row is not None else None


def create_validation_run(
    session_factory: sessionmaker[Session],
    payload: ValidationRunCreate,
    *,
    actor: RegistryActor,
) -> ValidationRun:
    with session_scope(session_factory) as session:
        _ensure_builtin_methods(session)
        _ensure_validation_refs(session, payload)
        metrics_json = dict(payload.metrics_json)
        for metric in payload.metrics:
            metrics_json.setdefault(metric.metric_name, metric.metric_value)
        row = ValidationRunORM(
            method_id=payload.method_id,
            model_version_id=payload.model_version_id,
            scoring_profile_id=payload.scoring_profile_id,
            threshold_profile_id=payload.threshold_profile_id,
            benchmark_dataset_id=payload.benchmark_dataset_id,
            status=payload.status,
            started_at=payload.started_at,
            finished_at=payload.finished_at,
            metrics_json=_json_dump(metrics_json),
            warnings_json=_json_dump(payload.warnings_json),
            notes_json=_json_dump(payload.notes_json),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        for metric in payload.metrics:
            session.add(
                ValidationMetricORM(
                    validation_run_id=row.id,
                    metric_name=metric.metric_name,
                    metric_value=metric.metric_value,
                    metric_unit=metric.metric_unit,
                    target_value=metric.target_value,
                    passed=metric.passed,
                    metadata_json=_json_dump(metric.metadata_json),
                )
            )
            if metric.passed is False:
                session.add(
                    DriftAlertORM(
                        method_id=payload.method_id,
                        model_version_id=payload.model_version_id,
                        severity="warning",
                        title=f"Validation metric failed: {metric.metric_name}",
                        message="Validation metric did not meet its configured target.",
                        metric_name=metric.metric_name,
                        baseline_value=metric.target_value,
                        current_value=metric.metric_value,
                        metadata_json=_json_dump(
                            {"validation_run_id": row.id, "auto_created": True}
                        ),
                    )
                )
        for alert in payload.drift_alerts:
            session.add(
                DriftAlertORM(
                    method_id=alert.method_id or payload.method_id,
                    model_version_id=alert.model_version_id or payload.model_version_id,
                    severity=alert.severity,
                    title=alert.title,
                    message=alert.message,
                    metric_name=alert.metric_name,
                    baseline_value=alert.baseline_value,
                    current_value=alert.current_value,
                    metadata_json=_json_dump({**alert.metadata_json, "validation_run_id": row.id}),
                )
            )
        _audit_create(
            session,
            actor,
            "validation_run",
            row.id,
            {
                "method_id": row.method_id,
                "status": row.status,
                "metric_count": len(payload.metrics),
            },
        )
        session.flush()
        return _validation_run_to_record(row, session)


def list_validation_runs(
    session_factory: sessionmaker[Session], *, limit: int = 500
) -> list[ValidationRun]:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(ValidationRunORM).order_by(ValidationRunORM.id.desc()).limit(limit)
        ).all()
        return [_validation_run_to_record(row, session) for row in rows]


def get_validation_run(
    session_factory: sessionmaker[Session], validation_run_id: int
) -> ValidationRun | None:
    with session_scope(session_factory) as session:
        row = session.get(ValidationRunORM, validation_run_id)
        return _validation_run_to_record(row, session) if row is not None else None


def create_method_comparison(
    session_factory: sessionmaker[Session],
    payload: MethodComparisonRunCreate,
    *,
    actor: RegistryActor,
) -> MethodComparisonRun:
    with session_scope(session_factory) as session:
        _ensure_optional_method(session, payload.baseline_method_id)
        _ensure_optional_method(session, payload.candidate_method_id)
        _ensure_optional_profile(
            session, BenchmarkDatasetORM, payload.benchmark_dataset_id, "benchmark dataset"
        )
        row = MethodComparisonRunORM(
            baseline_method_id=payload.baseline_method_id,
            candidate_method_id=payload.candidate_method_id,
            benchmark_dataset_id=payload.benchmark_dataset_id,
            status=payload.status,
            metrics_json=_json_dump(payload.metrics_json),
            winner=payload.winner,
            warnings_json=_json_dump(payload.warnings_json),
            notes_json=_json_dump(payload.notes_json),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit_create(session, actor, "method_comparison_run", row.id, {"status": row.status})
        return _comparison_to_record(row)


def list_method_comparisons(
    session_factory: sessionmaker[Session],
    *,
    limit: int = 500,
) -> list[MethodComparisonRun]:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(MethodComparisonRunORM).order_by(MethodComparisonRunORM.id.desc()).limit(limit)
        ).all()
        return [_comparison_to_record(row) for row in rows]


def get_method_comparison(
    session_factory: sessionmaker[Session],
    comparison_id: int,
) -> MethodComparisonRun | None:
    with session_scope(session_factory) as session:
        row = session.get(MethodComparisonRunORM, comparison_id)
        return _comparison_to_record(row) if row is not None else None


def model_health(session_factory: sessionmaker[Session]) -> ModelHealthSummary:
    with session_scope(session_factory) as session:
        _ensure_builtin_methods(session)
        method_count = session.scalar(select(func.count(MethodRegistryEntryORM.id))) or 0
        active_method_count = (
            session.scalar(
                select(func.count(MethodRegistryEntryORM.id)).where(
                    MethodRegistryEntryORM.status == "active"
                )
            )
            or 0
        )
        model_version_count = session.scalar(select(func.count(ModelVersionORM.id))) or 0
        validation_run_count = session.scalar(select(func.count(ValidationRunORM.id))) or 0
        open_drift_alert_count = (
            session.scalar(
                select(func.count(DriftAlertORM.id)).where(DriftAlertORM.status == "open")
            )
            or 0
        )
        latest_runs = session.scalars(
            select(ValidationRunORM).order_by(ValidationRunORM.id.desc()).limit(5)
        ).all()
        alerts = session.scalars(
            select(DriftAlertORM)
            .where(DriftAlertORM.status == "open")
            .order_by(DriftAlertORM.id.desc())
            .limit(10)
        ).all()
        return ModelHealthSummary(
            method_count=int(method_count),
            active_method_count=int(active_method_count),
            model_version_count=int(model_version_count),
            validation_run_count=int(validation_run_count),
            open_drift_alert_count=int(open_drift_alert_count),
            latest_validation_runs=[_validation_run_to_record(row, session) for row in latest_runs],
            drift_alerts=[_drift_alert_to_record(row) for row in alerts],
            notes=[_REVIEW_NOTE],
            metadata_json={"builtin_method_count": len(BUILTIN_METHODS)},
        )


def list_drift_alerts(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    limit: int = 500,
) -> list[DriftAlert]:
    with session_scope(session_factory) as session:
        stmt = select(DriftAlertORM).order_by(DriftAlertORM.id.desc())
        if status is not None:
            stmt = stmt.where(DriftAlertORM.status == status)
        return [_drift_alert_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def set_drift_alert_status(
    session_factory: sessionmaker[Session],
    alert_id: int,
    status: str,
    *,
    actor: RegistryActor,
) -> DriftAlert | None:
    with session_scope(session_factory) as session:
        row = session.get(DriftAlertORM, alert_id)
        if row is None:
            return None
        row.status = status
        metadata = _json_dict(row.metadata_json)
        metadata[f"{status}_at"] = utcnow().isoformat()
        metadata[f"{status}_by"] = actor.email
        row.metadata_json = _json_dump(metadata)
        _audit(
            session,
            actor=actor,
            event_type=f"method_registry.drift_alert.{status}",
            message=f"Drift alert marked {status}.",
            entity_type="drift_alert",
            entity_id=row.id,
            metadata={"status": status, "method_id": row.method_id},
        )
        return _drift_alert_to_record(row)


def _ensure_builtin_methods(session: Session) -> None:
    for entry in BUILTIN_METHODS:
        existing = session.scalar(
            select(MethodRegistryEntryORM)
            .where(MethodRegistryEntryORM.slug == entry["slug"])
            .where(MethodRegistryEntryORM.version == "1.0.0")
        )
        if existing is not None:
            continue
        session.add(
            MethodRegistryEntryORM(
                name=entry["name"],
                slug=entry["slug"],
                category=entry["category"],
                version="1.0.0",
                description=entry["description"],
                implementation_module=entry.get("implementation_module"),
                endpoint_paths_json=_json_dump(entry.get("endpoint_paths_json", [])),
                status="active",
                metadata_json=_json_dump({"builtin": True}),
            )
        )
    session.flush()


def _apply_model_update(row: ModelVersionORM, payload: ModelVersionUpdate) -> None:
    for field in (
        "method_id",
        "model_name",
        "model_family",
        "version",
        "training_data_summary",
        "validation_summary",
        "model_hash",
        "artifact_uri",
        "status",
    ):
        if field in payload.model_fields_set:
            setattr(row, field, getattr(payload, field))
    if payload.metadata_json is not None:
        row.metadata_json = _json_dump(payload.metadata_json)


def _ensure_optional_method(session: Session, method_id: int | None) -> None:
    _ensure_optional_profile(session, MethodRegistryEntryORM, method_id, "method")


def _ensure_optional_profile(
    session: Session, orm_cls: type[Any], row_id: int | None, label: str
) -> None:
    if row_id is not None and session.get(orm_cls, row_id) is None:
        raise MethodRegistryError(f"{label.title()} {row_id} not found.")


def _ensure_validation_refs(session: Session, payload: ValidationRunCreate) -> None:
    _ensure_optional_method(session, payload.method_id)
    _ensure_optional_profile(session, ModelVersionORM, payload.model_version_id, "model version")
    _ensure_optional_profile(
        session, ScoringProfileORM, payload.scoring_profile_id, "scoring profile"
    )
    _ensure_optional_profile(
        session, ThresholdProfileORM, payload.threshold_profile_id, "threshold profile"
    )
    _ensure_optional_profile(
        session, BenchmarkDatasetORM, payload.benchmark_dataset_id, "benchmark dataset"
    )


def _method_to_record(row: MethodRegistryEntryORM) -> MethodRegistryEntry:
    return MethodRegistryEntry(
        id=row.id,
        name=row.name,
        slug=row.slug,
        category=row.category,  # type: ignore[arg-type]
        version=row.version,
        description=row.description,
        implementation_module=row.implementation_module,
        endpoint_paths_json=_json_list(row.endpoint_paths_json),
        default_scoring_profile_id=row.default_scoring_profile_id,
        default_threshold_profile_id=row.default_threshold_profile_id,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_REVIEW_NOTE],
    )


def _model_version_to_record(row: ModelVersionORM) -> ModelVersion:
    return ModelVersion(
        id=row.id,
        method_id=row.method_id,
        model_name=row.model_name,
        model_family=row.model_family,  # type: ignore[arg-type]
        version=row.version,
        training_data_summary=row.training_data_summary,
        validation_summary=row.validation_summary,
        model_hash=row.model_hash,
        artifact_uri=row.artifact_uri,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_REVIEW_NOTE],
    )


def _scoring_profile_to_record(row: ScoringProfileORM) -> ScoringProfile:
    return ScoringProfile(
        id=row.id,
        name=row.name,
        slug=row.slug,
        version=row.version,
        method_id=row.method_id,
        weights_json=_json_dict(row.weights_json),
        scoring_rules_json=_json_dict(row.scoring_rules_json),
        label_thresholds_json=_json_dict(row.label_thresholds_json),
        description=row.description,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_REVIEW_NOTE],
    )


def _threshold_profile_to_record(row: ThresholdProfileORM) -> ThresholdProfile:
    return ThresholdProfile(
        id=row.id,
        name=row.name,
        slug=row.slug,
        version=row.version,
        category=row.category,  # type: ignore[arg-type]
        thresholds_json=_json_dict(row.thresholds_json),
        description=row.description,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_REVIEW_NOTE],
    )


def _benchmark_to_record(row: BenchmarkDatasetORM) -> BenchmarkDataset:
    return BenchmarkDataset(
        id=row.id,
        name=row.name,
        slug=row.slug,
        version=row.version,
        category=row.category,  # type: ignore[arg-type]
        description=row.description,
        dataset_hash=row.dataset_hash,
        sample_count=row.sample_count,
        ground_truth_summary=row.ground_truth_summary,
        data_uri=row.data_uri,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_REVIEW_NOTE],
    )


def _validation_run_to_record(row: ValidationRunORM, session: Session) -> ValidationRun:
    metrics = session.scalars(
        select(ValidationMetricORM)
        .where(ValidationMetricORM.validation_run_id == row.id)
        .order_by(ValidationMetricORM.id.asc())
    ).all()
    return ValidationRun(
        id=row.id,
        method_id=row.method_id,
        model_version_id=row.model_version_id,
        scoring_profile_id=row.scoring_profile_id,
        threshold_profile_id=row.threshold_profile_id,
        benchmark_dataset_id=row.benchmark_dataset_id,
        status=row.status,  # type: ignore[arg-type]
        started_at=row.started_at,
        finished_at=row.finished_at,
        metrics_json=_json_dict(row.metrics_json),
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_list(row.notes_json),
        metrics=[_metric_to_record(metric) for metric in metrics],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_REVIEW_NOTE],
    )


def _metric_to_record(row: ValidationMetricORM) -> ValidationMetric:
    return ValidationMetric(
        id=row.id,
        validation_run_id=row.validation_run_id,
        metric_name=row.metric_name,
        metric_value=row.metric_value,
        metric_unit=row.metric_unit,
        target_value=row.target_value,
        passed=row.passed,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _drift_alert_to_record(row: DriftAlertORM) -> DriftAlert:
    return DriftAlert(
        id=row.id,
        method_id=row.method_id,
        model_version_id=row.model_version_id,
        severity=row.severity,  # type: ignore[arg-type]
        title=row.title,
        message=row.message,
        metric_name=row.metric_name,
        baseline_value=row.baseline_value,
        current_value=row.current_value,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_REVIEW_NOTE],
    )


def _comparison_to_record(row: MethodComparisonRunORM) -> MethodComparisonRun:
    return MethodComparisonRun(
        id=row.id,
        baseline_method_id=row.baseline_method_id,
        candidate_method_id=row.candidate_method_id,
        benchmark_dataset_id=row.benchmark_dataset_id,
        status=row.status,  # type: ignore[arg-type]
        metrics_json=_json_dict(row.metrics_json),
        winner=row.winner,
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_list(row.notes_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_REVIEW_NOTE],
    )


def _audit_create(
    session: Session,
    actor: RegistryActor,
    entity_type: str,
    entity_id: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    _audit(
        session,
        actor=actor,
        event_type=f"method_registry.{entity_type}.create",
        message=f"{entity_type.replace('_', ' ').title()} created.",
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=metadata or {},
    )


def _audit_update(
    session: Session,
    actor: RegistryActor,
    entity_type: str,
    entity_id: int,
    updated_fields: set[str],
) -> None:
    _audit(
        session,
        actor=actor,
        event_type=f"method_registry.{entity_type}.update",
        message=f"{entity_type.replace('_', ' ').title()} updated.",
        entity_type=entity_type,
        entity_id=entity_id,
        metadata={"updated_fields": sorted(updated_fields)},
    )


def _audit(
    session: Session,
    *,
    actor: RegistryActor,
    event_type: str,
    message: str,
    entity_type: str,
    entity_id: int,
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


def _json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


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
