"""5-layer SpectraCheck benchmark.

The benchmark scores each (structure, observed spectrum) case across five
layers reflecting what regulators and chemists care about:

  1. **Peak-level accuracy** — does each predicted shift land on a real
     observed peak? Measured via greedy matching with a tolerance window.
  2. **Structural ranking** — when multiple candidates are supplied, does the
     true structure sit at rank 1 (or in top-k)?
  3. **Explainability** — what fraction of observed peaks carry a category +
     reason + chemical region that a human can read? This is the
     "prove WHY" axis the product positions on.
  4. **Robustness** — when the most prominent peaks are dropped from the
     observed list (simulating noise / missing signals), does peak-level
     accuracy still hold up?
  5. **Regulatory evidence** — does the case carry the audit envelope
     (sample id, sha256, operator, instrument) and does the per-peak result
     keep its reasoning trace?

The module is intentionally additive: it reuses
:func:`predict_nmr_from_smiles`, the candidate comparator, and the peak
enrichment functions added in Phase 2. It does not change any existing
analyze flow.

Public entry points:

  - :func:`evaluate_case`
  - :func:`evaluate_suite`
"""

from __future__ import annotations

from statistics import mean
from typing import Any

from .candidate import compare_candidates, parse_candidate_text
from .models import (
    BenchmarkAggregate,
    BenchmarkCase,
    BenchmarkCaseResult,
    BenchmarkLayerScore,
    BenchmarkRunResponse,
    CandidateComparisonRequest,
    Peak,
)
from .nmr_prediction import predict_nmr_from_smiles
from .parser import parse_nmr_text
from .peak_categorization import build_predicted_vs_observed, enrich_peaks

LAYER_WEIGHTS = {
    "peak_level_accuracy": 0.30,
    "structural_ranking": 0.20,
    "explainability": 0.20,
    "robustness": 0.15,
    "regulatory_evidence": 0.15,
}


def _enrich_observed_peaks(peaks: list[Peak], nucleus: str, solvent: str | None) -> list[dict[str, Any]]:
    raw = [
        {
            "shift_ppm": float(p.shift_ppm),
            "multiplicity": p.multiplicity,
            "integration_h": float(p.integration_h),
            "j_values_hz": list(p.j_values_hz),
        }
        for p in peaks
    ]
    return enrich_peaks(peaks=raw, nucleus=nucleus, solvent=solvent)  # type: ignore[arg-type]


def _peak_level_accuracy(
    *, smiles: str, observed: list[dict[str, Any]], nucleus: str, solvent: str | None
) -> BenchmarkLayerScore:
    notes: list[str] = []
    components: dict[str, Any] = {}
    try:
        prediction = predict_nmr_from_smiles(smiles, name=None, solvent=solvent)
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Prediction failed: {exc}")
        return BenchmarkLayerScore(
            name="peak_level_accuracy",
            score=0.0,
            components={"error": str(exc)},
            notes=notes,
        )

    predicted = (
        prediction.proton_peaks if nucleus == "1H" else prediction.carbon13_peaks
    )
    rows = build_predicted_vs_observed(
        predicted_peaks=predicted,
        observed_peaks=observed,
        nucleus=nucleus,  # type: ignore[arg-type]
    )
    matched = sum(1 for r in rows if r["status"] == "matched")
    unmatched_predicted = sum(1 for r in rows if r["status"] == "unmatched_predicted")
    unmatched_observed = sum(1 for r in rows if r["status"] == "unmatched_observed")
    denominator = max(matched + unmatched_predicted + unmatched_observed, 1)
    score = round(matched / denominator, 4)
    components = {
        "matched": matched,
        "unmatched_predicted": unmatched_predicted,
        "unmatched_observed": unmatched_observed,
        "predicted_peak_count": len(predicted),
        "observed_peak_count": len(observed),
    }
    if matched == 0:
        notes.append("No predicted peak landed within tolerance of any observed peak.")
    if unmatched_predicted:
        notes.append(
            f"{unmatched_predicted} predicted peak(s) have no observed match — possible missing signals."
        )
    if unmatched_observed:
        notes.append(
            f"{unmatched_observed} observed peak(s) have no predicted match — possible impurity / overlap."
        )
    return BenchmarkLayerScore(
        name="peak_level_accuracy",
        score=score,
        components=components,
        notes=notes,
    )


