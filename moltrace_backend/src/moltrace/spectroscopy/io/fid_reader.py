from __future__ import annotations

import hashlib
import math
import re
import shutil
import tarfile
import tempfile
import warnings
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError  # exception type only; parsing uses defusedxml

import defusedxml.ElementTree as ET  # XXE-safe parser for user-supplied Bruker peaklist XML
import numpy as np

_ZERO_FILL_POINTS = 65_536
_DEFAULT_ACQUISITION_TIME = datetime.fromtimestamp(0, UTC)
_NUCLEUS_LB_HZ = {
    "1H": 0.5,
    "13C": 2.0,
}


class FIDReaderError(RuntimeError):
    """Raised when a raw FID dataset cannot be read or transformed."""


@dataclass(slots=True)
class NMRSpectrum:
    data: np.ndarray
    ppm_axis: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)
    nucleus: str = "unknown"
    solvent: str = ""
    field_mhz: float = 0.0
    acquisition_time: datetime = _DEFAULT_ACQUISITION_TIME
    fingerprint_hash: str = ""

    @property
    def fingerprint(self) -> str:
        return self.fingerprint_hash


def read_fid(path: Path) -> NMRSpectrum:
    """Read a Bruker or Varian/Agilent 1D FID and return a processed spectrum.

    The raw time-domain data is zero-filled to 64K points, exponentially
    apodized with nucleus-specific line broadening, Fourier transformed, and
    returned on a descending ppm axis.
    """

    source = Path(path).expanduser()
    with _prepared_dataset_root(source) as root:
        vendor, dataset_root = _detect_dataset(root)
        ng = _require_nmrglue()

        if vendor == "bruker":
            dictionary, params, fid = _read_bruker(ng, dataset_root)
        elif vendor == "varian":
            dictionary, params, fid = _read_varian(ng, dataset_root)
        else:  # pragma: no cover - defensive guard for future vendor additions.
            raise FIDReaderError(f"Unsupported FID vendor: {vendor}")

        fid_1d = _as_1d_fid(fid)
        nucleus = _extract_nucleus(params)
        solvent = _extract_solvent(params)
        field_mhz = _extract_field_mhz(params)
        sw_hz = _extract_sweep_width_hz(params)
        if not math.isfinite(sw_hz) or sw_hz <= 0:
            raise FIDReaderError(
                "The FID acquisition parameters do not include a valid sweep width."
            )

        line_broadening_hz = _line_broadening_hz(nucleus)
        windowed = _apply_exponential_apodization(fid_1d, sw_hz, line_broadening_hz)
        fft_size = (
            _ZERO_FILL_POINTS
            if windowed.size <= _ZERO_FILL_POINTS
            else _next_power_of_two(windowed.size)
        )
        complex_spectrum = np.fft.fftshift(np.fft.fft(windowed, n=fft_size))
        complex_spectrum = _phase_largest_peak_positive(complex_spectrum)
        real_spectrum = np.real(complex_spectrum).astype(np.float64, copy=False)

        ppm_axis = _ppm_axis(
            ng=ng,
            vendor=vendor,
            dictionary=dictionary,
            params=params,
            fid=fid_1d,
            size=fft_size,
            field_mhz=field_mhz,
            sw_hz=sw_hz,
        )
        ppm_axis, real_spectrum = _ensure_descending_axis(ppm_axis, real_spectrum)
        real_spectrum, frequency_orientation = _align_bruker_13c_with_peaklist(
            dataset_root=dataset_root,
            vendor=vendor,
            nucleus=nucleus,
            ppm_axis=ppm_axis,
            data=real_spectrum,
        )

        estimated_peak_count = _estimate_peak_count(
            real_spectrum,
            ppm_axis,
            nucleus=nucleus,
            solvent=solvent,
        )
        processed_peaklist_ppm = (
            _processed_peaklist_ppm(dataset_root, nucleus=nucleus)
            if vendor == "bruker"
            else []
        )
        peak_count = len(processed_peaklist_ppm) if processed_peaklist_ppm else estimated_peak_count
        acquisition_time = _extract_acquisition_time(params)
        metadata = {
            "vendor": "Bruker" if vendor == "bruker" else "Varian/Agilent",
            "dataset_root": str(dataset_root),
            "source_path": str(source),
            "zero_fill_points": fft_size,
            "input_points": int(fid_1d.size),
            "line_broadening_hz": line_broadening_hz,
            "apodization": "exponential",
            "sweep_width_hz": sw_hz,
            "peak_count": peak_count,
            "estimated_peak_count": estimated_peak_count,
            "processed_peaklist_peak_count": len(processed_peaklist_ppm),
            "frequency_orientation": frequency_orientation,
            "acquisition_params": _json_safe(params),
        }
        fingerprint_hash = _fingerprint(
            data=real_spectrum,
            ppm_axis=ppm_axis,
            metadata={
                "vendor": metadata["vendor"],
                "nucleus": nucleus,
                "solvent": solvent,
                "field_mhz": field_mhz,
                "zero_fill_points": fft_size,
                "line_broadening_hz": line_broadening_hz,
            },
        )
        metadata["fingerprint_hash"] = fingerprint_hash

        return NMRSpectrum(
            data=real_spectrum,
            ppm_axis=ppm_axis,
            metadata=metadata,
            nucleus=nucleus,
            solvent=solvent,
            field_mhz=field_mhz,
            acquisition_time=acquisition_time,
            fingerprint_hash=fingerprint_hash,
        )


