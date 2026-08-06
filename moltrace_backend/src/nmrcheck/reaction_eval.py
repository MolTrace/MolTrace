"""Repho R11 — evaluation harness, reproduction benchmark & blocking safety gate (frozen).

The promotion contract for reaction optimiser/predictor versions: **a candidate ships only if its
metric vector dominates the incumbent on a frozen benchmark AND safety-flag recall does not
regress.** This engine is the pure, deterministic half of that contract.

Integrity is the whole point of a benchmark, so this module is fail-closed by construction:

* **Frozen gold set.** :func:`load_gold_set` recomputes the content hash and **refuses to run on
  drift**; every malformed-payload path also raises :class:`ReactionEvalError` (so the CI mapping
  is ``EXIT_DRIFT``, never the ``EXIT_BLOCKED`` that an uncaught exception would produce). Gold
  numbers must be finite, task ids unique, and every hazardous-condition key must be **canonical
  and present in the frozen surface** — ground truth that cannot be matched is not ground truth.
* **Canonical condition keys.** :func:`condition_key` normalises numerics (an integral ``100.0``
  keys identically to ``100``), so a hazardous encounter cannot become invisible to safety-flag
  recall through ordinary float/int drift in a recorded trace.
* **Traces are checked against the frozen surface.** A step landing on a gold grid point must
  report the gold objective; a contradicting trace is refused rather than scored.
* **Comparable hypervolume.** The reference vector and outcome dimension order are **frozen per
  task in the checksummed fixture** — never derived from the model's own trace, which a candidate
  could inflate by sampling a deliberately bad point.
* **Results are bound to the gold set.** :class:`EvalResult` carries the gold checksum it was
  computed against; :func:`run_benchmark_gate` refuses (``EXIT_DRIFT``) when a result was not
  evaluated against the payload being gated.
* **Blocking gate.** :func:`gate` delegates to the adversarially-hardened R9 promotion gate
  (:func:`reaction_feedback.evaluate_ab_promotion`) — fail-closed on missing/non-finite recall,
  dominance refused when a metric is omitted — and maps the verdict to a CI exit code. A metric a
  trace cannot support is **omitted, never defaulted to its best value**, so the gate refuses
  dominance instead of rewarding missing evidence.

Pure: no DB / HTTP / clock / randomness.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import reaction_feedback, reaction_pareto

ENGINE = "reaction_eval.v1"

# CI exit codes (the wiring maps these to the process exit status — fail-closed).
EXIT_OK = 0  # promotable (still requires human sign-off — never auto-deploy)
EXIT_BLOCKED = 1  # not promotable: safety regression and/or no dominance
EXIT_DRIFT = 2  # gold set drifted / integrity failure: refuse to evaluate at all

# Frozen metric directions for dominance.
METRIC_DIRECTIONS: dict[str, str] = {
    "experiments_to_target_median": "lower",
    "best_objective": "higher",
    "hypervolume": "higher",
    "cumulative_regret": "lower",
    "reproduction_accuracy": "higher",
    "calibration_error": "lower",
    "iteration_latency_seconds": "lower",
    # Higher is better, and it MUST be declared here: reaction_feedback excludes metrics of
    # unknown direction from dominance, so an undeclared axis would be computed, reported, and
    # then quietly ignored by the promotion gate.
    "regulatory_compliant_yield": "higher",
}

# A trace landing on a frozen grid point must report the frozen objective within this tolerance.
SURFACE_TOLERANCE = 1e-6


class ReactionEvalError(Exception):
    """Raised on benchmark integrity failures (drift, malformed gold set, contradicting trace)."""


# --------------------------------------------------------------------------- #
# Canonicalisation.
# --------------------------------------------------------------------------- #
def _canonical_scalar(value: Any) -> Any:
    """Normalise a condition value so equal chemistry keys identically.

    Integral floats collapse to int (``100.0`` -> ``100``) — otherwise a hazardous condition
    recorded as a float would never match the frozen key and would silently vanish from the
    safety-recall denominator.
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise ReactionEvalError(f"Condition value must be finite, got {value!r}")
        return int(number) if number.is_integer() else number
    return value


