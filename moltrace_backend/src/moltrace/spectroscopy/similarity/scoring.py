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

#: Encoding contract version. Bump on ANY change to sigma, ranges, n_points or
#: normalization — the geometry of every persisted index depends on them, and the
#: dimension alone cannot detect a change (see :meth:`SpectrumIndex.save`).
ENCODER_VERSION = 2

#: Per-nucleus Gaussian widths, in ppm, chosen from the expected shift ERROR —
#: **not** from the grid step (tying sigma to the step measurably degrades recall
#: as ``n_points`` grows). The two optima differ ~20×, so a single shared sigma
#: cannot serve both nuclei: at the pre-v2 shared 0.05, a ¹³C Gaussian is ~35×
#: narrower than the ¹³C grid step of 220/127 = 1.732 ppm, so peaks land between
#: grid nodes and alias away — measured on this repo's corpus, only 6.4 % of 1048
#: real ¹³C peaks retained >0.5 amplitude and ¹³C contributed 4.1 % of squared
#: distance. At 0.30/2.00 retention is 100 % and the ¹³C share is 56.4 %.
DEFAULT_SIGMA_1H = 0.30
DEFAULT_SIGMA_13C = 2.00

#: Default ppm grid bounds per nucleus (the bulk of organic ¹H / ¹³C shifts).
RANGE_1H: tuple[float, float] = (0.0, 12.0)
RANGE_13C: tuple[float, float] = (0.0, 220.0)

#: Dimension of :func:`encode_spectrum` output at the default ``n_points`` (2×128).
ENCODING_DIM = 2 * _DEFAULT_N_POINTS

#: Length of one nucleus half of an encoding. ``vec[:HALF_DIM]`` is ¹H,
#: ``vec[HALF_DIM:]`` is ¹³C.
HALF_DIM = _DEFAULT_N_POINTS

#: Weight of the coverage penalty in :class:`MultiNucleusSpectrumIndex` ranking —
#: added per *query* nucleus that a candidate does not carry. Chosen by measurement
#: on the 42 449-molecule NMRShiftDB2 corpus, not by intuition; see that class's
#: docstring for the sweep. λ=0.20 is the knee: it restores full-vector precision on
#: both-nuclei queries (99.7 % recall@1, matching a 256-D index exactly) while still
#: reaching single-nucleus references (90.7 % @1 / 99.7 % @10, which routing serves
#: at 0 %). λ=0 costs 6.4 points on the common case; λ=0.5 costs 15 points on the
#: single-nucleus case.
FUSED_COVERAGE_PENALTY = 0.20

#: Nucleus keys used by the per-nucleus sub-indices, in encoding order.
NUCLEI: tuple[str, str] = ("1h", "13c")


def nuclei_present(vector: np.ndarray, half_dim: int | None = None) -> tuple[str, ...]:
    """Which nuclei an encoding actually carries.

    :func:`encode_spectrum` L2-normalizes each half that has peaks and leaves an
    absent nucleus as exact zeros, so a nonzero half *is* the presence signal. This
    is what lets a query be routed and scored by the nuclei it really measured
    rather than by the fixed 256-D shape it is padded into.

    ``half_dim`` defaults to half the vector's own length rather than to the module
    constant, so a non-default ``n_points`` encoding is split where its halves
    actually meet. Reading a fixed 128 would mis-slice such a vector and report the
    wrong nucleus — a 64-bin ¹³C-only encoding came back as ``('1h',)``.
    """

    vec = np.asarray(vector)
    width = int(half_dim) if half_dim is not None else vec.shape[-1] // 2
    return tuple(
        name
        for name, half in zip(NUCLEI, (vec[..., :width], vec[..., width:]), strict=True)
        if bool(np.any(half))
    )


def current_encoder_meta() -> dict[str, Any]:
    """The encoding contract this module currently produces.

    Persisted alongside an index by :meth:`SpectrumIndex.save` and compared on load.
    """

    return {
        "encoder_version": ENCODER_VERSION,
        "sigma_1h": DEFAULT_SIGMA_1H,
        "sigma_13c": DEFAULT_SIGMA_13C,
        "n_points": _DEFAULT_N_POINTS,
        "range_1h": list(RANGE_1H),
        "range_13c": list(RANGE_13C),
        "normalize": "per_half_l2",
    }


