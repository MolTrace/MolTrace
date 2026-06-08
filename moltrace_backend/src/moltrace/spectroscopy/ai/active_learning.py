"""The closed active-learning loop (Prompt 16, Roadmap Layer 4).

This is the flywheel and the core moat: every time a human reviewer overrides
SpectraCheck, that correction becomes labeled training data, and the system
*actively* chooses the most informative spectra for scarce expert attention. No
incumbent spectroscopy tool runs a closed active-learning loop on customer data.

The four stages of the loop, four public functions, each composing substrate that
earlier prompts already built rather than re-implementing it:

* :func:`capture_override` — when a reviewer corrects an assignment / structure /
  peak label / purity call, persist a :class:`LabeledExample` (from the Prompt 23
  feedback layer) with full provenance (raw-FID hash, processed spectrum, the Prompt 13
  ``model_versions`` that produced the original, the AI output, the human
  correction, reviewer id + timestamp). Append-only — it flows through the Prompt
  23 :class:`~moltrace.spectroscopy.feedback.capture.FeedbackCollector` and feeds
  the Prompt 15 training snapshot.
* :func:`disagreement_score` — run N model variants (the Prompt 6 pretrained
  predictor, the Prompt 15 fine-tuned adapter, and the Prompt 14 RAG reasoner)
  and measure their disagreement: vote split on the top-1 structure, variance of
  predicted shifts, and spread of confidences. High disagreement == high
  information value.
* :func:`build_annotation_queue` — rank an unlabeled / low-confidence candidate
  pool by :func:`disagreement_score` (highest first), de-duplicate near-identical
  spectra, and return the top ``budget`` for expert annotation — reusing the
  Prompt 23 :func:`~moltrace.spectroscopy.feedback.reward_model.prioritize_annotation_queue`
  so a reward model can blend in "how likely the model is to be wrong".
* :func:`retraining_trigger` — fire on a monthly schedule OR when newly labeled
  examples exceed a threshold since the last fine-tune; :func:`maybe_kickoff_retrain`
  then kicks off the Prompt 15 pipeline (:func:`kickoff_finetune`).

Instrumentation (:func:`loop_yield_metrics`) tracks the loop's *yield* — labeled
examples per month, the override-rate trend (which should fall as the model
improves), and the accuracy lift per retrain — and :func:`emit_loop_yield` writes
that rollup to the Prompt 12 audit trail for the Prompt 18 dashboard.

Differentiation: corrections compound. Each customer's expert review improves the
shared model (subject to their data-sharing terms); disagreement sampling makes
labeling far more efficient than random; and the override-rate trend is direct,
auditable evidence the product is getting better. This loop is extremely hard for
a late competitor to replicate because it needs the install base *and* the closed
loop at once.

Like the rest of the AI layer, every heavy path is injectable: the model variants,
the reward function, the retraining kick-off, and the audit recorder are all passed
in, so the orchestration and scoring are pure-Python and unit-testable on a
CPU-only host with none of the heavy ML dependencies installed.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from moltrace.spectroscopy.ai.finetune import (
    ActiveLearningItem,
    build_training_snapshot,
    finetune_lora,
    register_if_eligible,
)
from moltrace.spectroscopy.audit.trail import get_default_recorder
from moltrace.spectroscopy.feedback.capture import (
    FeedbackCollector,
    FeedbackEvent,
    LabeledExample,
    OutputKind,
    ReasonCode,
    UsageAnalytics,
    usage_analytics,
)
from moltrace.spectroscopy.feedback.reward_model import (
    PrioritizedItem,
    prioritize_annotation_queue,
)
from moltrace.spectroscopy.infra.contract import content_hash

__all__ = [
    "DEFAULT_DEDUP_THRESHOLD",
    "DEFAULT_DISAGREEMENT_WEIGHTS",
    "DEFAULT_METRICS_WINDOW_DAYS",
    "DEFAULT_RETRAIN_MIN_NEW_LABELS",
    "DEFAULT_RETRAIN_SCHEDULE_DAYS",
    "DEFAULT_SHIFT_DISAGREEMENT_SCALE_PPM",
    "ActiveLearningError",
    "DisagreementReport",
    "LoopYieldMetrics",
    "ModelVariant",
    "OverrideSession",
    "RetrainEvent",
    "RetrainingDecision",
    "VariantPrediction",
    "build_annotation_queue",
    "capture_override",
    "disagreement_score",
    "emit_loop_yield",
    "evaluate_retraining",
    "get_default_collector",
    "kickoff_finetune",
    "loop_yield_metrics",
    "maybe_kickoff_retrain",
    "rag_variant",
    "retraining_trigger",
    "routed_variant",
    "score_disagreement",
    "set_default_collector",
]

# How many ppm of cross-variant shift standard deviation saturates the shift
# component of the disagreement score (soft 1 - exp(-std/scale)). 5 ppm is a
# pragmatic single-nucleus default; tune per nucleus (¹H is tighter, ¹³C wider).
DEFAULT_SHIFT_DISAGREEMENT_SCALE_PPM = 5.0
# Convex blend of the three disagreement components (must be read as relative —
# they are renormalised over whichever components are defined for a given pool).
DEFAULT_DISAGREEMENT_WEIGHTS: Mapping[str, float] = {
    "structure": 0.5,
    "shift": 0.3,
    "confidence": 0.2,
}
# A queued candidate at/above this similarity to an already-kept one is a near
# duplicate and is dropped (only used when a ``similarity_fn`` is supplied).
DEFAULT_DEDUP_THRESHOLD = 0.98
# Retraining trigger defaults: monthly schedule OR a volume of new labels.
DEFAULT_RETRAIN_MIN_NEW_LABELS = 50
DEFAULT_RETRAIN_SCHEDULE_DAYS = 30
# Trailing window for loop-yield rates (≈ one month).
DEFAULT_METRICS_WINDOW_DAYS = 30


class ActiveLearningError(RuntimeError):
    """Raised when the active-learning loop is given inconsistent inputs."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _parse_iso(value: Any) -> datetime | None:
    """Best-effort ISO-8601 parse; ``None`` for anything unparseable.

    The loop tolerates non-timestamp ``created_utc`` markers (tests use opaque
    strings like ``"t-0"``): such events still count toward totals but are simply
    excluded from the time-windowed rates.
    """

    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# --------------------------------------------------------------------------- #
