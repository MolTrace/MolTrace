"""Versioned, append-only model registry (Prompt 13, Roadmap Layers 1-3).

SpectraCheck must never depend on a single hard-coded predictor.  This module
tracks *every* artifact that can produce or transform a prediction so that any
result is reproducible bit-for-bit, years later, from the registry + lineage --
and so a reviewer can see WHICH artifact produced each number and why one was
chosen over another.  Provenance as a feature, not an afterthought.

Tracked artifacts (the :class:`ModelRole` vocabulary):

* ``nmrnet_checkpoint`` -- per-nucleus NMRNet weights + SHA-256 (Prompt 6),
* ``hose_kb``           -- HOSE-code KB build id + source-DB snapshot hash (Prompt 6),
* ``lora_adapter``      -- LoRA fine-tuned adapter + parent base id (Prompt 15),
* ``embedding_model``   -- spectral embedding model id (Prompt 8).

Each :class:`ModelEntry` carries a ``semantic_version``, ``artifact_sha256``,
``training_data_lineage`` (dataset snapshot hash + row count), ``created_utc``,
a ``metric_snapshot`` (the Phase-0 metric vector at registration -- see
:mod:`moltrace.spectroscopy.infra.eval`), and a lifecycle ``status`` in
{candidate, shadow, production, retired}.

The registry is **append-only**: entries are immutable, no field is ever
hard-edited, and a new ``semantic_version`` supersedes an older one.  Lifecycle
changes are recorded as an append-only log of :class:`StatusTransition` events
(never an in-place mutation), so the full "who was production when, and what
replaced it" history is reconstructable from the log alone.

Persistence is pluggable behind :class:`RegistryStore`:

* :class:`InMemoryRegistryStore` -- zero-dependency, for tests / ephemeral use,
* :class:`SqlAlchemyRegistryStore` -- durable; the same store drives PostgreSQL
  in production (point it at ``DATABASE_URL``) and SQLite in tests.  In a
  regulated deployment, harden the tables with ``REVOKE UPDATE, DELETE`` + an
  INSERT-only trigger so append-only is enforced at the database layer too.

No artifacts/weights/DB dumps are stored here -- only content addresses
(SHA-256) and lineage metadata.
"""

from __future__ import annotations

import abc
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from moltrace.spectroscopy.infra.contract import content_hash

__all__ = [
    "AppendOnlyViolation",
    "InMemoryRegistryStore",
    "InvalidStatusTransition",
    "ModelEntry",
    "ModelLineage",
    "ModelRegistry",
    "ModelRole",
    "ModelStatus",
    "RegistryError",
    "RegistryStore",
    "SqlAlchemyRegistryStore",
    "StatusTransition",
    "TrainingDataLineage",
    "build_model_entry",
]


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
class ModelRole(StrEnum):
    """The role an artifact plays in the inference pipeline."""

    NMRNET_CHECKPOINT = "nmrnet_checkpoint"  # Layer 1 pretrained (Prompt 6)
    HOSE_KB = "hose_kb"  # deterministic fallback (Prompt 6)
    LORA_ADAPTER = "lora_adapter"  # Layer 3 fine-tuned (Prompt 15)
    EMBEDDING_MODEL = "embedding_model"  # spectral embedding (Prompt 8)


class ModelStatus(StrEnum):
    """Lifecycle status of a registered artifact."""

    CANDIDATE = "candidate"
    SHADOW = "shadow"
    PRODUCTION = "production"
    RETIRED = "retired"


# Allowed lifecycle transitions. RETIRED is terminal. Same-status is rejected.
_ALLOWED_TRANSITIONS: dict[ModelStatus, frozenset[ModelStatus]] = {
    ModelStatus.CANDIDATE: frozenset(
        {ModelStatus.SHADOW, ModelStatus.PRODUCTION, ModelStatus.RETIRED}
    ),
    ModelStatus.SHADOW: frozenset(
        {ModelStatus.CANDIDATE, ModelStatus.PRODUCTION, ModelStatus.RETIRED}
    ),
    ModelStatus.PRODUCTION: frozenset({ModelStatus.SHADOW, ModelStatus.RETIRED}),
    ModelStatus.RETIRED: frozenset(),
}


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class RegistryError(RuntimeError):
    """Base class for registry errors."""


