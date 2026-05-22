from __future__ import annotations

from .carbon13 import (
    Carbon13ParseError,
    expected_carbon_count_from_smiles,
    parse_carbon13_text,
)
from .chemistry import structure_summary_from_smiles
from .exceptions import PeakParseError, StructureParseError
from .models import (
    AnalysisInputs,
    AnalysisReport,
    AnalysisValidationInputs,
    Carbon13Peak,
    Peak,
    StructureSummary,
    ValidationReport,
)
from .parser import parse_nmr_text, total_integrated_protons
from .proton import analyze_proton_evidence
from .settings import get_settings
from .solvents import find_solvent_peak_hit_indices, find_solvent_peak_hits, get_solvent_profile


def _confidence_from_delta(delta: int, expected_labile_h: int) -> float:
    magnitude = abs(delta)
    if magnitude == 0:
        return 0.96
    if magnitude <= max(1, expected_labile_h):
        return 0.76
    if magnitude <= 2:
        return 0.67
    if magnitude <= 4:
        return 0.82
    return 0.91


def _empty_structure(smiles: str) -> StructureSummary:
    return StructureSummary(
        smiles=smiles,
        formula="",
        molecular_weight=0.0,
        total_hydrogens=0,
        labile_hydrogens=0,
        non_labile_hydrogens=0,
        aromatic_protons=0,
        aliphatic_protons=0,
        aromatic_atom_count=0,
    )


def _resolved_solvent(solvent: str | None) -> str | None:
    return solvent or get_settings().default_solvent


def _has_broad_peak(peaks: list[Peak]) -> bool:
    return any(peak.multiplicity.lower().startswith("br") for peak in peaks)


def _pattern_alerts(
    *,
    peaks: list[Peak],
    structure: StructureSummary,
    delta_total_h: int,
    solvent_hits_count: int,
    solvent: str | None,
) -> list[str]:
    alerts: list[str] = []
    aromatic_peaks = [peak for peak in peaks if 6.0 <= peak.shift_ppm <= 8.6]
    aliphatic_singlets = [
        peak
        for peak in peaks
        if peak.multiplicity.lower() in {"s", "br s"} and peak.integration_h >= 3 and peak.shift_ppm <= 2.2
    ]
    heteroatom_adjacent = [
        peak for peak in peaks if 2.2 <= peak.shift_ppm <= 4.5 and peak.integration_h >= 2
    ]

    if structure.aromatic_atom_count >= 6 and len(aromatic_peaks) >= 3:
        alerts.append(
            "Aromatic-region crowding is present, so overlap in the 6.0–8.6 ppm window may be hiding or distorting integrations."
        )
    if delta_total_h > 0 and aliphatic_singlets and solvent_hits_count == 0:
        alerts.append(
            "An isolated aliphatic singlet with substantial integration is present without a solvent match; that pattern is often worth checking as a purification-related impurity."
        )
    if delta_total_h > 0 and heteroatom_adjacent and solvent_hits_count == 0:
        alerts.append(
            "Extra integration appears in the 2.2–4.5 ppm region, which can be consistent with residual reagent, solvent carryover, or another heteroatom-adjacent impurity."
        )
    if solvent and solvent.upper() == "D2O" and structure.labile_hydrogens > 0:
        alerts.append(
            "Because D2O was specified and the structure contains labile hydrogens, exchange suppression of OH/NH/SH signals should be assumed unless proven otherwise."
        )
    if _has_broad_peak(peaks) and structure.labile_hydrogens > 0:
        alerts.append(
            "Broad peaks plus labile hydrogens strengthen an exchange-based explanation for small proton deficits."
        )
    return alerts


def _expected_visible_h(structure: StructureSummary, solvent: str | None) -> float:
    if solvent and solvent.upper() == "D2O":
        return float(structure.non_labile_hydrogens)
    return float(structure.total_hydrogens)


