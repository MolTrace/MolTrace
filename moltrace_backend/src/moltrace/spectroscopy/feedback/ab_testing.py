"""A/B champion vs challenger rollout (Prompt 23, Roadmap Phases 5-6).

When Prompt 15 registers a fine-tuned **challenger** (a non-production artifact in
the Prompt 13 registry), this module routes a controlled slice of production
traffic to it alongside the current **champion** (the production artifact), then
decides -- but never *applies* -- promotion on hard evidence.

Three concerns, kept separate:

1. **Routing** (:class:`ABRouter`) -- deterministic, *sticky* assignment. A request's
   arm is a stable hash of its routing key, so the same entity always lands in the
   same arm (no flapping). Two modes: ``SHADOW`` (challenger is computed and logged
   but **never served** -- 0% user-facing) and ``CANARY`` (a controlled fraction is
   served by the challenger; the champion serves the rest and is always the
   fallback).
2. **Comparison** (:class:`ArmStats`, :func:`evaluate_promotion`) -- each arm is
   scored on the live Prompt 17 metric vector *plus* reviewer-acceptance and
   override rate mined from the Prompt 23 feedback stream.
3. **Promotion** (:class:`ABTest`) -- the gated, human-driven action.

**Promotion rule.** A challenger is *recommended* for promotion only when it
(a) **dominates** the champion on the Prompt 17 metric vector with **no
safety-critical regression** (:func:`~eval.harness.dominates`), (b) does **not**
worsen the reviewer override rate, (c) does **not** worsen reviewer acceptance, and
(d) passes the **Prompt 18 fail-closed gate**. Even then it **never auto-deploys**:
:meth:`ABTest.promote` refuses to mutate the registry without an explicit
``signed_off_by`` -- a human sign-off.

**Instant rollback.** :meth:`ABTest.rollback` routes 100% of traffic back to the
champion by zeroing the challenger's traffic fraction at the *routing layer*. The
champion never leaves ``production`` during a test, so rollback is instantaneous
and lossless -- it never tries to re-promote a retired model (registry retirement
is terminal). Registry promotion is the separate, signed-off, one-way action.

Only the standard library + the in-repo registry / harness / feedback layers are
imported, so the controller runs anywhere those do.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from moltrace.spectroscopy.ai.registry import (
    ModelEntry,
    ModelRegistry,
    ModelRole,
    ModelStatus,
    StatusTransition,
)
from moltrace.spectroscopy.eval.harness import GoldMetricVector, MetricDelta, dominates
from moltrace.spectroscopy.feedback.capture import FeedbackEvent, usage_analytics

__all__ = [
    "ABAssignment",
    "ABRouter",
    "ABTest",
    "ABTestError",
    "Arm",
    "ArmStats",
    "PromotionBlocked",
    "PromotionDecision",
    "RoutingMode",
    "evaluate_promotion",
]


class ABTestError(RuntimeError):
    """Raised when an A/B test is misconfigured (bad arm, missing champion, ...)."""


class PromotionBlocked(ABTestError):
    """Raised when a promotion is attempted without a positive decision + sign-off."""


class Arm(StrEnum):
    """Which arm of the A/B test served a request."""

    CHAMPION = "champion"
    CHALLENGER = "challenger"


class RoutingMode(StrEnum):
    """How challenger traffic is handled."""

    SHADOW = "shadow"  # challenger computed + logged, NEVER served (0% user-facing)
    CANARY = "canary"  # a controlled fraction is served by the challenger


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _bucket(key: str) -> float:
    """Deterministic, uniform hash of ``key`` into ``[0, 1)`` (sticky assignment)."""

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(1 << 64)


def _check_fraction(fraction: float) -> float:
    if not 0.0 <= fraction <= 1.0:
        raise ABTestError(f"traffic fraction must be in [0, 1], got {fraction!r}")
    return float(fraction)


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ABAssignment:
    """The (deterministic) routing decision for one request.

    ``arm`` / ``served_model_id`` is what the user sees. ``shadow_model_id`` is a
    challenger that was evaluated *off the serving path* (always set in ``SHADOW``
    mode for sampled traffic; ``None`` otherwise).
    """

    arm: Arm
    served_model_id: str
    shadow_model_id: str | None
    routing_key: str
    bucket: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm.value,
            "served_model_id": self.served_model_id,
            "shadow_model_id": self.shadow_model_id,
            "routing_key": self.routing_key,
            "bucket": self.bucket,
        }


class ABRouter:
    """Deterministic, sticky traffic router between a champion and a challenger.

    Routing is a stable hash of the routing key salted per test, so an entity's arm
    never flaps between calls. ``traffic_fraction`` is the served fraction in
    ``CANARY`` mode and the shadow-sampled fraction in ``SHADOW`` mode. The router
    holds *live* routing state (so :meth:`rollback` can flip it instantly); it is
    intentionally mutable, unlike the content-addressed records elsewhere.
    """

    def __init__(
        self,
        *,
        champion_model_id: str,
        challenger_model_id: str,
        mode: RoutingMode | str = RoutingMode.SHADOW,
        traffic_fraction: float = 1.0,
        salt: str = "",
    ) -> None:
        self.champion_model_id = champion_model_id
        self.challenger_model_id = challenger_model_id
        self.mode = RoutingMode(mode)
        self.traffic_fraction = _check_fraction(traffic_fraction)
        self.salt = salt
        self.rolled_back = False
        self.rollback_reason: str | None = None

    def set_fraction(self, fraction: float) -> None:
        """Ramp the challenger's traffic fraction (e.g. canary 1% -> 5% -> 25%)."""

        self.traffic_fraction = _check_fraction(fraction)

    def rollback(self, *, reason: str | None = None) -> None:
        """Instant rollback: route 100% of traffic back to the champion."""

        self.traffic_fraction = 0.0
        self.rolled_back = True
        self.rollback_reason = reason

    def assign(self, routing_key: str) -> ABAssignment:
        """Resolve the arm for ``routing_key`` (stable across calls)."""

        bucket = _bucket(f"{self.salt}\x1f{routing_key}")
        sampled = bucket < self.traffic_fraction
        if self.mode is RoutingMode.SHADOW:
            # Champion always serves; challenger is shadow-evaluated on sampled traffic.
            return ABAssignment(
                arm=Arm.CHAMPION,
                served_model_id=self.champion_model_id,
                shadow_model_id=self.challenger_model_id if sampled else None,
                routing_key=routing_key,
                bucket=bucket,
            )
        # CANARY: the sampled fraction is served by the challenger; champion is the
        # fallback for everything else (and for the whole stream after a rollback).
        if sampled:
            return ABAssignment(
                arm=Arm.CHALLENGER,
                served_model_id=self.challenger_model_id,
                shadow_model_id=None,
                routing_key=routing_key,
                bucket=bucket,
            )
        return ABAssignment(
            arm=Arm.CHAMPION,
            served_model_id=self.champion_model_id,
            shadow_model_id=None,
            routing_key=routing_key,
            bucket=bucket,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "champion_model_id": self.champion_model_id,
            "challenger_model_id": self.challenger_model_id,
            "mode": self.mode.value,
            "traffic_fraction": self.traffic_fraction,
            "rolled_back": self.rolled_back,
            "rollback_reason": self.rollback_reason,
        }


