from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator

from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    AdminSystemSummary,
    AdminUserRecord,
    AnalysisEvidenceReport,
    AnalysisInputs,
    AnalysisReport,
    AuditEventRecord,
    EmailOutboxRecord,
    FIDPreviewReport,
    FIDProcessingMetadata,
    FIDRunRecord,
    FIDRunReport,
    FIDRunReviewDecisionRecord,
    FullStoredAnalysisRecord,
    JobRecord,
    MetricCard,
    MetricsSummary,
    NMR2DEvidenceReportSection,
    ProjectDashboardRecord,
    ProjectRecord,
    ProjectSampleCreate,
    ProjectSampleRecord,
    RawArchivePreview,
    RawArchiveRecord,
    ReviewDecisionRecord,
    ReviewQueueItem,
    SampleAnalysisComparison,
    SampleAnalysisComparisonItem,
    SampleDetailRecord,
    SampleReportsRecord,
    SampleTimelineRecord,
    StoredAnalysisRecord,
    StoredReportRecord,
    UserPublic,
)
from .nmr2d_models import NMR2DAnalysisReport, NMR2DRunRecord
from .orm import (
    AnalysisORM,
    AppMetricDailyORM,
    AuditEventORM,
    Base,
    EmailOutboxORM,
    FIDRunORM,
    FIDRunReviewDecisionORM,
    JobORM,
    NMR2DRunORM,
    ProjectORM,
    ProjectSampleORM,
    RawArchiveORM,
    RefreshTokenORM,
    ReportORM,
    ReviewDecisionORM,
    SessionFamilyORM,
    SessionTokenORM,
    UserActionTokenORM,
    UserORM,
    utcnow,
)
from .security import (
    create_access_token,
    create_action_token,
    hash_password,
    token_digest,
    verify_password,
)


def create_engine_for_url(database_url: str) -> Engine:
    connect_args: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, pool_pre_ping=True, future=True, connect_args=connect_args)



def create_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_engine_for_url(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)



def init_db(session_factory: sessionmaker[Session]) -> None:
    engine = session_factory.kw["bind"]
    if engine is None:
        raise RuntimeError("Session factory is missing a bound engine.")
    Base.metadata.create_all(engine)
    _ensure_sqlite_schema(engine)


def _ensure_sqlite_schema(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        tables = {
            str(row[0])
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "users" in tables:
            # v0.6.7 per-tenant graduation knob — add the column
            # idempotently for existing SQLite dev DBs that pre-date
            # Alembic migration 0011.  Production Postgres picks the
            # column up via the Alembic migration itself.
            users_existing = {
                str(row[1])
                for row in connection.exec_driver_sql("PRAGMA table_info(users)").fetchall()
            }
            if "gsd_graduated_at" not in users_existing:
                connection.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN gsd_graduated_at TIMESTAMP"
                )
        if "fid_runs" in tables:
            existing = {
                str(row[1])
                for row in connection.exec_driver_sql("PRAGMA table_info(fid_runs)").fetchall()
            }
            missing_columns = {
                "raw_archive_id": "INTEGER",
                "raw_sha256": "VARCHAR(64)",
                "processing_recipe_json": "TEXT DEFAULT '{}'",
                "derived_spectrum_metadata_json": "TEXT DEFAULT '{}'",
            }
            for column, ddl in missing_columns.items():
                if column not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE fid_runs ADD COLUMN {column} {ddl}")
        if "nmr2d_runs" in tables:
            nmr2d_existing = {
                str(row[1])
                for row in connection.exec_driver_sql("PRAGMA table_info(nmr2d_runs)").fetchall()
            }
            nmr2d_missing_columns = {
                "sample_pk": "INTEGER",
                "filename": "VARCHAR(255) DEFAULT ''",
                "experiment_detected": "VARCHAR(32) DEFAULT 'UNKNOWN'",
                "evidence_score": "FLOAT DEFAULT 0",
                "suspicious_peak_count": "INTEGER DEFAULT 0",
                "preview_json": "TEXT DEFAULT '{}'",
                "result_json": "TEXT DEFAULT '{}'",
            }
            for column, ddl in nmr2d_missing_columns.items():
                if column not in nmr2d_existing:
                    connection.exec_driver_sql(f"ALTER TABLE nmr2d_runs ADD COLUMN {column} {ddl}")
        if "session_tokens" in tables:
            # MFA/step-up columns (Prompt 3 / migration 0019) on a pre-existing dev SQLite DB.
            session_existing = {
                str(row[1])
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(session_tokens)"
                ).fetchall()
            }
            session_mfa_columns = {
                "amr": "VARCHAR(64)",
                "mfa_at": "TIMESTAMP",
                "stepped_up_at": "TIMESTAMP",
                "step_up_factor": "VARCHAR(16)",
                "step_up_aal": "VARCHAR(8)",
                # Session/token hardening (Prompt 4 / migration 0020).
                "family_id": "INTEGER",
                "refresh_id": "INTEGER",
            }
            for column, ddl in session_mfa_columns.items():
                if column not in session_existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE session_tokens ADD COLUMN {column} {ddl}"
                    )
        version_reference_columns = {
            "method_id": "INTEGER",
            "model_version_id": "INTEGER",
            "scoring_profile_id": "INTEGER",
            "threshold_profile_id": "INTEGER",
        }
        for table_name in (
            "jobs",
            "spectracheck_sessions",
            "spectracheck_evidence_records",
            "spectracheck_report_records",
            "analysis_jobs",
            "artifact_records",
            "workflow_runs",
            "workflow_run_artifacts",
        ):
            if table_name not in tables:
                continue
            existing_columns = {
                str(row[1])
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column, ddl in version_reference_columns.items():
                if column not in existing_columns:
                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column} {ddl}")
        if "prediction_service_configs" in tables:
            prediction_config_columns = {
                str(row[1])
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info(prediction_service_configs)"
                ).fetchall()
            }
            prediction_config_missing_columns = {
                "service_key": "VARCHAR(120)",
                "confidence_thresholds_json": "TEXT DEFAULT '{}'",
                "ood_rules_json": "TEXT DEFAULT '{}'",
                "fallback_rules_json": "TEXT DEFAULT '{}'",
                "human_review_rules_json": "TEXT DEFAULT '{}'",
                "max_batch_size": "INTEGER",
            }
            for column, ddl in prediction_config_missing_columns.items():
                if column not in prediction_config_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE prediction_service_configs ADD COLUMN {column} {ddl}"
                    )


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()



def _user_to_public(user: UserORM) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        is_verified=user.is_verified,
        created_at=user.created_at,
        verified_at=user.verified_at,
        gsd_graduated_at=user.gsd_graduated_at,
    )



def create_user(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    password: str,
    is_verified: bool = False,
    is_admin: bool = False,
) -> UserPublic:
    normalized_email = email.strip().lower()
    with session_scope(session_factory) as session:
        existing = session.scalar(select(UserORM).where(UserORM.email == normalized_email))
        if existing is not None:
            raise ValueError("A user with that email already exists.")
        verified_at = utcnow() if is_verified else None
        user = UserORM(
            email=normalized_email,
            password_hash=hash_password(password),
            is_active=True,
            is_admin=is_admin,
            is_verified=is_verified,
            verified_at=verified_at,
        )
        session.add(user)
        session.flush()
        session.refresh(user)
        return _user_to_public(user)



def get_user_by_email(session_factory: sessionmaker[Session], email: str) -> UserPublic | None:
    normalized_email = email.strip().lower()
    with session_scope(session_factory) as session:
        user = session.scalar(select(UserORM).where(UserORM.email == normalized_email))
        return None if user is None else _user_to_public(user)



def authenticate_user(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    password: str,
    require_verified: bool = False,
) -> UserPublic | None:
    normalized_email = email.strip().lower()
    with session_scope(session_factory) as session:
        user = session.scalar(select(UserORM).where(UserORM.email == normalized_email))
        if user is None or not user.is_active:
            return None
        if require_verified and not user.is_verified:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return _user_to_public(user)



def create_user_session(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    ttl_minutes: int,
    amr: str | None = None,
) -> tuple[str, datetime]:
    token, expires_at = create_access_token(ttl_minutes)
    with session_scope(session_factory) as session:
        record = SessionTokenORM(
            user_id=user_id,
            token_hash=token_digest(token),
            expires_at=expires_at,
            amr=amr,
            mfa_at=utcnow() if amr else None,
        )
        session.add(record)
    return token, expires_at



def get_user_by_token(session_factory: sessionmaker[Session], token: str) -> UserPublic | None:
    digest = token_digest(token)
    now = datetime.now(UTC)
    with session_scope(session_factory) as session:
        stmt = (
            select(SessionTokenORM)
            .where(SessionTokenORM.token_hash == digest)
            .where(SessionTokenORM.revoked_at.is_(None))
            .where(SessionTokenORM.expires_at >= now)
        )
        token_record = session.scalar(stmt)
        if token_record is None:
            return None
        # Immediate family-wide revocation + absolute-cap enforcement (Prompt 4): a revoked family —
        # or one past its hard absolute cap — kills its access bearers on the very next request, so a
        # bearer minted by a late rotation can't outlive the cap. NULL family_id = legacy -> no-op.
        if token_record.family_id is not None:
            family = session.get(SessionFamilyORM, token_record.family_id)
            if family is not None:
                if family.revoked_at is not None:
                    return None
                cap = family.absolute_expires_at
                if cap is not None and (cap if cap.tzinfo else cap.replace(tzinfo=UTC)) <= now:
                    return None
        token_record.last_used_at = utcnow()
        user = session.get(UserORM, token_record.user_id)
        if user is None or not user.is_active:
            return None
        return _user_to_public(user)



def revoke_token(session_factory: sessionmaker[Session], token: str) -> None:
    digest = token_digest(token)
    with session_scope(session_factory) as session:
        token_record = session.scalar(select(SessionTokenORM).where(SessionTokenORM.token_hash == digest))
        if token_record is not None and token_record.revoked_at is None:
            token_record.revoked_at = utcnow()



