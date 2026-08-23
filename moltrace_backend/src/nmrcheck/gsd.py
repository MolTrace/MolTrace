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
#
# The upper edge is a claim about CHEMISTRY, and it decides a discrete label, so
# it was measured rather than guessed. Dumping every adjacent-line spacing the
# deconvolution produces across the 19-fixture golden corpus (773 spacings from
# 126 multiplets) splits cleanly into two regimes with nothing in between:
#
#   * spacings actually reported as a coupling (d / t / q / dd ...) top out at
#     18.06 Hz -- a geminal 2J, the largest genuine 1H-1H coupling in the corpus;
#   * the next-largest values are 43.52 and 45.62 Hz, and neither is a coupling.
#     43.52 Hz is 60000023 (cocaine) peak 2, two overlapping bicyclic-ring
#     signals; 45.62 Hz is 40256149 (piperine) peak 9, two methylene multiplets
#     inside the piperidine envelope. Neither compound contains fluorine or
#     phosphorus, so no heteronuclear route reaches those values either.
#
# So the interval (18.06, 43.52) Hz is EMPTY, and the previous 60.0 sat on the
# far side of it -- past both spurious pairs, which were therefore shipped to
# chemists as doublets with impossible J values. Its midpoint, the edge furthest
# from both regimes, is 30.79 Hz; the independently tuned 1H multiplet window in
# moltrace.spectroscopy.peaks.gsd (_DEFAULT_CLUSTER_J_HZ_BY_NUCLEUS) answers the
# same physical question -- how far apart two lines of one 1H multiplet can sit --
# and was tuned against the same corpus to 30.0. Those two agree to 0.8 Hz, so
# 30.0 it is, and the two constants now say the same thing instead of differing
# by a factor of two.
#
# The exact value inside that empty interval is not load-bearing for this corpus:
# any edge in [19, 43] Hz classifies all 177 golden peaks identically. That is the
# point. A threshold on a fitted quantity belongs where the density is zero, not
# where a round number happens to fall -- the fit's own spread on the weakest
# lines is several Hz, so an edge with data near it makes the reported
# multiplicity a function of the last bits of the input. tests/test_gsd.py
# TestTheCouplingWindowIsAChemicalBound pins the two regimes and deliberately
# asserts nothing about the gap between them.
_MIN_J_HZ = 0.5
_MAX_J_HZ = 30.0

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


