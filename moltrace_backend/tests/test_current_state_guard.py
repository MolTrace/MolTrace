from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.baseline import apply_bernstein_baseline_correction
from nmrcheck.fid import _auto_phase_spectrum, apply_phase
from nmrcheck.settings import Settings

pytestmark = pytest.mark.current_state

FIXTURES = Path(__file__).parent / "fixtures" / "current_state"

ANALYZE_VALIDATE_KEYS = {
    "sample_id",
    "solvent",
    "structure_valid",
    "nmr_text_valid",
    "structure_nmr_match",
    "analysis_ready",
    "parseable_peak_count",
    "expected_visible_h",
    "observed_total_h",
    "adjusted_observed_total_h",
    "delta_visible_h",
    "parsed_peaks",
    "structure",
    "warnings",
    "errors",
}
PROTON_EVIDENCE_KEYS = {
    "sample_id",
    "smiles",
    "solvent",
    "expected_total_h",
    "expected_non_labile_h",
    "expected_labile_h",
    "observed_total_h",
    "observed_non_solvent_h",
    "solvent_or_water_h",
    "delta_total_h",
    "delta_non_solvent_h",
    "label",
    "overall_score",
    "integration_score",
    "solvent_exclusion_score",
    "region_support_score",
    "peaks",
    "notes",
    "warnings",
    "structure",
}
CARBON13_ANALYZE_KEYS = {
    "sample_id",
    "smiles",
    "solvent",
    "expected_carbon_atoms",
    "observed_carbon_signals",
    "delta_carbon_signals",
    "label",
    "confidence",
    "peaks",
    "region_summary",
    "solvent_warnings",
    "notes",
    "carbon13_match_score",
    "carbon_count_score",
    "region_consistency_score",
    "solvent_exclusion_score",
    "dept_apt_consistency_score",
    "expected_region_summary",
    "observed_region_summary",
    "evidence_summary",
    "structure",
}
SPECTRUM_PREVIEW_KEYS = {
    "filename",
    "format_detected",
    "source_mode",
    "point_count",
    "preview_points",
    "inferred_peaks",
    "inferred_nmr_text",
    "reference_nmr_text_normalized",
    "reference_peaks",
    "comparison",
    "warnings",
    "metadata",
}
FID_PREVIEW_KEYS = SPECTRUM_PREVIEW_KEYS | {"fid_run_id", "processing_metadata"}
FID_PROCESS_KEYS = {"preview", "generated_inputs", "analysis"}


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _client(tmp_path) -> tuple[TestClient, dict[str, str]]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'current_state_guard.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_data_vault_dir=str(tmp_path / "raw_data_vault"),
            raw_vault_dir=str(tmp_path / "raw_data_vault"),
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _synthetic_bruker_zip() -> bytes:
    points = 1024
    sw_hz = 5000.0
    sfo1 = 500.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65), (2.10, 0.3)]:
        frequency_hz = (ppm - center_ppm) * sfo1
        fid += amplitude * np.exp(2j * np.pi * frequency_hz * time_axis) * np.exp(
            -time_axis * 10.0
        )
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = f"""##TITLE= current state guard bruker
##$TD= {points * 2}
##$SW_h= {sw_hz}
##$SW= 10.0
##$SFO1= {sfo1}
##$BF1= {sfo1}
##$O1= {center_ppm * sfo1}
##$O1P= {center_ppm}
##$NUC1= <1H>
##$SOLVENT= <CDCl3>
##$BYTORDA= 0
##$DTYPA= 0
##$GRPDLY= 0
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("current_state_bruker/fid", interleaved.tobytes())
        archive.writestr("current_state_bruker/acqus", acqus)
        archive.writestr("current_state_bruker/pulseprogram", "zg30\n")
    return buffer.getvalue()


def _synthetic_varian_zip() -> bytes:
    ng = pytest.importorskip("nmrglue")
    from nmrglue.fileio.varian import create_pdic_param

    points = 1024
    sw_hz = 5000.0
    sfo1 = 500.0
    center_ppm = 4.0
    udic = ng.fileiobase.create_blank_udic(1)
    udic[0]["size"] = points
    udic[0]["complex"] = True
    udic[0]["sw"] = sw_hz
    udic[0]["obs"] = sfo1
    udic[0]["car"] = center_ppm * sfo1
    udic[0]["label"] = "1H"
    dic = ng.varian.create_dic(udic)
    for key, value in {
        "sw": sw_hz,
        "sfrq": sfo1,
        "tn": "H1",
        "solvent": "CDCl3",
        "seqfil": "s2pul",
        "temp": 25,
    }.items():
        dic["procpar"][key] = create_pdic_param(key, [str(value)])
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex64)
    for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65), (2.10, 0.3)]:
        frequency_hz = (ppm - center_ppm) * sfo1
        fid += amplitude * np.exp(2j * np.pi * frequency_hz * time_axis) * np.exp(
            -time_axis * 10.0
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        dataset = root / "current_state_varian.fid"
        ng.varian.write(str(dataset), dic, fid, overwrite=True)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in dataset.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(root))
        return buffer.getvalue()


def _fid_form(**overrides: str) -> dict[str, str]:
    data = {
        "selected_preset": "baseline_preserve",
        "phase_mode": "none",
        "baseline_correction": "preserve",
        "baseline_order": "3",
        "display_mode": "real",
        "vertical_gain": "1",
    }
    data.update(overrides)
    return data


def test_health_returns_ok(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.get("/health", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"]["app"] == "ok"
    assert response.json()["checks"]["database"] == "ok"


def test_analyze_validate_still_rejects_invalid_smiles(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/analyze/validate",
            headers=headers,
            json=_load_json("invalid_smiles_inputs.json"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == ANALYZE_VALIDATE_KEYS
    assert payload["structure_valid"] is False
    assert payload["nmr_text_valid"] is True
    assert payload["analysis_ready"] is False
    assert any("SMILES" in error for error in payload["errors"])


def test_analyze_validate_still_accepts_ethanol_smiles_and_1h_nmr(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/analyze/validate",
            headers=headers,
            json=_load_json("ethanol_inputs.json"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == ANALYZE_VALIDATE_KEYS
    assert payload["structure_valid"] is True
    assert payload["nmr_text_valid"] is True
    assert payload["structure_nmr_match"] is True
    assert payload["analysis_ready"] is True
    assert payload["expected_visible_h"] == 6.0
    assert payload["observed_total_h"] == 6.0
    assert payload["parseable_peak_count"] == 3


def test_proton_evidence_stable_fields(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post("/proton/evidence", headers=headers, json=_load_json("ethanol_inputs.json"))

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == PROTON_EVIDENCE_KEYS
    assert payload["label"] == "consistent"
    assert payload["expected_total_h"] == 6
    assert payload["observed_total_h"] == 6.0
    assert payload["overall_score"] == 1.0
    assert len(payload["peaks"]) == 3


def test_carbon13_analyze_stable_ethanol_carbon_count(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/carbon13/analyze",
            headers=headers,
            json=_load_json("ethanol_carbon13_inputs.json"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == CARBON13_ANALYZE_KEYS
    assert payload["label"] == "carbon_count_consistent"
    assert payload["expected_carbon_atoms"] == 2
    assert payload["observed_carbon_signals"] == 2
    assert payload["delta_carbon_signals"] == 0
    assert payload["confidence"] == 0.96


def test_spectrum_preview_default_preserves_original_intensities(tmp_path) -> None:
    client, headers = _client(tmp_path)
    content = (FIXTURES / "processed_spectrum_trace.csv").read_bytes()
    with client:
        response = client.post(
            "/spectrum/preview",
            headers=headers,
            files={"file": ("processed_spectrum_trace.csv", content, "text/csv")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == SPECTRUM_PREVIEW_KEYS
    assert payload["format_detected"] == "csv"
    assert payload["source_mode"] == "trace"
    assert payload["preview_points"] == [
        {"shift_ppm": 4.0, "intensity": 0.0},
        {"shift_ppm": 3.65, "intensity": 2.5},
        {"shift_ppm": 1.26, "intensity": 3.0},
        {"shift_ppm": 0.0, "intensity": 0.0},
    ]
    assert payload["metadata"]["display_mode"] == "real"
    assert payload["metadata"]["evidence_trace_mode"] == "uploaded_intensity"
    assert payload["metadata"]["baseline_lock_visual_only"] is True


def test_spectrum_preview_raw_preview_points_are_debug_only(tmp_path) -> None:
    client, headers = _client(tmp_path)
    content = (FIXTURES / "processed_spectrum_trace.csv").read_bytes()
    with client:
        default = client.post(
            "/spectrum/preview",
            headers=headers,
            files={"file": ("processed_spectrum_trace.csv", content, "text/csv")},
        )
        debug = client.post(
            "/spectrum/preview",
            headers=headers,
            data={"debug_preview": "true"},
            files={"file": ("processed_spectrum_trace.csv", content, "text/csv")},
        )

    assert default.status_code == 200
    assert debug.status_code == 200
    assert "raw_preview_points" not in default.json()["metadata"]
    assert debug.json()["metadata"]["raw_preview_points"] == debug.json()["preview_points"]


def test_fid_preview_detects_bruker_and_varian_fixtures(tmp_path) -> None:
    client, headers = _client(tmp_path)
    cases = [
        ("current_state_bruker.zip", _synthetic_bruker_zip(), "Bruker 1D", "bruker_fid_zip"),
        (
            "current_state_varian.zip",
            _synthetic_varian_zip(),
            "Varian/Agilent 1D",
            "varian_agilent_fid_zip",
        ),
    ]
    with client:
        for filename, content, vendor, format_detected in cases:
            response = client.post(
                "/fid/preview",
                headers=headers,
                data=_fid_form(),
                files={"file": (filename, content, "application/zip")},
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert set(payload) == FID_PREVIEW_KEYS
            assert payload["format_detected"] == format_detected
            assert payload["processing_metadata"]["vendor_format_detected"] == vendor
            assert payload["processing_metadata"]["raw_dataset_files_found"]["fid"] is True
            required_param = "acqus" if vendor == "Bruker 1D" else "procpar"
            assert payload["processing_metadata"]["raw_dataset_files_found"][required_param] is True


def test_fid_process_accepts_phase_baseline_order_and_display_fields(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/fid/process",
            headers=headers,
            data=_fid_form(
                smiles="CCO",
                sample_id="current-state-fid",
                solvent="CDCl3",
                manual_nmr_text="3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)",
                phase_mode="manual",
                phase_p0="0.0",
                phase_p1="0.0",
                baseline_correction="bernstein",
                baseline_order="3",
                display_mode="real",
            ),
            files={"file": ("current_state_bruker.zip", _synthetic_bruker_zip(), "application/zip")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == FID_PROCESS_KEYS
    recipe = payload["preview"]["processing_metadata"]["processing_recipe"]
    assert recipe["phase_mode"] == "manual"
    assert recipe["baseline_correction"] == "bernstein"
    assert recipe["baseline_order"] == 3
    assert recipe["display_mode"] == "real"
    assert payload["preview"]["metadata"]["display_mode"] == "real"
    assert payload["preview"]["metadata"]["baseline_lock_visual_only"] is True


def test_baseline_and_phase_smoke_guard_still_passes() -> None:
    points = [
        (float(idx), np.exp(-((idx - 40) ** 2) / 20.0) * 8.0 + 0.01 * idx + 0.5)
        for idx in range(80)
    ]
    corrected, metadata, warnings = apply_bernstein_baseline_correction(points, order=3)
    assert warnings == []
    assert metadata["order"] == 3
    assert metadata["correction_applied"] is True
    assert max(y for _x, y in corrected) > 5.0

    axis = np.linspace(-2.0, 2.0, 256)
    clean = np.exp(-(axis**2) / 0.04).astype(np.complex128)
    misphased = apply_phase(clean, p0=45.0)
    phased, phase_metadata, phase_warnings = _auto_phase_spectrum(misphased, mode="auto")
    assert isinstance(phase_warnings, list)
    assert phase_metadata["phase_correction_applied"] is True
    assert phase_metadata["phase_score"] > 0
    assert np.max(np.real(phased)) > np.max(np.real(misphased))
