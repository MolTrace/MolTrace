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
* :mod:`.ms_models` -- the MS / structure pretrained layer (Prompt 21):
  CSI:FingerID (MS/MS -> structure), METLIN retention-time corroboration, and
  DP4-AI candidate ranking (reusing the in-house ``dp4_scoring``), fused into one
  calibrated candidate ranking that the Prompt 7 verifier arbitrates.
"""

from __future__ import annotations

from moltrace.spectroscopy.ai.ms_models import (
    CandidatePosterior,
    CSIFingerIDUnavailable,
    FingerIDResult,
    MSCandidate,
    MSModelsError,
    MSMSSpectrum,
    NMRCandidate,
    RankedCandidate,
    arbitrate,
    dp4_candidate_posterior,
    fuse_candidates,
    predict_msms_candidates,
    predict_retention_times,
    register_ms_models,
    rt_corroboration,
)
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
    "CSIFingerIDUnavailable",
    "CandidatePosterior",
    "FingerIDResult",
    "InMemoryRegistryStore",
    "InferenceRouter",
    "InvalidStatusTransition",
    "Layer",
    "MSCandidate",
    "MSMSSpectrum",
    "MSModelsError",
    "ModelEntry",
    "ModelLineage",
    "ModelRegistry",
    "ModelRole",
    "ModelStatus",
    "NMRCandidate",
    "RankedCandidate",
    "RegistryError",
    "RegistryStore",
    "RoutedAtomPrediction",
    "RoutedPrediction",
    "SqlAlchemyRegistryStore",
    "StatusTransition",
    "TrainingDataLineage",
    "arbitrate",
    "build_model_entry",
    "dp4_candidate_posterior",
    "fuse_candidates",
    "predict_msms_candidates",
    "predict_retention_times",
    "register_ms_models",
    "rt_corroboration",
]
