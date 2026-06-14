"""In-app feedback capture for regulatory AI output (Prompt 22, Phase 5).

Renders the "Was this correct / acceptable?" signal on every AI output (a generated narrative, a
triage decision, a classification, a justification): accept / edit + free-text + a structured REASON
TAXONOMY. Each event is persisted append-only with its rule-set + model versions (Prompt 13).

THE HARD ROUTING RULE: a CLASSIFICATION override is routed through the Prompt 16 borderline queue to
a TOXICOLOGIST — recorded as an adjudication, never silent learning of a new boundary. A NARRATIVE
edit is fed into the Prompt 16 review log as the learning signal for the narrative reward model
(Prompt 22) and the narrative LoRA (Prompt 15). The deterministic math is never touched here.
"""

from __future__ import annotations

import abc
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from moltrace.regulatory.ai.active_learning import (
    ClassificationCandidate,
    LabeledExample,
    ReviewerRole,
    ReviewKind,
    ReviewLog,
    ReviewSession,
    borderline_queue,
    capture_review,
)
from moltrace.regulatory.ai.active_learning import QueueItem as _QueueItem
from moltrace.regulatory.compliance.annex22_wrapper import Annex22Log
from moltrace.regulatory.infra import content_hash

__all__ = [
    "CaptureResult",
    "FeedbackEvent",
    "FeedbackStore",
    "FeedbackVerdict",
    "InMemoryFeedbackStore",
    "OutputKind",
    "ReasonCode",
    "capture_feedback",
    "feedback_events",
]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class OutputKind(StrEnum):
    """What AI output the feedback rates."""

    NARRATIVE = "narrative"
    TRIAGE = "triage"
    CLASSIFICATION = "classification"
    JUSTIFICATION = "justification"


class FeedbackVerdict(StrEnum):
    """The reviewer's verdict on the output."""

    ACCEPT = "accept"
    EDIT = "edit"
    REJECT = "reject"


class ReasonCode(StrEnum):
    """The structured reason taxonomy attached to a non-accept verdict."""

    WRONG_CLASSIFICATION = "wrong_classification"
    CITATION_MISSING = "citation_missing"
    CITATION_WRONG = "citation_wrong"
    TONE_FORMAT = "tone_format"
    FACTUAL_EDIT = "factual_edit"
    SCOPE = "scope"
    OTHER = "other"


