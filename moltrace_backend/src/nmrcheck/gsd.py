"""Global Spectral Deconvolution (GSD) for 1H multiplet resolution.

A local-maximum peak picker reports only the lines it can see as separate
bumps; overlapped transitions inside a multiplet are merged and lost. This
module fits each detected multiplet region to a sum of analytic lineshapes
and so recovers the resolved transition list. From that list the coupling
pattern (multiplicity) and J-couplings are read by first-order rules.

Grounded in the established GSD principle: every peak in a 1H-NMR spectrum is
basically an envelope of a large number of transitions; GSD applies an
automatic deconvolution of the spectrum into a list of fully-characterised
peaks (centre, height, width).

Each line is modelled as a **pseudo-Voigt** — a mix ``eta * Lorentzian +
(1 - eta) * Gaussian``. A real NMR line is Lorentzian from T2 relaxation but
acquires Gaussian character from field inhomogeneity and apodisation; fitting
a fixed pure-Lorentzian shape would chase that mismatch by inventing extra
lines. The per-line ``eta`` lets one line absorb one peak whatever its shape.

The fit runs in two passes so the resolved line set is both complete and
parsimonious:

* **Forward** — fit from the detected seed maxima, then add a line wherever
  the residual still falls a real amount below the data (an unresolved,
  overlapped transition) and refit.
* **Backward** — drop the weakest line and refit; if the region is still
  reproduced within the noise floor the line was redundant. Plain
  least-squares has no cost for extra lines, so this elimination is what
  prevents an over-seeded region from being over-resolved.

This is a region-wise deconvolution: each detected multiplet is fitted on its
own — numerically far more stable than one whole-spectrum fit, and it achieves
the same goal of resolving the lines inside each multiplet.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import least_squares

# Plausible homonuclear 1H-1H coupling window (Hz). Spacings outside this are
# not treated as real J couplings.
_MIN_J_HZ = 0.5
_MAX_J_HZ = 60.0

# A fit is accepted (and a line is deemed redundant) when the region is
# reproduced to within this many noise-sigma everywhere.
_FIT_TOLERANCE_SIGMA = 5.0

# Parameters per pseudo-Voigt line: amplitude, centre, hwhm, eta.
_PARAMS_PER_LINE = 4

_LN2 = math.log(2.0)

_SIMPLE_MULTIPLICITY: dict[int, str] = {
    2: "d",
    3: "t",
    4: "q",
    5: "p",
    6: "sext",
    7: "sept",
}


def _pseudo_voigt_sum(x: np.ndarray, params: np.ndarray) -> np.ndarray:
    """Sum of pseudo-Voigt lineshapes (vectorized over lines).

    ``params`` is flat ``[amp, centre, hwhm, eta, ...]``. Each line is
    ``amp * (eta * Lorentzian + (1 - eta) * Gaussian)`` with both components
    sharing the same half-width at half-maximum.

    Vectorized via broadcasting: reshape params to ``[N_lines, 4]`` and
    compute the full ``[N_lines, M_points]`` pseudo-Voigt tensor in one
    pass.  Paired with ``_pseudo_voigt_jacobian`` (analytical jacobian) to
    eliminate scipy's finite-difference jacobian iterations -- the prior
    perf bottleneck in dense 13C deconvolutions like NMRShiftDB2 60000006_13c.
    """

    n_lines = len(params) // _PARAMS_PER_LINE
    if n_lines == 0:
        return np.zeros_like(x)
    # [N_lines, 4]  -- amp, centre, hwhm, eta
    p = np.asarray(params, dtype=float).reshape(n_lines, _PARAMS_PER_LINE)
    amp = p[:, 0:1]
    center = p[:, 1:2]
    hwhm = p[:, 2:3]
    eta = p[:, 3:4]
    # Broadcast x [M] -> [1, M] -> [N, M] for dx
    x_bc = np.asarray(x, dtype=float)[np.newaxis, :]
    dx2 = (x_bc - center) ** 2  # [N, M]
    hwhm2 = hwhm * hwhm  # [N, 1]
    lorentzian = hwhm2 / (dx2 + hwhm2)  # [N, M]
    gaussian = np.exp(-_LN2 * dx2 / hwhm2)  # [N, M]
    return (amp * (eta * lorentzian + (1.0 - eta) * gaussian)).sum(axis=0)


def _pseudo_voigt_jacobian(x: np.ndarray, params: np.ndarray) -> np.ndarray:
    """Analytical jacobian of ``_pseudo_voigt_sum`` w.r.t. ``params``.

    Returns ``[M_points, 4 * N_lines]`` matrix in column order
    ``[d/d(amp_0), d/d(center_0), d/d(hwhm_0), d/d(eta_0), d/d(amp_1), ...]``
    matching the flat ``params`` layout.

    Closed-form derivatives per line (cross-line entries are zero because
    each line is additive and independent in its own 4 parameters):

      d(pv)/d(amp)    = eta * L + (1 - eta) * G
      d(pv)/d(center) = 2 * amp * dx / h^2 * (eta * L^2 + (1-eta) * ln2 * G)
      d(pv)/d(hwhm)   = amp * (eta * 2*L*(1-L)/h + (1-eta) * G * 2*ln2*dx^2/h^3)
      d(pv)/d(eta)    = amp * (L - G)

    where L = h^2/(dx^2+h^2), G = exp(-ln2 * dx^2 / h^2), dx = x - center, h = hwhm.

    Passing this to ``scipy.optimize.least_squares`` via ``jac=`` eliminates
    the finite-difference fallback (which previously called
    ``_pseudo_voigt_sum`` ~643k times for a dense 13C spectrum).
    """

    n_lines = len(params) // _PARAMS_PER_LINE
    m_points = int(np.asarray(x).size)
    if n_lines == 0:
        return np.zeros((m_points, 0), dtype=float)
    p = np.asarray(params, dtype=float).reshape(n_lines, _PARAMS_PER_LINE)
    amp = p[:, 0:1]
    center = p[:, 1:2]
    hwhm = p[:, 2:3]
    eta = p[:, 3:4]
    x_bc = np.asarray(x, dtype=float)[np.newaxis, :]
    dx = x_bc - center  # [N, M]
    dx2 = dx * dx
    hwhm2 = hwhm * hwhm
    hwhm3 = hwhm2 * hwhm
    denom = dx2 + hwhm2
    L = hwhm2 / denom  # [N, M]
    G = np.exp(-_LN2 * dx2 / hwhm2)  # [N, M]
    one_minus_eta = 1.0 - eta
    one_minus_L = 1.0 - L

    # Per-parameter blocks [N, M].
    d_amp = eta * L + one_minus_eta * G
    d_center = 2.0 * amp * dx / hwhm2 * (eta * L * L + one_minus_eta * _LN2 * G)
    d_hwhm = amp * (
        eta * 2.0 * L * one_minus_L / hwhm
        + one_minus_eta * G * 2.0 * _LN2 * dx2 / hwhm3
    )
    d_eta = amp * (L - G)

    # Stack as [N, 4, M] then reshape to [N*4, M] then transpose -> [M, N*4].
    jac_per_line = np.stack([d_amp, d_center, d_hwhm, d_eta], axis=1)
    return jac_per_line.reshape(n_lines * _PARAMS_PER_LINE, m_points).T


def deconvolve_region(
    x_region: list[float],
    y_region: list[float],
    seed_centers: list[float],
    *,
    noise_sigma: float,
    max_lines: int = 24,
) -> list[tuple[float, float, float]]:
    """Deconvolve one multiplet region into resolved pseudo-Voigt lines.

    Returns ``(center_ppm, height, hwhm_ppm)`` per resolved line, sorted by
    ppm — or ``[]`` when the region is too small or the fit cannot be trusted,
    so the caller falls back to the raw local-maximum count.
    """
    x = np.asarray(x_region, dtype=float)
    y = np.asarray(y_region, dtype=float)
    seeds_raw = sorted(float(center) for center in seed_centers if math.isfinite(center))
    if x.size < 8 or not seeds_raw:
        return []
    x_lo = float(np.min(x))
    x_hi = float(np.max(x))
    span = x_hi - x_lo
    if span <= 0.0:
        return []
    step = span / float(x.size - 1)
    min_hwhm = max(step * 0.75, span * 1e-3)
    max_hwhm = max(min_hwhm * 3.0, span * 0.6)
    height = float(np.max(y))
    if not math.isfinite(height) or height <= 0.0:
        return []
    # A line must clear this to count as real; also the fit-quality scale.
    noise_floor = max(float(noise_sigma), height * 5e-3)
    tolerance = _FIT_TOLERANCE_SIGMA * noise_floor

    # Coarsely dedup + clamp the seeds. The forward pass adds lines where the
    # data demands them and the backward pass prunes redundant ones, so the
    # exact seed count is not critical — but it must be a clean minimal set.
    seed_gap = max(min_hwhm * 4.0, step * 10.0)
    seeds: list[float] = []
    for center in seeds_raw:
        clamped = min(max(center, x_lo), x_hi)
        if seeds and abs(clamped - seeds[-1]) <= seed_gap:
            continue
        seeds.append(clamped)
    seeds = seeds[:max_lines]

    def residual(params: np.ndarray) -> np.ndarray:
        return _pseudo_voigt_sum(x, params) - y

    def jacobian(params: np.ndarray) -> np.ndarray:
        # dr/dp = d(pv_sum - y)/dp = d(pv_sum)/dp because y is independent of p.
        return _pseudo_voigt_jacobian(x, params)

    def fit_centers(centers: list[float]) -> tuple[np.ndarray | None, float]:
        """Fit pseudo-Voigt lines at ``centers``; return (params, max abs resid)."""
        if not centers:
            return (None, math.inf)
        initial: list[float] = []
        lower: list[float] = []
        upper: list[float] = []
        for center in centers:
            initial += [height * 0.4, min(max(center, x_lo), x_hi), min_hwhm * 2.0, 0.6]
            lower += [0.0, x_lo, min_hwhm, 0.0]
            upper += [height * 1.6, x_hi, max_hwhm, 1.0]
        try:
            # Supplying the analytical jacobian eliminates scipy's
            # finite-difference jacobian (which would call ``residual``
            # ~4*N additional times per iteration to numerically estimate
            # derivatives).  See _pseudo_voigt_jacobian for the math.
            fit = least_squares(
                residual,
                initial,
                jac=jacobian,
                bounds=(lower, upper),
                method="trf",
                max_nfev=6000,
            )
        except (ValueError, RuntimeError):
            return (None, math.inf)
        return (fit.x, float(np.max(np.abs(residual(fit.x)))))

    def centers_of(params: np.ndarray) -> list[float]:
        return [float(params[index + 1]) for index in range(0, len(params), _PARAMS_PER_LINE)]

    # ---- Forward pass: fit from seeds, add lines the residual still demands.
    best, best_resid = fit_centers(seeds)
    if best is None:
        return []
    while len(best) // _PARAMS_PER_LINE < max_lines:
        resid = residual(best)
        if -float(np.min(resid)) <= tolerance:  # no real unfitted line left
            break
        worst_x = float(x[int(np.argmin(resid))])
        current = centers_of(best)
        if any(abs(worst_x - center) <= min_hwhm * 2.0 for center in current):
            break  # a line already covers that spot — adding more would overfit
        trial, trial_resid = fit_centers([*current, worst_x])
        if trial is None or trial_resid >= best_resid:
            break
        best, best_resid = trial, trial_resid

    # ---- Backward pass: drop redundant lines (only worthwhile once the
    # forward fit actually reproduces the region within the noise floor).
    if best_resid <= tolerance:
        while best is not None and len(best) // _PARAMS_PER_LINE > 1:
            amplitudes = [
                float(best[index]) for index in range(0, len(best), _PARAMS_PER_LINE)
            ]
            weakest = int(np.argmin(amplitudes))
            kept = [
                center
                for line, center in enumerate(centers_of(best))
                if line != weakest
            ]
            trial, trial_resid = fit_centers(kept)
            if trial is None or trial_resid > tolerance:
                break  # the dropped line was load-bearing — keep it
            best, best_resid = trial, trial_resid

    if best is None:
        return []
    lines: list[tuple[float, float, float]] = []
    for index in range(0, len(best), _PARAMS_PER_LINE):
        amplitude = float(best[index])
        center = float(best[index + 1])
        hwhm = float(best[index + 2])
        if amplitude >= 3.0 * noise_floor and math.isfinite(center):
            lines.append((center, amplitude, hwhm))
    lines.sort(key=lambda line: line[0])
    # Collapse lines that converged onto the same position.
    merged: list[tuple[float, float, float]] = []
    for line in lines:
        if merged and abs(line[0] - merged[-1][0]) <= min_hwhm * 3.0:
            if line[1] > merged[-1][1]:
                merged[-1] = line
            continue
        merged.append(line)
    return merged


def _distinct_spacings(spacings: list[float], tolerance: float) -> list[float]:
    """Cluster nearly-equal spacings and return their group means, descending."""
    groups: list[list[float]] = []
    for value in sorted(spacings, reverse=True):
        for group in groups:
            if abs(sum(group) / len(group) - value) <= tolerance:
                group.append(value)
                break
        else:
            groups.append([value])
    return [round(sum(group) / len(group), 1) for group in groups]


def multiplicity_from_lines(
    line_centers: list[float],
    *,
    frequency_mhz: float | None,
) -> tuple[str, tuple[float, ...]]:
    """First-order multiplicity + J from a resolved (deconvolved) line list.

    With the lines properly resolved, adjacent-line spacings are clean. A set
    of equal spacings is a simple multiplet (d / t / q / p / sext / sept). A
    four-line symmetric ``a, b, a`` spacing pattern is a doublet-of-doublets —
    note its adjacent spacings are *not* the couplings: the J pair is recovered
    from line-pair separations by first-order rules. Anything else is reported
    honestly as a generic multiplet "m" with the resolved J set.
    """
    finite = [float(center) for center in line_centers if math.isfinite(center)]
    line_count = len(finite)
    if line_count <= 1:
        return ("s", ())
    if frequency_mhz is None or frequency_mhz <= 0:
        return ("m", ())
    frequency = float(frequency_mhz)
    ascending = sorted(finite)
    spacings = [
        (ascending[index + 1] - ascending[index]) * frequency
        for index in range(line_count - 1)
    ]
    if any(value < _MIN_J_HZ or value > _MAX_J_HZ for value in spacings):
        # A spacing outside the J window — these lines are not one first-order
        # multiplet (e.g. two separate multiplets clustered together).
        return ("m", ())
    mean_spacing = sum(spacings) / len(spacings)
    tolerance = max(0.6, mean_spacing * 0.18)
    if all(abs(value - mean_spacing) <= tolerance for value in spacings):
        return (_SIMPLE_MULTIPLICITY.get(line_count, "m"), (round(mean_spacing, 1),))
    if line_count == 4 and abs(spacings[0] - spacings[2]) <= tolerance:
        # Doublet-of-doublets: lines sit at ±J_large/2 ±J_small/2, so the
        # couplings come from line-pair separations, not adjacent spacings.
        j_small = (
            (ascending[1] - ascending[0]) + (ascending[3] - ascending[2])
        ) / 2.0 * frequency
        j_large = (
            (ascending[2] - ascending[0]) + (ascending[3] - ascending[1])
        ) / 2.0 * frequency
        return ("dd", (round(j_large, 1), round(j_small, 1)))
    distinct = _distinct_spacings(spacings, tolerance)
    return ("m", tuple(sorted(distinct, reverse=True))[:3])
