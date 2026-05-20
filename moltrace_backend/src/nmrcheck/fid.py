from __future__ import annotations

import io
import hashlib
import json
import math
import os
import re
import tarfile
import warnings
import zipfile
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Any

import numpy as np

from .baseline import (
    apply_bernstein_baseline_correction,
    apply_signal_free_smooth_baseline_polish,
    apply_simple_baseline_correction,
    evaluate_baseline_flatness,
    normalize_baseline_mode,
)
from .mnova_view import weak_peak_magnifier_view
from .models import (
    FIDPresetId,
    FIDPreviewReport,
    FIDProcessingMetadata,
    FIDProcessingPreset,
    FIDProcessingRecipe,
    FIDProcessingSettings,
    FIDQADiagnostics,
    Peak,
)
from .parser import normalize_nmr_text, parse_reference_nmr_text
from .raw_vault import RawVaultError, build_raw_upload_provenance, load_raw_archive_bytes
from .spectrum import (
    _apply_solvent_mask,
    _build_impurity_candidates,
    _build_preserved_spectrum_state,
    _build_reference_guided_nmr_text,
    _build_spectrum_comparison,
    _PREVIEW_DOWNSAMPLING_METHOD,
    _downsample_points,
    _estimates_to_peaks,
    _infer_peak_estimates,
    _peaks_to_nmr_text,
    _prepare_trace_display_points,
    _reference_assignments_to_peaks,
    _select_target_proton_count,
    _solvent_mask_windows,
)


class FIDProcessingError(ValueError):
    pass


FIDError = FIDProcessingError


@dataclass(frozen=True)
class _BrukerDataset:
    root: Path
    fid_path: Path
    acqus_path: Path
    pulseprogram_path: Path | None
    pdata_path: Path | None


@dataclass(frozen=True)
class _VarianDataset:
    root: Path
    fid_path: Path
    procpar_path: Path
    log_path: Path | None


@dataclass(frozen=True)
class _DatasetDetection:
    vendor: str
    dataset_root: str | None
    files_found: list[str]
    required_files_present: bool
    warnings: list[str]
    metadata: dict[str, Any]
    score: int


@dataclass(frozen=True)
class FIDZipInspection:
    filename: str
    vendor_detected: str
    dataset_root: str | None
    required_files_present: bool
    files_found: list[str]
    warnings: list[str]
    metadata: dict[str, Any]


_MAX_ZIP_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = _MAX_ZIP_UNCOMPRESSED_BYTES
_MAX_ARCHIVE_FILES = 5_000
_BRUKER_PARAM_RE = re.compile(r"^##\$([^=]+)=\s*(.*)$")
_VARIAN_SIMPLE_PARAM_RE = re.compile(r"^([A-Za-z][\w.]*)\s+(.+)$")
_REQUIRED_BRUKER_FILES = {"fid", "acqus"}
_OPTIONAL_BRUKER_FILES = {"pulseprogram", "acqu", "procs", "proc", "title", "pdata"}
_REQUIRED_VARIAN_FILES = {"fid", "procpar"}
_OPTIONAL_VARIAN_FILES = {"log", "text", "phasefile"}
_FID_PRESET_ORDER: tuple[FIDPresetId, ...] = (
    "baseline_preserve",
    "balanced",
    "sensitive_weak_peaks",
    "higher_resolution",
    "custom",
)
_FID_PRESET_SETTINGS: dict[FIDPresetId, dict[str, Any]] = {
    "baseline_preserve": {
        "zero_fill_factor": 2,
        "fourier_transform": "fft_1d",
        "apodization_mode": "none",
        "line_broadening_hz": 0.0,
        "apply_group_delay": True,
        "auto_phase": True,
        "phase_mode": "auto",
        "auto_baseline": False,
        "baseline_correction": "preserve",
        "baseline_order": 3,
        "peak_sensitivity": 0.1,
        "mask_solvent_regions": True,
    },
    "balanced": {
        "zero_fill_factor": 2,
        "fourier_transform": "fft_1d",
        "apodization_mode": "exponential",
        "line_broadening_hz": 0.3,
        "apply_group_delay": True,
        "auto_phase": True,
        "phase_mode": "auto",
        "auto_baseline": True,
        "baseline_correction": "bernstein",
        "baseline_order": 3,
        "peak_sensitivity": 0.12,
        "mask_solvent_regions": True,
    },
    "sensitive_weak_peaks": {
        "zero_fill_factor": 2,
        "fourier_transform": "fft_1d",
        "apodization_mode": "exponential",
        "line_broadening_hz": 0.7,
        "apply_group_delay": True,
        "auto_phase": True,
        "phase_mode": "auto",
        "auto_baseline": True,
        "baseline_correction": "bernstein",
        "baseline_order": 3,
        "peak_sensitivity": 0.06,
        "mask_solvent_regions": True,
    },
    "higher_resolution": {
        "zero_fill_factor": 4,
        "fourier_transform": "fft_1d",
        "apodization_mode": "exponential",
        "line_broadening_hz": 0.05,
        "apply_group_delay": True,
        "auto_phase": True,
        "phase_mode": "auto",
        "auto_baseline": True,
        "baseline_correction": "bernstein",
        "baseline_order": 3,
        "peak_sensitivity": 0.1,
        "mask_solvent_regions": True,
    },
    "custom": {},
}
_FID_PRESET_LABELS: dict[FIDPresetId, str] = {
    "baseline_preserve": "Baseline preserve",
    "balanced": "Balanced",
    "sensitive_weak_peaks": "Sensitive weak peaks",
    "higher_resolution": "Higher resolution",
    "custom": "Custom",
}
_FID_PRESET_DESCRIPTIONS: dict[FIDPresetId, str] = {
    "baseline_preserve": (
        "Preserves the transformed FID spectrum state with no line broadening or "
        "baseline subtraction, then reports baseline flatness for review."
    ),
    "balanced": "Conservative default for routine Bruker or Varian/Agilent 1D FID review with auto phase and Bernstein baseline correction.",
    "sensitive_weak_peaks": "Adds mild apodization and lower peak threshold for weak signals with Bernstein baseline correction.",
    "higher_resolution": (
        "Uses more zero filling and minimal line broadening for tighter peak shape with Bernstein baseline correction."
    ),
    "custom": "Preserves manually selected processing controls.",
}
_RAW_FID_MNOVA_ZERO_FILL_FACTOR = 3
_RAW_FID_MNOVA_C13_LINE_BROADENING_HZ = 2.0
_RAW_FID_MNOVA_BASELINE_ORDER = 3
# Display point budget for the raw-FID preview. The previous 4000 was far
# too coarse for a full 1H window: a 7 Hz triplet (~14 Hz wide) collapsed
# into a single decimation bucket, so multiplet structure was invisible and
# sharp peaks looked broken/disjointed. 16000 points gives ~3 points/Hz at
# 400 MHz over 12 ppm, enough to render doublets-of-doublets, triplets and
# quartets cleanly. Source rationale: MestreNova manual pp. 109, 140-141
# (zero-filling raises "apparent digital resolution"; the on-screen trace
# must carry that resolution through to be useful).
_RAW_FID_MNOVA_C13_PREVIEW_POINTS = 16000
_RAW_FID_MNOVA_H1_PREVIEW_POINTS = 16000
# First-point correction — MestreNova manual p. 136: "multiply the first
# point of the FID by 0.5 before FT". The discrete FT treats the FID as
# periodic, so an uncorrected first point creates a constant vertical
# baseline displacement (peaks that sit off / protrude through the
# baseline). 0.5 is the manual's stated default.
_RAW_FID_MNOVA_FIRST_POINT_SCALE = 0.5
# Trapezoidal apodization ramp fraction for 1H — MestreNova manual p. 137
# names the Trapezoidal window as the fix for "'sinc' artifacts resulting
# from truncation of the FID". The window holds unit weight across the
# resolution-bearing early FID, then ramps linearly to zero over the final
# fraction below. 0.30 ramps only the last third (decayed-signal + noise
# for a properly acquired 1H dataset), so it removes the truncation step
# without the linewidth penalty of an exponential window — the manual
# (pp. 128, 131) is explicit that exponential LB decreases 1H resolution.
_RAW_FID_MNOVA_TRAPEZOID_RAMP_FRACTION = 0.30
_RAW_FID_NOISE_RMS_SPAN_POINTS = 7
_RAW_FID_SOLVENT_NEGATIVE_LOBE_SIGMA_LIMIT = 3.0
_RAW_FID_SOLVENT_NEGATIVE_LOBE_PEAK_FRACTION_LIMIT = 0.02
_RAW_FID_CARBON13_SOLVENT_FLOOR_PPM = 49.0
_RAW_FID_CARBON13_SOLVENT_FLOOR_WINDOW = (
    48.2,
    50.2,
    "13C solvent carbon near 49 ppm",
)
_RAW_FID_PROCESS_CACHE_VERSION = "raw-fid-solvent-display-v3"
_RAW_FID_PROCESS_CACHE_MAX_ENTRIES = 12
_RAW_FID_PROCESS_CACHE: OrderedDict[str, FIDPreviewReport] = OrderedDict()
_RAW_FID_PROCESS_CACHE_LOCK = Lock()


@contextmanager
def _suppress_known_nmrglue_warnings() -> Any:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message='The chemical shift referencing was not corrected for "sr".',
            category=UserWarning,
            module=r"nmrglue\.fileio\.bruker",
        )
        warnings.filterwarnings(
            "ignore",
            message=r"Failed to determine udic parameters for dim: .*",
            category=UserWarning,
            module=r"nmrglue\.fileio\.bruker",
        )
        warnings.filterwarnings(
            "ignore",
            message="Error reading the pulse program",
            category=UserWarning,
            module=r"nmrglue\.fileio\.bruker",
        )
        warnings.filterwarnings(
            "ignore",
            message="invalid value encountered in divide",
            category=RuntimeWarning,
            module=r"nmrglue\.process\.proc_autophase",
        )
        yield


def normalize_fid_preset_id(value: str | None) -> FIDPresetId:
    normalized = (value or "balanced").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "sensitive": "sensitive_weak_peaks",
        "weak_peaks": "sensitive_weak_peaks",
        "higher": "higher_resolution",
        "resolution": "higher_resolution",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in _FID_PRESET_SETTINGS:
        return "balanced"
    return normalized  # type: ignore[return-value]


def normalize_phase_mode(value: str | None) -> str:
    normalized = (value or "auto").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "automatic": "auto",
        "acme": "auto_acme",
        "peak_minima": "auto_peak_minima",
        "peak_minimum": "auto_peak_minima",
        "manual_phase": "manual",
        "off": "none",
        "preserve": "none",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {"auto", "auto_acme", "auto_peak_minima", "manual", "none"} else "auto"


def fid_preset_label(preset_id: str | None) -> str:
    return _FID_PRESET_LABELS[normalize_fid_preset_id(preset_id)]


def available_fid_presets() -> list[FIDProcessingPreset]:
    presets: list[FIDProcessingPreset] = []
    for preset_id in _FID_PRESET_ORDER:
        presets.append(
            FIDProcessingPreset(
                id=preset_id,
                label=_FID_PRESET_LABELS[preset_id],
                description=_FID_PRESET_DESCRIPTIONS[preset_id],
                settings=dict(_FID_PRESET_SETTINGS[preset_id]),
            )
        )
    return presets


def normalize_apodization_mode(value: str | None) -> str:
    normalized = str(value or "exponential").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"none", "off", "disabled", "no_apodization", "preserve"}:
        return "none"
    if normalized in {"exp", "exponential", "exponential_line_broadening", "line_broadening"}:
        return "exponential"
    if normalized in {
        "sine",
        "sine_bell",
        "sinebell",
        "sinbell",
        "sine_window",
        "sine_bell_window",
    }:
        return "sine_bell"
    if normalized in {
        "trapezoid",
        "trapezoidal",
        "trap",
        "trapezoidal_window",
        "trapezium",
    }:
        return "trapezoidal"
    return "exponential"


def fid_settings_from_preset(
    *,
    selected_preset: str | None = None,
    zero_fill_factor: int | None = None,
    fourier_transform: str | None = None,
    apodization_mode: str | None = None,
    line_broadening_hz: float | None = None,
    apply_group_delay: bool | None = None,
    auto_phase: bool | None = None,
    auto_baseline: bool | None = None,
    phase_mode: str | None = None,
    phase_p0: float | None = None,
    phase_p1: float | None = None,
    baseline_correction: str | None = None,
    baseline_order: int | None = None,
    baseline_lock_visual_only: bool | None = None,
    peak_sensitivity: float | None = None,
    mask_solvent_regions: bool | None = None,
    max_preview_points: int | None = None,
    display_mode: str | None = None,
    vertical_gain: float | None = None,
    debug_preview: bool | None = None,
) -> FIDProcessingSettings:
    preset_id = normalize_fid_preset_id(selected_preset)
    values = dict(_FID_PRESET_SETTINGS["balanced" if preset_id == "custom" else preset_id])
    if display_mode is not None:
        normalized_display_mode = (
            str(display_mode).strip().lower().replace("-", "_").replace(" ", "_")
        )
        if normalized_display_mode in {"weak_peak_magnifier", "weak_peak_magnifier_view"}:
            display_mode = "magnifier"
        elif normalized_display_mode not in {"real", "magnifier"}:
            display_mode = "real"
        else:
            display_mode = normalized_display_mode
    if phase_mode is not None:
        phase_mode = normalize_phase_mode(phase_mode)
    if baseline_correction is not None:
        baseline_correction = normalize_baseline_mode(baseline_correction)
    if apodization_mode is not None:
        apodization_mode = normalize_apodization_mode(apodization_mode)
    overrides: dict[str, Any] = {
        "zero_fill_factor": zero_fill_factor,
        "fourier_transform": fourier_transform,
        "apodization_mode": apodization_mode,
        "line_broadening_hz": line_broadening_hz,
        "apply_group_delay": apply_group_delay,
        "auto_phase": auto_phase,
        "auto_baseline": auto_baseline,
        "phase_mode": phase_mode,
        "phase_p0": phase_p0,
        "phase_p1": phase_p1,
        "baseline_correction": baseline_correction,
        "baseline_order": baseline_order,
        "baseline_lock_visual_only": baseline_lock_visual_only,
        "peak_sensitivity": peak_sensitivity,
        "mask_solvent_regions": mask_solvent_regions,
        "max_preview_points": max_preview_points,
        "display_mode": display_mode,
        "vertical_gain": vertical_gain,
        "debug_preview": debug_preview,
    }
    values.update({key: value for key, value in overrides.items() if value is not None})
    return FIDProcessingSettings(selected_preset=preset_id, **values)


def _is_safe_member_name(name: str) -> bool:
    if not name or name.startswith(("/", "\\")):
        return False
    parts = Path(name).parts
    return not any(part in {"..", ""} for part in parts)


def _is_tar_gz_upload(filename: str, content: bytes) -> bool:
    if not filename.lower().endswith((".tar.gz", ".tgz")):
        return False
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz"):
            return True
    except tarfile.TarError:
        return False


