from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import esign
from .database import session_scope
from .models import (
    CAPARecord,
    CAPARecordCreate,
    CAPARecordUpdate,
    ControlledRecord,
    ControlledRecordArchiveRequest,
    ControlledRecordCreate,
    ControlledRecordLockRequest,
    ControlledRecordNewVersionRequest,
    DataIntegrityAssessment,
    DataIntegrityAssessmentCreate,
    DeviationRecord,
    DeviationRecordCreate,
    DeviationRecordUpdate,
    ElectronicSignatureRecord,
    ElectronicSignatureRecordCreate,
    FunctionalSpecification,
    FunctionalSpecificationCreate,
    InspectionReadinessPackage,
    InspectionReadinessPackageCreate,
    RecordRetentionPolicy,
    RecordRetentionPolicyCreate,
    SystemReleaseApproveRequest,
    SystemReleaseRecord,
    SystemReleaseRecordCreate,
    TraceabilityMatrix,
    UserRequirementSpecification,
    UserRequirementSpecificationCreate,
    ValidationProject,
    ValidationProjectCreate,
    ValidationProjectUpdate,
    ValidationRiskAssessment,
    ValidationRiskAssessmentCreate,
    ValidationTestCase,
    ValidationTestCaseCreate,
    ValidationTestExecution,
    ValidationTestExecutionCreate,
    ValidationTestProtocol,
    ValidationTestProtocolCreate,
)
from .orm import (
    AuditEventORM,
    CAPARecordORM,
    ControlledRecordORM,
    DataIntegrityAssessmentORM,
    DeviationRecordORM,
    ElectronicSignatureRecordORM,
    FunctionalSpecificationORM,
    InspectionReadinessPackageORM,
    RecordRetentionPolicyORM,
    SystemReleaseRecordORM,
    TraceabilityMatrixORM,
    UserRequirementSpecificationORM,
    ValidationProjectORM,
    ValidationRiskAssessmentORM,
    ValidationTestCaseORM,
    ValidationTestExecutionORM,
    ValidationTestProtocolORM,
    utcnow,
)


class ValidationCenterError(ValueError):
    pass


class ControlledRecordLockedError(ValidationCenterError):
    pass


DEFAULT_VALIDATION_MODULE_ORDER = [
    "spectracheck",
    "regulatory_hub",
    "reaction_optimization",
    "cross_module",
    "system",
]


