"""Bridge recovered multiplet J couplings into candidate confidence.

This is the multiplet -> unified-confidence evidence layer.  Given the J
couplings recovered by the Prompt 4 multiplet analyser
(``POST /spectrum/analyze/multiplets``) and a set of candidate structures, it
scores how well each candidate's *topology-predicted* coupling set (from
``jcoupling_prediction.predict_proton_couplings_from_smiles``) agrees with the
observed couplings.

Scoring uses the house :func:`greedy_set_similarity` Gaussian-kernel matcher
(the same primitive used for NMR shift matching).  A candidate is flagged with
a contradiction when the observed spectrum carries a large coupling (>= the
contradiction threshold, e.g. a ~16 Hz trans-alkene) that the candidate's
topology cannot produce — the matcher leaves it in ``unmatched_observed``.

Like the LC-MS feature-family bridge, this layer is intentionally
conservative: J agreement is supporting evidence, not a standalone
identification, and it never releases anything without human review.
"""

from __future__ import annotations

from .evidence import greedy_set_similarity
from .jcoupling_prediction import predict_proton_couplings_from_smiles
from .models import (
    CandidateInput,
    JCouplingMatch,
    MultipletJCouplingBridgeRequest,
    MultipletJCouplingBridgeResult,
    MultipletJCouplingCandidateMatch,
)

# Observed couplings within this window (Hz) are merged into one representative.
# Mutual couplings (J_AB appears in both partner multiplets) and peak-pick
# jitter would otherwise inflate the matching denominator with near-duplicates.
_OBSERVED_COMPACTION_HZ = 0.6
# When a candidate contradicts the observed couplings, cap its layer score so a
# few coincidental matches cannot rank it highly (mirrors the LC-MS bridge).
_CONTRADICTION_SCORE_CAP = 0.25


class MultipletJCouplingBridgeError(ValueError):
    """Raised when observed multiplet couplings cannot be bridged to candidates."""


def _candidate_key(smiles: str) -> str:
    return " ".join(str(smiles or "").strip().split())


def _candidate_formula(candidate: CandidateInput) -> str | None:
    try:
        from .hrms import formula_from_smiles

        return formula_from_smiles(candidate.smiles).formula
    except Exception:
        try:
            from .chemistry import structure_summary_from_smiles

            return structure_summary_from_smiles(candidate.smiles).formula
        except Exception:
            return None


def _compact_couplings(values: list[float], tolerance: float) -> list[float]:
    if not values:
        return []
    ordered = sorted(float(v) for v in values)
    clusters: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - clusters[-1][-1] <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    means = [round(sum(cluster) / len(cluster), 2) for cluster in clusters]
    return sorted(means, reverse=True)


def collect_observed_couplings(req: MultipletJCouplingBridgeRequest) -> tuple[list[float], int]:
    """Merge + compact the observed couplings supplied to the bridge.

    Returns ``(compacted_couplings_desc, raw_count)``.  Couplings are pulled
    from ``observed_multiplets[*].j_couplings_hz`` and ``observed_j_couplings_hz``,
    filtered to ``>= min_observed_hz``, then single-linkage compacted so mutual
    couplings and peak-pick jitter do not double-count.
    """
    raw: list[float] = []
    if req.observed_multiplets:
        for multiplet in req.observed_multiplets:
            raw.extend(float(j) for j in (multiplet.j_couplings_hz or []))
    if req.observed_j_couplings_hz:
        raw.extend(float(j) for j in req.observed_j_couplings_hz)
    filtered = [j for j in raw if j >= req.min_observed_hz]
    return _compact_couplings(filtered, _OBSERVED_COMPACTION_HZ), len(filtered)


def _agreement_label(score: float) -> str:
    if score >= 0.72:
        return "strong_j_agreement"
    if score >= 0.5:
        return "partial_j_agreement"
    if score >= 0.3:
        return "weak_j_agreement"
    return "poor_j_agreement"


