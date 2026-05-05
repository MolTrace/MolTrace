from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    ApprovalRecord,
    ApprovalRecordCreate,
    CollaborationRole,
    EvidenceCommentCreate,
    EvidenceCommentRecord,
    EvidenceCommentUpdate,
    OrganizationCreate,
    OrganizationRecord,
    ProjectPermissionCreate,
    ProjectPermissionRecord,
    ProjectPermissionUpdate,
    ReportLock,
    ReportLockRequest,
    ReportReleaseRequest,
    ReviewTaskCreate,
    ReviewTaskRecord,
    ReviewTaskUpdate,
    SecureShareLinkCreate,
    SecureShareLinkRecord,
    SessionReviewerCreate,
    SessionReviewerRecord,
    SessionReviewerUpdate,
    TeamMemberCreate,
    TeamMemberRecord,
    TeamMemberUpdate,
)
from .orm import (
    ApprovalRecordORM,
    AuditEventORM,
    EvidenceCommentORM,
    OrganizationORM,
    ProjectPermissionORM,
    ReportLockORM,
    ReviewTaskORM,
    SecureShareLinkORM,
    SessionReviewerORM,
    SpectraCheckAuditEventORM,
    SpectraCheckEvidenceRecordORM,
    SpectraCheckProjectORM,
    SpectraCheckReportRecordORM,
    SpectraCheckSessionORM,
    TeamMemberORM,
    utcnow,
)


class CollaborationError(ValueError):
    pass


class CollaborationPermissionError(PermissionError):
    pass


Action = Literal["view", "comment", "review", "approve", "upload_run", "manage", "release", "share"]

_ROLE_ACTIONS: dict[CollaborationRole, set[Action]] = {
    "owner": {"view", "comment", "review", "approve", "upload_run", "manage", "release", "share"},
    "admin": {"view", "comment", "review", "approve", "upload_run", "manage", "release", "share"},
    "scientist": {"view", "comment", "upload_run"},
    "reviewer": {"view", "comment", "review", "approve"},
    "viewer": {"view"},
}
_ROLE_RANK: dict[str, int] = {
    "viewer": 10,
    "reviewer": 20,
    "scientist": 30,
    "admin": 40,
    "owner": 50,
}
_REVIEW_NOTE = (
    "Human-review records capture reviewer decisions and workflow state; they do not by "
    "themselves establish chemical identity."
)


@dataclass(frozen=True)
class CollaborationActor:
    user_id: int | None = None
    email: str | None = None
    is_admin: bool = False
    is_system: bool = False
    permissive: bool = False

    @property
    def normalized_email(self) -> str | None:
        return _normalize_email(self.email)

    @property
    def bypasses_rbac(self) -> bool:
        return bool(self.permissive or self.is_system or self.is_admin)


def can_project_action(
    session_factory: sessionmaker[Session],
    project_id: int,
    actor: CollaborationActor,
    action: Action,
) -> bool:
    with session_scope(session_factory) as session:
        role = _resolve_project_role(session, project_id, actor)
        return _role_allows(role, action)


def can_session_action(
    session_factory: sessionmaker[Session],
    session_id: int,
    actor: CollaborationActor,
    action: Action,
) -> bool:
    with session_scope(session_factory) as session:
        role = _resolve_session_role(session, session_id, actor)
        return _role_allows(role, action)


def create_organization(
    session_factory: sessionmaker[Session],
    payload: OrganizationCreate,
    *,
    actor: CollaborationActor,
) -> OrganizationRecord:
    with session_scope(session_factory) as session:
        existing = session.scalar(
            select(OrganizationORM).where(OrganizationORM.name == payload.name)
        )
        if existing is not None:
            raise CollaborationError("An organization with that name already exists.")
        row = OrganizationORM(name=payload.name, metadata_json=_json_dump(payload.metadata_json))
        session.add(row)
        session.flush()
        if actor.normalized_email:
            session.add(
                TeamMemberORM(
                    organization_id=row.id,
                    user_email=actor.normalized_email,
                    display_name=None,
                    role="owner",
                    status="active",
                    metadata_json=_json_dump({"created_with_organization": True}),
                )
            )
        _audit(
            session,
            event_type="collaboration.organization.create",
            message="Organization created.",
            actor=actor,
            entity_type="organization",
            entity_id=row.id,
            metadata={"name": row.name},
        )
        session.refresh(row)
        return _organization_to_record(row)


def list_organizations(
    session_factory: sessionmaker[Session],
    *,
    actor: CollaborationActor,
    limit: int = 200,
) -> list[OrganizationRecord]:
    with session_scope(session_factory) as session:
        stmt = select(OrganizationORM).order_by(OrganizationORM.id.desc()).limit(limit)
        if not actor.bypasses_rbac:
            email = actor.normalized_email
            if not email:
                return []
            stmt = (
                stmt.join(TeamMemberORM, TeamMemberORM.organization_id == OrganizationORM.id)
                .where(TeamMemberORM.user_email == email)
                .where(TeamMemberORM.status == "active")
            )
        return [_organization_to_record(row) for row in session.scalars(stmt).all()]