# --------------------------------------------------------------------------- #
# Processed-spectrum ingest (Bruker pdata / JCAMP-DX)
# --------------------------------------------------------------------------- #
#: Bruker ``procs.WDW`` window-function codes (Bruker TopSpin processing reference).
_BRUKER_WDW = {
    0: "none",
    1: "exponential",
    2: "gaussian",
    3: "sine",
    4: "sine-squared",
    5: "trapezoid",
    6: "user",
    7: "sinc",
    8: "sinc-squared",
    9: "traficante",
    10: "traficante-shifted",
}
#: Bruker ``procs.BC_mod`` baseline-correction codes.
_BRUKER_BC = {0: "none", 1: "single-point", 2: "polynomial", 3: "sine", 4: "quadratic"}

_JCAMP_SUFFIXES = {".jdx", ".dx", ".jcamp", ".jcm"}


def read_processed_spectrum(path: Path) -> NMRSpectrum:
    """Read an already-processed 1D spectrum: Bruker ``pdata/N`` or JCAMP-DX.

    The counterpart to :func:`read_fid`, and deliberately *not* the same thing.
    ``read_fid`` takes time-domain data and applies MolTrace's own apodization,
    Fourier transform and phasing. This function takes data that a vendor or
    operator **has already processed** — apodized, phased, baseline-corrected and
    referenced — and loads it without re-processing it.

    That difference is recorded, not glossed. The returned spectrum carries:

    * ``metadata['domain'] = 'frequency'`` and ``metadata['processed_by'] =
      'vendor'``, so nothing downstream can mistake someone else's processing for
      ours;
    * ``metadata['processing_provenance']`` — the window function, line
      broadening, phase corrections and baseline mode the file says were applied;
    * ``metadata['referencing']`` — the basis on which the ppm axis was
      established, **read from the file**. A wrong reference moves every peak, so
      it is never assumed; when it cannot be established that is stated
      (``established: False``) rather than defaulted to zero.

    A quantitation claim over a spectrum processed by an unknown operator sits in
    a different evidentiary class from one over a FID we processed ourselves, and
    a reviewer needs to be able to see which they are looking at.

    Raises ``FIDReaderError``, naming the cause, when no processed data is found.
    """

    source = Path(path).expanduser()
    if not source.exists():
        raise FIDReaderError(f"Processed-spectrum path does not exist: {source}")

    if source.is_file() and "".join(source.suffixes).lower().endswith(
        tuple(_JCAMP_SUFFIXES)
    ):
        return _read_jcampdx_spectrum(source)

    with _prepared_dataset_root(source) as root:
        pdata_dir = _locate_pdata(root)
        if pdata_dir is None:
            if _has_marker(root, "fid") or _has_marker(root, "acqus"):
                raise FIDReaderError(
                    f"{root} holds raw time-domain data (a FID), not a processed "
                    "spectrum. Use read_fid() for that, which applies MolTrace's own "
                    "apodization and Fourier transform."
                )
            raise FIDReaderError(
                f"No processed spectrum found under {root}: expected a Bruker "
                "'pdata/N/1r' real-part file, or a JCAMP-DX (.jdx/.dx) file."
            )
        return _read_bruker_pdata_spectrum(pdata_dir, source)


def _locate_pdata(root: Path) -> Path | None:
    """The processing directory holding ``1r``, whether root *is* it or contains it."""

    if (root / "1r").is_file():
        return root
    candidates = sorted(p.parent for p in root.rglob("pdata/*/1r") if p.is_file())
    return candidates[0] if candidates else None


def _read_bruker_pdata_spectrum(pdata_dir: Path, source: Path) -> NMRSpectrum:
    ng = _require_nmrglue()
    try:
        dictionary, data = ng.bruker.read_pdata(str(pdata_dir))
    except Exception as exc:
        raise FIDReaderError(
            f"nmrglue could not read the Bruker processed data at {pdata_dir}: {exc}"
        ) from exc

    real = np.asarray(data, dtype=np.float64).squeeze()
    if real.ndim != 1 or real.size < 2:
        raise FIDReaderError(
            f"{pdata_dir} does not hold a 1D processed spectrum "
            f"(got shape {np.asarray(data).shape}); 2D processed data is not supported here."
        )

    procs = dict(dictionary.get("procs", {}) or {})
    acqus = dict(dictionary.get("acqus", {}) or {})
    params = {**acqus, **{f"procs.{k}": v for k, v in procs.items()}}

    ppm_axis, referencing = _pdata_ppm_axis(procs, real.size)
    ppm_axis, real = _ensure_descending_axis(ppm_axis, real)

    nucleus = _extract_nucleus(params)
    solvent = _extract_solvent(params)
    field_mhz = _pdata_field_mhz(procs, acqus)

    metadata: dict[str, Any] = {
        "vendor": "Bruker",
        "domain": "frequency",
        "processed_by": "vendor",
        "moltrace_processing": "none",
        "dataset_root": str(pdata_dir),
        "source_path": str(source),
        "input_points": int(real.size),
        "processing_provenance": _bruker_processing_provenance(procs),
        "referencing": referencing,
        "estimated_peak_count": _estimate_peak_count(
            real, ppm_axis, nucleus=nucleus, solvent=solvent
        ),
        "acquisition_params": _json_safe(params),
    }
    metadata["peak_count"] = metadata["estimated_peak_count"]
    return _finalize_processed_spectrum(
        data=real,
        ppm_axis=ppm_axis,
        metadata=metadata,
        nucleus=nucleus,
        solvent=solvent,
        field_mhz=field_mhz,
        acquisition_time=_extract_acquisition_time(params),
    )


