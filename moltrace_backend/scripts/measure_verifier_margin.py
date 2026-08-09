#!/usr/bin/env python
"""Measure how far `verify_structure` separates a right structure from a wrong one.

This is the arbiter-level counterpart to `measure_false_confirmation`. That one scores a
¹³C shift list through DP4 and reported **38.1 %** false confirmation over 3,073 pairs
(`docs/structure_elucidation_program.md`, B5.2); it says in its own docstring that it is
*not* the multi-test verifier. So the published number describes a component, and the
component is not the thing that decides.

**Real spectra only.** An earlier version of this script synthesised a ¹³C spectrum from
each record's experimental shift positions, which is 40× cheaper and runs on the whole
corpus. It was measured against the real Bruker fixtures and refuted: the margins
correlate at *r* = −0.106 and disagree in sign for 35 % of pairs, because the synthesis
saturates `gsd_peak_pick`'s peak cap with ~96 % spurious peaks and turns the verifier into
a near-universal acceptor. See the warning on `eval.verifier_margin.simulate_spectrum`.
The cost of honesty here is n: **13 real ¹³C fixtures**, not 1,657 molecules.

The knowledge base is built from the **training** split. The shipped
`data/hose/hose_index.json.gz` would be leakage — it is built from this same corpus. Note
that even so, 8 of the 13 fixtures land in the training split; the report separates them,
because a leaked molecule's margin is memorisation, not discrimination.

Usage:

    uv run python scripts/measure_verifier_margin.py
    uv run python scripts/measure_verifier_margin.py --out /tmp/margin.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_hose_kb import _sd_records, build_from_nmredata  # noqa: E402
from rdkit import Chem  # noqa: E402

from moltrace.spectroscopy.eval.shift_accuracy import split_records_three_way  # noqa: E402
from moltrace.spectroscopy.eval.verifier_margin import measure_verifier_margin  # noqa: E402
from moltrace.spectroscopy.io.fid_reader import read_fid  # noqa: E402
from moltrace.spectroscopy.predict import nmrnet_wrapper as _nw  # noqa: E402

_DEFAULT_SOURCE = Path.home() / ".cache/moltrace/nmrshiftdb2/nmrshiftdb2.nmredata.sd"
_FIXTURES = Path(__file__).resolve().parent.parent / "tests/fixtures/nmrshiftdb2"
_SPECTRUM_ID = re.compile(r"spectrumid=(\d+)")
_DIR_NAME = re.compile(r"nmrshiftdb2_(\d+)_(1h|13c)_bruker", re.IGNORECASE)


def _fixture_index() -> dict[str, dict[str, Any]]:
    """spectrum id -> {molblock, assignments} from the bundled NMReDATA index.

    The molblock, never the ``NMREDATA_SMILES`` tag: across the 196 records the tag drops
    E/Z stereochemistry on 129 of them.
    """

    by_spectrum: dict[str, dict[str, Any]] = {}
    by_db: dict[str, dict[str, Any]] = {}
    for molblock, props in _sd_records(_FIXTURES / "source/nmrshiftdb2rawdata.nmredata.sd"):
        lines = molblock.split("\n")
        db_id = lines[2].split()[-1] if len(lines) > 2 and lines[2].strip() else ""
        entry = {"molblock": molblock, "props": props}
        if db_id:
            by_db[db_id] = entry
        for rows in props.values():
            for row in rows:
                for match in _SPECTRUM_ID.finditer(row):
                    by_spectrum.setdefault(match.group(1), entry)
    by_spectrum.update({k: v for k, v in by_db.items() if k not in by_spectrum})
    return by_spectrum


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=_DEFAULT_SOURCE)
    parser.add_argument("--nucleus", default="13C", choices=["13C", "1H"])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if not args.source.exists():
        print(f"No corpus at {args.source}. Fetch it first.", file=sys.stderr)
        return 2

    corpus = build_from_nmredata(args.source)
    train, _calibration, _test = split_records_three_way(corpus)
    t0 = time.perf_counter()
    _nw._FALLBACK_KB = _nw.build_knowledge_base(train)
    print(
        f"knowledge base: {_nw._FALLBACK_KB.reference_count} reference atoms from "
        f"{len(train)} training records in {time.perf_counter() - t0:.1f}s",
        file=sys.stderr,
    )
    train_smiles = set()
    for record in train:
        mol = _nw.molecule_from_record(record)
        if mol is not None:
            train_smiles.add(Chem.MolToSmiles(Chem.RemoveHs(mol)))

    index = _fixture_index()
    want = args.nucleus.lower()
    records: list[dict[str, Any]] = []
    spectra: dict[int, Any] = {}
    for path in sorted((_FIXTURES / "raw/extracted").iterdir()):
        match = _DIR_NAME.match(path.name)
        if not match or match.group(2).lower() != want:
            continue
        entry = index.get(match.group(1))
        if entry is None:
            continue
        parsed = build_from_nmredata_single(entry)
        if parsed is None:
            continue
        try:
            spectrum = read_fid(path)
        except Exception as exc:  # noqa: BLE001 — a broken fixture is data, not a crash
            print(f"  skip {path.name}: {exc}", file=sys.stderr)
            continue
        spectra[len(records)] = spectrum
        records.append(parsed)

    print(f"{len(records)} real {args.nucleus} fixtures joined to a structure", file=sys.stderr)
    if not records:
        return 2

    order = {id(r): i for i, r in enumerate(records)}
    report = measure_verifier_margin(
        test=records,
        nucleus=args.nucleus,
        spectrum_for=lambda record, _shifts, _nuc: spectra.get(order[id(record)]),
    )

    payload = report.as_dict()
    payload["fixtures"] = len(records)
    payload["fixtures_leaked_into_train"] = sum(
        1
        for r in records
        if (m := _nw.molecule_from_record(r)) is not None
        and Chem.MolToSmiles(Chem.RemoveHs(m)) in train_smiles
    )
    payload["note_real_spectra"] = (
        "Margins measured on real Bruker FIDs. A synthesised spectrum was measured not to "
        "transfer (r = -0.106, 35% sign disagreement) and must not be substituted."
    )
    print(json.dumps(payload, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2))
    return 0


def build_from_nmredata_single(entry: dict[str, Any]) -> dict[str, Any] | None:
    """One NMReDATA record -> the ``{molblock, assignments}`` shape the eval modules take."""

    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".sd", delete=False) as handle:
        handle.write(entry["molblock"] + "\n")
        for tag, rows in entry["props"].items():
            handle.write(f"> <{tag}>\n" + "\n".join(rows) + "\n\n")
        handle.write("$$$$\n")
        path = Path(handle.name)
    try:
        parsed = build_from_nmredata(path)
    finally:
        path.unlink(missing_ok=True)
    return parsed[0] if parsed else None


if __name__ == "__main__":
    raise SystemExit(main())
