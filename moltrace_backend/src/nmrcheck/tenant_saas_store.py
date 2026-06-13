from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    CustomerOnboardingProject,
    CustomerOnboardingProjectCreate,
    CustomerOnboardingProjectUpdate,
    CustomerSuccessHealthScore,
    FeatureFlag,
    FeatureFlagCreate,
    FeatureFlagUpdate,
    ImplementationTask,
    ImplementationTaskCreate,
    ImplementationTaskUpdate,
    PilotProgram,
    PilotProgramCreate,
    PilotProgramUpdate,
    ProcurementEvidencePackage,
    ProcurementEvidencePackageCreate,
    SubscriptionPlan,
    SubscriptionPlanCreate,
    Tenant,
    TenantAuditExport,
    TenantAuditExportCreate,
    TenantDataBoundary,
    TenantDataBoundaryCreate,
    TenantDataBoundaryUpdate,
    TenantEntitlement,
    TenantEntitlementCreate,
    TenantEntitlementUpdate,
    TenantEnvironment,
    TenantEnvironmentCreate,
    TenantEnvironmentUpdate,
    TenantGoLiveReadiness,
    TenantModuleReadiness,
    TenantRoiSnapshot,
    TenantSecurityProfile,
    TenantSecurityProfileCreate,
    TenantSecurityProfileUpdate,
    TenantUpdate,
    TenantUsageSummary,
    TenantValidationProfile,
    TenantValidationProfileCreate,
    TenantValidationProfileUpdate,
    TenantCreate,
)
from .orm import (
    AuditEventORM,
    CustomerOnboardingProjectORM,
    CustomerSuccessHealthScoreORM,
    FeatureFlagORM,
    ImplementationTaskORM,
    PilotProgramORM,
    ProcurementEvidencePackageORM,
    SubscriptionPlanORM,
    TenantAuditExportORM,
    TenantDataBoundaryORM,
    TenantEntitlementORM,
    TenantEnvironmentORM,
    TenantORM,
    TenantRoiSnapshotORM,
    TenantSecurityProfileORM,
    TenantUsageSummaryORM,
    TenantValidationProfileORM,
    utcnow,
)


class TenantSaaSError(ValueError):
    pass


class TenantNotFoundError(TenantSaaSError):
    pass


class TenantIsolationError(PermissionError):
    pass


DEFAULT_PRODUCT_ORDER = ["SpectraCheck", "ComplianceCore", "Reaction Optimization"]
DEFAULT_PRODUCT_KEYS = ["spectracheck", "regulatory_hub", "reaction_optimization"]
SENSITIVE_KEY_MARKERS = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "credential",
    "raw_spectrum",
    "raw_spectra",
    "full_smiles",
    "source_text",
    "source_document",
    "document_text",
    "model_artifact",
    "private_key",
)


def _json_dump(value: Any, *, default: Any) -> str:
    return json.dumps(_safe_json(default if value is None else value), sort_keys=True, separators=(",", ":"))


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return _safe_json(parsed) if isinstance(parsed, dict) else {}


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return _safe_json(parsed) if isinstance(parsed, list) else []


def _safe_json(value: Any, key: str = "") -> Any:
    if any(marker in key.lower() for marker in SENSITIVE_KEY_MARKERS):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _safe_json(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json(item, key) for item in value]
    return value


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_json_dump(value, default={}).encode("utf-8")).hexdigest()


def ensure_tenant_scope(
    requested_tenant_id: int,
    actual_tenant_id: int,
    *,
    is_internal_super_admin: bool = False,
) -> None:
    if requested_tenant_id != actual_tenant_id and not is_internal_super_admin:
        raise TenantIsolationError("Cross-tenant access is blocked by tenant isolation policy.")


def _require_tenant(session: Session, tenant_id: int) -> TenantORM:
    row = session.get(TenantORM, tenant_id)
    if row is None:
        raise TenantNotFoundError("Tenant not found.")
    return row


