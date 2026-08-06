"""Where uploaded files and generated artifacts actually live.

Managed files were written straight to the local filesystem and their rows stamped
``storage_backend="local"`` unconditionally. On a host with a persistent disk that is fine. On a
serverless host it is silent data loss: Cloud Run's filesystem is ephemeral, so an uploaded file
disappears on the next instance recycle while its database row still says it is there — the
failure shows up later as a broken download, not as an error at upload time.

This is the same problem the raw vault already solved, so this module follows the same shape: a
small backend interface, a local implementation that preserves the existing behaviour exactly, a
Cloud Storage implementation for serverless hosts, and a settings-driven resolver that defaults to
local so dev, tests and existing deployments are untouched.

Two details worth keeping:

* **Exclusive create.** The local backend writes with ``open("xb")`` so two uploads that resolve to
  the same key cannot silently overwrite each other. Object stores have no such mode, so the GCS
  backend asks for the same guarantee with a generation precondition rather than dropping it.
* **The record tells the truth.** A row's ``storage_backend`` is now whatever actually stored the
  bytes, so an operator reading the table can tell where to look for them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class FileStorageError(RuntimeError):
    """Storing or retrieving file bytes failed."""


class FileStorageBackend(Protocol):
    """Reads and writes opaque byte objects by key."""

    name: str

    def write(self, key: str, content: bytes) -> None:
        """Store ``content`` at ``key``. Must fail if the key already holds an object."""

    def read(self, key: str) -> bytes:
        """Return the bytes at ``key``, or raise :class:`FileNotFoundError`."""

    def exists(self, key: str) -> bool: ...


class LocalFileStorage:
    """The filesystem backend — the behaviour every existing deployment already has."""

    name = "local"

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        # ``storage/…`` keys are rooted a level up, matching how the keys were originally minted.
        return self._root.parent / key if key.startswith("storage/") else self._root / key

    def write(self, key: str, content: bytes) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create: a colliding key is an error, never a silent overwrite.
        with target.open("xb") as handle:
            handle.write(content)

    def read(self, key: str) -> bytes:
        target = self._path(key)
        if not target.exists():
            raise FileNotFoundError(f"No stored object for key {key!r}.")
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class GcsFileStorage:
    """Cloud Storage, for hosts whose filesystem does not survive a restart."""

    name = "gcs"

    def __init__(self, bucket: str) -> None:
        self._bucket_name = bucket
        self._bucket = None

    def _resolve_bucket(self):
        if self._bucket is None:
            try:
                from google.cloud import storage  # type: ignore[import-not-found]
            except ImportError as exc:  # pragma: no cover - depends on the deployment image
                raise FileStorageError(
                    "FILE_STORAGE_BACKEND=gcs requires the google-cloud-storage package."
                ) from exc
            self._bucket = storage.Client().bucket(self._bucket_name)
        return self._bucket

    def write(self, key: str, content: bytes) -> None:
        blob = self._resolve_bucket().blob(key)
        try:
            # if_generation_match=0 means "only if this object does not exist yet" — the object
            # store's equivalent of the local backend's exclusive create.
            blob.upload_from_string(content, if_generation_match=0)
        except Exception as exc:  # pragma: no cover - depends on a live bucket
            raise FileStorageError(f"Could not store object {key!r}: {exc}") from exc

    def read(self, key: str) -> bytes:
        blob = self._resolve_bucket().blob(key)
        if not blob.exists():
            raise FileNotFoundError(f"No stored object for key {key!r}.")
        return blob.download_as_bytes()

    def exists(self, key: str) -> bool:
        return bool(self._resolve_bucket().blob(key).exists())


def default_file_storage(storage_root: Path | str) -> FileStorageBackend:
    """Pick the backend from settings, defaulting to the local filesystem.

    ``storage_root`` is only consulted by the local backend; the object backend keys off the
    bucket alone. Mirrors ``raw_vault.default_raw_storage_backend`` deliberately — an operator who
    has configured one should find the other works the same way.
    """
    from .settings import get_settings

    settings = get_settings()
    choice = (getattr(settings, "file_storage_backend", None) or "local").strip().lower()
    if choice in {"gcs", "gs", "google"}:
        bucket = getattr(settings, "file_storage_bucket", None)
        if not bucket:
            raise FileStorageError(
                "FILE_STORAGE_BACKEND=gcs requires FILE_STORAGE_BUCKET to name the bucket."
            )
        return GcsFileStorage(bucket)
    if choice not in {"local", "filesystem", "file"}:
        raise FileStorageError(
            f"Unknown FILE_STORAGE_BACKEND {choice!r}; expected 'local' or 'gcs'."
        )
    return LocalFileStorage(Path(storage_root))
