"""Credentials resolve at most once per request — without weakening the gate.

``_baseline_access_gate`` calls ``get_optional_access_context`` as a plain
function rather than a ``Depends`` parameter. That is deliberate: resolving as a
parameter would run BEFORE the public-route short-circuit, so a stale credential
riding along on a public route (an SPA re-attaching an expired bearer to
``/auth/login``, an LB probe carrying a rotated api key) would become a 401
lockout. The cost is that FastAPI's per-request ``dependency_cache`` does not
cover the call, so a route's own ``Depends(require_access_context)`` resolved the
same credential a second time: a second session, the same SELECTs, and a second
``last_used_at`` UPDATE + COMMIT on the hottest row in the system.

The memo lives on ``request.state`` (per-request in Starlette). These tests pin
both halves: the duplicate work is gone, AND every authentication guarantee the
gate makes still holds.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck import api as api_module
from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _app(tmp_path, **overrides):
    base = dict(
        database_url=f"sqlite:///{tmp_path / 'auth_once.sqlite3'}",
        api_key="test-key",
        require_verified_email=False,
    )
    base.update(overrides)
    return create_app(Settings(**base))


def _count_token_lookups(monkeypatch) -> list[int]:
    """Count get_user_by_token calls, as imported into the api module."""
    calls = [0]
    real = api_module.get_user_by_token

    def counting(*args, **kwargs):
        calls[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(api_module, "get_user_by_token", counting)
    return calls


def _register_and_login(client) -> str:
    client.post(
        "/auth/register",
        json={"email": "once@example.com", "password": "correct-horse-battery-1"},
    )
    response = client.post(
        "/auth/login",
        json={"email": "once@example.com", "password": "correct-horse-battery-1"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_a_bearer_request_resolves_its_token_once(tmp_path, monkeypatch):
    with TestClient(_app(tmp_path)) as client:
        token = _register_and_login(client)
        calls = _count_token_lookups(monkeypatch)
        response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200, response.text

    assert calls[0] == 1, (
        f"the same bearer was resolved {calls[0]} times in one request — the router "
        "gate and the route dependency are each doing their own lookup, which is a "
        "second session, SELECTs and a last_used_at UPDATE+COMMIT per request"
    )


def test_an_invalid_bearer_is_still_rejected(tmp_path):
    # The memo must never turn a bad credential into an accepted one.
    with TestClient(_app(tmp_path)) as client:
        response = client.get("/history", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


def test_a_missing_credential_is_still_rejected_on_a_gated_route(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        response = client.get("/history")
    assert response.status_code == 401


def test_a_wrong_api_key_is_still_rejected(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        response = client.get("/history", headers={"x-api-key": "wrong-key"})
    assert response.status_code == 401


def test_a_stale_credential_on_a_public_route_is_still_ignored(tmp_path):
    """The ordering the gate protects, re-pinned.

    A public route must ignore a stray/expired credential rather than 401. The
    memo must not have moved resolution earlier for public routes.
    """
    with TestClient(_app(tmp_path)) as client:
        response = client.get("/health", headers={"Authorization": "Bearer expired-token"})
    assert response.status_code == 200


def test_the_memo_does_not_leak_between_requests(tmp_path, monkeypatch):
    """request.state is per-request; prove one caller's context cannot serve another."""
    with TestClient(_app(tmp_path)) as client:
        token = _register_and_login(client)
        ok = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert ok.status_code == 200
        # A DIFFERENT caller, immediately after, with a bad token must not inherit
        # the previous request's resolved context.
        bad = client.get("/auth/me", headers={"Authorization": "Bearer not-a-token"})
        assert bad.status_code == 401
        # ...and an unauthenticated one must not either.
        anon = client.get("/history")
        assert anon.status_code == 401


def test_resolving_twice_in_one_request_hits_the_database_once(tmp_path, monkeypatch):
    """The memo itself, proven directly.

    (Note on method: this cannot be shown by monkeypatching the module attribute
    and counting calls — FastAPI's ``Depends`` captured the original function
    object at decoration time, so a patched name only ever observes the router
    gate's call, not the route's. So the resolver is exercised directly instead:
    two resolutions of one request must reach the database once.)
    """
    from starlette.requests import Request

    with TestClient(_app(tmp_path)) as client:
        token = _register_and_login(client)
        app = client.app

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/history",
        "headers": [],
        "query_string": b"",
        "app": app,
        "state": {},
    }
    request = Request(scope)
    lookups = _count_token_lookups(monkeypatch)

    import asyncio

    async def resolve_twice():
        first = await api_module.get_optional_access_context(
            request, None, token, None
        )
        second = await api_module.get_optional_access_context(
            request, None, token, None
        )
        return first, second

    first, second = asyncio.run(resolve_twice())

    assert first is not None and first.user is not None
    assert second is first, "the second resolution built a fresh context instead of reusing"
    assert lookups[0] == 1, (
        f"two resolutions of one request made {lookups[0]} database lookups — each is a "
        "session, the token/family/user SELECTs and a last_used_at UPDATE+COMMIT"
    )


def test_an_api_key_still_takes_precedence_over_a_bearer(tmp_path):
    """The resolver's branch order, re-pinned after the refactor.

    The original was a sequence of early returns; memoising required a single
    assignment, so the branches became if/elif/else. That rewrite is exactly
    where precedence can silently invert: an x-api-key present must be judged on
    its own (match -> system principal, mismatch -> 401) and must never fall
    through to the bearer, or a bad key alongside a good token would quietly
    authenticate as the user.
    """
    with TestClient(_app(tmp_path)) as client:
        token = _register_and_login(client)
        # Good bearer, BAD api key -> the key decides, and it fails.
        both = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}", "x-api-key": "wrong-key"},
        )
        assert both.status_code == 401, (
            "a bad x-api-key fell through to the bearer instead of failing closed"
        )
        # Good api key alone -> system principal reaches a gated route.
        keyed = client.get("/history", headers={"x-api-key": "test-key"})
        assert keyed.status_code == 200


def test_local_auth_disabled_still_short_circuits(tmp_path):
    # The resolver's FIRST branch: a local demo deployment needs no credential
    # at all. local_auth_disabled is derived (non-production + disable_auth or
    # no api key), so it is driven through those, not set directly.
    with TestClient(_app(tmp_path, app_env="development", disable_auth=True)) as client:
        assert client.get("/history").status_code == 200
