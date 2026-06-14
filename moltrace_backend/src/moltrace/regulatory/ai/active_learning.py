"""Active-learning loop on regulatory reviewer feedback (Prompt 16, Roadmap Layer 4).

Capture every regulatory-affairs reviewer edit as labeled data and route the genuinely hard cases
to the right experts first. The loop improves narrative **drafting** and expert-**time allocation**;
it never touches the regulated decision math.

HARD RULE: borderline classifications (CPCA / M7) are escalated to humans, never silently
auto-resolved or re-classified by a model, and classifications NEVER auto-retrain (a boundary change
requires a new validated rule-set version, Prompt 13). This module only *reads* a classifier's
result fields to compute an ambiguity score for routing; it does not produce or alter a
classification. Only ``NARRATIVE_EDIT`` examples feed the (narrative) retraining trigger.

Three entry points (mirroring the spectroscopy edition):

* :func:`capture_review` — persist a reviewer edit/override/adjudication with full provenance
  (inputs, rule_set/model versions from Prompt 13, the AI output, the human-final version, reviewer
  id + role + timestamp) into an append-only :class:`ReviewLog`; optionally mirror to the Prompt 12
  Annex 22 audit chain (the expert-review log).
* :func:`borderline_queue` — rank borderline CPCA/M7 classifications by ambiguity and route them
  to a TOXICOLOGIST first; rank narrative drafts by cross-variant disagreement sampling.
* :func:`retraining_trigger` / :func:`evaluate_retraining` — fire a (narrative-only) retrain on
  a volume threshold or a monthly cadence, wired to a Prompt 15 hook; classifications are excluded.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from moltrace.regulatory.compliance.annex22_wrapper import Annex22Log, DecisionInputs
from moltrace.regulatory.infra import content_hash

__all__ = [
    "DEFAULT_RETRAIN_MIN_NEW_NARRATIVES",
    "DEFAULT_RETRAIN_SCHEDULE_DAYS",
    "ReviewerRole",
    "ReviewKind",
    "ReviewSession",
    "LabeledExample",
    "ReviewLog",
    "ClassificationCandidate",
    "NarrativeCandidate",
    "QueueItem",
    "RetrainDecision",
    "NarrativeRetrainHook",
    "capture_review",
    "classification_ambiguity",
    "narrative_disagreement",
    "borderline_queue",
    "evaluate_retraining",
    "retraining_trigger",
    "maybe_kickoff_narrative_retrain",
    "get_default_review_log",
    "set_default_review_log",
]

DEFAULT_RETRAIN_MIN_NEW_NARRATIVES = 50  # volume threshold of approved narratives
DEFAULT_RETRAIN_SCHEDULE_DAYS = 30  # monthly cadence


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, assuming UTC when it is naive (offset-less)."""

    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _get(result: Any, name: str, default: Any = None) -> Any:
    """Read a field from a frozen dataclass result OR a plain mapping (duck-typed, read-only)."""

    if isinstance(result, Mapping):
        return result.get(name, default)
    return getattr(result, name, default)


class ReviewerRole(StrEnum):
    """Roles authorized to adjudicate an expert review."""

    TOXICOLOGIST = "toxicologist"
    REGULATORY_AFFAIRS = "regulatory_affairs"
    QA = "qa"
    INDEPENDENT_EXPERT = "independent_expert"


class ReviewKind(StrEnum):
    """What the reviewer did. Only ``NARRATIVE_EDIT`` feeds the narrative retraining trigger."""

    NARRATIVE_EDIT = "narrative_edit"  # edited a generated narrative
    TRIAGE_OVERRIDE = "triage_override"  # overrode an LLM triage decision
    CLASSIFICATION_ADJUDICATION = "classification_adjudication"  # adjudicated a borderline class.


