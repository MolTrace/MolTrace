"""MLOps: production monitoring, drift detection, and the deployment gate (Prompt 18).

* :mod:`.monitoring` -- drift monitors (input population-stability index, confidence
  and override-rate trends, latency vs SLO), the registry-backed lineage dashboard,
  and the fail-closed deployment gate (Prompt 17 dominance + Prompt 12 audit chain +
  test-suite-green + gold-set leakage check).
* :mod:`.deployment_gate` -- the CLI the CI pipeline invokes; it fails closed unless
  every gate check passes.
"""

from __future__ import annotations

from moltrace.spectroscopy.ops.monitoring import (
    ConfidenceSample,
    DriftMetric,
    GateCheck,
    GateDecision,
    LineageDashboard,
    LineageRow,
    MonitoringError,
    MonitoringReport,
    MonitorStatus,
    check_audit_chain,
    check_data_leakage,
    check_dominance,
    confidence_drift,
    evaluate_deployment_gate,
    input_drift,
    latency_drift,
    lineage_dashboard,
    numeric_psi,
    override_rate_drift,
    percentile,
    population_stability_index,
    production_monitors,
    run_deployment_gate,
    snapshot_distributions,
)

__all__ = [
    "ConfidenceSample",
    "DriftMetric",
    "GateCheck",
    "GateDecision",
    "LineageDashboard",
    "LineageRow",
    "MonitorStatus",
    "MonitoringError",
    "MonitoringReport",
    "check_audit_chain",
    "check_data_leakage",
    "check_dominance",
    "confidence_drift",
    "evaluate_deployment_gate",
    "input_drift",
    "latency_drift",
    "lineage_dashboard",
    "numeric_psi",
    "override_rate_drift",
    "percentile",
    "population_stability_index",
    "production_monitors",
    "run_deployment_gate",
    "snapshot_distributions",
]
