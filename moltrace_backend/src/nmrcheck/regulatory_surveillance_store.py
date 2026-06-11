from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    RegulatoryChangeEvent,
    RegulatoryChangeReviewRequest,
    RegulatoryDossierChangeImpact,
    RegulatoryImpactAssessment,
    RegulatoryImpactAssessmentCreate,
    RegulatoryImpactNotification,
    RegulatoryImpactNotificationUpdate,
    RegulatoryRuleUpdateProposal,
    RegulatoryRuleUpdateProposalCreate,
    RegulatoryRuleUpdateProposalReviewRequest,
    RegulatorySourceVersion,
    RegulatorySourceVersionCompareRequest,
    RegulatorySourceVersionCompareResponse,
    RegulatorySourceWatcher,
    RegulatorySourceWatcherCreate,
    RegulatorySourceWatcherUpdate,
    RegulatorySurveillanceRun,
    RegulatorySurveillanceRunCreate,
)
from .orm import (
    AIGovernanceRecordORM,
    AuditEventORM,
    RegulatoryActionItemORM,
    RegulatoryChangeDiffORM,
    RegulatoryChangeEventORM,
    RegulatoryCitationORM,
    RegulatoryDossierORM,
    RegulatoryImpactAssessmentORM,
    RegulatoryImpactNotificationORM,
    RegulatoryJurisdictionORM,
    RegulatoryRequirementORM,
    RegulatoryRuleSetORM,
    RegulatoryRuleUpdateProposalORM,
    RegulatorySourceDocumentORM,
    RegulatorySourceVersionORM,
    RegulatorySourceWatcherORM,
    RegulatorySurveillanceRunORM,
    utcnow,
)


class RegulatorySurveillanceError(ValueError):
    pass


class RegulatorySurveillanceNotFoundError(RegulatorySurveillanceError):
    pass


@dataclass(frozen=True)
class RegulatorySurveillanceActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


_REVIEW_NOTE = "Source change detected outputs are draft records and require qualified review."
_IMPACT_NOTE = "Draft impact assessment; possible impact only until a qualified reviewer accepts it."
_FETCH_WARNING = (
    "Outbound source retrieval is not enabled for this deployment; submit uploaded_text or an uploaded document version."
)
_MAX_VERSION_EXCERPT = 12_000
_MAX_DIFF_EXCERPT = 1_200
_TOPIC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("impurity_threshold", ("impurity", "threshold", "reporting", "identification", "qualification")),
    ("residual_solvent", ("residual solvent", "solvent", "pde", "permitted daily exposure", "class 1", "class 2", "class 3")),
    ("nitrosamine", ("nitrosamine", "n-nitroso", "n nitroso", "nitroso")),
    ("qnmr", ("qnmr", "quantitative nmr", "internal standard", "analytical target profile")),
    ("method_validation", ("q2", "q14", "validation", "accuracy", "precision", "specificity", "robustness")),
    ("ai_governance", ("ai governance", "model version", "explainability", "human oversight", "workflow version")),
    ("jurisdictional_map", ("jurisdiction", "fda", "ema", "pmda", "health canada", "ich", "usp")),
    ("reporting", ("reporting", "dossier", "submission", "report")),
)


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


def _metadata_with_warning(metadata: dict[str, Any] | None, warning: str | None = None) -> dict[str, Any]:
    output = dict(metadata or {})
    if warning:
        warnings = output.get("warnings")
        merged = list(warnings) if isinstance(warnings, list) else []
        if warning not in merged:
            merged.append(warning)
        output["warnings"] = merged
    output.setdefault("human_review_required", True)
    return output


def _warnings_from_metadata(value: str | None) -> list[str]:
    metadata = _json_dict(value)
    warnings = metadata.get("warnings", [])
    return [str(item) for item in warnings] if isinstance(warnings, list) else []


def _audit(
    session: Session,
    *,
    actor: RegulatorySurveillanceActor,
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


def create_watcher(
    session_factory: sessionmaker[Session],
    payload: RegulatorySourceWatcherCreate,
    *,
    actor: RegulatorySurveillanceActor,
) -> RegulatorySourceWatcher:
    with session_scope(session_factory) as session:
        if payload.source_id is not None:
            _require_source(session, payload.source_id)
        _require_jurisdiction(session, payload.jurisdiction_id)
        row = RegulatorySourceWatcherORM(
            source_id=payload.source_id,
            title=payload.title,
            source_type=payload.source_type,
            jurisdiction_id=payload.jurisdiction_id,
            source_url=payload.source_url,
            check_frequency=payload.check_frequency,
            status=payload.status,
            metadata_json=_json_dump(_metadata_with_warning(payload.metadata_json)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.surveillance.watcher.create",
            message="Regulatory source watcher created; checks require qualified review.",
            entity_type="regulatory_source_watcher",
            entity_id=row.id,
            metadata={"source_id": row.source_id, "check_frequency": row.check_frequency},
        )
        return _watcher_to_record(row)


def list_watchers(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    jurisdiction_id: int | None = None,
    limit: int = 200,
) -> list[RegulatorySourceWatcher]:
    with session_scope(session_factory) as session:
        stmt = select(RegulatorySourceWatcherORM).order_by(RegulatorySourceWatcherORM.id.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(RegulatorySourceWatcherORM.status == status)
        if jurisdiction_id is not None:
            stmt = stmt.where(RegulatorySourceWatcherORM.jurisdiction_id == jurisdiction_id)
        return [_watcher_to_record(row) for row in session.scalars(stmt).all()]


def get_watcher(session_factory: sessionmaker[Session], watcher_id: int) -> RegulatorySourceWatcher | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatorySourceWatcherORM, watcher_id)
        return _watcher_to_record(row) if row is not None else None


def update_watcher(
    session_factory: sessionmaker[Session],
    watcher_id: int,
    payload: RegulatorySourceWatcherUpdate,
    *,
    actor: RegulatorySurveillanceActor,
) -> RegulatorySourceWatcher | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatorySourceWatcherORM, watcher_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        if "source_id" in update:
            if update["source_id"] is not None:
                _require_source(session, update["source_id"])
            row.source_id = update["source_id"]
        if "jurisdiction_id" in update:
            _require_jurisdiction(session, update["jurisdiction_id"])
            row.jurisdiction_id = update["jurisdiction_id"]
        for field in ("title", "source_type", "source_url", "check_frequency", "status"):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update:
            row.metadata_json = _json_dump(_metadata_with_warning(update["metadata_json"]))
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.surveillance.watcher.update",
            message="Regulatory source watcher updated.",
            entity_type="regulatory_source_watcher",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update)},
        )
        return _watcher_to_record(row)


