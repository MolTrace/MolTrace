"""Tests for Global Spectral Deconvolution (nmrcheck.gsd)."""

import random

from nmrcheck.gsd import deconvolve_region, multiplicity_from_lines


def _lorentzian(x: float, amplitude: float, center: float, hwhm: float) -> float:
    return amplitude * hwhm * hwhm / ((x - center) ** 2 + hwhm * hwhm)


def _synth_region(
    lines: list[tuple[float, float, float]],
    *,
    noise: float,
    seed: int,
) -> tuple[list[float], list[float]]:
    """Synthesize a region: x grid + summed-Lorentzian intensities + noise.

    ``lines`` are ``(center_ppm, amplitude, hwhm_ppm)`` triples.
    """
    mid = sum(center for center, _a, _w in lines) / len(lines)
    rng = random.Random(seed)
    xs = [mid - 0.08 + idx * (0.16 / 319) for idx in range(320)]
    ys = [
        sum(_lorentzian(x, amp, center, hwhm) for center, amp, hwhm in lines)
        + rng.gauss(0.0, noise)
        for x in xs
    ]
    return xs, ys


def test_deconvolution_resolves_an_overlapped_quartet() -> None:
    # Four lines (1:3:3:1, J = 7 Hz at 400 MHz) broad enough to merge into a
    # two-bump envelope a local-maximum picker cannot resolve. GSD must
    # recover all four and read the pattern as a quartet.
    freq = 400.0
    j_ppm = 7.0 / freq
    lines = [
        (2.40 + k * j_ppm, amp, 0.0090)
        for k, amp in zip((1.5, 0.5, -0.5, -1.5), (1.0, 3.0, 3.0, 1.0))
    ]
    xs, ys = _synth_region(lines, noise=0.02, seed=1)
    resolved = deconvolve_region(
        xs, ys, [2.40 - 0.009, 2.40 + 0.009], noise_sigma=0.02, max_lines=16
    )
    multiplicity, j_values = multiplicity_from_lines(
        [line[0] for line in resolved], frequency_mhz=freq
    )
    assert len(resolved) == 4
    assert multiplicity == "q"
    assert j_values and abs(j_values[0] - 7.0) <= 1.0


def test_deconvolution_does_not_over_resolve_a_singlet() -> None:
    # A clean singlet must stay one line — GSD must not invent structure.
    xs, ys = _synth_region([(2.40, 3.0, 0.004)], noise=0.02, seed=2)
    resolved = deconvolve_region(xs, ys, [2.40], noise_sigma=0.02, max_lines=16)
    multiplicity, _j = multiplicity_from_lines(
        [line[0] for line in resolved], frequency_mhz=400.0
    )
    assert len(resolved) == 1
    assert multiplicity == "s"


def test_deconvolution_distinguishes_dd_from_quartet() -> None:
    # A doublet-of-doublets (J = 12, 4 Hz) has four lines like a quartet but
    # two distinct spacings — GSD plus first-order analysis must label it "dd".
    freq = 400.0
    j1, j2 = 12.0 / freq, 4.0 / freq
    lines = [
        (2.40 + a * j1 / 2 + b * j2 / 2, 1.0, 0.0060)
        for a in (1, -1)
        for b in (1, -1)
    ]
    xs, ys = _synth_region(lines, noise=0.02, seed=3)
    resolved = deconvolve_region(
        xs, ys, [2.40 - 0.02, 2.40 + 0.02], noise_sigma=0.02, max_lines=16
    )
    multiplicity, j_values = multiplicity_from_lines(
        [line[0] for line in resolved], frequency_mhz=freq
    )
    assert len(resolved) == 4
    assert multiplicity == "dd"
    assert sorted(round(value) for value in j_values) == [4, 12]


def test_multiplicity_from_lines_reads_a_clean_triplet() -> None:
    freq = 400.0
    j_ppm = 7.0 / freq
    multiplicity, j_values = multiplicity_from_lines(
        [2.40 - j_ppm, 2.40, 2.40 + j_ppm], frequency_mhz=freq
    )
    assert multiplicity == "t"
    assert abs(j_values[0] - 7.0) <= 0.5


def test_multiplicity_from_lines_handles_degenerate_input() -> None:
    assert multiplicity_from_lines([], frequency_mhz=400.0) == ("s", ())
    assert multiplicity_from_lines([2.4], frequency_mhz=400.0) == ("s", ())
    # No frequency -> cannot compute J, reports a generic multiplet.
    assert multiplicity_from_lines([2.4, 2.41], frequency_mhz=None) == ("m", ())
