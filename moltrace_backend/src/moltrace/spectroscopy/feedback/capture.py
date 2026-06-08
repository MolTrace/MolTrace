"""In-app feedback capture (Prompt 23, Roadmap Phases 5-6).

Every AI output a reviewer sees -- a predicted shift, a proposed structure, a
peak label, a purity call -- is rendered with a "Was this correct?" control:
thumbs up/down, an optional free-text correction, and a structured **reason
taxonomy** (:class:`ReasonCode`). This module is the *single intake* for those
signals. It turns each click into an immutable, content-addressed
:class:`FeedbackEvent` that records:

* **what** was rated (:class:`OutputKind` + an ``output_ref`` content address),
* the **verdict** (thumbs up / down) and the structured **reason**,
* the reviewer's **correction** (free text and/or a structured ``corrected_value``),
* the **Prompt 13 ``model_versions``** that produced the output (so a correction
  is forever attributable to the exact artifacts that earned it), and
* the full **context** + reviewer / tenant identity.

This is the production embodiment of MolTrace's data moat: corrections become a
*structured asset*, not a lost comment. Two sinks fan out from the intake:

* a **correction with a ``corrected_value``** becomes a :class:`LabeledExample`
  -- the labeled-example store the Prompt 16 active-learning loop consumes
  (:meth:`FeedbackCollector.labeled_examples`); and
* a **bare override** (thumbs down, no ground truth supplied) is routed to the
  Prompt 16 :class:`~moltrace.spectroscopy.ai.finetune.ActiveLearningQueue` as a
  case that still needs a label.

Alongside, :func:`usage_analytics` rolls up lightweight product analytics: which
output kinds are used and *where reviewers override* (the override rate per
kind), which feeds the Prompt 17 A/B comparison and tells the team where the
model is weakest.

Persistence is pluggable behind :class:`FeedbackStore` (mirroring the Prompt 13
registry): :class:`InMemoryFeedbackStore` for tests / ephemeral use and
:class:`SqlAlchemyFeedbackStore` for durable PostgreSQL / SQLite. Writes are
append-only and idempotent (re-submitting a byte-identical event is a no-op).
Only the standard library + the in-repo contract layer are imported, so the
intake stays usable in minimal environments.
"""

from __future__ import annotations

import abc
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from moltrace.spectroscopy.ai.finetune import ActiveLearningItem, ActiveLearningQueue
from moltrace.spectroscopy.infra.contract import content_hash

__all__ = [
    "FeedbackCollector",
    "FeedbackEvent",
    "FeedbackStore",
    "FeedbackVerdict",
    "InMemoryFeedbackStore",
    "LabeledExample",
    "OutputKind",
    "ReasonCode",
    "SqlAlchemyFeedbackStore",
    "UsageAnalytics",
    "usage_analytics",
]

# Severity assigned to a human override routed to the active-learning queue. A
# reviewer thumbs-down is a high-signal hard case (above the 0.5 contradiction
# threshold), but below an outright cross-modal disagreement (0.8).
_OVERRIDE_SEVERITY = 0.9


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
class OutputKind(StrEnum):
    """The kind of AI output a feedback control is attached to."""

    PREDICTED_SHIFT = "predicted_shift"  # a predicted chemical shift (ppm)
    PROPOSED_STRUCTURE = "proposed_structure"  # an LLM/CASE-proposed SMILES
    PEAK_LABEL = "peak_label"  # a peak category / assignment
    PURITY_CALL = "purity_call"  # a qNMR purity verdict
    MULTIPLICITY = "multiplicity"  # a multiplet multiplicity label
    INTEGRATION = "integration"  # an integration / proton-count call
    OTHER = "other"


class FeedbackVerdict(StrEnum):
    """The thumbs control: did the reviewer accept the AI output?"""

    UP = "up"  # thumbs up -- accepted
    DOWN = "down"  # thumbs down -- rejected / overridden


