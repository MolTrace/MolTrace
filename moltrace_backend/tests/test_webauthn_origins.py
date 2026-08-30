"""Multi-origin WebAuthn verification: one ``rp_id``, several EXACT origins.

Phishing resistance in :mod:`nmrcheck.mfa_webauthn` comes from the server always supplying the
expected ``rp_id`` and origin from settings. This suite widens the origin side to a configured set
and pins the property that makes the widening safe: **whole-string equality, never a pattern.**

Unlike ``test_mfa.py`` — which substitutes py_webauthn's verify functions with a synthetic
authenticator and so never exercises origin checking at all — these tests mint **real ES256
credentials** and sign genuine ``clientDataJSON`` carrying the origin under test. The verifier's
decision here is the real one, so a weakening of the match (a prefix, a suffix, a wildcard) shows
up as a test going green when it should be red.
"""

from __future__ import annotations

import base64
import hashlib
import json

import cbor2
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers.exceptions import InvalidAuthenticationResponse

from nmrcheck import mfa_webauthn
from nmrcheck.settings import (
    Settings,
    validate_startup_settings,
    webauthn_accepted_origins,
)

PRIMARY = "https://app.moltrace.co"
DESKTOP = "https://desk.moltrace.co"
RP_ID = "moltrace.co"
CHALLENGE = b"\x07" * 32
CRED_ID = b"passkey-origin-suite"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _settings(
    *,
    additional: tuple[str, ...] = (),
    app_env: str = "development",
    database_url: str | None = None,
) -> Settings:
    return Settings(
        app_env=app_env,
        **({"database_url": database_url} if database_url else {}),
        webauthn_rp_id=RP_ID,
        webauthn_rp_name="MolTrace",
        webauthn_origin=PRIMARY,
        webauthn_additional_origins=additional,
    )


def _cose_es256(public_key: ec.EllipticCurvePublicKey) -> bytes:
    """The credential public key in the COSE_Key form an authenticator would have returned."""
    numbers = public_key.public_numbers()
    return cbor2.dumps(
        {
            1: 2,  # kty: EC2
            3: -7,  # alg: ES256
            -1: 1,  # crv: P-256
            -2: numbers.x.to_bytes(32, "big"),
            -3: numbers.y.to_bytes(32, "big"),
        }
    )


def _signed_assertion(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    origin: str,
    rp_id: str = RP_ID,
    sign_count: int = 7,
) -> dict:
    """A genuinely signed assertion whose clientDataJSON claims ``origin``.

    This is what an authenticator at ``origin`` would actually produce, so a verifier that accepts
    it has accepted that origin — there is no seam here to mock the decision away.
    """
    client_data = json.dumps(
        {
            "type": "webauthn.get",
            "challenge": _b64(CHALLENGE),
            "origin": origin,
            "crossOrigin": False,
        },
        separators=(",", ":"),
    ).encode()
    # rpIdHash ‖ flags (user present + user verified) ‖ signCount
    authenticator_data = (
        hashlib.sha256(rp_id.encode()).digest()
        + bytes([0x01 | 0x04])
        + sign_count.to_bytes(4, "big")
    )
    signature = private_key.sign(
        authenticator_data + hashlib.sha256(client_data).digest(),
        ec.ECDSA(hashes.SHA256()),
    )
    return {
        "id": _b64(CRED_ID),
        "rawId": _b64(CRED_ID),
        "type": "public-key",
        "response": {
            "clientDataJSON": _b64(client_data),
            "authenticatorData": _b64(authenticator_data),
            "signature": _b64(signature),
            "userHandle": _b64(b"moltrace-user-1"),
        },
    }


@pytest.fixture
def keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, _cose_es256(private_key.public_key())


def _verify(settings: Settings, credential: dict, cose_key: bytes):
    return mfa_webauthn.verify_authentication(
        credential,
        expected_challenge=CHALLENGE,
        public_key=cose_key,
        current_sign_count=0,
        settings=settings,
    )


# --------------------------------------------------------------------------------- T1
def test_additional_origin_is_accepted(keypair):
    """An assertion from a configured additional origin verifies."""
    private_key, cose_key = keypair
    settings = _settings(additional=(DESKTOP,))
    verified = _verify(settings, _signed_assertion(private_key, origin=DESKTOP), cose_key)
    assert verified.new_sign_count == 7
    # ...and the primary keeps working alongside it.
    assert _verify(settings, _signed_assertion(private_key, origin=PRIMARY), cose_key)