def _pdata_ppm_axis(procs: dict[str, Any], size: int) -> tuple[np.ndarray, dict[str, Any]]:
    """Derive the ppm axis from ``procs``, reporting how it was established.

    Bruker defines ``OFFSET`` as the ppm of the **first (leftmost, highest-ppm)**
    point and ``SW_p`` as the sweep width in Hz, so the axis descends from OFFSET
    by ``SW_p / SF`` ppm. Both values are read; neither is invented.
    """

    offset = _float_param(procs, "OFFSET")
    sf = _float_param(procs, "SF")
    sw_hz = _float_param(procs, "SW_p")

    if math.isfinite(offset) and math.isfinite(sf) and sf > 0 and math.isfinite(sw_hz):
        width_ppm = sw_hz / sf
        axis = offset - np.arange(size, dtype=np.float64) * (width_ppm / size)
        return axis, {
            "established": True,
            "basis": "Bruker procs SF/OFFSET",
            "offset_ppm": offset,
            "spectrometer_frequency_mhz": sf,
            "sweep_width_hz": sw_hz,
        }

    # No fabricated reference: an index axis is obviously not ppm, and the caller
    # is told so explicitly rather than being handed a plausible-looking scale.
    missing = [
        name
        for name, value in (("OFFSET", offset), ("SF", sf), ("SW_p", sw_hz))
        if not math.isfinite(value)
    ]
    return np.arange(size, dtype=np.float64)[::-1], {
        "established": False,
        "basis": "unavailable",
        "reason": (
            "Bruker procs is missing "
            + ", ".join(missing)
            + "; the chemical-shift axis could not be established and the returned "
            "axis is point index, not ppm."
        ),
    }


def _bruker_processing_provenance(procs: dict[str, Any]) -> dict[str, Any]:
    """What the vendor already applied — preserved so it is not attributed to us."""

    wdw = _float_param(procs, "WDW")
    bc = _float_param(procs, "BC_mod")
    provenance: dict[str, Any] = {
        "source": "Bruker procs",
        "window_function": _BRUKER_WDW.get(int(wdw), f"code {int(wdw)}")
        if math.isfinite(wdw)
        else "unknown",
        "line_broadening_hz": _float_or_none(procs, "LB"),
        "phase_zero_order": _float_or_none(procs, "PHC0"),
        "phase_first_order": _float_or_none(procs, "PHC1"),
        "baseline_correction": _BRUKER_BC.get(int(bc), f"code {int(bc)}")
        if math.isfinite(bc)
        else "unknown",
        "processed_size": _float_or_none(procs, "SI"),
        "intensity_scale_exponent": _float_or_none(procs, "NC_proc"),
    }
    return provenance


def _pdata_field_mhz(procs: dict[str, Any], acqus: dict[str, Any]) -> float:
    for source, key in ((acqus, "BF1"), (procs, "SF"), (acqus, "SFO1")):
        value = _float_param(source, key)
        if math.isfinite(value) and value > 0:
            return value
    return 0.0