def revoke_all_user_tokens(session_factory: sessionmaker[Session], user_id: int) -> None:
    now = utcnow()
    with session_scope(session_factory) as session:
        rows = list(session.scalars(select(SessionTokenORM).where(SessionTokenORM.user_id == user_id)).all())
        for row in rows:
            if row.revoked_at is None:
                row.revoked_at = now
        # Family-aware (Prompt 4): also revoke the user's session families + refresh tokens, so a
        # held refresh token can't mint a fresh session after a global revoke (e.g. password reset).
        families = session.scalars(
            select(SessionFamilyORM)
            .where(SessionFamilyORM.user_id == user_id)
            .where(SessionFamilyORM.revoked_at.is_(None))
        ).all()
        for family in families:
            family.revoked_at = now
            family.revoked_reason = "global_revoke"
        session.execute(
            update(RefreshTokenORM)
            .where(RefreshTokenORM.user_id == user_id)
            .where(RefreshTokenORM.revoked_at.is_(None))
            .values(revoked_at=now)
        )



def create_user_action_token(
    session_factory: sessionmaker[Session],
    *,
    email: str,
    purpose: str,
    ttl_minutes: int,
) -> tuple[str, datetime] | None:
    normalized_email = email.strip().lower()
    token, expires_at = create_action_token(ttl_minutes)
    digest = token_digest(token)
    with session_scope(session_factory) as session:
        user = session.scalar(select(UserORM).where(UserORM.email == normalized_email))
        if user is None or not user.is_active:
            return None
        session.execute(
            delete(UserActionTokenORM).where(UserActionTokenORM.user_id == user.id).where(UserActionTokenORM.purpose == purpose)
        )
        record = UserActionTokenORM(
            user_id=user.id,
            purpose=purpose,
            token_hash=digest,
            expires_at=expires_at,
        )
        session.add(record)
    return token, expires_at



def consume_user_action_token(
    session_factory: sessionmaker[Session],
    *,
    token: str,
    purpose: str,
) -> UserPublic | None:
    digest = token_digest(token)
    now = datetime.now(UTC)
    with session_scope(session_factory) as session:
        stmt = (
            select(UserActionTokenORM)
            .where(UserActionTokenORM.token_hash == digest)
            .where(UserActionTokenORM.purpose == purpose)
            .where(UserActionTokenORM.consumed_at.is_(None))
            .where(UserActionTokenORM.expires_at >= now)
        )
        record = session.scalar(stmt)
        if record is None:
            return None
        record.consumed_at = utcnow()
        user = session.get(UserORM, record.user_id)
        if user is None or not user.is_active:
            return None
        return _user_to_public(user)



def mark_user_verified(session_factory: sessionmaker[Session], *, user_id: int) -> UserPublic | None:
    with session_scope(session_factory) as session:
        user = session.get(UserORM, user_id)
        if user is None:
            return None
        user.is_verified = True
        user.verified_at = utcnow()
        session.flush()
        session.refresh(user)
        return _user_to_public(user)



def set_user_password(session_factory: sessionmaker[Session], *, user_id: int, new_password: str) -> UserPublic | None:
    with session_scope(session_factory) as session:
        user = session.get(UserORM, user_id)
        if user is None:
            return None
        user.password_hash = hash_password(new_password)
        session.flush()
        session.refresh(user)
        return _user_to_public(user)



def queue_email(session_factory: sessionmaker[Session], *, to_email: str, subject: str, body: str, purpose: str | None = None) -> int:
    with session_scope(session_factory) as session:
        row = EmailOutboxORM(to_email=to_email, subject=subject, body=body, purpose=purpose)
        session.add(row)
        session.flush()
        return int(row.id)



def list_email_outbox(session_factory: sessionmaker[Session], *, limit: int = 20) -> list[EmailOutboxRecord]:
    with session_scope(session_factory) as session:
        rows = list(session.scalars(select(EmailOutboxORM).order_by(EmailOutboxORM.id.desc()).limit(limit)).all())
        return [
            EmailOutboxRecord(
                id=row.id,
                created_at=row.created_at,
                to_email=row.to_email,
                subject=row.subject,
                body=row.body,
                purpose=row.purpose,
            )
            for row in rows
        ]



def create_job(
    session_factory: sessionmaker[Session],
    *,
    total_items: int,
    job_name: str | None = None,
    uploaded_filename: str | None = None,
    user_id: int | None = None,
    queue_name: str | None = None,
) -> JobRecord:
    with session_scope(session_factory) as session:
        job = JobORM(
            user_id=user_id,
            job_name=job_name,
            uploaded_filename=uploaded_filename,
            status="pending",
            total_items=total_items,
            completed_items=0,
            queue_name=queue_name,
        )
        session.add(job)
        session.flush()
        session.refresh(job)
        return _job_to_record(job)



def set_job_backend_id(session_factory: sessionmaker[Session], job_id: int, *, backend_job_id: str, status: str = "queued") -> None:
    with session_scope(session_factory) as session:
        job = session.get(JobORM, job_id)
        if job is None:
            raise KeyError(f"Job {job_id} not found.")
        job.backend_job_id = backend_job_id
        job.status = status



def mark_job_started(session_factory: sessionmaker[Session], job_id: int) -> None:
    with session_scope(session_factory) as session:
        job = session.get(JobORM, job_id)
        if job is None:
            raise KeyError(f"Job {job_id} not found.")
        job.status = "processing"
        job.started_at = utcnow()
        job.error_message = None



def update_job_progress(
    session_factory: sessionmaker[Session],
    job_id: int,
    *,
    completed_items: int,
    status: str,
    error_message: str | None = None,
) -> None:
    with session_scope(session_factory) as session:
        job = session.get(JobORM, job_id)
        if job is None:
            raise KeyError(f"Job {job_id} not found.")
        job.completed_items = completed_items
        job.status = status
        if status in {"completed", "failed"}:
            job.finished_at = utcnow()
        if error_message is not None:
            job.error_message = error_message



def save_analysis(
    session_factory: sessionmaker[Session],
    report: AnalysisReport,
    payload: AnalysisInputs,
    *,
    user_id: int | None = None,
    job_id: int | None = None,
    hours_saved_estimate: float | None = None,
) -> int:
    with session_scope(session_factory) as session:
        row = AnalysisORM(
            user_id=user_id,
            job_id=job_id,
            sample_id=payload.sample_id,
            solvent=payload.solvent,
            smiles=payload.smiles,
            nmr_text=payload.nmr_text,
            label=report.label,
            review_status="pending_review",
            final_label=report.label,
            expected_total_h=report.expected_total_h,
            observed_total_h=report.observed_total_h,
            confidence=report.confidence,
            notes_json=json.dumps(report.notes),
            parsed_peak_count=report.parsed_peak_count,
            delta_total_h=report.delta_total_h,
            hours_saved_estimate=0.0 if hours_saved_estimate is None else float(hours_saved_estimate),
            full_report_json=report.model_dump_json(),
        )
        session.add(row)
        session.flush()
        row_id = row.id
    return int(row_id)



def _analysis_to_record(row: AnalysisORM) -> StoredAnalysisRecord:
    return StoredAnalysisRecord(
        id=row.id,
        created_at=row.created_at,
        label=row.label,
        sample_id=row.sample_id,
        solvent=row.solvent,
        smiles=row.smiles,
        nmr_text=row.nmr_text,
        expected_total_h=row.expected_total_h,
        observed_total_h=row.observed_total_h,
        confidence=row.confidence,
        notes=list(json.loads(row.notes_json)),
        parsed_peak_count=row.parsed_peak_count,
        delta_total_h=row.delta_total_h,
        job_id=row.job_id,
        user_id=row.user_id,
        review_status=row.review_status,
        reviewer_user_id=row.reviewer_user_id,
        reviewed_at=row.reviewed_at,
        review_comment=row.review_comment,
        final_label=row.final_label,
        hours_saved_estimate=row.hours_saved_estimate,
    )



def _project_to_record(row: ProjectORM) -> ProjectRecord:
    samples = list(row.samples or [])
    linked_analysis_ids = {sample.analysis_id for sample in samples if sample.analysis_id is not None}
    linked_analysis_count = sum(1 for sample in samples if sample.analysis_id is not None)
    return ProjectRecord(
        id=row.id,
        user_id=row.user_id,
        name=row.name,
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
        sample_count=len(samples),
        analysis_count=len(linked_analysis_ids),
        linked_analysis_count=linked_analysis_count,
    )


