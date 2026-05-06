from __future__ import annotations

import math
import re
from collections.abc import Iterable

from .carbon13 import Carbon13ParseError, parse_carbon13_text
from .evidence import PeakMatch, gaussian_kernel, greedy_set_similarity
from .exceptions import PeakParseError
from .models import (
    NMR2DCrossPeakMatch,
    NMR2DPreviewReport,
    SpectralSimilarityLayerResult,
    SpectralSimilarityMatch,
    SpectralSimilarityRequest,
    SpectralSimilarityResult,
)
from .nmr2d import parse_nmr2d_table
from .parser import parse_nmr_text


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _experiment_value(value: object) -> str:
    if hasattr(value, "value"):
        return str(getattr(value, "value"))
    return str(value or "UNKNOWN").upper()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return 0.0
    return round(_clamp(dot / (norm_a * norm_b)), 4)


def gaussian_vectorize_1d(
    shifts: Iterable[float],
    *,
    weights: Iterable[float] | None = None,
    ppm_min: float,
    ppm_max: float,
    bins: int = 128,
    sigma: float = 0.08,
) -> list[float]:
    values = [float(shift) for shift in shifts]
    if weights is None:
        weight_values = [1.0] * len(values)
    else:
        weight_values = [float(weight) for weight in weights]
        if len(weight_values) != len(values):
            weight_values = [1.0] * len(values)
    if not values:
        return [0.0] * bins
    if bins < 2:
        bins = 2
    step = (ppm_max - ppm_min) / (bins - 1)
    vector: list[float] = []
    for idx in range(bins):
        target = ppm_min + idx * step
        vector.append(
            sum(
                weight * gaussian_kernel(target - shift, sigma)
                for shift, weight in zip(values, weight_values, strict=False)
            )
        )
    max_value = max(vector) if vector else 0.0
    if max_value > 0:
        vector = [value / max_value for value in vector]
    return vector


def _matches_to_models(matches: list[PeakMatch]) -> list[SpectralSimilarityMatch]:
    return [
        SpectralSimilarityMatch(
            observed_ppm=round(match.observed_ppm, 4),
            reference_ppm=round(match.expected_ppm, 4),
            delta_ppm=round(match.delta_ppm, 4),
            score=round(match.score, 4),
        )
        for match in matches[:50]
    ]


def _combine_vector_set(vector_score: float | None, set_score: float | None) -> float:
    if vector_score is None and set_score is None:
        return 0.0
    if vector_score is None:
        return _clamp(set_score or 0.0)
    if set_score is None:
        return _clamp(vector_score)
    return round(_clamp(0.45 * vector_score + 0.55 * set_score), 4)


def _clean_carbon13_text_for_similarity(text: str) -> str:
    return re.sub(r"\b(?:13\s*C|C\s*13)\b|¹³C", "carbon", text, flags=re.IGNORECASE)


def score_proton_similarity(observed_text: str, reference_text: str) -> SpectralSimilarityLayerResult:
    warnings: list[str] = []
    observed = parse_nmr_text(observed_text)
    reference = parse_nmr_text(reference_text)
    obs_shifts = [peak.shift_ppm for peak in observed]
    ref_shifts = [peak.shift_ppm for peak in reference]
    obs_weights = [max(0.1, peak.integration_h) for peak in observed]
    ref_weights = [max(0.1, peak.integration_h) for peak in reference]

    obs_multiset: list[float] = []
    ref_multiset: list[float] = []
    for shift, weight in zip(obs_shifts, obs_weights, strict=False):
        obs_multiset.extend([shift] * max(1, int(round(weight))))
    for shift, weight in zip(ref_shifts, ref_weights, strict=False):
        ref_multiset.extend([shift] * max(1, int(round(weight))))

    set_score, matches, unmatched_obs, unmatched_ref = greedy_set_similarity(obs_multiset, ref_multiset, sigma=0.08)
    vector_score = _cosine_similarity(
        gaussian_vectorize_1d(obs_shifts, weights=obs_weights, ppm_min=-1.0, ppm_max=12.0, bins=256, sigma=0.06),
        gaussian_vectorize_1d(ref_shifts, weights=ref_weights, ppm_min=-1.0, ppm_max=12.0, bins=256, sigma=0.06),
    )
    if unmatched_obs:
        warnings.append(f"{len(unmatched_obs)} observed 1H shift instance(s) were not matched to the reference.")
    if unmatched_ref:
        warnings.append(f"{len(unmatched_ref)} reference 1H shift instance(s) were not matched to the observed spectrum.")
    return SpectralSimilarityLayerResult(
        layer="1H",
        vector_score=vector_score,
        set_score=set_score,
        combined_score=_combine_vector_set(vector_score, set_score),
        observed_count=len(obs_multiset),
        reference_count=len(ref_multiset),
        matched_count=len(matches),
        unmatched_observed_count=len(unmatched_obs),
        unmatched_reference_count=len(unmatched_ref),
        matches=_matches_to_models(matches),
        notes=[
            "1H vector score uses Gaussian-smoothed weighted chemical shifts.",
            "1H set score uses greedy Gaussian peak matching with integration represented by repeated shifts.",
        ],
        warnings=warnings,
        metadata={"sigma_set_ppm": 0.08, "sigma_vector_ppm": 0.06, "bins": 256},
    )


