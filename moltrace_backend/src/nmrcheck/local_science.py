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

from moltrace.spectroscopy.classify.solvent_impurity import describe_impurity_match
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

from .chemistry import structure_summary_from_smiles
from .peak_categorization import build_proton_inventory, categorize_peak


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


def _library_reference(raw: str) -> str:
    """The library record's own locator, as a citation rather than a field dump.

    Measured over the shipped library: 97% of records carry a DOI and 3% a
    database id, both written the way the NMReDATA block stores them --
    "Doi=10.18716/nmrshiftdb2/2151", "DB_ID=76532". Rendered raw under a column
    headed "Reference" that reads as noise, which is the complaint the column was
    already supposed to have fixed; the earlier fix moved SMILES into its own
    column and left this one exactly as it was.

    Both forms ARE useful -- a DOI resolves and a record id is looked up. The
    problem was the presentation, so nothing is dropped and nothing is invented.
    """
    text = (raw or "").rstrip(chr(92)).strip()
    if not text:
        return "no reference recorded"
    lowered = text.lower()
    if lowered.startswith("doi="):
        return "doi:" + text[4:].strip()
    if lowered.startswith("db_id="):
        return "NMRShiftDB2 record " + text[6:].strip()
    return text


def _test_finding(
    name: str,
    applicable: bool,
    score: float,
    significance: float,
    details: dict | None = None,
) -> str:
    """What one test found, for a chemist, from the structured fields.

    The engine's `diagnostic` is written for whoever is debugging the engine:
    "Assigned 3/3 predicted 1H resonances (merit 0.44, multiplicity consistency
    0.83); unexplained integral 63% -> significance 0.0 (low); scaled by flat
    prior." Rendered unedited in a column headed "What it found", it asks a
    chemist to read `merit`, a significance on an unstated scale, and an arrow.

    Structured-first with the raw text kept as an escape hatch, which is the
    pattern this platform already uses for machine-written prose.

    `score` IS A SIGNED FIT QUALITY IN -1..+1, NOT A FRACTION OF SIGNALS
    (`scorer.py:320`). The first version of this function read it as a fraction
    because `prediction_bounds` returned 0.667 on the acquisition it was written
    against and the diagnostic beside it said "2/3" -- a coincidence. On the very
    same verdict `assignments` scores **-0.129**, which that reading rendered as
    "0% of the measured signals could be assigned to an atom" while the engine's
    own line said it had assigned 3 of 3. A negative number clamped into a
    percentage is not a rounding error, it is a different claim. So this reports
    DIRECTION and STRENGTH, which is what the field holds.
    """
    if not applicable:
        # "NONE WAS SUPPLIED" INVITES A CHEMIST TO GO AND SUPPLY IT. This module
        # is imported by exactly one caller -- the local service the desktop
        # starts -- and that service exposes six operations, none of which takes
        # a 2-D spectrum or MS peaks. So these two of the verifier's four tests
        # abstain on EVERY check made here, and no action by the reader changes
        # that. Saying the evidence is missing when the ability to accept it is
        # what is missing sends them looking for a control that does not exist.
        needs = {
            "hsqc_2d_ranges": (
                "This needs a 2-D spectrum, which this installation cannot read yet, "
                "so it never runs here."
            ),
            "ms_molecule_match": (
                "This needs mass-spectrometry peaks, which this installation cannot read "
                "yet, so it never runs here."
            ),
        }
        return needs.get(name, "This test had no data to work with, so it did not run.")

    value = max(-1.0, min(1.0, float(score)))
    if value >= 0.5:
        direction = "agrees closely with that structure"
    elif value >= 0.15:
        direction = "agrees with that structure"
    elif value > -0.15:
        direction = "neither agrees nor disagrees"
    elif value > -0.5:
        direction = "disagrees with that structure"
    else:
        direction = "disagrees strongly with that structure"

    # Significance is the weight this test carried into the verdict. A test can
    # point one way and still move nothing, and saying so is the difference
    # between a reader trusting the arrow and trusting the verdict.
    if significance <= 0.0:
        # NAME THE CAUSE. "Too weak to move the verdict" is true and tells a
        # chemist nothing they can act on, and on this corpus the assignment test
        # is zeroed on 9 of 11 acquisitions with a known structure -- so the
        # verdict routinely rests on ONE of the four tests while the screen says
        # two had data. The cause is a single number the engine already computed:
        # `significance = SIG_MAX * (1 - impurity_pct / 25)`, so any spectrum
        # whose unexplained integral reaches 25% switches this test off.
        #
        # What makes that worth saying out loud is WHAT is unexplained. The
        # verifier has no notion of a solvent; every peak this structure does not
        # account for is impurity to it, and the CDCl3 triplet is three of them.
        # This application labels those peaks "solvent" in the table above, so a
        # reader who is told the number can see for themselves what made it.
        unexplained = (details or {}).get("impurity_pct")
        if name == "assignments" and isinstance(unexplained, (int, float)):
            # NAMES THE NUMBER, NOT A CULPRIT. The first version of this sentence
            # said "solvent peaks count toward that figure", which is true and
            # points at the wrong thing: measured over the zeroed cases in this
            # corpus, solvent-labelled area accounts for the WHOLE unexplained
            # integral in none of them (58% unexplained against 38% solvent, 77%
            # against 58%), and one 1H acquisition is zeroed at 30% unexplained
            # with NO non-compound signal at all. Naming solvent there sends a
            # chemist to look at a peak that is not the cause. The honest sentence
            # gives the figure and the threshold and lets the table above -- which
            # labels every signal -- show where it came from.
            return (
                f"{unexplained:.0f}% of the measured signal is not accounted for by this "
                "structure, and at 25% this test stops counting altogether. Anything the "
                "structure does not explain adds to that: solvent, an impurity, or a second "
                f"compound. What it did measure {direction}, on no weight."
            )
        return f"What this measures {direction}, but on evidence too weak to move the verdict."
    weight = "strong" if significance >= 3.0 else "moderate" if significance >= 1.0 else "weak"
    return f"What this measures {direction} ({weight} evidence)."


