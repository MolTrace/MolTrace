from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import Counter
from statistics import median
from typing import Any

from rdkit import Chem

from .chemistry import mol_from_smiles, structure_summary_from_smiles
from .compound_class_priors import diagnostic_regions_for
from .evidence import ratio_score
from .exceptions import StructureParseError
from .impurities import match_c13_impurity_shifts
from .baseline import evaluate_baseline_flatness, normalize_baseline_mode
from .mnova_view import weak_peak_magnifier_view
from .models import (
    Carbon13AnalysisReport,
    Carbon13Peak,
    Carbon13RegionSummary,
    Carbon13UploadPreview,
)
from .nmr_tables import classify_carbon13_region, find_solvent_or_impurity_hits
from .parser import parse_reference_nmr_text
from .spectrum import _apply_solvent_mask as _apply_trace_solvent_mask
from .spectrum import _estimate_noise_sigma
from .spectrum import _in_priority_region
from .spectrum import _ppm_step
from .spectrum import _robust_polynomial_baseline_correct
from .spectrum import _sensitivity_to_noise_factor
from .spectrum import _build_preserved_spectrum_state
from .spectrum import _build_preview_spectrum_state
from .spectrum import _PREVIEW_DOWNSAMPLING_METHOD
from .spectrum import _PROCESSED_DISPLAY_DOWNSAMPLING_METHOD
from .spectrum import _downsample_points
from .spectrum import _downsample_processed_display_points
from .spectrum import _prepare_trace_display_points
from .spectrum import _preview_baseline_flatness_qa
from .spectrum import apply_processed_trace_baseline_conditions
from .spectrum import smooth_trace_display_points

_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)")
_C13_UPLOAD_MIN_PPM = -50.0
_C13_UPLOAD_MAX_PPM = 260.0
_C13_TEXT_MATCH_TOLERANCE_PPM = 0.35


class Carbon13ParseError(ValueError):
    pass


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _detect_text_extension(filename: str) -> str:
    name = filename.lower().strip()
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1]


_TEXT_SPECTRUM_EXTENSIONS = {"csv", "tsv", "txt", "xy", "asc", "dat"}
_JCAMP_SPECTRUM_EXTENSIONS = {"jcamp", "jdx", "dx"}


def _is_plausible_carbon13_upload_shift(value: float) -> bool:
    return _C13_UPLOAD_MIN_PPM <= float(value) <= _C13_UPLOAD_MAX_PPM


def normalize_carbon_type(value: Any) -> str | None:
    if value is None:
        return None
    text = "".join(char for char in str(value).strip().lower() if char.isalnum() or char == "/")
    if not text:
        return None
    aliases = {
        "c": "C",
        "quat": "C",
        "quaternary": "C",
        "q": "C",
        "ch": "CH",
        "methine": "CH",
        "ch2": "CH2",
        "methylene": "CH2",
        "ch3": "CH3",
        "methyl": "CH3",
        "0": "C",
        "attached0": "C",
        "attachedh0": "C",
        "1": "CH",
        "attached1": "CH",
        "attachedh1": "CH",
        "2": "CH2",
        "attached2": "CH2",
        "attachedh2": "CH2",
        "3": "CH3",
        "attached3": "CH3",
        "attachedh3": "CH3",
        "ch_or_ch3": "CH_OR_CH3",
        "chorch3": "CH_OR_CH3",
        "ch/ch3": "CH_OR_CH3",
        "ch3/ch": "CH_OR_CH3",
        "ch2_or_c": "CH2_OR_C",
        "ch2orc": "CH2_OR_C",
        "ch2/c": "CH2_OR_C",
        "c/ch2": "CH2_OR_C",
    }
    return aliases.get(text, str(value).strip().upper())


def _carbon_type_from_assignment(assignment: str | None) -> str | None:
    if not assignment:
        return None
    upper = assignment.upper().replace(" ", "")
    for token in ("CH3", "CH2", "CH"):
        if token in upper:
            return token
    if "QUAT" in upper or upper == "C":
        return "C"
    return None


def _make_peak(
    shift: float,
    *,
    solvent: str | None = None,
    intensity: float | None = None,
    assignment: str | None = None,
    carbon_type: str | None = None,
) -> Carbon13Peak:
    region = classify_carbon13_region(shift)
    hits = find_solvent_or_impurity_hits(shift, solvent=solvent, nucleus="13C")
    impurity_matches = match_c13_impurity_shifts(shift, solvent)
    notes: list[str] = []
    for hit in hits:
        notes.append(f"Likely {hit.label}.")
    for match in impurity_matches:
        notes.append(
            f"Embedded ¹³C impurity/reference match: {match['label']} near {match['expected_ppm']} ppm."
        )
    if "unusual" in region.lower():
        notes.append("Chemical shift is outside the usual ¹³C range and should be reviewed.")
    inferred_type = normalize_carbon_type(carbon_type) or _carbon_type_from_assignment(assignment)
    return Carbon13Peak(
        shift_ppm=round(shift, 3),
        intensity=intensity,
        assignment=assignment,
        region=region,
        carbon_type=inferred_type,
        is_likely_solvent=bool(hits),
        is_likely_impurity=any(match.get("kind") != "solvent" for match in impurity_matches),
        impurity_matches=impurity_matches,
        notes=notes,
    )