def _archive_member_names(content: bytes, *, filename: str) -> tuple[str, list[str]]:
    if zipfile.is_zipfile(io.BytesIO(content)):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = [info for info in archive.infolist() if not info.is_dir()]
                if not members:
                    raise FIDProcessingError("The uploaded raw FID archive is empty.")
                unsafe = [info.filename for info in members if not _is_safe_member_name(info.filename)]
                if unsafe:
                    raise FIDProcessingError(
                        "The uploaded raw FID archive contains an unsafe relative path."
                    )
                return ("zip", sorted(info.filename for info in members))
        except zipfile.BadZipFile as exc:
            raise FIDProcessingError(
                "Upload a valid .zip or .tar.gz file containing a Bruker or Varian/Agilent 1D dataset folder."
            ) from exc
    if _is_tar_gz_upload(filename, content):
        try:
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
                members = [member for member in archive.getmembers() if member.isfile()]
                if not members:
                    raise FIDProcessingError("The uploaded raw FID archive is empty.")
                unsafe = [member.name for member in members if not _is_safe_member_name(member.name)]
                if unsafe:
                    raise FIDProcessingError(
                        "The uploaded raw FID archive contains an unsafe relative path."
                    )
                return ("tar.gz", sorted(member.name for member in members))
        except tarfile.TarError as exc:
            raise FIDProcessingError(
                "Upload a valid .zip or .tar.gz file containing a Bruker or Varian/Agilent 1D dataset folder."
            ) from exc
    raise FIDProcessingError(
        "Upload a valid .zip or .tar.gz file containing a Bruker or Varian/Agilent 1D dataset folder."
    )


def _zip_files_by_directory(files_found: list[str]) -> dict[str, set[str]]:
    by_dir: dict[str, set[str]] = {}
    for name in files_found:
        path = Path(name)
        parent = str(path.parent) if str(path.parent) != "." else ""
        by_dir.setdefault(parent, set()).add(path.name.lower())
    return by_dir


def _detect_bruker_members(files_found: list[str]) -> _DatasetDetection:
    by_dir = _zip_files_by_directory(files_found)
    best_root: str | None = None
    best_score = -1
    for root, basenames in by_dir.items():
        score = len(_REQUIRED_BRUKER_FILES & basenames) * 10 + len(
            _OPTIONAL_BRUKER_FILES & basenames
        )
        if score > best_score:
            best_root = root
            best_score = score
    root_files = by_dir.get(best_root or "", set())
    required_present = _REQUIRED_BRUKER_FILES.issubset(root_files)
    warnings: list[str] = []
    if best_score <= 0:
        warnings.append("No Bruker dataset root was detected.")
    if "fid" not in root_files:
        warnings.append("Missing Bruker raw FID file named 'fid'.")
    if "acqus" not in root_files:
        warnings.append("Missing Bruker acquisition parameter file named 'acqus'.")
    if any("/pdata/" in f.replace("\\", "/").lower() for f in files_found):
        warnings.append(
            "Processed Bruker pdata files were detected; raw beta processing uses fid/acqus."
        )
    return _DatasetDetection(
        vendor="Bruker",
        dataset_root=best_root,
        files_found=files_found[:250],
        required_files_present=required_present,
        warnings=warnings,
        metadata={
            "required_files": sorted(_REQUIRED_BRUKER_FILES),
            "optional_files_seen": sorted(_OPTIONAL_BRUKER_FILES & root_files),
            "file_count": len(files_found),
        },
        score=best_score,
    )


def _detect_varian_members(files_found: list[str]) -> _DatasetDetection:
    by_dir = _zip_files_by_directory(files_found)
    best_root: str | None = None
    best_score = -1
    for root, basenames in by_dir.items():
        score = len(_REQUIRED_VARIAN_FILES & basenames) * 10 + len(
            _OPTIONAL_VARIAN_FILES & basenames
        )
        if root.lower().endswith(".fid"):
            score += 3
        if score > best_score:
            best_root = root
            best_score = score
    root_files = by_dir.get(best_root or "", set())
    required_present = _REQUIRED_VARIAN_FILES.issubset(root_files)
    warnings: list[str] = []
    if best_score <= 0:
        warnings.append("No Varian/Agilent dataset root was detected.")
    if "fid" not in root_files:
        warnings.append("Missing Varian/Agilent raw FID file named 'fid'.")
    if "procpar" not in root_files:
        warnings.append("Missing Varian/Agilent acquisition parameter file named 'procpar'.")
    return _DatasetDetection(
        vendor="Varian/Agilent",
        dataset_root=best_root,
        files_found=files_found[:250],
        required_files_present=required_present,
        warnings=warnings,
        metadata={
            "required_files": sorted(_REQUIRED_VARIAN_FILES),
            "optional_files_seen": sorted(_OPTIONAL_VARIAN_FILES & root_files),
            "file_count": len(files_found),
            "expected_vendor": "Varian/Agilent",
        },
        score=best_score,
    )


def inspect_zip_members(content: bytes, *, filename: str = "dataset.zip") -> FIDZipInspection:
    _archive_format, files_found = _archive_member_names(content, filename=filename)

    bruker = _detect_bruker_members(files_found)
    varian = _detect_varian_members(files_found)
    if bruker.required_files_present and not varian.required_files_present:
        detection = bruker
    elif varian.required_files_present and not bruker.required_files_present:
        detection = varian
    else:
        detection = varian if varian.score > bruker.score else bruker
    vendor = detection.vendor if detection.score > 0 else "unknown"
    return FIDZipInspection(
        filename=filename,
        vendor_detected=vendor,
        dataset_root=detection.dataset_root,
        required_files_present=detection.required_files_present,
        files_found=detection.files_found,
        warnings=detection.warnings,
        metadata=detection.metadata,
    )


def _coerce_bruker_value(raw: str) -> Any:
    value = raw.strip()
    if value.startswith("<") and value.endswith(">"):
        return value[1:-1]
    if not value:
        return ""
    try:
        if re.fullmatch(r"[-+]?\d+", value):
            return int(value)
        if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", value):
            return float(value)
    except Exception:
        return value
    return value


