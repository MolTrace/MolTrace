from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    ComplianceDrivenOptimizationObjective,
    ComplianceDrivenOptimizationObjectiveCreate,
    CrossModuleActionItem,
    CrossModuleActionItemCreate,
    CrossModuleActionItemUpdate,
    CrossModuleBridgeReviewRequest,
    CrossModuleCommandCenterSummary,
    CrossModuleWorkflowTemplate,
    CrossModuleWorkflowTemplateCreate,
    CTDModule3ReportBundle,
    CTDModule3ReportBundleCreate,
    ModulePriorityMap,
    ModulePriorityMapPatch,
    ProductProgramOrderPatch,
    ProductProgramRegistry,
    RegulatoryConstraintSet,
    RegulatoryConstraintSetCreate,
    RegulatoryConstraintSetUpdate,
    RegulatoryToReactionBridge,
    RegulatoryToReactionBridgeCreate,
    SpectroscopyToRegulatoryBridge,
    SpectroscopyToRegulatoryBridgeCreate,
)
from .orm import (
    AIGovernanceRecordORM,
    AuditEventORM,
    BatchRegulatoryAssessmentORM,
    ComplianceDrivenOptimizationObjectiveORM,
    CrossModuleActionItemORM,
    CrossModuleCommandCenterSummaryORM,
    CrossModuleWorkflowTemplateORM,
    CTDModule3ReportBundleORM,
    ImpurityRiskRegisterORM,
    ImpurityThresholdRuleORM,
    ModulePriorityMapORM,
    ProductProgramRegistryORM,
    QNMRComplianceProfileORM,
    ReactionProjectORM,
    RegulatoryActionItemORM,
    RegulatoryConstraintSetORM,
    RegulatoryDossierORM,
    RegulatoryReadinessReportORM,
    RegulatoryRequirementORM,
    RegulatoryRuleSetORM,
    RegulatoryToReactionBridgeORM,
    SpectraCheckEvidenceRecordORM,
    SpectraCheckReportRecordORM,
    SpectraCheckSessionORM,
    SpectroscopyToRegulatoryBridgeORM,
    utcnow,
)


class ProductOrchestrationError(ValueError):
    pass


class ProductOrchestrationNotFoundError(ProductOrchestrationError):
    pass


@dataclass(frozen=True)
class ProductOrchestrationActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


DEFAULT_PROGRAM_ORDER = ["spectracheck", "regulatory_hub", "reaction_optimization"]
_PROGRAMS = (
    {
        "program_key": "spectracheck",
        "display_name": "SpectraCheck",
        "display_order": 1,
        "description": "Spectroscopy evidence generation and review.",
    },
    {
        "program_key": "regulatory_hub",
        "display_name": "Regulatory Hub",
        "display_order": 2,
        "description": "Source-supported regulatory action and compliance review.",
    },
    {
        "program_key": "reaction_optimization",
        "display_name": "Reaction Optimization",
        "display_order": 3,
        "description": "Reaction optimization constrained by compliance actions.",
    },
)
_PRODUCT_RULE_NOTE = (
    "Spectroscopy generates evidence; Regulatory Intelligence converts evidence into "
    "compliance action; Reaction Optimization uses compliance action as constraints."
)
_REVIEW_NOTE = (
    "Cross-module handoffs are draft, auditable, and require review before scientific "
    "or regulatory use."
)
_PRIVATE_MARKERS = (
    "password",
    "token",
    "secret",
    "api_key",
    "raw_spectrum",
    "raw_spectra",
    "raw_data",
    "raw_source",
    "full_source",
    "full_text",
    "full_smiles",
    "smiles",
    "file_bytes",
    "uploaded_file",
)


def ensure_default_programs(session_factory: sessionmaker[Session]) -> None:
    with session_scope(session_factory) as session:
        _ensure_defaults(session)


def list_programs(session_factory: sessionmaker[Session]) -> list[ProductProgramRegistry]:
    with session_scope(session_factory) as session:
        _ensure_defaults(session)
        rows = session.scalars(
            select(ProductProgramRegistryORM).order_by(
                ProductProgramRegistryORM.display_order.asc(),
                ProductProgramRegistryORM.id.asc(),
            )
        ).all()
        return [_program_to_record(row) for row in rows]


def update_program_order(
    session_factory: sessionmaker[Session],
    payload: ProductProgramOrderPatch,
    *,
    actor: ProductOrchestrationActor,
) -> list[ProductProgramRegistry]:
    order = _validated_program_order(payload.program_order_json)
    with session_scope(session_factory) as session:
        _ensure_defaults(session)
        rows = {
            row.program_key: row for row in session.scalars(select(ProductProgramRegistryORM)).all()
        }
        for index, program_key in enumerate(order, start=1):
            rows[program_key].display_order = index
            rows[program_key].updated_at = utcnow()
            rows[program_key].metadata_json = _json_dump(
                {**_json_dict(rows[program_key].metadata_json), **payload.metadata_json}
            )
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.program_order.update",
            message="Product program order updated for reviewable module orchestration.",
            entity_type="product_program_registry",
            metadata={"program_order_json": order},
        )
        return [
            _program_to_record(row)
            for row in session.scalars(
                select(ProductProgramRegistryORM).order_by(
                    ProductProgramRegistryORM.display_order.asc()
                )
            ).all()
        ]


def list_module_priority(
    session_factory: sessionmaker[Session],
    *,
    context: str | None = None,
) -> list[ModulePriorityMap]:
    with session_scope(session_factory) as session:
        _ensure_defaults(session)
        stmt = select(ModulePriorityMapORM).order_by(ModulePriorityMapORM.context.asc())
        if context is not None:
            stmt = stmt.where(ModulePriorityMapORM.context == context)
        return [_priority_to_record(row) for row in session.scalars(stmt).all()]


def update_module_priority(
    session_factory: sessionmaker[Session],
    payload: ModulePriorityMapPatch,
    *,
    actor: ProductOrchestrationActor,
) -> ModulePriorityMap:
    order = _validated_program_order(payload.program_order_json)
    with session_scope(session_factory) as session:
        _ensure_defaults(session)
        row = session.scalar(
            select(ModulePriorityMapORM).where(ModulePriorityMapORM.context == payload.context)
        )
        if row is None:
            row = ModulePriorityMapORM(context=payload.context)
            session.add(row)
        row.program_order_json = _json_dump(order)
        row.updated_at = utcnow()
        row.metadata_json = _json_dump(payload.metadata_json)
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.module_priority.update",
            message="Module priority map updated.",
            entity_type="module_priority_map",
            entity_id=row.id,
            metadata={"context": row.context, "program_order_json": order},
        )
        session.flush()
        return _priority_to_record(row)


