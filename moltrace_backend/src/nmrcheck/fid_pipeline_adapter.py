"""Default-off adapter for the newer Prompt 1/2 raw-FID pipeline.

This module is intentionally non-invasive.  The existing SpectraCheck raw-FID
processor remains the runtime source of preview/process spectra unless a later
phase explicitly wires a different mode into the API.  Phase 1 only gives us a
safe place to collect Prompt 1/2 sidecar metadata and regression-test that the
legacy spectrum output is preserved.
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from .models import FIDPreviewReport

RAW_FID_PIPELINE_ENV = "MOLTRACE_RAW_FID_PIPELINE"
LEGACY_RAW_FID_PIPELINE = "legacy"
HYBRID_METADATA_RAW_FID_PIPELINE = "hybrid_metadata"

_PIPELINE_ALIASES = {
    "": LEGACY_RAW_FID_PIPELINE,
    "default": LEGACY_RAW_FID_PIPELINE,
    "current": LEGACY_RAW_FID_PIPELINE,
    "legacy": LEGACY_RAW_FID_PIPELINE,
    "off": LEGACY_RAW_FID_PIPELINE,
    "hybrid": HYBRID_METADATA_RAW_FID_PIPELINE,
    "hybrid_metadata": HYBRID_METADATA_RAW_FID_PIPELINE,
    "metadata": HYBRID_METADATA_RAW_FID_PIPELINE,
    "sidecar": HYBRID_METADATA_RAW_FID_PIPELINE,
}


def resolve_raw_fid_pipeline_mode(
    raw_value: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Return the selected raw-FID pipeline mode.

    Unknown values deliberately fall back to ``legacy`` so a typo or deployment
    config error cannot replace the tuned SpectraCheck raw-FID behavior.
    """

    source = environ if environ is not None else os.environ
    value = raw_value if raw_value is not None else source.get(RAW_FID_PIPELINE_ENV, "")
    normalized = str(value or "").strip().lower().replace("-", "_")
    return _PIPELINE_ALIASES.get(normalized, LEGACY_RAW_FID_PIPELINE)


def should_build_prompt_sidecar(mode: str | None = None) -> bool:
    """True when Prompt 1/2 should run as metadata-only sidecar."""

    return resolve_raw_fid_pipeline_mode(mode) == HYBRID_METADATA_RAW_FID_PIPELINE


def build_prompt_pipeline_sidecar(
    *,
    filename: str,
    content: bytes,
    nucleus: str | None = None,
    solvent: str | None = None,
    baseline_method: str | None = None,
    baseline_order: int = 3,
    strict: bool = False,
) -> dict[str, Any]:
    """Run Prompt 1/2 as sidecar metadata without changing plotted spectra.

    The sidecar is for future validation/comparison only.  It returns compact,
    deterministic metadata and never mutates the active report.  By default,
    failures are captured as warnings so optional experiments cannot break
    upload/preview/process flows.
    """

    started_at = time.perf_counter()
    try:
        from moltrace.spectroscopy.io.fid_reader import read_fid
        from moltrace.spectroscopy.preprocess.phase_baseline import (
            auto_phase_correct,
            baseline_correct,
        )

        with TemporaryDirectory(prefix="moltrace-fid-sidecar-") as tmp:
            archive_path = Path(tmp) / _safe_archive_name(filename)
            archive_path.write_bytes(content)
            spectrum = read_fid(archive_path)
            phased = auto_phase_correct(spectrum, method="regions_analysis")
            corrected = baseline_correct(
                phased,
                method=baseline_method
                or _default_baseline_method(nucleus or spectrum.nucleus),
                order=baseline_order,
            )
        return _sidecar_from_spectrum(
            corrected,
            requested_nucleus=nucleus,
            requested_solvent=solvent,
            baseline_method=baseline_method,
            baseline_order=baseline_order,
            runtime_ms=_elapsed_ms(started_at),
        )
    except Exception as exc:  # pragma: no cover - exact optional dependency errors vary
        if strict:
            raise
        return {
            "pipeline": "prompt_1_2",
            "role": "sidecar_metadata_only",
            "active": False,
            "available": False,
            "runtime_ms": _elapsed_ms(started_at),
            "warnings": [f"{exc.__class__.__name__}: {exc}"],
        }


