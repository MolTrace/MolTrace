"""Session & token hardening: rotating refresh tokens + families (Security Prompt 4).

Every login mints a short-ish-lived opaque ACCESS bearer (the existing ``session_tokens`` row,
unchanged contract) plus a long-lived, single-use, ROTATING REFRESH token, grouped into a
``session_families`` lineage. ``POST /auth/refresh`` spends the refresh and mints a fresh pair;
presenting an already-spent/revoked refresh is **reuse** and revokes the whole family (OWASP/RFC
9700). Idle + absolute timeouts bound the family; revocation is **immediate** (DB-checked on the hot
``get_user_by_token`` path via the family-revoked predicate). Tokens are stored only as sha256
digests. Legacy (pre-0020, ``family_id IS NULL``) access rows are untouched by all of this.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from .database import audit_event, session_scope
from .orm import RefreshTokenORM, SessionFamilyORM, SessionTokenORM, utcnow
from .security import create_access_token, token_digest
from .settings import Settings

_MFA_CARRY_FIELDS = ("amr", "mfa_at", "stepped_up_at", "step_up_factor", "step_up_aal")


class SessionError(Exception):
    """Refresh/session failure rendered as ``{status} {detail}``; detail is a stable machine code
    (token_invalid | token_expired | token_reuse_detected)."""

    def __init__(self, detail: str, status: int = 401) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


class MintedSession(NamedTuple):
    access_token: str
    expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def fingerprint_hash(raw: str | None) -> str | None:
    """sha256 of a COARSE, STABLE device signal (UA family + client/install id) — never IP."""
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _refresh_expiry(settings: Settings, now: datetime, absolute_cap: datetime) -> datetime:
    """A refresh never outlives the family's absolute cap, and slides only up to the idle window."""
    idle = now + timedelta(minutes=settings.refresh_token_idle_minutes)
    return min(idle, _aware(absolute_cap))


# --------------------------------------------------------------------------- mint


def mint_session(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    user_id: int,
    amr: str | None = None,
    device_fingerprint: str | None = None,
) -> MintedSession:
    """Create a new family + access bearer + first refresh token. The access bearer is identical to
    today (opaque, sha256 at rest, ``access_token_ttl_minutes``); the refresh + family are new."""
    now = utcnow()
    access_token, access_expires = create_access_token(settings.access_token_ttl_minutes)
    refresh_token = secrets.token_urlsafe(32)
    absolute_expires = now + timedelta(minutes=settings.refresh_token_absolute_minutes)
    refresh_expires = _refresh_expiry(settings, now, absolute_expires)
    with session_scope(session_factory) as session:
        family = SessionFamilyORM(
            user_id=user_id,
            created_at=now,
            absolute_expires_at=absolute_expires,
            idle_ttl_seconds=settings.refresh_token_idle_minutes * 60,
            device_fingerprint_hash=fingerprint_hash(device_fingerprint),
            amr=amr,
            mfa_at=now if amr else None,
        )
        session.add(family)
        session.flush()
        refresh = RefreshTokenORM(
            family_id=family.id,
            user_id=user_id,
            token_hash=token_digest(refresh_token),
            created_at=now,
            expires_at=refresh_expires,
            last_used_at=now,
        )
        session.add(refresh)
        session.flush()
        session.add(
            SessionTokenORM(
                user_id=user_id,
                token_hash=token_digest(access_token),
                expires_at=access_expires,
                amr=amr,
                mfa_at=now if amr else None,
                family_id=family.id,
                refresh_id=refresh.id,
            )
        )
    return MintedSession(access_token, access_expires, refresh_token, refresh_expires)


# --------------------------------------------------------------------------- rotate


