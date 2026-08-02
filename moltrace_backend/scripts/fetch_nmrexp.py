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


def fetch(name: str) -> bool:
    target = DEST / name
    if target.exists() and target.stat().st_size > 0:
        print(f"  {name}: already present ({target.stat().st_size/1e6:.1f} MB)")
        return True
    url = f"{BASE}/{name}?download=1"
    print(f"  {name}: downloading ...", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
    except Exception as exc:  # noqa: BLE001 - report and continue with the rest
        print(f"  {name}: FAILED {type(exc).__name__}: {exc}")
        target.unlink(missing_ok=True)
        return False
    print(f"  {name}: {target.stat().st_size/1e6:.1f} MB")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="also fetch the 2.1 GB corpus")
    args = parser.parse_args()

    DEST.mkdir(parents=True, exist_ok=True)
    print(f"NMRexp (CC BY 4.0, doi:10.5281/zenodo.{RECORD}) -> {DEST}")
    print("gitignored; attribute the source if results are published\n")

    ok = sum(fetch(name) for name in SUBSETS)
    if args.full:
        ok += fetch(FULL)
    print(f"\nfetched {ok} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
