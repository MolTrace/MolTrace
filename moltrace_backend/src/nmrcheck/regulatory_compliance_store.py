from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    AIGovernanceRecord,
    AIGovernanceRecordCreate,
    AnalyticalMethodValidationProfile,
    AnalyticalMethodValidationProfileCreate,
    BatchRegulatoryAssessment,
    BatchRegulatoryAssessmentCreate,
    DossierNitrosamineCumulativeRisk,
    DossierNitrosamineExcludedAssessment,
    DossierNitrosamineRiskComponent,
    ElementalImpurityAssessmentRequest,
    ImpurityRiskRegister,
    ImpurityRiskRegisterCreate,
    ImpurityThresholdRule,
    JurisdictionalRequirementMap,
    JurisdictionalRequirementMapCreate,
    NitrosamineRiskRule,
    NitrosamineWatchRequest,
    QNMRComplianceProfile,
    QNMRComplianceProfileCreate,
    RegulatoryActionItem,
    RegulatoryActionItemCreate,
    RegulatoryActionItemUpdate,
    RegulatoryRuleSet,
    RegulatoryRuleSetCreate,
    ResidualSolventAssessmentRequest,
    ResidualSolventRule,
)
from .orm import (
    AIGovernanceRecordORM,
    AnalyticalMethodValidationProfileORM,
    AuditEventORM,
    BatchRegulatoryAssessmentORM,
    CompoundBatchORM,
    CompoundEntityORM,
    CompoundEvidenceLinkORM,
    ImpurityRiskRegisterORM,
    ImpurityThresholdRuleORM,
    JurisdictionalRequirementMapORM,
    NitrosamineRiskRuleORM,
    QNMRComplianceProfileORM,
    RegulatoryActionItemORM,
    RegulatoryCitationORM,
    RegulatoryDossierORM,
    RegulatoryJurisdictionORM,
    RegulatoryRequirementORM,
    RegulatoryRuleSetORM,
    RegulatorySourceDocumentORM,
    ResidualSolventRuleORM,
    utcnow,
)


class RegulatoryComplianceError(ValueError):
    pass


class RegulatoryComplianceNotFoundError(RegulatoryComplianceError):
    pass


@dataclass(frozen=True)
class RegulatoryComplianceActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


_COMPLIANCE_NOTE = "Draft compliance assessment; qualified human review required."
_SOURCE_NOTE = "Use source-supported rules where available; missing citations create source_needed action items."
_NITROSO_PATTERNS = (
    re.compile(r"N\s*[-=]\s*N\s*O", re.IGNORECASE),
    re.compile(r"N\(\s*N\s*=\s*O\s*\)", re.IGNORECASE),
    re.compile(r"N\s*\(\s*O\s*\)\s*=\s*N", re.IGNORECASE),
    re.compile(r"nitroso|nitrosamine|n-nitroso|n nitroso", re.IGNORECASE),
)
_SOLVENT_ALIASES = {
    "meoh": "methanol",
    "methyl alcohol": "methanol",
    "etoh": "ethanol",
    "ethyl alcohol": "ethanol",
    "ipa": "isopropanol",
    "isopropyl alcohol": "isopropanol",
    "acn": "acetonitrile",
    "dcm": "dichloromethane",
    "methylene chloride": "dichloromethane",
    "thf": "tetrahydrofuran",
}
_TRIGGER_ORDER = {"none": 0, "reporting": 1, "identification": 2, "qualification": 3, "review_required": 4}


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


def _string_list(value: str | None) -> list[str]:
    return [str(item) for item in _json_list(value) if str(item).strip()]