class AppendOnlyViolation(RegistryError):
    """Raised when a write would mutate or overwrite an existing entry."""


class InvalidStatusTransition(RegistryError):
    """Raised when a status change is not a permitted lifecycle transition."""


# --------------------------------------------------------------------------- #
# Time helpers (real UTC clock; injectable for deterministic tests)
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _normalize_metrics(metrics: Any) -> dict[str, float]:
    """Coerce a MetricVector / mapping / None into a plain ``{str: float}`` dict.

    Drops ``None`` values so a snapshot records only the metrics actually
    measured at registration (mirrors :meth:`MetricVector.as_dict`).
    """

    if metrics is None:
        return {}
    if hasattr(metrics, "as_dict"):
        metrics = metrics.as_dict()
    if not isinstance(metrics, Mapping):
        raise TypeError("metric_snapshot must be a MetricVector or a mapping")
    out: dict[str, float] = {}
    for key, value in metrics.items():
        if value is None:
            continue
        out[str(key)] = float(value)
    return out


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TrainingDataLineage:
    """Where an artifact's training/build data came from, content-addressed."""

    dataset_snapshot_hash: str  # e.g. "sha256:..." from infra.versioning.dataset_hash
    row_count: int
    dataset_tag: str | None = None
    source: str | None = None  # e.g. "nmrshiftdb2", "qm9-nmr"
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_snapshot_hash": self.dataset_snapshot_hash,
            "row_count": int(self.row_count),
            "dataset_tag": self.dataset_tag,
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ModelEntry:
    """One immutable registry entry for a single artifact version.

    Identity is ``model_id`` (globally unique, append-only). ``status`` here is
    the *declared* status at registration; the authoritative current status is
    derived from the append-only :class:`StatusTransition` log.
    """

    model_id: str
    role: ModelRole
    semantic_version: str
    artifact_sha256: str
    training_data_lineage: TrainingDataLineage
    created_utc: datetime
    metric_snapshot: dict[str, float] = field(default_factory=dict)
    nucleus: str | None = None  # per-nucleus for NMRNet / LoRA; None otherwise
    parent_base_id: str | None = None  # for LoRA: the base it adapts (model_id)
    confidence_band_ppm: float | None = None  # LoRA: validated max uncertainty (ppm)
    status: ModelStatus = ModelStatus.CANDIDATE
    extra: dict[str, Any] = field(default_factory=dict)

    def _provenance_dict(self) -> dict[str, Any]:
        """The immutable, identity-defining fields, as JSON primitives.

        Excludes ``status`` (which evolves via the transition log): the artifact
        *identity* must not change when it is promoted or retired.
        """

        return {
            "model_id": self.model_id,
            "role": self.role.value,
            "semantic_version": self.semantic_version,
            "artifact_sha256": self.artifact_sha256,
            "training_data_lineage": self.training_data_lineage.as_dict(),
            "created_utc": _iso(self.created_utc),
            "metric_snapshot": dict(sorted(self.metric_snapshot.items())),
            "nucleus": self.nucleus,
            "parent_base_id": self.parent_base_id,
            "confidence_band_ppm": self.confidence_band_ppm,
            "extra": self.extra,
        }

    def entry_hash(self) -> str:
        """Deterministic ``sha256:<hex>`` content address of this entry."""

        return content_hash(self._provenance_dict())


@dataclass(frozen=True)
class StatusTransition:
    """One append-only lifecycle event for a model_id.

    ``from_status is None`` marks the initial registration event.
    """

    model_id: str
    from_status: ModelStatus | None
    to_status: ModelStatus
    transitioned_utc: datetime
    reason: str | None = None


@dataclass(frozen=True)
class ModelLineage:
    """The reviewer-facing provenance view returned by :meth:`ModelRegistry.list_lineage`."""

    entry: ModelEntry
    current_status: ModelStatus
    training_data_lineage: TrainingDataLineage
    status_history: tuple[StatusTransition, ...]
    parent_base_id: str | None
    supersedes: str | None  # model_id this entry replaced on promotion to production
    superseded_by: str | None  # model_id that replaced this one


