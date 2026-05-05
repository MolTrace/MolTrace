from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from rdkit import Chem

from .carbon13 import Carbon13ParseError, analyze_carbon13_text, parse_carbon13_text
from .chemistry import mol_from_smiles
from .dept import find_dept_type_for_shift
from .exceptions import PeakParseError, StructureParseError
from .models import DeptAptPeak
from .nmr2d_models import (
    NMR2DAnalysisReport,
    NMR2DAnalyzeResult,
    NMR2DCorrelationEvidence,
    NMR2DPeak,
    NMR2DPreview,
)
from .nmr_tables import classify_carbon13_region, classify_proton_region, find_solvent_or_impurity_hits
from .parser import parse_nmr_text
from .proton import analyze_proton_evidence

_H_TOLERANCE = 0.07
_C_TOLERANCE = 0.85


@dataclass(frozen=True)
class _ReferencePeak:
    shift_ppm: float
    region: str
    is_artifact: bool = False


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _nearest(value: float | None, candidates: list[_ReferencePeak], tolerance: float) -> _ReferencePeak | None:
    if value is None or not candidates:
        return None
    nearest = min(candidates, key=lambda item: abs(item.shift_ppm - value))
    return nearest if abs(nearest.shift_ppm - value) <= tolerance else None


def _carbon_count(smiles: str) -> int:
    mol = mol_from_smiles(smiles)
    return sum(1 for atom in mol.GetAtoms() if atom.GetAtomicNum() == 6)


def _protonated_carbon_count(smiles: str) -> int:
    mol = Chem.AddHs(mol_from_smiles(smiles))
    count = 0
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6:
            continue
        if any(neighbor.GetAtomicNum() == 1 for neighbor in atom.GetNeighbors()):
            count += 1
    return count


def _proton_references(
    proton_nmr_text: str | None,
    *,
    smiles: str | None,
    solvent: str | None,
) -> tuple[list[_ReferencePeak], dict[str, Any] | None, list[str]]:
    if not proton_nmr_text or not proton_nmr_text.strip():
        return [], None, []
    warnings: list[str] = []
    evidence_metadata: dict[str, Any] | None = None
    if smiles:
        report = analyze_proton_evidence(smiles=smiles, nmr_text=proton_nmr_text, solvent=solvent)
        evidence_metadata = {
            "label": report.label,
            "overall_score": report.overall_score,
            "peak_count": len(report.peaks),
            "solvent_exclusion_score": report.solvent_exclusion_score,
        }
        warnings.extend(report.warnings)
        return [
            _ReferencePeak(
                shift_ppm=peak.shift_ppm,
                region=peak.region,
                is_artifact=bool(peak.is_likely_solvent or peak.is_likely_water),
            )
            for peak in report.peaks
        ], evidence_metadata, warnings
    try:
        parsed = parse_nmr_text(proton_nmr_text)
    except PeakParseError as exc:
        return [], None, [f"Could not parse linked ¹H trace text: {exc}"]
    return [
        _ReferencePeak(
            shift_ppm=peak.shift_ppm,
            region=classify_proton_region(peak.shift_ppm),
            is_artifact=bool(find_solvent_or_impurity_hits(peak.shift_ppm, solvent=solvent, nucleus="1H")),
        )
        for peak in parsed
    ], evidence_metadata, warnings


