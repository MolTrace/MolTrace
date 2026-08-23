"""§7.1 peer identity for the local scientific service.

"Establish peer identity in the transport layer, before a request reaches the
service… refuse any peer whose user is not the launching user or whose executable
image is not the installed host binary at its verified path."

This runs in the service process, not the Electron host — see ``desktop_transport``
for why the host cannot do it.

**Two checks of very different strength, and the difference is the point.**

The *user* is delivered by the kernel along with the connection. It is
authoritative: a process cannot present a uid it does not have.

The *executable* is reached through the peer's **pid**, and a pid is not a durable
identity. Between the connection arriving and the path being read, the peer can
exit and its pid be reused by an unrelated process. So the executable check
**corroborates and does not authenticate**, and this module says so rather than
letting a weaker signal quietly become load-bearing.

MEASURED on macOS: ``LOCAL_PEERCRED`` returns an ``xucred``, which carries the uid
and group list and **no pid**. The pid needs a second option, ``LOCAL_PEERPID``.
Code written on the assumption that one call delivers both would have shipped an
executable check that silently never ran.
"""

from __future__ import annotations

import os
import socket
import struct
import sys
from dataclasses import dataclass

# macOS: <sys/un.h>. SOL_LOCAL is 0; Python exposes LOCAL_PEERCRED but not the
# level or LOCAL_PEERPID, so both are named here.
_SOL_LOCAL = 0
_LOCAL_PEERCRED = 1
_LOCAL_PEERPID = 2

#: Linux, <sys/socket.h>. Python exposes SO_PEERCRED only on Linux builds.
_LINUX_SO_PEERCRED = 17


class PeerRefusal(Exception):
    """A peer the service refuses to serve."""


@dataclass(frozen=True)
class PeerIdentity:
    """What the platform could actually tell us about the other end."""

    uid: int | None
    pid: int | None
    executable: str | None


def read_peer(sock: socket.socket) -> PeerIdentity:
    """Read what the platform supplies for this connection.

    Returns partial information rather than raising: a platform that cannot
    supply a pid is a stated limitation, not an error, and the caller decides
    what an absent field means.
    """
    if sys.platform == "darwin":
        raw = sock.getsockopt(_SOL_LOCAL, _LOCAL_PEERCRED, 128)
        # struct xucred { u_int cr_version; uid_t cr_uid; short cr_ngroups; ... }
        _version, uid = struct.unpack_from("Ii", raw)
        try:
            pid = struct.unpack_from("i", sock.getsockopt(_SOL_LOCAL, _LOCAL_PEERPID, 4))[0]
        except OSError:
            pid = None
        return PeerIdentity(uid=uid, pid=pid, executable=_executable_for(pid))
    if sys.platform.startswith("linux"):
        opt = getattr(socket, "SO_PEERCRED", _LINUX_SO_PEERCRED)
        pid, uid, _gid = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, opt, 12))
        return PeerIdentity(uid=uid, pid=pid, executable=_executable_for(pid))
    # Windows loopback TCP: the owning process is found through the connection
    # table rather than the socket, and is not implemented here yet.
    return PeerIdentity(uid=None, pid=None, executable=None)


def _executable_for(pid: int | None) -> str | None:
    if pid is None:
        return None
    if sys.platform.startswith("linux"):
        try:
            return os.readlink(f"/proc/{pid}/exe")
        except OSError:
            return None
    return None  # macOS needs proc_pidpath(); not wired yet.


def assess_peer(
    peer: PeerIdentity,
    *,
    expected_uid: int | None,
    expected_executable: str | None,
) -> None:
    """Admit the peer, or raise. Absent information is refused, never assumed."""
    if expected_uid is not None:
        if peer.uid is None:
            raise PeerRefusal("refused: this connection carries no user identity")
        if peer.uid != expected_uid:
            raise PeerRefusal("refused: the connection came from a different user account")
    if expected_executable is not None:
        if peer.executable is None:
            raise PeerRefusal(
                "refused: the program on the other end of this connection could not be identified"
            )
        if os.path.realpath(peer.executable) != os.path.realpath(expected_executable):
            raise PeerRefusal("refused: the connection came from a different program")


_PID_REUSE = (
    "The program on the other end is identified through its process number, and a process "
    "number can be reused after a program exits. This check corroborates the user check; it "
    "does not authenticate on its own."
)
_SAME_USER = (
    "Any program running under your user account on this computer can connect to the local "
    "science service. The per-launch credential is what separates them, not this check."
)
_LINUX_NO_SIGNATURE = (
    "On Linux there is no code signature to verify, so the program's path and the user account "
    "are the whole of this check."
)
_WINDOWS_NOT_WIRED = (
    "On Windows the connecting program is found through the system's connection table, which "
    "this installation does not yet consult, so only the per-launch credential applies."
)
_MACOS_NO_PATH = (
    "On macOS the program's path is not yet read, so only the user account is checked here."
)


def peer_check_limitations(platform: str) -> list[str]:
    """What this check does NOT establish, per platform, in words a person reads.

    §7.1 requires the release evidence to state where the check runs; §15 records
    the residual limits. Neither is served by a list of what the check does.
    """
    limits = [_PID_REUSE, _SAME_USER]
    if platform.startswith("linux"):
        limits.append(_LINUX_NO_SIGNATURE)
    elif platform == "darwin":
        limits.append(_MACOS_NO_PATH)
    else:
        limits.append(_WINDOWS_NOT_WIRED)
    return limits
