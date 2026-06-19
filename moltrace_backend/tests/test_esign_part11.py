"""21 CFR Part 11 e-signature hardening (Security Prompt 11).

Covers the two gaps this build closes:
  * §11.100 — signer identity is the authenticated server principal; the client-supplied name is
    ignored (impersonation attempt is recorded, not honoured).
  * §11.70  — the signature is bound to a SHA-256 of the signed record's content and is therefore
    non-transferable; mutating the record invalidates the binding.
Plus the §11.50 manifestation, the §11.200 step-up gate, P10 audit-chain integration, the honest
"unbound" path for target types without a snapshot resolver, and back-compat for inline callers.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from nmrcheck import esign
from nmrcheck import validation_center_store as validation_store
from nmrcheck.api import create_app
from nmrcheck.database import init_db
from nmrcheck.models import SystemReleaseApproveRequest, SystemReleaseRecordCreate
from nmrcheck.orm import AuditEventORM, ControlledRecordORM, ElectronicSignatureRecordORM
from nmrcheck.settings import Settings


def _app(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'esign.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    init_db(app.state.session_factory)
    return app


def _signup(client: TestClient, email: str, password: str = "password123") -> dict:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": password, "password_confirm": password},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _step_up(client: TestClient, bearer: dict, password: str = "password123") -> None:
    res = client.post("/auth/step-up/password", headers=bearer, json={"password": password})
    assert res.status_code == 200, res.text


def _make_controlled_record(client: TestClient, bearer: dict) -> int:
    res = client.post(
        "/controlled-records", headers=bearer, json={"record_type": "sop", "title": "Test SOP"}
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


# --------------------------------------------------------------------------- esign unit


def _binding(**over):
    base = dict(
        signer_user_id=7,
        signer_email="a@b.co",
        signer_display_name="a@b.co",
        signature_meaning="approved",
        target_type="controlled_record",
        target_id=3,
        record_content_hash="sha256:" + "a" * 64,
        reason="ok",
        signed_at=datetime(2026, 6, 19, tzinfo=UTC),
        step_up_factor="password",
        step_up_aal="aal1",
    )
    base.update(over)
    return base


def test_digest_is_deterministic_and_order_independent():
    p1 = esign.canonical_signature_payload(**_binding())
    p2 = esign.canonical_signature_payload(**_binding())
    assert esign.compute_signature_digest(p1) == esign.compute_signature_digest(p2)
    assert esign.compute_record_content_hash({"a": 1, "b": 2}) == esign.compute_record_content_hash(
        {"b": 2, "a": 1}
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("signer_user_id", 99),
        ("record_content_hash", "sha256:" + "b" * 64),
        ("signature_meaning", "rejected"),
        ("target_id", 4),
        ("reason", "different"),
    ],
)
def test_any_binding_field_change_changes_digest(field, value):
    base = esign.compute_signature_digest(esign.canonical_signature_payload(**_binding()))
    changed = esign.compute_signature_digest(
        esign.canonical_signature_payload(**_binding(**{field: value}))
    )
    assert base != changed


def test_verify_detects_tamper_and_content_change():
    payload = esign.canonical_signature_payload(**_binding())
    digest = esign.compute_signature_digest(payload)
    stored = {**_binding(), "signature_digest": digest}
    ok = esign.verify_signature(stored)
    assert ok["bound"] and ok["valid"] and ok["hash_matches"]
    same = esign.verify_signature(stored, recomputed_content_hash=stored["record_content_hash"])
    assert same["content_matches"] is True and same["valid"] is True
    moved = esign.verify_signature(stored, recomputed_content_hash="sha256:" + "0" * 64)
    assert moved["content_matches"] is False and moved["valid"] is False
    tampered = esign.verify_signature({**stored, "reason": "evil"})
    assert tampered["hash_matches"] is False and tampered["valid"] is False


def test_verify_legacy_unbound_signature():
    stored = {**_binding(), "signature_digest": None}
    v = esign.verify_signature(stored, recomputed_content_hash="sha256:" + "0" * 64)
    assert v["bound"] is False and v["valid"] is None and v["content_matches"] is None


# --------------------------------------------------------------------------- route: §11.200 / §11.100 / §11.70


def test_sign_requires_step_up(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "s@acme.com")
        rid = _make_controlled_record(client, bearer)
        blocked = client.post(
            "/esignatures/records",
            headers=bearer,
            json={
                "signer_name": "x",
                "signature_meaning": "approved",
                "target_type": "controlled_record",
                "target_id": rid,
                "reason": "r",
            },
        )
        assert blocked.status_code == 401 and blocked.json()["detail"] == "step_up_required"


def test_signer_identity_is_server_authoritative(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "real@acme.com")
        rid = _make_controlled_record(client, bearer)
        _step_up(client, bearer)
        res = client.post(
            "/esignatures/records",
            headers=bearer,
            json={
                "signer_name": "IMPERSONATED VICTIM",
                "signer_email": "victim@evil.com",
                "signature_meaning": "approved",
                "target_type": "controlled_record",
                "target_id": rid,
                "reason": "approve",
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        # §11.100 — persisted signer is the authenticated principal, NOT the client-supplied name.
        assert body["signer_name"] == "real@acme.com"
        assert body["signer_email"] == "real@acme.com"
        assert body["signer_user_id"] is not None
        assert body["metadata_json"].get("client_declared_signer_name") == "IMPERSONATED VICTIM"
        # §11.70 — content-bound digest present.
        assert body["record_content_hash"].startswith("sha256:")
        assert body["signature_digest"].startswith("sha256:")


def test_verify_and_content_change_detection(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "rev@acme.com")
        rid = _make_controlled_record(client, bearer)
        _step_up(client, bearer)
        sid = client.post(
            "/esignatures/records",
            headers=bearer,
            json={
                "signer_name": "x",
                "signature_meaning": "approved",
                "target_type": "controlled_record",
                "target_id": rid,
                "reason": "r",
            },
        ).json()["id"]
        v = client.get(f"/esignatures/records/{sid}/verify", headers=bearer).json()
        assert v["bound"] and v["valid"] and v["hash_matches"]
        vr = client.get(f"/esignatures/records/{sid}/verify?recompute=true", headers=bearer).json()
        assert vr["content_matches"] is True and vr["valid"] is True
        # Mutate the signed record's content -> recompute detects the change (§11.70).
        with app.state.session_factory() as s:
            row = s.get(ControlledRecordORM, rid)
            row.version = "99"
            s.commit()
        vr2 = client.get(f"/esignatures/records/{sid}/verify?recompute=true", headers=bearer).json()
        assert vr2["content_matches"] is False and vr2["valid"] is False


def test_manifestation_json_and_html(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "m@acme.com")
        rid = _make_controlled_record(client, bearer)
        _step_up(client, bearer)
        sid = client.post(
            "/esignatures/records",
            headers=bearer,
            json={
                "signer_name": "x",
                "signature_meaning": "approved",
                "target_type": "controlled_record",
                "target_id": rid,
                "reason": "release approval",
            },
        ).json()["id"]
        j = client.get(f"/esignatures/records/{sid}/manifestation", headers=bearer).json()
        assert j["printed_name"] == "m@acme.com"
        assert j["meaning_label"] == "Approved by"
        assert j["signed_at_utc"] and j["compliance_notice"]
        assert j["record_content_hash"].startswith("sha256:")
        h = client.get(f"/esignatures/records/{sid}/manifestation?format=html", headers=bearer)
        assert h.status_code == 200
        assert "Electronic signature" in h.text and "m@acme.com" in h.text


def test_unbound_target_is_honest(tmp_path):
    """A target type with no server-side snapshot resolver signs but stays unbound (not fake-bound)."""
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "u@acme.com")
        _step_up(client, bearer)
        sig = client.post(
            "/esignatures/records",
            headers=bearer,
            json={
                "signer_name": "x",
                "signature_meaning": "reviewed",
                "target_type": "analysis",
                "target_id": 123,
                "reason": "r",
            },
        ).json()
        assert sig["record_content_hash"] is None and sig["signature_digest"] is None
        v = client.get(f"/esignatures/records/{sig['id']}/verify", headers=bearer).json()
        assert v["bound"] is False and v["valid"] is None


def test_signing_emits_chained_audit_event(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "a@acme.com")
        rid = _make_controlled_record(client, bearer)
        _step_up(client, bearer)
        client.post(
            "/esignatures/records",
            headers=bearer,
            json={
                "signer_name": "x",
                "signature_meaning": "approved",
                "target_type": "controlled_record",
                "target_id": rid,
                "reason": "r",
            },
        )
        with app.state.session_factory() as s:
            events = (
                s.execute(
                    select(AuditEventORM).where(AuditEventORM.event_type == "esignature.create")
                )
                .scalars()
                .all()
            )
        assert events
        assert all(e.chain_seq is not None and e.entry_hash for e in events)


# --------------------------------------------------------------------------- back-compat / migration


def test_system_release_signature_is_content_bound(tmp_path):
    """The inline system-release approval path still works and now content-binds its signature,
    while keeping the legacy 64-char signature_hash."""
    app = _app(tmp_path)
    sf = app.state.session_factory
    release = validation_store.create_system_release(
        sf,
        SystemReleaseRecordCreate(
            release_version="1.0.0",
            release_type="backend",
            change_summary="initial",
            test_summary_json={"passed": 10},
            risk_summary_json={"high": 0},
        ),
    )
    validation_store.approve_system_release(
        sf,
        release.id,
        SystemReleaseApproveRequest(signer_name="QA Lead", reason="approved", release=True),
    )
    with sf() as s:
        row = (
            s.execute(
                select(ElectronicSignatureRecordORM).where(
                    ElectronicSignatureRecordORM.target_type == "system_release"
                )
            )
            .scalars()
            .first()
        )
    assert row is not None
    assert len(row.signature_hash) == 64  # legacy String(64) hash preserved
    assert row.record_content_hash and row.record_content_hash.startswith("sha256:")
    assert row.signature_digest and row.signature_digest.startswith("sha256:")


def test_esign_columns_present_and_idempotent(tmp_path):
    """init_db (which runs _ensure_sqlite_schema) is idempotent and yields the binding columns."""
    app = _app(tmp_path)
    init_db(app.state.session_factory)  # second run must be a no-op
    with app.state.session_factory() as s:
        cols = {
            row[1]
            for row in s.connection()
            .exec_driver_sql("PRAGMA table_info(electronic_signature_records)")
            .fetchall()
        }
    assert {"signer_user_id", "record_content_hash", "signature_digest"} <= cols
