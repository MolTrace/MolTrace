from __future__ import annotations

import csv
import io
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from .carbon13 import Carbon13ParseError, normalize_carbon_type, parse_carbon13_text
from .evidence import greedy_set_similarity
from .models import DeptAptAnalyzeResult, DeptAptPeak, DeptAptPreviewReport


class DeptAptParseError(ValueError):
    pass


_SHIFT_KEYS = ("shift_ppm", "ppm", "shift", "delta", "carbon_ppm", "c_ppm")
_PHASE_KEYS = ("phase", "sign", "polarity", "direction")
_TYPE_KEYS = ("carbon_type", "dept", "apt", "multiplicity", "attached_h", "type_label")
_EXPERIMENT_KEYS = ("experiment", "exp", "type", "experiment_type", "dept_type", "spectrum")
_INTENSITY_KEYS = ("intensity", "height", "area", "volume", "amplitude")
_ASSIGNMENT_KEYS = ("assignment", "label", "annotation")


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _norm_key(value: str) -> str:
    return "".join(char for char in str(value).strip().lower() if char.isalnum())


def _row_value(row: dict[str, Any], *keys: str) -> Any:
    normalized = {_norm_key(key): value for key, value in row.items() if key is not None}
    for key in keys:
        value = normalized.get(_norm_key(key))
        if value not in {None, ""}:
            return value
    return None


def normalize_dept_experiment(value: Any, *, filename: str = "") -> str:
    text = str(value or filename or "").strip().upper().replace(" ", "").replace("-", "").replace("_", "")
    if "DEPT90" in text or text == "90":
        return "DEPT90"
    if "DEPT135" in text or text == "135":
        return "DEPT135"
    if "DEPT" in text:
        return "DEPT"
    if "APT" in text:
        return "APT"
    return "UNKNOWN"


def normalize_phase(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"+", "pos", "positive", "up", "u", "1", "true", "p"}:
        return "positive"
    if text in {"-", "neg", "negative", "down", "d", "-1", "n"}:
        return "negative"
    return "unknown"


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
        raise DeptAptParseError("DEPT/APT upload is empty.")
    suffix = Path(filename.lower()).suffix
    if suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DeptAptParseError("Invalid JSON DEPT/APT table.") from exc
        if isinstance(payload, dict):
            payload = payload.get("peaks") or payload.get("dept_apt_peaks") or payload.get("signals")
        if not isinstance(payload, list):
            raise DeptAptParseError("JSON DEPT/APT upload must be a list of peak objects or an object with a peaks list.")
        return [row for row in payload if isinstance(row, dict)]
    if suffix in {".csv", ".tsv", ""}:
        delimiter = _sniff_delimiter(text, filename)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise DeptAptParseError("DEPT/APT CSV/TSV must include a header row.")
        return list(reader)
    raise DeptAptParseError("Unsupported DEPT/APT upload format. Use CSV, TSV, or JSON.")


def _normalize_explicit_carbon_type(value: Any) -> str | None:
    normalized = normalize_carbon_type(value)
    return normalized if normalized in {"C", "CH", "CH2", "CH3", "CH_OR_CH3", "CH2_OR_C"} else None


def normalize_apt_positive(value: Any) -> str:
    text = str(value or "CH_CH3").strip().upper().replace(" ", "").replace("-", "_")
    if text in {"CH2_C", "C_CH2", "CH2/C", "C/CH2", "CH2_OR_C"}:
        return "CH2_C"
    return "CH_CH3"


def infer_carbon_type_from_dept(
    *,
    experiment: str,
    phase: str,
    explicit_type: str | None = None,
    apt_positive: str = "CH_CH3",
) -> tuple[str | None, list[str]]:
    explicit = _normalize_explicit_carbon_type(explicit_type)
    if explicit:
        return explicit, []
    warnings: list[str] = []
    if experiment == "DEPT90":
        if phase == "positive":
            return "CH", []
        warnings.append("DEPT-90 positive peaks support CH carbons; absent/negative peaks are not definitive contradictions unless explicitly labeled.")
        return None, warnings
    if experiment == "DEPT135":
        if phase == "negative":
            return "CH2", []
        if phase == "positive":
            return "CH_OR_CH3", ["DEPT-135 positive peaks support CH or CH3; DEPT-135 alone does not separate CH from CH3."]
        warnings.append("DEPT-135 phase was not supplied; carbon type cannot be inferred reliably.")
        return None, warnings
    if experiment == "APT":
        positive_means_ch = normalize_apt_positive(apt_positive) == "CH_CH3"
        warnings.append("APT separates CH/CH3 from CH2/quaternary groups, but sign convention can vary and requires review.")
        if phase == "positive":
            return ("CH_OR_CH3" if positive_means_ch else "CH2_OR_C"), warnings
        if phase == "negative":
            return ("CH2_OR_C" if positive_means_ch else "CH_OR_CH3"), warnings
        warnings.append("APT phase was not supplied; carbon type cannot be inferred reliably.")
        return None, warnings
    if experiment == "DEPT":
        warnings.append("Generic DEPT row lacks DEPT-90/135 subtype; provide explicit carbon_type where possible.")
        return None, warnings
    warnings.append("DEPT/APT experiment type could not be detected.")
    return None, warnings