def _structural_ranking(
    *,
    case: BenchmarkCase,
    observed_text: str,
) -> BenchmarkLayerScore:
    """Reward the case if the true SMILES is the highest-scoring candidate.

    When ``candidate_block`` is empty we still need a score: synthesize a
    candidate block from the true SMILES alone so the layer reports 1.0 (it
    is trivially correct, but we flag it in the notes).
    """
    notes: list[str] = []
    components: dict[str, Any] = {}
    block = case.candidate_block or f"True | {case.smiles}"
    try:
        candidates = parse_candidate_text(block)
    except Exception as exc:  # noqa: BLE001
        return BenchmarkLayerScore(
            name="structural_ranking",
            score=0.0,
            components={"error": str(exc)},
            notes=[f"Could not parse candidate block: {exc}"],
        )
    if not candidates:
        return BenchmarkLayerScore(
            name="structural_ranking",
            score=0.0,
            components={"candidate_count": 0},
            notes=["No parseable candidates."],
        )

    request = CandidateComparisonRequest(
        sample_id=case.sample_id,
        solvent=case.solvent,
        candidates=candidates,
        proton_nmr_text=observed_text if case.nucleus == "1H" else None,
        carbon13_text=observed_text if case.nucleus == "13C" else None,
    )
    result = compare_candidates(request)
    best = result.best_candidate
    candidate_count = result.candidate_count
    if best is None:
        return BenchmarkLayerScore(
            name="structural_ranking",
            score=0.0,
            components={"candidate_count": candidate_count},
            notes=["Candidate comparison returned no ranking."],
        )

    rank = None
    for idx, scored in enumerate(result.ranked_candidates):
        if scored.smiles.strip() == case.smiles.strip():
            rank = idx + 1
            break

    top1 = 1.0 if rank == 1 else 0.0
    top3 = 1.0 if rank is not None and rank <= 3 else 0.0
    # Reward top-1 most heavily, top-3 partially, and any-rank a little.
    if rank == 1:
        score = 1.0
    elif rank is not None and rank <= 3:
        score = 0.7
    elif rank is not None:
        score = 0.4
    else:
        score = 0.0

    components = {
        "candidate_count": candidate_count,
        "rank_of_true_structure": rank,
        "best_candidate_smiles": best.smiles,
        "best_candidate_score": float(best.total_score),
        "top1": top1,
        "top3": top3,
    }
    if rank is None:
        notes.append("True SMILES did not appear in the candidate block.")
    elif rank > 1:
        notes.append(f"True SMILES ranked #{rank} — not top-1.")
    if not case.candidate_block:
        notes.append("No candidate_block supplied — score reflects a trivial single-entry ranking.")
    return BenchmarkLayerScore(
        name="structural_ranking",
        score=round(score, 4),
        components=components,
        notes=notes,
    )


def _explainability(*, observed_enriched: list[dict[str, Any]]) -> BenchmarkLayerScore:
    if not observed_enriched:
        return BenchmarkLayerScore(
            name="explainability",
            score=0.0,
            components={"peak_count": 0},
            notes=["No observed peaks to score."],
        )
    total = len(observed_enriched)
    with_category = sum(1 for p in observed_enriched if p.get("category"))
    with_region = sum(1 for p in observed_enriched if p.get("chemical_region"))
    with_reason = sum(1 for p in observed_enriched if p.get("category_reason"))
    # Weighted average — reasoning is what proves "why", so weight it most.
    score = round(
        (0.25 * (with_category / total))
        + (0.30 * (with_region / total))
        + (0.45 * (with_reason / total)),
        4,
    )
    notes: list[str] = []
    if with_reason < total:
        notes.append(
            f"{total - with_reason} of {total} observed peak(s) have no category_reason — explainability gap."
        )
    return BenchmarkLayerScore(
        name="explainability",
        score=score,
        components={
            "peak_count": total,
            "with_category": with_category,
            "with_region": with_region,
            "with_reason": with_reason,
        },
        notes=notes,
    )


def _robustness(
    *,
    smiles: str,
    observed: list[dict[str, Any]],
    nucleus: str,
    solvent: str | None,
    baseline_score: float,
    drop_peaks: int,
) -> BenchmarkLayerScore:
    if drop_peaks <= 0 or not observed:
        return BenchmarkLayerScore(
            name="robustness",
            score=baseline_score,
            components={
                "drop_peaks": drop_peaks,
                "baseline_score": baseline_score,
                "perturbed_score": baseline_score,
            },
            notes=["No perturbation applied — robustness equals baseline."],
        )
    # Drop the peaks with the largest integrations — those are the easiest
    # signals, so removing them is the worst-case "noisy spectrum" perturbation.
    sorted_obs = sorted(
        observed, key=lambda p: float(p.get("integration_h") or 0.0), reverse=True
    )
    perturbed = sorted_obs[drop_peaks:]
    perturbed_score = _peak_level_accuracy(
        smiles=smiles,
        observed=perturbed,
        nucleus=nucleus,
        solvent=solvent,
    ).score
    # Robustness is the ratio of perturbed to baseline (capped at 1) so a
    # perfect baseline with no degradation reads as 1.0.
    if baseline_score <= 0.0:
        ratio = 0.0
    else:
        ratio = min(1.0, perturbed_score / baseline_score)
    return BenchmarkLayerScore(
        name="robustness",
        score=round(ratio, 4),
        components={
            "drop_peaks": drop_peaks,
            "baseline_score": baseline_score,
            "perturbed_score": perturbed_score,
        },
        notes=(
            ["Peak-level accuracy degraded materially after peak removal."]
            if ratio < 0.5
            else []
        ),
    )


