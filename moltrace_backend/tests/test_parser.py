import pytest

from nmrcheck.exceptions import PeakParseError
from nmrcheck.parser import parse_nmr_text, parse_reference_nmr_text

TOBRAMYCIN_REFERENCE_TEXT = """'H NMR (500 MHz, D2O) 8 5.23 (d, J = 3.6 Hz, 1H), 5.08 (d, J = 3.9 Hz, 1H), 3.95 (ddd,
J= 10.3, 4.6, 2.6 Hz, 1H), 3.80 (dd, J = 6.6, 3.6 Hz, 2H), 3.68 (tdd, J = 9.2, 5.6, 3.1 Hz,
2H), 3.60 - 3.53 (т, 3H), 3.40 - 3.33 (m, 3H), 3.32 - 3.23 (m, 1H), 3.11 - 2.98 (m, 4H),
2.93 (tdd, J = 11.9,9.7, 4.1 Hz, 3H), 2.83 (dd, J = 13.6, 7.5 Hz, 1H), 2.07 (dt, J = 11.8,
4.5 Hz, 1H), 2.00 (dt, J = 13.0, 4.2 Hz, 1H), 1.71 - 1.60 (m, 1H), 1.27 (q, J = 12.5 Hz,
1H)"""


def test_parse_reference_nmr_text_normalizes_and_parses_pasted_reference_text() -> None:
    normalized, assignments = parse_reference_nmr_text(TOBRAMYCIN_REFERENCE_TEXT)

    assert normalized.startswith("1H NMR (500 MHz, D2O) δ 5.23")
    assert len(assignments) == 15
    assert assignments[0].shift_ppm == 5.23
    assert assignments[5].shift_start_ppm == 3.6
    assert assignments[5].shift_end_ppm == 3.53
    assert assignments[5].multiplicity == "t"
    assert assignments[0].j_values_hz == (3.6,)
    assert assignments[2].j_values_hz == (10.3, 4.6, 2.6)


def test_parse_nmr_text_accepts_cyrillic_multiplicity_tokens() -> None:
    peaks = parse_nmr_text("1H NMR (500 MHz, D2O) δ 3.60 - 3.53 (т, 3H)")

    assert len(peaks) == 1
    assert peaks[0].multiplicity == "t"
    assert peaks[0].integration_h == 3


def test_parse_nmr_text_preserves_j_values_on_parsed_peaks() -> None:
    peaks = parse_nmr_text("1H NMR (500 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H)")

    assert [peak.j_values_hz for peak in peaks] == [[7.1], [7.1]]


# A single 1H signal may integrate far above the old 50 H ceiling. Three
# triisopropylsilyl protecting groups put 63 equivalent protons under one
# 1.0-1.1 ppm envelope, and silyl-protected sugars like this are ordinary work,
# not an edge case. Measured over 400,000 1H records in NMRexp, the largest
# single signal per spectrum runs p99 20 H, p99.99 64 H and reaches 156 H; the
# 50 H bound sat at the 99.97th percentile and rejected real published spectra
# outright. Each value below is taken from that measured distribution.
@pytest.mark.parametrize("integration", [51.0, 63.0, 72.0, 156.0])
def test_parse_nmr_text_accepts_real_large_integrations(integration: float) -> None:
    peaks = parse_nmr_text(f"1H NMR (500 MHz, CDCl3) δ 1.08 (m, {integration:g}H)")

    assert peaks[0].integration_h == integration


def test_parse_nmr_text_names_the_signal_when_an_integration_is_impossible() -> None:
    """An impossible integration must be reported as a problem with the text.

    Left to ``Peak``'s own bound this raised a bare model-validation error,
    which the API turned into "Service temporarily unavailable" — blaming the
    server for a typo and telling the chemist nothing. The parser owns the
    check so the offending signal can be named.
    """
    with pytest.raises(PeakParseError) as excinfo:
        parse_nmr_text("1H NMR (500 MHz, CDCl3) δ 1.08 (m, 5000H)")

    message = str(excinfo.value)
    assert "1.08 ppm" in message
    assert "5000 H" in message
    # Plain language only: no model, field or HTTP vocabulary.
    assert not any(term in message.lower() for term in ("peak(", "validation", "422", "503"))


# ---------------------------------------------------------------------------
# House styles
#
# Journals do not agree on the order or the labelling of the fields inside a
# signal's brackets, and the parser used to accept exactly one arrangement.
# Measured over 20,000 real ¹H records in NMRexp, that rejected 12.4% of the
# corpus outright — on the full 3.37M-record corpus, hundreds of thousands of
# published spectra. Each case below is a format taken from those rejections.
# ---------------------------------------------------------------------------


