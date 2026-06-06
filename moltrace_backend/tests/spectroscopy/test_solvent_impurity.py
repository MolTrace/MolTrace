"""Tests for the Prompt 10 solvent / impurity expert system.

Exercises the two public entry points — :func:`detect_solvent` (most-likely
deuterated solvent from a peak pattern) and :func:`classify_peak` (per-peak
compound / solvent / residual_solvent / impurity / 13C_satellite / artifact
labelling) — plus the Fulmer 2010 reference-data integrity and the documented
scoring scheme.
"""

from __future__ import annotations

import numpy as np
import pytest

from moltrace.spectroscopy.classify import (
    COMMON_IMPURITIES,
    DEUTERATED_SOLVENTS,
    classify_peak,
    classify_peaks,
    detect_solvent,
)
from moltrace.spectroscopy.classify.solvent_impurity import (
    _C13_IMPURITIES,
    _canonical_solvent,
    _infer_nucleus,
)
from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.peaks.gsd import Peak

_VALID_CATEGORIES = {
    "compound",
    "solvent",
    "residual_solvent",
    "impurity",
    "13C_satellite",
    "artifact",
}


def _peak(
    ppm: float,
    intensity: float = 1.0,
    *,
    field_mhz: float = 500.0,
    width_hz: float = 1.0,
    snr: float = 200.0,
) -> Peak:
    return Peak(
        position_ppm=ppm,
        position_hz=ppm * field_mhz,
        intensity=intensity,
        area=intensity,
        width_hz=width_hz,
        shape="lorentzian",
        metadata={"signal_to_noise": snr},
    )


def _spectrum(nucleus: str, solvent: str | None, field_mhz: float = 500.0) -> NMRSpectrum:
    axis = np.linspace(210.0, -5.0, 4096) if nucleus == "13C" else np.linspace(12.0, -1.0, 4096)
    return NMRSpectrum(
        data=np.zeros_like(axis),
        ppm_axis=axis,
        metadata={},
        nucleus=nucleus,
        solvent=solvent,
        field_mhz=field_mhz,
    )


# --------------------------------------------------------------------------- #
# Reference-data integrity
# --------------------------------------------------------------------------- #


class TestReferenceData:
    def test_exactly_fourteen_deuterated_solvents(self) -> None:
        assert len(DEUTERATED_SOLVENTS) == 14
        names = {solv.canonical_name for solv in DEUTERATED_SOLVENTS}
        # The seven canonical Fulmer/Gottlieb columns must all be present.
        for expected in ("CDCl3", "DMSO-d6", "CD3OD", "D2O", "acetone-d6", "CD3CN", "C6D6"):
            assert expected in names

    def test_core_residual_shifts_match_fulmer(self) -> None:
        by_name = {solv.canonical_name: solv for solv in DEUTERATED_SOLVENTS}
        assert by_name["CDCl3"].residual_1h == (7.26,)
        assert by_name["CDCl3"].residual_13c == (77.16,)
        assert by_name["DMSO-d6"].residual_1h == (2.50,)
        assert by_name["DMSO-d6"].residual_13c == (39.52,)
        assert by_name["CD3OD"].residual_1h == (3.31,)
        assert by_name["acetone-d6"].residual_1h == (2.05,)
        assert by_name["C6D6"].residual_1h == (7.16,)
        assert by_name["CD3CN"].residual_1h == (1.94,)
        assert by_name["D2O"].water_1h == 4.79

    def test_impurity_table_kinds_and_coverage(self) -> None:
        assert COMMON_IMPURITIES, "impurity table must not be empty"
        kinds = {entry.kind for entry in COMMON_IMPURITIES}
        assert kinds == {"residual_solvent", "impurity"}
        labels = {entry.label.split()[0] for entry in COMMON_IMPURITIES}
        # The impurities the prompt explicitly calls out must be covered.
        for compound in ("water", "ethyl", "n-hexane", "dichloromethane", "ethanol", "methanol"):
            assert any(compound in label for label in {e.label for e in COMMON_IMPURITIES}), compound
        assert "water" in labels

    def test_water_and_tms_are_non_solvent_impurities(self) -> None:
        for entry in COMMON_IMPURITIES:
            if entry.label.startswith(("water", "TMS", "BHT", "grease", "silicone")):
                assert entry.kind == "impurity"

    def test_c13_impurity_table_present(self) -> None:
        assert _C13_IMPURITIES
        labels = {entry.label for entry in _C13_IMPURITIES}
        assert any("ethyl acetate" in label for label in labels)

    def test_fulmer_citation_registered(self) -> None:
        from nmrcheck.literature_data import reference

        ref = reference("fulmer_2010_solvent_impurities")
        assert ref is not None
        assert ref["year"] == 2010
        assert ref["doi"] == "10.1021/om100106e"


