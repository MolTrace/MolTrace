"""Tests for the spectrum-similarity scoring + retrieval module (Prompt 8)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from moltrace.spectroscopy.predict.nmrnet_wrapper import AtomShift, ShiftPrediction
from moltrace.spectroscopy.similarity.scoring import (
    COVERAGE_PENALTY_BY_ABSENT_NUCLEUS,
    ENCODING_DIM,
    HALF_DIM,
    RANGE_1H,
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


# --------------------------------------------------------------------------- #
# Encoder v2: per-nucleus sigma, per-half normalization, contract versioning
# --------------------------------------------------------------------------- #
def test_encode_normalizes_each_half_independently():
    """Each nucleus half is unit-norm, so distance can't be driven by peak count."""
    v = encode_spectrum([1.0, 2.0, 3.0, 4.0], [20.0, 60.0])
    assert np.linalg.norm(v[:128]) == pytest.approx(1.0, abs=1e-5)
    assert np.linalg.norm(v[128:]) == pytest.approx(1.0, abs=1e-5)


def test_encode_absent_nucleus_half_stays_zero_not_nan():
    """Normalization must skip an empty half rather than divide by zero."""
    v = encode_spectrum([1.0, 2.0], [])
    assert np.isfinite(v).all()
    assert np.linalg.norm(v[:128]) == pytest.approx(1.0, abs=1e-5)
    assert not v[128:].any()


def test_encode_distance_is_bounded_by_two():
    """Two unit halves put every pairwise L2 in [0, 2] — what makes a threshold possible."""
    a = encode_spectrum([1.0], [20.0])
    b = encode_spectrum([9.0], [200.0])
    assert 0.0 <= vector_similarity(a, b) <= 2.0 + 1e-6


def test_encode_peak_count_does_not_dominate_distance():
    """Adding duplicate-region peaks must not move a spectrum as far as changing chemistry."""
    base = encode_spectrum([2.0, 2.1, 2.2], [40.0, 41.0])
    more_peaks = encode_spectrum([2.0, 2.1, 2.2, 2.05, 2.15], [40.0, 41.0, 40.5])
    different = encode_spectrum([7.5, 7.6, 7.7], [150.0, 151.0])
    assert vector_similarity(base, more_peaks) < vector_similarity(base, different)


def test_13c_peaks_survive_encoding():
    """Regression guard for the aliasing defect fixed in encoder v2.

    The pre-v2 shared sigma of 0.05 was ~35x narrower than the 13C grid step, so
    most 13C peaks landed between grid nodes and encoded to ~0 — 13C was silently
    dropped from every distance. Assert real 13C shifts still register.
    """
    for shift in (18.4, 55.7, 128.9, 171.2, 205.0):
        half = encode_spectrum([], [shift])[128:]
        assert half.max() > 0.5, f"13C peak at {shift} ppm aliased away"


def test_legacy_shared_sigma_escape_hatch_reproduces_old_geometry():
    """Passing `sigma` overrides both nuclei and disables normalization on request."""
    legacy = encode_spectrum([1.0], [100.0], sigma=0.05, normalize=False)
    assert np.linalg.norm(legacy[:128]) != pytest.approx(1.0, abs=1e-3)
    assert legacy[128:].max() < 0.5  # the aliasing this fix removes


def test_save_records_encoder_contract(tmp_path):
    import json

    from moltrace.spectroscopy.similarity.scoring import (
        ENCODER_VERSION,
        current_encoder_meta,
    )

    index = SpectrumIndex()
    index.add(encode_spectrum([1.0], [20.0]).reshape(1, -1), ["a"])
    path = tmp_path / "i.faiss"
    index.save(str(path))

    meta = json.loads((tmp_path / "i.faiss.ids.json").read_text())
    assert meta["encoder"] == current_encoder_meta()
    assert meta["encoder"]["encoder_version"] == ENCODER_VERSION
    assert meta["encoder"]["sigma_1h"] != meta["encoder"]["sigma_13c"]


