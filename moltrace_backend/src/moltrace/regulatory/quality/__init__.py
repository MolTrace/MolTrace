"""Quality-system workflows (Prompt 7).

:mod:`oos_investigation` implements the FDA 2006 *Investigating Out-of-Specification (OOS) Test
Results for Pharmaceutical Production* two-phase framework and assembles a complete investigation
report carrying the FDA OOS + ICH Q10 elements, ready for QA review. Decision-support only — the
quality unit owns the disposition.
"""

from __future__ import annotations

from moltrace.regulatory.quality.oos_investigation import (
    AnalyticalResult,
    BatchRecord,
    InvestigationReport,
    OOSDecision,
    Phase1Findings,
    Phase1Investigation,
    Phase2Findings,
    Phase2Investigation,
    RegulatoryActionType,
    RootCauseCategory,
    SpecificationLimit,
    initiate_phase1_investigation,
    initiate_phase2_investigation,
    run_oos_investigation,
)

__all__ = [
    "AnalyticalResult",
    "BatchRecord",
    "InvestigationReport",
    "OOSDecision",
    "Phase1Findings",
    "Phase1Investigation",
    "Phase2Findings",
    "Phase2Investigation",
    "RegulatoryActionType",
    "RootCauseCategory",
    "SpecificationLimit",
    "initiate_phase1_investigation",
    "initiate_phase2_investigation",
    "run_oos_investigation",
]
