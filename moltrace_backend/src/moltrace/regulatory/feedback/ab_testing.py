"""A/B champion vs challenger for narrative models/templates (Prompt 22, Phase 6).

Runs a shadow/controlled comparison of a challenger narrative model/template (Prompt 15) against the
production champion on the Prompt 17 metric vector + reviewer acceptance.

PROMOTION RULE (the challenger replaces the champion ONLY if ALL hold):
  * ZERO calculation-error regression — the deterministic math is shared and frozen; if calc error
    is measured at all it must be 0 and never worse than the champion;
  * NO citation-correctness regression and DOMINANCE on narrative metrics (Prompt 15 gate);
  * reviewer acceptance is not worse;
  * the Prompt 18 fail-closed deployment gate is green;
  * an explicit human sign-off (never auto-deploy).
Instant rollback is always available — the champion stays in production throughout (the challenger
runs SHADOW / CANARY), so a rollback is a routing flip with no re-promotion.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from moltrace.regulatory.ai.finetune import narrative_promotion_gate
from moltrace.regulatory.infra import RegulatoryMetricVector

__all__ = [
    "ABAssignment",
    "ABRouter",
    "ABTest",
    "ABTestError",
    "Arm",
    "ArmStats",
    "Promotion",
    "PromotionBlocked",
    "PromotionDecision",
    "RoutingMode",
    "evaluate_promotion",
]

_EPS = 1e-9


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ABTestError(RuntimeError):
    """Base class for A/B testing errors."""


class PromotionBlocked(ABTestError):
    """Raised when a challenger promotion is attempted without meeting the rule + human sign-off."""


class Arm(StrEnum):
    CHAMPION = "champion"
    CHALLENGER = "challenger"


class RoutingMode(StrEnum):
    SHADOW = "shadow"  # challenger computed + logged, NEVER served (0% user-facing)
    CANARY = "canary"  # a controlled fraction is served by the challenger


@dataclass(frozen=True)
class ABAssignment:
    arm: Arm
    served_model_id: str  # what the user actually sees
    shadow_model_id: str | None  # the challenger computed in the background (SHADOW)
    routing_key: str
    bucket: float


class ABRouter:
    """Deterministic, sticky champion/challenger routing with an instant kill-switch (rollback)."""

    def __init__(
        self,
        *,
        champion_model_id: str,
        challenger_model_id: str,
        mode: RoutingMode = RoutingMode.SHADOW,
        traffic_fraction: float = 1.0,
        salt: str = "",
    ) -> None:
        self.champion_model_id = champion_model_id
        self.challenger_model_id = challenger_model_id
        self.mode = mode
        self.traffic_fraction = traffic_fraction
        self.salt = salt
        self.rolled_back = False
        self.rollback_reason: str | None = None

    def _bucket(self, routing_key: str) -> float:
        digest = hashlib.sha256(f"{self.salt}|{routing_key}".encode()).hexdigest()
        return int(digest[:16], 16) / float(1 << 64)

    def assign(self, routing_key: str) -> ABAssignment:
        bucket = self._bucket(routing_key)
        # SHADOW (or rolled-back / canary miss) -> the user is served the CHAMPION; the challenger
        # may still be computed in the background for comparison but is never user-facing.
        if self.rolled_back or self.mode is RoutingMode.SHADOW or bucket >= self.traffic_fraction:
            shadow = None if self.rolled_back else self.challenger_model_id
            return ABAssignment(Arm.CHAMPION, self.champion_model_id, shadow, routing_key, bucket)
        return ABAssignment(
            Arm.CHALLENGER, self.challenger_model_id, None, routing_key, bucket
        )

    def set_fraction(self, fraction: float) -> None:
        self.traffic_fraction = max(0.0, min(1.0, fraction))

    def rollback(self, *, reason: str | None = None) -> None:
        """Instant rollback: the champion serves 100%, the challenger is no longer computed."""

        self.rolled_back = True
        self.rollback_reason = reason
        self.traffic_fraction = 0.0


@dataclass(frozen=True)
class ArmStats:
    """One arm's measured performance over the comparison window."""

    arm: Arm
    model_id: str
    metrics: RegulatoryMetricVector  # Prompt 17 metric vector
    n_feedback: int = 0
    reviewer_acceptance_rate: float = 0.0
    override_rate: float = 0.0


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    calc_ok: bool  # zero calculation-error regression (deterministic math frozen)
    narrative_dominates: bool  # citation no-regression + narrative dominance (Prompt 15 gate)
    acceptance_ok: bool
    gate_ok: bool  # Prompt 18 fail-closed deployment gate
    requires_sign_off: bool  # ALWAYS True — never auto-deploy
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "promote": self.promote,
            "calc_ok": self.calc_ok,
            "narrative_dominates": self.narrative_dominates,
            "acceptance_ok": self.acceptance_ok,
            "gate_ok": self.gate_ok,
            "requires_sign_off": self.requires_sign_off,
            "reasons": list(self.reasons),
        }


