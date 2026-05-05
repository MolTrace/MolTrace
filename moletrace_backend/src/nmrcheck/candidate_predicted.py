from __future__ import annotations

from .carbon13 import Carbon13ParseError
from .exceptions import PeakParseError
from .models import (
    CandidatePredictedNMRMatchItem,
    CandidatePredictedNMRMatchRequest,
    CandidatePredictedNMRMatchResult,
)
from .nmr2d import NMR2DPreviewReport
from .nmr_prediction import (
    predict_nmr_from_smiles,
    score_observed_2d_against_predicted_hsqc,
    score_observed_against_predicted_carbon13,
    score_observed_against_predicted_proton,
)

PREDICTED_NMR_MATCH_LIMITATIONS = [
    "Candidate-specific predicted NMR matching is ranking evidence, not final structure "
    "identification.",
    "The bundled predictor is a transparent RDKit atom-environment heuristic; external ML or "
    "DFT predictors may change ranking.",
    "Peak parsing can miss overlapped, solvent, impurity, exchangeable, stereochemical, or "
    "concentration-dependent signals.",
    "Human review is required before using the result in a regulatory-ready conclusion.",
]


def _weighted_available(scores: dict[str, float | None], weights: dict[str, float]) -> float:
    total = 0.0
    denominator = 0.0
    for key, weight in weights.items():
        value = scores.get(key)
        if value is None:
            continue
        total += max(0.0, min(1.0, value)) * weight
        denominator += weight
    if denominator <= 0:
        return 0.0
    return round(max(0.0, min(1.0, total / denominator)), 4)


def _label(score: float, rank: int, delta_to_next: float | None, valid: bool) -> str:
    if not valid:
        return "invalid_structure"
    if rank == 1 and score >= 0.76 and (delta_to_next is None or delta_to_next >= 0.05):
        return "best_predicted_match"
    if score >= 0.68:
        return "predicted_match"
    if score >= 0.50:
        return "ambiguous"
    return "weak_match"


def _moltrace_evidence_label(
    score: float,
    *,
    rank: int,
    delta_to_next: float | None,
    valid: bool,
    has_evidence: bool,
    has_contradictions: bool,
) -> str:
    if not valid:
        return "invalid_structure"
    if not has_evidence:
        return "insufficient_evidence"
    if has_contradictions and score < 0.72:
        return "conflicting_evidence"
    if (
        rank == 1
        and score >= 0.76
        and not has_contradictions
        and (delta_to_next is None or delta_to_next >= 0.05)
    ):
        return "best_supported"
    if score >= 0.62 and not has_contradictions:
        return "plausible"
    if score < 0.36:
        return "insufficient_evidence"
    return "requires_review"


def _experiment_label(value: object) -> str:
    if hasattr(value, "value"):
        return str(value.value).upper()
    return str(value or "UNKNOWN").upper()


