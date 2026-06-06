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


def _baseline_fit_span(points: list[tuple[float, float]]) -> dict[str, float | int]:
    baseline = estimate_baseline_points(points)
    if len(baseline) < 3:
        return {"span": 0.0, "slope": 0.0, "intercept": 0.0, "baseline_points": len(baseline)}
    try:
        import numpy as np

        xs = np.asarray([x for x, _y in baseline], dtype=float)
        ys = np.asarray([y for _x, y in baseline], dtype=float)
        slope, intercept = np.polyfit(xs, ys, 1)
        span = abs(float(slope)) * max(float(xs.max() - xs.min()), 0.0)
        return {
            "span": span,
            "slope": float(slope),
            "intercept": float(intercept),
            "baseline_points": int(xs.size),
        }
    except Exception:
        xs = [x for x, _y in baseline]
        ys = [y for _x, y in baseline]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        denom = sum((x - x_mean) ** 2 for x in xs) or 1e-12
        slope = sum((x - x_mean) * (y - y_mean) for x, y in baseline) / denom
        intercept = y_mean - slope * x_mean
        return {
            "span": abs(float(slope)) * max(max(xs) - min(xs), 0.0),
            "slope": float(slope),
            "intercept": float(intercept),
            "baseline_points": len(baseline),
        }


