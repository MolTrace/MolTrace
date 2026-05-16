from __future__ import annotations

import re

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

from .exceptions import StructureParseError
from .models import StructureSummary

LABILE_ATOMIC_NUMBERS = {7, 8, 16}  # N, O, S
SMILES_ALLOWED_PATTERN = re.compile(r"^[A-Za-z0-9@+\-\[\]\(\)=#$\\/%.]+$")


def _prevalidate_smiles(smiles: str) -> str:
    value = smiles.strip()
    if not value:
        raise StructureParseError("SMILES cannot be empty.")
    if any(ch.isspace() for ch in value):
        raise StructureParseError("SMILES must not contain spaces or line breaks.")
    if "," in value or ";" in value:
        raise StructureParseError("SMILES must not contain commas or semicolons.")
    lowered = value.lower()
    if "1h nmr" in lowered or "δ" in value:
        raise StructureParseError("SMILES input appears to contain NMR text rather than a structure string.")
    if not SMILES_ALLOWED_PATTERN.fullmatch(value):
        raise StructureParseError("SMILES contains unsupported characters.")
    return value


def mol_from_smiles(smiles: str) -> Chem.Mol:
    candidate = _prevalidate_smiles(smiles)
    mol = Chem.MolFromSmiles(candidate)
    if mol is None:
        raise StructureParseError(f"Invalid SMILES: {candidate!r}")
    return mol


def count_total_hydrogens(mol: Chem.Mol) -> int:
    return sum(atom.GetTotalNumHs(includeNeighbors=False) for atom in mol.GetAtoms())


def count_labile_hydrogens(mol: Chem.Mol) -> int:
    labile = 0
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() in LABILE_ATOMIC_NUMBERS:
            labile += atom.GetTotalNumHs(includeNeighbors=False)
    return labile


def count_hydroxyl_protons(mol: Chem.Mol) -> int:
    """Count O-H protons (hydroxyls, carboxylic-acid OH, phenols, enols).

    Implementation: for every oxygen atom, sum its implicit + explicit H count
    via RDKit's ``GetTotalNumHs``. This counts ANY proton bonded to an oxygen
    — there is no need to distinguish phenol vs alcohol vs COOH OH for the
    "is this proton labile and what element" question.
    """
    return sum(
        atom.GetTotalNumHs(includeNeighbors=False)
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() == 8
    )


def count_amine_amide_protons(mol: Chem.Mol) -> int:
    """Count N-H protons (primary/secondary amines, amides, anilines, NH in heterocycles)."""
    return sum(
        atom.GetTotalNumHs(includeNeighbors=False)
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() == 7
    )


def count_thiol_protons(mol: Chem.Mol) -> int:
    """Count S-H protons (thiols, thiophenols)."""
    return sum(
        atom.GetTotalNumHs(includeNeighbors=False)
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() == 16
    )


def count_olefinic_protons(mol: Chem.Mol) -> int:
    """Count vinyl / olefinic protons.

    A proton is olefinic when it sits on an sp2 carbon that is part of a C=C
    bond and is NOT aromatic. Aromatic CH already lives under
    ``aromatic_protons``; this counter exclusively captures non-aromatic
    alkenyl / vinyl / styrene-side-chain protons.

    Used by the 1H peak categoriser to disambiguate the 4.4–6.0 ppm window:
    when ``count_olefinic_protons(mol) > 0`` and ``count_anomeric_protons(mol)
    == 0``, peaks in that window are confidently olefinic; otherwise they
    are anomeric (or ambiguous).
    """
    count = 0
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6:
            continue
        if atom.GetIsAromatic():
            continue
        # Find a C=C bond on this atom (any double bond to another carbon).
        for bond in atom.GetBonds():
            if bond.GetBondType() != Chem.BondType.DOUBLE:
                continue
            other = bond.GetOtherAtom(atom)
            if other.GetAtomicNum() != 6:
                continue
            # Exclude aromatic-bond doubles (Kekulised aromatic rings).
            if bond.GetIsAromatic() or other.GetIsAromatic():
                continue
            count += atom.GetTotalNumHs(includeNeighbors=False)
            break  # avoid double-counting a CH in a conjugated dienic CH=CH-CH=CH
    return count


