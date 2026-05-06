from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    CompactModuleSummary,
    MobileActionDraft,
    MobileActionDraftCreate,
    MobileActionDraftPatch,
    MobileActionQueueItem,
    MobileActionQueueResponse,
    MobileCommandCenterResponse,
    MobileCommandCenterSection,
    MobileConfigResponse,
    MobileDashboardResponse,
    MobileDeviceSession,
    MobileDeviceSessionCreate,
    MobileDeviceSessionPatch,
    MobileJobsSummary,
    MobileNavigationItem,
    MobileNotification,
    MobileNotificationCreate,
    MobileNotificationPatch,
    MobileOfflineSafeSummary,
    MobilePushSubscription,
    MobilePushSubscriptionCreate,
    MobileResourceSummary,
    MobileSyncItemResult,
    MobileSyncRequest,
    MobileSyncResponse,
    MobileSyncResult,
    MobileViewPreference,
    MobileViewPreferencePatch,
)
from .orm import (
    AnalysisORM,
    AuditEventORM,
    CompactModuleSummaryORM,
    CrossModuleActionItemORM,
    JobORM,
    MobileActionDraftORM,
    MobileDeviceSessionORM,
    MobileNotificationORM,
    MobilePushSubscriptionORM,
    MobileSyncResultORM,
    MobileViewPreferenceORM,
    ReactionExecutionBatchORM,
    ReactionExecutionEventORM,
    ReactionExecutionItemORM,
    ReactionProjectORM,
    RegulatoryActionItemORM,
    RegulatoryDossierORM,
    RegulatoryRequirementORM,
    RegulatoryReviewDecisionORM,
    ReportORM,
    ReviewDecisionORM,
    SpectraCheckAuditEventORM,
    SpectraCheckEvidenceRecordORM,
    SpectraCheckReportRecordORM,
    SpectraCheckReviewDecisionORM,
    SpectraCheckSessionORM,
    utcnow,
)


class MobileExperienceError(ValueError):
    pass


class MobileExperienceNotFoundError(MobileExperienceError):
    pass


class MobileSyncValidationError(MobileExperienceError):
    def __init__(self, messages: list[str]) -> None:
        super().__init__("; ".join(messages))
        self.messages = messages


@dataclass(frozen=True)
class MobileActor:
    user_id: int | None = None
    email: str | None = None
    system_api_key: bool = False


DEFAULT_MOBILE_PROGRAM_ORDER = ["spectracheck", "regulatory_hub", "reaction_optimization"]
_PROGRAM_LABELS = {
    "spectracheck": "SpectraCheck",
    "regulatory_hub": "Regulatory Hub",
    "reaction_optimization": "Reaction Optimization",
}
_PROGRAM_ROUTES = {
    "spectracheck": "/spectracheck",
    "regulatory_hub": "/regulatory",
    "reaction_optimization": "/reactions",
}
MOBILE_SAFETY_RULES = [
    "Mobile drafts may contain decisions, comments, status updates, and short notes only.",
    "Raw FID files, raw spectra, full regulatory source text, full SMILES libraries, model artifacts, passwords, tokens, and secrets are rejected.",
    "Offline drafts are not final decisions until server sync validates and accepts them.",
    "Every accepted mobile review or approval action writes an audit event.",
]
_DRAFT_PAYLOAD_MAX_BYTES = 30_000
_STRING_VALUE_MAX_CHARS = 5_000
_FORBIDDEN_KEY_MARKERS = (
    "raw_fid",
    "fid_bytes",
    "free_induction_decay",
    "raw_spectrum",
    "raw_spectra",
    "spectrum_points",
    "spectra_points",
    "spectral_points",
    "intensity_array",
    "mz_array",
    "raw_source",
    "full_source",
    "source_text",
    "full_text",
    "full_smiles",
    "smiles_library",
    "model_artifact",
    "password",
    "passwd",
    "token",
    "secret",
    "api_key",
    "authorization",
    "bearer",
    "credential",
)
_SECRET_VALUE_MARKERS = ("-----BEGIN", "Bearer ", "x-api-key", "api_key=", "password=")
_SPECTRUM_POINT_KEYS = {"ppm", "shift", "mz", "intensity", "x", "y"}
_ANALYSIS_DECISIONS = {
    "approve": "approved",
    "approved": "approved",
    "reject": "rejected",
    "rejected": "rejected",
    "override": "approved",
    "request_changes": "needs_revision",
    "needs_changes": "needs_revision",
    "needs_revision": "needs_revision",
}
_SPECTRACHECK_DECISIONS = {
    "approve": ("approved_confirmed", "approved"),
    "approved": ("approved_confirmed", "approved"),
    "approved_confirmed": ("approved_confirmed", "approved"),
    "approved_plausible": ("approved_plausible", "approved"),
    "reject": ("rejected", "blocked"),
    "rejected": ("rejected", "blocked"),
    "request_changes": ("needs_changes", "review_required"),
    "needs_changes": ("needs_changes", "review_required"),
    "defer": ("deferred", "review_required"),
    "deferred": ("deferred", "review_required"),
}
_REGULATORY_ACTION_STATUSES = {"open", "in_progress", "resolved", "dismissed", "deferred"}
_CROSS_MODULE_ACTION_STATUSES = {"open", "in_progress", "resolved", "dismissed", "blocked"}
_REACTION_EXECUTION_STATUSES = {"planned", "running", "completed", "failed", "skipped", "canceled"}


def get_config(
    session_factory: sessionmaker[Session],
    *,
    actor: MobileActor,
    device_session_id: int | None = None,
) -> MobileConfigResponse:
    with session_scope(session_factory) as session:
        pref = _get_or_create_preference(
            session,
            user_email=actor.email,
            device_session_id=device_session_id,
        )
        return _config_response(pref)


def update_config(
    session_factory: sessionmaker[Session],
    payload: MobileViewPreferencePatch,
    *,
    actor: MobileActor,
) -> MobileConfigResponse:
    if payload.metadata_json is not None:
        _assert_safe_mobile_json(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        pref = _get_or_create_preference(
            session,
            user_email=_email_for_payload(payload.user_email, actor),
            device_session_id=payload.device_session_id,
        )
        updates = payload.model_dump(exclude_unset=True)
        for field in (
            "preferred_home",
            "compact_mode",
            "bottom_nav_enabled",
            "reduce_motion",
            "high_contrast",
        ):
            if field in updates:
                setattr(pref, field, updates[field])
        if payload.user_email is not None:
            pref.user_email = str(payload.user_email).lower()
        if payload.device_session_id is not None:
            _require_device_session(session, payload.device_session_id)
            pref.device_session_id = payload.device_session_id
        if payload.metadata_json is not None:
            pref.metadata_json = _json_dump(payload.metadata_json)
        pref.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="mobile.config.update",
            message="Mobile view preferences updated.",
            entity_type="mobile_view_preference",
            entity_id=pref.id,
        )
        session.flush()
        return _config_response(pref)


