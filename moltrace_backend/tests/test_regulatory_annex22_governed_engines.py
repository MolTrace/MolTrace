"""Prompt 12 finalization — Annex 22 governance bound to every Prompt 4–8 decision function.

Verifies the full governance wrap across P4–P8: a completeness gate (every P4–P8 decision has a
governed binding, and the gate fails if one is removed), each governed engine records an
Annex-22-compliant, hash-chained, explainable decision, high-risk decisions block until human
review, M7 risk is dynamic (mutagenic → high, otherwise low), and governance never alters the
deterministic engine's output. Everything runs offline.
"""

from __future__ import annotations

import pytest

from moltrace.regulatory.compliance import (
    REQUIRED_P4_P8_DECISIONS,
    Annex22GovernanceError,
    annex22_compliance_checklist,
    assert_full_p4_p8_governance,
    ungoverned_p4_p8,
)
from moltrace.regulatory.compliance.annex22_wrapper import Annex22Log, governance_context
from moltrace.regulatory.compliance.governed_engines import (
    GOVERNED_ENGINES,
    governed_build_specification,
    governed_calculate_cumulative_risk,
    governed_classify_cpca,
    governed_classify_m7,
    governed_generate_3p5_impurities,
    governed_generate_3s3_impurities_drug_substance,
    governed_run_oos_investigation,
)
from moltrace.regulatory.ctd import ImpurityEntry, ImpurityOrigin, ImpurityProfile
from moltrace.regulatory.impurities import (
    calculate_q3ab_thresholds,
    classify_cpca,
    classify_m7,
)
from moltrace.regulatory.quality import AnalyticalResult, BatchRecord, SpecificationLimit
from moltrace.regulatory.specifications import (
    BatchResult,
    ImpurityObservation,
    MethodValidation,
    SubstanceProfile,
)

_EMS = "CCOS(=O)(=O)C"  # ethyl methanesulfonate — mutagenic (ICH M7)
_NDMA = "CN(C)N=O"  # N-nitrosodimethylamine — Cohort of Concern


# --------------------------------------------------------------------------- #
# Fixtures that drive each P4–P8 engine with valid inputs
# --------------------------------------------------------------------------- #
def _ctd_inputs():
    q3ab = calculate_q3ab_thresholds(1.0, "drug_substance", "oral")
    profile = ImpurityProfile(
        "Reference Substance",
        impurities=(
            ImpurityEntry(
                "Process impurity A",
                origin=ImpurityOrigin.PROCESS_RELATED,
                observed_levels_percent=(0.04,),
            ),
            ImpurityEntry(
                "Mutagenic alert impurity",
                structure_smiles=_EMS,
                origin=ImpurityOrigin.PROCESS_RELATED,
                observed_levels_percent=(0.0005,),
            ),
        ),
    )
    return profile, q3ab


def _invoke_each_engine() -> dict[str, object]:
    """Call every governed engine once, returning ``{decision_type: GovernedResult}``."""

    substance = SubstanceProfile(name="API", substance_type="drug_substance", max_daily_dose_g=1.0)
    profile, q3ab = _ctd_inputs()
    mv = MethodValidation(validated_methods=frozenset({"assay_hplc", "dissolution", "water_kf"}))
    q6a_profile = SubstanceProfile(
        name="API",
        substance_type="drug_substance",
        impurities=(ImpurityObservation("EMS", structural_assignment=_EMS),),
    )
    limit = SpecificationLimit(parameter="Assay", unit="%", lower=98.0, upper=102.0)
    oos_result = AnalyticalResult(
        test_name="Assay",
        reported_value=96.5,
        unit="%",
        batch_id="B-1",
        product_name="Examplinib",
        analyst_id="A-1",
        test_date="2026-06-14",
    )
    batch_record = BatchRecord(
        batch_id="B-1", product_name="Examplinib", is_distributed=True, application_type="ANDA"
    )
    batches = [BatchResult("B1", total_impurities_percent=0.30)]
    return {
        "m7_classification": governed_classify_m7(_EMS),
        "cpca_classification": governed_classify_cpca(_NDMA),
        "cpca_cumulative_risk": governed_calculate_cumulative_risk([(_NDMA, 50.0)]),
        "q6a_specification": governed_build_specification(q6a_profile, [], mv),
        "oos_investigation": governed_run_oos_investigation(oos_result, limit, "A-1", batch_record),
        "ctd_module3_3s3": governed_generate_3s3_impurities_drug_substance(substance, profile, q3ab),
        "ctd_module3_3p5": governed_generate_3p5_impurities(
            profile, q3ab, [classify_m7(_EMS)], [classify_cpca(_NDMA)], batches
        ),
    }


