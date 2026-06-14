"""SCIM 2.0 provisioning service layer (Security Prompt 2).

Bolted onto the per-organization SSO connections (see :mod:`sso_store`). The IdP (Okta/Entra)
authenticates with a long-lived per-connection bearer token (stored SHA-256-digest only, like
session tokens) that resolves to exactly one connection -> one organization — the sole tenant key
for every request.

Tenant isolation invariant: the SCIM resource ``id`` handed back to the IdP is the
``scim_users.id`` row, NEVER the global ``users.id``. Every read/write starts from
``scim_users WHERE connection_id = ctx.connection_id``, so a resource id minted under one
connection resolves to no row under another connection's token (-> 404), closing IDOR and the
global-user enumeration space.

Deprovisioning is always **soft** (21 CFR Part 11 / GxP: a provisioned user may own analyses,
e-signatures, and audit rows that must stay referenceable forever). ``active:false`` and DELETE
flip ``scim_users.active`` + this org's ``team_members.status`` + revoke the user's sessions, and
only flip the *global* ``users.is_active`` when the user has no remaining active membership in any
*other* org — so one IdP can't lock a contractor out of a second org that still employs them.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import (
    audit_event,
    create_user,
    get_user_by_email,
    session_scope,
)
from .models import ScimTokenInfo, ScimTokenIssueResponse
from .orm import (
    SCIMTokenORM,
    SCIMUserORM,
    SessionTokenORM,
    SSOConnectionORM,
    TeamMemberORM,
    UserORM,
    utcnow,
)
from .security import token_digest

# team_members vocabulary — MUST match CollaborationRole / TeamMemberStatus in models.py
# (an out-of-vocabulary value breaks the org-members serializer). IdP-provisioned users get the
# least-privilege role; deactivation uses the canonical "disabled" status.
_SCIM_MEMBER_ROLE = "viewer"
_MEMBER_ACTIVE = "active"
_MEMBER_DISABLED = "disabled"

# SCIM 2.0 URNs.
_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
_ENTERPRISE_USER_SCHEMA = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
_PATCHOP_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"

_TOKEN_PREFIX_LEN = 12
_DEFAULT_PAGE = 100
_MAX_PAGE = 200

_FILTER_RE = re.compile(r'^\s*(?P<attr>\w+)\s+eq\s+"(?P<value>[^"]*)"\s*$', re.IGNORECASE)


# --------------------------------------------------------------------------- errors / context


class SCIMError(Exception):
    """A SCIM-shaped failure; the route renders it as the SCIM Error envelope."""

    def __init__(self, detail: str, status: int, scim_type: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.scim_type = scim_type


@dataclass(frozen=True)
class SCIMContext:
    """Resolved from the bearer token: the single connection/org this request may touch."""

    connection_id: int
    organization_id: int
    connection_slug: str


def scim_error_body(detail: str, status: int, scim_type: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"schemas": [_ERROR_SCHEMA], "detail": detail, "status": str(status)}
    if scim_type:
        body["scimType"] = scim_type
    return body


# --------------------------------------------------------------------------- small helpers


def _is_expired(expires_at: datetime, now: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_bool(value: Any) -> bool:
    """Coerce SCIM booleans, including the string ``"False"`` Okta/Entra sometimes send (treating
    it as truthy is the notorious bug that leaves offboarded users active)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _parse_id(scim_id: str) -> int | None:
    try:
        return int(scim_id)
    except (TypeError, ValueError):
        return None


def _parse_filter(filter_str: str) -> tuple[str, str]:
    """Minimal SCIM filter: ``<attr> eq "<value>"`` for userName / externalId (what Okta/Entra
    use to correlate). Anything else -> 400 invalidFilter."""
    match = _FILTER_RE.match(filter_str)
    if not match:
        raise SCIMError(f"Unsupported filter: {filter_str!r}", 400, "invalidFilter")
    attr = match.group("attr").lower()
    if attr not in {"username", "externalid"}:
        raise SCIMError(f"Unsupported filter attribute: {attr}", 400, "invalidFilter")
    return attr, match.group("value")


