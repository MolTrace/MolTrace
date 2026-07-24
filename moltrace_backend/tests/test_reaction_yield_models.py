"""Unit tests for R12 yield predictors (sklearn fallback always; torch smoke auto-skips)."""

from __future__ import annotations

import importlib.util

import pytest

from nmrcheck.reaction_ml import CapabilityUnavailableError
from nmrcheck.reaction_yield_models import (
    ConditionFeaturizer,
    KNNSurrogatePredictor,
    SklearnSurrogatePredictor,
    YieldExample,
    benchmark_yield_predictor,
    compare_yield_models,
    select_yield_predictor,
)

_TRAIN = [
    YieldExample({"catalyst": "Cat-A", "temperature_c": 60}, 85.0),
    YieldExample({"catalyst": "Cat-A", "temperature_c": 80}, 90.0),
    YieldExample({"catalyst": "Cat-B", "temperature_c": 60}, 35.0),
    YieldExample({"catalyst": "Cat-B", "temperature_c": 80}, 42.0),
    YieldExample({"catalyst": "Cat-A", "temperature_c": 40}, 78.0),
    YieldExample({"catalyst": "Cat-B", "temperature_c": 40}, 30.0),
]

_EVIDENCE_OK = {"exit_code": 0, "gold_checksum": "sha256:3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f3f", "model_version": "mpnn.v3"}


# --- featurizer --------------------------------------------------------------------------------
def test_featurizer_is_deterministic_and_sorted():
    a = ConditionFeaturizer().fit([e.conditions for e in _TRAIN])
    b = ConditionFeaturizer().fit([e.conditions for e in reversed(_TRAIN)])
    assert a.as_dict() == b.as_dict()
    assert a.transform({"catalyst": "Cat-A", "temperature_c": 60}) == b.transform(
        {"catalyst": "Cat-A", "temperature_c": 60}
    )
    assert a.width == 1 + 2  # one numeric + two catalyst values


def test_featurizer_flags_unseen_categorical_values():
    featurizer = ConditionFeaturizer().fit([e.conditions for e in _TRAIN])
    vector = featurizer.transform({"catalyst": "Cat-Z", "temperature_c": 60})
    assert featurizer.last_unknowns == ["catalyst=Cat-Z"]
    assert vector[1:] == [0.0, 0.0]  # one-hot block all zero for the unseen value


def test_featurizer_roundtrips_through_dict():
    featurizer = ConditionFeaturizer().fit([e.conditions for e in _TRAIN])
    clone = ConditionFeaturizer.from_dict(featurizer.as_dict())
    assert clone.transform({"catalyst": "Cat-B", "temperature_c": 80}) == featurizer.transform(
        {"catalyst": "Cat-B", "temperature_c": 80}
    )


def test_featurizer_refuses_non_finite_numerics():
    with pytest.raises(ValueError, match="finite"):
        ConditionFeaturizer().fit([{"temperature_c": float("inf")}])


# --- the zero-dependency terminal fallback (always available) ---------------------------------
def test_knn_surrogate_learns_the_catalyst_signal():
    predictor = KNNSurrogatePredictor().fit(_TRAIN)
    good = predictor.predict({"catalyst": "Cat-A", "temperature_c": 70})
    bad = predictor.predict({"catalyst": "Cat-B", "temperature_c": 70})
    assert good.backend == "knn_surrogate"
    assert good.mean > bad.mean  # Cat-A campaigns yielded far higher
    assert good.std >= 2.0  # the uncertainty floor: a k-NN never claims certainty


def test_knn_surrogate_is_deterministic():
    a = KNNSurrogatePredictor().fit(_TRAIN).predict({"catalyst": "Cat-A", "temperature_c": 65})
    b = KNNSurrogatePredictor().fit(list(reversed(_TRAIN))).predict(
        {"catalyst": "Cat-A", "temperature_c": 65}
    )
    assert a.mean == pytest.approx(b.mean)
    assert a.std == pytest.approx(b.std)


def test_benchmark_produces_bounded_metrics():
    predictor = KNNSurrogatePredictor().fit(_TRAIN)
    metrics = benchmark_yield_predictor(predictor, _TRAIN)
    assert set(metrics) == {"mae", "calibration_error"}
    assert metrics["mae"] >= 0.0
    assert 0.0 <= metrics["calibration_error"] <= 1.0


# --- the sklearn GP fallback (exercised only where sklearn is installed) ------------------------
def test_sklearn_surrogate_learns_the_catalyst_signal():
    pytest.importorskip("sklearn")
    predictor = SklearnSurrogatePredictor().fit(_TRAIN)
    good = predictor.predict({"catalyst": "Cat-A", "temperature_c": 70})
    bad = predictor.predict({"catalyst": "Cat-B", "temperature_c": 70})
    assert good.backend == "sklearn_gp_surrogate"
    assert good.mean > bad.mean
    assert good.std >= 0.0