def test_load_warns_but_does_not_raise_on_encoder_mismatch(tmp_path):
    """A stale index must degrade loudly, never raise.

    `nmrcheck.api._load_similarity_index` calls `load()` with no guard, so raising
    would turn a stale index into a 500 instead of a serving-but-warning surface.
    """
    import json

    index = SpectrumIndex()
    index.add(encode_spectrum([1.0], [20.0]).reshape(1, -1), ["a"])
    path = tmp_path / "i.faiss"
    index.save(str(path))

    sidecar = tmp_path / "i.faiss.ids.json"
    meta = json.loads(sidecar.read_text())
    meta["encoder"]["sigma_13c"] = 0.05
    sidecar.write_text(json.dumps(meta))

    with pytest.warns(RuntimeWarning, match="different encoding contract"):
        loaded = SpectrumIndex.load(str(path))
    assert len(loaded) == 1
    assert loaded.encoder_meta["sigma_13c"] == 0.05


def test_load_warns_on_pre_v2_sidecar_without_encoder_metadata(tmp_path):
    """The dimension is unchanged by a sigma change, so absence of metadata is the
    only signal that an index predates v2 — it must not pass silently."""
    import json

    index = SpectrumIndex()
    index.add(encode_spectrum([1.0], [20.0]).reshape(1, -1), ["a"])
    path = tmp_path / "i.faiss"
    index.save(str(path))

    sidecar = tmp_path / "i.faiss.ids.json"
    meta = json.loads(sidecar.read_text())
    del meta["encoder"]
    sidecar.write_text(json.dumps(meta))

    with pytest.warns(RuntimeWarning, match="no encoder metadata"):
        loaded = SpectrumIndex.load(str(path))
    assert len(loaded) == 1
    assert loaded.encoder_meta is None


def test_load_roundtrip_with_matching_contract_is_silent(tmp_path):
    import warnings

    index = SpectrumIndex()
    index.add(encode_spectrum([1.0], [20.0]).reshape(1, -1), ["a"])
    path = tmp_path / "i.faiss"
    index.save(str(path))

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        loaded = SpectrumIndex.load(str(path))
    assert loaded.encoder_meta is not None


def test_index_search_returns_true_l2_not_squared():
    """FAISS METRIC_L2 reports squared L2; the endpoint calls the field `l2_distance`.

    Before this was corrected, `SpectrumIndex.search` disagreed with `exact_knn` and
    `vector_similarity` — both of which return true L2 — by a square, so magnitudes
    were not comparable across code paths and the [0, 2] bound that per-half
    normalization buys did not describe what the API surfaced.
    """
    a = encode_spectrum([1.0, 3.0], [20.0, 60.0])
    b = encode_spectrum([1.2, 3.3], [22.0, 64.0])
    index = SpectrumIndex()
    index.add(b.reshape(1, -1), ["b"])

    got = index.search(a, k=1)[0][1]
    assert got == pytest.approx(float(np.linalg.norm(a - b)), rel=1e-5)
    assert got == pytest.approx(vector_similarity(a, b), rel=1e-5)
    assert got == pytest.approx(exact_knn(a, b.reshape(1, -1), k=1)[0][1], rel=1e-5)


# --------------------------------------------------------------------------- #
# nuclei_present
# --------------------------------------------------------------------------- #
def test_nuclei_present_reads_the_zero_half_as_absence():
    assert nuclei_present(encode_spectrum([1.0], [20.0])) == ("1h", "13c")
    assert nuclei_present(encode_spectrum([], [20.0])) == ("13c",)
    assert nuclei_present(encode_spectrum([1.0], [])) == ("1h",)
    assert nuclei_present(np.zeros(ENCODING_DIM, dtype=np.float32)) == ()


def test_nuclei_present_splits_a_non_default_grid_at_its_own_midpoint():
    """Reading the module constant instead of the vector's own width mis-sliced it.

    A 64-bin-per-nucleus encoding is 128-D, so slicing at the default 128 put the
    entire vector in the '1h' half: a 13C-only spectrum reported as ('1h',).
    """
    carbon_only = encode_spectrum([], [50.0, 120.0], n_points=64)
    assert len(carbon_only) == 128
    assert nuclei_present(carbon_only) == ("13c",)
    assert nuclei_present(encode_spectrum([2.0], [], n_points=64)) == ("1h",)
    # An explicit width still wins, for callers that know better than the length.
    assert nuclei_present(carbon_only, half_dim=128) == ("1h",)


# --------------------------------------------------------------------------- #
# MultiNucleusSpectrumIndex
# --------------------------------------------------------------------------- #
def _multi(entries):
    """Build a MultiNucleusSpectrumIndex from ``{id: (shifts_1h, shifts_13c)}``."""
    index = MultiNucleusSpectrumIndex()
    for identifier, (h, c) in entries.items():
        index.add(encode_spectrum(h, c).reshape(1, -1), [identifier])
    return index


