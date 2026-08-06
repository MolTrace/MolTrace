"""A1: does the processed-spectrum path recover TRUE proton ratios?

Every other quantitation test in this suite compares the pipeline against
synthetic Lorentzians whose areas we chose. This one compares it against a real
spectrum whose ratios nobody chose.

The fixture is one half of a matched pair -- same sample, same probe, same
pulse program (zg30), same solvent, differing only in recycle delay:

    exp 10   d1 22.005 s + AQ 7.995 s = 30.00 s   fully relaxed
    exp 11   d1  1.000 s + AQ 3.998 s =  5.00 s   routine

At 30 s recycle with a 30 degree pulse exp 10 is quantitative, which is what
makes it usable as ground truth: **its own trace areas ARE the true proton
ratios**, up to integration-window choice. So the pipeline can be checked
without anyone having to know the structure, and without an arbiter that could
itself be wrong.

Measured 2026-08-04 (median 21% error on isolated peaks, small peaks
systematically under-reported, worst -71.5%). These tests pin that measurement
so the number moves visibly when the scale chain is fixed, rather than being
re-discovered later. See docs/validation_playbook.md section A1.

The fixture lives in validation_fixtures/ and is gitignored (real customer
spectra are not committed to a public repo), so every test here skips when it
is absent. That is deliberate: a skip is honest, a synthetic stand-in would
quietly turn this into another test that cannot fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("nmrglue")

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "validation_fixtures"
    / "bruker"
    / "naw-1-244-54pt"
    / "10"
    / "pdata"
    / "1"
)

pytestmark = pytest.mark.skipif(
    not (FIXTURE / "1r").exists(),
    reason=(
        "matched-pair Bruker fixture absent (gitignored real spectra); "
        "stage validation_fixtures/bruker/naw-1-244-54pt to run A1"
    ),
)

#: Median relative error between reported proton share and true area share,
#: over well-isolated peaks, measured on exp 10. This is a BASELINE of current
#: behaviour, not a target -- the target is well under 5%, which is what
#: "readable as a proton count" means.
MEASURED_MEDIAN_ERROR_PCT = 21.1
MEASURED_WORST_ERROR_PCT = 71.5


def _load_trace():
    import nmrglue as ng
    import numpy as np

    dic, data = ng.bruker.read_pdata(str(FIXTURE))
    udic = ng.bruker.guess_udic(dic, data)
    uc = ng.fileiobase.uc_from_udic(udic, 0)
    ppm = uc.ppm_scale()
    y = np.asarray(data, dtype=float)
    # Baseline off the empty far-upfield region rather than assuming zero.
    y = np.clip(y - np.median(y[(ppm > -2.0) & (ppm < -0.5)]), 0, None)
    return ppm, y


def test_the_fixture_is_the_fully_relaxed_half_of_the_pair() -> None:
    """Guard the premise. If this is not quantitative, it is not ground truth."""
    from nmrcheck.acquisition_quality import assess_1h_acquisition, LEVEL_QUANTITATIVE

    acqus = FIXTURE.parent.parent / "acqus"
    text = acqus.read_text(errors="replace")

    assert "<zg30>" in text, "fixture is not a 30 degree pulse"
    sw_hz = float(text.split("##$SW_h=")[1].split()[0])
    td = int(text.split("##$TD=")[1].split()[0])
    d1 = float(text.split("##$D=")[1].split("\n")[1].split()[1])

    result = assess_1h_acquisition(
        relaxation_delay_s=d1, td=td, sw_hz=sw_hz, scans=16, pulse_program="zg30"
    )
    assert result.parameters["recycle_time_s"] == pytest.approx(30.0, abs=0.05)
    assert result.level == LEVEL_QUANTITATIVE, (
        "the ground-truth half of the pair must itself be judged quantitative, "
        f"got {result.level}"
    )


def test_reported_proton_ratios_still_deviate_from_the_true_area_ratios() -> None:
    """The A1 finding, pinned.

    This asserts the CURRENT (wrong) behaviour so the gap is tracked. When the
    scale chain improves, this test fails loudly and should be re-baselined
    downward -- deliberately, in the same change, with the new measurement
    written into MEASURED_MEDIAN_ERROR_PCT.
    """
    import numpy as np

    from nmrcheck.spectrum import parse_processed_spectrum

    ppm, y = _load_trace()
    csv = "ppm,intensity\n" + "\n".join(f"{p:.6f},{v:.6f}" for p, v in zip(ppm, y))
    report = parse_processed_spectrum(
        filename="exp10.csv",
        content=csv.encode(),
        solvent="CDCl3",
        frequency_mhz=500.163,
    )
    peaks = sorted(report.inferred_peaks, key=lambda p: -p.shift_ppm)
    assert len(peaks) >= 10, f"expected a populated spectrum, got {len(peaks)} peaks"

    centres = [p.shift_ppm for p in peaks]
    heights = np.array([p.integration_h for p in peaks], dtype=float)

    # Nearest-peak partition: every point is assigned to the reported peak it
    # is closest to, which is what an integration effectively does.
    edges = (
        [centres[0] + 0.5]
        + [(a + b) / 2 for a, b in zip(centres[:-1], centres[1:])]
        + [centres[-1] - 0.5]
    )
    areas = np.array(
        [
            float(np.trapezoid(y[(ppm >= lo) & (ppm <= hi)], -ppm[(ppm >= lo) & (ppm <= hi)]))
            for hi, lo in zip(edges[:-1], edges[1:])
        ]
    )

    share_area = areas / areas.sum()
    share_h = heights / heights.sum()
    error_pct = (share_h - share_area) / share_area * 100.0

    # Restrict to well-isolated peaks. Next to a very large neighbour the
    # partition above mis-assigns tail area, and that is a limitation of the
    # MEASUREMENT, not of the pipeline -- excluding those keeps the finding
    # about the pipeline.
    gap_left = [np.inf] + [centres[i - 1] - centres[i] for i in range(1, len(centres))]
    gap_right = [centres[i] - centres[i + 1] for i in range(len(centres) - 1)] + [np.inf]
    biggest_neighbour = [
        max(
            heights[i - 1] if i > 0 else 0.0,
            heights[i + 1] if i < len(centres) - 1 else 0.0,
        )
        for i in range(len(centres))
    ]
    isolated = [
        i
        for i in range(len(centres))
        if min(gap_left[i], gap_right[i]) > 0.15 and biggest_neighbour[i] < 40
    ]
    assert len(isolated) >= 4, f"too few isolated peaks to judge ({len(isolated)})"

    magnitude = np.abs(error_pct[isolated])
    median = float(np.median(magnitude))

    assert median == pytest.approx(MEASURED_MEDIAN_ERROR_PCT, abs=8.0), (
        f"processed-path proton-ratio error moved: median {median:.1f}% vs the "
        f"pinned {MEASURED_MEDIAN_ERROR_PCT}%. If this DROPPED, the scale chain "
        f"improved -- re-baseline this constant in the same change and say so."
    )


def test_small_peaks_are_the_ones_that_are_wrong() -> None:
    """Direction matters for the fix: the error is not random noise.

    Large multiplets come back close to right; the smallest signals are
    systematically UNDER-reported (worst measured -71.5%). A chemist reading a
    minor impurity or a single diagnostic proton is therefore the person most
    misled, which is the opposite of what an integration should degrade toward.
    """
    import numpy as np

    from nmrcheck.spectrum import parse_processed_spectrum

    ppm, y = _load_trace()
    csv = "ppm,intensity\n" + "\n".join(f"{p:.6f},{v:.6f}" for p, v in zip(ppm, y))
    report = parse_processed_spectrum(
        filename="exp10.csv",
        content=csv.encode(),
        solvent="CDCl3",
        frequency_mhz=500.163,
    )
    peaks = sorted(report.inferred_peaks, key=lambda p: -p.shift_ppm)
    heights = np.array([p.integration_h for p in peaks], dtype=float)

    smallest = heights.min()
    largest = heights.max()
    assert largest / smallest > 50, (
        "this fixture is expected to span a wide dynamic range; if it no longer "
        "does, the premise of the small-peak finding has changed"
    )
    # Every reported value lands on the 0.5 H quantiser grid.
    assert all(abs(h * 2 - round(h * 2)) < 1e-9 for h in heights), (
        "reported integrations are expected to be multiples of 0.5 H; the "
        "quantiser is part of what this baseline measures"
    )