def parse_carbon13_text(text: str, *, solvent: str | None = None) -> list[Carbon13Peak]:
    value = text.strip()
    if not value:
        raise Carbon13ParseError("¹³C NMR text cannot be empty.")
    lowered = value.lower()
    if "13c" not in lowered and "¹³c" not in lowered and "c nmr" not in lowered:
        if "1h nmr" in lowered or "¹h nmr" in lowered:
            raise Carbon13ParseError("Input appears to be ¹H NMR text rather than ¹³C NMR text.")

    segment = value.split("δ", 1)[1] if "δ" in value else value
    segment = re.sub(r"\([^)]*MHz[^)]*\)", " ", segment, flags=re.IGNORECASE)
    # Replace ranges with midpoints. ¹³C is normally reported as discrete shifts, but this keeps parsing tolerant.
    for left, right in _RANGE_RE.findall(segment):
        midpoint = (float(left) + float(right)) / 2.0
        segment = segment.replace(f"{left}-{right}", str(midpoint)).replace(f"{left}–{right}", str(midpoint))
    shifts = [float(x) for x in _FLOAT_RE.findall(segment)]
    shifts = [x for x in shifts if _is_plausible_carbon13_upload_shift(x)]
    if not shifts:
        raise Carbon13ParseError("No ¹³C chemical shifts could be parsed.")

    peaks: list[Carbon13Peak] = []
    seen: list[float] = []
    for shift in shifts:
        if any(abs(shift - prior) < 0.005 for prior in seen):
            continue
        seen.append(shift)
        peaks.append(_make_peak(shift, solvent=solvent))
    return peaks


def carbon13_peaks_from_shift_values(
    shifts: list[float] | list[tuple[float, float | None]],
    *,
    solvent: str | None = None,
) -> list[Carbon13Peak]:
    peaks: list[Carbon13Peak] = []
    seen: list[float] = []
    for item in shifts:
        if isinstance(item, tuple):
            shift, intensity = item
        else:
            shift = item
            intensity = None
        if not _is_plausible_carbon13_upload_shift(float(shift)):
            continue
        if any(abs(float(shift) - prior) < 0.005 for prior in seen):
            continue
        seen.append(float(shift))
        peaks.append(_make_peak(float(shift), solvent=solvent, intensity=intensity))
    return peaks


def _sniff_delimiter(text: str, filename: str) -> str:
    if filename.lower().endswith(".tsv"):
        return "\t"
    sample = "\n".join(text.splitlines()[:10])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except Exception:
        return "\t" if "\t" in sample else (";" if ";" in sample else ",")


def parse_carbon13_table(filename: str, content: bytes, *, solvent: str | None = None) -> Carbon13UploadPreview:
    text = content.decode("utf-8", errors="replace").lstrip("\ufeff")
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    warnings: list[str] = []

    rows: list[dict[str, Any]]
    if ext == "json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise Carbon13ParseError("Invalid JSON carbon-13 peak table.") from exc
        if isinstance(parsed, dict) and "peaks" in parsed:
            parsed = parsed["peaks"]
        if not isinstance(parsed, list):
            raise Carbon13ParseError("JSON carbon-13 upload must be a list of peak objects or an object with a 'peaks' list.")
        rows = [row for row in parsed if isinstance(row, dict)]
    elif ext in _TEXT_SPECTRUM_EXTENSIONS:
        delimiter = _sniff_delimiter(text, filename)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise Carbon13ParseError("Carbon-13 delimited text table must include a header row.")
        rows = list(reader)
    else:
        raise Carbon13ParseError("Unsupported ¹³C upload format. Use CSV, TSV, TXT, XY, ASC, DAT, or JSON.")

    peaks: list[Carbon13Peak] = []
    original_points: list[tuple[float, float]] = []
    for row in rows:
        norm = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
        shift = _safe_float(norm.get("shift_ppm") or norm.get("ppm") or norm.get("shift") or norm.get("delta"))
        if shift is None:
            continue
        intensity = _safe_float(norm.get("intensity") or norm.get("height") or norm.get("area"))
        assignment = norm.get("assignment") or norm.get("label")
        carbon_type = norm.get("carbon_type") or norm.get("dept") or norm.get("apt") or norm.get("type")
        peaks.append(_make_peak(shift, solvent=solvent, intensity=intensity, assignment=assignment, carbon_type=carbon_type))
        original_points.append((float(shift), float(intensity if intensity is not None else 0.0)))

    if not peaks:
        raise Carbon13ParseError("No valid ¹³C peaks were found in the uploaded table.")
    if any(p.is_likely_solvent for p in peaks):
        warnings.append("One or more ¹³C peaks fall in known solvent-carbon regions.")
    if any(p.is_likely_impurity for p in peaks):
        warnings.append("One or more ¹³C peaks overlap embedded impurity-reference shifts.")
    if any(p.region and "unusual" in p.region.lower() for p in peaks):
        warnings.append("One or more carbon shifts are outside the usual ¹³C range.")
    return Carbon13UploadPreview(
        filename=filename,
        source_mode="peak_table",
        observed_signal_count=len(peaks),
        peaks=peaks,
        warnings=warnings,
        metadata={
            "solvent": solvent,
            "format": ext,
            "original_spectrum_state": _build_preserved_spectrum_state(
                original_points,
                source="uploaded_carbon13_peak_table",
                processing_stage="as_uploaded",
            ),
        },
    )


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
        if _is_plausible_carbon13_upload_shift(x) and math.isfinite(y):
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
        if _is_plausible_carbon13_upload_shift(x) and math.isfinite(y):
            points.append((x, y))
    return points


def _parse_carbon13_jcamp_text(text: str) -> list[tuple[float, float]]:
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
            if _is_plausible_carbon13_upload_shift(x) and math.isfinite(y):
                points.append((x, y))
    if not points:
        raise Carbon13ParseError("Could not extract simple XY data pairs from the JCAMP-DX ¹³C file.")
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


