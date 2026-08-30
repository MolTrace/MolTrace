"""Does the 13C line list contain the carbons that are in the molecule?

``detector_corpus`` plants lines in synthetic noise and asks where the boundary
between signal and noise belongs. It cannot ask this: on a real acquisition, are
the lines reported the carbons that are actually there? The answer has to come
from outside the platform, and it ships with the fixtures -- the submitting
chemist's assigned shift list, in the NMReDATA record beside every acquisition.

This is the arbiter the fit-drift work was scored on, pinned so the improvement
cannot be given back quietly. Lines matching no assigned carbon include solvent,
satellites and impurities, so the extras count compares two versions of the
platform and nothing more.

**THE RAW RECALL IS NOT A DETECTOR SCORE, AND CHASING IT IS A KNOWN TRAP.** Local
SNR at each curated carbon's own position, this corpus:

    carbons FOUND   n=55   median local SNR  26.2
    carbons MISSED  n=37   median local SNR   0.7   (p90 2.9)
      missed with SNR <  3 : 33 of 37
      missed with SNR >= 10:  0 of 37

There is nothing at the positions of the carbons this platform does not report --
quaternary carbons, no NOE, too few scans. A detector cannot find a line that is
not there, so 55/92 measures these ACQUISITIONS and only the detectable subset
measures the detector. That subset was called "under-detection, a bigger problem
than the over-picking" three times by two sessions before anyone measured the SNR.

So both numbers are asserted below, and the one that can move is named as such.
"""

from __future__ import annotations

import glob
import os
import re
from pathlib import Path

import numpy as np
import pytest

from moltrace.spectroscopy.eval.curated_shifts import (
    DETECTABLE_SNR,
    curated_carbon_shifts,
    local_snr_at,
    recall_against_curated,
)
from moltrace.spectroscopy.io.fid_reader import read_fid, read_processed_spectrum
from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

#: Measured, and re-baselined twice, both times visibly:
#:
#:     baseline                       carbons  lines  unassigned
#:     before the fit-drift fix        50/92     348         254
#:     after it                        53/92     348         252
#:     after the sqrt(2 ln N) floor    52/92     184          96
#:     at fe28d2f / a0c3cbe            55/92       -           -
#:
#: The last row is not mine: the half-height width fix (a0c3cbe) and the broad-line
#: relabel (fe28d2f) landed from other sessions and took recall 52 -> 55. Re-pinned
#: at the measured value so this guard is not passing on slack.
#:
#: THE FLOOR COSTS ONE CARBON AND REMOVES 156 UNASSIGNED LINES. The carbon is
#: 130.3 ppm of 60000006, and its apex there stands at 3.6x MAD -- below the 10x
#: quantitation floor this platform draws everywhere else, and below the 4.71
#: sigma at which noise is EXPECTED to win somewhere in a 65,536-point spectrum.
#: Reporting it was luck rather than detection, and a line that cannot be read as
#: a number is not one a chemist loses anything by not seeing.
EXPECTED_CARBONS_FOUND = 55
#: Of the 92 assigned carbons, the ones whose own position carries any signal at
#: all. This is the denominator the detector is answerable for: 55/58 = 94.8%,
#: against 55/92 = 59.8% over the full list. Emitting it is the point -- a metric
#: over a subset that never states its coverage stops responding to the thing it
#: claims to measure.
EXPECTED_DETECTABLE_CARBONS = 58
MIN_RECALL_AMONG_DETECTABLE = 0.90
TOTAL_ASSIGNED_CARBONS = 92
#: Unassigned lines may not grow. The detector still over-picks on this corpus
#: (184 lines for 92 carbons plus solvent); this pins that it does not get worse.
MAX_UNASSIGNED_LINES = 96


def _acquisitions() -> list[tuple[str, Path, list[float]]]:
    curated = curated_carbon_shifts()
    out: list[tuple[str, Path, list[float]]] = []
    for directory in sorted(
        glob.glob("tests/fixtures/nmrshiftdb2/raw/extracted/*13c*")
    ):
        match = re.search(r"nmrshiftdb2_(\d+)_13c", os.path.basename(directory))
        if not match:
            continue
        truth = curated.get(match.group(1))
        if truth:
            out.append((match.group(1), Path(directory), truth))
    return out


