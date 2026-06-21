"""Regulatory-constraint enforcement engine for the Repho reaction optimizer (R4, engine slice).

Closes the Regentry→Repho loop on the *enforcement* side: given a reaction project's injected
regulatory constraints (an ICH Q3A/B impurity limit, a residual-solvent limit, a nitrosamine
avoidance requirement, …) and a candidate experiment's predicted/expected outcome, decide which
candidates **violate a hard regulatory limit** — so the Bayesian-optimization ranking can filter
or penalise them, each with full provenance back to the regulatory source action item.

Design (matches the rest of Repho): pure, deterministic, frozen arithmetic — no ORM, no HTTP, no
LLM. The store/BO layers (follow-up slices) translate ``RegulatoryConstraintSetORM`` rows into the
plain mappings this module consumes and apply the verdict to candidate ranking. This module owns
only the math + the constraint contract.

Constraint contract (the numeric ``constraint_json`` shape the bridge-enrichment slice must
populate, read here defensively):

    {
      "limit_value": 0.10,                # the numeric bound (required to be enforceable)
      "limit_unit": "percent",            # "percent" | "ppm" | "ng_per_day" | …
      "comparator": "max",                # "max" (outcome must be <= limit) | "min" (>= limit)
      "objective_field": "impurity_percent",   # which outcome field the limit constrains
      "limit_basis": "ICH Q3B(R2) identification threshold",   # provenance text
    }

A constraint with no ``limit_value`` is **not enforceable quantitatively** — it is treated as
advisory (skipped here; the bridge/UI still surface it). This means the engine is a safe no-op
until the enrichment slice populates numeric limits, so wiring it into BO never regresses behaviour.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Severities (from the regulatory action item) that make a violation a HARD block — the candidate
# is infeasible and filtered out of the ranking. Lower tiers only apply a soft ranking penalty.
_HARD_SEVERITIES = frozenset({"high", "critical"})

# Default (outcome field, comparator) per constraint_type, used when constraint_json does not
# name an objective_field explicitly. Only fields that map to a real reaction-outcome measurement
# can be enforced; others remain advisory unless constraint_json names an explicit field.
_DEFAULT_FIELD_BY_TYPE: dict[str, tuple[str, str]] = {
    "impurity_limit": ("impurity_percent", "max"),
    "residual_solvent_limit": ("residual_solvent_ppm", "max"),
    "nitrosamine_risk_avoidance": ("nitrosamine_ng_per_day", "max"),
    "qnmr_validation_requirement": ("nmr_purity_percent", "min"),
}

# Tolerance so floating-point equality at exactly the limit is not reported as a violation.
_EPS = 1e-9


@dataclass(frozen=True)
class RegulatoryLimit:
    """One enforceable numeric regulatory limit, normalized from a stored constraint."""

    objective_field: str
    comparator: str  # "max" | "min"
    limit_value: float
    limit_unit: str
    basis: str
    severity: str
    constraint_id: int | None = None
    constraint_type: str = "other"
    source_action_item_ids: tuple[int, ...] = ()

    @property
    def is_hard(self) -> bool:
        return self.severity in _HARD_SEVERITIES


@dataclass(frozen=True)
class ConstraintViolation:
    constraint_id: int | None
    constraint_type: str
    objective_field: str
    comparator: str
    predicted_value: float
    limit_value: float
    limit_unit: str
    basis: str
    severity: str
    is_hard: bool
    source_action_item_ids: tuple[int, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "constraint_type": self.constraint_type,
            "objective_field": self.objective_field,
            "comparator": self.comparator,
            "predicted_value": self.predicted_value,
            "limit_value": self.limit_value,
            "limit_unit": self.limit_unit,
            "basis": self.basis,
            "severity": self.severity,
            "is_hard": self.is_hard,
            "source_action_item_ids": list(self.source_action_item_ids),
        }


@dataclass(frozen=True)
class FeasibilityVerdict:
    """Outcome of evaluating one candidate against the active regulatory limits."""

    feasible: bool  # no HARD violation
    hard_block: bool  # at least one high/critical violation -> filter from ranking
    penalty: float  # aggregate soft penalty in [0, 1] for ranking down-weighting
    violations: tuple[ConstraintViolation, ...] = ()
    unmeasured: tuple[str, ...] = ()  # objective_fields with a limit but no predicted value
    applied_constraint_ids: tuple[int, ...] = ()

    def summary(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "hard_block": self.hard_block,
            "penalty": round(self.penalty, 6),
            "violations": [v.as_dict() for v in self.violations],
            "unmeasured": list(self.unmeasured),
            "applied_constraint_ids": list(self.applied_constraint_ids),
            "violation_reasons": [
                f"{v.objective_field} {_reason_phrase(v)} {v.limit_value} {v.limit_unit}"
                f" ({v.basis})"
                for v in self.violations
            ],
        }


def _reason_phrase(v: ConstraintViolation) -> str:
    return "exceeds" if v.comparator == "max" else "is below"


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):  # bool is an int subclass — never a measurement
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def parse_limit(constraint: Mapping[str, Any]) -> RegulatoryLimit | None:
    """Normalize one stored constraint into a ``RegulatoryLimit``.

    ``constraint`` is a plain mapping shaped like a ``RegulatoryConstraintSet`` row:
    ``{constraint_type, severity, status, constraint_json, source_action_item_ids?, id?}``.
    Returns ``None`` when the constraint carries no numeric ``limit_value`` (not enforceable —
    advisory only) or is not active.
    """
    status = str(constraint.get("status", "active")).lower()
    if status not in ("active", "reviewed"):
        return None  # draft/archived constraints are not enforced

    body = constraint.get("constraint_json") or {}
    if not isinstance(body, Mapping):
        return None

    limit_value = _coerce_float(body.get("limit_value"))
    if limit_value is None:
        return None  # no numeric bound -> cannot enforce quantitatively

    constraint_type = str(constraint.get("constraint_type", "other"))
    default_field, default_cmp = _DEFAULT_FIELD_BY_TYPE.get(
        constraint_type, ("", "max")
    )
    objective_field = str(body.get("objective_field") or default_field).strip()
    if not objective_field:
        return None  # nothing to compare against

    comparator = str(body.get("comparator") or default_cmp).lower()
    if comparator not in ("max", "min"):
        comparator = "max"

    ids = constraint.get("source_action_item_ids") or body.get("source_action_item_ids") or []
    source_ids = tuple(int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit())

    cid = constraint.get("id")
    return RegulatoryLimit(
        objective_field=objective_field,
        comparator=comparator,
        limit_value=limit_value,
        limit_unit=str(body.get("limit_unit") or ""),
        basis=str(body.get("limit_basis") or body.get("source_action_type") or constraint_type),
        severity=str(constraint.get("severity", "medium")).lower(),
        constraint_id=int(cid) if isinstance(cid, int) else None,
        constraint_type=constraint_type,
        source_action_item_ids=source_ids,
    )


def parse_limits(constraints: Iterable[Mapping[str, Any]]) -> list[RegulatoryLimit]:
    """Normalize a collection of stored constraints, dropping non-enforceable ones."""
    out: list[RegulatoryLimit] = []
    for c in constraints:
        limit = parse_limit(c)
        if limit is not None:
            out.append(limit)
    return out


_IMPURITY_LIMIT_BASIS = {
    "impurity_identification": "ICH Q3A/B identification threshold",
    "impurity_reporting": "ICH Q3A/B reporting threshold",
    "impurity_qualification": "ICH Q3A/B qualification threshold",
}


def build_impurity_limit_fields(
    action_type: str, action_metadata: Mapping[str, Any]
) -> dict[str, Any]:
    """Derive the numeric ``constraint_json`` fields for an ``impurity_limit`` constraint from the
    regulatory impurity action item that produced it (the bridge-enrichment slice — the *write*
    side of the contract that :func:`parse_limit` reads).

    The action carries the ICH threshold it tripped (``threshold_percent``); that threshold is the
    limit future experiments must stay under. Returns ``{}`` when no numeric threshold is present,
    leaving the constraint advisory until a limit is set manually — so enrichment never invents a
    number the regulatory engine did not produce.
    """
    threshold = _coerce_float(action_metadata.get("threshold_percent"))
    if threshold is None:
        return {}
    fields: dict[str, Any] = {
        "limit_value": threshold,
        "limit_unit": "percent",
        "objective_field": "impurity_percent",
        "comparator": "max",
        "limit_basis": _IMPURITY_LIMIT_BASIS.get(action_type, "ICH Q3A/B impurity threshold"),
    }
    observed = _coerce_float(action_metadata.get("observed_level_percent"))
    if observed is not None:
        fields["observed_level_percent"] = observed
    return fields


def _violation_fraction(predicted: float, limit: RegulatoryLimit) -> float:
    """Fractional overshoot in [0, 1] for the soft penalty (0 == at/within the limit)."""
    denom = abs(limit.limit_value) if abs(limit.limit_value) > _EPS else 1.0
    if limit.comparator == "max":
        over = predicted - limit.limit_value
    else:  # "min"
        over = limit.limit_value - predicted
    if over <= _EPS:
        return 0.0
    return min(1.0, over / denom)


def evaluate_candidate(
    predicted_outcome: Mapping[str, Any], limits: Sequence[RegulatoryLimit]
) -> FeasibilityVerdict:
    """Evaluate one candidate's predicted/expected outcome against the active regulatory limits.

    ``predicted_outcome`` maps reaction-outcome fields (e.g. ``impurity_percent``) to numbers. A
    limit whose ``objective_field`` is absent from the outcome cannot be checked and is reported in
    ``unmeasured`` (advisory — never silently treated as passing). A violation of a high/critical
    limit sets ``hard_block`` (filter the candidate); lower-tier violations only add to ``penalty``.
    """
    violations: list[ConstraintViolation] = []
    unmeasured: list[str] = []
    penalties: list[float] = []
    applied: list[int] = []

    for limit in limits:
        if limit.constraint_id is not None:
            applied.append(limit.constraint_id)
        predicted = _coerce_float(predicted_outcome.get(limit.objective_field))
        if predicted is None:
            unmeasured.append(limit.objective_field)
            continue
        frac = _violation_fraction(predicted, limit)
        if frac <= 0.0:
            continue
        # Weight the soft penalty by tier so a medium violation pushes a candidate down more
        # than a low one, while hard violations are filtered outright (penalty still recorded).
        weight = 1.0 if limit.is_hard else (0.6 if limit.severity == "medium" else 0.3)
        penalties.append(min(1.0, frac * weight))
        violations.append(
            ConstraintViolation(
                constraint_id=limit.constraint_id,
                constraint_type=limit.constraint_type,
                objective_field=limit.objective_field,
                comparator=limit.comparator,
                predicted_value=predicted,
                limit_value=limit.limit_value,
                limit_unit=limit.limit_unit,
                basis=limit.basis,
                severity=limit.severity,
                is_hard=limit.is_hard,
                source_action_item_ids=limit.source_action_item_ids,
            )
        )

    hard_block = any(v.is_hard for v in violations)
    penalty = min(1.0, sum(penalties))
    return FeasibilityVerdict(
        feasible=not hard_block,
        hard_block=hard_block,
        penalty=penalty,
        violations=tuple(violations),
        unmeasured=tuple(dict.fromkeys(unmeasured)),  # de-dup, preserve order
        applied_constraint_ids=tuple(applied),
    )


@dataclass(frozen=True)
class EnforcementResult:
    """Aggregate outcome of applying constraints across a batch of candidates."""

    verdicts: tuple[FeasibilityVerdict, ...]
    limits: tuple[RegulatoryLimit, ...] = field(default_factory=tuple)

    @property
    def blocked_count(self) -> int:
        return sum(1 for v in self.verdicts if v.hard_block)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "enforced_constraint_count": len(self.limits),
            "active_constraint_ids": sorted(
                {lim.constraint_id for lim in self.limits if lim.constraint_id is not None}
            ),
            "candidates_evaluated": len(self.verdicts),
            "candidates_hard_blocked": self.blocked_count,
            "constraint_bases": sorted({lim.basis for lim in self.limits}),
        }


def enforce(
    candidates_outcomes: Sequence[Mapping[str, Any]],
    constraints: Iterable[Mapping[str, Any]],
) -> EnforcementResult:
    """Convenience: parse constraints once, evaluate every candidate, return verdicts + diagnostics.

    The BO ranking layer (follow-up wiring slice) uses ``verdicts[i].hard_block`` to filter a
    candidate and ``verdicts[i].penalty`` to down-weight its acquisition score, recording
    ``diagnostics()`` on the optimization run for an auditable provenance trail.
    """
    limits = tuple(parse_limits(constraints))
    verdicts = tuple(evaluate_candidate(o or {}, limits) for o in candidates_outcomes)
    return EnforcementResult(verdicts=verdicts, limits=limits)
