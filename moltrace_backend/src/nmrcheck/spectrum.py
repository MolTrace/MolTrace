from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from statistics import median
from typing import Any

from .baseline import (
    apply_bernstein_baseline_correction,
    apply_signal_free_smooth_baseline_polish,
    apply_simple_baseline_correction,
    evaluate_baseline_flatness,
    normalize_baseline_mode,
)
from .mnova_view import weak_peak_magnifier_view
from .models import (
    Peak,
    SpectrumComparisonReport,
    SpectrumExtraPeak,
    SpectrumMissingReferencePeak,
    SpectrumPeakMatch,
    SpectrumPoint,
    SpectrumPreviewReport,
)
from .compound_class_priors import diagnostic_regions_for
from .gsd import deconvolve_region, multiplicity_from_lines
from .impurities import match_h1_impurity_shifts
from .nmr_tables import solvent_windows
from .parser import ReferencePeakAssignment, normalize_multiplicity, normalize_nmr_text, parse_j_values_hz, parse_reference_nmr_text

_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_PREVIEW_DOWNSAMPLING_METHOD = "min_max_lttb_envelope"
_PROCESSED_DISPLAY_DOWNSAMPLING_METHOD = "min_max_bucket_extrema_preserving"

try:  # Optional C fast path; the pure-Python fallback below is deterministic.
    import lttbc as _lttbc
except Exception:  # pragma: no cover - exercised only when optional wheel is absent.
    _lttbc = None


class SpectrumParseError(ValueError):
    pass


@dataclass(frozen=True)
class _PeakComponent:
    shift_ppm: float
    area: float
    intensity: float
    left_index: int
    apex_index: int
    right_index: int


@dataclass(frozen=True)
class _PeakEstimate:
    shift_ppm: float
    area: float
    intensity: float
    multiplicity: str
    width_ppm: float
    component_count: int
    j_values_hz: tuple[float, ...]


@dataclass(frozen=True)
class _ReferenceCandidateMatch:
    reference_index: int
    extracted_index: int
    delta_ppm: float
    status: str
    multiplicity_match: bool
    integration_match: bool


_SOLVENT_MASK_WINDOWS: dict[str, list[tuple[float, float, str]]] = {
    "CDCl3": [(7.20, 7.32, "residual solvent"), (1.45, 1.70, "water")],
    "DMSO-d6": [(2.45, 2.60, "residual solvent"), (3.15, 3.45, "water")],
    "CD3OD": [(3.25, 3.38, "residual solvent"), (4.70, 5.05, "water")],
    "D2O": [(4.55, 5.05, "water")],
    "acetone-d6": [(2.00, 2.12, "residual solvent"), (2.70, 2.95, "water")],
    "CD3CN": [(1.90, 2.05, "residual solvent"), (2.05, 2.25, "water")],
    "C6D6": [(7.05, 7.25, "residual solvent"), (0.35, 0.55, "water")],
    "pyridine-d5": [(7.10, 8.80, "residual solvent"), (3.90, 4.95, "water")],
    "THF-d8": [(1.65, 1.82, "residual solvent"), (3.50, 3.70, "residual solvent"), (2.65, 2.90, "water")],
    "toluene-d8": [(2.02, 2.18, "residual solvent"), (0.35, 0.55, "water")],
}


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _lttbc_selected_positions(clean: list[tuple[float, float, int]], target: int) -> list[int]:
    if _lttbc is None or target < 3 or len(clean) <= target:
        return []
    try:
        sampled_x, sampled_y = _lttbc.downsample(
            [point[0] for point in clean],
            [point[1] for point in clean],
            min(target, len(clean)),
        )
    except Exception:
        return []

    positions_by_value: dict[tuple[float, float], list[int]] = {}
    for position, (x, y, _) in enumerate(clean):
        positions_by_value.setdefault((x, y), []).append(position)

    cursors: dict[tuple[float, float], int] = {}
    selected: list[int] = []
    last_position = -1
    for x_raw, y_raw in zip(sampled_x, sampled_y, strict=False):
        key = (float(x_raw), float(y_raw))
        positions = positions_by_value.get(key)
        if not positions:
            continue
        cursor = cursors.get(key, 0)
        while cursor < len(positions) and positions[cursor] <= last_position:
            cursor += 1
        if cursor >= len(positions):
            continue
        position = positions[cursor]
        selected.append(position)
        last_position = position
        cursors[key] = cursor + 1
    return selected


def _average_clean_point(clean: list[tuple[float, float, int]], start: int, stop: int) -> tuple[float, float]:
    sx = 0.0
    sy = 0.0
    count = 0
    for idx in range(max(0, start), min(stop, len(clean))):
        sx += clean[idx][0]
        sy += clean[idx][1]
        count += 1
    if count == 0:
        fallback = clean[min(max(start, 0), len(clean) - 1)]
        return fallback[0], fallback[1]
    return sx / count, sy / count


def _python_lttb_position(
    clean: list[tuple[float, float, int]],
    *,
    start: int,
    stop: int,
    next_start: int,
    next_stop: int,
    anchor_position: int,
) -> int | None:
    if start >= stop:
        return None
    anchor_x, anchor_y, _ = clean[anchor_position]
    next_avg_x, next_avg_y = _average_clean_point(clean, next_start, next_stop)
    best_position: int | None = None
    best_area = -1.0
    for position in range(start, stop):
        x, y, _ = clean[position]
        area = abs((anchor_x - next_avg_x) * (y - anchor_y) - (anchor_x - x) * (next_avg_y - anchor_y))
        if area > best_area:
            best_area = area
            best_position = position
    return best_position


def _trim_selected_downsample_points(
    ordered: list[tuple[float, float, int]],
    *,
    limit: int,
) -> list[tuple[float, float, int]]:
    if len(ordered) <= limit:
        return ordered
    if limit <= 2:
        return ordered[:limit]
    endpoints = [ordered[0], ordered[-1]]
    interior = ordered[1:-1]
    strongest = sorted(interior, key=lambda item: abs(item[1]), reverse=True)[: max(0, limit - 2)]
    return [endpoints[0], *sorted(strongest, key=lambda item: item[2]), endpoints[1]]


