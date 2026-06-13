"""Prompt 21 Phase 7 — regulatory validation suite + GAMP 5 CSV package.

Worked-example zero-error proof for every formula, Hypothesis property tests asserting ICH
invariants, FDA NDSRI + EMA Q&A reproductions, formula->citation completeness (untraceable fails the
build), the auto-assembled CSV package with the expert sign-off slot, and the launch gate.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from moltrace.regulatory.infra.eval import calculation_errors, enforce_zero_calculation_errors
from moltrace.regulatory.validation import (
    CitationError,
    ExpertSignOff,
    build_csv_package,
    enforce_launch_gate,
    enforce_traceable_formulas,
    evaluate_launch_gate,
    formula_citation_map,
    launch_gate_exit_code,
    run_property_invariants,
    run_worked_examples,
    untraceable_formulas,
    validate_ema_qa,
    validate_ndsri,
    worked_example_checks,
)
from moltrace.regulatory.validation import citation_map as cm
from moltrace.regulatory.validation.property_invariants import (
    _Q3D_ELEMENTS,
    _VALID_SMILES,
    assert_cpca_cumulative_strict_rule,
    assert_m7_class_valid,
    assert_q3ab_thresholds_well_formed,
    assert_q3d_permitted_inverse_monotonic_in_dose,
)


# --------------------------------------------------------------------------- #
# 1. Worked examples — zero calculation errors for every formula
# --------------------------------------------------------------------------- #
def test_worked_examples_are_zero_error() -> None:
    results = run_worked_examples()
    errors = [e for r in results for e in calculation_errors(r.numeric_checks)]
    equality = [f for r in results for f in r.equality_failures]
    unresolved = [u for r in results for u in r.unresolved]
    assert not errors, [f"{e.name}: {e.computed} != {e.expected}" for e in errors[:10]]
    assert not equality, equality[:10]
    assert not unresolved, unresolved[:10]
    enforce_zero_calculation_errors(worked_example_checks(results))  # the hard gate


def test_worked_examples_cover_every_calculator() -> None:
    calculators = {r.calculator for r in run_worked_examples()}
    assert calculators == {"q3ab", "q3c", "q3d", "m7", "cpca"}


# --------------------------------------------------------------------------- #
# 2. Hypothesis property-based tests — ICH invariants over random valid inputs
# --------------------------------------------------------------------------- #
@settings(max_examples=200, deadline=None)
@given(
    dose=st.floats(min_value=1e-4, max_value=50.0, allow_nan=False, allow_infinity=False),
    substance=st.sampled_from(["drug_substance", "drug_product"]),
)
def test_property_q3ab_thresholds_well_formed(dose: float, substance: str) -> None:
    assert_q3ab_thresholds_well_formed(dose, substance)


@settings(max_examples=120, deadline=None)
@given(
    element=st.sampled_from(_Q3D_ELEMENTS),
    a=st.floats(min_value=0.01, max_value=20.0, allow_nan=False, allow_infinity=False),
    b=st.floats(min_value=0.01, max_value=20.0, allow_nan=False, allow_infinity=False),
)
def test_property_q3d_permitted_inverse_monotonic(element: str, a: float, b: float) -> None:
    assert_q3d_permitted_inverse_monotonic_in_dose(element, "oral", min(a, b), max(a, b))


@settings(max_examples=30, deadline=None)
@given(smiles=st.sampled_from(_VALID_SMILES))
def test_property_m7_class_always_valid(smiles: str) -> None:
    assert_m7_class_valid(smiles)


@settings(max_examples=40, deadline=None)
@given(
    smiles=st.sampled_from(_VALID_SMILES[:4]),
    measured=st.floats(min_value=0.1, max_value=5000.0, allow_nan=False, allow_infinity=False),
)
def test_property_cpca_cumulative_strict_rule(smiles: str, measured: float) -> None:
    assert_cpca_cumulative_strict_rule(smiles, measured)


def test_property_invariants_hold_on_deterministic_grid() -> None:
    results = run_property_invariants()
    assert results
    failed = [(i.name, i.failures) for i in results if not i.passed]
    assert not failed, failed


# --------------------------------------------------------------------------- #
# 3. External validation sets — FDA NDSRI + EMA Q&A reproduced exactly
# --------------------------------------------------------------------------- #
def test_ndsri_limits_reproduced_exactly() -> None:
    result = validate_ndsri()
    assert result.ok, result.category_failures
    assert result.n_compounds >= 4
    assert all(not c.is_error() for c in result.ai_limit_checks)


def test_ema_qa_limits_reproduced_exactly() -> None:
    result = validate_ema_qa()
    assert result.ok, result.category_failures


# --------------------------------------------------------------------------- #
# 4. Formula -> citation map (untraceable formula fails the build)
# --------------------------------------------------------------------------- #
def test_formula_citation_map_is_complete() -> None:
    assert untraceable_formulas() == []
    enforce_traceable_formulas()  # does not raise
    mapping = formula_citation_map()
    assert mapping["q3c_residual_solvent_pde"].guideline == "ICH Q3C(R8)"
    assert mapping["q3d_elemental_pde"].effective_date == "2022"
    assert all(c.is_traceable() for c in mapping.values())


def test_untraceable_formula_fails_the_build(monkeypatch) -> None:
    orphan = cm.FormulaCitation(
        "orphan_formula", guideline="", section_or_table="", effective_date=""
    )
    assert not orphan.is_traceable()
    base = cm.formula_citation_map()
    monkeypatch.setattr(cm, "formula_citation_map", lambda: {**base, "orphan_formula": orphan})
    assert "orphan_formula" in cm.untraceable_formulas()
    with pytest.raises(CitationError):
        cm.enforce_traceable_formulas()


# --------------------------------------------------------------------------- #
# 5. GAMP 5 CSV package + expert sign-off slot
# --------------------------------------------------------------------------- #
def test_csv_package_assembles_with_pending_sign_off() -> None:
    pkg = build_csv_package(rule_set_version="sha256:deadbeef")
    assert "Formula → Citation Map" in pkg.document
    assert "Independent Regulatory-Affairs Expert Audit" in pkg.document
    assert pkg.sign_off.hours_budgeted == 40
    assert pkg.sign_off.is_signed is False
    assert "PENDING" in pkg.document
    assert pkg.launch_gate.passed  # the suite is green
    assert pkg.formula_citations["m7_class"].guideline.startswith("ICH M7")


def test_csv_package_captures_signed_expert_audit() -> None:
    sign_off = ExpertSignOff(
        reviewer_id="QA-Jane-Doe", outcome="approved", signed_date="2026-06-12"
    )
    pkg = build_csv_package(rule_set_version="sha256:deadbeef", sign_off=sign_off)
    assert pkg.sign_off.is_signed
    assert "QA-Jane-Doe" in pkg.document
    assert "approved" in pkg.document
    assert "SIGNED" in pkg.document


# --------------------------------------------------------------------------- #
# 6. Launch gate — fully green before go-live
# --------------------------------------------------------------------------- #
def test_launch_gate_is_fully_green() -> None:
    result = evaluate_launch_gate()
    assert result.passed, result.failed_checks()
    assert launch_gate_exit_code() == 0
    enforce_launch_gate()  # does not raise


def test_launch_gate_covers_all_validation_dimensions() -> None:
    names = {c.name for c in evaluate_launch_gate().checks}
    assert {
        "worked_examples",
        "formula_citation_map",
        "property_invariants",
        "external_ndsri",
        "external_ema",
    } <= names