def _audit(
    session: Session,
    *,
    actor: RegulatoryComplianceActor,
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


def _require_dossier(session: Session, dossier_id: int) -> RegulatoryDossierORM:
    row = session.get(RegulatoryDossierORM, dossier_id)
    if row is None:
        raise RegulatoryComplianceNotFoundError("Regulatory dossier not found.")
    return row


def _require_jurisdiction(session: Session, jurisdiction_id: int | None) -> None:
    if jurisdiction_id is not None and session.get(RegulatoryJurisdictionORM, jurisdiction_id) is None:
        raise RegulatoryComplianceNotFoundError("Regulatory jurisdiction not found.")


def _validate_source_ids(session: Session, source_ids: list[int]) -> None:
    for source_id in source_ids:
        if session.get(RegulatorySourceDocumentORM, source_id) is None:
            raise RegulatoryComplianceNotFoundError("Regulatory source document not found.")


def _validate_citation_ids(session: Session, citation_ids: list[int]) -> None:
    for citation_id in citation_ids:
        if session.get(RegulatoryCitationORM, citation_id) is None:
            raise RegulatoryComplianceNotFoundError("Regulatory citation not found.")


def _require_batch(session: Session, batch_id: int | None) -> None:
    if batch_id is not None and session.get(CompoundBatchORM, batch_id) is None:
        raise RegulatoryComplianceNotFoundError("Compound batch not found.")


def _require_compound(session: Session, compound_id: int | None) -> None:
    if compound_id is not None and session.get(CompoundEntityORM, compound_id) is None:
        raise RegulatoryComplianceNotFoundError("Compound not found.")


def _require_evidence_link(session: Session, evidence_link_id: int | None) -> None:
    if evidence_link_id is not None and session.get(CompoundEvidenceLinkORM, evidence_link_id) is None:
        raise RegulatoryComplianceNotFoundError("Compound evidence link not found.")


def _source_warnings(source_ids: list[int], citation_ids: list[int] | None = None, *, source_type: str | None = None) -> list[str]:
    warnings: list[str] = []
    if not source_ids:
        marker = "internal_draft" if source_type == "internal_sop" else "source_needed"
        warnings.append(f"{marker}: no source document IDs were supplied for this regulatory rule.")
    if citation_ids is not None and not citation_ids:
        warnings.append("source_needed: no citation IDs were supplied for this rule or action.")
    return warnings


def _metadata_with_warnings(metadata: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    output = dict(metadata or {})
    if warnings:
        existing = output.get("warnings")
        merged = list(existing) if isinstance(existing, list) else []
        for warning in warnings:
            if warning not in merged:
                merged.append(warning)
        output["warnings"] = merged
    output.setdefault("human_review_required", True)
    return output


def _rule_set_children(session: Session, rule_set_id: int) -> tuple[list[ImpurityThresholdRuleORM], list[ResidualSolventRuleORM], list[NitrosamineRiskRuleORM]]:
    impurity = session.scalars(
        select(ImpurityThresholdRuleORM)
        .where(ImpurityThresholdRuleORM.rule_set_id == rule_set_id)
        .order_by(ImpurityThresholdRuleORM.id.asc())
    ).all()
    solvents = session.scalars(
        select(ResidualSolventRuleORM)
        .where(ResidualSolventRuleORM.rule_set_id == rule_set_id)
        .order_by(ResidualSolventRuleORM.id.asc())
    ).all()
    nitrosamines = session.scalars(
        select(NitrosamineRiskRuleORM)
        .where(NitrosamineRiskRuleORM.rule_set_id == rule_set_id)
        .order_by(NitrosamineRiskRuleORM.id.asc())
    ).all()
    return list(impurity), list(solvents), list(nitrosamines)


def _impurity_rule_to_record(row: ImpurityThresholdRuleORM, *, rule_set_sources: list[int] | None = None) -> ImpurityThresholdRule:
    citation_ids = _json_int_list(row.citation_ids_json)
    return ImpurityThresholdRule(
        id=row.id,
        rule_set_id=row.rule_set_id,
        rule_type=row.rule_type,  # type: ignore[arg-type]
        threshold_percent=row.threshold_percent,
        threshold_amount_mg_per_day=row.threshold_amount_mg_per_day,
        applies_to=row.applies_to,  # type: ignore[arg-type]
        citation_ids_json=citation_ids,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=_source_warnings(rule_set_sources or [], citation_ids),
    )


def _solvent_rule_to_record(row: ResidualSolventRuleORM, *, rule_set_sources: list[int] | None = None) -> ResidualSolventRule:
    citation_ids = _json_int_list(row.citation_ids_json)
    return ResidualSolventRule(
        id=row.id,
        rule_set_id=row.rule_set_id,
        solvent_name=row.solvent_name,
        solvent_class=row.solvent_class,  # type: ignore[arg-type]
        permitted_daily_exposure=row.permitted_daily_exposure,
        concentration_limit=row.concentration_limit,
        citation_ids_json=citation_ids,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=_source_warnings(rule_set_sources or [], citation_ids),
    )


def _nitrosamine_rule_to_record(row: NitrosamineRiskRuleORM, *, rule_set_sources: list[int] | None = None) -> NitrosamineRiskRule:
    citation_ids = _json_int_list(row.citation_ids_json)
    return NitrosamineRiskRule(
        id=row.id,
        rule_set_id=row.rule_set_id,
        risk_category=row.risk_category,  # type: ignore[arg-type]
        structural_pattern=row.structural_pattern,
        acceptable_intake=row.acceptable_intake,
        ai_limit=row.ai_limit,
        citation_ids_json=citation_ids,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=_source_warnings(rule_set_sources or [], citation_ids),
    )


def _rule_set_to_record(session: Session, row: RegulatoryRuleSetORM) -> RegulatoryRuleSet:
    source_ids = _json_int_list(row.source_ids_json)
    impurity, solvents, nitrosamines = _rule_set_children(session, row.id)
    warnings = _source_warnings(source_ids, source_type=row.source_type)
    return RegulatoryRuleSet(
        id=row.id,
        name=row.name,
        jurisdiction_id=row.jurisdiction_id,
        version=row.version,
        source_type=row.source_type,  # type: ignore[arg-type]
        source_ids_json=source_ids,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        impurity_threshold_rules_json=[
            _impurity_rule_to_record(item, rule_set_sources=source_ids) for item in impurity
        ],
        residual_solvent_rules_json=[
            _solvent_rule_to_record(item, rule_set_sources=source_ids) for item in solvents
        ],
        nitrosamine_risk_rules_json=[
            _nitrosamine_rule_to_record(item, rule_set_sources=source_ids) for item in nitrosamines
        ],
        warnings=warnings,
        notes=[_COMPLIANCE_NOTE, _SOURCE_NOTE],
    )


def create_rule_set(
    session_factory: sessionmaker[Session],
    payload: RegulatoryRuleSetCreate,
    *,
    actor: RegulatoryComplianceActor,
) -> RegulatoryRuleSet:
    with session_scope(session_factory) as session:
        _require_jurisdiction(session, payload.jurisdiction_id)
        _validate_source_ids(session, payload.source_ids_json)
        for rule in payload.impurity_threshold_rules_json:
            _validate_citation_ids(session, rule.citation_ids_json)
        for rule in payload.residual_solvent_rules_json:
            _validate_citation_ids(session, rule.citation_ids_json)
        for rule in payload.nitrosamine_risk_rules_json:
            _validate_citation_ids(session, rule.citation_ids_json)
        warnings = _source_warnings(payload.source_ids_json, source_type=payload.source_type)
        metadata = _metadata_with_warnings(payload.metadata_json, warnings)
        if warnings:
            metadata["rule_source_status"] = "internal_draft" if payload.source_type == "internal_sop" else "source_needed"
        row = RegulatoryRuleSetORM(
            name=payload.name,
            jurisdiction_id=payload.jurisdiction_id,
            version=payload.version,
            source_type=payload.source_type,
            source_ids_json=_json_dump(payload.source_ids_json),
            status=payload.status,
            metadata_json=_json_dump(metadata),
        )
        session.add(row)
        session.flush()
        for rule in payload.impurity_threshold_rules_json:
            session.add(
                ImpurityThresholdRuleORM(
                    rule_set_id=row.id,
                    rule_type=rule.rule_type,
                    threshold_percent=rule.threshold_percent,
                    threshold_amount_mg_per_day=rule.threshold_amount_mg_per_day,
                    applies_to=rule.applies_to,
                    citation_ids_json=_json_dump(rule.citation_ids_json),
                    metadata_json=_json_dump(
                        _metadata_with_warnings(
                            rule.metadata_json,
                            _source_warnings(payload.source_ids_json, rule.citation_ids_json),
                        )
                    ),
                )
            )
        for rule in payload.residual_solvent_rules_json:
            session.add(
                ResidualSolventRuleORM(
                    rule_set_id=row.id,
                    solvent_name=rule.solvent_name,
                    solvent_class=rule.solvent_class,
                    permitted_daily_exposure=rule.permitted_daily_exposure,
                    concentration_limit=rule.concentration_limit,
                    citation_ids_json=_json_dump(rule.citation_ids_json),
                    metadata_json=_json_dump(
                        _metadata_with_warnings(
                            rule.metadata_json,
                            _source_warnings(payload.source_ids_json, rule.citation_ids_json),
                        )
                    ),
                )
            )
        for rule in payload.nitrosamine_risk_rules_json:
            session.add(
                NitrosamineRiskRuleORM(
                    rule_set_id=row.id,
                    risk_category=rule.risk_category,
                    structural_pattern=rule.structural_pattern,
                    acceptable_intake=rule.acceptable_intake,
                    ai_limit=rule.ai_limit,
                    citation_ids_json=_json_dump(rule.citation_ids_json),
                    metadata_json=_json_dump(
                        _metadata_with_warnings(
                            rule.metadata_json,
                            _source_warnings(payload.source_ids_json, rule.citation_ids_json),
                        )
                    ),
                )
            )
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.rule_set.create",
            message="Regulatory compliance rule set created for draft compliance assessment.",
            entity_type="regulatory_rule_set",
            entity_id=row.id,
            metadata={"status": row.status, "source_type": row.source_type, "warning_count": len(warnings)},
        )
        return _rule_set_to_record(session, row)


def list_rule_sets(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    jurisdiction_id: int | None = None,
) -> list[RegulatoryRuleSet]:
    with session_scope(session_factory) as session:
        stmt = select(RegulatoryRuleSetORM).order_by(RegulatoryRuleSetORM.id.desc())
        if status is not None:
            stmt = stmt.where(RegulatoryRuleSetORM.status == status)
        if jurisdiction_id is not None:
            stmt = stmt.where(RegulatoryRuleSetORM.jurisdiction_id == jurisdiction_id)
        return [_rule_set_to_record(session, row) for row in session.scalars(stmt).all()]


def get_rule_set(session_factory: sessionmaker[Session], rule_set_id: int) -> RegulatoryRuleSet | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryRuleSetORM, rule_set_id)
        return _rule_set_to_record(session, row) if row is not None else None


def _active_rule_sets(session: Session, dossier: RegulatoryDossierORM) -> list[RegulatoryRuleSetORM]:
    stmt = select(RegulatoryRuleSetORM).where(RegulatoryRuleSetORM.status == "active")
    if dossier.jurisdiction_id is not None:
        stmt = stmt.where(
            or_(
                RegulatoryRuleSetORM.jurisdiction_id.is_(None),
                RegulatoryRuleSetORM.jurisdiction_id == dossier.jurisdiction_id,
            )
        )
    return list(session.scalars(stmt.order_by(RegulatoryRuleSetORM.id.desc())).all())


