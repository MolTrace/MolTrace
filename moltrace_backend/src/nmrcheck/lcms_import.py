from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
import struct
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterable

from .models import (
    LCMSChromatogramPoint,
    LCMSExtractedPrecursor,
    LCMSImportBridgeRequest,
    LCMSImportBridgeResult,
    LCMSImportedSpectrum,
    LCMSPeak,
    LCMSScanSummary,
)

FLOAT_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
SECTION_RE = re.compile(r"(?:scan|spectrum)\s*[=:]\s*([^\s,;]+)|ms\s*([12])|mslevel\s*[=:]\s*([12])|precursor(?:_mz| m/z|mz)?\s*[=:]\s*([-+]?\d+(?:\.\d+)?)|rt(?:_min| min|minute|s|sec|second)?\s*[=:]\s*([-+]?\d+(?:\.\d+)?)", re.I)


class LCMSImportError(ValueError):
    pass


@dataclass
class _RawScan:
    scan_id: str
    ms_level: int
    retention_time_min: float | None = None
    precursor_mz: float | None = None
    polarity: str = "unknown"
    peaks: list[tuple[float, float]] = field(default_factory=list)
    total_ion_current: float | None = None
    base_peak_mz: float | None = None
    base_peak_intensity: float | None = None
    source: str = "processed"
    warnings: list[str] = field(default_factory=list)


def _tag_name(elem: ET.Element) -> str:
    return elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag


def _iter_named(elem: ET.Element, name: str) -> Iterable[ET.Element]:
    for child in elem.iter():
        if _tag_name(child) == name:
            yield child


def _cv_params(elem: ET.Element) -> list[dict[str, str]]:
    params: list[dict[str, str]] = []
    for cv in _iter_named(elem, "cvParam"):
        params.append({str(k): str(v) for k, v in cv.attrib.items()})
    return params


def _find_cv_value(elem: ET.Element, *needles: str) -> str | None:
    needles_lower = [needle.lower() for needle in needles]
    for param in _cv_params(elem):
        name = param.get("name", "").lower()
        accession = param.get("accession", "").lower()
        if any(needle in name or needle in accession for needle in needles_lower):
            return param.get("value")
    return None


def _find_cv_param(elem: ET.Element, *needles: str) -> dict[str, str] | None:
    needles_lower = [needle.lower() for needle in needles]
    for param in _cv_params(elem):
        name = param.get("name", "").lower()
        accession = param.get("accession", "").lower()
        if any(needle in name or needle in accession for needle in needles_lower):
            return param
    return None