def _structure_match_validation(
    *,
    peaks: list[Peak],
    structure: StructureSummary,
    solvent: str | None,
) -> tuple[list[str], list[str], float, float, float, float]:
    errors: list[str] = []
    warnings: list[str] = []
    expected_visible_h = _expected_visible_h(structure, solvent)
    observed_total_h = total_integrated_protons(peaks)
    solvent_hit_indices = find_solvent_peak_hit_indices(peaks, solvent)
    adjusted_observed_total_h = round(
        sum(peak.integration_h for index, peak in enumerate(peaks) if index not in solvent_hit_indices),
        4,
    )
    observed_for_match = adjusted_observed_total_h if solvent_hit_indices else observed_total_h
    delta_visible_h = round(observed_for_match - expected_visible_h, 4)

    if solvent_hit_indices:
        warnings.append(
            "Likely residual-solvent and water peaks were excluded while checking the SMILES-to-1H NMR proton-count match."
        )

    allowed_deficit = 0.5 if solvent and solvent.upper() == "D2O" else max(0.5, float(structure.labile_hydrogens))
    expected_label = "visible H" if solvent and solvent.upper() == "D2O" else "total H"
    if delta_visible_h > 0.5:
        errors.append(
            f"SMILES / 1H NMR mismatch: the parsed text accounts for {observed_for_match:g}H, but the structure expects {expected_visible_h:g} {expected_label}."
        )
    elif delta_visible_h < -allowed_deficit:
        errors.append(
            f"SMILES / 1H NMR mismatch: the parsed text accounts for only {observed_for_match:g}H, but the structure expects {expected_visible_h:g} {expected_label}."
        )
    elif delta_visible_h < -0.5:
        warnings.append(
            "The parsed 1H NMR text is slightly lower than the structure-based expectation, but the difference stays within the allowed labile-hydrogen/exchange window."
        )

    aromatic_observed_h = round(
        sum(
            peak.integration_h
            for index, peak in enumerate(peaks)
            if index not in solvent_hit_indices and 6.0 <= peak.shift_ppm <= 8.6
        ),
        4,
    )
    if structure.aromatic_protons == 0 and aromatic_observed_h >= 1.0:
        errors.append(
            f"SMILES / 1H NMR mismatch: about {aromatic_observed_h:g}H appears in the aromatic region, but the structure has no aromatic protons."
        )
    elif structure.aromatic_protons >= 2 and aromatic_observed_h < 0.5:
        errors.append(
            f"SMILES / 1H NMR mismatch: the structure contains {structure.aromatic_protons} aromatic protons, but the text does not show a corresponding aromatic region."
        )

    return (
        errors,
        warnings,
        expected_visible_h,
        observed_total_h,
        adjusted_observed_total_h,
        delta_visible_h,
    )


def _carbon13_match_validation(
    *,
    peaks: list[Carbon13Peak],
    expected_carbon_count: int,
) -> tuple[list[str], list[str], int, int]:
    """Cross-check the parsed ¹³C signal count against the SMILES carbon count.

    Returns ``(errors, warnings, observed_signal_count, delta_signals)``.
    Fewer signals than carbons is treated as benign — molecular symmetry and
    equivalence collapse carbons onto shared signals — while more signals than
    carbons is suspicious and escalates to an error once it exceeds a small
    structure-scaled tolerance (rotamer doubling can explain a slight excess).
    """
    errors: list[str] = []
    warnings: list[str] = []
    solvent_peaks = [peak for peak in peaks if peak.is_likely_solvent]
    non_solvent_peaks = [peak for peak in peaks if not peak.is_likely_solvent]
    observed = len(non_solvent_peaks)
    delta = observed - expected_carbon_count

    if solvent_peaks:
        warnings.append(
            f"{len(solvent_peaks)} likely residual-solvent ¹³C peak(s) were excluded "
            "while checking the SMILES-to-¹³C signal-count match."
        )

    if delta > 0:
        allowed_overage = max(1, round(expected_carbon_count * 0.15))
        if delta > allowed_overage:
            errors.append(
                f"SMILES / ¹³C NMR mismatch: the parsed text reports {observed} carbon "
                f"signals, but the structure has only {expected_carbon_count} carbon atoms."
            )
        else:
            warnings.append(
                f"The ¹³C text reports {observed} signals, slightly more than the "
                f"structure's {expected_carbon_count} carbons; rotamers, an impurity "
                "peak, or a stray value in the text are possible and worth a check."
            )
    elif delta < 0:
        warnings.append(
            f"The ¹³C text reports {observed} signals for a structure with "
            f"{expected_carbon_count} carbons; fewer signals than carbons usually "
            "reflects molecular symmetry or equivalence, though peak overlap and weak "
            "quaternary carbons can also reduce the count."
        )

    return errors, warnings, observed, delta