def parse_dept_apt_table(
    filename: str,
    content: bytes,
    *,
    experiment_type: str | None = None,
    apt_positive: str = "CH_CH3",
) -> DeptAptPreviewReport:
    rows = _rows_from_upload(filename, content)
    requested = normalize_dept_experiment(experiment_type)
    peaks: list[DeptAptPeak] = []
    experiments: list[str] = []
    warnings: list[str] = []
    for index, row in enumerate(rows, start=1):
        row_experiment = normalize_dept_experiment(_row_value(row, *_EXPERIMENT_KEYS), filename=filename)
        experiment = requested if requested != "UNKNOWN" else row_experiment
        shift = _safe_float(_row_value(row, *_SHIFT_KEYS))
        if shift is None:
            continue
        phase = normalize_phase(_row_value(row, *_PHASE_KEYS))
        explicit_type = _row_value(row, *_TYPE_KEYS)
        carbon_type, type_warnings = infer_carbon_type_from_dept(
            experiment=experiment,
            phase=phase,
            explicit_type=str(explicit_type) if explicit_type is not None else None,
            apt_positive=apt_positive,
        )
        peak_warnings = list(type_warnings)
        if not (0.0 <= shift <= 230.0):
            peak_warnings.append("Carbon shift is outside the usual 13C range.")
        intensity = _safe_float(_row_value(row, *_INTENSITY_KEYS))
        assignment_raw = _row_value(row, *_ASSIGNMENT_KEYS)
        peaks.append(
            DeptAptPeak(
                experiment=experiment,  # type: ignore[arg-type]
                shift_ppm=round(shift, 3),
                intensity=intensity,
                phase=phase,  # type: ignore[arg-type]
                carbon_type=carbon_type,  # type: ignore[arg-type]
                assignment=str(assignment_raw).strip() if assignment_raw not in {None, ""} else None,
                warnings=list(dict.fromkeys(peak_warnings)),
            )
        )
        experiments.append(experiment)
    if not peaks:
        raise DeptAptParseError("No valid DEPT/APT peaks were found. Expected columns like shift_ppm, phase, and experiment.")
    known = [experiment for experiment in experiments if experiment != "UNKNOWN"]
    detected = known[0] if len(set(known)) == 1 else ("DEPT" if known else "UNKNOWN")
    if detected == "UNKNOWN":
        warnings.append("DEPT/APT experiment type could not be confidently detected.")
    if any(peak.warnings for peak in peaks):
        warnings.append("One or more DEPT/APT peaks need manual review.")
    if detected == "APT":
        warnings.append("APT sign convention can vary; keep assignments ambiguous unless the convention or carbon_type is supplied.")
    if detected == "DEPT135":
        warnings.append("DEPT-135 positive peaks indicate CH or CH3 and do not separate them by themselves.")
    if detected in {"DEPT90", "DEPT135", "DEPT"}:
        warnings.append("Quaternary carbons may be absent from DEPT spectra.")
    typed = [peak for peak in peaks if peak.carbon_type]
    return DeptAptPreviewReport(
        filename=filename,
        experiment_detected=detected,  # type: ignore[arg-type]
        peak_count=len(peaks),
        peaks=peaks,
        warnings=list(dict.fromkeys(warnings)),
        metadata={
            "typed_peak_count": len(typed),
            "type_summary": dict(Counter(str(peak.carbon_type) for peak in typed)),
            "apt_positive_convention": normalize_apt_positive(apt_positive),
            "accepted_formats": ["csv", "tsv", "json"],
        },
    )


