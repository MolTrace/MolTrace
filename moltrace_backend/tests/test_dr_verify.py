"""DR restore-integrity verifier (Security Prompt 21).

Tests the pure `assess` decision + the `verify_restore` path against a real seeded
database (clean → verified) and a tampered one (audit-chain break → fails) — the
"verified for integrity" DR acceptance check.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck import dr_verify
from nmrcheck.api import create_app
from nmrcheck.database import init_db
from nmrcheck.models import AuditChainVerification
from nmrcheck.orm import AuditEventORM
from nmrcheck.settings import Settings


def _verif(*, ok=True, total=5, key_id="prod-key-id", detail="ok", first_break=None):
    return AuditChainVerification(
        ok=ok,
        verified_count=total,
        total_chained=total,
        first_break_seq=first_break,
        anchors_ok=ok,
        anchor_count=1,
        detail=detail,
        key_id=key_id,
    )


# --------------------------------------------------------------------------- assess (pure)


def test_assess_clean_restore_ok():
    report = dr_verify.assess(_verif(), row_counts={"audit_events": 5, "users": 1})
    assert report.ok is True
    assert report.audit_chain_ok and not report.signing_key_is_dev
    assert all(c.ok for c in report.checks)


def test_assess_fails_on_chain_break():
    report = dr_verify.assess(
        _verif(ok=False, detail="entry_hash_mismatch", first_break=3), row_counts={}
    )
    assert report.ok is False
    chain = next(c for c in report.checks if c.name == "audit_chain")
    assert not chain.ok and "entry_hash_mismatch" in chain.detail and "@seq 3" in chain.detail


def test_assess_flags_dev_signing_key():
    report = dr_verify.assess(_verif(key_id=dr_verify._DEV_KEY_ID), row_counts={"audit_events": 5})
    assert report.signing_key_is_dev is True
    assert report.ok is False


def test_assess_empty_history_fails():
    report = dr_verify.assess(_verif(total=0), row_counts={})
    assert report.ok is False
    assert not next(c for c in report.checks if c.name == "audit_history_present").ok


def test_assess_baseline_shortfall_fails():
    report = dr_verify.assess(_verif(), row_counts={"users": 0}, baseline={"users": 1})
    assert report.ok is False
    assert not next(c for c in report.checks if c.name == "row_counts_meet_baseline").ok


def test_assess_baseline_met_ok():
    report = dr_verify.assess(_verif(), row_counts={"users": 3}, baseline={"users": 1})
    assert report.ok is True


def test_assess_fails_on_missing_table():
    # A core table that came back -1 (missing/unqueryable) fails even without a baseline.
    report = dr_verify.assess(_verif(), row_counts={"audit_events": 5, "users": -1})
    assert report.ok is False
    present = next(c for c in report.checks if c.name == "core_tables_present")
    assert not present.ok and "users" in present.detail


def test_parse_min_rows():
    assert dr_verify._parse_min_rows("audit_events=1, users=2") == {"audit_events": 1, "users": 2}
    assert dr_verify._parse_min_rows("") == {}


# --------------------------------------------------------------------------- verify_restore (DB)


def _app(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'dr.sqlite3'}",
        api_key="k",
        require_verified_email=False,
        audit_signing_key="prod-signing-key-under-test",  # not the dev fallback
    )
    app = create_app(settings)
    # Pass the signing key so the chain-head HMAC is written with the same key verify uses.
    init_db(app.state.session_factory, audit_signing_key=settings.audit_signing_key)
    return app, settings


def test_verify_restore_clean(tmp_path):
    app, settings = _app(tmp_path)
    sf = app.state.session_factory
    with TestClient(app) as client:
        for i in range(3):  # each security event writes a paired audit-chain row
            client.post(
                "/security/events", headers={"x-api-key": "k"},
                json={"event_type": "other", "message": f"seed {i}"},
            )
    report = dr_verify.verify_restore(sf, settings, baseline={"audit_events": 1})
    assert report.ok is True, [(c.name, c.detail) for c in report.checks]
    assert report.audit_chain_ok and not report.signing_key_is_dev
    assert report.chained_events >= 3


def test_verify_restore_detects_tamper(tmp_path):
    app, settings = _app(tmp_path)
    sf = app.state.session_factory
    with TestClient(app) as client:
        for i in range(3):
            client.post(
                "/security/events", headers={"x-api-key": "k"},
                json={"event_type": "other", "message": f"seed {i}"},
            )
    with sf() as session:  # tamper a chained audit row
        row = (
            session.query(AuditEventORM)
            .filter(AuditEventORM.chain_seq.is_not(None))
            .order_by(AuditEventORM.chain_seq.asc())
            .first()
        )
        row.message = "tampered-after-restore"
        session.commit()
    report = dr_verify.verify_restore(sf, settings)
    assert report.ok is False and report.audit_chain_ok is False


def test_verify_restore_flags_dev_key(tmp_path):
    # An app with NO AUDIT_SIGNING_KEY resolves to the dev fallback → restore not trusted.
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'dr2.sqlite3'}",
        api_key="k",
        require_verified_email=False,
    )
    app = create_app(settings)
    init_db(app.state.session_factory, audit_signing_key=settings.audit_signing_key)
    with TestClient(app) as client:
        client.post("/security/events", headers={"x-api-key": "k"},
                    json={"event_type": "other", "message": "seed"})
    report = dr_verify.verify_restore(app.state.session_factory, settings)
    assert report.signing_key_is_dev is True and report.ok is False
