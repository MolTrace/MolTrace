import csv
import io
import zipfile

import numpy as np

from nmrcheck.baseline import (
    apply_bernstein_baseline_correction,
    apply_signal_free_smooth_baseline_polish,
    apply_simple_baseline_correction,
    fit_bernstein_baseline,
)
from nmrcheck.fid import (
    _apply_raw_fid_advised_constraints,
    _auto_phase_spectrum,
    _fine_tune_solvent_display_regions,
    _smooth_fid_display_trace,
    apply_phase,
    fid_settings_from_preset,
    phase_score,
    process_bruker_1d_zip,
    process_raw_fid_zip_to_spectrum,
)
from nmrcheck.spectrum import parse_processed_spectrum


def _csv_trace(points: list[tuple[float, float]]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ppm", "intensity"])
    writer.writerows(points)
    return out.getvalue().encode()


def test_raw_fid_proton_advised_constraints_preserve_multiplet_resolution() -> None:
    settings = fid_settings_from_preset(selected_preset="balanced")

    constrained, detail, notes = _apply_raw_fid_advised_constraints(settings, nucleus="1H")

    assert detail["applied"] is True
    assert detail["scope"] == "raw_fid_only"
    assert detail["processed_uploads_touched"] is False
    assert detail["resolution_policy"] == "multiplet_preserving_no_exponential_line_broadening"
    assert constrained.zero_fill_factor == 3
    assert constrained.apodization_mode == "trapezoidal"
    assert constrained.line_broadening_hz == 0.0
    assert constrained.auto_phase is True
    assert constrained.phase_mode == "auto"
    assert constrained.auto_baseline is True
    assert constrained.baseline_correction == "bernstein"
    assert constrained.baseline_order == 3
    assert constrained.max_preview_points >= 12000
    assert any("Raw 1H FID advised processing applied" in note for note in notes)


def _synthetic_cubic_baseline_points() -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    points: list[tuple[float, float]] = []
    peak_only: list[tuple[float, float]] = []
    for idx in range(260):
        x = idx / 25.0
        baseline = 0.018 * (x - 5.0) ** 3 - 0.06 * (x - 5.0) + 0.35
        peak = 8.0 * np.exp(-((x - 5.0) ** 2) / (2 * 0.08**2))
        shoulder = 1.4 * np.exp(-((x - 2.1) ** 2) / (2 * 0.06**2))
        points.append((x, float(baseline + peak + shoulder)))
        peak_only.append((x, float(peak + shoulder)))
    return points, peak_only


def _build_bruker_zip(*, phase_degrees: float = 0.0, baseline_curve: bool = False) -> bytes:
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
    if baseline_curve:
        fid += 0.03 * np.exp(-time_axis * 0.8)
    if phase_degrees:
        fid *= np.exp(1j * np.deg2rad(phase_degrees))

    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = f"""##TITLE= synthetic phase baseline regression
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


def test_bernstein_baseline_correction_removes_known_cubic_baseline() -> None:
    points, peak_only = _synthetic_cubic_baseline_points()

    corrected, metadata, warnings = apply_bernstein_baseline_correction(points, order=3)

    peak_x_before = points[int(np.argmax([y for _x, y in points]))][0]
    peak_x_after = corrected[int(np.argmax([y for _x, y in corrected]))][0]
    off_peak_raw = [
        abs(y)
        for (x, y), (_px, peak_y) in zip(points, peak_only, strict=True)
        if peak_y < 0.05 and 0.5 < x < 9.5
    ]
    off_peak_corrected = [
        abs(y)
        for (x, y), (_px, peak_y) in zip(corrected, peak_only, strict=True)
        if peak_y < 0.05 and 0.5 < x < 9.5
    ]

    assert not warnings
    assert metadata["method"] == "bernstein_polynomial"
    assert metadata["order"] == 3
    assert metadata["correction_applied"] is True
    assert np.median(off_peak_corrected) < np.median(off_peak_raw) * 0.55
    assert abs(peak_x_after - peak_x_before) <= 0.05


def test_bernstein_order_defaults_to_three() -> None:
    points, _peak_only = _synthetic_cubic_baseline_points()

    _corrected, metadata, _warnings = apply_bernstein_baseline_correction(points)

    assert metadata["order"] == 3


def test_fit_bernstein_baseline_returns_auditable_model_points() -> None:
    points, _peak_only = _synthetic_cubic_baseline_points()

    model_points, metadata, warnings = fit_bernstein_baseline(points)

    assert not warnings
    assert len(model_points) == len(points)
    assert metadata["order"] == 3
    assert metadata["coefficients"]


def test_bernstein_baseline_does_not_distort_already_clean_spectrum() -> None:
    points = []
    for idx in range(240):
        x = idx / 24.0
        y = (
            7.0 * np.exp(-((x - 4.0) ** 2) / (2 * 0.06**2))
            + 2.0 * np.exp(-((x - 7.2) ** 2) / (2 * 0.05**2))
        )
        points.append((x, float(y)))

    corrected, metadata, warnings = apply_bernstein_baseline_correction(points, order=3)

    assert not warnings
    assert metadata["correction_applied"] is True
    assert abs(max(y for _x, y in corrected) - max(y for _x, y in points)) < 0.05
    assert np.median([abs(y) for x, y in corrected if abs(x - 4.0) > 0.2 and abs(x - 7.2) > 0.2]) < 0.05


def test_signal_free_polish_flattens_rolling_fid_baseline_without_moving_peaks() -> None:
    x_values = np.linspace(0.0, 12.0, 720)
    baseline = (
        0.34 * np.sin((x_values - 1.3) / 12.0 * 2.0 * np.pi)
        + 0.18 * ((x_values - 6.0) / 6.0) ** 2
        - 0.12 * (x_values - 6.0) / 6.0
    )
    peak_only = (
        7.0 * np.exp(-((x_values - 2.15) ** 2) / (2 * 0.025**2))
        + 5.5 * np.exp(-((x_values - 5.75) ** 2) / (2 * 0.030**2))
        + 4.0 * np.exp(-((x_values - 9.35) ** 2) / (2 * 0.035**2))
    )
    points = [(float(x), float(y)) for x, y in zip(x_values, baseline + peak_only, strict=True)]

    corrected, metadata, warnings = apply_signal_free_smooth_baseline_polish(points)

    assert not warnings
    assert metadata["correction_applied"] is True
    assert metadata["qa_after"]["score"] >= metadata["qa_before"]["score"]
    off_peak_raw = [
        abs(y)
        for (_x, y), peak_y in zip(points, peak_only, strict=True)
        if peak_y < 0.02
    ]
    off_peak_corrected = [
        abs(y)
        for (_x, y), peak_y in zip(corrected, peak_only, strict=True)
        if peak_y < 0.02
    ]
    assert np.median(off_peak_corrected) < np.median(off_peak_raw) * 0.25

    peak_x_before = points[int(np.argmax([y for _x, y in points]))][0]
    peak_x_after = corrected[int(np.argmax([y for _x, y in corrected]))][0]
    assert abs(peak_x_after - peak_x_before) < 0.03

    base_medians = []
    for center in (2.15, 5.75, 9.35):
        base_medians.append(
            float(
                np.median(
                    [
                        y
                        for x, y in corrected
                        if 0.12 <= abs(x - center) <= 0.22
                    ]
                )
            )
        )
    assert max(base_medians) - min(base_medians) < 0.08


def test_raw_fid_display_envelope_preserves_noise_and_limits_negative_lobes() -> None:
    x_values = np.linspace(12.0, 0.0, 2400)
    peak = 5.0 * np.exp(-((x_values - 7.25) ** 2) / (2 * 0.018**2))
    peak += 2.3 * np.exp(-((x_values - 1.15) ** 2) / (2 * 0.025**2))
    ripple = 0.045 * np.sin(np.arange(x_values.size) * 1.7)
    ripple += 0.035 * np.cos(np.arange(x_values.size) * 0.63)
    negative_lobes = np.zeros_like(x_values)
    negative_lobes[np.argmin(np.abs(x_values - 7.31))] = -3.0
    negative_lobes[np.argmin(np.abs(x_values - 4.2))] = -2.4
    points = [
        (float(x), float(y))
        for x, y in zip(x_values, peak + ripple + negative_lobes, strict=True)
    ]

    smoothed, metadata = _smooth_fid_display_trace(points, nucleus="1H")
    tuned, solvent_meta = _fine_tune_solvent_display_regions(
        smoothed,
        solvent="CDCl3",
        nucleus="1H",
        noise_sigma=metadata["noise_sigma"],
    )

    assert metadata["applied"] is True
    assert metadata["display_only"] is True
    assert metadata["method"] == "raw_fid_noise_envelope"
    assert metadata["smoothing_kernel"] == "none"
    assert metadata["baseline_noise_preserved"] is True
    assert metadata["negative_lobes_limited"] == 0
    assert solvent_meta["applied"] is True
    assert solvent_meta["negative_lobes_limited"] >= 1
    assert solvent_meta["scope"] == "known_solvent_windows_only"
    before_y = np.asarray([y for _x, y in points])
    centered_y = np.asarray([y for _x, y in smoothed])
    after_y = np.asarray([y for _x, y in tuned])
    noise_mask = (x_values >= 10.0) & (x_values <= 11.5)
    solvent_mask = (x_values >= 7.20) & (x_values <= 7.32)
    non_solvent_negative_mask = np.isclose(x_values, 4.2, atol=0.01)

    assert float(np.max(after_y)) >= float(np.max(before_y)) * 0.99
    assert float(np.min(after_y[solvent_mask])) > float(np.min(centered_y[solvent_mask]))
    assert np.allclose(after_y[non_solvent_negative_mask], centered_y[non_solvent_negative_mask])
    assert float(np.std(after_y[noise_mask])) > 0.0
    assert float(np.max(after_y[noise_mask])) > 0.0
    assert float(np.min(after_y[noise_mask])) < 0.0
    assert abs(float(x_values[np.argmax(before_y)]) - float(x_values[np.argmax(after_y)])) < 0.02


def test_raw_fid_carbon13_solvent_region_near_49_ppm_uses_baseline_floor() -> None:
    x_values = np.linspace(220.0, -10.0, 4800)
    peak = 7.0 * np.exp(-((x_values - 49.0) ** 2) / (2 * 0.018**2))
    peak += 2.5 * np.exp(-((x_values - 49.35) ** 2) / (2 * 0.026**2))
    peak += 1.8 * np.exp(-((x_values - 52.0) ** 2) / (2 * 0.030**2))
    ripple = 0.04 * np.sin(np.arange(x_values.size) * 1.31)
    ripple += 0.025 * np.cos(np.arange(x_values.size) * 0.47)
    negative_lobes = np.zeros_like(x_values)
    negative_lobes[np.argmin(np.abs(x_values - 48.92))] = -3.8
    negative_lobes[np.argmin(np.abs(x_values - 52.06))] = -2.2
    points = [
        (float(x), float(y))
        for x, y in zip(x_values, peak + ripple + negative_lobes, strict=True)
    ]

    smoothed, metadata = _smooth_fid_display_trace(points, nucleus="1H")
    centered_y = np.asarray([y for _x, y in smoothed])
    solvent_mask = (x_values >= 48.2) & (x_values <= 50.2)
    non_solvent_negative_mask = np.isclose(x_values, 52.06, atol=0.01)

    for solvent, expect_fallback in (("methanol-d4", False), (None, True)):
        tuned, solvent_meta = _fine_tune_solvent_display_regions(
            smoothed,
            solvent=solvent,
            nucleus="1H",
            noise_sigma=metadata["noise_sigma"],
        )
        after_y = np.asarray([y for _x, y in tuned])

        assert solvent_meta["applied"] is True
        assert solvent_meta["nucleus"] == "13C"
        assert solvent_meta["carbon13_axis_detected"] is True
        assert solvent_meta["added_carbon13_floor_window"] is expect_fallback
        assert any(window.get("floor_mode") == "baseline_floor" for window in solvent_meta["windows"])
        assert float(np.min(centered_y[solvent_mask])) < 0.0
        assert float(np.min(after_y[solvent_mask])) >= 0.0
        assert float(np.max(after_y[solvent_mask])) == float(np.max(centered_y[solvent_mask]))
        assert np.allclose(after_y[non_solvent_negative_mask], centered_y[non_solvent_negative_mask])


def test_preserve_mode_does_not_change_points() -> None:
    points, _peak_only = _synthetic_cubic_baseline_points()

    corrected, metadata, warnings = apply_simple_baseline_correction(points, mode="preserve")

    assert corrected == points
    assert warnings == []
    assert metadata["correction_applied"] is False


def test_auto_phase_correction_improves_synthetic_misphased_spectrum() -> None:
    axis = np.linspace(-1.0, 1.0, 512)
    absorption = (
        4.0 * np.exp(-((axis + 0.35) ** 2) / (2 * 0.025**2))
        + 2.5 * np.exp(-((axis - 0.28) ** 2) / (2 * 0.035**2))
    )
    clean = absorption.astype(np.complex128)
    misphased = apply_phase(clean, p0=55.0)

    before = phase_score(np.real(misphased), np.imag(misphased))
    phased, metadata, warnings = _auto_phase_spectrum(misphased, mode="auto")
    after = phase_score(np.real(phased), np.imag(phased))

    assert metadata["phase_correction_applied"] is True
    assert abs(metadata["zero_order_degrees"]) > 1.0
    assert after >= before
    assert isinstance(warnings, list)


def test_manual_phase_correction_applies_p0_p1() -> None:
    spectrum = np.ones(64, dtype=np.complex128)

    phased, metadata, warnings = _auto_phase_spectrum(
        spectrum,
        mode="manual",
        phase_p0=45.0,
        phase_p1=0.0,
    )

    assert warnings == []
    assert metadata["phase_mode"] == "manual"
    assert metadata["phase_correction_applied"] is True
    assert not np.allclose(phased, spectrum)


def test_raw_fid_processing_metadata_reports_auto_phase_and_bernstein_baseline() -> None:
    settings = fid_settings_from_preset(
        selected_preset="balanced",
        zero_fill_factor=1,
        line_broadening_hz=0.0,
        phase_mode="auto",
        baseline_correction="bernstein",
        baseline_order=3,
    )

    report = process_bruker_1d_zip(
        filename="fid.zip",
        content=_build_bruker_zip(phase_degrees=35.0, baseline_curve=True),
        settings=settings,
    )

    metadata = report.processing_metadata
    assert metadata.phase_settings["phase_mode"] in {"auto_acme", "auto_peak_minima", "auto_grid"}
    assert "phase_p0" in report.metadata
    assert "phase_p1" in report.metadata
    assert "phase_score" in report.metadata
    assert report.metadata["phase"]["mode"] == report.metadata["phase_mode"]
    assert report.metadata["phase"]["score"] == report.metadata["phase_score"]
    assert metadata.baseline_correction["baseline_correction"] == "bernstein"
    assert metadata.baseline_correction["baseline_order"] == 3
    assert metadata.baseline_correction["correction_applied"] is True
    assert metadata.baseline_correction["post_baseline_polish"]["baseline_locked_to_zero"] is True
    assert "qa_after" in metadata.baseline_correction["post_baseline_polish"]
    assert metadata.baseline_correction["flatness_qa"]
    assert report.metadata["baseline"]["mode"] == "bernstein"
    assert report.metadata["baseline"]["order"] == 3
    assert report.metadata["baseline"]["qa"]
    assert report.metadata["baseline_qa"]
    assert report.metadata["original_spectrum_state"]["processing_stage"] == "post_fft_phase_pre_baseline"
    assert report.metadata["original_spectrum_state"]["preview_points_omitted"] is True
    assert report.metadata["display_preprocessing"]["trace_smoothing"]["applied"] is True
    assert report.metadata["display_preprocessing"]["trace_smoothing"]["display_only"] is True
    assert report.metadata["evidence_trace_mode"] == "raw_fid_fft_real_baseline_corrected"


def test_process_raw_fid_zip_to_spectrum_alias_uses_same_defaults() -> None:
    report = process_raw_fid_zip_to_spectrum(
        filename="fid.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="balanced", zero_fill_factor=1),
    )

    assert report.metadata["phase_mode"] in {"auto_acme", "auto_peak_minima", "auto_grid"}
    assert report.metadata["baseline"]["mode"] == "bernstein"
    assert report.metadata["baseline"]["order"] == 3


def test_raw_fid_raw_preview_points_are_debug_only() -> None:
    default = process_bruker_1d_zip(
        filename="fid.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(selected_preset="balanced", zero_fill_factor=1),
    )
    debug = process_bruker_1d_zip(
        filename="fid.zip",
        content=_build_bruker_zip(),
        settings=fid_settings_from_preset(
            selected_preset="balanced",
            zero_fill_factor=1,
            debug_preview=True,
        ),
    )

    assert "raw_preview_points" not in default.metadata
    assert "raw_preview_points" in debug.metadata


def test_processed_uploaded_spectrum_applies_default_baseline_and_display_smoothing() -> None:
    points, _peak_only = _synthetic_cubic_baseline_points()

    preview = parse_processed_spectrum(filename="processed.csv", content=_csv_trace(points))

    assert [(p.shift_ppm, p.intensity) for p in preview.preview_points] != points
    assert preview.metadata["processed_baseline_correction"]["order"] == 3
    assert preview.metadata["processed_baseline_correction"]["correction_applied"] is True
    assert (
        preview.metadata["processed_baseline_correction"]["post_baseline_polish"]["baseline_locked_to_zero"]
        is True
    )
    assert preview.metadata["display_preprocessing"]["trace_smoothing"]["applied"] is True
    assert preview.metadata["display_preprocessing"]["trace_smoothing"]["display_only"] is True
    assert preview.metadata["display"]["main_trace"] == "display_smoothed_evidence_intensity"
    assert preview.metadata["evidence_trace_mode"] == "uploaded_intensity_baseline_corrected"


def test_processed_uploaded_spectrum_can_preserve_baseline_when_explicit() -> None:
    points, _peak_only = _synthetic_cubic_baseline_points()

    uncorrected = parse_processed_spectrum(
        filename="processed.csv",
        content=_csv_trace(points),
        processed_baseline_correction="none",
    )
    preview = parse_processed_spectrum(
        filename="processed.csv",
        content=_csv_trace(points),
        processed_baseline_correction="bernstein",
    )

    assert uncorrected.metadata["processed_baseline_correction"]["correction_applied"] is False
    assert uncorrected.metadata["evidence_trace_mode"] == "uploaded_intensity"
    assert [(p.shift_ppm, p.intensity) for p in preview.preview_points] != points
    assert preview.metadata["processed_baseline_correction"]["order"] == 3
    assert preview.metadata["processed_baseline_correction"]["correction_applied"] is True
    assert (
        preview.metadata["baseline_flatness_qa"]["score"]
        >= uncorrected.metadata["baseline_flatness_qa"]["score"]
    )
    assert preview.metadata["evidence_trace_mode"] == "uploaded_intensity_baseline_corrected"


def test_vertical_gain_still_does_not_change_preview_points() -> None:
    points, _peak_only = _synthetic_cubic_baseline_points()

    normal = parse_processed_spectrum(filename="processed.csv", content=_csv_trace(points), vertical_gain=1)
    gained = parse_processed_spectrum(filename="processed.csv", content=_csv_trace(points), vertical_gain=100)

    assert [(p.shift_ppm, p.intensity) for p in gained.preview_points] == [
        (p.shift_ppm, p.intensity) for p in normal.preview_points
    ]
    assert gained.metadata["display_gain"] == 100.0
