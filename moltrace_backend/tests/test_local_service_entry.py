"""Reading the credential from the inherited handle — the other half of §7.1.

The shell generates a credential and writes it to fd 3 with a trailing newline
(service-credential.js, spawnPlan). Nothing had ever read it: the app took the
credential as a constructor argument, so the two halves agreed only in principle.

This is where a cross-boundary mismatch lives, and the newline is the specific
one — a credential that arrives with "\\n" attached never matches, and no test
that stays on one side of the boundary can see it.
"""

from __future__ import annotations

import os

import pytest

from nmrcheck.local_service_entry import CredentialHandleError, read_credential_from_handle

CRED = "c" * 43


def _pipe_containing(payload: bytes) -> int:
    r, w = os.pipe()
    os.write(w, payload)
    os.close(w)
    return r


def test_the_trailing_newline_the_shell_writes_is_stripped() -> None:
    """The shell writes `secret + '\\n'`. Read verbatim, nothing would ever match."""
    fd = _pipe_containing((CRED + "\n").encode())
    assert read_credential_from_handle(fd) == CRED


def test_a_credential_without_a_newline_also_works() -> None:
    assert read_credential_from_handle(_pipe_containing(CRED.encode())) == CRED


def test_windows_line_endings_are_stripped() -> None:
    assert read_credential_from_handle(_pipe_containing((CRED + "\r\n").encode())) == CRED


def test_an_empty_handle_is_refused_rather_than_yielding_an_empty_credential() -> None:
    """An empty credential would be compared against, and a comparison against
    nothing is not a check. Refusing to start is the only safe answer."""
    with pytest.raises(CredentialHandleError):
        read_credential_from_handle(_pipe_containing(b""))


def test_a_short_credential_is_refused() -> None:
    with pytest.raises(CredentialHandleError):
        read_credential_from_handle(_pipe_containing(b"tooshort\n"))


def test_a_missing_handle_is_refused() -> None:
    """No fd 3 at all means the service was started by something other than the
    shell — by hand, by a supervisor, by anything. It must not fall back."""
    with pytest.raises(CredentialHandleError):
        read_credential_from_handle(9999)


def test_the_credential_is_never_echoed_in_a_refusal() -> None:
    for payload in (b"", b"tooshort\n"):
        with pytest.raises(CredentialHandleError) as exc:
            read_credential_from_handle(_pipe_containing(payload))
        assert "tooshort" not in str(exc.value)


def test_what_the_shell_actually_emits_round_trips() -> None:
    """The cross-boundary check, using the shell's real output format rather than
    a fixture that happens to look like it: 43 characters of base64url plus the
    newline spawnPlan appends."""
    import base64
    import secrets

    emitted = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    assert len(emitted) == 43
    assert read_credential_from_handle(_pipe_containing((emitted + "\n").encode())) == emitted
