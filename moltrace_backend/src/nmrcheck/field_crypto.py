"""Field-level envelope encryption (Security Prompt 7).

Encrypts a single field with a fresh random **data-encryption key (DEK)**, then wraps that DEK
with a **key-encryption key (KEK)** supplied by a :mod:`kms` provider — classic envelope
encryption. The ciphertext is one self-describing ASCII string that carries the algorithm and
the KEK ``key_id``, so the KEK can be rotated (re-wrap the small DEK) without re-encrypting data,
and a stale value can be detected (:func:`needs_rewrap`) and upgraded (:func:`rewrap`).

Envelope (version 2)::

    mtenc.v2.<key_id>.<b64url(header_json)>.<b64url(wrapped_dek)>.<b64url(nonce[12] || ct||tag)>

The ``header_json`` (``{"kid","v","alg","wrap","purpose"}``) is the AAD on *both* the DEK wrap
and the field payload, so the key id, algorithm, and purpose are cryptographically bound —
tampering with any of them fails GCM authentication. (The ``key_id`` is *also* echoed in the
readable dot-field so :func:`needs_rewrap` can scan for stale values without a base64 decode.)

Backward compatibility: a pre-Prompt-7 ``sso_secret_crypto`` value is a single base64url word
(``base64url(nonce||ct||tag)``) — it has no ``mtenc.`` magic prefix, so :func:`decrypt_field`
auto-detects it and decrypts it with the original SHA-256 KDF under the caller's key material.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import kms

_MAGIC = "mtenc"
_VERSION = 2
_DATA_ALG = "AES-256-GCM"
_DEV_FALLBACK = "moltrace-dev-sso-key-change-me"  # legacy KDF fallback parity


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode("ascii"))


def _is_enveloped(token: str) -> bool:
    # A legacy blob is one base64url word (alphabet A-Z a-z 0-9 - _): it can neither contain a
    # '.' nor begin with the literal "mtenc." — so this discriminates with zero false positives.
    return token.startswith(_MAGIC + ".")


def _header_bytes(purpose: str, provider: kms.KekProvider) -> bytes:
    # Canonical (sorted keys, no spaces) so the AAD is byte-reproducible. ``kid`` is included so
    # the KEK key id is authenticated (bound into the AAD), not just echoed in the dot-field.
    return json.dumps(
        {
            "kid": provider.key_id,
            "v": _VERSION,
            "alg": _DATA_ALG,
            "wrap": provider.wrap_alg,
            "purpose": purpose,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def encrypt_field(plaintext: str, *, provider: kms.KekProvider, purpose: str = "secret") -> str:
    """Envelope-encrypt ``plaintext`` under ``provider``'s KEK. Returns the ``mtenc.v2`` string."""
    header = _header_bytes(purpose, provider)
    dek = AESGCM.generate_key(bit_length=256)
    wrapped = provider.wrap_dek(dek, aad=header)
    nonce = os.urandom(12)
    body = nonce + AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), header)
    return ".".join(
        [_MAGIC, f"v{_VERSION}", provider.key_id, _b64e(header), _b64e(wrapped), _b64e(body)]
    )


def decrypt_field(
    token: str, *, provider: kms.KekProvider, legacy_key_material: str | None = None
) -> str:
    """Decrypt an envelope produced by :func:`encrypt_field`, OR a legacy headerless blob
    (auto-detected and decrypted with the original SHA-256 KDF under ``legacy_key_material``)."""
    if not _is_enveloped(token):
        return _legacy_decrypt(token, legacy_key_material)
    _, _ver, _key_id, h_b64, w_b64, body_b64 = token.split(".", 5)
    header = _b64d(h_b64)
    dek = provider.unwrap_dek(_b64d(w_b64), aad=header)
    raw = _b64d(body_b64)
    nonce, blob = raw[:12], raw[12:]
    return AESGCM(dek).decrypt(nonce, blob, header).decode("utf-8")


def needs_rewrap(token: str, *, provider: kms.KekProvider) -> bool:
    """Whether ``token`` should be re-wrapped under ``provider``'s active KEK: True for any
    legacy (headerless) value and for any envelope whose ``key_id`` != the provider's."""
    if not _is_enveloped(token):
        return True
    return token.split(".", 5)[2] != provider.key_id


def rewrap(
    token: str,
    *,
    to_provider: kms.KekProvider,
    from_provider: kms.KekProvider | None = None,
    purpose: str = "secret",
    legacy_key_material: str | None = None,
) -> str:
    """Decrypt under ``from_provider`` (or ``to_provider`` if omitted) and re-encrypt under
    ``to_provider``'s active KEK. Used by the KEK-rotation pass / rewrap-on-write to migrate a
    legacy or old-KEK value to the current key without changing the plaintext.

    Rotation availability note: a value stays decryptable only while *some* provider holding its
    KEK exists. When rotating the underlying key material, keep the OLD KEK available (pass it as
    ``from_provider`` here, or run this rewrap pass over all rows) BEFORE retiring it — otherwise
    old envelopes wrapped under the previous ``key_id`` can no longer be unwrapped.
    """
    source = from_provider if from_provider is not None else to_provider
    plaintext = decrypt_field(token, provider=source, legacy_key_material=legacy_key_material)
    return encrypt_field(plaintext, provider=to_provider, purpose=purpose)


def _legacy_decrypt(token: str, key_material: str | None) -> str:
    key = hashlib.sha256((key_material or _DEV_FALLBACK).encode("utf-8")).digest()
    raw = _b64d(token)
    nonce, blob = raw[:12], raw[12:]
    return AESGCM(key).decrypt(nonce, blob, None).decode("utf-8")