def create_surveillance_run(
    session_factory: sessionmaker[Session],
    payload: RegulatorySurveillanceRunCreate,
    *,
    actor: RegulatorySurveillanceActor,
) -> RegulatorySurveillanceRun:
    with session_scope(session_factory) as session:
        watcher = _require_watcher(session, payload.watcher_id) if payload.watcher_id is not None else None
        source = _resolve_or_create_source(session, watcher, payload)
        warnings: list[str] = []
        if watcher is not None and watcher.status != "active":
            warnings.append(f"Watcher status is {watcher.status}; manual run was recorded for review.")
        text = payload.uploaded_text
        if not text:
            warnings.append(_FETCH_WARNING if (watcher and watcher.source_url) or source.source_url else "No uploaded source text was supplied.")
            now = utcnow()
            if watcher is not None:
                watcher.last_checked_at = now
                watcher.updated_at = now
            run = RegulatorySurveillanceRunORM(
                watcher_id=watcher.id if watcher else None,
                source_id=source.id,
                run_type=payload.run_type,
                status="warning",
                started_at=now,
                completed_at=now,
                warnings_json=_json_dump(warnings),
                notes_json=_json_dump([_REVIEW_NOTE]),
                metadata_json=_json_dump(_metadata_with_warning(payload.metadata_json)),
            )
            session.add(run)
            session.flush()
            _audit(
                session,
                actor=actor,
                event_type="regulatory.surveillance.run.warning",
                message="Regulatory surveillance run recorded without outbound retrieval.",
                entity_type="regulatory_surveillance_run",
                entity_id=run.id,
                metadata={"source_id": source.id, "warning_count": len(warnings)},
            )
            return _run_to_record(run)

        now = utcnow()
        old_version = _current_version(session, source.id)
        excerpt = _sanitize_excerpt(text)
        sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        normalized_hash = hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()
        version = RegulatorySourceVersionORM(
            source_id=source.id,
            watcher_id=watcher.id if watcher else None,
            version_label=payload.version_label,
            source_date=payload.source_date,
            retrieved_at=now,
            file_id=payload.file_id,
            sha256=sha256,
            content_hash=sha256,
            normalized_text_hash=normalized_hash,
            text_excerpt=excerpt,
            status="current",
            metadata_json=_json_dump(
                _metadata_with_warning(
                    {
                        **payload.metadata_json,
                        "raw_text_not_stored": True,
                        "uploaded_text_chars": len(text),
                    }
                )
            ),
        )
        session.add(version)
        session.flush()
        compare = _compare_version_rows(old_version, version)
        if compare["change_type"] == "no_change":
            version.status = "archived"
        elif old_version is not None:
            old_version.status = "superseded"
        source.retrieved_at = now
        source.version = payload.version_label or source.version
        source.sha256 = sha256
        source.text_excerpt = excerpt
        source.status = "active"
        source.updated_at = now
        if watcher is not None:
            watcher.source_id = source.id
            watcher.last_checked_at = now
            if compare["change_type"] != "no_change":
                watcher.last_change_detected_at = now
            watcher.updated_at = now
        event = _create_change_event(
            session,
            source=source,
            old_version=old_version,
            new_version=version,
            compare=compare,
            actor=actor,
        )
        run = RegulatorySurveillanceRunORM(
            watcher_id=watcher.id if watcher else None,
            source_id=source.id,
            run_type=payload.run_type,
            status="no_change" if compare["change_type"] == "no_change" else "completed",
            started_at=now,
            completed_at=now,
            created_version_id=version.id,
            change_event_id=event.id,
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_REVIEW_NOTE]),
            metadata_json=_json_dump(_metadata_with_warning(payload.metadata_json)),
        )
        session.add(run)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.surveillance.run.create",
            message="Regulatory surveillance run completed with version comparison.",
            entity_type="regulatory_surveillance_run",
            entity_id=run.id,
            metadata={"source_id": source.id, "version_id": version.id, "change_event_id": event.id},
        )
        return _run_to_record(run)


def list_runs(
    session_factory: sessionmaker[Session],
    *,
    watcher_id: int | None = None,
    source_id: int | None = None,
    limit: int = 200,
) -> list[RegulatorySurveillanceRun]:
    with session_scope(session_factory) as session:
        stmt = select(RegulatorySurveillanceRunORM).order_by(RegulatorySurveillanceRunORM.id.desc()).limit(limit)
        if watcher_id is not None:
            stmt = stmt.where(RegulatorySurveillanceRunORM.watcher_id == watcher_id)
        if source_id is not None:
            stmt = stmt.where(RegulatorySurveillanceRunORM.source_id == source_id)
        return [_run_to_record(row) for row in session.scalars(stmt).all()]


def get_run(session_factory: sessionmaker[Session], run_id: int) -> RegulatorySurveillanceRun | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatorySurveillanceRunORM, run_id)
        return _run_to_record(row) if row is not None else None


