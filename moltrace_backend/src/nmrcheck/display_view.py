from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Any

from .baseline import evaluate_baseline_flatness


@dataclass(frozen=True)
class DisplayViewResult:
    points: list[tuple[float, float]]
    metadata: dict[str, Any]
    warnings: list[str]


def _clean_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return [
        (float(x), float(y))
        for x, y in points
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]


def _noise_estimate(values: list[float]) -> float:
    if not values:
        return 0.0
    center = median(values)
    return max(0.0, float(median(abs(value - center) for value in values)) * 1.4826)


def weak_peak_magnifier_view(
    points: list[tuple[float, float]],
    *,
    visual_gain: float = 12.0,
) -> DisplayViewResult:
    """Build an optional display-only weak-peak inset trace.

    This helper intentionally does not replace the evidence trace. It only emits
    a separate relative-intensity view that the UI can render as an inset when a
    reviewer asks for weak-peak help.
    """

    clean = _clean_points(points)
    if not clean:
        return DisplayViewResult(
            points=[],
            metadata={
                "enabled": False,
                "display_only": True,
                "method": "weak_peak_magnifier",
            },
            warnings=[],
        )

    values = [y for _, y in clean]
    baseline = float(median(values))
    centered = [y - baseline for y in values]
    max_abs = max(abs(value) for value in centered) or 1.0
    gain = max(1.0, min(float(visual_gain or 12.0), 1_000_000.0))
    denom = math.log1p(gain)
    display = [
        (
            x,
            math.copysign(math.log1p(gain * min(1.0, abs(delta) / max_abs)) / denom, delta),
        )
        for (x, _), delta in zip(clean, centered, strict=False)
    ]
    qa = evaluate_baseline_flatness(clean, mode="evidence").as_dict()
    return DisplayViewResult(
        points=display,
        metadata={
            "enabled": True,
            "display_only": True,
            "method": "weak_peak_magnifier_log_relative_inset",
            "evidence_trace_preserved": True,
            "baseline_source": "median_for_relative_inset_only",
            "baseline": round(baseline, 8),
            "visual_gain": gain,
            "noise_estimate": _noise_estimate(centered),
            "baseline_qa": qa,
        },
        warnings=[],
    )


def make_locked_display_view(
    points: list[tuple[float, float]],
    *,
    enabled: bool = False,
    baseline_lock: bool = True,
    visual_gain: float = 1.0,
) -> DisplayViewResult:
    """Compatibility wrapper for the retired locked-display intensity transform.

    The previous implementation subtracted a fitted baseline and asinh-scaled
    intensities. That made spectra look warped and made peak-height controls
    feel like they were changing the data. The default professional viewer now
    preserves evidence intensities; callers that need weak-peak assistance should
    render ``weak_peak_magnifier_view`` as a separate inset.
    """

    clean = _clean_points(points)
    qa = evaluate_baseline_flatness(clean, mode="evidence").as_dict() if clean else {}
    return DisplayViewResult(
        points=clean,
        metadata={
            "enabled": False,
            "requested": bool(enabled),
            "legacy_transform_disabled": True,
            "baseline_lock": bool(baseline_lock),
            "visual_gain": max(1.0, float(visual_gain or 1.0)),
            "evidence_trace_preserved": True,
            "baseline_qa": qa,
            "note": (
                "Legacy fitted-baseline/asinh display transform is disabled; "
                "the main spectrum uses real evidence intensities."
            ),
        },
        warnings=(
            [
                "Legacy locked-display intensity transform was requested but is "
                "disabled; the real spectrum was preserved."
            ]
            if enabled
            else []
        ),
    )