def _verdict_summary(verdict: str, tests: list[dict], nucleus: str) -> str:
    """The verdict in a sentence, replacing the engine's diagnostic line.

    Was "INCONCLUSIVE: posterior confidence 0.66 from prior 0.50 using 2/4
    applicable test(s) on the 1H spectrum." -- `posterior`, `prior`, and a count
    of "applicable test(s)". The confidence and its starting point are already
    rendered directly above this line, so the only thing it added was how many
    tests had data, which is worth saying in words.
    """
    ran = sum(1 for t in tests if t.get("applicable"))
    total = len(tests)
    word = {
        "CONSISTENT": "This spectrum is consistent with that structure",
        "INCONCLUSIVE": "This spectrum neither supports nor rules out that structure",
        "INCONSISTENT": "This spectrum is not consistent with that structure",
    }.get(str(verdict).upper(), f"Result: {str(verdict).replace('_', ' ').lower()}")
    # SAME CORRECTION AS THE PER-TEST LINE. "Had the data to run" blames absent
    # evidence, and on this installation two of the four can never run at all --
    # it reads neither 2-D spectra nor MS peaks. A chemist told the data was
    # missing goes looking for a way to add it.
    if ran == 0:
        return f"{word}. None of the {total} checks could run here."
    tail = (
        f"{ran} of the {total} checks could run on this evidence"
        if ran < total
        else f"all {total} checks ran"
    )
    return f"{word}, on its {nucleus} signals. {tail[0].upper()}{tail[1:]}."


def _predictor_note(warnings: list[str], knowledge: dict) -> str | None:
    """How the shifts were predicted, in terms of prediction QUALITY.

    The engine's own warning is a Python packaging fact -- "NMRNet unavailable
    (PyTorch is not installed (No module named 'torch')); using HOSE-code
    fallback." -- and it was rendered verbatim under a heading that promises to
    say something about prediction quality. It says nothing of the kind: it names
    a module the reader cannot install, a model they have never heard of, and an
    algorithm, and on a full-coverage prediction it is the ENTIRE body of the
    alert because the coverage line is only emitted when some atoms fall back to
    the element prior.

    It also fires on EVERY check in a packaged build -- the frozen service does
    not carry PyTorch and never will -- so as written it is an amber block that
    is always on, which is the one thing this interface says caveats must not be.

    So: say what was actually used and how much evidence stands behind it. That
    is a fact about prediction quality, it varies with the build, and it is
    checkable by the reader against the knowledge-base line beside it.
    """
    if not any("NMRNet unavailable" in w for w in warnings):
        return None
    count = int(knowledge.get("reference_count") or 0)
    if knowledge.get("source") == "nmrshiftdb2" and count:
        return (
            "Shifts here were predicted by matching each atom's local environment against "
            f"{count:,} measured reference shifts, rather than by this platform's neural "
            "predictor, which is not part of an offline build. Environments with close "
            "matches predict well; unusual ones fall back to a broad element average."
        )
    return (
        "Shifts here were predicted from a small built-in reference table rather than this "
        "platform's neural predictor, which is not part of an offline build. Treat the "
        "predicted shifts as indicative only."
    )


def _rejected_processed_reason(error: Exception) -> str:
    """Why the STORED spectrum was passed over, as one sentence a chemist can read.

    Not `_readable_refusal`. That one answers "why could this acquisition not be
    opened at all", and its fallback sentence says the acquisition holds neither a
    processed spectrum nor a readable FID. Reached from here that is FALSE and
    self-contradicting: this branch runs only when the FID *did* read, and the
    sentence it lands in already says a spectrum was computed from it. Shipped
    that way in the commit that fixed the path leak -- the sanitiser was correct
    and the caller was wrong, which is the half-applied-guard shape again.

    ENGINE PROSE IS NEVER PASSED THROUGH HERE, on purpose. The reader builds these
    messages for a developer: they embed the pdata directory, the array shape and
    the parsing library, and none of that is actionable to a chemist. Sanitising
    such a string is also weaker than it looks -- the path guard replaces the
    acquisition's own path, but the reader names a SUBpath (`<source>/pdata/1`)
    that never equals it, so what actually caught the leak was the developer-word
    filter, and `nmrglue` is not one of its words. Classifying on the reader's
    stable phrasing and writing our own sentence cannot leak by construction.
    """
    text = str(error).lower()
    if "2d processed data" in text or "does not hold a 1d" in text:
        return "The spectrum stored with it is two-dimensional, which this cannot use."
    if "too few points" in text or "truncated" in text or "incomplete" in text:
        return "The spectrum stored with it is incomplete."
    return "The spectrum stored with it could not be read."


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


#: How many lines each published contaminant pattern should show. `m` is absent
#: on purpose: an unresolved multiplet has no line count to contradict, so a
#: signal matched to one is never called into question on this evidence.
_PATTERN_LINES: dict[str, int] = {"s": 1, "d": 2, "t": 3, "q": 4, "quint": 5, "sept": 7}



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

