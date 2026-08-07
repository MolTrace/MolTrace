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
from nmrcheck.orm import AuditCheckpointORM, AuditEventORM, utcnow
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


# --------------------------------------------------------- subject-scoped verification
#
# The whole-chain walk above is admin-only and answers a compliance question. A scientist
# looking at a number asks a narrower one — "can I trust the trail behind THIS number?" —
# and could not ask it at all before. These pin what the subject-scoped answer establishes,
# and just as importantly what it does not.


def _dossier(sf, *, owner_id: int) -> int:
    """A minimal owned dossier, so subject access has something real to resolve."""
    from nmrcheck.orm import RegulatoryDossierORM

    with session_scope(sf) as session:
        row = RegulatoryDossierORM(title="D", created_by_user_id=owner_id)
        session.add(row)
        session.flush()
        return int(row.id)


def test_subject_verify_reports_only_that_subjects_entries(tmp_path):
    sf, settings = _factory(tmp_path, "subj1.sqlite3")
    did = _dossier(sf, owner_id=1)
    for i in range(3):
        audit_event(sf, event_type=f"d.{i}", message="m",
                    entity_type="regulatory_dossier", entity_id=did)
    _seed(sf, 4)  # unrelated chained events

    report = ops.verify_subject_audit_chain(
        sf, "regulatory_dossier", did, owner_scope_id=None, settings=settings
    )
    assert report.entry_count == 3, "must scope to the subject, not the whole chain"
    assert report.verified_count == 3
    assert report.ok is True and report.content_ok is True and report.chain_ok is True
    assert report.break_kind is None and report.detail == "ok"


def test_altering_one_subject_entry_is_detected_and_named(tmp_path):
    sf, settings = _factory(tmp_path, "subj2.sqlite3")
    did = _dossier(sf, owner_id=1)
    for i in range(3):
        audit_event(sf, event_type=f"d.{i}", message="m",
                    entity_type="regulatory_dossier", entity_id=did)

    with session_scope(sf) as session:
        row = session.execute(
            select(AuditEventORM)
            .where(AuditEventORM.entity_id == did)
            .order_by(AuditEventORM.chain_seq.asc())
        ).scalars().all()[1]
        row.message = "tampered"
        target_seq = int(row.chain_seq)

    report = ops.verify_subject_audit_chain(
        sf, "regulatory_dossier", did, owner_scope_id=None, settings=settings
    )
    assert report.ok is False
    assert report.content_ok is False
    assert report.first_break_seq == target_seq
    # A machine-readable cause, so no client has to parse `detail`.
    assert report.break_kind == "entry_hash_mismatch"
    assert report.verified_count == 1  # stopped at the altered entry


def test_a_subject_whose_entries_are_intact_still_reports_a_broken_chain(tmp_path):
    """The honest half: removal is not provable from the subject's own slice.

    Entries carry a global chain_seq and no per-subject sequence, so deleting one about this
    subject leaves no gap in the subject's own view. The global walk is what surfaces it, and
    its verdict must not be folded away into a clean `ok`.
    """
    sf, settings = _factory(tmp_path, "subj3.sqlite3")
    did = _dossier(sf, owner_id=1)
    audit_event(sf, event_type="d.0", message="m",
                entity_type="regulatory_dossier", entity_id=did)
    _seed(sf, 4)

    with session_scope(sf) as session:  # delete an UNRELATED entry -> global gap
        victim = session.execute(
            select(AuditEventORM)
            .where(AuditEventORM.entity_id.is_(None))
            .order_by(AuditEventORM.chain_seq.asc())
        ).scalars().first()
        session.delete(victim)

    report = ops.verify_subject_audit_chain(
        sf, "regulatory_dossier", did, owner_scope_id=None, settings=settings
    )
    assert report.content_ok is True, "the subject's own entries were untouched"
    assert report.chain_ok is False
    assert report.chain_break_kind is not None
    assert report.ok is False, "a broken chain cannot be reported as a trustworthy trail"
    assert report.detail.startswith("subject_entries_intact_but_chain_")


def test_a_caller_outside_the_owner_scope_gets_the_missing_subject_answer(tmp_path):
    """Unreachable and non-existent must be indistinguishable, or the trail leaks a census."""
    import pytest

    sf, settings = _factory(tmp_path, "subj4.sqlite3")
    did = _dossier(sf, owner_id=1)
    audit_event(sf, event_type="d.0", message="m",
                entity_type="regulatory_dossier", entity_id=did)

    with pytest.raises(KeyError):
        ops.verify_subject_audit_chain(
            sf, "regulatory_dossier", did, owner_scope_id=999, settings=settings
        )
    with pytest.raises(KeyError):  # same answer for one that does not exist
        ops.verify_subject_audit_chain(
            sf, "regulatory_dossier", 424242, owner_scope_id=999, settings=settings
        )


