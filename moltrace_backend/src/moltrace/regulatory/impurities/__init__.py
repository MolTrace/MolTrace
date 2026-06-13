"""Impurity assessment & risk — the deterministic ICH/FDA impurity engine.

Tier A of the ComplianceCore (Methods 1-10): ICH Q3A/B thresholds, Q3C residual
solvents, Q3D elemental impurities, ICH M7 mutagenicity, the FDA/EMA nitrosamine
CPCA classifier, and cumulative risk. Every result is a deterministic, auditable
calculation tied to a named guidance revision — decision-support that a qualified
reviewer verifies and signs off, never a regulatory determination.
"""

from __future__ import annotations

from moltrace.regulatory.impurities.cpca_classifier import (
    CPCAResult,
    CumulativeRiskResult,
    aggregate_cumulative_risk,
    calculate_cumulative_risk,
    classify_cpca,
    cpca_rule_set,
)
from moltrace.regulatory.impurities.m7_classifier import (
    M7Classification,
    classify_m7,
    m7_rule_set,
)
from moltrace.regulatory.impurities.q3ab_calculator import (
    ImpurityThresholds,
    ThresholdValue,
    calculate_q3ab_thresholds,
    q3ab_rule_set,
)
from moltrace.regulatory.impurities.q3c_solvents import (
    ComplianceResult,
    SolventClassification,
    check_residual_solvent_limits,
    classify_solvent,
    q3c_rule_set,
)
from moltrace.regulatory.impurities.q3d_elements import (
    ConcentrationLimit,
    ElementalRiskAssessment,
    ElementPDE,
    ElementRiskItem,
    calculate_concentration_limit,
    get_element_pde,
    q3d_rule_set,
    risk_assessment_report,
)

__all__ = [
    "CPCAResult",
    "ComplianceResult",
    "ConcentrationLimit",
    "CumulativeRiskResult",
    "ElementPDE",
    "ElementRiskItem",
    "ElementalRiskAssessment",
    "ImpurityThresholds",
    "M7Classification",
    "SolventClassification",
    "ThresholdValue",
    "aggregate_cumulative_risk",
    "calculate_concentration_limit",
    "calculate_cumulative_risk",
    "calculate_q3ab_thresholds",
    "check_residual_solvent_limits",
    "classify_cpca",
    "classify_m7",
    "classify_solvent",
    "cpca_rule_set",
    "get_element_pde",
    "m7_rule_set",
    "q3ab_rule_set",
    "q3c_rule_set",
    "q3d_rule_set",
    "risk_assessment_report",
]
