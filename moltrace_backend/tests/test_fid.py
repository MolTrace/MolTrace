import asyncio
import hashlib
import io
import json
import os
import stat
import tarfile
import warnings
import zipfile
from tempfile import mkdtemp

import numpy as np
import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from starlette.requests import Request

from nmrcheck.api import (
    AccessContext,
    create_app,
    evidence_report_json,
    fid_presets,
    fid_preview,
    fid_process,
    fid_run_approve,
    fid_run_package,
    fid_run_report,
    fid_run_report_html,
    fid_run_review_decisions,
    fid_runs,
    nmr_raw_fid_preview_route,
    nmr_raw_fid_process_route,
    report_from_analysis,
)
from nmrcheck.database import get_raw_archive_by_sha256, init_db, list_recent_analyses
from nmrcheck.fid import (
    FIDProcessingError,
    fid_settings_from_preset,
    normalize_apodization_mode,
    process_bruker_1d_zip,
)
from nmrcheck.fid_pipeline_adapter import (
    HYBRID_METADATA_RAW_FID_PIPELINE,
    LEGACY_RAW_FID_PIPELINE,
    RAW_FID_PIPELINE_ENV,
    attach_prompt_pipeline_sidecar,
    build_prompt_pipeline_analysis_guidance,
    build_prompt_pipeline_consistency_check,
    build_prompt_pipeline_sidecar,
    build_prompt_pipeline_validation_report,
    resolve_raw_fid_pipeline_mode,
    should_build_prompt_sidecar,
)
from nmrcheck.models import FIDProcessingRecipe, FIDRunReviewCreate
from nmrcheck.raw_vault import build_raw_upload_provenance
from nmrcheck.settings import Settings

REFERENCE_TEXT = "3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)"


def _assert_prompt_runtime_contract(metadata: dict[str, object]) -> dict[str, object]:
    contract = metadata["prompt_1_2_runtime_contract"]
    assert isinstance(contract, dict)
    assert contract["version"] == "raw_fid_prompt_1_2_runtime_contract_v1"
    assert contract["scope"] == "raw_fid_only"
    assert contract["visibility"] == "metadata_only"
    assert contract["integration_status"] == "merged_with_active_raw_fid_layer"
    assert contract["active_visible_pipeline"] == "legacy_raw_fid_processor"
    assert contract["visible_spectrum_fields_preserved"] is True
    assert contract["processed_uploads_touched"] is False
    assert contract["prompt_pipeline_active"] is False
    assert contract["used_for_plot"] is False
    assert contract["used_for_peak_markers"] is False
    assert contract["used_for_phase_or_baseline_swap"] is False
    prompt_reader = contract["prompt_1_fid_reader"]
    assert prompt_reader["module"] == "moltrace.spectroscopy.io.fid_reader.read_fid"
    assert prompt_reader["zero_fill_points"] == 65536
    prompt_preprocess = contract["prompt_2_phase_baseline"]
    assert (
        prompt_preprocess["module"]
        == "moltrace.spectroscopy.preprocess.phase_baseline"
    )
    assert prompt_preprocess["phase_default_method"] == "regions_analysis"
    prompt_gsd = contract["prompt_3_gsd_peak_picker"]
    assert prompt_gsd["module"] == "moltrace.spectroscopy.peaks.gsd"
    assert prompt_gsd["status"] == "available_for_sidecar_validation"
    assert prompt_gsd["default_level"] == 2
    assert prompt_gsd["prompt_pipeline_active"] is False
    assert prompt_gsd["used_for_plot"] is False
    assert prompt_gsd["used_for_peak_markers"] is False
    assert prompt_gsd["used_for_visible_spectrum"] is False
    gates = contract["acceptance_gates"]
    assert gates["ppm_scale_reference_tolerance_ppm"] == 0.01
    assert gates["peak_count_tolerance_vs_reference"] == 2
    assert gates["phase_angle_tolerance_degrees"] == 5
    assert gates["baseline_rmse_fraction_full_scale"] == 0.005
    assert gates["prompt_3_peak_count_tolerance_fraction_vs_expert"] == 0.05
    assert gates["prompt_3_solvent_detection_target_fraction"] == 0.95
    return contract


def test_fid_processing_recipe_defaults_are_safe_real_spectrum_defaults() -> None:
    recipe = FIDProcessingRecipe()

    assert recipe.phase_mode == "auto"
    assert recipe.baseline_correction == "bernstein"
    assert recipe.baseline_order == 3
    assert recipe.display_mode == "real"
    assert recipe.vertical_gain == 1.0
    assert recipe.debug_preview is False


def test_raw_fid_accepts_sine_bell_windowing_before_fft() -> None:
    assert normalize_apodization_mode("sine-bell") == "sine_bell"
    settings = fid_settings_from_preset(
        selected_preset="balanced",
        apodization_mode="sine_bell",
        line_broadening_hz=0.0,
        zero_fill_factor=4,
    )

    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=_build_bruker_zip(),
        settings=settings,
    )

    recipe = report.processing_metadata.processing_recipe
    assert recipe.apodization_mode == "sine_bell"
    assert report.metadata["line_broadening"]["window_function"] == "sine_bell"
    assert report.metadata["line_broadening"]["window_applied"] is True
    assert report.metadata["line_broadening"]["window"]["applied_before_fft"] is True
    zero_filling = report.metadata["zero_filling"]
    assert zero_filling["factor"] == 4
    assert zero_filling["fft_size"] > zero_filling["input_points"]
    assert zero_filling["zero_filled_points_added"] > 0
    preparation = report.metadata["plotly_data_preparation"]
    assert preparation["applied_before_plotly"] is True
    assert preparation["sequence"] == [
        "digital_filter_or_group_delay",
        "apodization_window",
        "zero_fill_fft",
        "phase_correction",
        "baseline_flattening",
        "peak_preserving_downsample",
    ]


def test_prompt_fid_pipeline_adapter_defaults_to_legacy_without_report_changes() -> None:
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="balanced"),
    )

    assert resolve_raw_fid_pipeline_mode(environ={}) == LEGACY_RAW_FID_PIPELINE
    adapted = attach_prompt_pipeline_sidecar(
        report,
        {"pipeline": "prompt_1_2", "available": True},
        mode=LEGACY_RAW_FID_PIPELINE,
    )

    assert adapted is report
    assert adapted.model_dump(mode="json") == report.model_dump(mode="json")


def test_prompt_fid_pipeline_adapter_sidecar_does_not_touch_spectral_fields() -> None:
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="balanced"),
    )
    sidecar = {
        "pipeline": "prompt_1_2",
        "role": "sidecar_metadata_only",
        "available": True,
        "fingerprint_hash": "deterministic-test-hash",
        "point_count": 65536,
    }

    adapted = attach_prompt_pipeline_sidecar(
        report,
        sidecar,
        mode=HYBRID_METADATA_RAW_FID_PIPELINE,
    )
    original = report.model_dump(mode="json")
    updated = adapted.model_dump(mode="json")

    assert adapted is not report
    assert updated["preview_points"] == original["preview_points"]
    assert updated["inferred_peaks"] == original["inferred_peaks"]
    assert updated["warnings"] == original["warnings"]

    updated_metadata = dict(updated["metadata"])
    attached_sidecar = updated_metadata.pop("prompt_pipeline_sidecar")
    assert updated_metadata == original["metadata"]
    assert attached_sidecar["default_pipeline_preserved"] is True
    assert attached_sidecar["fingerprint_hash"] == "deterministic-test-hash"
    validation = attached_sidecar["validation_report"]
    assert validation["visibility"] == "hidden_metadata_only"
    assert validation["active_visible_pipeline"] == "legacy"
    assert validation["prompt_pipeline_active"] is False
    assert validation["safe_to_activate"] is False
    assert validation["regression_guard"]["spectral_fields_preserved"] is True
    guidance = attached_sidecar["analysis_guidance"]
    assert guidance["visibility"] == "metadata_only"
    assert guidance["active_visible_pipeline"] == "legacy"
    assert guidance["used_for_plot"] is False
    assert guidance["used_for_peak_markers"] is False
    assert guidance["legacy_spectrum_fields_preserved"] is True


def test_prompt_fid_pipeline_rejects_unapproved_runtime_activation_modes() -> None:
    for raw_value in (
        "prompt_1_2",
        "active",
        "enabled",
        "true",
        "phase_baseline",
        "reader_processor",
        "new_pipeline",
    ):
        assert resolve_raw_fid_pipeline_mode(raw_value) == LEGACY_RAW_FID_PIPELINE
        assert (
            resolve_raw_fid_pipeline_mode(environ={RAW_FID_PIPELINE_ENV: raw_value})
            == LEGACY_RAW_FID_PIPELINE
        )
        assert should_build_prompt_sidecar(raw_value) is False

    assert should_build_prompt_sidecar(HYBRID_METADATA_RAW_FID_PIPELINE) is True
    assert should_build_prompt_sidecar("sidecar") is True


