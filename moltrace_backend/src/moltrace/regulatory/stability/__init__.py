"""Stability engines (Prompt 11).

:mod:`protocol_generator` generates an ICH Q1A(R2) stability protocol — climate-zone determination
from the intended markets, the per-zone long-term / intermediate / accelerated storage conditions,
the ICH testing timepoints, the dosage-form-specific attribute panel, and the ICH Q1E statistical
analysis plan — as a structured object that renders to Markdown (zero-dependency) or to a Word
``.docx`` (via the optional ``docx`` extra). Decision-support: a qualified person reviews and signs
the protocol before it is executed or filed.
"""

from __future__ import annotations

from moltrace.regulatory.stability.protocol_generator import (
    ClimateZone,
    ConditionType,
    StabilityProtocol,
    StatisticalAnalysisPlan,
    StorageCondition,
    TestAttribute,
    generate_stability_protocol,
)

__all__ = [
    "ClimateZone",
    "ConditionType",
    "StabilityProtocol",
    "StatisticalAnalysisPlan",
    "StorageCondition",
    "TestAttribute",
    "generate_stability_protocol",
]