# 1. Override capture
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OverrideSession:
    """A reviewer's override of one AI output, with the full context to learn from.

    This is the structured input to :func:`capture_override`. It carries
    everything needed to turn a correction into an attributable training signal:
    the dataset identity (``record_hash``), what was overridden (``output_kind`` +
    the original ``ai_output``), the **ground-truth** correction
    (``corrected_value``), the Prompt 13 ``model_versions`` that produced the
    wrong output, the raw-FID hash + processed spectrum for full reproducibility,
    and who reviewed it when.
    """

    record_hash: str  # dataset identity of the corrected example
    output_kind: OutputKind | str
    model_versions: Mapping[str, str]  # Prompt 13 provenance of the original output
    ai_output: Any  # the original (overridden) AI value
    corrected_value: Any  # the reviewer's structured ground truth
    reviewer_id: str
    raw_fid_hash: str | None = None  # content hash of the raw FID
    processed_spectrum: Mapping[str, Any] | None = None  # the processed spectrum
    reason: ReasonCode | str | None = None
    correction_text: str | None = None
    output_ref: str | None = None  # content address of the rated output (derived if absent)
    tenant_id: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)
    created_utc: str | None = None


# Process-wide default collector (mirrors audit.trail.get_default_recorder). In
# production wire a durable SqlAlchemyFeedbackStore-backed collector via
# set_default_collector(); the lazy in-memory default keeps capture usable in
# minimal / test environments.
_DEFAULT_COLLECTOR: FeedbackCollector | None = None


def get_default_collector() -> FeedbackCollector:
    """The process-wide default :class:`FeedbackCollector` (lazily created)."""

    global _DEFAULT_COLLECTOR
    if _DEFAULT_COLLECTOR is None:
        _DEFAULT_COLLECTOR = FeedbackCollector()
    return _DEFAULT_COLLECTOR


def set_default_collector(collector: FeedbackCollector | None) -> None:
    """Install (or clear) the process-wide default collector."""

    global _DEFAULT_COLLECTOR
    _DEFAULT_COLLECTOR = collector