def list_workflow_templates(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    limit: int = 500,
) -> list[CrossModuleWorkflowTemplate]:
    with session_scope(session_factory) as session:
        stmt = select(CrossModuleWorkflowTemplateORM).order_by(
            CrossModuleWorkflowTemplateORM.id.desc()
        )
        if status is not None:
            stmt = stmt.where(CrossModuleWorkflowTemplateORM.status == status)
        return [_workflow_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def create_workflow_template(
    session_factory: sessionmaker[Session],
    payload: CrossModuleWorkflowTemplateCreate,
    *,
    actor: ProductOrchestrationActor,
) -> CrossModuleWorkflowTemplate:
    sequence = payload.program_sequence_json or DEFAULT_PROGRAM_ORDER
    _validated_program_order(sequence)
    with session_scope(session_factory) as session:
        row = CrossModuleWorkflowTemplateORM(
            template_key=payload.template_key,
            name=payload.name,
            description=payload.description,
            program_sequence_json=_json_dump(sequence),
            trigger_type=payload.trigger_type,
            required_inputs_json=_json_dump(payload.required_inputs_json),
            optional_inputs_json=_json_dump(payload.optional_inputs_json),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ProductOrchestrationError("Workflow template already exists.") from exc
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.workflow_template.create",
            message="Cross-module workflow template created.",
            entity_type="cross_module_workflow_template",
            entity_id=row.id,
        )
        return _workflow_to_record(row)


def create_spectroscopy_to_regulatory_bridge(
    session_factory: sessionmaker[Session],
    payload: SpectroscopyToRegulatoryBridgeCreate,
    *,
    actor: ProductOrchestrationActor,
    owner_scope_id: int | None = None,
) -> SpectroscopyToRegulatoryBridge:
    with session_scope(session_factory) as session:
        session_row = _optional(session, SpectraCheckSessionORM, payload.spectracheck_session_id)
        evidence_row = _optional(session, SpectraCheckEvidenceRecordORM, payload.evidence_item_id)
        report_row = _optional(session, SpectraCheckReportRecordORM, payload.report_id)
        dossier = _resolve_dossier(session, payload.dossier_id, session_row, owner_scope_id)
        warnings: list[str] = []
        notes = [_PRODUCT_RULE_NOTE, _REVIEW_NOTE]
        if dossier is None:
            warnings.append(
                "dossier_required: bridge can inspect evidence but cannot create "
                "regulatory action items."
            )
        sources = _spectroscopy_sources(
            session, session_row, evidence_row, report_row, payload.metadata_json
        )
        signals = _extract_regulatory_signals(sources)
        created_actions: list[int] = []
        if dossier is not None:
            created_actions.extend(
                _create_signal_action_items(
                    session,
                    dossier=dossier,
                    evidence_id=evidence_row.id
                    if evidence_row is not None
                    else payload.evidence_item_id,
                    compound_id=payload.compound_id,
                    batch_id=payload.batch_id,
                    signals=signals,
                    warnings=warnings,
                )
            )
        status = "action_items_created" if created_actions else "ready_for_review"
        if dossier is None and warnings:
            status = "blocked"
        row = SpectroscopyToRegulatoryBridgeORM(
            spectracheck_session_id=payload.spectracheck_session_id,
            evidence_item_id=payload.evidence_item_id,
            report_id=payload.report_id,
            dossier_id=dossier.id if dossier is not None else payload.dossier_id,
            compound_id=payload.compound_id,
            batch_id=payload.batch_id,
            bridge_status=status,
            extracted_regulatory_signals_json=_json_dump(signals),
            created_requirement_ids_json=_json_dump([]),
            created_action_item_ids_json=_json_dump(created_actions),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(notes),
            human_review_required=True,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        for action_id in created_actions:
            _create_cross_action_row(
                session,
                source_program="spectracheck",
                target_program="regulatory_hub",
                source_resource_type="spectroscopy_to_regulatory_bridge",
                source_resource_id=row.id,
                target_resource_type="regulatory_action_item",
                target_resource_id=action_id,
                action_type="run_regulatory_assessment",
                title="Review SpectraCheck-derived regulatory action item",
                description=(
                    "Spectroscopy evidence produced a possible threshold trigger or review "
                    "signal; source-supported requirement review is required."
                ),
                severity="warning",
                metadata={"bridge_id": row.id, "regulatory_action_item_id": action_id},
            )
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.spectroscopy_to_regulatory.create",
            message="Spectroscopy-to-regulatory bridge created; outputs require review.",
            entity_type="spectroscopy_to_regulatory_bridge",
            entity_id=row.id,
            metadata={"created_action_item_ids_json": created_actions},
        )
        return _s2r_to_record(row)


def list_spectroscopy_to_regulatory_bridges(
    session_factory: sessionmaker[Session],
    *,
    dossier_id: int | None = None,
    owner_scope_id: int | None = None,
    limit: int = 500,
) -> list[SpectroscopyToRegulatoryBridge]:
    with session_scope(session_factory) as session:
        stmt = select(SpectroscopyToRegulatoryBridgeORM).order_by(
            SpectroscopyToRegulatoryBridgeORM.id.desc()
        )
        if owner_scope_id is not None:
            # Restrict to bridges whose dossier the caller owns (system/admin pass None and
            # see all); the inner join also drops dossier-less bridges from a user view.
            stmt = stmt.join(
                RegulatoryDossierORM,
                SpectroscopyToRegulatoryBridgeORM.dossier_id == RegulatoryDossierORM.id,
            ).where(RegulatoryDossierORM.created_by_user_id == owner_scope_id)
        if dossier_id is not None:
            stmt = stmt.where(SpectroscopyToRegulatoryBridgeORM.dossier_id == dossier_id)
        return [_s2r_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def get_spectroscopy_to_regulatory_bridge(
    session_factory: sessionmaker[Session],
    bridge_id: int,
) -> SpectroscopyToRegulatoryBridge | None:
    with session_scope(session_factory) as session:
        row = session.get(SpectroscopyToRegulatoryBridgeORM, bridge_id)
        return _s2r_to_record(row) if row is not None else None


def review_spectroscopy_to_regulatory_bridge(
    session_factory: sessionmaker[Session],
    bridge_id: int,
    payload: CrossModuleBridgeReviewRequest,
    *,
    actor: ProductOrchestrationActor,
) -> SpectroscopyToRegulatoryBridge | None:
    with session_scope(session_factory) as session:
        row = session.get(SpectroscopyToRegulatoryBridgeORM, bridge_id)
        if row is None:
            return None
        metadata = _json_dict(row.metadata_json)
        metadata["review"] = {
            "reviewer_name": payload.reviewer_name,
            "reviewer_comment": payload.reviewer_comment,
            **payload.metadata_json,
        }
        row.bridge_status = "reviewed"
        row.metadata_json = _json_dump(metadata)
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.spectroscopy_to_regulatory.review",
            message="Spectroscopy-to-regulatory bridge reviewed by a human reviewer.",
            entity_type="spectroscopy_to_regulatory_bridge",
            entity_id=row.id,
        )
        return _s2r_to_record(row)


def create_regulatory_to_reaction_bridge(
    session_factory: sessionmaker[Session],
    payload: RegulatoryToReactionBridgeCreate,
    *,
    actor: ProductOrchestrationActor,
    owner_scope_id: int | None = None,
) -> RegulatoryToReactionBridge:
    with session_scope(session_factory) as session:
        action_rows = _regulatory_action_rows(session, payload, owner_scope_id)
        dossier = _resolve_r2r_dossier(session, payload, action_rows, owner_scope_id)
        reaction_project_id = payload.reaction_project_id or (
            dossier.reaction_project_id if dossier is not None else None
        )
        project = _required(session, ReactionProjectORM, reaction_project_id, "Reaction project")
        warnings: list[str] = []
        notes = [_PRODUCT_RULE_NOTE, _REVIEW_NOTE]
        constraints: list[dict[str, Any]] = []
        constraint_ids: list[int] = []
        for action in action_rows:
            constraint_type = _constraint_type_for_action(action.action_type)
            constraint_json = {
                "source_action_item_id": action.id,
                "source_action_type": action.action_type,
                "source_supported_requirement": action.title,
                "description": action.description,
                "compliance_driven_optimization_constraint": True,
                "requires_review": True,
            }
            row = RegulatoryConstraintSetORM(
                reaction_project_id=project.id,
                dossier_id=action.dossier_id or (dossier.id if dossier is not None else None),
                source_action_item_ids_json=_json_dump([action.id]),
                constraint_type=constraint_type,
                constraint_json=_json_dump(constraint_json),
                severity=action.severity,
                status="draft",
                metadata_json=_json_dump({"bridge_source": "regulatory_to_reaction"}),
            )
            session.add(row)
            session.flush()
            constraints.append(
                {
                    "constraint_id": row.id,
                    "constraint_type": constraint_type,
                    "severity": action.severity,
                    "source_action_item_id": action.id,
                }
            )
            constraint_ids.append(row.id)
        if not action_rows:
            warnings.append(
                "regulatory_action_item_required: no open regulatory action items were available."
            )
        objectives = _compliance_objective_payload(constraints)
        status = "constraints_created" if constraint_ids else "ready_for_review"
        row = RegulatoryToReactionBridgeORM(
            dossier_id=dossier.id if dossier is not None else payload.dossier_id,
            regulatory_action_item_id=payload.regulatory_action_item_id,
            reaction_project_id=project.id,
            compound_id=payload.compound_id,
            batch_id=payload.batch_id,
            bridge_status=status,
            regulatory_constraints_json=_json_dump(constraints),
            optimization_objectives_json=_json_dump(objectives),
            created_constraint_ids_json=_json_dump(constraint_ids),
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(notes),
            human_review_required=True,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        for constraint_id in constraint_ids:
            _create_cross_action_row(
                session,
                source_program="regulatory_hub",
                target_program="reaction_optimization",
                source_resource_type="regulatory_to_reaction_bridge",
                source_resource_id=row.id,
                target_resource_type="regulatory_constraint_set",
                target_resource_id=constraint_id,
                action_type="create_reaction_constraint",
                title="Review compliance-driven optimization constraint",
                description=(
                    "A regulatory action item was converted into a draft "
                    "compliance-driven optimization constraint."
                ),
                severity="warning",
                metadata={"bridge_id": row.id, "constraint_id": constraint_id},
            )
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.regulatory_to_reaction.create",
            message="Regulatory-to-reaction bridge created draft compliance constraints.",
            entity_type="regulatory_to_reaction_bridge",
            entity_id=row.id,
            metadata={"created_constraint_ids_json": constraint_ids},
        )
        return _r2r_to_record(row)


def list_regulatory_to_reaction_bridges(
    session_factory: sessionmaker[Session],
    *,
    reaction_project_id: int | None = None,
    limit: int = 500,
) -> list[RegulatoryToReactionBridge]:
    with session_scope(session_factory) as session:
        stmt = select(RegulatoryToReactionBridgeORM).order_by(
            RegulatoryToReactionBridgeORM.id.desc()
        )
        if reaction_project_id is not None:
            stmt = stmt.where(
                RegulatoryToReactionBridgeORM.reaction_project_id == reaction_project_id
            )
        return [_r2r_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def get_regulatory_to_reaction_bridge(
    session_factory: sessionmaker[Session],
    bridge_id: int,
) -> RegulatoryToReactionBridge | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryToReactionBridgeORM, bridge_id)
        return _r2r_to_record(row) if row is not None else None


def review_regulatory_to_reaction_bridge(
    session_factory: sessionmaker[Session],
    bridge_id: int,
    payload: CrossModuleBridgeReviewRequest,
    *,
    actor: ProductOrchestrationActor,
) -> RegulatoryToReactionBridge | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryToReactionBridgeORM, bridge_id)
        if row is None:
            return None
        metadata = _json_dict(row.metadata_json)
        metadata["review"] = {
            "reviewer_name": payload.reviewer_name,
            "reviewer_comment": payload.reviewer_comment,
            **payload.metadata_json,
        }
        row.bridge_status = "reviewed"
        row.metadata_json = _json_dump(metadata)
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.regulatory_to_reaction.review",
            message="Regulatory-to-reaction bridge reviewed by a human reviewer.",
            entity_type="regulatory_to_reaction_bridge",
            entity_id=row.id,
        )
        return _r2r_to_record(row)