def _rolling_percentile(values: list[float], *, window: int, percentile: float) -> list[float]:
    if not values:
        return []
    radius = max(1, window // 2)
    out: list[float] = []
    for idx in range(len(values)):
        start = max(0, idx - radius)
        end = min(len(values), idx + radius + 1)
        out.append(_percentile(sorted(values[start:end]), percentile))
    return out


def _baseline_correct(values: list[float]) -> list[float]:
    if not values:
        return []
    raw = [float(value) for value in values]
    if len(raw) < 51:
        base = median(raw)
        corrected = [value - base for value in raw]
        min_value = min(corrected)
        if min_value < 0:
            corrected = [value - min_value for value in corrected]
        return corrected
    baseline_window = _odd_window(len(raw), fraction=0.018, minimum=21, maximum=181)
    baseline = _rolling_percentile(raw, window=baseline_window, percentile=18.0)
    baseline = _smooth(baseline, window=_odd_window(len(raw), fraction=0.004, minimum=5, maximum=31))
    return [max(0.0, value - base) for value, base in zip(raw, baseline, strict=False)]


def _downsample_carbon13_points(points: list[tuple[float, float]], limit: int = 700) -> list[dict[str, float]]:
    if not points:
        return []
    ordered = sorted(points, key=lambda item: item[0], reverse=True)
    if len(ordered) <= limit:
        sampled = ordered
    else:
        step = max(1, len(ordered) // limit)
        sampled = ordered[::step]
        if sampled[-1] != ordered[-1]:
            sampled.append(ordered[-1])
    return [{"shift_ppm": round(float(x), 4), "intensity": float(y)} for x, y in sampled[: limit + 1]]


def _infer_carbon13_trace_peaks(
    points: list[tuple[float, float]],
    *,
    solvent: str | None = None,
    peak_sensitivity: float | None = None,
    priority_regions: tuple[tuple[float, float], ...] = (),
) -> list[Carbon13Peak]:
    if len(points) < 3:
        return []
    ordered = sorted(points, key=lambda item: item[0], reverse=True)
    x_vals = [float(x) for x, _ in ordered]
    # Baseline-correct once: the unclipped result feeds an unbiased noise
    # estimate, the zero-clipped result is the detection trace.
    corrected, _baseline_meta = _robust_polynomial_baseline_correct(
        [float(y) for _, y in ordered], orient_positive=True
    )
    if len(corrected) < 3:
        return []
    smoothing_window = 5 if len(corrected) >= 1200 else 3
    y_vals = _smooth([max(0.0, value) for value in corrected], window=smoothing_window)
    low = min(y_vals)
    high = max(y_vals)
    if math.isclose(high, low):
        return []
    sensitivity = 0.12 if peak_sensitivity is None else min(max(float(peak_sensitivity), 0.02), 0.45)
    # SNR detection threshold — noise_factor·σ above the baseline, with σ the
    # robust 1.4826·MAD noise estimate of the unclipped corrected trace. This
    # replaces the former fraction-of-dynamic-range cut, so weak ¹³C carbons are
    # not lost beneath a dominant signal and noise spikes are not picked.
    noise_sigma = _estimate_noise_sigma(_smooth(corrected, window=smoothing_window))
    baseline_level = median(y_vals)
    if noise_sigma > 0.0:
        noise_factor = _sensitivity_to_noise_factor(sensitivity)
        threshold = baseline_level + noise_factor * noise_sigma
        # Inside compound-class-diagnostic windows, drop to a more sensitive
        # SNR cut (floored at 3σ) so weak diagnostic carbons are not lost.
        region_threshold = baseline_level + max(3.0, noise_factor * 0.6) * noise_sigma
    else:
        threshold = low + 0.02 * (high - low)
        region_threshold = threshold
    candidates: list[tuple[float, float]] = []
    for idx in range(1, len(y_vals) - 1):
        center = y_vals[idx]
        local_threshold = (
            region_threshold
            if priority_regions and _in_priority_region(x_vals[idx], priority_regions)
            else threshold
        )
        if center < local_threshold:
            continue
        if center < y_vals[idx - 1] or center < y_vals[idx + 1]:
            continue
        candidates.append((x_vals[idx], center))
    candidates.sort(key=lambda item: item[1], reverse=True)
    selected: list[tuple[float, float]] = []
    # Resolution-driven dedup distance — replaces the former flat 0.25 ppm
    # merge, which fused genuinely distinct carbons. Local maxima are already
    # ≥2 samples apart, so this only collapses a noisy peak top.
    min_sep_ppm = max(_ppm_step(x_vals) * 4, 0.01)
    for shift, intensity in candidates:
        if any(abs(shift - prior_shift) < min_sep_ppm for prior_shift, _ in selected):
            continue
        selected.append((shift, intensity))
    selected.sort(key=lambda item: item[0], reverse=True)
    return [
        _make_peak(shift, solvent=solvent, intensity=round(float(intensity), 6))
        for shift, intensity in selected
    ]


def parse_carbon13_processed_spectrum(
    filename: str,
    content: bytes,
    *,
    solvent: str | None = None,
    carbon13_text: str | None = None,
    peak_sensitivity: float | None = None,
    compound_class: str | None = None,
    mask_solvent_regions: bool = True,
    display_mode: str = "real",
    vertical_gain: float = 1.0,
    debug_preview: bool = False,
    max_preview_points: int = 1200,
    processed_baseline_correction: str = "bernstein",
    processed_baseline_order: int = 3,
    infer_peaks: bool = True,
) -> Carbon13UploadPreview:
    text = content.decode("utf-8", errors="replace").lstrip("\ufeff")
    ext = _detect_text_extension(filename)
    warnings: list[str] = []
    points: list[tuple[float, float]] = []

    if ext == "json":
        return parse_carbon13_table(filename, content, solvent=solvent)
    if ext in _TEXT_SPECTRUM_EXTENSIONS:
        delimiter = _sniff_delimiter(text, filename)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader) if reader.fieldnames else []
        if rows:
            lowered = {str(name).strip().lower() for name in (reader.fieldnames or []) if name}
            assignment_keys = {"assignment", "label", "carbon_type", "dept", "apt", "type"}
            shift_keys = {"shift_ppm", "ppm", "shift", "delta"}
            trace_y_keys = {"signal", "y", "amplitude"}
            if len(rows) <= 80 and (assignment_keys & lowered or ((shift_keys & lowered) and not (trace_y_keys & lowered))):
                return parse_carbon13_table(filename, content, solvent=solvent)
            for row in rows:
                norm = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
                x = _safe_float(norm.get("ppm") or norm.get("shift") or norm.get("shift_ppm") or norm.get("delta") or norm.get("x"))
                y = _safe_float(norm.get("intensity") or norm.get("signal") or norm.get("y") or norm.get("amplitude") or norm.get("height") or norm.get("area"))
                if x is None:
                    continue
                if y is None and len(rows) <= 80:
                    return parse_carbon13_table(filename, content, solvent=solvent)
                if y is not None and _is_plausible_carbon13_upload_shift(x) and math.isfinite(y):
                    points.append((x, y))
        else:
            points = _extract_numeric_pairs_from_delimited(text, delimiter=delimiter)
            if not points:
                points = _extract_numeric_pairs_from_text(text)
        if not points:
            points = _extract_numeric_pairs_from_text(text)
    elif ext in _JCAMP_SPECTRUM_EXTENSIONS:
        points = _parse_carbon13_jcamp_text(text)
        warnings.append("JCAMP-DX support is limited to simple XY-style ¹³C exports.")
    else:
        raise Carbon13ParseError("Unsupported ¹³C spectrum format. Use CSV, TSV, TXT, XY, ASC, DAT, JSON, JCAMP, JDX, or DX.")

    if not points:
        return parse_carbon13_table(filename, content, solvent=solvent)
    original_points = points[:]
    points, processed_baseline_metadata, warnings = apply_processed_trace_baseline_conditions(
        points,
        mode=processed_baseline_correction,
        order=processed_baseline_order,
        warnings=warnings,
        label="processed-file 13C",
    )
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
            "the ¹³C preview trace preserves original intensity values."
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
    inference_points = points
    if mask_solvent_regions:
        inference_points, mask_notes = _apply_trace_solvent_mask(
            points,
            solvent,
            nucleus="13C",
        )
        warnings.extend(mask_notes)
    display_points, display_meta, display_notes = _prepare_trace_display_points(
        points,
        solvent=solvent,
        mask_solvent_regions=mask_solvent_regions,
        nucleus="13C",
        baseline_already_corrected=bool(processed_baseline_metadata.get("correction_applied")),
    )
    if smoothing_allowed:
        display_points, trace_smoothing_meta = smooth_trace_display_points(
            display_points,
            nucleus="13C",
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
            "Processed 13C preview points use display-only trace smoothing after "
            "automatic baseline correction. Peak picking and evidence scoring "
            "use the corrected unsmoothed evidence trace."
        )
    warnings.extend(note for note in display_notes if note not in warnings)
    if normalized_display_mode == "magnifier":
        magnifier = weak_peak_magnifier_view(
            points,
            visual_gain=max(viewer_gain, 2.0),
        )
        display_meta["weak_peak_magnifier"] = {
            **magnifier.metadata,
            "points": [
                point.model_dump(mode="json")
                for point in _downsample_points(
                    magnifier.points,
                    limit=min(preview_limit, 700),
                )
            ],
        }
        warnings.extend(note for note in magnifier.warnings if note not in warnings)
    if not infer_peaks:
        text_guidance_meta = {
            "carbon13_text_guidance_used": False,
            "reference_peak_count": 0,
            "matched_reference_peak_count": 0,
            "missing_reference_peak_count": 0,
            "filtered_unmatched_detected_peak_count": 0,
            "match_tolerance_ppm": _C13_TEXT_MATCH_TOLERANCE_PPM,
            "peak_evidence_policy": "detected_peaks_only_no_reference_fabrication",
            "skipped": True,
            "reason": "peak_inference_disabled",
        }
        preview_points = _downsample_processed_display_points(display_points, limit=preview_limit)
        warnings.append("Display preview generated without ¹³C peak inference; use Analyze to run peak detection and evidence scoring.")
        return Carbon13UploadPreview(
            filename=filename,
            source_mode="processed_trace",
            observed_signal_count=0,
            peaks=[],
            warnings=warnings,
            metadata={
                "solvent": solvent,
                "format": ext,
                "point_count": len(points),
                "peak_sensitivity": 0.12 if peak_sensitivity is None else peak_sensitivity,
                "peak_inference": "skipped_for_display_preview",
                "peak_inference_skipped": True,
                "carbon13_text_guidance": text_guidance_meta,
                "peak_evidence_policy": "detected_peaks_only_no_reference_fabrication",
                "mask_solvent_regions": mask_solvent_regions,
                "preview_points": [point.model_dump(mode="json") for point in preview_points],
                "display_preprocessing": display_meta,
                "processed_baseline_correction": processed_baseline_metadata,
                "baseline_flatness_qa": _preview_baseline_flatness_qa(
                    preview_points,
                    mode=processed_baseline_metadata.get("method") or "processed_13c",
                ),
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
                "preview_fast_path": True,
                "original_spectrum_state": _build_preview_spectrum_state(
                    original_points,
                    preview_points,
                    source="uploaded_carbon13_trace",
                    processing_stage="as_uploaded",
                ),
                **(
                    {
                        "raw_preview_points": [point.model_dump(mode="json") for point in preview_points]
                    }
                    if debug_preview
                    else {}
                ),
            },
        )
    peaks = _infer_carbon13_trace_peaks(
        inference_points,
        solvent=solvent,
        peak_sensitivity=peak_sensitivity,
        priority_regions=diagnostic_regions_for(compound_class, "13C"),
    )
    if not peaks:
        raise Carbon13ParseError("No ¹³C peaks could be inferred from the uploaded processed spectrum.")
    peaks, text_guidance_meta, text_guidance_notes = refine_carbon13_peaks_with_text_guidance(
        peaks,
        carbon13_text=carbon13_text,
        solvent=solvent,
    )
    warnings.extend(note for note in text_guidance_notes if note not in warnings)
    warnings.append("Processed ¹³C spectrum trace detected; carbon peaks were inferred heuristically and should be reviewed.")
    if any(peak.is_likely_solvent for peak in peaks):
        warnings.append("One or more inferred ¹³C peaks fall in known solvent-carbon regions.")
    if any(peak.is_likely_impurity for peak in peaks):
        warnings.append("One or more inferred ¹³C peaks overlap embedded impurity-reference shifts.")
    return Carbon13UploadPreview(
        filename=filename,
        source_mode="processed_trace",
        observed_signal_count=len(peaks),
        peaks=peaks,
        warnings=warnings,
        metadata={
            "solvent": solvent,
            "format": ext,
            "point_count": len(points),
            "peak_sensitivity": 0.12 if peak_sensitivity is None else peak_sensitivity,
            "peak_inference": "enabled",
            "peak_inference_skipped": False,
            "carbon13_text_guidance": text_guidance_meta,
            "peak_evidence_policy": "detected_peaks_only_no_reference_fabrication",
            "mask_solvent_regions": mask_solvent_regions,
            "preview_points": [
                point.model_dump(mode="json")
                for point in _downsample_processed_display_points(display_points, limit=preview_limit)
            ],
            "display_preprocessing": display_meta,
            "processed_baseline_correction": processed_baseline_metadata,
            "baseline_flatness_qa": evaluate_baseline_flatness(
                points,
                mode=processed_baseline_metadata.get("method") or "processed_13c",
            ).as_dict(),
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
            "original_spectrum_state": _build_preserved_spectrum_state(
                original_points,
                source="uploaded_carbon13_trace",
                processing_stage="as_uploaded",
                point_limit=preview_limit,
            ),
            **(
                {
                    "raw_preview_points": [
                        point.model_dump(mode="json")
                        for point in _downsample_points(points, limit=preview_limit)
                    ]
                }
                if debug_preview
                else {}
            ),
        },
    )


def expected_carbon_count_from_smiles(smiles: str) -> int:
    mol = mol_from_smiles(smiles)
    return sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 6)


