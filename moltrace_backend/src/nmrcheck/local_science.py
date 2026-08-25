"""The science the desktop runs locally.

A thin, deliberately narrow seam onto `moltrace.spectroscopy`. It exists so the
local service can serve `fid.process` without importing the cloud API's
dependency tree — which carries authorization, the database session factory, and
the query-parameter credential acceptor the desktop profile is required to
remove.

**The property that makes this servable offline is that it needs nothing.** No
database, no network, no authorization: it takes arrays in and returns numbers
out. That is asserted by test rather than assumed, because the moment it acquires
a dependency on any of the three it stops being an offline operation and the
policy table's classification becomes wrong.

It returns a plain summary rather than the engine's own `Peak`. The engine type
is free to grow fields — provenance, internal confidences, fitting diagnostics —
and a transport that forwards whatever it is given would publish them the day
they appear. This lists what crosses the boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from moltrace.spectroscopy.io.fid_reader import (
    FIDReaderError,
    NMRSpectrum,
    read_processed_spectrum,
)
from moltrace.spectroscopy.multiplet.analysis import detect_multiplets
from moltrace.spectroscopy.peaks import gsd_peak_pick


@dataclass(frozen=True)
class PeakSummary:
    """What crosses the boundary, enumerated."""

    position_ppm: float
    position_hz: float
    intensity: float
    area: float
    width_hz: float
    shape: str

    def to_dict(self) -> dict:
        return asdict(self)


def process_spectrum(
    *,
    ppm_axis: Sequence[float],
    intensity: Sequence[float],
    nucleus: str,
    field_mhz: float,
) -> list[PeakSummary]:
    """Pick peaks from a spectrum. Raises on input it cannot honestly analyse."""
    if len(ppm_axis) == 0 or len(intensity) == 0:
        # Zero peaks from an empty input is a true answer to a question nobody
        # asked, and a caller cannot tell it apart from "the analysis found
        # nothing", which is a different and meaningful result.
        raise ValueError("a spectrum with no points cannot be analysed")
    if len(ppm_axis) != len(intensity):
        raise ValueError(
            f"the ppm axis has {len(ppm_axis)} points and the intensities have "
            f"{len(intensity)}; they must describe the same spectrum"
        )

    spectrum = NMRSpectrum(
        data=np.asarray(intensity, dtype=float),
        ppm_axis=np.asarray(ppm_axis, dtype=float),
        nucleus=nucleus,
        field_mhz=field_mhz,
    )
    return [
        PeakSummary(
            position_ppm=float(p.position_ppm),
            position_hz=float(p.position_hz),
            intensity=float(p.intensity),
            area=float(p.area),
            width_hz=float(p.width_hz),
            shape=str(p.shape),
        )
        for p in gsd_peak_pick(spectrum)
    ]


@dataclass(frozen=True)
class MultipletSummary:
    """One multiplet, as a chemist reads a peak table.

    A raw peak list is not what a chemist reads, and showing one invites a
    specific and fair objection: this platform's peak detector over-picks, so a
    single environment appears as several "peaks" at the same shift. Measured on
    a public 1H reference acquisition: 30 picked peaks resolved to 8 multiplets,
    with five of those peaks being lines of ONE of them. Grouping is not
    presentation polish -- an ungrouped list misrepresents how many signals the
    spectrum contains.
    """

    name: str
    center_ppm: float
    range_ppm: tuple[float, float]
    multiplicity: str
    j_couplings_hz: list[float]
    line_count: int
    #: Area as a FRACTION OF THE TOTAL, never a proton count. Without an assigned
    #: structure there is nothing to normalise against, so a proton count would be
    #: an invention. The wire key says what it is; the display must not relabel it.
    relative_area: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "center_ppm": self.center_ppm,
            "range_ppm": list(self.range_ppm),
            "multiplicity": self.multiplicity,
            "j_couplings_hz": self.j_couplings_hz,
            "line_count": self.line_count,
            "relative_area": self.relative_area,
        }


class SpectrumUnreadable(ValueError):
    """The file is not a spectrum this service can read. Names no path."""


def open_spectrum(path: str) -> dict:
    """Read an acquisition off this computer and summarise what is in it.

    Takes a PATH rather than the arrays. A processed 1H acquisition is 131,072
    points, which is 3.6 MB of JSON -- measured -- and the service runs on the
    same machine as the caller under the same user, so handing it a filename
    costs one stat where handing it arrays costs a serialise, a copy and a parse.

    It reads whatever the caller can already read, and no more: same user, same
    authority. The credential on the transport is what stops anything ELSE on the
    machine reaching this.
    """
    source = Path(path)
    if not source.exists():
        raise SpectrumUnreadable("that file is no longer where it was")
    try:
        spectrum = read_processed_spectrum(source)
    except FIDReaderError as unreadable:
        # The reader's own words, which describe the FORMAT rather than the
        # sample. The path is deliberately not interpolated: a filename can carry
        # a compound name, and this cause is written to the device journal.
        raise SpectrumUnreadable(str(unreadable).replace(str(source), source.name)) from None
    except (OSError, ValueError) as unreadable:
        raise SpectrumUnreadable(
            f"that file could not be read as a spectrum ({type(unreadable).__name__})"
        ) from None

    peaks = gsd_peak_pick(spectrum)
    multiplets = detect_multiplets(peaks)
    total_area = sum(abs(p.area) for m in multiplets for p in m.peaks) or 1.0

    summaries = [
        MultipletSummary(
            name=m.name,
            center_ppm=float(m.center_ppm),
            range_ppm=(float(m.range_ppm[0]), float(m.range_ppm[1])),
            multiplicity=str(m.multiplicity_label),
            j_couplings_hz=[round(float(j), 2) for j in m.j_couplings_hz],
            line_count=len(m.peaks),
            relative_area=float(sum(abs(p.area) for p in m.peaks) / total_area),
        )
        for m in multiplets
    ]

    return {
        "nucleus": spectrum.nucleus,
        "field_mhz": float(spectrum.field_mhz),
        "points": int(len(spectrum.data)),
        "file_name": source.name,
        "peak_count": len(peaks),
        "multiplets": [m.to_dict() for m in summaries],
        # Stated by the engine, not by the interface, so a caller cannot render
        # the numbers without them. §7.1's readout rule in miniature: the limits
        # travel with the result.
        "limits": [
            "Shifts, multiplicities and couplings are measured from this spectrum alone. "
            "Nothing here has been checked against a proposed structure.",
            "Areas are shown relative to the whole spectrum. They are ratios, not proton counts: "
            "assigning protons needs a structure this analysis was not given.",
            "Multiplicity and coupling assignment is a fit. A crowded or overlapping region can "
            "be grouped more than one way.",
        ],
    }
