import json

import pytest
from fastapi.testclient import TestClient

from nmrcheck import tenant_saas_store as tenant_store

PRODUCT_ORDER = ["SpectraCheck", "Regentry", "Reaction Optimization"]
PRODUCT_PROGRAMS = ["spectracheck", "regulatory_hub", "reaction_optimization"]


def _tenant(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/tenants",
        headers=headers,
        json={
            "tenant_key": "pilot-alpha",
            "display_name": "Pilot Alpha",
            "tenant_type": "pilot",
            "status": "onboarding",
            "primary_contact_email": "pilot@example.com",
            "metadata_json": {"pilot_scope": "regulated R&D readiness"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_tenant_environment_entitlement_and_module_order(client, api_headers):
    headers = api_headers
    with client:
        tenant = _tenant(client, headers)

        readiness = client.get(f"/tenants/{tenant['id']}/module-readiness", headers=headers)
        assert readiness.status_code == 200, readiness.text
        assert readiness.json()["product_order"] == PRODUCT_ORDER
        assert [row["program"] for row in readiness.json()["modules"]] == PRODUCT_PROGRAMS

        environment = client.post(
            f"/tenants/{tenant['id']}/environments",
            headers=headers,
            json={
                "environment_type": "validation",
                "base_url": "https://validation.example.test",
                "status": "active",
                "metadata_json": {"region": "us-east-1"},
            },
        )
        assert environment.status_code == 201, environment.text
        assert environment.json()["tenant_id"] == tenant["id"]

        plan = client.post(
            "/subscription-plans",
            headers=headers,
            json={
                "plan_key": "pilot",
                "display_name": "Pilot Plan",
                "description": "Pilot onboarding readiness plan.",
                "default_entitlements_json": {"modules": PRODUCT_PROGRAMS},
            },
        )
        assert plan.status_code == 201, plan.text

        entitlement = client.post(
            f"/tenants/{tenant['id']}/entitlements",
            headers=headers,
            json={
                "plan_id": plan.json()["id"],
                "feature_key": "reaction_optimization.workspace",
                "program": "reaction_optimization",
                "enabled": False,
                "limit_json": {"seats": 3},
            },
        )
        assert entitlement.status_code == 201, entitlement.text

        readiness_after = client.get(f"/tenants/{tenant['id']}/module-readiness", headers=headers)
        assert readiness_after.status_code == 200, readiness_after.text
        body = readiness_after.json()
        assert body["product_order"] == PRODUCT_ORDER
        assert [row["program"] for row in body["modules"]] == PRODUCT_PROGRAMS
        assert body["modules"][2]["readiness_status"] == "disabled_by_entitlement"


def test_pilot_onboarding_seeds_tasks_in_program_order(client, api_headers):
    headers = api_headers
    with client:
        tenant = _tenant(client, headers)
        pilot = client.post(
            f"/tenants/{tenant['id']}/pilot-programs",
            headers=headers,
            json={
                "title": "Spectroscopy to regulatory pilot",
                "objective": "Measure onboarding readiness across core modules.",
                "status": "active",
                "target_programs_json": PRODUCT_PROGRAMS,
                "success_criteria_json": [{"metric": "review required workflow tested"}],
            },
        )
        assert pilot.status_code == 201, pilot.text

        onboarding = client.post(
            f"/tenants/{tenant['id']}/onboarding-projects",
            headers=headers,
            json={
                "pilot_program_id": pilot.json()["id"],
                "title": "Pilot Alpha implementation",
                "status": "in_progress",
                "owner_name": "Implementation Owner",
                "customer_contact": "customer@example.com",
                "implementation_stage": "discovery",
            },
        )
        assert onboarding.status_code == 201, onboarding.text

        tasks = client.get(
            f"/onboarding-projects/{onboarding.json()['id']}/tasks",
            headers=headers,
        )
        assert tasks.status_code == 200, tasks.text
        task_rows = tasks.json()
        assert [row["program"] for row in task_rows[:3]] == PRODUCT_PROGRAMS
        assert [row["title"] for row in task_rows[:3]] == [
            "SpectraCheck setup",
            "Regentry setup",
            "Reaction Optimization setup",
        ]


def test_profiles_usage_roi_procurement_and_audit_are_safe(client, api_headers):
    headers = api_headers
    with client:
        tenant = _tenant(client, headers)

        boundary = client.post(
            f"/tenants/{tenant['id']}/data-boundary",
            headers=headers,
            json={
                "isolation_mode": "dedicated_schema",
                "encryption_profile": "tenant-managed-envelope",
                "storage_prefix": "tenants/pilot-alpha/",
                "allowed_regions_json": ["us-east-1"],
                "status": "active",
            },
        )
        assert boundary.status_code == 201, boundary.text

        security = client.post(
            f"/tenants/{tenant['id']}/security-profile",
            headers=headers,
            json={
                "sso_enabled": True,
                "mfa_required": True,
                "allowed_domains_json": ["example.com"],
                "ip_allowlist_json": ["203.0.113.10/32"],
                "security_frameworks_json": ["SOC2 readiness"],
                "risk_summary_json": {
                    "connector_api_key": "sk-tenant-secret",
                    "full_smiles": "C1=CC=CC=C1O",
                    "summary": "Review network policy.",
                },
                "status": "active",
                "metadata_json": {
                    "raw_spectra": "raw peak text",
                    "password": "super-secret-value",
                },
            },
        )
        assert security.status_code == 201, security.text
        serialized_security = json.dumps(security.json(), sort_keys=True)
        assert "sk-tenant-secret" not in serialized_security
        assert "C1=CC=CC=C1O" not in serialized_security
        assert "raw peak text" not in serialized_security
        assert "super-secret-value" not in serialized_security
        assert security.json()["risk_summary_json"]["connector_api_key"] == "[redacted]"

        validation = client.post(
            f"/tenants/{tenant['id']}/validation-profile",
            headers=headers,
            json={
                "validation_required": True,
                "validation_project_ids_json": [101, 102],
                "controlled_record_policy": "new_version_required_after_lock",
                "esignature_required": True,
                "data_integrity_assessment_ids_json": [201],
                "inspection_package_ids_json": [301],
                "status": "ready_for_review",
            },
        )
        assert validation.status_code == 201, validation.text
        assert validation.json()["validation_project_ids_json"] == [101, 102]

        usage = client.get(f"/tenants/{tenant['id']}/usage-summary", headers=headers)
        assert usage.status_code == 200, usage.text
        usage_text = json.dumps(usage.json(), sort_keys=True).lower()
        assert "raw peak text" not in usage_text
        assert "c1=cc=cc=c1o" not in usage_text
        assert usage.json()["spectracheck_usage_json"]["safe_aggregate_only"] is True

        roi = client.get(f"/tenants/{tenant['id']}/roi", headers=headers)
        assert roi.status_code == 200, roi.text
        assert roi.json()["renewal_summary_json"]["safe_aggregate_only"] is True

        procurement = client.post(
            f"/tenants/{tenant['id']}/procurement-package",
            headers=headers,
            json={
                "title": "Pilot Alpha procurement evidence package",
                "package_type": "full_procurement",
                "metadata_json": {"source_document": "sensitive source body"},
            },
        )
        assert procurement.status_code == 201, procurement.text
        procurement_body = procurement.json()
        assert len(procurement_body["package_sha256"]) == 64
        procurement_text = json.dumps(procurement_body, sort_keys=True)
        assert "sensitive source body" not in procurement_text
        assert "sk-tenant-secret" not in procurement_text
        assert "C1=CC=CC=C1O" not in procurement_text
        assert "raw peak text" not in procurement_text
        assert procurement_body["package_json"]["product_order"] == PRODUCT_ORDER
        assert (
            procurement_body["package_json"]["connector_safety_summary"]["connector_auth_material_included"]
            is False
        )

        audit_export = client.post(
            f"/tenants/{tenant['id']}/audit-export",
            headers=headers,
            json={"export_scope": "all"},
        )
        assert audit_export.status_code == 201, audit_export.text
        assert audit_export.json()["status"] == "succeeded"
        assert len(audit_export.json()["export_sha256"]) == 64

        health = client.get(f"/tenants/{tenant['id']}/health-score", headers=headers)
        assert health.status_code == 200, health.text
        assert health.json()["tenant_id"] == tenant["id"]

        go_live = client.get(f"/tenants/{tenant['id']}/go-live-readiness", headers=headers)
        assert go_live.status_code == 200, go_live.text
        assert go_live.json()["product_order"] == PRODUCT_ORDER


def test_cross_tenant_scope_helper_blocks_mismatch():
    with pytest.raises(tenant_store.TenantIsolationError):
        tenant_store.ensure_tenant_scope(1, 2)
    tenant_store.ensure_tenant_scope(1, 2, is_internal_super_admin=True)


def test_phase64_openapi_includes_tenant_endpoints(client, api_headers):
    headers = api_headers
    with client:
        response = client.get("/openapi.json", headers=headers)
        assert response.status_code == 200, response.text
        paths = response.json()["paths"]
        for path in [
            "/tenants",
            "/tenants/{tenant_id}",
            "/tenants/{tenant_id}/environments",
            "/tenant-environments/{environment_id}",
            "/subscription-plans",
            "/tenants/{tenant_id}/entitlements",
            "/tenant-entitlements/{entitlement_id}",
            "/feature-flags",
            "/tenants/{tenant_id}/pilot-programs",
            "/pilot-programs/{pilot_id}",
            "/tenants/{tenant_id}/onboarding-projects",
            "/onboarding-projects/{project_id}/tasks",
            "/implementation-tasks/{task_id}",
            "/tenants/{tenant_id}/data-boundary",
            "/tenant-data-boundaries/{boundary_id}",
            "/tenants/{tenant_id}/security-profile",
            "/tenant-security-profiles/{profile_id}",
            "/tenants/{tenant_id}/validation-profile",
            "/tenant-validation-profiles/{profile_id}",
            "/tenants/{tenant_id}/usage-summary",
            "/tenants/{tenant_id}/roi",
            "/tenants/{tenant_id}/health-score",
            "/tenants/{tenant_id}/procurement-package",
            "/tenants/{tenant_id}/procurement-packages",
            "/procurement-packages/{package_id}",
            "/tenants/{tenant_id}/audit-export",
            "/tenant-audit-exports/{export_id}",
            "/tenants/{tenant_id}/module-readiness",
            "/tenants/{tenant_id}/go-live-readiness",
        ]:
            assert path in paths