def get_organization(
    session_factory: sessionmaker[Session],
    organization_id: int,
    *,
    actor: CollaborationActor,
) -> OrganizationRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(OrganizationORM, organization_id)
        if row is None:
            return None
        _require_organization_role(
            session,
            organization_id,
            actor,
            allowed={"owner", "admin", "scientist", "reviewer", "viewer"},
        )
        return _organization_to_record(row)


def add_team_member(
    session_factory: sessionmaker[Session],
    organization_id: int,
    payload: TeamMemberCreate,
    *,
    actor: CollaborationActor,
) -> TeamMemberRecord:
    with session_scope(session_factory) as session:
        _require_organization_role(session, organization_id, actor, allowed={"owner", "admin"})
        email = _normalize_email(payload.user_email)
        if email is None:
            raise CollaborationError("user_email is required.")
        row = session.scalar(
            select(TeamMemberORM)
            .where(TeamMemberORM.organization_id == organization_id)
            .where(TeamMemberORM.user_email == email)
        )
        if row is None:
            row = TeamMemberORM(
                organization_id=organization_id,
                user_email=email,
                display_name=payload.display_name,
                role=payload.role,
                status=payload.status,
                metadata_json=_json_dump(payload.metadata_json),
            )
            session.add(row)
            event_type = "collaboration.team_member.create"
        else:
            row.display_name = payload.display_name
            row.role = payload.role
            row.status = payload.status
            row.metadata_json = _json_dump(payload.metadata_json)
            row.updated_at = utcnow()
            event_type = "collaboration.team_member.update"
        session.flush()
        _audit(
            session,
            event_type=event_type,
            message="Organization team member saved.",
            actor=actor,
            entity_type="team_member",
            entity_id=row.id,
            metadata={
                "organization_id": organization_id,
                "user_email": email,
                "role": payload.role,
            },
        )
        session.refresh(row)
        return _team_member_to_record(row)


def list_team_members(
    session_factory: sessionmaker[Session],
    organization_id: int,
    *,
    actor: CollaborationActor,
    limit: int = 500,
) -> list[TeamMemberRecord]:
    with session_scope(session_factory) as session:
        _require_organization_role(session, organization_id, actor, allowed={"owner", "admin"})
        rows = session.scalars(
            select(TeamMemberORM)
            .where(TeamMemberORM.organization_id == organization_id)
            .order_by(TeamMemberORM.id.asc())
            .limit(limit)
        ).all()
        return [_team_member_to_record(row) for row in rows]


def update_team_member(
    session_factory: sessionmaker[Session],
    organization_id: int,
    member_id: int,
    payload: TeamMemberUpdate,
    *,
    actor: CollaborationActor,
) -> TeamMemberRecord | None:
    with session_scope(session_factory) as session:
        _require_organization_role(session, organization_id, actor, allowed={"owner", "admin"})
        row = session.get(TeamMemberORM, member_id)
        if row is None or row.organization_id != organization_id:
            return None
        if "display_name" in payload.model_fields_set:
            row.display_name = payload.display_name
        if payload.role is not None:
            row.role = payload.role
        if payload.status is not None:
            row.status = payload.status
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.updated_at = utcnow()
        _audit(
            session,
            event_type="collaboration.team_member.update",
            message="Organization team member updated.",
            actor=actor,
            entity_type="team_member",
            entity_id=row.id,
            metadata={
                "organization_id": organization_id,
                "updated_fields": sorted(payload.model_fields_set),
            },
        )
        return _team_member_to_record(row)


def add_project_permission(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: ProjectPermissionCreate,
    *,
    actor: CollaborationActor,
) -> ProjectPermissionRecord:
    with session_scope(session_factory) as session:
        _require_project_action(session, project_id, actor, "manage")
        email = _normalize_email(payload.user_email)
        if email is None:
            raise CollaborationError("user_email is required.")
        row = session.scalar(
            select(ProjectPermissionORM)
            .where(ProjectPermissionORM.project_id == project_id)
            .where(ProjectPermissionORM.user_email == email)
        )
        if row is None:
            row = ProjectPermissionORM(
                project_id=project_id,
                user_email=email,
                role=payload.role,
                metadata_json=_json_dump(payload.metadata_json),
            )
            session.add(row)
            event_type = "collaboration.project_permission.create"
        else:
            row.role = payload.role
            row.metadata_json = _json_dump(payload.metadata_json)
            row.updated_at = utcnow()
            event_type = "collaboration.project_permission.update"
        session.flush()
        _audit(
            session,
            event_type=event_type,
            message="Project permission saved.",
            actor=actor,
            entity_type="project_permission",
            entity_id=row.id,
            metadata={"project_id": project_id, "user_email": email, "role": payload.role},
        )
        session.refresh(row)
        return _project_permission_to_record(row)


