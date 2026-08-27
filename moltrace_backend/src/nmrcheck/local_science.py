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

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from moltrace.spectroscopy.io.fid_reader import (
    FIDReaderError,
    NMRSpectrum,
    read_fid,
    read_processed_spectrum,
)
from moltrace.spectroscopy.multiplet.analysis import detect_multiplets
from moltrace.spectroscopy.peaks import gsd_peak_pick
from moltrace.spectroscopy.peaks.gsd import _MAX_PEAKS_BY_LEVEL


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


#: Text the reader writes for a developer, which must not reach a chemist: a
#: function name, a module path, or the absolute path of their own file.
_DEVELOPER_WORDS = re.compile(
    r"\b\w+\(\)"                      # a function call, e.g. "use read_fid()"
    r"|\bread_fid\b|\bread_processed_spectrum\b"
    r"|(?:/[\w.-]+){2,}"                # an absolute path
)


def _readable_refusal(error: Exception, source: Path) -> str:
    """Why it could not be opened, without naming the machinery or the path."""
    text = str(error).replace(str(source), source.name)
    if _DEVELOPER_WORDS.search(text):
        return (
            "that acquisition is not in a form this can read: it holds neither a processed "
            "spectrum nor a readable free-induction decay"
        )
    return text


def _readable_name(source: Path) -> str:
    """What to call this acquisition on screen.

    A Bruker experiment lives in a NUMBERED directory inside the dataset -- so
    the last path segment is "251" or "10", which tells a chemist nothing about
    which sample they just opened. Measured on a real acquisition: the name shown
    was "251". Where the segment is purely a number, the dataset name above it is
    the part that identifies the work, so both are shown.

    The full path is never returned. A path carries a compound name into a
    screenshot, and this string is rendered.
    """
    if source.name.isdigit() and source.parent.name:
        return f"{source.parent.name}/{source.name}"
    return source.name


#: How many buckets the display trace is reduced to. A spectrum is hundreds of
#: thousands of points and a screen is about a thousand wide, so something has to
#: give; this is what gives.
_TRACE_BUCKETS = 1200


def _display_trace(
    ppm_axis, intensity, multiplets: list[MultipletSummary]
) -> dict:
    """A drawable reduction of the spectrum — and the reduction is the hard part.

    **A MIN/MAX ENVELOPE, not every Nth point.** Measured on a 524,288-point
    acquisition: taking every Nth point left the tallest peak at 19.9% of its
    real height, because an NMR line is a handful of points wide and a stride
    steps straight over it. Keeping the minimum AND maximum of each bucket
    reproduced it at 100%. A chemist looking at a trace that silently shortened
    its own peaks would be right not to trust anything else on the screen.

    **The window is where the signal is, and the full sweep is reported beside
    it.** A 1H acquisition may sweep -44 to 263 ppm while every signal sits
    between 0 and 10; drawn end to end the spectrum is a flat line with a spike.
    So the window follows the detected signals, padded — and `sweep_ppm` says
    what was left out, because a trimmed axis that does not admit it is a claim
    that nothing lies outside.
    """
    import numpy as np

    x = np.asarray(ppm_axis, dtype=float)
    y = np.asarray(intensity, dtype=float)

    if multiplets:
        lo = min(m.range_ppm[0] for m in multiplets)
        hi = max(m.range_ppm[1] for m in multiplets)
        pad = max((hi - lo) * 0.05, 0.2)
        lo, hi = lo - pad, hi + pad
        window = (x >= lo) & (x <= hi)
        if window.sum() < 16:      # too few points to draw; fall back to everything
            window = np.ones_like(x, dtype=bool)
    else:
        window = np.ones_like(x, dtype=bool)

    xw, yw = x[window], y[window]
    buckets = min(_TRACE_BUCKETS, len(xw))
    if buckets < 2:
        return {
            "ppm": [], "min": [], "max": [],
            "points_represented": int(len(xw)),
            "sweep_ppm": [float(x.max()), float(x.min())],
        }

    edges = np.array_split(np.arange(len(xw)), buckets)
    return {
        # Highest ppm FIRST. An NMR spectrum is read right to left, and a plot
        # that runs the other way is one a chemist has to translate every time.
        "ppm": [float(xw[b[0]]) for b in edges],
        "min": [float(yw[b].min()) for b in edges],
        "max": [float(yw[b].max()) for b in edges],
        "points_represented": int(len(xw)),
        "sweep_ppm": [float(x.max()), float(x.min())],
    }


