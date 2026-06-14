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
"""

from __future__ import annotations

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
    "Confidence",
    "GroundedAnswer",
    "InvalidStatusTransition",
    "Passage",
    "Registry",
    "RegistryEntry",
    "RegistryError",
    "RegulatoryTask",
    "RoutedResult",
    "Router",
    "RoutingError",
    "StatusTransition",
    "TaskKind",
    "answer_with_citations",
    "build_registry_entry",
    "default_regulatory_registry",
    "deterministic_operations",
    "reason",
    "retrieve",
    "router_backend",
]
