"""§7.1 peer identity for the local scientific service.

"Establish peer identity in the transport layer, before a request is served…
refuse any peer whose user is not the launching user or whose executable image
is not the installed host binary at its verified path."

Two checks with very different strength, and the tests exist mostly to stop the
weaker one being described as the stronger:

* **uid** is delivered by the kernel with the connection. It is authoritative.
* **executable path** is reached through the peer's *pid*, and a pid can be
  reused after the process exits. It corroborates; it does not authenticate.

MEASURED on this platform (darwin): ``LOCAL_PEERCRED`` returns ``xucred``, which
carries uid and groups and **no pid at all** — so the executable check needs a
second option, ``LOCAL_PEERPID``. Anything that assumed one call delivers both
would have shipped an executable check that never ran.
"""

from __future__ import annotations

import os
import socket
import sys

import pytest

from nmrcheck.desktop_peer import (
    PeerIdentity,
    PeerRefusal,
    assess_peer,
    peer_check_limitations,
    read_peer,
)


def test_the_real_uid_is_readable_from_a_live_socket() -> None:
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        peer = read_peer(a)
        assert peer.uid == os.getuid()
    finally:
        a.close()
        b.close()


@pytest.mark.skipif(sys.platform not in ("darwin", "linux"), reason="posix peer creds")
def test_the_peer_pid_is_readable_where_the_platform_supplies_it() -> None:
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        peer = read_peer(a)
        assert peer.pid == os.getpid()
    finally:
        a.close()
        b.close()


def test_a_different_user_is_refused() -> None:
    peer = PeerIdentity(uid=os.getuid() + 1, pid=1234, executable=None)
    with pytest.raises(PeerRefusal):
        assess_peer(peer, expected_uid=os.getuid(), expected_executable=None)


def test_the_launching_user_is_admitted() -> None:
    peer = PeerIdentity(uid=os.getuid(), pid=os.getpid(), executable=None)
    assert assess_peer(peer, expected_uid=os.getuid(), expected_executable=None) is None


def test_an_ABSENT_uid_is_refused_when_one_is_expected() -> None:
    """The fail-closed branch, and the one that actually fires in practice.

    Windows loopback supplies no uid today, so this is not a hypothetical: a
    platform that cannot tell us who connected must be refused, not admitted.
    Added after a weakening probe found this branch had no test — deleting the
    `uid is None` check left the suite green.
    """
    peer = PeerIdentity(uid=None, pid=1234, executable=None)
    with pytest.raises(PeerRefusal) as exc:
        assess_peer(peer, expected_uid=os.getuid(), expected_executable=None)
    # Asserting on the CAUSE, not just the refusal. Removing the `uid is None`
    # branch still refuses -- the next check catches it, because None != uid --
    # so an outcome-only test cannot see this branch at all. What the branch
    # provides is the correct cause: "no user identity" rather than "a different
    # user account", which are different facts and imply different investigations.
    assert "no user identity" in str(exc.value), (
        f"an absent uid was reported as a different-user refusal: {exc.value}"
    )


def test_a_wrong_executable_is_refused_when_one_is_expected() -> None:
    peer = PeerIdentity(uid=os.getuid(), pid=1234, executable="/tmp/not-the-host")
    with pytest.raises(PeerRefusal):
        assess_peer(peer, expected_uid=os.getuid(), expected_executable="/opt/MolTrace/MolTrace")


def test_an_UNKNOWN_executable_is_refused_when_one_is_expected() -> None:
    """Absent is not "probably fine". If the path could not be read and the
    deployment expects one, that is a refusal, not a pass."""
    peer = PeerIdentity(uid=os.getuid(), pid=1234, executable=None)
    with pytest.raises(PeerRefusal):
        assess_peer(peer, expected_uid=os.getuid(), expected_executable="/opt/MolTrace/MolTrace")


# --- the honesty half, which is most of the value ---------------------------


def test_the_pid_reuse_race_is_stated_not_hidden() -> None:
    limits = peer_check_limitations(sys.platform)
    joined = " ".join(limits).lower()
    assert "reus" in joined, "the pid-reuse race is not stated"


def test_linux_states_that_there_is_no_signature_to_check() -> None:
    joined = " ".join(peer_check_limitations("linux")).lower()
    assert "signature" in joined, "§15's Linux residual limit is not stated"


def test_no_platform_claims_the_executable_check_authenticates() -> None:
    """§7.1 asks for the check; it does not license calling it authentication.

    The uid comes from the kernel with the connection. The executable comes from
    a pid, and a pid is not a durable identity. Describing the second as
    authoritative is how a corroborating signal becomes load-bearing by accident.
    """
    for platform in ("darwin", "linux", "win32"):
        joined = " ".join(peer_check_limitations(platform)).lower()
        assert "corroborat" in joined or "not authenticat" in joined, (
            f"{platform} does not say the executable check is corroborating only"
        )


def test_limitations_are_readable_and_carry_no_api_names() -> None:
    for platform in ("darwin", "linux", "win32"):
        for line in peer_check_limitations(platform):
            assert len(line) > 20
            assert "LOCAL_PEERCRED" not in line
            assert "SO_PEERCRED" not in line
            assert "getsockopt" not in line