# --------------------------------------------------------------------------- #
# Review capture (append-only labeled-example / expert-review log)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReviewSession:
    """The context of one reviewer action — the input to :func:`capture_review`."""

    review_kind: ReviewKind
    reviewer_id: str
    reviewer_role: ReviewerRole
    inputs: Mapping[str, Any]
    ai_output: Any
    human_final: Any
    rule_set_version: str | None = None  # Prompt 13 deterministic rule-set provenance
    model_versions: Mapping[str, str] = field(default_factory=dict)  # Prompt 13 model provenance
    context: Mapping[str, Any] = field(default_factory=dict)
    created_utc: str | None = None


@dataclass(frozen=True)
class LabeledExample:
    """An append-only, content-addressed labeled example captured from a reviewer action."""

    example_id: str
    review_kind: ReviewKind
    reviewer_id: str
    reviewer_role: ReviewerRole
    inputs: Mapping[str, Any]
    ai_output: Any
    human_final: Any
    rule_set_version: str | None
    model_versions: Mapping[str, str]
    context: Mapping[str, Any]
    created_utc: str

    @property
    def feeds_narrative_retrain(self) -> bool:
        """Only narrative edits feed retraining — classifications/triage never do."""

        return self.review_kind is ReviewKind.NARRATIVE_EDIT

    def as_dict(self) -> dict:
        return {
            "example_id": self.example_id,
            "review_kind": self.review_kind.value,
            "reviewer_id": self.reviewer_id,
            "reviewer_role": self.reviewer_role.value,
            "inputs": dict(self.inputs),
            "ai_output": self.ai_output,
            "human_final": self.human_final,
            "rule_set_version": self.rule_set_version,
            "model_versions": dict(self.model_versions),
            "context": dict(self.context),
            "created_utc": self.created_utc,
        }


class ReviewLog:
    """Append-only store of labeled examples (the expert-review log).

    There is no update or delete; ``append`` is idempotent on ``example_id`` (re-capturing the same
    review is a no-op), and reads return immutable tuples — so the captured record is tamper-evident
    by construction.
    """

    def __init__(self) -> None:
        self._examples: list[LabeledExample] = []
        self._ids: set[str] = set()

    def append(self, example: LabeledExample) -> LabeledExample:
        if example.example_id not in self._ids:
            self._examples.append(example)
            self._ids.add(example.example_id)
        return example

    def examples(self, *, review_kind: ReviewKind | None = None) -> tuple[LabeledExample, ...]:
        if review_kind is None:
            return tuple(self._examples)
        return tuple(e for e in self._examples if e.review_kind is review_kind)

    def narrative_examples(self) -> tuple[LabeledExample, ...]:
        """The examples eligible to feed (narrative) retraining — NARRATIVE_EDIT only."""

        return self.examples(review_kind=ReviewKind.NARRATIVE_EDIT)

    def __len__(self) -> int:
        return len(self._examples)


_DEFAULT_REVIEW_LOG: ReviewLog | None = None


def get_default_review_log() -> ReviewLog:
    """The process-wide default append-only review log (lazily created)."""

    global _DEFAULT_REVIEW_LOG
    if _DEFAULT_REVIEW_LOG is None:
        _DEFAULT_REVIEW_LOG = ReviewLog()
    return _DEFAULT_REVIEW_LOG


def set_default_review_log(log: ReviewLog | None) -> None:
    global _DEFAULT_REVIEW_LOG
    _DEFAULT_REVIEW_LOG = log


