from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from .exceptions import PeakParseError
from .models import MAX_SIGNAL_INTEGRATION_H, Peak

# A signal is a shift (or a shift range) followed by a parenthesised group.
# What is INSIDE that group is not fixed by any convention - journals order the
# fields differently, label them differently, and omit units - so the group is
# captured whole here and classified field by field in ``_classify_signal_body``
# rather than pinned down by this pattern. One level of nesting is allowed so an
# assignment like ``C(CH3)3`` does not truncate the group.
PEAK_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
    (?P<shift1>-?\d+(?:\.\d+)?)
    (?:\s*[–-]\s*(?P<shift2>-?\d+(?:\.\d+)?))?
    \s*
    \(
      (?P<body>(?:[^()]|\([^()]*\))*)
    \)
    """,
    re.VERBOSE,
)

# ---------------------------------------------------------------------------
# Signal-body fields
#
# Real published ¹H data does not agree on the order or the labelling of the
# fields inside the brackets. All of the following are ordinary, and every one
# of them was rejected outright before this classifier existed:
#
#     3.65 (q, J = 7.1 Hz, 2H)              multiplicity first (ACS style)
#     8.34 (1 H, dd, J = 8.0, 1.3 Hz, ArH)  integration first (RSC style)
#     7.61 (d, J = 8.1 Hz, 4H, Har)         trailing assignment label
#     7.51 (dd, J1 = 5.2 Hz, J2 = 8.4 Hz, 2H)   couplings numbered separately
#     3.96 (AB, JAB = 13.6 Hz, 1H)          coupling named for the spin pair
#     8.24 (d, J = 7.6, 1 H)                coupling with the unit left off
#     5.65 (br. s, 1H)                      punctuated multiplicity
#
# Each field is therefore identified by what it looks like, not by where it
# sits, and anything left over is an assignment label and is not a signal.
# ---------------------------------------------------------------------------

#: ``2H``, ``1 H`` - a proton count. Deliberately anchored so that ``2 Hz``
#: (a coupling constant) and ``2CH3`` (an assignment) cannot match.
_INTEGRATION_FIELD_RE: Final[re.Pattern[str]] = re.compile(r"\d+(?:\.\d+)?\s*H", re.IGNORECASE)

#: ``J =``, ``J1 =``, ``JAB =``, ``J2' =`` - a coupling, however it is labelled.
_J_FIELD_RE: Final[re.Pattern[str]] = re.compile(
    r"J[A-Za-z0-9'′]{0,4}\s*=\s*(?P<values>.*)", re.IGNORECASE
)

#: A bare number continuing a coupling list (``J = 8.0, 1.3 Hz``). Cannot match
#: an integration, so ``J = 7.6, 1 H`` still yields one coupling and one count.
_J_CONTINUATION_FIELD_RE: Final[re.Pattern[str]] = re.compile(
    r"[-+]?\d+(?:\.\d+)?\s*(?:Hz)?", re.IGNORECASE
)

#: Multiplicities built from the single-letter cores - s, d, t, q, p (pentet),
#: h (hextet), m - and their combinations (dd, ddd, dt, tdd, pd, ...).
#:
#: Only ever applied to a token written in lower case. Assignment labels are
#: capitalised and are spelled from these same letters - Ph, Ts, Ms, TMS - so
#: case is what separates the pentet ``p`` from the phenyl ``Ph``.
_MULTIPLICITY_CORE_RE: Final[re.Pattern[str]] = re.compile(r"[sdtqmph]{1,5}")

#: Spelled-out multiplicities and modifiers that the letter cores do not cover.
_MULTIPLICITY_WORDS: Final[frozenset[str]] = frozenset(
    {
        "br", "b", "bs", "brs", "brd", "broad",
        "app", "apt", "apparent",
        "quin", "quint", "quintet",
        "sex", "sext", "sextet",
        "sep", "sept", "spt", "septet",
        "hep", "hept", "heptet",
        "oct", "octet", "non", "nonet",
        "ab", "abq", "abx",
        "pent", "pentet",
        "comp", "complex", "multiplet", "multiple", "peaks",
    }
)

#: Fields inside the brackets are separated by a comma in most house styles and
#: by a semicolon in others ("3H; ArH"); a pasted CJK comma appears too.
_SIGNAL_FIELD_SEPARATOR_RE: Final[re.Pattern[str]] = re.compile(r"[,;，；]")

#: Modifiers that describe line shape rather than coupling. They are written
#: either before or after the multiplicity; both are recorded as ``br s``.
_BROADENING_WORDS: Final[frozenset[str]] = frozenset({"br", "b", "bs", "brs", "broad"})

#: A following block for a different nucleus. ¹H data is routinely pasted with
#: the ¹³C or ¹⁹F section that follows it in the experimental, and the corpus
#: also holds the truncated form - a dangling ``, 13`` where the ¹³C header was
#: cut. Neither is ¹H content; both are dropped rather than treated as an error.
_FOLLOWING_NUCLEUS_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"""
    ^[\s,;.]*
    (?!1\s*H\b)          # a second ¹H block is ¹H data; never drop it silently
    (?:
        \d{1,3}\s*[A-Za-z]{1,2}\s*(?:\{[^}]*\}\s*)?\s*NMR\b
      | \d{1,3}\s*$
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_HEADER_VARIANT_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*['`‘’\"]?\s*(?:[iIlL1¹])?\s*h\s*nmr\b",
    re.IGNORECASE,
)

