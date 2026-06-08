"""Production monitoring, drift detection, and the fail-closed deployment gate (Prompt 18).

Pharma-grade observability and release control from day one: nothing reaches
production without passing evaluation, audit, and validation. This module is the
MLOps layer over the rest of the stack — it *reads* the registry (Prompt 13), the
evaluation gold gate (Prompt 17), the audit chain (Prompt 12), the closed-loop
feedback (Prompt 16), and the per-prediction uncertainty (Prompt 6) / RAG
grounding (Prompt 14), and turns them into drift metrics, a lineage dashboard, and
a deployment gate that fails closed.

Three faces:

* **Drift monitors** (:func:`production_monitors`) — input drift (population
  stability index of nucleus / field / solvent / molecular weight vs the training
  snapshot), confidence drift (the trend of per-prediction uncertainty and RAG
  grounding), override-rate drift (the Prompt 16 reviewer override trend — a rising
  trend means the model is degrading on live data), and latency (p50 / p95 vs an
  SLO). Each yields a :class:`DriftMetric` with an ``ok`` / ``warn`` / ``breach``
  status; the report emits to an injectable observability sink and pages an
  injectable alerter on any breach.
* **Lineage dashboard** (:func:`lineage_dashboard`) — per production model, its
  version, training-snapshot hash, gold-set metric vector (Prompt 17), promotion
  record, and current live drift status, read straight from the Prompt 13 registry.
* **Deployment gate** (:func:`run_deployment_gate` / :func:`evaluate_deployment_gate`)
  — a model or pipeline change is allowed to production **only if all four** pass:
  (1) the Prompt 17 dominance gate (no regression on safety metrics), (2) the
  Prompt 12 audit chain verifies (provenance intact), (3) the test suite is green,
  and (4) the data-leakage check (the candidate never trained on the gold set).
  Any failure — or any missing input — blocks the deploy. It fails **closed**.

Like the rest of the AI/ops layer, the observability sink, the alerter, and every
data input are injected, so the math and the gate logic are pure-Python and
unit-testable on a CPU-only host with no live infrastructure.
"""

from __future__ import annotations

import bisect
import math
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from moltrace.spectroscopy.ai.active_learning import loop_yield_metrics
from moltrace.spectroscopy.ai.registry import ModelRegistry, ModelStatus
from moltrace.spectroscopy.audit.trail import verify_chain
from moltrace.spectroscopy.eval.harness import GoldMetricVector, dominates

__all__ = [
    "DEFAULT_CONFIDENCE_TREND_BREACH",
    "DEFAULT_CONFIDENCE_TREND_WARN",
    "DEFAULT_OVERRIDE_TREND_BREACH",
    "DEFAULT_OVERRIDE_TREND_WARN",
    "DEFAULT_SLO_P50_MS",
    "DEFAULT_SLO_P95_MS",
    "DEFAULT_WINDOW_DAYS",
    "PSI_BREACH_THRESHOLD",
    "PSI_WARN_THRESHOLD",
    "ConfidenceSample",
    "DriftMetric",
    "GateCheck",
    "GateDecision",
    "LineageDashboard",
    "LineageRow",
    "MonitorStatus",
    "MonitoringError",
    "MonitoringReport",
    "check_audit_chain",
    "check_data_leakage",
    "check_dominance",
    "confidence_drift",
    "evaluate_deployment_gate",
    "input_drift",
    "latency_drift",
    "lineage_dashboard",
    "numeric_psi",
    "override_rate_drift",
    "percentile",
    "population_stability_index",
    "production_monitors",
    "run_deployment_gate",
    "snapshot_distributions",
]

# Population Stability Index bands (Karst / industry convention): < 0.1 stable,
# 0.1–0.25 a moderate shift worth watching, >= 0.25 a significant shift — new
# chemistry the model has not seen — that pages.
PSI_WARN_THRESHOLD = 0.1
PSI_BREACH_THRESHOLD = 0.25
# Confidence drift: a rise in mean per-prediction uncertainty (or an equal fall in
# RAG grounding) between consecutive windows, in absolute [0, 1] units.
DEFAULT_CONFIDENCE_TREND_WARN = 0.05
DEFAULT_CONFIDENCE_TREND_BREACH = 0.10
# Override-rate drift: a rise in the reviewer override rate between windows.
DEFAULT_OVERRIDE_TREND_WARN = 0.05
DEFAULT_OVERRIDE_TREND_BREACH = 0.10
# Latency SLO (ms). p95 over the SLO breaches; p50 over half the SLO warns.
DEFAULT_SLO_P95_MS = 2000.0
DEFAULT_SLO_P50_MS = 800.0
# Trailing window for trend-based monitors (≈ one month).
DEFAULT_WINDOW_DAYS = 30


