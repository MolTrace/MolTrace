"""Acquisition gating: may these integrals be read as proton counts?"""

from __future__ import annotations

import pytest

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
        T1-sensitive: the same 5 s recycle leaves ~15% differential saturation
        rather than ~112%, which is a real limitation but not grounds to refuse
        the integrals.

        The figure was ~8% when this test was written, under a T1 range that
        assumed every proton relaxes within 5 s. Integrating a real matched
        pair (30 s vs 5 s recycle, same sample) measured 14.1%, so the range
        was widened and the number here corrected. The VERDICT is unchanged,
        which is the point of the test.
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

    def test_intermediate_recycle_at_90_degrees_is_not_quantitative(self) -> None:
        """DELIBERATE RE-BASELINE (was LEVEL_SEMI).

        A 90 degree pulse at d1 = 8 s (≈12 s recycle) was called
        semi-quantitative when the model assumed protons relax within 5 s. With
        a realistic 8 s ceiling it leaves ~28% differential saturation, and the
        classic rule agrees: a 90 degree pulse needs ~5·T1, which is 40 s for
        an 8 s proton, not 12.

        This is the one classification the wider T1 range genuinely moves, and
        it moves in the direction the chemistry supports. A 30 degree pulse at
        the same recycle stays semi-quantitative — that case is covered by
        test_routine_zg30_is_semi_quantitative_not_condemned — so the change
        does not condemn ordinary routine work.
        """
        result = assess_1h_acquisition(
            relaxation_delay_s=8.0, td=65536, sw_hz=8000.0, scans=16, pulse_program="zg"
        )
        assert result.level == LEVEL_NOT
        assert result.parameters["pulse_angle_deg"] == 90.0

    def test_intermediate_recycle_at_30_degrees_stays_semi_quantitative(self) -> None:
        """The counterpart: the same recycle with a small flip angle is usable."""
        result = assess_1h_acquisition(
            relaxation_delay_s=8.0, td=65536, sw_hz=8000.0, scans=16, pulse_program="zg30"
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
        # RE-BASELINED with the T1 range (0.5-5 s -> 0.5-8 s): narrow moved
        # 1.078 -> 1.154. The claim under test is the GAP between the two flip
        # angles, which is unchanged and large (2.15 vs 1.15); only the
        # absolute bound needed moving. 1.154 is also the value that now
        # brackets the 1.141 measured on a real 5 s / 30 degree acquisition.
        assert wide > 1.4 and narrow < 1.20


class TestAgainstMeasuredSpectra:
    """Pinned to a real matched pair, not to the model's own arithmetic.

    naw-1-244-54pt: one sample, one probe, two acquisitions differing only in
    relaxation delay — 22.005 s + 7.995 s AQ = 30.00 s recycle, and 1.000 s +
    3.998 s AQ = 5.00 s — both zg30 on a 500 MHz instrument. Integrating
    identical ppm windows in the two processed spectra, the per-window ratio
    between them spread by a factor of 1.141. That is a MEASUREMENT of
    differential saturation at a 5 s recycle, and the model has to be
    consistent with it.
    """

    def test_the_fully_relaxed_acquisition_is_called_quantitative(self) -> None:
        from nmrcheck.acquisition_quality import assess_1h_acquisition

        result = assess_1h_acquisition(
            relaxation_delay_s=22.00461, td=131072,
            sw_hz=16.3881000708626 * 500.16300096, scans=16, pulse_program="zg30",
        )
        assert result.level == LEVEL_QUANTITATIVE
        assert result.parameters["recycle_time_s"] == pytest.approx(30.0, abs=0.01)

    def test_the_routine_acquisition_is_flagged_but_not_condemned(self) -> None:
        from nmrcheck.acquisition_quality import assess_1h_acquisition

        result = assess_1h_acquisition(
            relaxation_delay_s=1.0, td=65536,
            sw_hz=16.3881000708626 * 500.16300096, scans=16, pulse_program="zg30",
        )
        assert result.level == LEVEL_SEMI
        assert result.parameters["recycle_time_s"] == pytest.approx(5.0, abs=0.01)

    def test_the_predicted_bias_brackets_what_was_measured(self) -> None:
        """The estimate must not fall SHORT of the observed spread.

        It read 1.078 against the observed value before the T1 range was
        widened, i.e. it told the chemist the integrals were better than they
        were. Being conservative in the other direction is acceptable; being
        optimistic is not.

        RE-MEASURED 2026-08-04 on the full matched pair with a better method:
        signal windows are now taken from the FULLY RELAXED spectrum (exp 10,
        >2% of max, 28 windows) and each window compared as a share of its own
        spectrum's total, which removes the receiver-gain and NC_proc scaling
        difference between the two datasets instead of assuming it away. That
        gives 1.1334, against 1.141 from the earlier cruder pass -- close
        enough to confirm the original figure, and preferred here because the
        normalisation is principled rather than incidental.

        Against 1.1334 the current model reads 1.1543 (+0.021, conservative)
        and the pre-fix model read 1.0784 (-0.055, optimistic). The fix cut the
        magnitude of the error by ~2.6x and, more importantly, moved it to the
        safe side.
        """
        from nmrcheck.acquisition_quality import differential_saturation_ratio

        MEASURED = 1.1334
        predicted = differential_saturation_ratio(recycle_s=5.0, angle_deg=30.0)

        assert predicted >= MEASURED, (
            f"model predicts {predicted:.4f} but {MEASURED} was measured on a real "
            "matched pair; an optimistic estimate understates the error a chemist "
            "will actually see"
        )
        assert predicted <= MEASURED * 1.25, (
            f"model predicts {predicted:.4f}, far above the measured {MEASURED}; "
            "an over-pessimistic estimate condemns usable spectra"
        )
