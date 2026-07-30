#!/usr/bin/env python3
"""Convert an NMReDATA ``.sd`` file into a similarity-index corpus JSONL.

Bridges the gap between an NMReDATA export and ``scripts/build_similarity_index.py``,
which expects one JSON object per line. Each emitted record carries the molecule's
**experimental** shift lists::

    {"id": "nmrshiftdb2:75667", "smiles": "...", "shifts_1h": [...], "shifts_13c": [...]}

Emitting ``shifts_1h`` / ``shifts_13c`` (rather than just ``smiles``) is deliberate: it
takes ``build_similarity_index.py``'s pre-computed branch, so the index is built from
measured shifts and never calls ``predict_shifts``. That matters because without NMRNet
weights the predictor falls back to a small seed HOSE knowledge base, which would encode
most carbons to the same element prior and make L2 neighbours meaningless.

Parses the ``NMREDATA_1D_1H`` / ``NMREDATA_1D_13C`` property blocks, whose rows look like
``2.59, L=s6\\`` and are interleaved with metadata rows (``Larmor=``,
``Spectrum_Location=``) that are skipped by testing for ``=`` before the first comma.
Records are de-duplicated by SMILES, keeping whichever entry carries the most assigned
shifts. Stdlib only — no RDKit, no FAISS, no extras needed.

LICENSE: shifts taken from an NMRShiftDB2 export are CC-BY-SA, and ShareAlike attaches to
a derived corpus/index. ShareAlike triggers on **distribution**, so a local-only index is
fine; the output paths are gitignored. Do not commit or ship the artifacts. For a
commercially distributable index use an MIT-licensed source (see NOTICE).

Usage::

    python scripts/nmredata_to_corpus.py \\
        tests/fixtures/nmrshiftdb2/source/nmrshiftdb2rawdata.nmredata.sd \\
        spectrum_similarity_index/corpus.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterator
from pathlib import Path

#: A shift row starts with the ppm value followed by a comma (``2.59, L=s6``).
SHIFT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,")
#: SDF property header, e.g. ``> <NMREDATA_1D_1H>``.
PROP_RE = re.compile(r"^>\s*<([^>]+)>")


def parse_property_blocks(record: str) -> dict[str, list[str]]:
    """Split one SDF record into ``{tag: [lines]}`` for its ``> <TAG>`` properties.

    A blank line terminates a block, matching the SDF convention.
    """
    blocks: dict[str, list[str]] = {}
    tag: str | None = None
    for line in record.splitlines():
        header = PROP_RE.match(line)
        if header:
            tag = header.group(1)
            blocks[tag] = []
            continue
        if tag is None:
            continue
        if line.strip():
            blocks[tag].append(line.rstrip("\\").strip())
        else:
            tag = None
    return blocks


def parse_shifts(lines: list[str]) -> list[float]:
    """Extract ppm values from an ``NMREDATA_1D_*`` block, skipping metadata rows."""
    shifts: list[float] = []
    for line in lines:
        # Metadata rows (Larmor=…, Spectrum_Location=…) carry '=' before the first comma.
        if "=" in line.split(",", 1)[0]:
            continue
        match = SHIFT_RE.match(line)
        if match:
            shifts.append(float(match.group(1)))
    return shifts


def iter_records(src: Path) -> Iterator[str]:
    """Yield one SDF record at a time.

    Streams rather than reading the file whole: the full NMRShiftDB2 export is
    ~271 MiB, and ``read_text`` + ``split`` on it peaked at ~1.3 GB resident.
    """
    buf: list[str] = []
    with src.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.startswith("$$$$"):
                if buf:
                    yield "".join(buf)
                buf = []
            else:
                buf.append(line)
    if buf:
        yield "".join(buf)


def convert(src: Path) -> tuple[list[dict], dict[str, int]]:
    """Parse an NMReDATA ``.sd`` file into corpus records + conversion counters.

    Records sharing a SMILES are merged **per nucleus** rather than keeping whichever
    single record has the most shifts overall. The full export is one-record-per-
    spectrum and nucleus-grouped, so a molecule routinely appears as a ¹H-only record
    and a separate ¹³C-only record; global keep-max picks one and silently discards
    the other nucleus entirely. Merging per nucleus lifted both-nuclei coverage from
    68/90 to 83/90 molecules on the in-repo fixture alone.

    Within a nucleus the richest (longest) assigned list wins rather than the union —
    two records for the same nucleus are re-measurements, so unioning them would
    double-count peaks. The chosen source is recorded per nucleus in ``provenance``,
    which also surfaces the honest limitation: a merged record's ¹H and ¹³C may come
    from different measurements, and therefore possibly different solvents or fields.
    """
    by_smiles: dict[str, dict] = {}
    stats = {
        "records": 0,
        "no_smiles": 0,
        "no_shifts": 0,
        "duplicates": 0,
        "merged_nuclei": 0,
        "cross_solvent_merges": 0,
    }

    for record in iter_records(src):
        if not record.strip():
            continue
        stats["records"] += 1
        props = parse_property_blocks(record)

        smiles = " ".join(props.get("NMREDATA_SMILES", [])).strip()
        if not smiles:
            stats["no_smiles"] += 1
            continue

        shifts_1h = parse_shifts(props.get("NMREDATA_1D_1H", []))
        shifts_13c = parse_shifts(props.get("NMREDATA_1D_13C", []))
        if not shifts_1h and not shifts_13c:
            stats["no_shifts"] += 1
            continue

        raw_id = " ".join(props.get("NMREDATA_ID", [])).strip()
        db_id = re.search(r"DB_ID=(\S+)", raw_id)
        name = " ".join(props.get("CHEMNAME", [])).strip()
        identifier = db_id.group(1) if db_id else (raw_id or name or smiles[:24])
        solvent = " ".join(props.get("NMREDATA_SOLVENT", [])).strip() or None

        entry = by_smiles.get(smiles)
        is_duplicate = entry is not None
        if entry is None:
            # The id names the merged composite; `provenance` carries the real
            # per-nucleus source DB_IDs, so first-seen is a deterministic label
            # rather than a claim that this record came from one measurement.
            entry = by_smiles[smiles] = {
                "id": f"nmrshiftdb2:{identifier}",
                "smiles": smiles,
                "shifts_1h": [],
                "shifts_13c": [],
                "provenance": {},
            }
        else:
            stats["duplicates"] += 1

        # Per-nucleus: take the richest assigned list, and remember where it came from.
        for key, shifts in (("shifts_1h", shifts_1h), ("shifts_13c", shifts_13c)):
            if not shifts or len(shifts) <= len(entry[key]):
                continue
            filled_an_empty_nucleus = not entry[key]
            entry[key] = shifts
            entry["provenance"][key] = {"db_id": identifier, "solvent": solvent}
            if is_duplicate and filled_an_empty_nucleus:
                # A later record supplied a nucleus the earlier one lacked — the
                # exact case global keep-max used to throw away.
                stats["merged_nuclei"] += 1

    # Flag merged records whose two nuclei came from different solvents.
    for entry in by_smiles.values():
        prov = entry["provenance"]
        solvents = {
            prov[key]["solvent"]
            for key in ("shifts_1h", "shifts_13c")
            if key in prov and prov[key]["solvent"]
        }
        if len(solvents) > 1:
            stats["cross_solvent_merges"] += 1

    return list(by_smiles.values()), stats


def write_corpus(records: list[dict], out_path: Path) -> None:
    """Write one JSON object per line, the shape build_similarity_index.py reads."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def write_metadata(records: list[dict], out_path: Path, source_label: str) -> None:
    """Write the ``MOLTRACE_SIMILARITY_METADATA`` sidecar (index id -> descriptor).

    Without it the retrieval/reasoning layer treats each index id *as* a SMILES string,
    which is meaningless for ``nmrshiftdb2:…`` keys.
    """
    metadata = {
        record["id"]: {
            "smiles": record["smiles"],
            "license": "CC-BY-SA (NMRShiftDB2) - local use only, do not distribute",
            "source": source_label,
            "shift_summary": (
                f"{len(record['shifts_1h'])}x 1H, {len(record['shifts_13c'])}x 13C"
            ),
        }
        for record in records
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert an NMReDATA .sd export into a similarity-index corpus JSONL."
    )
    parser.add_argument("source", type=Path, help="input NMReDATA .sd file")
    parser.add_argument("out", type=Path, help="output corpus JSONL path")
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="also write the MOLTRACE_SIMILARITY_METADATA sidecar to this path",
    )
    args = parser.parse_args(argv)

    records, stats = convert(args.source)
    write_corpus(records, args.out)
    both = sum(1 for r in records if r["shifts_1h"] and r["shifts_13c"])

    print(f"  SDF records scanned : {stats['records']}")
    print(f"  skipped (no SMILES) : {stats['no_smiles']}")
    print(f"  skipped (no shifts) : {stats['no_shifts']}")
    print(f"  duplicate SMILES    : {stats['duplicates']}")
    print(f"  unique molecules    : {len(records)} (both nuclei: {both})")
    print(f"Wrote {len(records)} records -> {args.out}")

    if args.metadata is not None:
        write_metadata(records, args.metadata, source_label=args.source.name)
        print(f"Wrote metadata sidecar -> {args.metadata}")

    print(
        "NOTE: an NMRShiftDB2-derived corpus is CC-BY-SA (ShareAlike, see NOTICE). "
        "The output paths are gitignored -- do not commit or distribute them."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
