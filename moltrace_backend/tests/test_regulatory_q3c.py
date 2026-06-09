"""Worked-example tests for the ICH Q3C(R8) residual-solvent classifier (Prompt 2).

Reproduces the ICH Q3C(R8) Class 1/2/3 solvent table **exactly** for the encoded
curated subset (44 solvents) — class assignment, the Class 2/3 permitted daily
exposure (PDE), and the Option-1 concentration limit — and verifies the dose-scaled
Option-2 limit check, name/CAS/SMILES lookup, explicit handling of unknown solvents,
and that the regulated numbers clear the Phase 0 zero-tolerance calculation gate.

The expected values below are an INDEPENDENT transcription of ICH Q3C(R8) (not an
import of the module's own table) so the test actually pins the regulatory ground
truth. Q3C calculations are deterministic; an error here is a code bug with
regulatory consequences, so this suite is exhaustive by design.
"""

from __future__ import annotations

import pytest

from moltrace.regulatory.impurities import (
    check_residual_solvent_limits,
    classify_solvent,
    q3c_rule_set,
)
from moltrace.regulatory.infra.eval import CalculationCheck, enforce_zero_calculation_errors
from moltrace.regulatory.infra.validation import DataValidationError

# --------------------------------------------------------------------------- #
# Independent ground truth: ICH Q3C(R8) Appendices 1-3.
# (name, cas, class, pde_mg_per_day | None, concentration_limit_ppm)
# Class 1: pde is None; concentration_limit_ppm is the ICH limit.
# Class 2/3: concentration_limit_ppm == PDE * 100 (Option 1 at 10 g/day).
# --------------------------------------------------------------------------- #
_CLASS1 = [
    ("Benzene", "71-43-2", 1, None, 2.0),
    ("Carbon tetrachloride", "56-23-5", 1, None, 4.0),
    ("1,2-Dichloroethane", "107-06-2", 1, None, 5.0),
    ("1,1-Dichloroethene", "75-35-4", 1, None, 8.0),
    ("1,1,1-Trichloroethane", "71-55-6", 1, None, 1500.0),
]
_CLASS2 = [
    ("Acetonitrile", "75-05-8", 2, 4.1, 410.0),
    ("Chlorobenzene", "108-90-7", 2, 3.6, 360.0),
    ("Chloroform", "67-66-3", 2, 0.6, 60.0),
    ("Cyclohexane", "110-82-7", 2, 38.8, 3880.0),
    ("Dichloromethane", "75-09-2", 2, 6.0, 600.0),
    ("N,N-Dimethylformamide", "68-12-2", 2, 8.8, 880.0),
    ("1,4-Dioxane", "123-91-1", 2, 3.8, 380.0),
    ("Hexane", "110-54-3", 2, 2.9, 290.0),
    ("Methanol", "67-56-1", 2, 30.0, 3000.0),
    ("2-Methoxyethanol", "109-86-4", 2, 0.5, 50.0),
    ("Methylbutyl ketone", "591-78-6", 2, 0.5, 50.0),
    ("N-Methylpyrrolidone", "872-50-4", 2, 5.3, 530.0),
    ("Nitromethane", "75-52-5", 2, 0.5, 50.0),
    ("Pyridine", "110-86-1", 2, 2.0, 200.0),
    ("Tetrahydrofuran", "109-99-9", 2, 7.2, 720.0),
    ("Toluene", "108-88-3", 2, 8.9, 890.0),
    ("Trichloroethene", "79-01-6", 2, 0.8, 80.0),
    ("Xylene", "1330-20-7", 2, 21.7, 2170.0),
]
_CLASS3 = [
    ("Acetic acid", "64-19-7", 3, 50.0, 5000.0),
    ("Acetone", "67-64-1", 3, 50.0, 5000.0),
    ("Anisole", "100-66-3", 3, 50.0, 5000.0),
    ("1-Butanol", "71-36-3", 3, 50.0, 5000.0),
    ("2-Butanol", "78-92-2", 3, 50.0, 5000.0),
    ("Butyl acetate", "123-86-4", 3, 50.0, 5000.0),
    ("tert-Butylmethyl ether", "1634-04-4", 3, 50.0, 5000.0),
    ("Dimethyl sulfoxide", "67-68-5", 3, 50.0, 5000.0),
    ("Ethanol", "64-17-5", 3, 50.0, 5000.0),
    ("Ethyl acetate", "141-78-6", 3, 50.0, 5000.0),
    ("Ethyl ether", "60-29-7", 3, 50.0, 5000.0),
    ("Heptane", "142-82-5", 3, 50.0, 5000.0),
    ("Isopropyl acetate", "108-21-4", 3, 50.0, 5000.0),
    ("Methyl acetate", "79-20-9", 3, 50.0, 5000.0),
    ("Methylethyl ketone", "78-93-3", 3, 50.0, 5000.0),
    ("Methylisobutyl ketone", "108-10-1", 3, 50.0, 5000.0),
    ("Pentane", "109-66-0", 3, 50.0, 5000.0),
    ("1-Propanol", "71-23-8", 3, 50.0, 5000.0),
    ("2-Propanol", "67-63-0", 3, 50.0, 5000.0),
    ("Propyl acetate", "109-60-4", 3, 50.0, 5000.0),
    ("Triethylamine", "121-44-8", 3, 50.0, 5000.0),
]
_ALL = _CLASS1 + _CLASS2 + _CLASS3


