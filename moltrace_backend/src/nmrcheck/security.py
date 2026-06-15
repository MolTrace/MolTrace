"""Credential hashing and token primitives.

Passwords are hashed with **Argon2id** (Security Prompt 6) — a memory-hard KDF per the §7
crypto-binding table (Argon2id, 64–256 MB, t≥3, p≥1, unique salt, optional KMS-held pepper).
The argon2 hash string is self-describing (it embeds the algorithm + m/t/p parameters and the
salt), which gives crypto-agility: :func:`needs_rehash` detects an out-of-policy or legacy hash
and the login path transparently upgrades it on the next successful sign-in — no migration.

Backward compatibility: pre-Prompt-6 passwords were stored as ``pbkdf2_sha256$...``.
:func:`verify_password` still verifies those (so no user is locked out), and :func:`needs_rehash`
flags them for upgrade to Argon2id. New hashes are never PBKDF2.

High-entropy random secrets (session/refresh/action tokens, MFA recovery codes, share-link
tokens) are NOT passwords — they are 256-bit unguessable values, so :func:`token_digest`
(SHA-256) is the correct, fast at-rest digest for them; a memory-hard KDF buys nothing there and
would only slow the hot auth path. Argon2id is reserved for low-entropy, user-chosen credentials.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher, Type
from argon2.exceptions import HashingError, InvalidHashError, VerificationError, VerifyMismatchError

# --- Argon2id parameters (§7 binding: 64–256 MB, t>=3, p>=1, unique salt) -------------------
# These match argon2-cffi's secure defaults and the OWASP Argon2id recommendation. Bumping any
# of them later is safe: existing hashes verify, needs_rehash() flags them, and the login path
# re-hashes on the next sign-in (crypto-agility, no migration).
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536  # KiB = 64 MiB
ARGON2_PARALLELISM = 4
ARGON2_HASH_LEN = 32
ARGON2_SALT_LEN = 16

# Legacy PBKDF2 scheme (pre-Prompt-6) — verified for back-compat, never newly emitted.
_LEGACY_PBKDF2_ALGORITHM = "sha256"
_LEGACY_PBKDF2_PREFIX = f"pbkdf2_{_LEGACY_PBKDF2_ALGORITHM}"

SALT_BYTES = 16  # retained for any external importers; legacy PBKDF2 salt width
TOKEN_BYTES = 32

# Reused for the common (no-pepper) path so we don't rebuild the hasher per call. A pepper, when
# configured, is passed as argon2's ``secret=`` and needs a distinct instance (see _hasher).
_DEFAULT_HASHER = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST,
    parallelism=ARGON2_PARALLELISM,
    hash_len=ARGON2_HASH_LEN,
    salt_len=ARGON2_SALT_LEN,
    type=Type.ID,
)


def _peppered(password: str, pepper: str | None) -> str:
    """Pre-mix a configured pepper into the password before Argon2id. The pepper (a KMS-held
    application secret, §7) is used as an HMAC-SHA256 key, so a stolen DB *without* the pepper
    cannot be brute-forced offline. Done as a pre-hash (rather than argon2's native ``secret=``,
    which this argon2-cffi version's high-level API does not expose) so it is independent of the
    backend version and the hash string format is unchanged."""
    if not pepper:
        return password
    return hmac.new(pepper.encode("utf-8"), password.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_password(password: str, *, pepper: str | None = None) -> str:
    """Hash a password with Argon2id (+ optional pepper). The returned string is self-describing
    (``$argon2id$v=19$m=...,t=...,p=...$salt$hash``)."""
    try:
        return _DEFAULT_HASHER.hash(_peppered(password, pepper))
    except HashingError as exc:  # pragma: no cover - argon2 backend failure
        raise ValueError("Password hashing failed.") from exc


def verify_password(password: str, stored_hash: str, *, pepper: str | None = None) -> bool:
    """Verify ``password`` against ``stored_hash``. Accepts both the current Argon2id format and
    legacy ``pbkdf2_sha256$...`` hashes (back-compat), returning a plain bool (never raises)."""
    if not stored_hash:
        return False
    if stored_hash.startswith("$argon2"):
        try:
            return _DEFAULT_HASHER.verify(stored_hash, _peppered(password, pepper))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    if stored_hash.startswith(_LEGACY_PBKDF2_PREFIX):
        # Legacy PBKDF2 hashes predate the pepper; verify them as-is, then the login path's
        # needs_rehash()->True upgrades them to a peppered Argon2id hash on success.
        return _verify_legacy_pbkdf2(password, stored_hash)
    return False


def needs_rehash(stored_hash: str, *, pepper: str | None = None) -> bool:
    """Whether ``stored_hash`` should be re-hashed on the next successful login: True for any
    legacy (non-argon2) hash, and for an Argon2id hash whose parameters are below current policy.
    The caller (the login path) re-hashes the verified plaintext and persists it. Total over any
    input (empty/None -> True) so it never raises, mirroring :func:`verify_password`."""
    if not stored_hash or not stored_hash.startswith("$argon2"):
        return True
    try:
        return _DEFAULT_HASHER.check_needs_rehash(stored_hash)
    except InvalidHashError:  # pragma: no cover - malformed argon2 string
        return True


def _verify_legacy_pbkdf2(password: str, stored_hash: str) -> bool:
    """Constant-time verification of a pre-Prompt-6 ``pbkdf2_sha256$iters$salt$digest`` hash."""
    try:
        scheme, iterations_str, salt_hex, digest_hex = stored_hash.split("$", 3)
    except ValueError:
        return False
    if scheme != _LEGACY_PBKDF2_PREFIX:
        return False
    try:
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        if iterations <= 0:
            # pbkdf2_hmac rejects a non-positive count with a ValueError; a corrupted/tampered
            # hash must degrade to a denied login (False), never raise into a 5xx.
            return False
        candidate = hashlib.pbkdf2_hmac(
            _LEGACY_PBKDF2_ALGORITHM, password.encode("utf-8"), salt, iterations
        )
    except ValueError:
        return False
    return hmac.compare_digest(candidate, expected)


def create_access_token(ttl_minutes: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    return token, expires_at


def create_action_token(ttl_minutes: int) -> tuple[str, datetime]:
    return create_access_token(ttl_minutes)


def token_digest(token: str) -> str:
    """SHA-256 at-rest digest for HIGH-ENTROPY random tokens (session/refresh/action tokens,
    recovery codes, share links). These are 256-bit unguessable values, so a fast hash is correct
    and a memory-hard KDF is unnecessary — Argon2id is reserved for low-entropy passwords."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


RECOVERY_CODE_COUNT = 10


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """One-time MFA recovery codes, formatted ``xxxxx-xxxxx`` (40 bits each). Returned once at
    enrollment; only their :func:`token_digest` is persisted."""
    codes: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(5)  # 10 hex chars
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def normalize_recovery_code(code: str) -> str:
    """Canonicalize a user-entered recovery code before hashing (tolerate spaces / case)."""
    return code.strip().lower().replace(" ", "")
