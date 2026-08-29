from __future__ import annotations

import json
import math
import shutil
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


# Cross-platform regression guard tolerances for the real-FID fingerprint test.
# numpy/scipy use platform-specific BLAS backends and SIMD paths, so a byte-exact
# hash of the rounded spectrum is not portable across OS/arch (it diverged between
# macOS/arm64 and the Linux/x86_64 CI runner). Peak positions and heights
# normalized to the spectrum max, however, agree across platforms to far better
# than these tolerances while still catching any real regression in the
# FID-processing pipeline. ppm tol ~8 axis bins; intensity tol 0.5% of full scale.
_REAL_FID_PEAK_PPM_TOL = 0.05
_REAL_FID_PEAK_INTENSITY_ATOL = 0.005


def _assert_reference_peak_values(
    spectrum: NMRSpectrum,
    reference_peaks: list[dict[str, float]],
    *,
    window_ppm: float = 0.04,
) -> None:
    scale = float(np.max(np.abs(spectrum.data)))
    assert scale > 0.0, "spectrum is flat — cannot normalize peak heights"
    for peak in reference_peaks:
        target = float(peak["ppm"])
        mask = np.abs(spectrum.ppm_axis - target) <= window_ppm
        assert np.any(mask), f"ppm window missing for {target}"
        local_axis = spectrum.ppm_axis[mask]
        local_data = spectrum.data[mask]
        idx = int(np.argmax(local_data))
        position = float(local_axis[idx])
        norm_intensity = float(local_data[idx]) / scale
        assert position == pytest.approx(target, abs=_REAL_FID_PEAK_PPM_TOL), (
            f"peak position {position:.4f} ppm off reference {target:.4f} ppm"
        )
        assert norm_intensity == pytest.approx(
            float(peak["norm_intensity"]), abs=_REAL_FID_PEAK_INTENSITY_ATOL
        ), (
            f"peak height {norm_intensity:.5f} off reference "
            f"{float(peak['norm_intensity']):.5f} at {target:.4f} ppm"
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


def test_the_real_nmrglue_varian_fixture_is_arrayed_and_is_refused() -> None:
    """Re-baselined. This test used to pin the fingerprint of a splice.

    The only real Varian dataset in the tree is nmrglue's `separate_1d_varian`
    example -- named for what it demonstrates, and shipped with a `separate.py`.
    nmrglue returns shape (26, 1500) for it. The reader reshaped that to one
    39000-point pseudo-FID, and this test asserted `input_points == 39000`,
    `peak_count == 75` and a reference-peak table: every one of those values
    described 26 experiments laid end to end. The golden recorded the answer that
    was produced first, not a true one.

    What is worth pinning is that the refusal is not path-dependent -- a chemist
    who hands it the directory and a chemist who hands it the zip must get the
    same answer. Single-trace Varian metadata, ppm axis and peak coverage is
    unaffected and still runs, against the synthesised dataset in
    `test_varian_fid_reader_matches_reference_ppm_count_and_metadata`.
    """
    from moltrace.spectroscopy.io.fid_reader import FIDReaderError

    fixture_root = Path(__file__).parent / "fixtures" / "nmrglue" / "varian"
    fixture_spec = json.loads(
        (fixture_root / "expected" / "example_separate_1d_varian.json").read_text(encoding="utf-8")
    )
    expected = fixture_spec["expected"]
    assert expected["arrayed"] is True, "the fixture no longer records this dataset as arrayed"

    dataset = fixture_root / fixture_spec["dataset_path"]
    archive = fixture_root / "raw" / "example_separate_1d_varian.zip"

    messages = []
    for source in (dataset, archive):
        if not source.exists():
            continue
        with pytest.raises(FIDReaderError) as excinfo:
            read_fid(source)
        messages.append(str(excinfo.value))

    assert messages, "neither the directory nor the archive is in this checkout"
    assert str(expected["trace_count"]) in messages[0], (
        "the refusal does not say how many experiments it found: " + messages[0]
    )
    assert len(set(messages)) == 1, (
        "the directory and the archive give different answers for the same data:\n  "
        + "\n  ".join(messages)
    )


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


def test_a_processed_spectrum_shorter_than_its_declared_size_is_refused(tmp_path: Path) -> None:
    """Half a `1r` must not be stretched across the whole sweep.

    `_pdata_ppm_axis` spreads the sweep `procs.SW_p` declares across whatever
    number of points it is handed, and the reader handed it `real.size` -- the
    bytes actually present. A `1r` copied short therefore keeps the full sweep
    and every point moves.

    Measured on a 100.66 MHz 13C acquisition cut to half its 2097152 bytes: the
    axis endpoints were IDENTICAL to the intact read (262.7726 .. -43.83 ppm)
    while the data halved, so a carbon at 135.6074 ppm was reported at 8.4423 --
    127.17 ppm out, and the error grew along the axis (-127.17, -137.48, -143.66)
    because the stretch is linear about the axis start. The result still carried
    `referencing.established = True`.

    The evidence was already in the object: `procs.SI` is read into
    `processing_provenance['processed_size']` and sat beside `input_points`
    with nothing comparing them.
    """
    from moltrace.spectroscopy.io.fid_reader import FIDReaderError, read_processed_spectrum

    sources = sorted(Path("tests/fixtures").glob("**/pdata/*/1r"))
    if not sources:
        pytest.skip("no processed Bruker acquisition in this checkout")
    dataset = sources[0].parent.parent.parent

    intact = read_processed_spectrum(dataset)
    declared = intact.metadata["processing_provenance"].get("processed_size")
    assert declared, "the fixture does not declare a processed size, so this proves nothing"

    cut = tmp_path / "cut"
    shutil.copytree(dataset, cut)
    target = next(cut.glob("pdata/*/1r"))
    with open(target, "r+b") as fh:
        fh.truncate(target.stat().st_size // 2)

    with pytest.raises(FIDReaderError) as excinfo:
        read_processed_spectrum(cut)

    message = str(excinfo.value)
    assert "half" in message or str(int(declared)) in message, (
        "the refusal does not name the shortfall it is refusing over: " + message
    )
    # A refusal a chemist cannot act on is a stack trace with better manners.
    assert "1r" in message or "processed spectrum" in message.lower(), message


def test_an_arrayed_acquisition_is_refused_rather_than_concatenated(tmp_path: Path) -> None:
    """26 experiments laid end to end are not one spectrum.

    `_flatten_1d_fid` squeezed and then reshaped `ndim > 1` to `-1`, so a genuinely
    multi-trace acquisition was concatenated into a single pseudo-FID, apodized,
    zero-filled and transformed. Measured on the repo's own Agilent arrayed
    fixture (`procpar arraydim = 26`, arrayed on tHX, shape (26, 1500) -> 39000):
    217 multiplets reported, ALL 217 marked quantifiable, at a median spacing of
    0.2653 ppm against the 50000/1500 Hz = 0.2652 ppm the concatenation period
    predicts at 125.68 MHz. That 0.04% agreement is the arithmetic signature of
    the splice, not chemistry.

    A kinetics or variable-temperature series is the most common arrayed
    acquisition there is, so this is a shape a working chemist will hand it.
    """
    from moltrace.spectroscopy.io.fid_reader import FIDReaderError, read_fid

    dataset = Path(
        "tests/fixtures/nmrglue/varian/extracted/example_separate_1d_varian"
        "/separate_1d_varian/arrayed_data.dir"
    )
    if not dataset.exists():
        pytest.skip("the arrayed Agilent fixture is not in this checkout")

    with pytest.raises(FIDReaderError) as excinfo:
        read_fid(dataset)

    message = str(excinfo.value)
    assert "26" in message, "the refusal does not say how many experiments it found: " + message
    assert "one" in message.lower() or "single" in message.lower(), (
        "the refusal does not tell the chemist what to do instead: " + message
    )