# --------------------------------------------------------------------------- #
# Per-arm live statistics
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ArmStats:
    """One arm's live evidence: Prompt 17 metrics + reviewer signals."""

    arm: Arm
    model_id: str
    metrics: GoldMetricVector
    n_feedback: int
    reviewer_acceptance_rate: float  # thumbs-up / n_feedback
    override_rate: float  # thumbs-down / n_feedback

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm.value,
            "model_id": self.model_id,
            "metrics": self.metrics.as_dict(),
            "n_feedback": self.n_feedback,
            "reviewer_acceptance_rate": self.reviewer_acceptance_rate,
            "override_rate": self.override_rate,
        }


def _arm_feedback_stats(
    events: Iterable[FeedbackEvent],
    *,
    model_id: str,
    model_versions_key: str | None,
) -> tuple[int, float, float]:
    """(n, reviewer_acceptance_rate, override_rate) for events attributable to a model."""

    def matches(event: FeedbackEvent) -> bool:
        if model_versions_key is not None:
            return event.model_versions.get(model_versions_key) == model_id
        return model_id in event.model_versions.values()

    selected = [e for e in events if matches(e)]
    analytics = usage_analytics(selected)
    n = analytics.n_events
    acceptance = (analytics.thumbs_up / n) if n else 0.0
    return n, acceptance, analytics.override_rate