def _tenant_to_record(row: TenantORM) -> Tenant:
    return Tenant(
        id=row.id,
        tenant_key=row.tenant_key,
        display_name=row.display_name,
        tenant_type=row.tenant_type,
        status=row.status,
        primary_contact_email=row.primary_contact_email,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _environment_to_record(row: TenantEnvironmentORM) -> TenantEnvironment:
    return TenantEnvironment(
        id=row.id,
        tenant_id=row.tenant_id,
        environment_type=row.environment_type,
        base_url=row.base_url,
        status=row.status,
        data_retention_policy_id=row.data_retention_policy_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _plan_to_record(row: SubscriptionPlanORM) -> SubscriptionPlan:
    return SubscriptionPlan(
        id=row.id,
        plan_key=row.plan_key,
        display_name=row.display_name,
        description=row.description,
        default_entitlements_json=_json_dict(row.default_entitlements_json),
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _entitlement_to_record(row: TenantEntitlementORM) -> TenantEntitlement:
    return TenantEntitlement(
        id=row.id,
        tenant_id=row.tenant_id,
        plan_id=row.plan_id,
        feature_key=row.feature_key,
        program=row.program,
        enabled=row.enabled,
        limit_json=_json_dict(row.limit_json),
        effective_start=row.effective_start,
        effective_end=row.effective_end,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _feature_flag_to_record(row: FeatureFlagORM) -> FeatureFlag:
    return FeatureFlag(
        id=row.id,
        flag_key=row.flag_key,
        display_name=row.display_name,
        description=row.description,
        program=row.program,
        default_enabled=row.default_enabled,
        rollout_rules_json=_json_dict(row.rollout_rules_json),
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _pilot_to_record(row: PilotProgramORM) -> PilotProgram:
    return PilotProgram(
        id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        objective=row.objective,
        status=row.status,
        start_date=row.start_date,
        end_date=row.end_date,
        target_programs_json=[str(item) for item in _json_list(row.target_programs_json)],
        success_criteria_json=[item for item in _json_list(row.success_criteria_json) if isinstance(item, dict)],
        risks_json=[item for item in _json_list(row.risks_json) if isinstance(item, dict)],
        notes_json=_json_dict(row.notes_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _onboarding_to_record(row: CustomerOnboardingProjectORM) -> CustomerOnboardingProject:
    return CustomerOnboardingProject(
        id=row.id,
        tenant_id=row.tenant_id,
        pilot_program_id=row.pilot_program_id,
        title=row.title,
        status=row.status,
        owner_name=row.owner_name,
        customer_contact=row.customer_contact,
        implementation_stage=row.implementation_stage,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _task_to_record(row: ImplementationTaskORM) -> ImplementationTask:
    return ImplementationTask(
        id=row.id,
        onboarding_project_id=row.onboarding_project_id,
        title=row.title,
        description=row.description,
        task_type=row.task_type,
        program=row.program,
        status=row.status,
        owner=row.owner,
        due_date=row.due_date,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _boundary_to_record(row: TenantDataBoundaryORM) -> TenantDataBoundary:
    return TenantDataBoundary(
        id=row.id,
        tenant_id=row.tenant_id,
        isolation_mode=row.isolation_mode,
        encryption_profile=row.encryption_profile,
        storage_prefix=row.storage_prefix,
        allowed_regions_json=[str(item) for item in _json_list(row.allowed_regions_json)],
        data_residency_notes=row.data_residency_notes,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _security_to_record(row: TenantSecurityProfileORM) -> TenantSecurityProfile:
    return TenantSecurityProfile(
        id=row.id,
        tenant_id=row.tenant_id,
        sso_enabled=row.sso_enabled,
        mfa_required=row.mfa_required,
        allowed_domains_json=[str(item) for item in _json_list(row.allowed_domains_json)],
        session_timeout_minutes=row.session_timeout_minutes,
        ip_allowlist_json=[str(item) for item in _json_list(row.ip_allowlist_json)],
        security_frameworks_json=[str(item) for item in _json_list(row.security_frameworks_json)],
        risk_summary_json=_json_dict(row.risk_summary_json),
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _validation_to_record(row: TenantValidationProfileORM) -> TenantValidationProfile:
    return TenantValidationProfile(
        id=row.id,
        tenant_id=row.tenant_id,
        validation_required=row.validation_required,
        validation_project_ids_json=[int(item) for item in _json_list(row.validation_project_ids_json) if isinstance(item, int)],
        controlled_record_policy=row.controlled_record_policy,
        esignature_required=row.esignature_required,
        data_integrity_assessment_ids_json=[
            int(item) for item in _json_list(row.data_integrity_assessment_ids_json) if isinstance(item, int)
        ],
        inspection_package_ids_json=[
            int(item) for item in _json_list(row.inspection_package_ids_json) if isinstance(item, int)
        ],
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _usage_to_record(row: TenantUsageSummaryORM) -> TenantUsageSummary:
    return TenantUsageSummary(
        id=row.id,
        tenant_id=row.tenant_id,
        period_start=row.period_start,
        period_end=row.period_end,
        spectracheck_usage_json=_json_dict(row.spectracheck_usage_json),
        regulatory_usage_json=_json_dict(row.regulatory_usage_json),
        reaction_usage_json=_json_dict(row.reaction_usage_json),
        reports_generated=row.reports_generated,
        actions_completed=row.actions_completed,
        hours_saved=row.hours_saved,
        warnings_json=[item for item in _json_list(row.warnings_json) if isinstance(item, dict)],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _roi_to_record(row: TenantRoiSnapshotORM) -> TenantRoiSnapshot:
    return TenantRoiSnapshot(
        id=row.id,
        tenant_id=row.tenant_id,
        period_start=row.period_start,
        period_end=row.period_end,
        total_hours_saved=row.total_hours_saved,
        tasks_automated=row.tasks_automated,
        reports_generated=row.reports_generated,
        regulatory_actions_created=row.regulatory_actions_created,
        reaction_recommendations_approved=row.reaction_recommendations_approved,
        renewal_summary_json=_json_dict(row.renewal_summary_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _health_to_record(row: CustomerSuccessHealthScoreORM) -> CustomerSuccessHealthScore:
    return CustomerSuccessHealthScore(
        id=row.id,
        tenant_id=row.tenant_id,
        score=row.score,
        status=row.status,
        usage_summary_json=_json_dict(row.usage_summary_json),
        onboarding_summary_json=_json_dict(row.onboarding_summary_json),
        support_summary_json=_json_dict(row.support_summary_json),
        roi_summary_json=_json_dict(row.roi_summary_json),
        blockers_json=[item for item in _json_list(row.blockers_json) if isinstance(item, dict)],
        recommended_actions_json=[item for item in _json_list(row.recommended_actions_json) if isinstance(item, dict)],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _procurement_to_record(row: ProcurementEvidencePackageORM) -> ProcurementEvidencePackage:
    return ProcurementEvidencePackage(
        id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        package_type=row.package_type,
        status=row.status,
        package_json=_json_dict(row.package_json),
        package_html=row.package_html,
        package_sha256=row.package_sha256,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _audit_export_to_record(row: TenantAuditExportORM) -> TenantAuditExport:
    return TenantAuditExport(
        id=row.id,
        tenant_id=row.tenant_id,
        export_scope=row.export_scope,
        status=row.status,
        export_sha256=row.export_sha256,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _apply_updates(row: Any, payload: Any, fields: tuple[str, ...]) -> None:
    for field in fields:
        if field not in payload.model_fields_set:
            continue
        value = getattr(payload, field)
        if field.endswith("_json"):
            setattr(row, field, _json_dump(value, default=[] if isinstance(value, list) else {}))
        else:
            setattr(row, field, value)


def create_tenant(session_factory: sessionmaker[Session], payload: TenantCreate) -> Tenant:
    with session_scope(session_factory) as session:
        row = TenantORM(
            tenant_key=payload.tenant_key,
            display_name=payload.display_name,
            tenant_type=payload.tenant_type,
            status=payload.status,
            primary_contact_email=payload.primary_contact_email,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _tenant_to_record(row)


def list_tenants(
    session_factory: sessionmaker[Session],
    *,
    status_filter: str | None = None,
    limit: int = 200,
) -> list[Tenant]:
    with session_scope(session_factory) as session:
        stmt = select(TenantORM).order_by(TenantORM.created_at.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(TenantORM.status == status_filter)
        return [_tenant_to_record(row) for row in session.scalars(stmt)]


def get_tenant(session_factory: sessionmaker[Session], tenant_id: int) -> Tenant | None:
    with session_scope(session_factory) as session:
        row = session.get(TenantORM, tenant_id)
        return _tenant_to_record(row) if row else None


def update_tenant(session_factory: sessionmaker[Session], tenant_id: int, payload: TenantUpdate) -> Tenant | None:
    with session_scope(session_factory) as session:
        row = session.get(TenantORM, tenant_id)
        if row is None:
            return None
        _apply_updates(
            row,
            payload,
            ("tenant_key", "display_name", "tenant_type", "status", "primary_contact_email", "metadata_json"),
        )
        row.updated_at = utcnow()
        session.flush()
        return _tenant_to_record(row)


def create_environment(
    session_factory: sessionmaker[Session],
    tenant_id: int,
    payload: TenantEnvironmentCreate,
) -> TenantEnvironment:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        row = TenantEnvironmentORM(
            tenant_id=tenant_id,
            environment_type=payload.environment_type,
            base_url=payload.base_url,
            status=payload.status,
            data_retention_policy_id=payload.data_retention_policy_id,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _environment_to_record(row)


def list_environments(session_factory: sessionmaker[Session], tenant_id: int) -> list[TenantEnvironment]:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        stmt = select(TenantEnvironmentORM).where(TenantEnvironmentORM.tenant_id == tenant_id).order_by(TenantEnvironmentORM.created_at.desc())
        return [_environment_to_record(row) for row in session.scalars(stmt)]


def update_environment(
    session_factory: sessionmaker[Session],
    environment_id: int,
    payload: TenantEnvironmentUpdate,
    *,
    requested_tenant_id: int | None = None,
    is_internal_super_admin: bool = False,
) -> TenantEnvironment | None:
    with session_scope(session_factory) as session:
        row = session.get(TenantEnvironmentORM, environment_id)
        if row is None:
            return None
        if requested_tenant_id is not None:
            ensure_tenant_scope(requested_tenant_id, row.tenant_id, is_internal_super_admin=is_internal_super_admin)
        _apply_updates(row, payload, ("environment_type", "base_url", "status", "data_retention_policy_id", "metadata_json"))
        row.updated_at = utcnow()
        session.flush()
        return _environment_to_record(row)


def create_subscription_plan(session_factory: sessionmaker[Session], payload: SubscriptionPlanCreate) -> SubscriptionPlan:
    with session_scope(session_factory) as session:
        row = SubscriptionPlanORM(
            plan_key=payload.plan_key,
            display_name=payload.display_name,
            description=payload.description,
            default_entitlements_json=_json_dump(payload.default_entitlements_json, default={}),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _plan_to_record(row)


def list_subscription_plans(session_factory: sessionmaker[Session], *, limit: int = 200) -> list[SubscriptionPlan]:
    with session_scope(session_factory) as session:
        stmt = select(SubscriptionPlanORM).order_by(SubscriptionPlanORM.created_at.desc()).limit(limit)
        return [_plan_to_record(row) for row in session.scalars(stmt)]


def get_subscription_plan(session_factory: sessionmaker[Session], plan_id: int) -> SubscriptionPlan | None:
    with session_scope(session_factory) as session:
        row = session.get(SubscriptionPlanORM, plan_id)
        return _plan_to_record(row) if row else None


def create_entitlement(
    session_factory: sessionmaker[Session],
    tenant_id: int,
    payload: TenantEntitlementCreate,
) -> TenantEntitlement:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        if payload.plan_id is not None and session.get(SubscriptionPlanORM, payload.plan_id) is None:
            raise TenantSaaSError("Subscription plan not found.")
        row = TenantEntitlementORM(
            tenant_id=tenant_id,
            plan_id=payload.plan_id,
            feature_key=payload.feature_key,
            program=payload.program,
            enabled=payload.enabled,
            limit_json=_json_dump(payload.limit_json, default={}),
            effective_start=payload.effective_start,
            effective_end=payload.effective_end,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _entitlement_to_record(row)


def list_entitlements(session_factory: sessionmaker[Session], tenant_id: int) -> list[TenantEntitlement]:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        stmt = select(TenantEntitlementORM).where(TenantEntitlementORM.tenant_id == tenant_id).order_by(TenantEntitlementORM.created_at.desc())
        return [_entitlement_to_record(row) for row in session.scalars(stmt)]


def update_entitlement(
    session_factory: sessionmaker[Session],
    entitlement_id: int,
    payload: TenantEntitlementUpdate,
    *,
    requested_tenant_id: int | None = None,
    is_internal_super_admin: bool = False,
) -> TenantEntitlement | None:
    with session_scope(session_factory) as session:
        row = session.get(TenantEntitlementORM, entitlement_id)
        if row is None:
            return None
        if requested_tenant_id is not None:
            ensure_tenant_scope(requested_tenant_id, row.tenant_id, is_internal_super_admin=is_internal_super_admin)
        _apply_updates(
            row,
            payload,
            ("plan_id", "feature_key", "program", "enabled", "limit_json", "effective_start", "effective_end", "metadata_json"),
        )
        row.updated_at = utcnow()
        session.flush()
        return _entitlement_to_record(row)


def create_feature_flag(session_factory: sessionmaker[Session], payload: FeatureFlagCreate) -> FeatureFlag:
    with session_scope(session_factory) as session:
        row = FeatureFlagORM(
            flag_key=payload.flag_key,
            display_name=payload.display_name,
            description=payload.description,
            program=payload.program,
            default_enabled=payload.default_enabled,
            rollout_rules_json=_json_dump(payload.rollout_rules_json, default={}),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _feature_flag_to_record(row)


def list_feature_flags(session_factory: sessionmaker[Session], *, limit: int = 200) -> list[FeatureFlag]:
    with session_scope(session_factory) as session:
        stmt = select(FeatureFlagORM).order_by(FeatureFlagORM.created_at.desc()).limit(limit)
        return [_feature_flag_to_record(row) for row in session.scalars(stmt)]


def get_feature_flag(session_factory: sessionmaker[Session], flag_id: int) -> FeatureFlag | None:
    with session_scope(session_factory) as session:
        row = session.get(FeatureFlagORM, flag_id)
        return _feature_flag_to_record(row) if row else None


def update_feature_flag(session_factory: sessionmaker[Session], flag_id: int, payload: FeatureFlagUpdate) -> FeatureFlag | None:
    with session_scope(session_factory) as session:
        row = session.get(FeatureFlagORM, flag_id)
        if row is None:
            return None
        _apply_updates(
            row,
            payload,
            ("flag_key", "display_name", "description", "program", "default_enabled", "rollout_rules_json", "status", "metadata_json"),
        )
        row.updated_at = utcnow()
        session.flush()
        return _feature_flag_to_record(row)


def create_pilot_program(
    session_factory: sessionmaker[Session],
    tenant_id: int,
    payload: PilotProgramCreate,
) -> PilotProgram:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        row = PilotProgramORM(
            tenant_id=tenant_id,
            title=payload.title,
            objective=payload.objective,
            status=payload.status,
            start_date=payload.start_date,
            end_date=payload.end_date,
            target_programs_json=_json_dump(payload.target_programs_json or DEFAULT_PRODUCT_KEYS, default=[]),
            success_criteria_json=_json_dump(payload.success_criteria_json, default=[]),
            risks_json=_json_dump(payload.risks_json, default=[]),
            notes_json=_json_dump(payload.notes_json, default={}),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _pilot_to_record(row)


def list_pilot_programs(session_factory: sessionmaker[Session], tenant_id: int) -> list[PilotProgram]:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        stmt = select(PilotProgramORM).where(PilotProgramORM.tenant_id == tenant_id).order_by(PilotProgramORM.created_at.desc())
        return [_pilot_to_record(row) for row in session.scalars(stmt)]


def get_pilot_program(session_factory: sessionmaker[Session], pilot_id: int) -> PilotProgram | None:
    with session_scope(session_factory) as session:
        row = session.get(PilotProgramORM, pilot_id)
        return _pilot_to_record(row) if row else None


def update_pilot_program(session_factory: sessionmaker[Session], pilot_id: int, payload: PilotProgramUpdate) -> PilotProgram | None:
    with session_scope(session_factory) as session:
        row = session.get(PilotProgramORM, pilot_id)
        if row is None:
            return None
        _apply_updates(
            row,
            payload,
            ("title", "objective", "status", "start_date", "end_date", "target_programs_json", "success_criteria_json", "risks_json", "notes_json", "metadata_json"),
        )
        row.updated_at = utcnow()
        session.flush()
        return _pilot_to_record(row)


def _seed_default_onboarding_tasks(session: Session, project: CustomerOnboardingProjectORM) -> None:
    seeds = [
        ("SpectraCheck setup", "spectracheck_configuration", "spectracheck"),
        ("ComplianceCore setup", "regulatory_configuration", "regulatory_hub"),
        ("Reaction Optimization setup", "reaction_configuration", "reaction_optimization"),
    ]
    for index, (title, task_type, program) in enumerate(seeds, start=1):
        session.add(
            ImplementationTaskORM(
                onboarding_project_id=project.id,
                title=title,
                description="Default onboarding readiness task.",
                task_type=task_type,
                program=program,
                status="open",
                metadata_json=_json_dump({"seed_order": index, "pilot_scope": True}, default={}),
            )
        )


def create_onboarding_project(
    session_factory: sessionmaker[Session],
    tenant_id: int,
    payload: CustomerOnboardingProjectCreate,
) -> CustomerOnboardingProject:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        if payload.pilot_program_id is not None:
            pilot = session.get(PilotProgramORM, payload.pilot_program_id)
            if pilot is None:
                raise TenantSaaSError("Pilot program not found.")
            ensure_tenant_scope(tenant_id, pilot.tenant_id)
        row = CustomerOnboardingProjectORM(
            tenant_id=tenant_id,
            pilot_program_id=payload.pilot_program_id,
            title=payload.title,
            status=payload.status,
            owner_name=payload.owner_name,
            customer_contact=payload.customer_contact,
            implementation_stage=payload.implementation_stage,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        _seed_default_onboarding_tasks(session, row)
        session.flush()
        return _onboarding_to_record(row)


def list_onboarding_projects(session_factory: sessionmaker[Session], tenant_id: int) -> list[CustomerOnboardingProject]:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        stmt = select(CustomerOnboardingProjectORM).where(CustomerOnboardingProjectORM.tenant_id == tenant_id).order_by(CustomerOnboardingProjectORM.created_at.desc())
        return [_onboarding_to_record(row) for row in session.scalars(stmt)]


def get_onboarding_project(session_factory: sessionmaker[Session], project_id: int) -> CustomerOnboardingProject | None:
    with session_scope(session_factory) as session:
        row = session.get(CustomerOnboardingProjectORM, project_id)
        return _onboarding_to_record(row) if row else None


def update_onboarding_project(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: CustomerOnboardingProjectUpdate,
) -> CustomerOnboardingProject | None:
    with session_scope(session_factory) as session:
        row = session.get(CustomerOnboardingProjectORM, project_id)
        if row is None:
            return None
        _apply_updates(
            row,
            payload,
            ("pilot_program_id", "title", "status", "owner_name", "customer_contact", "implementation_stage", "metadata_json"),
        )
        row.updated_at = utcnow()
        session.flush()
        return _onboarding_to_record(row)


def create_implementation_task(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ImplementationTaskCreate,
) -> ImplementationTask:
    with session_scope(session_factory) as session:
        project = session.get(CustomerOnboardingProjectORM, project_id)
        if project is None:
            raise TenantSaaSError("Onboarding project not found.")
        row = ImplementationTaskORM(
            onboarding_project_id=project_id,
            title=payload.title,
            description=payload.description,
            task_type=payload.task_type,
            program=payload.program,
            status=payload.status,
            owner=payload.owner,
            due_date=payload.due_date,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _task_to_record(row)


def list_implementation_tasks(session_factory: sessionmaker[Session], project_id: int) -> list[ImplementationTask]:
    with session_scope(session_factory) as session:
        if session.get(CustomerOnboardingProjectORM, project_id) is None:
            raise TenantSaaSError("Onboarding project not found.")
        stmt = select(ImplementationTaskORM).where(ImplementationTaskORM.onboarding_project_id == project_id).order_by(ImplementationTaskORM.id.asc())
        return [_task_to_record(row) for row in session.scalars(stmt)]


def get_implementation_task_tenant_id(
    session_factory: sessionmaker[Session],
    task_id: int,
) -> int | None:
    with session_scope(session_factory) as session:
        row = session.get(ImplementationTaskORM, task_id)
        if row is None:
            return None
        project = session.get(CustomerOnboardingProjectORM, row.onboarding_project_id)
        return project.tenant_id if project else None


def update_implementation_task(session_factory: sessionmaker[Session], task_id: int, payload: ImplementationTaskUpdate) -> ImplementationTask | None:
    with session_scope(session_factory) as session:
        row = session.get(ImplementationTaskORM, task_id)
        if row is None:
            return None
        _apply_updates(
            row,
            payload,
            ("title", "description", "task_type", "program", "status", "owner", "due_date", "metadata_json"),
        )
        row.updated_at = utcnow()
        session.flush()
        return _task_to_record(row)


def create_data_boundary(
    session_factory: sessionmaker[Session],
    tenant_id: int,
    payload: TenantDataBoundaryCreate,
) -> TenantDataBoundary:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        row = TenantDataBoundaryORM(
            tenant_id=tenant_id,
            isolation_mode=payload.isolation_mode,
            encryption_profile=payload.encryption_profile,
            storage_prefix=payload.storage_prefix,
            allowed_regions_json=_json_dump(payload.allowed_regions_json, default=[]),
            data_residency_notes=payload.data_residency_notes,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _boundary_to_record(row)


def get_data_boundary(session_factory: sessionmaker[Session], tenant_id: int) -> TenantDataBoundary | None:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        stmt = select(TenantDataBoundaryORM).where(TenantDataBoundaryORM.tenant_id == tenant_id).order_by(TenantDataBoundaryORM.created_at.desc())
        row = session.scalars(stmt).first()
        return _boundary_to_record(row) if row else None


def update_data_boundary(session_factory: sessionmaker[Session], boundary_id: int, payload: TenantDataBoundaryUpdate) -> TenantDataBoundary | None:
    with session_scope(session_factory) as session:
        row = session.get(TenantDataBoundaryORM, boundary_id)
        if row is None:
            return None
        _apply_updates(
            row,
            payload,
            ("isolation_mode", "encryption_profile", "storage_prefix", "allowed_regions_json", "data_residency_notes", "status", "metadata_json"),
        )
        session.flush()
        return _boundary_to_record(row)


def create_security_profile(
    session_factory: sessionmaker[Session],
    tenant_id: int,
    payload: TenantSecurityProfileCreate,
) -> TenantSecurityProfile:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        row = TenantSecurityProfileORM(
            tenant_id=tenant_id,
            sso_enabled=payload.sso_enabled,
            mfa_required=payload.mfa_required,
            allowed_domains_json=_json_dump(payload.allowed_domains_json, default=[]),
            session_timeout_minutes=payload.session_timeout_minutes,
            ip_allowlist_json=_json_dump(payload.ip_allowlist_json, default=[]),
            security_frameworks_json=_json_dump(payload.security_frameworks_json, default=[]),
            risk_summary_json=_json_dump(payload.risk_summary_json, default={}),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _security_to_record(row)


def get_security_profile(session_factory: sessionmaker[Session], tenant_id: int) -> TenantSecurityProfile | None:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        stmt = select(TenantSecurityProfileORM).where(TenantSecurityProfileORM.tenant_id == tenant_id).order_by(TenantSecurityProfileORM.created_at.desc())
        row = session.scalars(stmt).first()
        return _security_to_record(row) if row else None


def update_security_profile(session_factory: sessionmaker[Session], profile_id: int, payload: TenantSecurityProfileUpdate) -> TenantSecurityProfile | None:
    with session_scope(session_factory) as session:
        row = session.get(TenantSecurityProfileORM, profile_id)
        if row is None:
            return None
        _apply_updates(
            row,
            payload,
            ("sso_enabled", "mfa_required", "allowed_domains_json", "session_timeout_minutes", "ip_allowlist_json", "security_frameworks_json", "risk_summary_json", "status", "metadata_json"),
        )
        row.updated_at = utcnow()
        session.flush()
        return _security_to_record(row)


def create_validation_profile(
    session_factory: sessionmaker[Session],
    tenant_id: int,
    payload: TenantValidationProfileCreate,
) -> TenantValidationProfile:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        row = TenantValidationProfileORM(
            tenant_id=tenant_id,
            validation_required=payload.validation_required,
            validation_project_ids_json=_json_dump(payload.validation_project_ids_json, default=[]),
            controlled_record_policy=payload.controlled_record_policy,
            esignature_required=payload.esignature_required,
            data_integrity_assessment_ids_json=_json_dump(payload.data_integrity_assessment_ids_json, default=[]),
            inspection_package_ids_json=_json_dump(payload.inspection_package_ids_json, default=[]),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _validation_to_record(row)


def get_validation_profile(session_factory: sessionmaker[Session], tenant_id: int) -> TenantValidationProfile | None:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        stmt = select(TenantValidationProfileORM).where(TenantValidationProfileORM.tenant_id == tenant_id).order_by(TenantValidationProfileORM.created_at.desc())
        row = session.scalars(stmt).first()
        return _validation_to_record(row) if row else None


def update_validation_profile(session_factory: sessionmaker[Session], profile_id: int, payload: TenantValidationProfileUpdate) -> TenantValidationProfile | None:
    with session_scope(session_factory) as session:
        row = session.get(TenantValidationProfileORM, profile_id)
        if row is None:
            return None
        _apply_updates(
            row,
            payload,
            ("validation_required", "validation_project_ids_json", "controlled_record_policy", "esignature_required", "data_integrity_assessment_ids_json", "inspection_package_ids_json", "status", "metadata_json"),
        )
        row.updated_at = utcnow()
        session.flush()
        return _validation_to_record(row)


def _latest_or_create_usage(session: Session, tenant_id: int) -> TenantUsageSummaryORM:
    stmt = select(TenantUsageSummaryORM).where(TenantUsageSummaryORM.tenant_id == tenant_id).order_by(TenantUsageSummaryORM.period_end.desc())
    row = session.scalars(stmt).first()
    if row is not None:
        return row
    now = utcnow()
    row = TenantUsageSummaryORM(
        tenant_id=tenant_id,
        period_start=now - timedelta(days=30),
        period_end=now,
        spectracheck_usage_json=_json_dump({"sessions": 0, "safe_aggregate_only": True}, default={}),
        regulatory_usage_json=_json_dump({"dossiers": 0, "safe_aggregate_only": True}, default={}),
        reaction_usage_json=_json_dump({"projects": 0, "safe_aggregate_only": True}, default={}),
        reports_generated=0,
        actions_completed=0,
        hours_saved=0.0,
        warnings_json=_json_dump([{"message": "No tenant usage events have been rolled up yet."}], default=[]),
        metadata_json=_json_dump({"safe_summary": True}, default={}),
    )
    session.add(row)
    session.flush()
    return row


def _latest_or_create_roi(session: Session, tenant_id: int, usage: TenantUsageSummaryORM | None = None) -> TenantRoiSnapshotORM:
    stmt = select(TenantRoiSnapshotORM).where(TenantRoiSnapshotORM.tenant_id == tenant_id).order_by(TenantRoiSnapshotORM.period_end.desc())
    row = session.scalars(stmt).first()
    if row is not None:
        return row
    usage = usage or _latest_or_create_usage(session, tenant_id)
    row = TenantRoiSnapshotORM(
        tenant_id=tenant_id,
        period_start=usage.period_start,
        period_end=usage.period_end,
        total_hours_saved=float(usage.hours_saved or 0.0),
        tasks_automated=usage.actions_completed,
        reports_generated=usage.reports_generated,
        regulatory_actions_created=0,
        reaction_recommendations_approved=0,
        renewal_summary_json=_json_dump({"status": "requires_review", "safe_aggregate_only": True}, default={}),
        metadata_json=_json_dump({"safe_summary": True}, default={}),
    )
    session.add(row)
    session.flush()
    return row


def get_usage_summary(session_factory: sessionmaker[Session], tenant_id: int) -> TenantUsageSummary:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        return _usage_to_record(_latest_or_create_usage(session, tenant_id))


def get_roi_snapshot(session_factory: sessionmaker[Session], tenant_id: int) -> TenantRoiSnapshot:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        usage = _latest_or_create_usage(session, tenant_id)
        return _roi_to_record(_latest_or_create_roi(session, tenant_id, usage))


def _blocked_tasks(session: Session, tenant_id: int) -> list[ImplementationTaskORM]:
    stmt = (
        select(ImplementationTaskORM)
        .join(CustomerOnboardingProjectORM, ImplementationTaskORM.onboarding_project_id == CustomerOnboardingProjectORM.id)
        .where(CustomerOnboardingProjectORM.tenant_id == tenant_id)
        .where(ImplementationTaskORM.status.in_(["blocked", "open", "in_progress"]))
        .order_by(ImplementationTaskORM.id.asc())
    )
    return list(session.scalars(stmt))


def get_health_score(session_factory: sessionmaker[Session], tenant_id: int) -> CustomerSuccessHealthScore:
    with session_scope(session_factory) as session:
        tenant = _require_tenant(session, tenant_id)
        usage = _latest_or_create_usage(session, tenant_id)
        roi = _latest_or_create_roi(session, tenant_id, usage)
        tasks = _blocked_tasks(session, tenant_id)
        blocked = [task for task in tasks if task.status == "blocked"]
        score = max(0.0, 100.0 - len(blocked) * 20.0 - len([t for t in tasks if t.status == "open"]) * 3.0)
        status = "healthy" if score >= 80 else "watch" if score >= 55 else "at_risk"
        row = CustomerSuccessHealthScoreORM(
            tenant_id=tenant_id,
            score=round(score, 2),
            status=status,
            usage_summary_json=_json_dump(_usage_to_record(usage).model_dump(mode="json"), default={}),
            onboarding_summary_json=_json_dump(
                {"tenant_status": tenant.status, "open_task_count": len(tasks), "blocked_task_count": len(blocked)},
                default={},
            ),
            support_summary_json=_json_dump({"status": "unknown", "safe_summary_only": True}, default={}),
            roi_summary_json=_json_dump(_roi_to_record(roi).model_dump(mode="json"), default={}),
            blockers_json=_json_dump(
                [
                    {"task_id": task.id, "title": task.title, "program": task.program, "status": task.status}
                    for task in blocked
                ],
                default=[],
            ),
            recommended_actions_json=_json_dump(
                [{"action": "Review open onboarding, validation readiness, security profile, and go-live readiness."}],
                default=[],
            ),
            metadata_json=_json_dump({"safe_summary": True}, default={}),
        )
        session.add(row)
        session.flush()
        return _health_to_record(row)


def _safe_security_summary(row: TenantSecurityProfileORM | None) -> dict[str, Any]:
    if row is None:
        return {"status": "missing", "sso_enabled": False, "mfa_required": False}
    record = _security_to_record(row)
    return record.model_dump(mode="json")


def _safe_boundary_summary(row: TenantDataBoundaryORM | None) -> dict[str, Any]:
    if row is None:
        return {"status": "missing", "isolation_mode": None}
    return _boundary_to_record(row).model_dump(mode="json")


def _safe_validation_summary(row: TenantValidationProfileORM | None) -> dict[str, Any]:
    if row is None:
        return {"status": "missing", "validation_required": False}
    return _validation_to_record(row).model_dump(mode="json")


def _latest_row(session: Session, orm_class: Any, tenant_id: int) -> Any | None:
    stmt = select(orm_class).where(orm_class.tenant_id == tenant_id).order_by(orm_class.created_at.desc())
    return session.scalars(stmt).first()


def _procurement_payload(session: Session, tenant_id: int) -> dict[str, Any]:
    usage = _latest_or_create_usage(session, tenant_id)
    roi = _latest_or_create_roi(session, tenant_id, usage)
    audit_count = int(
        session.scalar(
            select(AuditEventORM.id)
            .where(AuditEventORM.metadata_json.contains(str(tenant_id)))
            .limit(1)
        )
        or 0
    )
    payload = {
        "safe_summary": True,
        "language_notice": "Procurement evidence package supports review and does not assert certification, approval, or legal compliance.",
        "product_order": DEFAULT_PRODUCT_ORDER,
        "security_profile": _safe_security_summary(_latest_row(session, TenantSecurityProfileORM, tenant_id)),
        "data_boundary": _safe_boundary_summary(_latest_row(session, TenantDataBoundaryORM, tenant_id)),
        "validation_profile": _safe_validation_summary(_latest_row(session, TenantValidationProfileORM, tenant_id)),
        "ai_governance_summary": {"status": "requires_review", "raw_model_artifacts_included": False},
        "audit_summary": {"tenant_admin_actions_present": bool(audit_count), "raw_audit_export_included": False},
        "mobile_offline_safety_summary": {"status": "requires_review", "raw_sensitive_data_included": False},
        "connector_safety_summary": {"status": "requires_review", "connector_auth_material_included": False},
        "roi_summary": _roi_to_record(roi).model_dump(mode="json"),
        "usage_summary": _usage_to_record(usage).model_dump(mode="json"),
    }
    return _safe_json(payload)


def create_procurement_package(
    session_factory: sessionmaker[Session],
    tenant_id: int,
    payload: ProcurementEvidencePackageCreate,
) -> ProcurementEvidencePackage:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        package = _procurement_payload(session, tenant_id)
        package_sha = _sha256_json(package)
        html = (
            "<!doctype html><html><body>"
            f"<h1>{payload.title}</h1>"
            "<p>Procurement evidence package for review. No raw spectra, full structures, source documents, secrets, connector credentials, or model artifacts are included.</p>"
            "</body></html>"
        )
        row = ProcurementEvidencePackageORM(
            tenant_id=tenant_id,
            title=payload.title,
            package_type=payload.package_type,
            status=payload.status,
            package_json=_json_dump(package, default={}),
            package_html=html,
            package_sha256=package_sha,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _procurement_to_record(row)


def list_procurement_packages(session_factory: sessionmaker[Session], tenant_id: int) -> list[ProcurementEvidencePackage]:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        stmt = select(ProcurementEvidencePackageORM).where(ProcurementEvidencePackageORM.tenant_id == tenant_id).order_by(ProcurementEvidencePackageORM.created_at.desc())
        return [_procurement_to_record(row) for row in session.scalars(stmt)]


def get_procurement_package(session_factory: sessionmaker[Session], package_id: int) -> ProcurementEvidencePackage | None:
    with session_scope(session_factory) as session:
        row = session.get(ProcurementEvidencePackageORM, package_id)
        return _procurement_to_record(row) if row else None


def create_audit_export(
    session_factory: sessionmaker[Session],
    tenant_id: int,
    payload: TenantAuditExportCreate,
) -> TenantAuditExport:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        export_payload = _safe_json(
            {
                "tenant_id": tenant_id,
                "export_scope": payload.export_scope,
                "safe_summary": True,
                "raw_sensitive_data_included": False,
            }
        )
        row = TenantAuditExportORM(
            tenant_id=tenant_id,
            export_scope=payload.export_scope,
            status="succeeded",
            export_sha256=_sha256_json(export_payload),
            metadata_json=_json_dump({**payload.metadata_json, "manifest": export_payload}, default={}),
        )
        session.add(row)
        session.flush()
        return _audit_export_to_record(row)


def get_audit_export(session_factory: sessionmaker[Session], export_id: int) -> TenantAuditExport | None:
    with session_scope(session_factory) as session:
        row = session.get(TenantAuditExportORM, export_id)
        return _audit_export_to_record(row) if row else None


def get_module_readiness(session_factory: sessionmaker[Session], tenant_id: int) -> TenantModuleReadiness:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        entitlements = list(
            session.scalars(
                select(TenantEntitlementORM).where(TenantEntitlementORM.tenant_id == tenant_id)
            )
        )
        by_program = {key: [] for key in DEFAULT_PRODUCT_KEYS}
        for entitlement in entitlements:
            if entitlement.program in by_program:
                by_program[entitlement.program].append(entitlement)
        modules = []
        for display, key in zip(DEFAULT_PRODUCT_ORDER, DEFAULT_PRODUCT_KEYS, strict=True):
            entries = by_program[key]
            enabled = True if not entries else any(entry.enabled for entry in entries)
            modules.append(
                {
                    "program": key,
                    "display_name": display,
                    "enabled": enabled,
                    "entitlement_count": len(entries),
                    "readiness_status": "enabled" if enabled else "disabled_by_entitlement",
                }
            )
        return TenantModuleReadiness(
            tenant_id=tenant_id,
            product_order=DEFAULT_PRODUCT_ORDER,
            modules=modules,
            entitlement_summary_json={"entitlements_may_disable_modules": True, "order_is_fixed": True},
            warnings_json=["Entitlements may enable or disable modules but must not reorder core programs."],
        )


def get_go_live_readiness(session_factory: sessionmaker[Session], tenant_id: int) -> TenantGoLiveReadiness:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        tasks = _blocked_tasks(session, tenant_id)
        blocked = [
            {"task_id": task.id, "title": task.title, "program": task.program, "status": task.status}
            for task in tasks
            if task.status == "blocked"
        ]
        security = _safe_security_summary(_latest_row(session, TenantSecurityProfileORM, tenant_id))
        boundary = _safe_boundary_summary(_latest_row(session, TenantDataBoundaryORM, tenant_id))
        validation = _safe_validation_summary(_latest_row(session, TenantValidationProfileORM, tenant_id))
        status = "blocked" if blocked else "ready_for_review"
        return TenantGoLiveReadiness(
            tenant_id=tenant_id,
            status=status,
            onboarding_readiness={"open_task_count": len(tasks), "blocked_task_count": len(blocked)},
            validation_readiness=validation,
            security_profile=security,
            data_boundary=boundary,
            blockers_json=blocked,
            product_order=DEFAULT_PRODUCT_ORDER,
        )
