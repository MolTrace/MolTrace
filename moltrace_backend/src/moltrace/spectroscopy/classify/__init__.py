"""Peak classification expert systems (solvent / impurity identity, Prompt 10).

This package holds MolTrace's source-of-truth classifiers for non-analyte
signals.  :mod:`~moltrace.spectroscopy.classify.solvent_impurity` ingests the
Fulmer et al. (Organometallics 29, 2176, 2010) residual-solvent and trace-
impurity reference tables and exposes :func:`detect_solvent` and
:func:`classify_peak`.
"""

from __future__ import annotations

from moltrace.spectroscopy.classify.solvent_impurity import (
    COMMON_IMPURITIES,
    DEUTERATED_SOLVENTS,
    SolventImpurityCategory,
    classify_peak,
    classify_peaks,
    detect_solvent,
)

__all__ = [
    "COMMON_IMPURITIES",
    "DEUTERATED_SOLVENTS",
    "SolventImpurityCategory",
    "classify_peak",
    "classify_peaks",
    "detect_solvent",
]
