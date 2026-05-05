import pytest

from nmrcheck.models import CandidateInput, MSMSAnnotationRequest
from nmrcheck.msms import annotate_msms, parse_msms_peak_text


def test_parse_processed_msms_peak_text_csv_tsv_and_whitespace():
    peaks = parse_msms_peak_text(
        """
        m/z,intensity
        47.04914,10
        29.03913 100
        31.0184\t25
        # comment
        """
    )
    assert len(peaks) == 3
    assert peaks[0].mz == 47.04914
    assert peaks[1].intensity == 100
    assert peaks[2].mz == 31.0184


def test_msms_annotation_detects_water_loss_and_ranks_ethanol():
    result = annotate_msms(
        MSMSAnnotationRequest(
            precursor_mz=47.04914,
            adduct="[M+H]+",
            mz_tolerance_da=0.02,
            ppm_tolerance=20,
            peak_list_text="47.04914,10\n29.03913,100\n",
            candidates=[
                CandidateInput(name="methanol", smiles="CO"),
                CandidateInput(name="ethanol", smiles="CCO"),
            ],
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.name == "ethanol"
    assert result.best_candidate.label == "consistent_with_msms"
    assert any(hit.loss_name == "H2O" for hit in result.neutral_loss_hits)
    assert result.best_candidate.fragment_match_count >= 1
    assert result.best_candidate.explained_intensity_fraction > 0.8


def test_msms_invalid_smiles_does_not_crash():
    result = annotate_msms(
        MSMSAnnotationRequest(
            precursor_mz=47.04914,
            adduct="[M+H]+",
            peak_list_text="29.03913,100\n",
            candidates=[
                CandidateInput(name="invalid", smiles="not a smiles"),
                CandidateInput(name="ethanol", smiles="CCO"),
            ],
        )
    )
    invalid = [item for item in result.ranked_candidates if item.name == "invalid"][0]
    assert invalid.label == "invalid_structure"
    assert invalid.warnings
    assert result.best_candidate is not None
    assert result.best_candidate.name == "ethanol"


def test_msms_neutral_loss_only_without_candidates():
    result = annotate_msms(
        MSMSAnnotationRequest(
            precursor_mz=181.07066,
            adduct="[M+H]+",
            mz_tolerance_da=0.02,
            ppm_tolerance=20,
            peak_list_text="163.06010,100\n135.04500,30\n",
            candidates=[],
        )
    )
    assert result.candidate_count == 0
    assert result.best_candidate is None
    assert any(hit.loss_name == "H2O" for hit in result.neutral_loss_hits)


def test_msms_unsupported_adduct_raises_clear_error():
    with pytest.raises(ValueError, match="Unsupported HRMS adduct"):
        annotate_msms(
            MSMSAnnotationRequest(
                precursor_mz=100.0,
                adduct="[M+Foo]+",
                peak_list_text="80.0,100\n",
                candidates=[],
            )
        )
