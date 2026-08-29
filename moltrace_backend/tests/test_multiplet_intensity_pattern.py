"""A multiplet has the INTENSITIES of a multiplet, not just the spacings.

The label was decided from spacings alone, so any two lines whose gap fell inside
the J window became a doublet however unequal they were. Measured on a real 13C
acquisition: four signals in the QUANTIFIABLE half of the table were labelled
doublets with J of 25-29 Hz and line ratios of 62, 101, 186 and 237 to one.

A doublet is one nucleus split by one neighbour. Its two lines are equal. Those
were a strong carbon beside a weak line a quarter of a ppm away — an ordinary gap
between two distinct carbons — and the reported "coupling" was the gap.
"""

from __future__ import annotations

import pytest

from moltrace.spectroscopy.multiplet.analysis import (
    _binomial_pattern,
    _intensities_fit_a_multiplet,
    _trinomial_pattern,
)


class _Line:
    """Only what the check reads."""

    def __init__(self, intensity: float) -> None:
        self.intensity = intensity


def _lines(*intensities: float) -> list:
    return [_Line(v) for v in intensities]


def test_a_doublet_must_have_two_equal_lines() -> None:
    """The defect, asserted. 1:1 is what a doublet is."""
    assert _intensities_fit_a_multiplet(_lines(100.0, 100.0))
    assert _intensities_fit_a_multiplet(_lines(100.0, 80.0)), "a real doublet is never exact"


@pytest.mark.parametrize("ratio", [62.0, 101.0, 186.0, 237.0])
def test_the_ratios_measured_on_a_real_spectrum_are_rejected(ratio: float) -> None:
    """The four that were shipped as doublets, by their measured ratios."""
    assert not _intensities_fit_a_multiplet(_lines(ratio, 1.0)), (
        f"a {ratio:.0f}:1 pair was accepted as a first-order multiplet"
    )


def test_deuterium_is_spin_one_and_its_septet_survives() -> None:
    """The check that would be wrong if it only knew Pascal's triangle.

    DMSO-d6 couples to three spin-1 deuterons and gives 1:3:6:7:6:3:1, not the
    1:6:15:20:15:6:1 of six spin-1/2 neighbours. Measured on a real acquisition:
    1.0 : 3.1 : 6.2 : 7.3 : 6.2 : 3.1 : 1.0. A binomial-only check would reject
    the most confidently correct assignment on the page.
    """
    observed = _lines(1.0, 3.1, 6.2, 7.3, 6.2, 3.1, 1.0)
    assert _intensities_fit_a_multiplet(observed)
    assert _trinomial_pattern(7) == [1.0, 3.0, 6.0, 7.0, 6.0, 3.0, 1.0]


def test_a_dd_and_a_ddd_have_EQUAL_lines_and_are_accepted() -> None:
    """The false-positive half, and the one that bit.

    Binomial coefficients describe n EQUIVALENT neighbours. n DIFFERENT couplings
    give all lines equal: a dd is 1:1:1:1 and a ddd is eight equal lines, nothing
    like the 1:7:21:35:35:21:7:1 of seven equivalent neighbours. Omitting that
    family reclassified quinine's H10 vinyl ddd as `m` and discarded its
    couplings — caught by the reference test, which is exactly what it is for.
    """
    from moltrace.spectroscopy.multiplet.analysis import _uniform_pattern

    assert _uniform_pattern(4) == [1.0, 1.0, 1.0, 1.0]
    assert _intensities_fit_a_multiplet(_lines(1.0, 1.0, 1.0, 1.0)), "a dd was rejected"
    assert _intensities_fit_a_multiplet(
        _lines(1.0, 1.1, 0.95, 1.05, 1.0, 0.9, 1.02, 0.98)
    ), "a ddd with ordinary scatter was rejected"


def test_the_uniform_family_does_not_reopen_the_hole() -> None:
    """Accepting equal lines must not accept a 186:1 pair — they are not equal."""
    for ratio in (62.0, 186.0, 237.0):
        assert not _intensities_fit_a_multiplet(_lines(ratio, 1.0))


def test_a_spin_half_triplet_is_accepted() -> None:
    assert _binomial_pattern(3) == [1.0, 2.0, 1.0]
    assert _intensities_fit_a_multiplet(_lines(1.0, 2.0, 1.0))
    assert _intensities_fit_a_multiplet(_lines(0.9, 2.1, 1.05))


def test_a_pattern_with_the_wrong_shape_is_rejected() -> None:
    """Three EQUAL lines are not a triplet — a triplet's centre is twice its wings.

    Three equal lines are what two distinct signals plus a third look like.
    """
    assert not _intensities_fit_a_multiplet(_lines(100.0, 100.0, 1.0)), (
        "a 100:100:1 pattern was accepted as a triplet"
    )


