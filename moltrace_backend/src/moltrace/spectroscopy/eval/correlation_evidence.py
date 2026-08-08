"""Predicted HSQC / HMBC correlations, and how much they separate candidates (B6.2).

Why this exists
---------------
The held-out false-confirmation measurement found that ¹³C shift lists resolve
**regioisomers at a 37.7 % error rate** — barely better than chance — and that a
regioisomer survives every upstream filter, because it has the same molecular
formula and the same carbon count as the truth.

The usual answer is "use 2-D", and it is right, but the reason matters and is
easy to state wrongly. It is *not* that 2-D makes the candidates more
distinguishable in principle: a regioisomer already has a different predicted ¹³C
list. It is that the two evidence types fail differently:

* a **shift** is a continuous value that must be predicted accurately. Measured
  held-out ¹³C MAE is 3.44 ppm against a DP4 scale of 2.306 ppm, so the prediction
  is often too coarse to exploit the difference it does have;
* an **HMBC cross-peak** is a near-binary observation — the correlation is either
  present or absent — and *which* protons correlate to *which* carbons follows from
  **topology alone**, which is predicted exactly.

So 2-D evidence sidesteps the part of the pipeline that is failing. This module
computes the correlation sets and measures the separation, so that argument rests
on a number rather than on plausibility.

Scope, stated plainly
---------------------
This predicts correlations from a structure and compares two structures. It does
**not** score against experimental 2-D data — only 218 of 64,723 NMRShiftDB2
records carry HMBC blocks (0.34 %), far too few for a held-out measurement. So
this bounds *available* discriminating power; converting it to a measured
false-confirmation rate needs 2-D data the corpus does not have.

Pure: topology only, no shifts, no clock, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rdkit import Chem

__all__ = [
    "CorrelationSeparation",
    "hsqc_correlations",
    "hmbc_correlations",
    "correlation_separation",
]

#: HMBC reports 2- and 3-bond H->C couplings. The 4-bond case exists (allylic,
#: W-coupling) but is weak and inconsistent, so it is excluded rather than
#: predicted as if it were reliable.
_HMBC_MIN_BONDS = 2
_HMBC_MAX_BONDS = 3


def _with_explicit_h(smiles: str) -> Chem.Mol | None:
    mol = Chem.MolFromSmiles(smiles)
    return Chem.AddHs(mol) if mol is not None else None


def _correlation_signature(
    mol_h: Chem.Mol, min_bonds: int, max_bonds: int
) -> tuple[tuple[str, ...], ...]:
    """Canonical H->C correlation set, as environment pairs rather than indices.

    Keyed by each partner's canonical rank rather than its atom index, so the
    signature is a property of the *structure* and does not change when the same
    molecule is written a different way.
    """

    ranks = list(Chem.CanonicalRankAtoms(mol_h, breakTies=False))
    distances = Chem.GetDistanceMatrix(mol_h)

    pairs: list[tuple[str, ...]] = []
    for atom in mol_h.GetAtoms():
        if atom.GetSymbol() != "H":
            continue
        h_index = atom.GetIdx()
        for carbon in mol_h.GetAtoms():
            if carbon.GetSymbol() != "C":
                continue
            c_index = carbon.GetIdx()
            bonds = int(distances[h_index][c_index])
            if min_bonds <= bonds <= max_bonds:
                pairs.append((str(ranks[h_index]), str(ranks[c_index]), str(bonds)))
    return tuple(sorted(pairs))


def hsqc_correlations(smiles: str) -> tuple[tuple[str, ...], ...]:
    """One-bond H->C correlations (HSQC/HMQC), from topology."""

    mol_h = _with_explicit_h(smiles)
    if mol_h is None:
        raise ValueError(f"Could not parse SMILES: {smiles!r}")
    return _correlation_signature(mol_h, 1, 1)


def hmbc_correlations(smiles: str) -> tuple[tuple[str, ...], ...]:
    """Two- and three-bond H->C correlations (HMBC), from topology."""

    mol_h = _with_explicit_h(smiles)
    if mol_h is None:
        raise ValueError(f"Could not parse SMILES: {smiles!r}")
    return _correlation_signature(mol_h, _HMBC_MIN_BONDS, _HMBC_MAX_BONDS)


@dataclass(frozen=True)
class CorrelationSeparation:
    """How far apart two candidates are in predicted-correlation space."""

    hsqc_truth: int
    hsqc_decoy: int
    hsqc_symmetric_difference: int
    hmbc_truth: int
    hmbc_decoy: int
    hmbc_symmetric_difference: int

    @property
    def separated(self) -> bool:
        """Do the two candidates predict different correlation patterns at all?"""

        return self.hsqc_symmetric_difference > 0 or self.hmbc_symmetric_difference > 0

    @property
    def hmbc_separation_ratio(self) -> float:
        """Differing HMBC correlations as a share of the truth's own count.

        A rough answer to "how much of the 2-D spectrum would have to be wrong for
        this decoy to pass?" — 0.0 means an HMBC could not tell them apart.
        """

        if not self.hmbc_truth:
            return 0.0
        return self.hmbc_symmetric_difference / self.hmbc_truth

    def as_dict(self) -> dict[str, Any]:
        return {
            "hsqc_truth": self.hsqc_truth,
            "hsqc_decoy": self.hsqc_decoy,
            "hsqc_symmetric_difference": self.hsqc_symmetric_difference,
            "hmbc_truth": self.hmbc_truth,
            "hmbc_decoy": self.hmbc_decoy,
            "hmbc_symmetric_difference": self.hmbc_symmetric_difference,
            "hmbc_separation_ratio": self.hmbc_separation_ratio,
            "separated": self.separated,
        }


def correlation_separation(truth_smiles: str, decoy_smiles: str) -> CorrelationSeparation:
    """Compare two candidates' predicted HSQC and HMBC correlation sets."""

    truth_hsqc, decoy_hsqc = set(hsqc_correlations(truth_smiles)), set(
        hsqc_correlations(decoy_smiles)
    )
    truth_hmbc, decoy_hmbc = set(hmbc_correlations(truth_smiles)), set(
        hmbc_correlations(decoy_smiles)
    )
    return CorrelationSeparation(
        hsqc_truth=len(truth_hsqc),
        hsqc_decoy=len(decoy_hsqc),
        hsqc_symmetric_difference=len(truth_hsqc ^ decoy_hsqc),
        hmbc_truth=len(truth_hmbc),
        hmbc_decoy=len(decoy_hmbc),
        hmbc_symmetric_difference=len(truth_hmbc ^ decoy_hmbc),
    )