_UNICODE_DASH_RE: Final[re.Pattern[str]] = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")
_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_J_EQUALS_RE: Final[re.Pattern[str]] = re.compile(r"\bJ\s*=\s*", re.IGNORECASE)
_FLOAT_VALUE_RE: Final[re.Pattern[str]] = re.compile(r"[-+]?\d+(?:\.\d+)?")
_CYRILLIC_LOOKALIKE_TRANSLATION = str.maketrans(
    {
        "т": "t",
        "Т": "T",
        "м": "m",
        "М": "M",
        "ѕ": "s",
        "Ѕ": "S",
        "ԛ": "q",
        "Ԛ": "Q",
        "ԁ": "d",
        "Ԁ": "D",
    }
)

NORMALIZED_MULTIPLICITIES = {
    "s": "s",
    "d": "d",
    "t": "t",
    "q": "q",
    "m": "m",
    "br s": "br s",
    "br": "br",
    "dd": "dd",
    "ddd": "ddd",
    "dt": "dt",
    "td": "td",
    "tt": "tt",
    "dq": "dq",
    "qd": "qd",
    "tdd": "tdd",
    "ddt": "ddt",
    "app t": "app t",
    "app d": "app d",
    # Spelled-out names for the same unresolved shape. They compared as
    # different multiplicities until they were folded onto "m".
    "multiplet": "m",
    "multiple peaks": "m",
    "comp": "m",
    "complex": "m",
}


@dataclass(frozen=True)
class ReferencePeakAssignment:
    shift_ppm: float
    shift_start_ppm: float | None
    shift_end_ppm: float | None
    multiplicity: str
    integration_h: float
    j_values_hz: tuple[float, ...]
    raw_text: str

    def as_peak(self) -> Peak:
        return Peak(
            shift_ppm=self.shift_ppm,
            multiplicity=self.multiplicity,
            integration_h=self.integration_h,
            j_values_hz=list(self.j_values_hz),
        )


def normalize_multiplicity(raw: str) -> str:
    # Periods are decoration - "br. s." and "br s" are the same multiplicity,
    # and leaving them in produced two spellings that compared as different.
    value = " ".join(raw.lower().replace(".", " ").split())
    return NORMALIZED_MULTIPLICITIES.get(value, value)


def parse_j_values_hz(raw: str | None) -> tuple[float, ...]:
    if raw is None:
        return ()
    values: list[float] = []
    for token in _FLOAT_VALUE_RE.findall(str(raw)):
        try:
            value = round(float(token), 1)
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    return tuple(values)


@dataclass(frozen=True)
class _SignalBody:
    """The classified contents of one signal's brackets."""

    multiplicity: str
    integration_h: float
    j_values_hz: tuple[float, ...]


