from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    RegulatoryAnswer,
    RegulatoryCitation,
    RegulatoryDossier,
    RegulatoryDossierCreate,
    RegulatoryDossierUpdate,
    RegulatoryEvidenceLink,
    RegulatoryEvidenceLinkCreate,
    RegulatoryJurisdiction,
    RegulatoryJurisdictionCreate,
    RegulatoryQuery,
    RegulatoryQueryCreate,
    RegulatoryReadinessReport,
    RegulatoryReadinessReportRequest,
    RegulatoryRequirement,
    RegulatoryRequirementCreate,
    RegulatoryRequirementUpdate,
    RegulatoryReviewDecision,
    RegulatoryReviewDecisionCreate,
    RegulatoryRiskAssessment,
    RegulatoryRiskAssessmentRequest,
    RegulatorySourceDocument,
    RegulatorySourceSearchRequest,
    RegulatorySourceSearchResult,
)
from .orm import (
    AuditEventORM,
    ManagedFileRecordORM,
    ProjectORM,
    ReactionProjectORM,
    RegulatoryAnswerORM,
    RegulatoryCitationORM,
    RegulatoryDossierORM,
    RegulatoryEvidenceLinkORM,
    RegulatoryJurisdictionORM,
    RegulatoryQueryORM,
    RegulatoryReadinessReportORM,
    RegulatoryRequirementORM,
    RegulatoryReviewDecisionORM,
    RegulatoryRiskAssessmentORM,
    RegulatorySourceDocumentORM,
    SpectraCheckSessionORM,
    utcnow,
)


class RegulatoryError(ValueError):
    pass


@dataclass(frozen=True)
class RegulatoryActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


_SAFE_NOTE = (
    "Regulatory intelligence outputs are decision-support drafts. They require review and "
    "are not binding regulatory conclusions."
)
_SOURCE_SUPPORTED_NOTE = (
    "Answers must be source-supported. If relevant citations are not available, the answer "
    "is labeled insufficient_sources."
)
_MAX_EXCERPT_CHARS = 60_000
_ANSWER_QUOTE_CHARS = 240


def create_jurisdiction(
    session_factory: sessionmaker[Session],
    payload: RegulatoryJurisdictionCreate,
    *,
    actor: RegulatoryActor,
) -> RegulatoryJurisdiction:
    with session_scope(session_factory) as session:
        row = RegulatoryJurisdictionORM(
            name=payload.name,
            region=payload.region,
            country_code=payload.country_code,
            authority_name=payload.authority_name,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise RegulatoryError(f"Regulatory jurisdiction already exists: {payload.name}") from exc
        _audit(
            session,
            actor=actor,
            event_type="regulatory.jurisdiction.create",
            message="Regulatory jurisdiction created.",
            entity_type="regulatory_jurisdiction",
            entity_id=row.id,
            metadata={"name": row.name, "status": row.status},
        )
        return _jurisdiction_to_record(row)


def list_jurisdictions(
    session_factory: sessionmaker[Session],
    *,
    include_inactive: bool = False,
) -> list[RegulatoryJurisdiction]:
    with session_scope(session_factory) as session:
        stmt = select(RegulatoryJurisdictionORM).order_by(RegulatoryJurisdictionORM.name.asc())
        if not include_inactive:
            stmt = stmt.where(RegulatoryJurisdictionORM.status == "active")
        return [_jurisdiction_to_record(row) for row in session.scalars(stmt).all()]


def upload_source_document(
    session_factory: sessionmaker[Session],
    *,
    title: str,
    source_type: str,
    jurisdiction_id: int | None,
    source_url: str | None,
    source_date: str | datetime | None,
    retrieved_at: str | datetime | None,
    version: str | None,
    file_id: int | None,
    filename: str,
    content_type: str | None,
    content: bytes,
    status: str = "active",
    metadata_json: dict[str, Any] | None = None,
    actor: RegulatoryActor,
) -> RegulatorySourceDocument:
    if not content:
        raise RegulatoryError("Uploaded regulatory source file cannot be empty.")
    sha256 = hashlib.sha256(content).hexdigest()
    text, warnings = _extract_source_text(filename, content_type, content)
    excerpt = _sanitize_excerpt(text)
    with session_scope(session_factory) as session:
        _jurisdiction_or_raise(session, jurisdiction_id)
        _file_or_raise(session, file_id)
        row = RegulatorySourceDocumentORM(
            title=title,
            source_type=source_type,
            jurisdiction_id=jurisdiction_id,
            source_url=source_url,
            source_date=_parse_datetime(source_date),
            retrieved_at=_parse_datetime(retrieved_at) or utcnow(),
            version=version,
            file_id=file_id,
            sha256=sha256,
            text_excerpt=excerpt,
            status=status,
            metadata_json=_json_dump(
                {
                    **(metadata_json or {}),
                    "filename": filename,
                    "content_type": content_type,
                    "parse_warnings": warnings,
                    "stored_text_excerpt_chars": len(excerpt or ""),
                }
            ),
        )
        session.add(row)
        session.flush()
        citations = _create_citations(session, row, excerpt)
        if not citations and not warnings:
            warnings.append("No citation-sized text excerpts could be extracted from this source.")
        _audit(
            session,
            actor=actor,
            event_type="regulatory.source.upload",
            message="Regulatory source document registered with hash and draft citations.",
            entity_type="regulatory_source_document",
            entity_id=row.id,
            metadata={
                "jurisdiction_id": jurisdiction_id,
                "sha256": sha256,
                "citation_count": len(citations),
                "warning_count": len(warnings),
            },
        )
        return _source_to_record(row, citations=citations, warnings=warnings)


def list_sources(
    session_factory: sessionmaker[Session],
    *,
    jurisdiction_id: int | None = None,
    limit: int = 200,
) -> list[RegulatorySourceDocument]:
    with session_scope(session_factory) as session:
        stmt = (
            select(RegulatorySourceDocumentORM)
            .order_by(RegulatorySourceDocumentORM.id.desc())
            .limit(limit)
        )
        if jurisdiction_id is not None:
            stmt = stmt.where(RegulatorySourceDocumentORM.jurisdiction_id == jurisdiction_id)
        return [
            _source_to_record(row, citations=_citations_for_source(session, row.id))
            for row in session.scalars(stmt).all()
        ]


def get_source(
    session_factory: sessionmaker[Session],
    source_id: int,
) -> RegulatorySourceDocument | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatorySourceDocumentORM, source_id)
        if row is None:
            return None
        return _source_to_record(row, citations=_citations_for_source(session, row.id))


