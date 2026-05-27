from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum
from moltrace.spectroscopy.preprocess.phase_baseline import auto_phase_correct, baseline_correct


def _gaussian(axis: np.ndarray, center: float, width: float, amplitude: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((axis - center) / width) ** 2)


def _synthetic_spectrum() -> tuple[NMRSpectrum, np.ndarray, np.ndarray]:
    ppm = np.linspace(10.0, 0.0, 4096, dtype=np.float64)
    clean = (
        _gaussian(ppm, 7.25, 0.015, 1.0)
        + _gaussian(ppm, 4.12, 0.020, 0.65)
        + _gaussian(ppm, 3.54, 0.012, 0.45)
        + _gaussian(ppm, 1.22, 0.018, 0.30)
    )
    centered = (ppm - float(np.mean(ppm))) / float(np.ptp(ppm))
    baseline = 0.035 + 0.018 * centered + 0.020 * centered**2
    data = clean + baseline
    spectrum = NMRSpectrum(
        data=data.astype(np.float64),
        ppm_axis=ppm,
        metadata={"fixture": "phase_baseline"},
        nucleus="1H",
        solvent="CDCl3",
        field_mhz=500.0,
        acquisition_time=datetime.fromtimestamp(1700000000, UTC),
        fingerprint_hash="source",
    )
    return spectrum, clean, baseline


def _processed_reference_spectra() -> list[tuple[str, NMRSpectrum]]:
    ng = pytest.importorskip("nmrglue")
    root = Path(__file__).parent / "fixtures" / "nmrshiftdb2" / "raw" / "extracted"
    spectra: list[tuple[str, NMRSpectrum]] = []
    for one_r in sorted(root.rglob("pdata/1/1r")):
        pdata = one_r.parent
        dictionary, data = ng.bruker.read_pdata(str(pdata), scale_data=True)
        udic = ng.bruker.guess_udic(dictionary, data)
        ppm_axis = np.asarray(ng.fileiobase.uc_from_udic(udic).ppm_scale(), dtype=np.float64)
        real_data = np.asarray(data, dtype=np.float64)
        if ppm_axis[0] < ppm_axis[-1]:
            ppm_axis = ppm_axis[::-1]
            real_data = real_data[::-1]
        scale = max(float(np.nanpercentile(np.abs(real_data), 99.5)), 1.0)
        nucleus = str(dictionary.get("procs", {}).get("AXNUC", "unknown")).strip("<>")
        spectra.append(
            (
                str(pdata.relative_to(root)),
                NMRSpectrum(
                    data=(real_data / scale).astype(np.float64),
                    ppm_axis=ppm_axis,
                    metadata={"fixture": str(pdata)},
                    nucleus=nucleus,
                ),
            )
        )
    assert spectra, "No processed Bruker reference spectra were found in tests/fixtures."
    return spectra


def test_auto_phase_regions_analysis_recovers_known_phase_without_mutating_input() -> None:
    spectrum, clean, _baseline = _synthetic_spectrum()
    phase_error = 37.0
    complex_data = clean.astype(np.complex128) * np.exp(1j * np.deg2rad(phase_error))
    complex_spectrum = NMRSpectrum(
        data=complex_data,
        ppm_axis=spectrum.ppm_axis,
        metadata=spectrum.metadata,
        nucleus=spectrum.nucleus,
        solvent=spectrum.solvent,
        field_mhz=spectrum.field_mhz,
        acquisition_time=spectrum.acquisition_time,
        fingerprint_hash=spectrum.fingerprint_hash,
    )

    corrected = auto_phase_correct(
        complex_spectrum,
        blind_regions=[(4.6, 5.1)],
    )

    phase_meta = corrected.metadata["preprocessing"]["phase"]
    assert phase_meta["method"] == "regions_analysis"
    assert phase_meta["applied_phase_deg"] == pytest.approx(-phase_error, abs=5.0)
    assert np.sqrt(np.mean(np.square(np.imag(corrected.data)))) < 0.08
    assert np.real(corrected.data).max() > 0.95 * clean.max()
    assert "preprocessing" not in complex_spectrum.metadata
    assert corrected.fingerprint_hash != complex_spectrum.fingerprint_hash