def test_multi_index_does_not_index_absent_nuclei():
    index = _multi({
        "both": ([1.0], [20.0]),
        "c_only": ([], [60.0]),
        "h_only": ([3.0], []),
    })
    assert len(index) == 3  # molecules, not vectors
    assert index.nucleus_size("1h") == 2
    assert index.nucleus_size("13c") == 2


def test_single_nucleus_query_reaches_a_both_nuclei_reference():
    """THE regression guard for the zero-half retrieval cliff.

    Measured on the full 42,449-molecule NMRShiftDB2 export, a single concatenated
    256-D index answered this at **0.0 % recall@1 and 0.0 % @10**: a 13C-only query
    has a zero 1H half, every 13C-only reference also has one, and matching zeros
    cost nothing while a real 1H half costs its full unit norm. 100 % of such a
    query's top-10 were zero-1H entries against a 59.7 % base rate.

    Here the chemically correct answer carries BOTH nuclei and every distractor is
    13C-only, so the zero-half magnet and the right answer pull in opposite
    directions. The assertion below is the one that fails if the magnet returns.

    The distractors are offset by only 1-3 ppm of 13C because that is what makes the
    defect visible at toy scale: a missing 1H half costs exactly 1.000 of *squared*
    distance, so a distractor must sit within that budget to win. In the real corpus
    the 25,323 13C-only entries guarantee many such neighbours; here they are placed
    deliberately. Note how lopsided the outcome is — `worse_c_only_c` is a 26x worse
    carbon match than the correct answer (13C distance 0.928 vs 0.035) and the single
    concatenated index still ranks it higher, purely for carrying no protons.
    """
    entries = {
        "correct_both": ([1.0, 3.0], [20.0, 60.0]),
        "worse_c_only_a": ([], [21.1, 61.1]),
        "worse_c_only_b": ([], [22.1, 62.1]),
        "worse_c_only_c": ([], [23.1, 63.1]),
    }
    query = encode_spectrum([], [20.1, 60.1])  # 13C only, matching correct_both

    ranked = [i for i, _ in _multi(entries).search(query, k=4)]
    assert ranked[0] == "correct_both", f"zero-half magnet is back: {ranked}"

    # Document the defect this replaces: one concatenated index gets it wrong, and
    # ranks all three chemically-distant zero-1H entries above the right answer.
    flat = SpectrumIndex()
    for identifier, (h, c) in entries.items():
        flat.add(encode_spectrum(h, c).reshape(1, -1), [identifier])
    flat_ranked = [i for i, _ in flat.search(query, k=4)]
    assert flat_ranked[0] != "correct_both"
    assert flat_ranked.index("correct_both") == 3


def test_both_nuclei_query_still_prefers_the_both_nuclei_match():
    """The coverage penalty exists so the fix does not invert the bug.

    Scoring on shared nuclei alone means a candidate is judged on fewer dimensions
    when it carries fewer nuclei, which has lower variance and lets single-nucleus
    entries crowd out complete ones — measured as 93.3 % vs 99.7 % recall@1 on the
    real corpus. With the penalty, a complete match must win.
    """
    entries = {
        "complete": ([1.0, 3.0], [20.0, 60.0]),
        "c_only_same_carbon": ([], [20.0, 60.0]),
        "h_only_same_proton": ([1.0, 3.0], []),
    }
    query = encode_spectrum([1.02, 3.02], [20.2, 60.2])
    ranked = [i for i, _ in _multi(entries).search(query, k=3)]
    assert ranked[0] == "complete", ranked


def test_zero_coverage_penalty_lets_a_partial_match_win():
    """Pins *why* the coverage penalty is nonzero rather than a tunable nicety.

    With no penalty at all, a candidate matching one nucleus exactly outranks a
    complete candidate that is marginally off. The 1H-only reference used here is
    exact on protons and carries no carbon, so it is charged the heavier 0.50 (halved
    to 0.25 over two query nuclei) and must lose to the complete match at 0.0588.

    The mirror case is deliberately NOT symmetric: a 13C-only reference is charged
    only 0.10 (0.05 halved), so it legitimately CAN outrank a slightly-off complete
    match. That leniency is the point of the asymmetry — it is what makes the
    59.7% of references carrying carbon alone reachable at all — and is asserted in
    test_missing_13c_costs_more_than_missing_1h.
    """
    entries = {
        "complete": ([1.0, 3.0], [20.0, 60.0]),
        "h_only_exact": ([1.05, 3.05], []),
    }
    query = encode_spectrum([1.05, 3.05], [20.0, 60.0])

    lenient = MultiNucleusSpectrumIndex(coverage_penalty=0.0)
    strict = MultiNucleusSpectrumIndex()  # measured per-nucleus defaults
    for index in (lenient, strict):
        for identifier, (h, c) in entries.items():
            index.add(encode_spectrum(h, c).reshape(1, -1), [identifier])

    assert lenient.search(query, k=2)[0][0] == "h_only_exact"
    assert strict.search(query, k=2)[0][0] == "complete"


