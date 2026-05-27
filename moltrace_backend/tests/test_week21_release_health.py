import json
from pathlib import Path

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


RELEASE_HEALTH_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "contracts"
    / "release-health"
    / "raw_fid_prompt_sidecar_smoke.v1.json"
)


def _raw_fid_prompt_sidecar_contract() -> dict[str, object]:
    return json.loads(RELEASE_HEALTH_CONTRACT.read_text(encoding="utf-8"))[
        "raw_fid_prompt_sidecar_smoke"
    ]


def test_release_health_requires_admin_and_returns_release_data(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path / 'release_health.sqlite3'}"
    settings = Settings(
        database_url=db_url,
        require_verified_email=False,
        api_key="test-key",
        admin_emails=("admin@example.com",),
    )
    with TestClient(create_app(settings)) as client:
        reg = client.post(
            "/auth/register",
            json={"email": "admin@example.com", "password": "StrongPassword123!"},
        )
        assert reg.status_code in {200, 201, 409}

        login = client.post(
            "/auth/login",
            json={"email": "admin@example.com", "password": "StrongPassword123!"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        res = client.get(
            "/admin/release-health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["release_stage"] == "week21-release-candidate"
        assert data["release_version"] == "0.21.0"
        assert data["supported_raw_fid_vendors_beta"] == ["Bruker", "Varian/Agilent"]
        assert "value_dashboard" in data
        assert (
            "GET /admin/raw-fid/prompt-sidecar/fixture-report?limit=1&include_varian=false"
            in data["recommended_smoke_tests"]
        )
        sidecar_smoke = data["raw_fid_prompt_sidecar_smoke"]
        contract_smoke = _raw_fid_prompt_sidecar_contract()
        assert set(sidecar_smoke) == set(contract_smoke)
        assert sidecar_smoke["status"] in {
            contract_smoke["status"],
            "missing_optional_fid_dependencies",
        }
        assert {
            key: value for key, value in sidecar_smoke.items() if key != "status"
        } == {key: value for key, value in contract_smoke.items() if key != "status"}
        assert "moltrace-raw-fid-sidecar-report" in sidecar_smoke["ci_command"]
        assert "--smoke" in sidecar_smoke["ci_command"]
        promotion_gate = sidecar_smoke["manual_promotion_gate"]
        assert "--promotion-gate" in promotion_gate["ci_command"]
        assert "--include-varian" in promotion_gate["ci_command"]
        promotion_design = sidecar_smoke["manual_promotion_design"]
        assert promotion_design["runtime_activation_allowed"] is False
        assert (
            promotion_design["doc_path"]
            == "docs/raw_fid_prompt_manual_promotion_design.md"
        )
        assert (
            promotion_design["required_guardrail_command"]
            == "./scripts/run_prompt_sidecar_guardrails.sh"
        )
        assert "no_runtime_activation" in promotion_design["required_gates"]
        assert (
            "stage_0_metadata_only_current_state"
            in promotion_design["promotion_stages"]
        )
        assert promotion_design["rollback_mode"] == "MOLTRACE_RAW_FID_PIPELINE=legacy"
        provenance_artifact = sidecar_smoke["provenance_checksum_artifact"]
        assert "--include-varian" in provenance_artifact["ci_command"]
        assert "raw_fid_prompt_provenance_checksums" in provenance_artifact[
            "ci_command"
        ]
        assert "raw_fid_prompt_sidecar_provenance_checksums.json" in (
            provenance_artifact["files"]
        )
        shadow_artifact = sidecar_smoke["shadow_comparison_artifact"]
        assert "raw_fid_prompt_shadow_comparison" in shadow_artifact["ci_command"]
        assert shadow_artifact["runtime_activation_allowed"] is False
        assert shadow_artifact["ci_artifact"] == "raw-fid-prompt-shadow-comparison"
        assert "raw_fid_prompt_shadow_comparison_summary.json" in (
            shadow_artifact["files"]
        )
        readiness_artifact = sidecar_smoke["release_readiness_artifact"]
        assert "raw_fid_prompt_release_readiness" in readiness_artifact[
            "ci_command"
        ]
        assert readiness_artifact["runtime_activation_allowed"] is False
        assert readiness_artifact["ci_artifact"] == "raw-fid-prompt-release-readiness"
        assert readiness_artifact["files"] == [
            "raw_fid_prompt_release_readiness.md"
        ]


def test_ci_runs_raw_fid_prompt_promotion_gate_as_non_blocking_artifact() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "tests.yml"
    )
    workflow = workflow_path.read_text(encoding="utf-8")

    assert "Raw FID Prompt manual promotion gate diagnostic" in workflow
    assert "continue-on-error: true" in workflow
    assert "--promotion-gate" in workflow
    assert "--include-varian" in workflow
    assert "raw_fid_prompt_manual_promotion_gate" in workflow
    assert "raw-fid-prompt-manual-promotion-gate" in workflow
    assert "Raw FID Prompt provenance checksum report" in workflow
    assert "raw_fid_prompt_provenance_checksums" in workflow
    assert "raw-fid-prompt-provenance-checksums" in workflow
    assert "Raw FID Prompt shadow comparison summary" in workflow
    assert "raw_fid_prompt_shadow_comparison" in workflow
    assert "raw-fid-prompt-shadow-comparison" in workflow
    assert "raw_fid_prompt_shadow_comparison_summary.json" in workflow
    assert "raw_fid_prompt_shadow_comparison_summary.csv" in workflow
    assert "Summarize Raw FID Prompt shadow comparison review" in workflow
    assert "read-only release evidence for Prompt 1/2 sidecar-vs-legacy fixture review" in workflow
    assert "Raw FID Prompt release readiness summary" in workflow
    assert "raw_fid_prompt_release_readiness" in workflow
    assert "raw-fid-prompt-release-readiness" in workflow
    assert "raw_fid_prompt_release_readiness.md" in workflow
    assert "one read-only reviewer summary of manual-promotion gate, provenance, and shadow-comparison status" in workflow
    assert "A separate manual runtime promotion must be implemented and reviewed" in workflow
    assert "Run release-health contract guardrail suite" in workflow
    assert "scripts/run_release_health_contract_guardrails.sh" in workflow
    assert "id: prompt_sidecar_guardrails" in workflow
    assert "id: release_health_guardrails" in workflow
    assert "Summarize reviewer guardrail workflow" in workflow
    assert "Prompt sidecar guardrails: \\`${{ steps.prompt_sidecar_guardrails.outcome }}\\`" in workflow
    assert "Release-health guardrails: \\`${{ steps.release_health_guardrails.outcome }}\\`" in workflow
    assert "If Prompt sidecar guardrails fail: stop release review" in workflow
    assert "If release-health guardrails fail: update backend payloads" in workflow
    assert "does not activate Prompt 1/2 for runtime spectra" in workflow
    assert "Summarize Raw FID Prompt artifact map" in workflow
    assert "### Raw FID Prompt artifact map" in workflow
    assert "You need the fastest one-page Prompt 1/2 readiness summary" in workflow
    assert "Read-only comparison evidence; do not use it to drive plotted spectra" in workflow
    assert "Audit evidence only; investigate hash drift before release" in workflow
    assert "May show \\`review_required\\` without failing CI" in workflow
    assert "None may activate Prompt 1/2 for SpectraCheck runtime spectra" in workflow


def test_raw_fid_prompt_manual_promotion_design_stays_reporting_only() -> None:
    docs_dir = Path(__file__).resolve().parents[1] / "docs"
    design = (docs_dir / "raw_fid_prompt_manual_promotion_design.md").read_text(
        encoding="utf-8"
    )
    release_checklist = (docs_dir / "week21_release_candidate.md").read_text(
        encoding="utf-8"
    )

    assert "metadata-only diagnostics" in design
    assert "Prompt 1/2 sidecar output may not drive visible `x/y`" in design
    assert "processed-spectrum behavior" in design
    assert "MOLTRACE_RAW_FID_PIPELINE=legacy" in design
    assert "raw_fid_prompt_manual_promotion_design.md" in release_checklist
    assert "raw-fid-prompt-shadow-comparison" in release_checklist
    assert "raw-fid-prompt-release-readiness" in release_checklist
    assert "raw_fid_prompt_release_readiness.md" in release_checklist
    assert "runtime_activation_allowed=false" in release_checklist
    assert "separate manual runtime promotion" in release_checklist
    assert "./scripts/run_release_health_contract_guardrails.sh" in release_checklist
    assert "backend release-health contract regression" in release_checklist
    assert "Reviewer guardrail workflow" in release_checklist
    assert "./scripts/run_prompt_sidecar_guardrails.sh" in release_checklist
    assert "Prompt sidecar failure: stop the release review" in release_checklist
    assert "Release-health failure: update the backend contract" in release_checklist
    assert "does not activate Prompt 1/2 for runtime spectra" in release_checklist
    assert "CI artifacts map" in release_checklist
    assert "raw-fid-prompt-release-readiness" in release_checklist
    assert "raw-fid-prompt-shadow-comparison" in release_checklist
    assert "raw-fid-prompt-provenance-checksums" in release_checklist
    assert "raw-fid-prompt-manual-promotion-gate" in release_checklist
    assert "runtime activation stays blocked" in release_checklist
    assert "do not use it to drive plotted spectra" in release_checklist
    assert "activation_allowed=false" in release_checklist


def test_release_health_contract_guardrail_script_is_cross_stack() -> None:
    root_dir = Path(__file__).resolve().parents[2]
    script = (
        root_dir / "scripts" / "run_release_health_contract_guardrails.sh"
    ).read_text(encoding="utf-8")
    package_json = (
        root_dir / "moltrace_frontend" / "package.json"
    ).read_text(encoding="utf-8")

    assert "tests/test_week21_release_health.py" in script
    assert "pnpm test:release-health" in script
    assert "Release-health contract guardrails passed." in script
    assert "test:release-health" in package_json
    assert "src/lib/admin/release-health.test.ts" in package_json
    assert "components/settings/deployment-settings-workspace.test.tsx" in package_json


def test_root_release_guardrails_doc_keeps_prompt_integration_cadence() -> None:
    root_dir = Path(__file__).resolve().parents[2]
    guardrails = (root_dir / "RELEASE_GUARDRAILS.md").read_text(
        encoding="utf-8"
    )

    assert "MolTrace Release Guardrails" in guardrails
    assert "./scripts/run_prompt_sidecar_guardrails.sh" in guardrails
    assert "./scripts/run_release_health_contract_guardrails.sh" in guardrails
    assert "raw-fid-prompt-release-readiness" in guardrails
    assert "raw-fid-prompt-shadow-comparison" in guardrails
    assert "Fast Prompt Integration Cadence" in guardrails
    assert "Spec and contract first" in guardrails
    assert "Shadow or sidecar integration" in guardrails
    assert "Promotion is separate" in guardrails
    assert "Prompt 3: GSD layer" in guardrails
    assert "no visible spectrum mutation" in guardrails
    assert "Per-Prompt Definition Of Done" in guardrails
    assert "Dependency Rule" in guardrails
