"""API abuse protection — rate limiting + body-size guard (Security Prompt 16).

Covers the in-process token-bucket limiter (per-IP on public routes, per-user on authenticated
routes, unlimited for the system api key), the 429 + Retry-After / X-RateLimit headers, default-off
behaviour, and the global request-body-size guard (multipart exempt).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from nmrcheck import rate_limit
from nmrcheck.api import create_app
from nmrcheck.database import init_db
from nmrcheck.settings import Settings

SYSTEM = {"x-api-key": "test-key"}


def _app(tmp_path, **overrides):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'rl.sqlite3'}",
        api_key="test-key",
        require_verified_email=False,
        **overrides,
    )
    app = create_app(settings)
    init_db(app.state.session_factory)
    return app


def _signup(client: TestClient, email: str, password: str = "password123") -> dict:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": password, "password_confirm": password},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# --------------------------------------------------------------------------- token-bucket unit


def test_token_bucket_consume_and_refill():
    store = rate_limit.InProcessTokenBucketStore()
    # capacity = limit*burst = 3*1 = 3; refill = 3/60 per second.
    now = 1000.0
    allowed = [store.consume("k", limit=3, window_s=60.0, burst=1.0, now=now)[0] for _ in range(3)]
    assert allowed == [True, True, True]
    blocked, retry_after, remaining = store.consume("k", limit=3, window_s=60.0, burst=1.0, now=now)
    assert blocked is False and remaining == 0 and retry_after > 0
    # After enough time one token refills (60/3 = 20s per token).
    ok, _, _ = store.consume("k", limit=3, window_s=60.0, burst=1.0, now=now + 21.0)
    assert ok is True


def test_distinct_keys_are_independent():
    store = rate_limit.InProcessTokenBucketStore()
    now = 0.0
    assert store.consume("a", limit=1, window_s=60.0, burst=1.0, now=now)[0] is True
    assert store.consume("a", limit=1, window_s=60.0, burst=1.0, now=now)[0] is False
    # different key still has a full bucket
    assert store.consume("b", limit=1, window_s=60.0, burst=1.0, now=now)[0] is True


# --------------------------------------------------------------------------- middleware behaviour


def test_disabled_by_default_no_throttle(tmp_path):
    app = _app(tmp_path)  # rate_limit_enabled defaults False
    with TestClient(app) as client:
        codes = {client.get("/health").status_code for _ in range(40)}
        assert codes == {200}


def test_public_route_throttled_by_ip(tmp_path):
    app = _app(
        tmp_path, rate_limit_enabled=True, rate_limit_default_per_minute=3, rate_limit_burst_multiplier=1.0
    )
    with TestClient(app) as client:
        oks = [client.get("/health").status_code for _ in range(3)]
        assert oks == [200, 200, 200]
        blocked = client.get("/health")
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) >= 1
        assert blocked.headers["x-ratelimit-limit"] == "3"
        assert blocked.headers["x-ratelimit-remaining"] == "0"


def test_authenticated_route_per_user_isolation(tmp_path):
    app = _app(
        tmp_path, rate_limit_enabled=True, rate_limit_default_per_minute=3, rate_limit_burst_multiplier=1.0
    )
    with TestClient(app) as client:
        a = _signup(client, "a@acme.com")
        b = _signup(client, "b@acme.com")
        # User A exhausts the per-user bucket on an authenticated route.
        a_codes = [client.get("/controlled-records", headers=a).status_code for _ in range(3)]
        assert a_codes == [200, 200, 200]
        assert client.get("/controlled-records", headers=a).status_code == 429
        # User B has an independent bucket — not affected by A's throttle.
        assert client.get("/controlled-records", headers=b).status_code == 200


def test_system_api_key_is_unlimited(tmp_path):
    app = _app(
        tmp_path, rate_limit_enabled=True, rate_limit_default_per_minute=1, rate_limit_burst_multiplier=1.0
    )
    with TestClient(app) as client:
        codes = {client.get("/controlled-records", headers=SYSTEM).status_code for _ in range(20)}
        assert codes == {200}  # system api key bypasses the limiter


# --------------------------------------------------------------------------- body-size guard


def test_oversized_json_body_rejected(tmp_path):
    app = _app(tmp_path, max_request_body_bytes=1000)  # rate limiter stays off
    with TestClient(app) as client:
        big = {
            "email": "x@acme.com",
            "password": "p" * 4000,
            "password_confirm": "p" * 4000,
        }
        res = client.post("/auth/sign-up", json=big)
        assert res.status_code == 413, res.text
        # A small body passes the guard (the route then handles it — not a 413).
        small = client.post(
            "/auth/sign-up",
            json={"email": "ok@acme.com", "password": "password123", "password_confirm": "password123"},
        )
        assert small.status_code != 413


def test_credential_routes_resolve_to_tight_auth_policy():
    """Drift guard: the abuse-prone auth endpoints must map to the tight 'auth' policy, not the
    generous default (regression for the review finding that register/sign-in/email-verification fell
    through to 300/min)."""
    s = Settings(database_url="sqlite://", api_key="k")
    for path in (
        "/auth/login",
        "/auth/sign-in",
        "/auth/register",
        "/auth/sign-up",
        "/auth/request-password-reset",
        "/auth/reset-password",
        "/auth/request-email-verification",
        "/auth/verify-email",
        "/auth/step-up/password",
        "/auth/mfa/login/totp",
    ):
        assert rate_limit._policy_for(path, s).scope == "auth", path
    assert rate_limit._policy_for("/controlled-records", s).scope == "default"


def test_body_guard_rejects_chunked_when_capped():
    """A chunked (no Content-Length) non-multipart body can't be size-checked → 413 when a cap is
    set; multipart is exempt; no cap is a no-op (regression for the chunked-bypass finding)."""

    class _Req:
        def __init__(self, headers):
            self.headers = headers

    capped = Settings(database_url="sqlite://", api_key="k", max_request_body_bytes=1000)
    with pytest.raises(HTTPException) as exc:
        rate_limit._enforce_body_size(
            _Req({"transfer-encoding": "chunked", "content-type": "application/json"}), capped
        )
    assert exc.value.status_code == 413
    # multipart chunked is exempt (no raise)
    rate_limit._enforce_body_size(
        _Req({"transfer-encoding": "chunked", "content-type": "multipart/form-data"}), capped
    )
    # cap off → no raise
    rate_limit._enforce_body_size(
        _Req({"transfer-encoding": "chunked"}),
        Settings(database_url="sqlite://", api_key="k"),
    )


def test_multipart_is_exempt_from_body_guard(tmp_path):
    app = _app(tmp_path, max_request_body_bytes=1000)
    with TestClient(app) as client:
        # A large multipart upload must NOT be 413'd by the global guard (uploads have their own caps).
        res = client.post(
            "/auth/sign-up",
            headers={"content-type": "multipart/form-data; boundary=x"},
            content=b"--x\r\n" + b"A" * 5000 + b"\r\n--x--\r\n",
        )
        assert res.status_code != 413
