"""Endpoint tests for the Prompt 18 MLOps admin surface (GET /admin/ops/*).

Covers: the fail-closed deployment-gate status, the registry-backed model-lineage
dashboard (empty until a registry is wired, populated when it is), admin gating,
and the OpenAPI contract the FE dashboard is generated from.
"""


def test_deployment_gate_status(client, api_headers):
    res = client.get("/admin/ops/deployment-gate", headers=api_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["fails_closed"] is True
    assert body["self_check_passed"] is True
    assert body["self_check_failures"] == []
    assert {c["name"] for c in body["checks"]} == {
        "dominance",
        "audit_chain",
        "tests_green",
        "data_leakage",
    }
    assert body["output_contract_schema_version"] == "1.0.0"
    assert body["monitoring_thresholds"]["psi_breach"] == 0.25
    assert body["monitoring_thresholds"]["slo_p95_ms"] == 2000.0


def test_model_lineage_empty_until_registry_wired(client, api_headers):
    res = client.get("/admin/ops/model-lineage", headers=api_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["registry_configured"] is False
    assert body["rows"] == []
    assert body["note"]  # explains how it populates


def test_model_lineage_reads_registry_when_wired(client, api_headers):
    from moltrace.spectroscopy.ai.registry import (
        ModelRegistry,
        ModelRole,
        TrainingDataLineage,
    )

    registry = ModelRegistry()
    entry = registry.register_artifact(
        role=ModelRole.LORA_ADAPTER,
        nucleus="13C",
        semantic_version="1.0.0",
        artifact_sha256="sha256:adapter-abc",
        training_data_lineage=TrainingDataLineage(
            dataset_snapshot_hash="sha256:snap-1", row_count=1000
        ),
        metric_snapshot={"top1_accuracy": 0.91},
    )
    registry.promote(entry.model_id, reason="dominance gate passed")
    previous = getattr(client.app.state, "model_registry", None)
    client.app.state.model_registry = registry
    try:
        res = client.get("/admin/ops/model-lineage", headers=api_headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["registry_configured"] is True
        assert len(body["rows"]) == 1
        row = body["rows"][0]
        assert row["model_id"] == entry.model_id
        assert row["training_snapshot_hash"] == "sha256:snap-1"
        assert row["metric_vector"]["top1_accuracy"] == 0.91
        assert row["promotion_reason"] == "dominance gate passed"
        assert row["drift_status"] == "unknown"
    finally:
        # The app is shared per xdist worker; restore so this wiring doesn't
        # leak into other tests that expect an unconfigured registry.
        client.app.state.model_registry = previous


def test_ops_endpoints_require_admin(client):
    for path in ("/admin/ops/deployment-gate", "/admin/ops/model-lineage"):
        res = client.get(path)  # no credentials
        assert res.status_code in (401, 403), f"{path} -> {res.status_code}: {res.text}"


def test_ops_endpoints_in_openapi(openapi_schema):
    spec = openapi_schema
    assert "/admin/ops/deployment-gate" in spec["paths"]
    assert "/admin/ops/model-lineage" in spec["paths"]
    schemas = spec["components"]["schemas"]
    assert "OpsDeploymentGateStatus" in schemas
    assert "OpsDeploymentGateCheck" in schemas
    assert "OpsModelLineageResponse" in schemas
    assert "OpsModelLineageRow" in schemas
