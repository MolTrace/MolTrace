"""A fitted line may not be wider than the data that constrained it.

`_fit_single_with_model` bounds sigma at `max(span, step)` where `span` is the
width of that peak's own fit window. Both `LorentzianModel` and
`PseudoVoigtModel` define ``fwhm = 2 * sigma``, so the bound permits a fitted
line **exactly twice as wide as the window it was fitted on** -- and lmfit's
``amplitude`` is the integral to infinity, so the area such a fit reports is
mostly extrapolation into trace the fit never saw.

Measured before this bound was changed, on one reference acquisition: 4 of 31
peaks sat at that bound (fwhm/window 1.973, 2.000, 2.000, 2.000), one of them
reporting an area of which only 29.7% lay inside its own window. Three sat under
a single multiplet envelope each claiming most of it, which is how summing fitted
areas inflated that spectrum's total by 2.15x.

This is the cheap, unambiguous guard on the fitter itself. It asserts nothing
about how wide a line SHOULD be -- only that a fit cannot claim to have measured
something wider than what it looked at.
"""

from __future__ import annotations

import glob
import math
import os
from pathlib import Path

import numpy as np
import pytest

from moltrace.spectroscopy.io.fid_reader import read_fid, read_processed_spectrum
from moltrace.spectroscopy.peaks import gsd_peak_pick


def _acquisitions() -> list[str]:
    return sorted({os.path.dirname(p) for p in glob.glob("tests/fixtures/**/pdata", recursive=True)})


def _fit_window_ppm(peak: object) -> float:
    """The width of the data this peak's fit actually saw.

    Read from the fit's own record, NOT recomputed. The first version of this
    guard rebuilt the window from the peak's FITTED width and passed on a corpus
    that violates it: `_local_fit_bounds` opens the window from the SEED width
    measured on the smoothed signal, so reconstructing it from the fitted width
    inflates it for precisely the runaway fits this exists to catch. Predicted
    red, came back green, and the test was what was wrong.
    """
    metadata = getattr(peak, "metadata", None) or {}
    recorded = metadata.get("fit_window_ppm")
    return float(recorded) if isinstance(recorded, (int, float)) else math.inf


@pytest.mark.slow
def test_no_fitted_line_is_wider_than_its_own_fit_window() -> None:
    """Across every acquisition in the corpus, on the shipped code path."""
    offenders: list[str] = []
    checked = 0

    for source in _acquisitions():
        path = Path(source)
        try:
            try:
                spectrum = read_processed_spectrum(path)
            except Exception:  # noqa: BLE001 - fall back exactly as the app does
                spectrum = read_fid(path)
            peaks = gsd_peak_pick(spectrum)
        except Exception:  # noqa: BLE001 - an unreadable acquisition is not this test's subject
            continue
        peaks = getattr(peaks, "peaks", peaks)
        field = float(spectrum.field_mhz) or 1.0

        for peak in peaks:
            checked += 1
            fwhm_ppm = float(peak.width_hz) / field
            window_ppm = _fit_window_ppm(peak)
            if not math.isfinite(window_ppm) or window_ppm <= 0:
                continue
            ratio = fwhm_ppm / window_ppm
            if ratio > 1.0:
                offenders.append(
                    f"{os.path.basename(source)} @ {peak.position_ppm:.4f} ppm: "
                    f"fwhm {peak.width_hz:.2f} Hz is {ratio:.3f}x its own fit window"
                )

    assert checked > 0, "no acquisition in this checkout produced a fitted peak"
    assert not offenders, (
        f"{len(offenders)} of {checked} fitted lines are wider than the data that constrained "
        f"them, so their reported area is mostly extrapolation:\n  "
        + "\n  ".join(offenders[:12])
    )
