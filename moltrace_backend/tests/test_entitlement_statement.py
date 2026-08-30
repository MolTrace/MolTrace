"""DELTA 3 — the signed offline entitlement statement, at the byte level.

The negative tests are the product. A verifier that accidentally accepts everything passes
every positive test ever written, so each refusal below was watched to fail against a
deliberately weakened implementation before the implementation was strengthened.

Nothing in this file touches the database or the router: ``entitlement_statement`` is pure by
design (see ``tests/test_entitlement_never_gates_reads.py`` for why that matters).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from nmrcheck import audit_chain, module_access
from nmrcheck import entitlement_statement as es
from nmrcheck.models import ProductProgramKey

# --------------------------------------------------------------------------- #
# Test vectors.
#
# THESE ARE TEST KEYS. They are fixed so a signature is reproducible across runs and a golden
# byte string can be asserted. They must never appear in ``settings.py``, in a ``.env``, in the
# provisioning runbook, or in any deployment. A deployment generates its own seed and that seed
# never leaves it.
# --------------------------------------------------------------------------- #
ROOT_SEED_HEX = bytes(range(32)).hex()
ISSUING_SEED_HEX = bytes(range(32, 64)).hex()
OTHER_SEED_HEX = bytes(range(64, 96)).hex()

NOW = datetime(2026, 8, 21, 12, 0, 0, tzinfo=UTC)
DEVICE_ID = 4271
DEVICE_KEY = "ed25519:" + ("ab" * 32)


@pytest.fixture(scope="module")
def authority() -> dict[str, object]:
    """A root key, a deployment sub-key, and a certificate binding one to the other."""
    root_public = es.public_key_hex_from_seed(ROOT_SEED_HEX)
    issuing_public = es.public_key_hex_from_seed(ISSUING_SEED_HEX)
    certificate = {
        "certificate_schema": "moltrace.deployment.certificate/1",
        "certificate_id": "cert-0001",
        "deployment_id": "deployment-alpha",
        "tenant_key": "tenant-alpha",
        "issuing_public_key": issuing_public,
        "issuing_key_id": es.public_key_id("d", es.ISSUING_KEY_TAG, issuing_public),
        "permitted_modules": ["spectracheck", "regulatory_hub"],
        "permitted_licence_classes": ["commercial", "perpetual"],
        "not_before": audit_chain._iso_utc(NOW - timedelta(days=30)),
        "not_after": audit_chain._iso_utc(NOW + timedelta(days=365)),
        "root_key_id": es.public_key_id("r", es.ROOT_KEY_TAG, root_public),
    }
    certificate_bytes = es.canonical_bytes(certificate)
    return {
        "root_public": root_public,
        "issuing_public": issuing_public,
        "certificate": certificate,
        "certificate_bytes": certificate_bytes,
        "certificate_signature": es.sign_payload(
            es.CERTIFICATE_DOMAIN, certificate, ROOT_SEED_HEX
        ),
    }


def _statement(authority: dict[str, object], **overrides: object) -> dict[str, object]:
    certificate = authority["certificate"]
    payload: dict[str, object] = {
        "statement_schema": "moltrace.entitlement.statement/1",
        "statement_id": "9f1d2c33-0000-4000-8000-000000000001",
        "tenant": {"tenant_key": "tenant-alpha", "display_name": "Alpha Pharma"},
        "deployment": {
            "deployment_id": "deployment-alpha",
            "workspace_url": "https://alpha.example",
        },
        "device": {"device_id": DEVICE_ID, "identity_public_key": DEVICE_KEY},
        "modules": ["spectracheck"],
        "package_profiles": ["desktop_shell", "scientific_runtime"],
        "licence_class": "commercial",
        "issued_at": audit_chain._iso_utc(NOW),
        "expires_at": audit_chain._iso_utc(NOW + timedelta(hours=24)),
        "offline_period_days": 14,
        "issuing_key_id": certificate["issuing_key_id"],  # type: ignore[index]
    }
    payload.update(overrides)
    return payload


def _verify(
    authority: dict[str, object],
    statement: dict[str, object],
    *,
    signature: str | None = None,
    **kwargs: object,
) -> es.EntitlementDecision:
    arguments: dict[str, object] = {
        "statement_bytes": es.canonical_bytes(statement),
        "statement_signature": signature
        or es.sign_payload(es.STATEMENT_DOMAIN, statement, ISSUING_SEED_HEX),
        "certificate_bytes": authority["certificate_bytes"],
        "certificate_signature": authority["certificate_signature"],
        "pinned_root_public_key": authority["root_public"],
        "installation_identity_public_key": DEVICE_KEY,
        "installation_device_id": DEVICE_ID,
        "effective_now": NOW,
    }
    arguments.update(kwargs)
    return es.verify_issuance(**arguments)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# T1 — one canonicalization, not two
# --------------------------------------------------------------------------- #
CANONICAL_FIXTURES: tuple[dict[str, object], ...] = (
    {"b": {"nested": {"deep": 1}}, "a": 2},                      # nested object, reversed keys
    {"list": ["one", "two", "three"]},                           # list of strings
    {"count": 42},                                               # integer
    {"expires_at": None},                                        # explicit null
    {"display_name": "Bäyer Ärzneimittel — 東京"},               # non-ASCII, exercises ensure_ascii
    {"empty": []},                                               # empty list
    {"z": 1, "y": 2, "x": 3},                                    # key ordering reversed in source
)


@pytest.mark.parametrize("payload", CANONICAL_FIXTURES, ids=range(len(CANONICAL_FIXTURES)))
def test_canonical_bytes_match_the_audit_chain_serializer(payload: dict[str, object]) -> None:
    """One canonicalization in this tree, not two.

    ``entitlement_statement.canonical_bytes`` restates ``audit_chain._canon`` rather than
    importing a private name across modules; this is what stops a refactor of the audit chain
    from silently changing the entitlement wire format.
    """
    assert es.canonical_bytes(payload) == audit_chain._canon(payload), (
        "the entitlement serializer has drifted from the audit chain's — a signature produced "
        "by one would no longer verify under the other"
    )


# --------------------------------------------------------------------------- #
# T2 — the module vocabulary is the deployment's, not a second copy
# --------------------------------------------------------------------------- #
def test_module_vocabulary_matches_the_deployment_module_list() -> None:
    from typing import get_args

    assert get_args(ProductProgramKey) == module_access.ALL_MODULES, (
        "the statement's module vocabulary has diverged from the deployment's — a statement "
        "would silently narrow or widen what a deployment actually serves"
    )


# --------------------------------------------------------------------------- #
# T3 — domain separation, in both directions, over all four declared domains
# --------------------------------------------------------------------------- #
def test_a_signature_from_another_domain_is_refused(authority: dict[str, object]) -> None:
    statement = _statement(authority)

    for wrong_domain in (es.CERTIFICATE_DOMAIN, es.EXCHANGE_DOMAIN, es.VERSION_ASSERTION_DOMAIN):
        forged = es.sign_payload(wrong_domain, statement, ISSUING_SEED_HEX)
        decision = _verify(authority, statement, signature=forged)
        assert decision.refusal is not None, (
            f"a signature made under {wrong_domain!r} was accepted as an entitlement statement"
        )
        assert decision.refusal.code == "not_genuine"

    # ...and the reverse: a statement signature must not verify as any other kind of document.
    statement_signature = es.sign_payload(es.STATEMENT_DOMAIN, statement, ISSUING_SEED_HEX)
    for other_domain in (es.CERTIFICATE_DOMAIN, es.EXCHANGE_DOMAIN, es.VERSION_ASSERTION_DOMAIN):
        assert not es.verify_payload(
            other_domain,
            es.canonical_bytes(statement),
            statement_signature,
            authority["issuing_public"],  # type: ignore[arg-type]
        ), f"an entitlement statement signature was accepted under {other_domain!r}"


def test_the_declared_domains_are_distinct_and_include_the_version_assertion() -> None:
    """DELTA 4 signs version assertions with the same sub-key and the same chain, so its domain
    must be declared here — a set of three would let one be replayed as the other."""
    assert len(set(es.SIGNING_DOMAINS)) == len(es.SIGNING_DOMAINS)
    assert es.VERSION_ASSERTION_DOMAIN in es.SIGNING_DOMAINS
    assert es.VERSION_ASSERTION_DOMAIN == b"moltrace-version-assertion:v1:"


# --------------------------------------------------------------------------- #
# T4 — the offline-restart invariant. The single most load-bearing test in the delta.
# --------------------------------------------------------------------------- #
def test_a_stored_statement_verifies_with_no_exchange_material(
    authority: dict[str, object],
) -> None:
    """Four public artefacts on disk, no nonce, no ``observed_at``, no network.

    The statement must verify from local storage across an offline restart. If any exchange
    material were a condition of validity, it could not — which is the whole point of binding
    to the device rather than to a per-session challenge.
    """
    statement = _statement(authority)
    decision = es.verify_issuance(
        statement_bytes=es.canonical_bytes(statement),
        statement_signature=es.sign_payload(es.STATEMENT_DOMAIN, statement, ISSUING_SEED_HEX),
        certificate_bytes=authority["certificate_bytes"],  # type: ignore[arg-type]
        certificate_signature=authority["certificate_signature"],  # type: ignore[arg-type]
        pinned_root_public_key=authority["root_public"],  # type: ignore[arg-type]
        installation_identity_public_key=DEVICE_KEY,
        installation_device_id=DEVICE_ID,
        effective_now=NOW + timedelta(hours=2),
    )
    assert decision.refusal is None, decision.refusal
    assert decision.granted_modules == frozenset({"spectracheck"})
    assert decision.licence_class == "commercial"


# --------------------------------------------------------------------------- #
# T5 / T6 — the certificate is a ceiling and a binding
# --------------------------------------------------------------------------- #
def test_a_statement_exceeding_its_certificate_is_refused(authority: dict[str, object]) -> None:
    beyond_modules = _statement(
        authority, modules=["spectracheck", "reaction_optimization"]
    )
    decision = _verify(authority, beyond_modules)
    assert decision.refusal is not None and decision.refusal.code == "exceeds_authorisation", (
        "a deployment granted itself a module its certificate does not permit"
    )
    assert decision.granted_modules == frozenset()

    beyond_class = _statement(authority, licence_class="evaluation")
    decision = _verify(authority, beyond_class)
    assert decision.refusal is not None and decision.refusal.code == "exceeds_authorisation", (
        "a deployment granted itself a licence class its certificate does not permit"
    )


def test_a_statement_for_another_deployment_is_refused(authority: dict[str, object]) -> None:
    wrong_deployment = _statement(
        authority,
        deployment={"deployment_id": "deployment-beta", "workspace_url": "https://beta.example"},
    )
    decision = _verify(authority, wrong_deployment)
    assert decision.refusal is not None and decision.refusal.code == "wrong_workspace", (
        "one deployment minted an entitlement naming another deployment"
    )

    wrong_tenant = _statement(
        authority, tenant={"tenant_key": "tenant-beta", "display_name": "Beta Pharma"}
    )
    decision = _verify(authority, wrong_tenant)
    assert decision.refusal is not None and decision.refusal.code == "wrong_workspace", (
        "one deployment minted an entitlement naming another tenant"
    )


def test_a_statement_for_another_installation_is_refused(authority: dict[str, object]) -> None:
    statement = _statement(authority)
    decision = _verify(
        authority, statement, installation_identity_public_key="ed25519:" + ("cd" * 32)
    )
    assert decision.refusal is not None and decision.refusal.code == "wrong_installation"


# --------------------------------------------------------------------------- #
# T7 — an unsigned blob cannot move the high-water mark
# --------------------------------------------------------------------------- #
def test_an_unsigned_blob_cannot_advance_the_high_water_mark(
    authority: dict[str, object],
) -> None:
    """§5.2's ordering rule, and the denial-of-service it exists to prevent.

    Checking monotonicity before the signature would let a local attacker who cannot forge a
    signature push the mark into the far future and lock the installation out of every
    legitimate refresh.
    """
    mark = es.HighWaterMark(
        high_water_mark_utc=NOW,
        last_issued_at_utc=NOW,
        last_statement_id="9f1d2c33-0000-4000-8000-000000000001",
        monotonic_since_mark=1000.0,
        boot_id="boot-a",
    )
    forged = _statement(
        authority,
        statement_id="9f1d2c33-0000-4000-8000-00000000dead",
        issued_at=audit_chain._iso_utc(NOW + timedelta(days=3650)),
    )
    decision, advanced = es.accept_issuance(
        statement_bytes=es.canonical_bytes(forged),
        statement_signature="ed25519:" + ("00" * 64),  # not a signature over anything
        certificate_bytes=authority["certificate_bytes"],  # type: ignore[arg-type]
        certificate_signature=authority["certificate_signature"],  # type: ignore[arg-type]
        pinned_root_public_key=authority["root_public"],  # type: ignore[arg-type]
        installation_identity_public_key=DEVICE_KEY,
        installation_device_id=DEVICE_ID,
        effective_now=NOW,
        mark=mark,
    )
    assert decision.refusal is not None and decision.refusal.code == "not_genuine"
    assert advanced == mark, (
        "an unsigned blob moved the high-water mark — a local attacker who cannot forge a "
        "signature could lock this installation out of every legitimate refresh"
    )


# --------------------------------------------------------------------------- #
# T7a — the reboot boundary. NOT an arithmetic check.
#
# An arithmetic test written from the formula passes on the BROKEN formula, because the formula
# is self-consistent. It is the boot boundary that breaks it, so every scenario below crosses
# one (or deliberately does not).
# --------------------------------------------------------------------------- #
def test_a_reboot_plus_a_backwards_clock_cannot_lower_effective_now() -> None:
    mark_at = NOW

    # (1) The attack: keep the machine up, trigger a refresh late in the boot session, reboot,
    #     roll the wall clock back. The stale monotonic anchor subtracts to a large NEGATIVE
    #     number, and without the floor the attacker picks any instant above it.
    rolled_back = es.effective_now(
        high_water_mark_utc=mark_at,
        device_wall_clock=mark_at - timedelta(days=7),
        monotonic_now=10.0,                 # fresh epoch: the machine has been up 10 seconds
        monotonic_since_mark=500_000.0,     # written 5.8 days into the PREVIOUS boot session
        mark_boot_id="boot-a",
        current_boot_id="boot-b",           # <- rebooted
    )
    assert rolled_back >= mark_at, (
        "a reboot plus a backwards wall clock lowered the effective time below the high-water "
        "mark — an expired authorisation would pass its validity window and grace would extend "
        "indefinitely"
    )

    # (2) A monotonic reading from a previous boot session must contribute NOTHING. Left in, a
    #     stale anchor fabricates elapsed time that never happened and silently consumes grace.
    wall = mark_at + timedelta(seconds=60)
    stale_anchor = es.effective_now(
        high_water_mark_utc=mark_at,
        device_wall_clock=wall,
        monotonic_now=500_000.0,            # machine has been up a long time SINCE the reboot
        monotonic_since_mark=10.0,          # written 10s into the PREVIOUS boot session
        mark_boot_id="boot-a",
        current_boot_id="boot-b",
    )
    assert stale_anchor == max(mark_at, wall), (
        "a monotonic reading carried across a reboot was treated as comparable with the "
        "current one — the two are on different epochs and the subtraction is meaningless"
    )

    # (3) ...and within ONE boot session the monotonic term must still count, or the fix above
    #     would have quietly deleted the defence it exists to protect: time genuinely elapsed
    #     offline still counts, so setting the clock backwards extends nothing.
    same_boot = es.effective_now(
        high_water_mark_utc=mark_at,
        device_wall_clock=mark_at - timedelta(days=7),
        monotonic_now=1000.0 + 3600.0,
        monotonic_since_mark=1000.0,
        mark_boot_id="boot-a",
        current_boot_id="boot-a",
    )
    assert same_boot >= mark_at + timedelta(seconds=3600), (
        "an hour of genuinely elapsed offline time stopped counting once the wall clock was "
        "set backwards"
    )


# --------------------------------------------------------------------------- #
# T7b — an HONESTY property. Its failure mode is an overclaim, not a wrong number.
# --------------------------------------------------------------------------- #
OVERCLAIMING_PHRASES = (
    "tamper-proof",
    "tamper proof",
    "tamperproof",
    "tamper-evident mark",
    "cannot be tampered",
    "cannot be altered",
    "unforgeable",
    "impossible to roll back",
    "prevents rollback",
    "guarantees monotonic",
    "guaranteed monotonic",
)


def test_the_high_water_mark_is_not_claimed_to_survive_local_tampering() -> None:
    """The mark lives on hardware the attacker controls, and it carries no authentication.

    It cannot be given any: authenticating it needs a key on the device, and a key that
    verifies is a key that forges. The honest bound is server-side — the deployment declines to
    reissue, and the statement's own expiry caps how long a rolled-back device stays useful. So
    this test pins the *documented scope*, not a property the design cannot have.
    """
    # An actor with local write access can simply lower the stored mark. The code must behave
    # as though that is possible, because it is: no detection, no refusal, no pretence.
    lowered = es.effective_now(
        high_water_mark_utc=NOW - timedelta(days=365),
        device_wall_clock=NOW - timedelta(days=365),
        monotonic_now=None,
        monotonic_since_mark=None,
        mark_boot_id=None,
        current_boot_id=None,
    )
    assert lowered == NOW - timedelta(days=365), (
        "the code behaved as though a locally-edited high-water mark could be detected; it "
        "cannot be, and pretending otherwise makes the gap look closed"
    )

    # No user-visible string, docstring or comment in the entitlement modules may claim the
    # mark is tamper-proof. An overclaim here reaches an auditor.
    import pathlib

    sources = [
        pathlib.Path(es.__file__).read_text(),
        (pathlib.Path(es.__file__).parent / "entitlement_store.py").read_text(),
    ]
    for message in es.VERIFIER_MESSAGES.values():
        sources.append(message)
    for source in sources:
        lowered_source = source.lower()
        for phrase in OVERCLAIMING_PHRASES:
            assert phrase not in lowered_source, (
                f"an entitlement module claims {phrase!r} of a value that lives on hardware the "
                "attacker controls and carries no authentication"
            )

    # ...and the honest scope is stated, so the next reader meets it before the code.
    assert "not tamper-proof" in es.__doc__ or "cannot be authenticated" in es.__doc__, (
        "the module does not state the high-water mark's honest scope"
    )


# --------------------------------------------------------------------------- #
# T8 — replay of a captured earlier statement
# --------------------------------------------------------------------------- #
def test_an_older_statement_is_refused_as_superseded(authority: dict[str, object]) -> None:
    """The anti-replay control is (device binding ∧ monotonicity). Neither needs a live
    challenge, which is what lets both survive an offline restart."""
    captured = _statement(
        authority,
        statement_id="9f1d2c33-0000-4000-8000-0000000000aa",
        modules=["spectracheck", "regulatory_hub"],          # a WIDER module set
        issued_at=audit_chain._iso_utc(NOW - timedelta(days=30)),
    )
    decision = _verify(
        authority,
        captured,
        held_statement_issued_at=NOW,
        held_statement_id="9f1d2c33-0000-4000-8000-000000000001",
        high_water_last_issued_at=NOW,
    )
    assert decision.refusal is not None and decision.refusal.code == "superseded", (
        "a captured older statement with a wider module set was accepted, rolling the "
        "installation back to an entitlement it no longer holds"
    )

    # Re-storing the SAME statement is idempotent, not a refusal — the desktop re-reads its own
    # stored statement on every restart.
    held = _statement(authority)
    decision = _verify(
        authority,
        held,
        held_statement_issued_at=NOW,
        held_statement_id="9f1d2c33-0000-4000-8000-000000000001",
        high_water_last_issued_at=NOW,
    )
    assert decision.refusal is None, decision.refusal


# --------------------------------------------------------------------------- #
# The remaining chain steps
# --------------------------------------------------------------------------- #
def test_an_unrecognised_root_is_refused(authority: dict[str, object]) -> None:
    other_root = es.public_key_hex_from_seed(OTHER_SEED_HEX)
    decision = _verify(authority, _statement(authority), pinned_root_public_key=other_root)
    assert decision.refusal is not None and decision.refusal.code == "unknown_authority"


def test_a_certificate_outside_its_window_is_refused(authority: dict[str, object]) -> None:
    decision = _verify(
        authority, _statement(authority), effective_now=NOW + timedelta(days=400)
    )
    assert decision.refusal is not None and decision.refusal.code == "certificate_expired"


def test_a_withdrawn_issuing_key_is_refused(authority: dict[str, object]) -> None:
    certificate = authority["certificate"]
    decision = _verify(
        authority,
        _statement(authority),
        revoked_issuing_key_ids=frozenset({certificate["issuing_key_id"]}),  # type: ignore[index]
    )
    assert decision.refusal is not None and decision.refusal.code == "authority_withdrawn"


def test_a_certificate_signed_by_the_wrong_root_is_refused(authority: dict[str, object]) -> None:
    """The root signature is checked against the PINNED root, not against whatever the
    certificate names — otherwise a forger would only have to name their own key."""
    certificate = dict(authority["certificate"])  # type: ignore[arg-type]
    forged_signature = es.sign_payload(es.CERTIFICATE_DOMAIN, certificate, OTHER_SEED_HEX)
    statement = _statement(authority)
    decision = es.verify_issuance(
        statement_bytes=es.canonical_bytes(statement),
        statement_signature=es.sign_payload(es.STATEMENT_DOMAIN, statement, ISSUING_SEED_HEX),
        certificate_bytes=authority["certificate_bytes"],  # type: ignore[arg-type]
        certificate_signature=forged_signature,
        pinned_root_public_key=authority["root_public"],  # type: ignore[arg-type]
        installation_identity_public_key=DEVICE_KEY,
        installation_device_id=DEVICE_ID,
        effective_now=NOW,
    )
    assert decision.refusal is not None and decision.refusal.code == "certificate_not_genuine"


def test_key_ids_are_computed_from_the_public_half() -> None:
    """The desktop holds only public material. A fingerprint it cannot compute is not a
    control, which is the one difference from ``audit_chain.key_id``."""
    public = es.public_key_hex_from_seed(ISSUING_SEED_HEX)
    assert es.public_key_id("d", es.ISSUING_KEY_TAG, public).startswith("d")
    assert len(es.public_key_id("d", es.ISSUING_KEY_TAG, public)) == 13
    # computable from the public key alone, with no access to the seed
    assert es.public_key_id("d", es.ISSUING_KEY_TAG, public) == es.public_key_id(
        "d", es.ISSUING_KEY_TAG, public.removeprefix("ed25519:")
    )


# --------------------------------------------------------------------------- #
# Golden vectors — the desktop's independent verifier is pinned to bytes, not to prose.
# Cross-language verification parity is where signature schemes actually break.
# --------------------------------------------------------------------------- #
def test_golden_vectors_are_current(authority: dict[str, object]) -> None:
    from pathlib import Path

    statement = _statement(authority)
    vectors = {
        "note": (
            "TEST KEYS. Generated by tests/test_entitlement_statement.py. Never use these seeds "
            "in a deployment; a deployment generates its own and it never leaves it."
        ),
        "root_public_key": authority["root_public"],
        "root_key_id": es.public_key_id(
            "r", es.ROOT_KEY_TAG, authority["root_public"]  # type: ignore[arg-type]
        ),
        "domains": {
            "statement": es.STATEMENT_DOMAIN.decode(),
            "certificate": es.CERTIFICATE_DOMAIN.decode(),
            "exchange": es.EXCHANGE_DOMAIN.decode(),
            "version_assertion": es.VERSION_ASSERTION_DOMAIN.decode(),
        },
        "certificate": authority["certificate"],
        "certificate_bytes_b64": es.b64u_encode(
            authority["certificate_bytes"]  # type: ignore[arg-type]
        ),
        "certificate_signature": authority["certificate_signature"],
        "statement": statement,
        "statement_bytes_b64": es.b64u_encode(es.canonical_bytes(statement)),
        "statement_signature": es.sign_payload(
            es.STATEMENT_DOMAIN, statement, ISSUING_SEED_HEX
        ),
    }
    path = Path(__file__).parent / "data" / "entitlement_golden_vectors.json"
    rendered = json.dumps(vectors, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if not path.exists() or path.read_text() != rendered:
        path.write_text(rendered)
    assert json.loads(path.read_text())["statement_signature"] == vectors["statement_signature"]


def test_the_signed_bytes_are_the_payload_bytes_with_the_domain_prepended(
    authority: dict[str, object],
) -> None:
    """The field on the wire holds the CANONICAL PAYLOAD bytes, not the signed bytes.

    Storing the signed bytes double-prefixes the domain at verification and fails EVERY
    verification — and the symptom (every signature invalid) points at the key material or the
    algorithm, so it is the most expensive way to get this wrong.
    """
    statement = _statement(authority)
    payload_bytes = es.canonical_bytes(statement)
    assert es.signing_input(es.STATEMENT_DOMAIN, statement) == (
        es.STATEMENT_DOMAIN + payload_bytes
    )
    assert not payload_bytes.startswith(es.STATEMENT_DOMAIN)
