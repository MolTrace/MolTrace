"""Tests for Global Spectral Deconvolution (nmrcheck.gsd)."""

import random

import pytest

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

    It was reverted to 1e-8. TWO things are true here and they are independent —
    an earlier revert-of-the-revert conflated them, so keep them apart:

    1. 1e-5 is UNDER-CONVERGED for this stage. On the fixture corpus the peak list
       is not identical: multiplicity is read off the resolved line COUNT, and the
       count still moves between 1e-5 and 1e-8. Measured on one machine, with no
       platform variable in play, 3 of 177 labels differ (40256149 peak 2 in both
       configs "m" -> "t"; 40256175 guided peak 8 "dd" -> "m"), and only 1e-8
       reproduces the committed goldens.
    2. A few multiplets ALSO diverge by PLATFORM at a fully converged fit —
       40256175 unguided peak 6 is "s" on macOS/ARM and "d" on Linux/x86 at 1e-8.
       No tolerance reconciles that one; it is a different local minimum per
       LAPACK, and it is handled by the boundary register, not by ftol.

    So convergence is necessary but not sufficient. Fixing (1) does not fix (2),
    and (2) is not a reason to give up on (1). See the note in nmrcheck.gsd
    deconvolve_region and tests/golden/fid_invariants/boundary_register.json.

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


class TestTheCouplingWindowIsAChemicalBound:
    """``_MAX_J_HZ`` is a statement about chemistry, so it is tested as one.

    ``multiplicity_from_lines`` reports a first-order label only when every
    adjacent-line spacing falls inside the plausible J window. The upper edge is
    therefore an assertion that a spacing that large CAN be a 1H-1H scalar
    coupling — and when it is set too high, two unrelated signals that the peak
    detector happened to cluster together are handed to a chemist as a doublet
    with an impossible J.

    These tests pin the CHEMISTRY, not the constant. They assert that real
    couplings up to the geminal / trans-vinyl ceiling survive, and that the two
    separations measured in the fixture corpus which cannot be couplings are
    rejected. They deliberately say nothing about the interval between those two
    regimes: the corpus has no data there (see the class docstring below), so
    pinning a value inside it would be inventing a bound rather than measuring
    one. Any ``_MAX_J_HZ`` in that empty interval passes.
    """

    MHZ = 399.953799784  # the nmrshiftdb2 40256149 spectrometer frequency

    def _pair(self, separation_hz: float) -> tuple[str, tuple[float, ...]]:
        """Label a two-line set separated by ``separation_hz``."""
        return multiplicity_from_lines(
            [2.0, 2.0 + separation_hz / self.MHZ], frequency_mhz=self.MHZ
        )

    @pytest.mark.parametrize(
        ("j_hz", "what"),
        [
            (0.9, "long-range 4J, at the resolution limit"),
            (2.5, "meta aromatic 4J"),
            (7.2, "vicinal 3J, the most common coupling in a 1H spectrum"),
            (8.5, "ortho aromatic 3J"),
            (12.4, "geminal 2J in an sp3 methylene"),
            (16.8, "trans-vinyl 3J"),
            (18.06, "the largest genuine coupling in the fixture corpus"),
        ],
    )
    def test_a_real_coupling_is_still_read_as_a_doublet(
        self, j_hz: float, what: str
    ) -> None:
        multiplicity, j_values = self._pair(j_hz)
        assert multiplicity == "d", (
            f"{j_hz} Hz ({what}) must read as a doublet, got {multiplicity!r} — "
            "the coupling window has been narrowed past real chemistry."
        )
        assert j_values and abs(j_values[0] - j_hz) <= 0.1

    @pytest.mark.parametrize(
        ("separation_hz", "source"),
        [
            (
                43.52,
                "60000023 (cocaine) peak 2 at 3.578 ppm — two overlapping "
                "bicyclic-ring signals, not one doublet",
            ),
            (
                45.62,
                "40256149 (piperine) peak 9 at 1.773 ppm — two methylene "
                "multiplets inside the piperidine envelope",
            ),
        ],
    )
    def test_a_separation_no_1h_coupling_can_produce_is_not_a_doublet(
        self, separation_hz: float, source: str
    ) -> None:
        # Neither compound contains fluorine or phosphorus, so there is no
        # heteronuclear route to a splitting this large either. The honest label
        # for two clustered signals is the generic multiplet.
        multiplicity, _j = self._pair(separation_hz)
        assert multiplicity == "m", (
            f"{separation_hz} Hz was reported as {multiplicity!r}. No 1H-1H "
            f"scalar coupling reaches that value. Source: {source}."
        )

    def test_the_piperine_label_holds_across_the_whole_range_the_fit_explores(
        self,
    ) -> None:
        """The label must not turn on where inside its own spread the fit lands.

        40256149 peak 9 is one strong line and one weak line at 1.96x the
        inclusion cut, whose fitted centre the data does not constrain. Nudging
        the region trace by a relative 1e-12 — seven orders below one ADC count —
        moves their separation across 44.37 / 45.62 / 58.29 / 58.80 Hz. A
        classifier boundary anywhere in that range makes the reported
        multiplicity a function of the last bits of the input.
        """
        labels = {sep: self._pair(sep)[0] for sep in (44.37, 45.62, 58.29, 58.80)}
        assert set(labels.values()) == {"m"}, (
            "the label changes across the range this peak's fit explores: "
            f"{labels}. The band edge sits inside the fit's own spread."
        )