def _looks_like_multiplicity(field: str) -> bool:
    """True for a multiplicity token, false for an assignment label.

    Decided on shape, because position is not reliable: ``ArH``, ``Har``,
    ``2CH3``, ``NH``, ``H-4`` and ``N=CH`` all sit where a multiplicity can sit.
    A multiplicity is built from the lower-case letter cores or from a
    spelled-out name; an assignment label carries element symbols, digits or
    bonds and so fails both tests.

    Case carries real weight here. ``Ph``, ``Ts``, ``Ms`` and ``TMS`` are built
    from the very letters the cores use, so without the lower-case requirement
    a phenyl label would be read as a pentet-heptet.
    """
    cleaned = field.replace(".", " ").strip()
    if not cleaned or len(cleaned) > 20:
        return False
    parts = cleaned.split()
    return bool(parts) and all(
        part.lower() in _MULTIPLICITY_WORDS
        or (part.islower() and _MULTIPLICITY_CORE_RE.fullmatch(part))
        for part in parts
    )


def _classify_signal_body(body: str) -> _SignalBody | None:
    """Read one signal's bracketed fields, in whatever order they were written.

    Returns ``None`` when the group is not a signal at all - an acquisition
    header like ``(400 MHz, CDCl3)`` has no proton count, and a group with two
    proton counts is ambiguous. Refusing here keeps the caller's guarantee that
    text which cannot be read is reported rather than silently dropped.
    """
    fields = [field.strip() for field in _SIGNAL_FIELD_SEPARATOR_RE.split(body)]
    fields = [field for field in fields if field]

    integrations: list[float] = []
    j_values: list[float] = []
    multiplicity_tokens: list[str] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        if _INTEGRATION_FIELD_RE.fullmatch(field):
            integrations.append(float(_FLOAT_VALUE_RE.findall(field)[0]))
            index += 1
            continue
        coupling = _J_FIELD_RE.fullmatch(field)
        if coupling is not None:
            j_values.extend(parse_j_values_hz(coupling.group("values")))
            index += 1
            # "J = 8.0, 1.3 Hz" splits across fields; keep taking bare numbers
            # until the unit closes the list or a non-number ends it.
            while index < len(fields) and _J_CONTINUATION_FIELD_RE.fullmatch(fields[index]):
                j_values.extend(parse_j_values_hz(fields[index]))
                closed = fields[index].lower().rstrip().endswith("hz")
                index += 1
                if closed:
                    break
            continue
        if _looks_like_multiplicity(field):
            multiplicity_tokens.append(field)
            index += 1
            continue
        index += 1  # an assignment label; ``raw_text`` keeps it

    if len(integrations) != 1 or not multiplicity_tokens:
        return None

    # A line-shape modifier is written on either side of the multiplicity
    # ("br. s" and "s, br" are both ordinary); record one spelling for both.
    #
    # Only the FIRST core is the multiplicity. Protecting-group labels are
    # spelled from the same letters the multiplicity cores use - TMS, Ts and Ms
    # are all s/d/t/q/m - so "0.00 (s, 9H, TMS)" would otherwise be recorded as
    # the multiplicity "s tms". A later core is a label, not part of the shape.
    modifiers: list[str] = []
    cores: list[str] = []
    for token in multiplicity_tokens:
        bucket = modifiers if token.strip(". ").lower() in _BROADENING_WORDS else cores
        bucket.append(token)
    multiplicity = normalize_multiplicity(" ".join(modifiers + cores[:1] if cores else modifiers))
    if not multiplicity or len(multiplicity) > 20:
        return None
    return _SignalBody(
        multiplicity=multiplicity,
        integration_h=integrations[0],
        j_values_hz=tuple(j_values),
    )


def _iter_signals(text: str) -> Iterator[tuple[re.Match[str], _SignalBody]]:
    """Yield only the bracketed groups that are genuinely signals."""
    for match in PEAK_PATTERN.finditer(text):
        body = _classify_signal_body(match.group("body"))
        if body is not None:
            yield (match, body)


def _first_signal(text: str) -> re.Match[str] | None:
    for match, _body in _iter_signals(text):
        return match
    return None


