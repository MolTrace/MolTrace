"""Prompt 7 — FDA OOS investigation workflow engine.

Exercises the two-phase FDA 2006 OOS framework: Phase I laboratory triage (assignable-cause →
invalidate-and-retest vs escalate), Phase II full-scale investigation (five root-cause categories,
the invalidation rule, regulatory reporting), and the single-call orchestrator that assembles a
QA-ready Investigation Report carrying every FDA OOS + ICH Q10 element.
"""

from __future__ import annotations

from moltrace.regulatory.quality import (
    AnalyticalResult,
    BatchRecord,
    InvestigationReport,
    OOSDecision,
    Phase1Findings,
    Phase2Findings,
    RegulatoryActionType,
    RootCauseCategory,
    SpecificationLimit,
    initiate_phase1_investigation,
    initiate_phase2_investigation,
    run_oos_investigation,
)

# A 98.0–102.0% assay spec breached by a 96.5% result.
_LIMIT = SpecificationLimit(parameter="Assay", unit="%", lower=98.0, upper=102.0)
_RESULT = AnalyticalResult(
    test_name="Assay",
    reported_value=96.5,
    unit="%",
    batch_id="B-2026-014",
    product_name="Examplinib 250 mg tablets",
    analyst_id="A-17",
    test_date="2026-06-10",
)
_BATCH = BatchRecord(
    batch_id="B-2026-014",
    product_name="Examplinib 250 mg tablets",
    is_distributed=True,
    application_type="ANDA",
)


# --------------------------------------------------------------------------- #
# SpecificationLimit
# --------------------------------------------------------------------------- #
def test_specification_limit_is_oos() -> None:
    two_sided = SpecificationLimit("Assay", "%", lower=98.0, upper=102.0)
    assert two_sided.is_oos(96.5) is True
    assert two_sided.is_oos(103.0) is True
    assert two_sided.is_oos(100.0) is False
    upper_only = SpecificationLimit("Total impurities", "%", upper=0.5)
    assert upper_only.is_oos(0.6) is True
    assert upper_only.is_oos(0.4) is False
    assert "NMT 0.5" in upper_only.describe()


# --------------------------------------------------------------------------- #
# Phase I
# --------------------------------------------------------------------------- #
def test_phase1_in_spec_result_is_not_oos() -> None:
    in_spec = AnalyticalResult("Assay", 100.2, "%", "B1", "Prod", analyst_id="A-1")
    p1 = initiate_phase1_investigation(in_spec, _LIMIT, "A-1")
    assert p1.is_oos is False
    assert p1.decision is OOSDecision.NOT_OOS
    assert p1.is_assignable_cause_found is False


def test_phase1_without_findings_is_pending_and_escalates() -> None:
    p1 = initiate_phase1_investigation(_RESULT, _LIMIT, "A-17")
    assert p1.is_oos is True
    assert {s.status for s in p1.steps} == {"pending"}
    assert len(p1.steps) == 4  # the 4 FDA IV.B steps
    assert p1.decision is OOSDecision.PHASE2_REQUIRED  # nothing ruled out yet
    assert p1.is_assignable_cause_found is False


def test_phase1_assignable_lab_cause_invalidates_and_retests() -> None:
    findings = Phase1Findings(assessed=True, calculation_error=True, notes="wrong dilution factor")
    p1 = initiate_phase1_investigation(_RESULT, _LIMIT, "A-17", findings=findings)
    assert p1.is_assignable_cause_found is True
    assert "calculation error" in p1.assignable_cause
    assert "wrong dilution factor" in p1.assignable_cause
    assert p1.decision is OOSDecision.RETEST_AFTER_ASSIGNABLE_CAUSE
    assert p1.requires_phase2 is False
    # the analyst-error step is flagged fail, the others pass/complete
    by_name = {s.name: s for s in p1.steps}
    assert by_name["Analyst error check (calculation / transcription)"].status == "fail"
    assert by_name["Instrument calibration verification"].status == "pass"


