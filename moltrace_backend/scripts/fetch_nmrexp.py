#!/usr/bin/env python3
"""Fetch NMRexp - 3.37M experimental NMR records from published Supporting Information.

WHY THIS CORPUS
---------------
NMRexp records are literature 1H strings paired with a structure, which is
EXACTLY the input shape of MolTrace's ``nmr_text_guided`` path - the same route
that produced the reported anomeric-misassignment. Each record carries chemical
shifts, multiplicities, J-couplings, INTEGRATIONS, solvent, frequency, a SMILES
and a source DOI. That makes it the first corpus we have found that can
validate the proton inventory at scale on real published data.

It does NOT contain raw FIDs or acquisition parameters (no relaxation delay, no
pulse program), so it cannot settle whether integration is proportional. For
that, a long-relaxation-delay spectrum is still needed. Use BMRB metabolomics
(scripts/fetch_bmrb_metabolomics.py) when raw FIDs are wanted instead.

LICENCE
-------
The Zenodo dataset is CC BY 4.0 - commercial use, redistribution and
derivatives are all permitted with attribution. Note this differs from the
ACCOMPANYING PAPER, which is CC BY-NC-ND; do not quote the article licence for
the data. Attribute as:

    NMRexp: A database of 3.37 million experimental NMR spectra,
    Zenodo, doi:10.5281/zenodo.17296666  (CC BY 4.0)

Even so this writes into ``corpus_store/``, which is gitignored: a 2.1 GB CSV
does not belong in the repository. Only this fetcher is version-controlled.

USAGE
-----
    .venv/bin/python scripts/fetch_nmrexp.py                 # curated subsets (~1 MB)
    .venv/bin/python scripts/fetch_nmrexp.py --full          # + the 2.1 GB corpus
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

RECORD = "17296666"
BASE = f"https://zenodo.org/records/{RECORD}/files"
DEST = Path(__file__).resolve().parent.parent / "corpus_store" / "nmrexp"

# Small curated, human-checked subsets - enough to validate against.
SUBSETS = [
    "test_300_checked.csv",
    "hetero_200_checked.csv",
    "F_50_checked.csv",
    "P_50_checked.csv",
    "B_50_checked.csv",
    "Si_50_checked.csv",
]
FULL = "NMRexp_10to24_1_1004.csv"  # ~2.1 GB


def expected_sizes() -> dict[str, int]:
    """Authoritative file sizes from the Zenodo record."""
    try:
        with urllib.request.urlopen(
            f"https://zenodo.org/api/records/{RECORD}", timeout=60
        ) as response:
            record = json.load(response)
    except Exception:
        return {}
    sizes: dict[str, int] = {}
    for entry in record.get("files", []):
        key = entry.get("key") or entry.get("filename")
        size = entry.get("size")
        if key and isinstance(size, int):
            sizes[key] = size
    return sizes


def fetch(name: str, sizes: dict[str, int]) -> bool:
    """Download one file, resuming nothing but never trusting a partial result.

    A 2 GB transfer can be interrupted, and an existence check alone cannot
    tell a truncated file from a finished one - the first version of this
    script reported success on a 51 MB fragment of a 2,143 MB corpus. The
    download therefore goes to a ``.part`` file that is only renamed into place
    once the whole body has arrived and the byte count matches what Zenodo
    reports.
    """
    target = DEST / name
    want = sizes.get(name)
    if target.exists():
        have = target.stat().st_size
        if want is None or have == want:
            print(f"  {name}: already present ({have/1e6:.1f} MB)")
            return True
        print(f"  {name}: incomplete ({have/1e6:.1f} of {want/1e6:.1f} MB), refetching")

    part = target.with_suffix(target.suffix + ".part")
    url = f"{BASE}/{name}?download=1"
    print(f"  {name}: downloading{f' {want/1e6:.0f} MB' if want else ''} ...", flush=True)
    written = 0
    try:
        with urllib.request.urlopen(url, timeout=180) as response, part.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
                written += len(chunk)
    except Exception as exc:  # noqa: BLE001 - report and continue with the rest
        print(f"  {name}: FAILED after {written/1e6:.1f} MB - {type(exc).__name__}: {exc}")
        part.unlink(missing_ok=True)
        return False
    if want is not None and written != want:
        print(f"  {name}: TRUNCATED {written/1e6:.1f} of {want/1e6:.1f} MB - not kept")
        part.unlink(missing_ok=True)
        return False
    part.replace(target)
    print(f"  {name}: {written/1e6:.1f} MB")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="also fetch the 2.1 GB corpus")
    args = parser.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    print(f"NMRexp (CC BY 4.0, doi:10.5281/zenodo.{RECORD}) -> {DEST}")
    print("gitignored; attribute the source if results are published\n")

    sizes = expected_sizes()
    if not sizes:
        print("  (could not read Zenodo file sizes; completeness cannot be verified)\n")
    ok = sum(fetch(name, sizes) for name in SUBSETS)
    if args.full:
        ok += fetch(FULL, sizes)
    print(f"\nfetched {ok} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