class MonitoringError(RuntimeError):
    """Raised when a monitor or the deployment gate is given inconsistent inputs."""


class MonitorStatus(StrEnum):
    """The traffic-light status of a single drift metric (or the whole report)."""

    OK = "ok"
    WARN = "warn"
    BREACH = "breach"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _worst(statuses: Iterable[MonitorStatus]) -> MonitorStatus:
    order = {MonitorStatus.OK: 0, MonitorStatus.WARN: 1, MonitorStatus.BREACH: 2}
    worst = MonitorStatus.OK
    for status in statuses:
        if order[status] > order[worst]:
            worst = status
    return worst


def _status_for(value: float, warn: float, breach: float) -> MonitorStatus:
    """Status for a metric where larger == worse (the usual drift convention)."""

    if value >= breach:
        return MonitorStatus.BREACH
    if value >= warn:
        return MonitorStatus.WARN
    return MonitorStatus.OK


# --------------------------------------------------------------------------- #
# Drift metric record
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DriftMetric:
    """One monitored quantity with its value, status, and alerting thresholds."""

    name: str
    value: float
    status: MonitorStatus
    threshold_warn: float
    threshold_breach: float
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "status": self.status.value,
            "threshold_warn": self.threshold_warn,
            "threshold_breach": self.threshold_breach,
            "detail": self.detail,
        }


# --------------------------------------------------------------------------- #
# Population Stability Index (input drift)
# --------------------------------------------------------------------------- #
def population_stability_index(
    expected: Mapping[str, float],
    actual: Mapping[str, float],
    *,
    epsilon: float = 1e-6,
) -> float:
    """PSI between two **categorical** count distributions (e.g. nucleus, solvent).

    ``PSI = Σ (a_i - e_i) · ln(a_i / e_i)`` over the union of categories, where
    ``e_i`` / ``a_i`` are the expected (training-snapshot) and actual (live)
    proportions. Zero / missing categories are floored to ``epsilon`` so a category
    the model never trained on (new chemistry) contributes a large, finite term
    rather than diverging. Returns ``0.0`` when either side is empty.
    """

    categories = set(expected) | set(actual)
    expected_total = sum(float(v) for v in expected.values())
    actual_total = sum(float(v) for v in actual.values())
    if expected_total <= 0 or actual_total <= 0:
        return 0.0
    psi = 0.0
    for category in categories:
        e_prop = max(float(expected.get(category, 0.0)) / expected_total, epsilon)
        a_prop = max(float(actual.get(category, 0.0)) / actual_total, epsilon)
        psi += (a_prop - e_prop) * math.log(a_prop / e_prop)
    return float(psi)


def numeric_psi(
    expected_values: Sequence[float],
    actual_values: Sequence[float],
    *,
    bins: int = 10,
    epsilon: float = 1e-6,
) -> float:
    """PSI between two **continuous** samples (e.g. molecular weight) via quantile bins.

    Bin edges are the ``bins``-quantiles of the *expected* sample, so each expected
    bin holds ~equal mass; the actual sample is counted into the same edges. Returns
    ``0.0`` when there is too little data to bin.
    """

    expected = sorted(float(v) for v in expected_values)
    actual = [float(v) for v in actual_values]
    if len(expected) < 2 or not actual or bins < 2:
        return 0.0
    try:
        cuts = statistics.quantiles(expected, n=bins)
    except statistics.StatisticsError:  # pragma: no cover - guarded by len check
        return 0.0
    expected_counts = [0] * bins
    actual_counts = [0] * bins
    for value in expected:
        expected_counts[bisect.bisect_right(cuts, value)] += 1
    for value in actual:
        actual_counts[bisect.bisect_right(cuts, value)] += 1
    expected_total = sum(expected_counts)
    actual_total = sum(actual_counts)
    psi = 0.0
    for e_count, a_count in zip(expected_counts, actual_counts, strict=True):
        e_prop = max(e_count / expected_total, epsilon)
        a_prop = max(a_count / actual_total, epsilon)
        psi += (a_prop - e_prop) * math.log(a_prop / e_prop)
    return float(psi)