# --------------------------------------------------------------------------- #
# Storage backends
# --------------------------------------------------------------------------- #
class RegistryStore(abc.ABC):
    """Append-only persistence for entries + the status-transition log.

    Implementations only INSERT; they never UPDATE or DELETE. Insertion order is
    preserved (it defines the lifecycle timeline).
    """

    @abc.abstractmethod
    def add_entry(self, entry: ModelEntry) -> None: ...

    @abc.abstractmethod
    def get_entry(self, model_id: str) -> ModelEntry | None: ...

    @abc.abstractmethod
    def all_entries(self) -> list[ModelEntry]: ...

    @abc.abstractmethod
    def add_transition(self, transition: StatusTransition) -> None: ...

    @abc.abstractmethod
    def all_transitions(self) -> list[StatusTransition]: ...

    def transitions_for(self, model_id: str) -> list[StatusTransition]:
        return [t for t in self.all_transitions() if t.model_id == model_id]


class InMemoryRegistryStore(RegistryStore):
    """Volatile store (tests / ephemeral runs). NOT durable storage."""

    def __init__(self) -> None:
        self._entries: dict[str, ModelEntry] = {}
        self._transitions: list[StatusTransition] = []

    def add_entry(self, entry: ModelEntry) -> None:
        self._entries[entry.model_id] = entry

    def get_entry(self, model_id: str) -> ModelEntry | None:
        return self._entries.get(model_id)

    def all_entries(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def add_transition(self, transition: StatusTransition) -> None:
        self._transitions.append(transition)

    def all_transitions(self) -> list[StatusTransition]:
        return list(self._transitions)


class SqlAlchemyRegistryStore(RegistryStore):
    """Durable, append-only store over any SQLAlchemy engine.

    The same implementation drives **PostgreSQL** in production (pass the app's
    ``DATABASE_URL``) and SQLite in tests (``sqlite://`` in-memory). Two tables
    are self-created (``<prefix>_registry`` and ``<prefix>_status_log``); writes
    are INSERT-only. SQLAlchemy is imported lazily so the in-memory store and the
    dataclasses stay usable in minimal environments.
    """

    def __init__(self, engine_or_url: Any, *, table_prefix: str = "ai_model") -> None:
        import sqlalchemy as sa

        self._sa = sa
        self._engine = (
            sa.create_engine(engine_or_url) if isinstance(engine_or_url, str) else engine_or_url
        )
        self._meta = sa.MetaData()
        self._registry = sa.Table(
            f"{table_prefix}_registry",
            self._meta,
            sa.Column("seq", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("model_id", sa.String(512), unique=True, nullable=False, index=True),
            sa.Column("role", sa.String(64), nullable=False),
            sa.Column("nucleus", sa.String(16), nullable=True),
            sa.Column("semantic_version", sa.String(64), nullable=False),
            sa.Column("artifact_sha256", sa.String(128), nullable=False),
            sa.Column("training_data_lineage", sa.JSON, nullable=False),
            sa.Column("created_utc", sa.String(64), nullable=False),
            sa.Column("metric_snapshot", sa.JSON, nullable=False),
            sa.Column("parent_base_id", sa.String(512), nullable=True),
            sa.Column("confidence_band_ppm", sa.Float, nullable=True),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("extra", sa.JSON, nullable=False),
        )
        self._status_log = sa.Table(
            f"{table_prefix}_status_log",
            self._meta,
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("model_id", sa.String(512), nullable=False, index=True),
            sa.Column("from_status", sa.String(32), nullable=True),
            sa.Column("to_status", sa.String(32), nullable=False),
            sa.Column("transitioned_utc", sa.String(64), nullable=False),
            sa.Column("reason", sa.Text, nullable=True),
        )
        self._meta.create_all(self._engine, checkfirst=True)

    # -- entries -------------------------------------------------------------- #
    def add_entry(self, entry: ModelEntry) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                self._registry.insert().values(
                    model_id=entry.model_id,
                    role=entry.role.value,
                    nucleus=entry.nucleus,
                    semantic_version=entry.semantic_version,
                    artifact_sha256=entry.artifact_sha256,
                    training_data_lineage=entry.training_data_lineage.as_dict(),
                    created_utc=_iso(entry.created_utc),
                    metric_snapshot=dict(entry.metric_snapshot),
                    parent_base_id=entry.parent_base_id,
                    confidence_band_ppm=entry.confidence_band_ppm,
                    status=entry.status.value,
                    extra=dict(entry.extra),
                )
            )

    def get_entry(self, model_id: str) -> ModelEntry | None:
        sa = self._sa
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.select(self._registry).where(self._registry.c.model_id == model_id)
            ).mappings().first()
        return self._row_to_entry(row) if row is not None else None

    def all_entries(self) -> list[ModelEntry]:
        sa = self._sa
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(self._registry).order_by(self._registry.c.seq)
            ).mappings().all()
        return [self._row_to_entry(r) for r in rows]

    def _row_to_entry(self, row: Mapping[str, Any]) -> ModelEntry:
        lineage = dict(row["training_data_lineage"])
        return ModelEntry(
            model_id=row["model_id"],
            role=ModelRole(row["role"]),
            semantic_version=row["semantic_version"],
            artifact_sha256=row["artifact_sha256"],
            training_data_lineage=TrainingDataLineage(
                dataset_snapshot_hash=lineage["dataset_snapshot_hash"],
                row_count=int(lineage["row_count"]),
                dataset_tag=lineage.get("dataset_tag"),
                source=lineage.get("source"),
                notes=lineage.get("notes"),
            ),
            created_utc=_parse_iso(row["created_utc"]),
            metric_snapshot={k: float(v) for k, v in dict(row["metric_snapshot"]).items()},
            nucleus=row["nucleus"],
            parent_base_id=row["parent_base_id"],
            confidence_band_ppm=row["confidence_band_ppm"],
            status=ModelStatus(row["status"]),
            extra=dict(row["extra"]),
        )

    # -- transitions ---------------------------------------------------------- #
    def add_transition(self, transition: StatusTransition) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                self._status_log.insert().values(
                    model_id=transition.model_id,
                    from_status=(
                        transition.from_status.value if transition.from_status else None
                    ),
                    to_status=transition.to_status.value,
                    transitioned_utc=_iso(transition.transitioned_utc),
                    reason=transition.reason,
                )
            )

    def all_transitions(self) -> list[StatusTransition]:
        sa = self._sa
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.select(self._status_log).order_by(self._status_log.c.id)
            ).mappings().all()
        return [
            StatusTransition(
                model_id=r["model_id"],
                from_status=ModelStatus(r["from_status"]) if r["from_status"] else None,
                to_status=ModelStatus(r["to_status"]),
                transitioned_utc=_parse_iso(r["transitioned_utc"]),
                reason=r["reason"],
            )
            for r in rows
        ]


