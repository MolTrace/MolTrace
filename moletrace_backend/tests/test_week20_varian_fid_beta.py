import io
import zipfile

from nmrcheck.fid import inspect_zip_members


def make_zip(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_varian_agilent_zip_detection_requires_fid_and_procpar() -> None:
    content = make_zip(
        {
            "sample.fid/fid": b"raw-varian-bytes",
            "sample.fid/procpar": b"sw 8000\n",
            "sample.fid/log": b"test",
        }
    )

    preview = inspect_zip_members(content, filename="sample_varian.zip")

    assert preview.vendor_detected == "Varian/Agilent"
    assert preview.required_files_present is True
    assert preview.dataset_root == "sample.fid"


def test_varian_agilent_missing_procpar_warns() -> None:
    content = make_zip({"sample.fid/fid": b"raw-varian-bytes"})

    preview = inspect_zip_members(content, filename="bad_varian.zip")

    assert preview.vendor_detected == "Varian/Agilent"
    assert preview.required_files_present is False
    assert any("procpar" in warning for warning in preview.warnings)
