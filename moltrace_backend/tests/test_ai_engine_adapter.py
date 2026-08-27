"""L0 — the seam between the API layer and the MolTrace AI/ML layer.

The invariant these tests exist to protect: **no AI/ML route records a model-derived
number that a model did not produce.** Before the adapter, ``POST /ai/predictions``
read ``confidence_score`` out of the request body and, failing that, recorded a
hard-coded ``0.82`` — a number indistinguishable downstream from a measured one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pytest

from nmrcheck import ai_engine_adapter as adapter


# --------------------------------------------------------------------------- #
# The boundary itself
# --------------------------------------------------------------------------- #
def test_stores_never_import_the_science_layer_directly() -> None:
    """The adapter is the only import boundary; the stores stay engine-free.

    If a store starts importing ``moltrace`` directly, the seam has been bypassed
    and provenance is no longer guaranteed to travel with the number.
    """

    from pathlib import Path

    root = Path(adapter.__file__).parent
    for name in ("ai_inference_store.py", "ml_model_factory_store.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "moltrace" not in source, (
            f"{name} imports the science layer directly; route it through "
            "ai_engine_adapter so provenance travels with the result"
        )


def test_engine_backed_services_reject_caller_supplied_model_numbers() -> None:
    for key in sorted(adapter.MODEL_DERIVED_REQUEST_KEYS):
        with pytest.raises(adapter.EngineInputError) as excinfo:
            adapter.assert_no_model_derived_inputs(
                "nmr_shift_prediction", {"smiles": "CCO", key: 0.99}
            )
        assert key in str(excinfo.value)


def test_non_engine_backed_services_are_not_gated() -> None:
    """A service with no engine has nothing to contradict; rejecting would only break callers."""

    assert not adapter.is_engine_backed("knowledge_quality_scorer")
    adapter.assert_no_model_derived_inputs(
        "knowledge_quality_scorer", {"confidence_score": 0.9}
    )


def test_a_result_without_provenance_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provenance is mandatory: a number with no traceable artifact is not recorded."""

    def _no_provenance(request_json: Any, session_factory: Any = None) -> adapter.EngineResult:
        return adapter.EngineResult(
            output={},
            confidence=0.9,
            uncertainty={},
            ood_status="in_domain",
            model_versions={},
            engine="test",
        )

    monkeypatch.setitem(adapter._RUNNERS, "test_service", "_no_provenance_runner")
    monkeypatch.setitem(adapter.__dict__, "_no_provenance_runner", _no_provenance)
    with pytest.raises(adapter.EngineUnavailable, match="no model provenance"):
        adapter.run_prediction("test_service", {})


# --------------------------------------------------------------------------- #
# Input validation — refusal paths before happy paths
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("request_json", "expected"),
    [
        ({}, "smiles"),
        ({"smiles": "   "}, "smiles"),
        ({"smiles": "CCO", "nuclei": "1H"}, "nuclei"),
    ],
)
def test_shift_prediction_names_its_missing_input(
    request_json: dict[str, Any], expected: str
) -> None:
    with pytest.raises(adapter.EngineInputError, match=expected):
        adapter.run_prediction("nmr_shift_prediction", request_json)


@pytest.mark.parametrize(
    ("request_json", "expected"),
    [
        ({}, "observed_shifts_ppm"),
        ({"observed_shifts_ppm": [10.0]}, "candidates"),
        (
            {"observed_shifts_ppm": [10.0], "candidates": [{}], "nucleus": "31P"},
            "nucleus",
        ),
        (
            {"observed_shifts_ppm": [10.0], "candidates": [{"candidate_id": "a"}]},
            "predicted_shifts_ppm",
        ),
    ],
)
def test_candidate_ranking_names_its_missing_input(
    request_json: dict[str, Any], expected: str
) -> None:
    with pytest.raises(adapter.EngineInputError, match=expected):
        adapter.run_prediction("nmr_candidate_ranking", request_json)


# --------------------------------------------------------------------------- #
# Candidate ranking — a real posterior, and an honest caveat
# --------------------------------------------------------------------------- #
def test_candidate_ranking_computes_a_dp4_posterior() -> None:
    result = adapter.run_prediction(
        "nmr_candidate_ranking",
        {
            "nucleus": "13C",
            "observed_shifts_ppm": [18.0, 58.0, 128.0, 140.0],
            "candidates": [
                {"candidate_id": "close", "predicted_shifts_ppm": [18.2, 58.3, 127.6, 140.4]},
                {"candidate_id": "far", "predicted_shifts_ppm": [40.0, 90.0, 100.0, 175.0]},
            ],
        },
    )
    ranked = result.output["candidates"]
    assert ranked[0]["candidate_id"] == "close"
    assert ranked[0]["dp4_probability"] > ranked[1]["dp4_probability"]
    assert result.confidence == pytest.approx(ranked[0]["dp4_probability"])
    assert result.model_versions, "a posterior must be attributable to its scoring model"
    # DP4 is closed-world; the record must say so rather than imply exhaustiveness.
    assert any("closed-world" in w for w in result.warnings)


