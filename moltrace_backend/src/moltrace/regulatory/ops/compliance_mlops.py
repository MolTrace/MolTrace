"""Compliance MLOps — GxP AI lifecycle & fail-closed deployment gate (Prompt 18).

Ties the model/rule-set lifecycle to GAMP 5 Appendix D11, 21 CFR Part 11, and the **direction of**
the DRAFT EU GMP Annex 22 (consistent with Prompt 12). This layer is mostly *integration*: it reuses

* Prompt 17 (:mod:`moltrace.regulatory.eval`) — the zero-tolerance gate (zero calc errors, 100 %
  formula coverage, citation no-regression, dominance) and the :class:`RegulatoryMetricVector` that
  is the test evidence in a validation record;
* Prompt 13 (:mod:`moltrace.regulatory.ai.registry`) — the append-only model/rule registry that
  carries immutable lineage and the validation-doc id per version;
* Prompt 12 (:mod:`moltrace.regulatory.compliance`) — the tamper-evident Annex 22 audit chain;
* the GAMP 5 D11 generator (:func:`build_regulatory_validation_document`).

It adds three things on top: per-version **validation records** + **change control** (GAMP 5 D11 /
Annex 22 direction), production **monitors** that open a change-control item rather than letting a
guidance/limit change flow silently, and a **fail-closed deployment gate** (deploy only if the
Prompt 17 gate passes, a current validation record exists, the Prompt 12 audit chain verifies, and
tests are green).

LANGUAGE GUARDRAIL: this module never claims the product *is* "21 CFR Part 11 compliant" or
"Annex 22 compliant" (Annex 22 is a draft). MolTrace provides controls *designed to support* these
frameworks; formal computerised-system validation remains the regulated customer's responsibility.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from moltrace.regulatory.ai.registry import Registry, default_regulatory_registry
from moltrace.regulatory.compliance.annex22_wrapper import Annex22Log
from moltrace.regulatory.eval import gate
from moltrace.regulatory.infra import (
    RegulatoryMetricVector,
    build_regulatory_validation_document,
    content_hash,
)

__all__ = [
    "LIFECYCLE_DISCLAIMER",
    "GxpRiskClass",
    "ChangeTrigger",
    "ChangeStatus",
    "ValidationRecord",
    "ChangeControl",
    "MonitorThresholds",
    "MonitorObservation",
    "MonitorAlert",
    "MonitorReport",
    "GateCheck",
    "DeploymentDecision",
    "LifecycleController",
    "build_validation_record",
    "open_change_control",
    "production_monitors",
    "evaluate_deployment",
    "main",
]

# Language guardrail (Prompt 12/18): controls that SUPPORT the frameworks — never "compliant".
LIFECYCLE_DISCLAIMER = (
    "MolTrace provides controls designed to support GAMP 5 Appendix D11, 21 CFR Part 11, and the "
    "direction of the DRAFT EU GMP Annex 22 (the Annex is in draft and not in force). Formal "
    "computerised-system validation and the overall compliance determination remain the regulated "
    "customer's responsibility."
)

_DEFAULT_REVALIDATION_DAYS = 365  # periodic-review cadence (annual) unless a caller overrides


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


class GxpRiskClass(StrEnum):
    """GAMP 5 GxP risk class of a model/rule-set version."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def gamp_label(self) -> str:
        return self.value.title()  # "High" / "Medium" / "Low" — the GAMP 5 D11 wording


class ChangeTrigger(StrEnum):
    """What opened a change-control item."""

    RETRAIN = "retrain"
    RULE_SET_UPDATE = "rule_set_update"
    GUIDANCE_REVISION = "guidance_revision"
    MONITOR_BREACH = "monitor_breach"


class ChangeStatus(StrEnum):
    OPEN = "open"
    ASSESSED = "assessed"
    SIGNED_OFF = "signed_off"
    CLOSED = "closed"


