from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    SpectraCheckAuditEventRecord,
    SpectraCheckEvidenceCreate,
    SpectraCheckEvidenceRecord,
    SpectraCheckEvidenceUpdate,
    SpectraCheckProjectCreate,
    SpectraCheckProjectRecord,
    SpectraCheckProjectUpdate,
    SpectraCheckReportCreate,
    SpectraCheckReportRecord,
    SpectraCheckReviewCreate,
    SpectraCheckReviewDecisionRecord,
    SpectraCheckSampleCreate,
    SpectraCheckSampleRecord,
    SpectraCheckSampleUpdate,
    SpectraCheckSessionCreate,
    SpectraCheckSessionRecord,
    SpectraCheckSessionStatus,
    SpectraCheckSessionUpdate,
    SpectraCheckUnifiedEvidenceRecord,
    SpectraCheckUnifiedEvidenceSave,
)
from .orm import (
    SpectraCheckAuditEventORM,
    SpectraCheckEvidenceRecordORM,
    SpectraCheckProjectORM,
    SpectraCheckReportRecordORM,
    SpectraCheckReviewDecisionORM,
    SpectraCheckSampleORM,
    SpectraCheckSessionORM,
    utcnow,
)


class SpectraCheckPersistenceError(ValueError):
    pass


_FILE_BYTES_KEYS = {
    "archive_bytes",
    "bytes_base64",
    "file_bytes",
    "file_content",
    "raw_bytes",
    "raw_file_content",
    "upload_bytes",
}