class ReasonCode(StrEnum):
    """The structured reason taxonomy for a correction (why it was wrong)."""

    WRONG_SHIFT = "wrong_shift"
    WRONG_MULTIPLICITY = "wrong_multiplicity"
    WRONG_STRUCTURE = "wrong_structure"
    MISSED_IMPURITY = "missed_impurity"
    WRONG_INTEGRATION = "wrong_integration"
    CALIBRATION_OFF = "calibration_off"
    OTHER = "other"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _coerce_versions(model_versions: Mapping[str, str] | None) -> dict[str, str]:
    return {str(k): str(v) for k, v in dict(model_versions or {}).items()}


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FeedbackEvent:
    """One immutable, content-addressed feedback event on a single AI output.

    Identity is :meth:`event_id` -- the ``sha256:`` content address of every
    semantically-identifying field (including ``created_utc`` and ``reviewer_id``),
    so two distinct clicks never collide while a byte-identical re-submission is a
    no-op in the store.
    """

    output_kind: OutputKind
    output_ref: str  # content address / id of the specific AI output rated
    verdict: FeedbackVerdict
    model_versions: Mapping[str, str]  # Prompt 13 provenance of the rated output
    record_hash: str | None = None  # dataset identity (links to Prompt 16 / training)
    reason: ReasonCode | None = None
    correction_text: str | None = None  # free-text correction
    corrected_value: Any | None = None  # structured ground truth (JSON-serialisable)
    context: Mapping[str, Any] = field(default_factory=dict)  # nucleus, original value, ...
    reviewer_id: str | None = None
    tenant_id: str | None = None
    created_utc: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        # Normalise enums passed as bare strings (ergonomic for callers / JSON).
        object.__setattr__(self, "output_kind", OutputKind(self.output_kind))
        object.__setattr__(self, "verdict", FeedbackVerdict(self.verdict))
        if self.reason is not None:
            object.__setattr__(self, "reason", ReasonCode(self.reason))
        object.__setattr__(self, "model_versions", _coerce_versions(self.model_versions))

    def _identity(self) -> dict[str, Any]:
        return {
            "output_kind": self.output_kind.value,
            "output_ref": self.output_ref,
            "verdict": self.verdict.value,
            "model_versions": dict(sorted(self.model_versions.items())),
            "record_hash": self.record_hash,
            "reason": self.reason.value if self.reason else None,
            "correction_text": self.correction_text,
            "corrected_value": self.corrected_value,
            "context": dict(self.context),
            "reviewer_id": self.reviewer_id,
            "tenant_id": self.tenant_id,
            "created_utc": self.created_utc,
        }

    def event_id(self) -> str:
        """Deterministic ``sha256:<hex>`` content address of this event."""

        return content_hash(self._identity())

    @property
    def is_override(self) -> bool:
        """True when the reviewer rejected the AI output (a thumbs-down)."""

        return self.verdict is FeedbackVerdict.DOWN

    @property
    def has_ground_truth(self) -> bool:
        """True when the reviewer supplied a structured corrected value."""

        return self.corrected_value is not None and self.record_hash is not None

    @property
    def is_correction(self) -> bool:
        """True when the reviewer both rejected the output and explained / fixed it."""

        return self.is_override and (
            self.corrected_value is not None or bool(self.correction_text)
        )

    def to_labeled_example(self) -> LabeledExample | None:
        """The labeled training example this event yields, or ``None``.

        Only an override that carries a structured ``corrected_value`` *and* a
        ``record_hash`` produces a label (the Prompt 16 store needs both a dataset
        identity and ground truth). Free-text-only feedback does not.
        """

        if not (self.is_override and self.has_ground_truth):
            return None
        assert self.record_hash is not None  # narrowed by has_ground_truth
        return LabeledExample(
            record_hash=self.record_hash,
            output_kind=self.output_kind,
            corrected_value=self.corrected_value,
            reason=self.reason,
            source_event_id=self.event_id(),
            model_versions=dict(self.model_versions),
            context=dict(self.context),
            created_utc=self.created_utc,
        )

    def to_active_learning_item(self) -> ActiveLearningItem | None:
        """The Prompt 16 queue item this event yields, or ``None``.

        A *bare override* -- thumbs down with a ``record_hash`` but no structured
        ground truth -- is a hard case that still needs a label, so it is routed
        to the active-learning queue. An override that already supplies a
        ``corrected_value`` becomes a :class:`LabeledExample` instead and is not
        re-queued.
        """

        if not self.is_override or self.record_hash is None or self.has_ground_truth:
            return None
        reason = self.reason.value if self.reason else "user_override"
        return ActiveLearningItem(
            record_hash=self.record_hash,
            reason=reason,
            severity=_OVERRIDE_SEVERITY,
            kinds=(reason,),
            created_utc=self.created_utc,
        )

    def as_dict(self) -> dict[str, Any]:
        out = self._identity()
        out["event_id"] = self.event_id()
        out["is_override"] = self.is_override
        out["is_correction"] = self.is_correction
        return out