def _score_candidate(
    candidate: CandidateInput,
    observed: list[float],
    *,
    req: MultipletJCouplingBridgeRequest,
) -> MultipletJCouplingCandidateMatch:
    key = _candidate_key(candidate.smiles)
    predicted = predict_proton_couplings_from_smiles(
        candidate.smiles,
        use_karplus=req.use_karplus,
        karplus_method=req.karplus_method,
        karplus_max_conformers=req.karplus_max_conformers,
        karplus_conformer_weighting=req.karplus_conformer_weighting,
    )
    max_observed = max(observed) if observed else None

    if predicted.invalid_structure:
        return MultipletJCouplingCandidateMatch(
            rank=0,
            name=candidate.name,
            role=candidate.role,
            smiles=candidate.smiles,
            formula=None,
            predicted_j_couplings_hz=[],
            observed_j_couplings_hz=observed,
            matched_pairs=[],
            matched_count=0,
            unmatched_observed_hz=observed,
            unmatched_predicted_hz=[],
            max_observed_j_hz=max_observed,
            max_predicted_j_hz=None,
            score=0.0,
            label="candidate_invalid",
            contradiction=True,
            evidence_summary=["Candidate SMILES could not be parsed for J-coupling prediction."],
            warnings=list(predicted.warnings),
            metadata={"candidate_key": key},
        )

    formula = _candidate_formula(candidate)
    predicted_hz = list(predicted.couplings_hz)
    max_predicted = predicted.max_predicted_hz or None

    if not observed:
        return MultipletJCouplingCandidateMatch(
            rank=0,
            name=candidate.name,
            role=candidate.role,
            smiles=candidate.smiles,
            formula=formula,
            predicted_j_couplings_hz=predicted_hz,
            observed_j_couplings_hz=[],
            matched_pairs=[],
            matched_count=0,
            unmatched_observed_hz=[],
            unmatched_predicted_hz=predicted_hz,
            max_observed_j_hz=None,
            max_predicted_j_hz=max_predicted,
            score=0.0,
            label="no_observed_couplings",
            contradiction=False,
            evidence_summary=[
                "No observed J couplings were supplied; the candidate's predicted "
                f"couplings ({', '.join(f'{j:.1f}' for j in predicted_hz) or 'none'} Hz) "
                "could not be scored.",
            ],
            warnings=[],
            metadata={"candidate_key": key},
        )

    if not predicted_hz:
        contradiction = any(j >= req.contradiction_j_hz for j in observed)
        summary = [
            "Candidate topology predicts no diagnostic 1H-1H couplings "
            "(no adjacent protonated carbons, alkene, or aromatic CH-CH), "
            f"but {len(observed)} observed coupling(s) were supplied.",
        ]
        if contradiction:
            big = [j for j in observed if j >= req.contradiction_j_hz]
            summary.append(
                f"Observed coupling(s) {', '.join(f'{j:.1f}' for j in big)} Hz cannot be "
                "produced by this structure."
            )
        return MultipletJCouplingCandidateMatch(
            rank=0,
            name=candidate.name,
            role=candidate.role,
            smiles=candidate.smiles,
            formula=formula,
            predicted_j_couplings_hz=[],
            observed_j_couplings_hz=observed,
            matched_pairs=[],
            matched_count=0,
            unmatched_observed_hz=observed,
            unmatched_predicted_hz=[],
            max_observed_j_hz=max_observed,
            max_predicted_j_hz=None,
            score=0.0,
            label="no_predicted_couplings",
            contradiction=contradiction,
            evidence_summary=summary,
            warnings=list(predicted.warnings),
            metadata={"candidate_key": key},
        )

    similarity, matches, unmatched_observed, unmatched_predicted = greedy_set_similarity(
        observed, predicted_hz, sigma=req.sigma_hz
    )
    contradiction_couplings = [j for j in unmatched_observed if j >= req.contradiction_j_hz]
    contradiction = bool(contradiction_couplings)
    score = min(similarity, _CONTRADICTION_SCORE_CAP) if contradiction else similarity
    label = "j_coupling_contradiction" if contradiction else _agreement_label(similarity)

    matched_pairs = [
        JCouplingMatch(
            observed_hz=round(match.observed_ppm, 3),
            predicted_hz=round(match.expected_ppm, 3),
            delta_hz=round(match.delta_ppm, 3),
            score=round(match.score, 4),
        )
        for match in matches
    ]

    summary = [
        f"Observed J set [{', '.join(f'{j:.1f}' for j in observed)}] Hz matched against "
        f"predicted [{', '.join(f'{j:.1f}' for j in predicted_hz)}] Hz "
        f"({len(matched_pairs)}/{len(observed)} couplings within ~{req.sigma_hz:.1f} Hz; "
        f"similarity {similarity:.3f}).",
    ]
    if contradiction:
        summary.append(
            "Observed coupling(s) "
            f"{', '.join(f'{j:.1f}' for j in contradiction_couplings)} Hz exceed what this "
            f"structure can produce (max predicted {max_predicted:.1f} Hz); review before ranking."
        )
    elif unmatched_observed:
        summary.append(
            "Unmatched observed coupling(s): "
            f"{', '.join(f'{j:.1f}' for j in unmatched_observed)} Hz."
        )

    return MultipletJCouplingCandidateMatch(
        rank=0,
        name=candidate.name,
        role=candidate.role,
        smiles=candidate.smiles,
        formula=formula,
        predicted_j_couplings_hz=predicted_hz,
        observed_j_couplings_hz=observed,
        matched_pairs=matched_pairs,
        matched_count=len(matched_pairs),
        unmatched_observed_hz=[round(j, 3) for j in unmatched_observed],
        unmatched_predicted_hz=[round(j, 3) for j in unmatched_predicted],
        max_observed_j_hz=max_observed,
        max_predicted_j_hz=max_predicted,
        score=round(score, 4),
        label=label,  # type: ignore[arg-type]
        contradiction=contradiction,
        evidence_summary=summary,
        warnings=list(predicted.warnings),
        metadata={
            "candidate_key": key,
            "raw_similarity": round(similarity, 4),
            "predicted_category_counts": predicted.category_counts,
            "sigma_hz": req.sigma_hz,
            "contradiction_j_hz": req.contradiction_j_hz,
        },
    )


