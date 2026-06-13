from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    CustomerAcceptanceProtocol,
    CustomerAcceptanceProtocolCreate,
    CustomerAcceptanceProtocolUpdate,
    CustomerAcceptanceTest,
    CustomerAcceptanceTestExecute,
    DemoTenantSeed,
    DemoTenantSeedCreate,
    ExpectedOutputContract,
    ExpectedOutputContractCreate,
    GoldenDataset,
    GoldenDatasetCreate,
    GoldenDatasetUpdate,
    GoldenPilotScenario,
    GoldenPilotScenarioCreate,
    GoldenPilotScenarioUpdate,
    GoldenWorkflowCase,
    GoldenWorkflowCaseCreate,
    PilotCustomerDashboard,
    PilotEvidenceBundle,
    PilotEvidenceBundleCreate,
    PilotReadinessAssessment,
    PilotReadinessAssessmentCreate,
    PilotRun,
    PilotRunCreate,
    PilotRunDetail,
    PilotRunStep,
    PilotSignoffCreate,
    PilotSignoffRecord,
    ScenarioValidationResult,
)
from .orm import (
    CustomerAcceptanceProtocolORM,
    CustomerAcceptanceTestORM,
    DemoTenantSeedORM,
    ExpectedOutputContractORM,
    GoldenDatasetORM,
    GoldenPilotScenarioORM,
    GoldenWorkflowCaseORM,
    PilotEvidenceBundleORM,
    PilotReadinessAssessmentORM,
    PilotRunORM,
    PilotRunStepORM,
    PilotSignoffRecordORM,
    ScenarioValidationResultORM,
    TenantORM,
    utcnow,
)


class GoldenPilotError(ValueError):
    pass


class GoldenPilotNotFoundError(GoldenPilotError):
    pass


DEFAULT_PRODUCT_ORDER = ["SpectraCheck", "Regentry", "Reaction Optimization"]
DEFAULT_PRODUCT_KEYS = ["spectracheck", "regulatory_hub", "reaction_optimization"]
DEMO_SOURCE_TYPES = {"internal_demo", "curated_literature", "synthetic_demo", "benchmark"}
CUSTOMER_SOURCE_TYPES = {"customer_pilot"}
SENSITIVE_KEY_MARKERS = (
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "credential",
    "connector_credential",
    "raw_spectrum",
    "raw_spectra",
    "full_smiles",
    "smiles_library",
    "full_structure",
    "structure_library",
    "source_text",
    "source_document",
    "document_text",
    "private_customer",
    "private_notes",
    "model_artifact",
)


PROGRAM_LABEL_TO_MODULE = {
    "SpectraCheck": "spectracheck",
    "spectra_check": "spectracheck",
    "spectracheck": "spectracheck",
    "Regentry": "regulatory_hub",
    "regulatory": "regulatory_hub",
    "regulatory_hub": "regulatory_hub",
    "Reaction Optimization": "reaction_optimization",
    "reactions": "reaction_optimization",
    "reaction_optimization": "reaction_optimization",
    "Cross-module/system": "cross_module",
    "cross_module": "cross_module",
    "system": "cross_module",
}


MODULE_STEP_KEYS = {
    "spectracheck": "spectracheck_evidence_generation",
    "regulatory_hub": "regulatory_action_item_generation",
    "reaction_optimization": "reaction_objective_creation",
    "cross_module": "cross_module_review_task",
    "mobile": "mobile_review_summary",
    "validation": "validation_evidence",
}


def _safe_json(value: Any, key: str = "") -> Any:
    if isinstance(value, bool) and key.lower().endswith(("_included", "_claimed", "_created", "_required")):
        return value
    if any(marker in key.lower() for marker in SENSITIVE_KEY_MARKERS):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(k): _safe_json(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_safe_json(item, key) for item in value]
    return value


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


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_json_dump(value, default={}).encode("utf-8")).hexdigest()


def _require_tenant(session: Session, tenant_id: int) -> TenantORM:
    row = session.get(TenantORM, tenant_id)
    if row is None:
        raise GoldenPilotNotFoundError("Tenant not found.")
    return row


def _require_dataset(session: Session, dataset_id: int) -> GoldenDatasetORM:
    row = session.get(GoldenDatasetORM, dataset_id)
    if row is None:
        raise GoldenPilotNotFoundError("Golden dataset not found.")
    return row


def _require_scenario(session: Session, scenario_id: int) -> GoldenPilotScenarioORM:
    row = session.get(GoldenPilotScenarioORM, scenario_id)
    if row is None:
        raise GoldenPilotNotFoundError("Golden scenario not found.")
    return row


def _require_pilot_run(session: Session, pilot_run_id: int) -> PilotRunORM:
    row = session.get(PilotRunORM, pilot_run_id)
    if row is None:
        raise GoldenPilotNotFoundError("Pilot run not found.")
    return row


def _default_program_sequence(value: list[str] | None) -> list[str]:
    return list(value) if value else list(DEFAULT_PRODUCT_ORDER)


def _module_for_sequence_item(item: str) -> str:
    return PROGRAM_LABEL_TO_MODULE.get(item, PROGRAM_LABEL_TO_MODULE.get(item.lower(), "cross_module"))


def _validate_dataset_mix(session: Session, dataset_ids: list[int]) -> None:
    if not dataset_ids:
        return
    source_types: set[str] = set()
    for dataset_id in dataset_ids:
        source_types.add(_require_dataset(session, dataset_id).source_type)
    if source_types & CUSTOMER_SOURCE_TYPES and source_types & DEMO_SOURCE_TYPES:
        raise GoldenPilotError("Customer pilot data must not be mixed with internal demo data.")


def _dataset_metadata(source_type: str, metadata: dict[str, Any]) -> dict[str, Any]:
    merged = dict(_safe_json(metadata))
    if source_type in DEMO_SOURCE_TYPES:
        merged.setdefault("data_label", "demo/test data")
        merged.setdefault("customer_data_included", False)
    elif source_type == "customer_pilot":
        merged.setdefault("data_label", "customer pilot data")
        merged.setdefault("customer_data_included", True)
    return merged


