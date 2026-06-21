from __future__ import annotations

import base64
import csv
import hashlib
import json
import re
import zipfile
from fnmatch import fnmatch
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import orchestration_store as orch_store
from . import reaction_access
# `_dossier_owned_by` is the canonical session-scoped dossier-ownership predicate used by the
# cross-module routes the 7a8a52d fix landed; reusing it here keeps the body-id check identical.
from .product_orchestration_store import _dossier_owned_by
from .database import session_scope
from .models import (
    ConnectorCredentialReference,
    ConnectorCredentialReferenceCreate,
    ConnectorHealthCheck,
    ConnectorHealthCheckRequest,
    ConnectorRegistry,
    ConnectorRegistryCreate,
    ConnectorRegistryUpdate,
    ExternalObjectLink,
    ExternalObjectLinkCreate,
    ExternalSystemRecord,
    ExternalSystemRecordCreate,
    FileNormalizationRequest,
    FileNormalizationRun,
    FileNormalizationSourceFormat,
    FileNormalizationTargetFormat,
    IngestionFileInput,
    IngestionRun,
    IngestionRunCreate,
    InstrumentWatchFolder,
    InstrumentWatchFolderCreate,
    InstrumentWatchFolderScanRequest,
    InstrumentWatchFolderUpdate,
    IntegrationImportResponse,
    MappingTemplate,
    MappingTemplateCreate,
    MappingTemplateUpdate,
    OutboundSyncJob,
    OutboundSyncJobCreate,
    ReactionApprovedExperimentsExportRequest,
    ReactionExperimentTableImportRequest,
    RegulatoryImportSourceRequest,
    RegulatorySubmissionPackage,
    RegulatorySubmissionPackageCreate,
    SpectraCheckImportFileRequest,
    WebhookSubscription,
    WebhookSubscriptionCreate,
    WebhookSubscriptionUpdate,
)
from .orm import (
    ArtifactRecordORM,
    ConnectorCredentialReferenceORM,
    ConnectorHealthCheckORM,
    ConnectorRegistryORM,
    ExternalObjectLinkORM,
    ExternalSystemRecordORM,
    FileNormalizationRunORM,
    IngestionRunORM,
    InstrumentWatchFolderORM,
    ManagedFileRecordORM,
    MappingTemplateORM,
    OutboundSyncJobORM,
    ReactionExperimentORM,
    ReactionProjectORM,
    RegulatoryDossierORM,
    RegulatorySubmissionPackageORM,
    SpectraCheckProjectORM,
    SpectraCheckSessionORM,
    WebhookSubscriptionORM,
    utcnow,
)


class InteroperabilityError(ValueError):
    pass


_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|credential|password|secret|token)", re.IGNORECASE
)


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


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _int_list(value: str | None) -> list[int]:
    out: list[int] = []
    for item in _json_list(value):
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _scrub_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, child in value.items():
            if _SENSITIVE_KEY_RE.search(str(key)):
                scrubbed[str(key)] = "[redacted]"
            else:
                scrubbed[str(key)] = _scrub_sensitive(child)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_sensitive(item) for item in value]
    return value


def _safe_health_message(message: str | None) -> str | None:
    if message is None:
        return None
    if _SENSITIVE_KEY_RE.search(message):
        return "Connector health recorded; sensitive detail redacted."
    return message