def _rolling_signal_free_baseline(values: Any) -> tuple[Any, dict[str, Any]]:
    import numpy as np

    y = np.asarray(values, dtype=float).reshape(-1)
    n = int(y.size)
    if n == 0:
        return y, {"method": "rolling_signal_free_smoother", "baseline_nodes": 0}
    finite = np.isfinite(y)
    if not np.any(finite):
        return np.zeros_like(y), {"method": "rolling_signal_free_smoother", "baseline_nodes": 0}

    bins = max(24, min(240, int(math.sqrt(n) * 3)))
    node_x: list[float] = []
    node_y: list[float] = []
    for idx in range(bins):
        low = int(round(idx * n / bins))
        high = int(round((idx + 1) * n / bins))
        segment = y[low:high]
        segment = segment[np.isfinite(segment)]
        if segment.size == 0:
            continue
        node_x.append((low + max(high - low, 1) / 2.0) / max(n - 1, 1))
        node_y.append(float(np.percentile(segment, 18.0)))
    if len(node_x) < 2:
        return np.full_like(y, float(np.nanmedian(y[finite]))), {
            "method": "rolling_signal_free_smoother",
            "baseline_nodes": len(node_x),
        }

    grid = np.linspace(0.0, 1.0, n)
    baseline = np.interp(grid, np.asarray(node_x, dtype=float), np.asarray(node_y, dtype=float))
    kernel_width = max(9, min(n // 3 if n >= 3 else n, int(round(n * 0.035)) | 1))
    if kernel_width >= 3:
        half = kernel_width // 2
        ramp = np.arange(1, half + 2, dtype=float)
        kernel = np.concatenate([ramp, ramp[-2::-1]])
        kernel = kernel / float(kernel.sum())
        padded = np.pad(baseline, (half, half), mode="edge")
        baseline = np.convolve(padded, kernel, mode="valid")
    return baseline, {
        "method": "rolling_signal_free_smoother",
        "baseline_nodes": len(node_x),
        "kernel_width": int(kernel_width),
    }


def _whittaker_signal_free_baseline(
    values: Any,
    *,
    smoothness: float,
    asymmetry: float,
    max_iter: int,
) -> tuple[Any, dict[str, Any]]:
    import numpy as np

    try:
        from scipy import sparse
        from scipy.sparse.linalg import spsolve
    except Exception:
        return _rolling_signal_free_baseline(values)

    y = np.asarray(values, dtype=float).reshape(-1)
    n = int(y.size)
    if n < 4:
        baseline = np.full_like(y, float(np.nanmedian(y)) if y.size else 0.0)
        return baseline, {
            "method": "constant_signal_free_baseline",
            "baseline_nodes": n,
        }

    finite = np.isfinite(y)
    if not np.any(finite):
        return np.zeros_like(y), {
            "method": "whittaker_asymmetric_smoother",
            "iterations": 0,
            "signal_free_fraction": 0.0,
        }

    work = y.copy()
    fill_value = float(np.nanmedian(work[finite]))
    work[~finite] = fill_value
    weights = np.ones(n, dtype=float)
    diff = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(n - 2, n), format="csc")
    penalty = float(smoothness) * (diff.T @ diff)
    p = max(0.001, min(0.2, float(asymmetry)))
    baseline = np.full(n, fill_value, dtype=float)
    iterations = max(1, min(25, int(max_iter)))
    for _idx in range(iterations):
        system = sparse.spdiags(weights, 0, n, n, format="csc") + penalty
        baseline = np.asarray(spsolve(system, weights * work), dtype=float)
        weights = np.where(work > baseline, p, 1.0 - p)
        weights[~finite] = 0.0
    signal_free_fraction = float(np.mean(weights > 0.5)) if weights.size else 0.0
    return baseline, {
        "method": "whittaker_asymmetric_smoother",
        "iterations": iterations,
        "smoothness": float(smoothness),
        "asymmetry": p,
        "signal_free_fraction": round(signal_free_fraction, 4),
    }


def apply_signal_free_smooth_baseline_polish(
    points: list[tuple[float, float]],
    *,
    smoothness: float | None = None,
    asymmetry: float = 0.01,
    max_iter: int = 10,
) -> tuple[list[tuple[float, float]], dict[str, Any], list[str]]:
    """Remove residual rolling baseline using signal-free regions and smoothing.

    This is a post-polish for already transformed FID spectra. It mirrors the
    industry-standard sequence of phase correction, Bernstein baseline
    correction, and signal-free smoother cleanup for broad rolling baseline
    topographies.
    """

    warnings: list[str] = []
    clean = [
        (float(x), float(y))
        for x, y in points
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    before_qa = evaluate_baseline_flatness(clean, mode="signal_free_smoother").as_dict()
    before_span = _baseline_fit_span(clean)
    metadata: dict[str, Any] = {
        "method": "signal_free_smooth_baseline_polish",
        "correction_applied": False,
        "baseline_locked_to_zero": True,
        "qa_before": before_qa,
        "residual_span_before": before_span,
    }
    if len(clean) < 32:
        warnings.append("Too few points were available for signal-free baseline polishing.")
        metadata["qa_after"] = before_qa
        metadata["residual_span_after"] = before_span
        return (clean, metadata, warnings)

    try:
        import numpy as np

        y = np.asarray([value for _x, value in clean], dtype=float)
        n = int(y.size)
        scale = float(np.nanpercentile(np.abs(y), 99.5)) if y.size else 0.0
        if scale <= 1e-12:
            metadata["qa_after"] = before_qa
            metadata["residual_span_after"] = before_span
            return (clean, metadata, warnings)

        lambda_value = float(smoothness) if smoothness is not None else 2.5e6 * (n / 1200.0) ** 2
        lambda_value = max(5.0e4, min(2.5e9, lambda_value))
        baseline, smoother_meta = _whittaker_signal_free_baseline(
            y,
            smoothness=lambda_value,
            asymmetry=asymmetry,
            max_iter=max_iter,
        )
        corrected_y = y - np.asarray(baseline, dtype=float)
        finite = np.isfinite(corrected_y)
        if np.any(finite):
            centered = corrected_y[finite] - float(np.nanmedian(corrected_y[finite]))
            abs_centered = np.abs(centered)
            noise = 1.4826 * float(np.nanmedian(np.abs(centered - float(np.nanmedian(centered)))))
            threshold = max(noise * 3.5, float(np.nanpercentile(abs_centered, 35.0)), 1e-12)
            corrected_center = float(np.nanmedian(corrected_y[finite]))
            signal_free = finite & (np.abs(corrected_y - corrected_center) <= threshold)
            if int(np.count_nonzero(signal_free)) >= 3:
                offset = float(np.nanmedian(corrected_y[signal_free]))
                corrected_y = corrected_y - offset
            else:
                offset = float(np.nanmedian(corrected_y[finite]))
                corrected_y = corrected_y - offset
        else:
            offset = 0.0

        corrected = [(x, float(value)) for (x, _y), value in zip(clean, corrected_y, strict=False)]
        after_qa = evaluate_baseline_flatness(corrected, mode="signal_free_smoother").as_dict()
        after_span = _baseline_fit_span(corrected)
        before_score = float(before_qa.get("score") or 0.0)
        after_score = float(after_qa.get("score") or 0.0)
        before_span_value = float(before_span.get("span") or 0.0)
        after_span_value = float(after_span.get("span") or 0.0)
        span_improved = before_span_value <= 1e-12 or after_span_value <= before_span_value * 1.05
        if after_score + 1e-9 < before_score and not span_improved:
            warnings.append(
                "Signal-free baseline polish was skipped because flatness QA did not improve."
            )
            metadata.update(
                {
                    **smoother_meta,
                    "qa_after": before_qa,
                    "residual_span_after": before_span,
                    "skipped_reason": "flatness_not_improved",
                }
            )
            return (clean, metadata, warnings)

        metadata.update(
            {
                **smoother_meta,
                "correction_applied": True,
                "baseline_residual_offset": round(float(offset), 10),
                "qa_after": after_qa,
                "residual_span_after": after_span,
                "baseline_slope": round(float(after_span.get("slope") or 0.0), 10),
                "baseline_span": round(float(after_span.get("span") or 0.0), 10),
            }
        )
        return (corrected, metadata, warnings)
    except Exception as exc:
        warnings.append(
            f"Signal-free baseline polish failed; Bernstein result was preserved ({exc})."
        )
        metadata["qa_after"] = before_qa
        metadata["residual_span_after"] = before_span
        return (clean, metadata, warnings)


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
