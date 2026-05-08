from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    AuditEventRecord,
    DataMode,
    DebugBundle,
    DebugBundleCreate,
    DependencyCheck,
    DependencyStatus,
    EnvironmentCheckResponse,
    OperationalMetric,
    SecurityEvent,
    SecurityEventCreate,
    SecuritySummary,
    SystemHealthResponse,
    SystemHealthStatus,
    SystemStatusResponse,
)
from .orm import (
    AnalysisJobORM,
    ArtifactRecordORM,
    AuditEventORM,
    DebugBundleORM,
    JobORM,
    ManagedFileRecordORM,
    RawArchiveORM,
    SecurityEventORM,
    SpectraCheckSessionORM,
    utcnow,
)
from .settings import Settings


class OperationsError(ValueError):
    pass


@dataclass(frozen=True)
class OperationsActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


SECRET_NAME_TOKENS = ("SECRET", "PASSWORD", "TOKEN", "API_KEY", "PRIVATE", "CREDENTIAL")
_SAFE_NOTE = (
    "Operational diagnostics expose metadata only; they do not include raw uploaded files, "
    "secrets, passwords, access tokens, or scientific identity claims."
)


def system_health(
    session_factory: sessionmaker[Session],
    *,
    settings: Settings,
    uptime_seconds: float | None,
    local_auth_disabled: bool,
) -> SystemHealthResponse:
    checks = [database_check(session_factory)]
    status = _aggregate_status(checks)
    warnings = _local_dev_warnings(local_auth_disabled)
    generated_at = utcnow()
    return SystemHealthResponse(
        status=status,
        timestamp=generated_at,
        backend_version=settings.release_version,
        environment=settings.app_env,
        uptime_seconds=uptime_seconds,
        checks=checks,
        warnings=warnings,
        notes=["Lightweight health check for uptime monitoring.", _SAFE_NOTE],
        metadata={"auth_mode": "local-dev-disabled" if local_auth_disabled else "enforced"},
        data_mode=_data_mode_for_health_status(status),
        last_synced_at=generated_at if status != "unhealthy" else None,
        generated_at=generated_at,
    )


def system_status(
    session_factory: sessionmaker[Session],
    *,
    settings: Settings,
    storage_root: Path,
    openapi_available: bool,
    local_auth_disabled: bool,
) -> SystemStatusResponse:
    checks = dependencies(
        session_factory,
        settings=settings,
        storage_root=storage_root,
        openapi_available=openapi_available,
    )
    by_name = {check.name: check for check in checks}
    warnings = _local_dev_warnings(local_auth_disabled)
    if not openapi_available:
        warnings.append("OpenAPI schema could not be generated.")
    status = _aggregate_status(checks)
    generated_at = utcnow()
    return SystemStatusResponse(
        status=status,
        backend_version=settings.release_version,
        api_version=settings.release_version,
        database_status=by_name.get("database", _unknown_check("database")).status,
        storage_status=by_name.get("storage", _unknown_check("storage")).status,
        job_queue_status=by_name.get("job_queue", _unknown_check("job_queue")).status,
        worker_status=by_name.get("worker", _unknown_check("worker")).status,
        openapi_available=openapi_available,
        warnings=warnings,
        notes=[_SAFE_NOTE],
        metadata={"dependency_count": len(checks), "environment": settings.app_env},
        data_mode=_data_mode_for_health_status(status),
        last_synced_at=generated_at if status != "unhealthy" else None,
        generated_at=generated_at,
    )


def dependencies(
    session_factory: sessionmaker[Session],
    *,
    settings: Settings,
    storage_root: Path,
    openapi_available: bool,
) -> list[DependencyCheck]:
    return [
        database_check(session_factory),
        storage_check(storage_root),
        openapi_check(openapi_available),
        job_queue_check(session_factory, settings),
        worker_check(settings),
    ]


def database_check(session_factory: sessionmaker[Session]) -> DependencyCheck:
    start = time.perf_counter()
    try:
        with session_factory() as session:
            session.execute(select(1))
        return DependencyCheck(
            name="database",
            status="ok",
            latency_ms=_elapsed_ms(start),
            message="Database connection succeeded.",
        )
    except Exception as exc:
        return DependencyCheck(
            name="database",
            status="error",
            latency_ms=_elapsed_ms(start),
            message=f"Database check failed: {type(exc).__name__}",
        )


