"""RFC 9116 ``security.txt`` — builder + route (Security Prompt 17).

Covers the pure body builder (mandatory Contact/Expires, in-window + computed
Expires, optional-field omission, multiple contacts, expires-day clamping, CRLF
framing) and the public ``/.well-known/security.txt`` route (200, text/plain,
anonymously reachable, disable→404).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from nmrcheck import wellknown
from nmrcheck.api import create_app
from nmrcheck.database import init_db
from nmrcheck.settings import Settings

_FIXED_NOW = datetime(2026, 6, 25, 12, 0, 0, tzinfo=UTC)


def _settings(**overrides) -> Settings:
    return Settings(database_url="sqlite://", api_key="k", **overrides)


def _app(tmp_path, **overrides):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'stxt.sqlite3'}",
        api_key="test-key",
        require_verified_email=False,
        **overrides,
    )
    app = create_app(settings)
    init_db(app.state.session_factory)
    return app


def _fields(body: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition(":")
        out.setdefault(name.strip(), []).append(value.strip())
    return out


# --------------------------------------------------------------------------- builder


def test_builder_emits_mandatory_contact_and_expires():
    body = wellknown.build_security_txt(_settings(), now=_FIXED_NOW)
    fields = _fields(body)
    assert fields["Contact"] == ["mailto:security@moltrace.co"]
    assert len(fields["Expires"]) == 1
    expires = datetime.strptime(fields["Expires"][0], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=UTC
    )
    # In the future and inside RFC 9116's one-year window.
    assert _FIXED_NOW < expires <= _FIXED_NOW + timedelta(days=366)


def test_builder_omits_unconfigured_optional_fields():
    body = wellknown.build_security_txt(_settings(), now=_FIXED_NOW)
    fields = _fields(body)
    # Defaults: no Policy/Canonical/Encryption/Acknowledgments (never advertise a 404).
    for name in ("Policy", "Canonical", "Encryption", "Acknowledgments"):
        assert name not in fields
    assert fields["Preferred-Languages"] == ["en"]


def test_builder_includes_configured_optional_fields_and_multiple_contacts():
    body = wellknown.build_security_txt(
        _settings(
            security_txt_contacts=(
                "https://github.com/example/MolTrace/security/advisories/new,"
                "mailto:security@moltrace.co"
            ),
            security_txt_policy_url="https://moltrace.co/security-policy",
            security_txt_canonical_url="https://moltrace.co/.well-known/security.txt",
        ),
        now=_FIXED_NOW,
    )
    fields = _fields(body)
    assert fields["Contact"][0].startswith("https://github.com/")
    assert fields["Contact"][1] == "mailto:security@moltrace.co"
    assert fields["Policy"] == ["https://moltrace.co/security-policy"]
    assert fields["Canonical"] == ["https://moltrace.co/.well-known/security.txt"]


def test_builder_clamps_out_of_window_expires_days():
    # >1yr is clamped back into the RFC window; <=0 is clamped up to a valid future date.
    too_far = wellknown.build_security_txt(
        _settings(security_txt_expires_days=100000), now=_FIXED_NOW
    )
    expires = datetime.strptime(
        _fields(too_far)["Expires"][0], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=UTC)
    assert expires <= _FIXED_NOW + timedelta(days=365)

    nonpos = wellknown.build_security_txt(
        _settings(security_txt_expires_days=0), now=_FIXED_NOW
    )
    expires2 = datetime.strptime(
        _fields(nonpos)["Expires"][0], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=UTC)
    assert expires2 > _FIXED_NOW


def test_builder_blank_contacts_falls_back_to_default():
    body = wellknown.build_security_txt(
        _settings(security_txt_contacts="  ,  "), now=_FIXED_NOW
    )
    assert _fields(body)["Contact"] == ["mailto:security@moltrace.co"]


def test_builder_uses_crlf_line_endings():
    body = wellknown.build_security_txt(_settings(), now=_FIXED_NOW)
    assert "\r\n" in body
    assert body.endswith("\r\n")


def test_builder_neutralizes_crlf_field_injection():
    # A CR/LF embedded in an operator value must NOT inject a forged *field line*
    # (e.g. a second, past-dated Expires, or an attacker-pointed Encryption). The
    # CR/LF is collapsed to a space, so the junk stays inside the one value's line.
    body = wellknown.build_security_txt(
        _settings(
            security_txt_contacts=(
                "mailto:a@b.co\r\nExpires: 1999-01-01T00:00:00Z\r\nContact: mailto:evil@x.co"
            ),
            security_txt_policy_url="https://moltrace.co/p\r\nEncryption: https://evil/key",
        ),
        now=_FIXED_NOW,
    )
    lines = body.split("\r\n")

    def _field_lines(name: str) -> list[str]:
        return [ln for ln in lines if ln.startswith(f"{name}:")]

    # Exactly one Expires line, and it is the real (future) one — not the forged 1999.
    assert len(_field_lines("Expires")) == 1
    assert "1999" not in _field_lines("Expires")[0]
    # The forged Encryption field never becomes its own line (we configured no Encryption).
    assert _field_lines("Encryption") == []
    # The mangled value collapses onto a single Contact / Policy line (no new lines spawned).
    assert len(_field_lines("Contact")) == 1
    assert len(_field_lines("Policy")) == 1


# --------------------------------------------------------------------------- route


def test_security_txt_route_served_publicly(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        res = client.get("/.well-known/security.txt")  # no auth header
        assert res.status_code == 200, res.text
        assert res.headers["content-type"] == "text/plain; charset=utf-8"
        fields = _fields(res.text)
        assert "Contact" in fields and "Expires" in fields


def test_security_txt_route_can_be_disabled(tmp_path):
    app = _app(tmp_path, security_txt_enabled=False)
    with TestClient(app) as client:
        assert client.get("/.well-known/security.txt").status_code == 404