def _carbon_references(
    carbon13_text: str | None,
    *,
    smiles: str | None,
    solvent: str | None,
) -> tuple[list[_ReferencePeak], dict[str, Any] | None, list[str]]:
    if not carbon13_text or not carbon13_text.strip():
        return [], None, []
    warnings: list[str] = []
    evidence_metadata: dict[str, Any] | None = None
    if smiles:
        try:
            report = analyze_carbon13_text(smiles, carbon13_text, solvent=solvent)
            evidence_metadata = {
                "label": report.label,
                "confidence": report.confidence,
                "peak_count": len(report.peaks),
                "carbon13_match_score": report.carbon13_match_score,
            }
            warnings.extend(report.solvent_warnings)
            return [
                _ReferencePeak(
                    shift_ppm=peak.shift_ppm,
                    region=peak.region or classify_carbon13_region(peak.shift_ppm),
                    is_artifact=bool(peak.is_likely_solvent or peak.is_likely_impurity),
                )
                for peak in report.peaks
            ], evidence_metadata, warnings
        except (Carbon13ParseError, StructureParseError, ValueError) as exc:
            warnings.append(f"Could not score linked ¹³C evidence object: {exc}")
    try:
        parsed = parse_carbon13_text(carbon13_text, solvent=solvent)
    except (Carbon13ParseError, ValueError) as exc:
        return [], evidence_metadata, [*warnings, f"Could not parse linked ¹³C trace text: {exc}"]
    return [
        _ReferencePeak(
            shift_ppm=peak.shift_ppm,
            region=peak.region or classify_carbon13_region(peak.shift_ppm),
            is_artifact=bool(peak.is_likely_solvent or peak.is_likely_impurity),
        )
        for peak in parsed
    ], evidence_metadata, warnings


def _plausible_peak(peak: NMR2DPeak) -> bool:
    experiment = str(peak.experiment)
    if experiment == "COSY":
        return peak.proton1_ppm is not None and peak.proton2_ppm is not None
    return peak.proton1_ppm is not None and peak.carbon_ppm is not None


def _axis_plausible(peak: NMR2DPeak) -> bool:
    experiment = str(peak.experiment)
    if experiment == "COSY":
        return -1.0 <= peak.f2_ppm <= 16.0 and -1.0 <= peak.f1_ppm <= 16.0
    return -1.0 <= peak.f2_ppm <= 16.0 and -10.0 <= peak.f1_ppm <= 240.0


def _direct_hsqc_region_plausible(proton_ppm: float | None, carbon_ppm: float | None) -> tuple[bool, str]:
    if proton_ppm is None or carbon_ppm is None:
        return False, "Missing ¹H or ¹³C dimension for direct heteronuclear region check."
    windows = [
        (4.5, 6.0, 90.0, 110.0, "anomeric/acetal ¹H-¹³C region support"),
        (3.0, 4.5, 45.0, 90.0, "O/N-bearing ¹H-¹³C region support"),
        (0.5, 2.5, 0.0, 55.0, "aliphatic ¹H-¹³C region support"),
        (6.0, 8.5, 110.0, 160.0, "aromatic/vinylic ¹H-¹³C region support"),
    ]
    for h_low, h_high, c_low, c_high, label in windows:
        if h_low <= proton_ppm <= h_high and c_low <= carbon_ppm <= c_high:
            return True, label
    return False, "Direct ¹H-¹³C shift pairing is outside the conservative region windows."


def _peak_artifact_score(peak: NMR2DPeak, solvent: str | None) -> float:
    score = 0.0
    if peak.is_solvent_artifact:
        score += 1.0
    if find_solvent_or_impurity_hits(peak.f2_ppm, solvent=solvent, nucleus="1H"):
        score += 1.0
    if str(peak.experiment) == "COSY":
        if find_solvent_or_impurity_hits(peak.f1_ppm, solvent=solvent, nucleus="1H"):
            score += 1.0
    elif find_solvent_or_impurity_hits(peak.f1_ppm, solvent=solvent, nucleus="13C"):
        score += 1.0
    return min(score, 2.0)


def _match_score(matches: int, possible: int, *, fallback: float) -> float:
    if possible <= 0:
        return fallback
    return matches / possible


