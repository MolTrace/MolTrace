"""Argon2id credential hashing (Security Prompt 6).

Two tiers: pure security.py unit tests (hash/verify/needs_rehash/pepper, legacy PBKDF2
back-compat, token_digest unchanged) and API/DB integration tests proving the transparent
rehash-on-login migration from legacy PBKDF2 to Argon2id, and the optional KMS-held pepper
end-to-end through signup -> login -> reset.
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi.testclient import TestClient

from nmrcheck import security as S
from nmrcheck.api import create_app
from nmrcheck.database import authenticate_user, init_db, session_scope
from nmrcheck.orm import UserORM
from nmrcheck.settings import Settings


def _legacy_pbkdf2(password: str, *, iterations: int = 390_000) -> str:
    """Reproduce a pre-Prompt-6 ``pbkdf2_sha256$...`` hash for back-compat tests."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


# --------------------------------------------------------------------------- #
# Unit — Argon2id hashing
# --------------------------------------------------------------------------- #
def test_hash_password_is_argon2id_and_verifies():
    h = S.hash_password("correct horse battery staple")
    assert h.startswith("$argon2id$")
    assert S.verify_password("correct horse battery staple", h) is True
    assert S.verify_password("wrong", h) is False


def test_hash_password_is_salted_unique():
    a = S.hash_password("samepassword")
    b = S.hash_password("samepassword")
    assert a != b  # unique per-hash salt
    assert S.verify_password("samepassword", a) and S.verify_password("samepassword", b)


def test_fresh_argon2_does_not_need_rehash():
    assert S.needs_rehash(S.hash_password("pw")) is False


def test_argon2_params_meet_binding_spec():
    # §7: Argon2id, 64-256 MB, t>=3, p>=1.
    assert S.ARGON2_MEMORY_COST >= 64 * 1024 and S.ARGON2_MEMORY_COST <= 256 * 1024
    assert S.ARGON2_TIME_COST >= 3 and S.ARGON2_PARALLELISM >= 1
    h = S.hash_password("pw")
    assert f"m={S.ARGON2_MEMORY_COST}" in h and f"t={S.ARGON2_TIME_COST}" in h


# --------------------------------------------------------------------------- #
# Unit — legacy PBKDF2 back-compat
# --------------------------------------------------------------------------- #
def test_legacy_pbkdf2_verifies():
    legacy = _legacy_pbkdf2("hunter2")
    assert S.verify_password("hunter2", legacy) is True
    assert S.verify_password("nope", legacy) is False


def test_legacy_pbkdf2_needs_rehash():
    assert S.needs_rehash(_legacy_pbkdf2("hunter2")) is True


def test_empty_and_malformed_hash_reject():
    assert S.verify_password("x", "") is False
    assert S.verify_password("x", "not-a-hash") is False
    assert S.verify_password("x", "$argon2id$garbage") is False


def test_corrupted_legacy_hash_returns_false_never_raises():
    # A tampered/corrupted PBKDF2 hash with a non-positive iteration count must degrade to a
    # denied login (False), not raise ValueError out of verify_password into a 5xx (contract:
    # verify_password never raises). Reviewed finding, P6.
    assert S.verify_password("x", "pbkdf2_sha256$0$ab$ff") is False
    assert S.verify_password("x", "pbkdf2_sha256$-5$ab$ff") is False
    assert S.verify_password("x", "pbkdf2_sha256$notanint$ab$ff") is False
    assert S.verify_password("x", "pbkdf2_sha256$1000$nothex$ff") is False


def test_needs_rehash_is_total():
    # Mirrors verify_password's never-raise guarantee: empty/None -> True (treat as legacy).
    assert S.needs_rehash("") is True
    assert S.needs_rehash(None) is True  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Unit — pepper
# --------------------------------------------------------------------------- #
def test_pepper_round_trip_and_isolation():
    h = S.hash_password("pw", pepper="kms-pepper")
    assert S.verify_password("pw", h, pepper="kms-pepper") is True
    assert S.verify_password("pw", h, pepper="other-pepper") is False  # wrong pepper -> deny
    assert S.verify_password("pw", h) is False  # no pepper -> deny


def test_no_pepper_default_matches_unpeppered():
    h = S.hash_password("pw")
    assert S.verify_password("pw", h, pepper=None) is True


# --------------------------------------------------------------------------- #
# Unit — token_digest unchanged (high-entropy tokens stay on SHA-256)
# --------------------------------------------------------------------------- #
def test_token_digest_is_sha256():
    assert S.token_digest("abc") == hashlib.sha256(b"abc").hexdigest()


