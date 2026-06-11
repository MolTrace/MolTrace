from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.raw_fid_prompt_validation import (
    PROMOTION_GATE_VERSION,
    PROVENANCE_ARTIFACT_VERSION,
    PROVENANCE_VERSION,
    RELEASE_READINESS_ARTIFACT_VERSION,
    REPORT_VERSION,
    SHADOW_COMPARISON_ARTIFACT_VERSION,
    SHADOW_COMPARISON_VERSION,
    build_fixture_validation_report,
    main,
    promotion_gate_failures,
    promotion_gate_summary,
    reporting_only_smoke_failures,
    reporting_only_smoke_summary,
    shadow_comparison_summary,
    write_validation_outputs,
)
from nmrcheck.settings import Settings

pytest.importorskip("nmrglue")


@pytest.mark.slow
def test_raw_fid_prompt_fixture_report_is_reporting_only(tmp_path: Path) -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "nmrshiftdb2"

    report = build_fixture_validation_report(
        nmrshiftdb2_root=fixture_root,
        include_varian=False,
        limit=1,
    )

    assert report["version"] == REPORT_VERSION
    assert report["active_visible_pipeline"] == "legacy"
    assert report["prompt_pipeline_active"] is False
    assert report["activation_policy"] == "reporting_only_no_runtime_wiring"
    assert report["fixture_count"] == 1
    assert report["summary"]["prompt_sidecar_available"] == 1
    assert report["reporting_only_smoke"] == {
        "passed": True,
        "failure_count": 0,
        "failures": [],
    }
    readiness = report["activation_readiness"]
    assert readiness["version"] == "raw_fid_prompt_activation_readiness_v1"
    assert readiness["visibility"] == "admin_diagnostic_only"
    assert readiness["active_visible_pipeline"] == "legacy"
    assert readiness["prompt_pipeline_active"] is False
    assert readiness["activation_allowed"] is False
    assert (
        readiness["activation_policy"]
        == "blocked_until_all_gates_pass_and_a_separate_manual_promotion_is_implemented"
    )
    assert readiness["fixture_count"] == 1
    assert readiness["gate_count"] >= 8
    gate_names = {gate["name"] for gate in readiness["gates"]}
    assert {
        "prompt_sidecar_available",
        "peak_count_reference_tolerance",
        "ppm_axis_alignment",
        "phase_delta",
        "baseline_method",
        "processed_peak_ppm_axis_alignment",
        "fingerprint_hash",
        "runtime_target",
        "no_runtime_activation",
    }.issubset(gate_names)
    promotion_gate = report["promotion_gate"]
    assert promotion_gate["version"] == PROMOTION_GATE_VERSION
    assert promotion_gate["visibility"] == "ci_admin_gate_only"
    assert promotion_gate["runtime_activation_allowed"] is False
    assert promotion_gate["active_visible_pipeline"] == "legacy"
    assert promotion_gate["prompt_pipeline_active"] is False
    assert promotion_gate["requires_manual_code_change"] is True
    assert promotion_gate["requires_explicit_runtime_feature_flag"] is True
    assert promotion_gate["status"] in {
        "blocked",
        "eligible_for_manual_promotion",
    }
    assert "moltrace-raw-fid-sidecar-report" in promotion_gate["ci_command"]
    assert "--promotion-gate" in promotion_gate["ci_command"]
    shadow = report["shadow_comparison_summary"]
    assert shadow["version"] == SHADOW_COMPARISON_VERSION
    assert shadow["visibility"] == "admin_diagnostic_only"
    assert shadow["reporting_policy"] == (
        "read_only_shadow_comparison_no_runtime_activation"
    )
    assert shadow["active_visible_pipeline"] == "legacy"
    assert shadow["prompt_pipeline_active"] is False
    assert shadow["runtime_activation_allowed"] is False
    assert shadow["fixture_count"] == 1
    assert shadow["prompt_sidecar_available"] == 1
    assert shadow["reference_rows"] == 1
    assert shadow["runtime_effect"]["spectracheck_visible_pipeline"] == (
        "unchanged_legacy"
    )
    assert shadow["status"] in {"passed", "review_required", "blocked"}
    assert shadow["decision_guidance"] in {
        "all_shadow_gates_passed_manual_review_still_required",
        "review_required_before_any_manual_promotion",
    }
    provenance = report["provenance"]
    assert provenance["version"] == PROVENANCE_VERSION
    assert provenance["route_policy"] == "offline_builder"
    assert provenance["parameters"] == {
        "include_varian": False,
        "limit": 1,
        "strict": False,
    }
    assert provenance["fixture_count"] == 1
    assert len(provenance["fixture_identity_sha256"]) == 64
    assert len(provenance["row_fingerprint_sha256"]) == 64
    assert len(provenance["row_payload_sha256"]) == 64
    assert len(provenance["shadow_comparison_sha256"]) == 64
    assert len(provenance["report_payload_sha256"]) == 64

    row = report["rows"][0]
    assert row["source"] == "NMRShiftDB2"
    assert row["vendor"] == "Bruker"
    assert row["archive"].endswith(".zip")
    expected_archive_hash = hashlib.sha256(
        (fixture_root / row["archive"]).read_bytes()
    ).hexdigest()
    assert row["archive_sha256"] == expected_archive_hash
    assert len(row["archive_sha256"]) == 64
    assert row["archive_size_bytes"] > 0
    assert row["legacy_status"] == "ok"
    assert row["prompt_status"] == "ok"
    assert row["validation_visibility"] == "hidden_metadata_only"
    assert row["safe_to_activate"] is False
    assert isinstance(row["legacy_peak_count"], int)
    assert isinstance(row["prompt_peak_count"], int)
    assert row["prompt_hash_present"] is True
    assert row["reference_peak_ppm_count"] > 0
    assert row["reference_ppm_tolerance"] == pytest.approx(0.01)
    assert (
        row["prompt_reference_ppm_checked_count"]
        == row["reference_peak_ppm_count"]
    )
    assert row["prompt_reference_ppm_max_error"] <= row["reference_ppm_tolerance"]
    assert row["prompt_reference_ppm_mean_error"] <= row["reference_ppm_tolerance"]
    assert row["prompt_reference_ppm_within_tolerance"] is True
    assert row["prompt_ppm_min"] < row["prompt_ppm_max"]
    assert row["baseline_prompt_rmse_fraction_full_scale"] is not None
    assert row["activation_readiness_status"] in {
        "passed",
        "review_required",
        "failed",
    }
    assert isinstance(row["activation_readiness_gate_failures"], list)
    assert isinstance(row["activation_readiness_gate_reviews"], list)
    second_report = build_fixture_validation_report(
        nmrshiftdb2_root=fixture_root,
        include_varian=False,
        limit=1,
    )
    assert (
        second_report["provenance"]["fixture_identity_sha256"]
        == provenance["fixture_identity_sha256"]
    )
    assert (
        second_report["provenance"]["row_fingerprint_sha256"]
        == provenance["row_fingerprint_sha256"]
    )

    json_path, csv_path = write_validation_outputs(report, tmp_path)
    provenance_path = tmp_path / "raw_fid_prompt_sidecar_provenance_checksums.json"
    checksum_csv_path = tmp_path / "raw_fid_prompt_sidecar_provenance_checksums.csv"
    shadow_path = tmp_path / "raw_fid_prompt_shadow_comparison_summary.json"
    shadow_csv_path = tmp_path / "raw_fid_prompt_shadow_comparison_summary.csv"
    readiness_path = tmp_path / "raw_fid_prompt_release_readiness.md"

    reloaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert reloaded["rows"][0]["fixture_id"] == row["fixture_id"]
    assert reloaded["provenance"]["row_fingerprint_sha256"] == provenance[
        "row_fingerprint_sha256"
    ]
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "fixture_id,source,vendor,nucleus,archive,archive_sha256" in csv_text
    assert "activation_readiness_status" in csv_text
    assert "prompt_reference_ppm_max_error" in csv_text
    assert "baseline_prompt_rmse_fraction_full_scale" in csv_text
    assert row["fixture_id"] in csv_text
    assert row["archive_sha256"] in csv_text

    provenance_artifact = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance_artifact["version"] == PROVENANCE_ARTIFACT_VERSION
    assert provenance_artifact["active_visible_pipeline"] == "legacy"
    assert provenance_artifact["prompt_pipeline_active"] is False
    assert provenance_artifact["runtime_effect"]["raw_fid_plotting"] == "unchanged"
    assert provenance_artifact["provenance"]["fixture_identity_sha256"] == provenance[
        "fixture_identity_sha256"
    ]
    exported = {
        item["artifact_type"]: item for item in provenance_artifact["exported_files"]
    }
    assert exported["report_json"]["sha256"] == hashlib.sha256(
        json_path.read_bytes()
    ).hexdigest()
    assert exported["report_csv"]["sha256"] == hashlib.sha256(
        csv_path.read_bytes()
    ).hexdigest()
    assert exported["shadow_comparison_json"]["sha256"] == hashlib.sha256(
        shadow_path.read_bytes()
    ).hexdigest()
    assert exported["shadow_comparison_csv"]["sha256"] == hashlib.sha256(
        shadow_csv_path.read_bytes()
    ).hexdigest()
    assert exported["release_readiness_markdown"]["sha256"] == hashlib.sha256(
        readiness_path.read_bytes()
    ).hexdigest()
    assert provenance_artifact["fixture_archives"][0]["fixture_id"] == row["fixture_id"]
    assert provenance_artifact["fixture_archives"][0]["sha256"] == row[
        "archive_sha256"
    ]
    checksum_csv = checksum_csv_path.read_text(encoding="utf-8")
    assert "artifact_type,fixture_id,source,vendor,nucleus,path,sha256" in checksum_csv
    assert "report_json" in checksum_csv
    assert "shadow_comparison_json" in checksum_csv
    assert "release_readiness_markdown" in checksum_csv
    assert "fixture_archive" in checksum_csv
    assert row["archive_sha256"] in checksum_csv

    shadow_artifact = json.loads(shadow_path.read_text(encoding="utf-8"))
    assert shadow_artifact["version"] == SHADOW_COMPARISON_ARTIFACT_VERSION
    assert shadow_artifact["active_visible_pipeline"] == "legacy"
    assert shadow_artifact["prompt_pipeline_active"] is False
    assert shadow_artifact["runtime_activation_allowed"] is False
    assert (
        shadow_artifact["policy"]
        == "ci_admin_shadow_comparison_no_runtime_activation"
    )
    assert shadow_artifact["shadow_comparison_summary"]["version"] == (
        SHADOW_COMPARISON_VERSION
    )
    assert shadow_artifact["shadow_comparison_sha256"] == provenance[
        "shadow_comparison_sha256"
    ]
    shadow_csv = shadow_csv_path.read_text(encoding="utf-8")
    assert "version,status,visibility,reporting_policy" in shadow_csv
    assert "raw_fid_prompt_shadow_comparison_v1" in shadow_csv
    assert "runtime_activation_allowed" in shadow_csv

    readiness_markdown = readiness_path.read_text(encoding="utf-8")
    assert "# Raw FID Prompt 1/2 Release Readiness" in readiness_markdown
    assert RELEASE_READINESS_ARTIFACT_VERSION in readiness_markdown
    assert "Runtime activation: `blocked`" in readiness_markdown
    assert "separate manual runtime promotion" in readiness_markdown
    assert "## Manual Promotion Gate" in readiness_markdown
    assert "## Shadow Comparison" in readiness_markdown
    assert "## Provenance Hashes" in readiness_markdown
    assert row["fixture_id"] in readiness_markdown