def normalize_nmr_text(nmr_text: str) -> str:
    text = str(nmr_text).strip()
    if not text:
        raise PeakParseError("¹H NMR text cannot be empty.")
    text = text.translate(_CYRILLIC_LOOKALIKE_TRANSLATION)
    text = _UNICODE_DASH_RE.sub("-", text)
    text = text.replace("δ", " δ ")
    text = _HEADER_VARIANT_RE.sub("1H NMR", text, count=1)
    text = _J_EQUALS_RE.sub("J = ", text)
    text = re.sub(r"\s*-\s*", " - ", text)
    # That last step spaces out the dash so a shift RANGE reads uniformly, but
    # it also detached the minus sign from a negative shift, and the detached
    # sign was then not read at all: a metal hydride at -12.45 ppm was recorded
    # as +12.45, in the middle of the aromatic window, with no error raised.
    # A dash that opens a value - after δ, a comma, a semicolon or a bracket -
    # is a sign and belongs to the number; a dash between two numbers is a range.
    text = re.sub(r"(?<=[δ,;(])\s+-\s+(?=\d)", " -", text)
    text = re.sub(r"^\s*-\s+(?=\d)", "-", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    first_match = _first_signal(text)
    if first_match and "δ" not in text[: first_match.start() + 1]:
        prefix = text[: first_match.start()]
        if re.search(r"\bNMR\b", prefix, flags=re.IGNORECASE):
            prefix = re.sub(r"\s*[8B]\s*$", "", prefix).rstrip(" ;,")
            text = f"{prefix} δ {text[first_match.start():].lstrip()}".strip()
    return _WHITESPACE_RE.sub(" ", text).strip()


def _strip_nmr_header(nmr_text: str) -> str:
    text = normalize_nmr_text(nmr_text)
    if "δ" in text:
        return text.split("δ", 1)[1].strip()
    first_match = _first_signal(text)
    if first_match:
        return text[first_match.start() :].strip()
    return text


def _allowed_gap(fragment: str) -> bool:
    cleaned = fragment.strip()
    if not cleaned:
        return True
    cleaned = cleaned.replace(",", "").replace(";", "").replace("·", "").replace("•", "")
    cleaned = cleaned.replace("–", "").replace("-", "").replace("~", "")
    return cleaned.strip() == ""


def parse_reference_nmr_text(nmr_text: str) -> tuple[str, list[ReferencePeakAssignment]]:
    normalized_text = normalize_nmr_text(nmr_text)
    text = _strip_nmr_header(normalized_text)
    signals = list(_iter_signals(text))
    if not signals:
        raise PeakParseError(
            "Could not parse any peaks. Expected format like '3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H)'."
        )

    cursor = 0
    assignments: list[ReferencePeakAssignment] = []
    for match, body in signals:
        if not _allowed_gap(text[cursor:match.start()]):
            raise PeakParseError("¹H NMR text contains unparsed content between peak assignments.")
        shift1 = float(match.group("shift1"))
        shift2 = match.group("shift2")
        shift_end = float(shift2) if shift2 is not None else None
        shift = (shift1 + shift_end) / 2 if shift_end is not None else shift1
        multiplicity = body.multiplicity
        integration = body.integration_h
        # Reject an impossible integration HERE, where the offending signal can
        # still be named. Left to the Peak model it surfaced as a bare
        # validation error, which the API turned into "Service temporarily
        # unavailable" — a message that blames the server for a problem with
        # the text and gives the chemist nothing to act on.
        if integration > MAX_SIGNAL_INTEGRATION_H:
            raise PeakParseError(
                f"The signal at {shift:g} ppm reads as {integration:g} H, which is more "
                "protons than any single signal can hold. Check that value in the "
                "¹H NMR text — a coupling constant or a mass is easy to paste into the "
                "integration by mistake."
            )
        assignments.append(
            ReferencePeakAssignment(
                shift_ppm=round(shift, 4),
                shift_start_ppm=round(shift1, 4) if shift_end is not None else None,
                shift_end_ppm=round(shift_end, 4) if shift_end is not None else None,
                multiplicity=multiplicity,
                integration_h=integration,
                j_values_hz=body.j_values_hz,
                raw_text=match.group(0).strip(),
            )
        )
        cursor = match.end()

    tail = text[cursor:]
    if not _allowed_gap(tail) and not _FOLLOWING_NUCLEUS_BLOCK_RE.match(tail):
        raise PeakParseError("¹H NMR text contains trailing content that could not be parsed.")

    return (normalized_text, assignments)


def parse_nmr_text(nmr_text: str) -> list[Peak]:
    _, assignments = parse_reference_nmr_text(nmr_text)
    return [assignment.as_peak() for assignment in assignments]


def total_integrated_protons(peaks: list[Peak]) -> float:
    return round(sum(peak.integration_h for peak in peaks), 4)