def capture_override(
    session: OverrideSession,
    *,
    collector: FeedbackCollector | None = None,
) -> LabeledExample:
    """Persist a reviewer override as a labeled training example, append-only.

    Routes the override through the Prompt 23 :class:`FeedbackCollector` (which
    stores an immutable, content-addressed :class:`FeedbackEvent` and fans bare
    overrides out to the active-learning queue), then returns the
    :class:`LabeledExample` the correction yields — the unit the Prompt 15
    training snapshot consumes.

    Full provenance is preserved: the original ``ai_output``, the ``raw_fid_hash``,
    and the ``processed_spectrum`` are recorded in the event ``context``; the
    Prompt 13 ``model_versions`` and the ``reviewer_id`` / timestamp travel on the
    event itself. The processed spectrum is also content-hashed so the example is
    reproducible from its inputs.

    Raises :class:`ActiveLearningError` if the session lacks the structured
    ``corrected_value`` a label requires (a bare thumbs-down with no ground truth
    belongs on the active-learning queue, not in the labeled-example store).
    """

    if session.corrected_value is None:
        raise ActiveLearningError(
            "capture_override requires a structured corrected_value (the reviewer's "
            "ground truth); a bare override with no correction is queued for "
            "annotation instead of labeled"
        )
    if not session.record_hash:
        raise ActiveLearningError("capture_override requires a record_hash (dataset identity)")

    sink = collector if collector is not None else get_default_collector()

    # Assemble the full learning context. The processed spectrum is stored verbatim
    # AND content-hashed so the example is reproducible and de-dupable by content.
    context: dict[str, Any] = dict(session.context)
    context["ai_output"] = session.ai_output
    if session.raw_fid_hash is not None:
        context["raw_fid_hash"] = session.raw_fid_hash
    if session.processed_spectrum is not None:
        context["processed_spectrum"] = dict(session.processed_spectrum)
        context["processed_spectrum_hash"] = content_hash(dict(session.processed_spectrum))

    # A correction is, by definition, a thumbs-down that supplies ground truth.
    output_ref = session.output_ref or content_hash(session.ai_output)
    event = sink.capture(
        output_kind=session.output_kind,
        output_ref=output_ref,
        verdict="down",
        model_versions=session.model_versions,
        record_hash=session.record_hash,
        reason=session.reason,
        correction_text=session.correction_text,
        corrected_value=session.corrected_value,
        context=context,
        reviewer_id=session.reviewer_id,
        tenant_id=session.tenant_id,
        created_utc=session.created_utc,
    )
    example = event.to_labeled_example()
    if example is None:  # pragma: no cover - guarded by the checks above
        raise ActiveLearningError(
            "override did not yield a labeled example (missing corrected_value/record_hash)"
        )
    return example


# --------------------------------------------------------------------------- #
# 2. Disagreement sampling
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class VariantPrediction:
    """One model variant's read on a spectrum, normalised for disagreement scoring.

    A variant supplies whatever it can: a top-1 structure (canonical SMILES), a
    predicted-shift vector (ppm, index-aligned across variants), and its own
    confidence in ``[0, 1]``. Any field may be empty — the score uses only the
    components enough variants supply.
    """

    variant: str
    top1_structure: str | None = None
    predicted_shifts: tuple[float, ...] = ()
    confidence: float = 0.0


@runtime_checkable
class ModelVariant(Protocol):
    """A callable that reads a spectrum and returns a :class:`VariantPrediction`."""

    def __call__(self, spectrum: Any) -> VariantPrediction: ...


@dataclass(frozen=True)
class DisagreementReport:
    """The disagreement score plus the per-component breakdown that produced it."""

    score: float
    n_variants: int
    structure_disagreement: float | None
    shift_disagreement: float | None
    confidence_spread: float | None
    mean_shift_std_ppm: float | None
    weights: Mapping[str, float]  # the renormalised weights actually applied
    top1_structures: tuple[str | None, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "n_variants": self.n_variants,
            "structure_disagreement": self.structure_disagreement,
            "shift_disagreement": self.shift_disagreement,
            "confidence_spread": self.confidence_spread,
            "mean_shift_std_ppm": self.mean_shift_std_ppm,
            "weights": dict(sorted(self.weights.items())),
            "top1_structures": list(self.top1_structures),
        }


def _structure_disagreement(structures: Sequence[str]) -> float | None:
    """Normalised vote split on the top-1 structure (0 unanimous .. 1 all differ)."""

    m = len(structures)
    if m < 2:
        return None
    counts: dict[str, int] = {}
    for smiles in structures:
        counts[smiles] = counts.get(smiles, 0) + 1
    plurality = max(counts.values())
    raw = 1.0 - plurality / m  # 0 when unanimous, (1 - 1/m) when all distinct
    return _clip01(raw / (1.0 - 1.0 / m))  # renormalise to a full [0, 1]


def _shift_disagreement(
    vectors: Sequence[Sequence[float]], *, scale_ppm: float
) -> tuple[float | None, float | None]:
    """Soft-saturated mean per-position shift spread across variants.

    Returns ``(disagreement, mean_std_ppm)``; both ``None`` when fewer than two
    variants predicted shifts (or they share no aligned positions).
    """

    usable = [tuple(v) for v in vectors if len(v) > 0]
    if len(usable) < 2:
        return None, None
    length = min(len(v) for v in usable)
    if length == 0:
        return None, None
    stds = [statistics.pstdev([v[i] for v in usable]) for i in range(length)]
    mean_std = sum(stds) / length
    return _clip01(1.0 - math.exp(-mean_std / scale_ppm)), mean_std


