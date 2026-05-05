from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    BenchmarkDatasetCandidate,
    BenchmarkDatasetCandidateCreate,
    BenchmarkDatasetCandidateUpdate,
    DatasetVersion,
    DatasetVersionCreate,
    DatasetVersionUpdate,
    ExtractedAnalyticalRecord,
    ExtractedCitation,
    ExtractedReactionRecord,
    ExtractedRegulatoryRecord,
    FeatureRecord,
    FeatureRecordCreate,
    KnowledgeExtractionRun,
    KnowledgeExtractionRunCreate,
    KnowledgeGraphLink,
    KnowledgeGraphLinkCreate,
    KnowledgeRecordReviewRequest,
    KnowledgeRecordReviewResult,
    KnowledgeReviewTask,
    KnowledgeReviewTaskCreate,
    KnowledgeReviewTaskUpdate,
    KnowledgeSearchResult,
    KnowledgeSource,
    KnowledgeSourceCreate,
    KnowledgeSourceFile,
    KnowledgeSourceUpdate,
    ModelImprovementQueueItem,
    ModelImprovementQueueItemCreate,
    ModelImprovementQueueItemUpdate,
    TrainingDatasetCandidate,
    TrainingDatasetCandidateCreate,
    TrainingDatasetCandidateUpdate,
)
from .orm import (
    AuditEventORM,
    BenchmarkDatasetCandidateORM,
    DatasetVersionORM,
    ExtractedAnalyticalRecordORM,
    ExtractedCitationORM,
    ExtractedReactionRecordORM,
    ExtractedRegulatoryRecordORM,
    FeatureRecordORM,
    KnowledgeExtractionRunORM,
    KnowledgeGraphLinkORM,
    KnowledgeReviewTaskORM,
    KnowledgeSourceFileORM,
    KnowledgeSourceORM,
    ManagedFileRecordORM,
    ModelImprovementQueueItemORM,
    RegulatoryJurisdictionORM,
    TrainingDatasetCandidateORM,
    utcnow,
)


class KnowledgeFlywheelError(ValueError):
    pass


class KnowledgeFlywheelNotFoundError(KnowledgeFlywheelError):
    pass


@dataclass(frozen=True)
class KnowledgeFlywheelActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


_REVIEW_NOTE = "Extracted record requires review before use as trusted knowledge."
_SOURCE_NOTE = "Source-supported extraction only; citation missing warnings must be reviewed."
_PRIVATE_TEXT_KEY = "_parsed_text_cache"
_MAX_PRIVATE_PARSE_CHARS = 60_000
_MAX_EXCERPT_CHARS = 800
_MAX_FIELD_TEXT = 2_000
_RECORD_TABLES = {
    "reaction": ExtractedReactionRecordORM,
    "analytical": ExtractedAnalyticalRecordORM,
    "regulatory": ExtractedRegulatoryRecordORM,
    "citation": ExtractedCitationORM,
    "training_candidate": TrainingDatasetCandidateORM,
    "benchmark_candidate": BenchmarkDatasetCandidateORM,
}


def _json_dump(value: Any, *, default: Any = None) -> str:
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


def _json_int_list(value: str | None) -> list[int]:
    output: list[int] = []
    for item in _json_list(value):
        try:
            output.append(int(item))
        except (TypeError, ValueError):
            continue
    return output


def _public_metadata(value: str | None) -> dict[str, Any]:
    return {key: val for key, val in _json_dict(value).items() if not str(key).startswith("_")}


def _metadata_with_review(metadata: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    output = dict(metadata or {})
    output.update(extra)
    output.setdefault("human_review_required", True)
    return output


def _audit(
    session: Session,
    *,
    actor: KnowledgeFlywheelActor,
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


def create_source(
    session_factory: sessionmaker[Session],
    payload: KnowledgeSourceCreate,
    *,
    actor: KnowledgeFlywheelActor,
) -> KnowledgeSource:
    with session_scope(session_factory) as session:
        _require_jurisdiction(session, payload.jurisdiction_id)
        row = KnowledgeSourceORM(
            title=payload.title,
            source_type=payload.source_type,
            source_url=payload.source_url,
            doi=payload.doi,
            patent_number=payload.patent_number,
            jurisdiction_id=payload.jurisdiction_id,
            publisher=payload.publisher,
            publication_date=payload.publication_date,
            status=payload.status,
            reliability_label=payload.reliability_label,
            metadata_json=_json_dump(_metadata_with_review(payload.metadata_json)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="knowledge.source.create",
            message="Knowledge source created for source-supported extraction.",
            entity_type="knowledge_source",
            entity_id=row.id,
            metadata={"source_type": row.source_type, "reliability_label": row.reliability_label},
        )
        return _source_to_record(row)


def list_sources(
    session_factory: sessionmaker[Session],
    *,
    source_type: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[KnowledgeSource]:
    with session_scope(session_factory) as session:
        stmt = select(KnowledgeSourceORM).order_by(KnowledgeSourceORM.id.desc()).limit(limit)
        if source_type:
            stmt = stmt.where(KnowledgeSourceORM.source_type == source_type)
        if status:
            stmt = stmt.where(KnowledgeSourceORM.status == status)
        return [_source_to_record(row) for row in session.scalars(stmt).all()]


def get_source(session_factory: sessionmaker[Session], source_id: int) -> KnowledgeSource | None:
    with session_scope(session_factory) as session:
        row = session.get(KnowledgeSourceORM, source_id)
        return _source_to_record(row) if row is not None else None


def update_source(
    session_factory: sessionmaker[Session],
    source_id: int,
    payload: KnowledgeSourceUpdate,
    *,
    actor: KnowledgeFlywheelActor,
) -> KnowledgeSource | None:
    with session_scope(session_factory) as session:
        row = session.get(KnowledgeSourceORM, source_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        if "jurisdiction_id" in update:
            _require_jurisdiction(session, update["jurisdiction_id"])
        for field in (
            "title",
            "source_type",
            "source_url",
            "doi",
            "patent_number",
            "jurisdiction_id",
            "publisher",
            "publication_date",
            "status",
            "reliability_label",
        ):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(_metadata_with_review(update["metadata_json"]))
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="knowledge.source.update",
            message="Knowledge source updated.",
            entity_type="knowledge_source",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update)},
        )
        return _source_to_record(row)


def add_source_file(
    session_factory: sessionmaker[Session],
    source_id: int,
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
    file_id: int | None,
    metadata_json: dict[str, Any] | None,
    actor: KnowledgeFlywheelActor,
) -> KnowledgeSourceFile:
    if not content:
        raise KnowledgeFlywheelError("Knowledge source file cannot be empty.")
    with session_scope(session_factory) as session:
        _require_source(session, source_id)
        _require_file(session, file_id)
        sha256 = hashlib.sha256(content).hexdigest()
        parsed_text, warnings, parse_status = _parse_source_file(filename or "source.bin", content_type, content)
        parsed_hash = hashlib.sha256(_normalize_text(parsed_text).encode("utf-8")).hexdigest() if parsed_text else None
        metadata = _metadata_with_review(
            metadata_json,
            filename=filename,
            parsed_text_chars=len(parsed_text),
        )
        if parsed_text:
            metadata[_PRIVATE_TEXT_KEY] = parsed_text[:_MAX_PRIVATE_PARSE_CHARS]
        row = KnowledgeSourceFileORM(
            source_id=source_id,
            file_id=file_id,
            filename=filename,
            sha256=sha256,
            content_type=content_type,
            parsed_text_hash=parsed_hash,
            parse_status=parse_status,
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_REVIEW_NOTE, "Raw source text is not exposed in API responses."]),
            metadata_json=_json_dump(metadata),
        )
        session.add(row)
        session.flush()
        if parsed_text:
            _create_citations(session, source_id=source_id, source_file_id=row.id, text=parsed_text)
        _audit(
            session,
            actor=actor,
            event_type="knowledge.source_file.create",
            message="Knowledge source file registered with hash and citation extraction.",
            entity_type="knowledge_source_file",
            entity_id=row.id,
            metadata={"source_id": source_id, "sha256": sha256, "parse_status": parse_status},
        )
        return _source_file_to_record(row)


