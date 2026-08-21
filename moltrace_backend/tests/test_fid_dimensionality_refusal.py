"""Multi-dimensional raw data must be refused, never flattened into a pseudo-FID.

`tests/test_nmr2d_ingestion_boundary.py` already pins the *Bruker* half of this
boundary, and states the invariant it protects: a 2D acquisition read as a 1D FID
"Fourier-transforms into something with peaks, a plausible ppm axis, and no
outward sign of being wrong." That guard lives at dataset **detection** — Bruker
writes 2D to `ser`, the reader only looks for `fid`, so the folder is never found.

Detection is the wrong place for the guard to be the only one, because it is
vendor-shaped. Varian/Agilent stores 2D and *arrayed* experiments in a file named
`fid` next to `procpar` — the exact pair detection accepts. Those datasets reached
the reader's flatten (`_flatten_1d_fid`, now `_as_1d_fid`), which concatenated every
record end to end with `reshape(-1)` and returned a spectrum. The repository's own
`arrayed_data.dir` fixture (26 records x 1500 points) came back as a
39,000-point pseudo-FID processed into a
65,536-point 13C spectrum spanning ~199 to ~-199 ppm: no exception, no warning, no
metadata flag. A confident wrong answer, which is worse than a refusal.

So the invariant is pinned here at the **engine**, where it is vendor-independent:
a real second dimension is refused by name. A trailing length-1 axis is not a
second dimension and still passes, because `.squeeze()` removes it.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import numpy as np
import pytest

ng = pytest.importorskip("nmrglue")

from nmrglue.fileio.varian import create_pdic_param  # noqa: E402

from moltrace.spectroscopy.io.fid_reader import (  # noqa: E402
    FIDReaderError,
    _as_1d_fid,
    read_fid,
)

# The nmrglue `separate_1d_varian` example: a real vendor **arrayed** dataset,
# BSD-3-Clause, already tracked (see fixtures/nmrglue/varian/README.md). Not
# maintainer data, so it is safe to name in tracked code.
_ARRAYED_VARIAN = (
    Path(__file__).parent
    / "fixtures"
    / "nmrglue"
    / "varian"
    / "extracted"
    / "example_separate_1d_varian"
    / "separate_1d_varian"
    / "arrayed_data.dir"
)

# Transport-layer vocabulary that must never reach a chemist. Matched as whole
# words -- a bare "500" substring would also match "1500 points", which is the
# record length and exactly the thing the message is supposed to say.
_BACKEND_JARGON = (
    r"http",
    r"endpoint",
    r"/api",
    r"\b(?:400|401|403|404|409|422|500|502|503)\b",
    r"\bpost\b",
    r"\bpayload\b",
    r"_json",
    r"\bbackend\b",
    r"\bndim\b",
    r"\breshape\b",
    r"\btraceback\b",
)


def _assert_names_its_cause(message: str) -> None:
    """A rejection names what was wrong, in the user's vocabulary."""
    lowered = message.lower()
    for pattern in _BACKEND_JARGON:
        assert not re.search(pattern, lowered), (
            f"backend jargon {pattern!r} in user-facing message: {message}"
        )
    assert any(
        word in lowered for word in ("2d", "two-dimensional", "arrayed", "record")
    ), f"message does not name the cause: {message}"


