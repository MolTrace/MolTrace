"""Prompt 18 — compliance MLOps: GxP lifecycle & fail-closed deployment gate.

Exercises the four acceptance criteria: a validation record + change control + lineage per version,
production monitors with a guidance-update change-control trigger, the fail-closed CI gate (allow an
all-pass candidate, block every single-check failure), and the language guardrail (no "compliant"
product claims). Everything runs offline.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from moltrace.regulatory.ai.registry import default_regulatory_registry
from moltrace.regulatory.infra import RegulatoryMetricVector
from moltrace.regulatory.ops import (
    LIFECYCLE_DISCLAIMER,
    ChangeStatus,
    ChangeTrigger,
    DeploymentDecision,
    GxpRiskClass,
    LifecycleController,
    MonitorObservation,
    MonitorThresholds,
    ValidationRecord,
    build_validation_record,
    evaluate_deployment,
    main,
    open_change_control,
    production_monitors,
)
from moltrace.regulatory.ops import compliance_mlops as mlops

_BASE = datetime(2026, 1, 1, tzinfo=UTC)
_INCUMBENT = RegulatoryMetricVector(
    formula_coverage=1.0,
    calculation_error_rate=0.0,
    citation_correctness=0.90,
    classification_accuracy=0.90,
)
_CANDIDATE = RegulatoryMetricVector(
    formula_coverage=1.0,
    calculation_error_rate=0.0,
    citation_correctness=0.95,
    classification_accuracy=0.92,
)
_BAD_CANDIDATE = RegulatoryMetricVector(  # fails the hard gates
    formula_coverage=0.99,
    calculation_error_rate=0.01,
    citation_correctness=0.95,
    classification_accuracy=0.92,
)


def _valid_record(*, now=_BASE) -> ValidationRecord:
    return build_validation_record(
        version="rs-1",
        intended_use="ICH/FDA impurity decision-support",
        risk_class=GxpRiskClass.HIGH,
        candidate=_CANDIDATE,
        incumbent=_INCUMBENT,
        approver="QA Lead",
        now=now,
    )


# --------------------------------------------------------------------------- #
# Acceptance 1: validation record + change control + lineage per version
# --------------------------------------------------------------------------- #
def test_validation_record_has_gamp_d11_evidence_and_cadence() -> None:
    rec = _valid_record()
    assert isinstance(rec, ValidationRecord)
    assert rec.intended_use and rec.approver == "QA Lead"
    assert rec.risk_class is GxpRiskClass.HIGH
    assert rec.metric_vector is _CANDIDATE  # Prompt 17 test evidence
    assert rec.gate_passed is True
    assert rec.revalidation_due_utc == _BASE + timedelta(days=365)
    assert rec.is_current(as_of=_BASE) is True
    assert rec.is_current(as_of=_BASE + timedelta(days=400)) is False  # periodic review lapsed
    assert "responsibility" in rec.validation_document.lower()  # decision-support framing
    assert "rs-1" in rec.validation_document  # versioned to the rule-set
    assert rec.record_hash.startswith("sha256:")


def test_gate_failing_version_is_not_current() -> None:
    rec = build_validation_record(
        version="rs-bad",
        intended_use="x",
        risk_class=GxpRiskClass.HIGH,
        candidate=_BAD_CANDIDATE,
        incumbent=_INCUMBENT,
        approver="QA",
        now=_BASE,
    )
    assert rec.gate_passed is False
    assert rec.is_current(as_of=_BASE) is False  # a failed gate is never "current"


def test_controller_keeps_validation_record_and_lineage_per_version() -> None:
    registry = default_regulatory_registry()
    controller = LifecycleController(registry=registry)
    rec = controller.validate_version(
        version="rs-1",
        intended_use="ICH/FDA impurity decision-support",
        risk_class=GxpRiskClass.HIGH,
        candidate=_CANDIDATE,
        incumbent=_INCUMBENT,
        approver="QA Lead",
        now=_BASE,
    )
    assert controller.current_validation("rs-1", as_of=_BASE) is rec
    assert controller.current_validation("rs-1", as_of=_BASE + timedelta(days=400)) is None
    assert controller.current_validation("rs-unknown", as_of=_BASE) is None
    # immutable lineage from the Prompt 13 registry
    entry_id = registry.list_entries()[0].entry_id
    lineage = controller.lineage(entry_id)
    assert isinstance(lineage, dict) and lineage


def test_change_control_open_and_sign_off() -> None:
    controller = LifecycleController()
    cc = controller.open_change_control(
        trigger=ChangeTrigger.RETRAIN,
        description="quarterly retrain of the narrative adapter",
        affected_version="rs-1",
        now=_BASE,
    )
    assert cc.status is ChangeStatus.OPEN and cc.change_id.startswith("CC-")
    assert cc.revalidation_required is True
    assert controller.open_change_controls() == (cc,)
    signed = controller.sign_off_change_control(cc.change_id, approver="QA Lead", now=_BASE)
    assert signed.status is ChangeStatus.SIGNED_OFF and signed.signed_off_by == "QA Lead"
    assert controller.open_change_controls() == ()  # no longer open


def test_change_control_id_is_deterministic() -> None:
    a = open_change_control(
        trigger=ChangeTrigger.RULE_SET_UPDATE, description="d", affected_version="rs-1", now=_BASE
    )
    b = open_change_control(
        trigger=ChangeTrigger.RULE_SET_UPDATE, description="d", affected_version="rs-1", now=_BASE
    )
    assert a.change_id == b.change_id  # content-addressed, reproducible


# --------------------------------------------------------------------------- #
# Acceptance 2: monitors with a guidance-update change-control trigger
# --------------------------------------------------------------------------- #
def test_monitors_clean_observation_is_ok() -> None:
    report = production_monitors(MonitorObservation(), now=_BASE)
    assert report.ok is True and not report.alerts and not report.change_controls


def test_monitors_alert_on_each_breach() -> None:
    obs = MonitorObservation(
        reviewer_override_rate=0.5,
        hallucination_rate=0.2,
        citation_failure_rate=0.3,
        agreement_rate=0.7,
        baseline_agreement_rate=0.95,
    )
    report = production_monitors(obs, now=_BASE)
    metrics = {a.metric for a in report.alerts}
    assert {
        "reviewer_override_rate",
        "hallucination_rate",
        "citation_failure_rate",
        "classification_agreement_drift",
    } <= metrics
    assert report.ok is False


def test_guidance_revision_opens_change_control_not_silent() -> None:
    obs = MonitorObservation(guidance_revisions=("ICH Q3D(R3)",))
    report = production_monitors(obs, affected_version="rs-1", now=_BASE)
    assert len(report.change_controls) == 1
    cc = report.change_controls[0]
    assert cc.trigger is ChangeTrigger.GUIDANCE_REVISION
    assert cc.revalidation_required is True and cc.affected_version == "rs-1"
    assert "ICH Q3D(R3)" in cc.description
    assert report.ok is False  # a change-control item needs attention


def test_new_ndsri_cohort_opens_rule_set_update_and_input_drift_alert() -> None:
    obs = MonitorObservation(new_ndsri_cohorts=("NDSRI-X",))
    report = production_monitors(obs, affected_version="rs-1", now=_BASE)
    assert any(a.metric == "input_drift_ndsri" for a in report.alerts)
    assert any(c.trigger is ChangeTrigger.RULE_SET_UPDATE for c in report.change_controls)


def test_controller_run_monitors_persists_change_controls() -> None:
    controller = LifecycleController()
    controller.run_monitors(MonitorObservation(guidance_revisions=("ICH M7(R3)",)), now=_BASE)
    assert any(
        c.trigger is ChangeTrigger.GUIDANCE_REVISION for c in controller.change_controls()
    )


def test_monitor_thresholds_are_configurable() -> None:
    obs = MonitorObservation(hallucination_rate=0.03)
    assert production_monitors(obs, now=_BASE).alerts  # default 0.02 threshold breached
    loose = MonitorThresholds(max_hallucination_rate=0.10)
    assert not production_monitors(obs, thresholds=loose, now=_BASE).alerts


# --------------------------------------------------------------------------- #
# Acceptance 3: CI gate fails closed unless all checks pass
# --------------------------------------------------------------------------- #
def test_deployment_gate_allows_all_pass() -> None:
    decision = evaluate_deployment(
        candidate=_CANDIDATE,
        incumbent=_INCUMBENT,
        validation_record=_valid_record(),
        audit_chain_ok=True,
        tests_green=True,
        now=_BASE,
    )
    assert isinstance(decision, DeploymentDecision)
    assert decision.allowed is True and decision.blocked is False
    assert all(c.passed for c in decision.checks)


@pytest.mark.parametrize(
    "override,expected_block",
    [
        ({"candidate": _BAD_CANDIDATE}, "prompt17_gate"),
        ({"validation_record": None}, "validation_record_current"),
        ({"audit_chain_ok": False}, "audit_chain_verifies"),
        ({"tests_green": False}, "tests_green"),
    ],
)
def test_deployment_gate_fails_closed_on_any_single_failure(override, expected_block) -> None:
    params = dict(
        candidate=_CANDIDATE,
        incumbent=_INCUMBENT,
        validation_record=_valid_record(),
        audit_chain_ok=True,
        tests_green=True,
        now=_BASE,
    )
    params.update(override)
    decision = evaluate_deployment(**params)
    assert decision.allowed is False
    assert expected_block in decision.reason
    blocked = {c.name for c in decision.checks if not c.passed}
    assert expected_block in blocked


def test_deployment_gate_blocks_stale_validation_record() -> None:
    decision = evaluate_deployment(
        candidate=_CANDIDATE,
        incumbent=_INCUMBENT,
        validation_record=_valid_record(),  # validated at _BASE, due +365d
        audit_chain_ok=True,
        tests_green=True,
        now=_BASE + timedelta(days=400),  # past revalidation
    )
    assert decision.allowed is False


def test_controller_deployment_decision_end_to_end() -> None:
    controller = LifecycleController()
    controller.validate_version(
        version="rs-1",
        intended_use="ICH/FDA impurity decision-support",
        risk_class=GxpRiskClass.HIGH,
        candidate=_CANDIDATE,
        incumbent=_INCUMBENT,
        approver="QA",
        now=_BASE,
    )
    ok = controller.deployment_decision(
        version="rs-1", candidate=_CANDIDATE, incumbent=_INCUMBENT, tests_green=True, now=_BASE
    )
    assert ok.allowed is True  # empty audit chain verifies, validation current, gate passes
    # a version with no validation record is blocked, fail-closed
    blocked = controller.deployment_decision(
        version="rs-2", candidate=_CANDIDATE, incumbent=_INCUMBENT, tests_green=True, now=_BASE
    )
    assert blocked.allowed is False


def test_self_check_passes() -> None:
    ok, failures = mlops._self_check()
    assert ok is True, failures


def test_cli_self_check_returns_zero() -> None:
    assert main(["--self-check"]) == 0
    assert main([]) == 0  # no flags defaults to the self-check


def test_cli_real_mode_is_fail_closed() -> None:
    assert main(["--gate-pass"]) == 1  # only one verdict -> blocked
    assert main(["--gate-pass", "--validation-current", "--audit-pass"]) == 1  # tests missing
    assert main(["--gate-pass", "--validation-current", "--audit-pass", "--tests-green"]) == 0


# --------------------------------------------------------------------------- #
# Acceptance 4: no "compliant" product claims in user-facing strings
# --------------------------------------------------------------------------- #
_FORBIDDEN_CLAIMS = (
    "part 11 compliant",
    "annex 22 compliant",
    "annex22 compliant",
    "is compliant",
    "are compliant",
    "fully compliant",
)


def test_disclaimer_uses_supporting_language() -> None:
    low = LIFECYCLE_DISCLAIMER.lower()
    assert "designed to support" in low
    assert "responsibility" in low
    assert "draft" in low  # Annex 22 framed as draft, not in force
    assert "compliant" not in low


def test_no_compliant_claims_in_user_facing_strings() -> None:
    decision = evaluate_deployment(
        candidate=_BAD_CANDIDATE,
        incumbent=_INCUMBENT,
        validation_record=None,
        audit_chain_ok=False,
        tests_green=False,
        now=_BASE,
    )
    report = production_monitors(
        MonitorObservation(
            hallucination_rate=0.9, guidance_revisions=("ICH Q3D(R3)",), new_ndsri_cohorts=("X",)
        ),
        now=_BASE,
    )
    strings = [LIFECYCLE_DISCLAIMER, decision.reason]
    strings += [c.detail for c in decision.checks]
    strings += [a.message for a in report.alerts]
    strings += [c.description for c in report.change_controls]
    strings.append(_valid_record().validation_document)
    blob = "\n".join(strings).lower()
    for claim in _FORBIDDEN_CLAIMS:
        assert claim not in blob, f"forbidden product claim in user-facing strings: {claim!r}"
