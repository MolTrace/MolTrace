from __future__ import annotations

import hashlib
import math
from dataclasses import replace
from math import comb
from typing import Any

import numpy as np

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum

PhaseRegion = tuple[float, float]

_EPS = 1e-12
_MAX_PHASE_SCORE_POINTS = 12_000


def auto_phase_correct(
    spectrum: NMRSpectrum,
    method: str = "regions_analysis",
    blind_regions: list[PhaseRegion] | None = None,
) -> NMRSpectrum:
    """Apply automatic phase correction to an NMR spectrum.

    Methods:
      - ``regions_analysis``: identify signal and signal-free regions, then fit a
        stable zero-order phase. The metadata keeps the region fractions so a
        future first-order fit can be layered in without changing this API.
      - ``whitening``: entropy-like minimization with a negative-lobe penalty.
      - ``magnitude``: return the magnitude trace for phase-insensitive spectra
        such as 2D HMBC projections.

    ``blind_regions`` excludes ppm ranges from phase scoring, for example
    residual water or a very large solvent resonance.
    """

    normalized = _normalize_method(method) or "regions_analysis"
    if normalized not in {"regions_analysis", "whitening", "magnitude"}:
        raise ValueError(
            "Unsupported phase correction method. Expected one of: "
            "regions_analysis, whitening, magnitude."
        )
    data = np.asarray(spectrum.data)
    if data.size == 0:
        return _copy_spectrum(
            spectrum,
            data=data.copy(),
            step="phase",
            metadata={
                "method": normalized,
                "applied_phase_deg": 0.0,
                "phase_correction_applied": False,
                "warnings": ["Empty spectrum was preserved."],
            },
        )

    complex_data = data.astype(np.complex128, copy=False)
    axis = _coerce_axis(spectrum.ppm_axis, complex_data.size)
    unblinded = _unblinded_mask(axis, blind_regions)
    if normalized == "magnitude":
        magnitude = np.abs(complex_data).astype(np.float64, copy=False)
        return _copy_spectrum(
            spectrum,
            data=magnitude,
            step="phase",
            metadata={
                "method": "magnitude",
                "applied_phase_deg": 0.0,
                "zero_order_degrees": 0.0,
                "phase_correction_applied": False,
                "blind_regions": _json_blind_regions(blind_regions),
            },
        )

    if not np.iscomplexobj(data):
        return _copy_spectrum(
            spectrum,
            data=np.asarray(data, dtype=np.float64).copy(),
            step="phase",
            metadata={
                "method": normalized,
                "applied_phase_deg": 0.0,
                "zero_order_degrees": 0.0,
                "phase_correction_applied": False,
                "blind_regions": _json_blind_regions(blind_regions),
                "warnings": ["Input spectrum is real-only; phase correction was not required."],
            },
        )

    score_data, score_axis, score_unblinded = _downsample_for_phase(
        complex_data,
        axis,
        unblinded,
    )
    signal_mask, signal_free_mask = _phase_masks(score_data, score_unblinded)
    if normalized == "regions_analysis":
        applied_phase, score = _regions_analysis_phase(
            score_data,
            signal_mask=signal_mask,
            signal_free_mask=signal_free_mask,
        )
    elif normalized == "whitening":
        applied_phase, score = _whitening_phase(
            score_data,
            active_mask=score_unblinded,
        )

    phased = _apply_zero_order_phase(complex_data, applied_phase)
    metadata = {
        "method": normalized,
        "applied_phase_deg": round(float(applied_phase), 4),
        "zero_order_degrees": round(float(applied_phase), 4),
        "first_order_degrees": 0.0,
        "phase_score": round(float(score), 8),
        "phase_correction_applied": not math.isclose(float(applied_phase), 0.0, abs_tol=1e-6),
        "blind_regions": _json_blind_regions(blind_regions),
        "signal_fraction": round(float(np.mean(signal_mask)), 5) if signal_mask.size else 0.0,
        "signal_free_fraction": round(float(np.mean(signal_free_mask)), 5)
        if signal_free_mask.size
        else 0.0,
        "score_points": int(score_axis.size),
    }
    return _copy_spectrum(spectrum, data=phased, step="phase", metadata=metadata)