def analyze_nmr2d_preview(
    preview: NMR2DPreview,
    *,
    proton_nmr_text: str | None = None,
    carbon13_text: str | None = None,
    smiles: str | None = None,
    solvent: str | None = None,
    dept_apt_peaks: list[DeptAptPeak] | None = None,
    dept_apt_metadata: dict[str, Any] | None = None,
) -> NMR2DAnalyzeResult:
    proton_refs, proton_evidence_metadata, proton_warnings = _proton_references(
        proton_nmr_text,
        smiles=smiles,
        solvent=solvent,
    )
    carbon_refs, carbon_evidence_metadata, carbon_warnings = _carbon_references(
        carbon13_text,
        smiles=smiles,
        solvent=solvent,
    )

    correlations: list[NMR2DCorrelationEvidence] = []
    notes: list[str] = []
    warnings = [*preview.warnings, *proton_warnings, *carbon_warnings]
    experiment_counts = Counter(str(peak.experiment) for peak in preview.peaks)
    proton_graph_edges: set[tuple[str, str]] = set()
    symmetric_duplicates = 0
    duplicate_pairs: set[tuple[str, str]] = set()
    dimension_matches = 0
    dimension_possible = 0
    reference_matches = 0
    reference_possible = 0
    quality_values: list[float] = []
    experiment_values: list[float] = []
    artifact_units = 0.0
    suspicious_count = 0
    non_diagonal_cosy_count = 0
    plausible_count = 0
    dept_supported_count = 0
    dept_ambiguous_count = 0
    dept_conflicting_count = 0
    dept_contextual_count = 0

    for peak in preview.peaks:
        experiment = str(peak.experiment)
        matched_h_f2 = _nearest(peak.f2_ppm, proton_refs, _H_TOLERANCE)
        matched_h_f1 = _nearest(peak.f1_ppm, proton_refs, _H_TOLERANCE) if experiment == "COSY" else None
        matched_c_f1 = _nearest(peak.f1_ppm, carbon_refs, _C_TOLERANCE) if experiment != "COSY" else None
        dept_peak = find_dept_type_for_shift(dept_apt_peaks or [], peak.f1_ppm, tolerance=1.2) if experiment != "COSY" else None
        dept_type = str(dept_peak.carbon_type) if dept_peak is not None and dept_peak.carbon_type else None
        artifact_units += _peak_artifact_score(peak, solvent)
        if peak.is_suspicious:
            suspicious_count += 1

        correlation_notes = list(peak.notes)
        if peak.warnings:
            correlation_notes.extend(peak.warnings)

        if experiment == "COSY":
            dimension_possible += 2 if proton_refs else 1
            if proton_refs:
                dimension_matches += int(matched_h_f2 is not None) + int(matched_h_f1 is not None)
                reference_possible += 2
                reference_matches += int(matched_h_f2 is not None) + int(matched_h_f1 is not None)
            elif _axis_plausible(peak):
                dimension_matches += 1
            if peak.is_diagonal:
                quality_values.append(0.25)
                experiment_values.append(0.35)
                correlation_notes.append("Diagonal COSY peak excluded from connectivity score.")
                label = "diagonal_artifact"
                confidence = 0.25
            else:
                non_diagonal_cosy_count += 1
                left = matched_h_f2.shift_ppm if matched_h_f2 else peak.f2_ppm
                right = matched_h_f1.shift_ppm if matched_h_f1 else peak.f1_ppm
                pair_key = tuple(sorted((f"{left:.2f}", f"{right:.2f}")))
                if pair_key in proton_graph_edges:
                    symmetric_duplicates += 1
                    duplicate_pairs.add(pair_key)
                    correlation_notes.append("Symmetric COSY pair treated as supporting duplicate, not an extra error.")
                    label = "supportive_duplicate"
                    quality_values.append(0.72)
                else:
                    proton_graph_edges.add(pair_key)
                    label = "supportive" if (matched_h_f2 or matched_h_f1 or _axis_plausible(peak)) else "review"
                    quality_values.append(0.88 if label == "supportive" else 0.48)
                experiment_values.append(0.90 if label in {"supportive", "supportive_duplicate"} else 0.45)
                correlation_notes.append("¹H-¹H scalar connectivity evidence.")
                confidence = 0.86 if label == "supportive" else (0.74 if label == "supportive_duplicate" else 0.45)
            matched_1h = matched_h_f2.shift_ppm if matched_h_f2 else (matched_h_f1.shift_ppm if matched_h_f1 else None)
            matched_13c = None
        elif experiment in {"HSQC", "HMQC"}:
            dimension_possible += (1 if proton_refs else 0) + (1 if carbon_refs else 0)
            if proton_refs:
                dimension_matches += int(matched_h_f2 is not None)
                reference_possible += 1
                reference_matches += int(matched_h_f2 is not None)
            if carbon_refs:
                dimension_matches += int(matched_c_f1 is not None)
                reference_possible += 1
                reference_matches += int(matched_c_f1 is not None)
            if not proton_refs and not carbon_refs:
                dimension_possible += 1
                dimension_matches += int(_axis_plausible(peak))
            region_ok, region_note = _direct_hsqc_region_plausible(peak.proton1_ppm or peak.f2_ppm, peak.carbon_ppm or peak.f1_ppm)
            correlation_notes.append(region_note)
            correlation_notes.append("Direct ¹H-¹³C attachment evidence; do not treat intensity as carbon count.")
            dept_quality_adjustment = 0.0
            if dept_type:
                if dept_type == "C":
                    dept_conflicting_count += 1
                    suspicious_count += 1
                    dept_quality_adjustment = -0.28
                    correlation_notes.append(
                        "DEPT/APT conflict: HSQC/HMQC direct ¹H-¹³C attachment matched a quaternary carbon label; review this cross-peak."
                    )
                elif dept_type == "CH2_OR_C":
                    dept_ambiguous_count += 1
                    dept_quality_adjustment = -0.04
                    correlation_notes.append(
                        "DEPT/APT ambiguous support: matched CH2/quaternary group, so direct attachment remains plausible but requires review."
                    )
                elif dept_type in {"CH", "CH2", "CH3", "CH_OR_CH3"}:
                    dept_supported_count += 1
                    dept_quality_adjustment = 0.08
                    correlation_notes.append(
                        f"DEPT/APT supports a protonated carbon type ({dept_type}) for this direct attachment."
                    )
            direct_match_fraction = (
                (int(matched_h_f2 is not None) + int(matched_c_f1 is not None))
                / max(1, int(bool(proton_refs)) + int(bool(carbon_refs)))
                if (proton_refs or carbon_refs)
                else float(_axis_plausible(peak))
            )
            quality = _clamp(0.62 * direct_match_fraction + 0.38 * float(region_ok) + dept_quality_adjustment)
            quality_values.append(quality)
            experiment_values.append(0.95 if region_ok else 0.55)
            label = "supportive" if quality >= 0.62 else "review"
            confidence = _clamp(0.48 + 0.42 * quality)
            matched_1h = matched_h_f2.shift_ppm if matched_h_f2 else None
            matched_13c = matched_c_f1.shift_ppm if matched_c_f1 else None
        elif experiment == "HMBC":
            dimension_possible += (1 if proton_refs else 0) + (1 if carbon_refs else 0)
            if proton_refs:
                dimension_matches += int(matched_h_f2 is not None)
                reference_possible += 1
                reference_matches += int(matched_h_f2 is not None)
            if carbon_refs:
                dimension_matches += int(matched_c_f1 is not None)
                reference_possible += 1
                reference_matches += int(matched_c_f1 is not None)
            if not proton_refs and not carbon_refs:
                dimension_possible += 1
                dimension_matches += int(_axis_plausible(peak))
            plausible_axis = _axis_plausible(peak)
            if not plausible_axis:
                correlation_notes.append("HMBC correlation is outside typical ¹H/¹³C ranges; review referencing or artifact.")
            correlation_notes.append("Supports long-range heteronuclear connectivity.")
            correlation_notes.append("HMBC correlations require expert review and should not be treated as direct attachment.")
            if dept_type:
                dept_contextual_count += 1
                if dept_type == "C":
                    correlation_notes.append("DEPT/APT context: quaternary carbon labels can be valid HMBC long-range correlation targets and are not treated as conflicts.")
                else:
                    correlation_notes.append(f"DEPT/APT context: matched carbon type {dept_type}; HMBC remains long-range supporting evidence.")
            quality = 0.72 if plausible_axis else 0.35
            if matched_h_f2 or matched_c_f1:
                quality = min(0.9, quality + 0.12)
            quality_values.append(quality)
            experiment_values.append(0.78 if plausible_axis else 0.35)
            label = "long_range_support" if quality >= 0.62 else "review"
            confidence = _clamp(0.40 + 0.42 * quality)
            matched_1h = matched_h_f2.shift_ppm if matched_h_f2 else None
            matched_13c = matched_c_f1.shift_ppm if matched_c_f1 else None
        else:
            dimension_possible += 1
            dimension_matches += int(_axis_plausible(peak))
            quality_values.append(0.35)
            experiment_values.append(0.30)
            label = "review"
            confidence = 0.35
            matched_1h = matched_h_f2.shift_ppm if matched_h_f2 else None
            matched_13c = matched_c_f1.shift_ppm if matched_c_f1 else None
            correlation_notes.append("Unknown 2D experiment type; review manually.")

        if _plausible_peak(peak):
            plausible_count += 1
        if _peak_artifact_score(peak, solvent) > 0:
            correlation_notes.append("Solvent/artifact overlap reduces confidence for this cross-peak.")
            confidence = max(0.2, confidence - 0.15)
        correlations.append(
            NMR2DCorrelationEvidence(
                correlation_type=experiment,
                observed_f2_ppm=peak.f2_ppm,
                observed_f1_ppm=peak.f1_ppm,
                matched_1h_peak=round(matched_1h, 4) if matched_1h is not None else None,
                matched_13c_peak=round(matched_13c, 4) if matched_13c is not None else None,
                plausibility_label=label,
                confidence=round(_clamp(confidence), 4),
                notes=list(dict.fromkeys(correlation_notes)),
            )
        )

    peak_count = len(preview.peaks)
    dimension_match_score = round(_match_score(dimension_matches, dimension_possible, fallback=0.65 if peak_count else 0.0), 4)
    correlation_quality_score = round(sum(quality_values) / len(quality_values), 4) if quality_values else 0.0
    artifact_penalty = round(_clamp((artifact_units + 0.5 * suspicious_count) / max(1.0, peak_count * 3.0), 0.0, 0.35), 4)
    reference_support_score = round(_match_score(reference_matches, reference_possible, fallback=0.55 if peak_count else 0.0), 4)
    experiment_specific_score = round(sum(experiment_values) / len(experiment_values), 4) if experiment_values else 0.0
    duplicate_penalty = round(_clamp(symmetric_duplicates / max(1, non_diagonal_cosy_count) * 0.08, 0.0, 0.08), 4)
    suspicious_penalty = round(_clamp((suspicious_count - symmetric_duplicates) / max(1, peak_count) * 0.12, 0.0, 0.12), 4)
    dept_total = dept_supported_count + dept_ambiguous_count + dept_conflicting_count
    dept_apt_carbon_type_score = None
    dept_adjustment = 0.0
    if dept_total:
        dept_apt_carbon_type_score = round(
            _clamp((dept_supported_count + 0.5 * dept_ambiguous_count - dept_conflicting_count) / dept_total),
            4,
        )
        dept_adjustment = 0.06 * (dept_apt_carbon_type_score - 0.5)
    evidence_score = round(
        _clamp(
            0.30 * dimension_match_score
            + 0.27 * correlation_quality_score
            + 0.20 * reference_support_score
            + 0.23 * experiment_specific_score
            + dept_adjustment
            - artifact_penalty
            - duplicate_penalty
            - suspicious_penalty
        ),
        4,
    )

    if not proton_refs:
        warnings.append("No linked ¹H reference peak list was supplied or parsed; F2 dimension support is range-based only.")
    if any(exp in experiment_counts for exp in ("HSQC", "HMQC", "HMBC")) and not carbon_refs:
        warnings.append("No linked ¹³C reference peak list was supplied or parsed; F1 carbon support is range-based only.")
    if symmetric_duplicates:
        notes.append(f"{symmetric_duplicates} COSY symmetric duplicate(s) were treated as supporting duplicate observations.")
    if proton_graph_edges:
        notes.append(f"COSY proton connectivity graph contains {len(proton_graph_edges)} non-diagonal edge(s).")
    if experiment_counts.get("HMBC", 0):
        notes.append("HMBC supports long-range heteronuclear connectivity and requires expert review.")
    if dept_apt_peaks and (experiment_counts.get("HSQC", 0) or experiment_counts.get("HMQC", 0)):
        notes.append(
            f"DEPT/APT cross-check for HSQC/HMQC: {dept_supported_count} supported, {dept_ambiguous_count} ambiguous, {dept_conflicting_count} conflict(s)."
        )
    if dept_apt_peaks and experiment_counts.get("HMBC", 0):
        notes.append(
            f"DEPT/APT context for HMBC: {dept_contextual_count} matched carbon type annotation(s); quaternary targets are allowed for long-range correlations."
        )
    notes.append("2D NMR correlations are supporting evidence only; human review remains required.")

    matched_correlation_count = sum(1 for item in correlations if item.matched_1h_peak is not None or item.matched_13c_peak is not None)
    missing_reference_count = (
        sum(1 for item in correlations if item.matched_1h_peak is None and item.matched_13c_peak is None)
        if (proton_refs or carbon_refs)
        else 0
    )
    extra_correlation_count = sum(
        1
        for item in correlations
        if item.plausibility_label in {"diagonal_artifact", "review"} and "duplicate" not in item.plausibility_label
    )
    score_components = {
        "dimension_match_score": dimension_match_score,
        "correlation_quality_score": correlation_quality_score,
        "artifact_penalty": artifact_penalty,
        "reference_support_score": reference_support_score,
        "experiment_specific_score": experiment_specific_score,
        "duplicate_symmetric_pair_count": symmetric_duplicates,
        "duplicate_penalty": duplicate_penalty,
        "suspicious_penalty": suspicious_penalty,
        "non_diagonal_cosy_cross_peak_count": non_diagonal_cosy_count,
        "dept_apt_carbon_type_score": dept_apt_carbon_type_score,
    }
    correlation_summary = {
        "experiment_counts": dict(experiment_counts),
        "plausible_peak_count": plausible_count,
        "proton_reference_count": len(proton_refs),
        "carbon13_reference_count": len(carbon_refs),
        "matched_correlation_count": matched_correlation_count,
        "missing_reference_count": missing_reference_count,
        "extra_correlation_count": extra_correlation_count,
        "suspicious_peak_count": suspicious_count,
        "dept_apt_supported_correlations": dept_supported_count,
        "dept_apt_ambiguous_correlations": dept_ambiguous_count,
        "dept_apt_conflicting_correlations": dept_conflicting_count,
        "dept_apt_contextual_correlations": dept_contextual_count,
        "cosy_connectivity_graph": {
            "nodes": sorted({node for edge in proton_graph_edges for node in edge}),
            "edges": [list(edge) for edge in sorted(proton_graph_edges)],
        },
        "human_review_required": True,
    }

    return NMR2DAnalyzeResult(
        preview=preview,
        evidence_score=evidence_score,
        correlation_summary=correlation_summary,
        suspicious_peak_count=suspicious_count,
        matched_correlation_count=matched_correlation_count,
        missing_reference_count=missing_reference_count,
        extra_correlation_count=extra_correlation_count,
        correlations=correlations,
        notes=list(dict.fromkeys(notes)),
        warnings=list(dict.fromkeys(warnings)),
        metadata={
            "score_components": score_components,
            "proton_evidence": proton_evidence_metadata,
            "carbon13_evidence": carbon_evidence_metadata,
            "dept_apt_evidence": dept_apt_metadata,
            "solvent": solvent,
            "analysis_mode": "processed_2d_preview_evidence",
            "real_spectrum_evidence_unchanged": True,
        },
    )