# --------------------------------------------------------------------------- #
# Validation record (GAMP 5 Appendix D11) per model/rule-set version
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ValidationRecord:
    """A GAMP 5 D11 validation record for one version: intended use, risk class, test evidence."""

    version: str
    intended_use: str
    risk_class: GxpRiskClass
    metric_vector: RegulatoryMetricVector  # Prompt 17 test evidence
    gate_passed: bool
    approver: str
    validated_utc: datetime
    revalidation_due_utc: datetime
    document_id: str
    validation_document: str  # rendered GAMP 5 D11 markdown skeleton
    record_hash: str

    def is_current(self, *, as_of: datetime | None = None) -> bool:
        """True iff the version passed its gate and the periodic-review window has not lapsed."""

        now = as_of if as_of is not None else _now()
        return self.gate_passed and now <= self.revalidation_due_utc

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "intended_use": self.intended_use,
            "risk_class": self.risk_class.value,
            "metric_vector": self.metric_vector.as_dict(),
            "gate_passed": self.gate_passed,
            "approver": self.approver,
            "validated_utc": _iso(self.validated_utc),
            "revalidation_due_utc": _iso(self.revalidation_due_utc),
            "document_id": self.document_id,
            "validation_document": self.validation_document,
            "record_hash": self.record_hash,
        }


def build_validation_record(
    *,
    version: str,
    intended_use: str,
    risk_class: GxpRiskClass,
    candidate: RegulatoryMetricVector,
    incumbent: RegulatoryMetricVector,
    approver: str,
    document_id: str = "VAL-REG-D11-0001",
    requirements: Sequence[dict] | None = None,
    revalidation_days: int = _DEFAULT_REVALIDATION_DAYS,
    now: datetime | None = None,
) -> ValidationRecord:
    """Build a per-version GAMP 5 D11 validation record; the Prompt 17 gate is the test evidence."""

    now = now if now is not None else _now()
    gate_passed, _deltas = gate(candidate, incumbent)
    document = build_regulatory_validation_document(
        rule_set_version=version,
        intended_use=intended_use,
        document_id=document_id,
        gxp_risk_class=risk_class.gamp_label,
        requirements=requirements,
        metric_vector=candidate,
    )
    revalidation_due = now + timedelta(days=revalidation_days)
    record_hash = content_hash(
        {
            "version": version,
            "intended_use": intended_use,
            "risk_class": risk_class.value,
            "metric_vector": candidate.as_dict(),
            "gate_passed": gate_passed,
            "approver": approver,
            "validated_utc": _iso(now),
            "revalidation_due_utc": _iso(revalidation_due),
            "document_id": document_id,
        }
    )
    return ValidationRecord(
        version=version,
        intended_use=intended_use,
        risk_class=risk_class,
        metric_vector=candidate,
        gate_passed=gate_passed,
        approver=approver,
        validated_utc=now,
        revalidation_due_utc=revalidation_due,
        document_id=document_id,
        validation_document=document,
        record_hash=record_hash,
    )


# --------------------------------------------------------------------------- #
# Change control (any retrain / rule-set update / guidance revision)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChangeControl:
    """A change-control item: a retrain, a rule-set update, or a guidance revision to assess."""

    change_id: str
    trigger: ChangeTrigger
    description: str
    affected_version: str
    impact_assessment: str
    revalidation_required: bool
    status: ChangeStatus
    opened_utc: datetime
    signed_off_by: str | None = None
    signed_off_utc: datetime | None = None

    def with_sign_off(self, *, approver: str, now: datetime | None = None) -> ChangeControl:
        return replace(
            self,
            status=ChangeStatus.SIGNED_OFF,
            signed_off_by=approver,
            signed_off_utc=now if now is not None else _now(),
        )

    def as_dict(self) -> dict:
        return {
            "change_id": self.change_id,
            "trigger": self.trigger.value,
            "description": self.description,
            "affected_version": self.affected_version,
            "impact_assessment": self.impact_assessment,
            "revalidation_required": self.revalidation_required,
            "status": self.status.value,
            "opened_utc": _iso(self.opened_utc),
            "signed_off_by": self.signed_off_by,
            "signed_off_utc": _iso(self.signed_off_utc) if self.signed_off_utc else None,
        }


