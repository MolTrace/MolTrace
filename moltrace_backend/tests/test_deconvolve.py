"""Separating lines the peak detector reports as one.

The detector recovers two lines separately only from about four linewidths
apart — below that there is one apex to find. This stage asks a different
question of the same data: do two Lorentzians explain this region better than
one can, by more than noise allows?

**Both directions are tested, and the second one is the hard one.** Splitting a
close pair is easy if you are willing to split everything; the whole difficulty
is not splitting a single line. A spurious second line is a coupling constant a
chemist will try to explain.
"""

from __future__ import annotations

import numpy as np
import pytest

from moltrace.spectroscopy.peaks.deconvolve import resolve_region

_FIELD_MHZ = 150.9
_FWHM_HZ = 3.23


def _region(separation_widths: float | None, seed: int, *, height: float = 200.0, points: int = 400):
    """A window holding one line, or two a given number of linewidths apart."""
    centre = 60.0
    half_window_hz = _FWHM_HZ * 8
    hz = np.linspace(centre * _FIELD_MHZ - half_window_hz, centre * _FIELD_MHZ + half_window_hz, points)
    ppm = hz / _FIELD_MHZ
    y = np.random.default_rng(seed).normal(0.0, 1.0, points)
    centres = [centre] if separation_widths is None else [
        centre,
        centre + (separation_widths * _FWHM_HZ) / _FIELD_MHZ,
    ]
    for c in centres:
        half = _FWHM_HZ / 2
        y += height * (half * half) / ((hz - c * _FIELD_MHZ) ** 2 + half * half)
    return ppm, y, centres


def test_one_line_is_not_split_into_two() -> None:
    """The failure that matters. Measured 40/40 across seeds."""
    for seed in range(20):
        ppm, y, _ = _region(None, 5000 + seed)
        components = resolve_region(ppm, y, field_mhz=_FIELD_MHZ, noise_sigma=1.0)
        assert len(components) == 1, (
            f"a single line was reported as {len(components)} — a spurious second line is a "
            "coupling a chemist will try to explain"
        )


@pytest.mark.parametrize("separation", [1.0, 1.5, 2.0, 3.0])
def test_a_pair_the_detector_merges_is_recovered(separation: float) -> None:
    """Below about four linewidths the detector reports one maximum. These are
    the separations it cannot reach, and they are recovered here."""
    found = 0
    for seed in range(8):
        ppm, y, centres = _region(separation, 6000 + seed)
        components = resolve_region(ppm, y, field_mhz=_FIELD_MHZ, noise_sigma=1.0)
        if len(components) == len(centres):
            found += 1
    assert found >= 7, f"only {found}/8 pairs at {separation} linewidths were separated"


def test_recovered_positions_are_where_the_lines_actually_are() -> None:
    """Splitting into the right NUMBER in the wrong PLACES is not a result."""
    ppm, y, centres = _region(2.0, 7001)
    components = resolve_region(ppm, y, field_mhz=_FIELD_MHZ, noise_sigma=1.0)
    assert len(components) == 2
    for truth in centres:
        nearest = min(abs(c.position_ppm - truth) for c in components) * _FIELD_MHZ
        assert nearest < _FWHM_HZ / 2, f"a recovered line sits {nearest:.2f} Hz from any real one"


@pytest.mark.parametrize("gaussian_fraction", [0.0, 0.3, 0.6, 0.8])
def test_a_real_lineshape_is_not_split_into_two(gaussian_fraction: float) -> None:
    """The false positive a Lorentzian-only corpus cannot see.

    A real NMR line is a Voigt — Lorentzian broadened by a Gaussian from
    shimming — and two Lorentzians fit a Voigt better than one does. If the
    selection rule cannot tell that apart from a genuine pair, every well-shimmed
    peak in a spectrum becomes two lines and the feature is worse than useless.

    Suspected after real acquisitions split NARROW signals while leaving wide ones
    alone, which is the opposite of what a merged pair looks like. Measured here
    across the full range of Gaussian character: one line, every time — so
    lineshape is not that mechanism, and those splits may be real.

    HONEST LIMIT OF THIS GUARD: no weakening tried so far turns it red. The other
    checks reach the same case first, so it is not demonstrated to discriminate;
    it is not vacuous either, since the tests above require two components for a
    genuine pair. Treat it as a regression guard against a future rule that
    splits more eagerly, not as evidence the current one is safe.
    """
    from scipy.special import wofz

    centre = 60.0
    half_window_hz = _FWHM_HZ * 8
    hz = np.linspace(
        centre * _FIELD_MHZ - half_window_hz, centre * _FIELD_MHZ + half_window_hz, 400
    )
    ppm = hz / _FIELD_MHZ
    y = np.random.default_rng(9600).normal(0.0, 1.0, 400)

    sigma = (gaussian_fraction * _FWHM_HZ) / (2 * np.sqrt(2 * np.log(2))) or 1e-9
    gamma = ((1.0 - gaussian_fraction) * _FWHM_HZ) / 2
    z = ((hz - centre * _FIELD_MHZ) + 1j * gamma) / (sigma * np.sqrt(2))
    profile = np.real(wofz(z))
    y += 200.0 * profile / profile.max()

    components = resolve_region(ppm, y, field_mhz=_FIELD_MHZ, noise_sigma=1.0)
    assert len(components) == 1, (
        f"a single line with {gaussian_fraction:.0%} Gaussian character was reported as "
        f"{len(components)} lines — every well-shimmed peak would become two"
    )


