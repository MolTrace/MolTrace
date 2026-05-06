from __future__ import annotations

import re
from collections.abc import Iterable

from .hrms import (
    HRMSError,
    neutral_mass_from_mz,
    normalize_adduct,
    ppm_error,
    search_formulas_by_hrms,
    theoretical_mz,
)
from .models import (
    HRMSFormulaSearchRequest,
    MS1AdductInferenceCandidate,
    MS1AdductInferenceRequest,
    MS1AdductInferenceResult,
    MS1AdductPeakEvidence,
    MS1IsotopeCluster,
    MS1IsotopeClusterPeak,
    MS1Peak,
)

FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
C13_NEUTRON_SPACING = 1.00335483507
HALOGEN_M_PLUS_2_SPACING = 1.99705


class AdductInferenceError(ValueError):
    pass


def parse_ms1_peak_text(text: str) -> list[MS1Peak]:
    peaks: list[MS1Peak] = []
    for line_no, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        lowered = line.lower()
        if ("mz" in lowered or "m/z" in lowered) and ("int" in lowered or "abund" in lowered or "rel" in lowered):
            continue
        numbers = FLOAT_RE.findall(line.replace("%", " "))
        if len(numbers) < 2:
            if numbers:
                raise AdductInferenceError(f"MS1 peak line {line_no} must contain both m/z and intensity.")
            continue
        mz = float(numbers[0])
        intensity = float(numbers[1])
        if mz <= 0:
            raise AdductInferenceError(f"MS1 peak line {line_no} has non-positive m/z.")
        if intensity < 0:
            raise AdductInferenceError(f"MS1 peak line {line_no} has negative intensity.")
        peaks.append(MS1Peak(mz=mz, intensity=intensity))
    if not peaks:
        raise AdductInferenceError("No MS1 peaks were parsed. Provide lines like 'm/z,intensity'.")
    return peaks


def _normalize_peaks(peaks: Iterable[MS1Peak], *, min_relative_intensity: float, max_peaks: int) -> tuple[list[MS1Peak], int]:
    raw = [peak for peak in peaks if peak.intensity >= 0.0]
    if not raw:
        raise AdductInferenceError("At least one MS1 peak is required.")
    max_intensity = max((peak.relative_intensity if peak.relative_intensity is not None else peak.intensity) for peak in raw)
    if max_intensity <= 0:
        raise AdductInferenceError("At least one MS1 peak must have positive intensity.")
    normalized: list[MS1Peak] = []
    for peak in raw:
        relative = peak.relative_intensity if peak.relative_intensity is not None else peak.intensity / max_intensity * 100.0
        if relative >= min_relative_intensity:
            normalized.append(peak.model_copy(update={"relative_intensity": round(float(relative), 4)}))
    normalized.sort(key=lambda peak: peak.mz)
    if len(normalized) > max_peaks:
        normalized = sorted(normalized, key=lambda peak: peak.relative_intensity or 0.0, reverse=True)[:max_peaks]
        normalized.sort(key=lambda peak: peak.mz)
    return normalized, len(raw)


def _peak_tolerance(mz: float, *, mz_tolerance_da: float, ppm_tolerance: float) -> float:
    return max(float(mz_tolerance_da), abs(float(mz)) * float(ppm_tolerance) / 1_000_000.0)


def _closest_peak(peaks: list[MS1Peak], expected_mz: float, *, mz_tolerance_da: float, ppm_tolerance: float) -> MS1Peak | None:
    tolerance = _peak_tolerance(expected_mz, mz_tolerance_da=mz_tolerance_da, ppm_tolerance=ppm_tolerance)
    best: tuple[float, MS1Peak] | None = None
    for peak in peaks:
        delta = abs(peak.mz - expected_mz)
        if delta <= tolerance and (best is None or delta < best[0]):
            best = (delta, peak)
    return best[1] if best else None