def list_source_versions(session_factory: sessionmaker[Session], source_id: int) -> list[RegulatorySourceVersion]:
    with session_scope(session_factory) as session:
        _require_source(session, source_id)
        rows = session.scalars(
            select(RegulatorySourceVersionORM)
            .where(RegulatorySourceVersionORM.source_id == source_id)
            .order_by(RegulatorySourceVersionORM.id.asc())
        ).all()
        return [_version_to_record(row) for row in rows]


def get_source_version(
    session_factory: sessionmaker[Session],
    source_id: int,
    version_id: int,
) -> RegulatorySourceVersion | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatorySourceVersionORM, version_id)
        if row is None or row.source_id != source_id:
            return None
        return _version_to_record(row)


def compare_source_versions(
    session_factory: sessionmaker[Session],
    source_id: int,
    payload: RegulatorySourceVersionCompareRequest,
) -> RegulatorySourceVersionCompareResponse:
    with session_scope(session_factory) as session:
        old = _require_version(session, payload.old_version_id)
        new = _require_version(session, payload.new_version_id)
        if old.source_id != source_id or new.source_id != source_id:
            raise RegulatorySurveillanceError("Both versions must belong to the requested regulatory source.")
        compare = _compare_version_rows(old, new)
        return RegulatorySourceVersionCompareResponse(
            source_id=source_id,
            old_version_id=old.id,
            new_version_id=new.id,
            changed=compare["change_type"] != "no_change",
            change_type=compare["change_type"],
            diff_summary=compare["diff_summary"],
            before_excerpt=compare["before_excerpt"],
            after_excerpt=compare["after_excerpt"],
            affected_topics_json=compare["topics"],
            old_normalized_text_hash=old.normalized_text_hash,
            new_normalized_text_hash=new.normalized_text_hash,
            warnings=[],
            notes=[_REVIEW_NOTE],
            human_review_required=True,
        )


def list_changes(
    session_factory: sessionmaker[Session],
    *,
    source_id: int | None = None,
    review_status: str | None = None,
    limit: int = 200,
) -> list[RegulatoryChangeEvent]:
    with session_scope(session_factory) as session:
        stmt = select(RegulatoryChangeEventORM).order_by(RegulatoryChangeEventORM.id.desc()).limit(limit)
        if source_id is not None:
            stmt = stmt.where(RegulatoryChangeEventORM.source_id == source_id)
        if review_status is not None:
            stmt = stmt.where(RegulatoryChangeEventORM.review_status == review_status)
        return [_event_to_record(session, row) for row in session.scalars(stmt).all()]


def get_change(session_factory: sessionmaker[Session], change_id: int) -> RegulatoryChangeEvent | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryChangeEventORM, change_id)
        return _event_to_record(session, row) if row is not None else None


def review_change(
    session_factory: sessionmaker[Session],
    change_id: int,
    payload: RegulatoryChangeReviewRequest,
    *,
    actor: RegulatorySurveillanceActor,
) -> RegulatoryChangeEvent | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryChangeEventORM, change_id)
        if row is None:
            return None
        metadata = _json_dict(row.metadata_json)
        metadata["reviewer_name"] = payload.reviewer_name or actor.email
        metadata["reviewer_comment"] = payload.reviewer_comment
        metadata["review_metadata"] = payload.metadata_json
        row.review_status = payload.review_status
        row.metadata_json = _json_dump(metadata)
        _audit(
            session,
            actor=actor,
            event_type="regulatory.change.review",
            message="Regulatory source change review status updated.",
            entity_type="regulatory_change_event",
            entity_id=row.id,
            metadata={"review_status": row.review_status},
        )
        return _event_to_record(session, row)


def create_impact_assessment(
    session_factory: sessionmaker[Session],
    change_id: int,
    payload: RegulatoryImpactAssessmentCreate,
    *,
    actor: RegulatorySurveillanceActor,
) -> RegulatoryImpactAssessment:
    with session_scope(session_factory) as session:
        event = _require_change(session, change_id)
        source = _require_source(session, event.source_id)
        topics = [str(item) for item in _json_list(event.affected_topics_json)]
        impact = _map_impacts(session, source, topics)
        event_action_ids = _json_int_list(_json_dump(_json_dict(event.metadata_json).get("review_action_item_ids", [])))
        action_ids = sorted(set(impact["action_item_ids"]) | set(event_action_ids))
        warnings = ["draft impact assessment requires qualified review."]
        if not _citation_ids_for_source(session, source.id):
            warnings.append("No citation records are linked to this source; source-supported review may require citations.")
        row = RegulatoryImpactAssessmentORM(
            change_event_id=event.id,
            status=payload.status or "draft",
            impacted_dossiers_json=_json_dump(impact["dossier_ids"]),
            impacted_requirements_json=_json_dump(impact["requirement_ids"]),
            impacted_action_items_json=_json_dump(action_ids),
            impacted_rule_sets_json=_json_dump(impact["rule_set_ids"]),
            impacted_ai_governance_records_json=_json_dump(impact["ai_governance_record_ids"]),
            recommended_actions_json=_json_dump(_recommended_actions(event, impact)),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_IMPACT_NOTE, *payload.notes_json]),
            human_review_required=True,
            metadata_json=_json_dump(_metadata_with_warning(payload.metadata_json)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.impact_assessment.create",
            message="Draft impact assessment created for regulatory source change.",
            entity_type="regulatory_impact_assessment",
            entity_id=row.id,
            metadata={"change_event_id": event.id, "dossier_count": len(impact["dossier_ids"])},
        )
        return _impact_to_record(row)