def _warn_on_encoder_mismatch(recorded: dict[str, Any] | None, path: str) -> None:
    """Warn when a persisted index's encoding contract differs from the live one."""

    import warnings

    if recorded is None:
        warnings.warn(
            f"similarity index {path!r} carries no encoder metadata, so it predates "
            f"encoder v{ENCODER_VERSION} (shared sigma, unnormalized halves). Its "
            f"geometry does not match the current query encoder and retrieval quality "
            f"is unreliable — rebuild it with scripts/build_similarity_index.py.",
            RuntimeWarning,
            stacklevel=3,
        )
        return
    live = current_encoder_meta()
    differing: list[str] = []
    for key, want in live.items():
        got = recorded.get(key)
        # Ranges round-trip through JSON as lists, so compare both as lists.
        if isinstance(want, list):
            got = list(got) if isinstance(got, (list, tuple)) else got
        if got != want:
            differing.append(key)
    if differing:
        warnings.warn(
            f"similarity index {path!r} was built with a different encoding contract "
            f"(differing: {', '.join(differing)}). Distances are not comparable to "
            f"freshly-encoded queries — rebuild the index.",
            RuntimeWarning,
            stacklevel=3,
        )


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
    sigma: float | None = None,
    n_points: int = _DEFAULT_N_POINTS,
    range_1h: tuple[float, float] = RANGE_1H,
    range_13c: tuple[float, float] = RANGE_13C,
    *,
    sigma_1h: float = DEFAULT_SIGMA_1H,
    sigma_13c: float = DEFAULT_SIGMA_13C,
    normalize: bool = True,
) -> np.ndarray:
    """Concatenated encoding ``[v_1H (n_points); v_13C (n_points)]``.

    With the default ``n_points=128`` this is a 256-D ``float32`` vector (the
    NMR-Solver encoding dimension). Either nucleus list may be empty (its half is
    then all zeros), so the encoding is well-defined for ¹H-only or ¹³C-only data.

    Each nucleus is smoothed with its own width (``sigma_1h`` / ``sigma_13c``) and,
    when ``normalize`` is set, each half is **L2-normalized independently before
    concatenation**. Normalization is what makes the resulting distance a measure of
    chemistry rather than of peak count: unnormalized, a vector's magnitude grows
    with the number of peaks, so L2 ranks by spectrum size. Measured on this repo's
    68 both-nuclei molecules (2278 pairs, Morgan r=2/2048): Spearman(L2, 1−Tanimoto)
    rises +0.087 → +0.594 while the peak-count confound Spearman(L2, |Δpeak count|)
    falls +0.585 → −0.051, and distance becomes bounded on [0, 2] (was [1.6, 15.6]),
    which is what lets a similarity threshold exist at all. Per-half rather than
    global normalization keeps the two nuclei contributing comparably regardless of
    how many peaks each carries.

    ``sigma`` is the pre-v2 shared-width escape hatch: when given it overrides
    **both** nuclei (and so reproduces the aliasing described at
    :data:`DEFAULT_SIGMA_13C`). Prefer the per-nucleus arguments.

    An encoding is only comparable to others built with the same parameters — see
    :data:`ENCODER_VERSION` and :meth:`SpectrumIndex.save`.
    """

    s_1h = sigma_1h if sigma is None else sigma
    s_13c = sigma_13c if sigma is None else sigma
    v_1h = gaussian_smooth_encode(shifts_1h, range_1h, s_1h, n_points)
    v_13c = gaussian_smooth_encode(shifts_13c, range_13c, s_13c, n_points)
    if normalize:
        for half in (v_1h, v_13c):
            norm = float(np.linalg.norm(half))
            if norm > 0.0:
                half /= norm
    return np.concatenate([v_1h, v_13c]).astype(np.float32)


