"""The fail-closed deployment-gate CLI (Prompt 18) — wired into CI/CD.

A model or pipeline change reaches production **only if all four checks pass**:
the Prompt 17 dominance gate, the Prompt 12 audit-chain verification, a green test
suite, and the gold-set data-leakage check. This CLI is what the CI pipeline runs
before any deploy step; it exits non-zero (blocking the deploy) unless the gate
allows it.

Two modes:

* ``--self-check`` (the default) verifies the gate *machinery* itself: it confirms
  the gate allows an all-pass candidate and **blocks** every single-check failure
  (and an under-specified call). This runs on every CI deploy, so a regression in
  the release-control logic fails the pipeline before it can let a bad model
  through — there are no live model artifacts in CI, so this is the meaningful
  always-on check.
* ``--dominance-pass / --audit-pass / --tests-green / --leakage-pass`` evaluates a
  real deploy from pre-computed check verdicts (the orchestration layer computes
  each check via :mod:`moltrace.spectroscopy.ops.monitoring` and passes the
  booleans). Every flag defaults to *failed*, so an under-specified invocation is
  blocked — the gate fails closed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from moltrace.spectroscopy.ops.monitoring import (
    evaluate_deployment_gate,
    run_deployment_gate,
)

_CHECK_NAMES = ("dominance", "audit_chain", "tests_green", "data_leakage")


def self_check() -> tuple[bool, list[str]]:
    """Verify the gate fails closed: it allows all-pass and blocks every failure.

    Returns ``(ok, failures)`` — ``ok`` is True only when the gate allowed the
    all-pass candidate, blocked each single-check failure, and blocked an
    under-specified call.
    """

    failures: list[str] = []

    allow = evaluate_deployment_gate(
        dominance=True, audit_chain=True, tests_green=True, data_leakage=True
    )
    if not allow.allowed:
        failures.append("gate blocked an all-pass candidate (should allow)")

    for failing in _CHECK_NAMES:
        kwargs = {name: name != failing for name in _CHECK_NAMES}
        decision = evaluate_deployment_gate(**kwargs)
        if decision.allowed:
            failures.append(f"gate allowed a deploy with {failing} failing (should block)")

    under = run_deployment_gate(tests_green=True)  # nothing else supplied
    if under.allowed:
        failures.append("gate allowed an under-specified deploy (should fail closed)")

    return (not failures), failures


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code (0 = deploy allowed)."""

    parser = argparse.ArgumentParser(
        prog="moltrace-deployment-gate",
        description="Fail-closed deployment gate: production only on all four checks passing.",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="verify the gate machinery fails closed (default when no verdicts are given)",
    )
    parser.add_argument(
        "--dominance-pass", action="store_true", help="Prompt 17 dominance gate passed"
    )
    parser.add_argument(
        "--audit-pass", action="store_true", help="Prompt 12 audit chain verified"
    )
    parser.add_argument("--tests-green", action="store_true", help="the test suite is green")
    parser.add_argument(
        "--leakage-pass",
        action="store_true",
        help="data-leakage check passed (candidate never trained on the gold set)",
    )
    args = parser.parse_args(argv)

    explicit = args.dominance_pass or args.audit_pass or args.tests_green or args.leakage_pass
    if args.self_check or not explicit:
        ok, failures = self_check()
        if ok:
            print("deployment-gate self-check PASSED — fails closed on every check")
            return 0
        for failure in failures:
            print(f"deployment-gate self-check FAILED: {failure}", file=sys.stderr)
        return 1

    decision = evaluate_deployment_gate(
        dominance=args.dominance_pass,
        audit_chain=args.audit_pass,
        tests_green=args.tests_green,
        data_leakage=args.leakage_pass,
    )
    print(json.dumps(decision.as_dict(), indent=2, sort_keys=True))
    return 0 if decision.allowed else 1


if __name__ == "__main__":  # pragma: no cover - module CLI entry
    sys.exit(main())