def list_impact_assessments(session_factory: sessionmaker[Session], change_id: int) -> list[RegulatoryImpactAssessment]:
    with session_scope(session_factory) as session:
        _require_change(session, change_id)
        rows = session.scalars(
            select(RegulatoryImpactAssessmentORM)
            .where(RegulatoryImpactAssessmentORM.change_event_id == change_id)
            .order_by(RegulatoryImpactAssessmentORM.id.desc())
        ).all()
        return [_impact_to_record(row) for row in rows]


def create_rule_update_proposal(
    session_factory: sessionmaker[Session],
    change_id: int,
    payload: RegulatoryRuleUpdateProposalCreate,
    *,
    actor: RegulatorySurveillanceActor,
) -> RegulatoryRuleUpdateProposal:
    with session_scope(session_factory) as session:
        _require_change(session, change_id)
        if payload.rule_set_id is not None and session.get(RegulatoryRuleSetORM, payload.rule_set_id) is None:
            raise RegulatorySurveillanceNotFoundError("Regulatory rule set not found.")
        _validate_citation_ids(session, payload.citation_ids_json)
        warning = None if payload.citation_ids_json else "source_needed: no citation IDs were supplied for this rule update proposal."
        row = RegulatoryRuleUpdateProposalORM(
            change_event_id=change_id,
            rule_set_id=payload.rule_set_id,
            proposal_type=payload.proposal_type,
            title=payload.title,
            rationale=payload.rationale,
            proposed_changes_json=_json_dump(payload.proposed_changes_json),
            citation_ids_json=_json_dump(payload.citation_ids_json),
            status="proposed",
            metadata_json=_json_dump(_metadata_with_warning(payload.metadata_json, warning)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory.rule_update_proposal.create",
            message="Rule update proposal created; no rule update was applied.",
            entity_type="regulatory_rule_update_proposal",
            entity_id=row.id,
            metadata={"change_event_id": change_id, "proposal_type": row.proposal_type},
        )
        return _proposal_to_record(row)


def list_rule_update_proposals(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    rule_set_id: int | None = None,
    limit: int = 200,
) -> list[RegulatoryRuleUpdateProposal]:
    with session_scope(session_factory) as session:
        stmt = select(RegulatoryRuleUpdateProposalORM).order_by(RegulatoryRuleUpdateProposalORM.id.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(RegulatoryRuleUpdateProposalORM.status == status)
        if rule_set_id is not None:
            stmt = stmt.where(RegulatoryRuleUpdateProposalORM.rule_set_id == rule_set_id)
        return [_proposal_to_record(row) for row in session.scalars(stmt).all()]


def get_rule_update_proposal(
    session_factory: sessionmaker[Session],
    proposal_id: int,
) -> RegulatoryRuleUpdateProposal | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryRuleUpdateProposalORM, proposal_id)
        return _proposal_to_record(row) if row is not None else None


def approve_rule_update_proposal(
    session_factory: sessionmaker[Session],
    proposal_id: int,
    payload: RegulatoryRuleUpdateProposalReviewRequest,
    *,
    actor: RegulatorySurveillanceActor,
) -> RegulatoryRuleUpdateProposal | None:
    return _review_rule_update_proposal(
        session_factory,
        proposal_id,
        payload,
        status="approved",
        actor=actor,
    )


def reject_rule_update_proposal(
    session_factory: sessionmaker[Session],
    proposal_id: int,
    payload: RegulatoryRuleUpdateProposalReviewRequest,
    *,
    actor: RegulatorySurveillanceActor,
) -> RegulatoryRuleUpdateProposal | None:
    return _review_rule_update_proposal(
        session_factory,
        proposal_id,
        payload,
        status="rejected",
        actor=actor,
    )


def get_dossier_change_impact(
    session_factory: sessionmaker[Session],
    dossier_id: int,
) -> RegulatoryDossierChangeImpact:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        changes = [
            row
            for row in session.scalars(select(RegulatoryChangeEventORM).order_by(RegulatoryChangeEventORM.id.desc())).all()
            if dossier_id in _json_int_list(row.affected_dossier_ids_json)
        ]
        change_ids = [row.id for row in changes]
        assessments = (
            session.scalars(
                select(RegulatoryImpactAssessmentORM)
                .where(RegulatoryImpactAssessmentORM.change_event_id.in_(change_ids))
                .order_by(RegulatoryImpactAssessmentORM.id.desc())
            ).all()
            if change_ids
            else []
        )
        proposals = (
            session.scalars(
                select(RegulatoryRuleUpdateProposalORM)
                .where(RegulatoryRuleUpdateProposalORM.change_event_id.in_(change_ids))
                .order_by(RegulatoryRuleUpdateProposalORM.id.desc())
            ).all()
            if change_ids
            else []
        )
        notifications = session.scalars(
            select(RegulatoryImpactNotificationORM)
            .where(RegulatoryImpactNotificationORM.dossier_id == dossier_id)
            .order_by(RegulatoryImpactNotificationORM.id.desc())
        ).all()
        action_ids = [
            row.id
            for row in session.scalars(
                select(RegulatoryActionItemORM)
                .where(RegulatoryActionItemORM.dossier_id == dossier_id)
                .order_by(RegulatoryActionItemORM.id.desc())
            ).all()
            if _json_dict(row.metadata_json).get("change_event_id") in change_ids
        ]
        return RegulatoryDossierChangeImpact(
            dossier_id=dossier_id,
            change_events=[_event_to_record(session, row) for row in changes],
            impact_assessments=[_impact_to_record(row) for row in assessments],
            rule_update_proposals=[_proposal_to_record(row) for row in proposals],
            notifications=[_notification_to_record(row) for row in notifications],
            action_item_ids_json=action_ids,
            warnings=[],
            notes=[_IMPACT_NOTE],
            human_review_required=True,
        )


def list_notifications(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    dossier_id: int | None = None,
    owner_scope_id: int | None = None,
    limit: int = 200,
) -> list[RegulatoryImpactNotification]:
    with session_scope(session_factory) as session:
        stmt = select(RegulatoryImpactNotificationORM).order_by(RegulatoryImpactNotificationORM.id.desc()).limit(limit)
        if owner_scope_id is not None:
            # Restrict to notifications whose dossier the caller owns (system/admin pass
            # None and see all); the inner join also drops dossier-less notifications.
            stmt = stmt.join(
                RegulatoryDossierORM,
                RegulatoryImpactNotificationORM.dossier_id == RegulatoryDossierORM.id,
            ).where(RegulatoryDossierORM.created_by_user_id == owner_scope_id)
        if status is not None:
            stmt = stmt.where(RegulatoryImpactNotificationORM.status == status)
        if dossier_id is not None:
            stmt = stmt.where(RegulatoryImpactNotificationORM.dossier_id == dossier_id)
        return [_notification_to_record(row) for row in session.scalars(stmt).all()]


def update_notification(
    session_factory: sessionmaker[Session],
    notification_id: int,
    payload: RegulatoryImpactNotificationUpdate,
    *,
    actor: RegulatorySurveillanceActor,
) -> RegulatoryImpactNotification | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryImpactNotificationORM, notification_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        if "status" in update and update["status"] is not None:
            row.status = update["status"]
        if "metadata_json" in update:
            row.metadata_json = _json_dump(_metadata_with_warning(update["metadata_json"]))
        _audit(
            session,
            actor=actor,
            event_type="regulatory.notification.update",
            message="Regulatory impact notification updated.",
            entity_type="regulatory_impact_notification",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update), "status": row.status},
        )
        return _notification_to_record(row)


