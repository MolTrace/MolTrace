"""Repho R9 — chemist feedback → preference re-ranker → safety-gated A/B promotion.

Pure, frozen, deterministic engine (no DB / HTTP / clock / randomness). Three concerns:

1. **Feedback capture taxonomy.** Every proposal (route, condition set, next batch) can be
   accepted / edited / rejected with a structured reason. A **safety rejection is high-signal**:
   it routes to *strengthen the R6 safety gate* and is **never** fed to the preference learner
   (we don't want a re-ranker that learns to dodge a hazard for a non-safety reason — the hazard
   is handled by the deterministic screen, not by preference).

2. **Preference re-ranker (advisory only).** A transparent, deterministic acceptance-likelihood
   model fit from accumulated *preference-learnable* feedback (Beta-smoothed accept rates per
   discretised candidate feature). It re-orders proposals by likely chemist acceptance; it never
   overrides the optimiser's ranking, only annotates it.

3. **A/B champion-vs-challenger gate.** A challenger model may replace the champion **only** with
   (a) **no safety-flag-recall regression** and (b) **dominance** on the metric vector. Promotion
   is never automatic — every verdict requires human sign-off and is instantly rollback-able.

The wiring (a follow-up) persists feedback rows with model versions, fits the model from history,
and gates deployment behind the verdict + a human sign-off + a fail-closed CI check.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

ENGINE = "reaction_feedback.v1"

FEEDBACK_DECISIONS: tuple[str, ...] = ("accept", "edit", "reject")
REJECTION_REASONS: tuple[str, ...] = (
    "unsafe",
    "infeasible_on_our_kit",
    "reagent_unavailable",
    "cost",
    "lower_confidence_than_stated",
    "wrong_precedent",
    "other",
)
SAFETY_REJECTION_REASON = "unsafe"

# Acceptance label weight per decision (kept-with-edits counts as a soft positive).
_DECISION_WEIGHT: dict[str, float] = {"accept": 1.0, "edit": 0.5, "reject": 0.0}

# Default better-direction for common reaction A/B metrics. Callers may extend via `directions`.
_BETTER_HIGHER: frozenset[str] = frozenset(
    {
        "yield_percent",
        "selectivity_percent",
        "conversion_percent",
        "green_score",
        "atom_economy_percent",
        "rme_percent",
        "hypervolume",
        "best_objective",
        "acceptance_rate",
        "reproduction_accuracy",
    }
)
_BETTER_LOWER: frozenset[str] = frozenset(
    {
        "impurity_percent",
        "e_factor",
        "e_factor_simple",
        "e_factor_complete",
        "pmi",
        "cumulative_regret",
        "experiments_to_target",
        "iteration_latency_seconds",
        "calibration_error",
    }
)


# --------------------------------------------------------------------------- #
# 1. Feedback capture + safety routing.
# --------------------------------------------------------------------------- #
@dataclass
class FeedbackRecord:
    decision: str
    reason: str | None
    free_text: str
    proposal_ref: str
    model_version: str | None
    features: dict[str, Any]
    is_safety_signal: bool
    routes_to_safety_hardening: bool
    is_preference_learnable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "free_text": self.free_text,
            "proposal_ref": self.proposal_ref,
            "model_version": self.model_version,
            "features": self.features,
            "is_safety_signal": self.is_safety_signal,
            "routes_to_safety_hardening": self.routes_to_safety_hardening,
            "is_preference_learnable": self.is_preference_learnable,
            "engine": ENGINE,
        }


def record_feedback(
    *,
    decision: str,
    proposal_ref: str,
    reason: str | None = None,
    free_text: str = "",
    model_version: str | None = None,
    features: Mapping[str, Any] | None = None,
) -> FeedbackRecord:
    """Normalise one piece of chemist feedback and classify its routing.

    A ``reject`` requires a ``reason`` from :data:`REJECTION_REASONS`. An ``unsafe`` rejection is a
    safety signal: it routes to R6 hardening and is excluded from the preference learner.
    """

    if decision not in FEEDBACK_DECISIONS:
        raise ValueError(f"decision must be one of {FEEDBACK_DECISIONS}, got {decision!r}")
    if decision == "reject":
        if reason is None:
            raise ValueError("a reject requires a reason")
        if reason not in REJECTION_REASONS:
            raise ValueError(f"reason must be one of {REJECTION_REASONS}, got {reason!r}")
    elif reason is not None and reason not in REJECTION_REASONS:
        raise ValueError(f"reason must be one of {REJECTION_REASONS}, got {reason!r}")

    # Safety routing depends on the reason alone: ANY record tagged "unsafe" (whatever the
    # decision) is high-signal — it strengthens the R6 screen and is kept out of preference
    # learning, so a contradictory accept/edit + "unsafe" cannot leak a hazard into the re-ranker.
    is_safety_signal = reason == SAFETY_REJECTION_REASON
    return FeedbackRecord(
        decision=decision,
        reason=reason,
        free_text=free_text,
        proposal_ref=proposal_ref,
        model_version=model_version,
        features=dict(features or {}),
        is_safety_signal=is_safety_signal,
        # A safety rejection strengthens the deterministic R6 screen — never auto-learned-around.
        routes_to_safety_hardening=is_safety_signal,
        # Safety rejections are kept out of the preference model on purpose.
        is_preference_learnable=not is_safety_signal,
    )


# --------------------------------------------------------------------------- #
# 2. Preference re-ranker (advisory only).
# --------------------------------------------------------------------------- #
@dataclass
class PreferenceModel:
    # feature_name -> discretised_value -> (accept_weight_sum, count)
    feature_stats: dict[str, dict[str, tuple[float, float]]]
    global_rate: float
    trained_n: int
    excluded_safety_signals: int
    prior_strength: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "global_rate": self.global_rate,
            "trained_n": self.trained_n,
            "excluded_safety_signals": self.excluded_safety_signals,
            "prior_strength": self.prior_strength,
            "features": sorted(self.feature_stats),
            "engine": ENGINE,
        }


def _bucket(value: Any) -> str:
    """Discretise a feature value into a stable bucket key (deterministic, dependency-free)."""

    if isinstance(value, bool):
        return f"bool:{value}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Round numeric features to a coarse bucket so nearby conditions share evidence.
        try:
            return f"num:{round(float(value), 1)}"
        except (TypeError, ValueError):
            return f"raw:{value!r}"
    return f"cat:{value!r}"


def fit_preference_model(
    records: Sequence[FeedbackRecord],
    *,
    prior_strength: float = 2.0,
) -> PreferenceModel:
    """Fit a transparent acceptance-likelihood model from preference-learnable feedback.

    Per discretised feature value we accumulate the acceptance weight (accept=1, edit=0.5,
    reject=0) and a count; prediction is a Beta-smoothed rate toward the global acceptance rate.
    Deterministic — same records (in any order) yield the same model.
    """

    learnable = [r for r in records if r.is_preference_learnable]
    excluded = sum(1 for r in records if not r.is_preference_learnable)
    feature_stats: dict[str, dict[str, tuple[float, float]]] = {}
    total_weight = 0.0
    for record in learnable:
        weight = _DECISION_WEIGHT.get(record.decision, 0.0)
        total_weight += weight
        for name, value in record.features.items():
            bucket = _bucket(value)
            per_feature = feature_stats.setdefault(str(name), {})
            acc, count = per_feature.get(bucket, (0.0, 0.0))
            per_feature[bucket] = (acc + weight, count + 1.0)
    global_rate = total_weight / len(learnable) if learnable else 0.5
    return PreferenceModel(
        feature_stats=feature_stats,
        global_rate=global_rate,
        trained_n=len(learnable),
        excluded_safety_signals=excluded,
        prior_strength=prior_strength,
    )


def predict_acceptance(model: PreferenceModel, features: Mapping[str, Any]) -> float:
    """Predict acceptance likelihood in [0, 1] for a candidate's features.

    Each feature contributes its Beta-smoothed accept rate (smoothed toward ``global_rate`` by
    ``prior_strength`` pseudo-observations); the prediction is their mean. An unseen candidate
    with no known features falls back to the global rate.
    """

    rates: list[float] = []
    for name, value in features.items():
        per_feature = model.feature_stats.get(str(name))
        if not per_feature:
            continue
        stats = per_feature.get(_bucket(value))
        if stats is None:
            continue
        acc, count = stats
        smoothed = (acc + model.prior_strength * model.global_rate) / (count + model.prior_strength)
        rates.append(smoothed)
    if not rates:
        return model.global_rate
    return sum(rates) / len(rates)


@dataclass
class RankedCandidate:
    proposal_ref: str
    acceptance_score: float
    original_rank: int | None
    features: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_ref": self.proposal_ref,
            "acceptance_score": self.acceptance_score,
            "original_rank": self.original_rank,
            "features": self.features,
        }


def rank_by_acceptance(
    model: PreferenceModel,
    candidates: Sequence[Mapping[str, Any]],
) -> list[RankedCandidate]:
    """Re-rank candidates by predicted acceptance (advisory). Ties keep the original order.

    Each candidate is a mapping with ``proposal_ref``, ``features``, and optional ``rank``. The
    optimiser's own ranking is preserved on each item; this is a suggestion, not an override.
    """

    scored: list[tuple[int, RankedCandidate]] = []
    for index, candidate in enumerate(candidates):
        features = dict(candidate.get("features") or {})
        ranked = RankedCandidate(
            proposal_ref=str(candidate.get("proposal_ref") or candidate.get("ref") or index),
            acceptance_score=predict_acceptance(model, features),
            original_rank=candidate.get("rank"),
            features=features,
        )
        scored.append((index, ranked))
    # Stable sort: higher acceptance first, original order breaks ties.
    scored.sort(key=lambda pair: (-pair[1].acceptance_score, pair[0]))
    return [ranked for _, ranked in scored]


# --------------------------------------------------------------------------- #
# 3. A/B champion-vs-challenger promotion gate.
# --------------------------------------------------------------------------- #
@dataclass
class ModelMetrics:
    """A model version's frozen metric vector + its safety-flag recall (the blocking dimension)."""

    model_version: str
    metrics: dict[str, float]
    safety_flag_recall: float