def test_processed_references_meet_phase_and_baseline_acceptance() -> None:
    phase_error = 33.0

    for label, reference in _processed_reference_spectra():
        phased_input = NMRSpectrum(
            data=reference.data.astype(np.complex128) * np.exp(1j * np.deg2rad(phase_error)),
            ppm_axis=reference.ppm_axis,
            metadata=dict(reference.metadata),
            nucleus=reference.nucleus,
        )
        phase_corrected = auto_phase_correct(phased_input)
        phase_meta = phase_corrected.metadata["preprocessing"]["phase"]
        assert phase_meta["applied_phase_deg"] == pytest.approx(-phase_error, abs=5.0), label

        centered_axis = (reference.ppm_axis - float(np.nanmean(reference.ppm_axis))) / max(
            float(np.ptp(reference.ppm_axis)),
            1e-12,
        )
        baseline_input = NMRSpectrum(
            data=reference.data + 0.02 + 0.01 * centered_axis**2,
            ppm_axis=reference.ppm_axis,
            metadata=dict(reference.metadata),
            nucleus=reference.nucleus,
        )
        baseline_method = "whittaker" if "13C" in reference.nucleus.upper() else "bernstein"
        baseline_corrected = baseline_correct(
            baseline_input,
            method=baseline_method,
            order=3,
        )
        full_scale = float(np.ptp(reference.data))
        residual = np.real(baseline_corrected.data) - reference.data
        residual = residual - float(np.nanmedian(residual))
        reference_rmse = float(np.sqrt(np.mean(np.square(residual))))
        assert reference_rmse / max(full_scale, 1e-12) < 0.005, label


def test_auto_phase_whitening_and_magnitude_modes_are_deterministic() -> None:
    spectrum, clean, _baseline = _synthetic_spectrum()
    complex_data = clean.astype(np.complex128) * np.exp(1j * np.deg2rad(-22.0))
    complex_spectrum = NMRSpectrum(
        data=complex_data,
        ppm_axis=spectrum.ppm_axis,
        metadata={},
        nucleus="1H",
    )

    first = auto_phase_correct(complex_spectrum, method="whitening")
    second = auto_phase_correct(complex_spectrum, method="whitening")
    magnitude = auto_phase_correct(complex_spectrum, method="magnitude")

    assert first.metadata["preprocessing"]["phase"]["method"] == "whitening"
    assert first.fingerprint_hash == second.fingerprint_hash
    assert np.all(np.asarray(magnitude.data) >= 0.0)
    assert magnitude.metadata["preprocessing"]["phase"]["method"] == "magnitude"


@pytest.mark.parametrize("method", ["bernstein", "polynomial", "spline", "whittaker"])
def test_baseline_correction_methods_reduce_baseline_error(method: str) -> None:
    spectrum, clean, baseline = _synthetic_spectrum()
    corrected = baseline_correct(spectrum, method=method, order=3)

    source_rmse = float(np.sqrt(np.mean(np.square(baseline))))
    corrected_rmse = float(np.sqrt(np.mean(np.square(np.real(corrected.data) - clean))))
    full_scale = float(np.ptp(spectrum.data))

    assert corrected.metadata["preprocessing"]["baseline"]["method"] == method
    assert corrected_rmse < source_rmse * 0.45
    assert corrected_rmse / full_scale < 0.005
    assert corrected.ppm_axis[0] > corrected.ppm_axis[-1]
    assert "preprocessing" not in spectrum.metadata


def test_baseline_correction_preserves_complex_imaginary_channel() -> None:
    spectrum, _clean, _baseline = _synthetic_spectrum()
    imaginary = np.linspace(0.0, 1.0, spectrum.data.size)
    complex_spectrum = NMRSpectrum(
        data=spectrum.data.astype(np.complex128) + 1j * imaginary,
        ppm_axis=spectrum.ppm_axis,
        metadata={},
        nucleus="13C",
    )

    corrected = baseline_correct(complex_spectrum, method="bernstein")

    assert np.allclose(np.imag(corrected.data), imaginary)
    baseline_meta = corrected.metadata["preprocessing"]["baseline"]
    assert baseline_meta["baseline_model"] == "bernstein_polynomial"


def test_unknown_phase_and_baseline_methods_raise_clear_errors() -> None:
    spectrum, _clean, _baseline = _synthetic_spectrum()

    with pytest.raises(ValueError, match="Unsupported phase correction method"):
        auto_phase_correct(spectrum, method="not-a-method")
    with pytest.raises(ValueError, match="Unsupported baseline correction method"):
        baseline_correct(spectrum, method="not-a-method")