def list_source_citations(
    session_factory: sessionmaker[Session],
    source_id: int,
) -> list[RegulatoryCitation]:
    with session_scope(session_factory) as session:
        _source_or_raise(session, source_id)
        return [_citation_to_record(row) for row in _citations_for_source(session, source_id)]


def search_sources(
    session_factory: sessionmaker[Session],
    payload: RegulatorySourceSearchRequest,
) -> RegulatorySourceSearchResult:
    with session_scope(session_factory) as session:
        _jurisdiction_or_raise(session, payload.jurisdiction_id)
        sources, citations = _search_source_rows(
            session,
            payload.query,
            jurisdiction_id=payload.jurisdiction_id,
            source_type=payload.source_type,
            limit=payload.limit,
        )
        warnings: list[str] = []
        if not citations:
            warnings.append("No source-supported citations matched the search query.")
        return RegulatorySourceSearchResult(
            query=payload.query,
            sources=[_source_to_record(row, citations=_citations_for_source(session, row.id)) for row in sources],
            citations=[_citation_to_record(row) for row in citations],
            warnings=warnings,
            notes=[_SAFE_NOTE, _SOURCE_SUPPORTED_NOTE],
            human_review_required=True,
        )


def create_dossier(
    session_factory: sessionmaker[Session],
    payload: RegulatoryDossierCreate,
    *,
    actor: RegulatoryActor,
) -> RegulatoryDossier:
    with session_scope(session_factory) as session:
        _validate_dossier_links(session, payload, actor=actor)
        row = RegulatoryDossierORM(
            created_by_user_id=actor.user_id,  # owner; NULL for a system api key
            project_id=payload.project_id,
            sample_id=payload.sample_id,
            spectracheck_session_id=payload.spectracheck_session_id,
            reaction_project_id=payload.reaction_project_id,
            title=payload.title,
            product_name=payload.product_name,
            compound_name=payload.compound_name,
            jurisdiction_id=payload.jurisdiction_id,
            intended_use=payload.intended_use,
            max_daily_dose_g=payload.max_daily_dose_g,
            substance_type=payload.substance_type,
            route=payload.route,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.dossier.create",
            message="Regulatory dossier created for human-reviewed decision support.",
            entity_type="regulatory_dossier",
            entity_id=row.id,
            metadata={"status": row.status, "jurisdiction_id": row.jurisdiction_id},
        )
        return _dossier_to_record(row)


def list_dossiers(
    session_factory: sessionmaker[Session],
    *,
    owner_scope_id: int | None = None,
    limit: int = 200,
) -> list[RegulatoryDossier]:
    """List dossiers, scoped to ``owner_scope_id`` when set.

    ``owner_scope_id is None`` (a system api key or admin) lists every dossier; a
    user-scoped caller sees only the dossiers they own. NULL-owner rows (system-created
    or un-backfilled legacy) are therefore invisible to a user-scoped caller.
    """
    with session_scope(session_factory) as session:
        stmt = select(RegulatoryDossierORM)
        if owner_scope_id is not None:
            stmt = stmt.where(RegulatoryDossierORM.created_by_user_id == owner_scope_id)
        rows = session.scalars(
            stmt.order_by(RegulatoryDossierORM.id.desc()).limit(limit)
        ).all()
        return [_dossier_to_record(row) for row in rows]


def get_dossier(
    session_factory: sessionmaker[Session],
    dossier_id: int,
) -> RegulatoryDossier | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryDossierORM, dossier_id)
        return _dossier_to_record(row) if row is not None else None


def dossier_owned_by(
    session: Session, dossier_id: int | None, owner_scope_id: int | None
) -> bool:
    """In-session check: may a caller scoped to ``owner_scope_id`` access dossier ``dossier_id``?

    ``owner_scope_id is None`` (a system api key or admin) may access any dossier; a
    user-scoped caller may access only a dossier they own (``created_by_user_id ==
    owner_scope_id``). A missing dossier, an unowned one, and ``dossier_id is None`` are all
    indistinguishable (``False``) so cross-tenant existence is never leaked. This is the single
    source of truth for dossier access — :func:`can_read_dossier` (the route dependency) and the
    by-child-id read/write gates all funnel through it. Use this variant when you already hold a
    session (e.g. gating a write to a dossier child).
    """
    if owner_scope_id is None:
        return True
    if dossier_id is None:
        return False
    row = session.get(RegulatoryDossierORM, dossier_id)
    return row is not None and row.created_by_user_id == owner_scope_id


def can_read_dossier(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    *,
    owner_scope_id: int | None,
) -> bool:
    """Whether a caller scoped to ``owner_scope_id`` may access this dossier (its own id)."""
    with session_scope(session_factory) as session:
        return dossier_owned_by(session, dossier_id, owner_scope_id)


def patch_dossier(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: RegulatoryDossierUpdate,
    *,
    actor: RegulatoryActor,
) -> RegulatoryDossier | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryDossierORM, dossier_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        candidate = payload.model_copy(update={})
        _validate_dossier_links(session, candidate, existing=row, actor=actor)
        for field in (
            "project_id",
            "sample_id",
            "spectracheck_session_id",
            "reaction_project_id",
            "title",
            "product_name",
            "compound_name",
            "jurisdiction_id",
            "intended_use",
            "max_daily_dose_g",
            "substance_type",
            "route",
            "status",
        ):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(update["metadata_json"] or {})
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.dossier.update",
            message="Regulatory dossier updated.",
            entity_type="regulatory_dossier",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _dossier_to_record(row)


