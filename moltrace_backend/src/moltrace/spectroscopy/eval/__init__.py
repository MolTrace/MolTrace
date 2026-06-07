"""Evaluation harness — the ten metrics + dominance-based model promotion (Prompt 17).

:mod:`.harness` scores any :class:`~moltrace.spectroscopy.eval.harness.ModelBundle`
on a frozen, checksum-locked :class:`~moltrace.spectroscopy.eval.harness.GoldSet`,
returning a :class:`~moltrace.spectroscopy.eval.harness.GoldMetricVector`; a
candidate is promotable only when it **dominates** the incumbent (no regression
beyond tolerance, a strict improvement on at least one metric, zero regression on
the safety-critical metrics). :func:`~moltrace.spectroscopy.eval.harness.gate_for_ci`
is the CI gate Prompt 18 consumes.
"""

from __future__ import annotations

from moltrace.spectroscopy.eval.harness import (
    DEFAULT_TOLERANCES,
    METRIC_DIRECTIONS,
    SAFETY_CRITICAL,
    CallableBundle,
    GoldMetricVector,
    GoldRecord,
    GoldSet,
    GoldSetChecksumError,
    MetricDelta,
    MetricDirection,
    ModelBundle,
    Prediction,
    default_perturb,
    dominates,
    evaluate,
    gate_for_ci,
    persist_metric_vector,
)

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
