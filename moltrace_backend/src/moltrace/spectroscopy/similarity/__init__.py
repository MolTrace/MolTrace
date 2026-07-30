"""Vector + set similarity for NMR spectrum retrieval (Prompt 8).

Gaussian-smoothed spectral encoding, L2 vector similarity (FAISS HNSW for
scale), and a Kuhn-Munkres set-similarity score — following the NMR-Solver
retrieval methodology (Jin et al., arXiv:2509.00640, 2025). See
:mod:`moltrace.spectroscopy.similarity.scoring`.
"""

from moltrace.spectroscopy.similarity.scoring import (
    ENCODING_DIM,
    FUSED_COVERAGE_PENALTY,
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

#: Documented in :class:`MultiNucleusSpectrumIndex`; re-exported for callers that
#: need to interpret an ``l2_distance`` against a per-nucleus index.
FUSED_SCORE_MAX = 2.0**0.5 + FUSED_COVERAGE_PENALTY

__all__ = [
    "ENCODING_DIM",
    "FUSED_COVERAGE_PENALTY",
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
