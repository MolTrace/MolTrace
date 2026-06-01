"""Prompt 5 — validation of the three Mnova-equivalent integration methods.

Headline gate
-------------
On synthetic spectra with known impurity *area* fractions of **5 %, 10 %, and
25 %**, :func:`integrate_edited_sum` recovers the true compound integral to
within **1 % relative error**.  When the contaminant shares the compound
linewidth — the regime the Edited Sum formula assumes, since a Lorentzian area
is proportional to (height × width) — the recovery is exact to machine
precision; under realistic correlated baseline noise (SNR ≈ 600) it stays
comfortably below 1 %.

Construction
------------
Each fixture is a sum of Lorentzian lines ``h·w² / ((δ−c)² + w²)`` on a
descending ppm axis (matching ``NMRSpectrum``).  For an impurity area fraction
``f`` with equal linewidth, the impurity height is ``f/(1−f)`` of the compound
height, so that ``Aᵢ/(A_c+Aᵢ) = Hᵢ/(H_c+Hᵢ) = f``.  The ground-truth compound
integral is the trapezoidal area of the *compound-only* contribution over the
same window, so the comparison isolates the contaminant-removal — not window
truncation, which is common-mode.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter1d

from moltrace.spectroscopy.integration.methods import (
    IntegrationResult,
    integrate,
    integrate_edited_sum,
    integrate_peaks,
    integrate_sum,
)
from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.peaks.gsd import Peak

FIELD_MHZ = 500.0
PPM_HI, PPM_LO, N_POINTS = 4.0, 0.0, 60_001
REGION = (0.5, 2.5)
HWHM_PPM = 0.004  # ≈ 4 Hz FWHM at 500 MHz
COMPOUND_CENTER = 1.3
IMPURITY_CENTER = 1.7
SOLVENT_CENTER = 2.1

_PPM_AXIS = np.linspace(PPM_HI, PPM_LO, N_POINTS)  # descending, like NMRSpectrum


# --------------------------------------------------------------------------- #
# Synthetic-spectrum helpers
# --------------------------------------------------------------------------- #
def _lorentzian(center: float, height: float, hwhm: float = HWHM_PPM) -> np.ndarray:
    return height * hwhm * hwhm / ((_PPM_AXIS - center) ** 2 + hwhm * hwhm)


def _spectrum(intensity: np.ndarray, *, noise_std: float = 0.0, seed: int = 0) -> NMRSpectrum:
    y = np.array(intensity, dtype=float)
    if noise_std > 0.0:
        rng = np.random.default_rng(seed)
        raw = rng.normal(0.0, noise_std, size=y.size)
        correlated = gaussian_filter1d(raw, sigma=2.0, mode="nearest")
        realized = float(np.std(correlated)) or 1.0
        y = y + correlated * (noise_std / realized)
    return NMRSpectrum(
        data=y,
        ppm_axis=_PPM_AXIS,
        metadata={"source": "test_integration_methods"},
        nucleus="1H",
        solvent="CDCl3",
        field_mhz=FIELD_MHZ,
    )


def _peak(
    center: float, height: float, area: float, category: str, *, hwhm: float = HWHM_PPM
) -> Peak:
    return Peak(
        position_ppm=center,
        position_hz=center * FIELD_MHZ,
        intensity=height,
        area=area,
        width_hz=2.0 * hwhm * FIELD_MHZ,
        shape="lorentzian",
        category=category,
        confidence=0.95,
    )


def _mixture(
    impurity_fraction: float,
    *,
    compound_height: float = 1.0,
    noise_std: float = 0.0,
    seed: int = 0,
) -> tuple[NMRSpectrum, list[Peak], float]:
    """Build a compound+impurity fixture with a known impurity area fraction.

    Returns ``(spectrum, classified_peaks, true_compound_integral)``.
    """

    impurity_height = impurity_fraction / (1.0 - impurity_fraction) * compound_height
    compound_only = _lorentzian(COMPOUND_CENTER, compound_height)
    impurity_only = _lorentzian(IMPURITY_CENTER, impurity_height)

    true_compound = integrate_sum(_spectrum(compound_only), REGION)
    impurity_area = integrate_sum(_spectrum(impurity_only), REGION)

    spectrum = _spectrum(compound_only + impurity_only, noise_std=noise_std, seed=seed)
    peaks = [
        _peak(COMPOUND_CENTER, compound_height, true_compound, "compound"),
        _peak(IMPURITY_CENTER, impurity_height, impurity_area, "impurity"),
    ]
    return spectrum, peaks, true_compound


# --------------------------------------------------------------------------- #
# Headline gate: edited_sum recovers the true compound integral within 1 %
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("impurity_fraction", [0.05, 0.10, 0.25])
def test_edited_sum_recovers_true_compound_noiseless(impurity_fraction: float) -> None:
    spectrum, peaks, true_compound = _mixture(impurity_fraction)
    edited = integrate_edited_sum(spectrum, REGION, peaks)
    rel_err = abs(edited - true_compound) / true_compound
    assert rel_err < 0.01  # the documented gate
    assert rel_err < 1e-6  # equal-linewidth Edited Sum is exact to ~machine eps


@pytest.mark.parametrize("impurity_fraction", [0.05, 0.10, 0.25])
def test_edited_sum_within_1pct_under_realistic_noise(impurity_fraction: float) -> None:
    # Correlated baseline noise at SNR ≈ 600 on the compound peak height.
    spectrum, peaks, true_compound = _mixture(
        impurity_fraction, noise_std=1.0 / 600.0, seed=20_260_531
    )
    edited = integrate_edited_sum(spectrum, REGION, peaks)
    rel_err = abs(edited - true_compound) / true_compound
    assert rel_err < 0.01, f"f={impurity_fraction:.0%}: rel_err={rel_err:.4%}"


# --------------------------------------------------------------------------- #
# The other two methods behave as specified
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("impurity_fraction", [0.05, 0.10, 0.25])
def test_raw_sum_overcounts_by_the_impurity_fraction(impurity_fraction: float) -> None:
    spectrum, _peaks, true_compound = _mixture(impurity_fraction)
    raw = integrate_sum(spectrum, REGION)
    # The raw sum counts the impurity too: Int(Sum) = true_compound / (1 − f).
    assert abs(raw - true_compound / (1.0 - impurity_fraction)) / raw < 1e-6
    assert raw > true_compound  # strictly over-counts


@pytest.mark.parametrize("impurity_fraction", [0.05, 0.10, 0.25])
def test_integrate_peaks_sums_compound_areas_only(impurity_fraction: float) -> None:
    spectrum, peaks, true_compound = _mixture(impurity_fraction)
    value = integrate_peaks(spectrum, REGION, peaks)
    assert abs(value - true_compound) / true_compound < 1e-9  # exact compound-area sum


# --------------------------------------------------------------------------- #
# Dispatcher: provenance, default method, routing, validation
# --------------------------------------------------------------------------- #
def test_dispatcher_defaults_to_edited_sum_with_provenance() -> None:
    spectrum, peaks, true_compound = _mixture(0.25)
    result = integrate(spectrum, REGION, peaks)  # default method
    assert isinstance(result, IntegrationResult)
    assert result.method_used == "edited_sum"
    assert abs(result.value - true_compound) / true_compound < 0.01
    assert [p.category for p in result.peaks_used] == ["compound"]
    assert [p.category for p in result.excluded_peaks] == ["impurity"]
    assert 0.0 <= result.confidence <= 1.0


def test_dispatcher_sum_counts_all_peaks_and_excludes_none() -> None:
    spectrum, peaks, _true = _mixture(0.25)
    result = integrate(spectrum, REGION, peaks, method="sum")
    assert result.method_used == "sum"
    assert result.excluded_peaks == []
    assert len(result.peaks_used) == 2
    assert result.value == integrate_sum(spectrum, REGION)


def test_dispatcher_peaks_method_matches_helper() -> None:
    spectrum, peaks, true_compound = _mixture(0.10)
    result = integrate(spectrum, REGION, peaks, method="peaks")
    assert result.method_used == "peaks"
    assert abs(result.value - true_compound) / true_compound < 1e-9
    assert [p.category for p in result.excluded_peaks] == ["impurity"]


def test_unknown_method_raises() -> None:
    spectrum, peaks, _true = _mixture(0.10)
    with pytest.raises(ValueError):
        integrate(spectrum, REGION, peaks, method="bogus")


# --------------------------------------------------------------------------- #
# Contaminant handling: solvent + impurity, out-of-region, empty, mismatch
# --------------------------------------------------------------------------- #
def test_solvent_and_impurity_both_excluded_by_edited_sum() -> None:
    compound_only = _lorentzian(COMPOUND_CENTER, 1.0)
    impurity_only = _lorentzian(IMPURITY_CENTER, 0.15)
    solvent_only = _lorentzian(SOLVENT_CENTER, 0.20)
    true_compound = integrate_sum(_spectrum(compound_only), REGION)
    spectrum = _spectrum(compound_only + impurity_only + solvent_only)
    peaks = [
        _peak(COMPOUND_CENTER, 1.0, true_compound, "compound"),
        _peak(IMPURITY_CENTER, 0.15, integrate_sum(_spectrum(impurity_only), REGION), "impurity"),
        _peak(SOLVENT_CENTER, 0.20, integrate_sum(_spectrum(solvent_only), REGION), "solvent"),
    ]
    result = integrate(spectrum, REGION, peaks)  # edited_sum
    assert abs(result.value - true_compound) / true_compound < 0.01
    assert {p.category for p in result.excluded_peaks} == {"impurity", "solvent"}
    assert [p.category for p in result.peaks_used] == ["compound"]
    # integrate_peaks recovers the compound area regardless of contaminants.
    assert abs(integrate_peaks(spectrum, REGION, peaks) - true_compound) / true_compound < 1e-9


def test_peaks_outside_the_region_are_ignored() -> None:
    compound_only = _lorentzian(COMPOUND_CENTER, 1.0)
    true_compound = integrate_sum(_spectrum(compound_only), REGION)
    spectrum = _spectrum(compound_only)  # only the compound sits inside the window
    inside = _peak(COMPOUND_CENTER, 1.0, true_compound, "compound")
    outside = _peak(3.5, 0.5, 0.001, "impurity")  # 3.5 ppm is outside (0.5, 2.5)
    edited = integrate_edited_sum(spectrum, REGION, [inside, outside])
    assert abs(edited - true_compound) / true_compound < 1e-9  # out-of-window peak ignored


def test_edited_sum_falls_back_to_raw_sum_without_classified_peaks() -> None:
    spectrum, _peaks, _true = _mixture(0.10)
    assert integrate_edited_sum(spectrum, REGION, []) == integrate_sum(spectrum, REGION)


def test_region_order_is_insensitive() -> None:
    spectrum, _peaks, _true = _mixture(0.10)
    assert integrate_sum(spectrum, (2.5, 0.5)) == integrate_sum(spectrum, (0.5, 2.5))


def test_edited_sum_beats_raw_sum_with_mismatched_linewidth() -> None:
    # When the impurity is broader, the height ratio no longer equals the area
    # ratio, so Edited Sum is not exact — but it still corrects most of the
    # contamination, and integrate_peaks recovers the area exactly.
    compound_only = _lorentzian(COMPOUND_CENTER, 1.0, HWHM_PPM)
    impurity_only = _lorentzian(IMPURITY_CENTER, 0.2, 2.0 * HWHM_PPM)
    true_compound = integrate_sum(_spectrum(compound_only), REGION)
    spectrum = _spectrum(compound_only + impurity_only)
    peaks = [
        _peak(COMPOUND_CENTER, 1.0, true_compound, "compound", hwhm=HWHM_PPM),
        _peak(
            IMPURITY_CENTER,
            0.2,
            integrate_sum(_spectrum(impurity_only), REGION),
            "impurity",
            hwhm=2.0 * HWHM_PPM,
        ),
    ]
    raw_err = abs(integrate_sum(spectrum, REGION) - true_compound) / true_compound
    edited_err = abs(integrate_edited_sum(spectrum, REGION, peaks) - true_compound) / true_compound
    assert edited_err < raw_err  # Edited Sum still improves on the raw sum
    assert abs(integrate_peaks(spectrum, REGION, peaks) - true_compound) / true_compound < 1e-9


# --------------------------------------------------------------------------- #
# Confidence behaviour
# --------------------------------------------------------------------------- #
def test_confidence_decreases_with_baseline_noise() -> None:
    clean_spectrum, peaks, _true = _mixture(0.10)
    noisy_spectrum, noisy_peaks, _true2 = _mixture(0.10, noise_std=1.0 / 30.0, seed=7)
    clean = integrate(clean_spectrum, REGION, peaks)
    noisy = integrate(noisy_spectrum, REGION, noisy_peaks)
    assert 0.0 <= noisy.confidence <= 1.0
    assert noisy.confidence < clean.confidence


def test_confidence_discounts_larger_contaminant_subtraction() -> None:
    # Edited Sum over a heavily-contaminated window should be less confident
    # than over a lightly-contaminated one (same baseline noise).
    light_spec, light_peaks, _t1 = _mixture(0.05)
    heavy_spec, heavy_peaks, _t2 = _mixture(0.25)
    light = integrate(light_spec, REGION, light_peaks)
    heavy = integrate(heavy_spec, REGION, heavy_peaks)
    assert heavy.confidence < light.confidence