def expected_carbon_environment_summary(smiles: str) -> dict[str, int]:
    mol = Chem.AddHs(mol_from_smiles(smiles))
    summary: Counter[str] = Counter()
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6:
            continue
        neighbors = [nbr for nbr in atom.GetNeighbors()]
        attached_h = sum(1 for nbr in neighbors if nbr.GetAtomicNum() == 1)
        heavy_neighbors = [nbr for nbr in neighbors if nbr.GetAtomicNum() != 1]
        has_o_or_n = any(nbr.GetAtomicNum() in {7, 8} for nbr in heavy_neighbors)
        double_o = any(bond.GetBondTypeAsDouble() == 2 and bond.GetOtherAtom(atom).GetAtomicNum() == 8 for bond in atom.GetBonds())
        if double_o:
            summary["carbonyl/carboxyl-like carbon"] += 1
        elif atom.GetIsAromatic() or atom.GetHybridization().name == "SP2":
            summary["aromatic/alkene carbon"] += 1
        elif has_o_or_n and attached_h >= 1:
            summary["O/N-bearing protonated carbon"] += 1
        elif has_o_or_n:
            summary["O/N-bearing quaternary carbon"] += 1
        else:
            summary["aliphatic carbon"] += 1
        if attached_h == 0:
            summary["C"] += 1
        elif attached_h == 1:
            summary["CH"] += 1
        elif attached_h == 2:
            summary["CH2"] += 1
        elif attached_h == 3:
            summary["CH3"] += 1
    return dict(summary)