# --------------------------------------------------------------------------- #
# Promotion decision (advisory -- never auto-applied)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PromotionDecision:
    """The evidence-based recommendation. ``promote`` is advice, not an action.

    Even when ``promote`` is ``True``, ``requires_sign_off`` is always ``True`` and
    :meth:`ABTest.promote` still demands an explicit human ``signed_off_by`` before
    touching the registry.
    """

    promote: bool
    dominates: bool
    safety_ok: bool
    override_ok: bool
    acceptance_ok: bool
    gate_ok: bool
    requires_sign_off: bool
    champion: ArmStats
    challenger: ArmStats
    deltas: tuple[MetricDelta, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "promote": self.promote,
            "dominates": self.dominates,
            "safety_ok": self.safety_ok,
            "override_ok": self.override_ok,
            "acceptance_ok": self.acceptance_ok,
            "gate_ok": self.gate_ok,
            "requires_sign_off": self.requires_sign_off,
            "champion": self.champion.as_dict(),
            "challenger": self.challenger.as_dict(),
            "deltas": [
                {
                    "metric": d.metric,
                    "candidate": d.candidate,
                    "incumbent": d.incumbent,
                    "improvement": d.improvement,
                    "regressed": d.regressed,
                    "improved": d.improved,
                    "safety_critical": d.safety_critical,
                }
                for d in self.deltas
            ],
            "reasons": list(self.reasons),
        }


def evaluate_promotion(
    champion: ArmStats,
    challenger: ArmStats,
    *,
    tolerances: Mapping[str, float] | None = None,
    override_tolerance: float = 0.0,
    acceptance_tolerance: float = 0.0,
    gate_exit_code: int | None = None,
    require_gate: bool = True,
) -> PromotionDecision:
    """Apply the full promotion rule and return a (never auto-applied) recommendation.

    A positive recommendation requires **all** of: Prompt 17 dominance with no
    safety-critical regression; the challenger's override rate no worse than the
    champion's (within ``override_tolerance``); reviewer acceptance no worse (within
    ``acceptance_tolerance``); and -- when ``require_gate`` -- a passing Prompt 18
    gate (``gate_exit_code == 0``).
    """

    passed, deltas = dominates(challenger.metrics, champion.metrics, tolerances)
    safety_ok = not any(d.safety_critical and d.regressed for d in deltas)
    override_ok = challenger.override_rate <= champion.override_rate + override_tolerance
    acceptance_ok = (
        challenger.reviewer_acceptance_rate
        >= champion.reviewer_acceptance_rate - acceptance_tolerance
    )
    if require_gate:
        gate_ok = gate_exit_code == 0
    else:
        gate_ok = True

    reasons: list[str] = []
    if not passed:
        reasons.append("no Prompt 17 dominance (regression beyond tolerance or no strict gain)")
    for d in deltas:
        if d.safety_critical and d.regressed:
            reasons.append(f"safety-critical regression on {d.metric}")
    if not override_ok:
        reasons.append(
            f"override rate worse: {challenger.override_rate:.4f} > {champion.override_rate:.4f}"
        )
    if not acceptance_ok:
        reasons.append(
            "reviewer acceptance worse: "
            f"{challenger.reviewer_acceptance_rate:.4f} < {champion.reviewer_acceptance_rate:.4f}"
        )
    if not gate_ok:
        reasons.append("Prompt 18 fail-closed gate not passed (gate_exit_code != 0)")

    promote = passed and safety_ok and override_ok and acceptance_ok and gate_ok
    return PromotionDecision(
        promote=promote,
        dominates=passed,
        safety_ok=safety_ok,
        override_ok=override_ok,
        acceptance_ok=acceptance_ok,
        gate_ok=gate_ok,
        requires_sign_off=True,  # human sign-off is ALWAYS required -- no auto-deploy
        champion=champion,
        challenger=challenger,
        deltas=tuple(deltas),
        reasons=tuple(reasons),
    )