def list_project_permissions(
    session_factory: sessionmaker[Session],
    project_id: int,
    *,
    actor: CollaborationActor,
    limit: int = 500,
) -> list[ProjectPermissionRecord]:
    with session_scope(session_factory) as session:
        _require_project_action(session, project_id, actor, "manage")
        rows = session.scalars(
            select(ProjectPermissionORM)
            .where(ProjectPermissionORM.project_id == project_id)
            .order_by(ProjectPermissionORM.id.asc())
            .limit(limit)
        ).all()
        return [_project_permission_to_record(row) for row in rows]


def update_project_permission(
    session_factory: sessionmaker[Session],
    project_id: int,
    permission_id: int,
    payload: ProjectPermissionUpdate,
    *,
    actor: CollaborationActor,
) -> ProjectPermissionRecord | None:
    with session_scope(session_factory) as session:
        _require_project_action(session, project_id, actor, "manage")
        row = session.get(ProjectPermissionORM, permission_id)
        if row is None or row.project_id != project_id:
            return None
        if payload.role is not None:
            row.role = payload.role
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.updated_at = utcnow()
        _audit(
            session,
            event_type="collaboration.project_permission.update",
            message="Project permission updated.",
            actor=actor,
            entity_type="project_permission",
            entity_id=row.id,
            metadata={"project_id": project_id, "updated_fields": sorted(payload.model_fields_set)},
        )
        return _project_permission_to_record(row)


def delete_project_permission(
    session_factory: sessionmaker[Session],
    project_id: int,
    permission_id: int,
    *,
    actor: CollaborationActor,
) -> ProjectPermissionRecord | None:
    with session_scope(session_factory) as session:
        _require_project_action(session, project_id, actor, "manage")
        row = session.get(ProjectPermissionORM, permission_id)
        if row is None or row.project_id != project_id:
            return None
        record = _project_permission_to_record(row)
        session.delete(row)
        _audit(
            session,
            event_type="collaboration.project_permission.delete",
            message="Project permission deleted.",
            actor=actor,
            entity_type="project_permission",
            entity_id=record.id,
            metadata={"project_id": project_id, "user_email": record.user_email},
        )
        return record


def add_session_reviewer(
    session_factory: sessionmaker[Session],
    session_id: int,
    payload: SessionReviewerCreate,
    *,
    actor: CollaborationActor,
) -> SessionReviewerRecord:
    with session_scope(session_factory) as session:
        parent = _require_session_action(session, session_id, actor, "manage")
        email = _normalize_email(payload.reviewer_email)
        if email is None:
            raise CollaborationError("reviewer_email is required.")
        row = session.scalar(
            select(SessionReviewerORM)
            .where(SessionReviewerORM.session_id == session_id)
            .where(SessionReviewerORM.reviewer_email == email)
        )
        if row is None:
            row = SessionReviewerORM(
                session_id=session_id,
                reviewer_email=email,
                assigned_by=payload.assigned_by or actor.normalized_email,
                status=payload.status,
                metadata_json=_json_dump(payload.metadata_json),
            )
            session.add(row)
            event_type = "collaboration.session_reviewer.create"
        else:
            row.assigned_by = payload.assigned_by or row.assigned_by or actor.normalized_email
            row.status = payload.status
            row.metadata_json = _json_dump(payload.metadata_json)
            row.updated_at = utcnow()
            event_type = "collaboration.session_reviewer.update"
        session.flush()
        _audit(
            session,
            event_type=event_type,
            message="Session reviewer assignment saved.",
            actor=actor,
            entity_type="session_reviewer",
            entity_id=row.id,
            session_id=session_id,
            metadata={
                "project_id": parent.project_id,
                "reviewer_email": email,
                "status": payload.status,
            },
        )
        session.refresh(row)
        return _session_reviewer_to_record(row)


def list_session_reviewers(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    actor: CollaborationActor,
    limit: int = 500,
) -> list[SessionReviewerRecord]:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "view")
        rows = session.scalars(
            select(SessionReviewerORM)
            .where(SessionReviewerORM.session_id == session_id)
            .order_by(SessionReviewerORM.id.asc())
            .limit(limit)
        ).all()
        return [_session_reviewer_to_record(row) for row in rows]


def update_session_reviewer(
    session_factory: sessionmaker[Session],
    session_id: int,
    reviewer_id: int,
    payload: SessionReviewerUpdate,
    *,
    actor: CollaborationActor,
) -> SessionReviewerRecord | None:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "manage")
        row = session.get(SessionReviewerORM, reviewer_id)
        if row is None or row.session_id != session_id:
            return None
        if payload.status is not None:
            row.status = payload.status
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.updated_at = utcnow()
        _audit(
            session,
            event_type="collaboration.session_reviewer.update",
            message="Session reviewer assignment updated.",
            actor=actor,
            entity_type="session_reviewer",
            entity_id=row.id,
            session_id=session_id,
            metadata={"updated_fields": sorted(payload.model_fields_set)},
        )
        return _session_reviewer_to_record(row)