def _action_to_record(row: RegulatoryActionItemORM) -> RegulatoryActionItem:
    metadata = _json_dict(row.metadata_json)
    warnings = [str(item) for item in metadata.get("warnings", [])] if isinstance(metadata.get("warnings"), list) else []
    return RegulatoryActionItem(
        id=row.id,
        dossier_id=row.dossier_id,
        batch_id=row.batch_id,
        compound_id=row.compound_id,
        evidence_link_id=row.evidence_link_id,
        requirement_id=row.requirement_id,
        action_type=row.action_type,  # type: ignore[arg-type]
        title=row.title,
        description=row.description,
        severity=row.severity,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        due_date=row.due_date,
        assigned_to=row.assigned_to,
        citation_ids_json=_json_int_list(row.citation_ids_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=metadata,
        warnings=warnings,
        notes=[_COMPLIANCE_NOTE],
    )


def _create_action_item_row(
    session: Session,
    *,
    actor: RegulatoryComplianceActor,
    dossier_id: int | None,
    batch_id: int | None = None,
    compound_id: int | None = None,
    evidence_link_id: int | None = None,
    requirement_id: int | None = None,
    action_type: str,
    title: str,
    description: str,
    severity: str = "warning",
    citation_ids: list[int] | None = None,
    metadata: dict[str, Any] | None = None,
) -> RegulatoryActionItemORM:
    citation_ids = citation_ids or []
    warnings = _source_warnings([], citation_ids) if not citation_ids else []
    row = RegulatoryActionItemORM(
        dossier_id=dossier_id,
        batch_id=batch_id,
        compound_id=compound_id,
        evidence_link_id=evidence_link_id,
        requirement_id=requirement_id,
        action_type=action_type,
        title=title,
        description=description,
        severity=severity,
        status="open",
        citation_ids_json=_json_dump(citation_ids),
        metadata_json=_json_dump(_metadata_with_warnings(metadata or {}, warnings)),
    )
    session.add(row)
    session.flush()
    _audit(
        session,
        actor=actor,
        event_type="regulatory_compliance.action_item.create",
        message="Regulatory compliance action item created; qualified human review required.",
        entity_type="regulatory_action_item",
        entity_id=row.id,
        metadata={"action_type": action_type, "severity": severity, "dossier_id": dossier_id},
    )
    return row


def create_action_item(
    session_factory: sessionmaker[Session],
    payload: RegulatoryActionItemCreate,
    *,
    actor: RegulatoryComplianceActor,
) -> RegulatoryActionItem:
    with session_scope(session_factory) as session:
        if payload.dossier_id is not None:
            _require_dossier(session, payload.dossier_id)
        _require_batch(session, payload.batch_id)
        _require_compound(session, payload.compound_id)
        _require_evidence_link(session, payload.evidence_link_id)
        if payload.requirement_id is not None and session.get(RegulatoryRequirementORM, payload.requirement_id) is None:
            raise RegulatoryComplianceNotFoundError("Regulatory requirement not found.")
        _validate_citation_ids(session, payload.citation_ids_json)
        row = RegulatoryActionItemORM(
            dossier_id=payload.dossier_id,
            batch_id=payload.batch_id,
            compound_id=payload.compound_id,
            evidence_link_id=payload.evidence_link_id,
            requirement_id=payload.requirement_id,
            action_type=payload.action_type,
            title=payload.title,
            description=payload.description,
            severity=payload.severity,
            status=payload.status,
            due_date=payload.due_date,
            assigned_to=payload.assigned_to,
            citation_ids_json=_json_dump(payload.citation_ids_json),
            metadata_json=_json_dump(
                _metadata_with_warnings(
                    payload.metadata_json,
                    _source_warnings([], payload.citation_ids_json) if not payload.citation_ids_json else [],
                )
            ),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.action_item.create",
            message="Regulatory compliance action item created.",
            entity_type="regulatory_action_item",
            entity_id=row.id,
            metadata={"action_type": row.action_type, "severity": row.severity},
        )
        return _action_to_record(row)


def list_action_items(
    session_factory: sessionmaker[Session],
    *,
    dossier_id: int | None = None,
    status: str | None = None,
    owner_scope_id: int | None = None,
    limit: int = 200,
) -> list[RegulatoryActionItem]:
    with session_scope(session_factory) as session:
        stmt = select(RegulatoryActionItemORM).order_by(RegulatoryActionItemORM.id.desc()).limit(limit)
        if owner_scope_id is not None:
            # Restrict to action items whose dossier the caller owns (a system api key /
            # admin passes owner_scope_id=None and sees all). The inner join also drops
            # action items with no dossier from a user-scoped view.
            stmt = stmt.join(
                RegulatoryDossierORM,
                RegulatoryActionItemORM.dossier_id == RegulatoryDossierORM.id,
            ).where(RegulatoryDossierORM.created_by_user_id == owner_scope_id)
        if dossier_id is not None:
            stmt = stmt.where(RegulatoryActionItemORM.dossier_id == dossier_id)
        if status is not None:
            stmt = stmt.where(RegulatoryActionItemORM.status == status)
        return [_action_to_record(row) for row in session.scalars(stmt).all()]


def update_action_item(
    session_factory: sessionmaker[Session],
    action_item_id: int,
    payload: RegulatoryActionItemUpdate,
    *,
    actor: RegulatoryComplianceActor,
) -> RegulatoryActionItem | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryActionItemORM, action_item_id)
        if row is None:
            return None
        fields = payload.model_fields_set
        for field_name in ("action_type", "title", "description", "severity", "status", "due_date", "assigned_to"):
            if field_name in fields:
                setattr(row, field_name, getattr(payload, field_name))
        if "citation_ids_json" in fields and payload.citation_ids_json is not None:
            _validate_citation_ids(session, payload.citation_ids_json)
            row.citation_ids_json = _json_dump(payload.citation_ids_json)
        if "metadata_json" in fields and payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.updated_at = utcnow()
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.action_item.update",
            message="Regulatory compliance action item updated.",
            entity_type="regulatory_action_item",
            entity_id=row.id,
            metadata={"updated_fields": sorted(fields)},
        )
        return _action_to_record(row)


def _best_impurity_trigger(
    session: Session,
    dossier: RegulatoryDossierORM,
    *,
    observed_level_percent: float | None,
    observed_amount: float | None,
) -> tuple[str, ImpurityThresholdRuleORM | None]:
    best_trigger = "none"
    best_rule: ImpurityThresholdRuleORM | None = None
    rule_set_ids = [row.id for row in _active_rule_sets(session, dossier)]
    if not rule_set_ids:
        return ("review_required" if observed_level_percent is not None or observed_amount is not None else "none", None)
    rules = session.scalars(
        select(ImpurityThresholdRuleORM).where(ImpurityThresholdRuleORM.rule_set_id.in_(rule_set_ids))
    ).all()
    for rule in rules:
        triggered = False
        if (
            observed_level_percent is not None
            and rule.threshold_percent is not None
            and observed_level_percent >= rule.threshold_percent
        ):
            triggered = True
        if (
            observed_amount is not None
            and rule.threshold_amount_mg_per_day is not None
            and observed_amount >= rule.threshold_amount_mg_per_day
        ):
            triggered = True
        if triggered and _TRIGGER_ORDER.get(rule.rule_type, 0) >= _TRIGGER_ORDER.get(best_trigger, 0):
            best_trigger = rule.rule_type
            best_rule = rule
    return best_trigger, best_rule


def _q3ab_trigger(
    daily_dose_g: float, observed_level_percent: float, substance_type: str = "drug_substance"
) -> str:
    """ICH Q3A/B threshold band the observed impurity level falls in (deterministic
    engine) when no tenant rule matches."""

    try:
        from moltrace.regulatory.impurities import calculate_q3ab_thresholds

        thr = calculate_q3ab_thresholds(daily_dose_g, substance_type)
    except Exception:
        return "none"
    if observed_level_percent >= thr.qualification_threshold.effective_percent:
        return "qualification"
    if observed_level_percent >= thr.identification_threshold.effective_percent:
        return "identification"
    if observed_level_percent >= thr.reporting_threshold.effective_percent:
        return "reporting"
    return "none"


def _m7_summary(structural_assignment: str | None) -> dict[str, Any] | None:
    """ICH M7 mutagenicity classification when ``structural_assignment`` is a parseable
    SMILES (deterministic engine). ``None`` for free-text assignments."""

    if not structural_assignment or not structural_assignment.strip():
        return None
    try:
        from moltrace.regulatory.impurities import classify_m7

        m7 = classify_m7(structural_assignment.strip())
    except Exception:
        return None
    return {
        "m7_class": m7.m7_class,
        "ttc_ug_per_day": m7.ttc_ug_per_day,
        "coc_flag": m7.coc_flag,
        "expert_review_required": m7.expert_review_required,
        "regulatory_basis": m7.regulatory_basis,
        "rule_set_version": m7.rule_set_version,
    }