def _json_dump(value: Any, *, default: Any) -> str:
    return json.dumps(default if value is None else value, sort_keys=True, separators=(",", ":"))


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def _assert_no_uploaded_file_bytes(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise SpectraCheckPersistenceError(f"{path} cannot contain uploaded file bytes.")
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in _FILE_BYTES_KEYS:
                raise SpectraCheckPersistenceError(
                    f"{path}.{key} appears to contain uploaded file bytes; store file hashes or provenance instead."
                )
            _assert_no_uploaded_file_bytes(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_no_uploaded_file_bytes(nested, path=f"{path}[{index}]")


def _project_visible(row: SpectraCheckProjectORM | None, *, owner_scope_id: int | None) -> bool:
    return row is not None and (owner_scope_id is None or row.owner_id == owner_scope_id)


def _get_project(
    session: Session,
    project_id: int,
    *,
    owner_scope_id: int | None,
) -> SpectraCheckProjectORM | None:
    row = session.get(SpectraCheckProjectORM, project_id)
    return row if _project_visible(row, owner_scope_id=owner_scope_id) else None


def _get_sample_by_identity(
    session: Session,
    sample_identity: str | int,
    *,
    owner_scope_id: int | None,
) -> SpectraCheckSampleORM | None:
    identity = str(sample_identity).strip()
    if not identity:
        return None
    if identity.isdigit():
        row = session.get(SpectraCheckSampleORM, int(identity))
        if row is not None and _project_visible(row.project, owner_scope_id=owner_scope_id):
            return row
    stmt = (
        select(SpectraCheckSampleORM)
        .join(SpectraCheckProjectORM)
        .where(SpectraCheckSampleORM.sample_id == identity)
        .order_by(SpectraCheckSampleORM.updated_at.desc(), SpectraCheckSampleORM.id.desc())
        .limit(1)
    )
    if owner_scope_id is not None:
        stmt = stmt.where(SpectraCheckProjectORM.owner_id == owner_scope_id)
    return session.scalar(stmt)


def _get_session(
    session: Session,
    session_id: int,
    *,
    owner_scope_id: int | None,
) -> SpectraCheckSessionORM | None:
    row = session.get(SpectraCheckSessionORM, session_id)
    if row is None or not _project_visible(row.project, owner_scope_id=owner_scope_id):
        return None
    return row


def _project_to_record(row: SpectraCheckProjectORM) -> SpectraCheckProjectRecord:
    return SpectraCheckProjectRecord(
        id=row.id,
        name=row.name,
        description=row.description,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        owner_id=row.owner_id,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Project stores SpectraCheck session state and does not alter scientific evidence."],
    )


def _sample_to_record(row: SpectraCheckSampleORM) -> SpectraCheckSampleRecord:
    return SpectraCheckSampleRecord(
        id=row.id,
        project_id=row.project_id,
        sample_id=row.sample_id,
        display_name=row.display_name,
        molecule_name=row.molecule_name,
        solvent=row.solvent,
        notes=row.notes,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes_list=["Sample persistence stores references and metadata, not uploaded file bytes."],
    )


def _session_to_record(row: SpectraCheckSessionORM) -> SpectraCheckSessionRecord:
    return SpectraCheckSessionRecord(
        id=row.id,
        project_id=row.project_id,
        sample_pk=row.sample_pk,
        sample_id=row.sample_id,
        title=row.title,
        status=row.status,  # type: ignore[arg-type]
        shared_inputs_json=_json_dict(row.shared_inputs_json),
        latest_unified_evidence_json=_json_dict(row.latest_unified_evidence_json)
        if row.latest_unified_evidence_json
        else None,
        latest_report_json=_json_dict(row.latest_report_json) if row.latest_report_json else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Session persistence reloads saved evidence for human review; it does not confirm identity."],
    )


def _evidence_to_record(row: SpectraCheckEvidenceRecordORM) -> SpectraCheckEvidenceRecord:
    return SpectraCheckEvidenceRecord(
        id=row.id,
        session_id=row.session_id,
        layer=row.layer,
        title=row.title,
        source_tab=row.source_tab,
        status=row.status,
        score=row.score,
        label=row.label,
        summary=row.summary,
        evidence_summary_json=_json_list(row.evidence_summary_json),
        contradictions_json=_json_list(row.contradictions_json),
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_list(row.notes_json),
        endpoint=row.endpoint,
        request_preview_json=_json_dict(row.request_preview_json) if row.request_preview_json else None,
        response_json=_json_dict(row.response_json),
        selected_for_unified=row.selected_for_unified,
        provenance_json=_json_dict(row.provenance_json),
        method_id=row.method_id,
        model_version_id=row.model_version_id,
        scoring_profile_id=row.scoring_profile_id,
        threshold_profile_id=row.threshold_profile_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _review_to_record(row: SpectraCheckReviewDecisionORM) -> SpectraCheckReviewDecisionRecord:
    return SpectraCheckReviewDecisionRecord(
        id=row.id,
        session_id=row.session_id,
        status=row.status,  # type: ignore[arg-type]
        reviewer_name=row.reviewer_name,
        reviewer_comment=row.reviewer_comment,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Review status records human assessment language and does not confirm identity by itself."],
    )


def _audit_to_record(row: SpectraCheckAuditEventORM) -> SpectraCheckAuditEventRecord:
    return SpectraCheckAuditEventRecord(
        id=row.id,
        session_id=row.session_id,
        event_type=row.event_type,
        message=row.message,
        actor_id=row.actor_id,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _report_to_record(row: SpectraCheckReportRecordORM) -> SpectraCheckReportRecord:
    return SpectraCheckReportRecord(
        id=row.id,
        session_id=row.session_id,
        report_title=row.report_title,
        status=row.status,
        report_json=_json_dict(row.report_json),
        report_html=row.report_html,
        report_sha256=row.report_sha256,
        method_id=row.method_id,
        model_version_id=row.model_version_id,
        scoring_profile_id=row.scoring_profile_id,
        threshold_profile_id=row.threshold_profile_id,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Stored report records are review artifacts and should not be read as identity confirmation."],
    )


def _add_session_audit(
    session: Session,
    *,
    session_id: int,
    event_type: str,
    message: str,
    actor_id: int | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        SpectraCheckAuditEventORM(
            session_id=session_id,
            event_type=event_type,
            message=message,
            actor_id=actor_id,
            metadata_json=_json_dump(metadata, default={}),
        )
    )


def create_spectracheck_project(
    session_factory: sessionmaker[Session],
    payload: SpectraCheckProjectCreate,
    *,
    owner_id: int | None,
) -> SpectraCheckProjectRecord:
    _assert_no_uploaded_file_bytes(payload.metadata_json, path="metadata_json")
    normalized_name = payload.name.strip()
    with session_scope(session_factory) as session:
        stmt = select(SpectraCheckProjectORM).where(SpectraCheckProjectORM.name == normalized_name)
        stmt = stmt.where(
            SpectraCheckProjectORM.owner_id.is_(None)
            if owner_id is None
            else SpectraCheckProjectORM.owner_id == owner_id
        )
        if session.scalar(stmt) is not None:
            raise SpectraCheckPersistenceError("A SpectraCheck project with that name already exists.")
        row = SpectraCheckProjectORM(
            name=normalized_name,
            description=payload.description,
            status=payload.status,
            owner_id=owner_id,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _project_to_record(row)


def list_spectracheck_projects(
    session_factory: sessionmaker[Session],
    *,
    owner_scope_id: int | None,
    limit: int = 200,
) -> list[SpectraCheckProjectRecord]:
    with session_scope(session_factory) as session:
        stmt = select(SpectraCheckProjectORM).order_by(
            SpectraCheckProjectORM.updated_at.desc(), SpectraCheckProjectORM.id.desc()
        )
        if owner_scope_id is not None:
            stmt = stmt.where(SpectraCheckProjectORM.owner_id == owner_scope_id)
        rows = list(session.scalars(stmt.limit(limit)).all())
        return [_project_to_record(row) for row in rows]


def get_spectracheck_project(
    session_factory: sessionmaker[Session],
    project_id: int,
    *,
    owner_scope_id: int | None,
) -> SpectraCheckProjectRecord | None:
    with session_scope(session_factory) as session:
        row = _get_project(session, project_id, owner_scope_id=owner_scope_id)
        return _project_to_record(row) if row is not None else None


def update_spectracheck_project(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: SpectraCheckProjectUpdate,
    *,
    owner_scope_id: int | None,
) -> SpectraCheckProjectRecord | None:
    if payload.metadata_json is not None:
        _assert_no_uploaded_file_bytes(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        row = _get_project(session, project_id, owner_scope_id=owner_scope_id)
        if row is None:
            return None
        fields = payload.model_fields_set
        if "name" in fields and payload.name is not None:
            row.name = payload.name
        if "description" in fields:
            row.description = payload.description
        if "status" in fields and payload.status is not None:
            row.status = payload.status
        if "metadata_json" in fields and payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json, default={})
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _project_to_record(row)


def create_spectracheck_sample(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: SpectraCheckSampleCreate,
    *,
    owner_scope_id: int | None,
) -> SpectraCheckSampleRecord:
    _assert_no_uploaded_file_bytes(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        project = _get_project(session, project_id, owner_scope_id=owner_scope_id)
        if project is None:
            raise KeyError(f"Project {project_id} not found.")
        existing = session.scalar(
            select(SpectraCheckSampleORM)
            .where(SpectraCheckSampleORM.project_id == project_id)
            .where(SpectraCheckSampleORM.sample_id == payload.sample_id)
        )
        if existing is not None:
            raise SpectraCheckPersistenceError("A sample with that sample_id already exists in this project.")
        row = SpectraCheckSampleORM(
            project_id=project_id,
            sample_id=payload.sample_id,
            display_name=payload.display_name,
            molecule_name=payload.molecule_name,
            solvent=payload.solvent,
            notes=payload.notes,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        project.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _sample_to_record(row)


def list_spectracheck_samples(
    session_factory: sessionmaker[Session],
    project_id: int,
    *,
    owner_scope_id: int | None,
    limit: int = 200,
) -> list[SpectraCheckSampleRecord]:
    with session_scope(session_factory) as session:
        project = _get_project(session, project_id, owner_scope_id=owner_scope_id)
        if project is None:
            raise KeyError(f"Project {project_id} not found.")
        rows = list(
            session.scalars(
                select(SpectraCheckSampleORM)
                .where(SpectraCheckSampleORM.project_id == project_id)
                .order_by(SpectraCheckSampleORM.updated_at.desc(), SpectraCheckSampleORM.id.desc())
                .limit(limit)
            ).all()
        )
        return [_sample_to_record(row) for row in rows]


def get_spectracheck_sample(
    session_factory: sessionmaker[Session],
    sample_identity: str | int,
    *,
    owner_scope_id: int | None,
) -> SpectraCheckSampleRecord | None:
    with session_scope(session_factory) as session:
        row = _get_sample_by_identity(session, sample_identity, owner_scope_id=owner_scope_id)
        return _sample_to_record(row) if row is not None else None


def update_spectracheck_sample(
    session_factory: sessionmaker[Session],
    sample_identity: str | int,
    payload: SpectraCheckSampleUpdate,
    *,
    owner_scope_id: int | None,
) -> SpectraCheckSampleRecord | None:
    if payload.metadata_json is not None:
        _assert_no_uploaded_file_bytes(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        row = _get_sample_by_identity(session, sample_identity, owner_scope_id=owner_scope_id)
        if row is None:
            return None
        fields = payload.model_fields_set
        for field in ("sample_id", "display_name", "molecule_name", "solvent", "notes", "status"):
            if field in fields:
                setattr(row, field, getattr(payload, field))
        if "metadata_json" in fields and payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json, default={})
        row.updated_at = utcnow()
        row.project.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _sample_to_record(row)


def create_spectracheck_session(
    session_factory: sessionmaker[Session],
    payload: SpectraCheckSessionCreate,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> SpectraCheckSessionRecord:
    _assert_no_uploaded_file_bytes(payload.shared_inputs_json, path="shared_inputs_json")
    _assert_no_uploaded_file_bytes(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        project = _get_project(session, payload.project_id, owner_scope_id=owner_scope_id)
        if project is None:
            raise KeyError(f"Project {payload.project_id} not found.")
        sample = None
        if payload.sample_pk is not None:
            sample = session.get(SpectraCheckSampleORM, payload.sample_pk)
            if sample is None or sample.project_id != project.id:
                sample = None
        if sample is None and payload.sample_id:
            sample = session.scalar(
                select(SpectraCheckSampleORM)
                .where(SpectraCheckSampleORM.project_id == project.id)
                .where(SpectraCheckSampleORM.sample_id == payload.sample_id)
                .limit(1)
            )
        if sample is None:
            raise KeyError("Sample not found for SpectraCheck session.")
        row = SpectraCheckSessionORM(
            project_id=project.id,
            sample_pk=sample.id,
            sample_id=payload.sample_id or sample.sample_id,
            title=payload.title,
            status=payload.status,
            shared_inputs_json=_json_dump(payload.shared_inputs_json, default={}),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        project.updated_at = utcnow()
        sample.updated_at = utcnow()
        session.flush()
        _add_session_audit(
            session,
            session_id=row.id,
            event_type="spectracheck.session.create",
            message="SpectraCheck session created for persisted evidence review.",
            actor_id=actor_id,
            metadata={"project_id": project.id, "sample_pk": sample.id, "sample_id": row.sample_id},
        )
        session.refresh(row)
        return _session_to_record(row)


def list_spectracheck_sessions(
    session_factory: sessionmaker[Session],
    *,
    owner_scope_id: int | None,
    project_id: int | None = None,
    sample_pk: int | None = None,
    limit: int = 200,
) -> list[SpectraCheckSessionRecord]:
    with session_scope(session_factory) as session:
        stmt = select(SpectraCheckSessionORM).join(SpectraCheckProjectORM).order_by(
            SpectraCheckSessionORM.updated_at.desc(), SpectraCheckSessionORM.id.desc()
        )
        if owner_scope_id is not None:
            stmt = stmt.where(SpectraCheckProjectORM.owner_id == owner_scope_id)
        if project_id is not None:
            stmt = stmt.where(SpectraCheckSessionORM.project_id == project_id)
        if sample_pk is not None:
            stmt = stmt.where(SpectraCheckSessionORM.sample_pk == sample_pk)
        rows = list(session.scalars(stmt.limit(limit)).all())
        return [_session_to_record(row) for row in rows]


def get_spectracheck_session(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
) -> SpectraCheckSessionRecord | None:
    with session_scope(session_factory) as session:
        row = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        return _session_to_record(row) if row is not None else None


def update_spectracheck_session(
    session_factory: sessionmaker[Session],
    session_id: int,
    payload: SpectraCheckSessionUpdate,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> SpectraCheckSessionRecord | None:
    for field in ("shared_inputs_json", "latest_unified_evidence_json", "latest_report_json", "metadata_json"):
        value = getattr(payload, field)
        if value is not None:
            _assert_no_uploaded_file_bytes(value, path=field)
    with session_scope(session_factory) as session:
        row = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if row is None:
            return None
        fields = payload.model_fields_set
        if "title" in fields:
            row.title = payload.title
        if "status" in fields and payload.status is not None:
            row.status = payload.status
        for field in ("shared_inputs_json", "latest_unified_evidence_json", "latest_report_json", "metadata_json"):
            if field in fields:
                setattr(row, field, _json_dump(getattr(payload, field), default={}))
        row.updated_at = utcnow()
        _add_session_audit(
            session,
            session_id=row.id,
            event_type="spectracheck.session.update",
            message="SpectraCheck session metadata updated.",
            actor_id=actor_id,
            metadata={"updated_fields": sorted(fields)},
        )
        session.flush()
        session.refresh(row)
        return _session_to_record(row)


def archive_spectracheck_session(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> bool:
    with session_scope(session_factory) as session:
        row = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if row is None:
            return False
        row.status = "archived"
        row.updated_at = utcnow()
        _add_session_audit(
            session,
            session_id=row.id,
            event_type="spectracheck.session.archive",
            message="SpectraCheck session archived.",
            actor_id=actor_id,
            metadata={"status": "archived"},
        )
        return True


def create_spectracheck_evidence(
    session_factory: sessionmaker[Session],
    session_id: int,
    payload: SpectraCheckEvidenceCreate,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> SpectraCheckEvidenceRecord:
    _assert_no_uploaded_file_bytes(payload.request_preview_json, path="request_preview_json")
    _assert_no_uploaded_file_bytes(payload.response_json, path="response_json")
    _assert_no_uploaded_file_bytes(payload.provenance_json, path="provenance_json")
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        row = SpectraCheckEvidenceRecordORM(
            session_id=session_id,
            layer=payload.layer,
            title=payload.title,
            source_tab=payload.source_tab,
            status=payload.status,
            score=payload.score,
            label=payload.label,
            summary=payload.summary,
            evidence_summary_json=_json_dump(payload.evidence_summary_json, default=[]),
            contradictions_json=_json_dump(payload.contradictions_json, default=[]),
            warnings_json=_json_dump(payload.warnings_json, default=[]),
            notes_json=_json_dump(payload.notes_json, default=[]),
            endpoint=payload.endpoint,
            request_preview_json=_json_dump(payload.request_preview_json, default={})
            if payload.request_preview_json is not None
            else None,
            response_json=_json_dump(payload.response_json, default={}),
            selected_for_unified=payload.selected_for_unified,
            provenance_json=_json_dump(payload.provenance_json, default={}),
            method_id=payload.method_id,
            model_version_id=payload.model_version_id,
            scoring_profile_id=payload.scoring_profile_id,
            threshold_profile_id=payload.threshold_profile_id,
        )
        session.add(row)
        if parent.status in {"draft", "analyzing"}:
            parent.status = "evidence_ready"
        parent.updated_at = utcnow()
        _add_session_audit(
            session,
            session_id=session_id,
            event_type="spectracheck.evidence.create",
            message="SpectraCheck evidence record saved.",
            actor_id=actor_id,
            metadata={
                "layer": payload.layer,
                "selected_for_unified": payload.selected_for_unified,
                "endpoint": payload.endpoint,
            },
        )
        session.flush()
        session.refresh(row)
        return _evidence_to_record(row)


def list_spectracheck_evidence(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
    limit: int = 500,
) -> list[SpectraCheckEvidenceRecord]:
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        rows = list(
            session.scalars(
                select(SpectraCheckEvidenceRecordORM)
                .where(SpectraCheckEvidenceRecordORM.session_id == session_id)
                .order_by(SpectraCheckEvidenceRecordORM.created_at.asc(), SpectraCheckEvidenceRecordORM.id.asc())
                .limit(limit)
            ).all()
        )
        return [_evidence_to_record(row) for row in rows]


def update_spectracheck_evidence(
    session_factory: sessionmaker[Session],
    session_id: int,
    evidence_id: int,
    payload: SpectraCheckEvidenceUpdate,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> SpectraCheckEvidenceRecord | None:
    for field in ("request_preview_json", "response_json", "provenance_json"):
        value = getattr(payload, field)
        if value is not None:
            _assert_no_uploaded_file_bytes(value, path=field)
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            return None
        row = session.get(SpectraCheckEvidenceRecordORM, evidence_id)
        if row is None or row.session_id != session_id:
            return None
        fields = payload.model_fields_set
        for field in (
            "layer",
            "title",
            "source_tab",
            "status",
            "score",
            "label",
            "summary",
            "endpoint",
            "selected_for_unified",
            "method_id",
            "model_version_id",
            "scoring_profile_id",
            "threshold_profile_id",
        ):
            if field in fields:
                setattr(row, field, getattr(payload, field))
        for field, default in (
            ("evidence_summary_json", []),
            ("contradictions_json", []),
            ("warnings_json", []),
            ("notes_json", []),
            ("request_preview_json", {}),
            ("response_json", {}),
            ("provenance_json", {}),
        ):
            if field in fields:
                value = getattr(payload, field)
                if field == "request_preview_json" and value is None:
                    row.request_preview_json = None
                elif value is not None:
                    setattr(row, field, _json_dump(value, default=default))
        row.updated_at = utcnow()
        parent.updated_at = utcnow()
        _add_session_audit(
            session,
            session_id=session_id,
            event_type="spectracheck.evidence.update",
            message="SpectraCheck evidence record updated.",
            actor_id=actor_id,
            metadata={"evidence_id": evidence_id, "updated_fields": sorted(fields)},
        )
        session.flush()
        session.refresh(row)
        return _evidence_to_record(row)


def delete_spectracheck_evidence(
    session_factory: sessionmaker[Session],
    session_id: int,
    evidence_id: int,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> bool:
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            return False
        row = session.get(SpectraCheckEvidenceRecordORM, evidence_id)
        if row is None or row.session_id != session_id:
            return False
        _add_session_audit(
            session,
            session_id=session_id,
            event_type="spectracheck.evidence.delete",
            message="SpectraCheck evidence record deleted.",
            actor_id=actor_id,
            metadata={"evidence_id": evidence_id, "layer": row.layer},
        )
        parent.updated_at = utcnow()
        session.delete(row)
        return True


def save_spectracheck_unified_evidence(
    session_factory: sessionmaker[Session],
    session_id: int,
    payload: SpectraCheckUnifiedEvidenceSave,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> SpectraCheckUnifiedEvidenceRecord | None:
    _assert_no_uploaded_file_bytes(payload.unified_evidence_json, path="unified_evidence_json")
    if payload.metadata_json is not None:
        _assert_no_uploaded_file_bytes(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        row = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if row is None:
            return None
        row.latest_unified_evidence_json = _json_dump(payload.unified_evidence_json, default={})
        if payload.metadata_json is not None:
            metadata = _json_dict(row.metadata_json)
            metadata["latest_unified_evidence_metadata"] = payload.metadata_json
            row.metadata_json = _json_dump(metadata, default={})
        for field in ("method_id", "model_version_id", "scoring_profile_id", "threshold_profile_id"):
            if field in payload.model_fields_set:
                setattr(row, field, getattr(payload, field))
        row.status = payload.status
        row.updated_at = utcnow()
        _add_session_audit(
            session,
            session_id=row.id,
            event_type="spectracheck.unified_evidence.save",
            message="Unified evidence snapshot saved to SpectraCheck session.",
            actor_id=actor_id,
            metadata={"status": row.status},
        )
        session.flush()
        session.refresh(row)
        return SpectraCheckUnifiedEvidenceRecord(
            session_id=row.id,
            latest_unified_evidence_json=_json_dict(row.latest_unified_evidence_json),
            status=row.status,  # type: ignore[arg-type]
            updated_at=row.updated_at,
            method_id=row.method_id,
            model_version_id=row.model_version_id,
            scoring_profile_id=row.scoring_profile_id,
            threshold_profile_id=row.threshold_profile_id,
            notes=["Unified evidence remains a review aid and does not confirm identity."],
        )


def get_spectracheck_unified_evidence(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
) -> SpectraCheckUnifiedEvidenceRecord | None:
    with session_scope(session_factory) as session:
        row = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if row is None:
            return None
        return SpectraCheckUnifiedEvidenceRecord(
            session_id=row.id,
            latest_unified_evidence_json=_json_dict(row.latest_unified_evidence_json)
            if row.latest_unified_evidence_json
            else None,
            status=row.status,  # type: ignore[arg-type]
            updated_at=row.updated_at,
            method_id=row.method_id,
            model_version_id=row.model_version_id,
            scoring_profile_id=row.scoring_profile_id,
            threshold_profile_id=row.threshold_profile_id,
            notes=["Unified evidence remains a review aid and does not confirm identity."],
        )


def _session_status_for_review(status: str) -> SpectraCheckSessionStatus:
    if status in {"approved_plausible", "approved_confirmed"}:
        return "approved"
    if status == "rejected":
        return "blocked"
    return "review_required"


def create_spectracheck_review(
    session_factory: sessionmaker[Session],
    session_id: int,
    payload: SpectraCheckReviewCreate,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> SpectraCheckReviewDecisionRecord:
    _assert_no_uploaded_file_bytes(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        row = SpectraCheckReviewDecisionORM(
            session_id=session_id,
            status=payload.status,
            reviewer_name=payload.reviewer_name,
            reviewer_comment=payload.reviewer_comment,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        parent.status = _session_status_for_review(payload.status)
        parent.updated_at = utcnow()
        _add_session_audit(
            session,
            session_id=session_id,
            event_type="spectracheck.review.create",
            message="SpectraCheck review decision saved.",
            actor_id=actor_id,
            metadata={"review_status": payload.status, "session_status": parent.status},
        )
        session.flush()
        session.refresh(row)
        return _review_to_record(row)


def list_spectracheck_reviews(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
    limit: int = 200,
) -> list[SpectraCheckReviewDecisionRecord]:
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        rows = list(
            session.scalars(
                select(SpectraCheckReviewDecisionORM)
                .where(SpectraCheckReviewDecisionORM.session_id == session_id)
                .order_by(SpectraCheckReviewDecisionORM.created_at.desc(), SpectraCheckReviewDecisionORM.id.desc())
                .limit(limit)
            ).all()
        )
        return [_review_to_record(row) for row in rows]


def list_spectracheck_audit_events(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
    limit: int = 500,
) -> list[SpectraCheckAuditEventRecord]:
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        rows = list(
            session.scalars(
                select(SpectraCheckAuditEventORM)
                .where(SpectraCheckAuditEventORM.session_id == session_id)
                .order_by(SpectraCheckAuditEventORM.created_at.asc(), SpectraCheckAuditEventORM.id.asc())
                .limit(limit)
            ).all()
        )
        return [_audit_to_record(row) for row in rows]


def _report_sha256(report_json: dict[str, Any]) -> str:
    payload = json.dumps(report_json, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def create_spectracheck_report(
    session_factory: sessionmaker[Session],
    session_id: int,
    payload: SpectraCheckReportCreate,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> SpectraCheckReportRecord:
    _assert_no_uploaded_file_bytes(payload.report_json, path="report_json")
    _assert_no_uploaded_file_bytes(payload.metadata_json, path="metadata_json")
    report_sha256 = payload.report_sha256 or _report_sha256(payload.report_json)
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        row = SpectraCheckReportRecordORM(
            session_id=session_id,
            report_title=payload.report_title,
            status=payload.status,
            report_json=_json_dump(payload.report_json, default={}),
            report_html=payload.report_html,
            report_sha256=report_sha256,
            method_id=payload.method_id,
            model_version_id=payload.model_version_id,
            scoring_profile_id=payload.scoring_profile_id,
            threshold_profile_id=payload.threshold_profile_id,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        parent.latest_report_json = row.report_json
        if parent.status in {"draft", "analyzing", "evidence_ready"}:
            parent.status = "review_required"
        parent.updated_at = utcnow()
        _add_session_audit(
            session,
            session_id=session_id,
            event_type="spectracheck.report.create",
            message="SpectraCheck report record saved.",
            actor_id=actor_id,
            metadata={"report_title": payload.report_title, "report_sha256": report_sha256},
        )
        session.flush()
        session.refresh(row)
        return _report_to_record(row)


def list_spectracheck_reports(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
    limit: int = 200,
) -> list[SpectraCheckReportRecord]:
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        rows = list(
            session.scalars(
                select(SpectraCheckReportRecordORM)
                .where(SpectraCheckReportRecordORM.session_id == session_id)
                .order_by(SpectraCheckReportRecordORM.created_at.desc(), SpectraCheckReportRecordORM.id.desc())
                .limit(limit)
            ).all()
        )
        return [_report_to_record(row) for row in rows]