def _project_sample_to_record(row: ProjectSampleORM) -> ProjectSampleRecord:
    return ProjectSampleRecord(
        id=row.id,
        project_id=row.project_id,
        analysis_id=row.analysis_id,
        sample_id=row.sample_id,
        smiles=row.smiles,
        nmr_text=row.nmr_text,
        solvent=row.solvent,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _job_to_record(job: JobORM) -> JobRecord:
    return JobRecord(
        id=job.id,
        created_at=job.created_at,
        user_id=job.user_id,
        job_name=job.job_name,
        uploaded_filename=job.uploaded_filename,
        status=job.status,
        total_items=job.total_items,
        completed_items=job.completed_items,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
        backend_job_id=job.backend_job_id,
        queue_name=job.queue_name,
        review_required=job.review_required,
        method_id=job.method_id,
        model_version_id=job.model_version_id,
        scoring_profile_id=job.scoring_profile_id,
        threshold_profile_id=job.threshold_profile_id,
        review_completion_rate=(0.0 if job.total_items == 0 else sum(1 for a in (job.analyses or []) if a.review_status in {"approved","rejected","needs_revision"}) / job.total_items),
    )



def create_project(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    name: str,
    description: str | None = None,
) -> ProjectRecord:
    normalized_name = name.strip()
    with session_scope(session_factory) as session:
        existing = session.scalar(select(ProjectORM).where(ProjectORM.user_id == user_id).where(ProjectORM.name == normalized_name))
        if existing is not None:
            raise ValueError("A project with that name already exists.")
        row = ProjectORM(user_id=user_id, name=normalized_name, description=description)
        session.add(row)
        session.flush()
        session.refresh(row)
        return _project_to_record(row)


def list_projects(session_factory: sessionmaker[Session], *, user_id: int, limit: int = 200) -> list[ProjectRecord]:
    with session_scope(session_factory) as session:
        rows = list(
            session.scalars(
                select(ProjectORM)
                .where(ProjectORM.user_id == user_id)
                .order_by(ProjectORM.updated_at.desc(), ProjectORM.id.desc())
                .limit(limit)
            ).all()
        )
        return [_project_to_record(row) for row in rows]


def get_project_by_id(session_factory: sessionmaker[Session], project_id: int, *, user_id: int) -> ProjectRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(ProjectORM, project_id)
        if row is None or row.user_id != user_id:
            return None
        return _project_to_record(row)


def create_project_sample(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    project_id: int,
    payload: ProjectSampleCreate,
) -> ProjectSampleRecord:
    with session_scope(session_factory) as session:
        project = session.get(ProjectORM, project_id)
        if project is None or project.user_id != user_id:
            raise KeyError(f"Project {project_id} not found.")
        if payload.analysis_id is not None:
            analysis = session.get(AnalysisORM, payload.analysis_id)
            if analysis is None or analysis.user_id != user_id:
                raise ValueError("The referenced analysis is not available for this user.")
        row = ProjectSampleORM(
            project_id=project_id,
            analysis_id=payload.analysis_id,
            sample_id=payload.sample_id,
            smiles=payload.smiles,
            nmr_text=payload.nmr_text,
            solvent=payload.solvent,
        )
        session.add(row)
        project.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _project_sample_to_record(row)


def link_project_sample_analysis(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    project_id: int,
    sample_record_id: int,
    analysis_id: int,
) -> ProjectSampleRecord:
    with session_scope(session_factory) as session:
        project = session.get(ProjectORM, project_id)
        if project is None or project.user_id != user_id:
            raise KeyError(f"Project {project_id} not found.")
        row = session.get(ProjectSampleORM, sample_record_id)
        if row is None or row.project_id != project_id:
            raise KeyError(f"Sample {sample_record_id} not found.")
        analysis = session.get(AnalysisORM, analysis_id)
        if analysis is None or analysis.user_id != user_id:
            raise ValueError("The referenced analysis is not available for this user.")
        row.analysis_id = analysis_id
        row.updated_at = utcnow()
        project.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _project_sample_to_record(row)


def list_project_samples(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    project_id: int,
    limit: int = 200,
) -> list[ProjectSampleRecord]:
    with session_scope(session_factory) as session:
        project = session.get(ProjectORM, project_id)
        if project is None or project.user_id != user_id:
            raise KeyError(f"Project {project_id} not found.")
        rows = list(
            session.scalars(
                select(ProjectSampleORM)
                .where(ProjectSampleORM.project_id == project_id)
                .order_by(ProjectSampleORM.updated_at.desc(), ProjectSampleORM.id.desc())
                .limit(limit)
            ).all()
        )
        return [_project_sample_to_record(row) for row in rows]


def _find_project_sample_row(
    session: Session,
    *,
    user_id: int,
    sample_identity: str,
) -> ProjectSampleORM | None:
    identity = str(sample_identity).strip()
    if not identity:
        return None
    if identity.isdigit():
        row = session.get(ProjectSampleORM, int(identity))
        if row is not None and row.project is not None and row.project.user_id == user_id:
            return row
    return session.scalar(
        select(ProjectSampleORM)
        .join(ProjectORM)
        .where(ProjectORM.user_id == user_id)
        .where(ProjectSampleORM.sample_id == identity)
        .order_by(ProjectSampleORM.updated_at.desc(), ProjectSampleORM.id.desc())
        .limit(1)
    )


def _analysis_rows_for_sample(
    session: Session,
    *,
    sample: ProjectSampleORM,
    user_id: int,
    same_smiles_fallback: bool = False,
) -> tuple[list[AnalysisORM], str]:
    rows_by_id: dict[int, AnalysisORM] = {}
    if sample.sample_id:
        rows = list(
            session.scalars(
                select(AnalysisORM)
                .where(AnalysisORM.user_id == user_id)
                .where(AnalysisORM.sample_id == sample.sample_id)
                .order_by(AnalysisORM.id.desc())
            ).all()
        )
        rows_by_id.update({row.id: row for row in rows})
        if rows_by_id:
            basis = "sample_id"
        else:
            basis = "none"
    else:
        basis = "none"

    if sample.analysis_id is not None:
        row = session.get(AnalysisORM, sample.analysis_id)
        if row is not None and row.user_id == user_id:
            rows_by_id[row.id] = row
            if basis == "none" and row.sample_id and sample.sample_id and row.sample_id == sample.sample_id:
                basis = "sample_id"

    if not rows_by_id and same_smiles_fallback and sample.smiles:
        rows = list(
            session.scalars(
                select(AnalysisORM)
                .where(AnalysisORM.user_id == user_id)
                .where(AnalysisORM.smiles == sample.smiles)
                .order_by(AnalysisORM.id.desc())
            ).all()
        )
        rows_by_id.update({row.id: row for row in rows})
        if rows_by_id:
            basis = "smiles"

    rows = sorted(rows_by_id.values(), key=lambda row: row.id, reverse=True)
    return (rows, basis)


def get_sample_detail(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    sample_identity: str,
) -> SampleDetailRecord | None:
    with session_scope(session_factory) as session:
        sample = _find_project_sample_row(session, user_id=user_id, sample_identity=sample_identity)
        if sample is None:
            return None
        analysis_rows, _basis = _analysis_rows_for_sample(session, sample=sample, user_id=user_id)
        latest_analysis = _analysis_to_record(analysis_rows[0]) if analysis_rows else None
        notes = latest_analysis.notes if latest_analysis is not None else []
        report_count = 0
        if analysis_rows:
            report_count = int(
                session.scalar(
                    select(func.count())
                    .select_from(ReportORM)
                    .where(ReportORM.analysis_id.in_([row.id for row in analysis_rows]))
                )
                or 0
            )
        return SampleDetailRecord(
            sample=_project_sample_to_record(sample),
            latest_analysis=latest_analysis,
            notes=notes,
            reports_count=report_count,
        )


def list_sample_analyses(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    sample_identity: str,
) -> list[StoredAnalysisRecord] | None:
    with session_scope(session_factory) as session:
        sample = _find_project_sample_row(session, user_id=user_id, sample_identity=sample_identity)
        if sample is None:
            return None
        rows, _basis = _analysis_rows_for_sample(session, sample=sample, user_id=user_id)
        return [_analysis_to_record(row) for row in rows]


def get_sample_timeline(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    sample_identity: str,
) -> SampleTimelineRecord | None:
    with session_scope(session_factory) as session:
        sample = _find_project_sample_row(session, user_id=user_id, sample_identity=sample_identity)
        if sample is None:
            return None
        analysis_rows, _basis = _analysis_rows_for_sample(session, sample=sample, user_id=user_id)
        analysis_ids = [row.id for row in analysis_rows]

    decisions: list[ReviewDecisionRecord] = []
    audit_events: list[AuditEventRecord] = []
    for analysis_id in analysis_ids:
        decisions.extend(list_review_decisions(session_factory, analysis_id=analysis_id, limit=200))
        audit_events.extend(
            list_audit_events(
                session_factory,
                limit=200,
                entity_type="analysis",
                entity_id=analysis_id,
            )
        )
    decisions.sort(key=lambda item: item.created_at, reverse=True)
    audit_events.sort(key=lambda item: item.created_at, reverse=True)
    return SampleTimelineRecord(
        sample=get_sample_detail(
            session_factory,
            user_id=user_id,
            sample_identity=sample_identity,
        ).sample,
        analysis_ids=analysis_ids,
        review_decisions=decisions,
        audit_events=audit_events,
    )


def list_sample_reports(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    sample_identity: str,
) -> SampleReportsRecord | None:
    with session_scope(session_factory) as session:
        sample = _find_project_sample_row(session, user_id=user_id, sample_identity=sample_identity)
        if sample is None:
            return None
        analysis_rows, _basis = _analysis_rows_for_sample(session, sample=sample, user_id=user_id)
        analysis_ids = [row.id for row in analysis_rows]
        reports: list[StoredReportRecord] = []
        if analysis_ids:
            report_rows = list(
                session.scalars(
                    select(ReportORM)
                    .where(ReportORM.analysis_id.in_(analysis_ids))
                    .order_by(ReportORM.id.desc())
                ).all()
            )
            reports = [_report_to_record(row) for row in report_rows]
        return SampleReportsRecord(sample=_project_sample_to_record(sample), reports=reports)


def compare_sample_analyses(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    sample_identity: str,
) -> SampleAnalysisComparison | None:
    with session_scope(session_factory) as session:
        sample = _find_project_sample_row(session, user_id=user_id, sample_identity=sample_identity)
        if sample is None:
            return None
        rows, basis = _analysis_rows_for_sample(
            session,
            sample=sample,
            user_id=user_id,
            same_smiles_fallback=True,
        )
        chronological = sorted(rows, key=lambda row: row.created_at)
        previous_peak_count = 0
        change_by_id: dict[int, int] = {}
        for row in chronological:
            change_by_id[row.id] = row.parsed_peak_count - previous_peak_count
            previous_peak_count = row.parsed_peak_count
        items = []
        for row in rows:
            notes = list(json.loads(row.notes_json))
            impurity_flags = int("impurity" in row.label) + sum(
                1 for note in notes if "impur" in note.lower()
            )
            items.append(
                SampleAnalysisComparisonItem(
                    analysis_id=row.id,
                    created_at=row.created_at,
                    label=row.label,
                    final_label=row.final_label,
                    proton_count_delta=row.delta_total_h,
                    confidence=row.confidence,
                    impurity_flags=impurity_flags,
                    reviewer_outcome=row.review_status,
                    peak_count=row.parsed_peak_count,
                    peak_count_change=change_by_id.get(row.id, 0),
                    time_saved=row.hours_saved_estimate,
                )
            )
        return SampleAnalysisComparison(
            sample=_project_sample_to_record(sample),
            basis=basis if items else "none",
            items=items,
        )


def build_project_dashboard(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    project_id: int,
) -> ProjectDashboardRecord | None:
    with session_scope(session_factory) as session:
        project = session.get(ProjectORM, project_id)
        if project is None or project.user_id != user_id:
            return None
        samples = list(project.samples or [])
        analysis_ids = sorted({sample.analysis_id for sample in samples if sample.analysis_id is not None})
        analysis_rows = []
        if analysis_ids:
            analysis_rows = list(
                session.scalars(
                    select(AnalysisORM)
                    .where(AnalysisORM.user_id == user_id)
                    .where(AnalysisORM.id.in_(analysis_ids))
                    .order_by(AnalysisORM.id.desc())
                ).all()
            )
        solvent_distribution: dict[str, int] = {}
        for sample in samples:
            if sample.solvent:
                solvent_distribution[sample.solvent] = solvent_distribution.get(sample.solvent, 0) + 1
        approved = sum(1 for row in analysis_rows if row.review_status == "approved")
        rejected = sum(1 for row in analysis_rows if row.review_status == "rejected")
        pending = sum(1 for row in analysis_rows if row.review_status == "pending_review")
        hours_saved = round(sum(row.hours_saved_estimate for row in analysis_rows), 2)
        likely_impurity_flags = sum(
            1 for row in analysis_rows if row.label == "possible_impurity_or_incorrect_assignment"
        )
        activity: list[AuditEventRecord] = []
        activity.extend(list_audit_events(session_factory, limit=50, entity_type="project", entity_id=project_id))
        for sample in samples[:50]:
            activity.extend(
                list_audit_events(
                    session_factory,
                    limit=50,
                    entity_type="project_sample",
                    entity_id=sample.id,
                )
            )
        for analysis_id in analysis_ids[:50]:
            activity.extend(
                list_audit_events(
                    session_factory,
                    limit=50,
                    entity_type="analysis",
                    entity_id=analysis_id,
                )
            )
        activity.sort(key=lambda item: item.created_at, reverse=True)
        return ProjectDashboardRecord(
            project=_project_to_record(project),
            sample_count=len(samples),
            analysis_count=len(analysis_rows),
            approved_reviews=approved,
            rejected_reviews=rejected,
            pending_review=pending,
            solvent_distribution=solvent_distribution,
            hours_saved_estimate=hours_saved,
            likely_impurity_flags=likely_impurity_flags,
            latest_activity=activity[:12],
        )


def list_recent_analyses(session_factory: sessionmaker[Session], *, limit: int = 20, user_id: int | None = None) -> list[StoredAnalysisRecord]:
    with session_scope(session_factory) as session:
        stmt = select(AnalysisORM).order_by(AnalysisORM.id.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(AnalysisORM.user_id == user_id)
        rows = list(session.scalars(stmt).all())
        return [_analysis_to_record(row) for row in rows]


def save_raw_archive_preview(
    session_factory: sessionmaker[Session],
    *,
    provenance: dict[str, Any],
    user_id: int | None = None,
    content_type: str | None = None,
) -> RawArchivePreview:
    sha256 = str(provenance.get("sha256") or "").strip()
    if not sha256:
        raise ValueError("Raw archive provenance is missing sha256.")
    storage_path = str(provenance.get("storage_path") or "").strip()
    if not storage_path:
        raise ValueError("Raw archive provenance is missing storage_path.")
    files_found = list(provenance.get("files_found") or [])
    acquisition_metadata = dict(provenance.get("acquisition_metadata") or {})
    warnings = list(provenance.get("warnings") or [])
    required_files_present = bool(
        provenance.get("required_files_present")
        or acquisition_metadata.get("required_files_present")
    )
    created = False
    with session_scope(session_factory) as session:
        row = session.scalar(select(RawArchiveORM).where(RawArchiveORM.sha256 == sha256))
        if row is None:
            row = RawArchiveORM(
                user_id=user_id,
                filename=str(provenance.get("original_filename") or provenance.get("filename") or "raw_nmr_archive"),
                content_type=content_type,
                byte_size=int(provenance.get("byte_size") or 0),
                sha256=sha256,
                storage_path=storage_path,
                vendor_detected=str(provenance.get("vendor_detected") or "unknown"),
                dataset_root=provenance.get("dataset_root"),
                required_files_present=required_files_present,
                files_found_json=json.dumps(files_found),
                acquisition_metadata_json=json.dumps(acquisition_metadata, sort_keys=True),
                warnings_json=json.dumps(warnings),
                immutable=bool(provenance.get("raw_data_immutable", True)),
            )
            session.add(row)
            created = True
        else:
            if row.user_id is None and user_id is not None:
                row.user_id = user_id
            if row.content_type is None and content_type:
                row.content_type = content_type
        session.flush()
        session.refresh(row)
        record = _raw_archive_to_record(row)
    return RawArchivePreview(
        archive=record,
        already_stored=not created,
        provenance=dict(provenance),
    )


def save_raw_archive_record(
    session_factory: sessionmaker[Session],
    *,
    provenance: dict[str, Any],
    user_id: int | None = None,
    content_type: str | None = None,
) -> RawArchiveRecord:
    return save_raw_archive_preview(
        session_factory,
        provenance=provenance,
        user_id=user_id,
        content_type=content_type,
    ).archive


def save_nmr2d_run(
    session_factory: sessionmaker[Session],
    report: NMR2DAnalysisReport,
    *,
    source_filename: str,
    user_id: int | None = None,
    analysis_id: int | None = None,
) -> NMR2DRunRecord:
    with session_scope(session_factory) as session:
        row = NMR2DRunORM(
            user_id=user_id,
            analysis_id=analysis_id,
            sample_pk=analysis_id,
            sample_id=report.sample_id,
            filename=source_filename,
            experiment_detected=report.preview.experiment_detected,
            source_filename=source_filename,
            experiment_types_json=json.dumps(list(report.experiments)),
            peak_count=report.peak_count,
            evidence_score=report.evidence_score,
            suspicious_peak_count=report.suspicious_peak_count,
            overall_score=report.overall_score,
            review_status="pending_review",
            preview_json=report.preview.model_dump_json(),
            result_json=report.model_dump_json(),
            peaks_json=json.dumps([peak.model_dump(mode="json") for peak in report.peaks], sort_keys=True),
            report_json=report.model_dump_json(),
            metadata_json=json.dumps(report.metadata, sort_keys=True),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        record = _nmr2d_run_to_record(row)
    return record


def get_nmr2d_run_by_id(
    session_factory: sessionmaker[Session],
    *,
    run_id: int,
    user_id: int | None = None,
) -> NMR2DRunRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(NMR2DRunORM, run_id)
        if row is None:
            return None
        if user_id is not None and row.user_id not in {None, user_id}:
            return None
        return _nmr2d_run_to_record(row)


def _collect_nmr2d_notes(report: NMR2DAnalysisReport, experiments: set[str], *needles: str) -> list[str]:
    lowered_needles = tuple(needle.lower() for needle in needles)
    notes: list[str] = []
    for note in report.notes:
        if any(experiment.lower() in note.lower() for experiment in experiments):
            notes.append(note)
    for correlation in report.correlations:
        if str(correlation.correlation_type) not in experiments:
            continue
        for note in correlation.notes:
            if not lowered_needles or any(needle in note.lower() for needle in lowered_needles):
                notes.append(note)
    return list(dict.fromkeys(notes))


def _nmr2d_evidence_section_from_row(row: NMR2DRunORM) -> NMR2DEvidenceReportSection:
    record = _nmr2d_run_to_record(row)
    report = record.report
    experiments = [str(item) for item in (record.experiments or report.experiments)]
    experiment_type = ", ".join(experiments) if experiments else str(record.experiment_detected or "UNKNOWN")
    graph = report.correlation_summary.get("cosy_connectivity_graph")
    cosy_notes = _collect_nmr2d_notes(report, {"COSY"}, "connectivity", "scalar", "duplicate", "diagonal")
    if isinstance(graph, dict):
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
        cosy_notes.insert(0, f"COSY graph has {len(nodes)} node(s) and {len(edges)} non-diagonal edge(s).")
    direct_notes = _collect_nmr2d_notes(
        report,
        {"HSQC", "HMQC"},
        "direct",
        "attachment",
        "region",
        "carbon count",
    )
    hmbc_notes = _collect_nmr2d_notes(report, {"HMBC"}, "long-range", "expert review", "direct attachment")
    missing_extra_notes: list[str] = []
    if report.missing_reference_count:
        missing_extra_notes.append(
            f"{report.missing_reference_count} correlation(s) had no linked 1D reference match."
        )
    if report.extra_correlation_count:
        missing_extra_notes.append(
            f"{report.extra_correlation_count} extra or low-plausibility correlation(s) require review."
        )
    for warning in report.warnings:
        if any(word in warning.lower() for word in ("missing", "extra", "reference", "linked")):
            missing_extra_notes.append(warning)
    dept_apt = report.metadata.get("dept_apt_evidence")
    if not isinstance(dept_apt, dict):
        dept_apt = {}
    summary = report.correlation_summary
    apt_warning = None
    dept_warnings = dept_apt.get("warnings") if isinstance(dept_apt.get("warnings"), list) else []
    for warning in dept_warnings:
        if "APT" in str(warning) and "convention" in str(warning).lower():
            apt_warning = str(warning)
            break
    return NMR2DEvidenceReportSection(
        run_id=record.id,
        report_url=f"/nmr2d/runs/{record.id}/report",
        experiment_type=experiment_type,
        peak_count=record.peak_count,
        matched_correlations=report.matched_correlation_count,
        suspicious_correlations=report.suspicious_peak_count,
        evidence_score=report.evidence_score,
        cosy_connectivity_notes=list(dict.fromkeys(cosy_notes)),
        hsqc_hmqc_direct_attachment_notes=direct_notes,
        hmbc_long_range_notes=hmbc_notes,
        missing_extra_correlation_notes=list(dict.fromkeys(missing_extra_notes)),
        dept_apt_experiment_type=dept_apt.get("experiment_detected"),
        dept_apt_typed_peak_count=int(dept_apt.get("typed_peak_count") or 0),
        dept_apt_type_summary=dict(dept_apt.get("type_summary") or {}),
        dept_apt_matched_carbon13_count=int(dept_apt.get("matched_carbon13_count") or 0),
        dept_apt_consistency_score=dept_apt.get("dept_apt_consistency_score"),
        dept_apt_apt_convention_warning=apt_warning,
        hsqc_hmqc_dept_apt_supported_correlations=int(summary.get("dept_apt_supported_correlations") or 0),
        hsqc_hmqc_dept_apt_conflicting_correlations=int(summary.get("dept_apt_conflicting_correlations") or 0),
        hmbc_dept_apt_contextual_correlations=int(summary.get("dept_apt_contextual_correlations") or 0),
        human_review_status=record.review_status,  # type: ignore[arg-type]
        score_components=dict(report.metadata.get("score_components") or {}),
        warnings=list(dict.fromkeys([*report.warnings, *report.preview.warnings])),
    )


def list_nmr2d_evidence_sections_for_analysis(
    session_factory: sessionmaker[Session],
    *,
    analysis_id: int,
    user_id: int | None = None,
) -> list[NMR2DEvidenceReportSection]:
    with session_scope(session_factory) as session:
        rows = list(
            session.scalars(
                select(NMR2DRunORM)
                .where(NMR2DRunORM.analysis_id == analysis_id)
                .order_by(NMR2DRunORM.id.desc())
            ).all()
        )
        if user_id is not None:
            rows = [row for row in rows if row.user_id in {None, user_id}]
        return [_nmr2d_evidence_section_from_row(row) for row in rows]


def update_nmr2d_run_review_status(
    session_factory: sessionmaker[Session],
    *,
    run_id: int,
    review_status: str,
    reviewer_user_id: int | None = None,
    comment: str | None = None,
    user_id: int | None = None,
) -> NMR2DRunRecord | None:
    allowed_statuses = {"pending_review", "approved", "rejected", "needs_revision"}
    if review_status not in allowed_statuses:
        raise ValueError("Invalid 2D NMR review status.")
    with session_scope(session_factory) as session:
        row = session.get(NMR2DRunORM, run_id)
        if row is None:
            return None
        if user_id is not None and row.user_id not in {None, user_id}:
            return None
        previous_status = row.review_status
        row.review_status = review_status
        try:
            result_json = row.result_json if row.result_json and row.result_json != "{}" else row.report_json
            report = NMR2DAnalysisReport.model_validate_json(result_json)
            report = report.model_copy(
                update={
                    "evidence_summary": {
                        **dict(report.evidence_summary),
                        "human_review_status": review_status,
                    },
                    "metadata": {
                        **dict(report.metadata),
                        "human_review_status": review_status,
                        **({"human_review_comment": comment} if comment else {}),
                    },
                }
            )
            row.result_json = report.model_dump_json()
            row.report_json = report.model_dump_json()
            metadata = _json_dict(row.metadata_json)
            metadata["human_review_status"] = review_status
            if comment:
                metadata["human_review_comment"] = comment
            row.metadata_json = json.dumps(metadata, sort_keys=True)
        except Exception:
            pass
        session.add(
            AuditEventORM(
                event_type="nmr2d.review",
                message="2D NMR run review status updated.",
                actor_user_id=reviewer_user_id,
                entity_type="nmr2d_run",
                entity_id=row.id,
                metadata_json=json.dumps(
                    {
                        "previous_status": previous_status,
                        "new_status": review_status,
                        "comment": comment,
                    },
                    sort_keys=True,
                ),
            )
        )
        session.flush()
        session.refresh(row)
        return _nmr2d_run_to_record(row)


def get_raw_archive_by_sha256(
    session_factory: sessionmaker[Session],
    *,
    sha256: str,
    user_id: int | None = None,
) -> RawArchiveRecord | None:
    with session_scope(session_factory) as session:
        stmt = select(RawArchiveORM).where(RawArchiveORM.sha256 == sha256)
        if user_id is not None:
            stmt = stmt.where((RawArchiveORM.user_id == user_id) | (RawArchiveORM.user_id.is_(None)))
        row = session.scalar(stmt)
        return None if row is None else _raw_archive_to_record(row)


def get_raw_archive_by_id_or_sha(
    session_factory: sessionmaker[Session],
    *,
    archive_id: str,
    user_id: int | None = None,
) -> RawArchiveRecord | None:
    identity = str(archive_id or "").strip()
    if not identity:
        return None
    with session_scope(session_factory) as session:
        row = None
        if len(identity) == 64:
            stmt = select(RawArchiveORM).where(RawArchiveORM.sha256 == identity)
            if user_id is not None:
                stmt = stmt.where((RawArchiveORM.user_id == user_id) | (RawArchiveORM.user_id.is_(None)))
            row = session.scalar(stmt)
        if row is None:
            try:
                db_id = int(identity)
            except (TypeError, ValueError):
                db_id = None
            if db_id is not None:
                row = session.get(RawArchiveORM, db_id)
                if row is not None and user_id is not None and row.user_id not in {None, user_id}:
                    row = None
        return None if row is None else _raw_archive_to_record(row)


def _fid_processing_recipe(metadata: FIDProcessingMetadata) -> dict[str, Any]:
    recipe = metadata.processing_recipe.model_dump(mode="json")
    warnings = list(metadata.warnings)
    for warning in metadata.qa_diagnostics.warnings:
        if warning not in warnings:
            warnings.append(warning)
    recipe["warnings"] = warnings
    recipe["reviewer_status"] = metadata.human_review_status
    recipe["phase_score"] = metadata.phase_settings.get("phase_score")
    recipe["phase_correction_applied"] = metadata.phase_settings.get("phase_correction_applied")
    recipe["baseline_correction_applied"] = metadata.baseline_correction.get("correction_applied")
    recipe["extracted_peak_count"] = len(metadata.extracted_peak_list)
    return recipe


def _fid_derived_spectrum_metadata(preview: FIDPreviewReport) -> dict[str, Any]:
    metadata = preview.processing_metadata
    return {
        "format_detected": preview.format_detected,
        "source_mode": preview.source_mode,
        "point_count": preview.point_count,
        "preview_point_count": len(preview.preview_points),
        "inferred_peak_count": len(preview.inferred_peaks),
        "evidence_trace_mode": preview.metadata.get("evidence_trace_mode"),
        "display_mode": preview.metadata.get("display_mode"),
        "display_gain": preview.metadata.get("display_gain"),
        "baseline_lock_visual_only": preview.metadata.get("baseline_lock_visual_only"),
        "preview_downsampling": preview.metadata.get("preview_downsampling"),
        "raw_dataset_files_found": metadata.raw_dataset_files_found,
        "acquisition_parameters": metadata.acquisition_parameters,
        "qa_diagnostics": metadata.qa_diagnostics.model_dump(mode="json"),
    }


def save_fid_run(
    session_factory: sessionmaker[Session],
    preview: FIDPreviewReport,
    *,
    user_id: int | None = None,
    analysis_id: int | None = None,
    sample_id: str | None = None,
) -> FIDRunRecord:
    metadata = preview.processing_metadata
    qa = metadata.qa_diagnostics
    provenance = dict(metadata.raw_upload_provenance)
    raw_archive_id = provenance.get("raw_archive_db_id")
    processing_recipe = _fid_processing_recipe(metadata)
    derived_spectrum_metadata = _fid_derived_spectrum_metadata(preview)
    with session_scope(session_factory) as session:
        row = FIDRunORM(
            user_id=user_id,
            analysis_id=analysis_id,
            raw_archive_id=int(raw_archive_id) if raw_archive_id is not None else None,
            sample_id=sample_id,
            filename=preview.filename,
            raw_sha256=provenance.get("sha256"),
            selected_preset=metadata.selected_preset,
            quality_label=qa.quality_label,
            quality_score=qa.quality_score,
            review_status=metadata.human_review_status,
            preview_json=preview.model_copy(update={"fid_run_id": None}).model_dump_json(),
            metadata_json=metadata.model_dump_json(),
            processing_recipe_json=json.dumps(processing_recipe, sort_keys=True),
            derived_spectrum_metadata_json=json.dumps(derived_spectrum_metadata, sort_keys=True),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        row.preview_json = preview.model_copy(update={"fid_run_id": row.id}).model_dump_json()
        session.flush()
        session.refresh(row)
        return _fid_run_to_record(row)


def list_fid_runs(
    session_factory: sessionmaker[Session],
    *,
    limit: int = 20,
    user_id: int | None = None,
) -> list[FIDRunRecord]:
    with session_scope(session_factory) as session:
        stmt = select(FIDRunORM).order_by(FIDRunORM.id.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(FIDRunORM.user_id == user_id)
        rows = list(session.scalars(stmt).all())
        return [_fid_run_to_record(row) for row in rows]


def list_fid_runs_for_raw_archive(
    session_factory: sessionmaker[Session],
    *,
    raw_archive_id: int | None = None,
    raw_sha256: str | None = None,
    limit: int = 100,
    user_id: int | None = None,
) -> list[FIDRunRecord]:
    with session_scope(session_factory) as session:
        stmt = select(FIDRunORM).order_by(FIDRunORM.id.desc()).limit(limit)
        if raw_archive_id is not None:
            stmt = stmt.where(FIDRunORM.raw_archive_id == raw_archive_id)
        elif raw_sha256 is not None:
            stmt = stmt.where(FIDRunORM.raw_sha256 == raw_sha256)
        else:
            return []
        if user_id is not None:
            stmt = stmt.where(FIDRunORM.user_id == user_id)
        rows = list(session.scalars(stmt).all())
        return [_fid_run_to_record(row) for row in rows]


def get_fid_run_by_id(
    session_factory: sessionmaker[Session],
    run_id: int,
    *,
    user_id: int | None = None,
) -> FIDRunRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(FIDRunORM, run_id)
        if row is None:
            return None
        if user_id is not None and row.user_id != user_id:
            return None
        return _fid_run_to_record(row)


def list_fid_run_review_decisions(
    session_factory: sessionmaker[Session],
    *,
    run_id: int,
    limit: int = 100,
) -> list[FIDRunReviewDecisionRecord]:
    with session_scope(session_factory) as session:
        stmt = (
            select(FIDRunReviewDecisionORM)
            .where(FIDRunReviewDecisionORM.run_id == run_id)
            .order_by(FIDRunReviewDecisionORM.id.desc())
            .limit(limit)
        )
        rows = list(session.scalars(stmt).all())
        return [_fid_run_decision_to_record(row) for row in rows]


def submit_fid_run_review_decision(
    session_factory: sessionmaker[Session],
    *,
    run_id: int,
    reviewer_user_id: int,
    action: str,
    comment: str | None = None,
) -> FIDRunReviewDecisionRecord:
    action_to_status = {
        "approve": "approved",
        "reject": "rejected",
        "request_changes": "needs_revision",
        "review": "pending_review",
    }
    new_status = action_to_status.get(action, "pending_review")
    with session_scope(session_factory) as session:
        row = session.get(FIDRunORM, run_id)
        if row is None:
            raise ValueError("FID run not found.")
        previous_status = row.review_status
        row.review_status = new_status
        row.reviewer_user_id = reviewer_user_id
        row.reviewed_at = utcnow()
        row.reviewer_comment = comment
        try:
            metadata = FIDProcessingMetadata.model_validate_json(row.metadata_json)
            metadata = metadata.model_copy(update={"human_review_status": new_status})
            preview = FIDPreviewReport.model_validate_json(row.preview_json)
            preview = preview.model_copy(
                update={
                    "fid_run_id": row.id,
                    "processing_metadata": metadata,
                    "metadata": {
                        **dict(preview.metadata),
                        "human_review_status": new_status,
                    },
                }
            )
            row.metadata_json = metadata.model_dump_json()
            row.preview_json = preview.model_dump_json()
            recipe = _json_dict(row.processing_recipe_json)
            recipe["reviewer_status"] = new_status
            row.processing_recipe_json = json.dumps(recipe, sort_keys=True)
        except Exception:
            pass
        decision = FIDRunReviewDecisionORM(
            run_id=row.id,
            reviewer_user_id=reviewer_user_id,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            comment=comment,
        )
        session.add(decision)
        session.add(
            AuditEventORM(
                event_type="fid.review",
                message=f"FID run review decision '{action}' recorded.",
                actor_user_id=reviewer_user_id,
                entity_type="fid_run",
                entity_id=row.id,
                metadata_json=json.dumps(
                    {
                        "previous_status": previous_status,
                        "new_status": new_status,
                        "selected_preset": row.selected_preset,
                        "quality_label": row.quality_label,
                    }
                ),
            )
        )
        session.flush()
        session.refresh(decision)
        return _fid_run_decision_to_record(decision)


def build_fid_run_report(
    session_factory: sessionmaker[Session],
    *,
    run_id: int,
    user_id: int | None = None,
) -> FIDRunReport | None:
    run = get_fid_run_by_id(session_factory, run_id, user_id=user_id)
    if run is None:
        return None
    decisions = list_fid_run_review_decisions(session_factory, run_id=run_id, limit=200)
    metadata = run.processing_metadata
    raw_upload_provenance = dict(metadata.raw_upload_provenance)
    return FIDRunReport(
        run=run,
        raw_fid_provenance={
            "filename": run.filename,
            "vendor_format_detected": metadata.vendor_format_detected,
            "dataset_folder": metadata.dataset_folder,
            "raw_dataset_files_found": metadata.raw_dataset_files_found,
            "raw_upload_provenance": raw_upload_provenance,
            "raw_sha256": raw_upload_provenance.get("sha256"),
            "raw_data_immutable": raw_upload_provenance.get("raw_data_immutable"),
            "storage_backend": raw_upload_provenance.get("storage_backend"),
            "object_key": raw_upload_provenance.get("object_key"),
            "raw_archive_id": run.raw_archive_id,
            "raw_sha256": run.raw_sha256,
            "analysis_artifact_policy": metadata.analysis_artifact_policy,
            "nmrglue_used": metadata.nmrglue_used,
        },
        processing_assumptions={
            "selected_preset": metadata.selected_preset,
            "zero_filling": metadata.zero_filling,
            "line_broadening": metadata.line_broadening,
            "phase_settings": metadata.phase_settings,
            "baseline_correction": metadata.baseline_correction,
            "digital_filter_correction_status": metadata.digital_filter_correction_status,
            "processing_parameters": metadata.processing_parameters,
            "processing_recipe": run.processing_recipe,
            "derived_spectrum_metadata": run.derived_spectrum_metadata,
            "analysis_artifact_policy": metadata.analysis_artifact_policy,
        },
        qa_diagnostics=metadata.qa_diagnostics,
        inferred_peak_list=run.preview.inferred_peaks,
        review_decisions=decisions,
    )



def get_analysis_by_id(session_factory: sessionmaker[Session], analysis_id: int, *, user_id: int | None = None) -> StoredAnalysisRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(AnalysisORM, analysis_id)
        if row is None:
            return None
        if user_id is not None and row.user_id != user_id:
            return None
        return _analysis_to_record(row)



def get_full_analysis_by_id(session_factory: sessionmaker[Session], analysis_id: int, *, user_id: int | None = None) -> FullStoredAnalysisRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(AnalysisORM, analysis_id)
        if row is None:
            return None
        if user_id is not None and row.user_id != user_id:
            return None
        base = _analysis_to_record(row)
        full_report = AnalysisReport.model_validate_json(row.full_report_json)
        return FullStoredAnalysisRecord(**base.model_dump(), full_report=full_report)



def iter_analyses(session_factory: sessionmaker[Session], *, limit: int | None = None, user_id: int | None = None) -> Iterable[StoredAnalysisRecord]:
    with session_scope(session_factory) as session:
        stmt = select(AnalysisORM).order_by(AnalysisORM.id.desc())
        if user_id is not None:
            stmt = stmt.where(AnalysisORM.user_id == user_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = list(session.scalars(stmt).all())
    for row in rows:
        yield _analysis_to_record(row)



def list_jobs(session_factory: sessionmaker[Session], *, limit: int = 20, user_id: int | None = None) -> list[JobRecord]:
    with session_scope(session_factory) as session:
        stmt = select(JobORM).order_by(JobORM.id.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(JobORM.user_id == user_id)
        rows = list(session.scalars(stmt).all())
        return [_job_to_record(row) for row in rows]



def get_job_by_id(session_factory: sessionmaker[Session], job_id: int, *, user_id: int | None = None) -> JobRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(JobORM, job_id)
        if row is None:
            return None
        if user_id is not None and row.user_id != user_id:
            return None
        return _job_to_record(row)



def list_job_analyses(session_factory: sessionmaker[Session], job_id: int, *, user_id: int | None = None) -> list[StoredAnalysisRecord]:
    with session_scope(session_factory) as session:
        stmt = select(AnalysisORM).where(AnalysisORM.job_id == job_id).order_by(AnalysisORM.id.asc())
        if user_id is not None:
            stmt = stmt.where(AnalysisORM.user_id == user_id)
        rows = list(session.scalars(stmt).all())
        return [_analysis_to_record(row) for row in rows]



def export_history_csv(session_factory: sessionmaker[Session], *, limit: int | None = None, user_id: int | None = None) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "created_at", "label", "sample_id", "solvent", "smiles", "nmr_text", "expected_total_h",
        "observed_total_h", "confidence", "parsed_peak_count", "delta_total_h", "job_id", "notes",
    ])
    for record in iter_analyses(session_factory, limit=limit, user_id=user_id):
        writer.writerow([
            record.id, record.created_at.isoformat(), record.label, record.sample_id or "", record.solvent or "",
            record.smiles, record.nmr_text, record.expected_total_h, record.observed_total_h,
            record.confidence, record.parsed_peak_count, record.delta_total_h, record.job_id or "",
            " | ".join(record.notes),
        ])
    return output.getvalue()



def export_job_csv(session_factory: sessionmaker[Session], job_id: int, *, user_id: int | None = None) -> str:
    records = list_job_analyses(session_factory, job_id=job_id, user_id=user_id)
    if not records:
        raise KeyError(f"Job {job_id} not found or contains no accessible records.")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "created_at", "sample_id", "label", "solvent", "expected_total_h", "observed_total_h", "delta_total_h", "confidence", "notes"])
    for record in records:
        writer.writerow([
            record.id, record.created_at.isoformat(), record.sample_id or "", record.label, record.solvent or "",
            record.expected_total_h, record.observed_total_h, record.delta_total_h, record.confidence,
            " | ".join(record.notes),
        ])
    return output.getvalue()



def export_job_json(session_factory: sessionmaker[Session], job_id: int, *, user_id: int | None = None) -> str:
    job = get_job_by_id(session_factory, job_id, user_id=user_id)
    if job is None:
        raise KeyError(f"Job {job_id} not found.")
    items = list_job_analyses(session_factory, job_id=job_id, user_id=user_id)
    payload = {"job": job.model_dump(mode="json"), "items": [item.model_dump(mode="json") for item in items]}
    return json.dumps(payload, indent=2)


def _review_to_record(row: ReviewDecisionORM) -> ReviewDecisionRecord:
    return ReviewDecisionRecord(
        id=row.id,
        analysis_id=row.analysis_id,
        reviewer_user_id=row.reviewer_user_id,
        action=row.action,
        previous_status=row.previous_status,
        new_status=row.new_status,
        comment=row.comment,
        previous_label=row.previous_label,
        final_label=row.final_label,
        created_at=row.created_at,
    )


def _audit_to_record(row: AuditEventORM) -> AuditEventRecord:
    metadata: dict[str, object]
    try:
        metadata = dict(json.loads(row.metadata_json))
    except Exception:
        metadata = {}
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


def _metadata_str(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _report_to_record(row: ReportORM) -> StoredReportRecord:
    return StoredReportRecord(
        id=row.id,
        analysis_id=row.analysis_id,
        user_id=row.user_id,
        created_at=row.created_at,
        version=row.version,
        title=row.title,
        report=AnalysisEvidenceReport.model_validate_json(row.report_json),
    )


def _fid_run_decision_to_record(row: FIDRunReviewDecisionORM) -> FIDRunReviewDecisionRecord:
    return FIDRunReviewDecisionRecord(
        id=row.id,
        run_id=row.run_id,
        reviewer_user_id=row.reviewer_user_id,
        action=row.action,
        previous_status=row.previous_status,
        new_status=row.new_status,
        comment=row.comment,
        created_at=row.created_at,
    )


def _json_list(value: str) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _raw_archive_to_record(row: RawArchiveORM) -> RawArchiveRecord:
    return RawArchiveRecord(
        id=row.id,
        created_at=row.created_at,
        user_id=row.user_id,
        filename=row.filename,
        content_type=row.content_type,
        byte_size=row.byte_size,
        sha256=row.sha256,
        storage_path=row.storage_path,
        vendor_detected=row.vendor_detected,
        dataset_root=row.dataset_root,
        required_files_present=row.required_files_present,
        files_found=[str(item) for item in _json_list(row.files_found_json)],
        acquisition_metadata=_json_dict(row.acquisition_metadata_json),
        warnings=[str(item) for item in _json_list(row.warnings_json)],
        immutable=row.immutable,
        raw_archive_id=row.sha256,
    )


def _fid_run_to_record(row: FIDRunORM) -> FIDRunRecord:
    preview = FIDPreviewReport.model_validate_json(row.preview_json)
    try:
        metadata = FIDProcessingMetadata.model_validate_json(row.metadata_json)
    except Exception:
        metadata = preview.processing_metadata
    preview = preview.model_copy(
        update={
            "fid_run_id": row.id,
            "processing_metadata": metadata,
            "metadata": {
                **dict(preview.metadata),
                "human_review_status": row.review_status,
            },
        }
    )
    return FIDRunRecord(
        id=row.id,
        user_id=row.user_id,
        analysis_id=row.analysis_id,
        raw_archive_id=row.raw_archive_id,
        raw_sha256=row.raw_sha256,
        created_at=row.created_at,
        sample_id=row.sample_id,
        filename=row.filename,
        selected_preset=row.selected_preset,
        quality_label=row.quality_label,
        quality_score=row.quality_score,
        review_status=row.review_status,
        reviewer_user_id=row.reviewer_user_id,
        reviewed_at=row.reviewed_at,
        reviewer_comment=row.reviewer_comment,
        preview=preview,
        processing_metadata=metadata,
        processing_recipe=_json_dict(row.processing_recipe_json),
        derived_spectrum_metadata=_json_dict(row.derived_spectrum_metadata_json),
        review_decision_count=len(row.decisions or []),
    )


def _nmr2d_run_to_record(row: NMR2DRunORM) -> NMR2DRunRecord:
    result_json = getattr(row, "result_json", None)
    if not result_json or result_json == "{}":
        result_json = row.report_json
    report = NMR2DAnalysisReport.model_validate_json(result_json)
    report = report.model_copy(update={"run_id": row.id})
    experiments = [str(item) for item in _json_list(row.experiment_types_json)]
    metadata = _json_dict(row.metadata_json)
    filename = getattr(row, "filename", None) or row.source_filename
    experiment_detected = getattr(row, "experiment_detected", None) or (
        experiments[0] if len(experiments) == 1 else "UNKNOWN"
    )
    evidence_score = getattr(row, "evidence_score", None)
    if evidence_score is None:
        evidence_score = row.overall_score
    suspicious_peak_count = getattr(row, "suspicious_peak_count", None)
    if suspicious_peak_count is None:
        suspicious_peak_count = report.suspicious_peak_count
    return NMR2DRunRecord(
        id=row.id,
        created_at=row.created_at,
        user_id=row.user_id,
        sample_pk=getattr(row, "sample_pk", None) if getattr(row, "sample_pk", None) is not None else row.analysis_id,
        filename=filename,
        experiment_detected=experiment_detected,  # type: ignore[arg-type]
        analysis_id=row.analysis_id,
        sample_id=row.sample_id,
        experiments=experiments,  # type: ignore[list-item]
        peak_count=row.peak_count,
        evidence_score=evidence_score,
        suspicious_peak_count=suspicious_peak_count,
        overall_score=row.overall_score,
        review_status=row.review_status,
        metadata=metadata,
        report=report,
    )


def audit_event(
    session_factory: sessionmaker[Session],
    *,
    event_type: str,
    message: str,
    actor_user_id: int | None = None,
    actor_email: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    metadata: dict[str, object] | None = None,
) -> int:
    with session_scope(session_factory) as session:
        row = AuditEventORM(
            event_type=event_type,
            message=message,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=json.dumps(metadata or {}),
        )
        session.add(row)
        session.flush()
        return int(row.id)


def list_audit_events(
    session_factory: sessionmaker[Session],
    *,
    limit: int = 100,
    actor_user_id: int | None = None,
    event_type: str | None = None,
    event_types: list[str] | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    since: datetime | None = None,
) -> list[AuditEventRecord]:
    """Query the audit-event log with optional filters.

    ``event_type`` (singular) matches one type; ``event_types`` (plural,
    v0.6.9) matches a set via SQL ``IN`` — used by the graduation
    history endpoint to fetch ``admin.gsd_graduate_user`` plus
    ``admin.gsd_ungraduate_user`` in a single query.  If both are
    supplied, they AND together (event must equal ``event_type`` AND be
    in ``event_types``); this is intentional so callers can layer
    filters without one silently overriding the other.
    """

    with session_scope(session_factory) as session:
        stmt = select(AuditEventORM).order_by(AuditEventORM.id.desc()).limit(limit)
        if actor_user_id is not None:
            stmt = stmt.where(AuditEventORM.actor_user_id == actor_user_id)
        if event_type is not None:
            stmt = stmt.where(AuditEventORM.event_type == event_type)
        if event_types is not None:
            stmt = stmt.where(AuditEventORM.event_type.in_(event_types))
        if entity_type is not None:
            stmt = stmt.where(AuditEventORM.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditEventORM.entity_id == entity_id)
        if since is not None:
            # ``audit_events.created_at`` is timestamp-with-timezone in
            # production (Postgres) and naive UTC in the SQLite test
            # harness; both compare correctly against a tz-aware UTC
            # ``datetime`` so callers should pass a tz-aware value.
            stmt = stmt.where(AuditEventORM.created_at >= since)
        rows = list(session.scalars(stmt).all())
        return [_audit_to_record(row) for row in rows]


def build_evidence_report(
    session_factory: sessionmaker[Session],
    *,
    analysis_id: int,
    user_id: int | None = None,
) -> AnalysisEvidenceReport | None:
    full_record = get_full_analysis_by_id(session_factory, analysis_id, user_id=user_id)
    if full_record is None:
        return None
    review_decisions = list_review_decisions(session_factory, analysis_id=analysis_id, limit=200)
    audit_events = list_audit_events(session_factory, limit=200, entity_type="analysis", entity_id=analysis_id)
    notes = list(full_record.full_report.notes)
    impurity_candidates = [note for note in notes if "impur" in note.lower()]
    raw_fid_processing = None
    for event in audit_events:
        if event.event_type == "fid.process":
            candidate = event.metadata.get("fid_processing")
            if isinstance(candidate, dict):
                raw_fid_processing = candidate
                break
    nmr2d_evidence = list_nmr2d_evidence_sections_for_analysis(
        session_factory,
        analysis_id=analysis_id,
        user_id=user_id,
    )
    return AnalysisEvidenceReport(
        analysis=full_record,
        structure=full_record.full_report.structure,
        parsed_nmr_text=full_record.nmr_text,
        parsed_peaks=list(full_record.full_report.peaks),
        spectrum_derived_matched_peaks=list(full_record.full_report.peaks),
        unmatched_peaks=[],
        impurity_candidates=impurity_candidates,
        confidence_notes=notes,
        review_decisions=review_decisions,
        audit_events=audit_events,
        audit_metadata={
            "analysis_id": analysis_id,
            "job_id": full_record.job_id,
            "created_at": full_record.created_at.isoformat(),
            "review_status": full_record.review_status,
            "review_decision_count": len(review_decisions),
            "audit_event_count": len(audit_events),
            "raw_fid_processing": raw_fid_processing,
            "nmr2d_evidence_links": [
                {
                    "run_id": section.run_id,
                    "report_url": section.report_url,
                    "experiment_type": section.experiment_type,
                    "human_review_status": section.human_review_status,
                }
                for section in nmr2d_evidence
            ],
            "persistence_note": "Current stored analyses preserve the final analyzed peak list and report metadata. Raw spectrum-only mismatch groups are not persisted for older records.",
        },
        nmr2d_evidence=nmr2d_evidence,
        time_saved_estimate=full_record.hours_saved_estimate,
    )


def create_report_from_analysis(
    session_factory: sessionmaker[Session],
    *,
    analysis_id: int,
    user_id: int | None = None,
) -> StoredReportRecord | None:
    report = build_evidence_report(session_factory, analysis_id=analysis_id, user_id=user_id)
    if report is None:
        return None
    with session_scope(session_factory) as session:
        analysis = session.get(AnalysisORM, analysis_id)
        if analysis is None:
            return None
        if user_id is not None and analysis.user_id != user_id:
            return None
        existing_versions = int(
            session.scalar(
                select(func.count()).select_from(ReportORM).where(ReportORM.analysis_id == analysis_id)
            )
            or 0
        )
        row = ReportORM(
            analysis_id=analysis_id,
            user_id=analysis.user_id,
            version=existing_versions + 1,
            title=f"Evidence Report #{analysis_id} v{existing_versions + 1}",
            report_json=report.model_dump_json(),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _report_to_record(row)


def get_report_by_id(
    session_factory: sessionmaker[Session],
    *,
    report_id: int,
    user_id: int | None = None,
) -> StoredReportRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(ReportORM, report_id)
        if row is None:
            return None
        if user_id is not None:
            analysis = session.get(AnalysisORM, row.analysis_id)
            if row.user_id != user_id and (analysis is None or analysis.user_id != user_id):
                return None
        return _report_to_record(row)


def submit_review_decision(
    session_factory: sessionmaker[Session],
    *,
    analysis_id: int,
    reviewer_user_id: int,
    action: str,
    comment: str | None = None,
    final_label: str | None = None,
    hours_saved_estimate: float | None = None,
) -> ReviewDecisionRecord:
    action_to_status = {
        "approve": "approved",
        "reject": "rejected",
        "override": "approved",
        "request_changes": "needs_revision",
    }
    new_status = action_to_status.get(action, "needs_revision")
    with session_scope(session_factory) as session:
        row = session.get(AnalysisORM, analysis_id)
        if row is None:
            raise ValueError("Analysis not found.")
        previous_status = row.review_status
        previous_label = row.final_label or row.label
        row.review_status = new_status
        row.reviewer_user_id = reviewer_user_id
        row.reviewed_at = utcnow()
        row.review_comment = comment
        row.final_label = final_label or previous_label
        if hours_saved_estimate is not None:
            row.hours_saved_estimate = hours_saved_estimate
        decision = ReviewDecisionORM(
            analysis_id=row.id,
            reviewer_user_id=reviewer_user_id,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            comment=comment,
            previous_label=previous_label,
            final_label=row.final_label,
        )
        session.add(decision)
        session.add(
            AuditEventORM(
                event_type="review.decision",
                message=f"Review decision '{action}' recorded.",
                actor_user_id=reviewer_user_id,
                entity_type="analysis",
                entity_id=row.id,
                metadata_json=json.dumps(
                    {
                        "previous_status": previous_status,
                        "new_status": new_status,
                        "previous_label": previous_label,
                        "final_label": row.final_label,
                    }
                ),
            )
        )
        session.flush()
        session.refresh(decision)
        return _review_to_record(decision)


def list_review_queue(
    session_factory: sessionmaker[Session],
    *,
    limit: int = 50,
    review_status: str | None = None,
    reviewer_user_id: int | None = None,
) -> list[ReviewQueueItem]:
    with session_scope(session_factory) as session:
        stmt = select(AnalysisORM).order_by(AnalysisORM.id.desc()).limit(limit)
        if review_status is not None:
            stmt = stmt.where(AnalysisORM.review_status == review_status)
        if reviewer_user_id is not None:
            stmt = stmt.where(AnalysisORM.reviewer_user_id == reviewer_user_id)
        rows = list(session.scalars(stmt).all())
        items: list[ReviewQueueItem] = []
        for row in rows:
            record = _analysis_to_record(row)
            evidence = list(json.loads(row.notes_json))
            items.append(
                ReviewQueueItem(
                    analysis=record,
                    evidence_notes=evidence,
                    recommended_action="needs_revision" if row.label == "invalid_input" else "approved" if row.confidence >= 0.9 else "pending_review",
                )
            )
        return items


def list_review_decisions(
    session_factory: sessionmaker[Session],
    *,
    analysis_id: int | None = None,
    reviewer_user_id: int | None = None,
    limit: int = 100,
) -> list[ReviewDecisionRecord]:
    with session_scope(session_factory) as session:
        stmt = select(ReviewDecisionORM).order_by(ReviewDecisionORM.id.desc()).limit(limit)
        if analysis_id is not None:
            stmt = stmt.where(ReviewDecisionORM.analysis_id == analysis_id)
        if reviewer_user_id is not None:
            stmt = stmt.where(ReviewDecisionORM.reviewer_user_id == reviewer_user_id)
        rows = list(session.scalars(stmt).all())
        return [_review_to_record(row) for row in rows]


def list_admin_users(session_factory: sessionmaker[Session], *, limit: int = 100) -> list[AdminUserRecord]:
    with session_scope(session_factory) as session:
        users = list(session.scalars(select(UserORM).order_by(UserORM.id.desc()).limit(limit)).all())
        results: list[AdminUserRecord] = []
        for user in users:
            analyses_count = session.scalar(select(func.count()).select_from(AnalysisORM).where(AnalysisORM.user_id == user.id)) or 0
            jobs_count = session.scalar(select(func.count()).select_from(JobORM).where(JobORM.user_id == user.id)) or 0
            results.append(
                AdminUserRecord(
                    id=user.id,
                    email=user.email,
                    is_active=user.is_active,
                    is_admin=user.is_admin,
                    is_verified=user.is_verified,
                    created_at=user.created_at,
                    analyses_count=int(analyses_count),
                    jobs_count=int(jobs_count),
                    gsd_graduated_at=user.gsd_graduated_at,
                )
            )
        return results


def set_user_admin_status(session_factory: sessionmaker[Session], *, user_id: int, is_admin: bool) -> UserPublic:
    with session_scope(session_factory) as session:
        user = session.get(UserORM, user_id)
        if user is None:
            raise ValueError("User not found.")
        user.is_admin = is_admin
        session.flush()
        session.refresh(user)
        return _user_to_public(user)


def count_gsd_graduated_users(
    session_factory: sessionmaker[Session],
    *,
    actor_user_id: int | None = None,
) -> int:
    """Count users with ``gsd_graduated_at IS NOT NULL`` (v0.6.8).

    Backs the ``graduated_user_count`` field on
    ``SpectrumGSDTelemetrySummary``.  When ``actor_user_id`` is set,
    restricts the count to that one user (returns 0 or 1, cleanly
    answering "is this tenant graduated?").  Cheap query — single
    indexed COUNT — so calling it inline from the rollup endpoint
    does not move latency meaningfully.
    """

    with session_scope(session_factory) as session:
        stmt = select(func.count()).select_from(UserORM).where(
            UserORM.gsd_graduated_at.is_not(None)
        )
        if actor_user_id is not None:
            stmt = stmt.where(UserORM.id == actor_user_id)
        return int(session.scalar(stmt) or 0)


def set_user_gsd_graduation(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    graduated: bool,
) -> tuple[UserPublic, datetime | None]:
    """Set or clear the per-tenant GSD graduation flag.

    Returns the updated ``UserPublic`` plus the *previous*
    ``gsd_graduated_at`` value so the caller can emit a before/after
    audit event without an extra read.  ``graduated=True`` sets the
    column to ``utcnow()`` (idempotent: re-setting on an already-
    graduated user leaves the original timestamp in place); ``False``
    clears it back to ``None``.

    Idempotent on the "already graduated" path so the admin endpoint
    can be safely retried without overwriting the original graduation
    timestamp (which dashboards may already be displaying).
    """

    with session_scope(session_factory) as session:
        user = session.get(UserORM, user_id)
        if user is None:
            raise ValueError("User not found.")
        previous = user.gsd_graduated_at
        if graduated:
            # Idempotent: if already graduated, keep the original
            # timestamp so dashboards' "graduated since YYYY-MM-DD"
            # labels stay stable across admin retries.
            if previous is None:
                user.gsd_graduated_at = utcnow()
        else:
            user.gsd_graduated_at = None
        session.flush()
        session.refresh(user)
        return _user_to_public(user), previous


def get_metrics_summary(session_factory: sessionmaker[Session]) -> MetricsSummary:
    with session_scope(session_factory) as session:
        total_analyses = int(session.scalar(select(func.count()).select_from(AnalysisORM)) or 0)
        total_jobs = int(session.scalar(select(func.count()).select_from(JobORM)) or 0)
        pending_review = int(session.scalar(select(func.count()).select_from(AnalysisORM).where(AnalysisORM.review_status == "pending_review")) or 0)
        approved_reviews = int(session.scalar(select(func.count()).select_from(AnalysisORM).where(AnalysisORM.review_status == "approved")) or 0)
        rejected_reviews = int(session.scalar(select(func.count()).select_from(AnalysisORM).where(AnalysisORM.review_status == "rejected")) or 0)
        overrides = int(session.scalar(select(func.count()).select_from(ReviewDecisionORM).where(ReviewDecisionORM.action == "override")) or 0)
        validation_failures = int(session.scalar(select(func.count()).select_from(AnalysisORM).where(AnalysisORM.label == "invalid_input")) or 0)
        likely_impurity_flags = int(session.scalar(select(func.count()).select_from(AnalysisORM).where(AnalysisORM.label == "possible_impurity_or_incorrect_assignment")) or 0)
        hours_saved_estimate = float(session.scalar(select(func.coalesce(func.sum(AnalysisORM.hours_saved_estimate), 0.0))) or 0.0)

    automation_rate = 0.0 if total_analyses == 0 else max(0.0, min(1.0, (total_analyses - pending_review) / total_analyses))
    cards = [
        MetricCard(key="analyses", label="Analyses run", value=total_analyses),
        MetricCard(key="jobs", label="Jobs processed", value=total_jobs),
        MetricCard(key="pending_review", label="Pending review", value=pending_review),
        MetricCard(key="hours_saved", label="Estimated hours saved", value=round(hours_saved_estimate, 2), unit="hours"),
        MetricCard(key="automation_rate", label="Automation rate", value=round(automation_rate * 100, 1), unit="%"),
    ]
    return MetricsSummary(
        total_analyses=total_analyses,
        total_jobs=total_jobs,
        pending_review=pending_review,
        approved_reviews=approved_reviews,
        rejected_reviews=rejected_reviews,
        overrides=overrides,
        validation_failures=validation_failures,
        likely_impurity_flags=likely_impurity_flags,
        hours_saved_estimate=round(hours_saved_estimate, 2),
        automation_rate=automation_rate,
        cards=cards,
    )


def get_admin_system_summary(
    session_factory: sessionmaker[Session],
    *,
    queue_backend: str,
    redis_configured: bool,
) -> AdminSystemSummary:
    with session_scope(session_factory) as session:
        users = int(session.scalar(select(func.count()).select_from(UserORM)) or 0)
        admins = int(session.scalar(select(func.count()).select_from(UserORM).where(UserORM.is_admin.is_(True))) or 0)
        active_users = int(session.scalar(select(func.count()).select_from(UserORM).where(UserORM.is_active.is_(True))) or 0)
        analyses = int(session.scalar(select(func.count()).select_from(AnalysisORM)) or 0)
        jobs = int(session.scalar(select(func.count()).select_from(JobORM)) or 0)
        pending_review = int(session.scalar(select(func.count()).select_from(AnalysisORM).where(AnalysisORM.review_status == "pending_review")) or 0)
        audit_events = int(session.scalar(select(func.count()).select_from(AuditEventORM)) or 0)
    return AdminSystemSummary(
        users=users,
        admins=admins,
        active_users=active_users,
        analyses=analyses,
        jobs=jobs,
        pending_review=pending_review,
        audit_events=audit_events,
        queue_backend=queue_backend,
        redis_configured=redis_configured,
    )