def _proton_context_from_text(proton_nmr_text: str | None) -> dict[str, int]:
    if not proton_nmr_text or not proton_nmr_text.strip():
        return {}
    try:
        _, assignments = parse_reference_nmr_text(proton_nmr_text)
    except Exception:
        return {}
    hints: Counter[str] = Counter()
    for assignment in assignments:
        shift = float(assignment.shift_ppm)
        if 4.4 <= shift <= 5.8:
            hints["anomeric_or_acetal_protons"] += 1
        if 3.0 <= shift <= 4.5:
            hints["oxygenated_or_nitrogen_adjacent_protons"] += 1
        if 6.0 <= shift <= 8.8:
            hints["aromatic_or_alkene_protons"] += 1
        if 0.5 <= shift <= 2.5:
            hints["aliphatic_protons"] += 1
    return dict(hints)


def _carbon13_peak_context_score(
    peak: Carbon13Peak,
    *,
    max_intensity: float,
    expected_env: dict[str, int],
    proton_context: dict[str, int],
) -> float:
    intensity = abs(float(peak.intensity or 0.0))
    intensity_score = intensity / max(max_intensity, 1e-9)
    region = (peak.region or "").lower()
    score = 0.65 * intensity_score
    if peak.is_likely_solvent:
        score -= 2.0
    if peak.is_likely_impurity:
        score -= 0.10
    if expected_env.get("carbonyl/carboxyl-like carbon", 0) and ("carbonyl" in region or "carboxyl" in region):
        score += 0.35
    if expected_env.get("aromatic/alkene carbon", 0) and ("aromatic" in region or "alkene" in region):
        score += 0.30
    if (
        expected_env.get("O/N-bearing protonated carbon", 0)
        or expected_env.get("O/N-bearing quaternary carbon", 0)
    ) and ("oxygenated" in region or "nitrogen" in region or "anomeric" in region):
        score += 0.30
    if expected_env.get("aliphatic carbon", 0) and "aliphatic" in region:
        score += 0.12
    if proton_context.get("anomeric_or_acetal_protons", 0) and 90.0 <= peak.shift_ppm <= 110.0:
        score += 0.45
    if proton_context.get("oxygenated_or_nitrogen_adjacent_protons", 0) and 40.0 <= peak.shift_ppm <= 95.0:
        score += 0.25
    if proton_context.get("aromatic_or_alkene_protons", 0) and 110.0 <= peak.shift_ppm <= 160.0:
        score += 0.25
    if proton_context.get("aliphatic_protons", 0) and 0.0 <= peak.shift_ppm < 40.0:
        score += 0.12
    return score


