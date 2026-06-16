"""Symmetric encryption for SSO IdP client secrets (and MFA TOTP seeds) at rest.

As of Security Prompt 7 this is a thin compatibility shim over the envelope-encryption layer
(:mod:`field_crypto`): new values are KMS-envelope ciphertexts (a fresh per-record AES-256-GCM
data key wrapped by a key-encryption key derived from the caller's ``key_material``), while
pre-Prompt-7 ``base64url(nonce||ct||tag)`` blobs are auto-detected and still decrypt unchanged.
The ``encrypt_secret`` / ``decrypt_secret`` signatures — and therefore every call site in
``sso_store`` and ``mfa_store`` (via ``mfa_totp``) — are deliberately unchanged. Blast-radius
isolation between SSO and MFA is preserved because each is passed a different ``key_material``
(``sso_encryption_key`` vs ``mfa_encryption_key``), yielding distinct KEKs and ``key_id``s.
"""

from __future__ import annotations

from . import field_crypto, kms


def encrypt_secret(plaintext: str, key_material: str | None) -> str:
    """Envelope-encrypt a secret under a KEK derived from ``key_material``."""
    return field_crypto.encrypt_field(plaintext, provider=kms.build_local_provider(key_material))


def decrypt_secret(token: str, key_material: str | None) -> str:
    """Decrypt a value produced by :func:`encrypt_secret`, or a legacy headerless blob
    (transparently, using ``key_material`` as the legacy SHA-256 KDF input)."""
    return field_crypto.decrypt_field(
        token,
        provider=kms.build_local_provider(key_material),
        legacy_key_material=key_material,
    )
