import json
from pathlib import Path

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


REQUIRED_FRONTEND_CONTRACT_OPERATIONS = {
    "/system/health": {"get"},
    "/system/status": {"get"},
    "/system/jobs/summary": {"get"},
    "/system/storage/summary": {"get"},
    "/security/summary": {"get"},
    "/connectors": {"get"},
    "/ingestion-runs": {"get"},
    "/outbound-sync-jobs": {"get"},
    "/projects": {"get", "post"},
    "/reaction-projects": {"get", "post"},
    "/reaction-projects/{reaction_project_id}/experiments": {"get", "post"},
    "/reaction-projects/{reaction_project_id}/recommendations": {"get", "post"},
    "/reaction-projects/{reaction_project_id}/optimization/bo/run": {"post"},
    "/regulatory/dossiers": {"get", "post"},
    "/regulatory/action-items": {"get", "post"},
    "/regulatory/action-items/{action_item_id}": {"patch"},
    "/regulatory/changes": {"get"},
    "/regulatory/notifications": {"get"},
    "/regulatory/rule-update-proposals": {"get"},
    "/regulatory/jurisdictions": {"get"},
    "/regulatory/sources": {"get"},
    "/regulatory/sources/upload": {"post"},
    "/validation-center/projects": {"get", "post"},
    "/validation-center/projects/{validation_project_id}": {"get", "patch"},
    "/validation-center/projects/{validation_project_id}/urs": {"get", "post"},
    "/validation-center/projects/{validation_project_id}/functional-specs": {"get", "post"},
    "/validation-center/projects/{validation_project_id}/risk-assessment": {"get", "post"},
    "/validation-center/projects/{validation_project_id}/test-protocols": {"get", "post"},
    "/validation-center/projects/{validation_project_id}/traceability": {"get"},
    "/validation-center/projects/{validation_project_id}/traceability/generate": {"post"},
    "/validation-center/test-executions": {"get"},
    "/validation-center/test-cases/{test_case_id}/execute": {"post"},
    "/validation-runs/{validation_run_id}": {"get"},
    "/data-integrity/assessments": {"get", "post"},
    "/controlled-records": {"get", "post"},
    "/controlled-records/{record_id}/lock": {"post"},
    "/deviations": {"get", "post"},
    "/capa": {"get", "post"},
    "/system-releases": {"get", "post"},
    "/inspection-packages": {"get", "post"},
    "/inspection-packages/{package_id}/download": {"get"},
    "/knowledge/sources": {"get", "post"},
    "/knowledge/sources/{source_id}": {"get", "patch"},
    "/knowledge/extractions/runs": {"get"},
    "/knowledge/review-tasks": {"get", "post"},
    "/knowledge/training-dataset-candidates": {"get", "post"},
    "/knowledge/benchmark-dataset-candidates": {"get", "post"},
    "/knowledge/model-improvement-queue": {"get", "post"},
    "/knowledge/dataset-versions": {"get", "post"},
    "/ml/model-health": {"get"},
    "/ml/model-artifacts": {"get"},
    "/ml/model-cards": {"get", "post"},
    "/ml/training-runs": {"get", "post"},
    "/ml/evaluation-runs": {"get", "post"},
    "/ml/calibration-assessments": {"get", "post"},
    "/ml/error-analysis": {"get", "post"},
    "/ml/ood-assessments": {"get", "post"},
    "/ml/deployment-candidates": {"get", "post"},
    "/ai/services": {"get", "post"},
    "/ai/predictions": {"get", "post"},
    "/ai/active-learning/candidates": {"get", "post"},
    "/ai/model-monitoring": {"get"},
    "/model-health": {"get"},
    "/model-health/drift-alerts": {"get"},
    "/cross-module/action-items": {"get", "post"},
    "/cross-module/command-center": {"get"},
    "/files/upload": {"post"},
    "/spectracheck/sessions": {"get", "post"},
    "/spectracheck/sessions/{session_id}/files": {"get", "post"},
    "/workflow-templates": {"get", "post"},
    "/nmr/processed/preview": {"post"},
    "/nmr/processed/analyze": {"post"},
    "/nmr/raw-fid/preview": {"post"},
    "/nmr/raw-fid/process": {"post"},
    "/quality-control/files/{file_id}/assess": {"post"},
    "/quality-control/files/{file_id}": {"get"},
    "/ms/hrms/candidates/match/evidence": {"post"},
    "/ms/hrms/formulas/search": {"post"},
    "/ms/adducts/infer/evidence": {"post"},
    "/ms/msms/annotate/evidence": {"post"},
    "/ms/msms/fragmentation-tree/evidence": {"post"},
    "/ms/lcms/import/bridge/upload": {"post"},
    "/ms/lcms/features/detect/upload": {"post"},
    "/ms/lcms/features/group/evidence": {"post"},
    "/ms/lcms/features/consensus/evidence": {"post"},
    "/ms/lcms/dereplication/evidence": {"post"},
    "/confidence/candidates/lcms-consensus-bridge": {"post"},
    "/confidence/candidates/unified/evidence": {"post"},
    "/reports/structure-elucidation/compose/evidence": {"post"},
    "/mobile/config": {"get"},
    "/mobile/command-center": {"get"},
    "/mobile/dashboard": {"get"},
    "/mobile/action-queue": {"get"},
    "/mobile/action-drafts": {"get", "post"},
    "/mobile/sync": {"post"},
    "/mobile/offline-safe-summary": {"get"},
}