# --------------------------------------------------------------------------- #
# Entry construction helper
# --------------------------------------------------------------------------- #
def build_model_entry(
    *,
    role: ModelRole,
    semantic_version: str,
    artifact_sha256: str,
    training_data_lineage: TrainingDataLineage,
    metric_snapshot: Any = None,
    nucleus: str | None = None,
    parent_base_id: str | None = None,
    confidence_band_ppm: float | None = None,
    status: ModelStatus = ModelStatus.CANDIDATE,
    model_id: str | None = None,
    created_utc: datetime | None = None,
    extra: Mapping[str, Any] | None = None,
) -> ModelEntry:
    """Build a :class:`ModelEntry`, defaulting ``model_id`` and ``created_utc``.

    The default ``model_id`` -- ``"<role>:<nucleus|all>:<semantic_version>"`` --
    makes re-registering the same role/nucleus/version an append-only violation,
    which is the desired behaviour (a version is registered exactly once).
    """

    role = ModelRole(role)
    status = ModelStatus(status)
    if model_id is None:
        model_id = f"{role.value}:{nucleus or 'all'}:{semantic_version}"
    return ModelEntry(
        model_id=model_id,
        role=role,
        semantic_version=semantic_version,
        artifact_sha256=artifact_sha256,
        training_data_lineage=training_data_lineage,
        created_utc=created_utc or _now(),
        metric_snapshot=_normalize_metrics(metric_snapshot),
        nucleus=nucleus,
        parent_base_id=parent_base_id,
        confidence_band_ppm=confidence_band_ppm,
        status=status,
        extra=dict(extra or {}),
    )


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #
class ModelRegistry:
    """Append-only, versioned registry over a pluggable :class:`RegistryStore`.

    Entries are immutable; lifecycle changes are appended as
    :class:`StatusTransition` events. Promoting an artifact to ``production``
    auto-supersedes the incumbent production artifact for the same
    (role, nucleus), and that supersession is reconstructable from the log.
    """

    def __init__(
        self,
        store: RegistryStore | None = None,
        *,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.store = store if store is not None else InMemoryRegistryStore()
        self._clock = clock

    # -- registration --------------------------------------------------------- #
    def register(self, entry: ModelEntry) -> ModelEntry:
        """Append ``entry`` to the registry. Raises on any overwrite (append-only)."""

        if self.store.get_entry(entry.model_id) is not None:
            raise AppendOnlyViolation(
                f"model_id {entry.model_id!r} already registered; the registry is "
                "append-only -- register a new semantic_version instead of editing."
            )
        self.store.add_entry(entry)
        self.store.add_transition(
            StatusTransition(
                model_id=entry.model_id,
                from_status=None,
                to_status=entry.status,
                transitioned_utc=entry.created_utc,
                reason="registered",
            )
        )
        return entry

    def register_artifact(self, **kwargs: Any) -> ModelEntry:
        """Convenience: :func:`build_model_entry` then :meth:`register`."""

        return self.register(build_model_entry(**kwargs))

    # -- lookups -------------------------------------------------------------- #
    def get(self, model_id: str) -> ModelEntry:
        entry = self.store.get_entry(model_id)
        if entry is None:
            raise KeyError(f"unknown model_id: {model_id!r}")
        return entry

    def current_status(self, model_id: str) -> ModelStatus:
        self.get(model_id)  # KeyError if unknown
        transitions = self.store.transitions_for(model_id)
        if not transitions:  # pragma: no cover - register always logs one
            return self.get(model_id).status
        return transitions[-1].to_status

    def list_entries(
        self,
        *,
        role: ModelRole | None = None,
        nucleus: str | None = None,
        status: ModelStatus | None = None,
    ) -> list[ModelEntry]:
        out = []
        for entry in self.store.all_entries():
            if role is not None and entry.role != role:
                continue
            if nucleus is not None and entry.nucleus != nucleus:
                continue
            if status is not None and self.current_status(entry.model_id) != status:
                continue
            out.append(entry)
        return out

    def resolve(self, role: ModelRole, nucleus: str | None = None) -> ModelEntry | None:
        """Return the current ``production`` artifact for ``(role, nucleus)``.

        There is at most one (promotion auto-retires the incumbent); if several
        somehow match, the most recently promoted wins.
        """

        role = ModelRole(role)
        candidates = [
            e
            for e in self.store.all_entries()
            if e.role == role
            and e.nucleus == nucleus
            and self.current_status(e.model_id) == ModelStatus.PRODUCTION
        ]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        promoted_at = self._production_promotion_index()
        return max(candidates, key=lambda e: promoted_at.get(e.model_id, -1))

    # -- lifecycle ------------------------------------------------------------ #
    def set_status(
        self, model_id: str, to_status: ModelStatus, *, reason: str | None = None
    ) -> StatusTransition:
        """Append a validated lifecycle transition for ``model_id``.

        Promoting to ``production`` first records this artifact's promotion, then
        retires the prior production artifact for the same (role, nucleus) with a
        ``superseded by`` reason -- both as appended events.
        """

        to_status = ModelStatus(to_status)
        entry = self.get(model_id)
        current = self.current_status(model_id)
        if to_status not in _ALLOWED_TRANSITIONS[current]:
            allowed = ", ".join(sorted(s.value for s in _ALLOWED_TRANSITIONS[current])) or "(none)"
            raise InvalidStatusTransition(
                f"{model_id!r}: cannot go {current.value} -> {to_status.value} "
                f"(allowed from {current.value}: {allowed})"
            )

        incumbent = (
            self.resolve(entry.role, entry.nucleus)
            if to_status == ModelStatus.PRODUCTION
            else None
        )

        transition = StatusTransition(
            model_id=model_id,
            from_status=current,
            to_status=to_status,
            transitioned_utc=self._clock(),
            reason=reason,
        )
        self.store.add_transition(transition)

        # Auto-supersede the prior production artifact (append-only retire event).
        if incumbent is not None and incumbent.model_id != model_id:
            self.store.add_transition(
                StatusTransition(
                    model_id=incumbent.model_id,
                    from_status=ModelStatus.PRODUCTION,
                    to_status=ModelStatus.RETIRED,
                    transitioned_utc=self._clock(),
                    reason=f"superseded by {model_id}",
                )
            )
        return transition

    def promote(self, model_id: str, *, reason: str | None = None) -> StatusTransition:
        """Shorthand for ``set_status(model_id, PRODUCTION)``."""

        return self.set_status(model_id, ModelStatus.PRODUCTION, reason=reason)

    def retire(self, model_id: str, *, reason: str | None = None) -> StatusTransition:
        """Shorthand for ``set_status(model_id, RETIRED)``."""

        return self.set_status(model_id, ModelStatus.RETIRED, reason=reason)

    # -- lineage -------------------------------------------------------------- #
    def list_lineage(self, model_id: str) -> ModelLineage:
        """Full provenance view: lineage + status history + supersession links."""

        entry = self.get(model_id)
        history = tuple(self.store.transitions_for(model_id))
        supersedes, superseded_by = self._supersession_links(model_id)
        return ModelLineage(
            entry=entry,
            current_status=self.current_status(model_id),
            training_data_lineage=entry.training_data_lineage,
            status_history=history,
            parent_base_id=entry.parent_base_id,
            supersedes=supersedes,
            superseded_by=superseded_by,
        )

    def model_provenance(self, model_id: str) -> dict[str, str]:
        """``{model_id: artifact_sha256}`` for a single entry (router composes these)."""

        entry = self.get(model_id)
        return {entry.model_id: entry.artifact_sha256}

    # -- internal: replay the append-only log -------------------------------- #
    def _role_nucleus(self, model_id: str) -> tuple[ModelRole, str | None]:
        entry = self.store.get_entry(model_id)
        if entry is None:  # pragma: no cover - transitions always have an entry
            raise KeyError(model_id)
        return entry.role, entry.nucleus

    def _production_promotion_index(self) -> dict[str, int]:
        """Map model_id -> index of its most recent promotion-to-production event."""

        index: dict[str, int] = {}
        for i, t in enumerate(self.store.all_transitions()):
            if t.to_status == ModelStatus.PRODUCTION:
                index[t.model_id] = i
        return index

    def _supersession_links(self, model_id: str) -> tuple[str | None, str | None]:
        """Derive (supersedes, superseded_by) for ``model_id`` from the log.

        Replays every transition in order, tracking the production holder per
        (role, nucleus). When model X becomes production while Y held it, X
        supersedes Y. Purely a function of the append-only log.
        """

        holder: dict[tuple[ModelRole, str | None], str] = {}
        supersedes: str | None = None
        superseded_by: str | None = None
        for t in self.store.all_transitions():
            key = self._role_nucleus(t.model_id)
            if t.to_status == ModelStatus.PRODUCTION:
                prev = holder.get(key)
                if prev is not None and prev != t.model_id:
                    if t.model_id == model_id:
                        supersedes = prev
                    if prev == model_id:
                        superseded_by = t.model_id
                holder[key] = t.model_id
            elif holder.get(key) == t.model_id:
                # left production (retired/shadow) without a direct replacement
                holder.pop(key, None)
        return supersedes, superseded_by
