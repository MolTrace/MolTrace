from __future__ import annotations

from .chemistry import structure_summary_from_smiles
from .exceptions import PeakParseError, StructureParseError
from .evidence import ratio_score
from .models import ProtonEvidencePeak, ProtonEvidenceReport
from .nmr_tables import classify_proton_region, find_solvent_or_impurity_hits
from .parser import parse_nmr_text, total_integrated_protons
from .settings import get_settings


def _resolved_solvent(solvent: str | None) -> str | None:
    return solvent or get_settings().default_solvent


def _label_from_scores(delta_total: float, delta_non_solvent: float, expected_labile: int) -> str:
    # Prefer non-solvent comparison when solvent/water peaks were detected.
    best_delta = delta_non_solvent if abs(delta_non_solvent) < abs(delta_total) else delta_total
    if abs(best_delta) <= 0.5:
        return "consistent"
    if best_delta < 0:
        return "possible_overlap_or_missing_labile_signals"
    return "possible_impurity_or_incorrect_assignment"


def analyze_proton_evidence(
    *,
    smiles: str,
    nmr_text: str,
    sample_id: str | None = None,
    solvent: str | None = None,
) -> ProtonEvidenceReport:
    solvent = _resolved_solvent(solvent)
    try:
        structure = structure_summary_from_smiles(smiles)
        parsed = parse_nmr_text(nmr_text)
    except (StructureParseError, PeakParseError) as exc:
        return ProtonEvidenceReport(
            sample_id=sample_id,
            smiles=smiles,
            solvent=solvent,
            expected_total_h=0,
            expected_non_labile_h=0,
            expected_labile_h=0,
            observed_total_h=0.0,
            observed_non_solvent_h=0.0,
            solvent_or_water_h=0.0,
            delta_total_h=0.0,
            delta_non_solvent_h=0.0,
            label="invalid_input",
            overall_score=0.0,
            integration_score=0.0,
            solvent_exclusion_score=0.0,
            region_support_score=0.0,
            peaks=[],
            notes=[str(exc)],
            warnings=[str(exc)],
            structure=None,
        )

    evidence_peaks: list[ProtonEvidencePeak] = []
    solvent_h = 0.0
    warnings: list[str] = []
    region_counts: dict[str, float] = {}

    for peak in parsed:
        hits = find_solvent_or_impurity_hits(peak.shift_ppm, solvent=solvent, nucleus="1H")
        is_solvent = any(hit.kind == "solvent" for hit in hits)
        is_water = any(hit.kind == "water" for hit in hits)
        notes = [f"Likely {hit.label}." for hit in hits]
        if is_solvent or is_water:
            solvent_h += peak.integration_h
        region = classify_proton_region(peak.shift_ppm)
        region_counts[region] = region_counts.get(region, 0.0) + peak.integration_h
        evidence_peaks.append(
            ProtonEvidencePeak(
                shift_ppm=peak.shift_ppm,
                multiplicity=peak.multiplicity,
                integration_h=peak.integration_h,
                region=region,
                is_likely_solvent=is_solvent,
                is_likely_water=is_water,
                notes=notes,
            )
        )

    observed_total = total_integrated_protons(parsed)
    observed_non_solvent = round(observed_total - solvent_h, 4)
    expected_non_labile = max(0, structure.non_labile_hydrogens)
    delta_total = round(observed_total - structure.total_hydrogens, 4)
    delta_non_solvent = round(observed_non_solvent - expected_non_labile, 4)
    label = _label_from_scores(delta_total, delta_non_solvent, structure.labile_hydrogens)

    # Score against both total H and non-labile H; use the better score because exchangeable protons and solvent inclusion are common.
    total_score = ratio_score(observed_total, structure.total_hydrogens, tolerance_fraction=0.25, absolute_tolerance=1.5)
    non_labile_score = ratio_score(observed_non_solvent, expected_non_labile, tolerance_fraction=0.25, absolute_tolerance=1.5)
    integration_score = max(total_score, non_labile_score)
    solvent_exclusion_score = 1.0 if observed_total == 0 else round(max(0.0, min(1.0, 1.0 - solvent_h / max(observed_total, 1e-6))), 4)

    # Simple region sanity score: enough non-solvent peaks and no extreme out-of-range peaks.
    unusual_penalty = sum(peak.integration_h for peak in evidence_peaks if "unusual" in peak.region.lower())
    region_support_score = round(max(0.0, min(1.0, 1.0 - unusual_penalty / max(observed_total, 1e-6))), 4)
    overall_score = round(0.55 * integration_score + 0.25 * solvent_exclusion_score + 0.20 * region_support_score, 4)

    notes: list[str] = []
    if solvent_h > 0:
        notes.append(f"Detected approximately {solvent_h:g}H of likely solvent/water-region signal and excluded it from the non-solvent comparison.")
    if structure.labile_hydrogens > 0:
        notes.append("Structure contains labile H atoms; missing OH/NH/SH signals can be chemically reasonable, especially in protic/deuterated solvents.")
    if label == "consistent":
        notes.append("1H evidence is consistent within tolerant real-spectrum assumptions.")
    elif label == "possible_overlap_or_missing_labile_signals":
        notes.append("Observed 1H integration is lower than expected; overlap, exchangeable protons, or broad/weak signals should be reviewed.")
    else:
        notes.append("Observed 1H integration is higher than expected; impurity, residual solvent, or over-integration should be reviewed.")
    if any(peak.is_likely_solvent or peak.is_likely_water for peak in evidence_peaks):
        warnings.append("One or more 1H peaks overlap known residual-solvent or water regions.")

    return ProtonEvidenceReport(
        sample_id=sample_id,
        smiles=smiles,
        solvent=solvent,
        expected_total_h=structure.total_hydrogens,
        expected_non_labile_h=expected_non_labile,
        expected_labile_h=structure.labile_hydrogens,
        observed_total_h=observed_total,
        observed_non_solvent_h=observed_non_solvent,
        solvent_or_water_h=round(solvent_h, 4),
        delta_total_h=delta_total,
        delta_non_solvent_h=delta_non_solvent,
        label=label,  # type: ignore[arg-type]
        overall_score=overall_score,
        integration_score=integration_score,
        solvent_exclusion_score=solvent_exclusion_score,
        region_support_score=region_support_score,
        peaks=evidence_peaks,
        notes=notes,
        warnings=warnings,
        structure=structure,
    )