def score_disagreement(
    predictions: Sequence[VariantPrediction],
    *,
    weights: Mapping[str, float] | None = None,
    shift_scale_ppm: float = DEFAULT_SHIFT_DISAGREEMENT_SCALE_PPM,
) -> DisagreementReport:
    """Combine the three disagreement signals over a set of variant predictions.

    The score is a convex blend, in ``[0, 1]``, of the structure vote split, the
    shift spread, and the confidence spread — renormalised over whichever
    components at least two variants actually supply (a pool where only confidences
    are present still scores). Requires at least two variants.
    """

    preds = list(predictions)
    if len(preds) < 2:
        raise ActiveLearningError("disagreement scoring needs at least 2 variant predictions")

    blend = {**DEFAULT_DISAGREEMENT_WEIGHTS, **(weights or {})}

    top1 = tuple(getattr(p, "top1_structure", None) for p in preds)
    structures = [s for s in top1 if s]
    structure_dis = _structure_disagreement(structures)

    vectors = [tuple(getattr(p, "predicted_shifts", ()) or ()) for p in preds]
    shift_dis, mean_std = _shift_disagreement(vectors, scale_ppm=shift_scale_ppm)

    # Every prediction carries a confidence, so with n >= 2 variants this is always
    # defined — the spread (range) of their confidences in [0, 1].
    confidences = [_clip01(float(getattr(p, "confidence", 0.0) or 0.0)) for p in preds]
    confidence_spread = _clip01(max(confidences) - min(confidences))

    components = {
        "structure": structure_dis,
        "shift": shift_dis,
        "confidence": confidence_spread,
    }
    active = {k: float(blend.get(k, 0.0)) for k, v in components.items() if v is not None}
    total = sum(active.values())
    if total <= 0.0:  # pragma: no cover - confidence is always defined for n >= 2
        applied: dict[str, float] = {}
        score = 0.0
    else:
        applied = {k: w / total for k, w in active.items()}
        score = sum(applied[k] * float(components[k]) for k in applied)

    return DisagreementReport(
        score=_clip01(score),
        n_variants=len(preds),
        structure_disagreement=structure_dis,
        shift_disagreement=shift_dis,
        confidence_spread=confidence_spread,
        mean_shift_std_ppm=mean_std,
        weights=applied,
        top1_structures=top1,
    )


def disagreement_score(
    spectrum: Any,
    *,
    variants: Sequence[ModelVariant],
    weights: Mapping[str, float] | None = None,
    shift_scale_ppm: float = DEFAULT_SHIFT_DISAGREEMENT_SCALE_PPM,
) -> float:
    """Run the model ``variants`` on ``spectrum`` and return their disagreement.

    Each variant is a callable ``variant(spectrum) -> VariantPrediction``. The
    Roadmap wires three — the Prompt 6 pretrained predictor, the Prompt 15
    fine-tuned adapter, and the Prompt 14 RAG reasoner (see :func:`routed_variant`
    and :func:`rag_variant`) — but any ``>= 2`` are accepted. High return value ==
    high information value == prioritise for expert annotation.
    """

    materialized = list(variants)
    if len(materialized) < 2:
        raise ActiveLearningError("disagreement_score needs at least 2 model variants")
    predictions = [v(spectrum) for v in materialized]
    return score_disagreement(
        predictions, weights=weights, shift_scale_ppm=shift_scale_ppm
    ).score


# -- Variant adapters over the real Roadmap models (thin + injectable) -------- #
def routed_variant(
    router: Any,
    candidate_smiles: str,
    *,
    name: str,
    nuclei: Sequence[str] = ("1H", "13C"),
    device: str | None = None,
) -> ModelVariant:
    """A variant that scores a fixed candidate structure through an inference router.

    Wraps :meth:`InferenceRouter.predict_shifts_routed` (Prompt 13/15): the same
    router with vs. without a registered LoRA adapter yields the "pretrained" and
    "fine-tuned" variants. Confidence is derived from the mean per-atom
    uncertainty (tighter ensemble == higher confidence). The ``spectrum`` argument
    is unused here (the candidate structure is fixed); it keeps the uniform
    ``variant(spectrum)`` signature.
    """

    def _variant(spectrum: Any) -> VariantPrediction:
        routed = router.predict_shifts_routed(candidate_smiles, tuple(nuclei), device=device)
        shifts = tuple(float(p.predicted_ppm) for p in routed.predictions)
        uncertainties = [
            float(p.uncertainty_ppm)
            for p in routed.predictions
            if math.isfinite(float(p.uncertainty_ppm))
        ]
        mean_unc = sum(uncertainties) / len(uncertainties) if uncertainties else float("inf")
        confidence = math.exp(-mean_unc) if math.isfinite(mean_unc) else 0.0
        return VariantPrediction(
            variant=name,
            top1_structure=candidate_smiles,
            predicted_shifts=shifts,
            confidence=_clip01(confidence),
        )

    return _variant