@dataclass(frozen=True)
class LabeledExample:
    """A corrected training example -- the Prompt 16 labeled-example store sink.

    Produced from a :class:`FeedbackEvent` that carries a structured
    ``corrected_value`` for a known ``record_hash``. Carries the
    ``model_versions`` that produced the *original* (wrong) output, so the
    learning signal is attributable to the exact artifacts it corrects.
    """

    record_hash: str
    output_kind: OutputKind
    corrected_value: Any
    reason: ReasonCode | None
    source_event_id: str
    model_versions: Mapping[str, str]
    context: Mapping[str, Any] = field(default_factory=dict)
    created_utc: str = field(default_factory=_now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_hash": self.record_hash,
            "output_kind": OutputKind(self.output_kind).value,
            "corrected_value": self.corrected_value,
            "reason": ReasonCode(self.reason).value if self.reason else None,
            "source_event_id": self.source_event_id,
            "model_versions": dict(sorted(dict(self.model_versions).items())),
            "context": dict(self.context),
            "created_utc": self.created_utc,
        }


# --------------------------------------------------------------------------- #
# Usage / override analytics
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class UsageAnalytics:
    """Lightweight product analytics over a set of feedback events.

    ``by_output_kind`` answers *which features are used*; ``override_rate_by_kind``
    answers *where reviewers override*. Both feed the Prompt 17 A/B comparison and
    point the team at the model's weak spots.
    """

    n_events: int
    thumbs_up: int
    thumbs_down: int
    override_rate: float  # thumbs_down / n_events
    n_corrections: int  # overrides that produced a labeled example (ground truth)
    by_output_kind: Mapping[str, int]
    override_rate_by_kind: Mapping[str, float]
    reason_histogram: Mapping[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_events": self.n_events,
            "thumbs_up": self.thumbs_up,
            "thumbs_down": self.thumbs_down,
            "override_rate": self.override_rate,
            "n_corrections": self.n_corrections,
            "by_output_kind": dict(sorted(self.by_output_kind.items())),
            "override_rate_by_kind": dict(sorted(self.override_rate_by_kind.items())),
            "reason_histogram": dict(sorted(self.reason_histogram.items())),
        }


def usage_analytics(
    events: Iterable[FeedbackEvent], *, output_kind: OutputKind | str | None = None
) -> UsageAnalytics:
    """Roll up usage + override analytics for ``events`` (optionally one kind)."""

    only = OutputKind(output_kind) if output_kind is not None else None
    selected = [e for e in events if only is None or e.output_kind is only]

    n = len(selected)
    up = sum(1 for e in selected if not e.is_override)
    down = n - up
    corrections = sum(1 for e in selected if e.to_labeled_example() is not None)

    by_kind: dict[str, int] = {}
    down_by_kind: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for e in selected:
        kind = e.output_kind.value
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if e.is_override:
            down_by_kind[kind] = down_by_kind.get(kind, 0) + 1
        if e.reason is not None:
            reasons[e.reason.value] = reasons.get(e.reason.value, 0) + 1

    override_rate_by_kind = {
        kind: down_by_kind.get(kind, 0) / total for kind, total in by_kind.items()
    }
    return UsageAnalytics(
        n_events=n,
        thumbs_up=up,
        thumbs_down=down,
        override_rate=(down / n) if n else 0.0,
        n_corrections=corrections,
        by_output_kind=dict(sorted(by_kind.items())),
        override_rate_by_kind=dict(sorted(override_rate_by_kind.items())),
        reason_histogram=dict(sorted(reasons.items())),
    )