# --------------------------------------------------------------------------- #
# The controller
# --------------------------------------------------------------------------- #
class ABTest:
    """Orchestrates a champion-vs-challenger rollout over the Prompt 13 registry.

    The champion is the current ``production`` artifact for ``(role, nucleus)`` and
    **stays** production for the whole test; the challenger is a registered
    ``candidate`` / ``shadow`` artifact that only *serves* via the routing layer.
    Promotion (the one registry mutation) is gated and requires human sign-off;
    rollback is an instant routing-layer flip that never touches the registry.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        role: ModelRole | str,
        nucleus: str | None = None,
        feedback_model_versions_key: str | None = None,
        clock: Callable[[], str] = _now_iso,
    ) -> None:
        self.registry = registry
        self.role = ModelRole(role)
        self.nucleus = nucleus
        self._versions_key = feedback_model_versions_key
        self._clock = clock
        self._router: ABRouter | None = None
        self._challenger_id: str | None = None

    @property
    def champion(self) -> ModelEntry:
        champ = self.registry.resolve(self.role, self.nucleus)
        if champ is None:
            raise ABTestError(
                f"no production champion for role={self.role.value} nucleus={self.nucleus!r}; "
                "cannot start an A/B test"
            )
        return champ

    def start(
        self,
        *,
        challenger_model_id: str,
        mode: RoutingMode | str = RoutingMode.SHADOW,
        traffic_fraction: float = 1.0,
        salt: str | None = None,
    ) -> ABRouter:
        """Begin routing against ``challenger_model_id`` (champion resolved live).

        Defaults to ``SHADOW`` at 100% sampling (challenger fully evaluated, never
        served) -- the safe default. Switch to ``CANARY`` with a small
        ``traffic_fraction`` to serve a controlled slice.
        """

        champ = self.champion  # raises if there is no production champion
        challenger = self.registry.get(challenger_model_id)  # raises if unknown
        status = self.registry.current_status(challenger_model_id)
        if status not in (ModelStatus.CANDIDATE, ModelStatus.SHADOW):
            raise ABTestError(
                f"challenger {challenger_model_id!r} must be candidate/shadow, is {status.value}"
            )
        if challenger.role != self.role or challenger.nucleus != self.nucleus:
            raise ABTestError(
                "challenger role/nucleus must match the champion's "
                f"({self.role.value}/{self.nucleus!r})"
            )
        if challenger_model_id == champ.model_id:
            raise ABTestError("challenger must differ from the champion")

        self._challenger_id = challenger_model_id
        self._router = ABRouter(
            champion_model_id=champ.model_id,
            challenger_model_id=challenger_model_id,
            mode=mode,
            traffic_fraction=traffic_fraction,
            salt=salt if salt is not None else f"{self.role.value}:{self.nucleus or ''}",
        )
        return self._router

    def router(self) -> ABRouter:
        if self._router is None:
            raise ABTestError("A/B test not started; call start() first")
        return self._router

    def rollback(self, *, reason: str | None = None) -> None:
        """Instant rollback to the champion (routing-layer kill, no registry change)."""

        self.router().rollback(reason=reason)

    def arm_stats(
        self,
        arm: Arm,
        metrics: GoldMetricVector,
        feedback_events: Iterable[FeedbackEvent] = (),
    ) -> ArmStats:
        """Bundle an arm's Prompt 17 metrics with its mined reviewer signals."""

        router = self.router()
        model_id = router.champion_model_id if arm is Arm.CHAMPION else router.challenger_model_id
        n, acceptance, override = _arm_feedback_stats(
            feedback_events, model_id=model_id, model_versions_key=self._versions_key
        )
        return ArmStats(
            arm=arm,
            model_id=model_id,
            metrics=metrics,
            n_feedback=n,
            reviewer_acceptance_rate=acceptance,
            override_rate=override,
        )

    def evaluate(
        self,
        *,
        champion_metrics: GoldMetricVector,
        challenger_metrics: GoldMetricVector,
        feedback_events: Iterable[FeedbackEvent] = (),
        tolerances: Mapping[str, float] | None = None,
        override_tolerance: float = 0.0,
        acceptance_tolerance: float = 0.0,
        gate_exit_code: int | None = None,
        require_gate: bool = True,
    ) -> PromotionDecision:
        """Score both arms and apply the promotion rule (recommendation only)."""

        events = list(feedback_events)
        champion = self.arm_stats(Arm.CHAMPION, champion_metrics, events)
        challenger = self.arm_stats(Arm.CHALLENGER, challenger_metrics, events)
        return evaluate_promotion(
            champion,
            challenger,
            tolerances=tolerances,
            override_tolerance=override_tolerance,
            acceptance_tolerance=acceptance_tolerance,
            gate_exit_code=gate_exit_code,
            require_gate=require_gate,
        )

    def promote(
        self,
        decision: PromotionDecision,
        *,
        signed_off_by: str,
        reason: str | None = None,
    ) -> StatusTransition:
        """Promote the challenger to production -- gated, one-way, never automatic.

        Refuses unless ``decision.promote`` is ``True`` *and* a non-empty
        ``signed_off_by`` is supplied. Delegates to the registry, which atomically
        retires the superseded champion.
        """

        if self._router is None or self._challenger_id is None:
            raise ABTestError("A/B test not started; call start() first")
        if not decision.promote:
            blockers = ", ".join(decision.reasons) or "challenger did not dominate the champion"
            raise PromotionBlocked(f"challenger is not promotable: {blockers}")
        if not signed_off_by or not str(signed_off_by).strip():
            raise PromotionBlocked(
                "human sign-off is required to promote a challenger (no auto-deploy)"
            )
        note = reason or "A/B challenger dominates champion"
        return self.registry.promote(
            self._challenger_id, reason=f"{note} (signed off by {signed_off_by})"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role.value,
            "nucleus": self.nucleus,
            "challenger_model_id": self._challenger_id,
            "router": self._router.as_dict() if self._router is not None else None,
        }
