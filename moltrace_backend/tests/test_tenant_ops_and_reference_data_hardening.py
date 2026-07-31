"""Layer 0.A of the standalone-modules program: close the holes that make licensing enforceable.

Three of these were live: (1) the tenant-operations surface accepted any authenticated caller who
echoed the path's tenant id back in an ``x-tenant-id`` header, so a customer could read another
tenant's records and mint their own entitlement rows; (2) regulatory reference data is global and
unowned, so any authenticated user could publish an "active" rule set that changed *other* users'
assessment verdicts; (3) a report's stored fingerprint was taken from the request body when the
caller supplied one, so a report and its digest could disagree by design.

A module licence check is only as trustworthy as the surface that grants the licence, so these
land before any entitlement becomes load-bearing.
"""

import hashlib
import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from nmrcheck import models


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _tenant(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/tenants",
        headers=headers,
        json={
            "tenant_key": "hardening-alpha",
            "display_name": "Hardening Alpha",
            "tenant_type": "pilot",
            "status": "onboarding",
            "primary_contact_email": "ops@example.com",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# Tenant operations surface
# --------------------------------------------------------------------------- #
def test_user_cannot_mint_entitlements_with_a_self_asserted_tenant_header(client, api_headers):
    """The headline hole: an ``x-tenant-id`` matching the path is not proof of anything."""
    with client:
        tenant = _tenant(client, api_headers)
        user = _sign_up(client, "customer@example.com")
        spoofed = {**user, "x-tenant-id": str(tenant["id"])}

        res = client.post(
            f"/tenants/{tenant['id']}/entitlements",
            headers=spoofed,
            json={"program": "regulatory_hub", "feature_key": "regulatory_hub", "enabled": True},
        )
        assert res.status_code == 403, res.text

        # And the write really did not happen.
        listed = client.get(f"/tenants/{tenant['id']}/entitlements", headers=api_headers)
        assert listed.status_code == 200, listed.text
        assert listed.json() == []


def test_user_cannot_read_another_tenants_records_with_a_self_asserted_header(client, api_headers):
    with client:
        tenant = _tenant(client, api_headers)
        user = _sign_up(client, "reader@example.com")
        spoofed = {**user, "x-tenant-id": str(tenant["id"])}

        for path in (
            f"/tenants/{tenant['id']}",
            f"/tenants/{tenant['id']}/entitlements",
            f"/tenants/{tenant['id']}/security-profile",
            f"/tenants/{tenant['id']}/module-readiness",
        ):
            res = client.get(path, headers=spoofed)
            assert res.status_code == 403, f"{path} -> {res.status_code} {res.text}"


def test_operator_retains_full_tenant_operations_access(client, api_headers):
    """The gate must close the hole without breaking internal tenant ops."""
    with client:
        tenant = _tenant(client, api_headers)

        created = client.post(
            f"/tenants/{tenant['id']}/entitlements",
            headers=api_headers,
            json={"program": "spectracheck", "feature_key": "spectracheck", "enabled": True},
        )
        assert created.status_code == 201, created.text

        readiness = client.get(f"/tenants/{tenant['id']}/module-readiness", headers=api_headers)
        assert readiness.status_code == 200, readiness.text


def test_operator_header_still_guards_against_a_mis_targeted_tenant(client, api_headers):
    """A supplied header is a consistency check: it must agree with the path it accompanies."""
    with client:
        tenant = _tenant(client, api_headers)
        mismatched = {**api_headers, "x-tenant-id": str(tenant["id"] + 1000)}

        res = client.get(f"/tenants/{tenant['id']}/entitlements", headers=mismatched)
        assert res.status_code == 403, res.text


# --------------------------------------------------------------------------- #
# Global regulatory reference data
# --------------------------------------------------------------------------- #
def test_user_cannot_publish_global_regulatory_reference_data(client, api_headers):
    """Rule sets and jurisdictions are global: one user's write changes everyone's verdicts."""
    with client:
        user = _sign_up(client, "chemist@example.com")

        jurisdiction = client.post(
            "/regulatory/jurisdictions",
            headers=user,
            json={"name": "Elsewhere", "country_code": "ZZ", "authority_name": "ZZA"},
        )
        assert jurisdiction.status_code == 403, jurisdiction.text

        # A well-formed body, so the 403 is an authorization decision and not a validation
        # rejection that happens to arrive first.
        rule_set = client.post(
            "/regulatory/rule-sets",
            headers=user,
            json={"name": "Rogue limits", "version": "1.0", "status": "active"},
        )
        assert rule_set.status_code == 403, rule_set.text


def test_operator_can_still_publish_regulatory_reference_data(client, api_headers):
    with client:
        res = client.post(
            "/regulatory/jurisdictions",
            headers=api_headers,
            json={"name": "Elsewhere", "country_code": "ZZ", "authority_name": "ZZA"},
        )
        assert res.status_code == 201, res.text


# --------------------------------------------------------------------------- #
# Report fingerprint integrity
# --------------------------------------------------------------------------- #
def _session(client: TestClient, headers: dict[str, str]) -> dict:
    project = client.post(
        "/projects", headers=headers, json={"name": "Fingerprint study"}
    )
    assert project.status_code == 201, project.text
    sample = client.post(
        f"/projects/{project.json()['id']}/samples",
        headers=headers,
        json={"sample_id": "MT-FP-001", "display_name": "Fraction A"},
    )
    assert sample.status_code == 201, sample.text
    session = client.post(
        "/spectracheck/sessions",
        headers=headers,
        json={
            "project_id": project.json()["id"],
            "sample_pk": sample.json()["id"],
            "sample_id": sample.json()["sample_id"],
            "title": "Fingerprint session",
        },
    )
    assert session.status_code == 201, session.text
    return session.json()


def test_report_fingerprint_is_always_the_server_computation(client, api_headers):
    report_json = {"verdict": "pass", "purity_percent": 99.1}
    expected = hashlib.sha256(
        json.dumps(report_json, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    with client:
        session = _session(client, api_headers)

        res = client.post(
            f"/spectracheck/sessions/{session['id']}/reports",
            headers=api_headers,
            json={"report_title": "Evidence report", "report_json": report_json},
        )
        assert res.status_code == 201, res.text
        assert res.json()["report_sha256"] == expected


def test_a_report_fingerprint_that_disagrees_with_the_body_is_rejected(client, api_headers):
    with client:
        session = _session(client, api_headers)

        res = client.post(
            f"/spectracheck/sessions/{session['id']}/reports",
            headers=api_headers,
            json={
                "report_title": "Tampered report",
                "report_json": {"verdict": "pass", "purity_percent": 99.1},
                "report_sha256": "0" * 64,
            },
        )
        assert res.status_code == 400, res.text
        assert "fingerprint" in res.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# Vocabulary invariant
# --------------------------------------------------------------------------- #
def test_every_action_type_the_compliance_store_writes_is_a_declared_action_type():
    """``elemental_impurity_review`` was written by the store but absent from the response type,
    so a single ICH Q3D assessment made the whole action-item list permanently unreadable. This
    pins the class of bug rather than the one instance."""
    store = Path(__file__).resolve().parents[1] / "src" / "nmrcheck" / "regulatory_compliance_store.py"
    written = set(re.findall(r'action_type="([a-z_]+)"', store.read_text()))
    assert written, "expected the compliance store to raise action items"

    declared = set(models.RegulatoryActionType.__args__)
    assert written <= declared, f"action types written but not declared: {sorted(written - declared)}"