def snapshot_distributions(snapshot: Any) -> dict[str, dict[str, float]]:
    """Extract the categorical training distributions from a Prompt 15 ``Snapshot``.

    Returns ``{dimension: {category: count}}`` for the dimensions a snapshot
    carries (nucleus, field, solvent), duck-typed so any object exposing the
    ``*_distribution`` mappings works.
    """

    out: dict[str, dict[str, float]] = {}
    for dimension, attr in (
        ("nucleus", "nucleus_distribution"),
        ("field", "field_distribution"),
        ("solvent", "solvent_distribution"),
    ):
        dist = getattr(snapshot, attr, None)
        if isinstance(dist, Mapping):
            out[dimension] = {str(k): float(v) for k, v in dist.items()}
    return out


def input_drift(
    expected: Mapping[str, Mapping[str, float]],
    actual: Mapping[str, Mapping[str, float]],
    *,
    warn: float = PSI_WARN_THRESHOLD,
    breach: float = PSI_BREACH_THRESHOLD,
) -> list[DriftMetric]:
    """Per-dimension input drift (PSI) of live data vs the training distribution.

    ``expected`` / ``actual`` are ``{dimension: {category: count}}`` (use
    :func:`snapshot_distributions` to derive ``expected`` from a training
    snapshot). Only dimensions present in ``expected`` are scored.
    """

    metrics: list[DriftMetric] = []
    for dimension, expected_counts in expected.items():
        actual_counts = actual.get(dimension, {})
        psi = population_stability_index(expected_counts, actual_counts)
        metrics.append(
            DriftMetric(
                name=f"input_drift.{dimension}",
                value=psi,
                status=_status_for(psi, warn, breach),
                threshold_warn=warn,
                threshold_breach=breach,
                detail=f"PSI of live {dimension} distribution vs training snapshot",
            )
        )
    return metrics


# --------------------------------------------------------------------------- #
# Confidence drift (uncertainty + RAG grounding)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ConfidenceSample:
    """One observed prediction's confidence signals at a point in time.

    ``uncertainty`` is the Prompt 6 per-prediction uncertainty (higher == less
    certain); ``grounding`` is the optional Prompt 14 RAG grounding score in
    ``[0, 1]`` (higher == better grounded).
    """

    created_utc: str
    uncertainty: float
    grounding: float | None = None


def _window_split(
    items: Sequence[Any],
    *,
    now: datetime,
    window_days: int,
    timestamp_of: Callable[[Any], Any],
) -> tuple[list[Any], list[Any]]:
    """Partition ``items`` into the trailing window and the window before it."""

    recent_start = now.timestamp() - window_days * 86400.0
    prior_start = now.timestamp() - 2 * window_days * 86400.0
    recent: list[Any] = []
    prior: list[Any] = []
    for item in items:
        dt = _parse_iso(timestamp_of(item))
        if dt is None:
            continue
        ts = dt.timestamp()
        if ts >= recent_start:
            recent.append(item)
        elif ts >= prior_start:
            prior.append(item)
    return recent, prior


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _grounding_values(samples: Sequence[Any]) -> list[float]:
    return [float(s.grounding) for s in samples if getattr(s, "grounding", None) is not None]


