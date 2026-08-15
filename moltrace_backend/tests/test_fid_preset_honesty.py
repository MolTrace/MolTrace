"""Processing presets must do what their labels say (Prompt 2, A5).

Verified before this change: the four SpectraCheck preset ids
(``safe_automatic``, ``imported_parameters``, ``no_baseline_correction``,
``no_phase_correction``) were all unknown to ``normalize_fid_preset_id``,
silently fell back to "balanced", and produced byte-identical settings — so
"No baseline correction" still applied Bernstein baseline + auto phase.

These tests pin the fix at all three layers: id resolution, the settings a
preset yields (including surviving the 1H advised-processing constraints),
and the pipeline metadata a processed archive reports.
"""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from nmrcheck.fid import (
    UnknownFIDPresetError,
    fid_settings_from_preset,
    normalize_fid_preset_id,
    process_bruker_1d_zip,
    resolve_fid_preset_id_strict,
)


def _bruker_zip(*, title: str, points: int = 2048) -> bytes:
    sw_hz = 5000.0
    sfo1_mhz = 400.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65)]:
        freq = (ppm - center_ppm) * sfo1_mhz
        fid += amplitude * np.exp(2j * np.pi * freq * time_axis) * np.exp(-time_axis * 8.0)
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = (
        f"##TITLE= {title}\n"
        f"##$TD= {points * 2}\n"
        f"##$SW_h= {sw_hz}\n"
        "##$SW= 12.5\n"
        f"##$SFO1= {sfo1_mhz}\n"
        f"##$BF1= {sfo1_mhz}\n"
        f"##$O1= {center_ppm * sfo1_mhz}\n"
        f"##$O1P= {center_ppm}\n"
        "##$NUC1= <1H>\n"
        "##$BYTORDA= 0\n"
        "##$DTYPA= 0\n"
        "##$GRPDLY= 0\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("sample/fid", interleaved.tobytes())
        archive.writestr("sample/acqus", acqus)
        archive.writestr("sample/pulseprogram", "zg30\n")
    return buffer.getvalue()


def test_product_preset_ids_resolve_to_real_presets() -> None:
    assert resolve_fid_preset_id_strict("safe_automatic") == "balanced"
    assert resolve_fid_preset_id_strict("no_baseline_correction") == "baseline_preserve"
    assert resolve_fid_preset_id_strict("no_phase_correction") == "phase_preserve"
    assert resolve_fid_preset_id_strict(None) == "balanced"
    assert resolve_fid_preset_id_strict("Balanced") == "balanced"


def test_unknown_preset_id_is_refused_naming_the_id() -> None:
    with pytest.raises(UnknownFIDPresetError, match="imported_parameters"):
        resolve_fid_preset_id_strict("imported_parameters")
    # The lenient normalizer keeps its fallback for internal callers.
    assert normalize_fid_preset_id("imported_parameters") == "balanced"


def test_presets_yield_distinct_settings() -> None:
    automatic = fid_settings_from_preset(selected_preset="safe_automatic")
    no_baseline = fid_settings_from_preset(selected_preset="no_baseline_correction")
    no_phase = fid_settings_from_preset(selected_preset="no_phase_correction")

    assert automatic.auto_baseline is True
    assert automatic.auto_phase is True

    assert no_baseline.auto_baseline is False
    assert no_baseline.baseline_correction == "preserve"
    assert no_baseline.auto_phase is True

    assert no_phase.auto_phase is False
    assert no_phase.phase_mode == "none"
    assert no_phase.auto_baseline is True

    assert automatic.model_dump() != no_baseline.model_dump()
    assert automatic.model_dump() != no_phase.model_dump()


def test_no_baseline_preset_survives_pipeline_end_to_end() -> None:
    archive = _bruker_zip(title="preset-honesty-no-baseline")
    settings = fid_settings_from_preset(selected_preset="no_baseline_correction")
    report = process_bruker_1d_zip(
        filename="sample.zip",
        content=archive,
        solvent="CDCl3",
        nucleus="1H",
        settings=settings,
    )
    baseline = (report.metadata or {}).get("baseline") or {}
    assert baseline.get("correction_applied") is not True, (
        "'No baseline correction' must not apply a baseline correction — the "
        "advised 1H constraints used to stomp this preset back to Bernstein"
    )


def test_no_phase_preset_survives_pipeline_end_to_end() -> None:
    archive = _bruker_zip(title="preset-honesty-no-phase")
    settings = fid_settings_from_preset(selected_preset="no_phase_correction")
    report = process_bruker_1d_zip(
        filename="sample.zip",
        content=archive,
        solvent="CDCl3",
        nucleus="1H",
        settings=settings,
    )
    phase = (report.metadata or {}).get("phase") or {}
    assert phase.get("mode") == "none"
    assert phase.get("correction_applied") is not True


def test_presets_change_the_preview_trace() -> None:
    """The 'no correction' presets must visibly change the computed trace."""

    archive = _bruker_zip(title="preset-honesty-trace-difference")
    automatic = process_bruker_1d_zip(
        filename="sample.zip",
        content=archive,
        solvent="CDCl3",
        nucleus="1H",
        settings=fid_settings_from_preset(selected_preset="safe_automatic"),
    )
    preserved = process_bruker_1d_zip(
        filename="sample.zip",
        content=archive,
        solvent="CDCl3",
        nucleus="1H",
        settings=fid_settings_from_preset(selected_preset="no_baseline_correction"),
    )
    automatic_trace = [(p.shift_ppm, p.intensity) for p in automatic.preview_points]
    preserved_trace = [(p.shift_ppm, p.intensity) for p in preserved.preview_points]
    assert automatic_trace != preserved_trace


def test_preview_route_rejects_unknown_preset_naming_it(
    client: TestClient, api_headers: dict[str, str]
) -> None:
    response = client.post(
        "/nmr/raw-fid/preview",
        headers=api_headers,
        files={"file": ("sample.zip", _bruker_zip(title="route-422"), "application/zip")},
        data={"processing_preset": "imported_parameters"},
    )
    assert response.status_code == 422
    assert "imported_parameters" in str(response.json().get("detail"))


def test_preview_route_accepts_product_preset_ids(
    client: TestClient, api_headers: dict[str, str]
) -> None:
    response = client.post(
        "/nmr/raw-fid/preview",
        headers=api_headers,
        files={"file": ("sample.zip", _bruker_zip(title="route-accepts"), "application/zip")},
        data={"processing_preset": "no_baseline_correction"},
    )
    assert response.status_code == 200
