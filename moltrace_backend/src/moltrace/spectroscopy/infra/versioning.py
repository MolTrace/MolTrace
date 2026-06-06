"""Data versioning: content-addressed datasets + a DVC/S3 remote adapter.

Every dataset, gold set, and training snapshot must be content-addressed and
reproducible by hash, with no data blobs committed to git.  This module provides:

* :func:`dataset_hash` -- a pure sha256 content address for a file or directory
  (directory hash is over the sorted ``(relpath, file-sha256)`` manifest, so it
  is independent of filesystem walk order).
* :func:`current_git_sha` -- the code revision, for run provenance.
* :class:`LocalDatasetRemote` -- a zero-dependency, git-like content-addressed
  store that ``pin``\\s a dataset under a tag and ``restore``\\s it by hash with
  integrity verification.  This is the always-available fallback.
* :class:`DvcS3Remote` -- a thin adapter that drives the ``dvc`` CLI to pin to
  and restore from an S3 (or S3-compatible) remote, used when the optional
  ``infra`` extra is installed and a DVC repo is initialised.

The native store and the DVC adapter share the same :class:`DatasetVersion`
return type, so call sites are backend-agnostic.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from moltrace.spectroscopy.infra.contract import canonical_json

__all__ = [
    "DatasetIntegrityError",
    "DatasetVersion",
    "DvcNotAvailableError",
    "DvcS3Remote",
    "LocalDatasetRemote",
    "current_git_sha",
    "dataset_hash",
    "file_sha256",
]

_CHUNK = 1 << 20  # 1 MiB


class DatasetIntegrityError(RuntimeError):
    """Raised when a restored dataset's content hash does not match its pin."""


class DvcNotAvailableError(RuntimeError):
    """Raised when a DVC operation is requested but DVC is not usable."""


@dataclass(frozen=True)
class DatasetVersion:
    """A pinned dataset: its tag, content hash, and shape."""

    tag: str
    dataset_hash: str
    kind: str  # "file" | "dir"
    n_files: int
    total_bytes: int
    backend: str  # "local" | "dvc-s3"


# --------------------------------------------------------------------------- #
# Pure content addressing
# --------------------------------------------------------------------------- #
def file_sha256(path: str | Path) -> str:
    """Hex sha256 of a single file's bytes (chunked, constant memory)."""

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dir_manifest(root: Path) -> list[dict[str, object]]:
    """Sorted ``[{path, sha256, size}]`` for every file under ``root``."""

    entries: list[dict[str, object]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        entries.append(
            {"path": rel, "sha256": file_sha256(path), "size": path.stat().st_size}
        )
    entries.sort(key=lambda e: e["path"])  # deterministic, OS-independent order
    return entries


def dataset_hash(path: str | Path) -> str:
    """Content address (``sha256:<hex>``) of a file or directory.

    * file -> sha256 of its bytes.
    * directory -> sha256 of the canonical JSON of its sorted file manifest, so
      the hash depends only on contents + relative layout, never on walk order.
    """

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"dataset path does not exist: {target}")
    if target.is_file():
        return "sha256:" + file_sha256(target)
    manifest = _dir_manifest(target)
    return "sha256:" + hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def current_git_sha(*, short: bool = False, cwd: str | Path | None = None) -> str:
    """Best-effort current git commit SHA for run provenance.

    Resolution order: ``$MOLTRACE_GIT_SHA`` (CI override) -> ``git rev-parse`` ->
    ``"unknown"``.  Never raises; provenance must not break a run.
    """

    override = os.environ.get("MOLTRACE_GIT_SHA")
    if override:
        return override[:7] if short else override
    args = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
    try:
        out = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# --------------------------------------------------------------------------- #
