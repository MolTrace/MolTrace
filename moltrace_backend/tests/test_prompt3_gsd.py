from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.peaks.gsd import Peak, auto_classify, gsd_peak_pick


def _spectrum(
    ppm_axis: np.ndarray,
    data: np.ndarray,
    *,
    nucleus: str = "1H",
    solvent: str = "CDCl3",
    field_mhz: float = 500.0,
) -> NMRSpectrum:
    return NMRSpectrum(
        data=np.asarray(data, dtype=float),
        ppm_axis=np.asarray(ppm_axis, dtype=float),
        metadata={"source": "synthetic_prompt3_fixture"},
        nucleus=nucleus,
        solvent=solvent,
        field_mhz=field_mhz,
        acquisition_time=datetime(2024, 1, 1, tzinfo=UTC),
        fingerprint_hash="synthetic",
    )


def _lorentzian(
    ppm_axis: np.ndarray,
    *,
    center: float,
    height: float,
    fwhm: float,
) -> np.ndarray:
    hwhm = fwhm / 2.0
    return height * hwhm * hwhm / ((ppm_axis - center) ** 2 + hwhm * hwhm)


def _has_peak_near(peaks: list[Peak], position: float, tolerance: float) -> bool:
    return any(abs(peak.position_ppm - position) <= tolerance for peak in peaks)


def test_gsd_peak_pick_finds_known_1h_peaks_deterministically() -> None:
    ppm_axis = np.linspace(10.0, 0.0, 8192)
    data = (
        _lorentzian(ppm_axis, center=7.26, height=120.0, fwhm=0.010)
        + _lorentzian(ppm_axis, center=3.50, height=85.0, fwhm=0.014)
        + _lorentzian(ppm_axis, center=1.25, height=55.0, fwhm=0.018)
        + 0.05 * np.sin(np.arange(ppm_axis.size) * 0.037)
    )
    spectrum = _spectrum(ppm_axis, data)

    first = gsd_peak_pick(spectrum, level=2)
    second = gsd_peak_pick(spectrum, level=2)

    assert _has_peak_near(first, 7.26, 0.015)
    assert _has_peak_near(first, 3.50, 0.015)
    assert _has_peak_near(first, 1.25, 0.015)
    assert all(peak.shape == "voigt" for peak in first[:3])
    assert all(peak.width_hz > 0 for peak in first)
    assert all(peak.area >= 0 for peak in first)
    assert [round(peak.position_ppm, 4) for peak in first] == [
        round(peak.position_ppm, 4) for peak in second
    ]


def test_gsd_level_one_uses_lorentzian_shape() -> None:
    ppm_axis = np.linspace(5.0, 0.0, 4096)
    data = _lorentzian(ppm_axis, center=2.50, height=80.0, fwhm=0.015)
    data += 0.03 * np.sin(np.arange(ppm_axis.size) * 0.061)
    peaks = gsd_peak_pick(_spectrum(ppm_axis, data), level=1)

    assert _has_peak_near(peaks, 2.50, 0.015)
    assert peaks[0].shape == "lorentzian"


def test_auto_classify_uses_solvent_impurity_and_artifact_rules() -> None:
    ppm_axis = np.linspace(10.0, 0.0, 4096)
    data = 0.4 * np.sin(np.arange(ppm_axis.size) * 0.25)
    spectrum = _spectrum(ppm_axis, data, solvent="CDCl3")
    peaks = [
        Peak(7.26, 3630.0, 100.0, 1.0, 1.2, "voigt"),
        Peak(1.26, 630.0, 35.0, 1.0, 1.1, "voigt"),
        Peak(4.00, 2000.0, 0.2, 1.0, 1.1, "voigt"),
        Peak(3.50, 1750.0, 45.0, 1.0, 1.1, "voigt"),
    ]

    classified = auto_classify(peaks, spectrum, "CDCl3")
    by_ppm = {round(peak.position_ppm, 2): peak.category for peak in classified}

    assert by_ppm[7.26] == "solvent"
    assert by_ppm[1.26] == "impurity"
    assert by_ppm[4.00] == "artifact"
    assert by_ppm[3.50] == "compound"


def test_auto_classify_carbon13_cd3od_solvent_window() -> None:
    ppm_axis = np.linspace(220.0, -20.0, 4096)
    spectrum = _spectrum(
        ppm_axis,
        np.zeros_like(ppm_axis),
        nucleus="13C",
        solvent="CD3OD",
        field_mhz=125.0,
    )
    classified = auto_classify(
        [Peak(49.0, 6125.0, 100.0, 1.0, 2.0, "voigt")],
        spectrum,
        "CD3OD",
    )

    assert classified[0].category == "solvent"
    assert classified[0].confidence >= 0.78


def test_auto_classify_detects_symmetric_13c_satellite_pairs() -> None:
    ppm_axis = np.linspace(10.0, 0.0, 4096)
    spectrum = _spectrum(ppm_axis, np.zeros_like(ppm_axis), solvent="CDCl3")
    peaks = [
        Peak(7.125, 3562.5, 1.0, 1.0, 1.0, "voigt"),
        Peak(7.000, 3500.0, 100.0, 1.0, 1.0, "voigt"),
        Peak(6.875, 3437.5, 1.1, 1.0, 1.0, "voigt"),
    ]

    classified = auto_classify(peaks, spectrum, "CDCl3")
    categories = {round(peak.position_ppm, 3): peak.category for peak in classified}

    assert categories[7.125] == "13C_satellite"
    assert categories[6.875] == "13C_satellite"
    assert categories[7.000] == "compound"


def test_auto_classify_proton_dmso_residual_at_2_50() -> None:
    """The DMSO-d6 residual-proton quintet sits at 2.50 ppm in 1H spectra.

    auto_classify must label that peak as ``solvent`` based on the curated
    shift-window table even before any multiplicity-pattern check is wired in.
    Locks in this behaviour so a future categorisation refactor cannot silently
    regress the most common 1H solvent reference in the Fulmer table.
    """

    ppm_axis = np.linspace(10.0, 0.0, 4096)
    spectrum = _spectrum(ppm_axis, np.zeros_like(ppm_axis), solvent="DMSO-d6")
    classified = auto_classify(
        [Peak(2.50, 1250.0, 100.0, 1.0, 1.2, "voigt")],
        spectrum,
        "DMSO-d6",
    )

    assert classified[0].category == "solvent"
    assert classified[0].confidence >= 0.78
