"""RFC 6238 TOTP second factor (Security Prompt 3).

Thin, testable wrapper over :mod:`pyotp`. The base32 secret is AES-256-GCM encrypted at rest
(:mod:`sso_secret_crypto`, under the separate ``mfa_encryption_key``); a secret is only usable once
*confirmed* (a code was verified). Verification enforces a ±1 step (30s) drift window AND a
``last_used_step`` replay guard so a captured code cannot be replayed within its validity window.
"""

from __future__ import annotations

import hmac
from datetime import UTC, datetime

import pyotp

from . import sso_secret_crypto

_VALID_WINDOW = 1  # accept the current 30s step plus one on each side


def generate_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(secret: str, key_material: str | None) -> str:
    return sso_secret_crypto.encrypt_secret(secret, key_material)


def decrypt_secret(token: str, key_material: str | None) -> str:
    return sso_secret_crypto.decrypt_secret(token, key_material)


def provisioning_uri(secret: str, *, account_name: str, issuer: str) -> str:
    """The ``otpauth://`` URI the authenticator app consumes (rendered as a QR by the SPA)."""
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer)


def verify(
    secret: str,
    code: str,
    *,
    last_used_step: int | None = None,
    for_time: datetime | None = None,
) -> int | None:
    """Return the accepted timestep counter if ``code`` is valid within the drift window AND newer
    than ``last_used_step`` (replay guard); otherwise ``None``. The caller persists the returned
    step as the new ``last_used_step``."""
    cleaned = (code or "").strip().replace(" ", "")
    if not cleaned.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    now = for_time or datetime.now(UTC)
    current = totp.timecode(now)
    for offset in range(-_VALID_WINDOW, _VALID_WINDOW + 1):
        step = current + offset
        if hmac.compare_digest(totp.generate_otp(step), cleaned):
            if last_used_step is not None and step <= last_used_step:
                return None  # replay of an already-consumed (or older) step
            return step
    return None
