"""Hidden 11.4 Hz coupling benchmark — Prompt 4 gate.

A well-known worked example shows a dd cluster where the inner pair of
lines sits closer than the spectrometer's natural linewidth, so a naive
peak picker (level-2 single-pass detection on a crude grid) reports only
3 peaks and assigns "t".  The hidden 11.4 Hz coupling is invisible to
that naive picker.

GSD-enhanced picking (level 4 iterative ``deconvolve_region``) resolves
the inner pair into two distinct lines, the new ``detect_multiplets``
matches the four-line dd hypothesis, and the recovered J set carries
the 11.4 Hz coupling.

The test forward-models the dd, runs both the *naive* GSD level-2
picker and the *GSD-enhanced* level-4 picker, and asserts that:

* Level 2 alone (the "naive" baseline) does *not* see the 11.4 Hz
  coupling — it merges the inner pair and reports either ``t`` or a
  ``d`` with the wrong J (the standard "this peak is hidden" symptom).
* Level 4 + ``detect_multiplets`` recovers the dd with both J values,
  ``11.4`` Hz appearing within 0.3 Hz tolerance.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter1d

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.multiplet import (
    detect_multiplets,
    generate_synthetic_multiplet,
)
from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

# dd coupling constants chosen so the inner pair offset is
# (J_large - J_small) / 2 = 0.85 Hz at 500 MHz, just below the
# realistic 1.5 Hz linewidth — the classic "hidden coupling" geometry.
# Outer pair offset = (J_large + J_small) / 2 = 12.55 Hz, easily
# resolved.  The benchmark uses 11.4 Hz as the hidden coupling;
# the partner J=13.7 here is chosen so the inner pair collapses
# cleanly under typical linewidth.
J_LARGE_HZ = 13.7
J_SMALL_HZ = 11.4
FIELD_MHZ = 500.0
CENTRE_PPM = 6.50
# Wider linewidth than the quinine test (the benchmark example
# explicitly assumes the inner pair is unresolved under coarse
# resolution); choose 1.5 Hz so the inner ddd pair at 0.85 Hz
# separation cleanly merges into a single envelope before
# deconvolution.
LINEWIDTH_HZ = 1.5


def _synthesize_dd_spectrum(
    *,
    n_points: int = 65536,
    snr_target: float = 1000.0,
) -> NMRSpectrum:
    """Build a single dd cluster spectrum at the benchmark geometry."""
    ppm_high = 7.5
    ppm_low = 5.5
    ppm_axis = np.linspace(ppm_high, ppm_low, n_points)
    intensity = np.zeros_like(ppm_axis)
    sample_step_ppm = abs(ppm_high - ppm_low) / float(n_points - 1)
    hwhm_ppm = max((LINEWIDTH_HZ / FIELD_MHZ) / 2.0, 3.0 * sample_step_ppm)

    positions = generate_synthetic_multiplet(
        multiplicity="dd",
        j_hz=[J_LARGE_HZ, J_SMALL_HZ],
        center_ppm=CENTRE_PPM,
        freq_mhz=FIELD_MHZ,
    )
    for centre in positions:
        dx2 = (ppm_axis - centre) ** 2
        intensity += 0.25 * hwhm_ppm * hwhm_ppm / (dx2 + hwhm_ppm * hwhm_ppm)

    peak_intensity = float(np.max(intensity))
    noise_std = peak_intensity / max(snr_target, 1.0)
    seed = int.from_bytes(
        hashlib.md5(b"hidden_coupling_11_4_hz_benchmark").digest()[:4], "big"
    )
    rng = np.random.default_rng(seed=seed)
    raw_noise = rng.normal(loc=0.0, scale=noise_std, size=intensity.size)
    correlated_noise = gaussian_filter1d(raw_noise, sigma=2.0, mode="nearest")
    realized_std = float(np.std(correlated_noise))
    if realized_std > 0:
        correlated_noise = correlated_noise * (noise_std / realized_std)
    intensity = intensity + correlated_noise

    return NMRSpectrum(
        data=intensity,
        ppm_axis=ppm_axis,
        metadata={"source": "test_multiplet_hidden_coupling"},
        nucleus="1H",
        solvent="CDCl3",
        field_mhz=FIELD_MHZ,
    )


@pytest.mark.current_state
def test_hidden_coupling_recovered_by_gsd_level_4() -> None:
    """GSD-enhanced detection recovers the 11.4 Hz hidden coupling."""

    spectrum = _synthesize_dd_spectrum()

    # GSD-enhanced path: level 4 iterative ``deconvolve_region`` lets
    # the picker resolve the inner pair even when their separation is
    # below the natural linewidth.  ``detect_multiplets`` then matches
    # the 4-line dd hypothesis analytically.
    enhanced_peaks = gsd_peak_pick(spectrum, level=4)
    enhanced_hi_snr = [
        p
        for p in enhanced_peaks
        if float(p.metadata.get("signal_to_noise", 0.0) or 0.0) >= 10.0
    ]
    enhanced_multiplets = detect_multiplets(enhanced_hi_snr)
    enhanced_detected = [m for m in enhanced_multiplets if m.peaks]

    # Find the multiplet at our target centre.
    target = min(
        enhanced_detected, key=lambda m: abs(m.center_ppm - CENTRE_PPM)
    )

    assert target.multiplicity_label == "dd", (
        f"Expected dd, got {target.multiplicity_label} at "
        f"{target.center_ppm:.3f}; J={target.j_couplings_hz}"
    )

    # Recovered J set should include both 13.7 and 11.4 Hz within
    # the 0.3 Hz Prompt 4 tolerance.  Order is largest-first.
    js_sorted = sorted(target.j_couplings_hz, reverse=True)
    assert len(js_sorted) == 2, (
        f"dd should report 2 J values, got {target.j_couplings_hz}"
    )
    assert abs(js_sorted[0] - J_LARGE_HZ) <= 0.3, (
        f"J_large recovered {js_sorted[0]:.2f} Hz, expected "
        f"{J_LARGE_HZ:.2f} Hz, delta {abs(js_sorted[0] - J_LARGE_HZ):.2f} Hz "
        "exceeds 0.3 Hz tolerance."
    )
    assert abs(js_sorted[1] - J_SMALL_HZ) <= 0.3, (
        f"J_small (hidden coupling) recovered {js_sorted[1]:.2f} Hz, "
        f"expected {J_SMALL_HZ:.2f} Hz, delta "
        f"{abs(js_sorted[1] - J_SMALL_HZ):.2f} Hz exceeds 0.3 Hz tolerance."
    )


@pytest.mark.current_state
def test_naive_level_2_misses_the_hidden_coupling() -> None:
    """Baseline: level-2 single-pass picking misses the 11.4 Hz J.

    This pins the "naive picker fails" half of the benchmark worked
    example.  Without GSD's iterative ``deconvolve_region``, the
    inner pair of dd lines (~0.85 Hz apart at the J set chosen here)
    merges under the 1.5 Hz linewidth and the picker sees only 3
    peaks.  Either (a) the cluster reports as a triplet with the
    wrong J, or (b) ``detect_multiplets`` falls back to ``m`` —
    *neither* recovers the 11.4 Hz coupling.

    The test passes when *either* of the failure modes occurs.  This
    is the literal "standard peak picking misses the 11.4 Hz hidden
    coupling" framing from the Prompt 4 spec.
    """

    spectrum = _synthesize_dd_spectrum()
    naive_peaks = gsd_peak_pick(spectrum, level=2)
    naive_hi_snr = [
        p
        for p in naive_peaks
        if float(p.metadata.get("signal_to_noise", 0.0) or 0.0) >= 10.0
    ]
    naive_multiplets = detect_multiplets(naive_hi_snr)
    naive_detected = [m for m in naive_multiplets if m.peaks]
    if naive_detected:
        target = min(
            naive_detected, key=lambda m: abs(m.center_ppm - CENTRE_PPM)
        )
        # Naive picker must not recover the dd label OR, if it does,
        # the J set must miss the 11.4 Hz coupling.
        if target.multiplicity_label == "dd":
            js_sorted = sorted(target.j_couplings_hz, reverse=True)
            assert not (
                len(js_sorted) >= 2 and abs(js_sorted[1] - J_SMALL_HZ) <= 0.3
            ), (
                "Naive level-2 picker unexpectedly recovered the 11.4 Hz "
                "hidden coupling.  The level-3-vs-4 distinction in the "
                "hidden-coupling benchmark worked example may no longer hold "
                "with the synthesis parameters chosen here — either tighten "
                f"the linewidth or update the test geometry.  Got J={js_sorted}"
            )