def test_candidate_is_scored_on_every_shared_nucleus_not_just_its_finder():
    """A molecule surfaced by one sub-index must still be judged on the other.

    Scoring a candidate only on the nucleus whose search returned it would rebuild
    the coverage bias inside the fused rule: `carbon_twin` wins the 13C sub-search
    outright, and if its badly-mismatched 1H were never consulted it would rank
    first despite being the worse chemical match.
    """
    entries = {
        "balanced": ([1.0, 3.0], [21.0, 61.0]),
        "carbon_twin": ([9.5, 9.9], [20.0, 60.0]),
    }
    query = encode_spectrum([1.0, 3.0], [20.0, 60.0])
    index = _multi(entries)

    # carbon_twin is the exact 13C match, so it does win the 13C sub-index alone.
    carbon_only = [i for i, _ in index.search(encode_spectrum([], [20.0, 60.0]), k=2)]
    assert carbon_only[0] == "carbon_twin"
    # ...but with both nuclei in the query its 1H mismatch must count against it.
    assert [i for i, _ in index.search(query, k=2)][0] == "balanced"


def test_search_of_an_all_zero_query_returns_nothing():
    """An encoding with no nuclei addresses no sub-index; it must not guess."""
    index = _multi({"a": ([1.0], [20.0])})
    assert index.search(np.zeros(ENCODING_DIM, dtype=np.float32), k=5) == []


def test_search_batch_returns_one_list_per_row():
    index = _multi({"a": ([1.0], [20.0]), "b": ([7.3], [130.0])})
    batch = np.stack([encode_spectrum([1.0], [20.0]), encode_spectrum([7.3], [130.0])])
    rows = index.search(batch, k=1)
    assert [row[0][0] for row in rows] == ["a", "b"]


def test_add_validates_dimension_and_id_count():
    index = MultiNucleusSpectrumIndex()
    with pytest.raises(ValueError, match="expected dim"):
        index.add(np.zeros((1, HALF_DIM), dtype=np.float32), ["a"])
    with pytest.raises(ValueError, match="ids must match"):
        index.add(encode_spectrum([1.0], [20.0]).reshape(1, -1), ["a", "b"])


def test_multi_index_roundtrip_is_identical_and_relocatable(tmp_path):
    """Sub-index filenames are basenames, so the artifact directory can be moved."""
    index = _multi({
        "both": ([1.0, 3.0], [20.0, 60.0]),
        "c_only": ([], [150.0]),
        "h_only": ([7.2], []),
    })
    query = encode_spectrum([], [20.1, 60.1])
    expected = index.search(query, k=3)

    home = tmp_path / "home"
    home.mkdir()
    index.save(str(home / "spectra.faiss"))
    assert {p.name for p in home.iterdir()} == {
        "spectra.faiss", "spectra.faiss.1h", "spectra.faiss.13c"
    }

    moved = tmp_path / "moved"
    home.rename(moved)
    reloaded = load_index(str(moved / "spectra.faiss"))
    assert isinstance(reloaded, MultiNucleusSpectrumIndex)
    assert len(reloaded) == 3
    assert reloaded.search(query, k=3) == expected


def test_load_index_dispatches_on_the_artifact_not_a_flag(tmp_path):
    """One env var points at either layout, so an upgrade needs no config change."""
    multi_path = tmp_path / "multi.faiss"
    _multi({"a": ([1.0], [20.0])}).save(str(multi_path))

    flat_path = tmp_path / "flat.faiss"
    flat = SpectrumIndex()
    flat.add(encode_spectrum([1.0], [20.0]).reshape(1, -1), ["a"])
    flat.save(str(flat_path))

    assert isinstance(load_index(str(multi_path)), MultiNucleusSpectrumIndex)
    assert isinstance(load_index(str(flat_path)), SpectrumIndex)


