"""Phase 7 launch gate (Prompt 21).

ICH calculations are deterministic — an error is a code bug with regulatory consequences — so the
ComplianceCore must NOT launch until every validation check is green: worked-example zero-error +
100% formula coverage, a complete formula->citation map (no untraceable formula), the ICH property
invariants, and external reproductions (NDSRI + EMA). :func:`enforce_launch_gate`
raises on any red; :func:`launch_gate_exit_code` maps the gate to a CI exit code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from moltrace.regulatory.infra.eval import calculation_errors
from moltrace.regulatory.validation.citation_map import (
    implemented_formulas,
    untraceable_formulas,
)
from moltrace.regulatory.validation.external_validation import validate_ema_qa, validate_ndsri
from moltrace.regulatory.validation.property_invariants import run_property_invariants
from moltrace.regulatory.validation.worked_examples import run_worked_examples

__all__ = [
    "CheckResult",
    "LaunchGateError",
    "LaunchGateResult",
    "enforce_launch_gate",
    "evaluate_launch_gate",
    "launch_gate_exit_code",
]


class LaunchGateError(RuntimeError):
    """Raised by :func:`enforce_launch_gate` when the validation suite is not fully green."""


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class LaunchGateResult:
    passed: bool
    checks: tuple[CheckResult, ...]

    def failed_checks(self) -> list[str]:
        return [c.name for c in self.checks if not c.passed]

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": [c.as_dict() for c in self.checks]}


def evaluate_launch_gate() -> LaunchGateResult:
    """Run every validation check; return the aggregate go/no-go result."""

    checks: list[CheckResult] = []

    # 1. Worked examples — zero calculation errors + no equality / resolution failures.
    we = run_worked_examples()
    we_calc_errors = [e for r in we for e in calculation_errors(r.numeric_checks)]
    we_eq = [f for r in we for f in r.equality_failures]
    we_unresolved = [u for r in we for u in r.unresolved]
    n_numeric = sum(len(r.numeric_checks) for r in we)
    checks.append(
        CheckResult(
            "worked_examples",
            not (we_calc_errors or we_eq or we_unresolved),
            f"{len(we)} examples, {n_numeric} numeric checks; "
            f"{len(we_calc_errors)} calc errors, {len(we_eq)} equality fails, "
            f"{len(we_unresolved)} unresolved",
        )
    )

    # 2. Formula -> citation map complete (100% coverage, every formula traceable).
    untraceable = untraceable_formulas()
    checks.append(
        CheckResult(
            "formula_citation_map",
            not untraceable,
            f"{len(implemented_formulas())} formulas, "
            f"{len(untraceable)} untraceable: {untraceable}",
        )
    )

    # 3. ICH property invariants.
    invariants = run_property_invariants()
    inv_failed = [i.name for i in invariants if not i.passed]
    checks.append(
        CheckResult(
            "property_invariants",
            not inv_failed,
            f"{len(invariants)} invariants, "
            f"{sum(i.cases for i in invariants)} cases; failed: {inv_failed}",
        )
    )

    # 4. External reference reproductions (FDA NDSRI + EMA Q&A).
    ndsri = validate_ndsri()
    ema = validate_ema_qa()
    checks.append(
        CheckResult(
            "external_ndsri", ndsri.ok, f"{ndsri.n_compounds} compounds; {ndsri.category_failures}"
        )
    )
    checks.append(
        CheckResult("external_ema", ema.ok, f"{ema.n_compounds} compounds; {ema.category_failures}")
    )

    return LaunchGateResult(passed=all(c.passed for c in checks), checks=tuple(checks))


def enforce_launch_gate() -> None:
    """Raise :class:`LaunchGateError` unless the validation suite is fully green."""

    result = evaluate_launch_gate()
    if not result.passed:
        raise LaunchGateError(
            f"ComplianceCore launch gate is RED — do not go live. Failed: {result.failed_checks()}"
        )


def launch_gate_exit_code() -> int:
    """CI exit code: ``0`` if the suite is fully green (go-live), ``1`` otherwise."""

    return 0 if evaluate_launch_gate().passed else 1
