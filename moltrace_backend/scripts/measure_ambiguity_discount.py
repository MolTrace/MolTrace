#!/usr/bin/env python
"""Measure the ambiguity discount's aggregate effect on held-out NMRShiftDB2.

`PredictionBoundsTest` weights each matched resonance by `_ambiguity_weight` — the
normalised likelihood that the line the matcher chose is the right one, given the
alternatives inside the same window. Per-resonance rival statistics were measured when
the discount landed; this measures the thing that actually reaches a user: **how much
evidence the verifier was over-claiming**.

The chain it reports through is the scorer's own:

    significance → quality = score · tanh(significance / 3) → log-odds += quality · LN10

so for a fully corroborating test (score = +1) the odds multiplier is 10^quality. The
difference between the multiplier before and after the discount is the honest statement
of what changed.

Replicates `_group_resonances` (ε = 0.50 ppm ¹³C / 0.03 ppm ¹H) on the predicted side and
deduplicates observed shifts to lines at the same resolution, so the candidate sets are
the ones the test really sees rather than raw per-atom ones.

    uv run python scripts/measure_ambiguity_discount.py
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
from moltrace.spectroscopy.verification.scorer import (  # noqa: E402
    _SIGMA_REF_PPM,
    _ambiguity_weight,
    _significance_from_half_width,
)

_BASE = {"1H": 0.30, "13C": 4.0}
_K = 3.0
_EPS = {"1H": 0.03, "13C": 0.50}
DEFAULT_SOURCE = Path.home() / ".cache" / "moltrace" / "nmrshiftdb2" / "nmrshiftdb2.nmredata.sd"


def _group(values: list[tuple[float, float, float]], eps: float) -> list[dict[str, Any]]:
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
        {"delta": g["sum"] / g["n"],
         "sigma": (sum(g["sigs"]) / len(g["sigs"])) if g["sigs"] else float("nan")}
        for g in out
    ]


def _lines(observed: list[float], eps: float) -> list[float]:
    out: list[float] = []
    for value in sorted(observed):
        if out and abs(value - out[-1]) <= eps:
            continue
        out.append(value)
    return out


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[idx]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=float, default=0.90)
    parser.add_argument(
        "--floor",
        type=float,
        action="append",
        dest="floors",
        help="ambiguity-weight floor to score; repeatable (default: sweep 0.0-0.5)",
    )
    args = parser.parse_args(argv)
    floors = tuple(args.floors or (0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50))
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

    weights: dict[str, list[float]] = defaultdict(list)
    sig_before: dict[str, list[float]] = defaultdict(list)
    sig_after: dict[str, list[float]] = defaultdict(list)

    for by_nucleus in per_mol.values():
        for nucleus, values in by_nucleus.items():
            eps = _EPS.get(nucleus, 0.03)
            observed_lines = _lines([o for _p, o, _s in values], eps)
            reference = calibration.reference_half_width(
                nucleus, _SIGMA_REF_PPM.get(nucleus, _SIGMA_REF_PPM["1H"])
            )
            for resonance in _group(values, eps):
                sigma = resonance["sigma"]
                if not math.isfinite(sigma):
                    continue
                tol = max(_BASE[nucleus], _K * sigma)
                in_window = [
                    abs(resonance["delta"] - x)
                    for x in observed_lines
                    if abs(resonance["delta"] - x) <= tol
                ]
                if not in_window:
                    continue
                chosen = min(range(len(in_window)), key=lambda i: in_window[i])
                half_width = calibration.interval(nucleus, sigma).half_width_ppm
                scale = half_width if half_width is not None else sigma
                weight = _ambiguity_weight(in_window, chosen=chosen, scale_ppm=float(scale))
                significance = _significance_from_half_width(
                    half_width, reference_half_width=reference
                )
                weights[nucleus].append(weight)
                sig_before[nucleus].append(significance)
                sig_after[nucleus].append(weight * significance)

    ln10 = math.log(10.0)

    def posterior(quality: float) -> float:
        """Posterior from a 0.50 prior after one test of this quality."""

        return 1.0 / (1.0 + math.exp(-(quality * ln10)))

    print(
        "NOTE: weights already carry the shipped _AMBIGUITY_FLOOR, so the f = 0.00 row is\n"
        "      today's behaviour and the rest show an ADDITIONAL floor on top of it.\n"
        "      max() is idempotent, so the hard-floor column reads directly; the affine\n"
        "      column composes with the shipped floor.\n"
    )
    for nucleus in sorted(weights):
        w = weights[nucleus]
        raw_sig = sig_before[nucleus]
        before = statistics.fmean(raw_sig)
        q_before = math.tanh(before / 3.0)
        print(f"=== {nucleus}: {len(w)} matched resonances ===")
        print(
            f"  ambiguity weight   mean={statistics.fmean(w):.4f}  "
            f"median={statistics.median(w):.4f}"
            f"  p10={_pct(w, 0.10):.4f}  p25={_pct(w, 0.25):.4f}  p90={_pct(w, 0.90):.4f}"
        )
        print(
            f"  undiscounted (>0.99)={sum(1 for x in w if x > 0.99) / len(w):.1%}   "
            f"halved or worse (<0.5)={sum(1 for x in w if x < 0.5) / len(w):.1%}"
        )
        print(
            f"  undiscounted baseline: mean significance {before:.3f}, "
            f"quality {q_before:.4f}, odds x{10 ** q_before:.2f}, "
            f"posterior-from-0.50 {posterior(q_before):.4f}"
        )
        # Two softenings, because they do very different things. A HARD floor
        # max(f, w) only lifts the tail, and the tail contributes little to a mean
        # over tens of thousands of resonances. An AFFINE floor f + (1-f)*w lifts the
        # whole distribution, which is the only lever that moves the aggregate.
        for form, apply, label in (
            ("hard", lambda f, x: max(f, x), "max(f, w)"),
            ("affine", lambda f, x: f + (1.0 - f) * x, "f + (1-f)*w"),
        ):
            print(f"  --- {form} floor: {label} ---")
            print(f"  {'f':>6}  {'mean w':>7}  {'touched':>8}  {'mean sig':>9}"
                  f"  {'quality':>8}  {'odds':>7}  {'posterior':>10}  verdict")
            for floor in floors:
                adjusted = [apply(floor, x) for x in w]
                touched = (
                    sum(1 for x in w if x < floor) / len(w)
                    if form == "hard"
                    else (1.0 if floor > 0.0 else 0.0)
                )
                after = statistics.fmean(
                    a * s for a, s in zip(adjusted, raw_sig, strict=True)
                )
                q_after = math.tanh(after / 3.0)
                p_after = posterior(q_after)
                verdict = "consistent" if p_after >= 0.80 else "inconclusive"
                print(
                    f"  {floor:6.2f}  {statistics.fmean(adjusted):7.4f}  {touched:7.1%}"
                    f"  {after:9.3f}  {q_after:8.4f}  x{10 ** q_after:6.2f}"
                    f"  {p_after:10.4f}  {verdict}"
                )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