def baseline_correct(
    spectrum: NMRSpectrum,
    method: str = "bernstein",
    order: int = 3,
) -> NMRSpectrum:
    """Apply baseline correction to an NMR spectrum.

    Methods:
      - ``bernstein``: robust low-envelope Bernstein polynomial, default for 1H.
      - ``whittaker``: asymmetric least-squares smoother, useful for 13C.
      - ``polynomial``: robust polynomial fit.
      - ``spline``: cubic spline through signal-free baseline nodes when SciPy is
        available, otherwise deterministic linear interpolation through nodes.
    """

    normalized = _normalize_method(method) or "bernstein"
    if normalized not in {"bernstein", "whittaker", "polynomial", "spline"}:
        raise ValueError(
            "Unsupported baseline correction method. Expected one of: "
            "bernstein, whittaker, polynomial, spline."
        )

    raw = np.asarray(spectrum.data)
    if raw.size == 0:
        return _copy_spectrum(
            spectrum,
            data=raw.copy(),
            step="baseline",
            metadata={
                "method": normalized,
                "order": int(order),
                "correction_applied": False,
                "warnings": ["Empty spectrum was preserved."],
            },
        )

    real = np.real(raw).astype(np.float64, copy=False)
    axis = _coerce_axis(spectrum.ppm_axis, real.size)
    finite = np.isfinite(real)
    fill = float(np.nanmedian(real[finite])) if np.any(finite) else 0.0
    work = real.copy()
    work[~finite] = fill
    effective_order = max(1, min(8, int(order or 3)))

    if normalized == "bernstein":
        baseline, fit_meta = _bernstein_baseline(axis, work, order=effective_order)
    elif normalized == "polynomial":
        baseline, fit_meta = _polynomial_baseline(axis, work, order=effective_order)
    elif normalized == "spline":
        baseline, fit_meta = _spline_baseline(axis, work, order=effective_order)
    else:
        baseline, fit_meta = _whittaker_baseline(work)

    corrected_real = real - baseline
    signal_free = _baseline_mask(corrected_real)
    if np.count_nonzero(signal_free) >= max(8, effective_order + 1):
        corrected_real = corrected_real - float(np.nanmedian(corrected_real[signal_free]))
    if np.iscomplexobj(raw):
        corrected = corrected_real.astype(np.float64) + 1j * np.imag(raw).astype(np.float64)
    else:
        corrected = corrected_real.astype(np.float64)

    full_scale = _full_scale(real)
    residual = corrected_real[_baseline_mask(corrected_real)]
    baseline_rmse = float(np.sqrt(np.nanmean(np.square(residual)))) if residual.size else 0.0
    metadata = {
        "method": normalized,
        "order": effective_order,
        "correction_applied": True,
        "baseline_rmse": baseline_rmse,
        "baseline_rmse_fraction_full_scale": baseline_rmse / max(full_scale, _EPS),
        "full_scale_intensity": full_scale,
        **fit_meta,
    }
    return _copy_spectrum(spectrum, data=corrected, step="baseline", metadata=metadata)


def _regions_analysis_phase(
    data: np.ndarray,
    *,
    signal_mask: np.ndarray,
    signal_free_mask: np.ndarray,
) -> tuple[float, float]:
    active = signal_mask if np.count_nonzero(signal_mask) >= 8 else np.ones(data.size, dtype=bool)
    analytic = _analytic_absorption_phase(data[active])
    candidates = _candidate_phases(analytic, span=32.0, step=0.25)
    best_phase = analytic
    best_score = -float("inf")
    for phase in candidates:
        rotated = _apply_zero_order_phase(data, phase)
        score = _absorption_score(
            rotated,
            signal_mask=active,
            signal_free_mask=signal_free_mask,
            entropy_weight=0.05,
        )
        if score > best_score:
            best_phase = float(phase)
            best_score = float(score)
    return _wrap_degrees(best_phase), best_score