def test_an_unknown_subject_type_is_the_same_404_not_a_distinct_error(tmp_path):
    """Answering differently would let an outsider enumerate the addressable types."""
    import pytest

    sf, settings = _factory(tmp_path, "subj5.sqlite3")
    with pytest.raises(KeyError):
        ops.verify_subject_audit_chain(
            sf, "not_a_subject", 1, owner_scope_id=None, settings=settings
        )


def test_spectroscopy_sessions_are_refused_and_pointed_at_their_own_surface(tmp_path):
    """A second, weaker path to session records would be a way around the role model."""
    import pytest

    sf, settings = _factory(tmp_path, "subj6.sqlite3")
    with pytest.raises(ValueError, match="session review surface"):
        ops.verify_subject_audit_chain(
            sf, "spectracheck_session", 1, owner_scope_id=None, settings=settings
        )


def test_a_subject_with_no_chained_entries_says_so_rather_than_passing(tmp_path):
    sf, settings = _factory(tmp_path, "subj7.sqlite3")
    did = _dossier(sf, owner_id=1)
    report = ops.verify_subject_audit_chain(
        sf, "regulatory_dossier", did, owner_scope_id=None, settings=settings
    )
    assert report.entry_count == 0
    assert report.detail == "no_chained_entries"


# ----------------------------------------------- verifiable export + offline re-verification
#
# `verify_subject_audit_chain` answers "is it intact?". These pin the harder promise: that an
# outsider can check for themselves. The export must be in the exact shape the digest covers,
# and the standalone script — which imports nothing from this package — must reach the same
# verdict the server does, including when the record has been tampered with.