def _linked_peaks_from_correlations(preview: NMR2DPreview, result: NMR2DAnalyzeResult) -> list[NMR2DPeak]:
    linked: list[NMR2DPeak] = []
    for peak, correlation in zip(preview.peaks, result.correlations, strict=False):
        notes = list(dict.fromkeys([*peak.notes, *correlation.notes]))
        label = correlation.plausibility_label
        if label in {"long_range_support", "supportive_duplicate"}:
            label = "supportive"
        linked.append(
            peak.model_copy(
                update={
                    "linked_proton_ppm": correlation.matched_1h_peak,
                    "linked_carbon_ppm": correlation.matched_13c_peak,
                    "evidence_label": label,
                    "notes": notes,
                }
            )
        )
    return linked


def analyze_nmr2d(
    *,
    smiles: str,
    preview: NMR2DPreview,
    sample_id: str | None = None,
    solvent: str | None = None,
    proton_nmr_text: str | None = None,
    carbon13_text: str | None = None,
    dept_apt_peaks: list[DeptAptPeak] | None = None,
    dept_apt_metadata: dict[str, Any] | None = None,
) -> NMR2DAnalysisReport:
    try:
        carbon_count = _carbon_count(smiles)
        protonated_carbons = _protonated_carbon_count(smiles)
    except StructureParseError:
        raise

    result = analyze_nmr2d_preview(
        preview,
        proton_nmr_text=proton_nmr_text,
        carbon13_text=carbon13_text,
        smiles=smiles,
        solvent=solvent,
        dept_apt_peaks=dept_apt_peaks,
        dept_apt_metadata=dept_apt_metadata,
    )
    linked_peaks = _linked_peaks_from_correlations(preview, result)
    experiment_counts = Counter(str(peak.experiment) for peak in linked_peaks)
    direct_count = experiment_counts.get("HSQC", 0) + experiment_counts.get("HMQC", 0)
    direct_expected = max(1, protonated_carbons)
    direct_score = 1.0
    if direct_count:
        direct_score = max(0.0, min(1.0, 1.0 - abs(direct_count - direct_expected) / max(direct_expected, direct_count, 1)))
    elif {"HSQC", "HMQC"} & set(str(item) for item in preview.experiments):
        direct_score = 0.25
    structure_score = round(0.70 * result.metadata["score_components"]["experiment_specific_score"] + 0.30 * direct_score, 4)
    correlation_score = round(
        0.70 * result.metadata["score_components"]["correlation_quality_score"]
        + 0.30 * result.metadata["score_components"]["reference_support_score"],
        4,
    )
    overall = result.evidence_score
    confidence = round(min(0.92, 0.35 + overall * 0.55), 4)
    if overall >= 0.72:
        label = "supportive"
    elif overall >= 0.45:
        label = "review"
    else:
        label = "weak"
    evidence_summary = {
        **result.correlation_summary,
        "linked_1d_peak_count": result.matched_correlation_count,
        "expected_carbon_count": carbon_count,
        "expected_protonated_carbon_count": protonated_carbons,
    }
    metadata = {
        **result.metadata,
        "feature": "week25_2d_nmr_evidence_engine_guarded",
        "raw_2d_fid_processing": "not_implemented",
        "report_integration": "nmr2d_run_report",
    }
    return NMR2DAnalysisReport(
        preview=result.preview,
        evidence_score=result.evidence_score,
        correlation_summary=result.correlation_summary,
        suspicious_peak_count=result.suspicious_peak_count,
        matched_correlation_count=result.matched_correlation_count,
        missing_reference_count=result.missing_reference_count,
        extra_correlation_count=result.extra_correlation_count,
        correlations=result.correlations,
        sample_id=sample_id,
        smiles=smiles,
        solvent=solvent,
        experiments=preview.experiments,
        peak_count=len(linked_peaks),
        linked_1d_peak_count=result.matched_correlation_count,
        correlation_score=correlation_score,
        structure_consistency_score=structure_score,
        overall_score=overall,
        confidence=confidence,
        label=label,  # type: ignore[arg-type]
        peaks=linked_peaks,
        warnings=result.warnings,
        notes=result.notes,
        evidence_summary=evidence_summary,
        metadata=metadata,
    )
