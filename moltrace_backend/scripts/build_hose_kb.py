#!/usr/bin/env python3
"""Build the HOSE-code fallback knowledge base from a NMRShiftDB2 SDF export.

The HOSE-code fallback in ``moltrace.spectroscopy.predict.nmrnet_wrapper`` looks
up each atom's spherical environment in a knowledge base. This script turns a
NMRShiftDB2 SDF (with assigned ¹H / ¹³C spectra) into the JSON that
``load_knowledge_base`` reads::

    [{"smiles": "...", "assignments": [{"atom_index": int (AddHs order),
        "nucleus": "1H"|"13C", "shift_ppm": float}, ...]}, ...]

Usage
-----
    python scripts/build_hose_kb.py nmrshiftdb2.sdf -o ~/.cache/moltrace/nmrnet/hose_kb.json
    # then point the predictor at it:
    export MOLTRACE_HOSE_KB=~/.cache/moltrace/nmrnet/hose_kb.json

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdf", type=Path, help="NMRShiftDB2 SDF export")
    parser.add_argument(
        "-o", "--out", type=Path, required=True, help="output JSON (gitignored)"
    )
    args = parser.parse_args(argv)

    if not args.sdf.exists():
        parser.error(f"SDF not found: {args.sdf}")
    records = build(args.sdf)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records))
    n_assign = sum(len(r["assignments"]) for r in records)
    print(
        f"Wrote {len(records)} molecules / {n_assign} assignments to {args.out}\n"
        f"NOTE: this table is a NMRShiftDB2 derivative — CC BY-SA (see NOTICE). "
        f"Point the predictor at it with MOLTRACE_HOSE_KB={args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