def rag_variant(
    context: Any,
    *,
    name: str = "rag_reasoner",
    propose_fn: Callable[..., Any] | None = None,
    **propose_kwargs: Any,
) -> ModelVariant:
    """A variant that proposes a top-1 structure via the Prompt 14 RAG reasoner.

    Wraps :func:`~moltrace.spectroscopy.ai.rag.propose_structures` (imported
    lazily so this module stays light): the top-1 is the highest-posterior
    verifier-accepted candidate, and the confidence is that posterior. ``propose_fn``
    is injectable for tests; the default is the real reasoner.
    """

    def _variant(spectrum: Any) -> VariantPrediction:
        proposer = propose_fn
        if proposer is None:
            from moltrace.spectroscopy.ai.rag import propose_structures as proposer
        result = proposer(spectrum, context, **propose_kwargs)
        accepted = list(getattr(result, "accepted", []) or [])
        if not accepted:
            return VariantPrediction(variant=name, top1_structure=None, confidence=0.0)
        best = accepted[0]
        return VariantPrediction(
            variant=name,
            top1_structure=getattr(best, "smiles", None),
            confidence=_clip01(float(getattr(best, "posterior_confidence", 0.0) or 0.0)),
        )

    return _variant


# --------------------------------------------------------------------------- #
# 3. Annotation queue
# --------------------------------------------------------------------------- #
def _candidate_record_hash(candidate: Any) -> str:
    record_hash = getattr(candidate, "record_hash", None)
    if not record_hash:
        raise ActiveLearningError("each candidate must expose a non-empty record_hash")
    return str(record_hash)


def _candidate_spectrum(candidate: Any) -> Any:
    """The spectrum to score: ``candidate.spectrum`` if present, else the candidate."""

    return getattr(candidate, "spectrum", candidate)


def _default_fingerprint(candidate: Any) -> Any:
    """Default near-duplicate key: an explicit ``fingerprint`` attribute, or None."""

    return getattr(candidate, "fingerprint", None)


def _is_near_duplicate(
    candidate: Any,
    record_hash: str,
    kept: Sequence[tuple[Any, ActiveLearningItem]],
    *,
    fingerprint_fn: Callable[[Any], Any],
    similarity_fn: Callable[[Any, Any], float] | None,
    threshold: float,
) -> bool:
    """True when ``candidate`` is a near-duplicate of an already-kept candidate.

    With a ``similarity_fn`` this is true similarity clustering (``>= threshold``);
    otherwise it falls back to fingerprint equality, and — when no fingerprint
    signal exists — to exact ``record_hash`` collisions so duplicates never double-
    spend the budget.
    """

    if similarity_fn is not None:
        return any(float(similarity_fn(candidate, kc)) >= threshold for kc, _ in kept)
    fingerprint = fingerprint_fn(candidate)
    if fingerprint is None:
        return any(item.record_hash == record_hash for _, item in kept)
    return any(fingerprint_fn(kc) == fingerprint for kc, _ in kept)


