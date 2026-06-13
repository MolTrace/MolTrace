"""Worked-example validation corpus + runner (Prompt 21, Phase 7).

For every threshold/classification formula, a frozen set of named worked examples pins the
implementation to guideline-traceable expected values: SMILES / dose / element -> ICH M7 + CPCA +
Q3A/B/C/D outputs. ICH calculations are deterministic, so a mismatch here is a CODE BUG WITH
REGULATORY CONSEQUENCES — every numeric value is a zero-tolerance
:class:`~moltrace.regulatory.infra.eval.CalculationCheck`.

The corpus (``worked_examples.json``) is the auditable evidence; each expected value is sourced from
the engine's encoded rule-set table or a hand-verified unit-test assertion (adversarially
verified, never invented). The runner calls each public function and resolves each expected field
against the real result.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moltrace.regulatory.impurities import (
    calculate_concentration_limit,
    calculate_cumulative_risk,
    calculate_q3ab_thresholds,
    check_residual_solvent_limits,
    classify_cpca,
    classify_m7,
    classify_solvent,
    get_element_pde,
    m7_rule_set,
    risk_assessment_report,
)
from moltrace.regulatory.infra.eval import CalculationCheck

__all__ = [
    "WorkedExampleResult",
    "load_corpus",
    "run_worked_examples",
    "worked_example_checks",
]

_CORPUS_PATH = Path(__file__).with_name("worked_examples.json")
_TOLERANCE = 1e-9  # tolerate only float ULP noise; a real guideline disagreement is 0.01+ apart

#: function name (as stored in the corpus) -> the deterministic engine callable.
_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "calculate_q3ab_thresholds": calculate_q3ab_thresholds,
    "classify_solvent": classify_solvent,
    "check_residual_solvent_limits": check_residual_solvent_limits,
    "get_element_pde": get_element_pde,
    "calculate_concentration_limit": calculate_concentration_limit,
    "risk_assessment_report": risk_assessment_report,
    "classify_m7": classify_m7,
    "m7_rule_set": m7_rule_set,
    "classify_cpca": classify_cpca,
    "calculate_cumulative_risk": calculate_cumulative_risk,
}


@dataclass(frozen=True)
class WorkedExampleResult:
    """One example's outcome: numeric checks + any equality / resolution failures."""

    name: str
    calculator: str
    numeric_checks: tuple[CalculationCheck, ...]
    equality_failures: tuple[str, ...]
    unresolved: tuple[str, ...]


def load_corpus() -> dict[str, Any]:
    """The frozen worked-example corpus (the audit evidence)."""

    with _CORPUS_PATH.open() as fh:
        return json.load(fh)


def _get(cur: Any, name: str) -> Any:
    if isinstance(cur, Mapping):
        return cur[name]
    if isinstance(cur, (list, tuple)) and name.isdigit():
        return cur[int(name)]
    return getattr(cur, name)


def _resolve(result: Any, path: str) -> Any:
    """Resolve an expected-field path against a result.

    Handles dotted attribute/dict access and a leading ``"<index>_<field>"`` list-index segment
    (e.g. ``"0_class_number"`` for the first element of a list result).
    """

    cur = result
    for seg in path.split("."):
        if "_" in seg:
            head, rest = seg.split("_", 1)
            if head.isdigit():
                cur = cur[int(head)]
                seg = rest
        cur = _get(cur, seg)
    return cur


def run_worked_examples(corpus: dict[str, Any] | None = None) -> list[WorkedExampleResult]:
    """Run every worked example, building a :class:`WorkedExampleResult` per case."""

    corpus = corpus if corpus is not None else load_corpus()
    results: list[WorkedExampleResult] = []
    for calculator, body in corpus.items():
        for example in body["worked_examples"]:
            fn = _FUNCTIONS[example["function"]]
            output = fn(**example["inputs"])
            numeric: list[CalculationCheck] = []
            equality_failures: list[str] = []
            unresolved: list[str] = []
            for path, expected in example["expected"].items():
                try:
                    actual = _resolve(output, path)
                except (AttributeError, KeyError, IndexError, TypeError) as exc:
                    unresolved.append(f"{path}: {exc}")
                    continue
                if isinstance(expected, bool):
                    if actual != expected:
                        equality_failures.append(f"{path}: expected {expected!r} != {actual!r}")
                elif isinstance(expected, (int, float)):
                    numeric.append(
                        CalculationCheck(
                            f"{calculator}:{example['name']}:{path}",
                            float(actual),
                            float(expected),
                            _TOLERANCE,
                        )
                    )
                elif str(actual) != str(expected):
                    equality_failures.append(f"{path}: expected {expected!r} != {actual!r}")
            results.append(
                WorkedExampleResult(
                    name=example["name"],
                    calculator=calculator,
                    numeric_checks=tuple(numeric),
                    equality_failures=tuple(equality_failures),
                    unresolved=tuple(unresolved),
                )
            )
    return results


def worked_example_checks(
    results: list[WorkedExampleResult] | None = None,
) -> list[CalculationCheck]:
    """Every numeric :class:`CalculationCheck` across all worked examples (for the hard gate)."""

    results = results if results is not None else run_worked_examples()
    return [check for r in results for check in r.numeric_checks]
