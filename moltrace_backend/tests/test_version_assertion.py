"""The version catalogue is signed, and cannot be confused with an entitlement statement.

An unsigned version list is forgeable by anything that can write to the local data plane, and an
installation that trusts a forged one will happily emit a regulated result while believing it
matches a deployment it never checked. So the catalogue is signed by the same deployment sub-key
that signs entitlement statements, verified through the same certificate chain, to the same
pinned root — and is a **separate document** with its own lifetime, so a rule-pack release never
touches a commercial credential.

No second crypto scheme is introduced. Same Ed25519, same canonical serializer, same
``"ed25519:" + hex`` encoding, same ``signing_input`` helper — a fourth domain prefix is the
entire difference.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from entitlement_authority import ISSUING_SEED_HEX, valid_authority  # noqa: E402

from nmrcheck import active_versions, audit_chain  # noqa: E402
from nmrcheck import entitlement_statement as es  # noqa: E402
from nmrcheck.version_currency import VersionCoordinate  # noqa: E402


def _coordinates() -> list[VersionCoordinate]:
    return active_versions.active_version_coordinates(None)


def _issuing_public() -> str:
    return es.public_key_hex_from_seed(ISSUING_SEED_HEX)


class _Settings:
    entitlement_issuing_private_key = ISSUING_SEED_HEX


# --------------------------------------------------------------------------------------- T7
def test_assertion_verifies_offline_with_no_exchange_material() -> None:
    """A stored assertion must keep verifying with no network, no nonce and no observed time.

    This is the negative that matters: a nonce cannot be the anti-replay control here, because
    the assertion has to verify from local storage across offline restarts. If this ever needs
    something an offline installation cannot produce, the design has failed.
    """
    coordinates = _coordinates()
    signature = active_versions.sign_version_assertion(_Settings(), coordinates)
    assert signature and signature.startswith("ed25519:")

    payload = active_versions.assertion_payload(coordinates)
    assert active_versions.verify_version_assertion(
        payload=payload, signature=signature, issuing_public_key=_issuing_public()
    )


def test_a_deployment_with_no_issuing_key_serves_an_unsigned_catalogue() -> None:
    """Degraded, not broken. A workspace that licenses no offline installations still answers
    its browser clients; only a client that REQUIRES authentication refuses."""

    class _Unprovisioned:
        entitlement_issuing_private_key = None

    assert active_versions.sign_version_assertion(_Unprovisioned(), _coordinates()) is None


def test_a_tampered_catalogue_stops_verifying() -> None:
    """The whole reason for signing: an edited local copy must not pass."""
    coordinates = _coordinates()
    signature = active_versions.sign_version_assertion(_Settings(), coordinates)
    payload = active_versions.assertion_payload(coordinates)
    payload["versions"][0]["revision"] = "99.0.0"

    assert not active_versions.verify_version_assertion(
        payload=payload, signature=signature, issuing_public_key=_issuing_public()
    )


def test_a_different_deployments_key_does_not_verify() -> None:
    coordinates = _coordinates()
    signature = active_versions.sign_version_assertion(_Settings(), coordinates)
    other = es.public_key_hex_from_seed(bytes(range(96, 128)).hex())

    assert not active_versions.verify_version_assertion(
        payload=active_versions.assertion_payload(coordinates),
        signature=signature,
        issuing_public_key=other,
    )


# --------------------------------------------------------------------------------------- T8
def test_an_entitlement_statement_cannot_be_replayed_as_a_version_assertion() -> None:
    """Both directions, because domain separation that holds one way is not separation.

    Without the fourth prefix a captured version assertion could be presented where a statement
    is expected, or the reverse — the payloads are both plain mappings signed by the same key.
    """
    coordinates = _coordinates()
    version_payload = active_versions.assertion_payload(coordinates)
    # The certificate is the other signed object this key produces; either direction of
    # confusion between it and a version assertion is the failure being pinned.
    statement_payload = valid_authority()["certificate"]

    # A version assertion signed under the STATEMENT domain must not verify as a version one.
    wrong_domain = es.sign_payload(es.STATEMENT_DOMAIN, version_payload, ISSUING_SEED_HEX)
    assert not active_versions.verify_version_assertion(
        payload=version_payload, signature=wrong_domain, issuing_public_key=_issuing_public()
    )

    # ...and a certificate signed under the VERSION domain must not verify as a certificate.
    as_version = es.sign_payload(es.VERSION_ASSERTION_DOMAIN, statement_payload, ISSUING_SEED_HEX)
    assert not es.verify_payload(
        es.CERTIFICATE_DOMAIN,
        es.canonical_bytes(statement_payload),
        as_version,
        _issuing_public(),
    )

    # The certificate and exchange domains are equally closed against it.
    for domain in (es.CERTIFICATE_DOMAIN, es.EXCHANGE_DOMAIN):
        assert not active_versions.verify_version_assertion(
            payload=version_payload,
            signature=es.sign_payload(domain, version_payload, ISSUING_SEED_HEX),
            issuing_public_key=_issuing_public(),
        )


def test_the_version_domain_is_distinct_and_follows_the_established_form() -> None:
    domains = {
        es.STATEMENT_DOMAIN,
        es.CERTIFICATE_DOMAIN,
        es.EXCHANGE_DOMAIN,
        es.VERSION_ASSERTION_DOMAIN,
    }
    assert len(domains) == 4, "two objects share a signing domain"
    assert es.VERSION_ASSERTION_DOMAIN == b"moltrace-version-assertion:v1:"


# --------------------------------------------------------------------------------------- T9
@pytest.mark.parametrize(
    "payload",
    [
        {"b": 1, "a": 2},
        {"nested": {"z": [1, 2, {"k": None}], "a": "é"}},
        {"empty_list": [], "empty_map": {}, "zero": 0, "false": False},
        {"unicode": "Å ± µ", "float": 1.5, "int": 10**12},
    ],
)
def test_canonical_bytes_match_the_audit_chain_serializer(payload: dict) -> None:
    """No second canonicalization. A signature is over bytes, so a serializer that drifted from
    the audit chain's would silently produce signatures nothing else could check."""
    assert es.canonical_bytes(payload) == audit_chain._canon(payload)


def test_the_assertion_payload_is_stable_across_calls() -> None:
    """A signature over a payload whose serialization wandered would fail to verify for no
    reason a person could see."""
    coordinates = _coordinates()
    assert es.canonical_bytes(active_versions.assertion_payload(coordinates)) == es.canonical_bytes(
        active_versions.assertion_payload(coordinates)
    )
