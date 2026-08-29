#!/usr/bin/env python
"""Measure HOSE match error stratified by BOTH sphere depth and bucket size.

`shallow_match_fraction` gates on sphere depth alone, and that is only half the picture.
Paracetamol's ring CH predicts 5.117 ppm (literature ~6.7-7.3) from a sphere-6 bucket holding
three references: the deepest possible match, so every existing quality gate reads clean --
`shallow_match_fraction` 0.000, `prior_fallback_fraction` 0.000 -- while the prediction is
about 1.6 ppm out on a nucleus whose whole useful range is ten.

Depth says the environment matched precisely. Bucket size says how many measured examples that
precision rests on. They are independent, and a deep match on three references can be worse
than a shallow one on five hundred. This script produces the table needed to choose a
`sparse_match_fraction` threshold from data instead of picking a round number:

    MAE per (nucleus, sphere, bucket-size band), with the n behind each cell.

Same three-way molecule-level split as the conformal fitting, cut from one hash in a single
pass: the table is built from `train` only, and every error reported here is on molecules the
table has never seen.

    uv run python scripts/measure_kb_match_quality.py
    uv run python scripts/measure_kb_match_quality.py --out report.json

Needs the NMReDATA export at ~/.cache/moltrace/nmrshiftdb2/nmrshiftdb2.nmredata.sd.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_hose_kb import build_from_nmredata  # noqa: E402

from moltrace.spectroscopy.eval.shift_accuracy import split_records_three_way  # noqa: E402
from moltrace.spectroscopy.predict.nmrnet_wrapper import (  # noqa: E402
    build_knowledge_base,
    hose_code,
    molecule_from_record,
)

DEFAULT_SOURCE = Path.home() / ".cache" / "moltrace" / "nmrshiftdb2" / "nmrshiftdb2.nmredata.sd"

#: Bucket-size bands. Open at the top because the tail is long; the low bands are where the
#: question lives, so they are narrow. `_MIN_KB_MATCHES` is 3, so band "3-4" is the smallest
#: a match can currently come from.
_BANDS: tuple[tuple[str, int, int], ...] = (
    ("3-4", 3, 4),
    ("5-9", 5, 9),
    ("10-29", 10, 29),
    ("30-99", 30, 99),
    ("100+", 100, 10**9),
)


#: Sigma bands, per nucleus, spanning the reported range. The predictor's own uncertainty is
#: the gate that already exists; these make it comparable with bucket size on one axis.
_SIGMA_EDGES: dict[str, tuple[float, ...]] = {
    "1H": (0.05, 0.15, 0.30, 0.60),
    "13C": (0.5, 1.5, 3.0, 6.0),
}


def _sigma_band(nucleus: str, sigma: float) -> str:
    edges = _SIGMA_EDGES.get(nucleus)
    if not edges:
        return "n/a"
    for edge in edges:
        if sigma <= edge:
            return f"<={edge}"
    return f">{edges[-1]}"


def _band(n: int) -> str:
    for label, low, high in _BANDS:
        if low <= n <= high:
            return label
    return "<3"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--calibration-fraction", type=float, default=0.10)
    parser.add_argument("--test-fraction", type=float, default=0.10)
    args = parser.parse_args(argv)

    if not args.source.exists():
        parser.error(f"{args.source} not found; pass --source.")

    started = time.monotonic()
    records = build_from_nmredata(args.source)
    train, _calib, evalu = split_records_three_way(
        records,
        calibration_fraction=args.calibration_fraction,
        test_fraction=args.test_fraction,
    )
    kb = build_knowledge_base(train)
    print(
        f"loaded {len(records)} molecules, table {kb.reference_count} atoms, "
        f"evaluation {len(evalu)} molecules, {time.monotonic() - started:.0f}s",
        flush=True,
    )

    # (nucleus, sphere, band) -> absolute errors
    cells: dict[tuple[str, int, str], list[float]] = defaultdict(list)
    # (nucleus, band) -> absolute errors, pooled over spheres
    by_band: dict[tuple[str, str], list[float]] = defaultdict(list)
    # (nucleus, sigma band) -> absolute errors. The comparison that decides whether a
    # bucket-size gate is worth adding: the predictor already reports a per-atom sigma, and
    # a new gate has to beat the one already there.
    by_sigma: dict[tuple[str, str], list[float]] = defaultdict(list)

    for record in evalu:
        mol_h = molecule_from_record(record)
        if mol_h is None:
            continue
        for assignment in record.get("assignments", []):
            nucleus = str(assignment.get("nucleus", ""))
            try:
                atom_index = int(assignment["atom_index"])
                observed = float(assignment["shift_ppm"])
            except (KeyError, TypeError, ValueError):
                continue
            hit = kb.lookup(nucleus, hose_code(mol_h, atom_index))
            if hit is None:
                continue
            predicted, _sigma, sphere, n = hit
            if not math.isfinite(predicted) or sphere is None or n is None:
                continue
            error = abs(predicted - observed)
            cells[(nucleus, int(sphere), _band(int(n)))].append(error)
            by_band[(nucleus, _band(int(n)))].append(error)
            if _sigma is not None and math.isfinite(_sigma):
                by_sigma[(nucleus, _sigma_band(nucleus, float(_sigma)))].append(error)

    def _summarise(errors: list[float]) -> dict[str, float]:
        return {
            "n_atoms": len(errors),
            "mae_ppm": statistics.fmean(errors),
            "median_ae_ppm": statistics.median(errors),
            "p90_ae_ppm": sorted(errors)[min(len(errors) - 1, int(round(0.9 * (len(errors) - 1))))],
        }

    report: dict[str, Any] = {
        "source": str(args.source),
        "n_reference_atoms": kb.reference_count,
        "n_evaluation_molecules": len(evalu),
        "bands": [b[0] for b in _BANDS],
        "by_band": {
            f"{nucleus}|{band}": _summarise(errors)
            for (nucleus, band), errors in sorted(by_band.items())
            if errors
        },
        "by_sigma_band": {
            f"{nucleus}|{band}": _summarise(errors)
            for (nucleus, band), errors in sorted(by_sigma.items())
            if errors
        },
        "by_sphere_and_band": {
            f"{nucleus}|{sphere}|{band}": _summarise(errors)
            for (nucleus, sphere, band), errors in sorted(cells.items())
            if errors
        },
    }

    for nucleus in sorted({k[0] for k in by_band}):
        print(f"\n=== {nucleus}: pooled over spheres ===", flush=True)
        print(f"{'bucket size':>12} {'n atoms':>9} {'MAE ppm':>9} {'median':>9} {'p90':>9}")
        for label, _lo, _hi in _BANDS:
            stats = report["by_band"].get(f"{nucleus}|{label}")
            if stats:
                print(
                    f"{label:>12} {stats['n_atoms']:>9} {stats['mae_ppm']:>9.3f} "
                    f"{stats['median_ae_ppm']:>9.3f} {stats['p90_ae_ppm']:>9.3f}"
                )

        print(f"\n--- {nucleus}: deepest sphere only (the case every gate calls clean) ---")
        deepest = max(s for (nu, s, _b) in cells if nu == nucleus)
        print(f"{'bucket size':>12} {'n atoms':>9} {'MAE ppm':>9}")
        for label, _lo, _hi in _BANDS:
            stats = report["by_sphere_and_band"].get(f"{nucleus}|{deepest}|{label}")
            if stats:
                print(f"{label:>12} {stats['n_atoms']:>9} {stats['mae_ppm']:>9.3f}")

    for nucleus in sorted({k[0] for k in by_sigma}):
        print(f"\n=== {nucleus}: by the predictor's OWN reported sigma ===", flush=True)
        print(f"{'sigma band':>12} {'n atoms':>9} {'MAE ppm':>9} {'p90':>9}")
        edges = _SIGMA_EDGES[nucleus]
        for label in [f"<={e}" for e in edges] + [f">{edges[-1]}"]:
            stats = report["by_sigma_band"].get(f"{nucleus}|{label}")
            if stats:
                print(
                    f"{label:>12} {stats['n_atoms']:>9} {stats['mae_ppm']:>9.3f} "
                    f"{stats['p90_ae_ppm']:>9.3f}"
                )

    if args.out:
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