def open_change_control(
    *,
    trigger: ChangeTrigger,
    description: str,
    affected_version: str,
    impact_assessment: str = "pending assessment",
    revalidation_required: bool = True,
    now: datetime | None = None,
) -> ChangeControl:
    """Open a change-control item with a deterministic, content-addressed id."""

    now = now if now is not None else _now()
    digest = content_hash(
        {
            "trigger": trigger.value,
            "description": description,
            "affected_version": affected_version,
            "opened_utc": _iso(now),
        }
    )
    change_id = "CC-" + digest.split(":", 1)[-1][:12]
    return ChangeControl(
        change_id=change_id,
        trigger=trigger,
        description=description,
        affected_version=affected_version,
        impact_assessment=impact_assessment,
        revalidation_required=revalidation_required,
        status=ChangeStatus.OPEN,
        opened_utc=now,
    )


# --------------------------------------------------------------------------- #
# Production monitors
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MonitorThresholds:
    """Alert thresholds for production monitoring."""

    max_override_rate: float = 0.20
    max_hallucination_rate: float = 0.02
    max_citation_failure_rate: float = 0.05
    max_agreement_drift: float = 0.10  # max tolerated drop vs the baseline expert-agreement rate


@dataclass(frozen=True)
class MonitorObservation:
    """A window of production telemetry to evaluate."""

    reviewer_override_rate: float = 0.0
    hallucination_rate: float = 0.0
    citation_failure_rate: float = 0.0
    agreement_rate: float = 1.0  # current classification-vs-expert agreement
    baseline_agreement_rate: float = 1.0  # the validated baseline
    new_ndsri_cohorts: Sequence[str] = ()  # input drift: cohorts not in the validated rule-set
    guidance_revisions: Sequence[str] = ()  # upstream guidance revisions detected


@dataclass(frozen=True)
class MonitorAlert:
    metric: str
    value: float
    threshold: float
    message: str

    def as_dict(self) -> dict:
        return {
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "message": self.message,
        }


@dataclass(frozen=True)
class MonitorReport:
    alerts: tuple[MonitorAlert, ...]
    change_controls: tuple[ChangeControl, ...]

    @property
    def ok(self) -> bool:
        """True iff nothing needs attention (no alerts and no change-control items opened)."""

        return not self.alerts and not self.change_controls

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "alerts": [a.as_dict() for a in self.alerts],
            "change_controls": [c.as_dict() for c in self.change_controls],
        }


def production_monitors(
    observation: MonitorObservation,
    *,
    thresholds: MonitorThresholds | None = None,
    affected_version: str = "current",
    now: datetime | None = None,
) -> MonitorReport:
    """Evaluate production telemetry; alert on breaches and open change control for input drift.

    A guidance revision (or a new NDSRI cohort the validated rule-set does not cover) opens a
    change-control item rather than silently flowing into answers — the deterministic rule-set must
    be assessed and revalidated first (consistent with the Prompt 20 ``revision_watch`` hold).
    """

    thresholds = thresholds if thresholds is not None else MonitorThresholds()
    now = now if now is not None else _now()
    alerts: list[MonitorAlert] = []
    changes: list[ChangeControl] = []

    if observation.reviewer_override_rate > thresholds.max_override_rate:
        alerts.append(
            MonitorAlert(
                "reviewer_override_rate",
                observation.reviewer_override_rate,
                thresholds.max_override_rate,
                "reviewer override rate above threshold — model/rule quality may be drifting",
            )
        )
    if observation.hallucination_rate > thresholds.max_hallucination_rate:
        alerts.append(
            MonitorAlert(
                "hallucination_rate",
                observation.hallucination_rate,
                thresholds.max_hallucination_rate,
                "hallucination rate above threshold (Prompt 17 metric)",
            )
        )
    if observation.citation_failure_rate > thresholds.max_citation_failure_rate:
        alerts.append(
            MonitorAlert(
                "citation_failure_rate",
                observation.citation_failure_rate,
                thresholds.max_citation_failure_rate,
                "citation-failure rate above threshold — grounding is degrading",
            )
        )
    agreement_drift = observation.baseline_agreement_rate - observation.agreement_rate
    if agreement_drift > thresholds.max_agreement_drift:
        alerts.append(
            MonitorAlert(
                "classification_agreement_drift",
                agreement_drift,
                thresholds.max_agreement_drift,
                "classification-vs-expert agreement has drifted below the validated baseline",
            )
        )

    # Input drift → change control, NOT a silent flow.
    for revision in observation.guidance_revisions:
        changes.append(
            open_change_control(
                trigger=ChangeTrigger.GUIDANCE_REVISION,
                description=(
                    f"guidance revision detected: {revision} — any limit/threshold change must be "
                    "assessed and revalidated before it can affect answers"
                ),
                affected_version=affected_version,
                revalidation_required=True,
                now=now,
            )
        )
    if observation.new_ndsri_cohorts:
        cohorts = ", ".join(observation.new_ndsri_cohorts)
        alerts.append(
            MonitorAlert(
                "input_drift_ndsri",
                float(len(observation.new_ndsri_cohorts)),
                0.0,
                f"input drift: new NDSRI cohort(s) not in the validated rule-set ({cohorts})",
            )
        )
        for cohort in observation.new_ndsri_cohorts:
            changes.append(
                open_change_control(
                    trigger=ChangeTrigger.RULE_SET_UPDATE,
                    description=(
                        f"new NDSRI cohort observed in inputs: {cohort} — assess whether the "
                        "deterministic rule-set requires an update"
                    ),
                    affected_version=affected_version,
                    revalidation_required=True,
                    now=now,
                )
            )

    return MonitorReport(tuple(alerts), tuple(changes))


