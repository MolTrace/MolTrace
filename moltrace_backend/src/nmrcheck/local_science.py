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
from moltrace.spectroscopy.peaks.deconvolve import resolve_region
from moltrace.spectroscopy.peaks.gsd import (
    _MAX_PEAKS_BY_LEVEL,
    _distance_points,
)


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
    #: Apex height over the baseline noise width. The measure a chemist needs to
    #: decide whether a row is worth reading numbers off, and the one thing a
    #: peak table almost never shows.
    snr: float
    #: Whether this signal clears the limit of QUANTITATION, not merely detection.
    #: Detection and quantitation are different claims and this platform draws
    #: that line everywhere else; a peak table that does not draw it presents
    #: three-sigma bumps beside real carbons as if they were the same kind of
    #: thing.
    quantifiable: bool
    #: How many lines a deconvolution finds in this signal's window.
    #:
    #: The detector reports one maximum per resolvable feature, so two lines
    #: closer than about four linewidths arrive as ONE. Asking whether two
    #: Lorentzians explain the window better than one can — by more than noise
    #: allows — recovers pairs from about one linewidth apart. Where this exceeds
    #: `line_count`, the signal beside it is more than one line.
    resolved_lines: int
    #: The widest line in this signal, in Hz. Shown because two lines closer than
    #: the detector can separate are reported as ONE, and the tell is width:
    #: measured on planted pairs, a merged pair fits 3.3-4.5x the true linewidth
    #: while a single line fits 1.0-1.3x. It is NOT flagged automatically — on
    #: real acquisitions 14% of lines exceed 3x the median width and most are
    #: broad features or poor fits rather than merged pairs, so a flag would cry
    #: wolf. The number is shown; the chemist judges.
    width_hz: float
    #: What this signal appears to BE: the compound, the solvent, its residual
    #: proton, an impurity, a 13C satellite, or an artifact. A chemist otherwise
    #: identifies these by eye every time they read a spectrum, and the engine
    #: already knows: `classify_peaks` was computed nowhere and shown never.
    category: str
    #: How sure that call is, 0-1. Shown beside the category rather than used as
    #: a filter: a low number is information, not a reason to hide a row.
    category_confidence: float
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
            "snr": self.snr,
            "quantifiable": self.quantifiable,
            "line_count": self.line_count,
            "resolved_lines": self.resolved_lines,
            "width_hz": self.width_hz,
            "category": self.category,
            "category_confidence": self.category_confidence,
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


#: Where "a signal worth reading numbers off" starts, in noise sigmas. The
#: conventional limit of quantitation, and the floor below which this module
#: will not claim to resolve structure.
_QUANTIFIABLE_SIGMA = 10.0



def _summarise_multiplet(
    spectrum: NMRSpectrum,
    multiplet: object,
    baseline_sigma: float,
    total_area: float,
    snr: float,
    categories: dict[int, tuple[str, float]],
) -> MultipletSummary:
    """One signal, with every claim held to the floor this module declares.

    A MULTIPLICITY AND A COUPLING ARE STRUCTURAL CLAIMS, so they are withheld
    below `_QUANTIFIABLE_SIGMA` for the same reason `_resolved_line_count`
    refuses to split a signal there: a shape read off a three-sigma bump is a
    shape read off noise. This was applied to the line count and not to the
    label, so 227 of 227 signals below the floor still carried a pattern, 37 of
    them with a coupling constant attached. The worst was a triplet at J = 22.07
    Hz on a signal standing 3.8 times the baseline noise, in a proton-decoupled
    13C acquisition (PULPROG zgpg30, CPDPRG2 waltz16) whose experiment cannot
    produce a carbon-proton coupling at all.

    Withheld at the boundary rather than blanked in the display, because the
    label is a claim wherever it is read, and a reader added later would
    otherwise inherit it. `snr` is measured by the caller and passed in: it
    decides both the flag and which signals are reported at all, so computing it
    here as well would run the same measurement twice for one answer.
    """
    quantifiable = snr >= _QUANTIFIABLE_SIGMA
    return MultipletSummary(
        name=multiplet.name,
        center_ppm=float(multiplet.center_ppm),
        range_ppm=(float(multiplet.range_ppm[0]), float(multiplet.range_ppm[1])),
        multiplicity=str(multiplet.multiplicity_label) if quantifiable else "",
        j_couplings_hz=(
            [round(float(j), 2) for j in multiplet.j_couplings_hz] if quantifiable else []
        ),
        line_count=len(multiplet.peaks),
        width_hz=float(max((p.width_hz for p in multiplet.peaks), default=0.0)),
        # THE STRONGEST LINE DECIDES. A multiplet is one signal, so it gets one
        # answer, and the tallest line in it is the one the call was most
        # confident about -- averaging categories across lines would invent a
        # category nothing measured.
        **_multiplet_category(multiplet, categories),
        resolved_lines=_resolved_line_count(spectrum, multiplet, baseline_sigma),
        snr=snr,
        quantifiable=quantifiable,
        relative_area=float(sum(abs(p.area) for p in multiplet.peaks) / total_area),
    )