def create_device_session(
    session_factory: sessionmaker[Session],
    payload: MobileDeviceSessionCreate,
    *,
    actor: MobileActor,
) -> MobileDeviceSession:
    _assert_safe_mobile_json(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        row = MobileDeviceSessionORM(
            user_email=_email_for_payload(payload.user_email, actor),
            device_label=_clean_optional(payload.device_label),
            device_type=payload.device_type,
            platform=_clean_optional(payload.platform),
            browser=_clean_optional(payload.browser),
            last_seen_at=utcnow(),
            status="active",
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="mobile.device_session.create",
            message="Mobile device session registered.",
            entity_type="mobile_device_session",
            entity_id=row.id,
        )
        return _device_session_to_record(row)


def list_device_sessions(
    session_factory: sessionmaker[Session],
    *,
    actor: MobileActor,
    status: str | None = None,
    limit: int = 200,
) -> list[MobileDeviceSession]:
    with session_scope(session_factory) as session:
        stmt = select(MobileDeviceSessionORM).order_by(
            MobileDeviceSessionORM.last_seen_at.desc(), MobileDeviceSessionORM.id.desc()
        )
        if status is not None:
            stmt = stmt.where(MobileDeviceSessionORM.status == status)
        if actor.email is not None and not actor.system_api_key:
            stmt = stmt.where(MobileDeviceSessionORM.user_email == actor.email.lower())
        rows = session.scalars(stmt.limit(limit)).all()
        return [_device_session_to_record(row) for row in rows]


def update_device_session(
    session_factory: sessionmaker[Session],
    device_session_id: int,
    payload: MobileDeviceSessionPatch,
    *,
    actor: MobileActor,
) -> MobileDeviceSession:
    if payload.metadata_json is not None:
        _assert_safe_mobile_json(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        row = _require_device_session(session, device_session_id)
        _assert_session_visible(row, actor=actor)
        updates = payload.model_dump(exclude_unset=True)
        for field in ("device_label", "device_type", "platform", "browser", "status"):
            if field in updates:
                setattr(row, field, _clean_optional(updates[field]) if field != "status" else updates[field])
        if payload.user_email is not None:
            row.user_email = str(payload.user_email).lower()
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.last_seen_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="mobile.device_session.update",
            message="Mobile device session updated.",
            entity_type="mobile_device_session",
            entity_id=row.id,
            metadata={"status": row.status},
        )
        return _device_session_to_record(row)


def dashboard_summary(session_factory: sessionmaker[Session]) -> MobileDashboardResponse:
    summary = build_compact_module_summary(session_factory, scope="global")
    return MobileDashboardResponse(
        module_order=list(DEFAULT_MOBILE_PROGRAM_ORDER),
        summary=summary,
        compact_payload=True,
        generated_at=summary.generated_at,
    )


def command_center_summary(session_factory: sessionmaker[Session]) -> MobileCommandCenterResponse:
    summary = build_compact_module_summary(session_factory, scope="global")
    sections = [
        MobileCommandCenterSection(
            program_key="spectracheck",
            display_name="SpectraCheck",
            display_order=1,
            summary_json=summary.spectracheck_summary_json,
        ),
        MobileCommandCenterSection(
            program_key="regulatory_hub",
            display_name="Regulatory Hub",
            display_order=2,
            summary_json=summary.regulatory_summary_json,
        ),
        MobileCommandCenterSection(
            program_key="reaction_optimization",
            display_name="Reaction Optimization",
            display_order=3,
            summary_json=summary.reaction_summary_json,
        ),
    ]
    return MobileCommandCenterResponse(
        module_order=list(DEFAULT_MOBILE_PROGRAM_ORDER),
        sections=sections,
        action_summary_json=summary.action_summary_json,
        generated_at=summary.generated_at,
    )


def build_compact_module_summary(
    session_factory: sessionmaker[Session],
    *,
    scope: str,
    scope_id: str | None = None,
) -> CompactModuleSummary:
    with session_scope(session_factory) as session:
        spectracheck = _spectracheck_summary(session, scope, scope_id)
        regulatory = _regulatory_summary(session, scope, scope_id)
        reaction = _reaction_summary(session, scope, scope_id)
        actions = _action_summary(session, scope, scope_id)
        row = CompactModuleSummaryORM(
            scope=scope,
            scope_id=scope_id,
            spectracheck_summary_json=_json_dump(spectracheck),
            regulatory_summary_json=_json_dump(regulatory),
            reaction_summary_json=_json_dump(reaction),
            action_summary_json=_json_dump(actions),
            generated_at=utcnow(),
            metadata_json=_json_dump(
                {
                    "compact_payload": True,
                    "program_order": DEFAULT_MOBILE_PROGRAM_ORDER,
                    "sensitive_payloads_excluded": True,
                    "appendices_excluded": True,
                }
            ),
        )
        session.add(row)
        session.flush()
        return _compact_summary_to_record(row)


def spectracheck_session_summary(
    session_factory: sessionmaker[Session],
    session_id: int,
) -> MobileResourceSummary:
    with session_scope(session_factory) as session:
        row = session.get(SpectraCheckSessionORM, session_id)
        if row is None:
            raise MobileExperienceNotFoundError("SpectraCheck session not found.")
        evidence_rows = session.scalars(
            select(SpectraCheckEvidenceRecordORM)
            .where(SpectraCheckEvidenceRecordORM.session_id == session_id)
            .order_by(SpectraCheckEvidenceRecordORM.id.desc())
            .limit(10)
        ).all()
        review_count = _count(
            session,
            select(func.count())
            .select_from(SpectraCheckReviewDecisionORM)
            .where(SpectraCheckReviewDecisionORM.session_id == session_id),
        )
        report_count = _count(
            session,
            select(func.count())
            .select_from(SpectraCheckReportRecordORM)
            .where(SpectraCheckReportRecordORM.session_id == session_id),
        )
        summary = {
            "program_key": "spectracheck",
            "project_id": row.project_id,
            "sample_pk": row.sample_pk,
            "sample_id": row.sample_id,
            "evidence_count": len(evidence_rows),
            "review_count": review_count,
            "report_count": report_count,
            "evidence": [
                {
                    "id": item.id,
                    "layer": item.layer,
                    "title": item.title,
                    "status": item.status,
                    "score": item.score,
                    "summary": _truncate(item.summary, 360),
                }
                for item in evidence_rows
            ],
        }
        return MobileResourceSummary(
            target_type="spectracheck_session",
            target_id=str(row.id),
            title=row.title,
            status=row.status,
            summary_json=summary,
            warnings_json=[],
            generated_at=utcnow(),
        )


def regulatory_dossier_summary(
    session_factory: sessionmaker[Session],
    dossier_id: int,
) -> MobileResourceSummary:
    with session_scope(session_factory) as session:
        row = session.get(RegulatoryDossierORM, dossier_id)
        if row is None:
            raise MobileExperienceNotFoundError("Regulatory dossier not found.")
        requirement_count = _count(
            session,
            select(func.count())
            .select_from(RegulatoryRequirementORM)
            .where(RegulatoryRequirementORM.dossier_id == dossier_id),
        )
        open_action_count = _count(
            session,
            select(func.count())
            .select_from(RegulatoryActionItemORM)
            .where(RegulatoryActionItemORM.dossier_id == dossier_id)
            .where(RegulatoryActionItemORM.status.in_(["open", "in_progress", "deferred"])),
        )
        review_count = _count(
            session,
            select(func.count())
            .select_from(RegulatoryReviewDecisionORM)
            .where(RegulatoryReviewDecisionORM.dossier_id == dossier_id),
        )
        summary = {
            "program_key": "regulatory_hub",
            "project_id": row.project_id,
            "sample_id": row.sample_id,
            "spectracheck_session_id": row.spectracheck_session_id,
            "reaction_project_id": row.reaction_project_id,
            "product_name": row.product_name,
            "compound_name": row.compound_name,
            "requirement_count": requirement_count,
            "open_action_count": open_action_count,
            "review_count": review_count,
        }
        return MobileResourceSummary(
            target_type="regulatory_dossier",
            target_id=str(row.id),
            title=row.title,
            status=row.status,
            summary_json=summary,
            warnings_json=[],
            generated_at=utcnow(),
        )


def reaction_project_summary(
    session_factory: sessionmaker[Session],
    reaction_project_id: int,
) -> MobileResourceSummary:
    with session_scope(session_factory) as session:
        row = session.get(ReactionProjectORM, reaction_project_id)
        if row is None:
            raise MobileExperienceNotFoundError("Reaction project not found.")
        batch_count = _count(
            session,
            select(func.count())
            .select_from(ReactionExecutionBatchORM)
            .where(ReactionExecutionBatchORM.reaction_project_id == reaction_project_id),
        )
        execution_counts = _status_counts(
            session.scalars(
                select(ReactionExecutionItemORM).where(
                    ReactionExecutionItemORM.reaction_project_id == reaction_project_id
                )
            ).all()
        )
        summary = {
            "program_key": "reaction_optimization",
            "objective": row.objective,
            "target_product_name": row.target_product_name,
            "execution_batch_count": batch_count,
            "execution_item_counts_json": execution_counts,
            "latest_updated_at": row.updated_at.isoformat(),
        }
        return MobileResourceSummary(
            target_type="reaction_project",
            target_id=str(row.id),
            title=row.name,
            status=row.status,
            summary_json=summary,
            warnings_json=[],
            generated_at=utcnow(),
        )


def action_queue(
    session_factory: sessionmaker[Session],
    *,
    actor: MobileActor,
    device_session_id: int | None = None,
    limit: int = 100,
) -> MobileActionQueueResponse:
    with session_scope(session_factory) as session:
        items: list[MobileActionQueueItem] = []
        cross_actions = session.scalars(
            select(CrossModuleActionItemORM)
            .where(CrossModuleActionItemORM.status.in_(["open", "in_progress", "blocked"]))
            .order_by(CrossModuleActionItemORM.id.desc())
            .limit(limit)
        ).all()
        for row in cross_actions:
            items.append(
                MobileActionQueueItem(
                    id=f"cross-module-{row.id}",
                    source="cross_module_action",
                    title=row.title,
                    status=row.status,
                    severity=_mobile_severity(row.severity),
                    target_type=row.target_resource_type or row.source_resource_type,
                    target_id=str(row.target_resource_id or row.source_resource_id),
                    action_type=row.action_type,
                    module_key=row.target_program,
                    created_at=row.created_at,
                )
            )
        draft_stmt = (
            select(MobileActionDraftORM)
            .where(MobileActionDraftORM.status.in_(["draft", "queued_for_sync", "rejected"]))
            .order_by(MobileActionDraftORM.id.desc())
            .limit(limit)
        )
        if device_session_id is not None:
            draft_stmt = draft_stmt.where(MobileActionDraftORM.device_session_id == device_session_id)
        elif actor.email is not None and not actor.system_api_key:
            draft_stmt = draft_stmt.where(MobileActionDraftORM.user_email == actor.email.lower())
        for row in session.scalars(draft_stmt).all():
            items.append(
                MobileActionQueueItem(
                    id=f"draft-{row.id}",
                    source="draft",
                    title=f"{row.action_type.replace('_', ' ').title()} draft",
                    status=row.status,
                    severity="warning" if row.status == "rejected" else "info",
                    target_type=row.target_type,
                    target_id=row.target_id,
                    action_type=row.action_type,
                    module_key=_module_for_target(row.target_type),
                    created_at=row.created_at,
                    summary_json={"validation_warnings_json": _json_list(row.validation_warnings_json)},
                )
            )
        notification_stmt = (
            select(MobileNotificationORM)
            .where(MobileNotificationORM.status == "unread")
            .order_by(MobileNotificationORM.id.desc())
            .limit(limit)
        )
        if actor.email is not None and not actor.system_api_key:
            notification_stmt = notification_stmt.where(
                MobileNotificationORM.user_email == actor.email.lower()
            )
        for row in session.scalars(notification_stmt).all():
            items.append(
                MobileActionQueueItem(
                    id=f"notification-{row.id}",
                    source="notification",
                    title=row.title,
                    status=row.status,
                    severity=_mobile_severity(row.severity),
                    target_type=row.target_type,
                    target_id=row.target_id,
                    action_type=row.notification_type,
                    module_key=_module_for_target(row.target_type),
                    created_at=row.created_at,
                )
            )
        counts: dict[str, int] = {}
        for item in items:
            counts[item.source] = counts.get(item.source, 0) + 1
        return MobileActionQueueResponse(
            items=items[:limit],
            counts_json=counts,
            generated_at=utcnow(),
        )


def create_action_draft(
    session_factory: sessionmaker[Session],
    payload: MobileActionDraftCreate,
    *,
    actor: MobileActor,
) -> MobileActionDraft:
    _assert_safe_mobile_json(payload.draft_payload_json, path="draft_payload_json")
    _assert_safe_mobile_json(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        if payload.device_session_id is not None:
            _require_device_session(session, payload.device_session_id)
        row = MobileActionDraftORM(
            user_email=_email_for_payload(payload.user_email, actor),
            device_session_id=payload.device_session_id,
            action_type=payload.action_type,
            target_type=payload.target_type,
            target_id=payload.target_id,
            draft_payload_json=_json_dump(payload.draft_payload_json),
            status=payload.status,
            validation_warnings_json="[]",
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="mobile.action_draft.create",
            message="Mobile action draft saved for server-side sync validation.",
            entity_type="mobile_action_draft",
            entity_id=row.id,
            metadata={"action_type": row.action_type, "target_type": row.target_type},
        )
        return _draft_to_record(row)


def list_action_drafts(
    session_factory: sessionmaker[Session],
    *,
    actor: MobileActor,
    device_session_id: int | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[MobileActionDraft]:
    with session_scope(session_factory) as session:
        stmt = select(MobileActionDraftORM).order_by(MobileActionDraftORM.id.desc()).limit(limit)
        if device_session_id is not None:
            stmt = stmt.where(MobileActionDraftORM.device_session_id == device_session_id)
        elif actor.email is not None and not actor.system_api_key:
            stmt = stmt.where(MobileActionDraftORM.user_email == actor.email.lower())
        if status is not None:
            stmt = stmt.where(MobileActionDraftORM.status == status)
        return [_draft_to_record(row) for row in session.scalars(stmt).all()]


def update_action_draft(
    session_factory: sessionmaker[Session],
    draft_id: int,
    payload: MobileActionDraftPatch,
    *,
    actor: MobileActor,
) -> MobileActionDraft:
    if payload.draft_payload_json is not None:
        _assert_safe_mobile_json(payload.draft_payload_json, path="draft_payload_json")
    if payload.metadata_json is not None:
        _assert_safe_mobile_json(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        row = session.get(MobileActionDraftORM, draft_id)
        if row is None:
            raise MobileExperienceNotFoundError("Mobile action draft not found.")
        _assert_draft_visible(row, actor=actor)
        updates = payload.model_dump(exclude_unset=True)
        for field in ("action_type", "target_type", "target_id", "status"):
            if field in updates:
                setattr(row, field, updates[field])
        if payload.draft_payload_json is not None:
            row.draft_payload_json = _json_dump(payload.draft_payload_json)
            row.validation_warnings_json = "[]"
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.updated_at = utcnow()
        _audit(
            session,
            actor=actor,
            event_type="mobile.action_draft.update",
            message="Mobile action draft updated.",
            entity_type="mobile_action_draft",
            entity_id=row.id,
            metadata={"status": row.status},
        )
        return _draft_to_record(row)


def sync_action_drafts(
    session_factory: sessionmaker[Session],
    payload: MobileSyncRequest,
    *,
    actor: MobileActor,
) -> MobileSyncResponse:
    if payload.metadata_json:
        _assert_safe_mobile_json(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        if payload.device_session_id is not None:
            device = _require_device_session(session, payload.device_session_id)
            device.last_seen_at = utcnow()
        rows = _drafts_for_sync(session, payload=payload, actor=actor)
        items: list[MobileSyncItemResult] = []
        warnings: list[str] = []
        synced = 0
        rejected = 0
        for row in rows:
            try:
                _assert_draft_visible(row, actor=actor)
                _assert_safe_mobile_json(_json_dict(row.draft_payload_json), path="draft_payload_json")
                audit_ids = _apply_synced_draft(session, row, actor=actor)
            except MobileSyncValidationError as exc:
                messages = exc.messages
                row.status = "rejected"
                row.validation_warnings_json = _json_dump(messages)
                row.updated_at = utcnow()
                warnings.extend([f"draft:{row.id}:{message}" for message in messages])
                rejected += 1
                items.append(
                    MobileSyncItemResult(
                        draft_id=row.id,
                        action_type=row.action_type,  # type: ignore[arg-type]
                        target_type=row.target_type,
                        target_id=row.target_id,
                        status="rejected",
                        validation_messages=messages,
                        audit_event_ids=[],
                    )
                )
                continue
            row.status = "synced"
            row.validation_warnings_json = "[]"
            row.updated_at = utcnow()
            synced += 1
            items.append(
                MobileSyncItemResult(
                    draft_id=row.id,
                    action_type=row.action_type,  # type: ignore[arg-type]
                    target_type=row.target_type,
                    target_id=row.target_id,
                    status="synced",
                    validation_messages=[],
                    audit_event_ids=audit_ids,
                )
            )
        result_row = MobileSyncResultORM(
            device_session_id=payload.device_session_id,
            synced_count=synced,
            rejected_count=rejected,
            warnings_json=_json_dump(warnings),
            notes_json=_json_dump(
                [
                    "Offline mobile drafts are not final until this server sync accepts them.",
                    "Accepted mobile review and approval actions are auditable.",
                ]
            ),
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(result_row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="mobile.sync.complete",
            message="Mobile action draft sync completed.",
            entity_type="mobile_sync_result",
            entity_id=result_row.id,
            metadata={"synced_count": synced, "rejected_count": rejected},
        )
        return MobileSyncResponse(result=_sync_result_to_record(result_row), items=items)


def create_push_subscription(
    session_factory: sessionmaker[Session],
    payload: MobilePushSubscriptionCreate,
    *,
    actor: MobileActor,
) -> MobilePushSubscription:
    endpoint_hash = hashlib.sha256(payload.endpoint.encode("utf-8")).hexdigest()
    sanitized = _sanitize_push_subscription(payload.subscription_json, endpoint_hash=endpoint_hash)
    _assert_safe_mobile_json(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        row = session.scalar(
            select(MobilePushSubscriptionORM).where(
                MobilePushSubscriptionORM.endpoint_hash == endpoint_hash
            )
        )
        if row is None:
            row = MobilePushSubscriptionORM(
                user_email=_email_for_payload(payload.user_email, actor),
                endpoint_hash=endpoint_hash,
                subscription_json=_json_dump(sanitized),
                status="active",
                metadata_json=_json_dump(payload.metadata_json),
            )
            session.add(row)
        else:
            row.user_email = _email_for_payload(payload.user_email, actor)
            row.subscription_json = _json_dump(sanitized)
            row.status = "active"
            row.updated_at = utcnow()
            row.metadata_json = _json_dump(payload.metadata_json)
        try:
            session.flush()
        except IntegrityError as exc:
            raise MobileExperienceError("Push subscription endpoint hash already exists.") from exc
        _audit(
            session,
            actor=actor,
            event_type="mobile.push_subscription.upsert",
            message="Mobile push subscription registered by endpoint hash.",
            entity_type="mobile_push_subscription",
            entity_id=row.id,
            metadata={"endpoint_hash": endpoint_hash},
        )
        return _push_subscription_to_record(row)


def create_notification(
    session_factory: sessionmaker[Session],
    payload: MobileNotificationCreate,
    *,
    actor: MobileActor,
) -> MobileNotification:
    _assert_safe_mobile_json(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        row = MobileNotificationORM(
            user_email=_email_for_payload(payload.user_email, actor),
            notification_type=payload.notification_type,
            title=payload.title,
            message=payload.message,
            target_type=payload.target_type,
            target_id=payload.target_id,
            severity=payload.severity,
            status="unread",
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="mobile.notification.create",
            message="Mobile notification created.",
            entity_type="mobile_notification",
            entity_id=row.id,
            metadata={"notification_type": row.notification_type, "target_type": row.target_type},
        )
        return _notification_to_record(row)


def list_notifications(
    session_factory: sessionmaker[Session],
    *,
    actor: MobileActor,
    status: str | None = None,
    limit: int = 100,
) -> list[MobileNotification]:
    with session_scope(session_factory) as session:
        stmt = select(MobileNotificationORM).order_by(MobileNotificationORM.id.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(MobileNotificationORM.status == status)
        if actor.email is not None and not actor.system_api_key:
            stmt = stmt.where(MobileNotificationORM.user_email == actor.email.lower())
        return [_notification_to_record(row) for row in session.scalars(stmt).all()]


def update_notification(
    session_factory: sessionmaker[Session],
    notification_id: int,
    payload: MobileNotificationPatch,
    *,
    actor: MobileActor,
) -> MobileNotification:
    if payload.metadata_json is not None:
        _assert_safe_mobile_json(payload.metadata_json, path="metadata_json")
    with session_scope(session_factory) as session:
        row = session.get(MobileNotificationORM, notification_id)
        if row is None:
            raise MobileExperienceNotFoundError("Mobile notification not found.")
        if actor.email is not None and not actor.system_api_key and row.user_email != actor.email.lower():
            raise MobileExperienceNotFoundError("Mobile notification not found.")
        row.status = payload.status
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        _audit(
            session,
            actor=actor,
            event_type="mobile.notification.update",
            message="Mobile notification status updated.",
            entity_type="mobile_notification",
            entity_id=row.id,
            metadata={"status": row.status},
        )
        return _notification_to_record(row)


def report_preview(
    session_factory: sessionmaker[Session],
    report_id: int,
) -> MobileReportPreview:
    from .models import MobileReportPreview

    with session_scope(session_factory) as session:
        row = session.get(ReportORM, report_id)
        if row is not None:
            report_json = _json_dict(row.report_json)
            analysis = session.get(AnalysisORM, row.analysis_id)
            preview_sections = _stored_report_preview_sections(report_json, analysis)
            omitted = _omitted_report_sections(report_json)
            return MobileReportPreview(
                id=row.id,
                report_type="analysis_evidence_report",
                title=row.title,
                version=row.version,
                created_at=row.created_at,
                target_type="analysis",
                target_id=str(row.analysis_id),
                preview_sections=preview_sections,
                omitted_sections=omitted,
                raw_appendices_included=False,
                compact_payload=True,
            )
        sc_row = session.get(SpectraCheckReportRecordORM, report_id)
        if sc_row is None:
            raise MobileExperienceNotFoundError("Report not found.")
        report_json = _json_dict(sc_row.report_json)
        return MobileReportPreview(
            id=sc_row.id,
            report_type="spectracheck_report",
            title=sc_row.report_title,
            version=None,
            created_at=sc_row.created_at,
            target_type="spectracheck_session",
            target_id=str(sc_row.session_id),
            preview_sections=[
                {
                    "section": "summary",
                    "status": sc_row.status,
                    "report_sha256": sc_row.report_sha256,
                    "summary_json": _public_json(report_json),
                }
            ],
            omitted_sections=["report_html", "raw_appendices", "raw_spectra"],
            raw_appendices_included=False,
            compact_payload=True,
        )


def jobs_summary(session_factory: sessionmaker[Session], *, limit: int = 20) -> MobileJobsSummary:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(JobORM).order_by(JobORM.id.desc()).limit(max(limit, 100))
        ).all()
        active = [row for row in rows if row.status in {"pending", "queued", "processing"}]
        failed = [row for row in rows if row.status == "failed"]
        completed = [row for row in rows if row.status == "completed"]
        review_required = [row for row in rows if row.review_required]
        focus = (active + failed + review_required + completed)[:limit]
        return MobileJobsSummary(
            active_count=len(active),
            failed_count=len(failed),
            completed_count=len(completed),
            review_required_count=len(review_required),
            jobs=[
                {
                    "id": row.id,
                    "job_name": row.job_name,
                    "status": row.status,
                    "review_required": row.review_required,
                    "completed_items": row.completed_items,
                    "total_items": row.total_items,
                    "created_at": row.created_at.isoformat(),
                    "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                }
                for row in focus
            ],
            generated_at=utcnow(),
        )


def offline_safe_summary(
    session_factory: sessionmaker[Session],
    *,
    actor: MobileActor,
) -> MobileOfflineSafeSummary:
    with session_scope(session_factory) as session:
        stmt = select(MobileActionDraftORM)
        if actor.email is not None and not actor.system_api_key:
            stmt = stmt.where(MobileActionDraftORM.user_email == actor.email.lower())
        counts = _status_counts(session.scalars(stmt).all())
        return MobileOfflineSafeSummary(
            offline_drafts_allowed=True,
            server_sync_required=True,
            final_decisions_offline=False,
            safety_rules=list(MOBILE_SAFETY_RULES),
            draft_counts_json=counts,
            generated_at=utcnow(),
        )


def _apply_synced_draft(
    session: Session,
    row: MobileActionDraftORM,
    *,
    actor: MobileActor,
) -> list[int]:
    payload = _json_dict(row.draft_payload_json)
    if row.status not in {"draft", "queued_for_sync"}:
        raise MobileSyncValidationError([f"draft_status_not_syncable: {row.status}"])
    if row.action_type == "review_decision":
        return _apply_review_decision(session, row, payload, actor=actor)
    if row.action_type == "evidence_comment":
        return _apply_audit_only_action(
            session,
            row,
            payload,
            actor=actor,
            required_note=True,
            event_type="mobile.evidence_comment.sync",
            message="Mobile evidence comment synced after server-side target validation.",
        )
    if row.action_type == "regulatory_action_update":
        return _apply_regulatory_action_update(session, row, payload, actor=actor)
    if row.action_type == "reaction_execution_update":
        return _apply_reaction_execution_update(session, row, payload, actor=actor)
    if row.action_type == "report_review":
        return _apply_report_review(session, row, payload, actor=actor)
    if row.action_type == "qc_override":
        return _apply_audit_only_action(
            session,
            row,
            payload,
            actor=actor,
            required_note=True,
            event_type="mobile.qc_override.sync",
            message="Mobile QC override request synced as an auditable request.",
        )
    return _apply_audit_only_action(
        session,
        row,
        payload,
        actor=actor,
        required_note=False,
        event_type="mobile.other_action.sync",
        message="Mobile action synced as an auditable server-validated request.",
    )


def _apply_review_decision(
    session: Session,
    row: MobileActionDraftORM,
    payload: dict[str, Any],
    *,
    actor: MobileActor,
) -> list[int]:
    target_type = row.target_type.lower()
    if target_type in {"analysis", "stored_analysis", "review"}:
        target_id = _target_int(row)
        analysis = session.get(AnalysisORM, target_id)
        if analysis is None:
            raise MobileSyncValidationError(["target_not_found: analysis"])
        decision = _normalized_decision(payload)
        if decision not in _ANALYSIS_DECISIONS:
            raise MobileSyncValidationError(["invalid_review_decision: expected approve, reject, override, or request_changes"])
        previous_status = analysis.review_status
        previous_label = analysis.final_label or analysis.label
        new_status = _ANALYSIS_DECISIONS[decision]
        analysis.review_status = new_status
        analysis.reviewed_at = utcnow()
        analysis.review_comment = _short_note(payload)
        if actor.user_id is not None:
            analysis.reviewer_user_id = actor.user_id
        analysis.final_label = _clean_optional(payload.get("final_label")) or previous_label
        if actor.user_id is not None:
            session.add(
                ReviewDecisionORM(
                    analysis_id=analysis.id,
                    reviewer_user_id=actor.user_id,
                    action="override" if decision == "override" else "approve" if new_status == "approved" else "reject" if new_status == "rejected" else "request_changes",
                    previous_status=previous_status,
                    new_status=new_status,
                    comment=analysis.review_comment,
                    previous_label=previous_label,
                    final_label=analysis.final_label,
                )
            )
        audit_id = _audit(
            session,
            actor=actor,
            event_type="mobile.review_decision.sync",
            message="Mobile review decision accepted after server-side validation.",
            entity_type="analysis",
            entity_id=analysis.id,
            metadata={
                "draft_id": row.id,
                "previous_status": previous_status,
                "new_status": new_status,
                "offline_final_before_sync": False,
            },
        )
        return [audit_id]
    if target_type in {"spectracheck_session", "spectracheck"}:
        target_id = _target_int(row)
        parent = session.get(SpectraCheckSessionORM, target_id)
        if parent is None:
            raise MobileSyncValidationError(["target_not_found: spectracheck_session"])
        decision = _normalized_decision(payload)
        if decision not in _SPECTRACHECK_DECISIONS:
            raise MobileSyncValidationError(["invalid_review_decision: expected approved_confirmed, rejected, needs_changes, or deferred"])
        review_status, session_status = _SPECTRACHECK_DECISIONS[decision]
        parent.status = session_status
        parent.updated_at = utcnow()
        session.add(
            SpectraCheckReviewDecisionORM(
                session_id=parent.id,
                status=review_status,
                reviewer_name=_actor_name(actor, row),
                reviewer_comment=_short_note(payload),
                metadata_json=_json_dump({"mobile_draft_id": row.id}),
            )
        )
        session.add(
            SpectraCheckAuditEventORM(
                session_id=parent.id,
                event_type="mobile.review_decision.sync",
                message="Mobile SpectraCheck review accepted after server-side validation.",
                actor_id=actor.user_id,
                metadata_json=_json_dump({"draft_id": row.id, "review_status": review_status}),
            )
        )
        audit_id = _audit(
            session,
            actor=actor,
            event_type="mobile.review_decision.sync",
            message="Mobile SpectraCheck review decision accepted after server-side validation.",
            entity_type="spectracheck_session",
            entity_id=parent.id,
            metadata={"draft_id": row.id, "review_status": review_status},
        )
        return [audit_id]
    if target_type in {"regulatory_dossier", "dossier"}:
        target_id = _target_int(row)
        dossier = session.get(RegulatoryDossierORM, target_id)
        if dossier is None:
            raise MobileSyncValidationError(["target_not_found: regulatory_dossier"])
        decision = _normalized_decision(payload)
        if decision not in {"approve", "approved", "needs_changes", "reject", "rejected", "defer", "deferred"}:
            raise MobileSyncValidationError(["invalid_review_decision: expected approve, reject, needs_changes, or defer"])
        if decision in {"approve", "approved"}:
            dossier.status = "approved"
        elif decision in {"reject", "rejected"}:
            dossier.status = "blocked"
        else:
            dossier.status = "in_review"
        dossier.updated_at = utcnow()
        session.add(
            RegulatoryReviewDecisionORM(
                dossier_id=dossier.id,
                reviewer_name=_actor_name(actor, row),
                decision="approve" if decision in {"approve", "approved"} else "reject" if decision in {"reject", "rejected"} else "defer" if decision in {"defer", "deferred"} else "needs_changes",
                rationale=_short_note(payload) or "Mobile review synced after server validation.",
                metadata_json=_json_dump({"mobile_draft_id": row.id}),
            )
        )
        audit_id = _audit(
            session,
            actor=actor,
            event_type="mobile.review_decision.sync",
            message="Mobile regulatory review decision accepted after server-side validation.",
            entity_type="regulatory_dossier",
            entity_id=dossier.id,
            metadata={"draft_id": row.id, "dossier_status": dossier.status},
        )
        return [audit_id]
    raise MobileSyncValidationError([f"unsupported_review_target: {row.target_type}"])


def _apply_regulatory_action_update(
    session: Session,
    row: MobileActionDraftORM,
    payload: dict[str, Any],
    *,
    actor: MobileActor,
) -> list[int]:
    status = _clean_optional(payload.get("status"))
    if status is None:
        raise MobileSyncValidationError(["missing_status: regulatory action update requires status"])
    target_type = row.target_type.lower()
    if target_type == "regulatory_action_item":
        if status not in _REGULATORY_ACTION_STATUSES:
            raise MobileSyncValidationError(["invalid_status: regulatory action status is not allowed"])
        target = session.get(RegulatoryActionItemORM, _target_int(row))
        if target is None:
            raise MobileSyncValidationError(["target_not_found: regulatory_action_item"])
        previous = target.status
        target.status = status
        target.updated_at = utcnow()
        audit_id = _audit(
            session,
            actor=actor,
            event_type="mobile.regulatory_action.sync",
            message="Mobile regulatory action update accepted after server-side validation.",
            entity_type="regulatory_action_item",
            entity_id=target.id,
            metadata={"draft_id": row.id, "previous_status": previous, "new_status": status},
        )
        return [audit_id]
    if target_type == "cross_module_action_item":
        if status not in _CROSS_MODULE_ACTION_STATUSES:
            raise MobileSyncValidationError(["invalid_status: cross-module action status is not allowed"])
        target = session.get(CrossModuleActionItemORM, _target_int(row))
        if target is None:
            raise MobileSyncValidationError(["target_not_found: cross_module_action_item"])
        previous = target.status
        target.status = status
        target.updated_at = utcnow()
        audit_id = _audit(
            session,
            actor=actor,
            event_type="mobile.regulatory_action.sync",
            message="Mobile cross-module action update accepted after server-side validation.",
            entity_type="cross_module_action_item",
            entity_id=target.id,
            metadata={"draft_id": row.id, "previous_status": previous, "new_status": status},
        )
        return [audit_id]
    raise MobileSyncValidationError([f"unsupported_regulatory_target: {row.target_type}"])


def _apply_reaction_execution_update(
    session: Session,
    row: MobileActionDraftORM,
    payload: dict[str, Any],
    *,
    actor: MobileActor,
) -> list[int]:
    if row.target_type.lower() != "reaction_execution_item":
        raise MobileSyncValidationError([f"unsupported_reaction_target: {row.target_type}"])
    status = _clean_optional(payload.get("status"))
    if status not in _REACTION_EXECUTION_STATUSES:
        raise MobileSyncValidationError(["invalid_status: reaction execution status is not allowed"])
    target = session.get(ReactionExecutionItemORM, _target_int(row))
    if target is None:
        raise MobileSyncValidationError(["target_not_found: reaction_execution_item"])
    previous = target.status
    target.status = status
    target.updated_at = utcnow()
    if status == "running" and target.started_at is None:
        target.started_at = utcnow()
    if status in {"completed", "failed", "skipped", "canceled"} and target.completed_at is None:
        target.completed_at = utcnow()
    if status == "failed" and payload.get("failure_reason"):
        target.failure_reason = str(payload.get("failure_reason"))[:20_000]
    event_type = "started" if status == "running" else status if status in {"completed", "failed", "skipped"} else "note"
    session.add(
        ReactionExecutionEventORM(
            execution_item_id=target.id,
            execution_batch_id=target.execution_batch_id,
            event_type=event_type,
            message=_short_note(payload) or f"Mobile execution status update: {status}",
            actor=_actor_name(actor, row),
            metadata_json=_json_dump({"mobile_draft_id": row.id, "previous_status": previous}),
        )
    )
    audit_id = _audit(
        session,
        actor=actor,
        event_type="mobile.reaction_execution.sync",
        message="Mobile reaction execution update accepted after server-side validation.",
        entity_type="reaction_execution_item",
        entity_id=target.id,
        metadata={"draft_id": row.id, "previous_status": previous, "new_status": status},
    )
    return [audit_id]


def _apply_report_review(
    session: Session,
    row: MobileActionDraftORM,
    payload: dict[str, Any],
    *,
    actor: MobileActor,
) -> list[int]:
    target_type = row.target_type.lower()
    target_id = _target_int(row)
    entity_type = target_type
    if target_type == "report":
        target = session.get(ReportORM, target_id)
        if target is None:
            raise MobileSyncValidationError(["target_not_found: report"])
        entity_type = "report"
    elif target_type == "spectracheck_report":
        target = session.get(SpectraCheckReportRecordORM, target_id)
        if target is None:
            raise MobileSyncValidationError(["target_not_found: spectracheck_report"])
        entity_type = "spectracheck_report"
    else:
        raise MobileSyncValidationError([f"unsupported_report_target: {row.target_type}"])
    return [
        _audit(
            session,
            actor=actor,
            event_type="mobile.report_review.sync",
            message="Mobile report review synced as an auditable review action.",
            entity_type=entity_type,
            entity_id=target_id,
            metadata={"draft_id": row.id, "comment": _short_note(payload)},
        )
    ]


def _apply_audit_only_action(
    session: Session,
    row: MobileActionDraftORM,
    payload: dict[str, Any],
    *,
    actor: MobileActor,
    required_note: bool,
    event_type: str,
    message: str,
) -> list[int]:
    if required_note and not _short_note(payload):
        raise MobileSyncValidationError(["missing_note: a short note or comment is required"])
    entity_type, entity_id = _validate_generic_target(session, row)
    return [
        _audit(
            session,
            actor=actor,
            event_type=event_type,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata={"draft_id": row.id, "comment": _short_note(payload)},
        )
    ]


def _validate_generic_target(session: Session, row: MobileActionDraftORM) -> tuple[str, int | None]:
    target_type = row.target_type.lower()
    target_id = _target_int(row, allow_non_numeric=True)
    model_map: dict[str, type[Any]] = {
        "analysis": AnalysisORM,
        "spectracheck_session": SpectraCheckSessionORM,
        "spectracheck_evidence": SpectraCheckEvidenceRecordORM,
        "regulatory_dossier": RegulatoryDossierORM,
        "reaction_project": ReactionProjectORM,
        "report": ReportORM,
        "cross_module_action_item": CrossModuleActionItemORM,
        "regulatory_action_item": RegulatoryActionItemORM,
        "reaction_execution_item": ReactionExecutionItemORM,
    }
    model = model_map.get(target_type)
    if model is None:
        return (row.target_type, target_id if isinstance(target_id, int) else None)
    if not isinstance(target_id, int):
        raise MobileSyncValidationError(["invalid_target_id: expected numeric target id"])
    if session.get(model, target_id) is None:
        raise MobileSyncValidationError([f"target_not_found: {target_type}"])
    return (target_type, target_id)


def _drafts_for_sync(
    session: Session,
    *,
    payload: MobileSyncRequest,
    actor: MobileActor,
) -> list[MobileActionDraftORM]:
    stmt = (
        select(MobileActionDraftORM)
        .where(MobileActionDraftORM.status.in_(["draft", "queued_for_sync"]))
        .order_by(MobileActionDraftORM.id.asc())
        .limit(200)
    )
    if payload.draft_ids:
        stmt = stmt.where(MobileActionDraftORM.id.in_(payload.draft_ids))
    elif payload.device_session_id is not None:
        stmt = stmt.where(MobileActionDraftORM.device_session_id == payload.device_session_id)
    elif actor.email is not None and not actor.system_api_key:
        stmt = stmt.where(MobileActionDraftORM.user_email == actor.email.lower())
    return list(session.scalars(stmt).all())


def _assert_safe_mobile_json(value: Any, *, path: str) -> None:
    try:
        encoded = _json_dump(value)
    except TypeError as exc:
        raise MobileExperienceError(f"{path}: payload must be JSON serializable.") from exc
    if len(encoded.encode("utf-8")) > _DRAFT_PAYLOAD_MAX_BYTES:
        raise MobileExperienceError(
            f"{path}: payload_too_large: mobile payloads must remain compact."
        )
    problems: list[str] = []
    _collect_mobile_safety_problems(value, path=path, problems=problems)
    if problems:
        raise MobileExperienceError("; ".join(problems))


def _collect_mobile_safety_problems(value: Any, *, path: str, problems: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if any(marker in key_lower for marker in _FORBIDDEN_KEY_MARKERS):
                problems.append(f"{path}.{key_text}: forbidden_mobile_payload_field")
                continue
            if key_lower in {"spectrum", "spectra"} and isinstance(item, (dict, list)):
                problems.append(f"{path}.{key_text}: raw_spectrum_like_payload_not_allowed")
                continue
            _collect_mobile_safety_problems(item, path=f"{path}.{key_text}", problems=problems)
        return
    if isinstance(value, list):
        if _looks_like_spectrum_points(value):
            problems.append(f"{path}: raw_spectrum_like_payload_not_allowed")
            return
        for index, item in enumerate(value[:250]):
            _collect_mobile_safety_problems(item, path=f"{path}[{index}]", problems=problems)
        if len(value) > 250:
            problems.append(f"{path}: mobile_array_too_large")
        return
    if isinstance(value, str):
        if len(value) > _STRING_VALUE_MAX_CHARS:
            problems.append(f"{path}: mobile_string_too_large")
        if any(marker in value for marker in _SECRET_VALUE_MARKERS):
            problems.append(f"{path}: secret_like_value_not_allowed")


def _looks_like_spectrum_points(value: list[Any]) -> bool:
    if len(value) < 20:
        return False
    sample = value[:20]
    dict_points = 0
    numeric_pairs = 0
    for item in sample:
        if isinstance(item, dict) and len(_SPECTRUM_POINT_KEYS.intersection({str(k).lower() for k in item})) >= 2:
            dict_points += 1
        if (
            isinstance(item, (list, tuple))
            and len(item) >= 2
            and isinstance(item[0], (int, float))
            and isinstance(item[1], (int, float))
        ):
            numeric_pairs += 1
    return dict_points >= 10 or numeric_pairs >= 10


def _spectracheck_summary(session: Session, scope: str, scope_id: str | None) -> dict[str, Any]:
    stmt = select(SpectraCheckSessionORM)
    scope_int = _optional_int(scope_id)
    if scope == "project" and scope_int is not None:
        stmt = stmt.where(SpectraCheckSessionORM.project_id == scope_int)
    elif scope == "sample" and scope_int is not None:
        stmt = stmt.where(SpectraCheckSessionORM.sample_pk == scope_int)
    elif scope == "session" and scope_int is not None:
        stmt = stmt.where(SpectraCheckSessionORM.id == scope_int)
    rows = session.scalars(
        stmt.order_by(SpectraCheckSessionORM.updated_at.desc()).limit(200)
    ).all()
    return {
        "program_key": "spectracheck",
        "display_order": 1,
        "session_count": len(rows),
        "review_required_count": sum(
            1 for row in rows if row.status in {"review_required", "evidence_ready"}
        ),
        "approved_count": sum(1 for row in rows if row.status == "approved"),
        "latest_sessions": [
            {
                "id": row.id,
                "title": row.title,
                "status": row.status,
                "sample_id": row.sample_id,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows[:5]
        ],
    }


def _regulatory_summary(session: Session, scope: str, scope_id: str | None) -> dict[str, Any]:
    dossier_stmt = select(RegulatoryDossierORM)
    action_stmt = select(RegulatoryActionItemORM)
    scope_int = _optional_int(scope_id)
    if scope == "project" and scope_int is not None:
        dossier_stmt = dossier_stmt.where(RegulatoryDossierORM.project_id == scope_int)
    elif scope == "session" and scope_int is not None:
        dossier_stmt = dossier_stmt.where(RegulatoryDossierORM.spectracheck_session_id == scope_int)
    elif scope == "dossier" and scope_int is not None:
        dossier_stmt = dossier_stmt.where(RegulatoryDossierORM.id == scope_int)
        action_stmt = action_stmt.where(RegulatoryActionItemORM.dossier_id == scope_int)
    elif scope == "reaction_project" and scope_int is not None:
        dossier_stmt = dossier_stmt.where(RegulatoryDossierORM.reaction_project_id == scope_int)
    elif scope == "compound" and scope_int is not None:
        action_stmt = action_stmt.where(RegulatoryActionItemORM.compound_id == scope_int)
    elif scope == "batch" and scope_int is not None:
        action_stmt = action_stmt.where(RegulatoryActionItemORM.batch_id == scope_int)
    dossiers = session.scalars(
        dossier_stmt.order_by(RegulatoryDossierORM.updated_at.desc()).limit(200)
    ).all()
    actions = session.scalars(action_stmt.limit(500)).all()
    return {
        "program_key": "regulatory_hub",
        "display_order": 2,
        "dossier_count": len(dossiers),
        "open_action_count": sum(1 for row in actions if row.status in {"open", "in_progress"}),
        "blocked_dossier_count": sum(1 for row in dossiers if row.status == "blocked"),
        "latest_dossiers": [
            {
                "id": row.id,
                "title": row.title,
                "status": row.status,
                "product_name": row.product_name,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in dossiers[:5]
        ],
    }


def _reaction_summary(session: Session, scope: str, scope_id: str | None) -> dict[str, Any]:
    project_stmt = select(ReactionProjectORM)
    item_stmt = select(ReactionExecutionItemORM)
    scope_int = _optional_int(scope_id)
    if scope in {"reaction_project", "project"} and scope_int is not None:
        project_stmt = project_stmt.where(ReactionProjectORM.id == scope_int)
        item_stmt = item_stmt.where(ReactionExecutionItemORM.reaction_project_id == scope_int)
    projects = session.scalars(
        project_stmt.order_by(ReactionProjectORM.updated_at.desc()).limit(200)
    ).all()
    items = session.scalars(item_stmt.limit(500)).all()
    return {
        "program_key": "reaction_optimization",
        "display_order": 3,
        "reaction_project_count": len(projects),
        "running_execution_count": sum(1 for row in items if row.status == "running"),
        "failed_execution_count": sum(1 for row in items if row.status == "failed"),
        "completed_execution_count": sum(1 for row in items if row.status == "completed"),
        "latest_projects": [
            {
                "id": row.id,
                "name": row.name,
                "status": row.status,
                "objective": row.objective,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in projects[:5]
        ],
    }


def _action_summary(session: Session, scope: str, scope_id: str | None) -> dict[str, Any]:
    return {
        "open_cross_module_action_count": _count(
            session,
            select(func.count())
            .select_from(CrossModuleActionItemORM)
            .where(CrossModuleActionItemORM.status.in_(["open", "in_progress", "blocked"])),
        ),
        "queued_mobile_draft_count": _count(
            session,
            select(func.count())
            .select_from(MobileActionDraftORM)
            .where(MobileActionDraftORM.status == "queued_for_sync"),
        ),
        "rejected_mobile_draft_count": _count(
            session,
            select(func.count())
            .select_from(MobileActionDraftORM)
            .where(MobileActionDraftORM.status == "rejected"),
        ),
        "unread_notification_count": _count(
            session,
            select(func.count())
            .select_from(MobileNotificationORM)
            .where(MobileNotificationORM.status == "unread"),
        ),
        "review_required_job_count": _count(
            session,
            select(func.count()).select_from(JobORM).where(JobORM.review_required.is_(True)),
        ),
        "scope": scope,
        "scope_id": scope_id,
    }


def _stored_report_preview_sections(
    report_json: dict[str, Any],
    analysis: AnalysisORM | None,
) -> list[dict[str, Any]]:
    analysis_json = report_json.get("analysis") if isinstance(report_json.get("analysis"), dict) else {}
    structure_json = report_json.get("structure") if isinstance(report_json.get("structure"), dict) else {}
    sections = [
        {
            "section": "summary",
            "analysis_id": analysis.id if analysis is not None else analysis_json.get("id"),
            "sample_id": analysis.sample_id if analysis is not None else analysis_json.get("sample_id"),
            "label": analysis.label if analysis is not None else analysis_json.get("label"),
            "review_status": analysis.review_status if analysis is not None else analysis_json.get("review_status"),
            "confidence": analysis.confidence if analysis is not None else analysis_json.get("confidence"),
        },
        {
            "section": "structure_summary",
            "formula": structure_json.get("formula"),
            "molecular_weight": structure_json.get("molecular_weight"),
            "total_hydrogens": structure_json.get("total_hydrogens"),
        },
        {
            "section": "review",
            "review_decision_count": len(report_json.get("review_decisions") or []),
            "audit_event_count": len(report_json.get("audit_events") or []),
            "confidence_notes": [_truncate(str(item), 240) for item in (report_json.get("confidence_notes") or [])[:5]],
        },
    ]
    return sections


def _omitted_report_sections(report_json: dict[str, Any]) -> list[str]:
    omitted: list[str] = ["raw_appendices", "raw_fid", "raw_spectra", "full_source_text"]
    for key in (
        "parsed_nmr_text",
        "parsed_peaks",
        "spectrum_derived_matched_peaks",
        "unmatched_peaks",
        "nmr2d_evidence",
    ):
        if key in report_json:
            omitted.append(key)
    return omitted


def _get_or_create_preference(
    session: Session,
    *,
    user_email: str | None,
    device_session_id: int | None,
) -> MobileViewPreferenceORM:
    normalized_email = user_email.lower() if user_email else None
    stmt = select(MobileViewPreferenceORM)
    if device_session_id is not None:
        _require_device_session(session, device_session_id)
        stmt = stmt.where(MobileViewPreferenceORM.device_session_id == device_session_id)
    elif normalized_email is not None:
        stmt = stmt.where(MobileViewPreferenceORM.user_email == normalized_email)
    else:
        stmt = stmt.where(MobileViewPreferenceORM.user_email.is_(None)).where(
            MobileViewPreferenceORM.device_session_id.is_(None)
        )
    row = session.scalar(stmt.order_by(MobileViewPreferenceORM.id.desc()).limit(1))
    if row is not None:
        return row
    row = MobileViewPreferenceORM(
        user_email=normalized_email,
        device_session_id=device_session_id,
        preferred_home="dashboard",
        compact_mode=True,
        bottom_nav_enabled=True,
        reduce_motion=False,
        high_contrast=False,
        metadata_json="{}",
    )
    session.add(row)
    session.flush()
    return row


def _config_response(pref: MobileViewPreferenceORM) -> MobileConfigResponse:
    preference = _view_preference_to_record(pref)
    return MobileConfigResponse(
        navigation_order=_navigation_order(),
        preferred_home=preference.preferred_home,
        view_preference=preference,
        offline_enabled=True,
        draft_sync_required=True,
        safety_rules=list(MOBILE_SAFETY_RULES),
    )


def _navigation_order() -> list[MobileNavigationItem]:
    return [
        MobileNavigationItem(
            program_key=program_key,  # type: ignore[arg-type]
            display_name=_PROGRAM_LABELS[program_key],
            display_order=index,
            route=_PROGRAM_ROUTES[program_key],
        )
        for index, program_key in enumerate(DEFAULT_MOBILE_PROGRAM_ORDER, start=1)
    ]


def _sanitize_push_subscription(
    subscription_json: dict[str, Any],
    *,
    endpoint_hash: str,
) -> dict[str, Any]:
    keys = subscription_json.get("keys") if isinstance(subscription_json.get("keys"), dict) else {}
    return {
        "endpoint_hash": endpoint_hash,
        "has_endpoint": True,
        "has_keys": bool(keys),
        "key_fields_present": sorted(str(key) for key in keys),
        "content_encoding": subscription_json.get("contentEncoding")
        or subscription_json.get("content_encoding"),
    }


def _device_session_to_record(row: MobileDeviceSessionORM) -> MobileDeviceSession:
    return MobileDeviceSession(
        id=row.id,
        user_email=row.user_email,
        device_label=row.device_label,
        device_type=row.device_type,  # type: ignore[arg-type]
        platform=row.platform,
        browser=row.browser,
        last_seen_at=row.last_seen_at,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _view_preference_to_record(row: MobileViewPreferenceORM) -> MobileViewPreference:
    return MobileViewPreference(
        id=row.id,
        user_email=row.user_email,
        device_session_id=row.device_session_id,
        preferred_home=row.preferred_home,  # type: ignore[arg-type]
        compact_mode=row.compact_mode,
        bottom_nav_enabled=row.bottom_nav_enabled,
        reduce_motion=row.reduce_motion,
        high_contrast=row.high_contrast,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _draft_to_record(row: MobileActionDraftORM) -> MobileActionDraft:
    return MobileActionDraft(
        id=row.id,
        user_email=row.user_email,
        device_session_id=row.device_session_id,
        action_type=row.action_type,  # type: ignore[arg-type]
        target_type=row.target_type,
        target_id=row.target_id,
        draft_payload_json=_json_dict(row.draft_payload_json),
        status=row.status,  # type: ignore[arg-type]
        validation_warnings_json=[str(item) for item in _json_list(row.validation_warnings_json)],
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _sync_result_to_record(row: MobileSyncResultORM) -> MobileSyncResult:
    return MobileSyncResult(
        id=row.id,
        device_session_id=row.device_session_id,
        synced_count=row.synced_count,
        rejected_count=row.rejected_count,
        warnings_json=[str(item) for item in _json_list(row.warnings_json)],
        notes_json=[str(item) for item in _json_list(row.notes_json)],
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _push_subscription_to_record(row: MobilePushSubscriptionORM) -> MobilePushSubscription:
    return MobilePushSubscription(
        id=row.id,
        user_email=row.user_email,
        endpoint_hash=row.endpoint_hash,
        subscription_json=_json_dict(row.subscription_json),
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _notification_to_record(row: MobileNotificationORM) -> MobileNotification:
    return MobileNotification(
        id=row.id,
        user_email=row.user_email,
        notification_type=row.notification_type,  # type: ignore[arg-type]
        title=row.title,
        message=row.message,
        target_type=row.target_type,
        target_id=row.target_id,
        severity=row.severity,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _compact_summary_to_record(row: CompactModuleSummaryORM) -> CompactModuleSummary:
    return CompactModuleSummary(
        id=row.id,
        scope=row.scope,  # type: ignore[arg-type]
        scope_id=row.scope_id,
        spectracheck_summary_json=_json_dict(row.spectracheck_summary_json),
        regulatory_summary_json=_json_dict(row.regulatory_summary_json),
        reaction_summary_json=_json_dict(row.reaction_summary_json),
        action_summary_json=_json_dict(row.action_summary_json),
        generated_at=row.generated_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _audit(
    session: Session,
    *,
    actor: MobileActor,
    event_type: str,
    message: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    row = AuditEventORM(
        event_type=event_type,
        message=message,
        actor_user_id=actor.user_id,
        actor_email=actor.email,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=_json_dump(metadata or {}),
    )
    session.add(row)
    session.flush()
    return int(row.id)


def _assert_session_visible(row: MobileDeviceSessionORM, *, actor: MobileActor) -> None:
    if actor.system_api_key or actor.email is None:
        return
    if row.user_email != actor.email.lower():
        raise MobileExperienceNotFoundError("Mobile device session not found.")


def _assert_draft_visible(row: MobileActionDraftORM, *, actor: MobileActor) -> None:
    if actor.system_api_key or actor.email is None:
        return
    if row.user_email != actor.email.lower():
        raise MobileSyncValidationError(["draft_not_visible_for_actor"])


def _require_device_session(session: Session, device_session_id: int) -> MobileDeviceSessionORM:
    row = session.get(MobileDeviceSessionORM, device_session_id)
    if row is None:
        raise MobileExperienceNotFoundError("Mobile device session not found.")
    return row


def _target_int(row: MobileActionDraftORM, *, allow_non_numeric: bool = False) -> int | str:
    try:
        return int(row.target_id)
    except (TypeError, ValueError) as exc:
        if allow_non_numeric:
            return row.target_id
        raise MobileSyncValidationError(["invalid_target_id: expected numeric target id"]) from exc


def _email_for_payload(value: Any, actor: MobileActor) -> str | None:
    if value is not None:
        return str(value).strip().lower() or None
    return actor.email.lower() if actor.email else None


def _actor_name(actor: MobileActor, row: MobileActionDraftORM) -> str | None:
    return actor.email or row.user_email or "mobile-api-key"


def _normalized_decision(payload: dict[str, Any]) -> str:
    value = payload.get("decision") or payload.get("action") or payload.get("status")
    return str(value or "").strip().lower()


def _short_note(payload: dict[str, Any]) -> str | None:
    for key in ("comment", "note", "notes", "message", "rationale"):
        value = payload.get(key)
        if value is not None:
            return _truncate(str(value).strip(), 4000) or None
    return None


def _mobile_severity(value: str | None) -> str:
    if value in {"info", "warning", "high", "critical"}:
        return value
    if value in {"error", "failed", "blocked"}:
        return "high"
    return "warning" if value else "info"


def _module_for_target(target_type: str | None) -> str | None:
    if target_type is None:
        return None
    lowered = target_type.lower()
    if "spectra" in lowered or "analysis" in lowered or "evidence" in lowered:
        return "spectracheck"
    if "regulatory" in lowered or "dossier" in lowered:
        return "regulatory_hub"
    if "reaction" in lowered:
        return "reaction_optimization"
    return None


def _public_json(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            if any(marker in key_lower for marker in _FORBIDDEN_KEY_MARKERS):
                continue
            output[key_text] = _public_json(item)
        return output
    if isinstance(value, list):
        return [_public_json(item) for item in value[:20]]
    if isinstance(value, str):
        return _truncate(value, 500)
    return value


def _status_counts(rows: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(getattr(row, "status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _count(session: Session, stmt: Any) -> int:
    return int(session.scalar(stmt) or 0)


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"


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
