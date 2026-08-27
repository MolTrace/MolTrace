#!/usr/bin/env python
"""Measure what the verifier's match tolerance costs and buys, on held-out data.

`PredictionBoundsTest` decides whether a predicted shift matches an observed line
with `tol = max(base, 3σ)` and `_SHIFT_TOL_PPM = {"1H": 0.30, "13C": 4.0}`. The ¹³C
base is a round number, and measurement showed σ is differentially mis-scaled, so
the window derived from it is too permissive — most for the atoms the predictor is
most confident about.

Replacing it with a conformal window is not automatically an improvement, and this
script exists to stop that being asserted. Two quantities move in opposite
directions and both have to be reported:

  RETENTION  the share of atoms whose *true* observed shift falls inside the window.
             A narrower window misses real lines, which the verifier scores as a
             failure to corroborate — a false negative on a correct structure.

  EXPOSURE   the mean number of *other* atoms in the same molecule whose observed
             shift also falls inside the window. Every one of those is a line the
             matcher could bind instead, scoring a wrong assignment as
             corroboration.

             This is computed from reference shifts — one line per atom — not from
             detected peaks. It was previously described here as a LOWER bound, on
             the reasoning that a picker over-picking 3-7x puts more candidate lines
             in a real spectrum. **Measured, that is wrong in direction.** Counting
             rivals against what the matcher actually sees (13C: classified compound
             peaks; 1H: clustered environments) over the 19-fixture Bruker corpus,
             detected rival density is 0.16-0.41x the reference-shift estimate across
             every window tried, rising gently with width but never approaching 1.

             The mechanism: a reference list carries every distinct atom environment,
             and a real spectrum does not resolve them all — an unresolved pair
             contributes two reference rivals and one detected line — while
             auto_classify removes the solvent, artifact and satellite picks that the
             raw over-pick factor counts. So exposure here OVERSTATES the rival
             density a wide window really faces, which cuts against wide windows, not
             for them. On 19 fixtures; a larger corpus could move it.

Sweeping the coverage target lets the window be chosen from the measured
distribution rather than from a round number. Note the reported interval and the
matching window answer different questions and need not share a target: 90 % is a
reasonable thing to *tell* a user, while a matcher wants to be confident it has not
excluded the true line.

    uv run python scripts/measure_match_tolerance.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_hose_kb import build_from_nmredata  # noqa: E402
from rdkit import Chem  # noqa: E402

from moltrace.spectroscopy.eval.conformal import fit_conformal  # noqa: E402
from moltrace.spectroscopy.eval.shift_accuracy import (  # noqa: E402
    evaluate_shift_accuracy,
    split_records_three_way,
)
from moltrace.spectroscopy.predict.nmrnet_wrapper import (  # noqa: E402
    build_knowledge_base,
    hose_code,
    molecule_from_record,
)

# The constants under test, mirrored from verification/scorer.py.
_SHIFT_TOL_PPM = {"1H": 0.30, "13C": 4.0}
_TOL_SIGMA_K = 3.0

DEFAULT_SOURCE = Path.home() / ".cache" / "moltrace" / "nmrshiftdb2" / "nmrshiftdb2.nmredata.sd"
DEFAULT_TARGETS = (0.90, 0.95, 0.99)


def _atoms_by_molecule(
    records: list[dict[str, Any]], kb: Any
) -> dict[str, list[tuple[str, float, float, float]]]:
    """molecule key -> [(nucleus, predicted, observed, sigma)] for matched atoms."""

    out: dict[str, list[tuple[str, float, float, float]]] = defaultdict(list)
    for index, record in enumerate(records):
        mol_h = molecule_from_record(record)
        if mol_h is None:
            continue
        key = record.get("smiles") or Chem.MolToSmiles(mol_h) or str(index)
        n_atoms = mol_h.GetNumAtoms()
        for assignment in record.get("assignments", []):
            nucleus = str(assignment.get("nucleus", ""))
            atom_index = int(assignment.get("atom_index", -1))
            if not (0 <= atom_index < n_atoms):
                continue
            try:
                observed = float(assignment["shift_ppm"])
            except (KeyError, TypeError, ValueError):
                continue
            hit = kb.lookup(nucleus, hose_code(mol_h, atom_index))
            if hit is None:
                continue  # element-prior atoms carry no sigma; nothing to window
            predicted, sigma, _sphere, _n = hit
            out[f"{key}#{index}"].append((nucleus, float(predicted), observed, float(sigma)))
    return out


def _score_rule(
    molecules: dict[str, list[tuple[str, float, float, float]]],
    window: Any,
) -> dict[str, dict[str, float]]:
    """Retention and exposure for one windowing rule, per nucleus."""

    retained: dict[str, list[int]] = defaultdict(list)
    exposure: dict[str, list[int]] = defaultdict(list)
    widths: dict[str, list[float]] = defaultdict(list)
    skipped: dict[str, int] = defaultdict(int)

    for atoms in molecules.values():
        observed_by_nucleus: dict[str, list[float]] = defaultdict(list)
        for nucleus, _pred, obs, _sig in atoms:
            observed_by_nucleus[nucleus].append(obs)

        for nucleus, predicted, observed, sigma in atoms:
            half = window(nucleus, sigma)
            if half is None:
                skipped[nucleus] += 1
                continue
            widths[nucleus].append(half)
            retained[nucleus].append(1 if abs(predicted - observed) <= half else 0)
            others = sum(
                1
                for other in observed_by_nucleus[nucleus]
                if other != observed and abs(predicted - other) <= half
            )
            exposure[nucleus].append(others)

    out: dict[str, dict[str, float]] = {}
    for nucleus in sorted(widths):
        out[nucleus] = {
            "n": float(len(widths[nucleus])),
            "retention": statistics.fmean(retained[nucleus]) if retained[nucleus] else 0.0,
            "mean_exposure": statistics.fmean(exposure[nucleus]) if exposure[nucleus] else 0.0,
            "share_with_a_rival_line": (
                statistics.fmean([1 if e else 0 for e in exposure[nucleus]])
                if exposure[nucleus]
                else 0.0
            ),
            "mean_half_width_ppm": statistics.fmean(widths[nucleus]),
            "median_half_width_ppm": statistics.median(widths[nucleus]),
            "no_window": float(skipped.get(nucleus, 0)),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--target", type=float, action="append", dest="targets")
    args = parser.parse_args(argv)

    if not args.source.exists():
        parser.error(f"{args.source} not found; pass --source.")
    targets = tuple(args.targets or DEFAULT_TARGETS)

    started = time.monotonic()
    records = build_from_nmredata(args.source)
    train, calib, evalu = split_records_three_way(records)
    kb = build_knowledge_base(train)
    print(
        f"loaded {len(records)} molecules, table {kb.reference_count} atoms, "
        f"{time.monotonic() - started:.0f}s",
        flush=True,
    )

    calib_report = evaluate_shift_accuracy(train=train, test=calib, knowledge_base=kb)
    molecules = _atoms_by_molecule(list(evalu), kb)
    n_atoms = sum(len(v) for v in molecules.values())
    print(f"evaluation: {len(molecules)} molecules, {n_atoms} matched atoms\n", flush=True)

    def current(nucleus: str, sigma: float) -> float:
        return max(_SHIFT_TOL_PPM.get(nucleus, 0.30), _TOL_SIGMA_K * sigma)

    results: dict[str, Any] = {"current": _score_rule(molecules, current)}
    print("=== current rule: max(base, 3σ) ===", flush=True)
    _report(results["current"])

    for target in targets:
        calibration = fit_conformal(calib_report.sigma_error_pairs, target_coverage=target)

        def conformal(nucleus: str, sigma: float, _c: Any = calibration) -> float | None:
            return _c.interval(nucleus, sigma).half_width_ppm

        key = f"conformal_{int(round(target * 100))}"
        results[key] = _score_rule(molecules, conformal)
        print(f"\n=== conformal window at {target:.0%} ===", flush=True)
        _report(results[key])

    if args.out is not None:
        args.out.write_text(json.dumps(results, indent=2, default=str))
        print(f"\nwrote {args.out}", flush=True)
    return 0


def _report(scored: dict[str, dict[str, float]]) -> None:
    for nucleus, stats in scored.items():
        print(
            f"  {nucleus}: n={int(stats['n'])}  retention={stats['retention']:.3%}  "
            f"mean exposure={stats['mean_exposure']:.3f} rival lines  "
            f"({stats['share_with_a_rival_line']:.1%} of atoms have ≥1)  "
            f"median window={stats['median_half_width_ppm']:.3f} ppm",
            flush=True,
        )


if __name__ == "__main__":
    raise SystemExit(main())
