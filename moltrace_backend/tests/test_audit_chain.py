"""Tamper-evident audit hash chain (Security Prompt 10).

Covers: every audit write (via ``audit_event`` AND direct ``AuditEventORM(...)`` construction) is
chained and verifies; tampering / deletion is detected at the right sequence; signed anchors
catch a forged tip and a wrong signing key; the legacy pre-chain prefix is tolerated; the
reconciliation job alerts and records a break; and the lightweight health check reflects it.
"""

from __future__ import annotations

from sqlalchemy import select

from nmrcheck import operations_store as ops
from nmrcheck.audit_chain import GENESIS_HASH
from nmrcheck.database import (
    audit_event,
    create_session_factory,
    init_db,
    list_audit_events,
    session_scope,
)
from nmrcheck.orm import AuditCheckpointORM, AuditEventORM
from nmrcheck.settings import Settings


def _factory(tmp_path, name="ac.sqlite3"):
    url = f"sqlite:///{tmp_path / name}"
    sf = create_session_factory(url)
    settings = Settings(database_url=url, api_key="test-key")
    init_db(sf, audit_signing_key=settings.audit_signing_key)
    return sf, settings


def _seed(sf, n=5):
    for i in range(n):
        audit_event(sf, event_type=f"test.event.{i}", message=f"message {i}")


# --------------------------------------------------------------------------- chain integrity
def test_chain_appends_and_verifies(tmp_path):
    sf, st = _factory(tmp_path)
    _seed(sf, 5)
    v = ops.verify_audit_chain(sf, settings=st)
    assert v.ok is True
    assert v.verified_count == 5 and v.total_chained == 5
    assert v.first_break_seq is None
    with session_scope(sf) as s:
        rows = s.execute(select(AuditEventORM).order_by(AuditEventORM.chain_seq)).scalars().all()
        assert [r.chain_seq for r in rows] == [1, 2, 3, 4, 5]
        assert rows[0].prev_hash == GENESIS_HASH
        assert all(r.entry_hash.startswith("sha256:") for r in rows)


def test_direct_construction_is_also_chained(tmp_path):
    # ~22 store modules build AuditEventORM directly; the before_flush listener must chain them too.
    sf, st = _factory(tmp_path)
    audit_event(sf, event_type="via.helper", message="one")
    with session_scope(sf) as s:
        s.add(AuditEventORM(event_type="direct.construct", message="two", metadata_json="{}"))
    v = ops.verify_audit_chain(sf, settings=st)
    assert v.ok is True and v.verified_count == 2


def test_tampered_message_detected(tmp_path):
    sf, st = _factory(tmp_path)
    _seed(sf, 5)
    with session_scope(sf) as s:
        row = s.execute(select(AuditEventORM).where(AuditEventORM.chain_seq == 3)).scalars().one()
        row.message = "TAMPERED"
    v = ops.verify_audit_chain(sf, settings=st)
    assert v.ok is False
    assert v.first_break_seq == 3 and v.detail == "entry_hash_mismatch"


def test_unanchored_tail_truncation_detected(tmp_path):
    # Review HIGH: deleting the most-recent rows that NO anchor has sealed yet leaves a valid
    # prefix — the signed high-water mark is what catches it.
    sf, st = _factory(tmp_path)
    _seed(sf, 5)
    ops.create_audit_anchor(sf, settings=st)  # anchors 1-5
    _seed(sf, 2)  # rows 6,7 — unanchored
    assert ops.verify_audit_chain(sf, settings=st).ok is True
    with session_scope(sf) as s:  # truncate the unanchored tail
        for seq in (6, 7):
            rid = s.execute(select(AuditEventORM.id).where(AuditEventORM.chain_seq == seq)).scalar_one()
            s.delete(s.get(AuditEventORM, rid))
    v = ops.verify_audit_chain(sf, settings=st)
    assert v.ok is False and v.detail.startswith("tail_truncated")
    assert ops.audit_chain_check(sf, settings=st).status == "error"  # O(1) health catches it too


def test_forged_head_detected(tmp_path):
    sf, st = _factory(tmp_path)
    _seed(sf, 3)
    from nmrcheck.orm import AuditChainHeadORM

    with session_scope(sf) as s:  # attacker lowers the head to match a truncated chain
        head = s.get(AuditChainHeadORM, 1)
        head.max_seq = 1
    v = ops.verify_audit_chain(sf, settings=st)
    assert v.ok is False and v.detail == "head_signature_invalid"


