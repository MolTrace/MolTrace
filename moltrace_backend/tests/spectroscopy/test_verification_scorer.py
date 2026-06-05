"""Tests for the multi-test ASV structure-verification scorer (Prompt 7).

The unit tests drive each test class with controlled inputs (constructed
``ShiftPrediction`` objects + synthetic experimental units) so they need
neither PyTorch nor real weights.  The end-to-end tests run
``verify_structure`` on a synthetic spectrum through the deterministic
HOSE-code fallback.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from rdkit import Chem

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.predict.nmrnet_wrapper import AtomShift, ShiftPrediction
from moltrace.spectroscopy.verification.scorer import (
    LN10,
    VERDICT_CONSISTENT_AT,
    VERDICT_INCONSISTENT_AT,
    AssignmentsTest,
    HSQC2DRangesTest,
    MSMoleculeMatchTest,
    PredictionBoundsTest,
    TestResult,
    VerificationOptions,
    VerificationResult,
    _combine,
    _predict_ms,
    _verdict,
    verify_structure,
)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def _prediction(shifts: list[AtomShift], method: str = "nmrnet") -> ShiftPrediction:
    return ShiftPrediction(
        smiles="X",
        method=method,
        device="cpu",
        shifts=shifts,
        n_conformers=8,
        warnings=[],
    )


def _unit(center_ppm: float, area: float = 1.0, label: str = "s") -> dict:
    return {"center_ppm": center_ppm, "area": area, "label": label}


def _synthetic_1h(center: float = 7.26, width: float = 0.01, npts: int = 20000) -> NMRSpectrum:
    ppm = np.linspace(10.0, 0.0, npts)
    data = (width**2) / ((ppm - center) ** 2 + width**2)
    return NMRSpectrum(
        data=data, ppm_axis=ppm, nucleus="1H", solvent="CDCl3", field_mhz=400.0
    )


# --------------------------------------------------------------------------- #
# TestResult dataclass
# --------------------------------------------------------------------------- #
def test_testresult_quality_is_score_times_tanh():
    r = TestResult.create(
        name="t", score=0.5, significance=3.0, prior_confidence=0.5, diagnostic=""
    )
    assert r.quality == pytest.approx(0.5 * math.tanh(1.0))
    assert r.applicable is True


def test_testresult_clamps_score_and_floors_significance():
    r = TestResult.create(
        name="t", score=5.0, significance=-2.0, prior_confidence=0.5, diagnostic=""
    )
    assert r.score == 1.0
    assert r.significance == 0.0
    assert r.quality == 0.0  # tanh(0) == 0


@pytest.mark.parametrize(
    "sig, band", [(1.0, "low"), (3.0, "medium"), (5.0, "medium"), (6.0, "high")]
)
def test_significance_band(sig, band):
    r = TestResult.create(
        name="t", score=1.0, significance=sig, prior_confidence=0.5, diagnostic=""
    )
    assert r.significance_band == band


def test_abstain_is_not_applicable_and_zero_quality():
    r = TestResult.abstain(name="t", prior_confidence=0.5, diagnostic="no data")
    assert r.applicable is False
    assert r.quality == 0.0
    assert r.score == 0.0


# --------------------------------------------------------------------------- #
# Combination model
# --------------------------------------------------------------------------- #
def test_combine_single_corroborating_test_known_value():
    # score=+1, very high significance -> quality ~ +1 -> +LN10 of log-odds.
    r = TestResult.create(
        name="t", score=1.0, significance=20.0, prior_confidence=0.5, diagnostic=""
    )
    posterior, combination = _combine(0.5, [r])
    expected = 1.0 / (1.0 + math.exp(-(r.quality * LN10)))  # prior logit is 0 at p=0.5
    assert posterior == pytest.approx(expected, abs=1e-9)
    assert posterior > 0.9
    assert combination["model"] == "bayesian_log_odds"
    assert combination["contributions"][0]["log_likelihood_ratio"] == pytest.approx(
        round(r.quality * LN10, 4)
    )


def test_combine_contradicting_test_lowers_confidence():
    r = TestResult.create(
        name="t", score=-1.0, significance=20.0, prior_confidence=0.5, diagnostic=""
    )
    posterior, _ = _combine(0.5, [r])
    assert posterior < 0.1


def test_combine_abstain_leaves_prior_unchanged():
    r = TestResult.abstain(name="t", prior_confidence=0.5, diagnostic="")
    posterior, _ = _combine(0.5, [r])
    assert posterior == pytest.approx(0.5, abs=1e-9)


def test_combine_two_tests_accumulate():
    rs = [
        TestResult.create(
            name=f"t{i}", score=1.0, significance=20.0, prior_confidence=0.5, diagnostic=""
        )
        for i in range(2)
    ]
    one, _ = _combine(0.5, rs[:1])
    two, _ = _combine(0.5, rs)
    assert two > one  # more corroboration -> higher posterior


def test_verdict_thresholds():
    applicable = [
        TestResult.create(
            name="t", score=1.0, significance=5.0, prior_confidence=0.5, diagnostic=""
        )
    ]
    assert _verdict(VERDICT_CONSISTENT_AT + 0.01, applicable) == "consistent"
    assert _verdict(VERDICT_INCONSISTENT_AT - 0.01, applicable) == "inconsistent"
    assert _verdict(0.5, applicable) == "inconclusive"
    # all-abstain -> inconclusive regardless of posterior
    abstained = [TestResult.abstain(name="t", prior_confidence=0.5, diagnostic="")]
    assert _verdict(0.99, abstained) == "inconclusive"


# --------------------------------------------------------------------------- #
# PredictionBoundsTest
# --------------------------------------------------------------------------- #
def test_prediction_bounds_match_scores_high():
    pred = _prediction([AtomShift(0, "H", "1H", 7.26, 0.05)])
    units = [_unit(7.26, area=1.0)]
    r = PredictionBoundsTest().run(
        prediction=pred, units=units, nucleus="1H", total_h=1, prior_confidence=0.5
    )
    assert r.applicable is True
    assert r.score == pytest.approx(1.0)
    assert r.significance_band in ("medium", "high")
    assert r.details["matched_good"] == 1


def test_prediction_bounds_no_match_scores_minus_one():
    pred = _prediction([AtomShift(0, "H", "1H", 2.00, 0.05)])
    units = [_unit(7.26, area=1.0)]
    r = PredictionBoundsTest().run(
        prediction=pred, units=units, nucleus="1H", total_h=1, prior_confidence=0.5
    )
    assert r.score == pytest.approx(-1.0)


def test_prediction_bounds_narrower_uncertainty_more_significant():
    tight = PredictionBoundsTest().run(
        prediction=_prediction([AtomShift(0, "H", "1H", 7.26, 0.02)]),
        units=[_unit(7.26)],
        nucleus="1H",
        total_h=1,
        prior_confidence=0.5,
    )
    loose = PredictionBoundsTest().run(
        prediction=_prediction([AtomShift(0, "H", "1H", 7.26, 0.40)]),
        units=[_unit(7.26)],
        nucleus="1H",
        total_h=1,
        prior_confidence=0.5,
    )
    assert tight.significance > loose.significance


def test_prediction_bounds_hose_fallback_notes_proxy():
    pred = _prediction([AtomShift(0, "H", "1H", 7.26, 0.05)], method="hose_fallback")
    r = PredictionBoundsTest().run(
        prediction=pred, units=[_unit(7.26)], nucleus="1H", total_h=1, prior_confidence=0.5
    )
    assert "HOSE" in r.diagnostic


# --------------------------------------------------------------------------- #
# AssignmentsTest
# --------------------------------------------------------------------------- #
def test_assignments_impurity_lowers_significance():
    pred = _prediction([AtomShift(0, "H", "1H", 7.26, 0.05)])
    clean = AssignmentsTest().run(
        prediction=pred,
        units=[_unit(7.26, area=1.0)],
        coupling_set=None,
        nucleus="1H",
        total_h=1,
        prior_confidence=0.5,
    )
    dirty = AssignmentsTest().run(
        prediction=pred,
        units=[_unit(7.26, area=1.0), _unit(3.0, area=3.0)],  # large unexplained impurity
        coupling_set=None,
        nucleus="1H",
        total_h=1,
        prior_confidence=0.5,
    )
    assert clean.significance > dirty.significance
    assert dirty.details["impurity_pct"] > clean.details["impurity_pct"]


def test_assignments_abstains_without_units():
    pred = _prediction([AtomShift(0, "H", "1H", 7.26, 0.05)])
    r = AssignmentsTest().run(
        prediction=pred,
        units=[],
        coupling_set=None,
        nucleus="1H",
        total_h=1,
        prior_confidence=0.5,
    )
    assert r.applicable is False


# --------------------------------------------------------------------------- #
# HSQC2DRangesTest
# --------------------------------------------------------------------------- #
def _methane_prediction() -> tuple[ShiftPrediction, Chem.Mol]:
    mol_h = Chem.AddHs(Chem.MolFromSmiles("C"))  # atom 0 = C, 1..4 = H
    shifts = [AtomShift(0, "C", "13C", -2.0, 0.5)]
    shifts += [AtomShift(i, "H", "1H", 0.20, 0.05) for i in range(1, 5)]
    return _prediction(shifts), mol_h


def test_hsqc_abstains_without_2d_data():
    pred, mol_h = _methane_prediction()
    r = HSQC2DRangesTest().run(
        prediction=pred, mol_h=mol_h, options=VerificationOptions(), prior_confidence=0.5
    )
    assert r.applicable is False


def test_hsqc_full_coverage_scores_high():
    pred, mol_h = _methane_prediction()
    opts = VerificationOptions(hsqc_peaks=[(0.20, -2.0)])
    r = HSQC2DRangesTest().run(
        prediction=pred, mol_h=mol_h, options=opts, prior_confidence=0.5
    )
    assert r.applicable is True
    assert r.score == pytest.approx(1.0)
    assert r.details["missing"] == 0
    assert r.details["matched"] == r.details["predicted"]


def test_hsqc_wrong_peak_counts_missing_and_extra():
    pred, mol_h = _methane_prediction()
    opts = VerificationOptions(hsqc_peaks=[(5.0, 80.0)])  # nowhere near the CH4 rectangle
    r = HSQC2DRangesTest().run(
        prediction=pred, mol_h=mol_h, options=opts, prior_confidence=0.5
    )
    assert r.details["missing"] == r.details["predicted"]
    assert r.details["extra"] == 1
    assert r.score < 0


# --------------------------------------------------------------------------- #
# MSMoleculeMatchTest + MS predictor
# --------------------------------------------------------------------------- #
def test_predict_ms_toluene_envelope():
    peaks = _predict_ms(Chem.MolFromSmiles("Cc1ccccc1"), "[M+H]+")
    mz0, i0 = peaks[0]
    assert mz0 == pytest.approx(93.07, abs=0.02)  # C7H8 + H
    assert i0 == pytest.approx(1.0)
    # M+1 ~ 7 carbons * 1.07%
    mz1, i1 = peaks[1]
    assert mz1 == pytest.approx(94.073, abs=0.02)
    assert i1 == pytest.approx(0.075, abs=0.01)


def test_predict_ms_adducts_shift_mass():
    mol = Chem.MolFromSmiles("Cc1ccccc1")
    plus_h = _predict_ms(mol, "[M+H]+")[0][0]
    minus_h = _predict_ms(mol, "[M-H]-")[0][0]
    plus_na = _predict_ms(mol, "[M+Na]+")[0][0]
    assert minus_h == pytest.approx(plus_h - 2 * 1.0072765, abs=1e-3)
    assert plus_na > plus_h


def test_ms_match_abstains_without_ms():
    mol = Chem.MolFromSmiles("Cc1ccccc1")
    r = MSMoleculeMatchTest().run(mol=mol, options=VerificationOptions(), prior_confidence=0.5)
    assert r.applicable is False


def test_ms_match_correct_pattern_scores_high():
    mol = Chem.MolFromSmiles("Cc1ccccc1")
    opts = VerificationOptions(ms_peaks=[(93.07, 100.0), (94.07, 7.5)], ms_mz_tolerance_da=0.5)
    r = MSMoleculeMatchTest().run(mol=mol, options=opts, prior_confidence=0.5)
    assert r.score > 0.9
    assert r.significance_band == "high"
    assert r.details["molecular_ion_ppm_error"] is not None


def test_ms_match_absent_molecular_ion_scores_low():
    mol = Chem.MolFromSmiles("Cc1ccccc1")
    opts = VerificationOptions(ms_peaks=[(200.0, 100.0)], ms_mz_tolerance_da=0.5)
    r = MSMoleculeMatchTest().run(mol=mol, options=opts, prior_confidence=0.5)
    assert r.score < 0
    assert r.details["molecular_ion_ppm_error"] is None


# --------------------------------------------------------------------------- #
# verify_structure end-to-end
# --------------------------------------------------------------------------- #
def test_verify_structure_benzene_is_consistent():
    spec = _synthetic_1h(center=7.26)
    res = verify_structure(spec, "c1ccccc1", prior_confidence=0.5)
    assert isinstance(res, VerificationResult)
    assert res.posterior_confidence > 0.5
    names = {t.name for t in res.test_results}
    assert names == {"prediction_bounds", "assignments", "hsqc_2d_ranges", "ms_molecule_match"}
    # 2-D and MS abstain with a 1-D-only spectrum
    by_name = {t.name: t for t in res.test_results}
    assert by_name["hsqc_2d_ranges"].applicable is False
    assert by_name["ms_molecule_match"].applicable is False


def test_verify_structure_invalid_smiles_is_inconclusive():
    spec = _synthetic_1h()
    res = verify_structure(spec, "not_a_smiles)(", prior_confidence=0.5)
    assert res.verdict == "inconclusive"
    assert "invalid_smiles" in res.warnings
    assert res.test_results == []


def test_verify_structure_unknown_test_raises():
    spec = _synthetic_1h()
    with pytest.raises(ValueError):
        verify_structure(spec, "c1ccccc1", tests=["bogus_test"])


def test_verify_structure_test_subset_runs_only_selected():
    spec = _synthetic_1h()
    res = verify_structure(spec, "c1ccccc1", tests=["prediction_bounds"])
    assert [t.name for t in res.test_results] == ["prediction_bounds"]


def test_verify_structure_is_deterministic():
    spec = _synthetic_1h()
    a = verify_structure(spec, "c1ccccc1", prior_confidence=0.4)
    b = verify_structure(spec, "c1ccccc1", prior_confidence=0.4)
    assert a.posterior_confidence == pytest.approx(b.posterior_confidence, abs=1e-9)
    assert [t.score for t in a.test_results] == [t.score for t in b.test_results]


def test_audit_dict_round_trips_every_test():
    spec = _synthetic_1h()
    res = verify_structure(spec, "c1ccccc1")
    audit = res.to_audit_dict()
    assert set(audit) >= {
        "proposed_smiles",
        "posterior_confidence",
        "verdict",
        "tests",
        "combination",
    }
    assert len(audit["tests"]) == 4
    for t in audit["tests"]:
        assert {"name", "score", "significance", "quality", "applicable", "diagnostic"} <= set(t)
