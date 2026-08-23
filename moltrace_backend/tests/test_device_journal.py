"""§7.8 / §8.4 — the local device journal.

On the critical path for ANY local execution: the first local route to run tries
to write an audit event, and on a workstation there is no cloud chain to write
to. The Phase 0 prototype intercepted the record-writing globals and counted
deferred writes; that was a prototype device, not a design.

Most of these tests are about time, because §8.4 says time is the hardest problem
in the offline design and version 1.0 did not address it. A device clock is
attacker-controllable and drifts, so the rule is blunt: **the interface must never
present a device timestamp as an authoritative record time.**
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nmrcheck.device_journal import (
    GENESIS,
    ClockState,
    JournalEntry,
    append,
    authoritative_record_time,
    verify_chain,
)

T0 = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


def synced(at=T0, offset=0.25, age=30.0) -> ClockState:
    return ClockState(device_now=at, synchronized=True, offset_seconds=offset,
                      last_sync_age_seconds=age, source="network")


def unsynced(at=T0) -> ClockState:
    return ClockState(device_now=at, synchronized=False, offset_seconds=None,
                      last_sync_age_seconds=None, source="device")


# --- the chain --------------------------------------------------------------


def test_the_first_entry_chains_from_genesis() -> None:
    e = append([], payload={"action": "fid.process"}, clock=synced())
    assert e.prev_hash == GENESIS
    assert verify_chain([e]) is None


def test_entries_chain_and_verify() -> None:
    chain: list[JournalEntry] = []
    for i in range(5):
        chain.append(append(chain, payload={"action": f"a{i}"}, clock=synced(T0 + timedelta(seconds=i))))
    assert verify_chain(chain) is None


def test_a_tampered_payload_breaks_the_chain() -> None:
    chain = [append([], payload={"action": "a"}, clock=synced())]
    chain.append(append(chain, payload={"action": "b"}, clock=synced()))
    tampered = chain[0].__class__(**{**chain[0].__dict__, "payload": {"action": "EDITED"}})
    with pytest.raises(ValueError):
        verify_chain([tampered, chain[1]])


def test_a_removed_entry_breaks_the_chain() -> None:
    chain: list[JournalEntry] = []
    for i in range(3):
        chain.append(append(chain, payload={"action": f"a{i}"}, clock=synced()))
    with pytest.raises(ValueError):
        verify_chain([chain[0], chain[2]])


# --- time, which is the hard part ------------------------------------------


def test_a_device_timestamp_is_NEVER_the_authoritative_record_time() -> None:
    """§8.4, stated as bluntly as the spec states it."""
    e = append([], payload={"action": "a"}, clock=synced())
    assert e.observed_at is None, "an unreconciled entry has no server time"
    assert authoritative_record_time(e) is None, (
        "a device timestamp was offered as the authoritative record time"
    )


def test_the_server_time_becomes_authoritative_only_after_reconciliation() -> None:
    e = append([], payload={"action": "a"}, clock=synced())
    reconciled = e.reconciled(observed_at=T0 + timedelta(minutes=5))
    assert authoritative_record_time(reconciled) == T0 + timedelta(minutes=5)


def test_every_entry_carries_source_offset_and_sync_age() -> None:
    e = append([], payload={"action": "a"}, clock=synced(offset=1.5, age=42.0))
    assert e.time_source == "network"
    assert e.offset_seconds == 1.5
    assert e.last_sync_age_seconds == 42.0


def test_an_unsynchronized_clock_is_recorded_as_such() -> None:
    """§8.4: "A record created while the clock is unsynchronized carries that fact.\""""
    e = append([], payload={"action": "a"}, clock=unsynced())
    assert e.clock_synchronized is False
    assert e.offset_seconds is None


def test_clock_rollback_is_recorded_not_assumed_away() -> None:
    """§8.4: "Clock rollback is a tested state, not an assumption."

    The journal does not refuse the entry — refusing would lose the record of the
    rollback, which is the thing worth keeping. It records that it happened.
    """
    first = append([], payload={"action": "a"}, clock=synced(T0))
    second = append([first], payload={"action": "b"}, clock=synced(T0 - timedelta(hours=1)))
    assert second.clock_went_backwards is True
    assert first.clock_went_backwards is False


def test_a_forward_clock_is_not_flagged_as_rollback() -> None:
    first = append([], payload={"action": "a"}, clock=synced(T0))
    second = append([first], payload={"action": "b"}, clock=synced(T0 + timedelta(seconds=1)))
    assert second.clock_went_backwards is False


def test_reordering_is_caught_by_the_sequence() -> None:
    chain: list[JournalEntry] = []
    for i in range(3):
        chain.append(append(chain, payload={"action": f"a{i}"}, clock=synced(T0 + timedelta(seconds=i))))
    with pytest.raises(ValueError):
        verify_chain([chain[1], chain[0], chain[2]])