def encode_prediction(
    prediction: ShiftPrediction,
    sigma: float | None = None,
    n_points: int = _DEFAULT_N_POINTS,
    range_1h: tuple[float, float] = RANGE_1H,
    range_13c: tuple[float, float] = RANGE_13C,
    *,
    sigma_1h: float = DEFAULT_SIGMA_1H,
    sigma_13c: float = DEFAULT_SIGMA_13C,
    normalize: bool = True,
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
        sigma_1h=sigma_1h, sigma_13c=sigma_13c, normalize=normalize,
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

    .. warning::
       ``sigma`` is **nucleus-specific and the default is not suitable for ¹³C.**
       This function compares one set of shifts and cannot know which nucleus it
       holds, so it keeps the legacy shared 0.05 — appropriate for ¹H at best. Pass
       :data:`DEFAULT_SIGMA_1H` / :data:`DEFAULT_SIGMA_13C` (or a noise-matched
       value) explicitly. Using this as a re-ranking stage at the default width was
       measured to be a severe regression rather than an improvement.
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
        #: Encoding contract recorded in a loaded index's sidecar (``None`` for a
        #: freshly-constructed index or a pre-v2 sidecar). See :meth:`load`.
        self.encoder_meta: dict[str, Any] | None = None

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
        such list per row. Distances are **true** L2 (lower = closer).

        FAISS ``METRIC_L2`` reports *squared* L2, so the raw values are square-rooted
        here. Without that, this method disagreed with :func:`exact_knn` and
        :func:`vector_similarity` — which both return true L2 — by a square, and the
        endpoint surfaced the squared number under the field name ``l2_distance``.
        Ranking is unaffected (√ is monotonic on non-negatives) but the magnitudes
        were not comparable across code paths, and the [0, 2] bound that per-half
        normalization buys applies to true L2 only.
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
                    (self.ids[i], math.sqrt(max(0.0, float(d))))
                    for i, d in zip(row_idx, row_dist, strict=True)
                    if i != -1
                ]
            )
        return results[0] if single else results

    def save(self, path: str, encoder: dict[str, Any] | None = None) -> None:
        """Persist the FAISS index (``path``) + the id sidecar (``path + '.ids.json'``).

        The sidecar also records the **encoding contract** the vectors were built
        with, so a later load can detect that the live encoder no longer matches.
        This is not cosmetic: the dimension is unchanged by a sigma or normalization
        change, so every dimension guard in this module still passes and a stale
        index reads back as valid while its geometry no longer matches the query
        encoder — measured on this repo's corpus, a silent recall@1 collapse from
        100 % to 10.3 % with no exception raised anywhere.

        ``encoder`` defaults to this module's current parameters, which assumes the
        vectors were encoded with them (true for every in-repo caller, none of which
        overrides sigma). Pass it explicitly when building with custom parameters.
        """
        import json

        path = str(path)
        self._faiss.write_index(self.index, path)
        with open(path + ".ids.json", "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "dim": self.dim,
                    "ids": self.ids,
                    "encoder": encoder if encoder is not None else current_encoder_meta(),
                },
                handle,
            )

    @classmethod
    def load(cls, path: str) -> SpectrumIndex:
        """Load an index previously written by :meth:`save`.

        Warns (never raises) when the sidecar's encoding contract does not match the
        live encoder, including a pre-v2 sidecar that records none at all. Loading
        deliberately still succeeds: this is called from the request path without a
        guard (``nmrcheck.api._load_similarity_index``), so raising would turn a
        stale index into a 500 instead of a degraded-but-serving surface. The
        recorded contract is kept on ``encoder_meta`` for callers to surface.
        """
        import json

        faiss = _import_faiss()
        path = str(path)
        index = faiss.read_index(path)
        with open(path + ".ids.json", encoding="utf-8") as handle:
            meta = json.load(handle)
        obj = cls(dim=int(meta["dim"]))
        obj.index = index
        obj.ids = list(meta["ids"])
        obj.encoder_meta = meta.get("encoder")
        _warn_on_encoder_mismatch(obj.encoder_meta, path)
        return obj


#: Marker written into a :class:`MultiNucleusSpectrumIndex` manifest so
#: :func:`load_index` can tell the two artifact layouts apart.
_MULTI_NUCLEUS_KIND = "multi_nucleus_v1"


