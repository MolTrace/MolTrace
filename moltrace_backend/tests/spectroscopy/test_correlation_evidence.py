"""Predicted HSQC/HMBC correlations and candidate separation (B6.2)."""

from __future__ import annotations

import pytest

from moltrace.spectroscopy.eval.correlation_evidence import (
    correlation_separation,
    hmbc_correlations,
    hsqc_correlations,
)


def test_hsqc_counts_one_bond_ch_pairs():
    """Ethanol: 3 methyl H + 2 methylene H are C-bound; the OH proton is not."""

    assert len(hsqc_correlations("CCO")) == 5


def test_hsqc_excludes_heteroatom_protons():
    """An O-H or N-H proton has no one-bond carbon partner."""

    assert len(hsqc_correlations("O")) == 0  # water
    methanol = hsqc_correlations("CO")
    assert len(methanol) == 3  # the three C-H, not the O-H


def test_hmbc_excludes_one_bond_and_distant_couplings():
    """HMBC is the 2-3 bond window; 1-bond belongs to HSQC.

    The 4-bond case (allylic, W) exists but is weak and inconsistent, so
    predicting it as if it were reliable would manufacture evidence.
    """

    hsqc = set(hsqc_correlations("CCCCO"))
    hmbc = set(hmbc_correlations("CCCCO"))
    assert hsqc and hmbc
    assert not (hsqc & hmbc), "a correlation cannot be both one-bond and 2-3 bond"


def test_signature_is_independent_of_how_the_smiles_is_written():
    """A structure property must not change with its spelling."""

    assert hmbc_correlations("CCO") == hmbc_correlations("OCC")
    assert hmbc_correlations("c1ccccc1C") == hmbc_correlations("Cc1ccccc1")


def test_identical_structures_are_not_separated():
    sep = correlation_separation("CCCCO", "CCCCO")
    assert sep.hmbc_symmetric_difference == 0
    assert sep.hsqc_symmetric_difference == 0
    assert sep.separated is False
    assert sep.hmbc_separation_ratio == 0.0


def test_regioisomers_are_separated_by_hmbc():
    """The case ¹³C shift lists resolve at only 37.7 %.

    ortho- vs para-cresol have identical formulas, identical carbon counts and very
    similar shifts — but a different substitution pattern puts different protons
    within 2-3 bonds of different carbons, which is what HMBC reports.
    """

    sep = correlation_separation("Cc1ccccc1O", "Cc1ccc(O)cc1")
    assert sep.separated is True
    assert sep.hmbc_symmetric_difference > 0
    assert sep.hmbc_separation_ratio > 0.1, (
        f"only {sep.hmbc_separation_ratio:.1%} of HMBC correlations differ — too "
        "little for 2-D to be the answer to regiochemistry"
    )


def test_stereoisomers_are_not_separated():
    """Honest boundary: HMBC topology cannot see stereochemistry either.

    2-D correlations fix regiochemistry, not stereochemistry — that needs NOE or
    J-couplings. Claiming otherwise would repeat the overclaim this program exists
    to prevent.
    """

    sep = correlation_separation("C[C@H](O)CC", "C[C@@H](O)CC")
    assert sep.hmbc_symmetric_difference == 0
    assert sep.separated is False


def test_rejects_unparseable_input():
    with pytest.raises(ValueError, match="SMILES"):
        hmbc_correlations("not-a-molecule((((")