def capture_review(
    session: ReviewSession,
    *,
    log: ReviewLog | None = None,
    audit_log: Annex22Log | None = None,
    now: str | None = None,
) -> LabeledExample:
    """Persist a reviewer edit/override/adjudication with full provenance (append-only).

    Captures inputs, the rule_set/model versions (Prompt 13), the AI output, the human-final
    version, and the reviewer id + role + timestamp. Appends to ``log`` (the append-only review log;
    the process-wide default if omitted) and, when an ``audit_log`` is supplied, also records the
    adjudication on the Prompt 12 Annex 22 tamper-evident chain (the expert-review log).
    """

    created = session.created_utc or now or _now_iso()
    example_id = content_hash(
        {
            "review_kind": session.review_kind.value,
            "reviewer_id": session.reviewer_id,
            "reviewer_role": session.reviewer_role.value,
            "inputs": dict(session.inputs),
            "ai_output": session.ai_output,
            "human_final": session.human_final,
            "rule_set_version": session.rule_set_version,
            "model_versions": dict(session.model_versions),
            "context": dict(session.context),
            "created_utc": created,
        }
    )
    example = LabeledExample(
        example_id=example_id,
        review_kind=session.review_kind,
        reviewer_id=session.reviewer_id,
        reviewer_role=session.reviewer_role,
        inputs=dict(session.inputs),
        ai_output=session.ai_output,
        human_final=session.human_final,
        rule_set_version=session.rule_set_version,
        model_versions=dict(session.model_versions),
        context=dict(session.context),
        created_utc=created,
    )
    target = log if log is not None else get_default_review_log()
    target.append(example)

    if audit_log is not None:
        # Mirror the human adjudication onto the Annex 22 audit chain (expert-review log linkage).
        model_version = next(
            iter(session.model_versions.values()), session.rule_set_version or "n/a"
        )
        risk = "high" if session.review_kind is ReviewKind.CLASSIFICATION_ADJUDICATION else "medium"
        audit_log.record_decision(
            user_id=session.reviewer_id,
            decision_type=f"review:{session.review_kind.value}",
            risk_level=risk,
            model_name="regulatory_active_learning",
            model_version=str(model_version),
            inputs=DecisionInputs(
                input_data_hash=content_hash(dict(session.inputs)),
                input_smiles=session.inputs.get("smiles"),
            ),
            output={"ai_output": session.ai_output, "human_final": session.human_final},
            confidence=1.0,  # a human adjudication is certain
            feature_attribution={
                "reviewer_role": session.reviewer_role.value,
                "review_kind": session.review_kind.value,
            },
            regulatory_basis="Prompt 16 active-learning expert-review capture",
        )
    return example


# --------------------------------------------------------------------------- #
# Borderline queue (classification ambiguity + narrative disagreement sampling)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ClassificationCandidate:
    """A CPCA/M7 classification to consider for expert review (the result is read-only)."""

    candidate_id: str
    engine: str  # 'cpca' | 'm7'
    result: Any  # CPCAResult | M7Classification | a mapping carrying the same fields


@dataclass(frozen=True)
class NarrativeCandidate:
    """A narrative draft produced by several template/model variants (for disagreement sampling)."""

    candidate_id: str
    variants: Sequence[str]


@dataclass(frozen=True)
class QueueItem:
    """A review-queue item: its ambiguity, who to route it to, and the original candidate."""

    item_id: str
    item_type: str  # 'classification' | 'narrative'
    ambiguity: float  # [0, 1]; higher = more informative / more in need of judgment
    route_to: ReviewerRole
    reason: str
    payload: Any  # the original candidate, UNCHANGED (the loop never alters a classification)

    def as_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "ambiguity": round(self.ambiguity, 6),
            "route_to": self.route_to.value,
            "reason": self.reason,
        }