def remove_session_reviewer(
    session_factory: sessionmaker[Session],
    session_id: int,
    reviewer_id: int,
    *,
    actor: CollaborationActor,
) -> SessionReviewerRecord | None:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "manage")
        row = session.get(SessionReviewerORM, reviewer_id)
        if row is None or row.session_id != session_id:
            return None
        row.status = "removed"
        row.updated_at = utcnow()
        _audit(
            session,
            event_type="collaboration.session_reviewer.remove",
            message="Session reviewer assignment removed.",
            actor=actor,
            entity_type="session_reviewer",
            entity_id=row.id,
            session_id=session_id,
            metadata={"reviewer_email": row.reviewer_email},
        )
        return _session_reviewer_to_record(row)


def create_comment(
    session_factory: sessionmaker[Session],
    session_id: int,
    payload: EvidenceCommentCreate,
    *,
    actor: CollaborationActor,
) -> EvidenceCommentRecord:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "comment")
        _verify_optional_evidence(session, session_id, payload.evidence_id)
        row = EvidenceCommentORM(
            session_id=session_id,
            evidence_id=payload.evidence_id,
            artifact_id=payload.artifact_id,
            author_email=payload.author_email or actor.normalized_email,
            comment=payload.comment,
            comment_type=payload.comment_type,
            resolved=False,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            event_type="collaboration.comment.create",
            message="Evidence comment created.",
            actor=actor,
            entity_type="evidence_comment",
            entity_id=row.id,
            session_id=session_id,
            metadata={"comment_type": payload.comment_type, "evidence_id": payload.evidence_id},
        )
        session.refresh(row)
        return _comment_to_record(row)


def list_comments(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    actor: CollaborationActor,
    limit: int = 500,
) -> list[EvidenceCommentRecord]:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "view")
        rows = session.scalars(
            select(EvidenceCommentORM)
            .where(EvidenceCommentORM.session_id == session_id)
            .order_by(EvidenceCommentORM.created_at.asc(), EvidenceCommentORM.id.asc())
            .limit(limit)
        ).all()
        return [_comment_to_record(row) for row in rows]


def update_comment(
    session_factory: sessionmaker[Session],
    session_id: int,
    comment_id: int,
    payload: EvidenceCommentUpdate,
    *,
    actor: CollaborationActor,
) -> EvidenceCommentRecord | None:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "comment")
        row = session.get(EvidenceCommentORM, comment_id)
        if row is None or row.session_id != session_id:
            return None
        if payload.comment is not None:
            row.comment = payload.comment
        if payload.comment_type is not None:
            row.comment_type = payload.comment_type
        if payload.resolved is not None:
            row.resolved = payload.resolved
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.updated_at = utcnow()
        _audit(
            session,
            event_type="collaboration.comment.update",
            message="Evidence comment updated.",
            actor=actor,
            entity_type="evidence_comment",
            entity_id=row.id,
            session_id=session_id,
            metadata={"updated_fields": sorted(payload.model_fields_set), "resolved": row.resolved},
        )
        return _comment_to_record(row)


def delete_comment(
    session_factory: sessionmaker[Session],
    session_id: int,
    comment_id: int,
    *,
    actor: CollaborationActor,
) -> EvidenceCommentRecord | None:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "comment")
        row = session.get(EvidenceCommentORM, comment_id)
        if row is None or row.session_id != session_id:
            return None
        record = _comment_to_record(row)
        session.delete(row)
        _audit(
            session,
            event_type="collaboration.comment.delete",
            message="Evidence comment deleted.",
            actor=actor,
            entity_type="evidence_comment",
            entity_id=comment_id,
            session_id=session_id,
            metadata={"comment_type": record.comment_type},
        )
        return record


def create_review_task(
    session_factory: sessionmaker[Session],
    session_id: int,
    payload: ReviewTaskCreate,
    *,
    actor: CollaborationActor,
) -> ReviewTaskRecord:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "review")
        row = ReviewTaskORM(
            session_id=session_id,
            title=payload.title,
            description=payload.description,
            assigned_to=payload.assigned_to,
            status=payload.status,
            priority=payload.priority,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            event_type="collaboration.review_task.create",
            message="Review task created.",
            actor=actor,
            entity_type="review_task",
            entity_id=row.id,
            session_id=session_id,
            metadata={"status": payload.status, "priority": payload.priority},
        )
        session.refresh(row)
        return _review_task_to_record(row)


def list_review_tasks(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    actor: CollaborationActor,
    limit: int = 500,
) -> list[ReviewTaskRecord]:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "view")
        rows = session.scalars(
            select(ReviewTaskORM)
            .where(ReviewTaskORM.session_id == session_id)
            .order_by(ReviewTaskORM.created_at.asc(), ReviewTaskORM.id.asc())
            .limit(limit)
        ).all()
        return [_review_task_to_record(row) for row in rows]


def update_review_task(
    session_factory: sessionmaker[Session],
    session_id: int,
    task_id: int,
    payload: ReviewTaskUpdate,
    *,
    actor: CollaborationActor,
) -> ReviewTaskRecord | None:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "review")
        row = session.get(ReviewTaskORM, task_id)
        if row is None or row.session_id != session_id:
            return None
        for field in ("title", "description", "assigned_to", "status", "priority"):
            value = getattr(payload, field)
            if value is not None or field in payload.model_fields_set:
                setattr(row, field, value)
        if payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json)
        row.updated_at = utcnow()
        _audit(
            session,
            event_type="collaboration.review_task.update",
            message="Review task updated.",
            actor=actor,
            entity_type="review_task",
            entity_id=row.id,
            session_id=session_id,
            metadata={"updated_fields": sorted(payload.model_fields_set), "status": row.status},
        )
        return _review_task_to_record(row)


