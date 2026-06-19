"""Tamper-evident audit hash chain (Security Prompt 10).

Every ``audit_events`` row is linked into a SHA-256 hash chain — ``entry_hash`` covers a canonical
serialization of the row's fields **and** the previous row's ``entry_hash``, so any insert, edit,
delete, or reorder breaks recomputation. Because audit rows are written from ~244 sites (222 via
``database.audit_event`` plus ~22 direct ``AuditEventORM(...)`` constructions across the stores),
the chain is assigned by a single SQLAlchemy ``before_flush`` listener — installed once per
session factory — so every current and future writer is covered with no per-site change.

Per-row hashing is keyless (fast, hot path). The keyed **HMAC seal** is applied to the periodic
*anchor* (see ``operations_store.create_audit_anchor`` / ``AuditCheckpointORM``), so rewriting
history wholesale also requires forging every overlapping anchor's HMAC — which needs the
``AUDIT_SIGNING_KEY``. Verification (``operations_store.verify_audit_chain``) re-walks the chain
and re-checks anchors.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import event, select, text

from .orm import AuditChainHeadORM, AuditEventORM

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

# Prefixed genesis (matches the DB-persisted "sha256:"+64 convention used elsewhere).
GENESIS_HASH = "sha256:" + "0" * 64
# Fixed key for the Postgres transaction-scoped advisory lock that serializes chain appends.
_AUDIT_CHAIN_LOCK_KEY = 0x4D544143  # "MTAC"
# Dev fallback signing key — production MUST set AUDIT_SIGNING_KEY (see settings).
_DEV_FALLBACK = "moltrace-dev-audit-signing-key-not-for-prod"


# --------------------------------------------------------------------------- canonical hashing


def _iso_utc(dt: datetime | None) -> str | None:
    """UTC-ISO with explicit None handling. SQLite stores naive (assume UTC); Postgres tz-aware —
    normalize so the same logical event hashes identically across backends."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _canonical_payload(row: AuditEventORM, *, chain_ts: datetime) -> dict[str, object]:
    """The exact fields covered by ``entry_hash``, in a reproducible form. Hashes the RAW
    ``metadata_json`` string (not a re-projected dict) to avoid projection drift, and includes
    ``prev_hash`` so the link is part of the hash."""
    return {
        "chain_seq": row.chain_seq,
        "chain_ts": _iso_utc(chain_ts),
        "created_at": _iso_utc(row.created_at),
        "event_type": row.event_type,
        "message": row.message,
        "actor_user_id": row.actor_user_id,
        "actor_email": row.actor_email,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "metadata_json": row.metadata_json,
        "prev_hash": row.prev_hash,
    }


