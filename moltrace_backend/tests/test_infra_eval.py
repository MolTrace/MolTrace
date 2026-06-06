"""Unit tests for the Phase 0 evaluation framework (moltrace.spectroscopy.infra.eval).

Every metric is checked against a hand-computed value so the suite doubles as
executable documentation of the definitions.
"""

from __future__ import annotations

import math

import pytest

from moltrace.spectroscopy.infra.eval import (
    MetricVector,
    bedroc,
    classification_f1,
    expected_calibration_error,
    f1_score,
    peak_detection_f1,
    reliability_bins,
    rmse,
    top_k_accuracy,
)


# --------------------------------------------------------------------------- #
# rmse
# --------------------------------------------------------------------------- #
def test_rmse_zero_for_identical() -> None:
    assert rmse([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 0.0


def test_rmse_known_value() -> None:
    # errors 3 and 4 -> sqrt((9+16)/2) = sqrt(12.5)
    assert rmse([0.0, 0.0], [3.0, 4.0]) == pytest.approx(math.sqrt(12.5))


def test_rmse_single_pair() -> None:
    assert rmse([1.0], [4.0]) == pytest.approx(3.0)


def test_rmse_rejects_empty() -> None:
    with pytest.raises(ValueError):
        rmse([], [])


def test_rmse_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError):
        rmse([1.0, 2.0], [1.0])


def test_rmse_rejects_non_finite() -> None:
    with pytest.raises(ValueError):
        rmse([1.0, float("nan")], [1.0, 2.0])


# --------------------------------------------------------------------------- #
# f1_score
# --------------------------------------------------------------------------- #
def test_f1_perfect() -> None:
    prf = f1_score(5, 0, 0)
    assert (prf.precision, prf.recall, prf.f1) == (1.0, 1.0, 1.0)


def test_f1_all_zero_is_zero_not_nan() -> None:
    prf = f1_score(0, 0, 0)
    assert (prf.precision, prf.recall, prf.f1) == (0.0, 0.0, 0.0)


def test_f1_known_value() -> None:
    prf = f1_score(5, 5, 0)  # precision 0.5, recall 1.0
    assert prf.precision == pytest.approx(0.5)
    assert prf.recall == pytest.approx(1.0)
    assert prf.f1 == pytest.approx(2 * 0.5 * 1.0 / 1.5)


def test_f1_rejects_negative() -> None:
    with pytest.raises(ValueError):
        f1_score(-1, 0, 0)


# --------------------------------------------------------------------------- #
# peak_detection_f1
# --------------------------------------------------------------------------- #
def test_peak_detection_all_match() -> None:
    prf = peak_detection_f1([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], tolerance=0.05)
    assert prf.true_positives == 3
    assert prf.f1 == pytest.approx(1.0)


def test_peak_detection_missing_reference_peak() -> None:
    prf = peak_detection_f1([1.0, 2.0], [1.0, 2.0, 3.0], tolerance=0.05)
    assert (prf.true_positives, prf.false_positives, prf.false_negatives) == (2, 0, 1)
    assert prf.f1 == pytest.approx(0.8)


def test_peak_detection_just_inside_and_outside_tolerance() -> None:
    assert peak_detection_f1([1.04], [1.0], tolerance=0.05).true_positives == 1
    prf = peak_detection_f1([1.06], [1.0], tolerance=0.05)
    assert (prf.true_positives, prf.false_positives, prf.false_negatives) == (0, 1, 1)


def test_peak_detection_hungarian_prevents_double_claim() -> None:
    # Two predictions both within tolerance of one reference: only one may match.
    prf = peak_detection_f1([1.0, 1.02], [1.0], tolerance=0.05)
    assert (prf.true_positives, prf.false_positives, prf.false_negatives) == (1, 1, 0)


def test_peak_detection_empty_predictions() -> None:
    prf = peak_detection_f1([], [1.0, 2.0], tolerance=0.05)
    assert (prf.true_positives, prf.false_positives, prf.false_negatives) == (0, 0, 2)


# --------------------------------------------------------------------------- #
# classification_f1
# --------------------------------------------------------------------------- #
def test_classification_micro_equals_accuracy() -> None:
    pred = ["a", "a", "b", "c"]
    true = ["a", "b", "b", "c"]
    prf = classification_f1(pred, true, average="micro")
    # 3 of 4 correct -> micro precision = recall = f1 = 0.75
    assert prf.f1 == pytest.approx(0.75)
    assert (prf.true_positives, prf.false_positives, prf.false_negatives) == (3, 1, 1)


def test_classification_macro_value() -> None:
    pred = ["a", "a", "b", "c"]
    true = ["a", "b", "b", "c"]
    prf = classification_f1(pred, true, average="macro")
    # per-class F1: a=0.6667, b=0.6667, c=1.0 -> mean 0.7778
    assert prf.f1 == pytest.approx((2 / 3 + 2 / 3 + 1.0) / 3)


def test_classification_rejects_bad_average() -> None:
    with pytest.raises(ValueError):
        classification_f1(["a"], ["a"], average="weird")


# --------------------------------------------------------------------------- #
# top_k_accuracy
# --------------------------------------------------------------------------- #
def test_top_k_accuracy_varies_with_k() -> None:
    ranked = [["x", "y", "z"], ["a", "b"], ["m", "n"]]
    targets = ["y", "c", "m"]
    assert top_k_accuracy(ranked, targets, k=1) == pytest.approx(1 / 3)
    assert top_k_accuracy(ranked, targets, k=2) == pytest.approx(2 / 3)
    assert top_k_accuracy(ranked, targets, k=3) == pytest.approx(2 / 3)


def test_top_k_accuracy_rejects_bad_k() -> None:
    with pytest.raises(ValueError):
        top_k_accuracy([["a"]], ["a"], k=0)


# --------------------------------------------------------------------------- #
# bedroc (Truchon & Bayly 2007)
# --------------------------------------------------------------------------- #
def test_bedroc_perfect_ranking_is_one() -> None:
    scores = [5.0, 4.0, 3.0, 2.0, 1.0]
    labels = [1, 1, 0, 0, 0]  # actives ranked first
    assert bedroc(scores, labels, alpha=20.0) > 0.999


def test_bedroc_worst_ranking_is_zero() -> None:
    scores = [5.0, 4.0, 3.0, 2.0, 1.0]
    labels = [0, 0, 0, 1, 1]  # actives ranked last
    assert bedroc(scores, labels, alpha=20.0) < 0.001


def test_bedroc_perfect_beats_random_beats_worst() -> None:
    scores = [5.0, 4.0, 3.0, 2.0, 1.0, 0.0]
    perfect = bedroc(scores, [1, 1, 0, 0, 0, 0], alpha=20.0)
    middle = bedroc(scores, [0, 1, 0, 1, 0, 0], alpha=20.0)
    worst = bedroc(scores, [0, 0, 0, 0, 1, 1], alpha=20.0)
    assert perfect > middle > worst


def test_bedroc_all_active_is_one() -> None:
    assert bedroc([3.0, 2.0, 1.0], [1, 1, 1], alpha=20.0) == 1.0


def test_bedroc_no_actives_raises() -> None:
    with pytest.raises(ValueError):
        bedroc([3.0, 2.0, 1.0], [0, 0, 0])


def test_bedroc_rejects_bad_alpha() -> None:
    with pytest.raises(ValueError):
        bedroc([1.0], [1], alpha=0.0)


def test_bedroc_is_repeatable_no_rng() -> None:
    # Tied scores are broken by a stable sort (input order), so repeated calls on
    # the same input must be byte-for-byte equal -- there is no RNG anywhere.
    scores = [1.0, 1.0, 1.0, 1.0]
    labels = [1, 0, 1, 0]
    assert bedroc(scores, labels, alpha=20.0) == bedroc(scores, labels, alpha=20.0)


def test_bedroc_stable_tie_break_favours_input_order() -> None:
    # With all scores equal, the only signal is position: actives listed first
    # score better than the same actives listed last. Confirms stable ordering.
    early = bedroc([1.0, 1.0, 1.0, 1.0], [1, 1, 0, 0], alpha=20.0)
    late = bedroc([1.0, 1.0, 1.0, 1.0], [0, 0, 1, 1], alpha=20.0)
    assert early > late


# --------------------------------------------------------------------------- #
# expected_calibration_error (Guo et al. 2017)
# --------------------------------------------------------------------------- #
def test_ece_perfectly_calibrated_bin_is_zero() -> None:
    # Two samples at conf 0.5, one correct -> acc 0.5 == conf 0.5 -> ECE 0.
    assert expected_calibration_error([0.5, 0.5], [True, False], n_bins=10) == pytest.approx(0.0)


def test_ece_overconfident() -> None:
    conf = [0.9, 0.9, 0.9, 0.9]
    correct = [True, False, False, False]  # acc 0.25, conf 0.9 -> gap 0.65
    assert expected_calibration_error(conf, correct, n_bins=10) == pytest.approx(0.65)


def test_ece_two_bins_weighted() -> None:
    conf = [0.2, 0.2, 0.8, 0.8]
    correct = [False, False, True, True]  # each bin gap 0.2, weight 0.5 -> 0.2
    assert expected_calibration_error(conf, correct, n_bins=10) == pytest.approx(0.2)


def test_ece_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError):
        expected_calibration_error([1.5], [True])


