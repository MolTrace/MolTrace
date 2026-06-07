"""Public scientific-datasets pipeline (Prompt 20).

:mod:`.datasets_pipeline` ingests the canonical public datasets (NMRShiftDB2,
HMDB, BMRB, MassBank EU, GNPS, METLIN, QM9-NMR, 2DNMRGym; SDBS internal-only)
into a licence-aware, deduplicated, validated corpus with frozen, seeded
train/val/test splits whose **test** set is a checksummed, hash-excluded holdout.
"""

from __future__ import annotations

from moltrace.spectroscopy.data.datasets_pipeline import (
    SOURCES,
    CorpusBuild,
    DatasetsPipelineError,
    HoldoutLeakageError,
    Licence,
    LicenceViolationError,
    Modality,
    Normalized,
    NormalizedRecord,
    ProvenanceKind,
    QuarantineItem,
    RawDataset,
    RawRecord,
    SourceSpec,
    Splits,
    UpstreamChangedError,
    ValidationOutcome,
    assert_training_excludes_holdout,
    build_corpus,
    enforce_licences,
    freeze_splits,
    ingest,
    matchms_available,
    normalize,
    validate,
    version_splits,
)

__all__ = [
    "SOURCES",
    "CorpusBuild",
    "DatasetsPipelineError",
    "HoldoutLeakageError",
    "Licence",
    "LicenceViolationError",
    "Modality",
    "Normalized",
    "NormalizedRecord",
    "ProvenanceKind",
    "QuarantineItem",
    "RawDataset",
    "RawRecord",
    "SourceSpec",
    "Splits",
    "UpstreamChangedError",
    "ValidationOutcome",
    "assert_training_excludes_holdout",
    "build_corpus",
    "enforce_licences",
    "freeze_splits",
    "ingest",
    "matchms_available",
    "normalize",
    "validate",
    "version_splits",
]
