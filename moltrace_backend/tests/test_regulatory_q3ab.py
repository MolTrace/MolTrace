"""Worked-example tests for the ICH Q3A(R2)/Q3B(R2) threshold calculator (Prompt 1).

Reproduces the published ICH Q3A(R2) and Q3B(R2) Attachment-1 threshold tables
**exactly** across every dose band and boundary, verifies the "whichever is lower"
resolution, and confirms the calculator's regulated numbers pass the Phase 0
zero-tolerance calculation-error gate. ICH calculations are deterministic, so an
error here is a code bug with regulatory consequences — this suite is exhaustive
by design.
"""

from __future__ import annotations

import pytest

from moltrace.regulatory.impurities import calculate_q3ab_thresholds, q3ab_rule_set
from moltrace.regulatory.infra.eval import CalculationCheck, enforce_zero_calculation_errors
from moltrace.regulatory.infra.validation import DataValidationError


def _triple(daily_dose_g, substance_type):
    t = calculate_q3ab_thresholds(daily_dose_g, substance_type)
    return (
        t.reporting_threshold.effective_percent,
        t.identification_threshold.effective_percent,
        t.qualification_threshold.effective_percent,
    )


# --------------------------------------------------------------------------- #
# ICH Q3A(R2) — drug substances, Attachment 1
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "dose_g, expected",
    [
        (0.5, (0.05, 0.10, 0.15)),  # % rules bind (1.0 mg = 0.2% > rule)
        (1.0, (0.05, 0.10, 0.10)),  # qual capped by 1.0 mg/day (= 0.10%)
        (2.0, (0.05, 0.05, 0.05)),  # boundary: 1.0 mg/day = 0.05% caps id + qual
        (2.0001, (0.03, 0.05, 0.05)),  # just over 2 g -> > 2 g band
        (3.0, (0.03, 0.05, 0.05)),
    ],
)
def test_q3a_table1_reproduced_exactly(dose_g, expected):
    assert _triple(dose_g, "drug_substance") == pytest.approx(expected)


def test_q3a_whichever_lower_flags_binding_absolute():
    # At 2 g/day the 1.0 mg/day cap (0.05%) is the binding identification limit.
    t = calculate_q3ab_thresholds(2.0, "drug_substance")
    assert t.identification_threshold.absolute_is_binding is True
    assert t.identification_threshold.absolute_cap == 1.0
    assert t.identification_threshold.absolute_unit == "mg_per_day"
    # At 0.5 g/day the percentage rule binds (1.0 mg = 0.2% > 0.10%).
    t2 = calculate_q3ab_thresholds(0.5, "drug_substance")
    assert t2.identification_threshold.absolute_is_binding is False


# --------------------------------------------------------------------------- #
# ICH Q3B(R2) — drug products, Attachment 1
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "dose_g, expected",
    [
        (0.0005, (0.1, 1.0, 1.0)),  # 0.5 mg: ID <1mg (5 ug = 1.0%), qual <10mg
        (0.001, (0.1, 0.5, 1.0)),  # 1 mg boundary -> ID 1-10mg band; qual <10mg
        (0.01, (0.1, 0.2, 0.5)),  # 10 mg: ID 1-10mg capped by 20 ug (0.2%); qual 10-100mg rule
        (0.05, (0.1, 0.2, 0.4)),  # 50 mg: ID >10mg, qual 10-100mg capped by 200 ug (0.4%)
        (0.2, (0.1, 0.2, 0.2)),  # 200 mg: ID >10mg, qual >100mg
        (2.0, (0.05, 0.10, 0.15)),  # 2 g boundary: mg-TDI caps bind to 0.10% / 0.15%
        (2.0001, (0.05, 0.10, 0.15)),  # just over 2 g -> flat > 2 g band
        (3.0, (0.05, 0.10, 0.15)),
    ],
)
def test_q3b_table1_reproduced_exactly(dose_g, expected):
    assert _triple(dose_g, "drug_product") == pytest.approx(expected)


