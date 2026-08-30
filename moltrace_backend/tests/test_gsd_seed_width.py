"""The seeded half-height width, measured against lines of KNOWN width.

`_initial_peak_indices` seeds each peak's width with
`peak_widths(smoothed, indices, rel_height=0.5)`. scipy measures that at
`height - 0.5 * prominence`, and it computes prominence by walking outward to the
lowest point before a higher peak -- unbounded. On a trace with negative
excursions that walk reaches a trough far away and far below the baseline, so the
contour being measured at sits BELOW the baseline and the width runs until the
trace happens to fall that low.

Measured over the 22 public acquisitions: the prominence exceeds the peak's own
height above the baseline for 734 of 856 peaks -- 85.7%, so this was the normal
case rather than an edge one. One 13C peak of height 1.94e8 carried a prominence
of 9.59e8, 4.9x its own height, and seeded a width of 8871.9 Hz: a quarter of the
sweep.

That seed is upstream of the fit -- `_local_fit_bounds` sizes the fitting window
at about four times it -- which is why bounding the fitted linewidth did not move
it. The fit was never exceeding its bounds; it was being handed a window wide
enough to make a very broad line legal.

Ground truth here is planted rather than curated: lines of known FWHM in noise of
known width, so the arbiter is the construction and not another reading of the
same code.
"""

from __future__ import annotations

import numpy as np
import pytest


def _observed_half_width_hz(smoothed, axis, index, baseline, field_mhz):
    """Where the trace ACTUALLY falls to half this peak's height, read off the data.

    Independent of how the detector computes width: it walks outward from the
    apex until the trace first drops below half the apex height above the
    baseline. That is the definition of a half-height width, so it is a fair
    arbiter for the number the detector reports.
    """
    half = baseline + 0.5 * (smoothed[index] - baseline)
    left = index
    while left > 0 and smoothed[left] > half:
        left -= 1
    right = index
    while right < smoothed.size - 1 and smoothed[right] > half:
        right += 1
    return abs(float(axis[right]) - float(axis[left])) * field_mhz


def test_a_seeded_width_is_the_width_the_trace_actually_has() -> None:
    """Measured against the acquisitions, not against another reading of the code.

    Red before the fix: the seeded width was seven hundred times the width the
    trace has, because it was measured at a contour below the baseline.
    """
    import glob

    from moltrace.spectroscopy.io.fid_reader import read_fid, read_processed_spectrum
    from moltrace.spectroscopy.peaks.gsd import (
        _initial_peak_indices,
        _positive_peak_orientation,
        _robust_noise,
        _smooth_signal,
        _smooth_width,
    )

    roots = sorted({p.split("/pdata")[0] for p in glob.glob("tests/fixtures/**/pdata", recursive=True)})
    if not roots:
        pytest.skip("no acquisition in this checkout")

    checked = 0
    offenders: list[str] = []
    for root in roots:
        try:
            try:
                spectrum = read_processed_spectrum(root)
            except Exception:  # noqa: BLE001 - the other reader takes it
                spectrum = read_fid(root)
            axis = np.asarray(spectrum.ppm_axis, dtype=float)
            oriented = _positive_peak_orientation(np.asarray(spectrum.data, dtype=float))
            indices, widths, _ = _initial_peak_indices(
                axis, oriented, noise=_robust_noise(oriented),
                nucleus=spectrum.nucleus, level=2,
            )
        except Exception:  # noqa: BLE001 - unreadable acquisitions are another test's business
            continue
        if indices.size == 0:
            continue

        smoothed = _smooth_signal(oriented, _smooth_width(2))
        baseline = float(np.nanmedian(smoothed))
        field_mhz = float(spectrum.field_mhz)
        step_ppm = float(np.median(np.abs(np.diff(axis))))
        for index, width in zip(indices, widths, strict=False):
            observed = _observed_half_width_hz(smoothed, axis, int(index), baseline, field_mhz)
            if observed <= 0:
                continue
            checked += 1
            seeded = float(width) * step_ppm * field_mhz
            # Generous: smoothing, discretisation and a neighbouring line all move
            # this legitimately. 10x is far past any of them and far below the
            # 700x the defect produced.
            if seeded > observed * 10.0:
                offenders.append(
                    f"{axis[int(index)]:.2f} ppm: seeded {seeded:.1f} Hz, "
                    f"trace has {observed:.1f} Hz ({seeded / observed:.0f}x)"
                )

    assert checked, "no peak was examined, so this proves nothing"
    assert not offenders, (
        f"{len(offenders)} of {checked} seeded widths are not the width the trace has:\n  "
        + "\n  ".join(sorted(offenders, key=lambda t: -float(t.split("(")[1].split("x")[0]))[:6])
    )
