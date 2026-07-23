"""Repho R11 — CI entrypoint for the reaction benchmark promotion gate.

Wraps :func:`nmrcheck.reaction_eval.run_benchmark_gate` in a process-exit contract so CI can block
a merge. It **never re-implements the math**: the gold-set integrity check, the metric comparison,
and the safety-recall gate all live in the frozen engine.

Exit codes (fail-closed — anything that is not a clean, verified promotion is non-zero):

* ``0`` — promotable: the candidate dominates the incumbent with no safety-flag-recall regression.
  This is still **not** an auto-deploy; the verdict requires human sign-off.
* ``1`` — blocked: a safety-recall regression and/or no metric-vector dominance.
* ``2`` — drift/integrity failure: the gold set changed, a result was not evaluated against it, or
  an input is missing/malformed. Refuse to judge rather than judge on a broken benchmark.

Usage::

    python -m nmrcheck.reaction_eval_cli \\
        --gold tests/fixtures/reaction_eval/gold_set_v1.json \\
        --candidate benchmarks/reaction/candidate.json \\
        --incumbent benchmarks/reaction/incumbent.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .reaction_eval import (
    EXIT_BLOCKED,
    EXIT_DRIFT,
    EXIT_OK,
    EvalResult,
    run_benchmark_gate,
)

_REQUIRED = ("model_version", "metrics", "safety_flag_recall")


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _eval_result_from_payload(payload: Any, label: str) -> EvalResult:
    """Rebuild an :class:`EvalResult` from a measured-results file, strictly.

    Anything missing or of the wrong shape raises — the caller maps that to ``EXIT_DRIFT`` so a
    malformed results file can never be mistaken for a passing (or merely blocked) candidate.
    """

    if not isinstance(payload, dict):
        raise ValueError(f"{label} results must be a JSON object")
    missing = [key for key in _REQUIRED if key not in payload]
    if missing:
        raise ValueError(f"{label} results missing required field(s): {missing}")
    metrics = payload["metrics"]
    if not isinstance(metrics, dict) or not metrics:
        raise ValueError(f"{label} results carry no metrics")
    return EvalResult(
        model_version=str(payload["model_version"]),
        metrics={str(k): float(v) for k, v in metrics.items()},
        safety_flag_recall=float(payload["safety_flag_recall"]),
        per_task=payload.get("per_task") or {},
        gold_checksum=payload.get("gold_checksum"),
        warnings=list(payload.get("warnings") or []),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reaction-benchmark-gate",
        description="Gate a candidate reaction optimiser against the incumbent on the frozen "
        "benchmark. Exit 0 promotable (human sign-off still required), 1 blocked, 2 drift.",
    )
    parser.add_argument("--gold", required=True, help="frozen, checksummed gold-set JSON")
    parser.add_argument("--candidate", required=True, help="candidate EvalResult JSON")
    parser.add_argument("--incumbent", required=True, help="incumbent EvalResult JSON")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="metric tolerance for dominance (never widens the safety gate)",
    )
    args = parser.parse_args(argv)

    try:
        gold_payload = _load_json(args.gold)
        candidate = _eval_result_from_payload(_load_json(args.candidate), "candidate")
        incumbent = _eval_result_from_payload(_load_json(args.incumbent), "incumbent")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        # Fail closed: an unreadable or malformed input is an integrity failure, not a pass.
        print(f"reaction-benchmark-gate: DRIFT — {exc}", file=sys.stderr)
        return EXIT_DRIFT

    outcome = run_benchmark_gate(gold_payload, candidate, incumbent, tolerance=args.tolerance)
    label = {EXIT_OK: "PROMOTABLE", EXIT_BLOCKED: "BLOCKED", EXIT_DRIFT: "DRIFT"}.get(
        outcome.exit_code, "UNKNOWN"
    )
    stream = sys.stdout if outcome.exit_code == EXIT_OK else sys.stderr
    print(f"reaction-benchmark-gate: {label} — {outcome.reason}", file=stream)
    if outcome.verdict is not None:
        print(
            f"  candidate={candidate.model_version} incumbent={incumbent.model_version} "
            f"safety_regression={outcome.verdict.safety_regression} "
            f"dominates={outcome.verdict.dominates}",
            file=stream,
        )
        for reason in outcome.verdict.reasons:
            print(f"  - {reason}", file=stream)
        if outcome.exit_code == EXIT_OK:
            print("  NOTE: promotion still requires human sign-off; this is not auto-deploy.")
    return outcome.exit_code


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    sys.exit(main())
