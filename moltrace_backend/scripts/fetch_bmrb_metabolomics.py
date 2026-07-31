#!/usr/bin/env python3
"""Fetch BMRB metabolomics entries: real Bruker FIDs paired with structures.

WHY THIS CORPUS
---------------
Validating the 1H pipeline needs three things together: a real free-induction
decay, the acquisition parameters that say whether its integrals may be read as
proton counts, and a structure to score against. Almost nothing has all three.

  * our 42,449-record NMRShiftDB2 corpus is chemical SHIFTS only - no FIDs, no
    acquisition parameters, no integrations;
  * tests/fixtures/hmdb has 100 real FIDs but no SMILES anywhere in the repo;
  * hmdb_style_minicorpus spectra are synthesised at runtime;
  * tests/fixtures/nmrshiftdb2 has all three but only SEVEN 1H spectra.

BMRB metabolomics has all three at ~3,400-compound scale: each entry ships a
``.mol`` structure plus complete Bruker datasets (``fid``, ``acqus``,
``pulseprogram``, ``pdata/``).

WHAT IT DOES NOT SOLVE
----------------------
Its 1H spectra are acquired with solvent presaturation (``zgcppr``,
``jresgpprqf``) at d1 = 2-4 s in D2O/H2O, because these are aqueous metabolite
standards. Presaturation attenuates signal near the irradiated line, so these
are correctly gated ``not_quantitative`` and CANNOT settle whether integration
is proportional. This corpus is for CLASSIFICATION accuracy at scale; the
quantitation question still needs a long-relaxation-delay, non-suppressed
spectrum.

LICENCE
-------
BMRB states access is free and requests acknowledgement, but publishes no
explicit licence granting redistribution. So this script writes into
``corpus_store/``, which is gitignored - the data is used locally and NEVER
committed or shipped. Only this fetcher is version-controlled. Do not change
the destination to a tracked path.

    https://bmrb.io/  -  please acknowledge BMRB in any publication.

USAGE
-----
    .venv/bin/python scripts/fetch_bmrb_metabolomics.py --limit 50
    .venv/bin/python scripts/fetch_bmrb_metabolomics.py --limit 500 --nucleus 1H

Resumable: entries already present are skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://bmrb.io/ftp/pub/bmrb/metabolomics/entry_directories"
ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "corpus_store" / "bmrb"
USER_AGENT = "MolTrace-validation/1.0 (local scientific validation; contact repo owner)"
POLITE_DELAY_S = 0.34  # ~3 requests/second, well under any sane rate limit


def get(url: str, *, binary: bool = False, timeout: int = 60):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    time.sleep(POLITE_DELAY_S)
    return payload if binary else payload.decode("latin-1", errors="replace")


def listing(url: str) -> list[str]:
    """Directory entries from an Apache-style index."""
    try:
        html = get(url)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return []
    names = re.findall(r'href="([^"?/][^"]*/?)"', html)
    return [n for n in dict.fromkeys(names) if not n.startswith(("..", "http", "/"))]


def bruker_scalar(text: str, key: str) -> str | None:
    match = re.search(rf"^##\$\{{?{key}\}}?=\s*(.+)$", text, re.M)
    return match.group(1).strip().strip("<>") if match else None


def bruker_relaxation_delay(text: str) -> float | None:
    """D[1] - the relaxation delay. D[0] is a settling delay and is normally 0."""
    match = re.search(r"^##\$D=\s*\(0\.\.\d+\)\s*\n(.*?)(?=^##)", text, re.M | re.S)
    if not match:
        return None
    values = match.group(1).split()
    try:
        return float(values[1]) if len(values) > 1 else None
    except ValueError:
        return None


def smiles_from_mol(mol_text: str) -> str | None:
    try:
        from rdkit import Chem, RDLogger

        RDLogger.DisableLog("rdApp.*")
        mol = Chem.MolFromMolBlock(mol_text)
        return Chem.MolToSmiles(mol) if mol is not None else None
    except Exception:
        return None


def harvest_entry(entry: str, *, nucleus: str | None) -> list[dict]:
    """Download one entry's structure and every matching raw dataset."""
    entry_dir = DEST / entry
    root_url = f"{BASE}/{entry}"

    mol_text = None
    for candidate in (f"{entry}.mol", f"{entry}.sdf"):
        try:
            mol_text = get(f"{root_url}/{candidate}")
            break
        except Exception:
            continue
    smiles = smiles_from_mol(mol_text) if mol_text else None

    rows: list[dict] = []
    for set_name in [n for n in listing(f"{root_url}/nmr/") if n.endswith("/")]:
        set_url = f"{root_url}/nmr/{set_name}"
        for exp in [n for n in listing(set_url) if re.fullmatch(r"\d+/", n)]:
            acqus_url = f"{set_url}{exp}acqus"
            try:
                acqus = get(acqus_url)
            except Exception:
                continue
            nuc = bruker_scalar(acqus, "NUC1")
            if nucleus and (nuc or "").upper() != nucleus.upper():
                continue
            row = {
                "entry": entry,
                "set": set_name.rstrip("/"),
                "experiment": exp.rstrip("/"),
                "nucleus": nuc,
                "relaxation_delay_s": bruker_relaxation_delay(acqus),
                "pulse_program": bruker_scalar(acqus, "PULPROG"),
                "solvent": bruker_scalar(acqus, "SOLVENT"),
                "scans": bruker_scalar(acqus, "NS"),
                "td": bruker_scalar(acqus, "TD"),
                "sw_hz": bruker_scalar(acqus, "SW_h"),
                "smiles": smiles,
                "source_url": f"{set_url}{exp}",
            }
            # 2D experiments (COSY/TOCSY/HSQC/HMBC) also report NUC1=1H but store
            # their data as ``ser``, not ``fid``. They are not 1D proton spectra
            # and cannot feed the proton inventory, so a missing ``fid`` is the
            # cleanest discriminator - no pulse-program allow-list to maintain.
            try:
                fid_bytes = get(f"{set_url}{exp}fid", binary=True)
            except Exception:
                continue
            local = entry_dir / row["set"] / row["experiment"]
            local.mkdir(parents=True, exist_ok=True)
            (local / "acqus").write_text(acqus, encoding="latin-1")
            (local / "fid").write_bytes(fid_bytes)
            row["fid_bytes"] = len(fid_bytes)
            if mol_text:
                (entry_dir / f"{entry}.mol").write_text(mol_text, encoding="latin-1")
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25, help="how many entries to fetch")
    parser.add_argument("--nucleus", default="1H", help="filter by nucleus, or 'any'")
    parser.add_argument("--start", type=int, default=0, help="skip this many entries")
    args = parser.parse_args()
    nucleus = None if args.nucleus.lower() == "any" else args.nucleus

    DEST.mkdir(parents=True, exist_ok=True)
    print(f"BMRB metabolomics -> {DEST}  (gitignored; do not commit this data)")

    entries = sorted({e.rstrip("/") for e in listing(f"{BASE}/") if e.startswith("bmse")})
    print(f"catalogue: {len(entries)} entries")
    selected = entries[args.start : args.start + args.limit]

    manifest_path = DEST / "manifest.jsonl"
    seen = set()
    if manifest_path.exists():
        for line in manifest_path.read_text().splitlines():
            try:
                seen.add(json.loads(line)["entry"])
            except Exception:
                pass

    written = 0
    with manifest_path.open("a") as manifest:
        for index, entry in enumerate(selected, 1):
            if entry in seen:
                print(f"[{index}/{len(selected)}] {entry} already fetched")
                continue
            try:
                rows = harvest_entry(entry, nucleus=nucleus)
            except KeyboardInterrupt:
                print("\ninterrupted; manifest is consistent, rerun to resume")
                return 130
            except Exception as exc:  # noqa: BLE001 - one bad entry must not stop the run
                print(f"[{index}/{len(selected)}] {entry} FAILED {type(exc).__name__}: {exc}")
                continue
            for row in rows:
                manifest.write(json.dumps(row) + "\n")
            manifest.flush()
            written += len(rows)
            smiles_note = "smiles" if (rows and rows[0].get("smiles")) else "NO SMILES"
            print(f"[{index}/{len(selected)}] {entry}: {len(rows)} dataset(s), {smiles_note}")

    print(f"\ndone: {written} datasets appended to {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
