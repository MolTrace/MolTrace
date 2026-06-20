"""Unit tests for the Repho R4 regulatory-constraint enforcement engine (pure, no DB/HTTP)."""

from nmrcheck.reaction_regulatory_constraints import (
    enforce,
    evaluate_candidate,
    parse_limit,
    parse_limits,
)


def _impurity_constraint(
    *, limit=0.10, severity="high", status="active", cid=5, action_ids=(3,), **extra
):
    body = {
        "limit_value": limit,
        "limit_unit": "percent",
        "objective_field": "impurity_percent",
        "comparator": "max",
        "limit_basis": "ICH Q3B(R2) identification threshold",
    }
    body.update(extra)
    return {
        "id": cid,
        "constraint_type": "impurity_limit",
        "severity": severity,
        "status": status,
        "source_action_item_ids": list(action_ids),
        "constraint_json": body,
    }


# --- parse_limit -----------------------------------------------------------------------------


def test_parse_limit_reads_explicit_fields_and_provenance():
    limit = parse_limit(_impurity_constraint())
    assert limit is not None
    assert limit.objective_field == "impurity_percent"
    assert limit.comparator == "max"
    assert limit.limit_value == 0.10
    assert limit.severity == "high"
    assert limit.is_hard is True
    assert limit.constraint_id == 5
    assert limit.source_action_item_ids == (3,)
    assert "Q3B" in limit.basis


def test_parse_limit_uses_type_default_field_when_unspecified():
    c = _impurity_constraint()
    c["constraint_json"].pop("objective_field")
    c["constraint_json"].pop("comparator")
    limit = parse_limit(c)
    assert limit is not None
    assert limit.objective_field == "impurity_percent"  # default for impurity_limit
    assert limit.comparator == "max"


def test_parse_limit_returns_none_without_numeric_limit():
    c = _impurity_constraint()
    c["constraint_json"].pop("limit_value")
    assert parse_limit(c) is None  # advisory, not enforceable


def test_parse_limit_skips_draft_and_archived():
    assert parse_limit(_impurity_constraint(status="draft")) is None
    assert parse_limit(_impurity_constraint(status="archived")) is None
    assert parse_limit(_impurity_constraint(status="reviewed")) is not None


def test_parse_limit_min_comparator_for_purity_requirement():
    c = {
        "id": 9,
        "constraint_type": "qnmr_validation_requirement",
        "severity": "medium",
        "status": "active",
        "constraint_json": {"limit_value": 99.0},  # default field nmr_purity_percent, min
    }
    limit = parse_limit(c)
    assert limit is not None
    assert limit.objective_field == "nmr_purity_percent"
    assert limit.comparator == "min"


def test_parse_limits_drops_non_enforceable():
    rows = [_impurity_constraint(), _impurity_constraint(status="draft", cid=6)]
    rows[0]["constraint_json"]["limit_value"] = 0.10
    limits = parse_limits(rows)
    assert len(limits) == 1


# --- evaluate_candidate ----------------------------------------------------------------------


def test_candidate_within_limit_is_feasible():
    limits = parse_limits([_impurity_constraint(limit=0.10)])
    v = evaluate_candidate({"impurity_percent": 0.05}, limits)
    assert v.feasible is True
    assert v.hard_block is False
    assert v.violations == ()
    assert v.penalty == 0.0
    assert v.applied_constraint_ids == (5,)


def test_candidate_over_hard_limit_is_blocked_with_provenance():
    limits = parse_limits([_impurity_constraint(limit=0.10, severity="critical")])
    v = evaluate_candidate({"impurity_percent": 0.25}, limits)
    assert v.hard_block is True
    assert v.feasible is False
    assert len(v.violations) == 1
    viol = v.violations[0]
    assert viol.predicted_value == 0.25
    assert viol.limit_value == 0.10
    assert viol.is_hard is True
    assert viol.source_action_item_ids == (3,)
    # human-readable reason for the rationale/audit trail
    assert "exceeds" in v.summary()["violation_reasons"][0]


def test_low_severity_violation_penalises_but_does_not_block():
    limits = parse_limits([_impurity_constraint(limit=0.10, severity="low")])
    v = evaluate_candidate({"impurity_percent": 0.20}, limits)
    assert v.hard_block is False
    assert v.feasible is True  # soft: ranked lower, not filtered
    assert v.penalty > 0.0
    assert len(v.violations) == 1


def test_unmeasured_field_is_reported_not_silently_passed():
    limits = parse_limits([_impurity_constraint(limit=0.10)])
    v = evaluate_candidate({"yield_percent": 80.0}, limits)  # no impurity_percent
    assert v.unmeasured == ("impurity_percent",)
    assert v.violations == ()
    assert v.feasible is True  # cannot enforce what was not measured (advisory)


def test_at_exactly_the_limit_is_feasible():
    limits = parse_limits([_impurity_constraint(limit=0.10)])
    v = evaluate_candidate({"impurity_percent": 0.10}, limits)
    assert v.feasible is True
    assert v.violations == ()


def test_min_comparator_violation_when_below_floor():
    c = {
        "id": 9,
        "constraint_type": "qnmr_validation_requirement",
        "severity": "high",
        "status": "active",
        "constraint_json": {"limit_value": 99.0},
    }
    limits = parse_limits([c])
    below = evaluate_candidate({"nmr_purity_percent": 97.0}, limits)
    assert below.hard_block is True
    assert "is below" in below.summary()["violation_reasons"][0]
    at_or_above = evaluate_candidate({"nmr_purity_percent": 99.5}, limits)
    assert at_or_above.feasible is True


def test_multiple_limits_aggregate_and_penalty_caps_at_one():
    limits = parse_limits(
        [
            _impurity_constraint(limit=0.10, severity="low", cid=1, action_ids=(11,)),
            {
                "id": 2,
                "constraint_type": "impurity_limit",
                "severity": "medium",
                "status": "active",
                "constraint_json": {
                    "limit_value": 50.0,
                    "objective_field": "lcms_area_percent",
                    "comparator": "max",
                    "limit_basis": "secondary impurity ceiling",
                },
            },
        ]
    )
    v = evaluate_candidate({"impurity_percent": 5.0, "lcms_area_percent": 99.0}, limits)
    assert len(v.violations) == 2
    assert 0.0 < v.penalty <= 1.0
    assert set(v.applied_constraint_ids) == {1, 2}


# --- enforce (batch) -------------------------------------------------------------------------


def test_enforce_batch_returns_verdicts_and_diagnostics():
    constraints = [_impurity_constraint(limit=0.10, severity="critical")]
    candidates = [
        {"impurity_percent": 0.02},  # feasible
        {"impurity_percent": 0.40},  # hard-blocked
        {"yield_percent": 90.0},  # unmeasured
    ]
    result = enforce(candidates, constraints)
    assert [v.hard_block for v in result.verdicts] == [False, True, False]
    diag = result.diagnostics()
    assert diag["enforced_constraint_count"] == 1
    assert diag["active_constraint_ids"] == [5]
    assert diag["candidates_evaluated"] == 3
    assert diag["candidates_hard_blocked"] == 1


def test_enforce_with_no_enforceable_constraints_is_a_noop():
    # un-enriched constraints (no limit_value) -> nothing enforced -> all feasible
    bare = [{"id": 1, "constraint_type": "impurity_limit", "severity": "high",
             "status": "active", "constraint_json": {"source_action_type": "impurity_identification"}}]
    result = enforce([{"impurity_percent": 99.0}], bare)
    assert result.verdicts[0].feasible is True
    assert result.diagnostics()["enforced_constraint_count"] == 0