def create_impurity_risk_register(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: ImpurityRiskRegisterCreate,
    *,
    actor: RegulatoryComplianceActor,
) -> ImpurityRiskRegister:
    with session_scope(session_factory) as session:
        dossier = _require_dossier(session, dossier_id)
        _require_compound(session, payload.compound_id)
        _require_evidence_link(session, payload.evidence_link_id)
        trigger, rule = _best_impurity_trigger(
            session,
            dossier,
            observed_level_percent=payload.observed_level_percent,
            observed_amount=payload.observed_amount,
        )
        # Dose for the Q3A/B band: per-call override wins, else the dossier's product dose.
        dose = (
            payload.daily_dose_g if payload.daily_dose_g is not None else dossier.max_daily_dose_g
        )
        if payload.threshold_triggered is not None:
            trigger = payload.threshold_triggered
        elif rule is None and dose is not None and payload.observed_level_percent is not None:
            # No tenant rule but a dose is available -> compute the ICH Q3A/B band from the
            # deterministic engine (overrides the default no-rule review_required signal).
            trigger = _q3ab_trigger(
                dose, payload.observed_level_percent, dossier.substance_type or "drug_substance"
            )
        m7 = _m7_summary(payload.structural_assignment)
        warnings = list(payload.warnings_json)
        notes = list(payload.notes_json) or [_COMPLIANCE_NOTE]
        action: RegulatoryActionItemORM | None = None
        status = payload.status or ("action_required" if trigger in {"reporting", "identification", "qualification", "review_required"} else "needs_review")
        if trigger in {"reporting", "identification", "qualification", "review_required"}:
            action_type = {
                "reporting": "impurity_reporting",
                "identification": "impurity_identification",
                "qualification": "impurity_qualification",
            }.get(trigger, "human_review")
            severity = {"reporting": "warning", "identification": "high", "qualification": "critical"}.get(trigger, "warning")
            citation_ids = _json_int_list(rule.citation_ids_json) if rule is not None else []
            if not citation_ids:
                warnings.append("source_needed: threshold triggered without rule-level citation support.")
            action = _create_action_item_row(
                session,
                actor=actor,
                dossier_id=dossier_id,
                compound_id=payload.compound_id,
                evidence_link_id=payload.evidence_link_id,
                action_type=action_type,
                title=f"Impurity {trigger.replace('_', ' ')} threshold triggered",
                description=(
                    "Impurity evidence produced a threshold triggered draft compliance assessment; "
                    "qualified human review required."
                ),
                severity=severity,
                citation_ids=citation_ids,
                metadata={"threshold_triggered": trigger, "rule_id": rule.id if rule is not None else None},
            )
        _impurity_metadata = dict(payload.metadata_json)
        if m7 is not None:
            _impurity_metadata["m7"] = m7
        row = ImpurityRiskRegisterORM(
            dossier_id=dossier_id,
            impurity_name=payload.impurity_name,
            impurity_type=payload.impurity_type,
            source=payload.source,
            observed_level_percent=payload.observed_level_percent,
            observed_amount=payload.observed_amount,
            threshold_triggered=trigger,
            structural_assignment=payload.structural_assignment,
            compound_id=payload.compound_id,
            evidence_link_id=payload.evidence_link_id,
            action_item_id=action.id if action is not None else None,
            status=status,
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(notes),
            metadata_json=_json_dump(_metadata_with_warnings(_impurity_metadata, warnings)),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.impurity_register.create",
            message="Impurity risk register entry created; qualified human review required.",
            entity_type="impurity_risk_register",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "threshold_triggered": trigger},
        )
        return _impurity_to_record(row)


def list_impurity_risk_register(
    session_factory: sessionmaker[Session],
    dossier_id: int,
) -> list[ImpurityRiskRegister]:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        rows = session.scalars(
            select(ImpurityRiskRegisterORM)
            .where(ImpurityRiskRegisterORM.dossier_id == dossier_id)
            .order_by(ImpurityRiskRegisterORM.id.desc())
        ).all()
        return [_impurity_to_record(row) for row in rows]


def _impurity_to_record(row: ImpurityRiskRegisterORM) -> ImpurityRiskRegister:
    warnings = _string_list(row.warnings_json)
    notes = _string_list(row.notes_json) or [_COMPLIANCE_NOTE]
    return ImpurityRiskRegister(
        id=row.id,
        dossier_id=row.dossier_id,
        impurity_name=row.impurity_name,
        impurity_type=row.impurity_type,  # type: ignore[arg-type]
        source=row.source,  # type: ignore[arg-type]
        observed_level_percent=row.observed_level_percent,
        observed_amount=row.observed_amount,
        threshold_triggered=row.threshold_triggered,  # type: ignore[arg-type]
        structural_assignment=row.structural_assignment,
        compound_id=row.compound_id,
        evidence_link_id=row.evidence_link_id,
        action_item_id=row.action_item_id,
        status=row.status,  # type: ignore[arg-type]
        warnings_json=warnings,
        notes_json=notes,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=notes,
    )


def _assessment_to_record(row: BatchRegulatoryAssessmentORM) -> BatchRegulatoryAssessment:
    warnings = _string_list(row.warnings_json)
    notes = _string_list(row.notes_json) or [_COMPLIANCE_NOTE]
    return BatchRegulatoryAssessment(
        id=row.id,
        dossier_id=row.dossier_id,
        batch_id=row.batch_id,
        compound_id=row.compound_id,
        overall_status=row.overall_status,  # type: ignore[arg-type]
        impurity_summary_json=_json_dict(row.impurity_summary_json),
        elemental_summary_json=_json_dict(row.elemental_summary_json),
        residual_solvent_summary_json=_json_dict(row.residual_solvent_summary_json),
        nitrosamine_summary_json=_json_dict(row.nitrosamine_summary_json),
        qnmr_summary_json=_json_dict(row.qnmr_summary_json),
        ai_governance_summary_json=_json_dict(row.ai_governance_summary_json),
        action_item_ids_json=_json_int_list(row.action_item_ids_json),
        warnings_json=warnings,
        notes_json=notes,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=notes,
    )


def _solvent_key(name: str | None) -> str:
    raw = (name or "").strip().lower()
    return _SOLVENT_ALIASES.get(raw, raw)


def _q3c_default(name: str, daily_dose_g: float | None = None) -> dict[str, Any] | None:
    """ICH Q3C default classification for a solvent with no tenant rule (deterministic
    engine). When the dossier carries a daily dose, the dose-scaled Option-2 limit is
    used (``PDE * 1000 / dose``); otherwise the Option-1 concentration limit (10 g/day
    reference). Tenant rules, when present, remain the override. ``None`` when the
    solvent is outside the encoded ICH Q3C subset (caller keeps the source-needed path)."""

    if not name.strip():
        return None
    try:
        from moltrace.regulatory.impurities import classify_solvent

        cls = classify_solvent(name)
    except Exception:
        return None
    if not cls.matched:
        return None
    limit_ppm = cls.concentration_limit_ppm
    limit_basis = "ICH Q3C Option 1 (10 g/day reference)"
    if daily_dose_g is not None and cls.pde_mg_per_day is not None:
        limit_ppm = cls.pde_mg_per_day * 1000.0 / daily_dose_g  # Option 2, dose-scaled
        limit_basis = "ICH Q3C Option 2 (dose-scaled to the dossier daily dose)"
    return {
        "fields": {
            "solvent_class": f"class_{cls.class_number}",
            "concentration_limit": limit_ppm,
            "permitted_daily_exposure": cls.pde_mg_per_day,
            "source": "ich_q3c_engine",
            "regulatory_basis": cls.regulatory_basis,
            "rule_set_version": cls.rule_set_version,
            "limit_basis": limit_basis,
        },
        "limit_ppm": limit_ppm,
        "class_1": cls.class_number == 1,
    }


def create_residual_solvent_assessment(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: ResidualSolventAssessmentRequest,
    *,
    actor: RegulatoryComplianceActor,
) -> BatchRegulatoryAssessment:
    with session_scope(session_factory) as session:
        dossier = _require_dossier(session, dossier_id)
        _require_batch(session, payload.batch_id)
        _require_compound(session, payload.compound_id)
        rule_set_ids = [row.id for row in _active_rule_sets(session, dossier)]
        rules = session.scalars(select(ResidualSolventRuleORM).where(ResidualSolventRuleORM.rule_set_id.in_(rule_set_ids))).all() if rule_set_ids else []
        by_name = {_solvent_key(rule.solvent_name): rule for rule in rules}
        matches: list[dict[str, Any]] = []
        action_ids: list[int] = []
        warnings: list[str] = []
        for solvent in payload.solvents_json:
            name = str(solvent.get("solvent_name") or solvent.get("name") or "")
            key = _solvent_key(name)
            rule = by_name.get(key)
            observed = solvent.get("concentration") or solvent.get("concentration_ppm") or solvent.get("observed_ppm")
            try:
                observed_value = float(observed) if observed is not None else None
            except (TypeError, ValueError):
                observed_value = None
            match = {
                "input_solvent_name": name,
                "normalized_solvent_name": key,
                "observed_concentration": observed_value,
                "rule_found": rule is not None,
                "threshold_triggered": False,
            }
            citation_ids: list[int] = []
            if rule is not None:
                citation_ids = _json_int_list(rule.citation_ids_json)
                match.update(
                    {
                        "solvent_class": rule.solvent_class,
                        "concentration_limit": rule.concentration_limit,
                        "permitted_daily_exposure": rule.permitted_daily_exposure,
                    }
                )
                if observed_value is not None and rule.concentration_limit is not None and observed_value >= rule.concentration_limit:
                    match["threshold_triggered"] = True
                if rule.solvent_class == "class_1":
                    match["review_required"] = True
            else:
                engine = _q3c_default(name, dossier.max_daily_dose_g)
                if engine is not None:
                    match.update(engine["fields"])
                    if (
                        observed_value is not None
                        and engine["limit_ppm"] is not None
                        and observed_value >= engine["limit_ppm"]
                    ):
                        match["threshold_triggered"] = True
                    if engine["class_1"]:
                        match["review_required"] = True
                else:
                    warnings.append(
                        f"source_needed: no configured rule or ICH Q3C entry matched "
                        f"{name or 'unknown solvent'}."
                    )
                    match["review_required"] = True
            if match.get("threshold_triggered") or match.get("review_required"):
                action = _create_action_item_row(
                    session,
                    actor=actor,
                    dossier_id=dossier_id,
                    batch_id=payload.batch_id,
                    compound_id=payload.compound_id,
                    action_type="residual_solvent_review",
                    title="Residual solvent review required",
                    description="Residual solvent evidence produced a review required draft compliance assessment.",
                    severity="high" if match.get("threshold_triggered") else "warning",
                    citation_ids=citation_ids,
                    metadata=match,
                )
                action_ids.append(action.id)
            matches.append(match)
        status = "action_required" if action_ids else "ready_for_review"
        row = BatchRegulatoryAssessmentORM(
            dossier_id=dossier_id,
            batch_id=payload.batch_id,
            compound_id=payload.compound_id,
            overall_status=status,
            residual_solvent_summary_json=_json_dump({"matched_solvents": matches, "action_required": bool(action_ids)}),
            action_item_ids_json=_json_dump(action_ids),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_COMPLIANCE_NOTE]),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.residual_solvent_assessment.create",
            message="Residual solvent draft compliance assessment created.",
            entity_type="batch_regulatory_assessment",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "action_item_ids": action_ids},
        )
        return _assessment_to_record(row)


