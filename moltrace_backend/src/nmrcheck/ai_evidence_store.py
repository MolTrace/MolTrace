from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    AIEvidenceItem,
    AIEvidenceModule,
    AIEvidenceReviewRequest,
    AIEvidenceReviewResponse,
    AIEvidenceStatus,
    sanitize_optional_plain_text,
)
from .orm import AIEvidenceItemORM, AuditEventORM, utcnow


class AIEvidenceError(ValueError):
    pass


class AIEvidenceNotFoundError(AIEvidenceError):
    pass


@dataclass(frozen=True)
class AIEvidenceActor:
    user_id: int
    email: str | None = None


_SECRET_MARKERS = ("api_key", "apikey", "token", "password", "secret", "database_url")
_PROMPT_MARKERS = (
    "chain-of-thought",
    "chain_of_thought",
    "raw prompt",
    "system prompt",
    "developer prompt",
)


def list_evidence_queue(
    session_factory: sessionmaker[Session],
    *,
    module: AIEvidenceModule | None = None,
    status: AIEvidenceStatus | None = None,
    tenant_id: int | None = None,
    limit: int = 100,
) -> list[AIEvidenceItem]:
    with session_scope(session_factory) as session:
        stmt = select(AIEvidenceItemORM).order_by(
            AIEvidenceItemORM.updated_at.desc(), AIEvidenceItemORM.id.desc()
        )
        if module is not None:
            stmt = stmt.where(AIEvidenceItemORM.module == module)
        if status is not None:
            stmt = stmt.where(AIEvidenceItemORM.status == status)
        if tenant_id is not None:
            stmt = stmt.where(AIEvidenceItemORM.tenant_id == tenant_id)
        return [_to_record(row) for row in session.scalars(stmt.limit(limit)).all()]


def review_evidence_item(
    session_factory: sessionmaker[Session],
    evidence_id: int,
    payload: AIEvidenceReviewRequest,
    *,
    actor: AIEvidenceActor,
    correlation_id: str | None = None,
    tenant_id: int | None = None,
) -> AIEvidenceReviewResponse:
    if evidence_id < 1:
        raise AIEvidenceNotFoundError("AI evidence item not found.")
    with session_scope(session_factory) as session:
        row = session.get(AIEvidenceItemORM, evidence_id)
        if row is None or (tenant_id is not None and row.tenant_id != tenant_id):
            raise AIEvidenceNotFoundError("AI evidence item not found.")
        previous_state = _review_state(row)
        reviewed_at = utcnow()
        comment = _safe_public_text(sanitize_optional_plain_text(payload.review_comment))
        row.status = payload.status
        row.reviewer_id = actor.user_id
        row.reviewed_at = reviewed_at
        row.review_comment = comment
        row.updated_at = reviewed_at
        after_state = _review_state(row)
        action = _action_for_status(payload.status)
        audit = AuditEventORM(
            event_type=f"ai_evidence.review.{action}",
            message=f"AI evidence item review status set to {payload.status}.",
            actor_user_id=actor.user_id,
            actor_email=actor.email,
            entity_type="ai_evidence_item",
            entity_id=row.id,
            metadata_json=_json_dump(
                {
                    "tenant_id": row.tenant_id,
                    "action": action,
                    "module": row.module,
                    "before_state": previous_state,
                    "after_state": after_state,
                    "reason": comment,
                    "correlation_id": correlation_id,
                    "decision_support_only": True,
                    "raw_prompt_exposed": False,
                    "chain_of_thought_exposed": False,
                }
            ),
        )
        session.add(audit)
        session.flush()
        session.refresh(row)
        return AIEvidenceReviewResponse(
            evidence_item=_to_record(row),
            audit_event_id=int(audit.id),
            updated_status=payload.status,
            reviewed_at=reviewed_at,
            reviewer_id=actor.user_id,
            reviewer_display_name=actor.email,
        )


def _to_record(row: AIEvidenceItemORM) -> AIEvidenceItem:
    return AIEvidenceItem(
        id=row.id,
        module=row.module,  # type: ignore[arg-type]
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        status=row.status,  # type: ignore[arg-type]
        confidence_score=row.confidence_score,
        risk_level=row.risk_level,  # type: ignore[arg-type]
        summary=_safe_public_text(row.summary) or "",
        reviewer_id=row.reviewer_id,
        reviewed_at=row.reviewed_at,
        review_comment=_safe_public_text(row.review_comment),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _review_state(row: AIEvidenceItemORM) -> dict[str, Any]:
    return {
        "status": row.status,
        "reviewer_id": row.reviewer_id,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "review_comment_present": bool(row.review_comment),
    }


def _action_for_status(status: str) -> str:
    if status == "approved":
        return "approve"
    if status == "rejected":
        return "reject"
    return "set_pending_review"


def _safe_public_text(value: str | None) -> str | None:
    text = sanitize_optional_plain_text(value)
    if text is None:
        return None
    safe_lines: list[str] = []
    for line in text.splitlines():
        lower = line.lower()
        if any(marker in lower for marker in _PROMPT_MARKERS):
            safe_lines.append("[redacted internal AI prompt or reasoning]")
            continue
        if "prompt" in lower and (":" in line or "=" in line):
            safe_lines.append("[redacted internal AI prompt or reasoning]")
            continue
        safe_lines.append(_redact_secret_assignments(line))
    return "\n".join(safe_lines).strip() or None


def _redact_secret_assignments(line: str) -> str:
    lower = line.lower()
    if not any(marker in lower for marker in _SECRET_MARKERS):
        return line
    for separator in (":", "="):
        if separator not in line:
            continue
        key, _value = line.split(separator, 1)
        if any(marker in key.lower() for marker in _SECRET_MARKERS):
            return f"{key.strip()}{separator} [redacted]"
    return "[redacted sensitive value]"


def _json_dump(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
