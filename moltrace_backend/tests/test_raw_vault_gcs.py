"""GCS raw-vault backend: the same ALCOA+ invariants as the local backend, on GCS.

All tests run against an in-memory fake of the ``google-cloud-storage`` client, so the
suite needs neither the optional dependency nor network access. The fake reproduces the
exact API surface the backend touches: ``bucket().blob()``, ``upload_from_string`` with
``if_generation_match=0`` (raising a 412-style error when the object exists),
``download_as_bytes``, ``exists``, ``delete``, ``list_blobs``, and bucket
``retention_period`` / ``versioning_enabled`` probing.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from nmrcheck.raw_vault import (
    RAW_ARCHIVE_HASH_MISMATCH_MESSAGE,
    RawVaultError,
    default_raw_storage_backend,
    ingest_raw_archive,
)
from nmrcheck.raw_vault_gcs import GCSRawStorageBackend, parse_gs_uri


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("sample/1/fid", b"\x00\x01\x02\x03")
        archive.writestr("sample/1/acqus", "##$SFO1= 600.13\n")
    return buffer.getvalue()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------- fake GCS


class _PreconditionFailed(Exception):
    code = 412


class _FakeBlob:
    def __init__(self, store: _FakeGCS, bucket_name: str, name: str) -> None:
        self._store = store
        self._bucket_name = bucket_name
        self.name = name
        self.metadata: dict | None = None

    # -- helpers -------------------------------------------------------------
    @property
    def _key(self) -> tuple[str, str]:
        return (self._bucket_name, self.name)

    @property
    def bucket(self) -> _FakeBucket:
        return self._store.bucket(self._bucket_name)

    @property
    def size(self) -> int | None:
        payload = self._store.objects.get(self._key)
        return None if payload is None else len(payload)

    # -- API surface the backend uses ---------------------------------------
    def upload_from_string(self, content: bytes, *, content_type=None, if_generation_match=None):
        if if_generation_match == 0 and self._key in self._store.objects:
            raise _PreconditionFailed("object already exists")
        self._store.objects[self._key] = bytes(content)

    def download_as_bytes(self) -> bytes:
        payload = self._store.objects.get(self._key)
        if payload is None:
            raise KeyError(self.name)
        return payload

    def exists(self) -> bool:
        return self._key in self._store.objects

    def delete(self) -> None:
        self._store.objects.pop(self._key, None)


class _FakeBucket:
    def __init__(self, store: _FakeGCS, name: str) -> None:
        self._store = store
        self.name = name
        self.retention_period: int | None = store.retention_period
        self.versioning_enabled: bool = store.versioning_enabled

    def blob(self, key: str) -> _FakeBlob:
        return _FakeBlob(self._store, self.name, key)

    def reload(self) -> None:
        self.retention_period = self._store.retention_period
        self.versioning_enabled = self._store.versioning_enabled


class _FakeGCS:
    """Stands in for google.cloud.storage.Client."""

    def __init__(self, *, retention_period: int | None = 60, versioning_enabled: bool = False):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.retention_period = retention_period
        self.versioning_enabled = versioning_enabled

    def bucket(self, name: str) -> _FakeBucket:
        return _FakeBucket(self, name)

    def list_blobs(self, bucket_name: str, prefix: str = ""):
        return [
            _FakeBlob(self, bucket_name, key)
            for (b, key) in sorted(self.objects)
            if b == bucket_name and key.startswith(prefix)
        ]


@pytest.fixture()
def fake() -> _FakeGCS:
    return _FakeGCS()


@pytest.fixture()
def backend(fake: _FakeGCS) -> GCSRawStorageBackend:
    return GCSRawStorageBackend("vault-bucket", client=fake)


# ------------------------------------------------------------------------------ tests


def test_parse_gs_uri() -> None:
    assert parse_gs_uri("gs://bucket/a/b.zip") == ("bucket", "a/b.zip")
    assert parse_gs_uri("/local/path.zip") is None
    assert parse_gs_uri("gs://bucket-only") is None


def test_save_stores_object_and_reports_gs_uri(backend, fake) -> None:
    payload = _zip_bytes()
    digest = _sha(payload)
    result = backend.save(content=payload, sha256=digest, filename="run.zip")
    assert result["storage_backend"] == "gcs_raw_vault"
    assert result["storage_path"] == f"gs://vault-bucket/{digest}/run.zip"
    assert result["object_key"] == f"{digest}/run.zip"
    assert result["reused"] is False
    assert result["read_only"] is True  # fake bucket has a retention period
    assert fake.objects[("vault-bucket", f"{digest}/run.zip")] == payload


def test_save_is_write_once_and_reuses_on_hash_match(backend) -> None:
    payload = _zip_bytes()
    digest = _sha(payload)
    backend.save(content=payload, sha256=digest, filename="run.zip")
    warnings: list[str] = []
    result = backend.save(content=payload, sha256=digest, filename="run.zip", warnings=warnings)
    assert result["reused"] is True
    assert any("existing immutable object was reused" in w for w in warnings)


def test_save_refuses_reuse_when_stored_bytes_differ(backend, fake) -> None:
    payload = _zip_bytes()
    digest = _sha(payload)
    backend.save(content=payload, sha256=digest, filename="run.zip")
    # Simulate corruption of the stored object, then attempt a same-key save.
    fake.objects[("vault-bucket", f"{digest}/run.zip")] = b"tampered"
    with pytest.raises(RawVaultError) as excinfo:
        backend.save(content=payload, sha256=digest, filename="run.zip")
    assert RAW_ARCHIVE_HASH_MISMATCH_MESSAGE in str(excinfo.value)


def test_strict_immutable_deletes_fresh_object_when_unprotected(fake) -> None:
    unprotected = _FakeGCS(retention_period=None, versioning_enabled=False)
    backend = GCSRawStorageBackend("vault-bucket", client=unprotected)
    payload = _zip_bytes()
    digest = _sha(payload)
    with pytest.raises(RawVaultError):
        backend.save(content=payload, sha256=digest, filename="run.zip", strict_immutable=True)
    # Fail-closed: the freshly-written, unprotected object must NOT survive.
    assert ("vault-bucket", f"{digest}/run.zip") not in unprotected.objects


def test_non_strict_unprotected_bucket_warns_but_stores(fake) -> None:
    unprotected = _FakeGCS(retention_period=None, versioning_enabled=False)
    backend = GCSRawStorageBackend("vault-bucket", client=unprotected)
    payload = _zip_bytes()
    warnings: list[str] = []
    result = backend.save(
        content=payload, sha256=_sha(payload), filename="run.zip", warnings=warnings
    )
    assert result["read_only"] is False
    assert any("retention" in w for w in warnings)


def test_verify_ok_roundtrip(backend) -> None:
    payload = _zip_bytes()
    digest = _sha(payload)
    saved = backend.save(content=payload, sha256=digest, filename="run.zip")
    report = backend.verify(
        storage_path=saved["storage_path"],
        expected_sha256=digest,
        expected_byte_size=len(payload),
    )
    assert report.ok and report.exists and report.sha256_verified and report.byte_size_matches
    assert report.actual_sha256 == digest


def test_verify_detects_corruption(backend, fake) -> None:
    payload = _zip_bytes()
    digest = _sha(payload)
    saved = backend.save(content=payload, sha256=digest, filename="run.zip")
    fake.objects[("vault-bucket", f"{digest}/run.zip")] = b"tampered"
    report = backend.verify(storage_path=saved["storage_path"], expected_sha256=digest)
    assert not report.ok
    assert report.warning == RAW_ARCHIVE_HASH_MISMATCH_MESSAGE


def test_verify_missing_object(backend) -> None:
    report = backend.verify(
        storage_path="gs://vault-bucket/deadbeef/absent.zip", expected_sha256="deadbeef"
    )
    assert not report.ok and not report.exists


def test_verify_resolves_by_archive_id_alone(backend) -> None:
    payload = _zip_bytes()
    digest = _sha(payload)
    backend.save(content=payload, sha256=digest, filename="run.zip")
    report = backend.verify(storage_path=None, expected_sha256=digest, raw_archive_id=digest)
    assert report.ok


def test_read_returns_bytes_and_refuses_mismatch(backend, fake) -> None:
    payload = _zip_bytes()
    digest = _sha(payload)
    saved = backend.save(content=payload, sha256=digest, filename="run.zip")
    assert backend.read(storage_path=saved["storage_path"], expected_sha256=digest) == payload
    fake.objects[("vault-bucket", f"{digest}/run.zip")] = b"tampered"
    with pytest.raises(RawVaultError):
        backend.read(storage_path=saved["storage_path"], expected_sha256=digest)


def test_exists(backend) -> None:
    payload = _zip_bytes()
    digest = _sha(payload)
    assert backend.exists(storage_path=f"gs://vault-bucket/{digest}/run.zip") is False
    backend.save(content=payload, sha256=digest, filename="run.zip")
    assert backend.exists(storage_path=f"gs://vault-bucket/{digest}/run.zip") is True
    assert backend.exists(storage_path=None, raw_archive_id=digest) is True


def test_ingest_raw_archive_end_to_end_via_gcs_backend(backend) -> None:
    """The full ingest pipeline (validation + inspection + store) over the GCS backend."""
    payload = _zip_bytes()
    record = ingest_raw_archive(filename="bruker run.zip", content=payload, backend=backend)
    assert record.storage_backend == "gcs_raw_vault"
    assert record.storage_path.startswith("gs://vault-bucket/")
    assert record.sha256 == _sha(payload)
    assert record.read_only is True
    # And the stored object round-trips through the backend by id alone.
    assert backend.read(storage_path=None, expected_sha256=record.sha256, raw_archive_id=record.sha256) == payload


def test_prefix_scopes_object_keys(fake) -> None:
    backend = GCSRawStorageBackend("vault-bucket", client=fake, prefix="prod")
    payload = _zip_bytes()
    digest = _sha(payload)
    saved = backend.save(content=payload, sha256=digest, filename="run.zip")
    assert saved["object_key"] == f"prod/{digest}/run.zip"
    assert backend.exists(storage_path=None, raw_archive_id=digest) is True


def test_factory_selects_gcs_from_settings(monkeypatch, fake) -> None:
    """RAW_VAULT_BACKEND=gcs + RAW_VAULT_BUCKET selects the GCS backend (no client call)."""
    from nmrcheck import settings as settings_module

    monkeypatch.setenv("RAW_VAULT_BACKEND", "gcs")
    monkeypatch.setenv("RAW_VAULT_BUCKET", "vault-bucket")
    settings_module.get_settings.cache_clear()
    try:
        chosen = default_raw_storage_backend()
        assert isinstance(chosen, GCSRawStorageBackend)
        assert chosen.bucket_name == "vault-bucket"
    finally:
        settings_module.get_settings.cache_clear()


def test_factory_requires_bucket(monkeypatch) -> None:
    from nmrcheck import settings as settings_module

    monkeypatch.setenv("RAW_VAULT_BACKEND", "gcs")
    monkeypatch.delenv("RAW_VAULT_BUCKET", raising=False)
    settings_module.get_settings.cache_clear()
    try:
        with pytest.raises(RawVaultError):
            default_raw_storage_backend()
    finally:
        settings_module.get_settings.cache_clear()


def test_factory_defaults_to_local(monkeypatch, tmp_path: Path) -> None:
    from nmrcheck import settings as settings_module
    from nmrcheck.raw_vault import LocalRawStorageBackend

    monkeypatch.delenv("RAW_VAULT_BACKEND", raising=False)
    settings_module.get_settings.cache_clear()
    try:
        chosen = default_raw_storage_backend(tmp_path)
        assert isinstance(chosen, LocalRawStorageBackend)
    finally:
        settings_module.get_settings.cache_clear()