#: The level gsd_peak_pick defaults to. Named here so the ceiling this module
#: compares against is the ceiling that will actually apply.
_DEFAULT_GSD_LEVEL = 2


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

    # TWO WAYS IN, and which one was used changes what the numbers mean.
    #
    # An acquisition may carry a spectrum the instrument already processed, or
    # only the raw time-domain data it was derived from. Reading the processed
    # one first is deliberate: it is what the chemist saw on the spectrometer,
    # and reproducing their own numbers is worth more than improving on them.
    #
    # Falling back matters more than it sounds. Measured across every acquisition
    # in this repository: 7 of 23 carry a processed spectrum and 16 carry only the
    # FID -- so reading the processed one ALONE refuses two thirds of real
    # datasets, including every 400-600 MHz acquisition here. What comes off an
    # instrument is usually the FID.
    #
    # Any reader failure falls through rather than matching on the message text.
    # Deciding by message means a reworded exception silently becomes a refusal.
    processing = "instrument"
    try:
        spectrum = read_processed_spectrum(source)
    except (FIDReaderError, OSError, ValueError):
        try:
            spectrum = read_fid(source)
            processing = "moltrace"
        except FIDReaderError as unreadable:
            # The reader's words describe the FORMAT rather than the sample, but
            # they are written for a developer and name functions. Neither the
            # path nor the internals go out: a filename can carry a compound
            # name, and this cause is written to the device journal.
            raise SpectrumUnreadable(_readable_refusal(unreadable, source)) from None
        except (OSError, ValueError) as unreadable:
            raise SpectrumUnreadable(
                f"that file could not be read as a spectrum ({type(unreadable).__name__})"
            ) from None

    peaks = gsd_peak_pick(spectrum)

    # DID THE DETECTOR RUN OUT OF ROOM? It keeps at most a fixed number of
    # candidates per level and discards the rest by prominence, so a spectrum
    # that hits the ceiling has been TRUNCATED and the count below is a floor
    # rather than a finding.
    #
    # Measured across this repository's acquisitions: four instrument-processed
    # 13C spectra came back with exactly 220 lines -- the level-2 ceiling -- and
    # were then reported as 68 to 188 distinct signals. No 13C spectrum of a real
    # compound has 188 carbons, and a chemist shown that number would stop
    # trusting everything beside it.
    #
    # Read from the engine's own constant rather than repeated here. One number
    # written down twice is one that gets raised in one place.
    ceiling = _MAX_PEAKS_BY_LEVEL[_DEFAULT_GSD_LEVEL]
    saturated = len(peaks) >= ceiling

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

    trace = _display_trace(spectrum.ppm_axis, spectrum.data, summaries)

    return {
        "trace": trace,
        "nucleus": spectrum.nucleus,
        "field_mhz": float(spectrum.field_mhz),
        "points": int(len(spectrum.data)),
        "file_name": _readable_name(source),
        "processing": processing,
        "saturated": saturated,
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
            *(
                []
                if not saturated
                else [
                    "The peak detector reached the most lines it will fit for one spectrum, so "
                    "anything weaker than those was discarded. Treat the count below as a floor "
                    "rather than a result, and do not read the weakest signals as real."
                ]
            ),
            *(
                []
                if processing == "instrument"
                else [
                    "This acquisition held no processed spectrum, so one was computed here from "
                    "the "
                    "raw measurement using this application's own phasing and baseline settings. "
                    "Those settings are not the ones your spectrometer used, so shifts and "
                    "integrals can differ from the printout it produced."
                ]
            ),
        ],
    }