def create_regulatory_constraint(
    session_factory: sessionmaker[Session],
    reaction_project_id: int,
    payload: RegulatoryConstraintSetCreate,
    *,
    actor: ProductOrchestrationActor,
) -> RegulatoryConstraintSet:
    with session_scope(session_factory) as session:
        _required(session, ReactionProjectORM, reaction_project_id, "Reaction project")
        _optional(session, RegulatoryDossierORM, payload.dossier_id)
        row = RegulatoryConstraintSetORM(
            reaction_project_id=reaction_project_id,
            dossier_id=payload.dossier_id,
            source_action_item_ids_json=_json_dump(payload.source_action_item_ids_json),
            constraint_type=payload.constraint_type,
            constraint_json=_json_dump(
                {
                    **payload.constraint_json,
                    "compliance_driven_optimization_constraint": True,
                    "requires_review": True,
                }
            ),
            severity=payload.severity,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.regulatory_constraint.create",
            message="Draft regulatory constraint set created for reaction optimization.",
            entity_type="regulatory_constraint_set",
            entity_id=row.id,
        )
        return _constraint_to_record(row)


def list_regulatory_constraints(
    session_factory: sessionmaker[Session],
    reaction_project_id: int,
) -> list[RegulatoryConstraintSet]:
    with session_scope(session_factory) as session:
        _required(session, ReactionProjectORM, reaction_project_id, "Reaction project")
        rows = session.scalars(
            select(RegulatoryConstraintSetORM)
            .where(RegulatoryConstraintSetORM.reaction_project_id == reaction_project_id)
            .order_by(RegulatoryConstraintSetORM.id.desc())
        ).all()
        return [_constraint_to_record(row) for row in rows]


def update_regulatory_constraint(
    session_factory: sessionmaker[Session],
    constraint_id: int,
    payload: RegulatoryConstraintSetUpdate,
    *,
    actor: ProductOrchestrationActor,
) -> RegulatoryConstraintSet | None:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryConstraintSetORM, constraint_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in ("severity", "status"):
            if field in update:
                setattr(row, field, update[field])
        if "constraint_json" in update and update["constraint_json"] is not None:
            row.constraint_json = _json_dump(update["constraint_json"])
        if "metadata_json" in update and update["metadata_json"] is not None:
            row.metadata_json = _json_dump(update["metadata_json"])
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.regulatory_constraint.update",
            message="Regulatory constraint set updated.",
            entity_type="regulatory_constraint_set",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update)},
        )
        return _constraint_to_record(row)


def create_compliance_objective(
    session_factory: sessionmaker[Session],
    reaction_project_id: int,
    payload: ComplianceDrivenOptimizationObjectiveCreate,
    *,
    actor: ProductOrchestrationActor,
) -> ComplianceDrivenOptimizationObjective:
    with session_scope(session_factory) as session:
        _required(session, ReactionProjectORM, reaction_project_id, "Reaction project")
        constraint = _optional(
            session, RegulatoryConstraintSetORM, payload.regulatory_constraint_set_id
        )
        if constraint is not None and constraint.reaction_project_id != reaction_project_id:
            raise ProductOrchestrationError(
                "Regulatory constraint does not belong to reaction project."
            )
        default_payload = _compliance_objective_payload(
            [{"constraint_id": constraint.id, "constraint_type": constraint.constraint_type}]
            if constraint is not None
            else []
        )
        row = ComplianceDrivenOptimizationObjectiveORM(
            reaction_project_id=reaction_project_id,
            regulatory_constraint_set_id=payload.regulatory_constraint_set_id,
            objective_json=_json_dump(
                {**default_payload["objective_json"], **payload.objective_json}
            ),
            scalarization_json=_json_dump(
                {**default_payload["scalarization_json"], **payload.scalarization_json}
            ),
            hard_constraints_json=_json_dump(
                {**default_payload["hard_constraints_json"], **payload.hard_constraints_json}
            ),
            soft_constraints_json=_json_dump(
                {**default_payload["soft_constraints_json"], **payload.soft_constraints_json}
            ),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.compliance_objective.create",
            message="Compliance-driven reaction optimization objective created.",
            entity_type="compliance_driven_optimization_objective",
            entity_id=row.id,
        )
        return _objective_to_record(row)