def match_candidates_with_predicted_nmr(
    request: CandidatePredictedNMRMatchRequest,
    *,
    observed_nmr2d: NMR2DPreviewReport | None = None,
) -> CandidatePredictedNMRMatchResult:
    evidence_layers: list[str] = []
    if request.observed_proton_text:
        evidence_layers.append("1H predicted-match")
    if request.observed_carbon13_text:
        evidence_layers.append("13C predicted-match")
    if observed_nmr2d is not None:
        evidence_layers.append(
            f"{_experiment_label(observed_nmr2d.experiment_detected)} predicted-HSQC-context"
        )
    has_observed_evidence = bool(evidence_layers)

    warnings: list[str] = []
    notes = [
        "Candidate-specific predicted NMR matching compares observed spectra with predicted "
        "shifts for each candidate.",
        "Current predictor is a transparent RDKit environment heuristic; production deployments "
        "should allow external ML/DFT predictors.",
        "Results are ranking evidence and require human review.",
    ]
    if (
        not request.observed_proton_text
        and not request.observed_carbon13_text
        and observed_nmr2d is None
    ):
        warnings.append(
            "No observed NMR evidence supplied; predicted matching cannot discriminate candidates."
        )

    raw_items: list[CandidatePredictedNMRMatchItem] = []
    for candidate in request.candidates:
        prediction = predict_nmr_from_smiles(
            candidate.smiles,
            name=candidate.name,
            solvent=request.solvent,
        )
        valid = prediction.confidence_label != "invalid_structure"
        proton_result = None
        carbon_result = None
        nmr2d_result = None
        item_warnings = list(prediction.warnings)
        evidence_summary: list[str] = []
        contradictions: list[str] = []

        if valid and request.observed_proton_text:
            try:
                proton_result = score_observed_against_predicted_proton(
                    request.observed_proton_text,
                    prediction,
                )
                evidence_summary.append(
                    f"Predicted 1H match score: {proton_result.combined_score:.2f}."
                )
                if proton_result.unmatched_observed_count >= 2:
                    contradictions.append(
                        f"{proton_result.unmatched_observed_count} observed 1H signal instances "
                        "were not explained by predicted shifts."
                    )
            except PeakParseError as exc:
                item_warnings.append(f"Observed 1H text could not be scored: {exc}")

        if valid and request.observed_carbon13_text:
            try:
                carbon_result = score_observed_against_predicted_carbon13(
                    request.observed_carbon13_text,
                    prediction,
                    solvent=request.solvent,
                )
                evidence_summary.append(
                    f"Predicted 13C match score: {carbon_result.combined_score:.2f}."
                )
                if carbon_result.unmatched_observed_count >= 2:
                    contradictions.append(
                        f"{carbon_result.unmatched_observed_count} observed 13C peak(s) were "
                        "not explained by predicted shifts."
                    )
            except Carbon13ParseError as exc:
                item_warnings.append(f"Observed 13C text could not be scored: {exc}")

        if valid and observed_nmr2d is not None:
            nmr2d_result = score_observed_2d_against_predicted_hsqc(observed_nmr2d, prediction)
            if nmr2d_result is not None:
                evidence_summary.append(
                    "Predicted HSQC cross-peak match score: "
                    f"{nmr2d_result.combined_score:.2f}."
                )
                if nmr2d_result.unmatched_observed_count >= 2:
                    contradictions.append(
                        f"{nmr2d_result.unmatched_observed_count} observed HSQC/HMQC "
                        "cross-peak(s) were not explained by predicted candidate attachments."
                    )
            elif _experiment_label(observed_nmr2d.experiment_detected) in {"HMBC", "COSY"}:
                item_warnings.append(
                    "Current candidate-specific 2D prediction supports direct HSQC/HMQC-like "
                    "C-H attachments; COSY/HMBC prediction is not yet implemented."
                )

        scores = {
            "proton": proton_result.combined_score if proton_result else None,
            "carbon13": carbon_result.combined_score if carbon_result else None,
            "nmr2d": nmr2d_result.combined_score if nmr2d_result else None,
        }
        total = (
            _weighted_available(scores, {"proton": 0.42, "carbon13": 0.40, "nmr2d": 0.18})
            if valid
            else 0.0
        )
        if valid and prediction.metadata.get("average_uncertainty_ppm", 0):
            uncertainty = float(prediction.metadata.get("average_uncertainty_ppm", 0))
            total = round(max(0.0, total * (1.0 - min(0.12, uncertainty / 50.0))), 4)

        if not evidence_summary and valid:
            evidence_summary.append(
                "Prediction generated, but no comparable observed evidence layer was supplied."
            )

        raw_items.append(
            CandidatePredictedNMRMatchItem(
                rank=0,
                name=candidate.name,
                role=candidate.role,
                smiles=candidate.smiles,
                label="weak_match" if valid else "invalid_structure",
                total_score=total,
                prediction=prediction,
                proton_similarity=proton_result,
                carbon13_similarity=carbon_result,
                nmr2d_similarity=nmr2d_result,
                evidence_summary=evidence_summary,
                contradictions=contradictions,
                warnings=item_warnings,
                limitations=PREDICTED_NMR_MATCH_LIMITATIONS,
                metadata={
                    "prediction_method": prediction.prediction_method,
                    "prediction_confidence": prediction.confidence_label,
                    "human_review_required": True,
                },
            )
        )

    sorted_items = sorted(raw_items, key=lambda item: item.total_score, reverse=True)
    ranked: list[CandidatePredictedNMRMatchItem] = []
    for idx, item in enumerate(sorted_items):
        next_score = sorted_items[idx + 1].total_score if idx + 1 < len(sorted_items) else None
        delta = None if next_score is None else item.total_score - next_score
        valid = item.label != "invalid_structure"
        label = _label(item.total_score, idx + 1, delta, valid)
        evidence_label = _moltrace_evidence_label(
            item.total_score,
            rank=idx + 1,
            delta_to_next=delta,
            valid=valid,
            has_evidence=has_observed_evidence,
            has_contradictions=bool(item.contradictions),
        )
        ranked.append(
            item.model_copy(
                update={
                    "rank": idx + 1,
                    "label": label,
                    "evidence_label": evidence_label,
                }
            )
        )

    ambiguity_alerts: list[str] = []
    if len(ranked) >= 2:
        delta = ranked[0].total_score - ranked[1].total_score
        if delta < 0.05:
            ambiguity_alerts.append(
                f"Top candidates are close by predicted-NMR score (delta {delta:.3f}); inspect "
                "peak-level matches."
            )
    if any(item.contradictions for item in ranked[:3]):
        ambiguity_alerts.append("One or more top candidates has unexplained observed peaks.")

    return CandidatePredictedNMRMatchResult(
        sample_id=request.sample_id,
        solvent=request.solvent,
        candidate_count=len(ranked),
        best_candidate=ranked[0] if ranked else None,
        ranked_candidates=ranked,
        ambiguity_alerts=ambiguity_alerts,
        evidence_layers_used=evidence_layers,
        notes=notes,
        warnings=warnings,
        limitations=PREDICTED_NMR_MATCH_LIMITATIONS,
        metadata={
            "prediction_engine": "heuristic_rdkit_region_model",
            "prediction_status": "transparent_beta",
            "candidate_limit": 25,
            "human_review_required": True,
        },
    )