def create_requirement(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: RegulatoryRequirementCreate,
    *,
    actor: RegulatoryActor,
) -> RegulatoryRequirement:
    with session_scope(session_factory) as session:
        _dossier_or_raise(session, dossier_id)
        _validate_citation_ids(session, payload.citation_ids_json)
        _validate_evidence_link_ids(session, dossier_id, payload.evidence_link_ids_json)
        row = RegulatoryRequirementORM(
            dossier_id=dossier_id,
            title=payload.title,
            category=payload.category,
            requirement_text=payload.requirement_text,
            priority=payload.priority,
            status=payload.status,
            citation_ids_json=_json_dump(payload.citation_ids_json),
            evidence_link_ids_json=_json_dump(payload.evidence_link_ids_json),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.requirement.create",
            message="Regulatory dossier requirement created.",
            entity_type="regulatory_requirement",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "priority": row.priority, "status": row.status},
        )
        return _requirement_to_record(row)


def list_requirements(
    session_factory: sessionmaker[Session],
    dossier_id: int,
) -> list[RegulatoryRequirement]:
    with session_scope(session_factory) as session:
        _dossier_or_raise(session, dossier_id)
        rows = session.scalars(
            select(RegulatoryRequirementORM)
            .where(RegulatoryRequirementORM.dossier_id == dossier_id)
            .order_by(RegulatoryRequirementORM.id.asc())
        ).all()
        return [_requirement_to_record(row) for row in rows]


def patch_requirement(
    session_factory: sessionmaker[Session],
    requirement_id: int,
    payload: RegulatoryRequirementUpdate,
    *,
    actor: RegulatoryActor,
    owner_scope_id: int | None = None,
) -> RegulatoryRequirement | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryRequirementORM, requirement_id)
        # A requirement is a dossier child; a user-scoped caller may patch it only if they own
        # the parent dossier. Missing and unowned both return None -> non-leaking 404.
        if row is None or not dossier_owned_by(session, row.dossier_id, owner_scope_id):
            return None
        update = payload.model_dump(exclude_unset=True)
        if "citation_ids_json" in update:
            _validate_citation_ids(session, update["citation_ids_json"] or [])
            row.citation_ids_json = _json_dump(update["citation_ids_json"] or [])
        if "evidence_link_ids_json" in update:
            _validate_evidence_link_ids(session, row.dossier_id, update["evidence_link_ids_json"] or [])
            row.evidence_link_ids_json = _json_dump(update["evidence_link_ids_json"] or [])
        for field in ("title", "category", "requirement_text", "priority", "status"):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(update["metadata_json"] or {})
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.requirement.update",
            message="Regulatory dossier requirement updated.",
            entity_type="regulatory_requirement",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _requirement_to_record(row)


def create_evidence_link(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: RegulatoryEvidenceLinkCreate,
    *,
    actor: RegulatoryActor,
) -> RegulatoryEvidenceLink:
    with session_scope(session_factory) as session:
        _dossier_or_raise(session, dossier_id)
        requirement = _requirement_for_dossier(session, dossier_id, payload.requirement_id)
        row = RegulatoryEvidenceLinkORM(
            dossier_id=dossier_id,
            requirement_id=payload.requirement_id,
            evidence_type=payload.evidence_type,
            resource_id=payload.resource_id,
            title=payload.title,
            summary=payload.summary,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        if requirement is not None:
            ids = _json_int_list(requirement.evidence_link_ids_json)
            if row.id not in ids:
                ids.append(row.id)
                requirement.evidence_link_ids_json = _json_dump(ids)
                requirement.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.evidence_link.create",
            message="Regulatory evidence link created.",
            entity_type="regulatory_evidence_link",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "requirement_id": payload.requirement_id},
        )
        return _evidence_link_to_record(row)


def list_evidence_links(
    session_factory: sessionmaker[Session],
    dossier_id: int,
) -> list[RegulatoryEvidenceLink]:
    with session_scope(session_factory) as session:
        _dossier_or_raise(session, dossier_id)
        rows = session.scalars(
            select(RegulatoryEvidenceLinkORM)
            .where(RegulatoryEvidenceLinkORM.dossier_id == dossier_id)
            .order_by(RegulatoryEvidenceLinkORM.id.asc())
        ).all()
        return [_evidence_link_to_record(row) for row in rows]


