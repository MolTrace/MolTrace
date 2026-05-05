from __future__ import annotations

import csv
import io

from nmrcheck.candidate import compare_candidates
from nmrcheck.models import CandidateComparisonRequest, CandidateInput, SpectralSimilarityRequest
from nmrcheck.nmr2d import parse_nmr2d_table
from nmrcheck.spectral_similarity import (
    score_carbon13_similarity,
    score_nmr2d_similarity,
    score_proton_similarity,
    score_similarity_request,
)

ETHANOL_1H = "1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
ETHANOL_1H_SHIFTED = "1H NMR (400 MHz, CDCl3) delta 3.66 (q, J = 7.1 Hz, 2H), 1.25 (t, J = 7.1 Hz, 3H), 2.11 (br s, 1H)"
BAD_1H = "1H NMR (400 MHz, CDCl3) delta 7.30 (m, 5H), 4.50 (s, 2H)"
ETHANOL_13C = "13C NMR (101 MHz, CDCl3) delta 58.3, 18.2."
ETHANOL_13C_SHIFTED = "13C NMR (101 MHz, CDCl3) delta 58.5, 18.0."


def _table_bytes(rows: list[list[object]]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["experiment", "f2_ppm", "f1_ppm", "intensity"])
    writer.writerows(rows)
    return out.getvalue().encode()


def test_proton_similarity_high_for_shifted_ethanol() -> None:
    result = score_proton_similarity(ETHANOL_1H, ETHANOL_1H_SHIFTED)

    assert result.layer == "1H"
    assert result.vector_score is not None
    assert result.set_score is not None
    assert result.combined_score > 0.8
    assert result.matched_count >= 3


def test_proton_similarity_low_for_unrelated_spectrum() -> None:
    result = score_proton_similarity(ETHANOL_1H, BAD_1H)

    assert result.combined_score < 0.6
    assert result.unmatched_observed_count > 0


def test_carbon13_similarity_high_for_shifted_ethanol_without_quantitative_intensity() -> None:
    result = score_carbon13_similarity(ETHANOL_13C, ETHANOL_13C_SHIFTED, solvent="CDCl3")

    assert result.layer == "13C"
    assert result.vector_score is not None
    assert result.set_score is not None
    assert result.combined_score > 0.8
    assert result.matched_count == 2
    assert any("13C intensities are not treated as quantitative" in note for note in result.notes)


def test_overall_similarity_combines_1h_and_13c() -> None:
    result = score_similarity_request(
        SpectralSimilarityRequest(
            sample_id="ethanol",
            solvent="CDCl3",
            observed_proton_text=ETHANOL_1H,
            reference_proton_text=ETHANOL_1H_SHIFTED,
            observed_carbon13_text=ETHANOL_13C,
            reference_carbon13_text=ETHANOL_13C_SHIFTED,
        )
    )

    assert result.label == "high_similarity"
    assert set(result.evidence_layers_used) == {"1H", "13C"}
    assert result.overall_score > 0.8


def test_2d_hsqc_similarity_scores_shifted_crosspeak_sets() -> None:
    observed = parse_nmr2d_table(
        "obs_hsqc.csv",
        _table_bytes([["HSQC", 3.65, 58.3, 1.0], ["HSQC", 1.26, 18.2, 1.0]]),
        experiment_type="HSQC",
    )
    reference = parse_nmr2d_table(
        "ref_hsqc.csv",
        _table_bytes([["HSQC", 3.66, 58.5, 1.0], ["HSQC", 1.25, 18.0, 1.0]]),
        experiment_type="HSQC",
    )
    result = score_nmr2d_similarity(observed, reference)

    assert result.layer == "HSQC"
    assert result.vector_score is not None
    assert result.set_score is not None
    assert result.combined_score > 0.75
    assert result.matched_count == 2
    assert result.crosspeak_matches


def test_2d_similarity_excludes_cosy_diagonal_peaks() -> None:
    observed = parse_nmr2d_table(
        "obs_cosy.csv",
        _table_bytes([["COSY", 3.65, 1.26, 1.0], ["COSY", 3.65, 3.65, 1.0]]),
        experiment_type="COSY",
    )
    reference = parse_nmr2d_table(
        "ref_cosy.csv",
        _table_bytes([["COSY", 3.66, 1.25, 1.0], ["COSY", 3.66, 3.66, 1.0]]),
        experiment_type="COSY",
    )
    result = score_nmr2d_similarity(observed, reference)

    assert result.observed_count == 1
    assert result.reference_count == 1
    assert result.matched_count == 1
    assert result.metadata["diagonal_peaks_excluded"] is True


def test_candidate_comparison_behavior_remains_unchanged_after_similarity_scoring() -> None:
    request = CandidateComparisonRequest(
        sample_id="ethanol",
        solvent="CDCl3",
        proton_nmr_text=ETHANOL_1H,
        carbon13_text=ETHANOL_13C,
        candidates=[
            CandidateInput(name="Ethanol", smiles="CCO", role="proposed"),
            CandidateInput(name="Methanol", smiles="CO", role="starting material"),
            CandidateInput(name="Propanol", smiles="CCCO", role="side product"),
        ],
    )
    before = compare_candidates(request)
    score_similarity_request(
        SpectralSimilarityRequest(
            sample_id="ethanol",
            solvent="CDCl3",
            observed_proton_text=ETHANOL_1H,
            reference_proton_text=ETHANOL_1H_SHIFTED,
        )
    )
    after = compare_candidates(request)

    assert before.model_dump(mode="json") == after.model_dump(mode="json")