def create_approval(
    session_factory: sessionmaker[Session],
    session_id: int,
    payload: ApprovalRecordCreate,
    *,
    actor: CollaborationActor,
) -> ApprovalRecord:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "approve")
        _verify_optional_evidence(session, session_id, payload.evidence_id)
        if payload.report_id is not None:
            _require_report_for_session(session, payload.report_id, session_id)
        row = ApprovalRecordORM(
            session_id=session_id,
            evidence_id=payload.evidence_id,
            report_id=payload.report_id,
            approver_email=payload.approver_email or actor.normalized_email,
            decision=payload.decision,
            rationale=payload.rationale,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            event_type="collaboration.approval.create",
            message="Human-review approval decision saved.",
            actor=actor,
            entity_type="approval_record",
            entity_id=row.id,
            session_id=session_id,
            metadata={"decision": payload.decision, "report_id": payload.report_id},
        )
        session.refresh(row)
        return _approval_to_record(row)


def list_approvals(
    session_factory: sessionmaker[Session],
    session_id: int,
    *,
    actor: CollaborationActor,
    limit: int = 500,
) -> list[ApprovalRecord]:
    with session_scope(session_factory) as session:
        _require_session_action(session, session_id, actor, "view")
        rows = session.scalars(
            select(ApprovalRecordORM)
            .where(ApprovalRecordORM.session_id == session_id)
            .order_by(ApprovalRecordORM.created_at.desc(), ApprovalRecordORM.id.desc())
            .limit(limit)
        ).all()
        return [_approval_to_record(row) for row in rows]


def lock_report(
    session_factory: sessionmaker[Session],
    report_id: int,
    payload: ReportLockRequest | None,
    *,
    actor: CollaborationActor,
) -> ReportLock:
    payload = payload or ReportLockRequest()
    with session_scope(session_factory) as session:
        report = _get_report_or_raise(session, report_id)
        session_id = payload.session_id or report.session_id
        if session_id != report.session_id:
            raise CollaborationError("Report does not belong to the supplied session_id.")
        _require_session_action(session, session_id, actor, "review")
        row = _latest_lock(session, report_id)
        if row is None:
            row = ReportLockORM(
                report_id=report_id,
                session_id=session_id,
                locked_by=payload.locked_by or actor.normalized_email,
                lock_reason=payload.lock_reason,
                status="locked",
                metadata_json=_json_dump(payload.metadata_json),
            )
            session.add(row)
        else:
            row.session_id = session_id
            row.locked_by = payload.locked_by or actor.normalized_email
            row.lock_reason = payload.lock_reason
            row.status = "locked"
            row.metadata_json = _json_dump(payload.metadata_json)
            row.updated_at = utcnow()
        report.status = "locked_for_review"
        session.flush()
        _audit(
            session,
            event_type="collaboration.report.lock",
            message="Report locked for human review.",
            actor=actor,
            entity_type="report_lock",
            entity_id=row.id,
            session_id=session_id,
            metadata={"report_id": report_id},
        )
        session.refresh(row)
        return _report_lock_to_record(row)


def unlock_report(
    session_factory: sessionmaker[Session],
    report_id: int,
    payload: ReportLockRequest | None,
    *,
    actor: CollaborationActor,
) -> ReportLock:
    payload = payload or ReportLockRequest()
    with session_scope(session_factory) as session:
        report = _get_report_or_raise(session, report_id)
        session_id = payload.session_id or report.session_id
        _require_session_action(session, session_id, actor, "review")
        row = _latest_lock(session, report_id)
        if row is None:
            row = ReportLockORM(
                report_id=report_id,
                session_id=session_id,
                locked_by=payload.locked_by or actor.normalized_email,
                lock_reason=payload.lock_reason,
                status="unlocked",
                metadata_json=_json_dump(payload.metadata_json),
            )
            session.add(row)
        else:
            row.status = "unlocked"
            row.locked_by = payload.locked_by or actor.normalized_email or row.locked_by
            row.lock_reason = payload.lock_reason or row.lock_reason
            if payload.metadata_json:
                row.metadata_json = _json_dump(payload.metadata_json)
            row.updated_at = utcnow()
        report.status = "draft_requires_review"
        session.flush()
        _audit(
            session,
            event_type="collaboration.report.unlock",
            message="Report lock released back to editable review state.",
            actor=actor,
            entity_type="report_lock",
            entity_id=row.id,
            session_id=session_id,
            metadata={"report_id": report_id},
        )
        return _report_lock_to_record(row)


