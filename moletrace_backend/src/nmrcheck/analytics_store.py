from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    AnalyticsSummary,
    AutomationTaskDefinition,
    AutomationTaskDefinitionCreate,
    AutomationTaskDefinitionUpdate,
    RenewalValueReport,
    RenewalValueReportCreate,
    RoiSnapshot,
    UsageEvent,
    UsageEventCreate,
    UserFeedbackEvent,
    UserFeedbackEventCreate,
    WorkflowAnalyticsSummary,
)
from .orm import (
    AuditEventORM,
    AutomationRunMetricORM,
    AutomationTaskDefinitionORM,
    RenewalValueReportORM,
    RoiSnapshotORM,
    UsageEventORM,
    UserFeedbackEventORM,
    utcnow,
)


class AnalyticsError(ValueError):
    pass


@dataclass(frozen=True)
class AnalyticsActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


_SAFE_NOTE = (
    "Analytics records store non-sensitive metadata and references only; they do not include "
    "raw spectra, uploaded file contents, secrets, full SMILES, or raw NMR/MS text."
)

_REDACTED = "[redacted]"
_SENSITIVE_KEY_TOKENS = (
    "PASSWORD",
    "PASSWD",
    "SECRET",
    "TOKEN",
    "API_KEY",
    "CREDENTIAL",
    "AUTHORIZATION",
    "PRIVATE_NOTE",
    "RAW_NMR",
    "RAW_MS",
    "RAW_SPECTR",
    "SPECTRUM_TEXT",
    "SPECTRA_TEXT",
    "NMR_TEXT",
    "MS_TEXT",
    "PEAK_LIST_TEXT",
    "FILE_CONTENT",
    "FILE_CONTENTS",
    "UPLOADED_FILE",
    "SMILES",
    "MOLFILE",
    "SDF",
)
_RAW_PAYLOAD_MARKERS = ("##TITLE=", "##JCAMP", "BEGIN IONS", "END IONS", "M  END")
_NUMERIC_TOKEN_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?")


DEFAULT_AUTOMATION_TASKS: tuple[dict[str, Any], ...] = (
    {
        "task_key": "nmr_processed_preview",
        "name": "NMR processed preview",
        "category": "nmr",
        "default_minutes_saved": 5.0,
        "description": "Preview processed NMR metadata and plot-ready summaries.",
    },
    {
        "task_key": "nmr_raw_fid_metadata_preview",
        "name": "NMR raw FID metadata preview",
        "category": "nmr",
        "default_minutes_saved": 8.0,
        "description": "Inspect raw FID package metadata without exposing raw file content.",
    },
    {
        "task_key": "nmr_raw_fid_processing",
        "name": "NMR raw FID processing",
        "category": "nmr",
        "default_minutes_saved": 20.0,
        "description": "Process raw FID uploads into reviewable derived spectrum metadata.",
    },
    {
        "task_key": "candidate_specific_nmr_matching",
        "name": "Candidate-specific NMR matching",
        "category": "nmr",
        "default_minutes_saved": 30.0,
        "description": "Compare predicted and observed NMR evidence for a candidate.",
    },
    {
        "task_key": "hrms_exact_mass_matching",
        "name": "HRMS exact mass matching",
        "category": "ms",
        "default_minutes_saved": 10.0,
        "description": "Rank formula or candidate support using exact-mass evidence.",
    },
    {
        "task_key": "msms_annotation",
        "name": "MS/MS annotation",
        "category": "ms",
        "default_minutes_saved": 25.0,
        "description": "Annotate processed MS/MS peaks against candidate fragments.",
    },
    {
        "task_key": "fragmentation_tree_reasoning",
        "name": "Fragmentation-tree reasoning",
        "category": "ms",
        "default_minutes_saved": 35.0,
        "description": (
            "Build reviewable fragmentation-tree reasoning from processed MS/MS evidence."
        ),
    },
    {
        "task_key": "lcms_import_bridge",
        "name": "LCMS import bridge",
        "category": "lcms",
        "default_minutes_saved": 15.0,
        "description": "Normalize LCMS import metadata and feature-table references.",
    },
    {
        "task_key": "lcms_feature_detection",
        "name": "LCMS feature detection",
        "category": "lcms",
        "default_minutes_saved": 30.0,
        "description": "Detect LCMS features from non-sensitive processed inputs.",
    },
    {
        "task_key": "lcms_feature_grouping_blank_subtraction",
        "name": "LCMS grouping and blank subtraction",
        "category": "lcms",
        "default_minutes_saved": 40.0,
        "description": "Group LCMS features and account for blank-subtraction workflow steps.",
    },
    {
        "task_key": "lcms_feature_family_consensus",
        "name": "LCMS feature-family consensus",
        "category": "lcms",
        "default_minutes_saved": 45.0,
        "description": "Summarize LCMS feature-family consensus evidence for review.",
    },
    {
        "task_key": "unified_evidence_synthesis",
        "name": "Unified evidence synthesis",
        "category": "workflow",
        "default_minutes_saved": 30.0,
        "description": "Build unified evidence summaries across available review layers.",
    },
    {
        "task_key": "report_composer",
        "name": "Report composer",
        "category": "report",
        "default_minutes_saved": 60.0,
        "description": "Compose cautious, review-ready report drafts from existing evidence.",
    },
    {
        "task_key": "qc_readiness_assessment",
        "name": "QC readiness assessment",
        "category": "qc",
        "default_minutes_saved": 15.0,
        "description": "Assess readiness and warnings for files, artifacts, evidence, or sessions.",
    },
    {
        "task_key": "human_review_task_completion",
        "name": "Human review task completion",
        "category": "review",
        "default_minutes_saved": 10.0,
        "description": "Track completed human review tasks without storing private review notes.",
    },
)