# --------------------------------------------------------------------------- #
# Fail-closed deployment gate
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class DeploymentDecision:
    allowed: bool
    checks: tuple[GateCheck, ...]
    reason: str

    @property
    def blocked(self) -> bool:
        return not self.allowed

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "checks": [c.as_dict() for c in self.checks],
            "reason": self.reason,
        }


def evaluate_deployment(
    *,
    candidate: RegulatoryMetricVector,
    incumbent: RegulatoryMetricVector,
    validation_record: ValidationRecord | None,
    audit_chain_ok: bool,
    tests_green: bool,
    now: datetime | None = None,
) -> DeploymentDecision:
    """Fail-closed release control. Deploy ONLY if every check passes.

    Checks: (1) the Prompt 17 gate (zero calc errors, 100 % coverage, citation no-regression,
    dominance); (2) a *current* GAMP 5 D11 validation record exists for the version; (3) the
    Prompt 12 Annex 22 audit chain verifies; (4) tests are green. A missing validation record or any
    failing check blocks the deploy.
    """

    now = now if now is not None else _now()
    gate_passed, _deltas = gate(candidate, incumbent)
    validation_ok = (
        validation_record is not None
        and validation_record.gate_passed
        and validation_record.is_current(as_of=now)
    )
    checks = (
        GateCheck(
            "prompt17_gate",
            gate_passed,
            "zero calc errors, 100% formula coverage, citation no-regression, dominance",
        ),
        GateCheck(
            "validation_record_current",
            validation_ok,
            "a current GAMP 5 D11 validation record exists for this version"
            if validation_ok
            else "no current validation record (missing, gate-failed, or past revalidation due)",
        ),
        GateCheck(
            "audit_chain_verifies",
            bool(audit_chain_ok),
            "Prompt 12 Annex 22 hash-chain integrity",
        ),
        GateCheck("tests_green", bool(tests_green), "backend + frontend test suites green"),
    )
    allowed = all(c.passed for c in checks)
    if allowed:
        reason = "all release-control checks passed"
    else:
        reason = "blocked (fail-closed): " + ", ".join(c.name for c in checks if not c.passed)
    return DeploymentDecision(allowed=allowed, checks=checks, reason=reason)