def test_a_single_candidate_posterior_is_not_a_confidence() -> None:
    """DP4 over one candidate is 1.0 by construction — an identity, not evidence."""

    result = adapter.run_prediction(
        "nmr_candidate_ranking",
        {
            "nucleus": "13C",
            "observed_shifts_ppm": [18.0, 58.0],
            "candidates": [{"candidate_id": "only", "predicted_shifts_ppm": [18.2, 58.3]}],
        },
    )
    assert result.output["candidates"][0]["dp4_probability"] == pytest.approx(1.0)
    assert result.confidence is None, "a set of one must not record maximum confidence"
    assert any("1.0 by construction" in w for w in result.warnings)
    # The fit statistics still stand — abstaining on confidence is not refusing to answer.
    assert result.uncertainty["mae_ppm"] >= 0.0


def test_the_confidence_gate_and_the_row_flag_share_one_coverage_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One threshold, two readers -- they must not drift apart.

    The per-row ``low_coverage`` flag reads ``DP4_MIN_COVERAGE``; the gate that decides whether
    to report a confidence at all had its own literal. Equal today, independent tomorrow: tune
    the constant and a row can say coverage is fine while the confidence is withheld, or the
    reverse. Two disclosures about the same quantity that disagree are worse than either alone.
    """

    from nmrcheck import peak_categorization

    # Demand near-total coverage. The fixture below sits at 4/5 = 0.80 -- ABOVE the old
    # literal 0.75 and BELOW this, so the two readers can only agree if they read the same
    # constant. A case failing both thresholds would pass this test without proving anything.
    monkeypatch.setattr(peak_categorization, "DP4_MIN_COVERAGE", 0.99)

    result = adapter.run_prediction(
        "nmr_candidate_ranking",
        {
            "nucleus": "13C",
            "observed_shifts_ppm": [18.0, 58.0, 120.0, 140.0, 170.0],
            "candidates": [
                {"candidate_id": "a", "predicted_shifts_ppm": [18.1, 58.2, 120.3, 140.2]},
                {"candidate_id": "b", "predicted_shifts_ppm": [40.0, 90.0]},
            ],
        },
    )

    top_row = result.output["candidates"][0]
    assert top_row["low_coverage"] is True, "the row flag must follow the raised threshold"
    # The gate must follow the same constant, not a literal of its own.
    assert result.uncertainty["low_coverage"] is True
    assert result.confidence is None, (
        "coverage the row calls insufficient must also withhold the confidence"
    )


def test_the_uncertainty_block_carries_the_same_disclosure_as_the_candidate_rows() -> None:
    """The per-candidate rows got the coverage + calibration keys; ``uncertainty`` did not.

    Two frontend surfaces read the same DP4 numbers by different keys: the SpectraCheck panel
    reads the per-candidate rows, and the AI-predictions workspace reads ``uncertainty`` (keyed
    on its ``scale``). Applying the disclosure to the rows alone leaves the second surface
    reporting ``matched_peaks`` as a bare numerator -- 3 matched, with nothing saying whether
    that is 3 of 3 or 3 of 12 -- and no statement that the probability is uncalibrated.
    """

    result = adapter.run_prediction(
        "nmr_candidate_ranking",
        {
            "nucleus": "13C",
            # Twelve observed signals; each candidate can explain at most a few of them.
            "observed_shifts_ppm": [10.0, 18.0, 25.0, 33.0, 41.0, 58.0, 66.0, 74.0, 90.0, 110.0, 128.0, 170.0],
            "candidates": [
                {"candidate_id": "a", "predicted_shifts_ppm": [18.1, 58.2]},
                {"candidate_id": "b", "predicted_shifts_ppm": [41.4, 128.6]},
            ],
        },
    )

    unc = result.uncertainty
    # The denominator that makes matched_peaks readable.
    assert unc["observed_peak_count"] == 12
    assert unc["matched_fraction"] == pytest.approx(unc["matched_peaks"] / 12)
    # The same three disclosure keys the candidate rows carry.
    assert unc["probability_is_calibrated"] is False
    assert unc["error_basis"] == "matched_peaks_only"
    assert unc["low_coverage"] is True  # two matches out of twelve signals

    # And the row-level disclosure is unchanged -- this adds a reader, it does not move one.
    row = result.output["candidates"][0]
    for key in ("observed_peak_count", "matched_fraction", "low_coverage", "error_basis", "probability_is_calibrated"):
        assert key in row, f"row lost {key}"

    # Coverage this poor must not report a confidence at all.
    assert result.confidence is None


# --------------------------------------------------------------------------- #
# The promotion gate
# --------------------------------------------------------------------------- #
_BASE = {
    "top1_accuracy": 0.80,
    "ece": 0.030,
    "false_confirmation_rate": 0.020,
}


def test_no_incumbent_is_a_baseline_not_a_promotion() -> None:
    verdict = adapter.dominance_verdict(_BASE, None)
    assert not verdict.passed
    assert not verdict.applicable, "a first model must not be blocked by a gate with no incumbent"
    assert "baseline decision" in verdict.reason


def test_dropping_a_safety_metric_is_not_a_way_around_the_gate() -> None:
    """The asymmetric hole: one side reports ``ece``, the other omits it."""

    candidate = {"top1_accuracy": 0.99, "false_confirmation_rate": 0.001}
    verdict = adapter.dominance_verdict(candidate, _BASE)
    assert verdict.applicable and not verdict.passed
    assert "ece" in verdict.reason
    # ... and symmetrically, when the incumbent is the one missing it.
    reverse = adapter.dominance_verdict(_BASE, candidate)
    assert reverse.applicable and not reverse.passed
    assert "ece" in reverse.reason


def test_a_task_the_gate_cannot_score_is_not_refused() -> None:
    """A reaction-yield surrogate reports mae/r2; blocking it would be a false gate."""

    verdict = adapter.dominance_verdict({"mae": 0.09, "r2": 0.9}, {"mae": 0.11, "r2": 0.82})
    assert not verdict.applicable
    assert not verdict.passed
    assert "no metric this promotion gate compares" in verdict.reason


def test_a_task_with_no_safety_metrics_still_compares_what_it_has() -> None:
    verdict = adapter.dominance_verdict({"top1_accuracy": 0.99}, {"top1_accuracy": 0.10})
    assert verdict.applicable and verdict.passed
    assert "no safety-critical metric was reported" in verdict.reason


def test_safety_critical_regression_is_refused_however_small() -> None:
    candidate = {**_BASE, "top1_accuracy": 0.95, "ece": 0.0301}
    verdict = adapter.dominance_verdict(candidate, _BASE)
    assert not verdict.passed
    assert "ece" in verdict.reason
    assert "may not regress at all" in verdict.reason


def test_accuracy_gain_does_not_buy_a_false_confirmation_regression() -> None:
    candidate = {**_BASE, "top1_accuracy": 0.99, "false_confirmation_rate": 0.05}
    verdict = adapter.dominance_verdict(candidate, _BASE)
    assert not verdict.passed
    assert "false_confirmation_rate" in verdict.reason


def test_matching_on_everything_is_not_a_promotion() -> None:
    verdict = adapter.dominance_verdict(dict(_BASE), _BASE)
    assert not verdict.passed
    assert "improves none" in verdict.reason


def test_a_strict_improvement_with_no_regression_passes() -> None:
    candidate = {**_BASE, "top1_accuracy": 0.86, "ece": 0.028}
    verdict = adapter.dominance_verdict(candidate, _BASE)
    assert verdict.passed
    assert "top1_accuracy" in verdict.improvements
    assert not verdict.regressions


def test_tolerance_applies_to_non_safety_metrics_only() -> None:
    """A sub-tolerance wobble on accuracy is noise; the same on ECE is a regression."""

    from moltrace.spectroscopy.eval.harness import DEFAULT_TOLERANCES

    wobble = DEFAULT_TOLERANCES["top1_accuracy"] / 2.0
    candidate = {**_BASE, "top1_accuracy": 0.80 - wobble, "ece": 0.025}
    verdict = adapter.dominance_verdict(candidate, _BASE)
    assert verdict.passed, verdict.reason


# --------------------------------------------------------------------------- #
# Confidence derivation — the arbiter's scale, not a new one
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Atom:
    nucleus: str
    uncertainty_ppm: float
    layer: str = "layer1_nmrnet_pretrained"


@dataclass(frozen=True)
class _Routed:
    predictions: tuple[_Atom, ...]
    warnings: tuple[str, ...] = ()


def test_confidence_at_the_reference_sigma_is_not_one() -> None:
    """σ = σ_ref maps to the verifier's 'medium' significance, not to certainty."""

    from moltrace.spectroscopy.ai.confidence import confidence_from_sigma

    assert confidence_from_sigma(2.0, "13C") == pytest.approx(math.tanh(4.0 / 3.0), abs=1e-9)
    assert confidence_from_sigma(0.10, "1H") == pytest.approx(math.tanh(4.0 / 3.0), abs=1e-9)