def classification_ambiguity(engine: str, result: Any) -> tuple[float, bool, str]:
    """Read-only ambiguity score for a CPCA/M7 result: ``(score in [0,1], is_borderline, reason)``.

    This NEVER changes the classification — it only reads the deterministic engine's own borderline
    signals (M7 (Q)SAR discordance / cohort-of-concern; CPCA conflicting structural features / CoC /
    missing potency score) to decide whether a human should look and how urgently.
    """

    engine = engine.lower()
    reasons: list[str] = []
    score = 0.0
    if engine == "m7":
        if _get(result, "in_silico_concordance") == "discordant":
            score += 0.6
            reasons.append("discordant (Q)SAR: expert vs statistical disagree")
        if _get(result, "coc_flag"):
            score += 0.25
            reasons.append("cohort of concern")
        if len(_get(result, "structural_alerts", ()) or ()) > 1:
            score += 0.1
            reasons.append("multiple structural alerts")
        if _get(result, "expert_review_required") and not reasons:
            score += 0.1
            reasons.append("engine flagged expert review")
    elif engine == "cpca":
        activating = _get(result, "activating_features", ()) or ()
        deactivating = _get(result, "deactivating_features", ()) or ()
        if activating and deactivating:
            score += 0.5
            reasons.append("conflicting activating + deactivating structural features")
        if _get(result, "coc_flag"):
            score += 0.25
            reasons.append("cohort of concern")
        # NOTE: a None potency_score is NOT treated as borderline — the engine sets it for a forced
        # Category 5 (lowest predicted potency), which is the case least in need of toxicology time;
        # flagging it would over-escalate and waste the scarce expert budget this loop conserves.
    else:
        raise ValueError(f"unknown classification engine: {engine!r} (expected 'cpca' or 'm7')")
    score = min(1.0, score)
    return score, score > 0.0, "; ".join(reasons) if reasons else "no borderline signal"


def narrative_disagreement(variants: Sequence[str]) -> float:
    """Disagreement across template/model draft variants (a vote-split / plurality gap).

    Returns 0.0 when all variants agree (low information) and approaches 1.0 (bounded by 1 - 1/n) as
    they diverge (most informative to review). Fewer than two variants → 0.0.
    """

    drafts = [v.strip() for v in variants]
    n = len(drafts)
    if n < 2:
        return 0.0
    counts: dict[str, int] = {}
    for draft in drafts:
        counts[draft] = counts.get(draft, 0) + 1
    plurality = max(counts.values())
    return 1.0 - (plurality / n)


def borderline_queue(
    candidates: Sequence[Any],
    budget: int,
    *,
    narrative_route: ReviewerRole = ReviewerRole.REGULATORY_AFFAIRS,
) -> list[QueueItem]:
    """Rank hard cases for review and route them, respecting ``budget`` (max items returned).

    Borderline CPCA/M7 classifications are ranked by ambiguity and routed to a TOXICOLOGIST first;
    narrative drafts are ranked by cross-variant disagreement (disagreement sampling) and routed to
    regulatory affairs. Classification items precede narrative items so scarce toxicology time is
    spent on the regulated-boundary cases first. A classification that is NOT borderline is omitted
    (the deterministic engine resolved it; no human needed). Nothing here re-classifies anything.
    """

    if budget < 0:
        raise ValueError(f"budget must be >= 0, got {budget}")

    classification_items: list[QueueItem] = []
    narrative_items: list[QueueItem] = []
    for candidate in candidates:
        if isinstance(candidate, ClassificationCandidate):
            score, is_borderline, reason = classification_ambiguity(
                candidate.engine, candidate.result
            )
            if not is_borderline:
                continue  # resolved deterministically — escalate only the genuinely hard cases
            classification_items.append(
                QueueItem(
                    item_id=candidate.candidate_id,
                    item_type="classification",
                    ambiguity=score,
                    route_to=ReviewerRole.TOXICOLOGIST,
                    reason=reason,
                    payload=candidate,
                )
            )
        elif isinstance(candidate, NarrativeCandidate):
            score = narrative_disagreement(candidate.variants)
            if score <= 0.0:
                continue  # variants agree — not informative to review
            narrative_items.append(
                QueueItem(
                    item_id=candidate.candidate_id,
                    item_type="narrative",
                    ambiguity=score,
                    route_to=narrative_route,
                    reason="cross-variant disagreement (disagreement sampling)",
                    payload=candidate,
                )
            )
        else:
            raise TypeError(
                "candidates must be ClassificationCandidate or NarrativeCandidate, "
                f"got {type(candidate).__name__}"
            )

    classification_items.sort(key=lambda q: (-q.ambiguity, q.item_id))
    narrative_items.sort(key=lambda q: (-q.ambiguity, q.item_id))
    ordered = classification_items + narrative_items  # toxicologist (boundary cases) first
    return ordered[:budget]


