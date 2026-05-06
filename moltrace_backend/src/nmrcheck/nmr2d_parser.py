from __future__ import annotations

import csv
import io
import json
import math
import re
from pathlib import Path
from typing import Any

from .nmr2d_models import NMR2DContourPoint, NMR2DExperiment, NMR2DPeak, NMR2DPreview

_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_H_MIN, _H_MAX = -2.5, 16.5
_C_MIN, _C_MAX = -10.0, 240.0
_EXPERIMENT_ALIASES = {
    "cosy": "COSY",
    "1h-1h": "COSY",
    "h-h": "COSY",
    "hsqc": "HSQC",
    "hmqc": "HMQC",
    "hmbc": "HMBC",
}
_EXPERIMENT_KEYS = ("experiment", "exp", "type", "experiment_type", "spectrum")
_F2_DIRECT_KEYS = (
    "f2_ppm",
    "f2",
    "h_ppm",
    "proton_ppm",
    "direct_ppm",
    "x1_ppm",
    "ppm_h",
    "x1",
    "h",
)
_F1_INDIRECT_KEYS = (
    "f1_ppm",
    "f1",
    "h2_ppm",
    "proton2_ppm",
    "carbon_ppm",
    "c_ppm",
    "indirect_ppm",
    "x2_ppm",
    "ppm_c",
    "x2",
    "c",
)
_INTENSITY_KEYS = ("intensity", "height", "amplitude")
_VOLUME_KEYS = ("volume", "area", "integral")
_ASSIGNMENT_KEYS = ("assignment", "label", "annotation")
_DUPLICATE_TOLERANCE_PPM = 0.015
_DEFAULT_MATRIX_POINT_LIMIT = 2_000


class NMR2DParseError(ValueError):
    pass


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _normalize_experiment(value: Any, *, filename: str = "", fallback: str | None = None) -> NMR2DExperiment | None:
    text = str(value or fallback or filename or "").strip().lower()
    for key, label in _EXPERIMENT_ALIASES.items():
        if key in text:
            return label  # type: ignore[return-value]
    return None


def _sniff_delimiter(text: str, filename: str) -> str:
    if filename.lower().endswith(".tsv"):
        return "\t"
    sample = "\n".join(text.splitlines()[:10])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except Exception:
        return "\t" if "\t" in sample else (";" if ";" in sample else ",")


def _rows_from_upload(filename: str, content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8", errors="replace").lstrip("\ufeff")
    if not text.strip():
        raise NMR2DParseError("2D NMR upload is empty.")
    suffix = Path(filename.lower()).suffix
    if suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise NMR2DParseError("Invalid JSON 2D NMR peak table.") from exc
        if isinstance(payload, dict):
            payload = payload.get("peaks") or payload.get("cross_peaks") or payload.get("points")
        if not isinstance(payload, list):
            raise NMR2DParseError("2D NMR JSON must be a list or an object with peaks/cross_peaks.")
        return [row for row in payload if isinstance(row, dict)]
    delimiter = _sniff_delimiter(text, filename)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames:
        return list(reader)
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        values = [float(x) for x in _FLOAT_RE.findall(line)]
        if len(values) >= 2:
            rows.append({"f1": values[0], "f2": values[1], "intensity": values[2] if len(values) > 2 else None})
    return rows


def _json_payload(filename: str, content: bytes) -> Any | None:
    if Path(filename.lower()).suffix != ".json":
        return None
    text = content.decode("utf-8", errors="replace").lstrip("\ufeff")
    if not text.strip():
        raise NMR2DParseError("2D NMR upload is empty.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise NMR2DParseError("Invalid JSON 2D NMR upload.") from exc


def _is_json_matrix_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("f2_axis"), list)
        and isinstance(payload.get("f1_axis"), list)
        and isinstance(payload.get("intensity"), list)
    )