def build_annotation_queue(
    candidate_pool: Iterable[Any],
    budget: int,
    *,
    variants: Sequence[ModelVariant] | None = None,
    score_fn: Callable[[Any], float] | None = None,
    fingerprint_fn: Callable[[Any], Any] = _default_fingerprint,
    similarity_fn: Callable[[Any, Any], float] | None = None,
    dedup_threshold: float = DEFAULT_DEDUP_THRESHOLD,
    reward_fn: Callable[[Any], float] | None = None,
    reward_weight: float = 0.5,
    reason: str = "disagreement_sampling",
    weights: Mapping[str, float] | None = None,
    shift_scale_ppm: float = DEFAULT_SHIFT_DISAGREEMENT_SCALE_PPM,
    clock: Callable[[], str] = _now_iso,
) -> list[PrioritizedItem]:
    """Rank a candidate pool by disagreement, de-duplicate, and slice to ``budget``.

    Each candidate is scored — by ``score_fn`` if given, else by
    :func:`disagreement_score` over ``variants`` — and the score becomes the
    ``severity`` of an :class:`ActiveLearningItem`. Near-identical candidates are
    dropped greedily (highest severity wins), then the survivors are ordered by
    the Prompt 23 :func:`prioritize_annotation_queue` (severity, optionally blended
    with ``1 - sigmoid(reward)`` when a ``reward_fn`` is supplied), and the top
    ``budget`` are returned. This focuses scarce expert time on the examples that
    will most improve the model.
    """

    if budget < 0:
        raise ActiveLearningError("budget must be >= 0")
    if variants is None and score_fn is None:
        raise ActiveLearningError("provide either variants or a score_fn to score candidates")

    variant_list = list(variants) if variants is not None else None
    default_created = clock()

    scored: list[tuple[Any, ActiveLearningItem]] = []
    for candidate in candidate_pool:
        record_hash = _candidate_record_hash(candidate)
        if score_fn is not None:
            severity = float(score_fn(candidate))
        else:
            assert variant_list is not None  # guarded above
            severity = disagreement_score(
                _candidate_spectrum(candidate),
                variants=variant_list,
                weights=weights,
                shift_scale_ppm=shift_scale_ppm,
            )
        item = ActiveLearningItem(
            record_hash=record_hash,
            reason=reason,
            severity=_clip01(severity),
            kinds=(reason,),
            created_utc=str(getattr(candidate, "created_utc", None) or default_created),
        )
        scored.append((candidate, item))

    # Greedy de-dup in descending severity so the most-informative member of each
    # near-duplicate cluster is the one retained.
    scored.sort(key=lambda pair: (-pair[1].severity, pair[1].record_hash))
    kept: list[tuple[Any, ActiveLearningItem]] = []
    for candidate, item in scored:
        if _is_near_duplicate(
            candidate,
            item.record_hash,
            kept,
            fingerprint_fn=fingerprint_fn,
            similarity_fn=similarity_fn,
            threshold=dedup_threshold,
        ):
            continue
        kept.append((candidate, item))

    prioritized = prioritize_annotation_queue(
        [item for _, item in kept],
        reward_fn=reward_fn,
        reward_weight=reward_weight,
    )
    return prioritized[:budget]


# --------------------------------------------------------------------------- #
# 4. Retraining trigger (schedule OR volume) — wired to Prompt 15
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetrainingDecision:
    """Whether to retrain now, and why (so the trigger is auditable, not magic)."""

    should_retrain: bool
    reason: str  # 'volume' | 'schedule' | 'volume+schedule' | 'bootstrap' | 'not_yet'
    new_labels: int
    min_new_labels: int
    days_since_last: float | None
    schedule_days: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "should_retrain": self.should_retrain,
            "reason": self.reason,
            "new_labels": self.new_labels,
            "min_new_labels": self.min_new_labels,
            "days_since_last": self.days_since_last,
            "schedule_days": self.schedule_days,
        }


def evaluate_retraining(
    *,
    new_labeled_examples: int,
    last_finetune_utc: str | None = None,
    now_utc: str | None = None,
    min_new_labels: int = DEFAULT_RETRAIN_MIN_NEW_LABELS,
    schedule_days: int = DEFAULT_RETRAIN_SCHEDULE_DAYS,
) -> RetrainingDecision:
    """Decide whether to kick off a fine-tune: monthly schedule OR enough new labels.

    Fires when ``new_labeled_examples >= min_new_labels`` (volume) OR at least
    ``schedule_days`` have elapsed since ``last_finetune_utc`` (schedule). When no
    adapter has ever been trained (``last_finetune_utc is None``) the schedule leg
    cannot elapse, so the first fine-tune is gated purely on volume (``bootstrap``).
    """

    new_labels = max(0, int(new_labeled_examples))
    volume_due = new_labels >= min_new_labels

    days_since_last: float | None = None
    last_dt = _parse_iso(last_finetune_utc)
    if last_dt is not None:
        now_dt = _parse_iso(now_utc) or datetime.now(UTC)
        days_since_last = (now_dt - last_dt).total_seconds() / 86400.0
    schedule_due = days_since_last is not None and days_since_last >= schedule_days

    should = volume_due or schedule_due
    if volume_due and schedule_due:
        reason = "volume+schedule"
    elif schedule_due:
        reason = "schedule"
    elif volume_due:
        reason = "bootstrap" if last_dt is None else "volume"
    else:
        reason = "not_yet"

    return RetrainingDecision(
        should_retrain=should,
        reason=reason,
        new_labels=new_labels,
        min_new_labels=min_new_labels,
        days_since_last=days_since_last,
        schedule_days=schedule_days,
    )


