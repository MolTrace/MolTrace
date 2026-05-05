import io
import os
import stat
import tarfile
import zipfile

import pytest

from nmrcheck.database import (
    create_session_factory,
    get_raw_archive_by_sha256,
    init_db,
    save_raw_archive_preview,
)
from nmrcheck.raw_vault import (
    RawVaultError,
    build_raw_upload_provenance,
    ingest_raw_archive,
    inspect_raw_archive,
    verify_vault_archive,
)


def _minimal_bruker_acqus() -> str:
    return """##TITLE= immutable vault test
##$TD= 16
##$SW_h= 5000.0
##$SW= 10.0
##$SFO1= 500.0
##$BF1= 500.0
##$O1= 2000.0
##$O1P= 4.0
##$NUC1= <1H>
##$SOLVENT= <D2O>
##$PULPROG= <zg30>
##$TE= 298.0
##$RG= 32
##$AQ= 1.6384
##$BYTORDA= 0
##$DTYPA= 0
"""


def _zip_bytes(entries: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _bruker_zip() -> bytes:
    return _zip_bytes(
        {
            "sample/fid": b"\x00" * 128,
            "sample/acqus": _minimal_bruker_acqus(),
            "sample/pdata/1/procs": "##$SF= 500.13\n##$OFFSET= 14.0\n",
            "sample/pulseprogram": "zg30\n",
        }
    )


def _bruker_tar_gz() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in {
            "sample/ser": b"\x00" * 128,
            "sample/acqus": _minimal_bruker_acqus(),
        }.items():
            payload = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_raw_vault_stores_zip_read_only_with_acquisition_metadata(tmp_path) -> None:
    content = _bruker_zip()
    record = ingest_raw_archive(
        filename="sample.zip",
        content=content,
        vault_dir=tmp_path / "raw_data_vault",
    )

    assert record.raw_archive_id == record.sha256
    assert record.archive_format == "zip"
    assert record.vendor_detected == "Bruker"
    assert record.dataset_root == "sample"
    assert record.required_files_present is True
    assert record.acquisition_metadata["NUC1"] == "1H"
    assert record.acquisition_metadata["nucleus"] == "1H"
    assert record.acquisition_metadata["spectrometer_frequency_mhz"] == 500.0
    assert record.acquisition_metadata["spectral_width_hz"] == 5000.0
    assert record.acquisition_metadata["acquisition_time_sec"] == 1.6384
    assert record.acquisition_metadata["td"] == 16
    assert record.acquisition_metadata["offset_hz"] == 2000.0
    assert record.acquisition_metadata["offset_ppm"] == 4.0
    assert record.acquisition_metadata["solvent"] == "D2O"
    assert record.acquisition_metadata["pulse_program"] == "zg30"
    assert record.acquisition_metadata["temperature_k"] == 298.0
    assert record.acquisition_metadata["receiver_gain"] == 32.0
    assert record.acquisition_metadata["source_files"]["acqus"] == "sample/acqus"
    assert record.acquisition_metadata["raw_files_present"] == ["fid"]
    assert record.storage_path == str(tmp_path / "raw_data_vault" / record.sha256 / "sample.zip")
    assert os.path.isfile(record.storage_path)
    assert os.stat(record.storage_path).st_mode & stat.S_IWUSR == 0
    assert verify_vault_archive(record.to_provenance_dict()) is True


def test_raw_vault_accepts_tar_gz_and_notes_ser_future_support(tmp_path) -> None:
    record = ingest_raw_archive(
        filename="bruker_2d_preview.tar.gz",
        content=_bruker_tar_gz(),
        vault_dir=tmp_path / "raw_data_vault",
    )

    assert record.archive_format == "tar.gz"
    assert record.vendor_detected == "Bruker"
    assert record.acquisition_metadata["raw_files_present"] == ["ser"]
    assert record.acquisition_metadata["supports_future_ser"] is True


def test_raw_vault_rejects_unsafe_zip_paths(tmp_path) -> None:
    content = _zip_bytes({"sample/../evil/fid": b"\x00" * 128, "sample/acqus": _minimal_bruker_acqus()})

    with pytest.raises(RawVaultError, match="unsafe"):
        ingest_raw_archive(filename="unsafe.zip", content=content, vault_dir=tmp_path)


def test_raw_vault_rejects_tar_symlink(tmp_path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        link = tarfile.TarInfo("sample/fid")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        archive.addfile(link)
        payload = _minimal_bruker_acqus().encode()
        acqus = tarfile.TarInfo("sample/acqus")
        acqus.size = len(payload)
        archive.addfile(acqus, io.BytesIO(payload))

    with pytest.raises(RawVaultError, match="link"):
        ingest_raw_archive(filename="unsafe.tar.gz", content=buffer.getvalue(), vault_dir=tmp_path)


def test_raw_vault_enforces_file_count_and_byte_limits(tmp_path) -> None:
    too_many = _zip_bytes({f"sample/file_{idx}.txt": "x" for idx in range(4)})
    with pytest.raises(RawVaultError, match="too many files"):
        ingest_raw_archive(
            filename="too-many.zip",
            content=too_many,
            vault_dir=tmp_path,
            max_files=3,
        )

    content = _bruker_zip()
    with pytest.raises(RawVaultError, match="too large"):
        ingest_raw_archive(
            filename="too-large.zip",
            content=content,
            vault_dir=tmp_path,
            max_bytes=len(content) - 1,
        )


def test_raw_vault_metadata_only_provenance_does_not_store_bytes(tmp_path) -> None:
    content = _bruker_zip()

    provenance = build_raw_upload_provenance(filename="sample.zip", content=content, storage_dir=None)

    assert provenance["storage_backend"] == "metadata_only"
    assert provenance["storage_path"] is None
    assert provenance["raw_bytes_embedded_in_metadata"] is False
    assert provenance["byte_size"] == len(content)
    assert provenance["vendor_detected"] == "Bruker"
    assert not list(tmp_path.iterdir())


def test_raw_vault_inspection_detects_varian_procpar() -> None:
    procpar = """sfrq 500.0
sw 6000.0
tn H1
np 2048
solvent CDCl3
seqfil s2pul
temp 25.0
"""
    content = _zip_bytes({"sample.fid/fid": b"\x00" * 128, "sample.fid/procpar": procpar})

    inspection = inspect_raw_archive(filename="varian.zip", content=content)

    assert inspection["vendor_detected"] == "Varian/Agilent"
    assert inspection["dataset_root"] == "sample.fid"
    assert inspection["dataset_detection"]["required_files_present"] is True
    assert inspection["acquisition_metadata"]["sfrq"] == 500.0
    assert inspection["acquisition_metadata"]["tn"] == "H1"
    assert inspection["acquisition_metadata"]["nucleus"] == "H1"
    assert inspection["acquisition_metadata"]["spectrometer_frequency_mhz"] == 500.0
    assert inspection["acquisition_metadata"]["spectral_width_hz"] == 6000.0
    assert inspection["acquisition_metadata"]["points"] == 2048
    assert inspection["acquisition_metadata"]["solvent"] == "CDCl3"
    assert inspection["acquisition_metadata"]["pulse_sequence"] == "s2pul"
    assert inspection["acquisition_metadata"]["temperature_c"] == 25.0


def test_raw_archive_database_record_is_idempotent(tmp_path) -> None:
    content = _bruker_zip()
    provenance = build_raw_upload_provenance(
        filename="sample.zip",
        content=content,
        storage_dir=tmp_path / "raw_data_vault",
    )
    session_factory = create_session_factory(f"sqlite:///{tmp_path}/raw_archives.sqlite3")
    init_db(session_factory)

    first = save_raw_archive_preview(
        session_factory,
        provenance=provenance,
        user_id=None,
        content_type="application/zip",
    )
    second = save_raw_archive_preview(
        session_factory,
        provenance=provenance,
        user_id=None,
        content_type="application/zip",
    )
    loaded = get_raw_archive_by_sha256(session_factory, sha256=provenance["sha256"])

    assert first.already_stored is False
    assert second.already_stored is True
    assert second.archive.id == first.archive.id
    assert loaded is not None
    assert loaded.id == first.archive.id
    assert loaded.sha256 == provenance["sha256"]
    assert loaded.storage_path == provenance["storage_path"]
    assert loaded.filename == "sample.zip"
    assert loaded.content_type == "application/zip"
    assert loaded.vendor_detected == "Bruker"
    assert loaded.dataset_root == "sample"
    assert loaded.required_files_present is True
    assert loaded.immutable is True
    assert loaded.files_found == provenance["files_found"]
    assert loaded.acquisition_metadata["NUC1"] == "1H"
    assert loaded.acquisition_metadata["nucleus"] == "1H"
    assert loaded.acquisition_metadata["spectrometer_frequency_mhz"] == 500.0
    assert loaded.acquisition_metadata["pulse_program"] == "zg30"