def list_source_files(session_factory: sessionmaker[Session], source_id: int) -> list[KnowledgeSourceFile]:
    with session_scope(session_factory) as session:
        _require_source(session, source_id)
        rows = session.scalars(
            select(KnowledgeSourceFileORM)
            .where(KnowledgeSourceFileORM.source_id == source_id)
            .order_by(KnowledgeSourceFileORM.id.desc())
        ).all()
        return [_source_file_to_record(row) for row in rows]


def run_extraction(
    session_factory: sessionmaker[Session],
    payload: KnowledgeExtractionRunCreate,
    *,
    actor: KnowledgeFlywheelActor,
) -> KnowledgeExtractionRun:
    with session_scope(session_factory) as session:
        source, source_file, text = _resolve_extraction_text(session, payload)
        warnings: list[str] = []
        if not text:
            warnings.append("Extraction text unavailable or unsupported for this source file.")
        citations = _citations_for_source(session, source.id, source_file.id if source_file else None)
        if not citations:
            warnings.append("citation missing")
        now = utcnow()
        run = KnowledgeExtractionRunORM(
            source_id=source.id,
            source_file_id=source_file.id if source_file else None,
            extraction_type=payload.extraction_type,
            status="running",
            model_or_method=payload.model_or_method or "rule_based_extraction",
            method_version=payload.method_version or "phase57-v1",
            extracted_count=0,
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_REVIEW_NOTE, _SOURCE_NOTE]),
            created_at=now,
            metadata_json=_json_dump(_metadata_with_review(payload.metadata_json, external_llm_used=False)),
        )
        session.add(run)
        session.flush()
        created_count = 0
        extraction_types = _expanded_extraction_types(payload.extraction_type)
        citation_ids = [row.id for row in citations]
        if text:
            if "reaction" in extraction_types:
                record = _extract_reaction(session, run, source, text, citation_ids)
                if record is not None:
                    created_count += 1
            if "analytical" in extraction_types:
                record = _extract_analytical(session, run, source, text, citation_ids)
                if record is not None:
                    created_count += 1
            if "regulatory" in extraction_types:
                record = _extract_regulatory(session, run, source, text, citation_ids)
                if record is not None:
                    created_count += 1
        if payload.extraction_type == "citation_only":
            created_count = len(citations)
        run.extracted_count = created_count
        run.status = "requires_review" if created_count else "failed"
        if created_count and payload.extraction_type == "citation_only":
            run.status = "succeeded"
        run.finished_at = utcnow()
        if created_count == 0 and "No extracted record" not in warnings:
            warnings.append("No extracted record was created by the rule-based extractor.")
        run.warnings_json = _json_dump(warnings)
        _audit(
            session,
            actor=actor,
            event_type="knowledge.extraction.run",
            message="Knowledge extraction run completed; extracted records require review.",
            entity_type="knowledge_extraction_run",
            entity_id=run.id,
            metadata={"source_id": source.id, "extracted_count": created_count, "status": run.status},
        )
        return _run_to_record(run)


def list_extraction_runs(session_factory: sessionmaker[Session], *, source_id: int | None = None, limit: int = 200) -> list[KnowledgeExtractionRun]:
    with session_scope(session_factory) as session:
        stmt = select(KnowledgeExtractionRunORM).order_by(KnowledgeExtractionRunORM.id.desc()).limit(limit)
        if source_id is not None:
            stmt = stmt.where(KnowledgeExtractionRunORM.source_id == source_id)
        return [_run_to_record(row) for row in session.scalars(stmt).all()]


def get_extraction_run(session_factory: sessionmaker[Session], run_id: int) -> KnowledgeExtractionRun | None:
    with session_scope(session_factory) as session:
        row = session.get(KnowledgeExtractionRunORM, run_id)
        return _run_to_record(row) if row is not None else None


def list_reaction_records(session_factory: sessionmaker[Session], run_id: int) -> list[ExtractedReactionRecord]:
    with session_scope(session_factory) as session:
        _require_run(session, run_id)
        rows = session.scalars(
            select(ExtractedReactionRecordORM)
            .where(ExtractedReactionRecordORM.extraction_run_id == run_id)
            .order_by(ExtractedReactionRecordORM.id.asc())
        ).all()
        return [_reaction_to_record(row) for row in rows]


def list_analytical_records(session_factory: sessionmaker[Session], run_id: int) -> list[ExtractedAnalyticalRecord]:
    with session_scope(session_factory) as session:
        _require_run(session, run_id)
        rows = session.scalars(
            select(ExtractedAnalyticalRecordORM)
            .where(ExtractedAnalyticalRecordORM.extraction_run_id == run_id)
            .order_by(ExtractedAnalyticalRecordORM.id.asc())
        ).all()
        return [_analytical_to_record(row) for row in rows]


def list_regulatory_records(session_factory: sessionmaker[Session], run_id: int) -> list[ExtractedRegulatoryRecord]:
    with session_scope(session_factory) as session:
        _require_run(session, run_id)
        rows = session.scalars(
            select(ExtractedRegulatoryRecordORM)
            .where(ExtractedRegulatoryRecordORM.extraction_run_id == run_id)
            .order_by(ExtractedRegulatoryRecordORM.id.asc())
        ).all()
        return [_regulatory_to_record(row) for row in rows]


