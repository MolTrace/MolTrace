import hashlib
import io
import json
import os
import stat
import tarfile
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.raw_vault import (
    RAW_ARCHIVE_HASH_MISMATCH_MESSAGE,
    RawVaultError,
    ingest_raw_archive,
    inspect_raw_archive,
    verify_raw_archive_integrity,
)
from nmrcheck.settings import Settings

REFERENCE_TEXT = "3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)"


def _bruker_acqus(points: int = 1024) -> str:
    return f"""##TITLE= immutable raw fid test
##$TD= {points * 2}
##$SW_h= 5000.0
##$SW= 10.0
##$SFO1= 500.0
##$BF1= 500.0
##$O1= 2000.0
##$O1P= 4.0
##$NUC1= <1H>
##$SOLVENT= <CDCl3>
##$PULPROG= <zg30>
##$TE= 298.0
##$RG= 32
##$BYTORDA= 0
##$DTYPA= 0
##$GRPDLY= 0
"""


def _bruker_zip() -> bytes:
    points = 1024
    sw_hz = 5000.0
    sfo1 = 500.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65), (2.1, 0.3)]:
        frequency_hz = (ppm - center_ppm) * sfo1
        fid += amplitude * np.exp(2j * np.pi * frequency_hz * time_axis) * np.exp(-time_axis * 10.0)
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("sample/fid", interleaved.tobytes())
        archive.writestr("sample/acqus", _bruker_acqus(points))
    return buffer.getvalue()


def _zip_bytes(entries: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _tar_gz_bytes(entries: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in entries.items():
            payload = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _client(tmp_path) -> tuple[TestClient, dict[str, str]]:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'raw_fid_vault.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_vault_dir=str(tmp_path / "raw_data_vault"),
            raw_data_vault_dir=str(tmp_path / "raw_data_vault"),
        )
    )
    return TestClient(app), {"x-api-key": "test-key"}


