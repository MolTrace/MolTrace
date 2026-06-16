"""Field-level envelope encryption (Security Prompt 7).

Covers the envelope round-trip, transparent legacy (pre-P7 sso_secret_crypto) decryption, KEK
rotation via the self-describing key_id, wrong-key / tamper authentication failures, the BYOK
provider seam, and the unchanged sso_secret_crypto / mfa_totp shim signatures.
"""

from __future__ import annotations

import base64
import hashlib
import os

import pytest
from cryptography.exceptions import InvalidTag

from nmrcheck import field_crypto, kms, mfa_totp, sso_secret_crypto


def _legacy_blob(plaintext: str, key_material: str | None) -> str:
    """Reproduce a pre-Prompt-7 sso_secret_crypto value: base64url(nonce || ct||tag)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = hashlib.sha256((key_material or "moltrace-dev-sso-key-change-me").encode()).digest()
    nonce = os.urandom(12)
    return base64.urlsafe_b64encode(nonce + AESGCM(key).encrypt(nonce, plaintext.encode(), None)).decode()


# --------------------------------------------------------------------------- #
# Envelope round-trip + format
# --------------------------------------------------------------------------- #
def test_envelope_round_trip_and_shape():
    p = kms.build_local_provider("kek-material")
    tok = field_crypto.encrypt_field("hunter2", provider=p)
    assert tok.startswith("mtenc.v2.")
    assert len(tok.split(".")) == 6
    assert tok.split(".")[2] == p.key_id
    assert field_crypto.decrypt_field(tok, provider=p) == "hunter2"


def test_unique_dek_per_encrypt():
    p = kms.build_local_provider("k")
    a = field_crypto.encrypt_field("same", provider=p)
    b = field_crypto.encrypt_field("same", provider=p)
    assert a != b  # fresh DEK + nonce each time
    assert field_crypto.decrypt_field(a, provider=p) == field_crypto.decrypt_field(b, provider=p)


def test_header_carries_alg_and_purpose():
    import json

    p = kms.build_local_provider("k")
    tok = field_crypto.encrypt_field("x", provider=p, purpose="sso")
    header = json.loads(base64.urlsafe_b64decode(tok.split(".")[3]))
    assert header["alg"] == "AES-256-GCM" and header["purpose"] == "sso" and header["v"] == 2


# --------------------------------------------------------------------------- #
# Legacy back-compat
# --------------------------------------------------------------------------- #
def test_legacy_blob_decrypts_transparently():
    p = kms.build_local_provider("sso-key")
    legacy = _legacy_blob("old-secret", "sso-key")
    assert not legacy.startswith("mtenc.")
    assert field_crypto.decrypt_field(legacy, provider=p, legacy_key_material="sso-key") == "old-secret"


def test_legacy_dev_fallback_blob_decrypts():
    p = kms.build_local_provider(None)
    legacy = _legacy_blob("devsecret", None)  # encrypted under the dev fallback key
    assert field_crypto.decrypt_field(legacy, provider=p, legacy_key_material=None) == "devsecret"


def test_legacy_needs_rewrap():
    p = kms.build_local_provider("k")
    assert field_crypto.needs_rewrap(_legacy_blob("x", "k"), provider=p) is True


# --------------------------------------------------------------------------- #
# KEK rotation
# --------------------------------------------------------------------------- #
def test_kek_rotation_rewrap():
    a = kms.build_local_provider("material-A")
    b = kms.build_local_provider("material-B")
    assert a.key_id != b.key_id
    tok_a = field_crypto.encrypt_field("rotate-me", provider=a)
    assert field_crypto.needs_rewrap(tok_a, provider=a) is False
    assert field_crypto.needs_rewrap(tok_a, provider=b) is True  # stale under the new KEK
    tok_b = field_crypto.rewrap(tok_a, to_provider=b, from_provider=a)
    assert tok_b.split(".")[2] == b.key_id
    assert field_crypto.needs_rewrap(tok_b, provider=b) is False
    assert field_crypto.decrypt_field(tok_b, provider=b) == "rotate-me"


def test_rewrap_upgrades_legacy_to_envelope():
    b = kms.build_local_provider("active")
    legacy = _legacy_blob("legacy-secret", "old-key")
    upgraded = field_crypto.rewrap(legacy, to_provider=b, legacy_key_material="old-key")
    assert upgraded.startswith("mtenc.v2.")
    assert field_crypto.decrypt_field(upgraded, provider=b) == "legacy-secret"


# --------------------------------------------------------------------------- #
# Authentication failures
# --------------------------------------------------------------------------- #
def test_wrong_kek_fails():
    a = kms.build_local_provider("right")
    b = kms.build_local_provider("wrong")
    tok = field_crypto.encrypt_field("s", provider=a)
    with pytest.raises(InvalidTag):
        field_crypto.decrypt_field(tok, provider=b)


def test_tampered_body_fails():
    p = kms.build_local_provider("k")
    parts = field_crypto.encrypt_field("s", provider=p).split(".")
    raw = bytearray(base64.urlsafe_b64decode(parts[5]))
    raw[-1] ^= 0x01
    parts[5] = base64.urlsafe_b64encode(bytes(raw)).decode()
    with pytest.raises(InvalidTag):
        field_crypto.decrypt_field(".".join(parts), provider=p)


def test_tampered_header_fails():
    # The header is AAD on the DEK wrap, so altering it breaks the unwrap authentication.
    p = kms.build_local_provider("k")
    parts = field_crypto.encrypt_field("s", provider=p).split(".")
    parts[3] = base64.urlsafe_b64encode(b'{"alg":"X","purpose":"evil","v":2,"wrap":"X"}').decode()
    with pytest.raises(InvalidTag):
        field_crypto.decrypt_field(".".join(parts), provider=p)


# --------------------------------------------------------------------------- #
# BYOK seam
# --------------------------------------------------------------------------- #
def test_byok_provider_swappable():
    """A custom KekProvider (e.g. a cloud KMS) drops in with no field_crypto change."""

    class FakeKms:
        wrap_alg = "fake:kms"
        key_id = "fake-1"

        def wrap_dek(self, dek: bytes, *, aad: bytes) -> bytes:
            return b"\x00" + dek  # not real crypto — just proves the seam round-trips

        def unwrap_dek(self, wrapped_dek: bytes, *, aad: bytes) -> bytes:
            return wrapped_dek[1:]

    fake = FakeKms()
    assert isinstance(fake, kms.KekProvider)  # satisfies the runtime-checkable Protocol
    tok = field_crypto.encrypt_field("byok", provider=fake)
    assert tok.split(".")[2] == "fake-1"
    assert field_crypto.decrypt_field(tok, provider=fake) == "byok"


# --------------------------------------------------------------------------- #
# Shim signatures unchanged (sso_store / mfa_store call sites)
# --------------------------------------------------------------------------- #
def test_sso_secret_crypto_shim_round_trip():
    enc = sso_secret_crypto.encrypt_secret("client-secret", "sso-key")
    assert enc.startswith("mtenc.v2.")
    assert sso_secret_crypto.decrypt_secret(enc, "sso-key") == "client-secret"


def test_mfa_totp_shim_round_trip():
    enc = mfa_totp.encrypt_secret("JBSWY3DPEHPK3PXP", "mfa-key")
    assert mfa_totp.decrypt_secret(enc, "mfa-key") == "JBSWY3DPEHPK3PXP"


def test_shim_decrypts_legacy_value():
    legacy = _legacy_blob("legacy-client-secret", "sso-key")
    assert sso_secret_crypto.decrypt_secret(legacy, "sso-key") == "legacy-client-secret"


def test_sso_and_mfa_keys_isolate():
    # Different key material -> different KEK -> a value encrypted under one key cannot be
    # decrypted under the other (blast-radius isolation preserved).
    sso = sso_secret_crypto.encrypt_secret("s", "sso-key")
    with pytest.raises(InvalidTag):
        sso_secret_crypto.decrypt_secret(sso, "mfa-key")