def test_it_judges_nothing_it_cannot_judge() -> None:
    """A silent extra rejection would be worse than the label it prevents."""
    assert _intensities_fit_a_multiplet(_lines(5.0))
    assert _intensities_fit_a_multiplet([])
    assert _intensities_fit_a_multiplet(_lines(0.0, 0.0))


def test_the_label_on_a_real_spectrum_changes_only_where_it_should() -> None:
    """End to end, on the acquisition the defect was found in.

    The four unequal pairs stop being doublets; the septet stays a septet.
    """
    import glob
    import os

    from moltrace.spectroscopy.io.fid_reader import read_processed_spectrum
    from moltrace.spectroscopy.multiplet.analysis import detect_multiplets
    from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

    roots = sorted(
        {p.split("/pdata")[0] for p in glob.glob("tests/fixtures/**/pdata", recursive=True)}
    )
    spectrum = None
    for root in roots:
        try:
            candidate = read_processed_spectrum(os.fspath(root))
        except Exception:  # noqa: BLE001
            continue
        if "13C" in candidate.nucleus:
            spectrum = candidate
            break
    if spectrum is None:
        pytest.skip("no instrument-processed 13C acquisition in this checkout")

    for multiplet in detect_multiplets(gsd_peak_pick(spectrum)):
        if multiplet.multiplicity_label in {"s", "m"}:
            continue
        intensities = [max(float(p.intensity), 0.0) for p in multiplet.peaks]
        if not intensities or min(intensities) <= 0:
            continue
        extreme = max(intensities) / min(intensities)
        # A real multiplet's extremes are bounded by its own pattern: 1 for a
        # doublet, 2 for a triplet, 7 for the deuterium septet. Nothing
        # first-order reaches 60.
        assert extreme < 20.0, (
            f"a {multiplet.multiplicity_label} at {multiplet.center_ppm:.3f} ppm has lines "
            f"{extreme:.0f}:1 apart — that is two signals, not one multiplet"
        )


def test_a_rejected_pattern_reports_no_couplings_either() -> None:
    """Correcting the label and leaving the number beside it is the same claim.

    The first fix gated only the first-order label. Step 3 could still hand these
    lines a confident `dd`, and step 4 still reported their spacings in a column
    headed "couplings" — measured, four signals kept 9.5 to 28.9 Hz couplings
    after their doublet labels had been withdrawn. A spacing between two
    independent carbons is a shift difference, not a coupling.
    """
    import glob
    import os

    from moltrace.spectroscopy.io.fid_reader import read_processed_spectrum
    from moltrace.spectroscopy.multiplet.analysis import detect_multiplets
    from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

    roots = sorted(
        {p.split("/pdata")[0] for p in glob.glob("tests/fixtures/**/pdata", recursive=True)}
    )
    spectrum = None
    for root in roots:
        try:
            candidate = read_processed_spectrum(os.fspath(root))
        except Exception:  # noqa: BLE001
            continue
        if "13C" in candidate.nucleus:
            spectrum = candidate
            break
    if spectrum is None:
        pytest.skip("no instrument-processed 13C acquisition in this checkout")

    offenders = []
    for multiplet in detect_multiplets(gsd_peak_pick(spectrum)):
        intensities = [max(float(p.intensity), 0.0) for p in multiplet.peaks]
        if len(intensities) < 2 or min(intensities) <= 0:
            continue
        if not _intensities_fit_a_multiplet(multiplet.peaks) and multiplet.j_couplings_hz:
            offenders.append(
                (round(multiplet.center_ppm, 3), [round(j, 1) for j in multiplet.j_couplings_hz])
            )
    assert not offenders, (
        f"signals whose intensities rule out a multiplet still report couplings: {offenders[:4]}"
    )


def test_a_pattern_that_FITS_keeps_its_couplings() -> None:
    """The false-positive half. Withdrawing every coupling would also be wrong."""
    import glob
    import os

    from moltrace.spectroscopy.io.fid_reader import read_processed_spectrum
    from moltrace.spectroscopy.multiplet.analysis import detect_multiplets
    from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

    roots = sorted(
        {p.split("/pdata")[0] for p in glob.glob("tests/fixtures/**/pdata", recursive=True)}
    )
    for root in roots:
        try:
            spectrum = read_processed_spectrum(os.fspath(root))
        except Exception:  # noqa: BLE001
            continue
        multiplets = detect_multiplets(gsd_peak_pick(spectrum))
        keeping = [
            m
            for m in multiplets
            if m.multiplicity_label not in {"s", "m"} and m.j_couplings_hz
        ]
        if keeping:
            return
    pytest.skip("no first-order multiplet with couplings in this checkout")