def ensure_default_tasks(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as session:
        _ensure_default_tasks(session)


def create_usage_event(
    session_factory: sessionmaker[Session],
    payload: UsageEventCreate,
    *,
    actor: AnalyticsActor,
) -> UsageEvent:
    with session_scope(session_factory) as session:
        _ensure_default_tasks(session)
        metadata, warnings = _sanitize_metadata(payload.metadata_json)
        task_key = _resolve_task_key(payload.event_type, metadata)
        minutes_saved = _resolve_minutes_saved(session, payload, task_key)
        if minutes_saved is not None and minutes_saved > 0:
            metadata.setdefault("task_key", task_key)
        user_email = (payload.user_email or actor.email or "").strip().lower() or None
        row = UsageEventORM(
            event_type=payload.event_type,
            project_id=payload.project_id,
            sample_id=payload.sample_id,
            session_id=payload.session_id,
            workflow_run_id=payload.workflow_run_id,
            job_id=payload.job_id,
            artifact_id=payload.artifact_id,
            report_id=payload.report_id,
            user_email=user_email,
            status=payload.status,
            duration_seconds=payload.duration_seconds,
            estimated_minutes_saved=minutes_saved,
            event_source=payload.event_source,
            metadata_json=_json_dump(metadata),
        )
        session.add(row)
        session.flush()
        if minutes_saved is not None and minutes_saved > 0:
            metric = AutomationRunMetricORM(
                task_key=task_key,
                project_id=payload.project_id,
                session_id=payload.session_id,
                workflow_run_id=payload.workflow_run_id,
                job_id=payload.job_id,
                status=payload.status or "succeeded",
                minutes_saved=minutes_saved,
                metadata_json=_json_dump(
                    {
                        "usage_event_id": row.id,
                        "event_type": payload.event_type,
                        "source": payload.event_source,
                    }
                ),
            )
            session.add(metric)
        _audit(
            session,
            actor=actor,
            event_type="analytics.usage_event.create",
            message="Usage analytics event recorded.",
            entity_type="usage_event",
            entity_id=row.id,
            metadata={
                "event_type": row.event_type,
                "project_id": row.project_id,
                "session_id": row.session_id,
                "minutes_saved": minutes_saved,
            },
        )
        return _usage_event_to_record(row, warnings=warnings)


def list_usage_events(
    session_factory: sessionmaker[Session],
    *,
    event_type: str | None = None,
    project_id: int | None = None,
    session_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[UsageEvent]:
    with session_scope(session_factory) as session:
        stmt = select(UsageEventORM).order_by(UsageEventORM.id.desc()).limit(limit)
        if event_type is not None:
            stmt = stmt.where(UsageEventORM.event_type == event_type)
        if project_id is not None:
            stmt = stmt.where(UsageEventORM.project_id == project_id)
        if session_id is not None:
            stmt = stmt.where(UsageEventORM.session_id == session_id)
        if status is not None:
            stmt = stmt.where(UsageEventORM.status == status)
        return [_usage_event_to_record(row) for row in session.scalars(stmt).all()]


def list_automation_tasks(
    session_factory: sessionmaker[Session],
    *,
    category: str | None = None,
    enabled: bool | None = None,
) -> list[AutomationTaskDefinition]:
    with session_scope(session_factory) as session:
        _ensure_default_tasks(session)
        stmt = select(AutomationTaskDefinitionORM).order_by(
            AutomationTaskDefinitionORM.task_key.asc()
        )
        if category is not None:
            stmt = stmt.where(AutomationTaskDefinitionORM.category == category)
        if enabled is not None:
            stmt = stmt.where(AutomationTaskDefinitionORM.enabled.is_(enabled))
        return [_task_to_record(row) for row in session.scalars(stmt).all()]


def create_automation_task(
    session_factory: sessionmaker[Session],
    payload: AutomationTaskDefinitionCreate,
    *,
    actor: AnalyticsActor,
) -> AutomationTaskDefinition:
    with session_scope(session_factory) as session:
        _ensure_default_tasks(session)
        metadata, _warnings = _sanitize_metadata(payload.metadata_json)
        row = AutomationTaskDefinitionORM(
            task_key=payload.task_key,
            name=payload.name,
            category=payload.category,
            default_minutes_saved=payload.default_minutes_saved,
            description=payload.description,
            enabled=payload.enabled,
            metadata_json=_json_dump(metadata),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise AnalyticsError(f"Automation task already exists: {payload.task_key}") from exc
        _audit(
            session,
            actor=actor,
            event_type="analytics.automation_task.create",
            message="Automation task definition created.",
            entity_type="automation_task_definition",
            entity_id=row.id,
            metadata={"task_key": row.task_key, "category": row.category},
        )
        return _task_to_record(row)


def update_automation_task(
    session_factory: sessionmaker[Session],
    task_id: int,
    payload: AutomationTaskDefinitionUpdate,
    *,
    actor: AnalyticsActor,
) -> AutomationTaskDefinition | None:
    with session_scope(session_factory) as session:
        _ensure_default_tasks(session)
        row = session.get(AutomationTaskDefinitionORM, task_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        if "metadata_json" in update:
            metadata, _warnings = _sanitize_metadata(update["metadata_json"] or {})
            row.metadata_json = _json_dump(metadata)
        for field in ("name", "category", "default_minutes_saved", "description", "enabled"):
            if field in update:
                setattr(row, field, update[field])
        row.updated_at = utcnow()
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="analytics.automation_task.update",
            message="Automation task definition updated.",
            entity_type="automation_task_definition",
            entity_id=row.id,
            metadata={"task_key": row.task_key},
        )
        return _task_to_record(row)


def analytics_summary(session_factory: sessionmaker[Session]) -> AnalyticsSummary:
    with session_scope(session_factory) as session:
        _ensure_default_tasks(session)
        roi = _compute_roi(session, scope="global", scope_id=None)
        by_event = {
            str(event_type): int(count)
            for event_type, count in session.execute(
                select(UsageEventORM.event_type, func.count(UsageEventORM.id)).group_by(
                    UsageEventORM.event_type
                )
            ).all()
        }
        by_status = {
            str(status or "unknown"): int(count)
            for status, count in session.execute(
                select(UsageEventORM.status, func.count(UsageEventORM.id)).group_by(
                    UsageEventORM.status
                )
            ).all()
        }
        total_events = int(session.scalar(select(func.count(UsageEventORM.id))) or 0)
    return AnalyticsSummary(
        total_events=total_events,
        tasks_automated=roi["tasks_automated"],
        total_minutes_saved=roi["total_minutes_saved"],
        total_hours_saved=roi["total_hours_saved"],
        reports_generated=roi["reports_generated"],
        workflows_completed=roi["workflows_completed"],
        analyses_completed=roi["analyses_completed"],
        failed_jobs=roi["failed_jobs"],
        qc_warnings=roi["qc_warnings"],
        counts_by_event_type=by_event,
        counts_by_status=by_status,
        notes=[_SAFE_NOTE],
        metadata={"default_tasks_seeded": True},
    )


def roi_snapshot(
    session_factory: sessionmaker[Session],
    *,
    scope: str = "global",
    scope_id: str | None = None,
    period_start: Any | None = None,
    period_end: Any | None = None,
) -> RoiSnapshot:
    with session_scope(session_factory) as session:
        _ensure_default_tasks(session)
        end = period_end or utcnow()
        start = period_start or (end - timedelta(days=30))
        roi = _compute_roi(
            session,
            scope=scope,
            scope_id=scope_id,
            period_start=start,
            period_end=end,
        )
        row = RoiSnapshotORM(
            scope=scope,
            scope_id=scope_id,
            period_start=start,
            period_end=end,
            tasks_automated=roi["tasks_automated"],
            total_minutes_saved=roi["total_minutes_saved"],
            total_hours_saved=roi["total_hours_saved"],
            reports_generated=roi["reports_generated"],
            workflows_completed=roi["workflows_completed"],
            analyses_completed=roi["analyses_completed"],
            review_tasks_completed=roi["review_tasks_completed"],
            failed_jobs=roi["failed_jobs"],
            qc_warnings=roi["qc_warnings"],
            metadata_json=_json_dump({"safe_metadata_only": True}),
        )
        session.add(row)
        session.flush()
        return _roi_to_record(row)


def workflow_summary(session_factory: sessionmaker[Session]) -> WorkflowAnalyticsSummary:
    with session_scope(session_factory) as session:
        started = _count_events(session, event_like="workflow", status="started")
        completed = _count_events(session, event_like="workflow", status="succeeded")
        failed = _count_events(session, event_like="workflow", status="failed")
        minutes = _sum_minutes(session, event_like="workflow")
    return WorkflowAnalyticsSummary(
        workflows_started=started,
        workflows_completed=completed,
        workflows_failed=failed,
        total_minutes_saved=minutes,
        notes=[_SAFE_NOTE],
        metadata={"source": "usage_events"},
    )


def create_feedback(
    session_factory: sessionmaker[Session],
    payload: UserFeedbackEventCreate,
    *,
    actor: AnalyticsActor,
) -> UserFeedbackEvent:
    with session_scope(session_factory) as session:
        metadata, warnings = _sanitize_metadata(payload.metadata_json)
        comment = _sanitize_comment(payload.comment)
        row = UserFeedbackEventORM(
            project_id=payload.project_id,
            session_id=payload.session_id,
            user_email=(payload.user_email or actor.email or "").strip().lower() or None,
            feedback_type=payload.feedback_type,
            rating=payload.rating,
            comment=comment,
            metadata_json=_json_dump(metadata),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="analytics.feedback.create",
            message="Analytics feedback event recorded.",
            entity_type="user_feedback_event",
            entity_id=row.id,
            metadata={"feedback_type": row.feedback_type, "project_id": row.project_id},
        )
        return _feedback_to_record(row, warnings=warnings)


def list_feedback(
    session_factory: sessionmaker[Session],
    *,
    feedback_type: str | None = None,
    project_id: int | None = None,
    session_id: int | None = None,
    limit: int = 100,
) -> list[UserFeedbackEvent]:
    with session_scope(session_factory) as session:
        stmt = select(UserFeedbackEventORM).order_by(UserFeedbackEventORM.id.desc()).limit(limit)
        if feedback_type is not None:
            stmt = stmt.where(UserFeedbackEventORM.feedback_type == feedback_type)
        if project_id is not None:
            stmt = stmt.where(UserFeedbackEventORM.project_id == project_id)
        if session_id is not None:
            stmt = stmt.where(UserFeedbackEventORM.session_id == session_id)
        return [_feedback_to_record(row) for row in session.scalars(stmt).all()]


def create_renewal_report(
    session_factory: sessionmaker[Session],
    payload: RenewalValueReportCreate,
    *,
    actor: AnalyticsActor,
) -> RenewalValueReport:
    with session_scope(session_factory) as session:
        _ensure_default_tasks(session)
        end = payload.period_end or utcnow()
        start = payload.period_start or (end - timedelta(days=30))
        metadata, warnings = _sanitize_metadata(payload.metadata_json)
        scope_id = payload.scope_id
        roi = _compute_roi(
            session,
            scope=payload.scope,
            scope_id=scope_id,
            period_start=start,
            period_end=end,
        )
        summary = {
            "scope": payload.scope,
            "scope_id": scope_id,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "tasks_automated": roi["tasks_automated"],
            "total_hours_saved": roi["total_hours_saved"],
            "reports_generated": roi["reports_generated"],
            "workflows_completed": roi["workflows_completed"],
            "analyses_completed": roi["analyses_completed"],
        }
        report_payload = {
            "summary": summary,
            "value_indicators": {
                "total_minutes_saved": roi["total_minutes_saved"],
                "review_tasks_completed": roi["review_tasks_completed"],
                "failed_jobs": roi["failed_jobs"],
                "qc_warnings": roi["qc_warnings"],
            },
            "privacy": {
                "contains_raw_spectra": False,
                "contains_uploaded_file_contents": False,
                "contains_secrets": False,
                "contains_full_smiles": False,
                "contains_raw_nmr_ms_text": False,
            },
            "notes": [_SAFE_NOTE],
        }
        report_json_text = _json_dump(report_payload)
        digest = hashlib.sha256(report_json_text.encode("utf-8")).hexdigest()
        title = payload.title or f"{payload.scope.title()} automation value report"
        row = RenewalValueReportORM(
            scope=payload.scope,
            scope_id=scope_id,
            period_start=start,
            period_end=end,
            title=title,
            summary_json=_json_dump(summary),
            report_json=report_json_text,
            report_html=_renewal_html(title, report_payload),
            report_sha256=digest,
            metadata_json=_json_dump({**metadata, "safe_customer_summary": True}),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="analytics.renewal_report.create",
            message="Safe renewal value report generated.",
            entity_type="renewal_value_report",
            entity_id=row.id,
            metadata={"scope": row.scope, "scope_id": row.scope_id, "report_sha256": digest},
        )
        return _renewal_to_record(row, warnings=warnings)


def get_renewal_report(
    session_factory: sessionmaker[Session], report_id: int
) -> RenewalValueReport | None:
    with session_scope(session_factory) as session:
        row = session.get(RenewalValueReportORM, report_id)
        return _renewal_to_record(row) if row is not None else None


def _ensure_default_tasks(session: Session) -> None:
    existing_count = int(session.scalar(select(func.count(AutomationTaskDefinitionORM.id))) or 0)
    if existing_count:
        return
    for task in DEFAULT_AUTOMATION_TASKS:
        session.add(
            AutomationTaskDefinitionORM(
                task_key=task["task_key"],
                name=task["name"],
                category=task["category"],
                default_minutes_saved=task["default_minutes_saved"],
                description=task["description"],
                enabled=True,
                metadata_json=_json_dump({"default_seed": True}),
            )
        )
    session.flush()


def _resolve_task_key(event_type: str, metadata: dict[str, Any]) -> str:
    task_key = metadata.get("task_key") or event_type
    return str(task_key).strip()[:120] or event_type[:120]


def _resolve_minutes_saved(
    session: Session,
    payload: UsageEventCreate,
    task_key: str,
) -> float | None:
    if payload.status in {"failed", "canceled"}:
        return 0.0
    if payload.estimated_minutes_saved is not None:
        return float(payload.estimated_minutes_saved)
    task = session.scalar(
        select(AutomationTaskDefinitionORM).where(
            AutomationTaskDefinitionORM.task_key == task_key,
            AutomationTaskDefinitionORM.enabled.is_(True),
        )
    )
    if task is None:
        return None
    return float(task.default_minutes_saved)


def _compute_roi(
    session: Session,
    *,
    scope: str,
    scope_id: str | None,
    period_start: Any | None = None,
    period_end: Any | None = None,
) -> dict[str, Any]:
    stmt = select(UsageEventORM)
    if period_start is not None:
        stmt = stmt.where(UsageEventORM.created_at >= period_start)
    if period_end is not None:
        stmt = stmt.where(UsageEventORM.created_at <= period_end)
    stmt = _apply_scope(stmt, scope=scope, scope_id=scope_id)
    rows = session.scalars(stmt).all()
    minutes = sum(float(row.estimated_minutes_saved or 0.0) for row in rows)
    completed_rows = [row for row in rows if row.status in {None, "succeeded", "warning"}]
    return {
        "tasks_automated": sum(
            1 for row in completed_rows if (row.estimated_minutes_saved or 0) > 0
        ),
        "total_minutes_saved": round(minutes, 2),
        "total_hours_saved": round(minutes / 60.0, 2),
        "reports_generated": sum(
            1
            for row in rows
            if row.status in {None, "succeeded"}
            and (row.report_id is not None or "report" in row.event_type.lower())
        ),
        "workflows_completed": sum(
            1
            for row in rows
            if row.status == "succeeded"
            and (row.workflow_run_id is not None or "workflow" in row.event_type.lower())
        ),
        "analyses_completed": sum(
            1
            for row in rows
            if row.status == "succeeded"
            and (row.job_id is not None or "analysis" in row.event_type.lower())
        ),
        "review_tasks_completed": sum(
            1
            for row in rows
            if row.status == "succeeded" and "review" in row.event_type.lower()
        ),
        "failed_jobs": sum(1 for row in rows if row.status == "failed" and row.job_id is not None),
        "qc_warnings": sum(
            1
            for row in rows
            if row.status == "warning"
            and (
                "qc" in row.event_type.lower()
                or row.event_type.lower().startswith("quality")
            )
        ),
    }


def _apply_scope(stmt: Any, *, scope: str, scope_id: str | None) -> Any:
    if scope == "project" and scope_id is not None:
        return stmt.where(UsageEventORM.project_id == _coerce_int(scope_id))
    if scope == "session" and scope_id is not None:
        return stmt.where(UsageEventORM.session_id == _coerce_int(scope_id))
    if scope == "user" and scope_id is not None:
        return stmt.where(UsageEventORM.user_email == scope_id.strip().lower())
    return stmt


def _count_events(
    session: Session,
    *,
    event_like: str | None = None,
    status: str | None = None,
) -> int:
    stmt = select(func.count(UsageEventORM.id))
    if event_like is not None:
        stmt = stmt.where(UsageEventORM.event_type.like(f"%{event_like}%"))
    if status is not None:
        stmt = stmt.where(UsageEventORM.status == status)
    return int(session.scalar(stmt) or 0)


def _sum_minutes(session: Session, *, event_like: str | None = None) -> float:
    stmt = select(func.sum(UsageEventORM.estimated_minutes_saved))
    if event_like is not None:
        stmt = stmt.where(UsageEventORM.event_type.like(f"%{event_like}%"))
    return round(float(session.scalar(stmt) or 0.0), 2)


def _usage_event_to_record(row: UsageEventORM, *, warnings: list[str] | None = None) -> UsageEvent:
    metadata = _json_dict(row.metadata_json)
    response_warnings = list(warnings or [])
    if metadata.get("_sanitized_fields") and not response_warnings:
        response_warnings.append("Sensitive analytics metadata was redacted.")
    return UsageEvent(
        id=row.id,
        event_type=row.event_type,
        project_id=row.project_id,
        sample_id=row.sample_id,
        session_id=row.session_id,
        workflow_run_id=row.workflow_run_id,
        job_id=row.job_id,
        artifact_id=row.artifact_id,
        report_id=row.report_id,
        user_email=row.user_email,
        status=row.status,  # type: ignore[arg-type]
        duration_seconds=row.duration_seconds,
        estimated_minutes_saved=row.estimated_minutes_saved,
        event_source=row.event_source,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=metadata,
        warnings=response_warnings,
        notes=[_SAFE_NOTE],
    )


def _task_to_record(row: AutomationTaskDefinitionORM) -> AutomationTaskDefinition:
    return AutomationTaskDefinition(
        id=row.id,
        task_key=row.task_key,
        name=row.name,
        category=row.category,  # type: ignore[arg-type]
        default_minutes_saved=row.default_minutes_saved,
        description=row.description,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
    )


def _roi_to_record(row: RoiSnapshotORM) -> RoiSnapshot:
    return RoiSnapshot(
        id=row.id,
        scope=row.scope,  # type: ignore[arg-type]
        scope_id=row.scope_id,
        period_start=row.period_start,
        period_end=row.period_end,
        tasks_automated=row.tasks_automated,
        total_minutes_saved=row.total_minutes_saved,
        total_hours_saved=row.total_hours_saved,
        reports_generated=row.reports_generated,
        workflows_completed=row.workflows_completed,
        analyses_completed=row.analyses_completed,
        review_tasks_completed=row.review_tasks_completed,
        failed_jobs=row.failed_jobs,
        qc_warnings=row.qc_warnings,
        metadata_json=_json_dict(row.metadata_json),
        created_at=row.created_at,
        notes=[_SAFE_NOTE],
    )


def _feedback_to_record(
    row: UserFeedbackEventORM, *, warnings: list[str] | None = None
) -> UserFeedbackEvent:
    return UserFeedbackEvent(
        id=row.id,
        project_id=row.project_id,
        session_id=row.session_id,
        user_email=row.user_email,
        feedback_type=row.feedback_type,  # type: ignore[arg-type]
        rating=row.rating,
        comment=row.comment,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings or [],
        notes=[_SAFE_NOTE],
    )


def _renewal_to_record(
    row: RenewalValueReportORM, *, warnings: list[str] | None = None
) -> RenewalValueReport:
    return RenewalValueReport(
        id=row.id,
        scope=row.scope,  # type: ignore[arg-type]
        scope_id=row.scope_id,
        period_start=row.period_start,
        period_end=row.period_end,
        title=row.title,
        summary_json=_json_dict(row.summary_json),
        report_json=_json_dict(row.report_json),
        report_html=row.report_html,
        report_sha256=row.report_sha256,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings or [],
        notes=[_SAFE_NOTE],
    )


def _audit(
    session: Session,
    *,
    actor: AnalyticsActor,
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
            metadata_json=_json_dump(_sanitize_metadata(metadata or {})[0]),
        )
    )


def _sanitize_metadata(value: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    redacted_fields: list[str] = []
    sanitized = _sanitize_mapping(value, redacted_fields, path=())
    warnings = []
    if redacted_fields:
        sanitized["_sanitized_fields"] = sorted(set(redacted_fields))
        warnings.append("Sensitive analytics metadata was redacted.")
    return sanitized, warnings


def _sanitize_mapping(
    value: dict[str, Any],
    redacted_fields: list[str],
    *,
    path: tuple[str, ...],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in value.items():
        key_str = str(key)
        item_path = (*path, key_str)
        if _is_sensitive_key(key_str):
            output[key_str] = _REDACTED
            redacted_fields.append(".".join(item_path))
        else:
            output[key_str] = _sanitize_value(item, redacted_fields, path=item_path)
    return output


def _sanitize_value(value: Any, redacted_fields: list[str], *, path: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return _sanitize_mapping(value, redacted_fields, path=path)
    if isinstance(value, list):
        return [
            _sanitize_value(item, redacted_fields, path=(*path, str(index)))
            for index, item in enumerate(value[:100])
        ]
    if isinstance(value, tuple):
        return [
            _sanitize_value(item, redacted_fields, path=(*path, str(index)))
            for index, item in enumerate(value[:100])
        ]
    if isinstance(value, str):
        if _looks_like_raw_payload(value):
            redacted_fields.append(".".join(path))
            return _REDACTED
        if len(value) > 1000:
            return value[:1000] + "...[truncated]"
    return value


def _is_sensitive_key(key: str) -> bool:
    key_upper = key.upper().replace("-", "_")
    return any(token in key_upper for token in _SENSITIVE_KEY_TOKENS)


def _looks_like_raw_payload(value: str) -> bool:
    if any(marker in value for marker in _RAW_PAYLOAD_MARKERS):
        return True
    if len(value) < 250:
        return False
    if value.count("\n") >= 4 and len(_NUMERIC_TOKEN_RE.findall(value)) >= 40:
        return True
    return False


def _sanitize_comment(comment: str | None) -> str | None:
    if comment is None:
        return None
    cleaned = comment.strip()
    for token in ("password", "token", "secret", "api_key", "smiles"):
        cleaned = re.sub(
            rf"(?i)({re.escape(token)}\s*[:=]\s*)\S+",
            rf"\1{_REDACTED}",
            cleaned,
        )
    if _looks_like_raw_payload(cleaned):
        return _REDACTED
    return cleaned[:1000]


def _renewal_html(title: str, report: dict[str, Any]) -> str:
    summary = report["summary"]
    return "\n".join(
        [
            "<!doctype html>",
            "<html><body>",
            f"<h1>{html.escape(title)}</h1>",
            "<p>Automation value summary generated from safe metadata only.</p>",
            "<ul>",
            f"<li>Tasks automated: {int(summary['tasks_automated'])}</li>",
            f"<li>Hours saved: {float(summary['total_hours_saved']):.2f}</li>",
            f"<li>Reports generated: {int(summary['reports_generated'])}</li>",
            f"<li>Workflows completed: {int(summary['workflows_completed'])}</li>",
            "</ul>",
            f"<p>{html.escape(_SAFE_NOTE)}</p>",
            "</body></html>",
        ]
    )


def _coerce_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
