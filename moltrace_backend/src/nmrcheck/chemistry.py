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
        non_labile_hydrogens=non_labile_h,
        aromatic_protons=aromatic_protons,
        aliphatic_protons=aliphatic_protons,
        aromatic_atom_count=aromatic_atoms,
    )
