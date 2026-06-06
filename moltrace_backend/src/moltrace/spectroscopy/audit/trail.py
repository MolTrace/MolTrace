"""Audit trail + GxP controls SUPPORTING 21 CFR Part 11 workflows (Prompt 12).

This module ships software *controls* that HELP a customer operate an analytical
system under 21 CFR Part 11 — a tamper-evident, cryptographically chained audit
trail, electronic-signature primitives designed per **21 CFR Part 11.50**
(signature manifestations) and **11.70** (signature/record linking), append-only
log sinks, periodic chain verification, a 7-year retention policy, and capture of
the exact model-weight checksums behind any AI-assisted result so it is
reproducible and traceable.

IMPORTANT — scope of the claim. These are *controls that support* 21 CFR Part 11;
they help customers meet it. MolTrace does **not** claim the product is itself
compliant with 21 CFR Part 11: full computerized-system validation (CSV), SOPs,
identity/access management, and the overall compliance determination remain the
customer's responsibility. No function here emits a string asserting the product
itself meets the rule.

Design
------
* :class:`AuditEntry` — one frozen, immutable record per audited operation. Each
  entry carries the SHA-256 of its input and output, all method parameters, the
  software and model-weight versions, the hash of the *previous* entry (chain of
  custody), and an HMAC-SHA256 ``signature`` keyed by an organisation secret.
* The chain: ``previous_entry_hash`` links every entry to the one before it, so
  insertion, deletion, or reordering breaks the chain; the keyed HMAC additionally
  makes any *content* edit detectable (and unforgeable without the secret key).
* :func:`with_audit` — a decorator that wraps any analysis function and writes an
  :class:`AuditEntry` to an append-only :class:`AuditLog`. Two log backends ship
  here (in-memory + append-only JSONL); a production deployment implements the
  same interface over PostgreSQL (an append-only table with row-level integrity:
  ``REVOKE UPDATE, DELETE`` + an INSERT-only trigger) or AWS QLDB.
* :func:`verify_chain` — periodic tamper detection by recomputing the SHA-256
  chain (and, with the key, the HMAC signatures).
* :func:`render_audit_report_text` / :func:`render_audit_report_html` — a
  deterministic, human-readable archival report; :func:`export_pdfa` renders it to
  PDF/A for a regulatory submission when an optional renderer is installed.

References
----------
* U.S. FDA. 21 CFR Part 11 — Electronic Records; Electronic Signatures (esp.
  §11.10 controls for closed systems, §11.50 signature manifestations, §11.70
  signature/record linking).
* U.S. FDA. *Data Integrity and Compliance With Drug CGMP — Q&A Guidance* (2018)
  — ALCOA+ attributes (Attributable, Legible, Contemporaneous, Original,
  Accurate, +Complete, Consistent, Enduring, Available).
"""

from __future__ import annotations

import abc
import functools
import hashlib
import hmac
import importlib.metadata
import inspect
import json
import math
import os
import warnings
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import UTC, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

try:  # numpy is a project dependency, but keep audit importable without it.
    import numpy as np
except Exception:  # pragma: no cover - numpy effectively always present
    np = None  # type: ignore[assignment]

__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "DEFAULT_RETENTION_YEARS",
    "GENESIS_HASH",
    "HMAC_KEY_ENV",
    "AuditConfigurationError",
    "AuditContextError",
    "AuditEntry",
    "AuditError",
    "AuditLog",
    "AuditRecorder",
    "AuthorizationError",
    "ChainBreak",
    "ChainIntegrityError",
    "ChainVerificationReport",
    "ElectronicSignature",
    "InMemoryAuditLog",
    "JsonlAuditLog",
    "ModelRegistry",
    "Operation",
    "PdfExportUnavailable",
    "RetentionPolicy",
    "SignatureMeaning",
    "MODEL_REGISTRY",
    "OPERATION_VOCABULARY",
    "assert_chain_integrity",
    "audit_context",
    "audited",
    "compute_signature",
    "configure_audit",
    "entry_from_dict",
    "entry_hash",
    "entry_to_dict",
    "export_pdfa",
    "get_default_recorder",
    "register_model_checksum",
    "register_model_weights",
    "render_audit_report_html",
    "render_audit_report_text",
    "sign_record",
    "static_key",
    "verify_chain",
    "verify_signature",
    "with_audit",
]

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
AUDIT_SCHEMA_VERSION = "1"
GENESIS_HASH = "0" * 64
DEFAULT_RETENTION_YEARS = 7
HMAC_KEY_ENV = "MOLTRACE_AUDIT_HMAC_KEY"

_DISCLAIMER = (
    "These controls are provided to SUPPORT 21 CFR Part 11 workflows (audit "
    "trail, electronic signatures, access control) and help customers meet "
    "21 CFR Part 11. Full computerized-system validation and the overall "
    "compliance determination remain the customer's responsibility."
)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class AuditError(RuntimeError):
    """Base class for audit-trail errors."""


