"""CTD (Common Technical Document) Module 3 generators (Prompt 8).

:mod:`module3_generator` assembles ICH M4Q(R1) Module-3 quality narratives from the validated
deterministic impurity engines (ICH Q3A/B, M7, FDA CPCA) plus batch data:

* :func:`generate_3p5_impurities` — CTD 3.2.P.5.5 (Characterisation of Impurities) and 3.2.P.5.6
  (Justification of Specifications) for a drug product.
* :func:`generate_3s3_impurities_drug_substance` — CTD 3.2.S.3.2 (Impurities) for a drug substance.

Every number and threshold carries a source reference back to the engine output or batch entry that
produced it (the traceability requirement). Output is a structured :class:`CTDSection` that renders
to Markdown or to a **draft** Word ``.docx`` with tracked changes enabled. Generated sections are
DRAFTS for qualified regulatory-affairs review and QA sign-off — never final filing content.
"""

from __future__ import annotations

from moltrace.regulatory.ctd.module3_generator import (
    CTD_DRAFT_DISCLAIMER,
    CTDSection,
    CTDSubsection,
    CTDTable,
    ImpurityEntry,
    ImpurityOrigin,
    ImpurityProfile,
    SourceKind,
    SourceRef,
    generate_3p5_impurities,
    generate_3s3_impurities_drug_substance,
)

__all__ = [
    "CTD_DRAFT_DISCLAIMER",
    "CTDSection",
    "CTDSubsection",
    "CTDTable",
    "ImpurityEntry",
    "ImpurityOrigin",
    "ImpurityProfile",
    "SourceKind",
    "SourceRef",
    "generate_3p5_impurities",
    "generate_3s3_impurities_drug_substance",
]