def pseudo_voigt_area(amplitude: float, hwhm: float, eta: float) -> float:
    """Analytic area of one fitted line.

    Closed form for the shape :func:`_pseudo_voigt_sum` fits --
    ``amp * (eta * Lorentzian + (1 - eta) * Gaussian)`` with a shared half-width
    at half-maximum, so ``eta`` is the LORENTZIAN fraction::

        integral of  w^2 / (x^2 + w^2)        = pi * w
        integral of  exp(-ln2 * x^2 / w^2)    = w * sqrt(pi / ln 2)

    It lives here, beside the lineshape, because ``eta`` only exists inside the
    fit. Reconstructing an area downstream from height and width alone silently
    assumes a pure Lorentzian and overstates a Gaussian-leaning line by up to
    ~66 % (pi vs sqrt(pi/ln 2)) -- and the parameter needed to correct it was the
    one being discarded, so the error could not be detected from outside.
    """
    return float(
        amplitude * (eta * math.pi * hwhm + (1.0 - eta) * hwhm * math.sqrt(math.pi / _LN2))
    )


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
) -> list[tuple[float, float, float, float]]:
    """Deconvolve one multiplet region into resolved pseudo-Voigt lines.

    Returns ``(center_ppm, height, hwhm_ppm, area)`` per resolved line, sorted by
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
                # scipy's default 1e-8, restored. A previous change loosened these
                # to 1e-5 for speed on the premise that the fit "stops changing"
                # long before 1e-8 — measured true on one 65k-point spectrum (same
                # 40 peaks, 0.0000 Hz drift, identical multiplicities, 6.95x faster).
                #
                # It is NOT true across the fixture corpus. Multiplicity is a
                # DISCRETE label read off the resolved line COUNT, and for real
                # spectra the count is still moving between 1e-5 and 1e-8: measured,
                # nmrshiftdb2 40256149 peak 2 reads a generic "m" at 1e-8 and flips
                # to "t" at 1e-5 / 1e-6 / 1e-7 alike — i.e. 1e-5 reports an
                # UNDER-converged fit, not a faster-but-equal one. No tolerance
                # between 1e-5 and 1e-7 reproduces the goldens; only 1e-8 does. The
                # output-invariance goldens (test_fid_pipeline_invariants.py) caught
                # exactly this, which is their job.
                #
                # Re-measured over the whole corpus on ONE machine, so no platform
                # variable is in play: 3 of 177 labels differ between the two — that
                # peak in both guidance configs, plus 40256175 guided peak 8
                # ("dd" -> "m"). At 1e-8 all 177 reproduce the committed goldens
                # exactly; at 1e-5 those three do not. Note the direction, because
                # it is the opposite of the intuition and makes 1e-5 look good in a
                # spot check: 1e-5 is MORE repeatable under a perturbed input and
                # LESS correct, since a looser stop halts nearer the initial guess —
                # so the label is then set partly by that guess, not by the data.
                #
                # This was loosened a second time (aad2174) on the premise that the
                # goldens would be re-minted on Linux to match. That re-mint is a
                # manual workflow and never ran, so main shipped a fit whose labels
                # disagreed with its own committed goldens on the very platform they
                # were minted on. Restored here; if you loosen it again, re-mint in
                # the SAME commit or the corpus tier is red the moment it runs.
                #
                # A discrete classifier has to sit on a converged fit. If the SVD
                # cost matters, the lever is fewer/cheaper fits or better initial
                # guesses (output-preserving), not a looser stop that changes which
                # multiplet the chemist is shown.
                #
                # Convergence is necessary but not sufficient: a few genuinely-
                # ambiguous multiplets still land in a different local minimum under
                # Linux/x86 LAPACK than under macOS/ARM at 1e-8, because their label
                # turns on a resolved line count or a spacing-symmetry test that the
                # data does not settle. Those are named with their measured evidence
                # in tests/golden/fid_invariants/boundary_register.json — do not
                # reach for the tolerance again to chase them.
                ftol=1e-8,
                xtol=1e-8,
                gtol=1e-8,
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
    lines: list[tuple[float, float, float, float]] = []
    for index in range(0, len(best), _PARAMS_PER_LINE):
        amplitude = float(best[index])
        center = float(best[index + 1])
        hwhm = float(best[index + 2])
        # index + 3 is eta, and it was the parameter being dropped. The area is
        # computed here, where it is still in scope.
        eta = float(np.clip(best[index + 3], 0.0, 1.0))
        if amplitude >= 3.0 * noise_floor and math.isfinite(center):
            lines.append((center, amplitude, hwhm, pseudo_voigt_area(amplitude, hwhm, eta)))
    lines.sort(key=lambda line: line[0])
    # Collapse lines that converged onto the same position.
    merged: list[tuple[float, float, float, float]] = []
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


def _collapse_sub_coupling_runs(
    ascending: list[float], *, frequency: float
) -> list[float]:
    """Collapse runs of lines too close together to be coupling partners.

    ``_MIN_J_HZ`` is the smallest resolvable 1H-1H scalar coupling. Two lines
    closer together than that are therefore not two coupling partners, and the
    pattern reader must not count them as two lines -- whatever they are, one
    transition whose lineshape the fit tiled with several components, or two
    genuinely degenerate transitions, they contribute a single line to a
    first-order pattern.

    This is not a loosening of the J window: the same ``_MIN_J_HZ`` still rejects
    a multiplet whose spacings fall outside it, and a spacing AT the bound is
    still a coupling. It is the other reading of the same bound, applied one step
    earlier -- to the lines rather than to the spacings between them.

    Without it a single sub-resolution gap discards the whole multiplet. Measured
    across the 19 nmrshiftdb2 raw-FID fixtures, that cost 18 of 126 deconvolved
    multiplets (14%) their label: every one was forced to a generic "m" by gaps of
    0.21-0.49 Hz, which at 250-400 MHz is 5e-4 ppm -- far below any resolvable
    linewidth. nmrshiftdb2 40254842 (1,2-epoxybutane) at 0.984 ppm is the clearest
    case: seven lines spaced 6.99 / 0.32 / 0.29 / 0.24 / 0.21 / 6.95 Hz, which is
    the ethyl CH3 triplet with its centre transition tiled five ways.

    The survivor of a run is its CENTROID, not one of its members: the run has
    width, and taking an end member would bias the reported coupling by that
    width -- 1.06 Hz on the epoxybutane methyl, 14% of its 7.5 Hz coupling.

    Note the collapsed positions are used only to read the pattern. The resolved
    line list ``deconvolve_region`` returns is deliberately NOT changed: those
    extra components are not free, they measurably improve the fit (collapsing
    the epoxybutane pair and refitting raises the region's max residual to 1.9x
    the acceptance tolerance), so removing them would misreport how the region
    was actually modelled.
    """
    collapsed: list[float] = []
    run: list[float] = [ascending[0]]
    for center in ascending[1:]:
        if (center - run[-1]) * frequency < _MIN_J_HZ:
            run.append(center)
            continue
        collapsed.append(sum(run) / len(run))
        run = [center]
    collapsed.append(sum(run) / len(run))
    return collapsed


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

    Lines closer together than ``_MIN_J_HZ`` are first collapsed into one -- see
    :func:`_collapse_sub_coupling_runs` for why that is a statement about the
    lines and not a loosening of the J window.
    """
    finite = [float(center) for center in line_centers if math.isfinite(center)]
    if len(finite) <= 1:
        return ("s", ())
    if frequency_mhz is None or frequency_mhz <= 0:
        return ("m", ())
    frequency = float(frequency_mhz)
    ascending = _collapse_sub_coupling_runs(sorted(finite), frequency=frequency)
    line_count = len(ascending)
    if line_count <= 1:
        return ("s", ())
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
        # Bound the COUPLINGS, matching ``multiplet.analysis``. The window above
        # is applied to adjacent SPACINGS, and on a dd no adjacent spacing is a
        # coupling -- J_large is the sum of two of them. So J_large reached this
        # return unchecked, and a dd could report a coupling of up to twice
        # _MAX_J_HZ while every spacing it was read from sat inside the window.
        if _MIN_J_HZ <= j_small <= j_large <= _MAX_J_HZ:
            return ("dd", (round(j_large, 1), round(j_small, 1)))
    distinct = _distinct_spacings(spacings, tolerance)
    return ("m", tuple(sorted(distinct, reverse=True))[:3])