def rotate_refresh(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    refresh_token: str,
    device_fingerprint: str | None = None,
) -> MintedSession:
    """Validate a refresh, detect reuse, and (on success) mint a fresh access+refresh pair carrying
    the MFA/step-up state forward. Reuse / device-mismatch revoke the whole family."""
    now = utcnow()
    digest = token_digest(refresh_token)
    new_access, access_expires = create_access_token(settings.access_token_ttl_minutes)
    new_refresh = secrets.token_urlsafe(32)
    # `pending_error` carries failures whose side effect (family revoke) must COMMIT before raising.
    pending_error: tuple[str, int] | None = None
    reuse_audit_family: int | None = None
    outcome: MintedSession | None = None

    with session_scope(session_factory) as session:
        row = session.scalar(select(RefreshTokenORM).where(RefreshTokenORM.token_hash == digest))
        if row is None:
            raise SessionError("token_invalid", 401)
        family = session.get(SessionFamilyORM, row.family_id)
        if family is None:
            raise SessionError("token_invalid", 401)

        spent_or_revoked = (
            row.rotated_at is not None
            or row.revoked_at is not None
            or family.revoked_at is not None
        )
        if spent_or_revoked:
            if settings.refresh_reuse_revokes_family and family.revoked_at is None:
                _revoke_family(session, family, "reuse_detected", now)
                reuse_audit_family = family.id
            pending_error = ("token_reuse_detected", 401)
        elif _aware(row.expires_at) <= now or _aware(family.absolute_expires_at) <= now:
            raise SessionError("token_expired", 401)  # idle/absolute — benign, no family revoke
        elif (
            settings.session_device_binding_enabled
            and family.device_fingerprint_hash
            and not (
                device_fingerprint
                and hmac.compare_digest(
                    fingerprint_hash(device_fingerprint) or "", family.device_fingerprint_hash
                )
            )
        ):
            _revoke_family(session, family, "reuse_detected", now)
            reuse_audit_family = family.id
            pending_error = ("token_invalid", 401)
        else:
            # The current LIVE access row behind this refresh (newest, in case rotation-off minted
            # several against the same refresh id) — source of the MFA/step-up carry-forward.
            old_access = session.scalar(
                select(SessionTokenORM)
                .where(SessionTokenORM.refresh_id == row.id)
                .where(SessionTokenORM.revoked_at.is_(None))
                .order_by(SessionTokenORM.id.desc())
            )
            if settings.refresh_rotation_enabled:
                # Atomically spend the old refresh; a lost race (rowcount 0) = concurrent rotation.
                spent = session.execute(
                    update(RefreshTokenORM)
                    .where(RefreshTokenORM.id == row.id)
                    .where(RefreshTokenORM.rotated_at.is_(None))
                    .values(rotated_at=now)
                )
                if spent.rowcount != 1:
                    raise SessionError("token_reuse_detected", 401)
                refresh_expires = _refresh_expiry(settings, now, family.absolute_expires_at)
                new_refresh_row = RefreshTokenORM(
                    family_id=family.id,
                    user_id=row.user_id,
                    token_hash=token_digest(new_refresh),
                    created_at=now,
                    expires_at=refresh_expires,
                    last_used_at=now,
                    prev_id=row.id,
                )
                session.add(new_refresh_row)
                session.flush()
                row.next_id = new_refresh_row.id
                refresh_id_for_access = new_refresh_row.id
                refresh_token_out, refresh_expires_out = new_refresh, refresh_expires
            else:
                # Rotation off: keep the same refresh but slide its idle window forward.
                row.last_used_at = now
                row.expires_at = _refresh_expiry(settings, now, family.absolute_expires_at)
                refresh_id_for_access = row.id
                refresh_token_out, refresh_expires_out = refresh_token, _aware(row.expires_at)

            # Retire EVERY prior live access bearer for the old refresh (rotation-off can have
            # minted several) before issuing the new one — superseded bearers must not survive.
            session.execute(
                update(SessionTokenORM)
                .where(SessionTokenORM.refresh_id == row.id)
                .where(SessionTokenORM.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            access_row = SessionTokenORM(
                user_id=row.user_id,
                token_hash=token_digest(new_access),
                expires_at=access_expires,
                family_id=family.id,
                refresh_id=refresh_id_for_access,
            )
            for field in _MFA_CARRY_FIELDS:  # carry MFA/step-up forward or the session de-MFAs
                setattr(access_row, field, getattr(old_access, field) if old_access else None)
            if access_row.amr is None:
                access_row.amr = family.amr
            session.add(access_row)
            outcome = MintedSession(
                new_access, access_expires, refresh_token_out, refresh_expires_out
            )

    if reuse_audit_family is not None:
        audit_event(
            session_factory,
            event_type="auth.refresh_reuse",
            message="Refresh-token reuse detected; session family revoked.",
            entity_type="session_family",
            entity_id=reuse_audit_family,
        )
    if pending_error is not None:
        raise SessionError(*pending_error)
    if outcome is None:  # pragma: no cover - defensive
        raise SessionError("token_invalid", 401)
    return outcome


# --------------------------------------------------------------------------- revoke


def _revoke_family(session: Session, family: SessionFamilyORM, reason: str, now: datetime) -> None:
    """Revoke a family and every access + refresh row in it (immediate, in-transaction)."""
    if family.revoked_at is None:
        family.revoked_at = now
        family.revoked_reason = reason
    session.execute(
        update(RefreshTokenORM)
        .where(RefreshTokenORM.family_id == family.id)
        .where(RefreshTokenORM.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    session.execute(
        update(SessionTokenORM)
        .where(SessionTokenORM.family_id == family.id)
        .where(SessionTokenORM.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def revoke_family_by_refresh(session_factory: sessionmaker[Session], *, refresh_token: str) -> bool:
    now = utcnow()
    with session_scope(session_factory) as session:
        row = session.scalar(
            select(RefreshTokenORM).where(RefreshTokenORM.token_hash == token_digest(refresh_token))
        )
        if row is None:
            return False
        family = session.get(SessionFamilyORM, row.family_id)
        if family is None:
            return False
        _revoke_family(session, family, "logout", now)
        return True


def revoke_family_by_access(session_factory: sessionmaker[Session], *, access_token: str) -> bool:
    """Revoke the family behind an access bearer (logout). Returns False for a legacy NULL-family
    token (the caller falls back to single-token revocation)."""
    now = utcnow()
    with session_scope(session_factory) as session:
        row = session.scalar(
            select(SessionTokenORM).where(SessionTokenORM.token_hash == token_digest(access_token))
        )
        if row is None or row.family_id is None:
            return False
        family = session.get(SessionFamilyORM, row.family_id)
        if family is None:
            return False
        _revoke_family(session, family, "logout", now)
        return True


# NOTE: user-wide family revocation (e.g. on password change) lives in
# ``database.revoke_all_user_tokens`` (which already revokes the access rows in the same
# transaction), to keep that logic in one place and avoid divergence.
