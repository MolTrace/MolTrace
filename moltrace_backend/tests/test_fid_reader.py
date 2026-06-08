from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from moltrace.spectroscopy.io.fid_reader import NMRSpectrum, read_fid

ng = pytest.importorskip("nmrglue")
from nmrglue.fileio.varian import create_pdic_param  # noqa: E402

REFERENCE_1H_PEAKS = ((3.65, 1.0), (1.26, 0.65), (2.10, 0.30))
REFERENCE_13C_PEAKS = ((77.10, 1.0), (120.40, 0.85), (39.50, 0.55))


def _synthetic_fid(
    *,
    peaks: tuple[tuple[float, float], ...],
    points: int,
    sweep_width_hz: float,
    field_mhz: float,
    center_ppm: float,
    decay_hz: float = 8.0,
    scale: float = 1_000.0,
) -> np.ndarray:
    time_axis = np.arange(points, dtype=np.float64) / sweep_width_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in peaks:
        frequency_hz = (ppm - center_ppm) * field_mhz
        fid += amplitude * np.exp(-2j * np.pi * frequency_hz * time_axis) * np.exp(
            -time_axis * decay_hz
        )
    return (fid * scale).astype(np.complex64)


def _write_bruker_dataset(
    root: Path,
    *,
    nucleus: str = "1H",
    peaks: tuple[tuple[float, float], ...] = REFERENCE_1H_PEAKS,
    field_mhz: float = 500.0,
    sweep_width_hz: float = 5_000.0,
    center_ppm: float = 4.0,
    points: int = 2_048,
) -> Path:
    dataset = root / f"bruker_{nucleus.lower()}"
    data = _synthetic_fid(
        peaks=peaks,
        points=points,
        sweep_width_hz=sweep_width_hz,
        field_mhz=field_mhz,
        center_ppm=center_ppm,
    )
    udic = ng.fileiobase.create_blank_udic(1)
    udic[0].update(
        {
            "size": points,
            "complex": True,
            "sw": sweep_width_hz,
            "obs": field_mhz,
            "car": center_ppm,
            "label": nucleus,
        }
    )
    dictionary = ng.bruker.create_dic(udic)
    dictionary["acqus"].update(
        {
            "SFO1": field_mhz,
            "BF1": field_mhz,
            "SW_h": sweep_width_hz,
            "SW": sweep_width_hz / field_mhz,
            "O1": center_ppm * field_mhz,
            "O1P": center_ppm,
            "NUC1": f"<{nucleus}>",
            "SOLVENT": "<CDCl3>",
            "DATE": "1700000000",
            "BYTORDA": 0,
            "DTYPA": 0,
            "GRPDLY": 0,
        }
    )
    ng.bruker.write(str(dataset), dictionary, data, overwrite=True)
    return dataset


def _write_varian_dataset(
    root: Path,
    *,
    nucleus: str = "1H",
    peaks: tuple[tuple[float, float], ...] = REFERENCE_1H_PEAKS,
    field_mhz: float = 500.0,
    sweep_width_hz: float = 5_000.0,
    center_ppm: float = 4.0,
    points: int = 2_048,
) -> Path:
    dataset = root / f"varian_{nucleus.lower()}.fid"
    data = _synthetic_fid(
        peaks=peaks,
        points=points,
        sweep_width_hz=sweep_width_hz,
        field_mhz=field_mhz,
        center_ppm=center_ppm,
    )
    udic = ng.fileiobase.create_blank_udic(1)
    udic[0].update(
        {
            "size": points,
            "complex": True,
            "sw": sweep_width_hz,
            "obs": field_mhz,
            "car": center_ppm * field_mhz,
            "label": nucleus,
        }
    )
    dictionary = ng.varian.create_dic(udic)
    for key, value in {
        "sw": sweep_width_hz,
        "sfrq": field_mhz,
        "tof": center_ppm * field_mhz,
        "tn": "H1" if nucleus == "1H" else "C13",
        "solvent": "CDCl3",
        "seqfil": "s2pul",
    }.items():
        dictionary["procpar"][key] = create_pdic_param(key, [str(value)])
    ng.varian.write(str(dataset), dictionary, data, overwrite=True)
    return dataset


