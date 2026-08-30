"""A 401 or 403 says the same thing to every caller, and says it in ``code``.

The browser never sees a backend ``detail`` on these two statuses — the ``/api/backend``
proxy replaces it in every case. A desktop client talks to the API directly and inherits
none of that, so the confidentiality control has to live on the server or it does not exist.

These pin that it does. Four handlers can emit a 401/403 and three of them used to return the
raiser's prose verbatim; the fourth, SCIM, still does **on purpose** and T5 pins that carve-out
so the next reader of "every handler" does not close it.

The rule these encode: on a 401/403 the cause of the refusal *is* the thing being protected,
so it goes to the operator log with the correlation id and the caller gets a situation code.
That is the deliberate opposite of the house rule that a rejection names its cause — which is a
rule about scientific bounds, where the caller is entitled to know why their data was refused.
"""

from __future__ import annotations

import base64
import types
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pyotp
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from nmrcheck import error_codes, mfa_webauthn
from nmrcheck.api import (
    PUBLIC_ACCESS_DENIED_DETAIL,
    PUBLIC_AUTH_REQUIRED_DETAIL,
    create_app,
)
from nmrcheck.database import init_db
from nmrcheck.orm import OrganizationORM, TeamMemberORM
from nmrcheck.settings import Settings

#: The only two sentences a sanitized 401/403 may carry.
GENERIC = {401: PUBLIC_AUTH_REQUIRED_DETAIL, 403: PUBLIC_ACCESS_DENIED_DETAIL}

ADMIN_EMAIL = "admin@example.com"