# --------------------------------------------------------------------------- #
# Completeness gate — every P4–P8 function carries a governed binding
# --------------------------------------------------------------------------- #
def test_completeness_gate_covers_all_p4_p8() -> None:
    assert ungoverned_p4_p8() == []
    assert_full_p4_p8_governance()  # does not raise
    assert set(GOVERNED_ENGINES) == set(REQUIRED_P4_P8_DECISIONS)
    # the seven P4–P8 decisions
    assert set(REQUIRED_P4_P8_DECISIONS) == {
        "m7_classification",
        "cpca_classification",
        "cpca_cumulative_risk",
        "q6a_specification",
        "oos_investigation",
        "ctd_module3_3s3",
        "ctd_module3_3p5",
    }


def test_completeness_gate_fails_if_a_binding_is_missing() -> None:
    partial = {k: v for k, v in GOVERNED_ENGINES.items() if k != "oos_investigation"}
    assert ungoverned_p4_p8(partial) == ["oos_investigation"]
    with pytest.raises(Annex22GovernanceError, match="oos_investigation"):
        assert_full_p4_p8_governance(partial)


# --------------------------------------------------------------------------- #
# Every governed engine records a compliant, chained, explainable decision
# --------------------------------------------------------------------------- #
def test_every_p4_p8_engine_records_a_compliant_chained_decision() -> None:
    log = Annex22Log()
    with governance_context("validator", log):
        results = _invoke_each_engine()

    # one governed result per required decision type, each tagged with the right decision_type
    assert set(results) == set(REQUIRED_P4_P8_DECISIONS)
    for decision_type, governed in results.items():
        record = governed.record
        assert record.decision_type == decision_type
        assert record.user_id == "validator"
        assert record.confidence == 1.0  # deterministic engines
        assert record.feature_attribution  # explainability present (Annex 22)
        checklist = annex22_compliance_checklist(record)
        assert all(checklist.values()), (decision_type, checklist)

    # the whole batch forms one tamper-evident hash chain
    ok, breaks = log.verify_chain()
    assert ok, breaks
    assert len(log.records()) == len(REQUIRED_P4_P8_DECISIONS)


# --------------------------------------------------------------------------- #
# Risk behavior: dynamic M7, high-risk blocks until review, medium passes through
# --------------------------------------------------------------------------- #
def test_m7_risk_is_dynamic() -> None:
    log = Annex22Log()
    with governance_context("validator", log):
        mutagenic = governed_classify_m7(_EMS)  # class 1–3 -> high
        benign = governed_classify_m7("CCO")  # ethanol -> class 5 -> low
    assert mutagenic.record.risk_level == "high" and mutagenic.is_blocked
    assert benign.record.risk_level == "low" and not benign.is_blocked


def test_high_risk_blocks_until_human_review() -> None:
    log = Annex22Log()
    with governance_context("validator", log):
        governed = governed_classify_cpca(_NDMA)  # always high-risk
    assert governed.status == "pending" and governed.is_blocked
    with pytest.raises(Exception):  # noqa: B017 - Annex22PendingError on a blocked unwrap
        governed.unwrap()
    log.submit_review(governed.record.entry_hash, reviewer_id="tox-1", approved=True)
    assert log.is_approved(governed.record.entry_hash)


def test_ctd_is_medium_risk_and_passes_through() -> None:
    log = Annex22Log()
    substance = SubstanceProfile(name="API", substance_type="drug_substance", max_daily_dose_g=1.0)
    profile, q3ab = _ctd_inputs()
    with governance_context("validator", log):
        governed = governed_generate_3s3_impurities_drug_substance(substance, profile, q3ab)
    assert governed.status == "approved" and not governed.is_blocked
    assert governed.unwrap().section_number == "3.2.S.3.2"  # the real CTD output passes through


def test_governance_does_not_alter_the_engine_decision() -> None:
    # the governed record's output equals the bare engine's output — governance only documents
    bare = classify_cpca(_NDMA)
    log = Annex22Log()
    with governance_context("validator", log):
        governed = governed_classify_cpca(_NDMA)
    assert governed.record.output == bare.as_dict()
    # and the bare engine still returns its result object directly (governance is opt-in)
    assert bare.category == classify_cpca(_NDMA).category