def _whitening_phase(data: np.ndarray, *, active_mask: np.ndarray) -> tuple[float, float]:
    active = active_mask if np.count_nonzero(active_mask) >= 8 else np.ones(data.size, dtype=bool)
    analytic = _analytic_absorption_phase(data[active])
    coarse = np.linspace(analytic - 90.0, analytic + 90.0, 181)
    best_phase = analytic
    best_score = -float("inf")
    for phase in coarse:
        rotated = _apply_zero_order_phase(data, phase)
        score = _whitening_score(np.real(rotated[active]))
        if score > best_score:
            best_phase = float(phase)
            best_score = float(score)
    for phase in _candidate_phases(best_phase, span=6.0, step=0.1):
        rotated = _apply_zero_order_phase(data, phase)
        score = _whitening_score(np.real(rotated[active]))
        if score > best_score:
            best_phase = float(phase)
            best_score = float(score)
    return _wrap_degrees(best_phase), best_score


def _analytic_absorption_phase(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    weights = np.abs(values)
    if not np.any(weights > 0):
        return 0.0
    vector = np.sum(values * weights)
    if abs(vector) <= _EPS:
        vector = values[int(np.argmax(weights))]
    return _wrap_degrees(-math.degrees(math.atan2(float(np.imag(vector)), float(np.real(vector)))))


def _absorption_score(
    data: np.ndarray,
    *,
    signal_mask: np.ndarray,
    signal_free_mask: np.ndarray,
    entropy_weight: float,
) -> float:
    real = np.real(data)
    imag = np.imag(data)
    active_real = real[signal_mask]
    active_imag = imag[signal_mask]
    if active_real.size == 0:
        return -float("inf")
    scale = max(float(np.percentile(np.abs(active_real), 99.0)), _EPS)
    positive = float(np.sum(np.maximum(active_real, 0.0)))
    negative = float(np.sum(np.abs(np.minimum(active_real, 0.0))))
    imag_penalty = float(np.sqrt(np.mean(np.square(active_imag)))) / scale
    free_bias = 0.0
    if np.count_nonzero(signal_free_mask) >= 8:
        free = real[signal_free_mask]
        free_bias = abs(float(np.median(free))) / scale
    entropy = _trace_entropy(np.maximum(active_real, 0.0))
    return (
        positive
        - 4.0 * negative
        - positive * imag_penalty
        - positive * free_bias
        - entropy_weight * entropy
    )


def _whitening_score(real: np.ndarray) -> float:
    finite = real[np.isfinite(real)]
    if finite.size == 0:
        return -float("inf")
    scale = max(float(np.percentile(np.abs(finite), 99.0)), _EPS)
    negative = float(np.sum(np.abs(np.minimum(finite, 0.0)))) / scale
    entropy = _trace_entropy(np.maximum(finite, 0.0))
    whiteness = (
        float(np.percentile(np.abs(np.diff(finite)), 50.0)) / scale
        if finite.size > 1
        else 0.0
    )
    peak_focus = float(np.percentile(finite, 99.5)) / scale
    return peak_focus - entropy - 5.0 * negative - 0.2 * whiteness


def _trace_entropy(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    total = float(np.sum(arr))
    if arr.size == 0 or total <= _EPS:
        return 0.0
    prob = arr / total
    prob = prob[prob > _EPS]
    return float(-np.sum(prob * np.log(prob)))


def _candidate_phases(center: float, *, span: float, step: float) -> np.ndarray:
    count = int(round((2.0 * span) / step)) + 1
    return np.linspace(float(center) - span, float(center) + span, count)


def _phase_masks(data: np.ndarray, active_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    magnitude = np.abs(data)
    valid = active_mask & np.isfinite(magnitude)
    if np.count_nonzero(valid) < 8:
        all_valid = np.isfinite(magnitude)
        return all_valid, all_valid
    valid_values = magnitude[valid]
    low = float(np.percentile(valid_values, 45.0))
    high = float(np.percentile(valid_values, 82.0))
    signal = valid & (magnitude >= high)
    signal_free = valid & (magnitude <= low)
    if np.count_nonzero(signal) < 8:
        signal = valid & (magnitude >= float(np.percentile(valid_values, 70.0)))
    if np.count_nonzero(signal_free) < 8:
        signal_free = valid & (magnitude <= float(np.percentile(valid_values, 55.0)))
    return signal, signal_free


def _apply_zero_order_phase(data: np.ndarray, degrees: float) -> np.ndarray:
    return np.asarray(data, dtype=np.complex128) * np.exp(1j * math.radians(float(degrees)))


def _bernstein_baseline(
    axis: np.ndarray,
    values: np.ndarray,
    *,
    order: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    t = _unit_axis(axis)
    mask = _baseline_mask(values)
    minimum = max(order + 1, 12)
    if np.count_nonzero(mask) < minimum:
        mask = _lowest_fraction_mask(values, fraction=0.45)
    coeffs = _robust_linear_fit(
        _bernstein_matrix(t, order),
        values,
        initial_mask=mask,
        order=order,
    )
    baseline = _bernstein_matrix(t, order) @ coeffs
    return baseline, {
        "baseline_model": "bernstein_polynomial",
        "baseline_points": int(np.count_nonzero(mask)),
        "coefficients": [round(float(value), 10) for value in coeffs],
    }


def _polynomial_baseline(
    axis: np.ndarray,
    values: np.ndarray,
    *,
    order: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    t = _unit_axis(axis)
    fit_order = max(1, min(5, order))
    mask = _baseline_mask(values)
    if np.count_nonzero(mask) < fit_order + 2:
        mask = _lowest_fraction_mask(values, fraction=0.45)
    matrix = np.vstack([t**power for power in range(fit_order + 1)]).T
    coeffs = _robust_linear_fit(matrix, values, initial_mask=mask, order=fit_order)
    baseline = matrix @ coeffs
    return baseline, {
        "baseline_model": "polynomial",
        "baseline_points": int(np.count_nonzero(mask)),
        "coefficients": [round(float(value), 10) for value in coeffs],
    }


def _spline_baseline(
    axis: np.ndarray,
    values: np.ndarray,
    *,
    order: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    t = _unit_axis(axis)
    mask = _baseline_mask(values)
    node_x, node_y = _baseline_nodes(t, values, mask)
    if node_x.size < 4:
        baseline, metadata = _polynomial_baseline(axis, values, order=min(order, 3))
        metadata["spline_fallback"] = "polynomial"
        return baseline, metadata
    sort_idx = np.argsort(node_x)
    node_x = node_x[sort_idx]
    node_y = node_y[sort_idx]
    try:
        from scipy.interpolate import CubicSpline  # type: ignore[import-not-found]

        spline = CubicSpline(node_x, node_y, bc_type="natural", extrapolate=True)
        baseline = np.asarray(spline(t), dtype=np.float64)
        fallback = None
    except Exception:
        baseline = np.interp(t, node_x, node_y)
        fallback = "linear_interpolation"
    return baseline, {
        "baseline_model": "cubic_spline",
        "baseline_nodes": int(node_x.size),
        "baseline_points": int(np.count_nonzero(mask)),
        **({"spline_fallback": fallback} if fallback else {}),
    }


def _whittaker_baseline(values: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    y = np.asarray(values, dtype=np.float64)
    n = int(y.size)
    if n < 4:
        baseline = np.full_like(y, float(np.nanmedian(y)) if y.size else 0.0)
        return baseline, {"baseline_model": "constant", "iterations": 0}
    try:
        from scipy import sparse  # type: ignore[import-not-found]
        from scipy.sparse.linalg import spsolve  # type: ignore[import-not-found]
    except Exception:
        baseline, metadata = _spline_baseline(np.arange(n, dtype=np.float64), y, order=3)
        metadata["whittaker_fallback"] = "spline"
        return baseline, metadata

    lam = float(2.5e6 * (n / 4096.0) ** 2)
    lam = max(1.0e5, min(2.5e9, lam))
    asymmetry = 0.01
    iterations = 12
    weights = np.ones(n, dtype=np.float64)
    diff = sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(n - 2, n), format="csc")
    penalty = lam * (diff.T @ diff)
    baseline = np.full(n, float(np.nanmedian(y)), dtype=np.float64)
    for _ in range(iterations):
        system = sparse.spdiags(weights, 0, n, n, format="csc") + penalty
        baseline = np.asarray(spsolve(system, weights * y), dtype=np.float64)
        weights = np.where(y > baseline, asymmetry, 1.0 - asymmetry)
    return baseline, {
        "baseline_model": "whittaker_asymmetric_least_squares",
        "smoothness": lam,
        "asymmetry": asymmetry,
        "iterations": iterations,
        "signal_free_fraction": round(float(np.mean(weights > 0.5)), 5),
    }


def _robust_linear_fit(
    matrix: np.ndarray,
    values: np.ndarray,
    *,
    initial_mask: np.ndarray,
    order: int,
) -> np.ndarray:
    mask = initial_mask.copy()
    minimum = max(order + 1, 8)
    if np.count_nonzero(mask) < minimum:
        mask = _lowest_fraction_mask(values, fraction=0.5)
    coeffs = np.zeros(matrix.shape[1], dtype=np.float64)
    for _ in range(5):
        if np.count_nonzero(mask) < matrix.shape[1]:
            break
        coeffs, *_ = np.linalg.lstsq(matrix[mask], values[mask], rcond=None)
        residual = values - matrix @ coeffs
        residual_masked = residual[mask]
        center = float(np.nanmedian(residual_masked)) if residual_masked.size else 0.0
        sigma = _mad(residual_masked)
        if sigma <= _EPS:
            break
        next_mask = mask & (residual <= center + 2.5 * sigma)
        if np.count_nonzero(next_mask) < minimum or np.array_equal(next_mask, mask):
            break
        mask = next_mask
    return coeffs


def _bernstein_matrix(t: np.ndarray, order: int) -> np.ndarray:
    n = max(1, int(order))
    return np.vstack(
        [comb(n, k) * (t**k) * ((1.0 - t) ** (n - k)) for k in range(n + 1)]
    ).T


def _baseline_nodes(
    t: np.ndarray,
    values: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    bins = max(12, min(96, int(round(math.sqrt(max(values.size, 1))))))
    node_x: list[float] = []
    node_y: list[float] = []
    for idx in range(bins):
        low = idx / bins
        high = (idx + 1) / bins
        in_bin = (t >= low) & ((t < high) if idx < bins - 1 else (t <= high)) & mask
        if np.count_nonzero(in_bin) < 2:
            in_bin = (t >= low) & ((t < high) if idx < bins - 1 else (t <= high))
        segment = values[in_bin]
        segment = segment[np.isfinite(segment)]
        if segment.size == 0:
            continue
        node_x.append((low + high) / 2.0)
        node_y.append(float(np.percentile(segment, 25.0)))
    return np.asarray(node_x, dtype=np.float64), np.asarray(node_y, dtype=np.float64)


def _baseline_mask(values: np.ndarray) -> np.ndarray:
    y = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(y)
    if np.count_nonzero(finite) < 8:
        return finite
    centered = y - float(np.nanmedian(y[finite]))
    abs_centered = np.abs(centered)
    noise = _mad(centered[finite])
    cutoff = max(noise * 3.5, float(np.nanpercentile(abs_centered[finite], 40.0)))
    mask = finite & (abs_centered <= cutoff)
    if np.count_nonzero(mask) < max(8, int(0.08 * y.size)):
        mask = _lowest_fraction_mask(abs_centered, fraction=0.45) & finite
    return mask


def _lowest_fraction_mask(values: np.ndarray, *, fraction: float) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    finite = np.isfinite(arr)
    if not np.any(finite):
        return finite
    cutoff = float(np.nanpercentile(arr[finite], max(1.0, min(99.0, fraction * 100.0))))
    return finite & (arr <= cutoff)


def _downsample_for_phase(
    data: np.ndarray,
    axis: np.ndarray,
    active_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if data.size <= _MAX_PHASE_SCORE_POINTS:
        return data, axis, active_mask
    stride = int(math.ceil(data.size / _MAX_PHASE_SCORE_POINTS))
    return data[::stride], axis[::stride], active_mask[::stride]


def _unblinded_mask(axis: np.ndarray, blind_regions: list[PhaseRegion] | None) -> np.ndarray:
    mask = np.ones(axis.size, dtype=bool)
    for region in blind_regions or []:
        if len(region) != 2:
            continue
        low = min(float(region[0]), float(region[1]))
        high = max(float(region[0]), float(region[1]))
        mask &= ~((axis >= low) & (axis <= high))
    return mask


def _unit_axis(axis: np.ndarray) -> np.ndarray:
    x = np.asarray(axis, dtype=np.float64)
    finite = x[np.isfinite(x)]
    if finite.size == 0:
        return np.linspace(0.0, 1.0, x.size)
    lo = float(np.nanmin(finite))
    hi = float(np.nanmax(finite))
    span = hi - lo
    if abs(span) <= _EPS:
        return np.zeros_like(x, dtype=np.float64)
    return np.clip((x - lo) / span, 0.0, 1.0)


def _coerce_axis(axis: np.ndarray, size: int) -> np.ndarray:
    ppm = np.asarray(axis, dtype=np.float64).reshape(-1)
    if ppm.size != size:
        return np.linspace(float(size - 1), 0.0, size, dtype=np.float64)
    return ppm


def _full_scale(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0
    return float(np.nanmax(finite) - np.nanmin(finite))


def _mad(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return 0.0
    center = float(np.nanmedian(arr))
    return float(1.4826 * np.nanmedian(np.abs(arr - center)))


def _normalize_method(method: str | None) -> str:
    return (method or "").strip().lower().replace("-", "_").replace(" ", "_")


def _wrap_degrees(value: float) -> float:
    wrapped = ((float(value) + 180.0) % 360.0) - 180.0
    return 180.0 if math.isclose(wrapped, -180.0, abs_tol=1e-12) else wrapped


def _json_blind_regions(blind_regions: list[PhaseRegion] | None) -> list[dict[str, float]]:
    return [
        {"ppm_min": min(float(low), float(high)), "ppm_max": max(float(low), float(high))}
        for low, high in (blind_regions or [])
    ]


def _copy_spectrum(
    spectrum: NMRSpectrum,
    *,
    data: np.ndarray,
    step: str,
    metadata: dict[str, Any],
) -> NMRSpectrum:
    merged = dict(spectrum.metadata or {})
    preprocessing = dict(merged.get("preprocessing") or {})
    preprocessing[step] = metadata
    merged["preprocessing"] = preprocessing
    merged["fingerprint_hash"] = _fingerprint(
        data=data,
        ppm_axis=spectrum.ppm_axis,
        metadata=merged,
    )
    return replace(
        spectrum,
        data=np.asarray(data).copy(),
        ppm_axis=np.asarray(spectrum.ppm_axis, dtype=np.float64).copy(),
        metadata=merged,
        fingerprint_hash=str(merged["fingerprint_hash"]),
    )


def _fingerprint(*, data: np.ndarray, ppm_axis: np.ndarray, metadata: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(b"moltrace.phase_baseline.v1")
    for key in sorted(metadata):
        if key == "acquisition_params":
            continue
        digest.update(str(key).encode("utf-8"))
        digest.update(str(metadata[key]).encode("utf-8"))
    digest.update(np.round(np.asarray(ppm_axis, dtype="<f8"), 8).tobytes())
    if np.iscomplexobj(data):
        arr = np.asarray(data, dtype=np.complex128)
        digest.update(np.round(arr.real.astype("<f8"), 8).tobytes())
        digest.update(np.round(arr.imag.astype("<f8"), 8).tobytes())
    else:
        digest.update(np.round(np.asarray(data, dtype="<f8"), 8).tobytes())
    return digest.hexdigest()
