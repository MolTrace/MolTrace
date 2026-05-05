from nmrcheck.fragmentation_tree import build_msms_fragmentation_tree
from nmrcheck.models import CandidateInput, MSMSFragmentationTreeRequest


def test_fragmentation_tree_ranks_ethanol_for_water_loss():
    result = build_msms_fragmentation_tree(
        MSMSFragmentationTreeRequest(
            precursor_mz=47.04914,
            adduct="[M+H]+",
            mz_tolerance_da=0.02,
            ppm_tolerance=20,
            peak_list_text="m/z,intensity\n47.04914,10\n29.03858,100\n31.01839,25",
            candidates=[
                CandidateInput(name="methanol", smiles="CO"),
                CandidateInput(name="ethanol", smiles="CCO"),
                CandidateInput(name="propanol", smiles="CCCO"),
            ],
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.name == "ethanol"
    assert result.best_candidate.label == "strong_fragmentation_tree_support"
    assert result.best_candidate.diagnostic_loss_count >= 1
    assert result.best_candidate.max_tree_depth >= 1
    assert any(hit.loss_name == "H2O" for hit in result.best_candidate.diagnostic_hits)


def test_fragmentation_tree_flags_unsupported_hcl_loss():
    result = build_msms_fragmentation_tree(
        MSMSFragmentationTreeRequest(
            precursor_mz=47.04914,
            adduct="[M+H]+",
            mz_tolerance_da=0.02,
            ppm_tolerance=20,
            peak_list_text="m/z,intensity\n47.04914,100\n11.07246,50",
            candidates=[CandidateInput(name="ethanol", smiles="CCO")],
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.contradiction_count >= 1
    assert any("HCl" in flag for flag in result.best_candidate.contradiction_flags)


def test_fragmentation_tree_invalid_smiles_is_safe():
    result = build_msms_fragmentation_tree(
        MSMSFragmentationTreeRequest(
            precursor_mz=47.04914,
            adduct="[M+H]+",
            peak_list_text="m/z,intensity\n47.04914,100\n29.03858,50",
            candidates=[CandidateInput(name="bad", smiles="not-a-smiles")],
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.label == "invalid_structure"
    assert result.best_candidate.warnings


def test_fragmentation_tree_builds_multi_step_edges():
    result = build_msms_fragmentation_tree(
        MSMSFragmentationTreeRequest(
            precursor_mz=105.0,
            adduct="M",
            mz_tolerance_da=0.05,
            ppm_tolerance=100,
            max_tree_depth=3,
            peak_list_text="m/z,intensity\n105.0,100\n87.0,70\n69.0,40",
            candidates=[CandidateInput(name="oxygenated", smiles="CCOCCO")],
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.max_tree_depth >= 2
    assert any(edge.relation_type == "series_loss" for edge in result.best_candidate.edges)


def test_fragmentation_tree_without_candidates_returns_global_losses_only():
    result = build_msms_fragmentation_tree(
        MSMSFragmentationTreeRequest(
            precursor_mz=47.04914,
            adduct="[M+H]+",
            peak_list_text="m/z,intensity\n47.04914,10\n29.03858,100",
            candidates=[],
        )
    )
    assert result.candidate_count == 0
    assert result.best_candidate is None
    assert any(hit.loss_name == "H2O" for hit in result.global_neutral_loss_hits)