def _read_jcampdx_spectrum(source: Path) -> NMRSpectrum:
    ng = _require_nmrglue()
    try:
        dictionary, data = ng.jcampdx.read(str(source))
    except Exception as exc:
        raise FIDReaderError(f"nmrglue could not read the JCAMP-DX file {source}: {exc}") from exc

    array = np.asarray(data[0] if isinstance(data, (list, tuple)) else data, dtype=np.float64)
    array = array.squeeze()
    if array.ndim != 1 or array.size < 2:
        raise FIDReaderError(f"{source} does not hold a 1D JCAMP-DX spectrum.")

    first_x = _jcamp_float(dictionary, "FIRSTX")
    last_x = _jcamp_float(dictionary, "LASTX")
    units = (_jcamp_str(dictionary, "XUNITS") or "").strip().upper()
    observe_mhz = _jcamp_float(dictionary, ".OBSERVEFREQUENCY")
    nucleus = _normalize_nucleus(_jcamp_str(dictionary, ".OBSERVENUCLEUS")) or "unknown"
    solvent = _clean_solvent(_jcamp_str(dictionary, ".SOLVENTNAME"))

    if not (math.isfinite(first_x) and math.isfinite(last_x)):
        raise FIDReaderError(
            f"{source} does not declare FIRSTX/LASTX, so its chemical-shift axis "
            "cannot be established."
        )

    if units.startswith("HZ"):
        if not (math.isfinite(observe_mhz) and observe_mhz > 0):
            # Hz without a carrier frequency cannot become ppm. Refusing beats
            # returning a Hz axis labelled ppm, which would put every 13C peak at
            # ~190x its true shift with no visible error.
            raise FIDReaderError(
                f"{source} gives its axis in Hz but declares no .OBSERVEFREQUENCY, "
                "so it cannot be converted to ppm."
            )
        axis = np.linspace(first_x / observe_mhz, last_x / observe_mhz, array.size)
        basis = "JCAMP-DX FIRSTX/LASTX (Hz) / .OBSERVEFREQUENCY"
    elif units.startswith("PPM"):
        axis = np.linspace(first_x, last_x, array.size)
        basis = "JCAMP-DX FIRSTX/LASTX (ppm)"
    else:
        raise FIDReaderError(
            f"{source} declares XUNITS={units!r}, which is neither Hz nor PPM; "
            "the chemical-shift axis cannot be established."
        )

    axis, array = _ensure_descending_axis(axis, array)
    metadata: dict[str, Any] = {
        "vendor": "JCAMP-DX",
        "domain": "frequency",
        "processed_by": "vendor",
        "moltrace_processing": "none",
        "dataset_root": str(source),
        "source_path": str(source),
        "input_points": int(array.size),
        # JCAMP-DX carries no standard record of the processing that produced it,
        # which is itself worth stating rather than leaving as an empty dict.
        "processing_provenance": {
            "source": "JCAMP-DX",
            "note": (
                "JCAMP-DX does not record the processing applied before export; "
                "apodization, phasing and baseline correction are unknown."
            ),
        },
        "referencing": {
            "established": True,
            "basis": basis,
            "offset_ppm": float(axis[0]),
            "spectrometer_frequency_mhz": observe_mhz if math.isfinite(observe_mhz) else None,
        },
        "estimated_peak_count": _estimate_peak_count(
            array, axis, nucleus=nucleus, solvent=solvent
        ),
        "acquisition_params": _json_safe(
            {k: v for k, v in dictionary.items() if not isinstance(v, (list, tuple)) or len(v) < 8}
        ),
    }
    metadata["peak_count"] = metadata["estimated_peak_count"]
    return _finalize_processed_spectrum(
        data=array,
        ppm_axis=axis,
        metadata=metadata,
        nucleus=nucleus,
        solvent=solvent,
        field_mhz=observe_mhz if math.isfinite(observe_mhz) else 0.0,
        acquisition_time=_DEFAULT_ACQUISITION_TIME,
    )


def _finalize_processed_spectrum(
    *,
    data: np.ndarray,
    ppm_axis: np.ndarray,
    metadata: dict[str, Any],
    nucleus: str,
    solvent: str,
    field_mhz: float,
    acquisition_time: datetime,
) -> NMRSpectrum:
    fingerprint_hash = _fingerprint(
        data=data,
        ppm_axis=ppm_axis,
        metadata={
            "vendor": metadata["vendor"],
            "domain": metadata["domain"],
            "nucleus": nucleus,
            "solvent": solvent,
            "field_mhz": field_mhz,
        },
    )
    metadata["fingerprint_hash"] = fingerprint_hash
    return NMRSpectrum(
        data=data,
        ppm_axis=ppm_axis,
        metadata=metadata,
        nucleus=nucleus,
        solvent=solvent,
        field_mhz=field_mhz,
        acquisition_time=acquisition_time,
        fingerprint_hash=fingerprint_hash,
    )


def _float_param(params: dict[str, Any], key: str) -> float:
    try:
        return float(_unwrap_param_value(params.get(key)))
    except (TypeError, ValueError):
        return float("nan")


def _float_or_none(params: dict[str, Any], key: str) -> float | None:
    value = _float_param(params, key)
    return value if math.isfinite(value) else None


def _jcamp_str(dictionary: dict[str, Any], key: str) -> str:
    value = dictionary.get(key)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip().strip("<>")


def _jcamp_float(dictionary: dict[str, Any], key: str) -> float:
    try:
        return float(_jcamp_str(dictionary, key))
    except (TypeError, ValueError):
        return float("nan")


@contextmanager
def _prepared_dataset_root(path: Path) -> Iterator[Path]:
    if not path.exists():
        raise FIDReaderError(f"FID path does not exist: {path}")
    if path.is_dir():
        yield path
        return
    if path.is_file() and path.name.lower() == "fid":
        yield path.parent
        return
    suffixes = "".join(path.suffixes).lower()
    if path.is_file() and suffixes.endswith(".zip"):
        with tempfile.TemporaryDirectory(prefix="moltrace-fid-") as tmp:
            root = Path(tmp)
            with zipfile.ZipFile(path) as archive:
                _safe_extract_zip(archive, root)
            yield root
        return
    if path.is_file() and (
        tarfile.is_tarfile(path) or suffixes.endswith((".tar.gz", ".tgz", ".tar"))
    ):
        with tempfile.TemporaryDirectory(prefix="moltrace-fid-") as tmp:
            root = Path(tmp)
            with tarfile.open(path) as archive:
                _safe_extract_tar(archive, root)
            yield root
        return
    raise FIDReaderError(
        "Expected a Bruker/Varian dataset directory, fid file, zip, or tar archive."
    )


def _safe_extract_zip(archive: zipfile.ZipFile, root: Path) -> None:
    for member in archive.infolist():
        target = (root / member.filename).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            raise FIDReaderError("Archive contains a path outside the extraction directory.")
        archive.extract(member, root)


def _safe_extract_tar(archive: tarfile.TarFile, root: Path) -> None:
    for member in archive.getmembers():
        target = (root / member.name).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            raise FIDReaderError("Archive contains a path outside the extraction directory.")
    archive.extractall(root)