def retraining_trigger(
    *,
    new_labeled_examples: int,
    last_finetune_utc: str | None = None,
    now_utc: str | None = None,
    min_new_labels: int = DEFAULT_RETRAIN_MIN_NEW_LABELS,
    schedule_days: int = DEFAULT_RETRAIN_SCHEDULE_DAYS,
) -> bool:
    """``True`` when a retrain should fire now (see :func:`evaluate_retraining`)."""

    return evaluate_retraining(
        new_labeled_examples=new_labeled_examples,
        last_finetune_utc=last_finetune_utc,
        now_utc=now_utc,
        min_new_labels=min_new_labels,
        schedule_days=schedule_days,
    ).should_retrain


def kickoff_finetune(
    examples: Iterable[Any],
    *,
    base_model_id: str,
    registry: Any,
    gold_set: Any,
    candidate_bundle: Any,
    splits: Any | None = None,
    trainer: Any | None = None,
    k_folds: int = 5,
    seed: int = 0,
    semantic_version: str = "0.1.0",
    nucleus: str | None = None,
    incumbent_metrics: Any | None = None,
    incumbent_bundle: Any | None = None,
    tolerances: Mapping[str, float] | None = None,
    max_ece: float | None = None,
    calibration_head: Any | None = None,
    dataset_tag: str | None = None,
    source: str | None = None,
    git_sha: str | None = None,
    created_utc: str | None = None,
) -> str | None:
    """Run the Prompt 15 pipeline on the accumulated labeled examples.

    The concrete "wired to Prompt 15" seam: freeze the examples into an immutable
    snapshot bound to the gold set (:func:`build_training_snapshot`), train a LoRA
    adapter with K-fold CV (:func:`finetune_lora`), and gate-then-register it
    (:func:`register_if_eligible`) — returning the registered ``model_id`` (or
    ``None`` if no adapter was produced). The training backend (``trainer``) is
    injectable, so the chain is exercisable without torch.
    """

    gold_checksum = gold_set.checksum() if hasattr(gold_set, "checksum") else None
    snapshot = build_training_snapshot(
        examples,
        splits=splits,
        gold_checksum=gold_checksum,
        git_sha=git_sha,
        created_utc=created_utc,
    )
    run = finetune_lora(
        snapshot,
        base_model_id,
        k_folds=k_folds,
        splits=splits,
        trainer=trainer,
        seed=seed,
        semantic_version=semantic_version,
        nucleus=nucleus,
        git_sha=git_sha,
        created_utc=created_utc,
    )
    return register_if_eligible(
        run,
        registry=registry,
        gold_set=gold_set,
        candidate_bundle=candidate_bundle,
        incumbent_metrics=incumbent_metrics,
        incumbent_bundle=incumbent_bundle,
        tolerances=tolerances,
        max_ece=max_ece,
        calibration_head=calibration_head,
        k=k_folds,
        dataset_tag=dataset_tag,
        source=source,
    )


def maybe_kickoff_retrain(
    decision: RetrainingDecision,
    *,
    kickoff: Callable[[], Any],
) -> Any | None:
    """Invoke ``kickoff`` (e.g. :func:`kickoff_finetune`) iff the trigger fired.

    Returns the kickoff's result when it ran, else ``None`` — so a caller can wire
    ``retraining_trigger`` straight to the Prompt 15 pipeline with no extra
    branching. Raises :class:`FineTuneError` is left to propagate from ``kickoff``.
    """

    if not decision.should_retrain:
        return None
    return kickoff()


# --------------------------------------------------------------------------- #
# 5. Loop-yield instrumentation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RetrainEvent:
    """One completed retrain, reduced to the accuracy metric we track lift on."""

    model_version: str
    created_utc: str
    primary_metric: float  # e.g. ¹H MAE in ppm
    metric_name: str = "mae_1h_ppm"
    higher_is_better: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "created_utc": self.created_utc,
            "primary_metric": self.primary_metric,
            "metric_name": self.metric_name,
            "higher_is_better": self.higher_is_better,
        }


@dataclass(frozen=True)
class LoopYieldMetrics:
    """The active-learning loop's yield — the numbers the Prompt 18 dashboard shows.

    ``override_rate_trend`` is ``recent - prior`` over consecutive windows: a
    *negative* trend means reviewers override less often, i.e. the model is getting
    better. ``accuracy_lift_*`` are improvements in the tracked accuracy metric
    across retrains (positive == better, regardless of metric direction).
    """

    n_events: int
    labeled_examples_total: int
    labeled_examples_per_month: float
    override_rate: float
    override_rate_recent: float | None
    override_rate_prior: float | None
    override_rate_trend: float | None
    n_retrains: int
    accuracy_lift_last_retrain: float | None
    accuracy_lift_total: float | None
    window_days: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_events": self.n_events,
            "labeled_examples_total": self.labeled_examples_total,
            "labeled_examples_per_month": self.labeled_examples_per_month,
            "override_rate": self.override_rate,
            "override_rate_recent": self.override_rate_recent,
            "override_rate_prior": self.override_rate_prior,
            "override_rate_trend": self.override_rate_trend,
            "n_retrains": self.n_retrains,
            "accuracy_lift_last_retrain": self.accuracy_lift_last_retrain,
            "accuracy_lift_total": self.accuracy_lift_total,
            "window_days": self.window_days,
        }


