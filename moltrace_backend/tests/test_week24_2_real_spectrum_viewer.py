import csv
import io
import zipfile

import numpy as np

from nmrcheck.api import _fid_settings_from_form
from nmrcheck.fid import fid_settings_from_preset, process_bruker_1d_zip
from nmrcheck.spectrum import _downsample_points, parse_processed_spectrum
from nmrcheck.web import index


def _csv_trace(points: list[tuple[float, float]]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ppm", "intensity"])
    writer.writerows(points)
    return out.getvalue().encode()


def _synthetic_peak_trace() -> bytes:
    points: list[tuple[float, float]] = []
    for idx in range(600):
        ppm = 6.0 - idx * 0.01
        signal = 0.03 if idx % 2 else -0.03
        signal += 10.0 * np.exp(-((ppm - 4.2) ** 2) / (2 * 0.025**2))
        signal += 1.6 * np.exp(-((ppm - 2.1) ** 2) / (2 * 0.02**2))
        signal += 4.0 * np.exp(-((ppm - 1.2) ** 2) / (2 * 0.018**2))
        points.append((ppm, float(signal)))
    return _csv_trace(points)


def _preview_y_values(preview) -> list[float]:
    return [point.intensity for point in preview.preview_points]


def _peak_signature(preview) -> list[tuple[float, str, float]]:
    return [
        (round(peak.shift_ppm, 4), peak.multiplicity, round(peak.integration_h, 4))
        for peak in preview.inferred_peaks
    ]


def _build_bruker_zip() -> bytes:
    points = 1024
    sw_hz = 5000.0
    sfo1 = 500.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
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
    acqus = f"""##TITLE= synthetic real-spectrum regression
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
        archive.writestr("sample/fid", interleaved.tobytes())
        archive.writestr("sample/acqus", acqus)
    return buffer.getvalue()


def test_default_processed_preview_preserves_exact_uploaded_intensities() -> None:
    points = [(5.0, 0.0), (4.0, 2.5), (3.0, -0.25), (2.0, 8.0)]

    preview = parse_processed_spectrum(filename="small.csv", content=_csv_trace(points))

    assert [(p.shift_ppm, p.intensity) for p in preview.preview_points] == points
    assert preview.metadata["display_mode"] == "real"
    assert preview.metadata["display"]["mode"] == "real"
    assert preview.metadata["evidence_trace_mode"] == "uploaded_intensity"
    assert preview.metadata["baseline_lock_visual_only"] is True


def test_deprecated_mnova_locked_display_mode_maps_to_real_without_changing_intensities() -> None:
    points = [(5.0, 0.0), (4.0, 1.0), (3.0, 20.0), (2.0, 0.5)]

    preview = parse_processed_spectrum(
        filename="deprecated.csv",
        content=_csv_trace(points),
        display_mode="mnova_locked",
        vertical_gain=100,
    )

    assert [(p.shift_ppm, p.intensity) for p in preview.preview_points] == points
    assert preview.metadata["display_mode"] == "real"
    assert preview.metadata["display_gain"] == 100.0
    assert preview.metadata["display"]["vertical_gain"] == 100.0
    assert any("Deprecated display_mode='mnova_locked'" in warning for warning in preview.warnings)


def test_vertical_gain_does_not_change_preview_points_or_inferred_peaks() -> None:
    content = _synthetic_peak_trace()

    normal = parse_processed_spectrum(filename="trace.csv", content=content, vertical_gain=1)
    gained = parse_processed_spectrum(filename="trace.csv", content=content, vertical_gain=100)

    assert _preview_y_values(gained) == _preview_y_values(normal)
    assert _peak_signature(gained) == _peak_signature(normal)
    assert gained.metadata["display_gain"] == 100.0


def test_raw_preview_points_are_debug_only() -> None:
    content = _synthetic_peak_trace()

    default = parse_processed_spectrum(filename="trace.csv", content=content)
    debug = parse_processed_spectrum(filename="trace.csv", content=content, debug_preview=True)

    assert "raw_preview_points" not in default.metadata
    assert "raw_preview_points" in debug.metadata
    assert debug.metadata["display_preprocessing"]["trace_smoothing"]["applied"] is True
    assert debug.metadata["raw_preview_points"] != [
        point.model_dump(mode="json") for point in debug.preview_points
    ]


def test_default_preview_payload_is_capped_for_large_traces() -> None:
    points = [(10.0 - idx * 0.001, 1.0 if idx % 100 else 100.0) for idx in range(10_000)]

    preview = parse_processed_spectrum(filename="large.csv", content=_csv_trace(points))

    assert len(preview.preview_points) <= 1200
    assert preview.metadata["preview_downsampling"]["method"] == "min_max_bucket_extrema_preserving"
    assert "raw_preview_points" not in preview.metadata


def test_min_max_bucket_downsampling_keeps_narrow_high_intensity_spikes() -> None:
    points = [(idx * 0.2, 0.0) for idx in range(1000)]
    points[503] = (100.6, 500.0)
    points[709] = (141.8, -200.0)

    downsampled = _downsample_points(points, limit=101)
    intensities = [point.intensity for point in downsampled]

    assert 500.0 in intensities
    assert -200.0 in intensities
    assert len(downsampled) <= 101


def test_weak_peak_magnifier_is_display_only_and_not_used_for_peak_picking() -> None:
    content = _synthetic_peak_trace()

    real = parse_processed_spectrum(filename="trace.csv", content=content, display_mode="real")
    magnifier = parse_processed_spectrum(filename="trace.csv", content=content, display_mode="magnifier", vertical_gain=80)

    assert _preview_y_values(magnifier) == _preview_y_values(real)
    assert _peak_signature(magnifier) == _peak_signature(real)
    assert magnifier.metadata["display_mode"] == "magnifier"
    assert magnifier.metadata["display"]["weak_peak_magnifier"] is True
    assert magnifier.metadata["display_preprocessing"]["weak_peak_magnifier"]["display_only"] is True
    assert magnifier.metadata["display_preprocessing"]["weak_peak_magnifier"]["points"]


def test_weak_peak_magnifier_alias_is_supported_for_package_compatibility() -> None:
    preview = parse_processed_spectrum(
        filename="trace.csv",
        content=_synthetic_peak_trace(),
        display_mode="weak_peak_magnifier",
        vertical_gain=20,
    )

    assert preview.metadata["display_mode"] == "magnifier"
    assert preview.metadata["display"]["mode"] == "magnifier"
    assert preview.metadata["display"]["vertical_gain"] == 20.0
    assert preview.metadata["display_preprocessing"]["weak_peak_magnifier"]["display_only"] is True


def test_raw_fid_processing_separates_evidence_trace_from_display_metadata() -> None:
    report = process_bruker_1d_zip(
        filename="fid.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="balanced", display_mode="real", vertical_gain=50),
    )

    assert report.processing_metadata.baseline_correction["method"] == "bernstein_polynomial"
    assert report.processing_metadata.baseline_correction["baseline_order"] == 3
    assert report.processing_metadata.baseline_correction["correction_applied"] is True
    assert report.metadata["evidence_trace_mode"] == "raw_fid_fft_real_baseline_corrected"
    assert report.metadata["display_mode"] == "real"
    assert report.metadata["display_gain"] == 50.0
    assert report.metadata["baseline_lock_visual_only"] is True
    assert report.metadata["display"]["main_trace"] == "display_smoothed_evidence_intensity"
    assert report.metadata["display"]["trace_smoothing"]["display_only"] is True
    assert report.metadata["display"]["vertical_gain"] == 50.0
    assert report.metadata["display"]["weak_peak_magnifier"] is False
    assert "raw_preview_points" not in report.metadata


def test_fid_form_accepts_package_aliases_without_baseline_subtraction() -> None:
    settings = _fid_settings_from_form(
        selected_preset="balanced",
        processing_preset="baseline_preserve",
        zero_fill_factor=None,
        line_broadening_hz=None,
        apply_group_delay=True,
        auto_phase=True,
        auto_baseline=False,
        phase_mode="auto",
        phase_p0=0.0,
        phase_p1=0.0,
        baseline_correction="preserve",
        baseline_order=3,
        baseline_lock=True,
        peak_sensitivity=None,
        mask_solvent_regions=True,
        display_mode="weak_peak_magnifier",
        vertical_gain=25,
        debug_preview=False,
    )

    assert settings.selected_preset == "baseline_preserve"
    assert settings.auto_baseline is False
    assert settings.baseline_lock_visual_only is True
    assert settings.display_mode == "magnifier"
    assert settings.vertical_gain == 25.0


def test_web_defaults_do_not_submit_legacy_mnova_parameters_or_old_transform_language() -> None:
    html = index()

    assert 'formData.append("mnova_view"' not in html
    assert 'mnova_baseline' not in html
    assert 'mnova_display' not in html
    assert 'baseline-flattened' not in html
    assert 'weak-peak compression' not in html
    assert 'Real spectrum — original intensity' in html
    assert 'id="fidDisplayMode"' in html
    assert 'id="processedDisplayMode"' in html
    assert 'Real spectrum - original intensity' in html
    assert 'Evidence intensities stay preserved. The ¹H viewer equalizes the displayed baseline to y=0, and peak height controls adjust the y-axis only.' in html
    assert 'getSpectrumBaselineAnchorFraction' in html
    assert 'getSpectrumBaselineEqualizedDisplay' in html
    assert 'baseline-locked display' in html
    assert 'fixedrange: true' in html
    assert 'Plotly.relayout' in html
    assert 'setSpectrumVerticalScale' in html
    rerender_fn = html.split('function rerenderSpectrumPreview', 1)[1].split('function renderSpectrumGainControl', 1)[0]
    assert 'renderInteractiveSpectrumPlot(context.data, activeId)' in rerender_fn
    assert 'target.innerHTML' not in rerender_fn
    assert 'api(' not in rerender_fn
    gain_fn = html.split('function setSpectrumVerticalScale', 1)[1].split('function setSpectrumLabelThreshold', 1)[0]
    assert 'relayoutSpectrumPlot(getSpectrumYAxisUpdate' in gain_fn
    assert 'api(' not in gain_fn
    assert 'renderInteractiveSpectrumPlot' not in gain_fn
    assert 'Plotly.react' not in gain_fn
