from __future__ import annotations

import csv
import io
import math
from typing import Any

from .chemistry import structure_summary_from_smiles
from .exceptions import StructureParseError
from .hrms import HRMSError, formula_from_smiles, normalize_adduct, ppm_error, theoretical_mz
from .lcms_consensus import LCMSFeatureFamilyConsensusError, score_lcms_feature_family_consensus
from .models import (
    CandidateInput,
    LCMSCandidateFeatureFamilyMatch,
    LCMSConsensusCandidateBridgeRequest,
    LCMSConsensusCandidateBridgeResult,
    LCMSFeatureFamilyConsensus,
    LCMSFeatureFamilyConsensusRequest,
    LCMSFeatureFamilyConsensusResult,
)


class LCMSConfidenceBridgeError(ValueError):
    """Raised when LC-MS consensus cannot be bridged into candidate confidence."""


def _clamp(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _candidate_key(smiles: str) -> str:
    return " ".join(str(smiles or "").strip().split())


def _effective_tolerance(expected_mz: float, mz_tolerance_da: float, ppm_tolerance: float) -> float:
    return max(float(mz_tolerance_da), abs(float(expected_mz)) * float(ppm_tolerance) / 1_000_000.0)


def _gaussian_score(error_da: float, tolerance_da: float) -> float:
    if tolerance_da <= 0:
        return 0.0
    return _clamp(math.exp(-0.5 * (float(error_da) / float(tolerance_da)) ** 2))


def _candidate_formula_and_mass(candidate: CandidateInput) -> tuple[str | None, float | None, list[str]]:
    warnings: list[str] = []
    try:
        info = formula_from_smiles(candidate.smiles)
        return info.formula, info.exact_mass, warnings
    except Exception as exc:
        warnings.append(f"Candidate structure could not be parsed for LC-MS mass matching: {exc}")
        try:
            summary = structure_summary_from_smiles(candidate.smiles)
            return summary.formula, summary.molecular_weight, warnings
        except Exception:
            return None, None, warnings


def _family_table_to_consensus_result(text: str, *, sample_id: str | None = None) -> LCMSFeatureFamilyConsensusResult:
    """Parse the Week 38 exportable family table into minimal family objects.

    The table-only path intentionally carries less evidence than a full Week 38
    result. It is still useful for audit reruns and report bridges because the
    anchor m/z, RT, label, consensus score, and promotion flag are preserved.
    """
    if not text or not text.strip():
        raise LCMSConfidenceBridgeError("LC-MS family table text is empty.")
    reader = csv.DictReader(io.StringIO(text.strip()))
    required = {"family_id", "anchor_group_id", "anchor_mz", "anchor_rt_min", "label", "consensus_score", "promoted"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise LCMSConfidenceBridgeError("LC-MS family table must use the Week 38 family_table_text columns.")

    families: list[LCMSFeatureFamilyConsensus] = []
    for row in reader:
        try:
            promoted = str(row.get("promoted") or "").strip().lower() in {"true", "1", "yes", "y"}
            score = float(row.get("consensus_score") or 0.0)
            family = LCMSFeatureFamilyConsensus(
                family_id=str(row["family_id"]).strip(),
                anchor_group_id=str(row["anchor_group_id"]).strip(),
                anchor_mz=float(row["anchor_mz"]),
                anchor_rt_min=float(row["anchor_rt_min"]),
                label=str(row["label"]).strip(),  # type: ignore[arg-type]
                promoted_for_candidate_scoring=promoted,
                consensus_score=score,
                evidence_layer_count=0,
                contradiction_count=1 if str(row.get("label") or "") == "conflicting_or_background_family" else 0,
                relationship_count=int(float(row.get("relationship_count") or 0)),
                member_count=int(float(row.get("member_count") or 0)),
                evidence_summary=[
                    "Imported from Week 38 LC-MS family_table_text; detailed layer/member evidence was not supplied.",
                    f"Family {str(row['family_id']).strip()} anchored at m/z {float(row['anchor_mz']):.6f}, RT {float(row['anchor_rt_min']):.3f} min.",
                ],
                warnings=["Table-only LC-MS bridge has reduced provenance; pass the full LCMSFeatureFamilyConsensusResult when possible."],
            )
            families.append(family)
        except (KeyError, TypeError, ValueError) as exc:
            raise LCMSConfidenceBridgeError("Could not parse one or more rows in the LC-MS family table.") from exc

    families.sort(key=lambda f: (not f.promoted_for_candidate_scoring, -f.consensus_score, f.anchor_rt_min, f.anchor_mz))
    promoted_count = sum(1 for f in families if f.promoted_for_candidate_scoring)
    conflicting_count = sum(1 for f in families if f.label == "conflicting_or_background_family")
    label = "ready_for_candidate_scoring" if promoted_count else "review_conflicting_families" if conflicting_count else "insufficient_consensus"
    return LCMSFeatureFamilyConsensusResult(
        sample_id=sample_id,
        label=label,  # type: ignore[arg-type]
        input_group_count=0,
        family_count=len(families),
        promoted_family_count=promoted_count,
        conflicting_family_count=conflicting_count,
        relationship_count=sum(f.relationship_count for f in families),
        families=families,
        best_family=families[0] if families else None,
        family_table_text=text.strip(),
        recommended_next_actions=["Use table-only LC-MS consensus as supporting evidence; preserve the original Week 38 result when available."],
        warnings=["LC-MS consensus was reconstructed from a table and lacks full layer provenance."],
        notes=["Week 39 table parser does not infer new feature relationships; it only bridges already-scored Week 38 families."],
        metadata={"parser_version": "week39_lcms_family_table_bridge_v1", "source": "family_table_text"},
    )


def resolve_lcms_consensus_result(req: LCMSConsensusCandidateBridgeRequest) -> LCMSFeatureFamilyConsensusResult:
    if req.lcms_consensus_result is not None:
        return req.lcms_consensus_result
    if req.lcms_consensus_request is not None:
        try:
            return score_lcms_feature_family_consensus(req.lcms_consensus_request)
        except LCMSFeatureFamilyConsensusError as exc:
            raise LCMSConfidenceBridgeError(f"Could not score LC-MS consensus request: {exc}") from exc
    if req.lcms_family_table_text:
        return _family_table_to_consensus_result(req.lcms_family_table_text, sample_id=req.sample_id)
    raise LCMSConfidenceBridgeError("Provide lcms_consensus_result, lcms_consensus_request, or lcms_family_table_text.")


def _eligible_families(result: LCMSFeatureFamilyConsensusResult, req: LCMSConsensusCandidateBridgeRequest) -> list[LCMSFeatureFamilyConsensus]:
    families = list(result.families or [])
    if req.selected_family_id:
        families = [family for family in families if family.family_id == req.selected_family_id]
    if req.require_promoted_family:
        families = [family for family in families if family.promoted_for_candidate_scoring]
    families = [family for family in families if family.consensus_score >= req.min_family_consensus_score and family.label != "conflicting_or_background_family"]
    families.sort(key=lambda f: (not f.promoted_for_candidate_scoring, -f.consensus_score, f.anchor_rt_min, f.anchor_mz))
    return families


def _match_candidate_to_families(
    candidate: CandidateInput,
    *,
    adduct_name: str,
    families: list[LCMSFeatureFamilyConsensus],
    all_family_count: int,
    req: LCMSConsensusCandidateBridgeRequest,
) -> LCMSCandidateFeatureFamilyMatch:
    formula, exact_mass, warnings = _candidate_formula_and_mass(candidate)
    if formula is None or exact_mass is None:
        return LCMSCandidateFeatureFamilyMatch(
            rank=0,
            name=candidate.name,
            role=candidate.role,
            smiles=candidate.smiles,
            formula=formula,
            exact_mass=exact_mass,
            adduct=adduct_name,
            score=0.0,
            label="candidate_invalid",
            contradiction=True,
            warnings=warnings,
            evidence_summary=["Candidate could not be converted into a formula/exact mass for LC-MS consensus matching."],
            metadata={"candidate_key": _candidate_key(candidate.smiles)},
        )

    adduct = normalize_adduct(adduct_name)
    expected_mz = theoretical_mz(exact_mass, adduct)
    if not families:
        message = "No eligible LC-MS consensus family was available for candidate scoring."
        if all_family_count:
            message += " Existing families were unpromoted, below the consensus threshold, conflicting, or filtered by selected_family_id."
        return LCMSCandidateFeatureFamilyMatch(
            rank=0,
            name=candidate.name,
            role=candidate.role,
            smiles=candidate.smiles,
            formula=formula,
            exact_mass=round(exact_mass, 6),
            adduct=adduct.name,
            expected_mz=round(expected_mz, 6),
            score=0.18 if all_family_count else 0.0,
            label="no_eligible_consensus_family",
            contradiction=False,
            warnings=[message],
            evidence_summary=[message, f"Candidate theoretical {adduct.name} m/z is {expected_mz:.6f}."],
            metadata={"candidate_key": _candidate_key(candidate.smiles)},
        )

    scored: list[tuple[float, float, float, LCMSFeatureFamilyConsensus]] = []
    for family in families:
        error_da = abs(float(family.anchor_mz) - expected_mz)
        tol_da = _effective_tolerance(expected_mz, req.mz_tolerance_da, req.ppm_tolerance)
        mass_score = _gaussian_score(error_da, tol_da)
        family_gate_score = 0.45 + 0.55 * _clamp(family.consensus_score)
        if not family.promoted_for_candidate_scoring:
            family_gate_score *= 0.78
        score = _clamp(mass_score * family_gate_score)
        scored.append((score, error_da, tol_da, family))

    score, error_da, tol_da, family = sorted(scored, key=lambda item: (-item[0], item[1], -item[3].consensus_score))[0]
    mz_ppm_error = ppm_error(family.anchor_mz, expected_mz)
    within_tolerance = error_da <= tol_da
    if within_tolerance:
        label = "matches_promoted_feature_family" if family.promoted_for_candidate_scoring else "matches_review_feature_family"
        contradiction = False
    else:
        label = "no_mass_match_to_consensus_family"
        contradiction = bool(family.promoted_for_candidate_scoring and req.require_promoted_family)
        score = min(score, 0.22)

    summary = [
        f"Candidate theoretical {adduct.name} m/z is {expected_mz:.6f}; best LC-MS family anchor {family.family_id} is {family.anchor_mz:.6f}.",
        f"LC-MS family consensus score {family.consensus_score:.3f}; mass error {error_da:.5f} Da ({mz_ppm_error:.2f} ppm); tolerance {tol_da:.5f} Da.",
    ]
    if within_tolerance:
        summary.append("Candidate mass/adduct is consistent with the LC-MS feature-family anchor.")
    else:
        summary.append("Candidate mass/adduct does not match the eligible LC-MS feature-family anchor within tolerance.")

    item_warnings = list(warnings)
    if family.warnings:
        item_warnings.extend([f"Family {family.family_id}: {warning}" for warning in family.warnings[:4]])
    if contradiction:
        item_warnings.append("LC-MS feature-family mass disagreement should be reviewed before ranking this candidate highly.")

    return LCMSCandidateFeatureFamilyMatch(
        rank=0,
        name=candidate.name,
        role=candidate.role,
        smiles=candidate.smiles,
        formula=formula,
        exact_mass=round(exact_mass, 6),
        adduct=adduct.name,
        expected_mz=round(expected_mz, 6),
        best_family_id=family.family_id,
        best_family_label=family.label,
        best_family_anchor_mz=round(family.anchor_mz, 6),
        best_family_anchor_rt_min=round(family.anchor_rt_min, 6),
        family_consensus_score=round(family.consensus_score, 4),
        mz_error_da=round(error_da, 6),
        mz_error_ppm=round(mz_ppm_error, 4),
        score=round(score, 4),
        label=label,  # type: ignore[arg-type]
        promoted_family=family.promoted_for_candidate_scoring,
        contradiction=contradiction,
        evidence_summary=summary,
        warnings=list(dict.fromkeys(item_warnings))[:8],
        metadata={
            "candidate_key": _candidate_key(candidate.smiles),
            "tolerance_da": round(tol_da, 6),
            "family_relationship_count": family.relationship_count,
            "family_member_count": family.member_count,
        },
    )


def _evidence_table(matches: list[LCMSCandidateFeatureFamilyMatch]) -> str:
    lines = ["rank,name,smiles,formula,adduct,expected_mz,best_family_id,best_family_anchor_mz,mz_error_da,mz_error_ppm,score,label,contradiction"]
    for match in matches:
        lines.append(
            f"{match.rank},{match.name or ''},{match.smiles},{match.formula or ''},{match.adduct},{match.expected_mz or ''},{match.best_family_id or ''},{match.best_family_anchor_mz or ''},{match.mz_error_da or ''},{match.mz_error_ppm or ''},{match.score:.4f},{match.label},{str(match.contradiction).lower()}"
        )
    return "\n".join(lines)


def score_lcms_candidates_against_consensus(req: LCMSConsensusCandidateBridgeRequest) -> LCMSConsensusCandidateBridgeResult:
    """Score candidate structures against promoted LC-MS feature-family evidence.

    This bridge is intentionally conservative. It asks whether a candidate's
    theoretical adduct m/z can be mapped to a Week 38 feature-family anchor that
    already passed blank/background, isotope/adduct, RT, and MS/MS-linkage checks.
    It does not perform database search or claim that a matching family proves
    identity.
    """
    if not req.candidates:
        raise LCMSConfidenceBridgeError("At least one candidate is required.")
    try:
        consensus = resolve_lcms_consensus_result(req)
        adduct = normalize_adduct(req.adduct)
    except (HRMSError, LCMSFeatureFamilyConsensusError, ValueError) as exc:
        raise LCMSConfidenceBridgeError(str(exc)) from exc

    eligible = _eligible_families(consensus, req)
    matches = [
        _match_candidate_to_families(
            candidate,
            adduct_name=adduct.name,
            families=eligible,
            all_family_count=len(consensus.families),
            req=req,
        )
        for candidate in req.candidates
    ]
    matches_sorted = sorted(matches, key=lambda item: (item.contradiction, -item.score, item.name or item.smiles))
    ranked = [match.model_copy(update={"rank": idx + 1}) for idx, match in enumerate(matches_sorted)]
    warnings: list[str] = []
    if consensus.warnings:
        warnings.extend(consensus.warnings)
    if not eligible:
        warnings.append("No eligible promoted/non-conflicting LC-MS family was available for strong candidate scoring.")
    if any(match.contradiction for match in ranked):
        warnings.append("At least one candidate conflicts with the promoted LC-MS feature-family m/z/adduct evidence.")

    notes = [
        "Week 39 bridges Week 38 LC-MS feature-family consensus into candidate confidence as one transparent evidence layer.",
        "A mass/adduct match to a promoted LC-MS family is supportive evidence, not a standalone molecular identification.",
        "Reviewer approval should preserve the LC-MS consensus settings, family table/result hash, and candidate adduct assumption.",
    ]
    return LCMSConsensusCandidateBridgeResult(
        sample_id=req.sample_id or consensus.sample_id,
        adduct=adduct.name,
        candidate_count=len(ranked),
        family_count=len(consensus.families),
        eligible_family_count=len(eligible),
        promoted_family_count=sum(1 for family in consensus.families if family.promoted_for_candidate_scoring),
        best_match=ranked[0] if ranked else None,
        matches=ranked,
        evidence_table_text=_evidence_table(ranked),
        warnings=list(dict.fromkeys(warnings)),
        notes=notes,
        metadata={
            "parser_version": "week39_lcms_consensus_candidate_bridge_v1",
            "consensus_label": consensus.label,
            "consensus_family_count": consensus.family_count,
            "consensus_promoted_family_count": consensus.promoted_family_count,
            "consensus_selected_family_id": req.selected_family_id,
            "require_promoted_family": req.require_promoted_family,
            "min_family_consensus_score": req.min_family_consensus_score,
            "mz_tolerance_da": req.mz_tolerance_da,
            "ppm_tolerance": req.ppm_tolerance,
        },
    )