@pytest.mark.slow
def test_raw_fid_prompt_fixture_report_can_include_varian_fixture() -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "nmrshiftdb2"
    varian_root = Path(__file__).parent / "fixtures" / "nmrglue" / "varian"

    report = build_fixture_validation_report(
        nmrshiftdb2_root=fixture_root,
        varian_root=varian_root,
        include_varian=True,
        limit=0,
    )

    assert report["fixture_count"] == 1
    row = report["rows"][0]
    assert row["fixture_id"] == "nmrglue_example_separate_1d_varian"
    assert row["vendor"] == "Varian/Agilent"
    assert row["nucleus"] == "13C"
    assert row["prompt_status"] == "ok"
    assert row["prompt_hash_present"] is True


def test_admin_raw_fid_prompt_fixture_report_route_is_reporting_only(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'sidecar_report.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=("admin@example.com",),
        )
    )
    client = TestClient(app)

    with client:
        forbidden = client.get(
            "/admin/raw-fid/prompt-sidecar/fixture-report",
        )
        assert forbidden.status_code == 401

        response = client.get(
            "/admin/raw-fid/prompt-sidecar/fixture-report",
            headers={"x-api-key": "test-key"},
            params={"limit": 1, "include_varian": False},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["version"] == "raw_fid_prompt_sidecar_fixture_report_v1"
    assert payload["route_policy"] == "admin_diagnostic_reporting_only"
    assert payload["active_visible_pipeline"] == "legacy"
    assert payload["prompt_pipeline_active"] is False
    assert payload["activation_policy"] == "reporting_only_no_runtime_wiring"
    readiness = payload["activation_readiness"]
    assert readiness["visibility"] == "admin_diagnostic_only"
    assert readiness["active_visible_pipeline"] == "legacy"
    assert readiness["prompt_pipeline_active"] is False
    assert readiness["activation_allowed"] is False
    assert payload["reporting_only_smoke"] == {
        "passed": True,
        "failure_count": 0,
        "failures": [],
    }
    shadow = payload["shadow_comparison_summary"]
    assert shadow["version"] == SHADOW_COMPARISON_VERSION
    assert shadow["visibility"] == "admin_diagnostic_only"
    assert shadow["runtime_activation_allowed"] is False
    assert shadow["active_visible_pipeline"] == "legacy"
    assert shadow["prompt_pipeline_active"] is False
    assert shadow["runtime_effect"]["raw_fid_plotting"] == "unchanged"
    promotion_gate = payload["promotion_gate"]
    assert promotion_gate["visibility"] == "ci_admin_gate_only"
    assert promotion_gate["runtime_activation_allowed"] is False
    assert promotion_gate["active_visible_pipeline"] == "legacy"
    assert promotion_gate["prompt_pipeline_active"] is False
    assert promotion_gate["requires_manual_code_change"] is True
    assert payload["runtime_effect"] == {
        "spectracheck_visible_pipeline": "unchanged_legacy",
        "processed_spectrum_pipeline": "unchanged",
        "raw_fid_plotting": "unchanged",
        "peak_markers": "unchanged",
    }
    assert payload["fixture_count"] == 1
    assert payload["rows"][0]["safe_to_activate"] is False
    assert payload["rows"][0]["validation_visibility"] == "hidden_metadata_only"
    assert payload["requested_by"]["system_api_key"] is True
    provenance = payload["provenance"]
    assert provenance["version"] == PROVENANCE_VERSION
    assert provenance["route_policy"] == "admin_diagnostic_reporting_only"
    assert provenance["parameters"] == {
        "include_varian": False,
        "limit": 1,
        "strict": False,
    }
    assert len(provenance["requested_by_sha256"]) == 64
    assert len(provenance["runtime_effect_sha256"]) == 64
    assert len(provenance["shadow_comparison_sha256"]) == 64
    assert len(provenance["report_payload_sha256"]) == 64


def test_shadow_comparison_summary_is_admin_only_and_flags_reviews() -> None:
    rows = [
        {
            "fixture_id": "shadow-review-fixture",
            "row_status": "review_required",
            "prompt_status": "ok",
            "activation_readiness_status": "review_required",
            "prompt_peak_count_within_reference_tolerance": False,
            "prompt_reference_ppm_within_tolerance": True,
            "prompt_runtime_within_target": True,
            "prompt_peak_count": 11,
            "reference_peak_count": 8,
            "prompt_reference_peak_count_delta": 3,
            "prompt_reference_ppm_checked_count": 5,
            "prompt_reference_ppm_max_error": 0.002,
            "phase_delta_degrees": 2.5,
            "baseline_prompt_rmse_fraction_full_scale": 0.001,
            "prompt_runtime_ms": 42.0,
        }
    ]

    summary = shadow_comparison_summary(rows)

    assert summary["version"] == SHADOW_COMPARISON_VERSION
    assert summary["visibility"] == "admin_diagnostic_only"
    assert summary["runtime_activation_allowed"] is False
    assert summary["active_visible_pipeline"] == "legacy"
    assert summary["prompt_pipeline_active"] is False
    assert summary["status"] == "review_required"
    assert summary["decision_guidance"] == (
        "review_required_before_any_manual_promotion"
    )
    assert summary["prompt_peak_count_review_required"] == 1
    assert summary["prompt_reference_ppm_within_tolerance"] == 1
    assert summary["max_prompt_reference_peak_count_delta"] == 3
    assert summary["max_prompt_reference_ppm_error"] == pytest.approx(0.002)
    assert summary["max_prompt_runtime_ms"] == pytest.approx(42.0)
    assert summary["review_fixture_ids"] == ["shadow-review-fixture"]


def test_reporting_only_smoke_flags_activation_regressions() -> None:
    report = {
        "version": REPORT_VERSION,
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "activation_policy": "reporting_only_no_runtime_wiring",
        "fixture_count": 1,
        "summary": {"prompt_sidecar_available": 1},
        "rows": [
            {
                "fixture_id": "smoke_fixture",
                "prompt_status": "ok",
                "prompt_hash_present": True,
                "safe_to_activate": False,
                "validation_visibility": "hidden_metadata_only",
            }
        ],
    }

    assert reporting_only_smoke_summary(report) == {
        "passed": True,
        "failure_count": 0,
        "failures": [],
    }

    activated = {**report, "prompt_pipeline_active": True}
    assert "prompt_pipeline_marked_active" in reporting_only_smoke_failures(activated)

    visible_row = {
        **report,
        "rows": [{**report["rows"][0], "validation_visibility": "visible"}],
    }
    assert (
        "smoke_fixture:validation_not_hidden_metadata_only"
        in reporting_only_smoke_failures(visible_row)
    )


def test_promotion_gate_is_manual_only_and_requires_all_gates_to_pass() -> None:
    report = {
        "version": REPORT_VERSION,
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "activation_policy": "reporting_only_no_runtime_wiring",
        "fixture_count": 1,
        "summary": {"prompt_sidecar_available": 1},
        "rows": [
            {
                "fixture_id": "promotion_fixture",
                "row_status": "passed",
                "prompt_status": "ok",
                "prompt_hash_present": True,
                "safe_to_activate": False,
                "validation_visibility": "hidden_metadata_only",
                "activation_readiness_status": "passed",
            }
        ],
        "activation_readiness": {
            "version": "raw_fid_prompt_activation_readiness_v1",
            "visibility": "admin_diagnostic_only",
            "active_visible_pipeline": "legacy",
            "prompt_pipeline_active": False,
            "activation_allowed": False,
            "overall_status": "candidate_ready_for_manual_promotion",
            "gate_count": 1,
            "passed_gate_count": 1,
            "review_gate_count": 0,
            "failed_gate_count": 0,
            "fixture_count": 1,
            "gates": [{"name": "synthetic_gate", "status": "passed"}],
        },
    }
    report["reporting_only_smoke"] = reporting_only_smoke_summary(report)

    gate = promotion_gate_summary(report)

    assert gate["eligible_for_manual_promotion"] is True
    assert gate["runtime_activation_allowed"] is False
    assert gate["requires_manual_code_change"] is True
    assert gate["requires_explicit_runtime_feature_flag"] is True
    assert promotion_gate_failures(report) == []

    activated = {**report, "prompt_pipeline_active": True}
    activated["reporting_only_smoke"] = reporting_only_smoke_summary(activated)
    activated_gate = promotion_gate_summary(activated)

    assert activated_gate["eligible_for_manual_promotion"] is False
    assert activated_gate["runtime_activation_allowed"] is False
    assert (
        "reporting_only_smoke:prompt_pipeline_marked_active"
        in activated_gate["failures"]
    )

    review = {
        **report,
        "activation_readiness": {
            **report["activation_readiness"],
            "overall_status": "review_required",
            "passed_gate_count": 0,
            "review_gate_count": 1,
            "gates": [{"name": "synthetic_gate", "status": "review_required"}],
        },
        "rows": [
            {
                **report["rows"][0],
                "row_status": "review_required",
                "activation_readiness_status": "review_required",
            }
        ],
    }
    review["reporting_only_smoke"] = reporting_only_smoke_summary(review)
    review_gate = promotion_gate_summary(review)

    assert review_gate["eligible_for_manual_promotion"] is False
    assert "activation_readiness_status:review_required" in review_gate["failures"]
    assert (
        "activation_readiness_gate_not_passed:synthetic_gate"
        in review_gate["failures"]
    )
    assert "promotion_fixture:row_status_not_passed" in review_gate["failures"]


def test_raw_fid_prompt_sidecar_smoke_cli_is_guardrail_only(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--output-dir",
            str(tmp_path),
            "--limit",
            "1",
            "--no-include-varian",
            "--quiet",
            "--smoke",
        ]
    )

    assert exit_code == 0
    payload = json.loads(
        (tmp_path / "raw_fid_prompt_sidecar_fixture_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["reporting_only_smoke"]["passed"] is True
    assert payload["prompt_pipeline_active"] is False
    assert payload["active_visible_pipeline"] == "legacy"
    assert payload["activation_readiness"]["activation_allowed"] is False
    assert payload["activation_readiness"]["visibility"] == "admin_diagnostic_only"
    provenance = json.loads(
        (tmp_path / "raw_fid_prompt_sidecar_provenance_checksums.json").read_text(
            encoding="utf-8"
        )
    )
    assert provenance["version"] == PROVENANCE_ARTIFACT_VERSION
    assert provenance["prompt_pipeline_active"] is False
    assert (
        tmp_path / "raw_fid_prompt_sidecar_provenance_checksums.csv"
    ).exists()
    assert (tmp_path / "raw_fid_prompt_shadow_comparison_summary.json").exists()
    assert (tmp_path / "raw_fid_prompt_shadow_comparison_summary.csv").exists()
    assert (tmp_path / "raw_fid_prompt_release_readiness.md").exists()
