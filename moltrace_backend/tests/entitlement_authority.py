"""A provisioned entitlement authority, for tests that need one.

THESE ARE TEST KEYS. The seeds below are fixed so signatures are reproducible across runs and a
golden byte string can be asserted. They must never appear in ``settings.py``, in a ``.env``, in
``docs/entitlement_provisioning.md``, or in any deployment: a deployment generates its own
issuing seed and that seed never leaves it, and the root seed lives offline in the founder's
custody and signs nothing but certificates.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nmrcheck import audit_chain
from nmrcheck import entitlement_statement as es

ROOT_SEED_HEX = bytes(range(32)).hex()
ISSUING_SEED_HEX = bytes(range(32, 64)).hex()

DEPLOYMENT_ID = "deployment-under-test"
TENANT_KEY = "tenant-under-test"
TENANT_DISPLAY_NAME = "Tenant Under Test"
WORKSPACE_URL = "https://workspace.example"


def _authority(*, not_before: datetime, not_after: datetime, **overrides: object) -> dict:
    root_public = es.public_key_hex_from_seed(ROOT_SEED_HEX)
    issuing_public = es.public_key_hex_from_seed(ISSUING_SEED_HEX)
    certificate: dict[str, object] = {
        "certificate_schema": "moltrace.deployment.certificate/1",
        "certificate_id": "cert-under-test",
        "deployment_id": DEPLOYMENT_ID,
        "tenant_key": TENANT_KEY,
        "issuing_public_key": issuing_public,
        "issuing_key_id": es.public_key_id("d", es.ISSUING_KEY_TAG, issuing_public),
        "permitted_modules": list(es.ALL_MODULES),
        "permitted_licence_classes": ["commercial", "no_charge", "evaluation", "perpetual"],
        "not_before": audit_chain._iso_utc(not_before),
        "not_after": audit_chain._iso_utc(not_after),
        "root_key_id": es.public_key_id("r", es.ROOT_KEY_TAG, root_public),
    }
    certificate.update(overrides)
    certificate_bytes = es.canonical_bytes(certificate)
    return {
        "root_seed": ROOT_SEED_HEX,
        "issuing_seed": ISSUING_SEED_HEX,
        "root_public": root_public,
        "issuing_public": issuing_public,
        "certificate": certificate,
        "certificate_bytes": certificate_bytes,
        "certificate_b64": es.b64u_encode(certificate_bytes),
        "certificate_signature": es.sign_payload(
            es.CERTIFICATE_DOMAIN, certificate, ROOT_SEED_HEX
        ),
    }


def valid_authority(**overrides: object) -> dict:
    now = datetime.now(UTC)
    return _authority(
        not_before=now - timedelta(days=1), not_after=now + timedelta(days=365), **overrides
    )


def expired_authority(**overrides: object) -> dict:
    now = datetime.now(UTC)
    return _authority(
        not_before=now - timedelta(days=400), not_after=now - timedelta(days=1), **overrides
    )


def settings_overrides(authority: dict, **extra: object) -> dict:
    """The five deployment settings a provisioned issuer carries."""
    values: dict[str, object] = {
        "entitlement_issuing_private_key": authority["issuing_seed"],
        "entitlement_certificate_b64": authority["certificate_b64"],
        "entitlement_certificate_signature": authority["certificate_signature"],
        "entitlement_root_public_key": authority["root_public"],
        "entitlement_offline_period_days": 14,
        "entitlement_statement_validity_hours": 24,
        # The certificate permits four classes, so the deployment must say which one it issues
        # under — an ambiguous authorisation is declined rather than resolved by guessing.
        "entitlement_licence_class": "commercial",
        "entitlement_tenant_display_name": TENANT_DISPLAY_NAME,
    }
    values.update(extra)
    return values