def refine_carbon13_peaks_with_context(
    peaks: list[Carbon13Peak],
    *,
    smiles: str | None = None,
    proton_nmr_text: str | None = None,
    solvent: str | None = None,
) -> tuple[list[Carbon13Peak], dict[str, Any], list[str]]:
    context_meta: dict[str, Any] = {
        "smiles_guidance_used": False,
        "proton_nmr_guidance_used": False,
        "expected_carbon_atoms": None,
        "expected_region_summary": {},
        "proton_context": {},
        "raw_peak_count_before_context": len(peaks),
        "raw_peak_count_after_context": len(peaks),
        "context_filtered_peak_count": 0,
    }
    notes: list[str] = []
    expected_carbons: int | None = None
    expected_env: dict[str, int] = {}
    if smiles and smiles.strip():
        try:
            expected_carbons = expected_carbon_count_from_smiles(smiles)
            expected_env = expected_carbon_environment_summary(smiles)
            context_meta["smiles_guidance_used"] = True
            context_meta["expected_carbon_atoms"] = expected_carbons
            context_meta["expected_region_summary"] = expected_env
            notes.append(
                "SMILES-derived carbon count and region expectations were linked to the raw ¹³C FID peak scoring."
            )
        except StructureParseError:
            notes.append("SMILES guidance could not be applied to raw ¹³C FID scoring because the structure was invalid.")
    proton_context = _proton_context_from_text(proton_nmr_text)
    if proton_context:
        context_meta["proton_nmr_guidance_used"] = True
        context_meta["proton_context"] = proton_context
        notes.append(
            "Current ¹H NMR text was linked to raw ¹³C FID scoring to prioritize compatible anomeric, oxygenated, aromatic, and aliphatic carbon regions."
        )

    if not peaks:
        return (peaks, context_meta, notes)
    solvent_peaks = [peak for peak in peaks if peak.is_likely_solvent]
    non_solvent_peaks = [peak for peak in peaks if not peak.is_likely_solvent]
    if expected_carbons is None or expected_carbons <= 0:
        return (peaks, context_meta, notes)
    if len(non_solvent_peaks) <= expected_carbons + 2:
        return (peaks, context_meta, notes)

    max_intensity = max(abs(float(peak.intensity or 0.0)) for peak in non_solvent_peaks) or 1.0
    scored = [
        (
            _carbon13_peak_context_score(
                peak,
                max_intensity=max_intensity,
                expected_env=expected_env,
                proton_context=proton_context,
            ),
            peak,
        )
        for peak in non_solvent_peaks
    ]
    scored.sort(key=lambda item: (item[0], abs(float(item[1].intensity or 0.0))), reverse=True)
    retained_non_solvent = [peak for _, peak in scored[:expected_carbons]]
    retained = sorted(retained_non_solvent + solvent_peaks, key=lambda peak: peak.shift_ppm, reverse=True)
    dropped_count = len(peaks) - len(retained)
    context_meta["raw_peak_count_after_context"] = len(retained)
    context_meta["context_filtered_peak_count"] = dropped_count
    if dropped_count > 0:
        notes.append(
            f"Context-guided raw ¹³C peak filtering retained {len(retained_non_solvent)} non-solvent signal(s) closest to the SMILES-derived carbon count and suppressed {dropped_count} low-support candidate(s)."
        )
    return (retained, context_meta, notes)