def test_multi_index_load_warns_but_does_not_raise_on_encoder_mismatch(tmp_path):
    """Same contract as SpectrumIndex.load: the request path has no try/except."""
    import json

    path = tmp_path / "spectra.faiss"
    _multi({"a": ([1.0], [20.0])}).save(str(path))

    payload = json.loads(path.read_text())
    payload["encoder"]["sigma_13c"] = 0.05
    path.write_text(json.dumps(payload))

    with pytest.warns(RuntimeWarning, match="different encoding contract"):
        loaded = MultiNucleusSpectrumIndex.load(str(path))
    assert len(loaded) == 1


def test_multi_index_load_rejects_a_foreign_manifest(tmp_path):
    import json

    path = tmp_path / "not-ours.json"
    path.write_text(json.dumps({"kind": "something-else"}))
    with pytest.raises(ValueError, match="not a multi_nucleus"):
        MultiNucleusSpectrumIndex.load(str(path))


def test_coverage_penalty_survives_the_roundtrip(tmp_path):
    """A non-default penalty is part of the artifact's ranking contract."""
    index = MultiNucleusSpectrumIndex(coverage_penalty=0.35)
    index.add(encode_spectrum([1.0], [20.0]).reshape(1, -1), ["a"])
    path = tmp_path / "spectra.faiss"
    index.save(str(path))
    assert load_index(str(path)).coverage_penalty == {"1h": 0.35, "13c": 0.35}


def test_search_with_coverage_distinguishes_penalty_from_disagreement():
    """A bare score cannot say how much evidence produced it; this can.

    `c_only` below is IDENTICAL to the query on 13C and carries no protons, so its
    whole reported distance is the coverage penalty — 0.20 x (1 of 2 nuclei) = 0.10 —
    with no measured disagreement in it at all. Without the coverage fields that is
    indistinguishable from 0.10 of real disagreement checked across both nuclei, and
    the two are not equally strong support for an identification.
    """
    index = _multi({
        "both": ([1.0, 3.0], [20.0, 60.0]),
        "c_only": ([], [20.0, 60.0]),
    })
    query = encode_spectrum([1.0, 3.0], [20.0, 60.0])

    detailed = {row[0]: row for row in index.search_with_coverage(query, k=2)}
    assert detailed["both"][1] == pytest.approx(0.0, abs=1e-5)
    assert detailed["both"][2] == ("1h", "13c")
    assert detailed["both"][3] == ()

    identifier, score, compared, absent = detailed["c_only"]
    assert score == pytest.approx(COVERAGE_PENALTY_BY_ABSENT_NUCLEUS["1h"] * 0.5)
    assert compared == ("13c",)
    assert absent == ("1h",)

    # search() stays a 2-tuple so the two index layouts are interchangeable.
    assert index.search(query, k=2)[0] == ("both", pytest.approx(0.0, abs=1e-5))


def test_missing_13c_costs_more_than_missing_1h():
    """The penalty is asymmetric because the nuclei are not equally diagnostic.

    13C spans 220 ppm with roughly one signal per distinct carbon, so a reference
    lacking it is much weaker corroboration than one lacking 1H. Charging both 0.20
    let 1H-only entries take 71.2% of a both-nuclei query's top-10 against a 22.6%
    base rate while 13C-only entries were all but excluded at 3.2% against 59.7%.
    """
    assert (
        COVERAGE_PENALTY_BY_ABSENT_NUCLEUS["13c"]
        > COVERAGE_PENALTY_BY_ABSENT_NUCLEUS["1h"]
    )

    # Two references, each perfect on the one nucleus it has, each missing the other.
    # Their scores must differ, and the 1H-only one must be the worse of the two.
    index = _multi({
        "c_only": ([], [20.0, 60.0]),
        "h_only": ([1.0, 3.0], []),
    })
    scores = dict(
        (row[0], row[1])
        for row in index.search_with_coverage(encode_spectrum([1.0, 3.0], [20.0, 60.0]), k=2)
    )
    assert scores["c_only"] == pytest.approx(
        COVERAGE_PENALTY_BY_ABSENT_NUCLEUS["1h"] / 2
    )
    assert scores["h_only"] == pytest.approx(
        COVERAGE_PENALTY_BY_ABSENT_NUCLEUS["13c"] / 2
    )
    assert scores["c_only"] < scores["h_only"]

    # The consequence that makes carbon-only references reachable: an exact 13C-only
    # match (0.05) CAN outrank a complete match that is slightly off (0.0588 here).
    # That is intended, not a regression -- it is why (d) went 88.8% -> 98.0% @1.
    both = _multi({
        "complete": ([1.0, 3.0], [20.0, 60.0]),
        "c_only": ([], [20.0, 60.0]),
    })
    assert both.search(encode_spectrum([1.05, 3.05], [20.0, 60.0]), k=2)[0][0] == "c_only"