@dataclass
class PromotionVerdict:
    promotable: bool
    safety_regression: bool
    dominates: bool
    requires_human_signoff: bool
    rollback_available: bool
    reasons: list[str] = field(default_factory=list)
    excluded_metrics: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "promotable": self.promotable,
            "safety_regression": self.safety_regression,
            "dominates": self.dominates,
            "requires_human_signoff": self.requires_human_signoff,
            "rollback_available": self.rollback_available,
            "reasons": list(self.reasons),
            "excluded_metrics": list(self.excluded_metrics),
            "engine": ENGINE,
        }


def _valid_recall(value: float) -> bool:
    """A safety-flag recall must be a finite number in [0, 1]; anything else fails closed."""

    return math.isfinite(value) and 0.0 <= value <= 1.0


def _direction(metric: str, directions: Mapping[str, str] | None) -> str | None:
    if directions is not None and metric in directions:
        value = directions[metric]
        return value if value in {"higher", "lower"} else None
    if metric in _BETTER_HIGHER:
        return "higher"
    if metric in _BETTER_LOWER:
        return "lower"
    return None


def dominates(
    challenger: Mapping[str, float],
    champion: Mapping[str, float],
    *,
    directions: Mapping[str, str] | None = None,
    tolerance: float = 0.0,
) -> tuple[bool, list[str]]:
    """Pareto dominance over the metric vector — fail-safe.

    Challenger dominates iff it reports every champion metric, is no worse on every comparable
    metric, and strictly better on at least one. Dominance is **refused** (never silently
    established) when the challenger omits a champion metric or when any compared value is
    non-finite — a challenger cannot hide a regression by dropping or corrupting a dimension.
    Metrics present in both but of unknown direction are excluded and reported (a fail-loud signal
    to register the metric's direction); they do not, on their own, defeat dominance.
    """

    excluded: list[str] = []
    blocking = False  # a champion metric the challenger omits, or a non-finite value -> refuse
    # Any champion dimension the challenger fails to report cannot be certified no-regression.
    missing = sorted(set(champion) - set(challenger))
    if missing:
        excluded.extend(missing)
        blocking = True
    not_worse_all = True
    strictly_better_any = False
    for metric in sorted(set(challenger) & set(champion)):
        direction = _direction(metric, directions)
        if direction is None:
            excluded.append(metric)
            continue
        c_val = float(challenger[metric])
        k_val = float(champion[metric])
        if not (math.isfinite(c_val) and math.isfinite(k_val)):
            excluded.append(metric)
            blocking = True
            continue
        if direction == "higher":
            if c_val < k_val - tolerance:
                not_worse_all = False
            if c_val > k_val + tolerance:
                strictly_better_any = True
        else:  # lower is better
            if c_val > k_val + tolerance:
                not_worse_all = False
            if c_val < k_val - tolerance:
                strictly_better_any = True
    dom = (not blocking) and not_worse_all and strictly_better_any
    return dom, sorted(set(excluded))


