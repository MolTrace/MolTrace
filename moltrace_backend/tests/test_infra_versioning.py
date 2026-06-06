"""Unit tests for data versioning (infra.versioning).

The native content-addressed store is exercised end-to-end; the DVC/S3 adapter's
unavailable-path guard is tested without requiring DVC to be installed.
"""

from __future__ import annotations

import importlib.util
import subprocess

import pytest

from moltrace.spectroscopy.infra.versioning import (
    DatasetIntegrityError,
    DvcNotAvailableError,
    DvcS3Remote,
    LocalDatasetRemote,
    current_git_sha,
    dataset_hash,
)

_HAS_DVC = importlib.util.find_spec("dvc") is not None


# --------------------------------------------------------------------------- #
# dataset_hash
# --------------------------------------------------------------------------- #
def test_dataset_hash_file_is_deterministic(tmp_path) -> None:
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello world")
    assert dataset_hash(f) == dataset_hash(f)
    assert dataset_hash(f).startswith("sha256:")


def test_dataset_hash_changes_with_content(tmp_path) -> None:
    f = tmp_path / "data.bin"
    f.write_bytes(b"aaaa")
    h1 = dataset_hash(f)
    f.write_bytes(b"bbbb")
    assert dataset_hash(f) != h1


def test_dataset_hash_dir_is_layout_not_walk_order(tmp_path) -> None:
    d1 = tmp_path / "d1"
    d1.mkdir()
    (d1 / "a.txt").write_text("alpha")
    (d1 / "b.txt").write_text("beta")
    d2 = tmp_path / "d2"
    d2.mkdir()
    # Same contents, written in the opposite order.
    (d2 / "b.txt").write_text("beta")
    (d2 / "a.txt").write_text("alpha")
    assert dataset_hash(d1) == dataset_hash(d2)


def test_dataset_hash_dir_detects_content_change(tmp_path) -> None:
    d = tmp_path / "d"
    d.mkdir()
    (d / "a.txt").write_text("alpha")
    before = dataset_hash(d)
    (d / "a.txt").write_text("ALPHA")
    assert dataset_hash(d) != before


def test_dataset_hash_missing_path_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        dataset_hash(tmp_path / "nope")


# --------------------------------------------------------------------------- #
# current_git_sha
# --------------------------------------------------------------------------- #
def test_current_git_sha_matches_rev_parse() -> None:
    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert current_git_sha() == expected


def test_current_git_sha_env_override(monkeypatch) -> None:
    monkeypatch.setenv("MOLTRACE_GIT_SHA", "deadbeefcafe")
    assert current_git_sha() == "deadbeefcafe"
    assert current_git_sha(short=True) == "deadbee"


# --------------------------------------------------------------------------- #
# LocalDatasetRemote round-trip
# --------------------------------------------------------------------------- #
def test_local_remote_file_round_trip(tmp_path) -> None:
    store = LocalDatasetRemote(tmp_path / "store")
    src = tmp_path / "gold.json"
    src.write_text('{"x": 1}')
    pinned = store.pin(src, "gold-v1")
    assert pinned.kind == "file"
    assert pinned.backend == "local"

    dest = tmp_path / "restored.json"
    restored = store.restore("gold-v1", dest)
    assert dest.read_text() == '{"x": 1}'
    assert restored.dataset_hash == pinned.dataset_hash


def test_local_remote_dir_round_trip(tmp_path) -> None:
    store = LocalDatasetRemote(tmp_path / "store")
    src = tmp_path / "dataset"
    src.mkdir()
    (src / "train.csv").write_text("a,b\n1,2\n")
    (src / "nested").mkdir()
    (src / "nested" / "meta.json").write_text("{}")
    pinned = store.pin(src, "ds-2026")
    assert pinned.kind == "dir"
    assert pinned.n_files == 2

    dest = tmp_path / "out"
    store.restore("ds-2026", dest)
    assert (dest / "train.csv").read_text() == "a,b\n1,2\n"
    assert (dest / "nested" / "meta.json").read_text() == "{}"
    assert dataset_hash(dest) == pinned.dataset_hash


def test_local_remote_resolve_without_restore(tmp_path) -> None:
    store = LocalDatasetRemote(tmp_path / "store")
    src = tmp_path / "x.bin"
    src.write_bytes(b"data")
    pinned = store.pin(src, "tag1")
    resolved = store.resolve("tag1")
    assert resolved.dataset_hash == pinned.dataset_hash


def test_local_remote_detects_corruption(tmp_path) -> None:
    store = LocalDatasetRemote(tmp_path / "store")
    src = tmp_path / "x.bin"
    src.write_bytes(b"important")
    store.pin(src, "tag1")
    # Corrupt the cached blob.
    blobs = [p for p in store.cache.rglob("*") if p.is_file()]
    assert blobs, "expected at least one cached blob"
    blobs[0].write_bytes(b"tampered")
    with pytest.raises(DatasetIntegrityError):
        store.restore("tag1", tmp_path / "out.bin")


def test_local_remote_unknown_tag_raises(tmp_path) -> None:
    store = LocalDatasetRemote(tmp_path / "store")
    with pytest.raises(KeyError):
        store.restore("missing", tmp_path / "out")


def test_local_remote_rejects_bad_tag(tmp_path) -> None:
    store = LocalDatasetRemote(tmp_path / "store")
    src = tmp_path / "x.bin"
    src.write_bytes(b"d")
    with pytest.raises(ValueError):
        store.pin(src, "bad/tag")


# --------------------------------------------------------------------------- #
# DvcS3Remote guard
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(_HAS_DVC, reason="DVC installed; the unavailable-path guard cannot fire")
def test_dvc_adapter_raises_when_unavailable(tmp_path) -> None:
    remote = DvcS3Remote(tmp_path, remote="s3prod")
    src = tmp_path / "x.bin"
    src.write_bytes(b"d")
    with pytest.raises(DvcNotAvailableError):
        remote.pin(src, "tag1")


@pytest.mark.skipif(not _HAS_DVC, reason="DVC not installed")
def test_dvc_adapter_importable_when_present(tmp_path) -> None:
    # When DVC is present, constructing the adapter must not raise.
    DvcS3Remote(tmp_path, remote="s3prod")
