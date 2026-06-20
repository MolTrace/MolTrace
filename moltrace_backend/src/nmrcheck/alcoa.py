"""ALCOA+ data-integrity primitives (Security Prompt 12).

Reusable, side-effect-free helpers that make a regulated mutation **Attributable** (who + *why*),
**reversible-by-record** (soft-delete instead of a physical delete), and that document which tables
are immutable-by-design. Kept standalone (no DB session ownership, no FastAPI imports) so the
enforcement primitive is unit-testable and future regulated mutations can opt in without threading
state through the parallel-session-contended store/route files.

P10 (server-timestamped, hash-chained audit) and P11 (record-bound e-signatures) already cover the
**Contemporaneous** attribute and signing attribution; this module fills the remaining ALCOA+ gaps:
the *why* (reason-for-change as a first-class value) and reversible-by-record soft deletion.

Grounded framing: these are controls that *support* ALCOA+ / 21 CFR Part 11 — retention schedules,
SOPs, and validation remain the customer's responsibility.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

# Tables whose rows must NEVER be deleted — not even soft-deleted — because they ARE the integrity
# trail. The guarantee is the *absence* of any deletion path, so it is enforced by a regression test
# (no DELETE route, no session.delete) rather than runtime code.
REGULATED_IMMUTABLE_TABLES: frozenset[str] = frozenset(
    {"audit_events", "audit_checkpoints", "audit_chain_head"}
)

MAX_REASON_LEN = 2000


class ReasonForChangeRequired(ValueError):
    """Raised when a regulated mutation is attempted without a non-empty reason-for-change."""


class _SoftDeletable(Protocol):
    deleted_at: datetime | None
    deleted_by: str | None
    reason_for_change: str | None


def require_reason_for_change(reason: str | None) -> str:
    """Validate + normalize a reason-for-change for a regulated mutation (ALCOA+ Attributable).

    Strips surrounding whitespace and rejects a blank reason — defense-in-depth, so that even if
    a request model later loosens its ``min_length=1`` the store still records a real reason.
    Rejects (never silently truncates) an over-long reason so the audit record stays legible.
    """
    text = (reason or "").strip()
    if not text:
        raise ReasonForChangeRequired("A reason for this regulated change is required.")
    if len(text) > MAX_REASON_LEN:
        raise ReasonForChangeRequired(
            f"Reason for change is too long (max {MAX_REASON_LEN} characters)."
        )
    return text


def apply_soft_delete(
    row: _SoftDeletable,
    *,
    reason: str | None,
    actor: str | None,
    now: datetime,
) -> None:
    """Mark a regulated row as soft-deleted in one place (ALCOA+ Enduring / reversible-by-record).

    Sets ``deleted_at`` (server timestamp), ``deleted_by`` (the authenticated principal supplied by
    the caller — never client-asserted), and ``reason_for_change`` (validated). Never calls
    ``session.delete``: the row is retained in full so the deletion is reversible-by-record and the
    record endures for inspection."""
    row.reason_for_change = require_reason_for_change(reason)
    row.deleted_at = now
    row.deleted_by = actor


def is_soft_deleted(row: object) -> bool:
    """True if the row carries a soft-delete timestamp (used to exclude it from default reads)."""
    return getattr(row, "deleted_at", None) is not None
