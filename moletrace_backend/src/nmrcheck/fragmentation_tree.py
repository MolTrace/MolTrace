from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from .candidate import parse_candidate_text
from .chemistry import mol_from_smiles
from .exceptions import StructureParseError
from .hrms import formula_from_smiles, normalize_adduct, ppm_error, ppm_score, theoretical_mz
from .msms import (
    MSMSError,
    NEUTRAL_LOSS_RULES,
    _feature_set_for_mol,
    _fragment_hypotheses,
    _loss_plausible,
    _match_peak_to_hypothesis,
    _neutral_loss_hits,
    _normalize_peaks,
    _peak_tolerance,
    parse_msms_peak_text,
)
from .models import (
    CandidateInput,
    MSMSDiagnosticLossEvidence,
    MSMSFragmentationTreeCandidate,
    MSMSFragmentationTreeEdge,
    MSMSFragmentationTreeNode,
    MSMSFragmentationTreeRequest,
    MSMSFragmentationTreeResult,
    MSMSPeak,
)


class MSMSFragmentationTreeError(ValueError):
    pass


@dataclass(frozen=True)
class _LossMatch:
    parent_id: str
    child_id: str
    loss_name: str
    observed_loss_da: float
    expected_loss_da: float
    error_da: float
    ppm_error: float | None
    chemically_plausible: bool
    diagnostic: bool
    explanation: str


def _node_id(index: int) -> str:
    return f"p{index}"


def _diagnostic_class(loss_name: str) -> str:
    mapping = {
        "H2O": "oxygenated / hydroxyl / acid dehydration",
        "NH3": "nitrogenous / amine / amide",
        "CO": "carbonyl / acyl fragmentation",
        "CO2": "carboxyl / ester / carbonate decarboxylation",
        "CH3OH": "methoxy / methyl ester",
        "CH3COOH": "acetate / ester",
        "HCl": "chlorinated structure",
        "HBr": "brominated structure",
        "SO2": "sulfone / sulfonyl / sulfur oxide",
        "H2S": "thiol / reduced sulfur",
        "C2H2O": "ketene / acetate-like loss",
        "C2H4": "alkyl-chain rearrangement",
    }
    return mapping.get(loss_name, "common neutral loss")


def _loss_edges_between_peak_nodes(
    nodes: list[MSMSFragmentationTreeNode],
    *,
    features: set[str] | None,
    mz_tolerance_da: float,
    ppm_tolerance: float,
    max_tree_depth: int,
) -> list[_LossMatch]:
    matches: list[_LossMatch] = []
    seen: set[tuple[str, str, str]] = set()
    sorted_nodes = sorted(nodes, key=lambda node: node.mz, reverse=True)
    for parent in sorted_nodes:
        for child in sorted_nodes:
            if parent.node_id == child.node_id or parent.mz <= child.mz:
                continue
            observed_loss = parent.mz - child.mz
            for rule in NEUTRAL_LOSS_RULES:
                tolerance = _peak_tolerance(rule.mass, mz_tolerance_da=mz_tolerance_da, ppm_tolerance=ppm_tolerance)
                error = observed_loss - rule.mass
                if abs(error) > tolerance:
                    continue
                key = (parent.node_id, child.node_id, rule.name)
                if key in seen:
                    continue
                seen.add(key)
                plausible = _loss_plausible(rule, features)
                explanation = rule.explanation if plausible else f"{rule.explanation}; candidate lacks usual supporting feature(s): {', '.join(rule.requires_any)}."
                matches.append(
                    _LossMatch(
                        parent_id=parent.node_id,
                        child_id=child.node_id,
                        loss_name=rule.name,
                        observed_loss_da=round(observed_loss, 6),
                        expected_loss_da=round(rule.mass, 6),
                        error_da=round(error, 6),
                        ppm_error=round(error / rule.mass * 1_000_000.0, 3) if rule.mass else None,
                        chemically_plausible=plausible,
                        diagnostic=plausible and bool(rule.requires_any),
                        explanation=explanation,
                    )
                )

    by_parent: dict[str, list[_LossMatch]] = defaultdict(list)
    for match in matches:
        by_parent[match.parent_id].append(match)

    kept: list[_LossMatch] = []
    queue: deque[tuple[str, int]] = deque([("precursor", 0)])
    visited_depth: dict[str, int] = {"precursor": 0}
    kept_keys: set[tuple[str, str, str]] = set()
    while queue:
        parent_id, depth = queue.popleft()
        if depth >= max_tree_depth:
            continue
        for edge in by_parent.get(parent_id, []):
            key = (edge.parent_id, edge.child_id, edge.loss_name)
            if key not in kept_keys:
                kept.append(edge)
                kept_keys.add(key)
            next_depth = depth + 1
            if next_depth < visited_depth.get(edge.child_id, 10**9):
                visited_depth[edge.child_id] = next_depth
                queue.append((edge.child_id, next_depth))
    return kept


