"""True multi-objective Pareto analysis for the Repho reaction optimizer (R2).

Replaces "weighted-sum only" with a real non-dominated (Pareto) front, a hypervolume
indicator, and a knee-point pick — pure NumPy/stdlib, deterministic, no BoTorch. The
maths are frozen and unit-tested; no model produces these numbers.

Conventions
-----------
* Each experiment contributes an objective *vector*; ``directions[i]`` is ``"max"`` or
  ``"min"`` per objective. Internally everything is converted to maximize-space.
* The hypervolume reference point defaults to the maximize-space origin (``0.0`` per
  objective). Callers should pass objectives already in a "higher = better, 0 = worst"
  scale (the Repho optimizer pre-maps impurity to ``100 - impurity`` and E-factor to a
  0–100 score), so the indicator is comparable across runs of the same objective set.
  For raw ``"min"`` objectives, pass an explicit worst-case ``reference``.
"""

from __future__ import annotations

from collections.abc import Sequence

Number = float
Point = Sequence[Number]


def _to_maximize(points: Sequence[Point], directions: Sequence[str]) -> list[list[float]]:
    return [
        [(-float(v) if d == "min" else float(v)) for v, d in zip(p, directions, strict=True)]
        for p in points
    ]


def _dominates(a: Sequence[float], b: Sequence[float]) -> bool:
    """True if a dominates b in maximize-space (>= on all dims, > on at least one)."""
    no_worse = True
    strictly_better = False
    for ai, bi in zip(a, b, strict=True):
        if ai < bi:
            no_worse = False
            break
        if ai > bi:
            strictly_better = True
    return no_worse and strictly_better


def non_dominated_indices(points: Sequence[Point], directions: Sequence[str]) -> list[int]:
    """Indices of the Pareto-optimal (non-dominated) points. O(n^2); fine for HTE sizes."""
    m = _to_maximize(points, directions)
    n = len(m)
    keep: list[int] = []
    for i in range(n):
        if any(j != i and _dominates(m[j], m[i]) for j in range(n)):
            continue
        keep.append(i)
    return keep


def _hv_2d(front: list[list[float]], ref: list[float]) -> float:
    """Exact 2-D hypervolume of the region dominated by ``front`` and above ``ref``
    (maximize-space). Sweeps from the largest x downward; each x-slab adds its width to
    the left edge times the gain in the running-best y. Dominated points contribute 0."""
    pts = [p for p in front if p[0] > ref[0] and p[1] > ref[1]]
    if not pts:
        return 0.0
    pts.sort(key=lambda p: p[0], reverse=True)
    hv = 0.0
    best_y = ref[1]
    for x, y in pts:
        if y > best_y:
            hv += (x - ref[0]) * (y - best_y)
            best_y = y
    return hv


def _hv_monte_carlo(front: list[list[float]], ref: list[float], *, samples: int = 200_000) -> float:
    """Deterministic Monte-Carlo hypervolume for >2 objectives (maximize-space).

    Uses a fixed-seed NumPy RNG so the value is reproducible run-to-run. Reported as
    ``hypervolume_method="monte_carlo"`` (an estimate, not exact)."""
    import numpy as np

    dims = len(ref)
    upper = [max(p[d] for p in front) for d in range(dims)]
    box = 1.0
    for d in range(dims):
        span = upper[d] - ref[d]
        if span <= 0:
            return 0.0
        box *= span
    rng = np.random.default_rng(20260615)
    arr = np.array(front, dtype=float)
    lo = np.array(ref, dtype=float)
    hi = np.array(upper, dtype=float)
    pts = lo + rng.random((samples, dims)) * (hi - lo)
    dominated = np.zeros(samples, dtype=bool)
    for f in arr:
        dominated |= np.all(f >= pts, axis=1)
    return float(box * dominated.mean())


def hypervolume(
    points: Sequence[Point],
    directions: Sequence[str],
    *,
    reference: Sequence[Number] | None = None,
) -> tuple[float, str]:
    """Hypervolume dominated by the non-dominated set, and the method used.

    Returns ``(hv, method)`` where method is ``"exact_2d"``, ``"monte_carlo"``, or
    ``"degenerate"``. Reference defaults to the maximize-space origin (0 per objective)."""
    if not points:
        return 0.0, "degenerate"
    dims = len(directions)
    m = _to_maximize(points, directions)
    nd = [m[i] for i in non_dominated_indices(points, directions)]
    if reference is None:
        ref = [0.0] * dims
    else:
        ref = [
            (-float(v)) if d == "min" else float(v)
            for v, d in zip(reference, directions, strict=True)
        ]
    if dims == 1:
        best = max((p[0] for p in nd), default=ref[0])
        return max(0.0, best - ref[0]), "exact_2d"
    if dims == 2:
        return _hv_2d(nd, ref), "exact_2d"
    return _hv_monte_carlo(nd, ref), "monte_carlo"


def knee_index(points: Sequence[Point], directions: Sequence[str]) -> int | None:
    """Index (into ``points``) of the knee of the non-dominated front — the best-balanced
    trade-off. Returns the strongest single point for a degenerate front, or None if empty."""
    nd = non_dominated_indices(points, directions)
    if not nd:
        return None
    m = _to_maximize(points, directions)
    if len(nd) <= 2:
        return max(nd, key=lambda i: sum(m[i]))
    dims = len(directions)
    mins = [min(m[i][d] for i in nd) for d in range(dims)]
    maxs = [max(m[i][d] for i in nd) for d in range(dims)]
    spans = [(maxs[d] - mins[d]) or 1.0 for d in range(dims)]

    def normalized_min(i: int) -> float:
        return min((m[i][d] - mins[d]) / spans[d] for d in range(dims))

    # Max-min fairness: the point whose worst normalized objective is highest — a robust,
    # dimension-agnostic proxy for the trade-off knee.
    return max(nd, key=normalized_min)


def pareto_summary(
    points: Sequence[Point],
    directions: Sequence[str],
    *,
    labels: Sequence[str] | None = None,
    reference: Sequence[Number] | None = None,
) -> dict:
    """Frozen, JSON-serializable Pareto summary for a set of objective vectors.

    ``points`` are the raw (un-negated) objective values; ``directions`` give max/min per
    objective."""
    nd = non_dominated_indices(points, directions)
    dominated = [i for i in range(len(points)) if i not in set(nd)]
    hv, method = hypervolume(points, directions, reference=reference)
    return {
        "objectives": list(labels) if labels is not None else None,
        "directions": list(directions),
        "non_dominated_indices": nd,
        "dominated_indices": dominated,
        "pareto_size": len(nd),
        "hypervolume": round(hv, 6),
        "hypervolume_method": method,
        "reference_point": list(reference) if reference is not None else [0.0] * len(directions),
        "knee_index": knee_index(points, directions),
        "guaranteed_optimum": False,
    }