def answer_query(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: RegulatoryQueryCreate,
    *,
    actor: RegulatoryActor,
) -> RegulatoryQuery:
    with session_scope(session_factory) as session:
        dossier = _dossier_or_raise(session, dossier_id)
        jurisdiction_id = payload.jurisdiction_id if payload.jurisdiction_id is not None else dossier.jurisdiction_id
        _jurisdiction_or_raise(session, jurisdiction_id)
        query = RegulatoryQueryORM(
            dossier_id=dossier_id,
            question=payload.question,
            jurisdiction_id=jurisdiction_id,
            status="queued",
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(query)
        session.flush()
        sources, citations = _search_source_rows(
            session,
            payload.question,
            jurisdiction_id=jurisdiction_id,
            limit=5,
        )
        if not citations:
            answer = RegulatoryAnswerORM(
                query_id=query.id,
                answer_text=(
                    "Insufficient sources: no relevant source-supported citation was found for this "
                    "jurisdiction-specific question. This draft interpretation requires review and "
                    "additional source documents."
                ),
                confidence_label="insufficient_sources",
                citation_ids_json="[]",
                missing_sources_json=_json_dump(
                    [
                        {
                            "question": payload.question,
                            "reason": "No relevant active citation was found.",
                            "jurisdiction_id": jurisdiction_id,
                        }
                    ]
                ),
                warnings_json=_json_dump(
                    ["No regulatory conclusion was generated because no relevant citations were available."]
                ),
                notes_json=_json_dump([_SAFE_NOTE, _SOURCE_SUPPORTED_NOTE]),
                human_review_required=True,
                metadata_json=_json_dump({"source_count": len(sources)}),
            )
            query.status = "insufficient_sources"
        else:
            selected = citations[:3]
            citation_ids = [row.id for row in selected]
            snippets = [_citation_snippet(row) for row in selected]
            answer_text = (
                "Source-supported draft interpretation requires review: "
                + " ".join(snippets)
                + " These citations support a cautious, jurisdiction-specific review path; they do "
                "not establish a binding regulatory conclusion."
            )
            answer = RegulatoryAnswerORM(
                query_id=query.id,
                answer_text=answer_text,
                confidence_label="medium" if len(selected) >= 2 else "low",
                citation_ids_json=_json_dump(citation_ids),
                missing_sources_json="[]",
                warnings_json=_json_dump(
                    ["Regulatory answer is limited to retrieved source excerpts and requires review."]
                ),
                notes_json=_json_dump([_SAFE_NOTE, _SOURCE_SUPPORTED_NOTE]),
                human_review_required=True,
                metadata_json=_json_dump({"source_count": len(sources), "citation_labels": [c.citation_label for c in selected]}),
            )
            query.status = "answered"
        session.add(answer)
        session.flush()
        query.answer_id = answer.id
        _audit(
            session,
            actor=actor,
            event_type="regulatory.query.answer",
            message="Regulatory query answered with citation constraints.",
            entity_type="regulatory_query",
            entity_id=query.id,
            metadata={"dossier_id": dossier_id, "status": query.status, "answer_id": answer.id},
        )
        return _query_to_record(query, answer=answer, answer_citations=citations[:3] if citations else [])


def get_query(
    session_factory: sessionmaker[Session],
    query_id: int,
) -> RegulatoryQuery | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryQueryORM, query_id)
        if row is None:
            return None
        answer = session.get(RegulatoryAnswerORM, row.answer_id) if row.answer_id is not None else None
        answer_citations = _answer_citations(session, answer) if answer is not None else []
        return _query_to_record(row, answer=answer, answer_citations=answer_citations)


def create_risk_assessment(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: RegulatoryRiskAssessmentRequest,
    *,
    actor: RegulatoryActor,
) -> RegulatoryRiskAssessment:
    with session_scope(session_factory) as session:
        _dossier_or_raise(session, dossier_id)
        requirements = _requirements_for_dossier(session, dossier_id)
        evidence_links = _evidence_for_dossier(session, dossier_id)
        risk_payload = _build_risk_payload(requirements, evidence_links)
        row = RegulatoryRiskAssessmentORM(
            dossier_id=dossier_id,
            overall_risk=risk_payload["overall_risk"],
            risk_factors_json=_json_dump(risk_payload["risk_factors"]),
            missing_evidence_json=_json_dump(risk_payload["missing_evidence"]),
            contradictions_json=_json_dump(risk_payload["contradictions"]),
            recommended_actions_json=_json_dump(risk_payload["recommended_actions"]),
            citation_ids_json=_json_dump(risk_payload["citation_ids"]),
            human_review_required=True,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.risk_assessment.create",
            message="Regulatory dossier risk assessment created.",
            entity_type="regulatory_risk_assessment",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "overall_risk": row.overall_risk},
        )
        return _risk_to_record(row)


def get_latest_risk_assessment(
    session_factory: sessionmaker[Session],
    dossier_id: int,
) -> RegulatoryRiskAssessment | None:
    with session_scope(session_factory) as session:
        _dossier_or_raise(session, dossier_id)
        row = session.scalar(
            select(RegulatoryRiskAssessmentORM)
            .where(RegulatoryRiskAssessmentORM.dossier_id == dossier_id)
            .order_by(RegulatoryRiskAssessmentORM.id.desc())
        )
        return _risk_to_record(row) if row is not None else None


def create_review_decision(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: RegulatoryReviewDecisionCreate,
    *,
    actor: RegulatoryActor,
) -> RegulatoryReviewDecision:
    with session_scope(session_factory) as session:
        dossier = _dossier_or_raise(session, dossier_id)
        row = RegulatoryReviewDecisionORM(
            dossier_id=dossier_id,
            reviewer_name=payload.reviewer_name or actor.email,
            decision=payload.decision,
            rationale=payload.rationale,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        if payload.decision == "approve":
            dossier.status = "approved"
        elif payload.decision in {"needs_changes", "defer"}:
            dossier.status = "in_review"
        elif payload.decision == "reject":
            dossier.status = "blocked"
        dossier.updated_at = utcnow()
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.review.create",
            message="Regulatory dossier review decision recorded.",
            entity_type="regulatory_review_decision",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "decision": row.decision},
        )
        return _review_to_record(row)


def list_review_decisions(
    session_factory: sessionmaker[Session],
    dossier_id: int,
) -> list[RegulatoryReviewDecision]:
    with session_scope(session_factory) as session:
        _dossier_or_raise(session, dossier_id)
        rows = session.scalars(
            select(RegulatoryReviewDecisionORM)
            .where(RegulatoryReviewDecisionORM.dossier_id == dossier_id)
            .order_by(RegulatoryReviewDecisionORM.id.desc())
        ).all()
        return [_review_to_record(row) for row in rows]


