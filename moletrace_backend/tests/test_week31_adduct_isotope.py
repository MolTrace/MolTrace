from nmrcheck.adduct_inference import infer_adducts_and_isotopes, parse_ms1_peak_text
from nmrcheck.hrms import formula_info, normalize_adduct, theoretical_mz
from nmrcheck.models import MS1AdductInferenceRequest


def test_parse_ms1_peak_text_accepts_csv_tsv_and_whitespace_tables():
    peaks = parse_ms1_peak_text("m/z,intensity\n47.04914,100\n48.05249,2.3\n")
    assert len(peaks) == 2
    assert peaks[0].mz == 47.04914
    assert peaks[0].intensity == 100

    tsv = parse_ms1_peak_text("mz\tintensity\n47.04914\t100\n48.05249\t2.3\n")
    spaced = parse_ms1_peak_text("47.04914 100\n48.05249 2.3\n")
    assert [peak.mz for peak in tsv] == [peak.mz for peak in spaced]


def test_adduct_inference_ranks_ethanol_m_plus_h_with_sodium_pair():
    text = "m/z,intensity\n47.04914,100\n48.05249,2.3\n69.03109,24\n"
    result = infer_adducts_and_isotopes(
        MS1AdductInferenceRequest(
            peak_list_text=text,
            target_mz=47.04914,
            ion_mode="positive",
            ppm_tolerance=10,
            max_c=5,
            max_h=20,
            max_n=2,
            max_o=3,
            max_s=0,
            max_p=0,
            max_cl=0,
            max_br=0,
        )
    )
    assert result.best_adduct_candidate is not None
    assert result.best_adduct_candidate.adduct.name == "[M+H]+"
    assert result.best_adduct_candidate.top_formulas[0].formula == "C2H6O"
    assert result.best_adduct_candidate.adduct_pair_count >= 1
    assert result.inferred_charge == 1
    assert result.inferred_m_plus_1_percent is not None


def test_isotope_cluster_can_infer_charge_two_from_half_dalton_spacing():
    text = "m/z,intensity\n500.00000,100\n500.50168,12\n"
    result = infer_adducts_and_isotopes(
        MS1AdductInferenceRequest(
            peak_list_text=text,
            target_mz=500.00000,
            ion_mode="positive",
            perform_formula_search=False,
            max_charge=3,
            ppm_tolerance=20,
        )
    )
    assert result.isotope_clusters[0].charge == 2
    assert result.isotope_clusters[0].label in {"possible_isotope_cluster", "clear_isotope_cluster"}


def test_halogen_like_m_plus_2_pattern_is_flagged():
    info = formula_info("C6H5Cl")
    mz = theoretical_mz(info.exact_mass, normalize_adduct("[M+H]+"))
    text = f"m/z,intensity\n{mz:.5f},100\n{mz + 1.00335:.5f},6.7\n{mz + 1.99705:.5f},33.5\n"
    result = infer_adducts_and_isotopes(
        MS1AdductInferenceRequest(
            peak_list_text=text,
            target_mz=mz,
            ion_mode="positive",
            perform_formula_search=False,
            max_charge=1,
            ppm_tolerance=20,
        )
    )
    assert result.isotope_clusters[0].halogen_signature == "chlorine_like"
    assert result.inferred_m_plus_2_percent is not None
    assert result.inferred_m_plus_2_percent > 20


def test_formula_search_can_be_disabled_for_fast_triage():
    result = infer_adducts_and_isotopes(
        MS1AdductInferenceRequest(
            peak_list_text="m/z,intensity\n47.04914,100\n48.05249,2.3\n",
            target_mz=47.04914,
            perform_formula_search=False,
        )
    )
    assert result.best_adduct_candidate is not None
    assert result.best_adduct_candidate.formula_count == 0
    assert any("Formula search disabled" in note for note in result.best_adduct_candidate.evidence_summary)
