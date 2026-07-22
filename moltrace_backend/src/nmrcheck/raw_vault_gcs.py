"""Google Cloud Storage backend for the immutable raw-NMR archive vault.

Cloud Run's filesystem is ephemeral, so ``LocalRawStorageBackend`` cannot hold the
write-once raw-FID vault in a serverless deployment. This backend implements the same
:class:`~nmrcheck.raw_vault.RawStorageBackend` contract against GCS and preserves every
ALCOA+ invariant the local backend encodes:

===========================  ===============================================================
Local invariant              GCS mechanism
===========================  ===============================================================
atomic write                 a GCS object write is atomic -- no temp-file/rename dance
write-once, never overwrite  ``if_generation_match=0`` precondition (create-only, race-safe)
reuse existing + verify      on precondition failure the stored object's SHA-256 is checked
immutability                 bucket retention policy / object versioning (durable WORM)
strict-immutable fail-closed the freshly-written object is deleted, then ``RawVaultError``
post-write hash verify       the stored bytes are re-read and re-hashed after upload
verify-before-read           :meth:`read` refuses to return bytes unless ``report.ok``
===========================  ===============================================================

``google-cloud-storage`` is an OPTIONAL dependency (``nmrcheck[gcs]``) and is imported
lazily, so the package, its tests, and the local backend all run without it installed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .raw_vault import (
    RAW_ARCHIVE_HASH_MISMATCH_MESSAGE,
    RawArchiveIntegrityReport,
    RawStorageBackend,
    RawVaultError,
)

__all__ = ["GCSRawStorageBackend", "parse_gs_uri"]

_NO_RETENTION_MESSAGE = (
    "Raw archive stored without bucket retention or object versioning; immutability rests "
    "only on create-only writes. Enable a retention policy or versioning on the bucket."
)


def parse_gs_uri(uri: str) -> tuple[str, str] | None:
    """Split ``gs://bucket/object/key`` into ``(bucket, key)``; ``None`` if not a gs URI."""
    text = str(uri or "")
    if not text.startswith("gs://"):
        return None
    remainder = text[len("gs://") :]
    bucket, _, key = remainder.partition("/")
    if not bucket or not key:
        return None
    return bucket, key


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class GCSRawStorageBackend(RawStorageBackend):
    """Immutable raw-archive vault backed by a Cloud Storage bucket."""

    name = "gcs_raw_vault"

    def __init__(
        self,
        bucket: str,
        *,
        client: Any | None = None,
        prefix: str = "",
    ) -> None:
        if not bucket:
            raise RawVaultError("GCSRawStorageBackend requires a bucket name.")
        self.bucket_name = str(bucket)
        # ``prefix`` lets several environments share one bucket; normalised to "" or "x/".
        self.prefix = f"{str(prefix).strip('/')}/" if str(prefix).strip("/") else ""
        self._client = client

    # ---------------------------------------------------------------- plumbing

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google.cloud import storage  # noqa: PLC0415 - optional dependency
            except ImportError as exc:  # pragma: no cover - exercised only without the extra
                raise RawVaultError(
                    "The GCS raw vault requires the optional 'google-cloud-storage' package "
                    "(install nmrcheck[gcs])."
                ) from exc
            self._client = storage.Client()
        return self._client

    def _bucket(self) -> Any:
        return self.client.bucket(self.bucket_name)

    def _object_key(self, *, sha256: str, filename: str) -> str:
        return f"{self.prefix}{sha256}/{filename}"

    def path_or_uri(self, *, sha256: str, filename: str) -> str:
        return f"gs://{self.bucket_name}/{self._object_key(sha256=sha256, filename=filename)}"

    def _resolve_blob(
        self,
        *,
        storage_path: str | Path | None,
        raw_archive_id: str | None,
    ) -> Any | None:
        """Locate a blob from an explicit ``gs://`` path, a bare key, or a sha256 id.

        Mirrors ``_resolve_integrity_path``: when only the archive id (its SHA-256) is
        known, the single object under ``{sha256}/`` is used.
        """
        if storage_path:
            text = str(storage_path)
            parsed = parse_gs_uri(text)
            if parsed is not None:
                bucket_name, key = parsed
                return self.client.bucket(bucket_name).blob(key)
            # A bare object key (no scheme) is treated as relative to this bucket.
            if not text.startswith("/"):
                return self._bucket().blob(text)
            return None
        if not raw_archive_id:
            return None
        candidates = [
            blob
            for blob in self.client.list_blobs(
                self.bucket_name, prefix=f"{self.prefix}{raw_archive_id}/"
            )
            if not Path(str(blob.name)).name.startswith(".")
        ]
        return candidates[0] if len(candidates) == 1 else None

    def _apply_immutability(self, blob: Any, warnings: list[str], *, strict: bool) -> bool:
        """Confirm durable WORM protection (retention policy or versioning) on the bucket.

        The local backend chmods the object read-only; the GCS analogue is bucket-level
        retention/versioning. Same contract: return whether the object is protected, warn
        when it is not, and raise under ``strict`` so the caller can fail closed.
        """
        try:
            bucket = blob.bucket
            reload_bucket = getattr(bucket, "reload", None)
            if callable(reload_bucket):
                reload_bucket()
            protected = bool(getattr(bucket, "retention_period", None)) or bool(
                getattr(bucket, "versioning_enabled", False)
            )
        except Exception:  # pragma: no cover - defensive: treat probe failure as unprotected
            protected = False
        if protected:
            return True
        warnings.append(_NO_RETENTION_MESSAGE)
        if strict:
            raise RawVaultError(_NO_RETENTION_MESSAGE)
        return False

    # ------------------------------------------------------------------- save

    def save(
        self,
        *,
        content: bytes,
        sha256: str,
        filename: str,
        immutable: bool = True,
        warnings: list[str] | None = None,
        strict_immutable: bool = False,
    ) -> dict[str, Any]:
        warning_list = warnings if warnings is not None else []
        key = self._object_key(sha256=sha256, filename=filename)
        blob = self._bucket().blob(key)
        blob.metadata = {"sha256": sha256}
        reused = False
        try:
            # ``if_generation_match=0`` == "create only if absent": atomic and race-safe,
            # so a concurrent ingest can never overwrite an existing immutable object.
            blob.upload_from_string(
                content,
                content_type="application/octet-stream",
                if_generation_match=0,
            )
        except Exception as exc:
            if not _is_precondition_failure(exc):
                raise
            # The object already exists -- verify it byte-for-byte, then reuse it.
            existing = blob.download_as_bytes()
            if _sha256_bytes(existing) != str(sha256):
                raise RawVaultError(RAW_ARCHIVE_HASH_MISMATCH_MESSAGE) from exc
            warning_list.append(
                "Raw archive already existed in the vault; existing immutable object was reused."
            )
            reused = True

        try:
            read_only = (
                self._apply_immutability(blob, warning_list, strict=strict_immutable)
                if immutable
                else False
            )
        except RawVaultError:
            # Strict mode: never leave a freshly-written, unprotected object behind that a
            # later same-hash ingest would accept through the reuse path above.
            if not reused:
                try:
                    blob.delete()
                except Exception:  # pragma: no cover - best-effort cleanup
                    pass
            raise

        # Post-write verification, matching the local backend's _verify_file_hash.
        stored = blob.download_as_bytes()
        if _sha256_bytes(stored) != str(sha256):
            raise RawVaultError(RAW_ARCHIVE_HASH_MISMATCH_MESSAGE)

        return {
            "storage_path": f"gs://{self.bucket_name}/{key}",
            "object_key": key,
            "read_only": read_only,
            "reused": reused,
            "storage_backend": self.name,
        }

    # ----------------------------------------------------------------- exists

    def exists(
        self, *, storage_path: str | Path | None, raw_archive_id: str | None = None
    ) -> bool:
        blob = self._resolve_blob(storage_path=storage_path, raw_archive_id=raw_archive_id)
        if blob is None:
            return False
        try:
            return bool(blob.exists())
        except Exception:  # pragma: no cover - network/permission failure reads as absent
            return False

    # ----------------------------------------------------------------- verify

    def verify(
        self,
        *,
        storage_path: str | Path | None,
        expected_sha256: str | None,
        expected_byte_size: int | None = None,
        raw_archive_id: str | None = None,
        require_hash_verification: bool = True,
    ) -> RawArchiveIntegrityReport:
        blob = self._resolve_blob(storage_path=storage_path, raw_archive_id=raw_archive_id)
        uri = (
            str(storage_path)
            if storage_path
            else (f"gs://{self.bucket_name}/{blob.name}" if blob is not None else None)
        )
        if blob is None or not _blob_exists(blob):
            return RawArchiveIntegrityReport(
                raw_archive_id=raw_archive_id,
                storage_path=uri,
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

        payload: bytes | None = None
        if require_hash_verification:
            payload = blob.download_as_bytes()
            actual_sha: str | None = _sha256_bytes(payload)
        else:
            actual_sha = None

        actual_size = getattr(blob, "size", None)
        if actual_size is None:
            payload = payload if payload is not None else blob.download_as_bytes()
            actual_size = len(payload)

        sha_ok = (not require_hash_verification) or (
            bool(expected_sha256) and actual_sha == str(expected_sha256)
        )
        size_ok = expected_byte_size is None or int(actual_size) == int(expected_byte_size)
        warning = None
        if not sha_ok:
            warning = RAW_ARCHIVE_HASH_MISMATCH_MESSAGE
        elif not size_ok:
            warning = (
                "Raw archive byte size mismatch. Processing blocked to protect data integrity."
            )
        return RawArchiveIntegrityReport(
            raw_archive_id=raw_archive_id,
            storage_path=uri,
            expected_sha256=str(expected_sha256) if expected_sha256 else None,
            actual_sha256=actual_sha,
            expected_byte_size=expected_byte_size,
            actual_byte_size=int(actual_size),
            exists=True,
            sha256_verified=sha_ok,
            byte_size_matches=size_ok,
            ok=sha_ok and size_ok,
            warning=warning,
        )

    # ------------------------------------------------------------------- read

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
        blob = self._resolve_blob(storage_path=storage_path, raw_archive_id=raw_archive_id)
        if blob is None:  # pragma: no cover - verify() already proved it resolves
            raise RawVaultError("Raw archive integrity verification failed.")
        return blob.download_as_bytes()


def _blob_exists(blob: Any) -> bool:
    try:
        return bool(blob.exists())
    except Exception:  # pragma: no cover - defensive
        return False


def _is_precondition_failure(exc: Exception) -> bool:
    """True when an upload failed because the object already exists (HTTP 412/409)."""
    if type(exc).__name__ in {"PreconditionFailed", "Conflict"}:
        return True
    return getattr(exc, "code", None) in {409, 412}