class TestLinesTooCloseToBeCouplingPartnersAreOneLine:
    """Two lines closer than the smallest possible coupling are one line.

    ``_MIN_J_HZ`` states that no resolvable 1H-1H scalar coupling is smaller than
    0.5 Hz. Read as a lower bound on a SPACING that is a rejection rule -- a
    multiplet containing one is not first-order, so it is reported "m". Read as
    what it actually says about the two lines either side of that spacing, it is
    a statement of identity: they are too close to be coupling partners, so for
    the purpose of reading a coupling pattern they contribute one line, not two.

    Measured across the 19 nmrshiftdb2 raw-FID fixtures: 18 of 126 deconvolved
    multiplets (14%) were reported "m" solely because at least one adjacent
    spacing fell below 0.5 Hz. Those gaps run 0.21-0.49 Hz -- at 250-400 MHz,
    5e-4 ppm, orders of magnitude below any resolvable linewidth.
    """

    FREQ_MHZ = 250.0

    # 40254842 (1,2-epoxybutane, 250 MHz), the ethyl CH3 at 0.984 ppm -- three
    # bonds from the CH2, a textbook triplet. The deconvolution resolves seven
    # lines: the two real ~7 Hz couplings, and a five-piece tiling of the centre
    # transition with gaps of 0.32 / 0.29 / 0.24 / 0.21 Hz.
    EPOXYBUTANE_CH3_LINES = [
        0.9526317246464563,
        0.9805969181335495,
        0.9818813403739153,
        0.9830529968996266,
        0.9839967110563363,
        0.9848433861175666,
        1.0126292417638614,
    ]

    def test_the_epoxybutane_methyl_reads_as_the_triplet_it_is(self) -> None:
        multiplicity, j_values = multiplicity_from_lines(
            self.EPOXYBUTANE_CH3_LINES, frequency_mhz=self.FREQ_MHZ
        )
        assert multiplicity == "t", (
            f"reported {multiplicity!r}. Adjacent spacings are 6.99 / 0.32 / "
            f"0.29 / 0.24 / 0.21 / 6.95 Hz; the four sub-resolution gaps are not "
            f"couplings, and what is left is two equal ones."
        )
        assert j_values and abs(j_values[0] - 7.5) <= 0.6, (
            f"J = {j_values} Hz; an ethyl CH3 couples to its CH2 at ~7.5 Hz."
        )

    def test_two_lines_closer_than_any_coupling_are_a_singlet(self) -> None:
        """40256149 peak 7 at 5.965 ppm: two lines 0.49 Hz apart, reported "m"."""
        pair = [5.965, 5.965 + 0.4948 / self.FREQ_MHZ]
        assert multiplicity_from_lines(pair, frequency_mhz=self.FREQ_MHZ) == ("s", ())

    def test_a_coupling_just_above_the_floor_is_still_a_doublet(self) -> None:
        """The other edge: a real coupling must survive the collapse.

        Deliberately 0.6 Hz and not 0.5. A pair constructed AT the bound does not
        test the rule -- ``(5.965 + 0.5 / 250.0 - 5.965) * 250.0`` is
        0.49999999999994 Hz, so which side of the bound it lands on is decided by
        the last bits of a subtraction, not by the data. The collapse and the
        rejection rule read the same ``_MIN_J_HZ`` with the same comparison, so
        they agree on that boundary by construction whichever way it rounds;
        what needs pinning is that a coupling clear of it survives.
        """
        pair = [5.965, 5.965 + 0.6 / self.FREQ_MHZ]
        multiplicity, j_values = multiplicity_from_lines(pair, frequency_mhz=self.FREQ_MHZ)
        assert multiplicity == "d"
        assert j_values and abs(j_values[0] - 0.6) <= 0.05

    def test_a_clean_multiplet_is_untouched(self) -> None:
        """Nothing with all spacings above the floor may move at all."""
        j_ppm = 7.0 / 400.0
        quartet = [2.40 + k * j_ppm for k in (-1.5, -0.5, 0.5, 1.5)]
        assert multiplicity_from_lines(quartet, frequency_mhz=400.0)[0] == "q"

    def test_a_collapsed_run_reports_the_envelope_centre(self) -> None:
        """The survivor is the run's centroid, not an arbitrary member.

        Picking an end member would shift the reported coupling by the width of
        the run -- here 1.06 Hz, which is 14% of a 7.5 Hz coupling.
        """
        _multiplicity, j_values = multiplicity_from_lines(
            self.EPOXYBUTANE_CH3_LINES, frequency_mhz=self.FREQ_MHZ
        )
        centre = sum(self.EPOXYBUTANE_CH3_LINES[1:6]) / 5
        expected = (centre - self.EPOXYBUTANE_CH3_LINES[0]) * self.FREQ_MHZ
        assert j_values and abs(j_values[0] - expected) <= 0.3
