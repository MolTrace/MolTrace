from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import orchestration_store as orch_store
from . import quality_control_store as qc_store
from .database import session_scope
from .models import (
    AnalysisJobCreate,
    QualityAssessmentRequest,
    WorkflowRunArtifactRecord,
    WorkflowRunCreate,
    WorkflowRunEventRecord,
    WorkflowRunRecord,
    WorkflowRunStepRecord,
    WorkflowTemplateCreate,
    WorkflowTemplateRecord,
    WorkflowTemplateUpdate,
)
from .orm import (
    ArtifactRecordORM,
    QualityAssessmentORM,
    SpectraCheckAuditEventORM,
    SpectraCheckEvidenceRecordORM,
    SpectraCheckProjectORM,
    SpectraCheckSessionORM,
    WorkflowRunArtifactORM,
    WorkflowRunEventORM,
    WorkflowRunORM,
    WorkflowRunStepORM,
    WorkflowTemplateORM,
    utcnow,
)


class WorkflowError(ValueError):
    pass


_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


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


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _normalize_slug(value: str) -> str:
    slug = _SLUG_RE.sub("_", value.strip().lower()).strip("_-")
    return slug or "workflow_template"


def _builtin_steps(*names: tuple[str, str, str]) -> list[dict[str, Any]]:
    return [
        {
            "step_id": step_id,
            "step_name": step_name,
            "step_type": step_type,
        }
        for step_id, step_name, step_type in names
    ]


BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": -1,
        "name": "Quick NMR Text Candidate Check",
        "slug": "quick_nmr_text_candidate_check",
        "description": "Create review-ready predicted-NMR text evidence from supplied NMR text and candidate notes.",
        "category": "nmr",
        "version": "1.0",
        "steps_json": _builtin_steps(
            ("predicted_nmr_match", "Predicted NMR match evidence", "evidence_queue"),
            ("quality_control_evidence", "Quality-control evidence readiness", "quality_control"),
            ("add_to_evidence_queue", "Mark evidence queue record ready", "evidence_queue"),
        ),
        "required_inputs_json": ["nmr_text", "candidates_text"],
        "optional_inputs_json": ["sample_id", "solvent", "candidate_smiles"],
    },
    {
        "id": -2,
        "name": "Processed 1H/13C Evidence",
        "slug": "processed_1h_13c_evidence",
        "description": "Run processed NMR preview/analyze jobs, QC artifacts, and save evidence queue records.",
        "category": "nmr",
        "version": "1.0",
        "steps_json": _builtin_steps(
            ("nmr_processed_preview", "Processed NMR preview job", "job"),
            ("nmr_processed_analyze", "Processed NMR analyze job", "job"),
            ("quality_control_artifacts", "Quality-control processed NMR artifacts", "quality_control"),
            ("add_to_evidence_queue", "Add processed NMR evidence queue record", "evidence_queue"),
        ),
        "required_inputs_json": ["processed_file_ids"],
        "optional_inputs_json": ["sample_id", "solvent", "nucleus", "spectrometer_frequency_mhz"],
    },
    {
        "id": -3,
        "name": "Raw FID To Evidence",
        "slug": "raw_fid_to_evidence",
        "description": "Inspect raw FID files, process derived spectra where available, QC provenance, and save review evidence.",
        "category": "nmr",
        "version": "1.0",
        "steps_json": _builtin_steps(
            ("nmr_raw_fid_preview", "Raw FID preview job", "job"),
            ("nmr_raw_fid_process", "Raw FID processing job", "job"),
            ("quality_control_file", "Quality-control raw file", "quality_control"),
            ("quality_control_artifact", "Quality-control derived artifact", "quality_control"),
            ("add_to_evidence_queue", "Add raw FID evidence queue record", "evidence_queue"),
        ),
        "required_inputs_json": ["raw_file_ids"],
        "optional_inputs_json": ["sample_id", "solvent", "nucleus", "processing_preset"],
    },
    {
        "id": -4,
        "name": "HRMS/MSMS Candidate Support",
        "slug": "hrms_msms_candidate_support",
        "description": "Orchestrate HRMS and MS/MS support evidence with QC and evidence-queue persistence.",
        "category": "ms",
        "version": "1.0",
        "steps_json": _builtin_steps(
            ("hrms_candidate_match", "HRMS candidate match job", "job"),
            ("formula_search", "Formula search job", "job"),
            ("msms_annotation", "MS/MS annotation job", "job"),
            ("fragmentation_tree", "Fragmentation tree job", "job"),
            ("quality_control_evidence", "Quality-control MS evidence", "quality_control"),
            ("add_to_evidence_queue", "Add MS evidence queue record", "evidence_queue"),
        ),
        "required_inputs_json": ["candidates_text"],
        "optional_inputs_json": ["observed_mz", "adduct", "msms_peaks"],
    },
    {
        "id": -5,
        "name": "LC-MS Feature Consensus",
        "slug": "lcms_feature_consensus",
        "description": "Run LC-MS import, feature detection/grouping/consensus, QC evidence, and save queue records.",
        "category": "lcms",
        "version": "1.0",
        "steps_json": _builtin_steps(
            ("lcms_import", "LC-MS import job", "job"),
            ("lcms_feature_detection", "LC-MS feature detection job", "job"),
            ("lcms_feature_grouping", "LC-MS feature grouping job", "job"),
            ("lcms_feature_family_consensus", "Feature-family consensus job", "job"),
            ("quality_control_evidence", "Quality-control LC-MS evidence", "quality_control"),
            ("add_to_evidence_queue", "Add LC-MS evidence queue record", "evidence_queue"),
        ),
        "required_inputs_json": ["lcms_file_ids"],
        "optional_inputs_json": ["blank_file_ids", "candidate_features"],
    },
    {
        "id": -6,
        "name": "Full SpectraCheck Evidence To Report",
        "slug": "full_spectracheck_evidence_to_report",
        "description": "QC selected evidence, synthesize unified evidence, compose a review-ready report, and stop at a review gate.",
        "category": "full_spectracheck",
        "version": "1.0",
        "steps_json": _builtin_steps(
            ("run_selected_evidence_steps", "Use selected evidence queue records", "manual"),
            ("quality_control_session", "Quality-control session readiness", "quality_control"),
            ("unified_evidence", "Save unified candidate confidence evidence", "unified_evidence"),
            ("report_compose", "Compose review-ready report artifact", "report"),
            ("review_gate", "Human review gate", "review_gate"),
        ),
        "required_inputs_json": ["session_id"],
        "optional_inputs_json": ["candidates_text", "report_title", "selected_evidence_ids"],
    },
]


