"""NMReDATA -> similarity-corpus converter (scripts/nmredata_to_corpus.py).

Unit-tests the pure parser: shift extraction (skipping the interleaved ``Larmor=`` /
``Spectrum_Location=`` metadata rows), property-block termination, SMILES de-duplication,
and the sidecar shape. Plus one guard against the failure mode that actually bites here —
a parser that silently yields ZERO molecules from a real export, which is what
``scripts/build_hose_kb.py`` does with this same fixture because its regex does not match
the ``NMREDATA_1D_*`` property names.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
import json
from pathlib import Path

# The converter is a standalone script, not part of the nmrcheck package — load it by
# path. tests/ -> moltrace_backend/ -> scripts/nmredata_to_corpus.py
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "nmredata_to_corpus.py"
_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "nmrshiftdb2"
    / "source"
    / "nmrshiftdb2rawdata.nmredata.sd"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("nmredata_to_corpus", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


conv = _load_module()


def test_parse_shifts_skips_metadata_rows() -> None:
    lines = [
        "Spectrum_Location=http://example.org/x.zip?spectrumid=1&format=rawdata",
        "Larmor=600.1300048828125",
        "2.59, L=s6",
        "3.13, L=s8",
        "-0.25, L=s9",
    ]
    assert conv.parse_shifts(lines) == [2.59, 3.13, -0.25]


def test_parse_property_blocks_terminates_on_blank_line() -> None:
    record = "\n".join(
        [
            "> <NMREDATA_1D_1H>",
            "2.59, L=s6",
            "",
            "> <CHEMNAME>",
            "caffeine",
        ]
    )
    blocks = conv.parse_property_blocks(record)
    assert blocks["NMREDATA_1D_1H"] == ["2.59, L=s6"]
    assert blocks["CHEMNAME"] == ["caffeine"]


def test_convert_dedupes_by_smiles_keeping_the_richer_record(tmp_path: Path) -> None:
    def _record(db_id: str, protons: list[str]) -> str:
        return "\n".join(
            ["> <NMREDATA_SMILES>", "CCO", "", "> <NMREDATA_ID>", f"DB_ID={db_id}", "", "> <NMREDATA_1D_1H>", *protons, ""]
        )

    src = tmp_path / "dup.sd"
    src.write_text(
        _record("1", ["1.10, L=s1"]) + "\n$$$$\n" + _record("2", ["1.10, L=s1", "3.60, L=s2"]) + "\n$$$$\n",
        encoding="utf-8",
    )
    records, stats = conv.convert(src)
    assert stats["duplicates"] == 1
    assert len(records) == 1
    # RE-BASELINED when merging went per-nucleus: the richer 1H list still wins, but
    # a merged record is a COMPOSITE, so its `id` is now the deterministic first-seen
    # label rather than the winning record's DB_ID. The real per-nucleus source moved
    # to `provenance`, which is the only place that can stay truthful once 1H and 13C
    # may come from two different measurements.
    assert records[0]["shifts_1h"] == [1.10, 3.60]
    assert records[0]["id"] == "nmrshiftdb2:1"
    assert records[0]["provenance"]["shifts_1h"]["db_id"] == "2"


def test_convert_merges_single_nucleus_records_for_the_same_molecule(tmp_path: Path) -> None:
    """The case global keep-max silently destroyed.

    The full export is one-record-per-spectrum and nucleus-grouped, so a molecule
    routinely appears as a 1H-only record and a separate 13C-only record. Picking
    whichever single record had more shifts discarded the other nucleus outright.
    """
    proton = "\n".join(
        ["> <NMREDATA_SMILES>", "CCO", "", "> <NMREDATA_ID>", "DB_ID=10", "",
         "> <NMREDATA_SOLVENT>", "CDCl3", "",
         "> <NMREDATA_1D_1H>", "1.20, L=s1", "3.70, L=s2", "3.80, L=s3", ""]
    )
    carbon = "\n".join(
        ["> <NMREDATA_SMILES>", "CCO", "", "> <NMREDATA_ID>", "DB_ID=11", "",
         "> <NMREDATA_SOLVENT>", "DMSO", "",
         "> <NMREDATA_1D_13C>", "18.4, L=s1", ""]
    )
    src = tmp_path / "split.sd"
    src.write_text(f"{proton}\n$$$$\n{carbon}\n$$$$\n", encoding="utf-8")

    records, stats = conv.convert(src)
    assert len(records) == 1
    rec = records[0]
    # Both nuclei survive -- global keep-max would have kept only the 3-shift 1H record.
    assert rec["shifts_1h"] == [1.20, 3.70, 3.80]
    assert rec["shifts_13c"] == [18.4]
    assert stats["merged_nuclei"] == 1
    # Each nucleus is attributed to the measurement it actually came from...
    assert rec["provenance"]["shifts_1h"]["db_id"] == "10"
    assert rec["provenance"]["shifts_13c"]["db_id"] == "11"
    # ...which is what lets the cross-solvent caveat be counted rather than hidden.
    assert stats["cross_solvent_merges"] == 1


def test_convert_does_not_union_remeasurements_of_the_same_nucleus(tmp_path: Path) -> None:
    """Two records for the SAME nucleus are re-measurements, not extra peaks.

    Unioning them would double-count; the richest list wins instead.
    """
    def _carbon(db_id: str, shifts: list[str]) -> str:
        return "\n".join(
            ["> <NMREDATA_SMILES>", "CCO", "", "> <NMREDATA_ID>", f"DB_ID={db_id}", "",
             "> <NMREDATA_1D_13C>", *shifts, ""]
        )

    src = tmp_path / "remeasured.sd"
    src.write_text(
        _carbon("20", ["18.1, L=s1", "57.9, L=s2"]) + "\n$$$$\n"
        + _carbon("21", ["18.4, L=s1"]) + "\n$$$$\n",
        encoding="utf-8",
    )
    records, _ = conv.convert(src)
    assert len(records) == 1
    assert records[0]["shifts_13c"] == [18.1, 57.9]  # not 3 peaks


def test_iter_records_streams_without_reading_whole_file(tmp_path: Path) -> None:
    """Records are yielded one at a time (the 271 MiB export OOM'd on read_text)."""
    src = tmp_path / "many.sd"
    src.write_text("".join(f"> <NMREDATA_SMILES>\nC{'C'*i}\n\n$$$$\n" for i in range(5)),
                   encoding="utf-8")
    it = conv.iter_records(src)
    assert isinstance(it, Iterator)
    assert len(list(it)) == 5


def test_convert_skips_records_without_smiles_or_shifts(tmp_path: Path) -> None:
    src = tmp_path / "sparse.sd"
    src.write_text(
        "\n".join(["> <NMREDATA_1D_1H>", "1.10, L=s1", ""])  # no SMILES
        + "\n$$$$\n"
        + "\n".join(["> <NMREDATA_SMILES>", "CCO", ""])  # no shifts
        + "\n$$$$\n",
        encoding="utf-8",
    )
    records, stats = conv.convert(src)
    assert records == []
    assert stats["no_smiles"] == 1
    assert stats["no_shifts"] == 1


def test_converts_the_real_fixture_without_silently_yielding_zero() -> None:
    """Guard: a regex/tag drift must fail loudly here, not produce an empty corpus."""
    assert _FIXTURE.exists(), f"missing fixture: {_FIXTURE}"
    records, stats = conv.convert(_FIXTURE)

    assert stats["records"] == 196
    # 90 unique molecules at time of writing; assert a floor so the test tracks real
    # regressions rather than pinning an exact count that curation could shift.
    assert len(records) >= 80, f"parsed only {len(records)} molecules"
    assert sum(1 for r in records if r["shifts_1h"] and r["shifts_13c"]) >= 60

    for record in records:
        assert record["id"].startswith("nmrshiftdb2:")
        assert record["smiles"]
        assert record["shifts_1h"] or record["shifts_13c"]
        # Real ppm values, not parsed metadata integers.
        for shift in (*record["shifts_1h"], *record["shifts_13c"]):
            assert -50.0 < shift < 400.0


def test_write_metadata_sidecar_shape(tmp_path: Path) -> None:
    records = [{"id": "nmrshiftdb2:1", "smiles": "CCO", "shifts_1h": [1.1], "shifts_13c": [58.0, 18.2]}]
    out = tmp_path / "metadata.json"
    conv.write_metadata(records, out, source_label="fixture.sd")

    payload = json.loads(out.read_text())
    entry = payload["nmrshiftdb2:1"]
    assert entry["smiles"] == "CCO"
    assert entry["shift_summary"] == "1x 1H, 2x 13C"
    assert "CC-BY-SA" in entry["license"]
    assert entry["source"] == "fixture.sd"


def test_write_corpus_is_one_json_object_per_line(tmp_path: Path) -> None:
    records = [
        {"id": "a", "smiles": "CCO", "shifts_1h": [1.1], "shifts_13c": []},
        {"id": "b", "smiles": "CCN", "shifts_1h": [], "shifts_13c": [40.0]},
    ]
    out = tmp_path / "nested" / "corpus.jsonl"
    conv.write_corpus(records, out)

    lines = out.read_text().strip().splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["id"] for line in lines] == ["a", "b"]