def storage_check(storage_root: Path) -> DependencyCheck:
    start = time.perf_counter()
    try:
        exists = storage_root.exists()
        writable = storage_root.exists() and os.access(storage_root, os.W_OK)
        status: DependencyStatus = "ok" if exists and writable else "warning"
        message = "Storage root is available." if exists else "Storage root does not exist yet."
        return DependencyCheck(
            name="storage",
            status=status,
            latency_ms=_elapsed_ms(start),
            message=message,
            metadata_json={"configured": True, "exists": exists, "writable": writable},
        )
    except Exception as exc:
        return DependencyCheck(
            name="storage",
            status="error",
            latency_ms=_elapsed_ms(start),
            message=f"Storage check failed: {type(exc).__name__}",
        )


def openapi_check(openapi_available: bool) -> DependencyCheck:
    return DependencyCheck(
        name="openapi",
        status="ok" if openapi_available else "error",
        message="OpenAPI schema is available."
        if openapi_available
        else "OpenAPI schema unavailable.",
    )


def job_queue_check(session_factory: sessionmaker[Session], settings: Settings) -> DependencyCheck:
    start = time.perf_counter()
    try:
        with session_factory() as session:
            queued = session.scalar(
                select(func.count(AnalysisJobORM.id)).where(AnalysisJobORM.status == "queued")
            )
            failed = session.scalar(
                select(func.count(AnalysisJobORM.id)).where(AnalysisJobORM.status == "failed")
            )
        return DependencyCheck(
            name="job_queue",
            status="ok",
            latency_ms=_elapsed_ms(start),
            message="Job tables are queryable.",
            metadata_json={
                "backend": "rq" if settings.redis_url else "fastapi-background",
                "redis_configured": settings.redis_url is not None,
                "queued_jobs": int(queued or 0),
                "failed_jobs": int(failed or 0),
            },
        )
    except Exception as exc:
        return DependencyCheck(
            name="job_queue",
            status="warning",
            latency_ms=_elapsed_ms(start),
            message=f"Job queue check was incomplete: {type(exc).__name__}",
        )


def worker_check(settings: Settings) -> DependencyCheck:
    return DependencyCheck(
        name="worker",
        status="unknown" if settings.redis_url else "ok",
        message=(
            "External RQ worker status is not directly observable."
            if settings.redis_url
            else "FastAPI background-task mode does not require a separate worker."
        ),
        metadata_json={
            "queue_name": settings.queue_name,
            "redis_configured": settings.redis_url is not None,
        },
    )


def environment_check(settings: Settings, *, local_auth_disabled: bool) -> EnvironmentCheckResponse:
    required = ["DATABASE_URL"]
    if settings.app_env.strip().lower() == "production":
        required.append("API_KEY")
    missing = [name for name in required if not _env_present(name, settings)]
    unsafe: list[str] = []
    if settings.app_env.strip().lower() == "production" and settings.debug:
        unsafe.append("DEBUG")
    if settings.allowed_origins == ("*",) and settings.app_env.strip().lower() == "production":
        unsafe.append("ALLOWED_ORIGINS")
    if local_auth_disabled:
        unsafe.append("AUTH_DISABLED")
    secret_like_present = [
        name for name in os.environ if any(token in name.upper() for token in SECRET_NAME_TOKENS)
    ]
    warnings = []
    if missing:
        warnings.append("One or more required environment variables are missing.")
    if unsafe:
        warnings.append("One or more environment settings are unsafe for production.")
    return EnvironmentCheckResponse(
        environment=settings.app_env,
        required_variables_present=not missing,
        missing_variables=missing,
        unsafe_variables=unsafe,
        public_variables={
            "APP_ENV": settings.app_env,
            "DEBUG": settings.debug,
            "LOG_LEVEL": settings.log_level,
            "QUEUE_NAME": settings.queue_name,
            "HEALTHCHECK_PATH": settings.healthcheck_path,
            "RELEASE_VERSION": settings.release_version,
            "SECRET_LIKE_VARIABLES_PRESENT": sorted(secret_like_present),
        },
        warnings=warnings,
        notes=[
            "Secret values are intentionally omitted; only variable names/presence are reported."
        ],
        metadata={"auth_mode": "local-dev-disabled" if local_auth_disabled else "enforced"},
    )


