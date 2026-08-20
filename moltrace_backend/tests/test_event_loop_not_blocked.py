"""No async route handler may run heavy science on the event loop.

FastAPI dispatches a plain ``def`` handler to anyio's worker threads, but an
``async def`` handler runs ON the loop — so a single CPU-bound call inside one
freezes the whole uvicorn worker for its duration. Measured before this was
fixed: 1.76 s at 16k points, 10.6 s at 32k and 32.1 s at 65k for
``parse_processed_spectrum``, and 6.8 s for a 2.5 MB Bruker archive; for that
whole time the instance served nothing at all — not another tenant's request,
not ``/health``, which is itself a sync ``def`` and so cannot even reach the
threadpool while the loop is blocked.

The heavy handlers are ``async def`` because they must ``await file.read()``,
so the fix is per-call (``run_in_threadpool``) rather than per-handler. That
makes it easy to reintroduce: a new handler, or a new call added to an existing
one, blocks again with no visible symptom until the instance is under load.
This guard is the thing that notices.
"""

from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[1] / "src" / "nmrcheck" / "api.py"

#: Calls that do seconds of numpy/scipy/rdkit work. Extend this when a new
#: expensive entry point appears — that is the point of the list.
HEAVY_CALLS = (
    "parse_processed_spectrum(",
    "process_bruker_1d_zip(",
    "gsd_peak_pick(",
    "analyze_inputs(",
)


def _blocking_call_sites() -> list[str]:
    lines = API.read_text(encoding="utf-8").split("\n")
    offenders: list[str] = []
    enclosing: tuple[str, bool] | None = None

    for index, line in enumerate(lines, start=1):
        signature = re.match(r"^(async )?def (\w+)\(", line)
        if signature:
            enclosing = (signature.group(2), bool(signature.group(1)))
        if enclosing is None or not enclosing[1]:
            continue
        stripped = line.strip()
        if stripped.startswith(("def ", "async def ", "#")):
            continue
        for call in HEAVY_CALLS:
            if call not in line:
                continue
            # The offload may sit on this line or on the one above it, since
            # `run_in_threadpool(\n    fn,` is the multi-line kwargs form.
            offloaded = "run_in_threadpool" in line or "run_in_threadpool" in lines[index - 2]
            if not offloaded:
                offenders.append(f"{enclosing[0]} (api.py:{index}): {stripped[:70]}")
    return offenders


def test_no_async_handler_runs_heavy_science_on_the_loop() -> None:
    offenders = _blocking_call_sites()
    assert not offenders, (
        "these async handlers call CPU-bound science directly, freezing the "
        "worker (and /health) for its duration — wrap the call in "
        "starlette.concurrency.run_in_threadpool:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_can_actually_fail() -> None:
    """A guard that cannot fail is decoration; prove the detector works."""
    lines = [
        "async def some_route(file: UploadFile = File(...)):",
        "    content = await file.read()",
        "    preview = parse_processed_spectrum(filename='x', content=content)",
    ]
    enclosing_is_async = lines[0].startswith("async def")
    offloaded = "run_in_threadpool" in lines[2]
    assert enclosing_is_async and not offloaded, (
        "the fixture this guard is modelled on no longer represents a violation"
    )


def test_freshness_headers_are_a_default_not_a_mandate() -> None:
    """A route must be able to declare its own caching policy.

    The middleware assigned Cache-Control / Pragma / Expires directly, so no
    endpoint could opt out — genuinely static reference data (``/fid/presets``,
    ``/spectrum/solvents/known``, ``/system/version``) was refetched in full on
    every navigation because the response had no way to say otherwise. All
    three are now ``setdefault``, and they move together: an opted-out
    Cache-Control sitting beside a leftover ``Pragma: no-cache`` would
    contradict itself. The default is unchanged, so live data still never
    caches and a route has to opt in deliberately.
    """
    source = API.read_text(encoding="utf-8")
    for header in ("Cache-Control", "Pragma", "Expires"):
        assert not re.search(rf'response\.headers\["{header}"\]\s*=[^=]', source), (
            f"{header} is assigned directly, so no route can declare its own policy"
        )
    assert 'setdefault(\n            "Cache-Control"' in source
    assert 'setdefault("Pragma", "no-cache")' in source
    assert 'setdefault("Expires", "0")' in source