def _max_depth(edges: list[MSMSFragmentationTreeEdge]) -> int:
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.relation_type in {"neutral_loss", "series_loss", "candidate_fragment_match", "precursor_match"}:
            children_by_parent[edge.parent_id].append(edge.child_id)
    best = 0
    queue: deque[tuple[str, int]] = deque([("precursor", 0)])
    seen: set[tuple[str, int]] = set()
    while queue:
        node_id, depth = queue.popleft()
        best = max(best, depth)
        if depth > 8:
            continue
        for child_id in children_by_parent.get(node_id, []):
            state = (child_id, depth + 1)
            if state in seen:
                continue
            seen.add(state)
            queue.append(state)
    return best


def _label_for_tree(score: float, precursor_score: float, contradiction_count: int, valid: bool) -> str:
    if not valid:
        return "invalid_structure"
    if contradiction_count >= 3 and score < 0.55:
        return "contradictory_fragmentation_tree"
    if score >= 0.72 and precursor_score >= 0.40 and contradiction_count == 0:
        return "strong_fragmentation_tree_support"
    if score >= 0.45 and contradiction_count <= 2:
        return "plausible_fragmentation_tree_support"
    if contradiction_count >= 2:
        return "contradictory_fragmentation_tree"
    return "weak_fragmentation_tree_support"


