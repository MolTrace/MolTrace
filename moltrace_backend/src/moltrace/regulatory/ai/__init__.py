"""Deterministic-first regulatory model & rule registry + router + RAG reasoning (Prompts 13-14).

Regulatory math is NEVER produced by a stochastic model. :mod:`registry` versions
every artifact that can touch a regulatory output -- the deterministic rule-engines
(which ICH/FDA revision a formula set encodes) and the AI artifacts used only for
narrative / retrieval / triage -- and :mod:`router` enforces the routing rule:
anything quantitative or classification-based goes to the deterministic engine ONLY,
LLMs draft and retrieve. Every result carries the exact rule-set + model versions and
citations -- the provenance the Annex 22 audit wrapper (Prompt 12) records.

:mod:`rag_reasoner` (Prompt 14) is the retrieval-augmented reasoning layer over the Prompt 10
corpus: it answers a regulatory question grounded ONLY in retrieved guidance passages, cites and
links the official source for every claim, and defers any numeric value to the deterministic engine
above -- returning a validated :class:`GroundedAnswer` flagged for qualified review.

:mod:`active_learning` (Prompt 16) closes the reviewer-feedback loop: it captures every reviewer
edit/override/adjudication as append-only labeled data with full provenance, routes borderline
CPCA/M7 classifications to a toxicologist (and narrative drafts by disagreement sampling), and
triggers a narrative-only retrain -- classifications never auto-retrain and are never re-classified.

:mod:`finetune` (Prompt 15) LoRA fine-tunes the NARRATIVE model on approved narratives only (the
regulated math is frozen): an approved-only, identifier-masked, hashed snapshot; leak-proof K-fold
CV with narrative-quality metrics; a narrative adapter registered with lineage and promotion gated
on citation no-regression. It never fine-tunes anything that produces a number or classification.
"""

from __future__ import annotations

from moltrace.regulatory.ai.active_learning import (
    ClassificationCandidate,
    LabeledExample,
    NarrativeCandidate,
    NarrativeRetrainHook,
    QueueItem,
    RetrainDecision,
    ReviewerRole,
    ReviewKind,
    ReviewLog,
    ReviewSession,
    borderline_queue,
    capture_review,
    classification_ambiguity,
    evaluate_retraining,
    maybe_kickoff_narrative_retrain,
    narrative_disagreement,
    retraining_trigger,
)
from moltrace.regulatory.ai.finetune import (
    FROZEN_DECISION_TYPES,
    NARRATIVE_DECISION_TYPES,
    FineTuneError,
    FineTuneRun,
    FineTuneUnavailable,
    FoldMetrics,
    FoldTrainer,
    LoRAConfig,
    NarrativeExample,
    NarrativeOnlyError,
    Snapshot,
    build_snapshot,
    finetune_narrative,
    mask_identifiers,
    narrative_promotion_gate,
    register_narrative_adapter,
)
from moltrace.regulatory.ai.rag_reasoner import (
    Confidence,
    GroundedAnswer,
    Passage,
    answer_with_citations,
    reason,
    retrieve,
    router_backend,
)
from moltrace.regulatory.ai.registry import (
    AppendOnlyViolation,
    ArtifactKind,
    ArtifactStatus,
    InvalidStatusTransition,
    Registry,
    RegistryEntry,
    RegistryError,
    StatusTransition,
    build_registry_entry,
    default_regulatory_registry,
)
from moltrace.regulatory.ai.router import (
    Citation,
    RegulatoryTask,
    RoutedResult,
    Router,
    RoutingError,
    TaskKind,
    deterministic_operations,
)

__all__ = [
    "AppendOnlyViolation",
    "ArtifactKind",
    "ArtifactStatus",
    "Citation",
    "ClassificationCandidate",
    "Confidence",
    "FROZEN_DECISION_TYPES",
    "FineTuneError",
    "FineTuneRun",
    "FineTuneUnavailable",
    "FoldMetrics",
    "FoldTrainer",
    "GroundedAnswer",
    "NARRATIVE_DECISION_TYPES",
    "InvalidStatusTransition",
    "LabeledExample",
    "LoRAConfig",
    "NarrativeCandidate",
    "NarrativeExample",
    "NarrativeOnlyError",
    "NarrativeRetrainHook",
    "Passage",
    "QueueItem",
    "Registry",
    "RegistryEntry",
    "RegistryError",
    "RegulatoryTask",
    "RetrainDecision",
    "ReviewKind",
    "ReviewLog",
    "ReviewSession",
    "ReviewerRole",
    "RoutedResult",
    "Router",
    "RoutingError",
    "Snapshot",
    "StatusTransition",
    "TaskKind",
    "answer_with_citations",
    "borderline_queue",
    "build_registry_entry",
    "build_snapshot",
    "capture_review",
    "classification_ambiguity",
    "default_regulatory_registry",
    "deterministic_operations",
    "evaluate_retraining",
    "finetune_narrative",
    "mask_identifiers",
    "maybe_kickoff_narrative_retrain",
    "narrative_disagreement",
    "narrative_promotion_gate",
    "reason",
    "register_narrative_adapter",
    "retraining_trigger",
    "retrieve",
    "router_backend",
]