def _dataset_warnings(source_type: str, warnings: list[dict[str, Any]], metadata: dict[str, Any]) -> list[dict[str, Any]]:
    rows = list(_safe_json(warnings))
    if source_type == "customer_pilot" and not metadata.get("customer_approved", False):
        rows.append(
            {
                "warning_type": "customer_approval_required",
                "message": "Customer pilot data is labeled as requiring explicit customer approval before demo use.",
            }
        )
    if source_type in DEMO_SOURCE_TYPES:
        rows.append(
            {
                "warning_type": "demo_test_data",
                "message": "Golden dataset is labeled demo/test data.",
            }
        )
    return rows


def _contains_missing_endpoint(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "missing_endpoint" and bool(item):
                return True
            if item == "missing_endpoint" or _contains_missing_endpoint(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_missing_endpoint(item) for item in value)
    return value == "missing_endpoint"


def _has_path(value: dict[str, Any], path: str) -> bool:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _dataset_to_record(row: GoldenDatasetORM) -> GoldenDataset:
    return GoldenDataset(
        id=row.id,
        dataset_key=row.dataset_key,
        title=row.title,
        description=row.description,
        dataset_type=row.dataset_type,
        source_type=row.source_type,
        status=row.status,
        source_references_json=_json_list(row.source_references_json),
        file_ids_json=_json_list(row.file_ids_json),
        artifact_ids_json=_json_list(row.artifact_ids_json),
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_dict(row.notes_json),
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _scenario_to_record(row: GoldenPilotScenarioORM) -> GoldenPilotScenario:
    return GoldenPilotScenario(
        id=row.id,
        scenario_key=row.scenario_key,
        title=row.title,
        description=row.description,
        scenario_type=row.scenario_type,
        program_sequence_json=_json_list(row.program_sequence_json),
        dataset_ids_json=_json_list(row.dataset_ids_json),
        required_inputs_json=_json_dict(row.required_inputs_json),
        expected_outputs_json=_json_dict(row.expected_outputs_json),
        acceptance_criteria_json=_json_list(row.acceptance_criteria_json),
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _workflow_case_to_record(row: GoldenWorkflowCaseORM) -> GoldenWorkflowCase:
    return GoldenWorkflowCase(
        id=row.id,
        scenario_id=row.scenario_id,
        case_key=row.case_key,
        title=row.title,
        input_payload_json=_json_dict(row.input_payload_json),
        expected_step_order_json=_json_list(row.expected_step_order_json),
        expected_resource_links_json=_json_list(row.expected_resource_links_json),
        expected_warnings_json=_json_list(row.expected_warnings_json),
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _contract_to_record(row: ExpectedOutputContractORM) -> ExpectedOutputContract:
    return ExpectedOutputContract(
        id=row.id,
        scenario_id=row.scenario_id,
        step_key=row.step_key,
        target_module=row.target_module,
        expected_output_type=row.expected_output_type,
        required_fields_json=_json_list(row.required_fields_json),
        forbidden_fields_json=_json_list(row.forbidden_fields_json),
        expected_statuses_json=_json_list(row.expected_statuses_json),
        tolerance_json=_json_dict(row.tolerance_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _demo_seed_to_record(row: DemoTenantSeedORM) -> DemoTenantSeed:
    return DemoTenantSeed(
        id=row.id,
        tenant_id=row.tenant_id,
        scenario_id=row.scenario_id,
        seed_type=row.seed_type,
        status=row.status,
        created_resource_ids_json=_json_dict(row.created_resource_ids_json),
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_dict(row.notes_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _pilot_run_to_record(row: PilotRunORM) -> PilotRun:
    return PilotRun(
        id=row.id,
        scenario_id=row.scenario_id,
        tenant_id=row.tenant_id,
        project_id=row.project_id,
        sample_id=row.sample_id,
        run_label=row.run_label,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        summary_json=_json_dict(row.summary_json),
        score=row.score,
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_dict(row.notes_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _pilot_step_to_record(row: PilotRunStepORM) -> PilotRunStep:
    return PilotRunStep(
        id=row.id,
        pilot_run_id=row.pilot_run_id,
        step_key=row.step_key,
        module=row.module,
        status=row.status,
        input_summary_json=_json_dict(row.input_summary_json),
        output_summary_json=_json_dict(row.output_summary_json),
        linked_resource_type=row.linked_resource_type,
        linked_resource_id=row.linked_resource_id,
        started_at=row.started_at,
        finished_at=row.finished_at,
        warnings_json=_json_list(row.warnings_json),
        notes_json=_json_dict(row.notes_json),
        metadata_json=_json_dict(row.metadata_json),
    )


def _pilot_run_detail(session: Session, row: PilotRunORM) -> PilotRunDetail:
    steps = session.scalars(
        select(PilotRunStepORM).where(PilotRunStepORM.pilot_run_id == row.id).order_by(PilotRunStepORM.id.asc())
    ).all()
    base = _pilot_run_to_record(row).model_dump()
    return PilotRunDetail(**base, steps=[_pilot_step_to_record(step) for step in steps])


def _validation_result_to_record(row: ScenarioValidationResultORM) -> ScenarioValidationResult:
    return ScenarioValidationResult(
        id=row.id,
        pilot_run_id=row.pilot_run_id,
        scenario_id=row.scenario_id,
        contract_id=row.contract_id,
        validation_status=row.validation_status,
        expected_json=_json_dict(row.expected_json),
        actual_json=_json_dict(row.actual_json),
        differences_json=_json_dict(row.differences_json),
        score=row.score,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _acceptance_protocol_to_record(row: CustomerAcceptanceProtocolORM) -> CustomerAcceptanceProtocol:
    return CustomerAcceptanceProtocol(
        id=row.id,
        tenant_id=row.tenant_id,
        pilot_program_id=row.pilot_program_id,
        title=row.title,
        scope=row.scope,
        scenario_ids_json=_json_list(row.scenario_ids_json),
        acceptance_tests_json=_json_list(row.acceptance_tests_json),
        success_criteria_json=_json_list(row.success_criteria_json),
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _acceptance_test_to_record(row: CustomerAcceptanceTestORM) -> CustomerAcceptanceTest:
    return CustomerAcceptanceTest(
        id=row.id,
        protocol_id=row.protocol_id,
        test_key=row.test_key,
        title=row.title,
        description=row.description,
        scenario_id=row.scenario_id,
        expected_result=row.expected_result,
        status=row.status,
        executed_by=row.executed_by,
        executed_at=row.executed_at,
        evidence_json=_json_dict(row.evidence_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _readiness_to_record(row: PilotReadinessAssessmentORM) -> PilotReadinessAssessment:
    return PilotReadinessAssessment(
        id=row.id,
        tenant_id=row.tenant_id,
        pilot_program_id=row.pilot_program_id,
        onboarding_project_id=row.onboarding_project_id,
        readiness_status=row.readiness_status,
        spectracheck_readiness_json=_json_dict(row.spectracheck_readiness_json),
        regulatory_readiness_json=_json_dict(row.regulatory_readiness_json),
        reaction_readiness_json=_json_dict(row.reaction_readiness_json),
        connector_readiness_json=_json_dict(row.connector_readiness_json),
        validation_readiness_json=_json_dict(row.validation_readiness_json),
        mobile_readiness_json=_json_dict(row.mobile_readiness_json),
        security_readiness_json=_json_dict(row.security_readiness_json),
        warnings_json=_json_list(row.warnings_json),
        recommended_actions_json=_json_list(row.recommended_actions_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _signoff_to_record(row: PilotSignoffRecordORM) -> PilotSignoffRecord:
    return PilotSignoffRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        pilot_run_id=row.pilot_run_id,
        protocol_id=row.protocol_id,
        signer_name=row.signer_name,
        signer_email=row.signer_email,
        decision=row.decision,
        rationale=row.rationale,
        signed_at=row.signed_at,
        signature_record_id=row.signature_record_id,
        metadata_json=_json_dict(row.metadata_json),
    )


def _evidence_bundle_to_record(row: PilotEvidenceBundleORM) -> PilotEvidenceBundle:
    return PilotEvidenceBundle(
        id=row.id,
        pilot_run_id=row.pilot_run_id,
        title=row.title,
        included_resource_ids_json=_json_dict(row.included_resource_ids_json),
        package_json=_json_dict(row.package_json),
        package_html=row.package_html,
        package_sha256=row.package_sha256,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def create_golden_dataset(session_factory: sessionmaker[Session], payload: GoldenDatasetCreate) -> GoldenDataset:
    with session_scope(session_factory) as session:
        metadata = _dataset_metadata(payload.source_type, payload.metadata_json)
        warnings = _dataset_warnings(payload.source_type, payload.warnings_json, metadata)
        row = GoldenDatasetORM(
            dataset_key=payload.dataset_key,
            title=payload.title,
            description=payload.description,
            dataset_type=payload.dataset_type,
            source_type=payload.source_type,
            status=payload.status,
            source_references_json=_json_dump(payload.source_references_json, default=[]),
            file_ids_json=_json_dump(payload.file_ids_json, default=[]),
            artifact_ids_json=_json_dump(payload.artifact_ids_json, default=[]),
            warnings_json=_json_dump(warnings, default=[]),
            notes_json=_json_dump(payload.notes_json, default={}),
            metadata_json=_json_dump(metadata, default={}),
        )
        session.add(row)
        session.flush()
        return _dataset_to_record(row)


def list_golden_datasets(
    session_factory: sessionmaker[Session],
    *,
    dataset_type: str | None = None,
    source_type: str | None = None,
    status_filter: str | None = None,
    limit: int = 200,
) -> list[GoldenDataset]:
    with session_scope(session_factory) as session:
        stmt = select(GoldenDatasetORM).order_by(GoldenDatasetORM.id.desc()).limit(limit)
        if dataset_type:
            stmt = stmt.where(GoldenDatasetORM.dataset_type == dataset_type)
        if source_type:
            stmt = stmt.where(GoldenDatasetORM.source_type == source_type)
        if status_filter:
            stmt = stmt.where(GoldenDatasetORM.status == status_filter)
        return [_dataset_to_record(row) for row in session.scalars(stmt).all()]


def get_golden_dataset(session_factory: sessionmaker[Session], dataset_id: int) -> GoldenDataset | None:
    with session_scope(session_factory) as session:
        row = session.get(GoldenDatasetORM, dataset_id)
        return _dataset_to_record(row) if row is not None else None


def update_golden_dataset(
    session_factory: sessionmaker[Session],
    dataset_id: int,
    payload: GoldenDatasetUpdate,
) -> GoldenDataset | None:
    with session_scope(session_factory) as session:
        row = session.get(GoldenDatasetORM, dataset_id)
        if row is None:
            return None
        update_data = payload.model_dump(exclude_unset=True)
        next_source_type = update_data.get("source_type", row.source_type)
        next_metadata = update_data.get("metadata_json", _json_dict(row.metadata_json))
        next_warnings = update_data.get("warnings_json", _json_list(row.warnings_json))
        if "metadata_json" in update_data or "source_type" in update_data:
            row.metadata_json = _json_dump(_dataset_metadata(next_source_type, next_metadata), default={})
        if "warnings_json" in update_data or "source_type" in update_data or "metadata_json" in update_data:
            row.warnings_json = _json_dump(_dataset_warnings(next_source_type, next_warnings, next_metadata), default=[])
        for field, value in update_data.items():
            if field in {"metadata_json", "warnings_json"}:
                continue
            if field in {"source_references_json", "file_ids_json", "artifact_ids_json"}:
                row_value_default: list[Any] = []
                setattr(row, field, _json_dump(value, default=row_value_default))
            elif field == "notes_json":
                row.notes_json = _json_dump(value, default={})
            elif value is not None:
                setattr(row, field, value)
        row.updated_at = utcnow()
        session.flush()
        return _dataset_to_record(row)


def create_scenario(session_factory: sessionmaker[Session], payload: GoldenPilotScenarioCreate) -> GoldenPilotScenario:
    with session_scope(session_factory) as session:
        _validate_dataset_mix(session, payload.dataset_ids_json)
        row = GoldenPilotScenarioORM(
            scenario_key=payload.scenario_key,
            title=payload.title,
            description=payload.description,
            scenario_type=payload.scenario_type,
            program_sequence_json=_json_dump(_default_program_sequence(payload.program_sequence_json), default=[]),
            dataset_ids_json=_json_dump(payload.dataset_ids_json, default=[]),
            required_inputs_json=_json_dump(payload.required_inputs_json, default={}),
            expected_outputs_json=_json_dump(payload.expected_outputs_json, default={}),
            acceptance_criteria_json=_json_dump(payload.acceptance_criteria_json, default=[]),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _scenario_to_record(row)


def list_scenarios(
    session_factory: sessionmaker[Session],
    *,
    scenario_type: str | None = None,
    status_filter: str | None = None,
    limit: int = 200,
) -> list[GoldenPilotScenario]:
    with session_scope(session_factory) as session:
        stmt = select(GoldenPilotScenarioORM).order_by(GoldenPilotScenarioORM.id.desc()).limit(limit)
        if scenario_type:
            stmt = stmt.where(GoldenPilotScenarioORM.scenario_type == scenario_type)
        if status_filter:
            stmt = stmt.where(GoldenPilotScenarioORM.status == status_filter)
        return [_scenario_to_record(row) for row in session.scalars(stmt).all()]


def get_scenario(session_factory: sessionmaker[Session], scenario_id: int) -> GoldenPilotScenario | None:
    with session_scope(session_factory) as session:
        row = session.get(GoldenPilotScenarioORM, scenario_id)
        return _scenario_to_record(row) if row is not None else None


def update_scenario(
    session_factory: sessionmaker[Session],
    scenario_id: int,
    payload: GoldenPilotScenarioUpdate,
) -> GoldenPilotScenario | None:
    with session_scope(session_factory) as session:
        row = session.get(GoldenPilotScenarioORM, scenario_id)
        if row is None:
            return None
        update_data = payload.model_dump(exclude_unset=True)
        next_dataset_ids = update_data.get("dataset_ids_json", _json_list(row.dataset_ids_json))
        _validate_dataset_mix(session, next_dataset_ids)
        for field, value in update_data.items():
            if field == "program_sequence_json":
                row.program_sequence_json = _json_dump(_default_program_sequence(value), default=[])
            elif field in {
                "dataset_ids_json",
                "acceptance_criteria_json",
            }:
                setattr(row, field, _json_dump(value, default=[]))
            elif field in {"required_inputs_json", "expected_outputs_json", "metadata_json"}:
                setattr(row, field, _json_dump(value, default={}))
            elif value is not None:
                setattr(row, field, value)
        row.updated_at = utcnow()
        session.flush()
        return _scenario_to_record(row)


def create_workflow_case(
    session_factory: sessionmaker[Session],
    scenario_id: int,
    payload: GoldenWorkflowCaseCreate,
) -> GoldenWorkflowCase:
    with session_scope(session_factory) as session:
        _require_scenario(session, scenario_id)
        row = GoldenWorkflowCaseORM(
            scenario_id=scenario_id,
            case_key=payload.case_key,
            title=payload.title,
            input_payload_json=_json_dump(payload.input_payload_json, default={}),
            expected_step_order_json=_json_dump(payload.expected_step_order_json, default=[]),
            expected_resource_links_json=_json_dump(payload.expected_resource_links_json, default=[]),
            expected_warnings_json=_json_dump(payload.expected_warnings_json, default=[]),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _workflow_case_to_record(row)


def list_workflow_cases(session_factory: sessionmaker[Session], scenario_id: int) -> list[GoldenWorkflowCase]:
    with session_scope(session_factory) as session:
        _require_scenario(session, scenario_id)
        rows = session.scalars(
            select(GoldenWorkflowCaseORM)
            .where(GoldenWorkflowCaseORM.scenario_id == scenario_id)
            .order_by(GoldenWorkflowCaseORM.id.asc())
        ).all()
        return [_workflow_case_to_record(row) for row in rows]


def create_expected_output_contract(
    session_factory: sessionmaker[Session],
    scenario_id: int,
    payload: ExpectedOutputContractCreate,
) -> ExpectedOutputContract:
    with session_scope(session_factory) as session:
        _require_scenario(session, scenario_id)
        row = ExpectedOutputContractORM(
            scenario_id=scenario_id,
            step_key=payload.step_key,
            target_module=payload.target_module,
            expected_output_type=payload.expected_output_type,
            required_fields_json=_json_dump(payload.required_fields_json, default=[]),
            forbidden_fields_json=_json_dump(payload.forbidden_fields_json, default=[]),
            expected_statuses_json=_json_dump(payload.expected_statuses_json, default=[]),
            tolerance_json=_json_dump(payload.tolerance_json, default={}),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _contract_to_record(row)


def list_expected_output_contracts(
    session_factory: sessionmaker[Session],
    scenario_id: int,
) -> list[ExpectedOutputContract]:
    with session_scope(session_factory) as session:
        _require_scenario(session, scenario_id)
        rows = session.scalars(
            select(ExpectedOutputContractORM)
            .where(ExpectedOutputContractORM.scenario_id == scenario_id)
            .order_by(ExpectedOutputContractORM.id.asc())
        ).all()
        return [_contract_to_record(row) for row in rows]


def seed_demo_tenant(
    session_factory: sessionmaker[Session],
    scenario_id: int,
    payload: DemoTenantSeedCreate,
) -> DemoTenantSeed:
    with session_scope(session_factory) as session:
        scenario = _require_scenario(session, scenario_id)
        _require_tenant(session, payload.tenant_id)
        dataset_ids = _json_list(scenario.dataset_ids_json)
        dataset_rows = [_require_dataset(session, int(dataset_id)) for dataset_id in dataset_ids]
        has_customer_data = any(row.source_type == "customer_pilot" for row in dataset_rows)
        warnings: list[dict[str, Any]] = []
        status = "succeeded"
        if has_customer_data and not payload.use_customer_data:
            warnings.append(
                {
                    "warning_type": "customer_data_not_seeded",
                    "message": "Customer pilot data was not seeded because explicit customer data selection was not provided.",
                }
            )
        elif has_customer_data and payload.use_customer_data:
            warnings.append(
                {
                    "warning_type": "customer_data_selected",
                    "message": "Customer pilot data was explicitly selected for this tenant seed and remains tenant scoped.",
                }
            )
            status = "requires_review"
        created_resources = {
            "tenant_id": payload.tenant_id,
            "scenario_id": scenario_id,
            "seed_type": payload.seed_type,
            "safe_demo_records": [
                {"resource_type": "golden_scenario", "resource_id": scenario_id},
                {"resource_type": "golden_dataset", "resource_ids": dataset_ids if not has_customer_data else []},
            ],
            "customer_data_included": bool(has_customer_data and payload.use_customer_data),
            "product_order": DEFAULT_PRODUCT_ORDER,
        }
        row = DemoTenantSeedORM(
            tenant_id=payload.tenant_id,
            scenario_id=scenario_id,
            seed_type=payload.seed_type,
            status=status,
            created_resource_ids_json=_json_dump(created_resources, default={}),
            warnings_json=_json_dump(warnings, default=[]),
            notes_json=_json_dump({"label": "demo/test seed", "safe_summary_only": True}, default={}),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _demo_seed_to_record(row)


def get_demo_seed(session_factory: sessionmaker[Session], seed_id: int) -> DemoTenantSeed | None:
    with session_scope(session_factory) as session:
        row = session.get(DemoTenantSeedORM, seed_id)
        return _demo_seed_to_record(row) if row is not None else None


def run_pilot_scenario(
    session_factory: sessionmaker[Session],
    scenario_id: int,
    payload: PilotRunCreate,
) -> PilotRunDetail:
    with session_scope(session_factory) as session:
        scenario = _require_scenario(session, scenario_id)
        if payload.tenant_id is not None:
            _require_tenant(session, payload.tenant_id)
        started = utcnow()
        warnings: list[dict[str, Any]] = []
        run = PilotRunORM(
            scenario_id=scenario_id,
            tenant_id=payload.tenant_id,
            project_id=payload.project_id,
            sample_id=payload.sample_id,
            run_label=payload.run_label,
            status="running",
            started_at=started,
            created_at=started,
            summary_json=_json_dump({}, default={}),
            warnings_json=_json_dump([], default=[]),
            notes_json=_json_dump({"execution_mode": "simulated_or_existing_endpoint_where_available"}, default={}),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(run)
        session.flush()

        sequence = _json_list(scenario.program_sequence_json) or list(DEFAULT_PRODUCT_ORDER)
        required_inputs = _json_dict(scenario.required_inputs_json)
        expected_outputs = _json_dict(scenario.expected_outputs_json)
        metadata = _json_dict(scenario.metadata_json)
        endpoint_missing = (
            _contains_missing_endpoint(required_inputs)
            or _contains_missing_endpoint(expected_outputs)
            or _contains_missing_endpoint(metadata)
        )

        for index, sequence_item in enumerate(sequence, start=1):
            module = _module_for_sequence_item(str(sequence_item))
            step_key = MODULE_STEP_KEYS.get(module, "cross_module_review_task")
            now = utcnow()
            output_summary = {
                "step_index": index,
                "module": module,
                "expected_output": "safe summary",
                "review_status": "requires review",
                "resource_links": [],
                "citations_fabricated": False,
                "reaction_recommendation_final_claimed": False,
            }
            if module == "spectracheck":
                output_summary.update({"evidence_item": {"status": "generated", "raw_spectra_included": False}})
            elif module == "regulatory_hub":
                output_summary.update(
                    {
                        "regulatory_action_item": {
                            "status": "requires review",
                            "source_citations_required": True,
                            "uncited_claims_created": False,
                        }
                    }
                )
            elif module == "reaction_optimization":
                output_summary.update(
                    {
                        "reaction_constraint": {
                            "status": "created",
                            "reaction_recommendation_final_claimed": False,
                        }
                    }
                )
            step = PilotRunStepORM(
                pilot_run_id=run.id,
                step_key=step_key,
                module=module,
                status="succeeded",
                input_summary_json=_json_dump(
                    {
                        "scenario_id": scenario_id,
                        "dataset_ids": _json_list(scenario.dataset_ids_json),
                        "safe_summary_only": True,
                    },
                    default={},
                ),
                output_summary_json=_json_dump(output_summary, default={}),
                started_at=now,
                finished_at=now,
                warnings_json=_json_dump([], default=[]),
                notes_json=_json_dump({"endpoint_mode": "simulated_or_existing"}, default={}),
                metadata_json=_json_dump({}, default={}),
            )
            session.add(step)

        if endpoint_missing:
            now = utcnow()
            warning = {
                "warning_type": "missing_endpoint",
                "message": "Scenario requested an endpoint that is not available; step requires review.",
            }
            warnings.append(warning)
            session.add(
                PilotRunStepORM(
                    pilot_run_id=run.id,
                    step_key="missing_endpoint",
                    module="cross_module",
                    status="failed",
                    input_summary_json=_json_dump({"scenario_id": scenario_id, "safe_summary_only": True}, default={}),
                    output_summary_json=_json_dump(
                        {"missing_endpoint": True, "review_status": "requires review"},
                        default={},
                    ),
                    started_at=now,
                    finished_at=now,
                    warnings_json=_json_dump([warning], default=[]),
                    notes_json=_json_dump({"failure_mode": "clear missing_endpoint warning"}, default={}),
                    metadata_json=_json_dump({}, default={}),
                )
            )

        finished = utcnow()
        run.status = "requires_review" if endpoint_missing else "succeeded"
        run.finished_at = finished
        run.score = 75.0 if endpoint_missing else 100.0
        run.warnings_json = _json_dump(warnings, default=[])
        run.summary_json = _json_dump(
            {
                "golden_scenario": scenario.scenario_key,
                "product_order": DEFAULT_PRODUCT_ORDER,
                "program_sequence": sequence,
                "expected_output_contracts_checked": False,
                "safe_summary_only": True,
                "customer_data_mixed_with_demo": False,
                "review_status": "requires review" if endpoint_missing else "ready for review",
            },
            default={},
        )
        session.flush()
        return _pilot_run_detail(session, run)


def list_pilot_runs(
    session_factory: sessionmaker[Session],
    *,
    tenant_id: int | None = None,
    limit: int = 200,
) -> list[PilotRun]:
    with session_scope(session_factory) as session:
        stmt = select(PilotRunORM).order_by(PilotRunORM.id.desc()).limit(limit)
        if tenant_id is not None:
            stmt = stmt.where(PilotRunORM.tenant_id == tenant_id)
        return [_pilot_run_to_record(row) for row in session.scalars(stmt).all()]


def get_pilot_run(session_factory: sessionmaker[Session], pilot_run_id: int) -> PilotRunDetail | None:
    with session_scope(session_factory) as session:
        row = session.get(PilotRunORM, pilot_run_id)
        return _pilot_run_detail(session, row) if row is not None else None


def validate_pilot_run(
    session_factory: sessionmaker[Session],
    pilot_run_id: int,
) -> list[ScenarioValidationResult]:
    with session_scope(session_factory) as session:
        run = _require_pilot_run(session, pilot_run_id)
        scenario = _require_scenario(session, run.scenario_id)
        contracts = session.scalars(
            select(ExpectedOutputContractORM)
            .where(ExpectedOutputContractORM.scenario_id == scenario.id)
            .order_by(ExpectedOutputContractORM.id.asc())
        ).all()
        steps = session.scalars(
            select(PilotRunStepORM).where(PilotRunStepORM.pilot_run_id == run.id).order_by(PilotRunStepORM.id.asc())
        ).all()
        results: list[ScenarioValidationResult] = []
        if not contracts:
            row = ScenarioValidationResultORM(
                pilot_run_id=run.id,
                scenario_id=scenario.id,
                contract_id=None,
                validation_status="not_assessed",
                expected_json=_json_dump({"contracts": []}, default={}),
                actual_json=_json_dump({"pilot_run_status": run.status}, default={}),
                differences_json=_json_dump({"message": "No expected output contracts were defined."}, default={}),
                score=None,
                metadata_json=_json_dump({}, default={}),
            )
            session.add(row)
            session.flush()
            return [_validation_result_to_record(row)]

        for contract in contracts:
            matching_step = next((step for step in steps if step.step_key == contract.step_key), None)
            if matching_step is None:
                matching_step = next((step for step in steps if step.module == contract.target_module), None)
            actual_json = _json_dict(matching_step.output_summary_json) if matching_step is not None else {}
            required_fields = [str(item) for item in _json_list(contract.required_fields_json)]
            forbidden_fields = [str(item) for item in _json_list(contract.forbidden_fields_json)]
            expected_statuses = [str(item) for item in _json_list(contract.expected_statuses_json)]
            missing_required_fields = [field for field in required_fields if not _has_path(actual_json, field)]
            forbidden_fields_present = [field for field in forbidden_fields if _has_path(actual_json, field)]
            status_mismatch = bool(
                expected_statuses
                and (matching_step is None or matching_step.status not in expected_statuses)
            )
            differences = {
                "missing_required_fields": missing_required_fields,
                "forbidden_fields_present": forbidden_fields_present,
                "status_mismatch": status_mismatch,
                "step_found": matching_step is not None,
            }
            validation_status = "pass"
            score = 100.0
            if missing_required_fields or forbidden_fields_present or status_mismatch or matching_step is None:
                validation_status = "fail"
                score = 0.0
            elif _json_list(run.warnings_json) or (matching_step and _json_list(matching_step.warnings_json)):
                validation_status = "warning"
                score = 85.0
            row = ScenarioValidationResultORM(
                pilot_run_id=run.id,
                scenario_id=scenario.id,
                contract_id=contract.id,
                validation_status=validation_status,
                expected_json=_json_dump(
                    {
                        "step_key": contract.step_key,
                        "target_module": contract.target_module,
                        "required_fields": required_fields,
                        "forbidden_fields": forbidden_fields,
                        "expected_statuses": expected_statuses,
                    },
                    default={},
                ),
                actual_json=_json_dump(
                    {
                        "step_status": matching_step.status if matching_step is not None else None,
                        "output_summary": actual_json,
                    },
                    default={},
                ),
                differences_json=_json_dump(differences, default={}),
                score=score,
                metadata_json=_json_dump({}, default={}),
            )
            session.add(row)
            session.flush()
            results.append(_validation_result_to_record(row))
        run.summary_json = _json_dump(
            {
                **_json_dict(run.summary_json),
                "expected_output_contracts_checked": True,
                "validation_result_count": len(results),
            },
            default={},
        )
        run.score = min((result.score for result in results if result.score is not None), default=run.score)
        return results


def list_validation_results(
    session_factory: sessionmaker[Session],
    pilot_run_id: int,
) -> list[ScenarioValidationResult]:
    with session_scope(session_factory) as session:
        _require_pilot_run(session, pilot_run_id)
        rows = session.scalars(
            select(ScenarioValidationResultORM)
            .where(ScenarioValidationResultORM.pilot_run_id == pilot_run_id)
            .order_by(ScenarioValidationResultORM.id.asc())
        ).all()
        return [_validation_result_to_record(row) for row in rows]


def create_acceptance_protocol(
    session_factory: sessionmaker[Session],
    payload: CustomerAcceptanceProtocolCreate,
) -> CustomerAcceptanceProtocol:
    with session_scope(session_factory) as session:
        if payload.tenant_id is not None:
            _require_tenant(session, payload.tenant_id)
        for scenario_id in payload.scenario_ids_json:
            _require_scenario(session, scenario_id)
        row = CustomerAcceptanceProtocolORM(
            tenant_id=payload.tenant_id,
            pilot_program_id=payload.pilot_program_id,
            title=payload.title,
            scope=payload.scope,
            scenario_ids_json=_json_dump(payload.scenario_ids_json, default=[]),
            acceptance_tests_json=_json_dump(payload.acceptance_tests_json, default=[]),
            success_criteria_json=_json_dump(payload.success_criteria_json, default=[]),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()

        test_specs = payload.acceptance_tests_json
        if not test_specs:
            test_specs = [
                {
                    "test_key": f"scenario-{scenario_id}-acceptance",
                    "title": f"Scenario {scenario_id} pilot acceptance",
                    "description": "Confirm expected output and review required evidence bundle.",
                    "scenario_id": scenario_id,
                    "expected_result": "Pilot acceptance evidence requires review.",
                }
                for scenario_id in payload.scenario_ids_json
            ]
        for index, test_spec in enumerate(test_specs, start=1):
            scenario_id = test_spec.get("scenario_id")
            if scenario_id is not None:
                _require_scenario(session, int(scenario_id))
            session.add(
                CustomerAcceptanceTestORM(
                    protocol_id=row.id,
                    test_key=str(test_spec.get("test_key") or f"acceptance-test-{index}"),
                    title=str(test_spec.get("title") or f"Acceptance test {index}"),
                    description=str(test_spec.get("description") or "Pilot acceptance test."),
                    scenario_id=int(scenario_id) if scenario_id is not None else None,
                    expected_result=str(test_spec.get("expected_result") or "Expected output requires review."),
                    status=str(test_spec.get("status") or "not_run"),
                    evidence_json=_json_dump(test_spec.get("evidence_json", {}), default={}),
                    metadata_json=_json_dump(test_spec.get("metadata_json", {}), default={}),
                )
            )
        session.flush()
        return _acceptance_protocol_to_record(row)


def list_acceptance_protocols(
    session_factory: sessionmaker[Session],
    *,
    tenant_id: int | None = None,
    limit: int = 200,
) -> list[CustomerAcceptanceProtocol]:
    with session_scope(session_factory) as session:
        stmt = select(CustomerAcceptanceProtocolORM).order_by(CustomerAcceptanceProtocolORM.id.desc()).limit(limit)
        if tenant_id is not None:
            stmt = stmt.where(CustomerAcceptanceProtocolORM.tenant_id == tenant_id)
        return [_acceptance_protocol_to_record(row) for row in session.scalars(stmt).all()]


def get_acceptance_protocol(
    session_factory: sessionmaker[Session],
    protocol_id: int,
) -> CustomerAcceptanceProtocol | None:
    with session_scope(session_factory) as session:
        row = session.get(CustomerAcceptanceProtocolORM, protocol_id)
        return _acceptance_protocol_to_record(row) if row is not None else None


def update_acceptance_protocol(
    session_factory: sessionmaker[Session],
    protocol_id: int,
    payload: CustomerAcceptanceProtocolUpdate,
) -> CustomerAcceptanceProtocol | None:
    with session_scope(session_factory) as session:
        row = session.get(CustomerAcceptanceProtocolORM, protocol_id)
        if row is None:
            return None
        update_data = payload.model_dump(exclude_unset=True)
        if "tenant_id" in update_data and update_data["tenant_id"] is not None:
            _require_tenant(session, int(update_data["tenant_id"]))
        for scenario_id in update_data.get("scenario_ids_json", _json_list(row.scenario_ids_json)):
            _require_scenario(session, int(scenario_id))
        for field, value in update_data.items():
            if field in {"scenario_ids_json", "acceptance_tests_json", "success_criteria_json"}:
                setattr(row, field, _json_dump(value, default=[]))
            elif field == "metadata_json":
                row.metadata_json = _json_dump(value, default={})
            elif value is not None:
                setattr(row, field, value)
        row.updated_at = utcnow()
        session.flush()
        return _acceptance_protocol_to_record(row)


def list_acceptance_tests(session_factory: sessionmaker[Session], protocol_id: int) -> list[CustomerAcceptanceTest]:
    with session_scope(session_factory) as session:
        if session.get(CustomerAcceptanceProtocolORM, protocol_id) is None:
            raise GoldenPilotNotFoundError("Customer acceptance protocol not found.")
        rows = session.scalars(
            select(CustomerAcceptanceTestORM)
            .where(CustomerAcceptanceTestORM.protocol_id == protocol_id)
            .order_by(CustomerAcceptanceTestORM.id.asc())
        ).all()
        return [_acceptance_test_to_record(row) for row in rows]


def get_acceptance_test(session_factory: sessionmaker[Session], test_id: int) -> CustomerAcceptanceTest | None:
    with session_scope(session_factory) as session:
        row = session.get(CustomerAcceptanceTestORM, test_id)
        return _acceptance_test_to_record(row) if row is not None else None


def execute_acceptance_test(
    session_factory: sessionmaker[Session],
    test_id: int,
    payload: CustomerAcceptanceTestExecute,
) -> CustomerAcceptanceTest | None:
    with session_scope(session_factory) as session:
        row = session.get(CustomerAcceptanceTestORM, test_id)
        if row is None:
            return None
        row.status = payload.status
        row.executed_by = payload.executed_by
        row.executed_at = utcnow()
        row.evidence_json = _json_dump(payload.evidence_json, default={})
        row.metadata_json = _json_dump(payload.metadata_json, default={})
        session.flush()
        return _acceptance_test_to_record(row)


def create_readiness_assessment(
    session_factory: sessionmaker[Session],
    payload: PilotReadinessAssessmentCreate,
) -> PilotReadinessAssessment:
    with session_scope(session_factory) as session:
        if payload.tenant_id is not None:
            _require_tenant(session, payload.tenant_id)
        default_module = {"status": "ready_for_pilot", "safe_summary_only": True}
        warnings = list(_safe_json(payload.warnings_json))
        readiness_status = payload.readiness_status or ("partially_ready" if warnings else "ready_for_pilot")
        row = PilotReadinessAssessmentORM(
            tenant_id=payload.tenant_id,
            pilot_program_id=payload.pilot_program_id,
            onboarding_project_id=payload.onboarding_project_id,
            readiness_status=readiness_status,
            spectracheck_readiness_json=_json_dump(payload.spectracheck_readiness_json or default_module, default={}),
            regulatory_readiness_json=_json_dump(payload.regulatory_readiness_json or default_module, default={}),
            reaction_readiness_json=_json_dump(payload.reaction_readiness_json or default_module, default={}),
            connector_readiness_json=_json_dump(payload.connector_readiness_json, default={}),
            validation_readiness_json=_json_dump(payload.validation_readiness_json, default={}),
            mobile_readiness_json=_json_dump(payload.mobile_readiness_json, default={}),
            security_readiness_json=_json_dump(payload.security_readiness_json, default={}),
            warnings_json=_json_dump(warnings, default=[]),
            recommended_actions_json=_json_dump(payload.recommended_actions_json, default=[]),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _readiness_to_record(row)


def list_readiness_assessments(
    session_factory: sessionmaker[Session],
    *,
    tenant_id: int | None = None,
    limit: int = 200,
) -> list[PilotReadinessAssessment]:
    with session_scope(session_factory) as session:
        stmt = select(PilotReadinessAssessmentORM).order_by(PilotReadinessAssessmentORM.id.desc()).limit(limit)
        if tenant_id is not None:
            stmt = stmt.where(PilotReadinessAssessmentORM.tenant_id == tenant_id)
        return [_readiness_to_record(row) for row in session.scalars(stmt).all()]


def get_readiness_assessment(
    session_factory: sessionmaker[Session],
    assessment_id: int,
) -> PilotReadinessAssessment | None:
    with session_scope(session_factory) as session:
        row = session.get(PilotReadinessAssessmentORM, assessment_id)
        return _readiness_to_record(row) if row is not None else None


def create_signoff(session_factory: sessionmaker[Session], payload: PilotSignoffCreate) -> PilotSignoffRecord:
    with session_scope(session_factory) as session:
        if payload.tenant_id is not None:
            _require_tenant(session, payload.tenant_id)
        if payload.pilot_run_id is not None:
            run = _require_pilot_run(session, payload.pilot_run_id)
            if payload.tenant_id is not None and run.tenant_id not in (None, payload.tenant_id):
                raise GoldenPilotError("Pilot signoff cannot link resources across tenants.")
        if payload.protocol_id is not None:
            protocol = session.get(CustomerAcceptanceProtocolORM, payload.protocol_id)
            if protocol is None:
                raise GoldenPilotNotFoundError("Customer acceptance protocol not found.")
            if payload.tenant_id is not None and protocol.tenant_id not in (None, payload.tenant_id):
                raise GoldenPilotError("Pilot signoff cannot link resources across tenants.")
        row = PilotSignoffRecordORM(
            tenant_id=payload.tenant_id,
            pilot_run_id=payload.pilot_run_id,
            protocol_id=payload.protocol_id,
            signer_name=payload.signer_name,
            signer_email=payload.signer_email,
            decision=payload.decision,
            rationale=payload.rationale,
            signed_at=utcnow(),
            signature_record_id=payload.signature_record_id,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _signoff_to_record(row)


def set_signoff_signature_record_id(
    session_factory: sessionmaker[Session],
    signoff_id: int,
    signature_record_id: int,
) -> PilotSignoffRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(PilotSignoffRecordORM, signoff_id)
        if row is None:
            return None
        row.signature_record_id = signature_record_id
        metadata = _json_dict(row.metadata_json)
        metadata["esignature_link_status"] = "linked"
        row.metadata_json = _json_dump(metadata, default={})
        session.flush()
        return _signoff_to_record(row)


def get_signoff(session_factory: sessionmaker[Session], signoff_id: int) -> PilotSignoffRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(PilotSignoffRecordORM, signoff_id)
        return _signoff_to_record(row) if row is not None else None


def create_evidence_bundle(
    session_factory: sessionmaker[Session],
    pilot_run_id: int,
    payload: PilotEvidenceBundleCreate,
) -> PilotEvidenceBundle:
    with session_scope(session_factory) as session:
        run = _require_pilot_run(session, pilot_run_id)
        scenario = _require_scenario(session, run.scenario_id)
        steps = session.scalars(
            select(PilotRunStepORM).where(PilotRunStepORM.pilot_run_id == run.id).order_by(PilotRunStepORM.id.asc())
        ).all()
        validation_results = session.scalars(
            select(ScenarioValidationResultORM)
            .where(ScenarioValidationResultORM.pilot_run_id == run.id)
            .order_by(ScenarioValidationResultORM.id.asc())
        ).all()
        included_resources = {
            "pilot_run_id": run.id,
            "scenario_id": scenario.id,
            "step_ids": [step.id for step in steps],
            "validation_result_ids": [result.id for result in validation_results],
        }
        package = {
            "title": payload.title,
            "golden_scenario": {"id": scenario.id, "scenario_key": scenario.scenario_key},
            "pilot_run": {
                "id": run.id,
                "status": run.status,
                "score": run.score,
                "review_status": "requires review" if run.status == "requires_review" else "ready for review",
            },
            "steps": [
                {
                    "id": step.id,
                    "step_key": step.step_key,
                    "module": step.module,
                    "status": step.status,
                    "warnings": _json_list(step.warnings_json),
                }
                for step in steps
            ],
            "validation_results": [
                {
                    "id": result.id,
                    "validation_status": result.validation_status,
                    "score": result.score,
                }
                for result in validation_results
            ],
            "warnings": _json_list(run.warnings_json),
            "resource_ids": included_resources,
            "product_order": DEFAULT_PRODUCT_ORDER,
            "safe_summary_only": True,
            "raw_spectra_included": False,
            "source_text_included": False,
            "secrets_included": False,
        }
        package_sha = _sha256_json(package)
        row = PilotEvidenceBundleORM(
            pilot_run_id=pilot_run_id,
            title=payload.title,
            included_resource_ids_json=_json_dump(included_resources, default={}),
            package_json=_json_dump(package, default={}),
            package_html=None,
            package_sha256=package_sha,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        return _evidence_bundle_to_record(row)


def list_evidence_bundles(session_factory: sessionmaker[Session], pilot_run_id: int) -> list[PilotEvidenceBundle]:
    with session_scope(session_factory) as session:
        _require_pilot_run(session, pilot_run_id)
        rows = session.scalars(
            select(PilotEvidenceBundleORM)
            .where(PilotEvidenceBundleORM.pilot_run_id == pilot_run_id)
            .order_by(PilotEvidenceBundleORM.id.desc())
        ).all()
        return [_evidence_bundle_to_record(row) for row in rows]


def get_customer_dashboard(session_factory: sessionmaker[Session], tenant_id: int) -> PilotCustomerDashboard:
    with session_scope(session_factory) as session:
        _require_tenant(session, tenant_id)
        readiness = session.scalars(
            select(PilotReadinessAssessmentORM)
            .where(PilotReadinessAssessmentORM.tenant_id == tenant_id)
            .order_by(PilotReadinessAssessmentORM.id.desc())
            .limit(1)
        ).first()
        runs = session.scalars(
            select(PilotRunORM)
            .where(PilotRunORM.tenant_id == tenant_id)
            .order_by(PilotRunORM.id.desc())
            .limit(10)
        ).all()
        protocols = session.scalars(
            select(CustomerAcceptanceProtocolORM)
            .where(CustomerAcceptanceProtocolORM.tenant_id == tenant_id)
            .order_by(CustomerAcceptanceProtocolORM.id.desc())
            .limit(10)
        ).all()
        signoffs = session.scalars(
            select(PilotSignoffRecordORM)
            .where(PilotSignoffRecordORM.tenant_id == tenant_id)
            .order_by(PilotSignoffRecordORM.id.desc())
            .limit(10)
        ).all()
        return PilotCustomerDashboard(
            tenant_id=tenant_id,
            product_order=DEFAULT_PRODUCT_ORDER,
            latest_readiness=_readiness_to_record(readiness).model_dump(mode="json") if readiness is not None else {},
            pilot_runs=[
                {
                    "id": row.id,
                    "scenario_id": row.scenario_id,
                    "status": row.status,
                    "score": row.score,
                    "warnings": _json_list(row.warnings_json),
                }
                for row in runs
            ],
            acceptance_protocols=[
                {"id": row.id, "title": row.title, "scope": row.scope, "status": row.status} for row in protocols
            ],
            signoffs=[
                {
                    "id": row.id,
                    "decision": row.decision,
                    "signature_record_id": row.signature_record_id,
                    "signed_at": row.signed_at.isoformat() if row.signed_at else None,
                }
                for row in signoffs
            ],
            warnings_json=[],
        )