def _local_peak_position(spectrum: NMRSpectrum, expected_ppm: float, window_ppm: float = 0.04) -> float:
    mask = np.abs(spectrum.ppm_axis - expected_ppm) <= window_ppm
    assert np.any(mask), f"ppm window missing for {expected_ppm}"
    local_axis = spectrum.ppm_axis[mask]
    local_data = spectrum.data[mask]
    return float(local_axis[int(np.argmax(local_data))])


def _assert_reference_peaks_match(spectrum: NMRSpectrum, peaks: tuple[tuple[float, float], ...]) -> None:
    for ppm, _amplitude in peaks:
        assert _local_peak_position(spectrum, ppm) == pytest.approx(ppm, abs=0.01)


def _axis_has_reference_ppm(spectrum: NMRSpectrum, expected_ppm: float, tolerance: float) -> None:
    nearest_error = float(np.min(np.abs(spectrum.ppm_axis - expected_ppm)))
    assert nearest_error <= tolerance, (
        f"ppm axis misses processed reference {expected_ppm:.4f} by {nearest_error:.4f} ppm"
    )


def test_bruker_fid_reader_matches_reference_ppm_count_and_metadata(tmp_path: Path) -> None:
    dataset = _write_bruker_dataset(tmp_path)

    first = read_fid(dataset)
    second = read_fid(dataset)

    assert first.nucleus == "1H"
    assert first.solvent == "CDCl3"
    assert first.field_mhz == pytest.approx(500.0)
    assert first.acquisition_time == datetime.fromtimestamp(1700000000, UTC)
    assert first.data.shape == (65_536,)
    assert first.ppm_axis.shape == (65_536,)
    assert first.ppm_axis[0] > first.ppm_axis[-1]
    assert first.metadata["vendor"] == "Bruker"
    assert first.metadata["line_broadening_hz"] == pytest.approx(0.5)
    assert abs(first.metadata["peak_count"] - len(REFERENCE_1H_PEAKS)) <= 2
    assert first.fingerprint_hash == second.fingerprint_hash
    assert len(first.fingerprint_hash) == 64
    _assert_reference_peaks_match(first, REFERENCE_1H_PEAKS)


def test_varian_fid_reader_matches_reference_ppm_count_and_metadata(tmp_path: Path) -> None:
    dataset = _write_varian_dataset(tmp_path)

    spectrum = read_fid(dataset)

    assert spectrum.nucleus == "1H"
    assert spectrum.solvent == "CDCl3"
    assert spectrum.field_mhz == pytest.approx(500.0)
    assert spectrum.data.shape == (65_536,)
    assert spectrum.ppm_axis[0] > spectrum.ppm_axis[-1]
    assert spectrum.metadata["vendor"] == "Varian/Agilent"
    assert abs(spectrum.metadata["peak_count"] - len(REFERENCE_1H_PEAKS)) <= 2
    _assert_reference_peaks_match(spectrum, REFERENCE_1H_PEAKS)


def test_bruker_13c_reader_uses_carbon_apodization_and_ppm_scale(tmp_path: Path) -> None:
    dataset = _write_bruker_dataset(
        tmp_path,
        nucleus="13C",
        peaks=REFERENCE_13C_PEAKS,
        field_mhz=125.0,
        sweep_width_hz=30_000.0,
        center_ppm=100.0,
    )

    spectrum = read_fid(dataset)

    assert spectrum.nucleus == "13C"
    assert spectrum.field_mhz == pytest.approx(125.0)
    assert spectrum.metadata["line_broadening_hz"] == pytest.approx(2.0)
    assert math.isfinite(float(np.nanmax(spectrum.data)))
    assert abs(spectrum.metadata["peak_count"] - len(REFERENCE_13C_PEAKS)) <= 2
    _assert_reference_peaks_match(spectrum, REFERENCE_13C_PEAKS)


