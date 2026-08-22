"""Issuance policy for signed offline entitlement statements — the only module here that
touches the database.

**Nothing is stored server-side.** There is no statement table, no issuance table and no key
table: a statement is derived from deployment configuration plus the device row, signed, and
returned. A stored statement would be a second source of truth that can disagree with the
configuration it came from, and the signature already carries the fact. It also keeps the issuer
stateless apart from device enrolment, so a deployment restored from any backup keeps issuing
correctly — which is what makes a perpetual licence survivable.

Issuance and refusal are recorded in the existing audit trail, which is the operator's ledger.
The chain listener links each row in with no per-site work.

**This module NEVER gates a read.** Reading, exporting and verifying existing records continues
whatever the entitlement state — a customer is not locked out of their own regulated records by
a commercial term. Nothing here may be turned into a FastAPI dependency;
``tests/test_entitlement_never_gates_reads.py`` fails the build if ``fastapi`` is imported here
or if a ``require_*`` callable appears. That structural check is a speed bump rather than a
proof (a gate can be built elsewhere out of a module shaped exactly like this one — that is how
``api._module_licence_gate`` is built out of ``module_access``), so the control that holds is
the behavioural one in the same file. If you need a gate, you need a different module and a
different conversation.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from . import database
from . import entitlement_statement as es
from .mobile_store import MobileActor, MobileExperienceNotFoundError, assert_device_session_visible
from .models import (
    ENTITLEMENT_REFUSAL_DETAILS,
    ENTITLEMENT_UNAVAILABLE_DETAILS,
    EntitlementAuthorityStatus,
    EntitlementCertificate,
    EntitlementIssuance,
    EntitlementIssuanceRequest,
    EntitlementStatement,
)
from .orm import MobileDeviceSessionORM
from .settings import Settings

#: Every setting that makes a deployment an issuer. A deployment that issues nothing must still
#: start, so "none of them set" is a valid configuration and not an error.
ISSUER_SETTINGS = (
    "entitlement_issuing_private_key",
    "entitlement_certificate_b64",
    "entitlement_certificate_signature",
    "entitlement_offline_period_days",
    "entitlement_statement_validity_hours",
)


@dataclass(frozen=True, slots=True)
class EntitlementAuthority:
    """This deployment's own signing authority, resolved from configuration and self-checked."""

    certificate: dict[str, object]
    certificate_bytes: bytes
    certificate_b64: str
    certificate_signature: str
    issuing_seed: str
    root_public_key: str
    root_key_id: str
    issuing_key_id: str
    offline_period_days: int
    statement_validity_hours: int
    licence_class: str


