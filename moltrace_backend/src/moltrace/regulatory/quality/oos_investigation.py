"""FDA OOS investigation workflow engine (Prompt 7).

Implements the two-phase framework of FDA's 2006 guidance *Investigating Out-of-Specification (OOS)
Test Results for Pharmaceutical Production*:

* **Phase I — laboratory investigation** (guidance Section IV.B): is the OOS the product of an
  assignable *laboratory* cause (calculation/transcription error, instrument out of calibration,
  faulty sample preparation)? A documented lab cause invalidates the original result and triggers a
  reanalysis; otherwise the investigation escalates.
* **Phase II — full-scale investigation** (guidance Section V): expanded laboratory work plus a
  manufacturing-process review and, where justified by a *pre-defined* protocol, retesting (never
  testing into compliance). A root cause is assigned to one of five categories and an invalidation
  decision is taken. An OOS may be invalidated **only** with a documented assignable cause; an
  unexplained OOS stands, the batch fails, and regulatory reporting is triggered.

:func:`run_oos_investigation` runs both phases and assembles a single
:class:`InvestigationReport` carrying every FDA OOS + ICH Q10 element, ready for QA review. The
engine is decision support: it records findings, applies the guidance decision logic, and proposes
actions — the quality unit owns the final disposition and signs the report.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "AnalyticalResult",
    "BatchRecord",
    "InvestigationReport",
    "InvestigationStep",
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

_GUIDANCE = "FDA 2006 Guidance: Investigating OOS Test Results for Pharmaceutical Production"


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class OOSDecision(StrEnum):
    """Disposition reached at the close of an investigation phase."""

    NOT_OOS = "not_oos"  # result within specification — no investigation warranted
    RETEST_AFTER_ASSIGNABLE_CAUSE = (
        "retest_after_assignable_cause"  # Phase I lab cause → invalidate
    )
    PHASE2_REQUIRED = "phase2_required"  # no Phase I lab cause → full-scale investigation
    INVALIDATED = "invalidated"  # Phase II assignable cause → original result invalidated
    CONFIRMED_OOS = "confirmed_oos"  # no valid assignable cause → result stands, batch fails


class RootCauseCategory(StrEnum):
    """The five FDA OOS root-cause categories (guidance Section V)."""

    MANUFACTURING_ERROR = "manufacturing_error"
    EQUIPMENT_FAILURE = "equipment_failure"
    RAW_MATERIAL = "raw_material"
    ANALYST_ERROR = "analyst_error"
    UNEXPLAINED_OUTLIER = "unexplained_or_statistical_outlier"


# Categories whose cause is a measurement artefact (the batch quality is not in question), so the
# original OOS may be invalidated. The remaining categories mean the product itself is affected.
_LAB_ATTRIBUTABLE = frozenset(
    {RootCauseCategory.ANALYST_ERROR, RootCauseCategory.EQUIPMENT_FAILURE}
)


class RegulatoryActionType(StrEnum):
    """Regulatory follow-up that a confirmed OOS may oblige."""

    FIELD_ALERT = "field_alert_report"  # 21 CFR 314.81(b)(1) — within 3 working days, NDA/ANDA
    ANNUAL_PRODUCT_REVIEW = "annual_product_review_entry"  # 21 CFR 211.180(e)
    NDA_ANDA_SUPPLEMENT = "nda_anda_supplement"  # spec/method change requiring a supplement


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AnalyticalResult:
    """An analytical test result that breached (or may have breached) a specification."""

    test_name: str
    reported_value: float
    unit: str
    batch_id: str
    product_name: str
    analyst_id: str = ""
    test_date: str = ""
    replicate_values: tuple[float, ...] = ()


@dataclass(frozen=True)
class SpecificationLimit:
    """A one- or two-sided acceptance criterion for a parameter (e.g. an ICH Q6A spec row)."""

    parameter: str
    unit: str = ""
    lower: float | None = None
    upper: float | None = None
    source: str = "ICH Q6A specification"

    def is_oos(self, value: float) -> bool:
        """True when *value* falls outside the acceptance criterion."""

        if self.lower is not None and value < self.lower:
            return True
        if self.upper is not None and value > self.upper:
            return True
        return False

    def describe(self) -> str:
        if self.lower is not None and self.upper is not None:
            return f"{self.lower:g}–{self.upper:g} {self.unit}".strip()
        if self.lower is not None:
            return f"NLT {self.lower:g} {self.unit}".strip()
        if self.upper is not None:
            return f"NMT {self.upper:g} {self.unit}".strip()
        return "no numeric limit defined"


@dataclass(frozen=True)
class BatchRecord:
    """The manufacturing context a Phase II investigation reviews."""

    batch_id: str
    product_name: str
    is_distributed: bool = False
    application_type: str = "none"  # "NDA" | "ANDA" | "none"
    manufacturing_deviations: tuple[str, ...] = ()
    equipment_log_findings: tuple[str, ...] = ()
    raw_material_lots: tuple[str, ...] = ()


@dataclass(frozen=True)
class Phase1Findings:
    """Outcomes the analyst/QC records while working the Phase I checklist.

    All flags are conservative defaults (no error / properly calibrated / acceptable prep) so an
    investigation opened without findings reports every step as *pending* rather than implying a
    clean result.
    """

    assessed: bool = False
    calculation_error: bool = False
    transcription_error: bool = False
    instrument_calibrated: bool = True
    sample_prep_acceptable: bool = True
    notes: str = ""


@dataclass(frozen=True)
class Phase2Findings:
    """Outcomes recorded during the full-scale (Phase II) investigation."""

    assessed: bool = False
    expanded_lab_reproduces_oos: bool = True
    assignable_cause_category: RootCauseCategory | None = None
    cause_is_measurement_artifact: bool = False
    retest_values: tuple[float, ...] = ()
    spec_or_method_change_required: bool = False
    notes: str = ""


# --------------------------------------------------------------------------- #
# Outputs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class InvestigationStep:
    """One checklist step with its status and finding."""

    name: str
    guidance_reference: str
    status: str  # "pending" | "pass" | "fail" | "complete"
    finding: str = ""


@dataclass(frozen=True)
class Phase1Investigation:
    """The Phase I laboratory investigation record."""

    investigation_id: str
    result: AnalyticalResult
    specification_limit: SpecificationLimit
    analyst_id: str
    is_oos: bool
    steps: tuple[InvestigationStep, ...]
    is_assignable_cause_found: bool
    assignable_cause: str
    decision: OOSDecision
    next_action: str

    @property
    def requires_phase2(self) -> bool:
        return self.decision is OOSDecision.PHASE2_REQUIRED


@dataclass(frozen=True)
class Phase2Investigation:
    """The Phase II full-scale investigation record."""

    phase1: Phase1Investigation
    steps: tuple[InvestigationStep, ...]
    root_cause_category: RootCauseCategory
    root_cause_statement: str
    retest_summary: str
    is_invalidated: bool
    invalidation_justification: str
    decision: OOSDecision
    regulatory_actions: tuple[RegulatoryActionType, ...]
    capa: tuple[str, ...]


@dataclass(frozen=True)
class InvestigationReport:
    """A complete OOS Investigation Report carrying the FDA OOS + ICH Q10 elements.

    ``as_markdown()`` renders the QA-review document; ``as_dict()`` gives the structured payload for
    persistence or an API. ``qa_review_status`` is ``"pending QA review"`` until the quality unit
    signs — the engine never self-approves.
    """

    investigation_id: str
    product_name: str
    batch_id: str
    triggering_result: AnalyticalResult
    specification_limit: SpecificationLimit
    phase1: Phase1Investigation
    phase2: Phase2Investigation | None
    final_decision: OOSDecision
    disposition_statement: str
    regulatory_actions: tuple[RegulatoryActionType, ...]
    capa: tuple[str, ...]
    ich_q10_elements: tuple[str, ...]
    qa_review_status: str = "pending QA review"
    guidance_basis: str = _GUIDANCE

    @property
    def is_complete(self) -> bool:
        """Every guidance element is present and the report is ready to hand to QA."""

        return bool(
            self.investigation_id
            and self.phase1.steps
            and self.disposition_statement
            and self.ich_q10_elements
        )

    def as_dict(self) -> dict:
        def step(s: InvestigationStep) -> dict:
            return {
                "name": s.name,
                "guidance_reference": s.guidance_reference,
                "status": s.status,
                "finding": s.finding,
            }

        return {
            "investigation_id": self.investigation_id,
            "product_name": self.product_name,
            "batch_id": self.batch_id,
            "guidance_basis": self.guidance_basis,
            "triggering_result": {
                "test": self.triggering_result.test_name,
                "reported_value": self.triggering_result.reported_value,
                "unit": self.triggering_result.unit,
                "analyst_id": self.triggering_result.analyst_id,
                "test_date": self.triggering_result.test_date,
            },
            "specification": {
                "parameter": self.specification_limit.parameter,
                "limit": self.specification_limit.describe(),
                "source": self.specification_limit.source,
            },
            "phase1": {
                "is_oos": self.phase1.is_oos,
                "steps": [step(s) for s in self.phase1.steps],
                "is_assignable_cause_found": self.phase1.is_assignable_cause_found,
                "assignable_cause": self.phase1.assignable_cause,
                "decision": self.phase1.decision.value,
                "next_action": self.phase1.next_action,
            },
            "phase2": None
            if self.phase2 is None
            else {
                "steps": [step(s) for s in self.phase2.steps],
                "root_cause_category": self.phase2.root_cause_category.value,
                "root_cause_statement": self.phase2.root_cause_statement,
                "retest_summary": self.phase2.retest_summary,
                "is_invalidated": self.phase2.is_invalidated,
                "invalidation_justification": self.phase2.invalidation_justification,
            },
            "final_decision": self.final_decision.value,
            "disposition_statement": self.disposition_statement,
            "regulatory_actions": [a.value for a in self.regulatory_actions],
            "capa": list(self.capa),
            "ich_q10_elements": list(self.ich_q10_elements),
            "qa_review_status": self.qa_review_status,
        }

    def as_markdown(self) -> str:
        res = self.triggering_result
        lines: list[str] = [
            f"# OOS Investigation Report — {self.investigation_id}",
            "",
            f"- **Product:** {self.product_name}",
            f"- **Batch:** {self.batch_id}",
            f"- **Guidance basis:** {self.guidance_basis}",
            f"- **QA review status:** {self.qa_review_status}",
            "",
            "## 1. Triggering OOS result",
            f"- **Test:** {res.test_name}",
            f"- **Reported value:** {res.reported_value:g} {res.unit}",
            f"- **Specification ({self.specification_limit.source}):** "
            f"{self.specification_limit.describe()}",
            f"- **Analyst:** {res.analyst_id or 'n/a'}  |  **Date:** {res.test_date or 'n/a'}",
            f"- **OOS confirmed against specification:** {'yes' if self.phase1.is_oos else 'no'}",
            "",
            "## 2. Phase I — laboratory investigation (FDA OOS Section IV.B)",
        ]
        for s in self.phase1.steps:
            lines.append(f"- [{s.status}] **{s.name}** ({s.guidance_reference}) — {s.finding}")
        lines += [
            f"- **Assignable laboratory cause found:** "
            f"{'yes' if self.phase1.is_assignable_cause_found else 'no'}"
            + (f" — {self.phase1.assignable_cause}" if self.phase1.assignable_cause else ""),
            f"- **Phase I decision:** {self.phase1.decision.value}",
            f"- **Next action:** {self.phase1.next_action}",
            "",
        ]
        if self.phase2 is not None:
            lines.append("## 3. Phase II — full-scale investigation (FDA OOS Section V)")
            for s in self.phase2.steps:
                lines.append(f"- [{s.status}] **{s.name}** ({s.guidance_reference}) — {s.finding}")
            lines += [
                f"- **Root-cause category:** {self.phase2.root_cause_category.value}",
                f"- **Root-cause statement:** {self.phase2.root_cause_statement}",
                f"- **Retesting:** {self.phase2.retest_summary}",
                f"- **Original result invalidated:** "
                f"{'yes' if self.phase2.is_invalidated else 'no'} — "
                f"{self.phase2.invalidation_justification}",
                "",
            ]
        lines += [
            "## 4. Final disposition",
            f"- **Decision:** {self.final_decision.value}",
            f"- {self.disposition_statement}",
            "",
            "## 5. Regulatory actions",
        ]
        if self.regulatory_actions:
            lines += [f"- {a.value}" for a in self.regulatory_actions]
        else:
            lines.append("- none required")
        lines += ["", "## 6. CAPA (ICH Q10 corrective & preventive action)"]
        lines += [f"- {c}" for c in self.capa] or ["- none assigned"]
        lines += ["", "## 7. ICH Q10 pharmaceutical quality system elements"]
        lines += [f"- {e}" for e in self.ich_q10_elements]
        lines += [
            "",
            "## 8. QA review & disposition",
            f"- **Status:** {self.qa_review_status}",
            "- **Reviewed by (quality unit):** ____________________  **Date:** __________",
            "- **Final batch disposition:** ____________________",
        ]
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Phase I
# --------------------------------------------------------------------------- #
def initiate_phase1_investigation(
    test_result: AnalyticalResult,
    specification_limit: SpecificationLimit,
    analyst_id: str,
    *,
    findings: Phase1Findings | None = None,
    investigation_id: str | None = None,
) -> Phase1Investigation:
    """Phase I laboratory investigation (FDA 2006 OOS guidance, Section IV.B).

    Steps:
      1. Check for an obvious analyst error (calculation, transcription).
      2. Verify instrument calibration at the time of test.
      3. Review the sample-preparation record.
      4. Retain the original sample/preparation for a possible Phase II.

    Decision: when an assignable *laboratory* cause is documented the original result is invalidated
    and a reanalysis is ordered; otherwise the investigation escalates to Phase II. Supplying
    ``findings`` records the step outcomes and resolves the decision in one call; without them the
    record is returned with every step *pending* for the analyst to complete.
    """

    inv_id = investigation_id or f"OOS-{test_result.batch_id}-{test_result.test_name}".replace(
        " ", "_"
    )
    is_oos = specification_limit.is_oos(test_result.reported_value)
    f = findings

    if not is_oos:
        steps = (
            InvestigationStep(
                "Confirm result against specification",
                "FDA OOS IV.A",
                "pass",
                f"{test_result.reported_value:g} {test_result.unit} is within "
                f"{specification_limit.describe()} — not an OOS.",
            ),
        )
        return Phase1Investigation(
            investigation_id=inv_id,
            result=test_result,
            specification_limit=specification_limit,
            analyst_id=analyst_id,
            is_oos=False,
            steps=steps,
            is_assignable_cause_found=False,
            assignable_cause="",
            decision=OOSDecision.NOT_OOS,
            next_action="No OOS investigation required; record the in-specification result.",
        )

    def status(ok: bool | None) -> str:
        if f is None or not f.assessed:
            return "pending"
        return "pass" if ok else "fail"

    assessed = f is not None and f.assessed
    calc_ok = f is None or not (f.calculation_error or f.transcription_error)
    cal_ok = f is None or f.instrument_calibrated
    prep_ok = f is None or f.sample_prep_acceptable

    def finding(ok: bool, *, ok_text: str, fail_text: str, todo_text: str) -> str:
        if not assessed:
            return todo_text
        return ok_text if ok else fail_text

    steps = (
        InvestigationStep(
            "Analyst error check (calculation / transcription)",
            "FDA OOS IV.B.1",
            status(calc_ok),
            finding(
                calc_ok,
                ok_text="no calculation or transcription error",
                fail_text="calculation/transcription error identified",
                todo_text="review raw data, integrations and calculations",
            ),
        ),
        InvestigationStep(
            "Instrument calibration verification",
            "FDA OOS IV.B.2",
            status(cal_ok),
            finding(
                cal_ok,
                ok_text="instrument within calibration at time of test",
                fail_text="instrument out of calibration",
                todo_text="confirm calibration status and system suitability",
            ),
        ),
        InvestigationStep(
            "Sample preparation record review",
            "FDA OOS IV.B.2",
            status(prep_ok),
            finding(
                prep_ok,
                ok_text="sample preparation acceptable",
                fail_text="sample-preparation error identified",
                todo_text="review weighing, dilution and standards/reagents",
            ),
        ),
        InvestigationStep(
            "Retain original sample/preparation for possible Phase II",
            "FDA OOS IV.B.3",
            "complete" if f and f.assessed else "pending",
            "original sample retained pending the outcome of the laboratory phase",
        ),
    )

    if f is None or not f.assessed:
        return Phase1Investigation(
            investigation_id=inv_id,
            result=test_result,
            specification_limit=specification_limit,
            analyst_id=analyst_id,
            is_oos=True,
            steps=steps,
            is_assignable_cause_found=False,
            assignable_cause="",
            decision=OOSDecision.PHASE2_REQUIRED,
            next_action=(
                "Phase I checklist opened — record findings for each step; escalate to Phase II if "
                "no assignable laboratory cause is identified."
            ),
        )

    causes: list[str] = []
    if f.calculation_error:
        causes.append("calculation error")
    if f.transcription_error:
        causes.append("transcription error")
    if not f.instrument_calibrated:
        causes.append("instrument out of calibration")
    if not f.sample_prep_acceptable:
        causes.append("sample-preparation error")
    assignable = bool(causes)
    cause_text = "; ".join(causes)
    if f.notes:
        cause_text = f"{cause_text} ({f.notes})" if cause_text else f.notes

    if assignable:
        decision = OOSDecision.RETEST_AFTER_ASSIGNABLE_CAUSE
        next_action = (
            "Document the assignable laboratory cause, invalidate the original result, and "
            "reanalyse the retained sample per an approved procedure (FDA OOS IV.B)."
        )
    else:
        decision = OOSDecision.PHASE2_REQUIRED
        next_action = (
            "No assignable laboratory cause identified — escalate to a Phase II full-scale "
            "investigation (FDA OOS Section V)."
        )

    return Phase1Investigation(
        investigation_id=inv_id,
        result=test_result,
        specification_limit=specification_limit,
        analyst_id=analyst_id,
        is_oos=True,
        steps=steps,
        is_assignable_cause_found=assignable,
        assignable_cause=cause_text,
        decision=decision,
        next_action=next_action,
    )


# --------------------------------------------------------------------------- #
# Phase II
# --------------------------------------------------------------------------- #
def initiate_phase2_investigation(
    phase1_result: Phase1Investigation,
    batch_record: BatchRecord,
    *,
    findings: Phase2Findings | None = None,
) -> Phase2Investigation:
    """Phase II full-scale investigation (FDA 2006 OOS guidance, Section V).

    Covers the expanded laboratory investigation (additional samples/analysts), a manufacturing
    process review, and retesting under a pre-defined protocol (never testing into compliance). A
    root cause is assigned to one of the five categories (manufacturing error, equipment failure,
    raw material, analyst, unexplained/statistical outlier) and an invalidation decision is taken: a
    result may be invalidated **only** with a documented assignable cause that shows the OOS is a
    measurement artefact; an unexplained OOS — or one caused by a genuine product defect — stands,
    the batch fails, and regulatory reporting is triggered.
    """

    f = findings or Phase2Findings()
    assessed = f.assessed

    # Root cause: prefer an explicit finding, else infer from the batch record, else unexplained.
    if f.assignable_cause_category is not None:
        category = f.assignable_cause_category
    elif batch_record.manufacturing_deviations:
        category = RootCauseCategory.MANUFACTURING_ERROR
    elif batch_record.equipment_log_findings:
        category = RootCauseCategory.EQUIPMENT_FAILURE
    else:
        category = RootCauseCategory.UNEXPLAINED_OUTLIER

    # Invalidation: only a measurement-artefact (lab-attributable) assignable cause invalidates the
    # result. An unexplained outlier can never be invalidated (FDA prohibits outlier-test removal of
    # a chemical OOS); a true product cause means the result is valid and the batch is affected.
    can_invalidate = (
        assessed
        and f.assignable_cause_category is not None
        and category in _LAB_ATTRIBUTABLE
        and f.cause_is_measurement_artifact
    )

    retest_summary = (
        f"retest values {', '.join(f'{v:g}' for v in f.retest_values)} obtained under a "
        "pre-defined protocol (no testing into compliance)"
        if f.retest_values
        else "retesting per a pre-defined protocol only where an assignable cause justifies it; "
        "testing into compliance is prohibited"
    )

    deviation_text = (
        "; ".join(batch_record.manufacturing_deviations)
        if batch_record.manufacturing_deviations
        else "no manufacturing deviation recorded"
    )
    equip_text = (
        "; ".join(batch_record.equipment_log_findings)
        if batch_record.equipment_log_findings
        else "no equipment anomaly recorded"
    )

    steps = (
        InvestigationStep(
            "Expanded laboratory investigation (additional samples / analysts)",
            "FDA OOS V.A",
            "complete" if assessed else "pending",
            (
                "expanded testing reproduces the OOS"
                if f.expanded_lab_reproduces_oos
                else "expanded testing does not reproduce the OOS"
            )
            if assessed
            else "second analyst to re-test the original preparation and a fresh aliquot",
        ),
        InvestigationStep(
            "Manufacturing process review",
            "FDA OOS V.A",
            "complete" if assessed else "pending",
            deviation_text,
        ),
        InvestigationStep(
            "Equipment & raw-material review",
            "FDA OOS V.A",
            "complete" if assessed else "pending",
            f"{equip_text}; raw-material lots: "
            + (", ".join(batch_record.raw_material_lots) or "none recorded"),
        ),
        InvestigationStep(
            "Retesting per pre-defined protocol",
            "FDA OOS V.B",
            "complete" if f.retest_values else "pending",
            retest_summary,
        ),
        InvestigationStep(
            "Root-cause determination (5 categories)",
            "FDA OOS Section V",
            "complete" if assessed else "pending",
            f"assigned: {category.value}",
        ),
    )

    if not assessed:
        root_statement = (
            "Phase II opened — complete the expanded laboratory and manufacturing review and "
            "assign a root cause before a disposition is taken."
        )
        decision = OOSDecision.PHASE2_REQUIRED
        invalidation_just = "pending — no disposition until the investigation is complete"
        reg_actions: tuple[RegulatoryActionType, ...] = ()
        capa: tuple[str, ...] = (
            "Complete the Phase II investigation and assign corrective/preventive actions to the "
            "confirmed root cause.",
        )
    elif can_invalidate:
        decision = OOSDecision.INVALIDATED
        root_statement = (
            f"Assignable cause ({category.value}) shows the OOS is a measurement artefact "
            "that does not reflect true batch quality."
        )
        invalidation_just = (
            "Documented assignable laboratory/measurement cause per FDA OOS Section V — original "
            "result invalidated and superseded by the valid (in-specification) reanalysis."
        )
        reg_actions = (RegulatoryActionType.ANNUAL_PRODUCT_REVIEW,)
        capa = _capa_for(category, invalidated=True)
    else:
        decision = OOSDecision.CONFIRMED_OOS
        if category is RootCauseCategory.UNEXPLAINED_OUTLIER:
            root_statement = (
                "No assignable cause identified. The OOS cannot be invalidated (an outlier test "
                "cannot remove a chemical OOS); the result stands and the batch fails."
            )
            invalidation_just = (
                "Not invalidated — no documented assignable cause; FDA prohibits invalidating an "
                "unexplained OOS."
            )
        else:
            root_statement = (
                f"Confirmed product-affecting root cause ({category.value}); the OOS reflects true "
                "batch quality. The result is valid and the batch fails."
            )
            invalidation_just = (
                "Not invalidated — the assignable cause affects the product itself, not the "
                "measurement."
            )
        reg_actions = _regulatory_actions(batch_record, f.spec_or_method_change_required)
        capa = _capa_for(category, invalidated=False)

    return Phase2Investigation(
        phase1=phase1_result,
        steps=steps,
        root_cause_category=category,
        root_cause_statement=root_statement,
        retest_summary=retest_summary,
        is_invalidated=can_invalidate,
        invalidation_justification=invalidation_just,
        decision=decision,
        regulatory_actions=reg_actions,
        capa=capa,
    )


def _regulatory_actions(
    batch_record: BatchRecord, spec_change_required: bool
) -> tuple[RegulatoryActionType, ...]:
    """Regulatory follow-up a confirmed OOS obliges, given batch distribution + application."""

    actions = [RegulatoryActionType.ANNUAL_PRODUCT_REVIEW]
    if batch_record.is_distributed and batch_record.application_type.upper() in {"NDA", "ANDA"}:
        # 21 CFR 314.81(b)(1): a confirmed OOS on a distributed batch → Field Alert within 3 days.
        actions.insert(0, RegulatoryActionType.FIELD_ALERT)
    if spec_change_required:
        actions.append(RegulatoryActionType.NDA_ANDA_SUPPLEMENT)
    return tuple(actions)


def _capa_for(category: RootCauseCategory, *, invalidated: bool) -> tuple[str, ...]:
    """Corrective + preventive actions appropriate to the assigned root cause (ICH Q10)."""

    base: dict[RootCauseCategory, tuple[str, ...]] = {
        RootCauseCategory.MANUFACTURING_ERROR: (
            "Correct the deviating manufacturing step and re-qualify the process.",
            "Reinforce in-process controls and operator training to prevent recurrence.",
        ),
        RootCauseCategory.EQUIPMENT_FAILURE: (
            "Repair/recalibrate the affected equipment and verify performance.",
            "Tighten the preventive-maintenance and calibration schedule.",
        ),
        RootCauseCategory.RAW_MATERIAL: (
            "Quarantine the implicated raw-material lot and assess affected batches.",
            "Strengthen incoming-material specifications and supplier qualification.",
        ),
        RootCauseCategory.ANALYST_ERROR: (
            "Retrain the analyst and reinforce the procedure/calculation review.",
            "Add a second-person verification of the calculation/transcription step.",
        ),
        RootCauseCategory.UNEXPLAINED_OUTLIER: (
            "Reject the batch; no scientific basis exists to invalidate the result.",
            "Trend the unexplained OOS in the PQS and review related batches for a signal.",
        ),
    }
    actions = base[category]
    if not invalidated and category is not RootCauseCategory.UNEXPLAINED_OUTLIER:
        actions = (*actions, "Assess the impact on other batches and the validated state.")
    return actions


# --------------------------------------------------------------------------- #
# Orchestrator — single-call Investigation Report
# --------------------------------------------------------------------------- #
_ICH_Q10_ELEMENTS: tuple[str, ...] = (
    "ICH Q10 §3.2.2 — CAPA system: corrective and preventive actions assigned to the root cause.",
    "ICH Q10 §3.2.1 — process performance & product quality monitoring: OOS captured as a quality "
    "signal for trending.",
    "ICH Q10 §3.2.3 — change management: any spec/method change routed through change control.",
    "ICH Q10 §3.2.4 / §3.1 — management review: confirmed OOS and CAPA escalated to senior "
    "management for the PQS review.",
    "ICH Q10 §1.6 — knowledge management: the investigation outcome retained to inform future "
    "risk assessment.",
)


def run_oos_investigation(
    test_result: AnalyticalResult,
    specification_limit: SpecificationLimit,
    analyst_id: str,
    batch_record: BatchRecord,
    *,
    phase1_findings: Phase1Findings | None = None,
    phase2_findings: Phase2Findings | None = None,
    investigation_id: str | None = None,
) -> InvestigationReport:
    """Run the full FDA OOS workflow and assemble a single QA-ready Investigation Report.

    Phase I runs first; Phase II runs automatically when Phase I finds no assignable laboratory
    cause. The returned :class:`InvestigationReport` carries every FDA OOS + ICH Q10 element and is
    marked *pending QA review* — the quality unit signs the final disposition.
    """

    phase1 = initiate_phase1_investigation(
        test_result,
        specification_limit,
        analyst_id,
        findings=phase1_findings,
        investigation_id=investigation_id,
    )

    phase2: Phase2Investigation | None = None
    if phase1.requires_phase2:
        phase2 = initiate_phase2_investigation(phase1, batch_record, findings=phase2_findings)

    # Roll the two phases up into a single disposition.
    if phase1.decision is OOSDecision.NOT_OOS:
        final = OOSDecision.NOT_OOS
        disposition = (
            "Result is within specification; no OOS exists and no further action is required."
        )
        reg_actions: tuple[RegulatoryActionType, ...] = ()
        capa: tuple[str, ...] = ()
    elif phase1.decision is OOSDecision.RETEST_AFTER_ASSIGNABLE_CAUSE:
        final = OOSDecision.RETEST_AFTER_ASSIGNABLE_CAUSE
        disposition = (
            f"Phase I identified an assignable laboratory cause ({phase1.assignable_cause}); the "
            "original result is invalidated and the sample is reanalysed under an approved "
            "procedure. No full-scale investigation required."
        )
        reg_actions = (RegulatoryActionType.ANNUAL_PRODUCT_REVIEW,)
        capa = (
            "Correct and document the laboratory error; reinforce the analyst procedure and "
            "second-person calculation review.",
        )
    elif phase2 is not None:
        final = phase2.decision
        disposition = f"{phase2.root_cause_statement} {phase2.invalidation_justification}"
        reg_actions = phase2.regulatory_actions
        capa = phase2.capa
    else:  # pragma: no cover — defensive; requires_phase2 implies phase2 is built above
        final = OOSDecision.PHASE2_REQUIRED
        disposition = "Phase II full-scale investigation required."
        reg_actions = ()
        capa = ()

    return InvestigationReport(
        investigation_id=phase1.investigation_id,
        product_name=test_result.product_name,
        batch_id=test_result.batch_id,
        triggering_result=test_result,
        specification_limit=specification_limit,
        phase1=phase1,
        phase2=phase2,
        final_decision=final,
        disposition_statement=disposition,
        regulatory_actions=reg_actions,
        capa=capa,
        ich_q10_elements=_ICH_Q10_ELEMENTS,
        qa_review_status="pending QA review",
    )