# --------------------------------------------------------------------------------- T2
def test_lookalike_origin_is_refused(keypair):
    """THE test for the exact-match rule. A suffix match on ``moltrace.co`` accepts ``evil-moltrace.co``; a prefix
    match on ``https://app.moltrace.co`` accepts ``https://app.moltrace.co.attacker.test``. Both
    are registrable domains an attacker can buy. Only whole-string equality refuses both."""
    private_key, cose_key = keypair
    settings = _settings(additional=(DESKTOP,))

    # The configured origin is allowed — establishes that the harness can produce a passing case,
    # so the refusals below are refusals of the origin and not of the signature.
    assert _verify(settings, _signed_assertion(private_key, origin=PRIMARY), cose_key)

    for lookalike in (
        "https://evil-moltrace.co",  # suffix match would accept this
        "https://app.moltrace.co.attacker.test",  # prefix match would accept this
        "https://moltrace.co.evil.test",
        "https://notapp.moltrace.co",
        "https://desk.moltrace.co.attacker.test",
    ):
        with pytest.raises(InvalidAuthenticationResponse):
            _verify(settings, _signed_assertion(private_key, origin=lookalike), cose_key)


# --------------------------------------------------------------------------------- T3
def test_null_origin_is_never_accepted(keypair):
    """Every opaque origin serialises as ``"null"``, so one such entry would accept all of them.
    It must be refused even when an operator explicitly configures it."""
    private_key, cose_key = keypair
    settings = _settings(additional=("null", DESKTOP))

    assert "null" not in webauthn_accepted_origins(settings)
    with pytest.raises(InvalidAuthenticationResponse):
        _verify(settings, _signed_assertion(private_key, origin="null"), cose_key)
    # The legitimate neighbour in the same list is unaffected by the refusal of "null".
    assert _verify(settings, _signed_assertion(private_key, origin=DESKTOP), cose_key)


# --------------------------------------------------------------------------------- T4
def test_scheme_and_port_are_part_of_the_match(keypair):
    """An origin is scheme + host + port. Downgrading any of the three is a different origin."""
    private_key, cose_key = keypair
    settings = _settings(additional=("https://lab.moltrace.co:8443",))

    assert _verify(
        settings, _signed_assertion(private_key, origin="https://lab.moltrace.co:8443"), cose_key
    )
    for wrong in (
        "http://lab.moltrace.co:8443",  # scheme downgraded
        "https://lab.moltrace.co",  # port dropped
        "https://lab.moltrace.co:8444",  # port changed
        "http://app.moltrace.co",  # the primary, downgraded to plaintext
    ):
        with pytest.raises(InvalidAuthenticationResponse):
            _verify(settings, _signed_assertion(private_key, origin=wrong), cose_key)


# --------------------------------------------------------------------------------- T5
def test_empty_allowlist_is_todays_behaviour(keypair, monkeypatch):
    """An unconfigured deployment must upgrade to no change at all — including the single string
    handed to py_webauthn, so even the refusal message is the one it produces today."""
    private_key, cose_key = keypair
    settings = _settings()
    assert settings.webauthn_additional_origins == ()

    seen: dict = {}

    def spy(**kwargs):
        seen.update(kwargs)
        raise AssertionError("stop after capture")

    monkeypatch.setattr(mfa_webauthn, "verify_authentication_response", spy)
    with pytest.raises(AssertionError):
        _verify(settings, _signed_assertion(private_key, origin=PRIMARY), cose_key)

    assert seen["expected_origin"] == PRIMARY
    assert isinstance(seen["expected_origin"], str)
    assert seen["expected_rp_id"] == RP_ID

    monkeypatch.undo()
    assert _verify(settings, _signed_assertion(private_key, origin=PRIMARY), cose_key)
    with pytest.raises(InvalidAuthenticationResponse):
        _verify(settings, _signed_assertion(private_key, origin=DESKTOP), cose_key)


# --------------------------------------------------------------------------------- T6
def test_production_refuses_a_loopback_or_insecure_origin(tmp_path):
    """An allowlist is a standing invitation to add localhost and ship it. Production says no, and
    says which value it is objecting to — a startup failure that does not name the offending value
    reappears later as an unexplained authentication failure."""
    for offender in ("http://localhost:3000", "http://127.0.0.1:8000", "http://[::1]:3000"):
        issues = validate_startup_settings(
            _settings(additional=(offender,), app_env="production")
        )
        assert any(offender in issue for issue in issues), (offender, issues)

    # "null" is refused in every environment, not only production.
    assert any("null" in issue for issue in validate_startup_settings(_settings(additional=("null",))))

    # A well-formed HTTPS origin is not objected to.
    assert not [
        issue
        for issue in validate_startup_settings(
            _settings(additional=(DESKTOP,), app_env="production")
        )
        if "WEBAUTHN" in issue
    ]

    # And "refuses" means refuses: startup issues are otherwise only logged, so this one class is
    # additionally fatal in production. Without this, the guard would report a phishing hole and
    # then serve traffic through it.
    from nmrcheck.api import create_app

    with pytest.raises(RuntimeError, match="localhost"):
        create_app(
            _settings(
                additional=("http://localhost:3000",),
                app_env="production",
                database_url=f"sqlite:///{tmp_path / 'refused.sqlite3'}",
            )
        )
    # A safe allowlist still starts — the refusal is aimed at the offending value, not the feature.
    assert create_app(
        _settings(
            additional=(DESKTOP,),
            app_env="production",
            database_url=f"sqlite:///{tmp_path / 'accepted.sqlite3'}",
        )
    )


