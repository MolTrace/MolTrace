"""Acquisition gating: may these integrals be read as proton counts?"""

from __future__ import annotations

from nmrcheck.acquisition_quality import (
    LEVEL_NOT,
    LEVEL_QUANTITATIVE,
    LEVEL_SEMI,
    LEVEL_UNKNOWN,
    acquisition_time_s,
    assess_1h_acquisition,
)


class TestAcquisitionTime:
    def test_bruker_td_counts_real_and_imaginary_points(self) -> None:
        # TD 65536 over a 8000 Hz sweep is 32768 complex points -> 4.096 s.
        assert acquisition_time_s(td=65536, sw_hz=8000.0) == 4.096

    def test_missing_or_nonsense_parameters_give_none(self) -> None:
        assert acquisition_time_s(td=None, sw_hz=8000.0) is None
        assert acquisition_time_s(td=65536, sw_hz=None) is None
        assert acquisition_time_s(td=0, sw_hz=8000.0) is None
        assert acquisition_time_s(td=65536, sw_hz=0.0) is None


class TestQuantitativeGating:
    def test_long_recycle_is_quantitative(self) -> None:
        result = assess_1h_acquisition(
            relaxation_delay_s=30.0, td=65536, sw_hz=8000.0, scans=16, pulse_program="zg"
        )
        assert result.level == LEVEL_QUANTITATIVE
        assert result.integrals_are_quantitative
        # The claim must be hedged: T1 is never measured on a routine dataset.
        assert "T1 was not measured" in " ".join(result.reasons)

    def test_routine_short_recycle_is_not_quantitative(self) -> None:
        # A typical routine 1H: d1 = 1 s, AQ ~ 4 s -> ~5 s recycle.
        result = assess_1h_acquisition(
            relaxation_delay_s=1.0, td=65536, sw_hz=8000.0, scans=16, pulse_program="zg30"
        )
        assert result.level == LEVEL_NOT
        assert not result.integrals_are_quantitative

    def test_intermediate_recycle_is_semi_quantitative(self) -> None:
        result = assess_1h_acquisition(
            relaxation_delay_s=8.0, td=65536, sw_hz=8000.0, scans=16, pulse_program="zg"
        )
        assert result.level == LEVEL_SEMI

    def test_missing_parameters_report_unknown_not_quantitative(self) -> None:
        """Absence of evidence must never be read as evidence of quality."""
        result = assess_1h_acquisition(
            relaxation_delay_s=None, td=65536, sw_hz=8000.0, pulse_program="zg"
        )
        assert result.level == LEVEL_UNKNOWN
        assert not result.integrals_are_quantitative
        assert "relaxation delay" in " ".join(result.reasons)

    def test_solvent_suppression_disqualifies_regardless_of_recycle(self) -> None:
        """A long recycle cannot rescue a presaturated spectrum."""
        result = assess_1h_acquisition(
            relaxation_delay_s=60.0, td=65536, sw_hz=8000.0, scans=64, pulse_program="zgpr"
        )
        assert result.level == LEVEL_NOT
        assert "suppression" in " ".join(result.reasons).lower()

    def test_noesy_presat_is_detected(self) -> None:
        result = assess_1h_acquisition(
            relaxation_delay_s=30.0, td=65536, sw_hz=8000.0, pulse_program="noesypr1d"
        )
        assert result.level == LEVEL_NOT

    def test_relaxation_encoded_sequences_are_not_quantitative(self) -> None:
        result = assess_1h_acquisition(
            relaxation_delay_s=30.0, td=65536, sw_hz=8000.0, pulse_program="t1ir"
        )
        assert result.level == LEVEL_NOT

    def test_low_scan_count_is_flagged_without_blocking(self) -> None:
        result = assess_1h_acquisition(
            relaxation_delay_s=30.0, td=65536, sw_hz=8000.0, scans=2, pulse_program="zg"
        )
        assert result.level == LEVEL_QUANTITATIVE
        assert any("scan" in reason for reason in result.reasons)

    def test_payload_is_serialisable_and_carries_parameters(self) -> None:
        payload = assess_1h_acquisition(
            relaxation_delay_s=2.0, td=65536, sw_hz=8000.0, scans=16, pulse_program="zg30"
        ).to_payload()
        assert payload["level"] == LEVEL_NOT
        assert payload["parameters"]["relaxation_delay_s"] == 2.0
        assert payload["parameters"]["acquisition_time_s"] == 4.096
        assert payload["parameters"]["recycle_time_s"] == 6.096
        assert isinstance(payload["reasons"], list)