def evaluate_ab_promotion(
    champion: ModelMetrics,
    challenger: ModelMetrics,
    *,
    directions: Mapping[str, str] | None = None,
    tolerance: float = 0.0,
) -> PromotionVerdict:
    """Gate a challenger for promotion: safety-recall must not regress AND it must dominate.

    Promotion is **never automatic**: ``requires_human_signoff`` is always true and a champion
    pointer is always rollback-able. This mirrors the platform-wide v0.14 dominance gate, scoped
    to reaction models with safety-flag recall as the hard, blocking dimension.
    """

    reasons: list[str] = []
    # The safety gate is exact and fail-closed: a missing / non-finite / out-of-range recall blocks,
    # and the metric `tolerance` is NEVER applied here — safety-flag recall must not regress at all.
    champion_ok = _valid_recall(champion.safety_flag_recall)
    challenger_ok = _valid_recall(challenger.safety_flag_recall)
    if not (champion_ok and challenger_ok):
        safety_regression = True
        reasons.append("Safety-flag recall is missing or out of range [0, 1]; failing closed.")
    elif challenger.safety_flag_recall < champion.safety_flag_recall:
        safety_regression = True
        reasons.append(
            "Safety-flag recall regressed "
            f"({challenger.safety_flag_recall:g} < {champion.safety_flag_recall:g}); blocked."
        )
    else:
        safety_regression = False
    dom, excluded = dominates(
        challenger.metrics, champion.metrics, directions=directions, tolerance=tolerance
    )
    if not dom:
        reasons.append("Challenger does not dominate the champion's metric vector; blocked.")
    if excluded:
        reasons.append(f"Metrics excluded for unknown direction: {excluded}.")
    promotable = (not safety_regression) and dom
    if promotable:
        reasons.append(
            "Eligible: no safety regression and metric-vector dominance — human sign-off required."
        )
    return PromotionVerdict(
        promotable=promotable,
        safety_regression=safety_regression,
        dominates=dom,
        requires_human_signoff=True,
        rollback_available=True,
        reasons=reasons,
        excluded_metrics=excluded,
    )