def _cluster_peak(label: str, peak: MS1Peak, base_mz: float, expected_mz: float) -> MS1IsotopeClusterPeak:
    return MS1IsotopeClusterPeak(
        isotope_label=label,
        mz=round(peak.mz, 6),
        expected_mz=round(expected_mz, 6),
        delta_da=round(peak.mz - expected_mz, 6),
        relative_intensity=round(float(peak.relative_intensity or 0.0), 4),
        ppm_error=round(ppm_error(peak.mz, expected_mz), 3),
        spacing_from_m0_da=round(peak.mz - base_mz, 6),
    )


def _halogen_signature(m2_percent: float | None, m1_percent: float | None) -> str:
    if m2_percent is None:
        return "none_detected"
    if m2_percent >= 75:
        return "bromine_like"
    if 20 <= m2_percent < 75:
        return "chlorine_like"
    if 6 <= m2_percent < 20:
        return "sulfur_or_silicon_possible"
    if m1_percent is not None and m2_percent / max(m1_percent, 1.0) > 1.5:
        return "mixed_or_high_m_plus_2"
    return "none_detected"


def find_isotope_clusters(
    peaks: list[MS1Peak],
    *,
    mz_tolerance_da: float,
    ppm_tolerance: float,
    isotope_mz_tolerance_da: float,
    max_charge: int,
    max_clusters: int = 20,
) -> list[MS1IsotopeCluster]:
    clusters: list[MS1IsotopeCluster] = []
    max_charge = max(1, min(int(max_charge), 5))
    for base in peaks:
        if (base.relative_intensity or 0.0) <= 0:
            continue
        for charge in range(1, max_charge + 1):
            spacing = C13_NEUTRON_SPACING / charge
            m1_expected = base.mz + spacing
            m2_expected = base.mz + 2.0 * spacing
            m2_halogen_expected = base.mz + HALOGEN_M_PLUS_2_SPACING / charge
            m1 = _closest_peak(peaks, m1_expected, mz_tolerance_da=isotope_mz_tolerance_da, ppm_tolerance=ppm_tolerance)
            m2_regular = _closest_peak(peaks, m2_expected, mz_tolerance_da=isotope_mz_tolerance_da, ppm_tolerance=ppm_tolerance)
            m2_halogen = _closest_peak(peaks, m2_halogen_expected, mz_tolerance_da=isotope_mz_tolerance_da, ppm_tolerance=ppm_tolerance)
            if m2_regular is None or (m2_halogen is not None and abs(m2_halogen.mz - m2_halogen_expected) < abs(m2_regular.mz - m2_expected)):
                m2 = m2_halogen
                m2_expected_used = m2_halogen_expected
            else:
                m2 = m2_regular
                m2_expected_used = m2_expected
            cluster_peaks = [_cluster_peak("M", base, base.mz, base.mz)]
            m1_percent = None
            m2_percent = None
            if m1 is not None:
                m1_percent = round((float(m1.relative_intensity or 0.0) / max(float(base.relative_intensity or 1.0), 1e-9)) * 100.0, 3)
                cluster_peaks.append(_cluster_peak("M+1", m1, base.mz, m1_expected))
            if m2 is not None:
                m2_percent = round((float(m2.relative_intensity or 0.0) / max(float(base.relative_intensity or 1.0), 1e-9)) * 100.0, 3)
                cluster_peaks.append(_cluster_peak("M+2", m2, base.mz, m2_expected_used))
            if m1 is None and m2 is None:
                if (base.relative_intensity or 0.0) < 20:
                    continue
                label = "single_peak_only"
                score = 0.15
            elif (m1 is not None and m2 is not None) or (m2_percent is not None and m2_percent >= 20):
                label = "clear_isotope_cluster"
                score = 0.82
            else:
                label = "possible_isotope_cluster"
                score = 0.55
            carbon_estimate = round(m1_percent / 1.1, 1) if m1_percent is not None else None
            signature = _halogen_signature(m2_percent, m1_percent)
            evidence = [f"Monoisotopic candidate at m/z {base.mz:.5f}; charge estimate z={charge}."]
            if m1_percent is not None:
                evidence.append(f"M+1 is approximately {m1_percent:.2f}% of M; rough carbon estimate ≈ {carbon_estimate:g}.")
            if m2_percent is not None:
                evidence.append(f"M+2 is approximately {m2_percent:.2f}% of M; isotope signature: {signature}.")
            if label == "single_peak_only":
                evidence.append("No isotope satellites were detected within tolerance; treat adduct/formula inference as tentative.")
            warnings: list[str] = []
            if carbon_estimate is not None and carbon_estimate > 120:
                warnings.append("M+1 carbon estimate is unusually high for the configured small-molecule workflow.")
            if signature in {"chlorine_like", "bromine_like", "mixed_or_high_m_plus_2"}:
                score = min(1.0, score + 0.08)
            clusters.append(
                MS1IsotopeCluster(
                    monoisotopic_mz=round(base.mz, 6),
                    charge=charge,
                    label=label,
                    confidence_score=round(score, 4),
                    m_plus_1_percent=m1_percent,
                    m_plus_2_percent=m2_percent,
                    estimated_carbon_count=carbon_estimate,
                    halogen_signature=signature,
                    peaks=cluster_peaks,
                    evidence_summary=evidence,
                    warnings=warnings,
                )
            )
    clusters.sort(key=lambda cluster: (cluster.confidence_score, len(cluster.peaks), -(cluster.monoisotopic_mz)), reverse=True)
    deduped: list[MS1IsotopeCluster] = []
    seen: set[tuple[int, int]] = set()
    for cluster in clusters:
        key = (int(round(cluster.monoisotopic_mz * 1000)), cluster.charge)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cluster)
        if len(deduped) >= max_clusters:
            break
    return deduped


