"""Deterministic-first regulatory model & rule registry + router (Prompt 13).

Regulatory math is NEVER produced by a stochastic model. :mod:`registry` versions
every artifact that can touch a regulatory output -- the deterministic rule-engines
(which ICH/FDA revision a formula set encodes) and the AI artifacts used only for
narrative / retrieval / triage -- and :mod:`router` enforces the routing rule:
anything quantitative or classification-based goes to the deterministic engine ONLY,
LLMs draft and retrieve. Every result carries the exact rule-set + model versions and
citations -- the provenance the Annex 22 audit wrapper (Prompt 12) records.
"""

from __future__ import annotations

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
    "InvalidStatusTransition",
    "Registry",
    "RegistryEntry",
    "RegistryError",
    "RegulatoryTask",
    "RoutedResult",
    "Router",
    "RoutingError",
    "StatusTransition",
    "TaskKind",
    "build_registry_entry",
    "default_regulatory_registry",
    "deterministic_operations",
]