def _write_varian_2d(root: Path, *, n_records: int = 8, points: int = 512) -> Path:
    """A 2D Varian/Agilent dataset: a directory holding `fid` + `procpar`."""
    dataset = root / "sample_2d.fid"
    udic = ng.fileiobase.create_blank_udic(2)
    udic[1].update(
        {"size": points, "complex": True, "sw": 5000.0, "obs": 500.0, "car": 4.0 * 500.0,
         "label": "H1", "time": True, "freq": False}
    )
    udic[0].update(
        {"size": n_records, "complex": True, "sw": 2000.0, "obs": 500.0, "car": 4.0 * 500.0,
         "label": "H1", "time": True, "freq": False}
    )
    dictionary = ng.varian.create_dic(udic)
    for key, value in {
        "sw": 5000.0,
        "sfrq": 500.0,
        "tof": 4.0 * 500.0,
        "tn": "H1",
        "solvent": "CDCl3",
        "seqfil": "s2pul",
    }.items():
        dictionary["procpar"][key] = create_pdic_param(key, [str(value)])

    time_axis = np.arange(points, dtype=np.float64) / 5000.0
    data = np.zeros((n_records, points), dtype=np.complex64)
    for index in range(n_records):
        frequency = (3.6 - 4.0 + 0.05 * index) * 500.0
        data[index] = (
            np.exp(-2j * np.pi * frequency * time_axis) * np.exp(-time_axis * 8.0) * 1_000.0
        )
    ng.varian.write(str(dataset), dictionary, data, overwrite=True)
    return dataset


class TestTheEngineRefusesASecondDimension:
    def test_a_two_dimensional_array_is_refused_not_flattened(self) -> None:
        fid = np.ones((8, 512), dtype=np.complex128)

        with pytest.raises(FIDReaderError) as caught:
            _as_1d_fid(fid)

        _assert_names_its_cause(str(caught.value))

    def test_the_refusal_states_the_shape_it_found(self) -> None:
        """"Unsupported" sends a chemist to support; the record count explains it."""
        with pytest.raises(FIDReaderError) as caught:
            _as_1d_fid(np.ones((26, 1500), dtype=np.complex128))

        message = str(caught.value)
        assert "26" in message, f"record count missing from: {message}"
        assert "1500" in message or "1,500" in message, f"record length missing from: {message}"

    @pytest.mark.parametrize("shape", [(2048, 1), (1, 2048), (1, 2048, 1)])
    def test_a_trailing_length_one_axis_is_not_a_second_dimension(self, shape) -> None:
        """A genuine 1-length axis is squeezed away — that path must keep working."""
        fid = np.ones(shape, dtype=np.complex128)

        result = _as_1d_fid(fid)

        assert result.ndim == 1
        assert result.size == 2048

    def test_a_one_dimensional_fid_is_unchanged(self) -> None:
        fid = np.arange(64, dtype=np.complex128)

        result = _as_1d_fid(fid)

        assert result.ndim == 1
        np.testing.assert_allclose(result, fid)


class TestTheVarianPathThatDetectionNeverCovered:
    def test_a_synthetic_two_dimensional_varian_dataset_is_refused(self, tmp_path: Path) -> None:
        dataset = _write_varian_2d(tmp_path)
        # Guard the premise: this must be the file pair detection accepts, or the
        # test would pass for the wrong reason.
        assert (dataset / "fid").is_file() and (dataset / "procpar").is_file()

        with pytest.raises(FIDReaderError) as caught:
            read_fid(dataset)

        _assert_names_its_cause(str(caught.value))

    def test_the_real_arrayed_fixture_is_refused(self) -> None:
        """The regression that reproduced this: a tracked vendor arrayed dataset."""
        if not (_ARRAYED_VARIAN / "fid").is_file():
            pytest.skip("nmrglue Varian example fixture is not extracted")

        with pytest.raises(FIDReaderError) as caught:
            read_fid(_ARRAYED_VARIAN)

        _assert_names_its_cause(str(caught.value))


