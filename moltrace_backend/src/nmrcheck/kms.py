"""KEK providers for envelope encryption (Security Prompt 7).

A KEK (key-encryption-key) provider wraps and unwraps the per-record data-encryption keys
(DEKs) that :mod:`field_crypto` uses to encrypt individual fields. v1 ships
:class:`LocalKekProvider`, which derives a 256-bit KEK from configured key material (the same
SHA-256 KDF family the legacy ``sso_secret_crypto`` helper used) and identifies it by a stable,
non-secret fingerprint ``key_id``. The ``key_id`` rides inside the ciphertext envelope, so the
KEK can be rotated (new material -> new ``key_id``) and a value can be detected as stale and
re-wrapped without re-encrypting anything else.

BYOK / cloud KMS is a documented seam: a provider backed by AWS/GCP KMS implements the same
three members (``key_id``, ``wrap_dek``, ``unwrap_dek``) by calling the KMS Encrypt/Decrypt (or
GenerateDataKey) APIs — ``field_crypto`` never sees raw key material and needs no change. No
cloud SDK is added in v1; :func:`build_local_provider` is the single construction point a future
``build_kek_provider(settings)`` switch would dispatch from.
"""

from __future__ import annotations

import hashlib
import os
from typing import Protocol, runtime_checkable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Dev-only fallback so local/test runs work without configuration — identical to the legacy
# sso_secret_crypto fallback, so dev-encrypted legacy blobs keep decrypting. Production MUST set
# the real SSO_ENCRYPTION_KEY / MFA_ENCRYPTION_KEY (enforced by settings' startup guards).
_DEV_FALLBACK = "moltrace-dev-sso-key-change-me"


@runtime_checkable
class KekProvider(Protocol):
    """Wrap/unwrap a DEK under a key-encryption key identified by ``key_id``."""

    wrap_alg: str

    @property
    def key_id(self) -> str: ...

    def wrap_dek(self, dek: bytes, *, aad: bytes) -> bytes: ...

    def unwrap_dek(self, wrapped_dek: bytes, *, aad: bytes) -> bytes: ...


class LocalKekProvider:
    """In-process KEK derived from configured key material.

    The KEK is ``sha256(key_material)`` (32 bytes) — the same KDF family as the legacy helper, so
    a given secret yields a stable key. ``key_id`` is a separate, non-secret fingerprint of the
    material (a different hash input, so it never reveals the KEK). Wrapping is AES-256-GCM with
    the field header passed as additional authenticated data, binding the wrapped DEK to its
    envelope header.
    """

    wrap_alg = "AES-256-GCM"

    def __init__(self, key_material: str | None) -> None:
        material = (key_material or _DEV_FALLBACK).encode("utf-8")
        self._kek = hashlib.sha256(material).digest()
        self._key_id = "k" + hashlib.sha256(b"mtkek1:" + material).hexdigest()[:12]

    @property
    def key_id(self) -> str:
        return self._key_id

    def wrap_dek(self, dek: bytes, *, aad: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._kek).encrypt(nonce, dek, aad)

    def unwrap_dek(self, wrapped_dek: bytes, *, aad: bytes) -> bytes:
        nonce, blob = wrapped_dek[:12], wrapped_dek[12:]
        return AESGCM(self._kek).decrypt(nonce, blob, aad)


def build_local_provider(key_material: str | None) -> LocalKekProvider:
    """Construct the v1 local KEK provider from configured key material. This is the single
    swap point for BYOK: a cloud-KMS provider implementing :class:`KekProvider` drops in here
    (e.g. selected by a settings flag) without any change to :mod:`field_crypto`."""
    return LocalKekProvider(key_material)