def attach_prompt_pipeline_sidecar(
    report: FIDPreviewReport,
    sidecar: Mapping[str, Any] | None,
    *,
    mode: str | None = None,
) -> FIDPreviewReport:
    """Attach Prompt 1/2 sidecar metadata without touching spectral fields."""

    if not sidecar or not should_build_prompt_sidecar(mode):
        return report
    sidecar_payload = dict(sidecar)
    validation_report = build_prompt_pipeline_validation_report(
        report,
        sidecar_payload,
    )
    sidecar_payload["validation_report"] = validation_report
    sidecar_payload["analysis_guidance"] = build_prompt_pipeline_analysis_guidance(
        report,
        sidecar_payload,
        validation_report=validation_report,
    )
    metadata = dict(report.metadata or {})
    metadata["prompt_pipeline_sidecar"] = {
        **sidecar_payload,
        "default_pipeline_preserved": True,
    }
    return report.model_copy(update={"metadata": metadata})


def build_prompt_pipeline_runtime_contract(report: FIDPreviewReport) -> dict[str, Any]:
    """Describe how Prompt 1/2 is merged into the active raw-FID layer.

    This contract is intentionally cheap to build: it does not re-read or
    reprocess the upload.  It records the active SpectraCheck raw-FID settings
    beside the Prompt 1/2 module locations and acceptance gates so API routes,
    saved previews, and regression tests have one authoritative integration
    record while preserving the visible spectrum output.
    """

    metadata = report.metadata if isinstance(report.metadata, Mapping) else {}
    zero_filling = _mapping(metadata.get("zero_filling"))
    line_broadening = _mapping(metadata.get("line_broadening"))
    phase_settings = _mapping(metadata.get("phase_settings")) or _mapping(
        metadata.get("phase")
    )
    baseline_correction = _mapping(metadata.get("baseline_correction")) or _mapping(
        metadata.get("baseline")
    )
    processing_recipe = _mapping(metadata.get("processing_recipe"))
    processing_parameters = _mapping(metadata.get("processing_parameters"))
    acquisition_parameters = _mapping(metadata.get("acquisition_parameters"))
    artifact_policy = _mapping(metadata.get("analysis_artifact_policy"))
    provenance = _mapping(metadata.get("raw_upload_provenance"))
    nucleus = str(_metadata_value(metadata, "nucleus") or "").strip() or None
    normalized_nucleus = str(nucleus or "").upper()
    if normalized_nucleus == "13C":
        prompt_line_broadening = 2.0
    elif normalized_nucleus == "1H":
        prompt_line_broadening = 0.5
    else:
        prompt_line_broadening = None
    field_mhz = _safe_float(
        _first_present(
            acquisition_parameters.get("field_mhz"),
            metadata.get("field_mhz"),
            metadata.get("spectrometer_frequency_mhz"),
        )
    )
    active_line_broadening = _safe_float(
        _first_present(
            line_broadening.get("hz"),
            line_broadening.get("line_broadening_hz"),
            processing_parameters.get("line_broadening_hz"),
        )
    )
    active_zero_fill = _safe_int(
        _first_present(
            zero_filling.get("factor"),
            zero_filling.get("zero_fill_factor"),
            processing_parameters.get("zero_fill_factor"),
        )
    )
    raw_sha256 = _first_present(
        artifact_policy.get("raw_sha256"),
        provenance.get("sha256"),
        provenance.get("raw_sha256"),
    )
    active_baseline_method = _baseline_method(baseline_correction)
    active_phase_method = _first_present(
        phase_settings.get("phase_mode"),
        phase_settings.get("method"),
        phase_settings.get("mode"),
    )
    return {
        "version": "raw_fid_prompt_1_2_runtime_contract_v1",
        "scope": "raw_fid_only",
        "visibility": "metadata_only",
        "integration_status": "merged_with_active_raw_fid_layer",
        "active_visible_pipeline": "legacy_raw_fid_processor",
        "visible_spectrum_source": "nmrcheck.fid.process_bruker_1d_zip",
        "visible_spectrum_fields_preserved": True,
        "processed_uploads_touched": False,
        "prompt_pipeline_active": False,
        "used_for_plot": False,
        "used_for_peak_markers": False,
        "used_for_phase_or_baseline_swap": False,
        "sidecar_activation_policy": (
            "metadata_only_until_fixture_report_is_reviewed_and_explicitly_promoted"
        ),
        "prompt_1_fid_reader": {
            "module": "moltrace.spectroscopy.io.fid_reader.read_fid",
            "status": "available_for_sidecar_validation",
            "supported_vendors": ["Bruker", "Varian/Agilent"],
            "required_output": [
                "data",
                "ppm_axis",
                "metadata",
                "nucleus",
                "solvent",
                "field_mhz",
                "acquisition_time",
            ],
            "zero_fill_points": 65536,
            "apodization_hz_by_nucleus": {"1H": 0.5, "13C": 2.0},
        },
        "prompt_2_phase_baseline": {
            "module": "moltrace.spectroscopy.preprocess.phase_baseline",
            "status": "available_for_sidecar_validation",
            "phase_default_method": "regions_analysis",
            "baseline_default_method_by_nucleus": {
                "1H": "bernstein",
                "13C": "whittaker",
            },
            "baseline_default_order": 3,
        },
        "prompt_3_gsd_peak_picker": {
            "module": "moltrace.spectroscopy.peaks.gsd",
            "status": "available_for_sidecar_validation",
            "default_level": 2,
            "fit_models_by_level": {
                "1": "lorentzian",
                "2": "pseudo_voigt",
                "3": "overlap_group_pseudo_voigt",
                "4": "iterative_pseudo_voigt_metadata_only",
                "5": "iterative_pseudo_voigt_metadata_only",
            },
            "classification_targets": [
                "compound",
                "solvent",
                "impurity",
                "artifact",
                "13C_satellite",
            ],
            "classification_sources": [
                "nmrcheck.nmr_tables",
                "nmrcheck.impurities",
                "nmrcheck.peak_categorization",
            ],
            "prompt_pipeline_active": False,
            "used_for_plot": False,
            "used_for_peak_markers": False,
            "used_for_visible_spectrum": False,
        },
        "active_runtime": {
            "filename": report.filename,
            "format_detected": report.format_detected,
            "nucleus": nucleus,
            "solvent": _metadata_value(metadata, "solvent"),
            "vendor": _metadata_value(metadata, "vendor_format_detected")
            or _metadata_value(metadata, "vendor"),
            "field_mhz": field_mhz,
            "point_count": int(report.point_count),
            "preview_point_count": len(report.preview_points),
            "peak_count": len(report.inferred_peaks),
            "zero_fill_factor": active_zero_fill,
            "line_broadening_hz": active_line_broadening,
            "prompt_target_line_broadening_hz": prompt_line_broadening,
            "phase_method": active_phase_method,
            "phase_zero_order_degrees": _phase_degrees(phase_settings),
            "phase_correction_applied": phase_settings.get("phase_correction_applied"),
            "baseline_method": active_baseline_method,
            "baseline_order": _safe_int(
                _first_present(
                    baseline_correction.get("baseline_order"),
                    baseline_correction.get("order"),
                    processing_parameters.get("baseline_order"),
                )
            ),
            "baseline_correction_applied": baseline_correction.get("correction_applied"),
            "processing_recipe_id": processing_recipe.get("id")
            or processing_recipe.get("selected_preset"),
            "raw_archive_sha256": raw_sha256,
            "raw_archive_immutable": bool(
                _first_present(
                    artifact_policy.get("raw_data_immutable"),
                    provenance.get("raw_data_immutable"),
                    True,
                )
            ),
        },
        "acceptance_gates": {
            "ppm_scale_reference_tolerance_ppm": 0.01,
            "peak_count_tolerance_vs_reference": 2,
            "phase_angle_tolerance_degrees": 5,
            "baseline_rmse_fraction_full_scale": 0.005,
            "prompt_3_peak_count_tolerance_fraction_vs_expert": 0.05,
            "prompt_3_solvent_detection_target_fraction": 0.95,
            "generation_target_seconds": [1, 3],
            "fingerprint_identity_source": (
                "prompt_reader_fingerprint_hash_when_sidecar_enabled; "
                "raw_archive_sha256_for_active_immutable_upload_identity"
            ),
        },
        "regression_guard": {
            "spectracheck_processed_routes_unchanged": True,
            "spectracheck_raw_preview_process_contract_preserved": True,
            "regulatory_hub_unchanged": True,
            "reactioniq_unchanged": True,
            "no_visual_activation_from_prompt_sidecar": True,
        },
    }