def _app(tmp_path, name: str = "codes", **overrides):
    base = dict(
        database_url=f"sqlite:///{tmp_path / f'{name}.sqlite3'}",
        api_key="test-key",
        require_verified_email=False,
        admin_emails=(ADMIN_EMAIL,),
        mfa_encryption_key="unit-test-mfa-key",
        webauthn_rp_id="localhost",
        webauthn_rp_name="MolTrace",
        webauthn_origin="http://localhost:3000",
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
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _make_org(app, name: str, member_email: str | None = None) -> int:
    with app.state.session_factory() as s:
        org = OrganizationORM(name=name)
        s.add(org)
        s.commit()
        s.refresh(org)
        oid = org.id
        if member_email:
            s.add(
                TeamMemberORM(
                    organization_id=oid,
                    user_email=member_email.strip().lower(),
                    role="viewer",
                    status="active",
                )
            )
            s.commit()
        return oid


def _set_policy(client: TestClient, org_id: int, *, required: bool, grace: int = 0):
    res = client.put(
        f"/admin/mfa/policy/{org_id}",
        headers={"x-api-key": "test-key"},
        json={
            "mfa_required": required,
            "grace_period_days": grace,
            "allowed_factors": ["webauthn", "totp"],
            "enforce_for_sso": False,
            "require_step_up_for_signing": True,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _assertion(cred_id: bytes) -> dict:
    rid = _b64(cred_id)
    return {"id": rid, "rawId": rid, "type": "public-key", "response": {}}


def _install_fake_authenticator(monkeypatch, *, cred_id=b"passkey-1") -> bytes:
    """A synthetic authenticator whose sign counter advances, so the stored counter is
    non-zero by the time the clone attempt is made. Without that the clone branch at
    ``mfa_webauthn`` is never reached and T3 would assert an absence on an unreached path —
    green by construction, forever."""
    counter = {"n": 0}

    def fake_reg(credential, *, expected_challenge, settings):
        return types.SimpleNamespace(
            credential_id=cred_id,
            credential_public_key=b"cose-public-key",
            sign_count=0,
            aaguid="00000000-0000-0000-0000-000000000000",
            credential_device_type="multi_device",
            credential_backed_up=True,
            user_verified=True,
        )

    def fake_auth(credential, *, expected_challenge, public_key, current_sign_count, settings):
        counter["n"] += 1
        return types.SimpleNamespace(
            credential_id=cred_id,
            new_sign_count=current_sign_count + counter["n"],
            credential_device_type="multi_device",
            credential_backed_up=True,
            user_verified=True,
        )

    monkeypatch.setattr(mfa_webauthn, "verify_registration", fake_reg)
    monkeypatch.setattr(mfa_webauthn, "verify_authentication", fake_auth)
    return cred_id


def _password_step_up(client: TestClient, bearer: dict, password: str = "password123"):
    res = client.post("/auth/step-up/password", headers=bearer, json={"password": password})
    assert res.status_code == 200, res.text
    return res.json()


def _fresh_totp(secret: str) -> str:
    return pyotp.TOTP(secret).at(datetime.now(UTC) + timedelta(seconds=30))


def _enroll_totp(client: TestClient, bearer: dict) -> tuple[str, list[str]]:
    _password_step_up(client, bearer)
    enroll = client.post("/auth/mfa/totp/enroll", headers=bearer)
    assert enroll.status_code == 200, enroll.text
    secret = parse_qs(urlparse(enroll.json()["otpauth_uri"]).query)["secret"][0]
    confirm = client.post(
        "/auth/mfa/totp/confirm", headers=bearer, json={"code": pyotp.TOTP(secret).now()}
    )
    assert confirm.status_code == 200, confirm.text
    return secret, confirm.json()["recovery_codes"]


def _assert_sanitized(res, *, where: str) -> str:
    """Every property §3.2 fixes, asserted in one place so each test names only its own point."""
    body = res.json()
    assert res.status_code in (401, 403), f"{where}: expected 401/403, got {res.status_code}"
    assert set(body) == {"code", "detail"}, f"{where}: extra keys on the wire: {sorted(body)}"
    assert body["code"] in error_codes.SANITIZED_AUTH_CODES, f"{where}: unregistered {body['code']!r}"
    assert body["detail"] == GENERIC[res.status_code], f"{where}: leaked detail {body['detail']!r}"
    return body["code"]


# --------------------------------------------------------------------------------------- T1
def test_every_401_and_403_carries_a_registered_code(tmp_path) -> None:
    """The field is never absent and never a value outside the registry, on any route.

    Swept rather than sampled: a client that must handle "sometimes there is a code" has
    gained nothing over parsing prose, and the guarantee is only worth as much as its
    weakest route.
    """
    app = _app(tmp_path, "sweep")
    swept = 0
    with TestClient(app, raise_server_exceptions=False) as client:
        for route in app.routes:
            if not isinstance(route, APIRoute) or "GET" not in route.methods:
                continue
            if "{" in route.path or route.path.startswith("/scim"):
                continue  # SCIM keeps its own envelope by design (T5)
            res = client.get(route.path)
            if res.status_code not in (401, 403):
                continue
            _assert_sanitized(res, where=route.path)
            swept += 1
    assert swept > 50, f"the sweep only reached {swept} denials — it is not measuring anything"


# --------------------------------------------------------------------------------------- T2
def test_mfa_error_detail_never_reaches_the_wire(tmp_path) -> None:
    """B1a-B1i: every MFAError at 401/403 is replaced by one of the two fixed sentences.

    ``mfa_error_handler`` returned ``exc.detail`` verbatim, so "Invalid authentication code."
    and "Incorrect password." were on the wire for any direct caller.
    """
    app = _app(tmp_path, "mfa")
    with TestClient(app) as client:
        bearer = _signup(client, "mfa@acme.com")

        # B1g "Incorrect password." — a wrong password at step-up.
        wrong_pw = client.post(
            "/auth/step-up/password", headers=bearer, json={"password": "not-the-password"}
        )
        assert _assert_sanitized(wrong_pw, where="step-up/password") == (
            error_codes.MFA_FACTOR_INVALID
        )

        # B1c "Invalid authentication code." — a wrong TOTP at step-up.
        _enroll_totp(client, bearer)
        wrong_totp = client.post("/auth/step-up/totp", headers=bearer, json={"code": "000000"})
        assert _assert_sanitized(wrong_totp, where="step-up/totp") == (
            error_codes.MFA_FACTOR_INVALID
        )

    # B1e "No active session to step up." — reuses token_invalid rather than minting a code:
    # it means the bearer is not a live session, which is exactly what token_invalid says.
    app2 = _app(tmp_path, "mfa2")
    with TestClient(app2) as client:
        _signup(client, "ghost@acme.com")
        orphan = client.post(
            "/auth/step-up/password",
            headers={"Authorization": "Bearer not-a-real-session"},
            json={"password": "password123"},
        )
        _assert_sanitized(orphan, where="step-up with a dead bearer")


# --------------------------------------------------------------------------------------- T3
def test_clone_detection_is_not_disclosed(tmp_path, monkeypatch) -> None:
    """B1i, the sharpest case.

    "Passkey clone/replay detected (sign count did not advance)." told the holder of a cloned
    credential that the clone was caught and named the detector that caught it. The refusal
    still happens; only the disclosure goes. The person who OWNS the credential is told
    through the audit chain and the account's notification path — which reaches the owner,
    not whoever is holding the copy.

    Driven through the same synthetic-authenticator seam ``test_webauthn_step_up_and_clone_detection``
    uses, and it must stay that way: a successful step-up first advances the stored counter, so
    the non-advancing assertion afterwards actually reaches the clone branch. Written standalone
    without that first step-up, the stored counter is 0, the branch is never entered, and an
    absence assertion passes vacuously.
    """
    app = _app(tmp_path, "clone")
    cred_id = _install_fake_authenticator(monkeypatch)
    with TestClient(app) as client:
        bearer = _signup(client, "clone@acme.com")
        _password_step_up(client, bearer)
        client.post("/auth/mfa/webauthn/register/options", headers=bearer)
        reg = client.post(
            "/auth/mfa/webauthn/register/verify",
            headers=bearer,
            json={"credential": _assertion(cred_id), "nickname": "K"},
        )
        assert reg.status_code == 200, reg.text

        # A genuine step-up first — this is what leaves a non-zero sign counter behind.
        client.post("/auth/step-up/options", headers=bearer)
        up = client.post(
            "/auth/step-up/webauthn", headers=bearer, json={"assertion": _assertion(cred_id)}
        )
        assert up.status_code == 200 and up.json()["aal"] == "aal2", up.text

        # The clone: the counter does not advance.
        monkeypatch.setattr(
            mfa_webauthn,
            "verify_authentication",
            lambda credential, **kw: types.SimpleNamespace(
                credential_id=cred_id,
                new_sign_count=0,
                credential_device_type="multi_device",
                credential_backed_up=True,
                user_verified=True,
            ),
        )
        client.post("/auth/step-up/options", headers=bearer)
        cloned = client.post(
            "/auth/step-up/webauthn", headers=bearer, json={"assertion": _assertion(cred_id)}
        )

        assert cloned.status_code == 401, cloned.text  # still refused — only the telling goes
        assert _assert_sanitized(cloned, where="cloned passkey") == error_codes.MFA_FACTOR_INVALID
        # The detector's whole vocabulary, not just the sentence: a reworded disclosure is
        # still a disclosure.
        raw = cloned.text.lower()
        for word in ("clone", "replay", "sign count", "sign_count"):
            assert word not in raw, f"the clone detector is disclosed via {word!r}: {cloned.text}"


# --------------------------------------------------------------------------------------- T4
def test_session_error_detail_is_sanitized(tmp_path) -> None:
    """B2, and the property that made it benign only by accident.

    ``session_error_handler`` returned ``exc.detail`` verbatim. That was harmless only because
    every SessionError happens to carry a registered public code today; a future one with prose
    would have leaked silently. The machine signal survives — as ``code``, which is where it
    belongs — while ``detail`` becomes the fixed sentence.
    """
    app = _app(tmp_path, "sess")
    with TestClient(app) as client:
        _signup(client, "sess@acme.com")
        login = client.post(
            "/auth/login", json={"email": "sess@acme.com", "password": "password123"}
        )
        assert login.status_code == 200, login.text
        refresh_token = login.json()["refresh_token"]

        rotated = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert rotated.status_code == 200, rotated.text

        # Replaying the spent token is reuse: the family is revoked and the caller is told
        # *as a code*, not as prose.
        replay = client.post("/auth/refresh", json={"refresh_token": refresh_token})
        assert _assert_sanitized(replay, where="refresh reuse") == error_codes.TOKEN_REUSE_DETECTED


# --------------------------------------------------------------------------------------- T5
def test_scim_error_envelope_is_preserved(tmp_path) -> None:
    """The SCIM carve-out is deliberate. Do not close it.

    Okta and Entra parse the SCIM ``Error`` envelope; rendering these as the MolTrace shape
    breaks provisioning for every customer using enterprise SSO. This test exists because
    "every handler is sanitized" is the natural reading of the rule T1-T4 encode, and the next
    person to apply it uniformly would take this with it.
    """
    app = _app(tmp_path, "scim")
    with TestClient(app) as client:
        res = client.get("/scim/v2/Users", headers={"Authorization": "Bearer scim_garbage"})

        assert res.status_code == 401
        body = res.json()
        assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
        assert body["status"] == "401"
        assert res.headers["content-type"].startswith("application/scim+json")
        assert res.headers.get("WWW-Authenticate") == "Bearer"
        # Explicitly NOT the MolTrace shape — this is the assertion that fails if someone
        # routes SCIM through the sanitizer.
        assert "code" not in body


# --------------------------------------------------------------------------------------- T6
def test_feature_flag_name_is_not_in_any_body(tmp_path) -> None:
    """B4. An environment-variable name is deployment configuration, not a product concept.

    It is backend jargon in a position a person reads — ``web.py`` renders a 403 ``detail``
    straight into the page it serves — so it goes in **no body and no header**. The client
    that needs to react gets ``feature_not_enabled``; the operator who needs the name gets it
    from the log with the correlation id.

    Scoped to 401/403 on purpose: ``nmr2d_routes`` also refuses with a 404 carrying the phrase
    "feature flag" (no variable name), which this delta does not sanitize. Matching the phrase
    rather than the names would go red on that out-of-scope 404 — a guard that fails for a
    reason other than the one it claims.
    """
    app = _app(tmp_path, "flags", enable_2d_nmr=True, enable_raw_2d_fid_beta=False)
    with TestClient(app) as client:
        bearer = _signup(client, "flag@acme.com")
        res = client.post("/nmr2d/raw/preview", headers=bearer, json={})

        assert res.status_code == 403, res.text
        assert _assert_sanitized(res, where="raw 2D beta") == error_codes.FEATURE_NOT_ENABLED
        for name in ("ENABLE_RAW_2D_FID_BETA", "ENABLE_2D_CONTOUR_PREVIEW"):
            assert name not in res.text, f"{name} is in the response body"
            for header, value in res.headers.items():
                assert name not in value, f"{name} is in the {header} header"


# --------------------------------------------------------------------------------------- T7
def test_mfa_enrollment_required_is_distinguishable_from_step_up(tmp_path) -> None:
    """C1's regression guard.

    ``mfa_satisfied_for_session`` returns two values — "step up with the factor you have" and
    "enrol a first factor" — which need different screens. With ``detail`` fixed to one
    sentence, ``code`` is the only carrier left, so an unregistered value collapses both to
    ``forbidden`` and the client cannot tell them apart. The handoff registered one of the two
    and pinned the vocabulary at 13; it is 14.
    """
    app = _app(tmp_path, "c1")
    with TestClient(app) as client:
        no_factor = _signup(client, "nofactor@acme.com")
        _make_org(app, "Acme", "nofactor@acme.com")
        _set_policy(client, _make_org_lookup(app, "Acme"), required=True, grace=0)

        blocked = client.get("/esignatures/records", headers=no_factor)
        enrolment_code = _assert_sanitized(blocked, where="no factor enrolled")
        assert enrolment_code == error_codes.MFA_ENROLLMENT_REQUIRED
        # C1's own evidence that this is not a lockout: the enrolment surface stays reachable.
        assert client.get("/auth/mfa/status", headers=no_factor).status_code == 200

    app2 = _app(tmp_path, "c1b")
    with TestClient(app2) as client:
        has_factor = _signup(client, "hasfactor@acme.com")
        _enroll_totp(client, has_factor)
        _make_org(app2, "Acme", "hasfactor@acme.com")
        _set_policy(client, _make_org_lookup(app2, "Acme"), required=True, grace=0)

        # A user WITH a factor whose session has not stepped up is a different situation.
        stale = client.get("/esignatures/records", headers=has_factor)
        if stale.status_code in (401, 403):
            step_up_code = _assert_sanitized(stale, where="factor enrolled, not stepped up")
            assert step_up_code != enrolment_code, (
                "enrol-a-factor and step-up collapsed to the same code, which is the whole "
                "failure C1 describes"
            )


def _make_org_lookup(app, name: str) -> int:
    from sqlalchemy import select

    with app.state.session_factory() as s:
        return s.execute(
            select(OrganizationORM.id).where(OrganizationORM.name == name)
        ).scalar_one()


# --------------------------------------------------------------------------------------- T8
def test_an_unregistered_code_fails_closed(tmp_path) -> None:
    """§3.3: an unrecognised code is replaced by the status fallback, never forwarded.

    Fail-closed is asymmetric on purpose. Adding a public code without updating a mirror
    degrades a client to a generic denial, which is the acceptable direction; a mirror
    forwarding something the backend never marked public is impossible by construction,
    because every mirror is an allowlist and never a denylist.
    """
    from nmrcheck.api import CodedHTTPException, _sanitized_auth_body

    # A route inventing a code that names a resource is the exact failure this prevents —
    # "mfa_required" was this, unregistered, on the wire, until it was registered.
    assert _sanitized_auth_body(403, "owner_of_dossier_7")["code"] == error_codes.FORBIDDEN
    assert _sanitized_auth_body(401, "some_new_idea")["code"] == error_codes.UNAUTHENTICATED
    # A registered but NON-public code is not public just because a raise site stated it.
    assert (
        _sanitized_auth_body(403, error_codes.UNKNOWN_PROCESSING_PRESET)["code"]
        == error_codes.FORBIDDEN
    )
    # A registered public code survives.
    assert (
        _sanitized_auth_body(403, error_codes.MODULE_NOT_LICENSED)["code"]
        == error_codes.MODULE_NOT_LICENSED
    )
    # And the field is never absent, whatever arrives.
    for detail in (None, 42, {"nested": "object"}, ""):
        for status_code in (401, 403):
            body = _sanitized_auth_body(status_code, detail)
            assert body["code"] in error_codes.SANITIZED_AUTH_CODES
            assert body["detail"] == GENERIC[status_code]

    assert CodedHTTPException(403, "prose", code="not_a_registered_code").error_code == (
        "not_a_registered_code"
    )
    assert _sanitized_auth_body(403, "prose", stated_code="not_a_registered_code")["code"] == (
        error_codes.FORBIDDEN
    )


# --------------------------------------------------------------------------------------- T9
def test_starlette_404_still_carries_a_code(tmp_path) -> None:
    """The parent-class registration must survive.

    An unmatched route raises Starlette's HTTPException, the PARENT of FastAPI's, so a handler
    registered only on the subclass never sees it — leaving plain 404s with no code, which the
    source comment records as the one gap a client would hit first.
    """
    app = _app(tmp_path, "notfound")
    with TestClient(app, raise_server_exceptions=False) as client:
        body = client.get("/no-such-route-anywhere").json()
        assert body["code"] == error_codes.NOT_FOUND


# --------------------------------------------------------------------------------------- T10
def test_500_path_is_untouched(tmp_path) -> None:
    """The >=500 branch keeps its stable payload and UNAVAILABLE code.

    Out of scope and must stay that way: this delta is 401/403 only. A 5xx keeps the
    data_mode/warnings shape the interface's unavailable states are built on.
    """
    from nmrcheck.api import _stable_unavailable_payload

    payload = _stable_unavailable_payload()
    assert payload["data_mode"] == "unavailable"
    assert payload["warnings"] and isinstance(payload["warnings"], list)
    assert error_codes.code_for(500, "boom") == error_codes.UNAVAILABLE
    assert error_codes.code_for(503, None) == error_codes.UNAVAILABLE