def create_elemental_impurity_assessment(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: ElementalImpurityAssessmentRequest,
    *,
    actor: RegulatoryComplianceActor,
) -> BatchRegulatoryAssessment:
    """ICH Q3D elemental-impurity assessment (deterministic engine). The PDE and
    permitted concentration use the dossier's ``route`` + ``max_daily_dose_g``. ICH Q3D
    has no legacy tenant rule type, so the engine is the sole source. Decision-support;
    every result requires qualified human review."""

    from moltrace.regulatory.impurities import calculate_concentration_limit, get_element_pde
    from moltrace.regulatory.infra.validation import DataValidationError

    with session_scope(session_factory) as session:
        dossier = _require_dossier(session, dossier_id)
        _require_batch(session, payload.batch_id)
        _require_compound(session, payload.compound_id)
        route = dossier.route or "oral"
        dose = dossier.max_daily_dose_g
        matches: list[dict[str, Any]] = []
        action_ids: list[int] = []
        warnings: list[str] = []
        for element in payload.elements_json:
            name = str(element.get("element") or element.get("name") or "")
            observed = element.get("observed_ppm") or element.get("measured_ppm")
            try:
                observed_value = float(observed) if observed is not None else None
            except (TypeError, ValueError):
                observed_value = None
            match: dict[str, Any] = {
                "input_element": name,
                "observed_concentration": observed_value,
                "route": route,
                "threshold_triggered": False,
            }
            try:
                pde = get_element_pde(name, route)
            except DataValidationError:
                warnings.append(
                    f"source_needed: {name or 'unknown element'} is not an ICH Q3D-listed element."
                )
                match["review_required"] = True
                matches.append(match)
                continue
            match.update(
                {
                    "element": pde.element,
                    "element_class": pde.element_class,
                    "pde_ug_per_day": pde.pde_ug_per_day,
                    "route_data_available": pde.route_data_available,
                    "source": "ich_q3d_engine",
                    "regulatory_basis": pde.regulatory_basis,
                    "rule_set_version": pde.rule_set_version,
                }
            )
            permitted_ppm = None
            if dose is not None and pde.route_data_available:
                try:
                    limit = calculate_concentration_limit(name, route, dose)
                except DataValidationError:
                    limit = None
                if limit is not None:
                    permitted_ppm = limit.permitted_concentration_ppm
                    match["permitted_concentration_ppm"] = permitted_ppm
                    match["control_threshold_ppm"] = limit.control_threshold_ppm
            elif dose is None:
                warnings.append(
                    f"dossier max_daily_dose_g required for the permitted concentration of "
                    f"{pde.element}."
                )
            if observed_value is not None and permitted_ppm is not None:
                match["threshold_triggered"] = observed_value >= permitted_ppm
            if pde.element_class == "1":
                match["review_required"] = True
            if match.get("threshold_triggered") or match.get("review_required"):
                action = _create_action_item_row(
                    session,
                    actor=actor,
                    dossier_id=dossier_id,
                    batch_id=payload.batch_id,
                    compound_id=payload.compound_id,
                    action_type="elemental_impurity_review",
                    title="Elemental impurity review required",
                    description=(
                        "Elemental impurity evidence produced a review required draft "
                        "compliance assessment."
                    ),
                    severity="high" if match.get("threshold_triggered") else "warning",
                    citation_ids=[],
                    metadata=match,
                )
                action_ids.append(action.id)
            matches.append(match)
        status = "action_required" if action_ids else "ready_for_review"
        row = BatchRegulatoryAssessmentORM(
            dossier_id=dossier_id,
            batch_id=payload.batch_id,
            compound_id=payload.compound_id,
            overall_status=status,
            elemental_summary_json=_json_dump(
                {"assessed_elements": matches, "route": route, "action_required": bool(action_ids)}
            ),
            action_item_ids_json=_json_dump(action_ids),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_COMPLIANCE_NOTE]),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.elemental_impurity_assessment.create",
            message="Elemental impurity draft compliance assessment created.",
            entity_type="batch_regulatory_assessment",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "action_item_ids": action_ids},
        )
        return _assessment_to_record(row)


def list_elemental_impurity_assessments(
    session_factory: sessionmaker[Session], dossier_id: int
) -> list[BatchRegulatoryAssessment]:
    return [
        item
        for item in list_batch_assessments(session_factory, dossier_id)
        if item.elemental_summary_json
    ]


def _has_nitroso_signal(text: str | None, signals: list[dict[str, Any]]) -> bool:
    haystack = text or ""
    for signal in signals:
        haystack += " " + " ".join(str(value) for value in signal.values())
        if signal.get("nitrosamine_possible") or signal.get("n_nitroso_motif") or signal.get("review_required"):
            return True
    return any(pattern.search(haystack) for pattern in _NITROSO_PATTERNS)


def _cpca_summary(structure_text: str | None) -> dict[str, Any] | None:
    """FDA CPCA categorization when ``structure_text`` is a parseable nitrosamine
    SMILES (deterministic engine) — the real potency category + AI limit, replacing
    the bare regex motif flag. ``None`` for free text / non-nitrosamine input (caller
    falls back to the regex signal)."""

    if not structure_text or not structure_text.strip():
        return None
    try:
        from moltrace.regulatory.impurities import classify_cpca

        cpca = classify_cpca(structure_text.strip())
    except Exception:
        return None
    return {
        "cpca_category": cpca.category,
        "ai_limit_ng_per_day": cpca.ai_limit_ng_per_day,
        "potency_score": cpca.potency_score,
        "coc_flag": cpca.coc_flag,
        "rule_set_version": cpca.rule_set_version,
        "regulatory_basis": cpca.regulatory_basis,
    }