def _row_value(row: dict[str, Any], *keys: str) -> Any:
    normalized = {_norm_key(str(key)): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(_norm_key(key))
        if value not in {None, ""}:
            return value
    return None


def _has_any_key(row: dict[str, Any], keys: tuple[str, ...]) -> bool:
    normalized = {_norm_key(str(key)) for key in row}
    return any(_norm_key(key) in normalized for key in keys)


def _header_has_matrix_long_columns(fieldnames: list[str] | None) -> bool:
    if not fieldnames:
        return False
    row = {field: "" for field in fieldnames}
    has_axes = _has_any_key(row, _F2_DIRECT_KEYS) and _has_any_key(row, _F1_INDIRECT_KEYS)
    has_intensity = _has_any_key(row, _INTENSITY_KEYS)
    has_peak_annotation = _has_any_key(row, _EXPERIMENT_KEYS + _ASSIGNMENT_KEYS + _VOLUME_KEYS)
    return bool(has_axes and has_intensity and not has_peak_annotation)


def is_2d_matrix_preview_upload(
    filename: str,
    content: bytes,
    *,
    include_contour_preview: bool = False,
    row_threshold: int = 50,
) -> bool:
    payload = _json_payload(filename, content)
    if _is_json_matrix_payload(payload):
        return True
    if Path(filename.lower()).suffix == ".json":
        return False
    text = content.decode("utf-8", errors="replace").lstrip("\ufeff")
    if not text.strip():
        return False
    delimiter = _sniff_delimiter(text, filename)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not _header_has_matrix_long_columns(reader.fieldnames):
        return False
    if include_contour_preview:
        return True
    return sum(1 for _row in reader) >= row_threshold


def _looks_h(value: float | None) -> bool:
    return value is not None and _H_MIN <= value <= _H_MAX


def _looks_c(value: float | None) -> bool:
    return value is not None and _C_MIN <= value <= _C_MAX and not _looks_h(value)


def _infer_experiment(filename: str, row: dict[str, Any], f1: float, f2: float, hint: str | None) -> NMR2DExperiment:
    explicit = _normalize_experiment(_row_value(row, *_EXPERIMENT_KEYS), filename=filename, fallback=hint)
    if explicit:
        return explicit
    if _looks_h(f1) and _looks_h(f2):
        return "COSY"
    if f1 > 20.0 and _looks_h(f2):
        return "HSQC"
    if (_looks_h(f1) and _looks_c(f2)) or (_looks_h(f2) and _looks_c(f1)):
        return "HSQC"
    return "COSY"


def _infer_matrix_experiment(
    filename: str,
    f1_values: list[float],
    f2_values: list[float],
    hint: str | None,
) -> NMR2DExperiment:
    explicit = _normalize_experiment(hint, filename=filename)
    if explicit:
        return explicit
    f1_valid = [value for value in f1_values if math.isfinite(value)]
    f2_valid = [value for value in f2_values if math.isfinite(value)]
    if f1_valid and sum(1 for value in f1_valid if value > 20.0) / len(f1_valid) >= 0.5:
        return "HSQC"
    if f1_valid and f2_valid and all(_looks_h(value) for value in f1_valid) and all(_looks_h(value) for value in f2_valid):
        return "COSY"
    if f1_valid and f2_valid and any(_looks_c(value) for value in f1_valid) and any(_looks_h(value) for value in f2_valid):
        return "HSQC"
    return "UNKNOWN"  # type: ignore[return-value]


def _missing_experiment_type(row: dict[str, Any], experiment_hint: str | None) -> bool:
    return not experiment_hint and not _has_any_key(row, _EXPERIMENT_KEYS)


def _make_peak(
    filename: str,
    row: dict[str, Any],
    experiment_hint: str | None,
    *,
    source_row: int | None = None,
) -> NMR2DPeak | None:
    f2 = _safe_float(_row_value(row, *_F2_DIRECT_KEYS))
    f1 = _safe_float(_row_value(row, *_F1_INDIRECT_KEYS))
    if f1 is None or f2 is None:
        return None
    experiment = _infer_experiment(filename, row, f1, f2, experiment_hint)
    intensity = _safe_float(_row_value(row, *_INTENSITY_KEYS))
    volume = _safe_float(_row_value(row, *_VOLUME_KEYS))
    assignment_raw = _row_value(row, *_ASSIGNMENT_KEYS)
    assignment = str(assignment_raw).strip() if assignment_raw not in {None, ""} else None
    notes: list[str] = []
    warnings: list[str] = []
    proton1 = proton2 = carbon = None
    f1_nucleus = "1H"
    f2_nucleus = "1H"
    display_f1 = f1
    display_f2 = f2
    if experiment == "COSY":
        proton1, proton2 = f1, f2
        if abs(f1 - f2) <= 0.025:
            notes.append("Near-diagonal COSY peak; review whether this is a diagonal artifact.")
            warnings.append("Near-diagonal COSY peak; review whether this is a diagonal artifact.")
    else:
        f1_nucleus = "13C"
        if _looks_h(f1) and not _looks_h(f2):
            proton1, carbon = f1, f2
            display_f1, display_f2 = f2, f1
        elif _looks_h(f2) and not _looks_h(f1):
            proton1, carbon = f2, f1
            display_f1, display_f2 = f1, f2
        else:
            notes.append("Could not confidently assign proton/carbon axes from shift ranges.")
            warnings.append("Could not confidently assign proton/carbon axes from shift ranges.")
    if _missing_experiment_type(row, experiment_hint):
        warnings.append(f"Experiment type missing; auto-detected {experiment}.")
    return NMR2DPeak(
        experiment=experiment,
        f1_ppm=round(display_f1, 4),
        f2_ppm=round(display_f2, 4),
        intensity=intensity,
        volume=volume,
        assignment=assignment,
        source_row=source_row,
        f1_nucleus=f1_nucleus,  # type: ignore[arg-type]
        f2_nucleus=f2_nucleus,  # type: ignore[arg-type]
        proton1_ppm=round(proton1, 4) if proton1 is not None else None,
        proton2_ppm=round(proton2, 4) if proton2 is not None else None,
        carbon_ppm=round(carbon, 4) if carbon is not None else None,
        warnings=warnings,
        notes=notes,
    )


def _annotate_duplicate_cross_peaks(peaks: list[NMR2DPeak]) -> tuple[list[NMR2DPeak], dict[str, int], list[str]]:
    exact_duplicates = 0
    symmetric_duplicates = 0
    annotated: list[NMR2DPeak] = []
    preview_warnings: list[str] = []
    for peak in peaks:
        peak_warnings = list(peak.warnings)
        peak_notes = list(peak.notes)
        exact_duplicate = any(
            str(previous.experiment) == str(peak.experiment)
            and abs(previous.f2_ppm - peak.f2_ppm) <= _DUPLICATE_TOLERANCE_PPM
            and abs(previous.f1_ppm - peak.f1_ppm) <= _DUPLICATE_TOLERANCE_PPM
            for previous in annotated
        )
        symmetric_duplicate = any(
            str(peak.experiment) == "COSY"
            and str(previous.experiment) == "COSY"
            and abs(previous.f2_ppm - peak.f1_ppm) <= _DUPLICATE_TOLERANCE_PPM
            and abs(previous.f1_ppm - peak.f2_ppm) <= _DUPLICATE_TOLERANCE_PPM
            for previous in annotated
        )
        if exact_duplicate:
            exact_duplicates += 1
            peak_warnings.append("Duplicate 2D cross-peak within tolerance; review duplicate picking.")
            peak_notes.append("Duplicate cross-peak detected within parser tolerance.")
        elif symmetric_duplicate:
            symmetric_duplicates += 1
            peak_notes.append("Symmetric COSY cross-peak detected; analysis treats it as supporting duplicate evidence.")
        if peak_warnings != peak.warnings or peak_notes != peak.notes:
            peak = peak.model_copy(
                update={
                    "warnings": list(dict.fromkeys(peak_warnings)),
                    "notes": list(dict.fromkeys(peak_notes)),
                    "is_suspicious": bool(peak.is_suspicious or peak_warnings),
                }
            )
        annotated.append(peak)
    if exact_duplicates:
        preview_warnings.append(f"{exact_duplicates} duplicate 2D cross-peak(s) were detected within tolerance.")
    if symmetric_duplicates:
        preview_warnings.append(f"{symmetric_duplicates} symmetric COSY duplicate pair(s) were detected and will be treated as supporting duplicates.")
    return annotated, {"exact": exact_duplicates, "symmetric_cosy": symmetric_duplicates}, preview_warnings


def _downsample_matrix_points(
    points: list[NMR2DContourPoint],
    max_points: int,
) -> tuple[list[NMR2DContourPoint], str]:
    if max_points < 1:
        max_points = _DEFAULT_MATRIX_POINT_LIMIT
    if len(points) <= max_points:
        return points, "none"
    ranked = sorted(
        enumerate(points),
        key=lambda item: abs(float(item[1].intensity)),
        reverse=True,
    )[:max_points]
    selected = [point for _index, point in sorted(ranked, key=lambda item: (item[1].f1_ppm, item[1].f2_ppm))]
    return selected, "top_abs_intensity"


def _matrix_points_from_json(payload: dict[str, Any]) -> tuple[list[NMR2DContourPoint], dict[str, Any]]:
    f2_axis = [_safe_float(item) for item in payload.get("f2_axis", [])]
    f1_axis = [_safe_float(item) for item in payload.get("f1_axis", [])]
    f2_values = [float(item) for item in f2_axis if item is not None]
    f1_values = [float(item) for item in f1_axis if item is not None]
    matrix = payload.get("intensity", [])
    if not isinstance(matrix, list):
        raise NMR2DParseError("2D matrix JSON intensity must be a list of rows.")
    points: list[NMR2DContourPoint] = []
    rows = 0
    cols = 0
    for f1_index, row in enumerate(matrix):
        if not isinstance(row, list) or f1_index >= len(f1_axis) or f1_axis[f1_index] is None:
            continue
        rows += 1
        cols = max(cols, len(row))
        for f2_index, value in enumerate(row):
            if f2_index >= len(f2_axis) or f2_axis[f2_index] is None:
                continue
            intensity = _safe_float(value)
            if intensity is None:
                continue
            points.append(
                NMR2DContourPoint(
                    f2_ppm=round(float(f2_axis[f2_index]), 4),
                    f1_ppm=round(float(f1_axis[f1_index]), 4),
                    intensity=float(intensity),
                )
            )
    return points, {
        "matrix_format": "json_axes_intensity",
        "f2_axis_count": len(f2_values),
        "f1_axis_count": len(f1_values),
        "intensity_shape": [rows, cols],
        "f2_values": f2_values,
        "f1_values": f1_values,
    }


def _matrix_points_from_long_csv(filename: str, content: bytes) -> tuple[list[NMR2DContourPoint], dict[str, Any]]:
    text = content.decode("utf-8", errors="replace").lstrip("\ufeff")
    if not text.strip():
        raise NMR2DParseError("2D matrix preview upload is empty.")
    delimiter = _sniff_delimiter(text, filename)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not _header_has_matrix_long_columns(reader.fieldnames):
        raise NMR2DParseError("2D matrix CSV must use long format columns f2_ppm,f1_ppm,intensity.")
    points: list[NMR2DContourPoint] = []
    f2_values: set[float] = set()
    f1_values: set[float] = set()
    for row in reader:
        f2 = _safe_float(_row_value(row, *_F2_DIRECT_KEYS))
        f1 = _safe_float(_row_value(row, *_F1_INDIRECT_KEYS))
        intensity = _safe_float(_row_value(row, *_INTENSITY_KEYS))
        if f2 is None or f1 is None or intensity is None:
            continue
        f2_values.add(float(f2))
        f1_values.add(float(f1))
        points.append(NMR2DContourPoint(f2_ppm=round(float(f2), 4), f1_ppm=round(float(f1), 4), intensity=float(intensity)))
    return points, {
        "matrix_format": "csv_long",
        "f2_axis_count": len(f2_values),
        "f1_axis_count": len(f1_values),
        "intensity_shape": [len(f1_values), len(f2_values)],
        "f2_values": sorted(f2_values),
        "f1_values": sorted(f1_values),
    }


def parse_2d_matrix_preview(
    filename: str,
    content: bytes,
    *,
    experiment_hint: str | None = None,
    max_points: int = _DEFAULT_MATRIX_POINT_LIMIT,
) -> NMR2DPreview:
    payload = _json_payload(filename, content)
    if _is_json_matrix_payload(payload):
        points, matrix_metadata = _matrix_points_from_json(payload)
        experiment_source = payload.get("experiment") or payload.get("experiment_type") or payload.get("type")
    else:
        points, matrix_metadata = _matrix_points_from_long_csv(filename, content)
        experiment_source = experiment_hint
    if not points:
        raise NMR2DParseError("No valid 2D matrix preview intensity points could be parsed.")
    experiment = _infer_matrix_experiment(
        filename,
        list(matrix_metadata.get("f1_values", [])),
        list(matrix_metadata.get("f2_values", [])),
        str(experiment_source or experiment_hint or ""),
    )
    downsampled, method = _downsample_matrix_points(points, max_points=max_points)
    warnings = [
        "Processed 2D matrix preview is display-only; it does not affect evidence scoring unless cross-peaks are explicitly picked.",
        "Raw 2D FID/SER processing is not performed by this preview.",
    ]
    metadata = {
        "parser": "processed_2d_matrix_preview_v1",
        "evidence_trace_mode": "display_only_matrix_preview",
        "contour_preview_affects_evidence_score": False,
        "raw_2d_fid_processing": "not_implemented_guarded_release",
        "original_point_count": len(points),
        "returned_point_count": len(downsampled),
        "max_point_limit": max_points,
        "downsampling_method": method,
        **{key: value for key, value in matrix_metadata.items() if key not in {"f1_values", "f2_values"}},
    }
    return NMR2DPreview(
        filename=filename,
        experiment_detected=experiment,  # type: ignore[arg-type]
        source_mode="processed_matrix_preview",
        experiments=[] if str(experiment) == "UNKNOWN" else [experiment],  # type: ignore[list-item]
        peak_count=0,
        peaks=[],
        contour_preview=downsampled,
        warnings=warnings,
        metadata=metadata,
    )


def parse_processed_2d_nmr(
    filename: str,
    content: bytes,
    *,
    experiment_hint: str | None = None,
    include_contour_preview: bool = False,
    contour_limit: int = 800,
) -> NMR2DPreview:
    rows = _rows_from_upload(filename, content)
    peaks: list[NMR2DPeak] = []
    contour: list[NMR2DContourPoint] = []
    warnings: list[str] = []
    missing_experiment_rows = 0
    for index, row in enumerate(rows, start=1):
        if _missing_experiment_type(row, experiment_hint):
            missing_experiment_rows += 1
        peak = _make_peak(filename, row, experiment_hint, source_row=index)
        if peak is None:
            continue
        peaks.append(peak)
        if include_contour_preview and peak.intensity is not None and len(contour) < contour_limit:
            contour.append(NMR2DContourPoint(f1_ppm=peak.f1_ppm, f2_ppm=peak.f2_ppm, intensity=peak.intensity))
    if not peaks:
        raise NMR2DParseError("No valid 2D NMR cross-peaks could be parsed.")
    peaks, duplicate_counts, duplicate_warnings = _annotate_duplicate_cross_peaks(peaks)
    warnings.extend(duplicate_warnings)
    experiments = sorted({peak.experiment for peak in peaks})
    experiment_detected = experiments[0] if len(experiments) == 1 else ("UNKNOWN" if len(experiments) > 1 else "UNKNOWN")
    if len(experiments) > 1:
        warnings.append("Multiple 2D experiment types were detected in one upload; review grouping before final interpretation.")
    if missing_experiment_rows:
        warnings.append(f"Experiment type was missing from {missing_experiment_rows} row(s); parser auto-detected experiment type from filename and shift ranges.")
    if any(peak.is_suspicious for peak in peaks):
        warnings.append("One or more 2D cross-peaks were flagged as diagonal, duplicate, solvent/artifact, or out-of-range and require review.")
    warnings.append("Processed 2D peak tables are evidence aids; human review is required for final assignment.")
    return NMR2DPreview(
        filename=filename,
        experiment_detected=experiment_detected,  # type: ignore[arg-type]
        source_mode="processed_contour_table" if contour else "processed_peak_table",
        experiments=experiments,  # type: ignore[arg-type]
        peak_count=len(peaks),
        peaks=peaks,
        contour_preview=contour,
        warnings=warnings,
        metadata={
            "parser": "processed_2d_peak_table_v1",
            "experiment_hint": experiment_hint or "auto",
            "contour_preview_enabled": include_contour_preview,
            "accepted_formats": ["csv", "tsv", "json"],
            "missing_experiment_type_rows": missing_experiment_rows,
            "duplicate_cross_peak_counts": duplicate_counts,
            "diagonal_peak_count": sum(1 for peak in peaks if peak.is_diagonal),
            "out_of_range_peak_count": sum(
                1
                for peak in peaks
                if (peak.f1_region or "").startswith("outside_") or (peak.f2_region or "").startswith("outside_")
            ),
            "raw_2d_fid_processing": "not_implemented_guarded_release",
        },
    )
