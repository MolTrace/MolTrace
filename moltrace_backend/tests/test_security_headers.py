"""Transport security headers (Security Prompt 9).

The response middleware always emits the safe browser-hardening headers and emits HSTS ONLY over
HTTPS (honouring the TLS-terminating edge's X-Forwarded-Proto), with the directive built from
configurable settings. Local plain-HTTP dev is never pinned to HTTPS.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _app(tmp_path, **overrides):
    base = dict(
        database_url=f"sqlite:///{tmp_path / 'sec_headers.sqlite3'}",
        api_key="test-key",
        require_verified_email=False,
    )
    base.update(overrides)
    return create_app(Settings(**base))


def test_safe_security_headers_always_present(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        r = client.get("/health")
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "geolocation=()" in r.headers["Permissions-Policy"]


def test_hsts_absent_on_plain_http(tmp_path):
    # TestClient speaks http:// and sends no X-Forwarded-Proto, so HSTS must NOT be emitted.
    with TestClient(_app(tmp_path)) as client:
        r = client.get("/health")
        assert "Strict-Transport-Security" not in r.headers


def test_hsts_present_when_forwarded_proto_https(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        r = client.get("/health", headers={"X-Forwarded-Proto": "https"})
        hsts = r.headers.get("Strict-Transport-Security")
        assert hsts is not None
        assert "max-age=63072000" in hsts
        assert "includeSubDomains" in hsts
        assert "preload" in hsts


def test_hsts_directive_is_configurable(tmp_path):
    app = _app(
        tmp_path,
        hsts_max_age_seconds=3600,
        hsts_include_subdomains=False,
        hsts_preload=False,
    )
    with TestClient(app) as client:
        r = client.get("/health", headers={"X-Forwarded-Proto": "https"})
        hsts = r.headers["Strict-Transport-Security"]
        assert hsts == "max-age=3600"
        assert "includeSubDomains" not in hsts
        assert "preload" not in hsts


def test_hsts_can_be_disabled(tmp_path):
    with TestClient(_app(tmp_path, hsts_enabled=False)) as client:
        r = client.get("/health", headers={"X-Forwarded-Proto": "https"})
        assert "Strict-Transport-Security" not in r.headers


def test_security_headers_on_authed_and_error_responses(tmp_path):
    with TestClient(_app(tmp_path)) as client:
        # 401 (anonymous to a gated route) still carries the hardening headers.
        r = client.get("/auth/me")
        assert r.status_code == 401
        assert r.headers["X-Content-Type-Options"] == "nosniff"