def _regulatory_evidence(*, case: BenchmarkCase, observed_enriched: list[dict[str, Any]]) -> BenchmarkLayerScore:
    """Score the audit envelope and reasoning trace.

    Weights — 0.25 each: sample_id, sha256, operator/instrument provenance,
    per-peak reasoning trace (at least one category_reason present).
    """
    notes: list[str] = []
    has_sample_id = bool(case.sample_id and case.sample_id.strip())
    has_sha256 = bool(case.sha256 and len(case.sha256) == 64)
    has_provenance = bool(
        (case.operator and case.operator.strip()) or (case.instrument and case.instrument.strip())
    )
    has_reason = any(p.get("category_reason") for p in observed_enriched)
    components = {
        "has_sample_id": has_sample_id,
        "has_sha256": has_sha256,
        "has_provenance": has_provenance,
        "has_peak_reasoning_trace": has_reason,
    }
    if not has_sample_id:
        notes.append("sample_id missing — required for audit trail.")
    if not has_sha256:
        notes.append("sha256 hash missing — uploads should be cryptographically traceable.")
    if not has_provenance:
        notes.append("operator / instrument missing — required for regulatory provenance.")
    if not has_reason:
        notes.append("No category_reason on any peak — reasoning trace empty.")
    score = round(0.25 * sum(components.values()), 4)
    return BenchmarkLayerScore(
        name="regulatory_evidence",
        score=score,
        components=components,
        notes=notes,
    )


def evaluate_case(case: BenchmarkCase, *, robustness_drop_peaks: int = 1) -> BenchmarkCaseResult:
    warnings: list[str] = []
    try:
        parsed_peaks = parse_nmr_text(case.observed_nmr_text)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Could not parse observed NMR text: {exc}")
        parsed_peaks = []

    observed_enriched = (
        _enrich_observed_peaks(parsed_peaks, case.nucleus, case.solvent)
        if parsed_peaks
        else []
    )

    peak_layer = _peak_level_accuracy(
        smiles=case.smiles,
        observed=observed_enriched,
        nucleus=case.nucleus,
        solvent=case.solvent,
    )
    structural_layer = _structural_ranking(case=case, observed_text=case.observed_nmr_text)
    explain_layer = _explainability(observed_enriched=observed_enriched)
    robust_layer = _robustness(
        smiles=case.smiles,
        observed=observed_enriched,
        nucleus=case.nucleus,
        solvent=case.solvent,
        baseline_score=peak_layer.score,
        drop_peaks=robustness_drop_peaks,
    )
    regulatory_layer = _regulatory_evidence(case=case, observed_enriched=observed_enriched)

    layers = [
        peak_layer,
        structural_layer,
        explain_layer,
        robust_layer,
        regulatory_layer,
    ]
    overall = round(
        sum(LAYER_WEIGHTS[layer.name] * layer.score for layer in layers),
        4,
    )

    summary = [
        f"Overall {overall:.0%} across 5 layers.",
        f"Peak-level accuracy: {peak_layer.score:.0%}.",
        f"Structural ranking: {structural_layer.score:.0%}.",
        f"Explainability: {explain_layer.score:.0%}.",
        f"Robustness (drop {robustness_drop_peaks}): {robust_layer.score:.0%}.",
        f"Regulatory evidence: {regulatory_layer.score:.0%}.",
    ]

    return BenchmarkCaseResult(
        case_id=case.case_id,
        smiles=case.smiles,
        nucleus=case.nucleus,
        solvent=case.solvent,
        overall_score=overall,
        layers=layers,
        summary=summary,
        warnings=warnings,
    )


def evaluate_suite(
    cases: list[BenchmarkCase], *, robustness_drop_peaks: int = 1
) -> BenchmarkRunResponse:
    results = [
        evaluate_case(case, robustness_drop_peaks=robustness_drop_peaks)
        for case in cases
    ]
    aggregates: list[BenchmarkAggregate] = []
    for layer_name in LAYER_WEIGHTS:
        scores = [
            layer.score
            for result in results
            for layer in result.layers
            if layer.name == layer_name
        ]
        if not scores:
            continue
        aggregates.append(
            BenchmarkAggregate(
                layer=layer_name,  # type: ignore[arg-type]
                mean_score=round(mean(scores), 4),
                case_count=len(scores),
                min_score=round(min(scores), 4),
                max_score=round(max(scores), 4),
            )
        )

    overall_mean = round(
        mean([result.overall_score for result in results]) if results else 0.0,
        4,
    )
    notes: list[str] = []
    if not results:
        notes.append("No cases to evaluate.")
    weak_layer = min(aggregates, key=lambda a: a.mean_score, default=None)
    if weak_layer is not None and weak_layer.mean_score < 0.6:
        notes.append(
            f"Weakest layer: {weak_layer.layer} (mean {weak_layer.mean_score:.0%})."
        )

    return BenchmarkRunResponse(
        case_count=len(results),
        overall_mean_score=overall_mean,
        aggregates=aggregates,
        cases=results,
        notes=notes,
    )


__all__ = [
    "LAYER_WEIGHTS",
    "evaluate_case",
    "evaluate_suite",
]