def _connector_to_record(row: ConnectorRegistryORM) -> ConnectorRegistry:
    return ConnectorRegistry(
        id=row.id,
        connector_key=row.connector_key,
        display_name=row.display_name,
        connector_type=row.connector_type,
        target_program=row.target_program,
        status=row.status,
        config_schema_json=_json_dict(row.config_schema_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _credential_to_record(row: ConnectorCredentialReferenceORM) -> ConnectorCredentialReference:
    return ConnectorCredentialReference(
        id=row.id,
        connector_id=row.connector_id,
        credential_type=row.credential_type,
        secret_ref=row.secret_ref,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_scrub_sensitive(_json_dict(row.metadata_json)),
    )


def _health_to_record(row: ConnectorHealthCheckORM) -> ConnectorHealthCheck:
    return ConnectorHealthCheck(
        id=row.id,
        connector_id=row.connector_id,
        status=row.status,
        latency_ms=row.latency_ms,
        message=_safe_health_message(row.message),
        checked_at=row.checked_at,
        metadata_json=_scrub_sensitive(_json_dict(row.metadata_json)),
    )


def _watch_folder_to_record(row: InstrumentWatchFolderORM) -> InstrumentWatchFolder:
    return InstrumentWatchFolder(
        id=row.id,
        connector_id=row.connector_id,
        folder_path=row.folder_path,
        file_patterns_json=[str(item) for item in _json_list(row.file_patterns_json)] or ["*"],
        recursive=row.recursive,
        target_program=row.target_program,
        target_route=row.target_route,
        status=row.status,
        last_scan_at=row.last_scan_at,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _ingestion_run_to_record(row: IngestionRunORM) -> IngestionRun:
    return IngestionRun(
        id=row.id,
        connector_id=row.connector_id,
        watch_folder_id=row.watch_folder_id,
        source_system=row.source_system,
        source_path=row.source_path,
        status=row.status,
        discovered_count=row.discovered_count,
        ingested_count=row.ingested_count,
        skipped_count=row.skipped_count,
        failed_count=row.failed_count,
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        finished_at=row.finished_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _normalization_run_to_record(row: FileNormalizationRunORM) -> FileNormalizationRun:
    return FileNormalizationRun(
        id=row.id,
        file_id=row.file_id,
        source_format=row.source_format,
        target_format=row.target_format,
        status=row.status,
        output_artifact_id=row.output_artifact_id,
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        finished_at=row.finished_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _external_record_to_record(row: ExternalSystemRecordORM) -> ExternalSystemRecord:
    return ExternalSystemRecord(
        id=row.id,
        connector_id=row.connector_id,
        external_system=row.external_system,
        external_object_type=row.external_object_type,
        external_object_id=row.external_object_id,
        external_url=row.external_url,
        title=row.title,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _external_link_to_record(row: ExternalObjectLinkORM) -> ExternalObjectLink:
    return ExternalObjectLink(
        id=row.id,
        external_record_id=row.external_record_id,
        moltrace_resource_type=row.moltrace_resource_type,
        moltrace_resource_id=row.moltrace_resource_id,
        relation_type=row.relation_type,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _mapping_template_to_record(row: MappingTemplateORM) -> MappingTemplate:
    return MappingTemplate(
        id=row.id,
        connector_id=row.connector_id,
        name=row.name,
        source_type=row.source_type,
        target_type=row.target_type,
        field_map_json=_json_dict(row.field_map_json),
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _sync_job_to_record(row: OutboundSyncJobORM) -> OutboundSyncJob:
    return OutboundSyncJob(
        id=row.id,
        connector_id=row.connector_id,
        target_system=row.target_system,
        source_resource_type=row.source_resource_type,
        source_resource_id=row.source_resource_id,
        payload_summary_json=_scrub_sensitive(_json_dict(row.payload_summary_json)),
        status=row.status,
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        finished_at=row.finished_at,
        metadata_json=_scrub_sensitive(_json_dict(row.metadata_json)),
    )


def _webhook_to_record(row: WebhookSubscriptionORM) -> WebhookSubscription:
    return WebhookSubscription(
        id=row.id,
        connector_id=row.connector_id,
        name=row.name,
        event_types_json=[str(item) for item in _json_list(row.event_types_json)],
        target_url_hash=row.target_url_hash,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_scrub_sensitive(_json_dict(row.metadata_json)),
    )


def _submission_package_to_record(row: RegulatorySubmissionPackageORM) -> RegulatorySubmissionPackage:
    return RegulatorySubmissionPackage(
        id=row.id,
        dossier_id=row.dossier_id,
        report_id=row.report_id,
        package_type=row.package_type,
        status=row.status,
        file_ids_json=_int_list(row.file_ids_json),
        artifact_ids_json=_int_list(row.artifact_ids_json),
        package_manifest_json=_json_dict(row.package_manifest_json),
        package_sha256=row.package_sha256,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _ensure_connector(session: Session, connector_id: int) -> ConnectorRegistryORM:
    row = session.get(ConnectorRegistryORM, connector_id)
    if row is None:
        raise KeyError("Connector not found.")
    return row


def _file_record_metadata(row: ManagedFileRecordORM) -> dict[str, Any]:
    return _json_dict(row.metadata_json)


def create_connector(
    session_factory: sessionmaker[Session],
    payload: ConnectorRegistryCreate,
) -> ConnectorRegistry:
    with session_scope(session_factory) as session:
        row = ConnectorRegistryORM(
            connector_key=payload.connector_key.strip(),
            display_name=payload.display_name.strip(),
            connector_type=payload.connector_type,
            target_program=payload.target_program,
            status=payload.status,
            config_schema_json=_json_dump(payload.config_schema_json, default={}),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _connector_to_record(row)


def list_connectors(
    session_factory: sessionmaker[Session],
    *,
    status_filter: str | None = None,
    target_program: str | None = None,
    limit: int = 200,
) -> list[ConnectorRegistry]:
    with session_scope(session_factory) as session:
        stmt = select(ConnectorRegistryORM).order_by(ConnectorRegistryORM.id.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(ConnectorRegistryORM.status == status_filter)
        if target_program:
            stmt = stmt.where(ConnectorRegistryORM.target_program == target_program)
        return [_connector_to_record(row) for row in session.scalars(stmt).all()]


def get_connector(
    session_factory: sessionmaker[Session],
    connector_id: int,
) -> ConnectorRegistry | None:
    with session_scope(session_factory) as session:
        row = session.get(ConnectorRegistryORM, connector_id)
        return _connector_to_record(row) if row is not None else None


def update_connector(
    session_factory: sessionmaker[Session],
    connector_id: int,
    payload: ConnectorRegistryUpdate,
) -> ConnectorRegistry | None:
    with session_scope(session_factory) as session:
        row = session.get(ConnectorRegistryORM, connector_id)
        if row is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        for field in ("connector_key", "display_name", "connector_type", "target_program", "status"):
            if field in data:
                setattr(row, field, data[field])
        if "config_schema_json" in data:
            row.config_schema_json = _json_dump(data["config_schema_json"], default={})
        if "metadata_json" in data:
            row.metadata_json = _json_dump(data["metadata_json"], default={})
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _connector_to_record(row)


def create_connector_credential(
    session_factory: sessionmaker[Session],
    connector_id: int,
    payload: ConnectorCredentialReferenceCreate,
) -> ConnectorCredentialReference:
    with session_scope(session_factory) as session:
        _ensure_connector(session, connector_id)
        row = ConnectorCredentialReferenceORM(
            connector_id=connector_id,
            credential_type=payload.credential_type,
            secret_ref=payload.secret_ref,
            status=payload.status,
            metadata_json=_json_dump(_scrub_sensitive(payload.metadata_json), default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _credential_to_record(row)


def list_connector_credentials(
    session_factory: sessionmaker[Session],
    connector_id: int,
    *,
    limit: int = 100,
) -> list[ConnectorCredentialReference]:
    with session_scope(session_factory) as session:
        _ensure_connector(session, connector_id)
        stmt = (
            select(ConnectorCredentialReferenceORM)
            .where(ConnectorCredentialReferenceORM.connector_id == connector_id)
            .order_by(ConnectorCredentialReferenceORM.id.desc())
            .limit(limit)
        )
        return [_credential_to_record(row) for row in session.scalars(stmt).all()]


def create_connector_health_check(
    session_factory: sessionmaker[Session],
    connector_id: int,
    payload: ConnectorHealthCheckRequest,
) -> ConnectorHealthCheck:
    with session_scope(session_factory) as session:
        connector = _ensure_connector(session, connector_id)
        status = payload.status
        if status is None:
            status = "ok" if connector.status == "active" else "warning"
        message = payload.message
        if message is None:
            message = "Connector health recorded without exposing credentials."
        row = ConnectorHealthCheckORM(
            connector_id=connector_id,
            status=status,
            latency_ms=payload.latency_ms,
            message=_safe_health_message(message),
            metadata_json=_json_dump(_scrub_sensitive(payload.metadata_json), default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _health_to_record(row)


def list_connector_health_checks(
    session_factory: sessionmaker[Session],
    connector_id: int,
    *,
    limit: int = 100,
) -> list[ConnectorHealthCheck]:
    with session_scope(session_factory) as session:
        _ensure_connector(session, connector_id)
        stmt = (
            select(ConnectorHealthCheckORM)
            .where(ConnectorHealthCheckORM.connector_id == connector_id)
            .order_by(ConnectorHealthCheckORM.checked_at.desc(), ConnectorHealthCheckORM.id.desc())
            .limit(limit)
        )
        return [_health_to_record(row) for row in session.scalars(stmt).all()]


def create_watch_folder(
    session_factory: sessionmaker[Session],
    payload: InstrumentWatchFolderCreate,
) -> InstrumentWatchFolder:
    with session_scope(session_factory) as session:
        if payload.connector_id is not None:
            _ensure_connector(session, payload.connector_id)
        row = InstrumentWatchFolderORM(
            connector_id=payload.connector_id,
            folder_path=payload.folder_path,
            file_patterns_json=_json_dump(payload.file_patterns_json or ["*"], default=[]),
            recursive=payload.recursive,
            target_program=payload.target_program,
            target_route=payload.target_route,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _watch_folder_to_record(row)


def list_watch_folders(
    session_factory: sessionmaker[Session],
    *,
    status_filter: str | None = None,
    limit: int = 200,
) -> list[InstrumentWatchFolder]:
    with session_scope(session_factory) as session:
        stmt = select(InstrumentWatchFolderORM).order_by(InstrumentWatchFolderORM.id.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(InstrumentWatchFolderORM.status == status_filter)
        return [_watch_folder_to_record(row) for row in session.scalars(stmt).all()]


def get_watch_folder(
    session_factory: sessionmaker[Session],
    watch_folder_id: int,
) -> InstrumentWatchFolder | None:
    with session_scope(session_factory) as session:
        row = session.get(InstrumentWatchFolderORM, watch_folder_id)
        return _watch_folder_to_record(row) if row is not None else None


def update_watch_folder(
    session_factory: sessionmaker[Session],
    watch_folder_id: int,
    payload: InstrumentWatchFolderUpdate,
) -> InstrumentWatchFolder | None:
    with session_scope(session_factory) as session:
        row = session.get(InstrumentWatchFolderORM, watch_folder_id)
        if row is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        if data.get("connector_id") is not None:
            _ensure_connector(session, int(data["connector_id"]))
        for field in (
            "connector_id",
            "folder_path",
            "recursive",
            "target_program",
            "target_route",
            "status",
        ):
            if field in data:
                setattr(row, field, data[field])
        if "file_patterns_json" in data:
            row.file_patterns_json = _json_dump(data["file_patterns_json"], default=[])
        if "metadata_json" in data:
            row.metadata_json = _json_dump(data["metadata_json"], default={})
        session.flush()
        session.refresh(row)
        return _watch_folder_to_record(row)


def _content_from_input(file_input: IngestionFileInput) -> bytes:
    if file_input.content_base64 is not None:
        try:
            return base64.b64decode(file_input.content_base64, validate=True)
        except Exception as exc:
            raise InteroperabilityError(f"{file_input.filename}: content_base64 is not valid base64.") from exc
    return (file_input.content_text or "").encode("utf-8")


def _find_existing_file(
    session: Session,
    *,
    sha256: str,
    source_path: str | None,
) -> tuple[ManagedFileRecordORM | None, str | None]:
    existing = session.scalar(
        select(ManagedFileRecordORM)
        .where(ManagedFileRecordORM.sha256 == sha256)
        .order_by(ManagedFileRecordORM.id.asc())
        .limit(1)
    )
    if existing is not None:
        return existing, "sha256"
    if source_path:
        rows = session.scalars(
            select(ManagedFileRecordORM).order_by(ManagedFileRecordORM.id.desc()).limit(2000)
        ).all()
        for row in rows:
            metadata = _file_record_metadata(row)
            if metadata.get("source_path") == source_path:
                return row, "source_path"
    return None, None


def _file_kind_for_route(target_route: str) -> str:
    return {
        "processed_nmr": "processed_nmr",
        "raw_fid": "raw_fid",
        "nmr2d": "nmr2d_peak_table",
        "dept_apt": "dept_apt_peak_table",
        "msms": "ms_peak_table",
        "ms_raw": "ms_raw",
        "lcms": "lcms_peak_table",
        "lcms_raw": "lcms_raw",
        "spectrum_file": "spectrum_vendor",
        "regulatory_source": "report",
        "reaction_outcome": "other",
    }.get(target_route, "other")


def _finish_ingestion_status(
    *,
    discovered_count: int,
    ingested_count: int,
    skipped_count: int,
    failed_count: int,
) -> str:
    if failed_count and ingested_count:
        return "partial"
    if failed_count:
        return "failed"
    if skipped_count and not ingested_count and discovered_count:
        return "requires_review"
    return "succeeded"


def _create_empty_ingestion_run(
    session_factory: sessionmaker[Session],
    payload: IngestionRunCreate,
) -> int:
    with session_scope(session_factory) as session:
        if payload.connector_id is not None:
            _ensure_connector(session, payload.connector_id)
        if payload.watch_folder_id is not None and session.get(InstrumentWatchFolderORM, payload.watch_folder_id) is None:
            raise KeyError("Instrument watch folder not found.")
        row = IngestionRunORM(
            connector_id=payload.connector_id,
            watch_folder_id=payload.watch_folder_id,
            source_system=payload.source_system,
            source_path=payload.source_path,
            status="running" if payload.files_json else payload.status,
            discovered_count=len(payload.files_json),
            ingested_count=0,
            skipped_count=0,
            failed_count=0,
            warnings_json=_json_dump(payload.warnings_json, default=[]),
            notes_json=_json_dump(payload.notes_json, default=[]),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return row.id


def _update_ingestion_run(
    session_factory: sessionmaker[Session],
    run_id: int,
    *,
    status: str,
    discovered_count: int,
    ingested_count: int,
    skipped_count: int,
    failed_count: int,
    warnings: list[str],
    notes: list[str],
    metadata: dict[str, Any],
) -> IngestionRun:
    with session_scope(session_factory) as session:
        row = session.get(IngestionRunORM, run_id)
        if row is None:
            raise KeyError("Ingestion run not found.")
        row.status = status
        row.discovered_count = discovered_count
        row.ingested_count = ingested_count
        row.skipped_count = skipped_count
        row.failed_count = failed_count
        row.warnings_json = _json_dump(warnings, default=[])
        row.notes_json = _json_dump(notes, default=[])
        row.finished_at = utcnow() if status not in {"queued", "running"} else None
        row.metadata_json = _json_dump(metadata, default={})
        session.flush()
        session.refresh(row)
        return _ingestion_run_to_record(row)


def create_ingestion_run(
    session_factory: sessionmaker[Session],
    payload: IngestionRunCreate,
    *,
    storage_root: Path,
) -> IngestionRun:
    run_id = _create_empty_ingestion_run(session_factory, payload)
    if not payload.files_json:
        existing = get_ingestion_run(session_factory, run_id)
        if existing is None:
            raise KeyError("Ingestion run not found.")
        return existing

    file_ids: list[int] = []
    file_hashes: list[str] = []
    duplicates: list[dict[str, Any]] = []
    failures: list[str] = []
    warnings = list(payload.warnings_json)
    notes = list(payload.notes_json)
    ingested_count = 0
    skipped_count = 0

    for file_input in payload.files_json:
        source_path = file_input.source_path or payload.source_path
        try:
            content = _content_from_input(file_input)
            if not content:
                raise InteroperabilityError(f"{file_input.filename}: content cannot be empty.")
            sha256 = hashlib.sha256(content).hexdigest()
            with session_scope(session_factory) as session:
                existing, duplicate_basis = _find_existing_file(
                    session,
                    sha256=sha256,
                    source_path=source_path,
                )
            if existing is not None and not payload.force:
                skipped_count += 1
                duplicate = {
                    "filename": file_input.filename,
                    "sha256": sha256,
                    "duplicate_basis": duplicate_basis,
                    "existing_file_id": existing.id,
                }
                duplicates.append(duplicate)
                warnings.append(
                    f"{file_input.filename} was skipped because the source hash or path was already imported."
                )
                continue
            metadata = {
                **file_input.metadata_json,
                "connector_id": payload.connector_id,
                "watch_folder_id": payload.watch_folder_id,
                "ingestion_run_id": run_id,
                "source_system": payload.source_system,
                "source_path": source_path,
                "source_sha256": sha256,
                "immutable_source": True,
                "raw_file_immutable": file_input.file_kind == "raw_fid",
                "ingestion_policy": "Source files are imported into immutable managed storage and are not modified in place.",
            }
            record = orch_store.upload_file_record(
                session_factory,
                original_filename=file_input.filename,
                content_type=file_input.content_type,
                content=content,
                file_kind=file_input.file_kind,
                metadata_json=metadata,
                storage_root=storage_root,
            )
            file_ids.append(record.id)
            file_hashes.append(record.sha256)
            ingested_count += 1
        except Exception as exc:
            failures.append(str(exc))
            warnings.append(str(exc))

    failed_count = len(failures)
    status = _finish_ingestion_status(
        discovered_count=len(payload.files_json),
        ingested_count=ingested_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
    )
    if ingested_count:
        notes.append("Files were imported into immutable managed storage with SHA-256 hashes.")
    if skipped_count:
        notes.append("Duplicate hash/path inputs were skipped and recorded for review.")
    metadata = {
        **payload.metadata_json,
        "file_ids_json": file_ids,
        "file_hashes_json": file_hashes,
        "duplicate_files_json": duplicates,
        "failed_files_json": failures,
        "forced": payload.force,
    }
    return _update_ingestion_run(
        session_factory,
        run_id,
        status=status,
        discovered_count=len(payload.files_json),
        ingested_count=ingested_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        warnings=warnings,
        notes=notes,
        metadata=metadata,
    )


def list_ingestion_runs(
    session_factory: sessionmaker[Session],
    *,
    status_filter: str | None = None,
    limit: int = 200,
) -> list[IngestionRun]:
    with session_scope(session_factory) as session:
        stmt = select(IngestionRunORM).order_by(IngestionRunORM.id.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(IngestionRunORM.status == status_filter)
        return [_ingestion_run_to_record(row) for row in session.scalars(stmt).all()]


def get_ingestion_run(
    session_factory: sessionmaker[Session],
    ingestion_run_id: int,
) -> IngestionRun | None:
    with session_scope(session_factory) as session:
        row = session.get(IngestionRunORM, ingestion_run_id)
        return _ingestion_run_to_record(row) if row is not None else None


def scan_watch_folder(
    session_factory: sessionmaker[Session],
    watch_folder_id: int,
    payload: InstrumentWatchFolderScanRequest,
    *,
    storage_root: Path,
) -> IngestionRun:
    with session_scope(session_factory) as session:
        row = session.get(InstrumentWatchFolderORM, watch_folder_id)
        if row is None:
            raise KeyError("Instrument watch folder not found.")
        watch_folder = _watch_folder_to_record(row)

    warnings: list[str] = []
    files: list[IngestionFileInput] = []
    if watch_folder.status != "active":
        warnings.append("Watch folder is not active; scan produced no imported files.")
    else:
        folder = Path(watch_folder.folder_path).expanduser()
        if not folder.exists() or not folder.is_dir():
            warnings.append("Watch folder path does not exist or is not a directory.")
        else:
            patterns = watch_folder.file_patterns_json or ["*"]
            candidates = folder.rglob("*") if watch_folder.recursive else folder.iterdir()
            for path in candidates:
                if len(files) >= 500:
                    warnings.append("Scan stopped at 500 files to keep the connector action bounded.")
                    break
                if not path.is_file():
                    continue
                if not any(fnmatch(path.name, pattern) for pattern in patterns):
                    continue
                content = path.read_bytes()
                files.append(
                    IngestionFileInput(
                        filename=path.name,
                        content_base64=base64.b64encode(content).decode("ascii"),
                        content_type=None,
                        file_kind=_file_kind_for_route(watch_folder.target_route),
                        source_path=str(path),
                        metadata_json={
                            "watch_folder_id": watch_folder.id,
                            "target_program": watch_folder.target_program,
                            "target_route": watch_folder.target_route,
                        },
                    )
                )

    ingestion_payload = IngestionRunCreate(
        connector_id=watch_folder.connector_id,
        watch_folder_id=watch_folder.id,
        source_system="instrument_watch_folder",
        source_path=watch_folder.folder_path,
        files_json=files,
        force=payload.force,
        warnings_json=warnings,
        notes_json=["Watch folder scan completed without modifying source files."],
        metadata_json={**payload.metadata_json, "watch_folder_scan": True},
    )
    run = create_ingestion_run(session_factory, ingestion_payload, storage_root=storage_root)
    with session_scope(session_factory) as session:
        row = session.get(InstrumentWatchFolderORM, watch_folder_id)
        if row is not None:
            row.last_scan_at = utcnow()
            if warnings and "does not exist" in warnings[0]:
                row.status = "error"
    return run


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _detect_source_format(filename: str, content_type: str | None, content: bytes) -> FileNormalizationSourceFormat:
    lower = filename.lower()
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".tsv"):
        return "tsv"
    if lower.endswith((".jdx", ".dx")):
        return "jcamp_dx"
    if lower.endswith(".mzml"):
        return "mzml"
    if lower.endswith(".mzxml"):
        return "mzxml"
    if lower.endswith(".sdf"):
        return "sdf"
    if lower.endswith(".pdf") or content_type == "application/pdf":
        return "pdf"
    if lower.endswith(".docx") or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return "docx"
    if lower.endswith(".zip"):
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                names = [name.lower() for name in archive.namelist()]
            if any(name.endswith("acqus") or "/pdata/" in name for name in names):
                return "bruker_zip"
            if any(name.endswith("procpar") or name.endswith(".fid/fid") or "/fid/" in name for name in names):
                return "agilent_varian_zip"
        except zipfile.BadZipFile:
            return "unknown"
        return "unknown"
    if lower.endswith(".txt") or (content_type or "").startswith("text/"):
        text = _decode_text(content[:2048])
        if "##TITLE=" in text.upper() or "##JCAMP-DX=" in text.upper():
            return "jcamp_dx"
        return "txt"
    return "unknown"


def _target_for_source(source_format: str, requested: FileNormalizationTargetFormat | None) -> FileNormalizationTargetFormat:
    if requested is not None:
        return requested
    if source_format in {"mzml", "mzxml"}:
        return "moltrace_lcms_json"
    if source_format in {"pdf", "docx"}:
        return "moltrace_regulatory_source_json"
    if source_format in {"csv", "tsv", "txt", "jcamp_dx", "bruker_zip", "agilent_varian_zip"}:
        return "moltrace_spectrum_json"
    return "unsupported"


def _parse_delimited_text(text: str, delimiter: str) -> dict[str, Any]:
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    columns = list(reader.fieldnames or [])
    rows = [dict(row) for row in reader]
    if not columns:
        plain_rows = list(csv.reader(StringIO(text), delimiter=delimiter))
        return {
            "columns": [],
            "rows": plain_rows,
            "row_count": len(plain_rows),
        }
    return {
        "columns": columns,
        "rows": rows[:1000],
        "row_count": len(rows),
        "truncated": len(rows) > 1000,
    }


def _parse_jcamp(text: str) -> dict[str, Any]:
    metadata: dict[str, str] = {}
    data_lines = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("##") and "=" in line:
            key, value = line[2:].split("=", 1)
            metadata[key.strip().lower()] = value.strip()[:500]
        elif line:
            data_lines += 1
    return {"jcamp_metadata_json": metadata, "data_line_count": data_lines}


def _parse_xml_metadata(content: bytes) -> dict[str, Any]:
    preview = content[:200000]
    try:
        root = ElementTree.fromstring(preview)
        root_tag = root.tag.split("}")[-1]
        attrs = {str(k): str(v) for k, v in list(root.attrib.items())[:30]}
    except Exception:
        root_tag = "unknown"
        attrs = {}
    return {"root_tag": root_tag, "root_attributes_json": attrs, "byte_size": len(content)}


def _parse_zip_metadata(content: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        names = archive.namelist()
        entries = [
            {
                "name": info.filename,
                "file_size": info.file_size,
                "compress_size": info.compress_size,
            }
            for info in archive.infolist()[:250]
            if not info.is_dir()
        ]
    return {
        "entry_count": len(names),
        "entries_json": entries,
        "truncated": len(names) > 250,
    }


def _extract_regulatory_text(
    filename: str,
    content_type: str | None,
    content: bytes,
) -> tuple[str, list[str]]:
    lower = filename.lower()
    warnings: list[str] = []
    if lower.endswith(".docx") or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                xml_bytes = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml_bytes)
            text = " ".join(node.text or "" for node in root.iter() if node.text)
            return re.sub(r"\s+", " ", text).strip(), warnings
        except Exception as exc:
            warnings.append(f"DOCX text extraction returned hash-only metadata: {exc}")
            return "", warnings
    if lower.endswith(".pdf") or content_type == "application/pdf":
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip(), warnings
        except Exception as exc:
            warnings.append(f"PDF text extraction returned hash-only metadata: {exc}")
            return "", warnings
    return _decode_text(content), warnings


def _build_normalized_artifact(
    *,
    source_format: str,
    target_format: str,
    file_row: ManagedFileRecordORM,
    content: bytes,
) -> tuple[str, dict[str, Any] | None, list[str], str]:
    warnings: list[str] = []
    base = {
        "schema_version": "phase62.v1",
        "normalized_artifact": True,
        "derived_output": True,
        "source_file_id": file_row.id,
        "source_sha256": file_row.sha256,
        "source_filename": file_row.original_filename,
        "source_format": source_format,
        "target_format": target_format,
    }
    try:
        if source_format == "csv":
            parsed = _parse_delimited_text(_decode_text(content), ",")
            return "succeeded", {**base, **parsed}, warnings, target_format
        if source_format == "tsv":
            parsed = _parse_delimited_text(_decode_text(content), "\t")
            return "succeeded", {**base, **parsed}, warnings, target_format
        if source_format == "txt":
            text = _decode_text(content)
            lines = text.splitlines()
            return "succeeded", {**base, "line_count": len(lines), "text_preview": "\n".join(lines[:100])}, warnings, target_format
        if source_format == "jcamp_dx":
            parsed = _parse_jcamp(_decode_text(content))
            return "succeeded", {**base, **parsed}, warnings, target_format
        if source_format in {"mzml", "mzxml"}:
            parsed = _parse_xml_metadata(content)
            return "succeeded", {**base, **parsed}, warnings, "moltrace_lcms_json"
        if source_format in {"bruker_zip", "agilent_varian_zip"}:
            parsed = _parse_zip_metadata(content)
            return "succeeded", {**base, **parsed}, warnings, target_format
        if source_format in {"pdf", "docx"}:
            text, extraction_warnings = _extract_regulatory_text(
                file_row.original_filename,
                file_row.content_type,
                content,
            )
            warnings.extend(extraction_warnings)
            status = "succeeded" if text else "requires_review"
            return (
                status,
                {
                    **base,
                    "text_excerpt": re.sub(r"\s+", " ", text).strip()[:5000],
                    "text_extracted": bool(text),
                },
                warnings,
                "moltrace_regulatory_source_json",
            )
        warnings.append(f"Unsupported normalization source format: {source_format}.")
        return "unsupported", None, warnings, "unsupported"
    except Exception as exc:
        warnings.append(f"Normalization failed for {source_format}: {exc}")
        return "failed", None, warnings, "unsupported"


def normalize_file(
    session_factory: sessionmaker[Session],
    file_id: int,
    payload: FileNormalizationRequest,
    *,
    storage_root: Path,
) -> FileNormalizationRun:
    download = orch_store.get_file_download(session_factory, file_id, storage_root=storage_root)
    if download is None:
        raise KeyError("Managed file not found.")
    _file_record, path = download
    content = path.read_bytes()
    with session_scope(session_factory) as session:
        file_row = session.get(ManagedFileRecordORM, file_id)
        if file_row is None:
            raise KeyError("Managed file not found.")
        source_format = payload.source_format or _detect_source_format(
            file_row.original_filename,
            file_row.content_type,
            content,
        )
        target_format = _target_for_source(source_format, payload.target_format)
        final_status, artifact_json, warnings, target_format = _build_normalized_artifact(
            source_format=source_format,
            target_format=target_format,
            file_row=file_row,
            content=content,
        )
        notes = ["Normalization created a derived output; source bytes were not modified."]
        artifact_id: int | None = None
        if artifact_json is not None and final_status in {"succeeded", "requires_review"}:
            serialized = _json_dump(artifact_json, default={})
            artifact = ArtifactRecordORM(
                job_id=None,
                session_id=None,
                artifact_type="job_artifact",
                title=f"Phase 62 normalized artifact for file {file_row.id}",
                content_type="application/json",
                sha256=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
                storage_key=None,
                artifact_json=serialized,
                metadata_json=_json_dump(
                    {
                        "source_file_id": file_row.id,
                        "source_sha256": file_row.sha256,
                        "source_format": source_format,
                        "target_format": target_format,
                        "derived_output": True,
                    },
                    default={},
                ),
            )
            session.add(artifact)
            session.flush()
            artifact_id = artifact.id
        row = FileNormalizationRunORM(
            file_id=file_row.id,
            source_format=source_format,
            target_format=target_format,
            status=final_status,
            output_artifact_id=artifact_id,
            warnings_json=_json_dump(warnings, default=[]),
            notes_json=_json_dump(notes, default=[]),
            created_at=utcnow(),
            finished_at=utcnow(),
            metadata_json=_json_dump(
                {
                    **payload.metadata_json,
                    "source_sha256": file_row.sha256,
                    "source_file_immutable": True,
                    "derived_output": artifact_id is not None,
                },
                default={},
            ),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _normalization_run_to_record(row)


def list_normalization_runs_for_file(
    session_factory: sessionmaker[Session],
    file_id: int,
    *,
    limit: int = 100,
) -> list[FileNormalizationRun]:
    with session_scope(session_factory) as session:
        stmt = (
            select(FileNormalizationRunORM)
            .where(FileNormalizationRunORM.file_id == file_id)
            .order_by(FileNormalizationRunORM.id.desc())
            .limit(limit)
        )
        return [_normalization_run_to_record(row) for row in session.scalars(stmt).all()]


def get_normalization_run(
    session_factory: sessionmaker[Session],
    normalization_run_id: int,
) -> FileNormalizationRun | None:
    with session_scope(session_factory) as session:
        row = session.get(FileNormalizationRunORM, normalization_run_id)
        return _normalization_run_to_record(row) if row is not None else None


def create_external_record(
    session_factory: sessionmaker[Session],
    payload: ExternalSystemRecordCreate,
) -> ExternalSystemRecord:
    with session_scope(session_factory) as session:
        _ensure_connector(session, payload.connector_id)
        row = ExternalSystemRecordORM(
            connector_id=payload.connector_id,
            external_system=payload.external_system,
            external_object_type=payload.external_object_type,
            external_object_id=payload.external_object_id,
            external_url=payload.external_url,
            title=payload.title,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _external_record_to_record(row)


def list_external_records(
    session_factory: sessionmaker[Session],
    *,
    connector_id: int | None = None,
    limit: int = 200,
) -> list[ExternalSystemRecord]:
    with session_scope(session_factory) as session:
        stmt = select(ExternalSystemRecordORM).order_by(ExternalSystemRecordORM.id.desc()).limit(limit)
        if connector_id is not None:
            stmt = stmt.where(ExternalSystemRecordORM.connector_id == connector_id)
        return [_external_record_to_record(row) for row in session.scalars(stmt).all()]


def get_external_record(
    session_factory: sessionmaker[Session],
    external_record_id: int,
) -> ExternalSystemRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(ExternalSystemRecordORM, external_record_id)
        return _external_record_to_record(row) if row is not None else None


def create_external_object_link(
    session_factory: sessionmaker[Session],
    payload: ExternalObjectLinkCreate,
) -> ExternalObjectLink:
    with session_scope(session_factory) as session:
        if session.get(ExternalSystemRecordORM, payload.external_record_id) is None:
            raise KeyError("External system record not found.")
        row = ExternalObjectLinkORM(
            external_record_id=payload.external_record_id,
            moltrace_resource_type=payload.moltrace_resource_type,
            moltrace_resource_id=payload.moltrace_resource_id,
            relation_type=payload.relation_type,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _external_link_to_record(row)


def list_external_object_links(
    session_factory: sessionmaker[Session],
    *,
    external_record_id: int | None = None,
    limit: int = 200,
) -> list[ExternalObjectLink]:
    with session_scope(session_factory) as session:
        stmt = select(ExternalObjectLinkORM).order_by(ExternalObjectLinkORM.id.desc()).limit(limit)
        if external_record_id is not None:
            stmt = stmt.where(ExternalObjectLinkORM.external_record_id == external_record_id)
        return [_external_link_to_record(row) for row in session.scalars(stmt).all()]


def create_mapping_template(
    session_factory: sessionmaker[Session],
    payload: MappingTemplateCreate,
) -> MappingTemplate:
    with session_scope(session_factory) as session:
        if payload.connector_id is not None:
            _ensure_connector(session, payload.connector_id)
        row = MappingTemplateORM(
            connector_id=payload.connector_id,
            name=payload.name,
            source_type=payload.source_type,
            target_type=payload.target_type,
            field_map_json=_json_dump(payload.field_map_json, default={}),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _mapping_template_to_record(row)


def list_mapping_templates(
    session_factory: sessionmaker[Session],
    *,
    connector_id: int | None = None,
    limit: int = 200,
) -> list[MappingTemplate]:
    with session_scope(session_factory) as session:
        stmt = select(MappingTemplateORM).order_by(MappingTemplateORM.id.desc()).limit(limit)
        if connector_id is not None:
            stmt = stmt.where(MappingTemplateORM.connector_id == connector_id)
        return [_mapping_template_to_record(row) for row in session.scalars(stmt).all()]


def get_mapping_template(
    session_factory: sessionmaker[Session],
    template_id: int,
) -> MappingTemplate | None:
    with session_scope(session_factory) as session:
        row = session.get(MappingTemplateORM, template_id)
        return _mapping_template_to_record(row) if row is not None else None


def update_mapping_template(
    session_factory: sessionmaker[Session],
    template_id: int,
    payload: MappingTemplateUpdate,
) -> MappingTemplate | None:
    with session_scope(session_factory) as session:
        row = session.get(MappingTemplateORM, template_id)
        if row is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        if data.get("connector_id") is not None:
            _ensure_connector(session, int(data["connector_id"]))
        for field in ("connector_id", "name", "source_type", "target_type", "status"):
            if field in data:
                setattr(row, field, data[field])
        if "field_map_json" in data:
            row.field_map_json = _json_dump(data["field_map_json"], default={})
        if "metadata_json" in data:
            row.metadata_json = _json_dump(data["metadata_json"], default={})
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _mapping_template_to_record(row)


# Source-resource-type → in-session ownership predicate for outbound sync jobs and any other
# typed body-id route. A type the table doesn't list is hidden under user scope (the SQL
# filter excludes unknown types from the user's list, and the create predicate returns False).
def _outbound_resource_owned_by(
    session: Session,
    source_resource_type: str,
    source_resource_id: int | None,
    owner_scope_id: int | None,
) -> bool:
    if owner_scope_id is None:
        return True
    if source_resource_type == "reaction_project":
        return reaction_access.reaction_project_owned_by(
            session, source_resource_id, owner_scope_id
        )
    if source_resource_type == "reaction_experiment":
        return reaction_access.reaction_experiment_owned_by(
            session, source_resource_id, owner_scope_id
        )
    if source_resource_type == "regulatory_dossier":
        return _dossier_owned_by(session, source_resource_id, owner_scope_id)
    if source_resource_type == "spectracheck_session":
        return _spectracheck_session_owned_by(session, source_resource_id, owner_scope_id)
    # Unknown type under user scope: hide. The list filter below uses the same enumeration, so
    # a user-scoped caller can't create or list a job whose source_resource_type is unknown to
    # the predicate set — extend both sites in lockstep when adding a new typed source.
    return False


def create_outbound_sync_job(
    session_factory: sessionmaker[Session],
    payload: OutboundSyncJobCreate,
    *,
    owner_scope_id: int | None = None,
) -> OutboundSyncJob:
    warnings = list(payload.warnings_json)
    status = payload.status
    if status not in {"queued", "requires_review"}:
        status = "requires_review"
        warnings.append("Outbound sync jobs created through the connector layer require review before completion.")
    notes = list(payload.notes_json)
    notes.append("Outbound sync is reviewable; no external status update is performed by this create action.")
    with session_scope(session_factory) as session:
        # Owner-scope the body-supplied source resource (the path gate cannot reach it): a
        # non-owner referencing another tenant's reaction project / dossier / etc. gets a
        # non-leaking 404. System/admin (owner_scope_id None) stays unrestricted.
        if not _outbound_resource_owned_by(
            session, payload.source_resource_type, payload.source_resource_id, owner_scope_id
        ):
            raise KeyError("Source resource not found.")
        _ensure_connector(session, payload.connector_id)
        row = OutboundSyncJobORM(
            connector_id=payload.connector_id,
            target_system=payload.target_system,
            source_resource_type=payload.source_resource_type,
            source_resource_id=payload.source_resource_id,
            payload_summary_json=_json_dump(_scrub_sensitive(payload.payload_summary_json), default={}),
            status=status,
            warnings_json=_json_dump(warnings, default=[]),
            notes_json=_json_dump(notes, default=[]),
            metadata_json=_json_dump(_scrub_sensitive(payload.metadata_json), default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _sync_job_to_record(row)


def list_outbound_sync_jobs(
    session_factory: sessionmaker[Session],
    *,
    status_filter: str | None = None,
    limit: int = 200,
    owner_scope_id: int | None = None,
) -> list[OutboundSyncJob]:
    with session_scope(session_factory) as session:
        stmt = select(OutboundSyncJobORM).order_by(OutboundSyncJobORM.id.desc())
        if status_filter:
            stmt = stmt.where(OutboundSyncJobORM.status == status_filter)
        if owner_scope_id is not None:
            # Owner-filter IN SQL BEFORE the .limit() — a post-.limit() Python filter would
            # silently drop owned rows behind another tenant's jobs on a busy table. Build the
            # union of every typed-resource ownership join the predicate set knows about; an
            # unknown source_resource_type is excluded (safe default).
            owned_reaction_projects = select(ReactionProjectORM.id).where(
                ReactionProjectORM.owner_id == owner_scope_id
            )
            owned_reaction_experiments = (
                select(ReactionExperimentORM.id)
                .join(
                    ReactionProjectORM,
                    ReactionProjectORM.id == ReactionExperimentORM.reaction_project_id,
                )
                .where(ReactionProjectORM.owner_id == owner_scope_id)
            )
            owned_dossiers = select(RegulatoryDossierORM.id).where(
                RegulatoryDossierORM.created_by_user_id == owner_scope_id
            )
            owned_spectracheck_sessions = (
                select(SpectraCheckSessionORM.id)
                .join(
                    SpectraCheckProjectORM,
                    SpectraCheckProjectORM.id == SpectraCheckSessionORM.project_id,
                )
                .where(SpectraCheckProjectORM.owner_id == owner_scope_id)
            )
            # Local import keeps the top-level import minimal — these are the only sites that
            # need ``and_``/``or_``, all in this filter block.
            from sqlalchemy import and_, or_

            stmt = stmt.where(
                or_(
                    and_(
                        OutboundSyncJobORM.source_resource_type == "reaction_project",
                        OutboundSyncJobORM.source_resource_id.in_(owned_reaction_projects),
                    ),
                    and_(
                        OutboundSyncJobORM.source_resource_type == "reaction_experiment",
                        OutboundSyncJobORM.source_resource_id.in_(owned_reaction_experiments),
                    ),
                    and_(
                        OutboundSyncJobORM.source_resource_type == "regulatory_dossier",
                        OutboundSyncJobORM.source_resource_id.in_(owned_dossiers),
                    ),
                    and_(
                        OutboundSyncJobORM.source_resource_type == "spectracheck_session",
                        OutboundSyncJobORM.source_resource_id.in_(owned_spectracheck_sessions),
                    ),
                )
            )
        stmt = stmt.limit(limit)
        return [_sync_job_to_record(row) for row in session.scalars(stmt).all()]


def get_outbound_sync_job(
    session_factory: sessionmaker[Session],
    sync_job_id: int,
) -> OutboundSyncJob | None:
    with session_scope(session_factory) as session:
        row = session.get(OutboundSyncJobORM, sync_job_id)
        return _sync_job_to_record(row) if row is not None else None


def _webhook_target_hash(payload: WebhookSubscriptionCreate | WebhookSubscriptionUpdate) -> str | None:
    if getattr(payload, "target_url", None):
        return hashlib.sha256(str(payload.target_url).encode("utf-8")).hexdigest()
    return getattr(payload, "target_url_hash", None)


def create_webhook_subscription(
    session_factory: sessionmaker[Session],
    payload: WebhookSubscriptionCreate,
) -> WebhookSubscription:
    target_url_hash = _webhook_target_hash(payload)
    if target_url_hash is None:
        raise InteroperabilityError("Webhook target hash could not be derived.")
    with session_scope(session_factory) as session:
        if payload.connector_id is not None:
            _ensure_connector(session, payload.connector_id)
        row = WebhookSubscriptionORM(
            connector_id=payload.connector_id,
            name=payload.name,
            event_types_json=_json_dump(payload.event_types_json, default=[]),
            target_url_hash=target_url_hash,
            status=payload.status,
            metadata_json=_json_dump(_scrub_sensitive(payload.metadata_json), default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _webhook_to_record(row)


def list_webhook_subscriptions(
    session_factory: sessionmaker[Session],
    *,
    limit: int = 200,
) -> list[WebhookSubscription]:
    with session_scope(session_factory) as session:
        stmt = select(WebhookSubscriptionORM).order_by(WebhookSubscriptionORM.id.desc()).limit(limit)
        return [_webhook_to_record(row) for row in session.scalars(stmt).all()]


def update_webhook_subscription(
    session_factory: sessionmaker[Session],
    subscription_id: int,
    payload: WebhookSubscriptionUpdate,
) -> WebhookSubscription | None:
    with session_scope(session_factory) as session:
        row = session.get(WebhookSubscriptionORM, subscription_id)
        if row is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        if data.get("connector_id") is not None:
            _ensure_connector(session, int(data["connector_id"]))
        for field in ("connector_id", "name", "status"):
            if field in data:
                setattr(row, field, data[field])
        if "event_types_json" in data:
            row.event_types_json = _json_dump(data["event_types_json"], default=[])
        target_url_hash = _webhook_target_hash(payload)
        if target_url_hash is not None:
            row.target_url_hash = target_url_hash
        if "metadata_json" in data:
            row.metadata_json = _json_dump(_scrub_sensitive(data["metadata_json"]), default={})
        session.flush()
        session.refresh(row)
        return _webhook_to_record(row)


def create_submission_package(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: RegulatorySubmissionPackageCreate,
) -> RegulatorySubmissionPackage:
    with session_scope(session_factory) as session:
        if session.get(RegulatoryDossierORM, dossier_id) is None:
            raise KeyError("Regulatory dossier not found.")
        files = []
        warnings = list(payload.warnings_json)
        for file_id in payload.file_ids_json:
            file_row = session.get(ManagedFileRecordORM, file_id)
            if file_row is None:
                warnings.append(f"File {file_id} was not found for the export package manifest.")
                continue
            file_metadata = _file_record_metadata(file_row)
            files.append(
                {
                    "file_id": file_row.id,
                    "original_filename": file_row.original_filename,
                    "sha256": file_row.sha256,
                    "file_size_bytes": file_row.file_size_bytes,
                    "source_path": file_metadata.get("source_path"),
                    "source_sha256": file_metadata.get("source_sha256", file_row.sha256),
                }
            )
        artifacts = []
        for artifact_id in payload.artifact_ids_json:
            artifact_row = session.get(ArtifactRecordORM, artifact_id)
            if artifact_row is None:
                warnings.append(f"Artifact {artifact_id} was not found for the export package manifest.")
                continue
            artifacts.append(
                {
                    "artifact_id": artifact_row.id,
                    "artifact_type": artifact_row.artifact_type,
                    "sha256": artifact_row.sha256,
                    "derived_output": True,
                }
            )
        manifest = {
            "schema_version": "phase62.ctd_package.v1",
            "package_type": payload.package_type,
            "status": payload.status,
            "dossier_id": dossier_id,
            "report_id": payload.report_id,
            "review_status": payload.status,
            "files": files,
            "artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
            "artifacts": artifacts,
            "source_citations": payload.source_citations_json,
            "warnings": warnings,
            "language_notice": "Export package is for review and does not assert legal approval or guaranteed compliance.",
        }
        serialized_manifest = _json_dump(manifest, default={})
        package_sha256 = hashlib.sha256(serialized_manifest.encode("utf-8")).hexdigest()
        row = RegulatorySubmissionPackageORM(
            dossier_id=dossier_id,
            report_id=payload.report_id,
            package_type=payload.package_type,
            status=payload.status,
            file_ids_json=_json_dump(payload.file_ids_json, default=[]),
            artifact_ids_json=_json_dump(payload.artifact_ids_json, default=[]),
            package_manifest_json=serialized_manifest,
            package_sha256=package_sha256,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _submission_package_to_record(row)


def list_submission_packages_for_dossier(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    *,
    limit: int = 100,
) -> list[RegulatorySubmissionPackage]:
    with session_scope(session_factory) as session:
        stmt = (
            select(RegulatorySubmissionPackageORM)
            .where(RegulatorySubmissionPackageORM.dossier_id == dossier_id)
            .order_by(RegulatorySubmissionPackageORM.id.desc())
            .limit(limit)
        )
        return [_submission_package_to_record(row) for row in session.scalars(stmt).all()]


def get_submission_package(
    session_factory: sessionmaker[Session],
    package_id: int,
) -> RegulatorySubmissionPackage | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatorySubmissionPackageORM, package_id)
        return _submission_package_to_record(row) if row is not None else None


def _spectracheck_session_owned_by(
    session: Session, session_id: int | None, owner_scope_id: int | None
) -> bool:
    """In-session ownership predicate for a SpectraCheck session, resolved via its parent
    project's ``owner_id``. Mirrors :func:`reaction_access.reaction_experiment_owned_by`'s
    parent-hop pattern. System/admin scope (``owner_scope_id is None``) sees all; otherwise the
    session must exist, its project must exist, and the project's owner must match — a missing
    session, a missing project, or a NULL/mismatched owner is False, so the route returns a
    non-leaking 404."""
    if owner_scope_id is None:
        return True
    if session_id is None:
        return False
    sc_session = session.get(SpectraCheckSessionORM, session_id)
    if sc_session is None:
        return False
    project = session.get(SpectraCheckProjectORM, sc_session.project_id)
    return project is not None and project.owner_id == owner_scope_id


def import_spectracheck_file(
    session_factory: sessionmaker[Session],
    payload: SpectraCheckImportFileRequest,
    *,
    owner_scope_id: int | None = None,
) -> IntegrationImportResponse:
    # Owner-scope the body-supplied spectracheck_session_id (the path gate cannot reach it):
    # a non-owner stitching an external link onto another tenant's session gets a non-leaking
    # 404. System/admin (owner_scope_id None) stays unrestricted.
    if payload.spectracheck_session_id is not None:
        with session_scope(session_factory) as session:
            if not _spectracheck_session_owned_by(
                session, payload.spectracheck_session_id, owner_scope_id
            ):
                raise KeyError("SpectraCheck session not found.")
    with session_scope(session_factory) as session:
        file_row = session.get(ManagedFileRecordORM, payload.file_id)
        if file_row is None:
            raise KeyError("Managed file not found.")
        run = IngestionRunORM(
            connector_id=payload.connector_id,
            source_system="spectracheck_import",
            source_path=_file_record_metadata(file_row).get("source_path"),
            status="succeeded",
            discovered_count=1,
            ingested_count=1,
            warnings_json="[]",
            notes_json=_json_dump(["File imported for SpectraCheck without modifying source bytes."], default=[]),
            finished_at=utcnow(),
            metadata_json=_json_dump(
                {
                    **payload.metadata_json,
                    "file_id": file_row.id,
                    "file_sha256": file_row.sha256,
                    "route": payload.route,
                    "spectracheck_session_id": payload.spectracheck_session_id,
                },
                default={},
            ),
        )
        session.add(run)
        session.flush()
        link_id = None
        if payload.external_record_id is not None and payload.spectracheck_session_id is not None:
            if session.get(ExternalSystemRecordORM, payload.external_record_id) is not None:
                link = ExternalObjectLinkORM(
                    external_record_id=payload.external_record_id,
                    moltrace_resource_type="spectracheck_session",
                    moltrace_resource_id=payload.spectracheck_session_id,
                    relation_type="source_of",
                    metadata_json=_json_dump({"file_id": file_row.id}, default={}),
                )
                session.add(link)
                session.flush()
                link_id = link.id
        return IntegrationImportResponse(
            status="imported",
            review_required=False,
            file_id=file_row.id,
            ingestion_run_id=run.id,
            external_record_id=payload.external_record_id,
            external_link_id=link_id,
            notes_json=["File imported for SpectraCheck; source bytes remain immutable."],
            metadata_json={"file_sha256": file_row.sha256, "route": payload.route},
        )


def import_regulatory_source(
    session_factory: sessionmaker[Session],
    payload: RegulatoryImportSourceRequest,
    *,
    owner_scope_id: int | None = None,
) -> IntegrationImportResponse:
    # Owner-scope the body-supplied dossier_id (the path gate cannot reach it): a non-owner
    # stitching an external evidence link onto another tenant's dossier gets a non-leaking 404.
    # System/admin (owner_scope_id None) stays unrestricted.
    if payload.dossier_id is not None:
        with session_scope(session_factory) as session:
            if not _dossier_owned_by(session, payload.dossier_id, owner_scope_id):
                raise KeyError("Regulatory dossier not found.")
    with session_scope(session_factory) as session:
        file_row = session.get(ManagedFileRecordORM, payload.file_id)
        if file_row is None:
            raise KeyError("Managed file not found.")
        link_id = None
        if payload.external_record_id is not None and payload.dossier_id is not None:
            if session.get(ExternalSystemRecordORM, payload.external_record_id) is not None:
                link = ExternalObjectLinkORM(
                    external_record_id=payload.external_record_id,
                    moltrace_resource_type="regulatory_dossier",
                    moltrace_resource_id=payload.dossier_id,
                    relation_type="evidence_for",
                    metadata_json=_json_dump(
                        {
                            "file_id": file_row.id,
                            "source_citation_json": payload.source_citation_json,
                        },
                        default={},
                    ),
                )
                session.add(link)
                session.flush()
                link_id = link.id
        run = IngestionRunORM(
            connector_id=payload.connector_id,
            source_system="regulatory_source_import",
            source_path=_file_record_metadata(file_row).get("source_path"),
            status="requires_review",
            discovered_count=1,
            ingested_count=1,
            warnings_json="[]",
            notes_json=_json_dump(["Regulatory source imported with citation metadata; review required."], default=[]),
            finished_at=utcnow(),
            metadata_json=_json_dump(
                {
                    **payload.metadata_json,
                    "file_id": file_row.id,
                    "file_sha256": file_row.sha256,
                    "dossier_id": payload.dossier_id,
                    "source_citation_json": payload.source_citation_json,
                },
                default={},
            ),
        )
        session.add(run)
        session.flush()
        return IntegrationImportResponse(
            status="requires_review",
            review_required=True,
            file_id=file_row.id,
            ingestion_run_id=run.id,
            external_record_id=payload.external_record_id,
            external_link_id=link_id,
            notes_json=["Regulatory source imported with citation metadata; review required."],
            metadata_json={"file_sha256": file_row.sha256, "source_citation_json": payload.source_citation_json},
        )


def import_reaction_experiment_table(
    session_factory: sessionmaker[Session],
    payload: ReactionExperimentTableImportRequest,
    *,
    storage_root: Path,
    owner_scope_id: int | None = None,
) -> IntegrationImportResponse:
    # Owner-scope the body-supplied reaction_project_id (the path gate cannot reach it): a
    # non-owner importing into another tenant's project gets a non-leaking 404.
    if payload.reaction_project_id is not None:
        with session_scope(session_factory) as session:
            if not reaction_access.reaction_project_owned_by(
                session, payload.reaction_project_id, owner_scope_id
            ):
                raise KeyError("Reaction project not found.")
    normalization = normalize_file(
        session_factory,
        payload.file_id,
        FileNormalizationRequest(
            target_format="moltrace_reaction_table_json",
            metadata_json={
                **payload.metadata_json,
                "reaction_project_id": payload.reaction_project_id,
                "review_required": True,
            },
        ),
        storage_root=storage_root,
    )
    link_id = None
    if payload.external_record_id is not None and payload.reaction_project_id is not None:
        with session_scope(session_factory) as session:
            if session.get(ExternalSystemRecordORM, payload.external_record_id) is not None:
                link = ExternalObjectLinkORM(
                    external_record_id=payload.external_record_id,
                    moltrace_resource_type="reaction_project",
                    moltrace_resource_id=payload.reaction_project_id,
                    relation_type="source_of",
                    metadata_json=_json_dump(
                        {"file_id": payload.file_id, "normalization_run_id": normalization.id},
                        default={},
                    ),
                )
                session.add(link)
                session.flush()
                link_id = link.id
    return IntegrationImportResponse(
        status="requires_review",
        review_required=True,
        file_id=payload.file_id,
        normalization_run_id=normalization.id,
        external_record_id=payload.external_record_id,
        external_link_id=link_id,
        warnings_json=normalization.warnings_json,
        notes_json=["Reaction experiment table imported as a normalized artifact; review required before official experiment creation."],
        metadata_json={
            "output_artifact_id": normalization.output_artifact_id,
            "reaction_project_id": payload.reaction_project_id,
        },
    )


def export_reaction_experiments(
    session_factory: sessionmaker[Session],
    payload: ReactionApprovedExperimentsExportRequest,
    *,
    owner_scope_id: int | None = None,
) -> IntegrationImportResponse:
    # Owner-scope every body-supplied experiment id (each resolves to a project): a non-owner
    # cannot export another tenant's experiments. Non-leaking 404 on the first unowned id.
    if owner_scope_id is not None and payload.experiment_ids_json:
        with session_scope(session_factory) as session:
            for experiment_id in payload.experiment_ids_json:
                if not reaction_access.reaction_experiment_owned_by(
                    session, experiment_id, owner_scope_id
                ):
                    raise KeyError("Reaction experiment not found.")
    sync = create_outbound_sync_job(
        session_factory,
        OutboundSyncJobCreate(
            connector_id=payload.connector_id,
            target_system=payload.target_system,
            source_resource_type="reaction_experiment",
            source_resource_id=payload.experiment_ids_json[0] if payload.experiment_ids_json else 1,
            payload_summary_json={
                **payload.payload_summary_json,
                "experiment_ids_json": payload.experiment_ids_json,
                "review_required": True,
            },
            status="requires_review",
            notes_json=["Reaction experiment export package created for review."],
            metadata_json=payload.metadata_json,
        ),
    )
    return IntegrationImportResponse(
        status="requires_review",
        review_required=True,
        sync_job_id=sync.id,
        notes_json=["Reaction experiment export package created for review; no external update was sent."],
        metadata_json={"target_system": payload.target_system, "experiment_ids_json": payload.experiment_ids_json},
    )
