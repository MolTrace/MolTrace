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
    GovernedResult,
    RiskLevel,
    annex22_compliance_checklist,
    default_annex22_log,
    governance_context,
    with_annex22_governance,
)

__all__ = [
    "DRAFT_DISCLAIMER",
    "GENESIS_HASH",
    "AIDecisionRecord",
    "Annex22Error",
    "Annex22Log",
    "Annex22PendingError",
    "GovernedResult",
    "RiskLevel",
    "annex22_compliance_checklist",
    "default_annex22_log",
    "governance_context",
    "with_annex22_governance",
]