def score_carbon13_similarity(
    observed_text: str,
    reference_text: str,
    *,
    solvent: str | None = None,
) -> SpectralSimilarityLayerResult:
    warnings: list[str] = []
    observed = [
        peak
        for peak in parse_carbon13_text(_clean_carbon13_text_for_similarity(observed_text), solvent=solvent)
        if not peak.is_likely_solvent
    ]
    reference = [
        peak
        for peak in parse_carbon13_text(_clean_carbon13_text_for_similarity(reference_text), solvent=solvent)
        if not peak.is_likely_solvent
    ]
    obs_shifts = [peak.shift_ppm for peak in observed]
    ref_shifts = [peak.shift_ppm for peak in reference]

    set_score, matches, unmatched_obs, unmatched_ref = greedy_set_similarity(obs_shifts, ref_shifts, sigma=1.2)
    vector_score = _cosine_similarity(
        gaussian_vectorize_1d(obs_shifts, ppm_min=0.0, ppm_max=230.0, bins=256, sigma=1.2),
        gaussian_vectorize_1d(ref_shifts, ppm_min=0.0, ppm_max=230.0, bins=256, sigma=1.2),
    )
    if unmatched_obs:
        warnings.append(f"{len(unmatched_obs)} observed 13C peak(s) were not matched to the reference.")
    if unmatched_ref:
        warnings.append(f"{len(unmatched_ref)} reference 13C peak(s) were not matched to the observed spectrum.")
    return SpectralSimilarityLayerResult(
        layer="13C",
        vector_score=vector_score,
        set_score=set_score,
        combined_score=_combine_vector_set(vector_score, set_score),
        observed_count=len(obs_shifts),
        reference_count=len(ref_shifts),
        matched_count=len(matches),
        unmatched_observed_count=len(unmatched_obs),
        unmatched_reference_count=len(unmatched_ref),
        matches=_matches_to_models(matches),
        notes=["13C similarity uses chemical shifts only; 13C intensities are not treated as quantitative carbon counts."],
        warnings=warnings,
        metadata={"sigma_set_ppm": 1.2, "sigma_vector_ppm": 1.2, "bins": 256, "solvent": solvent},
    )


def _sigma_for_2d(experiment: str) -> tuple[float, float]:
    return (0.08, 0.08) if experiment.upper() == "COSY" else (0.08, 1.2)


def _crosspeak_score(
    observed: tuple[float, float],
    reference: tuple[float, float],
    *,
    sigma_f2: float,
    sigma_f1: float,
) -> float:
    return gaussian_kernel(observed[0] - reference[0], sigma_f2) * gaussian_kernel(observed[1] - reference[1], sigma_f1)


