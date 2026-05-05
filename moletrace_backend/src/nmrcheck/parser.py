from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from .exceptions import PeakParseError
from .models import Peak

PEAK_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
    (?P<shift1>-?\d+(?:\.\d+)?)
    (?:\s*[–-]\s*(?P<shift2>-?\d+(?:\.\d+)?))?
    \s*
    \(
      \s*
      (?P<multiplicity>[A-Za-z][A-Za-z ]{0,18}?)
      \s*
      (?:,\s*J\s*=\s*(?P<j_values>[^,()]+(?:,\s*[^,()]+)*)\s*Hz)?
      \s*,\s*
      (?P<integration>\d+(?:\.\d+)?)\s*H
      \s*
    \)
    """,
    re.VERBOSE,
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
    value = " ".join(raw.lower().split())
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
    text = _WHITESPACE_RE.sub(" ", text).strip()

    first_match = PEAK_PATTERN.search(text)
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
    first_match = PEAK_PATTERN.search(text)
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
    matches = list(PEAK_PATTERN.finditer(text))
    if not matches:
        raise PeakParseError(
            "Could not parse any peaks. Expected format like '3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H)'."
        )

    cursor = 0
    assignments: list[ReferencePeakAssignment] = []
    for match in matches:
        if not _allowed_gap(text[cursor:match.start()]):
            raise PeakParseError("¹H NMR text contains unparsed content between peak assignments.")
        shift1 = float(match.group("shift1"))
        shift2 = match.group("shift2")
        shift_end = float(shift2) if shift2 is not None else None
        shift = (shift1 + shift_end) / 2 if shift_end is not None else shift1
        multiplicity = normalize_multiplicity(match.group("multiplicity"))
        integration = float(match.group("integration"))
        assignments.append(
            ReferencePeakAssignment(
                shift_ppm=round(shift, 4),
                shift_start_ppm=round(shift1, 4) if shift_end is not None else None,
                shift_end_ppm=round(shift_end, 4) if shift_end is not None else None,
                multiplicity=multiplicity,
                integration_h=integration,
                j_values_hz=parse_j_values_hz(match.group("j_values")),
                raw_text=match.group(0).strip(),
            )
        )
        cursor = match.end()

    if not _allowed_gap(text[cursor:]):
        raise PeakParseError("¹H NMR text contains trailing content that could not be parsed.")

    return (normalized_text, assignments)


def parse_nmr_text(nmr_text: str) -> list[Peak]:
    _, assignments = parse_reference_nmr_text(nmr_text)
    return [assignment.as_peak() for assignment in assignments]


def total_integrated_protons(peaks: list[Peak]) -> float:
    return round(sum(peak.integration_h for peak in peaks), 4)
