"""Repho R13 — retrosynthesis (AiZynthFinder MCTS) with frozen green/safety route overlays.

The division of labour is the Phase-C contract in miniature: the **ML proposes route trees; the
frozen Phase-A engines judge them**. Every molecule on a proposed route — target, intermediates,
starting materials — is screened by the R6 structural safety engine (fail-safe: an unparseable
structure is *unknown → requires review*, never silently clear), every step gets a Trost atom
economy, and step solvents are scored against the R1 CHEM21 greenness table. The route score is a
transparent weighted combination with every component exposed; it is **advisory decision support**
and requires human review — the engine ranks options, a chemist picks the route.

AiZynthFinder is a site-installed guest behind ``MOLTRACE_REACTION_RETRO`` (probed via
:mod:`nmrcheck.reaction_ml`, never imported at module load). There is no lightweight
retrosynthesis fallback — absent the extra, the capability reports *unavailable* plainly. The
mapper from AiZynthFinder's route dict shape into :class:`RouteNode` is a frozen, unit-tested
contract of this module; the live search call is a thin guarded adapter.

Route visualisation exports deterministic Mermaid; reproduction checks use a simple, documented
depth-wise topological similarity (canonical-SMILES multiset Jaccard, depth-weighted).

Pure: no DB / HTTP / clock / randomness; RDKit lazy (as in the R6 engine it reuses).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import reaction_ml, reaction_safety
from .reaction_green import _solvent_greenness, greenness_from_she  # noqa: F401  (one CHEM21 table)

ENGINE = "reaction_retro.v1"

ROUTE_DISCLAIMER = (
    "Retrosynthesis routes are machine proposals scored by the frozen safety and green-chemistry "
    "engines. Scores are advisory decision support: they rank options for review and are never a "
    "safety determination or a synthesis instruction. A qualified chemist must review every route."
)

# Mirrors reaction_safety's full severity vocabulary (low < medium < high < critical). An
# unrecognised or unknown severity ranks ABOVE critical so a route can never score as milder than
# what was actually screened, and scores 0 so it cannot inflate the route score.
_RISK_SCORE = {"low": 80.0, "medium": 40.0, "high": 10.0, "critical": 0.0, "unknown": 0.0}
_RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3, "unknown": 4}


class ReactionRetroError(Exception):
    """Raised on a malformed route tree or a failed adapter call."""


# --------------------------------------------------------------------------- #
# Route representation.
# --------------------------------------------------------------------------- #
@dataclass
class RouteNode:
    """A molecule in a route tree; ``children`` are its retrosynthetic precursors."""

    smiles: str
    children: list[RouteNode] = field(default_factory=list)
    reagents: list[str] = field(default_factory=list)
    solvent: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "smiles": self.smiles,
            "children": [child.as_dict() for child in self.children],
            "reagents": list(self.reagents),
            "solvent": self.solvent,
        }


def route_from_dict(payload: Mapping[str, Any]) -> RouteNode:
    """Parse a route tree from our canonical dict shape (inverse of :meth:`RouteNode.as_dict`)."""

    smiles = str(payload.get("smiles") or "")
    if not smiles:
        raise ReactionRetroError("Route node has no SMILES.")
    children_raw = payload.get("children") or []
    if not isinstance(children_raw, Sequence) or isinstance(children_raw, (str, bytes)):
        raise ReactionRetroError("Route node children must be a list.")
    return RouteNode(
        smiles=smiles,
        children=[route_from_dict(child) for child in children_raw],
        reagents=[str(r) for r in payload.get("reagents") or []],
        solvent=(str(payload["solvent"]) if payload.get("solvent") else None),
    )


def route_from_aizynth_dict(payload: Mapping[str, Any]) -> RouteNode:
    """Map AiZynthFinder's route dict (``type: mol`` / ``type: reaction`` alternation) to ours.

    AiZynth trees alternate molecule nodes and reaction nodes; a molecule's precursors are the
    children of its child reaction node(s). This mapper is the frozen contract this module owns —
    unit-tested against the documented shape, independent of the live package.
    """

    if payload.get("type") != "mol":
        raise ReactionRetroError("AiZynth route root must be a 'mol' node.")

    def _map_mol(node: Mapping[str, Any]) -> RouteNode:
        smiles = str(node.get("smiles") or "")
        if not smiles:
            raise ReactionRetroError("AiZynth mol node has no SMILES.")
        precursors: list[RouteNode] = []
        for reaction in node.get("children") or []:
            if reaction.get("type") != "reaction":
                raise ReactionRetroError("AiZynth mol children must be 'reaction' nodes.")
            for child in reaction.get("children") or []:
                if child.get("type") != "mol":
                    raise ReactionRetroError("AiZynth reaction children must be 'mol' nodes.")
                precursors.append(_map_mol(child))
        return RouteNode(smiles=smiles, children=precursors)

    return _map_mol(payload)


def _walk(node: RouteNode, depth: int = 0):
    yield node, depth
    for child in node.children:
        yield from _walk(child, depth + 1)


# --------------------------------------------------------------------------- #
# Frozen overlays: R6 safety per molecule, Trost AE per step, CHEM21 solvent greenness.
# --------------------------------------------------------------------------- #
def _load_rdkit_descriptors():
    try:
        from rdkit import Chem  # noqa: PLC0415
        from rdkit.Chem import Descriptors  # noqa: PLC0415

        return Chem, Descriptors
    except ImportError:
        return None, None


def _mol_weight(smiles: str) -> float | None:
    chem, descriptors = _load_rdkit_descriptors()
    if chem is None:
        return None
    mol = chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return float(descriptors.MolWt(mol))


def _risk_rank(risk: str) -> int:
    # An unrecognised severity is treated as maximally severe, never dropped or downgraded.
    return _RISK_RANK.get(risk, _RISK_RANK["unknown"])


def _worst_risk(risks: Sequence[str]) -> str:
    if not risks:
        return "unknown"  # nothing screened is not the same as nothing found
    return max(risks, key=_risk_rank)


def score_route(route: RouteNode) -> dict[str, Any]:
    """Score a proposed route with the frozen engines — every component exposed, advisory only."""

    nodes = list(_walk(route))
    if not nodes:
        raise ReactionRetroError("Empty route.")

    # R6 structural safety on EVERY molecule on the route — targets, intermediates, starting
    # materials AND reagents. A hazardous reagent is as much a process-safety fact as a hazardous
    # intermediate, so it is screened rather than assumed benign.
    safety_screens: list[dict[str, Any]] = []
    for node, depth in nodes:
        for smiles, role in [(node.smiles, "molecule")] + [
            (reagent, "reagent") for reagent in node.reagents
        ]:
            screen = reaction_safety.screen_smiles(smiles)
            safety_screens.append(
                {
                    "smiles": smiles,
                    "role": role,
                    "depth": depth,
                    "overall_risk": screen["overall_risk"],
                    "requires_expert_review": screen["requires_expert_review"],
                    "flagged_groups": [g.get("key") for g in screen.get("flagged_groups", [])],
                }
            )
    worst = _worst_risk([s["overall_risk"] for s in safety_screens])
    requires_review = True  # routes ALWAYS require human review; safety can only add urgency.
    safety_score = _RISK_SCORE.get(worst, 0.0)

    # Trost atom economy per step (product MW / Σ precursor+reagent MW).
    step_details: list[dict[str, Any]] = []
    warnings: list[str] = []
    atom_economies: list[float] = []
    solvent_scores: list[float] = []
    for node, depth in nodes:
        if not node.children:
            continue
        product_mw = _mol_weight(node.smiles)
        input_mws = [_mol_weight(child.smiles) for child in node.children]
        reagent_mws = [_mol_weight(reagent) for reagent in node.reagents]
        atom_economy: float | None = None
        # An unweighable REAGENT would shrink the denominator and inflate atom economy, so a
        # missing mass anywhere refuses the calculation rather than quietly reporting a better
        # number than the chemistry supports.
        if (
            product_mw is None
            or any(mw is None for mw in input_mws)
            or any(mw is None for mw in reagent_mws)
        ):
            warnings.append(
                f"Atom economy unavailable at depth {depth} (unparseable structure or no RDKit); "
                "the step is excluded rather than scored on a partial mass balance."
            )
        else:
            total_in = sum(input_mws) + sum(reagent_mws)
            if total_in > 0:
                raw = 100.0 * product_mw / total_in
                if raw > 100.0:
                    # >100% is mass-balance-impossible: surface it, never clamp it to perfect.
                    warnings.append(
                        f"Atom economy at depth {depth} computed as {raw:.1f}% (>100%): the step's "
                        "mass balance is impossible; excluded from the score pending review."
                    )
                else:
                    atom_economy = raw
                    atom_economies.append(atom_economy)
        solvent_green: float | None = None
        if node.solvent:
            solvent_green = _solvent_greenness(node.solvent, {})
            if solvent_green is None:
                warnings.append(f"Solvent {node.solvent!r} is not in the CHEM21 table.")
            else:
                solvent_scores.append(solvent_green)
        step_details.append(
            {
                "product_smiles": node.smiles,
                "depth": depth,
                "precursors": [child.smiles for child in node.children],
                "reagents": list(node.reagents),
                "solvent": node.solvent,
                "atom_economy_percent": atom_economy,
                "solvent_greenness": solvent_green,
            }
        )

    step_count = len(step_details)
    max_depth = max(depth for _, depth in nodes)
    leaves = sum(1 for node, _ in nodes if not node.children)

    mean_ae = sum(atom_economies) / len(atom_economies) if atom_economies else None
    mean_solvent = sum(solvent_scores) / len(solvent_scores) if solvent_scores else None
    brevity = 100.0 / (1.0 + max(0, step_count - 1))

    # Transparent weighted combination; components without data are EXCLUDED (weights renormalised)
    # and named in the warnings — never silently imputed.
    components: dict[str, tuple[float, float]] = {"safety": (0.4, safety_score)}
    if mean_ae is not None:
        components["atom_economy"] = (0.3, mean_ae)
    else:
        warnings.append("Route score excludes atom economy (no computable steps).")
    if mean_solvent is not None:
        components["solvent_greenness"] = (0.2, mean_solvent)
    else:
        warnings.append("Route score excludes solvent greenness (no scored solvents).")
    components["brevity"] = (0.1, brevity)
    total_weight = sum(weight for weight, _ in components.values())
    route_score = sum(weight * value for weight, value in components.values()) / total_weight

    return {
        "route_score": round(route_score, 3),
        "score_components": {
            name: {"weight": weight, "value": value} for name, (weight, value) in components.items()
        },
        "safety": {
            "worst_risk": worst,
            "screens": safety_screens,
            "requires_expert_review": requires_review,
        },
        "steps": step_details,
        "step_count": step_count,
        "max_depth": max_depth,
        "starting_materials": leaves,
        "mean_atom_economy_percent": mean_ae,
        "mean_solvent_greenness": mean_solvent,
        "warnings": warnings,
        "human_review_required": True,
        "disclaimer": ROUTE_DISCLAIMER,
        "engine": ENGINE,
    }


# --------------------------------------------------------------------------- #
# Deterministic Mermaid export.
# --------------------------------------------------------------------------- #
def to_mermaid(route: RouteNode) -> str:
    """Deterministic Mermaid flowchart (precursors point at their product)."""

    lines = ["graph TD"]
    labels: list[str] = []
    edges: list[tuple[int, int]] = []

    def _visit(node: RouteNode) -> int:
        index = len(labels)
        labels.append(node.smiles.replace('"', "'"))
        for child in node.children:
            child_index = _visit(child)
            edges.append((child_index, index))
        return index

    _visit(route)
    for index, label in enumerate(labels):
        lines.append(f'    n{index}["{label}"]')
    for src, dst in edges:
        lines.append(f"    n{src} --> n{dst}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Reproduction check: simple, documented topological similarity.
# --------------------------------------------------------------------------- #
def _canonical(smiles: str) -> str:
    chem, _ = _load_rdkit_descriptors()
    if chem is None:
        return smiles
    mol = chem.MolFromSmiles(smiles)
    return smiles if mol is None else chem.MolToSmiles(mol)


def route_similarity(a: RouteNode, b: RouteNode) -> float:
    """Depth-weighted Jaccard over canonical-SMILES multisets per depth, in [0, 1].

    A deliberately simple, deterministic topological similarity for validating proposed routes
    against published ones — not a graph-edit distance, and documented as such.
    """

    def _levels(route: RouteNode) -> dict[int, dict[str, int]]:
        levels: dict[int, dict[str, int]] = {}
        for node, depth in _walk(route):
            bucket = levels.setdefault(depth, {})
            key = _canonical(node.smiles)
            bucket[key] = bucket.get(key, 0) + 1
        return levels

    levels_a, levels_b = _levels(a), _levels(b)
    depths = sorted(set(levels_a) | set(levels_b))
    numerator = 0.0
    denominator = 0.0
    for depth in depths:
        weight = 1.0 / (1.0 + depth)
        bucket_a = levels_a.get(depth, {})
        bucket_b = levels_b.get(depth, {})
        keys = set(bucket_a) | set(bucket_b)
        intersection = sum(min(bucket_a.get(k, 0), bucket_b.get(k, 0)) for k in keys)
        union = sum(max(bucket_a.get(k, 0), bucket_b.get(k, 0)) for k in keys)
        if union:
            numerator += weight * (intersection / union)
            denominator += weight
    return numerator / denominator if denominator else 0.0


# --------------------------------------------------------------------------- #
# The AiZynthFinder guest adapter (probed; never imported at module load).
# --------------------------------------------------------------------------- #
def propose_routes(
    target_smiles: str,
    *,
    config_path: str,
    n_routes: int = 5,
    probe: Callable[[str], bool] | None = None,
    env: Mapping[str, str] | None = None,
    _search: Callable[[str, str, int], list[Mapping[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Propose + score up to ``n_routes`` retrosynthetic routes for ``target_smiles``.

    Requires the ``retrosynthesis`` capability (flag + aizynthfinder). ``_search`` is the
    injectable live-search seam (tests drive the mapper + scoring through a fake); the default
    performs the real AiZynthFinder expansion.
    """

    status = reaction_ml.require_capability("retrosynthesis", probe=probe, env=env)
    search = _search or _aizynth_search
    try:
        raw_routes = search(target_smiles, config_path, n_routes)
    except reaction_ml.CapabilityUnavailableError:
        raise
    except Exception as exc:
        raise ReactionRetroError(f"AiZynthFinder search failed: {exc}") from exc

    scored: list[dict[str, Any]] = []
    for raw in raw_routes[:n_routes]:
        route = route_from_aizynth_dict(raw)
        report = score_route(route)
        scored.append(
            {
                "route": route.as_dict(),
                "mermaid": to_mermaid(route),
                "score": report,
                "capability_provenance": status.as_dict(),
            }
        )
    scored.sort(key=lambda item: -item["score"]["route_score"])
    return scored


def _aizynth_search(
    target_smiles: str, config_path: str, n_routes: int
) -> list[Mapping[str, Any]]:  # pragma: no cover - requires the site-installed extra
    from aizynthfinder.aizynthfinder import AiZynthFinder  # noqa: PLC0415

    finder = AiZynthFinder(configfile=config_path)
    finder.target_smiles = target_smiles
    finder.tree_search()
    finder.build_routes()
    return list(finder.routes.dicts)[:n_routes]