def _extract_username(payload: dict[str, Any]) -> str:
    user_name = payload.get("userName")
    if not isinstance(user_name, str) or not user_name.strip():
        raise SCIMError("userName is required", 400, "invalidValue")
    return user_name.strip()


def _extract_email(payload: dict[str, Any], user_name: str) -> str:
    emails = payload.get("emails")
    if isinstance(emails, list) and emails:
        primary = next(
            (e for e in emails if isinstance(e, dict) and e.get("primary") and e.get("value")),
            None,
        )
        chosen = primary or next(
            (e for e in emails if isinstance(e, dict) and e.get("value")), None
        )
        if chosen:
            return str(chosen["value"]).strip().lower()
    if "@" in user_name:
        return user_name.strip().lower()
    raise SCIMError("Cannot determine an email address for the user", 400, "invalidValue")


def _normalized_raw(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep the SCIM attributes we round-trip back to the IdP (we don't model the full schema)."""
    return {
        key: payload[key]
        for key in ("name", "displayName", "emails", "title", "externalId")
        if key in payload
    }


def _email_domain(email: str) -> str:
    return email.strip().lower().rsplit("@", 1)[-1] if "@" in email else ""


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


def _parse_page_param(value: str | None, default: int) -> int:
    """SCIM startIndex/count arrive as query strings; a bad value is a SCIM 400, never a FastAPI
    422 in application/json (which a strict IdP would reject mid-sync)."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise SCIMError(f"Invalid pagination value: {value!r}", 400, "invalidValue") from None


def _scim_user_resource(su: SCIMUserORM, user_email: str, base_url: str) -> dict[str, Any]:
    raw = json.loads(su.raw_attributes_json or "{}")
    resource: dict[str, Any] = {
        "schemas": [_USER_SCHEMA],
        "id": str(su.id),
        "userName": su.scim_user_name,
        "active": su.active,
        "emails": raw.get("emails") or [{"value": user_email, "primary": True, "type": "work"}],
        "meta": {
            "resourceType": "User",
            "created": _iso(su.created_at),
            "lastModified": _iso(su.updated_at),
            "location": f"{base_url.rstrip('/')}/scim/v2/Users/{su.id}",
        },
    }
    if su.external_id is not None:
        resource["externalId"] = su.external_id
    if raw.get("name"):
        resource["name"] = raw["name"]
    if raw.get("displayName"):
        resource["displayName"] = raw["displayName"]
    return resource


def _list_response(resources: list[dict[str, Any]], total: int, start_index: int) -> dict[str, Any]:
    return {
        "schemas": [_LIST_SCHEMA],
        "totalResults": total,
        "startIndex": start_index,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }


# --------------------------------------------------------------------------- token lifecycle


def issue_token(
    session_factory: sessionmaker[Session],
    *,
    connection_id: int,
    created_by_user_id: int | None,
) -> ScimTokenIssueResponse | None:
    """Mint a per-connection SCIM bearer (revoke-then-issue keeps one live token). The plaintext
    is returned exactly once; only its SHA-256 digest is stored. Returns ``None`` if the
    connection does not exist."""
    plaintext = "scim_" + secrets.token_urlsafe(36)
    digest = token_digest(plaintext)
    prefix = plaintext[:_TOKEN_PREFIX_LEN]
    now = utcnow()
    try:
        with session_scope(session_factory) as session:
            if session.get(SSOConnectionORM, connection_id) is None:
                return None
            live = session.scalars(
                select(SCIMTokenORM)
                .where(SCIMTokenORM.connection_id == connection_id)
                .where(SCIMTokenORM.revoked_at.is_(None))
            ).all()
            for row in live:
                row.revoked_at = now
            session.flush()  # satisfy the one-live-token partial-unique index before inserting
            record = SCIMTokenORM(
                connection_id=connection_id,
                token_prefix=prefix,
                token_hash=digest,
                created_by_user_id=created_by_user_id,
                created_at=now,
            )
            session.add(record)
            session.flush()
            created_at = record.created_at
            expires_at = record.expires_at
    except IntegrityError as exc:
        # A concurrent issue on the same connection lost the one-live-token race; surface a clean
        # conflict instead of a 500 (the invariant itself is upheld by the partial-unique index).
        raise SCIMError("A SCIM token was just issued for this connection; retry.", 409) from exc
    return ScimTokenIssueResponse(
        token=plaintext,
        token_prefix=prefix,
        connection_id=connection_id,
        created_at=created_at,
        expires_at=expires_at,
    )


def revoke_token(session_factory: sessionmaker[Session], *, connection_id: int) -> bool:
    now = utcnow()
    with session_scope(session_factory) as session:
        live = session.scalars(
            select(SCIMTokenORM)
            .where(SCIMTokenORM.connection_id == connection_id)
            .where(SCIMTokenORM.revoked_at.is_(None))
        ).all()
        if not live:
            return False
        for row in live:
            row.revoked_at = now
        return True


def get_token_info(
    session_factory: sessionmaker[Session], *, connection_id: int
) -> ScimTokenInfo | None:
    with session_scope(session_factory) as session:
        row = session.scalar(
            select(SCIMTokenORM)
            .where(SCIMTokenORM.connection_id == connection_id)
            .where(SCIMTokenORM.revoked_at.is_(None))
            .order_by(SCIMTokenORM.id.desc())
        )
        if row is None:
            return None
        return ScimTokenInfo(
            connection_id=connection_id,
            token_prefix=row.token_prefix,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            expires_at=row.expires_at,
        )


def resolve_token(
    session_factory: sessionmaker[Session], *, bearer: str | None
) -> SCIMContext | None:
    """Validate a presented bearer -> the single connection/org it authorizes, or ``None``."""
    if not bearer:
        return None
    digest = token_digest(bearer)
    now = utcnow()
    with session_scope(session_factory) as session:
        record = session.scalar(select(SCIMTokenORM).where(SCIMTokenORM.token_hash == digest))
        if record is None or record.revoked_at is not None:
            return None
        if record.expires_at is not None and _is_expired(record.expires_at, now):
            return None
        conn = session.get(SSOConnectionORM, record.connection_id)
        if conn is None or not conn.enabled:  # disabling the SSO connection disables SCIM
            return None
        record.last_used_at = now
        return SCIMContext(
            connection_id=conn.id,
            organization_id=conn.organization_id,
            connection_slug=conn.slug,
        )


# --------------------------------------------------------------------------- membership / active


def _ensure_membership(
    session: Session, *, organization_id: int, user_email: str, active: bool
) -> None:
    member = session.scalar(
        select(TeamMemberORM)
        .where(TeamMemberORM.organization_id == organization_id)
        .where(TeamMemberORM.user_email == user_email)
    )
    status = _MEMBER_ACTIVE if active else _MEMBER_DISABLED
    if member is None:
        session.add(
            TeamMemberORM(
                organization_id=organization_id,
                user_email=user_email,
                role=_SCIM_MEMBER_ROLE,
                status=status,
            )
        )
    else:
        member.status = status


def _revoke_user_sessions(session: Session, user_id: int) -> None:
    """Revoke the user's live session tokens in THIS transaction, so the deactivation and the
    session cutoff commit atomically (no crash-window where a deprovisioned user keeps a live
    session)."""
    rows = session.scalars(
        select(SessionTokenORM)
        .where(SessionTokenORM.user_id == user_id)
        .where(SessionTokenORM.revoked_at.is_(None))
    ).all()
    for row in rows:
        row.revoked_at = utcnow()


def _set_active(
    session: Session, su: SCIMUserORM, active: bool, *, organization_id: int, user_email: str
) -> None:
    """Apply (de)activation: scim mapping + this org's membership + the conditional global flag.
    On deactivation, the user's sessions are revoked in the same transaction."""
    su.active = active
    if active:
        su.deprovisioned_at = None
        _ensure_membership(
            session, organization_id=organization_id, user_email=user_email, active=True
        )
        user = session.get(UserORM, su.user_id)
        if user is not None:
            user.is_active = True
        return
    member = session.scalar(
        select(TeamMemberORM)
        .where(TeamMemberORM.organization_id == organization_id)
        .where(TeamMemberORM.user_email == user_email)
    )
    if member is not None:
        member.status = _MEMBER_DISABLED
    _revoke_user_sessions(session, su.user_id)  # immediate session cutoff, atomic with the disable
    # Flip the GLOBAL flag only if no other org still has an active membership for this user —
    # else this IdP would lock the user out of a second org that still employs them.
    other_active = session.scalar(
        select(func.count())
        .select_from(TeamMemberORM)
        .where(TeamMemberORM.user_email == user_email)
        .where(TeamMemberORM.status == _MEMBER_ACTIVE)
        .where(TeamMemberORM.organization_id != organization_id)
    )
    if not other_active:
        user = session.get(UserORM, su.user_id)
        if user is not None:
            user.is_active = False


def _audit(
    session_factory: sessionmaker[Session],
    ctx: SCIMContext,
    *,
    event: str,
    message: str,
    scim_id: int | None,
    metadata: dict[str, object] | None = None,
) -> None:
    audit_event(
        session_factory,
        event_type=event,
        message=message,
        actor_user_id=None,
        actor_email=f"scim:{ctx.connection_slug}",
        entity_type="scim_user",
        entity_id=scim_id,
        metadata=metadata,
    )


# --------------------------------------------------------------------------- /Users provisioning


def list_users(
    session_factory: sessionmaker[Session],
    *,
    ctx: SCIMContext,
    base_url: str,
    filter_str: str | None,
    start_index: str | None,
    count: str | None,
) -> dict[str, Any]:
    # Parse pagination from raw query strings so a bad value is a SCIM 400 (not a FastAPI 422).
    start = _parse_page_param(start_index, 1)
    start = start if start >= 1 else 1
    page_size = _parse_page_param(count, _DEFAULT_PAGE)
    page_size = min(max(page_size, 0), _MAX_PAGE)
    with session_scope(session_factory) as session:
        stmt = select(SCIMUserORM).where(SCIMUserORM.connection_id == ctx.connection_id)
        if filter_str:
            attr, value = _parse_filter(filter_str)
            if attr == "username":
                stmt = stmt.where(func.lower(SCIMUserORM.scim_user_name) == value.lower())
            else:  # externalid — opaque, case-sensitive
                stmt = stmt.where(SCIMUserORM.external_id == value)
        rows = session.scalars(stmt.order_by(SCIMUserORM.id)).all()
        total = len(rows)
        page = rows[start - 1 : start - 1 + page_size] if page_size > 0 else []
        resources = [
            _scim_user_resource(su, _email_of(session, su), base_url) for su in page
        ]
    return _list_response(resources, total, start)


def get_user(
    session_factory: sessionmaker[Session], *, ctx: SCIMContext, base_url: str, scim_id: str
) -> dict[str, Any] | None:
    sid = _parse_id(scim_id)
    if sid is None:
        return None
    with session_scope(session_factory) as session:
        su = session.get(SCIMUserORM, sid)
        if su is None or su.connection_id != ctx.connection_id:
            return None
        return _scim_user_resource(su, _email_of(session, su), base_url)


def _email_of(session: Session, su: SCIMUserORM) -> str:
    user = session.get(UserORM, su.user_id)
    return user.email if user is not None else su.scim_user_name


def _clash(session: Session, connection_id: int, external_id: str | None, user_name: str) -> bool:
    if external_id:
        if session.scalar(
            select(SCIMUserORM.id)
            .where(SCIMUserORM.connection_id == connection_id)
            .where(SCIMUserORM.external_id == external_id)
        ):
            return True
    return bool(
        session.scalar(
            select(SCIMUserORM.id)
            .where(SCIMUserORM.connection_id == connection_id)
            .where(func.lower(SCIMUserORM.scim_user_name) == user_name.lower())
        )
    )


def _delete_orphan_user(session_factory: sessionmaker[Session], user_id: int) -> None:
    """Delete a just-minted global user that ended up with no SCIM mapping and no membership, so a
    uniqueness conflict on create never leaves an orphan (which would also shadow the email)."""
    with session_scope(session_factory) as session:
        if session.scalar(select(SCIMUserORM.id).where(SCIMUserORM.user_id == user_id)):
            return
        user = session.get(UserORM, user_id)
        if user is None:
            return
        if session.scalar(select(TeamMemberORM.id).where(TeamMemberORM.user_email == user.email)):
            return
        session.delete(user)


def create_user_scim(
    session_factory: sessionmaker[Session],
    *,
    ctx: SCIMContext,
    base_url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Three-way create/link. A connection may only provision emails inside its configured domain
    allowlist (fail closed on an empty allowlist) — this binds a SCIM-provisioned identity to the
    connection and blocks an IdP from linking/controlling a user in another org. 409 only when THIS
    connection already has the resource; otherwise link to the canonical (globally-unique-email)
    user and provision into this org."""
    user_name = _extract_username(payload)
    external_id = payload.get("externalId")
    if external_id is not None:
        external_id = str(external_id)
    email = _extract_email(payload, user_name)
    domain = _email_domain(email)
    active = _coerce_bool(payload.get("active", True))
    raw = _normalized_raw(payload)

    # Domain binding + pre-check (before creating any global user, so a conflict never orphans one).
    with session_scope(session_factory) as session:
        conn = session.get(SSOConnectionORM, ctx.connection_id)
        allowed = _decode_domains(conn.email_domains_json) if conn is not None else []
        if not allowed or domain not in allowed:
            raise SCIMError(
                "This SCIM connection is not permitted to provision this email domain.", 403
            )
        if _clash(session, ctx.connection_id, external_id, user_name):
            raise SCIMError("User already provisioned for this connection", 409, "uniqueness")

    existing = get_user_by_email(session_factory, email)
    linked = existing is not None
    created_new = False
    if existing is not None:
        user = existing
    else:
        try:
            user = create_user(
                session_factory, email=email, password=secrets.token_urlsafe(32), is_verified=True
            )
        except ValueError as exc:  # email raced into existence between lookup and create
            raise SCIMError("User already exists", 409, "uniqueness") from exc
        created_new = True

    try:
        with session_scope(session_factory) as session:
            if _clash(session, ctx.connection_id, external_id, user_name) or session.scalar(
                select(SCIMUserORM.id)
                .where(SCIMUserORM.connection_id == ctx.connection_id)
                .where(SCIMUserORM.user_id == user.id)
            ):
                raise SCIMError("User already provisioned for this connection", 409, "uniqueness")
            su = SCIMUserORM(
                connection_id=ctx.connection_id,
                user_id=user.id,
                external_id=external_id,
                scim_user_name=user_name,
                active=active,
                raw_attributes_json=json.dumps(raw),
            )
            session.add(su)
            _ensure_membership(
                session, organization_id=ctx.organization_id, user_email=email, active=active
            )
            session.flush()
            session.refresh(su)
            resource = _scim_user_resource(su, email, base_url)
            scim_id = su.id
    except (SCIMError, IntegrityError) as exc:
        if created_new:  # never leave an orphan global user behind on conflict
            _delete_orphan_user(session_factory, user.id)
        if isinstance(exc, IntegrityError):
            raise SCIMError(
                "User already provisioned for this connection", 409, "uniqueness"
            ) from exc
        raise

    _audit(
        session_factory,
        ctx,
        event="scim.user.linked" if linked else "scim.user.provisioned",
        message=f"SCIM {'linked' if linked else 'provisioned'} {email} ({user_name}).",
        scim_id=scim_id,
        metadata={"email": email, "external_id": external_id, "linked": linked},
    )
    return resource


def replace_user(
    session_factory: sessionmaker[Session],
    *,
    ctx: SCIMContext,
    base_url: str,
    scim_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """PUT: replace mutable attributes; honor ``active`` only when the IdP actually sends it.

    ``active`` is treated as a (de)activation signal ONLY when the key is present — defaulting an
    omitted ``active`` to True would silently re-enable an admin-disabled account on a routine
    attribute sync."""
    sid = _parse_id(scim_id)
    if sid is None:
        return None
    active = _coerce_bool(payload["active"]) if "active" in payload else None
    new_external = payload.get("externalId")
    raw = _normalized_raw(payload)
    deactivated = False
    try:
        with session_scope(session_factory) as session:
            su = session.get(SCIMUserORM, sid)
            if su is None or su.connection_id != ctx.connection_id:
                return None
            new_name = payload.get("userName")
            if isinstance(new_name, str) and new_name.strip():
                su.scim_user_name = new_name.strip()
            if new_external is not None:
                su.external_id = str(new_external)
            su.raw_attributes_json = json.dumps(raw)
            email = _email_of(session, su)
            if active is not None:
                was_active = su.active
                _set_active(
                    session, su, active, organization_id=ctx.organization_id, user_email=email
                )
                deactivated = was_active and not active
            session.flush()
            resource = _scim_user_resource(su, email, base_url)
            scim_id_int = su.id
    except IntegrityError as exc:
        raise SCIMError(
            "userName or externalId already in use for this connection", 409, "uniqueness"
        ) from exc
    if deactivated:
        _audit(session_factory, ctx, event="scim.user.deactivated",
               message="SCIM deactivated user via PUT.", scim_id=scim_id_int)
    return resource


def patch_user(
    session_factory: sessionmaker[Session],
    *,
    ctx: SCIMContext,
    base_url: str,
    scim_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """PATCH: the deprovisioning workhorse. Honors both Okta (scalar path ``active``) and Entra
    (capitalized op, pathless object value, string booleans) variants."""
    sid = _parse_id(scim_id)
    if sid is None:
        return None
    operations = payload.get("Operations") or payload.get("operations") or []
    if not isinstance(operations, list):
        raise SCIMError("PatchOp Operations must be a list", 400, "invalidValue")

    active_change: bool | None = None
    attr_updates: dict[str, Any] = {}
    for op in operations:
        if not isinstance(op, dict):
            continue
        op_name = str(op.get("op", "")).lower()
        path = op.get("path")
        value = op.get("value")
        if op_name not in {"add", "replace", "remove"}:
            raise SCIMError(f"Unsupported PATCH op: {op.get('op')!r}", 400, "invalidValue")
        if op_name == "remove":
            if isinstance(path, str) and path.lower() == "active":
                active_change = False
            continue
        if path is None and isinstance(value, dict):  # Entra pathless object
            for key, val in value.items():
                if key.lower() == "active":
                    active_change = _coerce_bool(val)
                else:
                    attr_updates[key] = val
        elif isinstance(path, str):  # Okta scalar path
            if path.lower() == "active":
                active_change = _coerce_bool(value)
            else:
                attr_updates[path] = value
        else:
            raise SCIMError("Unsupported PATCH path", 400, "invalidPath")

    deactivated = False
    try:
        with session_scope(session_factory) as session:
            su = session.get(SCIMUserORM, sid)
            if su is None or su.connection_id != ctx.connection_id:
                return None
            email = _email_of(session, su)
            if attr_updates:
                raw = json.loads(su.raw_attributes_json or "{}")
                for key, val in attr_updates.items():
                    base = key.split(".")[0].split("[")[0]  # tolerate value-paths
                    if base in {"name", "displayName", "emails", "title"}:
                        raw[base] = val
                    elif base == "userName" and isinstance(val, str) and val.strip():
                        su.scim_user_name = val.strip()
                    elif base == "externalId" and val is not None:
                        su.external_id = str(val)
                su.raw_attributes_json = json.dumps(raw)
            if active_change is not None:
                was_active = su.active
                _set_active(
                    session,
                    su,
                    active_change,
                    organization_id=ctx.organization_id,
                    user_email=email,
                )
                deactivated = was_active and not active_change
            session.flush()
            resource = _scim_user_resource(su, email, base_url)
            scim_id_int = su.id
    except IntegrityError as exc:
        raise SCIMError(
            "userName or externalId already in use for this connection", 409, "uniqueness"
        ) from exc
    if deactivated:
        _audit(session_factory, ctx, event="scim.user.deactivated",
               message="SCIM deactivated user via PATCH active:false.", scim_id=scim_id_int)
    return resource


def delete_user(session_factory: sessionmaker[Session], *, ctx: SCIMContext, scim_id: str) -> bool:
    """Soft-deprovision: tear down the mapping (active=false, deprovisioned_at, membership inactive,
    sessions revoked) but KEEP every row. Returns False (-> 404) if the resource isn't ours."""
    sid = _parse_id(scim_id)
    if sid is None:
        return False
    with session_scope(session_factory) as session:
        su = session.get(SCIMUserORM, sid)
        if su is None or su.connection_id != ctx.connection_id:
            return False
        email = _email_of(session, su)
        _set_active(session, su, False, organization_id=ctx.organization_id, user_email=email)
        su.deprovisioned_at = utcnow()
        scim_id_int = su.id
    _audit(session_factory, ctx, event="scim.user.deprovisioned",
           message="SCIM deprovisioned user via DELETE.", scim_id=scim_id_int)
    return True


# --------------------------------------------------------------------------- discovery


def service_provider_config(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": _MAX_PAGE},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "OAuth Bearer Token",
                "description": "Per-connection SCIM bearer token (issued by an org admin).",
                "primary": True,
            }
        ],
        "meta": {
            "resourceType": "ServiceProviderConfig",
            "location": f"{base}/scim/v2/ServiceProviderConfig",
        },
    }


def resource_type_user(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
        "id": "User",
        "name": "User",
        "endpoint": "/Users",
        "description": "User Account",
        "schema": _USER_SCHEMA,
        "schemaExtensions": [{"schema": _ENTERPRISE_USER_SCHEMA, "required": False}],
        "meta": {"resourceType": "ResourceType", "location": f"{base}/scim/v2/ResourceTypes/User"},
    }


def resource_types(base_url: str) -> dict[str, Any]:
    # Users-only by design (no Group provisioning in this build, so Group is not advertised).
    return _list_response([resource_type_user(base_url)], 1, 1)


def _core_user_schema(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")

    def attr(name: str, **kw: Any) -> dict[str, Any]:
        base = {
            "name": name,
            "type": "string",
            "multiValued": False,
            "required": False,
            "caseExact": False,
            "mutability": "readWrite",
            "returned": "default",
            "uniqueness": "none",
        }
        base.update(kw)
        return base

    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Schema"],
        "id": _USER_SCHEMA,
        "name": "User",
        "description": "User Account",
        "attributes": [
            attr("userName", required=True, uniqueness="server"),
            attr("active", type="boolean"),
            attr("externalId", caseExact=True),
            attr("displayName"),
            {
                "name": "name",
                "type": "complex",
                "multiValued": False,
                "required": False,
                "subAttributes": [attr("givenName"), attr("familyName"), attr("formatted")],
                "mutability": "readWrite",
                "returned": "default",
            },
            {
                "name": "emails",
                "type": "complex",
                "multiValued": True,
                "required": False,
                "subAttributes": [attr("value"), attr("type"), attr("primary", type="boolean")],
                "mutability": "readWrite",
                "returned": "default",
            },
        ],
        "meta": {"resourceType": "Schema", "location": f"{base}/scim/v2/Schemas/{_USER_SCHEMA}"},
    }


def _enterprise_user_schema(base_url: str) -> dict[str, Any]:
    base = base_url.rstrip("/")
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Schema"],
        "id": _ENTERPRISE_USER_SCHEMA,
        "name": "EnterpriseUser",
        "description": "Enterprise User Extension",
        "attributes": [
            {
                "name": "department",
                "type": "string",
                "multiValued": False,
                "required": False,
                "mutability": "readWrite",
                "returned": "default",
            }
        ],
        "meta": {
            "resourceType": "Schema",
            "location": f"{base}/scim/v2/Schemas/{_ENTERPRISE_USER_SCHEMA}",
        },
    }


def schemas_list(base_url: str) -> dict[str, Any]:
    return _list_response([_core_user_schema(base_url), _enterprise_user_schema(base_url)], 2, 1)


def schema_by_id(urn: str, base_url: str) -> dict[str, Any] | None:
    if urn == _USER_SCHEMA:
        return _core_user_schema(base_url)
    if urn == _ENTERPRISE_USER_SCHEMA:
        return _enterprise_user_schema(base_url)
    return None
