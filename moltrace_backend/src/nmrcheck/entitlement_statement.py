"""Signed offline entitlement statements — canonicalization, signatures, and the chain verifier.

An offline installation cannot call the server to ask whether the customer is still entitled,
and a licence that requires a network callback is rejected by pharmaceutical IT before the
science is ever evaluated. So a deployment issues a **signed statement** the desktop verifies
offline, against a certificate chain rooted in a MolTrace root key pinned in the application.

Two levels: MolTrace holds an offline root and signs one certificate per deployment, binding
that deployment's own issuing sub-key to its deployment and tenant identifiers. The deployment
then signs its own statements locally, so a deployment cut off from the vendor keeps entitling
its own installations.

**This module NEVER gates a read.** Reading, exporting and verifying existing records continues
whatever the entitlement state — a customer is not locked out of their own regulated records by
a commercial term. Nothing here may be turned into a FastAPI dependency;
``tests/test_entitlement_never_gates_reads.py`` fails the build if ``fastapi`` is imported here
or if a ``require_*`` callable appears. That test is a speed bump rather than a proof — a gate
can still be built *elsewhere* out of a module shaped exactly like this one, which is precisely
how ``api._module_licence_gate`` is built out of ``module_access`` — so the control that
actually holds is the behavioural one: twelve cells, four entitlement states by three surfaces,
all of which must keep answering. If you need a gate, you need a different module and a
different conversation.

**On the high-water mark and what it can be trusted for.** The mark this module evaluates lives
in the desktop's local data plane, on hardware the customer — or an attacker with local write
access — controls, and it **cannot be authenticated**. Authenticating it would need a key on
that device, and ``audit_chain.sign_anchor`` states the governing principle for exactly this
case: *a key that verifies is a key that forges*. ``audit_chain``'s own high-water mark is
sealed only because it lives server-side, where the attacker is not present; that precedent does
not cross the trust boundary. So :func:`effective_now` defeats accidental clock skew and casual
tampering, and nothing more. The real bound on a determined local attacker is server-side and is
already in the design: the deployment declines to reissue, and the statement's own expiry caps
how long a rolled-back installation stays useful. Offline entitlement on hardware someone else
controls is a time-bounded risk to be sized, not a threat to be eliminated.

The Ed25519 encoding, the hex-seed key format, the prefix-tagged signature idiom and the byte
canonicalization are all taken from :mod:`nmrcheck.audit_chain` rather than reinvented; this
tree has one signing scheme and one canonical JSON, and ``tests/test_entitlement_statement.py``
pins the serializers byte-equal.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from .module_access import ALL_MODULES, ModuleKey

__all__ = [
    "ALL_MODULES",
    "CERTIFICATE_DOMAIN",
    "EXCHANGE_DOMAIN",
    "ISSUING_KEY_TAG",
    "PACKAGE_PROFILES",
    "ROOT_KEY_TAG",
    "SIGNING_DOMAINS",
    "STATEMENT_DOMAIN",
    "VERIFIER_MESSAGES",
    "VERSION_ASSERTION_DOMAIN",
    "EntitlementDecision",
    "EntitlementKeyError",
    "EntitlementVerifyRefusal",
    "HighWaterMark",
    "accept_issuance",
    "b64u_decode",
    "b64u_encode",
    "canonical_bytes",
    "certificate_payload",
    "effective_now",
    "exchange_payload",
    "iso_utc",
    "parse_iso",
    "public_key_hex_from_seed",
    "public_key_id",
    "sign_payload",
    "signing_input",
    "statement_payload",
    "verify_issuance",
    "verify_payload",
]

# --------------------------------------------------------------------------- vocabularies

#: The five package profiles, in the canonical order a payload builder must emit them.
PACKAGE_PROFILES: tuple[str, ...] = (
    "desktop_shell",
    "scientific_runtime",
    "reference_rule_packs",
    "model_packs",
    "site_integration_packs",
)

LICENCE_CLASSES: tuple[str, ...] = ("commercial", "no_charge", "evaluation", "perpetual")

STATEMENT_SCHEMA = "moltrace.entitlement.statement/1"
CERTIFICATE_SCHEMA = "moltrace.deployment.certificate/1"
EXCHANGE_SCHEMA = "moltrace.entitlement.exchange/1"

# --------------------------------------------------------------------------- domains

# Domain separation. Without these prefixes, a document whose canonical JSON happened to satisfy
# another schema could be presented as that other document; the prefixes are cheap and the
# failure they prevent is total. VERSION_ASSERTION_DOMAIN is signed by the same deployment
# sub-key and verified through the same certificate chain, so it is declared here even though
# the assertion itself is a sibling delta's payload — a domain declared in two places is a
# domain that eventually diverges.
STATEMENT_DOMAIN = b"moltrace-entitlement-statement:v1:"
CERTIFICATE_DOMAIN = b"moltrace-deployment-certificate:v1:"
EXCHANGE_DOMAIN = b"moltrace-entitlement-exchange:v1:"
VERSION_ASSERTION_DOMAIN = b"moltrace-version-assertion:v1:"

SIGNING_DOMAINS: tuple[bytes, ...] = (
    STATEMENT_DOMAIN,
    CERTIFICATE_DOMAIN,
    EXCHANGE_DOMAIN,
    VERSION_ASSERTION_DOMAIN,
)

_ED25519_PREFIX = "ed25519:"

ROOT_KEY_TAG = b"mtroot1:"
ISSUING_KEY_TAG = b"mtdeploy1:"


class EntitlementKeyError(ValueError):
    """The configured entitlement signing key is not a usable Ed25519 seed."""


# --------------------------------------------------------------------------- canonical bytes


def canonical_bytes(payload: Mapping[str, object]) -> bytes:
    """The canonical JSON bytes a signature is taken over.

    Byte-for-byte the serializer the audit chain already uses (``audit_chain._canon``). It is
    restated rather than imported because that name is private, and importing a private name
    across modules invites a refactor to change the entitlement wire format silently. The two
    are pinned byte-equal by test over a fixture set that exercises nesting, lists, integers,
    explicit nulls, non-ASCII and reversed key order.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def signing_input(domain: bytes, payload: Mapping[str, object]) -> bytes:
    """The bytes actually signed: the domain, then the canonical payload.

    The domain is **never stored** alongside the payload bytes. It is prepended here and
    prepended again at verification; a payload that already carried it would be double-prefixed
    and every signature over it would fail.
    """
    return domain + canonical_bytes(payload)


