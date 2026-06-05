"""Vector + set similarity for NMR spectrum retrieval (Prompt 8).

Gaussian-smoothed spectral encoding, L2 vector similarity (FAISS HNSW for
scale), and a Kuhn-Munkres set-similarity score — following the NMR-Solver
retrieval methodology (Jin et al., arXiv:2509.00640, 2025). See
:mod:`moltrace.spectroscopy.similarity.scoring`.
"""

from moltrace.spectroscopy.similarity.scoring import (
    ENCODING_DIM,
    RANGE_1H,
    RANGE_13C,
    SpectrumIndex,
    encode_prediction,
    encode_spectrum,
    exact_knn,
    gaussian_smooth_encode,
    set_similarity_kuhn_munkres,
    vector_similarity,
)

__all__ = [
    "ENCODING_DIM",
    "RANGE_1H",
    "RANGE_13C",
    "SpectrumIndex",
    "encode_prediction",
    "encode_spectrum",
    "exact_knn",
    "gaussian_smooth_encode",
    "set_similarity_kuhn_munkres",
    "vector_similarity",
]
