"""Plausibly-wrong structures, for measuring how often one gets confirmed (B5.2).

Accuracy on correct structures says nothing about the failure that matters. A
verification system is only tested once it has been shown answers that are wrong,
and wrong in the ways a chemist is actually wrong — a heteroatom misread, a
homologue off by one CH₂, a methyl on the wrong carbon, a stereocentre inverted.
A randomly drawn molecule is rejected trivially and measures nothing.

The eval harness already treats ``false_confirmation_rate`` as a zero-regression
safety metric. It had no source of wrong answers to compute it from; this is that
source.

A capability boundary this module makes explicit
------------------------------------------------
HOSE codes are **topological**. A stereoisomer has identical connectivity, so it
yields an identical code and an identical prediction: this predictor cannot
discriminate stereoisomers *at all*. That is a stated limit, not a defect to hide
— and it is worth stating plainly because the strategy proposal that prompted this
program claimed ">99.5 % … stereochemical resolution".

:class:`DecoyKind.STEREO_INVERSION` decoys are therefore generated **and labelled**,
and :func:`predictions_are_distinguishable` reports ``False`` for them, so a
false-confirmation measurement records "indistinguishable" rather than silently
scoring a coin flip as a discrimination.

Pure and deterministic: no randomness, no clock. Transforms are applied at fixed
positions so the same input always yields the same decoy set — a false-confirmation
rate that cannot be reproduced is not a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from rdkit import Chem

__all__ = [
    "DecoyKind",
    "Decoy",
    "generate_decoys",
    "predictions_are_distinguishable",
]


class DecoyKind(StrEnum):
    """How a decoy is wrong. The report needs the mode, not just the fact."""

    HETEROATOM_SWAP = "heteroatom_swap"
    HOMOLOGUE = "homologue"
    METHYL_ADDED = "methyl_added"
    RING_SUBSTITUTION = "ring_substitution"
    STEREO_INVERSION = "stereo_inversion"


@dataclass(frozen=True)
class Decoy:
    smiles: str
    kind: DecoyKind


#: (SMARTS to find, SMILES to write instead) — chemically plausible misreadings.
#: Ordered, and applied at the first match only, so generation is deterministic.
_SWAPS: tuple[tuple[str, str, DecoyKind], ...] = (
    # An alcohol misread as an amine (and vice versa) — a classic confusion, and
    # one that moves 13C substantially.
    ("[OX2H]", "N", DecoyKind.HETEROATOM_SWAP),
    ("[NX3;H2]", "O", DecoyKind.HETEROATOM_SWAP),
    # A ketone/ester carbonyl oxygen read as sulfur.
    ("[OX1]=[CX3]", "S", DecoyKind.HETEROATOM_SWAP),
)


def _canonical(mol: Chem.Mol) -> str:
    return Chem.MolToSmiles(mol)


def _sanitised(mol: Chem.Mol) -> Chem.Mol | None:
    try:
        Chem.SanitizeMol(mol)
    except Exception:
        return None
    return mol


def _heteroatom_swaps(mol: Chem.Mol) -> list[Decoy]:
    out: list[Decoy] = []
    for smarts, replacement, kind in _SWAPS:
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is None:
            continue
        matches = mol.GetSubstructMatches(pattern)
        if not matches:
            continue
        editable = Chem.RWMol(mol)
        atom_index = matches[0][0]  # first match only — determinism
        editable.GetAtomWithIdx(atom_index).SetAtomicNum(
            Chem.GetPeriodicTable().GetAtomicNumber(replacement)
        )
        editable.GetAtomWithIdx(atom_index).SetNoImplicit(False)
        candidate = _sanitised(editable.GetMol())
        if candidate is not None:
            out.append(Decoy(_canonical(candidate), kind))
    return out


def _homologue(mol: Chem.Mol) -> list[Decoy]:
    """Insert a CH₂ into an acyclic C–C bond: the off-by-one-carbon mistake."""

    for bond in mol.GetBonds():
        if bond.IsInRing() or bond.GetBondType() != Chem.BondType.SINGLE:
            continue
        a, b = bond.GetBeginAtom(), bond.GetEndAtom()
        if a.GetSymbol() != "C" or b.GetSymbol() != "C":
            continue
        editable = Chem.RWMol(mol)
        editable.RemoveBond(a.GetIdx(), b.GetIdx())
        new_idx = editable.AddAtom(Chem.Atom(6))
        editable.AddBond(a.GetIdx(), new_idx, Chem.BondType.SINGLE)
        editable.AddBond(new_idx, b.GetIdx(), Chem.BondType.SINGLE)
        candidate = _sanitised(editable.GetMol())
        if candidate is not None:
            return [Decoy(_canonical(candidate), DecoyKind.HOMOLOGUE)]
    return []


def _methyl_added(mol: Chem.Mol) -> list[Decoy]:
    """Hang a methyl off the first carbon with a free valence."""

    for atom in mol.GetAtoms():
        if atom.GetSymbol() != "C" or atom.GetTotalNumHs() < 1:
            continue
        editable = Chem.RWMol(mol)
        new_idx = editable.AddAtom(Chem.Atom(6))
        editable.AddBond(atom.GetIdx(), new_idx, Chem.BondType.SINGLE)
        candidate = _sanitised(editable.GetMol())
        if candidate is not None:
            return [Decoy(_canonical(candidate), DecoyKind.METHYL_ADDED)]
    return []


def _ring_substitution(mol: Chem.Mol) -> list[Decoy]:
    """Move a ring substituent to a different ring position — a regioisomer.

    The mistake behind most "is it the ortho or the para isomer?" disputes, and one
    that 2-D correlations resolve but a 1-D shift list often cannot.
    """

    ring_info = mol.GetRingInfo()
    for ring in ring_info.AtomRings():
        ring_set = set(ring)
        # A ring atom carrying an exocyclic heavy substituent.
        for atom_index in ring:
            atom = mol.GetAtomWithIdx(atom_index)
            exo = [
                nbr.GetIdx()
                for nbr in atom.GetNeighbors()
                if nbr.GetIdx() not in ring_set and nbr.GetAtomicNum() > 1
            ]
            if not exo:
                continue
            # A different ring atom that has room for it.
            for target in ring:
                if target == atom_index:
                    continue
                if mol.GetAtomWithIdx(target).GetTotalNumHs() < 1:
                    continue
                editable = Chem.RWMol(mol)
                editable.RemoveBond(atom_index, exo[0])
                editable.AddBond(target, exo[0], Chem.BondType.SINGLE)
                candidate = _sanitised(editable.GetMol())
                if candidate is None:
                    continue
                if _canonical(candidate) != _canonical(mol):
                    return [Decoy(_canonical(candidate), DecoyKind.RING_SUBSTITUTION)]
    return []


def _stereo_inversion(mol: Chem.Mol) -> list[Decoy]:
    """Invert the first assigned stereocentre.

    Generated *because* it is invisible to a topological predictor, so the
    measurement can report that boundary rather than score it as a discrimination.
    """

    centres = Chem.FindMolChiralCenters(mol, includeUnassigned=False, useLegacyImplementation=False)
    if not centres:
        return []
    atom_index = centres[0][0]
    editable = Chem.RWMol(mol)
    atom = editable.GetAtomWithIdx(atom_index)
    tag = atom.GetChiralTag()
    if tag == Chem.ChiralType.CHI_TETRAHEDRAL_CW:
        atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CCW)
    elif tag == Chem.ChiralType.CHI_TETRAHEDRAL_CCW:
        atom.SetChiralTag(Chem.ChiralType.CHI_TETRAHEDRAL_CW)
    else:
        return []
    candidate = _sanitised(editable.GetMol())
    if candidate is None:
        return []
    return [Decoy(Chem.MolToSmiles(candidate), DecoyKind.STEREO_INVERSION)]


def generate_decoys(smiles: str) -> list[Decoy]:
    """Plausibly-wrong variants of ``smiles``, deterministically.

    Raises ``ValueError`` if the input cannot be parsed — an unparseable input is
    a broken test, not a wrong answer, and silently returning ``[]`` would report
    a perfect false-confirmation rate for a corpus that was never scored.
    """

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Could not parse SMILES: {smiles!r}")

    truth = _canonical(mol)
    decoys: list[Decoy] = []
    seen: set[str] = {truth}

    for generator in (
        _heteroatom_swaps,
        _homologue,
        _methyl_added,
        _ring_substitution,
        _stereo_inversion,
    ):
        for decoy in generator(mol):
            # A stereo decoy is *meant* to share the flat skeleton, so it is
            # exempt from the identical-to-truth check that guards the others.
            if decoy.kind is not DecoyKind.STEREO_INVERSION and decoy.smiles in seen:
                continue
            seen.add(decoy.smiles)
            decoys.append(decoy)
    return decoys


def predictions_are_distinguishable(truth_smiles: str, decoy_smiles: str) -> bool:
    """Can this predictor tell these two structures apart at all?

    ``False`` means the two produce the same per-atom HOSE environments, so no
    amount of spectral evidence scored through this predictor can separate them.
    A false-confirmation measurement must report those cases as *indistinguishable*
    rather than counting a coin flip as a correct discrimination.
    """

    from moltrace.spectroscopy.predict.nmrnet_wrapper import hose_code

    def environments(smiles: str) -> list[tuple[str, ...]] | None:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        mol_h = Chem.AddHs(mol)
        return sorted(
            hose_code(mol_h, atom.GetIdx())
            for atom in mol_h.GetAtoms()
            if atom.GetSymbol() in {"C", "H"}
        )

    left, right = environments(truth_smiles), environments(decoy_smiles)
    if left is None or right is None:
        return False
    return left != right
