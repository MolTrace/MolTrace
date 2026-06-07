"""Unit tests for the evaluation harness (Prompt 17).

Covers the ten metrics on a tiny hand-computed fixture, gold-set checksum
enforcement (abort on drift), the dominance rule incl. the safety-critical
no-regression guarantee, CI exit codes, and metric-vector persistence.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from moltrace.spectroscopy.eval import (
    CallableBundle,
    GoldMetricVector,
    GoldRecord,
    GoldSet,
    GoldSetChecksumError,
    Prediction,
    dominates,
    evaluate,
    gate_for_ci,
    persist_metric_vector,
)

# --------------------------------------------------------------------------- #
# A tiny, fully hand-computed gold set + a controlled fake model
# --------------------------------------------------------------------------- #
_RECORDS = (
    GoldRecord("r1", "nmrshiftdb2", "K1", {"1H": [1.0], "13C": [50.0]}, True, "K1", {"ppm": [1.0]}),
    GoldRecord("r2", "hmdb", "K2", {"1H": [2.0], "13C": [60.0]}, True, "K2", {"ppm": [2.0]}),
    GoldRecord("r3", "in_house", "K3", {"1H": [3.0], "13C": [70.0]}, False, "KWRONG", {"ppm": [3.0]}),
    GoldRecord("r4", "nmrshiftdb2", "K4", {"1H": [4.0], "13C": [80.0]}, False, "KWRONG2", {"ppm": [4.0]}),
)

# Clean predictions, keyed by identifier.
_CLEAN = {
    "r1": Prediction(("K1",), {"1H": [1.00], "13C": [50.0]}, 0.8, True, ("K1",), 0.1, 10.0),
    "r2": Prediction(("K2",), {"1H": [2.20], "13C": [61.0]}, 0.6, True, ("KX", "K2"), 0.2, 20.0),
    "r3": Prediction(("K3",), {"1H": [3.00], "13C": [70.0]}, 0.7, True, ("K3",), 0.3, 30.0),
    "r4": Prediction(("KOTHER",), {"1H": [4.00], "13C": [80.0]}, 0.4, False, ("KX",), 0.9, 40.0),
}


def _predict(record: GoldRecord) -> Prediction:
    clean = _CLEAN[record.identifier]
    if record.extra.get("perturbed") and record.identifier == "r2":
        return replace(clean, ranked_candidates=("KFLIP",))  # only r2 is fragile under perturbation
    return clean


def _bundle(model_versions=None) -> CallableBundle:
    return CallableBundle(_predict, model_versions or {"nmrnet_checkpoint:13C:1.0.0": "sha256:abc"})


def _gold(*, pinned: bool = True) -> GoldSet:
    gs = GoldSet("mini-gold", _RECORDS)
    if pinned:
        return GoldSet("mini-gold", _RECORDS, expected_checksum=gs.checksum(), expected_size=4)
    return gs


# --------------------------------------------------------------------------- #
# The ten metrics
# --------------------------------------------------------------------------- #
def test_evaluate_computes_all_ten_metrics() -> None:
    mv = evaluate(_bundle(), _gold(), k=5, timestamp="2026-06-07T00:00:00+00:00")

    assert mv.top1_accuracy == pytest.approx(0.75)  # r1,r2,r3 right; r4 wrong
    assert mv.top3_accuracy == pytest.approx(0.75)
    assert mv.shift_mae_1h == pytest.approx(0.05)  # (0 + 0.2 + 0 + 0) / 4
    assert mv.shift_mae_13c == pytest.approx(0.25)  # (0 + 1.0 + 0 + 0) / 4
    assert 0.0 <= mv.ece <= 1.0  # P19 ECE wired in (its own unit tests pin exact values)
    assert mv.false_confirmation_rate == pytest.approx(0.5)  # r3 confirmed a wrong structure; r4 didn't
    assert mv.recall_at_k == pytest.approx(0.75)  # K4 not retrieved
    assert mv.uncertainty_auroc == pytest.approx(1.0)  # the only error (r4) has the highest uncertainty
    assert mv.robustness == pytest.approx(0.75)  # r2 top-1 flips under perturbation
    assert mv.reviewer_agreement_rate == pytest.approx(0.75)  # r3 disagrees with the expert
    assert mv.latency_p50_ms == pytest.approx(25.0)  # median of [10,20,30,40]
    assert mv.latency_p95_ms == pytest.approx(38.5)

    # metadata is carried for auditability
    assert mv.model_versions == {"nmrnet_checkpoint:13C:1.0.0": "sha256:abc"}
    assert mv.gold_checksum == _gold().checksum()
    assert mv.n_records == 4 and mv.k == 5


def test_evaluate_is_deterministic_on_metric_content() -> None:
    a = evaluate(_bundle(), _gold(), timestamp="t")
    b = evaluate(_bundle(), _gold(), timestamp="t")
    assert a.metric_items() == b.metric_items()
    assert a.as_dict() == b.as_dict()


# --------------------------------------------------------------------------- #
# Gold-set checksum enforcement
# --------------------------------------------------------------------------- #
def test_evaluate_aborts_on_checksum_drift() -> None:
    drifted = GoldSet("mini-gold", _RECORDS, expected_checksum="sha256:deadbeef")
    with pytest.raises(GoldSetChecksumError):
        evaluate(_bundle(), drifted)


def test_evaluate_aborts_on_size_drift() -> None:
    wrong_size = GoldSet("mini-gold", _RECORDS, expected_size=100)
    with pytest.raises(GoldSetChecksumError):
        evaluate(_bundle(), wrong_size)


def test_gold_composition() -> None:
    assert _gold().composition() == {"hmdb": 1, "in_house": 1, "nmrshiftdb2": 2}


# --------------------------------------------------------------------------- #
# Dominance
# --------------------------------------------------------------------------- #
def _mv(**over) -> GoldMetricVector:
    base = dict(
        top1_accuracy=0.80,
        top3_accuracy=0.90,
        shift_mae_1h=0.10,
        shift_mae_13c=1.00,
        ece=0.05,
        false_confirmation_rate=0.02,
        recall_at_k=0.90,
        uncertainty_auroc=0.70,
        robustness=0.80,
        reviewer_agreement_rate=0.85,
        latency_p50_ms=100.0,
        latency_p95_ms=200.0,
        model_versions={"m": "sha"},
        gold_checksum="sha256:gc",
        gold_name="g",
        n_records=100,
        k=5,
    )
    base.update(over)
    return GoldMetricVector(**base)


def test_dominance_passes_when_strictly_better_no_regression() -> None:
    incumbent = _mv()
    candidate = _mv(top1_accuracy=0.85)  # better top-1, all else equal
    passed, deltas = dominates(candidate, incumbent)
    assert passed is True
    top1 = next(d for d in deltas if d.metric == "top1_accuracy")
    assert top1.improved and not top1.regressed


def test_dominance_blocks_safety_critical_regression() -> None:
    incumbent = _mv()
    candidate = _mv(top1_accuracy=0.95, ece=0.10)  # big top-1 win, but calibration regresses
    passed, deltas = dominates(candidate, incumbent)
    assert passed is False
    ece = next(d for d in deltas if d.metric == "ece")
    assert ece.safety_critical and ece.regressed


def test_dominance_blocks_false_confirmation_regression() -> None:
    incumbent = _mv()
    candidate = _mv(top1_accuracy=0.95, false_confirmation_rate=0.05)  # passes more wrong structures
    passed, _ = dominates(candidate, incumbent)
    assert passed is False


def test_dominance_requires_strict_improvement() -> None:
    incumbent = _mv()
    candidate = _mv()  # identical -> no metric strictly improves
    passed, _ = dominates(candidate, incumbent)
    assert passed is False


def test_dominance_tolerates_minor_nonsafety_regression() -> None:
    incumbent = _mv()
    # top-1 dips 0.003 (within the 0.005 tolerance) but recall improves materially
    candidate = _mv(top1_accuracy=0.797, recall_at_k=0.95)
    passed, deltas = dominates(candidate, incumbent)
    assert passed is True
    top1 = next(d for d in deltas if d.metric == "top1_accuracy")
    assert not top1.regressed  # within tolerance


def test_dominance_blocks_nonsafety_regression_beyond_tolerance() -> None:
    incumbent = _mv()
    candidate = _mv(top1_accuracy=0.70, recall_at_k=0.99)  # top-1 craters beyond tolerance
    passed, _ = dominates(candidate, incumbent)
    assert passed is False


# --------------------------------------------------------------------------- #
# CI gate exit codes
# --------------------------------------------------------------------------- #
def test_gate_returns_zero_when_dominant() -> None:
    candidate = evaluate(_bundle(), _gold(), timestamp="t")
    incumbent = replace(candidate, top1_accuracy=candidate.top1_accuracy - 0.1)  # strictly worse
    assert gate_for_ci(_bundle(), gold_set=_gold(), incumbent_metrics=incumbent) == 0


def test_gate_returns_one_when_not_promotable() -> None:
    candidate = evaluate(_bundle(), _gold(), timestamp="t")
    # incumbent has a strictly lower (better) false-confirmation rate -> candidate regresses on safety
    incumbent = replace(candidate, false_confirmation_rate=candidate.false_confirmation_rate - 0.4)
    assert gate_for_ci(_bundle(), gold_set=_gold(), incumbent_metrics=incumbent) == 1


def test_gate_returns_zero_with_no_incumbent() -> None:
    assert gate_for_ci(_bundle(), gold_set=_gold()) == 0  # first model is promotable


def test_gate_returns_two_on_checksum_drift() -> None:
    drifted = GoldSet("mini-gold", _RECORDS, expected_checksum="sha256:deadbeef")
    assert gate_for_ci(_bundle(), gold_set=drifted) == 2


# --------------------------------------------------------------------------- #
# Persistence (model_versions + checksum)
# --------------------------------------------------------------------------- #
def test_persist_metric_vector_roundtrip(tmp_path) -> None:
    report = evaluate(_bundle(), _gold(), timestamp="2026-06-07T00:00:00+00:00")
    out = tmp_path / "gold_eval.json"
    digest = persist_metric_vector(report, path=out)

    assert digest.startswith("sha256:")
    loaded = json.loads(out.read_text())
    assert loaded["model_versions"] == {"nmrnet_checkpoint:13C:1.0.0": "sha256:abc"}
    assert loaded["gold_checksum"] == report.gold_checksum
    assert loaded["top1_accuracy"] == pytest.approx(0.75)
    assert loaded["false_confirmation_rate"] == pytest.approx(0.5)
