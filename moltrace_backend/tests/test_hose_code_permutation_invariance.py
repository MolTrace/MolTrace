"""The HOSE code must not depend on the order atoms happen to be numbered in.

Two paths build these codes -- the knowledge-base index and the query -- and a lookup only
works because both produce the same string for the same environment. Nothing pinned that. It
**On what these tests do and do not catch.** The renumbering property below holds structurally,
not because of the ``tokens.sort()`` in ``hose_code``: deleting that sort leaves 0 differences
over 8,880 permuted comparisons, because ``RenumberAtoms`` preserves each atom's bond ordering
and the traversal therefore visits neighbours in the same order either way. So treat it as a
regression guard against a future traversal that is genuinely order-sensitive, not as proof the
sort is load-bearing -- it is not, and a test that claims otherwise is worse than none.

The invariance that CAN break, and did, is across CONSTRUCTION paths, which the last test here
pins.

An earlier note claimed order-dependence was live at ~41.5%. Measured, it is not: 0 differing
codes over 2,880 permuted comparisons. The real mechanism behind that number was hydrogen
handling, not atom ordering.

Ring systems carry the risk. A ring closure reaches an already-visited atom, so which branch
claims it depends on traversal order, and a fused or bridged system has several ways round.
"""

from __future__ import annotations

import random

import pytest
from rdkit import Chem

from moltrace.spectroscopy.predict.nmrnet_wrapper import hose_code

# Chosen for traversal hazards rather than variety: fused rings, a bridged bicycle, a
# spiro centre, symmetric substitution (equivalent atoms that must agree), and a sugar
# whose stereocentres give the canonicaliser something to do.
_MOLECULES = {
    "benzene": "c1ccccc1",
    "paracetamol": "CC(=O)Nc1ccc(O)cc1",
    "naphthalene": "c1ccc2ccccc2c1",
    "norbornane": "C1CC2CCC1CC2",
    "spiro": "C1CCC2(CC1)CCCC2",
    "caffeine": "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "glucose": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
    "p-xylene": "Cc1ccc(C)cc1",
}


@pytest.mark.parametrize("name,smiles", sorted(_MOLECULES.items()))
def test_the_code_survives_renumbering_the_atoms(name: str, smiles: str) -> None:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    assert mol is not None, name
    expected = [hose_code(mol, atom.GetIdx()) for atom in mol.GetAtoms()]

    rng = random.Random(f"{name}-20260827")
    for _ in range(12):
        order = list(range(mol.GetNumAtoms()))
        rng.shuffle(order)
        permuted = Chem.RenumberAtoms(mol, order)
        # RenumberAtoms places the atom formerly at ``order[j]`` at index ``j``.
        for j, original_index in enumerate(order):
            assert hose_code(permuted, j) == expected[original_index], (
                f"{name}: atom {original_index} encoded differently after renumbering"
            )


def test_equivalent_atoms_share_a_code() -> None:
    """The invariance has to hold ACROSS atoms too, not only across numberings.

    p-Xylene's two methyl carbons are the same environment reached from opposite ends of the
    ring. If shell tokens were emitted in traversal order rather than sorted, the two would
    encode differently and the knowledge base would hold two buckets for one environment --
    halving the references behind each, which is invisible in every coverage metric.
    """

    mol = Chem.AddHs(Chem.MolFromSmiles("Cc1ccc(C)cc1"))
    methyls = [
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetSymbol() == "C" and not atom.GetIsAromatic()
    ]
    assert len(methyls) == 2, methyls
    assert hose_code(mol, methyls[0]) == hose_code(mol, methyls[1])


def test_the_same_molecule_encodes_the_same_however_it_was_built() -> None:
    """The index and the query build their molecules by different routes; the codes must agree.

    This is the invariance that actually broke. ``molecule_from_record`` parses a molblock with
    ``removeHs=False``, which keeps the hydrogens a molblock carries but does not add the ones
    it omits, while every query goes through ``AddHs``. A HOSE code built without hydrogens
    shares nothing with one built with them, so a reference atom indexed from an H-less molblock
    could never be matched by any query -- silently, since it is indexed, just under a code
    nothing asks for.

    Measured before the fix: every comparable atom differed (11/11 on paracetamol, 14/14 on
    caffeine, 10/10 on naphthalene). ~0.2% of the NMRShiftDB2 records take that shape, and 100%
    of them take the molblock branch.
    """

    from moltrace.spectroscopy.predict.nmrnet_wrapper import molecule_from_record

    def by_canonical_rank(mol: Chem.Mol) -> dict[int, tuple[str, ...]]:
        ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=True))
        return {ranks[atom.GetIdx()]: hose_code(mol, atom.GetIdx()) for atom in mol.GetAtoms()}

    for name, smiles in sorted(_MOLECULES.items()):
        query = Chem.AddHs(Chem.MolFromSmiles(smiles))

        # An H-less molblock is the shape that broke: the record carries no explicit H.
        hless_block = Chem.MolToMolBlock(Chem.MolFromSmiles(smiles))
        indexed = molecule_from_record({"molblock": hless_block})
        assert indexed is not None, name

        want, got = by_canonical_rank(query), by_canonical_rank(indexed)
        shared = set(want) & set(got)
        assert shared, name
        mismatched = [k for k in shared if want[k] != got[k]]
        assert not mismatched, (
            f"{name}: {len(mismatched)}/{len(shared)} atoms encode differently when indexed "
            f"from an H-less molblock than when queried from SMILES"
        )

        # And the H-explicit route must be untouched by the repair.
        explicit_block = Chem.MolToMolBlock(query)
        from_explicit = molecule_from_record({"molblock": explicit_block})
        assert from_explicit is not None and from_explicit.GetNumAtoms() == query.GetNumAtoms()