def test_q3b_identification_band_boundaries():
    # <1mg vs 1-10mg
    assert calculate_q3ab_thresholds(0.000999, "drug_product").identification_threshold.dose_band == (
        "maximum daily dose < 1 mg"
    )
    assert calculate_q3ab_thresholds(0.001, "drug_product").identification_threshold.dose_band == (
        "maximum daily dose 1 mg to 10 mg"
    )
    # 1-10mg vs >10mg-2g
    assert calculate_q3ab_thresholds(0.010, "drug_product").identification_threshold.dose_band == (
        "maximum daily dose 1 mg to 10 mg"
    )
    assert calculate_q3ab_thresholds(0.0101, "drug_product").identification_threshold.dose_band == (
        "maximum daily dose > 10 mg to 2 g"
    )
    # >2g
    assert calculate_q3ab_thresholds(2.5, "drug_product").identification_threshold.dose_band == (
        "maximum daily dose > 2 g"
    )


def test_q3b_qualification_band_boundaries():
    assert calculate_q3ab_thresholds(0.009, "drug_product").qualification_threshold.dose_band == (
        "maximum daily dose < 10 mg"
    )
    assert calculate_q3ab_thresholds(0.010, "drug_product").qualification_threshold.dose_band == (
        "maximum daily dose 10 mg to 100 mg"
    )
    assert calculate_q3ab_thresholds(0.101, "drug_product").qualification_threshold.dose_band == (
        "maximum daily dose > 100 mg to 2 g"
    )


# --------------------------------------------------------------------------- #
# 5 representative product/substance dose cases (public, approximate doses).
# Validates the ICH dose->threshold computation, not any filing's impurity limits.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name, dose_g, substance_type, expected",
    [
        ("metformin HCl (substance)", 2.55, "drug_substance", (0.03, 0.05, 0.05)),
        ("amoxicillin (substance)", 3.0, "drug_substance", (0.03, 0.05, 0.05)),
        ("atorvastatin tablet (product)", 0.080, "drug_product", (0.1, 0.2, 0.25)),
        ("levothyroxine tablet (product)", 0.0002, "drug_product", (0.1, 1.0, 1.0)),
        ("sertraline tablet (product)", 0.200, "drug_product", (0.1, 0.2, 0.2)),
    ],
)
def test_representative_product_dose_cases(name, dose_g, substance_type, expected):
    assert _triple(dose_g, substance_type) == pytest.approx(expected), name


# --------------------------------------------------------------------------- #
# Foundation integration: regulated values pass the zero-tolerance gate
# --------------------------------------------------------------------------- #
def test_values_pass_zero_calculation_error_gate():
    # The calculator's outputs must match the ICH ground truth with zero error.
    t = calculate_q3ab_thresholds(1.0, "drug_substance")
    enforce_zero_calculation_errors(
        [
            CalculationCheck("q3a_reporting", t.reporting_threshold.effective_percent, 0.05),
            CalculationCheck("q3a_identification", t.identification_threshold.effective_percent, 0.10),
            CalculationCheck("q3a_qualification", t.qualification_threshold.effective_percent, 0.10),
        ]
    )


# --------------------------------------------------------------------------- #
# Traceability, determinism, validation
# --------------------------------------------------------------------------- #
def test_every_threshold_is_citation_tagged():
    t = calculate_q3ab_thresholds(0.05, "drug_product")
    assert t.regulatory_basis == "ICH Q3B(R2): Impurities in New Drug Products"
    assert t.table_reference == "ICH Q3B(R2) Attachment 1"
    assert t.guidance_effective_year == "2006"
    assert t.rule_set_version.startswith("sha256:")
    for thr in (t.reporting_threshold, t.identification_threshold, t.qualification_threshold):
        assert thr.basis.startswith("ICH Q3B(R2)")
        assert thr.table_reference == "ICH Q3B(R2) Attachment 1"
    assert any("decision-support" in n.lower() for n in t.notes)


def test_result_is_deterministic():
    a = calculate_q3ab_thresholds(1.0, "drug_substance").content_hash()
    b = calculate_q3ab_thresholds(1.0, "drug_substance").content_hash()
    assert a == b
    # rule-set version is stable across calls
    assert q3ab_rule_set() == q3ab_rule_set()


def test_invalid_input_fails_loudly():
    with pytest.raises(DataValidationError):
        calculate_q3ab_thresholds(0.0, "drug_substance")
    with pytest.raises(DataValidationError):
        calculate_q3ab_thresholds(-1.0, "drug_substance")
    with pytest.raises(DataValidationError):
        calculate_q3ab_thresholds(1.0, "neither")
