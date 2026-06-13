"""Quality-system engines.

:mod:`oos_investigation` (Prompt 7) implements the FDA 2006 *Investigating Out-of-Specification
(OOS) Test Results for Pharmaceutical Production* two-phase framework and assembles a complete
investigation report carrying the FDA OOS + ICH Q10 elements, ready for QA review.

:mod:`spc_dashboard` (Prompt 9) provides the process-capability indices (Cp/Cpk/Pp/Ppk/Cpm) and the
SPC signal detectors (the eight Western Electric / Nelson / Montgomery run-zone rules, plus CUSUM
and EWMA), and a trending layer that raises drift/shift alerts before an OOS event occurs.

Decision-support only — the quality unit owns the disposition.
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
from moltrace.regulatory.quality.spc_dashboard import (
    AlertSeverity,
    CapabilityIndices,
    CapabilityRating,
    MeasurementPoint,
    MeasurementSeries,
    SPCSignal,
    TrendAlert,
    TrendingReport,
    analyze_series,
    calculate_capability_indices,
    capability_for_specification,
    cusum_signals,
    cusum_statistics,
    detect_spc_signals,
    ewma_signals,
    ewma_statistics,
    series_from_analytical_results,
    series_from_batch_results,
)

__all__ = [
    "AlertSeverity",
    "AnalyticalResult",
    "BatchRecord",
    "CapabilityIndices",
    "CapabilityRating",
    "InvestigationReport",
    "MeasurementPoint",
    "MeasurementSeries",
    "OOSDecision",
    "Phase1Findings",
    "Phase1Investigation",
    "Phase2Findings",
    "Phase2Investigation",
    "RegulatoryActionType",
    "RootCauseCategory",
    "SPCSignal",
    "SpecificationLimit",
    "TrendAlert",
    "TrendingReport",
    "analyze_series",
    "calculate_capability_indices",
    "capability_for_specification",
    "cusum_signals",
    "cusum_statistics",
    "detect_spc_signals",
    "ewma_signals",
    "ewma_statistics",
    "initiate_phase1_investigation",
    "initiate_phase2_investigation",
    "run_oos_investigation",
    "series_from_analytical_results",
    "series_from_batch_results",
]