# Vendor marker files nmrglue opens by exact (lowercase) name. Some exports —
# notably Varian/Agilent "nmroned" datasets — store them uppercase (FID /
# PROCPAR). That reads fine on a case-INsensitive filesystem (macOS dev) but is
# invisible on a case-SENsitive one (Linux CI and the Render production host),
# so both dataset detection and the nmrglue read have to be case-insensitive.
_VENDOR_MARKER_FILES = frozenset(
    {
        "fid",
        "ser",
        "acqus",
        "acqu",
        "acqu2",
        "acqu2s",
        "acqu3",
        "acqu3s",
        "procpar",
        "procs",
        "proc",
        "proc2",
        "proc2s",
        "proc3",
        "proc3s",
    }
)


def _has_marker(directory: Path, marker: str) -> bool:
    """Case-insensitive check that *directory* contains a file named *marker*."""
    try:
        return any(c.is_file() and c.name.lower() == marker for c in directory.iterdir())
    except OSError:
        return False


def _ensure_lowercase_marker_aliases(dataset_root: Path) -> None:
    """Give nmrglue the lowercase marker filenames it opens by exact name.

    On a case-sensitive filesystem an uppercase ``FID``/``PROCPAR`` export is
    otherwise unreadable. For any vendor marker present only in non-lowercase
    form, create a lowercase alias (symlink, falling back to a copy). No-op on a
    case-insensitive filesystem, where the lowercase name already resolves to the
    same file, so the macOS-dev path is unchanged.
    """
    try:
        entries = [c for c in dataset_root.iterdir() if c.is_file()]
    except OSError:
        return
    for f in entries:
        lower = f.name.lower()
        if f.name == lower or lower not in _VENDOR_MARKER_FILES:
            continue
        alias = dataset_root / lower
        if alias.exists():  # case-insensitive FS already resolves it
            continue
        try:
            alias.symlink_to(f.name)
        except OSError:
            try:
                shutil.copyfile(f, alias)
            except OSError:
                pass


def _detect_dataset(root: Path) -> tuple[str, Path]:
    root = root.resolve()
    # Case-insensitive `fid`/`FID` match + case-insensitive sibling check, so an
    # uppercase Varian/Agilent dataset is found on a case-sensitive host.
    fid_files = [p for p in root.rglob("[Ff][Ii][Dd]") if p.is_file()]
    bruker = [fid.parent for fid in fid_files if _has_marker(fid.parent, "acqus")]
    varian = [fid.parent for fid in fid_files if _has_marker(fid.parent, "procpar")]
    if bruker:
        bruker.sort(key=lambda p: (len(p.relative_to(root).parts), str(p).lower()))
        return "bruker", bruker[0]
    if varian:
        varian.sort(
            key=lambda p: (
                0 if p.name.lower().endswith(".fid") else 1,
                len(p.relative_to(root).parts),
                str(p).lower(),
            )
        )
        return "varian", varian[0]
    raise FIDReaderError("No Bruker or Varian/Agilent FID dataset was found.")


def _require_nmrglue() -> Any:
    try:
        import nmrglue as ng  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - exercised only without optional extra.
        raise FIDReaderError(
            "Raw FID reading requires nmrglue. "
            "Install it with: cd moltrace_backend && uv sync --extra fid"
        ) from exc
    return ng


def _read_bruker(ng: Any, dataset_root: Path) -> tuple[dict[str, Any], dict[str, Any], np.ndarray]:
    _ensure_lowercase_marker_aliases(dataset_root)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dictionary, data = ng.bruker.read(str(dataset_root))
            if _should_remove_bruker_digital_filter(dictionary):
                try:
                    data = ng.bruker.remove_digital_filter(dictionary, data)
                except Exception:
                    pass
    except Exception as exc:
        raise FIDReaderError("nmrglue could not read the Bruker FID dataset.") from exc
    params = dict(dictionary.get("acqus", {}))
    if isinstance(dictionary.get("procs"), dict):
        params.update({f"procs.{key}": value for key, value in dictionary["procs"].items()})
    return dictionary, params, np.asarray(data)


def _should_remove_bruker_digital_filter(dictionary: dict[str, Any]) -> bool:
    acqus = dictionary.get("acqus", {})
    if not isinstance(acqus, dict):
        return False
    group_delay = _float_param(acqus, "GRPDLY")
    if group_delay is not None:
        return group_delay > 0
    return _float_param(acqus, "DECIM") is not None and _float_param(acqus, "DSPFVS") is not None


def _read_varian(ng: Any, dataset_root: Path) -> tuple[dict[str, Any], dict[str, Any], np.ndarray]:
    _ensure_lowercase_marker_aliases(dataset_root)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dictionary, data = ng.varian.read(str(dataset_root))
    except Exception as exc:
        raise FIDReaderError("nmrglue could not read the Varian/Agilent FID dataset.") from exc
    params = dict(dictionary.get("procpar", {}))
    return dictionary, params, np.asarray(data)


