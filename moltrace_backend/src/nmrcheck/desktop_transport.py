"""§7.1 transport controls for the local scientific service.

The desktop runs a packaged copy of this service on the workstation. Anything
else running on that workstation can reach a loopback port, so the transport
carries its own admission controls and they run *before* a request is served.

**Why the peer check lives here and not in the host.** §7.1 originally assigned it
to the Electron host, and that could not work: the host passes a *listening*
descriptor to the service, so the service calls ``accept()`` and the host never
sees a connection. Node also exposes no generic ``getsockopt`` and libuv has no
peer-credential API, so a host-side check would need a native addon prebuilt per
platform and architecture, each needing the nested-library signing that is a
dominant notarization-failure cause. In this process the same check is reachable
with ``ctypes``, inside an artifact that is already built and already signed. The
specification was corrected to match (v2.10).

**The controls are layered, and neither layer substitutes for the other.** §7.1:
the ``Origin``/``Referer``/``Host`` refusals "defeat classic rebinding but not a
direct loopback subresource load" — a ``script``, ``img``, ``link`` or ``iframe``
request sends no ``Origin``, and a page-level referrer policy suppresses
``Referer``. What closes that path is the credential-position rule: the credential
is accepted in one named header and refused everywhere a subresource load could
put it. Both are required.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

#: The one position a credential may occupy.
CREDENTIAL_HEADER = "x-moltrace-local-service"

#: Header positions a credential must never arrive in. A subresource load cannot
#: set a header, but it *can* carry a cookie automatically, and an ``Authorization``
#: header would invite the platform's own bearer path to be reused here.
_FORBIDDEN_CREDENTIAL_HEADERS = ("cookie", "authorization", "proxy-authorization")

#: Query keys that would put a credential in a URL. A URL-borne credential is the
#: one form a subresource load can carry, and it is also the form that lands in
#: logs, referrers and crash reports.
_FORBIDDEN_QUERY_KEYS = (b"access_token", b"token", b"credential", b"api_key")

_MIN_CREDENTIAL_LEN = 32


class TransportRefusal(Exception):
    """A request the transport refuses to serve. Never carries the credential."""


@dataclass(frozen=True)
class DesktopTransportGuard:
    """Admission control for the local service.

    ``bound_host``/``bound_port`` are set only on the loopback-TCP transport
    (Windows). On a Unix domain socket they stay ``None``: there is no reachable
    name to rebind, so the ``Host`` check is inapplicable and enforcing it would
    refuse legitimate traffic.
    """

    credential: str
    bound_host: str | None = None
    bound_port: int | None = None

    def __post_init__(self) -> None:
        if not self.credential or len(self.credential) < _MIN_CREDENTIAL_LEN:
            raise ValueError(
                "the local-service credential is too short to be a 256-bit value; "
                "refusing to start with a weak credential"
            )

    def check(self, scope: dict) -> None:
        """Admit the request, or raise. Called before the body is read."""
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}

        # Rebinding refusals first: they are cheap, and a request carrying an
        # Origin is a browser request that has no business here whatever
        # credential it presents.
        if "origin" in headers:
            raise TransportRefusal("refused: the request carried an Origin header")
        if "referer" in headers:
            raise TransportRefusal("refused: the request carried a Referer header")
        if self.bound_host is not None:
            expected = {f"{self.bound_host}:{self.bound_port}", self.bound_host}
            if headers.get("host", "") not in expected:
                raise TransportRefusal(
                    "refused: the request was addressed to another name"
                )

        # Credential position. Checked before the value, so a credential in the
        # wrong place is refused even when it is the RIGHT credential — otherwise
        # the position rule is advisory.
        for name in _FORBIDDEN_CREDENTIAL_HEADERS:
            if name in headers:
                raise TransportRefusal(
                    f"refused: a credential may not be presented in the {name} header"
                )
        query = scope.get("query_string", b"") or b""
        for key in _FORBIDDEN_QUERY_KEYS:
            if key + b"=" in b"&" + query:
                raise TransportRefusal("refused: a credential may not be presented in the address")
        if _looks_like_a_credential_segment(scope.get("path", "")):
            raise TransportRefusal("refused: a credential may not be presented in the address")

        presented = headers.get(CREDENTIAL_HEADER)
        if presented is None:
            raise TransportRefusal("refused: no local-service credential was presented")
        # Constant time. A short-circuiting comparison leaks the credential a byte
        # at a time to anything that can time a loopback request.
        if not hmac.compare_digest(presented, self.credential):
            raise TransportRefusal("refused: the local-service credential did not match")


def _looks_like_a_credential_segment(path: str) -> bool:
    """A long opaque path segment is a credential in the address.

    Deliberately shape-based rather than value-based: comparing against the real
    credential here would mean a *wrong* long token in the path sails through,
    and the rule is about the position, not the value.
    """
    return any(
        len(seg) >= _MIN_CREDENTIAL_LEN and seg.replace("-", "").replace("_", "").isalnum()
        for seg in path.split("/")
    )