def test_scalar_coverage_penalty_is_applied_uniformly_for_legacy_artifacts():
    """A manifest written before the penalty was per-nucleus persisted one float.

    Such an artifact must keep the ranking it was built with rather than silently
    acquiring the asymmetric weights, so a scalar spreads to every nucleus.
    """
    index = MultiNucleusSpectrumIndex(coverage_penalty=0.20)
    assert index.coverage_penalty == {"1h": 0.20, "13c": 0.20}


def test_legacy_scalar_penalty_survives_the_roundtrip(tmp_path):
    import json

    path = tmp_path / "legacy.faiss"
    index = MultiNucleusSpectrumIndex(coverage_penalty=0.20)
    index.add(encode_spectrum([1.0], [20.0]).reshape(1, -1), ["a"])
    index.save(str(path))
    # Rewrite the manifest the way a pre-per-nucleus build wrote it: a bare float.
    payload = json.loads(path.read_text())
    payload["coverage_penalty"] = 0.20
    path.write_text(json.dumps(payload))

    reloaded = load_index(str(path))
    assert reloaded.coverage_penalty == {"1h": 0.20, "13c": 0.20}


def test_fused_score_upper_bound_is_sqrt2_plus_heaviest_penalty():
    """An encoded half is non-negative, so two unit halves are at worst orthogonal.

    The bound is sqrt(2) + lambda, not 2 + lambda: antipodal halves are unreachable
    because a sum of Gaussians cannot go negative.
    """
    from moltrace.spectroscopy.similarity import FUSED_SCORE_MAX

    disjoint = float(np.linalg.norm(encode_spectrum([], [10.0]) - encode_spectrum([], [210.0])))
    assert disjoint == pytest.approx(math.sqrt(2.0), abs=1e-5)
    assert FUSED_SCORE_MAX == pytest.approx(
        math.sqrt(2.0) + max(COVERAGE_PENALTY_BY_ABSENT_NUCLEUS.values())
    )

    index = _multi({"far": ([], [210.0])})
    worst = index.search(encode_spectrum([1.0], [10.0]), k=1)[0][1]
    assert worst <= FUSED_SCORE_MAX + 1e-6


def test_load_index_does_not_parse_a_faiss_blob_as_json(tmp_path):
    """The layout probe reads a few bytes; it must not decode the whole artifact.

    Handing a large FAISS blob to json.load allocated ~3x its size and kept it alive
    inside the exception while the real reader ran.
    """
    path = tmp_path / "flat.faiss"
    flat = SpectrumIndex()
    flat.add(encode_spectrum([1.0], [20.0]).reshape(1, -1), ["a"])
    flat.save(str(path))

    assert path.read_bytes()[:4] == b"IHNf"  # FAISS HNSW fourcc, not JSON
    import tracemalloc

    tracemalloc.start()
    loaded = load_index(str(path))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert isinstance(loaded, SpectrumIndex)
    # Whole-file decode would scale with file size; a 64-byte probe does not.
    assert peak < max(4 * path.stat().st_size, 2_000_000)


def test_molecule_with_no_encodable_shift_is_in_no_sub_index(tmp_path):
    """Documents a real corpus condition rather than pretending it cannot happen.

    A molecule whose every shift falls outside the ppm grid encodes to all zeros and
    is retrievable by nothing (one such record exists in the NMRShiftDB2 export: a
    lone 13C at 333.8 ppm against a 0-220 grid). It still counts as a molecule, so
    index_size stays honest; scripts/build_similarity_index.py warns when it happens.
    """
    index = _multi({"ok": ([1.0], [20.0]), "off_grid": ([], [333.8])})
    assert len(index) == 2
    assert index.nucleus_size("13c") == 1
    assert all(i != "off_grid" for i, _ in index.search(encode_spectrum([], [333.8]), k=2))