def validate_inputs(payload: AnalysisInputs | AnalysisValidationInputs) -> ValidationReport:
    warnings: list[str] = []
    errors: list[str] = []
    structure: StructureSummary | None = None
    parsed_peaks: list[Peak] = []
    structure_valid = False
    nmr_text_valid = False
    structure_nmr_match = False
    carbon13_text_valid = False
    structure_carbon13_match = False
    smiles = (payload.smiles or "").strip()
    nmr_text = (payload.nmr_text or "").strip()
    carbon13_text = (getattr(payload, "carbon13_text", None) or "").strip()
    solvent = _resolved_solvent(payload.solvent)
    expected_visible_h: float | None = None
    observed_total_h: float | None = None
    adjusted_observed_total_h: float | None = None
    delta_visible_h: float | None = None
    parsed_carbon13_peaks: list[Carbon13Peak] = []
    expected_carbon_count: int | None = None
    observed_carbon_signal_count: int | None = None
    delta_carbon_signals: int | None = None

    if smiles:
        try:
            structure = structure_summary_from_smiles(smiles)
            structure_valid = True
            if structure.labile_hydrogens > 0:
                warnings.append(
                    "The structure contains labile hydrogens, so OH/NH/SH integrations may be incomplete."
                )
            if structure.aromatic_atom_count >= 6:
                warnings.append("The structure contains an aromatic system, so peak overlap is plausible.")
        except StructureParseError as exc:
            errors.append(str(exc))
    else:
        warnings.append("Enter a SMILES structure before running analysis.")

    if nmr_text:
        try:
            parsed_peaks = parse_nmr_text(nmr_text)
            nmr_text_valid = True
        except PeakParseError as exc:
            errors.append(str(exc))
    else:
        warnings.append("Enter 1H NMR text before running analysis.")

    # ¹³C NMR text is an optional supplementary layer: parse and cross-check it
    # only when supplied. Its absence is intentionally silent (no warning),
    # unlike the SMILES / ¹H NMR primary inputs above.
    if carbon13_text:
        try:
            parsed_carbon13_peaks = parse_carbon13_text(carbon13_text, solvent=solvent)
            carbon13_text_valid = True
        except Carbon13ParseError as exc:
            errors.append(str(exc))

    profile = get_solvent_profile(solvent)
    if solvent and profile is None:
        warnings.append(f"Solvent '{solvent}' is not recognized, so solvent-specific heuristics are disabled.")
    elif profile is not None:
        warnings.append(
            f"Solvent heuristics are enabled for {profile.canonical_name}; residual-solvent and water peaks will be checked approximately."
        )

    if structure_valid and nmr_text_valid and structure is not None:
        (
            match_errors,
            match_warnings,
            expected_visible_h,
            observed_total_h,
            adjusted_observed_total_h,
            delta_visible_h,
        ) = _structure_match_validation(
            peaks=parsed_peaks,
            structure=structure,
            solvent=solvent,
        )
        errors.extend(match_errors)
        warnings.extend(match_warnings)
        structure_nmr_match = not match_errors

    if structure_valid and carbon13_text_valid:
        expected_carbon_count = expected_carbon_count_from_smiles(smiles)
        (
            carbon_errors,
            carbon_warnings,
            observed_carbon_signal_count,
            delta_carbon_signals,
        ) = _carbon13_match_validation(
            peaks=parsed_carbon13_peaks,
            expected_carbon_count=expected_carbon_count,
        )
        errors.extend(carbon_errors)
        warnings.extend(carbon_warnings)
        structure_carbon13_match = not carbon_errors

    analysis_ready = structure_valid and nmr_text_valid and structure_nmr_match and not errors

    return ValidationReport(
        sample_id=payload.sample_id,
        solvent=solvent,
        structure_valid=structure_valid,
        nmr_text_valid=nmr_text_valid,
        structure_nmr_match=structure_nmr_match,
        analysis_ready=analysis_ready,
        parseable_peak_count=len(parsed_peaks),
        expected_visible_h=expected_visible_h,
        observed_total_h=observed_total_h,
        adjusted_observed_total_h=adjusted_observed_total_h,
        delta_visible_h=delta_visible_h,
        carbon13_text_valid=carbon13_text_valid,
        structure_carbon13_match=structure_carbon13_match,
        expected_carbon_count=expected_carbon_count,
        observed_carbon_signal_count=observed_carbon_signal_count,
        delta_carbon_signals=delta_carbon_signals,
        parsed_peaks=parsed_peaks,
        structure=structure,
        warnings=warnings,
        errors=errors,
    )


def analyze_inputs(payload: AnalysisInputs) -> AnalysisReport:
    return analyze_nmr_text(
        smiles=payload.smiles,
        nmr_text=payload.nmr_text,
        sample_id=payload.sample_id,
        solvent=payload.solvent,
    )


