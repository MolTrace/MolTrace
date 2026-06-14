"""SSO service layer: connection CRUD + the OIDC login/callback/exchange flow (Prompt 1).

This module is the only place that touches the ``sso_connections`` / ``sso_login_flows``
tables. The three-leg login is deliberately split so no bearer token is ever minted inside a
browser redirect:

1. :func:`begin_login`  — discover the IdP, mint PKCE/state/nonce, persist a pending flow,
   return the IdP authorization URL.
2. :func:`handle_callback` — verify state, exchange the code, validate the id_token, JIT the
   user + team membership, and stamp a single-use ``exchange_code`` on the flow.
3. :func:`consume_exchange` — trade that one-time code (over a normal POST from the SPA) for a
   hardened session (access + rotating refresh) via :func:`session_store.mint_session`.

Client secrets are stored AES-256-GCM encrypted (:mod:`sso_secret_crypto`) and decrypted only
for the token exchange. Redirect URIs are computed server-side from settings — never taken
from the client — to foreclose open-redirect / token-theft vectors.
"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import oidc_client, session_store
from .database import (
    create_user,
    get_user_by_email,
    get_user_by_token,
    session_scope,
)
from .models import (
    SSOConnectionCreate,
    SSOConnectionOut,
    SSOConnectionUpdate,
    UserPublic,
)
from .orm import SSOConnectionORM, SSOLoginFlowORM, TeamMemberORM, utcnow
from .session_store import MintedSession
from .settings import Settings
from .sso_secret_crypto import decrypt_secret, encrypt_secret

# A login flow is short-lived: the user is mid-redirect at the IdP. 10 minutes covers a slow
# MFA prompt while keeping the pending-state window small.
_FLOW_TTL_MINUTES = 10


class SSOError(ValueError):
    """Recoverable SSO failure (bad domain, disabled connection, expired flow) -> 400."""


class SSONotFound(LookupError):
    """No such connection / slug -> 404."""


# --------------------------------------------------------------------------- helpers


def _callback_redirect_uri(settings: Settings) -> str:
    """The OIDC ``redirect_uri`` the IdP posts back to — computed, never client-supplied."""
    return settings.base_url.rstrip("/") + "/auth/sso/callback"


def _decode_domains(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(value, list):
        return []
    return [str(d).strip().lower() for d in value if str(d).strip()]


def _normalize_domains(domains: list[str] | None) -> list[str]:
    seen: list[str] = []
    for d in domains or []:
        norm = d.strip().lower().lstrip("@")
        if norm and norm not in seen:
            seen.append(norm)
    return seen


def _email_domain(email: str) -> str:
    return email.strip().lower().rsplit("@", 1)[-1] if "@" in email else ""


def _is_expired(expires_at: datetime, now: datetime) -> bool:
    """SQLite returns naive datetimes for ``DateTime(timezone=True)`` columns; coerce to
    UTC-aware before comparing against the aware ``utcnow()`` value."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