class AuditConfigurationError(AuditError):
    """Raised when the audit trail is misconfigured (e.g. no signing key)."""


class AuditContextError(AuditError):
    """Raised when an audited operation runs without an attributable user."""


class AuthorizationError(AuditError):
    """Raised by an authorizer hook when a principal may not run an operation."""


class ChainIntegrityError(AuditError):
    """Raised by :func:`assert_chain_integrity` when the chain fails to verify."""


class PdfExportUnavailable(AuditError):
    """Raised when PDF/A export is requested without an installed renderer."""


# --------------------------------------------------------------------------- #
# Time helpers (real UTC clock; injectable for tests)
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _add_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:  # 29 Feb -> 28 Feb on a non-leap target year
        return dt.replace(year=dt.year + years, month=2, day=28)


# --------------------------------------------------------------------------- #
# Canonical content hashing + JSON serialisation
# --------------------------------------------------------------------------- #
def _feed(h: Any, obj: Any) -> None:
    """Type-tagged, length-prefixed streaming encode into a hash object.

    Deterministic across runs for the same value; handles numpy arrays (hashed by
    dtype + shape + raw bytes), datetimes, dataclasses, mappings, and sequences.
    """

    if obj is None:
        h.update(b"n;")
    elif isinstance(obj, bool):
        h.update(b"b1;" if obj else b"b0;")
    elif isinstance(obj, int):
        h.update(b"i" + str(obj).encode() + b";")
    elif isinstance(obj, float):
        h.update(b"f" + repr(obj).encode() + b";")
    elif isinstance(obj, complex):
        h.update(b"c" + repr(obj).encode() + b";")
    elif isinstance(obj, str):
        data = obj.encode("utf-8")
        h.update(b"s" + str(len(data)).encode() + b":" + data)
    elif isinstance(obj, (bytes, bytearray, memoryview)):
        data = bytes(obj)
        h.update(b"B" + str(len(data)).encode() + b":" + data)
    elif isinstance(obj, datetime):
        _feed(h, "dt:" + _iso(obj))
    elif np is not None and isinstance(obj, np.generic):
        _feed(h, obj.item())
    elif np is not None and isinstance(obj, np.ndarray):
        if obj.dtype == object:
            h.update(b"ao" + repr(obj.shape).encode() + b":")
            for element in obj.ravel(order="C").tolist():
                _feed(h, element)
        else:
            arr = np.ascontiguousarray(obj)
            h.update(b"a" + arr.dtype.str.encode() + b"|" + repr(arr.shape).encode() + b":")
            h.update(arr.tobytes())
    elif isinstance(obj, Mapping):
        h.update(b"M{")
        for key in sorted(obj.keys(), key=lambda k: str(k)):
            _feed(h, str(key))
            h.update(b"=")
            _feed(h, obj[key])
            h.update(b";")
        h.update(b"}")
    elif isinstance(obj, (list, tuple)):
        h.update(b"L[" + str(len(obj)).encode() + b":")
        for element in obj:
            _feed(h, element)
        h.update(b"]")
    elif isinstance(obj, (set, frozenset)):
        h.update(b"S[")
        for digest in sorted(_content_sha256(element) for element in obj):
            h.update(digest.encode() + b";")
        h.update(b"]")
    elif isinstance(obj, Enum):
        _feed(h, obj.value)
    elif is_dataclass(obj) and not isinstance(obj, type):
        h.update(b"D:" + type(obj).__qualname__.encode() + b"{")
        for f in fields(obj):
            _feed(h, f.name)
            h.update(b"=")
            _feed(h, getattr(obj, f.name))
            h.update(b";")
        h.update(b"}")
    elif hasattr(obj, "__dict__"):
        h.update(b"O:" + type(obj).__qualname__.encode() + b"{")
        for key in sorted(vars(obj).keys()):
            _feed(h, key)
            h.update(b"=")
            _feed(h, vars(obj)[key])
            h.update(b";")
        h.update(b"}")
    else:
        h.update(b"R:" + repr(obj).encode() + b";")


def _content_sha256(obj: Any) -> str:
    """SHA-256 hex digest of the canonical content of ``obj`` (spectra included)."""

    digest = hashlib.sha256()
    _feed(digest, obj)
    return digest.hexdigest()


