from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class PeakMatch:
    observed_ppm: float
    expected_ppm: float
    delta_ppm: float
    score: float


def gaussian_kernel(delta: float, sigma: float) -> float:
    if sigma <= 0:
        return 0.0
    return math.exp(-((delta * delta) / (2.0 * sigma * sigma)))


def greedy_set_similarity(observed: Iterable[float], expected: Iterable[float], *, sigma: float = 0.08) -> tuple[float, list[PeakMatch], list[float], list[float]]:
    """Small, dependency-free approximate set similarity for NMR peak lists.

    It aligns observed and expected chemical shifts greedily using a Gaussian kernel.
    This is not the full Hungarian assignment used in some publications, but it gives
    us a transparent and testable score until scipy becomes a dependency.
    """
    obs = sorted(float(x) for x in observed)
    exp = sorted(float(x) for x in expected)
    if not obs and not exp:
        return 1.0, [], [], []
    if not obs or not exp:
        return 0.0, [], obs, exp

    candidates: list[tuple[float, int, int, float]] = []
    for oi, o in enumerate(obs):
        for ei, e in enumerate(exp):
            delta = abs(o - e)
            score = gaussian_kernel(delta, sigma)
            candidates.append((score, oi, ei, delta))
    candidates.sort(reverse=True, key=lambda item: item[0])

    used_o: set[int] = set()
    used_e: set[int] = set()
    matches: list[PeakMatch] = []
    for score, oi, ei, delta in candidates:
        if oi in used_o or ei in used_e:
            continue
        if score < 0.05:
            continue
        used_o.add(oi)
        used_e.add(ei)
        matches.append(PeakMatch(observed_ppm=obs[oi], expected_ppm=exp[ei], delta_ppm=delta, score=score))

    unmatched_observed = [value for idx, value in enumerate(obs) if idx not in used_o]
    unmatched_expected = [value for idx, value in enumerate(exp) if idx not in used_e]
    denom = math.sqrt(max(1, len(obs)) * max(1, len(exp)))
    similarity = sum(match.score for match in matches) / denom
    return round(max(0.0, min(1.0, similarity)), 4), matches, unmatched_observed, unmatched_expected


def bounded_score(delta: float, tolerance: float) -> float:
    if tolerance <= 0:
        return 0.0
    return round(max(0.0, min(1.0, 1.0 - abs(delta) / tolerance)), 4)


def ratio_score(observed: float, expected: float, *, tolerance_fraction: float = 0.25, absolute_tolerance: float = 1.0) -> float:
    tolerance = max(absolute_tolerance, abs(expected) * tolerance_fraction)
    return bounded_score(observed - expected, tolerance)
