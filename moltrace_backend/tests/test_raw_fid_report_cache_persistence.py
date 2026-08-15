"""The 400x raw-FID report cache must survive a process restart (Prompt 2, A2).

Measured before this change: 6.837 s cold, 0.017 s warm — but the warm number
lived in ``fid.py:_RAW_FID_PROCESS_CACHE``, an in-process OrderedDict that dies
on every Cloud Run scale-to-zero and misses across autoscaled instances. These
tests pin the L2: the derived report persisted in ``raw_fid_report_cache`` and
found again by a *different process* (simulated by clearing the in-process dict
between calls against the same database).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np

from nmrcheck.database import create_session_factory, init_db
from nmrcheck.fid import _RAW_FID_PROCESS_CACHE, process_bruker_1d_zip


def _bruker_zip(*, title: str, points: int = 2048) -> bytes:
    """A minimal Bruker archive whose bytes are unique per ``title``.

    The cache key is content-addressed, so two tests sharing identical bytes
    would serve each other's L1 entries and mask what each test measures.
    """
    sw_hz = 5000.0
    sfo1_mhz = 400.0
    center_ppm = 4.0
    time_axis = np.arange(points, dtype=float) / sw_hz
    fid = np.zeros(points, dtype=np.complex128)
    for ppm, amplitude in [(3.65, 1.0), (1.26, 0.65)]:
        freq = (ppm - center_ppm) * sfo1_mhz
        fid += amplitude * np.exp(2j * np.pi * freq * time_axis) * np.exp(-time_axis * 8.0)
    interleaved = np.empty(points * 2, dtype="<i4")
    interleaved[0::2] = np.real(fid * 1_000_000).astype("<i4")
    interleaved[1::2] = np.imag(fid * 1_000_000).astype("<i4")
    acqus = (
        f"##TITLE= {title}\n"
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


def test_report_cache_survives_process_restart(tmp_path: Path) -> None:
    session_factory = create_session_factory(f"sqlite:///{tmp_path}/l2.sqlite3")
    init_db(session_factory)
    archive = _bruker_zip(title="restart-survival")
    _RAW_FID_PROCESS_CACHE.clear()

    cold = process_bruker_1d_zip(
        filename="sample.zip",
        content=archive,
        solvent="CDCl3",
        nucleus="1H",
        session_factory=session_factory,
    )
    cold_cache_meta = (cold.metadata or {}).get("raw_fid_processing_cache") or {}
    assert cold_cache_meta.get("hit") is False

    # A scale-to-zero restart loses exactly the in-process dict, nothing else.
    _RAW_FID_PROCESS_CACHE.clear()

    warm = process_bruker_1d_zip(
        filename="sample.zip",
        content=archive,
        solvent="CDCl3",
        nucleus="1H",
        session_factory=session_factory,
    )
    warm_cache_meta = (warm.metadata or {}).get("raw_fid_processing_cache") or {}
    assert warm_cache_meta.get("hit") is True, (
        "identical (archive, settings) request after a simulated restart must be "
        "served from the persisted report cache, not recomputed"
    )

    assert [
        (p.shift_ppm, p.integration_h, p.multiplicity) for p in warm.inferred_peaks
    ] == [(p.shift_ppm, p.integration_h, p.multiplicity) for p in cold.inferred_peaks]
    assert warm.point_count == cold.point_count
    assert len(warm.preview_points) == len(cold.preview_points)


def test_report_cache_shared_across_app_instances(tmp_path: Path) -> None:
    """Two apps on the same database behave like two Cloud Run instances."""

    from nmrcheck.api import create_app
    from nmrcheck.settings import Settings

    database_url = f"sqlite:///{tmp_path}/shared.sqlite3"
    archive = _bruker_zip(title="cross-instance-sharing")
    _RAW_FID_PROCESS_CACHE.clear()

    app_a = create_app(
        Settings(database_url=database_url, require_verified_email=False, api_key="k")
    )
    init_db(app_a.state.session_factory)
    first = process_bruker_1d_zip(
        filename="sample.zip",
        content=archive,
        solvent="CDCl3",
        nucleus="1H",
        session_factory=app_a.state.session_factory,
    )
    assert ((first.metadata or {}).get("raw_fid_processing_cache") or {}).get("hit") is False

    _RAW_FID_PROCESS_CACHE.clear()

    app_b = create_app(
        Settings(database_url=database_url, require_verified_email=False, api_key="k")
    )
    init_db(app_b.state.session_factory)
    second = process_bruker_1d_zip(
        filename="sample.zip",
        content=archive,
        solvent="CDCl3",
        nucleus="1H",
        session_factory=app_b.state.session_factory,
    )
    assert ((second.metadata or {}).get("raw_fid_processing_cache") or {}).get("hit") is True


def test_l2_failure_degrades_to_recompute_not_error(tmp_path: Path) -> None:
    """A broken cache database must never fail the request."""

    # A factory whose engine points at an unopenable path: every L2 call raises.
    session_factory = create_session_factory(
        f"sqlite:///{tmp_path}/missing-dir/does-not-exist/l2.sqlite3"
    )
    archive = _bruker_zip(title="l2-failure-degrades")
    _RAW_FID_PROCESS_CACHE.clear()

    report = process_bruker_1d_zip(
        filename="sample.zip",
        content=archive,
        solvent="CDCl3",
        nucleus="1H",
        session_factory=session_factory,
    )
    assert report.point_count > 0
    assert len(report.inferred_peaks) > 0