def create_review_task(
    session_factory: sessionmaker[Session],
    payload: KnowledgeReviewTaskCreate,
    *,
    actor: KnowledgeFlywheelActor,
) -> KnowledgeReviewTask:
    with session_scope(session_factory) as session:
        _require_record(session, payload.record_type, payload.record_id)
        if payload.extraction_run_id is not None:
            _require_run(session, payload.extraction_run_id)
        row = KnowledgeReviewTaskORM(
            extraction_run_id=payload.extraction_run_id,
            record_type=payload.record_type,
            record_id=payload.record_id,
            title=payload.title,
            status=payload.status,
            assigned_to=payload.assigned_to,
            metadata_json=_json_dump(_metadata_with_review(payload.metadata_json)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="knowledge.review_task.create",
            message="Knowledge review task created.",
            entity_type="knowledge_review_task",
            entity_id=row.id,
            metadata={"record_type": row.record_type, "record_id": row.record_id},
        )
        return _task_to_record(row)


def list_review_tasks(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    record_type: str | None = None,
    limit: int = 200,
) -> list[KnowledgeReviewTask]:
    with session_scope(session_factory) as session:
        stmt = select(KnowledgeReviewTaskORM).order_by(KnowledgeReviewTaskORM.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(KnowledgeReviewTaskORM.status == status)
        if record_type:
            stmt = stmt.where(KnowledgeReviewTaskORM.record_type == record_type)
        return [_task_to_record(row) for row in session.scalars(stmt).all()]


def update_review_task(
    session_factory: sessionmaker[Session],
    task_id: int,
    payload: KnowledgeReviewTaskUpdate,
    *,
    actor: KnowledgeFlywheelActor,
) -> KnowledgeReviewTask | None:
    with session_scope(session_factory) as session:
        row = session.get(KnowledgeReviewTaskORM, task_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in ("title", "status", "assigned_to", "reviewer_name", "reviewer_comment"):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(_metadata_with_review(update["metadata_json"]))
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="knowledge.review_task.update",
            message="Knowledge review task updated.",
            entity_type="knowledge_review_task",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _task_to_record(row)


def approve_record(
    session_factory: sessionmaker[Session],
    record_id: int,
    payload: KnowledgeRecordReviewRequest,
    *,
    actor: KnowledgeFlywheelActor,
) -> KnowledgeRecordReviewResult:
    return _review_record(session_factory, record_id, payload, accepted=True, actor=actor)


def reject_record(
    session_factory: sessionmaker[Session],
    record_id: int,
    payload: KnowledgeRecordReviewRequest,
    *,
    actor: KnowledgeFlywheelActor,
) -> KnowledgeRecordReviewResult:
    return _review_record(session_factory, record_id, payload, accepted=False, actor=actor)


def link_record(
    session_factory: sessionmaker[Session],
    record_id: int,
    payload: KnowledgeGraphLinkCreate,
    *,
    actor: KnowledgeFlywheelActor,
) -> KnowledgeGraphLink:
    with session_scope(session_factory) as session:
        record = _require_record(session, payload.record_type, record_id)
        if not _record_is_accepted(record, payload.record_type):
            raise KnowledgeFlywheelError("Extracted record must be accepted by reviewer before linking.")
        row = KnowledgeGraphLinkORM(
            record_type=payload.record_type,
            record_id=record_id,
            target_type=payload.target_type,
            target_id=str(payload.target_id),
            relation_type=payload.relation_type,
            confidence_label=payload.confidence_label,
            metadata_json=_json_dump(_metadata_with_review(payload.metadata_json, linked_after_review=True)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="knowledge.record.link",
            message="Accepted extracted record linked to downstream target.",
            entity_type="knowledge_graph_link",
            entity_id=row.id,
            metadata={"record_type": row.record_type, "record_id": row.record_id, "target_type": row.target_type},
        )
        return _link_to_record(row)


def search_knowledge(
    session_factory: sessionmaker[Session],
    *,
    query: str | None,
    record_type: str | None = None,
    limit: int = 50,
) -> KnowledgeSearchResult:
    tokens = _query_tokens(query or "")
    with session_scope(session_factory) as session:
        sources: list[KnowledgeSource] = []
        reactions: list[ExtractedReactionRecord] = []
        analytical: list[ExtractedAnalyticalRecord] = []
        regulatory: list[ExtractedRegulatoryRecord] = []
        citations: list[ExtractedCitation] = []
        if record_type in {None, "source"}:
            rows = session.scalars(select(KnowledgeSourceORM).order_by(KnowledgeSourceORM.id.desc()).limit(500)).all()
            sources = [_source_to_record(row) for row in rows if _matches(tokens, row.title, row.doi, row.patent_number)][:limit]
        if record_type in {None, "reaction"}:
            rows = session.scalars(select(ExtractedReactionRecordORM).order_by(ExtractedReactionRecordORM.id.desc()).limit(500)).all()
            reactions = [_reaction_to_record(row) for row in rows if _matches(tokens, row.reaction_name, row.reaction_type, row.product_summary, row.substrate_summary)][:limit]
        if record_type in {None, "analytical"}:
            rows = session.scalars(select(ExtractedAnalyticalRecordORM).order_by(ExtractedAnalyticalRecordORM.id.desc()).limit(500)).all()
            analytical = [_analytical_to_record(row) for row in rows if _matches(tokens, row.compound_name, row.formula, row.hrms_text, row.nmr_1h_text)][:limit]
        if record_type in {None, "regulatory"}:
            rows = session.scalars(select(ExtractedRegulatoryRecordORM).order_by(ExtractedRegulatoryRecordORM.id.desc()).limit(500)).all()
            regulatory = [_regulatory_to_record(row) for row in rows if _matches(tokens, row.topic, row.requirement_text)][:limit]
        if record_type in {None, "citation"}:
            rows = session.scalars(select(ExtractedCitationORM).order_by(ExtractedCitationORM.id.desc()).limit(500)).all()
            citations = [_citation_to_record(row) for row in rows if _matches(tokens, row.citation_label, row.quote_excerpt, row.summary)][:limit]
        return KnowledgeSearchResult(
            query=query,
            sources=sources,
            reaction_records=reactions,
            analytical_records=analytical,
            regulatory_records=regulatory,
            citations=citations,
            notes=[_SOURCE_NOTE],
            human_review_required=True,
        )


def create_training_candidate(
    session_factory: sessionmaker[Session],
    payload: TrainingDatasetCandidateCreate,
    *,
    actor: KnowledgeFlywheelActor,
) -> TrainingDatasetCandidate:
    with session_scope(session_factory) as session:
        _require_source_optional(session, payload.source_id)
        _require_record(session, payload.record_type, payload.record_id)
        _validate_citation_ids(session, payload.citation_ids_json)
        _ensure_candidate_acceptance_allowed(payload.status, payload.metadata_json)
        flags = list(payload.quality_flags_json)
        if not payload.citation_ids_json:
            flags.append("citation missing")
        row = TrainingDatasetCandidateORM(
            source_id=payload.source_id,
            record_type=payload.record_type,
            record_id=payload.record_id,
            dataset_type=payload.dataset_type,
            status=payload.status,
            quality_flags_json=_json_dump(sorted(set(flags))),
            citation_ids_json=_json_dump(payload.citation_ids_json),
            metadata_json=_json_dump(_metadata_with_review(payload.metadata_json)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="knowledge.training_candidate.create",
            message="Training dataset candidate created for review.",
            entity_type="training_dataset_candidate",
            entity_id=row.id,
            metadata={"dataset_type": row.dataset_type, "status": row.status},
        )
        return _training_candidate_to_record(row)


def list_training_candidates(session_factory: sessionmaker[Session], *, status: str | None = None, limit: int = 200) -> list[TrainingDatasetCandidate]:
    with session_scope(session_factory) as session:
        stmt = select(TrainingDatasetCandidateORM).order_by(TrainingDatasetCandidateORM.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(TrainingDatasetCandidateORM.status == status)
        return [_training_candidate_to_record(row) for row in session.scalars(stmt).all()]


def update_training_candidate(
    session_factory: sessionmaker[Session],
    candidate_id: int,
    payload: TrainingDatasetCandidateUpdate,
    *,
    actor: KnowledgeFlywheelActor,
) -> TrainingDatasetCandidate | None:
    with session_scope(session_factory) as session:
        row = session.get(TrainingDatasetCandidateORM, candidate_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        metadata = update.get("metadata_json") if "metadata_json" in update else _json_dict(row.metadata_json)
        if update.get("status") == "accepted":
            _ensure_candidate_acceptance_allowed("accepted", metadata)
        if "status" in update:
            row.status = update["status"]
        if "quality_flags_json" in update:
            row.quality_flags_json = _json_dump(update["quality_flags_json"] or [])
        if "citation_ids_json" in update:
            _validate_citation_ids(session, update["citation_ids_json"] or [])
            row.citation_ids_json = _json_dump(update["citation_ids_json"] or [])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(_metadata_with_review(update["metadata_json"]))
        _audit(
            session,
            actor=actor,
            event_type="knowledge.training_candidate.update",
            message="Training dataset candidate updated.",
            entity_type="training_dataset_candidate",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _training_candidate_to_record(row)


def create_benchmark_candidate(
    session_factory: sessionmaker[Session],
    payload: BenchmarkDatasetCandidateCreate,
    *,
    actor: KnowledgeFlywheelActor,
) -> BenchmarkDatasetCandidate:
    with session_scope(session_factory) as session:
        _require_source_optional(session, payload.source_id)
        _require_record(session, payload.record_type, payload.record_id)
        _ensure_candidate_acceptance_allowed(payload.status, payload.metadata_json)
        flags = list(payload.quality_flags_json)
        if payload.leakage_risk_label in {"high", "unknown"}:
            flags.append(f"leakage_risk_{payload.leakage_risk_label}")
        row = BenchmarkDatasetCandidateORM(
            source_id=payload.source_id,
            record_type=payload.record_type,
            record_id=payload.record_id,
            benchmark_type=payload.benchmark_type,
            status=payload.status,
            split_recommendation=payload.split_recommendation,
            leakage_risk_label=payload.leakage_risk_label,
            quality_flags_json=_json_dump(sorted(set(flags))),
            metadata_json=_json_dump(_metadata_with_review(payload.metadata_json)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="knowledge.benchmark_candidate.create",
            message="Benchmark candidate created for review.",
            entity_type="benchmark_dataset_candidate",
            entity_id=row.id,
            metadata={"benchmark_type": row.benchmark_type, "leakage_risk_label": row.leakage_risk_label},
        )
        return _benchmark_candidate_to_record(row)


def list_benchmark_candidates(session_factory: sessionmaker[Session], *, status: str | None = None, limit: int = 200) -> list[BenchmarkDatasetCandidate]:
    with session_scope(session_factory) as session:
        stmt = select(BenchmarkDatasetCandidateORM).order_by(BenchmarkDatasetCandidateORM.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(BenchmarkDatasetCandidateORM.status == status)
        return [_benchmark_candidate_to_record(row) for row in session.scalars(stmt).all()]


def update_benchmark_candidate(
    session_factory: sessionmaker[Session],
    candidate_id: int,
    payload: BenchmarkDatasetCandidateUpdate,
    *,
    actor: KnowledgeFlywheelActor,
) -> BenchmarkDatasetCandidate | None:
    with session_scope(session_factory) as session:
        row = session.get(BenchmarkDatasetCandidateORM, candidate_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        metadata = update.get("metadata_json") if "metadata_json" in update else _json_dict(row.metadata_json)
        if update.get("status") == "accepted":
            _ensure_candidate_acceptance_allowed("accepted", metadata)
        for field in ("status", "split_recommendation", "leakage_risk_label"):
            if field in update:
                setattr(row, field, update[field])
        if "quality_flags_json" in update:
            row.quality_flags_json = _json_dump(update["quality_flags_json"] or [])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(_metadata_with_review(update["metadata_json"]))
        _audit(
            session,
            actor=actor,
            event_type="knowledge.benchmark_candidate.update",
            message="Benchmark candidate updated.",
            entity_type="benchmark_dataset_candidate",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _benchmark_candidate_to_record(row)


def create_model_queue_item(
    session_factory: sessionmaker[Session],
    payload: ModelImprovementQueueItemCreate,
    *,
    actor: KnowledgeFlywheelActor,
) -> ModelImprovementQueueItem:
    with session_scope(session_factory) as session:
        if payload.linked_record_type and payload.linked_record_id:
            _require_record(session, payload.linked_record_type, payload.linked_record_id)
        row = ModelImprovementQueueItemORM(
            source_type=payload.source_type,
            target_module=payload.target_module,
            linked_record_type=payload.linked_record_type,
            linked_record_id=payload.linked_record_id,
            priority=payload.priority,
            status=payload.status,
            summary=payload.summary,
            metadata_json=_json_dump(_metadata_with_review(payload.metadata_json)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="knowledge.model_improvement_queue.create",
            message="Model improvement queue item created.",
            entity_type="model_improvement_queue_item",
            entity_id=row.id,
            metadata={"source_type": row.source_type, "target_module": row.target_module},
        )
        return _model_queue_to_record(row)


def list_model_queue_items(session_factory: sessionmaker[Session], *, status: str | None = None, limit: int = 200) -> list[ModelImprovementQueueItem]:
    with session_scope(session_factory) as session:
        stmt = select(ModelImprovementQueueItemORM).order_by(ModelImprovementQueueItemORM.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(ModelImprovementQueueItemORM.status == status)
        return [_model_queue_to_record(row) for row in session.scalars(stmt).all()]


def update_model_queue_item(
    session_factory: sessionmaker[Session],
    item_id: int,
    payload: ModelImprovementQueueItemUpdate,
    *,
    actor: KnowledgeFlywheelActor,
) -> ModelImprovementQueueItem | None:
    with session_scope(session_factory) as session:
        row = session.get(ModelImprovementQueueItemORM, item_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in ("priority", "status", "summary"):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(_metadata_with_review(update["metadata_json"]))
        _audit(
            session,
            actor=actor,
            event_type="knowledge.model_improvement_queue.update",
            message="Model improvement queue item updated.",
            entity_type="model_improvement_queue_item",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _model_queue_to_record(row)


def create_feature_record(
    session_factory: sessionmaker[Session],
    payload: FeatureRecordCreate,
    *,
    actor: KnowledgeFlywheelActor,
) -> FeatureRecord:
    with session_scope(session_factory) as session:
        row = FeatureRecordORM(
            record_type=payload.record_type,
            record_id=payload.record_id,
            feature_family=payload.feature_family,
            features_json=_json_dump(payload.features_json),
            feature_version=payload.feature_version,
            metadata_json=_json_dump(_metadata_with_review(payload.metadata_json)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="knowledge.feature.create",
            message="Feature record created for ML readiness review.",
            entity_type="feature_record",
            entity_id=row.id,
            metadata={"record_type": row.record_type, "feature_family": row.feature_family},
        )
        return _feature_to_record(row)


def list_feature_records(session_factory: sessionmaker[Session], record_type: str, record_id: int) -> list[FeatureRecord]:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(FeatureRecordORM)
            .where(FeatureRecordORM.record_type == record_type, FeatureRecordORM.record_id == record_id)
            .order_by(FeatureRecordORM.id.desc())
        ).all()
        return [_feature_to_record(row) for row in rows]


def create_dataset_version(
    session_factory: sessionmaker[Session],
    payload: DatasetVersionCreate,
    *,
    actor: KnowledgeFlywheelActor,
) -> DatasetVersion:
    with session_scope(session_factory) as session:
        row = DatasetVersionORM(
            dataset_type=payload.dataset_type,
            name=payload.name,
            version=payload.version,
            source_record_ids_json=_json_dump(payload.source_record_ids_json),
            split_json=_json_dump(payload.split_json),
            quality_summary_json=_json_dump(payload.quality_summary_json),
            leakage_warnings_json=_json_dump(payload.leakage_warnings_json),
            status=payload.status,
            metadata_json=_json_dump(_metadata_with_review(payload.metadata_json)),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise KnowledgeFlywheelError("Dataset version already exists for this dataset type, name, and version.") from exc
        _audit(
            session,
            actor=actor,
            event_type="knowledge.dataset_version.create",
            message="Dataset version created with source record IDs and split definitions.",
            entity_type="dataset_version",
            entity_id=row.id,
            metadata={"dataset_type": row.dataset_type, "status": row.status},
        )
        return _dataset_version_to_record(row)


def list_dataset_versions(session_factory: sessionmaker[Session], *, status: str | None = None, limit: int = 200) -> list[DatasetVersion]:
    with session_scope(session_factory) as session:
        stmt = select(DatasetVersionORM).order_by(DatasetVersionORM.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(DatasetVersionORM.status == status)
        return [_dataset_version_to_record(row) for row in session.scalars(stmt).all()]


def get_dataset_version(session_factory: sessionmaker[Session], dataset_version_id: int) -> DatasetVersion | None:
    with session_scope(session_factory) as session:
        row = session.get(DatasetVersionORM, dataset_version_id)
        return _dataset_version_to_record(row) if row is not None else None


def update_dataset_version(
    session_factory: sessionmaker[Session],
    dataset_version_id: int,
    payload: DatasetVersionUpdate,
    *,
    actor: KnowledgeFlywheelActor,
) -> DatasetVersion | None:
    with session_scope(session_factory) as session:
        row = session.get(DatasetVersionORM, dataset_version_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in ("name", "version", "status"):
            if field in update:
                setattr(row, field, update[field])
        for field in ("source_record_ids_json", "split_json", "quality_summary_json", "leakage_warnings_json", "metadata_json"):
            if field in update:
                value = _metadata_with_review(update[field]) if field == "metadata_json" else update[field]
                setattr(row, field, _json_dump(value))
        _audit(
            session,
            actor=actor,
            event_type="knowledge.dataset_version.update",
            message="Dataset version updated.",
            entity_type="dataset_version",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _dataset_version_to_record(row)


def _extract_reaction(
    session: Session,
    run: KnowledgeExtractionRunORM,
    source: KnowledgeSourceORM,
    text: str,
    citation_ids: list[int],
) -> ExtractedReactionRecordORM | None:
    lowered = text.lower()
    if not any(term in lowered for term in ("reaction", "yield", "product", "substrate")):
        return None
    warnings = [] if citation_ids else ["citation missing"]
    row = ExtractedReactionRecordORM(
        extraction_run_id=run.id,
        source_id=source.id,
        citation_ids_json=_json_dump(citation_ids),
        reaction_name=_extract_labeled_value(text, "reaction") or "extracted reaction",
        reaction_type=_first_match(text, r"(Suzuki|Buchwald|amide coupling|hydrogenation|oxidation|reduction|alkylation|acylation)", flags=re.I),
        substrate_summary=_extract_labeled_value(text, "substrate"),
        product_summary=_extract_labeled_value(text, "product"),
        product_smiles=_first_match(text, r"product\s+smiles\s*[:=]\s*([A-Za-z0-9@+\-\[\]\(\)=#$\\/%.]+)", flags=re.I),
        reagent_json=_json_dump(_extract_named_list(text, "reagent")),
        solvent_json=_json_dump(_extract_named_list(text, "solvent")),
        catalyst_json=_json_dump(_extract_named_list(text, "catalyst")),
        ligand_json=_json_dump(_extract_named_list(text, "ligand")),
        base_json=_json_dump(_extract_named_list(text, "base")),
        additive_json=_json_dump(_extract_named_list(text, "additive")),
        temperature_c=_float_match(text, r"(-?\d+(?:\.\d+)?)\s*(?:°C|C\b|deg C)"),
        time_h=_float_match(text, r"(\d+(?:\.\d+)?)\s*(?:h|hr|hours?)\b"),
        concentration=_first_match(text, r"(\d+(?:\.\d+)?\s*M)\b"),
        scale=_first_match(text, r"(\d+(?:\.\d+)?\s*(?:mmol|mol|g|mg))\b", flags=re.I),
        yield_percent=_percent_after(text, "yield"),
        conversion_percent=_percent_after(text, "conversion"),
        selectivity_percent=_percent_after(text, "selectivity"),
        ee_percent=_percent_after(text, "ee"),
        impurity_summary=_extract_sentence_with(text, "impurity"),
        conditions_json=_json_dump({"temperature_c": _float_match(text, r"(-?\d+(?:\.\d+)?)\s*(?:°C|C\b|deg C)"), "time_h": _float_match(text, r"(\d+(?:\.\d+)?)\s*(?:h|hr|hours?)\b")}),
        outcome_json=_json_dump({"yield_percent": _percent_after(text, "yield"), "conversion_percent": _percent_after(text, "conversion")}),
        confidence_score=0.65 if citation_ids else 0.35,
        review_status="unreviewed",
        warnings_json=_json_dump(warnings),
        notes_json=_json_dump([_REVIEW_NOTE]),
        metadata_json=_json_dump(_metadata_with_review({"extractor": "rule_based_reaction_v1"})),
    )
    session.add(row)
    session.flush()
    _auto_review_task(session, run.id, "reaction", row.id, "Review extracted reaction record")
    return row


def _extract_analytical(
    session: Session,
    run: KnowledgeExtractionRunORM,
    source: KnowledgeSourceORM,
    text: str,
    citation_ids: list[int],
) -> ExtractedAnalyticalRecordORM | None:
    lowered = text.lower()
    if not any(term in lowered for term in ("nmr", "hrms", "ms/ms", "m/z", "formula", "exact mass")):
        return None
    warnings = [] if citation_ids else ["citation missing"]
    row = ExtractedAnalyticalRecordORM(
        extraction_run_id=run.id,
        source_id=source.id,
        citation_ids_json=_json_dump(citation_ids),
        compound_name=_extract_labeled_value(text, "compound") or _extract_labeled_value(text, "analyte"),
        structure_input=_first_match(text, r"SMILES\s*[:=]\s*([A-Za-z0-9@+\-\[\]\(\)=#$\\/%.]+)", flags=re.I),
        structure_format="smiles" if re.search(r"SMILES\s*[:=]", text, re.I) else None,
        formula=_first_match(text, r"\bformula\s*[:=]\s*([A-Z][A-Za-z0-9]+)", flags=re.I),
        exact_mass=_float_match(text, r"(?:exact mass|calcd|calculated)\s*[:=]?\s*(\d+(?:\.\d+)?)", flags=re.I),
        nmr_1h_text=_extract_spectrum_block(text, "1H NMR"),
        nmr_13c_text=_extract_spectrum_block(text, "13C NMR"),
        nmr_2d_summary=_extract_sentence_with(text, "HSQC") or _extract_sentence_with(text, "HMBC") or _extract_sentence_with(text, "COSY"),
        hrms_text=_extract_sentence_with(text, "HRMS") or _extract_sentence_with(text, "m/z"),
        msms_summary=_extract_sentence_with(text, "MS/MS") or _extract_sentence_with(text, "MSMS"),
        solvent=_first_match(text, r"\b(?:CDCl3|DMSO-d6|MeOD|CD3OD|D2O|acetone-d6|benzene-d6)\b", flags=re.I),
        frequency_mhz=_float_match(text, r"(\d{2,4}(?:\.\d+)?)\s*MHz", flags=re.I),
        analytical_method="nmr" if "nmr" in lowered else ("hrms" if "hrms" in lowered else "other"),
        confidence_score=0.7 if citation_ids else 0.4,
        review_status="unreviewed",
        warnings_json=_json_dump(warnings),
        notes_json=_json_dump([_REVIEW_NOTE]),
        metadata_json=_json_dump(_metadata_with_review({"extractor": "rule_based_analytical_v1"})),
    )
    session.add(row)
    session.flush()
    _auto_review_task(session, run.id, "analytical", row.id, "Review extracted analytical record")
    return row


def _extract_regulatory(
    session: Session,
    run: KnowledgeExtractionRunORM,
    source: KnowledgeSourceORM,
    text: str,
    citation_ids: list[int],
) -> ExtractedRegulatoryRecordORM | None:
    lowered = text.lower()
    if not any(term in lowered for term in ("shall", "should", "must", "require", "threshold", "pde", "nitrosamine", "validation")):
        return None
    warnings = [] if citation_ids else ["citation missing"]
    topic = _regulatory_topic(text)
    thresholds = _thresholds(text)
    requirement = _extract_requirement_text(text)
    row = ExtractedRegulatoryRecordORM(
        extraction_run_id=run.id,
        source_id=source.id,
        citation_ids_json=_json_dump(citation_ids),
        jurisdiction_id=source.jurisdiction_id,
        topic=topic,
        requirement_text=requirement,
        threshold_summary_json=_json_dump(thresholds) if thresholds else None,
        rule_candidate_json=_json_dump({"topic": topic, "thresholds": thresholds, "source_supported": bool(citation_ids)}),
        action_candidate_json=_json_dump({"action_type": "human_review", "reason": "requires review"}),
        confidence_score=0.68 if citation_ids else 0.38,
        review_status="unreviewed",
        warnings_json=_json_dump(warnings),
        notes_json=_json_dump([_REVIEW_NOTE, "No unsupported scientific or regulatory claim is created."]),
        metadata_json=_json_dump(_metadata_with_review({"extractor": "rule_based_regulatory_v1"})),
    )
    session.add(row)
    session.flush()
    _auto_review_task(session, run.id, "regulatory", row.id, "Review extracted regulatory record")
    return row


def _review_record(
    session_factory: sessionmaker[Session],
    record_id: int,
    payload: KnowledgeRecordReviewRequest,
    *,
    accepted: bool,
    actor: KnowledgeFlywheelActor,
) -> KnowledgeRecordReviewResult:
    status_value = "accepted" if accepted else "rejected"
    task_status = "accepted" if accepted else "rejected"
    with session_scope(session_factory) as session:
        row = _require_record(session, payload.record_type, record_id)
        if payload.record_type in {"reaction", "analytical", "regulatory"}:
            row.review_status = status_value
        elif payload.record_type in {"training_candidate", "benchmark_candidate"}:
            row.status = status_value
        metadata = _json_dict(row.metadata_json)
        metadata["reviewer_name"] = payload.reviewer_name
        metadata["reviewer_comment"] = payload.reviewer_comment
        metadata["review_metadata"] = payload.metadata_json
        metadata["human_review_required"] = True
        row.metadata_json = _json_dump(metadata)
        tasks = session.scalars(
            select(KnowledgeReviewTaskORM).where(
                KnowledgeReviewTaskORM.record_type == payload.record_type,
                KnowledgeReviewTaskORM.record_id == record_id,
            )
        ).all()
        for task in tasks:
            task.status = task_status
            task.reviewer_name = payload.reviewer_name
            task.reviewer_comment = payload.reviewer_comment
            task.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type=f"knowledge.record.{status_value}",
            message=f"Extracted record {status_value} by reviewer.",
            entity_type=f"knowledge_{payload.record_type}_record",
            entity_id=record_id,
            metadata={"reviewer_name": payload.reviewer_name},
        )
        return KnowledgeRecordReviewResult(
            record_type=payload.record_type,
            record_id=record_id,
            review_status=status_value,
            reviewer_name=payload.reviewer_name,
            reviewer_comment=payload.reviewer_comment,
            message=f"Extracted record {status_value} by reviewer.",
            human_review_required=True,
        )


def _resolve_extraction_text(
    session: Session,
    payload: KnowledgeExtractionRunCreate,
) -> tuple[KnowledgeSourceORM, KnowledgeSourceFileORM | None, str]:
    source_file = session.get(KnowledgeSourceFileORM, payload.source_file_id) if payload.source_file_id is not None else None
    if payload.source_file_id is not None and source_file is None:
        raise KnowledgeFlywheelNotFoundError("Knowledge source file not found.")
    source_id = payload.source_id or (source_file.source_id if source_file is not None else None)
    source = _require_source(session, source_id)
    if source_file is not None and source_file.source_id != source.id:
        raise KnowledgeFlywheelError("Knowledge source file does not belong to requested source.")
    if source_file is not None:
        return source, source_file, _json_dict(source_file.metadata_json).get(_PRIVATE_TEXT_KEY, "")
    files = session.scalars(
        select(KnowledgeSourceFileORM)
        .where(KnowledgeSourceFileORM.source_id == source.id)
        .order_by(KnowledgeSourceFileORM.id.desc())
        .limit(5)
    ).all()
    text = "\n".join(str(_json_dict(file.metadata_json).get(_PRIVATE_TEXT_KEY, "")) for file in files)
    return source, files[0] if files else None, text.strip()


def _parse_source_file(filename: str, content_type: str | None, content: bytes) -> tuple[str, list[str], str]:
    lower = filename.lower()
    if lower.endswith((".txt", ".md", ".csv", ".tsv")) or (content_type or "").startswith("text/"):
        return _decode_text(content), [], "parsed"
    return "", ["Extraction is not supported for this file type in Phase 57; hash was preserved."], "failed"


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _create_citations(session: Session, *, source_id: int, source_file_id: int | None, text: str) -> list[ExtractedCitationORM]:
    chunks = _citation_chunks(text)
    rows: list[ExtractedCitationORM] = []
    for index, chunk in enumerate(chunks[:12], start=1):
        row = ExtractedCitationORM(
            source_id=source_id,
            source_file_id=source_file_id,
            citation_label=f"KS-{source_id}-F{source_file_id or 0}-P{index}",
            section_title="Extracted source text",
            paragraph_number=index,
            quote_excerpt=_truncate(chunk, _MAX_EXCERPT_CHARS),
            summary=_truncate(chunk, 320),
            confidence_score=0.75,
            metadata_json=_json_dump(_metadata_with_review({"generated_by": "phase57_rule_parser"})),
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def _citation_chunks(text: str) -> list[str]:
    paragraphs = [item.strip() for item in re.split(r"(?:\n\s*\n|(?<=[.!?])\s+)", text) if len(item.strip()) >= 20]
    if not paragraphs and text.strip():
        paragraphs = [text.strip()]
    return paragraphs


def _citations_for_source(session: Session, source_id: int, source_file_id: int | None = None) -> list[ExtractedCitationORM]:
    stmt = select(ExtractedCitationORM).where(ExtractedCitationORM.source_id == source_id)
    if source_file_id is not None:
        stmt = stmt.where(
            or_(ExtractedCitationORM.source_file_id == source_file_id, ExtractedCitationORM.source_file_id.is_(None))
        )
    return session.scalars(stmt.order_by(ExtractedCitationORM.id.asc())).all()


def _auto_review_task(session: Session, run_id: int, record_type: str, record_id: int, title: str) -> None:
    session.add(
        KnowledgeReviewTaskORM(
            extraction_run_id=run_id,
            record_type=record_type,
            record_id=record_id,
            title=title,
            status="open",
            metadata_json=_json_dump(_metadata_with_review({"auto_created": True})),
        )
    )


def _expanded_extraction_types(extraction_type: str) -> set[str]:
    if extraction_type == "mixed":
        return {"reaction", "analytical", "regulatory"}
    return {extraction_type}


def _require_source(session: Session, source_id: int | None) -> KnowledgeSourceORM:
    if source_id is None:
        raise KnowledgeFlywheelNotFoundError("Knowledge source not found.")
    row = session.get(KnowledgeSourceORM, source_id)
    if row is None:
        raise KnowledgeFlywheelNotFoundError("Knowledge source not found.")
    return row


def _require_source_optional(session: Session, source_id: int | None) -> None:
    if source_id is not None:
        _require_source(session, source_id)


def _require_jurisdiction(session: Session, jurisdiction_id: int | None) -> None:
    if jurisdiction_id is not None and session.get(RegulatoryJurisdictionORM, jurisdiction_id) is None:
        raise KnowledgeFlywheelNotFoundError("Regulatory jurisdiction not found.")


def _require_file(session: Session, file_id: int | None) -> None:
    if file_id is not None and session.get(ManagedFileRecordORM, file_id) is None:
        raise KnowledgeFlywheelNotFoundError("Managed file not found.")


def _require_run(session: Session, run_id: int) -> KnowledgeExtractionRunORM:
    row = session.get(KnowledgeExtractionRunORM, run_id)
    if row is None:
        raise KnowledgeFlywheelNotFoundError("Knowledge extraction run not found.")
    return row


def _require_record(session: Session, record_type: str, record_id: int) -> Any:
    table = _RECORD_TABLES.get(record_type)
    if table is None:
        raise KnowledgeFlywheelError("Unsupported knowledge record type.")
    row = session.get(table, record_id)
    if row is None:
        raise KnowledgeFlywheelNotFoundError("Knowledge record not found.")
    return row


def _record_is_accepted(row: Any, record_type: str) -> bool:
    if record_type in {"reaction", "analytical", "regulatory"}:
        return getattr(row, "review_status", None) == "accepted"
    if record_type in {"training_candidate", "benchmark_candidate"}:
        return getattr(row, "status", None) == "accepted"
    return record_type == "citation"


def _validate_citation_ids(session: Session, citation_ids: list[int]) -> None:
    for citation_id in citation_ids:
        if session.get(ExtractedCitationORM, citation_id) is None:
            raise KnowledgeFlywheelNotFoundError("Extracted citation not found.")


def _ensure_candidate_acceptance_allowed(status: str | None, metadata: dict[str, Any] | None) -> None:
    if status != "accepted":
        return
    metadata = metadata or {}
    if not metadata.get("reviewer_name") or not metadata.get("reviewer_comment"):
        raise KnowledgeFlywheelError("Accepted dataset candidates require human review metadata with reviewer_name and reviewer_comment.")


def _query_tokens(query: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z0-9]{2,}", query.lower()) if token]


def _matches(tokens: list[str], *values: Any) -> bool:
    if not tokens:
        return True
    text = " ".join(str(value or "") for value in values).lower()
    return all(token in text for token in tokens)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = _normalize_text(value)
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _first_match(text: str, pattern: str, *, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    value = match.group(1) if match.groups() else match.group(0)
    return _truncate(value, _MAX_FIELD_TEXT)


def _float_match(text: str, pattern: str, *, flags: int = 0) -> float | None:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _percent_after(text: str, label: str) -> float | None:
    return _float_match(text, rf"{re.escape(label)}\s*(?:=|:|of)?\s*(\d+(?:\.\d+)?)\s*%", flags=re.I)


def _extract_labeled_value(text: str, label: str) -> str | None:
    return _first_match(text, rf"{re.escape(label)}\s*[:=]\s*([^.;\n]+)", flags=re.I)


def _extract_named_list(text: str, label: str) -> list[dict[str, Any]]:
    value = _extract_labeled_value(text, label)
    if not value:
        return []
    return [{"name": item.strip()} for item in re.split(r",| and ", value) if item.strip()]


def _extract_sentence_with(text: str, needle: str) -> str | None:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if needle.lower() in sentence.lower():
            return _truncate(sentence, _MAX_FIELD_TEXT)
    return None


def _extract_spectrum_block(text: str, label: str) -> str | None:
    match = re.search(rf"({re.escape(label)}[^.]+(?:\.[^.]+)?)", text, re.I)
    return _truncate(match.group(1), _MAX_FIELD_TEXT) if match else None


def _regulatory_topic(text: str) -> str:
    lowered = text.lower()
    if "nitrosamine" in lowered or "n-nitroso" in lowered:
        return "nitrosamine"
    if "residual solvent" in lowered or "pde" in lowered:
        return "residual_solvent"
    if "qnmr" in lowered or "quantitative nmr" in lowered:
        return "qnmr"
    if "q2" in lowered or "q14" in lowered or "validation" in lowered:
        return "method_validation"
    if "ai governance" in lowered or "human oversight" in lowered:
        return "ai_governance"
    if "jurisdiction" in lowered:
        return "jurisdictional_map"
    if "report" in lowered or "submission" in lowered:
        return "reporting"
    if "threshold" in lowered or "impurity" in lowered:
        return "impurity_threshold"
    return "other"


def _thresholds(text: str) -> dict[str, Any]:
    percents = [float(item) for item in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]
    ppm = [float(item) for item in re.findall(r"(\d+(?:\.\d+)?)\s*ppm", text, re.I)]
    return {"percent_values": percents, "ppm_values": ppm}


def _extract_requirement_text(text: str) -> str | None:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"\b(shall|should|must|required|requires|threshold)\b", sentence, re.I):
            return _truncate(sentence, _MAX_FIELD_TEXT)
    return _truncate(text, _MAX_FIELD_TEXT)


def _source_to_record(row: KnowledgeSourceORM) -> KnowledgeSource:
    return KnowledgeSource(
        id=row.id,
        title=row.title,
        source_type=row.source_type,
        source_url=row.source_url,
        doi=row.doi,
        patent_number=row.patent_number,
        jurisdiction_id=row.jurisdiction_id,
        publisher=row.publisher,
        publication_date=row.publication_date,
        status=row.status,
        reliability_label=row.reliability_label,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_public_metadata(row.metadata_json),
        warnings=[],
        notes=[_REVIEW_NOTE],
        human_review_required=True,
    )


def _source_file_to_record(row: KnowledgeSourceFileORM) -> KnowledgeSourceFile:
    return KnowledgeSourceFile(
        id=row.id,
        source_id=row.source_id,
        file_id=row.file_id,
        filename=row.filename,
        sha256=row.sha256,
        content_type=row.content_type,
        parsed_text_hash=row.parsed_text_hash,
        parse_status=row.parse_status,
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _run_to_record(row: KnowledgeExtractionRunORM) -> KnowledgeExtractionRun:
    return KnowledgeExtractionRun(
        id=row.id,
        source_id=row.source_id,
        source_file_id=row.source_file_id,
        extraction_type=row.extraction_type,
        status=row.status,
        model_or_method=row.model_or_method,
        method_version=row.method_version,
        extracted_count=row.extracted_count,
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        finished_at=row.finished_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _citation_to_record(row: ExtractedCitationORM) -> ExtractedCitation:
    return ExtractedCitation(
        id=row.id,
        source_id=row.source_id,
        source_file_id=row.source_file_id,
        citation_label=row.citation_label,
        page_number=row.page_number,
        section_title=row.section_title,
        paragraph_number=row.paragraph_number,
        quote_excerpt=row.quote_excerpt,
        summary=row.summary,
        confidence_score=row.confidence_score,
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _reaction_to_record(row: ExtractedReactionRecordORM) -> ExtractedReactionRecord:
    return ExtractedReactionRecord(
        id=row.id,
        extraction_run_id=row.extraction_run_id,
        source_id=row.source_id,
        citation_ids_json=_json_int_list(row.citation_ids_json),
        reaction_name=row.reaction_name,
        reaction_type=row.reaction_type,
        substrate_summary=row.substrate_summary,
        product_summary=row.product_summary,
        product_smiles=row.product_smiles,
        reagent_json=[item for item in _json_list(row.reagent_json) if isinstance(item, dict)],
        solvent_json=[item for item in _json_list(row.solvent_json) if isinstance(item, dict)],
        catalyst_json=[item for item in _json_list(row.catalyst_json) if isinstance(item, dict)],
        ligand_json=[item for item in _json_list(row.ligand_json) if isinstance(item, dict)],
        base_json=[item for item in _json_list(row.base_json) if isinstance(item, dict)],
        additive_json=[item for item in _json_list(row.additive_json) if isinstance(item, dict)],
        temperature_c=row.temperature_c,
        time_h=row.time_h,
        concentration=row.concentration,
        scale=row.scale,
        yield_percent=row.yield_percent,
        conversion_percent=row.conversion_percent,
        selectivity_percent=row.selectivity_percent,
        ee_percent=row.ee_percent,
        impurity_summary=row.impurity_summary,
        conditions_json=_json_dict(row.conditions_json),
        outcome_json=_json_dict(row.outcome_json),
        confidence_score=row.confidence_score,
        review_status=row.review_status,
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _analytical_to_record(row: ExtractedAnalyticalRecordORM) -> ExtractedAnalyticalRecord:
    return ExtractedAnalyticalRecord(
        id=row.id,
        extraction_run_id=row.extraction_run_id,
        source_id=row.source_id,
        citation_ids_json=_json_int_list(row.citation_ids_json),
        compound_name=row.compound_name,
        structure_input=row.structure_input,
        structure_format=row.structure_format,
        formula=row.formula,
        exact_mass=row.exact_mass,
        nmr_1h_text=row.nmr_1h_text,
        nmr_13c_text=row.nmr_13c_text,
        nmr_2d_summary=row.nmr_2d_summary,
        hrms_text=row.hrms_text,
        msms_summary=row.msms_summary,
        solvent=row.solvent,
        frequency_mhz=row.frequency_mhz,
        analytical_method=row.analytical_method,
        confidence_score=row.confidence_score,
        review_status=row.review_status,
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _regulatory_to_record(row: ExtractedRegulatoryRecordORM) -> ExtractedRegulatoryRecord:
    return ExtractedRegulatoryRecord(
        id=row.id,
        extraction_run_id=row.extraction_run_id,
        source_id=row.source_id,
        citation_ids_json=_json_int_list(row.citation_ids_json),
        jurisdiction_id=row.jurisdiction_id,
        topic=row.topic,
        requirement_text=row.requirement_text,
        threshold_summary_json=_json_dict(row.threshold_summary_json),
        rule_candidate_json=_json_dict(row.rule_candidate_json),
        action_candidate_json=_json_dict(row.action_candidate_json),
        confidence_score=row.confidence_score,
        review_status=row.review_status,
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _task_to_record(row: KnowledgeReviewTaskORM) -> KnowledgeReviewTask:
    return KnowledgeReviewTask(
        id=row.id,
        extraction_run_id=row.extraction_run_id,
        record_type=row.record_type,
        record_id=row.record_id,
        title=row.title,
        status=row.status,
        assigned_to=row.assigned_to,
        reviewer_name=row.reviewer_name,
        reviewer_comment=row.reviewer_comment,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _link_to_record(row: KnowledgeGraphLinkORM) -> KnowledgeGraphLink:
    return KnowledgeGraphLink(
        id=row.id,
        record_type=row.record_type,
        record_id=row.record_id,
        target_type=row.target_type,
        target_id=row.target_id,
        relation_type=row.relation_type,
        confidence_label=row.confidence_label,
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _training_candidate_to_record(row: TrainingDatasetCandidateORM) -> TrainingDatasetCandidate:
    return TrainingDatasetCandidate(
        id=row.id,
        source_id=row.source_id,
        record_type=row.record_type,
        record_id=row.record_id,
        dataset_type=row.dataset_type,
        status=row.status,
        quality_flags_json=[str(item) for item in _json_list(row.quality_flags_json)],
        citation_ids_json=_json_int_list(row.citation_ids_json),
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _benchmark_candidate_to_record(row: BenchmarkDatasetCandidateORM) -> BenchmarkDatasetCandidate:
    return BenchmarkDatasetCandidate(
        id=row.id,
        source_id=row.source_id,
        record_type=row.record_type,
        record_id=row.record_id,
        benchmark_type=row.benchmark_type,
        status=row.status,
        split_recommendation=row.split_recommendation,
        leakage_risk_label=row.leakage_risk_label,
        quality_flags_json=[str(item) for item in _json_list(row.quality_flags_json)],
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _model_queue_to_record(row: ModelImprovementQueueItemORM) -> ModelImprovementQueueItem:
    return ModelImprovementQueueItem(
        id=row.id,
        source_type=row.source_type,
        target_module=row.target_module,
        linked_record_type=row.linked_record_type,
        linked_record_id=row.linked_record_id,
        priority=row.priority,
        status=row.status,
        summary=row.summary,
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _feature_to_record(row: FeatureRecordORM) -> FeatureRecord:
    return FeatureRecord(
        id=row.id,
        record_type=row.record_type,
        record_id=row.record_id,
        feature_family=row.feature_family,
        features_json=_json_dict(row.features_json),
        feature_version=row.feature_version,
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )


def _dataset_version_to_record(row: DatasetVersionORM) -> DatasetVersion:
    return DatasetVersion(
        id=row.id,
        dataset_type=row.dataset_type,
        name=row.name,
        version=row.version,
        source_record_ids_json=_json_list(row.source_record_ids_json),
        split_json=_json_dict(row.split_json),
        quality_summary_json=_json_dict(row.quality_summary_json),
        leakage_warnings_json=[str(item) for item in _json_list(row.leakage_warnings_json)],
        status=row.status,
        created_at=row.created_at,
        metadata_json=_public_metadata(row.metadata_json),
        human_review_required=True,
    )
