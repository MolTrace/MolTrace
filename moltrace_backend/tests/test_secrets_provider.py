"""Secrets-provider seam (Security Prompt 8).

Verifies the env backend is a byte-for-byte no-op versus the prior ``os.getenv(...) or default``
idiom, the ``resolve_secret`` (empty→default) vs ``resolve_secret_strict`` (absent-only)
semantics, the ``SECRETS_BACKEND`` switch, a swappable managed-store backend, and that the
settings secret reads are unchanged when no managed backend is configured.
"""

from __future__ import annotations

import pytest

from nmrcheck import secrets_provider
from nmrcheck.secrets_provider import (
    EnvSecretsProvider,
    resolve_secret,
    resolve_secret_strict,
)
from nmrcheck.settings import get_settings


def test_resolve_secret_returns_env_value(monkeypatch):
    monkeypatch.setenv("MOLTRACE_TEST_SECRET", "live-value")
    assert resolve_secret("MOLTRACE_TEST_SECRET") == "live-value"


def test_resolve_secret_falls_back_to_default_when_absent(monkeypatch):
    monkeypatch.delenv("MOLTRACE_TEST_SECRET", raising=False)
    assert resolve_secret("MOLTRACE_TEST_SECRET", default="fallback") == "fallback"
    assert resolve_secret("MOLTRACE_TEST_SECRET") is None


def test_resolve_secret_empty_string_collapses_to_default(monkeypatch):
    # API_KEY="" must resolve to None, preserving the `os.getenv(...) or None` idiom.
    monkeypatch.setenv("API_KEY", "")
    assert resolve_secret("API_KEY") is None


def test_resolve_secret_strict_keeps_empty_string(monkeypatch):
    # DATABASE_URL two-arg semantics: default only when absent, NOT when empty.
    monkeypatch.setenv("DATABASE_URL", "")
    assert resolve_secret_strict("DATABASE_URL", "sqlite:///x") == ""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert resolve_secret_strict("DATABASE_URL", "sqlite:///x") == "sqlite:///x"


@pytest.mark.parametrize("backend", ["env", "ENV", "", "unknown-backend", None])
def test_secrets_backend_env_and_unknown_use_env_provider(monkeypatch, backend):
    if backend is None:
        monkeypatch.delenv("SECRETS_BACKEND", raising=False)
    else:
        monkeypatch.setenv("SECRETS_BACKEND", backend)
    monkeypatch.setenv("MOLTRACE_TEST_SECRET", "from-env")
    assert resolve_secret("MOLTRACE_TEST_SECRET") == "from-env"


def test_fake_vault_backend_is_swappable(monkeypatch):
    class FakeVaultProvider:
        def get(self, name: str) -> str | None:
            return {"API_KEY": "vault-issued"}.get(name)

    monkeypatch.setitem(secrets_provider._BACKENDS, "vault", FakeVaultProvider)
    monkeypatch.setenv("SECRETS_BACKEND", "vault")
    assert resolve_secret("API_KEY") == "vault-issued"
    # A backend miss falls through to the caller default, never raising.
    assert resolve_secret("DATABASE_URL", default="sqlite:///x") == "sqlite:///x"


def test_env_provider_get_matches_os_environ(monkeypatch):
    monkeypatch.setenv("MOLTRACE_TEST_SECRET", "v")
    assert EnvSecretsProvider().get("MOLTRACE_TEST_SECRET") == "v"
    monkeypatch.delenv("MOLTRACE_TEST_SECRET", raising=False)
    assert EnvSecretsProvider().get("MOLTRACE_TEST_SECRET") is None


def test_settings_reads_unchanged_when_backend_unset(monkeypatch):
    monkeypatch.delenv("SECRETS_BACKEND", raising=False)
    monkeypatch.setenv("API_KEY", "k-123")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    monkeypatch.setenv("SSO_ENCRYPTION_KEY", "sso-k")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.api_key == "k-123"
        assert s.database_url == "postgresql+psycopg://u:p@h:5432/db"  # normalize applied
        assert s.sso_encryption_key == "sso-k"
    finally:
        get_settings.cache_clear()


def test_settings_database_url_dev_fallback_when_absent(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().database_url == "sqlite:///./nmrcheck.sqlite3"
    finally:
        get_settings.cache_clear()


def test_settings_empty_api_key_resolves_none(monkeypatch):
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()
    try:
        assert get_settings().api_key is None
    finally:
        get_settings.cache_clear()
