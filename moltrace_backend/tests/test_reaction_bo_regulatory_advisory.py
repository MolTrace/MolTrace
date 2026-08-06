"""Repho R4→BO seam: regulatory limits reach candidate ranking, and say so honestly.

The surrogate predicts a single scalarized objective, not per-field outcomes, so today a limit on
``impurity_percent`` has nothing to compare against. That is a real gap, and the one thing the seam
must never do is let a run read as regulatory-cleared when nothing was actually checked.

These tests pin both halves: the honest advisory while predictions are absent, and real blocking
the moment a per-field prediction exists.
"""

from nmrcheck.reaction_bo import (
    _candidate_predicted_outcome,
    _regulatory_verdict_for_candidate,
    _unchecked_limits_warning,
)
from nmrcheck.reaction_regulatory_constraints import parse_limits


def _impurity_limit(*, limit=0.10, severity="critical"):
    return {
        "id": 11,
        "constraint_type": "impurity_limit",
        "severity": severity,
        "status": "active",
        "source_action_item_ids": [4],
        "constraint_json": {
            "limit_value": limit,
            "limit_unit": "percent",
            "objective_field": "impurity_percent",
            "comparator": "max",
            "limit_basis": "ICH Q3B(R2) identification threshold",
        },
    }


# --- the honesty invariant --------------------------------------------------------------------


def test_candidate_without_per_field_predictions_is_never_reported_as_cleared():
    """A candidate the surrogate scored only scalar-wise cannot satisfy an impurity limit.

    It must come back unmeasured — not feasible, not blocked, not silently passing.
    """
    limits = parse_limits([_impurity_limit()])
    item = {"predicted_score": 82.0, "acquisition_score": 0.9, "metadata_json": {}}

    verdict = _regulatory_verdict_for_candidate(item, limits)

    assert verdict.unmeasured == ("impurity_percent",)
    assert verdict.violations == ()
    assert verdict.hard_block is False
    assert verdict.penalty == 0.0


def test_unchecked_limits_produce_a_warning_that_names_the_field_and_the_reason():
    limits = parse_limits([_impurity_limit()])
    warning = _unchecked_limits_warning(limits, ("impurity_percent",))

    assert warning is not None
    assert "impurity_percent" in warning
    # It must say the limit was NOT applied, not merely that data was missing.
    assert "not applied" in warning.lower()


def test_no_warning_when_there_are_no_active_limits():
    assert _unchecked_limits_warning([], ()) is None


# --- the seam is real, not decorative ---------------------------------------------------------


def test_a_predicted_violation_of_a_hard_limit_blocks_the_candidate():
    """The moment a per-field prediction exists, the same path must actually enforce.

    This is what stops the advisory from being a permanent no-op dressed as a guardrail.
    """
    limits = parse_limits([_impurity_limit(limit=0.10, severity="critical")])
    item = {
        "predicted_score": 91.0,
        "acquisition_score": 0.99,
        "metadata_json": {"predicted_outcome": {"impurity_percent": 0.40}},
    }

    verdict = _regulatory_verdict_for_candidate(item, limits)

    assert verdict.hard_block is True
    assert verdict.feasible is False
    assert verdict.unmeasured == ()
    assert len(verdict.violations) == 1
    violation = verdict.violations[0]
    assert violation.objective_field == "impurity_percent"
    assert violation.predicted_value == 0.40
    assert violation.limit_value == 0.10
    # Provenance must survive onto the violation so the ranking output is the audit record.
    assert violation.source_action_item_ids == (4,)
    assert "Q3B" in violation.basis


def test_predicted_outcome_is_read_from_candidate_metadata():
    item = {"metadata_json": {"predicted_outcome": {"impurity_percent": 0.2, "bogus": "x"}}}
    outcome = _candidate_predicted_outcome(item)

    assert outcome["impurity_percent"] == 0.2
    # Non-numeric entries are dropped rather than coerced into a false measurement.
    assert "bogus" not in outcome


def test_predicted_outcome_is_empty_when_the_surrogate_supplied_none():
    assert _candidate_predicted_outcome({"metadata_json": {}}) == {}
    assert _candidate_predicted_outcome({}) == {}