def list_compliance_objectives(
    session_factory: sessionmaker[Session],
    reaction_project_id: int,
) -> list[ComplianceDrivenOptimizationObjective]:
    with session_scope(session_factory) as session:
        _required(session, ReactionProjectORM, reaction_project_id, "Reaction project")
        rows = session.scalars(
            select(ComplianceDrivenOptimizationObjectiveORM)
            .where(
                ComplianceDrivenOptimizationObjectiveORM.reaction_project_id == reaction_project_id
            )
            .order_by(ComplianceDrivenOptimizationObjectiveORM.id.desc())
        ).all()
        return [_objective_to_record(row) for row in rows]


def create_ctd_module3_bundle(
    session_factory: sessionmaker[Session],
    dossier_id: int,
    payload: CTDModule3ReportBundleCreate,
    *,
    actor: ProductOrchestrationActor,
) -> CTDModule3ReportBundle:
    with session_scope(session_factory) as session:
        dossier = _required(session, RegulatoryDossierORM, dossier_id, "Regulatory dossier")
        report_json = _build_ctd_report_json(session, dossier, payload)
        if payload.report_json:
            report_json.update(_public_json(payload.report_json))
        report_sha256 = _sha256(report_json)
        row = CTDModule3ReportBundleORM(
            dossier_id=dossier_id,
            spectracheck_report_id=payload.spectracheck_report_id,
            regulatory_readiness_report_id=payload.regulatory_readiness_report_id,
            batch_assessment_id=payload.batch_assessment_id,
            qnmr_compliance_id=payload.qnmr_compliance_id,
            impurity_register_id=payload.impurity_register_id,
            ai_governance_record_id=payload.ai_governance_record_id,
            report_json=_json_dump(report_json),
            report_html=payload.report_html or _ctd_html(report_json),
            report_sha256=report_sha256,
            status=payload.status,
            human_review_required=True,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.ctd_module3_bundle.create",
            message="Draft CTD Module 3 bundle assembled for human review.",
            entity_type="ctd_module3_report_bundle",
            entity_id=row.id,
            metadata={"dossier_id": dossier_id, "report_sha256": report_sha256},
        )
        return _ctd_to_record(row)


def list_ctd_module3_bundles(
    session_factory: sessionmaker[Session],
    dossier_id: int,
) -> list[CTDModule3ReportBundle]:
    with session_scope(session_factory) as session:
        _required(session, RegulatoryDossierORM, dossier_id, "Regulatory dossier")
        rows = session.scalars(
            select(CTDModule3ReportBundleORM)
            .where(CTDModule3ReportBundleORM.dossier_id == dossier_id)
            .order_by(CTDModule3ReportBundleORM.id.desc())
        ).all()
        return [_ctd_to_record(row) for row in rows]


def get_ctd_module3_bundle(
    session_factory: sessionmaker[Session],
    bundle_id: int,
) -> CTDModule3ReportBundle | None:
    with session_scope(session_factory) as session:
        row = session.get(CTDModule3ReportBundleORM, bundle_id)
        return _ctd_to_record(row) if row is not None else None


def create_cross_module_action_item(
    session_factory: sessionmaker[Session],
    payload: CrossModuleActionItemCreate,
    *,
    actor: ProductOrchestrationActor,
) -> CrossModuleActionItem:
    with session_scope(session_factory) as session:
        row = _create_cross_action_row(
            session,
            source_program=payload.source_program,
            target_program=payload.target_program,
            source_resource_type=payload.source_resource_type,
            source_resource_id=payload.source_resource_id,
            target_resource_type=payload.target_resource_type,
            target_resource_id=payload.target_resource_id,
            action_type=payload.action_type,
            title=payload.title,
            description=payload.description,
            severity=payload.severity,
            status=payload.status,
            metadata=payload.metadata_json,
        )
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.cross_module_action.create",
            message="Cross-module action item created.",
            entity_type="cross_module_action_item",
            entity_id=row.id,
        )
        return _cross_action_to_record(row)


def list_cross_module_action_items(
    session_factory: sessionmaker[Session],
    *,
    status: str | None = None,
    limit: int = 500,
) -> list[CrossModuleActionItem]:
    with session_scope(session_factory) as session:
        stmt = select(CrossModuleActionItemORM).order_by(CrossModuleActionItemORM.id.desc())
        if status is not None:
            stmt = stmt.where(CrossModuleActionItemORM.status == status)
        return [_cross_action_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def update_cross_module_action_item(
    session_factory: sessionmaker[Session],
    action_item_id: int,
    payload: CrossModuleActionItemUpdate,
    *,
    actor: ProductOrchestrationActor,
) -> CrossModuleActionItem | None:
    with session_scope(session_factory) as session:
        row = session.get(CrossModuleActionItemORM, action_item_id)
        if row is None:
            return None
        update = payload.model_dump(exclude_unset=True)
        for field in (
            "target_resource_type",
            "target_resource_id",
            "action_type",
            "title",
            "description",
            "severity",
            "status",
        ):
            if field in update:
                setattr(row, field, update[field])
        if "metadata_json" in update and update["metadata_json"] is not None:
            row.metadata_json = _json_dump(update["metadata_json"])
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="product_orchestration.cross_module_action.update",
            message="Cross-module action item updated.",
            entity_type="cross_module_action_item",
            entity_id=row.id,
            metadata={"updated_fields": sorted(update)},
        )
        return _cross_action_to_record(row)


def command_center_summary(
    session_factory: sessionmaker[Session],
    *,
    scope: str = "global",
    scope_id: int | None = None,
) -> CrossModuleCommandCenterSummary:
    with session_scope(session_factory) as session:
        _ensure_defaults(session)
        spectracheck_summary = _spectracheck_summary(session, scope, scope_id)
        regulatory_summary = _regulatory_summary(session, scope, scope_id)
        reaction_summary = _reaction_summary(session, scope, scope_id)
        actions = _open_cross_actions(session, scope, scope_id)
        row = CrossModuleCommandCenterSummaryORM(
            scope=scope,
            scope_id=scope_id,
            spectracheck_summary_json=_json_dump(spectracheck_summary),
            regulatory_summary_json=_json_dump(regulatory_summary),
            reaction_summary_json=_json_dump(reaction_summary),
            open_cross_module_actions_json=_json_dump(actions),
            warnings_json=_json_dump([]),
            notes_json=_json_dump([_PRODUCT_RULE_NOTE, _REVIEW_NOTE]),
            metadata_json=_json_dump({"program_order_json": DEFAULT_PROGRAM_ORDER}),
        )
        session.add(row)
        session.flush()
        return _summary_to_record(row)


def _ensure_defaults(session: Session) -> None:
    existing = {
        row.program_key: row for row in session.scalars(select(ProductProgramRegistryORM)).all()
    }
    for program in _PROGRAMS:
        row = existing.get(program["program_key"])
        if row is None:
            session.add(ProductProgramRegistryORM(status="active", metadata_json="{}", **program))
        else:
            row.display_name = program["display_name"]
            row.description = program["description"]
            row.updated_at = utcnow()
    for context in ("global", "dashboard", "project", "sample", "report", "onboarding", "settings"):
        priority = session.scalar(
            select(ModulePriorityMapORM).where(ModulePriorityMapORM.context == context)
        )
        if priority is None:
            session.add(
                ModulePriorityMapORM(
                    context=context,
                    program_order_json=_json_dump(DEFAULT_PROGRAM_ORDER),
                    metadata_json=_json_dump({"default": True}),
                )
            )


def _validated_program_order(order: list[str]) -> list[str]:
    if list(order) != DEFAULT_PROGRAM_ORDER:
        raise ProductOrchestrationError(
            "Program order must preserve SpectraCheck, Regulatory Hub, Reaction Optimization."
        )
    return list(order)


def _json_dump(value: Any) -> str:
    return json.dumps(_public_json(value), sort_keys=True, separators=(",", ":"))


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
    return [int(item) for item in _json_list(value) if isinstance(item, int)]