def _candidate_tree(
    candidate: CandidateInput,
    *,
    peaks: list[MSMSPeak],
    precursor_mz: float,
    adduct_name: str,
    mz_tolerance_da: float,
    ppm_tolerance: float,
    max_tree_depth: int,
    total_relative_intensity: float,
) -> MSMSFragmentationTreeCandidate:
    item_warnings: list[str] = []
    evidence: list[str] = []
    contradiction_flags: list[str] = []
    diagnostic_hits: list[MSMSDiagnosticLossEvidence] = []
    nodes: list[MSMSFragmentationTreeNode] = [
        MSMSFragmentationTreeNode(
            node_id="precursor",
            mz=round(precursor_mz, 6),
            node_type="precursor",
            annotation="Observed precursor ion",
            explained=True,
            evidence_summary=["Root of the fragmentation tree."],
        )
    ]
    for index, peak in enumerate(sorted(peaks, key=lambda peak: peak.mz, reverse=True), start=1):
        nodes.append(
            MSMSFragmentationTreeNode(
                node_id=_node_id(index),
                mz=round(peak.mz, 6),
                intensity=peak.intensity,
                relative_intensity=round(float(peak.relative_intensity or 0.0), 4),
                node_type="observed_peak",
                explained=False,
            )
        )

    valid = True
    formula = None
    precursor_theory = None
    precursor_error = None
    precursor_score = 0.0
    tree_score = 0.0
    explained_fraction = 0.0
    explained_peak_keys: set[float] = set()
    edges: list[MSMSFragmentationTreeEdge] = []

    try:
        adduct = normalize_adduct(adduct_name)
        mol = mol_from_smiles(candidate.smiles)
        formula_info = formula_from_smiles(candidate.smiles)
        formula = formula_info.formula
        features = _feature_set_for_mol(mol, formula_info.element_counts)
        precursor_theory = theoretical_mz(formula_info.exact_mass, adduct)
        precursor_error = ppm_error(precursor_mz, precursor_theory)
        precursor_score = ppm_score(precursor_error, ppm_tolerance)
        if precursor_score < 0.15:
            contradiction_flags.append(f"Precursor exact mass is outside tolerance for {formula}: {precursor_error:+.2f} ppm.")

        loss_edges = _loss_edges_between_peak_nodes(
            nodes,
            features=features,
            mz_tolerance_da=mz_tolerance_da,
            ppm_tolerance=ppm_tolerance,
            max_tree_depth=max_tree_depth,
        )
        for match in loss_edges:
            relation_type = "neutral_loss" if match.parent_id == "precursor" else "series_loss"
            edges.append(
                MSMSFragmentationTreeEdge(
                    parent_id=match.parent_id,
                    child_id=match.child_id,
                    relation_type=relation_type,
                    loss_name=match.loss_name,
                    observed_loss_da=match.observed_loss_da,
                    expected_loss_da=match.expected_loss_da,
                    error_da=match.error_da,
                    ppm_error=match.ppm_error,
                    chemically_plausible=match.chemically_plausible,
                    diagnostic=match.diagnostic,
                    explanation=match.explanation,
                )
            )
            child_node = next((node for node in nodes if node.node_id == match.child_id), None)
            if child_node is None:
                continue
            explained_peak_keys.add(round(child_node.mz, 5))
            if match.diagnostic:
                diagnostic_hits.append(
                    MSMSDiagnosticLossEvidence(
                        loss_name=match.loss_name,
                        fragment_mz=child_node.mz,
                        observed_loss_da=match.observed_loss_da,
                        expected_loss_da=match.expected_loss_da,
                        relative_intensity=round(float(child_node.relative_intensity or 0.0), 4),
                        chemically_plausible=match.chemically_plausible,
                        diagnostic_class=_diagnostic_class(match.loss_name),
                        interpretation=match.explanation,
                    )
                )
            if not match.chemically_plausible:
                contradiction_flags.append(f"{match.loss_name} loss at fragment m/z {child_node.mz:.5f} is not supported by candidate features.")

        hypotheses = _fragment_hypotheses(mol, adduct, precursor_theory, features)
        for node in nodes[1:]:
            peak = MSMSPeak(mz=node.mz, intensity=node.intensity or 0.0, relative_intensity=node.relative_intensity)
            match = _match_peak_to_hypothesis(
                peak,
                hypotheses,
                mz_tolerance_da=mz_tolerance_da,
                ppm_tolerance=ppm_tolerance,
            )
            if match is None:
                continue
            explained_peak_keys.add(round(node.mz, 5))
            relation_type = "precursor_match" if "precursor" in match.fragment_type else "candidate_fragment_match"
            edges.append(
                MSMSFragmentationTreeEdge(
                    parent_id="precursor",
                    child_id=node.node_id,
                    relation_type=relation_type,
                    error_da=round(abs(node.mz - match.theoretical_mz), 6),
                    ppm_error=match.ppm_error,
                    chemically_plausible=True,
                    diagnostic=False,
                    explanation=match.explanation,
                    metadata={"formula": match.formula, "fragment_type": match.fragment_type, "theoretical_mz": match.theoretical_mz},
                )
            )
            node.annotation = match.formula or match.fragment_type
            node.formula = match.formula
            node.explained = True
            node.evidence_summary.append(match.explanation)

        explained_node_ids = {edge.child_id for edge in edges}
        nodes = [node.model_copy(update={"explained": True}) if node.node_id in explained_node_ids else node for node in nodes]

        explained_intensity = sum(float(peak.relative_intensity or 0.0) for peak in peaks if round(peak.mz, 5) in explained_peak_keys)
        explained_fraction = round(max(0.0, min(1.0, explained_intensity / max(total_relative_intensity, 1e-9))), 4)
        depth = _max_depth(edges)
        depth_score = min(1.0, depth / max(1, max_tree_depth))
        diagnostic_score = min(1.0, len(diagnostic_hits) / max(1, len([edge for edge in edges if edge.loss_name])))
        fragment_match_score = min(1.0, len([edge for edge in edges if edge.relation_type == "candidate_fragment_match"]) / max(1, len(peaks)))
        contradiction_penalty = min(0.45, 0.10 * len(set(contradiction_flags)))
        tree_score = round(
            max(
                0.0,
                min(
                    1.0,
                    0.25 * precursor_score
                    + 0.35 * explained_fraction
                    + 0.18 * depth_score
                    + 0.14 * diagnostic_score
                    + 0.08 * fragment_match_score
                    - contradiction_penalty,
                ),
            ),
            4,
        )

        evidence.append(f"{formula} theoretical {adduct.name} precursor m/z {precursor_theory:.6f}; precursor error {precursor_error:+.2f} ppm.")
        evidence.append(f"Fragmentation tree explains {len(explained_peak_keys)} of {len(peaks)} analyzed peaks and {explained_fraction:.2%} of filtered relative intensity.")
        if diagnostic_hits:
            evidence.append("Diagnostic losses: " + "; ".join(f"{hit.loss_name} ({hit.diagnostic_class})" for hit in diagnostic_hits[:5]) + ".")
        if contradiction_flags:
            evidence.append(f"{len(set(contradiction_flags))} contradiction flag(s) require human review.")
    except StructureParseError as exc:
        valid = False
        item_warnings.append(str(exc))
    except Exception as exc:
        valid = False
        item_warnings.append(f"Fragmentation-tree candidate analysis failed: {exc}")

    unique_edges: list[MSMSFragmentationTreeEdge] = []
    edge_keys: set[tuple[str, str, str, str | None]] = set()
    for edge in edges:
        key = (edge.parent_id, edge.child_id, edge.relation_type, edge.loss_name)
        if key in edge_keys:
            continue
        unique_edges.append(edge)
        edge_keys.add(key)
    edges = unique_edges

    contradiction_flags = sorted(set(contradiction_flags))
    diagnostic_seen: set[tuple[str, float]] = set()
    diagnostic_unique: list[MSMSDiagnosticLossEvidence] = []
    for hit in diagnostic_hits:
        key = (hit.loss_name, round(hit.fragment_mz, 5))
        if key in diagnostic_seen:
            continue
        diagnostic_unique.append(hit)
        diagnostic_seen.add(key)
    diagnostic_hits = diagnostic_unique

    return MSMSFragmentationTreeCandidate(
        rank=0,
        name=candidate.name,
        role=candidate.role,
        smiles=candidate.smiles,
        label=_label_for_tree(tree_score, precursor_score, len(contradiction_flags), valid),
        formula=formula,
        precursor_theoretical_mz=round(precursor_theory, 6) if precursor_theory is not None else None,
        precursor_ppm_error=round(precursor_error, 3) if precursor_error is not None else None,
        precursor_score=round(precursor_score, 4),
        tree_score=tree_score,
        explained_peak_count=len(explained_peak_keys),
        explained_intensity_fraction=explained_fraction,
        diagnostic_loss_count=len(diagnostic_hits),
        contradiction_count=len(contradiction_flags),
        max_tree_depth=_max_depth(edges),
        nodes=nodes[:200],
        edges=edges[:300],
        diagnostic_hits=diagnostic_hits[:100],
        contradiction_flags=contradiction_flags,
        evidence_summary=evidence,
        warnings=item_warnings,
        metadata={"max_tree_depth_requested": max_tree_depth, "analyzed_peak_count": len(peaks)},
    )


