"""Design-make-test-analyze (DMTA) loop engine for the Repho reaction optimizer (R5, engine slice).

Hardens the read-only SpectraCheck linkage into a *metered, human-gated* optimization loop. This
module is the **frozen** core: the canonical DMTA step model, the gate decision for proposing the
next batch, and the loop metering (latency + experiments-to-target + convergence). It is pure and
deterministic — no ORM, no HTTP, no clock, no LLM — so it is testable in isolation; a thin wiring
layer (a later slice) calls the existing R2 (BO/Pareto), R6 (safety gate), and
execution/SpectraCheck store functions in sequence and persists the metrics into the cycle's
``metadata_json`` (no schema change).

The loop is **half-closed by design**: a ``continue_optimization`` cycle decision may *propose* the
next batch (decision-support), but execution ALWAYS requires human signoff and must pass the R6
safety gate (`reaction_safety.assert_execution_allowed`). Nothing here auto-executes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Canonical DMTA loop, in order. The wiring advances through these by calling the existing step
# entry points (run_bayesian_optimization -> gate_status/assert_execution_allowed -> execution
# batch -> SpectraCheck-verified outcome -> refit + Pareto).
DMTA_SEQUENCE: tuple[str, ...] = ("propose", "safety_gate", "make", "test", "learn", "decision")

# Only this cycle decision permits proposing the next batch; everything else halts the loop.
_CONTINUE_DECISION = "continue_optimization"
_TERMINAL_DECISIONS = frozenset({"stop_success", "stop_insufficient_progress"})


@dataclass(frozen=True)
class ProposeNextVerdict:
    """Whether the loop may PROPOSE the next batch — and the always-on execution guardrails."""

    allowed: bool
    reason: str
    latest_decision: str | None
    safety_gate_status: str  # clear | review_pending | blocked | unknown
    # Invariants surfaced to the caller/UI — true regardless of `allowed`:
    requires_human_signoff_before_execution: bool = True
    execution_blocked_by_safety: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "latest_decision": self.latest_decision,
            "safety_gate_status": self.safety_gate_status,
            "requires_human_signoff_before_execution": (
                self.requires_human_signoff_before_execution
            ),
            "execution_blocked_by_safety": self.execution_blocked_by_safety,
        }


def evaluate_propose_next(
    latest_decision: str | None, safety_gate_status: str = "unknown"
) -> ProposeNextVerdict:
    """Decide whether a human-gated ``propose-next`` may run.

    Proposing the next batch is permitted ONLY when the cycle's latest recorded decision is
    ``continue_optimization``; a missing decision, a ``pause``/``stop_*``/``revise_*`` decision, or
    one requiring review refuses (the human has not green-lit continuing). Proposing is
    decision-support only: ``requires_human_signoff_before_execution`` is always True, and a
    ``blocked`` safety gate is surfaced (``execution_blocked_by_safety``) but does not stop a
    *proposal* — it stops *execution*, which the R6 gate enforces at the make boundary.
    """
    blocked_by_safety = safety_gate_status == "blocked"
    if latest_decision is None:
        return ProposeNextVerdict(
            allowed=False,
            reason="No cycle decision recorded yet; record a 'continue_optimization' decision "
            "before proposing the next batch.",
            latest_decision=None,
            safety_gate_status=safety_gate_status,
            execution_blocked_by_safety=blocked_by_safety,
        )
    if latest_decision != _CONTINUE_DECISION:
        terminal = latest_decision in _TERMINAL_DECISIONS
        reason = (
            f"The optimization was {'stopped' if terminal else 'held'} "
            f"(decision '{latest_decision}'); only 'continue_optimization' may propose the next "
            "batch."
        )
        return ProposeNextVerdict(
            allowed=False,
            reason=reason,
            latest_decision=latest_decision,
            safety_gate_status=safety_gate_status,
            execution_blocked_by_safety=blocked_by_safety,
        )
    return ProposeNextVerdict(
        allowed=True,
        reason="Proposing the next batch (decision-support); execution still requires human "
        "signoff and a clear safety gate.",
        latest_decision=latest_decision,
        safety_gate_status=safety_gate_status,
        execution_blocked_by_safety=blocked_by_safety,
    )


@dataclass(frozen=True)
class LoopMetrics:
    """Metering for one optimization cycle / campaign — the 'how fast, how far' of the loop."""

    latency_seconds: float | None  # cycle wall-clock (created -> completed)
    phase_latencies_seconds: dict[str, float] = field(default_factory=dict)
    experiments_to_target: int | None = None  # 1-based # of experiments to first hit the target
    best_objective: float | None = None  # scalarized score, higher is better
    objective_target: float | None = None
    objective_gap: float | None = None  # target - best (positive => still short of target)
    target_met: bool = False
    total_experiments: int = 0
    new_experiments: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "latency_seconds": self.latency_seconds,
            "phase_latencies_seconds": dict(self.phase_latencies_seconds),
            "experiments_to_target": self.experiments_to_target,
            "best_objective": self.best_objective,
            "objective_target": self.objective_target,
            "objective_gap": self.objective_gap,
            "target_met": self.target_met,
            "total_experiments": self.total_experiments,
            "new_experiments": self.new_experiments,
        }


def _to_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _seconds_between(start: Any, end: Any) -> float | None:
    a, b = _to_datetime(start), _to_datetime(end)
    if a is None or b is None:
        return None
    return max(0.0, (b - a).total_seconds())


def _phase_latencies(step_timestamps: Mapping[str, Any]) -> dict[str, float]:
    """Seconds between consecutive DMTA steps that have a timestamp, in canonical order."""
    present = [(s, _to_datetime(step_timestamps.get(s))) for s in DMTA_SEQUENCE]
    present = [(s, dt) for s, dt in present if dt is not None]
    out: dict[str, float] = {}
    for (a_name, a_dt), (b_name, b_dt) in zip(present, present[1:], strict=False):
        out[f"{a_name}_to_{b_name}"] = max(0.0, (b_dt - a_dt).total_seconds())
    return out


def compute_loop_metrics(
    *,
    experiment_scores: Sequence[float] | None = None,
    objective_target: float | None = None,
    step_timestamps: Mapping[str, Any] | None = None,
    created_at: Any = None,
    completed_at: Any = None,
    new_experiment_count: int = 0,
) -> LoopMetrics:
    """Compute loop metering. ``experiment_scores`` are the cycle's experiments' scalarized
    objective scores (higher is better) in chronological order; ``objective_target`` is the
    score the campaign aims to reach. All times are passed in (the engine never reads a clock).
    """
    scores = [float(s) for s in (experiment_scores or [])]
    best = max(scores) if scores else None

    experiments_to_target: int | None = None
    if objective_target is not None:
        for index, score in enumerate(scores, start=1):
            if score >= objective_target:
                experiments_to_target = index
                break

    target_met = best is not None and objective_target is not None and best >= objective_target
    gap = (
        (objective_target - best)
        if (best is not None and objective_target is not None)
        else None
    )
    return LoopMetrics(
        latency_seconds=_seconds_between(created_at, completed_at),
        phase_latencies_seconds=_phase_latencies(step_timestamps or {}),
        experiments_to_target=experiments_to_target,
        best_objective=best,
        objective_target=objective_target,
        objective_gap=gap,
        target_met=target_met,
        total_experiments=len(scores),
        new_experiments=new_experiment_count,
    )


def build_cycle_metrics_payload(
    metrics: LoopMetrics,
    *,
    bo_run_id: int | None = None,
    surrogate_model_version: str | None = None,
    spectracheck_session_ids: Sequence[int] | None = None,
    spectracheck_model_version_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Standardized ``cycle_metrics`` block for a cycle's ``metadata_json`` (wiring persists it).

    Bundles the metering with the per-step reproducibility provenance the spec requires (which BO
    run, surrogate model version, and SpectraCheck session/model versions produced the cycle), so a
    cycle is reproducible end to end without a schema migration.
    """
    return {
        "metrics": metrics.as_dict(),
        "provenance": {
            "bo_run_id": bo_run_id,
            "surrogate_model_version": surrogate_model_version,
            "spectracheck_session_ids": list(spectracheck_session_ids or []),
            "spectracheck_model_version_ids": list(spectracheck_model_version_ids or []),
        },
        "dmta_sequence": list(DMTA_SEQUENCE),
        "engine": "reaction_loop.v1",
    }