def test_real_nmrglue_varian_fixture_reads_metadata_and_fingerprint() -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "nmrglue" / "varian"
    expected_path = fixture_root / "expected" / "example_separate_1d_varian.json"
    fixture_spec = json.loads(expected_path.read_text(encoding="utf-8"))
    expected = fixture_spec["expected"]
    dataset = fixture_root / fixture_spec["dataset_path"]
    archive = fixture_root / "raw" / "example_separate_1d_varian.zip"

    spectrum = read_fid(dataset)
    repeated = read_fid(dataset)
    from_archive = read_fid(archive)

    assert spectrum.metadata["vendor"] == expected["vendor"]
    assert spectrum.nucleus == expected["nucleus"]
    assert spectrum.solvent == expected["solvent"]
    assert spectrum.field_mhz == pytest.approx(expected["field_mhz"])
    assert spectrum.metadata["sweep_width_hz"] == pytest.approx(expected["sweep_width_hz"])
    assert spectrum.metadata["zero_fill_points"] == expected["zero_fill_points"]
    assert spectrum.metadata["input_points"] == expected["input_points"]
    assert spectrum.data.shape == (expected["zero_fill_points"],)
    assert spectrum.ppm_axis[0] == pytest.approx(expected["ppm_axis_start"])
    assert spectrum.ppm_axis[-1] == pytest.approx(expected["ppm_axis_end"])
    assert spectrum.acquisition_time == datetime.fromisoformat(expected["acquisition_time"])
    assert spectrum.metadata["peak_count"] == expected["peak_count"]
    # The fingerprint hashes rounded float64 FFT output. numpy/scipy use
    # platform-specific BLAS backends and SIMD paths, so the absolute hash is
    # not portable across OS/arch — it was frozen on macOS/arm64 and differs on
    # the Linux/x86_64 CI runner even at identical library versions. Assert the
    # properties that actually matter (64-char format + within-run determinism),
    # matching test_nmrshiftdb2_bruker_20_fids_match_processed_references below.
    # Scientific correctness is already covered by the metadata/ppm/peak_count
    # assertions above.
    assert len(spectrum.fingerprint_hash) == 64
    assert repeated.fingerprint_hash == spectrum.fingerprint_hash
    assert from_archive.fingerprint_hash == spectrum.fingerprint_hash


def test_nmrshiftdb2_bruker_20_fids_match_processed_references() -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "nmrshiftdb2"
    manifest_path = fixture_root / "expected" / "nmrshiftdb2_bruker_20.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # NMRShiftDB2 manifest started at 20 fixtures; one (`60000023_1h`) was
    # dropped in v0.6.0 as a documented data-quality outlier (chemical-shift
    # referencing off by ~1.7 ppm).  See `removed_fixtures` in the manifest
    # for rationale and the technical white paper § 3.1 for the audit trail.
    assert manifest["fixture_count"] == 19
    for fixture in manifest["fixtures"]:
        spectrum = read_fid(fixture_root / fixture["archive"])
        repeated = read_fid(fixture_root / fixture["archive"])

        assert spectrum.metadata["vendor"] == "Bruker"
        assert spectrum.nucleus == fixture["nucleus"]
        assert spectrum.data.shape == (65_536,)
        assert spectrum.ppm_axis.shape == (65_536,)
        assert spectrum.ppm_axis[0] > spectrum.ppm_axis[-1]
        assert spectrum.fingerprint_hash == repeated.fingerprint_hash
        assert len(spectrum.fingerprint_hash) == 64

        for reference_ppm in fixture["reference_peak_ppm"]:
            _axis_has_reference_ppm(spectrum, reference_ppm, fixture["ppm_tolerance"])
        assert abs(spectrum.metadata["peak_count"] - fixture["reference_peak_count"]) <= fixture[
            "peak_count_tolerance"
        ]