def test_deleted_row_detected(tmp_path):
    sf, st = _factory(tmp_path)
    _seed(sf, 5)
    with session_scope(sf) as s:
        s.execute(select(AuditEventORM).where(AuditEventORM.chain_seq == 3)).scalars().one()
        s.delete(s.get(AuditEventORM, s.execute(
            select(AuditEventORM.id).where(AuditEventORM.chain_seq == 3)
        ).scalar_one()))
    v = ops.verify_audit_chain(sf, settings=st)
    assert v.ok is False
    assert v.first_break_seq == 4 and v.detail in {"sequence_gap", "prev_hash_mismatch"}


# --------------------------------------------------------------------------- anchors
def test_anchor_created_and_verified(tmp_path):
    sf, st = _factory(tmp_path)
    _seed(sf, 4)
    anchor = ops.create_audit_anchor(sf, settings=st)
    assert anchor is not None and anchor.from_seq == 1 and anchor.tip_seq == 4
    v = ops.verify_audit_chain(sf, settings=st)
    assert v.ok is True and v.anchors_ok is True and v.anchor_count == 1


def test_anchor_with_nothing_new_returns_none(tmp_path):
    sf, st = _factory(tmp_path)
    _seed(sf, 2)
    assert ops.create_audit_anchor(sf, settings=st) is not None
    # second anchor with no new rows since the first -> None
    assert ops.create_audit_anchor(sf, settings=st) is None


def test_forged_anchor_tip_detected(tmp_path):
    sf, st = _factory(tmp_path)
    _seed(sf, 3)
    ops.create_audit_anchor(sf, settings=st)
    with session_scope(sf) as s:  # corrupt the checkpoint's recorded tip hash
        chk = s.execute(select(AuditCheckpointORM)).scalars().one()
        chk.tip_hash = "sha256:" + "f" * 64
    v = ops.verify_audit_chain(sf, settings=st)
    assert v.anchors_ok is False and v.ok is False


def test_anchor_fails_under_wrong_signing_key(tmp_path):
    sf, st = _factory(tmp_path)
    _seed(sf, 3)
    ops.create_audit_anchor(sf, settings=st)  # signed with st's (default/dev) key
    other = Settings(database_url=st.database_url, api_key="test-key", audit_signing_key="other-key")
    v = ops.verify_audit_chain(sf, settings=other)
    assert v.anchors_ok is False  # HMAC signature no longer verifies


# --------------------------------------------------------------------------- legacy + reconcile
def test_legacy_prechain_rows_tolerated(tmp_path):
    sf, st = _factory(tmp_path)
    # Simulate a pre-Prompt-10 row: chain columns NULL (listener leaves them; we force-clear).
    with session_scope(sf) as s:
        s.add(AuditEventORM(event_type="legacy", message="old", metadata_json="{}"))
    with session_scope(sf) as s:
        row = s.execute(select(AuditEventORM)).scalars().one()
        row.chain_seq = None
        row.entry_hash = None
        row.prev_hash = None
    _seed(sf, 3)  # new chained rows after the legacy one
    v = ops.verify_audit_chain(sf, settings=st)
    assert v.ok is True and v.verified_count == 3  # legacy row skipped, chain verifies from genesis


def test_empty_chain_verifies_trivially(tmp_path):
    sf, st = _factory(tmp_path)
    v = ops.verify_audit_chain(sf, settings=st)
    assert v.ok is True and v.verified_count == 0


def test_reconcile_alerts_and_records_break(tmp_path):
    sf, st = _factory(tmp_path)
    _seed(sf, 4)
    with session_scope(sf) as s:
        row = s.execute(select(AuditEventORM).where(AuditEventORM.chain_seq == 2)).scalars().one()
        row.message = "HACKED"
    alerts: list = []
    report = ops.reconcile_audit_chain(sf, settings=st, alert_fn=alerts.append)
    assert report.ok is False
    assert len(alerts) == 1
    breaks = list_audit_events(sf, limit=50, event_type="security.audit_chain.break")
    assert len(breaks) >= 1
    # the health check now reflects the recorded break
    assert ops.audit_chain_check(sf, settings=st).status == "error"


def test_health_check_ok_on_clean_chain(tmp_path):
    sf, st = _factory(tmp_path)
    _seed(sf, 3)
    ops.create_audit_anchor(sf, settings=st)
    assert ops.audit_chain_check(sf, settings=st).status == "ok"