def _review_rule_update_proposal(
    session_factory: sessionmaker[Session],
    proposal_id: int,
    payload: RegulatoryRuleUpdateProposalReviewRequest,
    *,
    status: str,
    actor: RegulatorySurveillanceActor,
) -> RegulatoryRuleUpdateProposal | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryRuleUpdateProposalORM, proposal_id)
        if row is None:
            return None
        row.status = status
        row.reviewer_name = payload.reviewer_name
        row.reviewer_comment = payload.reviewer_comment or payload.rationale
        row.updated_at = utcnow()
        metadata = _json_dict(row.metadata_json)
        metadata["review_metadata"] = payload.metadata_json
        metadata["review_requires_application_step"] = True
        row.metadata_json = _json_dump(metadata)
        _audit(
            session,
            actor=actor,
            event_type=f"regulatory.rule_update_proposal.{status}",
            message="Rule update proposal review recorded; no automatic rule update was applied.",
            entity_type="regulatory_rule_update_proposal",
            entity_id=row.id,
            metadata={"status": status, "reviewer_name": row.reviewer_name},
        )
        return _proposal_to_record(row)


def _resolve_or_create_source(
    session: Session,
    watcher: RegulatorySourceWatcherORM | None,
    payload: RegulatorySurveillanceRunCreate,
) -> RegulatorySourceDocumentORM:
    source_id = payload.source_id or (watcher.source_id if watcher is not None else None)
    if source_id is not None:
        return _require_source(session, source_id)
    if watcher is None:
        raise RegulatorySurveillanceError("watcher_id or source_id is required.")
    now = utcnow()
    source = RegulatorySourceDocumentORM(
        title=watcher.title,
        source_type=_document_source_type(watcher.source_type),
        jurisdiction_id=watcher.jurisdiction_id,
        source_url=watcher.source_url,
        retrieved_at=now,
        version=payload.version_label,
        status="active",
        metadata_json=_json_dump(
            {
                "created_from_surveillance_watcher_id": watcher.id,
                "surveillance_source_type": watcher.source_type,
                "human_review_required": True,
            }
        ),
    )
    session.add(source)
    session.flush()
    watcher.source_id = source.id
    return source


def _create_change_event(
    session: Session,
    *,
    source: RegulatorySourceDocumentORM,
    old_version: RegulatorySourceVersionORM | None,
    new_version: RegulatorySourceVersionORM,
    compare: dict[str, Any],
    actor: RegulatorySurveillanceActor,
) -> RegulatoryChangeEventORM:
    topics = compare["topics"]
    impact = _map_impacts(session, source, topics)
    change_type = compare["change_type"]
    severity = _severity_for_change(change_type, topics)
    title = "No regulatory source change detected" if change_type == "no_change" else "Regulatory source change detected"
    event = RegulatoryChangeEventORM(
        source_id=source.id,
        old_version_id=old_version.id if old_version is not None else None,
        new_version_id=new_version.id,
        change_type=change_type,
        severity=severity,
        title=title,
        summary=compare["diff_summary"],
        affected_topics_json=_json_dump(topics),
        affected_rule_set_ids_json=_json_dump(impact["rule_set_ids"]),
        affected_dossier_ids_json=_json_dump(impact["dossier_ids"]),
        human_review_required=True,
        review_status="unreviewed",
        metadata_json=_json_dump(
            {
                "possible_impact": change_type != "no_change",
                "requires_qualified_review": True,
                "source_id": source.id,
            }
        ),
    )
    session.add(event)
    session.flush()
    diff = RegulatoryChangeDiffORM(
        change_event_id=event.id,
        diff_type="threshold" if change_type == "threshold_changed" else "text",
        before_excerpt=compare["before_excerpt"],
        after_excerpt=compare["after_excerpt"],
        diff_summary=compare["diff_summary"],
        citation_ids_json=_json_dump(_citation_ids_for_source(session, source.id)),
        metadata_json=_json_dump({"normalized_hash_changed": change_type != "no_change"}),
    )
    session.add(diff)
    review_action_ids = _create_review_tasks(session, event, impact)
    _create_notifications(session, event, impact, review_action_ids)
    metadata = _json_dict(event.metadata_json)
    metadata["review_action_item_ids"] = review_action_ids
    event.metadata_json = _json_dump(metadata)
    _audit(
        session,
        actor=actor,
        event_type="regulatory.change.detected",
        message="Regulatory source change event created and marked for qualified review.",
        entity_type="regulatory_change_event",
        entity_id=event.id,
        metadata={"source_id": source.id, "change_type": change_type, "severity": severity},
    )
    return event