def create_nitrosamine_watch(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: NitrosamineWatchRequest,
    *,
    actor: RegulatoryComplianceActor,
) -> BatchRegulatoryAssessment:
    with session_scope(session_factory) as session:
        dossier = _require_dossier(session, dossier_id)
        _require_batch(session, payload.batch_id)
        _require_compound(session, payload.compound_id)
        possible = _has_nitroso_signal(payload.structure_text, payload.risk_signals_json)
        cpca = _cpca_summary(payload.structure_text)
        if cpca is not None:
            possible = True  # a parseable nitrosamine SMILES is a definitive structural signal
        rule_set_ids = [row.id for row in _active_rule_sets(session, dossier)]
        rules = session.scalars(select(NitrosamineRiskRuleORM).where(NitrosamineRiskRuleORM.rule_set_id.in_(rule_set_ids))).all() if rule_set_ids else []
        matched_rules = [
            {
                "id": rule.id,
                "risk_category": rule.risk_category,
                "structural_pattern": rule.structural_pattern,
                "acceptable_intake": rule.acceptable_intake,
                "ai_limit": rule.ai_limit,
            }
            for rule in rules
            if possible and rule.risk_category in {"n_nitroso_motif", "nitrosamine_possible", "cpca_review_required"}
        ]
        action_ids: list[int] = []
        warnings: list[str] = []
        if possible:
            citation_ids = _json_int_list(rules[0].citation_ids_json) if rules else []
            if not citation_ids:
                warnings.append("source_needed: nitrosamine watch flagged review required without citation-supported rule.")
            action = _create_action_item_row(
                session,
                actor=actor,
                dossier_id=dossier_id,
                batch_id=payload.batch_id,
                compound_id=payload.compound_id,
                action_type="nitrosamine_risk_review",
                title="Nitrosamine risk review required",
                description=(
                    "N-nitroso or nitrosamine risk signal detected. This is a review required signal only, "
                    "not a confirmed nitrosamine conclusion."
                ),
                severity="high",
                citation_ids=citation_ids,
                metadata={"risk_category": "cpca_review_required", "matched_rule_count": len(matched_rules)},
            )
            action_ids.append(action.id)
        summary = {
            "risk_category": "cpca_review_required" if possible else "unknown",
            "review_required": possible,
            "nitrosamine_confirmed": False,
            "cpca": cpca,  # real FDA CPCA category + AI when structure_text is a nitrosamine SMILES
            # Measured ng/day + the SMILES it was measured against feed the dossier-level
            # cumulative-risk rollup; only kept when the structure parsed as a nitrosamine
            # (cpca present) so the AI-limit ratio is meaningful.
            "measured_ng_per_day": payload.measured_ng_per_day,
            "structure_text": payload.structure_text.strip() if (cpca is not None and payload.structure_text) else None,
            "matched_rules": matched_rules,
            "risk_signals_json": payload.risk_signals_json,
        }
        row = BatchRegulatoryAssessmentORM(
            dossier_id=dossier_id,
            batch_id=payload.batch_id,
            compound_id=payload.compound_id,
            overall_status="action_required" if action_ids else "ready_for_review",
            nitrosamine_summary_json=_json_dump(summary),
            action_item_ids_json=_json_dump(action_ids),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_COMPLIANCE_NOTE, "Nitrosamine watch does not claim confirmation without explicit evidence."]),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.nitrosamine_watch.create",
            message="Nitrosamine watch draft compliance assessment created.",
            entity_type="batch_regulatory_assessment",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "review_required": possible},
        )
        return _assessment_to_record(row)


def create_qnmr_compliance_profile(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: QNMRComplianceProfileCreate,
    *,
    actor: RegulatoryComplianceActor,
) -> QNMRComplianceProfile:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        warnings = list(payload.warnings_json)
        required = {
            "ATP": bool(payload.analytical_target_profile_json),
            "specificity": bool(payload.validation_parameters_json.get("specificity")),
            "accuracy": bool(payload.validation_parameters_json.get("accuracy")),
            "precision": bool(payload.validation_parameters_json.get("precision")),
            "calibration/internal standard": bool(payload.calibration_method or payload.internal_standard),
            "uncertainty": bool(payload.uncertainty_summary_json),
            "audit trail": bool(payload.metadata_json.get("audit_trail") or payload.metadata_json.get("audit_event_ids")),
            "sample/source hash": bool(payload.metadata_json.get("sample_hash") or payload.metadata_json.get("source_hash")),
        }
        missing = [name for name, ok in required.items() if not ok]
        for name in missing:
            warnings.append(f"review required: qNMR compliance metadata missing {name}.")
        status = payload.q2_q14_readiness_status or ("gaps_identified" if missing else "ready_for_review")
        action_ids: list[int] = []
        if missing:
            action = _create_action_item_row(
                session,
                actor=actor,
                dossier_id=dossier_id,
                action_type="qnmr_validation_gap",
                title="qNMR validation metadata gap",
                description="qNMR profile has validation metadata gaps; qualified human review required.",
                severity="warning",
                citation_ids=[],
                metadata={"missing_metadata": missing},
            )
            action_ids.append(action.id)
        metadata = dict(payload.metadata_json)
        metadata["action_item_ids"] = action_ids
        metadata["missing_metadata"] = missing
        row = QNMRComplianceProfileORM(
            dossier_id=dossier_id,
            analytical_target_profile_json=_json_dump(payload.analytical_target_profile_json),
            validation_parameters_json=_json_dump(payload.validation_parameters_json),
            calibration_method=payload.calibration_method,
            internal_standard=payload.internal_standard,
            acquisition_parameters_json=_json_dump(payload.acquisition_parameters_json),
            uncertainty_summary_json=_json_dump(payload.uncertainty_summary_json),
            q2_q14_readiness_status=status,
            citations_json=_json_dump(payload.citations_json),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(payload.notes_json or [_COMPLIANCE_NOTE]),
            metadata_json=_json_dump(metadata),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.qnmr_profile.create",
            message="qNMR compliance profile created.",
            entity_type="qnmr_compliance_profile",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "status": status, "missing_metadata": missing},
        )
        return _qnmr_to_record(row)


def list_qnmr_compliance_profiles(session_factory: sessionmaker[Session], dossier_id: int) -> list[QNMRComplianceProfile]:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        rows = session.scalars(
            select(QNMRComplianceProfileORM)
            .where(QNMRComplianceProfileORM.dossier_id == dossier_id)
            .order_by(QNMRComplianceProfileORM.id.desc())
        ).all()
        return [_qnmr_to_record(row) for row in rows]


def _qnmr_to_record(row: QNMRComplianceProfileORM) -> QNMRComplianceProfile:
    warnings = _string_list(row.warnings_json)
    notes = _string_list(row.notes_json) or [_COMPLIANCE_NOTE]
    return QNMRComplianceProfile(
        id=row.id,
        dossier_id=row.dossier_id,
        analytical_target_profile_json=_json_dict(row.analytical_target_profile_json),
        validation_parameters_json=_json_dict(row.validation_parameters_json),
        calibration_method=row.calibration_method,
        internal_standard=row.internal_standard,
        acquisition_parameters_json=_json_dict(row.acquisition_parameters_json),
        uncertainty_summary_json=_json_dict(row.uncertainty_summary_json),
        q2_q14_readiness_status=row.q2_q14_readiness_status,  # type: ignore[arg-type]
        citations_json=_json_list(row.citations_json),
        warnings_json=warnings,
        notes_json=notes,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=notes,
    )


def create_method_validation_profile(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: AnalyticalMethodValidationProfileCreate,
    *,
    actor: RegulatoryComplianceActor,
) -> AnalyticalMethodValidationProfile:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        warnings = list(payload.warnings_json)
        categories = {
            "analytical_target_profile": payload.analytical_target_profile_json,
            "accuracy": payload.accuracy_json,
            "precision": payload.precision_json,
            "specificity": payload.specificity_json,
            "linearity": payload.linearity_json,
            "range": payload.range_json,
            "robustness": payload.robustness_json,
            "lod_loq": payload.lod_loq_json,
        }
        missing = [name for name, value in categories.items() if not value]
        for name in missing:
            warnings.append(f"review required: method validation profile missing {name}.")
        status = payload.validation_status or ("gaps_identified" if missing else "ready_for_review")
        row = AnalyticalMethodValidationProfileORM(
            dossier_id=dossier_id,
            method_type=payload.method_type,
            analytical_target_profile_json=_json_dump(payload.analytical_target_profile_json),
            accuracy_json=_json_dump(payload.accuracy_json) if payload.accuracy_json is not None else None,
            precision_json=_json_dump(payload.precision_json) if payload.precision_json is not None else None,
            specificity_json=_json_dump(payload.specificity_json) if payload.specificity_json is not None else None,
            linearity_json=_json_dump(payload.linearity_json) if payload.linearity_json is not None else None,
            range_json=_json_dump(payload.range_json) if payload.range_json is not None else None,
            robustness_json=_json_dump(payload.robustness_json) if payload.robustness_json is not None else None,
            lod_loq_json=_json_dump(payload.lod_loq_json) if payload.lod_loq_json is not None else None,
            validation_status=status,
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(payload.notes_json or [_COMPLIANCE_NOTE]),
            metadata_json=_json_dump({**payload.metadata_json, "missing_categories": missing}),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.method_validation_profile.create",
            message="Analytical method validation profile created.",
            entity_type="analytical_method_validation_profile",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "status": status},
        )
        return _method_validation_to_record(row)


def list_method_validation_profiles(session_factory: sessionmaker[Session], dossier_id: int) -> list[AnalyticalMethodValidationProfile]:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        rows = session.scalars(
            select(AnalyticalMethodValidationProfileORM)
            .where(AnalyticalMethodValidationProfileORM.dossier_id == dossier_id)
            .order_by(AnalyticalMethodValidationProfileORM.id.desc())
        ).all()
        return [_method_validation_to_record(row) for row in rows]


