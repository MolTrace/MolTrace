import csv
import io

from nmrcheck.candidate_predicted import match_candidates_with_predicted_nmr
from nmrcheck.models import CandidateInput, CandidatePredictedNMRMatchRequest
from nmrcheck.nmr2d import parse_nmr2d_table
from nmrcheck.nmr_prediction import (
    predict_nmr_from_smiles,
    score_observed_against_predicted_carbon13,
    score_observed_against_predicted_proton,
)

ETHANOL_1H = (
    "1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), "
    "1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
)
ETHANOL_13C = "13C NMR (101 MHz, CDCl3) delta 58.3, 18.2."

TOBRAMYCIN_SMILES = (
    "O[C@@]1([H])[C@]([C@@H](O)[C@@H](O[C@@]([C@]2(O)[H])([H])"
    "[C@@H](C([H])[C@H](N)[C@H]2O[C@@H](O[C@]([C@@]3([H])O)([H])CN)"
    "[C@@H](C3([H])[H])N)N)O[C@@H]1CO)([H])N"
)


def nmr2d_bytes(rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["experiment", "f2_ppm", "f1_ppm", "intensity"])
    writer.writerows(rows)
    return out.getvalue().encode()


def test_predict_ethanol_generates_1h_13c_and_hsqc_peaks():
    prediction = predict_nmr_from_smiles("CCO", name="ethanol", solvent="CDCl3")
    assert prediction.confidence_label in {"high", "medium"}
    assert prediction.formula == "C2H6O"
    assert len(prediction.proton_peaks) >= 2
    assert len(prediction.carbon13_peaks) == 2
    assert prediction.predicted_hsqc_crosspeaks


def test_predict_tobramycin_prioritises_carbohydrate_regions_not_alkenes():
    prediction = predict_nmr_from_smiles(TOBRAMYCIN_SMILES, name="tobramycin derivative", solvent="D2O")
    proton_envs = [str(peak.environment or "") for peak in prediction.proton_peaks]
    carbon_envs = [str(peak.environment or "") for peak in prediction.carbon13_peaks]

    assert prediction.metadata["olefinic_proton_count"] == 0
    assert prediction.metadata["anomeric_proton_count"] > 0
    assert any("anomeric_or_acetal" in env for env in proton_envs)
    assert any("carbohydrate" in env or "aminoglycoside" in env for env in proton_envs)
    assert any("anomeric_or_acetal" in env for env in carbon_envs)
    assert not any("vinylic" in env or "alkene" in env for env in proton_envs + carbon_envs)
    assert any(3.0 <= peak.shift_ppm <= 4.4 for peak in prediction.proton_peaks)


def test_predicted_ethanol_matches_ethanol_text():
    prediction = predict_nmr_from_smiles("CCO", name="ethanol", solvent="CDCl3")
    proton = score_observed_against_predicted_proton(ETHANOL_1H, prediction)
    carbon = score_observed_against_predicted_carbon13(ETHANOL_13C, prediction, solvent="CDCl3")
    assert proton.combined_score > 0.75
    assert carbon.combined_score > 0.90


def test_candidate_specific_predicted_matching_ranks_ethanol_highest():
    result = match_candidates_with_predicted_nmr(
        CandidatePredictedNMRMatchRequest(
            solvent="CDCl3",
            observed_proton_text=ETHANOL_1H,
            observed_carbon13_text=ETHANOL_13C,
            candidates=[
                CandidateInput(name="methanol", smiles="CO"),
                CandidateInput(name="ethanol", smiles="CCO"),
                CandidateInput(name="propanol", smiles="CCCO"),
            ],
        )
    )
    assert result.best_candidate is not None
    assert result.best_candidate.name == "ethanol"
    assert result.best_candidate.label == "best_predicted_match"
    assert result.best_candidate.evidence_label == "best_supported"
    assert result.best_candidate.human_review_required is True
    assert result.human_review_status == "pending_review"
    assert result.limitations
    assert "1H predicted-match" in result.evidence_layers_used
    assert "13C predicted-match" in result.evidence_layers_used


def test_candidate_specific_predicted_matching_reuses_identical_request_cache():
    request = CandidatePredictedNMRMatchRequest(
        sample_id="cache-speed-regression-ethanol",
        solvent="CDCl3",
        observed_proton_text=ETHANOL_1H,
        observed_carbon13_text=ETHANOL_13C,
        candidates=[
            CandidateInput(name="methanol", smiles="CO"),
            CandidateInput(name="ethanol", smiles="CCO"),
            CandidateInput(name="propanol", smiles="CCCO"),
        ],
    )

    first = match_candidates_with_predicted_nmr(request)
    second = match_candidates_with_predicted_nmr(request)

    assert first.best_candidate is not None
    assert second.best_candidate is not None
    assert first.best_candidate.name == second.best_candidate.name == "ethanol"
    assert first.metadata["match_cache"] == "miss"
    assert second.metadata["match_cache"] == "hit"


def test_candidate_specific_predicted_matching_preserves_requires_review_for_weak_evidence():
    result = match_candidates_with_predicted_nmr(
        CandidatePredictedNMRMatchRequest(
            observed_proton_text="1H NMR delta 7.30 (m, 5H), 4.50 (s, 2H)",
            candidates=[
                CandidateInput(name="ethanol", smiles="CCO"),
                CandidateInput(name="methanol", smiles="CO"),
            ],
        )
    )

    assert result.best_candidate is not None
    assert result.best_candidate.evidence_label in {
        "requires_review",
        "conflicting_evidence",
        "insufficient_evidence",
    }
    assert any("final structure identification" in limitation for limitation in result.limitations)


def test_invalid_candidate_is_labeled_invalid_structure():
    result = match_candidates_with_predicted_nmr(
        CandidatePredictedNMRMatchRequest(
            observed_proton_text=ETHANOL_1H,
            candidates=[
                CandidateInput(name="bad", smiles="not_a_smiles"),
                CandidateInput(name="ethanol", smiles="CCO"),
            ],
        )
    )
    bad = [item for item in result.ranked_candidates if item.name == "bad"][0]
    assert bad.label == "invalid_structure"
    assert bad.evidence_label == "invalid_structure"
    assert bad.total_score == 0.0


def test_candidate_specific_hsqc_prediction_can_use_observed_hsqc():
    observed_hsqc = parse_nmr2d_table(
        "ethanol_hsqc.csv",
        nmr2d_bytes([["HSQC", 3.65, 58.3, 1.0], ["HSQC", 1.26, 18.2, 1.0]]),
        experiment_type="HSQC",
    )
    result = match_candidates_with_predicted_nmr(
        CandidatePredictedNMRMatchRequest(
            solvent="CDCl3",
            observed_proton_text=ETHANOL_1H,
            observed_carbon13_text=ETHANOL_13C,
            candidates=[CandidateInput(name="ethanol", smiles="CCO")],
        ),
        observed_nmr2d=observed_hsqc,
    )
    assert result.best_candidate is not None
    assert result.best_candidate.nmr2d_similarity is not None
    assert result.best_candidate.nmr2d_similarity.combined_score > 0.75