#: How the four verification tests are named to a chemist. The wire keys stay as
#: the engine emits them -- a display name is not a rename -- but `dp4_ranking` is
#: not what a person calls the thing it does.
_TEST_LABELS: dict[str, str] = {
    "prediction_bounds": "Predicted shifts against the observed ones",
    "assignments": "Every observed signal assigned to an atom",
    "hsqc_2d_ranges": "HSQC correlations (needs a 2-D spectrum)",
    "ms_molecule_match": "Mass-spectrometry evidence (needs MS peaks)",
}


def verify_candidate(path: str | Path, smiles: str) -> dict:
    """Check a proposed structure against an acquisition on this computer.

    THE VERIFIER IS THE ARBITER, and it runs here in full: `verify_structure` is
    the same deterministic function the platform uses everywhere, combining its
    tests through a Bayesian log-odds update whose whole arithmetic comes back on
    the result. Nothing about it needs a server.

    WHAT IS DIFFERENT OFFLINE IS THE PREDICTION IT IS FED. Without NMRNet the
    engine falls back to HOSE codes against a seed knowledge base, and on a real
    acquisition that meant half the atoms matched no environment at all and the
    median 13C uncertainty was 35 ppm -- which is most of the useful range. The
    engine says so in its own warnings. Those warnings are lifted to the front of
    this result rather than left at the end of a list, because a confidence read
    without them is a number a chemist could act on and should not.
    """
    source = Path(path)
    if not source.exists():
        raise SpectrumUnreadable("that file is no longer where it was")
    candidate = (smiles or "").strip()
    if not candidate:
        raise SpectrumUnreadable("no structure was given to check")

    from moltrace.spectroscopy.verification import verify_structure

    try:
        spectrum = read_processed_spectrum(source)
    except (FIDReaderError, OSError, ValueError):
        try:
            spectrum = read_fid(source)
        except FIDReaderError as unreadable:
            raise SpectrumUnreadable(_readable_refusal(unreadable, source)) from None

    try:
        result = verify_structure(spectrum, candidate)
    except ValueError as bad:
        # A structure the chemist typed that RDKit cannot read is their input, not
        # a fault: say which part failed rather than reporting a dead service.
        raise SpectrumUnreadable(
            f"that structure could not be read as a molecule ({bad})"
        ) from None

    warnings = list(result.warnings or [])

    # A TYPO IS NOT AN ANSWER. The engine handles an unreadable structure
    # honestly -- it warns `invalid_smiles`, abstains from every test, and returns
    # the prior back unchanged as `inconclusive` at 0.50. That is correct FOR THE
    # ENGINE and wrong to put in front of a person: a verdict and a confidence
    # rendered for a mistyped structure look exactly like a verdict and a
    # confidence for a real one, and the reader has no way to tell which they got.
    if any(w == "invalid_smiles" for w in warnings):
        raise SpectrumUnreadable(
            "that structure could not be read as a molecule. Check the SMILES \u2014 "
            "ethanol is CCO, benzene is c1ccccc1."
        )
    # The coverage line is the one that decides whether any of this is worth
    # reading, so it is pulled out rather than left as the last of nine.
    coverage = next((w for w in warnings if w.startswith("Coverage:")), None)
    predictor = next((w for w in warnings if "NMRNet unavailable" in w), None)

    return {
        "smiles": candidate,
        "verdict": str(result.verdict),
        "confidence": float(result.posterior_confidence),
        "prior": float(result.prior_confidence),
        "summary": str(result.diagnostic),
        "tests": [
            {
                "name": t.name,
                "label": _TEST_LABELS.get(t.name, t.name.replace("_", " ")),
                "applicable": bool(t.applicable),
                "score": float(t.score),
                "significance": float(t.significance),
                "quality": float(t.quality),
                "diagnostic": str(t.diagnostic),
            }
            for t in result.test_results
        ],
        # NOT A SCORE TO COMPARE CANDIDATES WITH, and this is measured rather than
        # cautious. On the ethylene glycol acquisition in this repository, checked
        # against four structures: ethylene glycol itself came back 0.556 and
        # ETHANOL came back 0.623 -- the wrong molecule outranked the right one,
        # with aspirin at 0.542 close behind. The engine is not at fault; it
        # returns "inconclusive" for all four, which is correct. What cannot carry
        # the weight is the prediction underneath, at a 35 ppm median uncertainty.
        #
        # So the desktop states this on every result rather than offering a ranked
        # candidate list. A list would put the wrong molecule first and look
        # exactly like a list that had put the right one first.
        "comparable_between_candidates": False,
        "prediction_coverage": coverage,
        "predictor_note": predictor,
        "warnings": warnings,
        # Every regulated result carries this, and a structure verdict is exactly
        # the kind of thing that must not be read as a decision.
        "human_review_required": True,
    }



