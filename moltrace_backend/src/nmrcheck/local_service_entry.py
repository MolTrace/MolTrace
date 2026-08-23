"""Starting the local scientific service: reading the credential it was handed.

§7.1 requires the credential be passed "over an inherited handle or pipe rather
than a command line, an environment variable, or a file". The shell writes it to
fd 3 and closes the handle immediately; this reads it.

**Until now nothing read it.** The app took the credential as a constructor
argument, so the shell's generator and the service's verifier agreed in principle
and had never met. The trailing newline the shell appends is the specific hazard
that lives in that gap: read verbatim, the credential would never match, and no
test that stays on one side of the boundary can see it.

Nothing here falls back. A missing handle means the service was started by
something other than the shell — by hand, by a supervisor, by anything — and the
only safe answer is to refuse, because every other control in the transport
assumes a credential that only the shell knows.
"""

from __future__ import annotations

import os

#: Matches the shell's emitted length: base64url of 32 random bytes.
_MIN_CREDENTIAL_CHARS = 32

#: The descriptor the shell's spawn plan writes to.
CREDENTIAL_FD = 3


class CredentialHandleError(RuntimeError):
    """The service could not obtain a credential, so it must not start."""


def read_credential_from_handle(fd: int = CREDENTIAL_FD) -> str:
    """Read the credential the host wrote, or raise.

    Never echoes what it read: a refusal that quotes the value publishes it into
    whatever collects the startup log.
    """
    try:
        with os.fdopen(fd, "rb", closefd=True) as handle:
            raw = handle.read()
    except OSError as unreadable:
        raise CredentialHandleError(
            "the local science service was not given a credential handle, so it will not start. "
            "It is started by the MolTrace desktop application, not on its own."
        ) from unreadable

    # The shell writes `secret + '\n'`. Strip line endings and nothing else --
    # a credential is base64url, which contains no whitespace, so anything else
    # surviving here would be a value we should not accept anyway.
    credential = raw.decode("utf-8", errors="replace").strip("\r\n")

    if not credential:
        raise CredentialHandleError(
            "the credential handle was empty, so the service has nothing to check against "
            "and will not start"
        )
    if len(credential) < _MIN_CREDENTIAL_CHARS:
        raise CredentialHandleError(
            f"the credential on the handle is {len(credential)} characters, shorter than the "
            f"{_MIN_CREDENTIAL_CHARS} required; refusing to start with a weak credential"
        )
    return credential