def test_prompt_fid_pipeline_sidecar_cannot_inject_visual_runtime_fields() -> None:
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="balanced"),
    )
    sidecar = {
        "pipeline": "prompt_1_2",
        "role": "sidecar_metadata_only",
        "available": True,
        "fingerprint_hash": "d" * 64,
        "point_count": 65536,
        "peak_count": 999,
        "preview_points": [{"shift_ppm": 999.0, "intensity": 999.0}],
        "inferred_peaks": [{"shift_ppm": 999.0, "intensity": 999.0}],
        "plotly_traces": [{"x": [999.0], "y": [999.0]}],
        "plotly_layout": {"xaxis": {"range": [999.0, 998.0]}},
        "peak_markers": [{"ppm": 999.0, "category": "prompt"}],
        "legend": [{"name": "Prompt replacement"}],
        "hover": {"chemical_shift_ppm": 999.0},
        "vertical_peak_guides": {"visible": True},
        "trace_lines": [{"ppm": 999.0}],
        "processing_metadata": {"selected_preset": "Prompt replacement"},
        "phase": {"zero_order_degrees": 180.0, "applied_to_visible_spectrum": True},
        "baseline": {"method": "prompt_replacement", "baseline_locked_to_zero": False},
    }

    adapted = attach_prompt_pipeline_sidecar(
        report,
        sidecar,
        mode=HYBRID_METADATA_RAW_FID_PIPELINE,
    )
    original = report.model_dump(mode="json")
    updated = adapted.model_dump(mode="json")

    for field_name in (
        "preview_points",
        "inferred_peaks",
        "inferred_nmr_text",
        "reference_peaks",
        "comparison",
        "warnings",
        "processing_metadata",
        "point_count",
        "format_detected",
    ):
        assert updated[field_name] == original[field_name]

    updated_metadata = dict(updated["metadata"])
    attached_sidecar = updated_metadata.pop("prompt_pipeline_sidecar")
    assert updated_metadata == original["metadata"]

    for visual_key in (
        "plotly_traces",
        "plotly_layout",
        "peak_markers",
        "legend",
        "hover",
        "vertical_peak_guides",
        "trace_lines",
    ):
        assert visual_key not in updated
        assert visual_key not in updated_metadata
        assert visual_key in attached_sidecar

    guidance = attached_sidecar["analysis_guidance"]
    assert guidance["visibility"] == "metadata_only"
    assert guidance["active_visible_pipeline"] == "legacy"
    assert guidance["used_for_plot"] is False
    assert guidance["used_for_peak_markers"] is False
    assert guidance["used_for_phase_or_baseline"] is False
    assert guidance["legacy_spectrum_fields_preserved"] is True
    validation = attached_sidecar["validation_report"]
    assert validation["active_visible_pipeline"] == "legacy"
    assert validation["prompt_pipeline_active"] is False
    assert validation["safe_to_activate"] is False
    assert validation["regression_guard"]["spectral_fields_preserved"] is True


def test_prompt_fid_pipeline_validation_report_is_hidden_and_review_only() -> None:
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="balanced"),
    )
    ppm_values = [point.shift_ppm for point in report.preview_points]
    sidecar = {
        "pipeline": "prompt_1_2",
        "role": "sidecar_metadata_only",
        "available": True,
        "nucleus": "1H",
        "solvent": None,
        "field_mhz": 500.0,
        "point_count": report.point_count,
        "peak_count": len(report.inferred_peaks),
        "ppm_min": min(ppm_values),
        "ppm_max": max(ppm_values),
        "fingerprint_hash": "a" * 64,
        "runtime_ms": 42.0,
        "phase": {"zero_order_degrees": 0.0},
        "baseline": {"method": "bernstein"},
    }

    validation = build_prompt_pipeline_validation_report(report, sidecar)

    assert validation["version"] == "raw_fid_prompt_sidecar_validation_v1"
    assert validation["visibility"] == "hidden_metadata_only"
    assert validation["active_visible_pipeline"] == "legacy"
    assert validation["prompt_pipeline_active"] is False
    assert validation["safe_to_activate"] is False
    assert validation["status"] == "sidecar_available"
    assert validation["legacy"]["peak_count"] == len(report.inferred_peaks)
    assert validation["prompt_1_2"]["fingerprint_hash"] == "a" * 64
    comparisons = validation["comparisons"]
    assert comparisons["peak_count_delta"]["value"] == 0
    assert comparisons["peak_count_delta"]["within_prompt_acceptance"] is True
    assert comparisons["fingerprint"]["prompt_hash_present"] is True
    assert comparisons["runtime"]["within_target"] is True
    assert validation["regression_guard"]["spectral_fields_preserved"] is True

    guidance = build_prompt_pipeline_analysis_guidance(
        report,
        sidecar,
        validation_report=validation,
    )
    assert guidance["version"] == "raw_fid_prompt_peak_guidance_v1"
    assert guidance["safe_to_use_for_analysis_metadata"] is True
    assert guidance["recommended_peak_count"] == len(report.inferred_peaks)
    assert guidance["recommended_peak_count_source"] == (
        "prompt_1_2_fixture_matched_peak_count"
    )
    assert guidance["used_for_plot"] is False
    assert guidance["used_for_peak_markers"] is False
    assert guidance["used_for_phase_or_baseline"] is False

    consistency = build_prompt_pipeline_consistency_check(
        guidance,
        active_peak_count=len(report.inferred_peaks) + 5,
        active_peak_source="unit_test_legacy_peaks",
    )
    assert consistency["version"] == "raw_fid_prompt_consistency_v1"
    assert consistency["visibility"] == "metadata_only"
    assert consistency["used_for_plot"] is False
    assert consistency["used_for_peak_markers"] is False
    assert consistency["active_peak_source"] == "unit_test_legacy_peaks"
    assert consistency["status"] == "review_peak_count_delta"
    assert consistency["within_prompt_acceptance"] is False


def test_prompt_fid_pipeline_collects_reader_preprocess_diagnostics_without_activation() -> None:
    pytest.importorskip("nmrglue")
    content = _build_bruker_zip()
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=content,
        settings=fid_settings_from_preset(selected_preset="balanced"),
    )

    sidecar = build_prompt_pipeline_sidecar(
        filename="bruker_dataset.zip",
        content=content,
        nucleus="1H",
        solvent="CDCl3",
        strict=True,
    )

    assert sidecar["role"] == "sidecar_metadata_only"
    assert sidecar["active"] is False
    assert sidecar["available"] is True

    reader = sidecar["reader_diagnostics"]
    assert reader["version"] == "prompt_1_fid_reader_sidecar_v1"
    assert reader["source"] == "moltrace.spectroscopy.io.fid_reader.read_fid"
    assert reader["visibility"] == "metadata_only"
    assert reader["active_visible_pipeline"] == "legacy"
    assert reader["prompt_pipeline_active"] is False
    assert reader["used_for_plot"] is False
    assert reader["used_for_peak_markers"] is False
    assert reader["used_for_phase_or_baseline"] is False
    assert reader["used_for_visible_spectrum"] is False
    assert reader["zero_fill_points"] == 65_536
    assert reader["input_points"] > 0
    assert reader["line_broadening_hz"] == 0.5
    assert reader["ppm_axis_direction"] == "descending"
    assert len(reader["fingerprint_hash"]) == 64

    preprocess = sidecar["preprocess_diagnostics"]
    assert preprocess["version"] == "prompt_2_phase_baseline_sidecar_v1"
    assert preprocess["source"] == "moltrace.spectroscopy.preprocess.phase_baseline"
    assert preprocess["visibility"] == "metadata_only"
    assert preprocess["active_visible_pipeline"] == "legacy"
    assert preprocess["prompt_pipeline_active"] is False
    assert preprocess["used_for_plot"] is False
    assert preprocess["used_for_peak_markers"] is False
    assert preprocess["used_for_phase_or_baseline"] is False
    assert preprocess["used_for_visible_spectrum"] is False
    assert preprocess["phase_method"] == "regions_analysis"
    assert preprocess["baseline_method"] == "bernstein"
    assert preprocess["baseline_order"] == 3

    adapted = attach_prompt_pipeline_sidecar(
        report,
        sidecar,
        mode=HYBRID_METADATA_RAW_FID_PIPELINE,
    )
    original = report.model_dump(mode="json")
    updated = adapted.model_dump(mode="json")
    for field_name in (
        "preview_points",
        "inferred_peaks",
        "inferred_nmr_text",
        "reference_peaks",
        "comparison",
        "warnings",
        "processing_metadata",
        "point_count",
        "format_detected",
    ):
        assert updated[field_name] == original[field_name]

    updated_metadata = dict(updated["metadata"])
    attached_sidecar = updated_metadata.pop("prompt_pipeline_sidecar")
    assert updated_metadata == original["metadata"]

    validation = attached_sidecar["validation_report"]
    integration = validation["integration_diagnostics"]
    assert integration["version"] == "raw_fid_prompt_metadata_seam_v1"
    assert integration["visibility"] == "hidden_metadata_only"
    assert integration["active_visible_pipeline"] == "legacy"
    assert integration["prompt_pipeline_active"] is False
    assert integration["visible_spectrum_source"] == "legacy_raw_fid_processor"
    assert integration["prompt_reader_source"] == "metadata_only_sidecar"
    assert integration["prompt_preprocess_source"] == "metadata_only_sidecar"
    assert integration["active_visual_fields_preserved"] is True
    assert integration["used_for_plot"] is False
    assert integration["used_for_peak_markers"] is False
    assert integration["used_for_phase_or_baseline"] is False
    assert integration["used_for_visible_spectrum"] is False
    assert integration["safe_to_activate"] is False
    assert integration["status"] == "ready_for_review"

    prompt_summary = validation["prompt_1_2"]
    assert prompt_summary["reader_diagnostics"]["used_for_plot"] is False
    assert prompt_summary["preprocess_diagnostics"]["used_for_phase_or_baseline"] is False

    guidance = attached_sidecar["analysis_guidance"]
    assert guidance["integration_diagnostics_version"] == (
        "raw_fid_prompt_metadata_seam_v1"
    )
    assert guidance["metadata_only_integration_status"] == "ready_for_review"
    assert guidance["reader_diagnostics_available"] is True
    assert guidance["preprocess_diagnostics_available"] is True
    assert guidance["used_for_plot"] is False
    assert guidance["used_for_peak_markers"] is False
    assert guidance["used_for_phase_or_baseline"] is False


