"""Unit tests for the Repho R5 DMTA-loop engine (pure: no DB/HTTP/clock)."""

from datetime import datetime

from nmrcheck.reaction_loop import (
    DMTA_SEQUENCE,
    build_cycle_metrics_payload,
    compute_loop_metrics,
    evaluate_propose_next,
)

# --- evaluate_propose_next (the human gate) --------------------------------------------------


def test_continue_decision_allows_proposing():
    v = evaluate_propose_next("continue_optimization", "clear")
    assert v.allowed is True
    assert v.requires_human_signoff_before_execution is True
    assert v.execution_blocked_by_safety is False


def test_no_decision_blocks_proposing():
    v = evaluate_propose_next(None)
    assert v.allowed is False
    assert "No cycle decision" in v.reason
    assert v.requires_human_signoff_before_execution is True


def test_non_continue_decisions_block_proposing():
    for decision in ("pause", "stop_success", "stop_insufficient_progress",
                     "revise_design_space", "revise_objective", "requires_review"):
        v = evaluate_propose_next(decision)
        assert v.allowed is False, decision
        assert decision in v.reason


def test_stop_decision_reads_as_stopped():
    assert "stopped" in evaluate_propose_next("stop_success").reason
    assert "held" in evaluate_propose_next("pause").reason


def test_blocked_safety_gate_is_surfaced_but_does_not_stop_a_proposal():
    # A continue decision still proposes (decision-support); the blocked gate is flagged and will
    # stop EXECUTION (enforced by the R6 gate), not the proposal.
    v = evaluate_propose_next("continue_optimization", "blocked")
    assert v.allowed is True
    assert v.execution_blocked_by_safety is True
    assert v.requires_human_signoff_before_execution is True


# --- compute_loop_metrics (metering) ---------------------------------------------------------


def test_experiments_to_target_is_first_to_meet_target():
    m = compute_loop_metrics(experiment_scores=[40.0, 55.0, 72.0, 80.0], objective_target=70.0)
    assert m.experiments_to_target == 3  # 72.0 is the first >= 70
    assert m.best_objective == 80.0
    assert m.target_met is True
    assert m.objective_gap == -10.0  # target - best (overshot)
    assert m.total_experiments == 4


def test_target_not_met_yields_none_and_positive_gap():
    m = compute_loop_metrics(experiment_scores=[10.0, 20.0, 30.0], objective_target=50.0)
    assert m.experiments_to_target is None
    assert m.target_met is False
    assert m.objective_gap == 20.0  # still 20 short
    assert m.best_objective == 30.0


def test_no_target_or_no_scores_is_safe():
    m = compute_loop_metrics(experiment_scores=[5.0, 9.0])
    assert m.experiments_to_target is None
    assert m.objective_target is None
    assert m.best_objective == 9.0
    empty = compute_loop_metrics()
    assert empty.total_experiments == 0
    assert empty.best_objective is None


def test_latency_and_phase_latencies_from_timestamps():
    t0 = datetime(2026, 1, 1, 9, 0, 0)
    m = compute_loop_metrics(
        created_at=t0,
        completed_at=datetime(2026, 1, 1, 17, 0, 0),  # 8 hours
        step_timestamps={
            "propose": t0,
            "safety_gate": datetime(2026, 1, 1, 9, 30, 0),  # +30 min
            "make": datetime(2026, 1, 1, 13, 0, 0),  # +3.5 h after safety
            # 'test'/'learn' absent -> skipped; next present is 'decision'
            "decision": datetime(2026, 1, 1, 16, 0, 0),
        },
        new_experiment_count=4,
    )
    assert m.latency_seconds == 8 * 3600
    pl = m.phase_latencies_seconds
    assert pl["propose_to_safety_gate"] == 30 * 60
    assert pl["safety_gate_to_make"] == int(3.5 * 3600)
    assert pl["make_to_decision"] == 3 * 3600  # consecutive *present* steps
    assert m.new_experiments == 4


def test_iso_string_timestamps_are_coerced():
    m = compute_loop_metrics(
        created_at="2026-01-01T09:00:00", completed_at="2026-01-01T10:00:00"
    )
    assert m.latency_seconds == 3600


# --- build_cycle_metrics_payload (persistence contract) --------------------------------------


def test_metrics_payload_bundles_metrics_and_provenance():
    m = compute_loop_metrics(experiment_scores=[80.0], objective_target=70.0)
    payload = build_cycle_metrics_payload(
        m,
        bo_run_id=12,
        surrogate_model_version="gp-matern-2.5",
        spectracheck_session_ids=[3, 4],
        spectracheck_model_version_ids=[7],
    )
    assert payload["metrics"]["best_objective"] == 80.0
    assert payload["provenance"]["bo_run_id"] == 12
    assert payload["provenance"]["spectracheck_session_ids"] == [3, 4]
    assert payload["dmta_sequence"] == list(DMTA_SEQUENCE)
    assert payload["engine"] == "reaction_loop.v1"