def release_report(
    session_factory: sessionmaker[Session],
    report_id: int,
    payload: ReportReleaseRequest | None,
    *,
    actor: CollaborationActor,
) -> ReportLock:
    payload = payload or ReportReleaseRequest()
    with session_scope(session_factory) as session:
        report = _get_report_or_raise(session, report_id)
        _require_session_action(session, report.session_id, actor, "release")
        has_confirmed = _has_confirmed_approval(session, report.session_id, report_id)
        if not has_confirmed:
            if not payload.override_approval_requirement:
                raise CollaborationError(
                    "Report release requires an approved_confirmed approval record."
                )
            if not payload.rationale:
                raise CollaborationError("Override release requires rationale.")
        row = _latest_lock(session, report_id)
        metadata = dict(payload.metadata_json or {})
        metadata.update(
            {
                "approval_confirmed": has_confirmed,
                "approval_requirement_overridden": bool(payload.override_approval_requirement),
                "override_rationale": payload.rationale,
            }
        )
        if row is None:
            row = ReportLockORM(
                report_id=report_id,
                session_id=report.session_id,
                locked_by=actor.normalized_email,
                lock_reason=payload.rationale,
                status="released",
                metadata_json=_json_dump(metadata),
            )
            session.add(row)
        else:
            row.status = "released"
            row.locked_by = actor.normalized_email or row.locked_by
            row.lock_reason = payload.rationale or row.lock_reason
            row.metadata_json = _json_dump(metadata)
            row.updated_at = utcnow()
        report.status = "released"
        session.flush()
        _audit(
            session,
            event_type="collaboration.report.release",
            message="Report released after required human-review gate.",
            actor=actor,
            entity_type="report_lock",
            entity_id=row.id,
            session_id=report.session_id,
            metadata={"report_id": report_id, **metadata},
        )
        return _report_lock_to_record(row)


def get_report_lock(
    session_factory: sessionmaker[Session],
    report_id: int,
    *,
    actor: CollaborationActor,
) -> ReportLock | None:
    with session_scope(session_factory) as session:
        report = _get_report_or_raise(session, report_id)
        _require_session_action(session, report.session_id, actor, "view")
        row = _latest_lock(session, report_id)
        return _report_lock_to_record(row) if row is not None else None


def create_share_link(
    session_factory: sessionmaker[Session],
    payload: SecureShareLinkCreate,
    *,
    actor: CollaborationActor,
) -> SecureShareLinkRecord:
    with session_scope(session_factory) as session:
        project_id, session_id, report_id = _resolve_share_targets(session, payload)
        if project_id is None:
            raise CollaborationError("Share target must resolve to a project.")
        _require_project_action(session, project_id, actor, "share")
        token = secrets.token_urlsafe(32)
        row = SecureShareLinkORM(
            project_id=project_id,
            session_id=session_id,
            report_id=report_id,
            token_hash=_hash_share_token(token),
            permission=payload.permission,
            expires_at=payload.expires_at,
            revoked=False,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            event_type="collaboration.share_link.create",
            message="Secure share link created.",
            actor=actor,
            entity_type="secure_share_link",
            entity_id=row.id,
            session_id=session_id,
            metadata={
                "project_id": project_id,
                "report_id": report_id,
                "permission": payload.permission,
            },
        )
        session.refresh(row)
        return _share_link_to_record(row, token=token)


def get_share_link(
    session_factory: sessionmaker[Session],
    token: str,
) -> SecureShareLinkRecord | None:
    with session_scope(session_factory) as session:
        row = session.scalar(
            select(SecureShareLinkORM).where(
                SecureShareLinkORM.token_hash == _hash_share_token(token)
            )
        )
        if row is None or row.revoked or _is_expired(row.expires_at):
            return None
        return _share_link_to_record(row)


def revoke_share_link(
    session_factory: sessionmaker[Session],
    share_id: int,
    *,
    actor: CollaborationActor,
) -> SecureShareLinkRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(SecureShareLinkORM, share_id)
        if row is None:
            return None
        project_id = row.project_id
        if project_id is None and row.session_id is not None:
            parent = session.get(SpectraCheckSessionORM, row.session_id)
            project_id = parent.project_id if parent is not None else None
        if project_id is None:
            raise CollaborationError("Share link target no longer resolves to a project.")
        _require_project_action(session, project_id, actor, "share")
        row.revoked = True
        _audit(
            session,
            event_type="collaboration.share_link.revoke",
            message="Secure share link revoked.",
            actor=actor,
            entity_type="secure_share_link",
            entity_id=row.id,
            session_id=row.session_id,
            metadata={"project_id": project_id, "report_id": row.report_id},
        )
        return _share_link_to_record(row)


def _organization_to_record(row: OrganizationORM) -> OrganizationRecord:
    return OrganizationRecord(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Organization records control collaboration scope and do not alter evidence data."],
    )


def _team_member_to_record(row: TeamMemberORM) -> TeamMemberRecord:
    return TeamMemberRecord(
        id=row.id,
        organization_id=row.organization_id,
        user_email=row.user_email,
        display_name=row.display_name,
        role=row.role,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Team membership grants collaboration permissions only within configured scopes."],
    )