def _builtin_template_by_id_or_slug(value: str | int | None) -> dict[str, Any] | None:
    if value is None:
        return None
    normalized = str(value).strip()
    for template in BUILTIN_TEMPLATES:
        if normalized == str(template["id"]) or normalized == template["slug"]:
            return template
    return None


def _project_visible(row: SpectraCheckProjectORM | None, *, owner_scope_id: int | None) -> bool:
    return row is not None and (owner_scope_id is None or row.owner_id == owner_scope_id)


def _session_visible(row: SpectraCheckSessionORM | None, *, owner_scope_id: int | None) -> bool:
    return row is not None and _project_visible(row.project, owner_scope_id=owner_scope_id)


def _add_session_audit(
    session: Session,
    *,
    session_id: int | None,
    actor_id: int | None,
    event_type: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if session_id is None:
        return
    session.add(
        SpectraCheckAuditEventORM(
            session_id=session_id,
            event_type=event_type,
            message=message,
            actor_id=actor_id,
            metadata_json=_json_dump(metadata or {}, default={}),
        )
    )


def _template_to_record(row: WorkflowTemplateORM | dict[str, Any]) -> WorkflowTemplateRecord:
    if isinstance(row, dict):
        now = utcnow()
        steps = list(row.get("steps_json") or [])
        required = list(row.get("required_inputs_json") or [])
        optional = list(row.get("optional_inputs_json") or [])
        return WorkflowTemplateRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            slug=str(row["slug"]),
            description=str(row["description"]),
            category=row["category"],  # type: ignore[arg-type]
            version=str(row["version"]),
            is_builtin=True,
            steps_json=steps,
            required_inputs_json=required,
            optional_inputs_json=optional,
            steps=steps,
            required_inputs=required,
            optional_inputs=optional,
            created_at=now,
            updated_at=now,
            metadata_json={"builtin_template": True},
            notes=["Built-in workflow template; execution preserves human-review language."],
        )
    steps = _json_list(row.steps_json)
    required = [str(item) for item in _json_list(row.required_inputs_json)]
    optional = [str(item) for item in _json_list(row.optional_inputs_json)]
    return WorkflowTemplateRecord(
        id=row.id,
        name=row.name,
        slug=row.slug,
        description=row.description,
        category=row.category,  # type: ignore[arg-type]
        version=row.version,
        is_builtin=row.is_builtin,
        steps_json=[dict(item) for item in steps if isinstance(item, dict)],
        required_inputs_json=required,
        optional_inputs_json=optional,
        steps=[dict(item) for item in steps if isinstance(item, dict)],
        required_inputs=required,
        optional_inputs=optional,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Workflow template orchestrates existing modules and does not add identity-confirmation scoring."],
    )