def create_readiness_report(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: RegulatoryReadinessReportRequest,
    *,
    actor: RegulatoryActor,
) -> RegulatoryReadinessReport:
    with session_scope(session_factory) as session:
        dossier = _dossier_or_raise(session, dossier_id)
        requirements = _requirements_for_dossier(session, dossier_id)
        evidence_links = _evidence_for_dossier(session, dossier_id)
        reviews = session.scalars(
            select(RegulatoryReviewDecisionORM)
            .where(RegulatoryReviewDecisionORM.dossier_id == dossier_id)
            .order_by(RegulatoryReviewDecisionORM.id.desc())
        ).all()
        latest_risk = session.scalar(
            select(RegulatoryRiskAssessmentORM)
            .where(RegulatoryRiskAssessmentORM.dossier_id == dossier_id)
            .order_by(RegulatoryRiskAssessmentORM.id.desc())
        )
        risk_payload = (
            {
                "overall_risk": latest_risk.overall_risk,
                "risk_factors": _json_list(latest_risk.risk_factors_json),
                "missing_evidence": _json_list(latest_risk.missing_evidence_json),
                "contradictions": _json_list(latest_risk.contradictions_json),
                "recommended_actions": _json_list(latest_risk.recommended_actions_json),
            }
            if latest_risk is not None
            else _build_risk_payload(requirements, evidence_links)
        )
        gaps = list(risk_payload.get("missing_evidence", []))
        citation_ids = sorted({cid for req in requirements for cid in _json_int_list(req.citation_ids_json)})
        warnings: list[str] = []
        if gaps:
            warnings.append("Readiness report includes evidence gaps that require review.")
        if not citation_ids:
            warnings.append("Readiness report has no source citations attached to requirements.")
        status = "blocked" if risk_payload.get("overall_risk") in {"critical", "high"} and gaps else "requires_review"
        if not gaps and requirements:
            status = "ready_for_review"
        row = RegulatoryReadinessReportORM(
            dossier_id=dossier_id,
            status=status,
            summary_json=_json_dump(
                {
                    "dossier_title": dossier.title,
                    "jurisdiction_id": dossier.jurisdiction_id,
                    "requirement_count": len(requirements),
                    "evidence_link_count": len(evidence_links),
                    "gap_count": len(gaps),
                    "review_count": len(reviews),
                    "source_supported": bool(citation_ids),
                }
            ),
            requirements_json=_json_dump([_requirement_summary(row) for row in requirements]),
            evidence_json=_json_dump([_evidence_summary(row) for row in evidence_links]),
            gaps_json=_json_dump(gaps),
            risks_json=_json_dump(risk_payload),
            citation_ids_json=_json_dump(citation_ids),
            review_status_json=_json_dump(
                {
                    "latest_decision": reviews[0].decision if reviews else None,
                    "latest_reviewer": reviews[0].reviewer_name if reviews else None,
                    "dossier_status": dossier.status,
                }
            ),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_SAFE_NOTE, "Readiness report is a draft interpretation and requires review."]),
            human_review_required=True,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.readiness_report.create",
            message="Regulatory readiness report created.",
            entity_type="regulatory_readiness_report",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "status": row.status, "gap_count": len(gaps)},
        )
        return _readiness_report_to_record(row)


def get_readiness_report(
    session_factory: sessionmaker[Session],
    report_id: int,
) -> RegulatoryReadinessReport | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryReadinessReportORM, report_id)
        return _readiness_report_to_record(row) if row is not None else None


