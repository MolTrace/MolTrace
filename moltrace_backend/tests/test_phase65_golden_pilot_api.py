import json

from fastapi.testclient import TestClient

PRODUCT_ORDER = ["SpectraCheck", "ComplianceCore", "Reaction Optimization"]


def _tenant(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/tenants",
        headers=headers,
        json={
            "tenant_key": "golden-pilot-alpha",
            "display_name": "Golden Pilot Alpha",
            "tenant_type": "pilot",
            "status": "onboarding",
            "primary_contact_email": "pilot@example.com",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _dataset(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/pilot/golden-datasets",
        headers=headers,
        json={
            "dataset_key": "demo-spectracheck-regulatory-reaction",
            "title": "Demo SpectraCheck to Regulatory to Reaction dataset",
            "description": "Curated demo/test data for golden scenario execution.",
            "dataset_type": "cross_module",
            "source_type": "synthetic_demo",
            "status": "ready_for_review",
            "source_references_json": [{"source": "internal demo fixture", "citation_required": False}],
            "file_ids_json": [101],
            "artifact_ids_json": [201],
            "metadata_json": {
                "raw_spectra": "raw peak text must not be exposed",
                "full_smiles": "C1=CC=CC=C1O",
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["metadata_json"]["data_label"] == "demo/test data"
    assert body["metadata_json"]["raw_spectra"] == "[redacted]"
    assert body["metadata_json"]["full_smiles"] == "[redacted]"
    return body


def _scenario(client: TestClient, headers: dict[str, str], dataset_id: int, *, missing_endpoint: bool = False) -> dict:
    response = client.post(
        "/pilot/scenarios",
        headers=headers,
        json={
            "scenario_key": "full-product-golden-flow" if not missing_endpoint else "missing-endpoint-flow",
            "title": "Full product golden scenario",
            "description": "Golden scenario for pilot acceptance across the three core programs.",
            "scenario_type": "full_product_workflow",
            "dataset_ids_json": [dataset_id],
            "required_inputs_json": {"sample_id": "demo-sample"},
            "expected_outputs_json": {"simulate_missing_endpoint": missing_endpoint},
            "acceptance_criteria_json": [{"criterion": "review required evidence bundle is produced"}],
            "status": "ready_for_review",
            "metadata_json": {"missing_endpoint": missing_endpoint},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["program_sequence_json"] == PRODUCT_ORDER
    return body


def test_golden_dataset_scenario_contract_run_validation_and_bundle(client, api_headers):
    headers = api_headers
    with client:
        tenant = _tenant(client, headers)
        dataset = _dataset(client, headers)
        scenario = _scenario(client, headers, dataset["id"])

        workflow_case = client.post(
            f"/pilot/scenarios/{scenario['id']}/workflow-cases",
            headers=headers,
            json={
                "case_key": "happy-path",
                "title": "Happy path pilot case",
                "input_payload_json": {"sample_id": "demo-sample"},
                "expected_step_order_json": PRODUCT_ORDER,
                "expected_resource_links_json": [{"relation": "evidence_for"}],
                "expected_warnings_json": [],
            },
        )
        assert workflow_case.status_code == 201, workflow_case.text
        assert workflow_case.json()["scenario_id"] == scenario["id"]

        contract = client.post(
            f"/pilot/scenarios/{scenario['id']}/expected-output-contracts",
            headers=headers,
            json={
                "step_key": "spectracheck_evidence_generation",
                "target_module": "spectracheck",
                "expected_output_type": "evidence_item",
                "required_fields_json": ["evidence_item.status", "review_status"],
                "forbidden_fields_json": ["secret", "raw_spectra"],
                "expected_statuses_json": ["succeeded"],
            },
        )
        assert contract.status_code == 201, contract.text

        seed = client.post(
            f"/pilot/scenarios/{scenario['id']}/seed-tenant",
            headers=headers,
            json={"tenant_id": tenant["id"], "seed_type": "full_product_demo"},
        )
        assert seed.status_code == 201, seed.text
        assert seed.json()["status"] == "succeeded"
        assert seed.json()["created_resource_ids_json"]["product_order"] == PRODUCT_ORDER

        run = client.post(
            f"/pilot/scenarios/{scenario['id']}/run",
            headers=headers,
            json={"tenant_id": tenant["id"], "run_label": "Pilot acceptance dry run"},
        )
        assert run.status_code == 201, run.text
        run_body = run.json()
        assert run_body["status"] == "succeeded"
        assert run_body["summary_json"]["product_order"] == PRODUCT_ORDER
        assert [step["module"] for step in run_body["steps"][:3]] == [
            "spectracheck",
            "regulatory_hub",
            "reaction_optimization",
        ]

        validation = client.post(f"/pilot/runs/{run_body['id']}/validate", headers=headers)
        assert validation.status_code == 200, validation.text
        assert validation.json()[0]["validation_status"] == "pass"

        results = client.get(f"/pilot/runs/{run_body['id']}/validation-results", headers=headers)
        assert results.status_code == 200, results.text
        assert results.json()[0]["contract_id"] == contract.json()["id"]

        bundle = client.post(
            f"/pilot/runs/{run_body['id']}/evidence-bundle",
            headers=headers,
            json={"title": "Pilot Alpha evidence bundle"},
        )
        assert bundle.status_code == 201, bundle.text
        bundle_body = bundle.json()
        assert len(bundle_body["package_sha256"]) == 64
        assert bundle_body["package_json"]["product_order"] == PRODUCT_ORDER
        serialized_bundle = json.dumps(bundle_body, sort_keys=True)
        assert "raw peak text must not be exposed" not in serialized_bundle
        assert "C1=CC=CC=C1O" not in serialized_bundle
        assert bundle_body["package_json"]["secrets_included"] is False


def test_missing_endpoint_acceptance_readiness_signoff_and_dashboard(client, api_headers):
    headers = api_headers
    with client:
        tenant = _tenant(client, headers)
        dataset = _dataset(client, headers)
        scenario = _scenario(client, headers, dataset["id"], missing_endpoint=True)

        run = client.post(
            f"/pilot/scenarios/{scenario['id']}/run",
            headers=headers,
            json={"tenant_id": tenant["id"], "run_label": "Missing endpoint dry run"},
        )
        assert run.status_code == 201, run.text
        run_body = run.json()
        assert run_body["status"] == "requires_review"
        assert any(warning["warning_type"] == "missing_endpoint" for warning in run_body["warnings_json"])
        assert any(step["step_key"] == "missing_endpoint" for step in run_body["steps"])

        protocol = client.post(
            "/pilot/acceptance-protocols",
            headers=headers,
            json={
                "tenant_id": tenant["id"],
                "title": "Pilot acceptance protocol",
                "scope": "full_platform",
                "scenario_ids_json": [scenario["id"]],
                "acceptance_tests_json": [
                    {
                        "test_key": "uat-missing-endpoint",
                        "title": "Missing endpoint review path",
                        "description": "Confirm missing endpoints surface as review required.",
                        "scenario_id": scenario["id"],
                        "expected_result": "Missing endpoint warning is visible.",
                    }
                ],
                "success_criteria_json": [{"criterion": "warning is not silent"}],
                "status": "active",
            },
        )
        assert protocol.status_code == 201, protocol.text

        tests = client.get(f"/pilot/acceptance-protocols/{protocol.json()['id']}/tests", headers=headers)
        assert tests.status_code == 200, tests.text
        assert tests.json()[0]["status"] == "not_run"

        executed = client.post(
            f"/pilot/acceptance-tests/{tests.json()[0]['id']}/execute",
            headers=headers,
            json={
                "status": "pass",
                "executed_by": "QA Reviewer",
                "evidence_json": {"review_status": "requires review", "source_text": "should redact"},
            },
        )
        assert executed.status_code == 200, executed.text
        assert executed.json()["status"] == "pass"
        assert executed.json()["evidence_json"]["source_text"] == "[redacted]"

        readiness = client.post(
            "/pilot/readiness-assessments",
            headers=headers,
            json={
                "tenant_id": tenant["id"],
                "readiness_status": "ready_for_pilot",
                "spectracheck_readiness_json": {"status": "ready_for_pilot"},
                "regulatory_readiness_json": {"status": "ready_for_pilot"},
                "reaction_readiness_json": {"status": "ready_for_pilot"},
            },
        )
        assert readiness.status_code == 201, readiness.text
        assert readiness.json()["readiness_status"] == "ready_for_pilot"

        signoff = client.post(
            "/pilot/signoff",
            headers=headers,
            json={
                "tenant_id": tenant["id"],
                "pilot_run_id": run_body["id"],
                "protocol_id": protocol.json()["id"],
                "signer_name": "Pilot Sponsor",
                "signer_email": "sponsor@example.com",
                "decision": "accepted_with_limitations",
                "rationale": "Accepted with limitations because one endpoint requires review.",
            },
        )
        assert signoff.status_code == 201, signoff.text
        assert signoff.json()["signature_record_id"] is not None
        assert signoff.json()["decision"] == "accepted_with_limitations"

        dashboard = client.get(f"/pilot/customer-dashboard/{tenant['id']}", headers=headers)
        assert dashboard.status_code == 200, dashboard.text
        assert dashboard.json()["product_order"] == PRODUCT_ORDER
        assert dashboard.json()["latest_readiness"]["readiness_status"] == "ready_for_pilot"


def test_customer_pilot_data_cannot_mix_with_demo_data(client, api_headers):
    headers = api_headers
    with client:
        demo = _dataset(client, headers)
        customer = client.post(
            "/pilot/golden-datasets",
            headers=headers,
            json={
                "dataset_key": "customer-pilot-dataset",
                "title": "Customer pilot dataset",
                "description": "Customer pilot data summary.",
                "dataset_type": "spectracheck",
                "source_type": "customer_pilot",
                "status": "draft",
                "metadata_json": {"customer_approved": False, "private_customer_notes": "redact me"},
            },
        )
        assert customer.status_code == 201, customer.text
        assert customer.json()["metadata_json"]["private_customer_notes"] == "[redacted]"

        mixed = client.post(
            "/pilot/scenarios",
            headers=headers,
            json={
                "scenario_key": "mixed-demo-customer",
                "title": "Mixed data scenario",
                "description": "This should be blocked.",
                "scenario_type": "full_product_workflow",
                "dataset_ids_json": [demo["id"], customer.json()["id"]],
            },
        )
        assert mixed.status_code == 400, mixed.text
        assert "Customer pilot data must not be mixed" in mixed.json()["detail"]


def test_phase65_openapi_includes_pilot_endpoints(client, api_headers):
    headers = api_headers
    with client:
        response = client.get("/openapi.json", headers=headers)
        assert response.status_code == 200, response.text
        paths = response.json()["paths"]
        for path in [
            "/pilot/golden-datasets",
            "/pilot/golden-datasets/{dataset_id}",
            "/pilot/scenarios",
            "/pilot/scenarios/{scenario_id}",
            "/pilot/scenarios/{scenario_id}/workflow-cases",
            "/pilot/scenarios/{scenario_id}/expected-output-contracts",
            "/pilot/scenarios/{scenario_id}/seed-tenant",
            "/pilot/demo-seeds/{seed_id}",
            "/pilot/scenarios/{scenario_id}/run",
            "/pilot/runs",
            "/pilot/runs/{pilot_run_id}",
            "/pilot/runs/{pilot_run_id}/validate",
            "/pilot/runs/{pilot_run_id}/validation-results",
            "/pilot/acceptance-protocols",
            "/pilot/acceptance-protocols/{protocol_id}",
            "/pilot/acceptance-tests/{test_id}/execute",
            "/pilot/acceptance-protocols/{protocol_id}/tests",
            "/pilot/readiness-assessments",
            "/pilot/readiness-assessments/{assessment_id}",
            "/pilot/signoff",
            "/pilot/signoff/{signoff_id}",
            "/pilot/runs/{pilot_run_id}/evidence-bundle",
            "/pilot/customer-dashboard/{tenant_id}",
        ]:
            assert path in paths
