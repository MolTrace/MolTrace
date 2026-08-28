"""Separating lines that sit closer than one maximum apart.

**The problem this solves.** A peak finder reports one maximum per resolvable
feature, so two lines closer than about four linewidths come back as a single
signal — measured, on planted pairs, at every field. Below that separation there
is genuinely one apex to find, and no threshold, smoothing window or minimum-
separation floor recovers the second line. Three of those were tried and
measured; none is the constraint.

**Why the existing group fit does not solve it.** `gsd._fit_peak_groups` fits the
maxima it was HANDED. It has no opinion about how many lines are really there, so
raising sensitivity to find more candidates is the only way to get more
components — which is why level 3 returned 21 components for two planted lines at
4,096 points and 37 at 8,192. That is a detection change wearing a fitting
change's clothes.

**What is actually missing is model selection.** Asking "do two Lorentzians
explain this better than one?" is a statistical question with a real answer, and
it became answerable only once the noise estimate was unbiased: the old 13C
estimator read 0.59x the true sigma, and a test against a noise level that is
itself wrong by 40% decides nothing.

So: fit one component, then two, then three, and accept the extra one only when
the residual falls by more than noise alone can explain. A component costs three
parameters, so under the null hypothesis that it is spurious the sum of squares
drops by about 3 sigma-squared; requiring far more than that is what stops this
becoming level 3 again.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: How much the residual sum of squares must fall, in units of the noise
#: variance, before an extra component is believed.
#:
#: A component adds three free parameters, so a spurious one still reduces the
#: sum of squares by about 3 sigma-squared by chance alone. This is the 99.9th
#: percentile of chi-squared with 3 degrees of freedom, so a component is
#: accepted only when the improvement would arise by chance about once in a
#: thousand regions. Deliberately strict: the failure this replaces was a fit
#: that invented components, and a second line reported where there is one is a
#: coupling constant a chemist will try to explain.
_CHI2_3DOF_P999 = 16.27

#: How far above the noise a component must stand to be a line. The conventional
#: limit of detection, and the same floor the peak detector applies — a
#: deconvolution that reports lines the detector would not is reporting noise.
_MIN_COMPONENT_SIGMA = 3.0


@dataclass(frozen=True)
class Component:
    """One line recovered from a region, in the units a chemist reads."""

    position_ppm: float
    height: float
    fwhm_hz: float


def _lorentzian(x_hz: np.ndarray, centre_hz: float, fwhm_hz: float, height: float) -> np.ndarray:
    half = max(fwhm_hz, 1e-9) / 2.0
    return height * (half * half) / ((x_hz - centre_hz) ** 2 + half * half)


def _model(x_hz: np.ndarray, params: np.ndarray) -> np.ndarray:
    out = np.zeros_like(x_hz)
    for i in range(0, len(params), 3):
        out += _lorentzian(x_hz, params[i], params[i + 1], params[i + 2])
    return out


def _fit(
    x_hz: np.ndarray, y: np.ndarray, seeds: list[tuple[float, float, float]], min_fwhm_hz: float
):
    """Least squares over (centre, fwhm, height) per component. Returns (params, rss).

    **The lower bound on width is load-bearing.** Left at an arbitrarily small
    number, least squares discovers that an infinitely narrow Lorentzian fits any
    single noise sample exactly, so every extra component converges to a spike:
    measured, a third component at **0.01 Hz** appeared on well-separated pairs
    whose two real lines had already been recovered at their true width. The
    residual drop is real, so no model-selection threshold rejects it — the model
    itself has to exclude the shape.

    A line cannot be narrower than the sampling that recorded it.
    """
    from scipy.optimize import least_squares

    p0 = np.array([v for seed in seeds for v in seed], dtype=float)
    span = float(x_hz.max() - x_hz.min()) or 1.0
    lower, upper = [], []
    for i in range(0, len(p0), 3):
        p0[i + 1] = max(p0[i + 1], min_fwhm_hz * 1.01)
        lower += [float(x_hz.min()) - span, min_fwhm_hz, 0.0]
        upper += [float(x_hz.max()) + span, span, np.inf]

    try:
        fit = least_squares(
            lambda p: _model(x_hz, p) - y,
            p0,
            bounds=(lower, upper),
            max_nfev=2000,
        )
    except Exception:  # noqa: BLE001 - a fit that will not converge is not a component
        return None, float("inf")
    return fit.x, float(np.sum((_model(x_hz, fit.x) - y) ** 2))


def _seed(
    x_hz: np.ndarray,
    y: np.ndarray,
    count: int,
    *,
    apex: int,
    width0: float,
    height0: float,
) -> list[tuple[float, float, float]]:
    """Starting positions for `count` components.

    **Seeded from the structure that is actually there.** A symmetric spread
    around the apex is a guess, and least squares is entitled to find the nearest
    local minimum to whatever it is handed. Measured: at three linewidths apart
    the two-component fit seeded that way converged to 172 units at 4.0 Hz beside
    50 units at 9.2 Hz — instead of the two 200-unit, 3.23 Hz lines that are
    there — and the residual it left behind then justified a third component. The
    model selection was working correctly on a fit that had gone wrong.

    So the shoulders and humps the region already shows are used first, and the
    symmetric spread is only the fallback when there are not enough of them.
    """
    from scipy.signal import find_peaks

    found, properties = find_peaks(y, prominence=(np.nanmax(y) - np.nanmin(y)) * 0.01)
    if found.size >= count:
        order = np.argsort(properties["prominences"])[::-1][:count]
        chosen = np.sort(found[order])
        return [
            (float(x_hz[i]), max(width0 / max(count, 1), 1e-6), max(float(y[i]), 1e-9))
            for i in chosen
        ]

    centres = np.linspace(
        float(x_hz[apex]) - width0 * (count - 1) / 2.0,
        float(x_hz[apex]) + width0 * (count - 1) / 2.0,
        count,
    )
    return [(float(c), width0 / max(count, 1), height0 / count) for c in centres]


def resolve_region(
    x_ppm: np.ndarray,
    y: np.ndarray,
    *,
    field_mhz: float,
    noise_sigma: float,
    max_components: int = 3,
) -> list[Component]:
    """How many lines are really in this region, and where.

    Returns one component per line it can justify. One component is the answer
    unless a second earns its place.
    """
    x_ppm = np.asarray(x_ppm, dtype=float)
    y = np.asarray(y, dtype=float)
    if x_ppm.size < 8 or not math.isfinite(noise_sigma) or noise_sigma <= 0 or field_mhz <= 0:
        return []

    x_hz = x_ppm * field_mhz
    variance = noise_sigma * noise_sigma

    apex = int(np.argmax(y))
    height0 = float(y[apex])
    if height0 <= 0:
        return []
    # A starting width from the region itself rather than a constant: half the
    # span is wrong for a narrow line in a wide window and vice versa.
    above_half = np.count_nonzero(y >= height0 / 2.0)
    step_hz = float(np.median(np.abs(np.diff(x_hz)))) or 1.0
    width0 = max(above_half * step_hz, step_hz * 2.0)
    # Two samples is the narrowest thing that can be said to have a width at all.
    min_fwhm_hz = step_hz * 2.0

    best: list[Component] = []
    previous_rss = float("inf")
    for count in range(1, max_components + 1):
        seeds = _seed(x_hz, y, count, apex=apex, width0=width0, height0=height0)
        params, rss = _fit(x_hz, y, seeds, min_fwhm_hz)
        if params is None:
            break

        if count == 1:
            previous_rss = rss
            best = _components(params, field_mhz)
            continue

        improvement = (previous_rss - rss) / variance
        if improvement < _CHI2_3DOF_P999:
            break

        # A component that does not clear the noise is not a line, however much
        # it improves the arithmetic. Same floor the detector uses.
        candidate = _components(params, field_mhz)
        if any(component.height < noise_sigma * _MIN_COMPONENT_SIGMA for component in candidate):
            break

        previous_rss = rss
        best = candidate

    return best


def _components(params: np.ndarray, field_mhz: float) -> list[Component]:
    out = []
    for i in range(0, len(params), 3):
        out.append(
            Component(
                position_ppm=float(params[i] / field_mhz),
                fwhm_hz=float(params[i + 1]),
                height=float(params[i + 2]),
            )
        )
    return sorted(out, key=lambda c: -c.height)
