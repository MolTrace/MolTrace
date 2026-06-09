"""The regulatory metric layer — the single source of truth for "better" (Prompt 19).

These are pure, unit-tested functions. They are the measurement substrate the
Prompt 17 zero-tolerance evaluation gate and the Prompt 21 GAMP 5 CSV package are
built on. The two **hard gates** for a regulated module are enforced here:

* **calculation-error rate must be 0** — a regulated number (an ICH threshold, a
  PDE, an AI limit, an M7/CPCA class) that disagrees with ground truth is a code
  bug with regulatory consequences, never an acceptable "miss";
* **formula coverage must be 100%** — every in-scope calculation must be
  implemented before a version can ship.

Everything else (classification accuracy vs expert, citation correctness,
hallucination rate, narrative-acceptance + edit distance, needs-review precision)
is a quality metric that the Prompt 17 dominance gate compares across versions.

Reuse-first: the confusion-count primitives (:class:`PRF`, :func:`f1_score`,
:func:`classification_f1`) and the deterministic content hash come straight from
the spectroscopy Phase 0 foundation — one source of truth, one tested implementation.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from moltrace.spectroscopy.infra.contract import content_hash
from moltrace.spectroscopy.infra.eval import PRF, classification_f1, f1_score

__all__ = [
    "CalculationCheck",
    "CitationCheck",
    "ClaimCheck",
    "ClassificationAccuracy",
    "HardGateError",
    "NarrativeReview",
    "RegulatoryEvalError",
    "RegulatoryMetricVector",
    "calculation_error_rate",
    "calculation_errors",
    "citation_correctness",
    "classification_accuracy",
    "enforce_full_coverage",
    "enforce_hard_gates",
    "enforce_zero_calculation_errors",
    "formula_coverage",
    "hallucination_rate",
    "levenshtein",
    "mean_edit_distance",
    "missing_formulas",
    "narrative_acceptance_rate",
    "needs_review_precision",
    "normalized_edit_distance",
]


class RegulatoryEvalError(ValueError):
    """Base error for the regulatory evaluation layer."""


class HardGateError(RegulatoryEvalError):
    """A zero-tolerance gate failed (a regulated number is wrong, or coverage < 100%)."""


# --------------------------------------------------------------------------- #
# 1. Calculation-error rate (HARD GATE: must be 0)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CalculationCheck:
    """One regulated number compared against its guideline ground truth.

    ``tolerance`` is an **absolute** tolerance and defaults to ``0.0`` — regulated
    thresholds must reproduce the guideline value exactly. Use a small tolerance
    only for values the guideline itself specifies to finite precision.
    """

    name: str
    computed: float
    expected: float
    tolerance: float = 0.0

    def is_error(self) -> bool:
        return not math.isclose(
            float(self.computed), float(self.expected), rel_tol=0.0, abs_tol=float(self.tolerance)
        )


def calculation_errors(checks: Iterable[CalculationCheck]) -> list[CalculationCheck]:
    """Every check whose computed value disagrees with ground truth beyond tolerance."""

    return [c for c in checks if c.is_error()]


def calculation_error_rate(checks: Iterable[CalculationCheck]) -> float:
    """Fraction of regulated calculations that disagree with ground truth (target 0)."""

    materialized = list(checks)
    if not materialized:
        return 0.0
    return len(calculation_errors(materialized)) / len(materialized)


def enforce_zero_calculation_errors(checks: Iterable[CalculationCheck]) -> None:
    """Raise :class:`HardGateError` if any regulated calculation is wrong."""

    errors = calculation_errors(checks)
    if errors:
        detail = ", ".join(
            f"{e.name}: computed {e.computed} != expected {e.expected}" for e in errors
        )
        raise HardGateError(f"{len(errors)} calculation error(s): {detail}")


# --------------------------------------------------------------------------- #
# 2. Formula coverage (HARD GATE: must be 100%)
# --------------------------------------------------------------------------- #
def formula_coverage(implemented: Iterable[str], required: Iterable[str]) -> float:
    """Fraction of in-scope formulas that are implemented (target 1.0)."""

    req = {str(r) for r in required}
    if not req:
        return 1.0
    impl = {str(i) for i in implemented}
    return len(impl & req) / len(req)


def missing_formulas(implemented: Iterable[str], required: Iterable[str]) -> list[str]:
    """The in-scope formulas not yet implemented (sorted)."""

    return sorted({str(r) for r in required} - {str(i) for i in implemented})


def enforce_full_coverage(implemented: Iterable[str], required: Iterable[str]) -> None:
    """Raise :class:`HardGateError` unless every in-scope formula is implemented."""

    missing = missing_formulas(implemented, required)
    if missing:
        raise HardGateError(f"formula coverage < 100%: missing {missing}")


# --------------------------------------------------------------------------- #
# 3. Classification accuracy vs expert adjudication (CPCA / M7)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ClassificationAccuracy:
    """Accuracy + macro-F1 of predicted classes vs expert adjudication."""

    accuracy: float
    macro_f1: float
    n: int
    prf: PRF

    def as_dict(self) -> dict[str, float]:
        return {"accuracy": self.accuracy, "macro_f1": self.macro_f1, "n": float(self.n)}


def classification_accuracy(
    predicted: Sequence[Any],
    expert: Sequence[Any],
    *,
    labels: Sequence[Any] | None = None,
) -> ClassificationAccuracy:
    """Exact-match accuracy + macro-F1 of ``predicted`` vs ``expert`` labels.

    Reuses the tested multiclass :func:`classification_f1` for the F1 breakdown.
    """

    if len(predicted) != len(expert):
        raise RegulatoryEvalError("predicted and expert must be the same length")
    if not expert:
        raise RegulatoryEvalError("classification_accuracy requires at least one label")
    correct = sum(1 for p, t in zip(predicted, expert, strict=True) if p == t)
    accuracy = correct / len(expert)
    prf = classification_f1(predicted, expert, labels=labels, average="macro")
    return ClassificationAccuracy(accuracy=accuracy, macro_f1=prf.f1, n=len(expert), prf=prf)


# --------------------------------------------------------------------------- #
# 4. Citation correctness + 5. hallucination rate
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CitationCheck:
    """A claim with its cited source and whether that source actually supports it."""

    claim: str
    cited_source: str | None
    supported: bool


def citation_correctness(checks: Iterable[CitationCheck]) -> float:
    """Of the claims that cite a source, the fraction whose source supports the claim.

    Returns 1.0 when there are no cited claims (vacuously correct). Regressions in
    this metric are a hard blocker at the Prompt 17 gate.
    """

    cited = [c for c in checks if c.cited_source]
    if not cited:
        return 1.0
    return sum(1 for c in cited if c.supported) / len(cited)


@dataclass(frozen=True)
class ClaimCheck:
    """An asserted claim and whether it is supported by a source (citation or engine)."""

    claim: str
    supported: bool


def hallucination_rate(checks: Iterable[ClaimCheck]) -> float:
    """Fraction of asserted claims that are not supported by any source (target → 0)."""

    materialized = list(checks)
    if not materialized:
        return 0.0
    return sum(1 for c in materialized if not c.supported) / len(materialized)


# --------------------------------------------------------------------------- #
# 6. Narrative-acceptance rate + edit distance to the final approved text
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class NarrativeReview:
    """A generated draft narrative and the reviewer's final approved text."""

    draft: str
    final: str
    accepted_without_edit: bool | None = None

    def was_accepted(self) -> bool:
        if self.accepted_without_edit is not None:
            return bool(self.accepted_without_edit)
        return self.draft == self.final