def _downsample_points(points: list[tuple[float, float]], limit: int = 700) -> list[SpectrumPoint]:
    if not points:
        return []
    clean: list[tuple[float, float, int]] = []
    for idx, (x_raw, y_raw) in enumerate(points):
        x = float(x_raw)
        y = float(y_raw)
        if math.isfinite(x) and math.isfinite(y):
            clean.append((x, y, idx))
    if len(clean) <= limit:
        return [SpectrumPoint(shift_ppm=x, intensity=y) for x, y, _ in clean]
    safe_limit = max(3, int(limit))
    bucket_count = max(1, (safe_limit - 2) // 3)
    bucket_size = (len(clean) - 2) / bucket_count
    selected: dict[int, tuple[float, float, int]] = {
        clean[0][2]: clean[0],
        clean[-1][2]: clean[-1],
    }
    use_python_lttb = _lttbc is None
    anchor_position = 0
    for bucket_idx in range(bucket_count):
        start = 1 + int(math.floor(bucket_idx * bucket_size))
        end = 1 + int(math.floor((bucket_idx + 1) * bucket_size))
        stop = max(start + 1, min(end, len(clean) - 1))
        if start >= stop:
            continue
        min_point = clean[start]
        max_point = clean[start]
        for clean_idx in range(start + 1, stop):
            item = clean[clean_idx]
            if item[1] < min_point[1]:
                min_point = item
            if item[1] > max_point[1]:
                max_point = item
        selected[min_point[2]] = min_point
        selected[max_point[2]] = max_point
        if use_python_lttb:
            next_start = 1 + int(math.floor((bucket_idx + 1) * bucket_size))
            next_stop = max(
                next_start + 1,
                min(1 + int(math.floor((bucket_idx + 2) * bucket_size)), len(clean) - 1),
            )
            lttb_position = _python_lttb_position(
                clean,
                start=start,
                stop=stop,
                next_start=next_start,
                next_stop=next_stop,
                anchor_position=anchor_position,
            )
            if lttb_position is not None:
                lttb_point = clean[lttb_position]
                selected[lttb_point[2]] = lttb_point
                anchor_position = lttb_position
    if _lttbc is not None:
        lttb_target = max(3, safe_limit - (2 * bucket_count))
        for position in _lttbc_selected_positions(clean, target=lttb_target):
            point = clean[position]
            selected[point[2]] = point
    ordered = [selected[idx] for idx in sorted(selected)]
    ordered = _trim_selected_downsample_points(ordered, limit=safe_limit)
    return [SpectrumPoint(shift_ppm=x, intensity=y) for x, y, _ in ordered]


def _downsample_processed_display_points(
    points: list[tuple[float, float]],
    limit: int = 700,
) -> list[SpectrumPoint]:
    """Previous processed-spectrum display sampler.

    Processed spectra are already baseline-corrected and display-smoothed before
    this step. The stronger MinMaxLTTB evidence sampler can re-emphasize tiny
    baseline extrema after smoothing; for the processed preview surface, keep
    the earlier min/max envelope so the baseline stays visually smooth.
    """
    if not points:
        return []
    clean: list[tuple[float, float, int]] = []
    for idx, (x_raw, y_raw) in enumerate(points):
        x = float(x_raw)
        y = float(y_raw)
        if math.isfinite(x) and math.isfinite(y):
            clean.append((x, y, idx))
    safe_limit = max(3, int(limit))
    if len(clean) <= safe_limit:
        return [SpectrumPoint(shift_ppm=x, intensity=y) for x, y, _ in clean]

    sorted_y = sorted(y for _x, y, _idx in clean)
    center = median(sorted_y)
    noise = 1.4826 * _median_absolute_deviation(sorted_y)
    y01 = _percentile(sorted_y, 1.0)
    y10 = _percentile(sorted_y, 10.0)
    y90 = _percentile(sorted_y, 90.0)
    y99 = _percentile(sorted_y, 99.0)
    robust_span = max(y99 - y01, y90 - y10, 0.0)
    peak_threshold = max(noise * 5.0, robust_span * 0.003, abs(center) * 1e-6, 1e-12)

    bucket_count = max(1, (safe_limit - 2) // 2)
    bucket_size = (len(clean) - 2) / bucket_count
    selected: dict[int, tuple[float, float, int]] = {
        clean[0][2]: clean[0],
        clean[-1][2]: clean[-1],
    }
    for bucket_idx in range(bucket_count):
        start = 1 + int(math.floor(bucket_idx * bucket_size))
        end = 1 + int(math.floor((bucket_idx + 1) * bucket_size))
        stop = max(start + 1, min(end, len(clean) - 1))
        if start >= stop:
            continue
        min_point = clean[start]
        max_point = clean[start]
        sx = 0.0
        sy = 0.0
        count = 0
        for clean_idx in range(start + 1, stop):
            item = clean[clean_idx]
            if item[1] < min_point[1]:
                min_point = item
            if item[1] > max_point[1]:
                max_point = item
        for clean_idx in range(start, stop):
            item = clean[clean_idx]
            sx += item[0]
            sy += item[1]
            count += 1
        bucket_span_y = max_point[1] - min_point[1]
        bucket_has_peak = bucket_span_y >= peak_threshold or max(
            abs(max_point[1] - center),
            abs(min_point[1] - center),
        ) >= peak_threshold * 2.0
        if bucket_has_peak:
            selected[min_point[2]] = min_point
            selected[max_point[2]] = max_point
        elif count:
            midpoint = clean[start + (stop - start) // 2]
            selected[midpoint[2]] = midpoint
    ordered = [selected[idx] for idx in sorted(selected)]
    return [SpectrumPoint(shift_ppm=x, intensity=y) for x, y, _ in ordered[:safe_limit]]


def _serialized_downsampled_points(
    points: list[tuple[float, float]],
    *,
    limit: int = 700,
) -> list[dict[str, float]]:
    return [point.model_dump(mode="json") for point in _downsample_points(points, limit=limit)]


def _estimate_preserved_baseline(points: list[tuple[float, float]]) -> float:
    values = sorted(float(y) for _, y in points if math.isfinite(float(y)))
    if not values:
        return 0.0
    return float(_percentile(values, 50.0))


def _build_preserved_spectrum_state(
    points: list[tuple[float, float]],
    *,
    source: str,
    processing_stage: str = "as_uploaded",
    point_limit: int = 700,
    normalized_for_preview: bool = False,
) -> dict[str, Any]:
    finite_points = [
        (float(x), float(y))
        for x, y in points
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    values = [y for _, y in finite_points]
    baseline = _estimate_preserved_baseline(finite_points)
    if values:
        intensity_min = min(values)
        intensity_max = max(values)
    else:
        intensity_min = 0.0
        intensity_max = 0.0
    return {
        "preserved": True,
        "source": source,
        "processing_stage": processing_stage,
        "point_count": len(finite_points),
        "baseline": round(baseline, 8),
        "intensity_min": round(float(intensity_min), 8),
        "intensity_max": round(float(intensity_max), 8),
        "normalized_for_preview": normalized_for_preview,
        "preview_points": _serialized_downsampled_points(
            finite_points,
            limit=point_limit,
        ),
    }


def _build_preview_spectrum_state(
    points: list[tuple[float, float]],
    preview_points: list[SpectrumPoint],
    *,
    source: str,
    processing_stage: str = "as_uploaded",
    normalized_for_preview: bool = False,
) -> dict[str, Any]:
    preview_pairs = [
        (float(point.shift_ppm), float(point.intensity))
        for point in preview_points
        if math.isfinite(float(point.shift_ppm)) and math.isfinite(float(point.intensity))
    ]
    preview_values = [y for _, y in preview_pairs]
    if preview_values:
        baseline = median(preview_values)
        intensity_min = min(preview_values)
        intensity_max = max(preview_values)
    else:
        baseline = 0.0
        intensity_min = 0.0
        intensity_max = 0.0
    return {
        "preserved": True,
        "source": source,
        "processing_stage": processing_stage,
        "point_count": len(points),
        "baseline": round(float(baseline), 8),
        "intensity_min": round(float(intensity_min), 8),
        "intensity_max": round(float(intensity_max), 8),
        "normalized_for_preview": normalized_for_preview,
        "summary_source": "downsampled_preview",
        "preview_points": [point.model_dump(mode="json") for point in preview_points],
    }


def _preview_baseline_flatness_qa(
    preview_points: list[SpectrumPoint],
    *,
    mode: str,
) -> dict[str, Any]:
    preview_pairs = [
        (float(point.shift_ppm), float(point.intensity))
        for point in preview_points
        if math.isfinite(float(point.shift_ppm)) and math.isfinite(float(point.intensity))
    ]
    qa = evaluate_baseline_flatness(preview_pairs, mode=mode).as_dict()
    qa["scope"] = "downsampled_preview"
    return qa


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def _detect_text_extension(filename: str) -> str:
    name = filename.lower().strip()
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1]


_TEXT_SPECTRUM_EXTENSIONS = {"csv", "tsv", "txt", "xy", "asc", "dat"}
_JCAMP_SPECTRUM_EXTENSIONS = {"jcamp", "jdx", "dx"}


def _parse_peak_table(rows: list[dict[str, str]]) -> list[Peak]:
    peaks: list[Peak] = []
    for row in rows:
        shift = _safe_float(row.get("shift_ppm") or row.get("ppm") or row.get("shift") or row.get("delta"))
        integ = _safe_float(row.get("integration_h") or row.get("integration") or row.get("integral") or row.get("h") or row.get("area"))
        mult = (row.get("multiplicity") or row.get("mult") or row.get("pattern") or "m").strip()
        j_values = parse_j_values_hz(
            row.get("j_values_hz")
            or row.get("j_values")
            or row.get("j_hz")
            or row.get("coupling_hz")
            or row.get("j")
        )
        if shift is None or integ is None:
            continue
        peaks.append(
            Peak(
                shift_ppm=shift,
                multiplicity=mult or "m",
                integration_h=max(0.2, integ),
                j_values_hz=list(j_values),
            )
        )
    if not peaks:
        raise SpectrumParseError("No valid peak rows were found in the uploaded peak table.")
    return peaks


def _extract_numeric_pairs_from_delimited(text: str, delimiter: str) -> list[tuple[float, float]]:
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    points: list[tuple[float, float]] = []
    for row in reader:
        if len(row) < 2:
            continue
        x = _safe_float(row[0])
        y = _safe_float(row[1])
        if x is None or y is None:
            continue
        points.append((x, y))
    return points


def _extract_numeric_pairs_from_text(text: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "//", "$$")):
            continue
        values = _FLOAT_RE.findall(line)
        if len(values) < 2:
            continue
        x = _safe_float(values[0])
        y = _safe_float(values[1])
        if x is None or y is None:
            continue
        points.append((x, y))
    return points


def _sniff_delimiter(text: str, filename: str) -> str:
    ext = _detect_text_extension(filename)
    if ext == "tsv":
        return "\t"
    sample = "\n".join(text.splitlines()[:10])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        return dialect.delimiter
    except Exception:
        return "\t" if "\t" in sample else (";" if ";" in sample else ",")


def _parse_csv_or_tsv(filename: str, text: str) -> tuple[str, list[Peak], list[tuple[float, float]], list[str]]:
    warnings: list[str] = []
    delimiter = _sniff_delimiter(text, filename)
    raw_reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        fieldnames = next(raw_reader)
    except StopIteration:
        fieldnames = []
    if fieldnames:
        normalized_fields = [str(name).strip().lower() for name in fieldnames]
        lowered = {name for name in normalized_fields if name}
        shift_keys = {"shift_ppm", "ppm", "shift", "delta"}
        integration_keys = {"integration_h", "integration", "integral", "h", "area"}
        if (shift_keys & lowered) and (integration_keys & lowered):
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            peaks = _parse_peak_table(list(reader))
            warnings.append("Peak table detected; uploaded rows were used directly as peak assignments.")
            return ("peak_table", peaks, [(p.shift_ppm, p.integration_h) for p in peaks], warnings)

        x_keys = {"ppm", "shift", "shift_ppm", "delta", "x"}
        y_keys = {"intensity", "signal", "y", "amplitude", "absorbance", "response"}
        x_index = next((idx for idx, name in enumerate(normalized_fields) if name in x_keys), None)
        y_index = next((idx for idx, name in enumerate(normalized_fields) if name in y_keys), None)
        if x_index is not None and y_index is not None:
            max_index = max(x_index, y_index)
            points: list[tuple[float, float]] = []
            for row in raw_reader:
                if len(row) <= max_index:
                    continue
                x = _safe_float(row[x_index])
                y = _safe_float(row[y_index])
                if x is None or y is None:
                    continue
                points.append((x, y))
            if points:
                warnings.append("Spectrum trace detected; peaks and integrations were inferred heuristically from intensity data.")
                return ("trace", [], points, warnings)

    points = _extract_numeric_pairs_from_delimited(text, delimiter=delimiter)
    if not points:
        points = _extract_numeric_pairs_from_text(text)
    if not points:
        raise SpectrumParseError("Could not parse numeric spectrum data from the uploaded text spectrum file.")
    warnings.append("Spectrum trace detected; peaks and integrations were inferred heuristically from intensity data.")
    return ("trace", [], points, warnings)


def _parse_jcamp_text(text: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("##") or line.startswith("$$"):
            continue
        nums = [float(token) for token in _FLOAT_RE.findall(line)]
        if len(nums) < 2:
            continue
        pair_count = len(nums) // 2
        for idx in range(pair_count):
            x = nums[2 * idx]
            y = nums[2 * idx + 1]
            points.append((x, y))
    if not points:
        raise SpectrumParseError(
            "Could not extract simple XY data pairs from the JCAMP-DX file. Complex JCAMP encodings may need a fuller parser."
        )
    return points


def _smooth(values: list[float], window: int = 7) -> list[float]:
    if window <= 1 or len(values) < 3:
        return values[:]
    radius = max(1, window // 2)
    out: list[float] = []
    for idx in range(len(values)):
        start = max(0, idx - radius)
        end = min(len(values), idx + radius + 1)
        out.append(sum(values[start:end]) / (end - start))
    return out


def _odd_window(length: int, *, fraction: float, minimum: int, maximum: int) -> int:
    if length <= 0:
        return minimum
    window = int(round(length * fraction))
    window = max(minimum, min(maximum, window))
    if window % 2 == 0:
        window += 1
    return min(window, length if length % 2 == 1 else max(1, length - 1))


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * max(0.0, min(100.0, percentile)) / 100.0
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return sorted_values[lower]
    fraction = rank - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def _median_absolute_deviation(values: list[float]) -> float:
    if not values:
        return 0.0
    center = median(values)
    return median([abs(value - center) for value in values])


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    size = len(vector)
    augmented = [row[:] + [rhs] for row, rhs in zip(matrix, vector, strict=True)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            return None
        if pivot != col:
            augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        for idx in range(col, size + 1):
            augmented[col][idx] /= pivot_value
        for row in range(size):
            if row == col:
                continue
            factor = augmented[row][col]
            if abs(factor) < 1e-16:
                continue
            for idx in range(col, size + 1):
                augmented[row][idx] -= factor * augmented[col][idx]
    return [augmented[row][size] for row in range(size)]


def _weighted_polynomial_fit(
    x_values: list[float],
    y_values: list[float],
    weights: list[float],
    degree: int,
) -> list[float] | None:
    degree = max(0, min(int(degree), max(0, len(x_values) - 1)))
    terms = degree + 1
    power_sums = [0.0 for _ in range(terms * 2 - 1)]
    rhs = [0.0 for _ in range(terms)]
    for x, y, weight in zip(x_values, y_values, weights, strict=False):
        w = max(0.0, float(weight))
        powers = [1.0]
        for _ in range(1, terms * 2 - 1):
            powers.append(powers[-1] * x)
        for idx in range(terms * 2 - 1):
            power_sums[idx] += w * powers[idx]
        for idx in range(terms):
            rhs[idx] += w * y * powers[idx]
    matrix = [
        [power_sums[row + col] for col in range(terms)]
        for row in range(terms)
    ]
    return _solve_linear_system(matrix, rhs)


def _evaluate_polynomial(coefficients: list[float], x: float) -> float:
    value = 0.0
    for coefficient in reversed(coefficients):
        value = value * x + coefficient
    return value


def _orient_positive(values: list[float]) -> tuple[list[float], int]:
    if not values:
        return ([], 1)
    high = max(values)
    low = min(values)
    if abs(low) > abs(high) * 1.15:
        return ([-value for value in values], -1)
    return (values[:], 1)


def _robust_polynomial_baseline_correct(
    values: list[float],
    *,
    degree: int | None = None,
    orient_positive: bool = True,
) -> tuple[list[float], dict[str, Any]]:
    raw = [float(value) for value in values if math.isfinite(float(value))]
    if len(raw) != len(values):
        raw = [float(value) if math.isfinite(float(value)) else 0.0 for value in values]
    if not raw:
        return ([], {"applied": False, "method": "none"})
    if len(raw) < 51:
        base = median(raw)
        corrected = [value - base for value in raw]
        if orient_positive:
            corrected, orientation = _orient_positive(corrected)
        else:
            orientation = 1
        return (
            corrected,
            {
                "applied": True,
                "method": "median_offset_sparse_trace",
                "polynomial_order": 0,
                "orientation": orientation,
                "baseline_locked_to_zero": True,
            },
        )

    center = median(raw)
    centered = [value - center for value in raw]
    if orient_positive:
        oriented, orientation = _orient_positive(centered)
    else:
        oriented = centered
        orientation = 1
    size = len(oriented)
    xs = [-1.0 + 2.0 * idx / max(1, size - 1) for idx in range(size)]
    polynomial_order = degree if degree is not None else (5 if size >= 700 else 3)
    polynomial_order = max(1, min(polynomial_order, 6, size // 8))
    weights = [1.0 for _ in oriented]
    baseline = [0.0 for _ in oriented]
    for _ in range(9):
        coeffs = _weighted_polynomial_fit(xs, oriented, weights, polynomial_order)
        if coeffs is None:
            break
        baseline = [_evaluate_polynomial(coeffs, x) for x in xs]
        residuals = [y - base for y, base in zip(oriented, baseline, strict=False)]
        abs_residuals = sorted(abs(value) for value in residuals)
        noise = 1.4826 * _median_absolute_deviation(residuals)
        if noise <= 1e-12:
            noise = _percentile(abs_residuals, 55.0)
        threshold = max(noise * 2.5, _percentile(abs_residuals, 52.0), 1e-12)
        weights = [
            0.015 if residual > threshold else (0.25 if residual < -threshold * 2.0 else 1.0)
            for residual in residuals
        ]

    corrected = [y - base for y, base in zip(oriented, baseline, strict=False)]
    baseline_candidates = [
        value
        for value, weight in zip(corrected, weights, strict=False)
        if weight >= 0.5
    ]
    offset = median(baseline_candidates) if baseline_candidates else median(corrected)
    corrected = [value - offset for value in corrected]
    return (
        corrected,
        {
            "applied": True,
            "method": "auto_polynomial_signal_free_nodes",
            "polynomial_order": polynomial_order,
            "orientation": orientation,
            "baseline_locked_to_zero": True,
            "baseline_node_fraction": round(sum(1 for weight in weights if weight >= 0.5) / max(1, len(weights)), 4),
        },
    )


def _baseline_correct(values: list[float]) -> list[float]:
    corrected, _metadata = _robust_polynomial_baseline_correct(values, orient_positive=True)
    return [max(0.0, value) for value in corrected]


def _solvent_mask_windows(solvent: str | None, *, nucleus: str = "1H") -> list[tuple[float, float, str]]:
    normalized_nucleus = nucleus.strip().upper().replace("¹", "1").replace("³", "3")
    if normalized_nucleus in {"13C", "C13", "CARBON13", "CARBON-13"}:
        return [
            (float(window.low), float(window.high), window.label)
            for window in solvent_windows(solvent, "13C")
            if window.kind in {"solvent", "water", "reference"}
        ]
    key = _normalize_solvent_key(solvent)
    return _SOLVENT_MASK_WINDOWS.get(key or "", [])


def _ppm_step(x_vals: list[float]) -> float:
    deltas = [abs(x_vals[idx] - x_vals[idx + 1]) for idx in range(len(x_vals) - 1) if not math.isclose(x_vals[idx], x_vals[idx + 1])]
    return median(deltas) if deltas else 0.005


def _normalize_solvent_key(solvent: str | None) -> str | None:
    if not solvent:
        return None
    s = solvent.strip()
    for key in _SOLVENT_MASK_WINDOWS:
        if key.lower() == s.lower():
            return key
    return s


def _in_window(ppm: float, low: float, high: float) -> bool:
    lo, hi = min(low, high), max(low, high)
    return lo <= ppm <= hi


def _apply_solvent_mask(
    points: list[tuple[float, float]],
    solvent: str | None,
    *,
    nucleus: str = "1H",
) -> tuple[list[tuple[float, float]], list[str]]:
    windows = _solvent_mask_windows(solvent, nucleus=nucleus)
    if not windows:
        return points, []
    masked: list[tuple[float, float]] = []
    notes: list[str] = []
    for low, high, label in windows:
        notes.append(f"Masked {label} region around {low:.2f}–{high:.2f} ppm during peak picking.")
    for x, y in points:
        if any(_in_window(x, low, high) for low, high, _ in windows):
            continue
        masked.append((x, y))
    return (masked or points), notes


def _apply_solvent_display_mask(
    points: list[tuple[float, float]],
    solvent: str | None,
    *,
    nucleus: str = "1H",
) -> tuple[list[tuple[float, float]], dict[str, Any], list[str]]:
    windows = _solvent_mask_windows(solvent, nucleus=nucleus)
    if not points or not windows:
        return points, {"display_solvent_masked": False, "display_solvent_mask_windows": []}, []
    non_solvent_values = [
        max(0.0, float(y))
        for x, y in points
        if not any(_in_window(float(x), low, high) for low, high, _ in windows)
    ]
    non_solvent_values = [value for value in non_solvent_values if value > 0]
    if not non_solvent_values:
        return points, {"display_solvent_masked": False, "display_solvent_mask_windows": []}, []
    sorted_non_solvent = sorted(non_solvent_values)
    baseline_cap = _percentile(sorted_non_solvent, 92.0)
    if baseline_cap <= 0:
        baseline_cap = _percentile(sorted_non_solvent, 99.0)
    masked_points: list[tuple[float, float]] = []
    changed_count = 0
    for x, y in points:
        if any(_in_window(float(x), low, high) for low, high, _ in windows):
            masked_value = min(float(y), baseline_cap) if float(y) > 0 else max(float(y), -baseline_cap)
            masked_points.append((x, masked_value))
            if not math.isclose(masked_value, float(y), rel_tol=1e-9, abs_tol=1e-12):
                changed_count += 1
        else:
            masked_points.append((x, y))
    meta = {
        "display_solvent_masked": changed_count > 0,
        "display_solvent_masked_points": changed_count,
        "display_solvent_mask_windows": [
            {"low": round(float(low), 4), "high": round(float(high), 4), "label": label}
            for low, high, label in windows
        ],
    }
    notes = (
        ["Solvent/water regions were muted in the displayed trace so non-solvent peaks control the visible peak height scale."]
        if changed_count > 0
        else []
    )
    return masked_points, meta, notes


def _prepare_trace_display_points(
    points: list[tuple[float, float]],
    *,
    solvent: str | None = None,
    mask_solvent_regions: bool = False,
    nucleus: str = "1H",
    baseline_already_corrected: bool = False,
) -> tuple[list[tuple[float, float]], dict[str, Any], list[str]]:
    windows = _solvent_mask_windows(solvent, nucleus=nucleus) if mask_solvent_regions else []
    meta = {
        "baseline_smoothing": {
            "applied": False,
            "method": "disabled_real_spectrum_default",
            "display_points_corrected": False,
            "baseline_locked_to_zero": False,
            "baseline_already_corrected": bool(baseline_already_corrected),
        },
        "display_solvent_masked": False,
        "display_solvent_mask_windows": [
            {"low": round(float(low), 4), "high": round(float(high), 4), "label": label}
            for low, high, label in windows
        ],
        "display_baseline": 0.0,
        "evidence_trace_preserved": True,
        "note": (
            "Display preprocessing is disabled by default. Solvent masking and "
            "baseline handling are applied only to analysis/QA metadata or explicit "
            "viewer controls, not to the main spectrum trace."
        ),
    }
    return points, meta, []


def _display_smoothing_window(
    x_values: Any,
    *,
    width_ppm: float,
    minimum: int,
    maximum: int,
) -> int:
    try:
        import numpy as np

        finite = np.asarray(x_values, dtype=float)
        finite = finite[np.isfinite(finite)]
        if finite.size < 3:
            return 1
        ordered = np.sort(finite)
        steps = np.diff(ordered)
        steps = steps[np.isfinite(steps) & (steps > 1e-12)]
        if steps.size == 0:
            return 1
        ppm_step = float(np.median(steps))
        window = int(round(float(width_ppm) / max(ppm_step, 1e-12)))
        window = max(int(minimum), min(int(maximum), window))
        if window % 2 == 0:
            window += 1
        limit = int(finite.size if finite.size % 2 else max(1, finite.size - 1))
        return max(1, min(window, limit))
    except Exception:
        return max(1, int(minimum))


def _smooth_display_values(values: Any, *, window: int) -> tuple[Any, str]:
    import numpy as np

    y = np.asarray(values, dtype=float)
    if window <= 2 or y.size < window:
        return y.copy(), "none"
    try:
        from scipy.signal import savgol_filter

        polyorder = min(3, max(1, window - 2))
        return (
            np.asarray(
                savgol_filter(y, window_length=window, polyorder=polyorder, mode="interp"),
                dtype=float,
            ),
            "savitzky_golay",
        )
    except Exception:
        kernel = np.ones(window, dtype=float) / float(window)
        radius = window // 2
        padded = np.pad(y, (radius, radius), mode="edge")
        return (np.convolve(padded, kernel, mode="valid"), "moving_average")


def _aromatic_display_window(nucleus: str) -> tuple[float, float] | None:
    normalized = (nucleus or "").strip().upper().replace("-", "")
    if normalized in {"13C", "C13", "CARBON13"}:
        return (110.0, 160.0)
    if normalized in {"1H", "H1", "PROTON", ""}:
        return (6.0, 9.0)
    return None


def smooth_trace_display_points(
    points: list[tuple[float, float]],
    *,
    nucleus: str,
) -> tuple[list[tuple[float, float]], dict[str, Any]]:
    clean = [
        (float(x), float(y))
        for x, y in points
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    metadata: dict[str, Any] = {
        "applied": False,
        "display_only": True,
        "evidence_trace_preserved": True,
        "method": "none",
    }
    if len(clean) < 9:
        metadata["reason"] = "too_few_points"
        return clean, metadata

    try:
        import numpy as np

        x_values = np.asarray([x for x, _y in clean], dtype=float)
        y_values = np.asarray([y for _x, y in clean], dtype=float)
        finite = np.isfinite(x_values) & np.isfinite(y_values)
        if int(np.count_nonzero(finite)) < 9:
            metadata["reason"] = "too_few_finite_points"
            return clean, metadata

        base_window = _display_smoothing_window(
            x_values,
            width_ppm=0.034,
            minimum=7,
            maximum=61,
        )
        aromatic_window = _display_smoothing_window(
            x_values,
            width_ppm=0.085,
            minimum=max(base_window + 4, 11),
            maximum=121,
        )
        base_values, base_method = _smooth_display_values(y_values, window=base_window)
        aromatic_values, aromatic_method = _smooth_display_values(
            y_values,
            window=aromatic_window,
        )

        smoothed = base_values.copy()
        aromatic_region = _aromatic_display_window(nucleus)
        aromatic_count = 0
        if aromatic_region is not None and aromatic_window > base_window:
            low, high = aromatic_region
            region_mask = (x_values >= low) & (x_values <= high)
            aromatic_count = int(np.count_nonzero(region_mask))
            if aromatic_count:
                smoothed[region_mask] = (
                    0.25 * base_values[region_mask]
                    + 0.75 * aromatic_values[region_mask]
                )

        smoothed_points = [
            (x, float(y))
            for (x, _old_y), y in zip(clean, smoothed, strict=False)
        ]
        metadata.update(
            {
                "applied": True,
                "method": (
                    "adaptive_savgol_aromatic_region"
                    if any("savitzky" in method for method in {base_method, aromatic_method})
                    else "adaptive_moving_average_aromatic_region"
                ),
                "base_method": base_method,
                "base_window_points": int(base_window),
                "aromatic_window_points": int(aromatic_window),
                "aromatic_region_ppm": (
                    {
                        "low": float(aromatic_region[0]),
                        "high": float(aromatic_region[1]),
                    }
                    if aromatic_region is not None
                    else None
                ),
                "aromatic_points_smoothed": aromatic_count,
            }
        )
        return smoothed_points, metadata
    except Exception as exc:
        metadata["reason"] = f"smoothing_failed: {exc}"
        return clean, metadata


def apply_processed_trace_baseline_conditions(
    points: list[tuple[float, float]],
    *,
    mode: str,
    order: int = 3,
    warnings: list[str] | None = None,
    label: str = "processed-file",
) -> tuple[list[tuple[float, float]], dict[str, Any], list[str]]:
    notes = warnings if warnings is not None else []
    processed_baseline_mode = normalize_baseline_mode(mode)
    metadata: dict[str, Any] = {
        "mode": processed_baseline_mode,
        "method": processed_baseline_mode,
        "order": int(order or 3),
        "correction_applied": False,
        "explicit": processed_baseline_mode not in {"none", "preserve"},
    }
    if processed_baseline_mode in {"none", "preserve"}:
        return points, metadata, notes

    if processed_baseline_mode == "bernstein":
        corrected, metadata, baseline_warnings = apply_bernstein_baseline_correction(
            points,
            order=order,
        )
        if len(corrected) >= 32:
            polished, polish_metadata, polish_warnings = apply_signal_free_smooth_baseline_polish(
                corrected,
            )
            baseline_warnings.extend(
                note for note in polish_warnings if note not in baseline_warnings
            )
            metadata["post_baseline_polish"] = polish_metadata
            metadata["baseline_polish_applied"] = bool(polish_metadata.get("correction_applied"))
            if polish_metadata.get("correction_applied"):
                corrected = polished
                metadata["correction_applied"] = True
                metadata["baseline_locked_to_zero"] = True
                flatness = polish_metadata.get("qa_after")
                if isinstance(flatness, dict):
                    metadata["qa"] = flatness
                    metadata["flatness_qa"] = flatness
                metadata["signal_free_fraction"] = polish_metadata.get("signal_free_fraction")
                metadata["baseline_slope"] = polish_metadata.get("baseline_slope")
                metadata["baseline_span"] = polish_metadata.get("baseline_span")
    else:
        corrected, metadata, baseline_warnings = apply_simple_baseline_correction(
            points,
            mode=processed_baseline_mode,
        )
    notes.extend(baseline_warnings)
    if metadata.get("correction_applied"):
        notes.append(
            f"Automatic {label} baseline correction was applied using "
            f"{metadata.get('method')}."
        )
    return corrected, metadata, notes


def _classify_multiplicity(component_count: int, width_ppm: float, ppm_step: float) -> str:
    # A local-maximum picker cannot resolve overlapped lines, so it cannot
    # distinguish a quartet from a doublet-of-doublets (both four lines) or any
    # busier pattern. Only s / d / t are claimed geometrically; four-plus lines
    # are reported honestly as "m" unless a reference text confirms the pattern
    # (see _apply_reference_multiplicity).
    broad_threshold = max(0.12, ppm_step * 24)
    if component_count <= 1:
        return "br s" if width_ppm >= broad_threshold else "s"
    if component_count == 2:
        return "d"
    if component_count == 3:
        return "t"
    return "m"


def _collapse_j_values_for_pattern(spacings_hz: list[float], multiplicity: str) -> tuple[float, ...]:
    if not spacings_hz:
        return ()
    normalized = normalize_multiplicity(multiplicity)
    if normalized in {"s", "br s", "m", "br"}:
        return ()

    grouped: list[list[float]] = []
    for value in sorted(spacings_hz, reverse=True):
        tolerance = max(0.35, value * 0.12)
        for group in grouped:
            anchor = sum(group) / len(group)
            if abs(anchor - value) <= tolerance:
                group.append(value)
                break
        else:
            grouped.append([value])

    collapsed = tuple(
        round(sum(group) / len(group), 1)
        for group in sorted(grouped, key=lambda group: -(sum(group) / len(group)))
    )
    if normalized in {"d", "t", "q"}:
        return (round(sum(spacings_hz) / len(spacings_hz), 1),)
    return collapsed[:3]


def _estimate_cluster_j_values_hz(
    cluster: list[_PeakComponent],
    *,
    frequency_mhz: float | None,
    multiplicity: str,
) -> tuple[float, ...]:
    if frequency_mhz is None or frequency_mhz <= 0 or len(cluster) <= 1:
        return ()
    ordered = sorted(cluster, key=lambda component: component.shift_ppm, reverse=True)
    spacings_hz = [
        abs(ordered[index].shift_ppm - ordered[index + 1].shift_ppm) * float(frequency_mhz)
        for index in range(len(ordered) - 1)
    ]
    filtered = [spacing for spacing in spacings_hz if 0.2 <= spacing <= 25.0]
    return _collapse_j_values_for_pattern(filtered, multiplicity)


def _cluster_peak_components(
    components: list[_PeakComponent],
    x_vals: list[float],
    *,
    sensitivity: float,
    frequency_mhz: float | None,
    detection_trace: list[float] | None = None,
    noise_sigma: float = 0.0,
    deconvolve: bool = False,
) -> list[_PeakEstimate]:
    if not components:
        return []
    ppm_step = _ppm_step(x_vals)
    gap_threshold = min(0.09, max(0.028, ppm_step * 18))
    index_gap_threshold = max(3, int(round(12 * ppm_step / max(ppm_step, 1e-6))))

    clusters: list[list[_PeakComponent]] = [[components[0]]]
    for component in components[1:]:
        current = clusters[-1]
        previous = current[-1]
        ppm_gap = abs(previous.shift_ppm - component.shift_ppm)
        index_gap = max(0, component.left_index - previous.right_index)
        if ppm_gap <= gap_threshold or (
            index_gap <= index_gap_threshold
            and ppm_gap <= gap_threshold * 2.5
        ):
            current.append(component)
        else:
            clusters.append([component])

    estimates: list[_PeakEstimate] = []
    for cluster in clusters:
        total_area = sum(component.area for component in cluster)
        if total_area <= 0:
            continue
        left_index = min(component.left_index for component in cluster)
        right_index = max(component.right_index for component in cluster)
        width_ppm = abs(x_vals[left_index] - x_vals[right_index]) if 0 <= left_index < len(x_vals) and 0 <= right_index < len(x_vals) else 0.0
        weighted_shift = sum(component.shift_ppm * component.area for component in cluster) / total_area
        # GSD: deconvolve multi-line clusters into resolved Lorentzian lines so
        # multiplicity / J come from the true transition count, not the raw
        # local-maximum count (run only on request — it is costly).
        resolved_lines: list[tuple[float, float, float]] = []
        if (
            deconvolve
            and detection_trace is not None
            and len(cluster) >= 2
            and 0 <= left_index < right_index < len(x_vals)
        ):
            lo_index = max(0, left_index - 4)
            hi_index = min(len(x_vals) - 1, right_index + 4)
            if hi_index - lo_index >= 8:
                resolved_lines = deconvolve_region(
                    x_vals[lo_index : hi_index + 1],
                    detection_trace[lo_index : hi_index + 1],
                    [component.shift_ppm for component in cluster],
                    noise_sigma=noise_sigma,
                    max_lines=max(8, len(cluster) + 6),
                )
        if resolved_lines:
            multiplicity, j_values_hz = multiplicity_from_lines(
                [line[0] for line in resolved_lines], frequency_mhz=frequency_mhz
            )
        else:
            multiplicity = _classify_multiplicity(len(cluster), width_ppm, ppm_step)
            j_values_hz = _estimate_cluster_j_values_hz(
                cluster, frequency_mhz=frequency_mhz, multiplicity=multiplicity
            )
        estimates.append(
            _PeakEstimate(
                shift_ppm=weighted_shift,
                area=total_area,
                intensity=max(component.intensity for component in cluster),
                multiplicity=multiplicity,
                width_ppm=width_ppm,
                component_count=len(cluster),
                j_values_hz=j_values_hz,
            )
        )

    estimates.sort(key=lambda peak: peak.shift_ppm, reverse=True)
    filtered: list[_PeakEstimate] = []
    min_sep = max(0.02 if sensitivity <= 0.09 else 0.03, ppm_step * 6)
    for peak in estimates:
        if filtered and abs(filtered[-1].shift_ppm - peak.shift_ppm) < min_sep:
            if peak.intensity > filtered[-1].intensity:
                filtered[-1] = peak
            continue
        filtered.append(peak)
    return filtered


def _estimate_noise_sigma(values: list[float]) -> float:
    """Robust noise σ for SNR-based peak detection.

    NMR peaks occupy only a small fraction of a spectrum, so the bulk of the
    points are baseline noise. A first MAD pass fixes a rough scale; points
    further than a few rough-MADs from the centre are peak signal and are
    dropped, then a second MAD over the surviving noise pool — scaled by the
    1.4826 normal-consistency constant — yields a σ that the peaks themselves
    cannot inflate. Falls back to a first-difference estimate when the trace
    is too flat for the MAD pass to resolve a scale.
    """
    finite = [value for value in values if math.isfinite(value)]
    if len(finite) < 8:
        return 0.0
    rough_mad = _median_absolute_deviation(finite)
    if rough_mad > 0.0:
        center = median(finite)
        noise_pool = [value for value in finite if abs(value - center) <= 6.0 * rough_mad]
        if len(noise_pool) >= 8:
            sigma = 1.4826 * _median_absolute_deviation(noise_pool)
            if sigma > 0.0:
                return sigma
    diffs = [abs(finite[idx + 1] - finite[idx]) for idx in range(len(finite) - 1)]
    if diffs:
        # First differences of white noise carry σ·√2; recover σ from their
        # MAD so a slowly drifting baseline cannot masquerade as noise.
        return max(0.0, 1.4826 * median(diffs) / math.sqrt(2.0))
    return 0.0


def _sensitivity_to_noise_factor(sensitivity: float) -> float:
    """Map the ``sensitivity`` knob onto an SNR (noise-factor) multiplier.

    Detection rejects anything that does not rise at least noise_factor·σ
    above the baseline — the directly noise-referenced criterion Mnova calls
    the "noise factor". A larger ``sensitivity`` yields a larger multiplier
    (fewer, higher-confidence peaks), preserving the direction of the legacy
    knob so the structure-guided tuning sweep keeps its ordering.
    """
    sensitivity = min(max(sensitivity, 0.02), 0.45)
    return min(12.0, max(3.0, 3.0 + sensitivity * 24.0))


def _in_priority_region(value: float, regions: tuple[tuple[float, float], ...]) -> bool:
    """True when ``value`` (ppm) falls inside any ``(lo, hi)`` priority window."""
    return any(lo <= value <= hi for lo, hi in regions)


def _infer_peak_estimates(
    points: list[tuple[float, float]],
    *,
    sensitivity: float = 0.12,
    frequency_mhz: float | None = None,
    priority_regions: tuple[tuple[float, float], ...] = (),
    deconvolve: bool = False,
) -> list[_PeakEstimate]:
    """Detect peaks from a processed / FID-derived intensity trace.

    Peaks are local maxima that rise an SNR-scaled amount above the noise
    floor: the threshold is ``noise_factor · σ``, where σ is the robust
    1.4826·MAD noise estimate of the baseline-corrected trace. This replaces
    the former fraction-of-the-dynamic-range cut, which scaled with the
    tallest peak and therefore both missed genuine weak signals and admitted
    noise spikes. ``priority_regions`` are compound-class-diagnostic ppm
    windows that receive a more sensitive (lower) threshold so weak diagnostic
    peaks there are not missed.
    """
    if len(points) < 3:
        return []
    ordered = sorted(points, key=lambda item: item[0], reverse=True)
    x_vals = [x for x, _ in ordered]
    sensitivity = min(max(sensitivity, 0.02), 0.45)
    # Baseline-correct once: the unclipped result feeds an unbiased noise
    # estimate; the zero-clipped result is the detection / integration trace
    # (identical to the previous _baseline_correct output).
    corrected, _baseline_meta = _robust_polynomial_baseline_correct(
        [float(y) for _, y in ordered], orient_positive=True
    )
    if len(corrected) < 3:
        return []
    short_trace = len(corrected) < 25
    smoothing_window = 1 if short_trace else 5 if len(corrected) >= 1200 else 3
    detection_clipped = [max(0.0, value) for value in corrected]
    y_smoothed = _smooth(detection_clipped, window=smoothing_window)
    lo = min(y_smoothed)
    hi = max(y_smoothed)
    if math.isclose(hi, lo):
        return []

    # SNR detection threshold. σ is measured on the *unclipped* trace under
    # the same smoothing as the detection array so the two share a scale.
    noise_sigma = 0.0 if short_trace else _estimate_noise_sigma(_smooth(corrected, window=smoothing_window))
    baseline_level = median(y_smoothed)
    if noise_sigma > 0.0:
        noise_factor = _sensitivity_to_noise_factor(sensitivity)
        threshold = baseline_level + noise_factor * noise_sigma
        # Inside compound-class-diagnostic windows, drop to a more sensitive
        # SNR cut (floored at 3σ, the classic detection limit) so weak
        # diagnostic peaks are not lost; the rest of the trace is unchanged.
        region_threshold = baseline_level + max(3.0, noise_factor * 0.6) * noise_sigma
    else:
        # Flat / noise-free trace: fall back to a minimal relative cut.
        threshold = lo + 0.02 * (hi - lo)
        region_threshold = threshold

    components: list[_PeakComponent] = []
    for idx in range(1, len(y_smoothed) - 1):
        center = y_smoothed[idx]
        local_threshold = (
            region_threshold
            if priority_regions and _in_priority_region(x_vals[idx], priority_regions)
            else threshold
        )
        if center < local_threshold:
            continue
        if center < y_smoothed[idx - 1] or center < y_smoothed[idx + 1]:
            continue

        left = idx - 1
        while left > 0 and y_smoothed[left] >= y_smoothed[left - 1]:
            left -= 1
            if idx - left > 40:
                break
        right = idx + 1
        while right < len(y_smoothed) - 1 and y_smoothed[right] >= y_smoothed[right + 1]:
            right += 1
            if right - idx > 40:
                break

        base = min(y_smoothed[left], y_smoothed[right])
        area = 0.0
        for j in range(left, right + 1):
            area += max(0.0, y_smoothed[j] - base)
        if area <= 0.0:
            continue
        components.append(
            _PeakComponent(
                shift_ppm=x_vals[idx],
                area=area,
                intensity=center,
                left_index=left,
                apex_index=idx,
                right_index=right,
            )
        )

    components.sort(key=lambda peak: peak.shift_ppm, reverse=True)
    filtered_components: list[_PeakComponent] = []
    min_component_sep = max(_ppm_step(x_vals) * 4, 0.008)
    for component in components:
        if filtered_components and abs(filtered_components[-1].shift_ppm - component.shift_ppm) < min_component_sep:
            if component.intensity > filtered_components[-1].intensity:
                filtered_components[-1] = component
            continue
        filtered_components.append(component)

    return _cluster_peak_components(
        filtered_components,
        x_vals,
        sensitivity=sensitivity,
        frequency_mhz=frequency_mhz,
        detection_trace=detection_clipped,
        noise_sigma=noise_sigma,
        deconvolve=deconvolve,
    )


def _provisional_integrations(estimates: list[_PeakEstimate]) -> list[float]:
    if not estimates:
        return []
    nonzero_areas = [peak.area for peak in estimates if peak.area > 0]
    if not nonzero_areas:
        return []
    reference = max(min(nonzero_areas), max(nonzero_areas) * 0.08)
    return [max(0.2, peak.area / reference) for peak in estimates]


def _round_half_integrations(values: list[float], *, minimum: float = 0.5, maximum: float = 12.0) -> list[float]:
    rounded: list[float] = []
    for value in values:
        clipped = min(maximum, max(minimum, value))
        rounded.append(math.floor(clipped * 2 + 0.5) / 2)
    return rounded


def _normalize_integrations_to_target(values: list[float], target_total_h: float) -> list[float] | None:
    if not values:
        return []
    total = sum(values)
    target_units = int(round(target_total_h * 2))
    if total <= 0 or target_units <= 0 or target_units < len(values):
        return None

    scaled_units = [max(1.0, value / total * target_units) for value in values]
    base_units = [max(1, int(math.floor(value))) for value in scaled_units]
    residuals = [scaled - base for scaled, base in zip(scaled_units, base_units)]
    diff = target_units - sum(base_units)

    if diff > 0:
        order = sorted(range(len(base_units)), key=lambda idx: residuals[idx], reverse=True)
        cursor = 0
        while diff > 0 and order:
            base_units[order[cursor % len(order)]] += 1
            cursor += 1
            diff -= 1
    elif diff < 0:
        order = sorted(range(len(base_units)), key=lambda idx: residuals[idx])
        cursor = 0
        while diff < 0 and order:
            idx = order[cursor % len(order)]
            if base_units[idx] > 1:
                base_units[idx] -= 1
                diff += 1
            cursor += 1
            if cursor > len(order) * 3:
                break

    if sum(base_units) != target_units:
        return None
    return [units / 2 for units in base_units]


def _select_target_proton_count(
    *,
    expected_total_h: int | None,
    expected_non_labile_h: int | None,
    solvent: str | None,
) -> float | None:
    if expected_total_h is None and expected_non_labile_h is None:
        return None
    if (
        solvent
        and solvent.upper() == "D2O"
        and expected_non_labile_h is not None
        and expected_non_labile_h > 0
    ):
        return float(expected_non_labile_h)
    if expected_total_h is not None and expected_total_h > 0:
        return float(expected_total_h)
    if expected_non_labile_h is not None and expected_non_labile_h > 0:
        return float(expected_non_labile_h)
    return None


def _reference_assignments_to_peaks(assignments: list[ReferencePeakAssignment]) -> list[Peak]:
    return [assignment.as_peak() for assignment in assignments]


def _multiplicity_match(reference: str, extracted: str) -> bool:
    ref = normalize_multiplicity(reference)
    obs = normalize_multiplicity(extracted)
    return ref == obs or ref == "m" or obs == "m"


def _reference_shift_match(
    assignment: ReferencePeakAssignment,
    extracted_peak: Peak,
) -> tuple[str, float] | None:
    observed_shift = extracted_peak.shift_ppm
    if assignment.shift_start_ppm is not None and assignment.shift_end_ppm is not None:
        lo = min(assignment.shift_start_ppm, assignment.shift_end_ppm)
        hi = max(assignment.shift_start_ppm, assignment.shift_end_ppm)
        expanded_lo = lo - 0.03
        expanded_hi = hi + 0.03
        if expanded_lo <= observed_shift <= expanded_hi:
            delta = 0.0 if lo <= observed_shift <= hi else min(abs(observed_shift - lo), abs(observed_shift - hi))
            return ("matched", round(delta, 4))

    delta = abs(observed_shift - assignment.shift_ppm)
    if delta <= 0.08:
        return ("matched" if delta <= 0.03 else "shifted", round(delta, 4))
    return None


def _reference_integration_match(assignment: ReferencePeakAssignment, extracted_peak: Peak) -> bool:
    return abs(float(assignment.integration_h) - float(extracted_peak.integration_h)) <= 0.5


def _reference_coverage_matches(
    reference_assignments: list[ReferencePeakAssignment],
    extracted_peaks: list[Peak],
) -> list[tuple[ReferencePeakAssignment, list[Peak]]]:
    coverage: list[tuple[ReferencePeakAssignment, list[Peak]]] = []
    for assignment in reference_assignments:
        matching_peaks = [
            peak for peak in extracted_peaks if _reference_shift_match(assignment, peak) is not None
        ]
        coverage.append((assignment, matching_peaks))
    return coverage


def _apply_reference_multiplicity(
    peaks: list[Peak],
    reference_assignments: list[ReferencePeakAssignment],
) -> list[Peak]:
    """Adopt literature multiplicity + J for detected peaks matching the text.

    The pasted ¹H NMR text is authoritative for coupling pattern and J values;
    a local-maximum picker cannot reliably resolve overlapped multiplets
    without spectral deconvolution. Each detected peak within shift tolerance
    of a reference assignment therefore takes that assignment's multiplicity
    and J-list. Peaks with no reference match keep their geometric label, and
    the structure-vs-reference comparison is built *before* this step so its
    multiplicity statistics still reflect raw detection.
    """
    if not reference_assignments:
        return peaks
    updated: list[Peak] = []
    for peak in peaks:
        best: ReferencePeakAssignment | None = None
        best_delta: float | None = None
        for assignment in reference_assignments:
            match = _reference_shift_match(assignment, peak)
            if match is None:
                continue
            _status, delta = match
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best = assignment
        if best is None:
            updated.append(peak)
        else:
            updated.append(
                peak.model_copy(
                    update={
                        "multiplicity": best.multiplicity,
                        "j_values_hz": list(best.j_values_hz),
                    }
                )
            )
    return updated


def _build_reference_guided_nmr_text(
    *,
    reference_assignments: list[ReferencePeakAssignment],
    extracted_peaks: list[Peak],
    minimum_coverage_ratio: float = 0.75,
    minimum_covered_assignments: int = 4,
) -> tuple[str | None, int]:
    if not reference_assignments or not extracted_peaks:
        return (None, 0)

    coverage = _reference_coverage_matches(reference_assignments, extracted_peaks)
    covered_count = sum(1 for _, matches in coverage if matches)
    minimum_count = min(len(reference_assignments), minimum_covered_assignments)
    if covered_count < minimum_count:
        return (None, covered_count)

    coverage_ratio = covered_count / len(reference_assignments)
    if coverage_ratio < minimum_coverage_ratio:
        return (None, covered_count)

    # No-fabrication guard: echo only reference assignments an actual detected
    # peak covers. A reference peak with no detected signal must never appear
    # in the analysis text — that would fabricate a peak the spectrum never
    # showed, violating the detected-peaks-only evidence policy.
    return (
        ", ".join(assignment.raw_text for assignment, matches in coverage if matches),
        covered_count,
    )


def _build_spectrum_comparison(
    *,
    reference_assignments: list[ReferencePeakAssignment],
    extracted_peaks: list[Peak],
    structure_visible_h: float | None,
) -> SpectrumComparisonReport | None:
    if not reference_assignments:
        return None

    reference_peaks = _reference_assignments_to_peaks(reference_assignments)
    candidates: list[_ReferenceCandidateMatch] = []
    for ref_idx, assignment in enumerate(reference_assignments):
        for extracted_idx, extracted_peak in enumerate(extracted_peaks):
            shift_match = _reference_shift_match(assignment, extracted_peak)
            if shift_match is None:
                continue
            status, delta_ppm = shift_match
            candidates.append(
                _ReferenceCandidateMatch(
                    reference_index=ref_idx,
                    extracted_index=extracted_idx,
                    delta_ppm=delta_ppm,
                    status=status,
                    multiplicity_match=_multiplicity_match(assignment.multiplicity, extracted_peak.multiplicity),
                    integration_match=_reference_integration_match(assignment, extracted_peak),
                )
            )

    candidates.sort(
        key=lambda item: (
            item.delta_ppm,
            0 if item.status == "matched" else 1,
            item.reference_index,
            item.extracted_index,
        )
    )

    matched_reference: set[int] = set()
    matched_extracted: set[int] = set()
    matched_items: list[SpectrumPeakMatch] = []
    multiplicity_match_count = 0
    integration_match_count = 0
    shifted_count = 0
    total_shift_delta_ppm = 0.0
    shared_peak_match_count = 0

    for candidate in candidates:
        if candidate.reference_index in matched_reference or candidate.extracted_index in matched_extracted:
            continue
        assignment = reference_assignments[candidate.reference_index]
        extracted_peak = extracted_peaks[candidate.extracted_index]
        matched_reference.add(candidate.reference_index)
        matched_extracted.add(candidate.extracted_index)
        matched_items.append(
            SpectrumPeakMatch(
                reference_peak=assignment.as_peak(),
                extracted_peak=extracted_peak,
                reference_raw_text=assignment.raw_text,
                reference_shift_start_ppm=assignment.shift_start_ppm,
                reference_shift_end_ppm=assignment.shift_end_ppm,
                delta_ppm=candidate.delta_ppm,
                status="matched" if candidate.status == "matched" else "shifted",
                multiplicity_match=candidate.multiplicity_match,
                integration_match=candidate.integration_match,
            )
        )
        if candidate.multiplicity_match:
            multiplicity_match_count += 1
        if candidate.integration_match:
            integration_match_count += 1
        if candidate.status == "shifted":
            shifted_count += 1
        total_shift_delta_ppm += candidate.delta_ppm

    for candidate in candidates:
        if candidate.reference_index in matched_reference:
            continue
        assignment = reference_assignments[candidate.reference_index]
        extracted_peak = extracted_peaks[candidate.extracted_index]
        matched_reference.add(candidate.reference_index)
        matched_items.append(
            SpectrumPeakMatch(
                reference_peak=assignment.as_peak(),
                extracted_peak=extracted_peak,
                reference_raw_text=assignment.raw_text,
                reference_shift_start_ppm=assignment.shift_start_ppm,
                reference_shift_end_ppm=assignment.shift_end_ppm,
                delta_ppm=candidate.delta_ppm,
                status="matched" if candidate.status == "matched" else "shifted",
                multiplicity_match=candidate.multiplicity_match,
                integration_match=candidate.integration_match,
            )
        )
        if candidate.extracted_index not in matched_extracted:
            matched_extracted.add(candidate.extracted_index)
        else:
            shared_peak_match_count += 1
        if candidate.multiplicity_match:
            multiplicity_match_count += 1
        if candidate.integration_match:
            integration_match_count += 1
        if candidate.status == "shifted":
            shifted_count += 1
        total_shift_delta_ppm += candidate.delta_ppm

    missing_reference = [
        SpectrumMissingReferencePeak(
            reference_peak=assignment.as_peak(),
            reference_raw_text=assignment.raw_text,
            reference_shift_start_ppm=assignment.shift_start_ppm,
            reference_shift_end_ppm=assignment.shift_end_ppm,
        )
        for idx, assignment in enumerate(reference_assignments)
        if idx not in matched_reference
    ]
    extra_spectrum = [
        SpectrumExtraPeak(extracted_peak=peak)
        for idx, peak in enumerate(extracted_peaks)
        if idx not in matched_extracted
    ]

    reference_total_h = round(sum(peak.integration_h for peak in reference_peaks), 4)
    extracted_total_h = round(sum(peak.integration_h for peak in extracted_peaks), 4)
    reference_structure_delta_h = (
        round(reference_total_h - structure_visible_h, 4) if structure_visible_h is not None else None
    )
    extracted_structure_delta_h = (
        round(extracted_total_h - structure_visible_h, 4) if structure_visible_h is not None else None
    )
    reference_extracted_delta_h = round(reference_total_h - extracted_total_h, 4)
    structure_reference_mismatch = (
        reference_structure_delta_h is not None and abs(reference_structure_delta_h) > 0.5
    )
    structure_extracted_mismatch = (
        extracted_structure_delta_h is not None and abs(extracted_structure_delta_h) > 0.5
    )

    notes: list[str] = []
    if structure_reference_mismatch and structure_visible_h is not None:
        notes.append(
            f"Reference text integrates to {reference_total_h:g}H, while the structure/solvent target is {structure_visible_h:g} visible H."
        )
    if structure_extracted_mismatch and structure_visible_h is not None:
        notes.append(
            f"Extracted peaks integrate to {extracted_total_h:g}H, which differs from the structure/solvent target of {structure_visible_h:g} visible H."
        )
    if abs(reference_extracted_delta_h) > 0.5:
        notes.append(
            f"Reference and extracted peak lists differ by {abs(reference_extracted_delta_h):g}H in total integration."
        )
    if shared_peak_match_count:
        notes.append(
            f"{shared_peak_match_count} dense-region reference assignment(s) were covered by an extracted peak already used for a neighboring overlapping signal."
        )

    return SpectrumComparisonReport(
        matched=matched_items,
        missing_reference=missing_reference,
        extra_spectrum=extra_spectrum,
        matched_count=len(matched_items),
        shifted_count=shifted_count,
        missing_count=len(missing_reference),
        extra_count=len(extra_spectrum),
        multiplicity_match_count=multiplicity_match_count,
        integration_match_count=integration_match_count,
        total_shift_delta_ppm=round(total_shift_delta_ppm, 4),
        reference_total_h=reference_total_h,
        extracted_total_h=extracted_total_h,
        structure_visible_h=structure_visible_h,
        reference_structure_delta_h=reference_structure_delta_h,
        extracted_structure_delta_h=extracted_structure_delta_h,
        reference_extracted_delta_h=reference_extracted_delta_h,
        structure_reference_mismatch=structure_reference_mismatch,
        structure_extracted_mismatch=structure_extracted_mismatch,
        notes=notes,
    )


def _estimates_to_peaks(estimates: list[_PeakEstimate], *, target_total_h: float | None = None) -> tuple[list[Peak], dict[str, Any]]:
    if not estimates:
        return ([], {"raw_estimated_total_h": 0.0, "integration_normalized_to_target": False})
    raw_integrations = _provisional_integrations(estimates)
    if not raw_integrations:
        return ([], {"raw_estimated_total_h": 0.0, "integration_normalized_to_target": False})
    integrations = _round_half_integrations(raw_integrations, minimum=0.5)
    normalized_to_target = False
    raw_total_h = round(sum(raw_integrations), 3)
    if target_total_h is not None:
        normalized = _normalize_integrations_to_target(raw_integrations, target_total_h)
        if normalized:
            integrations = normalized
            normalized_to_target = True
    peaks: list[Peak] = []
    for est, integration in zip(estimates, integrations):
        peaks.append(
            Peak(
                shift_ppm=round(est.shift_ppm, 3),
                multiplicity=est.multiplicity,
                integration_h=integration,
                j_values_hz=list(est.j_values_hz),
            )
        )
    return (
        peaks,
        {
            "raw_estimated_total_h": raw_total_h,
            "integration_normalized_to_target": normalized_to_target,
        },
    )


def _peaks_to_nmr_text(peaks: list[Peak]) -> str:
    fragments: list[str] = []
    for peak in peaks:
        j_values = [round(float(value), 1) for value in peak.j_values_hz if float(value) > 0]
        j_text = f", J = {', '.join(f'{value:.1f}' for value in j_values)} Hz" if j_values else ""
        fragments.append(f"{peak.shift_ppm:.2f} ({peak.multiplicity}{j_text}, {peak.integration_h:g}H)")
    return ", ".join(fragments)


def _normalized_reference_peak_text(
    reference_peaks: list[Peak],
    *,
    target_total_h: float | None,
) -> str | None:
    if not reference_peaks:
        return None
    peaks = reference_peaks
    if target_total_h is not None:
        normalized = _normalize_integrations_to_target(
            [float(peak.integration_h) for peak in reference_peaks],
            target_total_h,
        )
        if normalized:
            peaks = [
                peak.model_copy(update={"integration_h": integration})
                for peak, integration in zip(reference_peaks, normalized)
            ]
    return _peaks_to_nmr_text(peaks)


def _peak_identity(peak: Peak) -> tuple[float, str, float]:
    return (
        round(float(peak.shift_ppm), 3),
        normalize_multiplicity(peak.multiplicity),
        round(float(peak.integration_h), 1),
    )


def _nearest_peak_gap(peaks: list[Peak], index: int) -> float:
    deltas: list[float] = []
    if index > 0:
        deltas.append(abs(float(peaks[index].shift_ppm) - float(peaks[index - 1].shift_ppm)))
    if index + 1 < len(peaks):
        deltas.append(abs(float(peaks[index].shift_ppm) - float(peaks[index + 1].shift_ppm)))
    return min(deltas) if deltas else 99.0


def _build_impurity_candidates(
    peaks: list[Peak],
    solvent: str | None,
    comparison: SpectrumComparisonReport | None = None,
    target_total_h: float | None = None,
) -> list[dict[str, Any]]:
    if not peaks:
        return []
    key = _normalize_solvent_key(solvent)
    windows = _SOLVENT_MASK_WINDOWS.get(key or "", [])
    extra_peak_keys = {
        _peak_identity(item.extracted_peak)
        for item in (comparison.extra_spectrum if comparison is not None else [])
    }
    library_candidates: list[dict[str, Any]] = []
    seen_library: set[tuple[float, str]] = set()
    for peak in peaks:
        for match in match_h1_impurity_shifts(peak.shift_ppm, solvent):
            key_tuple = (round(peak.shift_ppm, 3), str(match["label"]))
            if key_tuple in seen_library:
                continue
            seen_library.add(key_tuple)
            library_candidates.append(
                {
                    "shift_ppm": round(peak.shift_ppm, 3),
                    "integration_h": peak.integration_h,
                    "reason": (
                        f"matches embedded H-1 impurity shift for {match['label']} "
                        f"({match['expected_ppm']} ppm)"
                    ),
                    "library_match": match,
                    "score": 5 if match.get("kind") in {"residual", "water"} else 4,
                }
            )
    extracted_total_h = round(sum(float(peak.integration_h) for peak in peaks), 4)
    if not extra_peak_keys and target_total_h is not None and abs(extracted_total_h - float(target_total_h)) <= 0.5:
        return []
    candidates: list[dict[str, Any]] = list(library_candidates)
    max_integration = max(p.integration_h for p in peaks) if peaks else 1.0
    ordered_peaks = sorted(peaks, key=lambda peak: float(peak.shift_ppm), reverse=True)
    for index, peak in enumerate(ordered_peaks):
        if any(_in_window(peak.shift_ppm, low, high) for low, high, _ in windows):
            continue
        peak_key = _peak_identity(peak)
        if extra_peak_keys and peak_key not in extra_peak_keys:
            continue

        normalized_mult = normalize_multiplicity(peak.multiplicity)
        nearest_gap = _nearest_peak_gap(ordered_peaks, index)
        integration = float(peak.integration_h)
        score = 0
        reason_bits: list[str] = []

        if peak_key in extra_peak_keys:
            score += 3
            reason_bits.append("unmatched vs reference")
        if integration <= 0.5:
            score += 3
            reason_bits.append("trace-level integration")
        elif integration <= 1.0:
            score += 2
            reason_bits.append("low integration")
        elif integration <= 0.15 * max_integration:
            score += 1
        if normalized_mult in {"s", "br s"}:
            score += 2
            reason_bits.append("isolated singlet-like pattern")
        elif normalized_mult == "m":
            score -= 1
        if nearest_gap >= 0.18:
            score += 2
            reason_bits.append("well separated from neighboring peaks")
        elif nearest_gap >= 0.12:
            score += 1
        else:
            score -= 1
        if 2.6 <= float(peak.shift_ppm) <= 4.2 and peak_key not in extra_peak_keys:
            score -= 2
        if integration > 1.0 and peak_key not in extra_peak_keys:
            score -= 1

        if score < 4:
            continue

        if peak_key in extra_peak_keys:
            reason = "high-likelihood extra signal relative to the reference peak list"
        elif reason_bits:
            reason = "; ".join(reason_bits[:2])
        else:
            reason = "high-likelihood impurity candidate"
        candidate = {
            "shift_ppm": round(peak.shift_ppm, 3),
            "integration_h": peak.integration_h,
            "reason": reason,
            "score": score,
        }
        if not any(
            math.isclose(float(existing["shift_ppm"]), float(candidate["shift_ppm"]), abs_tol=0.001)
            for existing in candidates
        ):
            candidates.append(candidate)
    candidates.sort(key=lambda item: (-int(item["score"]), float(item["integration_h"]), float(item["shift_ppm"])))
    trimmed = candidates[:6]
    for candidate in trimmed:
        candidate.pop("score", None)
    return trimmed


def _structure_guided_peak_estimates(
    points: list[tuple[float, float]],
    *,
    reference_assignments: list[ReferencePeakAssignment],
    reference_peaks: list[Peak],
    target_total_h: float | None,
    frequency_mhz: float | None,
    fixed_sensitivity: float | None = None,
    priority_regions: tuple[tuple[float, float], ...] = (),
) -> tuple[list[_PeakEstimate], SpectrumComparisonReport | None, float]:
    """Detect peaks with a structure / reference-guided sensitivity sweep.

    Each candidate SNR sensitivity is run through the noise-based detector, the
    resulting peak list is scored against the reference assignments (coverage,
    missing / extra peaks, shift agreement, multiplicity match, visible-H
    error), and the best-scoring candidate wins. ``fixed_sensitivity`` collapses
    the sweep to a single explicit value; ``priority_regions`` are forwarded to
    the detector as compound-class-diagnostic windows. Returns the winning
    estimates, the comparison computed for that candidate, and the sensitivity
    chosen — shared by the processed-upload and Raw-FID paths so both detect
    peaks identically.
    """
    sensitivity_candidates = (
        [fixed_sensitivity]
        if fixed_sensitivity is not None
        else [0.06, 0.08, 0.1, 0.12, 0.15]
    )
    max_reasonable_peaks = (
        max(12, int(target_total_h) + 4) if target_total_h is not None else 18
    )
    best_estimates: list[_PeakEstimate] = []
    best_sensitivity = float(sensitivity_candidates[0])
    best_comparison: SpectrumComparisonReport | None = None
    best_key: tuple[float, ...] | None = None

    for sensitivity_candidate in sensitivity_candidates:
        estimates = _infer_peak_estimates(
            points,
            sensitivity=sensitivity_candidate,
            frequency_mhz=frequency_mhz,
            priority_regions=priority_regions,
        )
        candidate_peaks, _ = _estimates_to_peaks(estimates, target_total_h=target_total_h)
        observed_total = round(sum(peak.integration_h for peak in candidate_peaks), 4)
        candidate_target_total = (
            target_total_h
            if target_total_h is not None
            else (
                round(sum(peak.integration_h for peak in reference_peaks), 4)
                if reference_peaks
                else None
            )
        )
        visible_total_error = (
            abs(observed_total - candidate_target_total)
            if candidate_target_total is not None
            else 0.0
        )
        peak_penalty = max(0, len(candidate_peaks) - max_reasonable_peaks) * 0.2
        candidate_reference_coverage = sum(
            1
            for _, matches in _reference_coverage_matches(reference_assignments, candidate_peaks)
            if matches
        )
        candidate_comparison = _build_spectrum_comparison(
            reference_assignments=reference_assignments,
            extracted_peaks=candidate_peaks,
            structure_visible_h=target_total_h,
        )
        if candidate_comparison is not None:
            key: tuple[float, ...] = (
                float(len(reference_assignments) - candidate_reference_coverage),
                float(candidate_comparison.missing_count),
                float(candidate_comparison.extra_count),
                candidate_comparison.total_shift_delta_ppm,
                round(visible_total_error, 4),
                float(-candidate_comparison.multiplicity_match_count),
                float(sensitivity_candidate),
            )
        else:
            key = (
                round(visible_total_error + peak_penalty, 4),
                float(-len(candidate_peaks)),
                float(sensitivity_candidate),
            )
        if best_key is None or key < best_key:
            best_key = key
            best_estimates = estimates
            best_sensitivity = float(sensitivity_candidate)
            best_comparison = candidate_comparison

    # GSD runs once, on the winning candidate only — Lorentzian deconvolution
    # is far too costly to repeat for every sweep candidate, and it changes
    # only multiplicity / J, never the peak shifts the sweep scores against.
    if best_estimates:
        best_estimates = _infer_peak_estimates(
            points,
            sensitivity=best_sensitivity,
            frequency_mhz=frequency_mhz,
            priority_regions=priority_regions,
            deconvolve=True,
        )
    return best_estimates, best_comparison, best_sensitivity


def parse_processed_spectrum(
    *,
    filename: str,
    content: bytes,
    solvent: str | None = None,
    frequency_mhz: float | None = None,
    reference_ppm: float | None = None,
    reference_nmr_text: str | None = None,
    peak_sensitivity: float | None = None,
    mask_solvent_regions: bool = False,
    expected_total_h: int | None = None,
    expected_non_labile_h: int | None = None,
    compound_class: str | None = None,
    display_mode: str = "real",
    vertical_gain: float = 1.0,
    debug_preview: bool = False,
    max_preview_points: int = 1200,
    processed_baseline_correction: str = "bernstein",
    processed_baseline_order: int = 3,
    infer_peaks: bool = True,
) -> SpectrumPreviewReport:
    ext = _detect_text_extension(filename)
    text = _strip_bom(content.decode("utf-8", errors="replace"))
    warnings: list[str] = []

    if ext in _TEXT_SPECTRUM_EXTENSIONS:
        source_mode, peaks, points, parse_warnings = _parse_csv_or_tsv(filename, text)
        warnings.extend(parse_warnings)
    elif ext in _JCAMP_SPECTRUM_EXTENSIONS:
        points = _parse_jcamp_text(text)
        peaks = []
        source_mode = "trace"
        warnings.append(
            "JCAMP-DX support is currently limited to simple XY-style exports; more complex vendor-specific encodings may require a fuller parser."
        )
    else:
        raise SpectrumParseError(
            "Unsupported processed spectrum format. Upload CSV, TSV, TXT, XY, ASC, DAT, JCAMP, JDX, or DX for this phase."
        )

    original_points = points[:]
    if source_mode == "trace":
        points, processed_baseline_metadata, warnings = apply_processed_trace_baseline_conditions(
            points,
            mode=processed_baseline_correction,
            order=processed_baseline_order,
            warnings=warnings,
            label="processed-file 1H",
        )
    else:
        processed_baseline_mode = normalize_baseline_mode(processed_baseline_correction)
        processed_baseline_metadata = {
            "mode": processed_baseline_mode,
            "method": processed_baseline_mode,
            "order": int(processed_baseline_order or 3),
            "correction_applied": False,
            "explicit": False,
        }

    sensitivity = 0.12 if peak_sensitivity is None else float(peak_sensitivity)
    target_total_h = _select_target_proton_count(
        expected_total_h=expected_total_h,
        expected_non_labile_h=expected_non_labile_h,
        solvent=solvent,
    )
    peak_meta: dict[str, Any] = {"raw_estimated_total_h": 0.0, "integration_normalized_to_target": False}
    reference_nmr_text_normalized: str | None = None
    reference_assignments: list[ReferencePeakAssignment] = []
    reference_peaks: list[Peak] = []
    comparison: SpectrumComparisonReport | None = None
    reference_guided_nmr_text: str | None = None
    reference_coverage_count = 0
    raw_display_mode = (
        str(display_mode or "real").strip().lower().replace("-", "_").replace(" ", "_")
    )
    deprecated_display_modes = {
        "mnova",
        "mnova_locked",
        "mnova-style",
        "mnova_style",
        "asinh",
        "locked",
        "baseline_locked",
    }
    display_mode_aliases = {
        "weak_peak_magnifier": "magnifier",
        "weak_peak_magnifier_view": "magnifier",
    }
    if raw_display_mode in display_mode_aliases:
        normalized_display_mode = display_mode_aliases[raw_display_mode]
    elif raw_display_mode in deprecated_display_modes:
        warnings.append(
            f"Deprecated display_mode='{raw_display_mode}' was mapped to real spectrum mode; "
            "the main preview trace preserves original intensity values."
        )
        normalized_display_mode = "real"
    elif raw_display_mode not in {"real", "magnifier"}:
        warnings.append(
            f"Unknown display_mode='{raw_display_mode}' was mapped to real spectrum mode."
        )
        normalized_display_mode = "real"
    else:
        normalized_display_mode = raw_display_mode
    viewer_gain = max(1.0, min(float(vertical_gain or 1.0), 1_000_000.0))
    preview_limit = max(100, min(int(max_preview_points or 1200), 5000))
    smoothing_allowed = normalize_baseline_mode(processed_baseline_correction) not in {"none", "preserve"}
    display_points = points
    display_meta: dict[str, Any] = {
        "baseline_smoothing": {
            "applied": False,
            "method": "disabled_real_spectrum_default",
            "display_points_corrected": False,
        },
        "display_solvent_masked": False,
    }
    if source_mode == "trace":
        display_points, display_meta, display_notes = _prepare_trace_display_points(
            points,
            solvent=solvent,
            mask_solvent_regions=mask_solvent_regions,
            nucleus="1H",
            baseline_already_corrected=bool(
                processed_baseline_metadata.get("correction_applied")
            ),
        )
        if smoothing_allowed:
            display_points, trace_smoothing_meta = smooth_trace_display_points(
                display_points,
                nucleus="1H",
            )
        else:
            trace_smoothing_meta = {
                "applied": False,
                "display_only": True,
                "evidence_trace_preserved": True,
                "method": "none",
                "reason": "uploaded_processed_trace_preserved",
            }
        display_meta["trace_smoothing"] = trace_smoothing_meta
        if trace_smoothing_meta.get("applied"):
            display_meta["note"] = (
                "Processed 1H preview points use display-only trace smoothing after "
                "automatic baseline correction. Peak picking and evidence scoring "
                "use the corrected unsmoothed evidence trace."
            )
        warnings.extend(note for note in display_notes if note not in warnings)
    else:
        display_meta["trace_smoothing"] = {
            "applied": False,
            "display_only": True,
            "evidence_trace_preserved": True,
            "method": "none",
            "reason": "peak_table_source",
        }

    if not infer_peaks:
        preview_points = _downsample_processed_display_points(display_points, limit=preview_limit)
        warnings = [
            warning
            for warning in warnings
            if warning != "Spectrum trace detected; peaks and integrations were inferred heuristically from intensity data."
        ]
        warnings.append("Display preview generated without peak inference; use Analyze to run peak detection and evidence scoring.")
        if solvent:
            warnings.append(f"The uploaded spectrum will be interpreted using the supplied solvent context: {solvent}.")
        if frequency_mhz is not None:
            warnings.append(f"Instrument frequency provided: {frequency_mhz:g} MHz.")
        if reference_ppm is not None:
            warnings.append(f"Reference calibration provided: {reference_ppm:g} ppm.")
        return SpectrumPreviewReport(
            filename=filename,
            format_detected=ext or "unknown",
            source_mode=source_mode,
            point_count=len(points),
            preview_points=preview_points,
            inferred_peaks=[],
            inferred_nmr_text="",
            reference_nmr_text_normalized=None,
            reference_peaks=[],
            comparison=None,
            warnings=warnings,
            metadata={
                "solvent": solvent,
                "frequency_mhz": frequency_mhz,
                "reference_ppm": reference_ppm,
                "reference_peak_count": 0,
                "reference_total_h": 0.0,
                "reference_coverage_count": 0,
                "reference_guided_text_used": False,
                "raw_extracted_nmr_text": "",
                "peak_sensitivity": sensitivity,
                "peak_sensitivity_percent": round(sensitivity * 100),
                "peak_inference": "skipped_for_display_preview",
                "peak_inference_skipped": True,
                "target_total_h": expected_total_h,
                "target_non_labile_h": expected_non_labile_h,
                "target_visible_h": target_total_h,
                "mask_solvent_regions": mask_solvent_regions,
                "processed_baseline_correction": processed_baseline_metadata,
                "baseline_flatness_qa": _preview_baseline_flatness_qa(
                    preview_points,
                    mode=processed_baseline_metadata.get("method") or "processed",
                ),
                "impurity_candidates": [],
                "display_preprocessing": display_meta,
                "evidence_trace_mode": (
                    "uploaded_intensity_baseline_corrected"
                    if processed_baseline_metadata.get("correction_applied")
                    else "uploaded_intensity"
                ),
                "display_mode": normalized_display_mode,
                "display_gain": viewer_gain,
                "baseline_lock_visual_only": True,
                "display": {
                    "mode": normalized_display_mode,
                    "gain": viewer_gain,
                    "vertical_gain": viewer_gain,
                    "baseline_lock_visual_only": True,
                    "main_trace": (
                        "display_smoothed_evidence_intensity"
                        if display_meta.get("trace_smoothing", {}).get("applied")
                        else "original_evidence_intensity"
                    ),
                    "trace_smoothing": display_meta.get("trace_smoothing"),
                    "weak_peak_magnifier": False,
                    "downsampling": {
                        "method": _PROCESSED_DISPLAY_DOWNSAMPLING_METHOD,
                        "point_limit": preview_limit,
                    },
                },
                "preview_downsampling": {
                    "method": _PROCESSED_DISPLAY_DOWNSAMPLING_METHOD,
                    "point_limit": preview_limit,
                    "source_point_count": len(points),
                },
                "preview_fast_path": True,
                "original_spectrum_state": _build_preview_spectrum_state(
                    original_points,
                    preview_points,
                    source="uploaded_peak_table" if source_mode == "peak_table" else "uploaded_trace",
                    processing_stage="as_uploaded",
                ),
                **(
                    {"raw_preview_points": [point.model_dump(mode="json") for point in preview_points]}
                    if debug_preview
                    else {}
                ),
                **peak_meta,
            },
        )

    if reference_nmr_text and reference_nmr_text.strip():
        try:
            reference_nmr_text_normalized, reference_assignments = parse_reference_nmr_text(reference_nmr_text)
            reference_peaks = _reference_assignments_to_peaks(reference_assignments)
            warnings.append("Reference 1H NMR text was normalized and will be used as a comparison target during peak picking.")
        except Exception as exc:
            try:
                reference_nmr_text_normalized = normalize_nmr_text(reference_nmr_text)
            except Exception:
                reference_nmr_text_normalized = reference_nmr_text.strip()
            warnings.append(f"Reference 1H NMR text could not be parsed: {exc}")

    if source_mode == "peak_table":
        inferred_peaks = peaks
        comparison = _build_spectrum_comparison(
            reference_assignments=reference_assignments,
            extracted_peaks=inferred_peaks,
            structure_visible_h=target_total_h,
        )
        impurity_candidates = _build_impurity_candidates(
            inferred_peaks,
            solvent,
            comparison=comparison,
            target_total_h=target_total_h,
        )
    else:
        inference_points = points
        if mask_solvent_regions:
            inference_points, mask_notes = _apply_solvent_mask(points, solvent)
            warnings.extend(mask_notes)
        if normalized_display_mode == "magnifier":
            magnifier = weak_peak_magnifier_view(
                points,
                visual_gain=max(viewer_gain, 2.0),
            )
            display_meta["weak_peak_magnifier"] = {
                **magnifier.metadata,
                "points": _serialized_downsampled_points(
                    magnifier.points,
                    limit=min(preview_limit, 700),
                ),
            }
            warnings.extend(note for note in magnifier.warnings if note not in warnings)
        best_estimates, best_comparison, sensitivity = _structure_guided_peak_estimates(
            inference_points,
            reference_assignments=reference_assignments,
            reference_peaks=reference_peaks,
            target_total_h=target_total_h,
            frequency_mhz=frequency_mhz,
            fixed_sensitivity=float(peak_sensitivity) if peak_sensitivity is not None else None,
            priority_regions=diagnostic_regions_for(compound_class, "1H"),
        )
        inferred_peaks, peak_meta = _estimates_to_peaks(best_estimates, target_total_h=target_total_h)
        comparison = best_comparison or _build_spectrum_comparison(
            reference_assignments=reference_assignments,
            extracted_peaks=inferred_peaks,
            structure_visible_h=target_total_h,
        )
        # Adopt literature multiplicity / J for reference-matched peaks (the
        # comparison above is intentionally built first, on raw detection).
        inferred_peaks = _apply_reference_multiplicity(inferred_peaks, reference_assignments)
        impurity_candidates = _build_impurity_candidates(
            inferred_peaks,
            solvent,
            comparison=comparison,
            target_total_h=target_total_h,
        )
        if not inferred_peaks:
            warnings.append("No peaks could be inferred from the uploaded trace using the current heuristic peak picker.")
        else:
            warnings.append(
                "Peak positions and integrations were inferred heuristically from processed intensity data and should be reviewed manually before final interpretation."
            )
            if target_total_h is not None:
                warnings.append(
                    "Peak picking was auto-tuned against the supplied structure so weaker signals can be lifted and matched more closely to the expected 1H count."
                )
            if comparison is not None:
                warnings.append("Reference-text comparison was applied to score peak-picking candidates and summarize mismatches.")

    if impurity_candidates:
        warnings.append(f"{len(impurity_candidates)} minor peak(s) were flagged as possible impurity candidates for manual review.")
    if solvent:
        warnings.append(f"The uploaded spectrum will be interpreted using the supplied solvent context: {solvent}.")
    if frequency_mhz is not None:
        warnings.append(f"Instrument frequency provided: {frequency_mhz:g} MHz.")
    if reference_ppm is not None:
        warnings.append(f"Reference calibration provided: {reference_ppm:g} ppm.")
    if comparison is not None:
        warnings.extend(note for note in comparison.notes if note not in warnings)

    raw_inferred_nmr_text = _peaks_to_nmr_text(inferred_peaks) if inferred_peaks else ""
    if reference_assignments and inferred_peaks:
        reference_guided_nmr_text, reference_coverage_count = _build_reference_guided_nmr_text(
            reference_assignments=reference_assignments,
            extracted_peaks=inferred_peaks,
        )
        if reference_guided_nmr_text is not None:
            warnings.append(
                "Reference-guided assignment text was emitted for overlapping regions so the generated peak list can preserve recognized shift ranges and multiplicities."
            )
        else:
            warnings.append(
                "Reference NMR text was used for comparison and scoring only; generated assignments were not emitted because independently detected peaks did not cover enough referenced regions."
            )

    original_spectrum_state = _build_preserved_spectrum_state(
        original_points,
        source="uploaded_peak_table" if source_mode == "peak_table" else "uploaded_trace",
        processing_stage="as_uploaded",
        point_limit=preview_limit,
    )

    return SpectrumPreviewReport(
        filename=filename,
        format_detected=ext or "unknown",
        source_mode=source_mode,
        point_count=len(points),
        preview_points=_downsample_processed_display_points(display_points, limit=preview_limit),
        inferred_peaks=inferred_peaks,
        inferred_nmr_text=reference_guided_nmr_text or raw_inferred_nmr_text,
        reference_nmr_text_normalized=reference_nmr_text_normalized,
        reference_peaks=reference_peaks,
        comparison=comparison,
        warnings=warnings,
        metadata={
            "solvent": solvent,
            "frequency_mhz": frequency_mhz,
            "reference_ppm": reference_ppm,
            "reference_peak_count": len(reference_peaks),
            "reference_total_h": round(sum(peak.integration_h for peak in reference_peaks), 4) if reference_peaks else 0.0,
            "reference_coverage_count": reference_coverage_count,
            "reference_guided_text_used": reference_guided_nmr_text is not None,
            "reference_guided_text_abstained": bool(reference_assignments) and reference_guided_nmr_text is None,
            "raw_extracted_nmr_text": raw_inferred_nmr_text,
            "peak_evidence_policy": "detected_peaks_only_no_reference_fabrication",
            "peak_sensitivity": sensitivity,
            "peak_sensitivity_percent": round(sensitivity * 100),
            "peak_inference": "enabled",
            "peak_inference_skipped": False,
            "target_total_h": expected_total_h,
            "target_non_labile_h": expected_non_labile_h,
            "target_visible_h": target_total_h,
            "mask_solvent_regions": mask_solvent_regions,
            "processed_baseline_correction": processed_baseline_metadata,
            "baseline_flatness_qa": evaluate_baseline_flatness(
                points,
                mode=processed_baseline_metadata.get("method") or "processed",
            ).as_dict(),
            "impurity_candidates": impurity_candidates,
            "display_preprocessing": display_meta,
            "evidence_trace_mode": (
                "uploaded_intensity_baseline_corrected"
                if processed_baseline_metadata.get("correction_applied")
                else "uploaded_intensity"
            ),
            "display_mode": normalized_display_mode,
            "display_gain": viewer_gain,
            "baseline_lock_visual_only": True,
            "display": {
                "mode": normalized_display_mode,
                "gain": viewer_gain,
                "vertical_gain": viewer_gain,
                "baseline_lock_visual_only": True,
                "main_trace": (
                    "display_smoothed_evidence_intensity"
                    if display_meta.get("trace_smoothing", {}).get("applied")
                    else "original_evidence_intensity"
                ),
                "trace_smoothing": display_meta.get("trace_smoothing"),
                "weak_peak_magnifier": normalized_display_mode == "magnifier",
                "downsampling": {
                    "method": _PROCESSED_DISPLAY_DOWNSAMPLING_METHOD,
                    "point_limit": preview_limit,
                },
            },
            "preview_downsampling": {
                "method": _PROCESSED_DISPLAY_DOWNSAMPLING_METHOD,
                "point_limit": preview_limit,
                "source_point_count": len(points),
            },
            "original_spectrum_state": original_spectrum_state,
            **(
                {"raw_preview_points": _serialized_downsampled_points(points, limit=preview_limit)}
                if debug_preview
                else {}
            ),
            **peak_meta,
        },
    )
