from __future__ import annotations

import hashlib
import json
from typing import Any

from .adduct_inference import AdductInferenceError, infer_adducts_and_isotopes
from .candidate_predicted import match_candidates_with_predicted_nmr
from .chemistry import structure_summary_from_smiles
from .fragmentation_tree import MSMSFragmentationTreeError, build_msms_fragmentation_tree
from .hrms import HRMSError, formula_from_smiles, match_hrms_candidates
from .lcms_confidence_bridge import LCMSConfidenceBridgeError, score_lcms_candidates_against_consensus
from .models import (
    CandidateInput,
    CandidatePredictedNMRMatchRequest,
    EvidenceBundleItem,
    HRMSCandidateMatchRequest,
    LCMSConsensusCandidateBridgeRequest,
    LCMSFeatureFamilyConsensusRequest,
    LCMSFeatureFamilyConsensusResult,
    MS1AdductInferenceRequest,
    MSMSAnnotationRequest,
    MSMSFragmentationTreeRequest,
    NMR2DPreviewReport,
    UnifiedCandidateConfidenceItem,
    UnifiedCandidateConfidenceRequest,
    UnifiedCandidateConfidenceResult,
    UnifiedEvidenceBundleConfidenceResult,
    UnifiedEvidenceBundleRequest,
    UnifiedEvidenceLayerScore,
)
from .msms import MSMSError, annotate_msms
from .nmr2d import NMR2DParseError, parse_nmr2d_table


class UnifiedConfidenceError(ValueError):
    pass


DEFAULT_LAYER_WEIGHTS = {
    "predicted_nmr": 0.36,
    "hrms_exact_mass": 0.20,
    "adduct_isotope": 0.10,
    "msms_annotation": 0.16,
    "fragmentation_tree": 0.18,
}

LAYER_LABELS = {
    "predicted_nmr": "Candidate-specific predicted NMR",
    "hrms_exact_mass": "HRMS exact mass",
    "adduct_isotope": "Adduct/isotope inference",
    "msms_annotation": "Processed MS/MS annotation",
    "fragmentation_tree": "MS/MS fragmentation tree",
    "lcms_feature_family": "LC-MS feature-family consensus",
}

BUNDLE_LAYER_ALIASES = {
    "predicted_nmr": "predicted_nmr",
    "predicted-nmr": "predicted_nmr",
    "candidate_predicted_nmr": "predicted_nmr",
    "nmr_prediction": "predicted_nmr",
    "hrms": "hrms_exact_mass",
    "hrms_exact_mass": "hrms_exact_mass",
    "exact_mass": "hrms_exact_mass",
    "adduct": "adduct_isotope",
    "adduct_isotope": "adduct_isotope",
    "adducts": "adduct_isotope",
    "ms1_adduct": "adduct_isotope",
    "msms": "msms_annotation",
    "msms_annotation": "msms_annotation",
    "ms_ms_annotation": "msms_annotation",
    "fragmentation": "fragmentation_tree",
    "fragmentation_tree": "fragmentation_tree",
    "msms_fragmentation_tree": "fragmentation_tree",
    "lcms_feature_family": "lcms_feature_family",
    "lcms_feature_family_consensus": "lcms_feature_family",
    "lcms_consensus": "lcms_feature_family",
    "lcms_dereplication": "lcms_feature_family",
    "dereplication": "lcms_feature_family",
    "lcms_confidence_bridge": "lcms_feature_family",
    "lcms_consensus_bridge": "lcms_feature_family",
}

BUNDLE_EXPECTED_LAYERS = [
    "predicted_nmr",
    "hrms_exact_mass",
    "adduct_isotope",
    "msms_annotation",
    "fragmentation_tree",
    "lcms_feature_family_consensus",
    "lcms_dereplication",
    "lcms_confidence_bridge",
]

BUNDLE_LAYER_LABELS = {
    **LAYER_LABELS,
    "lcms_feature_family_consensus": "LC-MS feature-family consensus",
    "lcms_dereplication": "LC-MS library dereplication",
    "lcms_confidence_bridge": "LC-MS confidence bridge",
}


def _candidate_key(smiles: str) -> str:
    return " ".join(str(smiles or "").strip().split())


