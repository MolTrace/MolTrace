"""The packaged service's entry point — what it refuses, and why.

Everything here is about NOT starting. §7.1 gives the service two inputs it can
only get from the desktop host, and a service that improvises either one is worse
than a service that fails: it replaces a private socket with a public port, or a
secret credential with nothing.
"""

from __future__ import annotations

import os
import socket

import pytest

from nmrcheck.local_service_main import ServiceStartupError, _require_socket, main


def test_a_passed_socket_descriptor_is_accepted() -> None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        assert _require_socket(s.fileno()) == s.fileno()
    finally:
        s.close()


def test_a_missing_socket_descriptor_is_REFUSED_not_defaulted_to_a_port() -> None:
    """The dangerous fallback. Binding a port because no socket arrived would
    open the service to every account on the machine, which is the exact thing
    the Unix-socket design exists to prevent."""
    with pytest.raises(ServiceStartupError):
        _require_socket(9999)


def _closed_fd() -> int:
    """A descriptor guaranteed not to be readable, so the refusal path is driven
    rather than whatever the test runner happens to have open on fd 3."""
    r, w = os.pipe()
    os.close(r)
    os.close(w)
    return r


def test_the_refusal_says_it_is_started_by_the_desktop(capsys) -> None:
    rc = main([], credential_fd=_closed_fd(), socket_fd=9999)
    assert rc == 78, "a service that cannot start safely must not report success"
    err = capsys.readouterr().err
    assert "MolTrace desktop application" in err
    assert "refused to start" in err


def test_the_refusal_carries_no_secret(capsys) -> None:
    main([], credential_fd=_closed_fd(), socket_fd=9999)
    err = capsys.readouterr().err
    assert "credential" not in err.lower() or "not given a credential" in err.lower()


def test_an_inherited_open_fd_3_does_not_hang_the_service() -> None:
    """A parent that leaves an unrelated file open on fd 3 must produce a refusal,
    not a hang. Found by this suite hanging under pytest, where fd 3 is open."""
    import tempfile

    with tempfile.TemporaryFile() as leftover:
        # dup, because the reader CONSUMES the descriptor it is given — it closes
        # the handle so the credential cannot be re-read by anything that later
        # inherits it. Passing the TemporaryFile's own fd would have it closed
        # underneath the context manager.
        rc = main([], credential_fd=os.dup(leftover.fileno()), socket_fd=9999)
    assert rc == 78


def test_it_does_not_bind_by_path_anywhere() -> None:
    """§7.1: the packaged runtime chmods a path-bound socket world-accessible, so
    the service must never create one. Checked in the source, because the failure
    is the presence of an option rather than a behaviour we can drive here."""
    import inspect

    from nmrcheck import local_service_main

    src = inspect.getsource(local_service_main)
    assert "uds=" not in src, "the service binds a Unix socket BY PATH"
    assert "port=" not in src, "the service binds a port"
    assert "fd=" in src, "the service does not serve on the passed descriptor"
