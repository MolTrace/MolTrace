#!/usr/bin/env python
"""Fit and score conformal prediction intervals on held-out NMRShiftDB2.

Why this is a script and not a test: it needs the full 284 MB NMReDATA export and
takes about a minute, but the number it produces is one MolTrace publishes, and a
published number that cannot be re-derived is a claim rather than a measurement.
Run it to reproduce the figures in `docs/ai_ml_layer_upgrade_program.md`.

Three molecule-level splits, cut from one hash in a single pass so they are
genuinely disjoint (see `split_records_three_way` for the trap that makes the
obvious two-call version return an empty calibration set):

  train        builds the HOSE table
  calibration  fits the conformal bands -- never scored
  evaluation   scores coverage -- never seen by table or bands

Usage:

    uv run python scripts/measure_conformal_calibration.py
    uv run python scripts/measure_conformal_calibration.py --out /tmp/report.json

The source defaults to the cached export at
``~/.cache/moltrace/nmrshiftdb2/nmrshiftdb2.nmredata.sd``; pass ``--source`` for
another copy. Nothing is written unless ``--out`` is given.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_hose_kb import build_from_nmredata  # noqa: E402

from moltrace.spectroscopy.eval.conformal import fit_conformal, measure_coverage  # noqa: E402
from moltrace.spectroscopy.eval.shift_accuracy import (  # noqa: E402
    evaluate_shift_accuracy,
    split_records_three_way,
)
from moltrace.spectroscopy.predict.nmrnet_wrapper import build_knowledge_base  # noqa: E402

DEFAULT_SOURCE = Path.home() / ".cache" / "moltrace" / "nmrshiftdb2" / "nmrshiftdb2.nmredata.sd"
DEFAULT_TARGETS = (0.90, 0.95)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=None, help="write the full report as JSON")
    parser.add_argument("--calibration-fraction", type=float, default=0.10)
    parser.add_argument("--test-fraction", type=float, default=0.10)
    parser.add_argument(
        "--target",
        type=float,
        action="append",
        dest="targets",
        help="coverage target; repeatable (default: 0.90 and 0.95)",
    )
    args = parser.parse_args(argv)

    if not args.source.exists():
        parser.error(
            f"{args.source} not found. Fetch the NMReDATA export first, or pass --source."
        )
    targets = tuple(args.targets or DEFAULT_TARGETS)

    started = time.monotonic()
    records = build_from_nmredata(args.source)
    print(f"loaded {len(records)} molecules in {time.monotonic() - started:.0f}s", flush=True)

    train, calib, evalu = split_records_three_way(
        records,
        calibration_fraction=args.calibration_fraction,
        test_fraction=args.test_fraction,
    )
    print(f"train={len(train)}  calibration={len(calib)}  evaluation={len(evalu)}", flush=True)
    if not (train and calib and evalu):
        parser.error("a split came back empty; check the fractions")

    started = time.monotonic()
    kb = build_knowledge_base(train)
    print(
        f"table built: {kb.reference_count} reference atoms "
        f"in {time.monotonic() - started:.0f}s",
        flush=True,
    )

    calib_report = evaluate_shift_accuracy(train=train, test=calib, knowledge_base=kb)
    eval_report = evaluate_shift_accuracy(train=train, test=evalu, knowledge_base=kb)

    out: dict[str, Any] = {
        "source": str(args.source),
        "n_molecules": {"train": len(train), "calibration": len(calib), "evaluation": len(evalu)},
        "n_reference_atoms": kb.reference_count,
        "accuracy_on_evaluation_split": eval_report.per_nucleus,
        "sigma_calibration_table": eval_report.calibration,
    }

    for target in targets:
        calibration = fit_conformal(calib_report.sigma_error_pairs, target_coverage=target)
        coverage = measure_coverage(calibration, eval_report.sigma_error_pairs)
        out[f"conformal_{int(round(target * 100))}"] = {
            "calibration": calibration.as_dict(),
            "coverage": coverage.as_dict(),
        }

        print(f"\n=== target {target:.0%} ===", flush=True)
        for nucleus, stats in coverage.per_nucleus.items():
            bands = [b for b in calibration.bins if b.nucleus == nucleus]
            ratios = [b.half_width_ppm / b.mean_sigma_ppm for b in bands if b.mean_sigma_ppm > 0]
            print(
                f"  {nucleus}: n={int(stats['n'])} "
                f"coverage={stats['coverage']:.3%} "
                f"mean half-width={stats['mean_half_width_ppm']:.3f} ppm "
                f"median={stats['median_half_width_ppm']:.3f} ppm",
                flush=True,
            )
            if ratios:
                # A correctly-scaled sigma gives a CONSTANT half-width/sigma ratio,
                # whatever the error distribution -- it is that distribution's
                # quantile expressed in units of sigma. A ratio that varies across
                # bands means sigma is not a consistent scale.
                print(
                    f"      half-width/σ  tightest band {ratios[0]:.2f}× → "
                    f"widest {ratios[-1]:.2f}×  (spread {ratios[0] / ratios[-1]:.2f}×)",
                    flush=True,
                )
        print(f"  worst coverage deficit: {coverage.worst_deficit:.5f}", flush=True)
        for note in coverage.notes:
            print(f"  note: {note}", flush=True)

    if args.out is not None:
        args.out.write_text(json.dumps(out, indent=2, default=str))
        print(f"\nwrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
