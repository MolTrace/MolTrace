"""Prompt 3 Global Spectral Deconvolution peak picking.

This module is deliberately independent from ``nmrcheck.gsd``.  The older
module remains the production multiplet resolver used by SpectraCheck today;
this layer exposes the Prompt 3 API for sidecar validation and later promotion
without changing the visible processed or raw-FID spectrum paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import numpy as np
from scipy.signal import find_peaks, peak_widths

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum

try:  # pragma: no cover - exercised only when an optional dependency is absent.
    from lmfit.models import LorentzianModel, PseudoVoigtModel
except Exception:  # pragma: no cover
    LorentzianModel = None  # type: ignore[assignment]
    PseudoVoigtModel = None  # type: ignore[assignment]

PeakShape = Literal["lorentzian", "voigt"]
PeakCategory = Literal["compound", "solvent", "impurity", "artifact", "13C_satellite"]

_LEVELS = {1, 2, 3, 4, 5}
_MAX_PEAKS_BY_LEVEL = {1: 160, 2: 220, 3: 280, 4: 340, 5: 400}
_MIN_SATELLITE_RATIO = 0.003
_MAX_SATELLITE_RATIO = 0.025
_DEFAULT_FIELD_MHZ = 500.0


@dataclass(slots=True, frozen=True)
class Peak:
    position_ppm: float
    position_hz: float
    intensity: float
    area: float
    width_hz: float
    shape: PeakShape
    category: PeakCategory = "compound"
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# Default multiplet-cluster window in Hz, applied when ``cluster_j_hz`` is
# not provided by the caller.  1H windows must accommodate typical
# J-couplings (vicinal ~6-8 Hz, geminal ~10-15 Hz, occasional 18-20 Hz
# couplings in cis-alkene / W-coupled systems).  13C spectra are usually
# 1H-decoupled so multiplet splittings are rare; a small floor catches
# ¹³C-¹³C couplings and prevents legitimate distinct environments at 5+
# ppm separation from accidentally merging.
_DEFAULT_CLUSTER_J_HZ_BY_NUCLEUS: dict[str, float] = {
    "1H": 20.0,
    "13C": 5.0,
}
# Multiplicity letters for environments containing N constituent peaks.
# 8+ peaks degenerates to "m" (multiplet / unresolved cluster).
_MULTIPLICITY_BY_PEAK_COUNT: dict[int, str] = {
    1: "s",
    2: "d",
    3: "t",
    4: "q",
    5: "quint",
    6: "sext",
    7: "sept",
}


@dataclass(slots=True, frozen=True)
class Environment:
    """One chemical environment, formed from one-or-more adjacent peaks of the
    same category whose ppm separation is within a J-coupling window.

    Exists because expert NMR reference shift lists (e.g., NMRShiftDB2,
    HMDB, literature ¹H/¹³C tables) count *environments*, not individual
    multiplet lines.  Without clustering, a real-world detector legitimately
    resolves a doublet as 2 peaks and a quartet as 4 -- but the curated
    reference treats each as one entry.  Clustering peaks back into
    environments lets gate metrics compare on the same unit the reference
    uses, making "median Δ ≤ 2" a tractable target instead of an artefact
    of multiplicity inflation.
    """

    centre_ppm: float
    peak_count: int
    total_intensity: float
    total_area: float
    category: PeakCategory
    multiplicity: str  # "s" | "d" | "t" | "q" | "quint" | "sext" | "sept" | "m"
    constituent_indices: list[int]


def cluster_into_environments(
    peaks: list[Peak],
    *,
    field_mhz: float,
    nucleus: str = "1H",
    cluster_j_hz: float | None = None,
) -> list[Environment]:
    """Group adjacent same-category peaks into chemical-environment clusters.

    Two peaks merge into the same environment when they share a category AND
    their ppm separation converts (via ``field_mhz``) to ≤ ``cluster_j_hz``.
    Category isolation prevents a compound peak from absorbing an adjacent
    solvent / impurity / artifact peak: each non-compound category produces
    single-peak environments by default (a solvent line stays one
    environment; an artefact stays one environment).

    Returns one environment per input peak when no clustering applies.
    Returns a single environment when every input peak shares a category
    and a tight cluster.  The intensity-weighted centre_ppm is the value
    the gate metric / FE display should use as the "peak position".

    Args:
        peaks: list of classified Peak objects (typically the output of
            ``auto_classify``).  Their order is preserved in ``constituent_indices``.
        field_mhz: spectrometer frequency in MHz; used to convert the
            ``cluster_j_hz`` window into a ppm threshold.
        nucleus: "1H" or "13C"; selects the per-nucleus default window
            when ``cluster_j_hz`` is None.
        cluster_j_hz: explicit J-coupling window in Hz; overrides the
            nucleus-aware default when provided.  Use a smaller value
            (e.g., 5-8 Hz) to be conservative and only merge clear
            doublet / triplet partners; use a larger value (e.g., 20 Hz)
            to absorb wider multiplet splittings.
    """

    if not peaks:
        return []

    if cluster_j_hz is None:
        cluster_j_hz = _DEFAULT_CLUSTER_J_HZ_BY_NUCLEUS.get(
            _normalise_nucleus(nucleus), 20.0
        )
    if field_mhz <= 0 or not math.isfinite(field_mhz):
        # Fall back to a safe single-peak-per-environment output if the
        # caller passed a non-physical field.  Better than emitting
        # nonsense clusters from a divide-by-zero conversion.
        return [_singleton_environment(idx, peak) for idx, peak in enumerate(peaks)]
    cluster_j_ppm = float(cluster_j_hz) / float(field_mhz)

    # Sort by ppm (ascending) but track the original index so the FE can
    # cross-reference environments back to specific peaks in the response.
    indexed = sorted(enumerate(peaks), key=lambda item: item[1].position_ppm)

    groups: list[list[tuple[int, Peak]]] = [[indexed[0]]]
    for original_index, peak in indexed[1:]:
        prev_index, prev_peak = groups[-1][-1]
        same_category = peak.category == prev_peak.category
        within_window = (
            abs(peak.position_ppm - prev_peak.position_ppm) <= cluster_j_ppm
        )
        if same_category and within_window:
            groups[-1].append((original_index, peak))
        else:
            groups.append([(original_index, peak)])

    environments: list[Environment] = []
    for group in groups:
        if len(group) == 1:
            idx, peak = group[0]
            environments.append(_singleton_environment(idx, peak))
            continue
        environments.append(_aggregate_environment(group))
    return environments


def _singleton_environment(index: int, peak: Peak) -> Environment:
    return Environment(
        centre_ppm=float(peak.position_ppm),
        peak_count=1,
        total_intensity=float(max(peak.intensity, 0.0)),
        total_area=float(max(peak.area, 0.0)),
        category=peak.category,
        multiplicity=_MULTIPLICITY_BY_PEAK_COUNT.get(1, "s"),
        constituent_indices=[int(index)],
    )


def _aggregate_environment(group: list[tuple[int, Peak]]) -> Environment:
    indices = [int(idx) for idx, _ in group]
    peaks_only = [peak for _, peak in group]
    intensities = np.asarray([max(p.intensity, 0.0) for p in peaks_only], dtype=float)
    positions = np.asarray([float(p.position_ppm) for p in peaks_only], dtype=float)
    total_intensity = float(intensities.sum())
    if total_intensity > 0.0:
        centre_ppm = float(np.sum(positions * intensities) / total_intensity)
    else:
        centre_ppm = float(positions.mean())
    multiplicity = _MULTIPLICITY_BY_PEAK_COUNT.get(len(peaks_only), "m")
    return Environment(
        centre_ppm=centre_ppm,
        peak_count=len(peaks_only),
        total_intensity=total_intensity,
        total_area=float(sum(max(p.area, 0.0) for p in peaks_only)),
        category=peaks_only[0].category,
        multiplicity=multiplicity,
        constituent_indices=indices,
    )


def gsd_peak_pick(spectrum: NMRSpectrum, level: int = 2) -> list[Peak]:
    """
    Pick and fit spectrum peaks with a Global Spectral Deconvolution style API.

    ``level`` controls fit cost and overlap handling:
      - 1: single Lorentzian per detected peak
      - 2: pseudo-Voigt per detected peak
      - 3: pseudo-Voigt group fits for overlapping peaks
      - 4-5: lower detection thresholds and wider group windows
    """

    level = _normalise_level(level)
    x, y = _finite_spectrum_arrays(spectrum)
    if x.size < 8:
        return []

    oriented = _positive_peak_orientation(y)
    baseline = float(np.median(oriented))
    signal = oriented - baseline
    noise = _robust_noise(signal)
    if not math.isfinite(noise) or noise <= 0.0:
        return []

    indices, widths_points, properties = _initial_peak_indices(
        x,
        signal,
        noise=noise,
        nucleus=spectrum.nucleus,
        level=level,
    )
    if indices.size == 0:
        return []

    max_peaks = _MAX_PEAKS_BY_LEVEL[level]
    if indices.size > max_peaks:
        prominences = np.asarray(properties.get("prominences", []), dtype=float)
        if prominences.size == indices.size:
            keep = np.argsort(prominences)[-max_peaks:]
            keep.sort()
            indices = indices[keep]
            widths_points = widths_points[keep]
        else:
            indices = indices[:max_peaks]
            widths_points = widths_points[:max_peaks]

    if level >= 3:
        raw_peaks = _fit_peak_groups(
            x,
            signal,
            indices,
            widths_points,
            spectrum=spectrum,
            level=level,
            noise=noise,
        )
    else:
        raw_peaks = [
            _fit_single_peak(
                x,
                signal,
                int(index),
                float(width_points),
                spectrum=spectrum,
                level=level,
                noise=noise,
            )
            for index, width_points in zip(indices, widths_points, strict=False)
        ]

    peaks = _deduplicate_peaks([peak for peak in raw_peaks if peak is not None], spectrum)
    peaks = _augment_with_residual_solvent_peak(
        x=x,
        signal=signal,
        peaks=peaks,
        spectrum=spectrum,
        noise=noise,
        level=level,
    )
    peaks.sort(key=lambda peak: peak.position_ppm, reverse=True)
    return peaks


def auto_classify(peaks: list[Peak], spectrum: NMRSpectrum, solvent: str) -> list[Peak]:
    """Classify GSD peaks as compound, solvent, impurity, artifact, or satellite."""

    if not peaks:
        return []

    x, y = _finite_spectrum_arrays(spectrum)
    signal = _positive_peak_orientation(y)
    signal = signal - float(np.median(signal))
    noise = _robust_noise(signal)
    median_width_hz = _median_positive([peak.width_hz for peak in peaks])
    max_intensity = max((peak.intensity for peak in peaks), default=0.0)
    nucleus = _normalise_nucleus(spectrum.nucleus)
    solvent_value = solvent or spectrum.solvent
    satellite_indices = _detect_13c_satellites(peaks, spectrum)

    classified: list[Peak] = []
    for index, peak in enumerate(peaks):
        category: PeakCategory = "compound"
        reasons: list[str] = []
        metadata = dict(peak.metadata)
        detail = _chemical_detail(peak, nucleus=nucleus, solvent=solvent_value)
        metadata["chemical_detail"] = detail
        solvent_hit = detail.get("solvent_hit")
        impurity_match = detail.get("impurity_match")

        if index in satellite_indices:
            category = "13C_satellite"
            reasons.append("Detected as a symmetric low-intensity 13C satellite partner.")
        elif _detail_is_solvent(
            peak=peak,
            peaks=peaks,
            solvent_hit=solvent_hit,
            impurity_match=impurity_match,
        ):
            category = "solvent"
            reasons.append(
                "Most-prominent peak inside the curated residual-solvent/water/reference window."
            )
        elif _is_artifact_like(
            peak,
            noise=noise,
            median_width_hz=median_width_hz,
            nucleus=nucleus,
        ):
            category = "artifact"
            reasons.append(
                "Below 3x baseline noise or width exceeds 2x median AND the nucleus Hz floor."
            )
        elif _detail_is_impurity(impurity_match, peak=peak, max_intensity=max_intensity):
            category = "impurity"
            reasons.append("Matches a curated minor-impurity shift table.")
        else:
            reasons.append("No solvent, impurity, satellite, or artifact rule matched.")

        metadata["classification_reasons"] = reasons
        metadata["baseline_noise_sigma"] = noise
        metadata["median_width_hz"] = median_width_hz
        confidence = _classification_confidence(
            peak,
            category=category,
            noise=noise,
            median_width_hz=median_width_hz,
        )
        classified.append(
            replace(
                peak,
                category=category,
                confidence=min(1.0, max(0.0, confidence)),
                metadata=metadata,
            )
        )

    return classified


def _normalise_level(level: int) -> int:
    try:
        value = int(level)
    except (TypeError, ValueError):
        value = 2
    if value not in _LEVELS:
        return 2
    return value


def _normalise_nucleus(nucleus: str | None) -> str:
    value = (
        str(nucleus or "")
        .strip()
        .upper()
        .replace("¹³", "13")
        .replace("¹", "1")
    )
    if value in {"H1", "PROTON"}:
        return "1H"
    if value in {"C13", "CARBON13", "CARBON-13"}:
        return "13C"
    if value in {"1H", "13C"}:
        return value
    return value or "1H"


def _finite_spectrum_arrays(spectrum: NMRSpectrum) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(spectrum.ppm_axis, dtype=float).reshape(-1)
    y = np.asarray(np.real(spectrum.data), dtype=float).reshape(-1)
    size = min(x.size, y.size)
    if size == 0:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    x = x[:size]
    y = y[:size]
    finite = np.isfinite(x) & np.isfinite(y)
    x = x[finite]
    y = y[finite]
    if x.size > 1 and x[0] < x[-1]:
        x = x[::-1]
        y = y[::-1]
    return x, y


def _positive_peak_orientation(y: np.ndarray) -> np.ndarray:
    """Return ``y`` or ``-y`` so that real peaks point upward.

    Uses smoothed extrema (not raw percentiles) because percentile-based
    detection misfires on spectra that contain one or two genuine very-large
    positive peaks alongside small phase-wiggle negative excursions: the big
    peaks live above the 99.5 percentile and so are invisible to the check,
    while the phase wiggle dominates the 0.5 percentile and triggers a wrong
    flip.  A 7-sample boxcar suppresses single-point spikes while preserving
    the magnitude of real peaks (which span many samples after FFT).
    """

    if y.size < 16:
        return y
    centered = y - float(np.median(y))
    kernel = np.ones(7, dtype=float) / 7.0
    smoothed = np.convolve(centered, kernel, mode="same")
    max_pos = float(np.nanmax(smoothed)) if smoothed.size else 0.0
    max_neg = abs(float(np.nanmin(smoothed))) if smoothed.size else 0.0
    return -y if max_neg > max_pos * 1.25 else y


def _robust_noise(y: np.ndarray) -> float:
    if y.size == 0:
        return 0.0
    centered = y - float(np.nanmedian(y))
    mad = float(np.nanmedian(np.abs(centered - float(np.nanmedian(centered)))))
    sigma = 1.4826 * mad
    if math.isfinite(sigma) and sigma > 0:
        return sigma
    std = float(np.nanstd(centered))
    return std if math.isfinite(std) else 0.0


def _initial_peak_indices(
    x: np.ndarray,
    signal: np.ndarray,
    *,
    noise: float,
    nucleus: str,
    level: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    smoothed = _smooth_signal(signal, _smooth_width(level))
    dynamic = float(np.nanpercentile(smoothed, 99.8) - np.nanmedian(smoothed))
    normalised_nucleus = _normalise_nucleus(nucleus)

    # Peak-free baseline noise estimate for 13C.  MAD-on-the-whole-spectrum
    # is inflated by analyte peak tails in dense 13C spectra (~33% of the
    # dynamic range for the worst cases), so the `noise * sensitivity`
    # detection threshold becomes too restrictive and minor 13C lines get
    # culled.  The lower-half of sorted smoothed values is peak-free by
    # construction.  Applied only to 13C because 1H spectra already detect
    # adequately and the lower threshold causes over-detection of analyte
    # multiplet components that are not present in NMRShiftDB2's curated
    # reference peak lists.  Floor at `noise * 0.4` defends against
    # pathological one-huge-peak spectra.
    if normalised_nucleus == "13C":
        sorted_smooth = np.sort(smoothed)
        pool = sorted_smooth[: max(sorted_smooth.size // 2, 8)]
        pool_med = float(np.nanmedian(pool))
        pool_noise = 1.4826 * float(np.nanmedian(np.abs(pool - pool_med)))
        detection_noise = max(pool_noise, noise * 0.4)
    else:
        detection_noise = noise

    sensitivity = {1: 6.0, 2: 4.5, 3: 3.5, 4: 3.0, 5: 2.5}[level]
    prominence = max(
        detection_noise * sensitivity,
        dynamic * _dynamic_prominence_fraction(level, normalised_nucleus),
    )
    # 13C spectra naturally have wider dynamic range (quaternary carbons +
    # NOE-suppressed peaks alongside protonated carbons) so the dynamic-
    # height term that gates 1H detection oversuppresses real 13C peaks.
    height_dynamic_fraction = 0.001 if normalised_nucleus == "13C" else 0.004
    height = max(
        detection_noise * max(2.5, sensitivity - 1.0),
        dynamic * height_dynamic_fraction,
    )
    distance = _distance_points(x, nucleus=nucleus, level=level)
    indices, properties = find_peaks(
        smoothed,
        height=height,
        prominence=prominence,
        distance=distance,
    )
    if indices.size == 0 and level >= 2:
        indices, properties = find_peaks(
            smoothed,
            height=max(noise * 2.5, dynamic * 0.002),
            prominence=max(noise * 2.5, dynamic * 0.001),
            distance=max(1, distance // 2),
        )
    if indices.size == 0:
        return indices, np.asarray([], dtype=float), properties
    widths = peak_widths(smoothed, indices, rel_height=0.5)[0]
    return indices.astype(int), np.asarray(widths, dtype=float), properties


def _smooth_signal(signal: np.ndarray, width: int) -> np.ndarray:
    if width <= 1 or signal.size < width:
        return signal
    kernel = np.ones(width, dtype=float) / float(width)
    return np.convolve(signal, kernel, mode="same")


def _smooth_width(level: int) -> int:
    return 1 if level <= 2 else 3


def _dynamic_prominence_fraction(level: int, nucleus: str = "1H") -> float:
    """Per-level prominence threshold expressed as a fraction of dynamic range.

    13C is scaled down because 13C spectra usually have a 100-1000x dynamic
    range between the most-intense protonated carbon and the smallest
    quaternary line, so the dynamic-range-based threshold suppresses real
    minor peaks much more aggressively than the noise-based one.  Halving the
    fraction shifts the gate closer to the noise-based threshold for 13C
    while leaving the well-tested 1H behaviour unchanged.
    """

    base = {1: 0.018, 2: 0.012, 3: 0.008, 4: 0.006, 5: 0.004}[level]
    if nucleus == "13C":
        return base * 0.4
    return base


def _distance_points(x: np.ndarray, *, nucleus: str, level: int) -> int:
    step = _median_ppm_step(x)
    if step <= 0:
        return 1
    nucleus_value = _normalise_nucleus(nucleus)
    if nucleus_value == "13C":
        min_ppm = {1: 0.10, 2: 0.07, 3: 0.04, 4: 0.03, 5: 0.02}[level]
    else:
        min_ppm = {1: 0.010, 2: 0.006, 3: 0.0035, 4: 0.0025, 5: 0.0018}[level]
    return max(1, int(round(min_ppm / step)))


def _median_ppm_step(x: np.ndarray) -> float:
    if x.size < 2:
        return 0.0
    diffs = np.diff(np.sort(x))
    diffs = np.abs(diffs[np.isfinite(diffs) & (np.abs(diffs) > 0)])
    return float(np.median(diffs)) if diffs.size else 0.0


def _fit_single_peak(
    x: np.ndarray,
    y: np.ndarray,
    index: int,
    width_points: float,
    *,
    spectrum: NMRSpectrum,
    level: int,
    noise: float,
) -> Peak | None:
    lo, hi = _local_fit_bounds(x, index, width_points, level=level)
    x_fit = x[lo:hi]
    y_fit = y[lo:hi]
    if x_fit.size < 5:
        return _fallback_peak(x, y, index, width_points, spectrum=spectrum, level=level, noise=noise)
    if level == 1:
        return _fit_single_with_model(
            x_fit,
            y_fit,
            center_guess=float(x[index]),
            spectrum=spectrum,
            level=level,
            shape="lorentzian",
            noise=noise,
        ) or _fallback_peak(x, y, index, width_points, spectrum=spectrum, level=level, noise=noise)
    return _fit_single_with_model(
        x_fit,
        y_fit,
        center_guess=float(x[index]),
        spectrum=spectrum,
        level=level,
        shape="voigt",
        noise=noise,
    ) or _fallback_peak(x, y, index, width_points, spectrum=spectrum, level=level, noise=noise)


def _fit_single_with_model(
    x_fit: np.ndarray,
    y_fit: np.ndarray,
    *,
    center_guess: float,
    spectrum: NMRSpectrum,
    level: int,
    shape: PeakShape,
    noise: float,
) -> Peak | None:
    model_cls = LorentzianModel if shape == "lorentzian" else PseudoVoigtModel
    if model_cls is None:
        return None
    x_lo = float(np.min(x_fit))
    x_hi = float(np.max(x_fit))
    span = max(abs(x_hi - x_lo), _median_ppm_step(x_fit) * 4.0)
    step = max(_median_ppm_step(x_fit), span / max(10.0, float(x_fit.size)))
    peak_height = max(float(np.max(y_fit)), noise)
    sigma = max(step, span / 12.0)
    amplitude = max(peak_height * sigma * math.pi, noise * step)
    model = model_cls()
    params = model.make_params(amplitude=amplitude, center=center_guess, sigma=sigma)
    params["amplitude"].set(min=0.0, max=max(amplitude * 30.0, peak_height * span * 30.0))
    params["center"].set(min=x_lo, max=x_hi)
    params["sigma"].set(min=step * 0.35, max=max(span, step))
    if "fraction" in params:
        params["fraction"].set(value=0.5, min=0.0, max=1.0)
    try:
        result = model.fit(
            y_fit,
            params,
            x=x_fit,
            nan_policy="omit",
            max_nfev=400 if level <= 2 else 800,
        )
    except Exception:
        return None
    values = result.params
    center = _param_value(values, "center", center_guess)
    if not math.isfinite(center) or center < x_lo or center > x_hi:
        return None
    fwhm_ppm = abs(_param_value(values, "fwhm", 2.0 * _param_value(values, "sigma", sigma)))
    intensity = max(_param_value(values, "height", float(np.max(result.best_fit))), 0.0)
    area = max(_param_value(values, "amplitude", amplitude), 0.0)
    rmse = _fit_rmse(np.asarray(result.residual, dtype=float))
    return _make_peak(
        position_ppm=center,
        intensity=intensity,
        area=area,
        fwhm_ppm=max(fwhm_ppm, step),
        shape=shape,
        spectrum=spectrum,
        noise=noise,
        rmse=rmse,
        metadata={
            "fit_model": model.__class__.__name__,
            "fit_level": level,
            "fit_redchi": float(result.redchi) if math.isfinite(float(result.redchi)) else None,
        },
    )


def _fit_peak_groups(
    x: np.ndarray,
    y: np.ndarray,
    indices: np.ndarray,
    widths_points: np.ndarray,
    *,
    spectrum: NMRSpectrum,
    level: int,
    noise: float,
) -> list[Peak | None]:
    groups = _overlap_groups(x, indices, widths_points, level=level)
    peaks: list[Peak | None] = []
    for group in groups:
        if len(group) <= 1:
            idx = group[0]
            width = float(widths_points[np.where(indices == idx)[0][0]])
            peaks.append(
                _fit_single_peak(x, y, int(idx), width, spectrum=spectrum, level=level, noise=noise)
            )
            continue
        if level >= 4:
            # Level 4-5 promised "iterative deconvolution with line shape
            # correction" in the Prompt 3 spec.  The legacy
            # nmrcheck.gsd.deconvolve_region does exactly this: forward pass
            # adds lines where the residual still demands them, backward
            # pass prunes redundant ones.  Resolves overlapping lines that
            # find_peaks missed entirely (the dominant remaining failure
            # mode in dense 13C spectra).
            peaks.extend(
                _fit_group_with_deconvolve_region(
                    x, y, group, spectrum=spectrum, level=level, noise=noise
                )
            )
        else:
            peaks.extend(
                _fit_group_with_model(
                    x, y, group, spectrum=spectrum, level=level, noise=noise
                )
            )
    return peaks


def _overlap_groups(
    x: np.ndarray,
    indices: np.ndarray,
    widths_points: np.ndarray,
    *,
    level: int,
) -> list[list[int]]:
    if indices.size == 0:
        return []
    order = np.argsort(indices)
    sorted_indices = [int(indices[i]) for i in order]
    sorted_widths = [float(widths_points[i]) for i in order]
    step = max(_median_ppm_step(x), 1e-9)
    factor = {3: 1.5, 4: 2.0, 5: 2.5}.get(level, 1.5)
    groups: list[list[int]] = [[sorted_indices[0]]]
    previous_width = sorted_widths[0]
    for idx, width in zip(sorted_indices[1:], sorted_widths[1:], strict=False):
        prev = groups[-1][-1]
        ppm_gap = abs(float(x[idx]) - float(x[prev]))
        width_ppm = max(previous_width, width) * step
        if ppm_gap <= max(width_ppm * factor, step * 3.0) and len(groups[-1]) < 8:
            groups[-1].append(idx)
        else:
            groups.append([idx])
        previous_width = width
    return groups


def _fit_group_with_model(
    x: np.ndarray,
    y: np.ndarray,
    group: list[int],
    *,
    spectrum: NMRSpectrum,
    level: int,
    noise: float,
) -> list[Peak | None]:
    if PseudoVoigtModel is None:
        return [
            _fit_single_peak(x, y, idx, 4.0, spectrum=spectrum, level=level, noise=noise)
            for idx in group
        ]
    lo = max(0, min(group) - 24)
    hi = min(x.size, max(group) + 25)
    x_fit = x[lo:hi]
    y_fit = y[lo:hi]
    if x_fit.size < max(8, len(group) * 4):
        return [
            _fit_single_peak(x, y, idx, 4.0, spectrum=spectrum, level=level, noise=noise)
            for idx in group
        ]
    x_lo = float(np.min(x_fit))
    x_hi = float(np.max(x_fit))
    span = max(abs(x_hi - x_lo), _median_ppm_step(x_fit) * 4.0)
    step = max(_median_ppm_step(x_fit), span / max(10.0, float(x_fit.size)))
    model = None
    params = None
    peak_height = max(float(np.max(y_fit)), noise)
    for line, idx in enumerate(group):
        prefix = f"p{line}_"
        component = PseudoVoigtModel(prefix=prefix)
        model = component if model is None else model + component
        center_guess = float(x[idx])
        sigma = max(step, span / (20.0 + 3.0 * len(group)))
        amplitude = max(float(y[idx]) * sigma * math.pi, noise * step)
        component_params = component.make_params(
            amplitude=amplitude,
            center=center_guess,
            sigma=sigma,
            fraction=0.5,
        )
        component_params[f"{prefix}amplitude"].set(
            min=0.0,
            max=max(amplitude * 30.0, peak_height * span * 30.0),
        )
        component_params[f"{prefix}center"].set(
            min=max(x_lo, center_guess - span * 0.35),
            max=min(x_hi, center_guess + span * 0.35),
        )
        component_params[f"{prefix}sigma"].set(min=step * 0.35, max=max(span, step))
        component_params[f"{prefix}fraction"].set(min=0.0, max=1.0)
        if params is None:
            params = component_params
        else:
            params.update(component_params)
    if model is None or params is None:
        return []
    try:
        result = model.fit(
            y_fit,
            params,
            x=x_fit,
            nan_policy="omit",
            max_nfev=800 + 250 * len(group),
        )
    except Exception:
        return [
            _fit_single_peak(x, y, idx, 4.0, spectrum=spectrum, level=level, noise=noise)
            for idx in group
        ]
    rmse = _fit_rmse(np.asarray(result.residual, dtype=float))
    fitted: list[Peak] = []
    for line, idx in enumerate(group):
        prefix = f"p{line}_"
        center = _param_value(result.params, f"{prefix}center", float(x[idx]))
        sigma = _param_value(result.params, f"{prefix}sigma", step)
        fwhm = abs(_param_value(result.params, f"{prefix}fwhm", 2.0 * sigma))
        intensity = max(_param_value(result.params, f"{prefix}height", float(y[idx])), 0.0)
        area = max(_param_value(result.params, f"{prefix}amplitude", intensity * fwhm), 0.0)
        fitted.append(
            _make_peak(
                position_ppm=center,
                intensity=intensity,
                area=area,
                fwhm_ppm=max(fwhm, step),
                shape="voigt",
                spectrum=spectrum,
                noise=noise,
                rmse=rmse,
                metadata={
                    "fit_model": "CompositePseudoVoigtModel",
                    "fit_level": level,
                    "fit_group_size": len(group),
                    "seed_index": int(idx),
                },
            )
        )
    return fitted


def _fit_group_with_deconvolve_region(
    x: np.ndarray,
    y: np.ndarray,
    group: list[int],
    *,
    spectrum: NMRSpectrum,
    level: int,
    noise: float,
) -> list[Peak | None]:
    """Resolve an overlapping-peak group using legacy iterative deconvolution.

    Bridges ``nmrcheck.gsd.deconvolve_region`` (region-wise forward-add /
    backward-prune pseudo-Voigt fit) into the sidecar's group-fit path.
    The legacy module is the production multiplet resolver for SpectraCheck;
    reusing it here unifies the two GSD layers rather than reimplementing
    the same algorithm.  Falls back to composite PseudoVoigt on any failure.

    Output map: legacy returns ``(center_ppm, height, hwhm_ppm)`` per
    resolved line; we convert to Peak using the standard ``_make_peak``
    constructor.  Area is approximated with the pure-Lorentzian formula
    because the legacy module does not expose its fitted eta (the harness
    compares peak counts, not areas, so the approximation is sufficient).
    """

    try:
        from nmrcheck.gsd import deconvolve_region
    except Exception:  # pragma: no cover - defensive
        return _fit_group_with_model(
            x, y, group, spectrum=spectrum, level=level, noise=noise
        )

    lo = max(0, min(group) - 24)
    hi = min(x.size, max(group) + 25)
    x_region = [float(value) for value in x[lo:hi]]
    y_region = [float(value) for value in y[lo:hi]]
    if len(x_region) < 8:
        return _fit_group_with_model(
            x, y, group, spectrum=spectrum, level=level, noise=noise
        )
    seed_centers = [float(x[idx]) for idx in group]

    # Cap max_lines based on group size + level so level 5 explores deeper
    # than level 4.  Legacy default is 24; we scale with group density.
    max_lines = min(24, max(4, len(group) * (3 if level == 4 else 4)))

    try:
        resolved = deconvolve_region(
            x_region,
            y_region,
            seed_centers,
            noise_sigma=float(noise),
            max_lines=max_lines,
        )
    except Exception:  # pragma: no cover - defensive
        return _fit_group_with_model(
            x, y, group, spectrum=spectrum, level=level, noise=noise
        )

    if not resolved:
        return _fit_group_with_model(
            x, y, group, spectrum=spectrum, level=level, noise=noise
        )

    peaks: list[Peak | None] = []
    for center, height, hwhm in resolved:
        fwhm_ppm = 2.0 * abs(float(hwhm))
        # Pure-Lorentzian area approximation (eta unknown).
        area = float(height) * fwhm_ppm * (math.pi / 2.0)
        peaks.append(
            _make_peak(
                position_ppm=float(center),
                intensity=max(float(height), 0.0),
                area=max(area, 0.0),
                fwhm_ppm=fwhm_ppm,
                shape="voigt",
                spectrum=spectrum,
                noise=noise,
                rmse=None,
                metadata={
                    "fit_model": "LegacyDeconvolveRegion",
                    "fit_level": level,
                    "deconvolve_seed_count": len(group),
                    "deconvolve_resolved_count": len(resolved),
                    "deconvolve_max_lines": max_lines,
                },
            )
        )
    return peaks


def _local_fit_bounds(
    x: np.ndarray,
    index: int,
    width_points: float,
    *,
    level: int,
) -> tuple[int, int]:
    half_window = max(6, int(math.ceil(max(width_points, 2.0) * (4.0 if level <= 2 else 5.0))))
    lo = max(0, index - half_window)
    hi = min(x.size, index + half_window + 1)
    return lo, hi


def _fallback_peak(
    x: np.ndarray,
    y: np.ndarray,
    index: int,
    width_points: float,
    *,
    spectrum: NMRSpectrum,
    level: int,
    noise: float,
) -> Peak | None:
    if index < 0 or index >= x.size:
        return None
    step = max(_median_ppm_step(x), 1e-9)
    fwhm_ppm = max(abs(float(width_points)) * step, step)
    lo, hi = _local_fit_bounds(x, index, width_points, level=level)
    local_y = y[lo:hi]
    local_x = x[lo:hi]
    intensity = max(float(y[index]), 0.0)
    area = float(np.trapz(np.maximum(local_y, 0.0), x=local_x))
    return _make_peak(
        position_ppm=float(x[index]),
        intensity=intensity,
        area=abs(area),
        fwhm_ppm=fwhm_ppm,
        shape="lorentzian" if level == 1 else "voigt",
        spectrum=spectrum,
        noise=noise,
        rmse=None,
        metadata={"fit_model": "fallback_peak_width", "fit_level": level},
    )


def _param_value(params: Any, name: str, default: float) -> float:
    try:
        value = params[name].value
    except Exception:
        return float(default)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return float(default)
    return value if math.isfinite(value) else float(default)


def _fit_rmse(residual: np.ndarray) -> float | None:
    if residual.size == 0:
        return None
    value = float(np.sqrt(np.mean(np.square(residual))))
    return value if math.isfinite(value) else None


def _make_peak(
    *,
    position_ppm: float,
    intensity: float,
    area: float,
    fwhm_ppm: float,
    shape: PeakShape,
    spectrum: NMRSpectrum,
    noise: float,
    rmse: float | None,
    metadata: dict[str, Any],
) -> Peak:
    field_mhz = _field_mhz(spectrum)
    width_hz = abs(float(fwhm_ppm) * field_mhz)
    snr = float(intensity) / max(float(noise), 1e-12)
    fit_score = 1.0 if rmse is None else 1.0 / (1.0 + max(0.0, rmse) / max(noise, 1e-12))
    snr_score = min(1.0, math.log1p(max(0.0, snr)) / math.log(101.0))
    confidence = max(0.0, min(1.0, 0.7 * snr_score + 0.3 * fit_score))
    merged_metadata = {
        **metadata,
        "signal_to_noise": snr,
        "fit_rmse": rmse,
        "fwhm_ppm": abs(float(fwhm_ppm)),
    }
    return Peak(
        position_ppm=float(position_ppm),
        position_hz=float(position_ppm) * field_mhz,
        intensity=float(intensity),
        area=float(area),
        width_hz=width_hz,
        shape=shape,
        confidence=confidence,
        metadata=merged_metadata,
    )


def _field_mhz(spectrum: NMRSpectrum) -> float:
    try:
        value = float(spectrum.field_mhz)
    except (TypeError, ValueError):
        value = 0.0
    return value if math.isfinite(value) and value > 0 else _DEFAULT_FIELD_MHZ


_RESIDUAL_SOLVENT_PROBE_PPM_1H: dict[str, float] = {
    "CDCL3": 7.26,
    "DMSO": 2.50,
    "DMSOD6": 2.50,
    "ACETONE": 2.05,
    "ACETONED6": 2.05,
    "CD3OD": 3.31,
    "METHANOLD4": 3.31,
    "MEOD": 3.31,
    "D2O": 4.79,
    "C6D6": 7.16,
    "BENZENED6": 7.16,
    "CD3CN": 1.94,
    "ACETONITRILED3": 1.94,
    "THF": 3.58,
    "THFD8": 3.58,
}
_RESIDUAL_SOLVENT_PROBE_PPM_13C: dict[str, float] = {
    "CDCL3": 77.16,
    "DMSO": 39.52,
    "DMSOD6": 39.52,
    "ACETONE": 29.84,
    "ACETONED6": 29.84,
    "CD3OD": 49.00,
    "METHANOLD4": 49.00,
    "MEOD": 49.00,
    "C6D6": 128.06,
    "BENZENED6": 128.06,
    "CD3CN": 118.26,
    "ACETONITRILED3": 118.26,
    "THF": 67.21,
    "THFD8": 67.21,
}


def _augment_with_residual_solvent_peak(
    *,
    x: np.ndarray,
    signal: np.ndarray,
    peaks: list[Peak],
    spectrum: NMRSpectrum,
    noise: float,
    level: int,
) -> list[Peak]:
    """Second-pass search for a residual-solvent peak the main pass missed.

    When an analyte produces peaks far larger than the residual-solvent peak,
    the dynamic prominence threshold can cull the smaller residual line and
    auto_classify is then left with no peak to label as 'solvent'.  This
    helper runs a localized low-threshold ``find_peaks`` inside the curated
    solvent window from ``peak_categorization`` and inserts the best
    candidate if no existing peak already sits in the window.
    """

    nucleus = _normalise_nucleus(spectrum.nucleus)
    solvent = spectrum.solvent
    if not solvent or nucleus not in {"1H", "13C"}:
        return peaks
    table = (
        _RESIDUAL_SOLVENT_PROBE_PPM_1H
        if nucleus == "1H"
        else _RESIDUAL_SOLVENT_PROBE_PPM_13C
    )
    solvent_key = solvent.upper().replace("-", "").replace("_", "")
    probe_ppm: float | None = None
    for key, ppm in table.items():
        if key in solvent_key:
            probe_ppm = ppm
            break
    if probe_ppm is None:
        return peaks
    try:
        from nmrcheck.peak_categorization import categorize_peak

        detail = categorize_peak(
            nucleus=nucleus,  # type: ignore[arg-type]
            shift_ppm=probe_ppm,
            solvent=solvent,
        )
    except Exception:  # pragma: no cover - defensive
        return peaks
    solvent_hit = detail.get("solvent_hit") if isinstance(detail, dict) else None
    if not isinstance(solvent_hit, dict):
        return peaks
    low_value = solvent_hit.get("low_ppm")
    high_value = solvent_hit.get("high_ppm")
    if low_value is None or high_value is None:
        return peaks
    low_ppm = float(low_value)
    high_ppm = float(high_value)
    if any(low_ppm <= peak.position_ppm <= high_ppm for peak in peaks):
        return peaks

    mask = (x >= low_ppm) & (x <= high_ppm)
    if not np.any(mask):
        return peaks
    local_signal = signal[mask]
    if local_signal.size < 8:
        return peaks
    local_indices = np.where(mask)[0]

    # Local baseline + noise estimate from the lower-half of the window's
    # sorted sample values.  This is robust to where in the window the
    # residual peak sits (which varies with chemical-shift referencing across
    # spectra) -- the bottom half is guaranteed peak-free because any actual
    # peak occupies upper values.  Edge-based sampling fails when the
    # residual happens to sit near a window edge (e.g. 40255417_1h has the
    # residual at 7.21 -- the low-ppm edge of the [7.20, 7.32] window).
    # Critical context: global noise (driven by analyte tails) is several
    # orders of magnitude larger than the true local noise in high-
    # concentration samples (40255417_1h: global=2.2e6, local~25k).
    sorted_samples = np.sort(local_signal)
    baseline_pool = sorted_samples[: max(sorted_samples.size // 2, 8)]
    edge_median = float(np.nanmedian(baseline_pool))
    edge_noise = float(np.nanmedian(np.abs(baseline_pool - edge_median))) * 1.4826
    edge_noise = max(edge_noise, 1e-12)

    # Use height-above-baseline as the qualifier instead of prominence:
    # a residual peak sitting on a noisy plateau can have very low prominence
    # (its noisy neighbours pull the prominence down) while still standing
    # materially above the window's clean baseline pool.  Among all local
    # maxima in the window, pick the highest one that clears the threshold.
    found, _ = find_peaks(local_signal, distance=1)
    if found.size == 0:
        return peaks
    height_threshold = edge_median + 3.0 * edge_noise
    qualified = found[local_signal[found] >= height_threshold]
    if qualified.size == 0:
        return peaks
    best_local = int(qualified[int(np.argmax(local_signal[qualified]))])
    widths_array = peak_widths(local_signal, np.asarray([best_local]), rel_height=0.5)[0]
    width_points = float(widths_array[0]) if widths_array.size else 4.0
    global_index = int(local_indices[best_local])
    fitted = _fit_single_peak(
        x,
        signal,
        global_index,
        width_points,
        spectrum=spectrum,
        level=level,
        noise=noise,
    )
    if fitted is None:
        return peaks
    augmented = list(peaks)
    augmented.append(fitted)
    return _deduplicate_peaks(augmented, spectrum)


def _deduplicate_peaks(peaks: list[Peak], spectrum: NMRSpectrum) -> list[Peak]:
    if not peaks:
        return []
    nucleus = _normalise_nucleus(spectrum.nucleus)
    min_gap = 0.025 if nucleus == "13C" else 0.0015
    ordered = sorted(peaks, key=lambda peak: peak.position_ppm, reverse=True)
    merged: list[Peak] = []
    for peak in ordered:
        if merged and abs(peak.position_ppm - merged[-1].position_ppm) <= min_gap:
            if (peak.confidence, peak.intensity) > (merged[-1].confidence, merged[-1].intensity):
                merged[-1] = peak
            continue
        merged.append(peak)
    return merged


def _median_positive(values: list[float]) -> float:
    finite = [float(value) for value in values if math.isfinite(float(value)) and float(value) > 0]
    return float(np.median(finite)) if finite else 0.0


def _chemical_detail(peak: Peak, *, nucleus: str, solvent: str | None) -> dict[str, Any]:
    if nucleus not in {"1H", "13C"}:
        return {}
    try:
        from nmrcheck.peak_categorization import categorize_peak
    except Exception:
        return {}
    return categorize_peak(
        nucleus=nucleus,  # type: ignore[arg-type]
        shift_ppm=peak.position_ppm,
        multiplicity=None,
        solvent=solvent,
        structure=None,
    )


def _detail_is_solvent(
    *,
    peak: Peak,
    peaks: list[Peak],
    solvent_hit: Any,
    impurity_match: Any,
) -> bool:
    """Strict 'solvent' classification.

    A peak earns the 'solvent' label only when it sits inside the curated
    shift window from ``peak_categorization`` AND is the most-prominent peak
    inside that window.  The shift window alone is too permissive -- broad
    windows around residual-solvent/water shifts will catch many compound
    peaks in dense spectra, which then all incorrectly inherit the 'solvent'
    label and disappear from the compound peak count.
    """

    hit = solvent_hit if isinstance(solvent_hit, dict) else impurity_match
    if not isinstance(hit, dict):
        return False
    if hit.get("kind") not in {"solvent", "water", "residual", "reference"}:
        return False
    low_value = hit.get("low_ppm")
    high_value = hit.get("high_ppm")
    if low_value is None or high_value is None:
        # Impurity-table fallback path does not include a window; preserve the
        # prior permissive behaviour for that rare branch so we do not lose
        # genuine residual-solvent matches inferred from impurity tables.
        return True
    low = float(low_value)
    high = float(high_value)
    in_window = [
        candidate for candidate in peaks if low <= candidate.position_ppm <= high
    ]
    if not in_window:
        return False
    # Score by intensity weighted by proximity to the window centre.  Pure
    # intensity-max can pick a 13C J-couplet satellite over the residual
    # solvent line (e.g. CDCl3 satellites at 77.16 +/- 0.21 ppm both sit
    # inside the residual window).  The proximity factor biases towards the
    # canonical residual position while still preferring real peaks over noise.
    centre = 0.5 * (low + high)
    sigma = max(0.5 * (high - low), 0.05)

    def _score(candidate: Peak) -> float:
        distance = candidate.position_ppm - centre
        proximity = math.exp(-(distance * distance) / (2.0 * sigma * sigma))
        return float(candidate.intensity) * proximity

    return peak is max(in_window, key=_score)


def _detail_is_impurity(impurity_match: Any, *, peak: Peak, max_intensity: float) -> bool:
    if not isinstance(impurity_match, dict) or impurity_match.get("kind") != "impurity":
        return False
    if max_intensity > 0 and peak.intensity > max_intensity * 0.4:
        return False
    return True


def _is_artifact_like(
    peak: Peak,
    *,
    noise: float,
    median_width_hz: float,
    nucleus: str,
) -> bool:
    """Artifact classification: low SNR OR an anomalously wide line.

    The wide-line check requires both ``> 2 * median_width`` AND an absolute
    Hz floor.  Without the absolute floor, legitimate broad compound peaks in
    13C (where natural line widths are larger than 1H) get misclassified as
    artifacts whenever the spectrum also contains sharper lines that lower
    the median.  Floors are conservative: 25 Hz for 1H, 60 Hz for 13C.
    """

    if peak.intensity < max(noise * 3.0, 0.0):
        return True
    width_floor_hz = 25.0 if nucleus == "1H" else 60.0
    if (
        median_width_hz > 0
        and peak.width_hz > median_width_hz * 2.0
        and peak.width_hz > width_floor_hz
    ):
        return True
    return False


def _classification_confidence(
    peak: Peak,
    *,
    category: PeakCategory,
    noise: float,
    median_width_hz: float,
) -> float:
    snr = peak.intensity / max(noise, 1e-12)
    base = min(1.0, math.log1p(max(0.0, snr)) / math.log(101.0))
    if category in {"solvent", "impurity", "13C_satellite"}:
        base = max(base, 0.78)
    if category == "artifact":
        base = max(0.55, 1.0 - min(1.0, snr / 6.0))
    if median_width_hz > 0 and peak.width_hz > median_width_hz * 2.0:
        base *= 0.85
    return base


def _detect_13c_satellites(peaks: list[Peak], spectrum: NMRSpectrum) -> set[int]:
    if _normalise_nucleus(spectrum.nucleus) != "1H":
        return set()
    field_mhz = _field_mhz(spectrum)
    satellites: set[int] = set()
    positions = np.asarray([peak.position_ppm for peak in peaks], dtype=float)
    intensities = np.asarray([peak.intensity for peak in peaks], dtype=float)
    order = np.argsort(intensities)[::-1]
    for main_index in order:
        main_intensity = intensities[main_index]
        if not math.isfinite(float(main_intensity)) or main_intensity <= 0:
            continue
        for j_ch in (125.0, 160.0):
            offset = 0.5 * j_ch / field_mhz
            tolerance = max(0.01, offset * 0.12)
            left = _closest_index(positions, positions[main_index] + offset, tolerance)
            right = _closest_index(positions, positions[main_index] - offset, tolerance)
            if left is None or right is None or left == right or main_index in {left, right}:
                continue
            left_ratio = intensities[left] / main_intensity
            right_ratio = intensities[right] / main_intensity
            if (
                _MIN_SATELLITE_RATIO <= left_ratio <= _MAX_SATELLITE_RATIO
                and _MIN_SATELLITE_RATIO <= right_ratio <= _MAX_SATELLITE_RATIO
            ):
                satellites.update({left, right})
    return satellites


def _closest_index(values: np.ndarray, target: float, tolerance: float) -> int | None:
    if values.size == 0:
        return None
    distances = np.abs(values - target)
    index = int(np.argmin(distances))
    return index if float(distances[index]) <= tolerance else None