@dataclass(frozen=True)
class FeedbackEvent:
    """One immutable, content-addressed feedback event on a single AI output."""

    output_kind: OutputKind
    output_ref: str  # content address / id of the rated output
    verdict: FeedbackVerdict
    model_versions: Mapping[str, str]  # Prompt 13 provenance
    rule_set_version: str | None = None  # Prompt 13 deterministic rule-set
    reason: ReasonCode | None = None
    free_text: str | None = None
    corrected_text: str | None = None  # the human-final narrative (an EDIT)
    context: Mapping[str, Any] = field(default_factory=dict)
    reviewer_id: str | None = None
    reviewer_role: ReviewerRole | None = None
    created_utc: str = field(default_factory=_now_iso)

    @property
    def is_override(self) -> bool:
        return self.verdict in (FeedbackVerdict.EDIT, FeedbackVerdict.REJECT)

    def event_id(self) -> str:
        return content_hash(
            {
                "output_kind": self.output_kind.value,
                "output_ref": self.output_ref,
                "verdict": self.verdict.value,
                "model_versions": dict(self.model_versions),
                "rule_set_version": self.rule_set_version,
                "reason": self.reason.value if self.reason else None,
                "free_text": self.free_text,
                "corrected_text": self.corrected_text,
                "context": dict(self.context),
                "reviewer_id": self.reviewer_id,
                "reviewer_role": self.reviewer_role.value if self.reviewer_role else None,
                "created_utc": self.created_utc,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id(),
            "output_kind": self.output_kind.value,
            "output_ref": self.output_ref,
            "verdict": self.verdict.value,
            "model_versions": dict(self.model_versions),
            "rule_set_version": self.rule_set_version,
            "reason": self.reason.value if self.reason else None,
            "free_text": self.free_text,
            "corrected_text": self.corrected_text,
            "reviewer_id": self.reviewer_id,
            "reviewer_role": self.reviewer_role.value if self.reviewer_role else None,
            "created_utc": self.created_utc,
        }


class FeedbackStore(abc.ABC):
    """Append-only, idempotent persistence for feedback events."""

    @abc.abstractmethod
    def add_event(self, event: FeedbackEvent) -> None: ...

    @abc.abstractmethod
    def all_events(self) -> list[FeedbackEvent]: ...


class InMemoryFeedbackStore(FeedbackStore):
    def __init__(self) -> None:
        self._events: dict[str, FeedbackEvent] = {}

    def add_event(self, event: FeedbackEvent) -> None:
        self._events.setdefault(event.event_id(), event)  # idempotent

    def all_events(self) -> list[FeedbackEvent]:
        return list(self._events.values())


@dataclass(frozen=True)
class CaptureResult:
    """The outcome of capturing one feedback event + where the signal went."""

    event: FeedbackEvent
    routed_to: ReviewerRole | None  # a toxicologist for a classification override
    review_queue: tuple[_QueueItem, ...]  # the Prompt 16 borderline-queue routing
    review_example: LabeledExample | None  # the narrative learning signal (NARRATIVE_EDIT)

    @property
    def is_classification_override(self) -> bool:
        return self.routed_to is ReviewerRole.TOXICOLOGIST


def capture_feedback(
    *,
    output_kind: OutputKind,
    output_ref: str,
    verdict: FeedbackVerdict,
    model_versions: Mapping[str, str],
    rule_set_version: str | None = None,
    reason: ReasonCode | None = None,
    free_text: str | None = None,
    corrected_text: str | None = None,
    context: Mapping[str, Any] | None = None,
    reviewer_id: str | None = None,
    reviewer_role: ReviewerRole | None = None,
    classification_result: Any = None,
    store: FeedbackStore | None = None,
    review_log: ReviewLog | None = None,
    audit_log: Annex22Log | None = None,
    now: str | None = None,
) -> CaptureResult:
    """Capture one in-app feedback event and route the signal correctly.

    Always persists the event (append-only) with its rule-set + model versions. A CLASSIFICATION
    override is routed to a TOXICOLOGIST via the Prompt 16 borderline queue and recorded as an
    adjudication — never silent learning. A NARRATIVE edit (with corrected text) is fed into the
    Prompt 16 review log as the learning signal. The deterministic math is never updated here.
    """

    context = dict(context or {})
    event = FeedbackEvent(
        output_kind=output_kind,
        output_ref=output_ref,
        verdict=verdict,
        model_versions=dict(model_versions),
        rule_set_version=rule_set_version,
        reason=reason,
        free_text=free_text,
        corrected_text=corrected_text,
        context=context,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        created_utc=now or _now_iso(),
    )
    if store is not None:
        store.add_event(event)  # append-only; capture also works with no store (no persistence)

    routed_to: ReviewerRole | None = None
    review_queue: tuple[_QueueItem, ...] = ()
    review_example: LabeledExample | None = None

    if output_kind is OutputKind.CLASSIFICATION and event.is_override:
        # HARD RULE: a human override of a regulated classification ALWAYS goes to a toxicologist
        # and is recorded as an adjudication — it never trains a model or moves a boundary.
        routed_to = ReviewerRole.TOXICOLOGIST
        candidate = ClassificationCandidate(
            candidate_id=output_ref,
            engine=str(context.get("engine", "cpca")),
            result=classification_result
            if classification_result is not None
            else context.get("result", {}),
        )
        review_queue = tuple(borderline_queue([candidate], budget=8))
        if review_log is not None:
            capture_review(
                ReviewSession(
                    review_kind=ReviewKind.CLASSIFICATION_ADJUDICATION,
                    reviewer_id=reviewer_id or "unassigned",
                    reviewer_role=ReviewerRole.TOXICOLOGIST,
                    inputs=context,
                    ai_output=candidate.result,
                    human_final=corrected_text if corrected_text is not None else candidate.result,
                    rule_set_version=rule_set_version,
                    model_versions=dict(model_versions),
                    context={"reason": reason.value if reason else None, "source": "feedback"},
                    created_utc=event.created_utc,
                ),
                log=review_log,
                audit_log=audit_log,
            )
    elif (
        output_kind is OutputKind.NARRATIVE
        and verdict is FeedbackVerdict.EDIT
        and corrected_text
        and review_log is not None
    ):
        # the narrative learning signal: an approved edit -> Prompt 16 review log (NARRATIVE_EDIT)
        review_example = capture_review(
            ReviewSession(
                review_kind=ReviewKind.NARRATIVE_EDIT,
                reviewer_id=reviewer_id or "unassigned",
                reviewer_role=reviewer_role or ReviewerRole.REGULATORY_AFFAIRS,
                inputs=context,
                ai_output=context.get("draft", output_ref),
                human_final=corrected_text,
                rule_set_version=rule_set_version,
                model_versions=dict(model_versions),
                context={"decision_type": context.get("decision_type", "narrative"),
                         "citations": context.get("citations", ())},
                created_utc=event.created_utc,
            ),
            log=review_log,
            audit_log=audit_log,
        )

    return CaptureResult(
        event=event, routed_to=routed_to, review_queue=review_queue, review_example=review_example
    )


def feedback_events(
    store: FeedbackStore, *, output_kind: OutputKind | None = None
) -> Sequence[FeedbackEvent]:
    """All captured events, optionally filtered by output kind."""

    events = store.all_events()
    if output_kind is None:
        return events
    return [e for e in events if e.output_kind is output_kind]
