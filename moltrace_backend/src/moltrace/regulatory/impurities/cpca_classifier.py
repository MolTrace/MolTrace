"""Nitrosamine CPCA classifier — FDA Carcinogenic Potency Categorization Approach (Prompt 5).

Implements the **canonical FDA CPCA** (Aug-2023 NDSRI guidance, carried into the
FDA Nitrosamine Guidance Rev 2): a deterministic structure-activity flowchart that
scores an N-nitrosamine's carcinogenic potency and assigns it to one of five
potency categories, each with a recommended acceptable intake (AI) limit. The
encoded scoring tables (the alpha-hydrogen score table and the activating /
deactivating feature point-values) are transcribed verbatim from the FDA's own
open-source reference tool (``github.com/FDA/featurize-nitrosamines``).

DISCLAIMER (surfaced in every result + intended for any UI). CPCA output is
**decision-support, not a regulatory determination**. Nitrosamine potency
categorization and AI-limit results must be reviewed and signed off by a qualified
toxicologist / regulatory-affairs professional before any use in a filing or
release decision.

Deterministic-first. The category, AI limit, and cumulative-risk math are pure,
auditable, content-versioned arithmetic over the published FDA rubric — **no model
in this path**. RDKit is used only to recognise structural features (the
alpha-carbons, rings, and substituents), exactly as the FDA reference tool does.

Fidelity note. The **alpha-hydrogen score table, the flowchart, the category /
AI-limit mapping, the carboxylic-acid and ring features, the tertiary-alpha-carbon
rule, and the benzylic feature are exact** (they reproduce the FDA reference
values). The chain-length, electron-withdrawing-group, beta-hydroxyl, and
beta-methyl detectors are faithful but **approximate** rdkit reimplementations of
the FDA tool's cheminformatics; for complex or edge structures, confirm the feature
calls against the FDA ``featurize-nitrosamines`` tool. The structural-alert subset
and these approximations must be verified before filing use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from moltrace.regulatory.infra.validation import (
    ValidationFailure,
    ValidationReport,
    assert_valid_compound_record,
)
from moltrace.regulatory.infra.versioning import content_hash, rule_set_version

__all__ = [
    "CPCAResult",
    "CumulativeRiskResult",
    "calculate_cumulative_risk",
    "classify_cpca",
    "cpca_rule_set",
]

GUIDELINE = "FDA Nitrosamine Guidance Rev 2 (Sept 2024); CPCA per FDA NDSRI Guidance (Aug 2023)"
TITLE = "Carcinogenic Potency Categorization Approach (CPCA) for N-nitrosamines"
METHOD_REFERENCE = "FDA featurize-nitrosamines (github.com/FDA/featurize-nitrosamines)"
EFFECTIVE_YEAR = "2024"

DISCLAIMER = (
    "Decision-support only, NOT a regulatory determination: CPCA potency categorization "
    "and AI-limit results must be reviewed and signed off by a qualified toxicologist / "
    "regulatory-affairs professional before any use in a filing or release decision."
)

# Recommended AI limits (ng/day) by potency category. FDA Category 1 = 26.5 ng/day;
# EMA Category 1 = 18 ng/day. Categories 2-5 are common to both.
_AI_LIMITS = {1: 26.5, 2: 100.0, 3: 400.0, 4: 1500.0, 5: 1500.0}
_AI_LIMIT_CAT1_EMA = 18.0

# alpha-Hydrogen score table (counts on each alpha-carbon, lowest first -> score).
# Scores 4 and 5 are sentinels that force Potency Category 5.
# Transcribed from the FDA featurize-nitrosamines reference tool.
_ALPHA_H_SCORE = {
    "0,0": 5,
    "0,1": 4,
    "1,1": 4,
    "0,2": 3,
    "0,3": 2,
    "1,2": 3,
    "1,3": 3,
    "2,2": 1,
    "2,3": 1,
    "3,3": 1,
}

# Feature point-values (FDA CPCA). Deactivating features raise the score (lower
# potency, higher category); activating features lower it.
_FEATURE_SCORES = {
    "carboxylic_acid": 3,
    "nno_in_pyrrolidine_ring": 3,
    "nno_in_6ring_with_sulfur": 3,
    "nno_in_5_or_6_ring": 2,
    "nno_in_morpholine_ring": 1,
    "nno_in_7_ring": 1,
    "chain_ge5_both_sides": 1,
    "ewg_on_alpha_one_side": 1,
    "ewg_on_alpha_both_sides": 2,
    "beta_hydroxyl_one_side": 1,
    "beta_hydroxyl_both_sides": 2,
    "aryl_on_alpha_benzylic": -1,
    "methyl_on_beta_carbon": -1,
}

_CATEGORY_DESCRIPTION = {
    1: "Category 1 - highest predicted carcinogenic potency.",
    2: "Category 2 - high predicted potency (<= NDMA/NNK).",
    3: "Category 3 - moderate predicted potency.",
    4: "Category 4 - low predicted potency (alpha-hydroxylation disfavoured).",
    5: "Category 5 - lowest predicted potency (no metabolic activation expected).",
}

# EWG substructures on an alpha-carbon (excluding carboxylic acid, aryl, ketone),
# a curated approximation of the FDA reference tool's electron-withdrawing set. The
# first SMARTS atom is the alpha-carbon. Free carboxylic acid (OX2H1) and ketones
# (C(=O)C) are deliberately excluded - the former is the separate +3 COOH feature.
_EWG_ALPHA_SMARTS = (
    "[CX4;H1,H2,H3][F,Cl,Br,I]",  # alpha-halogen
    "[CX4;H1,H2,H3]C#N",  # alpha-nitrile
    "[CX4;H1,H2,H3]C(=O)[OX2H0]",  # alpha to ESTER carbonyl (not free acid)
    "[CX4;H1,H2,H3]C(=O)[NX3]",  # alpha to amide carbonyl
    "[CX4;H1,H2,H3][SX4](=O)(=O)",  # alpha-sulfonyl
    "[CX4;H1,H2,H3][NX3+](=O)[O-]",  # alpha-nitro
)


def _fail(field: str, message: str) -> None:
    ValidationReport(
        success=False,
        failures=(ValidationFailure(field, message),),
        n_checks=1,
    ).raise_for_status()


def _mol_from_smiles(smiles: str) -> Any:
    from rdkit import Chem
    from rdkit.rdBase import BlockLogs

    with BlockLogs():
        mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        _fail("smiles", f"could not parse SMILES {smiles!r}")
    return mol


def _nitroso_centers(mol: Any) -> list[tuple[int, int]]:
    """Return (amino_N_idx, nitroso_N_idx) for each N-nitroso group."""
    from rdkit import Chem

    patt = Chem.MolFromSmarts("[NX3]-[NX2]=[OX1]")
    return [(m[0], m[1]) for m in mol.GetSubstructMatches(patt)]


def _alpha_carbons(mol: Any, amino_n: int, nitroso_n: int) -> list[Any]:
    amino = mol.GetAtomWithIdx(amino_n)
    return [
        nbr
        for nbr in amino.GetNeighbors()
        if nbr.GetIdx() != nitroso_n and nbr.GetAtomicNum() == 6
    ]


def _alpha_h_key(alpha_carbons: list[Any]) -> str:
    counts = sorted(c.GetTotalNumHs() for c in alpha_carbons)
    while len(counts) < 2:  # primary nitrosamine / single carbon substituent
        counts.insert(0, 0)
    return f"{counts[0]},{counts[1]}"


def _has_tertiary_alpha(alpha_carbons: list[Any]) -> bool:
    from rdkit import Chem

    return any(
        c.GetTotalNumHs() == 0
        and not c.GetIsAromatic()
        and c.GetHybridization() == Chem.HybridizationType.SP3
        for c in alpha_carbons
    )


def _ring_feature(mol: Any, amino_n: int) -> str | None:
    rings = [r for r in mol.GetRingInfo().AtomRings() if amino_n in r]
    if not rings:
        return None
    ring = min(rings, key=len)
    size = len(ring)
    hetero = {
        mol.GetAtomWithIdx(i).GetSymbol()
        for i in ring
        if i != amino_n and mol.GetAtomWithIdx(i).GetAtomicNum() != 6
    }
    if size == 7:
        return "nno_in_7_ring"
    if size == 6:
        if "S" in hetero:
            return "nno_in_6ring_with_sulfur"
        if "O" in hetero:
            return "nno_in_morpholine_ring"
        return "nno_in_5_or_6_ring"
    if size == 5:
        return "nno_in_pyrrolidine_ring" if not hetero else "nno_in_5_or_6_ring"
    return None


def _branch_heavy_count(mol: Any, start: int, exclude: set[int]) -> int:
    seen: set[int] = set()
    stack = [start]
    while stack:
        i = stack.pop()
        if i in seen or i in exclude:
            continue
        seen.add(i)
        for nbr in mol.GetAtomWithIdx(i).GetNeighbors():
            if nbr.GetIdx() not in seen and nbr.GetIdx() not in exclude:
                stack.append(nbr.GetIdx())
    return len(seen)


def _chain5_both_sides(mol: Any, amino_n: int, nitroso_n: int, alpha_carbons: list[Any]) -> bool:
    if len(alpha_carbons) < 2:
        return False
    idxs = {a.GetIdx() for a in alpha_carbons}
    for c in alpha_carbons:
        exclude = {amino_n, nitroso_n} | (idxs - {c.GetIdx()})
        if _branch_heavy_count(mol, c.GetIdx(), exclude) < 5:
            return False
    return True


def _is_methyl(atom: Any) -> bool:
    return atom.GetAtomicNum() == 6 and atom.GetTotalNumHs() == 3 and atom.GetDegree() == 1


def _beta_carbons(alpha_c: Any, amino_n: int) -> list[Any]:
    return [n for n in alpha_c.GetNeighbors() if n.GetIdx() != amino_n and n.GetAtomicNum() == 6]


def _side_has_beta_hydroxyl(alpha_c: Any, amino_n: int) -> bool:
    # A genuine alcohol -OH on an sp3 beta-carbon; excludes carboxylic-acid / ester
    # oxygens (whose carbon is sp2), so it never double-counts the COOH feature.
    from rdkit import Chem

    for beta in _beta_carbons(alpha_c, amino_n):
        if beta.GetIsAromatic() or beta.GetHybridization() != Chem.HybridizationType.SP3:
            continue
        for g in beta.GetNeighbors():
            if g.GetAtomicNum() == 8 and g.GetTotalNumHs() >= 1 and g.GetDegree() == 1:
                return True
    return False


def _side_has_beta_methyl(alpha_c: Any, amino_n: int) -> bool:
    # FDA logic: the alpha-carbon must carry no heteroatom substituent; the
    # beta-carbon must be a secondary methine (exactly 1 H), not bonded to a
    # terminal heteroatom, and bear a methyl. (A linear n-propyl beta-CH2 with 2 H
    # does NOT qualify.)
    if alpha_c.GetIsAromatic():
        return False
    for nbr in alpha_c.GetNeighbors():
        if nbr.GetIdx() != amino_n and nbr.GetAtomicNum() not in (1, 6):
            return False
    for beta in _beta_carbons(alpha_c, amino_n):
        if beta.GetTotalNumHs() != 1:
            continue
        if any(g.GetAtomicNum() not in (1, 6) and g.GetDegree() == 1 for g in beta.GetNeighbors()):
            continue
        if any(g.GetIdx() != alpha_c.GetIdx() and _is_methyl(g) for g in beta.GetNeighbors()):
            return True
    return False


def _side_is_benzylic(alpha_c: Any, amino_n: int) -> bool:
    if alpha_c.GetIsAromatic():
        return False
    return any(n.GetIdx() != amino_n and n.GetIsAromatic() for n in alpha_c.GetNeighbors())


def _side_has_ewg(mol: Any, alpha_c: Any) -> bool:
    from rdkit import Chem

    if alpha_c.GetIsAromatic() or alpha_c.GetTotalNumHs() == 0:
        return False
    idx = alpha_c.GetIdx()
    for sma in _EWG_ALPHA_SMARTS:
        patt = Chem.MolFromSmarts(sma)
        if patt is not None and any(m[0] == idx for m in mol.GetSubstructMatches(patt)):
            return True
    return False


def _has_carboxylic_acid(mol: Any) -> bool:
    from rdkit import Chem

    for sma in ("[CX3](=O)[OX2H1]", "[CX3](=O)[OX1-]"):
        patt = Chem.MolFromSmarts(sma)
        if patt is not None and mol.HasSubstructMatch(patt):
            return True
    return False


@dataclass(frozen=True)
class CPCAResult:
    """An FDA CPCA potency categorization for one N-nitrosamine."""

    smiles: str
    category: int
    category_description: str
    ai_limit_ng_per_day: float
    authority: str
    potency_score: int | None
    alpha_h_distribution: str
    alpha_h_score: int
    activating_features: tuple[str, ...]
    deactivating_features: tuple[str, ...]
    feature_evidence: dict[str, int]
    is_ndsri: bool
    coc_flag: bool
    regulatory_basis: str
    method_reference: str
    disclaimer: str
    notes: tuple[str, ...]
    rule_set_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "smiles": self.smiles,
            "category": self.category,
            "category_description": self.category_description,
            "ai_limit_ng_per_day": self.ai_limit_ng_per_day,
            "authority": self.authority,
            "potency_score": self.potency_score,
            "alpha_h_distribution": self.alpha_h_distribution,
            "alpha_h_score": self.alpha_h_score,
            "activating_features": list(self.activating_features),
            "deactivating_features": list(self.deactivating_features),
            "feature_evidence": dict(self.feature_evidence),
            "is_ndsri": self.is_ndsri,
            "coc_flag": self.coc_flag,
            "regulatory_basis": self.regulatory_basis,
            "method_reference": self.method_reference,
            "disclaimer": self.disclaimer,
            "notes": list(self.notes),
            "rule_set_version": self.rule_set_version,
        }

    def content_hash(self) -> str:
        return content_hash(self.as_dict())


@dataclass(frozen=True)
class CumulativeRiskResult:
    """Cumulative-risk verdict for a set of nitrosamines (FDA Rev 2)."""

    components: tuple[dict[str, Any], ...]
    total_risk_ratio: float
    passes: bool
    regulatory_basis: str
    disclaimer: str
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "components": [dict(c) for c in self.components],
            "total_risk_ratio": self.total_risk_ratio,
            "passes": self.passes,
            "regulatory_basis": self.regulatory_basis,
            "disclaimer": self.disclaimer,
            "notes": list(self.notes),
        }


def classify_cpca(smiles: str, authority: str = "FDA") -> CPCAResult:
    """Classify a nitrosamine using the 5-category FDA CPCA framework.

    ``authority`` selects the Category-1 AI limit: ``'FDA'`` -> 26.5 ng/day (default),
    ``'EMA'`` -> 18 ng/day; Categories 2-5 are common to both. A SMILES without an
    N-nitroso group fails loud (this classifier is for nitrosamines).
    """

    assert_valid_compound_record({"smiles": smiles})
    if authority not in ("FDA", "EMA"):
        _fail("authority", f"{authority!r} must be 'FDA' or 'EMA'")
    mol = _mol_from_smiles(smiles)

    centers = _nitroso_centers(mol)
    if not centers:
        _fail("smiles", "no N-nitroso group found; classify_cpca is for nitrosamines")
    multiple = len(centers) > 1
    amino_n, nitroso_n = centers[0]

    alpha_carbons = _alpha_carbons(mol, amino_n, nitroso_n)
    alpha_key = _alpha_h_key(alpha_carbons)
    alpha_score = _ALPHA_H_SCORE[alpha_key]
    tertiary_alpha = _has_tertiary_alpha(alpha_carbons)

    evidence: dict[str, int] = {}
    deactivating: list[str] = []
    activating: list[str] = []

    def record(name: str) -> None:
        score = _FEATURE_SCORES[name]
        evidence[name] = score
        (activating if score < 0 else deactivating).append(name)

    # --- deactivating features --- #
    if _has_carboxylic_acid(mol):
        record("carboxylic_acid")
    ring_feature = _ring_feature(mol, amino_n)
    if ring_feature is not None:
        record(ring_feature)
    if ring_feature is None and _chain5_both_sides(mol, amino_n, nitroso_n, alpha_carbons):
        record("chain_ge5_both_sides")
    ewg_sides = sum(1 for c in alpha_carbons if _side_has_ewg(mol, c))
    if ewg_sides >= 2:
        record("ewg_on_alpha_both_sides")
    elif ewg_sides == 1:
        record("ewg_on_alpha_one_side")
    oh_sides = sum(1 for c in alpha_carbons if _side_has_beta_hydroxyl(c, amino_n))
    if oh_sides >= 2:
        record("beta_hydroxyl_both_sides")
    elif oh_sides == 1:
        record("beta_hydroxyl_one_side")

    # --- activating features --- #
    if any(_side_is_benzylic(c, amino_n) for c in alpha_carbons):
        record("aryl_on_alpha_benzylic")
    if any(_side_has_beta_methyl(c, amino_n) for c in alpha_carbons):
        record("methyl_on_beta_carbon")

    # --- category (flowchart) --- #
    forced_cat5 = alpha_score in (4, 5) or tertiary_alpha
    if forced_cat5:
        category = 5
        potency_score: int | None = None
    else:
        potency_score = alpha_score + sum(evidence.values())
        if potency_score <= 1:
            category = 1
        elif potency_score == 2:
            category = 2
        elif potency_score == 3:
            category = 3
        else:
            category = 4

    ai_limit = _AI_LIMITS[category]
    if category == 1 and authority == "EMA":
        ai_limit = _AI_LIMIT_CAT1_EMA

    notes = [DISCLAIMER]
    if forced_cat5:
        reason = "tertiary alpha-carbon" if tertiary_alpha else "no/insufficient alpha-hydrogens"
        notes.insert(0, f"Forced to Category 5 ({reason}); metabolic activation not expected.")
    if multiple:
        notes.insert(0, "Multiple N-nitroso groups found; only the first was scored.")
    heavy = mol.GetNumHeavyAtoms()

    return CPCAResult(
        smiles=smiles,
        category=category,
        category_description=_CATEGORY_DESCRIPTION[category],
        ai_limit_ng_per_day=ai_limit,
        authority=authority,
        potency_score=potency_score,
        alpha_h_distribution=alpha_key,
        alpha_h_score=alpha_score,
        activating_features=tuple(activating),
        deactivating_features=tuple(deactivating),
        feature_evidence=evidence,
        is_ndsri=heavy > 12,
        coc_flag=True,
        regulatory_basis=GUIDELINE,
        method_reference=METHOD_REFERENCE,
        disclaimer=DISCLAIMER,
        notes=tuple(notes),
        rule_set_version=_RULE_SET_VERSION,
    )


def calculate_cumulative_risk(
    nitrosamines: list[tuple[str, float]], authority: str = "FDA"
) -> CumulativeRiskResult:
    """Cumulative risk for multiple nitrosamines (FDA Rev 2).

    For each ``(SMILES, measured_ng_per_day)``, the ratio ``measured / AI_limit`` is
    summed; the total **must be < 1**. Each component is classified via
    :func:`classify_cpca` to obtain its AI limit.
    """

    components: list[dict[str, Any]] = []
    total = 0.0
    for smiles, measured in nitrosamines:
        measured_ng = float(measured)
        if measured_ng < 0:
            _fail("measured", f"measured ng/day must be >= 0, got {measured_ng}")
        result = classify_cpca(smiles, authority=authority)
        ratio = measured_ng / result.ai_limit_ng_per_day
        total += ratio
        components.append(
            {
                "smiles": smiles,
                "category": result.category,
                "ai_limit_ng_per_day": result.ai_limit_ng_per_day,
                "measured_ng_per_day": measured_ng,
                "risk_ratio": ratio,
            }
        )

    return CumulativeRiskResult(
        components=tuple(components),
        total_risk_ratio=total,
        passes=total < 1.0,
        regulatory_basis=GUIDELINE,
        disclaimer=DISCLAIMER,
        notes=(
            "Cumulative risk = sum(measured / AI limit) across nitrosamines; must be < 1 "
            "(FDA Nitrosamine Guidance Rev 2).",
            DISCLAIMER,
        ),
    )


def cpca_rule_set() -> dict[str, Any]:
    """The encoded FDA CPCA rubric — the auditable rule-set."""

    return {
        "guideline": GUIDELINE,
        "title": TITLE,
        "method_reference": METHOD_REFERENCE,
        "effective_year": EFFECTIVE_YEAR,
        "ai_limits_ng_per_day": dict(_AI_LIMITS),
        "ai_limit_cat1_ema_ng_per_day": _AI_LIMIT_CAT1_EMA,
        "alpha_h_score_table": dict(_ALPHA_H_SCORE),
        "feature_scores": dict(_FEATURE_SCORES),
    }


_RULE_SET_VERSION = rule_set_version(cpca_rule_set())
