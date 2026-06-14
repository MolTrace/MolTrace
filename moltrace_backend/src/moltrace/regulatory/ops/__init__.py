"""Regulatory compliance MLOps — GxP AI lifecycle & fail-closed deployment (Prompt 18).

:mod:`compliance_mlops` ties the model/rule-set lifecycle to GAMP 5 Appendix D11, 21 CFR Part 11,
and the direction of the DRAFT EU GMP Annex 22 — reusing the Prompt 17 evaluation gate, the Prompt
13 registry (lineage), the Prompt 12 audit chain, and the GAMP 5 D11 generator. It maintains a
per-version validation record + change control, runs production monitors that open a change-control
item rather than letting a guidance/limit change flow silently, and gates deployment fail-closed.

The software provides controls *designed to support* these frameworks; formal computerised-system
validation remains the regulated customer's responsibility (never a "compliant" claim).
"""

from __future__ import annotations

from moltrace.regulatory.ops.compliance_mlops import (
    LIFECYCLE_DISCLAIMER,
    ChangeControl,
    ChangeStatus,
    ChangeTrigger,
    DeploymentDecision,
    GateCheck,
    GxpRiskClass,
    LifecycleController,
    MonitorAlert,
    MonitorObservation,
    MonitorReport,
    MonitorThresholds,
    ValidationRecord,
    build_validation_record,
    evaluate_deployment,
    main,
    open_change_control,
    production_monitors,
)

__all__ = [
    "LIFECYCLE_DISCLAIMER",
    "ChangeControl",
    "ChangeStatus",
    "ChangeTrigger",
    "DeploymentDecision",
    "GateCheck",
    "GxpRiskClass",
    "LifecycleController",
    "MonitorAlert",
    "MonitorObservation",
    "MonitorReport",
    "MonitorThresholds",
    "ValidationRecord",
    "build_validation_record",
    "evaluate_deployment",
    "main",
    "open_change_control",
    "production_monitors",
]
