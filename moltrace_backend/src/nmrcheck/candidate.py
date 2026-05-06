from __future__ import annotations

from .carbon13 import Carbon13ParseError, analyze_carbon13_text
from .chemistry import structure_summary_from_smiles
from .dept import DeptAptAnalyzeResult
from .exceptions import PeakParseError, StructureParseError
from .models import (
    CandidateComparisonItem,
    CandidateComparisonRequest,
    CandidateComparisonResult,
    CandidateInput,
    CandidateScoreBreakdown,
)
from .nmr2d_models import NMR2DAnalyzeResult
from .proton import analyze_proton_evidence


def parse_candidate_text(text: str) -> list[CandidateInput]:
    candidates: list[CandidateInput] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            parts = [part.strip() for part in line.split("|")]
        elif "," in line and line.count(",") <= 3:
            parts = [part.strip() for part in line.split(",")]
        else:
            parts = [line]
        if len(parts) == 1:
            candidates.append(CandidateInput(smiles=parts[0]))
        elif len(parts) == 2:
            candidates.append(CandidateInput(name=parts[0], smiles=parts[1]))
        else:
            candidates.append(CandidateInput(name=parts[0], smiles=parts[1], role=parts[2]))
    if not candidates:
        raise ValueError("No candidate structures were found. Enter one SMILES per line or use name | SMILES | role.")
    if len(candidates) > 25:
        raise ValueError("Candidate comparison is limited to 25 candidates per run.")
    return candidates


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _score_label(score: float, rank: int, delta_to_next: float | None, valid: bool) -> str:
    if not valid:
        return "invalid_structure"
    if rank == 1 and score >= 0.78 and (delta_to_next is None or delta_to_next >= 0.05):
        return "best_supported"
    if score >= 0.70:
        return "supported"
    if score >= 0.52:
        return "ambiguous"
    return "weak_support"


def _weighted_score(components: dict[str, float | None], weights: dict[str, float]) -> float:
    total = 0.0
    weight_sum = 0.0
    for key, weight in weights.items():
        value = components.get(key)
        if value is None:
            continue
        total += _clamp(value) * weight
        weight_sum += weight
    if weight_sum <= 0:
        return 0.0
    return _clamp(total / weight_sum)


