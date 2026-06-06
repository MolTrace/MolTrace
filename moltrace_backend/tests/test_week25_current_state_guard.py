from __future__ import annotations

from pathlib import Path

import numpy as np
from test_current_state_guard import (
    CARBON13_ANALYZE_KEYS,
    FID_PROCESS_KEYS,
    PROTON_EVIDENCE_KEYS,
    SPECTRUM_PREVIEW_KEYS,
    _client,
    _fid_form,
    _load_json,
    _synthetic_bruker_zip,
)
from test_current_state_guard import (
    FIXTURES as STATE_FIXTURES,
)

from nmrcheck.baseline import apply_bernstein_baseline_correction
from nmrcheck.fid import _auto_phase_spectrum, apply_phase

NMR2D_FIXTURES = Path(__file__).parent / "fixtures" / "nmr2d"


def test_existing_spectrum_preview_output_remains_stable_after_2d_preview(tmp_path) -> None:
    client, headers = _client(tmp_path)
    content = (STATE_FIXTURES / "processed_spectrum_trace.csv").read_bytes()
    with client:
        before = client.post(
            "/spectrum/preview",
            headers=headers,
            files={"file": ("processed_spectrum_trace.csv", content, "text/csv")},
        )
        nmr2d = client.post(
            "/nmr2d/preview",
            headers=headers,
            files={
                "file": (
                    "ethanol_hsqc.csv",
                    (NMR2D_FIXTURES / "ethanol_hsqc.csv").read_bytes(),
                    "text/csv",
                )
            },
        )
        after = client.post(
            "/spectrum/preview",
            headers=headers,
            files={"file": ("processed_spectrum_trace.csv", content, "text/csv")},
        )

    assert nmr2d.status_code == 200, nmr2d.text
    assert before.status_code == 200
    assert after.status_code == 200
    assert set(before.json()) == SPECTRUM_PREVIEW_KEYS
    assert set(after.json()) == SPECTRUM_PREVIEW_KEYS
    assert before.json()["preview_points"] == after.json()["preview_points"]
    assert set(before.json()["metadata"]) == set(after.json()["metadata"])


def test_existing_fid_process_route_still_accepts_phase_and_baseline_fields(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post(
            "/fid/process",
            headers=headers,
            data=_fid_form(
                smiles="CCO",
                sample_id="week25-current-state-fid",
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
    assert set(response.json()) == FID_PROCESS_KEYS
    recipe = response.json()["preview"]["processing_metadata"]["processing_recipe"]
    assert recipe["phase_mode"] == "manual"
    assert recipe["baseline_correction"] == "bernstein"
    assert recipe["baseline_order"] == 3


def test_existing_carbon13_analyze_ethanol_still_passes(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post("/carbon13/analyze", headers=headers, json=_load_json("ethanol_carbon13_inputs.json"))

    assert response.status_code == 200, response.text
    assert set(response.json()) == CARBON13_ANALYZE_KEYS
    assert response.json()["label"] == "carbon_count_consistent"
    assert response.json()["confidence"] == 0.96


def test_existing_proton_evidence_ethanol_still_passes(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        response = client.post("/proton/evidence", headers=headers, json=_load_json("ethanol_inputs.json"))

    assert response.status_code == 200, response.text
    assert set(response.json()) == PROTON_EVIDENCE_KEYS
    assert response.json()["label"] == "consistent"
    assert response.json()["overall_score"] == 1.0


def test_existing_baseline_and_phase_focused_paths_still_pass() -> None:
    points = [
        (float(idx), np.exp(-((idx - 40) ** 2) / 20.0) * 8.0 + 0.01 * idx + 0.5)
        for idx in range(80)
    ]
    corrected, metadata, warnings = apply_bernstein_baseline_correction(points, order=3)
    assert warnings == []
    assert metadata["correction_applied"] is True
    assert max(y for _x, y in corrected) > 5.0

    axis = np.linspace(-2.0, 2.0, 256)
    clean = np.exp(-(axis**2) / 0.04).astype(np.complex128)
    misphased = apply_phase(clean, p0=45.0)
    phased, phase_metadata, _phase_warnings = _auto_phase_spectrum(misphased, mode="auto")
    assert phase_metadata["phase_correction_applied"] is True
    assert np.max(np.real(phased)) > np.max(np.real(misphased))


def test_2d_requests_do_not_alter_existing_metadata_schemas(tmp_path) -> None:
    client, headers = _client(tmp_path)
    spectrum_content = (STATE_FIXTURES / "processed_spectrum_trace.csv").read_bytes()
    with client:
        spectrum = client.post(
            "/spectrum/preview",
            headers=headers,
            files={"file": ("processed_spectrum_trace.csv", spectrum_content, "text/csv")},
        )
        proton = client.post("/proton/evidence", headers=headers, json=_load_json("ethanol_inputs.json"))
        carbon = client.post("/carbon13/analyze", headers=headers, json=_load_json("ethanol_carbon13_inputs.json"))
        nmr2d = client.post(
            "/nmr2d/analyze",
            headers=headers,
            data={
                "smiles": "CCO",
                "sample_id": "schema-guard-2d",
                "solvent": "CDCl3",
                "proton_nmr_text": _load_json("ethanol_inputs.json")["nmr_text"],
                "carbon13_text": _load_json("ethanol_carbon13_inputs.json")["carbon13_text"],
                "save_run": "false",
            },
            files={
                "file": (
                    "ethanol_hsqc.csv",
                    (NMR2D_FIXTURES / "ethanol_hsqc.csv").read_bytes(),
                    "text/csv",
                )
            },
        )

    assert nmr2d.status_code == 200, nmr2d.text
    assert set(spectrum.json()) == SPECTRUM_PREVIEW_KEYS
    assert set(proton.json()) == PROTON_EVIDENCE_KEYS
    assert set(carbon.json()) == CARBON13_ANALYZE_KEYS
