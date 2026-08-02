#!/usr/bin/env python3
"""Run the proton-inventory invariants across NMRexp at scale.

NMRexp records are literature 1H strings paired with a structure - the same
input shape as MolTrace's ``nmr_text_guided`` path. That makes the corpus a
direct, large-scale test of the classifier on real published data.

The invariants asserted are statements of chemistry that must hold for ANY
molecule, so a violation is a defect rather than a disagreement:

  * observed anomeric/olefinic H may not exceed what the structure supports;
  * the expected classes must PARTITION the non-labile total;
  * a class total may not be negative.

It also measures how much of the corpus we can read at all. The text parser
rejecting a real published format is itself a finding: on a 3.37M-record corpus
a few percent is tens of thousands of spectra silently dropped.

Streams the CSV, so the 2.1 GB file needs no more memory than one row.

    .venv/bin/python scripts/validate_against_nmrexp.py --limit 50000
"""

from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "corpus_store" / "nmrexp" / "NMRexp_10to24_1_1004.csv"
sys.path.insert(0, str(ROOT / "src"))
csv.field_size_limit(10_000_000)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--limit", type=int, default=20000, help="1H records to analyse")
    parser.add_argument("--show", type=int, default=12, help="violations to print")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"missing {args.csv}\nrun: .venv/bin/python scripts/fetch_nmrexp.py --full")
        return 1

    from nmrcheck.chemistry import structure_summary_from_smiles
    from nmrcheck.parser import parse_reference_nmr_text
    from nmrcheck.peak_categorization import build_proton_inventory, enrich_peaks

    stat: collections.Counter[str] = collections.Counter()
    parse_errors: collections.Counter[str] = collections.Counter()
    violations: list[tuple[str, str, str]] = []
    seen = 0

    with args.csv.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if "1H" not in (row.get("NMR_type") or ""):
                continue
            seen += 1
            if seen > args.limit:
                break
            smiles = (row.get("smiles_actual") or row.get("SMILES") or "").strip()
            text = (row.get("NMR_shift_text") or "").strip()
            solvent = (row.get("NMR_solvent") or "").strip() or None
            if not smiles or not text:
                stat["missing_fields"] += 1
                continue
            try:
                structure = structure_summary_from_smiles(smiles)
            except Exception:
                stat["smiles_reject"] += 1
                continue
            try:
                _, assignments = parse_reference_nmr_text(text)
            except Exception as exc:
                stat["parse_reject"] += 1
                parse_errors[str(exc)[:90]] += 1
                continue
            if not assignments:
                stat["parse_empty"] += 1
                continue

            # A record the Peak model refuses must be COUNTED, not fatal. The
            # first run of this survey died on record 1 of 50,000 because a
            # single published integration exceeded a model bound; a survey
            # that aborts on its first finding cannot measure anything.
            try:
                peaks = []
                for assignment in assignments:
                    peak = assignment.as_peak().model_dump()
                    peak["inventory_basis"] = "nmr_text"
                    peak["j_values_hz"] = list(peak.get("j_values_hz") or [])
                    peaks.append(peak)
            except Exception as exc:  # noqa: BLE001
                stat["peak_reject"] += 1
                parse_errors[f"as_peak: {str(exc).splitlines()[-1][:70]}"] += 1
                continue
            try:
                enriched = enrich_peaks(
                    peaks=peaks, nucleus="1H", solvent=solvent, structure=structure
                )
                inventory = build_proton_inventory(
                    peaks=enriched, structure=structure, nucleus="1H", solvent=solvent
                )
            except Exception as exc:
                stat["analysis_error"] += 1
                violations.append(("analysis_error", smiles[:48], f"{type(exc).__name__}: {exc}"))
                continue

            stat["analysed"] += 1
            observed = inventory["observed"]
            expected = inventory.get("expected") or {}
            if not expected:
                continue

            if observed["anomeric_or_olefinic"] > expected["anomeric_or_olefinic"] + 1e-6:
                stat["violation_anomeric"] += 1
                violations.append((
                    "anomeric over-assigned", smiles[:48],
                    f"{observed['anomeric_or_olefinic']} > {expected['anomeric_or_olefinic']}",
                ))
            parts = sum(
                float(expected.get(k, 0) or 0)
                for k in ("aromatic", "anomeric_or_olefinic", "aliphatic", "aldehyde")
            )
            if abs(parts - float(expected["non_labile"])) > 1e-6:
                stat["violation_partition"] += 1
                violations.append((
                    "partition broken", smiles[:48],
                    f"parts {parts} != non_labile {expected['non_labile']}",
                ))
            if any(float(v) < -1e-6 for v in observed.values() if isinstance(v, (int, float))):
                stat["violation_negative"] += 1
                violations.append(("negative class total", smiles[:48], str(observed)))

    keys = ("analysed", "parse_reject", "parse_empty", "peak_reject",
            "smiles_reject", "missing_fields", "analysis_error")
    total = sum(stat[k] for k in keys)
    print(f"1H records examined : {total}")
    for key in keys:
        if stat[key]:
            print(f"  {key:<16} {stat[key]:>7}  ({stat[key]/max(1,total):.1%})")

    print(f"\nINVARIANT VIOLATIONS across {stat['analysed']} analysed spectra:")
    for key in ("violation_anomeric", "violation_partition", "violation_negative"):
        print(f"  {key:<22} {stat[key]}")

    if parse_errors:
        print("\ntop parser rejections (a real published format we cannot read):")
        for message, count in parse_errors.most_common(6):
            print(f"  {count:>6}x  {message}")

    if violations:
        print(f"\nexamples ({min(args.show, len(violations))} of {len(violations)}):")
        for kind, smiles, detail in violations[:args.show]:
            print(f"  [{kind}] {smiles}  {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