def build_prompt_pipeline_analysis_guidance(
    report: FIDPreviewReport,
    sidecar: Mapping[str, Any] | None,
    *,
    validation_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return metadata-only Prompt 1/2 guidance for downstream analysis.

    The guidance is intentionally compact and explicit about what it may and
    may not influence.  It can be used by analysis tables for fixture-matched
    peak-count statistics, but it must not replace the visible spectrum,
    baseline, phase, or legacy peak markers.
    """

    validation = dict(
        validation_report
        or build_prompt_pipeline_validation_report(report, sidecar)
    )
    legacy = validation.get("legacy") if isinstance(validation.get("legacy"), Mapping) else {}
    prompt = (
        validation.get("prompt_1_2")
        if isinstance(validation.get("prompt_1_2"), Mapping)
        else {}
    )
    comparisons = (
        validation.get("comparisons")
        if isinstance(validation.get("comparisons"), Mapping)
        else {}
    )
    fingerprint = (
        comparisons.get("fingerprint")
        if isinstance(comparisons.get("fingerprint"), Mapping)
        else {}
    )
    prompt_peak_count = _best_prompt_peak_count(prompt)
    legacy_peak_count = _safe_int(legacy.get("peak_count"))
    prompt_available = bool(prompt.get("available"))
    reader_diagnostics = (
        prompt.get("reader_diagnostics")
        if isinstance(prompt.get("reader_diagnostics"), Mapping)
        else {}
    )
    preprocess_diagnostics = (
        prompt.get("preprocess_diagnostics")
        if isinstance(prompt.get("preprocess_diagnostics"), Mapping)
        else {}
    )
    integration_diagnostics = (
        validation.get("integration_diagnostics")
        if isinstance(validation.get("integration_diagnostics"), Mapping)
        else {}
    )
    prompt_hash_present = bool(fingerprint.get("prompt_hash_present"))
    prompt_usable_for_metadata = (
        prompt_available
        and prompt_peak_count is not None
        and prompt_hash_present
    )
    recommended_peak_count = (
        prompt_peak_count if prompt_usable_for_metadata else legacy_peak_count
    )
    recommended_source = (
        "prompt_1_2_fixture_matched_peak_count"
        if prompt_usable_for_metadata
        else "legacy_visible_pipeline_peak_count"
    )
    return {
        "version": "raw_fid_prompt_peak_guidance_v1",
        "visibility": "metadata_only",
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "used_for_plot": False,
        "used_for_peak_markers": False,
        "used_for_phase_or_baseline": False,
        "legacy_spectrum_fields_preserved": True,
        "integration_diagnostics_version": integration_diagnostics.get("version"),
        "metadata_only_integration_status": integration_diagnostics.get("status"),
        "reader_diagnostics_available": bool(reader_diagnostics),
        "preprocess_diagnostics_available": bool(preprocess_diagnostics),
        "analysis_use_policy": (
            "analysis_metadata_guidance_only; do_not_replace_visible_trace_or_legacy_peak_markers"
        ),
        "safe_to_use_for_analysis_metadata": prompt_usable_for_metadata,
        "requires_human_review_before_visual_activation": True,
        "recommended_peak_count": recommended_peak_count,
        "recommended_peak_count_source": recommended_source,
        "legacy_peak_count": legacy_peak_count,
        "prompt_peak_count": prompt_peak_count,
        "peak_count_delta": _abs_int_delta(legacy_peak_count, prompt_peak_count),
        "nucleus": prompt.get("nucleus") or legacy.get("nucleus"),
        "solvent": prompt.get("solvent") or legacy.get("solvent"),
        "field_mhz": _safe_float(prompt.get("field_mhz")),
        "point_count": _safe_int(prompt.get("point_count")),
        "fingerprint_hash": prompt.get("fingerprint_hash"),
        "prompt_runtime_ms": _safe_float(prompt.get("runtime_ms")),
        "validation_status": validation.get("status"),
        "validation_version": validation.get("version"),
    }


def build_prompt_pipeline_consistency_check(
    guidance: Mapping[str, Any] | None,
    *,
    active_peak_count: int | None,
    active_peak_source: str = "legacy_visible_pipeline",
    tolerance: int = 2,
) -> dict[str, Any]:
    """Compare metadata-only Prompt 1/2 guidance with the active result.

    This is a review aid, not an activation path.  The visible raw-FID spectrum
    and its legacy peak markers remain authoritative until a later phase
    explicitly promotes a Prompt 1/2 component.
    """

    active_count = _safe_int(active_peak_count)
    prompt_guidance = dict(guidance or {})
    recommended_count = _safe_int(prompt_guidance.get("recommended_peak_count"))
    recommended_source = prompt_guidance.get("recommended_peak_count_source")
    if recommended_count is None:
        status = "prompt_guidance_unavailable"
        delta = None
        within_tolerance = None
        message = "Prompt 1/2 sidecar did not provide a usable peak-count recommendation."
    elif active_count is None:
        status = "active_peak_count_unavailable"
        delta = None
        within_tolerance = None
        message = "Active legacy peak count was unavailable for Prompt 1/2 sidecar comparison."
    else:
        delta = abs(active_count - recommended_count)
        within_tolerance = delta <= max(0, int(tolerance))
        status = "consistent" if within_tolerance else "review_peak_count_delta"
        message = (
            "Prompt 1/2 sidecar peak-count guidance is consistent with the active legacy result."
            if within_tolerance
            else (
                "Prompt 1/2 sidecar peak-count guidance differs from the active legacy "
                "result; keep the legacy visible spectrum authoritative pending review."
            )
        )
    return {
        "version": "raw_fid_prompt_consistency_v1",
        "visibility": "metadata_only",
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "used_for_plot": False,
        "used_for_peak_markers": False,
        "used_for_phase_or_baseline": False,
        "legacy_spectrum_fields_preserved": True,
        "active_peak_count": active_count,
        "active_peak_source": active_peak_source,
        "recommended_peak_count": recommended_count,
        "recommended_peak_count_source": recommended_source,
        "peak_count_delta": delta,
        "acceptance_tolerance": max(0, int(tolerance)),
        "within_prompt_acceptance": within_tolerance,
        "status": status,
        "message": message,
    }


def build_prompt_pipeline_validation_report(
    report: FIDPreviewReport,
    sidecar: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare legacy raw-FID output with Prompt 1/2 sidecar diagnostics.

    This is a hidden validation report, not a spectrum source.  It gives us the
    statistics needed to compare both paths on fixtures and staging uploads
    while keeping the existing SpectraCheck trace, peak picking, and analysis
    tables untouched.
    """

    sidecar_payload = dict(sidecar or {})
    prompt_available = bool(sidecar_payload.get("available"))
    legacy_summary = _legacy_report_summary(report)
    prompt_summary = _prompt_sidecar_summary(sidecar_payload)
    comparisons = _validation_comparisons(legacy_summary, prompt_summary)
    failure_reasons = list(sidecar_payload.get("warnings") or [])
    status = "sidecar_available" if prompt_available else "sidecar_unavailable"
    peak_count_delta = comparisons.get("peak_count_delta", {})
    if (
        prompt_available
        and peak_count_delta.get("within_prompt_acceptance") is False
    ):
        status = "review_required"
    integration_diagnostics = _metadata_only_integration_diagnostics(
        legacy_summary,
        prompt_summary,
        comparisons,
        prompt_available=prompt_available,
    )
    return {
        "version": "raw_fid_prompt_sidecar_validation_v1",
        "visibility": "hidden_metadata_only",
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "status": status,
        "legacy": legacy_summary,
        "prompt_1_2": prompt_summary,
        "comparisons": comparisons,
        "integration_diagnostics": integration_diagnostics,
        "failure_reasons": failure_reasons,
        "regression_guard": {
            "spectral_fields_preserved": True,
            "preserved_fields": [
                "preview_points",
                "inferred_peaks",
                "inferred_nmr_text",
                "reference_peaks",
                "comparison",
                "warnings",
                "processing_metadata",
            ],
            "activation_policy": "metadata_only_until_fixture_report_is_reviewed",
        },
        "safe_to_activate": False,
    }


def _safe_archive_name(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".tar.gz"):
        return "raw_fid.tar.gz"
    if lower.endswith(".tgz"):
        return "raw_fid.tgz"
    if lower.endswith(".zip"):
        return "raw_fid.zip"
    suffix = Path(filename).suffix or ".zip"
    return f"raw_fid{suffix}"


def _default_baseline_method(nucleus: str | None) -> str:
    return "whittaker" if str(nucleus or "").upper() == "13C" else "bernstein"


def _sidecar_from_spectrum(
    spectrum: Any,
    *,
    requested_nucleus: str | None,
    requested_solvent: str | None,
    baseline_method: str | None,
    baseline_order: int,
    runtime_ms: float,
) -> dict[str, Any]:
    metadata = spectrum.metadata if isinstance(spectrum.metadata, Mapping) else {}
    preprocessing = metadata.get("preprocessing")
    if not isinstance(preprocessing, Mapping):
        preprocessing = {}
    phase = _compact_mapping(preprocessing.get("phase"))
    baseline = _compact_mapping(preprocessing.get("baseline"))
    reader_diagnostics = _reader_diagnostics_from_spectrum(spectrum, metadata)
    preprocess_diagnostics = _preprocess_diagnostics_from_metadata(
        phase=phase,
        baseline=baseline,
        baseline_method=baseline_method or _default_baseline_method(spectrum.nucleus),
        baseline_order=baseline_order,
    )
    return {
        "pipeline": "prompt_1_2",
        "role": "sidecar_metadata_only",
        "active": False,
        "available": True,
        "requested_nucleus": requested_nucleus,
        "requested_solvent": requested_solvent,
        "nucleus": spectrum.nucleus,
        "solvent": spectrum.solvent,
        "field_mhz": spectrum.field_mhz,
        "point_count": int(len(spectrum.data)),
        "ppm_min": float(min(spectrum.ppm_axis)),
        "ppm_max": float(max(spectrum.ppm_axis)),
        "peak_count": _safe_int(metadata.get("peak_count")),
        "estimated_peak_count": _safe_int(metadata.get("estimated_peak_count")),
        "processed_peaklist_peak_count": _safe_int(
            metadata.get("processed_peaklist_peak_count")
        ),
        "fingerprint_hash": spectrum.fingerprint_hash,
        "runtime_ms": runtime_ms,
        "baseline_method": baseline_method or _default_baseline_method(spectrum.nucleus),
        "baseline_order": baseline_order,
        "phase": phase,
        "baseline": baseline,
        "reader_diagnostics": reader_diagnostics,
        "preprocess_diagnostics": preprocess_diagnostics,
    }


def _reader_diagnostics_from_spectrum(
    spectrum: Any,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    ppm_axis = getattr(spectrum, "ppm_axis", [])
    acquisition_time = getattr(spectrum, "acquisition_time", None)
    if hasattr(acquisition_time, "isoformat"):
        acquisition_time_value = acquisition_time.isoformat()
    else:
        acquisition_time_value = None
    return {
        "version": "prompt_1_fid_reader_sidecar_v1",
        "source": "moltrace.spectroscopy.io.fid_reader.read_fid",
        "visibility": "metadata_only",
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "used_for_plot": False,
        "used_for_peak_markers": False,
        "used_for_phase_or_baseline": False,
        "used_for_visible_spectrum": False,
        "vendor": metadata.get("vendor"),
        "nucleus": getattr(spectrum, "nucleus", None),
        "solvent": getattr(spectrum, "solvent", None),
        "field_mhz": _safe_float(getattr(spectrum, "field_mhz", None)),
        "acquisition_time": acquisition_time_value,
        "zero_fill_points": _safe_int(metadata.get("zero_fill_points")),
        "input_points": _safe_int(metadata.get("input_points")),
        "line_broadening_hz": _safe_float(metadata.get("line_broadening_hz")),
        "apodization": metadata.get("apodization"),
        "sweep_width_hz": _safe_float(metadata.get("sweep_width_hz")),
        "frequency_orientation": metadata.get("frequency_orientation"),
        "ppm_axis_direction": _axis_direction(ppm_axis),
        "point_count": _safe_int(getattr(getattr(spectrum, "data", []), "size", None)),
        "estimated_peak_count": _safe_int(metadata.get("estimated_peak_count")),
        "processed_peaklist_peak_count": _safe_int(
            metadata.get("processed_peaklist_peak_count")
        ),
        "fingerprint_hash": getattr(spectrum, "fingerprint_hash", None)
        or metadata.get("fingerprint_hash"),
    }


def _preprocess_diagnostics_from_metadata(
    *,
    phase: Mapping[str, Any],
    baseline: Mapping[str, Any],
    baseline_method: str,
    baseline_order: int,
) -> dict[str, Any]:
    return {
        "version": "prompt_2_phase_baseline_sidecar_v1",
        "source": "moltrace.spectroscopy.preprocess.phase_baseline",
        "visibility": "metadata_only",
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "used_for_plot": False,
        "used_for_peak_markers": False,
        "used_for_phase_or_baseline": False,
        "used_for_visible_spectrum": False,
        "phase_method": phase.get("method"),
        "phase_zero_order_degrees": _phase_degrees(phase),
        "phase_correction_applied": phase.get("phase_correction_applied"),
        "phase_acceptance": "within_5_degrees_against_mnova_reference",
        "baseline_method": baseline.get("method") or baseline_method,
        "baseline_order": _safe_int(baseline.get("order")) or int(baseline_order),
        "baseline_model": baseline.get("baseline_model"),
        "baseline_rmse_fraction_full_scale": _safe_float(
            baseline.get("baseline_rmse_fraction_full_scale")
        ),
        "baseline_acceptance": (
            "baseline_rmse_within_0.5_percent_full_scale_on_fixture_set"
        ),
    }


def _compact_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    compact: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            compact[str(key)] = item
    return compact


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _legacy_report_summary(report: FIDPreviewReport) -> dict[str, Any]:
    ppm_values = [
        float(point.shift_ppm)
        for point in report.preview_points
        if _is_finite_number(point.shift_ppm)
    ]
    metadata = report.metadata if isinstance(report.metadata, Mapping) else {}
    phase = metadata.get("phase") if isinstance(metadata.get("phase"), Mapping) else {}
    baseline = (
        metadata.get("baseline") if isinstance(metadata.get("baseline"), Mapping) else {}
    )
    return {
        "filename": report.filename,
        "format_detected": report.format_detected,
        "nucleus": _metadata_value(metadata, "nucleus"),
        "solvent": _metadata_value(metadata, "solvent"),
        "point_count": int(report.point_count),
        "preview_point_count": int(len(report.preview_points)),
        "peak_count": int(len(report.inferred_peaks)),
        "ppm_min": min(ppm_values) if ppm_values else None,
        "ppm_max": max(ppm_values) if ppm_values else None,
        "phase": _compact_mapping(phase),
        "baseline": _compact_mapping(baseline),
        "fingerprint_hash": None,
    }


def _prompt_sidecar_summary(sidecar: Mapping[str, Any]) -> dict[str, Any]:
    reader_diagnostics = _metadata_only_diagnostic(
        sidecar.get("reader_diagnostics")
    )
    preprocess_diagnostics = _metadata_only_diagnostic(
        sidecar.get("preprocess_diagnostics")
    )
    return {
        "available": bool(sidecar.get("available")),
        "nucleus": sidecar.get("nucleus"),
        "solvent": sidecar.get("solvent"),
        "field_mhz": _safe_float(sidecar.get("field_mhz")),
        "point_count": _safe_int(sidecar.get("point_count")),
        "peak_count": _safe_int(sidecar.get("peak_count")),
        "estimated_peak_count": _safe_int(sidecar.get("estimated_peak_count")),
        "processed_peaklist_peak_count": _safe_int(
            sidecar.get("processed_peaklist_peak_count")
        ),
        "ppm_min": _safe_float(sidecar.get("ppm_min")),
        "ppm_max": _safe_float(sidecar.get("ppm_max")),
        "fingerprint_hash": sidecar.get("fingerprint_hash"),
        "runtime_ms": _safe_float(sidecar.get("runtime_ms")),
        "phase": _compact_mapping(sidecar.get("phase")),
        "baseline": _compact_mapping(sidecar.get("baseline")),
        "reader_diagnostics": reader_diagnostics,
        "preprocess_diagnostics": preprocess_diagnostics,
    }


def _metadata_only_diagnostic(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    diagnostic = dict(value)
    diagnostic.update(
        {
            "visibility": "metadata_only",
            "active_visible_pipeline": "legacy",
            "prompt_pipeline_active": False,
            "used_for_plot": False,
            "used_for_peak_markers": False,
            "used_for_phase_or_baseline": False,
            "used_for_visible_spectrum": False,
        }
    )
    return diagnostic


def _best_prompt_peak_count(prompt: Mapping[str, Any]) -> int | None:
    for key in ("peak_count", "processed_peaklist_peak_count", "estimated_peak_count"):
        value = _safe_int(prompt.get(key))
        if value is not None:
            return value
    return None


def _validation_comparisons(
    legacy: Mapping[str, Any],
    prompt: Mapping[str, Any],
) -> dict[str, Any]:
    legacy_peak_count = _safe_int(legacy.get("peak_count"))
    prompt_peak_count = _safe_int(prompt.get("peak_count"))
    ppm_min_delta = _abs_delta(legacy.get("ppm_min"), prompt.get("ppm_min"))
    ppm_max_delta = _abs_delta(legacy.get("ppm_max"), prompt.get("ppm_max"))
    legacy_phase = _phase_degrees(legacy.get("phase"))
    prompt_phase = _phase_degrees(prompt.get("phase"))
    return {
        "nucleus_match": _string_equal(legacy.get("nucleus"), prompt.get("nucleus")),
        "solvent_match": _string_equal(legacy.get("solvent"), prompt.get("solvent")),
        "point_count_delta": _abs_int_delta(
            _safe_int(legacy.get("point_count")),
            _safe_int(prompt.get("point_count")),
        ),
        "peak_count_delta": {
            "value": _abs_int_delta(legacy_peak_count, prompt_peak_count),
            "acceptance": "within_2_of_reference_or_legacy_review_target",
            "within_prompt_acceptance": (
                None
                if legacy_peak_count is None or prompt_peak_count is None
                else abs(legacy_peak_count - prompt_peak_count) <= 2
            ),
        },
        "ppm_range_delta": {
            "ppm_min_abs_delta": ppm_min_delta,
            "ppm_max_abs_delta": ppm_max_delta,
            "acceptance": "reference_peak_ppm_within_0.01_ppm_on_fixture_set",
        },
        "phase_delta_degrees": {
            "value": _abs_delta(legacy_phase, prompt_phase),
            "acceptance": "within_5_degrees_against_mnova_reference",
        },
        "baseline": {
            "legacy_method": _baseline_method(legacy.get("baseline")),
            "prompt_method": _baseline_method(prompt.get("baseline")),
            "acceptance": "baseline_rmse_within_0.5_percent_full_scale_on_fixture_set",
        },
        "fingerprint": {
            "prompt_hash_present": isinstance(prompt.get("fingerprint_hash"), str)
            and len(str(prompt.get("fingerprint_hash"))) == 64,
            "legacy_hash_present": isinstance(legacy.get("fingerprint_hash"), str)
            and len(str(legacy.get("fingerprint_hash"))) == 64,
        },
        "runtime": {
            "prompt_runtime_ms": _safe_float(prompt.get("runtime_ms")),
            "target_ms": 3000.0,
            "within_target": (
                None
                if _safe_float(prompt.get("runtime_ms")) is None
                else _safe_float(prompt.get("runtime_ms")) <= 3000.0
            ),
        },
    }


def _metadata_only_integration_diagnostics(
    legacy: Mapping[str, Any],
    prompt: Mapping[str, Any],
    comparisons: Mapping[str, Any],
    *,
    prompt_available: bool,
) -> dict[str, Any]:
    ppm_range_delta = (
        comparisons.get("ppm_range_delta")
        if isinstance(comparisons.get("ppm_range_delta"), Mapping)
        else {}
    )
    runtime = (
        comparisons.get("runtime")
        if isinstance(comparisons.get("runtime"), Mapping)
        else {}
    )
    peak_count_delta = (
        comparisons.get("peak_count_delta")
        if isinstance(comparisons.get("peak_count_delta"), Mapping)
        else {}
    )
    return {
        "version": "raw_fid_prompt_metadata_seam_v1",
        "visibility": "hidden_metadata_only",
        "active_visible_pipeline": "legacy",
        "prompt_pipeline_active": False,
        "visible_spectrum_source": "legacy_raw_fid_processor",
        "prompt_reader_source": "metadata_only_sidecar",
        "prompt_preprocess_source": "metadata_only_sidecar",
        "active_visual_fields_preserved": True,
        "used_for_plot": False,
        "used_for_peak_markers": False,
        "used_for_phase_or_baseline": False,
        "used_for_visible_spectrum": False,
        "safe_to_activate": False,
        "status": "ready_for_review" if prompt_available else "sidecar_unavailable",
        "review_policy": (
            "compare_fixture_statistics_only; do_not_replace_visible_trace_or_legacy_analysis_without_explicit_activation_review"
        ),
        "comparison_fields": [
            "nucleus",
            "solvent",
            "point_count",
            "peak_count",
            "ppm_range",
            "phase",
            "baseline",
            "runtime",
            "fingerprint_hash",
        ],
        "legacy_peak_count": _safe_int(legacy.get("peak_count")),
        "prompt_peak_count": _best_prompt_peak_count(prompt),
        "peak_count_delta": peak_count_delta.get("value"),
        "ppm_min_abs_delta": ppm_range_delta.get("ppm_min_abs_delta"),
        "ppm_max_abs_delta": ppm_range_delta.get("ppm_max_abs_delta"),
        "prompt_runtime_ms": runtime.get("prompt_runtime_ms"),
    }


def _metadata_value(metadata: Mapping[str, Any], key: str) -> Any:
    value = metadata.get(key)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        if value is None:
            return None
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if _is_finite_number(numeric) else None


def _abs_int_delta(left: int | None, right: int | None) -> int | None:
    if left is None or right is None:
        return None
    return abs(left - right)


def _abs_delta(left: Any, right: Any) -> float | None:
    left_float = _safe_float(left)
    right_float = _safe_float(right)
    if left_float is None or right_float is None:
        return None
    return abs(left_float - right_float)


def _string_equal(left: Any, right: Any) -> bool | None:
    if left is None or right is None:
        return None
    return str(left).strip().lower() == str(right).strip().lower()


def _phase_degrees(value: Any) -> float | None:
    if not isinstance(value, Mapping):
        return None
    for key in ("zero_order_degrees", "applied_phase_deg", "p0"):
        phase = _safe_float(value.get(key))
        if phase is not None:
            return phase
    return None


def _baseline_method(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return None
    for key in ("method", "mode", "baseline_correction"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _axis_direction(axis: Any) -> str | None:
    try:
        values = list(axis)
    except TypeError:
        return None
    if len(values) < 2:
        return None
    first = _safe_float(values[0])
    last = _safe_float(values[-1])
    if first is None or last is None:
        return None
    if first > last:
        return "descending"
    if first < last:
        return "ascending"
    return "flat"


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000.0, 3)


def _is_finite_number(value: Any) -> bool:
    try:
        return bool(math.isfinite(float(value)))
    except (TypeError, ValueError):
        return False