def test_recovery_codes_shape():
    codes = S.generate_recovery_codes(5)
    assert len(codes) == 5
    assert all(len(c) == 11 and c[5] == "-" for c in codes)


# --------------------------------------------------------------------------- #
# Integration — signup / login / reset
# --------------------------------------------------------------------------- #
def _app(tmp_path, **overrides):
    base = dict(
        database_url=f"sqlite:///{tmp_path / 'pwhash.sqlite3'}",
        api_key="test-key",
        require_verified_email=False,
    )
    base.update(overrides)
    app = create_app(Settings(**base))
    init_db(app.state.session_factory)
    return app


def _signup(client: TestClient, email: str, password: str = "password123") -> dict:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": password, "password_confirm": password},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _stored_hash(app, email: str) -> str:
    with session_scope(app.state.session_factory) as session:
        return session.query(UserORM).filter_by(email=email).one().password_hash


def test_signup_stores_argon2_hash(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "new@x.com")
        assert _stored_hash(app, "new@x.com").startswith("$argon2id$")


def test_login_rejects_wrong_password(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "u@x.com", "rightpass1")
        ok = client.post("/auth/login", json={"email": "u@x.com", "password": "rightpass1"})
        bad = client.post("/auth/login", json={"email": "u@x.com", "password": "wrongpass1"})
        assert ok.status_code == 200 and bad.status_code == 401


def test_legacy_hash_is_rehashed_to_argon2_on_login(tmp_path):
    """AC: a rehash-on-login path exists — a legacy PBKDF2 hash upgrades to Argon2id the first
    time the user signs in, without locking them out."""
    app = _app(tmp_path)
    sf = app.state.session_factory
    with session_scope(sf) as s:
        s.add(UserORM(email="leg@x.com", password_hash=_legacy_pbkdf2("legacypw1"),
                      is_active=True, is_verified=True))
    with TestClient(app) as client:
        res = client.post("/auth/login", json={"email": "leg@x.com", "password": "legacypw1"})
        assert res.status_code == 200  # not locked out
    assert _stored_hash(app, "leg@x.com").startswith("$argon2id$")  # upgraded in place


def test_password_reset_stores_argon2(tmp_path):
    """The reset path (set_user_password, behind /auth/reset-password) writes an Argon2id hash."""
    from nmrcheck.database import get_user_by_email, set_user_password

    app = _app(tmp_path)
    sf = app.state.session_factory
    with TestClient(app) as client:
        _signup(client, "reset@x.com", "oldpass123")
    uid = get_user_by_email(sf, "reset@x.com").id
    set_user_password(sf, user_id=uid, new_password="newpass456")
    assert _stored_hash(app, "reset@x.com").startswith("$argon2id$")
    assert authenticate_user(sf, email="reset@x.com", password="newpass456") is not None
    assert authenticate_user(sf, email="reset@x.com", password="oldpass123") is None


def test_pepper_configured_end_to_end(tmp_path):
    """With a pepper configured, signup -> login -> step works, and a legacy hash migrates to a
    peppered Argon2id hash on login."""
    app = _app(tmp_path, password_pepper="prod-kms-pepper")
    sf = app.state.session_factory
    with TestClient(app) as client:
        _signup(client, "pep@x.com", "pepperpw12")
        assert _stored_hash(app, "pep@x.com").startswith("$argon2id$")
        ok = client.post("/auth/login", json={"email": "pep@x.com", "password": "pepperpw12"})
        assert ok.status_code == 200
        # wrong password still rejected under pepper
        bad = client.post("/auth/login", json={"email": "pep@x.com", "password": "nope1234"})
        assert bad.status_code == 401
    # a legacy (un-peppered) hash still verifies and migrates to a peppered argon2 hash
    with session_scope(sf) as s:
        s.add(UserORM(email="legpep@x.com", password_hash=_legacy_pbkdf2("legacypw2"),
                      is_active=True, is_verified=True))
    assert authenticate_user(sf, email="legpep@x.com", password="legacypw2",
                             pepper="prod-kms-pepper") is not None
    new_hash = _stored_hash(app, "legpep@x.com")
    assert new_hash.startswith("$argon2id$")
    # the migrated hash is genuinely peppered: verifying without the pepper now fails
    assert S.verify_password("legacypw2", new_hash) is False
    assert S.verify_password("legacypw2", new_hash, pepper="prod-kms-pepper") is True
