"""§7.8 / §8.4 — the local device journal.

On the critical path for any local execution. The first local route that runs
tries to write an audit event, and a workstation has no cloud chain to write to.
Phase 0's prototype intercepted the record-writing globals and counted deferred
writes; this is the thing that replaces that device.

The journal **extends** MolTrace's canonical server audit chain, it does not
replace it. Entries are hash-chained here, reconciled to the server later, and
the server chain remains authoritative for anything it has seen.

**Time is the hard part, and §8.4 says version 1.0 did not address it.** A device
clock is attacker-controllable and it drifts. So:

* every entry carries an ``occurred_at`` from the device AND an ``observed_at``
  from the server, the latter absent until reconciliation;
* **the interface must never present a device timestamp as an authoritative
  record time** — :func:`authoritative_record_time` returns ``None`` rather than
  the device's own clock, so a caller that wants a record time has to confront
  the absence instead of being handed a plausible number;
* every entry records its time source, the observed offset, and the age of the
  last successful synchronization, so a record made on an unsynchronized clock
  says so;
* clock rollback is recorded rather than assumed away. The entry is NOT refused:
  refusing would discard the record of the rollback, which is the part worth
  keeping.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .audit_chain import _canon

#: The chain's fixed root, so the first entry has something to commit to.
GENESIS = "sha256:" + "0" * 64


@dataclass(frozen=True)
class ClockState:
    """What the device believes about its own clock, at the moment of writing."""

    device_now: datetime
    synchronized: bool
    offset_seconds: float | None
    last_sync_age_seconds: float | None
    source: str


@dataclass(frozen=True)
class JournalEntry:
    # Position in the chain. NOT a tamper control -- the prev_hash chain already
    # catches reordering and middle-deletion, and weakening probes confirmed the
    # sequence check is masked by it in both cases. It is a RECONCILIATION
    # COORDINATE: it gives the server something to name when it says "I have seen
    # up to here", which is the only place end-truncation is detectable at all.
    sequence: int
    occurred_at: datetime           # the device's clock. NOT a record time.
    observed_at: datetime | None    # the server's clock, at reconciliation.
    time_source: str
    clock_synchronized: bool
    offset_seconds: float | None
    last_sync_age_seconds: float | None
    clock_went_backwards: bool
    payload: dict
    prev_hash: str
    entry_hash: str = field(default="")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["occurred_at"] = self.occurred_at.isoformat()
        d["observed_at"] = self.observed_at.isoformat() if self.observed_at else None
        return d

    def reconciled(self, *, observed_at: datetime) -> JournalEntry:
        """Attach the server's observation. The hash does not change: the entry's
        content is what the device wrote, and the server's time is an annotation
        on it rather than part of what was signed."""
        return JournalEntry(**{**self.__dict__, "observed_at": observed_at})


def _hashed_body(
    *, sequence, occurred_at, time_source, clock_synchronized, offset_seconds,
    last_sync_age_seconds, clock_went_backwards, payload, prev_hash,
) -> dict:
    """Exactly what the entry hash covers. ONE definition.

    It was briefly written out twice — once in ``append`` and once in
    ``verify_chain`` — and a weakening probe walked straight through the gap: an
    edit to one copy left the other agreeing with itself, so the hash quietly
    stopped covering a field while every entry still verified. Two copies of a
    hash input is the same defect as two canonicalizers, one level down.
    """
    return {
        "sequence": sequence,
        "occurred_at": occurred_at.isoformat(),
        "time_source": time_source,
        "clock_synchronized": clock_synchronized,
        "offset_seconds": offset_seconds,
        "last_sync_age_seconds": last_sync_age_seconds,
        "clock_went_backwards": clock_went_backwards,
        "payload": payload,
        "prev_hash": prev_hash,
    }


def _hash_entry(fields: dict) -> str:
    # The audit chain's canonical form, reused rather than reinvented. Two
    # serializers drift, and a drifted serializer breaks verification on exactly
    # the records that matter most.
    return "sha256:" + hashlib.sha256(_canon(fields)).hexdigest()


def append(chain: list[JournalEntry], *, payload: dict, clock: ClockState) -> JournalEntry:
    """Build the next entry. Pure — storage is the caller's problem."""
    prev = chain[-1] if chain else None
    prev_hash = prev.entry_hash if prev else GENESIS
    sequence = (prev.sequence + 1) if prev else 0
    went_backwards = bool(prev and clock.device_now < prev.occurred_at)

    body = _hashed_body(
        sequence=sequence,
        occurred_at=clock.device_now,
        time_source=clock.source,
        clock_synchronized=clock.synchronized,
        offset_seconds=clock.offset_seconds,
        last_sync_age_seconds=clock.last_sync_age_seconds,
        clock_went_backwards=went_backwards,
        payload=payload,
        prev_hash=prev_hash,
    )
    return JournalEntry(
        sequence=sequence,
        occurred_at=clock.device_now,
        observed_at=None,
        time_source=clock.source,
        clock_synchronized=clock.synchronized,
        offset_seconds=clock.offset_seconds,
        last_sync_age_seconds=clock.last_sync_age_seconds,
        clock_went_backwards=went_backwards,
        payload=payload,
        prev_hash=prev_hash,
        entry_hash=_hash_entry(body),
    )


