"""Symmetric encryption for SSO IdP client secrets at rest (Prompt 1, SSO).

AES-256-GCM (authenticated encryption) with a key derived from a configured secret. This
is a deliberate, self-contained seam: Prompt 7 (field-level encryption via KMS envelope
encryption) will replace ``_derive_key`` with a managed-KMS data key without changing the
``encrypt_secret`` / ``decrypt_secret`` call sites. The stored value is
``base64url(nonce[12] || ciphertext||tag)``.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Dev-only fallback so local/test runs work without configuration. Production MUST set
# SSO_ENCRYPTION_KEY (see settings); a real key is required before any tenant onboards SSO.
_DEV_FALLBACK = "moltrace-dev-sso-key-change-me"


def _derive_key(key_material: str | None) -> bytes:
    """32-byte AES key from the configured secret. SHA-256 is a fine KDF for a
    high-entropy configured key; Prompt 7 swaps this for a KMS-issued data key."""
    return hashlib.sha256((key_material or _DEV_FALLBACK).encode("utf-8")).digest()


def encrypt_secret(plaintext: str, key_material: str | None) -> str:
    key = _derive_key(key_material)
    nonce = os.urandom(12)
    blob = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + blob).decode("ascii")


def decrypt_secret(token: str, key_material: str | None) -> str:
    key = _derive_key(key_material)
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce, blob = raw[:12], raw[12:]
    return AESGCM(key).decrypt(nonce, blob, None).decode("utf-8")