def b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64u_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def iso_utc(moment: datetime) -> str:
    """UTC-ISO with an explicit offset — the single authority for every timestamp that enters a
    signed payload. Never a naive datetime, never a float epoch."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat()


def parse_iso(value: str) -> datetime:
    """Read a timestamp back, accepting the ``Z`` spelling a JSON client may have produced."""
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


# --------------------------------------------------------------------------- keys


def public_key_id(prefix: str, tag: bytes, public_key: str) -> str:
    """A non-secret fingerprint of a **public** key.

    This is the one deliberate difference from ``audit_chain.key_id``, which fingerprints the
    secret: the desktop holds only public material and must be able to compute this itself to
    compare a certificate against the root pinned in its binary, and a fingerprint it cannot
    compute is not a control.

    12 hex characters is 48 bits — a display and rotation-visibility handle, **not** a security
    boundary. The security is the signature verification in :func:`verify_payload`; a matching
    key id authenticates nothing on its own.
    """
    raw = bytes.fromhex(public_key.removeprefix(_ED25519_PREFIX))
    return prefix + hashlib.sha256(tag + raw).hexdigest()[:12]


def _private_key(seed_hex: str | None):  # type: ignore[no-untyped-def]
    """Load the Ed25519 signing key from a hex-encoded 32-byte seed, or None if unset.

    Hex rather than PEM, and the import inside the function, both mirror
    ``audit_chain._anchor_private_key``: the value arrives through the same secret-resolution
    path as every other secret, and a single-line value survives that path without quoting games.
    """
    if not seed_hex:
        return None
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    try:
        seed = bytes.fromhex(seed_hex.strip())
    except ValueError as exc:
        raise EntitlementKeyError("entitlement signing key is not valid hex") from exc
    if len(seed) != 32:
        raise EntitlementKeyError(
            f"entitlement signing key must be a 32-byte seed, got {len(seed)} bytes"
        )
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_hex_from_seed(seed_hex: str | None) -> str | None:
    """The public half, prefixed. Safe to publish; it cannot sign."""
    private = _private_key(seed_hex)
    if private is None:
        return None
    from cryptography.hazmat.primitives import serialization

    raw: bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return _ED25519_PREFIX + raw.hex()


def sign_payload(domain: bytes, payload: Mapping[str, object], seed_hex: str | None) -> str:
    """``"ed25519:" + hex`` — the convention already on every stored audit anchor signature.

    Carrying the algorithm on the value is what let the audit chain add asymmetric signing with
    no migration, and it is why a second scheme could be added here later without one either.
    """
    private = _private_key(seed_hex)
    if private is None:
        raise EntitlementKeyError("no entitlement signing key is configured")
    sealed: bytes = private.sign(signing_input(domain, payload))
    return _ED25519_PREFIX + sealed.hex()


def verify_payload(
    domain: bytes, payload_bytes: bytes, signature: str, public_key: str | None
) -> bool:
    """Verify a signature over ``domain + payload_bytes``. Never raises; a bad input is False."""
    if not public_key or not signature.startswith(_ED25519_PREFIX):
        return False  # an unknown scheme is not a pass
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        raw = bytes.fromhex(public_key.removeprefix(_ED25519_PREFIX))
        Ed25519PublicKey.from_public_bytes(raw).verify(
            bytes.fromhex(signature[len(_ED25519_PREFIX) :]), domain + payload_bytes
        )
    except (InvalidSignature, ValueError):
        return False
    return True


# --------------------------------------------------------------------------- payload builders


def statement_payload(statement: Mapping[str, object]) -> dict[str, object]:
    """Rebuild the canonical statement payload from a typed statement.

    Timestamps are re-normalized through :func:`iso_utc`, so a typed model that rendered a
    timestamp its own way still produces the bytes that were signed. This is what closes the
    drift between the typed object (display material) and the bytes (the fact).
    """
    tenant = dict(statement["tenant"])  # type: ignore[arg-type]
    deployment = dict(statement["deployment"])  # type: ignore[arg-type]
    device = dict(statement["device"])  # type: ignore[arg-type]
    expires_at = statement.get("expires_at")
    return {
        "statement_schema": statement["statement_schema"],
        "statement_id": statement["statement_id"],
        "tenant": {
            "tenant_key": tenant["tenant_key"],
            "display_name": tenant["display_name"],
        },
        "deployment": {
            "deployment_id": deployment["deployment_id"],
            "workspace_url": deployment["workspace_url"],
        },
        "device": {
            "device_id": int(device["device_id"]),  # type: ignore[call-overload]
            "identity_public_key": device["identity_public_key"],
        },
        "modules": list(statement["modules"]),  # type: ignore[arg-type]
        "package_profiles": list(statement["package_profiles"]),  # type: ignore[arg-type]
        "licence_class": statement["licence_class"],
        "issued_at": _as_iso(statement["issued_at"]),
        # Serialized present-and-null, never omitted: a field that can disappear is a field an
        # attacker can strip.
        "expires_at": None if expires_at is None else _as_iso(expires_at),
        "offline_period_days": int(statement["offline_period_days"]),  # type: ignore[call-overload]
        "issuing_key_id": statement["issuing_key_id"],
    }


def certificate_payload(certificate: Mapping[str, object]) -> dict[str, object]:
    """Rebuild the canonical certificate payload from a typed certificate."""
    return {
        "certificate_schema": certificate["certificate_schema"],
        "certificate_id": certificate["certificate_id"],
        "deployment_id": certificate["deployment_id"],
        "tenant_key": certificate["tenant_key"],
        "issuing_public_key": certificate["issuing_public_key"],
        "issuing_key_id": certificate["issuing_key_id"],
        "permitted_modules": list(certificate["permitted_modules"]),  # type: ignore[arg-type]
        "permitted_licence_classes": list(
            certificate["permitted_licence_classes"]  # type: ignore[arg-type]
        ),
        "not_before": _as_iso(certificate["not_before"]),
        "not_after": _as_iso(certificate["not_after"]),
        "root_key_id": certificate["root_key_id"],
    }


def exchange_payload(
    *, nonce: str, observed_at: datetime, issued: bool, statement_bytes: bytes | None
) -> dict[str, object]:
    """The one place a nonce lives.

    It proves *this exchange* happened now, with the deployment holding the sub-key — and then
    the desktop throws it away. It is not inside the statement and is never re-checked, because
    a statement that needed a live challenge could not verify from local storage across an
    offline restart, which is the entire point of the mechanism.
    """
    return {
        "exchange_schema": EXCHANGE_SCHEMA,
        "exchange_nonce": nonce,
        "observed_at": iso_utc(observed_at),
        "issued": issued,
        "statement_digest": (
            None
            if statement_bytes is None
            else "sha256:" + hashlib.sha256(statement_bytes).hexdigest()
        ),
    }


def _as_iso(value: object) -> str:
    if isinstance(value, datetime):
        return iso_utc(value)
    return iso_utc(parse_iso(str(value)))


# --------------------------------------------------------------------------- the decision type

#: What the desktop shows when a stored statement will not verify. Each names its cause, and
#: each restates the hard rule, because this is the screen where a regulated user's first fear
#: is losing their records.
VERIFIER_MESSAGES: dict[str, str] = {
    "unknown_authority": (
        "This offline licence was issued by an authority this application does not recognise. "
        "Your existing records remain available to read, export and verify."
    ),
    "certificate_not_genuine": (
        "This offline licence could not be confirmed as genuine. "
        "Your existing records remain available to read, export and verify."
    ),
    "not_genuine": (
        "This offline licence could not be confirmed as genuine. "
        "Your existing records remain available to read, export and verify."
    ),
    "certificate_expired": (
        "The authorisation behind this offline licence has expired. "
        "Your existing records remain available to read, export and verify."
    ),
    "authority_withdrawn": (
        "The authorisation behind this offline licence has been withdrawn. "
        "Your existing records remain available to read, export and verify."
    ),
    "wrong_workspace": (
        "This offline licence was issued for a different workspace. "
        "Your existing records remain available to read, export and verify."
    ),
    "exceeds_authorisation": (
        "This offline licence claims more than its authorisation allows. "
        "Your existing records remain available to read, export and verify."
    ),
    "wrong_installation": (
        "This offline licence was issued for a different installation. "
        "Your existing records remain available to read, export and verify."
    ),
    "superseded": (
        "A licence older than the one already on this computer was offered, and was not "
        "accepted. Your existing records remain available to read, export and verify."
    ),
}


@dataclass(frozen=True, slots=True)
class EntitlementVerifyRefusal:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class EntitlementDecision:
    """What this installation is additionally permitted to do. Never what it is forbidden.

    The empty decision — ``granted_modules=frozenset()`` — is a **fully working installation**.
    It can open, read, export and verify every record it holds; it simply cannot acquire or
    analyse new data, or install a new package profile. There is no ``blocked``, no ``locked``,
    no ``read_only_denied`` state, and no field a read path could consult to refuse. The type
    makes the lockout unrepresentable rather than merely discouraged, which is why the
    ``granted_`` prefix is load-bearing: a ``denied_modules`` field would reintroduce exactly
    what this shape removes.
    """

    granted_modules: frozenset[ModuleKey]
    granted_package_profiles: frozenset[str]
    licence_class: str | None
    effective_now: datetime
    valid_until: datetime | None
    refusal: EntitlementVerifyRefusal | None = None

    @classmethod
    def empty(
        cls, *, effective_now: datetime, refusal: EntitlementVerifyRefusal | None = None
    ) -> EntitlementDecision:
        return cls(
            granted_modules=frozenset(),
            granted_package_profiles=frozenset(),
            licence_class=None,
            effective_now=effective_now,
            valid_until=None,
            refusal=refusal,
        )


def _refuse(code: str, effective_now: datetime) -> EntitlementDecision:
    return EntitlementDecision.empty(
        effective_now=effective_now,
        refusal=EntitlementVerifyRefusal(code, VERIFIER_MESSAGES[code]),
    )


# --------------------------------------------------------------------------- time


@dataclass(frozen=True, slots=True)
class HighWaterMark:
    """The greatest server-attributable instant this installation has ever accepted.

    It only ever increases under the program's own logic — no code path decreases it: not a
    clock change, not a statement, not a user action, not an administrator action. That is a
    property of *this code*, and it is not a property of the stored row, which lives on hardware
    the attacker controls and carries no authentication. See the module docstring.
    """

    high_water_mark_utc: datetime
    last_issued_at_utc: datetime | None = None
    last_statement_id: str | None = None
    #: The OS monotonic reading when ``high_water_mark_utc`` was written. Comparable with a
    #: later reading only within the same boot session — the monotonic epoch resets at boot.
    monotonic_since_mark: float | None = None
    #: Identifies the boot session the reading above was taken in.
    boot_id: str | None = None

    def advanced(
        self, *, observed_at: datetime | None, issued_at: datetime | None
    ) -> HighWaterMark:
        # Every candidate is forced tz-aware before the comparison: a mark round-tripped
        # through a store that drops the offset would otherwise raise on the max rather than
        # produce a wrong answer, and a crash inside the advance would strand the installation
        # on its old mark.
        candidates = [_aware(self.high_water_mark_utc)]
        if observed_at is not None:
            candidates.append(_aware(observed_at))
        if issued_at is not None:
            candidates.append(_aware(issued_at))
        return replace(self, high_water_mark_utc=max(candidates))


def effective_now(
    *,
    high_water_mark_utc: datetime,
    device_wall_clock: datetime,
    monotonic_now: float | None = None,
    monotonic_since_mark: float | None = None,
    mark_boot_id: str | None = None,
    current_boot_id: str | None = None,
) -> datetime:
    """The instant expiry and grace are evaluated against.

    ``max`` over three terms, and each is there for a reason:

    * ``high_water_mark_utc`` is a **floor**. Whatever the wall clock and the monotonic term
      say, time is never evaluated as earlier than the latest instant this installation has
      already seen attributed to the deployment.
    * ``device_wall_clock`` lets a correct clock run forward normally.
    * ``high_water_mark_utc + elapsed`` makes time genuinely elapsed since the last server
      contact count while the installation is offline, so setting the clock **backwards**
      extends neither the hard expiry nor the grace deadline. Setting it forwards only ever
      brings expiry sooner, which is not an attack.

    ``elapsed`` is included **only when both monotonic readings come from the same boot
    session**. The monotonic epoch resets at boot, so a reading carried across one is not
    comparable with the current reading: the subtraction is meaningless rather than merely
    wrong, and goes negative whenever the mark was written later in the previous boot session
    than the current uptime — which is a condition an attacker arranges by keeping the machine
    up, triggering a refresh, and rebooting.

    Both the floor and the boot check are load-bearing, and they are independent: the floor
    stops a stale anchor from pulling time backwards, and the boot check stops a stale anchor
    from fabricating elapsed time that never happened. Neither substitutes for the other.

    **Scope.** This defeats accidental clock skew and casual tampering. It does not defeat an
    actor with local write access, who can simply edit the stored mark — see the module
    docstring for why nothing local can, and where the real bound lives.
    """
    candidates = [_aware(high_water_mark_utc), _aware(device_wall_clock)]
    same_boot = (
        mark_boot_id is not None
        and current_boot_id is not None
        and mark_boot_id == current_boot_id
    )
    if same_boot and monotonic_now is not None and monotonic_since_mark is not None:
        candidates.append(
            _aware(high_water_mark_utc) + timedelta(seconds=monotonic_now - monotonic_since_mark)
        )
    return max(candidates)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


# --------------------------------------------------------------------------- chain verification


def verify_issuance(
    *,
    statement_bytes: bytes,
    statement_signature: str,
    certificate_bytes: bytes,
    certificate_signature: str,
    pinned_root_public_key: str,
    installation_identity_public_key: str,
    installation_device_id: int,
    effective_now: datetime,
    revoked_issuing_key_ids: frozenset[str] = frozenset(),
    held_statement_issued_at: datetime | None = None,
    held_statement_id: str | None = None,
    high_water_last_issued_at: datetime | None = None,
) -> EntitlementDecision:
    """Verify a statement the way the desktop does offline. **Order matters** — each step
    assumes the previous one passed.

    Monotonicity (step 10) is checked **after** every signature check and before anything is
    persisted, deliberately. Checking it first would let an unsigned blob move the high-water
    mark forward and lock the installation out of every legitimate refresh — a
    denial-of-service by a local attacker who cannot forge a signature.

    Acceptance deliberately does **not** check ``effective_now >= statement.issued_at``: an
    installation whose clock is behind the deployment's would otherwise refuse a freshly-minted
    statement. Advancing the mark on acceptance makes that relation true from then on.
    """
    now = _aware(effective_now)

    try:
        certificate = json.loads(certificate_bytes.decode("utf-8"))
        statement = json.loads(statement_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _refuse("not_genuine", now)
    if not isinstance(certificate, dict) or not isinstance(statement, dict):
        return _refuse("not_genuine", now)

    # 1. Root key id — is this even our authority?
    expected_root = public_key_id("r", ROOT_KEY_TAG, pinned_root_public_key)
    if not hmac.compare_digest(str(certificate.get("root_key_id", "")), expected_root):
        return _refuse("unknown_authority", now)

    # 2. Certificate signature, under the PINNED root — never under whatever the certificate
    #    names, or a forger would only have to name their own key.
    if not verify_payload(
        CERTIFICATE_DOMAIN, certificate_bytes, certificate_signature, pinned_root_public_key
    ):
        return _refuse("certificate_not_genuine", now)

    # 3. Certificate validity window.
    try:
        not_before = parse_iso(str(certificate["not_before"]))
        not_after = parse_iso(str(certificate["not_after"]))
    except (KeyError, ValueError):
        return _refuse("certificate_not_genuine", now)
    if not (not_before <= now <= not_after):
        return _refuse("certificate_expired", now)

    # 4. Certificate revocation, from the list shipped inside the installed application. A
    #    revocation that required a callback would reintroduce the phone-home this whole
    #    mechanism exists to avoid.
    issuing_key_id = str(certificate.get("issuing_key_id", ""))
    if issuing_key_id in revoked_issuing_key_ids:
        return _refuse("authority_withdrawn", now)

    # 5. Statement signature, under the certificate's issuing key.
    issuing_public_key = str(certificate.get("issuing_public_key", ""))
    if not verify_payload(
        STATEMENT_DOMAIN, statement_bytes, statement_signature, issuing_public_key
    ):
        return _refuse("not_genuine", now)

    # 6. Sub-key identity — the statement must name the key that signed it, and that key id
    #    must be the one derivable from the certificate's public key.
    derived = public_key_id("d", ISSUING_KEY_TAG, issuing_public_key)
    if not hmac.compare_digest(str(statement.get("issuing_key_id", "")), issuing_key_id):
        return _refuse("not_genuine", now)
    if not hmac.compare_digest(issuing_key_id, derived):
        return _refuse("not_genuine", now)

    # 7. Binding. This is the step that makes "no deployment can mint an entitlement for any
    #    other deployment" true.
    deployment = statement.get("deployment") or {}
    tenant = statement.get("tenant") or {}
    if not hmac.compare_digest(
        str(deployment.get("deployment_id", "")), str(certificate.get("deployment_id", ""))
    ) or not hmac.compare_digest(
        str(tenant.get("tenant_key", "")), str(certificate.get("tenant_key", ""))
    ):
        return _refuse("wrong_workspace", now)

    # 8. Ceilings. This is the step that stops a compromised deployment self-upgrading its SKU.
    modules = frozenset(statement.get("modules") or ())
    permitted_modules = frozenset(certificate.get("permitted_modules") or ())
    licence_class = str(statement.get("licence_class", ""))
    permitted_classes = frozenset(certificate.get("permitted_licence_classes") or ())
    if not modules <= permitted_modules or licence_class not in permitted_classes:
        return _refuse("exceeds_authorisation", now)

    # 9. Device binding — the anti-replay control that survives an offline restart.
    device = statement.get("device") or {}
    if not hmac.compare_digest(
        str(device.get("identity_public_key", "")), installation_identity_public_key
    ):
        return _refuse("wrong_installation", now)
    if int(device.get("device_id", -1)) != installation_device_id:
        return _refuse("wrong_installation", now)

    # 10. Monotonicity — the other half of the anti-replay control.
    try:
        issued_at = parse_iso(str(statement["issued_at"]))
    except (KeyError, ValueError):
        return _refuse("not_genuine", now)
    statement_id = str(statement.get("statement_id", ""))
    if high_water_last_issued_at is not None and issued_at < _aware(high_water_last_issued_at):
        return _refuse("superseded", now)
    if held_statement_issued_at is not None and issued_at <= _aware(held_statement_issued_at):
        # Re-storing the SAME statement is idempotent: the desktop re-reads its own stored
        # statement on every restart, and that must not look like a replay.
        if statement_id != (held_statement_id or ""):
            return _refuse("superseded", now)

    expires_at_raw = statement.get("expires_at")
    valid_until: datetime | None = None
    if expires_at_raw is not None:
        try:
            valid_until = parse_iso(str(expires_at_raw)) + timedelta(
                days=int(statement.get("offline_period_days", 0))
            )
        except ValueError:
            return _refuse("not_genuine", now)

    return EntitlementDecision(
        granted_modules=frozenset(modules),  # type: ignore[arg-type]
        granted_package_profiles=frozenset(statement.get("package_profiles") or ()),
        licence_class=licence_class,
        effective_now=now,
        valid_until=valid_until,
    )


def accept_issuance(
    *, mark: HighWaterMark | None = None, observed_at: datetime | None = None, **kwargs: object
) -> tuple[EntitlementDecision, HighWaterMark | None]:
    """Verify, and advance the high-water mark **only** on a clean verification.

    The two are one function on purpose. Splitting them is what lets a caller advance the mark
    before the signature is checked, which is the denial-of-service :func:`verify_issuance`
    orders its steps to prevent.
    """
    decision = verify_issuance(**kwargs)  # type: ignore[arg-type]
    if decision.refusal is not None or mark is None:
        return decision, mark

    statement = json.loads(bytes(kwargs["statement_bytes"]).decode("utf-8"))  # type: ignore[arg-type]
    issued_at = parse_iso(str(statement["issued_at"]))
    advanced = mark.advanced(observed_at=observed_at, issued_at=issued_at)
    return decision, replace(
        advanced, last_issued_at_utc=issued_at, last_statement_id=str(statement["statement_id"])
    )
