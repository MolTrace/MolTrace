"""Pins the Phase 12 fix: the 3 NMRShiftDB2 fixtures the FE A/B run flagged
as "0 peaks from both detectors" via the legacy ``/nmr/raw-fid/process``
route now return peaks again.

Root cause was the strict ``SpectrumPoint.shift_ppm`` bound (-50..260 ppm)
rejecting trace samples from real 13C spectra that contain wrap-around
artifacts or off-referenced regions above 260 ppm.  A single out-of-range
edge sample tanked the whole response (Pydantic ValidationError → HTTP 400
wrapped as "produced data outside the accepted upload range"), causing the
route to return zero peaks for spectra that GSD had no trouble with.

Phase 12b widened ``SpectrumPoint`` bounds to ±500 ppm so display-only
trace samples no longer reject the whole response.  This test pins the
behaviour so a future tightening of ``SpectrumPoint`` bounds breaks
loudly rather than silently re-introducing the 0-peak bug.

Marked ``slow`` because 60000006_13c currently takes ~5 minutes through
the structure-guided peak-sensitivity sweep (separate Phase 12d perf
work tracks reducing this).  Skipped by default in fast CI; explicitly
runnable via ``pytest -m slow tests/test_raw_fid_process_zero_peak_regression.py``.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from tempfile import mkdtemp

import pytest
from fastapi import UploadFile
from starlette.requests import Request

from nmrcheck.api import (
    AccessContext,
    create_app,
    nmr_raw_fid_process_route,
)
from nmrcheck.database import init_db
from nmrcheck.settings import Settings

_FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures" / "nmrshiftdb2" / "raw"


def _build_request() -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-zero-peak-regress-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/zero_peak.sqlite3",
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
            "path": "/nmr/raw-fid/process",
            "query_string": b"",
        }
    )


async def _process(fixture_zip: Path) -> int:
    request = _build_request()
    content = fixture_zip.read_bytes()
    result = await nmr_raw_fid_process_route(
        request=request,
        file=UploadFile(filename=fixture_zip.name, file=io.BytesIO(content)),
        sample_id="zero-peak-regression",
        solvent="CDCl3",
        nucleus="13C",
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
    return result.peak_count


@pytest.mark.parametrize(
    "fixture_name",
    [
        "nmrshiftdb2_60003434_13c.zip",
        "nmrshiftdb2_60003436_13c.zip",
    ],
)
def test_raw_fid_process_no_longer_zero_peaks(fixture_name: str) -> None:
    """The 2 fast-recovery fixtures must return >0 peaks via legacy route."""

    fixture_zip = _FIXTURES_ROOT / fixture_name
    if not fixture_zip.exists():
        pytest.skip(f"Fixture {fixture_name} not present in test bundle")
    peak_count = asyncio.run(_process(fixture_zip))
    assert peak_count > 0, (
        f"{fixture_name} returned 0 peaks via /nmr/raw-fid/process. "
        "This regression indicates SpectrumPoint bounds (or another model "
        "validation) is rejecting trace samples again. See Phase 12b for "
        "context (widened bounds to ±500 ppm)."
    )


def test_raw_fid_process_recovers_dense_13c_60000006() -> None:
    """The previously-slow fixture (was 241s zero-peak, then 5.5 min) now ~40s.

    Trajectory:
      * Pre-Phase-12b: 0 peaks (HTTP 400 from SpectrumPoint validation).
      * Post-Phase-12b: 51 peaks in 331s.
      * Post-Phase-12d (vectorized _pseudo_voigt_sum): 51 peaks in 215s.
      * Post-Phase-12d-bis (analytical jacobian): 51 peaks in ~40s.

    Now fast enough to run by default in the regular suite (no slow marker).
    """

    fixture_zip = _FIXTURES_ROOT / "nmrshiftdb2_60000006_13c.zip"
    if not fixture_zip.exists():
        pytest.skip("Fixture not present in test bundle")
    peak_count = asyncio.run(_process(fixture_zip))
    assert peak_count > 0, (
        "60000006_13c returned 0 peaks via /nmr/raw-fid/process. "
        "This was the FE-flagged 241s zero-peak case fixed in Phase 12b; "
        "perf was dropped from 5.5 min to ~40s by Phase 12d + 12d-bis."
    )
