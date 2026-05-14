"""DP4 candidate-ranking probability.

Implements the Bayesian probability assignment from Smith & Goodman,
*J. Am. Chem. Soc.* 2010, 132 (37), 12946 — "Assigning the Stereochemistry of
Pairs of Diastereoisomers from GIAO NMR Shift Calculations: The DP4 Probability."

Given:
  - a set of observed NMR shifts δ_exp,k (k = 1..N) for a single nucleus,
  - one predicted shift list δ_calc,k^(i) per candidate i,

DP4 computes the posterior probability that candidate i is correct under a
Student's t error model with scale σ and degrees of freedom ν:

    P(i | δ) = ∏_k (1 − T_ν(|Δ_k,i| / σ)) / Σ_j ∏_k (1 − T_ν(|Δ_k,j| / σ))

where T_ν is the cumulative two-tailed Student's t-distribution. We use the
published scale/dof pair (σ_1H = 0.185, ν_1H = 14.18; σ_13C = 2.306,
ν_13C = 11.38) from the paper's Table 2.

Notes:
- The original DP4 first linearly scales calc shifts via slope/intercept from
  regressing calc vs exp. We do that too when there are ≥ 3 paired points;
  with fewer points the scaling falls back to identity (no fit possible).
- The product over peaks tends to underflow on dense lists. We do everything
  in log space and renormalise at the end.

Public entry points:
- :func:`dp4_probabilities` — full multi-candidate ranking.
- :func:`pair_residual_dp4_score` — per-peak unnormalised score for the
  predicted-vs-observed table (a "z-like" value that's nucleus-aware).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

from .literature_data import (
    DP4_NU_13C,
    DP4_NU_1H,
    DP4_SIGMA_13C,
    DP4_SIGMA_1H,
    dp4_nu,
    dp4_sigma,
)

Nucleus = Literal["1H", "13C"]


@dataclass(frozen=True)
class DP4CandidateScore:
    """One candidate's DP4 result."""

    candidate_index: int
    probability: float  # in [0, 1], sums to 1.0 across the suite
    log_likelihood: float
    matched_peaks: int
    mean_abs_error_ppm: float
    rms_error_ppm: float
    slope: float
    intercept: float
    notes: list[str]


def _student_t_cdf(t: float, nu: float) -> float:
    """Two-tailed Student's t cumulative distribution.

    Returns ``P(|T| ≤ |t|)`` for a t-distributed variable with ``nu`` degrees
    of freedom. Implemented via the regularised incomplete beta function so we
    don't need scipy at runtime.

        F(|t|; ν) = 1 − I_x(ν/2, 1/2), where x = ν / (ν + t²)
    """
    t = abs(t)
    if nu <= 0:
        return 0.0
    if not math.isfinite(t):
        return 1.0
    x = nu / (nu + t * t)
    incomplete = _regularised_incomplete_beta(x, nu / 2.0, 0.5)
    return 1.0 - incomplete


