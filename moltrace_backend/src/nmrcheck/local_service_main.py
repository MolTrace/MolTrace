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