def _open(root: Path):
    for reader in (read_processed_spectrum, read_fid):
        try:
            return reader(root)
        except Exception:  # noqa: BLE001 - any failure means "try the next reader"
            continue
    return None


@pytest.mark.slow
def test_reported_lines_recover_the_assigned_carbons() -> None:
    acquisitions = _acquisitions()
    if not acquisitions:
        pytest.skip("no 13C acquisitions with curated shifts in this checkout")

    found_total = truth_total = extras_total = detectable_total = 0
    per_spectrum: list[str] = []
    for spectrum_id, root, truth in acquisitions:
        spectrum = _open(root)
        if spectrum is None:
            continue
        peaks = gsd_peak_pick(spectrum, level=2)
        reported = [peak.position_ppm for peak in peaks]
        found, assigned, extras = recall_against_curated(reported, truth)
        found_total += found
        truth_total += assigned
        extras_total += extras

        # How many of these carbons are even present in the trace. The window is a
        # linewidth taken from the acquisition's own reported peaks, so it is the
        # spectrum's resolution rather than a constant.
        axis = np.asarray(spectrum.ppm_axis, dtype=float)
        trace = np.asarray(spectrum.data, dtype=float)
        if trace.ndim == 1 and axis.size == trace.size:
            widths = [p.width_hz for p in peaks if np.isfinite(p.width_hz)]
            field = float(getattr(spectrum, "field_mhz", 0.0) or 0.0)
            half = (
                2.0 * float(np.median(widths)) / field
                if widths and field > 0
                else 0.05
            )
            snrs = local_snr_at(
                truth, ppm_axis=axis, signal=np.abs(trace), half_window_ppm=half
            )
            detectable_total += sum(
                1 for v in snrs if np.isfinite(v) and v >= DETECTABLE_SNR
            )
        per_spectrum.append(f"{spectrum_id} {found}/{assigned} (+{extras})")

    detail = ", ".join(per_spectrum)
    assert truth_total == TOTAL_ASSIGNED_CARBONS, (
        f"the corpus changed size: {truth_total} assigned carbons, not "
        f"{TOTAL_ASSIGNED_CARBONS}. Re-baseline the counts here in the same change."
    )
    assert found_total >= EXPECTED_CARBONS_FOUND, (
        f"recall fell to {found_total}/{truth_total} from {EXPECTED_CARBONS_FOUND}: "
        f"carbons a chemist assigned are no longer reported. Per spectrum: {detail}"
    )
    # THE NUMBER THE DETECTOR IS ANSWERABLE FOR. Recall over the carbons that are
    # actually in the trace, reported next to the raw figure so neither can be read
    # without the other.
    detectable = max(detectable_total, 1)
    among_detectable = found_total / detectable
    assert detectable_total >= EXPECTED_DETECTABLE_CARBONS - 3, (
        f"only {detectable_total} of {truth_total} assigned carbons carry signal at "
        f"{DETECTABLE_SNR}x noise, against {EXPECTED_DETECTABLE_CARBONS} measured. "
        "The acquisitions changed, so the recall baselines below describe a "
        "different corpus and must be re-measured, not adjusted."
    )
    assert among_detectable >= MIN_RECALL_AMONG_DETECTABLE, (
        f"recall among DETECTABLE carbons is {among_detectable:.0%} "
        f"({found_total}/{detectable_total}), under {MIN_RECALL_AMONG_DETECTABLE:.0%}. "
        "This is the figure a detector change moves; the raw "
        f"{found_total}/{truth_total} is mostly these acquisitions. Per spectrum: {detail}"
    )
    assert extras_total <= MAX_UNASSIGNED_LINES, (
        f"{extras_total} lines match no assigned carbon, up from "
        f"{MAX_UNASSIGNED_LINES}. Per spectrum: {detail}"
    )