def test_a_partner_below_the_noise_is_not_reported() -> None:
    """The height floor, made visible.

    A pair where the second line is genuinely below the detection limit has ONE
    reportable line, and saying two is inventing a signal. This is the case that
    exercises the floor: the end-to-end tests above never produce a sub-noise
    component, so they cannot see whether the floor exists — measured, deleting
    it left every one of them green.
    """
    centre = 60.0
    half_window_hz = _FWHM_HZ * 8
    hz = np.linspace(
        centre * _FIELD_MHZ - half_window_hz, centre * _FIELD_MHZ + half_window_hz, 400
    )
    ppm = hz / _FIELD_MHZ
    y = np.random.default_rng(8100).normal(0.0, 1.0, 400)
    half = _FWHM_HZ / 2
    # One real line, and a partner at 1.5 sigma — under any limit of detection.
    for c, height in ((centre, 200.0), (centre + (2.0 * _FWHM_HZ) / _FIELD_MHZ, 1.5)):
        y += height * (half * half) / ((hz - c * _FIELD_MHZ) ** 2 + half * half)

    components = resolve_region(ppm, y, field_mhz=_FIELD_MHZ, noise_sigma=1.0)
    assert len(components) == 1, (
        f"a partner at 1.5 sigma was reported as a line ({len(components)} components) — "
        "that is a signal invented below the noise"
    )


def test_the_fit_cannot_return_a_line_narrower_than_the_sampling() -> None:
    """The width bound, tested DIRECTLY.

    An arbitrarily narrow Lorentzian fits one noise sample exactly, and least
    squares will find it: measured at 0.01 Hz beside two correctly recovered
    lines, before the region was seeded from its own structure. Better seeding
    made that rare, which also made it invisible to the end-to-end tests — they
    stayed green with the bound removed. So the bound is asserted where it is
    applied.
    """
    from moltrace.spectroscopy.peaks.deconvolve import _fit

    # PURE NOISE, which is the case the bound defends. Given real line data the
    # fit finds the real width whatever the bound allows, so line data cannot see
    # this guard — measured, the end-to-end tests stayed green without it. With
    # only noise, the best-fitting Lorentzian genuinely IS a spike on the tallest
    # sample, and nothing but the bound stops the fit going there.
    hz = np.linspace(60.0 * _FIELD_MHZ - 25.0, 60.0 * _FIELD_MHZ + 25.0, 400)
    y = np.random.default_rng(8200).normal(0.0, 1.0, 400)
    step_hz = float(np.median(np.abs(np.diff(hz))))
    min_fwhm = step_hz * 2.0
    apex = int(np.argmax(y))
    params, _rss = _fit(hz, y, [(float(hz[apex]), step_hz * 1e-3, float(y[apex]))], min_fwhm)
    assert params is not None
    for i in range(0, len(params), 3):
        assert params[i + 1] >= min_fwhm * 0.999, (
            f"the fit returned a {params[i + 1]:.4f} Hz line against a {min_fwhm:.4f} Hz floor"
        )


def test_no_component_is_narrower_than_the_sampling() -> None:
    """The degenerate fit this stage had to be defended against.

    An arbitrarily narrow Lorentzian fits a single noise sample exactly, so
    without a lower bound every extra component converges to a spike — measured
    at 0.01 Hz beside two correctly recovered lines. The residual drop is real,
    so no selection threshold rejects it; the model has to exclude the shape.
    """
    ppm, y, _ = _region(2.0, 7002)
    components = resolve_region(ppm, y, field_mhz=_FIELD_MHZ, noise_sigma=1.0)
    step_hz = float(np.median(np.abs(np.diff(ppm)))) * _FIELD_MHZ
    for component in components:
        assert component.fwhm_hz >= step_hz * 1.5, (
            f"a component {component.fwhm_hz:.3f} Hz wide, against {step_hz:.3f} Hz sampling — "
            "that is a spike fitted to one noise sample, not a line"
        )


def test_no_component_sits_below_the_noise() -> None:
    """A component that does not clear the noise is not a line, however much it
    improves the arithmetic."""
    ppm, y, _ = _region(1.5, 7003)
    components = resolve_region(ppm, y, field_mhz=_FIELD_MHZ, noise_sigma=1.0)
    for component in components:
        assert component.height >= 3.0, f"a component at {component.height:.2f} sigma was reported"


def test_it_still_works_near_the_detection_limit() -> None:
    """Deconvolution that only works on tall lines solves the easy half."""
    for seed in range(6):
        ppm, y, centres = _region(2.0, 7100 + seed, height=20.0)
        components = resolve_region(ppm, y, field_mhz=_FIELD_MHZ, noise_sigma=1.0)
        assert len(components) == len(centres)


def test_it_refuses_rather_than_guesses_on_input_it_cannot_use() -> None:
    ppm, y, _ = _region(2.0, 7004)
    assert resolve_region(ppm, y, field_mhz=0.0, noise_sigma=1.0) == []
    assert resolve_region(ppm, y, field_mhz=_FIELD_MHZ, noise_sigma=0.0) == []
    assert resolve_region(ppm[:4], y[:4], field_mhz=_FIELD_MHZ, noise_sigma=1.0) == []