def test_an_unusable_sigma_contributes_no_confidence() -> None:
    from moltrace.spectroscopy.ai.confidence import confidence_from_sigma

    assert confidence_from_sigma(float("nan"), "13C") == 0.0
    assert confidence_from_sigma(0.0, "13C") == 0.0


def test_the_pre_kb_production_sigma_reports_as_out_of_domain() -> None:
    """The 35 ppm median ¹³C σ that reached production is an abstention, and says so.

    This is the regression guard for the defect that made L0 necessary: the
    uncertainty was always honest, it was simply never aggregated, so an abstention
    could stand in for a prediction indefinitely.
    """

    from moltrace.spectroscopy.ai.confidence import routed_prediction_confidence

    summary = routed_prediction_confidence(
        _Routed(tuple(_Atom("13C", 35.0, "fallback_hose") for _ in range(10)))
    )
    assert summary.score == pytest.approx(0.143, abs=0.005)
    assert summary.ood_status == "out_of_domain"
    assert any("cannot discriminate" in w for w in summary.warnings)
    assert summary.uncertainty["fallback_fraction"] == 1.0


def test_a_sharp_prediction_is_in_domain() -> None:
    from moltrace.spectroscopy.ai.confidence import routed_prediction_confidence

    summary = routed_prediction_confidence(
        _Routed(tuple(_Atom("13C", 0.5) for _ in range(10)))
    )
    assert summary.ood_status == "in_domain"
    assert summary.score > 0.9
    assert summary.uncertainty["per_nucleus"]["13C"]["median_sigma_ppm"] == 0.5


