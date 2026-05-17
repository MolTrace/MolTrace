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
    report_from_analysis,
)
from nmrcheck.database import get_raw_archive_by_sha256, init_db, list_recent_analyses
from nmrcheck.fid import FIDProcessingError, fid_settings_from_preset, process_bruker_1d_zip
from nmrcheck.models import FIDProcessingRecipe, FIDRunReviewCreate
from nmrcheck.raw_vault import build_raw_upload_provenance
from nmrcheck.settings import Settings

REFERENCE_TEXT = "3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)"


def test_fid_processing_recipe_defaults_are_safe_real_spectrum_defaults() -> None:
    recipe = FIDProcessingRecipe()

    assert recipe.phase_mode == "auto"
    assert recipe.baseline_correction == "bernstein"
    assert recipe.baseline_order == 3
    assert recipe.display_mode == "real"
    assert recipe.vertical_gain == 1.0
    assert recipe.debug_preview is False


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
    assert report.processing_metadata.processing_recipe.phase_mode in {"auto_acme", "auto_peak_minima", "auto_grid"}
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
    assert report.processing_metadata.analysis_artifact_policy["processing_loaded_from_vault"] is True
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
    assert processed_run.raw_archive_id == processed_run.processing_metadata.raw_upload_provenance["raw_archive_db_id"]
    assert processed_run.raw_sha256 == processed_run.processing_metadata.raw_upload_provenance["sha256"]
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
    assert processed_run.processing_recipe["phase_mode"] in {"auto_acme", "auto_peak_minima", "auto_grid"}
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
    assert processed_run.derived_spectrum_metadata["point_count"] == processed_run.preview.point_count
    assert processed_run.derived_spectrum_metadata["raw_dataset_files_found"]["fid"] is True
    assert processed_run.review_status == "pending_review"
    assert processed_run.processing_metadata.reference_peak_selection["selected_peak_count"] in {0, 1}

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
        assert provenance["sha256"] == processed_run.processing_metadata.raw_upload_provenance["sha256"]
        assert manifest["sha256"] == provenance["sha256"]
        assert manifest["raw_archive"]["id"] == provenance["raw_archive_db_id"]
        assert manifest["sha256_verified"] is True
        original_names = [name for name in names if name.startswith("original/") and not name.endswith(".txt")]
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
        assert process_json["preview"]["processing_metadata"]["processing_recipe"]["baseline_correction"] == "bernstein"

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
            assert hashlib.sha256(package.read("raw/original_archive.zip")).hexdigest() == archive_id
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
