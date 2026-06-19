"""Predictive process-safety screening for the Repho reaction optimizer (R6, engine slice).

Structural screening for energetic / reactive functional groups via RDKit SMARTS, with a
conservative risk tier and an always-on expert-review gate. Decision-support ONLY — never
the sole basis for a safety decision; anything flagged medium or above (and any energetic
group) requires a qualified process-safety professional and a formal Process Hazard
Analysis (PHA) before execution.

The hazard motifs below are well-known explosophore / reactive classes encoded from public
GHS and structural-chemistry knowledge — NOT the copyrighted Bretherick's compiled dataset.
Quantitative predictions (exothermicity, gas evolution, DSC onset) are deliberately out of
this slice; they require thermochemical data and land in a follow-up. Pure RDKit/stdlib, no
ORM/HTTP imports, deterministic.
"""

from __future__ import annotations

from typing import Any

_DISCLAIMER = (
    "Decision-support only; NOT a safety determination and never the sole basis for one. "
    "Any reaction flagged medium or above, and any energetic or reactive group, requires "
    "review by a qualified process-safety professional and a formal Process Hazard Analysis "
    "(PHA) before execution."
)
_SCREEN_VERSION = "reaction_safety.v1"

# (key, label, SMARTS, severity, mitigation note). Severity in {critical, high, medium}.
_ENERGETIC_GROUPS: tuple[tuple[str, str, str, str, str], ...] = (
    ("azide", "Organic azide", "[NX2,NX1]=[N+]=[N-]", "critical",
     "Shock/heat/friction-sensitive; avoid heavy-metal contact; keep dilute and cold."),
    ("organic_peroxide", "Organic peroxide / hydroperoxide", "[OX2][OX2]", "critical",
     "Peroxide-forming/explosive; test for peroxides, avoid concentration to dryness."),
    ("peroxy_acid", "Peroxy acid", "[CX3](=[OX1])[OX2][OX2H1,OX2H0]", "critical",
     "Strong oxidizer, shock/heat-sensitive; keep cold and dilute."),
    ("diazo", "Diazo compound", "[CX3,CX2]=[N+]=[N-]", "critical",
     "Highly energetic and toxic; generate in situ, keep cold, avoid accumulation."),
    ("diazonium", "Diazonium salt", "[#6]-[NX2+]#[NX1]", "critical",
     "Explosive when dry; keep in solution, cold, never isolate dry."),
    ("nitrate_ester", "Nitrate ester", "[#6][OX2][NX3+](=[OX1])[O-]", "critical",
     "Explosive; avoid heat, shock, and acid."),
    ("perchlorate", "Perchlorate", "[Cl](=O)(=O)(=O)[O-,OX2H1,OX2]", "critical",
     "Strong oxidizer; explosive with organics/heavy metals."),
    ("fulminate", "Fulminate", "[C-]#[N+][O-]", "critical",
     "Primary explosive; extreme shock sensitivity."),
    ("nitro", "Nitro group", "[$([NX3](=O)=O),$([NX3+](=O)[O-])]", "high",
     "Energetic, especially poly-nitro / electron-poor arenes; assess thermal stability."),
    ("nitroso", "Nitroso / N-nitroso", "[#6,#7][NX2]=[OX1]", "high",
     "Reactive and frequently mutagenic (cf. nitrosamine control); minimize and contain."),
    ("azo", "Azo compound", "[#6][NX2]=[NX2][#6]", "high",
     "Gas-evolving (N2) on decomposition; can be energetic — control temperature."),
    ("tetrazole", "Tetrazole", "[$(c1nnnn1),$(C1=NN=NN1),$([NX3]1[NX2]=[NX2][NX2]=[CX3]1)]", "high",
     "High nitrogen content; energetic, particularly when substituted with other explosophores."),
    ("n_oxide", "Amine N-oxide", "[$([NX4+][OX1-]),$([nX3+][OX1-])]", "medium",
     "Can be a peroxide/oxidant source; assess thermal stability on scale."),
    ("hydrazine", "Hydrazine / hydrazide", "[NX3;!$(N=*)][NX3;!$(N=*)]", "medium",
     "Reducing and potentially energetic/toxic; handle with engineering controls."),
)

