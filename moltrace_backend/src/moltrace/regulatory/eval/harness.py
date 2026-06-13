"""Zero-tolerance regulatory evaluation harness (Prompt 17, Roadmap — Ten Metrics).

A new version ships only if its metric vector **dominates** the incumbent on a **frozen,
checksummed gold set** AND it has **zero calculation errors** and **100% formula coverage**, with
**no citation-correctness regression**. Calculation errors and citation regressions are hard
blockers regardless of any other gains — the bar a pharma QA group expects on regulated math and
citation integrity.

* :func:`evaluate` runs the per-version measurements over a gold-set bundle into a
  :class:`~moltrace.regulatory.infra.eval.RegulatoryMetricVector` (refusing to run on gold-set
  checksum drift), and
* :func:`gate` compares a candidate vector to the incumbent and returns ``(passed, deltas)`` —
  the objective, reproducible, per-version acceptance evidence the GAMP 5 CSV package (Prompt 18)
  consumes directly. :func:`promotion_exit_code` maps that to a CI exit code (0 promotable, 1 not).

The measurement primitives (the eight metrics + the two hard-gate enforcers) live in
:mod:`moltrace.regulatory.infra.eval`; this module is the orchestration + gold-set + dominance
layer on top of them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from moltrace.regulatory.infra.eval import (
    CalculationCheck,
    CitationCheck,
    ClaimCheck,
    NarrativeReview,
    RegulatoryEvalError,
    RegulatoryMetricVector,
    calculation_error_rate,
    citation_correctness,
    classification_accuracy,
    formula_coverage,
    hallucination_rate,
    mean_edit_distance,
    narrative_acceptance_rate,
    needs_review_precision,
)
from moltrace.regulatory.infra.versioning import gold_set_version

__all__ = [
    "HIGHER_IS_BETTER",
    "LOWER_IS_BETTER",
    "EvaluationBundle",
    "GoldSet",
    "GoldSetChecksumError",
    "MetricDelta",
    "evaluate",
    "gate",
    "promotion_exit_code",
    "validation_record",
]

#: Quality metrics where a larger value is better.
HIGHER_IS_BETTER: frozenset[str] = frozenset(
    {
        "formula_coverage",
        "classification_accuracy",
        "citation_correctness",
        "narrative_acceptance_rate",
        "needs_review_precision",
    }
)
#: Metrics where a smaller value is better.
LOWER_IS_BETTER: frozenset[str] = frozenset(
    {
        "calculation_error_rate",
        "hallucination_rate",
        "mean_edit_distance",
        "latency_p50_ms",
        "latency_p95_ms",
    }
)

_EPS = 1e-12


class GoldSetChecksumError(RegulatoryEvalError):
    """Raised when a gold set's content no longer matches its frozen checksum."""


# --------------------------------------------------------------------------- #
# Frozen, checksummed gold set
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GoldSet:
    """A frozen evaluation gold set, pinned by SHA-256 of its manifest.

    The real gold set is the 50 historical anonymised CTD reports + the FDA Nitrosamine (NDSRI)
    database; this is the mechanism that stores the manifest + checksum and **refuses to run on
    checksum drift** (:meth:`verify`), so an evaluation can never silently use a mutated corpus.
    """

    name: str
    manifest: Mapping[str, Any]
    checksum: str

    @classmethod
    def freeze(cls, name: str, manifest: Mapping[str, Any]) -> GoldSet:
        """Freeze ``manifest`` under its content checksum."""

        return cls(name=name, manifest=dict(manifest), checksum=gold_set_version(manifest))

    def verify(self) -> None:
        """Raise :class:`GoldSetChecksumError` if the manifest no longer matches the checksum."""

        actual = gold_set_version(self.manifest)
        if actual != self.checksum:
            raise GoldSetChecksumError(
                f"gold set {self.name!r} checksum drift: {actual} != frozen {self.checksum}; "
                "refusing to evaluate on a mutated gold set"
            )


# --------------------------------------------------------------------------- #
# The evaluation bundle (one version's results over the gold set)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EvaluationBundle:
    """One version's measured results over a gold set, ready for :func:`evaluate`.

    Each field is the raw material for one metric; only the fields actually populated are reported
    (an unmeasured *quality* metric stays ``None``). ``calculation_checks`` and the formula sets
    drive the two hard gates and should always be present for a regulated promotion decision.
    """

    gold_set: GoldSet
    required_formulas: Sequence[str] = ()
    implemented_formulas: Sequence[str] = ()
    calculation_checks: Sequence[CalculationCheck] = ()
    predicted_classes: Sequence[Any] = ()
    expert_classes: Sequence[Any] = ()
    citation_checks: Sequence[CitationCheck] = ()
    claim_checks: Sequence[ClaimCheck] = ()
    narrative_reviews: Sequence[NarrativeReview] = ()
    needs_review_flagged: Sequence[bool] = ()
    needs_review_should_flag: Sequence[bool] = ()
    latencies_ms: Sequence[float] = ()
    versions: Mapping[str, Any] = field(default_factory=dict)


