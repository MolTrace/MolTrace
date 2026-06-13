"""Regulatory evaluation harness (Prompt 17).

The zero-tolerance promotion gate: a new version ships only if its metric vector dominates the
incumbent on a frozen, checksummed gold set AND it has zero calculation errors and 100% formula
coverage, with no citation-correctness regression. Built on the measurement primitives in
:mod:`moltrace.regulatory.infra.eval`.
"""

from __future__ import annotations

from moltrace.regulatory.eval.harness import (
    EvaluationBundle,
    GoldSet,
    GoldSetChecksumError,
    MetricDelta,
    evaluate,
    gate,
    promotion_exit_code,
    validation_record,
)

__all__ = [
    "EvaluationBundle",
    "GoldSet",
    "GoldSetChecksumError",
    "MetricDelta",
    "evaluate",
    "gate",
    "promotion_exit_code",
    "validation_record",
]