_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _load_rdkit():
    try:
        from rdkit import Chem  # noqa: PLC0415

        return Chem
    except Exception:  # pragma: no cover - rdkit is a hard dependency
        return None


def _compiled_groups(chem) -> list[tuple[str, str, str, str, str, Any]]:
    compiled = []
    for key, label, smarts, severity, note in _ENERGETIC_GROUPS:
        pattern = chem.MolFromSmarts(smarts)
        if pattern is not None:
            compiled.append((key, label, smarts, severity, note, pattern))
    return compiled


def _worst(severities: list[str]) -> str:
    if not severities:
        return "low"
    return max(severities, key=lambda s: _RANK.get(s, 0))


def screen_smiles(smiles: str | None) -> dict[str, Any]:
    """Screen one structure for energetic/reactive groups.

    Returns ``{smiles, parsed, flagged_groups[], overall_risk, requires_expert_review,
    disclaimer, screen_version}``. A missing/unparseable SMILES yields ``parsed=False`` and
    ``requires_expert_review=True`` (fail safe — never silently 'clear' an unknown structure).
    """
    chem = _load_rdkit()
    if not smiles or chem is None:
        return {
            "smiles": smiles,
            "parsed": False,
            "flagged_groups": [],
            "overall_risk": "unknown",
            "requires_expert_review": True,
            "disclaimer": _DISCLAIMER,
            "screen_version": _SCREEN_VERSION,
        }
    mol = chem.MolFromSmiles(smiles)
    if mol is None:
        return {
            "smiles": smiles,
            "parsed": False,
            "flagged_groups": [],
            "overall_risk": "unknown",
            "requires_expert_review": True,
            "disclaimer": _DISCLAIMER,
            "screen_version": _SCREEN_VERSION,
        }
    flagged: list[dict[str, Any]] = []
    for key, label, _smarts, severity, note, pattern in _compiled_groups(chem):
        matches = mol.GetSubstructMatches(pattern)
        if matches:
            flagged.append(
                {
                    "key": key,
                    "label": label,
                    "severity": severity,
                    "count": len(matches),
                    "mitigation": note,
                }
            )
    # Escalation: multiple independent nitro groups (poly-nitro) are notably more energetic.
    nitro = next((f for f in flagged if f["key"] == "nitro"), None)
    if nitro is not None and nitro["count"] >= 2:
        nitro["severity"] = "critical"
        nitro["mitigation"] = "Poly-nitro motif — treat as high-energy; mandatory PHA before use."
    overall = _worst([f["severity"] for f in flagged])
    return {
        "smiles": smiles,
        "parsed": True,
        "flagged_groups": flagged,
        "overall_risk": overall,
        "requires_expert_review": overall != "low",
        "disclaimer": _DISCLAIMER,
        "screen_version": _SCREEN_VERSION,
    }


def screen_reaction(
    *,
    reactant_smiles: list[str] | None = None,
    product_smiles: str | None = None,
    reagent_smiles: list[str] | None = None,
) -> dict[str, Any]:
    """Screen every species in a reaction and aggregate to an overall verdict.

    ``overall_risk`` is the worst across species; ``requires_expert_review`` is True if any
    species is flagged, any SMILES fails to parse, or no structures were provided (fail safe).
    """
    species: list[dict[str, Any]] = []

    def _add(role: str, smiles: str) -> None:
        result = screen_smiles(smiles)
        result["role"] = role
        species.append(result)

    for smiles in reactant_smiles or []:
        _add("reactant", smiles)
    for smiles in reagent_smiles or []:
        _add("reagent", smiles)
    if product_smiles:
        _add("product", product_smiles)

    risks = [s["overall_risk"] for s in species if s["overall_risk"] != "unknown"]
    overall = _worst(risks) if risks else "low"
    any_unparsed = any(not s["parsed"] for s in species)
    any_flagged = any(s["flagged_groups"] for s in species)
    return {
        "species": species,
        "overall_risk": "unknown" if (not species) else overall,
        "requires_expert_review": (not species) or any_unparsed or any_flagged or overall != "low",
        "energetic_groups_found": sorted(
            {f["key"] for s in species for f in s["flagged_groups"]}
        ),
        "disclaimer": _DISCLAIMER,
        "screen_version": _SCREEN_VERSION,
    }
