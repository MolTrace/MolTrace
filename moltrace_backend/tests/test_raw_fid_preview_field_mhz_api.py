"""Test that NMRRawFIDPreviewResponse exposes a normalized field_mhz.

Phase 8c: the FE's raw-FID surface had no spectrometer-MHz user input, so it
was hardcoding ``field_mhz=500`` when forwarding to ``/spectrum/analyze/gsd``.
This test pins the backend contract that ``/nmr/raw-fid/preview`` returns
``field_mhz`` parsed from the vendor acquisition metadata (Bruker SFO1/BF1
or Varian sfrq/reffrq), so the FE can plumb the authoritative value through.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from tempfile import mkdtemp

import numpy as np
from fastapi import UploadFile
from starlette.requests import Request

from nmrcheck.api import (
    AccessContext,
    create_app,
    nmr_raw_fid_preview_route,
    nmr_raw_fid_process_route,
)
from nmrcheck.database import init_db
from nmrcheck.settings import Settings


def _bruker_zip(sfo1_mhz: float) -> bytes:
    """Minimal valid Bruker 1D zip with a fitted SFO1 value in acqus.

    Mirrors the synthesis in tests/test_fid.py::_build_bruker_zip but
    inlined here to avoid coupling to that file (which carries unrelated
    in-flight modifications).
    """

    points = 1024
    sw_hz = 5000.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65)]:
        freq = (ppm - center_ppm) * sfo1_mhz
        fid += (
            amplitude
            * np.exp(2j * np.pi * freq * time_axis)
            * np.exp(-time_axis * 10.0)
        )
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = (
        "##TITLE= field_mhz test fixture\n"
        f"##$TD= {points * 2}\n"
        f"##$SW_h= {sw_hz}\n"
        "##$SW= 10.0\n"
        f"##$SFO1= {sfo1_mhz}\n"
        f"##$BF1= {sfo1_mhz}\n"
        f"##$O1= {center_ppm * sfo1_mhz}\n"
        f"##$O1P= {center_ppm}\n"
        "##$NUC1= <1H>\n"
        "##$BYTORDA= 0\n"
        "##$DTYPA= 0\n"
        "##$GRPDLY= 0\n"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("sample/fid", interleaved.tobytes())
        archive.writestr("sample/acqus", acqus)
        archive.writestr("sample/pulseprogram", "zg30\n")
    return buffer.getvalue()


def _build_request() -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-fid-field-mhz-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/field_mhz.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    init_db(app.state.session_factory)
    return Request(
        {
            "type": "http",
            "app": app,
            "headers": [],
            "method": "POST",
            "path": "/nmr/raw-fid/preview",
            "query_string": b"",
        }
    )


def _build_upload(sfo1_mhz: float) -> UploadFile:
    return UploadFile(
        filename="sample.zip",
        file=io.BytesIO(_bruker_zip(sfo1_mhz)),
    )


def test_raw_fid_preview_exposes_field_mhz_from_acqus_sfo1() -> None:
    """Bruker SFO1 must surface as the normalized field_mhz field."""

    request = _build_request()

    async def run() -> None:
        result = await nmr_raw_fid_preview_route(
            request=request,
            file=_build_upload(sfo1_mhz=500.13),
            sample_id="field-mhz-test",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            include_spectrum=False,
            compound_class=None,
            candidates_text=None,
            proton_nmr_text=None,
            carbon13_text=None,
            context=AccessContext(system_api_key=True),
        )

        assert result.field_mhz is not None, (
            "field_mhz must be populated from acqus metadata so the FE can "
            "stop hardcoding 500 MHz when forwarding to /spectrum/analyze/gsd."
        )
        assert abs(result.field_mhz - 500.13) < 0.01, (
            f"field_mhz must echo the SFO1 value, got {result.field_mhz}"
        )
        # acquisition_parameters must still carry the raw value too (for
        # callers that want the full vendor key set).
        assert "SFO1" in result.acquisition_parameters
        assert abs(float(result.acquisition_parameters["SFO1"]) - 500.13) < 0.01

    asyncio.run(run())


def test_raw_fid_preview_field_mhz_handles_atypical_frequency() -> None:
    """Verify the helper actually reads the value rather than returning a default."""

    request = _build_request()

    async def run() -> None:
        result = await nmr_raw_fid_preview_route(
            request=request,
            file=_build_upload(sfo1_mhz=800.0),  # high-field magnet
            sample_id="field-mhz-test-2",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            include_spectrum=False,
            compound_class=None,
            candidates_text=None,
            proton_nmr_text=None,
            carbon13_text=None,
            context=AccessContext(system_api_key=True),
        )

        assert result.field_mhz is not None
        assert abs(result.field_mhz - 800.0) < 0.01, (
            f"800 MHz fixture returned field_mhz={result.field_mhz}; helper "
            "must read the actual SFO1, not return a hardcoded default."
        )

    asyncio.run(run())


def test_raw_fid_process_exposes_field_mhz_for_fe_plumbing() -> None:
    """Process route must mirror the preview route's field_mhz exposure.

    The FE plumbing pattern is ``previewResult?.field_mhz ?? processResult?.field_mhz ?? 500``.
    For tenants who run the spectrum through ``/nmr/raw-fid/process`` (the
    next lifecycle stage after preview) without re-uploading, the process
    response is the only source of the spectrometer frequency.
    """

    request = _build_request()

    async def run() -> None:
        result = await nmr_raw_fid_process_route(
            request=request,
            file=_build_upload(sfo1_mhz=600.13),
            sample_id="field-mhz-process-test",
            solvent="CDCl3",
            nucleus="1H",
            vendor="auto",
            processing_preset="balanced",
            preserve_raw=True,
            include_spectrum=False,
            compound_class=None,
            candidates_text=None,
            proton_nmr_text=None,
            carbon13_text=None,
            context=AccessContext(system_api_key=True),
        )

        assert result.field_mhz is not None, (
            "Process response must surface field_mhz so the FE plumbing chain "
            "returns a real value when the user is past the preview stage."
        )
        assert abs(result.field_mhz - 600.13) < 0.01, (
            f"process route returned field_mhz={result.field_mhz}; expected 600.13"
        )