def _canon(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def compute_entry_hash(row: AuditEventORM, *, chain_ts: datetime) -> str:
    digest = hashlib.sha256(_canon(_canonical_payload(row, chain_ts=chain_ts))).hexdigest()
    return "sha256:" + digest


# --------------------------------------------------------------------------- anchor signing


def _signing_material(key_material: str | None) -> bytes:
    return (key_material or _DEV_FALLBACK).encode("utf-8")


def key_id(key_material: str | None) -> str:
    """Non-secret fingerprint of the signing key (rotation visibility; mirrors the kms key_id
    idiom). Never reveals the key."""
    return "a" + hashlib.sha256(b"mtaudit1:" + _signing_material(key_material)).hexdigest()[:12]


def anchor_payload(
    *, from_seq: int, tip_seq: int, tip_hash: str, row_count: int, anchored_at: datetime
) -> dict[str, object]:
    """The canonical payload an anchor's HMAC signs (built identically at sign + verify time)."""
    return {
        "from_seq": from_seq,
        "tip_seq": tip_seq,
        "tip_hash": tip_hash,
        "row_count": row_count,
        "anchored_at": _iso_utc(anchored_at),
    }


def sign_anchor(payload: dict[str, object], key_material: str | None) -> str:
    """HMAC-SHA256 seal over the canonical anchor payload."""
    mac = hmac.new(_signing_material(key_material), _canon(payload), hashlib.sha256)
    return "hmac-sha256:" + mac.hexdigest()


def sign_head(max_seq: int, tip_hash: str, key_material: str | None) -> str:
    """HMAC-SHA256 seal over the chain high-water mark (max_seq + tip_hash)."""
    payload = {"max_seq": max_seq, "tip_hash": tip_hash}
    mac = hmac.new(_signing_material(key_material), _canon(payload), hashlib.sha256)
    return "hmac-sha256:" + mac.hexdigest()


# --------------------------------------------------------------------------- chain append (hook)


def _locked_tail(session: Session) -> tuple[int, str]:
    """Return (last chain_seq, last entry_hash), serializing concurrent appends. On Postgres a
    transaction-scoped advisory lock (auto-released at commit) serializes only audit-chain
    flushes; SQLite is single-writer so the in-transaction read-then-write is already serial."""
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_CHAIN_LOCK_KEY}
        )
    row = session.execute(
        select(AuditEventORM.chain_seq, AuditEventORM.entry_hash)
        .where(AuditEventORM.chain_seq.is_not(None))
        .order_by(AuditEventORM.chain_seq.desc())
        .limit(1)
    ).first()
    if row is None:
        return 0, GENESIS_HASH
    return int(row[0]), str(row[1])


def _update_chain_head(
    session: Session, *, max_seq: int, tip_hash: str, key_material: str | None
) -> None:
    """Upsert the signed singleton high-water mark so tail-truncation is detectable."""
    head = session.get(AuditChainHeadORM, 1)
    signature = sign_head(max_seq, tip_hash, key_material)
    kid = key_id(key_material)
    now = datetime.now(UTC)
    if head is None:
        session.add(
            AuditChainHeadORM(
                id=1, max_seq=max_seq, tip_hash=tip_hash,
                signature=signature, key_id=kid, updated_at=now,
            )
        )
    else:
        head.max_seq = max_seq
        head.tip_hash = tip_hash
        head.signature = signature
        head.key_id = kid
        head.updated_at = now


def install_audit_chain(
    session_factory: sessionmaker[Session], *, signing_key: str | None = None
) -> None:
    """Register the before_flush chain-assignment listener once per session factory. Idempotent:
    a second install on the same factory is a no-op (avoids double-chaining). ``signing_key`` keys
    the high-water-mark HMAC; pass ``settings.audit_signing_key`` so write + verify agree."""
    if getattr(session_factory, "_audit_chain_installed", False):
        return
    session_factory._audit_chain_installed = True  # type: ignore[attr-defined]

    @event.listens_for(session_factory, "before_flush")
    def _chain_new_audit_rows(session: Session, flush_context: object, instances: object) -> None:
        pending = [
            obj
            for obj in session.new
            if isinstance(obj, AuditEventORM) and obj.chain_seq is None
        ]
        if not pending:
            return
        chain_ts = datetime.now(UTC)
        seq, prev = _locked_tail(session)
        for row in pending:
            # created_at's Python default (utcnow) is applied DURING flush, i.e. after this
            # listener — so it is still None here. Populate it now (preserving any explicit
            # value) so the field is both hashed and reproducible at verify time.
            if row.created_at is None:
                row.created_at = chain_ts
            seq += 1
            row.chain_seq = seq
            row.chain_ts = chain_ts
            row.prev_hash = prev
            row.entry_hash = compute_entry_hash(row, chain_ts=chain_ts)
            prev = row.entry_hash
        # Advance the signed high-water mark to the new tip (under the same lock held above), so
        # deleting the most-recent (unanchored) rows is detectable: the live MAX(chain_seq) would
        # fall below this signed max_seq, which an attacker cannot lower without the key.
        _update_chain_head(session, max_seq=seq, tip_hash=prev, key_material=signing_key)
