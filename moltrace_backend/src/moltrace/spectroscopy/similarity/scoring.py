"""Vector + set similarity for NMR spectrum retrieval (Prompt 8).

Two complementary similarity measures over ¹H / ¹³C chemical shifts, consuming
either predicted shifts (``predict_shifts`` / ``ShiftPrediction`` from Prompt 6)
or experimental peak lists:

1. **Gaussian-smoothed vector encoding + L2 retrieval.** Each spectrum is
   encoded as a fixed-length vector by placing a Gaussian bump at every shift
   and sampling on a uniform ppm grid; the ¹H and ¹³C halves are concatenated
   into a 256-D vector. Nearest neighbours are found by L2 (Euclidean) distance,
   indexed with FAISS HNSW for million-scale retrieval.
2. **Kuhn-Munkres set similarity.** A peak-to-peak optimal bipartite matching
   (``scipy.optimize.linear_sum_assignment``) that is robust to peak
   insertion/deletion and to shift noise — slower than the vector measure but
   used to re-rank a vector-retrieved shortlist.

Methodology & citation
======================
The Gaussian-smoothed encoding and the Kuhn-Munkres set-similarity score follow
the retrieval approach of **NMR-Solver** — Y. Jin, J.-J. Wang, F. Xu, X. Ji,
Z. Gao, L. Zhang, G. Ke, R. Zhu, W. E, *"NMR-Solver: Automated Structure
Elucidation via Large-Scale Spectral Matching and Physics-Guided Fragment
Optimization"*, arXiv:2509.00640 (2025); Nat. Commun. The functions here are
implemented **from the published equations** (reproduced in the docstrings),
not from any copyrighted text.

Datasets & licensing
====================
* **NMRShiftDB2** (~45k molecules; CC BY-SA): a FAISS index or embedding table
  *derived* from NMRShiftDB2 is a CC-BY-SA derivative and carries the
  **ShareAlike** obligation — see ``NOTICE``. Such artifacts are gitignored and
  never committed; build them locally with ``scripts/build_similarity_index.py``.
* **SimNMR-PubChem** (106M molecules; Hugging Face ``yqj01/SimNMR-PubChem``):
  released under the **MIT license**, which permits commercial indexing — but
  re-confirm the dataset card at ship time before distributing a derived index.

Performance target: < 1 s top-100 retrieval from the ~45k NMRShiftDB2 corpus
(FAISS HNSW); scales to the 106M SimNMR-PubChem index.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy.optimize import linear_sum_assignment

if TYPE_CHECKING:  # pragma: no cover - typing only
    from moltrace.spectroscopy.predict.nmrnet_wrapper import ShiftPrediction

# --------------------------------------------------------------------------- #
# Encoding constants
# --------------------------------------------------------------------------- #
_DEFAULT_SIGMA = 0.05
_DEFAULT_N_POINTS = 128

#: Default ppm grid bounds per nucleus (the bulk of organic ¹H / ¹³C shifts).
RANGE_1H: tuple[float, float] = (0.0, 12.0)
RANGE_13C: tuple[float, float] = (0.0, 220.0)

#: Dimension of :func:`encode_spectrum` output at the default ``n_points`` (2×128).
ENCODING_DIM = 2 * _DEFAULT_N_POINTS


# --------------------------------------------------------------------------- #
# Gaussian-smoothed vector encoding
# --------------------------------------------------------------------------- #
def gaussian_smooth_encode(
    shifts: Sequence[float],
    range_ppm: tuple[float, float],
    sigma: float = _DEFAULT_SIGMA,
    n_points: int = _DEFAULT_N_POINTS,
) -> np.ndarray:
    """Encode a list of chemical shifts as a Gaussian-smoothed intensity profile.

    Implements ``g(t) = Σ_i exp(-(t - x_i)² / (2σ²))`` discretised over
    ``n_points`` uniformly-spaced grid points ``t`` in ``range_ppm``. Shifts
    outside the range still contribute their Gaussian tail. Non-finite shifts are
    dropped; an empty list yields an all-zero vector.

    Returns a ``float32`` array of length ``n_points`` (FAISS-ready).
    """

    if sigma <= 0:
        raise ValueError("sigma must be positive")
    if n_points < 1:
        raise ValueError("n_points must be >= 1")
    lo, hi = float(range_ppm[0]), float(range_ppm[1])
    if not hi > lo:
        raise ValueError("range_ppm must have hi > lo")

    grid = np.linspace(lo, hi, n_points)
    arr = np.asarray(list(shifts), dtype=np.float64)
    arr = arr[np.isfinite(arr)] if arr.size else arr
    if arr.size == 0:
        return np.zeros(n_points, dtype=np.float32)

    diff = grid[:, None] - arr[None, :]  # (n_points, k)
    profile = np.exp(-(diff * diff) / (2.0 * sigma * sigma)).sum(axis=1)
    return profile.astype(np.float32)


def encode_spectrum(
    shifts_1h: Sequence[float],
    shifts_13c: Sequence[float],
    sigma: float = _DEFAULT_SIGMA,
    n_points: int = _DEFAULT_N_POINTS,
    range_1h: tuple[float, float] = RANGE_1H,
    range_13c: tuple[float, float] = RANGE_13C,
) -> np.ndarray:
    """Concatenated encoding ``[v_1H (n_points); v_13C (n_points)]``.

    With the default ``n_points=128`` this is a 256-D ``float32`` vector (the
    NMR-Solver encoding dimension). Either nucleus list may be empty (its half is
    then all zeros), so the encoding is well-defined for ¹H-only or ¹³C-only data.
    """

    v_1h = gaussian_smooth_encode(shifts_1h, range_1h, sigma, n_points)
    v_13c = gaussian_smooth_encode(shifts_13c, range_13c, sigma, n_points)
    return np.concatenate([v_1h, v_13c]).astype(np.float32)


def encode_prediction(
    prediction: ShiftPrediction,
    sigma: float = _DEFAULT_SIGMA,
    n_points: int = _DEFAULT_N_POINTS,
    range_1h: tuple[float, float] = RANGE_1H,
    range_13c: tuple[float, float] = RANGE_13C,
) -> np.ndarray:
    """Encode a ``ShiftPrediction`` (from ``predict_shifts``) into the 256-D vector.

    Splits the prediction's per-atom shifts by nucleus and forwards to
    :func:`encode_spectrum`. Duck-typed: any object exposing ``shifts`` whose
    items have ``nucleus`` and ``predicted_ppm`` works.
    """

    shifts_1h: list[float] = []
    shifts_13c: list[float] = []
    for shift in getattr(prediction, "shifts", []):
        if shift.nucleus == "1H":
            shifts_1h.append(shift.predicted_ppm)
        elif shift.nucleus == "13C":
            shifts_13c.append(shift.predicted_ppm)
    return encode_spectrum(
        shifts_1h, shifts_13c, sigma=sigma, n_points=n_points,
        range_1h=range_1h, range_13c=range_13c,
    )


# --------------------------------------------------------------------------- #
# Vector similarity (L2)
# --------------------------------------------------------------------------- #
def vector_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """L2 (Euclidean) distance between two encodings — **lower means more similar**.

    This is the metric the FAISS HNSW index (:class:`SpectrumIndex`) uses, so a
    brute-force ``vector_similarity`` agrees with an index lookup up to HNSW's
    approximation. Use :class:`SpectrumIndex` for million-scale retrieval.
    """

    a = np.asarray(v1, dtype=np.float64).ravel()
    b = np.asarray(v2, dtype=np.float64).ravel()
    if a.shape != b.shape:
        raise ValueError(f"encoding shape mismatch: {a.shape} vs {b.shape}")
    return float(np.linalg.norm(a - b))


# --------------------------------------------------------------------------- #
# Kuhn-Munkres set similarity
# --------------------------------------------------------------------------- #
def set_similarity_kuhn_munkres(
    X: Sequence[float], Y: Sequence[float], sigma: float = _DEFAULT_SIGMA
) -> float:
    """Optimal-bipartite-matching set similarity between two shift sets.

    Implements ``S(X, Y) = (1 / √(m·n)) · max_P Σ f(x_i, y_j)`` with
    ``f(x, y) = exp(-(x - y)² / (2σ²))`` and ``P`` an injective matching of the
    ``m`` elements of ``X`` to the ``n`` elements of ``Y`` (solved exactly by the
    Kuhn-Munkres / Hungarian algorithm via ``scipy.optimize.linear_sum_assignment``
    with ``maximize=True``). Because the matching is injective on the smaller set,
    the ``|m − n|`` surplus elements are simply **left unmatched** (contributing 0),
    making the score robust to peak insertion/deletion.

    Identical equal-size sets score 1.0; far-apart or disjoint sets score ≈ 0.
    Returns 0.0 if either set is empty. Non-finite values are dropped.
    """

    if sigma <= 0:
        raise ValueError("sigma must be positive")
    x = np.asarray(list(X), dtype=np.float64)
    y = np.asarray(list(Y), dtype=np.float64)
    x = x[np.isfinite(x)] if x.size else x
    y = y[np.isfinite(y)] if y.size else y
    m, n = int(x.size), int(y.size)
    if m == 0 or n == 0:
        return 0.0

    diff = x[:, None] - y[None, :]  # (m, n)
    affinity = np.exp(-(diff * diff) / (2.0 * sigma * sigma))  # f(x_i, y_j) ∈ (0, 1]
    row, col = linear_sum_assignment(affinity, maximize=True)
    matched = float(affinity[row, col].sum())
    return matched / math.sqrt(m * n)


# --------------------------------------------------------------------------- #
# Exact brute-force k-NN (validation / small corpora)
# --------------------------------------------------------------------------- #
def exact_knn(
    query: np.ndarray, matrix: np.ndarray, k: int
) -> list[tuple[int, float]]:
    """Exact L2 k-nearest-neighbours of ``query`` among the rows of ``matrix``.

    Returns ``[(row_index, distance), ...]`` ascending by distance. Used to
    validate the approximate FAISS HNSW recall and for corpora small enough that
    an exact scan is cheap.
    """

    q = np.asarray(query, dtype=np.float64).ravel()
    mat = np.asarray(matrix, dtype=np.float64)
    if mat.ndim != 2 or mat.shape[1] != q.size:
        raise ValueError(f"matrix shape {mat.shape} incompatible with query {q.shape}")
    dist = np.linalg.norm(mat - q[None, :], axis=1)
    k = max(1, min(int(k), dist.size))
    if k < dist.size:
        cand = np.argpartition(dist, k - 1)[:k]
    else:
        cand = np.arange(dist.size)
    order = cand[np.argsort(dist[cand])]
    return [(int(i), float(dist[i])) for i in order]


# --------------------------------------------------------------------------- #
# FAISS HNSW index for scale retrieval
# --------------------------------------------------------------------------- #
def _import_faiss():
    try:
        import faiss
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ImportError(
            "FAISS is required for SpectrumIndex; install faiss-cpu (or faiss-gpu)."
        ) from exc
    return faiss


class SpectrumIndex:
    """FAISS **HNSW** index over spectrum encodings for fast top-k L2 retrieval.

    Wraps ``faiss.IndexHNSWFlat`` (L2 metric, matching :func:`vector_similarity`)
    and keeps a parallel list of caller-supplied external ids (e.g. SMILES or
    database keys). HNSW gives **approximate** nearest neighbours; tune recall vs
    speed with ``ef_search``. Target: < 1 s top-100 from the ~45k NMRShiftDB2
    corpus; scales to the 106M SimNMR-PubChem index.

    Note: an index built from NMRShiftDB2 is a CC-BY-SA derivative (ShareAlike —
    see ``NOTICE``); persisted artifacts are gitignored.
    """

    def __init__(
        self,
        dim: int = ENCODING_DIM,
        hnsw_m: int = 32,
        ef_construction: int = 200,
        ef_search: int = 128,
    ) -> None:
        faiss = _import_faiss()
        self._faiss = faiss
        self.dim = int(dim)
        index = faiss.IndexHNSWFlat(self.dim, int(hnsw_m))  # METRIC_L2 by default
        index.hnsw.efConstruction = int(ef_construction)
        index.hnsw.efSearch = int(ef_search)
        self.index = index
        self.ids: list[Any] = []

    def __len__(self) -> int:
        return int(self.index.ntotal)

    @property
    def ef_search(self) -> int:
        return int(self.index.hnsw.efSearch)

    @ef_search.setter
    def ef_search(self, value: int) -> None:
        self.index.hnsw.efSearch = int(value)

    def add(self, vectors: np.ndarray, ids: Sequence[Any]) -> None:
        """Add encodings (one per id). ``vectors`` may be a single 1-D encoding."""
        vecs = np.ascontiguousarray(np.asarray(vectors, dtype=np.float32))
        if vecs.ndim == 1:
            vecs = vecs.reshape(1, -1)
        if vecs.shape[1] != self.dim:
            raise ValueError(f"expected dim {self.dim}, got {vecs.shape[1]}")
        id_list = list(ids)
        if len(id_list) != vecs.shape[0]:
            raise ValueError("number of ids must match number of vectors")
        self.index.add(vecs)
        self.ids.extend(id_list)

    def search(
        self, query: np.ndarray, k: int = 100
    ) -> list[tuple[Any, float]] | list[list[tuple[Any, float]]]:
        """Top-``k`` nearest ids by L2 distance.

        A 1-D ``query`` returns ``[(id, distance), ...]``; a 2-D batch returns one
        such list per row. Distances are L2 (lower = closer).
        """
        q = np.ascontiguousarray(np.asarray(query, dtype=np.float32))
        single = q.ndim == 1
        if single:
            q = q.reshape(1, -1)
        if q.shape[1] != self.dim:
            raise ValueError(f"expected dim {self.dim}, got {q.shape[1]}")
        if len(self) == 0:
            return [] if single else [[] for _ in range(q.shape[0])]
        k = max(1, min(int(k), len(self)))
        distances, indices = self.index.search(q, k)
        results: list[list[tuple[Any, float]]] = []
        for row_idx, row_dist in zip(indices, distances, strict=True):
            results.append(
                [
                    (self.ids[i], float(d))
                    for i, d in zip(row_idx, row_dist, strict=True)
                    if i != -1
                ]
            )
        return results[0] if single else results

    def save(self, path: str) -> None:
        """Persist the FAISS index (``path``) + the id sidecar (``path + '.ids.json'``)."""
        import json

        path = str(path)
        self._faiss.write_index(self.index, path)
        with open(path + ".ids.json", "w", encoding="utf-8") as handle:
            json.dump({"dim": self.dim, "ids": self.ids}, handle)

    @classmethod
    def load(cls, path: str) -> SpectrumIndex:
        """Load an index previously written by :meth:`save`."""
        import json

        faiss = _import_faiss()
        path = str(path)
        index = faiss.read_index(path)
        with open(path + ".ids.json", encoding="utf-8") as handle:
            meta = json.load(handle)
        obj = cls(dim=int(meta["dim"]))
        obj.index = index
        obj.ids = list(meta["ids"])
        return obj