def condition_key(conditions: Mapping[str, Any]) -> str:
    """Canonical key for a condition set (sorted keys, normalised numerics, compact JSON)."""

    return json.dumps(
        {str(k): _canonical_scalar(conditions[k]) for k in sorted(conditions, key=str)},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _require_finite(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ReactionEvalError(f"{label} must be finite, got {value!r}")
    return number


# --------------------------------------------------------------------------- #
# Gold set — frozen, checksummed, refuse-on-drift.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GoldTask:
    """One frozen benchmark task: the known response surface + target + safety truth."""

    task_id: str
    objective_target: float
    optimum_objective: float
    surface: Mapping[str, float]
    observation_ids: tuple[str, ...] = ()
    hazardous_condition_keys: frozenset[str] = frozenset()
    #: Surface points a hard regulatory limit forbids. Frozen ground truth — never the
    #: model's own claim about its compliance. Empty means the gold set asserts nothing
    #: about regulatory status, which is different from asserting everything is allowed.
    noncompliant_condition_keys: frozenset[str] = frozenset()
    # Frozen multi-objective config — never derived from a model's own trace.
    outcome_names: tuple[str, ...] = ()
    outcome_directions: tuple[str, ...] = ()
    hypervolume_reference: tuple[float, ...] | None = None


def gold_set_checksum(payload: Mapping[str, Any]) -> str:
    """Content hash of a gold-set payload (everything except the recorded checksum itself)."""

    body = {k: payload[k] for k in sorted(payload) if k != "checksum"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_gold_set(payload: Mapping[str, Any]) -> list[GoldTask]:
    """Parse + integrity-check a frozen gold-set payload. Refuses to run on any defect.

    Every failure path raises :class:`ReactionEvalError` so the CI mapping is ``EXIT_DRIFT`` — a
    malformed payload must never surface as an ordinary Python exception (which CI would read as
    ``EXIT_BLOCKED``, i.e. "candidate not promotable" rather than "benchmark is broken").
    """

    recorded = str(payload.get("checksum") or "")
    if not recorded:
        raise ReactionEvalError("Gold set carries no checksum; refusing to evaluate.")
    actual = gold_set_checksum(payload)
    if actual != recorded:
        raise ReactionEvalError(
            f"Gold set drift: recorded checksum {recorded} != computed {actual}; "
            "refusing to evaluate. Re-freeze deliberately if the change is intended."
        )
    tasks_raw = payload.get("tasks")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise ReactionEvalError("Gold set has no tasks.")

    tasks: list[GoldTask] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(tasks_raw):
        try:
            tasks.append(_parse_task(raw))
        except ReactionEvalError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ReactionEvalError(f"Malformed gold task at index {index}: {exc}") from exc
        if tasks[-1].task_id in seen_ids:
            raise ReactionEvalError(f"Duplicate gold task id {tasks[-1].task_id!r}.")
        seen_ids.add(tasks[-1].task_id)
    return tasks


def _condition_key_set(
    raw_keys: Any, surface: Mapping[str, float], task_id: str, label: str
) -> set[str]:
    """Validate one frozen ground-truth key set against the frozen surface."""

    keys: set[str] = set()
    for key in raw_keys or ():
        key = str(key)
        try:
            canonical = condition_key(json.loads(key))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ReactionEvalError(
                f"Gold task {task_id!r}: {label} key is not canonical JSON: {key!r}"
            ) from exc
        if canonical != key:
            raise ReactionEvalError(
                f"Gold task {task_id!r}: {label} key is not canonical ({key!r} != {canonical!r})."
            )
        if key not in surface:
            raise ReactionEvalError(
                f"Gold task {task_id!r}: {label} key is not present in the frozen "
                f"surface: {key!r}"
            )
        keys.add(key)
    return keys


def _parse_task(raw: Any) -> GoldTask:
    if not isinstance(raw, dict):
        raise ReactionEvalError("Gold task entry is not an object.")
    task_id = str(raw["task_id"])
    surface_raw = raw.get("surface")
    if not isinstance(surface_raw, dict) or not surface_raw:
        raise ReactionEvalError(f"Gold task {task_id!r} has no surface.")
    surface = {
        str(k): _require_finite(v, f"surface value for {task_id!r}") for k, v in surface_raw.items()
    }

    # Both ground-truth key sets must be canonical AND present in the surface. Without that,
    # safety recall silently reports a perfect 1.0 for a model that never had a matchable hazard,
    # and the compliant-yield axis silently forbids nothing.
    hazardous = _condition_key_set(
        raw.get("hazardous_condition_keys"), surface, task_id, "hazardous"
    )
    noncompliant = _condition_key_set(
        raw.get("noncompliant_condition_keys"), surface, task_id, "noncompliant"
    )

    outcome_names = tuple(str(x) for x in raw.get("outcome_names") or ())
    outcome_directions = tuple(str(x) for x in raw.get("outcome_directions") or ())
    reference_raw = raw.get("hypervolume_reference")
    reference = (
        tuple(_require_finite(v, f"hypervolume reference for {task_id!r}") for v in reference_raw)
        if reference_raw is not None
        else None
    )
    if outcome_names or outcome_directions or reference is not None:
        if not (len(outcome_names) == len(outcome_directions) == len(reference or ())):
            raise ReactionEvalError(
                f"Gold task {task_id!r}: outcome_names / outcome_directions / "
                "hypervolume_reference must be the same length."
            )
        if any(d not in {"max", "min"} for d in outcome_directions):
            raise ReactionEvalError(f"Gold task {task_id!r}: outcome direction must be max|min.")

    return GoldTask(
        task_id=task_id,
        objective_target=_require_finite(raw["objective_target"], "objective_target"),
        optimum_objective=_require_finite(raw["optimum_objective"], "optimum_objective"),
        surface=surface,
        observation_ids=tuple(str(x) for x in raw.get("observation_ids") or ()),
        hazardous_condition_keys=frozenset(hazardous),
        noncompliant_condition_keys=frozenset(noncompliant),
        outcome_names=outcome_names,
        outcome_directions=outcome_directions,
        hypervolume_reference=reference,
    )


# --------------------------------------------------------------------------- #
# Campaign traces — what the harness evaluates.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CampaignStep:
    """One evaluated experiment in a benchmark run."""

    conditions: Mapping[str, Any]
    objective: float
    predicted_objective: float | None = None
    predicted_confidence: float | None = None  # [0,1]; for calibration
    safety_flagged: bool = False  # did the model's safety screen flag this condition?
    latency_seconds: float | None = None
    outcomes: Mapping[str, float] | None = None  # optional multi-objective outcomes


@dataclass
class CampaignRun:
    """One benchmark run (a sequence of steps) against a gold task."""

    task_id: str
    steps: Sequence[CampaignStep]


@dataclass
class EvalResult:
    model_version: str
    metrics: dict[str, float]
    safety_flag_recall: float
    per_task: dict[str, dict[str, Any]]
    gold_checksum: str | None = None
    warnings: list[str] = field(default_factory=list)

    def as_model_metrics(self) -> reaction_feedback.ModelMetrics:
        return reaction_feedback.ModelMetrics(
            model_version=self.model_version,
            metrics=dict(self.metrics),
            safety_flag_recall=self.safety_flag_recall,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "metrics": self.metrics,
            "safety_flag_recall": self.safety_flag_recall,
            "per_task": self.per_task,
            "gold_checksum": self.gold_checksum,
            "warnings": list(self.warnings),
            "engine": ENGINE,
        }


# --------------------------------------------------------------------------- #
# Metrics.
# --------------------------------------------------------------------------- #
def evaluate_campaign(
    model_version: str,
    runs: Sequence[CampaignRun],
    gold_tasks: Sequence[GoldTask],
    *,
    gold_checksum: str | None = None,
    reproduction_tolerance: float = 2.0,
    calibration_bins: int = 5,
    surface_tolerance: float = SURFACE_TOLERANCE,
) -> EvalResult:
    """Compute the frozen metric vector for a model's benchmark runs.

    Every run must reference a known gold task, every numeric in the trace must be finite, and a
    step landing on a frozen grid point must report the frozen objective — a trace that
    contradicts the benchmark is refused, not scored. Metrics a trace cannot support are omitted
    (never defaulted to their best value) so the gate refuses dominance rather than rewarding
    missing evidence. Pass ``gold_checksum`` to bind the result to the gold set it was run against.
    """

    by_task = {task.task_id: task for task in gold_tasks}
    warnings: list[str] = []
    per_task: dict[str, dict[str, Any]] = {}

    to_target: list[float] = []
    best_objectives: list[float] = []
    regrets: list[float] = []
    reproduced: list[bool] = []
    hv_values: list[float] = []
    latencies: list[float] = []
    calib_pairs: list[tuple[float, bool]] = []
    compliant_yields: list[float] = []
    runs_with_no_compliant_step = 0
    any_regulatory_truth = False
    hazardous_seen = 0
    hazardous_flagged = 0

    for run in runs:
        task = by_task.get(run.task_id)
        if task is None:
            raise ReactionEvalError(f"Run references unknown gold task {run.task_id!r}.")
        steps = list(run.steps)
        if not steps:
            warnings.append(f"Run on task {task.task_id!r} has no steps; skipped.")
            continue

        objectives = [
            _require_finite(step.objective, f"step objective on {task.task_id!r}") for step in steps
        ]

        # A step on a frozen grid point must agree with the frozen surface.
        for step, objective in zip(steps, objectives, strict=True):
            key = condition_key(step.conditions)
            gold_value = task.surface.get(key)
            if gold_value is not None and abs(objective - gold_value) > surface_tolerance:
                raise ReactionEvalError(
                    f"Trace contradicts the frozen gold surface on task {task.task_id!r}: "
                    f"condition {key} reported {objective!r}, gold says {gold_value!r}."
                )

        best = max(objectives)
        best_objectives.append(best)

        # best_objective answers "what is the highest yield the model found"; this answers the
        # question a regulated campaign turns on — how much of it is USABLE. A trace that reaches
        # its optimum only under conditions a hard limit forbids has found nothing runnable, and
        # without this axis it scores identically to one that reached the same yield cleanly.
        if task.noncompliant_condition_keys:
            any_regulatory_truth = True
            compliant = [
                objective
                for step, objective in zip(steps, objectives, strict=True)
                if condition_key(step.conditions) not in task.noncompliant_condition_keys
            ]
            if compliant:
                compliant_yields.append(max(compliant))
            else:
                # Never omit and never default to the best value: on a higher-is-better axis
                # either would let a model that proposed nothing runnable win this dimension.
                # The run's own worst observation is a real number it actually produced.
                compliant_yields.append(min(objectives))
                runs_with_no_compliant_step += 1
        reached = next(
            (i for i, value in enumerate(objectives, start=1) if value >= task.objective_target),
            None,
        )
        to_target.append(float(reached) if reached is not None else float(len(steps) + 1))
        regrets.append(sum(max(0.0, task.optimum_objective - value) for value in objectives))
        reproduced.append(best >= task.optimum_objective - reproduction_tolerance)

        hv = _run_hypervolume(task, steps, warnings)
        if hv is not None:
            hv_values.append(hv)

        for step in steps:
            if step.latency_seconds is not None:
                latencies.append(_require_finite(step.latency_seconds, "latency_seconds"))
            if step.predicted_objective is not None and step.predicted_confidence is not None:
                predicted = _require_finite(step.predicted_objective, "predicted_objective")
                confidence = _require_finite(step.predicted_confidence, "predicted_confidence")
                accurate = abs(predicted - step.objective) <= reproduction_tolerance
                calib_pairs.append((max(0.0, min(1.0, confidence)), accurate))
            if condition_key(step.conditions) in task.hazardous_condition_keys:
                hazardous_seen += 1
                if step.safety_flagged:
                    hazardous_flagged += 1

        entry = per_task.setdefault(task.task_id, {"runs": 0, "best_objectives": []})
        entry["runs"] += 1
        entry["best_objectives"].append(best)

    if not to_target:
        raise ReactionEvalError("No evaluable runs.")

    recall = 1.0 if hazardous_seen == 0 else hazardous_flagged / hazardous_seen
    if hazardous_seen == 0:
        warnings.append(
            "No hazardous gold condition was encountered; safety-flag recall is vacuously 1.0."
        )
    metrics: dict[str, float] = {
        "experiments_to_target_median": _median(to_target),
        "best_objective": _median(best_objectives),
        "cumulative_regret": _median(regrets),
        "reproduction_accuracy": sum(reproduced) / len(reproduced),
    }
    if calib_pairs:
        metrics["calibration_error"] = _expected_calibration_error(
            calib_pairs, bins=calibration_bins
        )
    else:
        warnings.append("No calibration pairs; calibration_error omitted.")
    if latencies:
        # Omitted (not defaulted to 0.0) when absent: 0.0 is the BEST value on a lower-is-better
        # dimension, so defaulting would hand a silent win to a trace carrying no timings.
        metrics["iteration_latency_seconds"] = _median(latencies)
    else:
        warnings.append("No step latencies; iteration_latency_seconds omitted.")
    if hv_values:
        metrics["hypervolume"] = _median(hv_values)
    if any_regulatory_truth:
        metrics["regulatory_compliant_yield"] = _median(compliant_yields)
        if runs_with_no_compliant_step:
            warnings.append(
                f"{runs_with_no_compliant_step} run(s) reached no regulatory-compliant condition; "
                "each scored its own worst observation on regulatory_compliant_yield."
            )
    else:
        # Absent, not vacuously equal to best_objective: no gold task declared which conditions a
        # limit forbids, so nothing was checked and the axis has no evidence behind it.
        warnings.append(
            "Gold set declares no regulatory ground truth; regulatory_compliant_yield omitted."
        )

    return EvalResult(
        model_version=model_version,
        metrics=metrics,
        safety_flag_recall=recall,
        per_task=per_task,
        gold_checksum=gold_checksum,
        warnings=warnings,
    )


def _run_hypervolume(
    task: GoldTask, steps: Sequence[CampaignStep], warnings: list[str]
) -> float | None:
    """Hypervolume for one run using the task's FROZEN dimension order + reference vector.

    Returns ``None`` (with a warning) when the task has no frozen multi-objective config or the
    trace cannot supply it — never a silently derived reference, which a candidate could inflate
    by sampling a deliberately bad point.
    """

    outcome_steps = [step for step in steps if step.outcomes]
    if not outcome_steps:
        return None
    if not task.outcome_names or task.hypervolume_reference is None:
        warnings.append(
            f"Task {task.task_id!r} has outcomes but no frozen hypervolume config; skipped."
        )
        return None
    points: list[tuple[float, ...]] = []
    for step in outcome_steps:
        outcomes = step.outcomes or {}
        missing = [name for name in task.outcome_names if name not in outcomes]
        if missing:
            warnings.append(
                f"Task {task.task_id!r}: step missing outcome(s) {missing}; hypervolume skipped."
            )
            return None
        # Aligned by FROZEN name order, never dict insertion order.
        points.append(
            tuple(
                _require_finite(outcomes[name], f"outcome {name!r}") for name in task.outcome_names
            )
        )
    hv, _method = reaction_pareto.hypervolume(
        points, list(task.outcome_directions), reference=list(task.hypervolume_reference)
    )
    return hv


# --------------------------------------------------------------------------- #
# The blocking gate → CI exit code.
# --------------------------------------------------------------------------- #
@dataclass
class GateOutcome:
    exit_code: int
    verdict: reaction_feedback.PromotionVerdict | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "verdict": self.verdict.as_dict() if self.verdict is not None else None,
            "reason": self.reason,
            "engine": ENGINE,
        }


def gate(
    candidate: EvalResult,
    incumbent: EvalResult,
    *,
    tolerance: float = 0.0,
) -> GateOutcome:
    """Promotable iff no safety-recall regression AND metric-vector dominance.

    Delegates to the adversarially-hardened R9 gate with the frozen R11 metric directions and maps
    the verdict to a CI exit code. ``EXIT_OK`` still requires human sign-off.
    """

    verdict = reaction_feedback.evaluate_ab_promotion(
        incumbent.as_model_metrics(),
        candidate.as_model_metrics(),
        directions=METRIC_DIRECTIONS,
        tolerance=tolerance,
    )
    if verdict.promotable:
        return GateOutcome(
            exit_code=EXIT_OK,
            verdict=verdict,
            reason="Candidate dominates with no safety-recall regression; human sign-off required.",
        )
    return GateOutcome(
        exit_code=EXIT_BLOCKED,
        verdict=verdict,
        reason="; ".join(verdict.reasons) or "Candidate is not promotable.",
    )


def run_benchmark_gate(
    gold_payload: Mapping[str, Any],
    candidate: EvalResult,
    incumbent: EvalResult,
    *,
    tolerance: float = 0.0,
) -> GateOutcome:
    """End-to-end: integrity-check the gold set, verify both results were evaluated against it,
    then gate. Any integrity failure -> ``EXIT_DRIFT`` (refuse to run), never a silent pass."""

    try:
        load_gold_set(gold_payload)
    except ReactionEvalError as exc:
        return GateOutcome(exit_code=EXIT_DRIFT, verdict=None, reason=str(exc))

    expected = gold_set_checksum(gold_payload)
    for label, result in (("candidate", candidate), ("incumbent", incumbent)):
        if result.gold_checksum != expected:
            return GateOutcome(
                exit_code=EXIT_DRIFT,
                verdict=None,
                reason=(
                    f"The {label} was not evaluated against this gold set "
                    f"(stamped {result.gold_checksum!r}, expected {expected!r}); refusing to gate."
                ),
            )
    return gate(candidate, incumbent, tolerance=tolerance)


def promotion_evidence(outcome: GateOutcome, candidate: EvalResult) -> dict[str, Any]:
    """Emit the machine-readable gate record that :mod:`nmrcheck.reaction_ml` consumes.

    The gate outcome carries the *exit code*; the evaluated result carries the *gold checksum* and
    the *model version*. Neither alone is the record the Phase-C capability seam requires, so this
    is the one producer of that union — without it the only thing that could ever unlock a heavy
    backend was a dict an operator typed by hand, and the "R11 gate pass" recorded in provenance
    would have been a self-attestation.

    It reports the outcome faithfully rather than only on success: a blocked or drifted run yields
    evidence carrying that non-zero exit code, which ``reaction_ml`` then correctly refuses. This
    ties the record to a gate run that actually happened; it is not a signature, and it does not
    defend against an operator who edits the artifact afterwards. Treat it as the audit trail of
    the promotion decision, and protect it the way the rest of the release evidence is protected.
    """

    return {
        "exit_code": int(outcome.exit_code),
        "gold_checksum": candidate.gold_checksum,
        "model_version": candidate.model_version,
        "safety_flag_recall": candidate.safety_flag_recall,
        "reason": outcome.reason,
        "verdict": outcome.verdict.as_dict() if outcome.verdict is not None else None,
        "engine": ENGINE,
    }


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _median(values: Sequence[float]) -> float:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _expected_calibration_error(pairs: Sequence[tuple[float, bool]], *, bins: int) -> float:
    """ECE over (confidence, accurate) pairs: |mean confidence - accuracy| weighted by bin size."""

    if not pairs:
        return 0.0
    bins = max(1, int(bins))
    grouped: dict[int, list[tuple[float, bool]]] = {}
    for confidence, accurate in pairs:
        index = min(bins - 1, int(confidence * bins))
        grouped.setdefault(index, []).append((confidence, accurate))
    total = len(pairs)
    ece = 0.0
    for bucket in grouped.values():
        mean_conf = sum(c for c, _ in bucket) / len(bucket)
        accuracy = sum(1 for _, a in bucket if a) / len(bucket)
        ece += (len(bucket) / total) * abs(mean_conf - accuracy)
    if not math.isfinite(ece):
        return 1.0  # fail-closed: a broken calibration input reads as maximally miscalibrated
    return ece
