"""Secrets provider seam (Security Prompt 8).

:func:`resolve_secret` / :func:`resolve_secret_strict` are the single read-point for the
credential-class env vars (DATABASE_URL, REDIS_URL, API_KEY, SSO/MFA encryption keys, password
pepper). The default backend reads ``os.environ`` and is a **byte-for-byte no-op** versus the
prior ``os.getenv(name) or default`` idiom, so behavior is identical when ``SECRETS_BACKEND`` is
unset or ``env`` and the existing suite stays green.

A managed store (HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager) is adopted by
implementing :class:`SecretsProvider` in a new backend, registering it in :data:`_BACKENDS`, and
selecting it via ``SECRETS_BACKEND``. With a Vault backend, ``DATABASE_URL`` can be issued by the
DB secrets engine as a short-lived dynamic credential — the provider interface is the swap point.
No cloud SDK ships in v1 (mirrors how Prompt 7 shipped the BYOK seam without live infra). See
``docs/ops_secrets_management.md``.
"""

from __future__ import annotations

import os
from typing import Protocol


class SecretsProvider(Protocol):
    """Interface a managed-store backend implements.

    ``get`` returns the raw secret value for ``name`` or ``None`` when the backend has no value
    for it. Returning ``None`` (rather than raising) lets :func:`resolve_secret` apply the
    caller's ``default`` uniformly across backends and degrade exactly like ``os.getenv``.
    """

    def get(self, name: str) -> str | None: ...


class EnvSecretsProvider:
    """Default backend: read the process environment. A behavioral no-op vs ``os.getenv``."""

    def get(self, name: str) -> str | None:
        return os.environ.get(name)


# Registry of available backends. A managed-store backend registers here, e.g.
#   _BACKENDS["vault"] = VaultSecretsProvider
# Kept env-only in v1 so importing this module pulls in no cloud SDK.
_BACKENDS: dict[str, type[SecretsProvider]] = {
    "env": EnvSecretsProvider,
}


def _select_provider() -> SecretsProvider:
    """Pick the backend named by ``SECRETS_BACKEND`` (default ``env``). An unset/unknown value
    falls back to the env backend, so a misconfiguration degrades to the prior behavior rather
    than silently resolving every secret to ``None``."""
    backend = (os.environ.get("SECRETS_BACKEND") or "env").strip().lower()
    provider_cls = _BACKENDS.get(backend, EnvSecretsProvider)
    return provider_cls()


def resolve_secret(name: str, *, default: str | None = None) -> str | None:
    """Resolve a credential-class secret with ``os.getenv(name) or default`` semantics: an unset
    key OR an empty string collapses to ``default``. This preserves the existing
    ``os.getenv(...) or None`` idiom for API_KEY / REDIS_URL / encryption keys / pepper, where
    ``API_KEY=""`` must resolve to ``None``."""
    value = _select_provider().get(name)
    return value or default


def resolve_secret_strict(name: str, default: str | None = None) -> str | None:
    """Like :func:`resolve_secret` but with two-arg ``os.getenv`` semantics: ``default`` is
    applied ONLY when the key is absent, not when it is empty. Used for ``DATABASE_URL`` so the
    read stays a strict no-op versus ``os.getenv("DATABASE_URL", "<dev sqlite>")`` (an explicit
    empty value is honored, not replaced by the default)."""
    value = _select_provider().get(name)
    return default if value is None else value