def refine_carbon13_peaks_with_text_guidance(
    peaks: list[Carbon13Peak],
    *,
    carbon13_text: str | None = None,
    solvent: str | None = None,
    tolerance_ppm: float = _C13_TEXT_MATCH_TOLERANCE_PPM,
) -> tuple[list[Carbon13Peak], dict[str, Any], list[str]]:
    """Use supplied 13C text to filter detected peaks without fabricating missing ones."""
    guidance_meta: dict[str, Any] = {
        "carbon13_text_guidance_used": False,
        "reference_peak_count": 0,
        "matched_reference_peak_count": 0,
        "missing_reference_peak_count": 0,
        "filtered_unmatched_detected_peak_count": 0,
        "match_tolerance_ppm": tolerance_ppm,
        "peak_evidence_policy": "detected_peaks_only_no_reference_fabrication",
    }
    notes: list[str] = []
    if not carbon13_text or not carbon13_text.strip():
        return (peaks, guidance_meta, notes)

    try:
        reference_peaks = parse_carbon13_text(carbon13_text, solvent=solvent)
    except Carbon13ParseError as exc:
        guidance_meta["carbon13_text_guidance_error"] = str(exc)
        notes.append(f"13C NMR text guidance could not be applied because the text did not parse: {exc}")
        return (peaks, guidance_meta, notes)

    reference_non_solvent = [
        peak for peak in reference_peaks if not peak.is_likely_solvent
    ]
    guidance_meta["carbon13_text_guidance_used"] = True
    guidance_meta["reference_peak_count"] = len(reference_non_solvent)
    if not reference_non_solvent or not peaks:
        return (peaks, guidance_meta, notes)

    solvent_peaks = [peak for peak in peaks if peak.is_likely_solvent]
    candidate_peaks = [peak for peak in peaks if not peak.is_likely_solvent]
    used_candidate_indices: set[int] = set()
    matched_indices: set[int] = set()
    missing_reference_shifts: list[float] = []

    for reference_peak in reference_non_solvent:
        ranked_matches = sorted(
            (
                (abs(float(candidate.shift_ppm) - float(reference_peak.shift_ppm)), idx)
                for idx, candidate in enumerate(candidate_peaks)
                if idx not in used_candidate_indices
            ),
            key=lambda item: item[0],
        )
        if ranked_matches and ranked_matches[0][0] <= tolerance_ppm:
            _, matched_idx = ranked_matches[0]
            used_candidate_indices.add(matched_idx)
            matched_indices.add(matched_idx)
        else:
            missing_reference_shifts.append(round(float(reference_peak.shift_ppm), 3))

    matched_peaks = [candidate_peaks[idx] for idx in sorted(matched_indices)]
    guidance_meta["matched_reference_peak_count"] = len(matched_peaks)
    guidance_meta["missing_reference_peak_count"] = len(missing_reference_shifts)
    guidance_meta["missing_reference_shifts_ppm"] = missing_reference_shifts[:20]

    if not matched_peaks:
        notes.append(
            "13C NMR text guidance did not filter the detected peak list because no detected non-solvent peaks matched the supplied 13C shifts within tolerance."
        )
        return (peaks, guidance_meta, notes)

    filtered_count = max(0, len(candidate_peaks) - len(matched_peaks))
    guidance_meta["filtered_unmatched_detected_peak_count"] = filtered_count
    retained = sorted(matched_peaks + solvent_peaks, key=lambda peak: peak.shift_ppm, reverse=True)
    if filtered_count:
        notes.append(
            f"13C NMR text guidance retained {len(matched_peaks)} independently detected non-solvent peak(s) that matched supplied 13C shifts and suppressed {filtered_count} unmatched candidate(s)."
        )
    if missing_reference_shifts:
        notes.append(
            f"13C NMR text listed {len(missing_reference_shifts)} shift(s) that were not independently detected within {tolerance_ppm:.2f} ppm; those peaks were not fabricated."
        )
    return (retained, guidance_meta, notes)


def summarize_regions(peaks: list[Carbon13Peak]) -> list[Carbon13RegionSummary]:
    grouped: dict[str, list[float]] = {}
    for peak in peaks:
        grouped.setdefault(peak.region or "unclassified", []).append(peak.shift_ppm)
    return [
        Carbon13RegionSummary(region=region, count=len(values), shifts_ppm=sorted(values, reverse=True))
        for region, values in sorted(grouped.items())
    ]


