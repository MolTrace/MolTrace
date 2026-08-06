"""Unit tests for the Repho R11 eval harness (pure: no DB/HTTP/clock/randomness).

Covers gold-set integrity (checksum, drift, malformed/duplicate/non-finite/non-canonical), every
metric on a frozen fixture trace, safety-flag recall (the blocking dimension), the promotion gate's
CI exit codes, and the R10 gold-exclusion bridge.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from nmrcheck import reaction_priors
from nmrcheck.reaction_eval import (
    EXIT_BLOCKED,
    EXIT_DRIFT,
    EXIT_OK,
    CampaignRun,
    CampaignStep,
    ReactionEvalError,
    condition_key,
    evaluate_campaign,
    gate,
    gold_set_checksum,
    load_gold_set,
    run_benchmark_gate,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "reaction_eval" / "gold_set_v1.json"


def _payload() -> dict:
    return json.loads(_FIXTURE.read_text())


def _tasks():
    return load_gold_set(_payload())


def _checksum() -> str:
    return _payload()["checksum"]


def _cond(catalyst: str, base: str, temp) -> dict:
    return {"catalyst": catalyst, "base": base, "temperature_c": temp}


def _step(catalyst, base, temp, objective, **kwargs) -> CampaignStep:
    return CampaignStep(conditions=_cond(catalyst, base, temp), objective=objective, **kwargs)


def _evaluate(version: str, runs, **kwargs):
    return evaluate_campaign(version, runs, _tasks(), gold_checksum=_checksum(), **kwargs)


def _run_reaching_target() -> CampaignRun:
    """Objectives match the frozen surface; reaches the 85 target on step 4 (step 3 is 84)."""
    return CampaignRun(
        task_id="bh_sim_v1",
        steps=[
            _step("Pd-dppf", "K3PO4", 60, 33.0, latency_seconds=10.0),
            _step("Pd-SPhos", "KOtBu", 80, 71.0, latency_seconds=10.0),
            _step("Pd-XPhos", "KOtBu", 60, 84.0, latency_seconds=10.0),
            _step("Pd-XPhos", "KOtBu", 80, 91.0, latency_seconds=10.0),
        ],
    )


# --- gold set: frozen, checksummed, refuse-on-drift -------------------------------------------
def test_gold_set_loads_and_checksum_is_self_consistent():
    payload = _payload()
    assert payload["checksum"] == gold_set_checksum(payload)
    task = load_gold_set(payload)[0]
    assert task.task_id == "bh_sim_v1"
    assert task.optimum_objective == 91.0
    assert len(task.surface) == 8
    assert len(task.hazardous_condition_keys) == 1
    assert task.outcome_names == ("yield", "impurity")
    assert task.hypervolume_reference == (0.0, 30.0)


def test_gold_set_refuses_to_run_on_drift():
    payload = _payload()
    key = next(iter(payload["tasks"][0]["surface"]))
    payload["tasks"][0]["surface"][key] += 1.0
    with pytest.raises(ReactionEvalError, match="drift"):
        load_gold_set(payload)


def test_gold_set_refuses_missing_checksum():
    payload = _payload()
    payload.pop("checksum")
    with pytest.raises(ReactionEvalError, match="no checksum"):
        load_gold_set(payload)


def _refrozen(mutate) -> dict:
    """A deliberately re-frozen payload — checksum valid, content changed."""
    payload = _payload()
    mutate(payload)
    payload.pop("checksum", None)
    payload["checksum"] = gold_set_checksum(payload)
    return payload


def test_malformed_task_raises_eval_error_not_a_bare_python_exception():
    # A missing required field must map to EXIT_DRIFT, not surface as KeyError (which CI would
    # read as exit 1 == "candidate not promotable").
    payload = _refrozen(lambda p: p["tasks"][0].pop("objective_target"))
    with pytest.raises(ReactionEvalError, match="Malformed gold task"):
        load_gold_set(payload)


def test_duplicate_task_ids_are_rejected():
    payload = _refrozen(lambda p: p["tasks"].append(dict(p["tasks"][0])))
    with pytest.raises(ReactionEvalError, match="Duplicate gold task id"):
        load_gold_set(payload)


def test_non_finite_gold_numbers_are_rejected():
    # NaN optimum would make cumulative_regret silently 0.0 (a perfect score).
    payload = _refrozen(lambda p: p["tasks"][0].__setitem__("optimum_objective", float("nan")))
    with pytest.raises(ReactionEvalError, match="finite"):
        load_gold_set(payload)


def test_non_canonical_hazardous_key_is_rejected():
    # A key that no step could ever match would make recall silently, permanently 1.0.
    payload = _refrozen(
        lambda p: p["tasks"][0].__setitem__(
            "hazardous_condition_keys", ['{"temperature_c":100,"base":"DBU","catalyst":"Pd-dppf"}']
        )
    )
    with pytest.raises(ReactionEvalError, match="not canonical"):
        load_gold_set(payload)


def test_hazardous_key_absent_from_surface_is_rejected():
    orphan = condition_key({"catalyst": "Nope", "base": "None", "temperature_c": 1})
    payload = _refrozen(
        lambda p: p["tasks"][0].__setitem__("hazardous_condition_keys", [orphan])
    )
    with pytest.raises(ReactionEvalError, match="not present in the frozen surface"):
        load_gold_set(payload)


# --- metrics ----------------------------------------------------------------------------------
def test_metric_vector_on_fixture_trace():
    m = _evaluate("candidate.v2", [_run_reaching_target()]).metrics
    assert m["experiments_to_target_median"] == 4.0
    assert m["best_objective"] == 91.0
    # Regret: (91-33)+(91-71)+(91-84)+(91-91) = 58+20+7+0 = 85.
    assert m["cumulative_regret"] == 85.0
    assert m["reproduction_accuracy"] == 1.0
    assert m["iteration_latency_seconds"] == 10.0


def test_target_never_reached_counts_budget_plus_one():
    run = CampaignRun(
        task_id="bh_sim_v1",
        steps=[_step("Pd-dppf", "K3PO4", 60, 33.0), _step("Pd-dppf", "KOtBu", 80, 48.0)],
    )
    result = _evaluate("m", [run])
    assert result.metrics["experiments_to_target_median"] == 3.0
    assert result.metrics["reproduction_accuracy"] == 0.0


def test_trace_contradicting_the_frozen_surface_is_refused():
    # Same grid point, inflated objective -> the benchmark refuses to score it.
    run = CampaignRun(task_id="bh_sim_v1", steps=[_step("Pd-dppf", "K3PO4", 60, 99.0)])
    with pytest.raises(ReactionEvalError, match="contradicts the frozen gold surface"):
        _evaluate("cheater", [run])


def test_non_finite_step_objective_is_refused():
    run = CampaignRun(task_id="bh_sim_v1", steps=[_step("Off", "Grid", 5, float("inf"))])
    with pytest.raises(ReactionEvalError, match="finite"):
        _evaluate("m", [run])


def test_latency_is_omitted_not_defaulted_when_absent():
    # 0.0 is the BEST value on a lower-is-better dimension; defaulting would be a silent win.
    run = CampaignRun(task_id="bh_sim_v1", steps=[_step("Pd-XPhos", "KOtBu", 80, 91.0)])
    result = _evaluate("m", [run])
    assert "iteration_latency_seconds" not in result.metrics
    assert any("latenc" in w for w in result.warnings)


# --- safety-flag recall (the blocking dimension) -----------------------------------------------
def test_safety_flag_recall_counts_hazardous_conditions():
    missed = _evaluate(
        "m",
        [CampaignRun("bh_sim_v1", [_step("Pd-dppf", "DBU", 100, 22.0, safety_flagged=False)])],
    )
    assert missed.safety_flag_recall == 0.0
    caught = _evaluate(
        "m",
        [CampaignRun("bh_sim_v1", [_step("Pd-dppf", "DBU", 100, 22.0, safety_flagged=True)])],
    )
    assert caught.safety_flag_recall == 1.0


def test_numeric_type_drift_still_counts_a_hazardous_encounter():
    # A float temperature must not make the hazard invisible (which would report a perfect 1.0).
    drifted = _evaluate(
        "m",
        [CampaignRun("bh_sim_v1", [_step("Pd-dppf", "DBU", 100.0, 22.0, safety_flagged=False)])],
    )
    assert drifted.safety_flag_recall == 0.0


def test_vacuous_recall_is_warned():
    result = _evaluate("m", [_run_reaching_target()])
    assert result.safety_flag_recall == 1.0
    assert any("vacuously" in w for w in result.warnings)


# --- calibration + hypervolume ------------------------------------------------------------------
def test_calibration_error_bounds():
    good = _evaluate(
        "m",
        [
            CampaignRun(
                "bh_sim_v1",
                [
                    _step(
                        "Pd-XPhos", "KOtBu", 80, 91.0,
                        predicted_objective=91.0, predicted_confidence=1.0,
                    )
                ],
            )
        ],
    )
    assert good.metrics["calibration_error"] == 0.0
    bad = _evaluate(
        "m",
        [
            CampaignRun(
                "bh_sim_v1",
                [
                    _step(
                        "Pd-XPhos", "KOtBu", 80, 91.0,
                        predicted_objective=10.0, predicted_confidence=1.0,
                    )
                ],
            )
        ],
    )
    assert bad.metrics["calibration_error"] == 1.0


def _hv_run(order_reversed: bool = False) -> CampaignRun:
    a = {"yield": 91.0, "impurity": 2.0}
    b = {"yield": 84.0, "impurity": 5.0}
    if order_reversed:  # different dict insertion order, same chemistry
        a = {"impurity": 2.0, "yield": 91.0}
        b = {"impurity": 5.0, "yield": 84.0}
    return CampaignRun(
        task_id="bh_sim_v1",
        steps=[
            _step("Pd-XPhos", "KOtBu", 80, 91.0, outcomes=a),
            _step("Pd-XPhos", "KOtBu", 60, 84.0, outcomes=b),
        ],
    )


def test_hypervolume_uses_frozen_reference_and_is_key_order_independent():
    straight = _evaluate("m", [_hv_run()]).metrics["hypervolume"]
    reversed_keys = _evaluate("m", [_hv_run(order_reversed=True)]).metrics["hypervolume"]
    assert straight > 0.0
    assert straight == reversed_keys  # aligned by frozen name order, not insertion order


def test_hypervolume_skipped_with_warning_when_outcome_missing():
    run = CampaignRun(
        task_id="bh_sim_v1",
        steps=[_step("Pd-XPhos", "KOtBu", 80, 91.0, outcomes={"yield": 91.0})],  # no impurity
    )
    result = _evaluate("m", [run])
    assert "hypervolume" not in result.metrics
    assert any("hypervolume skipped" in w for w in result.warnings)


def test_unknown_task_raises():
    with pytest.raises(ReactionEvalError, match="unknown gold task"):
        _evaluate("m", [CampaignRun("nope", [_step("a", "b", 1, 1.0)])])


# --- the blocking gate + CI exit codes ----------------------------------------------------------
def _result(version: str, *, to_target: float, recall: float, regret: float = 85.0):
    base = _evaluate(version, [_run_reaching_target()])
    base.metrics["experiments_to_target_median"] = to_target
    base.metrics["cumulative_regret"] = regret
    base.safety_flag_recall = recall
    return base


def test_gate_ok_when_dominant_and_recall_held():
    outcome = gate(
        _result("candidate.v2", to_target=4.0, recall=0.97, regret=85.0),
        _result("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0),
    )
    assert outcome.exit_code == EXIT_OK
    assert outcome.verdict.promotable is True
    assert outcome.verdict.requires_human_signoff is True  # never auto-deploy


def test_gate_blocks_on_safety_recall_regression_even_if_dominant():
    outcome = gate(
        _result("candidate.v2", to_target=3.0, recall=0.90, regret=60.0),
        _result("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0),
    )
    assert outcome.exit_code == EXIT_BLOCKED
    assert outcome.verdict.safety_regression is True


def test_gate_blocks_when_not_dominant():
    outcome = gate(
        _result("candidate.v2", to_target=5.0, recall=0.95),
        _result("incumbent.v1", to_target=4.0, recall=0.95),
    )
    assert outcome.exit_code == EXIT_BLOCKED
    assert outcome.verdict.dominates is False


def test_end_to_end_gate_with_intact_gold_set():
    outcome = run_benchmark_gate(
        _payload(),
        _result("candidate.v2", to_target=4.0, recall=0.97, regret=85.0),
        _result("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0),
    )
    assert outcome.exit_code == EXIT_OK


def test_drift_maps_to_exit_drift_in_end_to_end_gate():
    payload = _payload()
    payload["tasks"][0]["objective_target"] = 1.0  # tampered, checksum not re-frozen
    result = _result("m", to_target=4.0, recall=0.95)
    outcome = run_benchmark_gate(payload, result, result)
    assert outcome.exit_code == EXIT_DRIFT
    assert outcome.verdict is None


def test_results_not_bound_to_this_gold_set_are_refused():
    # Evaluated against a different (deliberately re-frozen, easier) gold set, then gated against
    # the pristine payload -> must refuse, not silently pass.
    easier = _refrozen(lambda p: p["tasks"][0].__setitem__("objective_target", 10.0))
    tasks = load_gold_set(easier)
    stray = evaluate_campaign(
        "candidate.v2", [_run_reaching_target()], tasks, gold_checksum=easier["checksum"]
    )
    incumbent = _result("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0)
    outcome = run_benchmark_gate(_payload(), stray, incumbent)
    assert outcome.exit_code == EXIT_DRIFT
    assert "not evaluated against this gold set" in outcome.reason


# --- R10 bridge: gold observation ids are excluded from warm-start snapshots ---------------------
def test_gold_observation_ids_are_excluded_from_warm_start_snapshots():
    task = _tasks()[0]
    assert task.observation_ids
    gold_id = task.observation_ids[0]
    snap = reaction_priors.build_snapshot(
        [
            reaction_priors.CampaignObservation(gold_id, {"catalyst": "Pd-XPhos"}, 91.0, verified=True),
            reaction_priors.CampaignObservation("ordinary:1", {"catalyst": "Pd-SPhos"}, 71.0, verified=True),
        ],
        gold_set_ids=task.observation_ids,
    )
    assert snap.excluded_gold_count == 1
    assert {row["observation_id"] for row in snap.observations} == {"ordinary:1"}
    reaction_priors.assert_no_gold_leakage(snap, task.observation_ids)


# --- the gate must be able to PRODUCE the evidence the Phase-C seam consumes ---------------------
def test_a_real_gate_pass_produces_evidence_the_capability_seam_accepts():
    """Closes the loop between R11 and Phase C.

    The gate outcome carries the exit code; the evaluated result carries the gold checksum and
    model version. Without a producer of that union the only thing that could ever unlock a heavy
    backend was a hand-typed dict, and the "R11 gate pass" in provenance was a self-attestation.
    """

    from nmrcheck import reaction_ml
    from nmrcheck.reaction_eval import promotion_evidence

    payload = _payload()
    candidate = _result("candidate.v2", to_target=4.0, recall=0.97, regret=85.0)
    incumbent = _result("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0)
    outcome = run_benchmark_gate(payload, candidate, incumbent)
    assert outcome.exit_code == EXIT_OK

    evidence = promotion_evidence(outcome, candidate)
    status = reaction_ml.capability_status(
        "yield_gnn",
        probe=lambda _module: True,
        env={"MOLTRACE_REACTION_YIELD_GNN": "1"},
        promotion_evidence=evidence,
        expected_gold_checksum=gold_set_checksum(payload),
        expected_model_version="candidate.v2",
    )
    assert status.active is True, status.reason


def test_a_blocked_gate_produces_evidence_that_is_refused():
    from nmrcheck import reaction_ml
    from nmrcheck.reaction_eval import promotion_evidence

    payload = _payload()
    candidate = _result("candidate.v2", to_target=3.0, recall=0.90, regret=60.0)
    incumbent = _result("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0)
    outcome = run_benchmark_gate(payload, candidate, incumbent)
    assert outcome.exit_code == EXIT_BLOCKED

    evidence = promotion_evidence(outcome, candidate)
    status = reaction_ml.capability_status(
        "yield_gnn",
        probe=lambda _module: True,
        env={"MOLTRACE_REACTION_YIELD_GNN": "1"},
        promotion_evidence=evidence,
    )
    assert status.active is False
    assert "exit_code" in status.reason


def test_cli_writes_the_evidence_artifact(tmp_path):
    import json as _json

    from nmrcheck.reaction_eval_cli import main

    payload = _payload()
    candidate = _result("candidate.v2", to_target=4.0, recall=0.97, regret=85.0)
    incumbent = _result("incumbent.v1", to_target=6.0, recall=0.95, regret=120.0)
    gold = tmp_path / "gold.json"
    gold.write_text(_json.dumps(payload))
    cand = tmp_path / "candidate.json"
    cand.write_text(_json.dumps(candidate.as_dict()))
    inc = tmp_path / "incumbent.json"
    inc.write_text(_json.dumps(incumbent.as_dict()))
    out = tmp_path / "evidence.json"

    code = main(
        [
            "--gold", str(gold),
            "--candidate", str(cand),
            "--incumbent", str(inc),
            "--evidence-out", str(out),
        ]
    )
    assert code == EXIT_OK
    evidence = _json.loads(out.read_text())
    assert evidence["exit_code"] == EXIT_OK
    assert evidence["gold_checksum"] == gold_set_checksum(payload)
    assert evidence["model_version"] == "candidate.v2"


# --- regulatory-compliant yield ----------------------------------------------------------------
#
# best_objective answers "what is the highest yield the model found". It does not answer the
# question a regulated campaign actually turns on: how much of that yield is USABLE. A model that
# drives to 91% under conditions a hard ICH limit forbids has found nothing a chemist can run, and
# scores identically to one that found 91% cleanly.
#
# `regulatory_compliant_yield` is the best objective reached among conditions the FROZEN gold set
# marks compliant. The ground truth is the gold set's, never the model's own claim about itself.


def _noncompliant_task(key: str):
    """The frozen gold tasks, with one surface point marked regulatory-noncompliant."""
    tasks = _tasks()
    return [
        replace(task, noncompliant_condition_keys=frozenset({key}))
        if task.task_id == "bh_sim_v1"
        else task
        for task in tasks
    ]


def test_compliant_yield_ignores_a_higher_yield_that_breaches_a_limit():
    """The 91% optimum is forbidden, so the reportable yield is the 84% compliant one."""
    forbidden = condition_key(_cond("Pd-XPhos", "KOtBu", 80))
    result = evaluate_campaign(
        "cand", [_run_reaching_target()], _noncompliant_task(forbidden),
        gold_checksum=_checksum(),
    )
    assert result.metrics["best_objective"] == 91.0
    assert result.metrics["regulatory_compliant_yield"] == 84.0, (
        "a yield only reachable by breaching a hard limit is not a yield the campaign can use"
    )


def test_compliant_yield_equals_best_objective_when_nothing_is_forbidden():
    result = evaluate_campaign(
        "cand", [_run_reaching_target()], _noncompliant_task(condition_key(_cond("x", "y", 999))),
        gold_checksum=_checksum(),
    )
    assert result.metrics["regulatory_compliant_yield"] == result.metrics["best_objective"]


def test_a_run_with_no_compliant_condition_is_not_rewarded_by_omission():
    """Every step forbidden: the run scores its own worst observation, never a silent pass.

    Omitting the run, or defaulting it to the best value, would let a model that proposed
    nothing runnable dominate the incumbent on this axis.
    """
    run = _run_reaching_target()
    tasks = [
        replace(
            task,
            noncompliant_condition_keys=frozenset(
                condition_key(step.conditions) for step in run.steps
            ),
        )
        if task.task_id == "bh_sim_v1"
        else task
        for task in _tasks()
    ]
    result = evaluate_campaign("cand", [run], tasks, gold_checksum=_checksum())
    assert result.metrics["regulatory_compliant_yield"] == 33.0  # the run's worst observation
    assert any("no regulatory-compliant" in w for w in result.warnings)


def test_metric_is_omitted_when_the_gold_set_declares_no_regulatory_truth():
    """Nothing was checked, so the axis is absent rather than vacuously perfect."""
    result = _evaluate("cand", [_run_reaching_target()])
    assert "regulatory_compliant_yield" not in result.metrics
    assert any("no regulatory ground truth" in w for w in result.warnings)


def test_noncompliant_key_must_be_canonical_and_present_in_the_surface():
    payload = _payload()
    payload["tasks"][0]["noncompliant_condition_keys"] = ['{"catalyst": "Pd-XPhos"}']
    payload["checksum"] = gold_set_checksum(payload)
    with pytest.raises(ReactionEvalError, match="noncompliant key"):
        load_gold_set(payload)


def test_compliant_yield_actually_gates_rather_than_being_reported_and_ignored():
    """Metrics of unknown direction are dropped from dominance, so this must be declared."""
    from nmrcheck.reaction_eval import METRIC_DIRECTIONS

    assert METRIC_DIRECTIONS["regulatory_compliant_yield"] == "higher"


def test_a_candidate_that_wins_only_on_forbidden_conditions_does_not_dominate():
    """The point of the axis: raw yield up, usable yield down => not a promotion."""
    forbidden = condition_key(_cond("Pd-XPhos", "KOtBu", 80))
    tasks = _noncompliant_task(forbidden)
    incumbent = evaluate_campaign(
        "inc", [_run_reaching_target()], tasks, gold_checksum=_checksum()
    )
    # Candidate reaches the same 91 optimum but its compliant best is worse (71 vs 84).
    candidate_run = CampaignRun(
        task_id="bh_sim_v1",
        steps=[
            _step("Pd-dppf", "K3PO4", 60, 33.0, latency_seconds=10.0),
            _step("Pd-SPhos", "KOtBu", 80, 71.0, latency_seconds=10.0),
            _step("Pd-XPhos", "KOtBu", 80, 91.0, latency_seconds=10.0),
        ],
    )
    candidate = evaluate_campaign("cand", [candidate_run], tasks, gold_checksum=_checksum())
    assert candidate.metrics["best_objective"] == incumbent.metrics["best_objective"]
    assert (
        candidate.metrics["regulatory_compliant_yield"]
        < incumbent.metrics["regulatory_compliant_yield"]
    )