def test_frontend_raw_fid_preview_sidecar_is_flagged_and_non_disruptive(monkeypatch) -> None:
    request = _build_request()
    context = AccessContext(system_api_key=True)
    monkeypatch.delenv("MOLTRACE_RAW_FID_PIPELINE", raising=False)

    async def preview_once():
        return await nmr_raw_fid_preview_route(
            request=request,
            file=_build_upload(),
            sample_id="adapter-preview",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            include_spectrum=True,
            compound_class=None,
            candidates_text=None,
            proton_nmr_text=REFERENCE_TEXT,
            carbon13_text=None,
            context=context,
        )

    legacy_preview = asyncio.run(preview_once())
    assert "prompt_pipeline_sidecar" not in legacy_preview.metadata
    legacy_contract = _assert_prompt_runtime_contract(legacy_preview.metadata)
    assert (
        legacy_preview.metadata["raw_fid_peak_guidance"][
            "prompt_1_2_runtime_contract_status"
        ]["version"]
        == legacy_contract["version"]
    )

    monkeypatch.setenv("MOLTRACE_RAW_FID_PIPELINE", HYBRID_METADATA_RAW_FID_PIPELINE)
    hybrid_preview = asyncio.run(preview_once())

    assert hybrid_preview.x == legacy_preview.x
    assert hybrid_preview.y == legacy_preview.y
    assert hybrid_preview.peaks == legacy_preview.peaks
    hybrid_contract = _assert_prompt_runtime_contract(hybrid_preview.metadata)
    assert hybrid_contract["active_runtime"]["point_count"] == legacy_contract[
        "active_runtime"
    ]["point_count"]
    assert hybrid_contract["active_runtime"]["peak_count"] == legacy_contract[
        "active_runtime"
    ]["peak_count"]
    sidecar = hybrid_preview.metadata["prompt_pipeline_sidecar"]
    assert sidecar["role"] == "sidecar_metadata_only"
    assert sidecar["active"] is False
    assert sidecar["default_pipeline_preserved"] is True
    assert sidecar["validation_report"]["visibility"] == "hidden_metadata_only"
    assert sidecar["validation_report"]["safe_to_activate"] is False
    guidance = sidecar["analysis_guidance"]
    assert guidance["visibility"] == "metadata_only"
    assert guidance["used_for_plot"] is False
    assert guidance["used_for_peak_markers"] is False
    assert hybrid_preview.metadata["raw_fid_peak_guidance"]["prompt_sidecar_guidance"] == guidance
    consistency = hybrid_preview.metadata["raw_fid_peak_guidance"][
        "prompt_sidecar_consistency"
    ]
    assert consistency["visibility"] == "metadata_only"
    assert consistency["used_for_plot"] is False
    assert consistency["used_for_peak_markers"] is False
    assert consistency["active_peak_count"] == len(hybrid_preview.peaks)
    assert consistency["active_peak_source"] == "legacy_raw_fid_preview_peaks"


def test_frontend_raw_fid_preview_ignores_unapproved_prompt_activation_env(monkeypatch) -> None:
    request = _build_request()
    context = AccessContext(system_api_key=True)
    sidecar_calls: list[dict[str, object]] = []

    def fake_sidecar(**kwargs):
        sidecar_calls.append(dict(kwargs))
        return {
            "pipeline": "prompt_1_2",
            "role": "sidecar_metadata_only",
            "active": False,
            "available": True,
            "point_count": 65536,
            "peak_count": 999,
        }

    monkeypatch.setattr("nmrcheck.api.build_prompt_pipeline_sidecar", fake_sidecar)
    monkeypatch.setenv("MOLTRACE_RAW_FID_PIPELINE", "prompt_1_2")

    async def preview_once():
        return await nmr_raw_fid_preview_route(
            request=request,
            file=_build_upload(),
            sample_id="unapproved-prompt-preview",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            include_spectrum=True,
            compound_class=None,
            candidates_text="CCO",
            proton_nmr_text=REFERENCE_TEXT,
            carbon13_text=None,
            context=context,
        )

    preview = asyncio.run(preview_once())

    assert sidecar_calls == []
    assert preview.x
    assert preview.y
    assert preview.peaks
    assert "prompt_pipeline_sidecar" not in preview.metadata
    guidance = preview.metadata["raw_fid_peak_guidance"]
    assert "prompt_sidecar_guidance" not in guidance
    assert "prompt_sidecar_consistency" not in guidance


def test_raw_fid_preview_and_process_remain_distinct_with_sidecar_default_off(
    monkeypatch,
) -> None:
    request = _build_request()
    context = AccessContext(system_api_key=True)
    carbon13_text = "13C NMR (126 MHz, CDCl3): 58.3, 18.1 ppm."
    sidecar_calls: list[dict[str, object]] = []

    def fake_sidecar(**kwargs):
        sidecar_calls.append(dict(kwargs))
        return {
            "pipeline": "prompt_1_2",
            "role": "sidecar_metadata_only",
            "active": False,
            "available": True,
            "point_count": 65536,
            "peak_count": 999,
        }

    monkeypatch.delenv(RAW_FID_PIPELINE_ENV, raising=False)
    monkeypatch.setattr("nmrcheck.api.build_prompt_pipeline_sidecar", fake_sidecar)

    async def run_routes():
        preview = await nmr_raw_fid_preview_route(
            request=request,
            file=_build_upload(),
            sample_id="contract-preview",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            include_spectrum=True,
            compound_class=None,
            candidates_text="CCO",
            proton_nmr_text=REFERENCE_TEXT,
            carbon13_text=carbon13_text,
            context=context,
        )
        process = await nmr_raw_fid_process_route(
            request=request,
            file=_build_upload(),
            sample_id="contract-process",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            preserve_raw=True,
            include_spectrum=False,
            compound_class=None,
            candidates_text="CCO",
            proton_nmr_text=REFERENCE_TEXT,
            carbon13_text=carbon13_text,
            context=context,
        )
        return preview, process

    preview, process = asyncio.run(run_routes())

    assert sidecar_calls == []
    assert "prompt_pipeline_sidecar" not in preview.metadata
    assert "prompt_pipeline_sidecar" not in process.metadata
    preview_contract = _assert_prompt_runtime_contract(preview.metadata)
    process_contract = _assert_prompt_runtime_contract(process.metadata)
    assert preview_contract["active_runtime"]["peak_count"] == preview.peak_count
    assert process_contract["active_runtime"]["peak_count"] >= 0

    assert preview.metadata["inline_spectrum_generated"] is True
    assert preview.x
    assert preview.y
    assert preview.peak_count == len(preview.peaks)
    assert any("quick auto-FT preview" in note for note in preview.notes)

    assert process.metadata["spectrum_points_included"] is False
    assert (
        process.metadata["spectrum_points_omitted_reason"]
        == "frontend_already_has_preview_trace"
    )
    assert process.x == []
    assert process.y == []
    assert process.peak_count == len(process.peaks)
    assert any("temporary derived workspace" in note for note in process.notes)

    preview_guidance = preview.metadata["raw_fid_peak_guidance"]
    process_guidance = process.metadata["raw_fid_peak_guidance"]
    for guidance in (preview_guidance, process_guidance):
        assert guidance["parsed_smiles_supplied_to_raw_fid"] is True
        assert guidance["proton_nmr_text_supplied_to_raw_fid"] is True
        assert guidance["carbon13_text_supplied_to_raw_fid"] is True
        assert guidance["carbon13_text_used_for_peak_guidance"] is False
        assert "prompt_sidecar_guidance" not in guidance
        assert "prompt_sidecar_consistency" not in guidance
        assert guidance["prompt_1_2_runtime_contract_status"]["used_for_plot"] is False


def test_raw_fid_prompt_sidecar_bridge_is_review_only_for_preview_and_process(
    monkeypatch,
) -> None:
    request = _build_request()
    context = AccessContext(system_api_key=True)
    sidecar_calls: list[dict[str, object]] = []

    def fake_sidecar(**kwargs):
        sidecar_calls.append(dict(kwargs))
        return {
            "pipeline": "prompt_1_2",
            "role": "sidecar_metadata_only",
            "active": False,
            "available": True,
            "nucleus": kwargs.get("nucleus"),
            "solvent": kwargs.get("solvent"),
            "field_mhz": 500.0,
            "point_count": 65536,
            "peak_count": 999,
            "ppm_min": 0.0,
            "ppm_max": 10.0,
            "fingerprint_hash": "d" * 64,
            "runtime_ms": 2.0,
            "preview_points": [{"shift_ppm": 999.0, "intensity": 999.0}],
            "inferred_peaks": [{"shift_ppm": 999.0, "intensity": 999.0}],
            "plotly_traces": [{"x": [999.0], "y": [999.0]}],
            "vertical_peak_guides": {"visible": True},
            "phase": {"zero_order_degrees": 180.0},
            "baseline": {"method": "prompt_replacement"},
        }

    monkeypatch.setenv(RAW_FID_PIPELINE_ENV, HYBRID_METADATA_RAW_FID_PIPELINE)
    monkeypatch.setattr("nmrcheck.api.build_prompt_pipeline_sidecar", fake_sidecar)

    async def run_routes():
        preview = await nmr_raw_fid_preview_route(
            request=request,
            file=_build_upload(),
            sample_id="sidecar-bridge-preview",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            include_spectrum=True,
            compound_class="aminoglycoside",
            candidates_text="CCO",
            proton_nmr_text=REFERENCE_TEXT,
            carbon13_text="13C NMR (126 MHz, CDCl3): 58.3, 18.1 ppm.",
            context=context,
        )
        process = await nmr_raw_fid_process_route(
            request=request,
            file=_build_upload(),
            sample_id="sidecar-bridge-process",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            preserve_raw=True,
            include_spectrum=False,
            compound_class="aminoglycoside",
            candidates_text="CCO",
            proton_nmr_text=REFERENCE_TEXT,
            carbon13_text="13C NMR (126 MHz, CDCl3): 58.3, 18.1 ppm.",
            context=context,
        )
        return preview, process

    preview, process = asyncio.run(run_routes())

    assert len(sidecar_calls) == 2
    assert {call["filename"] for call in sidecar_calls} == {"bruker_dataset.zip"}
    assert {call["nucleus"] for call in sidecar_calls} == {"1H"}
    assert {call["solvent"] for call in sidecar_calls} == {"CDCl3"}

    assert preview.x and preview.y
    assert preview.x != [999.0]
    assert preview.y != [999.0]
    assert process.x == []
    assert process.y == []
    assert preview.peak_count != 999
    assert process.peak_count != 999

    for result, active_peak_source in (
        (preview, "legacy_raw_fid_preview_peaks"),
        (process, "legacy_raw_fid_process_enriched_peaks"),
    ):
        sidecar = result.metadata["prompt_pipeline_sidecar"]
        assert sidecar["role"] == "sidecar_metadata_only"
        assert sidecar["active"] is False
        assert sidecar["default_pipeline_preserved"] is True
        assert sidecar["preview_points"] == [{"shift_ppm": 999.0, "intensity": 999.0}]
        assert sidecar["inferred_peaks"] == [{"shift_ppm": 999.0, "intensity": 999.0}]

        validation = sidecar["validation_report"]
        assert validation["visibility"] == "hidden_metadata_only"
        assert validation["active_visible_pipeline"] == "legacy"
        assert validation["prompt_pipeline_active"] is False
        assert validation["safe_to_activate"] is False
        assert validation["regression_guard"]["spectral_fields_preserved"] is True

        guidance = sidecar["analysis_guidance"]
        assert guidance["visibility"] == "metadata_only"
        assert guidance["active_visible_pipeline"] == "legacy"
        assert guidance["used_for_plot"] is False
        assert guidance["used_for_peak_markers"] is False
        assert guidance["used_for_phase_or_baseline"] is False
        assert guidance["legacy_spectrum_fields_preserved"] is True
        assert guidance["requires_human_review_before_visual_activation"] is True

        raw_guidance = result.metadata["raw_fid_peak_guidance"]
        assert raw_guidance["prompt_sidecar_guidance"] == guidance
        consistency = raw_guidance["prompt_sidecar_consistency"]
        assert consistency["visibility"] == "metadata_only"
        assert consistency["used_for_plot"] is False
        assert consistency["used_for_peak_markers"] is False
        assert consistency["active_peak_count"] == result.peak_count
        assert consistency["active_peak_source"] == active_peak_source


