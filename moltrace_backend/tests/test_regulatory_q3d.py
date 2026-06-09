"""Worked-example tests for the ICH Q3D(R2) elemental-impurity engine (Prompt 3).

Reproduces ICH Q3D(R2) Table A.2.1 **exactly** for all 24 elements across the
encoded oral / parenteral / inhalation routes, the 30%-of-PDE control thresholds,
the Option-1 permitted-concentration arithmetic, and the class-driven risk
assessment. Verifies the cutaneous / transcutaneous routes are an explicit
"not encoded" (never a guessed PDE), unknown elements fail loud, and the regulated
numbers clear the Phase 0 zero-tolerance calculation gate.

The expected PDEs below are an INDEPENDENT transcription of ICH Q3D(R2) Table A.2.1
(not an import of the module's own table) so the test actually pins the regulatory
ground truth.
"""

from __future__ import annotations

import pytest

from moltrace.regulatory.impurities import (
    calculate_concentration_limit,
    get_element_pde,
    q3d_rule_set,
    risk_assessment_report,
)
from moltrace.regulatory.infra.eval import CalculationCheck, enforce_zero_calculation_errors
from moltrace.regulatory.infra.validation import DataValidationError

# --------------------------------------------------------------------------- #
# Independent ground truth: ICH Q3D(R2) Table A.2.1 PDEs (microg/day).
# symbol -> (class, oral, parenteral, inhalation)
# --------------------------------------------------------------------------- #
_PDE = {
    # Class 1
    "As": ("1", 15.0, 15.0, 2.0),
    "Cd": ("1", 5.0, 2.0, 3.0),
    "Hg": ("1", 30.0, 3.0, 1.0),
    "Pb": ("1", 5.0, 5.0, 5.0),
    # Class 2A
    "Co": ("2A", 50.0, 5.0, 3.0),
    "Ni": ("2A", 200.0, 20.0, 5.0),
    "V": ("2A", 100.0, 10.0, 1.0),
    # Class 2B
    "Ag": ("2B", 150.0, 15.0, 7.0),
    "Au": ("2B", 300.0, 300.0, 3.0),
    "Ir": ("2B", 100.0, 10.0, 1.0),
    "Os": ("2B", 100.0, 10.0, 1.0),
    "Pd": ("2B", 100.0, 10.0, 1.0),
    "Pt": ("2B", 100.0, 10.0, 1.0),
    "Rh": ("2B", 100.0, 10.0, 1.0),
    "Ru": ("2B", 100.0, 10.0, 1.0),
    "Se": ("2B", 150.0, 80.0, 130.0),
    "Tl": ("2B", 8.0, 8.0, 8.0),
    # Class 3
    "Ba": ("3", 1400.0, 700.0, 300.0),
    "Cr": ("3", 11000.0, 1100.0, 3.0),
    "Cu": ("3", 3000.0, 300.0, 30.0),
    "Li": ("3", 550.0, 250.0, 25.0),
    "Mo": ("3", 3000.0, 1500.0, 10.0),
    "Sb": ("3", 1200.0, 90.0, 20.0),
    "Sn": ("3", 6000.0, 600.0, 60.0),
}
_ROUTES = ("oral", "parenteral", "inhalation")
_COL = {"oral": 1, "parenteral": 2, "inhalation": 3}  # index into _PDE tuple

_CASES = [
    (sym, route, _PDE[sym][_COL[route]], _PDE[sym][0]) for sym in _PDE for route in _ROUTES
]


# --------------------------------------------------------------------------- #
# Reproduce ICH Q3D(R2) Table A.2.1 exactly (24 elements x 3 routes = 72 PDEs)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "symbol, route, expected_pde, expected_class",
    _CASES,
    ids=[f"{s}-{r}" for (s, r, _p, _c) in _CASES],
)
def test_q3d_table_a21_reproduced_exactly(symbol, route, expected_pde, expected_class):
    p = get_element_pde(symbol, route)
    assert p.pde_ug_per_day == expected_pde
    assert p.element_class == expected_class
    assert p.route_data_available is True


def test_table_has_24_elements_and_class_counts():
    elements = q3d_rule_set()["elements"]
    assert len(elements) == 24
    counts: dict[str, int] = {}
    for e in elements:
        counts[e["element_class"]] = counts.get(e["element_class"], 0) + 1
    assert counts == {"1": 4, "2A": 3, "2B": 10, "3": 7}


