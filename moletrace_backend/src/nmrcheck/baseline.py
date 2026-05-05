from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Any


@dataclass(frozen=True)
class BaselineQA:
    mode: str
    score: float
    label: str
    slope: float
    curvature_proxy: float
    offset_ratio: float
    noise_estimate: float
    baseline_points: int
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "score": self.score,
            "label": self.label,
            "slope": self.slope,
            "curvature_proxy": self.curvature_proxy,
            "offset_ratio": self.offset_ratio,
            "noise_estimate": self.noise_estimate,
            "baseline_points": self.baseline_points,
            "warnings": self.warnings,
        }


STRICT_BASELINE_MODES = {"preserve", "strict", "locked", "no_correction", "off"}


def normalize_baseline_mode(mode: str | None) -> str:
    value = (mode or "bernstein").strip().lower().replace("-", "_").replace(" ", "_")
    if value in STRICT_BASELINE_MODES:
        return "preserve"
    if value in {"bernstein", "bernstein_polynomial", "polynomial"}:
        return "bernstein"
    if value in {"flat", "linear", "median", "percentile", "none"}:
        return value
    return "bernstein"


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    pos = min(max(q, 0.0), 1.0) * (len(vals) - 1)
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return vals[low]
    frac = pos - low
    return vals[low] * (1 - frac) + vals[high] * frac


def bernstein_basis(order: int, t: float) -> list[float]:
    """Return Bernstein basis values B(k,n)(t) for k=0..n."""

    n = max(0, int(order))
    t_value = max(0.0, min(1.0, float(t)))
    return [
        math.comb(n, k) * (t_value**k) * ((1.0 - t_value) ** (n - k))
        for k in range(n + 1)
    ]


