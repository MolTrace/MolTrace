"""Opt-in pytest plugin: name the test that breaks a cross-test invariant.

Enable with ``-p fuseguard``. Plugins load before ``tests/`` reaches ``sys.path``, so
point ``PYTHONPATH`` at it::

    PYTHONPATH=tests uv run pytest tests -p fuseguard -p no:randomly

The plugin evaluates every invariant in :data:`INVARIANTS` after each test and prints
the first ``nodeid`` after which one stops holding, then falls silent. That answers
"which earlier test left this behind?" in a single pass, instead of bisecting the file
list -- which is the wrong shape of search anyway, because pytest imports *every* test
module during collection, so a module-level polluter need not be anywhere near its
victim in the run order.

It is a debugging tool, not a gate: nothing here fails a run, and the suite does not
load it by default.

Adding an invariant: a callable taking no arguments and returning a value that is
equal across runs when the state is intact. Import inside the callable, not at module
scope -- a plugin is imported before collection, and importing a science module here
would change what the run under investigation actually exercises.

The shipped example is the MS fusion disclosure. It is kept because it is a worked
case, not because it is known to be fragile: the run that prompted it turned out to be
a pre-fix ``ms_models.py`` paired with post-fix tests (the two files were saved 29s
apart), not shared state at all. Checking whether the failing assertions map one-to-one
onto a single commit's additions -- and whether the observed output is reachable from
the current source -- is cheaper than any sweep, and worth doing first.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest


def _ms_fusion_disclosure() -> Any:
    """A fusion run without MS/MS says so, and one with it keeps the absolute score."""

    from moltrace.spectroscopy.ai import fuse_candidates

    without_ms = fuse_candidates(dp4={"a": 0.6, "b": 0.4})[0]
    with_ms = fuse_candidates(dp4={"a": 0.5, "b": 0.3}, msms={"a": 0.9, "b": 0.1})[0]
    return (
        any("MS/MS" in note for note in without_ms.notes),
        "msms_raw" in with_ms.signals,
    )


#: name -> callable. Extend this when hunting a different leak.
INVARIANTS: dict[str, Callable[[], Any]] = {
    "ms_fusion_disclosure": _ms_fusion_disclosure,
}


class _Guard:
    def __init__(self) -> None:
        self._baseline: dict[str, Any] = {}
        self._reported: set[str] = set()
        self._report: Any = None

    def bind(self, config: pytest.Config) -> None:
        # The terminal reporter, not print(): pytest captures stdout during teardown and
        # only replays it for a failing test, so a print here is swallowed on the green
        # run this plugin exists to investigate.
        self._report = config.pluginmanager.get_plugin("terminalreporter")

    def _say(self, message: str) -> None:
        if self._report is not None:
            self._report.write_line(message)
        else:  # pragma: no cover -- only if the terminal reporter is disabled
            print(message, flush=True)

    @staticmethod
    def _evaluate(invariant: Callable[[], Any]) -> Any:
        try:
            return invariant()
        except Exception as exc:  # noqa: BLE001 -- an exception is itself a broken state
            return f"raised {exc!r}"

    def check(self, when: str) -> None:
        for name, invariant in INVARIANTS.items():
            if name in self._reported:
                continue
            observed = self._evaluate(invariant)
            if name not in self._baseline:
                self._baseline[name] = observed
                continue
            if observed != self._baseline[name]:
                self._reported.add(name)
                self._say(f">>> fuseguard: invariant {name!r} broke after {when}")
                self._say(f"    was {self._baseline[name]!r}, now {observed!r}")


_guard = _Guard()


def pytest_sessionstart(session: pytest.Session) -> None:
    _guard.bind(session.config)
    _guard.check("session start (baseline)")


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item) -> None:
    _guard.check(item.nodeid)