# --------------------------------------------------------------------------- #
# Storage backends
# --------------------------------------------------------------------------- #
class FeedbackStore(abc.ABC):
    """Append-only, idempotent persistence for feedback events.

    Implementations only INSERT; re-adding a byte-identical event (same
    :meth:`FeedbackEvent.event_id`) is a no-op. Insertion order is preserved.
    """

    @abc.abstractmethod
    def add_event(self, event: FeedbackEvent) -> None: ...

    @abc.abstractmethod
    def get_event(self, event_id: str) -> FeedbackEvent | None: ...

    @abc.abstractmethod
    def all_events(self) -> list[FeedbackEvent]: ...

    def events_for(self, record_hash: str) -> list[FeedbackEvent]:
        return [e for e in self.all_events() if e.record_hash == record_hash]


class InMemoryFeedbackStore(FeedbackStore):
    """Volatile, append-only store (tests / ephemeral runs). NOT durable."""

    def __init__(self) -> None:
        self._events: dict[str, FeedbackEvent] = {}

    def add_event(self, event: FeedbackEvent) -> None:
        self._events.setdefault(event.event_id(), event)  # idempotent insert

    def get_event(self, event_id: str) -> FeedbackEvent | None:
        return self._events.get(event_id)

    def all_events(self) -> list[FeedbackEvent]:
        return list(self._events.values())


class SqlAlchemyFeedbackStore(FeedbackStore):
    """Durable, append-only feedback store over any SQLAlchemy engine.

    The same implementation drives **PostgreSQL** in production (pass the app's
    ``DATABASE_URL``) and SQLite in tests (``sqlite://`` in-memory). One table is
    self-created (``<prefix>_events``); writes are INSERT-only and idempotent on
    ``event_id``. SQLAlchemy is imported lazily so the in-memory store and the
    dataclasses stay usable in minimal environments.
    """

    def __init__(self, engine_or_url: Any, *, table_prefix: str = "ai_feedback") -> None:
        import sqlalchemy as sa

        self._sa = sa
        self._engine = (
            sa.create_engine(engine_or_url) if isinstance(engine_or_url, str) else engine_or_url
        )
        self._meta = sa.MetaData()
        self._events = sa.Table(
            f"{table_prefix}_events",
            self._meta,
            sa.Column("seq", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("event_id", sa.String(128), unique=True, nullable=False, index=True),
            sa.Column("output_kind", sa.String(64), nullable=False),
            sa.Column("output_ref", sa.String(512), nullable=False),
            sa.Column("verdict", sa.String(16), nullable=False),
            sa.Column("record_hash", sa.String(128), nullable=True, index=True),
            sa.Column("reason", sa.String(64), nullable=True),
            sa.Column("correction_text", sa.Text, nullable=True),
            sa.Column("corrected_value", sa.JSON, nullable=True),
            sa.Column("model_versions", sa.JSON, nullable=False),
            sa.Column("context", sa.JSON, nullable=False),
            sa.Column("reviewer_id", sa.String(128), nullable=True),
            sa.Column("tenant_id", sa.String(128), nullable=True),
            sa.Column("created_utc", sa.String(64), nullable=False),
        )
        self._meta.create_all(self._engine, checkfirst=True)

    def add_event(self, event: FeedbackEvent) -> None:
        if self.get_event(event.event_id()) is not None:
            return  # idempotent: byte-identical event already stored
        with self._engine.begin() as conn:
            conn.execute(
                self._events.insert().values(
                    event_id=event.event_id(),
                    output_kind=event.output_kind.value,
                    output_ref=event.output_ref,
                    verdict=event.verdict.value,
                    record_hash=event.record_hash,
                    reason=event.reason.value if event.reason else None,
                    correction_text=event.correction_text,
                    corrected_value=event.corrected_value,
                    model_versions=dict(event.model_versions),
                    context=dict(event.context),
                    reviewer_id=event.reviewer_id,
                    tenant_id=event.tenant_id,
                    created_utc=event.created_utc,
                )
            )

    def get_event(self, event_id: str) -> FeedbackEvent | None:
        sa = self._sa
        with self._engine.connect() as conn:
            row = (
                conn.execute(
                    sa.select(self._events).where(self._events.c.event_id == event_id)
                )
                .mappings()
                .first()
            )
        return self._row_to_event(row) if row is not None else None

    def all_events(self) -> list[FeedbackEvent]:
        sa = self._sa
        with self._engine.connect() as conn:
            rows = (
                conn.execute(sa.select(self._events).order_by(self._events.c.seq))
                .mappings()
                .all()
            )
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: Mapping[str, Any]) -> FeedbackEvent:
        return FeedbackEvent(
            output_kind=OutputKind(row["output_kind"]),
            output_ref=row["output_ref"],
            verdict=FeedbackVerdict(row["verdict"]),
            model_versions=dict(row["model_versions"]),
            record_hash=row["record_hash"],
            reason=ReasonCode(row["reason"]) if row["reason"] else None,
            correction_text=row["correction_text"],
            corrected_value=row["corrected_value"],
            context=dict(row["context"]),
            reviewer_id=row["reviewer_id"],
            tenant_id=row["tenant_id"],
            created_utc=row["created_utc"],
        )


