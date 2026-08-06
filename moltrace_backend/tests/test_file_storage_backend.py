"""Uploaded files survive a host that does not keep its filesystem.

Managed files were written straight to disk and their rows stamped ``storage_backend="local"``
unconditionally. On Cloud Run that is silent data loss: the filesystem is ephemeral, so an upload
vanishes on the next instance recycle while its database row still claims the file is there. The
failure surfaces later as a broken download rather than an error at upload time, which is the
worst shape for a data-integrity bug to have.

What these pin: the local backend keeps its existing behaviour including exclusive-create, a
misconfigured object backend fails at resolution rather than at first upload, and — the one that
matters for a real migration — a row written before the switch still reads from where its bytes
actually are.
"""

import pytest

from nmrcheck import file_storage
from nmrcheck.file_storage import (
    FileStorageError,
    GcsFileStorage,
    LocalFileStorage,
    default_file_storage,
)


def test_local_backend_round_trips(tmp_path):
    backend = LocalFileStorage(tmp_path / "storage")
    backend.write("storage/uploads/1_sample.bin", b"spectrum bytes")
    assert backend.read("storage/uploads/1_sample.bin") == b"spectrum bytes"
    assert backend.exists("storage/uploads/1_sample.bin")


def test_local_backend_refuses_to_overwrite(tmp_path):
    """Exclusive create is a collision guarantee, not an accident of the old implementation. Two
    uploads resolving to one key must be an error, never a silent overwrite of evidence."""
    backend = LocalFileStorage(tmp_path / "storage")
    backend.write("storage/uploads/1_sample.bin", b"first")
    with pytest.raises(FileExistsError):
        backend.write("storage/uploads/1_sample.bin", b"second")
    assert backend.read("storage/uploads/1_sample.bin") == b"first"


def test_reading_an_absent_object_is_a_not_found(tmp_path):
    backend = LocalFileStorage(tmp_path / "storage")
    with pytest.raises(FileNotFoundError):
        backend.read("storage/uploads/nope.bin")


def test_the_default_is_local_so_nothing_existing_changes(tmp_path):
    backend = default_file_storage(tmp_path / "storage")
    assert isinstance(backend, LocalFileStorage)
    assert backend.name == "local"


def test_object_storage_without_a_bucket_fails_at_resolution(tmp_path, monkeypatch):
    """A half-configured deployment must fail when the backend is resolved, not silently write to
    an ephemeral disk and lose the file hours later."""
    settings = file_storage.__dict__  # noqa: F841 - documents the import site below

    class _Settings:
        file_storage_backend = "gcs"
        file_storage_bucket = None

    monkeypatch.setattr("nmrcheck.settings.get_settings", lambda: _Settings())
    with pytest.raises(FileStorageError, match="FILE_STORAGE_BUCKET"):
        default_file_storage(tmp_path / "storage")


def test_an_unknown_backend_name_is_rejected(tmp_path, monkeypatch):
    class _Settings:
        file_storage_backend = "s3"  # not implemented — must not fall through to local
        file_storage_bucket = "bucket"

    monkeypatch.setattr("nmrcheck.settings.get_settings", lambda: _Settings())
    with pytest.raises(FileStorageError, match="Unknown FILE_STORAGE_BACKEND"):
        default_file_storage(tmp_path / "storage")


def test_object_storage_resolves_when_configured(tmp_path, monkeypatch):
    class _Settings:
        file_storage_backend = "gcs"
        file_storage_bucket = "moltrace-files"

    monkeypatch.setattr("nmrcheck.settings.get_settings", lambda: _Settings())
    backend = default_file_storage(tmp_path / "storage")
    assert isinstance(backend, GcsFileStorage)
    assert backend.name == "gcs"


# --------------------------------------------------------------------------- #
# The migration property
# --------------------------------------------------------------------------- #
def test_an_upload_records_the_backend_that_actually_stored_it(client, api_headers):
    """The row used to say "local" whatever happened. An operator reading the table has to be able
    to tell where the bytes really are."""
    with client:
        res = client.post(
            "/files/upload",
            headers=api_headers,
            files={"file": ("sample.txt", b"spectrum bytes", "text/plain")},
            data={"file_kind": "other"},
        )
        assert res.status_code == 201, res.text
        assert res.json()["storage_backend"] == "local"


def test_a_file_written_before_the_switch_still_reads_after_it(client, api_headers, monkeypatch):
    """The property that makes flipping a deployment to object storage safe: the backend is chosen
    from the row, not from current settings, so existing files are not orphaned."""
    with client:
        uploaded = client.post(
            "/files/upload",
            headers=api_headers,
            files={"file": ("legacy.txt", b"written before the switch", "text/plain")},
            data={"file_kind": "other"},
        ).json()

        # Now the deployment moves to object storage. The legacy row is still marked local.
        class _Settings:
            file_storage_backend = "gcs"
            file_storage_bucket = "moltrace-files"

        monkeypatch.setattr("nmrcheck.settings.get_settings", lambda: _Settings())

        # It must still come back from the filesystem, without touching the object store at all.
        res = client.get(f"/files/{uploaded['id']}/download", headers=api_headers)
        assert res.status_code == 200, res.text
        assert res.content == b"written before the switch"