def _multiplet_category(multiplet: object, categories: dict[int, tuple[str, float]]) -> dict:
    """What this signal appears to be, taken from its strongest line."""
    best: tuple[str, float] | None = None
    best_intensity = -1.0
    for peak in multiplet.peaks:
        found = categories.get(id(peak))
        if found is None:
            continue
        if float(peak.intensity) > best_intensity:
            best_intensity = float(peak.intensity)
            best = found
    if best is None:
        # Unclassified is a state, not a guess. An empty string renders as an em
        # dash and says nothing, which is the truth.
        return {"category": "", "category_confidence": 0.0}
    return {"category": str(best[0]), "category_confidence": float(best[1])}


def _has_processed_spectrum(source: Path) -> bool:
    """Did the instrument write one at all?

    Distinguishes the two reasons the processed read can fail. Looks for the file
    rather than parsing it, because the question is whether the chemist should
    expect one to be there -- and if it is there and unreadable, saying it is
    absent sends them to the wrong place.
    """
    root = source if source.is_dir() else source.parent
    return any(root.glob("pdata/*/1r"))


def _baseline_sigma(spectrum: NMRSpectrum) -> float:
    """The noise width, measured the way the detector measures it.

    A deconvolution decides whether a residual improvement is bigger than noise,
    so a noise figure that is wrong by 40% decides nothing. This is the same
    peak-free estimate the detector now uses.
    """
    from moltrace.spectroscopy.peaks.gsd import _positive_peak_orientation, _robust_noise

    oriented = _positive_peak_orientation(np.asarray(spectrum.data, dtype=float))
    signal = oriented - float(np.median(oriented))
    median = float(np.median(signal))
    peak_free = signal[signal <= median]
    if peak_free.size >= 8:
        reflected = np.concatenate([peak_free, 2.0 * median - peak_free])
        estimate = 1.4826 * float(np.median(np.abs(reflected - median)))
        if np.isfinite(estimate) and estimate > 0:
            return estimate
    return float(_robust_noise(signal))


