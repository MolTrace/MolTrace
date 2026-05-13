import hashlib
import io
import zipfile

import numpy as np
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings

HEADERS = {"x-api-key": "test-key"}
PEAK_CSV = b"""shift_ppm,integration_h,multiplicity
3.65,2,q
1.26,3,t
2.10,1,br s
"""
TRACE_TSV = b"""ppm\tintensity
4.20\t0
4.10\t3
4.00\t0
1.30\t0
1.20\t5
1.10\t0
"""
CARBON13_CSV = b"""ppm,signal
77.0,12
58.2,200
18.1,140
"""


def _client(tmp_path) -> TestClient:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'nmr_frontend.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_data_vault_dir=str(tmp_path / "raw_data_vault"),
        )
    )
    return TestClient(app)


def _build_bruker_zip() -> bytes:
    points = 1024
    sw_hz = 5000.0
    sfo1 = 500.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65), (2.1, 0.3)]:
        frequency_hz = (ppm - center_ppm) * sfo1
        fid += amplitude * np.exp(2j * np.pi * frequency_hz * time_axis) * np.exp(-time_axis * 10.0)
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = f"""##TITLE= synthetic frontend raw FID test
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


def test_nmr_processed_csv_preview_returns_flat_arrays(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"sample_id": "csv-preview", "nucleus": "1H", "solvent": "CDCl3"},
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sample_id"] == "csv-preview"
    assert payload["nucleus"] == "1H"
    assert payload["filename"] == "peaks.csv"
    assert payload["point_count"] == 3
    assert payload["x"] == [3.65, 1.26, 2.1]
    assert len(payload["x"]) == len(payload["y"])
    assert payload["x_label"] == "ppm"
    assert payload["y_label"] == "intensity"


def test_nmr_processed_tsv_preview_returns_flat_arrays(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"sample_id": "tsv-preview", "nucleus": "1H"},
            files={"file": ("trace.tsv", TRACE_TSV, "text/tab-separated-values")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["filename"] == "trace.tsv"
    assert payload["point_count"] == 6
    assert payload["x"]
    assert payload["y"]
    assert payload["metadata"]["peak_inference"] == "skipped_for_display_preview"
    assert not any("inferred heuristically" in warning for warning in payload["warnings"])


def test_nmr_processed_analyze_returns_peaks(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "analyze-peaks",
                "nucleus": "1H",
                "solvent": "CDCl3",
                "nmr_text": (
                    "1H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), "
                    "1.26 (t, 3H), 2.10 (br s, 1H)"
                ),
                "candidates_text": "ethanol | CCO",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["peak_count"] == 3
    assert payload["peaks"][0]["shift_ppm"] == 3.65
    assert payload["analysis_score"] is not None
    assert payload["metadata"]["peak_inference"] == "enabled"
    assert any("Human review" in item for item in payload["evidence_summary"])


def test_nmr_processed_analyze_returns_peak_enrichment(tmp_path) -> None:
    """Per-peak categorization, impurity matches, labile-H summary, and
    peak-category counts must be present in the analyze response."""
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/analyze",
            headers=HEADERS,
            data={
                "sample_id": "enrichment",
                "nucleus": "1H",
                "solvent": "CDCl3",
                "nmr_text": (
                    "1H NMR (400 MHz, CDCl3) δ 3.65 (q, 2H), "
                    "1.26 (t, 3H), 2.10 (br s, 1H)"
                ),
                "candidates_text": "ethanol | CCO",
            },
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()

    # Each peak has the new enrichment keys.
    for peak in payload["peaks"]:
        assert "category" in peak, f"missing category on peak {peak}"
        assert "chemical_region" in peak
        assert "labile_hint" in peak
        assert "category_reason" in peak

    # Top-level summary fields are present and the right shape.
    assert isinstance(payload["peak_category_summary"], dict)
    assert sum(payload["peak_category_summary"].values()) == len(payload["peaks"])

    assert isinstance(payload["labile_hydrogen_summary"], dict)
    summary = payload["labile_hydrogen_summary"]
    assert "expected_labile_h" in summary
    assert "observed_labile_candidates" in summary
    # Ethanol has 1 labile H (OH), and the 2.10 br s peak should be detected.
    assert summary["expected_labile_h"] == 1
    assert len(summary["observed_labile_candidates"]) >= 1

    assert isinstance(payload["impurity_candidates"], list)
    assert isinstance(payload["predicted_vs_observed"], list)
    # With "ethanol | CCO" candidate, predicted vs observed should produce rows.
    assert len(payload["predicted_vs_observed"]) > 0


def test_nmr_processed_invalid_file_returns_clear_400(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"nucleus": "1H"},
            files={"file": ("bad.csv", b"not,numeric\nabc,def\n", "text/csv")},
        )

    assert response.status_code == 400
    assert "Could not parse numeric spectrum data" in response.json()["detail"]


def test_nmr_raw_fid_preview_computes_sha256(tmp_path) -> None:
    content = _build_bruker_zip()
    expected = hashlib.sha256(content).hexdigest()
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/raw-fid/preview",
            headers=HEADERS,
            data={"sample_id": "raw-preview", "nucleus": "1H", "vendor": "auto"},
            files={"file": ("ethanol_raw.zip", content, "application/zip")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["raw_sha256"] == expected
    assert payload["vendor_detected"] == "Bruker"
    assert payload["file_inventory"]["required_files_present"] is True
    assert any("No Fourier transform" in note for note in payload["notes"])


def test_nmr_raw_fid_unsupported_archive_returns_clear_error(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/raw-fid/preview",
            headers=HEADERS,
            data={"nucleus": "1H", "vendor": "auto"},
            files={"file": ("not-raw.txt", b"not an archive", "text/plain")},
        )

    assert response.status_code == 400
    assert "Raw FID vault rejected the upload" in response.json()["detail"]


def test_nmr_raw_fid_process_preserves_raw_hash(tmp_path) -> None:
    content = _build_bruker_zip()
    expected = hashlib.sha256(content).hexdigest()
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/raw-fid/process",
            headers=HEADERS,
            data={
                "sample_id": "raw-process",
                "nucleus": "1H",
                "vendor": "auto",
                "processing_preset": "balanced",
                "preserve_raw": "true",
            },
            files={"file": ("ethanol_raw.zip", content, "application/zip")},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["raw_sha256"] == expected
    assert payload["metadata"]["preserve_raw"] is True
    assert payload["point_count"] > 0
    assert len(payload["x"]) == len(payload["y"])
    recipe = payload["processing_parameters"]["processing_recipe"]
    assert recipe["baseline_correction"] == "bernstein"


def test_nmr_processed_accepts_1h_and_13c_nucleus_values(tmp_path) -> None:
    with _client(tmp_path) as client:
        proton = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"nucleus": "1H"},
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )
        carbon = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"nucleus": "13C", "solvent": "CDCl3"},
            files={"file": ("carbon.csv", CARBON13_CSV, "text/csv")},
        )

    assert proton.status_code == 200, proton.text
    assert carbon.status_code == 200, carbon.text
    assert proton.json()["nucleus"] == "1H"
    assert carbon.json()["nucleus"] == "13C"
    assert proton.json()["metadata"]["peak_inference"] == "skipped_for_display_preview"
    assert carbon.json()["metadata"]["peak_inference"] == "skipped_for_display_preview"


def test_nmr_processed_invalid_nucleus_is_rejected(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/nmr/processed/preview",
            headers=HEADERS,
            data={"nucleus": "15N"},
            files={"file": ("peaks.csv", PEAK_CSV, "text/csv")},
        )

    assert response.status_code == 422


def test_nmr_frontend_upload_routes_are_in_openapi(tmp_path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/nmr/processed/preview" in paths
    assert "/nmr/processed/analyze" in paths
    assert "/nmr/raw-fid/preview" in paths
    assert "/nmr/raw-fid/process" in paths