def analyze_nmr_text(
    smiles: str,
    nmr_text: str,
    sample_id: str | None = None,
    solvent: str | None = None,
) -> AnalysisReport:
    solvent = _resolved_solvent(solvent)
    try:
        structure = structure_summary_from_smiles(smiles)
        peaks = parse_nmr_text(nmr_text)
    except (StructureParseError, PeakParseError) as exc:
        return AnalysisReport(
            label="invalid_input",
            confidence=0.99,
            sample_id=sample_id,
            solvent=solvent,
            expected_total_h=0,
            expected_non_labile_h=0,
            expected_labile_h=0,
            observed_total_h=0.0,
            rounded_observed_total_h=0,
            delta_total_h=0,
            parsed_peak_count=0,
            notes=[str(exc)],
            peaks=[],
            structure=_empty_structure(smiles),
            solvent_signal_hits=[],
            pattern_alerts=[],
            proton_evidence_score=0.0,
            proton_evidence={},
        )

    observed_total_h = total_integrated_protons(peaks)
    rounded_observed_total_h = round(observed_total_h)
    delta_total_h = rounded_observed_total_h - structure.total_hydrogens
    notes: list[str] = []

    if delta_total_h == 0:
        label = "consistent"
        notes.append("Observed integrated proton count matches the total hydrogen count from the structure.")
    elif delta_total_h < 0:
        label = "possible_overlap_or_missing_labile_signals"
        notes.append("Observed integrated proton count is lower than expected from the structure.")
        if structure.labile_hydrogens > 0:
            notes.append(
                "The molecule contains labile hydrogens (for example OH/NH/SH), which may broaden, exchange, or be omitted from the reported integration."
            )
        if structure.aromatic_atom_count >= 6:
            notes.append("The structure contains an aromatic system, so peak congestion and overlap are plausible.")
    else:
        label = "possible_impurity_or_incorrect_assignment"
        notes.append("Observed integrated proton count is higher than expected from the structure.")
        notes.append("This can indicate impurities, residual solvent, or an incorrect peak list/assignment.")

    if _has_broad_peak(peaks):
        notes.append("Broad signals are present in the peak list, which can be consistent with exchangeable protons.")

    profile = get_solvent_profile(solvent)
    hits = find_solvent_peak_hits(peaks=peaks, solvent=solvent)
    if profile is not None:
        notes.extend(profile.notes)
        if hits:
            notes.append(
                "One or more parsed peaks fall close to common residual-solvent or water signals for the stated solvent."
            )
            for hit in hits:
                notes.append(
                    f"Approximate solvent match: {hit.signal_label} expected near {hit.expected_ppm:.2f} ppm; observed {hit.observed_ppm:.2f} ppm."
                )
        if delta_total_h > 0:
            notes.append(
                "Because the observed total exceeds expectation and a solvent was specified, check whether residual solvent or water peaks were included in the integration summary."
            )
        elif delta_total_h < 0 and structure.labile_hydrogens > 0:
            notes.append(
                "Because the observed total is low and labile hydrogens are present, solvent-dependent exchange may explain part of the mismatch."
            )
        if profile.canonical_name == "D2O" and structure.labile_hydrogens > 0:
            notes.append(
                "D2O is especially likely to suppress exchangeable proton signals through H/D exchange."
            )
    elif solvent:
        notes.append(f"Solvent '{solvent}' is not recognized, so solvent-specific heuristics were not applied.")

    pattern_alerts = _pattern_alerts(
        peaks=peaks,
        structure=structure,
        delta_total_h=delta_total_h,
        solvent_hits_count=len(hits),
        solvent=solvent,
    )
    confidence = _confidence_from_delta(delta_total_h, structure.labile_hydrogens)
    proton_evidence = analyze_proton_evidence(
        smiles=smiles,
        nmr_text=nmr_text,
        sample_id=sample_id,
        solvent=solvent,
    )
    notes.append(f"1H evidence score: {proton_evidence.overall_score:.2f}.")

    return AnalysisReport(
        label=label,
        confidence=confidence,
        sample_id=sample_id,
        solvent=solvent,
        expected_total_h=structure.total_hydrogens,
        expected_non_labile_h=structure.non_labile_hydrogens,
        expected_labile_h=structure.labile_hydrogens,
        observed_total_h=observed_total_h,
        rounded_observed_total_h=rounded_observed_total_h,
        delta_total_h=delta_total_h,
        parsed_peak_count=len(peaks),
        notes=notes,
        peaks=peaks,
        structure=structure,
        solvent_signal_hits=hits,
        pattern_alerts=pattern_alerts,
        proton_evidence_score=proton_evidence.overall_score,
        proton_evidence=proton_evidence.model_dump(),
    )