def test_raw_fid_sidecar_cannot_override_preview_or_process_route_contracts(
    monkeypatch,
) -> None:
    request = _build_request()
    context = AccessContext(system_api_key=True)
    sidecar_calls: list[dict[str, object]] = []

    def fake_sidecar(**kwargs):
        sidecar_calls.append(dict(kwargs))
        return {
            "pipeline": "prompt_1_2",
            "role": "sidecar_metadata_only",
            "active": False,
            "available": True,
            "nucleus": kwargs.get("nucleus"),
            "solvent": kwargs.get("solvent"),
            "point_count": 65536,
            "peak_count": 777,
            "fingerprint_hash": "e" * 64,
            "runtime_ms": 1.0,
            "preview_points": [{"shift_ppm": 777.0, "intensity": 777.0}],
            "inferred_peaks": [{"shift_ppm": 777.0, "intensity": 777.0}],
            "plotly_traces": [{"x": [777.0], "y": [777.0]}],
            "vertical_peak_guides": {"visible": True},
            "phase": {"zero_order_degrees": 180.0},
            "baseline": {"method": "prompt_replacement"},
            "metadata": {
                "inline_spectrum_generated": False,
                "legacy_route_wrapped": "/nmr/processed/analyze",
                "spectrum_points_included": True,
                "spectrum_points_omitted_reason": "prompt_override",
                "raw_fid_peak_guidance": {
                    "peak_evidence_policy": "fabricate_reference_peaks",
                    "used_for_plot": True,
                    "used_for_peak_markers": True,
                },
            },
            "raw_fid_peak_guidance": {
                "used_for_plot": True,
                "used_for_peak_markers": True,
            },
        }

    monkeypatch.setenv(RAW_FID_PIPELINE_ENV, HYBRID_METADATA_RAW_FID_PIPELINE)
    monkeypatch.setattr("nmrcheck.api.build_prompt_pipeline_sidecar", fake_sidecar)

    async def run_routes():
        preview = await nmr_raw_fid_preview_route(
            request=request,
            file=_build_upload(),
            sample_id="sidecar-contract-preview",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            include_spectrum=True,
            compound_class="aminoglycoside",
            candidates_text="CCO",
            proton_nmr_text=REFERENCE_TEXT,
            carbon13_text="13C NMR (126 MHz, CDCl3): 58.3, 18.1 ppm.",
            context=context,
        )
        process = await nmr_raw_fid_process_route(
            request=request,
            file=_build_upload(),
            sample_id="sidecar-contract-process",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            preserve_raw=True,
            include_spectrum=False,
            compound_class="aminoglycoside",
            candidates_text="CCO",
            proton_nmr_text=REFERENCE_TEXT,
            carbon13_text="13C NMR (126 MHz, CDCl3): 58.3, 18.1 ppm.",
            context=context,
        )
        return preview, process

    preview, process = asyncio.run(run_routes())

    assert len(sidecar_calls) == 2
    assert preview.x and preview.y
    assert preview.x != [777.0]
    assert preview.y != [777.0]
    assert preview.peak_count != 777
    assert preview.metadata["inline_spectrum_generated"] is True
    assert preview.metadata["legacy_route_wrapped"] == "/raw-fid/upload"
    assert "spectrum_points_included" not in preview.metadata
    assert "spectrum_points_omitted_reason" not in preview.metadata

    assert process.x == []
    assert process.y == []
    assert process.peak_count != 777
    assert process.metadata["legacy_route_wrapped"] == (
        "/fid/process + immutable raw vault processing core"
    )
    assert process.metadata["spectrum_points_included"] is False
    assert (
        process.metadata["spectrum_points_omitted_reason"]
        == "frontend_already_has_preview_trace"
    )

    for result, active_peak_source in (
        (preview, "legacy_raw_fid_preview_peaks"),
        (process, "legacy_raw_fid_process_enriched_peaks"),
    ):
        sidecar = result.metadata["prompt_pipeline_sidecar"]
        assert sidecar["metadata"]["legacy_route_wrapped"] == "/nmr/processed/analyze"
        assert sidecar["metadata"]["spectrum_points_included"] is True
        assert sidecar["analysis_guidance"]["used_for_plot"] is False
        assert sidecar["analysis_guidance"]["used_for_peak_markers"] is False
        assert sidecar["analysis_guidance"]["used_for_phase_or_baseline"] is False

        guidance = result.metadata["raw_fid_peak_guidance"]
        assert guidance["peak_evidence_policy"] != "fabricate_reference_peaks"
        consistency = guidance["prompt_sidecar_consistency"]
        assert consistency["visibility"] == "metadata_only"
        assert consistency["used_for_plot"] is False
        assert consistency["used_for_peak_markers"] is False
        assert consistency["active_peak_count"] == result.peak_count
        assert consistency["active_peak_source"] == active_peak_source


def test_frontend_raw_fid_process_sidecar_is_flagged_and_non_disruptive(monkeypatch) -> None:
    request = _build_request()
    context = AccessContext(system_api_key=True)
    monkeypatch.setenv("MOLTRACE_RAW_FID_PIPELINE", HYBRID_METADATA_RAW_FID_PIPELINE)

    async def run_process():
        return await nmr_raw_fid_process_route(
            request=request,
            file=_build_upload(),
            sample_id="adapter-process",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            preserve_raw=True,
            include_spectrum=False,
            compound_class=None,
            candidates_text="CCO",
            proton_nmr_text=REFERENCE_TEXT,
            carbon13_text=None,
            context=context,
        )

    result = asyncio.run(run_process())

    assert result.x == []
    assert result.metadata["spectrum_points_included"] is False
    sidecar = result.metadata["prompt_pipeline_sidecar"]
    assert sidecar["role"] == "sidecar_metadata_only"
    assert sidecar["active"] is False
    assert sidecar["default_pipeline_preserved"] is True
    assert sidecar["validation_report"]["visibility"] == "hidden_metadata_only"
    assert sidecar["validation_report"]["safe_to_activate"] is False
    guidance = sidecar["analysis_guidance"]
    assert guidance["visibility"] == "metadata_only"
    assert guidance["used_for_plot"] is False
    assert guidance["used_for_peak_markers"] is False
    assert result.metadata["raw_fid_peak_guidance"]["prompt_sidecar_guidance"] == guidance
    consistency = result.metadata["raw_fid_peak_guidance"][
        "prompt_sidecar_consistency"
    ]
    assert consistency["visibility"] == "metadata_only"
    assert consistency["used_for_plot"] is False
    assert consistency["used_for_peak_markers"] is False
    assert consistency["active_peak_count"] == result.peak_count
    assert consistency["active_peak_source"] == "legacy_raw_fid_process_enriched_peaks"