# --------------------------------------------------------------------------- #
# The collector (the single intake)
# --------------------------------------------------------------------------- #
class FeedbackCollector:
    """The single feedback intake: persist events and fan out to the sinks.

    Wraps a :class:`FeedbackStore` and (optionally) a Prompt 16
    :class:`~moltrace.spectroscopy.ai.finetune.ActiveLearningQueue`. Each
    :meth:`capture` call stores an immutable event and -- when the event is a
    bare override -- enqueues a hard case for annotation. Corrections that carry
    ground truth surface via :meth:`labeled_examples`.
    """

    def __init__(
        self,
        store: FeedbackStore | None = None,
        *,
        queue: ActiveLearningQueue | None = None,
        clock: Callable[[], str] = _now_iso,
    ) -> None:
        self.store = store if store is not None else InMemoryFeedbackStore()
        self.queue = queue
        self._clock = clock

    def capture(
        self,
        *,
        output_kind: OutputKind | str,
        output_ref: str,
        verdict: FeedbackVerdict | str,
        model_versions: Mapping[str, str],
        record_hash: str | None = None,
        reason: ReasonCode | str | None = None,
        correction_text: str | None = None,
        corrected_value: Any | None = None,
        context: Mapping[str, Any] | None = None,
        reviewer_id: str | None = None,
        tenant_id: str | None = None,
        created_utc: str | None = None,
    ) -> FeedbackEvent:
        """Record one feedback event and fan it out to the configured sinks."""

        event = FeedbackEvent(
            output_kind=OutputKind(output_kind),
            output_ref=output_ref,
            verdict=FeedbackVerdict(verdict),
            model_versions=_coerce_versions(model_versions),
            record_hash=record_hash,
            reason=ReasonCode(reason) if reason is not None else None,
            correction_text=correction_text,
            corrected_value=corrected_value,
            context=dict(context or {}),
            reviewer_id=reviewer_id,
            tenant_id=tenant_id,
            created_utc=created_utc if created_utc is not None else self._clock(),
        )
        self.store.add_event(event)
        if self.queue is not None:
            item = event.to_active_learning_item()
            if item is not None:
                self.queue.enqueue(item)
        return event

    def labeled_examples(
        self, *, output_kind: OutputKind | str | None = None
    ) -> list[LabeledExample]:
        """Every correction (with ground truth) as a Prompt 16 labeled example."""

        only = OutputKind(output_kind) if output_kind is not None else None
        out: list[LabeledExample] = []
        for event in self.store.all_events():
            if only is not None and event.output_kind is not only:
                continue
            example = event.to_labeled_example()
            if example is not None:
                out.append(example)
        return out

    def analytics(self, *, output_kind: OutputKind | str | None = None) -> UsageAnalytics:
        """Usage + override analytics over all captured events."""

        return usage_analytics(self.store.all_events(), output_kind=output_kind)

    def events(self) -> Sequence[FeedbackEvent]:
        """All captured events, in insertion order."""

        return self.store.all_events()
