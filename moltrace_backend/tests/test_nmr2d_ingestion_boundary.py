"""Where 2D data can and cannot enter the system — pinned, because it is a cliff.

C2 of `docs/validation_playbook_2d_nmr.md` asks for axis assignment, per-dimension
referencing, magnitude-vs-phase-sensitive handling and folding to be checked
against the acquisition parameters. Measured against real fixtures, none of those
can be checked, for one reason: **no vendor 2D dataset can enter the system at
all.** The 2D layer receives peak lists and display-only matrices; the only code
that opens a Bruker directory is the 1D FID reader, and it requires `fid`, which a
2D acquisition does not have (it has `ser`).

That is a documented boundary, not a hidden defect — `parse_2d_matrix_preview`
stamps `raw_2d_fid_processing: not_implemented_guarded_release` and returns no
peaks. These tests exist so the boundary cannot move silently.

The dangerous change is not "someone adds 2D support". It is someone widening the
1D reader to accept `ser` because a user complained about the error message. A 2D
`ser` is *interleaved* — one row per t1 increment, concatenated. Read as a 1D FID
it Fourier-transforms into something with peaks, a plausible ppm axis, and no
outward sign of being wrong. Every downstream number would then be confident
nonsense about a spectrum that does not exist. So the rejection is the invariant,
and it must be replaced by real 2D handling rather than merely relaxed.

UPDATE (2026-08-20): this file's guard turned out to be vendor-shaped, and the
failure above had already happened on the other vendor. Varian/Agilent writes 2D
and *arrayed* data to a file named `fid`, so detection accepted it and the reader
concatenated the records exactly as described. That hole is closed at the engine
by `_as_1d_fid`, and pinned vendor-independently in
`tests/test_fid_dimensionality_refusal.py`. These tests still pin the Bruker
detection boundary; they are no longer the only thing standing between a 2D
dataset and a meaningless spectrum.
"""

from __future__ import annotations

import io
import zipfile

import pytest

pytest.importorskip("nmrglue")

from fixture_pointer import fixture_reason, resolve_fixture

_ROLE = "nmr2d_hsqc_1"


def _fixture():
    d = resolve_fixture(_ROLE)
    if d is None or not (d / "ser").exists():
        pytest.skip(fixture_reason(_ROLE))
    return d


def _zip_2d(directory) -> bytes:
    """A 2D acquisition packaged the way a user would drop the folder in."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("ser", "acqus", "acqu2s", "pulseprogram"):
            path = directory / name
            if path.exists():
                archive.write(path, f"dataset/{name}")
        for name in ("2rr", "procs", "proc2s"):
            path = directory / "pdata" / "1" / name
            if path.exists():
                archive.write(path, f"dataset/pdata/1/{name}")
    return buffer.getvalue()


class TestTheOneDReaderRefusesTwoDData:
    def test_read_fid_rejects_a_2d_dataset_directory(self) -> None:
        from moltrace.spectroscopy.io.fid_reader import FIDReaderError, read_fid

        directory = _fixture()
        # Guard the premise: if this ever grows a `fid`, the test below proves
        # nothing and the skip would be silent.
        assert not (directory / "fid").exists(), "fixture is no longer 2D-only"

        with pytest.raises(FIDReaderError):
            read_fid(str(directory))

    def test_the_1d_upload_path_names_what_is_missing(self) -> None:
        """The rejection has to say `fid`, not just fail.

        A user who dropped an HSQC folder onto the 1D uploader needs to learn
        which file was expected. "Could not process" sends them to support; naming
        `fid` tells them they picked a 2D experiment. Bounds and rejections name
        their cause -- the same rule the acquisition gate follows.
        """
        from nmrcheck.fid import FIDProcessingError, process_bruker_1d_zip

        with pytest.raises(FIDProcessingError) as caught:
            process_bruker_1d_zip(filename="dataset.zip", content=_zip_2d(_fixture()))

        message = str(caught.value).lower()
        assert "fid" in message
        assert "acqus" in message, "the message should say the folder WAS recognised as Bruker"


class TestTheMatrixPreviewClaimsNothingItDoesNotDo:
    """No fixture needed, so this half runs in CI where the spectra never exist."""

    def test_a_matrix_upload_yields_no_peaks_and_says_so(self) -> None:
        import json

        from nmrcheck.nmr2d_parser import parse_2d_matrix_preview

        # Shape per `_is_json_matrix_payload`: axis lists named f2_axis/f1_axis,
        # and `intensity` as rows indexed by F1. Rows are the indirect dimension.
        payload = {
            "experiment": "HSQC",
            "f2_axis": [1.0, 2.0],
            "f1_axis": [10.0, 20.0],
            "intensity": [[1.0, 2.0], [3.0, 4.0]],
        }
        preview = parse_2d_matrix_preview(
            "matrix.json", json.dumps(payload).encode(), experiment_hint="HSQC"
        )

        # The contract that keeps a contour picture from being read as evidence.
        assert preview.peak_count == 0
        assert list(preview.peaks) == []
        assert preview.metadata["contour_preview_affects_evidence_score"] is False
        assert preview.metadata["raw_2d_fid_processing"] == "not_implemented_guarded_release"
        assert any("does not affect evidence scoring" in w for w in preview.warnings)
        assert any("Raw 2D FID/SER processing is not performed" in w for w in preview.warnings)