def test_no_atoms_yields_no_confidence_rather_than_a_default() -> None:
    from moltrace.spectroscopy.ai.confidence import routed_prediction_confidence

    summary = routed_prediction_confidence(_Routed(()))
    assert summary.score == 0.0
    assert summary.ood_status == "not_assessed"
    assert any("no atoms" in w for w in summary.warnings)


# --------------------------------------------------------------------------- #
# Candidate ranking — coverage disclosure (P5 §6)
# --------------------------------------------------------------------------- #
def test_candidate_ranking_reports_its_denominator_and_basis() -> None:
    """`matched_peaks` alone is unreadable: 2 looks the same as 2 of 2 or 2 of 8.

    The SpectraCheck panel path has carried this disclosure since the coverage
    work (docs/fe_handoff_dp4_ranking_coverage.md); this surface emitted the same
    numbers bare while feeding an automated review threshold.
    """
    result = adapter.run_prediction(
        "nmr_candidate_ranking",
        {
            "nucleus": "13C",
            "observed_shifts_ppm": [18.0, 58.0, 128.0, 140.0],
            "candidates": [
                {"candidate_id": "close", "predicted_shifts_ppm": [18.2, 58.3, 127.6, 140.4]},
                {"candidate_id": "far", "predicted_shifts_ppm": [40.0, 90.0, 100.0, 175.0]},
            ],
        },
    )
    row = result.output["candidates"][0]
    assert row["observed_peak_count"] == 4
    assert 0.0 <= row["matched_fraction"] <= 1.0
    assert row["error_basis"] == "matched_peaks_only"
    # A ranking share is not a calibrated probability of correctness, and the
    # record must say so rather than let a consumer assume it.
    assert row["probability_is_calibrated"] is False
    assert row["probability_basis"]
    assert any("not calibrated" in w or "not\ncalibrated" in w or "calibrated" in w
               for w in result.warnings)


def test_a_leading_candidate_that_explains_little_records_no_confidence() -> None:
    """A DP4 share is computed over MATCHED peaks only.

    So a candidate matching a minority of the spectrum can still take most of the
    probability mass. Reporting that as confidence would clear a review threshold
    on the strength of a fit to a fraction of the evidence — the same defect the
    single-candidate case already guards against.
    """
    result = adapter.run_prediction(
        "nmr_candidate_ranking",
        {
            "nucleus": "13C",
            # Eight observed signals; each candidate predicts only two, so the
            # leader can explain at most a quarter of what was measured.
            "observed_shifts_ppm": [18.0, 58.0, 128.0, 140.0, 22.0, 71.0, 133.0, 155.0],
            "candidates": [
                {"candidate_id": "partial", "predicted_shifts_ppm": [18.1, 58.2]},
                {"candidate_id": "worse", "predicted_shifts_ppm": [95.0, 99.0]},
            ],
        },
    )
    top = result.output["candidates"][0]
    assert top["low_coverage"] is True
    assert top["matched_fraction"] < 0.75
    assert result.confidence is None, (
        "a share carried by a minority of the spectrum must not be recorded as confidence"
    )
    assert any("observed signals" in w for w in result.warnings)