def _create_review_tasks(
    session: Session,
    event: RegulatoryChangeEventORM,
    impact: dict[str, list[int]],
) -> list[int]:
    if event.change_type == "no_change":
        return []
    citation_ids = _citation_ids_for_source(session, event.source_id)
    action_ids: list[int] = []
    for dossier_id in impact["dossier_ids"]:
        row = RegulatoryActionItemORM(
            dossier_id=dossier_id,
            action_type="jurisdictional_review",
            title="Review regulatory source change",
            description=(
                "Source change detected with possible impact on this dossier; "
                "requires qualified review before rule or dossier updates."
            ),
            severity="high" if event.severity in {"high", "critical"} else "warning",
            status="open",
            citation_ids_json=_json_dump(citation_ids),
            metadata_json=_json_dump(
                {
                    "change_event_id": event.id,
                    "source_id": event.source_id,
                    "review_task_type": "regulatory_source_change",
                    "human_review_required": True,
                }
            ),
        )
        session.add(row)
        session.flush()
        action_ids.append(row.id)
    return action_ids


def _create_notifications(
    session: Session,
    event: RegulatoryChangeEventORM,
    impact: dict[str, list[int]],
    action_ids: list[int],
) -> None:
    dossier_ids = impact["dossier_ids"] or [None]
    for index, dossier_id in enumerate(dossier_ids):
        action_item_id = action_ids[index] if dossier_id is not None and index < len(action_ids) else None
        session.add(
            RegulatoryImpactNotificationORM(
                change_event_id=event.id,
                dossier_id=dossier_id,
                action_item_id=action_item_id,
                severity=event.severity,
                title=event.title,
                message=(
                    "Source change detected with possible impact; rule update proposal or dossier updates "
                    "require qualified review."
                ),
                status="unread",
                metadata_json=_json_dump({"source_id": event.source_id, "change_type": event.change_type}),
            )
        )


def _map_impacts(
    session: Session,
    source: RegulatorySourceDocumentORM,
    topics: list[str],
) -> dict[str, list[int]]:
    citation_ids = set(_citation_ids_for_source(session, source.id))
    rule_set_ids: set[int] = set()
    for rule_set in session.scalars(select(RegulatoryRuleSetORM)).all():
        source_ids = set(_json_int_list(rule_set.source_ids_json))
        if source.id in source_ids or (
            source.jurisdiction_id is not None and rule_set.jurisdiction_id == source.jurisdiction_id
        ):
            rule_set_ids.add(rule_set.id)
    dossier_ids: set[int] = set()
    if source.jurisdiction_id is not None:
        dossier_ids.update(
            row.id
            for row in session.scalars(
                select(RegulatoryDossierORM).where(RegulatoryDossierORM.jurisdiction_id == source.jurisdiction_id)
            ).all()
        )
    requirement_ids: set[int] = set()
    for requirement in session.scalars(select(RegulatoryRequirementORM)).all():
        if citation_ids.intersection(_json_int_list(requirement.citation_ids_json)):
            requirement_ids.add(requirement.id)
            dossier_ids.add(requirement.dossier_id)
    action_item_ids = {
        row.id
        for row in session.scalars(select(RegulatoryActionItemORM)).all()
        if row.dossier_id in dossier_ids
        or citation_ids.intersection(_json_int_list(row.citation_ids_json))
        or _json_dict(row.metadata_json).get("source_id") == source.id
    }
    ai_governance_ids: set[int] = set()
    if "ai_governance" in topics:
        ai_governance_ids.update(
            row.id
            for row in session.scalars(select(AIGovernanceRecordORM)).all()
            if row.dossier_id in dossier_ids
        )
    return {
        "rule_set_ids": sorted(rule_set_ids),
        "dossier_ids": sorted(dossier_ids),
        "requirement_ids": sorted(requirement_ids),
        "action_item_ids": sorted(action_item_ids),
        "ai_governance_record_ids": sorted(ai_governance_ids),
    }


def _recommended_actions(event: RegulatoryChangeEventORM, impact: dict[str, list[int]]) -> list[dict[str, Any]]:
    topics = [str(item) for item in _json_list(event.affected_topics_json)]
    actions: list[dict[str, Any]] = [
        {
            "action_type": "human_review",
            "title": "Qualified review required",
            "description": "Review source text, citations, impacted dossiers, and existing rule sets before taking action.",
        }
    ]
    if event.change_type in {"threshold_changed", "citation_changed", "text_changed", "new_source"}:
        actions.append(
            {
                "action_type": "rule_update_proposal",
                "title": "Consider a rule update proposal",
                "description": "Create or update rules only after source-supported reviewer acceptance.",
                "affected_rule_set_ids": impact["rule_set_ids"],
            }
        )
    if impact["dossier_ids"]:
        actions.append(
            {
                "action_type": "dossier_review",
                "title": "Review possible dossier impact",
                "description": "Assess impacted dossiers and open action items for review required updates.",
                "affected_dossier_ids": impact["dossier_ids"],
            }
        )
    if "ai_governance" in topics:
        actions.append(
            {
                "action_type": "ai_governance_review",
                "title": "Review AI governance records",
                "description": "Check model version, explainability, validation, and human oversight records.",
            }
        )
    return actions