def _region_summary_dict(peaks: list[Carbon13Peak]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for peak in peaks:
        counts[peak.region or "unclassified"] += 1
    return dict(counts)


def _dept_apt_score(peaks: list[Carbon13Peak], expected_env: dict[str, int]) -> float | None:
    typed = [peak for peak in peaks if peak.carbon_type and not peak.is_likely_solvent]
    if not typed:
        return None
    observed = Counter(peak.carbon_type for peak in typed)
    possible = 0
    matched = 0
    for label in ("C", "CH", "CH2", "CH3"):
        if observed.get(label) or expected_env.get(label):
            possible += max(observed.get(label, 0), expected_env.get(label, 0))
            matched += min(observed.get(label, 0), expected_env.get(label, 0))
    if possible == 0:
        return None
    return round(matched / possible, 4)


def analyze_carbon13(
    *,
    smiles: str,
    peaks: list[Carbon13Peak],
    solvent: str | None = None,
    sample_id: str | None = None,
) -> Carbon13AnalysisReport:
    try:
        structure = structure_summary_from_smiles(smiles)
        expected_carbons = expected_carbon_count_from_smiles(smiles)
        expected_env = expected_carbon_environment_summary(smiles)
    except StructureParseError:
        return Carbon13AnalysisReport(
            sample_id=sample_id,
            smiles=smiles,
            solvent=solvent,
            expected_carbon_atoms=0,
            observed_carbon_signals=len(peaks),
            delta_carbon_signals=len(peaks),
            label="invalid_input",
            confidence=0.0,
            peaks=peaks,
            notes=["Invalid SMILES; carbon count could not be computed."],
            structure=None,
        )

    non_solvent_peaks = [p for p in peaks if not p.is_likely_solvent]
    observed = len(non_solvent_peaks)
    delta = observed - expected_carbons
    solvent_peaks = [p for p in peaks if p.is_likely_solvent]
    impurity_peaks = [p for p in non_solvent_peaks if p.is_likely_impurity]
    solvent_warnings: list[str] = []
    if solvent_peaks:
        solvent_warnings.append(f"{len(solvent_peaks)} likely solvent carbon signal(s) detected and excluded from carbon-count comparison.")
    if impurity_peaks:
        solvent_warnings.append(f"{len(impurity_peaks)} non-solvent ¹³C signal(s) overlap embedded impurity-reference shifts and should be reviewed before signoff.")

    if delta == 0:
        label = "carbon_count_consistent"
        notes = ["Observed non-solvent ¹³C signal count matches the SMILES-derived carbon count."]
    elif delta < 0:
        label = "possible_overlap_or_missing_weak_carbons"
        notes = ["Observed ¹³C signals are fewer than expected; overlap, symmetry/equivalence, weak quaternary carbons, or low S/N are plausible explanations."]
    else:
        label = "possible_extra_carbons_or_impurity"
        notes = ["Observed ¹³C signals exceed the expected carbon count; possible impurity, solvent/artifact, duplicate peaks, or incorrect structure should be reviewed."]

    observed_regions = _region_summary_dict(non_solvent_peaks)
    region_summary = summarize_regions(peaks)
    dept_score = _dept_apt_score(peaks, expected_env)
    carbon_count_score = ratio_score(observed, expected_carbons, tolerance_fraction=0.20, absolute_tolerance=2.0)
    solvent_exclusion_score = round(1.0 - len(solvent_peaks) / max(1, len(peaks)), 4)

    # Region support is deliberately heuristic: reward carbonyl/aromatic/anomeric/O-N signals when the structure suggests such environments.
    expected_region_hints: dict[str, int] = {}
    if expected_env.get("carbonyl/carboxyl-like carbon", 0):
        expected_region_hints["carbonyl"] = expected_env["carbonyl/carboxyl-like carbon"]
    if expected_env.get("aromatic/alkene carbon", 0):
        expected_region_hints["aromatic"] = expected_env["aromatic/alkene carbon"]
    if expected_env.get("O/N-bearing protonated carbon", 0) or expected_env.get("O/N-bearing quaternary carbon", 0):
        expected_region_hints["O/N-bearing"] = expected_env.get("O/N-bearing protonated carbon", 0) + expected_env.get("O/N-bearing quaternary carbon", 0)

    region_hits = 0
    region_possible = 0
    for hint, count in expected_region_hints.items():
        region_possible += min(count, 3)
        if hint == "carbonyl":
            region_hits += min(sum(v for k, v in observed_regions.items() if "carbonyl" in k or "carboxyl" in k), min(count, 3))
        elif hint == "aromatic":
            region_hits += min(sum(v for k, v in observed_regions.items() if "aromatic" in k or "alkene" in k), min(count, 3))
        elif hint == "O/N-bearing":
            region_hits += min(sum(v for k, v in observed_regions.items() if "oxygenated" in k or "nitrogen" in k), min(count, 3))
    region_consistency_score = round(region_hits / region_possible, 4) if region_possible else 0.75

    if observed_regions.get("anomeric / acetal carbon", 0) >= 1:
        notes.append("Anomeric/acetal-region carbon signal(s) were detected.")
    if sum(v for k, v in observed_regions.items() if "oxygenated" in k or "nitrogen" in k) >= 3:
        notes.append("Multiple O/N-bearing carbon-region signals were detected, consistent with oxygenated/aminated scaffolds such as carbohydrates or aminoglycosides.")
    if dept_score is not None:
        notes.append(f"DEPT/APT carbon-type consistency score: {dept_score:.2f}.")

    score_parts = [0.45 * carbon_count_score, 0.30 * region_consistency_score, 0.15 * solvent_exclusion_score]
    total_weight = 0.90
    if dept_score is not None:
        score_parts.append(0.10 * dept_score)
        total_weight = 1.0
    carbon13_match_score = round(sum(score_parts) / total_weight, 4)
    confidence = round(max(0.0, min(0.96, 0.50 + 0.46 * carbon13_match_score)), 4)

    evidence_summary = [
        f"Carbon count score: {carbon_count_score:.2f}",
        f"Region consistency score: {region_consistency_score:.2f}",
        f"Solvent exclusion score: {solvent_exclusion_score:.2f}",
    ]
    if dept_score is not None:
        evidence_summary.append(f"DEPT/APT consistency score: {dept_score:.2f}")

    return Carbon13AnalysisReport(
        sample_id=sample_id,
        smiles=smiles,
        solvent=solvent,
        expected_carbon_atoms=expected_carbons,
        observed_carbon_signals=observed,
        delta_carbon_signals=delta,
        label=label,  # type: ignore[arg-type]
        confidence=confidence,
        peaks=peaks,
        region_summary=region_summary,
        solvent_warnings=solvent_warnings,
        notes=notes,
        carbon13_match_score=carbon13_match_score,
        carbon_count_score=carbon_count_score,
        region_consistency_score=region_consistency_score,
        solvent_exclusion_score=solvent_exclusion_score,
        dept_apt_consistency_score=dept_score,
        expected_region_summary=expected_env,
        observed_region_summary=observed_regions,
        evidence_summary=evidence_summary,
        structure=structure,
    )


def analyze_carbon13_text(smiles: str, carbon13_text: str, *, solvent: str | None = None, sample_id: str | None = None) -> Carbon13AnalysisReport:
    peaks = parse_carbon13_text(carbon13_text, solvent=solvent)
    return analyze_carbon13(smiles=smiles, peaks=peaks, solvent=solvent, sample_id=sample_id)