def _regularised_incomplete_beta(x: float, a: float, b: float) -> float:
    """Continued-fraction evaluation of I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    # Use the symmetric identity if x is in the upper half of the [0,1] range
    # so the continued fraction converges fast.
    log_bt = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _beta_cf(x, a, b) / a
    return 1.0 - bt * _beta_cf(1.0 - x, b, a) / b


def _beta_cf(x: float, a: float, b: float, max_iter: int = 200, eps: float = 3.0e-7) -> float:
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1.0e-30:
        d = 1.0e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1.0e-30:
            d = 1.0e-30
        c = 1.0 + aa / c
        if abs(c) < 1.0e-30:
            c = 1.0e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1.0e-30:
            d = 1.0e-30
        c = 1.0 + aa / c
        if abs(c) < 1.0e-30:
            c = 1.0e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _linear_fit(x: Sequence[float], y: Sequence[float]) -> tuple[float, float]:
    """Plain ordinary-least-squares slope / intercept of y vs x."""
    n = len(x)
    if n != len(y) or n < 2:
        return 1.0, 0.0
    sx = sum(x)
    sy = sum(y)
    sxx = sum(v * v for v in x)
    sxy = sum(a * b for a, b in zip(x, y))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        return 1.0, 0.0
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return slope, intercept


def _pair_observed_predicted(
    observed: Sequence[float], predicted: Sequence[float], tolerance: float
) -> tuple[list[float], list[float], int]:
    """Greedy nearest-shift pairing for DP4 scoring.

    We don't have explicit atom labels here, so we pair each observed peak
    with its nearest still-unused predicted shift within ``tolerance``. Any
    leftovers are dropped — DP4 only operates on assigned pairs.

    Returns (paired_obs, paired_pred, unmatched_count).
    """
    used: set[int] = set()
    paired_obs: list[float] = []
    paired_pred: list[float] = []
    unmatched = 0
    for obs in observed:
        best_idx: int | None = None
        best_delta: float | None = None
        for idx, pred in enumerate(predicted):
            if idx in used:
                continue
            delta = abs(pred - obs)
            if delta > tolerance:
                continue
            if best_delta is None or delta < best_delta:
                best_idx = idx
                best_delta = delta
        if best_idx is None:
            unmatched += 1
            continue
        used.add(best_idx)
        paired_obs.append(obs)
        paired_pred.append(predicted[best_idx])
    return paired_obs, paired_pred, unmatched


def dp4_probabilities(
    *,
    observed_shifts_ppm: Sequence[float],
    candidate_predicted_shifts_ppm: Sequence[Sequence[float]],
    nucleus: Nucleus,
    pairing_tolerance_ppm: float | None = None,
    apply_linear_scaling: bool = True,
) -> list[DP4CandidateScore]:
    """Compute DP4 probabilities for a list of candidate predictions.

    Parameters
    ----------
    observed_shifts_ppm
        The user's observed chemical-shift list for one nucleus.
    candidate_predicted_shifts_ppm
        ``len(candidates)`` lists of predicted shifts (one per candidate).
    nucleus
        ``"1H"`` or ``"13C"`` — selects σ and ν from Smith & Goodman 2010.
    pairing_tolerance_ppm
        Used to greedily pair predicted to observed peaks before scoring. The
        Computational-NMR-survey "acceptable" deviation is used by default
        (0.3 ppm 1H, 6 ppm 13C).
    apply_linear_scaling
        Whether to apply the calc→exp linear scaling Smith & Goodman recommend.

    Returns
    -------
    A list of :class:`DP4CandidateScore`, one per candidate. Probabilities sum
    to 1.0 if at least one candidate produced a finite score.
    """
    if pairing_tolerance_ppm is None:
        pairing_tolerance_ppm = 0.3 if nucleus == "1H" else 6.0

    sigma = dp4_sigma(nucleus)
    nu = dp4_nu(nucleus)
    n_candidates = len(candidate_predicted_shifts_ppm)
    if n_candidates == 0:
        return []

    log_likelihoods: list[float] = []
    diagnostics: list[DP4CandidateScore] = []

    for idx, predicted in enumerate(candidate_predicted_shifts_ppm):
        obs_paired, pred_paired, unmatched = _pair_observed_predicted(
            observed_shifts_ppm, predicted, pairing_tolerance_ppm
        )
        notes: list[str] = []
        slope = 1.0
        intercept = 0.0
        if apply_linear_scaling and len(obs_paired) >= 3:
            slope, intercept = _linear_fit(pred_paired, obs_paired)
            pred_scaled = [slope * p + intercept for p in pred_paired]
        else:
            pred_scaled = list(pred_paired)
            if apply_linear_scaling and len(obs_paired) < 3:
                notes.append(
                    "Fewer than 3 paired peaks — linear scaling skipped, "
                    "DP4 evaluated on raw predicted shifts."
                )
        deltas = [o - p for o, p in zip(obs_paired, pred_scaled)]
        n_matched = len(deltas)
        if n_matched == 0:
            diagnostics.append(
                DP4CandidateScore(
                    candidate_index=idx,
                    probability=0.0,
                    log_likelihood=-math.inf,
                    matched_peaks=0,
                    mean_abs_error_ppm=0.0,
                    rms_error_ppm=0.0,
                    slope=1.0,
                    intercept=0.0,
                    notes=["No predicted peak matched within tolerance — DP4 = 0."],
                )
            )
            log_likelihoods.append(-math.inf)
            continue

        log_lik = 0.0
        for delta in deltas:
            tail = 1.0 - _student_t_cdf(delta / sigma, nu)
            # Cap the per-term contribution to avoid -inf from numerical underflow.
            log_lik += math.log(max(tail, 1e-300))
        # Penalise unmatched predicted peaks softly so candidates with totally
        # different shift skeletons still rank below ones that align.
        if unmatched:
            log_lik += unmatched * math.log(0.5)
            notes.append(
                f"{unmatched} observed peak(s) unmatched within ±"
                f"{pairing_tolerance_ppm} ppm; soft penalty applied."
            )
        log_likelihoods.append(log_lik)

        abs_errors = [abs(d) for d in deltas]
        diagnostics.append(
            DP4CandidateScore(
                candidate_index=idx,
                probability=0.0,  # filled below
                log_likelihood=log_lik,
                matched_peaks=n_matched,
                mean_abs_error_ppm=sum(abs_errors) / n_matched,
                rms_error_ppm=math.sqrt(sum(d * d for d in deltas) / n_matched),
                slope=slope,
                intercept=intercept,
                notes=notes,
            )
        )

    # Renormalise into probabilities. Use the log-sum-exp trick to avoid
    # underflow when likelihoods are very small.
    finite = [ll for ll in log_likelihoods if math.isfinite(ll)]
    if not finite:
        return diagnostics
    m = max(finite)
    weights = [math.exp(ll - m) if math.isfinite(ll) else 0.0 for ll in log_likelihoods]
    total = sum(weights)
    if total <= 0.0:
        return diagnostics
    probabilities = [w / total for w in weights]
    return [
        DP4CandidateScore(
            candidate_index=diag.candidate_index,
            probability=round(prob, 6),
            log_likelihood=diag.log_likelihood,
            matched_peaks=diag.matched_peaks,
            mean_abs_error_ppm=round(diag.mean_abs_error_ppm, 4),
            rms_error_ppm=round(diag.rms_error_ppm, 4),
            slope=round(diag.slope, 4),
            intercept=round(diag.intercept, 4),
            notes=diag.notes,
        )
        for diag, prob in zip(diagnostics, probabilities)
    ]


def pair_residual_dp4_score(
    *, observed_ppm: float, predicted_ppm: float, nucleus: Nucleus
) -> dict[str, float]:
    """Per-pair DP4 z-like score useful for surfacing in evidence tables.

    Returns
    -------
    ``{"delta_ppm", "z_dp4", "tail_probability"}``

    - ``z_dp4`` = (predicted − observed) / σ  (signed; sigma from DP4).
    - ``tail_probability`` = 1 − T_ν(|z_dp4|) — closer to 0 means a worse fit.
    """
    sigma = dp4_sigma(nucleus)
    nu = dp4_nu(nucleus)
    delta = predicted_ppm - observed_ppm
    z = delta / sigma if sigma else 0.0
    tail = 1.0 - _student_t_cdf(z, nu)
    return {
        "delta_ppm": round(delta, 4),
        "z_dp4": round(z, 4),
        "tail_probability": round(tail, 6),
    }


__all__ = [
    "DP4CandidateScore",
    "DP4_NU_13C",
    "DP4_NU_1H",
    "DP4_SIGMA_13C",
    "DP4_SIGMA_1H",
    "dp4_probabilities",
    "pair_residual_dp4_score",
]
