from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import tarfile
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_RAW_DATA_VAULT_DIR = "raw_data_vault"
DEFAULT_RAW_ARCHIVE_MAX_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_RAW_ARCHIVE_MAX_FILES = 5_000
DEFAULT_RAW_ARCHIVE_ALLOWED_EXTENSIONS = (".zip", ".tar.gz", ".tgz")
RAW_ARCHIVE_HASH_MISMATCH_MESSAGE = "Raw archive hash mismatch. Processing blocked to protect data integrity."


class RawVaultError(ValueError):
    """Raised when a raw NMR archive cannot be accepted into the vault."""


RawFIDStorageError = RawVaultError


@dataclass(frozen=True)
class RawArchiveRecord:
    raw_archive_id: str
    filename: str
    safe_filename: str
    archive_format: str
    sha256: str
    byte_size: int
    storage_path: str | None
    object_key: str | None
    created_at: str
    vendor_detected: str
    dataset_root: str | None
    required_files_present: bool
    files_found: list[str]
    acquisition_metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    storage_backend: str = "local_raw_vault"
    storage_status: str = "stored"
    read_only: bool = False
    raw_data_immutable: bool = True
    raw_bytes_embedded_in_metadata: bool = False
    integrity_verified: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_provenance_dict(self) -> dict[str, Any]:
        data = self.as_dict()
        data.update(
            {
                "original_filename": self.filename,
                "stored_at": self.created_at,
                "vault_record": True,
            }
        )
        return data


@dataclass(frozen=True)
class RawArchiveIntegrityReport:
    raw_archive_id: str | None
    storage_path: str | None
    expected_sha256: str | None
    actual_sha256: str | None
    expected_byte_size: int | None
    actual_byte_size: int | None
    exists: bool
    sha256_verified: bool
    byte_size_matches: bool
    ok: bool
    warning: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __bool__(self) -> bool:
        return self.ok