def _public_json(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if key_lower.startswith("_") or any(marker in key_lower for marker in _PRIVATE_MARKERS):
                continue
            output[key_text] = _public_json(item)
        return output
    if isinstance(value, list):
        return [_public_json(item) for item in value]
    if isinstance(value, str) and len(value) > 1000:
        return value[:1000] + "...[truncated]"
    return value


def _sha256(value: Any) -> str:
    return hashlib.sha256(_json_dump(value).encode("utf-8")).hexdigest()


def _audit(
    session: Session,
    *,
    actor: ProductOrchestrationActor,
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


def _optional(session: Session, model: type[Any], entity_id: int | None) -> Any | None:
    if entity_id is None:
        return None
    row = session.get(model, entity_id)
    if row is None:
        raise ProductOrchestrationNotFoundError("Referenced record not found.")
    return row


def _required(session: Session, model: type[Any], entity_id: int | None, label: str) -> Any:
    if entity_id is None:
        raise ProductOrchestrationError(f"{label} is required.")
    row = session.get(model, entity_id)
    if row is None:
        raise ProductOrchestrationNotFoundError(f"{label} not found.")
    return row


def _dossier_owned_by(session: Session, dossier_id: int | None, owner_scope_id: int | None) -> bool:
    """In-session dossier-ownership check (mirrors regulatory_intelligence.dossier_owned_by):
    system/admin scope (``None``) sees all; else the dossier must be owned by the scope user;
    a missing / ``None`` dossier is hidden from a user-scoped caller."""
    if owner_scope_id is None:
        return True
    if dossier_id is None:
        return False
    row = session.get(RegulatoryDossierORM, dossier_id)
    return row is not None and row.created_by_user_id == owner_scope_id


def _resolve_dossier(
    session: Session,
    dossier_id: int | None,
    session_row: SpectraCheckSessionORM | None,
    owner_scope_id: int | None = None,
) -> RegulatoryDossierORM | None:
    if dossier_id is not None:
        dossier = _required(session, RegulatoryDossierORM, dossier_id, "Regulatory dossier")
        if not _dossier_owned_by(session, dossier.id, owner_scope_id):
            raise ProductOrchestrationNotFoundError("Regulatory dossier not found.")
        return dossier
    if session_row is None:
        return None
    dossier = session.scalar(
        select(RegulatoryDossierORM)
        .where(RegulatoryDossierORM.spectracheck_session_id == session_row.id)
        .order_by(RegulatoryDossierORM.id.desc())
        .limit(1)
    )
    # A session-derived dossier the caller does not own is treated as absent — the bridge then
    # inspects evidence but creates no action items on someone else's dossier.
    if dossier is not None and not _dossier_owned_by(session, dossier.id, owner_scope_id):
        return None
    return dossier


def _spectroscopy_sources(
    session: Session,
    session_row: SpectraCheckSessionORM | None,
    evidence_row: SpectraCheckEvidenceRecordORM | None,
    report_row: SpectraCheckReportRecordORM | None,
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    if evidence_row is not None:
        sources.append(
            {
                "source_type": "spectracheck_evidence",
                "id": evidence_row.id,
                "summary": evidence_row.summary,
                "evidence_summary_json": _json_list(evidence_row.evidence_summary_json),
                "warnings_json": _json_list(evidence_row.warnings_json),
                "contradictions_json": _json_list(evidence_row.contradictions_json),
                "response_json": _json_dict(evidence_row.response_json),
                "provenance_json": _json_dict(evidence_row.provenance_json),
            }
        )
    elif session_row is not None:
        rows = session.scalars(
            select(SpectraCheckEvidenceRecordORM)
            .where(SpectraCheckEvidenceRecordORM.session_id == session_row.id)
            .order_by(SpectraCheckEvidenceRecordORM.id.asc())
        ).all()
        for row in rows:
            sources.extend(_spectroscopy_sources(session, None, row, None, {}))
    if session_row is not None and session_row.latest_unified_evidence_json:
        sources.append(
            {
                "source_type": "spectracheck_unified_evidence",
                "id": session_row.id,
                "unified_evidence_json": _json_dict(session_row.latest_unified_evidence_json),
            }
        )
    if report_row is not None:
        sources.append(
            {
                "source_type": "spectracheck_report",
                "id": report_row.id,
                "report_json": _json_dict(report_row.report_json),
                "report_sha256": report_row.report_sha256,
            }
        )
    if metadata.get("signals_json") is not None:
        sources.append({"source_type": "request_signals", "signals_json": metadata["signals_json"]})
    return [_public_json(source) for source in sources]


def _extract_regulatory_signals(sources: list[dict[str, Any]]) -> dict[str, Any]:
    signals: dict[str, Any] = {
        "impurity_signals": [],
        "residual_solvent_flags": [],
        "nitrosamine_flags": [],
        "qnmr_output_present": False,
        "method_validation_metadata_present": False,
        "ai_prediction_used": False,
        "qc_warnings": [],
        "unified_evidence_contradictions": [],
        "source_count": len(sources),
    }
    for source in sources:
        _scan_signal_value(source, signals, source_ref=source.get("source_type", "unknown"))
    return signals


def _scan_signal_value(value: Any, signals: dict[str, Any], *, source_ref: str) -> None:
    if isinstance(value, dict):
        lower_keys = {str(key).lower(): key for key in value}
        for key_lower, original_key in lower_keys.items():
            item = value[original_key]
            if key_lower in {
                "impurity_level_percent",
                "observed_level_percent",
                "impurity_percent",
                "impurity_level_pct",
            }:
                level = _as_float(item)
                if level is not None:
                    signals["impurity_signals"].append(
                        {"observed_level_percent": level, "source_ref": source_ref}
                    )
            if key_lower in {"impurity_signals", "impurities", "impurity_candidates"}:
                _append_impurity_signals(item, signals, source_ref)
            if "residual_solvent" in key_lower and _truthy_flag(item):
                signals["residual_solvent_flags"].append(
                    {"source_ref": source_ref, "detail": _public_json(item)}
                )
            if "nitrosamine" in key_lower and _truthy_flag(item):
                signals["nitrosamine_flags"].append(
                    {"source_ref": source_ref, "detail": _public_json(item)}
                )
            if "qnmr" in key_lower and _truthy_flag(item):
                signals["qnmr_output_present"] = True
            if key_lower in {
                "validation_metadata",
                "method_validation_metadata",
                "validation_parameters_json",
                "method_id",
            } and _truthy_flag(item):
                signals["method_validation_metadata_present"] = True
            if (
                (
                    "ai" in key_lower
                    and any(token in key_lower for token in ("used", "generated", "prediction"))
                )
                or key_lower in {"model_version_id", "model_artifact_id", "prediction_run_id"}
            ) and _truthy_flag(item):
                signals["ai_prediction_used"] = True
            if "warning" in key_lower:
                signals["qc_warnings"].extend(_coerce_list(item))
            if "contradiction" in key_lower:
                signals["unified_evidence_contradictions"].extend(_coerce_list(item))
            _scan_signal_value(item, signals, source_ref=source_ref)
    elif isinstance(value, list):
        for item in value:
            _scan_signal_value(item, signals, source_ref=source_ref)


def _append_impurity_signals(value: Any, signals: dict[str, Any], source_ref: str) -> None:
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, dict):
            level = None
            for key in (
                "observed_level_percent",
                "impurity_level_percent",
                "impurity_percent",
                "level_percent",
            ):
                level = _as_float(item.get(key))
                if level is not None:
                    break
            if level is not None:
                signals["impurity_signals"].append(
                    {
                        "observed_level_percent": level,
                        "impurity_name": item.get("impurity_name") or item.get("name"),
                        "source_ref": source_ref,
                    }
                )


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().rstrip("%"))
        except ValueError:
            return None
    return None


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value > 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "none", "no", "0"}
    if isinstance(value, list | dict):
        return bool(value)
    return value is not None


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _active_rule_sets(
    session: Session, dossier: RegulatoryDossierORM
) -> list[RegulatoryRuleSetORM]:
    stmt = select(RegulatoryRuleSetORM).where(RegulatoryRuleSetORM.status == "active")
    if dossier.jurisdiction_id is not None:
        stmt = stmt.where(
            or_(
                RegulatoryRuleSetORM.jurisdiction_id.is_(None),
                RegulatoryRuleSetORM.jurisdiction_id == dossier.jurisdiction_id,
            )
        )
    return list(session.scalars(stmt.order_by(RegulatoryRuleSetORM.id.desc())).all())


