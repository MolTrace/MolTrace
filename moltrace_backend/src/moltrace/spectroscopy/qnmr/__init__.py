"""Quantitative-NMR (qNMR) purity determination (Prompt 9).

Internal-standard and PULCON purity calculators plus a multiplet-selection
helper, each fully auditable.  See
:mod:`moltrace.spectroscopy.qnmr.purity` for the literature grounding and the
transparent formulas.
"""

from moltrace.spectroscopy.qnmr.purity import (
    PurityResult,
    calculate_purity_internal_standard,
    calculate_purity_pulcon,
    molar_mass_from_smiles,
    rank_multiplets_for_qnmr,
    total_proton_count_from_smiles,
)

__all__ = [
    "PurityResult",
    "calculate_purity_internal_standard",
    "calculate_purity_pulcon",
    "molar_mass_from_smiles",
    "rank_multiplets_for_qnmr",
    "total_proton_count_from_smiles",
]