def confidence_drift(
    samples: Iterable[Any],
    *,
    now_utc: str | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    warn: float = DEFAULT_CONFIDENCE_TREND_WARN,
    breach: float = DEFAULT_CONFIDENCE_TREND_BREACH,
) -> list[DriftMetric]:
    """Drift in mean per-prediction uncertainty and RAG grounding between windows.

    A *rise* in mean uncertainty (the model is less sure on live data) or an equal
    *fall* in mean grounding both register as positive drift. Samples are duck-typed
    (``created_utc`` / ``uncertainty`` / optional ``grounding``); timestamps that do
    not parse are ignored. Returns one metric per signal that has data in both
    windows.
    """

    materialized = list(samples)
    now = _parse_iso(now_utc) or datetime.now(UTC)
    recent, prior = _window_split(
        materialized, now=now, window_days=window_days,
        timestamp_of=lambda s: getattr(s, "created_utc", None),
    )

    metrics: list[DriftMetric] = []

    recent_unc = _mean([float(getattr(s, "uncertainty", 0.0)) for s in recent])
    prior_unc = _mean([float(getattr(s, "uncertainty", 0.0)) for s in prior])
    if recent_unc is not None and prior_unc is not None:
        trend = recent_unc - prior_unc  # positive == less certain == worse
        metrics.append(
            DriftMetric(
                name="confidence_drift.uncertainty",
                value=trend,
                status=_status_for(trend, warn, breach),
                threshold_warn=warn,
                threshold_breach=breach,
                detail=f"mean uncertainty {prior_unc:.4f} -> {recent_unc:.4f} (rise == worse)",
            )
        )

    recent_g = _mean(_grounding_values(recent))
    prior_g = _mean(_grounding_values(prior))
    if recent_g is not None and prior_g is not None:
        trend = prior_g - recent_g  # positive == grounding fell == worse
        metrics.append(
            DriftMetric(
                name="confidence_drift.grounding",
                value=trend,
                status=_status_for(trend, warn, breach),
                threshold_warn=warn,
                threshold_breach=breach,
                detail=f"mean RAG grounding {prior_g:.4f} -> {recent_g:.4f} (fall == worse)",
            )
        )

    return metrics


# --------------------------------------------------------------------------- #
# Override-rate drift (reuses the Prompt 16 loop-yield trend)
# --------------------------------------------------------------------------- #
def override_rate_drift(
    feedback_events: Iterable[Any],
    *,
    now_utc: str | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    warn: float = DEFAULT_OVERRIDE_TREND_WARN,
    breach: float = DEFAULT_OVERRIDE_TREND_BREACH,
) -> DriftMetric | None:
    """Drift in the reviewer override rate — a rising trend means live degradation.

    Reuses the Prompt 16 :func:`~moltrace.spectroscopy.ai.active_learning.loop_yield_metrics`
    override-rate trend (recent window minus the prior window). Returns ``None``
    when the two windows do not both have feedback to compare.
    """

    metrics = loop_yield_metrics(feedback_events, now_utc=now_utc, window_days=window_days)
    if metrics.override_rate_trend is None:
        return None
    trend = metrics.override_rate_trend  # positive == overriding more == worse
    return DriftMetric(
        name="override_rate_drift",
        value=trend,
        status=_status_for(trend, warn, breach),
        threshold_warn=warn,
        threshold_breach=breach,
        detail=(
            f"override rate {metrics.override_rate_prior} -> {metrics.override_rate_recent} "
            "(rise == model degrading on live data)"
        ),
    )


