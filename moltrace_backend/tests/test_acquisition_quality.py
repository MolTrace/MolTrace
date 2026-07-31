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

    def test_routine_zg30_is_semi_quantitative_not_condemned(self) -> None:
        """DELIBERATE RE-BASELINE (was LEVEL_NOT).

        A typical routine 1H — d1 = 1 s, AQ ~ 4 s, 30 degree pulse — is the
        single most common experiment in existence. The old flat threshold
        applied the 5xT1 rule that is calibrated for a 90 degree pulse and
        condemned it outright. At 30 degrees the steady state is far less
        T1-sensitive: the same 5 s recycle leaves ~8% differential saturation
        rather than ~58%, which is a real limitation but not grounds to refuse
        the integrals. Verified against the user's own 500 MHz zg30 data.
        """
        result = assess_1h_acquisition(
            relaxation_delay_s=1.0, td=65536, sw_hz=8000.0, scans=16, pulse_program="zg30"
        )
        assert result.level == LEVEL_SEMI
        assert not result.integrals_are_quantitative

    def test_same_recycle_at_90_degrees_is_not_quantitative(self) -> None:
        """The flip angle, not just the delay, decides the verdict."""
        result = assess_1h_acquisition(
            relaxation_delay_s=1.0, td=65536, sw_hz=8000.0, scans=16, pulse_program="zg"
        )
        assert result.level == LEVEL_NOT
        assert result.parameters["pulse_angle_deg"] == 90.0
        assert result.parameters["differential_saturation_ratio"] > 1.4

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
        # Re-baselined alongside the flip-angle model: a 30 degree pulse with a
        # 6.1 s recycle is semi-quantitative, not disqualified.
        payload = assess_1h_acquisition(
            relaxation_delay_s=2.0, td=65536, sw_hz=8000.0, scans=16, pulse_program="zg30"
        ).to_payload()
        assert payload["level"] == LEVEL_SEMI
        assert payload["parameters"]["relaxation_delay_s"] == 2.0
        assert payload["parameters"]["acquisition_time_s"] == 4.096
        assert payload["parameters"]["recycle_time_s"] == 6.096
        assert payload["parameters"]["pulse_angle_deg"] == 30.0
        assert isinstance(payload["reasons"], list)


class TestFlipAngleModel:
    def test_pulse_angle_is_read_from_the_program_name(self) -> None:
        from nmrcheck.acquisition_quality import pulse_angle_from_program

        assert pulse_angle_from_program("zg30") == 30.0
        assert pulse_angle_from_program("zg60") == 60.0
        assert pulse_angle_from_program("zg") == 90.0
        # Unknown sequences fall back to 90, the conservative choice.
        assert pulse_angle_from_program("something_odd") == 90.0
        assert pulse_angle_from_program(None) == 90.0

    def test_full_relaxation_removes_differential_saturation(self) -> None:
        from nmrcheck.acquisition_quality import differential_saturation_ratio

        # Long recycle at any flip angle: fast and slow relaxers respond alike.
        assert differential_saturation_ratio(recycle_s=60.0, angle_deg=90.0) < 1.001
        assert differential_saturation_ratio(recycle_s=60.0, angle_deg=30.0) < 1.001

    def test_small_flip_angle_tolerates_a_shorter_recycle(self) -> None:
        from nmrcheck.acquisition_quality import differential_saturation_ratio

        short = 5.0
        wide = differential_saturation_ratio(recycle_s=short, angle_deg=90.0)
        narrow = differential_saturation_ratio(recycle_s=short, angle_deg=30.0)
        assert narrow < wide, (
            "a 30 degree pulse must be less T1-sensitive than a 90 at the same "
            f"recycle; got {narrow:.3f} vs {wide:.3f}"
        )
        assert wide > 1.4 and narrow < 1.15
