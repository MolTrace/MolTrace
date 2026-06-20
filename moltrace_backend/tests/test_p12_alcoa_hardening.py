"""ALCOA+ hardening (Security Prompt 12).

Covers the genuine gaps this build closes (most of ALCOA+ was already satisfied by P10/P11):
  * Attributable / *why* — reason-for-change is a queryable column, enforced by a shared primitive.
  * Enduring / reversible-by-record — archive is a soft-delete (row retained, deleted_at/by set,
    excluded from default reads), never a physical delete.
  * Contemporaneous — verify-only: regulated timestamps are server-authoritative; the client cannot
    supply created_at.
  * Original — the raw vault's write-once can no longer silently degrade to warn-only (strict mode).
  * Immutable audit trail — audit_events has no deletion path (regression guard).
"""

from __future__ import annotations

import hashlib
import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient

from nmrcheck import alcoa
from nmrcheck.api import create_app
from nmrcheck.database import init_db
from nmrcheck.orm import ControlledRecordORM
from nmrcheck.raw_vault import LocalRawStorageBackend, RawVaultError
from nmrcheck.settings import Settings


def _app(tmp_path):
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'alcoa.sqlite3'}",
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


def _make_record(client: TestClient, bearer: dict, title: str = "SOP") -> dict:
    res = client.post(
        "/controlled-records",
        headers=bearer,
        json={"record_type": "sop", "title": title, "content_json": {"body": title}},
    )
    assert res.status_code == 201, res.text
    return res.json()


# --------------------------------------------------------------------------- alcoa unit


def test_require_reason_for_change():
    assert alcoa.require_reason_for_change("  fix typo  ") == "fix typo"
    for bad in (None, "", "   ", "\t\n"):
        with pytest.raises(alcoa.ReasonForChangeRequired):
            alcoa.require_reason_for_change(bad)
    with pytest.raises(alcoa.ReasonForChangeRequired):
        alcoa.require_reason_for_change("x" * (alcoa.MAX_REASON_LEN + 1))


def test_apply_soft_delete_and_predicate():
    class Row:
        deleted_at = None
        deleted_by = None
        reason_for_change = None

    row = Row()
    assert alcoa.is_soft_deleted(row) is False
    now = datetime(2026, 6, 19, tzinfo=UTC)
    alcoa.apply_soft_delete(row, reason=" obsolete ", actor="a@b.co", now=now)
    assert row.deleted_at == now and row.deleted_by == "a@b.co"
    assert row.reason_for_change == "obsolete"
    assert alcoa.is_soft_deleted(row) is True


def test_audit_events_declared_immutable():
    assert "audit_events" in alcoa.REGULATED_IMMUTABLE_TABLES
    assert "audit_checkpoints" in alcoa.REGULATED_IMMUTABLE_TABLES


# --------------------------------------------------------------------------- reason-for-change


def test_archive_requires_real_reason(tmp_path):
    """A whitespace-only reason passes the model's min_length=1 but the store primitive rejects it."""
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "r@acme.com")
        rid = _make_record(client, bearer)["id"]
        res = client.post(
            f"/controlled-records/{rid}/archive", headers=bearer, json={"reason": "   "}
        )
        assert res.status_code == 422, res.text


def test_lock_persists_reason_to_column(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "l@acme.com")
        rid = _make_record(client, bearer)["id"]
        locked = client.post(
            f"/controlled-records/{rid}/lock",
            headers=bearer,
            json={"locked_by": "QA", "reason": "Issued for execution."},
        )
        assert locked.status_code == 200, locked.text
        assert locked.json()["reason_for_change"] == "Issued for execution."


# --------------------------------------------------------------------------- soft-delete / reversible


def test_archive_is_soft_delete_and_non_leaking(tmp_path):
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "owner@acme.com")
        rid = _make_record(client, bearer, "to-archive")["id"]
        archived = client.post(
            f"/controlled-records/{rid}/archive",
            headers=bearer,
            json={"reason": "Superseded by v2."},
        )
        assert archived.status_code == 200, archived.text
        body = archived.json()
        assert body["status"] == "archived"
        assert body["deleted_at"] is not None
        assert body["deleted_by"] == "owner@acme.com"  # §11.100-style: the authenticated principal
        assert body["reason_for_change"] == "Superseded by v2."
        # Default list excludes the soft-deleted row...
        default_list = client.get("/controlled-records", headers=bearer).json()
        assert all(r["id"] != rid for r in default_list)
        # ...but it is retained and retrievable for the reversible-by-record trail.
        with_deleted = client.get(
            "/controlled-records?include_deleted=true", headers=bearer
        ).json()
        assert any(r["id"] == rid for r in with_deleted)
        # The physical row still exists in the DB (never session.delete'd).
        with app.state.session_factory() as s:
            assert s.get(ControlledRecordORM, rid) is not None


