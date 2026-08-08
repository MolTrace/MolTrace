"""How often a *wrong* structure outranks the right one (B5.2).

Accuracy on correct structures says nothing about the failure that matters. The
eval harness treats ``false_confirmation_rate`` as a **zero-regression** safety
metric; this is what computes it.

The accounting is the design
----------------------------
A false-confirmation rate goes wrong in the denominator, so every decoy is placed
in exactly one bucket and the buckets are reported alongside the rate:

``scored``
    Truth and decoy were genuinely comparable, and DP4 preferred one. The only
    bucket the rate is computed over.
``indistinguishable``
    The predictor produces identical environments for both — a stereoisomer, to a
    topological predictor. Scoring these would count a coin flip as a
    discrimination, and would do so in the flattering direction.
``rejected_on_formula``
    The decoy has a different carbon count, so it was eliminated by the molecular
    formula rather than by shift evidence. Crediting that to NMR would overstate
    what the spectrum contributed — in practice HRMS removes these long before a
    shift list is consulted.
``unscorable``
    Could not be parsed or predicted at all. Counted so the buckets sum to the
    total; silence here would let coverage failures masquerade as good results.

``false_confirmation_rate`` is **None**, never 0.0, when nothing was scored. Zero
evidence is not a perfect score.

What this measures, and what it does not
----------------------------------------
One evidence layer: a shift list, through DP4, for a single nucleus. **Not** the
multi-test :func:`moltrace.spectroscopy.verification.verify_structure` arbiter,
which combines independent tests and abstains where it lacks data. A rate here is
a statement about how much a shift list alone can discriminate — useful precisely
because it bounds what the rest of the stack has to make up for.

Deterministic: decoys are generated at fixed positions, the split is content
hashed, and nothing here samples.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from rdkit import Chem

from moltrace.spectroscopy.eval.decoys import generate_decoys
from moltrace.spectroscopy.predict.nmrnet_wrapper import (
    KnowledgeBase,
    build_knowledge_base,
    hose_code,
    molecule_from_record,
)

__all__ = ["FalseConfirmationReport", "measure_false_confirmation"]

_MIN_OBSERVED_SHIFTS = 4
"""Below this, DP4's linear scaling has too few points to mean anything."""