def _method_validation_to_record(row: AnalyticalMethodValidationProfileORM) -> AnalyticalMethodValidationProfile:
    return AnalyticalMethodValidationProfile(
        id=row.id,
        dossier_id=row.dossier_id,
        method_type=row.method_type,  # type: ignore[arg-type]
        analytical_target_profile_json=_json_dict(row.analytical_target_profile_json),
        accuracy_json=_json_dict(row.accuracy_json) if row.accuracy_json else None,
        precision_json=_json_dict(row.precision_json) if row.precision_json else None,
        specificity_json=_json_dict(row.specificity_json) if row.specificity_json else None,
        linearity_json=_json_dict(row.linearity_json) if row.linearity_json else None,
        range_json=_json_dict(row.range_json) if row.range_json else None,
        robustness_json=_json_dict(row.robustness_json) if row.robustness_json else None,
        lod_loq_json=_json_dict(row.lod_loq_json) if row.lod_loq_json else None,
        validation_status=row.validation_status,  # type: ignore[arg-type]
        warnings_json=_string_list(row.warnings_json),
        notes_json=_string_list(row.notes_json) or [_COMPLIANCE_NOTE],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def create_ai_governance_record(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: AIGovernanceRecordCreate,
    *,
    actor: RegulatoryComplianceActor,
) -> AIGovernanceRecord:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        warnings = list(payload.warnings_json)
        gaps: list[str] = []
        if payload.model_version_id is None:
            gaps.append("model_version_id")
        if payload.method_id is None:
            gaps.append("method_id")
        if payload.workflow_run_id is None:
            gaps.append("workflow_run_id")
        if not payload.explainability_summary_json:
            gaps.append("explainability_summary_json")
        if not payload.human_override_available:
            gaps.append("human_override_available")
        if not payload.validation_record_ids_json:
            gaps.append("validation_record_ids_json")
        for gap in gaps:
            warnings.append(f"review required: AI governance record missing {gap}.")
        status = payload.governance_status or ("gaps_identified" if gaps else "ready_for_review")
        action_ids: list[int] = []
        if gaps:
            action = _create_action_item_row(
                session,
                actor=actor,
                dossier_id=dossier_id,
                action_type="ai_governance_gap",
                title="AI governance gap",
                description="AI governance record has lifecycle, validation, oversight, or explainability gaps.",
                severity="warning",
                citation_ids=[],
                metadata={"gaps": gaps},
            )
            action_ids.append(action.id)
        row = AIGovernanceRecordORM(
            dossier_id=dossier_id,
            ai_system_name=payload.ai_system_name,
            model_version_id=payload.model_version_id,
            method_id=payload.method_id,
            workflow_run_id=payload.workflow_run_id,
            evidence_item_ids_json=_json_dump(payload.evidence_item_ids_json),
            explainability_summary_json=_json_dump(payload.explainability_summary_json),
            human_override_available=payload.human_override_available,
            validation_record_ids_json=_json_dump(payload.validation_record_ids_json),
            governance_status=status,
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(payload.notes_json or [_COMPLIANCE_NOTE]),
            metadata_json=_json_dump({**payload.metadata_json, "gaps": gaps, "action_item_ids": action_ids}),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.ai_governance_record.create",
            message="AI governance record created.",
            entity_type="ai_governance_record",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "status": status, "gaps": gaps},
        )
        return _ai_governance_to_record(row)


def list_ai_governance_records(session_factory: sessionmaker[Session], dossier_id: int) -> list[AIGovernanceRecord]:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        rows = session.scalars(
            select(AIGovernanceRecordORM)
            .where(AIGovernanceRecordORM.dossier_id == dossier_id)
            .order_by(AIGovernanceRecordORM.id.desc())
        ).all()
        return [_ai_governance_to_record(row) for row in rows]


def _ai_governance_to_record(row: AIGovernanceRecordORM) -> AIGovernanceRecord:
    warnings = _string_list(row.warnings_json)
    notes = _string_list(row.notes_json) or [_COMPLIANCE_NOTE]
    return AIGovernanceRecord(
        id=row.id,
        dossier_id=row.dossier_id,
        ai_system_name=row.ai_system_name,
        model_version_id=row.model_version_id,
        method_id=row.method_id,
        workflow_run_id=row.workflow_run_id,
        evidence_item_ids_json=_json_int_list(row.evidence_item_ids_json),
        explainability_summary_json=_json_dict(row.explainability_summary_json),
        human_override_available=row.human_override_available,
        validation_record_ids_json=_json_int_list(row.validation_record_ids_json),
        governance_status=row.governance_status,  # type: ignore[arg-type]
        warnings_json=warnings,
        notes_json=notes,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=notes,
    )


def create_jurisdictional_map(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: JurisdictionalRequirementMapCreate,
    *,
    actor: RegulatoryComplianceActor,
) -> JurisdictionalRequirementMap:
    with session_scope(session_factory) as session:
        dossier = _require_dossier(session, dossier_id)
        _require_jurisdiction(session, payload.jurisdiction_id)
        if payload.rule_set_id is not None and session.get(RegulatoryRuleSetORM, payload.rule_set_id) is None:
            raise RegulatoryComplianceNotFoundError("Regulatory rule set not found.")
        target_rule_sets = _rule_sets_for_jurisdiction(session, payload.jurisdiction_id, payload.rule_set_id)
        baseline_ids = payload.compare_jurisdiction_ids_json or ([dossier.jurisdiction_id] if dossier.jurisdiction_id else [])
        baseline_rule_sets = [rule for jurisdiction_id in baseline_ids for rule in _rule_sets_for_jurisdiction(session, jurisdiction_id, None)]
        target_thresholds = _threshold_summary(session, target_rule_sets)
        baseline_thresholds = _threshold_summary(session, baseline_rule_sets)
        differences = {
            "target_jurisdiction_id": payload.jurisdiction_id,
            "compare_jurisdiction_ids_json": baseline_ids,
            "threshold_differences": _diff_dicts(baseline_thresholds, target_thresholds),
            "rule_set_count": len(target_rule_sets),
            "review_required": True,
        }
        warnings = []
        if not target_rule_sets:
            warnings.append("source_needed: no active rule sets found for selected jurisdiction.")
        row = JurisdictionalRequirementMapORM(
            dossier_id=dossier_id,
            jurisdiction_id=payload.jurisdiction_id,
            rule_set_id=payload.rule_set_id,
            requirement_summary_json=_json_dump({"active_rule_sets": [rule.id for rule in target_rule_sets]}),
            threshold_summary_json=_json_dump(target_thresholds),
            differences_json=_json_dump(differences),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_COMPLIANCE_NOTE]),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.jurisdictional_map.create",
            message="Jurisdictional requirement map created.",
            entity_type="jurisdictional_requirement_map",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "jurisdiction_id": payload.jurisdiction_id},
        )
        return _jurisdictional_map_to_record(row)


def _rule_sets_for_jurisdiction(session: Session, jurisdiction_id: int, rule_set_id: int | None) -> list[RegulatoryRuleSetORM]:
    stmt = select(RegulatoryRuleSetORM).where(
        RegulatoryRuleSetORM.status == "active",
        or_(RegulatoryRuleSetORM.jurisdiction_id.is_(None), RegulatoryRuleSetORM.jurisdiction_id == jurisdiction_id),
    )
    if rule_set_id is not None:
        stmt = stmt.where(RegulatoryRuleSetORM.id == rule_set_id)
    return list(session.scalars(stmt.order_by(RegulatoryRuleSetORM.id.asc())).all())


def _threshold_summary(session: Session, rule_sets: list[RegulatoryRuleSetORM]) -> dict[str, Any]:
    ids = [row.id for row in rule_sets]
    if not ids:
        return {}
    impurity = session.scalars(select(ImpurityThresholdRuleORM).where(ImpurityThresholdRuleORM.rule_set_id.in_(ids))).all()
    solvents = session.scalars(select(ResidualSolventRuleORM).where(ResidualSolventRuleORM.rule_set_id.in_(ids))).all()
    nitrosamines = session.scalars(select(NitrosamineRiskRuleORM).where(NitrosamineRiskRuleORM.rule_set_id.in_(ids))).all()
    return {
        "impurity_thresholds": {
            row.rule_type: {
                "threshold_percent": row.threshold_percent,
                "threshold_amount_mg_per_day": row.threshold_amount_mg_per_day,
            }
            for row in impurity
        },
        "residual_solvents": {
            _solvent_key(row.solvent_name): {
                "solvent_class": row.solvent_class,
                "concentration_limit": row.concentration_limit,
                "permitted_daily_exposure": row.permitted_daily_exposure,
            }
            for row in solvents
        },
        "nitrosamine_rules": {
            row.risk_category: {
                "acceptable_intake": row.acceptable_intake,
                "ai_limit": row.ai_limit,
                "structural_pattern": row.structural_pattern,
            }
            for row in nitrosamines
        },
    }


