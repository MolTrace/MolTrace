from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    AnalysisJobCreate,
    AnalysisJobRecord,
    ArtifactRecord,
    FileRecord,
    JobEventRecord,
    ManagedFileKind,
    SessionFileLinkCreate,
    SessionFileLinkRecord,
)
from .orm import (
    AnalysisJobORM,
    ArtifactRecordORM,
    JobEventORM,
    ManagedFileRecordORM,
    SpectraCheckAuditEventORM,
    SpectraCheckProjectORM,
    SpectraCheckSessionFileLinkORM,
    SpectraCheckSessionORM,
    utcnow,
)
from .spectrum import SpectrumParseError, parse_processed_spectrum


class OrchestrationError(ValueError):
    pass


SUPPORTED_JOB_TYPES = {
    "nmr_processed_preview",
    "nmr_processed_analyze",
    "nmr_raw_fid_preview",
    "nmr_raw_fid_process",
    "hrms_candidate_match",
    "msms_annotation",
    "lcms_import",
    "lcms_feature_detection",
    "unified_confidence",
    "report_compose",
}

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
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


def _json_list(value: str | None) -> list[int]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        out: list[int] = []
        for item in parsed:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out
    return []


def _assert_no_uploaded_file_bytes(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise OrchestrationError(f"{path} cannot contain uploaded file bytes.")
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in _FILE_BYTES_KEYS:
                raise OrchestrationError(
                    f"{path}.{key} appears to contain uploaded file bytes; store file hashes or provenance instead."
                )
            _assert_no_uploaded_file_bytes(nested, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_no_uploaded_file_bytes(nested, path=f"{path}[{index}]")


def _safe_filename(filename: str | None) -> str:
    raw = (filename or "upload.bin").strip().replace("\\", "/").rsplit("/", 1)[-1]
    safe = _SAFE_FILENAME_RE.sub("_", raw).strip("._")
    return safe[:180] or "upload.bin"


def _storage_key_for(filename: str) -> str:
    return f"storage/uploads/{filename}"


def _storage_path_from_key(storage_root: Path, storage_key: str) -> Path:
    if storage_key.startswith("storage/"):
        return storage_root.parent / storage_key
    return storage_root / storage_key


def _file_path(row: ManagedFileRecordORM, storage_root: Path) -> Path:
    metadata = _json_dict(row.metadata_json)
    local_path = metadata.get("local_path")
    if isinstance(local_path, str) and local_path.strip():
        return Path(local_path)
    return _storage_path_from_key(storage_root, row.storage_key)


def _project_visible(row: SpectraCheckProjectORM | None, *, owner_scope_id: int | None) -> bool:
    return row is not None and (owner_scope_id is None or row.owner_id == owner_scope_id)


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


def _file_to_record(row: ManagedFileRecordORM) -> FileRecord:
    metadata = _json_dict(row.metadata_json)
    warnings = []
    if metadata.get("duplicate_of_file_id"):
        warnings.append("Duplicate SHA-256 upload; this record points to an existing immutable stored object.")
    return FileRecord(
        id=row.id,
        file_id=row.id,
        filename=row.filename,
        original_filename=row.original_filename,
        content_type=row.content_type,
        file_size_bytes=row.file_size_bytes,
        sha256=row.sha256,
        storage_backend=row.storage_backend,  # type: ignore[arg-type]
        storage_key=row.storage_key,
        file_kind=row.file_kind,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=metadata,
        warnings=warnings,
        notes=["Uploaded file bytes are stored in managed local storage, not project/session/evidence records."],
    )


def _link_to_record(row: SpectraCheckSessionFileLinkORM, file_row: ManagedFileRecordORM | None = None) -> SessionFileLinkRecord:
    return SessionFileLinkRecord(
        id=row.id,
        session_id=row.session_id,
        file_id=row.file_id,
        role=row.role,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        file=_file_to_record(file_row) if file_row is not None else None,
        notes=["Session file links store file identifiers and provenance metadata only."],
    )


def _artifact_ids(session: Session, job_id: int) -> list[int]:
    return [
        int(row_id)
        for row_id in session.scalars(
            select(ArtifactRecordORM.id)
            .where(ArtifactRecordORM.job_id == job_id)
            .order_by(ArtifactRecordORM.id.asc())
        ).all()
    ]


def _job_to_record(row: AnalysisJobORM, session: Session | None = None) -> AnalysisJobRecord:
    artifact_ids = _artifact_ids(session, row.id) if session is not None else []
    warnings = []
    if row.status == "failed" and row.error_message:
        warnings.append(row.error_message)
    return AnalysisJobRecord(
        id=row.id,
        job_id=row.id,
        session_id=row.session_id,
        sample_id=row.sample_id,
        project_id=row.project_id,
        job_type=row.job_type,
        status=row.status,  # type: ignore[arg-type]
        progress_percent=float(row.progress_percent),
        current_step=row.current_step,
        input_file_ids_json=_json_list(row.input_file_ids_json),
        parameters_json=_json_dict(row.parameters_json),
        result_json=_json_dict(row.result_json) if row.result_json else None,
        error_message=row.error_message,
        artifact_ids=artifact_ids,
        method_id=row.method_id,
        model_version_id=row.model_version_id,
        scoring_profile_id=row.scoring_profile_id,
        threshold_profile_id=row.threshold_profile_id,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=["Analysis jobs orchestrate existing evidence workflows and preserve human-review language."],
    )


def _event_to_record(row: JobEventORM) -> JobEventRecord:
    return JobEventRecord(
        id=row.id,
        job_id=row.job_id,
        event_type=row.event_type,
        message=row.message,
        progress_percent=row.progress_percent,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _artifact_to_record(row: ArtifactRecordORM) -> ArtifactRecord:
    return ArtifactRecord(
        id=row.id,
        artifact_id=row.id,
        job_id=row.job_id,
        session_id=row.session_id,
        artifact_type=row.artifact_type,  # type: ignore[arg-type]
        title=row.title,
        content_type=row.content_type,
        sha256=row.sha256,
        storage_key=row.storage_key,
        download_url=f"/artifacts/{row.id}/download",
        artifact_json=_json_dict(row.artifact_json) if row.artifact_json else None,
        method_id=row.method_id,
        model_version_id=row.model_version_id,
        scoring_profile_id=row.scoring_profile_id,
        threshold_profile_id=row.threshold_profile_id,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Artifacts are derived outputs for review; they do not confirm identity by themselves."],
    )


def upload_file_record(
    session_factory: sessionmaker[Session],
    *,
    original_filename: str,
    content_type: str | None,
    content: bytes,
    file_kind: ManagedFileKind,
    metadata_json: dict[str, Any] | None,
    storage_root: Path,
) -> FileRecord:
    metadata = dict(metadata_json or {})
    _assert_no_uploaded_file_bytes(metadata, path="metadata_json")
    sha256 = hashlib.sha256(content).hexdigest()
    safe_name = _safe_filename(original_filename)
    storage_root = Path(storage_root)
    upload_dir = storage_root / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    with session_scope(session_factory) as session:
        existing = session.scalar(
            select(ManagedFileRecordORM)
            .where(ManagedFileRecordORM.sha256 == sha256)
            .order_by(ManagedFileRecordORM.id.asc())
            .limit(1)
        )
        if existing is not None:
            metadata.update(
                {
                    "duplicate_of_file_id": existing.id,
                    "duplicate_sha256": True,
                    "local_path": _json_dict(existing.metadata_json).get("local_path"),
                    "raw_file_immutable": file_kind == "raw_fid",
                }
            )
            row = ManagedFileRecordORM(
                filename=safe_name,
                original_filename=original_filename or safe_name,
                content_type=content_type,
                file_size_bytes=len(content),
                sha256=sha256,
                storage_backend=existing.storage_backend,
                storage_key=existing.storage_key,
                file_kind=file_kind,
                metadata_json=_json_dump(metadata, default={}),
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            return _file_to_record(row)

        row = ManagedFileRecordORM(
            filename=safe_name,
            original_filename=original_filename or safe_name,
            content_type=content_type,
            file_size_bytes=len(content),
            sha256=sha256,
            storage_backend="local",
            storage_key="pending",
            file_kind=file_kind,
            metadata_json="{}",
        )
        session.add(row)
        session.flush()
        stored_filename = f"{row.id}_{safe_name}"
        storage_key = _storage_key_for(stored_filename)
        target = _storage_path_from_key(storage_root, storage_key)
        with target.open("xb") as handle:
            handle.write(content)
        metadata.update(
            {
                "local_path": str(target),
                "raw_file_immutable": file_kind == "raw_fid",
                "storage_policy": "Uploads are stored as immutable local objects and are not overwritten by jobs.",
            }
        )
        row.filename = stored_filename
        row.storage_key = storage_key
        row.metadata_json = _json_dump(metadata, default={})
        session.flush()
        session.refresh(row)
        return _file_to_record(row)


def list_file_records(
    session_factory: sessionmaker[Session],
    *,
    limit: int = 200,
    file_kind: str | None = None,
) -> list[FileRecord]:
    with session_scope(session_factory) as session:
        stmt = select(ManagedFileRecordORM).order_by(ManagedFileRecordORM.id.desc()).limit(limit)
        if file_kind:
            stmt = stmt.where(ManagedFileRecordORM.file_kind == file_kind)
        rows = list(session.scalars(stmt).all())
        return [_file_to_record(row) for row in rows]


def get_file_record(session_factory: sessionmaker[Session], file_id: int) -> FileRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(ManagedFileRecordORM, file_id)
        return _file_to_record(row) if row is not None else None


def get_file_download(
    session_factory: sessionmaker[Session],
    file_id: int,
    *,
    storage_root: Path,
) -> tuple[FileRecord, Path] | None:
    with session_scope(session_factory) as session:
        row = session.get(ManagedFileRecordORM, file_id)
        if row is None:
            return None
        path = _file_path(row, Path(storage_root))
        if not path.exists():
            raise FileNotFoundError("Managed file bytes are not available in local storage.")
        return (_file_to_record(row), path)


def delete_file_record(session_factory: sessionmaker[Session], file_id: int) -> bool:
    with session_scope(session_factory) as session:
        row = session.get(ManagedFileRecordORM, file_id)
        if row is None:
            return False
        session.execute(delete(SpectraCheckSessionFileLinkORM).where(SpectraCheckSessionFileLinkORM.file_id == file_id))
        session.delete(row)
        return True


def link_file_to_session(
    session_factory: sessionmaker[Session],
    session_id: int,
    payload: SessionFileLinkCreate,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> SessionFileLinkRecord:
    _assert_no_uploaded_file_bytes(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        file_row = session.get(ManagedFileRecordORM, payload.file_id)
        if file_row is None:
            raise KeyError(f"File {payload.file_id} not found.")
        existing = session.scalar(
            select(SpectraCheckSessionFileLinkORM)
            .where(SpectraCheckSessionFileLinkORM.session_id == session_id)
            .where(SpectraCheckSessionFileLinkORM.file_id == payload.file_id)
            .where(SpectraCheckSessionFileLinkORM.role == payload.role)
            .limit(1)
        )
        if existing is not None:
            return _link_to_record(existing, file_row)
        row = SpectraCheckSessionFileLinkORM(
            session_id=session_id,
            file_id=payload.file_id,
            role=payload.role,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        parent.updated_at = utcnow()
        _add_session_audit(
            session,
            session_id=session_id,
            event_type="spectracheck.file.link",
            message="Managed file linked to SpectraCheck session.",
            actor_id=actor_id,
            metadata={"file_id": payload.file_id, "role": payload.role, "sha256": file_row.sha256},
        )
        session.flush()
        session.refresh(row)
        return _link_to_record(row, file_row)


def list_session_file_links(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
    limit: int = 200,
) -> list[SessionFileLinkRecord]:
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        rows = list(
            session.scalars(
                select(SpectraCheckSessionFileLinkORM)
                .where(SpectraCheckSessionFileLinkORM.session_id == session_id)
                .order_by(SpectraCheckSessionFileLinkORM.created_at.asc(), SpectraCheckSessionFileLinkORM.id.asc())
                .limit(limit)
            ).all()
        )
        file_ids = [row.file_id for row in rows]
        files = {
            file_row.id: file_row
            for file_row in session.scalars(
                select(ManagedFileRecordORM).where(ManagedFileRecordORM.id.in_(file_ids))
            ).all()
        } if file_ids else {}
        return [_link_to_record(row, files.get(row.file_id)) for row in rows]


def delete_session_file_link(
    session_factory: sessionmaker[Session],
    session_id: int,
    file_id: int,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> bool:
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            return False
        rows = list(
            session.scalars(
                select(SpectraCheckSessionFileLinkORM)
                .where(SpectraCheckSessionFileLinkORM.session_id == session_id)
                .where(SpectraCheckSessionFileLinkORM.file_id == file_id)
            ).all()
        )
        if not rows:
            return False
        for row in rows:
            session.delete(row)
        parent.updated_at = utcnow()
        _add_session_audit(
            session,
            session_id=session_id,
            event_type="spectracheck.file.unlink",
            message="Managed file unlinked from SpectraCheck session.",
            actor_id=actor_id,
            metadata={"file_id": file_id},
        )
        return True


def _add_job_event(
    session: Session,
    *,
    job_id: int,
    event_type: str,
    message: str,
    progress_percent: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        JobEventORM(
            job_id=job_id,
            event_type=event_type,
            message=message,
            progress_percent=progress_percent,
            metadata_json=_json_dump(metadata, default={}),
        )
    )


def _create_artifact(
    session: Session,
    *,
    job_id: int | None,
    session_id: int | None,
    artifact_type: str,
    title: str,
    content_type: str,
    artifact_json: dict[str, Any] | None = None,
    storage_key: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> ArtifactRecordORM:
    serialized = _json_dump(artifact_json, default={}) if artifact_json is not None else None
    sha256 = (
        hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        if serialized is not None
        else None
    )
    row = ArtifactRecordORM(
        job_id=job_id,
        session_id=session_id,
        artifact_type=artifact_type,
        title=title,
        content_type=content_type,
        sha256=sha256,
        storage_key=storage_key,
        artifact_json=serialized,
        metadata_json=_json_dump(metadata_json or {}, default={}),
    )
    if job_id is not None:
        parent_job = session.get(AnalysisJobORM, job_id)
        if parent_job is not None:
            row.method_id = parent_job.method_id
            row.model_version_id = parent_job.model_version_id
            row.scoring_profile_id = parent_job.scoring_profile_id
            row.threshold_profile_id = parent_job.threshold_profile_id
    session.add(row)
    return row


def _execute_processed_preview(
    session: Session,
    *,
    row: AnalysisJobORM,
    storage_root: Path,
) -> dict[str, Any]:
    input_ids = _json_list(row.input_file_ids_json)
    if not input_ids:
        raise OrchestrationError("nmr_processed_preview requires at least one input file id.")
    file_row = session.get(ManagedFileRecordORM, input_ids[0])
    if file_row is None:
        raise OrchestrationError(f"Input file {input_ids[0]} not found.")
    path = _file_path(file_row, storage_root)
    if not path.exists():
        raise OrchestrationError("Input file bytes are not available in local storage.")
    params = _json_dict(row.parameters_json)
    try:
        preview = parse_processed_spectrum(
            filename=file_row.original_filename,
            content=path.read_bytes(),
            solvent=params.get("solvent"),
            frequency_mhz=params.get("spectrometer_frequency_mhz"),
            reference_nmr_text=params.get("nmr_text"),
        )
    except SpectrumParseError as exc:
        raise OrchestrationError(str(exc)) from exc
    result = preview.model_dump(mode="json")
    _create_artifact(
        session,
        job_id=row.id,
        session_id=row.session_id,
        artifact_type="spectrum_preview",
        title="Processed NMR spectrum preview",
        content_type="application/json",
        artifact_json=result,
        metadata_json={"input_file_id": file_row.id, "source_sha256": file_row.sha256},
    )
    return result


def _execute_processed_analyze(
    session: Session,
    *,
    row: AnalysisJobORM,
    storage_root: Path,
) -> dict[str, Any]:
    preview = _execute_processed_preview(session, row=row, storage_root=storage_root)
    peaks = list(preview.get("inferred_peaks") or [])
    result = {
        "sample_id": row.sample_id,
        "status": "requires_review",
        "label": "processed_nmr_evidence_requires_review",
        "human_review_required": True,
        "point_count": int(preview.get("point_count") or 0),
        "peak_count": len(peaks),
        "peaks": peaks,
        "evidence_summary": [
            f"Processed spectrum parsed with {int(preview.get('point_count') or 0)} point(s).",
            f"Heuristic peak picker returned {len(peaks)} peak candidate(s) for human review.",
        ],
        "warnings": list(preview.get("warnings") or []),
        "notes": [
            "This orchestration result summarizes processed NMR evidence and does not confirm identity.",
        ],
        "metadata": {
            "preview_artifact_created": True,
            "source_preview_metadata": preview.get("metadata") if isinstance(preview.get("metadata"), dict) else {},
        },
    }
    _create_artifact(
        session,
        job_id=row.id,
        session_id=row.session_id,
        artifact_type="peak_table",
        title="Processed NMR peak table",
        content_type="application/json",
        artifact_json=result,
    )
    return result


def _execute_job(
    session: Session,
    *,
    row: AnalysisJobORM,
    storage_root: Path,
) -> dict[str, Any]:
    if row.job_type not in SUPPORTED_JOB_TYPES:
        raise OrchestrationError(
            f"Unsupported job_type '{row.job_type}'. Supported job types: {', '.join(sorted(SUPPORTED_JOB_TYPES))}."
    )
    if row.job_type == "nmr_processed_preview":
        return _execute_processed_preview(session, row=row, storage_root=storage_root)
    if row.job_type == "nmr_processed_analyze":
        return _execute_processed_analyze(session, row=row, storage_root=storage_root)
    if row.job_type == "unified_confidence":
        params = _json_dict(row.parameters_json)
        result = params.get("unified_evidence_json") or params.get("result_json") or {
            "status": "requires_review",
            "human_review_required": True,
            "notes": ["Unified confidence job saved supplied parameters for review."],
        }
        if not isinstance(result, dict):
            raise OrchestrationError("unified_confidence requires a JSON object result payload.")
        _create_artifact(
            session,
            job_id=row.id,
            session_id=row.session_id,
            artifact_type="unified_evidence",
            title="Unified confidence evidence",
            content_type="application/json",
            artifact_json=result,
        )
        return result
    if row.job_type == "report_compose":
        params = _json_dict(row.parameters_json)
        report_json = params.get("report_json")
        if not isinstance(report_json, dict):
            raise OrchestrationError("report_compose requires parameters_json.report_json.")
        _create_artifact(
            session,
            job_id=row.id,
            session_id=row.session_id,
            artifact_type="report_json",
            title=str(params.get("report_title") or "Structure elucidation report JSON"),
            content_type="application/json",
            artifact_json=report_json,
        )
        return {"report_json": report_json, "human_review_required": True}
    raise OrchestrationError(
        f"Job type '{row.job_type}' is registered, but its synchronous execution adapter is not implemented yet."
    )


def create_analysis_job(
    session_factory: sessionmaker[Session],
    payload: AnalysisJobCreate,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
    storage_root: Path,
) -> AnalysisJobRecord:
    _assert_no_uploaded_file_bytes(payload.parameters_json, path="parameters_json")
    _assert_no_uploaded_file_bytes(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        parent_session: SpectraCheckSessionORM | None = None
        project_id = payload.project_id
        sample_id = payload.sample_id
        if payload.session_id is not None:
            parent_session = _get_session(session, payload.session_id, owner_scope_id=owner_scope_id)
            if parent_session is None:
                raise KeyError(f"Session {payload.session_id} not found.")
            project_id = project_id or parent_session.project_id
            sample_id = sample_id or parent_session.sample_id
        for file_id in payload.input_file_ids_json:
            if session.get(ManagedFileRecordORM, file_id) is None:
                raise KeyError(f"File {file_id} not found.")
        row = AnalysisJobORM(
            session_id=payload.session_id,
            sample_id=sample_id,
            project_id=project_id,
            job_type=payload.job_type,
            status="queued",
            progress_percent=0.0,
            current_step="queued",
            input_file_ids_json=_json_dump(payload.input_file_ids_json, default=[]),
            parameters_json=_json_dump(payload.parameters_json, default={}),
            method_id=payload.method_id,
            model_version_id=payload.model_version_id,
            scoring_profile_id=payload.scoring_profile_id,
            threshold_profile_id=payload.threshold_profile_id,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        _add_job_event(
            session,
            job_id=row.id,
            event_type="queued",
            message="Analysis job queued for local orchestration.",
            progress_percent=0.0,
        )
        row.status = "running"
        row.started_at = utcnow()
        row.current_step = "executing"
        row.progress_percent = 25.0
        _add_job_event(
            session,
            job_id=row.id,
            event_type="running",
            message="Analysis job started.",
            progress_percent=25.0,
        )
        try:
            result = _execute_job(session, row=row, storage_root=storage_root)
        except OrchestrationError as exc:
            row.status = "failed"
            row.progress_percent = 100.0
            row.current_step = "failed"
            row.error_message = str(exc)
            row.result_json = _json_dump(
                {
                    "status": "failed",
                    "error": str(exc),
                    "human_review_required": True,
                },
                default={},
            )
            _add_job_event(
                session,
                job_id=row.id,
                event_type="failed",
                message=str(exc),
                progress_percent=100.0,
            )
        else:
            row.status = "succeeded"
            row.progress_percent = 100.0
            row.current_step = "complete"
            row.result_json = _json_dump(result, default={})
            _add_job_event(
                session,
                job_id=row.id,
                event_type="succeeded",
                message="Analysis job completed and artifacts were recorded where applicable.",
                progress_percent=100.0,
            )
        row.finished_at = utcnow()
        if parent_session is not None:
            parent_session.updated_at = utcnow()
            _add_session_audit(
                session,
                session_id=parent_session.id,
                event_type="spectracheck.job.create",
                message="Analysis orchestration job created for SpectraCheck session.",
                actor_id=actor_id,
                metadata={"job_id": row.id, "job_type": row.job_type, "status": row.status},
            )
        session.flush()
        session.refresh(row)
        return _job_to_record(row, session)


def list_analysis_jobs(
    session_factory: sessionmaker[Session],
    *,
    owner_scope_id: int | None,
    limit: int = 200,
) -> list[AnalysisJobRecord]:
    with session_scope(session_factory) as session:
        stmt = select(AnalysisJobORM).outerjoin(SpectraCheckProjectORM, AnalysisJobORM.project_id == SpectraCheckProjectORM.id).order_by(
            AnalysisJobORM.id.desc()
        )
        if owner_scope_id is not None:
            stmt = stmt.where(
                (AnalysisJobORM.project_id.is_(None))
                | (SpectraCheckProjectORM.owner_id == owner_scope_id)
            )
        rows = list(session.scalars(stmt.limit(limit)).all())
        return [_job_to_record(row, session) for row in rows]


def get_analysis_job(
    session_factory: sessionmaker[Session],
    job_id: int,
    *,
    owner_scope_id: int | None,
) -> AnalysisJobRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(AnalysisJobORM, job_id)
        if row is None:
            return None
        if row.project_id is not None and owner_scope_id is not None:
            project = session.get(SpectraCheckProjectORM, row.project_id)
            if project is None or project.owner_id != owner_scope_id:
                return None
        return _job_to_record(row, session)


def cancel_analysis_job(
    session_factory: sessionmaker[Session],
    job_id: int,
    *,
    owner_scope_id: int | None,
) -> AnalysisJobRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(AnalysisJobORM, job_id)
        if row is None:
            return None
        if row.project_id is not None and owner_scope_id is not None:
            project = session.get(SpectraCheckProjectORM, row.project_id)
            if project is None or project.owner_id != owner_scope_id:
                return None
        if row.status in {"queued", "running"}:
            row.status = "canceled"
            row.current_step = "canceled"
            row.finished_at = utcnow()
            _add_job_event(
                session,
                job_id=row.id,
                event_type="canceled",
                message="Job cancellation requested. Local synchronous jobs may already have finished.",
                progress_percent=row.progress_percent,
            )
        else:
            _add_job_event(
                session,
                job_id=row.id,
                event_type="cancel_requested",
                message=f"Cancel requested after job reached status '{row.status}'.",
                progress_percent=row.progress_percent,
            )
        session.flush()
        session.refresh(row)
        return _job_to_record(row, session)


def list_job_events(
    session_factory: sessionmaker[Session],
    job_id: int,
    *,
    owner_scope_id: int | None,
    limit: int = 500,
) -> list[JobEventRecord] | None:
    with session_scope(session_factory) as session:
        row = session.get(AnalysisJobORM, job_id)
        if row is None:
            return None
        if row.project_id is not None and owner_scope_id is not None:
            project = session.get(SpectraCheckProjectORM, row.project_id)
            if project is None or project.owner_id != owner_scope_id:
                return None
        rows = list(
            session.scalars(
                select(JobEventORM)
                .where(JobEventORM.job_id == job_id)
                .order_by(JobEventORM.id.asc())
                .limit(limit)
            ).all()
        )
        return [_event_to_record(event) for event in rows]


def list_session_jobs(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
    limit: int = 200,
) -> list[AnalysisJobRecord]:
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        rows = list(
            session.scalars(
                select(AnalysisJobORM)
                .where(AnalysisJobORM.session_id == session_id)
                .order_by(AnalysisJobORM.id.desc())
                .limit(limit)
            ).all()
        )
        return [_job_to_record(row, session) for row in rows]


def get_artifact_record(
    session_factory: sessionmaker[Session],
    artifact_id: int,
) -> ArtifactRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(ArtifactRecordORM, artifact_id)
        return _artifact_to_record(row) if row is not None else None


def get_artifact_download(
    session_factory: sessionmaker[Session],
    artifact_id: int,
    *,
    storage_root: Path,
) -> tuple[ArtifactRecord, bytes, str] | None:
    with session_scope(session_factory) as session:
        row = session.get(ArtifactRecordORM, artifact_id)
        if row is None:
            return None
        record = _artifact_to_record(row)
        if row.storage_key:
            path = _storage_path_from_key(Path(storage_root), row.storage_key)
            if not path.exists():
                raise FileNotFoundError("Artifact bytes are not available in local storage.")
            return (record, path.read_bytes(), row.content_type)
        if row.artifact_json:
            return (record, row.artifact_json.encode("utf-8"), row.content_type)
        return (record, b"", row.content_type)


def list_session_artifacts(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    owner_scope_id: int | None,
    limit: int = 500,
) -> list[ArtifactRecord]:
    with session_scope(session_factory) as session:
        parent = _get_session(session, session_id, owner_scope_id=owner_scope_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        rows = list(
            session.scalars(
                select(ArtifactRecordORM)
                .where(ArtifactRecordORM.session_id == session_id)
                .order_by(ArtifactRecordORM.id.desc())
                .limit(limit)
            ).all()
        )
        return [_artifact_to_record(row) for row in rows]