# --------------------------------------------------------------------------- #
# Reproduce the ICH Q3C(R8) table exactly (44 solvents > the 20 required)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name, cas, cls, pde, conc_ppm", _ALL, ids=[r[0] for r in _ALL])
def test_q3c_table_reproduced_exactly(name, cas, cls, pde, conc_ppm):
    c = classify_solvent(name)
    assert c.matched is True
    assert c.solvent_name == name
    assert c.cas_number == cas
    assert c.class_number == cls
    assert c.pde_mg_per_day == pde
    assert c.concentration_limit_ppm == conc_ppm


def test_table_has_expected_population():
    solvents = q3c_rule_set()["solvents"]
    assert len(solvents) == 44
    counts = {1: 0, 2: 0, 3: 0}
    for s in solvents:
        counts[s["class_number"]] += 1
    assert counts == {1: 5, 2: 18, 3: 21}


# --------------------------------------------------------------------------- #
# Named concentration limits at the oral PDE (Option 1) — the spec's 4 targets
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "ident, expected_class, expected_ppm",
    [
        ("ethanol", 3, 5000.0),
        ("methanol", 2, 3000.0),
        ("acetonitrile", 2, 410.0),
        ("dichloromethane", 2, 600.0),
    ],
)
def test_named_concentration_limits(ident, expected_class, expected_ppm):
    c = classify_solvent(ident, route="oral")
    assert c.class_number == expected_class
    assert c.concentration_limit_ppm == expected_ppm
    # Option 1 identity: concentration limit == PDE * 100 (10 g/day reference dose).
    assert c.concentration_limit_ppm == pytest.approx(c.pde_mg_per_day * 100.0)


# --------------------------------------------------------------------------- #
# Lookup by name, CAS number, alias, and SMILES
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name, cas, cls, pde, conc_ppm", _ALL, ids=[r[0] for r in _ALL])
def test_lookup_by_cas(name, cas, cls, pde, conc_ppm):
    assert classify_solvent(cas).solvent_name == name


@pytest.mark.parametrize(
    "alias, expected",
    [
        ("DCM", "Dichloromethane"),
        ("methylene chloride", "Dichloromethane"),
        ("MeOH", "Methanol"),
        ("EtOH", "Ethanol"),
        ("IPA", "2-Propanol"),
        ("isopropanol", "2-Propanol"),
        ("THF", "Tetrahydrofuran"),
        ("NMP", "N-Methylpyrrolidone"),
        ("DMF", "N,N-Dimethylformamide"),
        ("DMSO", "Dimethyl sulfoxide"),
        ("MTBE", "tert-Butylmethyl ether"),
        ("ACN", "Acetonitrile"),
        ("ether", "Ethyl ether"),
    ],
)
def test_lookup_by_alias(alias, expected):
    assert classify_solvent(alias).solvent_name == expected


@pytest.mark.parametrize(
    "smiles, expected",
    [
        ("CO", "Methanol"),
        ("CCO", "Ethanol"),
        ("ClCCl", "Dichloromethane"),
        ("c1ccccc1", "Benzene"),
        ("CC#N", "Acetonitrile"),
        ("CC(C)=O", "Acetone"),
        ("ClC(Cl)Cl", "Chloroform"),
        ("CC(C)O", "2-Propanol"),
    ],
)
def test_lookup_by_smiles(smiles, expected):
    # Non-canonical SMILES input still resolves via RDKit canonicalisation.
    assert classify_solvent(smiles).solvent_name == expected


def test_lookup_is_case_and_spacing_insensitive():
    assert classify_solvent("  METHANOL  ").solvent_name == "Methanol"
    assert classify_solvent("dichloromethane").solvent_name == "Dichloromethane"


# --------------------------------------------------------------------------- #
# Class 1 (avoid) and Class 3 invariants
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name, cas, cls, pde, conc_ppm", _CLASS1, ids=[r[0] for r in _CLASS1])
def test_class1_has_concentration_limit_and_no_pde(name, cas, cls, pde, conc_ppm):
    c = classify_solvent(name)
    assert c.class_number == 1
    assert c.pde_mg_per_day is None
    assert c.concentration_limit_ppm == conc_ppm
    assert "avoid" in c.class_description.lower()


def test_class3_all_share_50mg_pde():
    for name, *_ in _CLASS3:
        c = classify_solvent(name)
        assert c.class_number == 3
        assert c.pde_mg_per_day == 50.0
        assert c.concentration_limit_ppm == 5000.0


# --------------------------------------------------------------------------- #
# Unknown solvent: explicit "unknown", never a guessed limit
# --------------------------------------------------------------------------- #
def test_unknown_solvent_is_explicit_not_guessed():
    c = classify_solvent("unobtainium")
    assert c.matched is False
    assert c.class_number is None
    assert c.pde_mg_per_day is None
    assert c.concentration_limit_ppm is None
    assert any("not found" in n.lower() for n in c.notes)