def _project_permission_to_record(row: ProjectPermissionORM) -> ProjectPermissionRecord:
    return ProjectPermissionRecord(
        id=row.id,
        project_id=row.project_id,
        user_email=row.user_email,
        role=row.role,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Project permissions control access to review workflow records for this project."],
    )


def _session_reviewer_to_record(row: SessionReviewerORM) -> SessionReviewerRecord:
    return SessionReviewerRecord(
        id=row.id,
        session_id=row.session_id,
        reviewer_email=row.reviewer_email,
        assigned_by=row.assigned_by,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Reviewer assignments enable human review actions but do not modify raw evidence."],
    )


def _comment_to_record(row: EvidenceCommentORM) -> EvidenceCommentRecord:
    return EvidenceCommentRecord(
        id=row.id,
        session_id=row.session_id,
        evidence_id=row.evidence_id,
        artifact_id=row.artifact_id,
        author_email=row.author_email,
        comment=row.comment,
        comment_type=row.comment_type,  # type: ignore[arg-type]
        resolved=row.resolved,
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Comments annotate review workflow state and do not mutate underlying evidence."],
    )


def _review_task_to_record(row: ReviewTaskORM) -> ReviewTaskRecord:
    return ReviewTaskRecord(
        id=row.id,
        session_id=row.session_id,
        title=row.title,
        description=row.description,
        assigned_to=row.assigned_to,
        status=row.status,  # type: ignore[arg-type]
        priority=row.priority,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=["Review tasks coordinate human review and do not alter scientific evidence."],
    )


def _approval_to_record(row: ApprovalRecordORM) -> ApprovalRecord:
    return ApprovalRecord(
        id=row.id,
        session_id=row.session_id,
        evidence_id=row.evidence_id,
        report_id=row.report_id,
        approver_email=row.approver_email,
        decision=row.decision,  # type: ignore[arg-type]
        rationale=row.rationale,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[_REVIEW_NOTE],
    )


def _report_lock_to_record(row: ReportLockORM) -> ReportLock:
    return ReportLock(
        id=row.id,
        report_id=row.report_id,
        session_id=row.session_id,
        locked_by=row.locked_by,
        lock_reason=row.lock_reason,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        notes=[
            "Report locks guard review workflow state and leave report evidence payloads unchanged."
        ],
    )


def _share_link_to_record(
    row: SecureShareLinkORM,
    *,
    token: str | None = None,
) -> SecureShareLinkRecord:
    warnings: list[str] = []
    if row.revoked:
        warnings.append("This share link has been revoked.")
    elif _is_expired(row.expires_at):
        warnings.append("This share link has expired.")
    return SecureShareLinkRecord(
        id=row.id,
        project_id=row.project_id,
        session_id=row.session_id,
        report_id=row.report_id,
        token_hash=row.token_hash,
        permission=row.permission,  # type: ignore[arg-type]
        expires_at=row.expires_at,
        revoked=row.revoked,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        token=token,
        warnings=warnings,
        notes=["Share links grant scoped collaboration access metadata, not raw file bytes."],
    )


def _require_organization_role(
    session: Session,
    organization_id: int,
    actor: CollaborationActor,
    *,
    allowed: set[CollaborationRole],
) -> str:
    row = session.get(OrganizationORM, organization_id)
    if row is None:
        raise KeyError(f"Organization {organization_id} not found.")
    if actor.bypasses_rbac:
        return "owner"
    email = actor.normalized_email
    if not email:
        raise CollaborationPermissionError("A user email is required for organization access.")
    member = session.scalar(
        select(TeamMemberORM)
        .where(TeamMemberORM.organization_id == organization_id)
        .where(TeamMemberORM.user_email == email)
        .where(TeamMemberORM.status == "active")
    )
    if member is None or member.role not in allowed:
        raise CollaborationPermissionError("Insufficient organization role.")
    return member.role


def _require_project_action(
    session: Session,
    project_id: int,
    actor: CollaborationActor,
    action: Action,
) -> SpectraCheckProjectORM:
    project = session.get(SpectraCheckProjectORM, project_id)
    if project is None:
        raise KeyError(f"Project {project_id} not found.")
    role = _resolve_project_role(session, project_id, actor)
    if not _role_allows(role, action):
        raise CollaborationPermissionError(
            f"Project role '{role or 'none'}' cannot perform {action}."
        )
    return project


def _require_session_action(
    session: Session,
    session_id: int,
    actor: CollaborationActor,
    action: Action,
) -> SpectraCheckSessionORM:
    parent = session.get(SpectraCheckSessionORM, session_id)
    if parent is None:
        raise KeyError(f"Session {session_id} not found.")
    role = _resolve_session_role(session, session_id, actor)
    if not _role_allows(role, action):
        raise CollaborationPermissionError(
            f"Session role '{role or 'none'}' cannot perform {action}."
        )
    return parent


