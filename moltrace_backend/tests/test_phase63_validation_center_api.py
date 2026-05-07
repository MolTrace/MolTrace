from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _client(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'phase63_validation_center.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _project(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/validation-center/projects",
        headers=headers,
        json={
            "title": "Phase 63 backend validation package",
            "scope": "full_platform",
            "validation_type": "change_validation",
            "status": "in_progress",
            "intended_use": "Part 11 readiness and Annex 11 readiness evidence management.",
            "regulated_context": "Internal GxP readiness assessment.",
            "owner_name": "Validation Owner",
            "qa_reviewer_name": "QA Reviewer",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _urs(client: TestClient, headers: dict[str, str], project_id: int) -> dict:
    response = client.post(
        f"/validation-center/projects/{project_id}/urs",
        headers=headers,
        json={
            "requirement_code": "URS-SC-001",
            "module": "spectracheck",
            "requirement_text": "The system records analytical review evidence with audit context.",
            "criticality": "high",
            "gxp_impact": "direct",
            "status": "approved",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _risk(client: TestClient, headers: dict[str, str], project_id: int, requirement_id: int) -> dict:
    response = client.post(
        f"/validation-center/projects/{project_id}/risk-assessment",
        headers=headers,
        json={
            "target_type": "requirement",
            "target_id": requirement_id,
            "risk_description": "Analytical review evidence could be incomplete.",
            "severity": "high",
            "probability": "medium",
            "detectability": "medium",
            "mitigation": "Scripted validation protocol with execution evidence.",
            "testing_rigor": "scripted",
            "status": "open",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _protocol_and_case(
    client: TestClient,
    headers: dict[str, str],
    project_id: int,
    requirement_id: int,
    risk_id: int,
) -> tuple[dict, dict]:
    protocol = client.post(
        f"/validation-center/projects/{project_id}/test-protocols",
        headers=headers,
        json={
            "protocol_code": "OQ-SC-001",
            "title": "SpectraCheck evidence OQ",
            "module": "spectracheck",
            "protocol_type": "operational",
            "status": "approved",
        },
    )
    assert protocol.status_code == 201, protocol.text
    test_case = client.post(
        f"/validation-center/test-protocols/{protocol.json()['id']}/test-cases",
        headers=headers,
        json={
            "test_case_code": "TC-SC-001",
            "title": "Evidence is retained with review status",
            "preconditions": "Validation project and URS exist.",
            "steps_json": [{"step": 1, "action": "Create evidence record"}],
            "expected_results": "Evidence is available for QA review.",
            "linked_requirement_ids_json": [requirement_id],
            "linked_risk_ids_json": [risk_id],
            "status": "approved",
        },
    )
    assert test_case.status_code == 201, test_case.text
    return protocol.json(), test_case.json()


def test_validation_workflow_traceability_and_failed_execution_deviation(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        project = _project(client, headers)
        requirement = _urs(client, headers, project["id"])
        risk = _risk(client, headers, project["id"], requirement["id"])
        protocol, test_case = _protocol_and_case(
            client,
            headers,
            project["id"],
            requirement["id"],
            risk["id"],
        )

        passed = client.post(
            f"/validation-center/test-cases/{test_case['id']}/execute",
            headers=headers,
            json={
                "executed_by": "QA Analyst",
                "execution_status": "pass",
                "actual_results": "Expected evidence was retained.",
                "evidence_file_ids_json": [],
                "evidence_artifact_ids_json": [],
            },
        )
        assert passed.status_code == 201, passed.text
        assert passed.json()["execution_status"] == "pass"

        failed = client.post(
            f"/validation-center/test-cases/{test_case['id']}/execute",
            headers=headers,
            json={
                "executed_by": "QA Analyst",
                "execution_status": "fail",
                "actual_results": "A required evidence attachment was missing.",
            },
        )
        assert failed.status_code == 201, failed.text
        assert failed.json()["execution_status"] == "fail"
        assert failed.json()["deviation_id"] is not None

        deviations = client.get("/deviations", headers=headers)
        assert deviations.status_code == 200, deviations.text
        assert any(row["id"] == failed.json()["deviation_id"] for row in deviations.json())

        traceability = client.post(
            f"/validation-center/projects/{project['id']}/traceability/generate",
            headers=headers,
        )
        assert traceability.status_code == 201, traceability.text
        traceability_body = traceability.json()
        assert traceability_body["status"] == "gaps_identified"
        assert traceability_body["coverage_summary_json"]["requirement_count"] == 1
        assert any(gap["gap_type"] == "missing_function" for gap in traceability_body["missing_coverage_json"])
        assert traceability_body["matrix_json"]["rows"][0]["test_case_ids"] == [test_case["id"]]
        assert protocol["id"] > 0


def test_esignature_controlled_record_and_new_version_rules(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        missing_reason = client.post(
            "/esignatures/records",
            headers=headers,
            json={
                "signer_name": "QA Reviewer",
                "signature_meaning": "reviewed",
                "target_type": "validation_project",
                "target_id": 1,
            },
        )
        assert missing_reason.status_code == 422, missing_reason.text

        signature = client.post(
            "/esignatures/records",
            headers=headers,
            json={
                "signer_name": "QA Reviewer",
                "signer_email": "qa@example.com",
                "signature_meaning": "reviewed",
                "target_type": "validation_project",
                "target_id": 1,
                "reason": "QA review completed for readiness package.",
                "authentication_method": "api_key_session",
            },
        )
        assert signature.status_code == 201, signature.text
        signature_body = signature.json()
        assert len(signature_body["signature_hash"]) == 64
        assert signature_body["signed_at"]

        record = client.post(
            "/controlled-records",
            headers=headers,
            json={
                "record_type": "validation_protocol",
                "title": "OQ protocol controlled record",
                "version": "1",
                "content_json": {"protocol": "OQ-SC-001"},
            },
        )
        assert record.status_code == 201, record.text
        record_body = record.json()
        assert len(record_body["content_hash"]) == 64

        locked = client.post(
            f"/controlled-records/{record_body['id']}/lock",
            headers=headers,
            json={"locked_by": "QA Reviewer", "reason": "Protocol issued for execution."},
        )
        assert locked.status_code == 200, locked.text
        assert locked.json()["status"] == "locked"

        blocked_archive = client.post(
            f"/controlled-records/{record_body['id']}/archive",
            headers=headers,
            json={"reason": "Attempt direct modification after lock."},
        )
        assert blocked_archive.status_code == 409, blocked_archive.text

        new_version = client.post(
            f"/controlled-records/{record_body['id']}/new-version",
            headers=headers,
            json={"content_json": {"protocol": "OQ-SC-001", "revision": 2}},
        )
        assert new_version.status_code == 201, new_version.text
        assert new_version.json()["version"] == "2"
        assert new_version.json()["metadata_json"]["previous_record_id"] == record_body["id"]


def test_data_integrity_inspection_package_release_and_capa(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        project = _project(client, headers)
        record = client.post(
            "/controlled-records",
            headers=headers,
            json={
                "record_type": "release_record",
                "title": "Backend release controlled record",
                "content_json": {"release": "63.0.0"},
            },
        )
        assert record.status_code == 201, record.text

        data_integrity = client.post(
            "/data-integrity/assessments",
            headers=headers,
            json={
                "scope": "system",
                "assessment_status": "warning",
                "attributable_status": "pass",
                "legible_status": "pass",
                "contemporaneous_status": "warning",
                "original_status": "pass",
                "accurate_status": "pass",
                "complete_status": "pass",
                "consistent_status": "pass",
                "enduring_status": "pass",
                "available_status": "pass",
                "findings_json": [{"finding": "Timestamp review required"}],
                "recommended_actions_json": [{"action": "QA review"}],
            },
        )
        assert data_integrity.status_code == 201, data_integrity.text
        assert data_integrity.json()["contemporaneous_status"] == "warning"

        release = client.post(
            "/system-releases",
            headers=headers,
            json={
                "release_version": "63.0.0",
                "release_type": "backend",
                "change_summary": "GxP validation readiness backend layer.",
                "validation_project_id": project["id"],
                "test_summary_json": {"passed": 3, "failed": 0},
                "risk_summary_json": {"open_high_risks": 0},
                "approval_status": "ready_for_qa",
            },
        )
        assert release.status_code == 201, release.text

        approved = client.post(
            f"/system-releases/{release.json()['id']}/approve",
            headers=headers,
            json={
                "signer_name": "QA Reviewer",
                "signer_email": "qa@example.com",
                "reason": "Validation summary reviewed for release readiness.",
                "authentication_method": "api_key_session",
            },
        )
        assert approved.status_code == 200, approved.text
        approved_body = approved.json()
        assert approved_body["approval_status"] == "approved"
        signature_id = approved_body["metadata_json"]["approval_signature_id"]

        package = client.post(
            "/inspection-packages",
            headers=headers,
            json={
                "title": "Phase 63 inspection-ready package",
                "scope": "validation_project",
                "scope_id": project["id"],
                "included_record_ids_json": [record.json()["id"]],
                "included_signature_ids_json": [signature_id],
                "included_validation_project_ids_json": [project["id"]],
            },
        )
        assert package.status_code == 201, package.text
        package_body = package.json()
        assert len(package_body["package_sha256"]) == 64
        manifest = package_body["package_manifest_json"]
        assert manifest["controlled_records"][0]["content_hash"] == record.json()["content_hash"]
        assert manifest["e_signature_records"][0]["signature_id"] == signature_id
        assert manifest["release_records"]

        download = client.get(f"/inspection-packages/{package_body['id']}/download", headers=headers)
        assert download.status_code == 200, download.text
        assert package_body["package_sha256"] in download.text

        deviation = client.post(
            "/deviations",
            headers=headers,
            json={
                "title": "Release checklist gap",
                "description": "A release checklist item required follow-up.",
                "severity": "medium",
                "source_type": "audit",
                "status": "investigation",
            },
        )
        assert deviation.status_code == 201, deviation.text
        capa = client.post(
            "/capa",
            headers=headers,
            json={
                "title": "Release checklist corrective action",
                "description": "Close checklist gap and prevent recurrence.",
                "source_deviation_id": deviation.json()["id"],
                "corrective_action": "Update release checklist.",
                "preventive_action": "Add checklist review to QA workflow.",
                "owner": "QA",
            },
        )
        assert capa.status_code == 201, capa.text
        assert capa.json()["source_deviation_id"] == deviation.json()["id"]


def test_phase63_openapi_includes_validation_endpoints(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        openapi = client.get("/openapi.json", headers=headers)
        assert openapi.status_code == 200, openapi.text
        paths = openapi.json()["paths"]
        expected = [
            "/validation-center/projects",
            "/validation-center/projects/{validation_project_id}/urs",
            "/validation-center/projects/{validation_project_id}/traceability/generate",
            "/esignatures/records",
            "/controlled-records/{record_id}/lock",
            "/data-integrity/assessments",
            "/inspection-packages/{package_id}/download",
            "/system-releases/{release_id}/approve",
            "/deviations",
            "/capa",
        ]
        for path in expected:
            assert path in paths