# --------------------------------------------------------------------------- #
# Compliance: Option 2 dose-scaled limit, pass/fail, margin
# --------------------------------------------------------------------------- #
def test_compliance_option2_dose_scaled():
    # Methanol PDE 30 mg/day at 0.5 g/day dose -> 30*1000/0.5 = 60000 ppm permitted.
    res = check_residual_solvent_limits({"methanol": 3000.0}, daily_dose_g=0.5)
    assert len(res) == 1
    r = res[0]
    assert r.class_number == 2
    assert r.permitted_ppm == pytest.approx(60000.0)
    assert r.passed is True
    assert r.margin_ppm == pytest.approx(57000.0)


def test_compliance_option2_equals_option1_at_10g():
    # At the 10 g/day reference dose, Option 2 reproduces the Option-1 ppm limit.
    res = check_residual_solvent_limits(
        {"acetonitrile": 100.0, "dichloromethane": 100.0}, daily_dose_g=10.0
    )
    by_name = {r.solvent_name: r for r in res}
    assert by_name["Acetonitrile"].permitted_ppm == pytest.approx(410.0)
    assert by_name["Dichloromethane"].permitted_ppm == pytest.approx(600.0)


def test_compliance_fail_with_negative_margin():
    # Class 1 benzene fixed limit 2 ppm; 5 ppm measured fails.
    res = check_residual_solvent_limits({"benzene": 5.0}, daily_dose_g=1.0)
    r = res[0]
    assert r.class_number == 1
    assert r.permitted_ppm == 2.0
    assert r.passed is False
    assert r.margin_ppm == pytest.approx(-3.0)


def test_compliance_class1_uses_fixed_limit_not_dose_scaled():
    # Class 1 limit must not change with dose (it is a fixed concentration limit).
    low = check_residual_solvent_limits({"benzene": 1.0}, daily_dose_g=0.1)[0]
    high = check_residual_solvent_limits({"benzene": 1.0}, daily_dose_g=10.0)[0]
    assert low.permitted_ppm == high.permitted_ppm == 2.0


def test_compliance_unknown_solvent_not_judged():
    res = check_residual_solvent_limits({"unobtainium": 100.0}, daily_dose_g=1.0)
    r = res[0]
    assert r.passed is None
    assert r.permitted_ppm is None
    assert r.class_number is None


def test_compliance_mixed_spec_by_name_and_cas():
    res = check_residual_solvent_limits(
        {"67-56-1": 100.0, "ethanol": 100.0}, daily_dose_g=2.0
    )
    names = {r.solvent_name for r in res}
    assert names == {"Methanol", "Ethanol"}
    assert all(r.passed is True for r in res)


def test_compliance_rejects_nonpositive_dose():
    with pytest.raises(ValueError):
        check_residual_solvent_limits({"methanol": 1.0}, daily_dose_g=0.0)
    with pytest.raises(ValueError):
        check_residual_solvent_limits({"methanol": 1.0}, daily_dose_g=-1.0)


# --------------------------------------------------------------------------- #
# Route validation
# --------------------------------------------------------------------------- #
def test_supported_routes_accepted():
    for route in ("oral", "parenteral", "inhalation"):
        assert classify_solvent("methanol", route=route).route == route


def test_unsupported_route_fails_loudly():
    with pytest.raises(DataValidationError):
        classify_solvent("methanol", route="topical")
    with pytest.raises(DataValidationError):
        check_residual_solvent_limits({"methanol": 1.0}, daily_dose_g=1.0, route="topical")


# --------------------------------------------------------------------------- #
# Foundation integration: regulated values clear the zero-tolerance gate
# --------------------------------------------------------------------------- #
def test_values_pass_zero_calculation_error_gate():
    checks = []
    for name, _cas, _cls, _pde, conc_ppm in _ALL:
        c = classify_solvent(name)
        checks.append(CalculationCheck(f"q3c_{name}", c.concentration_limit_ppm, conc_ppm))
    enforce_zero_calculation_errors(checks)  # raises HardGateError on any mismatch


# --------------------------------------------------------------------------- #
# Traceability, determinism, validation
# --------------------------------------------------------------------------- #
def test_classification_is_citation_tagged():
    c = classify_solvent("acetonitrile")
    assert c.regulatory_basis.startswith("ICH Q3C(R8)")
    assert c.table_reference == "ICH Q3C(R8) Appendices 1-3"
    assert c.rule_set_version.startswith("sha256:")
    assert c.analytical_methods  # a recommended method is always present
    assert any("decision-support" in n.lower() for n in c.notes)


def test_result_is_deterministic():
    assert classify_solvent("methanol").content_hash() == classify_solvent("methanol").content_hash()
    assert q3c_rule_set() == q3c_rule_set()
    # SMILES path is deterministic too.
    assert classify_solvent("CCO").content_hash() == classify_solvent("ethanol").content_hash()