def narrative_acceptance_rate(reviews: Iterable[NarrativeReview]) -> float:
    """Fraction of generated narratives accepted by the reviewer without edits."""

    materialized = list(reviews)
    if not materialized:
        return 0.0
    return sum(1 for r in materialized if r.was_accepted()) / len(materialized)


def levenshtein(a: str, b: str) -> int:
    """Levenshtein edit distance between two strings (pure-Python DP, two rows)."""

    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def normalized_edit_distance(a: str, b: str) -> float:
    """Levenshtein distance normalised by the longer string length (0 = identical)."""

    longest = max(len(a), len(b))
    return levenshtein(a, b) / longest if longest else 0.0


def mean_edit_distance(reviews: Iterable[NarrativeReview], *, normalized: bool = True) -> float:
    """Mean edit distance from generated draft to final approved text (lower is better)."""

    materialized = list(reviews)
    if not materialized:
        return 0.0
    fn = normalized_edit_distance if normalized else (lambda a, b: float(levenshtein(a, b)))
    return sum(fn(r.draft, r.final) for r in materialized) / len(materialized)


# --------------------------------------------------------------------------- #
# 7. needs-review precision (does the flag fire when it should?)
# --------------------------------------------------------------------------- #
def needs_review_precision(
    flagged: Sequence[bool], should_flag: Sequence[bool]
) -> PRF:
    """Precision / recall / F1 of the ``needs_review`` flag vs ground truth.

    A high recall matters most (a case that should be reviewed but is not flagged
    is a missed safeguard); precision keeps the human-review queue meaningful.
    """

    if len(flagged) != len(should_flag):
        raise RegulatoryEvalError("flagged and should_flag must be the same length")
    pairs = list(zip(flagged, should_flag, strict=True))
    tp = sum(1 for f, s in pairs if f and s)
    fp = sum(1 for f, s in pairs if f and not s)
    fn = sum(1 for f, s in pairs if not f and s)
    return f1_score(tp, fp, fn)