def _to_out(conn: SSOConnectionORM) -> SSOConnectionOut:
    return SSOConnectionOut(
        id=conn.id,
        organization_id=conn.organization_id,
        slug=conn.slug,
        display_name=conn.display_name,
        protocol=conn.protocol,
        issuer=conn.issuer,
        client_id=conn.client_id,
        email_domains=_decode_domains(conn.email_domains_json),
        enabled=conn.enabled,
        enforce_sso=conn.enforce_sso,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


# ------------------------------------------------------------------------- CRUD (admin)


def list_connections(
    session_factory: sessionmaker[Session],
    *,
    organization_id: int | None = None,
) -> list[SSOConnectionOut]:
    with session_scope(session_factory) as session:
        stmt = select(SSOConnectionORM).order_by(SSOConnectionORM.id)
        if organization_id is not None:
            stmt = stmt.where(SSOConnectionORM.organization_id == organization_id)
        return [_to_out(row) for row in session.scalars(stmt).all()]


def get_connection(
    session_factory: sessionmaker[Session], connection_id: int
) -> SSOConnectionOut | None:
    with session_scope(session_factory) as session:
        row = session.get(SSOConnectionORM, connection_id)
        return None if row is None else _to_out(row)


def create_connection(
    session_factory: sessionmaker[Session],
    payload: SSOConnectionCreate,
    *,
    created_by_user_id: int | None,
    settings: Settings,
) -> SSOConnectionOut:
    with session_scope(session_factory) as session:
        clash = session.scalar(
            select(SSOConnectionORM).where(SSOConnectionORM.slug == payload.slug)
        )
        if clash is not None:
            raise SSOError(f"An SSO connection with slug {payload.slug!r} already exists.")
        row = SSOConnectionORM(
            organization_id=payload.organization_id,
            slug=payload.slug,
            display_name=payload.display_name,
            protocol="oidc",
            issuer=payload.issuer.rstrip("/"),
            client_id=payload.client_id,
            client_secret_encrypted=encrypt_secret(
                payload.client_secret, settings.sso_encryption_key
            ),
            email_domains_json=json.dumps(_normalize_domains(payload.email_domains)),
            enabled=payload.enabled,
            enforce_sso=payload.enforce_sso,
            created_by_user_id=created_by_user_id,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _to_out(row)


def update_connection(
    session_factory: sessionmaker[Session],
    connection_id: int,
    payload: SSOConnectionUpdate,
    *,
    settings: Settings,
) -> SSOConnectionOut | None:
    with session_scope(session_factory) as session:
        row = session.get(SSOConnectionORM, connection_id)
        if row is None:
            return None
        if payload.display_name is not None:
            row.display_name = payload.display_name
        if payload.issuer is not None:
            row.issuer = payload.issuer.rstrip("/")
        if payload.client_id is not None:
            row.client_id = payload.client_id
        if payload.client_secret is not None:
            row.client_secret_encrypted = encrypt_secret(
                payload.client_secret, settings.sso_encryption_key
            )
        if payload.email_domains is not None:
            row.email_domains_json = json.dumps(_normalize_domains(payload.email_domains))
        if payload.enabled is not None:
            row.enabled = payload.enabled
        if payload.enforce_sso is not None:
            row.enforce_sso = payload.enforce_sso
        session.flush()
        session.refresh(row)
        return _to_out(row)


def delete_connection(session_factory: sessionmaker[Session], connection_id: int) -> bool:
    with session_scope(session_factory) as session:
        row = session.get(SSOConnectionORM, connection_id)
        if row is None:
            return False
        session.delete(row)
        return True


# ----------------------------------------------------------------------- enforce-SSO


def is_sso_enforced_for_email(session_factory: sessionmaker[Session], email: str) -> bool:
    """True if an enabled+enforced connection claims this email's domain.

    Used by ``/auth/login`` to block password auth for SSO-governed users.
    """
    domain = _email_domain(email)
    if not domain:
        return False
    with session_scope(session_factory) as session:
        rows = session.scalars(
            select(SSOConnectionORM)
            .where(SSOConnectionORM.enabled.is_(True))
            .where(SSOConnectionORM.enforce_sso.is_(True))
        ).all()
        for row in rows:
            if domain in _decode_domains(row.email_domains_json):
                return True
    return False


# ------------------------------------------------------------------- OIDC login flow


def begin_login(
    session_factory: sessionmaker[Session], slug: str, *, settings: Settings
) -> str:
    """Start a login: returns the IdP authorization URL to redirect the browser to."""
    with session_scope(session_factory) as session:
        conn = session.scalar(
            select(SSOConnectionORM).where(SSOConnectionORM.slug == slug)
        )
        if conn is None:
            raise SSONotFound(f"No SSO connection for slug {slug!r}.")
        if not conn.enabled:
            raise SSOError(f"SSO connection {slug!r} is disabled.")
        conn_id = conn.id
        issuer = conn.issuer
        client_id = conn.client_id

    meta = oidc_client.discover(issuer)  # network — outside the DB session
    verifier, challenge = oidc_client.new_pkce()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    redirect_uri = _callback_redirect_uri(settings)

    with session_scope(session_factory) as session:
        session.add(
            SSOLoginFlowORM(
                connection_id=conn_id,
                state=state,
                nonce=nonce,
                code_verifier=verifier,
                redirect_uri=redirect_uri,
                status="pending",
                expires_at=utcnow() + timedelta(minutes=_FLOW_TTL_MINUTES),
            )
        )

    return oidc_client.build_authorization_url(
        meta,
        client_id=client_id,
        redirect_uri=redirect_uri,
        state=state,
        nonce=nonce,
        code_challenge=challenge,
    )


def handle_callback(
    session_factory: sessionmaker[Session], *, state: str, code: str, settings: Settings
) -> str:
    """Validate the IdP response, JIT the user, and return a one-time exchange code."""
    now = utcnow()
    with session_scope(session_factory) as session:
        flow = session.scalar(
            select(SSOLoginFlowORM).where(SSOLoginFlowORM.state == state)
        )
        if flow is None:
            raise SSOError("Unknown or already-used SSO login state.")
        if flow.status != "pending":
            raise SSOError("This SSO login has already been completed.")
        if _is_expired(flow.expires_at, now):
            raise SSOError("This SSO login has expired; please sign in again.")
        conn = session.get(SSOConnectionORM, flow.connection_id)
        if conn is None or not conn.enabled:
            raise SSOError("The SSO connection is no longer available.")
        flow_id = flow.id
        organization_id = conn.organization_id
        issuer = conn.issuer
        client_id = conn.client_id
        client_secret = decrypt_secret(
            conn.client_secret_encrypted, settings.sso_encryption_key
        )
        allowed_domains = _decode_domains(conn.email_domains_json)
        code_verifier = flow.code_verifier
        nonce = flow.nonce
        redirect_uri = flow.redirect_uri

    # Network legs, outside any DB session.
    meta = oidc_client.discover(issuer)
    tokens = oidc_client.exchange_code(
        meta,
        code=code,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
    )
    id_token = tokens.get("id_token")
    if not id_token:
        raise SSOError("The identity provider did not return an id_token.")
    claims = oidc_client.validate_id_token(
        id_token, meta=meta, client_id=client_id, nonce=nonce
    )

    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise SSOError("The identity provider did not assert an email address.")
    if claims.get("email_verified") is False:
        raise SSOError("The identity provider reports this email as unverified.")
    if allowed_domains and _email_domain(email) not in allowed_domains:
        raise SSOError("Your email domain is not permitted for this SSO connection.")

    # JIT provision the user (idempotent) and ensure org membership.
    user = get_user_by_email(session_factory, email)
    if user is None:
        user = create_user(
            session_factory,
            email=email,
            password=secrets.token_urlsafe(32),  # unusable; SSO is the only path in
            is_verified=True,
        )
    _ensure_team_membership(session_factory, organization_id=organization_id, email=email)

    exchange_code = secrets.token_urlsafe(32)
    with session_scope(session_factory) as session:
        flow = session.get(SSOLoginFlowORM, flow_id)
        if flow is None or flow.status != "pending":
            raise SSOError("This SSO login is no longer valid.")
        flow.user_id = user.id
        flow.exchange_code = exchange_code
        flow.status = "completed"
    return exchange_code


def consume_exchange(
    session_factory: sessionmaker[Session], *, code: str, settings: Settings
) -> tuple[MintedSession, UserPublic] | None:
    """Trade a one-time exchange code for a hardened session (access + rotating refresh, Prompt 4).
    Returns ``None`` if invalid."""
    now = utcnow()
    with session_scope(session_factory) as session:
        flow = session.scalar(
            select(SSOLoginFlowORM).where(SSOLoginFlowORM.exchange_code == code)
        )
        if flow is None or flow.status != "completed" or flow.user_id is None:
            return None
        if _is_expired(flow.expires_at, now):
            return None
        flow.status = "consumed"  # single-use
        user_id = flow.user_id

    minted = session_store.mint_session(session_factory, settings, user_id=user_id, amr="sso")
    user = get_user_by_token(session_factory, minted.access_token)
    if user is None:  # pragma: no cover - the session was just created
        return None
    return minted, user


def _ensure_team_membership(
    session_factory: sessionmaker[Session], *, organization_id: int, email: str
) -> None:
    normalized = email.strip().lower()
    with session_scope(session_factory) as session:
        existing = session.scalar(
            select(TeamMemberORM)
            .where(TeamMemberORM.organization_id == organization_id)
            .where(TeamMemberORM.user_email == normalized)
        )
        if existing is not None:
            if existing.status != "active":
                existing.status = "active"
            return
        session.add(
            TeamMemberORM(
                organization_id=organization_id,
                user_email=normalized,
                role="viewer",  # least-privilege; must be a valid CollaborationRole
                status="active",
            )
        )
