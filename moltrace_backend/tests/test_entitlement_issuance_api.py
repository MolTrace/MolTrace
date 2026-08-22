"""DELTA 3 — issuing a signed offline entitlement statement over the wire.

A refusal here is a licensing *answer*, not an error: a refresh that succeeds and returns no
entitlement is a refusal to reissue, and the desktop treats it as revocation rather than as a
fault to retry. Unavailability is the opposite — a misconfigured deployment must never tell a
customer they were revoked.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest
from entitlement_authority import (
    DEPLOYMENT_ID,
    TENANT_KEY,
    expired_authority,
    settings_overrides,
    valid_authority,
)
from fastapi.testclient import TestClient

from nmrcheck import entitlement_statement as es
from nmrcheck import orm

DEVICE_SEED_HEX = bytes(range(96, 128)).hex()
DEVICE_KEY = es.public_key_hex_from_seed(DEVICE_SEED_HEX)
OTHER_DEVICE_KEY = "ed25519:" + ("bc" * 32)
NONCE = "n" * 43


def _signup(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _provision(app, authority=None, **extra) -> dict:
    authority = authority or valid_authority()
    app.state.settings = replace(
        app.state.settings, **settings_overrides(authority, **extra)
    )
    return authority


def _device(client: TestClient, headers: dict[str, str], label: str = "bench") -> int:
    res = client.post(
        "/mobile/device-sessions",
        headers=headers,
        json={"device_label": label, "device_type": "desktop"},
    )
    assert res.status_code == 201, res.text
    return int(res.json()["id"])


def _enrol(client: TestClient, headers: dict[str, str], device_id: int, key: str = DEVICE_KEY):
    return client.patch(
        f"/mobile/device-sessions/{device_id}",
        headers=headers,
        json={"identity_public_key": key},
    )


def _issue(client: TestClient, headers: dict[str, str], device_id: int, **over):
    body = {
        "device_session_id": device_id,
        "device_identity_key": DEVICE_KEY,
        "package_profiles": ["desktop_shell", "scientific_runtime"],
        "exchange_nonce": NONCE,
    }
    body.update(over)
    return client.post("/desktop/entitlement-statements", headers=headers, json=body)


@pytest.fixture()
def enrolled(app, client: TestClient):
    headers = _signup(client, "issuance@example.com")
    _provision(app)
    device_id = _device(client, headers)
    assert _enrol(client, headers, device_id).status_code == 200
    return headers, device_id


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #
def test_an_enrolled_device_receives_a_verifiable_statement(client, enrolled) -> None:
    headers, device_id = enrolled
    response = _issue(client, headers, device_id)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["issued"] is True
    assert body["refusal_code"] is None
    assert body["exchange_nonce"] == NONCE
    assert body["statement"]["device"]["device_id"] == device_id
    assert body["statement"]["deployment"]["deployment_id"] == DEPLOYMENT_ID
    assert body["statement"]["tenant"]["tenant_key"] == TENANT_KEY

    # ...and it verifies through the full chain, from the pinned root down.
    decision = es.verify_issuance(
        statement_bytes=es.b64u_decode(body["statement_bytes_b64"]),
        statement_signature=body["statement_signature"],
        certificate_bytes=es.b64u_decode(body["certificate_bytes_b64"]),
        certificate_signature=body["certificate_signature"],
        pinned_root_public_key=valid_authority()["root_public"],
        installation_identity_public_key=DEVICE_KEY,
        installation_device_id=device_id,
        effective_now=es.parse_iso(body["statement"]["issued_at"]),
    )
    assert decision.refusal is None, decision.refusal
    assert decision.granted_modules == frozenset(es.ALL_MODULES)


def test_the_statement_never_names_a_tenant_the_caller_chose(client, enrolled) -> None:
    """The tenant comes from deployment configuration and is bound by the MolTrace-signed
    certificate. A deployment that could name its own tenant could mint an entitlement for a
    tenant it does not serve."""
    headers, device_id = enrolled
    response = _issue(client, headers, device_id)
    assert response.status_code == 200
    assert response.json()["statement"]["tenant"]["tenant_key"] == TENANT_KEY

    # The request model forbids extras, so a caller cannot smuggle one in.
    smuggled = client.post(
        "/desktop/entitlement-statements",
        headers=headers,
        json={
            "device_session_id": device_id,
            "device_identity_key": DEVICE_KEY,
            "package_profiles": ["desktop_shell"],
            "exchange_nonce": NONCE,
            "tenant_key": "tenant-i-do-not-serve",
        },
    )
    assert smuggled.status_code == 422, smuggled.text


# --------------------------------------------------------------------------- #
# T19 — the typed statement round-trips to the signed bytes
# --------------------------------------------------------------------------- #
def test_the_typed_statement_round_trips_to_the_signed_bytes(client, enrolled) -> None:
    """``statement_bytes_b64`` holds the CANONICAL PAYLOAD bytes, not the signed bytes.

    The signed input is the domain prepended to these bytes, and the domain is prepended again
    at verification. Storing the signed bytes here would double-prefix it and fail EVERY
    verification — with a symptom that points at the key material or the algorithm, nowhere
    near the cause.
    """
    headers, device_id = enrolled
    body = _issue(client, headers, device_id).json()

    decoded = es.b64u_decode(body["statement_bytes_b64"])
    assert not decoded.startswith(es.STATEMENT_DOMAIN), (
        "the domain was stored inside statement_bytes_b64; verification prepends it again and "
        "every signature would fail"
    )
    assert es.canonical_bytes(es.statement_payload(body["statement"])) == decoded

    certificate = es.b64u_decode(body["certificate_bytes_b64"])
    assert not certificate.startswith(es.CERTIFICATE_DOMAIN)
    assert es.canonical_bytes(es.certificate_payload(body["certificate"])) == certificate


# --------------------------------------------------------------------------- #
# T15 — non-leaking 404, never 403
# --------------------------------------------------------------------------- #
def test_issuance_for_a_device_owned_by_another_user_is_not_found(app, client) -> None:
    _provision(app)
    alice = _signup(client, "issuance-alice@example.com")
    bob = _signup(client, "issuance-bob@example.com")
    device_id = _device(client, alice, "alice's bench")
    assert _enrol(client, alice, device_id).status_code == 200

    stranger = _issue(client, bob, device_id)
    nonexistent = _issue(client, bob, 987654)

    assert stranger.status_code == nonexistent.status_code == 404, (
        f"a stranger's request was distinguishable from a nonexistent one: "
        f"{stranger.status_code} vs {nonexistent.status_code}"
    )
    assert stranger.json() == nonexistent.json(), (
        "a stranger learned that someone else's installation exists: "
        f"{stranger.text[:200]} vs {nonexistent.text[:200]}"
    )


# --------------------------------------------------------------------------- #
# T16 — a refusal is an answer, not an error
# --------------------------------------------------------------------------- #
def test_a_revoked_device_is_refused_as_an_answer_not_an_error(app, client, enrolled) -> None:
    headers, device_id = enrolled
    with app.state.session_factory() as session:
        session.get(orm.MobileDeviceSessionORM, device_id).status = "revoked"
        session.commit()

    response = _issue(client, headers, device_id)
    assert response.status_code == 200, (
        "a revocation was reported as an error; the desktop would retry as though a fault had "
        f"occurred instead of standing down: {response.status_code} {response.text[:200]}"
    )
    body = response.json()
    assert body["issued"] is False
    assert body["refusal_code"] == "device_revoked"
    assert body["statement"] is None and body["statement_signature"] is None
    assert body["exchange_nonce"] == NONCE
    assert body["exchange_signature"]


def test_a_device_with_no_identity_key_is_refused_rather_than_implicitly_granted(
    app, client
) -> None:
    _provision(app)
    headers = _signup(client, "unenrolled@example.com")
    device_id = _device(client, headers)

    body = _issue(client, headers, device_id).json()
    assert body["issued"] is False
    assert body["refusal_code"] == "device_identity_key_missing"


def test_a_mismatched_identity_key_is_refused(client, enrolled) -> None:
    headers, device_id = enrolled
    body = _issue(client, headers, device_id, device_identity_key=OTHER_DEVICE_KEY).json()
    assert body["issued"] is False
    assert body["refusal_code"] == "device_identity_key_mismatch"


@pytest.mark.parametrize("unknown_status", ["suspended", "quarantined", "pending", ""])
def test_a_status_this_code_does_not_recognise_is_refused_not_granted(
    app, client, enrolled, unknown_status
) -> None:
    """Fail closed on the status column, because it is not the enum it looks like.

    ``MobileSessionStatus`` constrains what the patch route ACCEPTS. The column is a plain
    ``String(32)`` with no enum and no check constraint, so it constrains nothing about what is
    stored — and the vocabulary can grow. Listing the two bad values and granting everything
    else makes every status anyone adds later a grant by default, and the person adding one to a
    mobile-session vocabulary has no reason to read the entitlement issuer.

    This is the worst place in the delta to fail open: what gets minted is a signed credential
    good for the whole offline period, and withdrawal here is expressed by declining to
    reissue — so once it is out, nothing retracts it.
    """
    headers, device_id = enrolled
    with app.state.session_factory() as session:
        session.get(orm.MobileDeviceSessionORM, device_id).status = unknown_status
        session.commit()

    body = _issue(client, headers, device_id).json()
    assert body["issued"] is False, (
        f"an installation whose status this code does not recognise ({unknown_status!r}) was "
        "issued a signed offline licence — and nothing can retract one"
    )
    assert body["statement"] is None and body["statement_signature"] is None
    # ...and it is not told something that did not happen. It was not withdrawn, and it was
    # not un-enrolled; what is true is that its standing cannot be established.
    assert body["refusal_code"] == "device_not_in_good_standing"


def test_a_deployment_serving_no_products_refuses_rather_than_issuing_an_empty_grant(
    app, client, enrolled
) -> None:
    headers, device_id = enrolled
    app.state.enabled_modules = ()
    try:
        body = _issue(client, headers, device_id).json()
    finally:
        app.state.enabled_modules = es.ALL_MODULES
    assert body["issued"] is False
    assert body["refusal_code"] == "no_licensed_modules"


# --------------------------------------------------------------------------- #
# T17 / T18 — unavailability is never revocation
# --------------------------------------------------------------------------- #
CUSTOMER_REFUSAL_CODES = (
    "device_not_enrolled",
    "device_identity_key_missing",
    "device_identity_key_mismatch",
    "device_revoked",
    "device_expired",
    "no_licensed_modules",
)


def test_an_unprovisioned_deployment_reports_unavailability_not_revocation(app, client) -> None:
    headers = _signup(client, "unprovisioned@example.com")
    app.state.settings = replace(
        app.state.settings,
        entitlement_issuing_private_key=None,
        entitlement_certificate_b64=None,
        entitlement_certificate_signature=None,
        entitlement_offline_period_days=None,
        entitlement_statement_validity_hours=None,
    )
    device_id = _device(client, headers)

    response = _issue(client, headers, device_id)
    assert response.status_code == 503, response.text
    text = response.text
    for code in CUSTOMER_REFUSAL_CODES:
        assert code not in text, (
            f"a misconfigured deployment told a customer {code!r} — a provisioning fault must "
            "never be reported as a licensing decision about them"
        )

    # The operator's cause is delivered where a body CAN carry it. A 5xx body cannot: the
    # shared handler replaces both `detail` and `code` with fixed constants, so the cause
    # travels on the authority route instead.
    admin = _admin_headers(app, client)
    authority = client.get("/desktop/entitlement-authority", headers=admin)
    assert authority.status_code == 200, authority.text
    assert authority.json()["provisioned"] is False
    assert authority.json()["unavailable_code"] == "authority_not_provisioned"


def test_an_unpublished_offline_period_refuses_rather_than_inventing_one(app, client) -> None:
    """No default is substituted. Neither number has been measured, and shipping a
    plausible-looking 30 that nobody chose is exactly the round-number failure this rule
    exists to prevent."""
    headers = _signup(client, "no-period@example.com")
    _provision(app, entitlement_offline_period_days=None)
    device_id = _device(client, headers)
    assert _enrol(client, headers, device_id).status_code == 200

    response = _issue(client, headers, device_id)
    assert response.status_code == 503, response.text

    admin = _admin_headers(app, client)
    authority = client.get("/desktop/entitlement-authority", headers=admin).json()
    assert authority["unavailable_code"] == "offline_period_not_published"
    assert authority["offline_period_days"] is None


def test_an_expired_certificate_is_reported_to_the_operator_as_expired(app, client) -> None:
    headers = _signup(client, "expired-cert@example.com")
    _provision(app, authority=expired_authority())
    device_id = _device(client, headers)
    assert _enrol(client, headers, device_id).status_code == 200

    assert _issue(client, headers, device_id).status_code == 503

    admin = _admin_headers(app, client)
    authority = client.get("/desktop/entitlement-authority", headers=admin).json()
    assert authority["unavailable_code"] == "authority_certificate_expired"


def _admin_headers(app, client: TestClient) -> dict[str, str]:
    email = "entitlement-admin@example.com"
    app.state.settings = replace(app.state.settings, admin_emails=(email,))
    return _signup(client, email)


def test_the_authority_route_never_returns_private_material(app, client) -> None:
    authority = _provision(app)
    admin = _admin_headers(app, client)
    response = client.get("/desktop/entitlement-authority", headers=admin)
    assert response.status_code == 200, response.text
    assert authority["issuing_seed"] not in response.text, (
        "the deployment's issuing seed appeared in an operator diagnostic"
    )
    assert authority["root_seed"] not in response.text
    body = response.json()
    assert body["provisioned"] is True
    assert body["issuing_key_id"].startswith("d")
    assert body["root_key_id"].startswith("r")


def test_the_authority_route_is_admin_only(app, client) -> None:
    _provision(app)
    headers = _signup(client, "not-an-admin@example.com")
    assert client.get("/desktop/entitlement-authority", headers=headers).status_code == 403


# --------------------------------------------------------------------------- #
# T20 — the identity key is write-once
# --------------------------------------------------------------------------- #
def test_the_identity_key_is_write_once(app, client) -> None:
    _provision(app)
    headers = _signup(client, "write-once@example.com")
    device_id = _device(client, headers)

    first = _enrol(client, headers, device_id)
    assert first.status_code == 200, first.text
    assert first.json()["identity_public_key"] == DEVICE_KEY
    assert first.json()["identity_key_enrolled_at"] is not None

    # The same key again is the normal desktop re-enrolment path: idempotent, not a refusal.
    again = _enrol(client, headers, device_id)
    assert again.status_code == 200, again.text
    # Compared as instants, not as strings: a value read back from SQLite renders without the
    # offset a freshly-written one carries, tree-wide and independently of this delta. The
    # statement's own timestamps are immune because they are normalized before they are signed.
    assert es.parse_iso(again.json()["identity_key_enrolled_at"]) == es.parse_iso(
        first.json()["identity_key_enrolled_at"]
    ), "re-registering the same identity moved the enrolment time"

    # A DIFFERENT key is refused, and the refusal names its cause.
    different = _enrol(client, headers, device_id, key=OTHER_DEVICE_KEY)
    assert different.status_code == 400, different.text
    assert "already registered" in different.text.lower(), different.text


# --------------------------------------------------------------------------- #
# Revocation is reachable by the person who has to perform it (C1)
# --------------------------------------------------------------------------- #
def test_an_administrator_can_revoke_a_device_they_do_not_own(app, client) -> None:
    """Revocation whose only route runs through the compromised user's own cooperation is not
    much of a control. The capability is scoped to this ONE transition."""
    _provision(app)
    owner = _signup(client, "revoke-owner@example.com")
    device_id = _device(client, owner, "someone else's bench")
    admin = _admin_headers(app, client)

    revoked = client.patch(
        f"/mobile/device-sessions/{device_id}", headers=admin, json={"status": "revoked"}
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "revoked"


def test_an_administrator_gains_no_other_reach_over_someone_elses_device(app, client) -> None:
    """The capability is scoped to the transition, not to the resource.

    Relaxing the write's visibility predicate instead would have handed an administrator every
    WRITE on any installation — relabelling it, re-pointing whose it is, rewriting its metadata,
    putting a withdrawn one back into service. It would have leaked no reads: that predicate
    guards this one write and gates no read at all.

    The listing assertion below holds for its own reason — that query scopes itself, and always
    did — so it pins that nothing widened there rather than crediting this fix for it.
    """
    _provision(app)
    owner = _signup(client, "reach-owner@example.com")
    device_id = _device(client, owner, "private bench")
    admin = _admin_headers(app, client)

    relabel = client.patch(
        f"/mobile/device-sessions/{device_id}", headers=admin, json={"device_label": "seen"}
    )
    assert relabel.status_code == 404, (
        f"an admin reached a device they do not own for something other than revoking it: "
        f"{relabel.status_code} {relabel.text[:200]}"
    )

    reactivate = client.patch(
        f"/mobile/device-sessions/{device_id}", headers=admin, json={"status": "active"}
    )
    assert reactivate.status_code == 404, (
        "an admin re-activated someone else's device; only the revoke transition was granted"
    )

    listed = client.get("/mobile/device-sessions", headers=admin)
    assert listed.status_code == 200
    assert all(row["id"] != device_id for row in listed.json()), (
        "an admin's device listing now includes another user's devices — that query scopes "
        "itself, so something widened it"
    )


def test_an_administrator_cannot_smuggle_another_write_alongside_the_revocation(
    app, client
) -> None:
    """The capability is the transition, not the field.

    A patch that revokes AND does something else is not the transition the policy engine
    permitted, so owner scope applies to the whole of it. The identity key is why this is not
    pedantry: an offline licence binds to that key, so writing one onto an installation the
    caller does not own hands them that installation's entitlement on hardware of their choosing.

    The exact-set reading is what makes this safe. A membership reading ("status is among the
    fields") admits the whole patch, and the neighbouring reach and stranger tests both stay
    green under it — so nothing else in this file would have caught it.
    """
    _provision(app)
    owner = _signup(client, "smuggle-owner@example.com")
    device_id = _device(client, owner, "the owner's bench")
    admin = _admin_headers(app, client)

    smuggled = client.patch(
        f"/mobile/device-sessions/{device_id}",
        headers=admin,
        json={"status": "revoked", "identity_public_key": OTHER_DEVICE_KEY},
    )
    assert smuggled.status_code == 404, (
        "an administrator revoked AND wrote an identity key onto an installation they do not "
        "own — that key is what an offline licence binds to, so this hands them the "
        f"installation's entitlement: {smuggled.status_code} {smuggled.text[:200]}"
    )

    # Nothing was written on the way to refusing — checked twice, on purpose. The row is
    # ground truth; the owner's own view is what they would actually experience, and it runs
    # through the read mapper, so a refusal that stored the key but failed to surface it would
    # still be caught.
    with app.state.session_factory() as session:
        row = session.get(orm.MobileDeviceSessionORM, device_id)
        assert row.identity_public_key is None, (
            "an identity key was written by a caller who does not own the installation"
        )
        assert row.status == "active", "the smuggled patch also revoked"

    owner_view = next(
        record
        for record in client.get("/mobile/device-sessions", headers=owner).json()
        if record["id"] == device_id
    )
    assert owner_view["status"] != "revoked", "the owner sees their installation withdrawn"
    assert not owner_view["identity_public_key"], (
        "the owner sees an identity key they never registered"
    )

    # The bare transition, from the same caller, still works — the extra field is the guard.
    assert (
        client.patch(
            f"/mobile/device-sessions/{device_id}", headers=admin, json={"status": "revoked"}
        ).status_code
        == 200
    )


def test_a_stranger_still_cannot_revoke_someone_elses_device(app, client) -> None:
    _provision(app)
    owner = _signup(client, "stranger-owner@example.com")
    stranger = _signup(client, "stranger@example.com")
    device_id = _device(client, owner)

    response = client.patch(
        f"/mobile/device-sessions/{device_id}", headers=stranger, json={"status": "revoked"}
    )
    assert response.status_code == 404, response.text


def test_a_revocation_by_someone_other_than_the_owner_names_the_actor(app, client) -> None:
    """Exactly the event an inspector asks about."""
    _provision(app)
    owner = _signup(client, "audited-owner@example.com")
    device_id = _device(client, owner)
    admin_email = "entitlement-admin@example.com"
    admin = _admin_headers(app, client)

    assert (
        client.patch(
            f"/mobile/device-sessions/{device_id}", headers=admin, json={"status": "revoked"}
        ).status_code
        == 200
    )

    with app.state.session_factory() as session:
        rows = (
            session.query(orm.AuditEventORM)
            .filter(orm.AuditEventORM.entity_type == "mobile_device_session")
            .all()
        )
    revocations = [
        row
        for row in rows
        if json.loads(row.metadata_json or "{}").get("status") == "revoked"
    ]
    assert revocations, "the revocation left no audit row"
    row = revocations[-1]
    assert row.actor_email == admin_email, (
        f"the audit row does not name who revoked the device: {row.actor_email!r}"
    )
    assert json.loads(row.metadata_json)["revoked_outside_owner_scope"] is True, (
        "the audit row does not record that this withdrawal was performed by someone the "
        "owner scope would have refused"
    )


def test_an_owner_who_is_also_an_administrator_is_not_recorded_as_acting_outside_their_scope(
    app, client
) -> None:
    """The audit field says what happened, not what role the actor holds.

    An administrator withdrawing their own installation used no capability and crossed no
    scope. Recording them as though they had would put a false statement in front of the
    inspector this field exists to answer.
    """
    _provision(app)
    admin = _admin_headers(app, client)
    device_id = _device(client, admin, "the admin's own bench")

    assert (
        client.patch(
            f"/mobile/device-sessions/{device_id}", headers=admin, json={"status": "revoked"}
        ).status_code
        == 200
    )
    with app.state.session_factory() as session:
        rows = [
            row
            for row in session.query(orm.AuditEventORM).all()
            if row.entity_id == device_id and row.entity_type == "mobile_device_session"
        ]
    revocations = [
        json.loads(row.metadata_json or "{}")
        for row in rows
        if json.loads(row.metadata_json or "{}").get("status") == "revoked"
    ]
    assert revocations, "the withdrawal left no audit row"
    assert revocations[-1]["revoked_outside_owner_scope"] is False


# --------------------------------------------------------------------------- #
# T14 — no key material in the audit trail
# --------------------------------------------------------------------------- #
SIGNATURE_RE = re.compile(r"[0-9a-f]{128}")


def test_no_audit_metadata_contains_key_material(app, client, enrolled) -> None:
    headers, device_id = enrolled
    authority = valid_authority()
    assert _issue(client, headers, device_id).status_code == 200
    with app.state.session_factory() as session:
        session.get(orm.MobileDeviceSessionORM, device_id).status = "revoked"
        session.commit()
    assert _issue(client, headers, device_id).status_code == 200

    with app.state.session_factory() as session:
        blobs = [
            row.metadata_json or "{}"
            for row in session.query(orm.AuditEventORM).all()
            if (row.event_type or "").startswith("entitlement.")
        ]
    assert blobs, "issuance and refusal left no audit trail"
    for blob in blobs:
        assert authority["issuing_seed"] not in blob, "the issuing seed reached the audit trail"
        assert authority["certificate_b64"] not in blob
        assert not SIGNATURE_RE.search(blob), (
            f"a 128-hex signature reached the audit trail: {blob[:200]}"
        )


# --------------------------------------------------------------------------- #
# T21 — no wire vocabulary in anything a person reads
# --------------------------------------------------------------------------- #
HTTP_VERBS = ("GET ", "POST ", "PATCH ", "PUT ", "DELETE ")
WIRE_SUFFIXES = ("_json", "_id", "_at", "_b64")


def _assert_human(label: str, message: str) -> None:
    assert "backend" not in message.lower(), f"{label}: names the backend"
    assert not re.search(r"(?<![\w.])/[a-z][\w./{}-]*", message), (
        f"{label}: contains an endpoint path — {message!r}"
    )
    assert not any(verb in message.upper() for verb in HTTP_VERBS), f"{label}: names an HTTP verb"
    assert not re.search(r"\b[1-5]\d{2}\b", message), f"{label}: names a status code — {message!r}"
    for suffix in WIRE_SUFFIXES:
        assert not re.search(rf"\w+{suffix}\b", message), (
            f"{label}: names a wire field ({suffix}) — {message!r}"
        )


def test_no_user_visible_string_contains_wire_vocabulary() -> None:
    from nmrcheck.models import ENTITLEMENT_REFUSAL_DETAILS, ENTITLEMENT_UNAVAILABLE_DETAILS

    for code, message in ENTITLEMENT_REFUSAL_DETAILS.items():
        _assert_human(f"refusal {code}", message)
    for code, message in ENTITLEMENT_UNAVAILABLE_DETAILS.items():
        _assert_human(f"unavailable {code}", message)
    for code, message in es.VERIFIER_MESSAGES.items():
        _assert_human(f"verifier {code}", message)


def _settings(**over):
    from nmrcheck.settings import Settings

    base = dict(app_env="production", api_key="x", sso_encryption_key="x", mfa_encryption_key="x")
    base.update(over)
    return Settings(**base)


def test_a_deployment_that_licenses_no_offline_installations_starts_silently() -> None:
    """Silence is a valid answer. Most deployments license no offline installations, and a
    diagnostic they can do nothing about is noise that teaches people to ignore the log."""
    from nmrcheck.settings import validate_startup_settings

    issues = [
        issue
        for issue in validate_startup_settings(_settings())
        if "offline" in issue.lower() or "licens" in issue.lower()
    ]
    assert issues == [], issues


def test_a_half_provisioned_issuer_is_a_startup_issue() -> None:
    """Deliberately NOT gated on the environment, unlike the neighbouring checks.

    Those ask "is this secret set in production?" — a question only production can answer wrong.
    This one asks "do these settings agree with each other?", which is wrong everywhere, and it
    only speaks at all once a deployment has declared itself an issuer. Startup issues are
    logged rather than fatal, so surfacing it early costs nothing and saves a developer from
    meeting the same fault later as a licence refusal with a deliberately generic body.
    """
    from nmrcheck.settings import validate_startup_settings

    authority = valid_authority()

    key_without_certificate = validate_startup_settings(
        _settings(entitlement_issuing_private_key=authority["issuing_seed"])
    )
    assert any("incomplete" in issue.lower() for issue in key_without_certificate)

    certificate_without_signature = validate_startup_settings(
        _settings(
            entitlement_issuing_private_key=authority["issuing_seed"],
            entitlement_certificate_b64=authority["certificate_b64"],
        )
    )
    assert any("incomplete" in issue.lower() for issue in certificate_without_signature)

    # A signature that does not verify is a different fault and must say so, not "incomplete".
    bad_signature = validate_startup_settings(
        _settings(
            **{
                **settings_overrides(authority),
                "entitlement_certificate_signature": "ed25519:" + ("00" * 64),
            }
        )
    )
    assert any("genuine" in issue.lower() for issue in bad_signature), bad_signature

    # ...and a correctly provisioned issuer says nothing at all.
    assert [
        issue
        for issue in validate_startup_settings(_settings(**settings_overrides(authority)))
        if "offline" in issue.lower() or "licens" in issue.lower()
    ] == []


def test_no_startup_issue_string_contains_wire_vocabulary() -> None:
    from nmrcheck.settings import Settings, validate_startup_settings

    half_provisioned = Settings(
        app_env="production",
        api_key="x",
        sso_encryption_key="x",
        mfa_encryption_key="x",
        hose_kb_path=None,
        entitlement_issuing_private_key=bytes(range(32, 64)).hex(),
    )
    issues = [
        issue for issue in validate_startup_settings(half_provisioned) if "offline" in issue.lower()
        or "licens" in issue.lower()
    ]
    assert issues, "a half-provisioned issuer produced no startup issue"
    for issue in issues:
        _assert_human("startup issue", issue)
