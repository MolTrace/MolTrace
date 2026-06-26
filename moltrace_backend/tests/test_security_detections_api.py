"""SIEM detections end-to-end (Security Prompt 19) — the "reliably alert in staging
tests" acceptance criterion.

Drives the four required scenarios through the live app + admin endpoints:
  - impossible_travel: real login×2 from different X-Forwarded-For IPs → alert.
  - cross_tenant_access: a user probes N owner-denied dossier ids (404s) → alert.
  - privilege_escalation: a privilege_escalation event surfaces as an error alert.
  - audit_chain_break: a tampered audit row → critical alert, shipped to the sink.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.database import init_db
from nmrcheck.orm import AuditEventORM
from nmrcheck.settings import Settings

SYSTEM = {"x-api-key": "test-key"}  # system key is unrestricted → passes require_admin


def _app(tmp_path, **overrides):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'det.sqlite3'}",
        api_key="test-key",
        require_verified_email=False,
        rate_limit_trust_forwarded_for=True,  # honor X-Forwarded-For so login IP is the client
        **overrides,
    )
    app = create_app(settings)
    init_db(app.state.session_factory)
    return app


def _signup(client, email, password="password123"):
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": password, "password_confirm": password},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _alerts(client):
    res = client.get("/admin/security/alerts", headers=SYSTEM)
    assert res.status_code == 200, res.text
    return res.json()


def _detections_for(payload, detection):
    return [a for a in payload["alerts"] if a["detection"] == detection]


# --------------------------------------------------------------------------- scenarios


def test_impossible_travel_alerts_on_two_ips(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "traveler@acme.com")
        for ip in ("1.1.1.1", "9.9.9.9"):
            res = client.post(
                "/auth/login",
                json={"email": "traveler@acme.com", "password": "password123"},
                headers={"X-Forwarded-For": ip},
            )
            assert res.status_code == 200, res.text
        alerts = _detections_for(_alerts(client), "impossible_travel")
        assert len(alerts) == 1
        assert alerts[0]["actor_email"] == "traveler@acme.com"
        assert {alerts[0]["evidence"]["ip_a"], alerts[0]["evidence"]["ip_b"]} == {
            "1.1.1.1",
            "9.9.9.9",
        }


def test_same_ip_logins_do_not_alert(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        _signup(client, "homebody@acme.com")
        for _ in range(3):
            client.post(
                "/auth/login",
                json={"email": "homebody@acme.com", "password": "password123"},
                headers={"X-Forwarded-For": "5.5.5.5"},
            )
        assert _detections_for(_alerts(client), "impossible_travel") == []


def test_cross_tenant_probing_alerts(tmp_path):
    app = _app(tmp_path, cross_tenant_denied_threshold=5)
    with TestClient(app) as client:
        attacker = _signup(client, "snoop@acme.com")
        # Probe 6 dossier ids the user does not own (all non-leaking 404s).
        for did in range(900, 906):
            res = client.get(f"/regulatory/dossiers/{did}", headers=attacker)
            assert res.status_code == 404
        alerts = _detections_for(_alerts(client), "cross_tenant_access")
        assert len(alerts) == 1
        assert alerts[0]["actor_email"] == "snoop@acme.com"
        assert alerts[0]["evidence"]["peak_in_window"] >= 5


def test_privilege_escalation_alerts(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        # Seed a privilege_escalation event through the real ingest endpoint (the
        # login auto-grant seam emits the same event_type in production).
        res = client.post(
            "/security/events",
            headers=SYSTEM,
            json={
                "event_type": "privilege_escalation",
                "severity": "error",
                "actor_email": "boss@acme.com",
                "message": "User boss@acme.com was granted admin (admin_email_login).",
            },
        )
        assert res.status_code == 201, res.text
        alerts = _detections_for(_alerts(client), "privilege_escalation")
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "error"
        assert alerts[0]["actor_email"] == "boss@acme.com"


def test_audit_chain_break_alerts_and_ships(tmp_path, capsys):
    app = _app(tmp_path)
    with TestClient(app) as client:
        # Build a few audit-chain rows (each security event writes a paired audit event).
        for i in range(3):
            client.post(
                "/security/events",
                headers=SYSTEM,
                json={"event_type": "other", "message": f"seed {i}"},
            )
        # Tamper an interior chained audit row — breaks entry_hash recomputation.
        with app.state.session_factory() as session:
            row = (
                session.query(AuditEventORM)
                .filter(AuditEventORM.chain_seq.isnot(None))
                .order_by(AuditEventORM.chain_seq.asc())
                .first()
            )
            assert row is not None
            row.message = "tampered-after-the-fact"
            session.commit()

        capsys.readouterr()  # drop prior output
        res = client.post("/admin/security/detections/run", headers=SYSTEM)
        assert res.status_code == 200, res.text
        body = res.json()
        breaks = _detections_for(body, "audit_chain_break")
        assert len(breaks) == 1 and breaks[0]["severity"] == "critical"
        assert body["audit_chain_ok"] is False
        assert body["shipped"] >= 1  # critical alert pushed to the SIEM sink
        assert "siem_alert" in capsys.readouterr().out  # stdout sink fired


def test_alerts_endpoint_is_admin_only(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        user = _signup(client, "nonadmin@acme.com")
        assert client.get("/admin/security/alerts", headers=user).status_code == 403
        assert client.get("/admin/security/alerts").status_code == 401  # anonymous