def compare_candidates(
    request: CandidateComparisonRequest,
    *,
    dept_apt_result: DeptAptAnalyzeResult | None = None,
    nmr2d_result: NMR2DAnalyzeResult | None = None,
) -> CandidateComparisonResult:
    evidence_layers: list[str] = []
    if request.proton_nmr_text:
        evidence_layers.append("1H")
    if request.carbon13_text:
        evidence_layers.append("13C")
    if dept_apt_result is not None:
        evidence_layers.append("DEPT/APT")
    if nmr2d_result is not None:
        evidence_layers.append("2D NMR")

    notes = [
        "Candidate comparison is evidence ranking, not final structure confirmation.",
        "Scores are transparent heuristics using available 1H, 13C, DEPT/APT, and 2D evidence.",
        "Human review is required, especially for close candidates, regioisomers, and assignments with missing evidence.",
    ]
    warnings: list[str] = []
    if not request.proton_nmr_text and not request.carbon13_text:
        warnings.append("No 1H or 13C text was supplied; candidate ranking will be weak.")

    raw_items: list[CandidateComparisonItem] = []
    global_dept_score = dept_apt_result.dept_apt_consistency_score if dept_apt_result else None
    global_2d_score = nmr2d_result.evidence_score if nmr2d_result else None
    has_spectral_evidence = any(
        value is not None for value in (request.proton_nmr_text, request.carbon13_text, global_dept_score, global_2d_score)
    )

    for candidate in request.candidates:
        evidence_summary: list[str] = []
        contradictions: list[str] = []
        item_warnings: list[str] = []
        formula = None
        exact_mass = None
        valid = True

        try:
            structure = structure_summary_from_smiles(candidate.smiles)
            formula = structure.formula
            exact_mass = getattr(structure, "exact_mass", None) or getattr(structure, "molecular_weight", None)
            structure_validity_score = 1.0
            evidence_summary.append(f"Structure parsed as {formula}.")
        except StructureParseError as exc:
            valid = False
            structure_validity_score = 0.0
            item_warnings.append(str(exc))

        proton_score = None
        proton_label = None
        if valid and request.proton_nmr_text:
            try:
                proton = analyze_proton_evidence(
                    smiles=candidate.smiles,
                    nmr_text=request.proton_nmr_text,
                    solvent=request.solvent,
                    sample_id=request.sample_id,
                )
                proton_score = proton.overall_score
                proton_label = proton.label
                evidence_summary.append(f"1H evidence score: {proton_score:.2f}; label: {proton.label}.")
                if proton.delta_non_solvent_h and abs(proton.delta_non_solvent_h) >= 2:
                    contradictions.append(f"1H non-solvent integration differs by {proton.delta_non_solvent_h:g} H.")
                item_warnings.extend(proton.warnings[:3])
            except (PeakParseError, StructureParseError, ValueError) as exc:
                item_warnings.append(f"1H evidence could not be scored: {exc}")

        carbon_score = None
        carbon_label = None
        if valid and request.carbon13_text:
            try:
                carbon = analyze_carbon13_text(
                    candidate.smiles,
                    request.carbon13_text,
                    solvent=request.solvent,
                    sample_id=request.sample_id,
                )
                carbon_score = carbon.carbon13_match_score if carbon.carbon13_match_score is not None else carbon.confidence
                carbon_label = carbon.label
                evidence_summary.append(f"13C evidence score: {carbon_score:.2f}; label: {carbon.label}.")
                if abs(carbon.delta_carbon_signals) >= 3:
                    contradictions.append(f"13C observed signal count differs by {carbon.delta_carbon_signals:+d}.")
                item_warnings.extend(carbon.solvent_warnings[:2])
            except (Carbon13ParseError, StructureParseError, ValueError) as exc:
                item_warnings.append(f"13C evidence could not be scored: {exc}")

        if global_dept_score is not None:
            evidence_summary.append(f"DEPT/APT consistency score: {global_dept_score:.2f}.")
        if global_2d_score is not None:
            evidence_summary.append(f"2D NMR evidence score: {global_2d_score:.2f}.")

        components = {
            "structure": structure_validity_score,
            "proton": proton_score,
            "carbon13": carbon_score,
            "dept_apt": global_dept_score,
            "nmr2d": global_2d_score,
        }
        weights = {
            "structure": 0.08,
            "proton": 0.36,
            "carbon13": 0.34,
            "dept_apt": 0.08,
            "nmr2d": 0.14,
        }
        total_score = _weighted_score(components, weights) if valid else 0.0
        if valid and not has_spectral_evidence:
            total_score = min(total_score, 0.35)
            evidence_summary.append("No spectral evidence was available; valid structure parsing is not strong support.")

        raw_items.append(
            CandidateComparisonItem(
                rank=0,
                name=candidate.name,
                role=candidate.role,
                smiles=candidate.smiles,
                label="supported" if valid else "invalid_structure",
                total_score=round(total_score, 3),
                score_breakdown=CandidateScoreBreakdown(
                    structure_validity_score=structure_validity_score,
                    proton_score=proton_score,
                    carbon13_score=carbon_score,
                    dept_apt_score=global_dept_score,
                    nmr2d_score=global_2d_score,
                ),
                formula=formula,
                exact_mass=exact_mass,
                proton_label=proton_label,
                carbon13_label=carbon_label,
                evidence_summary=evidence_summary,
                contradictions=contradictions,
                warnings=item_warnings,
                metadata={"valid_structure": valid},
            )
        )

    sorted_items = sorted(raw_items, key=lambda item: item.total_score, reverse=True)
    ranked: list[CandidateComparisonItem] = []
    for idx, item in enumerate(sorted_items):
        next_score = sorted_items[idx + 1].total_score if idx + 1 < len(sorted_items) else None
        delta_to_next = None if next_score is None else item.total_score - next_score
        label = _score_label(item.total_score, idx + 1, delta_to_next, item.label != "invalid_structure")
        ranked.append(item.model_copy(update={"rank": idx + 1, "label": label}))

    ambiguity_alerts: list[str] = []
    if len(ranked) >= 2:
        delta = ranked[0].total_score - ranked[1].total_score
        if delta < 0.05:
            ambiguity_alerts.append(
                f"Top two candidates are close (delta score {delta:.3f}); reviewer should inspect peak-level evidence and possible regioisomers."
            )
    if any(item.contradictions for item in ranked[:3]):
        ambiguity_alerts.append("One or more top candidates has contradictions that require human review.")

    return CandidateComparisonResult(
        sample_id=request.sample_id,
        solvent=request.solvent,
        candidate_count=len(ranked),
        best_candidate=ranked[0] if ranked else None,
        ranked_candidates=ranked,
        ambiguity_alerts=ambiguity_alerts,
        evidence_layers_used=evidence_layers,
        notes=notes,
        warnings=warnings,
    )