def verify_chain(chain: list[JournalEntry], *, expect_at_least: int | None = None) -> None:
    """Raise if the chain has been edited, reordered, or cut anywhere but the end.

    **Truncation at the END cannot be detected from the chain alone, and no
    arrangement of local data changes that.** A chain of entries 0..k is
    indistinguishable from a chain of 0..k+5 with the last five deleted — the
    remaining entries are internally consistent, because they were. An attacker
    who can edit the local store deletes the entries recording their own most
    recent activity and everything still verifies.

    Reordering and deletion in the middle were ALREADY caught, by the hash link
    alone — a weakening probe confirmed the sequence check is masked by it in both
    cases and adds no detection. The sequence is kept for the message it produces
    and for reconciliation, not as a second control, and this docstring says so
    rather than letting a redundant field read as defence in depth.

    ``expect_at_least`` is where end-truncation is actually caught, and it comes
    from OUTSIDE this device: the server holds the last sequence it reconciled,
    so at the next reconciliation a chain shorter than that is missing entries the
    server has already seen. Locally it is undetectable, and a local high-water
    mark would not help — see the entitlement work for the same conclusion: a key
    that verifies on hardware the attacker controls is a key that forges.
    """
    expected_prev = GENESIS
    for i, e in enumerate(chain):
        # Redundant against the hash link below for every case tested, and kept
        # anyway: it makes a corrupted store fail with a message that says WHICH
        # entry is out of place, where the hash link only says the chain broke.
        # Recorded as redundancy rather than presented as a second control.
        if e.sequence != i:
            raise ValueError(
                f"journal entry {i} carries sequence {e.sequence}; entries are missing or reordered"
            )
        if e.prev_hash != expected_prev:
            raise ValueError(f"journal entry {i} does not follow the previous entry")
        body = _hashed_body(
            sequence=e.sequence,
            occurred_at=e.occurred_at,
            time_source=e.time_source,
            clock_synchronized=e.clock_synchronized,
            offset_seconds=e.offset_seconds,
            last_sync_age_seconds=e.last_sync_age_seconds,
            clock_went_backwards=e.clock_went_backwards,
            payload=e.payload,
            prev_hash=e.prev_hash,
        )
        if _hash_entry(body) != e.entry_hash:
            raise ValueError(f"journal entry {i} has been altered since it was written")
        expected_prev = e.entry_hash

    if expect_at_least is not None and len(chain) < expect_at_least:
        raise ValueError(
            f"the journal holds {len(chain)} entries but the server has already "
            f"reconciled {expect_at_least}; entries have been removed from the end"
        )


def authoritative_record_time(entry: JournalEntry) -> datetime | None:
    """The time an interface may present as THE record time — or ``None``.

    Returns ``None`` for an unreconciled entry rather than falling back to
    ``occurred_at``. That is the whole point: a fallback here would put an
    attacker-controllable clock on a regulated record, and it would do it
    silently, because a plausible timestamp looks exactly like a real one.
    """
    return entry.observed_at