def _percentile(values: Sequence[float], pct: float) -> float | None:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (pct / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def evaluate(
    bundle: EvaluationBundle, *, timestamp: str | None = None
) -> RegulatoryMetricVector:
    """Compute the per-version regulatory metric vector from a gold-set bundle.

    Refuses to run on gold-set checksum drift. The two hard-gate metrics (calculation-error rate,
    formula coverage) are always computed; quality metrics are reported only when measured. The
    returned vector carries metadata (versions, gold checksum, timestamp) for the audit record.
    """

    bundle.gold_set.verify()  # refuse to run on a mutated gold set

    checks = list(bundle.calculation_checks)
    coverage = (
        formula_coverage(bundle.implemented_formulas, bundle.required_formulas)
        if bundle.required_formulas
        else 1.0
    )
    classification = (
        classification_accuracy(bundle.predicted_classes, bundle.expert_classes).accuracy
        if bundle.predicted_classes
        else None
    )
    citation = citation_correctness(bundle.citation_checks) if bundle.citation_checks else None
    hallucination = hallucination_rate(bundle.claim_checks) if bundle.claim_checks else None
    narrative = (
        narrative_acceptance_rate(bundle.narrative_reviews) if bundle.narrative_reviews else None
    )
    edit_distance = (
        mean_edit_distance(bundle.narrative_reviews) if bundle.narrative_reviews else None
    )
    review_precision = (
        needs_review_precision(
            bundle.needs_review_flagged, bundle.needs_review_should_flag
        ).precision
        if bundle.needs_review_flagged
        else None
    )

    return RegulatoryMetricVector(
        formula_coverage=coverage,
        calculation_error_rate=calculation_error_rate(checks),
        classification_accuracy=classification,
        citation_correctness=citation,
        hallucination_rate=hallucination,
        narrative_acceptance_rate=narrative,
        mean_edit_distance=edit_distance,
        needs_review_precision=review_precision,
        latency_p50_ms=_percentile(bundle.latencies_ms, 50.0) if bundle.latencies_ms else None,
        latency_p95_ms=_percentile(bundle.latencies_ms, 95.0) if bundle.latencies_ms else None,
        metadata={
            "versions": dict(bundle.versions),
            "gold_set": bundle.gold_set.name,
            "gold_checksum": bundle.gold_set.checksum,
            "timestamp": timestamp,
        },
    )


# --------------------------------------------------------------------------- #
# The dominance gate
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MetricDelta:
    """One metric's candidate-vs-incumbent comparison, in its better-is direction."""

    metric: str
    incumbent: float
    candidate: float
    delta: float  # candidate - incumbent (raw)
    higher_is_better: bool
    improved: bool
    blocks: bool  # blocks promotion: a regression, or an absolute hard-gate failure

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "incumbent": self.incumbent,
            "candidate": self.candidate,
            "delta": self.delta,
            "higher_is_better": self.higher_is_better,
            "improved": self.improved,
            "blocks": self.blocks,
        }


def _absolute_hard_gate_fail(metric: str, candidate: float) -> bool:
    """A metric that must hold an absolute value regardless of the incumbent."""

    if metric == "calculation_error_rate":
        return candidate != 0.0
    if metric == "formula_coverage":
        return candidate != 1.0
    return False


def gate(
    candidate: RegulatoryMetricVector, incumbent: RegulatoryMetricVector
) -> tuple[bool, list[MetricDelta]]:
    """Decide whether ``candidate`` is promotable over ``incumbent``.

    Promotable iff: calculation-error rate == 0 AND formula coverage == 100% AND no regression on
    citation correctness AND **dominance** on every comparable metric (>= on all in its
    better-is direction, strictly > on at least one). Calculation errors and citation regressions
    are hard blockers regardless of other gains. Returns ``(passed, deltas)`` — the per-metric
    comparison for the promotion + validation record.
    """

    cand = candidate.metric_items()
    inc = incumbent.metric_items()
    deltas: list[MetricDelta] = []
    regressions = 0
    improvements = 0

    for metric in sorted(set(cand) & set(inc)):
        higher = metric in HIGHER_IS_BETTER
        c = cand[metric]
        i = inc[metric]
        # progress in the metric's "better" direction (>0 = improvement)
        progress = (c - i) if higher else (i - c)
        improved = progress > _EPS
        regressed = progress < -_EPS
        blocks = regressed or _absolute_hard_gate_fail(metric, c)
        if regressed:
            regressions += 1
        if improved:
            improvements += 1
        deltas.append(
            MetricDelta(
                metric=metric,
                incumbent=i,
                candidate=c,
                delta=c - i,
                higher_is_better=higher,
                improved=improved,
                blocks=blocks,
            )
        )

    # Absolute hard gates must hold on the candidate even if the incumbent never measured them.
    hard_ok = cand.get("calculation_error_rate") == 0.0 and cand.get("formula_coverage") == 1.0
    dominates = regressions == 0 and improvements >= 1
    passed = hard_ok and not any(d.blocks for d in deltas) and dominates
    return passed, deltas


def validation_record(
    candidate: RegulatoryMetricVector, incumbent: RegulatoryMetricVector
) -> dict[str, Any]:
    """The GxP promotion/validation record (Prompt 18 consumes this directly)."""

    passed, deltas = gate(candidate, incumbent)
    return {
        "promotable": passed,
        "candidate": candidate.as_dict(),
        "incumbent": incumbent.as_dict(),
        "deltas": [d.as_dict() for d in deltas],
        "blockers": sorted(d.metric for d in deltas if d.blocks),
        "candidate_hash": candidate.content_hash(),
        "incumbent_hash": incumbent.content_hash(),
    }


def promotion_exit_code(
    candidate: RegulatoryMetricVector, incumbent: RegulatoryMetricVector
) -> int:
    """CI exit code: ``0`` if the candidate is promotable, ``1`` otherwise."""

    passed, _ = gate(candidate, incumbent)
    return 0 if passed else 1