def _create_signal_action_items(
    session: Session,
    *,
    dossier: RegulatoryDossierORM,
    evidence_id: int | None,
    compound_id: int | None,
    batch_id: int | None,
    signals: dict[str, Any],
    warnings: list[str],
) -> list[int]:
    action_ids: list[int] = []
    action_ids.extend(
        _create_impurity_actions(
            session,
            dossier=dossier,
            evidence_id=evidence_id,
            compound_id=compound_id,
            batch_id=batch_id,
            impurity_signals=signals.get("impurity_signals", []),
            warnings=warnings,
        )
    )
    for flag in signals.get("residual_solvent_flags", []):
        action_ids.append(
            _create_reg_action_item(
                session,
                dossier_id=dossier.id,
                batch_id=batch_id,
                compound_id=compound_id,
                evidence_link_id=None,
                action_type="residual_solvent_review",
                title="Residual solvent regulatory action item",
                description=(
                    "SpectraCheck evidence includes a residual solvent flag; source-supported "
                    "requirement review is required."
                ),
                severity="warning",
                metadata={"signal": flag, "requires_review": True},
            ).id
        )
    for flag in signals.get("nitrosamine_flags", []):
        action_ids.append(
            _create_reg_action_item(
                session,
                dossier_id=dossier.id,
                batch_id=batch_id,
                compound_id=compound_id,
                evidence_link_id=None,
                action_type="nitrosamine_risk_review",
                title="Nitrosamine review regulatory action item",
                description=(
                    "SpectraCheck evidence includes a nitrosamine-like flag; qualified "
                    "human review is required."
                ),
                severity="high",
                metadata={"signal": flag, "requires_review": True},
            ).id
        )
    if signals.get("qnmr_output_present") and not signals.get("method_validation_metadata_present"):
        action_ids.append(
            _create_reg_action_item(
                session,
                dossier_id=dossier.id,
                batch_id=batch_id,
                compound_id=compound_id,
                evidence_link_id=None,
                action_type="qnmr_validation_gap",
                title="qNMR validation metadata requires review",
                description=(
                    "qNMR output was detected without method validation metadata; qNMR/method "
                    "validation action is required."
                ),
                severity="high",
                metadata={"requires_review": True},
            ).id
        )
    if signals.get("ai_prediction_used") and not _ai_governance_exists(session, dossier.id):
        action_ids.append(
            _create_reg_action_item(
                session,
                dossier_id=dossier.id,
                batch_id=batch_id,
                compound_id=compound_id,
                evidence_link_id=None,
                action_type="ai_governance_gap",
                title="AI governance record required",
                description=(
                    "AI-generated evidence provenance was detected without a linked AI "
                    "governance record; review is required."
                ),
                severity="high",
                metadata={"requires_review": True},
            ).id
        )
    return action_ids


def _create_impurity_actions(
    session: Session,
    *,
    dossier: RegulatoryDossierORM,
    evidence_id: int | None,
    compound_id: int | None,
    batch_id: int | None,
    impurity_signals: list[Any],
    warnings: list[str],
) -> list[int]:
    if not impurity_signals:
        return []
    rule_sets = _active_rule_sets(session, dossier)
    if not rule_sets:
        warnings.append(
            "missing_rule_set: impurity signal found, but no active rule set exists; "
            "possible threshold trigger requires review."
        )
        return []
    rule_set_ids = [row.id for row in rule_sets]
    rules = session.scalars(
        select(ImpurityThresholdRuleORM).where(
            ImpurityThresholdRuleORM.rule_set_id.in_(rule_set_ids)
        )
    ).all()
    reporting = _min_threshold(rules, "reporting")
    identification = _min_threshold(rules, "identification")
    if reporting is None and identification is None:
        warnings.append(
            "missing_rule_set: active rule sets do not define impurity reporting or "
            "identification thresholds."
        )
        return []
    action_ids: list[int] = []
    for signal in impurity_signals:
        level = (
            _as_float(signal.get("observed_level_percent")) if isinstance(signal, dict) else None
        )
        if level is None:
            continue
        if identification is not None and level >= identification:
            action_type = "impurity_identification"
            severity = "high"
            threshold = identification
        elif reporting is not None and level >= reporting:
            action_type = "impurity_reporting"
            severity = "warning"
            threshold = reporting
        else:
            continue
        action_ids.append(
            _create_reg_action_item(
                session,
                dossier_id=dossier.id,
                batch_id=batch_id,
                compound_id=compound_id,
                evidence_link_id=None,
                action_type=action_type,
                title="Impurity possible threshold trigger requires review",
                description=(
                    "Spectroscopy evidence reported an impurity level at or above a configured "
                    "threshold; this is a possible threshold trigger requiring regulatory review."
                ),
                severity=severity,
                metadata={
                    "observed_level_percent": level,
                    "threshold_percent": threshold,
                    "signal": signal,
                    "spectracheck_evidence_item_id": evidence_id,
                    "requires_review": True,
                },
            ).id
        )
    return action_ids


def _min_threshold(rules: Any, rule_type: str) -> float | None:
    values = [
        row.threshold_percent
        for row in rules
        if row.rule_type == rule_type and row.threshold_percent is not None
    ]
    return min(values) if values else None


def _ai_governance_exists(session: Session, dossier_id: int) -> bool:
    return (
        session.scalar(
            select(AIGovernanceRecordORM.id)
            .where(AIGovernanceRecordORM.dossier_id == dossier_id)
            .limit(1)
        )
        is not None
    )


def _create_reg_action_item(
    session: Session,
    *,
    dossier_id: int,
    batch_id: int | None,
    compound_id: int | None,
    evidence_link_id: int | None,
    action_type: str,
    title: str,
    description: str,
    severity: str,
    metadata: dict[str, Any],
) -> RegulatoryActionItemORM:
    row = RegulatoryActionItemORM(
        dossier_id=dossier_id,
        batch_id=batch_id,
        compound_id=compound_id,
        evidence_link_id=evidence_link_id,
        requirement_id=None,
        action_type=action_type,
        title=title,
        description=description,
        severity=severity,
        status="open",
        citation_ids_json=_json_dump([]),
        metadata_json=_json_dump(metadata),
    )
    session.add(row)
    session.flush()
    return row


def _regulatory_action_rows(
    session: Session,
    payload: RegulatoryToReactionBridgeCreate,
    owner_scope_id: int | None = None,
) -> list[RegulatoryActionItemORM]:
    if payload.regulatory_action_item_id is not None:
        action = _required(
            session,
            RegulatoryActionItemORM,
            payload.regulatory_action_item_id,
            "Regulatory action item",
        )
        # The action item's content is reflected into the reaction-side constraint, so a
        # user-scoped caller may reference it only if they own its parent dossier.
        if not _dossier_owned_by(session, action.dossier_id, owner_scope_id):
            raise ProductOrchestrationNotFoundError("Regulatory action item not found.")
        return [action]
    if payload.dossier_id is None:
        return []
    if not _dossier_owned_by(session, payload.dossier_id, owner_scope_id):
        raise ProductOrchestrationNotFoundError("Regulatory dossier not found.")
    return list(
        session.scalars(
            select(RegulatoryActionItemORM)
            .where(RegulatoryActionItemORM.dossier_id == payload.dossier_id)
            .where(RegulatoryActionItemORM.status.in_(["open", "in_progress", "deferred"]))
            .order_by(RegulatoryActionItemORM.id.asc())
        ).all()
    )


