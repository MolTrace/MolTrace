"""NMRShiftDB2's curated carbon shifts, as ground truth for the 13C line list.

**Why this exists.** ``detector_corpus`` plants lines in synthetic noise, which is
the only way to ask where the line between signal and noise belongs. It cannot
ask the other question: on a real acquisition, are the lines this platform reports
the carbons that are actually in the molecule? For that the answer has to come
from outside the platform, and the fixtures already carry one -- every acquisition
under ``tests/fixtures/nmrshiftdb2`` ships with the submitting chemist's assigned
shift list in the NMReDATA record beside it.

**What it can and cannot settle.** A curated list holds the ASSIGNED carbons and
nothing else, so solvent, satellites and impurities are legitimately absent from
it. Lines matching no assigned carbon are therefore not false positives; they are
only comparable BETWEEN two versions of the platform on the same corpus. Recall --
assigned carbons the platform finds -- is the number that means something on its
own.

**Referencing.** Between an acquisition and its curated list the referencing
differs by up to ~0.6 ppm on this corpus, so a fixed match window scores the
referencing rather than the detector. Callers should remove a per-spectrum median
offset before matching; :func:`recall_against_curated` does.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

#: Where the NMReDATA records live, relative to the backend package root.
_DEFAULT_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "nmrshiftdb2"
    / "source"
    / "nmrshiftdb2rawdata.nmredata.sd"
)

_SPECTRUM_ID = re.compile(r"spectrumid=(\d+)")
_SHIFT_LINE = re.compile(r"^(-?\d+\.?\d*)\s*,\s*L=")
_CARBON_BLOCK = re.compile(r"<NMREDATA_1D_13C>(.*?)(?:\n>|\n\$\$\$\$)", re.S)

#: Windows where a solvent line is expected and correctly absent from a curated
#: carbon list: CDCl3, DMSO-d6, benzene-d6, methanol-d4, acetone-d6.
SOLVENT_WINDOWS: tuple[tuple[float, float], ...] = (
    (76.5, 78.0),
    (38.5, 40.5),
    (127.5, 129.0),
    (28.5, 30.5),
    (205.5, 207.5),
)

#: Estimated over this window, then removed, so matching does not score referencing.
_OFFSET_WINDOW_PPM = 1.0
#: What counts as the same line once referencing is out of the way.
_MATCH_PPM = 0.25


def curated_carbon_shifts(source: Path | None = None) -> dict[str, list[float]]:
    """``spectrum id -> assigned 13C shifts``, from the NMReDATA records."""

    path = source or _DEFAULT_SOURCE
    if not path.exists():
        return {}
    text = path.read_text(errors="replace")
    out: dict[str, list[float]] = {}
    for block in _CARBON_BLOCK.findall(text):
        found = _SPECTRUM_ID.search(block)
        if not found:
            continue
        shifts = [
            float(match.group(1))
            for match in (
                _SHIFT_LINE.match(line.strip().rstrip("\\").strip())
                for line in block.splitlines()
            )
            if match
        ]
        if shifts:
            out[found.group(1)] = sorted(shifts)
    return out


def recall_against_curated(
    reported_ppm: list[float], curated_ppm: list[float]
) -> tuple[int, int, int]:
    """``(carbons found, carbons assigned, lines matching no assigned carbon)``.

    A per-spectrum median referencing offset is removed first, and each assigned
    carbon may claim at most one reported line, so a cluster of lines on one
    carbon cannot inflate recall. Solvent windows are excluded from the extras.
    """

    truth = sorted(float(value) for value in curated_ppm)
    lines = np.asarray(sorted(float(value) for value in reported_ppm), dtype=float)
    if not truth:
        return 0, 0, int(lines.size)
    if lines.size == 0:
        return 0, len(truth), 0

    rough = [
        float(lines[int(np.argmin(np.abs(lines - t)))] - t)
        for t in truth
        if abs(float(lines[int(np.argmin(np.abs(lines - t)))] - t)) <= _OFFSET_WINDOW_PPM
    ]
    adjusted = lines - (float(np.median(rough)) if rough else 0.0)

    found = 0
    claimed: set[int] = set()
    for t in truth:
        candidates = [
            (abs(float(adjusted[j] - t)), j)
            for j in range(adjusted.size)
            if j not in claimed and abs(float(adjusted[j] - t)) <= _MATCH_PPM
        ]
        if candidates:
            found += 1
            claimed.add(min(candidates)[1])

    extras = sum(
        1
        for j in range(lines.size)
        if j not in claimed
        and not any(low <= float(lines[j]) <= high for low, high in SOLVENT_WINDOWS)
    )
    return found, len(truth), extras

#: A curated carbon whose own position carries less than this, in units of the
#: spectrum's MAD noise, is not something any detector could report. Set at the
#: conventional limit of detection rather than the 10x limit of quantitation, so
#: the denominator below is generous to the detector rather than flattering.
DETECTABLE_SNR = 3.0


def local_snr_at(
    positions_ppm: list[float],
    *,
    ppm_axis: np.ndarray,
    signal: np.ndarray,
    half_window_ppm: float,
) -> list[float]:
    """Peak height within +/-``half_window_ppm`` of each position, over MAD noise.

    **Recall against a curated list is not a detector score until this is asked.**
    On this corpus the carbons the platform does not report have a median local SNR
    of 0.7 and NONE of the 37 reaches 10 -- they are quaternary carbons with no NOE
    and too few scans, and there is nothing at their positions to find. A recall
    figure that counts them scores the acquisition, not the detector, and it was
    twice called under-detection before anyone measured it.

    Report recall over the carbons that ARE present alongside the raw figure, and
    say which is which.
    """

    centred = signal - float(np.median(signal))
    mad = 1.4826 * float(np.median(np.abs(centred - float(np.median(centred)))))
    if not np.isfinite(mad) or mad <= 0.0:
        return [float("nan")] * len(positions_ppm)
    out: list[float] = []
    for position in positions_ppm:
        mask = np.abs(ppm_axis - position) <= half_window_ppm
        out.append(float(np.max(centred[mask])) / mad if mask.any() else float("nan"))
    return out