def _multidimensional_fid_message(shape: tuple[int, ...]) -> str:
    """Explain, in a chemist's vocabulary, why multi-record data is refused.

    Kept deliberately identical in wording to the copy in ``nmrcheck.fid``; the
    two readers are separate but a user can reach either, and they must not
    disagree about what happened. ``tests/test_fid_dimensionality_refusal.py``
    holds both to the same contract.
    """
    records = int(np.prod(shape[:-1]))
    points = int(shape[-1])
    return (
        f"This dataset holds {records} separate records of {points} points each, so it is a "
        "2D or arrayed experiment rather than a single 1D acquisition. Joining the records "
        "end to end would produce a spectrum that looks ordinary but describes nothing that "
        "was measured, so it is refused instead. Process the records as individual 1D "
        "acquisitions, or use an analysis that handles 2D data."
    )


def _as_1d_fid(data: np.ndarray) -> np.ndarray:
    """Return the FID as a 1D complex array, refusing a real second dimension.

    ``squeeze`` still removes genuine length-1 axes, so a ``(N, 1)`` export reads
    normally. A real second dimension is *refused* rather than concatenated: a 2D
    or arrayed acquisition read as one long FID transforms into a spectrum with
    peaks and a plausible ppm axis and no outward sign of being wrong, which is
    worse than a rejection. See ``tests/test_nmr2d_ingestion_boundary.py`` for the
    same invariant stated at the Bruker dataset-detection boundary.
    """
    fid = np.asarray(data).squeeze()
    if fid.ndim == 0:
        raise FIDReaderError("The raw FID did not contain a usable 1D array.")
    if fid.ndim > 1:
        raise FIDReaderError(_multidimensional_fid_message(fid.shape))
    if fid.size < 8:
        raise FIDReaderError("The raw FID is too short to process.")
    return fid.astype(np.complex128, copy=False)


def _apply_exponential_apodization(
    fid: np.ndarray, sw_hz: float, line_broadening_hz: float
) -> np.ndarray:
    if line_broadening_hz <= 0:
        return np.asarray(fid, dtype=np.complex128)
    dwell_time = 1.0 / float(sw_hz)
    time_axis = np.arange(fid.size, dtype=np.float64) * dwell_time
    window = np.exp(-math.pi * float(line_broadening_hz) * time_axis)
    return np.asarray(fid, dtype=np.complex128) * window


def _phase_largest_peak_positive(spectrum: np.ndarray) -> np.ndarray:
    if spectrum.size == 0:
        return spectrum
    peak_index = int(np.argmax(np.abs(spectrum)))
    phase = -float(np.angle(spectrum[peak_index]))
    phased = spectrum * np.exp(1j * phase)
    real = np.real(phased)
    if abs(float(np.nanmin(real))) > float(np.nanmax(real)):
        phased = -phased
    return phased


def _ppm_axis(
    *,
    ng: Any,
    vendor: str,
    dictionary: dict[str, Any],
    params: dict[str, Any],
    fid: np.ndarray,
    size: int,
    field_mhz: float,
    sw_hz: float,
) -> np.ndarray:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if vendor == "bruker":
                udic = ng.bruker.guess_udic(dictionary, fid)
            else:
                udic = ng.varian.guess_udic(dictionary, fid)
        udic[0]["size"] = int(size)
        uc = ng.fileiobase.uc_from_udic(udic)
        axis = np.asarray(uc.ppm_scale(), dtype=np.float64)
        expected_span = sw_hz / field_mhz if field_mhz > 0 else None
        observed_span = float(np.nanmax(axis) - np.nanmin(axis)) if axis.size else 0.0
        span_is_plausible = (
            expected_span is None
            or expected_span <= 0
            or abs(observed_span - expected_span) <= max(0.05, expected_span * 0.2)
        )
        if axis.size == size and np.all(np.isfinite(axis)) and span_is_plausible:
            return axis
    except Exception:
        pass

    field = field_mhz if math.isfinite(field_mhz) and field_mhz > 0 else 400.0
    sw_ppm = sw_hz / field
    center_ppm = _extract_center_ppm(params, field)
    return np.linspace(
        center_ppm + sw_ppm / 2.0,
        center_ppm - sw_ppm / 2.0,
        int(size),
        endpoint=False,
        dtype=np.float64,
    )