def _offline_verifier():
    """Load scripts/verify_audit_export.py by path, the way an auditor would run it."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_audit_export.py"
    spec = importlib.util.spec_from_file_location("verify_audit_export", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _export(sf, did):
    return [
        e.model_dump(mode="json")
        for e in ops.export_subject_audit_entries(
            sf, "regulatory_dossier", did, owner_scope_id=None
        )
    ]


def test_the_offline_verifier_agrees_with_the_server_on_a_clean_export(tmp_path):
    sf, settings = _factory(tmp_path, "exp1.sqlite3")
    did = _dossier(sf, owner_id=1)
    for i in range(4):
        audit_event(sf, event_type=f"d.{i}", message=f"m{i}",
                    entity_type="regulatory_dossier", entity_id=did)

    entries = _export(sf, did)
    assert len(entries) == 4
    # The raw stored string, not a parsed dict — the digest covers the text.
    assert all(isinstance(e["metadata_json"], (str, type(None))) for e in entries)

    findings = _offline_verifier().verify(entries)
    assert findings == [], findings
    assert ops.verify_subject_audit_chain(
        sf, "regulatory_dossier", did, owner_scope_id=None, settings=settings
    ).content_ok is True


def test_the_offline_verifier_catches_a_tamper_the_server_also_catches(tmp_path):
    """The whole point: the auditor does not have to take our word for it."""
    sf, settings = _factory(tmp_path, "exp2.sqlite3")
    did = _dossier(sf, owner_id=1)
    for i in range(3):
        audit_event(sf, event_type=f"d.{i}", message=f"m{i}",
                    entity_type="regulatory_dossier", entity_id=did)

    with session_scope(sf) as session:
        row = session.execute(
            select(AuditEventORM)
            .where(AuditEventORM.entity_id == did)
            .order_by(AuditEventORM.chain_seq.asc())
        ).scalars().all()[1]
        row.message = "tampered"

    entries = _export(sf, did)
    findings = _offline_verifier().verify(entries)
    assert any("entry_hash_mismatch" in f for f in findings), findings
    # ...and the server independently reaches the same conclusion.
    assert ops.verify_subject_audit_chain(
        sf, "regulatory_dossier", did, owner_scope_id=None, settings=settings
    ).break_kind == "entry_hash_mismatch"


def test_the_offline_verifier_catches_a_removed_entry(tmp_path):
    sf, _ = _factory(tmp_path, "exp3.sqlite3")
    did = _dossier(sf, owner_id=1)
    for i in range(4):
        audit_event(sf, event_type=f"d.{i}", message=f"m{i}",
                    entity_type="regulatory_dossier", entity_id=did)

    entries = _export(sf, did)
    del entries[1]  # drop one from the middle of the subject's own slice
    findings = _offline_verifier().verify(entries)
    assert any("sequence_gap" in f or "prev_hash_mismatch" in f for f in findings), findings


def test_an_empty_export_is_not_a_pass(tmp_path):
    """Nothing checked must never read as verified — the failure mode this product exists to stop."""
    findings = _offline_verifier().verify([])
    assert findings and "not a pass" in findings[0]


def test_the_export_uses_the_same_access_rule_as_verification(tmp_path):
    import pytest

    sf, _ = _factory(tmp_path, "exp4.sqlite3")
    did = _dossier(sf, owner_id=1)
    with pytest.raises(KeyError):
        ops.export_subject_audit_entries(
            sf, "regulatory_dossier", did, owner_scope_id=999
        )
    with pytest.raises(KeyError):
        ops.export_subject_audit_entries(sf, "not_a_subject", 1, owner_scope_id=None)


# -------------------------------------------------- asymmetric anchor signatures (authenticity)
#
# Per-entry hashing is unkeyed SHA-256, so INTEGRITY was always externally checkable. AUTHENTICITY
# was not: anchors were HMAC-sealed, and a key that verifies an HMAC is a key that forges one, so
# handing it to an auditor proves nothing. Ed25519 anchors close that — the auditor gets the public
# half, which cannot sign.


_SEED = "11" * 32  # 32-byte hex seed


def test_with_no_seed_configured_anchors_are_unchanged():
    """Inert until a deployment opts in — the default path must be byte-identical."""
    from nmrcheck.audit_chain import anchor_payload, sign_anchor

    payload = anchor_payload(from_seq=1, tip_seq=3, tip_hash="sha256:aa", row_count=3,
                             anchored_at=utcnow())
    assert sign_anchor(payload, "k").startswith("hmac-sha256:")
    assert sign_anchor(payload, "k", anchor_seed_hex=None).startswith("hmac-sha256:")


def test_an_ed25519_anchor_verifies_from_the_public_key_alone(tmp_path):
    """The whole point: verification without a secret that could also forge.

    The auditor is given `public`, never the seed, and reaches a correct verdict.
    """
    from nmrcheck.audit_chain import (
        anchor_payload,
        anchor_public_key_hex,
        sign_anchor,
        verify_anchor,
    )

    payload = anchor_payload(from_seq=1, tip_seq=9, tip_hash="sha256:bb", row_count=9,
                             anchored_at=utcnow())
    signature = sign_anchor(payload, "org-secret", anchor_seed_hex=_SEED)
    assert signature.startswith("ed25519:")

    public = anchor_public_key_hex(_SEED)
    assert public and len(public) == 64
    # No seed, no org secret — only the public half.
    assert verify_anchor(payload, signature, None, public_key_hex=public) is True

    # A different payload under the same signature must not verify.
    tampered = anchor_payload(from_seq=1, tip_seq=10, tip_hash="sha256:bb", row_count=9,
                              anchored_at=payload["anchored_at"] and utcnow())
    assert verify_anchor(tampered, signature, None, public_key_hex=public) is False


def test_a_wrong_public_key_does_not_verify():
    from nmrcheck.audit_chain import (
        anchor_payload,
        anchor_public_key_hex,
        sign_anchor,
        verify_anchor,
    )

    payload = anchor_payload(from_seq=1, tip_seq=2, tip_hash="sha256:cc", row_count=2,
                             anchored_at=utcnow())
    signature = sign_anchor(payload, "k", anchor_seed_hex=_SEED)
    other = anchor_public_key_hex("22" * 32)
    assert verify_anchor(payload, signature, None, public_key_hex=other) is False


def test_an_ed25519_anchor_without_any_public_key_is_not_assumed_valid():
    """Unverifiable must never mean verified."""
    from nmrcheck.audit_chain import anchor_payload, sign_anchor, verify_anchor

    payload = anchor_payload(from_seq=1, tip_seq=2, tip_hash="sha256:dd", row_count=2,
                             anchored_at=utcnow())
    signature = sign_anchor(payload, "k", anchor_seed_hex=_SEED)
    assert verify_anchor(payload, signature, "k") is False


def test_enabling_asymmetric_signing_does_not_invalidate_existing_hmac_anchors():
    """Backward compatibility is the reason dispatch reads the signature, not the config.

    A deployment that turns this on must not have every previously sealed anchor start
    reporting as forged.
    """
    from nmrcheck.audit_chain import anchor_payload, sign_anchor, verify_anchor

    payload = anchor_payload(from_seq=1, tip_seq=4, tip_hash="sha256:ee", row_count=4,
                             anchored_at=utcnow())
    old = sign_anchor(payload, "org-secret")  # sealed before the seed existed
    assert old.startswith("hmac-sha256:")
    # ...now the seed IS configured; the old anchor must still verify under its own scheme.
    assert verify_anchor(payload, old, "org-secret", anchor_seed_hex=_SEED) is True


def test_an_unknown_signature_scheme_is_rejected_not_ignored():
    from nmrcheck.audit_chain import anchor_payload, verify_anchor

    payload = anchor_payload(from_seq=1, tip_seq=1, tip_hash="sha256:ff", row_count=1,
                             anchored_at=utcnow())
    assert verify_anchor(payload, "rot13:abc", "k") is False


def test_a_malformed_seed_fails_loudly_rather_than_falling_back_to_hmac():
    """Silently downgrading to HMAC would leave an operator believing anchors are asymmetric."""
    import pytest

    from nmrcheck.audit_chain import AnchorKeyError, anchor_payload, sign_anchor

    payload = anchor_payload(from_seq=1, tip_seq=1, tip_hash="sha256:00", row_count=1,
                             anchored_at=utcnow())
    with pytest.raises(AnchorKeyError):
        sign_anchor(payload, "k", anchor_seed_hex="not-hex")
    with pytest.raises(AnchorKeyError, match="32-byte"):
        sign_anchor(payload, "k", anchor_seed_hex="aabb")


def test_the_live_chain_verifies_end_to_end_with_asymmetric_anchors(tmp_path):
    """The real path: anchor + full verification under a configured seed."""
    url = f"sqlite:///{tmp_path / 'asym.sqlite3'}"
    sf = create_session_factory(url)
    settings = Settings(database_url=url, api_key="test-key", audit_anchor_private_key=_SEED)
    init_db(sf, audit_signing_key=settings.audit_signing_key)
    _seed(sf, 4)

    anchor = ops.create_audit_anchor(sf, settings=settings)
    assert anchor is not None
    assert anchor.signature.startswith("ed25519:")

    report = ops.verify_audit_chain(sf, settings=settings)
    assert report.ok is True, report.detail
    assert report.anchors_ok is True and report.anchor_count == 1


def test_anchor_authenticity_survives_the_JSON_ROUND_TRIP(tmp_path):
    """The gap that let a real bug through: the crypto tests never crossed the wire.

    Signing and verifying an in-process payload dict passed happily while the shipped path
    failed, because `anchored_at` is a datetime and Pydantic renders it `Z` where the
    signature covers `+00:00`. Anything that verifies an anchor must therefore go through
    `model_dump(mode="json")` — the shape an auditor is actually handed — and check the
    bytes that were signed rather than re-deriving them.
    """
    import json

    url = f"sqlite:///{tmp_path / 'rt.sqlite3'}"
    sf = create_session_factory(url)
    settings = Settings(database_url=url, api_key="test-key", audit_anchor_private_key=_SEED)
    init_db(sf, audit_signing_key=settings.audit_signing_key)
    _seed(sf, 3)

    anchor = ops.create_audit_anchor(sf, settings=settings)
    assert anchor is not None
    wire = json.loads(json.dumps(anchor.model_dump(mode="json")))  # exactly what ships

    assert wire["signed_payload"], "the exact signed bytes must reach the auditor"
    # The displayed tip_hash must be the one inside the signed bytes, or a server could
    # sign one checkpoint and show another.
    assert json.loads(wire["signed_payload"])["tip_hash"] == wire["tip_hash"]

    verifier = _offline_verifier()
    from nmrcheck.audit_chain import anchor_public_key_hex

    assert verifier.check_anchor(wire, anchor_public_key_hex(_SEED)) == "OK"
    assert verifier.check_anchor(wire, anchor_public_key_hex("22" * 32)).startswith("FAILED")
    # No public key is "could not establish", never a pass.
    assert verifier.check_anchor(wire, None) != "OK"


def test_a_server_cannot_display_one_tip_hash_and_sign_another():
    """signed_payload is authoritative; the sibling fields are display."""
    import json

    verifier = _offline_verifier()
    from nmrcheck.audit_chain import anchor_public_key_hex

    payload = {"from_seq": 1, "tip_seq": 3, "tip_hash": "sha256:real",
               "row_count": 3, "anchored_at": "2026-08-06T00:00:00+00:00"}
    signed = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    from nmrcheck.audit_chain import _anchor_private_key

    signature = "ed25519:" + _anchor_private_key(_SEED).sign(signed.encode()).hex()
    lying = {"tip_hash": "sha256:fake", "signed_payload": signed, "signature": signature}
    assert verifier.check_anchor(lying, anchor_public_key_hex(_SEED)).startswith("FAILED")