# --------------------------------------------------------------------------- #
# Lifecycle controller — ties registry (lineage) + audit chain + validations + change control
# --------------------------------------------------------------------------- #
class LifecycleController:
    """The GxP AI lifecycle: validation records + change control + lineage + the deployment gate.

    Holds a Prompt 13 :class:`Registry` (immutable lineage / validation-doc ids) and a Prompt 12
    :class:`Annex22Log` (tamper-evident audit chain); maintains a per-version validation record and
    a change-control log; and exposes the fail-closed deployment decision.
    """

    def __init__(
        self,
        *,
        registry: Registry | None = None,
        audit_log: Annex22Log | None = None,
        revalidation_days: int = _DEFAULT_REVALIDATION_DAYS,
    ) -> None:
        self.registry = registry if registry is not None else default_regulatory_registry()
        self.audit_log = audit_log if audit_log is not None else Annex22Log()
        self.revalidation_days = revalidation_days
        self._validations: dict[str, ValidationRecord] = {}
        self._changes: list[ChangeControl] = []

    # -- validation records -------------------------------------------------- #
    def validate_version(
        self,
        *,
        version: str,
        intended_use: str,
        risk_class: GxpRiskClass,
        candidate: RegulatoryMetricVector,
        incumbent: RegulatoryMetricVector,
        approver: str,
        document_id: str = "VAL-REG-D11-0001",
        requirements: Sequence[dict] | None = None,
        now: datetime | None = None,
    ) -> ValidationRecord:
        record = build_validation_record(
            version=version,
            intended_use=intended_use,
            risk_class=risk_class,
            candidate=candidate,
            incumbent=incumbent,
            approver=approver,
            document_id=document_id,
            requirements=requirements,
            revalidation_days=self.revalidation_days,
            now=now,
        )
        self._validations[version] = record
        return record

    def current_validation(
        self, version: str, *, as_of: datetime | None = None
    ) -> ValidationRecord | None:
        record = self._validations.get(version)
        if record is None or not record.is_current(as_of=as_of):
            return None
        return record

    # -- change control ------------------------------------------------------ #
    def open_change_control(
        self,
        *,
        trigger: ChangeTrigger,
        description: str,
        affected_version: str,
        impact_assessment: str = "pending assessment",
        revalidation_required: bool = True,
        now: datetime | None = None,
    ) -> ChangeControl:
        item = open_change_control(
            trigger=trigger,
            description=description,
            affected_version=affected_version,
            impact_assessment=impact_assessment,
            revalidation_required=revalidation_required,
            now=now,
        )
        self._changes.append(item)
        return item

    def sign_off_change_control(
        self, change_id: str, *, approver: str, now: datetime | None = None
    ) -> ChangeControl:
        for i, item in enumerate(self._changes):
            if item.change_id == change_id:
                signed = item.with_sign_off(approver=approver, now=now)
                self._changes[i] = signed
                return signed
        raise KeyError(change_id)

    def change_controls(self) -> tuple[ChangeControl, ...]:
        return tuple(self._changes)

    def open_change_controls(self) -> tuple[ChangeControl, ...]:
        active = (ChangeStatus.OPEN, ChangeStatus.ASSESSED)
        return tuple(c for c in self._changes if c.status in active)

    # -- monitors ------------------------------------------------------------ #
    def run_monitors(
        self,
        observation: MonitorObservation,
        *,
        thresholds: MonitorThresholds | None = None,
        affected_version: str = "current",
        now: datetime | None = None,
    ) -> MonitorReport:
        report = production_monitors(
            observation, thresholds=thresholds, affected_version=affected_version, now=now
        )
        self._changes.extend(report.change_controls)  # persist — never silent
        return report

    # -- lineage + audit ----------------------------------------------------- #
    def lineage(self, entry_id: str) -> dict:
        return self.registry.provenance(entry_id)

    def verify_audit_chain(self) -> tuple[bool, list[str]]:
        return self.audit_log.verify_chain()

    # -- the fail-closed gate ------------------------------------------------ #
    def deployment_decision(
        self,
        *,
        version: str,
        candidate: RegulatoryMetricVector,
        incumbent: RegulatoryMetricVector,
        tests_green: bool,
        now: datetime | None = None,
    ) -> DeploymentDecision:
        validation_record = self.current_validation(version, as_of=now)
        audit_ok, _breaks = self.verify_audit_chain()
        return evaluate_deployment(
            candidate=candidate,
            incumbent=incumbent,
            validation_record=validation_record,
            audit_chain_ok=audit_ok,
            tests_green=tests_green,
            now=now,
        )