# --------------------------------------------------------------------------- #
# Latency
# --------------------------------------------------------------------------- #
def percentile(values: Sequence[float], q: float) -> float:
    """The ``q``-th percentile (0–100) by linear interpolation; ``0.0`` if empty."""

    ordered = sorted(float(v) for v in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    rank = (q / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[int(rank)]
    frac = rank - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def latency_drift(
    latencies_ms: Sequence[float],
    *,
    slo_p95_ms: float = DEFAULT_SLO_P95_MS,
    slo_p50_ms: float = DEFAULT_SLO_P50_MS,
) -> list[DriftMetric]:
    """Latency p50 / p95 vs the SLO. p95 over the SLO breaches; p50 over its SLO warns."""

    if not latencies_ms:
        return []
    p50 = percentile(latencies_ms, 50)
    p95 = percentile(latencies_ms, 95)
    p95_status = MonitorStatus.BREACH if p95 > slo_p95_ms else MonitorStatus.OK
    p50_status = MonitorStatus.WARN if p50 > slo_p50_ms else MonitorStatus.OK
    return [
        DriftMetric(
            name="latency.p50_ms",
            value=p50,
            status=p50_status,
            threshold_warn=slo_p50_ms,
            threshold_breach=slo_p95_ms,
            detail=f"p50 {p50:.0f} ms vs SLO {slo_p50_ms:.0f} ms",
        ),
        DriftMetric(
            name="latency.p95_ms",
            value=p95,
            status=p95_status,
            threshold_warn=slo_p50_ms,
            threshold_breach=slo_p95_ms,
            detail=f"p95 {p95:.0f} ms vs SLO {slo_p95_ms:.0f} ms",
        ),
    ]


# --------------------------------------------------------------------------- #
# The monitoring report (aggregate + alert + emit)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MonitoringReport:
    """All drift metrics for one monitoring pass, with the worst status surfaced."""

    metrics: tuple[DriftMetric, ...]
    status: MonitorStatus
    breached: tuple[str, ...]
    warned: tuple[str, ...]
    generated_utc: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "breached": list(self.breached),
            "warned": list(self.warned),
            "generated_utc": self.generated_utc,
            "metrics": [m.as_dict() for m in self.metrics],
        }


def production_monitors(
    *,
    expected_distributions: Mapping[str, Mapping[str, float]] | None = None,
    live_distributions: Mapping[str, Mapping[str, float]] | None = None,
    numeric_distributions: Mapping[str, tuple[Sequence[float], Sequence[float]]] | None = None,
    confidence_samples: Iterable[Any] | None = None,
    feedback_events: Iterable[Any] | None = None,
    latencies_ms: Sequence[float] | None = None,
    slo_p95_ms: float = DEFAULT_SLO_P95_MS,
    slo_p50_ms: float = DEFAULT_SLO_P50_MS,
    now_utc: str | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    emit_fn: Callable[[str, Mapping[str, Any]], None] | None = None,
    alert_fn: Callable[[DriftMetric], None] | None = None,
    clock: Callable[[], str] = _now_iso,
) -> MonitoringReport:
    """Run every configured monitor, emit each metric, and page on any breach.

    Each monitor runs only when its inputs are supplied, so a caller can wire as
    much or as little as it has data for. ``emit_fn(name, payload)`` is called for
    every metric (the observability sink — e.g. an experiment tracker / metrics
    endpoint); ``alert_fn(metric)`` is called for every breaching metric (the
    pager). Both are optional no-ops by default, so the report is computable with
    no live infrastructure. Returns the aggregated :class:`MonitoringReport`.
    """

    metrics: list[DriftMetric] = []

    if expected_distributions is not None:
        metrics.extend(input_drift(expected_distributions, live_distributions or {}))
    if numeric_distributions:
        for name, (expected_values, actual_values) in numeric_distributions.items():
            psi = numeric_psi(expected_values, actual_values)
            metrics.append(
                DriftMetric(
                    name=f"input_drift.{name}",
                    value=psi,
                    status=_status_for(psi, PSI_WARN_THRESHOLD, PSI_BREACH_THRESHOLD),
                    threshold_warn=PSI_WARN_THRESHOLD,
                    threshold_breach=PSI_BREACH_THRESHOLD,
                    detail=f"numeric PSI of live {name} vs training snapshot",
                )
            )
    if confidence_samples is not None:
        metrics.extend(
            confidence_drift(confidence_samples, now_utc=now_utc, window_days=window_days)
        )
    if feedback_events is not None:
        override = override_rate_drift(
            feedback_events, now_utc=now_utc, window_days=window_days
        )
        if override is not None:
            metrics.append(override)
    if latencies_ms is not None:
        metrics.extend(
            latency_drift(latencies_ms, slo_p95_ms=slo_p95_ms, slo_p50_ms=slo_p50_ms)
        )

    breached = tuple(m.name for m in metrics if m.status is MonitorStatus.BREACH)
    warned = tuple(m.name for m in metrics if m.status is MonitorStatus.WARN)
    status = _worst(m.status for m in metrics) if metrics else MonitorStatus.OK

    if emit_fn is not None:
        for metric in metrics:
            emit_fn(metric.name, metric.as_dict())
    if alert_fn is not None:
        for metric in metrics:
            if metric.status is MonitorStatus.BREACH:
                alert_fn(metric)

    return MonitoringReport(
        metrics=tuple(metrics),
        status=status,
        breached=breached,
        warned=warned,
        generated_utc=clock(),
    )


# --------------------------------------------------------------------------- #
# Lineage dashboard (reads the Prompt 13 registry)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LineageRow:
    """One production model's lineage + live status, for the dashboard."""

    model_id: str
    role: str
    nucleus: str | None
    semantic_version: str
    artifact_sha256: str
    training_snapshot_hash: str
    metric_vector: Mapping[str, float]
    promoted_utc: str | None
    promotion_reason: str | None
    supersedes: str | None
    drift_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "role": self.role,
            "nucleus": self.nucleus,
            "semantic_version": self.semantic_version,
            "artifact_sha256": self.artifact_sha256,
            "training_snapshot_hash": self.training_snapshot_hash,
            "metric_vector": dict(sorted(self.metric_vector.items())),
            "promoted_utc": self.promoted_utc,
            "promotion_reason": self.promotion_reason,
            "supersedes": self.supersedes,
            "drift_status": self.drift_status,
        }