# --------------------------------------------------------------------------- #
# Retraining trigger (narrative ONLY — classifications are excluded by construction)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetrainDecision:
    """Whether to fire a narrative retrain now, and why (auditable, not magic)."""

    should_retrain: bool
    reason: str  # 'volume' | 'schedule' | 'volume+schedule' | 'bootstrap' | 'not_yet'
    new_examples: int
    min_new: int
    days_since_last: float | None
    schedule_days: int

    def as_dict(self) -> dict:
        return {
            "should_retrain": self.should_retrain,
            "reason": self.reason,
            "new_examples": self.new_examples,
            "min_new": self.min_new,
            "days_since_last": self.days_since_last,
            "schedule_days": self.schedule_days,
        }


def evaluate_retraining(
    *,
    new_approved_narratives: int,
    last_retrain_utc: str | None = None,
    now_utc: str | None = None,
    min_new: int = DEFAULT_RETRAIN_MIN_NEW_NARRATIVES,
    schedule_days: int = DEFAULT_RETRAIN_SCHEDULE_DAYS,
) -> RetrainDecision:
    """Decide whether to kick off a NARRATIVE retrain: enough new approved narratives OR monthly.

    Only approved-narrative volume drives this. Classifications are never an input — a boundary
    change requires a new validated rule-set version (Prompt 13), not a retrain.
    """

    now = now_utc or _now_iso()
    by_volume = new_approved_narratives >= min_new
    days_since: float | None = None
    by_schedule = False
    if last_retrain_utc is not None:
        days_since = (_parse_iso(now) - _parse_iso(last_retrain_utc)).total_seconds() / 86400.0
        by_schedule = days_since >= schedule_days

    if by_volume and by_schedule:
        reason = "volume+schedule"
    elif by_volume:
        reason = "volume"
    elif by_schedule:
        reason = "schedule"
    elif last_retrain_utc is None:
        reason = "bootstrap"  # no prior retrain; volume-gated only, and volume not yet met
    else:
        reason = "not_yet"
    return RetrainDecision(
        should_retrain=by_volume or by_schedule,
        reason=reason,
        new_examples=new_approved_narratives,
        min_new=min_new,
        days_since_last=days_since,
        schedule_days=schedule_days,
    )


def retraining_trigger(
    *,
    new_approved_narratives: int,
    last_retrain_utc: str | None = None,
    now_utc: str | None = None,
    min_new: int = DEFAULT_RETRAIN_MIN_NEW_NARRATIVES,
    schedule_days: int = DEFAULT_RETRAIN_SCHEDULE_DAYS,
) -> bool:
    """True when a (narrative-only) retrain should fire now. Classifications never auto-retrain."""

    return evaluate_retraining(
        new_approved_narratives=new_approved_narratives,
        last_retrain_utc=last_retrain_utc,
        now_utc=now_utc,
        min_new=min_new,
        schedule_days=schedule_days,
    ).should_retrain


@runtime_checkable
class NarrativeRetrainHook(Protocol):
    """The Prompt 15 injection point: receives the approved narrative examples to learn from."""

    def __call__(self, examples: Sequence[LabeledExample]) -> Any: ...


def maybe_kickoff_narrative_retrain(
    decision: RetrainDecision,
    examples: Sequence[LabeledExample],
    *,
    hook: NarrativeRetrainHook,
) -> Any | None:
    """Invoke the Prompt 15 ``hook`` iff the trigger fired — and ONLY on narrative examples.

    Any non-narrative example (a classification adjudication / triage override) is filtered out
    before the hook is called, so no classification can ever reach a retrain path.
    """

    if not decision.should_retrain:
        return None
    narrative_only = [e for e in examples if e.feeds_narrative_retrain]
    return hook(narrative_only)
