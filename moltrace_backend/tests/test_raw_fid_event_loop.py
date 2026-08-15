"""The raw-FID routes must not freeze the event loop while they compute.

Measured on a real 2.5 MB Bruker archive (2026-08, dev M-series Mac): the
preview/process pipeline ran 6.8 s *on the asyncio event loop*, so concurrent
requests queued behind it and a burst of uploads pushed wall times to 40-78 s —
the instance was frozen, not busy. The fix wraps ``process_bruker_1d_zip`` in
``starlette.concurrency.run_in_threadpool`` on every async route.

This test proves the property directly: while the preview route coroutine runs
on a synthetic multi-second archive, a heartbeat coroutine on the same loop
must keep ticking. If the pipeline ran inline, the largest heartbeat gap would
equal the whole compute time; with the threadpool it stays at scheduler noise.
"""

from __future__ import annotations

import asyncio
import io
import time
import zipfile
from tempfile import mkdtemp

import numpy as np
from fastapi import UploadFile
from starlette.requests import Request

from nmrcheck.api import (
    AccessContext,
    create_app,
    nmr_raw_fid_preview_route,
)
from nmrcheck.database import init_db
from nmrcheck.settings import Settings

# Big enough that the pipeline takes >1 s (32k complex points zero-fill to a
# >=196k FFT, the size of a real 2.5 MB archive), small enough to build fast.
_POINTS = 32768
# Inline-vs-threadpool is a RATIO question, not an absolute one, and pinning it
# to seconds made this gate fail on the hardware it is supposed to run on: an
# absolute 0.5 s (picked as "generous against CI scheduler noise") measured
# 0.529 s on a CI runner and turned a green pipeline red.
#
# Measured, cold cache, eight runs on a dev M-series Mac: wall 2.0-2.6 s, largest
# gap 0.074-0.243 s -- a ratio of 0.036-0.106. The CI run that failed: wall
# 5.78 s, gap 0.529 s -- a ratio of 0.092, squarely inside the same band. The
# absolute number moved with the hardware; the ratio did not. A bound in seconds
# sitting at roughly twice the fast-machine maximum is a coin flip on a runner
# 2-3x slower, which is a flaky gate on the deploy path, not a science gate.
#
# The property this test actually asserts survives the change intact, because it
# was always a ratio: an INLINE pipeline starves the loop for essentially the
# whole request (ratio -> 1.0), a threadpooled one only for scheduler slices.
# 0.35 leaves >3x headroom over the worst gap ever observed and still trips at a
# third of the inline signature.
_MAX_GAP_FRACTION_OF_WALL = 0.35

# A floor that proves the pipeline actually ran, which the ratio alone does not.
# The report cache landed with this same work and returns a completed report for
# an archive it has already seen without touching the pipeline: measured, a
# repeat of this exact request in-process drops the wall from 2.3 s to 0.08 s.
# The heartbeat across a cache hit is beautifully flat and means nothing, so the
# test has to refuse to draw a conclusion from one. Cold wall is >=2 s on the
# fastest machine here and was 5.78 s on CI, so this floor only ever catches the
# cache.
_MIN_MEANINGFUL_WALL_S = 0.75


def _bruker_zip(points: int = _POINTS) -> bytes:
    sw_hz = 5000.0
    sfo1_mhz = 400.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in [(7.26, 0.4), (3.65, 1.0), (1.26, 0.65)]:
        freq = (ppm - center_ppm) * sfo1_mhz
        fid += amplitude * np.exp(2j * np.pi * freq * time_axis) * np.exp(-time_axis * 2.0)
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = (
        "##TITLE= event loop responsiveness fixture\n"
        f"##$TD= {points * 2}\n"
        f"##$SW_h= {sw_hz}\n"
        "##$SW= 12.5\n"
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
    tmpdir = mkdtemp(prefix="nmrcheck-fid-loop-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/loop.sqlite3",
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


def test_preview_route_keeps_event_loop_responsive() -> None:
    request = _build_request()
    archive = _bruker_zip()

    async def run() -> None:
        gaps: list[float] = []
        done = asyncio.Event()

        async def heartbeat() -> None:
            last = time.perf_counter()
            while not done.is_set():
                await asyncio.sleep(0.005)
                now = time.perf_counter()
                gaps.append(now - last)
                last = now

        async def route() -> None:
            try:
                result = await nmr_raw_fid_preview_route(
                    request=request,
                    file=UploadFile(filename="sample.zip", file=io.BytesIO(archive)),
                    sample_id="loop-responsiveness-test",
                    solvent="CDCl3",
                    nucleus="1H",
                    vendor="auto",
                    processing_preset="balanced",
                    include_spectrum=True,
                    compound_class=None,
                    candidates_text=None,
                    proton_nmr_text=None,
                    carbon13_text=None,
                    context=AccessContext(system_api_key=True),
                )
                assert result.point_count > 0
            finally:
                done.set()

        t0 = time.perf_counter()
        await asyncio.gather(heartbeat(), route())
        wall = time.perf_counter() - t0

        assert gaps, "heartbeat never ticked"
        max_gap = max(gaps)
        assert wall > _MIN_MEANINGFUL_WALL_S, (
            f"the preview returned in {wall:.2f}s, too fast to have run the "
            "pipeline — this is a report-cache hit, and a heartbeat measured "
            "across one says nothing about where the compute ran"
        )
        assert max_gap < wall * _MAX_GAP_FRACTION_OF_WALL, (
            f"event loop starved for {max_gap:.3f}s of a {wall:.2f}s preview "
            f"request ({max_gap / wall:.0%} of it) — the FID pipeline is running "
            "inline on the loop instead of in the threadpool"
        )

    asyncio.run(run())
