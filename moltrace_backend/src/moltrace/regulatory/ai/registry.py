"""Versioned registry of regulatory rule-engines and AI artifacts (Prompt 13, Roadmap Layers 1-3).

Deterministic-first: regulatory math is **never** produced by a stochastic model.
This registry pins, for every artifact that can touch a regulatory output, the exact
version + provenance so a result is reproducible and defensible years later -- the
substrate the :class:`~moltrace.regulatory.ai.router.Router` and the Annex 22 audit
wrapper (Prompt 12) stand on.

Two artifact families share one :class:`ArtifactKind` vocabulary:

* the **deterministic rule-engines** -- which ICH/FDA revision a formula set encodes
  (e.g. ``ICH Q3C(R8)``, ``ICH M7(R2)``, ``FDA Nitrosamine Rev 2``). These own the
  quantitative + classification path and carry a ``rule_set_version`` content address.
* the **AI artifacts** used only for narrative drafting / retrieval / triage -- LLM
  prompt+template versions, the RAG index version (Prompt 14), and fine-tuned narrative
  adapters (Prompt 15). These never touch a number.

Each :class:`RegistryEntry` ties a ``semver`` to its ``source_guidance`` +
``effective_date``, a ``code_sha`` (the git revision that implements it), the
``rule_set_version`` content address (rule-engines only), a ``validation_doc_id``
linking to the GxP validation record (the GAMP 5 / CSV package, Prompt 21), and a
lifecycle ``status``.

The registry is **append-only**: entries are immutable, no field is ever hard-edited,
and a new ``semver`` supersedes an older one. Lifecycle changes are recorded as an
append-only log of :class:`StatusTransition` events (never an in-place mutation), so the
full "which guidance revision was production when" history is reconstructable from the
log alone. Persistence is in-memory here (tests / ephemeral use); the store can be made
durable behind the same API, exactly as the spectroscopy model registry is.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from moltrace.regulatory.infra.versioning import (
    content_hash,
    current_git_sha,
    rule_set_version,
)

__all__ = [
    "AppendOnlyViolation",
    "ArtifactKind",
    "ArtifactStatus",
    "InvalidStatusTransition",
    "Registry",
    "RegistryEntry",
    "RegistryError",
    "StatusTransition",
    "build_registry_entry",
    "default_regulatory_registry",
]


# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #
class ArtifactKind(StrEnum):
    """What an artifact is. Only ``RULE_ENGINE`` may produce a number."""

    RULE_ENGINE = "rule_engine"  # deterministic formula set tied to a guidance revision
    LLM_PROMPT = "llm_prompt"  # prompt / template version (narrative drafting only)
    RAG_INDEX = "rag_index"  # retrieval index version (Prompt 14)
    NARRATIVE_ADAPTER = "narrative_adapter"  # fine-tuned narrative adapter (Prompt 15)


class ArtifactStatus(StrEnum):
    """Lifecycle status of a registered artifact version."""

    CANDIDATE = "candidate"
    SHADOW = "shadow"
    PRODUCTION = "production"
    RETIRED = "retired"


# Allowed lifecycle transitions. RETIRED is terminal; same-status is rejected.
_ALLOWED_TRANSITIONS: dict[ArtifactStatus, frozenset[ArtifactStatus]] = {
    ArtifactStatus.CANDIDATE: frozenset(
        {ArtifactStatus.SHADOW, ArtifactStatus.PRODUCTION, ArtifactStatus.RETIRED}
    ),
    ArtifactStatus.SHADOW: frozenset(
        {ArtifactStatus.CANDIDATE, ArtifactStatus.PRODUCTION, ArtifactStatus.RETIRED}
    ),
    ArtifactStatus.PRODUCTION: frozenset({ArtifactStatus.SHADOW, ArtifactStatus.RETIRED}),
    ArtifactStatus.RETIRED: frozenset(),
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
# Time (real UTC clock; injectable for deterministic tests)
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RegistryEntry:
    """One immutable registry entry for a single artifact version.

    Identity is ``entry_id`` (globally unique, append-only). ``status`` here is the
    *declared* status at registration; the authoritative current status is derived from
    the append-only :class:`StatusTransition` log on the :class:`Registry`.

    For a ``RULE_ENGINE`` entry, ``source_guidance`` + ``effective_date`` name the exact
    ICH/FDA revision the formula set encodes and ``rule_set_version`` is the content
    address of that encoded rule-set; ``validation_doc_id`` links to its GxP validation
    record. AI artifacts (prompt / RAG index / adapter) leave ``rule_set_version`` and
    ``source_guidance`` unset -- they never produce a number.
    """

    entry_id: str
    kind: ArtifactKind
    name: str
    semver: str
    code_sha: str
    source_guidance: str | None = None
    effective_date: str | None = None
    rule_set_version: str | None = None
    validation_doc_id: str | None = None
    status: ArtifactStatus = ArtifactStatus.CANDIDATE
    created_utc: datetime = field(default_factory=_now)
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def _provenance_dict(self) -> dict[str, Any]:
        """The immutable, identity-defining fields (excludes the evolving ``status``)."""

        return {
            "entry_id": self.entry_id,
            "kind": self.kind.value,
            "name": self.name,
            "semver": self.semver,
            "code_sha": self.code_sha,
            "source_guidance": self.source_guidance,
            "effective_date": self.effective_date,
            "rule_set_version": self.rule_set_version,
            "validation_doc_id": self.validation_doc_id,
            "created_utc": _iso(self.created_utc),
            "notes": self.notes,
            "extra": self.extra,
        }

    def entry_hash(self) -> str:
        """Deterministic ``sha256:<hex>`` content address of this entry."""

        return content_hash(self._provenance_dict())

    def as_dict(self) -> dict[str, Any]:
        out = self._provenance_dict()
        out["status"] = self.status.value
        return out


@dataclass(frozen=True)
class StatusTransition:
    """One append-only lifecycle event for an ``entry_id``.

    ``from_status is None`` marks the initial registration event.
    """

    entry_id: str
    from_status: ArtifactStatus | None
    to_status: ArtifactStatus
    transitioned_utc: datetime
    reason: str | None = None


# --------------------------------------------------------------------------- #
# Entry construction helper
# --------------------------------------------------------------------------- #
def build_registry_entry(
    *,
    kind: ArtifactKind,
    name: str,
    semver: str,
    code_sha: str | None = None,
    source_guidance: str | None = None,
    effective_date: str | None = None,
    rule_set_version: str | None = None,
    validation_doc_id: str | None = None,
    status: ArtifactStatus = ArtifactStatus.CANDIDATE,
    entry_id: str | None = None,
    created_utc: datetime | None = None,
    notes: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> RegistryEntry:
    """Build a :class:`RegistryEntry`, defaulting ``entry_id`` and ``code_sha``.

    The default ``entry_id`` -- ``"<kind>:<name>:<semver>"`` -- makes re-registering the
    same kind/name/version an append-only violation, which is the desired behaviour (a
    version is registered exactly once). ``code_sha`` defaults to the current git SHA.
    """

    kind = ArtifactKind(kind)
    status = ArtifactStatus(status)
    if entry_id is None:
        entry_id = f"{kind.value}:{name}:{semver}"
    return RegistryEntry(
        entry_id=entry_id,
        kind=kind,
        name=name,
        semver=semver,
        code_sha=code_sha if code_sha is not None else current_git_sha(),
        source_guidance=source_guidance,
        effective_date=effective_date,
        rule_set_version=rule_set_version,
        validation_doc_id=validation_doc_id,
        status=status,
        created_utc=created_utc if created_utc is not None else _now(),
        notes=notes,
        extra=dict(extra or {}),
    )


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #
class Registry:
    """Append-only, versioned registry of rule-engines + AI artifacts.

    Entries are immutable; lifecycle changes are appended as :class:`StatusTransition`
    events. :meth:`resolve` returns the current ``production`` entry for a
    ``(kind, name)`` pair; promoting a new version auto-retires the incumbent (an
    appended event, never a mutation).
    """

    def __init__(self, *, clock: Callable[[], datetime] = _now) -> None:
        self._entries: dict[str, RegistryEntry] = {}
        self._transitions: list[StatusTransition] = []
        self._clock = clock

    # -- registration --------------------------------------------------------- #
    def register(self, entry: RegistryEntry) -> RegistryEntry:
        """Append ``entry``. Raises :class:`AppendOnlyViolation` on any overwrite."""

        if entry.entry_id in self._entries:
            raise AppendOnlyViolation(
                f"entry_id {entry.entry_id!r} already registered; the registry is "
                "append-only -- register a new semver instead of editing."
            )
        self._entries[entry.entry_id] = entry
        self._transitions.append(
            StatusTransition(
                entry_id=entry.entry_id,
                from_status=None,
                to_status=entry.status,
                transitioned_utc=entry.created_utc,
                reason="registered",
            )
        )
        return entry

    def register_artifact(self, **kwargs: Any) -> RegistryEntry:
        """Convenience: :func:`build_registry_entry` then :meth:`register`."""

        return self.register(build_registry_entry(**kwargs))

    # -- lookups -------------------------------------------------------------- #
    def get(self, entry_id: str) -> RegistryEntry:
        entry = self._entries.get(entry_id)
        if entry is None:
            raise KeyError(f"unknown entry_id: {entry_id!r}")
        return entry

    def current_status(self, entry_id: str) -> ArtifactStatus:
        self.get(entry_id)  # KeyError if unknown
        latest = [t for t in self._transitions if t.entry_id == entry_id]
        return latest[-1].to_status if latest else self.get(entry_id).status

    def list_entries(
        self,
        *,
        kind: ArtifactKind | None = None,
        name: str | None = None,
        status: ArtifactStatus | None = None,
    ) -> list[RegistryEntry]:
        out: list[RegistryEntry] = []
        for entry in self._entries.values():
            if kind is not None and entry.kind != kind:
                continue
            if name is not None and entry.name != name:
                continue
            if status is not None and self.current_status(entry.entry_id) != status:
                continue
            out.append(entry)
        return out

    def resolve(self, kind: ArtifactKind, name: str) -> RegistryEntry | None:
        """Return the current ``production`` entry for ``(kind, name)``, or ``None``.

        At most one is production (promotion auto-retires the incumbent); if several
        somehow match, the most recently promoted wins.
        """

        kind = ArtifactKind(kind)
        candidates = [
            e
            for e in self._entries.values()
            if e.kind == kind
            and e.name == name
            and self.current_status(e.entry_id) == ArtifactStatus.PRODUCTION
        ]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        promoted_at = self._production_promotion_index()
        return max(candidates, key=lambda e: promoted_at.get(e.entry_id, -1))

    # -- lifecycle ------------------------------------------------------------ #
    def set_status(
        self, entry_id: str, to_status: ArtifactStatus, *, reason: str | None = None
    ) -> StatusTransition:
        """Append a validated lifecycle transition. Promotion auto-retires the incumbent."""

        to_status = ArtifactStatus(to_status)
        entry = self.get(entry_id)
        current = self.current_status(entry_id)
        if to_status not in _ALLOWED_TRANSITIONS[current]:
            allowed = ", ".join(sorted(s.value for s in _ALLOWED_TRANSITIONS[current])) or "(none)"
            raise InvalidStatusTransition(
                f"{entry_id!r}: cannot go {current.value} -> {to_status.value} "
                f"(allowed from {current.value}: {allowed})"
            )
        incumbent = (
            self.resolve(entry.kind, entry.name)
            if to_status == ArtifactStatus.PRODUCTION
            else None
        )
        transition = StatusTransition(
            entry_id=entry_id,
            from_status=current,
            to_status=to_status,
            transitioned_utc=self._clock(),
            reason=reason,
        )
        self._transitions.append(transition)
        if incumbent is not None and incumbent.entry_id != entry_id:
            self._transitions.append(
                StatusTransition(
                    entry_id=incumbent.entry_id,
                    from_status=ArtifactStatus.PRODUCTION,
                    to_status=ArtifactStatus.RETIRED,
                    transitioned_utc=self._clock(),
                    reason=f"superseded by {entry_id}",
                )
            )
        return transition

    def promote(self, entry_id: str, *, reason: str | None = None) -> StatusTransition:
        """Shorthand for ``set_status(entry_id, PRODUCTION)``."""

        return self.set_status(entry_id, ArtifactStatus.PRODUCTION, reason=reason)

    def retire(self, entry_id: str, *, reason: str | None = None) -> StatusTransition:
        """Shorthand for ``set_status(entry_id, RETIRED)``."""

        return self.set_status(entry_id, ArtifactStatus.RETIRED, reason=reason)

    def transitions_for(self, entry_id: str) -> tuple[StatusTransition, ...]:
        return tuple(t for t in self._transitions if t.entry_id == entry_id)

    # -- provenance ----------------------------------------------------------- #
    def provenance(self, entry_id: str) -> dict[str, Any]:
        """The audit-facing provenance of one entry (feeds the Prompt 12 audit wrapper)."""

        entry = self.get(entry_id)
        out = entry.as_dict()
        out["current_status"] = self.current_status(entry_id).value
        out["entry_hash"] = entry.entry_hash()
        return out

    def _production_promotion_index(self) -> dict[str, int]:
        index: dict[str, int] = {}
        for i, t in enumerate(self._transitions):
            if t.to_status == ArtifactStatus.PRODUCTION:
                index[t.entry_id] = i
        return index


# --------------------------------------------------------------------------- #
# Seed: the production deterministic rule-engines, read from the engines themselves
# --------------------------------------------------------------------------- #
def _rule_engine_seeds() -> Iterable[dict[str, Any]]:
    """The five deterministic rule-engines, sourced from the engine modules.

    Versions are read from each engine's own ``*_rule_set()`` + guidance constants -- the
    single source of truth -- so a registry entry can never drift from the formula set it
    claims to encode. ``validation_doc_id`` references the engine's GxP validation record
    in the GAMP 5 / CSV package (Prompt 21).
    """

    from moltrace.regulatory.impurities import (
        cpca_classifier,
        m7_classifier,
        q3ab_calculator,
        q3c_solvents,
        q3d_elements,
    )

    return [
        {
            "name": "ich_q3ab",
            "source_guidance": (
                f"{q3ab_calculator.GUIDANCE_Q3A['guideline']} / "
                f"{q3ab_calculator.GUIDANCE_Q3B['guideline']}"
            ),
            "effective_date": q3ab_calculator.GUIDANCE_Q3A["effective_year"],
            "rule_set": q3ab_calculator.q3ab_rule_set(),
            "validation_doc_id": "GAMP5-CSV-ICH-Q3AB-R2",
        },
        {
            "name": "ich_q3c",
            "source_guidance": q3c_solvents.GUIDELINE,
            "effective_date": q3c_solvents.EFFECTIVE_YEAR,
            "rule_set": q3c_solvents.q3c_rule_set(),
            "validation_doc_id": "GAMP5-CSV-ICH-Q3C-R8",
        },
        {
            "name": "ich_q3d",
            "source_guidance": q3d_elements.GUIDELINE,
            "effective_date": q3d_elements.EFFECTIVE_YEAR,
            "rule_set": q3d_elements.q3d_rule_set(),
            "validation_doc_id": "GAMP5-CSV-ICH-Q3D-R2",
        },
        {
            "name": "ich_m7",
            "source_guidance": m7_classifier.GUIDELINE,
            "effective_date": m7_classifier.EFFECTIVE_YEAR,
            "rule_set": m7_classifier.m7_rule_set(),
            "validation_doc_id": "GAMP5-CSV-ICH-M7-R2",
        },
        {
            "name": "fda_cpca_nitrosamine",
            "source_guidance": cpca_classifier.GUIDELINE,
            "effective_date": cpca_classifier.EFFECTIVE_YEAR,
            "rule_set": cpca_classifier.cpca_rule_set(),
            "validation_doc_id": "GAMP5-CSV-FDA-NITROSAMINE-REV2",
        },
    ]


def default_regulatory_registry(
    *,
    semver: str = "1.0.0",
    code_sha: str | None = None,
    clock: Callable[[], datetime] = _now,
) -> Registry:
    """A :class:`Registry` seeded with the five production deterministic rule-engines.

    Each is registered as ``production`` and tied to its ICH/FDA guidance revision +
    effective date, its ``rule_set_version`` content address (computed from the engine's
    own ``*_rule_set()``), and its GxP ``validation_doc_id`` -- satisfying the Prompt 13
    acceptance that the registry tracks rule-set versions tied to guidance + effective
    date with validation-doc linkage for every rule-set.
    """

    registry = Registry(clock=clock)
    sha = code_sha if code_sha is not None else current_git_sha()
    for seed in _rule_engine_seeds():
        entry = build_registry_entry(
            kind=ArtifactKind.RULE_ENGINE,
            name=seed["name"],
            semver=semver,
            code_sha=sha,
            source_guidance=seed["source_guidance"],
            effective_date=seed["effective_date"],
            rule_set_version=rule_set_version(seed["rule_set"]),
            validation_doc_id=seed["validation_doc_id"],
            status=ArtifactStatus.PRODUCTION,
        )
        registry.register(entry)
    return registry