def _to_float(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        numbers = FLOAT_RE.findall(str(value))
        return float(numbers[0]) if numbers else None


def _to_int(value: str | float | int | None) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None


def _parse_retention_time(value: str | None, unit: str | None = None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    # ISO-ish mzXML duration: PT75.5S, PT1.25M, PT0.02H
    match = re.fullmatch(r"P?T?([-+]?\d+(?:\.\d+)?)([HMS])", text, flags=re.I)
    if match:
        amount = float(match.group(1))
        suffix = match.group(2).upper()
        if suffix == "H":
            return amount * 60.0
        if suffix == "S":
            return amount / 60.0
        return amount
    number = _to_float(text)
    if number is None:
        return None
    unit_l = (unit or "").lower()
    if "second" in unit_l or unit_l in {"s", "sec"}:
        return number / 60.0
    if "hour" in unit_l or unit_l in {"h", "hr"}:
        return number * 60.0
    return number


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _detect_format(filename: str | None, source_text: str, requested: str | None) -> tuple[str, list[str]]:
    warnings: list[str] = []
    requested_norm = (requested or "auto").strip()
    if requested_norm != "auto":
        return requested_norm, warnings
    suffix = (filename or "").lower()
    head = source_text[:2000].lower()
    if suffix.endswith(".mzml") or "<mzml" in head:
        return "mzML", warnings
    if suffix.endswith(".mzxml") or "<mzxml" in head:
        return "mzXML", warnings
    if suffix.endswith((".raw", ".d", ".wiff", ".cdf", ".masslynx")):
        warnings.append("The filename looks like a proprietary or vendor-specific MS container. Convert it to mzML/mzXML or export a processed peak table before using this bridge.")
        return "unsupported_vendor", warnings
    if suffix.endswith((".csv", ".tsv", ".txt")) or "m/z" in head or "mz," in head or "ms_level" in head:
        return "processed_peak_table", warnings
    if "<spectrum" in head and "ms level" in head:
        return "mzML", warnings
    warnings.append("Could not confidently detect LC-MS format; attempting processed peak-table parsing.")
    return "processed_peak_table", warnings


def _split_record(line: str) -> list[str]:
    if "," in line:
        return [part.strip() for part in next(csv.reader([line]))]
    if "\t" in line:
        return [part.strip() for part in line.split("\t")]
    return [part.strip() for part in re.split(r"\s+", line.strip()) if part.strip()]


def _norm_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _header_indices(parts: list[str]) -> dict[str, int]:
    aliases = {
        "mz": {"mz", "moverz", "mass", "masscharge", "masstocharge", "m/z"},
        "intensity": {"intensity", "int", "abundance", "relativeabundance", "height", "area"},
        "rt": {"rt", "rtmin", "retentiontime", "retentiontimemin", "time", "timemin"},
        "ms_level": {"mslevel", "ms", "level", "msorder"},
        "precursor_mz": {"precursormz", "precursor", "parentmz", "parention", "selectedionmz"},
        "scan_id": {"scan", "scanid", "scanindex", "spectrum", "spectrumid", "id"},
        "polarity": {"polarity", "ionmode", "mode"},
    }
    indices: dict[str, int] = {}
    for idx, part in enumerate(parts):
        norm = _norm_header(part)
        for key, vals in aliases.items():
            if norm in vals:
                indices[key] = idx
    return indices


def _looks_like_header(parts: list[str]) -> bool:
    joined = " ".join(parts).lower()
    return any(token in joined for token in ["mz", "m/z", "int", "abundance", "ms_level", "precursor", "rt"] ) and any(re.search(r"[A-Za-z]", part) for part in parts)


def _section_context(line: str, current_index: int) -> dict[str, object]:
    context: dict[str, object] = {"scan_id": f"section_{current_index}", "ms_level": 1, "rt": None, "precursor_mz": None}
    lowered = line.lower()
    if "ms2" in lowered or "ms/ms" in lowered:
        context["ms_level"] = 2
    elif "ms1" in lowered:
        context["ms_level"] = 1
    for match in SECTION_RE.finditer(line):
        scan_id, ms_a, ms_b, precursor, rt = match.groups()
        if scan_id:
            context["scan_id"] = scan_id
        if ms_a or ms_b:
            context["ms_level"] = int(ms_a or ms_b)
        if precursor:
            context["precursor_mz"] = float(precursor)
            context["ms_level"] = 2
        if rt:
            context["rt"] = float(rt)
    return context


def parse_processed_peak_table(text: str) -> list[_RawScan]:
    scans: dict[str, _RawScan] = {}
    header: dict[str, int] | None = None
    current = {"scan_id": "processed_ms1", "ms_level": 1, "rt": None, "precursor_mz": None}
    section_index = 1
    for line_no, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if line.startswith(">") or (line.startswith("[") and line.endswith("]")):
            section_index += 1
            current = _section_context(line, section_index)
            header = None
            continue
        parts = _split_record(line)
        if not parts:
            continue
        if _looks_like_header(parts):
            indices = _header_indices(parts)
            if "mz" in indices and "intensity" in indices:
                header = indices
            continue
        try:
            if header and "mz" in header and "intensity" in header:
                mz = float(parts[header["mz"]])
                intensity = float(parts[header["intensity"]])
                scan_id = parts[header["scan_id"]] if "scan_id" in header and header["scan_id"] < len(parts) and parts[header["scan_id"]].strip() else str(current["scan_id"])
                ms_level = _to_int(parts[header["ms_level"]]) if "ms_level" in header and header["ms_level"] < len(parts) else int(current["ms_level"] or 1)
                rt = _to_float(parts[header["rt"]]) if "rt" in header and header["rt"] < len(parts) and parts[header["rt"]].strip() else current["rt"]
                precursor_mz = _to_float(parts[header["precursor_mz"]]) if "precursor_mz" in header and header["precursor_mz"] < len(parts) and parts[header["precursor_mz"]].strip() else current["precursor_mz"]
                polarity = parts[header["polarity"]].strip().lower() if "polarity" in header and header["polarity"] < len(parts) and parts[header["polarity"]].strip() else "unknown"
            else:
                numbers = FLOAT_RE.findall(line.replace("%", " "))
                if len(numbers) < 2:
                    continue
                mz = float(numbers[0])
                intensity = float(numbers[1])
                scan_id = str(current["scan_id"])
                ms_level = int(current["ms_level"] or 1)
                rt = current["rt"]
                precursor_mz = current["precursor_mz"]
                polarity = "unknown"
        except (ValueError, IndexError) as exc:
            raise LCMSImportError(f"Processed LC-MS peak-table line {line_no} could not be parsed.") from exc
        if mz <= 0:
            raise LCMSImportError(f"Processed LC-MS peak-table line {line_no} has non-positive m/z.")
        if intensity < 0:
            raise LCMSImportError(f"Processed LC-MS peak-table line {line_no} has negative intensity.")
        if ms_level not in {1, 2}:
            ms_level = 2 if precursor_mz else 1
        if ms_level == 2 and precursor_mz is None:
            precursor_mz = _to_float(current.get("precursor_mz"))
        key = str(scan_id or f"scan_{len(scans)+1}")
        if key not in scans:
            scans[key] = _RawScan(
                scan_id=key,
                ms_level=ms_level,
                retention_time_min=float(rt) if rt is not None else None,
                precursor_mz=precursor_mz,
                polarity=polarity if polarity in {"positive", "negative"} else "unknown",
                source="processed_peak_table",
            )
        scans[key].peaks.append((mz, intensity))
        if scans[key].precursor_mz is None and precursor_mz is not None:
            scans[key].precursor_mz = precursor_mz
    if not scans:
        raise LCMSImportError("No LC-MS peaks were parsed. Provide mz/intensity rows or a supported mzML/mzXML file.")
    return list(scans.values())


def _decode_float_array(binary_text: str, *, precision: int, compressed: bool, byte_order: str = "little", warnings: list[str] | None = None) -> list[float]:
    text = (binary_text or "").strip()
    if not text:
        return []
    try:
        data = base64.b64decode(text)
        if compressed:
            data = zlib.decompress(data)
        endian = "<" if byte_order != "big" else ">"
        code = "d" if precision == 64 else "f"
        size = struct.calcsize(code)
        if len(data) % size != 0:
            if warnings is not None:
                warnings.append("Binary array length is not an even multiple of the configured float size; truncated unread bytes.")
            data = data[: len(data) - (len(data) % size)]
        return [item[0] for item in struct.iter_unpack(endian + code, data)]
    except Exception as exc:  # noqa: BLE001 - parser should return warnings rather than crash on unsupported arrays.
        if warnings is not None:
            warnings.append(f"Could not decode binary MS array: {exc}")
        return []


def _decode_mzml_peaks(spectrum: ET.Element, warnings: list[str]) -> list[tuple[float, float]]:
    mz_array: list[float] = []
    intensity_array: list[float] = []
    for bda in _iter_named(spectrum, "binaryDataArray"):
        params = _cv_params(bda)
        names = " ".join(p.get("name", "") for p in params).lower()
        accessions = " ".join(p.get("accession", "") for p in params).lower()
        if "ms-numpress" in names or "ms:100231" in accessions:
            warnings.append("MS-Numpress-compressed mzML arrays are not decoded by this lightweight bridge; convert to zlib/no-compression mzML or processed CSV.")
            continue
        array_type = None
        if "m/z array" in names or "ms:1000514" in accessions:
            array_type = "mz"
        elif "intensity array" in names or "ms:1000515" in accessions:
            array_type = "intensity"
        if array_type is None:
            continue
        precision = 32 if "32-bit float" in names or "ms:1000521" in accessions else 64
        compressed = "zlib compression" in names or "ms:1000574" in accessions
        binary_node = next((child for child in bda if _tag_name(child) == "binary"), None)
        if binary_node is None or not (binary_node.text or "").strip():
            continue
        values = _decode_float_array(binary_node.text or "", precision=precision, compressed=compressed, byte_order="little", warnings=warnings)
        if array_type == "mz":
            mz_array = values
        else:
            intensity_array = values
    return [(float(mz), float(intensity)) for mz, intensity in zip(mz_array, intensity_array) if mz > 0 and intensity >= 0]


def parse_mzml(text: str) -> tuple[list[_RawScan], list[str]]:
    warnings: list[str] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise LCMSImportError(f"mzML XML could not be parsed: {exc}") from exc
    scans: list[_RawScan] = []
    for index, spectrum in enumerate(_iter_named(root, "spectrum"), start=1):
        scan_id = spectrum.attrib.get("id") or spectrum.attrib.get("index") or f"mzml_scan_{index}"
        ms_level = _to_int(_find_cv_value(spectrum, "ms level", "ms:1000511")) or 1
        tic = _to_float(_find_cv_value(spectrum, "total ion current", "ms:1000285"))
        base_mz = _to_float(_find_cv_value(spectrum, "base peak m/z", "ms:1000504"))
        base_intensity = _to_float(_find_cv_value(spectrum, "base peak intensity", "ms:1000505"))
        polarity = "unknown"
        names = " ".join(p.get("name", "") for p in _cv_params(spectrum)).lower()
        if "positive scan" in names:
            polarity = "positive"
        elif "negative scan" in names:
            polarity = "negative"
        rt = None
        for scan in _iter_named(spectrum, "scan"):
            rt_param = _find_cv_param(scan, "scan start time", "ms:1000016")
            if rt_param:
                rt = _parse_retention_time(rt_param.get("value"), rt_param.get("unitName") or rt_param.get("unitAccession"))
                break
        precursor_mz = None
        for selected in _iter_named(spectrum, "selectedIon"):
            precursor_mz = _to_float(_find_cv_value(selected, "selected ion m/z", "ms:1000744"))
            if precursor_mz is not None:
                break
        scan_warnings: list[str] = []
        peaks = _decode_mzml_peaks(spectrum, scan_warnings)
        warnings.extend(scan_warnings)
        if not peaks and base_mz is not None and base_intensity is not None:
            peaks = [(base_mz, base_intensity)]
            warnings.append(f"mzML scan {scan_id} did not expose decodable arrays; using base-peak metadata only.")
        scans.append(
            _RawScan(
                scan_id=str(scan_id),
                ms_level=2 if int(ms_level) == 2 else 1,
                retention_time_min=rt,
                precursor_mz=precursor_mz,
                polarity=polarity,
                peaks=peaks,
                total_ion_current=tic,
                base_peak_mz=base_mz,
                base_peak_intensity=base_intensity,
                source="mzML",
                warnings=scan_warnings,
            )
        )
    if not scans:
        raise LCMSImportError("No <spectrum> elements were found in the mzML document.")
    return scans, warnings


def _decode_mzxml_peaks(peaks_elem: ET.Element, warnings: list[str]) -> list[tuple[float, float]]:
    text = (peaks_elem.text or "").strip()
    if not text:
        return []
    precision = int(peaks_elem.attrib.get("precision") or "32")
    compression = (peaks_elem.attrib.get("compressionType") or "none").lower()
    byte_order_raw = (peaks_elem.attrib.get("byteOrder") or "network").lower()
    byte_order = "big" if byte_order_raw in {"network", "big", "bigendian"} else "little"
    values = _decode_float_array(text, precision=precision, compressed=("zlib" in compression), byte_order=byte_order, warnings=warnings)
    if len(values) % 2:
        values = values[:-1]
        warnings.append("mzXML peak pair array contained an odd number of float values; last value was ignored.")
    return [(float(values[i]), float(values[i + 1])) for i in range(0, len(values), 2) if values[i] > 0 and values[i + 1] >= 0]


def parse_mzxml(text: str) -> tuple[list[_RawScan], list[str]]:
    warnings: list[str] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise LCMSImportError(f"mzXML XML could not be parsed: {exc}") from exc
    scans: list[_RawScan] = []
    for index, scan in enumerate(_iter_named(root, "scan"), start=1):
        scan_id = scan.attrib.get("num") or scan.attrib.get("id") or f"mzxml_scan_{index}"
        ms_level = int(scan.attrib.get("msLevel") or scan.attrib.get("mslevel") or 1)
        rt = _parse_retention_time(scan.attrib.get("retentionTime"))
        tic = _to_float(scan.attrib.get("totIonCurrent") or scan.attrib.get("totalIonCurrent"))
        base_mz = _to_float(scan.attrib.get("basePeakMz") or scan.attrib.get("basePeakMZ"))
        base_intensity = _to_float(scan.attrib.get("basePeakIntensity"))
        polarity = {"+": "positive", "-": "negative", "positive": "positive", "negative": "negative"}.get((scan.attrib.get("polarity") or "").lower(), "unknown")
        precursor_mz = None
        for child in scan:
            if _tag_name(child) == "precursorMz":
                precursor_mz = _to_float((child.text or "").strip())
                break
        scan_warnings: list[str] = []
        peaks: list[tuple[float, float]] = []
        for child in scan:
            if _tag_name(child) == "peaks":
                peaks = _decode_mzxml_peaks(child, scan_warnings)
                break
        warnings.extend(scan_warnings)
        if not peaks and base_mz is not None and base_intensity is not None:
            peaks = [(base_mz, base_intensity)]
            warnings.append(f"mzXML scan {scan_id} did not expose decodable arrays; using base-peak metadata only.")
        scans.append(
            _RawScan(
                scan_id=str(scan_id),
                ms_level=2 if ms_level == 2 else 1,
                retention_time_min=rt,
                precursor_mz=precursor_mz,
                polarity=polarity,
                peaks=peaks,
                total_ion_current=tic,
                base_peak_mz=base_mz,
                base_peak_intensity=base_intensity,
                source="mzXML",
                warnings=scan_warnings,
            )
        )
    if not scans:
        raise LCMSImportError("No <scan> elements were found in the mzXML document.")
    return scans, warnings


def _relative_peaks(raw_peaks: list[tuple[float, float]], *, min_relative_intensity: float, max_count: int) -> list[LCMSPeak]:
    if not raw_peaks:
        return []
    max_intensity = max((intensity for _, intensity in raw_peaks), default=0.0)
    if max_intensity <= 0:
        return []
    peaks: list[LCMSPeak] = []
    for mz, intensity in raw_peaks:
        rel = intensity / max_intensity * 100.0
        if rel >= min_relative_intensity:
            peaks.append(LCMSPeak(mz=round(float(mz), 6), intensity=round(float(intensity), 6), relative_intensity=round(rel, 4)))
    peaks.sort(key=lambda p: (p.relative_intensity, p.intensity), reverse=True)
    return peaks[:max_count]


def _scan_tic(scan: _RawScan) -> float:
    if scan.total_ion_current is not None:
        return float(scan.total_ion_current)
    return float(sum(intensity for _, intensity in scan.peaks))


def _base_peak(scan: _RawScan) -> tuple[float | None, float | None]:
    if scan.base_peak_mz is not None and scan.base_peak_intensity is not None:
        return scan.base_peak_mz, scan.base_peak_intensity
    if not scan.peaks:
        return None, None
    mz, intensity = max(scan.peaks, key=lambda pair: pair[1])
    return float(mz), float(intensity)


def _peak_list_text(peaks: list[LCMSPeak]) -> str:
    if not peaks:
        return ""
    sorted_peaks = sorted(peaks, key=lambda p: p.mz)
    rows = ["m/z,intensity,relative_intensity"]
    rows.extend(f"{p.mz:.6f},{p.intensity:.6g},{p.relative_intensity:.4g}" for p in sorted_peaks)
    return "\n".join(rows)


def _select_msms_scan(scans: list[_RawScan], preferred_precursor_mz: float | None, *, ppm_tolerance: float, mz_tolerance_da: float) -> _RawScan | None:
    ms2 = [scan for scan in scans if scan.ms_level == 2]
    if not ms2:
        return None
    if preferred_precursor_mz is not None:
        scored: list[tuple[float, _RawScan]] = []
        for scan in ms2:
            if scan.precursor_mz is None:
                continue
            abs_error = abs(scan.precursor_mz - preferred_precursor_mz)
            tolerance = max(mz_tolerance_da, abs(preferred_precursor_mz) * ppm_tolerance / 1_000_000.0)
            if abs_error <= tolerance:
                scored.append((abs_error, scan))
        if scored:
            scored.sort(key=lambda item: item[0])
            return scored[0][1]
    return max(ms2, key=lambda scan: (_scan_tic(scan), len(scan.peaks)))


def import_lcms_bridge(request: LCMSImportBridgeRequest, *, raw_bytes: bytes | None = None) -> LCMSImportBridgeResult:
    source_text = request.source_text or ""
    raw_for_hash = raw_bytes if raw_bytes is not None else source_text.encode("utf-8", errors="replace")
    computed_hash = _sha256_bytes(raw_for_hash)
    warnings: list[str] = []
    detected_format, detection_warnings = _detect_format(request.filename, source_text, request.source_format)
    warnings.extend(detection_warnings)
    if detected_format == "unsupported_vendor":
        return LCMSImportBridgeResult(
            sample_id=request.sample_id,
            filename=request.filename,
            source_format="unsupported_vendor",
            file_sha256=computed_hash,
            immutable_raw_data=True,
            label="unsupported_vendor_format",
            scan_count=0,
            ms1_scan_count=0,
            ms2_scan_count=0,
            chromatogram=[] ,
            scans=[] ,
            extracted_ms1_peak_count=0,
            extracted_ms1_peak_list_text="",
            extracted_msms_spectrum_count=0,
            extracted_msms_peak_list_text="",
            selected_msms_scan_id=None,
            selected_msms_precursor_mz=None,
            primary_ms1_mz=None,
            extracted_precursors=[] ,
            recommended_next_actions=[
                "Convert the vendor raw file to mzML/mzXML with a trusted converter or export centroid MS1/MS2 peak tables.",
                "Preserve the original vendor file separately with its SHA-256 hash for audit/provenance.",
            ],
            warnings=warnings,
            notes=["No proprietary vendor bytes were modified or interpreted by this bridge."],
            metadata={"parser_version": "week35_lcms_import_bridge_v1", "requested_format": request.source_format},
        )
    try:
        if detected_format == "mzML":
            scans, parser_warnings = parse_mzml(source_text)
            warnings.extend(parser_warnings)
        elif detected_format == "mzXML":
            scans, parser_warnings = parse_mzxml(source_text)
            warnings.extend(parser_warnings)
        else:
            scans = parse_processed_peak_table(source_text)
    except LCMSImportError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LCMSImportError(f"LC-MS import bridge failed: {exc}") from exc

    scans = scans[: request.max_scans_to_report] if len(scans) > request.max_scans_to_report else scans
    ms1_scans = [scan for scan in scans if scan.ms_level == 1]
    ms2_scans = [scan for scan in scans if scan.ms_level == 2]
    chrom: list[LCMSChromatogramPoint] = []
    summaries: list[LCMSScanSummary] = []
    imported_spectra: list[LCMSImportedSpectrum] = []
    for scan in scans:
        tic = _scan_tic(scan)
        base_mz, base_intensity = _base_peak(scan)
        peak_count = len(scan.peaks)
        chrom.append(
            LCMSChromatogramPoint(
                scan_id=scan.scan_id,
                ms_level=scan.ms_level,
                retention_time_min=scan.retention_time_min,
                total_ion_current=round(tic, 6),
                base_peak_mz=round(base_mz, 6) if base_mz is not None else None,
                base_peak_intensity=round(base_intensity, 6) if base_intensity is not None else None,
            )
        )
        summaries.append(
            LCMSScanSummary(
                scan_id=scan.scan_id,
                ms_level=scan.ms_level,
                retention_time_min=scan.retention_time_min,
                precursor_mz=scan.precursor_mz,
                polarity=scan.polarity if scan.polarity in {"positive", "negative"} else "unknown",
                peak_count=peak_count,
                total_ion_current=round(tic, 6),
                base_peak_mz=round(base_mz, 6) if base_mz is not None else None,
                base_peak_intensity=round(base_intensity, 6) if base_intensity is not None else None,
                warnings=scan.warnings,
            )
        )
        imported_spectra.append(
            LCMSImportedSpectrum(
                scan_id=scan.scan_id,
                ms_level=scan.ms_level,
                retention_time_min=scan.retention_time_min,
                precursor_mz=scan.precursor_mz,
                polarity=scan.polarity if scan.polarity in {"positive", "negative"} else "unknown",
                peak_count=peak_count,
                peaks=_relative_peaks(scan.peaks, min_relative_intensity=request.min_relative_intensity, max_count=request.max_peaks_per_spectrum),
                warnings=scan.warnings,
            )
        )
    # Aggregate MS1 peaks for MS1 adduct/isotope inference.
    aggregate_ms1: list[tuple[float, float]] = []
    for scan in ms1_scans:
        aggregate_ms1.extend(scan.peaks)
    ms1_peaks = _relative_peaks(aggregate_ms1, min_relative_intensity=request.min_relative_intensity, max_count=request.max_ms1_peaks)
    primary_ms1_mz = None
    if ms1_peaks:
        primary_ms1_mz = max(ms1_peaks, key=lambda p: p.intensity).mz
    selected_ms2 = _select_msms_scan(ms2_scans, request.preferred_msms_precursor_mz, ppm_tolerance=request.ppm_tolerance, mz_tolerance_da=request.mz_tolerance_da)
    selected_msms_peaks: list[LCMSPeak] = []
    if selected_ms2:
        selected_msms_peaks = _relative_peaks(selected_ms2.peaks, min_relative_intensity=request.min_relative_intensity, max_count=request.max_msms_peaks_per_spectrum)
    precursors: list[LCMSExtractedPrecursor] = []
    seen_precursors: set[tuple[str, int]] = set()
    for scan in ms2_scans:
        if scan.precursor_mz is None:
            continue
        key = (f"{scan.precursor_mz:.4f}", int(round((scan.retention_time_min or 0.0) * 100)))
        if key in seen_precursors:
            continue
        seen_precursors.add(key)
        precursors.append(
            LCMSExtractedPrecursor(
                scan_id=scan.scan_id,
                precursor_mz=round(scan.precursor_mz, 6),
                retention_time_min=scan.retention_time_min,
                peak_count=len(scan.peaks),
                total_ion_current=round(_scan_tic(scan), 6),
            )
        )
    label = "ready_for_downstream_ms" if (ms1_peaks or selected_msms_peaks) else "metadata_only"
    if not ms2_scans:
        warnings.append("No MS/MS scans were found; downstream MS/MS annotation and fragmentation-tree inputs will remain empty.")
    if not ms1_peaks:
        warnings.append("No MS1 peaks survived the threshold; lower the minimum relative intensity or check the input format.")
    actions = [
        "Paste the extracted MS1 peak list into Adduct + Isotope Pattern Inference.",
        "Paste the selected MS/MS peak list into Processed MS/MS Annotation and Fragmentation-Tree Reasoning.",
        "Copy the file SHA-256 into the report provenance field and keep the original raw file immutable.",
    ]
    if detected_format in {"mzML", "mzXML"}:
        actions.append("Review scan grouping and selected precursor before using the imported peak lists for candidate scoring.")
    return LCMSImportBridgeResult(
        sample_id=request.sample_id,
        filename=request.filename,
        source_format=detected_format,  # type: ignore[arg-type]
        file_sha256=computed_hash,
        immutable_raw_data=True,
        label=label,
        scan_count=len(scans),
        ms1_scan_count=len(ms1_scans),
        ms2_scan_count=len(ms2_scans),
        chromatogram=chrom,
        scans=summaries,
        imported_spectra=imported_spectra,
        extracted_ms1_peak_count=len(ms1_peaks),
        extracted_ms1_peak_list_text=_peak_list_text(ms1_peaks),
        extracted_msms_spectrum_count=1 if selected_ms2 else 0,
        extracted_msms_peak_list_text=_peak_list_text(selected_msms_peaks),
        selected_msms_scan_id=selected_ms2.scan_id if selected_ms2 else None,
        selected_msms_precursor_mz=round(selected_ms2.precursor_mz, 6) if selected_ms2 and selected_ms2.precursor_mz is not None else None,
        primary_ms1_mz=primary_ms1_mz,
        extracted_precursors=precursors,
        recommended_next_actions=actions,
        warnings=warnings,
        notes=[
            "The import bridge creates processed peak-list views and provenance metadata only; it does not overwrite or mutate raw LC-MS/MS data.",
            "mzML/mzXML parsing is intentionally conservative and should be validated against local vendor software for regulated workflows.",
        ],
        metadata={
            "parser_version": "week35_lcms_import_bridge_v1",
            "requested_format": request.source_format,
            "source_text_sha256": _sha256_bytes(source_text.encode("utf-8", errors="replace")),
            "preferred_msms_precursor_mz": request.preferred_msms_precursor_mz,
            "format_detection_warnings": detection_warnings,
        },
    )