def test_truncation_at_the_END_is_NOT_detectable_locally() -> None:
    """Stated as a test so nobody later assumes it is covered.

    A chain of 0..k is indistinguishable from 0..k+5 with the last five deleted:
    the survivors are internally consistent because they were. No arrangement of
    local data fixes this, and a local high-water mark would not either — a key
    that verifies on hardware the attacker controls is a key that forges.
    """
    chain: list[JournalEntry] = []
    for i in range(5):
        chain.append(append(chain, payload={"action": f"a{i}"}, clock=synced(T0 + timedelta(seconds=i))))
    assert verify_chain(chain[:2]) is None, (
        "if this now raises, the local-only claim has changed and the docstring is stale"
    )


def test_the_SERVER_catches_end_truncation_at_reconciliation() -> None:
    """Where the detection actually lives: outside this device.

    The server holds the last sequence it reconciled, so a chain shorter than
    that is missing entries it has already seen.
    """
    chain: list[JournalEntry] = []
    for i in range(5):
        chain.append(append(chain, payload={"action": f"a{i}"}, clock=synced(T0 + timedelta(seconds=i))))
    assert verify_chain(chain, expect_at_least=5) is None
    with pytest.raises(ValueError, match="removed from the end"):
        verify_chain(chain[:2], expect_at_least=5)


# --- the honesty half -------------------------------------------------------


def test_an_entry_never_serializes_a_bare_time_without_its_provenance() -> None:
    """A time in the record that does not say where it came from is the defect
    §8.4 exists to prevent. Every serialized time carries its source."""
    e = append([], payload={"action": "a"}, clock=unsynced())
    d = e.to_dict()
    assert "occurred_at" in d
    for key in ("time_source", "clock_synchronized", "offset_seconds", "last_sync_age_seconds"):
        assert key in d, f"{key} missing — a time was serialized without its provenance"


def test_every_field_the_entry_carries_is_covered_by_the_hash() -> None:
    """Tamper-evidence has to cover the whole entry, not most of it.

    Found by a weakening probe: dropping a field from the hashed body broke
    nothing, because the SAME function computes and verifies, so both sides
    agreed on a hash that no longer covered it. Verification cannot catch that —
    only a test that varies each field and demands the hash move.

    `clock_synchronized` is the one that was uncovered, and it is exactly the
    field an attacker would want to edit: it turns "made on an unsynchronized
    clock" into "made on a good clock" on a regulated record.
    """
    base = dict(payload={"action": "a"}, clock=synced())
    reference = append([], **base)

    variants = {
        "payload": append([], payload={"action": "DIFFERENT"}, clock=synced()),
        "occurred_at": append([], payload={"action": "a"}, clock=synced(at=T0 + timedelta(seconds=1))),
        "time_source": append([], payload={"action": "a"},
                              clock=ClockState(device_now=T0, synchronized=True, offset_seconds=0.25,
                                               last_sync_age_seconds=30.0, source="OTHER")),
        # ONE field different from the reference, deliberately. A first version
        # used unsynced(), which changes FOUR fields — so the hash moved for the
        # wrong reason and the probe stayed green with clock_synchronized
        # uncovered. Vary one thing, in test inputs as much as in weakenings.
        "clock_synchronized": append([], payload={"action": "a"},
                                     clock=ClockState(device_now=T0, synchronized=False,
                                                      offset_seconds=0.25,
                                                      last_sync_age_seconds=30.0,
                                                      source="network")),
        "offset_seconds": append([], payload={"action": "a"}, clock=synced(offset=99.0)),
        "last_sync_age_seconds": append([], payload={"action": "a"}, clock=synced(age=99.0)),
        # clock_went_backwards was in the hashed body and in NO variant, so
        # dropping it would have gone unnoticed — and it is the field an attacker
        # most wants to edit, since it turns a recorded rollback into a clean
        # record. It needs a prior entry to be true, so this variant is a chain.
        "clock_went_backwards": append(
            [append([], payload={"action": "a"}, clock=synced(at=T0 + timedelta(hours=1)))],
            payload={"action": "a"}, clock=synced(),
        ),
    }
    for field_name, variant in variants.items():
        assert variant.entry_hash != reference.entry_hash, (
            f"changing {field_name} did not change the entry hash — "
            f"the field is carried on the record but not covered by its tamper-evidence"
        )


def test_the_canonical_form_is_the_audit_chain_serializer() -> None:
    """Do not invent a second canonicalization. DELTA 3 makes the same demand of
    the entitlement statement, for the same reason: two serializers drift."""
    import inspect

    from nmrcheck import device_journal

    src = inspect.getsource(device_journal)
    assert "audit_chain" in src, "the journal does not reuse the audit chain's canonical form"
