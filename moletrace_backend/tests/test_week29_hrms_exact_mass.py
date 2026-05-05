import pytest

from nmrcheck.hrms import (
    HRMSError,
    estimate_isotope_pattern,
    formula_from_smiles,
    formula_info,
    match_hrms_candidates,
    normalize_adduct,
    search_formulas_by_hrms,
    theoretical_mz,
)
from nmrcheck.models import CandidateInput, HRMSCandidateMatchRequest, HRMSFormulaSearchRequest


def test_formula_from_smiles_ethanol_exact_mass_and_dbe():
    info = formula_from_smiles("CCO")
    assert info.formula == "C2H6O"
    assert abs(info.exact_mass - 46.041865) < 0.001
    assert info.dbe == 0


def test_theoretical_mz_for_ethanol_m_plus_h():
    info = formula_from_smiles("CCO")
    adduct = normalize_adduct("[M+H]+")
    mz = theoretical_mz(info.exact_mass, adduct)
    assert abs(mz - 47.04914) < 0.001


def test_hrms_candidate_matching_ranks_ethanol_highest():
    result = match_hrms_candidates(
        HRMSCandidateMatchRequest(
            sample_id="EtOH-HRMS",
            observed_mz=47.04914,
            adduct="[M+H]+",
            ppm_tolerance=5.0,
            candidates=[
                CandidateInput(name="methanol", smiles="CO"),
                CandidateInput(name="ethanol", smiles="CCO"),
                CandidateInput(name="propanol", smiles="CCCO"),
            ],
        )
    )
    assert result.best_match is not None
    assert result.best_match.name == "ethanol"
    assert result.best_match.label == "exact_mass_match"
    assert result.exact_match_count >= 1


def test_isotope_pattern_flags_halogen_rich_formulas():
    cl = formula_info("C6H5Cl")
    br = formula_info("C6H5Br")
    assert cl.isotope_m_plus_2_percent is not None
    assert br.isotope_m_plus_2_percent is not None
    assert cl.isotope_m_plus_2_percent > 25
    assert br.isotope_m_plus_2_percent > 80


def test_formula_search_finds_ethanol_formula():
    result = search_formulas_by_hrms(
        HRMSFormulaSearchRequest(
            observed_mz=47.04914,
            adduct="[M+H]+",
            ppm_tolerance=10,
            max_c=5,
            max_h=20,
            max_n=2,
            max_o=3,
            max_s=0,
            max_p=0,
            max_cl=0,
            max_br=0,
            max_results=50,
        )
    )
    assert "C2H6O" in {item.formula for item in result.formulas}


def test_unsupported_adduct_gives_clear_failure():
    with pytest.raises(HRMSError, match="Unsupported HRMS adduct"):
        normalize_adduct("[M+Li]+")


def test_invalid_smiles_is_labeled_invalid_structure_not_crash():
    result = match_hrms_candidates(
        HRMSCandidateMatchRequest(
            observed_mz=47.04914,
            adduct="[M+H]+",
            candidates=[
                CandidateInput(name="bad", smiles="not_a_smiles"),
                CandidateInput(name="ethanol", smiles="CCO"),
            ],
        )
    )
    bad = [item for item in result.ranked_candidates if item.name == "bad"][0]
    assert bad.label == "invalid_structure"
    assert bad.ppm_score == 0.0


def test_estimated_isotope_hints_are_optional_and_transparent():
    m1, m2 = estimate_isotope_pattern({"C": 2, "H": 6, "O": 1})
    assert m1 > 0
    assert m2 >= 0