def _coerce_varian_value(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    try:
        if re.fullmatch(r"[-+]?\d+", value):
            return int(value)
        if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", value):
            return float(value)
    except Exception:
        return value
    return value


def _unwrap_param_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "values" in value:
            value = value["values"]
        elif "value" in value:
            value = value["value"]
    if isinstance(value, (list, tuple)) and value:
        return _unwrap_param_value(value[0])
    if isinstance(value, bytes):
        return value.decode("latin-1", errors="replace")
    return value


def _read_bruker_acqus(path: Path) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for raw_line in path.read_text(encoding="latin-1", errors="replace").splitlines():
        match = _BRUKER_PARAM_RE.match(raw_line.strip())
        if not match:
            continue
        key, raw_value = match.groups()
        params[key.strip()] = _coerce_bruker_value(raw_value)
    return params


def _read_varian_procpar(path: Path) -> dict[str, Any]:
    params: dict[str, Any] = {}
    lines = [line.rstrip() for line in path.read_text(encoding="latin-1", errors="replace").splitlines()]
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        simple = _VARIAN_SIMPLE_PARAM_RE.match(line)
        if simple and len(line.split()) == 2:
            name, raw_value = simple.groups()
            params[name.strip()] = _coerce_varian_value(raw_value)
            index += 1
            continue
        name = line.split()[0]
        if index + 2 < len(lines):
            value_line = lines[index + 2].strip()
            parts = value_line.split()
            if parts and re.fullmatch(r"\d+", parts[0]) and len(parts) > 1:
                params[name] = _coerce_varian_value(" ".join(parts[1:]))
            elif parts:
                params[name] = _coerce_varian_value(value_line)
        index += 3
    return params


def _param(params: dict[str, Any], *names: str) -> Any:
    lowered = {key.lower(): _unwrap_param_value(value) for key, value in params.items()}
    for name in names:
        if name in params:
            return _unwrap_param_value(params[name])
        lowered_value = lowered.get(name.lower())
        if lowered_value is not None:
            return lowered_value
    return None


def _param_float(params: dict[str, Any], *names: str) -> float | None:
    value = _param(params, *names)
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalize_nucleus_label(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(_unwrap_param_value(value)).strip()
    if not raw:
        return None
    token = re.sub(r"[^A-Z0-9]", "", raw.upper())
    if any(marker in token for marker in ("13C", "C13", "CARBON13")) or token == "CARBON":
        return "13C"
    if token in {"1H", "H1", "PROTON"} or (
        token.startswith("H") and "1" in token and "13" not in token
    ):
        return "1H"
    if "19F" in token or "F19" in token:
        return "19F"
    if "31P" in token or "P31" in token:
        return "31P"
    return raw.strip()


def _raw_fid_axis_looks_carbon13(x_values: np.ndarray) -> bool:
    finite = x_values[np.isfinite(x_values)]
    if finite.size < 2:
        return False
    ppm_low = float(np.min(finite))
    ppm_high = float(np.max(finite))
    return (ppm_high - ppm_low) >= 40.0 or ppm_high >= 80.0


def _window_contains_ppm(windows: list[tuple[float, float, str]], ppm: float) -> bool:
    return any(
        min(float(low), float(high)) <= ppm <= max(float(low), float(high))
        for low, high, _label in windows
    )


def _resolve_raw_fid_solvent_display_windows(
    *,
    solvent: str | None,
    nucleus: str,
    x_values: np.ndarray,
) -> tuple[list[tuple[float, float, str]], str, bool, bool]:
    normalized_nucleus = _normalize_nucleus_label(nucleus) or str(nucleus or "").strip()
    axis_looks_carbon = _raw_fid_axis_looks_carbon13(x_values)
    effective_nucleus = (
        "13C" if normalized_nucleus == "13C" or axis_looks_carbon else normalized_nucleus
    )
    windows = _solvent_mask_windows(solvent, nucleus=effective_nucleus or "1H")

    added_carbon13_floor_window = False
    if (
        effective_nucleus == "13C"
        and axis_looks_carbon
        and not windows
        and not _window_contains_ppm(windows, _RAW_FID_CARBON13_SOLVENT_FLOOR_PPM)
    ):
        windows = [*windows, _RAW_FID_CARBON13_SOLVENT_FLOOR_WINDOW]
        added_carbon13_floor_window = True

    return windows, effective_nucleus, axis_looks_carbon, added_carbon13_floor_window


def _resolve_raw_fid_nucleus(params: dict[str, Any], requested: str) -> str:
    detected = _param(
        params,
        "NUC1",
        "NUC",
        "OBSNUC",
        "TN",
        "tn",
        "nucleus",
    )
    return (
        _normalize_nucleus_label(detected)
        or _normalize_nucleus_label(requested)
        or requested.strip()
        or "1H"
    )


def _apply_raw_fid_mnova_constraints(
    settings: FIDProcessingSettings,
    *,
    nucleus: str,
) -> tuple[FIDProcessingSettings, dict[str, Any], list[str]]:
    normalized = _normalize_nucleus_label(nucleus) or nucleus.strip() or "1H"
    detail: dict[str, Any] = {
        "applied": False,
        "scope": "raw_fid_only",
        "nucleus": normalized,
        "manual_source": "MestreNova Manual, advised 1D processing",
        "processed_uploads_touched": False,
    }
    notes: list[str] = []

    if normalized == "13C":
        # MestreNova Advised Processing for 13C (manual p. 106, p. 129):
        #   3x zero-fill · exponential apodization LB 2.0 Hz ·
        #   Regions-Analysis auto phase · Bernstein polynomial baseline
        #   (order 3). The 2.0 Hz exponential also damps the FID tail, so a
        #   separate truncation window is unnecessary for carbon.
        constrained = settings.model_copy(
            update={
                "zero_fill_factor": _RAW_FID_MNOVA_ZERO_FILL_FACTOR,
                "apodization_mode": "exponential",
                "line_broadening_hz": _RAW_FID_MNOVA_C13_LINE_BROADENING_HZ,
                "phase_mode": "auto",
                "auto_phase": True,
                "baseline_correction": "bernstein",
                "baseline_order": _RAW_FID_MNOVA_BASELINE_ORDER,
                "auto_baseline": True,
                "max_preview_points": max(
                    int(settings.max_preview_points),
                    _RAW_FID_MNOVA_C13_PREVIEW_POINTS,
                ),
            }
        )
        detail.update(
            {
                "applied": True,
                "zero_fill_factor": _RAW_FID_MNOVA_ZERO_FILL_FACTOR,
                "apodization_mode": "exponential",
                "line_broadening_hz": _RAW_FID_MNOVA_C13_LINE_BROADENING_HZ,
                "phase_mode": "auto",
                "phase_reference": "MolTrace automatic 1D phase correction",
                "baseline_correction": "bernstein",
                "baseline_order": _RAW_FID_MNOVA_BASELINE_ORDER,
                "first_point_scale": _RAW_FID_MNOVA_FIRST_POINT_SCALE,
                "max_preview_points": constrained.max_preview_points,
            }
        )
        notes.append(
            "Raw 13C FID advised processing applied: 3x zero-fill, exponential "
            "LB 2.0 Hz, first-point correction 0.5, auto phase, and Bernstein-3 "
            "baseline correction."
        )
        return constrained, detail, notes

    if normalized == "1H":
        # MestreNova Advised Processing for 1H (manual p. 106, p. 140):
        #   3x zero-fill · resolution-preserving apodization · NO exponential
        #   line broadening (manual pp. 128, 131 — an exponential window
        #   "increase[s] linewidth, which is to say, a decrease in the
        #   resolution") · Regions-Analysis auto phase · Bernstein
        #   polynomial baseline (order 3).
        #
        # MestreNova's exact 1H window ("Stanning") is proprietary and not
        # defined in the manual, so we use the manual's explicitly named,
        # fully specified resolution-preserving truncation window instead —
        # Trapezoidal (p. 137) — which preserves fine multiplet structure
        # (dd, t, q, anomeric couplings) while removing the truncation step
        # that makes peaks look broken / disjointed. line_broadening_hz is
        # forced to 0.0 so no exponential broadening is applied.
        constrained = settings.model_copy(
            update={
                "zero_fill_factor": _RAW_FID_MNOVA_ZERO_FILL_FACTOR,
                "apodization_mode": "trapezoidal",
                "line_broadening_hz": 0.0,
                "phase_mode": "auto",
                "auto_phase": True,
                "baseline_correction": "bernstein",
                "baseline_order": _RAW_FID_MNOVA_BASELINE_ORDER,
                "auto_baseline": True,
                "max_preview_points": max(
                    int(settings.max_preview_points),
                    _RAW_FID_MNOVA_H1_PREVIEW_POINTS,
                ),
            }
        )
        detail.update(
            {
                "applied": True,
                "zero_fill_factor": _RAW_FID_MNOVA_ZERO_FILL_FACTOR,
                "apodization_mode": "trapezoidal",
                "line_broadening_hz": 0.0,
                "trapezoid_ramp_fraction": _RAW_FID_MNOVA_TRAPEZOID_RAMP_FRACTION,
                "phase_mode": "auto",
                "phase_reference": "MolTrace automatic 1D phase correction",
                "baseline_correction": "bernstein",
                "baseline_order": _RAW_FID_MNOVA_BASELINE_ORDER,
                "first_point_scale": _RAW_FID_MNOVA_FIRST_POINT_SCALE,
                "max_preview_points": constrained.max_preview_points,
            }
        )
        notes.append(
            "Raw 1H FID advised processing applied: 3x zero-fill, trapezoidal "
            "apodization (no exponential line broadening — preserves multiplet "
            "resolution), first-point correction 0.5, auto phase, and "
            "Bernstein-3 baseline correction."
        )
        return constrained, detail, notes

    detail["reason"] = "no_raw_fid_constraints_for_nucleus"
    return settings, detail, notes


def _raw_fid_process_cache_key(
    *,
    filename: str,
    content: bytes,
    nucleus: str,
    solvent: str | None,
    reference_ppm: float | None,
    reference_nmr_text: str | None,
    settings: FIDProcessingSettings,
    expected_total_h: int | None,
    expected_non_labile_h: int | None,
) -> str:
    payload = {
        "version": _RAW_FID_PROCESS_CACHE_VERSION,
        "filename": filename,
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "nucleus": _normalize_nucleus_label(nucleus) or nucleus.strip() or "1H",
        "solvent": solvent or "",
        "reference_ppm": reference_ppm,
        "reference_nmr_text_sha256": hashlib.sha256(
            (reference_nmr_text or "").encode("utf-8")
        ).hexdigest(),
        "settings": settings.model_dump(mode="json"),
        "expected_total_h": expected_total_h,
        "expected_non_labile_h": expected_non_labile_h,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _raw_fid_cached_report_copy(
    report: FIDPreviewReport,
    *,
    hit: bool,
    raw_upload_provenance: dict[str, Any],
) -> FIDPreviewReport:
    copied = report.model_copy(deep=True)
    cache_meta = {
        "hit": bool(hit),
        "scope": "raw_fid_only",
        "key_version": _RAW_FID_PROCESS_CACHE_VERSION,
        "processed_uploads_touched": False,
    }
    analysis_artifact_policy = {
        **copied.processing_metadata.analysis_artifact_policy,
        "processing_input_source": raw_upload_provenance.get("processing_input_source"),
        "processing_loaded_from_vault": raw_upload_provenance.get(
            "processing_loaded_from_vault",
            False,
        ),
        "raw_archive_id": raw_upload_provenance.get("raw_archive_id"),
        "raw_sha256": raw_upload_provenance.get("sha256"),
        "storage_backend": raw_upload_provenance.get("storage_backend"),
        "object_key": raw_upload_provenance.get("object_key"),
    }
    metadata = {
        **copied.metadata,
        "raw_upload_provenance": raw_upload_provenance,
        "analysis_artifact_policy": analysis_artifact_policy,
        "raw_fid_processing_cache": cache_meta,
    }
    processing_metadata = copied.processing_metadata.model_copy(
        deep=True,
        update={
            "raw_upload_provenance": raw_upload_provenance,
            "analysis_artifact_policy": analysis_artifact_policy,
        },
    )
    return copied.model_copy(
        update={
            "metadata": metadata,
            "processing_metadata": processing_metadata,
        }
    )


def _get_raw_fid_process_cache(
    cache_key: str,
    *,
    raw_upload_provenance: dict[str, Any],
) -> FIDPreviewReport | None:
    with _RAW_FID_PROCESS_CACHE_LOCK:
        cached = _RAW_FID_PROCESS_CACHE.get(cache_key)
        if cached is None:
            return None
        _RAW_FID_PROCESS_CACHE.move_to_end(cache_key)
    return _raw_fid_cached_report_copy(
        cached,
        hit=True,
        raw_upload_provenance=raw_upload_provenance,
    )


def _store_raw_fid_process_cache(
    cache_key: str,
    report: FIDPreviewReport,
) -> FIDPreviewReport:
    returned = _raw_fid_cached_report_copy(
        report,
        hit=False,
        raw_upload_provenance=report.processing_metadata.raw_upload_provenance,
    )
    with _RAW_FID_PROCESS_CACHE_LOCK:
        _RAW_FID_PROCESS_CACHE[cache_key] = returned.model_copy(deep=True)
        _RAW_FID_PROCESS_CACHE.move_to_end(cache_key)
        while len(_RAW_FID_PROCESS_CACHE) > _RAW_FID_PROCESS_CACHE_MAX_ENTRIES:
            _RAW_FID_PROCESS_CACHE.popitem(last=False)
    return returned


def _safe_extract_zip(content: bytes, target_dir: Path) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files_seen = 0
            total_size = 0
            target_root = target_dir.resolve()
            for info in archive.infolist():
                if info.is_dir():
                    continue
                files_seen += 1
                if files_seen > _MAX_ARCHIVE_FILES:
                    raise FIDProcessingError(
                        "The uploaded raw FID zip contains too many files for beta FID processing."
                    )
                if not info.filename or info.filename.startswith(("/", "\\")):
                    raise FIDProcessingError(
                        "The uploaded raw FID zip contains an unsafe absolute path."
                    )
                parts = Path(info.filename).parts
                if any(part in {"..", ""} for part in parts):
                    raise FIDProcessingError(
                        "The uploaded raw FID zip contains an unsafe relative path."
                    )
                file_type = (info.external_attr >> 16) & 0o170000
                if file_type == 0o120000:
                    raise FIDProcessingError(
                        "The uploaded raw FID zip contains a symbolic link, which is not accepted."
                    )
                if file_type not in {0, 0o100000}:
                    raise FIDProcessingError(
                        "The uploaded raw FID zip contains a non-regular file, which is not accepted."
                    )
                total_size += int(info.file_size)
                if total_size > _MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise FIDProcessingError(
                        "The uploaded raw FID zip is too large for beta FID processing."
                    )
                destination = (target_root / info.filename).resolve()
                if os.path.commonpath([str(target_root), str(destination)]) != str(target_root):
                    raise FIDProcessingError(
                        "The uploaded Bruker zip escapes the extraction directory."
                    )
            archive.extractall(target_root)
    except zipfile.BadZipFile as exc:
        raise FIDProcessingError(
            "Upload a valid .zip file containing a Bruker or Varian/Agilent 1D dataset folder."
        ) from exc


def _safe_extract_tar_gz(content: bytes, target_dir: Path) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            files_seen = 0
            total_size = 0
            target_root = target_dir.resolve()
            for member in archive.getmembers():
                if member.isdir():
                    continue
                files_seen += 1
                if files_seen > _MAX_ARCHIVE_FILES:
                    raise FIDProcessingError(
                        "The uploaded raw FID tar.gz contains too many files for beta FID processing."
                    )
                if member.issym() or member.islnk():
                    raise FIDProcessingError(
                        "The uploaded raw FID tar.gz contains a link entry, which is not accepted."
                    )
                if not member.isfile():
                    raise FIDProcessingError(
                        "The uploaded raw FID tar.gz contains a non-regular file, which is not accepted."
                    )
                if not _is_safe_member_name(member.name):
                    raise FIDProcessingError(
                        "The uploaded raw FID tar.gz contains an unsafe relative path."
                    )
                total_size += int(member.size)
                if total_size > _MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise FIDProcessingError(
                        "The uploaded raw FID archive is too large for beta FID processing."
                    )
                destination = (target_root / member.name).resolve()
                if os.path.commonpath([str(target_root), str(destination)]) != str(target_root):
                    raise FIDProcessingError(
                        "The uploaded raw FID tar.gz escapes the extraction directory."
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise FIDProcessingError(
                        "The uploaded raw FID tar.gz contains an unreadable file."
                    )
                with source, destination.open("wb") as output:
                    output.write(source.read())
    except tarfile.TarError as exc:
        raise FIDProcessingError(
            "Upload a valid .zip or .tar.gz file containing a Bruker or Varian/Agilent 1D dataset folder."
        ) from exc


def _safe_extract_raw_archive(content: bytes, target_dir: Path, *, filename: str) -> str:
    archive_format, _files_found = _archive_member_names(content, filename=filename)
    if archive_format == "zip":
        _safe_extract_zip(content, target_dir)
    elif archive_format == "tar.gz":
        _safe_extract_tar_gz(content, target_dir)
    else:
        raise FIDProcessingError(
            "Upload a valid .zip or .tar.gz file containing a Bruker or Varian/Agilent 1D dataset folder."
        )
    return archive_format


def _find_bruker_dataset(root: Path) -> _BrukerDataset:
    candidates: list[Path] = []
    fid_folders: set[Path] = set()
    acqus_folders: set[Path] = set()
    for fid_path in root.rglob("fid"):
        if not fid_path.is_file():
            continue
        parent = fid_path.parent
        fid_folders.add(parent)
        if (parent / "acqus").is_file():
            candidates.append(parent)
    for acqus_path in root.rglob("acqus"):
        if acqus_path.is_file():
            acqus_folders.add(acqus_path.parent)
    if not candidates:
        if fid_folders and not acqus_folders:
            raise FIDProcessingError(
                "Bruker-style fid file was found, but the required acqus file is missing."
            )
        if acqus_folders and not fid_folders:
            raise FIDProcessingError(
                "Bruker-style acqus file was found, but the required fid file is missing."
            )
        raise FIDProcessingError(
            "No Bruker 1D dataset was found. Expected a folder containing fid and acqus files."
        )
    candidates.sort(key=lambda path: (len(path.relative_to(root).parts), str(path).lower()))
    dataset_root = candidates[0]
    return _BrukerDataset(
        root=dataset_root,
        fid_path=dataset_root / "fid",
        acqus_path=dataset_root / "acqus",
        pulseprogram_path=(
            dataset_root / "pulseprogram"
            if (dataset_root / "pulseprogram").is_file()
            else None
        ),
        pdata_path=(dataset_root / "pdata") if (dataset_root / "pdata").exists() else None,
    )


def _find_varian_dataset(root: Path) -> _VarianDataset:
    candidates: list[Path] = []
    fid_folders: set[Path] = set()
    procpar_folders: set[Path] = set()
    for fid_path in root.rglob("fid"):
        if not fid_path.is_file():
            continue
        parent = fid_path.parent
        fid_folders.add(parent)
        if (parent / "procpar").is_file():
            candidates.append(parent)
    for procpar_path in root.rglob("procpar"):
        if procpar_path.is_file():
            procpar_folders.add(procpar_path.parent)
    if not candidates:
        if fid_folders and not procpar_folders:
            raise FIDProcessingError(
                "Varian/Agilent-style fid file was found, but the required procpar file is missing."
            )
        if procpar_folders and not fid_folders:
            raise FIDProcessingError(
                "Varian/Agilent-style procpar file was found, but the required fid file is missing."
            )
        raise FIDProcessingError(
            "No Varian/Agilent 1D dataset was found. Expected a folder containing fid and procpar files."
        )
    candidates.sort(
        key=lambda path: (
            0 if path.name.lower().endswith(".fid") else 1,
            len(path.relative_to(root).parts),
            str(path).lower(),
        )
    )
    dataset_root = candidates[0]
    return _VarianDataset(
        root=dataset_root,
        fid_path=dataset_root / "fid",
        procpar_path=dataset_root / "procpar",
        log_path=(dataset_root / "log") if (dataset_root / "log").is_file() else None,
    )


def _read_with_nmrglue(dataset: _BrukerDataset) -> tuple[dict[str, Any], np.ndarray] | None:
    try:
        import nmrglue as ng  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        with _suppress_known_nmrglue_warnings():
            dic, data = ng.bruker.read(str(dataset.root))
    except Exception:
        return None
    acqus = dict(dic.get("acqus", {})) if isinstance(dic, dict) else {}
    return (acqus, np.asarray(data))


def _read_varian_with_nmrglue(dataset: _VarianDataset) -> tuple[dict[str, Any], np.ndarray]:
    try:
        import nmrglue as ng  # type: ignore[import-not-found]
    except Exception as exc:
        raise FIDProcessingError(
            "Varian/Agilent raw FID beta processing requires nmrglue. Install with: uv sync --extra fid"
        ) from exc
    try:
        with _suppress_known_nmrglue_warnings():
            dic, data = ng.varian.read(str(dataset.root))
    except Exception as exc:
        raise FIDProcessingError(
            "nmrglue could not read the Varian/Agilent dataset. Confirm the archive contains a valid 1D fid and procpar."
        ) from exc
    procpar = dict(dic.get("procpar", {})) if isinstance(dic, dict) else {}
    return (procpar, np.asarray(data))


def _read_minimal_bruker_fid(dataset: _BrukerDataset, params: dict[str, Any]) -> np.ndarray:
    bytorda = int(_param_float(params, "BYTORDA") or 0)
    dtypa = int(_param_float(params, "DTYPA") or 0)
    endian = ">" if bytorda else "<"
    dtype = np.dtype(f"{endian}f8") if dtypa == 2 else np.dtype(f"{endian}i4")
    raw = np.frombuffer(dataset.fid_path.read_bytes(), dtype=dtype)
    if raw.size < 8:
        raise FIDProcessingError("The Bruker fid file is too small to process.")
    if raw.size % 2 == 0:
        return raw[0::2].astype(float) + 1j * raw[1::2].astype(float)
    return raw.astype(float)


def _is_complex_fid(data: np.ndarray) -> bool:
    return bool(np.iscomplexobj(np.asarray(data)))


def _flatten_1d_fid(data: np.ndarray) -> np.ndarray:
    data = np.asarray(data).squeeze()
    if data.ndim == 0:
        raise FIDProcessingError("The raw fid data did not contain a usable 1D array.")
    if data.ndim > 1:
        data = data.reshape(-1)
    if data.size < 8:
        raise FIDProcessingError("The raw fid data is too short to process.")
    return data.astype(np.complex128, copy=False)


def _maybe_remove_group_delay(
    fid: np.ndarray,
    params: dict[str, Any],
    *,
    dataset_root: Path,
    settings: FIDProcessingSettings,
    warnings: list[str],
) -> tuple[np.ndarray, bool]:
    if not settings.apply_group_delay:
        return (fid, False)
    grpdly = _param_float(params, "GRPDLY")
    try:
        import nmrglue as ng  # type: ignore[import-not-found]

        try:
            with _suppress_known_nmrglue_warnings():
                dic, data = ng.bruker.read(str(dataset_root))
                corrected = ng.bruker.remove_digital_filter(dic, data)
            if _is_complex_fid(fid) and not _is_complex_fid(np.asarray(corrected)):
                raise FIDProcessingError("nmrglue returned non-complex corrected data.")
            corrected = _flatten_1d_fid(np.asarray(corrected))
            if corrected.size >= 8:
                return (corrected, True)
        except Exception:
            if (
                _is_complex_fid(fid)
                and grpdly is not None
                and math.isfinite(grpdly)
                and grpdly > 0
            ):
                warnings.append(
                    "Bruker digital-filter correction could not be applied without "
                    "losing complex FID orientation."
                )
    except Exception:
        pass

    if grpdly is None or not math.isfinite(grpdly) or grpdly <= 0:
        return (fid, False)
    points = int(round(grpdly))
    if points <= 0 or points >= fid.size // 4:
        warnings.append("Bruker group delay was present but outside the beta correction range.")
        return (fid, False)
    return (fid[points:], True)


def _next_power_of_two(value: int) -> int:
    return 1 << (max(1, int(value)) - 1).bit_length()


def _fid_apodization_window(
    size: int,
    params: dict[str, Any],
    line_broadening_hz: float,
    *,
    mode: str = "exponential",
) -> tuple[np.ndarray, dict[str, Any]]:
    normalized_mode = normalize_apodization_mode(mode)
    n = max(0, int(size))
    metadata: dict[str, Any] = {
        "apodization_mode": normalized_mode,
        "window_function": "none",
        "window_applied": False,
        "applied_before_fft": False,
        "fid_points": n,
        "line_broadening_hz": float(line_broadening_hz),
    }
    if n == 0:
        metadata["skip_reason"] = "empty_fid"
        return np.ones(0, dtype=float), metadata
    if normalized_mode == "none":
        metadata["skip_reason"] = "apodization_disabled"
        return np.ones(n, dtype=float), metadata

    if normalized_mode == "sine_bell":
        # Classic sine-bell apodization damps the beginning/end of the time
        # domain trace before FFT, reducing truncation ripple in dense raw FID
        # previews. The +1/(N+1) form avoids exact zeros at the endpoints.
        idx = np.arange(n, dtype=float)
        window = np.sin(math.pi * (idx + 1.0) / (n + 1.0))
        metadata.update(
            {
                "window_function": "sine_bell",
                "window_applied": True,
                "applied_before_fft": True,
                "first_weight": round(float(window[0]), 10),
                "last_weight": round(float(window[-1]), 10),
                "max_weight": round(float(np.max(window)), 10),
            }
        )
        return window, metadata

    if normalized_mode == "trapezoidal":
        # Trapezoidal apodization — MestreNova manual p. 137: explicitly the
        # window recommended to "avoid the 'sinc' artifacts resulting from
        # truncation of the FID". Unit weight is held across the early,
        # resolution-bearing part of the FID, then ramped linearly to zero
        # over the final fraction. Unlike an exponential window it does not
        # broaden lines (manual pp. 128, 131 — exponential LB decreases 1H
        # resolution), so fine multiplet structure is preserved while the
        # truncation step that produces broken-looking peaks is removed.
        ramp_fraction = float(_RAW_FID_MNOVA_TRAPEZOID_RAMP_FRACTION)
        ramp_fraction = min(0.95, max(0.0, ramp_fraction))
        plateau = max(1, int(round(n * (1.0 - ramp_fraction))))
        window = np.ones(n, dtype=float)
        if plateau < n:
            window[plateau:] = np.linspace(
                1.0, 0.0, n - plateau, endpoint=True, dtype=float
            )
        metadata.update(
            {
                "window_function": "trapezoidal",
                "window_applied": True,
                "applied_before_fft": True,
                "ramp_fraction": round(ramp_fraction, 6),
                "plateau_points": int(plateau),
                "first_weight": round(float(window[0]), 10),
                "last_weight": round(float(window[-1]), 10),
                "max_weight": 1.0,
            }
        )
        return window, metadata

    sw_h = _param_float(params, "SW_h", "SW_hz", "sw")
    if sw_h is None or sw_h <= 0:
        metadata["skip_reason"] = "missing_or_invalid_sweep_width"
        return np.ones(n, dtype=float), metadata
    if line_broadening_hz <= 0:
        metadata["skip_reason"] = "line_broadening_non_positive"
        return np.ones(n, dtype=float), metadata
    dwell = 1.0 / sw_h
    t = np.arange(n, dtype=float) * dwell
    window = np.exp(-math.pi * float(line_broadening_hz) * t)
    metadata.update(
        {
            "window_function": "exponential_line_broadening",
            "window_applied": True,
            "applied_before_fft": True,
            "dwell_time_sec": round(float(dwell), 12),
            "sweep_width_hz": round(float(sw_h), 6),
            "first_weight": round(float(window[0]), 10),
            "last_weight": round(float(window[-1]), 10),
            "max_weight": round(float(np.max(window)), 10),
        }
    )
    return window, metadata


def _apply_fid_apodization(
    fid: np.ndarray,
    params: dict[str, Any],
    line_broadening_hz: float,
    *,
    mode: str = "exponential",
) -> tuple[np.ndarray, dict[str, Any]]:
    working = np.array(fid, dtype=np.complex128, copy=True)
    window, metadata = _fid_apodization_window(
        working.size,
        params,
        line_broadening_hz,
        mode=mode,
    )
    if window.size:
        working = working * window
    return working, metadata


def _apply_line_broadening(
    fid: np.ndarray,
    params: dict[str, Any],
    line_broadening_hz: float,
    *,
    mode: str = "exponential",
) -> np.ndarray:
    windowed, _metadata = _apply_fid_apodization(
        fid,
        params,
        line_broadening_hz,
        mode=mode,
    )
    return windowed


def _phase_spectrum(spectrum: np.ndarray, *, ph0: float, ph1: float = 0.0, pivot: int | None = None) -> np.ndarray:
    size = int(np.asarray(spectrum).size)
    if size <= 1:
        return spectrum * np.exp(1j * math.radians(float(ph0)))
    pivot_index = size // 2 if pivot is None else max(0, min(size - 1, int(pivot)))
    ramp = (np.arange(size, dtype=float) - float(pivot_index)) / max(1.0, float(size - 1))
    phase = np.deg2rad(float(ph0) + float(ph1) * ramp)
    return spectrum * np.exp(1j * phase)


def apply_phase(
    spectrum: np.ndarray,
    *,
    p0: float = 0.0,
    p1: float = 0.0,
    pivot: int | None = None,
) -> np.ndarray:
    return _phase_spectrum(spectrum, ph0=p0, ph1=p1, pivot=pivot)


def phase_score(real: np.ndarray, imag: np.ndarray | None = None) -> float:
    finite = np.asarray(real, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return -1e30
    positive = float(np.sum(np.maximum(finite, 0.0)))
    negative = float(np.sum(np.abs(np.minimum(finite, 0.0))))
    high = float(np.percentile(np.abs(finite), 99.0))
    low = float(np.percentile(np.abs(finite), 50.0))
    if high <= 1e-12:
        return -1e30
    derivative = np.diff(finite)
    roughness = float(np.percentile(np.abs(derivative), 90.0)) / high if derivative.size else 0.0
    baseline_bias = abs(float(np.median(finite))) / high
    imag_penalty = 0.0
    if imag is not None:
        imag_finite = np.asarray(imag, dtype=float)
        imag_finite = imag_finite[np.isfinite(imag_finite)]
        if imag_finite.size:
            imag_penalty = float(np.percentile(np.abs(imag_finite), 95.0)) / high
    return (
        positive
        - 3.5 * negative
        - 0.5 * positive * baseline_bias
        - 0.05 * positive * roughness
        - 0.2 * positive * imag_penalty
        - low
    )


def _fallback_auto_phase_grid(
    spectrum: np.ndarray,
    *,
    include_p1: bool = True,
) -> tuple[np.ndarray, dict[str, Any]]:
    real_initial = np.real(spectrum)
    pivot = int(np.argmax(np.abs(real_initial))) if real_initial.size else None
    best_ph0 = 0.0
    best_ph1 = 0.0
    best_score = phase_score(np.real(spectrum), np.imag(spectrum))
    best = spectrum

    for ph0 in np.linspace(-180.0, 180.0, 73):
        phased = apply_phase(spectrum, p0=float(ph0), p1=0.0, pivot=pivot)
        score = phase_score(np.real(phased), np.imag(phased))
        if score > best_score:
            best_score = score
            best_ph0 = float(ph0)
            best = phased

    p1_values = np.linspace(-120.0, 120.0, 25) if include_p1 else [0.0]
    for ph0 in np.linspace(best_ph0 - 8.0, best_ph0 + 8.0, 33):
        for ph1 in p1_values:
            phased = apply_phase(spectrum, p0=float(ph0), p1=float(ph1), pivot=pivot)
            score = phase_score(np.real(phased), np.imag(phased))
            if score > best_score:
                best_score = score
                best_ph0 = float(ph0)
                best_ph1 = float(ph1)
                best = phased

    fine_p1_values = np.linspace(best_ph1 - 12.0, best_ph1 + 12.0, 13) if include_p1 else [0.0]
    for ph0 in np.linspace(best_ph0 - 1.5, best_ph0 + 1.5, 13):
        for ph1 in fine_p1_values:
            phased = apply_phase(spectrum, p0=float(ph0), p1=float(ph1), pivot=pivot)
            score = phase_score(np.real(phased), np.imag(phased))
            if score > best_score:
                best_score = score
                best_ph0 = float(ph0)
                best_ph1 = float(ph1)
                best = phased

    return (
        best,
        {
            "phase_mode": "auto_grid",
            "zero_order_degrees": round(best_ph0, 3),
            "first_order_degrees": round(best_ph1, 3),
            "pivot_index": int(pivot if pivot is not None else 0),
            "phase_score": round(float(best_score), 6),
            "phase_correction_applied": not (
                math.isclose(best_ph0, 0.0, abs_tol=1e-6)
                and math.isclose(best_ph1, 0.0, abs_tol=1e-6)
            ),
        },
    )


def _try_nmrglue_autophase(
    spectrum: np.ndarray,
    *,
    method: str,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    try:
        from nmrglue.process import proc_autophase  # type: ignore

        with _suppress_known_nmrglue_warnings():
            result = proc_autophase.autops(
                spectrum,
                method,
                return_phases=True,
                disp=False,
                maxiter=80,
            )
        if not isinstance(result, tuple) or len(result) != 2:
            return None
        phased, phases = result
        p0 = float(phases[0]) if len(phases) >= 1 else 0.0
        p1 = float(phases[1]) if len(phases) >= 2 else 0.0
        score = phase_score(np.real(phased), np.imag(phased))
        return (
            np.asarray(phased, dtype=np.complex128),
            {
                "phase_mode": f"auto_{method}",
                "zero_order_degrees": round(p0, 3),
                "first_order_degrees": round(p1, 3),
                "pivot_index": 0,
                "phase_score": round(float(score), 6),
                "phase_correction_applied": True,
                "phase_solver": "nmrglue.autops",
            },
        )
    except Exception:
        return None


def _auto_phase_spectrum(
    spectrum: np.ndarray,
    *,
    mode: str = "auto",
    phase_p0: float = 0.0,
    phase_p1: float = 0.0,
) -> tuple[np.ndarray, dict[str, Any], list[str]]:
    normalized_mode = normalize_phase_mode(mode)
    warnings: list[str] = []
    initial_score = phase_score(np.real(spectrum), np.imag(spectrum))
    if normalized_mode == "none":
        return (
            spectrum,
            {
                "phase_mode": "none",
                "zero_order_degrees": 0.0,
                "first_order_degrees": 0.0,
                "pivot_index": 0,
                "phase_score": round(float(initial_score), 6),
                "phase_correction_applied": False,
            },
            warnings,
        )
    if normalized_mode == "manual":
        phased = apply_phase(spectrum, p0=phase_p0, p1=phase_p1)
        return (
            phased,
            {
                "phase_mode": "manual",
                "zero_order_degrees": round(float(phase_p0), 3),
                "first_order_degrees": round(float(phase_p1), 3),
                "pivot_index": int(spectrum.size // 2 if spectrum.size else 0),
                "phase_score": round(float(phase_score(np.real(phased), np.imag(phased))), 6),
                "phase_correction_applied": not (
                    math.isclose(float(phase_p0), 0.0, abs_tol=1e-12)
                    and math.isclose(float(phase_p1), 0.0, abs_tol=1e-12)
                ),
            },
            warnings,
        )

    methods = ["acme", "peak_minima"] if normalized_mode == "auto" else [
        "acme" if normalized_mode == "auto_acme" else "peak_minima"
    ]
    best_result: tuple[np.ndarray, dict[str, Any]] | None = None
    best_score = initial_score
    for method in methods:
        result = _try_nmrglue_autophase(spectrum, method=method)
        if result is None:
            warnings.append(f"nmrglue auto phase {method} failed; fallback search will be used if needed.")
            continue
        score = float(result[1].get("phase_score", -1e30))
        if score > best_score:
            best_score = score
            best_result = result
            if normalized_mode != "auto":
                break

    if best_result is not None:
        return (best_result[0], best_result[1], warnings)

    phased, metadata = _fallback_auto_phase_grid(
        spectrum,
        include_p1=spectrum.size <= 32768,
    )
    if normalized_mode in {"auto_acme", "auto_peak_minima"}:
        metadata["requested_phase_mode"] = normalized_mode
    warnings.append("Used conservative grid-search automatic phase correction fallback.")
    return (phased, metadata, warnings)


def _flat_baseline_correct_real(values: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    raw = np.asarray(values, dtype=float).reshape(-1)
    if raw.size == 0:
        return (raw, {"method": "none", "baseline_locked_to_zero": False})

    finite = raw[np.isfinite(raw)]
    if finite.size == 0:
        corrected = np.zeros_like(raw)
        return (
            corrected,
            {
                "method": "signal_free_flat_baseline",
                "baseline_locked_to_zero": True,
                "baseline_model": "constant",
                "signal_free_fraction": 0.0,
                "baseline_slope": 0.0,
                "baseline_span": 0.0,
            },
        )

    centered = raw - float(np.median(finite))
    finite_centered = centered[np.isfinite(centered)]
    if finite_centered.size:
        high = float(np.max(finite_centered))
        low = float(np.min(finite_centered))
        orientation = -1 if abs(low) > abs(high) * 1.15 else 1
    else:
        orientation = 1
    oriented = centered * orientation
    finite_oriented = oriented[np.isfinite(oriented)]
    if finite_oriented.size == 0:
        corrected = np.zeros_like(oriented)
        return (
            corrected,
            {
                "method": "signal_free_flat_baseline",
                "baseline_locked_to_zero": True,
                "baseline_model": "constant",
                "orientation": orientation,
                "signal_free_fraction": 0.0,
                "baseline_slope": 0.0,
                "baseline_span": 0.0,
            },
        )

    median_value = float(np.median(finite_oriented))
    residual = oriented - median_value
    finite_residual = residual[np.isfinite(residual)]
    abs_residual = np.abs(finite_residual)
    if abs_residual.size:
        noise = (
            float(np.median(np.abs(finite_residual - float(np.median(finite_residual)))))
            * 1.4826
        )
        threshold = max(noise * 3.0, float(np.percentile(abs_residual, 45.0)), 1e-12)
    else:
        threshold = 1e-12
    signal_free_mask = np.isfinite(residual) & (np.abs(residual) <= threshold)
    if int(np.count_nonzero(signal_free_mask)) < max(12, raw.size // 40):
        cutoff = (
            float(np.percentile(np.abs(residual[np.isfinite(residual)]), 35.0))
            if finite_residual.size
            else threshold
        )
        signal_free_mask = np.isfinite(residual) & (np.abs(residual) <= max(cutoff, 1e-12))

    x_axis = np.linspace(-1.0, 1.0, raw.size)
    model_name = "constant"
    slope = 0.0
    intercept = median_value
    if int(np.count_nonzero(signal_free_mask)) >= 2:
        try:
            slope, intercept = np.polyfit(x_axis[signal_free_mask], oriented[signal_free_mask], 1)
            model_name = "linear"
        except Exception:
            slope = 0.0
            intercept = float(np.median(oriented[signal_free_mask]))
    elif int(np.count_nonzero(signal_free_mask)) == 1:
        intercept = float(oriented[signal_free_mask][0])

    baseline = slope * x_axis + intercept
    corrected = oriented - baseline
    zero_mask = signal_free_mask & np.isfinite(corrected)
    if int(np.count_nonzero(zero_mask)):
        corrected = corrected - float(np.median(corrected[zero_mask]))

    max_value = float(np.max(np.abs(corrected[np.isfinite(corrected)]))) if np.any(np.isfinite(corrected)) else 0.0
    if max_value > 0:
        corrected = corrected / max_value
        slope = float(slope) / max_value
    baseline_span = float(abs(slope) * 2.0)
    return (
        corrected,
        {
            "method": "signal_free_flat_baseline",
            "baseline_locked_to_zero": True,
            "baseline_model": model_name,
            "orientation": orientation,
            "signal_free_fraction": round(
                float(np.count_nonzero(signal_free_mask) / max(1, raw.size)),
                4,
            ),
            "baseline_slope": round(float(slope), 8),
            "baseline_span": round(baseline_span, 8),
        },
    )


def _baseline_correct_real(values: np.ndarray) -> np.ndarray:
    corrected, _metadata = _flat_baseline_correct_real(values)
    return corrected


def _smooth_fid_display_trace(
    points: list[tuple[float, float]],
    *,
    nucleus: str,
) -> tuple[list[tuple[float, float]], dict[str, Any]]:
    if not points:
        return (
            points,
            {
                "applied": False,
                "display_only": True,
                "evidence_trace_preserved": True,
                "method": "mnova_raw_fid_noise_envelope",
                "reason": "no_points",
            },
        )

    clean: list[tuple[float, float]] = []
    for x_raw, y_raw in points:
        x = float(x_raw)
        y = float(y_raw)
        if math.isfinite(x) and math.isfinite(y):
            clean.append((x, y))
    if len(clean) < _RAW_FID_NOISE_RMS_SPAN_POINTS:
        return (
            clean,
            {
                "applied": False,
                "display_only": True,
                "evidence_trace_preserved": True,
                "method": "mnova_raw_fid_noise_envelope",
                "reason": "too_few_points",
            },
        )

    y_values = np.asarray([y for _x, y in clean], dtype=float)
    abs_values = np.abs(y_values)
    signal_cutoff = float(np.percentile(abs_values, 60.0))
    signal_free_mask = abs_values <= signal_cutoff
    if int(np.count_nonzero(signal_free_mask)) < _RAW_FID_NOISE_RMS_SPAN_POINTS:
        signal_cutoff = float(np.percentile(abs_values, 75.0))
        signal_free_mask = abs_values <= signal_cutoff
    if int(np.count_nonzero(signal_free_mask)) < _RAW_FID_NOISE_RMS_SPAN_POINTS:
        signal_free_mask = np.ones_like(y_values, dtype=bool)

    baseline_center = float(np.median(y_values[signal_free_mask]))
    centered = y_values - baseline_center
    noise_reference = centered[signal_free_mask]
    noise_median = float(np.median(noise_reference))
    mad = float(np.median(np.abs(noise_reference - noise_median)))
    noise_sigma = 1.4826 * mad
    if not math.isfinite(noise_sigma) or noise_sigma <= 0.0:
        noise_sigma = float(np.sqrt(np.mean(np.square(noise_reference - noise_median))))
    if not math.isfinite(noise_sigma) or noise_sigma <= 0.0:
        noise_sigma = 0.0

    negative_limit = 0.0
    negative_lobes_limited = 0

    display = [
        (x, float(y))
        for (x, _old_y), y in zip(clean, centered, strict=True)
    ]
    return (
        display,
        {
            "applied": True,
            "display_only": True,
            "evidence_trace_preserved": True,
            "method": "mnova_raw_fid_noise_envelope",
            "smoothing_kernel": "none",
            "nucleus": _normalize_nucleus_label(nucleus) or nucleus,
            "baseline_centered": True,
            "baseline_center": round(baseline_center, 6),
            "signal_free_fraction": round(
                float(np.count_nonzero(signal_free_mask) / max(1, y_values.size)),
                4,
            ),
            "noise_sigma": round(float(noise_sigma), 6),
            "rms_calculation_span_points": _RAW_FID_NOISE_RMS_SPAN_POINTS,
            "negative_lobe_limit": round(float(negative_limit), 6),
            "negative_lobes_limited": negative_lobes_limited,
            "positive_peaks_preserved": True,
            "baseline_noise_preserved": True,
        },
    )


def _fine_tune_solvent_display_regions(
    points: list[tuple[float, float]],
    *,
    solvent: str | None,
    nucleus: str,
    noise_sigma: float | None = None,
) -> tuple[list[tuple[float, float]], dict[str, Any]]:
    base_meta: dict[str, Any] = {
        "applied": False,
        "display_only": True,
        "evidence_trace_preserved": True,
        "scope": "known_solvent_windows_only",
        "method": "solvent_window_negative_lobe_floor",
        "outside_solvent_windows_preserved": True,
        "positive_peaks_preserved": True,
        "negative_lobes_limited": 0,
        "windows": [],
    }
    if not points:
        base_meta["reason"] = "no_points"
        return points, base_meta

    clean: list[tuple[float, float]] = []
    for x_raw, y_raw in points:
        x = float(x_raw)
        y = float(y_raw)
        if math.isfinite(x) and math.isfinite(y):
            clean.append((x, y))
    if len(clean) < _RAW_FID_NOISE_RMS_SPAN_POINTS:
        base_meta["reason"] = "too_few_points"
        return clean, base_meta

    x_values = np.asarray([x for x, _y in clean], dtype=float)
    y_values = np.asarray([y for _x, y in clean], dtype=float)
    windows, effective_nucleus, carbon13_axis, added_carbon13_floor_window = _resolve_raw_fid_solvent_display_windows(
        solvent=solvent,
        nucleus=nucleus,
        x_values=x_values,
    )
    base_meta["nucleus"] = effective_nucleus
    base_meta["carbon13_axis_detected"] = carbon13_axis
    base_meta["added_carbon13_floor_window"] = added_carbon13_floor_window
    base_meta["windows"] = [
        {"low": round(float(low), 4), "high": round(float(high), 4), "label": label}
        for low, high, label in windows
    ]
    if not windows:
        base_meta["reason"] = "no_solvent_windows"
        return clean, base_meta

    out = y_values.copy()

    solvent_mask = np.zeros_like(y_values, dtype=bool)
    for low, high, _label in windows:
        lo = min(float(low), float(high))
        hi = max(float(low), float(high))
        solvent_mask |= (x_values >= lo) & (x_values <= hi)

    non_solvent = y_values[np.isfinite(y_values) & ~solvent_mask]
    if non_solvent.size:
        reference = non_solvent
        cutoff = float(np.percentile(np.abs(reference - float(np.median(reference))), 60.0))
        signal_free = reference[np.abs(reference - float(np.median(reference))) <= max(cutoff, 1e-12)]
        if signal_free.size >= _RAW_FID_NOISE_RMS_SPAN_POINTS:
            reference = signal_free
        local_median = float(np.median(reference))
        local_mad = float(np.median(np.abs(reference - local_median)))
        local_sigma = 1.4826 * local_mad
        if not math.isfinite(local_sigma) or local_sigma <= 0.0:
            local_sigma = float(np.sqrt(np.mean(np.square(reference - local_median))))
    else:
        local_sigma = 0.0

    sigma = float(noise_sigma or 0.0)
    if not math.isfinite(sigma) or sigma <= 0.0:
        sigma = local_sigma
    if not math.isfinite(sigma) or sigma <= 0.0:
        base_meta["reason"] = "noise_floor_unavailable"
        return clean, base_meta

    window_meta: list[dict[str, Any]] = []
    total_limited = 0
    for low, high, label in windows:
        lo = min(float(low), float(high))
        hi = max(float(low), float(high))
        mask = (x_values >= lo) & (x_values <= hi)
        if not int(np.count_nonzero(mask)):
            window_meta.append(
                {
                    "low": round(lo, 4),
                    "high": round(hi, 4),
                    "label": label,
                    "points_limited": 0,
                    "reason": "no_points_in_window",
                }
            )
            continue
        y_window = out[mask]
        local_positive_peak = float(np.max(y_window)) if y_window.size else 0.0
        is_carbon13_floor_window = (
            effective_nucleus == "13C"
            and carbon13_axis
            and lo <= _RAW_FID_CARBON13_SOLVENT_FLOOR_PPM <= hi
        )
        if is_carbon13_floor_window:
            floor = 0.0
            floor_mode = "baseline_floor"
        else:
            floor_magnitude = sigma * _RAW_FID_SOLVENT_NEGATIVE_LOBE_SIGMA_LIMIT
            if local_positive_peak > sigma * 6.0:
                floor_magnitude = min(
                    floor_magnitude,
                    local_positive_peak * _RAW_FID_SOLVENT_NEGATIVE_LOBE_PEAK_FRACTION_LIMIT,
                )
            floor = -max(float(floor_magnitude), 1e-12)
            floor_mode = "noise_floor"
        limited_mask = mask & (out < floor)
        limited_count = int(np.count_nonzero(limited_mask))
        if limited_count:
            out[limited_mask] = floor
            total_limited += limited_count
        window_meta.append(
            {
                "low": round(lo, 4),
                "high": round(hi, 4),
                "label": label,
                "negative_floor": round(float(floor), 6),
                "floor_mode": floor_mode,
                "points_limited": limited_count,
            }
        )

    display = [(x, float(y)) for (x, _old_y), y in zip(clean, out, strict=True)]
    return (
        display,
        {
            **base_meta,
            "applied": total_limited > 0,
            "negative_lobes_limited": total_limited,
            "noise_sigma": round(float(sigma), 6),
            "windows": window_meta,
            "reason": "applied" if total_limited > 0 else "no_solvent_negative_lobes_exceeded_floor",
        },
    )


def _apply_fid_baseline_correction(
    points: list[tuple[float, float]],
    settings: FIDProcessingSettings,
) -> tuple[list[tuple[float, float]], dict[str, Any], list[str]]:
    mode = normalize_baseline_mode(settings.baseline_correction)
    if not settings.auto_baseline:
        mode = "preserve"
    if mode == "bernstein":
        corrected, metadata, warnings = apply_bernstein_baseline_correction(
            points,
            order=settings.baseline_order,
        )
        if settings.auto_baseline and len(corrected) >= 32:
            polished, polish_metadata, polish_warnings = apply_signal_free_smooth_baseline_polish(
                corrected,
            )
            warnings.extend(note for note in polish_warnings if note not in warnings)
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
        corrected, metadata, warnings = apply_simple_baseline_correction(points, mode=mode)
    metadata.setdefault("mode", mode)
    metadata.setdefault("method", mode)
    metadata["order"] = int(settings.baseline_order) if mode == "bernstein" else metadata.get("order")
    metadata["automatic"] = bool(settings.auto_baseline and mode not in {"none", "preserve"})
    metadata["baseline_correction"] = mode
    return corrected, metadata, warnings


def _fallback_ppm_axis(
    params: dict[str, Any],
    size: int,
    *,
    vendor: str = "Bruker",
) -> tuple[np.ndarray, dict[str, Any]]:
    if vendor == "Varian/Agilent":
        sfo1 = _param_float(params, "sfrq", "reffrq", "SFRQ") or 400.0
        sw_h = _param_float(params, "sw", "SW")
        sw_ppm = (sw_h / sfo1) if sw_h and sfo1 else 12.0
        tof_hz = _param_float(params, "tof", "TOF")
        center_ppm = (tof_hz / sfo1) if tof_hz is not None and sfo1 else 4.7
        axis = np.linspace(center_ppm - sw_ppm / 2.0, center_ppm + sw_ppm / 2.0, size)
        return (
            axis,
            {
                "sfo1_mhz": round(float(sfo1), 6),
                "sw_hz": round(float(sw_h), 6) if sw_h is not None else None,
                "sw_ppm": round(float(sw_ppm), 6),
                "center_ppm": round(float(center_ppm), 6),
                "tof_hz": round(float(tof_hz), 6) if tof_hz is not None else None,
                "np": _param(params, "np"),
                "tn": _param(params, "tn"),
                "ppm_axis_orientation": "low_to_high_before_display_reverse",
            },
        )

    sfo1 = _param_float(params, "SFO1", "BF1") or 400.0
    sw_h = _param_float(params, "SW_h", "SW_hz")
    sw_ppm = _param_float(params, "SW")
    if sw_ppm is None or sw_ppm <= 0:
        sw_ppm = (sw_h / sfo1) if sw_h and sfo1 else 12.0
    center_ppm = _param_float(params, "O1P")
    if center_ppm is None:
        o1_hz = _param_float(params, "O1")
        center_ppm = (o1_hz / sfo1) if o1_hz is not None and sfo1 else 4.7
    axis = np.linspace(center_ppm - sw_ppm / 2.0, center_ppm + sw_ppm / 2.0, size)
    return (
        axis,
        {
            "sfo1_mhz": round(float(sfo1), 6),
            "sw_hz": round(float(sw_h), 6) if sw_h is not None else None,
            "sw_ppm": round(float(sw_ppm), 6),
            "center_ppm": round(float(center_ppm), 6),
            "td": _param(params, "TD"),
            "grpdly": _param(params, "GRPDLY"),
            "nucleus_from_acqus": _param(params, "NUC1"),
            "ppm_axis_orientation": "low_to_high_before_display_reverse",
        },
    )


def _maybe_nmrglue_ppm_axis(
    params: dict[str, Any],
    fid: np.ndarray,
    size: int,
    *,
    vendor: str = "Bruker",
) -> np.ndarray | None:
    try:
        import nmrglue as ng  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        if vendor == "Varian/Agilent":
            dic = {"procpar": params}
            with _suppress_known_nmrglue_warnings():
                udic = ng.varian.guess_udic(dic, fid)
        else:
            dic = {"acqus": params}
            with _suppress_known_nmrglue_warnings():
                udic = ng.bruker.guess_udic(dic, fid)
        udic[0]["size"] = int(size)
        uc = ng.fileiobase.uc_from_udic(udic)
        axis = np.asarray(uc.ppm_scale(), dtype=float)
        if axis.size == size and np.all(np.isfinite(axis)):
            if axis[0] > axis[-1]:
                axis = axis[::-1]
            return axis
    except Exception:
        return None
    return None


def _reference_target_from_text(reference_nmr_text: str | None) -> tuple[float | None, str | None]:
    if not reference_nmr_text or not reference_nmr_text.strip():
        return (None, None)
    try:
        _, assignments = parse_reference_nmr_text(reference_nmr_text)
    except Exception:
        return (None, None)
    if not assignments:
        return (None, None)
    anomeric = [
        assignment
        for assignment in assignments
        if 4.35 <= float(assignment.shift_ppm) <= 5.85
    ]
    if not anomeric:
        return (None, None)
    selected = max(anomeric, key=lambda assignment: float(assignment.shift_ppm))
    return (
        round(float(selected.shift_ppm), 6),
        "reference_text_anomeric_peak",
    )


def _select_single_reference_peak(
    points: list[tuple[float, float]],
    target_ppm: float | None,
) -> tuple[tuple[float, float] | None, str]:
    if target_ppm is None or not points:
        return (None, "none")
    target = float(target_ppm)
    window = 0.35 if 4.35 <= target <= 5.85 else 0.18
    candidates = [
        item
        for item in points
        if abs(float(item[0]) - target) <= window
    ]
    mode = "nearest_target_window"
    if not candidates and 4.35 <= target <= 5.85:
        candidates = [
            item
            for item in points
            if 4.35 <= float(item[0]) <= 5.85
        ]
        mode = "anomeric_window_fallback"
    if not candidates:
        candidates = points
        mode = "global_nearest_fallback"
    selected = min(
        candidates,
        key=lambda item: (
            abs(float(item[0]) - target),
            -abs(float(item[1])),
        ),
    )
    return (selected, mode)


def _reference_axis(
    points: list[tuple[float, float]],
    reference_ppm: float | None,
    reference_nmr_text: str | None,
) -> tuple[list[tuple[float, float]], float, dict[str, Any]]:
    if not points:
        return (points, 0.0, {"mode": "none", "selected_peak_count": 0})
    target_ppm = reference_ppm
    target_source = "explicit_reference_ppm" if reference_ppm is not None else None
    if target_ppm is None:
        target_ppm, target_source = _reference_target_from_text(reference_nmr_text)
    selected_peak, selection_mode = _select_single_reference_peak(points, target_ppm)
    if target_ppm is None or selected_peak is None:
        return (
            points,
            0.0,
            {
                "mode": "none",
                "selected_peak_count": 0,
                "target_source": target_source,
            },
        )
    observed_ppm = float(selected_peak[0])
    shift = float(target_ppm) - observed_ppm
    return (
        [(x + shift, y) for x, y in points],
        round(shift, 6),
        {
            "mode": selection_mode,
            "selected_peak_count": 1,
            "target_source": target_source,
            "target_ppm": round(float(target_ppm), 6),
            "observed_ppm": round(observed_ppm, 6),
            "observed_intensity": round(float(selected_peak[1]), 8),
        },
    )


def _finite_float_values(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float).reshape(-1)
    return values[np.isfinite(values)]


def _fid_saturation_clipping_proxy(fid: np.ndarray) -> float:
    fid = np.asarray(fid).reshape(-1)
    if fid.size == 0:
        return 0.0
    if np.iscomplexobj(fid):
        components = np.concatenate([np.real(fid), np.imag(fid)])
    else:
        components = np.asarray(fid, dtype=float)
    finite = _finite_float_values(np.asarray(components, dtype=float))
    if finite.size == 0:
        return 0.0
    max_abs = float(np.max(np.abs(finite)))
    if max_abs <= 0:
        return 0.0
    near_limits = np.abs(finite) >= max_abs * 0.999
    return round(float(np.count_nonzero(near_limits) / finite.size), 6)


def _fid_noise_estimate(values: np.ndarray) -> float:
    finite = _finite_float_values(values)
    if finite.size < 8:
        return 0.0
    centered = finite - float(np.median(finite))
    low_amplitude_limit = float(np.percentile(np.abs(centered), 65))
    noise_pool = centered[np.abs(centered) <= low_amplitude_limit]
    if noise_pool.size < 8:
        noise_pool = centered
    median = float(np.median(noise_pool))
    mad = float(np.median(np.abs(noise_pool - median)))
    noise = 1.4826 * mad
    if noise <= 1e-12 and finite.size > 1:
        noise = float(np.median(np.abs(np.diff(finite)))) / math.sqrt(2.0)
    return max(0.0, noise)


def _calculate_fid_qa(
    *,
    fid: np.ndarray,
    spectrum_real: np.ndarray,
    baseline_reference: np.ndarray,
) -> FIDQADiagnostics:
    finite_spectrum = _finite_float_values(spectrum_real)
    finite_baseline = _finite_float_values(baseline_reference)
    point_count = int(np.asarray(fid).size)
    warnings: list[str] = []

    if point_count == 0 or finite_spectrum.size == 0:
        return FIDQADiagnostics(
            quality_score=0.0,
            quality_label="failed",
            dynamic_range=0.0,
            noise_estimate=0.0,
            baseline_offset_ratio=0.0,
            saturation_clipping_proxy=0.0,
            point_count=point_count,
            warnings=["FID trace did not contain any usable points."],
        )

    signal = float(np.percentile(np.abs(finite_spectrum), 99.5))
    if signal <= 1e-12:
        return FIDQADiagnostics(
            quality_score=0.0,
            quality_label="failed",
            dynamic_range=0.0,
            noise_estimate=0.0,
            baseline_offset_ratio=0.0,
            saturation_clipping_proxy=_fid_saturation_clipping_proxy(fid),
            point_count=point_count,
            warnings=["FID trace appears empty or contains no measurable signal."],
        )

    noise = _fid_noise_estimate(finite_spectrum)
    noise_floor = noise if noise > 1e-12 else signal / 1_000_000.0
    dynamic_range = min(1_000_000.0, signal / noise_floor)
    baseline_source = finite_baseline if finite_baseline.size else finite_spectrum
    baseline_offset = abs(float(np.median(baseline_source)))
    baseline_signal = (
        float(np.percentile(np.abs(baseline_source), 99.5))
        if baseline_source.size
        else signal
    )
    baseline_offset_ratio = min(10.0, baseline_offset / max(baseline_signal, 1e-12))
    clipping_proxy = _fid_saturation_clipping_proxy(fid)
    score = 1.0

    if dynamic_range < 5:
        score -= 0.45
        warnings.append("Very low dynamic range; weak peaks may not be reliable.")
    elif dynamic_range < 15:
        score -= 0.2
        warnings.append("Limited dynamic range; review weak peak calls.")

    if baseline_offset_ratio > 0.6:
        score -= 0.3
        warnings.append("Large baseline offset remains after processing.")
    elif baseline_offset_ratio > 0.25:
        score -= 0.12
        warnings.append("Moderate baseline offset remains after processing.")

    if clipping_proxy > 0.08:
        score -= 0.45
        warnings.append("Saturation/clipping proxy is high for the uploaded FID.")
    elif clipping_proxy > 0.02:
        score -= 0.18
        warnings.append("Possible mild saturation/clipping pattern detected.")

    if point_count < 128:
        score -= 0.3
        warnings.append("FID point count is very low for trustworthy processing.")
    elif point_count < 512:
        score -= 0.08
        warnings.append("FID point count is lower than expected for routine 1D review.")

    nonfinite_count = int(np.asarray(spectrum_real).size - finite_spectrum.size)
    if nonfinite_count:
        score -= 0.2
        warnings.append("Non-finite values were encountered during FID processing.")

    score = round(max(0.0, min(1.0, score)), 3)
    if score >= 0.8:
        label = "good"
    elif score >= 0.55:
        label = "review"
    elif score >= 0.25:
        label = "poor"
    else:
        label = "failed"

    return FIDQADiagnostics(
        quality_score=score,
        quality_label=label,
        dynamic_range=round(float(dynamic_range), 3),
        noise_estimate=round(float(noise), 6),
        baseline_offset_ratio=round(float(baseline_offset_ratio), 6),
        saturation_clipping_proxy=clipping_proxy,
        point_count=point_count,
        warnings=warnings,
    )


def _digital_filter_correction_status(
    params: dict[str, Any],
    *,
    settings: FIDProcessingSettings,
    group_delay_applied: bool,
    vendor: str = "Bruker",
) -> str:
    if vendor != "Bruker":
        return "not_applicable"
    if not settings.apply_group_delay:
        return "disabled"
    if group_delay_applied:
        return "applied"
    grpdly = _param_float(params, "GRPDLY")
    if grpdly is not None and math.isfinite(grpdly) and grpdly > 0:
        return "not_applied"
    return "not_detected"


def _processing_parameters(settings: FIDProcessingSettings) -> dict[str, Any]:
    parameters = settings.model_dump(mode="json")
    parameters["selected_preset_label"] = fid_preset_label(settings.selected_preset)
    return parameters


def _recipe_from_processing_state(
    *,
    vendor_format_detected: str,
    nucleus: str,
    settings: FIDProcessingSettings,
    digital_filter_correction_status: str,
    phase_settings_detail: dict[str, Any] | None,
    baseline_correction_detail: dict[str, Any] | None,
    reference_ppm: float | None,
    solvent: str | None,
) -> FIDProcessingRecipe:
    phase = phase_settings_detail or {}
    baseline = baseline_correction_detail or {}
    baseline_mode = (
        baseline.get("baseline_correction")
        or baseline.get("mode")
        or baseline.get("method")
        or settings.baseline_correction
    )
    baseline_mode = normalize_baseline_mode(str(baseline_mode))
    apodization_mode = normalize_apodization_mode(settings.apodization_mode)
    if apodization_mode == "exponential" and settings.line_broadening_hz <= 0:
        apodization_mode = "none"
    return FIDProcessingRecipe(
        vendor=vendor_format_detected,
        nucleus=nucleus.strip() or "1H",
        processing_preset=settings.selected_preset,
        digital_filter_correction=digital_filter_correction_status,
        apodization_mode=apodization_mode,
        line_broadening_hz=settings.line_broadening_hz,
        zero_fill_factor=settings.zero_fill_factor,
        fourier_transform=settings.fourier_transform,
        phase_mode=str(phase.get("phase_mode") or settings.phase_mode or "auto"),
        phase_p0=float(phase.get("phase_p0") if phase.get("phase_p0") is not None else settings.phase_p0),
        phase_p1=float(phase.get("phase_p1") if phase.get("phase_p1") is not None else settings.phase_p1),
        baseline_correction=str(baseline_mode),
        baseline_order=int(baseline.get("baseline_order") or baseline.get("order") or settings.baseline_order),
        reference_ppm=reference_ppm,
        solvent=solvent,
        peak_sensitivity=settings.peak_sensitivity,
        mask_solvent_regions=settings.mask_solvent_regions,
        display_mode=settings.display_mode,
        vertical_gain=settings.vertical_gain,
        debug_preview=settings.debug_preview,
    )


def _metadata_from_preview(
    *,
    vendor_format_detected: str,
    dataset_folder: str,
    nucleus: str,
    solvent: str | None,
    reference_ppm: float | None,
    reference_shift_applied_ppm: float,
    reference_peak_selection: dict[str, Any],
    group_delay_applied: bool,
    phase_applied: bool,
    baseline_applied: bool,
    settings: FIDProcessingSettings,
    acquisition_parameters: dict[str, Any],
    fft_size: int,
    fid_points_before_zero_fill: int,
    apodization_detail: dict[str, Any] | None,
    phase_angle_degrees: float,
    phase_settings_detail: dict[str, float] | None = None,
    baseline_correction_detail: dict[str, Any] | None = None,
    digital_filter_correction_status: str,
    qa_diagnostics: FIDQADiagnostics,
    nmrglue_used: bool,
    peaks: list[Peak],
    warnings: list[str],
    raw_dataset_files_found: dict[str, bool],
    raw_upload_provenance: dict[str, Any] | None = None,
    pulseprogram_present: bool = False,
    pdata_present: bool = False,
) -> FIDProcessingMetadata:
    provenance = dict(raw_upload_provenance or {})
    processing_recipe = _recipe_from_processing_state(
        vendor_format_detected=vendor_format_detected,
        nucleus=nucleus,
        settings=settings,
        digital_filter_correction_status=digital_filter_correction_status,
        phase_settings_detail=phase_settings_detail,
        baseline_correction_detail=baseline_correction_detail,
        reference_ppm=reference_ppm,
        solvent=solvent,
    )
    return FIDProcessingMetadata(
        vendor_format_detected=vendor_format_detected,
        dataset_folder=dataset_folder,
        selected_preset=fid_preset_label(settings.selected_preset),
        nucleus=nucleus,
        solvent=solvent,
        reference_ppm=reference_ppm,
        reference_shift_applied_ppm=reference_shift_applied_ppm,
        reference_peak_selection=reference_peak_selection,
        group_delay_correction_applied=group_delay_applied,
        automatic_phase_correction=phase_applied,
        automatic_baseline_correction=baseline_applied,
        zero_filling={
            "factor": settings.zero_fill_factor,
            "fft_size": fft_size,
            "input_points": int(fid_points_before_zero_fill),
            "zero_filled_points_added": max(0, int(fft_size) - int(fid_points_before_zero_fill)),
        },
        line_broadening={
            "hz": settings.line_broadening_hz,
            "apodization_mode": processing_recipe.apodization_mode,
            "window_function": (apodization_detail or {}).get("window_function")
            or (
                "exponential_line_broadening"
                if processing_recipe.apodization_mode == "exponential"
                else "none"
            ),
            "window_applied": bool((apodization_detail or {}).get("window_applied", False)),
            "applied_before_fft": bool((apodization_detail or {}).get("applied_before_fft", False)),
            "window": dict(apodization_detail or {}),
        },
        phase_settings={
            "automatic": phase_applied,
            "phase_angle_degrees": phase_angle_degrees,
            "zero_order_degrees": (phase_settings_detail or {}).get("zero_order_degrees", phase_angle_degrees),
            "first_order_degrees": (phase_settings_detail or {}).get("first_order_degrees", 0.0),
            "pivot_index": int((phase_settings_detail or {}).get("pivot_index", 0)),
            "phase_mode": (phase_settings_detail or {}).get("phase_mode", "auto" if phase_applied else "none"),
            "phase_p0": (phase_settings_detail or {}).get("zero_order_degrees", phase_angle_degrees),
            "phase_p1": (phase_settings_detail or {}).get("first_order_degrees", 0.0),
            "phase_score": (phase_settings_detail or {}).get("phase_score"),
            "phase_correction_applied": (phase_settings_detail or {}).get("phase_correction_applied", phase_applied),
            "phase_solver": (phase_settings_detail or {}).get("phase_solver"),
            "phase_warnings": (phase_settings_detail or {}).get("phase_warnings", []),
        },
        baseline_correction={
            "automatic": baseline_applied,
            "method": (baseline_correction_detail or {}).get("method")
            or ("bernstein_polynomial" if baseline_applied else "none"),
            "mode": (baseline_correction_detail or {}).get("mode"),
            "baseline_correction": (baseline_correction_detail or {}).get("baseline_correction"),
            "order": (baseline_correction_detail or {}).get("order"),
            "baseline_order": (baseline_correction_detail or {}).get("order"),
            "coefficients": (baseline_correction_detail or {}).get("coefficients"),
            "baseline_points": (baseline_correction_detail or {}).get("baseline_points"),
            "correction_applied": (baseline_correction_detail or {}).get("correction_applied", baseline_applied),
            "baseline_locked_to_zero": bool(
                (baseline_correction_detail or {}).get(
                    "baseline_locked_to_zero",
                    baseline_applied,
                )
            ),
            "baseline_model": (baseline_correction_detail or {}).get("baseline_model"),
            "signal_free_fraction": (baseline_correction_detail or {}).get("signal_free_fraction"),
            "baseline_slope": (baseline_correction_detail or {}).get("baseline_slope"),
            "baseline_span": (baseline_correction_detail or {}).get("baseline_span"),
            "baseline_polish_applied": (baseline_correction_detail or {}).get(
                "baseline_polish_applied",
                False,
            ),
            "post_baseline_polish": (baseline_correction_detail or {}).get("post_baseline_polish"),
            "flatness_qa": (baseline_correction_detail or {}).get("flatness_qa"),
            "warnings": (baseline_correction_detail or {}).get("warnings", []),
        },
        digital_filter_correction_status=digital_filter_correction_status,
        qa_diagnostics=qa_diagnostics,
        processing_parameters=_processing_parameters(settings),
        processing_recipe=processing_recipe,
        acquisition_parameters=acquisition_parameters,
        raw_dataset_files_found=raw_dataset_files_found,
        raw_upload_provenance=provenance,
        analysis_artifact_policy={
            "raw_upload_treated_as_immutable": True,
            "raw_binary_modified": False,
            "original_archive_modified": False,
            "processing_operates_on": "temporary_extraction_and_in_memory_copies",
            "processing_outputs_are_derivative": True,
            "corrections_recorded_as_metadata": True,
            "raw_overwrite_allowed": False,
            "reprocessing_source": "original_raw_archive_sha256",
            "processing_input_source": provenance.get("processing_input_source"),
            "processing_loaded_from_vault": provenance.get("processing_loaded_from_vault", False),
            "raw_archive_id": provenance.get("raw_archive_id"),
            "raw_sha256": provenance.get("sha256"),
            "storage_backend": provenance.get("storage_backend"),
            "object_key": provenance.get("object_key"),
        },
        nmrglue_used=nmrglue_used,
        pulseprogram_present=pulseprogram_present,
        pdata_present=pdata_present,
        extracted_peak_list=peaks,
        reviewer_signoff_required=True,
        human_review_status="pending_review",
        warnings=warnings,
    )


def _archive_bytes_for_processing(
    *,
    content: bytes,
    provenance: dict[str, Any],
) -> tuple[bytes, dict[str, Any]]:
    """Load verified vault bytes for processing when an immutable vault object exists."""

    updated = dict(provenance)
    if updated.get("storage_path"):
        try:
            archive_bytes = load_raw_archive_bytes(updated)
        except RawVaultError as exc:
            raise FIDProcessingError(f"Could not load immutable raw archive from the vault: {exc}") from exc
        updated["processing_input_source"] = "immutable_vault_archive"
        updated["processing_loaded_from_vault"] = True
        return archive_bytes, updated
    updated["processing_input_source"] = "provided_upload_bytes_metadata_only"
    updated["processing_loaded_from_vault"] = False
    return bytes(content), updated


def process_bruker_1d_zip(
    *,
    filename: str,
    content: bytes,
    solvent: str | None = None,
    nucleus: str = "1H",
    reference_ppm: float | None = None,
    reference_nmr_text: str | None = None,
    settings: FIDProcessingSettings | None = None,
    expected_total_h: int | None = None,
    expected_non_labile_h: int | None = None,
    raw_upload_provenance: dict[str, Any] | None = None,
) -> FIDPreviewReport:
    if not filename.lower().endswith((".zip", ".tar.gz", ".tgz")):
        raise FIDProcessingError(
            "Raw FID beta accepts .zip or .tar.gz Bruker or Varian/Agilent 1D dataset folders only."
        )
    settings = settings or FIDProcessingSettings()
    if raw_upload_provenance is None:
        try:
            raw_upload_provenance = build_raw_upload_provenance(
                filename=filename,
                content=content,
                storage_dir=None,
            )
        except RawVaultError as exc:
            raise FIDProcessingError(str(exc)) from exc
    processing_content, raw_upload_provenance = _archive_bytes_for_processing(
        content=content,
        provenance=raw_upload_provenance,
    )
    cache_key = _raw_fid_process_cache_key(
        filename=filename,
        content=processing_content,
        nucleus=nucleus,
        solvent=solvent,
        reference_ppm=reference_ppm,
        reference_nmr_text=reference_nmr_text,
        settings=settings,
        expected_total_h=expected_total_h,
        expected_non_labile_h=expected_non_labile_h,
    )
    cached_report = _get_raw_fid_process_cache(
        cache_key,
        raw_upload_provenance=raw_upload_provenance,
    )
    if cached_report is not None:
        return cached_report
    inspection = inspect_zip_members(processing_content, filename=filename)
    warnings: list[str] = []
    # Do not mutate raw vendor files or immutable raw archive.
    # Processing operates on a temporary extraction tree and copied in-memory arrays only.
    with TemporaryDirectory(prefix="nmrcheck-fid-") as tmp:
        root = Path(tmp)
        archive_format = _safe_extract_raw_archive(processing_content, root, filename=filename)
        if inspection.vendor_detected == "Varian/Agilent":
            varian_dataset = _find_varian_dataset(root)
            params = _read_varian_procpar(varian_dataset.procpar_path)
            ng_params, data = _read_varian_with_nmrglue(varian_dataset)
            params = {**params, **ng_params}
            fid = np.array(_flatten_1d_fid(np.asarray(data)), dtype=np.complex128, copy=True)
            nmrglue_used = True
            group_delay_applied = False
            digital_filter_correction_status = "not_applicable"
            vendor_key = "Varian/Agilent"
            vendor_format_detected = "Varian/Agilent 1D"
            dataset_folder = varian_dataset.root.name
            raw_dataset_files_found = {
                "fid": varian_dataset.fid_path.is_file(),
                "procpar": varian_dataset.procpar_path.is_file(),
                "log": varian_dataset.log_path is not None,
            }
            pulseprogram_present = False
            pdata_present = False
            if settings.apply_group_delay:
                warnings.append(
                    "Digital-filter/group-delay correction is not applicable to Varian/Agilent beta processing."
                )
        else:
            bruker_dataset = _find_bruker_dataset(root)
            params = _read_bruker_acqus(bruker_dataset.acqus_path)
            read_result = _read_with_nmrglue(bruker_dataset)
            nmrglue_used = False
            if read_result is None:
                fid = _read_minimal_bruker_fid(bruker_dataset, params)
                warnings.append(
                    "nmrglue was not available or could not read this minimal dataset; "
                    "a conservative Bruker fid fallback reader was used."
                )
            else:
                ng_params, data = read_result
                params = {**params, **ng_params}
                if _is_complex_fid(data):
                    fid = data
                    nmrglue_used = True
                else:
                    fid = _read_minimal_bruker_fid(bruker_dataset, params)
                    warnings.append(
                        "nmrglue returned a non-complex Bruker FID; the beta processor used "
                        "the raw interleaved real/imaginary fid reader to preserve "
                        "spectrum orientation."
                    )
            fid = np.array(_flatten_1d_fid(np.asarray(fid)), dtype=np.complex128, copy=True)
            fid, group_delay_applied = _maybe_remove_group_delay(
                fid,
                params,
                dataset_root=bruker_dataset.root,
                settings=settings,
                warnings=warnings,
            )
            fid = np.array(fid, dtype=np.complex128, copy=True)
            digital_filter_correction_status = _digital_filter_correction_status(
                params,
                settings=settings,
                group_delay_applied=group_delay_applied,
                vendor="Bruker",
            )
            vendor_key = "Bruker"
            vendor_format_detected = "Bruker 1D"
            dataset_folder = bruker_dataset.root.name
            raw_dataset_files_found = {
                "fid": bruker_dataset.fid_path.is_file(),
                "acqus": bruker_dataset.acqus_path.is_file(),
                "pulseprogram": bruker_dataset.pulseprogram_path is not None,
                "pdata": bruker_dataset.pdata_path is not None,
            }
            pulseprogram_present = bruker_dataset.pulseprogram_path is not None
            pdata_present = bruker_dataset.pdata_path is not None
            if not pulseprogram_present:
                warnings.append("The Bruker pulseprogram file was not present in the uploaded folder.")
            if pdata_present:
                warnings.append(
                    "Existing pdata was detected but raw fid processing used the uploaded "
                    "fid and acqus files."
                )
        fid_for_qa = np.asarray(fid, dtype=np.complex128)
        nucleus = _resolve_raw_fid_nucleus(params, nucleus)
        settings, raw_fid_advised_processing, raw_fid_advised_notes = (
            _apply_raw_fid_mnova_constraints(settings, nucleus=nucleus)
        )
        warnings.extend(
            note for note in raw_fid_advised_notes if note not in warnings
        )
        # Do not mutate raw vendor files or immutable raw archive.
        # Apodization and all later processing happen on this in-memory working copy.
        fid_points_before_zero_fill = int(fid.size)
        # First-point correction (MestreNova manual p. 136): the discrete FT
        # treats the FID as periodic, so the un-scaled first point produces a
        # constant vertical baseline displacement — a primary cause of peaks
        # that protrude through / sit off the baseline. Multiplying the first
        # point by 0.5 (the manual's stated default) removes that DC offset.
        # Applied to a fresh copy so fid_for_qa and the immutable archive are
        # never mutated. This runs after group-delay removal, so index 0 is
        # the true first acquired point of the FID.
        if fid.size:
            fid = np.array(fid, dtype=np.complex128, copy=True)
            fid[0] = fid[0] * _RAW_FID_MNOVA_FIRST_POINT_SCALE
        fid, apodization_detail = _apply_fid_apodization(
            fid,
            params,
            settings.line_broadening_hz,
            mode=settings.apodization_mode,
        )
        fft_size = _next_power_of_two(fid.size) * settings.zero_fill_factor
        spectrum = np.fft.fftshift(np.fft.fft(fid, n=fft_size))
        effective_phase_mode = normalize_phase_mode(settings.phase_mode)
        if not settings.auto_phase and effective_phase_mode in {"auto", "auto_acme", "auto_peak_minima"}:
            effective_phase_mode = "none"
        spectrum, phase_settings, phase_warnings = _auto_phase_spectrum(
            spectrum,
            mode=effective_phase_mode,
            phase_p0=settings.phase_p0,
            phase_p1=settings.phase_p1,
        )
        phase_settings["phase_warnings"] = phase_warnings
        warnings.extend(note for note in phase_warnings if note not in warnings)
        real_before_baseline = np.real(spectrum)

        axis = _maybe_nmrglue_ppm_axis(params, fid, real_before_baseline.size, vendor=vendor_key)
        fallback_axis, acquisition_parameters = _fallback_ppm_axis(
            params,
            real_before_baseline.size,
            vendor=vendor_key,
        )
        if axis is None:
            axis = fallback_axis
        else:
            acquisition_parameters.update(
                {
                    "ppm_axis_source": "nmrglue",
                    "ppm_axis_orientation": "low_to_high_before_display_reverse",
                }
            )
        acquisition_parameters.update(
            {
                "raw_archive_format": archive_format,
                "phase_angle_degrees": phase_settings["zero_order_degrees"],
                "phase_zero_order_degrees": phase_settings["zero_order_degrees"],
                "phase_first_order_degrees": phase_settings["first_order_degrees"],
                "phase_mode": phase_settings.get("phase_mode"),
                "phase_score": phase_settings.get("phase_score"),
                "phase_pivot_index": phase_settings["pivot_index"],
                "fid_points_after_group_delay": int(fid.size),
                "fft_size": int(fft_size),
                "raw_fid_advised_processing": raw_fid_advised_processing,
            }
        )

        original_spectrum_points = [
            (float(x), float(y))
            for x, y in zip(axis, real_before_baseline, strict=False)
            if math.isfinite(float(x)) and math.isfinite(float(y))
        ]
        original_spectrum_points.sort(key=lambda item: item[0], reverse=True)
        points, baseline_correction_detail, baseline_warnings = _apply_fid_baseline_correction(
            original_spectrum_points,
            settings,
        )
        baseline_correction_detail["warnings"] = baseline_warnings
        warnings.extend(note for note in baseline_warnings if note not in warnings)
        points.sort(key=lambda item: item[0], reverse=True)
        real = np.asarray([y for _, y in points], dtype=float)
        qa_diagnostics = _calculate_fid_qa(
            fid=fid_for_qa,
            spectrum_real=real,
            baseline_reference=real,
        )
        warnings.extend(
            f"FID QA: {warning}"
            for warning in qa_diagnostics.warnings
            if f"FID QA: {warning}" not in warnings
        )
        points, reference_shift_applied, reference_peak_selection = _reference_axis(
            points,
            reference_ppm,
            reference_nmr_text,
        )
        if reference_shift_applied:
            original_spectrum_points = [
                (x + reference_shift_applied, y) for x, y in original_spectrum_points
            ]
        if reference_peak_selection.get("selected_peak_count") == 1:
            warnings.append(
                "FID referencing used one observed peak "
                f"({reference_peak_selection.get('observed_ppm')} ppm) mapped to "
                f"{reference_peak_selection.get('target_ppm')} ppm."
            )

        inference_points = points
        nucleus_label = nucleus.strip() or "1H"
        display_points = points
        display_meta: dict[str, Any] = {
            "baseline_smoothing": {
                "applied": False,
                "method": "disabled_real_spectrum_default",
                "display_points_corrected": False,
            },
            "display_solvent_masked": False,
            "display_baseline": 0.0,
            "evidence_trace_preserved": True,
        }
        if settings.mask_solvent_regions:
            inference_points, mask_notes = _apply_solvent_mask(
                points,
                solvent,
                nucleus=nucleus_label,
            )
            warnings.extend(mask_notes)
        display_points, display_meta, display_notes = _prepare_trace_display_points(
            points,
            solvent=solvent,
            mask_solvent_regions=settings.mask_solvent_regions,
            nucleus=nucleus_label,
            baseline_already_corrected=settings.auto_baseline,
        )
        if settings.auto_baseline:
            display_points, trace_smoothing_meta = _smooth_fid_display_trace(
                display_points,
                nucleus=nucleus_label,
            )
            display_points, solvent_fine_tune_meta = _fine_tune_solvent_display_regions(
                display_points,
                solvent=solvent,
                nucleus=nucleus_label,
                noise_sigma=trace_smoothing_meta.get("noise_sigma"),
            )
            trace_smoothing_meta["solvent_region_fine_tune"] = solvent_fine_tune_meta
        else:
            solvent_fine_tune_meta = {
                "applied": False,
                "display_only": True,
                "evidence_trace_preserved": True,
                "scope": "known_solvent_windows_only",
                "method": "solvent_window_negative_lobe_floor",
                "reason": "auto_baseline_disabled",
            }
            trace_smoothing_meta = {
                "applied": False,
                "display_only": True,
                "evidence_trace_preserved": True,
                "method": "none",
                "reason": "auto_baseline_disabled",
                "solvent_region_fine_tune": solvent_fine_tune_meta,
            }
        display_meta["trace_smoothing"] = trace_smoothing_meta
        display_meta["solvent_region_fine_tune"] = solvent_fine_tune_meta
        if trace_smoothing_meta.get("applied"):
            display_meta["note"] = (
                "Raw FID preview points use display-only baseline centering and "
                "solvent-window negative-lobe limiting after autophasing and baseline "
                "correction. Peak picking and evidence scoring use the corrected "
                "evidence trace."
            )
        warnings.extend(note for note in display_notes if note not in warnings)
        normalized_display_mode = settings.display_mode
        if normalized_display_mode == "magnifier":
            magnifier = weak_peak_magnifier_view(
                points,
                visual_gain=max(settings.vertical_gain, 2.0),
            )
            display_meta["weak_peak_magnifier"] = {
                **magnifier.metadata,
                "points": [
                    point.model_dump(mode="json")
                    for point in _downsample_points(
                        magnifier.points,
                        limit=min(settings.max_preview_points, 700),
                    )
                ],
            }
            warnings.extend(note for note in magnifier.warnings if note not in warnings)
        baseline_flatness_qa = evaluate_baseline_flatness(
            points,
            mode=str(baseline_correction_detail.get("method") or "evidence"),
        ).as_dict()
        baseline_correction_detail["flatness_qa"] = baseline_flatness_qa
        original_spectrum_state = _build_preserved_spectrum_state(
            original_spectrum_points,
            source="raw_fid_frequency_domain_before_baseline_display_correction",
            processing_stage="post_fft_phase_pre_baseline",
            point_limit=settings.max_preview_points,
            normalized_for_preview=False,
        )
        original_spectrum_state["baseline_flatness_qa"] = evaluate_baseline_flatness(
            original_spectrum_points,
            mode="preserve",
        ).as_dict()
        if not settings.debug_preview:
            original_spectrum_state["preview_points"] = []
            original_spectrum_state["preview_points_omitted"] = True
        sensitivity = settings.peak_sensitivity if settings.peak_sensitivity is not None else 0.12
        target_total_h = _select_target_proton_count(
            expected_total_h=expected_total_h,
            expected_non_labile_h=expected_non_labile_h,
            solvent=solvent,
        )
        frequency_mhz = _param_float(params, "SFO1", "BF1", "sfrq", "reffrq")
        estimates = _infer_peak_estimates(
            inference_points,
            sensitivity=sensitivity,
            detection_gain=1.0,
            frequency_mhz=frequency_mhz,
        )
        peaks, peak_meta = _estimates_to_peaks(estimates, target_total_h=target_total_h)
        reference_nmr_text_normalized: str | None = None
        reference_assignments = []
        reference_peaks: list[Peak] = []
        if reference_nmr_text and reference_nmr_text.strip():
            try:
                reference_nmr_text_normalized, reference_assignments = parse_reference_nmr_text(
                    reference_nmr_text
                )
                reference_peaks = _reference_assignments_to_peaks(reference_assignments)
                warnings.append(
                    "Reference 1H NMR text was used to compare raw FID-derived peaks."
                )
            except Exception as exc:
                try:
                    reference_nmr_text_normalized = normalize_nmr_text(reference_nmr_text)
                except Exception:
                    reference_nmr_text_normalized = reference_nmr_text.strip()
                warnings.append(f"Reference 1H NMR text could not be parsed: {exc}")

        comparison = _build_spectrum_comparison(
            reference_assignments=reference_assignments,
            extracted_peaks=peaks,
            structure_visible_h=target_total_h,
        )
        reference_guided_nmr_text: str | None = None
        reference_coverage_count = 0
        if reference_assignments and peaks:
            reference_guided_nmr_text, reference_coverage_count = _build_reference_guided_nmr_text(
                reference_assignments=reference_assignments,
                extracted_peaks=peaks,
            )
            if reference_guided_nmr_text is not None:
                warnings.append(
                    "Reference-assisted matching preserved recognized shift ranges and "
                    "multiplicities for the FID-derived analysis text."
                )
        impurity_candidates = _build_impurity_candidates(
            peaks,
            solvent,
            comparison=comparison,
            target_total_h=target_total_h,
        )
        raw_inferred_nmr_text = _peaks_to_nmr_text(peaks) if peaks else ""
        inferred_nmr_text = reference_guided_nmr_text or raw_inferred_nmr_text

        warnings.append(
            "Raw FID beta processing used automatic 1D Fourier transform, phasing, "
            "baseline, referencing, and peak-picking assumptions."
        )
        warnings.append(
            "Human reviewer signoff is required before using raw FID-derived evidence "
            "in a final report."
        )
        normalized_warning_nucleus = _normalize_nucleus_label(nucleus)
        if normalized_warning_nucleus not in {"1H", "13C"}:
            warnings.append(
                f"Raw FID beta is tuned for {vendor_key} 1D 1H data; "
                "this nucleus should be reviewed carefully."
            )
        if normalized_warning_nucleus == "13C":
            warnings.append(
                "13C FID intensity is not treated as quantitative carbon-count evidence; "
                "review uses peak positions and context instead."
            )
        if impurity_candidates:
            warnings.append(
                f"{len(impurity_candidates)} minor peak(s) were flagged as possible "
                "impurity candidates for manual review."
            )

        baseline_applied = bool(baseline_correction_detail.get("correction_applied"))
        metadata = _metadata_from_preview(
            vendor_format_detected=vendor_format_detected,
            dataset_folder=dataset_folder,
            nucleus=nucleus.strip() or "1H",
            solvent=solvent,
            reference_ppm=reference_ppm,
            reference_shift_applied_ppm=reference_shift_applied,
            reference_peak_selection=reference_peak_selection,
            group_delay_applied=group_delay_applied,
            phase_applied=bool(phase_settings.get("phase_correction_applied")),
            baseline_applied=baseline_applied,
            settings=settings,
            acquisition_parameters=acquisition_parameters,
            fft_size=int(fft_size),
            fid_points_before_zero_fill=fid_points_before_zero_fill,
            apodization_detail=apodization_detail,
            phase_angle_degrees=phase_settings["zero_order_degrees"],
            phase_settings_detail=phase_settings,
            baseline_correction_detail=baseline_correction_detail,
            digital_filter_correction_status=digital_filter_correction_status,
            qa_diagnostics=qa_diagnostics,
            nmrglue_used=nmrglue_used,
            peaks=peaks,
            warnings=warnings,
            raw_dataset_files_found=raw_dataset_files_found,
            raw_upload_provenance=raw_upload_provenance,
            pulseprogram_present=pulseprogram_present,
            pdata_present=pdata_present,
        )

        report = FIDPreviewReport(
            filename=filename,
            format_detected=(
                "varian_agilent_fid_zip"
                if vendor_key == "Varian/Agilent"
                else "bruker_fid_zip"
            ),
            source_mode="trace",
            point_count=len(points),
            preview_points=_downsample_points(display_points, limit=settings.max_preview_points),
            inferred_peaks=peaks,
            inferred_nmr_text=inferred_nmr_text,
            reference_nmr_text_normalized=reference_nmr_text_normalized,
            reference_peaks=reference_peaks,
            comparison=comparison,
            warnings=warnings,
            metadata={
                "vendor_format_detected": metadata.vendor_format_detected,
                "nucleus": metadata.nucleus,
                "solvent": solvent,
                "reference_ppm": reference_ppm,
                "reference_shift_applied_ppm": reference_shift_applied,
                "reference_peak_selection": reference_peak_selection,
                "selected_preset": metadata.selected_preset,
                "zero_filling": metadata.zero_filling,
                "line_broadening": metadata.line_broadening,
                "phase_settings": metadata.phase_settings,
                "baseline_correction": metadata.baseline_correction,
                "plotly_data_preparation": {
                    "applied_before_plotly": True,
                    "source": "raw_fid_time_domain",
                    "sequence": [
                        "digital_filter_or_group_delay",
                        "apodization_window",
                        "zero_fill_fft",
                        "phase_correction",
                        "baseline_flattening",
                        "peak_preserving_downsample",
                    ],
                    "windowing": metadata.line_broadening,
                    "zero_filling": metadata.zero_filling,
                    "baseline": metadata.baseline_correction,
                    "downsampling": {
                        "method": _PREVIEW_DOWNSAMPLING_METHOD,
                        "point_limit": settings.max_preview_points,
                        "source_point_count": len(points),
                    },
                },
                "phase": {
                    "mode": metadata.phase_settings.get("phase_mode"),
                    "p0": metadata.phase_settings.get("phase_p0"),
                    "p1": metadata.phase_settings.get("phase_p1"),
                    "score": metadata.phase_settings.get("phase_score"),
                    "correction_applied": metadata.phase_settings.get("phase_correction_applied"),
                    "warnings": metadata.phase_settings.get("phase_warnings", []),
                },
                "baseline": {
                    "mode": metadata.baseline_correction.get("baseline_correction")
                    or metadata.baseline_correction.get("mode")
                    or metadata.baseline_correction.get("method"),
                    "order": metadata.baseline_correction.get("baseline_order"),
                    "coefficients": metadata.baseline_correction.get("coefficients"),
                    "baseline_points": metadata.baseline_correction.get("baseline_points"),
                    "correction_applied": metadata.baseline_correction.get("correction_applied"),
                    "qa": metadata.baseline_correction.get("flatness_qa") or baseline_flatness_qa,
                    "warnings": metadata.baseline_correction.get("warnings", []),
                },
                "phase_mode": metadata.phase_settings.get("phase_mode"),
                "phase_p0": metadata.phase_settings.get("phase_p0"),
                "phase_p1": metadata.phase_settings.get("phase_p1"),
                "phase_score": metadata.phase_settings.get("phase_score"),
                "phase_correction_applied": metadata.phase_settings.get("phase_correction_applied"),
                "baseline_correction_mode": metadata.baseline_correction.get("mode")
                or metadata.baseline_correction.get("method"),
                "baseline_order": metadata.baseline_correction.get("baseline_order"),
                "baseline_correction_applied": metadata.baseline_correction.get("correction_applied"),
                "digital_filter_correction_status": metadata.digital_filter_correction_status,
                "qa_diagnostics": metadata.qa_diagnostics.model_dump(mode="json"),
                "processing_parameters": metadata.processing_parameters,
                "processing_recipe": metadata.processing_recipe.model_dump(mode="json"),
                "raw_fid_advised_processing": raw_fid_advised_processing,
                "acquisition_parameters": metadata.acquisition_parameters,
                "raw_dataset_files_found": metadata.raw_dataset_files_found,
                "raw_upload_provenance": metadata.raw_upload_provenance,
                "analysis_artifact_policy": metadata.analysis_artifact_policy,
                "group_delay_correction_applied": group_delay_applied,
                "automatic_phase_correction": settings.auto_phase,
                "automatic_baseline_correction": baseline_applied,
                "display_preprocessing": display_meta,
                "evidence_trace_mode": (
                    "raw_fid_fft_real_baseline_corrected"
                    if baseline_applied
                    else "raw_fid_fft_real"
                ),
                "display_mode": normalized_display_mode,
                "display_gain": float(settings.vertical_gain),
                "baseline_lock_visual_only": bool(settings.baseline_lock_visual_only),
                "preview_downsampling": {
                    "method": _PREVIEW_DOWNSAMPLING_METHOD,
                    "point_limit": settings.max_preview_points,
                    "source_point_count": len(points),
                },
                "display": {
                    "mode": normalized_display_mode,
                    "gain": float(settings.vertical_gain),
                    "vertical_gain": float(settings.vertical_gain),
                    "baseline_lock_visual_only": bool(settings.baseline_lock_visual_only),
                    "main_trace": (
                        "display_smoothed_evidence_intensity"
                        if trace_smoothing_meta.get("applied")
                        else "original_evidence_intensity"
                    ),
                    "trace_smoothing": trace_smoothing_meta,
                    "weak_peak_magnifier": normalized_display_mode == "magnifier",
                    "downsampling": {
                        "method": _PREVIEW_DOWNSAMPLING_METHOD,
                        "point_limit": settings.max_preview_points,
                    },
                },
                "fid_processing": {
                    "selected_preset": metadata.selected_preset,
                    "phase_settings": metadata.phase_settings,
                    "baseline_correction": metadata.baseline_correction,
                    "processing_parameters": metadata.processing_parameters,
                },
                "fid_quality": metadata.qa_diagnostics.model_dump(mode="json"),
                "baseline_qa": baseline_flatness_qa,
                "baseline_flatness_qa": baseline_flatness_qa,
                "original_spectrum_state": original_spectrum_state,
                **(
                    {
                        "raw_preview_points": [
                            point.model_dump(mode="json")
                            for point in _downsample_points(
                                points,
                                limit=settings.max_preview_points,
                            )
                        ]
                    }
                    if settings.debug_preview
                    else {}
                ),
                "reviewer_signoff_required": True,
                "human_review_status": metadata.human_review_status,
                "impurity_candidates": impurity_candidates,
                "reference_peak_count": len(reference_peaks),
                "reference_total_h": round(sum(peak.integration_h for peak in reference_peaks), 4)
                if reference_peaks
                else 0.0,
                "reference_coverage_count": reference_coverage_count,
                "reference_guided_text_used": reference_guided_nmr_text is not None,
                "raw_extracted_nmr_text": raw_inferred_nmr_text,
                "target_total_h": expected_total_h,
                "target_non_labile_h": expected_non_labile_h,
                "target_visible_h": target_total_h,
                **peak_meta,
            },
            processing_metadata=metadata,
        )
        return _store_raw_fid_process_cache(cache_key, report)


def process_raw_fid_zip_to_spectrum(
    *,
    filename: str,
    content: bytes,
    solvent: str | None = None,
    nucleus: str = "1H",
    reference_ppm: float | None = None,
    reference_nmr_text: str | None = None,
    settings: FIDProcessingSettings | None = None,
    expected_total_h: int | None = None,
    expected_non_labile_h: int | None = None,
    raw_upload_provenance: dict[str, Any] | None = None,
) -> FIDPreviewReport:
    """Compatibility wrapper for the Bruker/Varian 1D raw-FID processor."""

    return process_bruker_1d_zip(
        filename=filename,
        content=content,
        solvent=solvent,
        nucleus=nucleus,
        reference_ppm=reference_ppm,
        reference_nmr_text=reference_nmr_text,
        settings=settings,
        expected_total_h=expected_total_h,
        expected_non_labile_h=expected_non_labile_h,
        raw_upload_provenance=raw_upload_provenance,
    )
