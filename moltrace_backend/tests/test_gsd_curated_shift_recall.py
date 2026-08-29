"""Does the 13C line list contain the carbons that are in the molecule?

``detector_corpus`` plants lines in synthetic noise and asks where the boundary
between signal and noise belongs. It cannot ask this: on a real acquisition, are
the lines reported the carbons that are actually there? The answer has to come
from outside the platform, and it ships with the fixtures -- the submitting
chemist's assigned shift list, in the NMReDATA record beside every acquisition.

This is the arbiter the fit-drift work was scored on, pinned so the improvement
cannot be given back quietly. Recall is what means something on its own: lines
matching no assigned carbon include solvent, satellites and impurities, so the
extras count compares two versions of the platform and nothing more.
"""

from __future__ import annotations

import glob
import os
import re
from pathlib import Path

import pytest

from moltrace.spectroscopy.eval.curated_shifts import (
    curated_carbon_shifts,
    recall_against_curated,
)
from moltrace.spectroscopy.io.fid_reader import read_fid, read_processed_spectrum
from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

#: Measured. Before the fit-drift fix this corpus scored 50 of 92 assigned carbons
#: with 254 unassigned lines; after it, 53 of 92 with 252. Pinned at the measured
#: value so a regression is a failure and an improvement is a visible re-baseline.
EXPECTED_CARBONS_FOUND = 53
TOTAL_ASSIGNED_CARBONS = 92
#: Unassigned lines may not grow. The detector over-picks on this corpus already
#: (348 lines for 92 carbons plus solvent); this pins that it does not get worse.
MAX_UNASSIGNED_LINES = 252


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

    found_total = truth_total = extras_total = 0
    per_spectrum: list[str] = []
    for spectrum_id, root, truth in acquisitions:
        spectrum = _open(root)
        if spectrum is None:
            continue
        reported = [peak.position_ppm for peak in gsd_peak_pick(spectrum, level=2)]
        found, assigned, extras = recall_against_curated(reported, truth)
        found_total += found
        truth_total += assigned
        extras_total += extras
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
    assert extras_total <= MAX_UNASSIGNED_LINES, (
        f"{extras_total} lines match no assigned carbon, up from "
        f"{MAX_UNASSIGNED_LINES}. Per spectrum: {detail}"
    )