def build_msms_fragmentation_tree(request: MSMSFragmentationTreeRequest) -> MSMSFragmentationTreeResult:
    adduct = normalize_adduct(request.adduct)
    warnings: list[str] = []
    if request.ion_mode and adduct.ion_mode != "neutral" and request.ion_mode != adduct.ion_mode:
        warnings.append(f"Requested ion mode {request.ion_mode!r} differs from adduct mode {adduct.ion_mode!r}; adduct mode was used.")

    peaks_input = list(request.peaks or [])
    if request.peak_list_text:
        peaks_input.extend(parse_msms_peak_text(request.peak_list_text))
    if not peaks_input:
        raise MSMSFragmentationTreeError("Provide MS/MS peaks either as 'peaks' or 'peak_list_text'.")

    peaks, raw_peak_count = _normalize_peaks(
        peaks_input,
        min_relative_intensity=request.min_relative_intensity,
        max_peaks=request.max_peaks_to_analyze,
    )
    if not peaks:
        raise MSMSFragmentationTreeError("No MS/MS peaks remain after the relative-intensity filter.")

    global_losses = _neutral_loss_hits(
        peaks,
        precursor_mz=request.precursor_mz,
        mz_tolerance_da=request.mz_tolerance_da,
        ppm_tolerance=request.ppm_tolerance,
        features=None,
    )

    total_relative_intensity = sum(float(peak.relative_intensity or 0.0) for peak in peaks) or 1.0
    ranked = [
        _candidate_tree(
            candidate,
            peaks=peaks,
            precursor_mz=request.precursor_mz,
            adduct_name=request.adduct,
            mz_tolerance_da=request.mz_tolerance_da,
            ppm_tolerance=request.ppm_tolerance,
            max_tree_depth=request.max_tree_depth,
            total_relative_intensity=total_relative_intensity,
        )
        for candidate in request.candidates
    ]

    ranked_raw = sorted(
        ranked,
        key=lambda item: (item.tree_score, item.precursor_score, item.explained_intensity_fraction, -item.contradiction_count),
        reverse=True,
    )
    ranked_final = [item.model_copy(update={"rank": index + 1}) for index, item in enumerate(ranked_raw)]
    best = ranked_final[0] if ranked_final else None

    return MSMSFragmentationTreeResult(
        sample_id=request.sample_id,
        precursor_mz=request.precursor_mz,
        adduct=adduct,
        mz_tolerance_da=request.mz_tolerance_da,
        ppm_tolerance=request.ppm_tolerance,
        peak_count=raw_peak_count,
        analyzed_peak_count=len(peaks),
        candidate_count=len(ranked_final),
        best_candidate=best,
        ranked_candidates=ranked_final,
        global_neutral_loss_hits=global_losses[:100],
        warnings=warnings,
        notes=[
            "Fragmentation-tree reasoning links precursor, fragment, and subfragment peaks by diagnostic neutral losses and candidate-specific fragment hypotheses.",
            "This layer is an interpretable scoring and triage engine. It does not prove final structure or stereochemistry and should be reviewed with NMR, HRMS, adduct/isotope inference, and expert judgment.",
            "The current implementation uses processed centroid peak tables. Use the LC-MS/MS import bridge to extract peak-list views from mzML/mzXML or source files; collision-energy series, chromatographic deconvolution, and proprietary vendor parsing remain future modules.",
        ],
        metadata={
            "min_relative_intensity": request.min_relative_intensity,
            "max_peaks_to_analyze": request.max_peaks_to_analyze,
            "max_tree_depth": request.max_tree_depth,
            "global_neutral_loss_count": len(global_losses),
        },
    )


def parse_candidate_text_for_fragmentation_tree(text: str) -> list[CandidateInput]:
    return parse_candidate_text(text or "")