def _upload_archive(client: TestClient, headers: dict[str, str], content: bytes) -> dict:
    response = client.post(
        "/raw-fid/upload",
        headers=headers,
        files={"file": ("sample.zip", content, "application/zip")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_upload_zip_stores_original_archive_and_sha256(tmp_path) -> None:
    content = _bruker_zip()
    record = ingest_raw_archive(filename="sample.zip", content=content, vault_dir=tmp_path / "raw_data_vault")

    expected_sha = hashlib.sha256(content).hexdigest()
    stored_path = tmp_path / "raw_data_vault" / expected_sha / "sample.zip"
    assert record.sha256 == expected_sha
    assert record.storage_path == str(stored_path)
    assert stored_path.is_file()
    assert hashlib.sha256(stored_path.read_bytes()).hexdigest() == expected_sha
    assert verify_raw_archive_integrity(record).ok is True


def test_stored_raw_archive_is_read_only_where_supported(tmp_path) -> None:
    record = ingest_raw_archive(filename="sample.zip", content=_bruker_zip(), vault_dir=tmp_path / "raw_data_vault")
    mode = os.stat(record.storage_path).st_mode

    if os.name == "posix":
        assert mode & stat.S_IWUSR == 0
        assert record.read_only is True
    else:
        assert record.read_only is True or any("read-only" in warning.lower() for warning in record.warnings)


def test_unsafe_zip_path_traversal_is_rejected(tmp_path) -> None:
    content = _zip_bytes({"../evil/fid": b"\x00" * 16, "sample/acqus": _bruker_acqus()})

    with pytest.raises(RawVaultError, match="unsafe"):
        ingest_raw_archive(filename="unsafe.zip", content=content, vault_dir=tmp_path)


def test_unsafe_tar_path_traversal_is_rejected(tmp_path) -> None:
    content = _tar_gz_bytes({"../evil/fid": b"\x00" * 16, "sample/acqus": _bruker_acqus()})

    with pytest.raises(RawVaultError, match="unsafe"):
        ingest_raw_archive(filename="unsafe.tar.gz", content=content, vault_dir=tmp_path)


def test_symlink_tar_entry_is_rejected(tmp_path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        link = tarfile.TarInfo("sample/fid")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        archive.addfile(link)
        payload = _bruker_acqus().encode()
        acqus = tarfile.TarInfo("sample/acqus")
        acqus.size = len(payload)
        archive.addfile(acqus, io.BytesIO(payload))

    with pytest.raises(RawVaultError, match="link"):
        ingest_raw_archive(filename="unsafe.tar.gz", content=buffer.getvalue(), vault_dir=tmp_path)


def test_metadata_extraction_reads_vendor_params_without_modifying_archive() -> None:
    content = _zip_bytes(
        {
            "sample.fid/fid": b"\x00" * 128,
            "sample.fid/procpar": "sfrq 125.0\nsw 25000.0\ntn C13\nnp 4096\nsolvent CDCl3\nseqfil s2pul\ntemp 25\n",
        }
    )
    before = hashlib.sha256(content).hexdigest()
    inspection = inspect_raw_archive(filename="varian.zip", content=content)
    after = hashlib.sha256(content).hexdigest()

    assert before == after
    assert inspection["vendor_detected"] == "Varian/Agilent"
    assert inspection["acquisition_metadata"]["nucleus"] == "C13"
    assert inspection["acquisition_metadata"]["spectrometer_frequency_mhz"] == 125.0


def test_processing_does_not_change_raw_archive_hash(tmp_path) -> None:
    content = _bruker_zip()
    client, headers = _client(tmp_path)
    with client:
        archive = _upload_archive(client, headers, content)
        stored_path = archive["storage_path"]
        before = hashlib.sha256(open(stored_path, "rb").read()).hexdigest()
        preview = client.post(f"/raw-fid/{archive['raw_archive_id']}/preview", headers=headers)
        assert preview.status_code == 200, preview.text
        processed = client.post(
            f"/raw-fid/{archive['raw_archive_id']}/process",
            headers=headers,
            data={"smiles": "CCO", "manual_nmr_text": REFERENCE_TEXT},
        )
        assert processed.status_code == 200, processed.text
        after = hashlib.sha256(open(stored_path, "rb").read()).hexdigest()

    assert before == after == archive["sha256"]


def test_integrity_mismatch_blocks_processing_and_export(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        archive = _upload_archive(client, headers, _bruker_zip())
        os.chmod(archive["storage_path"], 0o644)
        with open(archive["storage_path"], "ab") as handle:
            handle.write(b"tamper")
        report = verify_raw_archive_integrity(archive)
        assert report.ok is False
        assert report.warning == RAW_ARCHIVE_HASH_MISMATCH_MESSAGE

        processed = client.post(
            f"/raw-fid/{archive['raw_archive_id']}/process",
            headers=headers,
            data={"smiles": "CCO", "manual_nmr_text": REFERENCE_TEXT},
        )
        assert processed.status_code == 409
        assert processed.json()["detail"] == RAW_ARCHIVE_HASH_MISMATCH_MESSAGE

        exported = client.get(f"/raw-fid/{archive['raw_archive_id']}/export", headers=headers)
        assert exported.status_code == 409
        assert exported.json()["detail"] == RAW_ARCHIVE_HASH_MISMATCH_MESSAGE

        audit = client.get(
            f"/audit?entity_type=raw_archive&entity_id={archive['id']}",
            headers=headers,
        )
        assert audit.status_code == 200, audit.text
        assert any(event["event_type"] == "raw_fid.integrity_failure" for event in audit.json())


def test_export_package_contains_original_archive_and_analysis_metadata(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        archive = _upload_archive(client, headers, _bruker_zip())
        processed = client.post(
            f"/raw-fid/{archive['raw_archive_id']}/process",
            headers=headers,
            data={"smiles": "CCO", "manual_nmr_text": REFERENCE_TEXT},
        )
        assert processed.status_code == 200, processed.text
        exported = client.get(f"/raw-fid/{archive['raw_archive_id']}/export", headers=headers)
        assert exported.status_code == 200, exported.text
        with zipfile.ZipFile(io.BytesIO(exported.content)) as package:
            names = set(package.namelist())
            manifest = package.read("manifest.json")
            manifest_json = json.loads(manifest)
            assert "raw/original_archive.zip" in names
            assert "analysis/analysis.json" in names
            assert "analysis/processing_recipe.json" in names
            assert manifest_json["hashes"]["raw/original_archive.zip"] == archive["sha256"]


def test_raw_preview_points_absent_unless_debug_preview_true(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        archive = _upload_archive(client, headers, _bruker_zip())
        default = client.post(f"/raw-fid/{archive['raw_archive_id']}/preview", headers=headers)
        debug = client.post(
            f"/raw-fid/{archive['raw_archive_id']}/preview",
            headers=headers,
            data={"debug_preview": "true"},
        )

    assert default.status_code == 200, default.text
    assert debug.status_code == 200, debug.text
    assert "raw_preview_points" not in default.json()["metadata"]
    assert "raw_preview_points" in debug.json()["metadata"]


def test_raw_fid_upload_endpoint_works(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        archive = _upload_archive(client, headers, _bruker_zip())

    assert archive["required_files_present"] is True
    assert archive["vendor_detected"] == "Bruker"
    assert archive["raw_archive_id"] == archive["sha256"]


def test_raw_fid_process_creates_run_linked_to_archive(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        archive = _upload_archive(client, headers, _bruker_zip())
        processed = client.post(
            f"/raw-fid/{archive['raw_archive_id']}/process",
            headers=headers,
            data={"smiles": "CCO", "manual_nmr_text": REFERENCE_TEXT},
        )
        assert processed.status_code == 200, processed.text
        runs = client.get(f"/raw-fid/{archive['raw_archive_id']}/runs", headers=headers)

    assert runs.status_code == 200, runs.text
    run_items = runs.json()
    assert len(run_items) == 1
    assert run_items[0]["raw_archive_id"] == archive["id"]
    assert run_items[0]["raw_sha256"] == archive["sha256"]


def test_raw_fid_export_endpoint_returns_package(tmp_path) -> None:
    client, headers = _client(tmp_path)
    with client:
        archive = _upload_archive(client, headers, _bruker_zip())
        exported = client.get(f"/raw-fid/{archive['raw_archive_id']}/export", headers=headers)

    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as package:
        assert "manifest.json" in package.namelist()
        assert "analysis/processing_recipe.json" in package.namelist()