# --------------------------------------------------------------------------- #
# Control threshold = 30% of the PDE (the spec's Table A.2.1 control-threshold check)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "symbol, route, expected_pde, expected_class",
    _CASES,
    ids=[f"{s}-{r}" for (s, r, _p, _c) in _CASES],
)
def test_control_threshold_is_30pct_of_pde(symbol, route, expected_pde, expected_class):
    p = get_element_pde(symbol, route)
    assert p.control_threshold_ug_per_day == pytest.approx(0.30 * expected_pde)


def test_named_control_threshold_values():
    # Worked control thresholds (30% of PDE).
    assert get_element_pde("Pb", "oral").control_threshold_ug_per_day == pytest.approx(1.5)
    assert get_element_pde("As", "oral").control_threshold_ug_per_day == pytest.approx(4.5)
    assert get_element_pde("Cr", "oral").control_threshold_ug_per_day == pytest.approx(3300.0)
    assert get_element_pde("Ni", "parenteral").control_threshold_ug_per_day == pytest.approx(6.0)


# --------------------------------------------------------------------------- #
# Permitted concentration = PDE / max daily dose (ICH Q3D Option 1)
# --------------------------------------------------------------------------- #
def test_concentration_limit_option1():
    # As parenteral PDE 15 microg/day at 2 g/day -> 7.5 ppm; control 30% -> 2.25 ppm.
    cl = calculate_concentration_limit("As", "parenteral", 2.0)
    assert cl.permitted_concentration_ppm == pytest.approx(7.5)
    assert cl.control_threshold_ppm == pytest.approx(2.25)
    assert cl.route_data_available is True


def test_concentration_limit_scales_inversely_with_dose():
    # Pb oral PDE 5 microg/day: at 1 g -> 5 ppm; at 10 g -> 0.5 ppm.
    assert calculate_concentration_limit("Pb", "oral", 1.0).permitted_concentration_ppm == 5.0
    assert calculate_concentration_limit("Pb", "oral", 10.0).permitted_concentration_ppm == 0.5


def test_concentration_limit_rejects_nonpositive_dose():
    with pytest.raises(DataValidationError):
        calculate_concentration_limit("Pb", "oral", 0.0)
    with pytest.raises(DataValidationError):
        calculate_concentration_limit("Pb", "oral", -1.0)


# --------------------------------------------------------------------------- #
# Lookup by symbol + name, case-insensitive
# --------------------------------------------------------------------------- #
def test_lookup_by_symbol_and_name():
    assert get_element_pde("arsenic", "oral").element == "As"
    assert get_element_pde("LEAD", "oral").element == "Pb"
    assert get_element_pde("pb", "oral").element == "Pb"
    assert get_element_pde(" Cadmium ", "oral").element == "Cd"


def test_unknown_element_fails_loud():
    with pytest.raises(DataValidationError):
        get_element_pde("Fe", "oral")  # iron is not an ICH Q3D-listed element
    with pytest.raises(DataValidationError):
        get_element_pde("unobtanium", "oral")


# --------------------------------------------------------------------------- #
# Cutaneous / transcutaneous: explicit "not encoded", never a guessed PDE
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("route", ["cutaneous", "transcutaneous"])
def test_cutaneous_route_is_explicit_not_encoded(route):
    p = get_element_pde("As", route)
    assert p.route_data_available is False
    assert p.pde_ug_per_day is None
    assert p.control_threshold_ug_per_day is None
    assert any("cutaneous" in n.lower() for n in p.notes)
    # The class is still known even when the route PDE is not encoded.
    assert p.element_class == "1"


def test_cutaneous_concentration_limit_is_none():
    cl = calculate_concentration_limit("Pb", "cutaneous", 1.0)
    assert cl.permitted_concentration_ppm is None
    assert cl.control_threshold_ppm is None
    assert cl.route_data_available is False


def test_unsupported_route_fails_loud():
    with pytest.raises(DataValidationError):
        get_element_pde("Pb", "topical")


# --------------------------------------------------------------------------- #
# Risk assessment: class-driven likelihood + source attribution
# --------------------------------------------------------------------------- #
def test_risk_assessment_covers_all_24_elements():
    ra = risk_assessment_report({"API": 100.0}, [], "oral", 0.5)
    assert len(ra.elements) == 24
    assert ra.route == "oral"
    assert ra.route_data_available is True


