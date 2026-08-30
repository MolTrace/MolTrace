"""WebAuthn / FIDO2 passkey second factor (Security Prompt 3).

Phishing resistance comes from the server ALWAYS supplying the expected ``rp_id`` and ``origin``
(from settings, never the client) and from requiring User Verification on every assertion. The
origin side is a SET — one ``rp_id``, several accepted origins, each matched by whole-string
equality and never by a pattern (:func:`nmrcheck.settings.webauthn_accepted_origins`). Options
generation is deliberately NOT widened: it still mints against the single ``rp_id``, because
varying it per ceremony would create credentials that cannot verify against each other. The two
network-equivalent verify calls — :func:`verify_registration` / :func:`verify_authentication` — are
module-level so tests can monkeypatch them with a synthetic authenticator (no real device), exactly
like :mod:`oidc_client`. Challenges are server-minted, single-use, and TTL-bounded; the
``sign_count`` is persisted for clone detection.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from . import error_codes
from .database import session_scope
from .orm import MFAWebAuthnChallengeORM, MFAWebAuthnCredentialORM, UserORM, utcnow
from .settings import Settings, webauthn_accepted_origins

_CHALLENGE_TTL_MINUTES = 5


class MFAError(Exception):
    """An MFA failure rendered to the client as ``{status} {detail}`` (default 400).

    ``code`` is the machine-readable situation for the 401/403 cases, where ``detail`` is
    replaced by fixed generic copy before it reaches the wire and is therefore no longer able
    to carry a signal. At 400/409/500 ``detail`` still reaches the client unchanged and
    ``code`` is optional.
    """

    def __init__(self, detail: str, status: int = 400, *, code: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.error_code = code


# --------------------------------------------------------------------- pure py_webauthn seams


def _expected_origin(settings: Settings) -> str | list[str]:
    """The origin(s) a ceremony may claim, for py_webauthn to match by whole-string equality.

    A single accepted origin is passed as the bare string it has always been, so a deployment that
    has not set ``WEBAUTHN_ADDITIONAL_ORIGINS`` verifies -- and refuses -- byte-identically to
    before. py_webauthn matches a list by membership, which is that same exact equality; it is
    never handed a prefix, suffix, wildcard or regular expression to interpret.
    """
    accepted = webauthn_accepted_origins(settings)
    if not accepted:
        # Nothing configured can ever match, so refuse with a nameable cause rather than letting
        # it surface as a puzzling verification failure. validate_startup_settings says which
        # value is at fault.
        raise MFAError("Passkeys are not usable: no valid WebAuthn origin is configured.", 500)
    if len(accepted) == 1:
        return accepted[0]
    return list(accepted)


def verify_registration(
    credential: dict[str, Any], *, expected_challenge: bytes, settings: Settings
):
    """Verify an attestation. Module-level so tests can substitute a synthetic authenticator."""
    return verify_registration_response(
        credential=json.dumps(credential),
        expected_challenge=expected_challenge,
        expected_rp_id=settings.webauthn_rp_id,
        expected_origin=_expected_origin(settings),
        require_user_verification=True,
    )


def verify_authentication(
    credential: dict[str, Any],
    *,
    expected_challenge: bytes,
    public_key: bytes,
    current_sign_count: int,
    settings: Settings,
):
    """Verify an assertion (UV required). Module-level seam for tests."""
    return verify_authentication_response(
        credential=json.dumps(credential),
        expected_challenge=expected_challenge,
        expected_rp_id=settings.webauthn_rp_id,
        expected_origin=_expected_origin(settings),
        credential_public_key=public_key,
        credential_current_sign_count=current_sign_count,
        require_user_verification=True,
    )


# ------------------------------------------------------------------------- helpers / queries


def _user_credentials(session: Session, user_id: int) -> list[MFAWebAuthnCredentialORM]:
    return list(
        session.scalars(
            select(MFAWebAuthnCredentialORM).where(MFAWebAuthnCredentialORM.user_id == user_id)
        ).all()
    )


def user_handle(session: Session, user_id: int) -> bytes:
    """A stable, opaque per-user WebAuthn handle (NOT the email — privacy + RP-ID hygiene)."""
    return f"moltrace-user-{user_id}".encode()


def _new_challenge_row(
    session: Session,
    *,
    user_id: int,
    purpose: str,
    challenge: bytes,
    rp_id: str,
    handle: bytes | None,
) -> None:
    session.add(
        MFAWebAuthnChallengeORM(
            user_id=user_id,
            purpose=purpose,
            challenge=challenge,
            rp_id=rp_id,
            webauthn_user_handle=handle,
            expires_at=utcnow() + timedelta(minutes=_CHALLENGE_TTL_MINUTES),
        )
    )


def _consume_challenge(
    session: Session, *, user_id: int, purpose: str, now: datetime
) -> MFAWebAuthnChallengeORM:
    row = session.scalar(
        select(MFAWebAuthnChallengeORM)
        .where(MFAWebAuthnChallengeORM.user_id == user_id)
        .where(MFAWebAuthnChallengeORM.purpose == purpose)
        .where(MFAWebAuthnChallengeORM.consumed_at.is_(None))
        .order_by(MFAWebAuthnChallengeORM.id.desc())
    )
    if row is None:
        raise MFAError("No pending WebAuthn challenge.", 400)
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires <= now:
        raise MFAError("WebAuthn challenge expired; please retry.", 400)
    row.consumed_at = now  # single-use
    return row


# --------------------------------------------------------------------------- registration


def begin_registration(
    session_factory: sessionmaker[Session], *, user: UserORM | Any, settings: Settings
) -> str:
    """Leg 1: mint registration options (resident key + UV required), persist the challenge."""
    with session_scope(session_factory) as session:
        existing = [
            PublicKeyCredentialDescriptor(id=c.credential_id)
            for c in _user_credentials(session, user.id)
        ]
        handle = user_handle(session, user.id)
        options = generate_registration_options(
            rp_id=settings.webauthn_rp_id,
            rp_name=settings.webauthn_rp_name,
            user_id=handle,
            user_name=user.email,
            user_display_name=user.email,
            exclude_credentials=existing,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        _new_challenge_row(
            session,
            user_id=user.id,
            purpose="webauthn_register",
            challenge=options.challenge,
            rp_id=settings.webauthn_rp_id,
            handle=handle,
        )
        return options_to_json(options)


def complete_registration(
    session_factory: sessionmaker[Session],
    *,
    user_id: int,
    credential: dict[str, Any],
    nickname: str | None,
    settings: Settings,
) -> int:
    """Leg 2: verify the attestation against the server-stored challenge; store the passkey."""
    now = utcnow()
    with session_scope(session_factory) as session:
        challenge_row = _consume_challenge(
            session, user_id=user_id, purpose="webauthn_register", now=now
        )
        try:
            verified = verify_registration(
                credential, expected_challenge=challenge_row.challenge, settings=settings
            )
        except MFAError:
            raise
        except Exception as exc:  # noqa: BLE001 - any verification failure is a hard fail
            raise MFAError(f"Passkey registration failed: {exc}", 400) from exc
        if not getattr(verified, "user_verified", True):
            raise MFAError("User verification was not performed.", 400)
        if session.scalar(
            select(MFAWebAuthnCredentialORM.id).where(
                MFAWebAuthnCredentialORM.credential_id == verified.credential_id
            )
        ):
            raise MFAError("This passkey is already registered.", 409)
        row = MFAWebAuthnCredentialORM(
            user_id=user_id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports_json=json.dumps(credential.get("transports") or []),
            aaguid=str(getattr(verified, "aaguid", "") or "") or None,
            device_type=str(getattr(verified, "credential_device_type", "") or "") or None,
            backed_up=bool(getattr(verified, "credential_backed_up", False)),
            nickname=(nickname or None),
            last_used_at=now,
        )
        session.add(row)
        session.flush()
        return int(row.id)


# ------------------------------------------------------------------- authentication / step-up


def begin_authentication_options(
    session_factory: sessionmaker[Session], *, user_id: int, purpose: str, settings: Settings
) -> str:
    """Mint authentication options (UV required) for an enrolled user; persist the step_up
    challenge under ``purpose``. Used by step-up (login mints its challenge on its own row)."""
    with session_scope(session_factory) as session:
        creds = _user_credentials(session, user_id)
        if not creds:
            raise MFAError("No passkey registered.", 400)
        options = generate_authentication_options(
            rp_id=settings.webauthn_rp_id,
            allow_credentials=[PublicKeyCredentialDescriptor(id=c.credential_id) for c in creds],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        _new_challenge_row(
            session,
            user_id=user_id,
            purpose=purpose,
            challenge=options.challenge,
            rp_id=settings.webauthn_rp_id,
            handle=None,
        )
        return options_to_json(options)


def make_login_authentication_options(
    session_factory: sessionmaker[Session], *, user_id: int, settings: Settings
) -> tuple[str, bytes] | None:
    """Pure auth options for the login flow (challenge persisted by the caller on the login row,
    not in mfa_webauthn_challenges). Returns ``(options_json, challenge_bytes)`` or ``None`` if the
    user has no passkey."""
    with session_scope(session_factory) as session:
        creds = _user_credentials(session, user_id)
        if not creds:
            return None
        options = generate_authentication_options(
            rp_id=settings.webauthn_rp_id,
            allow_credentials=[PublicKeyCredentialDescriptor(id=c.credential_id) for c in creds],
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        return options_to_json(options), options.challenge


def verify_assertion_for_user(
    session: Session,
    *,
    user_id: int,
    credential: dict[str, Any],
    expected_challenge: bytes,
    settings: Settings,
) -> MFAWebAuthnCredentialORM:
    """Core assertion verification shared by login + step-up: match the credential to THIS user,
    verify (UV required) against the given server challenge, clone-detect, advance sign_count.
    Runs in a caller-provided session so it commits atomically with the caller's mutation."""
    raw_id = credential.get("rawId") or credential.get("id")
    if not raw_id:
        raise MFAError("Malformed assertion (missing credential id).", 400)
    cred_id = _b64url_decode(raw_id)
    row = session.scalar(
        select(MFAWebAuthnCredentialORM)
        .where(MFAWebAuthnCredentialORM.user_id == user_id)
        .where(MFAWebAuthnCredentialORM.credential_id == cred_id)
    )
    if row is None:
        raise MFAError("Unknown passkey for this account.", 400)
    try:
        verified = verify_authentication(
            credential,
            expected_challenge=expected_challenge,
            public_key=row.public_key,
            current_sign_count=row.sign_count,
            settings=settings,
        )
    except MFAError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise MFAError(f"Passkey authentication failed: {exc}", 400) from exc
    if not getattr(verified, "user_verified", True):
        raise MFAError("User verification was not performed.", 400)
    new_count = int(getattr(verified, "new_sign_count", 0))
    # Clone detection: a non-zero counter must strictly advance. (Synced passkeys report 0 — never
    # downgrade a previously non-zero counter to 0.)
    if row.sign_count > 0 and new_count <= row.sign_count:
        # The caller is told only that the factor was not accepted. Naming the sign-counter
        # check here tells whoever holds a cloned credential that the clone was detected and
        # which check caught it; the person who OWNS the credential learns of it through the
        # audit chain and the account's notification path, which reaches the owner rather than
        # the copy.
        raise MFAError(
            "Passkey clone/replay detected (sign count did not advance).",
            401,
            code=error_codes.MFA_FACTOR_INVALID,
        )
    if new_count > row.sign_count:
        row.sign_count = new_count
    row.last_used_at = utcnow()
    return row


# -------------------------------------------------------------------------- management


def list_credentials(
    session_factory: sessionmaker[Session], *, user_id: int
) -> list[dict[str, Any]]:
    with session_scope(session_factory) as session:
        out = []
        for c in _user_credentials(session, user_id):
            out.append(
                {
                    "id": c.id,
                    "nickname": c.nickname,
                    "device_type": c.device_type,
                    "backed_up": c.backed_up,
                    "created_at": c.created_at,
                    "last_used_at": c.last_used_at,
                }
            )
        return out


def rename_credential(
    session_factory: sessionmaker[Session], *, user_id: int, credential_pk: int, nickname: str
) -> bool:
    with session_scope(session_factory) as session:
        row = session.get(MFAWebAuthnCredentialORM, credential_pk)
        if row is None or row.user_id != user_id:
            return False
        row.nickname = nickname.strip() or None
        return True


def delete_credential(
    session_factory: sessionmaker[Session], *, user_id: int, credential_pk: int
) -> bool:
    with session_scope(session_factory) as session:
        row = session.get(MFAWebAuthnCredentialORM, credential_pk)
        if row is None or row.user_id != user_id:
            return False
        session.delete(row)
        return True


def _b64url_decode(value: str) -> bytes:
    import base64

    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
