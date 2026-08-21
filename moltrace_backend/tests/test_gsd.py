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
        for k, amp in zip((1.5, 0.5, -0.5, -1.5), (1.0, 3.0, 3.0, 1.0), strict=True)
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


class TestFitConvergesToThePrecisionThatIsRead:
    """The fit tolerance feeds a discrete classifier, so it needs an accuracy contract.

    Profiling a 65k-point 1H analysis found 41,714 SVD calls — 11.3 s of a 24 s
    run — across 178 least-squares fits averaging 234 trust-region iterations
    each, so the fit tolerance was tried as a latency lever: loosening scipy's
    default ftol/xtol/gtol of 1e-8 to 1e-5 measured 6.95x faster with the peak
    list identical ON THAT SPECTRUM.

    A few ambiguous multiplets have a discrete label (read off the line COUNT)
    that is not robust to the tolerance OR the platform: 40256149 peak 2 is "m" at
    1e-8 and "t" at 1e-5 on macOS, and 40256175 peak 6 is "s" on macOS but "d" on
    Linux at both tolerances. That is a different local minimum per LAPACK, not an
    under-converged fit, so the tolerance does not fix it — the output-invariance
    goldens are minted on Linux (production) instead. See the note in nmrcheck.gsd
    deconvolve_region.

    These tests pin the accuracy side regardless of tolerance, so any future change
    has to answer to the same numbers: line COUNT, centre positions in Hz, and
    analytic areas must all survive.
    """

    MHZ = 400.0

    def _multiplet(self, j_hz: float, n_lines: int, linewidth_hz: float, span_ppm: float):
        import numpy as np

        rng = np.random.default_rng(11)
        j_ppm = j_hz / self.MHZ
        hwhm = linewidth_hz / 2.0 / self.MHZ
        centers = [3.5 + (i - (n_lines - 1) / 2) * j_ppm for i in range(n_lines)]
        mid = float(np.mean(centers))
        x = np.linspace(mid - span_ppm / 2, mid + span_ppm / 2, 8192)
        y = np.zeros_like(x)
        for c in centers:
            lorentz = 0.6 / (1.0 + ((x - c) / hwhm) ** 2)
            gauss = 0.4 * np.exp(-np.log(2) * ((x - c) / hwhm) ** 2)
            y += 100.0 * (lorentz + gauss)
        return list(x), list(y + rng.normal(0.0, 0.35, x.size)), centers

    def test_resolves_the_tightest_coupling_a_chemist_would_report(self) -> None:
        # J = 1.2 Hz at a 0.6 Hz linewidth: the lines are barely two linewidths
        # apart, which is where a loose fit would merge them into a singlet.
        x, y, centers = self._multiplet(1.2, 2, 0.6, 0.05)
        lines = deconvolve_region(x, y, centers, noise_sigma=0.35)
        assert len(lines) == 2, f"a 1.2 Hz doublet resolved as {len(lines)} line(s)"
        got = sorted(line[0] for line in lines)
        separation_hz = (got[1] - got[0]) * self.MHZ
        assert abs(separation_hz - 1.2) < 0.15, (
            f"recovered J = {separation_hz:.3f} Hz from a 1.2 Hz doublet"
        )

    def test_recovers_multiplet_centres_well_inside_reported_precision(self) -> None:
        # A coupling is read to ~0.1 Hz; the fit must be far better than that.
        for j_hz, n_lines, linewidth, span in (
            (7.2, 4, 0.7, 0.10),
            (6.8, 7, 0.9, 0.20),
            (2.0, 2, 0.7, 0.06),
        ):
            x, y, centers = self._multiplet(j_hz, n_lines, linewidth, span)
            lines = deconvolve_region(x, y, centers, noise_sigma=0.35)
            assert len(lines) == n_lines, (
                f"J={j_hz} Hz multiplet gave {len(lines)} lines, expected {n_lines}"
            )
            got = sorted(line[0] for line in lines)
            worst = max(
                abs(g - c) * self.MHZ for g, c in zip(got, sorted(centers), strict=True)
            )
            assert worst < 0.05, (
                f"J={j_hz} Hz multiplet centres drifted {worst:.3f} Hz from truth"
            )

    def test_a_broad_singlet_is_not_split_by_the_looser_tolerance(self) -> None:
        # The failure mode in the other direction: stopping early on a broad,
        # noisy line and calling the residual structure a second transition.
        x, y, centers = self._multiplet(0.0, 1, 3.0, 0.20)
        lines = deconvolve_region(x, y, centers, noise_sigma=0.35)
        assert len(lines) == 1, f"a broad singlet was split into {len(lines)} lines"

    def test_fitted_areas_stay_analytic_and_positive(self) -> None:
        x, y, centers = self._multiplet(7.2, 4, 0.7, 0.10)
        lines = deconvolve_region(x, y, centers, noise_sigma=0.35)
        assert lines
        for _centre, height, hwhm, area in lines:
            assert height > 0.0 and hwhm > 0.0
            assert area > 0.0, "an analytic pseudo-Voigt area cannot be non-positive"