def _resolve_session_role(
    session: Session,
    session_id: int,
    actor: CollaborationActor,
) -> str | None:
    parent = session.get(SpectraCheckSessionORM, session_id)
    if parent is None:
        raise KeyError(f"Session {session_id} not found.")
    role = _resolve_project_role(session, parent.project_id, actor)
    email = actor.normalized_email
    if email:
        reviewer = session.scalar(
            select(SessionReviewerORM)
            .where(SessionReviewerORM.session_id == session_id)
            .where(SessionReviewerORM.reviewer_email == email)
            .where(SessionReviewerORM.status != "removed")
        )
        if reviewer is not None:
            role = _max_role(role, "reviewer")
    return role


def _resolve_project_role(
    session: Session,
    project_id: int,
    actor: CollaborationActor,
) -> str | None:
    project = session.get(SpectraCheckProjectORM, project_id)
    if project is None:
        raise KeyError(f"Project {project_id} not found.")
    if actor.bypasses_rbac:
        return "owner"
    role: str | None = None
    if actor.user_id is not None and project.owner_id == actor.user_id:
        role = "owner"
    email = actor.normalized_email
    if email:
        permission = session.scalar(
            select(ProjectPermissionORM)
            .where(ProjectPermissionORM.project_id == project_id)
            .where(ProjectPermissionORM.user_email == email)
        )
        if permission is not None:
            role = _max_role(role, permission.role)
    return role


def _role_allows(role: str | None, action: Action) -> bool:
    if role is None:
        return False
    return action in _ROLE_ACTIONS.get(role, set())  # type: ignore[arg-type]


def _max_role(current: str | None, candidate: str | None) -> str | None:
    if candidate is None:
        return current
    if current is None:
        return candidate
    return candidate if _ROLE_RANK.get(candidate, 0) > _ROLE_RANK.get(current, 0) else current


def _verify_optional_evidence(session: Session, session_id: int, evidence_id: int | None) -> None:
    if evidence_id is None:
        return
    row = session.get(SpectraCheckEvidenceRecordORM, evidence_id)
    if row is None or row.session_id != session_id:
        raise KeyError(f"Evidence {evidence_id} not found for session {session_id}.")


def _require_report_for_session(
    session: Session,
    report_id: int,
    session_id: int,
) -> SpectraCheckReportRecordORM:
    row = session.get(SpectraCheckReportRecordORM, report_id)
    if row is None or row.session_id != session_id:
        raise KeyError(f"Report {report_id} not found for session {session_id}.")
    return row


def _get_report_or_raise(session: Session, report_id: int) -> SpectraCheckReportRecordORM:
    row = session.get(SpectraCheckReportRecordORM, report_id)
    if row is None:
        raise KeyError(f"Report {report_id} not found.")
    return row


def _latest_lock(session: Session, report_id: int) -> ReportLockORM | None:
    return session.scalar(
        select(ReportLockORM)
        .where(ReportLockORM.report_id == report_id)
        .order_by(ReportLockORM.id.desc())
        .limit(1)
    )


def _has_confirmed_approval(session: Session, session_id: int, report_id: int) -> bool:
    row = session.scalar(
        select(ApprovalRecordORM)
        .where(ApprovalRecordORM.session_id == session_id)
        .where(ApprovalRecordORM.decision == "approved_confirmed")
        .where((ApprovalRecordORM.report_id == report_id) | (ApprovalRecordORM.report_id.is_(None)))
        .limit(1)
    )
    return row is not None


def _resolve_share_targets(
    session: Session,
    payload: SecureShareLinkCreate,
) -> tuple[int | None, int | None, int | None]:
    project_id = payload.project_id
    session_id = payload.session_id
    report_id = payload.report_id
    if report_id is not None:
        report = session.get(SpectraCheckReportRecordORM, report_id)
        if report is None:
            raise KeyError(f"Report {report_id} not found.")
        session_id = session_id or report.session_id
    if session_id is not None:
        parent = session.get(SpectraCheckSessionORM, session_id)
        if parent is None:
            raise KeyError(f"Session {session_id} not found.")
        project_id = project_id or parent.project_id
    if project_id is not None and session.get(SpectraCheckProjectORM, project_id) is None:
        raise KeyError(f"Project {project_id} not found.")
    return project_id, session_id, report_id


def _audit(
    session: Session,
    *,
    event_type: str,
    message: str,
    actor: CollaborationActor,
    entity_type: str | None,
    entity_id: int | None,
    metadata: dict[str, Any] | None = None,
    session_id: int | None = None,
) -> None:
    payload = dict(metadata or {})
    if session_id is not None:
        payload["session_id"] = session_id
    session.add(
        AuditEventORM(
            event_type=event_type,
            message=message,
            actor_user_id=actor.user_id,
            actor_email=actor.normalized_email,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=_json_dump(payload),
        )
    )
    if session_id is not None:
        session.add(
            SpectraCheckAuditEventORM(
                session_id=session_id,
                event_type=event_type,
                message=message,
                actor_id=actor.user_id,
                metadata_json=_json_dump(payload),
            )
        )


def _json_dump(value: Any) -> str:
    return json.dumps({} if value is None else value, sort_keys=True, separators=(",", ":"))


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _hash_share_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    value = expires_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)
