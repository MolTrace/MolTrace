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

CORRECTED 2026-08-06. The first version of this file claimed a median 21.1%
error with small peaks under-reported to -71.5%, and concluded the pipeline does
not recover true proton ratios. **That was wrong, and it was wrong in a
particular way worth recording.**

The 21.1% came from comparing reported integrations against a midpoint
partition of the trace that the TEST computed -- every point assigned to its
nearest reported peak. That is not how the pipeline integrates, so the number
measured the disagreement between two window methods and then blamed the
pipeline for it.

Measured against the pipeline's own fitted areas on the identical run (19 peaks,
353 H): **median 1.7%, worst 8.8%, 14 of 14 within 10%.** The area -> proton
scaling is faithful.

What that does NOT establish is whether the fitted AREAS are right. They come
from raw local-maximum cluster sums, and the deconvolution fit that could
correct them is discarded (see tests/test_gsd_fitted_areas.py, phase A4). That
is the open question; this file no longer pretends to answer it.

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

#: Median relative error between each peak's share of the reported proton total
#: and its share of the pipeline's own fitted area, on exp 10. This measures the
#: SCALING step only. Re-baselined 2026-08-06 from a bogus 21.1% -- see the
#: module docstring.
MEASURED_MEDIAN_ERROR_PCT = 1.7
MEASURED_WORST_ERROR_PCT = 8.8


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


def test_the_area_to_proton_scaling_is_faithful() -> None:
    """Each peak's share of the reported protons matches its share of the areas.

    This is the step the pipeline is actually responsible for once areas exist:
    turning areas into proton numbers without distorting their ratios. Measured
    1.7% median / 8.8% worst, 14 of 14 within 10%.

    It deliberately compares against the pipeline's OWN fitted areas rather than
    against a trace partition computed here. The earlier version of this test did
    the latter and reported 21.1%, which was the disagreement between two window
    methods rather than an error in the pipeline.
    """
    import numpy as np

    from nmrcheck.spectrum import _infer_peak_estimates, parse_processed_spectrum

    ppm, y = _load_trace()
    csv = "ppm,intensity\n" + "\n".join(f"{p:.6f},{v:.6f}" for p, v in zip(ppm, y))
    report = parse_processed_spectrum(
        filename="exp10.csv", content=csv.encode(), solvent="CDCl3", frequency_mhz=500.163
    )
    peaks = sorted(report.inferred_peaks, key=lambda p: -p.shift_ppm)
    heights = np.array([p.integration_h for p in peaks], dtype=float)

    estimates = _infer_peak_estimates(
        list(zip(ppm.tolist(), y.tolist())), frequency_mhz=500.163
    )
    by_shift = {round(e.shift_ppm, 2): e.area for e in estimates}
    areas = np.array([by_shift.get(round(p.shift_ppm, 2), np.nan) for p in peaks])
    matched = ~np.isnan(areas)
    assert matched.sum() >= 8, f"only matched {matched.sum()} peaks back to an area"

    share_area = areas[matched] / areas[matched].sum()
    share_h = heights[matched] / heights[matched].sum()
    error = np.abs((share_h - share_area) / share_area * 100.0)

    assert float(np.median(error)) == pytest.approx(MEASURED_MEDIAN_ERROR_PCT, abs=3.0), (
        f"area-to-proton scaling drifted: median {np.median(error):.1f}% vs the "
        f"pinned {MEASURED_MEDIAN_ERROR_PCT}%"
    )
    assert (error < 10.0).all(), (
        f"a peak's proton share diverged from its area share by {error.max():.1f}%"
    )


def test_whether_the_areas_themselves_are_right_is_not_settled_here() -> None:
    """Names the open question instead of pretending this file answers it.

    The scaling above is faithful, but it inherits whatever the areas are. Those
    come from raw local-maximum cluster sums; the pseudo-Voigt fit that could
    correct them is computed and discarded (A4). So a spectrum can pass this
    test and still report wrong proton counts if the windows are wrong.

    Pinned as a reminder that "1.7% error" is a statement about one stage, not
    about the product's accuracy.
    """
    import inspect

    from nmrcheck import spectrum

    source = inspect.getsource(spectrum._cluster_peak_components)
    assert "area=total_area" in source, (
        "cluster areas no longer come from the pre-deconvolution sum — if the "
        "fit now feeds them, re-measure A1 against exp 10 and re-baseline"
    )


def test_the_reported_values_land_on_the_half_proton_grid() -> None:
    """The quantiser is real and worth knowing about, independent of the above.

    On a 1 H signal a 0.5 H grid is 50% granularity; on a 25 H multiplet it is
    2%. That size-dependence is a genuine property of the output even though it
    is not the 21% error this file once claimed.
    """
    import numpy as np

    from nmrcheck.spectrum import parse_processed_spectrum

    ppm, y = _load_trace()
    csv = "ppm,intensity\n" + "\n".join(f"{p:.6f},{v:.6f}" for p, v in zip(ppm, y))
    report = parse_processed_spectrum(
        filename="exp10.csv", content=csv.encode(), solvent="CDCl3", frequency_mhz=500.163
    )
    heights = np.array([p.integration_h for p in report.inferred_peaks], dtype=float)
    assert all(abs(h * 2 - round(h * 2)) < 1e-9 for h in heights)
    assert heights.max() / heights.min() > 50, (
        "this fixture is expected to span a wide dynamic range"
    )