# --------------------------------------------------------------------------------- T7
def test_options_generation_still_uses_a_single_rp_id(tmp_path, monkeypatch):
    """Verification widens, options generation does not. Varying rp_id per ceremony would
    mint credentials that cannot verify against each other — a failure that surfaces months later
    as "my key stopped working".

    This has to cover **all three** options-generating call sites, not just the convenient one.
    Both authentication paths refuse early when the user has no passkey, so a version of this test
    that skips enrolment reaches only ``begin_registration`` and would stay green while the
    step-up path — the one this delta exists to serve — was quietly widened.
    """
    from sqlalchemy.orm import Session

    from nmrcheck.database import create_session_factory, init_db
    from nmrcheck.orm import MFAWebAuthnChallengeORM, MFAWebAuthnCredentialORM, UserORM

    settings = _settings(additional=(DESKTOP, "https://lab.moltrace.co:8443"))
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'origins.sqlite3'}")
    init_db(session_factory)
    session: Session = session_factory()
    user = UserORM(email="keys@example.com", password_hash="x")
    session.add(user)
    session.commit()
    user_id = user.id
    # Enrolled, so begin_authentication_options and make_login_authentication_options both get
    # past their "No passkey registered" guard and actually mint options.
    session.add(
        MFAWebAuthnCredentialORM(
            user_id=user_id, credential_id=CRED_ID, public_key=b"cose", sign_count=0
        )
    )
    session.commit()
    session.close()

    minted: dict[str, list[dict]] = {"registration": [], "authentication": []}
    real_registration = mfa_webauthn.generate_registration_options
    real_authentication = mfa_webauthn.generate_authentication_options

    def spy_registration(**kwargs):
        minted["registration"].append(kwargs)
        return real_registration(**kwargs)

    def spy_authentication(**kwargs):
        minted["authentication"].append(kwargs)
        return real_authentication(**kwargs)

    monkeypatch.setattr(mfa_webauthn, "generate_registration_options", spy_registration)
    monkeypatch.setattr(mfa_webauthn, "generate_authentication_options", spy_authentication)

    with session_factory() as read_session:
        mfa_webauthn.begin_registration(
            session_factory, user=read_session.get(UserORM, user_id), settings=settings
        )
    mfa_webauthn.begin_authentication_options(  # the step-up path
        session_factory, user_id=user_id, purpose="step_up", settings=settings
    )
    assert mfa_webauthn.make_login_authentication_options(  # the login path
        session_factory, user_id=user_id, settings=settings
    ) is not None

    # One registration site and BOTH authentication sites were reached.
    assert len(minted["registration"]) == 1, minted
    assert len(minted["authentication"]) == 2, minted
    for kwargs in minted["registration"] + minted["authentication"]:
        assert kwargs["rp_id"] == RP_ID
        assert isinstance(kwargs["rp_id"], str)
        # Nothing origin-shaped may reach an options generator.
        assert not any("origin" in key for key in kwargs)

    # The persisted challenge rows carry that same single rp_id — a widened value here would
    # diverge silently from what the credential was minted against.
    with session_factory() as read_session:
        rows = read_session.query(MFAWebAuthnChallengeORM).all()
        assert {row.rp_id for row in rows} == {RP_ID}


# --------------------------------------------------------------------------------- T8
def test_step_up_still_raises_its_own_code(tmp_path):
    """``step_up_required`` is how the SPA tells "step up" apart from "log in again". A widened
    origin set must not disturb it."""
    from fastapi.testclient import TestClient

    from nmrcheck.api import create_app
    from nmrcheck.database import init_db

    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'stepup.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            mfa_encryption_key="unit-test-mfa-key",
            webauthn_rp_id=RP_ID,
            webauthn_rp_name="MolTrace",
            webauthn_origin=PRIMARY,
            webauthn_additional_origins=(DESKTOP,),
        )
    )
    init_db(app.state.session_factory)
    with TestClient(app) as client:
        res = client.post(
            "/auth/sign-up",
            json={
                "email": "stepup@example.com",
                "password": "password123",
                "password_confirm": "password123",
            },
        )
        assert res.status_code == 201, res.text
        bearer = {"Authorization": f"Bearer {res.json()['access_token']}"}
        blocked = client.post("/auth/mfa/webauthn/register/options", headers=bearer)
        assert blocked.status_code == 401
        # Re-baselined on merge: `detail` on a 401/403 is now one of two fixed sentences, and
        # the machine code travels in `code`. This assertion was written on a branch that had
        # not seen that change, so it is the fifteenth reader of the old shape — the fourteen
        # found earlier were all that existed in the tree at the time.
        assert blocked.json()["code"] == "step_up_required"