def _compare_version_rows(
    old: RegulatorySourceVersionORM | None,
    new: RegulatorySourceVersionORM,
) -> dict[str, Any]:
    before_text = old.text_excerpt if old is not None else None
    after_text = new.text_excerpt
    topics = _classify_topics(" ".join([before_text or "", after_text or ""]))
    if old is None:
        change_type = "new_source"
    elif old.normalized_text_hash == new.normalized_text_hash:
        change_type = "no_change"
    elif _threshold_signal_changed(before_text or "", after_text or ""):
        change_type = "threshold_changed"
    elif _citation_signal_changed(before_text or "", after_text or ""):
        change_type = "citation_changed"
    else:
        change_type = "text_changed"
    diff_summary = _diff_summary(change_type, topics, before_text, after_text)
    return {
        "change_type": change_type,
        "topics": topics,
        "diff_summary": diff_summary,
        "before_excerpt": _truncate(before_text, _MAX_DIFF_EXCERPT),
        "after_excerpt": _truncate(after_text, _MAX_DIFF_EXCERPT),
    }


def _diff_summary(
    change_type: str,
    topics: list[str],
    before_text: str | None,
    after_text: str | None,
) -> str:
    topic_text = ", ".join(topics) if topics else "other"
    if change_type == "no_change":
        return f"No normalized source text change detected. Topics checked: {topic_text}. Requires qualified review."
    if change_type == "new_source":
        return f"Source change detected: first version registered. Possible impact topics: {topic_text}. Requires qualified review."
    before_numbers = sorted(set(re.findall(r"\d+(?:\.\d+)?", before_text or "")))
    after_numbers = sorted(set(re.findall(r"\d+(?:\.\d+)?", after_text or "")))
    number_note = ""
    if before_numbers != after_numbers:
        number_note = f" Numeric tokens changed from {before_numbers[:8]} to {after_numbers[:8]}."
    return (
        f"Source change detected: normalized text hash changed with possible impact topics: {topic_text}."
        f"{number_note} Requires qualified review before any rule update proposal is applied."
    )


def _threshold_signal_changed(before_text: str, after_text: str) -> bool:
    combined = f"{before_text} {after_text}".lower()
    if not any(term in combined for term in ("threshold", "limit", "pde", "permitted daily exposure", "reporting", "qualification")):
        return False
    return sorted(set(re.findall(r"\d+(?:\.\d+)?", before_text))) != sorted(set(re.findall(r"\d+(?:\.\d+)?", after_text)))


def _citation_signal_changed(before_text: str, after_text: str) -> bool:
    combined = f"{before_text} {after_text}".lower()
    return "citation" in combined or "section" in combined or "chapter" in combined


def _classify_topics(text: str) -> list[str]:
    normalized = text.lower()
    topics: list[str] = []
    for topic, terms in _TOPIC_PATTERNS:
        if any(term in normalized for term in terms):
            topics.append(topic)
    return topics or ["other"]


