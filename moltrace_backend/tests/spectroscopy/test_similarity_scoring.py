"""Tests for the spectrum-similarity scoring + retrieval module (Prompt 8)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from moltrace.spectroscopy.predict.nmrnet_wrapper import AtomShift, ShiftPrediction
from moltrace.spectroscopy.similarity.scoring import (
    ENCODING_DIM,
    RANGE_1H,
    SpectrumIndex,
    encode_prediction,
    encode_spectrum,
    exact_knn,
    gaussian_smooth_encode,
    set_similarity_kuhn_munkres,
    vector_similarity,
)


# --------------------------------------------------------------------------- #
# gaussian_smooth_encode
# --------------------------------------------------------------------------- #
def test_gaussian_encode_shape_dtype():
    v = gaussian_smooth_encode([5.0], RANGE_1H, sigma=0.05, n_points=128)
    assert v.shape == (128,)
    assert v.dtype == np.float32


def test_gaussian_encode_peaks_at_shift():
    shift = 6.0
    v = gaussian_smooth_encode([shift], RANGE_1H, sigma=0.05, n_points=128)
    grid = np.linspace(RANGE_1H[0], RANGE_1H[1], 128)
    peak_ppm = grid[int(v.argmax())]
    step = (RANGE_1H[1] - RANGE_1H[0]) / 127
    assert abs(peak_ppm - shift) <= step


def test_gaussian_encode_empty_is_zero():
    v = gaussian_smooth_encode([], RANGE_1H)
    assert v.shape == (128,)
    assert not v.any()


def test_gaussian_encode_drops_nonfinite():
    a = gaussian_smooth_encode([3.0, float("nan"), float("inf")], RANGE_1H)
    b = gaussian_smooth_encode([3.0], RANGE_1H)
    np.testing.assert_array_equal(a, b)


def test_gaussian_encode_wider_sigma_more_mass():
    narrow = gaussian_smooth_encode([6.0], RANGE_1H, sigma=0.05).sum()
    wide = gaussian_smooth_encode([6.0], RANGE_1H, sigma=0.30).sum()
    assert wide > narrow


def test_gaussian_encode_two_shifts_two_bumps():
    v = gaussian_smooth_encode([2.0, 9.0], RANGE_1H, sigma=0.05, n_points=128)
    # two local maxima above a small threshold
    assert (v > 0.5).sum() >= 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sigma": 0.0},
        {"sigma": -1.0},
        {"n_points": 0},
    ],
)
def test_gaussian_encode_validates(kwargs):
    with pytest.raises(ValueError):
        gaussian_smooth_encode([1.0], RANGE_1H, **kwargs)


def test_gaussian_encode_bad_range_raises():
    with pytest.raises(ValueError):
        gaussian_smooth_encode([1.0], (5.0, 5.0))


# --------------------------------------------------------------------------- #
# encode_spectrum / encode_prediction
# --------------------------------------------------------------------------- #
def test_encode_spectrum_is_256d():
    v = encode_spectrum([7.26, 3.5], [128.0, 55.0])
    assert v.shape == (ENCODING_DIM,)
    assert v.dtype == np.float32


def test_encode_spectrum_halves_independent():
    v = encode_spectrum([7.26], [])  # 1H-only -> 13C half all zeros
    assert v[:128].any()
    assert not v[128:].any()


def test_encode_prediction_matches_encode_spectrum():
    pred = ShiftPrediction(
        smiles="X",
        method="nmrnet",
        device="cpu",
        n_conformers=8,
        warnings=[],
        shifts=[
            AtomShift(0, "H", "1H", 7.26, 0.05),
            AtomShift(1, "H", "1H", 3.50, 0.05),
            AtomShift(2, "C", "13C", 128.4, 1.0),
        ],
    )
    np.testing.assert_array_equal(
        encode_prediction(pred), encode_spectrum([7.26, 3.50], [128.4])
    )


# --------------------------------------------------------------------------- #
# vector_similarity
# --------------------------------------------------------------------------- #
def test_vector_similarity_identical_is_zero():
    v = encode_spectrum([7.26], [128.0])
    assert vector_similarity(v, v) == 0.0


def test_vector_similarity_known_distance():
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([3.0, 4.0, 0.0])
    assert vector_similarity(a, b) == pytest.approx(5.0)


def test_vector_similarity_shape_mismatch_raises():
    with pytest.raises(ValueError):
        vector_similarity(np.zeros(3), np.zeros(4))


# --------------------------------------------------------------------------- #
# set_similarity_kuhn_munkres
# --------------------------------------------------------------------------- #
def test_set_similarity_identical_is_one():
    assert set_similarity_kuhn_munkres([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_set_similarity_disjoint_is_near_zero():
    assert set_similarity_kuhn_munkres([1.0, 2.0], [100.0, 200.0], sigma=0.05) < 1e-6


def test_set_similarity_empty_is_zero():
    assert set_similarity_kuhn_munkres([], [1.0, 2.0]) == 0.0
    assert set_similarity_kuhn_munkres([1.0], []) == 0.0


def test_set_similarity_robust_to_insertion():
    # adding two far-away peaks to Y leaves the 3 real matches intact (unmatched allowed)
    s = set_similarity_kuhn_munkres([1.0, 2.0, 3.0], [1.0, 2.0, 3.0, 50.0, 60.0])
    # 3 perfect matches, normalised by sqrt(3*5): 3/sqrt(15)
    assert s == pytest.approx(3.0 / math.sqrt(15.0))


def test_set_similarity_is_symmetric():
    x = [1.0, 2.2, 3.4]
    y = [1.1, 2.0, 9.0]
    assert set_similarity_kuhn_munkres(x, y) == pytest.approx(set_similarity_kuhn_munkres(y, x))


def test_set_similarity_uses_optimal_not_greedy_matching():
    # X=[0, 0.05], Y=[0.05, 0.10], sigma=0.05.
    # Greedy-best-first grabs (0.05<->0.05, f=1) then (0<->0.10, f=e^-2) -> total 1.135.
    # Optimal Hungarian pairs (0<->0.05) + (0.05<->0.10), both f=e^-0.5 -> total 1.213.
    s = set_similarity_kuhn_munkres([0.0, 0.05], [0.05, 0.10], sigma=0.05)
    optimal = math.exp(-0.5)  # = 1.213 / sqrt(2*2)
    greedy = (1.0 + math.exp(-2.0)) / 2.0
    assert s == pytest.approx(optimal, abs=1e-4)
    assert s > greedy


def test_set_similarity_validates_sigma():
    with pytest.raises(ValueError):
        set_similarity_kuhn_munkres([1.0], [1.0], sigma=0.0)


# --------------------------------------------------------------------------- #
# exact_knn
# --------------------------------------------------------------------------- #
def test_exact_knn_sorted_and_correct():
    matrix = np.array([[0.0, 0.0], [10.0, 0.0], [1.0, 0.0]])
    hits = exact_knn(np.array([0.0, 0.0]), matrix, k=3)
    assert [i for i, _ in hits] == [0, 2, 1]  # ascending distance
    assert hits[0][1] == pytest.approx(0.0)


def test_exact_knn_clamps_k():
    matrix = np.zeros((2, 4))
    assert len(exact_knn(np.zeros(4), matrix, k=99)) == 2


# --------------------------------------------------------------------------- #
# SpectrumIndex (FAISS HNSW)
# --------------------------------------------------------------------------- #
def _random_vectors(n, dim=ENCODING_DIM, seed=0):
    return np.random.default_rng(seed).standard_normal((n, dim)).astype(np.float32)


def test_index_self_retrieval():
    vecs = _random_vectors(300)
    idx = SpectrumIndex(dim=ENCODING_DIM)
    idx.add(vecs, list(range(300)))
    assert len(idx) == 300
    hits = idx.search(vecs[42], k=5)
    assert hits[0][0] == 42
    assert hits[0][1] == pytest.approx(0.0, abs=1e-4)


def test_index_recall_vs_exact():
    vecs = _random_vectors(500, seed=1)
    idx = SpectrumIndex(dim=ENCODING_DIM)
    idx.add(vecs, list(range(500)))
    ann = {i for i, _ in idx.search(vecs[7], k=10)}
    exact = {i for i, _ in exact_knn(vecs[7], vecs, 10)}
    assert len(ann & exact) >= 9  # HNSW recall@10 ~ 1.0 at this scale


def test_index_empty_search_returns_empty():
    idx = SpectrumIndex(dim=ENCODING_DIM)
    assert idx.search(np.zeros(ENCODING_DIM, dtype=np.float32), k=5) == []


def test_index_dim_mismatch_raises():
    idx = SpectrumIndex(dim=ENCODING_DIM)
    with pytest.raises(ValueError):
        idx.add(np.zeros((1, 8), dtype=np.float32), ["x"])


def test_index_id_count_mismatch_raises():
    idx = SpectrumIndex(dim=ENCODING_DIM)
    with pytest.raises(ValueError):
        idx.add(_random_vectors(3), ["only-one-id"])


def test_index_save_load_roundtrip(tmp_path):
    vecs = _random_vectors(200, seed=2)
    ids = [f"mol-{i}" for i in range(200)]
    idx = SpectrumIndex(dim=ENCODING_DIM)
    idx.add(vecs, ids)
    path = tmp_path / "spectra.faiss"
    idx.save(str(path))

    loaded = SpectrumIndex.load(str(path))
    assert len(loaded) == 200
    hits = loaded.search(vecs[5], k=3)
    assert hits[0][0] == "mol-5"


def test_index_batch_search():
    vecs = _random_vectors(100, seed=3)
    idx = SpectrumIndex(dim=ENCODING_DIM)
    idx.add(vecs, list(range(100)))
    results = idx.search(vecs[:4], k=5)
    assert isinstance(results, list) and len(results) == 4
    assert all(r[0][0] == i for i, r in enumerate(results))


@pytest.mark.slow
def test_index_retrieval_under_1s_at_45k():
    """Acceptance target: < 1 s top-100 retrieval from the ~45k NMRShiftDB2 scale."""
    import time

    vecs = _random_vectors(45_000, seed=4)
    idx = SpectrumIndex(dim=ENCODING_DIM)
    idx.add(vecs, list(range(45_000)))
    t0 = time.perf_counter()
    hits = idx.search(vecs[12_345], k=100)
    elapsed = time.perf_counter() - t0
    assert hits[0][0] == 12_345
    assert len(hits) == 100
    assert elapsed < 1.0