def _evidence_table(matches: list[MultipletJCouplingCandidateMatch]) -> str:
    lines = [
        "rank,name,smiles,formula,score,label,matched_count,observed_count,"
        "predicted_count,max_observed_hz,max_predicted_hz,contradiction"
    ]
    for match in matches:
        lines.append(
            f"{match.rank},{match.name or ''},{match.smiles},{match.formula or ''},"
            f"{match.score:.4f},{match.label},{match.matched_count},"
            f"{len(match.observed_j_couplings_hz)},{len(match.predicted_j_couplings_hz)},"
            f"{match.max_observed_j_hz if match.max_observed_j_hz is not None else ''},"
            f"{match.max_predicted_j_hz if match.max_predicted_j_hz is not None else ''},"
            f"{str(match.contradiction).lower()}"
        )
    return "\n".join(lines)


def score_multiplets_against_candidates(
    req: MultipletJCouplingBridgeRequest,
) -> MultipletJCouplingBridgeResult:
    """Score recovered observed J couplings against candidate topologies."""
    if not req.candidates:
        raise MultipletJCouplingBridgeError("At least one candidate is required.")

    observed, raw_count = collect_observed_couplings(req)
    matches = [_score_candidate(candidate, observed, req=req) for candidate in req.candidates]
    matches_sorted = sorted(
        matches, key=lambda match: (match.contradiction, -match.score, match.name or match.smiles)
    )
    ranked = [match.model_copy(update={"rank": idx + 1}) for idx, match in enumerate(matches_sorted)]

    warnings: list[str] = []
    if not observed:
        warnings.append(
            "No observed J couplings were available after filtering; candidate J agreement "
            "could not be scored."
        )
    if any(match.contradiction for match in ranked):
        warnings.append(
            "At least one candidate cannot produce a large observed coupling; review the "
            "flagged candidate(s) before ranking."
        )

    if req.use_karplus:
        relation = (
            "Haasnoot-Altona generalized Karplus"
            if req.karplus_method == "haasnoot_altona"
            else "three-term Karplus"
        )
        weighting_note = (
            "Boltzmann-weighted"
            if req.karplus_conformer_weighting == "boltzmann"
            else "unweighted"
        )
        jmethod = (
            f"aliphatic vicinal couplings refined with a {weighting_note} conformer-averaged "
            f"{relation} 3J (opt-in); alkene/aromatic categories use empirical regions"
        )
    else:
        jmethod = "empirical regions, no Karplus/3D"
    notes = [
        "J agreement scores recovered multiplet couplings against topology-predicted "
        f"couplings ({jmethod}); it is supporting evidence, not a standalone "
        "identification.",
        "Predicted couplings cover 6-membered aromatic/N-heteroaromatic ortho & meta, "
        "alkene cis/trans, and aliphatic vicinal couplings.",
        "Human review is required, especially when top candidates are close or a candidate "
        "carries a J-coupling contradiction.",
    ]

    return MultipletJCouplingBridgeResult(
        sample_id=req.sample_id,
        candidate_count=len(ranked),
        observed_coupling_count=len(observed),
        observed_j_couplings_hz=observed,
        sigma_hz=req.sigma_hz,
        contradiction_j_hz=req.contradiction_j_hz,
        best_match=ranked[0] if ranked else None,
        matches=ranked,
        evidence_table_text=_evidence_table(ranked),
        warnings=list(dict.fromkeys(warnings)),
        notes=notes,
        metadata={
            "parser_version": "phase37_multiplet_jcoupling_bridge_v1",
            "raw_observed_coupling_count": raw_count,
            "compacted_observed_coupling_count": len(observed),
            "sigma_hz": req.sigma_hz,
            "contradiction_j_hz": req.contradiction_j_hz,
            "min_observed_hz": req.min_observed_hz,
            "use_karplus": req.use_karplus,
            "karplus_method": req.karplus_method,
            "karplus_conformer_weighting": req.karplus_conformer_weighting,
            "karplus_max_conformers": req.karplus_max_conformers,
            "compound_class": req.compound_class,
        },
    )
