"""Regulatory corpus data foundation (Prompt 20, Roadmap Phase 3).

:mod:`corpus_pipeline` is a versioned, licence-aware, effective-date-tracked ingestion pipeline for
the regulatory-guidance corpus that backs the Prompt 14 RAG layer. Per-source adapters (FDA, ICH,
EMA, FDA NDSRI) record revision / effective date / licence / content hash; ``index`` keeps
source + section + effective date + url on every chunk for exact citation; ``validate`` gates the
corpus (reusing the Prompt 19 validators); and ``revision_watch`` flags a new upstream revision by
opening a change-control item + a re-validation task and *holding* the changed revision out of
answers until the deterministic rule-set (Prompt 13) is updated and revalidated. ICH/EMA content is
licence-flagged internal-only and never redistributed.
"""

from __future__ import annotations

from moltrace.regulatory.data.corpus_pipeline import (
    ChangeControlItem,
    CorpusLicense,
    CorpusSource,
    EmaGuidanceAdapter,
    FdaGuidanceAdapter,
    FdaNdsriAdapter,
    IchGuidelineAdapter,
    IndexChunk,
    LicenseError,
    RawDoc,
    RawDocs,
    RevalidationTask,
    RevisionAlert,
    SourceAdapter,
    VersionPin,
    WhoTechnicalReportAdapter,
    guard_redistribution,
    index,
    ingest,
    revision_watch,
    validate,
)

__all__ = [
    "ChangeControlItem",
    "CorpusLicense",
    "CorpusSource",
    "EmaGuidanceAdapter",
    "FdaGuidanceAdapter",
    "FdaNdsriAdapter",
    "IchGuidelineAdapter",
    "IndexChunk",
    "LicenseError",
    "RawDoc",
    "RawDocs",
    "RevalidationTask",
    "RevisionAlert",
    "SourceAdapter",
    "VersionPin",
    "WhoTechnicalReportAdapter",
    "guard_redistribution",
    "index",
    "ingest",
    "revision_watch",
    "validate",
]
