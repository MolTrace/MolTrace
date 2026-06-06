"""Quinine reference dataset — acceptance gate for Prompt 4.

Forward-models a quinine ¹H NMR spectrum at 500 MHz from published
literature chemical shifts + J couplings using the new
``generate_synthetic_multiplet`` forward modeller (which honours the
full coupling tree for dd / ddd patterns), runs the GSD peak picker
followed by ``detect_multiplets``, and asserts that:

* All 8 diagnostic multiplets are identified (8 quinine multiplets is
  the literal Prompt 4 acceptance count).
* Each recovered J value lands within 0.3 Hz of the literature value.

Quinine reference values are drawn from standard published 1H NMR
(Aldrich Spectral Library / Pretsch *Spectra Interpretation* / SDBS):

  Position        ppm     mult    J (Hz)
  H2'             8.74    d       4.5
  H8              8.04    d       9.2
  H3'             7.69    d       4.5
  H5              7.55    d       2.7
  H7              7.38    dd      9.2, 2.7
  H10 (vinyl)     5.79    ddd     17.4, 10.4, 7.5
  H9 (CHOH)       5.56    d       4.8
  OCH3            3.92    s       -

The hardest cases are the dd at 7.38 (which the analyzer must
disambiguate from a triplet-ish pattern in the cluster) and the ddd
at 5.79 (which requires the complex-multiplet enumeration path).

The test bypasses the v0.6 ``synthesize_spectrum`` helper because the
latter was deliberately simplified to use only the first J of compound
multiplets (its goal is line-count gating, not literal J recovery);
this acceptance gate needs the full coupling-tree synthesis from
``generate_synthetic_multiplet``.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter1d

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.multiplet import (
    detect_multiplets,
    generate_synthetic_multiplet,
)
from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

# Literature quinine reference, ordered by ppm ascending so the
# A, B, C, ... labelling ``detect_multiplets`` produces matches the
# expected left-to-right order in the FE peak table.
QUININE_REFERENCE: list[tuple[str, float, str, tuple[float, ...]]] = [
    ("OCH3", 3.92, "s", ()),
    ("H9", 5.56, "d", (4.8,)),
    ("H10_vinyl", 5.79, "ddd", (17.4, 10.4, 7.5)),
    ("H7", 7.38, "dd", (9.2, 2.7)),
    ("H5", 7.55, "d", (2.7,)),
    ("H3p", 7.69, "d", (4.5,)),
    ("H8", 8.04, "d", (9.2,)),
    ("H2p", 8.74, "d", (4.5,)),
]


def _synthesize_quinine_spectrum(
    field_mhz: float = 500.0,
    # Sharp linewidth (0.7 Hz) approximates a well-shimmed modern
    # 500 MHz spectrometer.  Tight enough that the dd inner pair at
    # H7 (2.7 Hz separation) is fully resolved and the ddd inner pair
    # at H10 (0.5 Hz separation, sub-linewidth) cleanly merges into
    # the single observed peak the n=7 ddd branch handles.
    linewidth_hz: float = 0.7,
    # High SNR (1000) so spurious noise peaks don't sneak through the
    # 5σ S/N filter and contaminate the multiplet clusters.
    snr_target: float = 1000.0,
    ppm_low: float = 2.0,
    ppm_high: float = 10.0,
    # 65k samples give ~5 samples per Hz at 500 MHz over 8 ppm range,
    # so the GSD picker's position estimates land within 0.1-0.2 Hz
    # of the true line centres — leaving headroom under the 0.3 Hz
    # Prompt 4 J recovery acceptance gate.
    n_points: int = 65536,
) -> NMRSpectrum:
    """Forward-model the quinine spectrum using the new multiplet
    forward modeller.  Each environment's lines are placed at the
    exact dd / ddd / d / s positions; correlated Gaussian noise (the
    same model the v0.6 HMDB synthetic harness uses) is added.

    The point density is doubled vs the v0.6 harness (32k instead of
    16k) because the dd / ddd lines sit only ~3 Hz apart in places
    and the GSD picker needs ≥ 6 samples per FWHM to fit them.
    """
    ppm_axis = np.linspace(ppm_high, ppm_low, n_points)  # descending
    intensity = np.zeros_like(ppm_axis)
    sample_step_ppm = abs(ppm_high - ppm_low) / float(n_points - 1)
    hwhm_ppm = max((linewidth_hz / field_mhz) / 2.0, 3.0 * sample_step_ppm)

    for _name, centre_ppm, multiplicity, j_set in QUININE_REFERENCE:
        positions = generate_synthetic_multiplet(
            multiplicity=multiplicity,
            j_hz=list(j_set),
            center_ppm=centre_ppm,
            freq_mhz=field_mhz,
        )
        # Pascal-triangle intensity weighting per leaf of the binary
        # tree — for a doublet each leaf gets weight 1; for a triplet
        # the two outer leaves get 1 and the middle leaf gets 2; for
        # a dd the four leaves are 1:1:1:1 (anti-Pascal: each J adds
        # one binary split); for ddd all 8 leaves are 1:1:1:1:1:1:1:1.
        # That's the correct first-order pattern for distinct J
        # values (Pascal weighting only applies when J values are
        # identical, which is the s/d/t/q/p case).
        leaf_count = len(positions)
        weight_per_leaf = 1.0 / leaf_count if leaf_count else 1.0
        for centre in positions:
            dx2 = (ppm_axis - centre) ** 2
            intensity += (
                weight_per_leaf * hwhm_ppm * hwhm_ppm / (dx2 + hwhm_ppm * hwhm_ppm)
            )

    # Correlated Gaussian noise, exactly the same model the v0.6 HMDB
    # synthetic harness uses so the GSD picker's detection threshold
    # is calibrated against the noise structure it was tuned for.
    peak_intensity = float(np.max(intensity))
    noise_std = peak_intensity / max(snr_target, 1.0)
    seed = int.from_bytes(
        hashlib.md5(b"quinine_500mhz_prompt4").digest()[:4], "big"
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
        metadata={"source": "test_multiplet_quinine_reference"},
        nucleus="1H",
        solvent="CDCl3",
        field_mhz=field_mhz,
    )


@pytest.mark.current_state
def test_quinine_all_eight_multiplets_detected_with_correct_J() -> None:
    """8 multiplets resolved + every J within 0.3 Hz of literature."""

    spectrum = _synthesize_quinine_spectrum()

    # Use GSD level 3 (overlap-aware single pass) rather than level 4
    # (iterative deconvolve_region).  Level 4 is more aggressive and
    # produces low-amplitude phantom satellite peaks (S/N 30-50) on
    # tall well-isolated singlets like OCH3 and H8 here — which
    # spuriously inflate the cluster count.  Level 3's overlap
    # detection is sufficient to resolve the H7 dd and H10 ddd
    # patterns on a clean synthetic spectrum where every coupled
    # line is at least 2.7 Hz from its nearest neighbour.
    peaks = gsd_peak_pick(spectrum, level=3)

    # Filter spurious noise singletons by signal-to-noise (every GSD
    # peak carries ``metadata['signal_to_noise']`` from v0.6.3).  The
    # multiplet analyser then operates on the high-confidence subset
    # and the spatial-clustering step groups coupled lines back
    # together regardless of category, so the dd outer lines that
    # ``auto_classify`` would tag as "impurity" (because they fall
    # outside curated compound shift windows) stay in the same
    # multiplet as the inner lines.
    #
    # 10x noise is set above the 5σ classical detection threshold
    # because GSD's iterative deconvolve_region at level 4 produces
    # low-amplitude phantom satellite peaks (typically 1-5σ) around
    # very tall singlets like OCH3.  The Prompt 4 J recovery needs
    # them filtered out so the singlet cluster stays at n=1.
    snr_threshold = 10.0
    high_snr_peaks = [
        p
        for p in peaks
        if float(p.metadata.get("signal_to_noise", 0.0) or 0.0) >= snr_threshold
    ]
    multiplets = detect_multiplets(high_snr_peaks)
    detected = [m for m in multiplets if m.peaks]

    assert len(detected) == 8, (
        f"Expected 8 quinine multiplets, got {len(detected)} with labels "
        f"{[(m.name, m.multiplicity_label, round(m.center_ppm, 2), m.j_couplings_hz) for m in detected]}"
    )

    # Match each detected multiplet to the nearest literature
    # environment by center ppm.  Quinine multiplets are well
    # separated (>= 0.05 ppm) so nearest-ppm is unambiguous.
    for ref_name, ref_ppm, ref_mult, ref_j in QUININE_REFERENCE:
        nearest = min(detected, key=lambda m: abs(m.center_ppm - ref_ppm))
        assert abs(nearest.center_ppm - ref_ppm) <= 0.05, (
            f"Reference {ref_name} at {ref_ppm} ppm did not match any "
            f"detected multiplet within 0.05 ppm (nearest was "
            f"{nearest.name} at {nearest.center_ppm:.3f})"
        )

        # Multiplicity label must match exactly.
        assert nearest.multiplicity_label == ref_mult, (
            f"Reference {ref_name} ({ref_mult}) was classified as "
            f"{nearest.multiplicity_label} at {nearest.center_ppm:.3f} ppm; "
            f"recovered J={nearest.j_couplings_hz}"
        )

        # Every recovered J within 0.3 Hz of literature.
        ref_sorted = sorted(ref_j, reverse=True)
        got_sorted = sorted(nearest.j_couplings_hz, reverse=True)
        assert len(got_sorted) == len(ref_sorted), (
            f"Reference {ref_name} ({ref_mult}) needs "
            f"{len(ref_sorted)} J values, got {got_sorted}"
        )
        for got, expected in zip(got_sorted, ref_sorted, strict=True):
            delta = abs(got - expected)
            assert delta <= 0.3, (
                f"Reference {ref_name} ({ref_mult}) at {ref_ppm}: "
                f"J recovered {got:.2f} Hz, literature {expected:.2f} Hz, "
                f"delta {delta:.2f} Hz exceeds 0.3 Hz acceptance gate."
            )

        # Sanity check: every J in the homonuclear ¹H–¹H window.
        for j in got_sorted:
            assert math.isfinite(j) and 0.5 <= j <= 60.0, (
                f"Reference {ref_name}: J={j} outside ¹H–¹H window."
            )