def _score_crosspeak_sets(
    observed: list[tuple[float, float]],
    reference: list[tuple[float, float]],
    *,
    experiment: str,
) -> tuple[float, list[NMR2DCrossPeakMatch], list[tuple[float, float]], list[tuple[float, float]]]:
    if not observed and not reference:
        return 1.0, [], [], []
    if not observed or not reference:
        return 0.0, [], observed, reference
    sigma_f2, sigma_f1 = _sigma_for_2d(experiment)
    candidates: list[tuple[float, int, int]] = []
    for obs_idx, obs in enumerate(observed):
        for ref_idx, ref in enumerate(reference):
            candidates.append((_crosspeak_score(obs, ref, sigma_f2=sigma_f2, sigma_f1=sigma_f1), obs_idx, ref_idx))
    candidates.sort(reverse=True, key=lambda item: item[0])

    used_obs: set[int] = set()
    used_ref: set[int] = set()
    matches: list[NMR2DCrossPeakMatch] = []
    for score, obs_idx, ref_idx in candidates:
        if obs_idx in used_obs or ref_idx in used_ref or score < 0.05:
            continue
        used_obs.add(obs_idx)
        used_ref.add(ref_idx)
        obs = observed[obs_idx]
        ref = reference[ref_idx]
        matches.append(
            NMR2DCrossPeakMatch(
                observed_f2_ppm=round(obs[0], 4),
                observed_f1_ppm=round(obs[1], 4),
                reference_f2_ppm=round(ref[0], 4),
                reference_f1_ppm=round(ref[1], 4),
                delta_f2_ppm=round(abs(obs[0] - ref[0]), 4),
                delta_f1_ppm=round(abs(obs[1] - ref[1]), 4),
                score=round(score, 4),
            )
        )
    unmatched_obs = [peak for idx, peak in enumerate(observed) if idx not in used_obs]
    unmatched_ref = [peak for idx, peak in enumerate(reference) if idx not in used_ref]
    denom = math.sqrt(max(1, len(observed)) * max(1, len(reference)))
    similarity = sum(match.score for match in matches) / denom
    return round(_clamp(similarity), 4), matches[:50], unmatched_obs, unmatched_ref


def _vectorize_2d(
    peaks: list[tuple[float, float]],
    *,
    experiment: str,
    bins_f2: int = 64,
    bins_f1: int = 64,
) -> list[float]:
    if not peaks:
        return [0.0] * (bins_f2 * bins_f1)
    if experiment.upper() == "COSY":
        f1_min, f1_max = -1.0, 12.0
        sigma_f2, sigma_f1 = 0.10, 0.10
    else:
        f1_min, f1_max = 0.0, 230.0
        sigma_f2, sigma_f1 = 0.10, 1.8
    f2_min, f2_max = -1.0, 12.0
    vector: list[float] = []
    for f2_idx in range(bins_f2):
        f2 = f2_min + f2_idx * (f2_max - f2_min) / max(1, bins_f2 - 1)
        for f1_idx in range(bins_f1):
            f1 = f1_min + f1_idx * (f1_max - f1_min) / max(1, bins_f1 - 1)
            vector.append(
                sum(
                    gaussian_kernel(f2 - peak[0], sigma_f2) * gaussian_kernel(f1 - peak[1], sigma_f1)
                    for peak in peaks
                )
            )
    max_value = max(vector) if vector else 0.0
    if max_value > 0:
        vector = [value / max_value for value in vector]
    return vector