# --------------------------------------------------------------------------- #
# CI self-check (always-on guarantee that the gate fails closed)
# --------------------------------------------------------------------------- #
def _self_check() -> tuple[bool, list[str]]:
    """Verify the fail-closed gate: ALLOW an all-pass candidate, BLOCK each single-check failure."""

    failures: list[str] = []
    base = datetime(2026, 1, 1, tzinfo=UTC)
    incumbent = RegulatoryMetricVector(
        formula_coverage=1.0,
        calculation_error_rate=0.0,
        citation_correctness=0.90,
        classification_accuracy=0.90,
    )
    candidate = RegulatoryMetricVector(
        formula_coverage=1.0,
        calculation_error_rate=0.0,
        citation_correctness=0.95,
        classification_accuracy=0.92,
    )
    bad_candidate = RegulatoryMetricVector(  # fails the hard gates (calc error, coverage < 1)
        formula_coverage=0.99,
        calculation_error_rate=0.01,
        citation_correctness=0.95,
        classification_accuracy=0.92,
    )
    valid = build_validation_record(
        version="rs-1",
        intended_use="ICH/FDA impurity decision-support",
        risk_class=GxpRiskClass.HIGH,
        candidate=candidate,
        incumbent=incumbent,
        approver="QA",
        now=base,
    )
    stale = build_validation_record(
        version="rs-1",
        intended_use="ICH/FDA impurity decision-support",
        risk_class=GxpRiskClass.HIGH,
        candidate=candidate,
        incumbent=incumbent,
        approver="QA",
        now=base - timedelta(days=_DEFAULT_REVALIDATION_DAYS + 30),  # past revalidation as of base
    )

    def decide(**kw) -> DeploymentDecision:
        params = dict(
            candidate=candidate,
            incumbent=incumbent,
            validation_record=valid,
            audit_chain_ok=True,
            tests_green=True,
            now=base,
        )
        params.update(kw)
        return evaluate_deployment(**params)

    if not decide().allowed:
        failures.append("all-pass candidate was blocked")
    if decide(candidate=bad_candidate).allowed:
        failures.append("gate-failing candidate was allowed")
    if decide(validation_record=None).allowed:
        failures.append("missing validation record was allowed")
    if decide(validation_record=stale).allowed:
        failures.append("stale validation record was allowed")
    if decide(audit_chain_ok=False).allowed:
        failures.append("audit-chain failure was allowed")
    if decide(tests_green=False).allowed:
        failures.append("tests-not-green was allowed")
    return (not failures, failures)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for the regulatory fail-closed deployment gate. Returns the exit code."""

    parser = argparse.ArgumentParser(
        prog="moltrace-regulatory-deployment-gate",
        description="Regulatory compliance-MLOps fail-closed deployment gate (Prompt 18).",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="verify the gate machinery fails closed (the always-on CI guarantee)",
    )
    parser.add_argument("--gate-pass", action="store_true", help="Prompt 17 gate verdict")
    parser.add_argument(
        "--validation-current", action="store_true", help="a current validation record exists"
    )
    parser.add_argument("--audit-pass", action="store_true", help="Annex 22 audit chain verifies")
    parser.add_argument("--tests-green", action="store_true", help="test suites are green")
    args = parser.parse_args(argv)

    real_mode = any([args.gate_pass, args.validation_current, args.audit_pass, args.tests_green])
    if args.self_check or not real_mode:
        ok, failures = _self_check()
        if ok:
            print("regulatory deployment-gate self-check: PASS (allows all-pass, blocks failures)")
            return 0
        print("regulatory deployment-gate self-check: FAIL", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    # Real deploy from pre-computed verdicts (a missing flag = False = fail-closed).
    checks = (
        GateCheck("prompt17_gate", args.gate_pass, "Prompt 17 evaluation gate"),
        GateCheck("validation_record_current", args.validation_current, "current GAMP 5 record"),
        GateCheck("audit_chain_verifies", args.audit_pass, "Annex 22 hash chain"),
        GateCheck("tests_green", args.tests_green, "test suites green"),
    )
    allowed = all(c.passed for c in checks)
    for check in checks:
        print(f"  [{'PASS' if check.passed else 'FAIL'}] {check.name}")
    print("deploy ALLOWED" if allowed else "deploy BLOCKED (fail-closed)")
    return 0 if allowed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
