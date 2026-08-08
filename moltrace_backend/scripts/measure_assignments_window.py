#!/usr/bin/env python
"""Measure AssignmentsTest's candidate radius on held-out NMRShiftDB2.

Its objective differs from PredictionBoundsTest's, which is why it needs its own
measurement. The radius feeds a greedy bipartite assignment whose merit function then
discriminates, so **retention dominates and extra candidates are cheap**: a resonance
whose true pairing is outside the radius is penalised twice — merit 0.0, *and* its
integral counted as unexplained impurity, which lowers the test's own significance.
An extra candidate merely gets down-weighted by the merit Gaussian.

Rules compared:

    A  3.0 * base_tol                        flat, what shipped before v0.68.4
    B  3.0 * conformal_half_width            adaptive, what ships now
    C  max(A, B)                             a superset of A

Reproduce the figures in `docs/ai_ml_layer_upgrade_program.md`:

    uv run python scripts/measure_assignments_window.py
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
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

# Mirrored from verification/scorer.py.
_BASE = {"1H": 0.30, "13C": 4.0}
_EPS = {"1H": 0.03, "13C": 0.50}  # _EQUIV_EPS_PPM
DEFAULT_SOURCE = Path.home() / ".cache" / "moltrace" / "nmrshiftdb2" / "nmrshiftdb2.nmredata.sd"


def _group(values: list[tuple[float, float, float]], eps: float) -> list[dict[str, Any]]:
    """Single-linkage walk over sorted predicted shifts, mirroring _group_resonances."""

    out: list[dict[str, Any]] = []
    for pred, obs, sig in sorted(values, key=lambda v: v[0]):
        if out and abs(pred - out[-1]["last"]) <= eps:
            g = out[-1]
            g["sum"] += pred
            g["n"] += 1
            g["last"] = pred
            g["obs"].append(obs)
            if math.isfinite(sig):
                g["sigs"].append(sig)
        else:
            out.append({"sum": pred, "n": 1, "last": pred, "obs": [obs],
                        "sigs": [sig] if math.isfinite(sig) else []})
    return [
        {
            "delta": g["sum"] / g["n"],
            "sigma": (sum(g["sigs"]) / len(g["sigs"])) if g["sigs"] else float("nan"),
            "obs": g["obs"],
        }
        for g in out
    ]


def _lines(observed: list[float], eps: float) -> list[float]:
    """Collapse observed shifts a spectrometer would render as one line."""

    out: list[float] = []
    for value in sorted(observed):
        if out and abs(value - out[-1]) <= eps:
            continue
        out.append(value)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=float, default=0.90)
    args = parser.parse_args(argv)
    if not args.source.exists():
        parser.error(f"{args.source} not found; pass --source.")

    records = build_from_nmredata(args.source)
    train, calib, evalu = split_records_three_way(records)
    kb = build_knowledge_base(train)
    report = evaluate_shift_accuracy(train=train, test=calib, knowledge_base=kb)
    calibration = fit_conformal(report.sigma_error_pairs, target_coverage=args.target)

    per_mol: dict[str, dict[str, list[tuple[float, float, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for index, record in enumerate(evalu):
        mol_h = molecule_from_record(record)
        if mol_h is None:
            continue
        key = f"{record.get('smiles') or Chem.MolToSmiles(mol_h)}#{index}"
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
                continue
            predicted, sigma, _sphere, _n = hit
            per_mol[key][nucleus].append((float(predicted), observed, float(sigma)))

    def half(nucleus: str, sigma: float) -> float | None:
        return calibration.interval(nucleus, sigma).half_width_ppm

    rules = {
        "A  flat 3*base (pre-v0.68.4)": lambda nuc, sig: 3.0 * _BASE[nuc],
        "B  3*conformal (ships now)": lambda nuc, sig: (
            3.0 * half(nuc, sig) if half(nuc, sig) else 3.0 * _BASE[nuc]
        ),
        "C  max(A, B)": lambda nuc, sig: (
            max(3.0 * _BASE[nuc], 3.0 * half(nuc, sig)) if half(nuc, sig) else 3.0 * _BASE[nuc]
        ),
    }

    for label, rule in rules.items():
        stats: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for by_nucleus in per_mol.values():
            for nucleus, values in by_nucleus.items():
                eps = _EPS.get(nucleus, 0.03)
                observed_lines = _lines([o for _p, o, _s in values], eps)
                for resonance in _group(values, eps):
                    if not math.isfinite(resonance["sigma"]):
                        continue
                    radius = rule(nucleus, resonance["sigma"])
                    own = min(
                        (min(observed_lines, key=lambda x: abs(x - o)) for o in resonance["obs"]),
                        key=lambda x: abs(x - resonance["delta"]),
                    )
                    stats[nucleus]["retained"].append(
                        1.0 if abs(resonance["delta"] - own) <= radius else 0.0
                    )
                    stats[nucleus]["candidates"].append(
                        float(sum(1 for x in observed_lines
                                  if abs(resonance["delta"] - x) <= radius))
                    )
                    stats[nucleus]["radius"].append(radius)
        print(f"=== {label} ===")
        for nucleus in sorted(stats):
            s = stats[nucleus]
            print(
                f"  {nucleus}: resonances={len(s['retained'])}  "
                f"retention={statistics.fmean(s['retained']):.3%}  "
                f"mean candidates={statistics.fmean(s['candidates']):.3f}  "
                f"median radius={statistics.median(s['radius']):.3f} ppm"
            )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
