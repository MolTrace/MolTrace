from nmrcheck.models import CandidateInput, UnifiedCandidateConfidenceRequest
from nmrcheck.unified_confidence import build_unified_candidate_confidence


def test_unified_confidence_ranks_ethanol_across_nmr_hrms_ms_layers():
    result = build_unified_candidate_confidence(
        UnifiedCandidateConfidenceRequest(
            sample_id="unified-ethanol",
            solvent="CDCl3",
            candidates=[
                CandidateInput(name="methanol", smiles="CO"),
                CandidateInput(name="ethanol", smiles="CCO"),
                CandidateInput(name="propanol", smiles="CCCO"),
            ],
            observed_proton_text=(
                "1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), "
                "1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
            ),
            observed_carbon13_text="13C NMR (101 MHz, CDCl3) delta 58.3, 18.2.",
            hrms_observed_mz=47.04914,
            hrms_adduct="[M+H]+",
            ms1_peak_list_text="m/z,intensity\n47.04914,100\n48.05249,2.3\n69.03109,24\n",
            msms_peak_list_text="m/z,intensity\n47.04914,10\n29.03858,100\n31.01839,25\n",
            msms_precursor_mz=47.04914,
            msms_adduct="[M+H]+",
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.name == "ethanol"
    assert result.best_candidate.confidence_score > 0.75
    assert "HRMS exact mass" in result.evidence_layers_used
    assert "MS/MS fragmentation tree" in result.evidence_layers_used
    assert result.ranked_candidates[0].agreement_count >= 3


def test_unified_confidence_reports_sparse_evidence_and_missing_layers():
    result = build_unified_candidate_confidence(
        UnifiedCandidateConfidenceRequest(
            candidates=[
                CandidateInput(name="ethanol", smiles="CCO"),
                CandidateInput(name="methanol", smiles="CO"),
            ],
            hrms_observed_mz=47.04914,
            hrms_adduct="[M+H]+",
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.name == "ethanol"
    assert result.best_candidate.evidence_completeness < 0.5
    assert result.ambiguity_alerts
    assert any("NMR" in layer for layer in result.best_candidate.missing_layers)


def test_unified_confidence_invalid_candidate_does_not_crash():
    result = build_unified_candidate_confidence(
        UnifiedCandidateConfidenceRequest(
            candidates=[
                CandidateInput(name="bad", smiles="not_a_smiles"),
                CandidateInput(name="ethanol", smiles="CCO"),
            ],
            hrms_observed_mz=47.04914,
            hrms_adduct="[M+H]+",
        )
    )
    bad = next(item for item in result.ranked_candidates if item.name == "bad")
    assert bad.label == "invalid_structure"
    assert bad.warnings or bad.contradictions


def test_unified_confidence_uses_optional_2d_as_predicted_nmr_layer():
    result = build_unified_candidate_confidence(
        UnifiedCandidateConfidenceRequest(
            candidates=[
                CandidateInput(name="methanol", smiles="CO"),
                CandidateInput(name="ethanol", smiles="CCO"),
            ],
            observed_nmr2d_text="f2_ppm,f1_ppm,intensity\n3.65,58.3,100\n1.26,18.2,90\n",
            observed_nmr2d_experiment_type="HSQC",
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.name == "ethanol"
    assert "Candidate-specific predicted NMR" in result.evidence_layers_used