PROTECTED_FRONTEND_ENTRYPOINTS = [
    "/workflow-templates",
    "/mobile/command-center",
    "/validation-center/projects",
    "/ml/model-health",
    "/ai/predictions",
    "/cross-module/action-items",
]


def _client(tmp_path) -> tuple[TestClient, dict[str, str]]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'frontend_may10_11_contract.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            admin_emails=("admin@example.com",),
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def test_may10_11_frontend_endpoint_families_are_openapi_backed(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.get("/openapi.json", headers=headers)

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    missing: list[str] = []
    for path, required_methods in REQUIRED_FRONTEND_CONTRACT_OPERATIONS.items():
        path_doc = paths.get(path)
        if path_doc is None:
            missing.append(f"{path} missing")
            continue
        for method in required_methods:
            if method not in path_doc:
                missing.append(f"{method.upper()} {path} missing")

    assert not missing


def test_regenerated_frontend_backend_contract_report_has_no_missing_operations() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    report_path = (
        repo_root
        / "moltrace_frontend"
        / "tests"
        / "visual-baseline"
        / "backend-contract-report.json"
    )
    report = json.loads(report_path.read_text())

    assert report["missingCount"] == 0
    assert report["missing"] == []
    assert report["frontendApiCalls"] >= 673
    assert report["backendOperations"] >= 781
    assert report["unresolvedCount"] <= 18


def test_frontend_entrypoints_require_auth_with_safe_public_errors(tmp_path) -> None:
    client, _headers = _client(tmp_path)
    with client:
        responses = [client.get(path) for path in PROTECTED_FRONTEND_ENTRYPOINTS]

    combined = " ".join(response.text for response in responses)
    for response in responses:
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Sign in to access live MolTrace data."

    forbidden_markers = [
        "x-api-key",
        "Authorization:",
        "Traceback",
        "/Users/",
        "postgresql://",
        "API_KEY",
    ]
    for marker in forbidden_markers:
        assert marker not in combined


def test_workflow_templates_and_mobile_command_center_match_frontend_contract(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        templates_res = client.get("/workflow-templates", headers=headers)
        command_res = client.get("/mobile/command-center", headers=headers)

    assert templates_res.status_code == 200, templates_res.text
    templates = templates_res.json()
    template_slugs = {template["slug"] for template in templates}
    assert "raw_fid_to_evidence" in template_slugs
    assert "full_spectracheck_evidence_to_report" in template_slugs
    assert all("steps" in template and "required_inputs" in template for template in templates)

    assert command_res.status_code == 200, command_res.text
    command_body = command_res.json()
    assert command_body["module_order"] == [
        "spectracheck",
        "regulatory_hub",
        "reaction_optimization",
    ]
    assert isinstance(command_body["sections"], list)
    assert isinstance(command_body["action_summary_json"], dict)
    serialized = str(command_body).lower()
    for forbidden_payload in ("raw_spectrum", "raw_fid", "full_source_text", "latest_report_json"):
        assert forbidden_payload not in serialized