def test_parses_integration_first_house_style_with_an_assignment_label() -> None:
    """``8.34 (1 H, dd, J = 8.0, 1.3 Hz, ArH)`` — RSC ordering.

    The count comes first and the assignment trails. This single arrangement
    accounted for 785 of the 2,479 rejections in a 20,000-record sample.
    """
    peaks = parse_nmr_text(
        "1H NMR (400 MHz, CDCl3) δ 8.34 (1 H, dd, J = 8.0, 1.3 Hz, ArH), 8.04 (1 H, s, N=CH)"
    )

    assert [(p.shift_ppm, p.multiplicity, p.integration_h) for p in peaks] == [
        (8.34, "dd", 1.0),
        (8.04, "s", 1.0),
    ]
    assert peaks[0].j_values_hz == [8.0, 1.3]


def test_parses_couplings_numbered_or_named_for_the_spin_pair() -> None:
    """``J1 = … , J2 = …`` and ``JAB = …`` are both ordinary ways to write it."""
    numbered = parse_nmr_text("1H NMR (400 MHz, DMSO) δ 7.51 (dd, J1 = 5.2 Hz, J2 = 8.4 Hz, 2H)")
    named = parse_nmr_text("1H NMR (400 MHz, CDCl3) δ 3.96 (AB, JAB = 13.6 Hz, 1H)")

    assert numbered[0].j_values_hz == [5.2, 8.4]
    assert named[0].j_values_hz == [13.6]


def test_parses_a_coupling_written_without_its_unit() -> None:
    """``J = 7.6`` with the Hz left off must not swallow the proton count."""
    peaks = parse_nmr_text("1H NMR (400 MHz, CDCl3) δ 8.24 (d, J = 7.6, 1 H)")

    assert peaks[0].j_values_hz == [7.6]
    assert peaks[0].integration_h == 1.0


@pytest.mark.parametrize("written", ["br. s", "s, br", "br. s.", "br s"])
def test_a_broad_singlet_reads_the_same_however_it_is_punctuated(written: str) -> None:
    peaks = parse_nmr_text(f"1H NMR (400 MHz, CDCl3) δ 5.65 ({written}, 1H)")

    assert peaks[0].multiplicity == "br s"


def test_parses_a_semicolon_separated_assignment() -> None:
    """``(s, 3H; OCH3)`` — Wiley house style separates the assignment with ';'."""
    peaks = parse_nmr_text("1H NMR (400 MHz, CDCl3) δ 3.73 (s, 3H; OCH3), 7.08 - 7.12 (m, 2H; ArH)")

    assert [(p.multiplicity, p.integration_h) for p in peaks] == [("s", 3.0), ("m", 2.0)]


def test_parses_an_assignment_that_contains_brackets_of_its_own() -> None:
    peaks = parse_nmr_text("1H NMR (400 MHz, CDCl3) δ 1.20 (s, 9H, C(CH3)3)")

    assert (peaks[0].multiplicity, peaks[0].integration_h) == ("s", 9.0)


@pytest.mark.parametrize(
    "trailing",
    [
        ", 13",  # the ¹³C header, truncated where the record was cut
        "; 13C NMR (100 MHz, CDCl3) δ 170.1, 145.2, 128.9",
        "; 19F NMR (376 MHz, CDCl3) δ -62.5",
    ],
)
def test_a_following_block_for_another_nucleus_is_dropped_not_an_error(trailing: str) -> None:
    """Pasting the whole experimental section is normal and is not a mistake.

    The ¹³C or ¹⁹F block that follows the ¹H data is not ¹H content, so it is
    ignored rather than failing the whole spectrum.
    """
    peaks = parse_nmr_text(f"1H NMR (400 MHz, CDCl3) δ 4.13 (s, 3H), 2.56 (s, 3H){trailing}")

    assert [p.shift_ppm for p in peaks] == [4.13, 2.56]


def test_a_negative_chemical_shift_keeps_its_sign() -> None:
    """A hydride at -12.45 ppm was silently recorded at +12.45 ppm.

    Normalizing the range dash spaced the minus sign away from its number, and
    the detached sign was then never read — putting a metal hydride in the
    middle of the aromatic window with no error raised. Negative shifts are
    ordinary in organometallic work and ``Peak`` accepts them down to -50 ppm.
    """
    peaks = parse_nmr_text("1H NMR (400 MHz, C6D6) δ 4.20 (s, 2H), -12.45 (s, 1H)")

    assert [p.shift_ppm for p in peaks] == [4.20, -12.45]


