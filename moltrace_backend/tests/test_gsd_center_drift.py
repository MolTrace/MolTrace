"""A fitted line may refine its position; it may not walk onto its neighbour.

**These are xfail, and the defect is still live.** Three fixes were measured and
none of them is shippable yet; what each one cost is written at the foot of this
file. They are here because the measurement is the expensive part and it is done.

``gsd_peak_pick`` detects apexes, then fits each one. The fit window is several
line widths wide, so on a resolved multiplet it contains the neighbouring lines
too — and the fitted ``center`` was free to move anywhere inside that window. A
seeded line could therefore converge onto the minimum belonging to the line
beside it, at which point ``_deduplicate_peaks`` deleted it as a duplicate of
the line it had just become. The detector found the line; the fitter lost it.

Measured over the 20-fixture A/B corpus, as a fraction of the gap to the nearest
detected neighbour: the legitimate population is tight (median 0.047, only 32 of
475 lines past 0.25) and then there is a gap in the distribution, and 151 of 475
lines sat past 0.5 — beyond the midpoint, on the neighbour's side of it.

Which line was lost depended on the optimiser, so this reached CI as a
platform-dependent failure: on macOS/ARM the 4.1416 ppm line of the 60000016
ethyl quartet was swallowed, on Linux/x86 the 4.1837 one was.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.peaks.gsd import gsd_peak_pick

_AB_JSON = (
    Path(__file__).parent
    / "fixtures"
    / "gsd_prompt3_validation"
    / "fe_ab_legacy_vs_gsd_20260527.json"
)

#: The four lines of the ethyl quartet in nmrshiftdb2 60000016, in ppm. Evenly
#: spaced at 0.0138-0.0143 ppm (7.0-7.2 Hz at 500 MHz) — a textbook OCH2CH3
#: quartet, and every one of the four is a line a chemist reads off the table.
_QUARTET_PPM = (4.1416, 4.1554, 4.1697, 4.1840)

#: Half the smallest spacing in that quartet: close enough to say the reported
#: line IS this line, and not so loose that two of them could satisfy one target.
_QUARTET_TOL_PPM = 0.006


def _lorentzian(x: np.ndarray, centre: float, height: float, hwhm: float) -> np.ndarray:
    return height * hwhm**2 / ((x - centre) ** 2 + hwhm**2)


def _synthetic_quartet() -> NMRSpectrum:
    """Four equal lines at the spacing, width and digital resolution of the real one.

    0.00115 ppm per point and a 0.0040 ppm half-width are read off the 60000016
    acquisition; the four centres are its quartet. Nothing about the geometry is
    chosen to provoke the failure — it is the acquisition, with the line positions
    known instead of inferred.
    """
    x = np.linspace(3.6, 4.7, 960)
    y = np.zeros_like(x)
    for centre in _QUARTET_PPM:
        y += _lorentzian(x, centre, 1000.0, 0.0040)
    y += np.random.default_rng(11).normal(0.0, 1.0, x.size)
    return NMRSpectrum(data=y, ppm_axis=x, nucleus="1H", solvent="cdcl3", field_mhz=500.0)


def _captured_60000016() -> NMRSpectrum:
    if not _AB_JSON.exists():
        pytest.skip("FE A/B dump not present")
    payload = json.loads(_AB_JSON.read_text())
    run = next(
        (r for r in payload["ab_runs"] if r["fixture_id"] == "nmrshiftdb2_60000016_1h"),
        None,
    )
    if run is None:
        pytest.skip("60000016_1h not in the A/B dump")
    legacy = run["legacy"]
    return NMRSpectrum(
        data=np.asarray(legacy["y"], dtype=float),
        ppm_axis=np.asarray(legacy["x"], dtype=float),
        nucleus=run["nucleus"],
        solvent=legacy.get("solvent") or "",
        field_mhz=float(legacy.get("field_mhz") or 500.0),
    )


def _missing_quartet_lines(spectrum: NMRSpectrum) -> list[float]:
    found = np.asarray([peak.position_ppm for peak in gsd_peak_pick(spectrum, level=2)])
    if found.size == 0:
        return list(_QUARTET_PPM)
    return [
        line
        for line in _QUARTET_PPM
        if float(np.min(np.abs(found - line))) > _QUARTET_TOL_PPM
    ]


@pytest.mark.xfail(strict=True, reason="live defect: a fit walks onto its neighbour and is deduplicated away")
def test_a_resolved_quartet_keeps_all_four_lines_synthetic() -> None:
    """Four lines went in; four lines must come out.

    The arbiter is a spectrum whose line positions we chose, not another
    detector's opinion of a real one.
    """
    missing = _missing_quartet_lines(_synthetic_quartet())
    assert not missing, (
        f"{len(missing)} of 4 planted quartet lines were not reported: {missing}. "
        "Each was detected as an apex; a fit that relocated onto its neighbour is "
        "the only way one goes missing."
    )


@pytest.mark.xfail(strict=True, reason="live defect: a fit walks onto its neighbour and is deduplicated away")
def test_a_resolved_quartet_keeps_all_four_lines_on_real_data() -> None:
    """The same quartet, in the acquisition CI actually failed on."""
    missing = _missing_quartet_lines(_captured_60000016())
    assert not missing, (
        f"{len(missing)} of the 4 lines of the 60000016 ethyl quartet are not "
        f"reported: {missing}."
    )


# WHAT WAS TRIED, AND WHAT EACH ONE COST
#
# All three were measured against the 20-fixture A/B envelope, which fails 1
# fixture today (60000016_1h, and only on Linux).
#
#   1. Bound the fitted `center` to the line's own half of the gap.
#      WORSE: 2-3 of the 4 quartet lines missing instead of 1. A bounded fit does
#      not decline to walk, it parks on its bound — a wrong position reported
#      with confidence rather than a wrong position rejected.
#
#   2. Also clip the fit WINDOW to that half-gap, so the data being fitted is the
#      line and not the multiplet. Fixes both tests above. Cost: 9 of 20 A/B
#      fixtures red, because narrowing the data moves the fitted centre of every
#      line that has a neighbour — far more than the defect.
#
#   3. Leave the fit unconstrained and REJECT a result that landed outside its own
#      half-gap, falling back to the detected apex. Fixes both tests above, and
#      the smallest of the three: 5 of 20 A/B fixtures red. Two of those five are
#      the captured baseline being wrong (40255339: captured 1.5663, apex 1.5829
#      at 1165 sigma — the live run reports the apex and the capture reports the
#      drift). The other three are real losses this introduced: 40256166_13c
#      loses apexes at 10, 20 and 27 sigma that the capture had right.
#
# So it is entangled with detection and deduplication, not a local fix to the
# fitter, and the arbiter that ought to settle it cannot yet: scored on
# eval.detector_corpus, options 1-3 are IDENTICAL to no change at all
# (recall 73/90 quantifiable, 263 false positives either way). The corpus plants
# its lines further apart than the gap this defect lives in, so it is blind to
# it. A corpus that resolves this needs planted MULTIPLETS at measured J.