def _step_to_record(row: WorkflowRunStepORM) -> WorkflowRunStepRecord:
    return WorkflowRunStepRecord(
        id=row.id,
        workflow_run_id=row.workflow_run_id,
        step_id=row.step_id,
        step_name=row.step_name,
        step_type=row.step_type,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        job_id=row.job_id,
        input_json=_json_dict(row.input_json),
        output_json=_json_dict(row.output_json) if row.output_json else None,
        error_message=row.error_message,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _event_to_record(row: WorkflowRunEventORM) -> WorkflowRunEventRecord:
    return WorkflowRunEventRecord(
        id=row.id,
        workflow_run_id=row.workflow_run_id,
        step_id=row.step_id,
        event_type=row.event_type,
        message=row.message,
        progress_percent=row.progress_percent,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _artifact_to_record(row: WorkflowRunArtifactORM) -> WorkflowRunArtifactRecord:
    return WorkflowRunArtifactRecord(
        id=row.id,
        workflow_run_id=row.workflow_run_id,
        step_id=row.step_id,
        artifact_id=row.artifact_id,
        evidence_id=row.evidence_id,
        title=row.title,
        artifact_type=row.artifact_type,
        method_id=row.method_id,
        model_version_id=row.model_version_id,
        scoring_profile_id=row.scoring_profile_id,
        threshold_profile_id=row.threshold_profile_id,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _run_to_record(row: WorkflowRunORM, session: Session, *, include_children: bool = True) -> WorkflowRunRecord:
    steps: list[WorkflowRunStepRecord] = []
    events: list[WorkflowRunEventRecord] = []
    artifacts: list[WorkflowRunArtifactRecord] = []
    if include_children:
        steps = [
            _step_to_record(step)
            for step in session.scalars(
                select(WorkflowRunStepORM)
                .where(WorkflowRunStepORM.workflow_run_id == row.id)
                .order_by(WorkflowRunStepORM.id.asc())
            ).all()
        ]
        events = [
            _event_to_record(event)
            for event in session.scalars(
                select(WorkflowRunEventORM)
                .where(WorkflowRunEventORM.workflow_run_id == row.id)
                .order_by(WorkflowRunEventORM.id.asc())
            ).all()
        ]
        artifacts = [
            _artifact_to_record(artifact)
            for artifact in session.scalars(
                select(WorkflowRunArtifactORM)
                .where(WorkflowRunArtifactORM.workflow_run_id == row.id)
                .order_by(WorkflowRunArtifactORM.id.asc())
            ).all()
        ]
    warnings = _text_list(_json_list(row.warnings_json))
    notes = _text_list(_json_list(row.notes_json))
    outputs = _json_dict(row.outputs_json) if row.outputs_json else None
    current_step = None
    if row.current_step_id:
        for step in steps:
            if step.step_id == row.current_step_id:
                current_step = step.step_name
                break
    return WorkflowRunRecord(
        id=row.id,
        template_id=row.template_id,
        session_id=row.session_id,
        project_id=row.project_id,
        sample_id=row.sample_id,
        name=row.name,
        status=row.status,  # type: ignore[arg-type]
        progress_percent=float(row.progress_percent),
        current_step_id=row.current_step_id,
        current_step=current_step or row.current_step_id,
        inputs_json=_json_dict(row.inputs_json),
        outputs_json=outputs,
        outputs=outputs,
        method_id=row.method_id,
        model_version_id=row.model_version_id,
        scoring_profile_id=row.scoring_profile_id,
        threshold_profile_id=row.threshold_profile_id,
        warnings_json=warnings,
        notes_json=notes,
        warnings=warnings,
        notes=notes,
        steps=steps,
        events=events,
        artifacts=artifacts,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _add_event(
    session: Session,
    *,
    workflow_run_id: int,
    event_type: str,
    message: str,
    step_id: str | None = None,
    progress_percent: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        WorkflowRunEventORM(
            workflow_run_id=workflow_run_id,
            step_id=step_id,
            event_type=event_type,
            message=message,
            progress_percent=progress_percent,
            metadata_json=_json_dump(metadata or {}, default={}),
        )
    )


def _add_workflow_artifact(
    session: Session,
    *,
    workflow_run_id: int,
    step_id: str | None,
    title: str,
    artifact_type: str,
    artifact_id: int | None = None,
    evidence_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> WorkflowRunArtifactORM:
    row = WorkflowRunArtifactORM(
        workflow_run_id=workflow_run_id,
        step_id=step_id,
        artifact_id=artifact_id,
        evidence_id=evidence_id,
        title=title,
        artifact_type=artifact_type,
        metadata_json=_json_dump(metadata or {}, default={}),
    )
    parent_run = session.get(WorkflowRunORM, workflow_run_id)
    if parent_run is not None:
        row.method_id = parent_run.method_id
        row.model_version_id = parent_run.model_version_id
        row.scoring_profile_id = parent_run.scoring_profile_id
        row.threshold_profile_id = parent_run.threshold_profile_id
    session.add(row)
    session.flush()
    return row


def _get_template(session: Session, template_id: int | None, template_slug: str | None = None) -> WorkflowTemplateRecord | None:
    ref: str | int | None = template_slug or template_id
    builtin = _builtin_template_by_id_or_slug(ref)
    if builtin is not None:
        return _template_to_record(builtin)
    if template_id is not None:
        row = session.get(WorkflowTemplateORM, template_id)
        return _template_to_record(row) if row is not None else None
    if template_slug:
        row = session.scalar(select(WorkflowTemplateORM).where(WorkflowTemplateORM.slug == template_slug).limit(1))
        return _template_to_record(row) if row is not None else None
    return None


def list_workflow_templates(session_factory: sessionmaker[Session], *, category: str | None = None, limit: int = 200) -> list[WorkflowTemplateRecord]:
    builtin = [_template_to_record(row) for row in BUILTIN_TEMPLATES if category is None or row["category"] == category]
    with session_scope(session_factory) as session:
        stmt = select(WorkflowTemplateORM).order_by(WorkflowTemplateORM.updated_at.desc(), WorkflowTemplateORM.id.desc()).limit(limit)
        if category:
            stmt = stmt.where(WorkflowTemplateORM.category == category)
        custom = [_template_to_record(row) for row in session.scalars(stmt).all()]
    return [*builtin, *custom][:limit]


def get_workflow_template(session_factory: sessionmaker[Session], template_id: str) -> WorkflowTemplateRecord | None:
    with session_scope(session_factory) as session:
        if template_id.lstrip("-").isdigit():
            return _get_template(session, int(template_id))
        return _get_template(session, None, template_id)


def create_workflow_template(session_factory: sessionmaker[Session], payload: WorkflowTemplateCreate) -> WorkflowTemplateRecord:
    slug = _normalize_slug(payload.slug)
    if _builtin_template_by_id_or_slug(slug) is not None:
        raise WorkflowError("Workflow template slug is reserved by a built-in template.")
    with session_scope(session_factory) as session:
        if session.scalar(select(WorkflowTemplateORM).where(WorkflowTemplateORM.slug == slug).limit(1)) is not None:
            raise WorkflowError("Workflow template slug already exists.")
        row = WorkflowTemplateORM(
            name=payload.name,
            slug=slug,
            description=payload.description,
            category=payload.category,
            version=payload.version,
            is_builtin=False,
            steps_json=_json_dump(payload.steps_json, default=[]),
            required_inputs_json=_json_dump(payload.required_inputs_json, default=[]),
            optional_inputs_json=_json_dump(payload.optional_inputs_json, default=[]),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _template_to_record(row)


def update_workflow_template(session_factory: sessionmaker[Session], template_id: int, payload: WorkflowTemplateUpdate) -> WorkflowTemplateRecord | None:
    if template_id < 0:
        raise WorkflowError("Built-in workflow templates cannot be modified.")
    with session_scope(session_factory) as session:
        row = session.get(WorkflowTemplateORM, template_id)
        if row is None:
            return None
        fields = payload.model_fields_set
        for field in ("name", "description", "category", "version"):
            if field in fields:
                setattr(row, field, getattr(payload, field))
        for field in ("steps_json", "required_inputs_json", "optional_inputs_json", "metadata_json"):
            if field in fields:
                setattr(row, field, _json_dump(getattr(payload, field), default=[] if field != "metadata_json" else {}))
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _template_to_record(row)


def create_workflow_run(
    session_factory: sessionmaker[Session],
    payload: WorkflowRunCreate,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
) -> WorkflowRunRecord:
    with session_scope(session_factory) as session:
        template = _get_template(session, payload.template_id, payload.template_slug)
        if template is None:
            raise KeyError("Workflow template not found.")
        parent_session: SpectraCheckSessionORM | None = None
        if payload.session_id is not None:
            parent_session = session.get(SpectraCheckSessionORM, payload.session_id)
            if not _session_visible(parent_session, owner_scope_id=owner_scope_id):
                raise KeyError("SpectraCheck session not found.")
        project_id = payload.project_id or (parent_session.project_id if parent_session is not None else None)
        sample_id = payload.sample_id or (parent_session.sample_id if parent_session is not None else None)
        run = WorkflowRunORM(
            template_id=template.id,
            session_id=payload.session_id,
            project_id=project_id,
            sample_id=sample_id,
            name=payload.name or template.name,
            status="draft",
            progress_percent=0.0,
            inputs_json=_json_dump({**payload.inputs_json, **({"session_id": payload.session_id} if payload.session_id is not None else {})}, default={}),
            warnings_json="[]",
            notes_json=_json_dump(["Workflow run preserves human-review language and does not confirm identity."], default=[]),
            method_id=payload.method_id,
            model_version_id=payload.model_version_id,
            scoring_profile_id=payload.scoring_profile_id,
            threshold_profile_id=payload.threshold_profile_id,
            metadata_json=_json_dump({**payload.metadata_json, "template_slug": template.slug}, default={}),
        )
        session.add(run)
        session.flush()
        for step in template.steps:
            session.add(
                WorkflowRunStepORM(
                    workflow_run_id=run.id,
                    step_id=str(step.get("step_id")),
                    step_name=str(step.get("step_name") or step.get("step_id")),
                    step_type=str(step.get("step_type") or "manual"),
                    status="pending",
                    input_json="{}",
                    metadata_json=_json_dump(step, default={}),
                )
            )
        _add_event(
            session,
            workflow_run_id=run.id,
            event_type="created",
            message="Workflow run created from template.",
            progress_percent=0.0,
            metadata={"template_slug": template.slug},
        )
        _add_session_audit(
            session,
            session_id=run.session_id,
            actor_id=actor_id,
            event_type="workflow.run.create",
            message="SpectraCheck workflow run created.",
            metadata={"workflow_run_id": run.id, "template_slug": template.slug},
        )
        session.flush()
        session.refresh(run)
        return _run_to_record(run, session)


def _visible_run(session: Session, workflow_run_id: int, *, owner_scope_id: int | None) -> WorkflowRunORM | None:
    run = session.get(WorkflowRunORM, workflow_run_id)
    if run is None:
        return None
    if run.session_id is not None:
        parent = session.get(SpectraCheckSessionORM, run.session_id)
        if not _session_visible(parent, owner_scope_id=owner_scope_id):
            return None
    elif run.project_id is not None and owner_scope_id is not None:
        project = session.get(SpectraCheckProjectORM, run.project_id)
        if project is None or project.owner_id != owner_scope_id:
            return None
    return run


def get_workflow_run(session_factory: sessionmaker[Session], workflow_run_id: int, *, owner_scope_id: int | None) -> WorkflowRunRecord | None:
    with session_scope(session_factory) as session:
        run = _visible_run(session, workflow_run_id, owner_scope_id=owner_scope_id)
        return _run_to_record(run, session) if run is not None else None


def list_workflow_runs(
    session_factory: sessionmaker[Session],
    *,
    owner_scope_id: int | None,
    session_id: int | None = None,
    limit: int = 200,
) -> list[WorkflowRunRecord]:
    with session_scope(session_factory) as session:
        stmt = select(WorkflowRunORM).order_by(WorkflowRunORM.created_at.desc(), WorkflowRunORM.id.desc()).limit(limit)
        if session_id is not None:
            parent = session.get(SpectraCheckSessionORM, session_id)
            if not _session_visible(parent, owner_scope_id=owner_scope_id):
                raise KeyError("SpectraCheck session not found.")
            stmt = stmt.where(WorkflowRunORM.session_id == session_id)
        rows = list(session.scalars(stmt).all())
        visible = [row for row in rows if _visible_run(session, row.id, owner_scope_id=owner_scope_id) is not None]
        return [_run_to_record(row, session) for row in visible]


def _missing_required_inputs(template: WorkflowTemplateRecord, inputs: dict[str, Any], run_session_id: int | None) -> list[str]:
    missing: list[str] = []
    for key in template.required_inputs:
        if key == "session_id" and run_session_id is not None:
            continue
        value = inputs.get(key)
        if value is None or value == "" or value == [] or value == {}:
            missing.append(key)
    return missing


def _set_step_running(session: Session, run: WorkflowRunORM, step: WorkflowRunStepORM, *, progress: float) -> None:
    now = utcnow()
    step.status = "running"
    step.started_at = now
    run.status = "running"
    run.current_step_id = step.step_id
    run.progress_percent = progress
    _add_event(
        session,
        workflow_run_id=run.id,
        step_id=step.step_id,
        event_type="step.running",
        message=f"Workflow step started: {step.step_name}.",
        progress_percent=progress,
    )


def _finish_step(
    session: Session,
    run: WorkflowRunORM,
    step: WorkflowRunStepORM,
    *,
    status: str,
    output: dict[str, Any] | None = None,
    error_message: str | None = None,
    progress: float,
) -> None:
    step.status = status
    step.output_json = _json_dump(output or {}, default={}) if output is not None else step.output_json
    step.error_message = error_message
    step.finished_at = utcnow()
    run.progress_percent = progress
    _add_event(
        session,
        workflow_run_id=run.id,
        step_id=step.step_id,
        event_type=f"step.{status}",
        message=error_message or f"Workflow step {status}: {step.step_name}.",
        progress_percent=progress,
        metadata=output or {},
    )


def _input_file_ids_for_step(step_id: str, inputs: dict[str, Any]) -> list[int]:
    if step_id.startswith("nmr_processed"):
        raw = inputs.get("processed_file_ids") or inputs.get("input_file_ids_json") or inputs.get("file_ids") or []
    elif step_id.startswith("nmr_raw_fid"):
        raw = inputs.get("raw_file_ids") or inputs.get("input_file_ids_json") or inputs.get("file_ids") or []
    elif "lcms" in step_id:
        raw = inputs.get("lcms_file_ids") or inputs.get("input_file_ids_json") or inputs.get("file_ids") or []
    else:
        raw = inputs.get("input_file_ids_json") or inputs.get("file_ids") or []
    if isinstance(raw, int):
        return [raw]
    if isinstance(raw, list):
        out: list[int] = []
        for item in raw:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out
    return []


JOB_TYPE_BY_STEP = {
    "nmr_processed_preview": "nmr_processed_preview",
    "nmr_processed_analyze": "nmr_processed_analyze",
    "nmr_raw_fid_preview": "nmr_raw_fid_preview",
    "nmr_raw_fid_process": "nmr_raw_fid_process",
    "hrms_candidate_match": "hrms_candidate_match",
    "formula_search": "hrms_formula_search",
    "msms_annotation": "msms_annotation",
    "fragmentation_tree": "fragmentation_tree",
    "lcms_import": "lcms_import",
    "lcms_feature_detection": "lcms_feature_detection",
    "lcms_feature_grouping": "lcms_feature_grouping",
    "lcms_feature_family_consensus": "lcms_feature_family_consensus",
}


def _latest_output(session: Session, workflow_run_id: int) -> dict[str, Any]:
    for step in reversed(
        list(
            session.scalars(
                select(WorkflowRunStepORM)
                .where(WorkflowRunStepORM.workflow_run_id == workflow_run_id)
                .order_by(WorkflowRunStepORM.id.asc())
            ).all()
        )
    ):
        output = _json_dict(step.output_json)
        if output:
            return output
    return {}


def _execute_predicted_nmr_step(session: Session, run: WorkflowRunORM, step: WorkflowRunStepORM, inputs: dict[str, Any]) -> dict[str, Any]:
    evidence = SpectraCheckEvidenceRecordORM(
        session_id=run.session_id,
        layer="predicted_nmr",
        title="Predicted NMR text candidate check",
        source_tab="workflow",
        status="ready",
        score=None,
        label="requires_review",
        summary="Predicted-NMR workflow evidence was assembled for human review.",
        evidence_summary_json=_json_dump(
            [
                "NMR text and candidate notes were captured for review.",
                "This workflow result does not confirm structure identity.",
            ],
            default=[],
        ),
        contradictions_json="[]",
        warnings_json=_json_dump(
            ["Workflow evidence is review support only and must be checked by a human reviewer."],
            default=[],
        ),
        notes_json=_json_dump(["Preserve human-review language in unified evidence and reports."], default=[]),
        endpoint="/workflow-runs",
        request_preview_json=_json_dump(
            {
                "nmr_text_present": bool(inputs.get("nmr_text")),
                "candidates_text_present": bool(inputs.get("candidates_text")),
            },
            default={},
        ),
        response_json=_json_dump(
            {
                "sample_id": run.sample_id or inputs.get("sample_id"),
                "label": "requires_review",
                "human_review_required": True,
                "evidence_summary": ["Candidate/NMR text evidence captured for review."],
                "warnings": ["No identity confirmation is claimed."],
            },
            default={},
        ),
        selected_for_unified=True,
        provenance_json=_json_dump({"workflow_run_id": run.id, "step_id": step.step_id}, default={}),
    )
    session.add(evidence)
    session.flush()
    _add_workflow_artifact(
        session,
        workflow_run_id=run.id,
        step_id=step.step_id,
        evidence_id=evidence.id,
        title="Predicted NMR workflow evidence",
        artifact_type="evidence_queue",
    )
    return {"evidence_id": evidence.id, "human_review_required": True}


def _execute_add_to_queue_step(session: Session, run: WorkflowRunORM, step: WorkflowRunStepORM, inputs: dict[str, Any]) -> dict[str, Any]:
    latest = _latest_output(session, run.id)
    evidence_id = latest.get("evidence_id")
    if evidence_id:
        evidence = session.get(SpectraCheckEvidenceRecordORM, int(evidence_id))
        if evidence is not None:
            evidence.status = "ready"
            evidence.selected_for_unified = True
            evidence.updated_at = utcnow()
            return {"evidence_id": evidence.id, "status": "ready"}
    evidence = SpectraCheckEvidenceRecordORM(
        session_id=run.session_id,
        layer=str(inputs.get("layer") or "workflow"),
        title=f"{run.name} evidence",
        source_tab="workflow",
        status="ready",
        label="requires_review",
        summary="Workflow output was added to the Evidence Queue for human review.",
        evidence_summary_json=_json_dump(["Workflow output is available for review."], default=[]),
        contradictions_json="[]",
        warnings_json=_json_dump(["Workflow-generated evidence requires human review."], default=[]),
        notes_json=_json_dump(["No identity confirmation is claimed."], default=[]),
        endpoint="/workflow-runs",
        response_json=_json_dump({"sample_id": run.sample_id, "human_review_required": True}, default={}),
        selected_for_unified=True,
        provenance_json=_json_dump({"workflow_run_id": run.id, "step_id": step.step_id}, default={}),
    )
    session.add(evidence)
    session.flush()
    _add_workflow_artifact(
        session,
        workflow_run_id=run.id,
        step_id=step.step_id,
        evidence_id=evidence.id,
        title="Workflow evidence queue record",
        artifact_type="evidence_queue",
    )
    return {"evidence_id": evidence.id, "status": "ready"}


def _selected_evidence_rows(session: Session, run: WorkflowRunORM, inputs: dict[str, Any]) -> list[SpectraCheckEvidenceRecordORM]:
    selected_ids = inputs.get("selected_evidence_ids")
    stmt = select(SpectraCheckEvidenceRecordORM)
    if selected_ids:
        ids = [int(item) for item in selected_ids if str(item).isdigit()] if isinstance(selected_ids, list) else []
        stmt = stmt.where(SpectraCheckEvidenceRecordORM.id.in_(ids))
    elif run.session_id is not None:
        stmt = stmt.where(SpectraCheckEvidenceRecordORM.session_id == run.session_id).where(SpectraCheckEvidenceRecordORM.selected_for_unified.is_(True))
    else:
        return []
    return list(session.scalars(stmt.order_by(SpectraCheckEvidenceRecordORM.id.asc())).all())


def _execute_unified_step(session: Session, run: WorkflowRunORM, step: WorkflowRunStepORM, inputs: dict[str, Any]) -> dict[str, Any]:
    evidence_rows = _selected_evidence_rows(session, run, inputs)
    if not evidence_rows:
        raise WorkflowError("Unified evidence step requires selected evidence records.")
    blocked: list[int] = []
    for evidence in evidence_rows:
        latest_qc = session.scalar(
            select(QualityAssessmentORM)
            .where(QualityAssessmentORM.target_type == "evidence")
            .where(QualityAssessmentORM.target_id == evidence.id)
            .order_by(QualityAssessmentORM.id.desc())
            .limit(1)
        )
        if latest_qc is not None and latest_qc.readiness_status == "blocked_until_review" and latest_qc.override_status != "allow_with_warning":
            blocked.append(evidence.id)
    if blocked:
        raise WorkflowError(f"Unified evidence blocked by QC for evidence id(s): {blocked}.")
    result = {
        "sample_id": run.sample_id or inputs.get("sample_id"),
        "candidate_count": 0,
        "ranked_candidates": [],
        "evidence_layers_used": [row.layer for row in evidence_rows],
        "evidence_completeness": min(1.0, len(evidence_rows) / 4),
        "human_review_required": True,
        "label": "requires_review",
        "status": "requires_review",
        "warnings": ["Workflow unified evidence is a synthesis aid, not identity confirmation."],
        "notes": ["Human review is required before reporting."],
    }
    if run.session_id is not None:
        parent = session.get(SpectraCheckSessionORM, run.session_id)
        if parent is not None:
            parent.latest_unified_evidence_json = _json_dump(result, default={})
            parent.status = "review_required"
            parent.updated_at = utcnow()
    artifact = ArtifactRecordORM(
        job_id=None,
        session_id=run.session_id,
        artifact_type="unified_evidence",
        title="Workflow unified evidence",
        content_type="application/json",
        sha256=None,
        storage_key=None,
        artifact_json=_json_dump(result, default={}),
        metadata_json=_json_dump({"workflow_run_id": run.id, "step_id": step.step_id}, default={}),
    )
    session.add(artifact)
    session.flush()
    _add_workflow_artifact(
        session,
        workflow_run_id=run.id,
        step_id=step.step_id,
        artifact_id=artifact.id,
        title="Workflow unified evidence",
        artifact_type="unified_evidence",
    )
    return {"artifact_id": artifact.id, "unified_evidence": result}


def _execute_report_step(session: Session, run: WorkflowRunORM, step: WorkflowRunStepORM, inputs: dict[str, Any]) -> dict[str, Any]:
    latest = _latest_output(session, run.id)
    report = {
        "report_title": inputs.get("report_title") or f"{run.name} review report",
        "sample_id": run.sample_id or inputs.get("sample_id"),
        "human_review_required": True,
        "status": "draft_requires_review",
        "evidence_summary": ["Workflow report draft assembled from persisted evidence and artifacts."],
        "warnings": ["Report draft does not confirm identity without reviewer approval."],
        "unified_evidence": latest.get("unified_evidence"),
    }
    artifact = ArtifactRecordORM(
        session_id=run.session_id,
        artifact_type="report_json",
        title=str(report["report_title"]),
        content_type="application/json",
        artifact_json=_json_dump(report, default={}),
        metadata_json=_json_dump({"workflow_run_id": run.id, "step_id": step.step_id}, default={}),
    )
    session.add(artifact)
    session.flush()
    _add_workflow_artifact(
        session,
        workflow_run_id=run.id,
        step_id=step.step_id,
        artifact_id=artifact.id,
        title=str(report["report_title"]),
        artifact_type="report_json",
    )
    return {"artifact_id": artifact.id, "report_json": report}


def _execute_step_external(
    session_factory: sessionmaker[Session],
    run_id: int,
    step_db_id: int,
    *,
    actor_id: int | None,
    owner_scope_id: int | None,
    storage_root,
) -> tuple[str, dict[str, Any] | None, str | None]:
    with session_scope(session_factory) as session:
        run = session.get(WorkflowRunORM, run_id)
        step = session.get(WorkflowRunStepORM, step_db_id)
        if run is None or step is None:
            return ("failed", None, "Workflow run or step not found.")
        inputs = _json_dict(run.inputs_json)
        step.input_json = _json_dump(inputs, default={})
        step_id = step.step_id
    if step_id in JOB_TYPE_BY_STEP:
        job_type = JOB_TYPE_BY_STEP[step_id]
        input_file_ids = _input_file_ids_for_step(step_id, inputs)
        job = orch_store.create_analysis_job(
            session_factory,
            AnalysisJobCreate(
                session_id=run.session_id,
                sample_id=run.sample_id,
                project_id=run.project_id,
                job_type=job_type,
                input_file_ids_json=input_file_ids,
                parameters_json=inputs,
                metadata_json={"workflow_run_id": run.id, "step_id": step_id},
            ),
            owner_scope_id=owner_scope_id,
            actor_id=actor_id,
            storage_root=storage_root,
        )
        with session_scope(session_factory) as session:
            step = session.get(WorkflowRunStepORM, step_db_id)
            if step is not None:
                step.job_id = job.id
            for artifact_id in job.artifact_ids:
                _add_workflow_artifact(
                    session,
                    workflow_run_id=run_id,
                    step_id=step_id,
                    artifact_id=artifact_id,
                    title=f"{step_id} artifact {artifact_id}",
                    artifact_type="job_artifact",
                )
        if job.status == "failed":
            return ("failed", job.model_dump(mode="json"), job.error_message or f"Workflow step '{step_id}' job failed.")
        return ("succeeded", job.model_dump(mode="json"), None)
    if step_id == "quality_control_evidence":
        with session_scope(session_factory) as session:
            evidence_rows = _selected_evidence_rows(session, session.get(WorkflowRunORM, run_id), inputs)  # type: ignore[arg-type]
        assessments = []
        for evidence in evidence_rows:
            assessment = qc_store.assess_evidence(
                session_factory,
                evidence.id,
                owner_scope_id=owner_scope_id,
                actor_id=actor_id,
                payload=QualityAssessmentRequest(),
            )
            assessments.append(assessment.model_dump(mode="json"))
        blocked = [item for item in assessments if item.get("readiness_status") == "blocked_until_review"]
        return ("blocked" if blocked else "succeeded", {"assessments": assessments}, "QC blocked evidence until review." if blocked else None)
    if step_id in {"quality_control_artifacts", "quality_control_artifact"}:
        with session_scope(session_factory) as session:
            artifacts = list(
                session.scalars(
                    select(WorkflowRunArtifactORM)
                    .where(WorkflowRunArtifactORM.workflow_run_id == run_id)
                    .where(WorkflowRunArtifactORM.artifact_id.is_not(None))
                ).all()
            )
        assessments = []
        for artifact in artifacts:
            assessment = qc_store.assess_artifact(
                session_factory,
                int(artifact.artifact_id),
                owner_scope_id=owner_scope_id,
                actor_id=actor_id,
                payload=QualityAssessmentRequest(),
            )
            assessments.append(assessment.model_dump(mode="json"))
        blocked = [item for item in assessments if item.get("readiness_status") == "blocked_until_review"]
        return ("blocked" if blocked else "succeeded", {"assessments": assessments}, "QC blocked artifacts until review." if blocked else None)
    if step_id == "quality_control_file":
        assessments = []
        for file_id in _input_file_ids_for_step("nmr_raw_fid_process", inputs):
            assessment = qc_store.assess_file(
                session_factory,
                file_id,
                owner_scope_id=owner_scope_id,
                actor_id=actor_id,
                storage_root=storage_root,
                payload=QualityAssessmentRequest(),
            )
            assessments.append(assessment.model_dump(mode="json"))
        blocked = [item for item in assessments if item.get("readiness_status") == "blocked_until_review"]
        return ("blocked" if blocked else "succeeded", {"assessments": assessments}, "QC blocked file until review." if blocked else None)
    if step_id == "quality_control_session":
        if run.session_id is None:
            return ("blocked", None, "Session QC requires a SpectraCheck session id.")
        assessment = qc_store.assess_session(
            session_factory,
            run.session_id,
            owner_scope_id=owner_scope_id,
            actor_id=actor_id,
            storage_root=storage_root,
            payload=QualityAssessmentRequest(),
        )
        if assessment.readiness_status == "blocked_until_review":
            return ("blocked", assessment.model_dump(mode="json"), "Session QC blocked downstream unified evidence.")
        return ("succeeded", assessment.model_dump(mode="json"), None)
    with session_scope(session_factory) as session:
        run = session.get(WorkflowRunORM, run_id)
        step = session.get(WorkflowRunStepORM, step_db_id)
        if run is None or step is None:
            return ("failed", None, "Workflow run or step not found.")
        if step_id == "predicted_nmr_match":
            return ("succeeded", _execute_predicted_nmr_step(session, run, step, inputs), None)
        if step_id == "add_to_evidence_queue":
            return ("succeeded", _execute_add_to_queue_step(session, run, step, inputs), None)
        if step_id == "unified_evidence":
            try:
                return ("succeeded", _execute_unified_step(session, run, step, inputs), None)
            except WorkflowError as exc:
                return ("blocked", None, str(exc))
        if step_id == "report_compose":
            return ("succeeded", _execute_report_step(session, run, step, inputs), None)
        if step_id == "review_gate":
            return ("succeeded", {"human_review_required": True, "status": "requires_review"}, None)
        if step.step_type == "manual":
            return ("succeeded", {"manual_step_acknowledged": True, "human_review_required": True}, None)
    return ("failed", None, f"Workflow step '{step_id}' is not mapped to an available backend adapter.")


def start_workflow_run(
    session_factory: sessionmaker[Session],
    workflow_run_id: int,
    *,
    owner_scope_id: int | None,
    actor_id: int | None,
    storage_root,
) -> WorkflowRunRecord | None:
    with session_scope(session_factory) as session:
        run = _visible_run(session, workflow_run_id, owner_scope_id=owner_scope_id)
        if run is None:
            return None
        if run.status == "canceled":
            raise WorkflowError("Canceled workflow runs cannot be restarted.")
        template = _get_template(session, run.template_id, _json_dict(run.metadata_json).get("template_slug"))
        if template is None:
            raise WorkflowError("Workflow template not found.")
        inputs = _json_dict(run.inputs_json)
        missing = _missing_required_inputs(template, inputs, run.session_id)
        run.status = "running"
        run.started_at = run.started_at or utcnow()
        _add_event(session, workflow_run_id=run.id, event_type="started", message="Workflow run started.", progress_percent=0.0)
        if missing:
            first_step = session.scalar(
                select(WorkflowRunStepORM)
                .where(WorkflowRunStepORM.workflow_run_id == run.id)
                .order_by(WorkflowRunStepORM.id.asc())
                .limit(1)
            )
            if first_step is not None:
                first_step.status = "blocked"
                first_step.error_message = f"Missing required input(s): {', '.join(missing)}."
                first_step.finished_at = utcnow()
                run.current_step_id = first_step.step_id
            warnings = _text_list(_json_list(run.warnings_json))
            warnings.append(f"Workflow blocked because required input(s) are missing: {', '.join(missing)}.")
            run.warnings_json = _json_dump(warnings, default=[])
            run.status = "requires_review"
            run.finished_at = utcnow()
            run.progress_percent = 100.0
            _add_event(session, workflow_run_id=run.id, event_type="blocked", message=warnings[-1], progress_percent=100.0)
            _add_session_audit(session, session_id=run.session_id, actor_id=actor_id, event_type="workflow.run.blocked", message="Workflow run blocked by missing required inputs.", metadata={"workflow_run_id": run.id, "missing_inputs": missing})
            session.flush()
            session.refresh(run)
            return _run_to_record(run, session)
        steps = list(
            session.scalars(
                select(WorkflowRunStepORM)
                .where(WorkflowRunStepORM.workflow_run_id == run.id)
                .order_by(WorkflowRunStepORM.id.asc())
            ).all()
        )
        session.flush()
    total = max(1, len(steps))
    stop_status: str | None = None
    stop_message: str | None = None
    for index, detached_step in enumerate(steps, start=1):
        progress_start = round(((index - 1) / total) * 100, 2)
        progress_done = round((index / total) * 100, 2)
        with session_scope(session_factory) as session:
            run = session.get(WorkflowRunORM, workflow_run_id)
            step = session.get(WorkflowRunStepORM, detached_step.id)
            if run is None or step is None:
                return None
            _set_step_running(session, run, step, progress=progress_start)
        try:
            status, output, error = _execute_step_external(
                session_factory,
                workflow_run_id,
                detached_step.id,
                actor_id=actor_id,
                owner_scope_id=owner_scope_id,
                storage_root=storage_root,
            )
        except Exception as exc:
            status, output, error = "failed", None, str(exc)
        with session_scope(session_factory) as session:
            run = session.get(WorkflowRunORM, workflow_run_id)
            step = session.get(WorkflowRunStepORM, detached_step.id)
            if run is None or step is None:
                return None
            _finish_step(session, run, step, status=status, output=output, error_message=error, progress=progress_done)
            if status in {"blocked", "failed"}:
                stop_status = "requires_review" if status == "blocked" else "failed"
                stop_message = error or f"Workflow stopped at step {step.step_id}."
                warnings = _text_list(_json_list(run.warnings_json))
                warnings.append(stop_message)
                run.warnings_json = _json_dump(warnings, default=[])
                run.status = stop_status
                run.finished_at = utcnow()
                run.progress_percent = 100.0
                _add_event(session, workflow_run_id=run.id, step_id=step.step_id, event_type=f"workflow.{stop_status}", message=stop_message, progress_percent=100.0)
                break
    with session_scope(session_factory) as session:
        run = session.get(WorkflowRunORM, workflow_run_id)
        if run is None:
            return None
        if stop_status is None:
            run.status = "succeeded"
            run.progress_percent = 100.0
            run.finished_at = utcnow()
            run.outputs_json = _json_dump({"status": "succeeded", "human_review_required": True}, default={})
            _add_event(session, workflow_run_id=run.id, event_type="succeeded", message="Workflow run completed. Human review is still required.", progress_percent=100.0)
            _add_session_audit(session, session_id=run.session_id, actor_id=actor_id, event_type="workflow.run.succeeded", message="Workflow run completed.", metadata={"workflow_run_id": run.id, "human_review_required": True})
        else:
            run.outputs_json = _json_dump({"status": stop_status, "message": stop_message, "human_review_required": True}, default={})
            _add_session_audit(session, session_id=run.session_id, actor_id=actor_id, event_type=f"workflow.run.{stop_status}", message=stop_message or "Workflow run stopped.", metadata={"workflow_run_id": run.id})
        session.flush()
        session.refresh(run)
        return _run_to_record(run, session)


def cancel_workflow_run(session_factory: sessionmaker[Session], workflow_run_id: int, *, owner_scope_id: int | None, actor_id: int | None) -> WorkflowRunRecord | None:
    with session_scope(session_factory) as session:
        run = _visible_run(session, workflow_run_id, owner_scope_id=owner_scope_id)
        if run is None:
            return None
        if run.status in {"draft", "queued", "running"}:
            run.status = "canceled"
            run.finished_at = utcnow()
            for step in session.scalars(select(WorkflowRunStepORM).where(WorkflowRunStepORM.workflow_run_id == run.id)).all():
                if step.status in {"pending", "queued", "running"}:
                    step.status = "skipped"
                    step.finished_at = utcnow()
            _add_event(session, workflow_run_id=run.id, event_type="canceled", message="Workflow run canceled before completion.", progress_percent=run.progress_percent)
        else:
            _add_event(session, workflow_run_id=run.id, event_type="cancel_requested", message=f"Cancel requested after workflow reached status '{run.status}'.", progress_percent=run.progress_percent)
        _add_session_audit(session, session_id=run.session_id, actor_id=actor_id, event_type="workflow.run.cancel", message="Workflow run cancellation requested.", metadata={"workflow_run_id": run.id, "status": run.status})
        session.flush()
        session.refresh(run)
        return _run_to_record(run, session)


def list_workflow_events(session_factory: sessionmaker[Session], workflow_run_id: int, *, owner_scope_id: int | None) -> list[WorkflowRunEventRecord] | None:
    with session_scope(session_factory) as session:
        run = _visible_run(session, workflow_run_id, owner_scope_id=owner_scope_id)
        if run is None:
            return None
        return [
            _event_to_record(row)
            for row in session.scalars(
                select(WorkflowRunEventORM)
                .where(WorkflowRunEventORM.workflow_run_id == workflow_run_id)
                .order_by(WorkflowRunEventORM.id.asc())
            ).all()
        ]


def list_workflow_steps(session_factory: sessionmaker[Session], workflow_run_id: int, *, owner_scope_id: int | None) -> list[WorkflowRunStepRecord] | None:
    with session_scope(session_factory) as session:
        run = _visible_run(session, workflow_run_id, owner_scope_id=owner_scope_id)
        if run is None:
            return None
        return [
            _step_to_record(row)
            for row in session.scalars(
                select(WorkflowRunStepORM)
                .where(WorkflowRunStepORM.workflow_run_id == workflow_run_id)
                .order_by(WorkflowRunStepORM.id.asc())
            ).all()
        ]


def list_workflow_artifacts(session_factory: sessionmaker[Session], workflow_run_id: int, *, owner_scope_id: int | None) -> list[WorkflowRunArtifactRecord] | None:
    with session_scope(session_factory) as session:
        run = _visible_run(session, workflow_run_id, owner_scope_id=owner_scope_id)
        if run is None:
            return None
        return [
            _artifact_to_record(row)
            for row in session.scalars(
                select(WorkflowRunArtifactORM)
                .where(WorkflowRunArtifactORM.workflow_run_id == workflow_run_id)
                .order_by(WorkflowRunArtifactORM.id.asc())
            ).all()
        ]