class TestSolventNameNormalisation:
    @pytest.mark.parametrize(
        ("alias", "canonical"),
        [
            ("cdcl3", "CDCl3"),
            ("chloroform-d", "CDCl3"),
            ("DMSO", "DMSO-d6"),
            ("dmso_d6", "DMSO-d6"),
            ("MeOD", "CD3OD"),
            ("methanol-d4", "CD3OD"),
            ("acetonitrile-d3", "CD3CN"),
            ("benzene-d6", "C6D6"),
            ("THF-d8", "THF-d8"),
        ],
    )
    def test_aliases_normalise(self, alias: str, canonical: str) -> None:
        assert _canonical_solvent(alias) == canonical

    def test_unknown_returns_none(self) -> None:
        assert _canonical_solvent("not-a-solvent") is None
        assert _canonical_solvent(None) is None
        assert _canonical_solvent("") is None


# --------------------------------------------------------------------------- #
# detect_solvent
# --------------------------------------------------------------------------- #


class TestDetectSolvent:
    def test_detects_cdcl3_from_residual_pattern_1h(self) -> None:
        spec = _spectrum("1H", solvent=None)
        peaks = [_peak(7.26, 6.0), _peak(1.25, 9.0), _peak(2.30, 4.0)]
        assert detect_solvent(spec, peaks) == "CDCl3"

    def test_detects_dmso_without_metadata(self) -> None:
        spec = _spectrum("1H", solvent=None)
        peaks = [_peak(2.50, 7.0), _peak(3.33, 1.2), _peak(7.10, 9.0)]
        assert detect_solvent(spec, peaks) == "DMSO-d6"

    def test_detects_from_13c_pattern(self) -> None:
        spec = _spectrum("13C", solvent=None, field_mhz=125.0)
        peaks = [
            _peak(77.16, 9.0, field_mhz=125.0),
            _peak(128.0, 3.0, field_mhz=125.0),
            _peak(30.0, 4.0, field_mhz=125.0),
        ]
        assert detect_solvent(spec, peaks) == "CDCl3"

    def test_declared_solvent_acts_as_prior_when_peaks_silent(self) -> None:
        spec = _spectrum("1H", solvent="CD3OD")
        # No peak near any residual line -> fall back to the declared solvent.
        peaks = [_peak(6.50, 5.0), _peak(0.95, 8.0)]
        assert detect_solvent(spec, peaks) == "CD3OD"

    def test_returns_unknown_with_no_peaks_and_no_metadata(self) -> None:
        spec = _spectrum("1H", solvent=None)
        assert detect_solvent(spec, []) == "unknown"


# --------------------------------------------------------------------------- #
# classify_peak — one assertion per category route
# --------------------------------------------------------------------------- #


class TestClassifyPeakCategories:
    def test_bulk_solvent_residual_is_solvent(self) -> None:
        peaks = [_peak(7.26, 5.0), _peak(1.20, 8.0), _peak(1.56, 0.6)]
        category, confidence = classify_peak(_peak(7.26, 5.0), "CDCl3", peaks)
        assert category == "solvent"
        assert confidence >= 0.45

    def test_prominent_solvent_residual_still_solvent(self) -> None:
        # The bulk-solvent residual is exempt from the impurity prominence gate.
        peaks = [_peak(7.26, 10.0), _peak(1.20, 3.0)]
        category, _conf = classify_peak(_peak(7.26, 10.0), "CDCl3", peaks)
        assert category == "solvent"

    def test_trace_water_is_impurity(self) -> None:
        peaks = [_peak(7.26, 5.0), _peak(1.20, 9.0), _peak(1.56, 0.5)]
        category, confidence = classify_peak(_peak(1.56, 0.5), "CDCl3", peaks)
        assert category == "impurity"
        assert 0.0 <= confidence <= 1.0

    def test_minor_process_solvent_is_residual_solvent(self) -> None:
        peaks = [_peak(7.20, 9.0), _peak(2.05, 0.6), _peak(4.12, 0.5)]
        cat_acetone, _c1 = classify_peak(_peak(2.05, 0.6), "CDCl3", peaks)
        cat_etoac, _c2 = classify_peak(_peak(4.12, 0.5), "CDCl3", peaks)
        assert cat_acetone == "residual_solvent"
        assert cat_etoac == "residual_solvent"

    def test_tall_analyte_methyl_is_not_stolen_by_impurity(self) -> None:
        # 1.20 ppm collides with diethyl-ether / ethanol impurity shifts, but a
        # base-peak-intensity line is too dominant to be a trace contaminant.
        peaks = [_peak(7.26, 5.0), _peak(1.20, 9.0), _peak(1.56, 0.5)]
        category, _conf = classify_peak(_peak(1.20, 9.0), "CDCl3", peaks)
        assert category == "compound"

    def test_out_of_range_proton_is_artifact(self) -> None:
        peaks = [_peak(20.0, 1.0), _peak(7.0, 9.0), _peak(1.2, 6.0)]
        category, confidence = classify_peak(_peak(20.0, 1.0), "CDCl3", peaks)
        assert category == "artifact"
        assert confidence >= 0.45

    def test_13c_satellite_wing_detected_and_parent_is_compound(self) -> None:
        offset = 0.5 * 125.0 / 500.0  # ±0.125 ppm at 500 MHz
        parent = _peak(3.00, 1000.0)
        wing_lo = _peak(3.00 - offset, 5.5)
        wing_hi = _peak(3.00 + offset, 5.5)
        peaks = [parent, wing_lo, wing_hi, _peak(7.0, 400.0)]
        cat_wing, _cw = classify_peak(wing_hi, "CDCl3", peaks)
        cat_parent, _cp = classify_peak(parent, "CDCl3", peaks)
        assert cat_wing == "13C_satellite"
        assert cat_parent == "compound"

    def test_anomalously_broad_line_is_artifact(self) -> None:
        # One line ~6x the median width and above the 25 Hz 1H floor.
        peaks = [_peak(5.0, 1.0, width_hz=80.0), _peak(7.0, 9.0), _peak(1.2, 6.0)]
        category, _conf = classify_peak(_peak(5.0, 1.0, width_hz=80.0), "CDCl3", peaks)
        assert category == "artifact"

    def test_clean_analyte_peak_is_compound(self) -> None:
        peaks = [_peak(7.26, 4.0), _peak(6.80, 9.0), _peak(3.50, 7.0)]
        category, confidence = classify_peak(_peak(6.80, 9.0), "CDCl3", peaks)
        assert category == "compound"
        assert confidence >= 0.55