def analyze_dept_apt_preview(
    preview: DeptAptPreviewReport,
    *,
    carbon13_text: str | None = None,
    solvent: str | None = None,
) -> DeptAptAnalyzeResult:
    notes: list[str] = []
    warnings = list(preview.warnings)
    typed = [peak for peak in preview.peaks if peak.carbon_type]
    type_summary = dict(Counter(str(peak.carbon_type) for peak in typed))
    carbon13_count = 0
    matched_count = 0
    missing_count = 0
    extra_count = 0
    score: float | None = None
    peaks = preview.peaks
    if carbon13_text:
        try:
            carbon13_peaks = [peak for peak in parse_carbon13_text(carbon13_text, solvent=solvent) if not peak.is_likely_solvent]
            carbon13_count = len(carbon13_peaks)
            score_value, matches, unmatched_dept, unmatched_carbon13 = greedy_set_similarity(
                [peak.shift_ppm for peak in peaks],
                [peak.shift_ppm for peak in carbon13_peaks],
                sigma=1.2,
            )
            matched_count = len(matches)
            missing_count = len(unmatched_carbon13)
            extra_count = len(unmatched_dept)
            score = round(score_value, 4)
            matched_shifts = {
                round(match.observed_ppm, 3): match.expected_ppm
                for match in matches
            }
            peaks = [
                peak.model_copy(update={"matched_carbon13_shift_ppm": round(matched_shifts[round(peak.shift_ppm, 3)], 3)})
                if round(peak.shift_ppm, 3) in matched_shifts
                else peak
                for peak in peaks
            ]
            notes.append(f"DEPT/APT carbon shifts matched supplied 13C peak list with score {score_value:.2f}.")
            if unmatched_carbon13:
                notes.append(f"{len(unmatched_carbon13)} supplied non-solvent 13C peak(s) were not represented in the DEPT/APT table; quaternary carbons may be absent from DEPT.")
            if unmatched_dept:
                notes.append(f"{len(unmatched_dept)} DEPT/APT peak(s) were not matched to the supplied 13C text.")
        except Carbon13ParseError:
            warnings.append("Supplied 13C text could not be parsed for DEPT/APT cross-checking.")
    elif preview.experiment_detected in {"DEPT90", "DEPT135", "DEPT"}:
        warnings.append("No 13C text was supplied; quaternary carbons may be absent from DEPT and cannot be cross-checked.")
    if type_summary:
        notes.append("Carbon-type evidence summary: " + ", ".join(f"{key}: {value}" for key, value in sorted(type_summary.items())))
    oxygenated_typed = [
        peak
        for peak in typed
        if 50.0 <= peak.shift_ppm <= 110.0 and peak.carbon_type in {"CH", "CH2", "CH3", "CH_OR_CH3", "CH2_OR_C"}
    ]
    if len(oxygenated_typed) >= 2:
        notes.append(
            f"{len(oxygenated_typed)} typed peak(s) fall in the oxygenated/anomeric 13C region; review as possible O-bearing carbon-type evidence."
        )
    if preview.experiment_detected == "DEPT90":
        notes.append("DEPT-90 positive peaks support CH assignments; missing or negative peaks should not be treated as definitive contradictions without explicit labels.")
    if preview.experiment_detected == "DEPT135":
        notes.append("DEPT-135 negative peaks support CH2; positive peaks support CH or CH3 but do not separate CH from CH3 alone.")
    if preview.experiment_detected == "APT":
        notes.append("APT separates CH/CH3 from CH2/quaternary groups, but the sign convention can vary and requires review.")
    return DeptAptAnalyzeResult(
        preview=preview.model_copy(update={"peaks": peaks}),
        carbon13_peak_count=carbon13_count,
        matched_carbon13_count=matched_count,
        missing_carbon13_count=missing_count,
        extra_dept_apt_count=extra_count,
        typed_peak_count=len(typed),
        dept_apt_consistency_score=score,
        type_summary=type_summary,
        notes=list(dict.fromkeys(notes)),
        warnings=list(dict.fromkeys(warnings)),
    )


def find_dept_type_for_shift(peaks: list[DeptAptPeak], shift_ppm: float, *, tolerance: float = 1.2) -> DeptAptPeak | None:
    candidates = [peak for peak in peaks if peak.carbon_type and abs(peak.shift_ppm - shift_ppm) <= tolerance]
    if not candidates:
        return None
    return min(candidates, key=lambda peak: abs(peak.shift_ppm - shift_ppm))