def operational_metrics(session_factory: sessionmaker[Session]) -> list[OperationalMetric]:
    with session_scope(session_factory) as session:
        return [
            _metric("jobs_total", _count(session, JobORM), "count"),
            _metric("analysis_jobs_total", _count(session, AnalysisJobORM), "count"),
            _metric(
                "analysis_jobs_failed",
                _count_where(session, AnalysisJobORM, AnalysisJobORM.status == "failed"),
                "count",
            ),
            _metric("artifacts_total", _count(session, ArtifactRecordORM), "count"),
            _metric("managed_files_total", _count(session, ManagedFileRecordORM), "count"),
            _metric("raw_archives_total", _count(session, RawArchiveORM), "count"),
            _metric("audit_events_total", _count(session, AuditEventORM), "count"),
            _metric("security_events_total", _count(session, SecurityEventORM), "count"),
        ]


def jobs_summary(session_factory: sessionmaker[Session]) -> dict[str, Any]:
    with session_scope(session_factory) as session:
        statuses = {
            str(status): int(count)
            for status, count in session.execute(
                select(AnalysisJobORM.status, func.count(AnalysisJobORM.id)).group_by(
                    AnalysisJobORM.status
                )
            ).all()
        }
        legacy_statuses = {
            str(status): int(count)
            for status, count in session.execute(
                select(JobORM.status, func.count(JobORM.id)).group_by(JobORM.status)
            ).all()
        }
        recent = [
            {
                "id": row.id,
                "job_type": row.job_type,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
                "error_present": bool(row.error_message),
            }
            for row in session.scalars(
                select(AnalysisJobORM).order_by(AnalysisJobORM.id.desc()).limit(20)
            ).all()
        ]
    return {
        "status": "ok",
        "analysis_job_status_counts": statuses,
        "legacy_job_status_counts": legacy_statuses,
        "recent_jobs": recent,
        "warnings": [],
        "notes": [_SAFE_NOTE],
        "metadata": {"recent_limit": 20},
    }


def storage_summary(
    session_factory: sessionmaker[Session], *, storage_root: Path
) -> dict[str, Any]:
    with session_scope(session_factory) as session:
        managed_count = _count(session, ManagedFileRecordORM)
        raw_count = _count(session, RawArchiveORM)
        total_managed_bytes = (
            session.scalar(select(func.sum(ManagedFileRecordORM.file_size_bytes))) or 0
        )
        total_raw_bytes = session.scalar(select(func.sum(RawArchiveORM.byte_size))) or 0
        backends = {
            str(backend): int(count)
            for backend, count in session.execute(
                select(
                    ManagedFileRecordORM.storage_backend, func.count(ManagedFileRecordORM.id)
                ).group_by(ManagedFileRecordORM.storage_backend)
            ).all()
        }
    return {
        "status": "ok",
        "storage_root_exists": storage_root.exists(),
        "managed_file_count": managed_count,
        "raw_archive_count": raw_count,
        "total_file_bytes": int(total_managed_bytes) + int(total_raw_bytes),
        "storage_backends": backends,
        "warnings": [] if storage_root.exists() else ["Storage root does not exist yet."],
        "notes": [
            "Storage summary reports counts, sizes, and hashes only; it does not expose file bytes."
        ],
        "metadata": {"storage_root_configured": True},
    }


