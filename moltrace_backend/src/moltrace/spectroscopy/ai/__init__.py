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
* :mod:`.rag` -- retrieval-augmented reasoning (Prompt 14): Anthropic Claude
  wrapped in a retrieval layer over the Prompt 8 similarity index. Candidate
  structures are grounded in retrieved precedent (cite-or-drop hallucination
  guard) and arbitrated by the Prompt 7 verifier — the LLM proposes, the
  verifier decides; full prompt/completion/retrieval is captured for the Prompt
  12 audit trail.
"""

from __future__ import annotations

from moltrace.spectroscopy.ai.finetune import (
    FinalAdapter,
    FineTuneError,
    FineTuneRun,
    FineTuneUnavailable,
    FoldMetrics,
    FoldResult,
    FoldTrainer,
    LoRAConfig,
    Snapshot,
    TrainingExample,
    adapter_cache_dir,
    build_training_snapshot,
    finetune_lora,
    register_if_eligible,
)
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
from moltrace.spectroscopy.ai.rag import (
    Candidate,
    ProposalResult,
    RAGAudit,
    RAGContext,
    RAGError,
    RAGLLMUnavailable,
    RAGSchemaError,
    RetrievedAnalogue,
    build_reasoning_context,
    propose_structures,
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
    "Candidate",
    "CandidatePosterior",
    "FinalAdapter",
    "FineTuneError",
    "FineTuneRun",
    "FineTuneUnavailable",
    "FingerIDResult",
    "FoldMetrics",
    "FoldResult",
    "FoldTrainer",
    "InMemoryRegistryStore",
    "InferenceRouter",
    "InvalidStatusTransition",
    "Layer",
    "LoRAConfig",
    "MSCandidate",
    "MSMSSpectrum",
    "MSModelsError",
    "ModelEntry",
    "ModelLineage",
    "ModelRegistry",
    "ModelRole",
    "ModelStatus",
    "NMRCandidate",
    "ProposalResult",
    "RAGAudit",
    "RAGContext",
    "RAGError",
    "RAGLLMUnavailable",
    "RAGSchemaError",
    "RankedCandidate",
    "RegistryError",
    "RegistryStore",
    "RetrievedAnalogue",
    "RoutedAtomPrediction",
    "RoutedPrediction",
    "Snapshot",
    "SqlAlchemyRegistryStore",
    "StatusTransition",
    "TrainingDataLineage",
    "TrainingExample",
    "adapter_cache_dir",
    "arbitrate",
    "build_model_entry",
    "build_reasoning_context",
    "build_training_snapshot",
    "dp4_candidate_posterior",
    "finetune_lora",
    "fuse_candidates",
    "predict_msms_candidates",
    "predict_retention_times",
    "propose_structures",
    "register_if_eligible",
    "register_ms_models",
    "rt_corroboration",
]
