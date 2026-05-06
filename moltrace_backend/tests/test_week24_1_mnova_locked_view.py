import csv
import io

from nmrcheck.mnova_view import make_mnova_locked_view, weak_peak_magnifier_view
from nmrcheck.spectrum import parse_processed_spectrum


def test_legacy_mnova_transform_is_disabled_and_preserves_points() -> None:
    points = []
    for i in range(500):
        ppm = 10.0 - i * 0.02
        signal = 0.02 * i
        if abs(ppm - 7.25) < 0.03:
            signal += 2.0
        if abs(ppm - 1.25) < 0.03:
            signal += 50.0
        points.append((ppm, signal))

    result = make_mnova_locked_view(
        points,
        enabled=True,
        baseline_lock=True,
        visual_gain=80,
    )

    assert result.points == points
    assert result.metadata["enabled"] is False
    assert result.metadata["legacy_transform_disabled"] is True
    assert result.metadata["evidence_trace_preserved"] is True


def test_weak_peak_magnifier_is_separate_display_only_view() -> None:
    points = []
    for i in range(800):
        ppm = 12.0 - i * 0.02
        noise = 0.08 if i % 2 else -0.08
        signal = noise
        if abs(ppm - 7.2) < 0.02:
            signal += 5.0
        points.append((ppm, signal))

    result = weak_peak_magnifier_view(points, visual_gain=80)

    assert len(result.points) == len(points)
    assert result.points != points
    assert result.metadata["display_only"] is True
    assert result.metadata["evidence_trace_preserved"] is True
    assert result.metadata["method"] == "weak_peak_magnifier_log_relative_inset"


def test_processed_spectrum_defaults_to_real_display_metadata() -> None:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ppm", "intensity"])
    for i in range(300):
        ppm = 6.0 - i * 0.02
        baseline = i * 0.005
        signal = baseline
        if abs(ppm - 3.0) < 0.03:
            signal += 25
        if abs(ppm - 1.2) < 0.03:
            signal += 2
        writer.writerow([ppm, signal])

    preview = parse_processed_spectrum(
        filename="test_1h.csv",
        content=out.getvalue().encode(),
        solvent="CDCl3",
    )

    assert "mnova_view" not in preview.metadata
    assert preview.metadata["display_mode"] == "real"
    assert preview.metadata["display_gain"] == 1.0
    assert preview.metadata["baseline_lock_visual_only"] is True
    assert "raw_preview_points" not in preview.metadata
    assert preview.preview_points