# ---------------------------------------------------------------------------
# Reading more formats must not mean accepting nonsense: text that cannot be
# read still has to say so rather than yield a plausible-looking wrong answer.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # No proton count — an assignment alone is not a signal.
        "1H NMR (400 MHz, CDCl3) δ 7.26 (m, ArH), 4.13 (s, 3H)",
        # Two proton counts — which one is the integration is not knowable.
        "1H NMR (400 MHz, CDCl3) δ 7.26 (m, 2H, 3H)",
        # Prose between signals: something was in the text that we cannot read.
        "1H NMR (400 MHz, CDCl3) δ 4.13 (s, 3H) and then some prose 2.56 (s, 3H)",
        # A trailing measurement that is not an NMR block for another nucleus.
        "1H NMR (400 MHz, CDCl3) δ 4.13 (s, 3H), mp 145 - 147 C",
    ],
)
def test_text_that_cannot_be_read_is_reported_rather_than_guessed(text: str) -> None:
    with pytest.raises(PeakParseError):
        parse_nmr_text(text)


def test_an_acquisition_header_is_never_mistaken_for_a_signal() -> None:
    """``(400 MHz, CDCl3)`` has no proton count, so it cannot be a signal."""
    peaks = parse_nmr_text("1H NMR (400 MHz, CDCl3) δ 4.13 (s, 3H)")

    assert [(p.shift_ppm, p.integration_h) for p in peaks] == [(4.13, 3.0)]


@pytest.mark.parametrize(
    ("label", "expected"),
    [("TMS", "s"), ("Ts", "s"), ("Ms", "s"), ("ArH", "s"), ("CH3", "s")],
)
def test_a_protecting_group_label_is_not_read_as_part_of_the_multiplicity(
    label: str, expected: str
) -> None:
    """TMS, Ts and Ms are spelled from the same letters the multiplicities use.

    Without this, ``0.00 (s, 9H, TMS)`` was recorded with the multiplicity
    ``s tms`` — a shape no comparison downstream can match.
    """
    peaks = parse_nmr_text(f"1H NMR (400 MHz, CDCl3) δ 2.44 (s, 3H, {label})")

    assert peaks[0].multiplicity == expected


def test_a_second_proton_block_is_not_dropped_as_if_it_were_another_nucleus() -> None:
    """Dropping it would lose real ¹H data without saying so.

    Which of two pasted ¹H spectra is *the* spectrum is not ours to decide, so
    the text is reported as unread rather than silently truncated to the first.
    """
    with pytest.raises(PeakParseError):
        parse_nmr_text(
            "1H NMR (400 MHz, CDCl3) δ 4.13 (s, 3H); 1H NMR (400 MHz, DMSO) δ 2.50 (s, 3H)"
        )


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("p", "p"),  # pentet
        ("h", "h"),  # hextet
        ("pd", "pd"),
        ("multiple peaks", "m"),
        ("comp", "m"),
        ("multiplet", "m"),
    ],
)
def test_parses_the_multiplicities_beyond_s_d_t_q_m(written: str, expected: str) -> None:
    """A pentet and a hextet are ordinary, and were the largest class still
    unread after the house-style work. The spelled-out names for an unresolved
    shape are folded onto ``m`` so they stop comparing as different shapes.
    """
    peaks = parse_nmr_text(f"1H NMR (400 MHz, CDCl3) δ 1.90 ({written}, J = 6.4 Hz, 2H)")

    assert peaks[0].multiplicity == expected


def test_a_capitalised_label_is_never_read_as_a_multiplicity() -> None:
    """``Ph`` is spelled from the pentet and hextet letters.

    Case is what separates them: multiplicities are written in lower case and
    assignment labels are capitalised. Without that rule ``(2H, Ph)`` would be
    read as a signal whose shape is "ph" — a multiplicity nobody wrote.
    """
    with pytest.raises(PeakParseError):
        parse_nmr_text("1H NMR (400 MHz, CDCl3) δ 7.30 (2H, Ph)")

    # ...but a label sitting after a real multiplicity is simply a label.
    peaks = parse_nmr_text("1H NMR (400 MHz, CDCl3) δ 7.30 (m, 5H, Ph)")
    assert peaks[0].multiplicity == "m"