def _signal_to_noise(spectrum: NMRSpectrum, multiplet, baseline_sigma: float) -> float:
    """How far this signal stands above the baseline, in noise widths.

    Measured from the OBSERVED apex rather than a fitted amplitude. A fitted
    amplitude can exceed the apex it models when the fit is broad, and mixing a
    fitted height with a noise estimate computed another way is how the same
    peaks were once measured at 14-23 sigma and then, on one consistent
    definition, at 1.8. One definition, used everywhere.
    """
    from moltrace.spectroscopy.peaks.gsd import _positive_peak_orientation

    if baseline_sigma <= 0:
        return 0.0
    axis = np.asarray(spectrum.ppm_axis, dtype=float)

    # THE APEX HAS TO BELONG TO THIS SIGNAL. This took `np.max` over the
    # multiplet's range padded by 1.5x its own span on each side -- so a window up
    # to 4x the signal's extent -- which meant a strong neighbour falling inside
    # the pad was reported as this row's height. Measured across the corpus: 7 of
    # 395 signals reported a height their own extent does not hold, and two rows
    # on one acquisition printed the SAME 509.0 against their own 42.6 and 14.6.
    # A number printed on a row has to describe that row.
    #
    # The window is built from this multiplet's own fitted line centres, each
    # taken to one of its own linewidths. That keeps what the padding was for --
    # a single-line multiplet has a zero-width range and an unpadded window holds
    # no points -- without reaching far enough to collect anything else. The
    # floor of two axis steps is what makes a zero-width fit still select points.
    #
    # Still the OBSERVED apex, never a fitted amplitude: a fit can exceed the
    # peak it models, and that is how these signals once measured 14-23 sigma and
    # then, on one consistent definition, 1.8.
    step = float(np.median(np.abs(np.diff(axis)))) if axis.size > 1 else 0.0
    field_mhz = float(getattr(spectrum, "field_mhz", 0.0) or 0.0)
    window = np.zeros(axis.shape, dtype=bool)
    for peak in multiplet.peaks:
        width_ppm = (float(peak.width_hz) / field_mhz) if field_mhz > 0 else 0.0
        reach = max(width_ppm, 2.0 * step)
        window |= np.abs(axis - float(peak.position_ppm)) <= reach

    # CLIPPED to the region the signal was already credited with. Attribution
    # must only ever REMOVE height this row does not own, never find it new
    # height, and without this clip it does exactly that: a fitted linewidth is
    # not bounded against the spectrum's own resolution, so one pathological fit
    # (8871.9 Hz, 50.4 ppm on a 13C acquisition) would reach far past anything
    # the padded range ever considered. Measured: unclipped, this moved 7 rows
    # ACROSS the quantitation floor upward -- a fix for over-reporting that
    # over-reported. Clipped, S/N can only fall or stay equal.
    low, high = min(multiplet.range_ppm), max(multiplet.range_ppm)
    pad = max((high - low) * 1.5, 0.02)
    considered = (axis >= low - pad) & (axis <= high + pad)
    window &= considered

    if not np.any(window):
        # No fitted line placed a window inside the range -- fall back to the
        # stated range so a signal is never reported as absent for a bookkeeping
        # reason. This is the previous behaviour, unchanged.
        window = considered
        if not np.any(window):
            return 0.0

    oriented = _positive_peak_orientation(np.asarray(spectrum.data, dtype=float))
    centred = oriented - float(np.median(oriented))
    return float(np.max(centred[window]) / baseline_sigma)


