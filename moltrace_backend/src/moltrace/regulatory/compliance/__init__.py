"""Regulatory compliance wrappers (Prompt 12).

:mod:`annex22_wrapper` governs every AI-assisted regulatory decision in the direction of
EU GMP **Draft** Annex 22 (July 2025): each decision is documented, explainable, hash-chained
for tamper evidence, and -- for high-risk decisions -- gated behind human review. The Annex is
in DRAFT and not in force; this is decision-support governance, never an "Annex 22 compliant"
claim.
"""

from __future__ import annotations

from moltrace.regulatory.compliance.annex22_wrapper import (
    DRAFT_DISCLAIMER,
    GENESIS_HASH,
    AIDecisionRecord,
    Annex22Error,
    Annex22Log,
    Annex22PendingError,
    DecisionInputs,
    DecisionMeta,
    GovernedResult,
    RiskLevel,
    annex22_compliance_checklist,
    default_annex22_log,
    governance_context,
    with_annex22_governance,
)
from moltrace.regulatory.compliance.governed_engines import (
    GOVERNED_ENGINES,
    REQUIRED_P4_P8_DECISIONS,
    Annex22GovernanceError,
    assert_full_p4_p8_governance,
    governed_engine,
    ungoverned_p4_p8,
)

__all__ = [
    "DRAFT_DISCLAIMER",
    "GENESIS_HASH",
    "GOVERNED_ENGINES",
    "REQUIRED_P4_P8_DECISIONS",
    "AIDecisionRecord",
    "Annex22Error",
    "Annex22GovernanceError",
    "Annex22Log",
    "Annex22PendingError",
    "DecisionInputs",
    "DecisionMeta",
    "GovernedResult",
    "RiskLevel",
    "annex22_compliance_checklist",
    "assert_full_p4_p8_governance",
    "default_annex22_log",
    "governance_context",
    "governed_engine",
    "ungoverned_p4_p8",
    "with_annex22_governance",
]