class RawStorageBackend:
    """Storage abstraction for immutable raw NMR archives."""

    name = "raw_storage"

    def save(
        self,
        *,
        content: bytes,
        sha256: str,
        filename: str,
        immutable: bool = True,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def read(
        self,
        *,
        storage_path: str | Path | None,
        expected_sha256: str,
        expected_byte_size: int | None = None,
        raw_archive_id: str | None = None,
        require_hash_verification: bool = True,
    ) -> bytes:
        raise NotImplementedError

    def exists(self, *, storage_path: str | Path | None, raw_archive_id: str | None = None) -> bool:
        raise NotImplementedError

    def verify(
        self,
        *,
        storage_path: str | Path | None,
        expected_sha256: str | None,
        expected_byte_size: int | None = None,
        raw_archive_id: str | None = None,
        require_hash_verification: bool = True,
    ) -> RawArchiveIntegrityReport:
        raise NotImplementedError

    def path_or_uri(self, *, sha256: str, filename: str) -> str:
        raise NotImplementedError


class LocalRawStorageBackend(RawStorageBackend):
    """Local development backend storing archives under raw_data_vault/{sha256}/."""

    name = "local_raw_vault"

    def __init__(self, vault_dir: str | Path = DEFAULT_RAW_DATA_VAULT_DIR) -> None:
        self.vault_dir = Path(vault_dir).expanduser()

    def path_or_uri(self, *, sha256: str, filename: str) -> str:
        return str(self.vault_dir / sha256 / filename)

    def save(
        self,
        *,
        content: bytes,
        sha256: str,
        filename: str,
        immutable: bool = True,
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        warning_list = warnings if warnings is not None else []
        target_dir = self.vault_dir / sha256
        target = target_dir / filename
        target_dir.mkdir(parents=True, exist_ok=True)
        reused = False
        if target.exists():
            _verify_file_hash(target, sha256)
            warning_list.append("Raw archive already existed in the vault; existing immutable object was reused.")
            reused = True
        else:
            temp_path = target_dir / f".{filename}.tmp"
            try:
                with temp_path.open("xb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, target)
            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass
        read_only = _make_read_only(target, warning_list) if immutable else False
        _verify_file_hash(target, sha256)
        return {
            "storage_path": str(target),
            "object_key": f"{sha256}/{filename}",
            "read_only": read_only,
            "reused": reused,
            "storage_backend": self.name,
        }

    def exists(self, *, storage_path: str | Path | None, raw_archive_id: str | None = None) -> bool:
        path = _resolve_integrity_path(raw_archive_id, storage_path, vault_dir=self.vault_dir)
        return bool(path and path.is_file())

    def verify(
        self,
        *,
        storage_path: str | Path | None,
        expected_sha256: str | None,
        expected_byte_size: int | None = None,
        raw_archive_id: str | None = None,
        require_hash_verification: bool = True,
    ) -> RawArchiveIntegrityReport:
        path = _resolve_integrity_path(raw_archive_id, storage_path, vault_dir=self.vault_dir)
        if path is None or not path.is_file():
            return RawArchiveIntegrityReport(
                raw_archive_id=raw_archive_id,
                storage_path=str(path) if path is not None else None,
                expected_sha256=str(expected_sha256) if expected_sha256 else None,
                actual_sha256=None,
                expected_byte_size=expected_byte_size,
                actual_byte_size=None,
                exists=False,
                sha256_verified=False,
                byte_size_matches=False,
                ok=False,
                warning="Immutable raw archive is not available at the recorded vault path.",
            )
        actual_size = path.stat().st_size
        actual_sha = _sha256_file(path) if require_hash_verification else None
        sha_ok = (not require_hash_verification) or (bool(expected_sha256) and actual_sha == str(expected_sha256))
        size_ok = expected_byte_size is None or actual_size == expected_byte_size
        warning = None
        if not sha_ok:
            warning = RAW_ARCHIVE_HASH_MISMATCH_MESSAGE
        elif not size_ok:
            warning = "Raw archive byte size mismatch. Processing blocked to protect data integrity."
        return RawArchiveIntegrityReport(
            raw_archive_id=raw_archive_id,
            storage_path=str(path),
            expected_sha256=str(expected_sha256) if expected_sha256 else None,
            actual_sha256=actual_sha,
            expected_byte_size=expected_byte_size,
            actual_byte_size=actual_size,
            exists=True,
            sha256_verified=sha_ok,
            byte_size_matches=size_ok,
            ok=sha_ok and size_ok,
            warning=warning,
        )

    def read(
        self,
        *,
        storage_path: str | Path | None,
        expected_sha256: str,
        expected_byte_size: int | None = None,
        raw_archive_id: str | None = None,
        require_hash_verification: bool = True,
    ) -> bytes:
        report = self.verify(
            storage_path=storage_path,
            expected_sha256=expected_sha256,
            expected_byte_size=expected_byte_size,
            raw_archive_id=raw_archive_id,
            require_hash_verification=require_hash_verification,
        )
        if not report.ok:
            raise RawVaultError(report.warning or "Raw archive integrity verification failed.")
        with Path(str(report.storage_path)).expanduser().open("rb") as handle:
            return handle.read()


class S3RawStorageBackend(RawStorageBackend):
    """Production placeholder for object storage backed by S3 or compatible APIs."""

    name = "s3_raw_vault"

    # TODO: implement with S3 object lock/versioning, server-side encryption,
    # conditional writes, and checksum validation before enabling in production.


@dataclass(frozen=True)
class _ArchiveMember:
    name: str
    size: int
    kind: str = "file"


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_BRUKER_PARAM_RE = re.compile(r"^##\$([^=]+)=\s*(.*)$")
_VARIAN_SIMPLE_PARAM_RE = re.compile(r"^([A-Za-z][\w.]*)\s+(.+)$")
_TEXT_METADATA_BASENAMES = {"acqus", "procs", "proc", "procpar", "pulseprogram"}
_BRUKER_ACQ_KEYS = {
    "AQ",
    "TD",
    "SW",
    "SW_h",
    "SFO1",
    "BF1",
    "O1",
    "O1P",
    "NUC1",
    "SOLVENT",
    "PULPROG",
    "TE",
    "RG",
    "GRPDLY",
    "AQ_mod",
    "BYTORDA",
    "DTYPA",
}
_BRUKER_PROCS_KEYS = {"SF", "OFFSET", "SW_p", "SI", "XDIM", "NC_proc", "PHC0", "PHC1"}
_VARIAN_ACQ_KEYS = {
    "sfrq",
    "reffrq",
    "sw",
    "tof",
    "tn",
    "dn",
    "np",
    "solvent",
    "seqfil",
    "temp",
}


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "raw_nmr_archive").name.strip() or "raw_nmr_archive"
    safe = _SAFE_FILENAME_RE.sub("_", name)[:180]
    return safe or "raw_nmr_archive"


def _archive_extension(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".tar.gz"):
        return ".tar.gz"
    if lower.endswith(".tgz"):
        return ".tgz"
    return Path(lower).suffix


def _normalize_allowed_extensions(allowed_extensions: tuple[str, ...] | list[str] | set[str] | None) -> tuple[str, ...]:
    values = tuple(allowed_extensions or DEFAULT_RAW_ARCHIVE_ALLOWED_EXTENSIONS)
    normalized: list[str] = []
    for value in values:
        item = str(value).strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = f".{item}"
        normalized.append(item)
    return tuple(normalized) or DEFAULT_RAW_ARCHIVE_ALLOWED_EXTENSIONS


def _validate_supported_extension(
    filename: str,
    *,
    allowed_extensions: tuple[str, ...] | list[str] | set[str] | None = None,
) -> str:
    suffix = _archive_extension(filename)
    allowed = set(_normalize_allowed_extensions(allowed_extensions))
    if suffix == ".zip" and ".zip" in allowed:
        return "zip"
    if suffix in {".tar.gz", ".tgz"} and suffix in allowed:
        return "tar.gz"
    allowed_label = ", ".join(_normalize_allowed_extensions(allowed_extensions))
    raise RawVaultError(f"Raw NMR archive uploads must use one of: {allowed_label}.")


def _is_safe_member_name(name: str) -> bool:
    if not name or name.startswith(("/", "\\")):
        return False
    parts = Path(name).parts
    return not any(part in {"..", ""} for part in parts)


def _check_limits(
    *,
    members: list[_ArchiveMember],
    byte_size: int,
    max_bytes: int,
    max_files: int,
) -> None:
    if byte_size > max_bytes:
        raise RawVaultError(
            f"Raw NMR archive is too large ({byte_size} bytes); limit is {max_bytes} bytes."
        )
    if len(members) > max_files:
        raise RawVaultError(
            f"Raw NMR archive contains too many files ({len(members)}); limit is {max_files}."
        )
    uncompressed_size = sum(max(0, int(member.size)) for member in members)
    if uncompressed_size > max_bytes:
        raise RawVaultError(
            f"Raw NMR archive expands beyond the configured limit ({uncompressed_size} bytes)."
        )


def _zip_member_kind(info: zipfile.ZipInfo) -> str:
    file_type = (info.external_attr >> 16) & 0o170000
    if file_type == 0:
        return "file"
    if file_type == stat.S_IFREG:
        return "file"
    if file_type == stat.S_IFDIR:
        return "directory"
    if file_type == stat.S_IFLNK:
        return "symlink"
    if file_type in {stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK}:
        return "device"
    return "special"


def _read_zip_members(content: bytes) -> tuple[list[_ArchiveMember], dict[str, bytes]]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members: list[_ArchiveMember] = []
            small_text_files: dict[str, bytes] = {}
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if not _is_safe_member_name(info.filename):
                    raise RawVaultError("Raw NMR zip contains an unsafe relative path or absolute path.")
                kind = _zip_member_kind(info)
                if kind != "file":
                    raise RawVaultError(f"Raw NMR zip contains a disallowed {kind} entry.")
                members.append(_ArchiveMember(info.filename, int(info.file_size), kind))
                basename = Path(info.filename).name.lower()
                if basename in _TEXT_METADATA_BASENAMES and info.file_size <= 1_000_000:
                    small_text_files[info.filename] = archive.read(info)
    except zipfile.BadZipFile as exc:
        raise RawVaultError("Raw NMR archive is not a valid .zip file.") from exc
    if not members:
        raise RawVaultError("Raw NMR archive is empty.")
    return members, small_text_files


def _read_tar_members(content: bytes) -> tuple[list[_ArchiveMember], dict[str, bytes]]:
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            members: list[_ArchiveMember] = []
            small_text_files: dict[str, bytes] = {}
            for member in archive.getmembers():
                if member.isdir():
                    continue
                if not _is_safe_member_name(member.name):
                    raise RawVaultError("Raw NMR tar archive contains an unsafe relative path or absolute path.")
                if member.issym() or member.islnk():
                    raise RawVaultError("Raw NMR tar archive contains a disallowed link entry.")
                if not member.isfile():
                    raise RawVaultError("Raw NMR tar archive contains a disallowed special file entry.")
                members.append(_ArchiveMember(member.name, int(member.size), "file"))
                basename = Path(member.name).name.lower()
                if basename in _TEXT_METADATA_BASENAMES and member.size <= 1_000_000:
                    handle = archive.extractfile(member)
                    if handle is not None:
                        with handle:
                            small_text_files[member.name] = handle.read()
    except tarfile.TarError as exc:
        raise RawVaultError("Raw NMR archive is not a valid tar.gz file.") from exc
    if not members:
        raise RawVaultError("Raw NMR archive is empty.")
    return members, small_text_files


def _files_by_directory(files_found: list[str]) -> dict[str, set[str]]:
    by_dir: dict[str, set[str]] = {}
    for name in files_found:
        path = Path(name)
        parent = str(path.parent) if str(path.parent) != "." else ""
        by_dir.setdefault(parent, set()).add(path.name.lower())
    return by_dir


def _detect_dataset(files_found: list[str]) -> tuple[str, str | None, list[str], dict[str, Any]]:
    by_dir = _files_by_directory(files_found)
    best_vendor = "unknown"
    best_root: str | None = None
    best_score = 0
    best_meta: dict[str, Any] = {}
    for root, basenames in by_dir.items():
        bruker_raw = sorted({"fid", "ser"} & basenames)
        bruker_score = (10 if "acqus" in basenames else 0) + (10 if bruker_raw else 0)
        bruker_score += len({"acqu", "pulseprogram", "pdata", "procs", "proc"} & basenames)
        if bruker_score > best_score:
            best_vendor = "Bruker"
            best_root = root
            best_score = bruker_score
            best_meta = {
                "required_files_present": bool("acqus" in basenames and bruker_raw),
                "raw_files_present": bruker_raw,
                "supports_future_ser": "ser" in basenames,
            }
        varian_score = (10 if "procpar" in basenames else 0) + (10 if "fid" in basenames else 0)
        if root.lower().endswith(".fid"):
            varian_score += 3
        varian_score += len({"log", "text", "phasefile"} & basenames)
        if varian_score > best_score:
            best_vendor = "Varian/Agilent"
            best_root = root
            best_score = varian_score
            best_meta = {
                "required_files_present": "procpar" in basenames and "fid" in basenames,
                "raw_files_present": ["fid"] if "fid" in basenames else [],
            }
    warnings: list[str] = []
    if best_vendor == "unknown" or best_score <= 0:
        warnings.append("No supported Bruker or Varian/Agilent dataset root was detected.")
        best_root = None
    elif not best_meta.get("required_files_present"):
        warnings.append(
            f"{best_vendor} dataset-like files were found, but required raw/acquisition files are incomplete."
        )
    return best_vendor, best_root, warnings, best_meta


def _coerce_param_value(raw: str) -> Any:
    value = raw.strip()
    if value.startswith("<") and value.endswith(">"):
        return value[1:-1]
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    try:
        if re.fullmatch(r"[-+]?\d+", value):
            return int(value)
        if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", value):
            return float(value)
    except Exception:
        return value
    return value


def _parse_bruker_params(text: str, allowed_keys: set[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for line in text.splitlines():
        match = _BRUKER_PARAM_RE.match(line.strip())
        if match:
            key, raw_value = match.groups()
            if key in allowed_keys:
                params[key] = _coerce_param_value(raw_value)
    return params


def _first_text_file(
    *,
    text_files: dict[str, bytes],
    dataset_root: str | None,
    basename: str,
) -> tuple[str, bytes] | None:
    root = dataset_root or ""
    candidates = [
        name
        for name in text_files
        if Path(name).name.lower() == basename and (not root or str(Path(name).parent) == root)
    ]
    if not candidates:
        candidates = [name for name in text_files if Path(name).name.lower() == basename]
    if not candidates:
        return None
    name = sorted(candidates)[0]
    return name, text_files[name]


def _decode_text(payload: bytes) -> str:
    return payload.decode("latin-1", errors="replace")


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().strip("<>").strip('"').strip()
    return cleaned or None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _derive_bruker_acquisition_time(params: dict[str, Any]) -> float | None:
    aq = _to_float(params.get("AQ"))
    if aq is not None:
        return aq
    td = _to_float(params.get("TD"))
    sw_h = _to_float(params.get("SW_h"))
    if td is None or sw_h in {None, 0.0}:
        return None
    return td / (2.0 * sw_h)


def _canonical_bruker_metadata(
    params: dict[str, Any],
    procs: dict[str, Any],
    pulseprogram_text: str | None,
) -> dict[str, Any]:
    pulseprogram = _clean_string(params.get("PULPROG"))
    if not pulseprogram and pulseprogram_text:
        pulseprogram = next((line.strip() for line in pulseprogram_text.splitlines() if line.strip()), None)
    return {
        "nucleus": _clean_string(params.get("NUC1")),
        "spectrometer_frequency_mhz": _to_float(params.get("SFO1") or params.get("BF1")),
        "spectral_width_hz": _to_float(params.get("SW_h")),
        "spectral_width_ppm": _to_float(params.get("SW")),
        "acquisition_time_sec": _derive_bruker_acquisition_time(params),
        "td": _to_int(params.get("TD")),
        "offset_hz": _to_float(params.get("O1")),
        "offset_ppm": _to_float(params.get("O1P")),
        "solvent": _clean_string(params.get("SOLVENT")),
        "pulse_program": pulseprogram,
        "temperature_k": _to_float(params.get("TE")),
        "receiver_gain": _to_float(params.get("RG")),
        "processed_frequency_mhz": _to_float(procs.get("SF")),
        "processed_offset_ppm": _to_float(procs.get("OFFSET")),
    }


def _parse_varian_value(raw_value: str) -> Any:
    value = raw_value.strip()
    if not value:
        return None
    parts = value.split()
    if len(parts) > 1 and re.fullmatch(r"\d+", parts[0]):
        value = " ".join(parts[1:])
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    return _coerce_param_value(value)


def _parse_varian_procpar(text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    lines = [line.rstrip() for line in text.splitlines()]
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        simple = _VARIAN_SIMPLE_PARAM_RE.match(line)
        if simple and len(line.split()) == 2:
            name, raw_value = simple.groups()
            if name in _VARIAN_ACQ_KEYS:
                params[name] = _parse_varian_value(raw_value)
            index += 1
            continue
        name = line.split()[0]
        if name in _VARIAN_ACQ_KEYS and index + 2 < len(lines):
            value_line = lines[index + 2].strip()
            params[name] = _parse_varian_value(value_line)
        index += 3
    return params


def _canonical_varian_metadata(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "nucleus": _clean_string(params.get("tn") or params.get("dn")),
        "spectrometer_frequency_mhz": _to_float(params.get("sfrq") or params.get("reffrq")),
        "spectral_width_hz": _to_float(params.get("sw")),
        "points": _to_int(params.get("np")),
        "offset_hz": _to_float(params.get("tof")),
        "solvent": _clean_string(params.get("solvent")),
        "pulse_sequence": _clean_string(params.get("seqfil")),
        "temperature_c": _to_float(params.get("temp")),
    }


def _extract_acquisition_metadata(
    *,
    vendor: str,
    dataset_root: str | None,
    text_files: dict[str, bytes],
    dataset_metadata: dict[str, Any],
) -> dict[str, Any]:
    metadata = {
        "vendor": vendor,
        "dataset_root": dataset_root,
        "raw_files_present": dataset_metadata.get("raw_files_present", []),
        "supports_future_ser": bool(dataset_metadata.get("supports_future_ser")),
        "required_files_present": bool(dataset_metadata.get("required_files_present")),
    }
    if vendor == "Varian/Agilent":
        procpar = _first_text_file(text_files=text_files, dataset_root=dataset_root, basename="procpar")
        if procpar is None:
            return metadata
        params = _parse_varian_procpar(_decode_text(procpar[1]))
        metadata.update(params)
        metadata.update(
            {key: value for key, value in _canonical_varian_metadata(params).items() if value is not None}
        )
        metadata["source_files"] = {"procpar": procpar[0]}
        return metadata

    acqus = _first_text_file(text_files=text_files, dataset_root=dataset_root, basename="acqus")
    if acqus is None:
        return metadata
    params = _parse_bruker_params(_decode_text(acqus[1]), _BRUKER_ACQ_KEYS)
    procs_file = _first_text_file(text_files=text_files, dataset_root=dataset_root, basename="procs")
    procs = _parse_bruker_params(_decode_text(procs_file[1]), _BRUKER_PROCS_KEYS) if procs_file else {}
    pulse_file = _first_text_file(text_files=text_files, dataset_root=dataset_root, basename="pulseprogram")
    pulse_text = _decode_text(pulse_file[1]) if pulse_file else None
    metadata.update(params)
    if procs:
        metadata["procs"] = procs
    metadata.update(
        {
            key: value
            for key, value in _canonical_bruker_metadata(params, procs, pulse_text).items()
            if value is not None
        }
    )
    metadata["source_files"] = {
        "acqus": acqus[0],
        **({"procs": procs_file[0]} if procs_file else {}),
        **({"pulseprogram": pulse_file[0]} if pulse_file else {}),
    }
    return metadata


def inspect_raw_archive(
    *,
    filename: str,
    content: bytes,
    max_bytes: int = DEFAULT_RAW_ARCHIVE_MAX_BYTES,
    max_files: int = DEFAULT_RAW_ARCHIVE_MAX_FILES,
    allowed_extensions: tuple[str, ...] | list[str] | set[str] | None = None,
) -> dict[str, Any]:
    archive_format = _validate_supported_extension(filename, allowed_extensions=allowed_extensions)
    members, text_files = (
        _read_zip_members(content)
        if archive_format == "zip"
        else _read_tar_members(content)
    )
    _check_limits(
        members=members,
        byte_size=len(content),
        max_bytes=max_bytes,
        max_files=max_files,
    )
    files_found = sorted(member.name for member in members)
    vendor, dataset_root, warnings, dataset_metadata = _detect_dataset(files_found)
    acquisition_metadata = _extract_acquisition_metadata(
        vendor=vendor,
        dataset_root=dataset_root,
        text_files=text_files,
        dataset_metadata=dataset_metadata,
    )
    return {
        "archive_format": archive_format,
        "files_found": files_found[:500],
        "file_count": len(files_found),
        "vendor_detected": vendor,
        "dataset_root": dataset_root,
        "acquisition_metadata": acquisition_metadata,
        "warnings": warnings,
        "dataset_detection": dataset_metadata,
    }


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _verify_file_hash(path: Path, expected_sha256: str) -> None:
    if _sha256_file(path) != expected_sha256:
        raise RawVaultError(RAW_ARCHIVE_HASH_MISMATCH_MESSAGE)


def _make_read_only(path: Path, warnings: list[str]) -> bool:
    try:
        path.chmod(0o444)
        return True
    except OSError as exc:
        warnings.append(f"Could not set raw archive read-only permissions: {exc}")
        return False


def ingest_raw_archive(
    *,
    filename: str,
    content: bytes,
    vault_dir: str | Path = DEFAULT_RAW_DATA_VAULT_DIR,
    max_bytes: int = DEFAULT_RAW_ARCHIVE_MAX_BYTES,
    max_files: int = DEFAULT_RAW_ARCHIVE_MAX_FILES,
    allowed_extensions: tuple[str, ...] | list[str] | set[str] | None = None,
    immutable: bool = True,
    backend: RawStorageBackend | None = None,
) -> RawArchiveRecord:
    """Validate and store raw NMR archive bytes in an immutable development vault."""

    safe_name = _safe_filename(filename)
    digest = _sha256_bytes(content)
    inspection = inspect_raw_archive(
        filename=filename,
        content=content,
        max_bytes=max_bytes,
        max_files=max_files,
        allowed_extensions=allowed_extensions,
    )
    warnings = list(inspection.get("warnings") or [])
    storage = (backend or LocalRawStorageBackend(vault_dir)).save(
        content=content,
        sha256=digest,
        filename=safe_name,
        immutable=immutable,
        warnings=warnings,
    )
    return RawArchiveRecord(
        raw_archive_id=digest,
        filename=filename or safe_name,
        safe_filename=safe_name,
        archive_format=str(inspection["archive_format"]),
        sha256=digest,
        byte_size=len(content),
        storage_path=str(storage["storage_path"]),
        object_key=str(storage["object_key"]) if storage.get("object_key") is not None else None,
        created_at=datetime.now(UTC).isoformat(),
        vendor_detected=str(inspection["vendor_detected"]),
        dataset_root=inspection["dataset_root"],
        files_found=list(inspection["files_found"]),
        required_files_present=bool((inspection.get("dataset_detection") or {}).get("required_files_present")),
        acquisition_metadata=dict(inspection["acquisition_metadata"]),
        warnings=warnings,
        storage_backend=str(storage.get("storage_backend") or "local_raw_vault"),
        read_only=bool(storage.get("read_only")),
        raw_data_immutable=immutable,
    )


def build_raw_upload_provenance(
    *,
    filename: str,
    content: bytes,
    storage_dir: str | Path | None = None,
    max_bytes: int = DEFAULT_RAW_ARCHIVE_MAX_BYTES,
    max_files: int = DEFAULT_RAW_ARCHIVE_MAX_FILES,
    allowed_extensions: tuple[str, ...] | list[str] | set[str] | None = None,
    immutable: bool = True,
    backend: RawStorageBackend | None = None,
) -> dict[str, Any]:
    if storage_dir is None or not str(storage_dir).strip():
        digest = _sha256_bytes(content)
        inspection = inspect_raw_archive(
            filename=filename,
            content=content,
            max_bytes=max_bytes,
            max_files=max_files,
            allowed_extensions=allowed_extensions,
        )
        record = RawArchiveRecord(
            raw_archive_id=digest,
            filename=filename,
            safe_filename=_safe_filename(filename),
            archive_format=str(inspection["archive_format"]),
            sha256=digest,
            byte_size=len(content),
            storage_path=None,
            object_key=None,
            created_at=datetime.now(UTC).isoformat(),
            vendor_detected=str(inspection["vendor_detected"]),
            dataset_root=inspection["dataset_root"],
            required_files_present=bool((inspection.get("dataset_detection") or {}).get("required_files_present")),
            files_found=list(inspection["files_found"]),
            acquisition_metadata=dict(inspection["acquisition_metadata"]),
            warnings=list(inspection["warnings"]),
            storage_backend="metadata_only",
            storage_status="not_configured",
            read_only=False,
        )
        return record.to_provenance_dict()
    return ingest_raw_archive(
        filename=filename,
        content=content,
        vault_dir=storage_dir,
        max_bytes=max_bytes,
        max_files=max_files,
        allowed_extensions=allowed_extensions,
        immutable=immutable,
        backend=backend,
    ).to_provenance_dict()


def _integrity_input_value(raw_archive: Any, key: str) -> Any:
    if isinstance(raw_archive, dict):
        return raw_archive.get(key)
    return getattr(raw_archive, key, None)


def _resolve_integrity_path(
    raw_archive_id: str | None,
    storage_path: str | Path | None,
    *,
    vault_dir: str | Path = DEFAULT_RAW_DATA_VAULT_DIR,
) -> Path | None:
    if storage_path:
        return Path(str(storage_path)).expanduser()
    if not raw_archive_id:
        return None
    vault_entry = Path(vault_dir).expanduser() / str(raw_archive_id)
    if vault_entry.is_file():
        return vault_entry
    if vault_entry.is_dir():
        candidates = [path for path in vault_entry.iterdir() if path.is_file() and not path.name.startswith(".")]
        if len(candidates) == 1:
            return candidates[0]
    return vault_entry


def verify_raw_archive_integrity(
    raw_archive_id: Any,
    *,
    storage_path: str | Path | None = None,
    expected_sha256: str | None = None,
    expected_byte_size: int | None = None,
    require_hash_verification: bool = True,
    backend: RawStorageBackend | None = None,
) -> RawArchiveIntegrityReport:
    """Recalculate and report immutable raw archive SHA-256 integrity."""

    archive_id = (
        _integrity_input_value(raw_archive_id, "raw_archive_id")
        or _integrity_input_value(raw_archive_id, "sha256")
        or (str(raw_archive_id) if raw_archive_id is not None else None)
    )
    resolved_storage_path = storage_path or _integrity_input_value(raw_archive_id, "storage_path")
    expected = expected_sha256 or _integrity_input_value(raw_archive_id, "sha256") or archive_id
    expected_size = expected_byte_size
    if expected_size is None:
        size_value = _integrity_input_value(raw_archive_id, "byte_size")
        try:
            expected_size = int(size_value) if size_value is not None else None
        except (TypeError, ValueError):
            expected_size = None
    return (backend or LocalRawStorageBackend()).verify(
        storage_path=resolved_storage_path,
        expected_sha256=str(expected) if expected else None,
        expected_byte_size=expected_size,
        raw_archive_id=str(archive_id) if archive_id else None,
        require_hash_verification=require_hash_verification,
    )


def verify_vault_archive(provenance: dict[str, Any]) -> bool:
    return bool(verify_raw_archive_integrity(provenance))


verify_stored_raw_upload = verify_vault_archive


def load_raw_archive_bytes(
    provenance: dict[str, Any],
    *,
    require_hash_verification: bool = True,
    backend: RawStorageBackend | None = None,
) -> bytes:
    """Read a verified immutable vault archive without modifying it."""

    if not provenance.get("storage_path") or not provenance.get("sha256"):
        raise RawVaultError("Raw archive provenance does not include a vault storage path and SHA-256.")
    return (backend or LocalRawStorageBackend()).read(
        storage_path=provenance.get("storage_path"),
        expected_sha256=str(provenance.get("sha256")),
        expected_byte_size=int(provenance["byte_size"]) if provenance.get("byte_size") is not None else None,
        raw_archive_id=str(provenance.get("raw_archive_id") or provenance.get("sha256")),
        require_hash_verification=require_hash_verification,
    )