def count_anomeric_protons(mol: Chem.Mol) -> int:
    """Count anomeric / acetal protons.

    Anomeric definition (carbohydrate convention, Silverstein 8e §4.4.5;
    Pretsch 5e §H.3.2): a tetrahedral sp3 carbon bearing exactly one H and
    bonded to *two* oxygen atoms — typically a sugar C-1 carrying both a
    ring oxygen and a glycosidic / hemiacetal / acetal OR. Their 1H shifts
    cluster in 4.4–5.5 ppm in CDCl3 / D2O / DMSO-d6.

    Implementation: for every non-aromatic carbon, count its oxygen
    neighbours connected by a single bond. When two or more oxygens are
    attached, the carbon's H count is added to the anomeric total. This
    rule captures all classical anomeric / acetal / ketal / orthoester
    centres without false-positives on simple ethers (one O) or esters
    (sp2 / one O).
    """
    count = 0
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6:
            continue
        if atom.GetIsAromatic():
            continue
        oxygen_neighbours = 0
        for bond in atom.GetBonds():
            if bond.GetBondType() != Chem.BondType.SINGLE:
                continue
            other = bond.GetOtherAtom(atom)
            if other.GetAtomicNum() == 8:
                oxygen_neighbours += 1
        if oxygen_neighbours >= 2:
            count += atom.GetTotalNumHs(includeNeighbors=False)
    return count


def count_aromatic_atoms(mol: Chem.Mol) -> int:
    return sum(1 for atom in mol.GetAtoms() if atom.GetIsAromatic())


def count_aromatic_protons(mol: Chem.Mol) -> int:
    return sum(
        atom.GetTotalNumHs(includeNeighbors=False)
        for atom in mol.GetAtoms()
        if atom.GetIsAromatic()
    )


def count_aliphatic_protons(mol: Chem.Mol) -> int:
    return sum(
        atom.GetTotalNumHs(includeNeighbors=False)
        for atom in mol.GetAtoms()
        if atom.GetAtomicNum() == 6 and not atom.GetIsAromatic()
    )


def structure_summary_from_smiles(smiles: str) -> StructureSummary:
    candidate = _prevalidate_smiles(smiles)
    mol = mol_from_smiles(candidate)
    total_h = count_total_hydrogens(mol)
    labile_h = count_labile_hydrogens(mol)
    oh_h = count_hydroxyl_protons(mol)
    nh_h = count_amine_amide_protons(mol)
    sh_h = count_thiol_protons(mol)
    olefinic_h = count_olefinic_protons(mol)
    anomeric_h = count_anomeric_protons(mol)
    non_labile_h = total_h - labile_h
    formula = rdMolDescriptors.CalcMolFormula(mol)
    mw = round(float(Descriptors.MolWt(mol)), 4)
    aromatic_atoms = count_aromatic_atoms(mol)
    aromatic_protons = count_aromatic_protons(mol)
    aliphatic_protons = count_aliphatic_protons(mol)
    return StructureSummary(
        smiles=candidate,
        formula=formula,
        molecular_weight=mw,
        total_hydrogens=total_h,
        labile_hydrogens=labile_h,
        oh_hydrogen_count=oh_h,
        nh_hydrogen_count=nh_h,
        sh_hydrogen_count=sh_h,
        olefinic_proton_count=olefinic_h,
        anomeric_proton_count=anomeric_h,
        non_labile_hydrogens=non_labile_h,
        aromatic_protons=aromatic_protons,
        aliphatic_protons=aliphatic_protons,
        aromatic_atom_count=aromatic_atoms,
    )
