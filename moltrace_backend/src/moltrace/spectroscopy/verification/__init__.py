"""Multi-test automated structure verification (ASV) for MolTrace (Prompt 7).

Public surface::

    from moltrace.spectroscopy.verification import verify_structure

See :mod:`moltrace.spectroscopy.verification.scorer` for the literature
grounding, the transparent scoring model, and the individual tests.
"""

from moltrace.spectroscopy.verification.scorer import (
    AssignmentsTest,
    HSQC2DRangesTest,
    MSMoleculeMatchTest,
    PredictionBoundsTest,
    TestResult,
    VerificationOptions,
    VerificationResult,
    verify_structure,
)

__all__ = [
    "AssignmentsTest",
    "HSQC2DRangesTest",
    "MSMoleculeMatchTest",
    "PredictionBoundsTest",
    "TestResult",
    "VerificationOptions",
    "VerificationResult",
    "verify_structure",
]
