"""Entry point for the packaged local scientific service.

Started by the MolTrace desktop application and by nothing else. It takes two
things from its parent and neither of them from the command line, the
environment, or a file:

* the **credential**, on fd 3 (§7.1, see ``local_service_entry``);
* the **bound listening socket**, on a descriptor the host passes.

**The service must not bind by path.** §7.1 is explicit and Phase 0 measured it:
the packaged runtime chmods a path-bound Unix socket to world-accessible mode, so
a service that creates its own socket hands every local account a door. The host
creates it at owner-only mode inside a directory it owns and passes the bound
descriptor down; here we only accept what we were handed.

There is no fallback to a port. A missing socket descriptor means this was not
started by the shell, and starting anyway would replace a private socket with a
listening port that anything on the machine can reach.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .local_service_app import create_local_app
from .local_service_entry import (
    CREDENTIAL_FD,
    CredentialHandleError,
    read_credential_from_handle,
)

#: The descriptor the host passes the bound listening socket on. fd 3 carries the
#: credential and is consumed at startup, so the socket follows it.
SOCKET_FD = 4


class ServiceStartupError(RuntimeError):
    """The service cannot start safely, so it does not start."""


def _require_socket(fd: int = SOCKET_FD) -> int:
    try:
        os.fstat(fd)
    except OSError as missing:
        raise ServiceStartupError(
            "the local science service was not given a listening socket, so it will not start. "
            "It is started by the MolTrace desktop application, which creates the socket and "
            "passes it down; starting it another way would open a port to the whole machine."
        ) from missing
    return fd



#: The shift-prediction table, shipped beside the frozen service.
#:
#: WITHOUT IT THE PREDICTOR ANSWERS FROM A 16-MOLECULE SEED, and the difference is
#: not a nuance: median 13C uncertainty ~35 ppm against ~1.9 ppm, the latter being
#: below DP4's own 2.306 ppm error scale. Measured on the ethylene glycol
#: acquisition in this repository, checking four candidate structures:
#:
#:                      seed (146 atoms)   nmrshiftdb2 (495,215 atoms)
#:   ethylene glycol       0.556                0.939  consistent
#:   ethanol               0.623  <- won        0.242  inconclusive
#:   aspirin               0.542                0.166  inconsistent
#:
#: On the seed the WRONG molecule outranked the right one. With the table the
#: right one wins by 0.697. Same verifier, same spectrum: the predictor was
#: starved, not the method.
_BUNDLED_KB_NAMES = ("hose_index.json.gz", "hose_index.json")


def _bundled_file(name: str) -> str | None:
    """A data file shipped beside the service, by name, or None."""
    for root in _bundled_roots():
        candidate = root / name
        if candidate.is_file():
            return str(candidate)
    return None


def _bundled_roots() -> list[Path]:
    """Where a data file shipped with this build could be.

    PyInstaller's onedir layout puts data in `_internal` BESIDE the executable,
    not next to it, so the executable's own directory is not enough. `sys._MEIPASS`
    is the documented answer and is checked first; the explicit `_internal` costs
    nothing and removes an inference about a build tool's internals from the
    lookup that decides which product the user gets.

    A SOURCE CHECKOUT LOOKS WHERE THE BUILDERS WRITE, so a developer who followed
    the documented build steps does not test one product and package another.
    That cannot hide a missing file in a BUILD: packaging checks the freeze
    itself, not the running process.
    """
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        here = Path(sys.executable).resolve().parent
        internal = getattr(sys, "_MEIPASS", None)
        if internal:
            roots.append(Path(internal))
        roots.append(here / "_internal")
        roots.append(here)
    roots.append(Path(__file__).resolve().parent)
    roots.append(Path.home() / ".cache" / "moltrace" / "nmrnet")
    return roots


def _bundled_file(name: str) -> str | None:
    """A data file shipped beside the service, by name, or None if absent."""
    for root in _bundled_roots():
        candidate = root / name
        if candidate.is_file():
            return str(candidate)
    return None


def _bundled_knowledge_base() -> str | None:
    """The shift-prediction table shipped with this build, if there is one.

    Returns None when there is none, which is a legitimate configuration -- a dev
    checkout without the table -- and the predictor then says so through
    `knowledge_base_status` rather than pretending.
    """
    for name in _BUNDLED_KB_NAMES:
        found = _bundled_file(name)
        if found:
            return found
    return None


def _configure_knowledge_base() -> None:
    """Point the predictor at the shipped table, unless the operator chose one.

    An explicit `MOLTRACE_HOSE_KB` always wins: someone who set it meant it, and
    silently overriding a chosen table with a bundled one is the same class of
    substitution the predictor's own error path exists to prevent.

    Set BEFORE the app is built, because `_fallback_kb` caches the first table it
    loads for the life of the process.
    """
    if os.environ.get("MOLTRACE_HOSE_KB"):
        return
    bundled = _bundled_knowledge_base()
    if bundled:
        os.environ["MOLTRACE_HOSE_KB"] = bundled


def main(
    argv: list[str] | None = None,
    *,
    credential_fd: int = CREDENTIAL_FD,
    socket_fd: int = SOCKET_FD,
) -> int:
    """Read the credential, take the socket, serve. Refuse rather than improvise.

    The descriptors are parameters with the §7.1 defaults rather than constants
    read from ambient state. That is not only for testability: a process started
    where fd 3 is some INHERITED open file — a log, a lock, anything a parent
    left open — would read from it and block forever rather than refusing, which
    is a hang with no message rather than a refusal with one. Found exactly that
    way: under pytest, fd 3 is open, and this function hung.
    """
    del argv
    _configure_knowledge_base()
    try:
        credential = read_credential_from_handle(credential_fd)
        socket_fd = _require_socket(socket_fd)
    except (CredentialHandleError, ServiceStartupError) as refusal:
        # stderr, not the journal: there is no journal yet, and no credential to
        # authorise one. The message names the cause and carries no secret.
        print(f"MolTrace local service refused to start: {refusal}", file=sys.stderr)
        return 78  # EX_CONFIG

    import uvicorn

    app = create_local_app(credential=credential)
    uvicorn.run(app, fd=socket_fd, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