def _calc_regression_ok(
    challenger: RegulatoryMetricVector, champion: RegulatoryMetricVector
) -> tuple[bool, str | None]:
    cc = challenger.calculation_error_rate
    ch = champion.calculation_error_rate
    if cc is None:
        return True, None  # narrative challenger doesn't touch the math — nothing to regress
    if cc > _EPS:
        return False, f"challenger has calculation errors ({cc} > 0); the math must stay exact"
    if ch is not None and cc > ch + _EPS:
        return False, f"calculation-error regression {ch} -> {cc}"
    return True, None


def evaluate_promotion(
    champion: ArmStats,
    challenger: ArmStats,
    *,
    deploy_allowed: bool | None = None,
    require_gate: bool = True,
    acceptance_tolerance: float = 0.0,
) -> PromotionDecision:
    """Apply the promotion rule. ``deploy_allowed`` is the Prompt 18 gate verdict (fail-closed)."""

    reasons: list[str] = []

    calc_ok, calc_reason = _calc_regression_ok(challenger.metrics, champion.metrics)
    if calc_reason:
        reasons.append(calc_reason)

    narrative_dominates, gate_reasons = narrative_promotion_gate(
        challenger.metrics, champion.metrics
    )
    reasons.extend(gate_reasons)

    acceptance_ok = (
        challenger.reviewer_acceptance_rate
        >= champion.reviewer_acceptance_rate - acceptance_tolerance
    )
    if not acceptance_ok:
        reasons.append(
            f"reviewer acceptance regressed {champion.reviewer_acceptance_rate} -> "
            f"{challenger.reviewer_acceptance_rate}"
        )

    gate_ok = (deploy_allowed is True) if require_gate else True
    if require_gate and not gate_ok:
        reasons.append("Prompt 18 fail-closed deployment gate not green")

    promote = calc_ok and narrative_dominates and acceptance_ok and gate_ok
    return PromotionDecision(
        promote=promote,
        calc_ok=calc_ok,
        narrative_dominates=narrative_dominates,
        acceptance_ok=acceptance_ok,
        gate_ok=gate_ok,
        requires_sign_off=True,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class Promotion:
    """The record of a (human-signed-off, gate-passed) champion replacement."""

    new_champion_model_id: str
    previous_champion_model_id: str
    signed_off_by: str
    reason: str | None
    decision: PromotionDecision
    promoted_utc: str


class ABTest:
    """Drive a champion/challenger comparison: gated, signed-off promotion + instant rollback."""

    def __init__(self, *, champion_model_id: str) -> None:
        self.champion_model_id = champion_model_id
        self.router: ABRouter | None = None
        self._challenger_id: str | None = None

    def start(
        self,
        *,
        challenger_model_id: str,
        mode: RoutingMode = RoutingMode.SHADOW,
        traffic_fraction: float = 1.0,
        salt: str = "",
    ) -> ABRouter:
        self._challenger_id = challenger_model_id
        self.router = ABRouter(
            champion_model_id=self.champion_model_id,
            challenger_model_id=challenger_model_id,
            mode=mode,
            traffic_fraction=traffic_fraction,
            salt=salt,
        )
        return self.router

    def evaluate(
        self,
        champion: ArmStats,
        challenger: ArmStats,
        *,
        deploy_allowed: bool | None = None,
        require_gate: bool = True,
        acceptance_tolerance: float = 0.0,
    ) -> PromotionDecision:
        return evaluate_promotion(
            champion,
            challenger,
            deploy_allowed=deploy_allowed,
            require_gate=require_gate,
            acceptance_tolerance=acceptance_tolerance,
        )

    def promote(
        self, decision: PromotionDecision, *, signed_off_by: str, reason: str | None = None,
        now: str | None = None,
    ) -> Promotion:
        """Replace the champion — gated, one-way, requires a human sign-off (never auto-deploy)."""

        if not decision.promote:
            raise PromotionBlocked(
                f"promotion rule not satisfied: {list(decision.reasons)}"
            )
        if not signed_off_by or not signed_off_by.strip():
            raise PromotionBlocked("a human sign-off (signed_off_by) is required; no auto-deploy")
        if self._challenger_id is None:
            raise ABTestError("no challenger — call start() first")
        previous = self.champion_model_id
        promotion = Promotion(
            new_champion_model_id=self._challenger_id,
            previous_champion_model_id=previous,
            signed_off_by=signed_off_by,
            reason=reason,
            decision=decision,
            promoted_utc=now or _now_iso(),
        )
        self.champion_model_id = self._challenger_id
        if self.router is not None:
            self.router.champion_model_id = self._challenger_id
        return promotion

    def rollback(self, *, reason: str | None = None) -> None:
        """Instantly route 100% back to the champion — lossless (champion never left production)."""

        if self.router is not None:
            self.router.rollback(reason=reason)