def test_ece_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError):
        expected_calibration_error([0.5, 0.5], [True])


def test_reliability_bins_partition_all_samples() -> None:
    conf = [0.0, 0.05, 0.5, 0.95, 1.0]
    correct = [True, False, True, False, True]
    bins = reliability_bins(conf, correct, n_bins=10)
    assert sum(b.count for b in bins) == len(conf)


# --------------------------------------------------------------------------- #
# MetricVector
# --------------------------------------------------------------------------- #
def test_metric_vector_flattens_and_drops_none() -> None:
    vec = MetricVector(rmse=0.12, f1=0.9, top_k={1: 0.4, 3: 0.7})
    flat = vec.as_dict()
    assert flat == {
        "rmse": pytest.approx(0.12),
        "f1": pytest.approx(0.9),
        "top_1_accuracy": pytest.approx(0.4),
        "top_3_accuracy": pytest.approx(0.7),
    }
    # Unset metrics (precision, recall, bedroc, ece) are omitted, not None.
    assert "precision" not in flat
    assert "ece" not in flat


def test_metric_vector_all_floats() -> None:
    vec = MetricVector(rmse=1, precision=1, recall=1, f1=1, bedroc=1, ece=0)
    assert all(isinstance(v, float) for v in vec.as_dict().values())