class AuthorityUnavailable(Exception):
    """This deployment cannot issue. A fault in its own provisioning, never a decision about
    the customer — the two are kept apart so a misconfigured deployment never tells someone
    their offline use was withdrawn."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        self.detail = ENTITLEMENT_UNAVAILABLE_DETAILS[code]


def declares_itself_an_issuer(settings: Settings) -> bool:
    return any(getattr(settings, name, None) for name in ISSUER_SETTINGS)


def resolve_authority(settings: Settings, *, now: datetime | None = None) -> EntitlementAuthority:
    """Read the authority out of configuration, verifying the chain as we go.

    Raises :class:`AuthorityUnavailable` naming the cause. Order matters: an operator whose
    certificate is merely expired should be told that, not that it is not genuine.
    """
    moment = now or datetime.now(UTC)

    seed = settings.entitlement_issuing_private_key
    certificate_b64 = settings.entitlement_certificate_b64
    signature = settings.entitlement_certificate_signature
    root_public_key = settings.entitlement_root_public_key
    if not (seed and certificate_b64 and signature and root_public_key):
        raise AuthorityUnavailable("authority_not_provisioned")

    try:
        certificate_bytes = es.b64u_decode(certificate_b64)
        certificate = json.loads(certificate_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuthorityUnavailable("authority_certificate_invalid") from exc
    if not isinstance(certificate, dict):
        raise AuthorityUnavailable("authority_certificate_invalid")

    root_key_id = es.public_key_id("r", es.ROOT_KEY_TAG, root_public_key)
    if certificate.get("root_key_id") != root_key_id:
        raise AuthorityUnavailable("authority_certificate_invalid")
    if not es.verify_payload(
        es.CERTIFICATE_DOMAIN, certificate_bytes, signature, root_public_key
    ):
        raise AuthorityUnavailable("authority_certificate_invalid")

    # The seed must be the half of the pair the certificate names, or this deployment would be
    # signing statements no verifier could check against its own certificate.
    try:
        issuing_public = es.public_key_hex_from_seed(seed)
    except es.EntitlementKeyError as exc:
        raise AuthorityUnavailable("authority_certificate_invalid") from exc
    if issuing_public != certificate.get("issuing_public_key"):
        raise AuthorityUnavailable("authority_certificate_invalid")

    issuing_key_id = es.public_key_id("d", es.ISSUING_KEY_TAG, str(issuing_public))
    if certificate.get("issuing_key_id") != issuing_key_id:
        raise AuthorityUnavailable("authority_certificate_invalid")

    try:
        not_before = es.parse_iso(str(certificate["not_before"]))
        not_after = es.parse_iso(str(certificate["not_after"]))
    except (KeyError, ValueError) as exc:
        raise AuthorityUnavailable("authority_certificate_invalid") from exc
    if not (not_before <= moment <= not_after):
        raise AuthorityUnavailable("authority_certificate_expired")

    # Neither number has a default, on purpose: both are commercial terms nobody has measured,
    # and a plausible-looking round number inside a signature is worse than a refusal that says
    # the decision has not been made.
    offline_period_days = settings.entitlement_offline_period_days
    if not offline_period_days or offline_period_days < 1:
        raise AuthorityUnavailable("offline_period_not_published")
    validity_hours = settings.entitlement_statement_validity_hours
    if not validity_hours or validity_hours < 1:
        raise AuthorityUnavailable("offline_period_not_published")

    permitted_classes = [str(value) for value in certificate.get("permitted_licence_classes") or ()]
    licence_class = settings.entitlement_licence_class
    if not licence_class:
        # Unambiguous is not the same as invented: one permitted class IS the answer.
        if len(permitted_classes) == 1:
            licence_class = permitted_classes[0]
        else:
            raise AuthorityUnavailable("licence_class_not_published")
    if licence_class not in permitted_classes:
        raise AuthorityUnavailable("authority_certificate_invalid")

    return EntitlementAuthority(
        certificate=certificate,
        certificate_bytes=certificate_bytes,
        certificate_b64=certificate_b64,
        certificate_signature=signature,
        issuing_seed=seed,
        root_public_key=root_public_key,
        root_key_id=root_key_id,
        issuing_key_id=issuing_key_id,
        offline_period_days=int(offline_period_days),
        statement_validity_hours=int(validity_hours),
        licence_class=licence_class,
    )


def authority_status(
    settings: Settings, *, now: datetime | None = None
) -> EntitlementAuthorityStatus:
    """The operator diagnostic. **Public material only** — the issuing seed appears in no field.

    This is also where a provisioning cause is delivered, because a 5xx body cannot carry one:
    the shared error handler replaces a 5xx response's prose *and* its machine code with fixed
    constants, so neither field on that path can say what is wrong. A configuration problem
    does not belong in a 5xx body anyway; it belongs on a diagnostic an operator can read.
    """
    try:
        authority = resolve_authority(settings, now=now)
    except AuthorityUnavailable as unavailable:
        return EntitlementAuthorityStatus(
            provisioned=False,
            offline_period_days=settings.entitlement_offline_period_days,
            statement_validity_hours=settings.entitlement_statement_validity_hours,
            unavailable_code=unavailable.code,  # type: ignore[arg-type]
            unavailable_detail=unavailable.detail,
        )
    return EntitlementAuthorityStatus(
        provisioned=True,
        root_key_id=authority.root_key_id,
        issuing_key_id=authority.issuing_key_id,
        certificate=EntitlementCertificate(**authority.certificate),  # type: ignore[arg-type]
        certificate_bytes_b64=authority.certificate_b64,
        certificate_signature=authority.certificate_signature,
        offline_period_days=authority.offline_period_days,
        statement_validity_hours=authority.statement_validity_hours,
    )


def _refusal(
    authority: EntitlementAuthority, code: str, *, nonce: str, observed_at: datetime
) -> EntitlementIssuance:
    """A refusal is a licensing ANSWER carried by a successful response.

    A refresh that succeeds and returns no entitlement is a refusal to reissue, and the desktop
    treats it as a withdrawal: it keeps the statement it already holds, which runs out on its
    own terms, and does not retry as though a fault had occurred.
    """
    exchange = es.exchange_payload(
        nonce=nonce, observed_at=observed_at, issued=False, statement_bytes=None
    )
    return EntitlementIssuance(
        issued=False,
        exchange_nonce=nonce,
        observed_at=observed_at,
        exchange_signature=es.sign_payload(
            es.EXCHANGE_DOMAIN, exchange, authority.issuing_seed
        ),
        refusal_code=code,  # type: ignore[arg-type]
        refusal_detail=ENTITLEMENT_REFUSAL_DETAILS[code],
    )


def issue_statement(
    session_factory: sessionmaker[Session],
    settings: Settings,
    payload: EntitlementIssuanceRequest,
    *,
    actor: MobileActor,
    enabled_modules: tuple[str, ...],
    now: datetime | None = None,
) -> EntitlementIssuance:
    """Issue or refuse a statement for one enrolled installation.

    Raises :class:`AuthorityUnavailable` when this deployment cannot issue at all, and
    :class:`MobileExperienceNotFoundError` for a device the caller cannot reach — the same
    answer as one that does not exist, so a stranger learns nothing about whose installations
    exist.
    """
    observed_at = now or datetime.now(UTC)
    authority = resolve_authority(settings, now=observed_at)

    with database.session_scope(session_factory) as session:
        row = session.get(MobileDeviceSessionORM, payload.device_session_id)
        if row is None:
            raise MobileExperienceNotFoundError("Mobile device session not found.")
        # The mobile surface's own owner scope, reused rather than restated: an installation the
        # caller cannot reach is the same answer as one that does not exist, so a stranger
        # learns nothing about whose installations exist. Note that the revoke capability does
        # NOT apply here — it is scoped to that one transition, and nobody may mint a licence
        # for an installation that is not theirs.
        assert_device_session_visible(row, actor=actor)

        refusal_code = _refusal_for(row, payload)
        modules = tuple(
            module
            for module in es.ALL_MODULES
            if module in enabled_modules
            and module in (authority.certificate.get("permitted_modules") or ())
        )
        if refusal_code is None and not modules:
            refusal_code = "no_licensed_modules"

        if refusal_code is not None:
            response = _refusal(
                authority, refusal_code, nonce=payload.exchange_nonce, observed_at=observed_at
            )
            _audit(
                session,
                actor=actor,
                row=row,
                event_type="entitlement.statement.refused",
                message="An offline licence was refused for a registered installation.",
                metadata={
                    "refusal_code": refusal_code,
                    "issuing_key_id": authority.issuing_key_id,
                },
            )
            return response

        statement = _build_statement(
            authority, settings, row=row, payload=payload, observed_at=observed_at, modules=modules
        )
        statement_bytes = es.canonical_bytes(statement)
        statement_signature = es.sign_payload(
            es.STATEMENT_DOMAIN, statement, authority.issuing_seed
        )
        exchange = es.exchange_payload(
            nonce=payload.exchange_nonce,
            observed_at=observed_at,
            issued=True,
            statement_bytes=statement_bytes,
        )
        _audit(
            session,
            actor=actor,
            row=row,
            event_type="entitlement.statement.issued",
            message="An offline licence was issued for a registered installation.",
            # Public key IDS only. Never a seed, never a signature, never the certificate
            # bytes: the audit trail is read by people who are not entitled to key material,
            # and an id is enough to answer which key signed what.
            metadata={
                "statement_id": statement["statement_id"],
                "issuing_key_id": authority.issuing_key_id,
                "licence_class": authority.licence_class,
                "modules": list(modules),
                "package_profiles": list(statement["package_profiles"]),  # type: ignore[arg-type]
                "expires_at": statement["expires_at"],
                "offline_period_days": authority.offline_period_days,
            },
        )
        return EntitlementIssuance(
            issued=True,
            # Built FROM the same dict that was signed, one direction only. Re-serializing the
            # typed object to produce the bytes is the drift this ordering exists to prevent.
            statement=EntitlementStatement(**statement),  # type: ignore[arg-type]
            statement_bytes_b64=es.b64u_encode(statement_bytes),
            statement_signature=statement_signature,
            certificate=EntitlementCertificate(**authority.certificate),  # type: ignore[arg-type]
            certificate_bytes_b64=authority.certificate_b64,
            certificate_signature=authority.certificate_signature,
            root_key_id=authority.root_key_id,
            exchange_nonce=payload.exchange_nonce,
            observed_at=observed_at,
            exchange_signature=es.sign_payload(
                es.EXCHANGE_DOMAIN, exchange, authority.issuing_seed
            ),
        )


def _refusal_for(row: MobileDeviceSessionORM, payload: EntitlementIssuanceRequest) -> str | None:
    if row.status == "revoked":
        return "device_revoked"
    if row.status == "expired":
        return "device_expired"
    if row.device_type != "desktop":
        # An installation that was never registered as a desktop one has not been enrolled for
        # offline use at all — a different answer from one that has, but holds no identity yet.
        return "device_not_enrolled"
    if not row.identity_public_key:
        return "device_identity_key_missing"
    if row.identity_public_key != payload.device_identity_key:
        return "device_identity_key_mismatch"
    return None


def _build_statement(
    authority: EntitlementAuthority,
    settings: Settings,
    *,
    row: MobileDeviceSessionORM,
    payload: EntitlementIssuanceRequest,
    observed_at: datetime,
    modules: tuple[str, ...],
) -> dict[str, object]:
    """Build the canonical payload. Every rule here exists because JSON alone does not enforce it.

    The tenant and deployment identifiers come from the CERTIFICATE, never from the request,
    a header or the body: a request carries no server-derived tenant, so a caller-supplied one
    is not a verifiable claim, and a deployment that could name its own tenant could mint an
    entitlement for a tenant it does not serve.
    """
    expires_at = observed_at + timedelta(hours=authority.statement_validity_hours)
    return {
        "statement_schema": es.STATEMENT_SCHEMA,
        "statement_id": str(uuid.uuid4()),
        "tenant": {
            "tenant_key": str(authority.certificate["tenant_key"]),
            "display_name": (
                settings.entitlement_tenant_display_name
                or str(authority.certificate["tenant_key"])
            ),
        },
        "deployment": {
            "deployment_id": str(authority.certificate["deployment_id"]),
            "workspace_url": settings.base_url,
        },
        "device": {
            "device_id": int(row.id),
            "identity_public_key": str(row.identity_public_key),
        },
        # Sorted into the declared canonical order and deduplicated, so a verifier that
        # re-derives the order gets the same list.
        "modules": list(modules),
        "package_profiles": [
            profile for profile in es.PACKAGE_PROFILES if profile in set(payload.package_profiles)
        ],
        "licence_class": authority.licence_class,
        "issued_at": es.iso_utc(observed_at),
        # Present-and-null for a perpetual licence, never omitted: a field that can disappear
        # is a field an attacker can strip.
        "expires_at": None if authority.licence_class == "perpetual" else es.iso_utc(expires_at),
        "offline_period_days": authority.offline_period_days,
        "issuing_key_id": authority.issuing_key_id,
    }


def _audit(
    session: Session,
    *,
    actor: MobileActor,
    row: MobileDeviceSessionORM,
    event_type: str,
    message: str,
    metadata: dict[str, object],
) -> None:
    session.add(
        database.AuditEventORM(
            event_type=event_type,
            message=message,
            actor_user_id=actor.user_id,
            actor_email=actor.email,
            entity_type="mobile_device_session",
            entity_id=row.id,
            metadata_json=json.dumps(metadata),
        )
    )
