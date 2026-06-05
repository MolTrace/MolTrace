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


def build(corpus_path: Path, out_path: Path, ef_construction: int = 200) -> int:
    index = SpectrumIndex(dim=ENCODING_DIM, ef_construction=ef_construction)
    count = 0
    with open(corpus_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            index.add(_encode_record(record), [record["id"]])
            count += 1
            if count % 1000 == 0:
                print(f"  encoded {count}", file=sys.stderr)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    index.save(str(out_path))
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a FAISS spectrum-similarity index.")
    parser.add_argument("corpus", type=Path, help="JSONL corpus (id + shifts or smiles per line)")
    parser.add_argument("out", type=Path, help="output FAISS index path (e.g. .../spectra.faiss)")
    parser.add_argument("--ef-construction", type=int, default=200)
    args = parser.parse_args(argv)

    count = build(args.corpus, args.out, args.ef_construction)
    print(f"Indexed {count} spectra -> {args.out} (+ {args.out}.ids.json)")
    print(
        "NOTE: if derived from NMRShiftDB2 this index is CC-BY-SA (ShareAlike, see "
        "NOTICE) and is gitignored -- do not commit it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