def score_nmr2d_similarity(
    observed_preview: NMR2DPreviewReport,
    reference_preview: NMR2DPreviewReport,
) -> SpectralSimilarityLayerResult:
    observed_peaks = [(peak.f2_ppm, peak.f1_ppm) for peak in observed_preview.peaks if not peak.is_diagonal]
    reference_peaks = [(peak.f2_ppm, peak.f1_ppm) for peak in reference_preview.peaks if not peak.is_diagonal]
    observed_experiment = _experiment_value(observed_preview.experiment_detected)
    reference_experiment = _experiment_value(reference_preview.experiment_detected)
    experiment = observed_experiment if observed_experiment != "UNKNOWN" else reference_experiment
    set_score, matches, unmatched_obs, unmatched_ref = _score_crosspeak_sets(
        observed_peaks,
        reference_peaks,
        experiment=experiment,
    )
    vector_score = _cosine_similarity(
        _vectorize_2d(observed_peaks, experiment=experiment),
        _vectorize_2d(reference_peaks, experiment=experiment),
    )
    warnings: list[str] = []
    if observed_experiment != reference_experiment and reference_experiment != "UNKNOWN":
        warnings.append("Observed and reference 2D experiment types differ; similarity should be reviewed.")
    if unmatched_obs:
        warnings.append(f"{len(unmatched_obs)} observed 2D cross-peak(s) were not matched to the reference.")
    if unmatched_ref:
        warnings.append(f"{len(unmatched_ref)} reference 2D cross-peak(s) were not matched to the observed spectrum.")
    layer = experiment if experiment in {"COSY", "HSQC", "HMQC", "HMBC"} else "2D"
    return SpectralSimilarityLayerResult(
        layer=layer,  # type: ignore[arg-type]
        vector_score=vector_score,
        set_score=set_score,
        combined_score=_combine_vector_set(vector_score, set_score),
        observed_count=len(observed_peaks),
        reference_count=len(reference_peaks),
        matched_count=len(matches),
        unmatched_observed_count=len(unmatched_obs),
        unmatched_reference_count=len(unmatched_ref),
        crosspeak_matches=matches,
        notes=[
            "2D set score uses greedy Gaussian matching over cross-peak pairs.",
            "COSY uses 1H/1H tolerances; HSQC/HMQC/HMBC use 1H/13C tolerances.",
            "Near-diagonal COSY peaks are excluded from connectivity similarity.",
        ],
        warnings=warnings,
        metadata={"experiment": experiment, "diagonal_peaks_excluded": True},
    )


def combine_similarity_layers(
    layers: list[SpectralSimilarityLayerResult],
    *,
    sample_id: str | None = None,
    solvent: str | None = None,
) -> SpectralSimilarityResult:
    if not layers:
        return SpectralSimilarityResult(
            sample_id=sample_id,
            solvent=solvent,
            overall_score=0.0,
            label="insufficient_evidence",
            warnings=["No comparable spectral layers were supplied."],
        )
    weights = {"1H": 0.38, "13C": 0.34, "COSY": 0.10, "HSQC": 0.16, "HMQC": 0.16, "HMBC": 0.12, "2D": 0.12}
    total = 0.0
    denom = 0.0
    for layer in layers:
        weight = weights.get(layer.layer, 0.12)
        total += layer.combined_score * weight
        denom += weight
    overall = round(_clamp(total / max(denom, 1e-12)), 4)
    if overall >= 0.82:
        label = "high_similarity"
    elif overall >= 0.60:
        label = "moderate_similarity"
    else:
        label = "low_similarity"
    return SpectralSimilarityResult(
        sample_id=sample_id,
        solvent=solvent,
        overall_score=overall,
        label=label,  # type: ignore[arg-type]
        layers=layers,
        evidence_layers_used=[layer.layer for layer in layers],
        notes=[
            "Overall score is a weighted combination of available 1H, 13C, and 2D layer scores.",
            "Similarity is a confidence aid and does not replace human review.",
        ],
        warnings=[warning for layer in layers for warning in layer.warnings],
        metadata={"weights": weights, "layer_count": len(layers)},
    )


def score_similarity_request(request: SpectralSimilarityRequest) -> SpectralSimilarityResult:
    layers: list[SpectralSimilarityLayerResult] = []
    warnings: list[str] = []
    if request.observed_proton_text and request.reference_proton_text:
        try:
            layers.append(score_proton_similarity(request.observed_proton_text, request.reference_proton_text))
        except PeakParseError as exc:
            warnings.append(f"1H similarity could not be scored: {exc}")
    if request.observed_carbon13_text and request.reference_carbon13_text:
        try:
            layers.append(
                score_carbon13_similarity(
                    request.observed_carbon13_text,
                    request.reference_carbon13_text,
                    solvent=request.solvent,
                )
            )
        except Carbon13ParseError as exc:
            warnings.append(f"13C similarity could not be scored: {exc}")
    result = combine_similarity_layers(layers, sample_id=request.sample_id, solvent=request.solvent)
    if warnings:
        result = result.model_copy(update={"warnings": [*result.warnings, *warnings]})
    return result