# Native content-addressed store (always available)
# --------------------------------------------------------------------------- #
class LocalDatasetRemote:
    """A git-like content-addressed dataset store backed by a local directory.

    Layout under ``root``::

        cache/<ab>/<sha256>   # deduplicated file blobs
        tags/<tag>.json       # pointer: dataset_hash + file manifest

    ``pin`` copies a dataset's blobs into the cache and writes a tag pointer;
    ``restore`` rebuilds the dataset from the pointer and verifies every blob's
    hash plus the overall dataset hash.  No data ever touches git -- the store
    root is an artifact directory (see ``.gitignore``).
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.cache = self.root / "cache"
        self.tags = self.root / "tags"

    def _blob_path(self, sha_hex: str) -> Path:
        return self.cache / sha_hex[:2] / sha_hex

    def _pointer_path(self, tag: str) -> Path:
        if not tag or "/" in tag or os.sep in tag:
            raise ValueError(f"invalid dataset tag: {tag!r}")
        return self.tags / f"{tag}.json"

    def pin(self, path: str | Path, tag: str) -> DatasetVersion:
        """Content-address ``path`` and record it under ``tag``."""

        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"dataset path does not exist: {source}")
        self.cache.mkdir(parents=True, exist_ok=True)
        self.tags.mkdir(parents=True, exist_ok=True)

        if source.is_file():
            kind = "file"
            entries = [
                {"path": source.name, "sha256": file_sha256(source), "size": source.stat().st_size}
            ]
        else:
            kind = "dir"
            entries = _dir_manifest(source)

        total_bytes = 0
        for entry in entries:
            sha_hex = str(entry["sha256"])
            total_bytes += int(entry["size"])
            blob = self._blob_path(sha_hex)
            if not blob.exists():
                blob.parent.mkdir(parents=True, exist_ok=True)
                src_file = source if source.is_file() else source / str(entry["path"])
                tmp = blob.with_suffix(".tmp")
                shutil.copy2(src_file, tmp)
                tmp.replace(blob)  # atomic publish

        ds_hash = dataset_hash(source)
        pointer = {
            "tag": tag,
            "dataset_hash": ds_hash,
            "kind": kind,
            "entries": entries,
        }
        self._pointer_path(tag).write_text(canonical_json(pointer), encoding="utf-8")
        return DatasetVersion(tag, ds_hash, kind, len(entries), total_bytes, "local")

    def resolve(self, tag: str) -> DatasetVersion:
        """Return the :class:`DatasetVersion` for ``tag`` without restoring it."""

        pointer = self._read_pointer(tag)
        entries = pointer["entries"]
        return DatasetVersion(
            tag=tag,
            dataset_hash=str(pointer["dataset_hash"]),
            kind=str(pointer["kind"]),
            n_files=len(entries),
            total_bytes=sum(int(e["size"]) for e in entries),
            backend="local",
        )

    def restore(self, tag: str, dest: str | Path) -> DatasetVersion:
        """Rebuild the dataset pinned at ``tag`` into ``dest`` and verify it."""

        pointer = self._read_pointer(tag)
        entries = pointer["entries"]
        kind = str(pointer["kind"])
        destination = Path(dest)

        if kind == "file":
            entry = entries[0]
            blob = self._blob_path(str(entry["sha256"]))
            self._verify_blob(blob, str(entry["sha256"]))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(blob, destination)
            restored_hash = dataset_hash(destination)
        else:
            destination.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                blob = self._blob_path(str(entry["sha256"]))
                self._verify_blob(blob, str(entry["sha256"]))
                out_path = destination / str(entry["path"])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(blob, out_path)
            restored_hash = dataset_hash(destination)

        expected = str(pointer["dataset_hash"])
        if restored_hash != expected:
            raise DatasetIntegrityError(
                f"restored dataset hash {restored_hash} != pinned {expected} (tag {tag!r})"
            )
        return DatasetVersion(
            tag, expected, kind, len(entries), sum(int(e["size"]) for e in entries), "local"
        )

    def _read_pointer(self, tag: str) -> dict:
        import json

        path = self._pointer_path(tag)
        if not path.exists():
            raise KeyError(f"no dataset pinned under tag {tag!r}")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _verify_blob(blob: Path, expected_sha: str) -> None:
        if not blob.exists():
            raise DatasetIntegrityError(f"missing blob {expected_sha} in store")
        actual = file_sha256(blob)
        if actual != expected_sha:
            raise DatasetIntegrityError(
                f"blob corruption: expected {expected_sha}, found {actual}"
            )


# --------------------------------------------------------------------------- #
# DVC + S3 adapter (optional)
# --------------------------------------------------------------------------- #
def _require_dvc() -> None:
    """Raise a clear, actionable error if the DVC CLI is not importable."""

    if shutil.which("dvc") is None:
        try:  # the python package ships the CLI; importing proves availability
            import dvc  # noqa: F401
        except Exception as exc:  # pragma: no cover - exercised only without dvc
            raise DvcNotAvailableError(
                "DVC is not installed. Install the optional infra extra: "
                "`pip install nmrcheck[infra]` (provides dvc[s3])."
            ) from exc


class DvcS3Remote:
    """Drive the ``dvc`` CLI to pin/restore datasets against an S3 remote.

    Requires an initialised DVC repo (``dvc init``) with a configured S3 remote
    (``dvc remote add -d <name> s3://bucket/key``).  This adapter shells out to
    the CLI rather than importing DVC internals so it tracks whatever DVC version
    the user installed.  When DVC is unavailable every method raises
    :class:`DvcNotAvailableError` -- callers should fall back to
    :class:`LocalDatasetRemote`.
    """

    def __init__(self, repo_root: str | Path, *, remote: str | None = None) -> None:
        self.repo_root = Path(repo_root)
        self.remote = remote

    def _dvc(self, *args: str) -> subprocess.CompletedProcess[str]:
        _require_dvc()
        return subprocess.run(
            ["dvc", *args],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            check=True,
        )

    def pin(self, path: str | Path, tag: str) -> DatasetVersion:
        """``dvc add`` the dataset then ``dvc push`` it to the S3 remote.

        The content hash is computed natively (so it matches
        :func:`dataset_hash` regardless of DVC's internal md5 scheme) and the
        ``.dvc`` pointer file is what gets committed to git -- never the blob.
        """

        _require_dvc()
        source = Path(path)
        ds_hash = dataset_hash(source)
        self._dvc("add", str(source))
        push_args = ["push", str(source)]
        if self.remote:
            push_args += ["-r", self.remote]
        self._dvc(*push_args)
        kind = "file" if source.is_file() else "dir"
        if source.is_file():
            n_files, total = 1, source.stat().st_size
        else:
            manifest = _dir_manifest(source)
            n_files, total = len(manifest), sum(int(e["size"]) for e in manifest)
        return DatasetVersion(tag, ds_hash, kind, n_files, total, "dvc-s3")

    def restore(self, path: str | Path, *, expected_hash: str | None = None) -> DatasetVersion:
        """``dvc pull`` the dataset back and (optionally) verify its hash."""

        _require_dvc()
        target = Path(path)
        pull_args = ["pull", str(target)]
        if self.remote:
            pull_args += ["-r", self.remote]
        self._dvc(*pull_args)
        ds_hash = dataset_hash(target)
        if expected_hash is not None and ds_hash != expected_hash:
            raise DatasetIntegrityError(
                f"pulled dataset hash {ds_hash} != expected {expected_hash}"
            )
        kind = "file" if target.is_file() else "dir"
        if target.is_file():
            n_files, total = 1, target.stat().st_size
        else:
            manifest = _dir_manifest(target)
            n_files, total = len(manifest), sum(int(e["size"]) for e in manifest)
        return DatasetVersion("", ds_hash, kind, n_files, total, "dvc-s3")
