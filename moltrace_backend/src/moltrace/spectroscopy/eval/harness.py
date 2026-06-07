"""Evaluation harness: the ten metrics + dominance-based promotion (Prompt 17).

A model version is **not** better because one number improved. It is better only
when its *full* metric vector **dominates** the incumbent on a frozen, checksum-
locked gold set: no regression beyond tolerance on any metric, a strict
improvement on at least one, and — critically — **zero regression on the safety-
critical metrics** (false-confirmation rate, calibration). This prevents
metric-gaming and gives GxP validation (Prompt 12) exactly what it wants:
objective, reproducible, per-version acceptance criteria.

Pieces
------
* :class:`GoldSet` — 100 hand-validated spectra (60 NMRShiftDB2 + 20 HMDB +
  20 in-house) with a manifest and a SHA-256 over the records. :meth:`GoldSet.
  assert_integrity` aborts the run if the checksum drifts, so the holdout can
  never be silently contaminated.
* :func:`evaluate` — computes the ten metrics on the gold set and returns a
  :class:`GoldMetricVector` carrying the metrics + metadata (``model_versions``,
  gold-set checksum, timestamp). It reuses the Prompt 19 metric framework
  (:func:`moltrace.spectroscopy.infra.eval.expected_calibration_error`).
* :func:`dominates` — the promotion rule; returns ``(passed, per-metric deltas)``
  for the promotion record.
* :func:`gate_for_ci` — wraps evaluate + dominates against the production
  incumbent and returns a CI exit code (0 promotable / 1 not / 2 gold drift).
* :func:`persist_metric_vector` — persists the vector (with ``model_versions`` +
  checksum) as canonical JSON and, optionally, to the Prompt 19 run store.

The harness is model-agnostic: a model is any :class:`ModelBundle` (a
``model_versions`` map + ``predict(record) -> Prediction``), so it composes with
the Prompt 13 inference router without importing it.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from moltrace.spectroscopy.infra.contract import canonical_json, content_hash
from moltrace.spectroscopy.infra.eval import expected_calibration_error

__all__ = [
    "DEFAULT_TOLERANCES",
    "METRIC_DIRECTIONS",
    "SAFETY_CRITICAL",
    "CallableBundle",
    "GoldMetricVector",
    "GoldRecord",
    "GoldSet",
    "GoldSetChecksumError",
    "MetricDelta",
    "MetricDirection",
    "ModelBundle",
    "Prediction",
    "default_perturb",
    "dominates",
    "evaluate",
    "gate_for_ci",
    "persist_metric_vector",
]

_EPS = 1e-9


# --------------------------------------------------------------------------- #
# Metric directions, safety-critical set, default tolerances
# --------------------------------------------------------------------------- #
class MetricDirection(StrEnum):
    HIGHER_BETTER = "higher_better"
    LOWER_BETTER = "lower_better"


_HI = MetricDirection.HIGHER_BETTER
_LO = MetricDirection.LOWER_BETTER

# The comparable metric fields and which direction is "better".
METRIC_DIRECTIONS: dict[str, MetricDirection] = {
    "top1_accuracy": _HI,
    "top3_accuracy": _HI,
    "shift_mae_1h": _LO,
    "shift_mae_13c": _LO,
    "ece": _LO,
    "false_confirmation_rate": _LO,
    "recall_at_k": _HI,
    "uncertainty_auroc": _HI,
    "robustness": _HI,
    "reviewer_agreement_rate": _HI,
    "latency_p50_ms": _LO,
    "latency_p95_ms": _LO,
}

# Safety-critical metrics may NOT regress at all (tolerance 0): passing a wrong
# structure, or mis-calibrated confidence, is never an acceptable trade.
SAFETY_CRITICAL: frozenset[str] = frozenset({"false_confirmation_rate", "ece"})

# Default per-metric tolerances (how much regression counts as "noise, not a
# real regression"). Safety-critical metrics are pinned to 0.
DEFAULT_TOLERANCES: dict[str, float] = {
    "top1_accuracy": 0.005,
    "top3_accuracy": 0.005,
    "shift_mae_1h": 0.02,
    "shift_mae_13c": 0.10,
    "ece": 0.0,
    "false_confirmation_rate": 0.0,
    "recall_at_k": 0.005,
    "uncertainty_auroc": 0.01,
    "robustness": 0.01,
    "reviewer_agreement_rate": 0.005,
    "latency_p50_ms": 10.0,
    "latency_p95_ms": 25.0,
}


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class GoldSetChecksumError(RuntimeError):
    """Raised when the gold-set checksum drifts from its pinned manifest value."""


# --------------------------------------------------------------------------- #
# Gold set
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GoldRecord:
    """One hand-validated gold item: the truth a model is scored against."""

    identifier: str
    source: str  # "nmrshiftdb2" | "hmdb" | "in_house"
    true_inchikey: str
    reference_shifts: Mapping[str, Sequence[float]]  # {"1H": [...], "13C": [...]}
    reviewer_verdict: bool  # expert adjudication: is the proposed structure correct?
    proposed_inchikey: str | None = None  # the structure being verified
    spectrum: Mapping[str, Any] | None = None  # input the model sees (for perturbation)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def _content(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "source": self.source,
            "true_inchikey": self.true_inchikey,
            "proposed_inchikey": self.proposed_inchikey,
            "reviewer_verdict": self.reviewer_verdict,
            "reference_shifts": {k: list(v) for k, v in sorted(self.reference_shifts.items())},
            "spectrum": self.spectrum,
        }


@dataclass(frozen=True)
class GoldSet:
    """A frozen, checksummed gold set. ``expected_checksum`` pins the manifest;
    :meth:`assert_integrity` aborts the run if the live checksum drifts."""

    name: str
    records: tuple[GoldRecord, ...]
    expected_checksum: str | None = None
    expected_size: int | None = None

    def checksum(self) -> str:
        ordered = sorted((r._content() for r in self.records), key=lambda c: c["identifier"])
        return content_hash({"name": self.name, "records": ordered})

    def composition(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for rec in self.records:
            counts[rec.source] = counts.get(rec.source, 0) + 1
        return dict(sorted(counts.items()))

    def assert_integrity(self) -> str:
        """Verify size + checksum; raise :class:`GoldSetChecksumError` on drift."""

        actual = self.checksum()
        if self.expected_size is not None and len(self.records) != self.expected_size:
            raise GoldSetChecksumError(
                f"gold set {self.name!r}: size {len(self.records)} != pinned "
                f"{self.expected_size} — the holdout composition changed"
            )
        if self.expected_checksum is not None and actual != self.expected_checksum:
            raise GoldSetChecksumError(
                f"gold set {self.name!r}: checksum {actual} != pinned "
                f"{self.expected_checksum} — the holdout may be contaminated; refusing to run"
            )
        return actual


# --------------------------------------------------------------------------- #
# Model interface
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Prediction:
    """One model output for a gold record."""

    ranked_candidates: tuple[str, ...]  # InChIKeys, best-first
    predicted_shifts: Mapping[str, Sequence[float]]  # {"1H": [...], "13C": [...]}
    confidence: float  # 0..1, for ECE (calibration of the top-1 call)
    confirmed: bool  # did the model confirm the proposed structure?
    retrieved: tuple[str, ...] = ()  # retrieved InChIKeys, for recall@k
    uncertainty: float = 0.0  # higher = less certain (for error-vs-uncertainty AUROC)
    latency_ms: float | None = None  # measured if None


@runtime_checkable
class ModelBundle(Protocol):
    """A model under evaluation: a provenance map + a per-record predictor."""

    model_versions: Mapping[str, str]

    def predict(self, record: GoldRecord) -> Prediction: ...


@dataclass
class CallableBundle:
    """Wrap a ``predict`` callable + a ``model_versions`` map as a ModelBundle."""

    predict_fn: Callable[[GoldRecord], Prediction]
    model_versions: Mapping[str, str] = field(default_factory=dict)

    def predict(self, record: GoldRecord) -> Prediction:
        return self.predict_fn(record)


# --------------------------------------------------------------------------- #
# Metric vector
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GoldMetricVector:
    """The ten metrics on the gold set + the metadata that makes them auditable."""

    top1_accuracy: float
    top3_accuracy: float
    shift_mae_1h: float
    shift_mae_13c: float
    ece: float
    false_confirmation_rate: float
    recall_at_k: float
    uncertainty_auroc: float
    robustness: float
    reviewer_agreement_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    # metadata
    model_versions: Mapping[str, str] = field(default_factory=dict)
    gold_checksum: str = ""
    gold_name: str = ""
    n_records: int = 0
    k: int = 5
    timestamp: str | None = None

    def metric_items(self) -> dict[str, float]:
        """The comparable metric fields only (the keys of METRIC_DIRECTIONS)."""

        return {name: float(getattr(self, name)) for name in METRIC_DIRECTIONS}

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = self.metric_items()
        out.update(
            {
                "model_versions": dict(sorted(self.model_versions.items())),
                "gold_checksum": self.gold_checksum,
                "gold_name": self.gold_name,
                "n_records": self.n_records,
                "k": self.k,
                "timestamp": self.timestamp,
            }
        )
        return out


# --------------------------------------------------------------------------- #
# Numeric helpers
# --------------------------------------------------------------------------- #
def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    idx = (pct / 100.0) * (len(ordered) - 1)
    lo = int(math.floor(idx))
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return float(ordered[lo] * (1.0 - frac) + ordered[hi] * frac)


def _auroc(scores: Sequence[float], labels: Sequence[bool]) -> float:
    """AUROC that ``scores`` (uncertainty) ranks ``labels`` (is-error) — tie-aware.

    Returns 0.5 when one class is absent (the metric is undefined / non-informative).
    """

    n = len(scores)
    n_pos = sum(1 for v in labels if v)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    order = sorted(range(n), key=lambda i: scores[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-based, averaged over ties
        for m in range(i, j + 1):
            ranks[order[m]] = avg_rank
        i = j + 1
    sum_pos = sum(ranks[i] for i in range(n) if labels[i])
    return (sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def default_perturb(record: GoldRecord) -> GoldRecord:
    """A deterministic noise / line-broadening perturbation of a record's input.

    Shifts the input ppm axis by a small fixed amount and marks the record so a
    model (or a test stub) can react. The reference truth is left untouched.
    """

    spectrum = record.spectrum
    if spectrum is not None and spectrum.get("ppm") is not None:
        spectrum = dict(spectrum)
        spectrum["ppm"] = [round(float(p) + 0.01, 6) for p in spectrum["ppm"]]
    return replace(record, spectrum=spectrum, extra={**dict(record.extra), "perturbed": True})


# --------------------------------------------------------------------------- #
# evaluate
# --------------------------------------------------------------------------- #
def evaluate(
    bundle: ModelBundle,
    gold_set: GoldSet,
    *,
    k: int = 5,
    perturb: Callable[[GoldRecord], GoldRecord] = default_perturb,
    n_ece_bins: int = 10,
    timestamp: str | None = None,
) -> GoldMetricVector:
    """Compute the ten metrics for ``bundle`` on ``gold_set``.

    Aborts with :class:`GoldSetChecksumError` if the gold-set checksum has drifted
    (the holdout can never be silently contaminated).
    """

    checksum = gold_set.assert_integrity()
    records = gold_set.records
    n = len(records)
    if n == 0:
        raise ValueError("gold set is empty")

    top1_hits = 0
    top3_hits = 0
    abs_err_1h: list[float] = []
    abs_err_13c: list[float] = []
    confidences: list[float] = []
    correct: list[bool] = []
    uncertainties: list[float] = []
    is_error: list[bool] = []
    wrong_total = 0
    false_confirms = 0
    recall_hits = 0
    reviewer_match = 0
    robust_match = 0
    latencies: list[float] = []

    for rec in records:
        t0 = time.perf_counter()
        pred = bundle.predict(rec)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(pred.latency_ms if pred.latency_ms is not None else elapsed_ms)

        top1 = bool(pred.ranked_candidates) and pred.ranked_candidates[0] == rec.true_inchikey
        top1_hits += int(top1)
        top3_hits += int(rec.true_inchikey in pred.ranked_candidates[:3])

        for nucleus, bucket in (("1H", abs_err_1h), ("13C", abs_err_13c)):
            ref = rec.reference_shifts.get(nucleus) or []
            prd = pred.predicted_shifts.get(nucleus) or []
            for a, b in zip(prd, ref, strict=False):
                bucket.append(abs(float(a) - float(b)))

        confidences.append(float(pred.confidence))
        correct.append(top1)
        uncertainties.append(float(pred.uncertainty))
        is_error.append(not top1)

        if not rec.reviewer_verdict:  # the proposed structure is actually wrong
            wrong_total += 1
            if pred.confirmed:
                false_confirms += 1  # passed a wrong structure -- the critical error

        if rec.true_inchikey in pred.retrieved[:k]:
            recall_hits += 1
        if pred.confirmed == rec.reviewer_verdict:
            reviewer_match += 1

        perturbed = bundle.predict(perturb(rec))
        if (
            pred.ranked_candidates
            and perturbed.ranked_candidates
            and pred.ranked_candidates[0] == perturbed.ranked_candidates[0]
        ):
            robust_match += 1

    ece = (
        expected_calibration_error(confidences, correct, n_bins=n_ece_bins) if confidences else 0.0
    )
    return GoldMetricVector(
        top1_accuracy=top1_hits / n,
        top3_accuracy=top3_hits / n,
        shift_mae_1h=_mean(abs_err_1h),
        shift_mae_13c=_mean(abs_err_13c),
        ece=float(ece),
        false_confirmation_rate=(false_confirms / wrong_total) if wrong_total else 0.0,
        recall_at_k=recall_hits / n,
        uncertainty_auroc=_auroc(uncertainties, is_error),
        robustness=robust_match / n,
        reviewer_agreement_rate=reviewer_match / n,
        latency_p50_ms=_percentile(latencies, 50.0),
        latency_p95_ms=_percentile(latencies, 95.0),
        model_versions=dict(bundle.model_versions),
        gold_checksum=checksum,
        gold_name=gold_set.name,
        n_records=n,
        k=k,
        timestamp=timestamp if timestamp is not None else datetime.now(UTC).isoformat(),
    )


# --------------------------------------------------------------------------- #
# dominance
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MetricDelta:
    metric: str
    candidate: float
    incumbent: float
    delta: float  # raw candidate - incumbent
    improvement: float  # signed so positive = better (direction-aware)
    direction: MetricDirection
    tolerance: float
    regressed: bool  # worse than incumbent by more than tolerance
    improved: bool  # strictly better than incumbent
    safety_critical: bool


def dominates(
    candidate: GoldMetricVector,
    incumbent: GoldMetricVector,
    tolerances: Mapping[str, float] | None = None,
) -> tuple[bool, list[MetricDelta]]:
    """Promotion rule: candidate dominates incumbent.

    Promotable iff candidate is >= incumbent within tolerance on **every** metric,
    strictly better on **at least one**, and with **no** regression beyond
    tolerance on the safety-critical metrics (which default to tolerance 0).
    Returns ``(passed, deltas)`` — ``deltas`` is the per-metric promotion record.
    """

    tol_map = {**DEFAULT_TOLERANCES, **(dict(tolerances) if tolerances else {})}
    cand = candidate.metric_items()
    inc = incumbent.metric_items()

    deltas: list[MetricDelta] = []
    any_regressed = False
    any_improved = False
    for name, direction in METRIC_DIRECTIONS.items():
        if name not in cand or name not in inc:
            continue
        is_safety = name in SAFETY_CRITICAL
        tol = 0.0 if is_safety else float(tol_map.get(name, 0.0))
        c = cand[name]
        i = inc[name]
        raw = c - i
        improvement = raw if direction is _HI else -raw
        regressed = improvement < -tol
        improved = improvement > _EPS
        any_regressed = any_regressed or regressed
        any_improved = any_improved or improved
        deltas.append(
            MetricDelta(
                metric=name,
                candidate=c,
                incumbent=i,
                delta=raw,
                improvement=improvement,
                direction=direction,
                tolerance=tol,
                regressed=regressed,
                improved=improved,
                safety_critical=is_safety,
            )
        )

    passed = (not any_regressed) and any_improved
    return passed, deltas


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def persist_metric_vector(
    report: GoldMetricVector,
    *,
    path: str | Path | None = None,
    tracker: Any = None,
    run_name: str = "gold-eval",
) -> str:
    """Persist the metric vector (with ``model_versions`` + gold checksum).

    Writes canonical JSON to ``path`` when given, and logs to a Prompt 19
    :class:`~moltrace.spectroscopy.infra.tracking.ExperimentTracker` when given.
    Returns the content hash of the serialised vector.
    """

    payload = report.as_dict()
    serialised = canonical_json(payload)
    if path is not None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialised, encoding="utf-8")
    if tracker is not None:
        params = {"gold_name": report.gold_name, "k": report.k}
        with tracker.start_run(run_name, params=params) as run:
            run.log_metrics(report.metric_items())
            run.set_dataset_version(report.gold_checksum)
    return content_hash(payload)


# --------------------------------------------------------------------------- #
# CI gate (Prompt 18 consumes this)
# --------------------------------------------------------------------------- #
def gate_for_ci(
    candidate_bundle: ModelBundle,
    *,
    gold_set: GoldSet,
    incumbent_metrics: GoldMetricVector | None = None,
    incumbent_bundle: ModelBundle | None = None,
    tolerances: Mapping[str, float] | None = None,
    k: int = 5,
    persist_path: str | Path | None = None,
    tracker: Any = None,
) -> int:
    """Evaluate the candidate against the production incumbent; return a CI exit code.

    ``0`` = promotable (dominates the incumbent, or there is no incumbent),
    ``1`` = not promotable (regression or no strict improvement),
    ``2`` = gold-set checksum drift / evaluation error (hard abort).

    The incumbent's metrics are supplied directly (``incumbent_metrics``) or
    re-derived from ``incumbent_bundle`` on the same gold set; Prompt 18 wires the
    current production model from the registry.
    """

    try:
        candidate = evaluate(candidate_bundle, gold_set, k=k)
        incumbent = incumbent_metrics
        if incumbent is None and incumbent_bundle is not None:
            incumbent = evaluate(incumbent_bundle, gold_set, k=k)
    except GoldSetChecksumError:
        return 2

    if persist_path is not None or tracker is not None:
        persist_metric_vector(candidate, path=persist_path, tracker=tracker)

    if incumbent is None:
        return 0  # no incumbent to dominate -> first model is promotable

    passed, _deltas = dominates(candidate, incumbent, tolerances)
    return 0 if passed else 1
