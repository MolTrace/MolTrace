#!/usr/bin/env python3
"""Build the HOSE-code fallback knowledge base from a NMRShiftDB2 export.

The HOSE-code fallback in ``moltrace.spectroscopy.predict.nmrnet_wrapper`` looks
up each atom's spherical environment in a knowledge base. This script turns an
export with assigned ¹H / ¹³C spectra into the JSON ``load_knowledge_base`` reads.

**Both input formats are accepted and auto-detected**:

* **NMReDATA** (``nmrshiftdb2.nmredata.sd``) — preferred. Its
  ``NMREDATA_ASSIGNMENT`` block gives per-atom identity directly, so records emit
  a ``molblock`` and the atom numbering the file asserts is the numbering indexed::

      [{"molblock": "...", "assignments": [{"atom_index": int (molfile order),
          "nucleus": "1H"|"13C", "shift_ppm": float}, ...]}, ...]

* **Plain SDF** with ``Spectrum 13C 0``-style properties — records emit ``smiles``
  and ``atom_index`` in ``AddHs`` order.

Why assignments and not a bigger corpus: a HOSE table is keyed by *atom
environment*, so it can only be built from a source that says which atom each
shift belongs to. A corpus of peak lists paired with structures — at any scale —
carries no atom identity and cannot populate this table.

Usage
-----
    python scripts/build_hose_kb.py nmrshiftdb2.nmredata.sd \\
        -o ~/.cache/moltrace/nmrnet/hose_kb.json
    # then point the predictor at it:
    export MOLTRACE_HOSE_KB=~/.cache/moltrace/nmrnet/hose_kb.json

Measured on the full export (64 723 records → 49 618 molecules / 495 215
assignments): the drug-like panel's element-prior fallback goes 22.6-44.4 % → 0 %
and the median ¹³C prediction uncertainty 35.0 → 1.88 ppm, i.e. below DP4's own
2.306 ppm error scale. See ``tests/test_predict_shift_coverage.py``.

License
-------
NMRShiftDB2 is CC BY-SA. The table this script produces is a DERIVATIVE WORK and
inherits the ShareAlike + attribution obligation (see the repository NOTICE).
Do NOT commit the raw SDF or the generated table to git (they are .gitignored).

NMRShiftDB2 SDF spectrum properties look like ``Spectrum 13C 0`` with a value of
``shift;multiplicity;atomIndex|shift;multiplicity;atomIndex|...`` where
``atomIndex`` is 0-based into the SDF's heavy atoms. ¹³C shifts map to that
carbon; ¹H shifts are mapped to the hydrogens AddHs places on the referenced
heavy atom. VERIFY this mapping against your specific export — NMRShiftDB2
conventions vary by version.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from rdkit import Chem

_SPECTRUM_PROP = re.compile(r"^Spectrum\s+(1H|13C)\b", re.IGNORECASE)


def _parse_spectrum(value: str) -> list[tuple[float, int]]:
    """Parse ``shift;mult;atomIndex|...`` → ``[(shift_ppm, heavy_atom_index), ...]``."""

    out: list[tuple[float, int]] = []
    for entry in value.split("|"):
        parts = entry.split(";")
        if len(parts) < 3:
            continue
        try:
            shift = float(parts[0])
            atom_index = int(parts[-1])
        except ValueError:
            continue
        out.append((shift, atom_index))
    return out


def build(sdf_path: Path) -> list[dict]:
    records: list[dict] = []
    supplier = Chem.SDMolSupplier(str(sdf_path), removeHs=True, sanitize=True)
    for mol in supplier:
        if mol is None:
            continue
        smiles = Chem.MolToSmiles(mol)
        mol_h = Chem.AddHs(mol)  # heavy-atom indices preserved; H appended
        assignments: list[dict] = []
        for prop in mol.GetPropNames():
            match = _SPECTRUM_PROP.match(prop)
            if not match:
                continue
            nucleus = "13C" if match.group(1).upper() == "13C" else "1H"
            for shift, heavy_index in _parse_spectrum(mol.GetProp(prop)):
                if not (0 <= heavy_index < mol.GetNumAtoms()):
                    continue
                if nucleus == "13C":
                    if mol_h.GetAtomWithIdx(heavy_index).GetSymbol() == "C":
                        assignments.append(
                            {"atom_index": heavy_index, "nucleus": "13C", "shift_ppm": shift}
                        )
                else:  # 1H → the hydrogens on that heavy atom
                    for nbr in mol_h.GetAtomWithIdx(heavy_index).GetNeighbors():
                        if nbr.GetSymbol() == "H":
                            assignments.append(
                                {"atom_index": nbr.GetIdx(), "nucleus": "1H", "shift_ppm": shift}
                            )
        if assignments:
            records.append({"smiles": smiles, "assignments": assignments})
    return records


#: NMReDATA assignment row: ``s0, 44.21, 4`` -> (label, shift_ppm, atom_number).
#: The third field is a **1-based index into the molfile's own atom block**, which
#: includes explicit hydrogens. That exactness is the whole value of this format.
_NMREDATA_ASSIGNMENT_RE = re.compile(
    r"^\s*(\S+)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(\d+)"
)
#: A 1D block row referencing an assignment label: ``44.21, L=s0``.
_NMREDATA_LABEL_RE = re.compile(r"\bL\s*=\s*(\S+?)\s*\\?\s*$")


def _parse_sd_chunk(lines: list[str]):
    """Turn one record's lines into ``(molblock, {tag: [lines]})``."""

    molblock_lines: list[str] = []
    props: dict[str, list[str]] = {}
    current: str | None = None
    in_props = False

    for line in lines:
        header = re.match(r"^>\s*<([^>]+)>", line)
        if header:
            in_props = True
            current = header.group(1)
            props[current] = []
            continue
        if in_props:
            if current:
                props[current].append(line)
        else:
            molblock_lines.append(line)
    return "\n".join(molblock_lines), props


