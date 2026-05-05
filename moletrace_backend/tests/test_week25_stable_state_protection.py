from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from nmrcheck.analysis import analyze_inputs
from nmrcheck.api import create_app
from nmrcheck.carbon13 import analyze_carbon13_text
from nmrcheck.fid import fid_settings_from_preset
from nmrcheck.models import AnalysisInputs
from nmrcheck.nmr2d_analyzer import analyze_nmr2d
from nmrcheck.nmr2d_parser import parse_processed_2d_nmr
from nmrcheck.settings import Settings
from nmrcheck.spectrum import parse_processed_spectrum

FIXTURES = Path(__file__).parent / "fixtures" / "week25"
PROTON_TEXT = "¹H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
CARBON_TEXT = "¹³C NMR (101 MHz, CDCl3) δ 58.3, 18.2."


def _stable_snapshot() -> dict[str, object]:
    proton = analyze_inputs(
        AnalysisInputs(
            sample_id="ethanol-golden",
            smiles="CCO",
            solvent="CDCl3",
            nmr_text=PROTON_TEXT,
        )
    )
    carbon = analyze_carbon13_text(smiles="CCO", carbon13_text=CARBON_TEXT, solvent="CDCl3")
    spectrum = parse_processed_spectrum(
        filename="spectrum_1h_trace.csv",
        content=(FIXTURES / "spectrum_1h_trace.csv").read_bytes(),
    )
    fid = fid_settings_from_preset(selected_preset="balanced")
    return {
        "proton": {
            "label": proton.label,
            "confidence": proton.confidence,
            "expected_total_h": proton.expected_total_h,
            "observed_total_h": proton.observed_total_h,
            "parsed_peak_count": proton.parsed_peak_count,
            "delta_total_h": proton.delta_total_h,
        },
        "carbon13": {
            "label": carbon.label,
            "confidence": carbon.confidence,
            "expected_carbon_atoms": carbon.expected_carbon_atoms,
            "observed_carbon_signals": carbon.observed_carbon_signals,
            "delta_carbon_signals": carbon.delta_carbon_signals,
        },
        "spectrum_viewer": {
            "preview_points": [(point.shift_ppm, point.intensity) for point in spectrum.preview_points],
            "inferred_nmr_text": spectrum.inferred_nmr_text,
            "display_mode": spectrum.metadata["display_mode"],
            "baseline_lock_visual_only": spectrum.metadata["baseline_lock_visual_only"],
        },
        "fid_recipe_defaults": {
            "selected_preset": fid.selected_preset,
            "phase_mode": fid.phase_mode,
            "baseline_correction": fid.baseline_correction,
            "baseline_order": fid.baseline_order,
            "display_mode": fid.display_mode,
            "vertical_gain": fid.vertical_gain,
            "debug_preview": fid.debug_preview,
        },
    }


def test_week25_golden_fixture_files_exist() -> None:
    required = {
        "proton_ethanol.json",
        "carbon13_ethanol.csv",
        "spectrum_1h_trace.csv",
        "fid_bruker_acqus.txt",
        "cosy_ethanol.csv",
        "hsqc_ethanol.csv",
        "hmbc_ethanol.csv",
    }

    assert required <= {path.name for path in FIXTURES.iterdir()}
    assert "##$NUC1= <1H>" in (FIXTURES / "fid_bruker_acqus.txt").read_text()


def test_2d_analysis_does_not_alter_stable_1d_fid_or_viewer_outputs() -> None:
    before = _stable_snapshot()
    preview = parse_processed_2d_nmr("hsqc_ethanol.csv", (FIXTURES / "hsqc_ethanol.csv").read_bytes())

    report = analyze_nmr2d(
        smiles="CCO",
        preview=preview,
        sample_id="ethanol-2d",
        solvent="CDCl3",
        proton_nmr_text=PROTON_TEXT,
        carbon13_text=CARBON_TEXT,
    )

    assert report.peak_count == 2
    assert _stable_snapshot() == before


def test_stable_route_snapshots_with_2d_feature_enabled(tmp_path) -> None:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'week25_protection.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            enable_2d_nmr=True,
        )
    )
    with TestClient(app) as client:
        health = client.get("/health")
        presets = client.get("/fid/presets")
        status = client.get("/nmr2d/status")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["checks"]["app"] == "ok"
    assert presets.status_code == 200
    assert [preset["id"] for preset in presets.json()] == [
        "baseline_preserve",
        "balanced",
        "sensitive_weak_peaks",
        "higher_resolution",
        "custom",
    ]
    balanced = next(preset for preset in presets.json() if preset["id"] == "balanced")
    assert balanced["settings"]["phase_mode"] == "auto"
    assert balanced["settings"]["baseline_correction"] == "bernstein"
    assert balanced["settings"]["baseline_order"] == 3
    assert status.status_code == 200
    assert status.json()["enabled"] is True
    assert status.json()["contour_preview_enabled"] is True
    assert status.json()["raw_2d_fid_beta_enabled"] is False
    assert status.json()["supported_experiments"] == ["COSY", "HSQC", "HMQC", "HMBC"]