def test_compare_yield_models_uses_frozen_dominance():
    better = {"mae": 4.0, "calibration_error": 0.05}
    worse = {"mae": 7.0, "calibration_error": 0.20}
    dominant, excluded = compare_yield_models(better, worse)
    assert dominant is True and excluded == []
    # Omitting a metric refuses dominance (inherited R9 hardening).
    partial, excluded = compare_yield_models({"mae": 3.0}, worse)
    assert partial is False
    assert "calibration_error" in excluded


# --- governed backend selection ----------------------------------------------------------------
def test_selection_defaults_to_a_lightweight_fallback():
    predictor, decision = select_yield_predictor(env={})
    assert isinstance(predictor, (SklearnSurrogatePredictor, KNNSurrogatePredictor))
    assert decision.backend == "fallback"
    assert decision.provenance["fallback_backend"] == predictor.backend_name


def test_selection_without_evidence_stays_on_the_fallback_even_with_flag_and_deps():
    predictor, decision = select_yield_predictor(
        env={"MOLTRACE_REACTION_YIELD_GNN": "1"}, probe=lambda _m: True
    )
    assert isinstance(predictor, (SklearnSurrogatePredictor, KNNSurrogatePredictor))
    assert decision.backend == "fallback"
    assert "evidence" in decision.reason


@pytest.mark.skipif(
    importlib.util.find_spec("torch") is not None,
    reason="torch installed — the lying-probe refusal only applies without it",
)
def test_heavy_selection_with_lying_probe_fails_closed_without_torch():
    # The probe claims torch exists; construction discovers it does not and refuses honestly.
    with pytest.raises(CapabilityUnavailableError, match="torch"):
        select_yield_predictor(
            env={"MOLTRACE_REACTION_YIELD_GNN": "1"},
            probe=lambda _m: True,
            promotion_evidence=_EVIDENCE_OK,
        )


@pytest.mark.skipif(importlib.util.find_spec("torch") is None, reason="torch not installed")
def test_torch_mpnn_smoke():  # pragma: no cover - exercised only on torch-equipped hosts
    from nmrcheck.reaction_yield_models import TorchMPNNPredictor

    train = [
        YieldExample(
            {"temperature_c": 60}, 80.0, reactants_smiles=("CCO",), products_smiles=("CCOC(C)=O",)
        ),
        YieldExample(
            {"temperature_c": 80}, 60.0, reactants_smiles=("CCN",), products_smiles=("CCNC(C)=O",)
        ),
    ]
    predictor = TorchMPNNPredictor(epochs=3, mc_samples=4).fit(train)
    prediction = predictor.predict(train[0])
    assert prediction.backend == "torch_mpnn_mc_dropout"
    assert prediction.n_samples == 4
    assert 0.0 <= prediction.mean <= 200.0


# --- remediation-verification regressions (adversarial re-review) -------------------------------
def test_missing_numeric_condition_is_reported_not_silently_imputed():
    """0.0 is a legitimate value (0 degC), so a fabricated numeric feature is invisible.

    A missing `temperature_c` imputed to 0.0 can collide with genuine 0 degC training rows and
    earn a near-perfect MAE for a run whose condition was never recorded. It must be disclosed
    for exactly the reason an absent categorical is.
    """

    predictor = KNNSurrogatePredictor().fit(_TRAIN)
    prediction = predictor.predict({"catalyst": "Cat-A"})
    assert prediction.warnings, "a fabricated numeric condition must be disclosed"
    assert any("temperature_c=<missing>" in w for w in prediction.warnings)


@pytest.mark.parametrize("bad", ["n/a", None, True, "60"])
def test_non_numeric_value_in_a_numeric_column_is_reported(bad):
    predictor = KNNSurrogatePredictor().fit(_TRAIN)
    prediction = predictor.predict({"catalyst": "Cat-A", "temperature_c": bad})
    assert any("temperature_c=" in w for w in prediction.warnings)


def test_a_fully_specified_condition_carries_no_warnings():
    predictor = KNNSurrogatePredictor().fit(_TRAIN)
    prediction = predictor.predict({"catalyst": "Cat-A", "temperature_c": 70})
    assert prediction.warnings == []


def test_featurizer_records_both_missing_and_non_numeric_distinctly():
    featurizer = ConditionFeaturizer().fit([row.conditions for row in _TRAIN])
    featurizer.transform({"catalyst": "Cat-A"})
    assert featurizer.last_unknowns == ["temperature_c=<missing>"]
    featurizer.transform({"catalyst": "Cat-A", "temperature_c": "hot"})
    assert featurizer.last_unknowns == ["temperature_c=<non-numeric:'hot'>"]