def _sd_records(path: Path):
    """Stream ``(molblock, {tag: [lines]})`` per record from an SD file.

    Streamed rather than ``read_text().split("$$$$")`` because the full
    NMRShiftDB2 NMReDATA export is ~271 MB / ~44 k records, and the split form
    holds the whole file plus every chunk in memory at once.

    Record boundaries are handled by *accumulating lines* rather than splitting on
    the ``$$$$`` separator, which avoids the off-by-one that splitting causes: a
    molblock's first line is the title and is legitimately **empty** in this
    export, so a stray leading newline shifts the mandatory 4-line header and
    RDKit rejects every record after the first — silently, with no error.
    """

    with path.open("r", errors="replace") as handle:
        buffer: list[str] = []
        for raw in handle:
            line = raw.rstrip("\n")
            if line.startswith("$$$$"):
                if any(row.strip() for row in buffer):
                    yield _parse_sd_chunk(buffer)
                buffer = []
            else:
                buffer.append(line)
        if any(row.strip() for row in buffer):
            yield _parse_sd_chunk(buffer)


def build_from_nmredata(path: Path) -> list[dict]:
    """Convert an NMReDATA ``.sd`` export into knowledge-base records.

    NMReDATA is the right source for a HOSE table because it carries *per-atom
    assignments*, not just peak lists: ``NMREDATA_ASSIGNMENT`` maps a label to
    (shift, atom number), and the ``NMREDATA_1D_1H`` / ``NMREDATA_1D_13C`` blocks
    say which nucleus each label belongs to. A corpus of shift lists without atom
    identity — however large — cannot build this table at all.

    Emits ``molblock`` rather than ``smiles`` so the atom numbering the file
    asserts is the numbering the knowledge base indexes. See ``load_knowledge_base``.
    """

    records: list[dict] = []
    for molblock, props in _sd_records(path):
        assignment_rows = props.get("NMREDATA_ASSIGNMENT")
        if not assignment_rows:
            continue

        mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=True)
        if mol is None:
            continue
        n_atoms = mol.GetNumAtoms()

        # label -> (shift_ppm, 0-based atom index)
        labelled: dict[str, tuple[float, int]] = {}
        for row in assignment_rows:
            match = _NMREDATA_ASSIGNMENT_RE.match(row)
            if not match:
                continue
            index = int(match.group(3)) - 1
            if 0 <= index < n_atoms:
                labelled[match.group(1)] = (float(match.group(2)), index)

        assignments: list[dict] = []
        for tag, nucleus in (("NMREDATA_1D_1H", "1H"), ("NMREDATA_1D_13C", "13C")):
            expected = "H" if nucleus == "1H" else "C"
            for row in props.get(tag, []):
                label_match = _NMREDATA_LABEL_RE.search(row)
                if not label_match:
                    continue
                entry = labelled.get(label_match.group(1))
                if entry is None:
                    continue
                shift, index = entry
                # Guard the mapping rather than trusting it: a 1H shift landing on
                # a carbon means the atom numbering was misread, and a silently
                # mis-indexed table is worse than no table.
                if mol.GetAtomWithIdx(index).GetSymbol() != expected:
                    continue
                assignments.append(
                    {"atom_index": index, "nucleus": nucleus, "shift_ppm": shift}
                )

        if assignments:
            records.append({"molblock": molblock, "assignments": assignments})
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdf", type=Path, help="NMRShiftDB2 SDF or NMReDATA .sd export")
    parser.add_argument(
        "-o", "--out", type=Path, required=True, help="output JSON (gitignored)"
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help=(
            "emit a precomputed HOSE index instead of molecules+assignments. "
            "THIS IS THE DEPLOYABLE ARTIFACT: 14 MB gzipped vs 193 MB, and ~1 s to "
            "load vs ~47 s, because it needs no RDKit at startup. Give -o a .gz "
            "suffix to compress."
        ),
    )
    args = parser.parse_args(argv)

    if not args.sdf.exists():
        parser.error(f"input not found: {args.sdf}")

    # Auto-detect: NMReDATA carries assignment blocks, a plain SDF export does not.
    # Read a prefix, not the file — the full NMRShiftDB2 export is ~271 MB.
    with args.sdf.open("r", errors="replace") as handle:
        head = handle.read(200_000)
    if "NMREDATA_ASSIGNMENT" in head:
        records = build_from_nmredata(args.sdf)
    else:
        records = build(args.sdf)

    n_assign = sum(len(r["assignments"]) for r in records)
    licence_note = (
        "NOTE: this table is a NMRShiftDB2 derivative — CC BY-SA (see NOTICE). "
        "ShareAlike attaches on redistribution."
    )

    if args.index:
        # Round-trip through the loader so the index is built by exactly the same
        # code path the predictor uses — a separately-implemented indexer would be
        # free to drift from it silently.
        import tempfile

        from moltrace.spectroscopy.predict.nmrnet_wrapper import (
            load_knowledge_base,
            save_knowledge_base_index,
        )

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
            json.dump(records, tmp)
            staged = Path(tmp.name)
        try:
            kb = load_knowledge_base(staged)
            save_knowledge_base_index(kb, args.out)
        finally:
            staged.unlink(missing_ok=True)

        print(
            f"Wrote a precomputed index of {kb.reference_count} reference atoms "
            f"({len(records)} molecules / {n_assign} assignments) to {args.out}\n"
            f"{licence_note}\n"
            f"Point the predictor at it with MOLTRACE_HOSE_KB={args.out}",
            file=sys.stderr,
        )
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records))
    print(
        f"Wrote {len(records)} molecules / {n_assign} assignments to {args.out}\n"
        f"{licence_note}\n"
        f"This is the INPUT format: loading it re-parses every molecule with RDKit "
        f"(~47 s for the full table). For deployment, re-run with --index.\n"
        f"Point the predictor at it with MOLTRACE_HOSE_KB={args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