def test_class1_and_2a_always_assessed():
    ra = risk_assessment_report({"API": 100.0}, [], "oral", 0.5)
    by = {it.element: it for it in ra.elements}
    for sym in ("As", "Cd", "Hg", "Pb", "Co", "Ni", "V"):
        assert by[sym].likely_present is True
        assert by[sym].assessment_required is True
        assert by[sym].exclusion_applies is False


def test_class2b_excluded_unless_intentionally_added():
    # No catalysts, no equipment -> noble metals excluded.
    ra = risk_assessment_report({"API": 100.0}, [], "oral", 0.5)
    by = {it.element: it for it in ra.elements}
    for sym in ("Pd", "Pt", "Ir", "Os", "Rh", "Ru", "Au", "Ag"):
        assert by[sym].likely_present is False
        assert by[sym].exclusion_applies is True


def test_class2b_assessed_when_intentionally_added():
    ra = risk_assessment_report(
        {"API": 99.0, "Palladium on carbon catalyst": 1.0}, [], "oral", 0.5
    )
    pd = next(it for it in ra.elements if it.element == "Pd")
    assert pd.likely_present is True
    assert pd.assessment_required is True
    assert any("intentional addition" in s.lower() for s in pd.potential_sources)


def test_equipment_sourcing_via_alloy_kb():
    ra = risk_assessment_report({"API": 100.0}, ["316L stainless steel reactor"], "oral", 0.5)
    by = {it.element: it for it in ra.elements}
    for sym in ("Cr", "Ni", "Mo"):
        assert by[sym].likely_present is True
        assert any("equipment" in s.lower() for s in by[sym].potential_sources)


def test_class3_route_dependent():
    # Oral: a Class 3 element with no source is excludable.
    oral = risk_assessment_report({"API": 100.0}, [], "oral", 0.5)
    sn_oral = next(it for it in oral.elements if it.element == "Sn")
    assert sn_oral.exclusion_applies is True
    assert sn_oral.likely_present is False
    # Parenteral: the same Class 3 element must be assessed.
    par = risk_assessment_report({"API": 100.0}, [], "parenteral", 0.5)
    sn_par = next(it for it in par.elements if it.element == "Sn")
    assert sn_par.assessment_required is True
    assert sn_par.likely_present is True


def test_risk_assessment_carries_permitted_concentration():
    ra = risk_assessment_report({"API": 100.0}, [], "parenteral", 2.0)
    pb = next(it for it in ra.elements if it.element == "Pb")
    # Pb parenteral PDE 5 microg/day / 2 g -> 2.5 ppm.
    assert pb.permitted_concentration_ppm == pytest.approx(2.5)
    assert pb.control_threshold_ug_per_day == pytest.approx(1.5)


def test_risk_assessment_cutaneous_route_has_no_limits():
    ra = risk_assessment_report({"API": 100.0}, [], "cutaneous", 1.0)
    assert ra.route_data_available is False
    assert all(it.permitted_concentration_ppm is None for it in ra.elements)
    assert any("cutaneous" in n.lower() for n in ra.notes)


# --------------------------------------------------------------------------- #
# Foundation integration: regulated PDEs clear the zero-tolerance gate
# --------------------------------------------------------------------------- #
def test_pdes_pass_zero_calculation_error_gate():
    checks = []
    for sym, route, expected_pde, _cls in _CASES:
        p = get_element_pde(sym, route)
        checks.append(CalculationCheck(f"q3d_{sym}_{route}", p.pde_ug_per_day, expected_pde))
    enforce_zero_calculation_errors(checks)  # raises HardGateError on any mismatch


# --------------------------------------------------------------------------- #
# Traceability + determinism
# --------------------------------------------------------------------------- #
def test_pde_is_citation_tagged():
    p = get_element_pde("Pb", "oral")
    assert p.regulatory_basis.startswith("ICH Q3D(R2)")
    assert p.table_reference == "ICH Q3D(R2) Table A.2.1"
    assert p.rule_set_version.startswith("sha256:")
    assert any("decision-support" in n.lower() for n in p.notes)


def test_result_is_deterministic():
    assert get_element_pde("Pb", "oral").content_hash() == get_element_pde("Pb", "oral").content_hash()
    assert q3d_rule_set() == q3d_rule_set()
    a = risk_assessment_report({"API": 100.0}, ["316L"], "oral", 0.5).content_hash()
    b = risk_assessment_report({"API": 100.0}, ["316L"], "oral", 0.5).content_hash()
    assert a == b
