"""Three standard region-integration methods for 1D NMR.

Prompt 5 — Integration methods
==============================

Quantitative NMR reports the *integral* of a resonance — the area under the
peak — which is proportional to the number of nuclei that give rise to it.
When an integration window is contaminated by solvent, residual water, or
impurity signals, a naive area sum over-counts.  This module exposes the three
standard integration strategies, plus a dispatcher that returns a
provenance-rich :class:`IntegrationResult`:

1. :func:`integrate_sum`        — classical trapezoidal area over the whole
                                  window (everything in it, contaminants
                                  included).  Equivalent terminology in the
                                  literature and in common NMR processing
                                  software: *Sum*.
2. :func:`integrate_edited_sum` — *edited-sum* method: scales the raw
                                  trapezoidal area by the fraction of total
                                  peak *height* that belongs to compound peaks,
                                  proportionally removing the solvent / impurity
                                  contribution.  A simple arithmetic
                                  relationship -- not proprietary; see the
                                  derivation below.
3. :func:`integrate_peaks`      — the sum of the *fitted* areas of the compound
                                  peaks only.  Most accurate when the GSD
                                  deconvolution fit is good and every
                                  contaminant peak is resolved.

Edited Sum formula
------------------

    Int(Edited) = Int(Sum) · ( Σ Ps_i / Σ P_i )

where ``Ps_i`` are the heights of the *compound* peaks in the window and
``P_i`` the heights of *all* peaks in the window.  A Lorentzian/Voigt area is
proportional to (height × linewidth), so when a contaminant shares the compound
linewidth the height ratio equals the area ratio and the formula recovers the
true compound integral exactly::

    Int(Sum) · Hc / (Hc + Hi) = (Ac + Ai) · Hc / (Hc + Hi) = Ac
    (because, at equal linewidth, Ai / Ac = Hi / Hc)

When linewidths differ the recovery is no longer exact but remains a robust,
first-order contaminant subtraction — far better than the raw sum and not
dependent on a per-peak fit the way :func:`integrate_peaks` is.

Axis orientation
----------------
``NMRSpectrum.ppm_axis`` is stored *descending* (high ppm first).  ``np.trapz``
over a descending abscissa returns a negative value; NMR integrals are reported
as positive magnitudes, so the trapezoidal result is taken in absolute value.

Confidence
----------
:class:`IntegrationResult.confidence` is a ``float`` in ``[0, 1]`` combining
(a) the signal-to-noise of the integrated area against the spectrum's baseline
noise and (b) the mean fit confidence of the compound peaks used — mirroring the
``0.x·snr_score + 0.y·fit_score`` convention in
``moltrace.spectroscopy.peaks.gsd``.  For Edited Sum it is additionally
discounted in proportion to how much area had to be subtracted (a large
contaminant fraction is a larger model extrapolation).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.peaks.gsd import Peak

# ``np.trapz`` was renamed to ``np.trapezoid`` in NumPy 2.0 and removed in a
# later release.  Bind whichever the installed NumPy provides so the module
# works across versions.
try:  # NumPy >= 2.0
    _np_trapezoid = np.trapezoid
except AttributeError:  # pragma: no cover - NumPy < 2.0
    _np_trapezoid = np.trapz  # type: ignore[attr-defined]

__all__ = [
    "IntegrationResult",
    "integrate",
    "integrate_edited_sum",
    "integrate_peaks",
    "integrate_sum",
]

# The one peak category that counts as analyte signal; everything else
# (``solvent`` / ``impurity`` / ``artifact`` / ``13C_satellite``) is a
# contaminant to be excluded or proportionally subtracted.
_COMPOUND: str = "compound"

_VALID_METHODS: tuple[str, ...] = ("sum", "edited_sum", "peaks")


@dataclass(slots=True, frozen=True)
class IntegrationResult:
    """The outcome of a region integration, with full provenance.

    Attributes
    ----------
    value:
        The integral (positive magnitude, in intensity·ppm units).
    method_used:
        One of ``"sum"``, ``"edited_sum"``, ``"peaks"``.
    peaks_used:
        The peaks that contributed signal to ``value``.  For ``edited_sum`` and
        ``peaks`` these are the compound peaks in the window; for ``sum`` it is
        every peak in the window (the raw sum counts them all).
    excluded_peaks:
        The contaminant peaks in the window removed from (or down-weighted in)
        the result.  Always empty for ``sum``.
    confidence:
        Quality score in ``[0, 1]`` from baseline SNR and peak-fit quality.
    """

    value: float
    method_used: str
    peaks_used: list[Peak]
    excluded_peaks: list[Peak]
    confidence: float


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _normalize_region(region_ppm: tuple[float, float]) -> tuple[float, float]:
    """Return ``(low, high)`` regardless of the order the caller supplied."""

    lo, hi = float(region_ppm[0]), float(region_ppm[1])
    return (lo, hi) if lo <= hi else (hi, lo)


def _region_arrays(
    spectrum: NMRSpectrum, lo: float, hi: float
) -> tuple[np.ndarray, np.ndarray]:
    """Slice the spectrum to ``[lo, hi]`` ppm (inclusive)."""

    ppm = np.asarray(spectrum.ppm_axis, dtype=float)
    data = np.asarray(spectrum.data, dtype=float)
    mask = (ppm >= lo) & (ppm <= hi)
    return ppm[mask], data[mask]


def _peaks_in_region(peaks: list[Peak], lo: float, hi: float) -> list[Peak]:
    return [p for p in peaks if lo <= float(p.position_ppm) <= hi]


def _trapz_magnitude(ppm_region: np.ndarray, y_region: np.ndarray) -> float:
    """Trapezoidal area over the region, as a positive magnitude.

    ``ppm_axis`` is descending so ``np.trapz`` returns a negative number; the
    absolute value is the integral.  Matches the ``np.trapz`` area convention in
    ``moltrace.spectroscopy.peaks.gsd``.
    """

    if ppm_region.size < 2:
        return 0.0
    return float(abs(_np_trapezoid(y_region, x=ppm_region)))


def _median_step(ppm_region: np.ndarray) -> float:
    if ppm_region.size < 2:
        return 1.0
    return float(np.median(np.abs(np.diff(ppm_region))))


def _baseline_noise(spectrum: NMRSpectrum) -> float:
    """Robust per-point baseline noise via the median absolute deviation.

    On a (baseline-corrected) spectrum the real peaks occupy a small fraction of
    the points, so the median is the baseline and ``σ ≈ 1.4826·MAD(y − median)``
    recovers the noise amplitude while shrugging off the sparse peaks — the
    standard robust NMR noise estimate.  Unlike a first-difference estimator it
    measures *correlated* (apodised / line-broadened) baseline noise correctly,
    since differencing would cancel the low-frequency component such noise
    carries.
    """

    data = np.asarray(spectrum.data, dtype=float)
    if data.size < 2:
        return 1e-12
    mad = float(np.median(np.abs(data - np.median(data))))
    sigma = 1.4826 * mad
    return max(sigma, 1e-12)


def _confidence(
    *,
    value: float,
    spectrum: NMRSpectrum,
    region: tuple[float, float],
    compound_peaks: list[Peak],
    compound_fraction: float,
    method: str,
) -> float:
    """Score the integral in ``[0, 1]`` from baseline SNR and peak-fit quality."""

    lo, hi = region
    ppm_region, _ = _region_arrays(spectrum, lo, hi)
    noise = _baseline_noise(spectrum)

    # Std of the trapezoidal integral of white noise across the window:
    # σ · Δppm · √N.  The integrated-area SNR is the area over that.
    n_points = max(int(ppm_region.size), 1)
    noise_area = noise * _median_step(ppm_region) * math.sqrt(n_points)
    snr = abs(value) / max(noise_area, 1e-12)
    snr_score = min(1.0, math.log1p(max(0.0, snr)) / math.log(101.0))

    if compound_peaks:
        fit_score = float(
            np.mean([min(max(float(p.confidence), 0.0), 1.0) for p in compound_peaks])
        )
    else:
        # ``sum`` carries no per-peak fit model — stay neutral on that axis.
        fit_score = 0.5

    score = 0.6 * snr_score + 0.4 * fit_score

    if method == "edited_sum":
        # Subtracting a large contaminant fraction is a bigger extrapolation;
        # discount confidence by up to 25 % as the compound fraction → 0.
        score *= 1.0 - 0.25 * (1.0 - min(max(compound_fraction, 0.0), 1.0))

    return round(max(0.0, min(1.0, score)), 4)


# --------------------------------------------------------------------------- #
# The three integration methods
# --------------------------------------------------------------------------- #
def integrate_sum(spectrum: NMRSpectrum, region_ppm: tuple[float, float]) -> float:
    """Classical trapezoidal integration over the region.

    Sums everything in the window — analyte, solvent, and impurity alike.
    """

    lo, hi = _normalize_region(region_ppm)
    ppm_region, y_region = _region_arrays(spectrum, lo, hi)
    return _trapz_magnitude(ppm_region, y_region)


def integrate_edited_sum(
    spectrum: NMRSpectrum,
    region_ppm: tuple[float, float],
    classified_peaks: list[Peak],
) -> float:
    """Edited-sum formula -- a simple arithmetic relationship, not proprietary.

        Int(Edited) = Int(Sum) · ( Σ Ps_i / Σ P_i )

    where ``Ps_i`` are the heights of compound peaks only and ``P_i`` the
    heights of ALL peaks in the region.  Subtracts solvent and impurity
    contribution proportionally.

    With no classified peaks in the window there is nothing to discriminate, so
    the raw sum is returned unchanged (the honest fallback).
    """

    lo, hi = _normalize_region(region_ppm)
    int_sum = integrate_sum(spectrum, (lo, hi))

    region_peaks = _peaks_in_region(classified_peaks, lo, hi)
    total_height = sum(max(float(p.intensity), 0.0) for p in region_peaks)
    if total_height <= 0.0:
        return int_sum

    compound_height = sum(
        max(float(p.intensity), 0.0)
        for p in region_peaks
        if p.category == _COMPOUND
    )
    return int_sum * (compound_height / total_height)


def integrate_peaks(
    spectrum: NMRSpectrum,
    region_ppm: tuple[float, float],
    peaks: list[Peak],
) -> float:
    """Sum of fitted peak areas for compound peaks only.

    Most accurate when the GSD fit is good.  ``spectrum`` is accepted for
    signature symmetry with the other methods (the areas are already fitted);
    only the region bounds are used, to select which peaks belong to the window.
    """

    lo, hi = _normalize_region(region_ppm)
    region_peaks = _peaks_in_region(peaks, lo, hi)
    return float(
        sum(
            max(float(p.area), 0.0)
            for p in region_peaks
            if p.category == _COMPOUND
        )
    )


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #
def integrate(
    spectrum: NMRSpectrum,
    region_ppm: tuple[float, float],
    peaks: list[Peak],
    method: str = "edited_sum",
) -> IntegrationResult:
    """Dispatch to one of the three integration methods, with provenance.

    Parameters
    ----------
    spectrum:
        The processed spectrum (descending ppm axis).
    region_ppm:
        The integration window ``(a, b)``; order-insensitive.
    peaks:
        Classified peaks (``category`` distinguishes ``"compound"`` from
        solvent / impurity / artifact / satellite).
    method:
        ``"sum"`` | ``"edited_sum"`` (default) | ``"peaks"``.

    Returns
    -------
    IntegrationResult
        ``value``, ``method_used``, ``peaks_used``, ``excluded_peaks``,
        ``confidence``.
    """

    if method not in _VALID_METHODS:
        raise ValueError(
            f"Unknown integration method {method!r}; "
            f"expected one of {_VALID_METHODS}."
        )

    lo, hi = _normalize_region(region_ppm)
    region_peaks = _peaks_in_region(peaks, lo, hi)
    compound_peaks = [p for p in region_peaks if p.category == _COMPOUND]
    contaminant_peaks = [p for p in region_peaks if p.category != _COMPOUND]

    total_height = sum(max(float(p.intensity), 0.0) for p in region_peaks)
    compound_height = sum(max(float(p.intensity), 0.0) for p in compound_peaks)
    compound_fraction = (
        compound_height / total_height if total_height > 0.0 else 1.0
    )

    if method == "sum":
        value = integrate_sum(spectrum, (lo, hi))
        peaks_used = list(region_peaks)  # the raw sum counts every peak
        excluded_peaks: list[Peak] = []
    elif method == "edited_sum":
        value = integrate_edited_sum(spectrum, (lo, hi), peaks)
        peaks_used = list(compound_peaks)
        excluded_peaks = list(contaminant_peaks)
    else:  # "peaks"
        value = integrate_peaks(spectrum, (lo, hi), peaks)
        peaks_used = list(compound_peaks)
        excluded_peaks = list(contaminant_peaks)

    confidence = _confidence(
        value=value,
        spectrum=spectrum,
        region=(lo, hi),
        compound_peaks=compound_peaks,
        compound_fraction=compound_fraction,
        method=method,
    )

    return IntegrationResult(
        value=value,
        method_used=method,
        peaks_used=peaks_used,
        excluded_peaks=excluded_peaks,
        confidence=confidence,
    )
