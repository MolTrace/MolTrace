"""ICH Q6A specification builder (Prompt 6).

Runs the ICH Q6A decision trees (substance profile + batch data + method validation) and returns
a complete draft specification table, consuming the deterministic P1-5 impurity engines (Q3A/B
thresholds + ICH M7 safety limits) for impurity rows. Every parameter carries a proposed limit,
a justification (regulatory basis + batch-data summary), and a method reference — decision support
that a qualified person reviews; never a final filing.
"""

from __future__ import annotations

from moltrace.regulatory.specifications.q6a_builder import (
    BatchResult,
    ImpurityObservation,
    MethodValidation,
    Specification,
    SpecificationParameter,
    SubstanceProfile,
    build_specification,
    process_capability_cpk,
)

__all__ = [
    "BatchResult",
    "ImpurityObservation",
    "MethodValidation",
    "Specification",
    "SpecificationParameter",
    "SubstanceProfile",
    "build_specification",
    "process_capability_cpk",
]
