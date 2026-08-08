"""The retrieval corpus grounds the reasoning; it is not redistributed.

`spectrum_similarity_index/` is 42,449 NMRShiftDB2 records, every one carrying:

    "license": "CC-BY-SA (NMRShiftDB2) - local use only, do not distribute"

`POST /spectrum/reason` used to return each retrieved record's SMILES verbatim
to any authenticated caller, with `allowed_licenses` defaulting to `None`, which
resolved to no filtering at all. The licence terms travelled in the response
alongside the data they forbade sending.

CC-BY-SA's share-alike clause obliges derivatives to carry the same licence.
This product is BUSL 1.1, so it cannot satisfy that and also redistribute the
work. The gate therefore fails CLOSED: `_REDISTRIBUTABLE_LICENCES` is empty, and
a licence is added only when someone has established that its terms allow it.

**What is withheld is the structure, not the retrieval.** The corpus still does
its job — it builds the reasoner's prompt and backs the hallucination guard,
both internal processing rather than distribution — and the caller still gets
the similarity, rank, citation id and shift summary needed to judge how well
grounded a proposal is. Only the record itself stays behind.

This is a code guard reflecting a legal reading, not a legal opinion. The
residual question worth a real answer: a structure the reasoner PROPOSES for the
user's own spectrum, having seen CC-BY-SA precedent, is not a reproduction of
the corpus — but nobody here has ruled on it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from nmrcheck.api import _may_redistribute, _to_reason_analogue


@dataclass(frozen=True)
class _Analogue:
    """Duck-typed stand-in for rag.RetrievedAnalogue."""

    analogue_id: str = "nmrshiftdb2:234"
    smiles: str = "C1(C(C(C2(C(C1([H])[H])..."
    l2_distance: float = 0.4
    similarity: float = 0.87
    rank: int = 1
    license: str = "CC-BY-SA (NMRShiftDB2) - local use only, do not distribute"
    shift_summary: str | None = "0x 1H, 14x 13C"
    multiplet_summary: str | None = "m, 3H"
    source: str | None = "nmrshiftdb2.nmredata.sd"


class TestTheGateFailsClosed:
    def test_the_shipped_corpus_licence_is_not_redistributable(self) -> None:
        assert not _may_redistribute(
            "CC-BY-SA (NMRShiftDB2) - local use only, do not distribute"
        )

    @pytest.mark.parametrize("licence", ["", None, "unknown", "something-new"])
    def test_an_unrecognised_licence_is_not_redistributable(self, licence) -> None:
        """Unknown must mean no. An allowlist that defaults open is not a gate."""
        assert not _may_redistribute(licence)


def test_the_structure_is_withheld_for_the_shipped_corpus() -> None:
    wire = _to_reason_analogue(_Analogue())

    assert wire.smiles == "", "a CC-BY-SA record's structure was sent to the caller"
    assert wire.structure_withheld is True
    assert wire.multiplet_summary is None


def test_what_grounds_the_answer_still_reaches_the_caller() -> None:
    """Withholding the record must not blind the reviewer.

    A chemist judging whether a proposal is well grounded needs to know how
    close the precedent was and how many there were — not what it was.
    """
    wire = _to_reason_analogue(_Analogue())

    assert wire.analogue_id == "nmrshiftdb2:234", "the citation id must survive"
    assert wire.similarity == pytest.approx(0.87)
    assert wire.rank == 1
    assert wire.shift_summary == "0x 1H, 14x 13C", "a coarse count is not the data"
    assert wire.license, "the terms must travel so a consumer can see why"


def test_a_permissive_licence_would_pass_through_intact() -> None:
    """The mechanism is a gate, not a blanket redaction.

    Monkeypatched rather than shipped-open: this proves the path exists for a
    corpus whose terms allow it, without asserting that any current licence does.
    """
    import nmrcheck.api as api

    original = api._REDISTRIBUTABLE_LICENCES
    api._REDISTRIBUTABLE_LICENCES = frozenset({"CC0-1.0"})
    try:
        wire = _to_reason_analogue(_Analogue(license="CC0-1.0"))
        assert wire.smiles.startswith("C1("), "a permissive record was redacted anyway"
        assert wire.structure_withheld is False
        assert wire.multiplet_summary == "m, 3H"
    finally:
        api._REDISTRIBUTABLE_LICENCES = original


def test_the_corpus_on_disk_still_carries_its_terms() -> None:
    """If the metadata ever stops saying this, the gate's premise changed."""
    import json
    from pathlib import Path

    index = (
        Path(__file__).resolve().parent.parent / "spectrum_similarity_index" / "metadata.json"
    )
    if not index.exists():
        pytest.skip("similarity index not staged locally")

    records = json.loads(index.read_text())
    licences = {
        value.get("license") for value in records.values() if isinstance(value, dict)
    }
    assert licences, "the index carries no licence metadata at all"
    assert all(not _may_redistribute(licence) for licence in licences), (
        f"a corpus licence is now on the redistributable list: {licences}. "
        "If that was deliberate, say who established it and where."
    )
