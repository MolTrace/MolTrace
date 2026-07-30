#!/usr/bin/env python3
"""Build a FAISS HNSW spectrum-similarity index from a shift corpus (Prompt 8).

Reads a JSONL corpus and writes a FAISS index consumable by
``moltrace.spectroscopy.similarity.SpectrumIndex.load``.

Each input line is a JSON object with an ``id`` plus EITHER pre-computed shift
lists or a SMILES to predict shifts from::

    {"id": "nmrshiftdb2:12345", "shifts_1h": [7.26, ...], "shifts_13c": [128.4, ...]}
    {"id": "CCO", "smiles": "CCO"}     # shifts predicted via predict_shifts (Prompt 6)

LICENSE: an index built from NMRShiftDB2 is a CC-BY-SA derivative and carries the
ShareAlike obligation (see ``NOTICE``). It is gitignored and must NOT be
committed. SimNMR-PubChem (MIT) permits commercial indexing; re-confirm the
dataset card before distributing a derived index.

Usage::

    python scripts/build_similarity_index.py corpus.jsonl spectrum_similarity_index/spectra.faiss
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from moltrace.spectroscopy.similarity import (
    ENCODING_DIM,
    MultiNucleusSpectrumIndex,
    SpectrumIndex,
    encode_prediction,
    encode_spectrum,
)


def _encode_record(record: dict) -> np.ndarray:
    """Encode one corpus record into the 256-D spectrum vector."""
    if "shifts_1h" in record or "shifts_13c" in record:
        return encode_spectrum(record.get("shifts_1h", []), record.get("shifts_13c", []))
    smiles = record.get("smiles")
    if not smiles:
        raise ValueError(f"record {record.get('id')!r} has neither shift lists nor smiles")
    # Imported lazily so the common (pre-computed shifts) path needs no RDKit/torch.
    from moltrace.spectroscopy.predict.nmrnet_wrapper import predict_shifts

    return encode_prediction(predict_shifts(smiles))


def build(
    corpus_path: Path,
    out_path: Path,
    ef_construction: int = 200,
    per_nucleus: bool = True,
) -> tuple[int, object]:
    """Encode the corpus into an index and persist it. Returns (count, index).

    ``per_nucleus`` builds a :class:`MultiNucleusSpectrumIndex`, which is the right
    default for any real corpus: reference databases routinely record one nucleus
    only (82.2 % of the full NMRShiftDB2 export), and a single concatenated index
    ranks those entries by their *missing* half rather than by chemistry. Pass
    ``--single-index`` only for a corpus where every molecule carries every nucleus.
    """

    index: object
    if per_nucleus:
        index = MultiNucleusSpectrumIndex(ef_construction=ef_construction)
    else:
        index = SpectrumIndex(dim=ENCODING_DIM, ef_construction=ef_construction)
    count = 0
    unreachable: list[str] = []
    with open(corpus_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            vector = _encode_record(record)
            # A record whose every shift falls outside the encoding's ppm grid
            # encodes to all zeros and is retrievable by nothing. That is a real
            # (if rare) data condition -- report it rather than dropping it
            # silently, because a silent drop reads as full coverage.
            if not vector.any():
                unreachable.append(str(record.get("id")))
            index.add(vector, [record["id"]])
            count += 1
            if count % 1000 == 0:
                print(f"  encoded {count}", file=sys.stderr)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    index.save(str(out_path))
    if unreachable:
        shown = ", ".join(unreachable[:5]) + (" ..." if len(unreachable) > 5 else "")
        print(
            f"WARNING: {len(unreachable)} of {count} records encode to all zeros "
            f"(every shift outside the ppm grid) and cannot be retrieved: {shown}",
            file=sys.stderr,
        )
    return count, index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a FAISS spectrum-similarity index.")
    parser.add_argument("corpus", type=Path, help="JSONL corpus (id + shifts or smiles per line)")
    parser.add_argument("out", type=Path, help="output FAISS index path (e.g. .../spectra.faiss)")
    parser.add_argument("--ef-construction", type=int, default=200)
    parser.add_argument(
        "--single-index",
        action="store_true",
        help=(
            "build one concatenated 256-D index instead of per-nucleus sub-indices. "
            "Only sound when every corpus molecule carries every nucleus -- otherwise "
            "entries missing a nucleus are ranked by the missing half, not by chemistry."
        ),
    )
    args = parser.parse_args(argv)

    count, index = build(
        args.corpus, args.out, args.ef_construction, per_nucleus=not args.single_index
    )
    if isinstance(index, MultiNucleusSpectrumIndex):
        sizes = ", ".join(f"{n}: {index.nucleus_size(n)}" for n in ("1h", "13c"))
        print(f"Indexed {count} molecules -> {args.out} (+ per-nucleus files; {sizes})")
    else:
        print(f"Indexed {count} spectra -> {args.out} (+ {args.out}.ids.json)")
    print(
        "NOTE: if derived from NMRShiftDB2 this index is CC-BY-SA (ShareAlike, see "
        "NOTICE) and is gitignored -- do not commit it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
