"""MFA orchestration: login challenge, step-up, per-tenant policy, recovery (Security Prompt 3).

This is the policy/flow layer over :mod:`mfa_totp` + :mod:`mfa_webauthn`. Security spine:
- The MFA-pending token lives in ``mfa_login_challenges`` (digest only) — invisible to
  ``get_user_by_token`` — so "no MFA -> no bearer" is structural, not disciplinary.
- Per-tenant enforcement is fail-closed: if ANY active org requires MFA past its grace, MFA is
  required; any error resolving policy is treated as required.
- Step-up is a fresh-factor proof stamped on ``session_tokens`` (5-min TTL). Admin + signing ops
  demand it. Recovery codes are a valid login factor but NEVER a valid step-up.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from . import mfa_totp, mfa_webauthn
from .database import (
    authenticate_user,
    create_user_session,
    get_user_by_token,
    session_scope,
)
from .mfa_webauthn import MFAError
from .models import UserPublic
from .orm import (
    MFALoginChallengeORM,
    MFAPolicyORM,
    MFARecoveryCodeORM,
    MFATotpCredentialORM,
    MFAWebAuthnCredentialORM,
    SessionTokenORM,
    TeamMemberORM,
    utcnow,
)
from .security import (
    generate_recovery_codes,
    normalize_recovery_code,
    token_digest,
)
from .settings import Settings

# 'mfa' = IdP-asserted MFA at SSO; 'backup' = recovery code (valid for login, never for step-up).
_STRONG_LOGIN_AMR = {"totp", "webauthn", "backup", "mfa"}


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _within(dt: datetime | None, minutes: int, now: datetime) -> bool:
    return dt is not None and _aware(dt) + timedelta(minutes=minutes) > now


# --------------------------------------------------------------------------- decisions


@dataclass
class LoginDecision:
    """Either a challenge (route returns 202) or proceed-and-mint (route mints a session)."""

    challenge_token: str | None = None
    factors: list[str] = field(default_factory=list)
    webauthn_options: str | None = None
    amr: list[str] = field(default_factory=list)  # factors to stamp when not a challenge
    enrollment_required: bool = False

    @property
    def needs_mfa(self) -> bool:
        return self.challenge_token is not None


# ----------------------------------------------------------------- factor / policy queries


def _confirmed_totp(session: Session, user_id: int) -> MFATotpCredentialORM | None:
    return session.scalar(
        select(MFATotpCredentialORM)
        .where(MFATotpCredentialORM.user_id == user_id)
        .where(MFATotpCredentialORM.confirmed_at.is_not(None))
    )


def _has_passkey(session: Session, user_id: int) -> bool:
    return (
        session.scalar(
            select(MFAWebAuthnCredentialORM.id)
            .where(MFAWebAuthnCredentialORM.user_id == user_id)
            .limit(1)
        )
        is not None
    )


def _user_factors(session: Session, user_id: int) -> list[str]:
    factors: list[str] = []
    if _has_passkey(session, user_id):
        factors.append("webauthn")
    if _confirmed_totp(session, user_id) is not None:
        factors.append("totp")
    return factors


def has_confirmed_factor(session_factory: sessionmaker[Session], user_id: int) -> bool:
    with session_scope(session_factory) as session:
        return bool(_user_factors(session, user_id))


def _active_org_ids(session: Session, email: str) -> list[int]:
    rows = session.scalars(
        select(TeamMemberORM.organization_id)
        .where(TeamMemberORM.user_email == email.strip().lower())
        .where(TeamMemberORM.status == "active")
    ).all()
    return [int(r) for r in rows]


def mfa_required_for_user(
    session_factory: sessionmaker[Session], email: str, now: datetime
) -> tuple[bool, bool]:
    """Return ``(required_past_grace, in_grace)``. Fail-closed: any error -> required."""
    try:
        with session_scope(session_factory) as session:
            org_ids = _active_org_ids(session, email)
            if not org_ids:
                return False, False
            policies = session.scalars(
                select(MFAPolicyORM)
                .where(MFAPolicyORM.organization_id.in_(org_ids))
                .where(MFAPolicyORM.mfa_required.is_(True))
            ).all()
            required, in_grace = False, False
            for p in policies:
                anchor = _aware(p.mfa_required_at) if p.mfa_required_at else now
                if anchor + timedelta(days=p.grace_period_days) <= now:
                    required = True
                else:
                    in_grace = True
            return required, in_grace
    except Exception:  # noqa: BLE001 - fail closed
        return True, False


# --------------------------------------------------------------------------- login flow


def _new_login_challenge(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    org_id: int | None,
    settings: Settings,
    factors: list[str],
    webauthn_challenge: bytes | None,
    sso_flow_id: str | None,
    amr_from_sso: str | None,
) -> str:
    token = secrets.token_urlsafe(32)
    with session_scope(session_factory) as session:
        session.add(
            MFALoginChallengeORM(
                token_hash=token_digest(token),
                user_id=user_id,
                organization_id=org_id,
                purpose="login",
                factors_offered_json=json.dumps(factors),
                webauthn_challenge=webauthn_challenge,
                sso_flow_id=sso_flow_id,
                amr_from_sso=amr_from_sso,
                expires_at=utcnow() + timedelta(minutes=settings.mfa_pending_ttl_minutes),
            )
        )
    return token


def begin_or_complete_login(
    session_factory: sessionmaker[Session],
    settings: Settings,
    user: UserPublic,
    *,
    org_id: int | None = None,
    sso_amr: str | None = None,
) -> LoginDecision:
    """Decide whether to challenge for a second factor or proceed to mint a session.

    Password path (``sso_amr=None``): if the user has a confirmed factor, challenge. SSO path: if
    the IdP asserted MFA, proceed (amr includes sso+mfa); else behave like the password path. With
    ``enforce_for_sso`` the user must verify a LOCAL factor regardless of the IdP."""
    now = utcnow()
    is_sso = sso_amr is not None
    sso_has_mfa = is_sso and _sso_amr_has_mfa(sso_amr)
    with session_scope(session_factory) as session:
        factors = _user_factors(session, user.id)
        enforce_for_sso = False
        if is_sso:
            org_ids = _active_org_ids(session, user.email)
            if org_ids:
                enforce_for_sso = bool(
                    session.scalar(
                        select(MFAPolicyORM.id)
                        .where(MFAPolicyORM.organization_id.in_(org_ids))
                        .where(MFAPolicyORM.enforce_for_sso.is_(True))
                        .limit(1)
                    )
                )

    has_factor = bool(factors)
    if is_sso and sso_has_mfa and not enforce_for_sso:
        return LoginDecision(amr=["sso", "mfa"])
    if not has_factor:
        # Nothing to challenge with. Proceed; require_mfa_satisfied / enrollment handles the rest.
        amr = ["sso"] if is_sso else ["pwd"]
        required, _ = mfa_required_for_user(session_factory, user.email, now)
        return LoginDecision(amr=amr, enrollment_required=required or enforce_for_sso)

    # The user has a local factor -> challenge for it before issuing a bearer.
    webauthn_options = None
    webauthn_challenge = None
    if "webauthn" in factors:
        made = mfa_webauthn.make_login_authentication_options(
            session_factory, user_id=user.id, settings=settings
        )
        if made is not None:
            webauthn_options, webauthn_challenge = made
    offered = list(factors)
    if _recovery_remaining(session_factory, user.id) > 0:
        offered.append("recovery")
    token = _new_login_challenge(
        session_factory,
        user_id=user.id,
        org_id=org_id,
        settings=settings,
        factors=offered,
        webauthn_challenge=webauthn_challenge,
        sso_flow_id=None,
        amr_from_sso=sso_amr,
    )
    return LoginDecision(
        challenge_token=token, factors=offered, webauthn_options=webauthn_options
    )


def _sso_amr_has_mfa(sso_amr: str | None) -> bool:
    if not sso_amr:
        return False
    tokens = {t.strip().lower() for t in sso_amr.replace(",", " ").split()}
    return bool(tokens & {"mfa", "otp", "totp", "hwk", "swk", "pin", "fido", "webauthn"})


def _burn_login_challenge(
    session_factory: sessionmaker[Session], token: str, now: datetime
) -> tuple[int, bytes | None]:
    """Atomically consume (single-use) the MFA-pending token in its OWN committed transaction,
    BEFORE the factor is verified — so a wrong code burns the token and can't be retried (closes the
    brute-force oracle). The conditional UPDATE (rowcount==1) is the atomic single-use guard under
    concurrency. Returns ``(user_id, webauthn_challenge)``; raises on invalid/expired/used."""
    digest = token_digest(token)
    with session_scope(session_factory) as session:
        row = session.scalar(
            select(MFALoginChallengeORM).where(MFALoginChallengeORM.token_hash == digest)
        )
        if row is None or row.consumed_at is not None:
            raise MFAError("Invalid or already-used MFA token.", 400)
        if _aware(row.expires_at) <= now:
            raise MFAError("MFA challenge expired; please sign in again.", 400)
        user_id = row.user_id
        webauthn_challenge = row.webauthn_challenge
        result = session.execute(
            update(MFALoginChallengeORM)
            .where(MFALoginChallengeORM.id == row.id)
            .where(MFALoginChallengeORM.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        if result.rowcount != 1:  # lost a concurrent race -> already consumed
            raise MFAError("Invalid or already-used MFA token.", 400)
    return user_id, webauthn_challenge


def _mint(
    session_factory: sessionmaker[Session], settings: Settings, user_id: int, amr: list[str]
) -> tuple[str, datetime, UserPublic]:
    token, expires = create_user_session(
        session_factory,
        user_id=user_id,
        ttl_minutes=settings.access_token_ttl_minutes,
        amr=",".join(amr),
    )
    user = get_user_by_token(session_factory, token)
    if user is None:  # pragma: no cover
        raise MFAError("Session creation failed.", 500)
    return token, expires, user


def complete_login_totp(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    mfa_token: str,
    code: str,
    for_time: datetime | None = None,
) -> tuple[str, datetime, UserPublic]:
    now = utcnow()
    user_id, _ = _burn_login_challenge(session_factory, mfa_token, now)
    with session_scope(session_factory) as session:
        cred = _confirmed_totp(session, user_id)
        if cred is None:
            raise MFAError("No confirmed TOTP for this account.", 400)
        secret = mfa_totp.decrypt_secret(cred.secret_encrypted, settings.mfa_encryption_key)
        step = mfa_totp.verify(secret, code, last_used_step=cred.last_used_step, for_time=for_time)
        if step is None:
            raise MFAError("Invalid authentication code.", 401)
        cred.last_used_step = step
    return _mint(session_factory, settings, user_id, ["totp"])


def complete_login_webauthn(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    mfa_token: str,
    credential: dict,
) -> tuple[str, datetime, UserPublic]:
    now = utcnow()
    user_id, webauthn_challenge = _burn_login_challenge(session_factory, mfa_token, now)
    if not webauthn_challenge:
        raise MFAError("This MFA challenge has no passkey option.", 400)
    with session_scope(session_factory) as session:
        mfa_webauthn.verify_assertion_for_user(
            session,
            user_id=user_id,
            credential=credential,
            expected_challenge=webauthn_challenge,
            settings=settings,
        )
    return _mint(session_factory, settings, user_id, ["webauthn"])


def complete_login_recovery(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    mfa_token: str,
    code: str,
) -> tuple[str, datetime, UserPublic]:
    now = utcnow()
    user_id, _ = _burn_login_challenge(session_factory, mfa_token, now)
    with session_scope(session_factory) as session:
        if not _consume_recovery_code(session, user_id, code, now):
            raise MFAError("Invalid recovery code.", 401)
    return _mint(session_factory, settings, user_id, ["backup"])


# --------------------------------------------------------------------------- step-up


def _read_session(session: Session, raw_token: str | None) -> SessionTokenORM | None:
    if not raw_token:
        return None
    return session.scalar(
        select(SessionTokenORM).where(SessionTokenORM.token_hash == token_digest(raw_token))
    )


def is_stepped_up(
    session_factory: sessionmaker[Session], settings: Settings, raw_token: str | None
) -> bool:
    now = utcnow()
    with session_scope(session_factory) as session:
        row = _read_session(session, raw_token)
        if row is None:
            return False
        return _within(row.stepped_up_at, settings.step_up_ttl_minutes, now)


def _stamp_step_up(
    session: Session, raw_token: str, *, factor: str, aal: str, now: datetime
) -> None:
    row = _read_session(session, raw_token)
    if row is None:
        raise MFAError("No active session to step up.", 401)
    row.stepped_up_at = now
    row.step_up_factor = factor
    row.step_up_aal = aal
    merged = {p for p in (row.amr or "").split(",") if p}
    merged.add(factor)
    row.amr = ",".join(sorted(merged))


def step_up_options(
    session_factory: sessionmaker[Session], settings: Settings, *, user_id: int
) -> dict:
    with session_scope(session_factory) as session:
        factors = _user_factors(session, user_id)
    options = None
    if "webauthn" in factors:
        options = mfa_webauthn.begin_authentication_options(
            session_factory, user_id=user_id, purpose="step_up", settings=settings
        )
    # password fallback only when the user has no stronger factor
    offered = list(factors) or ["password"]
    return {"factors": offered, "webauthn_options": options}


def complete_step_up_totp(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    raw_token: str,
    user_id: int,
    code: str,
    for_time: datetime | None = None,
) -> dict:
    now = utcnow()
    with session_scope(session_factory) as session:
        if "webauthn" in _user_factors(session, user_id):
            raise MFAError("A passkey is required for step-up on this account.", 400)
        cred = _confirmed_totp(session, user_id)
        if cred is None:
            raise MFAError("No confirmed TOTP for this account.", 400)
        secret = mfa_totp.decrypt_secret(cred.secret_encrypted, settings.mfa_encryption_key)
        step = mfa_totp.verify(secret, code, last_used_step=cred.last_used_step, for_time=for_time)
        if step is None:
            raise MFAError("Invalid authentication code.", 401)
        cred.last_used_step = step
        _stamp_step_up(session, raw_token, factor="totp", aal="aal1", now=now)
    return {"stepped_up": True, "factor": "totp", "aal": "aal1",
            "expires_at": now + timedelta(minutes=settings.step_up_ttl_minutes)}


def complete_step_up_webauthn(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    raw_token: str,
    user_id: int,
    credential: dict,
) -> dict:
    now = utcnow()
    with session_scope(session_factory) as session:
        challenge = mfa_webauthn._consume_challenge(
            session, user_id=user_id, purpose="step_up", now=now
        )
        mfa_webauthn.verify_assertion_for_user(
            session,
            user_id=user_id,
            credential=credential,
            expected_challenge=challenge.challenge,
            settings=settings,
        )
        _stamp_step_up(session, raw_token, factor="webauthn", aal="aal2", now=now)
    return {"stepped_up": True, "factor": "webauthn", "aal": "aal2",
            "expires_at": now + timedelta(minutes=settings.step_up_ttl_minutes)}


def complete_step_up_password(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    raw_token: str,
    user: UserPublic,
    password: str,
) -> dict:
    """Password step-up is accepted ONLY when the user has no stronger factor (no downgrade)."""
    now = utcnow()
    with session_scope(session_factory) as session:
        if _user_factors(session, user.id):
            raise MFAError("A passkey or authenticator code is required for step-up.", 400)
    if authenticate_user(session_factory, email=user.email, password=password) is None:
        raise MFAError("Incorrect password.", 401)
    with session_scope(session_factory) as session:
        _stamp_step_up(session, raw_token, factor="pwd", aal="aal1", now=now)
    return {"stepped_up": True, "factor": "pwd", "aal": "aal1",
            "expires_at": now + timedelta(minutes=settings.step_up_ttl_minutes)}


def read_step_up(
    session_factory: sessionmaker[Session], raw_token: str | None
) -> tuple[datetime | None, str | None, str | None]:
    with session_scope(session_factory) as session:
        row = _read_session(session, raw_token)
        if row is None:
            return None, None, None
        return row.stepped_up_at, row.step_up_factor, row.step_up_aal


# --------------------------------------------------------------------------- TOTP enrollment


def totp_enroll(
    session_factory: sessionmaker[Session], settings: Settings, *, user_id: int, email: str
) -> str:
    secret = mfa_totp.generate_secret()
    enc = mfa_totp.encrypt_secret(secret, settings.mfa_encryption_key)
    with session_scope(session_factory) as session:
        # Replace any prior unconfirmed enrollment.
        for row in session.scalars(
            select(MFATotpCredentialORM)
            .where(MFATotpCredentialORM.user_id == user_id)
            .where(MFATotpCredentialORM.confirmed_at.is_(None))
        ).all():
            session.delete(row)
        session.flush()
        session.add(MFATotpCredentialORM(user_id=user_id, secret_encrypted=enc))
    return mfa_totp.provisioning_uri(secret, account_name=email, issuer=settings.webauthn_rp_name)


def totp_confirm(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    user_id: int,
    code: str,
    for_time: datetime | None = None,
) -> list[str] | None:
    """Confirm a pending TOTP enrollment. Returns recovery codes when this is the user's first
    confirmed factor (shown once), else ``None``."""
    now = utcnow()
    issued: list[str] | None = None
    with session_scope(session_factory) as session:
        if _confirmed_totp(session, user_id) is not None:
            raise MFAError("TOTP is already configured.", 409)
        pending = session.scalar(
            select(MFATotpCredentialORM)
            .where(MFATotpCredentialORM.user_id == user_id)
            .where(MFATotpCredentialORM.confirmed_at.is_(None))
            .order_by(MFATotpCredentialORM.id.desc())
        )
        if pending is None:
            raise MFAError("Start TOTP enrollment first.", 400)
        secret = mfa_totp.decrypt_secret(pending.secret_encrypted, settings.mfa_encryption_key)
        step = mfa_totp.verify(secret, code, last_used_step=None, for_time=for_time)
        if step is None:
            raise MFAError("Invalid authentication code.", 401)
        pending.confirmed_at = now
        pending.last_used_step = step
        had_passkey = bool(
            session.scalar(
                select(MFAWebAuthnCredentialORM.id)
                .where(MFAWebAuthnCredentialORM.user_id == user_id)
                .limit(1)
            )
        )
        had_recovery = _recovery_remaining_in_session(session, user_id) > 0
        if not had_passkey and not had_recovery:
            issued = _issue_recovery_codes(session, user_id)
    return issued


def totp_delete(session_factory: sessionmaker[Session], *, user_id: int) -> bool:
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(MFATotpCredentialORM).where(MFATotpCredentialORM.user_id == user_id)
        ).all()
        if not rows:
            return False
        for row in rows:
            session.delete(row)
        return True


# --------------------------------------------------------------------------- recovery codes


def _issue_recovery_codes(session: Session, user_id: int) -> list[str]:
    for row in session.scalars(
        select(MFARecoveryCodeORM).where(MFARecoveryCodeORM.user_id == user_id)
    ).all():
        session.delete(row)
    session.flush()
    codes = generate_recovery_codes()
    for code in codes:
        session.add(
            MFARecoveryCodeORM(
                user_id=user_id, code_hash=token_digest(normalize_recovery_code(code))
            )
        )
    return codes


def regenerate_recovery_codes(session_factory: sessionmaker[Session], *, user_id: int) -> list[str]:
    with session_scope(session_factory) as session:
        return _issue_recovery_codes(session, user_id)


def ensure_recovery_codes(
    session_factory: sessionmaker[Session], *, user_id: int
) -> list[str] | None:
    """Issue recovery codes if the user has a confirmed factor but no codes yet (covers the
    passkey-first user, who would otherwise have no recovery path). Returns them once, or None."""
    with session_scope(session_factory) as session:
        if _recovery_remaining_in_session(session, user_id) > 0:
            return None
        if not _user_factors(session, user_id):
            return None
        return _issue_recovery_codes(session, user_id)


def _consume_recovery_code(session: Session, user_id: int, code: str, now: datetime) -> bool:
    digest = token_digest(normalize_recovery_code(code))
    # Conditional UPDATE (rowcount==1) is the atomic single-use guard against a double-submit race.
    result = session.execute(
        update(MFARecoveryCodeORM)
        .where(MFARecoveryCodeORM.user_id == user_id)
        .where(MFARecoveryCodeORM.code_hash == digest)
        .where(MFARecoveryCodeORM.used_at.is_(None))
        .values(used_at=now)
    )
    return result.rowcount == 1


def _recovery_remaining_in_session(session: Session, user_id: int) -> int:
    return len(
        session.scalars(
            select(MFARecoveryCodeORM.id)
            .where(MFARecoveryCodeORM.user_id == user_id)
            .where(MFARecoveryCodeORM.used_at.is_(None))
        ).all()
    )


def _recovery_remaining(session_factory: sessionmaker[Session], user_id: int) -> int:
    with session_scope(session_factory) as session:
        return _recovery_remaining_in_session(session, user_id)


# --------------------------------------------------------------------------- status / policy


def status(session_factory: sessionmaker[Session], *, user_id: int, email: str) -> dict:
    now = utcnow()
    with session_scope(session_factory) as session:
        factors = _user_factors(session, user_id)
        totp_confirmed = "totp" in factors
        passkeys = len(
            session.scalars(
                select(MFAWebAuthnCredentialORM.id).where(
                    MFAWebAuthnCredentialORM.user_id == user_id
                )
            ).all()
        )
        recovery_remaining = _recovery_remaining_in_session(session, user_id)
    required, in_grace = mfa_required_for_user(session_factory, email, now)
    return {
        "factors": factors,
        "totp_confirmed": totp_confirmed,
        "passkey_count": passkeys,
        "recovery_remaining": recovery_remaining,
        "org_mfa_required": required,
        "in_grace": in_grace,
    }


def _policy_to_dict(row: MFAPolicyORM) -> dict:
    return {
        "organization_id": row.organization_id,
        "mfa_required": row.mfa_required,
        "grace_period_days": row.grace_period_days,
        "allowed_factors": json.loads(row.allowed_factors_json or "[]"),
        "enforce_for_sso": row.enforce_for_sso,
        "require_step_up_for_signing": row.require_step_up_for_signing,
    }


def get_policy(session_factory: sessionmaker[Session], *, organization_id: int) -> dict:
    with session_scope(session_factory) as session:
        row = session.scalar(
            select(MFAPolicyORM).where(MFAPolicyORM.organization_id == organization_id)
        )
        if row is None:
            return {
                "organization_id": organization_id,
                "mfa_required": False,
                "grace_period_days": 7,
                "allowed_factors": ["webauthn", "totp"],
                "enforce_for_sso": False,
                "require_step_up_for_signing": True,
            }
        return _policy_to_dict(row)


def set_policy(
    session_factory: sessionmaker[Session],
    *,
    organization_id: int,
    mfa_required: bool,
    grace_period_days: int,
    allowed_factors: list[str],
    enforce_for_sso: bool,
    require_step_up_for_signing: bool,
    updated_by_user_id: int | None,
) -> dict:
    now = utcnow()
    with session_scope(session_factory) as session:
        row = session.scalar(
            select(MFAPolicyORM).where(MFAPolicyORM.organization_id == organization_id)
        )
        if row is None:
            row = MFAPolicyORM(organization_id=organization_id)
            session.add(row)
        was_required = row.mfa_required
        row.mfa_required = mfa_required
        if mfa_required and not was_required:
            row.mfa_required_at = now  # (re)stamp the grace anchor when enabling
        row.grace_period_days = grace_period_days
        row.allowed_factors_json = json.dumps(allowed_factors)
        row.enforce_for_sso = enforce_for_sso
        row.require_step_up_for_signing = require_step_up_for_signing
        row.updated_by_user_id = updated_by_user_id
        session.flush()
        return _policy_to_dict(row)


def mfa_satisfied_for_session(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    user_id: int,
    email: str,
    raw_token: str | None,
) -> tuple[bool, str | None]:
    """Evaluate require_mfa_satisfied: True unless the user's org requires MFA and the session has
    neither a strong login amr nor a fresh step-up. Returns ``(allowed, detail_if_blocked)``."""
    now = utcnow()
    required, _ = mfa_required_for_user(session_factory, email, now)
    if not required:
        return True, None
    with session_scope(session_factory) as session:
        row = _read_session(session, raw_token)
        amr = {p for p in ((row.amr if row else None) or "").split(",") if p}
        stepped = row is not None and _within(row.stepped_up_at, settings.step_up_ttl_minutes, now)
        has_factor = bool(_user_factors(session, user_id))
    if amr & _STRONG_LOGIN_AMR or stepped:
        return True, None
    return False, ("mfa_required" if has_factor else "mfa_enrollment_required")