def _ensure_descending_axis(axis: np.ndarray, data: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    axis = np.asarray(axis, dtype=np.float64)
    data = np.asarray(data, dtype=np.float64)
    if axis.size != data.size:
        raise FIDReaderError("The generated ppm axis does not match the spectrum size.")
    if axis.size > 1 and axis[0] < axis[-1]:
        return axis[::-1].copy(), data[::-1].copy()
    return axis.copy(), data.copy()


def _align_bruker_13c_with_peaklist(
    *,
    dataset_root: Path,
    vendor: str,
    nucleus: str,
    ppm_axis: np.ndarray,
    data: np.ndarray,
) -> tuple[np.ndarray, str]:
    """Use NMRShiftDB2's processed peaklist as a Bruker 13C orientation guard.

    Bruker archives from public repositories sometimes retain raw FID frequency
    ordering that is mirrored relative to the processed spectrum.  We only apply
    this guard to 13C datasets with an explicit processed peaklist, and only when
    the reversed trace scores materially better at the curated peak positions.
    """

    if vendor != "bruker" or nucleus != "13C":
        return data, "native"
    references = _processed_peaklist_ppm(dataset_root, nucleus=nucleus)
    if not references:
        return data, "native"
    native_score = _orientation_reference_score(data, ppm_axis, references)
    reversed_data = np.asarray(data, dtype=np.float64)[::-1].copy()
    reversed_score = _orientation_reference_score(reversed_data, ppm_axis, references)
    if reversed_score > max(native_score * 1.25, native_score + 1e-12):
        return reversed_data, "reversed_to_processed_peaklist"
    return data, "native"


def _processed_peaklist_ppm(dataset_root: Path, *, nucleus: str) -> list[float]:
    peaklist = dataset_root / "pdata" / "1" / "peaklist.xml"
    if not peaklist.exists():
        return []
    try:
        root = ET.parse(peaklist).getroot()
    except ParseError:
        return []
    references: list[float] = []
    if nucleus == "13C":
        for peak in root.findall(".//Peak1D"):
            try:
                ppm = float(peak.attrib["F1"])
            except (KeyError, ValueError):
                continue
            if not _is_common_13c_solvent_ppm(ppm):
                references.append(ppm)
        return _cluster_ppm(references, tolerance=0.18)

    for block in root.findall(".//PeakList1D"):
        block_peaks: list[tuple[float, float]] = []
        for peak in block.findall("Peak1D"):
            try:
                block_peaks.append(
                (float(peak.attrib["F1"]), float(peak.attrib.get("intensity", "0")))
            )
            except (KeyError, ValueError):
                continue
        if block_peaks:
            references.append(max(block_peaks, key=lambda item: item[1])[0])
    return _cluster_ppm(references, tolerance=0.08)


def _orientation_reference_score(
    data: np.ndarray,
    ppm_axis: np.ndarray,
    references: list[float],
    *,
    window_ppm: float = 0.08,
) -> float:
    if not references:
        return 0.0
    signal = np.asarray(data, dtype=np.float64)
    axis = np.asarray(ppm_axis, dtype=np.float64)
    centered = signal - float(np.nanmedian(signal))
    positive = np.maximum(centered, 0.0)
    score = 0.0
    for ppm in references:
        mask = np.abs(axis - ppm) <= window_ppm
        if np.any(mask):
            score += float(np.nanmax(positive[mask]))
    return score


def _line_broadening_hz(nucleus: str) -> float:
    return _NUCLEUS_LB_HZ.get(nucleus, 0.5)


def _extract_nucleus(params: dict[str, Any]) -> str:
    value = _param(params, "NUC1", "NUCLEUS", "tn", "dn", "nucleus")
    return _normalize_nucleus(value) or "unknown"


def _normalize_nucleus(value: Any) -> str:
    text = _string_param_value(value).upper().replace(" ", "")
    text = text.strip("<>{}[]()\"'")
    if not text:
        return ""
    isotope_first = re.fullmatch(r"(\d{1,3})([A-Z]{1,2})", text)
    if isotope_first:
        return f"{isotope_first.group(1)}{isotope_first.group(2).title()}"
    element_first = re.fullmatch(r"([A-Z]{1,2})(\d{1,3})", text)
    if element_first:
        return f"{element_first.group(2)}{element_first.group(1).title()}"
    return text


def _extract_solvent(params: dict[str, Any]) -> str:
    direct = _clean_solvent(_param(params, "SOLVENT", "solvent", "locksolvent"))
    processed = _solvent_from_sreglst(_param(params, "procs.SREGLST", "SREGLST"))
    if processed and (not direct or direct.upper() in {"H2O", "WATER"}):
        return processed
    return direct or processed


def _clean_solvent(value: Any) -> str:
    return _string_param_value(value).strip("<>{}[]()\"'")


def _solvent_from_sreglst(value: Any) -> str:
    text = _clean_solvent(value)
    if not text:
        return ""
    if "." in text:
        text = text.split(".")[-1]
    return text.strip("<>{}[]()\"'")


def _extract_field_mhz(params: dict[str, Any]) -> float:
    for name in ("SFO1", "BF1", "sfrq", "reffrq", "H1reffrq", "dfrq", "SF", "sf"):
        value = _float_param(params, name)
        if value is not None and math.isfinite(value) and value > 0:
            return float(value)
    return 0.0


def _extract_sweep_width_hz(params: dict[str, Any]) -> float:
    value = _float_param(params, "SW_h", "SW_hz", "sw")
    if value is not None and math.isfinite(value) and value > 0:
        return float(value)
    sw_ppm = _float_param(params, "SW")
    field = _extract_field_mhz(params)
    if sw_ppm is not None and field > 0:
        return float(sw_ppm) * field
    return float("nan")


def _extract_center_ppm(params: dict[str, Any], field_mhz: float) -> float:
    o1p = _float_param(params, "O1P")
    if o1p is not None and math.isfinite(o1p):
        return float(o1p)
    o1_hz = _float_param(params, "O1", "tof")
    if o1_hz is not None and field_mhz > 0:
        return float(o1_hz) / field_mhz
    car = _float_param(params, "car")
    if car is not None and math.isfinite(car):
        return float(car)
    return 4.7


def _extract_acquisition_time(params: dict[str, Any]) -> datetime:
    for name in ("time_complete", "time_run", "time_saved", "DATE", "date"):
        text = _string_param_value(_param(params, name))
        if not text:
            continue
        try:
            numeric = float(text)
            if numeric > 0:
                return datetime.fromtimestamp(numeric, UTC)
        except ValueError:
            pass
        for fmt in (
            "%Y%m%dT%H%M%S",
            "%Y-%m-%d %H:%M:%S",
            "%a %b %d %H:%M:%S %Y",
            "%b %d %Y",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.replace(tzinfo=UTC)
            except ValueError:
                continue
    return _DEFAULT_ACQUISITION_TIME


def _param(params: dict[str, Any], *names: str) -> Any:
    lower_lookup = {str(key).lower(): key for key in params}
    for name in names:
        if name in params:
            return params[name]
        actual = lower_lookup.get(name.lower())
        if actual is not None:
            return params[actual]
    return None


def _float_param(params: dict[str, Any], *names: str) -> float | None:
    value = _param(params, *names)
    text = _string_param_value(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _string_param_value(value: Any) -> str:
    value = _unwrap_param_value(value)
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _unwrap_param_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "values" in value and value["values"]:
            return _unwrap_param_value(value["values"][0])
        if "value" in value:
            return _unwrap_param_value(value["value"])
    if isinstance(value, (list, tuple)) and value:
        return _unwrap_param_value(value[0])
    return value


def _next_power_of_two(value: int) -> int:
    return 1 << (max(1, int(value)) - 1).bit_length()


def _estimate_peak_count(
    data: np.ndarray,
    ppm_axis: np.ndarray,
    *,
    nucleus: str | None = None,
    solvent: str | None = None,
) -> int:
    signal = np.asarray(data, dtype=np.float64)
    if signal.size < 3:
        return 0
    centered = signal - float(np.nanmedian(signal))
    positive = np.maximum(centered, 0.0)
    positive = _mask_solvent_regions(positive, ppm_axis, nucleus=nucleus, solvent=solvent)
    noise = _mad(positive[positive <= np.nanpercentile(positive, 70)])
    if not math.isfinite(noise) or noise <= 0:
        noise = _mad(positive)
    maximum = float(np.nanmax(positive)) if positive.size else 0.0
    if maximum <= 0:
        return 0
    threshold = max(noise * 10.0, maximum * 0.15)
    candidates = np.flatnonzero(
        (positive[1:-1] > positive[:-2])
        & (positive[1:-1] >= positive[2:])
        & (positive[1:-1] >= threshold)
    ) + 1
    if candidates.size == 0:
        return 0
    step = float(np.nanmedian(np.abs(np.diff(np.asarray(ppm_axis, dtype=np.float64)))))
    min_distance = max(1, int(round(0.06 / step))) if step > 0 else 1
    selected: list[int] = []
    for idx in sorted(candidates.tolist(), key=lambda item: float(positive[item]), reverse=True):
        if all(abs(idx - existing) >= min_distance for existing in selected):
            selected.append(idx)
    return len(selected)


def _mask_solvent_regions(
    positive: np.ndarray,
    ppm_axis: np.ndarray,
    *,
    nucleus: str | None,
    solvent: str | None,
) -> np.ndarray:
    masked = np.asarray(positive, dtype=np.float64).copy()
    axis = np.asarray(ppm_axis, dtype=np.float64)
    for ppm_min, ppm_max in _solvent_blind_regions(nucleus=nucleus, solvent=solvent):
        low, high = sorted((ppm_min, ppm_max))
        masked[(axis >= low) & (axis <= high)] = 0.0
    return masked


def _solvent_blind_regions(
    *,
    nucleus: str | None,
    solvent: str | None,
) -> tuple[tuple[float, float], ...]:
    if nucleus != "13C":
        return ()
    solvent_key = (solvent or "").upper().replace("-", "").replace("_", "")
    if "CDCL3" in solvent_key or "CHLOROFORM" in solvent_key:
        return ((76.4, 77.8),)
    if "DMSO" in solvent_key:
        return ((38.7, 40.2),)
    if "CD3OD" in solvent_key or "METHANOL" in solvent_key or "MEOD" in solvent_key:
        return ((48.2, 50.3),)
    return ()


def _is_common_13c_solvent_ppm(ppm: float) -> bool:
    return (
        76.4 <= ppm <= 77.8
        or 38.7 <= ppm <= 40.2
        or 48.2 <= ppm <= 50.3
    )


def _cluster_ppm(peaks: list[float], *, tolerance: float) -> list[float]:
    if not peaks:
        return []
    ordered = sorted(float(peak) for peak in peaks)
    clusters: list[list[float]] = []
    for peak in ordered:
        if not clusters or abs(peak - clusters[-1][-1]) > tolerance:
            clusters.append([peak])
        else:
            clusters[-1].append(peak)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _mad(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return 0.0
    median = float(np.nanmedian(arr))
    return float(1.4826 * np.nanmedian(np.abs(arr - median)))


def _fingerprint(*, data: np.ndarray, ppm_axis: np.ndarray, metadata: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(b"moltrace.fid_reader.v1")
    for key in sorted(metadata):
        digest.update(str(key).encode("utf-8"))
        digest.update(str(metadata[key]).encode("utf-8"))
    digest.update(np.round(np.asarray(ppm_axis, dtype="<f8"), 8).tobytes())
    digest.update(np.round(np.asarray(data, dtype="<f8"), 8).tobytes())
    return digest.hexdigest()


def _json_safe(params: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in params.items():
        unwrapped = _unwrap_param_value(value)
        if isinstance(unwrapped, (str, int, float, bool)) or unwrapped is None:
            safe[str(key)] = unwrapped
        else:
            safe[str(key)] = str(unwrapped)
    return safe
