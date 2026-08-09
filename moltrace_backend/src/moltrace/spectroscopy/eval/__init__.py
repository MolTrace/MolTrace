"""Evaluation harness — the ten metrics + dominance-based model promotion (Prompt 17).

:mod:`.harness` scores any :class:`~moltrace.spectroscopy.eval.harness.ModelBundle`
on a frozen, checksum-locked :class:`~moltrace.spectroscopy.eval.harness.GoldSet`,
returning a :class:`~moltrace.spectroscopy.eval.harness.GoldMetricVector`; a
candidate is promotable only when it **dominates** the incumbent (no regression
beyond tolerance, a strict improvement on at least one metric, zero regression on
the safety-critical metrics). :func:`~moltrace.spectroscopy.eval.harness.gate_for_ci`
is the CI gate Prompt 18 consumes.

:mod:`.conformal` turns the predictor's *claimed* per-atom uncertainty into a
**guaranteed** prediction interval. The claim and the guarantee are different
quantities and both are reported: held-out evaluation measured the reported ¹³C σ
as optimistic by ~3× in its tightest band — the band the verifier weights most —
and a Mondrian split-conformal fit repairs that band specifically, with
distribution-free finite-sample coverage that does not depend on σ being right.
"""

from __future__ import annotations

from moltrace.spectroscopy.eval.conformal import (
    CALIBRATION_VERSION,
    ConformalBin,
    ConformalCalibration,
    CoverageReport,
    Interval,
    fit_conformal,
    measure_coverage,
    min_calibration_size,
)
from moltrace.spectroscopy.eval.harness import (
    DEFAULT_TOLERANCES,
    METRIC_DIRECTIONS,
    NULLABLE_METRICS,
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
    "CALIBRATION_VERSION",
    "DEFAULT_TOLERANCES",
    "METRIC_DIRECTIONS",
    "NULLABLE_METRICS",
    "SAFETY_CRITICAL",
    "CallableBundle",
    "ConformalBin",
    "ConformalCalibration",
    "CoverageReport",
    "GoldMetricVector",
    "GoldRecord",
    "GoldSet",
    "GoldSetChecksumError",
    "Interval",
    "MetricDelta",
    "MetricDirection",
    "ModelBundle",
    "Prediction",
    "default_perturb",
    "dominates",
    "evaluate",
    "fit_conformal",
    "gate_for_ci",
    "measure_coverage",
    "min_calibration_size",
    "persist_metric_vector",
]