def test_phase1_no_lab_cause_escalates_to_phase2() -> None:
    clean = Phase1Findings(
        assessed=True
    )  # all conservative defaults: no error, calibrated, ok prep
    p1 = initiate_phase1_investigation(_RESULT, _LIMIT, "A-17", findings=clean)
    assert p1.is_assignable_cause_found is False
    assert p1.decision is OOSDecision.PHASE2_REQUIRED
    assert p1.requires_phase2 is True
    assert all(s.status in {"pass", "complete"} for s in p1.steps)


# --------------------------------------------------------------------------- #
# Phase II
# --------------------------------------------------------------------------- #
def _escalated_phase1() -> object:
    return initiate_phase1_investigation(
        _RESULT, _LIMIT, "A-17", findings=Phase1Findings(assessed=True)
    )


def test_phase2_measurement_artifact_invalidates_result() -> None:
    p1 = _escalated_phase1()
    findings = Phase2Findings(
        assessed=True,
        expanded_lab_reproduces_oos=False,
        assignable_cause_category=RootCauseCategory.ANALYST_ERROR,
        cause_is_measurement_artifact=True,
        retest_values=(99.8, 100.1),
    )
    p2 = initiate_phase2_investigation(p1, _BATCH, findings=findings)
    assert p2.is_invalidated is True
    assert p2.decision is OOSDecision.INVALIDATED
    assert p2.root_cause_category is RootCauseCategory.ANALYST_ERROR
    # invalidated result → no Field Alert, just an APR entry
    assert RegulatoryActionType.FIELD_ALERT not in p2.regulatory_actions
    assert RegulatoryActionType.ANNUAL_PRODUCT_REVIEW in p2.regulatory_actions


def test_phase2_manufacturing_defect_confirms_oos_and_files_field_alert() -> None:
    p1 = _escalated_phase1()
    batch = BatchRecord(
        batch_id="B-2026-014",
        product_name="Examplinib 250 mg tablets",
        is_distributed=True,
        application_type="ANDA",
        manufacturing_deviations=("blend uniformity excursion at step 4",),
    )
    findings = Phase2Findings(
        assessed=True,
        assignable_cause_category=RootCauseCategory.MANUFACTURING_ERROR,
        cause_is_measurement_artifact=False,
    )
    p2 = initiate_phase2_investigation(p1, batch, findings=findings)
    assert p2.is_invalidated is False
    assert p2.decision is OOSDecision.CONFIRMED_OOS
    # confirmed OOS on a distributed ANDA batch → Field Alert + APR
    assert RegulatoryActionType.FIELD_ALERT in p2.regulatory_actions
    assert RegulatoryActionType.ANNUAL_PRODUCT_REVIEW in p2.regulatory_actions
    assert p2.capa  # CAPA assigned


def test_phase2_unexplained_oos_cannot_be_invalidated() -> None:
    p1 = _escalated_phase1()
    findings = Phase2Findings(assessed=True, assignable_cause_category=None)
    p2 = initiate_phase2_investigation(p1, _BATCH, findings=findings)
    assert p2.root_cause_category is RootCauseCategory.UNEXPLAINED_OUTLIER
    assert p2.is_invalidated is False
    assert p2.decision is OOSDecision.CONFIRMED_OOS
    assert "cannot be invalidated" in p2.root_cause_statement


def test_phase2_spec_change_adds_supplement_and_nondistributed_skips_field_alert() -> None:
    p1 = _escalated_phase1()
    batch = BatchRecord(
        batch_id="B-2026-014",
        product_name="Examplinib 250 mg tablets",
        is_distributed=False,  # not distributed → no Field Alert
        application_type="ANDA",
    )
    findings = Phase2Findings(
        assessed=True,
        assignable_cause_category=RootCauseCategory.RAW_MATERIAL,
        cause_is_measurement_artifact=False,
        spec_or_method_change_required=True,
    )
    p2 = initiate_phase2_investigation(p1, batch, findings=findings)
    assert RegulatoryActionType.FIELD_ALERT not in p2.regulatory_actions
    assert RegulatoryActionType.NDA_ANDA_SUPPLEMENT in p2.regulatory_actions


