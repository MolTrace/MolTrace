import io
import zipfile

import numpy as np
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.fid import fid_settings_from_preset, process_bruker_1d_zip
from nmrcheck.models import Carbon13Peak, Peak, SpectrumPoint
from nmrcheck.settings import Settings


def _login_headers(client: TestClient) -> dict[str, str]:
    client.post(
        "/auth/register",
        json={"email": "c13@example.com", "password": "StrongPassword123!"},
    )
    login = client.post(
        "/auth/login",
        json={"email": "c13@example.com", "password": "StrongPassword123!"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _build_carbon13_bruker_zip() -> bytes:
    points = 1024
    sw_hz = 20_000.0
    sfo1 = 100.0
    center_ppm = 85.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in [(77.0, 0.35), (58.3, 1.0), (18.2, 0.85)]:
        frequency_hz = (ppm - center_ppm) * sfo1
        fid += (
            amplitude
            * np.exp(2j * np.pi * frequency_hz * time_axis)
            * np.exp(-time_axis * 12.0)
        )
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = f"""##TITLE= synthetic carbon beta regression
##$TD= {points * 2}
##$SW_h= {sw_hz}
##$SW= {sw_hz / sfo1}
##$SFO1= {sfo1}
##$BF1= {sfo1}
##$O1= {center_ppm * sfo1}
##$O1P= {center_ppm}
##$NUC1= <13C>
##$BYTORDA= 0
##$DTYPA= 0
##$GRPDLY= 0
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ethanol_c13_raw/fid", interleaved.tobytes())
        archive.writestr("ethanol_c13_raw/acqus", acqus)
    return buffer.getvalue()


def test_carbon13_upload_models_accept_realistic_axis_margins() -> None:
    SpectrumPoint(shift_ppm=-10.1448, intensity=0.0)
    Peak(shift_ppm=-10.1448, multiplicity="s", integration_h=1.0)
    Carbon13Peak(shift_ppm=-10.1448)


def test_raw_carbon13_fid_uses_mnova_advised_processing_constraints() -> None:
    report = process_bruker_1d_zip(
        filename="ethanol_13c_raw.zip",
        content=_build_carbon13_bruker_zip(),
        nucleus="1H",
        settings=fid_settings_from_preset(
            selected_preset="balanced",
            zero_fill_factor=1,
            line_broadening_hz=0.3,
            max_preview_points=700,
        ),
    )

    assert report.metadata["nucleus"] == "13C"
    advised = report.metadata["raw_fid_advised_processing"]
    assert advised["applied"] is True
    assert advised["scope"] == "raw_fid_only"
    assert report.metadata["zero_filling"]["factor"] == 3
    assert report.metadata["line_broadening"]["hz"] == 2.0
    assert report.metadata["line_broadening"]["window_function"] == "exponential_line_broadening"
    assert report.metadata["baseline"]["mode"] == "bernstein"
    assert report.metadata["baseline"]["order"] == 3
    assert report.metadata["preview_downsampling"]["point_limit"] == 4000
    trace_display = report.metadata["display_preprocessing"]["trace_smoothing"]
    assert trace_display["method"] == "mnova_raw_fid_noise_envelope"
    assert trace_display["smoothing_kernel"] == "none"
    assert trace_display["baseline_noise_preserved"] is True
    assert not any("tuned for Bruker 1D 1H" in warning for warning in report.warnings)


def test_carbon13_analyze_endpoint(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'c13.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    with TestClient(app) as client:
        headers = _login_headers(client)
        res = client.post(
            "/carbon13/analyze",
            headers=headers,
            json={
                "sample_id": "ethanol",
                "smiles": "CCO",
                "carbon13_text": "13C NMR (101 MHz, CDCl3) δ 58.3, 18.2.",
                "solvent": "CDCl3",
            },
        )
        assert res.status_code == 200
        assert res.json()["label"] == "carbon_count_consistent"


def test_carbon13_processed_spectrum_preview_and_analyze_endpoint(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'c13-spectrum.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    content = b"shift_ppm,intensity,assignment\n58.3,1000,CH2\n18.2,900,CH3\n77.0,200,CDCl3\n"
    with TestClient(app) as client:
        headers = _login_headers(client)
        preview = client.post(
            "/carbon13/spectrum/preview",
            headers=headers,
            data={"solvent": "CDCl3"},
            files={"file": ("ethanol_13c.csv", content, "text/csv")},
        )
        assert preview.status_code == 200
        assert preview.json()["observed_signal_count"] == 3
        assert preview.json()["source_mode"] == "peak_table"

        analyzed = client.post(
            "/carbon13/spectrum/analyze",
            headers=headers,
            data={
                "smiles": "CCO",
                "sample_id": "ethanol",
                "solvent": "CDCl3",
                "manual_peaks_json": '{"peaks":[{"shift_ppm":58.3,"intensity":1000},{"shift_ppm":18.2,"intensity":900}]}',
            },
            files={"file": ("ethanol_13c.csv", content, "text/csv")},
        )
        assert analyzed.status_code == 200
        assert analyzed.json()["label"] == "carbon_count_consistent"
        assert any("Reviewer-adjusted ¹³C" in note for note in analyzed.json()["notes"])


def test_carbon13_processed_shift_intensity_table_does_not_500(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'c13-processed-shift-intensity.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    content = b"shift_ppm,intensity\n58.3,1000\n18.2,900\n77.0,200\n"
    with TestClient(app) as client:
        headers = _login_headers(client)
        preview = client.post(
            "/carbon13/spectrum/preview",
            headers=headers,
            data={"solvent": "CDCl3"},
            files={"file": ("ethanol_13c_shift_intensity.csv", content, "text/csv")},
        )
        assert preview.status_code == 200
        assert preview.json()["source_mode"] == "peak_table"


def test_carbon13_raw_fid_preview_and_analyze_accept_broad_carbon_axis(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'c13-raw-fid.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_fid_storage_dir=str(tmp_path / "raw-fid-store"),
            raw_data_vault_dir=str(tmp_path / "raw-data-vault"),
        )
    )
    content = _build_carbon13_bruker_zip()
    with TestClient(app) as client:
        headers = _login_headers(client)
        preview = client.post(
            "/carbon13/fid/preview",
            headers=headers,
            data={
                "smiles": "CCO",
                "proton_nmr_text": "¹H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), 1.26 (t, 3H)",
                "solvent": "CDCl3",
                "reference_ppm": "77.0",
            },
            files={"file": ("ethanol_c13_raw.zip", content, "application/zip")},
        )
        assert preview.status_code == 200
        assert preview.json()["source_mode"] == "raw_fid"
        assert preview.json()["observed_signal_count"] >= 1
        assert preview.json()["metadata"]["preview_points"]
        assert preview.json()["metadata"]["context_guidance"]["smiles_guidance_used"] is True
        assert preview.json()["metadata"]["context_guidance"]["proton_nmr_guidance_used"] is True
        assert preview.json()["metadata"]["context_guidance"]["expected_carbon_atoms"] == 2
        baseline = preview.json()["metadata"]["fid_processing"]["baseline_correction"]
        assert baseline["method"] == "bernstein_polynomial"
        assert baseline["baseline_correction"] == "bernstein"
        assert baseline["baseline_order"] == 3
        assert baseline["baseline_locked_to_zero"] is True
        assert preview.json()["metadata"]["evidence_trace_mode"] == "raw_fid_fft_real_baseline_corrected"
        assert preview.json()["metadata"]["display_mode"] == "real"
        assert preview.json()["metadata"]["baseline_lock_visual_only"] is True
        provenance = preview.json()["metadata"]["raw_upload_provenance"]
        assert provenance["storage_backend"] == "local_raw_vault"
        assert provenance["raw_archive_id"] == provenance["sha256"]
        assert provenance["vendor_detected"] == "Bruker"
        original_state = preview.json()["metadata"]["original_spectrum_state"]
        assert original_state["preserved"] is True
        assert original_state["preview_points"] == []
        assert original_state["preview_points_omitted"] is True
        assert preview.json()["metadata"]["fid_processing"]["processing_parameters"]["mask_solvent_regions"] is True

        analyzed = client.post(
            "/carbon13/fid/analyze",
            headers=headers,
            data={
                "smiles": "CCO",
                "proton_nmr_text": "¹H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), 1.26 (t, 3H)",
                "sample_id": "ethanol-c13-raw",
                "solvent": "CDCl3",
                "reference_ppm": "77.0",
            },
            files={"file": ("ethanol_c13_raw.zip", content, "application/zip")},
        )
        assert analyzed.status_code == 200
        assert "observed_carbon_signals" in analyzed.json()
        assert any("SMILES-derived carbon count" in note for note in analyzed.json()["notes"])


def test_carbon13_raw_fid_invalid_zip_returns_400_not_500(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'c13-invalid-raw.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_fid_storage_dir=str(tmp_path / "raw-fid-store-invalid"),
            raw_data_vault_dir=str(tmp_path / "raw-data-vault-invalid"),
        )
    )
    with TestClient(app) as client:
        headers = _login_headers(client)
        response = client.post(
            "/carbon13/fid/preview",
            headers=headers,
            files={"file": ("not-a-fid.zip", b"not a zip", "application/zip")},
        )
        assert response.status_code == 400
