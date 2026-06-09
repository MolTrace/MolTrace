"""Impurity assessment & risk — the deterministic ICH/FDA impurity engine.

Tier A of the Regulatory Hub (Methods 1-10): ICH Q3A/B thresholds, Q3C residual
solvents, Q3D elemental impurities, ICH M7 mutagenicity, the FDA/EMA nitrosamine
CPCA classifier, and cumulative risk. Every result is a deterministic, auditable
calculation tied to a named guidance revision — decision-support that a qualified
reviewer verifies and signs off, never a regulatory determination.
"""

from __future__ import annotations

from moltrace.regulatory.impurities.q3ab_calculator import (
    ImpurityThresholds,
    ThresholdValue,
    calculate_q3ab_thresholds,
    q3ab_rule_set,
)

__all__ = [
    "ImpurityThresholds",
    "ThresholdValue",
    "calculate_q3ab_thresholds",
    "q3ab_rule_set",
]