def _adducts_for_mode(mode: str | None) -> list[str]:
    if mode == "negative":
        return ["[M-H]-", "[M+Cl]-", "[M+FA-H]-", "[M+Ac-H]-"]
    if mode == "neutral":
        return ["M"]
    return ["[M+H]+", "[M+Na]+", "[M+K]+", "[M+NH4]+"]


def _adduct_prior(name: str) -> float:
    return {
        "[M+H]+": 0.95,
        "[M-H]-": 0.95,
        "[M+Na]+": 0.72,
        "[M+NH4]+": 0.68,
        "[M+K]+": 0.56,
        "[M+Cl]-": 0.70,
        "[M+FA-H]-": 0.62,
        "[M+Ac-H]-": 0.60,
        "M": 0.40,
    }.get(name, 0.40)


def _isotope_formula_score(cluster: MS1IsotopeCluster | None, formula) -> float | None:
    if cluster is None or (cluster.m_plus_1_percent is None and cluster.m_plus_2_percent is None):
        return None
    scores: list[float] = []
    if cluster.m_plus_1_percent is not None and formula.isotope_m_plus_1_percent is not None:
        tolerance = max(2.0, formula.isotope_m_plus_1_percent * 0.35)
        scores.append(max(0.0, min(1.0, 1.0 - abs(cluster.m_plus_1_percent - formula.isotope_m_plus_1_percent) / tolerance)))
    if cluster.m_plus_2_percent is not None and formula.isotope_m_plus_2_percent is not None:
        tolerance = max(2.0, formula.isotope_m_plus_2_percent * 0.35)
        scores.append(max(0.0, min(1.0, 1.0 - abs(cluster.m_plus_2_percent - formula.isotope_m_plus_2_percent) / tolerance)))
    return round(sum(scores) / len(scores), 4) if scores else None


def _find_adduct_pair_peaks(
    neutral_mass: float,
    current_adduct: str,
    mode: str | None,
    peaks: list[MS1Peak],
    *,
    mz_tolerance_da: float,
    ppm_tolerance: float,
) -> list[MS1AdductPeakEvidence]:
    matches: list[MS1AdductPeakEvidence] = []
    for other_name in _adducts_for_mode(mode):
        if other_name == current_adduct:
            continue
        other = normalize_adduct(other_name)
        expected = theoretical_mz(neutral_mass, other)
        if expected <= 0:
            continue
        peak = _closest_peak(peaks, expected, mz_tolerance_da=mz_tolerance_da, ppm_tolerance=ppm_tolerance)
        if peak is not None:
            matches.append(
                MS1AdductPeakEvidence(
                    adduct=other.name,
                    observed_mz=round(peak.mz, 6),
                    expected_mz=round(expected, 6),
                    ppm_error=round(ppm_error(peak.mz, expected), 3),
                    relative_intensity=round(float(peak.relative_intensity or 0.0), 4),
                )
            )
    matches.sort(key=lambda item: abs(item.ppm_error))
    return matches