def _clamp(value: float | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _round_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(_clamp(value), 4)


def _status_from_score(score: float | None, *, contradiction: bool = False, missing: bool = False) -> str:
    if missing:
        return "missing"
    if contradiction:
        return "contradiction"
    if score is None:
        return "missing"
    if score >= 0.78:
        return "strong_agreement"
    if score >= 0.58:
        return "partial_agreement"
    if score >= 0.35:
        return "weak_or_ambiguous"
    return "poor_agreement"


def _layer(
    layer: str,
    *,
    used: bool,
    score: float | None,
    weight: float,
    evidence_summary: list[str] | None = None,
    warnings: list[str] | None = None,
    contradiction: bool = False,
    metadata: dict[str, Any] | None = None,
) -> UnifiedEvidenceLayerScore:
    return UnifiedEvidenceLayerScore(
        layer=layer,
        label=LAYER_LABELS.get(layer, layer),
        used=used,
        score=_round_score(score),
        weight=round(float(weight), 4),
        status=_status_from_score(score, contradiction=contradiction, missing=not used),
        agreement=bool(used and score is not None and score >= 0.58 and not contradiction),
        contradiction=bool(contradiction),
        evidence_count=len(evidence_summary or []),
        evidence_summary=evidence_summary or [],
        warnings=warnings or [],
        metadata=metadata or {},
    )


def _weighted_score(
    layers: list[UnifiedEvidenceLayerScore], *, denominator_weight: float | None = None
) -> tuple[float, float]:
    total = 0.0
    weight_sum = 0.0
    for layer in layers:
        if not layer.used or layer.score is None:
            continue
        total += layer.score * layer.weight
        weight_sum += layer.weight
    if weight_sum <= 0:
        return 0.0, 0.0
    denominator = (
        float(denominator_weight) if denominator_weight is not None else sum(DEFAULT_LAYER_WEIGHTS.values())
    )
    return _clamp(total / weight_sum), min(1.0, weight_sum / max(0.0001, denominator))


def _label(confidence: float, used_count: int, contradiction_count: int, invalid: bool) -> str:
    if invalid:
        return "invalid_structure"
    if contradiction_count >= 2 and confidence < 0.78:
        return "conflicting_evidence"
    if confidence >= 0.82 and used_count >= 3 and contradiction_count == 0:
        return "high_confidence_candidate"
    if confidence >= 0.64 and used_count >= 2:
        return "moderate_confidence_candidate"
    if confidence >= 0.42:
        return "low_confidence_candidate"
    return "insufficient_evidence"


def _band(label: str) -> str:
    if label == "high_confidence_candidate":
        return "high"
    if label == "moderate_confidence_candidate":
        return "medium"
    if label == "conflicting_evidence":
        return "conflicting"
    if label in {"low_confidence_candidate", "invalid_structure"}:
        return "low"
    return "insufficient"


def _parse_optional_2d(req: UnifiedCandidateConfidenceRequest) -> NMR2DPreviewReport | None:
    if not req.observed_nmr2d_text:
        return None
    try:
        return parse_nmr2d_table(
            "unified_observed_2d.csv",
            req.observed_nmr2d_text.encode("utf-8"),
            experiment_type=req.observed_nmr2d_experiment_type,
        )
    except NMR2DParseError as exc:
        raise UnifiedConfidenceError(f"Observed 2D NMR evidence could not be parsed: {exc}") from exc


def _candidate_formula(candidate: CandidateInput, hrms_item: Any | None = None) -> str | None:
    if hrms_item is not None and getattr(hrms_item, "formula", None):
        return hrms_item.formula
    try:
        return formula_from_smiles(candidate.smiles).formula
    except Exception:
        try:
            return structure_summary_from_smiles(candidate.smiles).formula
        except Exception:
            return None


def _has_lcms_bridge_input(req: UnifiedCandidateConfidenceRequest) -> bool:
    return bool(req.lcms_consensus_result or req.lcms_consensus_request or req.lcms_family_table_text)


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _bridge_lcms_request(
    req: UnifiedCandidateConfidenceRequest,
    *,
    selected_adduct: str,
) -> LCMSConsensusCandidateBridgeRequest | None:
    if not _has_lcms_bridge_input(req):
        return None
    consensus_result = None
    consensus_request = None
    if req.lcms_consensus_result is not None:
        consensus_result = LCMSFeatureFamilyConsensusResult.model_validate(req.lcms_consensus_result)
    if req.lcms_consensus_request is not None:
        consensus_request = LCMSFeatureFamilyConsensusRequest.model_validate(req.lcms_consensus_request)
    return LCMSConsensusCandidateBridgeRequest(
        sample_id=req.sample_id,
        candidates=req.candidates,
        lcms_consensus_result=consensus_result,
        lcms_consensus_request=consensus_request,
        lcms_family_table_text=req.lcms_family_table_text,
        adduct=req.lcms_anchor_adduct or req.hrms_adduct or req.msms_adduct or selected_adduct or "[M+H]+",
        mz_tolerance_da=req.lcms_mz_tolerance_da,
        ppm_tolerance=req.lcms_ppm_tolerance,
        min_family_consensus_score=req.lcms_min_family_consensus_score,
        require_promoted_family=req.lcms_require_promoted_family,
        selected_family_id=req.lcms_selected_family_id,
    )


def build_unified_candidate_confidence(req: UnifiedCandidateConfidenceRequest) -> UnifiedCandidateConfidenceResult:
    """Combine available SpectraCheck evidence streams into one candidate ranking."""
    if not req.candidates:
        raise UnifiedConfidenceError("At least one candidate structure is required.")

    weights = dict(DEFAULT_LAYER_WEIGHTS)
    if _has_lcms_bridge_input(req):
        weights["lcms_feature_family"] = (
            float(req.layer_weights.get("lcms_feature_family", req.lcms_layer_weight))
            if req.layer_weights
            else float(req.lcms_layer_weight)
        )
    if req.layer_weights:
        for key, value in req.layer_weights.items():
            if key in weights and value is not None and value >= 0:
                weights[key] = float(value)

    warnings: list[str] = []
    notes = [
        "Unified confidence combines NMR, HRMS, MS1 adduct/isotope, MS/MS annotation, fragmentation-tree evidence, and optional LC-MS feature-family consensus.",
        "Scores are transparent decision-support confidence scores, not absolute proof or calibrated DP4/DP5 probabilities.",
        "Human review is required, especially when top candidates are close or evidence streams disagree.",
    ]
    component_metadata: dict[str, Any] = {"layer_weights": weights}
    if req.compound_class:
        component_metadata["compound_class"] = req.compound_class

    observed_2d = _parse_optional_2d(req)

    adduct_result = None
    selected_adduct = req.hrms_adduct or req.msms_adduct or "[M+H]+"
    if req.ms1_peak_list_text or req.ms1_peaks:
        try:
            adduct_result = infer_adducts_and_isotopes(
                MS1AdductInferenceRequest(
                    sample_id=req.sample_id,
                    peak_list_text=req.ms1_peak_list_text,
                    peaks=req.ms1_peaks,
                    ion_mode=req.ion_mode or "positive",
                    target_mz=req.hrms_observed_mz or req.msms_precursor_mz,
                    mz_tolerance_da=req.mz_tolerance_da,
                    ppm_tolerance=req.adduct_ppm_tolerance,
                    isotope_mz_tolerance_da=req.isotope_mz_tolerance_da,
                    min_relative_intensity=req.ms1_min_relative_intensity,
                    max_peaks_to_analyze=req.ms1_max_peaks_to_analyze,
                    max_charge=req.max_charge,
                    perform_formula_search=req.perform_adduct_formula_search,
                    formula_candidates_per_adduct=req.formula_candidates_per_adduct,
                    max_c=req.formula_max_c,
                    max_h=req.formula_max_h,
                    max_n=req.formula_max_n,
                    max_o=req.formula_max_o,
                    max_s=req.formula_max_s,
                    max_p=req.formula_max_p,
                    max_cl=req.formula_max_cl,
                    max_br=req.formula_max_br,
                )
            )
            component_metadata["adduct_inference"] = {
                "best_adduct": adduct_result.best_adduct_candidate.adduct.name if adduct_result.best_adduct_candidate else None,
                "primary_mz": adduct_result.primary_mz,
                "inferred_charge": adduct_result.inferred_charge,
            }
            if req.use_inferred_adduct and adduct_result.best_adduct_candidate is not None:
                selected_adduct = adduct_result.best_adduct_candidate.adduct.name
        except (AdductInferenceError, HRMSError, ValueError) as exc:
            warnings.append(f"Adduct/isotope inference was skipped: {exc}")

    predicted_nmr_result = None
    if req.observed_proton_text or req.observed_carbon13_text or observed_2d is not None:
        predicted_nmr_result = match_candidates_with_predicted_nmr(
            CandidatePredictedNMRMatchRequest(
                sample_id=req.sample_id,
                solvent=req.solvent,
                observed_proton_text=req.observed_proton_text,
                observed_carbon13_text=req.observed_carbon13_text,
                candidates=req.candidates,
            ),
            observed_nmr2d=observed_2d,
        )
        component_metadata["predicted_nmr"] = {
            "best_candidate": predicted_nmr_result.best_candidate.smiles if predicted_nmr_result.best_candidate else None,
            "evidence_layers_used": predicted_nmr_result.evidence_layers_used,
        }

    hrms_result = None
    if req.hrms_observed_mz is not None:
        try:
            hrms_result = match_hrms_candidates(
                HRMSCandidateMatchRequest(
                    sample_id=req.sample_id,
                    observed_mz=req.hrms_observed_mz,
                    adduct=selected_adduct,
                    ion_mode=req.ion_mode,
                    ppm_tolerance=req.hrms_ppm_tolerance,
                    observed_m_plus_1_percent=req.observed_m_plus_1_percent,
                    observed_m_plus_2_percent=req.observed_m_plus_2_percent,
                    candidates=req.candidates,
                )
            )
            component_metadata["hrms"] = {
                "observed_mz": hrms_result.observed_mz,
                "adduct": hrms_result.adduct.name,
                "exact_match_count": hrms_result.exact_match_count,
            }
        except HRMSError as exc:
            warnings.append(f"HRMS exact-mass matching was skipped: {exc}")

    precursor_mz = req.msms_precursor_mz or req.hrms_observed_mz or (adduct_result.primary_mz if adduct_result else None)
    msms_result = None
    frag_tree_result = None
    if req.msms_peak_list_text and precursor_mz:
        try:
            msms_result = annotate_msms(
                MSMSAnnotationRequest(
                    sample_id=req.sample_id,
                    precursor_mz=precursor_mz,
                    adduct=req.msms_adduct or selected_adduct,
                    ion_mode=req.ion_mode,
                    mz_tolerance_da=req.mz_tolerance_da,
                    ppm_tolerance=req.msms_ppm_tolerance,
                    min_relative_intensity=req.msms_min_relative_intensity,
                    max_peaks_to_annotate=req.msms_max_peaks_to_analyze,
                    peak_list_text=req.msms_peak_list_text,
                    candidates=req.candidates,
                )
            )
            component_metadata["msms_annotation"] = {
                "precursor_mz": msms_result.precursor_mz,
                "adduct": msms_result.adduct.name,
                "best_candidate": msms_result.best_candidate.smiles if msms_result.best_candidate else None,
            }
        except (MSMSError, HRMSError, ValueError) as exc:
            warnings.append(f"Processed MS/MS annotation was skipped: {exc}")
        try:
            frag_tree_result = build_msms_fragmentation_tree(
                MSMSFragmentationTreeRequest(
                    sample_id=req.sample_id,
                    precursor_mz=precursor_mz,
                    adduct=req.msms_adduct or selected_adduct,
                    ion_mode=req.ion_mode,
                    mz_tolerance_da=req.mz_tolerance_da,
                    ppm_tolerance=req.msms_ppm_tolerance,
                    min_relative_intensity=req.msms_min_relative_intensity,
                    max_peaks_to_analyze=req.msms_max_peaks_to_analyze,
                    max_tree_depth=req.max_tree_depth,
                    peak_list_text=req.msms_peak_list_text,
                    candidates=req.candidates,
                )
            )
            component_metadata["fragmentation_tree"] = {
                "precursor_mz": frag_tree_result.precursor_mz,
                "adduct": frag_tree_result.adduct.name,
                "best_candidate": frag_tree_result.best_candidate.smiles if frag_tree_result.best_candidate else None,
            }
        except (MSMSFragmentationTreeError, MSMSError, HRMSError, ValueError) as exc:
            warnings.append(f"Fragmentation-tree reasoning was skipped: {exc}")
    elif req.msms_peak_list_text and not precursor_mz:
        warnings.append("MS/MS peak list was supplied without precursor m/z; MS/MS layers were skipped.")

    lcms_bridge_result = None
    lcms_bridge_request = _bridge_lcms_request(req, selected_adduct=selected_adduct)
    if lcms_bridge_request is not None:
        try:
            lcms_bridge_result = score_lcms_candidates_against_consensus(lcms_bridge_request)
            component_metadata["lcms_feature_family_bridge"] = {
                "adduct": lcms_bridge_result.adduct,
                "candidate_count": lcms_bridge_result.candidate_count,
                "family_count": lcms_bridge_result.family_count,
                "eligible_family_count": lcms_bridge_result.eligible_family_count,
                "promoted_family_count": lcms_bridge_result.promoted_family_count,
                "best_match": lcms_bridge_result.best_match.smiles if lcms_bridge_result.best_match else None,
                "best_match_score": lcms_bridge_result.best_match.score if lcms_bridge_result.best_match else None,
                "bridge_result_sha256": _canonical_hash(lcms_bridge_result.model_dump(mode="json")),
            }
            warnings.extend(lcms_bridge_result.warnings)
        except (LCMSConfidenceBridgeError, HRMSError, ValueError) as exc:
            warnings.append(f"LC-MS feature-family consensus bridge was skipped: {exc}")

    nmr_by_key = {_candidate_key(i.smiles): i for i in (predicted_nmr_result.ranked_candidates if predicted_nmr_result else [])}
    hrms_by_key = {_candidate_key(i.smiles): i for i in (hrms_result.ranked_candidates if hrms_result else [])}
    msms_by_key = {_candidate_key(i.smiles): i for i in (msms_result.ranked_candidates if msms_result else [])}
    tree_by_key = {_candidate_key(i.smiles): i for i in (frag_tree_result.ranked_candidates if frag_tree_result else [])}
    lcms_by_key = {_candidate_key(i.smiles): i for i in (lcms_bridge_result.matches if lcms_bridge_result else [])}

    best_adduct = adduct_result.best_adduct_candidate if adduct_result and adduct_result.best_adduct_candidate else None
    best_adduct_top_formulas = {f.formula for f in (best_adduct.top_formulas if best_adduct else [])}

    raw_items: list[UnifiedCandidateConfidenceItem] = []
    for candidate in req.candidates:
        key = _candidate_key(candidate.smiles)
        evidence_summary: list[str] = []
        contradictions: list[str] = []
        item_warnings: list[str] = []
        invalid = False

        nmr_item = nmr_by_key.get(key)
        hrms_item = hrms_by_key.get(key)
        msms_item = msms_by_key.get(key)
        tree_item = tree_by_key.get(key)
        lcms_item = lcms_by_key.get(key)

        formula = _candidate_formula(candidate, hrms_item)
        exact_mass = None
        try:
            exact_mass = formula_from_smiles(candidate.smiles).exact_mass
        except Exception:
            pass

        layers: list[UnifiedEvidenceLayerScore] = []

        if nmr_item is not None:
            invalid = invalid or nmr_item.label == "invalid_structure"
            contradictions.extend(nmr_item.contradictions)
            item_warnings.extend(nmr_item.warnings)
            evidence_summary.extend([f"NMR: {x}" for x in nmr_item.evidence_summary[:4]])
            layers.append(
                _layer(
                    "predicted_nmr",
                    used=True,
                    score=nmr_item.total_score,
                    weight=weights["predicted_nmr"],
                    evidence_summary=nmr_item.evidence_summary[:5],
                    warnings=nmr_item.warnings,
                    contradiction=bool(nmr_item.contradictions),
                    metadata={"rank": nmr_item.rank, "label": nmr_item.label},
                )
            )
        else:
            layers.append(_layer("predicted_nmr", used=False, score=None, weight=weights["predicted_nmr"]))

        if hrms_item is not None:
            invalid = invalid or hrms_item.label == "invalid_structure"
            if hrms_item.label == "outside_tolerance":
                contradictions.append("HRMS exact mass is outside tolerance for this candidate/adduct.")
            item_warnings.extend(hrms_item.warnings)
            evidence_summary.extend([f"HRMS: {x}" for x in hrms_item.evidence_summary[:3]])
            layers.append(
                _layer(
                    "hrms_exact_mass",
                    used=True,
                    score=hrms_item.ppm_score,
                    weight=weights["hrms_exact_mass"],
                    evidence_summary=hrms_item.evidence_summary[:5],
                    warnings=hrms_item.warnings,
                    contradiction=hrms_item.label == "outside_tolerance",
                    metadata={"rank": hrms_item.rank, "label": hrms_item.label, "ppm_error": hrms_item.ppm_error},
                )
            )
        else:
            layers.append(_layer("hrms_exact_mass", used=False, score=None, weight=weights["hrms_exact_mass"]))

        adduct_score = None
        adduct_evidence: list[str] = []
        if best_adduct is not None:
            adduct_score = best_adduct.candidate_score
            if formula and best_adduct_top_formulas:
                if formula in best_adduct_top_formulas:
                    adduct_evidence.append(f"Candidate formula {formula} appears among top formulas for inferred {best_adduct.adduct.name}.")
                else:
                    adduct_score = min(adduct_score, 0.58)
                    adduct_evidence.append(f"Candidate formula {formula} was not among top formula hits for inferred {best_adduct.adduct.name}.")
            else:
                adduct_evidence.append(f"Best inferred adduct is {best_adduct.adduct.name}; formula-specific adduct check was limited.")
            evidence_summary.extend([f"Adduct/isotope: {x}" for x in adduct_evidence[:3]])
            layers.append(
                _layer(
                    "adduct_isotope",
                    used=True,
                    score=adduct_score,
                    weight=weights["adduct_isotope"],
                    evidence_summary=adduct_evidence + best_adduct.evidence_summary[:3],
                    warnings=best_adduct.warnings,
                    metadata={"best_adduct": best_adduct.adduct.name, "primary_mz": adduct_result.primary_mz if adduct_result else None},
                )
            )
        else:
            layers.append(_layer("adduct_isotope", used=False, score=None, weight=weights["adduct_isotope"]))

        if msms_item is not None:
            invalid = invalid or msms_item.label == "invalid_structure"
            item_warnings.extend(msms_item.warnings)
            evidence_summary.extend([f"MS/MS: {x}" for x in msms_item.evidence_summary[:4]])
            msms_contradiction = msms_item.label == "weak_or_no_msms_support" and msms_item.precursor_score < 0.35
            if msms_contradiction:
                contradictions.append("MS/MS precursor/fragment evidence is weak for this candidate.")
            layers.append(
                _layer(
                    "msms_annotation",
                    used=True,
                    score=msms_item.candidate_score,
                    weight=weights["msms_annotation"],
                    evidence_summary=msms_item.evidence_summary[:5],
                    warnings=msms_item.warnings,
                    contradiction=msms_contradiction,
                    metadata={
                        "rank": msms_item.rank,
                        "label": msms_item.label,
                        "explained_intensity_fraction": msms_item.explained_intensity_fraction,
                    },
                )
            )
        else:
            layers.append(_layer("msms_annotation", used=False, score=None, weight=weights["msms_annotation"]))

        if tree_item is not None:
            invalid = invalid or tree_item.label == "invalid_structure"
            contradictions.extend(tree_item.contradiction_flags)
            item_warnings.extend(tree_item.warnings)
            evidence_summary.extend([f"Fragmentation tree: {x}" for x in tree_item.evidence_summary[:4]])
            tree_contradiction = tree_item.label == "contradictory_fragmentation_tree" or bool(tree_item.contradiction_flags)
            layers.append(
                _layer(
                    "fragmentation_tree",
                    used=True,
                    score=tree_item.tree_score,
                    weight=weights["fragmentation_tree"],
                    evidence_summary=tree_item.evidence_summary[:5],
                    warnings=tree_item.warnings,
                    contradiction=tree_contradiction,
                    metadata={
                        "rank": tree_item.rank,
                        "label": tree_item.label,
                        "diagnostic_loss_count": tree_item.diagnostic_loss_count,
                        "max_tree_depth": tree_item.max_tree_depth,
                    },
                )
            )
        else:
            layers.append(_layer("fragmentation_tree", used=False, score=None, weight=weights["fragmentation_tree"]))

        if lcms_item is not None:
            if lcms_item.contradiction:
                contradictions.append("LC-MS feature-family consensus m/z/adduct evidence conflicts with this candidate.")
            item_warnings.extend(lcms_item.warnings)
            evidence_summary.extend([f"LC-MS feature family: {x}" for x in lcms_item.evidence_summary[:4]])
            layers.append(
                _layer(
                    "lcms_feature_family",
                    used=True,
                    score=lcms_item.score,
                    weight=weights.get("lcms_feature_family", req.lcms_layer_weight),
                    evidence_summary=lcms_item.evidence_summary[:5],
                    warnings=lcms_item.warnings,
                    contradiction=lcms_item.contradiction,
                    metadata={
                        "rank": lcms_item.rank,
                        "label": lcms_item.label,
                        "family_id": lcms_item.best_family_id,
                        "family_consensus_score": lcms_item.family_consensus_score,
                        "expected_mz": lcms_item.expected_mz,
                        "anchor_mz": lcms_item.best_family_anchor_mz,
                        "mz_error_da": lcms_item.mz_error_da,
                        "mz_error_ppm": lcms_item.mz_error_ppm,
                        "adduct": lcms_item.adduct,
                    },
                )
            )

        base_score, completeness = _weighted_score(layers, denominator_weight=sum(weights.values()))
        used_layers = [layer for layer in layers if layer.used and layer.score is not None]
        agreement_count = sum(1 for layer in used_layers if layer.agreement)
        contradiction_count = len([x for x in contradictions if x]) + sum(1 for layer in used_layers if layer.contradiction)
        missing_layers = [layer.label for layer in layers if not layer.used]

        confidence = base_score
        confidence *= 0.86 + 0.14 * completeness
        confidence += min(0.06, agreement_count * 0.012)
        confidence -= min(0.24, contradiction_count * 0.045)
        confidence = round(_clamp(confidence), 4)

        label = _label(confidence, len(used_layers), contradiction_count, invalid)
        if not evidence_summary and not invalid:
            evidence_summary.append("No comparable evidence layer was supplied for this candidate.")
        if invalid:
            contradictions.append("Candidate could not be parsed by one or more structure-aware engines.")

        raw_items.append(
            UnifiedCandidateConfidenceItem(
                rank=0,
                name=candidate.name,
                role=candidate.role,
                smiles=candidate.smiles,
                formula=formula,
                exact_mass=round(exact_mass, 6) if exact_mass is not None else None,
                label=label,
                confidence_band=_band(label),
                confidence_score=confidence,
                raw_weighted_score=round(base_score, 4),
                evidence_completeness=round(completeness, 4),
                agreement_count=agreement_count,
                contradiction_count=contradiction_count,
                missing_layers=missing_layers,
                layers=layers,
                layer_scores={layer.layer: layer.score for layer in layers if layer.used},
                evidence_summary=evidence_summary[:12],
                contradictions=list(dict.fromkeys([x for x in contradictions if x]))[:12],
                warnings=list(dict.fromkeys([x for x in item_warnings if x]))[:12],
                metadata={
                    "selected_adduct": selected_adduct,
                    "used_layer_count": len(used_layers),
                    "candidate_key": key,
                    "lcms_feature_family_match": lcms_item.model_dump(mode="json") if lcms_item is not None else None,
                },
            )
        )

    sorted_items = sorted(raw_items, key=lambda item: item.confidence_score, reverse=True)
    ranked: list[UnifiedCandidateConfidenceItem] = []
    for idx, item in enumerate(sorted_items):
        ranked.append(item.model_copy(update={"rank": idx + 1}))

    ambiguity_alerts: list[str] = []
    if len(ranked) >= 2:
        delta = ranked[0].confidence_score - ranked[1].confidence_score
        if delta < req.ambiguity_delta_threshold:
            ambiguity_alerts.append(f"Top candidates are close in unified confidence score (delta {delta:.3f}); review peak-level evidence.")
    if ranked and ranked[0].contradiction_count:
        ambiguity_alerts.append("The top-ranked candidate has contradiction flags; do not treat ranking as final identification.")
    if ranked and ranked[0].evidence_completeness < 0.45:
        ambiguity_alerts.append("Unified ranking is based on sparse evidence; add more NMR/MS layers before decision.")

    evidence_layers_used = sorted({layer.label for item in ranked for layer in item.layers if layer.used})
    global_contradictions: list[str] = []
    if hrms_result and hrms_result.exact_match_count == 0:
        global_contradictions.append("No candidate was within HRMS exact-mass tolerance.")
    if frag_tree_result and frag_tree_result.best_candidate and frag_tree_result.best_candidate.contradiction_count:
        global_contradictions.append("Best fragmentation-tree candidate contains contradiction flags.")
    if lcms_bridge_result and any(match.contradiction for match in lcms_bridge_result.matches):
        global_contradictions.append("One or more candidates conflict with promoted LC-MS feature-family m/z/adduct evidence.")

    return UnifiedCandidateConfidenceResult(
        sample_id=req.sample_id,
        solvent=req.solvent,
        selected_adduct=selected_adduct,
        candidate_count=len(ranked),
        best_candidate=ranked[0] if ranked else None,
        ranked_candidates=ranked,
        evidence_layers_used=evidence_layers_used,
        global_contradictions=global_contradictions,
        ambiguity_alerts=ambiguity_alerts,
        notes=notes,
        warnings=warnings,
        component_metadata=component_metadata,
    )


def _normalize_bundle_layer(item: EvidenceBundleItem) -> str:
    candidates = [
        item.layer,
        item.source_tab,
        item.endpoint or "",
        item.title,
    ]
    for raw in candidates:
        normalized = (
            str(raw or "")
            .strip()
            .lower()
            .replace("-", "_")
            .replace("/", "_")
            .replace(" ", "_")
        )
        if normalized in BUNDLE_LAYER_ALIASES:
            return BUNDLE_LAYER_ALIASES[normalized]
        if "predicted" in normalized and "nmr" in normalized:
            return "predicted_nmr"
        if "hrms" in normalized or "exact_mass" in normalized:
            return "hrms_exact_mass"
        if "adduct" in normalized or "isotope" in normalized:
            return "adduct_isotope"
        if "fragmentation" in normalized:
            return "fragmentation_tree"
        if "msms" in normalized or "ms_ms" in normalized:
            return "msms_annotation"
        if "dereplication" in normalized or "lcms" in normalized:
            return "lcms_feature_family"
    return "lcms_feature_family" if "lcms" in str(item.layer).lower() else "predicted_nmr"


def _bundle_expected_key(item: EvidenceBundleItem) -> str:
    raw = " ".join([item.layer, item.source_tab, item.endpoint or "", item.title]).lower()
    normalized = raw.replace("-", "_").replace("/", "_").replace(" ", "_")
    if "dereplication" in normalized:
        return "lcms_dereplication"
    if "confidence" in normalized and "bridge" in normalized:
        return "lcms_confidence_bridge"
    if "consensus" in normalized and "lcms" in normalized:
        return "lcms_feature_family_consensus"
    return _normalize_bundle_layer(item)


def _dedupe_strings(values: list[str], *, limit: int = 100) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


def _bundle_candidates_from_text(text: str | None) -> list[CandidateInput]:
    if not text or not text.strip():
        return []
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
    if len(candidates) > 25:
        raise UnifiedConfidenceError("Evidence-bundle synthesis is limited to 25 candidates.")
    return candidates


def _entry_score(entry: dict[str, Any], fallback: float | None = None) -> float | None:
    for key in (
        "confidence_score",
        "total_score",
        "candidate_score",
        "tree_score",
        "ppm_score",
        "score",
        "family_consensus_score",
        "consensus_score",
    ):
        value = entry.get(key)
        if value is not None:
            try:
                return _clamp(float(value))
            except (TypeError, ValueError):
                continue
    return _round_score(fallback)


def _response_score(response: dict[str, Any], fallback: float | None = None) -> float | None:
    for key in ("best_candidate", "best_match", "best_adduct_candidate", "best_family"):
        value = response.get(key)
        if isinstance(value, dict):
            score = _entry_score(value)
            if score is not None:
                return score
    return _entry_score(response, fallback)


def _candidate_entries(response: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("ranked_candidates", "matches", "candidates"):
        value = response.get(key)
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    for key in ("best_candidate", "best_match"):
        value = response.get(key)
        if isinstance(value, dict):
            entries.append(value)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        marker = str(entry.get("smiles") or entry.get("name") or entry)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(entry)
    return deduped


def _entry_contradictions(entry: dict[str, Any]) -> list[str]:
    contradictions: list[str] = []
    for key in ("contradictions", "contradiction_flags"):
        value = entry.get(key)
        if isinstance(value, list):
            contradictions.extend(str(item) for item in value if str(item).strip())
    label = str(entry.get("label") or "").lower()
    if any(token in label for token in ("outside_tolerance", "contradict", "conflict")):
        contradictions.append(f"Candidate layer label indicates conflicting evidence: {entry.get('label')}.")
    return _dedupe_strings(contradictions)


def _entry_warnings(entry: dict[str, Any]) -> list[str]:
    value = entry.get("warnings")
    if isinstance(value, list):
        return _dedupe_strings([str(item) for item in value])
    return []


def _entry_summary(entry: dict[str, Any], item: EvidenceBundleItem) -> list[str]:
    summary: list[str] = []
    value = entry.get("evidence_summary")
    if isinstance(value, list):
        summary.extend(str(part) for part in value if str(part).strip())
    if not summary and item.summary:
        summary.append(item.summary)
    if not summary:
        label = entry.get("label") or item.label or item.status
        summary.append(f"{item.title}: {label}.")
    return _dedupe_strings(summary, limit=8)


def _selected_adduct_from_bundle(items: list[EvidenceBundleItem]) -> str:
    for item in items:
        response = item.response
        raw = response.get("adduct")
        if isinstance(raw, dict) and raw.get("name"):
            return str(raw["name"])
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        for key in ("best_adduct_candidate", "best_match"):
            value = response.get(key)
            if isinstance(value, dict):
                nested = value.get("adduct")
                if isinstance(nested, dict) and nested.get("name"):
                    return str(nested["name"])
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return "[M+H]+"


def _empty_candidate_state(candidate: CandidateInput) -> dict[str, Any]:
    formula = None
    exact_mass = None
    try:
        formula_info = formula_from_smiles(candidate.smiles)
        formula = formula_info.formula
        exact_mass = formula_info.exact_mass
    except Exception:
        try:
            summary = structure_summary_from_smiles(candidate.smiles)
            formula = summary.formula
        except Exception:
            pass
    return {
        "candidate": candidate,
        "formula": formula,
        "exact_mass": exact_mass,
        "layers": {},
        "evidence_summary": [],
        "contradictions": [],
        "warnings": [],
    }


def _merge_candidate_layer(
    state: dict[str, Any],
    *,
    layer: str,
    weight: float,
    score: float | None,
    item: EvidenceBundleItem,
    entry: dict[str, Any] | None,
    contextual: bool = False,
) -> None:
    if score is not None:
        score = _round_score(min(score, 0.55) if contextual else score)
    contradictions = list(item.contradictions)
    warnings = list(item.warnings)
    summary = list(item.evidence_summary)
    metadata: dict[str, Any] = {
        "bundle_item_id": item.id,
        "bundle_item_layer": item.layer,
        "bundle_item_title": item.title,
        "endpoint": item.endpoint,
        "source_tab": item.source_tab,
        "contextual_layer": contextual,
    }
    if entry is not None:
        contradictions.extend(_entry_contradictions(entry))
        warnings.extend(_entry_warnings(entry))
        summary.extend(_entry_summary(entry, item))
        metadata.update(
            {
                "rank": entry.get("rank"),
                "label": entry.get("label"),
                "response_candidate_score": _entry_score(entry),
            }
        )
    elif contextual:
        summary.append(
            f"{item.title} was selected as contextual evidence; it was not candidate-specific."
        )
    existing = state["layers"].get(layer)
    if existing is not None:
        score = max(
            [value for value in (existing["score"], score) if value is not None],
            default=None,
        )
        contradictions = existing["contradictions"] + contradictions
        warnings = existing["warnings"] + warnings
        summary = existing["summary"] + summary
        metadata = {**existing["metadata"], "additional_bundle_item_id": item.id}
    state["layers"][layer] = {
        "score": score,
        "weight": weight,
        "summary": _dedupe_strings(summary, limit=12),
        "warnings": _dedupe_strings(warnings, limit=12),
        "contradictions": _dedupe_strings(contradictions, limit=12),
        "metadata": metadata,
    }
    state["evidence_summary"].extend(summary)
    state["contradictions"].extend(contradictions)
    state["warnings"].extend(warnings)


def _bundle_top_label(
    *,
    ranked: list[UnifiedCandidateConfidenceItem],
    contradiction_count: int,
    selected_count: int,
) -> str:
    if contradiction_count:
        return "conflicting_evidence"
    if not ranked:
        return "requires_review" if selected_count else "insufficient_evidence"
    label = ranked[0].label
    if label in {
        "high_confidence_candidate",
        "moderate_confidence_candidate",
        "low_confidence_candidate",
        "conflicting_evidence",
        "insufficient_evidence",
    }:
        return label
    return "requires_review"


def build_unified_candidate_confidence_from_bundle(
    req: UnifiedEvidenceBundleRequest,
) -> UnifiedEvidenceBundleConfidenceResult:
    """Synthesize selected Evidence Queue endpoint responses into cautious confidence."""
    if not req.evidence_items:
        raise UnifiedConfidenceError("Evidence bundle must include at least one evidence item.")

    selected_items = [item for item in req.evidence_items if item.selected_for_unified]
    if not selected_items:
        raise UnifiedConfidenceError("No evidence bundle items were selected for unified confidence.")

    weights = dict(DEFAULT_LAYER_WEIGHTS)
    weights["lcms_feature_family"] = 0.12
    selected_adduct = _selected_adduct_from_bundle(selected_items)
    warnings: list[str] = []
    notes: list[str] = [
        "Evidence-bundle confidence is synthesized from selected frontend Evidence Queue responses.",
        "This endpoint ranks support for review only; it does not confirm identity or stereochemistry.",
        "Human review is required before using this output for release or regulatory decisions.",
    ]
    global_contradictions: list[str] = []
    layer_global_scores: dict[str, float | None] = {}
    used_expected_layers: set[str] = set()
    used_unified_layers: set[str] = set()
    grouped_layers: dict[str, list[str]] = {}
    references: list[dict[str, Any]] = []

    candidates_by_key: dict[str, dict[str, Any]] = {}
    for candidate in _bundle_candidates_from_text(req.candidates_text):
        candidates_by_key[_candidate_key(candidate.smiles)] = _empty_candidate_state(candidate)

    for item in selected_items:
        layer = _normalize_bundle_layer(item)
        expected_key = _bundle_expected_key(item)
        used_expected_layers.add(expected_key)
        used_unified_layers.add(layer)
        grouped_layers.setdefault(expected_key, []).append(item.id)
        response = item.response or {}
        response_hash = _canonical_hash(response)
        references.append(
            {
                "id": item.id,
                "layer": item.layer,
                "normalized_layer": layer,
                "title": item.title,
                "source_tab": item.source_tab,
                "endpoint": item.endpoint,
                "status": item.status,
                "score": item.score,
                "label": item.label,
                "created_at": item.created_at,
                "response_sha256": response_hash,
                "provenance": item.provenance,
            }
        )
        item_warnings = list(item.warnings)
        response_warnings = response.get("warnings")
        if isinstance(response_warnings, list):
            item_warnings.extend(str(warning) for warning in response_warnings)
        warnings.extend(item_warnings)
        notes.extend(item.notes)
        contradictions = list(item.contradictions)
        for key in ("global_contradictions", "contradictions", "ambiguity_alerts"):
            value = response.get(key)
            if isinstance(value, list):
                contradictions.extend(str(part) for part in value if str(part).strip())
        if any(token in str(item.label or item.status).lower() for token in ("conflict", "contradict")):
            contradictions.append(f"Bundle item {item.id} is labeled/statused as conflicting evidence.")
        global_contradictions.extend(contradictions)

        global_score = _response_score(response, item.score)
        current_global = layer_global_scores.get(layer)
        layer_global_scores[layer] = max(
            [value for value in (current_global, global_score) if value is not None],
            default=None,
        )

        for entry in _candidate_entries(response):
            smiles = entry.get("smiles")
            if not smiles:
                continue
            candidate = CandidateInput(
                name=entry.get("name"),
                role=entry.get("role"),
                smiles=str(smiles),
            )
            key = _candidate_key(candidate.smiles)
            state = candidates_by_key.setdefault(key, _empty_candidate_state(candidate))
            _merge_candidate_layer(
                state,
                layer=layer,
                weight=weights.get(layer, 0.1),
                score=_entry_score(entry, item.score),
                item=item,
                entry=entry,
            )

    for state in candidates_by_key.values():
        for layer, score in layer_global_scores.items():
            if layer in state["layers"] or score is None:
                continue
            _merge_candidate_layer(
                state,
                layer=layer,
                weight=weights.get(layer, 0.1),
                score=score,
                item=next(item for item in selected_items if _normalize_bundle_layer(item) == layer),
                entry=None,
                contextual=True,
            )

    raw_ranked: list[UnifiedCandidateConfidenceItem] = []
    denominator_weight = sum(weights[layer] for layer in weights if layer in {
        "predicted_nmr",
        "hrms_exact_mass",
        "adduct_isotope",
        "msms_annotation",
        "fragmentation_tree",
        "lcms_feature_family",
    })
    for state in candidates_by_key.values():
        candidate = state["candidate"]
        layers: list[UnifiedEvidenceLayerScore] = []
        for layer in (
            "predicted_nmr",
            "hrms_exact_mass",
            "adduct_isotope",
            "msms_annotation",
            "fragmentation_tree",
            "lcms_feature_family",
        ):
            layer_state = state["layers"].get(layer)
            if layer_state is None:
                layers.append(_layer(layer, used=False, score=None, weight=weights.get(layer, 0.1)))
                continue
            layers.append(
                _layer(
                    layer,
                    used=True,
                    score=layer_state["score"],
                    weight=layer_state["weight"],
                    evidence_summary=layer_state["summary"],
                    warnings=layer_state["warnings"],
                    contradiction=bool(layer_state["contradictions"]),
                    metadata=layer_state["metadata"],
                )
            )
        base_score, completeness = _weighted_score(layers, denominator_weight=denominator_weight)
        used_layers = [layer for layer in layers if layer.used and layer.score is not None]
        agreement_count = sum(1 for layer in used_layers if layer.agreement)
        contradictions = _dedupe_strings(state["contradictions"], limit=12)
        contradiction_count = len(contradictions) + sum(1 for layer in used_layers if layer.contradiction)
        confidence = _clamp(
            base_score * (0.86 + 0.14 * completeness)
            + min(0.06, agreement_count * 0.012)
            - min(0.24, contradiction_count * 0.045)
        )
        label = _label(confidence, len(used_layers), contradiction_count, invalid=False)
        raw_ranked.append(
            UnifiedCandidateConfidenceItem(
                rank=0,
                name=candidate.name,
                role=candidate.role,
                smiles=candidate.smiles,
                formula=state["formula"],
                exact_mass=round(state["exact_mass"], 6)
                if state["exact_mass"] is not None
                else None,
                label=label,
                confidence_band=_band(label),
                confidence_score=round(confidence, 4),
                raw_weighted_score=round(base_score, 4),
                evidence_completeness=round(completeness, 4),
                agreement_count=agreement_count,
                contradiction_count=contradiction_count,
                missing_layers=[layer.label for layer in layers if not layer.used],
                layers=layers,
                layer_scores={layer.layer: layer.score for layer in layers if layer.used},
                evidence_summary=_dedupe_strings(state["evidence_summary"], limit=12)
                or ["Evidence bundle provided no candidate-specific summary for this candidate."],
                contradictions=contradictions,
                warnings=_dedupe_strings(state["warnings"], limit=12),
                metadata={
                    "candidate_key": _candidate_key(candidate.smiles),
                    "source": "evidence_bundle",
                },
            )
        )

    ranked = [
        item.model_copy(update={"rank": index + 1})
        for index, item in enumerate(
            sorted(raw_ranked, key=lambda candidate: candidate.confidence_score, reverse=True)
        )
    ]
    missing_layers = [layer for layer in BUNDLE_EXPECTED_LAYERS if layer not in used_expected_layers]
    evidence_completeness = (
        ranked[0].evidence_completeness
        if ranked
        else round(len(used_expected_layers) / max(1, len(BUNDLE_EXPECTED_LAYERS)), 4)
    )
    agreement_count = ranked[0].agreement_count if ranked else sum(
        1 for score in layer_global_scores.values() if score is not None and score >= 0.58
    )
    contradiction_count = len(_dedupe_strings(global_contradictions)) + (
        ranked[0].contradiction_count if ranked else 0
    )
    ambiguity_alerts: list[str] = []
    if len(ranked) >= 2 and ranked[0].confidence_score - ranked[1].confidence_score < 0.05:
        ambiguity_alerts.append("Top evidence-bundle candidates are close; review source evidence.")
    if not ranked:
        ambiguity_alerts.append(
            "Evidence bundle did not contain candidate-level scores; review source evidence manually."
        )
    label = _bundle_top_label(
        ranked=ranked,
        contradiction_count=contradiction_count,
        selected_count=len(selected_items),
    )
    status = (
        "bundle_candidate_ranking_requires_review"
        if ranked
        else "bundle_evidence_summary_requires_review"
    )
    if contradiction_count:
        status = "bundle_conflicting_evidence_requires_review"

    metadata = {
        "bundle_metadata": req.metadata or {},
        "selected_item_count": len(selected_items),
        "ignored_item_count": len(req.evidence_items) - len(selected_items),
        "grouped_layers": grouped_layers,
        "evidence_references": references,
        "raw_response_policy": "Full endpoint responses are summarized by SHA-256 reference only.",
    }
    component_metadata = {
        "bundle_layer_scores": {
            layer: score for layer, score in layer_global_scores.items() if score is not None
        },
        "selected_adduct": selected_adduct,
    }

    return UnifiedEvidenceBundleConfidenceResult(
        sample_id=req.sample_id,
        solvent=req.solvent,
        selected_adduct=selected_adduct,
        candidate_count=len(ranked),
        best_candidate=ranked[0] if ranked else None,
        ranked_candidates=ranked,
        evidence_layers_used=[
            BUNDLE_LAYER_LABELS.get(layer, layer) for layer in sorted(used_expected_layers)
        ],
        evidence_completeness=round(evidence_completeness, 4),
        agreement_count=agreement_count,
        contradiction_count=contradiction_count,
        missing_layers=missing_layers,
        global_contradictions=_dedupe_strings(global_contradictions, limit=20),
        ambiguity_alerts=ambiguity_alerts,
        warnings=_dedupe_strings(warnings, limit=30),
        notes=_dedupe_strings(notes, limit=30),
        human_review_required=True,
        label=label,
        status=status,
        metadata=metadata,
        component_metadata=component_metadata,
    )