def _normalize_axis_to_unit(points: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
    xs = [x for x, _ in points]
    lo = min(xs)
    hi = max(xs)
    span = hi - lo
    if abs(span) <= 1e-15:
        return [(0.0, x, y) for x, y in points]
    return [((x - lo) / span, x, y) for x, y in points]


def _mad(values: list[float]) -> float:
    if not values:
        return 0.0
    center = median(values)
    return median([abs(value - center) for value in values])


def _fit_bernstein_coefficients(
    baseline_points: list[tuple[float, float]],
    *,
    order: int,
) -> list[float] | None:
    if len(baseline_points) < order + 1:
        return None
    try:
        import numpy as np

        matrix = np.asarray([bernstein_basis(order, t) for t, _ in baseline_points], dtype=float)
        vector = np.asarray([y for _, y in baseline_points], dtype=float)
        coeffs, *_ = np.linalg.lstsq(matrix, vector, rcond=None)
        return [float(value) for value in coeffs]
    except Exception:
        return None


def _evaluate_bernstein(coefficients: list[float], t: float) -> float:
    basis = bernstein_basis(len(coefficients) - 1, t)
    return float(sum(coef * value for coef, value in zip(coefficients, basis, strict=False)))


def _select_bernstein_baseline_points(
    normalized: list[tuple[float, float, float]],
    *,
    order: int,
    quantile: float,
) -> list[tuple[float, float]]:
    if not normalized:
        return []
    ordered = sorted(normalized, key=lambda item: item[0])
    bins = max(12, min(80, int(math.sqrt(len(ordered))) or 12, (order + 1) * 8))
    selected: list[tuple[float, float]] = []
    for idx in range(bins):
        low = idx / bins
        high = (idx + 1) / bins
        bucket = [
            (t, y)
            for t, _x, y in ordered
            if (low <= t < high) or (idx == bins - 1 and math.isclose(t, 1.0))
        ]
        if not bucket:
            continue
        cutoff = _quantile([y for _, y in bucket], quantile)
        selected.extend((t, y) for t, y in bucket if y <= cutoff)

    minimum = max(order + 1, 8)
    if len(selected) >= minimum:
        return selected

    values = [y for _t, _x, y in ordered]
    cutoff = _quantile(values, min(max(quantile, 0.05), 0.5))
    fallback = [(t, y) for t, _x, y in ordered if y <= cutoff]
    return fallback if len(fallback) >= minimum else []


def apply_bernstein_baseline_correction(
    points: list[tuple[float, float]],
    *,
    order: int = 3,
    quantile: float = 0.25,
    max_iter: int = 3,
) -> tuple[list[tuple[float, float]], dict[str, Any], list[str]]:
    """Subtract a conservative Bernstein-polynomial baseline from NMR points.

    The fit uses low-envelope candidate points and iterative positive-residual
    clipping so obvious absorption peaks do not pull the baseline upward.
    """

    warnings: list[str] = []
    clean = [
        (float(x), float(y))
        for x, y in points
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    normalized_order = max(1, min(8, int(order or 3)))
    metadata: dict[str, Any] = {
        "mode": "bernstein_polynomial",
        "method": "bernstein_polynomial",
        "order": normalized_order,
        "baseline_locked_to_zero": True,
        "correction_applied": False,
        "baseline_points": 0,
        "coefficients": [],
    }
    if len(clean) < max(normalized_order + 1, 8):
        warnings.append("Too few points were available for Bernstein baseline correction.")
        metadata["qa"] = evaluate_baseline_flatness(clean, mode="bernstein").as_dict()
        return (clean, metadata, warnings)

    normalized = _normalize_axis_to_unit(clean)
    baseline_points = _select_bernstein_baseline_points(
        normalized,
        order=normalized_order,
        quantile=max(0.05, min(0.45, float(quantile))),
    )
    if len(baseline_points) < normalized_order + 1:
        warnings.append("Too few baseline-like points were available for Bernstein fitting.")
        metadata["baseline_points"] = len(baseline_points)
        metadata["qa"] = evaluate_baseline_flatness(clean, mode="bernstein").as_dict()
        return (clean, metadata, warnings)

    coefficients = _fit_bernstein_coefficients(baseline_points, order=normalized_order)
    if coefficients is None:
        warnings.append("Bernstein baseline least-squares fit failed; spectrum was preserved.")
        metadata["baseline_points"] = len(baseline_points)
        metadata["qa"] = evaluate_baseline_flatness(clean, mode="bernstein").as_dict()
        return (clean, metadata, warnings)

    candidates = baseline_points
    for _ in range(max(0, int(max_iter))):
        residuals = [
            y - _evaluate_bernstein(coefficients, t)
            for t, y in candidates
        ]
        if len(residuals) < normalized_order + 1:
            break
        center = median(residuals)
        sigma = 1.4826 * _mad(residuals)
        if sigma <= 1e-12:
            break
        next_candidates = [
            (t, y)
            for (t, y), residual in zip(candidates, residuals, strict=False)
            if residual <= center + 2.5 * sigma
        ]
        if len(next_candidates) < normalized_order + 1 or len(next_candidates) == len(candidates):
            break
        next_coefficients = _fit_bernstein_coefficients(
            next_candidates,
            order=normalized_order,
        )
        if next_coefficients is None:
            break
        candidates = next_candidates
        coefficients = next_coefficients

    residual_offset = 0.0
    corrected = [
        (x, y - _evaluate_bernstein(coefficients, t))
        for t, x, y in normalized
    ]
    if candidates:
        candidate_by_t = {round(t, 12) for t, _y in candidates}
        baseline_residuals = [
            y
            for t, (x, y) in zip([item[0] for item in normalized], corrected, strict=False)
            if round(t, 12) in candidate_by_t
        ]
        if baseline_residuals:
            residual_offset = float(median(baseline_residuals))
            corrected = [(x, y - residual_offset) for x, y in corrected]

    qa = evaluate_baseline_flatness(corrected, mode="bernstein").as_dict()
    metadata.update(
        {
            "correction_applied": True,
            "baseline_points": len(candidates),
            "coefficients": [round(float(value), 10) for value in coefficients],
            "quantile": max(0.05, min(0.45, float(quantile))),
            "max_iter": max(0, int(max_iter)),
            "baseline_residual_offset": residual_offset,
            "qa": qa,
            "flatness_qa": qa,
            "baseline_model": "bernstein_polynomial",
        }
    )
    return (corrected, metadata, warnings)


def fit_bernstein_baseline(
    points: list[tuple[float, float]],
    *,
    order: int = 3,
    mask_peaks: bool = True,
    quantile: float = 0.25,
    max_iter: int = 3,
) -> tuple[list[tuple[float, float]], dict[str, Any], list[str]]:
    """Fit and return the Bernstein baseline model without replacing the trace."""

    effective_quantile = quantile if mask_peaks else 1.0
    _corrected, metadata, warnings = apply_bernstein_baseline_correction(
        points,
        order=order,
        quantile=effective_quantile,
        max_iter=max_iter,
    )
    coefficients = [float(value) for value in metadata.get("coefficients", [])]
    clean = [
        (float(x), float(y))
        for x, y in points
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    if not coefficients or not clean:
        return ([], metadata, warnings)
    model_points = [
        (x, _evaluate_bernstein(coefficients, t) + float(metadata.get("baseline_residual_offset") or 0.0))
        for t, x, _y in _normalize_axis_to_unit(clean)
    ]
    return (model_points, {**metadata, "baseline_model_points": len(model_points)}, warnings)


def apply_bernstein_baseline(
    points: list[tuple[float, float]],
    *,
    order: int = 3,
) -> tuple[list[tuple[float, float]], dict[str, Any], list[str]]:
    return apply_bernstein_baseline_correction(points, order=order)


def apply_simple_baseline_correction(
    points: list[tuple[float, float]],
    *,
    mode: str,
) -> tuple[list[tuple[float, float]], dict[str, Any], list[str]]:
    normalized_mode = normalize_baseline_mode(mode)
    clean = [
        (float(x), float(y))
        for x, y in points
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    if normalized_mode in {"none", "preserve"}:
        qa = evaluate_baseline_flatness(clean, mode=normalized_mode).as_dict()
        return (
            clean,
            {
                "mode": normalized_mode,
                "method": normalized_mode,
                "correction_applied": False,
                "baseline_locked_to_zero": False,
                "qa": qa,
                "flatness_qa": qa,
            },
            [],
        )
    if not clean:
        return (
            clean,
            {
                "mode": normalized_mode,
                "method": normalized_mode,
                "correction_applied": False,
                "baseline_locked_to_zero": False,
                "qa": evaluate_baseline_flatness(clean, mode=normalized_mode).as_dict(),
            },
            ["No points were available for baseline correction."],
        )
    values = [y for _, y in clean]
    if normalized_mode == "percentile":
        baseline = _quantile(values, 0.05)
    elif normalized_mode in {"median", "flat", "linear"}:
        baseline = median(values)
    else:
        return apply_bernstein_baseline_correction(clean)
    corrected = [(x, y - baseline) for x, y in clean]
    qa = evaluate_baseline_flatness(corrected, mode=normalized_mode).as_dict()
    return (
        corrected,
        {
            "mode": normalized_mode,
            "method": normalized_mode,
            "baseline_model": "constant",
            "baseline_offset": float(baseline),
            "correction_applied": True,
            "baseline_locked_to_zero": True,
            "qa": qa,
            "flatness_qa": qa,
        },
        [],
    )


def apply_simple_baseline_mode(
    points: list[tuple[float, float]],
    *,
    mode: str,
) -> tuple[list[tuple[float, float]], dict[str, Any], list[str]]:
    return apply_simple_baseline_correction(points, mode=mode)


def estimate_baseline_points(
    points: list[tuple[float, float]],
    *,
    fraction: float = 0.25,
) -> list[tuple[float, float]]:
    clean = [
        (float(x), float(y))
        for x, y in points
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    if not clean:
        return []
    cutoff = _quantile([abs(y) for _, y in clean], fraction)
    baseline = [(x, y) for x, y in clean if abs(y) <= cutoff]
    return baseline or clean[: max(1, min(len(clean), 25))]


def evaluate_baseline_flatness(
    points: list[tuple[float, float]],
    *,
    mode: str = "flat",
) -> BaselineQA:
    baseline = estimate_baseline_points(points)
    if len(baseline) < 5:
        return BaselineQA(
            mode=normalize_baseline_mode(mode),
            score=0.0,
            label="insufficient_data",
            slope=0.0,
            curvature_proxy=0.0,
            offset_ratio=0.0,
            noise_estimate=0.0,
            baseline_points=len(baseline),
            warnings=["Too few baseline-like points were available for flatness QA."],
        )

    xs = [x for x, _ in baseline]
    ys = [y for _, y in baseline]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denom = sum((x - x_mean) ** 2 for x in xs) or 1e-12
    slope = sum((x - x_mean) * (y - y_mean) for x, y in baseline) / denom
    intercept = y_mean - slope * x_mean
    residuals = [y - (slope * x + intercept) for x, y in baseline]
    abs_residuals = [abs(value) for value in residuals]
    noise = median(abs_residuals) or (
        sum(abs_residuals) / len(abs_residuals) if abs_residuals else 0.0
    ) or 1e-12

    ordered = sorted(baseline, key=lambda item: item[0])
    mid = len(ordered) // 2
    left_y = [y for _, y in ordered[:mid]]
    right_y = [y for _, y in ordered[mid:]]
    curvature_proxy = abs(
        (median(left_y) if left_y else 0.0) - (median(right_y) if right_y else 0.0)
    ) / max(noise, 1e-12)
    dynamic = max(abs(y) for _, y in points) if points else 1.0
    slope_ratio = abs(slope) * abs(max(xs) - min(xs)) / max(dynamic, 1e-12)
    offset_ratio = abs(y_mean) / max(dynamic, 1e-12)

    score = 100.0
    warnings: list[str] = []
    if slope_ratio > 0.08:
        score -= 25
        warnings.append("Baseline-like points show noticeable slope across the spectrum.")
    elif slope_ratio > 0.03:
        score -= 10
        warnings.append("Baseline-like points show mild slope.")

    if curvature_proxy > 4.0:
        score -= 25
        warnings.append("Baseline-like points show curvature or different offsets across the spectrum.")
    elif curvature_proxy > 2.0:
        score -= 10
        warnings.append("Baseline-like points show mild curvature.")

    if offset_ratio > 0.08:
        score -= 15
        warnings.append("Baseline offset is high relative to maximum signal.")
    elif offset_ratio > 0.03:
        score -= 6
        warnings.append("Baseline offset is mildly elevated.")

    score = max(0.0, min(100.0, score))
    label = "flat" if score >= 85 else ("review" if score >= 65 else "distorted")
    return BaselineQA(
        mode=normalize_baseline_mode(mode),
        score=round(score, 1),
        label=label,
        slope=float(slope),
        curvature_proxy=round(float(curvature_proxy), 3),
        offset_ratio=round(float(offset_ratio), 4),
        noise_estimate=float(noise),
        baseline_points=len(baseline),
        warnings=warnings,
    )