@dataclass(frozen=True)
class LineageDashboard:
    """The production-model lineage view returned by :func:`lineage_dashboard`."""

    rows: tuple[LineageRow, ...]
    generated_utc: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_utc": self.generated_utc,
            "rows": [r.as_dict() for r in self.rows],
        }


def lineage_dashboard(
    registry: ModelRegistry,
    *,
    drift_status: Mapping[str, str] | None = None,
    clock: Callable[[], str] = _now_iso,
) -> LineageDashboard:
    """Per production model: version, snapshot hash, metric vector, promotion, drift.

    Reads the Prompt 13 registry as the source of truth — every ``production``
    artifact, with its training-snapshot hash and gold metric snapshot (Prompt 17),
    the promotion event that put it live, and the model it superseded. ``drift_status``
    maps ``model_id -> status`` from a recent :func:`production_monitors` pass (the
    "current live drift status"); unknown models read ``"unknown"``.
    """

    drift = dict(drift_status or {})
    rows: list[LineageRow] = []
    for entry in registry.list_entries(status=ModelStatus.PRODUCTION):
        lineage = registry.list_lineage(entry.model_id)
        promotion = next(
            (t for t in reversed(lineage.status_history) if t.to_status == ModelStatus.PRODUCTION),
            None,
        )
        rows.append(
            LineageRow(
                model_id=entry.model_id,
                role=entry.role.value,
                nucleus=entry.nucleus,
                semantic_version=entry.semantic_version,
                artifact_sha256=entry.artifact_sha256,
                training_snapshot_hash=entry.training_data_lineage.dataset_snapshot_hash,
                metric_vector=dict(entry.metric_snapshot),
                promoted_utc=promotion.transitioned_utc.isoformat() if promotion else None,
                promotion_reason=promotion.reason if promotion else None,
                supersedes=lineage.supersedes,
                drift_status=drift.get(entry.model_id, "unknown"),
            )
        )
    rows.sort(key=lambda r: (r.role, r.nucleus or "", r.model_id))
    return LineageDashboard(rows=tuple(rows), generated_utc=clock())


# --------------------------------------------------------------------------- #
# The fail-closed deployment gate
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GateCheck:
    """One deployment-gate check and its verdict."""

    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class GateDecision:
    """The deployment-gate verdict: allowed only if every check passed."""

    allowed: bool
    checks: tuple[GateCheck, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "checks": [c.as_dict() for c in self.checks],
        }


def check_dominance(
    candidate_metrics: GoldMetricVector | None,
    incumbent_metrics: GoldMetricVector | None,
    *,
    tolerances: Mapping[str, float] | None = None,
) -> GateCheck:
    """Prompt 17 dominance gate: candidate must dominate the incumbent (no safety regression).

    A first model with no incumbent passes. A missing candidate fails closed.
    """

    if candidate_metrics is None:
        return GateCheck("dominance", False, "no candidate metric vector supplied")
    if incumbent_metrics is None:
        return GateCheck("dominance", True, "no incumbent — first model is promotable")
    passed, deltas = dominates(candidate_metrics, incumbent_metrics, tolerances)
    regressions = [d.metric for d in deltas if d.regressed]
    detail = "dominates incumbent" if passed else f"regressed / no strict gain: {regressions}"
    return GateCheck("dominance", passed, detail)


