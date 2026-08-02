import pytest

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