def test_legacy_fid_preview_sidecar_is_default_off_and_metadata_only(monkeypatch) -> None:
    request = _build_request()
    context = AccessContext(system_api_key=True)
    upload_bytes = _build_bruker_zip()
    sidecar_calls: list[dict[str, object]] = []

    def fake_sidecar(**kwargs):
        sidecar_calls.append(dict(kwargs))
        return {
            "pipeline": "prompt_1_2",
            "role": "sidecar_metadata_only",
            "active": False,
            "available": True,
            "nucleus": kwargs.get("nucleus"),
            "solvent": kwargs.get("solvent"),
            "point_count": 65536,
            "peak_count": 3,
            "fingerprint_hash": "b" * 64,
            "runtime_ms": 1.0,
        }

    monkeypatch.setattr("nmrcheck.api.build_prompt_pipeline_sidecar", fake_sidecar)

    async def preview_once():
        return await fid_preview(
            request=request,
            file=UploadFile(filename="bruker_dataset.zip", file=io.BytesIO(upload_bytes)),
            sample_id="legacy-adapter-preview",
            workspace_sample_record_id=None,
            solvent="CDCl3",
            nucleus="1H",
            reference_ppm=None,
            reference_nmr_text=REFERENCE_TEXT,
            smiles="CCO",
            selected_preset="balanced",
            zero_fill_factor=2,
            line_broadening_hz=0.3,
            apply_group_delay=True,
            auto_phase=True,
            auto_baseline=True,
            peak_sensitivity=0.08,
            mask_solvent_regions=False,
            context=context,
        )

    monkeypatch.delenv("MOLTRACE_RAW_FID_PIPELINE", raising=False)
    legacy_preview = asyncio.run(preview_once())
    assert "prompt_pipeline_sidecar" not in legacy_preview.metadata
    assert sidecar_calls == []

    monkeypatch.setenv("MOLTRACE_RAW_FID_PIPELINE", HYBRID_METADATA_RAW_FID_PIPELINE)
    hybrid_preview = asyncio.run(preview_once())
    assert len(sidecar_calls) == 1

    legacy_payload = legacy_preview.model_dump(mode="json")
    hybrid_payload = hybrid_preview.model_dump(mode="json")
    attached_sidecar = hybrid_payload["metadata"].pop("prompt_pipeline_sidecar")

    assert hybrid_payload["preview_points"] == legacy_payload["preview_points"]
    assert hybrid_payload["inferred_peaks"] == legacy_payload["inferred_peaks"]
    assert hybrid_payload["inferred_nmr_text"] == legacy_payload["inferred_nmr_text"]
    assert hybrid_payload["reference_peaks"] == legacy_payload["reference_peaks"]
    assert hybrid_payload["comparison"] == legacy_payload["comparison"]
    assert hybrid_payload["warnings"] == legacy_payload["warnings"]
    assert (
        hybrid_payload["processing_metadata"]["processing_recipe"]
        == legacy_payload["processing_metadata"]["processing_recipe"]
    )
    assert (
        hybrid_payload["processing_metadata"]["qa_diagnostics"]
        == legacy_payload["processing_metadata"]["qa_diagnostics"]
    )
    for metadata_key in (
        "display_mode",
        "baseline_lock_visual_only",
        "line_broadening",
        "zero_filling",
        "plotly_data_preparation",
        "qa_diagnostics",
        "analysis_artifact_policy",
        "reference_peak_selection",
    ):
        assert hybrid_payload["metadata"][metadata_key] == legacy_payload["metadata"][metadata_key]
    assert (
        hybrid_payload["metadata"]["raw_upload_provenance"]["sha256"]
        == legacy_payload["metadata"]["raw_upload_provenance"]["sha256"]
    )
    assert attached_sidecar["role"] == "sidecar_metadata_only"
    assert attached_sidecar["default_pipeline_preserved"] is True
    assert attached_sidecar["validation_report"]["visibility"] == "hidden_metadata_only"
    assert attached_sidecar["validation_report"]["safe_to_activate"] is False
    guidance = attached_sidecar["analysis_guidance"]
    assert guidance["visibility"] == "metadata_only"
    assert guidance["used_for_plot"] is False
    assert guidance["used_for_peak_markers"] is False
    assert guidance["used_for_phase_or_baseline"] is False


def test_legacy_fid_process_sidecar_is_saved_as_review_only_metadata(monkeypatch) -> None:
    request = _build_request()
    context = AccessContext(system_api_key=True)
    monkeypatch.setenv("MOLTRACE_RAW_FID_PIPELINE", HYBRID_METADATA_RAW_FID_PIPELINE)

    def fake_sidecar(**kwargs):
        return {
            "pipeline": "prompt_1_2",
            "role": "sidecar_metadata_only",
            "active": False,
            "available": True,
            "nucleus": kwargs.get("nucleus"),
            "solvent": kwargs.get("solvent"),
            "point_count": 65536,
            "peak_count": 3,
            "fingerprint_hash": "c" * 64,
            "runtime_ms": 1.0,
        }

    monkeypatch.setattr("nmrcheck.api.build_prompt_pipeline_sidecar", fake_sidecar)

    async def run_process():
        return await fid_process(
            request=request,
            file=_build_upload(),
            smiles="CCO",
            sample_id="legacy-adapter-process",
            workspace_project_id=None,
            workspace_sample_record_id=None,
            solvent="CDCl3",
            nucleus="1H",
            reference_ppm=None,
            reference_nmr_text=REFERENCE_TEXT,
            manual_nmr_text="3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)",
            selected_preset="balanced",
            zero_fill_factor=2,
            line_broadening_hz=0.3,
            apply_group_delay=True,
            auto_phase=True,
            auto_baseline=True,
            peak_sensitivity=0.08,
            mask_solvent_regions=False,
            context=context,
        )

    result = asyncio.run(run_process())

    assert result.generated_inputs.sample_id == "legacy-adapter-process"
    assert result.analysis.sample_id == "legacy-adapter-process"
    assert result.preview.preview_points
    assert result.preview.inferred_peaks
    sidecar = result.preview.metadata["prompt_pipeline_sidecar"]
    assert sidecar["role"] == "sidecar_metadata_only"
    assert sidecar["default_pipeline_preserved"] is True
    assert sidecar["validation_report"]["active_visible_pipeline"] == "legacy"
    assert sidecar["validation_report"]["safe_to_activate"] is False
    assert sidecar["analysis_guidance"]["used_for_plot"] is False
    assert sidecar["analysis_guidance"]["used_for_peak_markers"] is False
    assert sidecar["analysis_guidance"]["used_for_phase_or_baseline"] is False

    saved_runs = fid_runs(request=request, context=context, limit=1)
    assert saved_runs
    saved_sidecar = saved_runs[0].preview.metadata["prompt_pipeline_sidecar"]
    assert saved_sidecar["fingerprint_hash"] == "c" * 64
    assert saved_sidecar["default_pipeline_preserved"] is True


def _build_request() -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-fid-api-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/fid_api.sqlite3",
            require_verified_email=False,
            api_key="test-key",
            raw_fid_storage_dir=f"{tmpdir}/raw_fid_store",
            raw_data_vault_dir=f"{tmpdir}/raw_data_vault",
        )
    )
    init_db(app.state.session_factory)
    scope = {
        "type": "http",
        "app": app,
        "headers": [],
        "method": "POST",
        "path": "/fid/test",
        "query_string": b"",
    }
    return Request(scope)


def _build_bruker_zip(*, empty: bool = False) -> bytes:
    points = 1024
    sw_hz = 5000.0
    sfo1 = 500.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    if not empty:
        for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65), (2.1, 0.3)]:
            frequency_hz = (ppm - center_ppm) * sfo1
            fid += (
                amplitude
                * np.exp(2j * np.pi * frequency_hz * time_axis)
                * np.exp(-time_axis * 10.0)
            )
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = f"""##TITLE= synthetic beta regression
##$TD= {points * 2}
##$SW_h= {sw_hz}
##$SW= 10.0
##$SFO1= {sfo1}
##$BF1= {sfo1}
##$O1= {center_ppm * sfo1}
##$O1P= {center_ppm}
##$NUC1= <1H>
##$BYTORDA= 0
##$DTYPA= 0
##$GRPDLY= 0
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ethanol_raw/fid", interleaved.tobytes())
        archive.writestr("ethanol_raw/acqus", acqus)
        archive.writestr("ethanol_raw/pulseprogram", "zg30\n")
    return buffer.getvalue()


def _build_bruker_tar_gz() -> bytes:
    zip_content = _build_bruker_zip()
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(zip_content)) as source:
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name in source.namelist():
                data = source.read(name)
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _build_upload() -> UploadFile:
    return UploadFile(filename="bruker_dataset.zip", file=io.BytesIO(_build_bruker_zip()))


def _zip_bytes(entries: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _signal_free_baseline_fit_span(report) -> float:
    points = np.array([[point.shift_ppm, point.intensity] for point in report.preview_points])
    y_values = points[:, 1]
    signal_free = np.abs(y_values) <= np.percentile(np.abs(y_values), 35)
    if int(np.count_nonzero(signal_free)) < 3:
        return 0.0
    slope, _intercept = np.polyfit(points[:, 0][signal_free], y_values[signal_free], 1)
    return float(abs(slope) * (points[:, 0].max() - points[:, 0].min()))


async def _streaming_response_bytes(response) -> bytes:
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))
    return b"".join(chunks)


def test_fid_presets_endpoint_lists_expected_presets() -> None:
    presets = fid_presets()
    labels = [preset.label for preset in presets]
    assert labels == [
        "Baseline preserve",
        "Balanced",
        "Sensitive weak peaks",
        "Higher resolution",
        "Custom",
    ]
    by_id = {preset.id: preset for preset in presets}
    assert by_id["baseline_preserve"].settings["line_broadening_hz"] == 0.0
    assert by_id["baseline_preserve"].settings["auto_baseline"] is False
    assert by_id["baseline_preserve"].settings["baseline_correction"] == "preserve"
    assert by_id["balanced"].settings["zero_fill_factor"] == 2
    assert by_id["balanced"].settings["auto_baseline"] is True
    assert by_id["balanced"].settings["baseline_correction"] == "bernstein"
    assert by_id["balanced"].settings["baseline_order"] == 3
    assert by_id["sensitive_weak_peaks"].settings["auto_baseline"] is True
    assert by_id["higher_resolution"].settings["auto_baseline"] is True
    assert (
        by_id["sensitive_weak_peaks"].settings["peak_sensitivity"]
        < by_id["balanced"].settings["peak_sensitivity"]
    )
    assert (
        by_id["higher_resolution"].settings["zero_fill_factor"]
        > by_id["balanced"].settings["zero_fill_factor"]
    )


def test_raw_bruker_fid_qa_scores_usable_trace() -> None:
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="higher_resolution"),
    )
    qa = report.processing_metadata.qa_diagnostics
    assert report.processing_metadata.selected_preset == "Higher resolution"
    assert qa.quality_label in {"good", "review"}
    assert qa.quality_score >= 0.55
    assert qa.dynamic_range > 0
    assert qa.point_count >= 1024
    assert report.metadata["qa_diagnostics"]["quality_label"] == qa.quality_label


def test_raw_bruker_fid_preserves_ppm_orientation() -> None:
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="balanced"),
    )

    shifts = sorted(peak.shift_ppm for peak in report.inferred_peaks)
    assert any(abs(shift - 1.26) <= 0.05 for shift in shifts)
    assert any(abs(shift - 2.10) <= 0.05 for shift in shifts)
    assert any(abs(shift - 3.65) <= 0.05 for shift in shifts)
    assert report.processing_metadata.acquisition_parameters["ppm_axis_orientation"] == (
        "low_to_high_before_display_reverse"
    )


def test_raw_fid_provenance_records_hash_and_non_destructive_policy() -> None:
    content = _build_bruker_zip()
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=content,
        settings=fid_settings_from_preset(selected_preset="balanced"),
    )

    provenance = report.processing_metadata.raw_upload_provenance
    assert provenance["sha256"] == hashlib.sha256(content).hexdigest()
    assert provenance["byte_size"] == len(content)
    assert provenance["archive_format"] == "zip"
    assert provenance["raw_data_immutable"] is True
    assert provenance["raw_bytes_embedded_in_metadata"] is False
    assert provenance["storage_backend"] == "metadata_only"
    assert provenance["raw_archive_id"] == provenance["sha256"]
    assert provenance["vendor_detected"] == "Bruker"
    assert provenance["dataset_root"] == "ethanol_raw"
    assert provenance["acquisition_metadata"]["NUC1"] == "1H"
    policy = report.processing_metadata.analysis_artifact_policy
    assert policy["raw_upload_treated_as_immutable"] is True
    assert policy["raw_binary_modified"] is False
    assert policy["original_archive_modified"] is False
    assert policy["raw_overwrite_allowed"] is False
    assert policy["processing_operates_on"] == "temporary_extraction_and_in_memory_copies"
    assert report.metadata["raw_upload_provenance"]["sha256"] == provenance["sha256"]
    assert report.metadata["analysis_artifact_policy"]["processing_outputs_are_derivative"] is True
    assert report.processing_metadata.processing_recipe.processing_preset == "balanced"
    assert report.processing_metadata.processing_recipe.phase_mode in {
        "auto_acme",
        "auto_peak_minima",
        "auto_grid",
    }
    assert report.processing_metadata.processing_recipe.baseline_correction == "bernstein"
    assert report.processing_metadata.processing_recipe.baseline_order == 3
    assert report.processing_metadata.processing_recipe.display_mode == "real"


def test_raw_fid_processing_uses_verified_vault_bytes_as_source_of_truth(tmp_path) -> None:
    content = _build_bruker_zip()
    provenance = build_raw_upload_provenance(
        filename="bruker_dataset.zip",
        content=content,
        storage_dir=tmp_path / "raw_data_vault",
    )

    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=b"this request body is not the source of truth",
        settings=fid_settings_from_preset(selected_preset="balanced"),
        raw_upload_provenance=provenance,
    )

    stored_provenance = report.processing_metadata.raw_upload_provenance
    assert stored_provenance["processing_input_source"] == "immutable_vault_archive"
    assert stored_provenance["processing_loaded_from_vault"] is True
    assert (
        report.processing_metadata.analysis_artifact_policy["processing_loaded_from_vault"]
        is True
    )
    assert report.processing_metadata.raw_upload_provenance["sha256"] == provenance["sha256"]
    assert report.point_count > 0


def test_raw_fid_tar_gz_archive_is_accepted_without_mutating_raw_bytes() -> None:
    content = _build_bruker_tar_gz()
    before_hash = hashlib.sha256(content).hexdigest()

    report = process_bruker_1d_zip(
        filename="bruker_dataset.tar.gz",
        content=content,
        settings=fid_settings_from_preset(selected_preset="balanced"),
    )

    assert hashlib.sha256(content).hexdigest() == before_hash
    assert report.processing_metadata.raw_upload_provenance["sha256"] == before_hash
    assert report.processing_metadata.raw_upload_provenance["archive_format"] == "tar.gz"
    assert report.processing_metadata.acquisition_parameters["raw_archive_format"] == "tar.gz"
    assert report.processing_metadata.raw_dataset_files_found["fid"] is True
    assert report.processing_metadata.raw_dataset_files_found["acqus"] is True


def test_raw_fid_tar_gz_processing_rejects_links_even_if_provenance_is_prebuilt() -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = b"\x00" * 128
        fid = tarfile.TarInfo("ethanol_raw/fid")
        fid.size = len(payload)
        archive.addfile(fid, io.BytesIO(payload))
        acqus_payload = b"""##TITLE= linked tar test