def _to_jsonable(obj: Any) -> Any:
    """Convert ``obj`` to a JSON-native, deterministic, idempotent structure.

    Bulk arrays/bytes are reduced to a content-hash reference (never inlined), so
    a stored entry stays compact while remaining integrity-checkable.
    """

    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    if isinstance(obj, complex):
        return {"__complex__": [obj.real, obj.imag]}
    if isinstance(obj, (bytes, bytearray, memoryview)):
        data = bytes(obj)
        return {"__bytes_sha256__": _content_sha256(data), "length": len(data)}
    if isinstance(obj, datetime):
        return _iso(obj)
    if isinstance(obj, Enum):
        return obj.value
    if np is not None and isinstance(obj, np.generic):
        return _to_jsonable(obj.item())
    if np is not None and isinstance(obj, np.ndarray):
        return {
            "__ndarray_sha256__": _content_sha256(obj),
            "dtype": obj.dtype.str,
            "shape": list(obj.shape),
        }
    if isinstance(obj, Mapping):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        encoded = [_to_jsonable(v) for v in obj]
        return {
            "__set__": sorted(encoded, key=lambda v: json.dumps(v, sort_keys=True, default=str))
        }
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if hasattr(obj, "__dict__"):
        return {
            "__type__": type(obj).__qualname__,
            **{k: _to_jsonable(v) for k, v in vars(obj).items()},
        }
    return repr(obj)


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(
        _to_jsonable(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# AuditEntry + hashing/signing
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AuditEntry:
    """One immutable audit record. All fields participate in the signed payload
    except :attr:`signature` itself; :attr:`previous_entry_hash` chains custody."""

    timestamp_utc: datetime
    user_id: str
    operation: str
    input_hash: str
    parameters: dict
    result_hash: str
    software_version: str
    model_versions: dict
    previous_entry_hash: str
    signature: str


# Fields that are HMAC-signed, in a fixed order (everything except ``signature``).
_SIGNED_FIELDS = (
    "timestamp_utc",
    "user_id",
    "operation",
    "input_hash",
    "parameters",
    "result_hash",
    "software_version",
    "model_versions",
    "previous_entry_hash",
)


def _payload_bytes(entry: AuditEntry) -> bytes:
    return _canonical_json({name: getattr(entry, name) for name in _SIGNED_FIELDS})


def compute_signature(entry: AuditEntry, key: bytes) -> str:
    """HMAC-SHA256 of the entry's canonical payload, keyed by the org secret."""

    return hmac.new(key, _payload_bytes(entry), hashlib.sha256).hexdigest()


def entry_hash(entry: AuditEntry) -> str:
    """SHA-256 of the payload + signature; the next entry's ``previous_entry_hash``.

    Binding the signature into the chain means tampering with either the content
    or the signature breaks every downstream link.
    """

    return hashlib.sha256(_payload_bytes(entry) + b"|sig:" + entry.signature.encode()).hexdigest()


def entry_to_dict(entry: AuditEntry) -> dict:
    out = {name: _to_jsonable(getattr(entry, name)) for name in _SIGNED_FIELDS}
    out["signature"] = entry.signature
    return out


def entry_from_dict(data: Mapping[str, Any]) -> AuditEntry:
    return AuditEntry(
        timestamp_utc=_parse_iso(data["timestamp_utc"]),
        user_id=data["user_id"],
        operation=data["operation"],
        input_hash=data["input_hash"],
        parameters=dict(data["parameters"]),
        result_hash=data["result_hash"],
        software_version=data["software_version"],
        model_versions=dict(data["model_versions"]),
        previous_entry_hash=data["previous_entry_hash"],
        signature=data["signature"],
    )


# --------------------------------------------------------------------------- #
# Model-weight checksum registry (Prompt 6 NMRNet + Prompt 11 JTF-Net, ...)
# --------------------------------------------------------------------------- #
class ModelRegistry:
    """Records the SHA-256 of each AI model's weights so an AI-assisted result is
    reproducible and traceable. The decorator snapshots this into every entry's
    ``model_versions``."""

    def __init__(self) -> None:
        self._checksums: dict[str, str] = {}
        self._path_cache: dict[str, tuple[str, int, int]] = {}

    def register(self, name: str, checksum: str) -> None:
        self._checksums[str(name)] = str(checksum)

    def register_weights(self, name: str, path: str | Path) -> str:
        p = Path(path)
        stat = p.stat()
        cache_key = (str(p.resolve()), stat.st_size, stat.st_mtime_ns)
        if self._path_cache.get(name) == cache_key and name in self._checksums:
            return self._checksums[name]
        digest = _sha256_file(p)
        self._checksums[name] = digest
        self._path_cache[name] = cache_key
        return digest

    def snapshot(self) -> dict[str, str]:
        return dict(sorted(self._checksums.items()))

    def clear(self) -> None:
        self._checksums.clear()
        self._path_cache.clear()


MODEL_REGISTRY = ModelRegistry()


def register_model_checksum(name: str, checksum: str) -> None:
    """Register a precomputed model-weight checksum (no file I/O)."""

    MODEL_REGISTRY.register(name, checksum)


def register_model_weights(name: str, path: str | Path) -> str:
    """Hash a weights file (mtime/size-cached) and register it; returns the hex."""

    return MODEL_REGISTRY.register_weights(name, path)


def _default_software_version() -> str:
    for dist in ("nmrcheck", "moltrace"):
        try:
            return f"{dist}/{importlib.metadata.version(dist)}"
        except importlib.metadata.PackageNotFoundError:
            continue
    return "unknown"


# --------------------------------------------------------------------------- #
# Secret-key providers
# --------------------------------------------------------------------------- #
def static_key(key: bytes | str) -> Callable[[], bytes]:
    """A key provider returning a fixed secret (tests, or in-process config)."""

    material = key.encode("utf-8") if isinstance(key, str) else bytes(key)
    if not material:
        raise AuditConfigurationError("audit HMAC key must be non-empty")
    return lambda: material


def _env_key() -> bytes:
    raw = os.environ.get(HMAC_KEY_ENV)
    if not raw:
        raise AuditConfigurationError(
            f"audit signing key not configured: set ${HMAC_KEY_ENV} to a "
            "high-entropy organisation secret (optionally as 'hex:<hexkey>')"
        )
    if raw.startswith("hex:"):
        return bytes.fromhex(raw[4:])
    return raw.encode("utf-8")


# --------------------------------------------------------------------------- #
# Electronic signatures — designed per 21 CFR Part 11.50 / 11.70
# --------------------------------------------------------------------------- #
class SignatureMeaning(StrEnum):
    """The meaning a signer attributes to a signing act (§11.50(a)(3))."""

    AUTHORSHIP = "authorship"
    REVIEW = "review"
    APPROVAL = "approval"
    RESPONSIBILITY = "responsibility"


@dataclass(frozen=True)
class ElectronicSignature:
    """An e-signature bound to one audit record.

    §11.50 — the manifestation carries the signer's printed name, the date/time,
    and the meaning. §11.70 — ``record_hash`` + the keyed HMAC bind the signature
    to *this* record so it cannot be excised, copied, or transferred to falsify
    another record by ordinary means.
    """

    signer_id: str
    signer_name: str
    signed_at_utc: datetime
    meaning: SignatureMeaning
    record_hash: str
    signature: str
    manifestation: str


def _signature_payload(
    signer_id: str,
    signer_name: str,
    signed_at: datetime,
    meaning: SignatureMeaning,
    record_hash: str,
) -> bytes:
    return _canonical_json(
        {
            "signer_id": signer_id,
            "signer_name": signer_name,
            "signed_at_utc": signed_at,
            "meaning": meaning.value,
            "record_hash": record_hash,
        }
    )


def sign_record(
    record_hash: str,
    *,
    signer_id: str,
    signer_name: str,
    meaning: SignatureMeaning,
    key: bytes,
    signed_at: datetime | None = None,
) -> ElectronicSignature:
    """Create an :class:`ElectronicSignature` bound to ``record_hash``."""

    if not signer_id or not signer_name:
        raise AuditConfigurationError("electronic signature requires signer_id and signer_name")
    meaning = SignatureMeaning(meaning)
    when = signed_at or _now()
    payload = _signature_payload(signer_id, signer_name, when, meaning, record_hash)
    signature = hmac.new(key, payload, hashlib.sha256).hexdigest()
    manifestation = (
        f"Electronically signed by {signer_name} (user {signer_id}); "
        f"meaning: {meaning.value.upper()}; at {_iso(when)}; "
        f"record {record_hash[:16]}..."
    )
    return ElectronicSignature(
        signer_id=signer_id,
        signer_name=signer_name,
        signed_at_utc=when,
        meaning=meaning,
        record_hash=record_hash,
        signature=signature,
        manifestation=manifestation,
    )


def verify_signature(signature: ElectronicSignature, *, key: bytes) -> bool:
    """Constant-time check that ``signature`` was made with ``key`` for its record."""

    expected = hmac.new(
        key,
        _signature_payload(
            signature.signer_id,
            signature.signer_name,
            signature.signed_at_utc,
            signature.meaning,
            signature.record_hash,
        ),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature.signature)


# --------------------------------------------------------------------------- #
# Append-only log backends
# --------------------------------------------------------------------------- #
class AuditLog(abc.ABC):
    """Append-only audit sink. Production backends (PostgreSQL append-only table
    with row-level integrity, or AWS QLDB) implement this same interface."""

    @abc.abstractmethod
    def append(self, entry: AuditEntry) -> None: ...

    @abc.abstractmethod
    def __iter__(self) -> Iterator[AuditEntry]: ...

    @abc.abstractmethod
    def __len__(self) -> int: ...

    def latest_entry_hash(self) -> str:
        last: AuditEntry | None = None
        for last in self:  # noqa: B007 - we want the final element
            pass
        return entry_hash(last) if last is not None else GENESIS_HASH


class InMemoryAuditLog(AuditLog):
    """Volatile audit log (tests, ephemeral runs). NOT durable storage."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def append(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    def __iter__(self) -> Iterator[AuditEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def latest_entry_hash(self) -> str:
        return entry_hash(self._entries[-1]) if self._entries else GENESIS_HASH


class JsonlAuditLog(AuditLog):
    """Durable, append-only JSON-Lines log: one canonical entry per line.

    Open the file in append mode only — never truncate or rewrite. Pair with a
    write-once-read-many (WORM) filesystem / object-lock bucket for an enduring,
    tamper-resistant archive (ALCOA+ "Enduring").
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._count = 0
        self._last_hash = GENESIS_HASH
        if self.path.exists():
            last: AuditEntry | None = None
            for last in self._read():  # noqa: B007
                self._count += 1
            if last is not None:
                self._last_hash = entry_hash(last)

    def _read(self) -> Iterator[AuditEntry]:
        with open(self.path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield entry_from_dict(json.loads(line))

    def append(self, entry: AuditEntry) -> None:
        line = json.dumps(entry_to_dict(entry), sort_keys=True, ensure_ascii=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        self._count += 1
        self._last_hash = entry_hash(entry)

    def __iter__(self) -> Iterator[AuditEntry]:
        return self._read()

    def __len__(self) -> int:
        return self._count

    def latest_entry_hash(self) -> str:
        return self._last_hash


# --------------------------------------------------------------------------- #
# Retention policy (7-year minimum, configurable)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetentionPolicy:
    """A retention *floor* (default 7 years). This is a configurable minimum, not
    a legal determination: confirm the predicate-rule retention for your records."""

    minimum_years: int = DEFAULT_RETENTION_YEARS

    def retention_floor(self, entry: AuditEntry) -> datetime:
        return _add_years(entry.timestamp_utc, self.minimum_years)

    def is_destroyable(self, entry: AuditEntry, as_of: datetime) -> bool:
        return as_of >= self.retention_floor(entry)


# --------------------------------------------------------------------------- #
# Recorder + global configuration
# --------------------------------------------------------------------------- #
@dataclass
class AuditRecorder:
    """Binds a log, signing key, versions, clock, and an optional authorizer, and
    writes signed, chained :class:`AuditEntry` rows."""

    log: AuditLog
    key_provider: Callable[[], bytes] = _env_key
    software_version: str = field(default_factory=_default_software_version)
    model_registry: ModelRegistry = field(default_factory=lambda: MODEL_REGISTRY)
    clock: Callable[[], datetime] = _now
    authorizer: Callable[[str, str], None] | None = None
    retention: RetentionPolicy = field(default_factory=RetentionPolicy)

    def _key(self) -> bytes:
        key = self.key_provider()
        if not key:
            raise AuditConfigurationError("audit signing key provider returned an empty key")
        return key

    def record(
        self,
        *,
        operation: str,
        user_id: str,
        input_obj: Any,
        result_obj: Any,
        parameters: Mapping[str, Any] | None = None,
    ) -> AuditEntry:
        if not user_id:
            raise AuditContextError("an audit entry requires an attributable user_id")
        if self.authorizer is not None:
            self.authorizer(user_id, operation)
        unsigned = AuditEntry(
            timestamp_utc=self.clock(),
            user_id=user_id,
            operation=operation,
            input_hash=_content_sha256(input_obj),
            parameters=_to_jsonable(dict(parameters or {})),
            result_hash=_content_sha256(result_obj),
            software_version=self.software_version,
            model_versions=self.model_registry.snapshot(),
            previous_entry_hash=self.log.latest_entry_hash(),
            signature="",
        )
        entry = replace(unsigned, signature=compute_signature(unsigned, self._key()))
        self.log.append(entry)
        return entry


_DEFAULT_RECORDER: AuditRecorder | None = None


def configure_audit(
    log: AuditLog,
    *,
    key_provider: Callable[[], bytes] | None = None,
    software_version: str | None = None,
    model_registry: ModelRegistry | None = None,
    clock: Callable[[], datetime] | None = None,
    authorizer: Callable[[str, str], None] | None = None,
    retention: RetentionPolicy | None = None,
) -> AuditRecorder:
    """Install the process-wide default recorder used by :func:`with_audit`."""

    global _DEFAULT_RECORDER
    kwargs: dict[str, Any] = {"log": log}
    if key_provider is not None:
        kwargs["key_provider"] = key_provider
    if software_version is not None:
        kwargs["software_version"] = software_version
    if model_registry is not None:
        kwargs["model_registry"] = model_registry
    if clock is not None:
        kwargs["clock"] = clock
    if authorizer is not None:
        kwargs["authorizer"] = authorizer
    if retention is not None:
        kwargs["retention"] = retention
    _DEFAULT_RECORDER = AuditRecorder(**kwargs)
    return _DEFAULT_RECORDER


def get_default_recorder() -> AuditRecorder | None:
    return _DEFAULT_RECORDER


def reset_default_recorder() -> None:
    """Clear the global recorder (primarily for tests)."""

    global _DEFAULT_RECORDER
    _DEFAULT_RECORDER = None


# --------------------------------------------------------------------------- #
# Operator context (who is performing the operation)
# --------------------------------------------------------------------------- #
_current_user: ContextVar[str | None] = ContextVar("moltrace_audit_user", default=None)
_current_signer_name: ContextVar[str | None] = ContextVar(
    "moltrace_audit_signer_name", default=None
)


@contextmanager
def audit_context(user_id: str, *, signer_name: str | None = None):
    """Bind the authenticated operator for audited calls in this context.

    In production the API/auth middleware sets this from the verified session;
    auditing without an attributable user is rejected (§11.10(e))."""

    user_token = _current_user.set(user_id)
    name_token = _current_signer_name.set(signer_name)
    try:
        yield
    finally:
        _current_user.reset(user_token)
        _current_signer_name.reset(name_token)


def current_user() -> str | None:
    return _current_user.get()


# --------------------------------------------------------------------------- #
# The decorator
# --------------------------------------------------------------------------- #
_warned: set[str] = set()


def _warn_once(func: Callable[..., Any], message: str) -> None:
    key = getattr(func, "__qualname__", repr(func))
    if key not in _warned:
        _warned.add(key)
        warnings.warn(f"[moltrace.audit] {key}: {message}", RuntimeWarning, stacklevel=3)


def _split_call(
    bound: inspect.BoundArguments, data_params: tuple[str, ...] | None
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    if data_params:
        inputs = tuple(bound.arguments.get(name) for name in data_params)
        params = {k: v for k, v in bound.arguments.items() if k not in set(data_params)}
    else:
        inputs = tuple(bound.arguments.values())
        params = dict(bound.arguments)
    return inputs, params


def with_audit(
    operation_name: str,
    *,
    recorder: AuditRecorder | None = None,
    data_params: tuple[str, ...] | None = None,
    capture_result: bool = True,
):
    """Decorator wrapping any analysis function; writes an :class:`AuditEntry` to
    the append-only log on each call.

    The wrapped call's inputs are hashed into ``input_hash`` (``data_params`` may
    name the spectrum argument(s) to separate them from the recorded method
    ``parameters``); the return value is hashed into ``result_hash``; the active
    model-weight checksums are snapshotted into ``model_versions``. Both
    successful and failed operations are recorded.

    Safe to apply broadly: when no recorder is configured the wrapper passes
    through (warning once), so applying it across the Prompt 1-11 functions does
    not change behaviour until auditing is switched on in production.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            rec = recorder or _DEFAULT_RECORDER
            if rec is None:
                _warn_once(func, "audit not configured; running UN-AUDITED")
                return func(*args, **kwargs)

            user = _current_user.get()
            if not user:
                raise AuditContextError(
                    f"operation {operation_name!r} requires an authenticated user; "
                    "wrap the call in audit_context(user_id=...)"
                )

            try:
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
                inputs, params = _split_call(bound, data_params)
            except TypeError:
                inputs, params = (args, dict(enumerate(args))), {"kwargs": kwargs}

            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                rec.record(
                    operation=operation_name,
                    user_id=user,
                    input_obj=inputs,
                    result_obj={"error_type": type(exc).__name__, "error": str(exc)},
                    parameters={**params, "audit_event": "operation_error"},
                )
                raise
            rec.record(
                operation=operation_name,
                user_id=user,
                input_obj=inputs,
                result_obj=result if capture_result else None,
                parameters=params,
            )
            return result

        wrapper.__audited_operation__ = operation_name  # type: ignore[attr-defined]
        return wrapper

    return decorator


def audited(
    func: Callable[..., Any], operation_name: str, **options: Any
) -> Callable[..., Any]:
    """Programmatic form of :func:`with_audit` (wrap an existing function)."""

    return with_audit(operation_name, **options)(func)


# --------------------------------------------------------------------------- #
# Chain verification (periodic tamper detection)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ChainBreak:
    index: int
    reason: str
    detail: str


@dataclass(frozen=True)
class ChainVerificationReport:
    ok: bool
    entries_checked: int
    signature_verified: bool
    breaks: tuple[ChainBreak, ...]
    verified_at_utc: datetime

    @property
    def first_broken_index(self) -> int | None:
        return self.breaks[0].index if self.breaks else None


def verify_chain(
    log: AuditLog, *, key: bytes | None = None, verified_at: datetime | None = None
) -> ChainVerificationReport:
    """Recompute the SHA-256 chain (and, with ``key``, the HMAC signatures).

    The hash-chain check is keyless and detects insertion / deletion / reordering
    and naive edits; supplying the org key additionally verifies authenticity and
    detects any content tampering that recomputed the downstream chain.
    """

    expected_prev = GENESIS_HASH
    breaks: list[ChainBreak] = []
    count = 0
    for index, entry in enumerate(log):
        count += 1
        if entry.previous_entry_hash != expected_prev:
            breaks.append(
                ChainBreak(index, "chain_link", "previous_entry_hash does not match prior entry")
            )
        if key is not None:
            expected_sig = compute_signature(entry, key)
            if not hmac.compare_digest(expected_sig, entry.signature):
                breaks.append(
                    ChainBreak(index, "signature", "HMAC mismatch — content altered or wrong key")
                )
        expected_prev = entry_hash(entry)
    return ChainVerificationReport(
        ok=not breaks,
        entries_checked=count,
        signature_verified=key is not None,
        breaks=tuple(breaks),
        verified_at_utc=verified_at or _now(),
    )


def assert_chain_integrity(log: AuditLog, *, key: bytes | None = None) -> ChainVerificationReport:
    """Verify the chain and raise :class:`ChainIntegrityError` if it fails."""

    report = verify_chain(log, key=key)
    if not report.ok:
        first = report.breaks[0]
        raise ChainIntegrityError(
            f"audit chain failed at entry {first.index}: {first.reason} — {first.detail} "
            f"({len(report.breaks)} break(s) across {report.entries_checked} entries)"
        )
    return report


# --------------------------------------------------------------------------- #
# Human-readable report (PDF/A-ready) + optional PDF/A export
# --------------------------------------------------------------------------- #
_REPORT_TITLE = "MolTrace Audit Trail Report — controls supporting 21 CFR Part 11 workflows"


def _short(value: str, width: int = 16) -> str:
    return value[:width] + "..." if len(value) > width else value


def render_audit_report_text(
    log: AuditLog,
    *,
    key: bytes | None = None,
    signatures: list[ElectronicSignature] | None = None,
    generated_at: datetime | None = None,
    retention: RetentionPolicy | None = None,
) -> str:
    """Deterministic plain-text archival report (given ``generated_at``)."""

    entries = list(log)
    retention = retention or RetentionPolicy()
    report = verify_chain(log, key=key, verified_at=generated_at or _now())
    software = sorted({e.software_version for e in entries}) or ["(none)"]
    models: dict[str, str] = {}
    for e in entries:
        models.update(e.model_versions)

    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(_REPORT_TITLE)
    lines.append("=" * 78)
    lines.append(_DISCLAIMER)
    lines.append("")
    lines.append(f"Generated:           {_iso(report.verified_at_utc)}")
    lines.append(f"Audit schema:        v{AUDIT_SCHEMA_VERSION}")
    lines.append(f"Entries:             {report.entries_checked}")
    lines.append(f"Software versions:   {', '.join(software)}")
    lines.append(
        "Model weight SHA-256: "
        + (", ".join(f"{k}={_short(v)}" for k, v in sorted(models.items())) or "(none captured)")
    )
    verdict = "VERIFIED" if report.ok else "FAILED"
    sig_note = (
        "with signatures" if report.signature_verified else "hash-chain only (key not supplied)"
    )
    lines.append(f"Chain integrity:     {verdict} ({sig_note})")
    lines.append(
        f"Retention floor:     {retention.minimum_years} year(s) from each entry timestamp"
    )
    if not report.ok:
        for brk in report.breaks:
            lines.append(f"  ! break @ entry {brk.index}: {brk.reason} — {brk.detail}")
    lines.append("")
    lines.append("-" * 78)
    lines.append("Entries (chronological)")
    lines.append("-" * 78)
    for index, e in enumerate(entries):
        lines.append(
            f"[{index}] {_iso(e.timestamp_utc)}  user={e.user_id}  op={e.operation}"
        )
        lines.append(f"     input={_short(e.input_hash)}  result={_short(e.result_hash)}")
        lines.append(
            f"     prev={_short(e.previous_entry_hash)}  sig={_short(e.signature)}  "
            f"sw={e.software_version}"
        )
        if e.model_versions:
            lines.append(
                "     models: "
                + ", ".join(f"{k}={_short(v)}" for k, v in sorted(e.model_versions.items()))
            )
        if e.parameters:
            params = json.dumps(e.parameters, sort_keys=True, ensure_ascii=False)
            lines.append(f"     params: {_short(params, 200)}")
    if signatures:
        lines.append("")
        lines.append("-" * 78)
        lines.append("Electronic signatures (21 CFR Part 11.50 manifestations)")
        lines.append("-" * 78)
        for sig in signatures:
            lines.append(f"  - {sig.manifestation}")
    lines.append("")
    lines.append("End of report.")
    return "\n".join(lines)


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_audit_report_html(
    log: AuditLog,
    *,
    key: bytes | None = None,
    signatures: list[ElectronicSignature] | None = None,
    generated_at: datetime | None = None,
    retention: RetentionPolicy | None = None,
) -> str:
    """Self-contained HTML render of the report (archival master for PDF/A)."""

    text = render_audit_report_text(
        log, key=key, signatures=signatures, generated_at=generated_at, retention=retention
    )
    generated = _iso(generated_at or _now())
    body = _html_escape(text)
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\"/>\n"
        f"<meta name=\"title\" content=\"{_html_escape(_REPORT_TITLE)}\"/>\n"
        f"<meta name=\"dcterms.created\" content=\"{generated}\"/>\n"
        "<meta name=\"generator\" content=\"moltrace.spectroscopy.audit\"/>\n"
        f"<title>{_html_escape(_REPORT_TITLE)}</title>\n"
        "</head>\n<body>\n"
        f"<pre>{body}</pre>\n"
        "</body>\n</html>\n"
    )


def export_pdfa(
    log: AuditLog,
    path: str | Path,
    *,
    key: bytes | None = None,
    signatures: list[ElectronicSignature] | None = None,
    generated_at: datetime | None = None,
    retention: RetentionPolicy | None = None,
) -> Path:
    """Render the audit report to a PDF targeting PDF/A-2b for submission.

    Requires an optional renderer (``reportlab``); raises
    :class:`PdfExportUnavailable` if it is not installed — the always-available
    archival master is :func:`render_audit_report_html`. PDF/A *conformance*
    should be validated (e.g. veraPDF) as part of the customer's CSV.
    """

    try:  # pragma: no cover - optional dependency, not installed in CI
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover
        raise PdfExportUnavailable(
            "PDF/A export needs the optional 'reportlab' renderer "
            "(pip install reportlab); the HTML master from render_audit_report_html "
            "is always available."
        ) from exc

    # pragma: no cover - exercised only when reportlab is installed
    text = render_audit_report_text(  # pragma: no cover
        log, key=key, signatures=signatures, generated_at=generated_at, retention=retention
    )
    out = Path(path)  # pragma: no cover
    out.parent.mkdir(parents=True, exist_ok=True)  # pragma: no cover
    pdf = canvas.Canvas(str(out), pagesize=letter)  # pragma: no cover
    pdf.setTitle(_REPORT_TITLE)  # pragma: no cover
    pdf.setProducer("moltrace.spectroscopy.audit (targets PDF/A-2b)")  # pragma: no cover
    width, height = letter  # pragma: no cover
    y = height - 54  # pragma: no cover
    for line in text.splitlines():  # pragma: no cover
        if y < 54:
            pdf.showPage()
            y = height - 54
        pdf.drawString(54, y, line[:110])
        y -= 12
    pdf.save()  # pragma: no cover
    return out  # pragma: no cover


# --------------------------------------------------------------------------- #
# Operation vocabulary — the rollout manifest for Prompts 1-11
# --------------------------------------------------------------------------- #
class Operation:
    """Canonical ``operation`` strings for the analysis surfaces of Prompts 1-11.

    Apply :func:`with_audit` at the service boundary (where the authenticated user
    is known) using these names. Mapping to the public functions:

    * ``preprocess``         — Prompt 1-2 FID load / phase+baseline / preprocess
    * ``peak_pick``          — Prompt 3 GSD peak picking / deconvolution
    * ``multiplet_analyze``  — Prompt 4 multiplet / J-coupling analysis
    * ``integrate``          — Prompt 5 region integration
    * ``predict_shifts``     — Prompt 6 NMRNet / HOSE shift prediction
    * ``verify_structure``   — Prompt 7 ASV structure verification
    * ``spectrum_retrieve``  — Prompt 8 similarity retrieval
    * ``qnmr_purity``        — Prompt 9 quantitative-NMR purity
    * ``classify_peaks``     — Prompt 10 solvent / impurity classification
    * ``nus_reconstruct`` / ``nus_assess_quality`` — Prompt 11 NUS reconstruction
    * ``audit_chain_verify`` — periodic self-audit of the chain
    """

    PREPROCESS = "preprocess"
    PEAK_PICK = "peak_pick"
    MULTIPLET_ANALYZE = "multiplet_analyze"
    INTEGRATE = "integrate"
    PREDICT_SHIFTS = "predict_shifts"
    VERIFY_STRUCTURE = "verify_structure"
    SPECTRUM_RETRIEVE = "spectrum_retrieve"
    QNMR_PURITY = "qnmr_purity"
    CLASSIFY_PEAKS = "classify_peaks"
    NUS_RECONSTRUCT = "nus_reconstruct"
    NUS_ASSESS_QUALITY = "nus_assess_quality"
    AUDIT_CHAIN_VERIFY = "audit_chain_verify"


OPERATION_VOCABULARY = frozenset(
    value
    for name, value in vars(Operation).items()
    if not name.startswith("_") and isinstance(value, str)
)