def test_phase2_without_findings_is_pending() -> None:
    p1 = _escalated_phase1()
    p2 = initiate_phase2_investigation(p1, _BATCH)
    assert p2.decision is OOSDecision.PHASE2_REQUIRED
    assert all(s.status in {"pending"} for s in p2.steps if s.name.startswith("Expanded"))
    assert p2.is_invalidated is False


# --------------------------------------------------------------------------- #
# Single-call orchestrator + Investigation Report
# --------------------------------------------------------------------------- #
def test_run_investigation_produces_complete_qa_ready_report() -> None:
    report = run_oos_investigation(
        _RESULT,
        _LIMIT,
        "A-17",
        _BATCH,
        phase1_findings=Phase1Findings(assessed=True),  # no lab cause → Phase II runs
        phase2_findings=Phase2Findings(
            assessed=True,
            assignable_cause_category=RootCauseCategory.MANUFACTURING_ERROR,
            cause_is_measurement_artifact=False,
        ),
    )
    assert isinstance(report, InvestigationReport)
    assert report.is_complete is True
    assert report.phase2 is not None  # Phase II ran in the same call
    assert report.final_decision is OOSDecision.CONFIRMED_OOS
    assert report.qa_review_status == "pending QA review"  # engine never self-approves
    assert report.ich_q10_elements  # ICH Q10 elements present
    assert RegulatoryActionType.FIELD_ALERT in report.regulatory_actions


def test_report_markdown_carries_all_required_sections() -> None:
    report = run_oos_investigation(
        _RESULT,
        _LIMIT,
        "A-17",
        _BATCH,
        phase1_findings=Phase1Findings(assessed=True),
        phase2_findings=Phase2Findings(
            assessed=True,
            assignable_cause_category=RootCauseCategory.MANUFACTURING_ERROR,
            cause_is_measurement_artifact=False,
        ),
    )
    md = report.as_markdown()
    for heading in (
        "Triggering OOS result",
        "Phase I — laboratory investigation",
        "Phase II — full-scale investigation",
        "Final disposition",
        "Regulatory actions",
        "CAPA",
        "ICH Q10",
        "QA review & disposition",
    ):
        assert heading in md, heading
    assert "FDA 2006 Guidance" in md
    assert "pending QA review" in md


def test_report_dict_round_trips_the_decision_logic() -> None:
    report = run_oos_investigation(
        _RESULT, _LIMIT, "A-17", _BATCH, phase1_findings=Phase1Findings(assessed=True)
    )
    payload = report.as_dict()
    assert payload["final_decision"] == report.final_decision.value
    assert payload["phase1"]["is_oos"] is True
    assert payload["phase2"]["root_cause_category"] == "unexplained_or_statistical_outlier"
    assert payload["qa_review_status"] == "pending QA review"
    assert len(payload["ich_q10_elements"]) == 5


def test_run_investigation_short_circuits_on_assignable_lab_cause() -> None:
    report = run_oos_investigation(
        _RESULT,
        _LIMIT,
        "A-17",
        _BATCH,
        phase1_findings=Phase1Findings(assessed=True, transcription_error=True),
    )
    assert report.final_decision is OOSDecision.RETEST_AFTER_ASSIGNABLE_CAUSE
    assert report.phase2 is None  # no full-scale investigation needed
    assert "invalidated" in report.disposition_statement
    assert report.is_complete is True


def test_run_investigation_on_in_spec_result_needs_no_investigation() -> None:
    in_spec = AnalyticalResult("Assay", 100.0, "%", "B-1", "Prod", analyst_id="A-1")
    report = run_oos_investigation(in_spec, _LIMIT, "A-1", _BATCH)
    assert report.final_decision is OOSDecision.NOT_OOS
    assert report.phase2 is None
    assert report.regulatory_actions == ()