def check_audit_chain(audit_log: Any, *, key: bytes | None = None) -> GateCheck:
    """Prompt 12 provenance: the audit chain must verify (links + optional signatures).

    A missing log fails closed — a deploy with no verifiable provenance is not allowed.
    """

    if audit_log is None:
        return GateCheck("audit_chain", False, "no audit log supplied")
    report = verify_chain(audit_log, key=key)
    detail = (
        f"verified {report.entries_checked} entries"
        + (" + signatures" if report.signature_verified else "")
        if report.ok
        else f"chain broken at entry {report.first_broken_index}"
    )
    return GateCheck("audit_chain", report.ok, detail)


def check_data_leakage(
    snapshot: Any,
    *,
    gold_checksum: str,
    holdout_hashes: Iterable[str],
) -> GateCheck:
    """Leakage check: the candidate's training snapshot never touched the gold set.

    Two conditions, both required: the snapshot is **bound** to this gold set
    (``snapshot.gold_checksum == gold_checksum``, so it was validated against the
    same holdout it is gated on), and the snapshot's ``record_hashes`` are
    **disjoint** from the gold/holdout hashes. A missing snapshot fails closed.
    """

    if snapshot is None:
        return GateCheck("data_leakage", False, "no training snapshot supplied")
    snap_checksum = getattr(snapshot, "gold_checksum", None)
    if snap_checksum != gold_checksum:
        return GateCheck(
            "data_leakage",
            False,
            f"snapshot gold_checksum {snap_checksum!r} != gating gold set {gold_checksum!r}",
        )
    record_hashes = set(getattr(snapshot, "record_hashes", ()) or ())
    leaked = record_hashes & set(holdout_hashes)
    if leaked:
        return GateCheck(
            "data_leakage", False, f"{len(leaked)} gold/holdout record(s) present in training set"
        )
    return GateCheck("data_leakage", True, "training set disjoint from the gold holdout")


def evaluate_deployment_gate(
    *,
    dominance: GateCheck | bool,
    audit_chain: GateCheck | bool,
    tests_green: GateCheck | bool,
    data_leakage: GateCheck | bool,
) -> GateDecision:
    """Combine the four checks: deploy is allowed **only if all four pass**.

    Each argument is a :class:`GateCheck` or a bare bool. The gate **fails closed** —
    a failing or missing check blocks the deploy, and the ``reason`` names every
    failing check so the block is auditable.
    """

    def _as_check(name: str, value: GateCheck | bool) -> GateCheck:
        if isinstance(value, GateCheck):
            return value
        return GateCheck(name, bool(value), "ok" if value else "failed")

    checks = (
        _as_check("dominance", dominance),
        _as_check("audit_chain", audit_chain),
        _as_check("tests_green", tests_green),
        _as_check("data_leakage", data_leakage),
    )
    failing = [c.name for c in checks if not c.passed]
    allowed = not failing
    reason = "all gates passed" if allowed else f"blocked — failed: {', '.join(failing)}"
    return GateDecision(allowed=allowed, checks=checks, reason=reason)


def run_deployment_gate(
    *,
    candidate_metrics: GoldMetricVector | None = None,
    incumbent_metrics: GoldMetricVector | None = None,
    tolerances: Mapping[str, float] | None = None,
    audit_log: Any = None,
    audit_key: bytes | None = None,
    tests_green: bool = False,
    snapshot: Any = None,
    gold_checksum: str | None = None,
    holdout_hashes: Iterable[str] = (),
) -> GateDecision:
    """Compute all four gate checks from real inputs and return the fail-closed verdict.

    This is the production entry the CI deployment-gate job and the orchestration
    layer call: dominance (Prompt 17), audit-chain integrity (Prompt 12), the
    test-suite-green flag (supplied by CI), and the gold-set leakage check. Every
    input defaults to the failing state, so an under-specified call is blocked.
    """

    dominance = check_dominance(candidate_metrics, incumbent_metrics, tolerances=tolerances)
    audit = check_audit_chain(audit_log, key=audit_key)
    leakage = (
        check_data_leakage(snapshot, gold_checksum=gold_checksum, holdout_hashes=holdout_hashes)
        if gold_checksum is not None
        else GateCheck("data_leakage", False, "no gold_checksum supplied")
    )
    tests = GateCheck(
        "tests_green",
        bool(tests_green),
        "test suite green" if tests_green else "test suite not green",
    )
    return evaluate_deployment_gate(
        dominance=dominance, audit_chain=audit, tests_green=tests, data_leakage=leakage
    )