@dataclass(frozen=True)
class FalseConfirmationReport:
    pairs_generated: int
    pairs_scored: int
    truth_wins: int
    decoy_wins: int
    indistinguishable: int
    rejected_on_formula: int
    unscorable: int
    molecules_examined: int
    nucleus: str
    by_kind: dict[str, dict[str, int]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def false_confirmation_rate(self) -> float | None:
        """Share of scored pairs where a wrong structure won. ``None`` if none scored."""

        if not self.pairs_scored:
            return None
        return self.decoy_wins / self.pairs_scored

    def as_dict(self) -> dict[str, Any]:
        return {
            "nucleus": self.nucleus,
            "molecules_examined": self.molecules_examined,
            "pairs_generated": self.pairs_generated,
            "pairs_scored": self.pairs_scored,
            "truth_wins": self.truth_wins,
            "decoy_wins": self.decoy_wins,
            "indistinguishable": self.indistinguishable,
            "rejected_on_formula": self.rejected_on_formula,
            "unscorable": self.unscorable,
            "false_confirmation_rate": self.false_confirmation_rate,
            "by_kind": {k: dict(v) for k, v in sorted(self.by_kind.items())},
            "notes": list(self.notes),
        }


def _codes_and_shifts(
    kb: KnowledgeBase, smiles: str, element: str, nucleus: str
) -> tuple[list[tuple[str, ...]], list[float]] | None:
    """One pass over the molecule: environments *and* predicted shifts.

    The environments double as the structure's identity as this predictor sees it,
    so equal environment multisets mean the two candidates are indistinguishable.
    Computing both together avoids walking every atom twice.
    """

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mol_h = Chem.AddHs(mol)
    codes: list[tuple[str, ...]] = []
    shifts: list[float] = []
    for atom in mol_h.GetAtoms():
        if atom.GetSymbol() != element:
            continue
        code = hose_code(mol_h, atom.GetIdx())
        codes.append(code)
        hit = kb.lookup(nucleus, code)
        shifts.append(hit[0] if hit is not None else kb.priors.get(nucleus, float("nan")))
    return sorted(codes), shifts


def measure_false_confirmation(
    *,
    train: Sequence[Mapping[str, Any]],
    test: Sequence[Mapping[str, Any]],
    nucleus: str = "13C",
    knowledge_base: KnowledgeBase | None = None,
    max_molecules: int | None = None,
) -> FalseConfirmationReport:
    """Score each held-out molecule against plausibly-wrong variants of itself."""

    if not test:
        raise ValueError("measure_false_confirmation needs a non-empty test split")
    if knowledge_base is None and not train:
        raise ValueError("measure_false_confirmation needs a non-empty train split")

    from nmrcheck.dp4_scoring import dp4_probabilities

    kb = knowledge_base if knowledge_base is not None else build_knowledge_base(train)
    element = "H" if nucleus == "1H" else "C"

    generated = scored = truth_wins = decoy_wins = 0
    indistinguishable = rejected_on_formula = unscorable = 0
    examined = 0
    by_kind: dict[str, dict[str, int]] = {}

    for record in test:
        if max_molecules is not None and examined >= max_molecules:
            break
        mol = molecule_from_record(record)
        if mol is None:
            continue
        observed = [
            float(a["shift_ppm"])
            for a in record.get("assignments", [])
            if a.get("nucleus") == nucleus
        ]
        if len(observed) < _MIN_OBSERVED_SHIFTS:
            continue
        try:
            truth_smiles = Chem.MolToSmiles(Chem.RemoveHs(mol))
            decoys = generate_decoys(truth_smiles)
        except (ValueError, Chem.KekulizeException, RuntimeError):
            continue
        if not decoys:
            continue

        truth = _codes_and_shifts(kb, truth_smiles, element, nucleus)
        # The truth's own predicted count must match the observed list, or the
        # comparison is between differently-shaped things and means nothing.
        if truth is None or len(truth[1]) != len(observed):
            continue
        truth_codes, truth_shifts = truth
        examined += 1

        for decoy in decoys:
            generated += 1
            bucket = by_kind.setdefault(
                str(decoy.kind),
                {
                    "truth_wins": 0,
                    "decoy_wins": 0,
                    "indistinguishable": 0,
                    "rejected_on_formula": 0,
                    "unscorable": 0,
                },
            )
            predicted = _codes_and_shifts(kb, decoy.smiles, element, nucleus)
            if predicted is None:
                unscorable += 1
                bucket["unscorable"] += 1
                continue
            decoy_codes, decoy_shifts = predicted
            if decoy_codes == truth_codes:
                indistinguishable += 1
                bucket["indistinguishable"] += 1
                continue
            if len(decoy_shifts) != len(observed):
                rejected_on_formula += 1
                bucket["rejected_on_formula"] += 1
                continue

            probabilities = dp4_probabilities(
                observed_shifts_ppm=observed,
                candidate_predicted_shifts_ppm=[truth_shifts, decoy_shifts],
                nucleus=nucleus,  # type: ignore[arg-type]
            )
            scored += 1
            if probabilities[1].probability > probabilities[0].probability:
                decoy_wins += 1
                bucket["decoy_wins"] += 1
            else:
                truth_wins += 1
                bucket["truth_wins"] += 1

    notes = [
        f"Scored {nucleus} shift lists through DP4 only — not the multi-test verifier, "
        "and with no 2-D, MS or multiplicity evidence.",
        "'rejected_on_formula' decoys differ in atom count and are eliminated by the "
        "molecular formula, not by shift evidence; they are excluded from the rate.",
        "'indistinguishable' decoys produce identical predicted environments (e.g. "
        "stereoisomers, which a topological predictor cannot resolve) and are not scored.",
    ]

    return FalseConfirmationReport(
        pairs_generated=generated,
        pairs_scored=scored,
        truth_wins=truth_wins,
        decoy_wins=decoy_wins,
        indistinguishable=indistinguishable,
        rejected_on_formula=rejected_on_formula,
        unscorable=unscorable,
        molecules_examined=examined,
        nucleus=nucleus,
        by_kind=by_kind,
        notes=notes,
    )