def _diff_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    keys = set(left) | set(right)
    diff: dict[str, Any] = {}
    for key in sorted(keys):
        if left.get(key) != right.get(key):
            diff[key] = {"baseline": left.get(key), "target": right.get(key)}
    return diff


def list_jurisdictional_maps(session_factory: sessionmaker[Session], dossier_id: int) -> list[JurisdictionalRequirementMap]:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        rows = session.scalars(
            select(JurisdictionalRequirementMapORM)
            .where(JurisdictionalRequirementMapORM.dossier_id == dossier_id)
            .order_by(JurisdictionalRequirementMapORM.id.desc())
        ).all()
        return [_jurisdictional_map_to_record(row) for row in rows]


def _jurisdictional_map_to_record(row: JurisdictionalRequirementMapORM) -> JurisdictionalRequirementMap:
    warnings = _string_list(row.warnings_json)
    notes = _string_list(row.notes_json) or [_COMPLIANCE_NOTE]
    return JurisdictionalRequirementMap(
        id=row.id,
        dossier_id=row.dossier_id,
        jurisdiction_id=row.jurisdiction_id,
        rule_set_id=row.rule_set_id,
        requirement_summary_json=_json_dict(row.requirement_summary_json),
        threshold_summary_json=_json_dict(row.threshold_summary_json),
        differences_json=_json_dict(row.differences_json),
        warnings_json=warnings,
        notes_json=notes,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=warnings,
        notes=notes,
    )


def create_batch_assessment(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: BatchRegulatoryAssessmentCreate,
    *,
    actor: RegulatoryComplianceActor,
) -> BatchRegulatoryAssessment:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        _require_batch(session, payload.batch_id)
        _require_compound(session, payload.compound_id)
        actions = session.scalars(
            select(RegulatoryActionItemORM)
            .where(RegulatoryActionItemORM.dossier_id == dossier_id)
            .order_by(RegulatoryActionItemORM.id.desc())
        ).all()
        open_actions = [row for row in actions if row.status in {"open", "in_progress", "deferred"}]
        impurities = session.scalars(
            select(ImpurityRiskRegisterORM).where(ImpurityRiskRegisterORM.dossier_id == dossier_id)
        ).all()
        qnmr = session.scalars(
            select(QNMRComplianceProfileORM).where(QNMRComplianceProfileORM.dossier_id == dossier_id).order_by(QNMRComplianceProfileORM.id.desc()).limit(1)
        ).first()
        ai = session.scalars(
            select(AIGovernanceRecordORM).where(AIGovernanceRecordORM.dossier_id == dossier_id).order_by(AIGovernanceRecordORM.id.desc()).limit(1)
        ).first()
        assessments = session.scalars(
            select(BatchRegulatoryAssessmentORM).where(BatchRegulatoryAssessmentORM.dossier_id == dossier_id)
        ).all()
        residual_summaries = [_json_dict(row.residual_solvent_summary_json) for row in assessments if _json_dict(row.residual_solvent_summary_json)]
        nitrosamine_summaries = [_json_dict(row.nitrosamine_summary_json) for row in assessments if _json_dict(row.nitrosamine_summary_json)]
        status = "action_required" if open_actions else "ready_for_review"
        warnings = []
        if open_actions:
            warnings.append("action required: unresolved regulatory action items are present.")
        row = BatchRegulatoryAssessmentORM(
            dossier_id=dossier_id,
            batch_id=payload.batch_id,
            compound_id=payload.compound_id,
            overall_status=status,
            impurity_summary_json=_json_dump(
                {
                    "risk_register_count": len(impurities),
                    "threshold_triggered_count": sum(1 for item in impurities if item.threshold_triggered != "none"),
                }
            ),
            residual_solvent_summary_json=_json_dump({"assessments": residual_summaries[-5:]}),
            nitrosamine_summary_json=_json_dump({"assessments": nitrosamine_summaries[-5:]}),
            qnmr_summary_json=_json_dump(_qnmr_to_record(qnmr).model_dump(mode="json") if qnmr else {"status": "not_assessed"}),
            ai_governance_summary_json=_json_dump(_ai_governance_to_record(ai).model_dump(mode="json") if ai else {"status": "not_assessed"}),
            action_item_ids_json=_json_dump([item.id for item in open_actions]),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump([_COMPLIANCE_NOTE]),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="regulatory_compliance.batch_assessment.create",
            message="Batch regulatory draft compliance assessment created.",
            entity_type="batch_regulatory_assessment",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "overall_status": status, "open_action_count": len(open_actions)},
        )
        return _assessment_to_record(row)


def list_batch_assessments(session_factory: sessionmaker[Session], dossier_id: int) -> list[BatchRegulatoryAssessment]:
    with session_scope(session_factory) as session:
        _require_dossier(session, dossier_id)
        rows = session.scalars(
            select(BatchRegulatoryAssessmentORM)
            .where(BatchRegulatoryAssessmentORM.dossier_id == dossier_id)
            .order_by(BatchRegulatoryAssessmentORM.id.desc())
        ).all()
        return [_assessment_to_record(row) for row in rows]


def list_residual_solvent_assessments(session_factory: sessionmaker[Session], dossier_id: int) -> list[BatchRegulatoryAssessment]:
    return [
        item
        for item in list_batch_assessments(session_factory, dossier_id)
        if item.residual_solvent_summary_json
    ]


def list_nitrosamine_watch(session_factory: sessionmaker[Session], dossier_id: int) -> list[BatchRegulatoryAssessment]:
    return [
        item
        for item in list_batch_assessments(session_factory, dossier_id)
        if item.nitrosamine_summary_json
    ]


def dossier_nitrosamine_cumulative_risk(
    session_factory: sessionmaker[Session], dossier_id: int
) -> DossierNitrosamineCumulativeRisk:
    """Roll the dossier's nitrosamine watches up into one FDA Rev-2 cumulative-risk verdict.

    Every nitrosamine watch carrying both a CPCA AI limit (its structure parsed as a
    nitrosamine) and a measured ng/day contributes ``measured / AI limit`` to the sum,
    which must be **< 1**. Watches missing either input are listed under ``excluded`` so
    the verdict's coverage is explicit (a watch with no measured amount cannot have a risk
    ratio). The ``< 1`` decision rule itself is the CPCA engine's
    (:func:`aggregate_cumulative_risk`) — never re-implemented here.
    """

    from moltrace.regulatory.impurities import aggregate_cumulative_risk

    watches = list_nitrosamine_watch(session_factory, dossier_id)  # also validates the dossier
    raw_components: list[dict[str, Any]] = []
    excluded: list[DossierNitrosamineExcludedAssessment] = []
    for watch in watches:
        summary = watch.nitrosamine_summary_json or {}
        cpca = summary.get("cpca")
        measured = summary.get("measured_ng_per_day")
        if not cpca or cpca.get("ai_limit_ng_per_day") is None:
            excluded.append(
                DossierNitrosamineExcludedAssessment(
                    assessment_id=watch.id,
                    reason="structure is not a parseable nitrosamine; no CPCA AI limit to score against.",
                )
            )
            continue
        if measured is None:
            excluded.append(
                DossierNitrosamineExcludedAssessment(
                    assessment_id=watch.id,
                    reason="no measured ng/day recorded on this nitrosamine watch.",
                )
            )
            continue
        raw_components.append(
            {
                "assessment_id": watch.id,
                "structure_text": summary.get("structure_text"),
                "category": cpca.get("cpca_category"),
                "ai_limit_ng_per_day": cpca.get("ai_limit_ng_per_day"),
                "measured_ng_per_day": measured,
            }
        )

    result = aggregate_cumulative_risk(raw_components)
    components = [
        DossierNitrosamineRiskComponent(
            assessment_id=comp["assessment_id"],
            structure_text=comp.get("structure_text"),
            category=comp["category"],
            ai_limit_ng_per_day=comp["ai_limit_ng_per_day"],
            measured_ng_per_day=comp["measured_ng_per_day"],
            risk_ratio=comp["risk_ratio"],
        )
        for comp in result.components
    ]
    notes = list(result.notes)
    if not components:
        notes.insert(
            0,
            "No nitrosamine watch on this dossier carries both a CPCA AI limit and a "
            "measured ng/day; cumulative risk is 0 by default.",
        )
    return DossierNitrosamineCumulativeRisk(
        dossier_id=dossier_id,
        total_risk_ratio=result.total_risk_ratio,
        passes=result.passes,
        n_components=len(components),
        components=components,
        excluded=excluded,
        n_excluded=len(excluded),
        regulatory_basis=result.regulatory_basis,
        disclaimer=result.disclaimer,
        notes=notes,
        human_review_required=True,
    )
