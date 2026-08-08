"""Constitutional-isomer enumeration from formula + HSQC constraints (B6.2).

The acceptance test is a textbook answer: C4H10O has exactly **seven**
constitutional isomers — four alcohols (n-, iso-, sec-, tert-butanol) and three
ethers (diethyl, methyl propyl, methyl isopropyl). An enumerator that misses one
is unsound; one that invents an eighth is wrong. Both failures are silent without
a case whose answer is known independently of the code under test.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from moltrace.spectroscopy.case.enumeration import (
    EnumerationBounds,
    enumerate_structures,
    parse_formula,
)


def _canonical(smiles: str) -> str:
    return Chem.MolToSmiles(Chem.MolFromSmiles(smiles))


# --------------------------------------------------------------------------- #
# Formula parsing refuses rather than guesses
# --------------------------------------------------------------------------- #
def test_parses_a_formula_into_heavy_atoms_and_hydrogens():
    heavy, hydrogens = parse_formula("C7H8O")
    assert sorted(heavy) == ["C"] * 7 + ["O"]
    assert hydrogens == 8


def test_parses_multi_digit_and_two_letter_elements():
    heavy, hydrogens = parse_formula("C10H12ClN")
    assert heavy.count("C") == 10
    assert heavy.count("Cl") == 1
    assert heavy.count("N") == 1
    assert hydrogens == 12


@pytest.mark.parametrize("bad", ["", "   ", "7C8H", "C7H8?"])
def test_unparseable_formula_refuses(bad):
    with pytest.raises(ValueError):
        parse_formula(bad)


def test_untabulated_element_refuses_rather_than_guessing_a_valence():
    with pytest.raises(ValueError, match="valence"):
        parse_formula("C4H10Fe")


# --------------------------------------------------------------------------- #
# The known answer
# --------------------------------------------------------------------------- #
def test_c4h10o_yields_exactly_the_seven_textbook_isomers():
    result = enumerate_structures("C4H10O")
    assert result.complete is True

    expected = {
        _canonical(s)
        for s in (
            "CCCCO",  # n-butanol
            "CC(C)CO",  # isobutanol
            "CCC(C)O",  # sec-butanol
            "CC(C)(C)O",  # tert-butanol
            "CCOCC",  # diethyl ether
            "CCCOC",  # methyl propyl ether
            "COC(C)C",  # methyl isopropyl ether
        )
    }
    assert {_canonical(s) for s in result.candidates} == expected


def test_every_candidate_matches_the_requested_formula():
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula

    result = enumerate_structures("C4H10O")
    for smiles in result.candidates:
        assert CalcMolFormula(Chem.MolFromSmiles(smiles)) == "C4H10O"


def test_candidates_are_unique_and_deterministic():
    a = enumerate_structures("C4H10O").candidates
    b = enumerate_structures("C4H10O").candidates
    assert a == b
    assert len(set(a)) == len(a)


def test_unsaturation_is_handled():
    """C3H6O has one degree of unsaturation — carbonyls, alkenes and rings."""

    result = enumerate_structures("C3H6O")
    assert result.complete
    found = {_canonical(s) for s in result.candidates}
    assert _canonical("CC(C)=O") in found, "acetone missing"
    assert _canonical("CCC=O") in found, "propanal missing"


# --------------------------------------------------------------------------- #
# HSQC constraints — why 2-D matters for generation, not only for ranking
# --------------------------------------------------------------------------- #
def test_carbon_hydrogen_counts_prune_the_candidate_set():
    """n-butanol's carbons are CH3, CH2, CH2, CH2 — only one isomer fits."""

    unconstrained = enumerate_structures("C4H10O")
    constrained = enumerate_structures("C4H10O", carbon_hydrogen_counts=(3, 2, 2, 2))

    assert constrained.complete
    assert len(constrained.candidates) < len(unconstrained.candidates)
    assert {_canonical(s) for s in constrained.candidates} == {_canonical("CCCCO")}


def test_tert_butanol_is_isolated_by_its_quaternary_carbon():
    """Three CH3 and one carbon bearing no hydrogens is only tert-butanol."""

    result = enumerate_structures("C4H10O", carbon_hydrogen_counts=(3, 3, 3, 0))
    assert {_canonical(s) for s in result.candidates} == {_canonical("CC(C)(C)O")}


def test_carbon_hydrogen_counts_are_matched_as_a_multiset():
    """HSQC does not say which carbon is which, so order must not matter."""

    a = enumerate_structures("C4H10O", carbon_hydrogen_counts=(3, 2, 2, 2))
    b = enumerate_structures("C4H10O", carbon_hydrogen_counts=(2, 2, 3, 2))
    assert a.candidates == b.candidates


def test_wrong_number_of_carbon_counts_refuses():
    with pytest.raises(ValueError, match="carbons"):
        enumerate_structures("C4H10O", carbon_hydrogen_counts=(3, 2, 2))


def test_impossible_hydrogen_counts_refuse():
    with pytest.raises(ValueError, match="hydrogens"):
        enumerate_structures("C4H10O", carbon_hydrogen_counts=(4, 4, 4, 4))


# --------------------------------------------------------------------------- #
# Bounds refuse; they never truncate silently
# --------------------------------------------------------------------------- #
def test_too_many_heavy_atoms_refuses_with_a_named_cause():
    result = enumerate_structures("C20H42", bounds=EnumerationBounds(max_heavy_atoms=7))
    assert result.refused is True
    assert result.complete is False
    assert result.candidates == ()
    assert "heavy atoms" in (result.refusal_reason or "")


def test_node_budget_exhaustion_refuses_rather_than_returning_a_partial_list():
    """A truncated list invites 'the true structure is absent' when it was never reached."""

    result = enumerate_structures("C6H14O", bounds=EnumerationBounds(max_nodes=500))
    assert result.refused is True
    assert result.candidates == ()
    assert "budget" in (result.refusal_reason or "").lower()


def test_candidate_overflow_refuses():
    result = enumerate_structures("C4H10O", bounds=EnumerationBounds(max_candidates=2))
    assert result.refused is True
    assert "isomers are consistent" in (result.refusal_reason or "")


def test_complete_is_false_whenever_refused():
    refused = enumerate_structures("C30H62", bounds=EnumerationBounds(max_heavy_atoms=7))
    assert refused.complete is False


# --------------------------------------------------------------------------- #
# Stated boundary
# --------------------------------------------------------------------------- #
def test_stereochemistry_is_not_enumerated_and_says_so():
    """Topological correlations cannot distinguish stereoisomers.

    Emitting stereoisomers would imply evidence the inputs do not contain.
    """

    result = enumerate_structures("C4H10O")
    assert any("stereo" in note.lower() for note in result.notes)
    for smiles in result.candidates:
        assert "@" not in smiles