##$TD= 256
##$SW_h= 5000.0
##$SW= 10.0
##$SFO1= 500.0
##$BF1= 500.0
##$O1= 2000.0
##$O1P= 4.0
##$NUC1= <1H>
##$BYTORDA= 0
##$DTYPA= 0
##$GRPDLY= 0
"""
        acqus = tarfile.TarInfo("ethanol_raw/acqus")
        acqus.size = len(acqus_payload)
        archive.addfile(acqus, io.BytesIO(acqus_payload))
        hardlink = tarfile.TarInfo("ethanol_raw/link_to_fid")
        hardlink.type = tarfile.LNKTYPE
        hardlink.linkname = "ethanol_raw/fid"
        archive.addfile(hardlink)

    with pytest.raises(FIDProcessingError, match="link"):
        process_bruker_1d_zip(
            filename="linked.tar.gz",
            content=buffer.getvalue(),
            settings=fid_settings_from_preset(selected_preset="balanced"),
            raw_upload_provenance={"sha256": "0" * 64, "storage_backend": "metadata_only"},
        )


def test_raw_bruker_fid_preserves_baseline_by_default_and_separates_display_metadata() -> None:
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="balanced"),
    )

    baseline = report.processing_metadata.baseline_correction
    assert baseline["method"] == "bernstein_polynomial"
    assert baseline["baseline_correction"] == "bernstein"
    assert baseline["baseline_order"] == 3
    assert baseline["correction_applied"] is True
    assert baseline["baseline_locked_to_zero"] is True
    assert report.metadata["evidence_trace_mode"] == "raw_fid_fft_real_baseline_corrected"
    assert report.metadata["display_mode"] == "real"
    assert report.metadata["display_gain"] == 1.0
    assert report.metadata["baseline_lock_visual_only"] is True
    assert report.metadata["preview_downsampling"]["method"] == "min_max_lttb_envelope"
    assert "raw_preview_points" not in report.metadata
    assert report.metadata["display_preprocessing"]["display_baseline"] == 0.0
    assert report.metadata["display_preprocessing"]["baseline_smoothing"]["applied"] is False
    original_state = report.metadata["original_spectrum_state"]
    assert original_state["preserved"] is True
    assert original_state["processing_stage"] == "post_fft_phase_pre_baseline"
    assert original_state["preview_points"] == []
    assert original_state["preview_points_omitted"] is True
    assert report.metadata["baseline_flatness_qa"]["label"] in {"flat", "review", "distorted"}


def test_raw_bruker_fid_explicit_baseline_correction_still_corrects_evidence() -> None:
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="balanced", auto_baseline=True),
    )

    baseline = report.processing_metadata.baseline_correction
    assert baseline["method"] == "bernstein_polynomial"
    assert baseline["baseline_correction"] == "bernstein"
    assert baseline["baseline_order"] == 3
    assert baseline["baseline_locked_to_zero"] is True
    assert baseline["baseline_model"] == "bernstein_polynomial"
    assert baseline["baseline_points"] >= 4
    assert baseline["flatness_qa"]["label"] in {"flat", "review"}
    assert report.metadata["evidence_trace_mode"] == "raw_fid_fft_real_baseline_corrected"


def test_raw_bruker_fid_empty_trace_returns_failed_qa() -> None:
    report = process_bruker_1d_zip(
        filename="bruker_dataset.zip",
        content=_build_bruker_zip(empty=True),
    )
    qa = report.processing_metadata.qa_diagnostics
    assert qa.quality_label == "failed"
    assert qa.quality_score == 0.0
    assert qa.dynamic_range == 0.0
    assert qa.point_count >= 1024
    assert report.inferred_peaks == []
    assert any("appears empty" in warning for warning in qa.warnings)


def test_raw_bruker_fid_rejects_invalid_zip() -> None:
    with pytest.raises(FIDProcessingError, match="valid .zip"):
        process_bruker_1d_zip(filename="bruker_dataset.zip", content=b"not a zip")


def test_raw_bruker_fid_rejects_missing_fid() -> None:
    content = _zip_bytes({"sample/acqus": "##$SFO1= 500\n"})
    with pytest.raises(FIDProcessingError, match="required fid file is missing"):
        process_bruker_1d_zip(filename="bruker_dataset.zip", content=content)


def test_raw_bruker_fid_rejects_missing_acqus() -> None:
    content = _zip_bytes({"sample/fid": b"\x00" * 128})
    with pytest.raises(FIDProcessingError, match="required acqus file is missing"):
        process_bruker_1d_zip(filename="bruker_dataset.zip", content=content)


def test_raw_bruker_fid_rejects_zip_path_traversal() -> None:
    content = _zip_bytes({"sample/../evil/fid": b"\x00" * 128, "sample/acqus": "##$SFO1= 500\n"})
    with pytest.raises(FIDProcessingError, match="unsafe relative path"):
        process_bruker_1d_zip(filename="bruker_dataset.zip", content=content)


def test_raw_bruker_fid_preview_process_and_report_evidence() -> None:
    request = _build_request()
    context = AccessContext(system_api_key=True)

    async def run() -> None:
        preview = await fid_preview(
            request=request,
            file=_build_upload(),
            sample_id="fid-ethanol",
            workspace_sample_record_id=None,
            solvent="CDCl3",
            nucleus="1H",
            reference_ppm=None,
            reference_nmr_text=REFERENCE_TEXT,
            smiles="CCO",
            selected_preset="balanced",
            zero_fill_factor=2,
            line_broadening_hz=0.3,
            apply_group_delay=True,
            auto_phase=True,
            auto_baseline=True,
            peak_sensitivity=0.08,
            mask_solvent_regions=False,
            context=context,
        )

        assert preview.format_detected == "bruker_fid_zip"
        assert preview.processing_metadata.vendor_format_detected == "Bruker 1D"
        assert preview.processing_metadata.raw_dataset_files_found["fid"] is True
        assert preview.processing_metadata.raw_dataset_files_found["acqus"] is True
        assert preview.processing_metadata.selected_preset == "Balanced"
        assert preview.processing_metadata.qa_diagnostics.quality_label in {"good", "review"}
        assert preview.processing_metadata.reviewer_signoff_required is True
        provenance = preview.processing_metadata.raw_upload_provenance
        assert len(provenance["sha256"]) == 64
        assert preview.fid_run_id is None
        assert provenance["storage_backend"] == "metadata_only"
        assert provenance["storage_status"] == "not_configured"
        assert provenance["legacy_endpoint"] == "/fid/preview"
        assert any("/raw-fid/upload" in note for note in provenance["warnings"])
        assert provenance["raw_archive_id"] == provenance["sha256"]
        assert provenance["dataset_root"] == "ethanol_raw"
        assert preview.reference_nmr_text_normalized is not None
        assert preview.comparison is not None
        assert preview.point_count > 0

        result = await fid_process(
            request=request,
            file=_build_upload(),
            smiles="CCO",
            sample_id="fid-ethanol",
            workspace_project_id=None,
            workspace_sample_record_id=None,
            solvent="CDCl3",
            nucleus="1H",
            reference_ppm=None,
            reference_nmr_text=REFERENCE_TEXT,
            manual_nmr_text="3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)",
            selected_preset="balanced",
            zero_fill_factor=2,
            line_broadening_hz=0.3,
            apply_group_delay=True,
            auto_phase=True,
            auto_baseline=True,
            peak_sensitivity=0.08,
            mask_solvent_regions=False,
            context=context,
        )

        assert result.generated_inputs.sample_id == "fid-ethanol"
        assert result.analysis.sample_id == "fid-ethanol"
        assert any("Raw FID beta" in note for note in result.analysis.notes)
        assert result.preview.fid_run_id is not None

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"nmrglue\..*")
        warnings.filterwarnings("ignore", category=UserWarning, module=r"nmrglue\.fileio\.bruker")
        asyncio.run(run())

    saved_runs = fid_runs(request=request, context=context, limit=10)
    assert len(saved_runs) >= 1
    processed_run = saved_runs[0]
    assert processed_run.analysis_id is not None
    assert (
        processed_run.raw_archive_id
        == processed_run.processing_metadata.raw_upload_provenance["raw_archive_db_id"]
    )
    assert (
        processed_run.raw_sha256
        == processed_run.processing_metadata.raw_upload_provenance["sha256"]
    )
    provenance = processed_run.processing_metadata.raw_upload_provenance
    assert provenance["storage_backend"] == "local_raw_vault"
    assert provenance["storage_status"] == "stored"
    assert provenance["read_only"] is True
    assert provenance["raw_archive_id"] == provenance["sha256"]
    assert provenance["raw_archive_record"]["sha256"] == provenance["sha256"]
    assert provenance["raw_archive_record"]["required_files_present"] is True
    assert any("/raw-fid/upload" in note for note in provenance["warnings"])
    db_archive = get_raw_archive_by_sha256(
        request.app.state.session_factory,
        sha256=provenance["sha256"],
    )
    assert db_archive is not None
    assert db_archive.id == provenance["raw_archive_db_id"]
    assert db_archive.storage_path == provenance["storage_path"]
    stored_path = provenance["storage_path"]
    assert os.path.isfile(stored_path)
    assert "/raw_data_vault/" in stored_path
    assert os.stat(stored_path).st_mode & stat.S_IWUSR == 0
    with open(stored_path, "rb") as handle:
        assert hashlib.sha256(handle.read()).hexdigest() == provenance["sha256"]
    assert processed_run.processing_recipe["phase_mode"] in {
        "auto_acme",
        "auto_peak_minima",
        "auto_grid",
    }
    assert processed_run.processing_recipe["baseline_correction"] == "bernstein"
    assert processed_run.processing_recipe["baseline_order"] == 3
    assert processed_run.processing_recipe["zero_fill_factor"] == 2
    assert processed_run.processing_recipe["apodization_mode"] == "exponential"
    assert processed_run.processing_recipe["line_broadening_hz"] == 0.3
    assert processed_run.processing_recipe["digital_filter_correction"]
    assert processed_run.processing_recipe["reference_ppm"] is None
    assert processed_run.processing_recipe["solvent"] == "CDCl3"
    assert processed_run.processing_recipe["peak_sensitivity"] == 0.08
    assert processed_run.processing_recipe["mask_solvent_regions"] is False
    assert processed_run.processing_recipe["display_mode"] == "real"
    assert processed_run.processing_recipe["vertical_gain"] == 1.0
    assert processed_run.processing_recipe["debug_preview"] is False
    assert processed_run.derived_spectrum_metadata["format_detected"] == "bruker_fid_zip"
    assert (
        processed_run.derived_spectrum_metadata["point_count"]
        == processed_run.preview.point_count
    )
    assert processed_run.derived_spectrum_metadata["raw_dataset_files_found"]["fid"] is True
    assert processed_run.review_status == "pending_review"
    assert processed_run.processing_metadata.reference_peak_selection[
        "selected_peak_count"
    ] in {0, 1}

    run_report = fid_run_report(processed_run.id, request, context)
    assert run_report.run.id == processed_run.id
    assert run_report.raw_fid_provenance["vendor_format_detected"] == "Bruker 1D"
    assert run_report.processing_assumptions["selected_preset"] == "Balanced"
    assert run_report.qa_diagnostics.quality_label in {"good", "review"}
    assert len(run_report.inferred_peak_list) >= 1
    assert run_report.run.review_decision_count == 0

    decision = fid_run_approve(
        processed_run.id,
        FIDRunReviewCreate(comment="Approved FID run in regression test"),
        request,
        context,
    )
    assert decision.new_status == "approved"
    decisions = fid_run_review_decisions(processed_run.id, request, context)
    assert len(decisions) == 1
    approved_report = fid_run_report(processed_run.id, request, context)
    assert approved_report.run.review_status == "approved"
    assert approved_report.run.reviewer_comment == "Approved FID run in regression test"
    assert approved_report.run.review_decision_count == 1
    assert approved_report.run.processing_recipe["reviewer_status"] == "approved"
    html = fid_run_report_html(processed_run.id, request, context)
    assert "FID Run Evidence Report" in html.body.decode("utf-8")
    package = fid_run_package(processed_run.id, request, context)
    package_bytes = asyncio.run(_streaming_response_bytes(package))
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        names = set(archive.namelist())
        assert "analysis.json" in names
        assert "processing_metadata.json" in names
        assert "raw_upload_provenance.json" in names
        assert "raw_archive_export_manifest.json" in names
        provenance = json.loads(archive.read("raw_upload_provenance.json"))
        manifest = json.loads(archive.read("raw_archive_export_manifest.json"))
        assert (
            provenance["sha256"]
            == processed_run.processing_metadata.raw_upload_provenance["sha256"]
        )
        assert manifest["sha256"] == provenance["sha256"]
        assert manifest["raw_archive"]["id"] == provenance["raw_archive_db_id"]
        assert manifest["sha256_verified"] is True
        original_names = [
            name
            for name in names
            if name.startswith("original/") and not name.endswith(".txt")
        ]
        assert original_names
        original_bytes = archive.read(original_names[0])
        assert hashlib.sha256(original_bytes).hexdigest() == provenance["sha256"]

    latest = list_recent_analyses(request.app.state.session_factory, limit=1)[0]
    report = evidence_report_json(latest.id, request, context=context)
    raw_fid = report.audit_metadata["raw_fid_processing"]
    assert raw_fid["vendor_format_detected"] == "Bruker 1D"
    assert raw_fid["raw_dataset_files_found"]["fid"] is True
    assert raw_fid["raw_dataset_files_found"]["acqus"] is True
    assert raw_fid["automatic_phase_correction"] is True
    assert raw_fid["automatic_baseline_correction"] is True
    assert raw_fid["selected_preset"] == "Balanced"
    assert raw_fid["digital_filter_correction_status"] in {"applied", "not_detected"}
    assert raw_fid["qa_diagnostics"]["quality_label"] in {"good", "review"}
    assert raw_fid["human_review_status"] == "pending_review"

    stored = report_from_analysis(latest.id, request, context)
    assert stored.report.audit_metadata["raw_fid_processing"]["reviewer_signoff_required"] is True


def test_raw_fid_vault_endpoints_upload_preview_process_runs_download_and_export(tmp_path) -> None:
    content = _build_bruker_zip()
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'raw_fid_endpoints.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_data_vault_dir=str(tmp_path / "raw_data_vault"),
        )
    )
    headers = {"x-api-key": "test-key"}

    with TestClient(app) as client:
        upload = client.post(
            "/raw-fid/upload",
            headers=headers,
            files={"file": ("ethanol_raw.zip", content, "application/zip")},
        )
        assert upload.status_code == 200, upload.text
        archive = upload.json()
        archive_id = archive["raw_archive_id"]
        assert archive_id == hashlib.sha256(content).hexdigest()
        assert archive["required_files_present"] is True

        detail = client.get(f"/raw-fid/{archive_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        detail_json = detail.json()
        assert detail_json["raw_bytes_returned"] is False
        assert detail_json["integrity"]["sha256_verified"] is True

        download = client.get(f"/raw-fid/{archive_id}/download", headers=headers)
        assert download.status_code == 200, download.text
        assert download.content == content

        preview = client.post(
            f"/raw-fid/{archive_id}/preview",
            headers=headers,
            data={
                "solvent": "CDCl3",
                "reference_nmr_text": REFERENCE_TEXT,
                "selected_preset": "balanced",
            },
        )
        assert preview.status_code == 200, preview.text
        preview_json = preview.json()
        assert preview_json["fid_run_id"] is None
        assert (
            preview_json["processing_metadata"]["raw_upload_provenance"]["processing_input_source"]
            == "immutable_vault_archive"
        )

        runs_before = client.get(f"/raw-fid/{archive_id}/runs", headers=headers)
        assert runs_before.status_code == 200, runs_before.text
        assert runs_before.json() == []

        processed = client.post(
            f"/raw-fid/{archive_id}/process",
            headers=headers,
            data={
                "smiles": "CCO",
                "sample_id": "raw-fid-vault-endpoint",
                "solvent": "CDCl3",
                "manual_nmr_text": REFERENCE_TEXT,
                "selected_preset": "balanced",
                "baseline_correction": "bernstein",
                "baseline_order": "3",
            },
        )
        assert processed.status_code == 200, processed.text
        process_json = processed.json()
        assert process_json["preview"]["fid_run_id"] is not None
        assert (
            process_json["preview"]["processing_metadata"]["processing_recipe"][
                "baseline_correction"
            ]
            == "bernstein"
        )

        runs_after = client.get(f"/raw-fid/{archive_id}/runs", headers=headers)
        assert runs_after.status_code == 200, runs_after.text
        runs = runs_after.json()
        assert len(runs) == 1
        assert runs[0]["raw_sha256"] == archive_id
        assert runs[0]["raw_archive_id"] == archive["id"]

        export = client.get(f"/raw-fid/{archive_id}/export", headers=headers)
        assert export.status_code == 200, export.text
        with zipfile.ZipFile(io.BytesIO(export.content)) as package:
            names = set(package.namelist())
            assert "raw/original_archive.zip" in names
            assert "analysis/analysis.json" in names
            assert "analysis/processing_recipe.json" in names
            assert "analysis/acquisition_metadata.json" in names
            assert "analysis/peak_list.csv" in names
            assert "analysis/spectrum_preview.json" in names
            assert "analysis/evidence_report.json" in names
            assert "analysis/audit_trail.json" in names
            assert "manifest.json" in names
            assert (
                hashlib.sha256(package.read("raw/original_archive.zip")).hexdigest()
                == archive_id
            )
            manifest = json.loads(package.read("manifest.json"))
            assert manifest["raw_archive_id"] == archive_id
            assert manifest["original_archive_included"] is True
            assert manifest["hashes"]["raw/original_archive.zip"] == archive_id
            assert (
                manifest["hashes"]["analysis/processing_recipe.json"]
                == hashlib.sha256(package.read("analysis/processing_recipe.json")).hexdigest()
            )
            assert (
                manifest["hashes"]["analysis/analysis.json"]
                == hashlib.sha256(package.read("analysis/analysis.json")).hexdigest()
            )
            assert (
                manifest["hashes"]["analysis/peak_list.csv"]
                == hashlib.sha256(package.read("analysis/peak_list.csv")).hexdigest()
            )
            assert (
                manifest["hashes"]["analysis/evidence_report.json"]
                == hashlib.sha256(package.read("analysis/evidence_report.json")).hexdigest()
            )
            assert manifest["non_destructive_guarantees"]["original_fid_replaced"] is False
            assert (
                manifest["non_destructive_guarantees"]["processed_files_written_into_raw_vendor_folder"]
                is False
            )
            audit_trail = json.loads(package.read("analysis/audit_trail.json"))
            event_types = {event["event_type"] for event in audit_trail}
            assert "raw_fid.uploaded" in event_types
            assert "raw_fid.hash_verified" in event_types
            assert "raw_fid.metadata_extracted" in event_types
            assert "raw_fid.previewed" in event_types
            assert "raw_fid.processed" in event_types
            assert "raw_fid.exported" in event_types


def test_raw_fid_vault_prompt_sidecar_is_metadata_only_and_non_disruptive(
    tmp_path,
    monkeypatch,
) -> None:
    content = _build_bruker_zip()
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'raw_fid_sidecar_endpoints.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_data_vault_dir=str(tmp_path / "raw_data_vault"),
        )
    )
    headers = {"x-api-key": "test-key"}
    sidecar_calls: list[dict[str, object]] = []

    def fake_sidecar(**kwargs):
        sidecar_calls.append(dict(kwargs))
        return {
            "pipeline": "prompt_1_2",
            "role": "sidecar_metadata_only",
            "active": False,
            "available": True,
            "nucleus": kwargs.get("nucleus"),
            "solvent": kwargs.get("solvent"),
            "point_count": 65536,
            "peak_count": 888,
            "fingerprint_hash": "d" * 64,
            "runtime_ms": 1.0,
            "preview_points": [{"shift_ppm": 888.0, "intensity": 888.0}],
            "inferred_peaks": [{"shift_ppm": 888.0, "intensity": 888.0}],
            "plotly_traces": [{"x": [888.0], "y": [888.0]}],
            "vertical_peak_guides": {"visible": True},
            "phase": {"zero_order_degrees": 180.0},
            "baseline": {"method": "prompt_replacement"},
            "metadata": {
                "raw_fid_peak_guidance": {
                    "peak_evidence_policy": "fabricate_reference_peaks",
                    "used_for_plot": True,
                    "used_for_peak_markers": True,
                },
                "spectrum_points_included": True,
            },
            "raw_fid_peak_guidance": {
                "used_for_plot": True,
                "used_for_peak_markers": True,
            },
        }

    monkeypatch.setattr("nmrcheck.api.build_prompt_pipeline_sidecar", fake_sidecar)

    with TestClient(app) as client:
        upload = client.post(
            "/raw-fid/upload",
            headers=headers,
            files={"file": ("ethanol_raw.zip", content, "application/zip")},
        )
        assert upload.status_code == 200, upload.text
        archive_id = upload.json()["raw_archive_id"]

        preview_payload = {
            "solvent": "CDCl3",
            "reference_nmr_text": REFERENCE_TEXT,
            "selected_preset": "balanced",
        }
        process_payload = {
            "smiles": "CCO",
            "sample_id": "raw-fid-vault-sidecar",
            "solvent": "CDCl3",
            "manual_nmr_text": REFERENCE_TEXT,
            "selected_preset": "balanced",
            "baseline_correction": "bernstein",
            "baseline_order": "3",
        }

        monkeypatch.delenv(RAW_FID_PIPELINE_ENV, raising=False)
        legacy_preview = client.post(
            f"/raw-fid/{archive_id}/preview",
            headers=headers,
            data=preview_payload,
        )
        assert legacy_preview.status_code == 200, legacy_preview.text
        legacy_process = client.post(
            f"/raw-fid/{archive_id}/process",
            headers=headers,
            data=process_payload,
        )
        assert legacy_process.status_code == 200, legacy_process.text
        assert sidecar_calls == []

        monkeypatch.setenv(RAW_FID_PIPELINE_ENV, HYBRID_METADATA_RAW_FID_PIPELINE)
        hybrid_preview = client.post(
            f"/raw-fid/{archive_id}/preview",
            headers=headers,
            data=preview_payload,
        )
        assert hybrid_preview.status_code == 200, hybrid_preview.text
        hybrid_process = client.post(
            f"/raw-fid/{archive_id}/process",
            headers=headers,
            data={**process_payload, "sample_id": "raw-fid-vault-sidecar-hybrid"},
        )
        assert hybrid_process.status_code == 200, hybrid_process.text

    assert len(sidecar_calls) == 2

    legacy_preview_json = legacy_preview.json()
    hybrid_preview_json = hybrid_preview.json()
    preview_sidecar = hybrid_preview_json["metadata"].pop("prompt_pipeline_sidecar")
    assert "prompt_pipeline_sidecar" not in legacy_preview_json["metadata"]
    assert hybrid_preview_json["preview_points"] == legacy_preview_json["preview_points"]
    assert hybrid_preview_json["inferred_peaks"] == legacy_preview_json["inferred_peaks"]
    assert hybrid_preview_json["inferred_nmr_text"] == legacy_preview_json["inferred_nmr_text"]
    assert hybrid_preview_json["reference_peaks"] == legacy_preview_json["reference_peaks"]
    assert hybrid_preview_json["comparison"] == legacy_preview_json["comparison"]
    assert hybrid_preview_json["warnings"] == legacy_preview_json["warnings"]
    assert len(hybrid_preview_json["inferred_peaks"]) != 888
    assert preview_sidecar["preview_points"] == [{"shift_ppm": 888.0, "intensity": 888.0}]
    assert preview_sidecar["inferred_peaks"] == [{"shift_ppm": 888.0, "intensity": 888.0}]
    assert preview_sidecar["validation_report"]["active_visible_pipeline"] == "legacy"
    assert preview_sidecar["validation_report"]["safe_to_activate"] is False
    assert preview_sidecar["analysis_guidance"]["used_for_plot"] is False
    assert preview_sidecar["analysis_guidance"]["used_for_peak_markers"] is False
    assert preview_sidecar["analysis_guidance"]["used_for_phase_or_baseline"] is False

    legacy_process_json = legacy_process.json()
    hybrid_process_json = hybrid_process.json()
    legacy_process_preview = legacy_process_json["preview"]
    hybrid_process_preview = hybrid_process_json["preview"]
    process_sidecar = hybrid_process_preview["metadata"].pop("prompt_pipeline_sidecar")
    assert "prompt_pipeline_sidecar" not in legacy_process_preview["metadata"]
    assert hybrid_process_preview["preview_points"] == legacy_process_preview["preview_points"]
    assert hybrid_process_preview["inferred_peaks"] == legacy_process_preview["inferred_peaks"]
    assert hybrid_process_preview["inferred_nmr_text"] == legacy_process_preview["inferred_nmr_text"]
    assert len(hybrid_process_preview["inferred_peaks"]) != 888
    assert hybrid_process_json["generated_inputs"]["nmr_text"] == legacy_process_json["generated_inputs"]["nmr_text"]
    assert hybrid_process_json["analysis"]["parsed_peak_count"] == legacy_process_json["analysis"]["parsed_peak_count"]
    assert process_sidecar["metadata"]["raw_fid_peak_guidance"]["used_for_plot"] is True
    assert process_sidecar["analysis_guidance"]["used_for_plot"] is False
    assert process_sidecar["analysis_guidance"]["used_for_peak_markers"] is False
    assert process_sidecar["analysis_guidance"]["used_for_phase_or_baseline"] is False
