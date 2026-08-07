"""NMReDATA → HOSE knowledge-base conversion invariants (B0).

Why NMReDATA and not a larger corpus
------------------------------------
A HOSE table is indexed by *atom environment*, so it can only be built from a
source that says which atom each shift belongs to. NMReDATA does: its
``NMREDATA_ASSIGNMENT`` block maps a label to (shift, atom number), and the 1D
blocks say which nucleus owns each label. A corpus of peak lists paired with a
structure — however many millions of records — carries no atom identity and
cannot populate this table at all. That is a structural constraint, not a
preference between datasets.

The invariant that guards everything here: **a ¹H shift must land on a hydrogen
and a ¹³C shift on a carbon.** NMReDATA atom numbers index the molfile's own atom
block, explicit hydrogens included. Rebuilding those molecules through
``SMILES → AddHs`` re-orders the hydrogens, which would attach proton shifts to
the wrong protons and produce a knowledge base that looks entirely healthy while
being wrong everywhere. Nothing downstream could detect it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from rdkit import Chem

from moltrace.spectroscopy.predict.nmrnet_wrapper import (
    build_seed_knowledge_base,
    load_knowledge_base,
)

# scripts/ is not an importable package, so load the builder by path.
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_hose_kb.py"
_spec = importlib.util.spec_from_file_location("build_hose_kb", _SCRIPT)
build_hose_kb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_hose_kb)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests/fixtures/nmrshiftdb2/source/nmrshiftdb2rawdata.nmredata.sd"
)


@pytest.fixture(scope="module")
def records():
    if not FIXTURE.exists():  # pragma: no cover - fixture ships with the repo
        pytest.skip(f"NMReDATA fixture not present: {FIXTURE}")
    return build_hose_kb.build_from_nmredata(FIXTURE)


def test_converts_many_records_not_just_the_first(records):
    """Regression guard for the record splitter.

    Splitting an SD file on ``$$$$`` leaves a stray newline on every chunk after
    the first. A molblock's title line is legitimately empty here, so that stray
    newline shifts the 4-line header and RDKit rejects the record — yielding
    exactly one molecule and no error. The first version of this converter
    produced 1 molecule / 15 assignments instead of 128 / 2568, silently.
    """

    assert len(records) > 100, f"only {len(records)} records parsed — splitter regressed"
    assert sum(len(r["assignments"]) for r in records) > 2000


def test_every_shift_lands_on_the_right_element(records):
    """The corruption this whole design exists to prevent."""

    for record in records:
        mol = Chem.MolFromMolBlock(record["molblock"], removeHs=False)
        assert mol is not None, "emitted a molblock RDKit cannot read back"
        for assignment in record["assignments"]:
            symbol = mol.GetAtomWithIdx(assignment["atom_index"]).GetSymbol()
            expected = "H" if assignment["nucleus"] == "1H" else "C"
            assert symbol == expected, (
                f"{assignment['nucleus']} shift {assignment['shift_ppm']} ppm assigned to "
                f"atom {assignment['atom_index']} which is {symbol}, not {expected}"
            )


def test_records_carry_molblocks_not_smiles(records):
    """Atom identity must survive into the knowledge base exactly as given."""

    assert all("molblock" in r for r in records)
    assert not any("smiles" in r for r in records)


def test_knowledge_base_loads_from_molblock_records(records, tmp_path):
    """``load_knowledge_base`` must honour the molblock branch end to end."""

    path = tmp_path / "kb.json"
    path.write_text(json.dumps(records))

    kb = load_knowledge_base(path)
    assert kb.source == "nmrshiftdb2"
    assert kb.reference_count > 2000
    assert kb.priors.get("13C") is not None


def test_materially_outperforms_the_seed_table(records, tmp_path):
    """The point of the exercise: real coverage on a drug-like molecule.

    Asserted as a *relative* improvement rather than an absolute σ, because the
    absolute number depends on how much of NMRShiftDB2 is available locally and
    should not be frozen into a test.
    """

    from moltrace.spectroscopy.predict.nmrnet_wrapper import hose_code

    path = tmp_path / "kb.json"
    path.write_text(json.dumps(records))
    built = load_knowledge_base(path)
    seed = build_seed_knowledge_base()

    # Paracetamol: how many carbons find a real environment rather than falling
    # back to the element average. This is the functional outcome; the raw
    # reference count is not, so it is reported rather than asserted on.
    mol_h = Chem.AddHs(Chem.MolFromSmiles("CC(=O)Nc1ccc(O)cc1"))
    carbons = [a.GetIdx() for a in mol_h.GetAtoms() if a.GetSymbol() == "C"]

    def matched(kb):
        return sum(1 for idx in carbons if kb.lookup("13C", hose_code(mol_h, idx)) is not None)

    built_hits, seed_hits = matched(built), matched(seed)
    assert built_hits > seed_hits, (
        f"built KB ({built.reference_count} refs) matched {built_hits}/{len(carbons)} "
        f"carbons, no better than the seed ({seed.reference_count} refs, {seed_hits})"
    )