def _resolve_r2r_dossier(
    session: Session,
    payload: RegulatoryToReactionBridgeCreate,
    action_rows: list[RegulatoryActionItemORM],
    owner_scope_id: int | None = None,
) -> RegulatoryDossierORM | None:
    if payload.dossier_id is not None:
        dossier = _required(session, RegulatoryDossierORM, payload.dossier_id, "Regulatory dossier")
        if not _dossier_owned_by(session, dossier.id, owner_scope_id):
            raise ProductOrchestrationNotFoundError("Regulatory dossier not found.")
        return dossier
    for action in action_rows:
        if action.dossier_id is not None:
            return session.get(RegulatoryDossierORM, action.dossier_id)
    return None


def _constraint_type_for_action(action_type: str) -> str:
    if action_type.startswith("impurity"):
        return "impurity_limit"
    if action_type == "residual_solvent_review":
        return "residual_solvent_limit"
    if action_type == "nitrosamine_risk_review":
        return "nitrosamine_risk_avoidance"
    if action_type == "qnmr_validation_gap":
        return "qnmr_validation_requirement"
    if action_type == "ai_governance_gap":
        return "ai_governance_requirement"
    if action_type == "jurisdictional_review":
        return "jurisdictional_requirement"
    return "other"


def _compliance_objective_payload(constraints: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "objective_json": {
            "yield_selectivity_goal": "maximize reviewed yield/selectivity evidence",
            "compliance_driven_optimization_constraint": True,
            "review_required": True,
        },
        "scalarization_json": {
            "yield_weight": 1.0,
            "selectivity_weight": 0.5,
            "impurity_penalty_weight": 1.0,
            "residual_solvent_penalty_weight": 0.7,
            "nitrosamine_risk_penalty_weight": 1.0,
        },
        "hard_constraints_json": {
            "compliance_block_conditions": [
                "critical regulatory constraint unresolved",
                "nitrosamine risk review unresolved",
            ],
            "constraint_ids": [
                item.get("constraint_id") for item in constraints if item.get("constraint_id")
            ],
            "requires_review": True,
        },
        "soft_constraints_json": {
            "review_required_flags": [
                "low confidence evidence",
                "missing citation",
                "draft constraint",
            ],
            "constraint_types": [item.get("constraint_type") for item in constraints],
        },
    }


def _build_ctd_report_json(
    session: Session,
    dossier: RegulatoryDossierORM,
    payload: CTDModule3ReportBundleCreate,
) -> dict[str, Any]:
    report = _optional(session, SpectraCheckReportRecordORM, payload.spectracheck_report_id)
    readiness = _optional(
        session, RegulatoryReadinessReportORM, payload.regulatory_readiness_report_id
    )
    batch = _optional(session, BatchRegulatoryAssessmentORM, payload.batch_assessment_id)
    qnmr = _optional(session, QNMRComplianceProfileORM, payload.qnmr_compliance_id)
    impurity = _optional(session, ImpurityRiskRegisterORM, payload.impurity_register_id)
    ai_governance = _optional(session, AIGovernanceRecordORM, payload.ai_governance_record_id)
    action_items = session.scalars(
        select(RegulatoryActionItemORM)
        .where(RegulatoryActionItemORM.dossier_id == dossier.id)
        .order_by(RegulatoryActionItemORM.id.asc())
    ).all()
    requirements = session.scalars(
        select(RegulatoryRequirementORM)
        .where(RegulatoryRequirementORM.dossier_id == dossier.id)
        .order_by(RegulatoryRequirementORM.id.asc())
    ).all()
    citation_ids: set[int] = set()
    for item in list(action_items) + list(requirements):
        citation_ids.update(_json_int_list(getattr(item, "citation_ids_json", "[]")))
    return {
        "bundle_type": "draft CTD Module 3 bundle",
        "dossier": {
            "id": dossier.id,
            "title": dossier.title,
            "status": dossier.status,
        },
        "analytical_evidence_summary": _public_json(
            _json_dict(report.report_json) if report else {}
        ),
        "impurity_register": _public_json(_json_dict(impurity.metadata_json) if impurity else {}),
        "residual_solvent_assessment": _public_json(
            _json_dict(batch.residual_solvent_summary_json) if batch else {}
        ),
        "nitrosamine_watch_summary": _public_json(
            _json_dict(batch.nitrosamine_summary_json) if batch else {}
        ),
        "qnmr_method_validation_summary": _public_json(
            _json_dict(qnmr.validation_parameters_json) if qnmr else {}
        ),
        "ai_governance_summary": _public_json(
            _json_dict(ai_governance.explainability_summary_json) if ai_governance else {}
        ),
        "regulatory_readiness_summary": _public_json(
            _json_dict(readiness.summary_json) if readiness else {}
        ),
        "source_citations": sorted(citation_ids),
        "human_review_status": {
            "human_review_required": True,
            "requires_review": True,
            "status": "requires review",
        },
        "provenance_hashes": {
            "spectracheck_report_sha256": report.report_sha256 if report else None,
            "regulatory_readiness_report_id": readiness.id if readiness else None,
            "action_item_ids": [item.id for item in action_items],
            "requirement_ids": [item.id for item in requirements],
        },
        "notes": [_PRODUCT_RULE_NOTE, _REVIEW_NOTE],
    }


def _ctd_html(report_json: dict[str, Any]) -> str:
    title = str(report_json.get("bundle_type", "draft CTD Module 3 bundle"))
    return (
        "<article><h1>"
        + title
        + (
            "</h1><p>Draft bundle assembled for human review. "
            "It is not a legal approval.</p></article>"
        )
    )


def _create_cross_action_row(
    session: Session,
    *,
    source_program: str,
    target_program: str,
    source_resource_type: str,
    source_resource_id: int,
    target_resource_type: str | None = None,
    target_resource_id: int | None = None,
    action_type: str = "other",
    title: str,
    description: str,
    severity: str = "warning",
    status: str = "open",
    metadata: dict[str, Any] | None = None,
) -> CrossModuleActionItemORM:
    row = CrossModuleActionItemORM(
        source_program=source_program,
        target_program=target_program,
        source_resource_type=source_resource_type,
        source_resource_id=source_resource_id,
        target_resource_type=target_resource_type,
        target_resource_id=target_resource_id,
        action_type=action_type,
        title=title,
        description=description,
        severity=severity,
        status=status,
        metadata_json=_json_dump(metadata or {}),
    )
    session.add(row)
    session.flush()
    return row


def _spectracheck_summary(session: Session, scope: str, scope_id: int | None) -> dict[str, Any]:
    stmt = select(SpectraCheckSessionORM)
    if scope == "project" and scope_id is not None:
        stmt = stmt.where(SpectraCheckSessionORM.project_id == scope_id)
    if scope == "sample" and scope_id is not None:
        stmt = stmt.where(SpectraCheckSessionORM.sample_pk == scope_id)
    rows = session.scalars(stmt).all()
    return {
        "program_key": "spectracheck",
        "display_order": 1,
        "session_count": len(rows),
        "review_required_count": sum(1 for row in rows if row.status == "review_required"),
    }