# --------------------------------------------------------------------------- contemporaneous (verify-only)


def test_client_cannot_supply_timestamp(tmp_path):
    """Regulated create rejects a client-supplied created_at (extra='forbid'); timestamp is server-set."""
    app = _app(tmp_path)
    with TestClient(app) as client:
        bearer = _signup(client, "t@acme.com")
        res = client.post(
            "/controlled-records",
            headers=bearer,
            json={
                "record_type": "sop",
                "title": "ts",
                "created_at": "2000-01-01T00:00:00Z",
            },
        )
        assert res.status_code == 422  # created_at is not an accepted input field
        ok = _make_record(client, bearer, "ts-ok")
        assert ok["created_at"]  # server-populated


# --------------------------------------------------------------------------- raw vault write-once strict


def test_raw_vault_strict_chmod_raises(tmp_path, monkeypatch):
    content = b"raw-archive-bytes"
    sha = hashlib.sha256(content).hexdigest()

    def _boom(self, mode):  # noqa: ANN001
        raise OSError("filesystem refuses chmod")

    monkeypatch.setattr(Path, "chmod", _boom)
    strict_backend = LocalRawStorageBackend(tmp_path / "vault_strict")
    with pytest.raises(RawVaultError):
        strict_backend.save(
            content=content, sha256=sha, filename="a.bin", strict_immutable=True
        )
    # Non-strict (default) preserves the legacy warn-only behavior on chmod failure.
    warnings: list[str] = []
    lenient_backend = LocalRawStorageBackend(tmp_path / "vault_lenient")
    result = lenient_backend.save(
        content=content, sha256=sha, filename="a.bin", warnings=warnings, strict_immutable=False
    )
    assert result["read_only"] is False
    assert any("read-only" in w for w in warnings)


# --------------------------------------------------------------------------- audit immutability regression


def test_no_delete_route_on_audit_events(tmp_path):
    app = _app(tmp_path)
    for route in app.routes:
        methods = getattr(route, "methods", set()) or set()
        path = getattr(route, "path", "")
        if "DELETE" in methods:
            assert "audit" not in path.lower(), f"audit trail must be immutable: {path}"


# --------------------------------------------------------------------------- migration 0028 isolation


def test_migration_0028_upgrade_downgrade_idempotent():
    eng = sa.create_engine("sqlite:///:memory:")
    conn = eng.connect()
    # Pre-0028 controlled_records shape (the three ALCOA+ columns absent).
    conn.exec_driver_sql(
        """CREATE TABLE controlled_records (
            id INTEGER PRIMARY KEY, record_type VARCHAR(64), resource_id INTEGER,
            title VARCHAR(300), version VARCHAR(64), status VARCHAR(32), content_hash VARCHAR(64),
            locked_at TIMESTAMP, locked_by VARCHAR(200), retention_policy_id INTEGER,
            created_at TIMESTAMP, updated_at TIMESTAMP, metadata_json TEXT)"""
    )
    conn.commit()
    spec = importlib.util.spec_from_file_location(
        "m0028",
        str(
            Path(__file__).resolve().parents[1]
            / "alembic/versions/0028_alcoa_reason_soft_delete.py"
        ),
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.op = Operations(MigrationContext.configure(conn))

    def cols():
        return {
            r[1]
            for r in conn.exec_driver_sql("PRAGMA table_info(controlled_records)").fetchall()
        }

    m.upgrade()
    assert {"reason_for_change", "deleted_at", "deleted_by"} <= cols()
    m.upgrade()  # idempotent
    assert {"reason_for_change", "deleted_at", "deleted_by"} <= cols()
    m.downgrade()
    assert not ({"reason_for_change", "deleted_at", "deleted_by"} & cols())
    m.downgrade()  # idempotent


def test_ensure_sqlite_schema_has_alcoa_columns(tmp_path):
    app = _app(tmp_path)
    init_db(app.state.session_factory)  # second run is a no-op
    with app.state.session_factory() as s:
        cols = {
            r[1]
            for r in s.connection()
            .exec_driver_sql("PRAGMA table_info(controlled_records)")
            .fetchall()
        }
    assert {"reason_for_change", "deleted_at", "deleted_by"} <= cols
