"""AI model registry + inference router (Prompt 13).

* :mod:`.registry` -- a versioned, append-only :class:`ModelRegistry` that tracks
  every artifact (NMRNet checkpoints, HOSE KB builds, LoRA adapters, embedding
  models) with semantic version, SHA-256, training-data lineage, metric snapshot,
  and lifecycle status, persisted via a pluggable store (in-memory or SQLAlchemy/
  PostgreSQL).
* :mod:`.router` -- an :class:`InferenceRouter` that composes the LoRA fine-tuned
  layer, the NMRNet pretrained layer, and the deterministic HOSE fallback, and
  emits a complete, deterministic ``model_versions`` provenance record for every
  prediction (the Prompt 12 audit handoff).
"""

from __future__ import annotations

from moltrace.spectroscopy.ai.registry import (
    AppendOnlyViolation,
    InMemoryRegistryStore,
    InvalidStatusTransition,
    ModelEntry,
    ModelLineage,
    ModelRegistry,
    ModelRole,
    ModelStatus,
    RegistryError,
    RegistryStore,
    SqlAlchemyRegistryStore,
    StatusTransition,
    TrainingDataLineage,
    build_model_entry,
)
from moltrace.spectroscopy.ai.router import (
    InferenceRouter,
    Layer,
    RoutedAtomPrediction,
    RoutedPrediction,
)

__all__ = [
    "AppendOnlyViolation",
    "InMemoryRegistryStore",
    "InferenceRouter",
    "InvalidStatusTransition",
    "Layer",
    "ModelEntry",
    "ModelLineage",
    "ModelRegistry",
    "ModelRole",
    "ModelStatus",
    "RegistryError",
    "RegistryStore",
    "RoutedAtomPrediction",
    "RoutedPrediction",
    "SqlAlchemyRegistryStore",
    "StatusTransition",
    "TrainingDataLineage",
    "build_model_entry",
]