def _resolved_line_count(spectrum: NMRSpectrum, multiplet, baseline_sigma: float) -> int:
    """How many lines a deconvolution finds where the detector reported some.

    Returns the detector's own count when the deconvolution finds no more, so
    this can only ever say "there is more here", never "there is less". It is an
    additional reading of the same window, not a replacement for the peak list.
    """
    from moltrace.spectroscopy.peaks.gsd import _positive_peak_orientation

    if baseline_sigma <= 0:
        return len(multiplet.peaks)

    axis = np.asarray(spectrum.ppm_axis, dtype=float)
    low, high = min(multiplet.range_ppm), max(multiplet.range_ppm)

    # PADDED FIRST, and everything below uses this window.
    #
    # A single-line multiplet has a ZERO-WIDTH range — measured: 125.2953 to
    # 125.2953 ppm — so an unpadded window holds no points at all. A guard that
    # measured its apex there saw zero and refused every one-line signal, which
    # is exactly the population this stage exists to re-examine. The padding is
    # also what the fit needs: a Lorentzian's tails carry the information that
    # separates two of them, and a window clipped to the peak throws it away.
    pad = max((high - low) * 1.5, 0.02)
    window = (axis >= low - pad) & (axis <= high + pad)
    if int(np.count_nonzero(window)) < 16:
        return len(multiplet.peaks)

    # Oriented and centred, the way the detector sees it — a spectrum stored
    # negative-going would otherwise measure as no signal at all.
    oriented = _positive_peak_orientation(np.asarray(spectrum.data, dtype=float))
    centred = oriented - float(np.median(oriented))

    # A SIGNAL THAT IS NOT ITSELF QUANTIFIABLE IS NOT CREDIBLY TWO SIGNALS.
    # Measured on a real acquisition: of three signals split further, two stood
    # at 842 and 121 sigma and one at 4.3 — barely above the detection limit.
    # Claiming structure inside that third one is claiming to read noise.
    if float(np.max(centred[window])) < baseline_sigma * _QUANTIFIABLE_SIGMA:
        return len(multiplet.peaks)

    try:
        components = resolve_region(
            axis[window],
            centred[window],
            field_mhz=float(spectrum.field_mhz),
            noise_sigma=baseline_sigma,
        )
    except Exception:  # noqa: BLE001 - a refinement that fails leaves the reading unchanged
        return len(multiplet.peaks)
    return max(len(components), len(multiplet.peaks))


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
    # WHY the fallback happened, not just that it did. "No processed spectrum
    # present" and "a processed spectrum was present and could not be trusted"
    # send a chemist looking in different places, and the caveat below used to
    # assert the first unconditionally. An incomplete `1r` is now refused rather
    # than stretched, which made that assertion reachable and false.
    rejected: str | None = None
    try:
        spectrum = read_processed_spectrum(source)
    except (FIDReaderError, OSError, ValueError) as refused:
        if _has_processed_spectrum(source):
            rejected = str(refused)
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

    # Measured once, above the filter: the noise width sets both which fits are
    # signals at all and what every reported ratio is divided by.
    baseline_sigma = _baseline_sigma(spectrum)

    # A RATIO BELOW ZERO IS NOT A WEAK SIGNAL, IT IS THE ABSENCE OF ONE. The
    # fitted linewidth is not bounded against the acquisition's own resolution,
    # so the fitter can return a "line" wide enough to be modelling baseline roll
    # rather than a resonance -- measured up to 8871.9 Hz, 25.2% of the sweep on a
    # 13C acquisition. Where such a fit sits over a trough its apex, taken within
    # its own extent, falls below the baseline. Four rows in the corpus did this,
    # and they did not merely render: the caveat interpolates the weakest range
    # into prose, so one acquisition told its reader the signals stood "between
    # -2.7 and -0.2 times the baseline noise". That reads as a software fault and
    # takes the credibility of the neighbouring numbers with it.
    #
    # Definitional rather than a threshold: at or below the baseline there is
    # nothing to report. Dropped BEFORE `total_area` so they cannot set the scale
    # every other row is divided by either.
    # WHAT EACH LINE APPEARS TO BE. The engine has always known -- `classify_peaks`
    # separates the compound from the solvent, its residual proton, impurities,
    # 13C satellites and artifacts -- and nothing has ever asked it. On one public
    # acquisition that is 10 impurity lines and 2 satellites a chemist would
    # otherwise pick out by eye, every time they read the spectrum.
    #
    # Classified against the solvent the FILE recorded, not the detected one: the
    # instrument's record is the fact, and the detector's reading is a second
    # opinion. Where they disagree that is said below rather than silently
    # resolved -- a disagreement can mean a mislabelled sample or a mis-referenced
    # axis, and both are things the chemist needs to know.
    detected_solvent = ""
    categories: dict[int, tuple[str, float]] = {}
    try:
        from moltrace.spectroscopy.classify import classify_peaks, detect_solvent

        detected_solvent = str(detect_solvent(spectrum, peaks) or "")
        assigned = classify_peaks(peaks, spectrum.solvent or detected_solvent)
        categories = {id(peak): assigned[i] for i, peak in enumerate(peaks) if i < len(assigned)}
    except Exception:  # noqa: BLE001 - a reading without categories beats no reading
        detected_solvent = ""
        categories = {}

    measured = [(m, _signal_to_noise(spectrum, m, baseline_sigma)) for m in multiplets]
    discarded = [m for m, snr in measured if snr <= 0.0]
    kept = [(m, snr) for m, snr in measured if snr > 0.0]

    total_area = sum(abs(p.area) for m, _ in kept for p in m.peaks) or 1.0

    # WHAT THE DETECTOR COULD NOT SEPARATE, asked again with a different question.
    #
    # This runs on the desktop path only, deliberately: `gsd_peak_pick` is shared
    # by SpectraCheck, qNMR and the verifier, and a change there is a change to
    # every peak list this platform has ever produced. Here it adds a column and
    # takes nothing away.

    summaries = [
        _summarise_multiplet(spectrum, m, baseline_sigma, total_area, snr, categories)
        for m, snr in kept
    ]

    # WHAT THIS ANALYSIS CANNOT SEPARATE, in the units a chemist thinks in.
    #
    # The detector reports one maximum per resolvable feature, so two lines
    # closer than its minimum separation come back as a single signal. That is
    # not a caveat about confidence — it is a hard limit of the method, and a
    # peak table that does not state it invites a coupling to be read off a
    # merged pair.
    #
    # Measured rather than assumed: two strong lines are recovered separately
    # only from about four linewidths apart, so the true limit is coarser than
    # this floor. This reports the floor, which is the part the software knows.
    axis = np.asarray(spectrum.ppm_axis, dtype=float)
    step_ppm = float(np.median(np.abs(np.diff(np.sort(axis))))) if axis.size > 1 else 0.0
    separation_points = _distance_points(axis, nucleus=spectrum.nucleus, level=_DEFAULT_GSD_LEVEL)
    resolution_hz = float(separation_points * step_ppm * spectrum.field_mhz)

    trace = _display_trace(spectrum.ppm_axis, spectrum.data, summaries)

    return {
        "trace": trace,
        "nucleus": spectrum.nucleus,
        # PARSED ON EVERY READER PATH AND THEN DROPPED HERE. A chemical shift is
        # not interpretable without the solvent it was referenced in -- CDCl3 and
        # DMSO-d6 move the same proton by more than a ppm -- and every reader
        # already extracts it into `NMRSpectrum.solvent`. It reached this function
        # and stopped. Empty string when the file does not say, which is honest:
        # the reader never guesses one.
        "solvent": spectrum.solvent,
        #: What the peaks themselves look like they were run in. A SECOND OPINION,
        #: never a correction: the file's own record is the fact.
        "solvent_detected": detected_solvent,
        "field_mhz": float(spectrum.field_mhz),
        # The date the instrument recorded it. A reviewer reading a peak table
        # needs to know which run it came from, and the readers all carry it.
        "acquired_at": (
            spectrum.acquisition_time.isoformat()
            if spectrum.acquisition_time is not None
            else None
        ),
        "points": int(len(spectrum.data)),
        "file_name": _readable_name(source),
        "processing": processing,
        "processed_spectrum_rejected": rejected,
        "resolution_hz": resolution_hz,
        "saturated": saturated,
        "peak_count": len(peaks),
        "multiplets": [m.to_dict() for m in summaries],
        # Stated by the engine, not by the interface, so a caller cannot render
        # the numbers without them. §7.1's readout rule in miniature: the limits
        # travel with the result.
        "limits": [
            "Shifts, multiplicities and couplings are measured from this spectrum alone. "
            "Nothing here has been checked against a proposed structure.",
            # NAMES WHAT WAS ACTUALLY DIVIDED BY. This said "relative to the whole
            # spectrum", which is not the denominator: `total_area` is the sum of the
            # fitted peak areas, measured across the 22 acquisitions at 0.042x to
            # 2.150x the spectrum's own integral. A proportion is only readable if
            # its basis is stated correctly.
            "Areas are shown as a share of the signals listed here, not of the whole "
            "spectrum. They are ratios, not proton counts: assigning protons needs a "
            "structure this analysis was not given.",
            *(
                []
                if not (
                    detected_solvent
                    and spectrum.solvent
                    and detected_solvent.lower() != spectrum.solvent.lower()
                )
                else [
                    f"This acquisition records {spectrum.solvent} as its solvent, but the peaks "
                    f"look more like {detected_solvent}. Signals were sorted using the recorded "
                    f"one. A disagreement here can mean a mislabelled sample or a shift axis "
                    f"referenced to the wrong peak, and both change what the numbers mean."
                ]
            ),
            *(
                []
                if not discarded
                else [
                    f"{len(discarded)} fitted line(s) were discarded before these shares were "
                    "computed: their strongest point sat at or below the baseline, so they "
                    "measure no signal. A very broad fit over a dip in the baseline does this."
                ]
            ),
            "Multiplicity and coupling assignment is a fit. A crowded or overlapping region can "
            "be grouped more than one way.",
            f"{sum(1 for m in summaries if m.quantifiable)} of {len(summaries)} signals stand "
            f"at or above {_QUANTIFIABLE_SIGMA:.0f} times the baseline noise. The rest are "
            "detected but "
            "not quantifiable: they are real enough to see and not strong enough to read numbers "
            "off, and a shift or an integral taken from one of them is not a measurement.",
            f"Signals closer together than about {resolution_hz:.1f} Hz are reported as one. "
            "A wider-than-usual signal in the table may be two lines this analysis could not "
            "separate.",
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
                    (
                        "The processed spectrum in this acquisition could not be used, so one "
                        "was computed here from the raw measurement instead. " + rejected + " "
                        if rejected
                        else "This acquisition held no processed spectrum, so one was computed "
                        "here from the raw measurement. "
                    )
                    + "It uses this application's own phasing and baseline settings. "
                    "Those settings are not the ones your spectrometer used, so shifts and "
                    "integrals can differ from the printout it produced."
                ]
            ),
        ],
    }
