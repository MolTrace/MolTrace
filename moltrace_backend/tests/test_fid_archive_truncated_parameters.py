"""An uploaded archive with a cut-short parameter file must be refused, not read forever.

``test_fid_truncated_parameters.py`` guards the desktop reader
(``moltrace.spectroscopy.io.fid_reader``). This guards the OTHER reader -- the one
behind the upload routes -- ``nmrcheck.fid.process_bruker_1d_zip``, which reaches
``ng.bruker.read`` at fid.py:1439 and again on the digital-filter path at 1524.

Both call sites sit inside ``try/except Exception``, and that is exactly what makes
them look safe. nmrglue's ``parse_jcamp_line`` reads an array parameter with
``while len(value) < num``; at EOF ``readline()`` returns ``''`` and ``''.split()``
is ``[]``, so the loop can never advance. **A ``try`` cannot catch a loop.**

The truncation is CONSTRUCTED, not sampled. Cutting the file at a fraction of its
length only hangs when the cut happens to land inside an array parameter's values --
measured on one fixture, 90% hung while 40/50/60/70/100% completed, and on another
the same 90% was fine. That data-dependence is how this defect was once called
refuted on the strength of a single offset. Cutting immediately after an array
parameter's ``(0..N)`` header removes every value it declares, so the count can
never be satisfied on any fixture: verified to hang on 5 of 5 Bruker acquisitions
in this repository before the guard existed.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

#: Generous next to the ~6s a healthy archive takes, because the failure is
#: unbounded: anything that has not returned by now is not slow, it is spinning.
_WALL_CLOCK_LIMIT_S = 90

_ARRAY_HEADER = re.compile(rb"##\$([A-Z0-9_]+)= \(0\.\.(\d+)\)")

_WORKER = (
    "import pathlib, sys\n"
    "from nmrcheck.fid import process_bruker_1d_zip\n"
    "content = pathlib.Path(sys.argv[1]).read_bytes()\n"
    "try:\n"
    "    process_bruker_1d_zip(filename='d.zip', content=content, nucleus='13C')\n"
    "except Exception as exc:\n"
    "    print('REFUSED', type(exc).__name__)\n"
    "else:\n"
    "    print('PROCESSED')\n"
)


def _a_bruker_acquisition() -> Path | None:
    for acqus in sorted(Path("tests/fixtures").glob("**/acqus")):
        if (acqus.parent / "fid").is_file():
            return acqus.parent
    return None


def _cut_after_an_array_header(acqus: Path) -> str | None:
    """Truncate so a declared array loses every one of its values."""
    offset = 0
    for line in acqus.read_bytes().splitlines(keepends=True):
        offset += len(line)
        match = _ARRAY_HEADER.match(line)
        if match and int(match.group(2)) >= 1:
            with open(acqus, "r+b") as handle:
                handle.truncate(offset)
            return match.group(1).decode()
    return None


def _archive(root: Path, into: Path, *, truncate: bool) -> tuple[Path, str | None]:
    case = into / ("cut" if truncate else "intact")
    shutil.copytree(root, case)
    entry = _cut_after_an_array_header(case / "acqus") if truncate else None
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(case.rglob("*")):
            if path.is_file():
                archive.write(path, f"ds/{path.relative_to(case)}")
    package = into / f"{case.name}.zip"
    package.write_bytes(buffer.getvalue())
    return package, entry


def _run(package: Path) -> subprocess.CompletedProcess[str]:
    # A SUBPROCESS, because the failure guarded against is a loop: an in-process
    # test that regressed would hang the whole suite rather than fail it.
    #
    # And ``sys.executable``, never ``uv run`` -- uv is a launcher, so a subprocess
    # timeout kills uv while the python grandchild is reparented to launchd and
    # keeps running. Three probes leaked that way outlived their parent by nine and
    # a half hours at 25% CPU each.
    return subprocess.run(
        [sys.executable, "-c", _WORKER, str(package)],
        capture_output=True,
        text=True,
        timeout=_WALL_CLOCK_LIMIT_S,
        env={**os.environ, "PYTHONPATH": "src"},
    )


def test_a_truncated_archive_is_refused_rather_than_read_forever(tmp_path: Path) -> None:
    source = _a_bruker_acquisition()
    if source is None:
        pytest.skip("no Bruker acquisition with acqus + fid in this checkout")
    package, entry = _archive(source, tmp_path, truncate=True)
    assert entry is not None, "fixture's acqus declares no array parameter to cut"

    try:
        done = _run(package)
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"an archive whose acqus loses the values of '{entry}' never returned "
            f"within {_WALL_CLOCK_LIMIT_S}s. The upload routes "
            f"(raw_fid_archive_preview, raw_fid_archive_process) run this on a "
            f"threadpool worker, so each such upload consumes one permanently and "
            f"the pool is bounded."
        )
    assert "REFUSED" in done.stdout, (
        f"cutting '{entry}' should be refused with a named cause, not accepted.\n"
        f"stdout={done.stdout!r}\nstderr={done.stderr[-400:]!r}"
    )


def test_an_intact_archive_still_processes(tmp_path: Path) -> None:
    """The control. Without it, a guard that refused every archive would pass above."""
    source = _a_bruker_acquisition()
    if source is None:
        pytest.skip("no Bruker acquisition with acqus + fid in this checkout")
    package, _ = _archive(source, tmp_path, truncate=False)
    done = _run(package)
    assert "PROCESSED" in done.stdout, (
        f"an untouched archive must still be read.\n"
        f"stdout={done.stdout!r}\nstderr={done.stderr[-400:]!r}"
    )