class TestTheUploadPathRefusesItToo:
    """The engine refusing is only useful if the refusal survives to the operator."""

    def _zip_dataset(self, directory: Path) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(directory.iterdir()):
                if path.is_file():
                    archive.write(path, f"{directory.name}/{path.name}")
        return buffer.getvalue()

    def test_an_arrayed_varian_upload_is_refused_with_its_cause(self) -> None:
        from nmrcheck.fid import FIDProcessingError, process_bruker_1d_zip

        if not (_ARRAYED_VARIAN / "fid").is_file():
            pytest.skip("nmrglue Varian example fixture is not extracted")

        with pytest.raises(FIDProcessingError) as caught:
            process_bruker_1d_zip(
                filename="arrayed.zip", content=self._zip_dataset(_ARRAYED_VARIAN)
            )

        _assert_names_its_cause(str(caught.value))

    def test_the_processing_reader_refuses_a_second_dimension(self) -> None:
        """`nmrcheck.fid` carries its own copy of the reader — same rule applies."""
        from nmrcheck.fid import FIDProcessingError
        from nmrcheck.fid import _as_1d_fid as processing_as_1d

        with pytest.raises(FIDProcessingError) as caught:
            processing_as_1d(np.ones((26, 1500), dtype=np.complex128))

        _assert_names_its_cause(str(caught.value))

    @pytest.mark.parametrize("shape", [(2048, 1), (1, 2048)])
    def test_the_processing_reader_still_squeezes_a_length_one_axis(self, shape) -> None:
        from nmrcheck.fid import _as_1d_fid as processing_as_1d

        assert processing_as_1d(np.ones(shape, dtype=np.complex128)).size == 2048

    def test_both_readers_say_the_same_thing(self) -> None:
        """Two copies of the wording is two places for it to drift.

        Both modules carry their own message builder rather than importing one,
        because `nmrcheck.fid` has no other dependency on `moltrace.spectroscopy`
        and this is not worth creating one. That choice is only safe if something
        holds them together -- a user reaching either reader must not get a
        different account of what happened.
        """
        from moltrace.spectroscopy.io.fid_reader import (
            _multidimensional_fid_message as reader_message,
        )
        from nmrcheck.fid import _multidimensional_fid_message as processing_message

        for shape in [(26, 1500), (8, 512), (4, 8, 1024)]:
            assert reader_message(shape) == processing_message(shape)


class TestCustodyAndProcessabilityAgree:
    """A `ser` archive is accepted into the vault but cannot be processed.

    Keeping the archive is right — a raw-data vault takes custody of what the
    instrument produced, and refusing to store a 2D experiment would lose data.
    What is wrong is calling the dataset complete and saying nothing, so the
    operator learns it is unusable only when processing fails later.
    """

    def _tar_gz(self, files: dict[str, bytes]) -> bytes:
        import tarfile

        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name, payload in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
        return buffer.getvalue()

    def test_a_ser_only_archive_is_stored_but_flagged_unprocessable(self) -> None:
        from nmrcheck.raw_vault import inspect_raw_archive

        content = self._tar_gz(
            {
                "dataset/ser": b"\x00" * 4096,
                "dataset/acqus": b"##$NUC1= <1H>\n##$SW_h= 5000\n",
                "dataset/acqu2s": b"##$TD= 8\n",
            }
        )

        inspection = inspect_raw_archive(filename="dataset.tar.gz", content=content)

        assert inspection["vendor_detected"] == "Bruker"
        joined = " ".join(inspection["warnings"]).lower()
        assert joined, "a ser-only dataset was accepted with no warning at all"
        assert "ser" in joined, f"the warning does not name `ser`: {joined}"
        assert any(
            word in joined for word in ("2d", "two-dimensional", "not processed", "cannot")
        ), f"the warning does not say it is unprocessable: {joined}"

    def test_a_complete_1d_bruker_archive_is_not_flagged(self) -> None:
        """The warning must be specific to `ser`, not fire on every Bruker upload."""
        from nmrcheck.raw_vault import inspect_raw_archive

        content = self._tar_gz(
            {
                "dataset/fid": b"\x00" * 4096,
                "dataset/acqus": b"##$NUC1= <1H>\n##$SW_h= 5000\n",
            }
        )

        inspection = inspect_raw_archive(filename="dataset.tar.gz", content=content)

        assert inspection["vendor_detected"] == "Bruker"
        joined = " ".join(inspection["warnings"]).lower()
        assert "ser" not in joined, f"a 1D dataset was warned about `ser`: {joined}"