def _severity_for_change(change_type: str, topics: list[str]) -> str:
    if change_type in {"no_change"}:
        return "info"
    if change_type in {"parse_error", "deprecated"}:
        return "critical"
    if "nitrosamine" in topics or change_type == "threshold_changed":
        return "high"
    return "warning"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _sanitize_excerpt(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip()[:_MAX_VERSION_EXCERPT]


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _document_source_type(source_type: str) -> str:
    if source_type == "internal_sop":
        return "internal_sop"
    if source_type == "company_policy":
        return "company_policy"
    if source_type in {"fda_guidance", "ema_guideline", "ich_guideline", "usp_chapter", "pmda_guidance", "health_canada_guidance"}:
        return "guidance"
    return "other"


def _current_version(session: Session, source_id: int) -> RegulatorySourceVersionORM | None:
    return session.scalar(
        select(RegulatorySourceVersionORM)
        .where(
            RegulatorySourceVersionORM.source_id == source_id,
            RegulatorySourceVersionORM.status == "current",
        )
        .order_by(RegulatorySourceVersionORM.id.desc())
    )


def _citation_ids_for_source(session: Session, source_id: int) -> list[int]:
    return [
        row.id
        for row in session.scalars(
            select(RegulatoryCitationORM).where(RegulatoryCitationORM.source_id == source_id)
        ).all()
    ]


def _validate_citation_ids(session: Session, citation_ids: list[int]) -> None:
    for citation_id in citation_ids:
        if session.get(RegulatoryCitationORM, citation_id) is None:
            raise RegulatorySurveillanceNotFoundError("Regulatory citation not found.")


def _require_jurisdiction(session: Session, jurisdiction_id: int | None) -> None:
    if jurisdiction_id is not None and session.get(RegulatoryJurisdictionORM, jurisdiction_id) is None:
        raise RegulatorySurveillanceNotFoundError("Regulatory jurisdiction not found.")


def _require_source(session: Session, source_id: int | None) -> RegulatorySourceDocumentORM:
    if source_id is None:
        raise RegulatorySurveillanceNotFoundError("Regulatory source document not found.")
    row = session.get(RegulatorySourceDocumentORM, source_id)
    if row is None:
        raise RegulatorySurveillanceNotFoundError("Regulatory source document not found.")
    return row


def _require_watcher(session: Session, watcher_id: int | None) -> RegulatorySourceWatcherORM:
    if watcher_id is None:
        raise RegulatorySurveillanceNotFoundError("Regulatory source watcher not found.")
    row = session.get(RegulatorySourceWatcherORM, watcher_id)
    if row is None:
        raise RegulatorySurveillanceNotFoundError("Regulatory source watcher not found.")
    return row


def _require_version(session: Session, version_id: int) -> RegulatorySourceVersionORM:
    row = session.get(RegulatorySourceVersionORM, version_id)
    if row is None:
        raise RegulatorySurveillanceNotFoundError("Regulatory source version not found.")
    return row


def _require_change(session: Session, change_id: int) -> RegulatoryChangeEventORM:
    row = session.get(RegulatoryChangeEventORM, change_id)
    if row is None:
        raise RegulatorySurveillanceNotFoundError("Regulatory change event not found.")
    return row


def _require_dossier(session: Session, dossier_id: int) -> RegulatoryDossierORM:
    row = session.get(RegulatoryDossierORM, dossier_id)
    if row is None:
        raise RegulatorySurveillanceNotFoundError("Regulatory dossier not found.")
    return row


def _watcher_to_record(row: RegulatorySourceWatcherORM) -> RegulatorySourceWatcher:
    warnings = _warnings_from_metadata(row.metadata_json)
    notes = [_REVIEW_NOTE]
    if row.source_url:
        notes.append("Use manual uploaded document versions unless outbound retrieval is explicitly enabled.")
    return RegulatorySourceWatcher(
        id=row.id,
        source_id=row.source_id,
        title=row.title,
        source_type=row.source_type,
        jurisdiction_id=row.jurisdiction_id,
        source_url=row.source_url,
        check_frequency=row.check_frequency,
        status=row.status,
        last_checked_at=row.last_checked_at,
        last_change_detected_at=row.last_change_detected_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=notes,
        human_review_required=True,
    )


def _version_to_record(row: RegulatorySourceVersionORM) -> RegulatorySourceVersion:
    return RegulatorySourceVersion(
        id=row.id,
        source_id=row.source_id,
        watcher_id=row.watcher_id,
        version_label=row.version_label,
        source_date=row.source_date,
        retrieved_at=row.retrieved_at,
        file_id=row.file_id,
        sha256=row.sha256,
        content_hash=row.content_hash,
        normalized_text_hash=row.normalized_text_hash,
        text_excerpt=row.text_excerpt,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=_warnings_from_metadata(row.metadata_json),
        notes=[_REVIEW_NOTE],
        human_review_required=True,
    )


def _run_to_record(row: RegulatorySurveillanceRunORM) -> RegulatorySurveillanceRun:
    return RegulatorySurveillanceRun(
        id=row.id,
        watcher_id=row.watcher_id,
        source_id=row.source_id,
        run_type=row.run_type,
        status=row.status,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_version_id=row.created_version_id,
        change_event_id=row.change_event_id,
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _diff_to_record(row: RegulatoryChangeDiffORM) -> Any:
    from .models import RegulatoryChangeDiff

    return RegulatoryChangeDiff(
        id=row.id,
        change_event_id=row.change_event_id,
        diff_type=row.diff_type,
        before_excerpt=row.before_excerpt,
        after_excerpt=row.after_excerpt,
        diff_summary=row.diff_summary,
        citation_ids_json=_json_int_list(row.citation_ids_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )


def _event_to_record(session: Session, row: RegulatoryChangeEventORM) -> RegulatoryChangeEvent:
    diffs = session.scalars(
        select(RegulatoryChangeDiffORM)
        .where(RegulatoryChangeDiffORM.change_event_id == row.id)
        .order_by(RegulatoryChangeDiffORM.id.asc())
    ).all()
    return RegulatoryChangeEvent(
        id=row.id,
        source_id=row.source_id,
        old_version_id=row.old_version_id,
        new_version_id=row.new_version_id,
        change_type=row.change_type,
        severity=row.severity,
        title=row.title,
        summary=row.summary,
        affected_topics_json=[str(item) for item in _json_list(row.affected_topics_json)],
        affected_rule_set_ids_json=_json_int_list(row.affected_rule_set_ids_json),
        affected_dossier_ids_json=_json_int_list(row.affected_dossier_ids_json),
        human_review_required=True,
        review_status=row.review_status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        diffs=[_diff_to_record(diff) for diff in diffs],
        warnings=_warnings_from_metadata(row.metadata_json),
        notes=[_REVIEW_NOTE],
    )


def _impact_to_record(row: RegulatoryImpactAssessmentORM) -> RegulatoryImpactAssessment:
    return RegulatoryImpactAssessment(
        id=row.id,
        change_event_id=row.change_event_id,
        status=row.status,
        impacted_dossiers_json=_json_int_list(row.impacted_dossiers_json),
        impacted_requirements_json=_json_int_list(row.impacted_requirements_json),
        impacted_action_items_json=_json_int_list(row.impacted_action_items_json),
        impacted_rule_sets_json=_json_int_list(row.impacted_rule_sets_json),
        impacted_ai_governance_records_json=_json_int_list(row.impacted_ai_governance_records_json),
        recommended_actions_json=[item for item in _json_list(row.recommended_actions_json) if isinstance(item, dict)],
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        human_review_required=True,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _proposal_to_record(row: RegulatoryRuleUpdateProposalORM) -> RegulatoryRuleUpdateProposal:
    return RegulatoryRuleUpdateProposal(
        id=row.id,
        change_event_id=row.change_event_id,
        rule_set_id=row.rule_set_id,
        proposal_type=row.proposal_type,
        title=row.title,
        rationale=row.rationale,
        proposed_changes_json=_json_dict(row.proposed_changes_json),
        citation_ids_json=_json_int_list(row.citation_ids_json),
        status=row.status,
        reviewer_name=row.reviewer_name,
        reviewer_comment=row.reviewer_comment,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=_warnings_from_metadata(row.metadata_json),
        notes=["Rule update proposal requires qualified review and a separate application step."],
        human_review_required=True,
    )


def _notification_to_record(row: RegulatoryImpactNotificationORM) -> RegulatoryImpactNotification:
    return RegulatoryImpactNotification(
        id=row.id,
        change_event_id=row.change_event_id,
        dossier_id=row.dossier_id,
        action_item_id=row.action_item_id,
        severity=row.severity,
        title=row.title,
        message=row.message,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        human_review_required=True,
    )