# --------------------------------------------------------------------------- #
# The metric vector + the hard-gate enforcer
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RegulatoryMetricVector:
    """The per-version regulatory metric vector — the acceptance evidence.

    Fields are optional so a run reports only what it measured. The two hard-gate
    fields (``calculation_error_rate`` must be 0, ``formula_coverage`` must be 1.0)
    are enforced by :func:`enforce_hard_gates`; the Prompt 17 dominance gate
    compares the remaining quality metrics across versions.
    """

    formula_coverage: float | None = None
    calculation_error_rate: float | None = None
    classification_accuracy: float | None = None
    citation_correctness: float | None = None
    hallucination_rate: float | None = None
    narrative_acceptance_rate: float | None = None
    mean_edit_distance: float | None = None
    needs_review_precision: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def metric_items(self) -> dict[str, float]:
        """The numeric metrics only (drops ``None`` and the metadata)."""

        out: dict[str, float] = {}
        for name in (
            "formula_coverage",
            "calculation_error_rate",
            "classification_accuracy",
            "citation_correctness",
            "hallucination_rate",
            "narrative_acceptance_rate",
            "mean_edit_distance",
            "needs_review_precision",
            "latency_p50_ms",
            "latency_p95_ms",
        ):
            value = getattr(self, name)
            if value is not None:
                out[name] = float(value)
        return out

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = dict(self.metric_items())
        if self.metadata:
            out["metadata"] = dict(self.metadata)
        return out

    def content_hash(self) -> str:
        """Deterministic ``sha256:<hex>`` content address of the metric vector."""

        return content_hash(self.as_dict())

    @property
    def hard_gates_pass(self) -> bool:
        return self.calculation_error_rate == 0.0 and self.formula_coverage == 1.0


def enforce_hard_gates(vector: RegulatoryMetricVector) -> None:
    """Raise :class:`HardGateError` unless calc-error rate is 0 AND coverage is 100%.

    Both metrics must be present and satisfied — an unmeasured hard-gate metric
    fails loudly rather than passing silently.
    """

    if vector.calculation_error_rate is None or vector.formula_coverage is None:
        raise HardGateError(
            "hard-gate metrics not measured (calculation_error_rate and "
            "formula_coverage are both required)"
        )
    if vector.calculation_error_rate != 0.0:
        raise HardGateError(
            f"calculation-error rate must be 0, got {vector.calculation_error_rate}"
        )
    if vector.formula_coverage != 1.0:
        raise HardGateError(f"formula coverage must be 100%, got {vector.formula_coverage}")