class MultiNucleusSpectrumIndex:
    """Per-nucleus sub-indices, ranked by coverage-penalised mean nucleus distance.

    Why this exists
    ===============
    A single index over the concatenated 256-D encoding is only sound when every
    molecule carries every nucleus. Real reference data does not: of the 42 449
    molecules in the full NMRShiftDB2 export, **82.2 % carry one nucleus only**
    (59.7 % ¹³C-only, 22.6 % ¹H-only). Because :func:`encode_spectrum` leaves an
    absent nucleus as exact zeros, those zero halves match *each other* perfectly,
    and a missing half costs a candidate the half's full unit norm. Measured on
    that corpus, a single 256-D index is catastrophic in **both** directions:

    ==================================  ===============  ===============
    scenario                            one 256-D index  this class
    ==================================  ===============  ===============
    ¹³C-only query → both-nuclei ref     0.0 % @1/@10     99.0 % @1
    both-nuclei query → ¹³C-only ref     4.3 % @1         90.7 % @1
    ==================================  ===============  ===============

    In the first row 100 % of a ¹³C-only query's top-10 were zero-¹H entries against
    a 59.7 % base rate — the zero halves act as a magnet no chemical agreement can
    overcome.

    How it ranks
    ============
    Each nucleus gets its own ``half_dim``-D HNSW sub-index holding every molecule
    that actually carries it, so no zero half is ever indexed. A query is scored
    against a candidate on the nuclei the two **share**::

        score = mean(L2 per shared nucleus) + λ · (query nuclei the candidate lacks)
                                                  ────────────────────────────────
                                                        query nuclei

    The mean alone is not enough: averaging over fewer nuclei has lower variance, so
    single-nucleus candidates crowd out both-nuclei ones — the mirror of the bug
    being fixed, measured as 93.3 % vs 99.7 % recall@1 on both-nuclei queries. The
    coverage penalty restores that precision without making missing data
    unreachable. λ was swept on the real corpus (recall@1, both-nuclei query /
    ¹³C-only reference): 0.0 → 93.3/94.0, 0.05 → 98.3/94.0, **0.20 → 99.7/90.7**,
    0.35 → 99.7/86.3, 0.50 → 99.7/75.7. λ=0.20 is the knee and is
    :data:`FUSED_COVERAGE_PENALTY`.

    Two rejected alternatives, both measured rather than argued away:

    * **Routing** the query to the sub-index matching its own nuclei scores 99.7 %
      on both-nuclei queries but **0 % @1 and @10** for a both-nuclei query whose
      reference carries one nucleus — a structural blind spot over 82 % of the
      corpus that no choice of ``k`` can fix.
    * **Reciprocal-rank fusion** across sub-indices also scores **0 %** there: a
      both-nuclei candidate collects a contribution from every list it appears in
      while a single-nucleus one collects from a single list, so RRF reproduces the
      coverage bias it was meant to remove.

    Distances returned by :meth:`search` are therefore that fused score — a mean of
    **true** (not squared) per-nucleus L2 distances plus the penalty, lower = closer,
    bounded on **[0, √2 + λ]**. It is not the L2 norm of the 256-D difference; for a
    both-nuclei query matched to a both-nuclei candidate it equals that norm's
    per-nucleus mean. The √2 is not 2 because an encoded half is non-negative
    (a sum of Gaussians), so two unit halves can be at most orthogonal, never
    antipodal — measured at 1.414214 for disjoint halves.

    A consequence worth naming: for a candidate that shares only some of the query's
    nuclei, part of the score is the penalty rather than measured disagreement, and
    in the limit (identical on the shared nucleus, missing the other) it is *entirely*
    penalty — 0.1 at λ=0.20 with one of two nuclei absent. Use
    :meth:`search_with_coverage` when the caller needs to tell that apart from 0.1
    worth of real disagreement across both nuclei; the two carry different evidential
    weight and the bare number cannot distinguish them.

    Known characteristic: ¹H-only entries are over-represented below rank 1
    ==================================================================
    For a both-nuclei query the correct answer comes back at rank 1 in 99.7–100 % of
    cases, but the remaining slots skew: measured over 300 real queries, the top-10
    ran 68.7 % ¹H-only against a 22.6 % base rate (3.0×), with ¹³C-only entries at
    5.1 % against 59.7 % (0.09×).

    The cause is **variance, not scale**. A candidate sharing one nucleus is scored on
    a single distance while a both-nuclei candidate is scored on the *average* of two,
    and averaging shrinks the lower tail, so single-nucleus candidates reach extreme
    low scores more easily. ¹H dominates ¹³C within that effect because ¹H is the less
    discriminative nucleus here — σ/range is 0.30/12 = 0.025 against 0.0091 for ¹³C,
    so arbitrary ¹H halves overlap more and the lower tail of ``d_1h`` is fatter.

    A per-nucleus scale calibration was tried and **refuted**: the two typical corpus
    distances are 1.174 (¹H) and 1.222 (¹³C), a ratio of 1.04, so there is no scale
    gap to correct — dividing by them left the composition essentially unchanged and
    cost 8 points on the single-nucleus-reference case. No fix is applied because no
    measured objective is harmed: every scenario in the table above is at or above
    99 % @1 except the demoted-reference case at 92.8 % @1 / 100 % @10. Anyone
    revisiting this should weight the nuclei in the mean rather than rescale them,
    and must re-sweep λ if they do.
    """

    def __init__(
        self,
        half_dim: int = HALF_DIM,
        hnsw_m: int = 32,
        ef_construction: int = 200,
        ef_search: int = 128,
        coverage_penalty: float = FUSED_COVERAGE_PENALTY,
    ) -> None:
        faiss = _import_faiss()
        self._faiss = faiss
        self.half_dim = int(half_dim)
        self.dim = 2 * self.half_dim
        self.coverage_penalty = float(coverage_penalty)
        self.ids: list[Any] = []
        self._sub: dict[str, Any] = {}
        #: nucleus -> global row for each row of that sub-index
        self._rows: dict[str, list[int]] = {}
        #: nucleus -> {global row: sub-index row}, the inverse of ``_rows``
        self._pos: dict[str, dict[int, int]] = {}
        for nucleus in NUCLEI:
            index = faiss.IndexHNSWFlat(self.half_dim, int(hnsw_m))
            index.hnsw.efConstruction = int(ef_construction)
            index.hnsw.efSearch = int(ef_search)
            self._sub[nucleus] = index
            self._rows[nucleus] = []
            self._pos[nucleus] = {}
        self.encoder_meta: dict[str, Any] | None = None

    def __len__(self) -> int:
        """Number of molecules, not of indexed vectors (a molecule may hold two)."""

        return len(self.ids)

    @property
    def ef_search(self) -> int:
        return int(self._sub[NUCLEI[0]].hnsw.efSearch)

    @ef_search.setter
    def ef_search(self, value: int) -> None:
        for index in self._sub.values():
            index.hnsw.efSearch = int(value)

    def nucleus_size(self, nucleus: str) -> int:
        """How many molecules carry ``nucleus``."""

        return int(self._sub[nucleus].ntotal)

    def add(self, vectors: np.ndarray, ids: Sequence[Any]) -> None:
        """Add full ``dim``-D encodings; each half is routed to its own sub-index.

        A half of exact zeros means "this nucleus was not measured" and is **not**
        indexed — that omission is the entire point, since indexing zero halves is
        what makes them a retrieval magnet.
        """

        vecs = np.ascontiguousarray(np.asarray(vectors, dtype=np.float32))
        if vecs.ndim == 1:
            vecs = vecs.reshape(1, -1)
        if vecs.shape[1] != self.dim:
            raise ValueError(f"expected dim {self.dim}, got {vecs.shape[1]}")
        id_list = list(ids)
        if len(id_list) != vecs.shape[0]:
            raise ValueError("number of ids must match number of vectors")

        base = len(self.ids)
        self.ids.extend(id_list)
        halves = {"1h": vecs[:, : self.half_dim], "13c": vecs[:, self.half_dim :]}
        for nucleus, block in halves.items():
            keep = np.flatnonzero(np.any(block != 0.0, axis=1))
            if keep.size == 0:
                continue
            self._sub[nucleus].add(np.ascontiguousarray(block[keep]))
            for offset in keep.tolist():
                global_row = base + offset
                self._pos[nucleus][global_row] = len(self._rows[nucleus])
                self._rows[nucleus].append(global_row)

    def _nucleus_distance(self, nucleus: str, global_row: int, half: np.ndarray) -> float:
        """Exact true-L2 distance for a candidate the sub-index search did not return.

        ``reconstruct`` is an O(1) read out of HNSW's flat storage, so this keeps the
        full vectors out of process memory — which is what allows the same layout to
        scale past the point where holding them would not fit.
        """

        sub_row = self._pos[nucleus][global_row]
        stored = self._sub[nucleus].reconstruct(int(sub_row))
        return float(np.linalg.norm(np.asarray(stored, dtype=np.float32) - half))

    def _search_one(
        self, query: np.ndarray, k: int, pool: int
    ) -> list[tuple[Any, float, tuple[str, ...], tuple[str, ...]]]:
        present = nuclei_present(query, self.half_dim)
        if not present or len(self.ids) == 0:
            return []
        halves = {"1h": query[: self.half_dim], "13c": query[self.half_dim :]}

        # 1. Coarse candidates from each sub-index the query can actually address.
        distances: dict[int, dict[str, float]] = {}
        for nucleus in present:
            index = self._sub[nucleus]
            if index.ntotal == 0:
                continue
            half = np.ascontiguousarray(halves[nucleus].reshape(1, -1), dtype=np.float32)
            take = max(1, min(pool, int(index.ntotal)))
            sub_d, sub_i = index.search(half, take)
            for sub_row, sq in zip(sub_i[0], sub_d[0], strict=True):
                if sub_row == -1:
                    continue
                global_row = self._rows[nucleus][int(sub_row)]
                distances.setdefault(global_row, {})[nucleus] = math.sqrt(
                    max(0.0, float(sq))
                )

        # 2. Complete each candidate: a molecule surfaced by one nucleus may also
        #    carry the other, and scoring it on only the nucleus that found it would
        #    reintroduce exactly the coverage bias this class exists to remove.
        scored: list[tuple[float, Any, tuple[str, ...], tuple[str, ...]]] = []
        for global_row, known in distances.items():
            total = 0.0
            compared: list[str] = []
            absent: list[str] = []
            for nucleus in present:
                if global_row in self._pos[nucleus]:
                    value = known.get(nucleus)
                    if value is None:
                        value = self._nucleus_distance(
                            nucleus, global_row, halves[nucleus]
                        )
                    total += value
                    compared.append(nucleus)
                else:
                    absent.append(nucleus)
            if not compared:  # pragma: no cover - a candidate always shares its finder
                continue
            score = total / len(compared) + self.coverage_penalty * (
                len(absent) / len(present)
            )
            scored.append((score, self.ids[global_row], tuple(compared), tuple(absent)))

        scored.sort(key=lambda item: item[0])
        return [
            (identifier, float(score), compared, absent)
            for score, identifier, compared, absent in scored[:k]
        ]

    def _search_rows(
        self, query: np.ndarray, k: int, candidate_pool: int | None
    ) -> tuple[list[list[tuple[Any, float, tuple[str, ...], tuple[str, ...]]]], bool]:
        q = np.ascontiguousarray(np.asarray(query, dtype=np.float32))
        single = q.ndim == 1
        if single:
            q = q.reshape(1, -1)
        if q.shape[1] != self.dim:
            raise ValueError(f"expected dim {self.dim}, got {q.shape[1]}")
        k = max(1, int(k))
        pool = int(candidate_pool) if candidate_pool else max(200, 10 * k)
        return [self._search_one(row, k, pool) for row in q], single

    def search(
        self, query: np.ndarray, k: int = 100, candidate_pool: int | None = None
    ) -> list[tuple[Any, float]] | list[list[tuple[Any, float]]]:
        """Top-``k`` ids by fused per-nucleus distance (see the class docstring).

        Returns ``(id, score)`` pairs, matching :meth:`SpectrumIndex.search` so the
        two index layouts are interchangeable at the call site. Use
        :meth:`search_with_coverage` to also learn which nuclei each score was
        computed over.

        ``candidate_pool`` is how many coarse neighbours to pull from each
        sub-index before the exact fused re-scoring; it defaults to ``10 × k``
        (floor 200). Raising it costs recall nothing and latency a little — the
        re-scoring is exact on whatever set it receives, so the pool only bounds
        which molecules get considered at all.
        """

        rows, single = self._search_rows(query, k, candidate_pool)
        trimmed = [[(identifier, score) for identifier, score, _, _ in row] for row in rows]
        return trimmed[0] if single else trimmed

    def search_with_coverage(
        self, query: np.ndarray, k: int = 100, candidate_pool: int | None = None
    ) -> (
        list[tuple[Any, float, tuple[str, ...], tuple[str, ...]]]
        | list[list[tuple[Any, float, tuple[str, ...], tuple[str, ...]]]]
    ):
        """Like :meth:`search`, but also reports the coverage behind each score.

        Yields ``(id, score, nuclei_compared, nuclei_absent)``. Without this, a score
        is ambiguous in a way that matters for how much weight a reviewer should give
        it: 0.1 can mean "a little disagreement measured across both nuclei" or
        "perfect agreement on the only nucleus this reference has, and the other was
        never measured". Those are different strengths of evidence, and a regulated
        read-out should be able to say which one it is.
        """

        rows, single = self._search_rows(query, k, candidate_pool)
        return rows[0] if single else rows

    def save(self, path: str, encoder: dict[str, Any] | None = None) -> None:
        """Write a JSON manifest at ``path`` plus one FAISS file per nucleus.

        The manifest — not a FAISS blob — sits at ``path`` so that the artifact is
        self-describing and :func:`load_index` can pick the right reader by looking
        at the file. Sub-index filenames are stored as basenames, so the directory
        can be moved or copied without rewriting the manifest.
        """

        import json
        import os

        path = str(path)
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        written: dict[str, str] = {}
        for nucleus, index in self._sub.items():
            if index.ntotal == 0:
                continue
            sub_path = f"{path}.{nucleus}"
            self._faiss.write_index(index, sub_path)
            written[nucleus] = os.path.basename(sub_path)
        payload = {
            "kind": _MULTI_NUCLEUS_KIND,
            "half_dim": self.half_dim,
            "coverage_penalty": self.coverage_penalty,
            "ids": self.ids,
            "rows": {nucleus: self._rows[nucleus] for nucleus in NUCLEI},
            "sub_indexes": written,
            "encoder": encoder if encoder is not None else current_encoder_meta(),
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    @classmethod
    def load(cls, path: str) -> MultiNucleusSpectrumIndex:
        """Load an artifact written by :meth:`save`.

        Warns rather than raises on an encoder-contract mismatch, for the same reason
        :meth:`SpectrumIndex.load` does: the request path calls this without a guard,
        so raising would turn a stale index into a 500 instead of a degraded surface.
        """

        import json
        import os

        faiss = _import_faiss()
        path = str(path)
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("kind") != _MULTI_NUCLEUS_KIND:
            raise ValueError(f"{path!r} is not a {_MULTI_NUCLEUS_KIND} manifest")

        obj = cls(
            half_dim=int(payload["half_dim"]),
            coverage_penalty=float(
                payload.get("coverage_penalty", FUSED_COVERAGE_PENALTY)
            ),
        )
        obj.ids = list(payload["ids"])
        directory = os.path.dirname(os.path.abspath(path))
        for nucleus in NUCLEI:
            rows = [int(r) for r in payload.get("rows", {}).get(nucleus, [])]
            obj._rows[nucleus] = rows
            obj._pos[nucleus] = {row: i for i, row in enumerate(rows)}
            name = payload.get("sub_indexes", {}).get(nucleus)
            if name:
                obj._sub[nucleus] = faiss.read_index(os.path.join(directory, name))
        obj.encoder_meta = payload.get("encoder")
        _warn_on_encoder_mismatch(obj.encoder_meta, path)
        return obj


def load_index(path: str) -> SpectrumIndex | MultiNucleusSpectrumIndex:
    """Load whichever index layout ``path`` holds.

    A :class:`MultiNucleusSpectrumIndex` manifest is JSON; a :class:`SpectrumIndex`
    is a raw FAISS blob whose first bytes are a binary magic. Detecting from the file
    rather than from a caller-supplied flag means an existing deployment keeps
    working after an upgrade without touching its configuration, and a rebuilt
    artifact is picked up on its own.

    The probe reads a few leading bytes rather than parsing the file: handing a
    multi-gigabyte FAISS blob to ``json.load`` allocated ~3× its size and left the
    whole thing alive inside the exception (``UnicodeDecodeError.object`` retains the
    decoded bytes) while the real reader ran. The first non-UTF-8 byte of a FAISS
    index is at offset 4, so a short read decides it.
    """

    import json

    with open(path, "rb") as probe:
        head = probe.read(64).lstrip()
    if not head.startswith(b"{"):
        return SpectrumIndex.load(path)
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (UnicodeDecodeError, ValueError):
        return SpectrumIndex.load(path)
    if isinstance(payload, dict) and payload.get("kind") == _MULTI_NUCLEUS_KIND:
        return MultiNucleusSpectrumIndex.load(path)
    return SpectrumIndex.load(path)