#: How often the true structure scored highest, measured on this repository's own
#: corpus: every acquisition whose structure the NMReDATA source states, against
#: four decoys drawn from that same corpus. Reported to the reader rather than
#: kept as a footnote, because a comparison whose accuracy is unstated is a
#: comparison a chemist cannot weigh.
#:
#: Re-measure with scripts against `eval/curated_shifts._DEFAULT_SOURCE` if the
#: knowledge base or the predictor changes. Do not adjust these numbers to match
#: a hoped-for result.
_RANKING_ACCURACY: dict[str, object] = {
    "13C": {"first": 9, "of": 12},
    "1H": {"first": 3, "of": 8},
    "decoys_per_case": 4,
    "note": (
        "Measured on 20 acquisitions from this build's own reference corpus, each checked "
        "against four other real molecules from it."
    ),
}


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

    # WHICH TABLE ANSWERED. A prediction from 495,215 reference atoms and one from
    # 146 are different products, and the reader must be able to tell which they
    # got -- the engine's own error path exists because silently substituting a
    # worse predictor for a configured one is the failure that matters here.
    from moltrace.spectroscopy.predict.nmrnet_wrapper import knowledge_base_status

    status = knowledge_base_status()
    knowledge = {
        "source": status.get("source") or ("seed" if status.get("loaded") else "unknown"),
        "reference_count": int(status.get("reference_count") or 0),
    }

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
    predictor = _predictor_note(warnings, knowledge)

    return {
        "smiles": candidate,
        "verdict": str(result.verdict),
        "confidence": float(result.posterior_confidence),
        "prior": float(result.prior_confidence),
        "summary": _verdict_summary(
            str(result.verdict),
            [{"applicable": bool(t.applicable)} for t in result.test_results],
            str(spectrum.nucleus),
        ),
        # Same escape-hatch rule as each test's own line.
        "summary_diagnostic": str(result.diagnostic),
        "tests": [
            {
                "name": t.name,
                "label": _TEST_LABELS.get(t.name, t.name.replace("_", " ")),
                "applicable": bool(t.applicable),
                "score": float(t.score),
                "significance": float(t.significance),
                "quality": float(t.quality),
                # What the reader sees, built from the fields above.
                "finding": _test_finding(
                    t.name,
                    bool(t.applicable),
                    float(t.score),
                    float(t.significance),
                    dict(t.details or {}),
                ),
                # The engine's own words, kept as the escape hatch behind a
                # disclosure rather than deleted -- whoever wants them can have
                # them, and nobody has to read `merit` to use the column.
                "diagnostic": str(t.diagnostic),
            }
            for t in result.test_results
        ],
        # WHETHER THESE NUMBERS CAN RANK ANYTHING DEPENDS ON THE TABLE, so it is
        # read from the table rather than asserted. Measured on the ethylene
        # glycol acquisition in this repository against four structures:
        #
        #                     seed (146 atoms)   nmrshiftdb2 (495,215)
        #   ethylene glycol      0.556               0.939  consistent
        #   ethanol              0.623  <- won       0.242  inconclusive
        #   aspirin              0.542               0.166  inconsistent
        #
        # On the seed the WRONG molecule outranked the right one and every verdict
        # was "inconclusive". With the real table the right one wins by 0.697 and
        # the verdicts become words that mean something. Same verifier, same
        # spectrum: the predictor was starved, not the method.
        #
        # So a build answering from the seed says its number cannot rank, and one
        # answering from nmrshiftdb2 says it can -- and the reader is told which,
        # because those are different products.
        # COMPARABLE, WITH A STATED HIT RATE -- not a ranking. Measured over all 20
        # acquisitions in this repository whose structure the corpus states, each
        # against four decoys drawn from the same corpus (so the decoys are real
        # molecules, not absurdities):
        #
        #     13C   9/12 (75%)      1H   3/8 (38%)      overall 12/20
        #
        # 75% is genuinely useful and is NOT an ordering a reader should trust:
        # one carbon spectrum in four puts the wrong structure on top, and a
        # sorted list claims the top is the answer. So the desktop lets a chemist
        # put candidates side by side and tells them how often this has been
        # right, rather than presenting a winner.
        #
        # On the seed table the same measurement is not worth running: it ranked
        # ethanol above ethylene glycol on glycol's own spectrum.
        "comparable_between_candidates": knowledge["source"] == "nmrshiftdb2",
        "ranking_accuracy": _RANKING_ACCURACY if knowledge["source"] == "nmrshiftdb2" else None,
        "knowledge_base": knowledge,
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



#: What a DP4 number IS, in the words the web module already uses. Emitted from
#: here rather than written in the interface so the two surfaces cannot drift into
#: describing the same figure differently.
_DP4_BASIS = (
    "A relative ranking across the candidates supplied, not a calibrated probability that "
    "the structure is correct. The DP4 error model was fitted to DFT-computed shifts; the "
    "shifts ranked here come from an empirical predictor with a wider measured error."
)


def structure_inventory(path: str | Path, smiles: str) -> dict:
    """What the measured areas become once a structure is known.

    THIS IS THE ONE PLACE A SUPPLIED STRUCTURE FLOWS BACK INTO THE MEASUREMENT.
    Everything else here runs one way: the spectrum is measured without a
    structure, and a structure is then scored against that fixed measurement.
    Areas are reported as a SHARE of the listed signals for exactly that reason --
    turning a share into a proton count needs a denominator only the structure
    supplies, and the readout says so in as many words.

    Given one, the share becomes protons. The scale is the structure's own
    non-labile hydrogen count divided by the share the compound's signals hold.

    NON-LABILE, not total. OH, NH and SH protons exchange with the solvent and
    with each other; in a protic solvent they broaden, shift, or vanish, and
    normalising a spectrum that never showed them against a count that includes
    them shrinks every other signal by the missing fraction. A structure with
    four of its twelve hydrogens labile would put every count 33% low.

    WHAT THIS CANNOT TELL YOU, and the reason the total is reported as a
    constraint rather than a result: the total matches the expectation BY
    CONSTRUCTION. The scale is chosen to make it match. A reader who sees "10.00
    of 10 H" and takes it as agreement has read the arithmetic backwards. The
    evidence is entirely in the PER-SIGNAL residuals -- a real structure puts
    each signal near a whole number, and a signal sitting at 1.4 H is telling you
    that two environments merged, that one split into several, or that the
    structure is wrong. The verifier remains the arbiter of the last of those;
    this is a readout, not a fifth test, and it never moves the verdict.
    """
    source = Path(path)
    candidate = (smiles or "").strip()
    if not candidate:
        raise SpectrumUnreadable("no structure was given to count protons against")

    summary = open_spectrum(str(source))
    nucleus = str(summary.get("nucleus") or "unknown")

    # A proton inventory over carbon is not a thing. Said plainly rather than
    # returned as an empty table the reader has to interpret.
    if nucleus != "1H":
        return {
            "applicable": False,
            "nucleus": nucleus,
            "reason": (
                f"Counting protons needs a {'1H'} spectrum, and this one is {nucleus}. "
                f"The structure check above still applies."
            ),
            "human_review_required": True,
        }

    try:
        structure = structure_summary_from_smiles(candidate)
    except Exception as bad:  # noqa: BLE001 - the chemist's input, not a fault
        raise SpectrumUnreadable(
            f"that structure could not be read as a molecule ({bad})"
        ) from None

    multiplets = list(summary.get("multiplets") or [])
    compound = [m for m in multiplets if m.get("category") == "compound"]
    share = sum(float(m.get("relative_area") or 0.0) for m in compound)

    non_labile = int(structure.non_labile_hydrogens)
    if non_labile <= 0:
        return {
            "applicable": False,
            "nucleus": nucleus,
            "reason": (
                f"{structure.formula} has no non-exchanging hydrogens to count against, so a "
                f"proton count cannot be scaled from this spectrum."
            ),
            "human_review_required": True,
        }
    if share <= 0.0:
        return {
            "applicable": False,
            "nucleus": nucleus,
            "reason": (
                "No signal here is attributed to the compound, so there is no area to turn "
                "into proton counts."
            ),
            "human_review_required": True,
        }

    scale = non_labile / share

    rows = []
    for m in sorted(compound, key=lambda x: -float(x.get("center_ppm") or 0.0)):
        protons = float(m.get("relative_area") or 0.0) * scale
        nearest = round(protons)
        rows.append(
            {
                "name": m.get("name"),
                "center_ppm": m.get("center_ppm"),
                "relative_area": m.get("relative_area"),
                "protons": round(protons, 2),
                "nearest_whole": int(nearest),
                # The residual IS the evidence, so it travels as a number rather
                # than as a rendered string a reader has to re-derive.
                "off_by": round(abs(protons - nearest), 2),
                # Below the quantitation floor an area is not a measurement, so a
                # proton count derived from one is not either.
                "quantifiable": bool(m.get("quantifiable")),
            }
        )

    # The class-level table the platform already computes, so the desktop shows
    # the same expected-vs-observed a chemist sees on the web rather than a
    # second, subtly different one.
    #
    # TWO CATEGORISERS MEET HERE AND ONLY ONE OF THEM ANSWERS THIS QUESTION.
    # What the peak table shows comes from `classify_peaks`, whose vocabulary is
    # compound / solvent / impurity -- it answers "is this the sample". The
    # inventory buckets by CHEMICAL CLASS -- aromatic, olefinic, oxygenated,
    # labile -- which is `categorize_peak`. Handing the first one's words to the
    # second matches none of its category sets, so every observed class comes
    # back 0.0 while the total is right: a table that looks computed and says
    # nothing. Measured before this line existed.
    #
    # The two are not merged. `classify_peaks` stays authoritative for whether a
    # signal is the compound at all, because that is the call the peak table
    # renders and a disagreement between the two would put a signal in the
    # inventory that the table calls solvent. `categorize_peak` is asked only
    # what KIND of proton an already-accepted compound signal is.
    peaks = []
    for m in multiplets:
        if m.get("category") != "compound":
            # Carried through with its own label so the inventory can exclude it
            # from the total exactly as the web does.
            peaks.append({"category": m.get("category"), "shift_ppm": m.get("center_ppm")})
            continue
        try:
            fine = categorize_peak(
                nucleus="1H",
                shift_ppm=float(m.get("center_ppm") or 0.0),
                multiplicity=str(m.get("multiplicity") or "") or None,
                solvent=summary.get("solvent") or None,
                structure=structure,
                integration_h=float(m.get("relative_area") or 0.0) * scale,
            )
            chemical_class = str(fine.get("category") or "")
        except Exception:  # noqa: BLE001 - an uncategorised signal still counts
            chemical_class = ""
        peaks.append(
            {
                "category": chemical_class,
                "shift_ppm": m.get("center_ppm"),
                "integration_h": float(m.get("relative_area") or 0.0) * scale,
            }
        )
    inventory = build_proton_inventory(
        peaks=peaks,
        structure=structure,
        nucleus="1H",
        solvent=summary.get("solvent") or None,
    )

    # WHAT WAS LEFT OUT OF THE DENOMINATOR, because the counts depend on it
    # entirely and nothing on screen said so.
    #
    # The scale is the structure's hydrogen count divided by the share held by
    # signals classified `compound`. Every signal called solvent or impurity is
    # therefore excluded, and if one of them is really the compound, EVERY count
    # is wrong by the ratio of the shares -- silently, because the arithmetic
    # still produces whole-looking numbers.
    #
    # Measured on this corpus: one acquisition of 1,2-epoxybutane has 48% of its
    # listed area classified away (a 9-line multiplet at 1.583 called an impurity,
    # and a 4-line one at 2.486 called residual solvent), leaving two compound
    # signals to carry all 8 hydrogens. The counts came out 5.29 and 2.71.
    #
    # THIS DOES NOT RECLASSIFY ANYTHING. `classify_peaks` is deterministic and it
    # decides; a heuristic here that overrode it would be exactly the kind of
    # guess this codebase keeps out of the arbiter's way. What is added is the
    # disclosure: how much was excluded, and which excluded signals carry
    # resolved coupling. Water, chloroform, acetone and TMS are SINGLETS -- a
    # contaminant-labelled multiplet with several resolved lines is at least worth
    # a chemist's eye. Across this corpus contaminant-labelled multiplets have a
    # median of 1 line, so this is a real separation and not a threshold invented
    # to fit; the exceptions are real too (DMSO-d5 is a quintet, ethyl acetate
    # gives a triplet and a quartet), which is why these are flagged and not
    # moved.
    excluded_share = sum(
        float(m.get("relative_area") or 0.0)
        for m in multiplets
        if m.get("category") != "compound"
    )
    # WHICH contaminant it matched, and does this signal look like that thing?
    #
    # Counting resolved lines alone was the first version and it was too blunt:
    # it flagged a 4-line quartet at 2.486 ppm that matches triethylamine's CH2,
    # which IS a quartet -- a correct classification called suspicious. The table
    # now carries each contaminant's published pattern, so the question becomes
    # specific: water is a singlet, and a nine-line multiplet sitting on water's
    # shift is not water however well its strongest line matches.
    #
    # `+ 2` rather than `>`, because the line fitter over-picks and a singlet
    # occasionally comes back as two. The margin has to exceed that noise before
    # a correct classification gets called into question.
    contested = []
    for m in sorted(multiplets, key=lambda x: -float(x.get("relative_area") or 0.0)):
        if m.get("category") in ("compound", ""):
            continue
        lines = int(m.get("line_count") or 0)
        matched = describe_impurity_match(
            float(m.get("center_ppm") or 0.0), summary.get("solvent") or None, "1H"
        )
        if matched is None:
            continue
        expected_lines = _PATTERN_LINES.get(str(matched.get("multiplicity") or "s"))
        if expected_lines is None or lines < expected_lines + 2:
            continue
        contested.append(
            {
                "name": m.get("name"),
                "center_ppm": m.get("center_ppm"),
                "category": m.get("category"),
                "relative_area": m.get("relative_area"),
                "line_count": lines,
                "multiplicity": m.get("multiplicity"),
                "matched_label": matched.get("label"),
                "matched_pattern": matched.get("multiplicity"),
                "expected_lines": expected_lines,
            }
        )

    worst = max((r["off_by"] for r in rows if r["quantifiable"]), default=0.0)
    return {
        "applicable": True,
        "nucleus": nucleus,
        "structure": {
            "formula": structure.formula,
            "total_hydrogens": int(structure.total_hydrogens),
            "non_labile_hydrogens": non_labile,
            "labile_hydrogens": int(structure.labile_hydrogens),
        },
        "scale": {
            "hydrogens_per_share": round(scale, 4),
            "compound_share": round(share, 4),
            "basis": "non_labile_hydrogens",
            # Stated as data so the interface cannot present the total as
            # agreement even by accident.
            "total_matches_by_construction": True,
        },
        "signals": rows,
        "excluded": {
            "share": round(float(excluded_share), 4),
            "counted_share": round(float(share), 4),
            "coupled_signals": contested,
        },
        "largest_residual": round(float(worst), 2),
        "class_inventory": inventory,
        "human_review_required": True,
    }


def rank_candidates(path: str | Path, smiles_list: Sequence[str]) -> dict:
    """Order candidate structures by how well their predicted shifts fit this spectrum.

    DP4 IS ONLY MEANINGFUL ACROSS A SET. Its probabilities are normalised over the
    candidates supplied and sum to one, so a DP4 figure for a single structure is
    1.0 and says nothing. That is why this takes a list and why the interface
    offers it only from the second candidate on.

    It is a SECOND, INDEPENDENT reading beside `verify_candidate`: the verifier
    combines four tests through a Bayesian update, DP4 asks one narrower question
    -- how well do these predicted shifts agree -- under Smith & Goodman's error
    model. Two methods agreeing is worth more than either alone; two disagreeing
    is worth knowing.

    The number is NOT a calibrated probability and is labelled as such at every
    layer, because the error model was fitted to DFT shifts and these come from an
    empirical predictor with a wider measured error.
    """
    source = Path(path)
    if not source.exists():
        raise SpectrumUnreadable("that file is no longer where it was")
    candidates = [str(c or "").strip() for c in smiles_list]
    candidates = [c for c in candidates if c]
    if len(candidates) < 2:
        raise SpectrumUnreadable(
            "ranking compares candidates against each other, so it needs at least two"
        )

    from moltrace.spectroscopy.predict.nmrnet_wrapper import knowledge_base_status, predict_shifts

    from .dp4_scoring import dp4_probabilities

    summary = open_spectrum(source)
    nucleus = str(summary["nucleus"])
    if nucleus not in ("1H", "13C"):
        raise SpectrumUnreadable(
            "ranking is defined for 1H and 13C; this acquisition is "
            + (nucleus or "an unknown nucleus")
        )

    # THE COMPOUND'S OWN LINES, not everything detected. Solvent, its residual
    # proton, satellites and impurities are not part of the structure being
    # proposed, and scoring a candidate against them would penalise a correct
    # structure for the sample being real.
    observed = [
        float(m["center_ppm"])
        for m in summary["multiplets"]
        if m["quantifiable"] and m["category"] in ("compound", "")
    ]
    if not observed:
        raise SpectrumUnreadable(
            "no signal in this spectrum is both strong enough to measure and attributable "
            "to the compound, so there is nothing to rank a structure against"
        )

    predicted: list[list[float]] = []
    for candidate in candidates:
        try:
            prediction = predict_shifts(candidate, n_conformers=8)
        except Exception as bad:  # noqa: BLE001 - the chemist's input, not a fault
            raise SpectrumUnreadable(
                f"{candidate!r} could not be read as a molecule ({bad})"
            ) from None
        predicted.append([s.predicted_ppm for s in prediction.shifts if s.nucleus == nucleus])

    empty = [c for c, p in zip(candidates, predicted, strict=False) if not p]
    if empty:
        raise SpectrumUnreadable(
            f"no {nucleus} shifts could be predicted for {empty[0]!r}, so it cannot be ranked "
            f"against a {nucleus} spectrum"
        )

    scores = dp4_probabilities(
        observed_shifts_ppm=observed,
        candidate_predicted_shifts_ppm=predicted,
        nucleus=nucleus,  # type: ignore[arg-type]
    )

    # NOTHING MATCHED IS NOT A RANKING. When no candidate pairs with any observed
    # peak, DP4 gives every one of them a share of zero and the set sums to zero
    # instead of one. That is correct arithmetic on no evidence -- and rendered to
    # a person it is three rows of "0.0%" that look exactly like a ranking in
    # which every candidate did badly, rather than one that could not be made.
    # Measured across this corpus it happens on 2 of the first 6 acquisitions.
    if all(int(score.matched_peaks) == 0 for score in scores):
        raise SpectrumUnreadable(
            f"none of these structures matched any of the {len(observed)} measured "
            f"{nucleus} signals, so there is nothing to rank them on. Check the structures, "
            f"or that this spectrum is the compound you think it is."
        )

    # DOES THE ORDERING SURVIVE HOW WELL THE SHIFTS ARE KNOWN?
    #
    # Resample the observed shifts within the acquisition's own digital resolution
    # -- a conservative floor, since line fitting and referencing add more -- and
    # watch the MARGIN between the top two shares. If it ever reaches zero, the
    # ordering is not robust to the measurement and must not be read as one.
    #
    # BOTH THE MARGIN AND THE WINNER'S IDENTITY, because each one alone is blind
    # to a case the other catches, and this check has now been wrong in both
    # directions.
    #
    # Asking only "does the leader change" misses a perfect tie: with two
    # identical candidates DP4 returns exactly 50/50, `argmax` breaks the tie
    # deterministically at index 0, the leader never moves, and a dead heat is
    # reported STABLE. Asking only "does the margin reach zero" misses the
    # opposite: sorting the shares throws away WHICH candidate holds each place,
    # so two candidates trading first and second leave the margin untouched while
    # the answer on screen changes. Measured, three of nineteen corpus cases do
    # exactly that.
    #
    # Validated at both ends: a perfect tie gives a margin of 0.0000 throughout,
    # a clear winner 0.3311 at its narrowest.
    import numpy as _np

    _resamples = 50
    _sigma_ppm = float(summary.get("resolution_hz") or 0.0) / max(float(summary["field_mhz"]), 1e-9)
    _margins: list[float] = []
    _leaders: list[int] = []
    if _sigma_ppm > 0:
        _rng = _np.random.default_rng(20260830)
        for _ in range(_resamples):
            _jittered = [v + float(_rng.normal(0.0, _sigma_ppm)) for v in observed]
            _shares_in_order = [
                x.probability
                for x in dp4_probabilities(
                    observed_shifts_ppm=_jittered,
                    candidate_predicted_shifts_ppm=predicted,
                    nucleus=nucleus,  # type: ignore[arg-type]
                )
            ]
            # BOTH FAILURES, because each fix so far was blind to the other.
            # Reading argmax alone missed a perfect tie: ties break deterministically
            # at index 0, so the leader never moved. Reading the sorted margin alone
            # missed the opposite case: sorting discards WHICH candidate holds each
            # position, so two candidates swapping places leaves the margin
            # untouched and the ordering is reported as stable while the winner
            # changes. Measured: three of nineteen corpus cases change leader while
            # the margin stays positive.
            _leaders.append(int(_np.argmax(_shares_in_order)))
            _ordered = sorted(_shares_in_order, reverse=True)
            _margins.append(float(_ordered[0] - _ordered[1]) if len(_ordered) > 1 else 1.0)

    _leader_changed = bool(_leaders) and len(set(_leaders)) > 1

    # A MARGIN OF 1.0 IS NOT A ROBUST ORDERING, it is the absence of a contest.
    # DP4 gives a candidate that matched no observed peak a share of exactly 0,
    # so when only one candidate matches anything the top-two margin is 1.0 at
    # every resample -- perfectly "stable", and the screen turned that into
    # "the leader stayed ahead by at least 100.0 points". Measured on this
    # corpus: a winner matching ONE line of two, against two candidates matching
    # none, reported as a maximal margin.
    #
    # Resampling cannot rescue this. It perturbs the observed shifts, and a
    # candidate with no matching line has nothing to perturb, so the gap is
    # structural rather than evidential. Counted here, and reported separately
    # from a genuine near-tie because they call for opposite readings: a tie
    # means the evidence does not choose, this means there was no comparison.
    _scoreable = sum(1 for score in scores if int(score.matched_peaks) > 0)
    _no_contest = _scoreable < 2

    separation = {
        # WHY it could not be checked, so the renderer can say so. When the file
        # states no frequency, `resolution_hz` and the ppm uncertainty derived
        # from it are both 0, no resample runs, and `checked` is false -- and both
        # render branches tested `checked`, so the page fell silent about the one
        # thing this section exists to say. Silence after a ranking reads as "it
        # held", which is the opposite of what is known.
        "checked": bool(_margins),
        "unchecked_reason": (
            None
            if _margins
            else "this acquisition does not state its frequency, so the shift uncertainty "
            "that the check resamples within cannot be derived from it"
        ),
        "separated": (
            bool(_margins) and min(_margins) > 0.0 and not _leader_changed and not _no_contest
        ),
        "leader_changed": _leader_changed,
        "comparable_candidates": _scoreable,
        "no_contest": _no_contest,
        "narrowest_margin": min(_margins) if _margins else None,
        "resamples": _resamples if _margins else 0,
        "shift_uncertainty_ppm": _sigma_ppm if _margins else None,
    }

    status = knowledge_base_status()
    rows = []
    for candidate, score in zip(candidates, scores, strict=False):
        matched = int(score.matched_peaks)
        rows.append(
            {
                "smiles": candidate,
                "probability": float(score.probability),
                # Never true today. The flag exists so the claim tracks a future
                # calibration instead of a comment promising one.
                "probability_is_calibrated": False,
                "probability_basis": _DP4_BASIS,
                "matched_peaks": matched,
                "observed_peaks": len(observed),
                "mean_abs_error_ppm": float(score.mean_abs_error_ppm),
                "rms_error_ppm": float(score.rms_error_ppm),
                # Errors are computed over MATCHED peaks only, so a candidate that
                # matched one line of eight can post a flattering error. The
                # coverage travels with the error for exactly that reason.
                "error_basis": "matched_peaks_only",
                "coverage": matched / len(observed) if observed else 0.0,
                # Structural, not tuned: fewer than half the compound's own lines
                # matched means the error figures describe a minority of the
                # evidence.
                "low_coverage": matched * 2 < len(observed),
            }
        )
    rows.sort(key=lambda r: -r["probability"])

    return {
        "nucleus": nucleus,
        "observed_peaks": len(observed),
        "rows": rows,
        "separation": separation,
        "knowledge_base": {
            "source": status.get("source") or "unknown",
            "reference_count": int(status.get("reference_count") or 0),
        },
        "human_review_required": True,
    }



#: Measured retrieval on the shipped library, reported to the reader, because a
#: lookup whose hit rate is unstated is a lookup a chemist cannot weigh.
#:
#: FOUR harnesses stand behind this number and the first three were each measuring
#: something other than the task. In order:
#:
#:   30%  counted every record, including a 1H-only record and a 13C-only record of
#:        the same compound -- they occupy different halves of the vector and can
#:        never retrieve each other, so those pairs were unretrievable by
#:        construction.
#:   16%  ran over a 99-record subset in which most compounds appeared ONCE, and
#:        leave-one-out cannot retrieve a compound that is no longer in the pool.
#:   48%/63%  fixed both of those and measured 400 records cleanly -- but
#:        record-against-record, a curated shift list querying the library. That is
#:        not what this function does.
#:   20%/27%  what this function actually does: query with the detected multiplet
#:        centres of a real acquisition. See the constant below.
#:
#: The first two were wrong in the reader's favour. The third was RIGHT about its
#: own task and wrong about this one, which is the harder mistake to see -- a clean
#: measurement of the wrong operating point still reads as evidence. What separates
#: them is not rigour, it is whether the query the harness sends is the query the
#: app sends.
_SIMILARITY_ACCURACY: dict[str, object] = {
    # MEASURED AT THE OPERATING POINT THIS FUNCTION ACTUALLY RUNS AT, which is not
    # the one the first figure described.
    #
    # The first number here was 192/400 and 253/400 -- 48% and 63% -- from a
    # record-vs-record leave-one-out, where a library record's own curated shift
    # list queries the library. This function queries with something else
    # entirely: the detected multiplet centres of a real acquisition, filtered to
    # quantifiable and attributable to the compound. That query is sparser and
    # noisier than a curated record -- median 4 peaks against 5 -- and one
    # acquisition's 31 detected multiplets collapse to 7 query peaks.
    #
    # Re-measured the way the app runs, over every acquisition whose structure the
    # corpus states AND whose compound is present in the searched pool:
    #
    #     same compound first   3/15 (20%)      inside the top five   4/15 (27%)
    #
    # So the honest figure is less than half what was on screen. n=15 is small and
    # is reported as the count rather than dressed as a percentage alone.
    "first": 3,
    "top5": 4,
    "of": 15,
    "note": (
        "Measured the way this lookup is actually used: a real acquisition's measured signals "
        "queried against the shipped library, counting only cases where the compound is in it."
    ),
}

_LIBRARY: dict | None = None
_LIBRARY_VECTORS: dict = {}


def _spectrum_library() -> dict | None:
    """The reference spectra shipped beside the service, or None if absent.

    Ships as SHIFT LISTS rather than encoded vectors, and is encoded at load. It
    is 1.5 MB that way against 45 MB of float32, and -- the reason that matters --
    an index cannot detect that the encoder changed underneath it, while source
    shifts re-encode correctly whatever the encoder does next.
    """
    global _LIBRARY
    if _LIBRARY is None:
        import gzip
        import json

        from .local_service_main import _bundled_file

        path = _bundled_file("spectrum_library.json.gz")
        if not path:
            _LIBRARY = {"records": []}
        else:
            try:
                with gzip.open(path, "rt", encoding="utf-8") as handle:
                    _LIBRARY = json.load(handle)
            except (OSError, ValueError):
                _LIBRARY = {"records": []}
    return _LIBRARY


def find_similar_spectra(path: str | Path, limit: int = 5) -> dict:
    """Known spectra that look like this one. A LOOKUP, never an identification.

    Measured the way this function is actually called -- querying with a real
    acquisition's detected multiplet centres, over cases where the compound is in
    the library at all: it comes back first in 3 of 15 and inside the top five in
    4 of 15. A lead worth following and never an answer, so the rate travels with
    the result and the interface says which it is.

    The 48%/63% this docstring used to quote was a record-against-record
    leave-one-out -- a curated shift list querying the library, which is not what
    this does. See `_SIMILARITY_ACCURACY` for the four harnesses behind that
    number and why only the last one describes this call.

    Searched within the query's own nucleus. The encoding is 128 bins of 1H beside
    128 of 13C, so a 13C query and a 1H reference of the SAME compound sit in
    different halves and score near zero against each other -- comparing across
    them measures nothing.
    """
    import numpy as np

    from moltrace.spectroscopy.similarity import encode_spectrum, exact_knn

    summary = open_spectrum(path)
    nucleus = str(summary["nucleus"])
    if nucleus not in ("1H", "13C"):
        raise SpectrumUnreadable(
            "the reference library holds 1H and 13C spectra; this acquisition is "
            + (nucleus or "an unknown nucleus")
        )

    observed = [
        float(m["center_ppm"])
        for m in summary["multiplets"]
        if m["quantifiable"] and m["category"] in ("compound", "")
    ]
    if not observed:
        raise SpectrumUnreadable(
            "no signal here is both strong enough to measure and attributable to the "
            "compound, so there is nothing to match against"
        )

    library = _spectrum_library() or {"records": []}
    records = library.get("records") or []
    wants_13c = nucleus == "13C"
    # Only references carrying the query's nucleus AND not the other one: a record
    # holding both would sit in a different part of the vector space again.
    pool = [
        r for r in records
        if bool(r.get("c")) is wants_13c and bool(r.get("h")) is not wants_13c
    ]
    if not pool:
        raise SpectrumUnreadable(
            f"this build carries no {nucleus} reference spectra to compare against"
        )

    key = nucleus
    if key not in _LIBRARY_VECTORS:
        _LIBRARY_VECTORS[key] = np.vstack(
            [encode_spectrum(r.get("h") or [], r.get("c") or []) for r in pool]
        ).astype(np.float32)
    matrix = _LIBRARY_VECTORS[key]

    query = encode_spectrum(
        observed if nucleus == "1H" else [], observed if nucleus == "13C" else []
    )
    hits = exact_knn(query, matrix, max(1, min(int(limit), 20)))

    return {
        "nucleus": nucleus,
        "observed_peaks": len(observed),
        "library_size": len(pool),
        "library_source": library.get("source") or "unknown",
        "library_license": library.get("license") or "",
        "accuracy": _SIMILARITY_ACCURACY,
        "matches": [
            {
                "smiles": pool[i].get("s") or "",
                # A citation the reader can follow, not the raw NMReDATA field.
                "name": _library_reference(pool[i].get("n") or ""),
                # L2 DISTANCE, and named as one. `exact_knn` and the platform's
                # own `vector_similarity` both return a distance where LOWER is
                # closer, so calling it "similarity" would read backwards to
                # anyone who assumes bigger is better -- and inventing a 0-1
                # similarity here would put a second scale beside the platform's,
                # which is how two numbers meaning different things end up
                # compared against one threshold.
                "distance": float(score),
                "reference_peaks": len(pool[i].get("c") or pool[i].get("h") or []),
            }
            for i, score in hits
        ],
        "human_review_required": True,
    }


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
            # THROUGH THE SAME SANITISER AS EVERY OTHER REFUSAL. This took
            # `str(refused)` raw and put it on screen, and the reader's own error
            # names the directory it failed on: a corrupt `1r` under a folder
            # called after the compound rendered the absolute path, folder name
            # and all, inside the caveat block. A filename carries a compound name
            # into a screenshot, which is the whole reason no path is shown
            # anywhere else -- and the same string named `nmrglue` to a chemist.
            rejected = _rejected_processed_reason(refused)
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
            # SCOPED TO THIS TABLE, because "nothing here" stopped being true.
            # This line was written when the desktop only measured a spectrum, and
            # it is rendered at the foot of a page that now also checks structures
            # and ranks them -- so read literally it told a chemist no structure
            # had been checked immediately after they had checked two. The claim
            # itself is still correct about the numbers it travels with; only its
            # scope was wrong, so it names them instead of the page.
            "Shifts, multiplicities and couplings in this table are measured from this "
            "spectrum alone, with no structure assumed \u2014 they do not change when a "
            "structure is checked above.",
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