def create_security_event(
    session_factory: sessionmaker[Session],
    payload: SecurityEventCreate,
    *,
    actor: OperationsActor,
    request_ip: str | None = None,
    user_agent: str | None = None,
) -> SecurityEvent:
    with session_scope(session_factory) as session:
        row = SecurityEventORM(
            event_type=payload.event_type,
            severity=payload.severity,
            actor_email=payload.actor_email or actor.email,
            ip_address=payload.ip_address or request_ip,
            user_agent=payload.user_agent or user_agent,
            resource_type=payload.resource_type,
            resource_id=payload.resource_id,
            message=payload.message,
            metadata_json=_json_dump(_sanitize(payload.metadata_json)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="security.event.create",
            message="Security event recorded.",
            entity_type="security_event",
            entity_id=row.id,
            metadata={"event_type": row.event_type, "severity": row.severity},
        )
        return _security_event_to_record(row)


def list_security_events(
    session_factory: sessionmaker[Session],
    *,
    event_type: str | None = None,
    severity: str | None = None,
    actor_email: str | None = None,
    limit: int = 100,
) -> list[SecurityEvent]:
    with session_scope(session_factory) as session:
        stmt = select(SecurityEventORM).order_by(SecurityEventORM.id.desc()).limit(limit)
        if event_type is not None:
            stmt = stmt.where(SecurityEventORM.event_type == event_type)
        if severity is not None:
            stmt = stmt.where(SecurityEventORM.severity == severity)
        if actor_email is not None:
            stmt = stmt.where(SecurityEventORM.actor_email == actor_email.lower())
        return [_security_event_to_record(row) for row in session.scalars(stmt).all()]


def security_summary(session_factory: sessionmaker[Session]) -> SecuritySummary:
    with session_scope(session_factory) as session:
        by_type = {
            str(kind): int(count)
            for kind, count in session.execute(
                select(SecurityEventORM.event_type, func.count(SecurityEventORM.id)).group_by(
                    SecurityEventORM.event_type
                )
            ).all()
        }
        by_severity = {
            str(severity): int(count)
            for severity, count in session.execute(
                select(SecurityEventORM.severity, func.count(SecurityEventORM.id)).group_by(
                    SecurityEventORM.severity
                )
            ).all()
        }
    total = sum(by_type.values())
    warning_count = (
        by_severity.get("warning", 0) + by_severity.get("error", 0) + by_severity.get("critical", 0)
    )
    return SecuritySummary(
        total_events=total,
        counts_by_type=by_type,
        counts_by_severity=by_severity,
        open_warnings=warning_count,
        notes=[_SAFE_NOTE],
    )


def search_audit_events(
    session_factory: sessionmaker[Session],
    *,
    actor: OperationsActor,
    event_type: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    actor_email: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[AuditEventRecord]:
    with session_scope(session_factory) as session:
        stmt = select(AuditEventORM).order_by(AuditEventORM.id.desc()).limit(limit)
        if event_type is not None:
            stmt = stmt.where(AuditEventORM.event_type == event_type)
        if entity_type is not None:
            stmt = stmt.where(AuditEventORM.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditEventORM.entity_id == entity_id)
        if actor_email is not None:
            stmt = stmt.where(AuditEventORM.actor_email == actor_email.lower())
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(AuditEventORM.message.like(pattern))
        rows = session.scalars(stmt).all()
        _audit(
            session,
            actor=actor,
            event_type="admin.audit.search",
            message="Audit log searched.",
            entity_type="audit_event",
            entity_id=None,
            metadata={"event_type": event_type, "entity_type": entity_type, "limit": limit},
        )
        return [_audit_to_record(row) for row in rows]


def create_debug_bundle(
    session_factory: sessionmaker[Session],
    payload: DebugBundleCreate,
    *,
    actor: OperationsActor,
    settings: Settings,
    storage_root: Path,
    openapi_available: bool,
) -> DebugBundle:
    with session_scope(session_factory) as session:
        title = payload.title or f"{payload.scope} debug bundle"
        warnings: list[str] = []
        notes = [_SAFE_NOTE, "Debug bundle content is sanitized and metadata-only."]
        try:
            bundle = _build_safe_bundle_payload(
                session,
                payload=payload,
                settings=settings,
                storage_root=storage_root,
                openapi_available=openapi_available,
            )
            bundle_json = json.dumps(bundle, sort_keys=True, separators=(",", ":"), default=str)
            digest = hashlib.sha256(bundle_json.encode("utf-8")).hexdigest()
            row = DebugBundleORM(
                title=title,
                scope=payload.scope,
                resource_id=payload.resource_id,
                status="created",
                bundle_sha256=digest,
                storage_key=f"debug-bundles/{digest}.json",
                bundle_json=bundle_json,
                warnings_json=_json_dump(warnings),
                notes_json=_json_dump(notes),
                metadata_json=_json_dump(
                    {
                        **_sanitize(payload.metadata_json),
                        "safe_bundle": True,
                        "contains_raw_files": False,
                        "contains_secret_values": False,
                    }
                ),
            )
        except Exception as exc:
            warnings.append(f"Debug bundle generation failed: {type(exc).__name__}")
            row = DebugBundleORM(
                title=title,
                scope=payload.scope,
                resource_id=payload.resource_id,
                status="failed",
                warnings_json=_json_dump(warnings),
                notes_json=_json_dump(notes),
                metadata_json=_json_dump({"safe_bundle": True, "error_type": type(exc).__name__}),
            )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="admin.debug_bundle.create",
            message="Safe debug bundle generated.",
            entity_type="debug_bundle",
            entity_id=row.id,
            metadata={"scope": row.scope, "resource_id": row.resource_id, "status": row.status},
        )
        return _debug_bundle_to_record(row)


def get_debug_bundle(session_factory: sessionmaker[Session], bundle_id: int) -> DebugBundle | None:
    with session_scope(session_factory) as session:
        row = session.get(DebugBundleORM, bundle_id)
        return _debug_bundle_to_record(row) if row is not None else None


def get_debug_bundle_content(
    session_factory: sessionmaker[Session], bundle_id: int
) -> tuple[DebugBundle, bytes] | None:
    with session_scope(session_factory) as session:
        row = session.get(DebugBundleORM, bundle_id)
        if row is None:
            return None
        content = row.bundle_json or json.dumps(
            _debug_bundle_to_record(row).model_dump(mode="json")
        )
        return _debug_bundle_to_record(row), content.encode("utf-8")


def _build_safe_bundle_payload(
    session: Session,
    *,
    payload: DebugBundleCreate,
    settings: Settings,
    storage_root: Path,
    openapi_available: bool,
) -> dict[str, Any]:
    resource_id = _coerce_int(payload.resource_id)
    jobs = _relevant_jobs(session, payload.scope, resource_id)
    sessions = _relevant_sessions(session, payload.scope, resource_id)
    artifacts = _relevant_artifacts(session, payload.scope, resource_id)
    file_hashes = (
        _file_hashes(session, payload.scope, resource_id) if payload.include_file_hashes else []
    )
    audit_events = (
        _recent_audit_payloads(session, payload.scope, resource_id)
        if payload.include_recent_audit_events
        else []
    )
    recent_errors = _recent_error_payloads(session)
    status = {
        "backend_version": settings.release_version,
        "environment": settings.app_env,
        "openapi_available": openapi_available,
        "storage_root_exists": storage_root.exists(),
    }
    return cast(
        dict[str, Any],
        _sanitize(
            {
                "safe_bundle": True,
                "created_at": utcnow().isoformat(),
                "scope": payload.scope,
                "resource_id": payload.resource_id,
                "backend_version": settings.release_version,
                "system_status": status,
                "job_ids": [job["id"] for job in jobs],
                "jobs": jobs,
                "session_ids": [item["id"] for item in sessions],
                "sessions": sessions,
                "artifact_ids": [item["id"] for item in artifacts],
                "artifacts": artifacts,
                "file_hashes": file_hashes,
                "recent_audit_events": audit_events,
                "recent_errors": recent_errors,
                "warnings": [],
                "notes": [_SAFE_NOTE],
                "metadata": {"contains_raw_files": False, "contains_secret_values": False},
            }
        ),
    )


def _relevant_jobs(session: Session, scope: str, resource_id: int | None) -> list[dict[str, Any]]:
    stmt = select(AnalysisJobORM).order_by(AnalysisJobORM.id.desc()).limit(25)
    if scope == "job" and resource_id is not None:
        stmt = stmt.where(AnalysisJobORM.id == resource_id)
    elif scope == "session" and resource_id is not None:
        stmt = stmt.where(AnalysisJobORM.session_id == resource_id)
    rows = session.scalars(stmt).all()
    return [
        {
            "id": row.id,
            "session_id": row.session_id,
            "project_id": row.project_id,
            "job_type": row.job_type,
            "status": row.status,
            "progress_percent": float(row.progress_percent),
            "created_at": row.created_at.isoformat(),
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "error_present": bool(row.error_message),
        }
        for row in rows
    ]


def _relevant_sessions(
    session: Session, scope: str, resource_id: int | None
) -> list[dict[str, Any]]:
    stmt = select(SpectraCheckSessionORM).order_by(SpectraCheckSessionORM.id.desc()).limit(25)
    if scope == "session" and resource_id is not None:
        stmt = stmt.where(SpectraCheckSessionORM.id == resource_id)
    elif scope == "project" and resource_id is not None:
        stmt = stmt.where(SpectraCheckSessionORM.project_id == resource_id)
    rows = session.scalars(stmt).all()
    return [
        {
            "id": row.id,
            "project_id": row.project_id,
            "sample_pk": row.sample_pk,
            "sample_id": row.sample_id,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
        for row in rows
    ]


def _relevant_artifacts(
    session: Session, scope: str, resource_id: int | None
) -> list[dict[str, Any]]:
    stmt = select(ArtifactRecordORM).order_by(ArtifactRecordORM.id.desc()).limit(25)
    if scope == "job" and resource_id is not None:
        stmt = stmt.where(ArtifactRecordORM.job_id == resource_id)
    elif scope == "session" and resource_id is not None:
        stmt = stmt.where(ArtifactRecordORM.session_id == resource_id)
    rows = session.scalars(stmt).all()
    return [
        {
            "id": row.id,
            "job_id": row.job_id,
            "session_id": row.session_id,
            "artifact_type": row.artifact_type,
            "content_type": row.content_type,
            "sha256": row.sha256,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def _file_hashes(session: Session, scope: str, resource_id: int | None) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(ManagedFileRecordORM).order_by(ManagedFileRecordORM.id.desc()).limit(25)
    ).all()
    raw_rows = session.scalars(
        select(RawArchiveORM).order_by(RawArchiveORM.id.desc()).limit(25)
    ).all()
    if scope == "session" and resource_id is not None:
        linked_ids = {
            int(file_id)
            for file_id in session.scalars(
                select(ManagedFileRecordORM.id).join(
                    ArtifactRecordORM,
                    ArtifactRecordORM.sha256 == ManagedFileRecordORM.sha256,
                    isouter=True,
                )
            ).all()
        }
        rows = [row for row in rows if row.id in linked_ids]
    return [
        {
            "kind": "managed_file",
            "id": row.id,
            "file_kind": row.file_kind,
            "sha256": row.sha256,
            "size_bytes": row.file_size_bytes,
            "storage_backend": row.storage_backend,
        }
        for row in rows
    ] + [
        {
            "kind": "raw_archive",
            "id": row.id,
            "vendor_detected": row.vendor_detected,
            "sha256": row.sha256,
            "size_bytes": row.byte_size,
            "immutable": row.immutable,
        }
        for row in raw_rows
    ]


def _recent_audit_payloads(
    session: Session, scope: str, resource_id: int | None
) -> list[dict[str, Any]]:
    stmt = select(AuditEventORM).order_by(AuditEventORM.id.desc()).limit(50)
    if scope in {"job", "report", "session", "project", "sample"} and resource_id is not None:
        stmt = stmt.where(AuditEventORM.entity_id == resource_id)
    return [_safe_audit_payload(row) for row in session.scalars(stmt).all()]


def _recent_error_payloads(session: Session) -> list[dict[str, Any]]:
    job_errors = [
        {
            "source": "analysis_job",
            "id": row.id,
            "status": row.status,
            "job_type": row.job_type,
            "error_present": True,
            "created_at": row.created_at.isoformat(),
        }
        for row in session.scalars(
            select(AnalysisJobORM)
            .where(AnalysisJobORM.error_message.is_not(None))
            .order_by(AnalysisJobORM.id.desc())
            .limit(20)
        ).all()
    ]
    audit_errors = [
        {
            "source": "audit_event",
            "id": row.id,
            "event_type": row.event_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "created_at": row.created_at.isoformat(),
        }
        for row in session.scalars(
            select(AuditEventORM)
            .where(AuditEventORM.event_type.like("%error%"))
            .order_by(AuditEventORM.id.desc())
            .limit(20)
        ).all()
    ]
    return job_errors + audit_errors


def _security_event_to_record(row: SecurityEventORM) -> SecurityEvent:
    return SecurityEvent(
        id=row.id,
        event_type=row.event_type,  # type: ignore[arg-type]
        severity=row.severity,  # type: ignore[arg-type]
        actor_email=row.actor_email,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        message=row.message,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _debug_bundle_to_record(row: DebugBundleORM) -> DebugBundle:
    return DebugBundle(
        id=row.id,
        title=row.title,
        scope=row.scope,  # type: ignore[arg-type]
        resource_id=row.resource_id,
        status=row.status,  # type: ignore[arg-type]
        bundle_sha256=row.bundle_sha256,
        storage_key=row.storage_key,
        created_at=row.created_at,
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_list(row.notes_json),
        metadata_json=_json_dict(row.metadata_json),
    )


def _audit_to_record(row: AuditEventORM) -> AuditEventRecord:
    metadata = _json_dict(row.metadata_json)
    tenant_id = metadata.get("tenant_id")
    before_state = metadata.get("before_state")
    after_state = metadata.get("after_state")
    return AuditEventRecord(
        id=row.id,
        created_at=row.created_at,
        event_type=row.event_type,
        message=row.message,
        tenant_id=tenant_id if isinstance(tenant_id, int) else None,
        action=_metadata_str(metadata, "action"),
        module=_metadata_str(metadata, "module"),
        actor_user_id=row.actor_user_id,
        actor_email=row.actor_email,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        before_state=before_state if isinstance(before_state, dict) else None,
        after_state=after_state if isinstance(after_state, dict) else None,
        reason=_metadata_str(metadata, "reason"),
        correlation_id=_metadata_str(metadata, "correlation_id"),
        metadata=metadata,
    )


def _metadata_str(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _safe_audit_payload(row: AuditEventORM) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _sanitize(
            {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "event_type": row.event_type,
                "message": row.message,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "actor_email_present": bool(row.actor_email),
                "metadata": _json_dict(row.metadata_json),
            }
        ),
    )


def _audit(
    session: Session,
    *,
    actor: OperationsActor,
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
            metadata_json=_json_dump(_sanitize(metadata or {})),
        )
    )


def _metric(
    name: str, value: int | float, unit: str | None = None, status: str = "ok"
) -> OperationalMetric:
    return OperationalMetric(name=name, value=float(value), unit=unit, status=status)


def _count(session: Session, model: type[Any]) -> int:
    return int(session.scalar(select(func.count(model.id))) or 0)


def _count_where(session: Session, model: type[Any], criterion: Any) -> int:
    return int(session.scalar(select(func.count(model.id)).where(criterion)) or 0)


def _aggregate_status(checks: list[DependencyCheck]) -> SystemHealthStatus:
    statuses = {check.status for check in checks}
    if "error" in statuses:
        return "unhealthy"
    if "warning" in statuses or "unknown" in statuses:
        return "degraded"
    return "healthy"


def _data_mode_for_health_status(status: SystemHealthStatus) -> DataMode:
    if status == "healthy":
        return "live"
    if status == "degraded":
        return "partially_synced"
    return "unavailable"


def _unknown_check(name: str) -> DependencyCheck:
    return DependencyCheck(name=name, status="unknown")


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def _local_dev_warnings(local_auth_disabled: bool) -> list[str]:
    return ["Authentication is disabled for local development."] if local_auth_disabled else []


def _env_present(name: str, settings: Settings) -> bool:
    if name == "DATABASE_URL":
        return bool(settings.database_url)
    if name == "API_KEY":
        return bool(settings.api_key)
    return bool(os.getenv(name))


def _coerce_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_str = str(key)
            if any(token in key_str.upper() for token in SECRET_NAME_TOKENS):
                sanitized[key_str] = "[redacted]"
            else:
                sanitized[key_str] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value


def _json_dump(value: Any) -> str:
    return json.dumps(
        value if value is not None else {}, sort_keys=True, separators=(",", ":"), default=str
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