def _candidate_label(score: float, formula_count: int, neutral_mass: float) -> str:
    if neutral_mass <= 0:
        return "incompatible_adduct"
    if score >= 0.72 and formula_count > 0:
        return "strong_adduct_evidence"
    if score >= 0.45:
        return "plausible_adduct"
    return "weak_adduct_evidence"


def infer_adducts_and_isotopes(req: MS1AdductInferenceRequest) -> MS1AdductInferenceResult:
    peaks = list(req.peaks or [])
    if req.peak_list_text:
        peaks.extend(parse_ms1_peak_text(req.peak_list_text))
    normalized, raw_count = _normalize_peaks(
        peaks,
        min_relative_intensity=req.min_relative_intensity,
        max_peaks=req.max_peaks_to_analyze,
    )
    clusters = find_isotope_clusters(
        normalized,
        mz_tolerance_da=req.mz_tolerance_da,
        ppm_tolerance=req.ppm_tolerance,
        isotope_mz_tolerance_da=req.isotope_mz_tolerance_da,
        max_charge=req.max_charge,
        max_clusters=req.max_clusters,
    )
    best_cluster = clusters[0] if clusters else None
    if req.target_mz is not None:
        primary_mz = float(req.target_mz)
        matched_primary = _closest_peak(normalized, primary_mz, mz_tolerance_da=req.mz_tolerance_da, ppm_tolerance=req.ppm_tolerance)
        if matched_primary is not None:
            primary_mz = matched_primary.mz
    elif best_cluster is not None:
        primary_mz = best_cluster.monoisotopic_mz
    else:
        primary_mz = max(normalized, key=lambda peak: peak.relative_intensity or 0.0).mz
    primary_cluster = (
        next(
            (
                cluster
                for cluster in clusters
                if abs(cluster.monoisotopic_mz - primary_mz)
                <= _peak_tolerance(primary_mz, mz_tolerance_da=req.mz_tolerance_da, ppm_tolerance=req.ppm_tolerance)
            ),
            None,
        )
        or best_cluster
    )
    mode = req.ion_mode or "positive"
    warnings: list[str] = []
    candidates: list[MS1AdductInferenceCandidate] = []
    for adduct_name in _adducts_for_mode(mode):
        try:
            adduct = normalize_adduct(adduct_name)
            neutral_mass = neutral_mass_from_mz(primary_mz, adduct)
        except HRMSError as exc:
            warnings.append(str(exc))
            continue
        item_warnings: list[str] = []
        evidence: list[str] = [f"{adduct.name} gives neutral mass {neutral_mass:.6f} from primary m/z {primary_mz:.6f}."]
        formula_candidates = []
        formula_count = 0
        best_formula_isotope_score = None
        formula_score = 0.0
        if neutral_mass <= 0:
            item_warnings.append("Neutral mass is non-positive for this adduct; candidate is incompatible.")
        elif req.perform_formula_search:
            try:
                formula_result = search_formulas_by_hrms(
                    HRMSFormulaSearchRequest(
                        observed_mz=primary_mz,
                        adduct=adduct.name,
                        ppm_tolerance=req.ppm_tolerance,
                        max_c=req.max_c,
                        max_h=req.max_h,
                        max_n=req.max_n,
                        max_o=req.max_o,
                        max_s=req.max_s,
                        max_p=req.max_p,
                        max_cl=req.max_cl,
                        max_br=req.max_br,
                        require_nonnegative_dbe=req.require_nonnegative_dbe,
                        max_results=req.formula_candidates_per_adduct,
                    )
                )
                formula_candidates = formula_result.formulas
                formula_count = formula_result.formula_count
                if formula_count:
                    evidence.append(f"Formula search found {formula_count} formula candidate(s) within {req.ppm_tolerance:g} ppm.")
                    isotope_scores = [score for score in (_isotope_formula_score(primary_cluster, formula) for formula in formula_candidates) if score is not None]
                    if isotope_scores:
                        best_formula_isotope_score = max(isotope_scores)
                        evidence.append(f"Best formula/isotope agreement score: {best_formula_isotope_score:.2f}.")
                    formula_score = best_formula_isotope_score if best_formula_isotope_score is not None else 0.70
                else:
                    evidence.append("Formula search found no formula candidates with current bounds/tolerance.")
                item_warnings.extend(formula_result.warnings)
            except Exception as exc:
                item_warnings.append(f"Formula search failed for {adduct.name}: {exc}")
        else:
            formula_score = 0.40
            evidence.append("Formula search disabled; score is based on isotope cluster and adduct-pair evidence only.")
        pair_matches: list[MS1AdductPeakEvidence] = []
        if neutral_mass > 0:
            pair_matches = _find_adduct_pair_peaks(
                neutral_mass,
                adduct.name,
                mode,
                normalized,
                mz_tolerance_da=req.mz_tolerance_da,
                ppm_tolerance=req.ppm_tolerance,
            )
            if pair_matches:
                evidence.append(f"Detected {len(pair_matches)} paired adduct peak(s) consistent with the same neutral mass.")
        pair_score = min(1.0, len(pair_matches) / 2.0)
        cluster_score = primary_cluster.confidence_score if primary_cluster is not None else 0.0
        score = round(max(0.0, min(1.0, 0.30 * _adduct_prior(adduct.name) + 0.35 * formula_score + 0.25 * cluster_score + 0.10 * pair_score)), 4)
        candidates.append(
            MS1AdductInferenceCandidate(
                rank=0,
                label=_candidate_label(score, formula_count, neutral_mass),
                adduct=adduct,
                observed_mz=round(primary_mz, 6),
                neutral_mass=round(neutral_mass, 6),
                formula_count=formula_count,
                top_formulas=formula_candidates,
                isotope_score=best_formula_isotope_score,
                adduct_pair_count=len(pair_matches),
                adduct_peak_matches=pair_matches,
                candidate_score=score,
                evidence_summary=evidence,
                warnings=item_warnings,
                metadata={"adduct_prior": _adduct_prior(adduct.name), "formula_search_performed": req.perform_formula_search},
            )
        )
    ranked = [
        item.model_copy(update={"rank": index + 1})
        for index, item in enumerate(sorted(candidates, key=lambda item: (item.candidate_score, item.formula_count, item.adduct_pair_count), reverse=True))
    ]
    notes = [
        "Adduct and isotope inference is a triage layer; it proposes plausible ion assignments but does not prove molecular identity.",
        "Use inferred adducts with HRMS formula search, MS/MS fragments, NMR evidence, and human review.",
    ]
    if primary_cluster and primary_cluster.halogen_signature in {"chlorine_like", "bromine_like", "mixed_or_high_m_plus_2"}:
        notes.append(f"Primary isotope cluster indicates {primary_cluster.halogen_signature}; formula bounds should allow relevant halogens.")
    return MS1AdductInferenceResult(
        sample_id=req.sample_id,
        ion_mode=mode,
        peak_count=raw_count,
        analyzed_peak_count=len(normalized),
        primary_mz=round(primary_mz, 6),
        inferred_charge=primary_cluster.charge if primary_cluster else None,
        inferred_m_plus_1_percent=primary_cluster.m_plus_1_percent if primary_cluster else None,
        inferred_m_plus_2_percent=primary_cluster.m_plus_2_percent if primary_cluster else None,
        isotope_clusters=clusters,
        best_adduct_candidate=ranked[0] if ranked else None,
        adduct_candidates=ranked,
        warnings=warnings,
        notes=notes,
        metadata={
            "min_relative_intensity": req.min_relative_intensity,
            "max_peaks_to_analyze": req.max_peaks_to_analyze,
            "target_mz_requested": req.target_mz,
        },
    )