class TestScoringScheme:
    def test_below_noise_alone_does_not_reclassify(self) -> None:
        # A weak but in-range, normal-width, table-miss peak: '+low' evidence
        # alone (0.30) is below the 0.45 decision threshold -> stays compound.
        peaks = [_peak(5.0, 0.01, snr=1.0), _peak(7.0, 9.0), _peak(1.2, 6.0)]
        category, _conf = classify_peak(_peak(5.0, 0.01, snr=1.0), "CDCl3", peaks)
        assert category == "compound"

    def test_low_evidence_stacks_with_high_to_flag_artifact(self) -> None:
        # Out-of-range (high) + below-noise (low) clearly an artifact.
        peaks = [_peak(25.0, 0.01, snr=1.0), _peak(7.0, 9.0)]
        category, confidence = classify_peak(_peak(25.0, 0.01, snr=1.0), "CDCl3", peaks)
        assert category == "artifact"
        assert confidence > 0.9

    def test_confidence_always_in_unit_interval(self) -> None:
        peaks = [_peak(7.26, 5.0), _peak(1.20, 9.0), _peak(1.56, 0.5), _peak(20.0, 0.4)]
        for peak in peaks:
            category, confidence = classify_peak(peak, "CDCl3", peaks)
            assert category in _VALID_CATEGORIES
            assert 0.0 <= confidence <= 1.0


class TestClassifyPeaksBatch:
    def test_batch_labels_a_realistic_mixture(self) -> None:
        peaks = [
            _peak(7.26, 5.0),   # CDCl3 residual -> solvent
            _peak(6.80, 9.0),   # analyte        -> compound
            _peak(3.50, 7.0),   # analyte        -> compound
            _peak(1.56, 0.6),   # water          -> impurity
            _peak(2.05, 0.5),   # acetone        -> residual_solvent
        ]
        results = classify_peaks(peaks, "CDCl3")
        categories = [cat for cat, _conf in results]
        assert categories[0] == "solvent"
        assert categories[1] == "compound"
        assert categories[2] == "compound"
        assert categories[3] == "impurity"
        assert categories[4] == "residual_solvent"
        assert all(0.0 <= conf <= 1.0 for _cat, conf in results)


class TestNucleusInference:
    def test_median_robust_to_single_downfield_outlier(self) -> None:
        # A lone 20 ppm line among protons must NOT flip the spectrum to 13C.
        peaks = [_peak(20.0, 1.0), _peak(7.0, 9.0), _peak(1.2, 6.0)]
        assert _infer_nucleus(peaks) == "1H"

    def test_carbon_spectrum_inferred_from_spread(self) -> None:
        peaks = [_peak(14.0), _peak(22.0), _peak(77.0), _peak(128.0), _peak(170.0)]
        assert _infer_nucleus(peaks) == "13C"
