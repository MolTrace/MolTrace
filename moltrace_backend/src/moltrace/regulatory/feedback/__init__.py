"""Closed-loop feedback for regulatory narrative quality (Prompt 22, Phases 5-6).

A capture → reward → rollout loop that sharpens submission drafting while the regulated math stays
deterministic and frozen:

* :mod:`capture` — the in-app "Was this correct/acceptable?" signal (accept/edit + free-text +
  reason taxonomy), persisted with rule-set + model versions; a CLASSIFICATION override is routed to
  a toxicologist (Prompt 16), never silent learning; a NARRATIVE edit feeds the review log.
* :mod:`narrative_reward` — an RLHF-style preference + Bradley-Terry reward model over TEXT features
  ONLY (it can never read or influence a number/limit/classification); ranks narratives and
  prioritises the Prompt 16 review queue.
* :mod:`ab_testing` — champion vs challenger (Prompt 15) with the promotion rule (zero
  calculation-error regression, no citation-correctness regression, narrative dominance, Prompt 18
  fail-closed gate, human sign-off) and instant rollback.
"""

from __future__ import annotations

from moltrace.regulatory.feedback.ab_testing import (
    ABAssignment,
    ABRouter,
    ABTest,
    ABTestError,
    Arm,
    ArmStats,
    Promotion,
    PromotionBlocked,
    PromotionDecision,
    RoutingMode,
    evaluate_promotion,
)
from moltrace.regulatory.feedback.capture import (
    CaptureResult,
    FeedbackEvent,
    FeedbackStore,
    FeedbackVerdict,
    InMemoryFeedbackStore,
    OutputKind,
    ReasonCode,
    capture_feedback,
    feedback_events,
)
from moltrace.regulatory.feedback.narrative_reward import (
    NARRATIVE_FEATURE_NAMES,
    NarrativeRewardModel,
    Preference,
    RankedNarrative,
    RewardModelError,
    RewardModelRun,
    build_preference_dataset,
    default_narrative_features,
    prioritize_narrative_queue,
    rank_narratives,
    train_narrative_reward_model,
)

__all__ = [
    "ABAssignment",
    "ABRouter",
    "ABTest",
    "ABTestError",
    "Arm",
    "ArmStats",
    "CaptureResult",
    "FeedbackEvent",
    "FeedbackStore",
    "FeedbackVerdict",
    "InMemoryFeedbackStore",
    "NARRATIVE_FEATURE_NAMES",
    "NarrativeRewardModel",
    "OutputKind",
    "Preference",
    "Promotion",
    "PromotionBlocked",
    "PromotionDecision",
    "RankedNarrative",
    "ReasonCode",
    "RewardModelError",
    "RewardModelRun",
    "RoutingMode",
    "build_preference_dataset",
    "capture_feedback",
    "default_narrative_features",
    "evaluate_promotion",
    "feedback_events",
    "prioritize_narrative_queue",
    "rank_narratives",
    "train_narrative_reward_model",
]