def _override_rate(events: Sequence[FeedbackEvent]) -> float | None:
    if not events:
        return None
    return usage_analytics(events).override_rate


def _lift(earlier: RetrainEvent, later: RetrainEvent) -> float:
    """Improvement from ``earlier`` to ``later`` (positive == better)."""

    delta = later.primary_metric - earlier.primary_metric
    return delta if later.higher_is_better else -delta


def loop_yield_metrics(
    events: Iterable[FeedbackEvent],
    *,
    retrains: Sequence[RetrainEvent] = (),
    now_utc: str | None = None,
    window_days: int = DEFAULT_METRICS_WINDOW_DAYS,
) -> LoopYieldMetrics:
    """Roll up the loop's yield from captured feedback events + retrain history.

    * ``labeled_examples_per_month`` — corrections (overrides carrying ground
      truth) in the trailing ``window_days``, scaled to a 30-day month.
    * ``override_rate_trend`` — the override rate in the most recent window minus
      the one before it (negative == improving).
    * ``accuracy_lift_*`` — the tracked accuracy improvement of the last retrain vs.
      its predecessor, and across the whole retrain history.

    Timestamps that don't parse as ISO-8601 are excluded from the windowed rates
    (they still count toward totals), so opaque ``created_utc`` markers degrade
    gracefully instead of raising.
    """

    all_events = list(events)
    analytics: UsageAnalytics = usage_analytics(all_events)
    labeled_total = analytics.n_corrections

    now_dt = _parse_iso(now_utc) or datetime.now(UTC)
    recent_start = now_dt.timestamp() - window_days * 86400.0
    prior_start = now_dt.timestamp() - 2 * window_days * 86400.0

    recent: list[FeedbackEvent] = []
    prior: list[FeedbackEvent] = []
    labeled_in_window = 0
    for event in all_events:
        dt = _parse_iso(event.created_utc)
        if dt is None:
            continue
        ts = dt.timestamp()
        if ts >= recent_start:
            recent.append(event)
            if event.to_labeled_example() is not None:
                labeled_in_window += 1
        elif ts >= prior_start:
            prior.append(event)

    per_month = (labeled_in_window / window_days) * 30.0 if window_days > 0 else 0.0
    override_recent = _override_rate(recent)
    override_prior = _override_rate(prior)
    trend = (
        override_recent - override_prior
        if override_recent is not None and override_prior is not None
        else None
    )

    # Chronological order (ISO-8601 created_utc sorts lexicographically); lift is
    # measured across consecutive retrains and end-to-end.
    ordered = sorted(retrains, key=lambda r: r.created_utc)
    lift_last = _lift(ordered[-2], ordered[-1]) if len(ordered) >= 2 else None
    lift_total = _lift(ordered[0], ordered[-1]) if len(ordered) >= 2 else None

    return LoopYieldMetrics(
        n_events=len(all_events),
        labeled_examples_total=labeled_total,
        labeled_examples_per_month=per_month,
        override_rate=analytics.override_rate,
        override_rate_recent=override_recent,
        override_rate_prior=override_prior,
        override_rate_trend=trend,
        n_retrains=len(ordered),
        accuracy_lift_last_retrain=lift_last,
        accuracy_lift_total=lift_total,
        window_days=window_days,
    )


def emit_loop_yield(
    metrics: LoopYieldMetrics,
    *,
    recorder: Any | None = None,
    user_id: str = "system",
    operation: str = "ai.active_learning.loop_yield",
) -> Any | None:
    """Write the loop-yield rollup to the Prompt 12 audit trail (for Prompt 18).

    Uses the supplied ``recorder`` or the process-wide default
    (:func:`~moltrace.spectroscopy.audit.trail.get_default_recorder`); returns the
    signed :class:`AuditEntry`, or ``None`` when no recorder is configured (a
    no-op so metrics computation never depends on an audit backend being wired).
    """

    sink = recorder if recorder is not None else get_default_recorder()
    if sink is None:
        return None
    return sink.record(
        operation=operation,
        user_id=user_id,
        input_obj={"window_days": metrics.window_days, "n_events": metrics.n_events},
        result_obj=metrics.as_dict(),
        parameters={"window_days": metrics.window_days},
    )