_RISK_SCORE = {"low": 1, "medium": 2, "high": 3, "critical": 4, "unknown": 2}
_SAFE_NOTICE = (
    "Part 11 readiness and Annex 11 readiness records are review artifacts; "
    "they do not assert certification or legal compliance."
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


def _hash_json(value: Any) -> str:
    payload = _json_dump(value, default={})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _next_version(version: str) -> str:
    if version.isdigit():
        return str(int(version) + 1)
    match = re.match(r"^(.*?)(\d+)$", version)
    if match:
        return f"{match.group(1)}{int(match.group(2)) + 1}"
    return f"{version}.1"


def _code(prefix: str, row_id: int) -> str:
    return f"{prefix}-{row_id:05d}"


def _ensure_project(session: Session, validation_project_id: int) -> ValidationProjectORM:
    row = session.get(ValidationProjectORM, validation_project_id)
    if row is None:
        raise KeyError("Validation project not found.")
    return row


def _risk_priority(
    severity: str,
    probability: str,
    detectability: str,
    explicit: int | None,
) -> int:
    if explicit is not None:
        return explicit
    return _RISK_SCORE[severity] * _RISK_SCORE[probability] * _RISK_SCORE[detectability]


def _project_to_record(row: ValidationProjectORM) -> ValidationProject:
    return ValidationProject(
        id=row.id,
        title=row.title,
        scope=row.scope,
        validation_type=row.validation_type,
        status=row.status,
        intended_use=row.intended_use,
        regulated_context=row.regulated_context,
        owner_name=row.owner_name,
        qa_reviewer_name=row.qa_reviewer_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _urs_to_record(row: UserRequirementSpecificationORM) -> UserRequirementSpecification:
    return UserRequirementSpecification(
        id=row.id,
        validation_project_id=row.validation_project_id,
        requirement_code=row.requirement_code,
        module=row.module,
        requirement_text=row.requirement_text,
        criticality=row.criticality,
        gxp_impact=row.gxp_impact,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _functional_spec_to_record(row: FunctionalSpecificationORM) -> FunctionalSpecification:
    return FunctionalSpecification(
        id=row.id,
        validation_project_id=row.validation_project_id,
        requirement_id=row.requirement_id,
        function_code=row.function_code,
        function_name=row.function_name,
        function_description=row.function_description,
        expected_behavior=row.expected_behavior,
        module=row.module,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _risk_to_record(row: ValidationRiskAssessmentORM) -> ValidationRiskAssessment:
    return ValidationRiskAssessment(
        id=row.id,
        validation_project_id=row.validation_project_id,
        target_type=row.target_type,
        target_id=row.target_id,
        risk_description=row.risk_description,
        severity=row.severity,
        probability=row.probability,
        detectability=row.detectability,
        risk_priority=row.risk_priority,
        mitigation=row.mitigation,
        testing_rigor=row.testing_rigor,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _protocol_to_record(row: ValidationTestProtocolORM) -> ValidationTestProtocol:
    return ValidationTestProtocol(
        id=row.id,
        validation_project_id=row.validation_project_id,
        protocol_code=row.protocol_code,
        title=row.title,
        module=row.module,
        protocol_type=row.protocol_type,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _test_case_to_record(row: ValidationTestCaseORM) -> ValidationTestCase:
    return ValidationTestCase(
        id=row.id,
        protocol_id=row.protocol_id,
        test_case_code=row.test_case_code,
        title=row.title,
        preconditions=row.preconditions,
        steps_json=[item for item in _json_list(row.steps_json) if isinstance(item, dict)],
        expected_results=row.expected_results,
        linked_requirement_ids_json=_int_list(row.linked_requirement_ids_json),
        linked_risk_ids_json=_int_list(row.linked_risk_ids_json),
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _execution_to_record(row: ValidationTestExecutionORM) -> ValidationTestExecution:
    return ValidationTestExecution(
        id=row.id,
        test_case_id=row.test_case_id,
        executed_by=row.executed_by,
        execution_status=row.execution_status,
        actual_results=row.actual_results,
        evidence_file_ids_json=_int_list(row.evidence_file_ids_json),
        evidence_artifact_ids_json=_int_list(row.evidence_artifact_ids_json),
        deviation_id=row.deviation_id,
        executed_at=row.executed_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _traceability_to_record(row: TraceabilityMatrixORM) -> TraceabilityMatrix:
    return TraceabilityMatrix(
        id=row.id,
        validation_project_id=row.validation_project_id,
        matrix_json=_json_dict(row.matrix_json),
        coverage_summary_json=_json_dict(row.coverage_summary_json),
        missing_coverage_json=[
            item for item in _json_list(row.missing_coverage_json) if isinstance(item, dict)
        ],
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _signature_to_record(row: ElectronicSignatureRecordORM) -> ElectronicSignatureRecord:
    return ElectronicSignatureRecord(
        id=row.id,
        signer_name=row.signer_name,
        signer_email=row.signer_email,
        signature_meaning=row.signature_meaning,
        target_type=row.target_type,
        target_id=row.target_id,
        reason=row.reason,
        signed_at=row.signed_at,
        authentication_method=row.authentication_method,
        signature_hash=row.signature_hash,
        signer_user_id=row.signer_user_id,
        record_content_hash=row.record_content_hash,
        signature_digest=row.signature_digest,
        metadata_json=_json_dict(row.metadata_json),
    )


def _controlled_record_to_record(row: ControlledRecordORM) -> ControlledRecord:
    return ControlledRecord(
        id=row.id,
        record_type=row.record_type,
        resource_id=row.resource_id,
        title=row.title,
        version=row.version,
        status=row.status,
        content_hash=row.content_hash,
        locked_at=row.locked_at,
        locked_by=row.locked_by,
        retention_policy_id=row.retention_policy_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _retention_policy_to_record(row: RecordRetentionPolicyORM) -> RecordRetentionPolicy:
    return RecordRetentionPolicy(
        id=row.id,
        name=row.name,
        record_type=row.record_type,
        retention_period_years=row.retention_period_years,
        archive_strategy=row.archive_strategy,
        legal_hold=row.legal_hold,
        status=row.status,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _data_integrity_to_record(row: DataIntegrityAssessmentORM) -> DataIntegrityAssessment:
    return DataIntegrityAssessment(
        id=row.id,
        scope=row.scope,
        scope_id=row.scope_id,
        assessment_status=row.assessment_status,
        attributable_status=row.attributable_status,
        legible_status=row.legible_status,
        contemporaneous_status=row.contemporaneous_status,
        original_status=row.original_status,
        accurate_status=row.accurate_status,
        complete_status=row.complete_status,
        consistent_status=row.consistent_status,
        enduring_status=row.enduring_status,
        available_status=row.available_status,
        findings_json=[item for item in _json_list(row.findings_json) if isinstance(item, dict)],
        recommended_actions_json=[
            item for item in _json_list(row.recommended_actions_json) if isinstance(item, dict)
        ],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _inspection_package_to_record(row: InspectionReadinessPackageORM) -> InspectionReadinessPackage:
    return InspectionReadinessPackage(
        id=row.id,
        title=row.title,
        scope=row.scope,
        scope_id=row.scope_id,
        package_status=row.package_status,
        included_record_ids_json=_int_list(row.included_record_ids_json),
        included_signature_ids_json=_int_list(row.included_signature_ids_json),
        included_audit_event_ids_json=_int_list(row.included_audit_event_ids_json),
        included_validation_project_ids_json=_int_list(row.included_validation_project_ids_json),
        package_manifest_json=_json_dict(row.package_manifest_json),
        package_sha256=row.package_sha256,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _release_to_record(row: SystemReleaseRecordORM) -> SystemReleaseRecord:
    return SystemReleaseRecord(
        id=row.id,
        release_version=row.release_version,
        release_type=row.release_type,
        change_summary=row.change_summary,
        validation_project_id=row.validation_project_id,
        test_summary_json=_json_dict(row.test_summary_json),
        risk_summary_json=_json_dict(row.risk_summary_json),
        approval_status=row.approval_status,
        created_at=row.created_at,
        released_at=row.released_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _deviation_to_record(row: DeviationRecordORM) -> DeviationRecord:
    return DeviationRecord(
        id=row.id,
        deviation_code=row.deviation_code,
        title=row.title,
        description=row.description,
        severity=row.severity,
        source_type=row.source_type,
        source_id=row.source_id,
        status=row.status,
        root_cause=row.root_cause,
        resolution=row.resolution,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _capa_to_record(row: CAPARecordORM) -> CAPARecord:
    return CAPARecord(
        id=row.id,
        capa_code=row.capa_code,
        title=row.title,
        description=row.description,
        source_deviation_id=row.source_deviation_id,
        corrective_action=row.corrective_action,
        preventive_action=row.preventive_action,
        owner=row.owner,
        due_date=row.due_date,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def create_validation_project(
    session_factory: sessionmaker[Session],
    payload: ValidationProjectCreate,
) -> ValidationProject:
    metadata = {
        **payload.metadata_json,
        "module_order": DEFAULT_VALIDATION_MODULE_ORDER,
        "readiness_notice": _SAFE_NOTICE,
    }
    with session_scope(session_factory) as session:
        row = ValidationProjectORM(
            title=payload.title,
            scope=payload.scope,
            validation_type=payload.validation_type,
            status=payload.status,
            intended_use=payload.intended_use,
            regulated_context=payload.regulated_context,
            owner_name=payload.owner_name,
            qa_reviewer_name=payload.qa_reviewer_name,
            metadata_json=_json_dump(metadata, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _project_to_record(row)


def list_validation_projects(
    session_factory: sessionmaker[Session],
    *,
    status_filter: str | None = None,
    scope: str | None = None,
    limit: int = 200,
) -> list[ValidationProject]:
    with session_scope(session_factory) as session:
        stmt = select(ValidationProjectORM).order_by(ValidationProjectORM.id.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(ValidationProjectORM.status == status_filter)
        if scope:
            stmt = stmt.where(ValidationProjectORM.scope == scope)
        return [_project_to_record(row) for row in session.scalars(stmt).all()]


def get_validation_project(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
) -> ValidationProject | None:
    with session_scope(session_factory) as session:
        row = session.get(ValidationProjectORM, validation_project_id)
        return _project_to_record(row) if row is not None else None


def update_validation_project(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
    payload: ValidationProjectUpdate,
) -> ValidationProject | None:
    with session_scope(session_factory) as session:
        row = session.get(ValidationProjectORM, validation_project_id)
        if row is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        for field in (
            "title",
            "scope",
            "validation_type",
            "status",
            "intended_use",
            "regulated_context",
            "owner_name",
            "qa_reviewer_name",
        ):
            if field in data:
                setattr(row, field, data[field])
        if "metadata_json" in data:
            row.metadata_json = _json_dump(data["metadata_json"], default={})
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _project_to_record(row)


def create_urs(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
    payload: UserRequirementSpecificationCreate,
) -> UserRequirementSpecification:
    with session_scope(session_factory) as session:
        _ensure_project(session, validation_project_id)
        row = UserRequirementSpecificationORM(
            validation_project_id=validation_project_id,
            requirement_code=payload.requirement_code,
            module=payload.module,
            requirement_text=payload.requirement_text,
            criticality=payload.criticality,
            gxp_impact=payload.gxp_impact,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _urs_to_record(row)


def list_urs(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
    *,
    limit: int = 500,
) -> list[UserRequirementSpecification]:
    with session_scope(session_factory) as session:
        _ensure_project(session, validation_project_id)
        stmt = (
            select(UserRequirementSpecificationORM)
            .where(UserRequirementSpecificationORM.validation_project_id == validation_project_id)
            .order_by(UserRequirementSpecificationORM.id.asc())
            .limit(limit)
        )
        return [_urs_to_record(row) for row in session.scalars(stmt).all()]


def create_functional_spec(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
    payload: FunctionalSpecificationCreate,
) -> FunctionalSpecification:
    with session_scope(session_factory) as session:
        _ensure_project(session, validation_project_id)
        if payload.requirement_id is not None:
            requirement = session.get(UserRequirementSpecificationORM, payload.requirement_id)
            if requirement is None or requirement.validation_project_id != validation_project_id:
                raise KeyError("User requirement specification not found for validation project.")
        row = FunctionalSpecificationORM(
            validation_project_id=validation_project_id,
            requirement_id=payload.requirement_id,
            function_code=payload.function_code,
            function_name=payload.function_name,
            function_description=payload.function_description,
            expected_behavior=payload.expected_behavior,
            module=payload.module,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _functional_spec_to_record(row)


def list_functional_specs(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
    *,
    limit: int = 500,
) -> list[FunctionalSpecification]:
    with session_scope(session_factory) as session:
        _ensure_project(session, validation_project_id)
        stmt = (
            select(FunctionalSpecificationORM)
            .where(FunctionalSpecificationORM.validation_project_id == validation_project_id)
            .order_by(FunctionalSpecificationORM.id.asc())
            .limit(limit)
        )
        return [_functional_spec_to_record(row) for row in session.scalars(stmt).all()]


def create_risk_assessment(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
    payload: ValidationRiskAssessmentCreate,
) -> ValidationRiskAssessment:
    with session_scope(session_factory) as session:
        _ensure_project(session, validation_project_id)
        row = ValidationRiskAssessmentORM(
            validation_project_id=validation_project_id,
            target_type=payload.target_type,
            target_id=payload.target_id,
            risk_description=payload.risk_description,
            severity=payload.severity,
            probability=payload.probability,
            detectability=payload.detectability,
            risk_priority=_risk_priority(
                payload.severity,
                payload.probability,
                payload.detectability,
                payload.risk_priority,
            ),
            mitigation=payload.mitigation,
            testing_rigor=payload.testing_rigor,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _risk_to_record(row)


def list_risk_assessments(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
    *,
    limit: int = 500,
) -> list[ValidationRiskAssessment]:
    with session_scope(session_factory) as session:
        _ensure_project(session, validation_project_id)
        stmt = (
            select(ValidationRiskAssessmentORM)
            .where(ValidationRiskAssessmentORM.validation_project_id == validation_project_id)
            .order_by(ValidationRiskAssessmentORM.id.asc())
            .limit(limit)
        )
        return [_risk_to_record(row) for row in session.scalars(stmt).all()]


def create_test_protocol(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
    payload: ValidationTestProtocolCreate,
) -> ValidationTestProtocol:
    with session_scope(session_factory) as session:
        _ensure_project(session, validation_project_id)
        row = ValidationTestProtocolORM(
            validation_project_id=validation_project_id,
            protocol_code=payload.protocol_code,
            title=payload.title,
            module=payload.module,
            protocol_type=payload.protocol_type,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _protocol_to_record(row)


def list_test_protocols(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
    *,
    limit: int = 500,
) -> list[ValidationTestProtocol]:
    with session_scope(session_factory) as session:
        _ensure_project(session, validation_project_id)
        stmt = (
            select(ValidationTestProtocolORM)
            .where(ValidationTestProtocolORM.validation_project_id == validation_project_id)
            .order_by(ValidationTestProtocolORM.id.asc())
            .limit(limit)
        )
        return [_protocol_to_record(row) for row in session.scalars(stmt).all()]


def get_test_protocol(
    session_factory: sessionmaker[Session],
    protocol_id: int,
) -> ValidationTestProtocol | None:
    with session_scope(session_factory) as session:
        row = session.get(ValidationTestProtocolORM, protocol_id)
        return _protocol_to_record(row) if row is not None else None


def create_test_case(
    session_factory: sessionmaker[Session],
    protocol_id: int,
    payload: ValidationTestCaseCreate,
) -> ValidationTestCase:
    with session_scope(session_factory) as session:
        protocol = session.get(ValidationTestProtocolORM, protocol_id)
        if protocol is None:
            raise KeyError("Validation test protocol not found.")
        row = ValidationTestCaseORM(
            protocol_id=protocol_id,
            test_case_code=payload.test_case_code,
            title=payload.title,
            preconditions=payload.preconditions,
            steps_json=_json_dump(payload.steps_json, default=[]),
            expected_results=payload.expected_results,
            linked_requirement_ids_json=_json_dump(payload.linked_requirement_ids_json, default=[]),
            linked_risk_ids_json=_json_dump(payload.linked_risk_ids_json, default=[]),
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _test_case_to_record(row)


def list_test_cases(
    session_factory: sessionmaker[Session],
    protocol_id: int,
    *,
    limit: int = 500,
) -> list[ValidationTestCase]:
    with session_scope(session_factory) as session:
        if session.get(ValidationTestProtocolORM, protocol_id) is None:
            raise KeyError("Validation test protocol not found.")
        stmt = (
            select(ValidationTestCaseORM)
            .where(ValidationTestCaseORM.protocol_id == protocol_id)
            .order_by(ValidationTestCaseORM.id.asc())
            .limit(limit)
        )
        return [_test_case_to_record(row) for row in session.scalars(stmt).all()]


def _create_deviation_row(
    session: Session,
    *,
    title: str,
    description: str,
    severity: str,
    source_type: str,
    source_id: int | None,
    metadata_json: dict[str, Any] | None = None,
) -> DeviationRecordORM:
    row = DeviationRecordORM(
        deviation_code="pending",
        title=title,
        description=description,
        severity=severity,
        source_type=source_type,
        source_id=source_id,
        status="open",
        metadata_json=_json_dump(metadata_json or {}, default={}),
    )
    session.add(row)
    session.flush()
    row.deviation_code = _code("DEV", row.id)
    return row


def execute_test_case(
    session_factory: sessionmaker[Session],
    test_case_id: int,
    payload: ValidationTestExecutionCreate,
) -> ValidationTestExecution:
    with session_scope(session_factory) as session:
        test_case = session.get(ValidationTestCaseORM, test_case_id)
        if test_case is None:
            raise KeyError("Validation test case not found.")
        deviation_id = payload.deviation_id
        if deviation_id is not None and session.get(DeviationRecordORM, deviation_id) is None:
            raise KeyError("Deviation record not found.")
        execution = ValidationTestExecutionORM(
            test_case_id=test_case_id,
            executed_by=payload.executed_by,
            execution_status=payload.execution_status,
            actual_results=payload.actual_results,
            evidence_file_ids_json=_json_dump(payload.evidence_file_ids_json, default=[]),
            evidence_artifact_ids_json=_json_dump(payload.evidence_artifact_ids_json, default=[]),
            deviation_id=deviation_id,
            executed_at=utcnow(),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(execution)
        session.flush()
        if payload.execution_status == "fail" and deviation_id is None and payload.create_deviation_on_fail:
            deviation = _create_deviation_row(
                session,
                title=f"Failed validation test {test_case.test_case_code}",
                description=payload.actual_results,
                severity="high",
                source_type="validation_test",
                source_id=execution.id,
                metadata_json={"test_case_id": test_case_id, "auto_created": True},
            )
            execution.deviation_id = deviation.id
        test_case.status = "executed"
        session.flush()
        session.refresh(execution)
        return _execution_to_record(execution)


def list_test_executions(
    session_factory: sessionmaker[Session],
    *,
    status_filter: str | None = None,
    limit: int = 500,
) -> list[ValidationTestExecution]:
    with session_scope(session_factory) as session:
        stmt = select(ValidationTestExecutionORM).order_by(ValidationTestExecutionORM.id.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(ValidationTestExecutionORM.execution_status == status_filter)
        return [_execution_to_record(row) for row in session.scalars(stmt).all()]


def get_test_execution(
    session_factory: sessionmaker[Session],
    execution_id: int,
) -> ValidationTestExecution | None:
    with session_scope(session_factory) as session:
        row = session.get(ValidationTestExecutionORM, execution_id)
        return _execution_to_record(row) if row is not None else None


def _traceability_components(session: Session, validation_project_id: int) -> dict[str, Any]:
    requirements = session.scalars(
        select(UserRequirementSpecificationORM)
        .where(UserRequirementSpecificationORM.validation_project_id == validation_project_id)
        .order_by(UserRequirementSpecificationORM.id.asc())
    ).all()
    functions = session.scalars(
        select(FunctionalSpecificationORM)
        .where(FunctionalSpecificationORM.validation_project_id == validation_project_id)
        .order_by(FunctionalSpecificationORM.id.asc())
    ).all()
    risks = session.scalars(
        select(ValidationRiskAssessmentORM)
        .where(ValidationRiskAssessmentORM.validation_project_id == validation_project_id)
        .order_by(ValidationRiskAssessmentORM.id.asc())
    ).all()
    protocols = session.scalars(
        select(ValidationTestProtocolORM)
        .where(ValidationTestProtocolORM.validation_project_id == validation_project_id)
        .order_by(ValidationTestProtocolORM.id.asc())
    ).all()
    protocol_ids = [row.id for row in protocols]
    test_cases = (
        session.scalars(
            select(ValidationTestCaseORM)
            .where(ValidationTestCaseORM.protocol_id.in_(protocol_ids))
            .order_by(ValidationTestCaseORM.id.asc())
        ).all()
        if protocol_ids
        else []
    )
    case_ids = [row.id for row in test_cases]
    executions = (
        session.scalars(
            select(ValidationTestExecutionORM)
            .where(ValidationTestExecutionORM.test_case_id.in_(case_ids))
            .order_by(ValidationTestExecutionORM.id.asc())
        ).all()
        if case_ids
        else []
    )
    return {
        "requirements": requirements,
        "functions": functions,
        "risks": risks,
        "protocols": protocols,
        "test_cases": test_cases,
        "executions": executions,
    }


def generate_traceability(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
) -> TraceabilityMatrix:
    with session_scope(session_factory) as session:
        _ensure_project(session, validation_project_id)
        components = _traceability_components(session, validation_project_id)
        functions_by_requirement: dict[int, list[FunctionalSpecificationORM]] = {}
        for function in components["functions"]:
            if function.requirement_id is not None:
                functions_by_requirement.setdefault(function.requirement_id, []).append(function)
        test_cases_by_requirement: dict[int, list[ValidationTestCaseORM]] = {}
        test_cases_by_risk: dict[int, list[ValidationTestCaseORM]] = {}
        for case in components["test_cases"]:
            for requirement_id in _int_list(case.linked_requirement_ids_json):
                test_cases_by_requirement.setdefault(requirement_id, []).append(case)
            for risk_id in _int_list(case.linked_risk_ids_json):
                test_cases_by_risk.setdefault(risk_id, []).append(case)
        executions_by_case: dict[int, list[ValidationTestExecutionORM]] = {}
        for execution in components["executions"]:
            executions_by_case.setdefault(execution.test_case_id, []).append(execution)

        rows: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for requirement in components["requirements"]:
            linked_functions = functions_by_requirement.get(requirement.id, [])
            linked_risks = [
                risk
                for risk in components["risks"]
                if risk.target_type == "requirement" and risk.target_id == requirement.id
            ]
            linked_cases = test_cases_by_requirement.get(requirement.id, [])
            evidence_file_ids: list[int] = []
            evidence_artifact_ids: list[int] = []
            execution_statuses: list[str] = []
            for case in linked_cases:
                for execution in executions_by_case.get(case.id, []):
                    execution_statuses.append(execution.execution_status)
                    evidence_file_ids.extend(_int_list(execution.evidence_file_ids_json))
                    evidence_artifact_ids.extend(_int_list(execution.evidence_artifact_ids_json))
            if not linked_functions:
                missing.append(
                    {
                        "requirement_id": requirement.id,
                        "requirement_code": requirement.requirement_code,
                        "gap_type": "missing_function",
                    }
                )
            if not linked_risks:
                missing.append(
                    {
                        "requirement_id": requirement.id,
                        "requirement_code": requirement.requirement_code,
                        "gap_type": "missing_risk",
                    }
                )
            if not linked_cases:
                missing.append(
                    {
                        "requirement_id": requirement.id,
                        "requirement_code": requirement.requirement_code,
                        "gap_type": "missing_test_case",
                    }
                )
            if linked_cases and not execution_statuses:
                missing.append(
                    {
                        "requirement_id": requirement.id,
                        "requirement_code": requirement.requirement_code,
                        "gap_type": "missing_execution",
                    }
                )
            rows.append(
                {
                    "requirement_id": requirement.id,
                    "requirement_code": requirement.requirement_code,
                    "function_ids": [row.id for row in linked_functions],
                    "risk_ids": [row.id for row in linked_risks],
                    "test_case_ids": [row.id for row in linked_cases],
                    "execution_statuses": execution_statuses,
                    "evidence_file_ids": sorted(set(evidence_file_ids)),
                    "evidence_artifact_ids": sorted(set(evidence_artifact_ids)),
                }
            )
        risk_case_gaps = [
            {
                "risk_id": risk.id,
                "gap_type": "risk_missing_test_case",
            }
            for risk in components["risks"]
            if not test_cases_by_risk.get(risk.id)
        ]
        missing.extend(risk_case_gaps)
        summary = {
            "requirement_count": len(components["requirements"]),
            "function_count": len(components["functions"]),
            "risk_count": len(components["risks"]),
            "test_case_count": len(components["test_cases"]),
            "execution_count": len(components["executions"]),
            "missing_coverage_count": len(missing),
        }
        matrix = {
            "module_order": DEFAULT_VALIDATION_MODULE_ORDER,
            "rows": rows,
            "notice": _SAFE_NOTICE,
        }
        status = "gaps_identified" if missing else "complete"
        row = TraceabilityMatrixORM(
            validation_project_id=validation_project_id,
            matrix_json=_json_dump(matrix, default={}),
            coverage_summary_json=_json_dump(summary, default={}),
            missing_coverage_json=_json_dump(missing, default=[]),
            status=status,
            metadata_json=_json_dump({"generated": True}, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _traceability_to_record(row)


def get_latest_traceability(
    session_factory: sessionmaker[Session],
    validation_project_id: int,
) -> TraceabilityMatrix | None:
    with session_scope(session_factory) as session:
        _ensure_project(session, validation_project_id)
        row = session.scalar(
            select(TraceabilityMatrixORM)
            .where(TraceabilityMatrixORM.validation_project_id == validation_project_id)
            .order_by(TraceabilityMatrixORM.id.desc())
            .limit(1)
        )
        return _traceability_to_record(row) if row is not None else None


def _create_signature_row(
    session: Session,
    payload: ElectronicSignatureRecordCreate,
    *,
    signer_user_id: int | None = None,
    signer_display_name: str | None = None,
    signer_email: str | None = None,
    record_content_hash: str | None = None,
    step_up_factor: str | None = None,
    step_up_aal: str | None = None,
) -> ElectronicSignatureRecordORM:
    """Persist an electronic-signature row.

    When ``signer_user_id`` / ``record_content_hash`` are supplied (the server-authoritative route
    path), the row carries the §11.100 principal attribution and a content-bound ``signature_digest``
    (§11.70). The inline callers (system-release approval, pilot signoff) may omit them; identity
    then falls back to the payload fields and the legacy ``signature_hash`` is computed exactly as
    before so existing rows and the exactly-64 response contract stay valid."""
    signed_at = utcnow()
    effective_name = signer_display_name or payload.signer_name
    effective_email = signer_email if signer_email is not None else payload.signer_email
    # Legacy hash (unchanged shape) — back-compat with String(64) column + existing tests.
    signature_payload = {
        "signer_name": effective_name,
        "signer_email": effective_email,
        "signature_meaning": payload.signature_meaning,
        "target_type": payload.target_type,
        "target_id": payload.target_id,
        "reason": payload.reason,
        "signed_at": signed_at.isoformat(),
        "authentication_method": payload.authentication_method,
    }
    # Content-bound digest (§11.70) — computed only when a record content hash is available; a None
    # binding leaves the row "unbound" (honest) rather than binding a meaningless hash.
    signature_digest: str | None = None
    if record_content_hash is not None:
        signature_digest = esign.compute_signature_digest(
            esign.canonical_signature_payload(
                signer_user_id=signer_user_id,
                signer_email=effective_email,
                signer_display_name=effective_name,
                signature_meaning=payload.signature_meaning,
                target_type=payload.target_type,
                target_id=payload.target_id,
                record_content_hash=record_content_hash,
                reason=payload.reason,
                signed_at=signed_at,
                step_up_factor=step_up_factor,
                step_up_aal=step_up_aal,
            )
        )
    metadata = {
        **payload.metadata_json,
        "server_validated": True,
        "readiness_notice": _SAFE_NOTICE,
    }
    if step_up_factor is not None:
        metadata["step_up_factor"] = step_up_factor
    if step_up_aal is not None:
        metadata["step_up_aal"] = step_up_aal
    if signer_user_id is not None and effective_name != payload.signer_name:
        # Record what the client declared vs the server-authoritative identity that was used.
        metadata["client_declared_signer_name"] = payload.signer_name
    row = ElectronicSignatureRecordORM(
        signer_name=effective_name,
        signer_email=effective_email,
        signature_meaning=payload.signature_meaning,
        target_type=payload.target_type,
        target_id=payload.target_id,
        reason=payload.reason,
        signed_at=signed_at,
        authentication_method=payload.authentication_method,
        signature_hash=_hash_json(signature_payload),
        signer_user_id=signer_user_id,
        record_content_hash=record_content_hash,
        signature_digest=signature_digest,
        metadata_json=_json_dump(metadata, default={}),
    )
    session.add(row)
    session.flush()
    return row


# Target types for which a deterministic server-side content snapshot exists. Signing one of these
# against a missing record is an error (see ``create_record_signature``); any other target type is
# stored unbound (honest) — the digest simply omits a content binding.
_BINDABLE_TARGET_TYPES = frozenset({"controlled_record", "system_release"})


def _controlled_record_snapshot(row: ControlledRecordORM) -> dict[str, Any]:
    """Deterministic §11.70 content snapshot for a controlled record. Covers identity + version +
    the body (via the record's own ``content_hash`` when present, else a hash of identity fields).
    ``status``, ``locked_at``/``locked_by`` and ``retention_policy_id`` are **intentionally
    excluded**: they change through the normal lock/retention lifecycle of an already-signed record
    and must not retroactively invalidate the signature."""
    base = row.content_hash or _hash_json(
        {"id": row.id, "title": row.title, "version": row.version, "status": row.status}
    )
    return {
        "controlled_record_id": row.id,
        "record_type": row.record_type,
        "resource_id": row.resource_id,
        "version": row.version,
        "content_hash": base,
    }


def _system_release_snapshot(row: SystemReleaseRecordORM) -> dict[str, Any]:
    """Deterministic §11.70 content snapshot for a system release. Covers the identifying NOT-NULL
    columns plus the test/risk summaries the approval attests to. ``approval_status``/``released_at``
    and timestamps are excluded — they change *as part of* the approval being signed."""
    return {
        "system_release_id": row.id,
        "release_version": row.release_version,
        "release_type": row.release_type,
        "change_summary": row.change_summary,
        "test_summary": _json_dict(row.test_summary_json),
        "risk_summary": _json_dict(row.risk_summary_json),
    }


def _resolve_record_content_hash(
    session: Session, target_type: str, target_id: int
) -> str | None:
    """Server-side snapshot -> content hash for a signable record (§11.70). Returns None for target
    types not in ``_BINDABLE_TARGET_TYPES`` (genuinely unsupported — stored unbound, honest) **and**
    when a bindable record is missing; the route treats a None for a bindable type as a not-found
    error rather than minting an unbound signature (see ``create_record_signature``). The create-time
    snapshot here is byte-identical to the verify-time one (same helper), so a genuine signature
    always re-verifies."""
    if target_type == "controlled_record":
        row = session.get(ControlledRecordORM, target_id)
        if row is None:
            return None
        return esign.compute_record_content_hash(_controlled_record_snapshot(row))
    if target_type == "system_release":
        row = session.get(SystemReleaseRecordORM, target_id)
        if row is None:
            return None
        return esign.compute_record_content_hash(_system_release_snapshot(row))
    return None


def _signature_binding_dict(row: ElectronicSignatureRecordORM) -> dict[str, Any]:
    """Flatten an ORM row into the binding dict ``esign.verify_signature`` consumes."""
    meta = _json_dict(row.metadata_json)
    return {
        "signature_digest": row.signature_digest,
        "signer_user_id": row.signer_user_id,
        "signer_email": row.signer_email,
        "signer_name": row.signer_name,
        "signature_meaning": row.signature_meaning,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "record_content_hash": row.record_content_hash,
        "reason": row.reason,
        "signed_at": row.signed_at,
        "step_up_factor": meta.get("step_up_factor"),
        "step_up_aal": meta.get("step_up_aal"),
    }


def create_signature(
    session_factory: sessionmaker[Session],
    payload: ElectronicSignatureRecordCreate,
) -> ElectronicSignatureRecord:
    with session_scope(session_factory) as session:
        row = _create_signature_row(session, payload)
        session.refresh(row)
        return _signature_to_record(row)


def create_record_signature(
    session_factory: sessionmaker[Session],
    payload: ElectronicSignatureRecordCreate,
    *,
    signer_user_id: int | None,
    signer_display_name: str | None,
    signer_email: str | None,
    step_up_factor: str | None = None,
    step_up_aal: str | None = None,
) -> ElectronicSignatureRecord:
    """Server-authoritative signing entry point (the ``/esignatures/records`` route).

    Identity is taken from the authenticated principal (never the client payload — §11.100) and the
    record content hash is resolved server-side and bound into the digest (§11.70)."""
    with session_scope(session_factory) as session:
        record_content_hash = _resolve_record_content_hash(
            session, payload.target_type, payload.target_id
        )
        if record_content_hash is None and payload.target_type in _BINDABLE_TARGET_TYPES:
            # A bindable target that resolved to no content means the record doesn't exist. Refuse
            # rather than minting an unbound signature that would silently mask the missing target
            # and defeat the §11.70 binding promise. KeyError -> 404 at the route.
            raise KeyError(
                f"Cannot sign {payload.target_type} {payload.target_id}: record not found."
            )
        row = _create_signature_row(
            session,
            payload,
            signer_user_id=signer_user_id,
            signer_display_name=signer_display_name,
            signer_email=signer_email,
            record_content_hash=record_content_hash,
            step_up_factor=step_up_factor,
            step_up_aal=step_up_aal,
        )
        session.refresh(row)
        return _signature_to_record(row)


def verify_record_signature(
    session_factory: sessionmaker[Session],
    signature_id: int,
    *,
    recompute: bool = False,
) -> dict[str, Any] | None:
    """Verify a stored signature's integrity (§11.70). With ``recompute=True``, re-snapshot the
    current record and report whether the signed content has since changed. Returns None if the
    signature does not exist."""
    with session_scope(session_factory) as session:
        row = session.get(ElectronicSignatureRecordORM, signature_id)
        if row is None:
            return None
        recomputed_content_hash: str | None = None
        if recompute and row.record_content_hash is not None:
            recomputed_content_hash = _resolve_record_content_hash(
                session, row.target_type, row.target_id
            )
        result = esign.verify_signature(
            _signature_binding_dict(row), recomputed_content_hash=recomputed_content_hash
        )
        result["signature_id"] = row.id
        result["record_content_hash"] = row.record_content_hash
        result["recomputed_content_hash"] = recomputed_content_hash
        return result


def build_signature_manifestation(
    session_factory: sessionmaker[Session],
    signature_id: int,
) -> dict[str, Any] | None:
    """Structured §11.50 manifestation for a stored signature (the inspection-copy stamp)."""
    with session_scope(session_factory) as session:
        row = session.get(ElectronicSignatureRecordORM, signature_id)
        if row is None:
            return None
        meta = _json_dict(row.metadata_json)
        return esign.build_manifestation(
            signer_display_name=row.signer_name,
            signer_email=row.signer_email,
            signature_meaning=row.signature_meaning,
            reason=row.reason,
            signed_at=row.signed_at,
            target_type=row.target_type,
            target_id=row.target_id,
            record_content_hash=row.record_content_hash,
            signature_digest=row.signature_digest,
            authentication_method=row.authentication_method,
            step_up_factor=meta.get("step_up_factor"),
            step_up_aal=meta.get("step_up_aal"),
        )


def list_signatures(
    session_factory: sessionmaker[Session],
    *,
    target_type: str | None = None,
    target_id: int | None = None,
    limit: int = 200,
) -> list[ElectronicSignatureRecord]:
    with session_scope(session_factory) as session:
        stmt = select(ElectronicSignatureRecordORM).order_by(ElectronicSignatureRecordORM.id.desc()).limit(limit)
        if target_type:
            stmt = stmt.where(ElectronicSignatureRecordORM.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(ElectronicSignatureRecordORM.target_id == target_id)
        return [_signature_to_record(row) for row in session.scalars(stmt).all()]


def get_signature(
    session_factory: sessionmaker[Session],
    signature_id: int,
) -> ElectronicSignatureRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(ElectronicSignatureRecordORM, signature_id)
        return _signature_to_record(row) if row is not None else None


def create_controlled_record(
    session_factory: sessionmaker[Session],
    payload: ControlledRecordCreate,
) -> ControlledRecord:
    content_hash = payload.content_hash or (
        _hash_json(payload.content_json) if payload.content_json is not None else None
    )
    metadata = dict(payload.metadata_json)
    if payload.content_json is not None:
        metadata["content_json_hash"] = content_hash
    metadata["readiness_notice"] = _SAFE_NOTICE
    with session_scope(session_factory) as session:
        row = ControlledRecordORM(
            record_type=payload.record_type,
            resource_id=payload.resource_id,
            title=payload.title,
            version=payload.version,
            status=payload.status,
            content_hash=content_hash,
            retention_policy_id=payload.retention_policy_id,
            metadata_json=_json_dump(metadata, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _controlled_record_to_record(row)


def list_controlled_records(
    session_factory: sessionmaker[Session],
    *,
    status_filter: str | None = None,
    record_type: str | None = None,
    limit: int = 200,
) -> list[ControlledRecord]:
    with session_scope(session_factory) as session:
        stmt = select(ControlledRecordORM).order_by(ControlledRecordORM.id.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(ControlledRecordORM.status == status_filter)
        if record_type:
            stmt = stmt.where(ControlledRecordORM.record_type == record_type)
        return [_controlled_record_to_record(row) for row in session.scalars(stmt).all()]


def get_controlled_record(
    session_factory: sessionmaker[Session],
    record_id: int,
) -> ControlledRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(ControlledRecordORM, record_id)
        return _controlled_record_to_record(row) if row is not None else None


def create_controlled_record_version(
    session_factory: sessionmaker[Session],
    record_id: int,
    payload: ControlledRecordNewVersionRequest,
) -> ControlledRecord:
    with session_scope(session_factory) as session:
        source = session.get(ControlledRecordORM, record_id)
        if source is None:
            raise KeyError("Controlled record not found.")
        content_hash = payload.content_hash or (
            _hash_json(payload.content_json) if payload.content_json is not None else source.content_hash
        )
        metadata = {
            **_json_dict(source.metadata_json),
            **payload.metadata_json,
            "previous_record_id": source.id,
            "previous_version": source.version,
            "created_from_locked_record": source.status == "locked",
            "readiness_notice": _SAFE_NOTICE,
        }
        row = ControlledRecordORM(
            record_type=source.record_type,
            resource_id=source.resource_id,
            title=payload.title or source.title,
            version=payload.version or _next_version(source.version),
            status="draft",
            content_hash=content_hash,
            retention_policy_id=source.retention_policy_id,
            metadata_json=_json_dump(metadata, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _controlled_record_to_record(row)


def lock_controlled_record(
    session_factory: sessionmaker[Session],
    record_id: int,
    payload: ControlledRecordLockRequest,
) -> ControlledRecord:
    with session_scope(session_factory) as session:
        row = session.get(ControlledRecordORM, record_id)
        if row is None:
            raise KeyError("Controlled record not found.")
        if row.status == "locked":
            raise ControlledRecordLockedError("Controlled record is already locked; create a new version.")
        row.status = "locked"
        row.locked_at = utcnow()
        row.locked_by = payload.locked_by
        row.content_hash = payload.content_hash or row.content_hash or _hash_json(
            {
                "record_id": row.id,
                "record_type": row.record_type,
                "title": row.title,
                "version": row.version,
                "metadata_json": _json_dict(row.metadata_json),
            }
        )
        row.metadata_json = _json_dump(
            {
                **_json_dict(row.metadata_json),
                **payload.metadata_json,
                "lock_reason": payload.reason,
                "readiness_notice": _SAFE_NOTICE,
            },
            default={},
        )
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _controlled_record_to_record(row)


def archive_controlled_record(
    session_factory: sessionmaker[Session],
    record_id: int,
    payload: ControlledRecordArchiveRequest,
) -> ControlledRecord:
    with session_scope(session_factory) as session:
        row = session.get(ControlledRecordORM, record_id)
        if row is None:
            raise KeyError("Controlled record not found.")
        if row.status == "locked":
            raise ControlledRecordLockedError(
                "Locked controlled records cannot be silently modified; create a new version."
            )
        row.status = "archived"
        row.metadata_json = _json_dump(
            {
                **_json_dict(row.metadata_json),
                **payload.metadata_json,
                "archive_reason": payload.reason,
            },
            default={},
        )
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _controlled_record_to_record(row)


def create_retention_policy(
    session_factory: sessionmaker[Session],
    payload: RecordRetentionPolicyCreate,
) -> RecordRetentionPolicy:
    with session_scope(session_factory) as session:
        row = RecordRetentionPolicyORM(
            name=payload.name,
            record_type=payload.record_type,
            retention_period_years=payload.retention_period_years,
            archive_strategy=payload.archive_strategy,
            legal_hold=payload.legal_hold,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _retention_policy_to_record(row)


def list_retention_policies(
    session_factory: sessionmaker[Session],
    *,
    limit: int = 200,
) -> list[RecordRetentionPolicy]:
    with session_scope(session_factory) as session:
        stmt = select(RecordRetentionPolicyORM).order_by(RecordRetentionPolicyORM.id.desc()).limit(limit)
        return [_retention_policy_to_record(row) for row in session.scalars(stmt).all()]


def _derive_assessment_status(payload: DataIntegrityAssessmentCreate) -> str:
    statuses = [
        payload.attributable_status,
        payload.legible_status,
        payload.contemporaneous_status,
        payload.original_status,
        payload.accurate_status,
        payload.complete_status,
        payload.consistent_status,
        payload.enduring_status,
        payload.available_status,
    ]
    if payload.assessment_status is not None:
        return payload.assessment_status
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    if "requires_review" in statuses:
        return "requires_review"
    return "pass"


def create_data_integrity_assessment(
    session_factory: sessionmaker[Session],
    payload: DataIntegrityAssessmentCreate,
) -> DataIntegrityAssessment:
    with session_scope(session_factory) as session:
        row = DataIntegrityAssessmentORM(
            scope=payload.scope,
            scope_id=payload.scope_id,
            assessment_status=_derive_assessment_status(payload),
            attributable_status=payload.attributable_status,
            legible_status=payload.legible_status,
            contemporaneous_status=payload.contemporaneous_status,
            original_status=payload.original_status,
            accurate_status=payload.accurate_status,
            complete_status=payload.complete_status,
            consistent_status=payload.consistent_status,
            enduring_status=payload.enduring_status,
            available_status=payload.available_status,
            findings_json=_json_dump(payload.findings_json, default=[]),
            recommended_actions_json=_json_dump(payload.recommended_actions_json, default=[]),
            metadata_json=_json_dump(
                {
                    **payload.metadata_json,
                    "framework": "ALCOA+ readiness",
                    "readiness_notice": _SAFE_NOTICE,
                },
                default={},
            ),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _data_integrity_to_record(row)


def list_data_integrity_assessments(
    session_factory: sessionmaker[Session],
    *,
    scope: str | None = None,
    limit: int = 200,
) -> list[DataIntegrityAssessment]:
    with session_scope(session_factory) as session:
        stmt = select(DataIntegrityAssessmentORM).order_by(DataIntegrityAssessmentORM.id.desc()).limit(limit)
        if scope:
            stmt = stmt.where(DataIntegrityAssessmentORM.scope == scope)
        return [_data_integrity_to_record(row) for row in session.scalars(stmt).all()]


def get_data_integrity_assessment(
    session_factory: sessionmaker[Session],
    assessment_id: int,
) -> DataIntegrityAssessment | None:
    with session_scope(session_factory) as session:
        row = session.get(DataIntegrityAssessmentORM, assessment_id)
        return _data_integrity_to_record(row) if row is not None else None


def create_inspection_package(
    session_factory: sessionmaker[Session],
    payload: InspectionReadinessPackageCreate,
) -> InspectionReadinessPackage:
    with session_scope(session_factory) as session:
        records = [
            session.get(ControlledRecordORM, record_id)
            for record_id in payload.included_record_ids_json
        ]
        signatures = [
            session.get(ElectronicSignatureRecordORM, signature_id)
            for signature_id in payload.included_signature_ids_json
        ]
        audits = [
            session.get(AuditEventORM, audit_id)
            for audit_id in payload.included_audit_event_ids_json
        ]
        projects = [
            session.get(ValidationProjectORM, project_id)
            for project_id in payload.included_validation_project_ids_json
        ]
        releases = session.scalars(
            select(SystemReleaseRecordORM).order_by(SystemReleaseRecordORM.id.desc()).limit(100)
        ).all()
        manifest = {
            "schema_version": "phase63.inspection_package.v1",
            "title": payload.title,
            "scope": payload.scope,
            "scope_id": payload.scope_id,
            "package_status": payload.package_status,
            "controlled_records": [
                {
                    "record_id": row.id,
                    "record_type": row.record_type,
                    "version": row.version,
                    "status": row.status,
                    "content_hash": row.content_hash,
                }
                for row in records
                if row is not None
            ],
            "e_signature_records": [
                {
                    "signature_id": row.id,
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "signature_meaning": row.signature_meaning,
                    "signature_hash": row.signature_hash,
                    # Part 11 binding (§11.70 / §11.100) + §11.50 manifestation on the inspection copy.
                    "signer_user_id": row.signer_user_id,
                    "record_content_hash": row.record_content_hash,
                    "signature_digest": row.signature_digest,
                    "manifestation": esign.build_manifestation(
                        signer_display_name=row.signer_name,
                        signer_email=row.signer_email,
                        signature_meaning=row.signature_meaning,
                        reason=row.reason,
                        signed_at=row.signed_at,
                        target_type=row.target_type,
                        target_id=row.target_id,
                        record_content_hash=row.record_content_hash,
                        signature_digest=row.signature_digest,
                        authentication_method=row.authentication_method,
                    ),
                }
                for row in signatures
                if row is not None
            ],
            "audit_events": [
                {
                    "audit_event_id": row.id,
                    "event_type": row.event_type,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "created_at": row.created_at.isoformat(),
                }
                for row in audits
                if row is not None
            ],
            "validation_projects": [
                {
                    "validation_project_id": row.id,
                    "title": row.title,
                    "scope": row.scope,
                    "status": row.status,
                }
                for row in projects
                if row is not None
            ],
            "release_records": [
                {
                    "release_id": row.id,
                    "release_version": row.release_version,
                    "release_type": row.release_type,
                    "approval_status": row.approval_status,
                }
                for row in releases
            ],
            "readiness_notice": _SAFE_NOTICE,
        }
        package_sha256 = _hash_json(manifest)
        row = InspectionReadinessPackageORM(
            title=payload.title,
            scope=payload.scope,
            scope_id=payload.scope_id,
            package_status=payload.package_status,
            included_record_ids_json=_json_dump(payload.included_record_ids_json, default=[]),
            included_signature_ids_json=_json_dump(payload.included_signature_ids_json, default=[]),
            included_audit_event_ids_json=_json_dump(payload.included_audit_event_ids_json, default=[]),
            included_validation_project_ids_json=_json_dump(
                payload.included_validation_project_ids_json,
                default=[],
            ),
            package_manifest_json=_json_dump(manifest, default={}),
            package_sha256=package_sha256,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _inspection_package_to_record(row)


def list_inspection_packages(
    session_factory: sessionmaker[Session],
    *,
    limit: int = 200,
) -> list[InspectionReadinessPackage]:
    with session_scope(session_factory) as session:
        stmt = select(InspectionReadinessPackageORM).order_by(InspectionReadinessPackageORM.id.desc()).limit(limit)
        return [_inspection_package_to_record(row) for row in session.scalars(stmt).all()]


def get_inspection_package(
    session_factory: sessionmaker[Session],
    package_id: int,
) -> InspectionReadinessPackage | None:
    with session_scope(session_factory) as session:
        row = session.get(InspectionReadinessPackageORM, package_id)
        return _inspection_package_to_record(row) if row is not None else None


def get_inspection_package_download(
    session_factory: sessionmaker[Session],
    package_id: int,
) -> tuple[str, bytes] | None:
    package = get_inspection_package(session_factory, package_id)
    if package is None:
        return None
    payload = _json_dump(
        {
            "package_id": package.id,
            "package_sha256": package.package_sha256,
            "manifest": package.package_manifest_json,
        },
        default={},
    )
    return (f"inspection-ready-package-{package.id}.json", payload.encode("utf-8"))


def create_system_release(
    session_factory: sessionmaker[Session],
    payload: SystemReleaseRecordCreate,
) -> SystemReleaseRecord:
    with session_scope(session_factory) as session:
        if payload.validation_project_id is not None:
            _ensure_project(session, payload.validation_project_id)
        row = SystemReleaseRecordORM(
            release_version=payload.release_version,
            release_type=payload.release_type,
            change_summary=payload.change_summary,
            validation_project_id=payload.validation_project_id,
            test_summary_json=_json_dump(payload.test_summary_json, default={}),
            risk_summary_json=_json_dump(payload.risk_summary_json, default={}),
            approval_status=payload.approval_status,
            metadata_json=_json_dump(
                {
                    **payload.metadata_json,
                    "readiness_notice": _SAFE_NOTICE,
                },
                default={},
            ),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _release_to_record(row)


def list_system_releases(
    session_factory: sessionmaker[Session],
    *,
    limit: int = 200,
) -> list[SystemReleaseRecord]:
    with session_scope(session_factory) as session:
        stmt = select(SystemReleaseRecordORM).order_by(SystemReleaseRecordORM.id.desc()).limit(limit)
        return [_release_to_record(row) for row in session.scalars(stmt).all()]


def get_system_release(
    session_factory: sessionmaker[Session],
    release_id: int,
) -> SystemReleaseRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(SystemReleaseRecordORM, release_id)
        return _release_to_record(row) if row is not None else None


def approve_system_release(
    session_factory: sessionmaker[Session],
    release_id: int,
    payload: SystemReleaseApproveRequest,
    *,
    signer_user_id: int | None = None,
    signer_display_name: str | None = None,
    signer_email: str | None = None,
) -> SystemReleaseRecord:
    with session_scope(session_factory) as session:
        row = session.get(SystemReleaseRecordORM, release_id)
        if row is None:
            raise KeyError("System release record not found.")
        test_summary = _json_dict(row.test_summary_json)
        risk_summary = _json_dict(row.risk_summary_json)
        if not test_summary or not risk_summary:
            raise ValidationCenterError("System release approval requires validation test and risk summaries.")
        # §11.70: bind the same snapshot the verify path recomputes (shared helper -> byte-identical).
        release_content_hash = esign.compute_record_content_hash(_system_release_snapshot(row))
        signature = _create_signature_row(
            session,
            ElectronicSignatureRecordCreate(
                signer_name=payload.signer_name,
                signer_email=payload.signer_email,
                signature_meaning=payload.signature_meaning,
                target_type="system_release",
                target_id=row.id,
                reason=payload.reason,
                authentication_method=payload.authentication_method,
                metadata_json=payload.metadata_json,
            ),
            # §11.100: attribute to the authenticated principal when the route supplies it.
            signer_user_id=signer_user_id,
            signer_display_name=signer_display_name,
            signer_email=signer_email,
            record_content_hash=release_content_hash,
        )
        row.approval_status = "released" if payload.release else "approved"
        row.released_at = utcnow() if payload.release else row.released_at
        row.metadata_json = _json_dump(
            {
                **_json_dict(row.metadata_json),
                "approval_signature_id": signature.id,
                "approval_signature_hash": signature.signature_hash,
                "requires_qa_review": False,
            },
            default={},
        )
        session.flush()
        session.refresh(row)
        return _release_to_record(row)


def create_deviation(
    session_factory: sessionmaker[Session],
    payload: DeviationRecordCreate,
) -> DeviationRecord:
    with session_scope(session_factory) as session:
        row = DeviationRecordORM(
            deviation_code=payload.deviation_code or "pending",
            title=payload.title,
            description=payload.description,
            severity=payload.severity,
            source_type=payload.source_type,
            source_id=payload.source_id,
            status=payload.status,
            root_cause=payload.root_cause,
            resolution=payload.resolution,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        if payload.deviation_code is None:
            row.deviation_code = _code("DEV", row.id)
        session.flush()
        session.refresh(row)
        return _deviation_to_record(row)


def list_deviations(
    session_factory: sessionmaker[Session],
    *,
    status_filter: str | None = None,
    limit: int = 200,
) -> list[DeviationRecord]:
    with session_scope(session_factory) as session:
        stmt = select(DeviationRecordORM).order_by(DeviationRecordORM.id.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(DeviationRecordORM.status == status_filter)
        return [_deviation_to_record(row) for row in session.scalars(stmt).all()]


def update_deviation(
    session_factory: sessionmaker[Session],
    deviation_id: int,
    payload: DeviationRecordUpdate,
) -> DeviationRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(DeviationRecordORM, deviation_id)
        if row is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        for field in ("title", "description", "severity", "status", "root_cause", "resolution"):
            if field in data:
                setattr(row, field, data[field])
        if "metadata_json" in data:
            row.metadata_json = _json_dump(data["metadata_json"], default={})
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _deviation_to_record(row)


def create_capa(
    session_factory: sessionmaker[Session],
    payload: CAPARecordCreate,
) -> CAPARecord:
    with session_scope(session_factory) as session:
        if payload.source_deviation_id is not None and session.get(DeviationRecordORM, payload.source_deviation_id) is None:
            raise KeyError("Deviation record not found.")
        row = CAPARecordORM(
            capa_code=payload.capa_code or "pending",
            title=payload.title,
            description=payload.description,
            source_deviation_id=payload.source_deviation_id,
            corrective_action=payload.corrective_action,
            preventive_action=payload.preventive_action,
            owner=payload.owner,
            due_date=payload.due_date,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        if payload.capa_code is None:
            row.capa_code = _code("CAPA", row.id)
        session.flush()
        session.refresh(row)
        return _capa_to_record(row)


def list_capa(
    session_factory: sessionmaker[Session],
    *,
    status_filter: str | None = None,
    limit: int = 200,
) -> list[CAPARecord]:
    with session_scope(session_factory) as session:
        stmt = select(CAPARecordORM).order_by(CAPARecordORM.id.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(CAPARecordORM.status == status_filter)
        return [_capa_to_record(row) for row in session.scalars(stmt).all()]


def update_capa(
    session_factory: sessionmaker[Session],
    capa_id: int,
    payload: CAPARecordUpdate,
) -> CAPARecord | None:
    with session_scope(session_factory) as session:
        row = session.get(CAPARecordORM, capa_id)
        if row is None:
            return None
        data = payload.model_dump(exclude_unset=True)
        if data.get("source_deviation_id") is not None and session.get(DeviationRecordORM, int(data["source_deviation_id"])) is None:
            raise KeyError("Deviation record not found.")
        for field in (
            "title",
            "description",
            "source_deviation_id",
            "corrective_action",
            "preventive_action",
            "owner",
            "due_date",
            "status",
        ):
            if field in data:
                setattr(row, field, data[field])
        if "metadata_json" in data:
            row.metadata_json = _json_dump(data["metadata_json"], default={})
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _capa_to_record(row)
