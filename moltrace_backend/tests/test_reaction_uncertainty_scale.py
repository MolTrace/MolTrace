"""An uncertainty band written for 0-1 must not be applied to a posterior std in percent.

`_confidence_label` bands at >= 0.75 -> high_uncertainty and >= 0.35 -> moderate_uncertainty.
Two of the four predictor branches produce a unit-free 0-1 quantity (`_fallback_predictions`
emits the constants 1.0/0.5; the TPE-like branch emits `max(0.05, 1.0 - affinity)`), and those
bands suit them. The GP and forest branches emit a POSTERIOR STANDARD DEVIATION in objective
units, and `_score_outcome` returns percentages -- so the std is in percentage points.

Measured by running the real models over a 36-candidate grid: GP std ran 0.89-13.57 and the
label was `high_uncertainty` 36/36 at every training size from 5 to 60. The control that shows
it reads UNITS rather than confidence: the identical data on a 0-1 scale gives GP max 0.110 and
`lower_uncertainty` 36/36. Same model, same posterior, opposite label.

A second reader thresholds the same value -- `_candidate_label`'s `>= 0.5` -> exploratory
candidate -- so fixing only the first would leave the remediation half-applied.

No threshold in objective units is invented here. There is no measured distribution of Repho
posterior stds to place one on, and this file's own precedent is that a quantity is better
reported unlabelled than compared against a band that was never meant for it.
"""

from __future__ import annotations

from nmrcheck.reaction_bo import _candidate_label, _confidence_label

_UNIT_FREE = "unit_interval"
_OBJECTIVE_UNITS = "objective_units"


def test_a_unit_free_uncertainty_is_still_banded() -> None:
    """The branches the bands were written for keep their labels."""

    assert _confidence_label({"uncertainty": 0.9, "uncertainty_scale": _UNIT_FREE}, 20) == "high_uncertainty"
    assert _confidence_label({"uncertainty": 0.5, "uncertainty_scale": _UNIT_FREE}, 20) == "moderate_uncertainty"
    assert _confidence_label({"uncertainty": 0.1, "uncertainty_scale": _UNIT_FREE}, 20) == "lower_uncertainty"


def test_a_posterior_std_is_reported_unlabelled_not_mislabelled() -> None:
    """A std of 3.7 percentage points is not "0.75 uncertain"; it is not on that scale at all."""

    for std in (0.89, 3.70, 13.57):  # the measured GP range
        label = _confidence_label({"uncertainty": std, "uncertainty_scale": _OBJECTIVE_UNITS}, 20)
        assert label == "uncertain", f"std {std} in objective units was labelled {label}"


def test_the_low_data_short_circuit_is_unchanged() -> None:
    """Below five observations the label never reached the numeric bands anyway."""

    assert _confidence_label({"uncertainty": 1.0, "uncertainty_scale": _UNIT_FREE}, 4) == "low_data"
    assert _confidence_label({"uncertainty": 8.2, "uncertainty_scale": _OBJECTIVE_UNITS}, 4) == "low_data"


def test_a_missing_uncertainty_still_reads_uncertain() -> None:
    assert _confidence_label({"uncertainty": None}, 20) == "uncertain"
    assert _confidence_label({}, 20) == "uncertain"


def test_the_second_reader_does_not_call_a_std_exploratory() -> None:
    """`_candidate_label` gates the SAME value at >= 0.5.

    Every GP std measured exceeded 0.5, so a model-backed candidate with no expected
    improvement was always 'exploratory' and `requires_human_review` was unreachable by merit.
    """

    common = {"training_count": 20, "cost_aware": False, "safety_status": "ok"}

    # Unit-free: 0.6 of a 0-1 quantity genuinely is exploratory.
    assert (
        _candidate_label(
            {"expected_improvement": 0.0, "uncertainty": 0.6, "uncertainty_scale": _UNIT_FREE},
            **common,
        )
        == "exploratory_candidate"
    )

    # Objective units: 3.7 percentage points says nothing about that band.
    assert (
        _candidate_label(
            {"expected_improvement": 0.0, "uncertainty": 3.7, "uncertainty_scale": _OBJECTIVE_UNITS},
            **common,
        )
        == "requires_human_review"
    )
