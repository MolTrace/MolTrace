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


def test_detect_dataset_finds_uppercase_varian_markers(tmp_path: Path) -> None:
    """`_detect_dataset` must find a Varian dataset whose marker files are
    uppercase (``FID`` / ``PROCPAR``). Vendor exports vary in case; the CI and
    Render production hosts use a case-sensitive filesystem, so a case-sensitive
    lookup would miss them (passes on a case-insensitive macOS dev box only)."""
    from moltrace.spectroscopy.io.fid_reader import _detect_dataset

    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "FID").write_bytes(b"\x00" * 16)
    (dataset / "PROCPAR").write_text("seqfil 1 1\n")

    vendor, root = _detect_dataset(tmp_path)
    assert vendor == "varian"
    assert root == dataset.resolve()


def test_varian_reader_handles_uppercase_marker_filenames(tmp_path: Path) -> None:
    """Regression (v0.23.x): Varian/Agilent "nmroned" exports store ``FID`` /
    ``PROCPAR`` uppercase. nmrglue opens them by exact lowercase name, so on a
    case-sensitive filesystem (Linux CI + the Render production host) the read
    failed — dropping the HMDB harness parseable rate from 95 % to 82 %. read_fid
    now detects case-insensitively and aliases the markers to lowercase, so the
    same dataset reads on both filesystems."""
    dataset = _write_varian_dataset(tmp_path)
    # nmrglue writes lowercase fid/procpar; uppercase them to mirror the export.
    for lower, upper in (("fid", "FID"), ("procpar", "PROCPAR")):
        src = dataset / lower
        if src.exists():
            src.rename(dataset / upper)

    spectrum = read_fid(dataset)

    assert isinstance(spectrum, NMRSpectrum)
    assert spectrum.metadata["vendor"] == "Varian/Agilent"
    assert spectrum.data.size > 0
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


def test_real_nmrglue_varian_fixture_is_arrayed_and_is_refused() -> None:
    """The nmrglue Varian example is an *arrayed* dataset, so it must be refused.

    RE-BASELINED 2026-08-20. This test previously asserted a full processed
    spectrum for this fixture: 39,000 input points (26 records x 1500,
    concatenated), a 65,536-point FFT, a ppm axis from 198.92 to -198.91, and four
    13C "reference peaks" all at negative ppm. Every one of those numbers came
    from `reshape(-1)` joining the 26 records end to end -- a measurement of
    nothing. The test passed because it had recorded the bug's own output as
    truth; see `tests/test_fid_dimensionality_refusal.py` for the invariant.

    What is still worth pinning here is the *vendor-format* coverage the fixture
    was added for (see fixtures/nmrglue/varian/README.md): detection classifies
    the directory as Varian and the real `procpar` parses. The 1D processing path
    is covered by the synthetic Varian datasets built above.
    """
    from moltrace.spectroscopy.io.fid_reader import (
        FIDReaderError,
        _detect_dataset,
        _extract_field_mhz,
        _extract_nucleus,
        _read_varian,
    )

    fixture_root = Path(__file__).parent / "fixtures" / "nmrglue" / "varian"
    fixture_spec = json.loads(
        (fixture_root / "expected" / "example_separate_1d_varian.json").read_text(encoding="utf-8")
    )
    expected = fixture_spec["expected"]
    shape = fixture_spec["dataset_shape"]
    dataset = fixture_root / fixture_spec["dataset_path"]
    archive = fixture_root / "raw" / "example_separate_1d_varian.zip"

    # The Varian format still parses -- that is what this fixture is for.
    vendor, dataset_root = _detect_dataset(dataset)
    assert vendor == expected["vendor_detected"]
    _dictionary, params, raw = _read_varian(ng, dataset_root)
    assert _extract_nucleus(params) == expected["nucleus"]
    assert _extract_field_mhz(params) == pytest.approx(expected["field_mhz"])

    # And it is arrayed, which is why no spectrum may come out of it.
    assert raw.shape == (shape["records"], shape["points_per_record"])

    for entry_point in (dataset, archive):
        with pytest.raises(FIDReaderError) as caught:
            read_fid(entry_point)
        message = str(caught.value)
        for token in expected["refusal_names"]:
            assert token in message, f"refusal does not name {token!r}: {message}"


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