def _extract_source_text(filename: str, content_type: str | None, content: bytes) -> tuple[str, list[str]]:
    lower = filename.lower()
    warnings: list[str] = []
    if lower.endswith((".txt", ".md", ".csv", ".tsv")) or (content_type or "").startswith("text/"):
        return _decode_text(content), warnings
    if lower.endswith(".docx") or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                xml_bytes = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml_bytes)
            text = " ".join(node.text or "" for node in root.iter() if node.text)
            return re.sub(r"\s+", " ", text).strip(), warnings
        except Exception as exc:  # pragma: no cover - dependency-free fallback path
            warnings.append(f"DOCX text extraction failed; source was registered with hash only: {exc}")
            return "", warnings
    if lower.endswith(".pdf") or content_type == "application/pdf":
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(BytesIO(content))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip(), warnings
        except Exception as exc:  # pragma: no cover - optional parser availability
            warnings.append(f"PDF text extraction is not available or failed; source was registered with hash only: {exc}")
            return "", warnings
    warnings.append("Source file type is not currently parsed; source was registered with hash only.")
    return "", warnings


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _sanitize_excerpt(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return None
    return normalized[:_MAX_EXCERPT_CHARS]


def _create_citations(
    session: Session,
    source: RegulatorySourceDocumentORM,
    excerpt: str | None,
) -> list[RegulatoryCitationORM]:
    if not excerpt:
        return []
    chunks = _citation_chunks(excerpt)
    rows: list[RegulatoryCitationORM] = []
    for index, chunk in enumerate(chunks[:8], start=1):
        row = RegulatoryCitationORM(
            source_id=source.id,
            citation_label=f"SRC-{source.id}-P{index}",
            section_title=source.title,
            paragraph_number=index,
            quote_excerpt=_truncate(chunk, 800),
            summary=_truncate(chunk, 320),
            metadata_json=_json_dump({"generated_from_source_upload": True}),
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def _citation_chunks(text: str) -> list[str]:
    paragraphs = [item.strip() for item in re.split(r"(?:\n\s*\n|(?<=\.)\s{2,})", text) if item.strip()]
    if len(paragraphs) <= 1:
        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]
        paragraphs = []
        buffer: list[str] = []
        for sentence in sentences:
            buffer.append(sentence)
            if sum(len(item) for item in buffer) >= 260:
                paragraphs.append(" ".join(buffer))
                buffer = []
        if buffer:
            paragraphs.append(" ".join(buffer))
    return [item for item in paragraphs if len(item) >= 20] or ([text] if text else [])


def _search_source_rows(
    session: Session,
    query: str,
    *,
    jurisdiction_id: int | None = None,
    source_type: str | None = None,
    limit: int = 10,
) -> tuple[list[RegulatorySourceDocumentORM], list[RegulatoryCitationORM]]:
    tokens = _query_tokens(query)
    stmt = select(RegulatorySourceDocumentORM).where(RegulatorySourceDocumentORM.status == "active")
    if jurisdiction_id is not None:
        stmt = stmt.where(
            (RegulatorySourceDocumentORM.jurisdiction_id == jurisdiction_id)
            | (RegulatorySourceDocumentORM.jurisdiction_id.is_(None))
        )
    if source_type is not None:
        stmt = stmt.where(RegulatorySourceDocumentORM.source_type == source_type)
    source_rows = session.scalars(stmt.order_by(RegulatorySourceDocumentORM.id.desc())).all()
    scored_sources: list[tuple[int, RegulatorySourceDocumentORM]] = []
    scored_citations: list[tuple[int, RegulatoryCitationORM]] = []
    for source in source_rows:
        text = " ".join([source.title or "", source.text_excerpt or ""]).lower()
        source_score = _score_text(tokens, text)
        citations = _citations_for_source(session, source.id)
        citation_best = 0
        for citation in citations:
            citation_text = " ".join(
                [
                    citation.citation_label or "",
                    citation.section_title or "",
                    citation.quote_excerpt or "",
                    citation.summary or "",
                ]
            ).lower()
            score = _score_text(tokens, citation_text)
            if score:
                scored_citations.append((score, citation))
                citation_best = max(citation_best, score)
        score = max(source_score, citation_best)
        if score:
            scored_sources.append((score, source))
    scored_sources.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    scored_citations.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    return [row for _, row in scored_sources[:limit]], [row for _, row in scored_citations[:limit]]


def _query_tokens(query: str) -> list[str]:
    stop = {
        "the",
        "and",
        "or",
        "for",
        "with",
        "this",
        "that",
        "does",
        "what",
        "when",
        "where",
        "require",
        "requires",
        "required",
        "regulatory",
        "dossier",
    }
    return [
        token
        for token in re.findall(r"[a-zA-Z0-9_%-]{3,}", query.lower())
        if token not in stop
    ]


def _score_text(tokens: list[str], text: str) -> int:
    if not tokens:
        return 0
    return sum(1 for token in tokens if token in text)


def _citation_snippet(row: RegulatoryCitationORM) -> str:
    excerpt = _truncate(row.quote_excerpt or row.summary or "", _ANSWER_QUOTE_CHARS)
    return f"[{row.citation_label}] {excerpt}"


def _build_risk_payload(
    requirements: list[RegulatoryRequirementORM],
    evidence_links: list[RegulatoryEvidenceLinkORM],
) -> dict[str, Any]:
    evidence_by_requirement: dict[int, list[RegulatoryEvidenceLinkORM]] = {}
    for evidence in evidence_links:
        if evidence.requirement_id is not None:
            evidence_by_requirement.setdefault(evidence.requirement_id, []).append(evidence)
    risk_factors: list[dict[str, Any]] = []
    missing_evidence: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []
    recommended_actions: list[dict[str, Any]] = []
    citation_ids: set[int] = set()
    for requirement in requirements:
        citation_ids.update(_json_int_list(requirement.citation_ids_json))
        linked = evidence_by_requirement.get(requirement.id, [])
        accepted = [item for item in linked if item.status in {"linked", "accepted"}]
        rejected = [item for item in linked if item.status == "rejected"]
        if requirement.status in {"blocked", "evidence_needed"}:
            risk_factors.append(
                {
                    "requirement_id": requirement.id,
                    "title": requirement.title,
                    "priority": requirement.priority,
                    "status": requirement.status,
                    "potential_concern": "Requirement is blocked or needs evidence.",
                }
            )
        if requirement.status not in {"satisfied", "not_applicable"} and not accepted:
            missing_evidence.append(
                {
                    "requirement_id": requirement.id,
                    "title": requirement.title,
                    "priority": requirement.priority,
                    "evidence_gap": "No accepted or linked evidence is attached.",
                }
            )
            recommended_actions.append(
                {
                    "requirement_id": requirement.id,
                    "suggested_action": "Attach source-supported evidence or mark the requirement not applicable with rationale.",
                }
            )
        if rejected:
            contradictions.append(
                {
                    "requirement_id": requirement.id,
                    "title": requirement.title,
                    "rejected_evidence_ids": [item.id for item in rejected],
                    "potential_concern": "Rejected evidence is linked to this requirement.",
                }
            )
    overall = "low"
    if any(item.get("priority") == "critical" for item in missing_evidence) or contradictions:
        overall = "critical"
    elif any(item.get("priority") == "high" for item in missing_evidence) or risk_factors:
        overall = "high"
    elif missing_evidence:
        overall = "medium"
    if not requirements:
        overall = "unknown"
        recommended_actions.append(
            {"suggested_action": "Create jurisdiction-specific requirements before assessing readiness."}
        )
    return {
        "overall_risk": overall,
        "risk_factors": risk_factors,
        "missing_evidence": missing_evidence,
        "contradictions": contradictions,
        "recommended_actions": recommended_actions,
        "citation_ids": sorted(citation_ids),
    }


def _validate_dossier_links(
    session: Session,
    payload: RegulatoryDossierCreate | RegulatoryDossierUpdate,
    *,
    actor: RegulatoryActor,
    existing: RegulatoryDossierORM | None = None,
) -> None:
    values = payload.model_dump(exclude_unset=True)
    project_id = values.get("project_id", existing.project_id if existing is not None else None)
    spectracheck_session_id = values.get(
        "spectracheck_session_id",
        existing.spectracheck_session_id if existing is not None else None,
    )
    reaction_project_id = values.get(
        "reaction_project_id",
        existing.reaction_project_id if existing is not None else None,
    )
    jurisdiction_id = values.get("jurisdiction_id", existing.jurisdiction_id if existing is not None else None)
    if project_id is not None:
        project = session.get(ProjectORM, project_id)
        if project is None:
            raise KeyError("Project not found.")
        # Projects are user-owned. When the caller assigns/changes the project link in this
        # request, it must be a project they own — a system api key (internal/admin ops) may
        # reference any project. The same "not found" message is raised whether the project is
        # absent or owned by another user, so cross-tenant existence is never leaked. Ownership
        # is only re-checked when project_id is set this request, not for an inherited link.
        if (
            "project_id" in values
            and not actor.system_api_key
            and project.user_id != actor.user_id
        ):
            raise KeyError("Project not found.")
    if spectracheck_session_id is not None and session.get(SpectraCheckSessionORM, spectracheck_session_id) is None:
        raise KeyError("SpectraCheck session not found.")
    if reaction_project_id is not None and session.get(ReactionProjectORM, reaction_project_id) is None:
        raise KeyError("Reaction project not found.")
    _jurisdiction_or_raise(session, jurisdiction_id)


def _jurisdiction_or_raise(session: Session, jurisdiction_id: int | None) -> RegulatoryJurisdictionORM | None:
    if jurisdiction_id is None:
        return None
    row = session.get(RegulatoryJurisdictionORM, jurisdiction_id)
    if row is None:
        raise KeyError("Regulatory jurisdiction not found.")
    return row


def _file_or_raise(session: Session, file_id: int | None) -> ManagedFileRecordORM | None:
    if file_id is None:
        return None
    row = session.get(ManagedFileRecordORM, file_id)
    if row is None:
        raise KeyError("Managed file not found.")
    return row


def _source_or_raise(session: Session, source_id: int) -> RegulatorySourceDocumentORM:
    row = session.get(RegulatorySourceDocumentORM, source_id)
    if row is None:
        raise KeyError("Regulatory source document not found.")
    return row


def _dossier_or_raise(session: Session, dossier_id: int) -> RegulatoryDossierORM:
    row = session.get(RegulatoryDossierORM, dossier_id)
    if row is None:
        raise KeyError("Regulatory dossier not found.")
    return row


def _requirement_for_dossier(
    session: Session,
    dossier_id: int,
    requirement_id: int | None,
) -> RegulatoryRequirementORM | None:
    if requirement_id is None:
        return None
    row = session.get(RegulatoryRequirementORM, requirement_id)
    if row is None or row.dossier_id != dossier_id:
        raise KeyError("Regulatory requirement not found.")
    return row


def _validate_citation_ids(session: Session, citation_ids: list[int]) -> None:
    for citation_id in citation_ids:
        if session.get(RegulatoryCitationORM, citation_id) is None:
            raise KeyError("Regulatory citation not found.")


def _validate_evidence_link_ids(session: Session, dossier_id: int, evidence_ids: list[int]) -> None:
    for evidence_id in evidence_ids:
        row = session.get(RegulatoryEvidenceLinkORM, evidence_id)
        if row is None or row.dossier_id != dossier_id:
            raise KeyError("Regulatory evidence link not found.")


def _requirements_for_dossier(session: Session, dossier_id: int) -> list[RegulatoryRequirementORM]:
    return session.scalars(
        select(RegulatoryRequirementORM)
        .where(RegulatoryRequirementORM.dossier_id == dossier_id)
        .order_by(RegulatoryRequirementORM.id.asc())
    ).all()


def _evidence_for_dossier(session: Session, dossier_id: int) -> list[RegulatoryEvidenceLinkORM]:
    return session.scalars(
        select(RegulatoryEvidenceLinkORM)
        .where(RegulatoryEvidenceLinkORM.dossier_id == dossier_id)
        .order_by(RegulatoryEvidenceLinkORM.id.asc())
    ).all()


def _citations_for_source(session: Session, source_id: int) -> list[RegulatoryCitationORM]:
    return session.scalars(
        select(RegulatoryCitationORM)
        .where(RegulatoryCitationORM.source_id == source_id)
        .order_by(RegulatoryCitationORM.id.asc())
    ).all()


def _answer_citations(
    session: Session,
    answer: RegulatoryAnswerORM,
) -> list[RegulatoryCitationORM]:
    ids = _json_int_list(answer.citation_ids_json)
    if not ids:
        return []
    rows = session.scalars(select(RegulatoryCitationORM).where(RegulatoryCitationORM.id.in_(ids))).all()
    by_id = {row.id: row for row in rows}
    return [by_id[citation_id] for citation_id in ids if citation_id in by_id]


def _jurisdiction_to_record(row: RegulatoryJurisdictionORM) -> RegulatoryJurisdiction:
    return RegulatoryJurisdiction(
        id=row.id,
        name=row.name,
        region=row.region,
        country_code=row.country_code,
        authority_name=row.authority_name,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _source_to_record(
    row: RegulatorySourceDocumentORM,
    *,
    citations: list[RegulatoryCitationORM] | None = None,
    warnings: list[str] | None = None,
) -> RegulatorySourceDocument:
    metadata = _json_dict(row.metadata_json)
    warnings_list = list(warnings or metadata.get("parse_warnings") or [])
    return RegulatorySourceDocument(
        id=row.id,
        title=row.title,
        source_type=row.source_type,  # type: ignore[arg-type]
        jurisdiction_id=row.jurisdiction_id,
        source_url=row.source_url,
        source_date=row.source_date,
        retrieved_at=row.retrieved_at,
        version=row.version,
        file_id=row.file_id,
        sha256=row.sha256,
        text_excerpt=row.text_excerpt,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=metadata,
        citations=[_citation_to_record(item) for item in (citations or [])],
        warnings=[str(item) for item in warnings_list],
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _citation_to_record(row: RegulatoryCitationORM) -> RegulatoryCitation:
    return RegulatoryCitation(
        id=row.id,
        source_id=row.source_id,
        citation_label=row.citation_label,
        section_title=row.section_title,
        page_number=row.page_number,
        paragraph_number=row.paragraph_number,
        quote_excerpt=row.quote_excerpt,
        summary=row.summary,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _dossier_to_record(row: RegulatoryDossierORM) -> RegulatoryDossier:
    return RegulatoryDossier(
        id=row.id,
        project_id=row.project_id,
        sample_id=row.sample_id,
        spectracheck_session_id=row.spectracheck_session_id,
        reaction_project_id=row.reaction_project_id,
        title=row.title,
        product_name=row.product_name,
        compound_name=row.compound_name,
        jurisdiction_id=row.jurisdiction_id,
        intended_use=row.intended_use,
        max_daily_dose_g=row.max_daily_dose_g,
        substance_type=row.substance_type,  # type: ignore[arg-type]
        route=row.route,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _requirement_to_record(row: RegulatoryRequirementORM) -> RegulatoryRequirement:
    return RegulatoryRequirement(
        id=row.id,
        dossier_id=row.dossier_id,
        title=row.title,
        category=row.category,  # type: ignore[arg-type]
        requirement_text=row.requirement_text,
        priority=row.priority,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        citation_ids_json=_json_int_list(row.citation_ids_json),
        evidence_link_ids_json=_json_int_list(row.evidence_link_ids_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _evidence_link_to_record(row: RegulatoryEvidenceLinkORM) -> RegulatoryEvidenceLink:
    return RegulatoryEvidenceLink(
        id=row.id,
        dossier_id=row.dossier_id,
        requirement_id=row.requirement_id,
        evidence_type=row.evidence_type,  # type: ignore[arg-type]
        resource_id=row.resource_id,
        title=row.title,
        summary=row.summary,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _query_to_record(
    row: RegulatoryQueryORM,
    *,
    answer: RegulatoryAnswerORM | None = None,
    answer_citations: list[RegulatoryCitationORM] | None = None,
) -> RegulatoryQuery:
    return RegulatoryQuery(
        id=row.id,
        dossier_id=row.dossier_id,
        question=row.question,
        jurisdiction_id=row.jurisdiction_id,
        status=row.status,  # type: ignore[arg-type]
        answer_id=row.answer_id,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        answer=_answer_to_record(answer, citations=answer_citations or []) if answer is not None else None,
        notes=[_SAFE_NOTE],
        human_review_required=True,
    )


def _answer_to_record(
    row: RegulatoryAnswerORM,
    *,
    citations: list[RegulatoryCitationORM] | None = None,
) -> RegulatoryAnswer:
    citation_ids = _json_int_list(row.citation_ids_json)
    warnings = [str(item) for item in _json_list(row.warnings_json)]
    notes = [str(item) for item in _json_list(row.notes_json)] or [_SAFE_NOTE]
    return RegulatoryAnswer(
        id=row.id,
        query_id=row.query_id,
        answer_text=row.answer_text,
        confidence_label=row.confidence_label,  # type: ignore[arg-type]
        citation_ids_json=citation_ids,
        missing_sources_json=[item for item in _json_list(row.missing_sources_json) if isinstance(item, dict)],
        warnings_json=warnings,
        notes_json=notes,
        human_review_required=row.human_review_required,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        citations=[_citation_to_record(item) for item in (citations or [])],
        warnings=warnings,
        notes=notes,
    )


def _risk_to_record(row: RegulatoryRiskAssessmentORM) -> RegulatoryRiskAssessment:
    return RegulatoryRiskAssessment(
        id=row.id,
        dossier_id=row.dossier_id,
        overall_risk=row.overall_risk,  # type: ignore[arg-type]
        risk_factors_json=[item for item in _json_list(row.risk_factors_json) if isinstance(item, dict)],
        missing_evidence_json=[item for item in _json_list(row.missing_evidence_json) if isinstance(item, dict)],
        contradictions_json=[item for item in _json_list(row.contradictions_json) if isinstance(item, dict)],
        recommended_actions_json=[item for item in _json_list(row.recommended_actions_json) if isinstance(item, dict)],
        citation_ids_json=_json_int_list(row.citation_ids_json),
        human_review_required=row.human_review_required,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_SAFE_NOTE],
    )


def _review_to_record(row: RegulatoryReviewDecisionORM) -> RegulatoryReviewDecision:
    return RegulatoryReviewDecision(
        id=row.id,
        dossier_id=row.dossier_id,
        reviewer_name=row.reviewer_name,
        decision=row.decision,  # type: ignore[arg-type]
        rationale=row.rationale,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _readiness_report_to_record(row: RegulatoryReadinessReportORM) -> RegulatoryReadinessReport:
    warnings = [str(item) for item in _json_list(row.warnings_json)]
    notes = [str(item) for item in _json_list(row.notes_json)] or [_SAFE_NOTE]
    return RegulatoryReadinessReport(
        id=row.id,
        dossier_id=row.dossier_id,
        status=row.status,  # type: ignore[arg-type]
        summary_json=_json_dict(row.summary_json),
        requirements_json=[item for item in _json_list(row.requirements_json) if isinstance(item, dict)],
        evidence_json=[item for item in _json_list(row.evidence_json) if isinstance(item, dict)],
        gaps_json=[item for item in _json_list(row.gaps_json) if isinstance(item, dict)],
        risks_json=_json_dict(row.risks_json),
        citation_ids_json=_json_int_list(row.citation_ids_json),
        review_status_json=_json_dict(row.review_status_json),
        warnings_json=warnings,
        notes_json=notes,
        human_review_required=row.human_review_required,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=notes,
    )


def _requirement_summary(row: RegulatoryRequirementORM) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "category": row.category,
        "priority": row.priority,
        "status": row.status,
        "citation_ids": _json_int_list(row.citation_ids_json),
        "evidence_link_ids": _json_int_list(row.evidence_link_ids_json),
    }


def _evidence_summary(row: RegulatoryEvidenceLinkORM) -> dict[str, Any]:
    return {
        "id": row.id,
        "requirement_id": row.requirement_id,
        "evidence_type": row.evidence_type,
        "resource_id": row.resource_id,
        "title": row.title,
        "status": row.status,
    }


def _audit(
    session: Session,
    *,
    actor: RegulatoryActor,
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
            metadata_json=_json_dump(metadata or {}),
        )
    )


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise RegulatoryError(f"Invalid datetime value: {text}") from None


def _truncate(value: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _json_dump(value: Any) -> str:
    return json.dumps(
        value if value is not None else {},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
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


def _json_int_list(value: str | None) -> list[int]:
    ids: list[int] = []
    for item in _json_list(value):
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids
