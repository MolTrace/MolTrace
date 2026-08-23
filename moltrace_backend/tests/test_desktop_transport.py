"""§7.1 transport controls for the local scientific service.

Written before the implementation. Every assertion here is a sentence from the
desktop specification's §7.1, turned into something that fails.

The controls are layered on purpose, and §7.1 says why: the Origin/Referer/Host
refusals "defeat classic rebinding but not a direct loopback subresource load" —
a ``script``/``img``/``link``/``iframe`` request sends no Origin, and a page-level
referrer policy suppresses Referer. The credential-position rule is what closes
that path. **Both controls are required**, so both are tested, and neither is
allowed to stand in for the other.
"""

from __future__ import annotations

import pytest

from nmrcheck.desktop_transport import (
    CREDENTIAL_HEADER,
    DesktopTransportGuard,
    TransportRefusal,
)

CRED = "a" * 43


def guard(**kw) -> DesktopTransportGuard:
    return DesktopTransportGuard(credential=CRED, **kw)


def headers(**kw) -> list[tuple[bytes, bytes]]:
    return [(k.lower().encode(), v.encode()) for k, v in kw.items()]


def scope(path="/health", hdrs=None, query=b"") -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query,
        "headers": hdrs if hdrs is not None else headers(**{CREDENTIAL_HEADER: CRED}),
    }


# --- the credential, and only where it belongs ------------------------------


def test_the_named_header_is_accepted() -> None:
    assert guard().check(scope()) is None


def test_a_missing_credential_is_refused() -> None:
    with pytest.raises(TransportRefusal):
        guard().check(scope(hdrs=[]))


def test_a_wrong_credential_is_refused() -> None:
    with pytest.raises(TransportRefusal):
        guard().check(scope(hdrs=headers(**{CREDENTIAL_HEADER: "b" * 43})))


@pytest.mark.parametrize("position", ["query", "cookie", "authorization"])
def test_the_credential_is_refused_in_every_other_position(position: str) -> None:
    """§7.1: refuse it in the query string, path, cookie and body.

    A URL-borne credential is the form a subresource load can carry, so accepting
    one anywhere else would reopen the path the header rule exists to close.

    THE VALID HEADER IS ESSENTIAL AND WAS MISSING. A first version supplied the
    credential ONLY in the forbidden position, so every case was refused for
    "no credential presented" and passed whether or not the position rule
    existed — measured: deleting the rule left this test green. Presenting a
    VALID header alongside means the position rule is the only thing that can
    refuse, so the test now fails when it is removed.
    """
    valid = {CREDENTIAL_HEADER: CRED}
    if position == "query":
        s = scope(hdrs=headers(**valid), query=f"access_token={CRED}".encode())
    elif position == "cookie":
        s = scope(hdrs=headers(**valid, cookie=f"credential={CRED}"))
    else:
        s = scope(hdrs=headers(**valid, authorization=f"Bearer {CRED}"))
    with pytest.raises(TransportRefusal):
        guard().check(s)


def test_a_credential_in_the_path_is_refused() -> None:
    """Valid header present, so only the path rule can refuse this. See above."""
    with pytest.raises(TransportRefusal):
        guard().check(scope(path=f"/health/{CRED}", hdrs=headers(**{CREDENTIAL_HEADER: CRED})))


def test_comparison_is_constant_time() -> None:
    """§7.1: "comparing it in constant time before any request body is read"."""
    import inspect

    from nmrcheck import desktop_transport

    src = inspect.getsource(desktop_transport)
    assert "compare_digest" in src, "the credential is not compared in constant time"
    assert "== self.credential" not in src, "a short-circuiting comparison leaks the credential"


# --- the rebinding refusals -------------------------------------------------


def test_any_origin_header_is_refused() -> None:
    """§7.1: "Refuse any request carrying an Origin or Referer header." Any, not a bad one."""
    s = scope(hdrs=headers(**{CREDENTIAL_HEADER: CRED, "origin": "https://moltrace.co"}))
    with pytest.raises(TransportRefusal):
        guard().check(s)


def test_any_referer_header_is_refused() -> None:
    s = scope(hdrs=headers(**{CREDENTIAL_HEADER: CRED, "referer": "https://moltrace.co/x"}))
    with pytest.raises(TransportRefusal):
        guard().check(s)


def test_a_wrong_host_is_refused_on_loopback_tcp() -> None:
    g = guard(bound_host="127.0.0.1", bound_port=51234)
    s = scope(hdrs=headers(**{CREDENTIAL_HEADER: CRED, "host": "evil.example"}))
    with pytest.raises(TransportRefusal):
        g.check(s)


def test_the_bound_host_is_accepted_on_loopback_tcp() -> None:
    g = guard(bound_host="127.0.0.1", bound_port=51234)
    s = scope(hdrs=headers(**{CREDENTIAL_HEADER: CRED, "host": "127.0.0.1:51234"}))
    assert g.check(s) is None


def test_host_is_not_checked_on_a_unix_socket() -> None:
    """§7.1: "a Unix domain socket has no reachable name to rebind and the check is
    inapplicable there." Enforcing it anyway would refuse legitimate traffic."""
    s = scope(hdrs=headers(**{CREDENTIAL_HEADER: CRED, "host": "anything"}))
    assert guard().check(s) is None


# --- the properties that keep the whole thing honest -------------------------


def test_a_refusal_names_no_secret() -> None:
    for s in (
        scope(hdrs=[]),
        scope(hdrs=headers(**{CREDENTIAL_HEADER: "b" * 43})),
        scope(hdrs=[], query=f"access_token={CRED}".encode()),
    ):
        with pytest.raises(TransportRefusal) as exc:
            guard().check(s)
        assert CRED not in str(exc.value), "the refusal echoed the credential"


def test_every_refusal_names_its_cause() -> None:
    with pytest.raises(TransportRefusal) as exc:
        guard().check(scope(hdrs=headers(**{CREDENTIAL_HEADER: CRED, "origin": "x"})))
    assert len(str(exc.value)) > 10
