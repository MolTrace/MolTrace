"""Vector + set similarity for NMR spectrum retrieval (Prompt 8).

Gaussian-smoothed spectral encoding, L2 vector similarity (FAISS HNSW for
scale), and a Kuhn-Munkres set-similarity score — following the NMR-Solver
retrieval methodology (Jin et al., arXiv:2509.00640, 2025). See
:mod:`moltrace.spectroscopy.similarity.scoring`.
"""

from moltrace.spectroscopy.similarity.scoring import (
    COVERAGE_PENALTY_BY_ABSENT_NUCLEUS,
    ENCODING_DIM,
    HALF_DIM,
    NUCLEI,
    RANGE_1H,
    RANGE_13C,
    MultiNucleusSpectrumIndex,
    SpectrumIndex,
    encode_prediction,
    encode_spectrum,
    exact_knn,
    gaussian_smooth_encode,
    load_index,
    nuclei_present,
    set_similarity_kuhn_munkres,
    vector_similarity,
)

#: Largest value :meth:`MultiNucleusSpectrumIndex.search` can return: two unit halves
#: are at worst orthogonal (√2, not 2 — an encoded half is non-negative), plus the
#: heaviest coverage penalty. Re-exported for callers that need to interpret an
#: ``l2_distance`` against a per-nucleus index.
FUSED_SCORE_MAX = 2.0**0.5 + max(COVERAGE_PENALTY_BY_ABSENT_NUCLEUS.values())

__all__ = [
    "COVERAGE_PENALTY_BY_ABSENT_NUCLEUS",
    "ENCODING_DIM",
    "FUSED_SCORE_MAX",
    "HALF_DIM",
    "NUCLEI",
    "RANGE_1H",
    "RANGE_13C",
    "MultiNucleusSpectrumIndex",
    "SpectrumIndex",
    "encode_prediction",
    "encode_spectrum",
    "exact_knn",
    "gaussian_smooth_encode",
    "load_index",
    "nuclei_present",
    "set_similarity_kuhn_munkres",
    "vector_similarity",
]
