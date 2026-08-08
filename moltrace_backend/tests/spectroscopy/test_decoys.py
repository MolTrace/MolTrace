"""Decoy structure generation for false-confirmation measurement (B5.2).

Why decoys
----------
Accuracy on *correct* structures says nothing about how often a **wrong** one gets
confirmed, and that is the safety-critical direction: a verification system that
has never been shown a wrong answer has not been tested. The eval harness already
treats ``false_confirmation_rate`` as a zero-regression metric; it had no way to
produce the wrong answers to measure it with.

A decoy must be *plausibly* wrong — a random molecule is trivially rejected and
proves nothing. These are the mistakes a chemist actually makes: a heteroatom
misread, a homologue off by one CH₂, a methyl in the wrong place, a stereocentre
inverted.

The stereo case is deliberate
-----------------------------
HOSE codes are **topological**. A stereoisomer has the identical connectivity, so
it produces an identical code and therefore an identical prediction. A stereo
decoy is consequently *indistinguishable* from the truth by this predictor — not
a bug, a stated capability boundary. It is generated and labelled precisely so the
false-confirmation measurement reports that honestly rather than quietly scoring
stereoisomers as if they had been discriminated.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from moltrace.spectroscopy.eval.decoys import (
    DecoyKind,
    generate_decoys,
    predictions_are_distinguishable,
)


def _canonical(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    return Chem.MolToSmiles(mol) if mol else ""


REAL_MOLECULES = [
    "CC(=O)Nc1ccc(O)cc1",  # paracetamol
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O",  # ibuprofen
    "CCCCO",  # butanol
    "c1ccc(cc1)C(=O)OC",  # methyl benzoate
]


def test_generates_decoys_for_real_molecules():
    for smiles in REAL_MOLECULES:
        decoys = generate_decoys(smiles)
        assert decoys, f"no decoys generated for {smiles}"


def test_every_decoy_is_a_valid_molecule():
    """An invalid decoy is not a wrong answer, it is a broken input."""

    for smiles in REAL_MOLECULES:
        for decoy in generate_decoys(smiles):
            mol = Chem.MolFromSmiles(decoy.smiles)
            assert mol is not None, f"{decoy.kind} produced unparseable {decoy.smiles!r}"


def test_no_decoy_is_the_truth_in_disguise():
    """A decoy identical to the truth would score as a false confirmation forever.

    Compared canonically, because the same structure written two ways is still the
    same structure.
    """

    for smiles in REAL_MOLECULES:
        truth = _canonical(smiles)
        for decoy in generate_decoys(smiles):
            if decoy.kind is DecoyKind.STEREO_INVERSION:
                continue  # differs only in stereochemistry; see the dedicated test
            assert _canonical(decoy.smiles) != truth, (
                f"{decoy.kind} regenerated the truth for {smiles}"
            )


def test_decoys_are_deterministic():
    """A false-confirmation rate has to be reproducible."""

    a = [(d.kind, d.smiles) for d in generate_decoys("CC(=O)Nc1ccc(O)cc1")]
    b = [(d.kind, d.smiles) for d in generate_decoys("CC(=O)Nc1ccc(O)cc1")]
    assert a == b


def test_each_decoy_names_its_kind():
    """The report needs to say *how* it was wrong, not just that it was."""

    for decoy in generate_decoys("CC(=O)Nc1ccc(O)cc1"):
        assert isinstance(decoy.kind, DecoyKind)


def test_generates_several_distinct_kinds_across_a_corpus():
    kinds = set()
    for smiles in REAL_MOLECULES:
        kinds.update(d.kind for d in generate_decoys(smiles))
    assert len(kinds) >= 3, f"only produced {kinds}"


# --------------------------------------------------------------------------- #
# The capability boundary this measurement must not paper over
# --------------------------------------------------------------------------- #
def test_stereoisomer_decoy_is_topologically_identical():
    """HOSE codes cannot see stereochemistry — stated, not hidden.

    The source proposal this program reviewed claimed ">99.5% stereochemical
    resolution". This predictor resolves *none*: a stereoisomer has identical
    connectivity, hence an identical HOSE code, hence an identical prediction.
    """

    chiral = "C[C@H](O)CC"
    decoys = [d for d in generate_decoys(chiral) if d.kind is DecoyKind.STEREO_INVERSION]
    if not decoys:
        pytest.skip("no stereocentre available in the probe molecule")

    decoy = decoys[0]
    assert _canonical(decoy.smiles) != _canonical(chiral), "stereochemistry did not change"

    # Same skeleton once stereochemistry is stripped — that is why it is invisible.
    def flat(s: str) -> str:
        mol = Chem.MolFromSmiles(s)
        Chem.RemoveStereochemistry(mol)
        return Chem.MolToSmiles(mol)

    assert flat(decoy.smiles) == flat(chiral)
    assert predictions_are_distinguishable(chiral, decoy.smiles) is False, (
        "a stereo decoy must be reported as indistinguishable, not silently scored"
    )


def test_constitutional_decoys_are_distinguishable():
    """A real skeletal change must actually change the prediction.

    Otherwise the false-confirmation measurement is scoring noise.
    """

    distinguishable = [
        d
        for d in generate_decoys("CCCCO")
        if d.kind is not DecoyKind.STEREO_INVERSION
        and predictions_are_distinguishable("CCCCO", d.smiles)
    ]
    assert distinguishable, "no constitutional decoy changed the predicted shifts at all"


def test_rejects_unparseable_input():
    with pytest.raises(ValueError, match="SMILES"):
        generate_decoys("not-a-molecule((((")