def _regulatory_summary(session: Session, scope: str, scope_id: int | None) -> dict[str, Any]:
    dossier_stmt = select(RegulatoryDossierORM)
    action_stmt = select(RegulatoryActionItemORM)
    if scope == "project" and scope_id is not None:
        dossier_stmt = dossier_stmt.where(RegulatoryDossierORM.project_id == scope_id)
    if scope == "compound" and scope_id is not None:
        action_stmt = action_stmt.where(RegulatoryActionItemORM.compound_id == scope_id)
    if scope == "batch" and scope_id is not None:
        action_stmt = action_stmt.where(RegulatoryActionItemORM.batch_id == scope_id)
    dossiers = session.scalars(dossier_stmt).all()
    actions = session.scalars(action_stmt).all()
    return {
        "program_key": "regulatory_hub",
        "display_order": 2,
        "dossier_count": len(dossiers),
        "open_regulatory_action_item_count": sum(1 for row in actions if row.status == "open"),
    }


def _reaction_summary(session: Session, scope: str, scope_id: int | None) -> dict[str, Any]:
    project_stmt = select(ReactionProjectORM)
    constraint_stmt = select(RegulatoryConstraintSetORM)
    if scope == "project" and scope_id is not None:
        project_stmt = project_stmt.where(ReactionProjectORM.id == scope_id)
        constraint_stmt = constraint_stmt.where(
            RegulatoryConstraintSetORM.reaction_project_id == scope_id
        )
    projects = session.scalars(project_stmt).all()
    constraints = session.scalars(constraint_stmt).all()
    return {
        "program_key": "reaction_optimization",
        "display_order": 3,
        "reaction_project_count": len(projects),
        "compliance_constraint_count": len(constraints),
    }


def _open_cross_actions(session: Session, scope: str, scope_id: int | None) -> list[dict[str, Any]]:
    stmt = (
        select(CrossModuleActionItemORM)
        .where(CrossModuleActionItemORM.status.in_(["open", "in_progress", "blocked"]))
        .order_by(CrossModuleActionItemORM.id.desc())
        .limit(100)
    )
    rows = session.scalars(stmt).all()
    output = []
    for row in rows:
        if scope != "global" and scope_id is not None:
            metadata = _json_dict(row.metadata_json)
            if metadata.get(f"{scope}_id") not in {scope_id, str(scope_id), None}:
                continue
        output.append(
            {
                "id": row.id,
                "source_program": row.source_program,
                "target_program": row.target_program,
                "action_type": row.action_type,
                "title": row.title,
                "severity": row.severity,
                "status": row.status,
            }
        )
    return output


def _program_to_record(row: ProductProgramRegistryORM) -> ProductProgramRegistry:
    return ProductProgramRegistry(
        id=row.id,
        program_key=row.program_key,  # type: ignore[arg-type]
        display_name=row.display_name,
        display_order=row.display_order,
        description=row.description,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _priority_to_record(row: ModulePriorityMapORM) -> ModulePriorityMap:
    return ModulePriorityMap(
        id=row.id,
        context=row.context,  # type: ignore[arg-type]
        program_order_json=_json_list(row.program_order_json),  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _workflow_to_record(row: CrossModuleWorkflowTemplateORM) -> CrossModuleWorkflowTemplate:
    return CrossModuleWorkflowTemplate(
        id=row.id,
        template_key=row.template_key,
        name=row.name,
        description=row.description,
        program_sequence_json=_json_list(row.program_sequence_json),  # type: ignore[arg-type]
        trigger_type=row.trigger_type,  # type: ignore[arg-type]
        required_inputs_json=_json_dict(row.required_inputs_json),
        optional_inputs_json=_json_dict(row.optional_inputs_json),
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _s2r_to_record(row: SpectroscopyToRegulatoryBridgeORM) -> SpectroscopyToRegulatoryBridge:
    return SpectroscopyToRegulatoryBridge(
        id=row.id,
        spectracheck_session_id=row.spectracheck_session_id,
        evidence_item_id=row.evidence_item_id,
        report_id=row.report_id,
        dossier_id=row.dossier_id,
        compound_id=row.compound_id,
        batch_id=row.batch_id,
        bridge_status=row.bridge_status,  # type: ignore[arg-type]
        extracted_regulatory_signals_json=_json_dict(row.extracted_regulatory_signals_json),
        created_requirement_ids_json=_json_int_list(row.created_requirement_ids_json),
        created_action_item_ids_json=_json_int_list(row.created_action_item_ids_json),
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        human_review_required=row.human_review_required,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _r2r_to_record(row: RegulatoryToReactionBridgeORM) -> RegulatoryToReactionBridge:
    return RegulatoryToReactionBridge(
        id=row.id,
        dossier_id=row.dossier_id,
        regulatory_action_item_id=row.regulatory_action_item_id,
        reaction_project_id=row.reaction_project_id,
        compound_id=row.compound_id,
        batch_id=row.batch_id,
        bridge_status=row.bridge_status,  # type: ignore[arg-type]
        regulatory_constraints_json=_json_list(row.regulatory_constraints_json),  # type: ignore[arg-type]
        optimization_objectives_json=_json_dict(row.optimization_objectives_json),
        created_constraint_ids_json=_json_int_list(row.created_constraint_ids_json),
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        human_review_required=row.human_review_required,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _constraint_to_record(row: RegulatoryConstraintSetORM) -> RegulatoryConstraintSet:
    return RegulatoryConstraintSet(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        dossier_id=row.dossier_id,
        source_action_item_ids_json=_json_int_list(row.source_action_item_ids_json),
        constraint_type=row.constraint_type,  # type: ignore[arg-type]
        constraint_json=_json_dict(row.constraint_json),
        severity=row.severity,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _objective_to_record(
    row: ComplianceDrivenOptimizationObjectiveORM,
) -> ComplianceDrivenOptimizationObjective:
    return ComplianceDrivenOptimizationObjective(
        id=row.id,
        reaction_project_id=row.reaction_project_id,
        regulatory_constraint_set_id=row.regulatory_constraint_set_id,
        objective_json=_json_dict(row.objective_json),
        scalarization_json=_json_dict(row.scalarization_json),
        hard_constraints_json=_json_dict(row.hard_constraints_json),
        soft_constraints_json=_json_dict(row.soft_constraints_json),
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _ctd_to_record(row: CTDModule3ReportBundleORM) -> CTDModule3ReportBundle:
    return CTDModule3ReportBundle(
        id=row.id,
        dossier_id=row.dossier_id,
        spectracheck_report_id=row.spectracheck_report_id,
        regulatory_readiness_report_id=row.regulatory_readiness_report_id,
        batch_assessment_id=row.batch_assessment_id,
        qnmr_compliance_id=row.qnmr_compliance_id,
        impurity_register_id=row.impurity_register_id,
        ai_governance_record_id=row.ai_governance_record_id,
        report_json=_json_dict(row.report_json),
        report_html=row.report_html,
        report_sha256=row.report_sha256,
        status=row.status,  # type: ignore[arg-type]
        human_review_required=row.human_review_required,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _cross_action_to_record(row: CrossModuleActionItemORM) -> CrossModuleActionItem:
    return CrossModuleActionItem(
        id=row.id,
        source_program=row.source_program,  # type: ignore[arg-type]
        target_program=row.target_program,  # type: ignore[arg-type]
        source_resource_type=row.source_resource_type,
        source_resource_id=row.source_resource_id,
        target_resource_type=row.target_resource_type,
        target_resource_id=row.target_resource_id,
        action_type=row.action_type,  # type: ignore[arg-type]
        title=row.title,
        description=row.description,
        severity=row.severity,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _summary_to_record(row: CrossModuleCommandCenterSummaryORM) -> CrossModuleCommandCenterSummary:
    return CrossModuleCommandCenterSummary(
        id=row.id,
        scope=row.scope,  # type: ignore[arg-type]
        scope_id=row.scope_id,
        spectracheck_summary_json=_json_dict(row.spectracheck_summary_json),
        regulatory_summary_json=_json_dict(row.regulatory_summary_json),
        reaction_summary_json=_json_dict(row.reaction_summary_json),
        open_cross_module_actions_json=_json_list(row.open_cross_module_actions_json),  # type: ignore[arg-type]
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )
