"""Closed-loop feedback: capture -> reward model -> A/B rollout (Prompt 23).

This package turns reviewer interaction into a compounding data moat -- the
production loop that lets the science improve itself without ever letting a model
override the science:

* :mod:`.capture` -- the single in-app feedback intake. Every AI output (predicted
  shift, proposed structure, peak label, purity call, ...) is rated with a
  thumbs up/down + optional free-text correction + a structured reason taxonomy.
  Each click becomes an immutable, content-addressed
  :class:`~moltrace.spectroscopy.feedback.capture.FeedbackEvent` carrying the
  Prompt 13 ``model_versions`` that produced it. Corrections fan out to the Prompt
  16 labeled-example store; bare overrides go to the active-learning queue; usage /
  override analytics roll up where the model is weakest.
* :mod:`.reward_model` -- an RLHF-style preference model. Corrections + accept/reject
  signals become (chosen, rejected) pairs; a deterministic Bradley-Terry reward
  model scores candidate outputs by likely reviewer acceptance. It re-ranks the
  Prompt 14 reasoner's candidates and prioritises the Prompt 16 annotation queue --
  **advisory only**; the deterministic Prompt 7 verifier still arbitrates.
* :mod:`.ab_testing` -- champion vs challenger rollout. A registered challenger gets
  a controlled (or shadow) slice of traffic; promotion is gated on Prompt 17
  dominance with no safety regression plus reviewer guards and the Prompt 18 gate,
  **never auto-deploys** (human sign-off required), and supports instant rollback.
"""

from __future__ import annotations

from moltrace.spectroscopy.feedback.ab_testing import (
    ABAssignment,
    ABRouter,
    ABTest,
    ABTestError,
    Arm,
    ArmStats,
    PromotionBlocked,
    PromotionDecision,
    RoutingMode,
    evaluate_promotion,
)
from moltrace.spectroscopy.feedback.capture import (
    FeedbackCollector,
    FeedbackEvent,
    FeedbackStore,
    FeedbackVerdict,
    InMemoryFeedbackStore,
    LabeledExample,
    OutputKind,
    ReasonCode,
    SqlAlchemyFeedbackStore,
    UsageAnalytics,
    usage_analytics,
)
from moltrace.spectroscopy.feedback.reward_model import (
    Preference,
    PrioritizedItem,
    RankedByReward,
    RewardModel,
    RewardModelError,
    RewardModelRun,
    build_preference_dataset,
    default_candidate_features,
    prioritize_annotation_queue,
    rank_candidates,
    reward_scorer,
    train_reward_model,
)

__all__ = [
    "ABAssignment",
    "ABRouter",
    "ABTest",
    "ABTestError",
    "Arm",
    "ArmStats",
    "FeedbackCollector",
    "FeedbackEvent",
    "FeedbackStore",
    "FeedbackVerdict",
    "InMemoryFeedbackStore",
    "LabeledExample",
    "OutputKind",
    "Preference",
    "PrioritizedItem",
    "PromotionBlocked",
    "PromotionDecision",
    "RankedByReward",
    "ReasonCode",
    "RewardModel",
    "RewardModelError",
    "RewardModelRun",
    "RoutingMode",
    "SqlAlchemyFeedbackStore",
    "UsageAnalytics",
    "build_preference_dataset",
    "default_candidate_features",
    "evaluate_promotion",
    "prioritize_annotation_queue",
    "rank_candidates",
    "reward_scorer",
    "train_reward_model",
    "usage_analytics",
]
