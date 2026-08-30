"""A parameter file cut short must be refused, not read forever.

nmrglue's `parse_jcamp_line` has two unbounded reads -- a `<string>` with no
closing bracket, and an array short of its declared count. At end of file
`readline()` returns `""` and `"".split()` is `[]`, so neither loop can advance.
`read_jcamp` wraps the call in a bare `except:`, which catches an exception and
cannot catch a loop.

Measured on a real acquisition before the guard: of seven truncation offsets of
`acqus`, THREE never returned (60%, 70%, 90%) while 30/40/50/80% read fine.
Whether it hangs depends on where the cut lands inside a parameter, which is why
one sample is not evidence a dataset is safe -- an earlier pass truncated at 50%,
saw it return, and wrongly concluded there was nothing here.

It matters more than a bad file usually would: the read ran on the service's
event loop, so one such dataset stopped the whole service answering anything,
health included, while the process stayed alive at full CPU and the desktop's
status box went on saying the service was running.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

#: Fractions of `acqus` to keep. Three of these hang the unguarded reader; the
#: set is kept whole rather than reduced to the failing three, because which
#: offsets hang is a property of THIS file's layout and would drift.
_TRUNCATION_FRACTIONS = (0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90)

#: Generous. A guarded read of any of these returns in about a second; the
#: unguarded one never returns at all, so nothing here is timing-sensitive.
_WALL_CLOCK_LIMIT_S = 60


def _an_acquisition_with_parameters() -> Path | None:
    for pdata in sorted(Path("tests/fixtures").glob("**/pdata")):
        root = pdata.parent
        if (root / "acqus").is_file():
            return root
    return None


def test_a_truncated_parameter_file_is_refused_rather_than_read_forever(tmp_path: Path) -> None:
    source = _an_acquisition_with_parameters()
    if source is None:
        pytest.skip("no Bruker acquisition with parameters in this checkout")

    size = (source / "acqus").stat().st_size
    refused = 0
    for fraction in _TRUNCATION_FRACTIONS:
        case = tmp_path / f"case{int(fraction * 100)}"
        shutil.copytree(source, case)
        with open(case / "acqus", "r+b") as handle:
            handle.truncate(int(size * fraction))

        # A SUBPROCESS, because the failure being guarded against is a loop. A
        # loop cannot be interrupted by an assertion, a timeout decorator, or a
        # `try` -- an in-process test that regressed would hang the whole suite
        # rather than fail it, which is the same defect wearing a test's clothes.
        script = (
            "from moltrace.spectroscopy.io.fid_reader import read_fid, read_processed_spectrum\n"
            f"try: read_processed_spectrum(r'{case}')\n"
            f"except Exception: read_fid(r'{case}')\n"
            "print('RETURNED')\n"
        )
        try:
            done = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, timeout=_WALL_CLOCK_LIMIT_S,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"truncating acqus to {fraction:.0%} never returned within "
                f"{_WALL_CLOCK_LIMIT_S}s -- the reader is spinning, and on the service "
                "this stops it answering anything at all"
            )
        if "RETURNED" not in (done.stdout or ""):
            refused += 1
            assert "incomplete" in (done.stderr or ""), (
                f"truncating to {fraction:.0%} failed without naming the cause:\n"
                + (done.stderr or "")[-400:]
            )

    assert refused, (
        "no truncation was refused, so this asserts nothing about the guard -- "
        "either the fixture changed or the offsets no longer land inside a parameter"
    )


def test_the_local_read_does_not_run_on_the_event_loop() -> None:
    """A blocking read declared `async` runs ON the loop and takes the service with it.

    Pinned by inspection rather than by timing: the alternative is to hang a real
    service and measure it, which is the defect itself.
    """
    import inspect

    from nmrcheck.local_service_app import _fid_open

    assert not inspect.iscoroutinefunction(_fid_open), (
        "_fid_open is a coroutine again. Its body is blocking numerical work with no "
        "await in it, so the event loop cannot serve anything else -- including health "
        "-- while a spectrum is being read."
    )
