"""RLHF reward / preference model (Prompt 23, Roadmap Phases 5-6).

The Prompt 23 feedback intake (:mod:`.capture`) turns every reviewer click into a
structured signal. This module turns that *stream of signals* into a **learned
preference** -- an RLHF-style reward model that scores a candidate AI output by
how likely a reviewer is to accept it. Two stages:

1. :func:`build_preference_dataset` mines the captured
   :class:`~moltrace.spectroscopy.feedback.capture.FeedbackEvent` stream for
   **(chosen, rejected) pairs**:

   * a **correction** -- a reviewer who supplied a structured ``corrected_value``
     -- yields the strongest signal: *corrected* output (chosen) is preferred over
     the *original* output (rejected); and
   * **accept / reject** thumbs on competing outputs for the *same decision*
     (e.g. rival structures for one record) yield ``accepted ≻ rejected`` pairs.

2. :func:`train_reward_model` fits a **Bradley-Terry / pairwise-logistic** reward
   ``r(x)`` so that ``P(chosen ≻ rejected) = sigmoid(r(chosen) - r(rejected))``,
   minimising ``-log sigmoid(r(chosen) - r(rejected))`` (Christiano et al. 2017;
   Ouyang et al. 2022). Training is deterministic full-batch gradient descent with
   L2 (mirroring the house :func:`ai.finetune._fit_logistic_regression`), so a run
   is reproducible by construction -- no seed, no randomness.

The model has two advisory uses:

* :func:`rank_candidates` re-orders the Prompt 14 reasoner's candidates by reward
  to surface the most likely-to-be-accepted option first; and
* :func:`prioritize_annotation_queue` orders the Prompt 16 active-learning queue so
  severe cases the model would likely get *wrong* are labelled first.

**The reward model is advisory and never arbitrates correctness.** The
deterministic Prompt 7 verifier remains the sole arbiter: :func:`rank_candidates`
keeps every verifier-accepted candidate strictly above every rejected one and lets
the reward order *only within* a verdict class. The reward sharpens the queue and
the UX; it never overrides the science.

Only numpy + the in-repo contract / versioning layers are imported, so the model
trains and scores on a CPU-only host with no heavy dependencies.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from moltrace.spectroscopy.feedback.capture import FeedbackEvent
from moltrace.spectroscopy.infra.contract import content_hash
from moltrace.spectroscopy.infra.versioning import current_git_sha

__all__ = [
    "Preference",
    "PrioritizedItem",
    "RankedByReward",
    "RewardModel",
    "RewardModelError",
    "RewardModelRun",
    "build_preference_dataset",
    "default_candidate_features",
    "prioritize_annotation_queue",
    "rank_candidates",
    "reward_scorer",
    "train_reward_model",
]

# A featurizer for a single output *value* given its capture context (e.g. a
# corrected ppm shift + the nucleus / original value in context).
ValueFeaturizer = Callable[[Any, Mapping[str, Any]], Mapping[str, float]]
# A featurizer for a single candidate object (e.g. a Prompt 14 Candidate).
CandidateFeaturizer = Callable[[Any], Mapping[str, float]]


class RewardModelError(RuntimeError):
    """Raised when a reward model cannot be built, trained, or applied."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))


# --------------------------------------------------------------------------- #
# Preference dataset
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Preference:
    """One preference pair: ``chosen`` output is preferred over ``rejected``.

    Both are ``{feature_name: value}`` vectors produced by the same featurizer.
    ``source`` records provenance (``"correction"`` or ``"accept_reject"``);
    ``weight`` lets stronger signals (e.g. explicit corrections) count for more.
    """

    chosen_features: Mapping[str, float]
    rejected_features: Mapping[str, float]
    source: str
    weight: float = 1.0
    context: Mapping[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        """Content address of the *pair* (chosen, rejected, source) for de-duping."""

        return content_hash(
            {
                "chosen": {k: float(v) for k, v in sorted(self.chosen_features.items())},
                "rejected": {k: float(v) for k, v in sorted(self.rejected_features.items())},
                "source": self.source,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "chosen_features": {k: float(v) for k, v in sorted(self.chosen_features.items())},
            "rejected_features": {k: float(v) for k, v in sorted(self.rejected_features.items())},
            "source": self.source,
            "weight": float(self.weight),
            "context": dict(self.context),
        }


def _default_group(event: FeedbackEvent) -> str:
    """Default decision group: same output kind + same record (or decision id)."""

    decision = event.record_hash or event.context.get("decision_id") or event.output_ref
    return f"{event.output_kind.value}|{decision}"


def build_preference_dataset(
    events: Iterable[FeedbackEvent],
    *,
    feature_fn: ValueFeaturizer,
    output_value_key: str = "output_value",
    group_fn: Callable[[FeedbackEvent], str] | None = None,
    include_accept_reject_pairs: bool = True,
) -> list[Preference]:
    """Mine captured feedback into a de-duplicated list of preference pairs.

    Two signal sources are extracted (both featurized through ``feature_fn``):

    * **Corrections** -- any event whose reviewer supplied a structured
      ``corrected_value`` *and* whose ``context[output_value_key]`` carries the
      original output: ``corrected ≻ original`` (source ``"correction"``).
    * **Accept / reject** -- when ``include_accept_reject_pairs`` is set, events
      that carry ``context[output_value_key]`` are bucketed by ``group_fn`` (default:
      output-kind + record) and every thumbs-up output is paired against every
      thumbs-down output in the same bucket (source ``"accept_reject"``).

    Processing is order-independent (events are sorted by id first) and the result
    is de-duplicated by :meth:`Preference.key`, so the dataset is deterministic.
    """

    ordered = sorted(events, key=lambda e: e.event_id())
    prefs: list[Preference] = []

    # 1. Corrections: corrected_value (chosen) > the original output (rejected).
    for event in ordered:
        if not event.is_correction or event.corrected_value is None:
            continue
        original = event.context.get(output_value_key)
        if original is None:
            continue
        chosen = dict(feature_fn(event.corrected_value, event.context))
        rejected = dict(feature_fn(original, event.context))
        if chosen == rejected:
            continue  # no learnable signal
        prefs.append(
            Preference(
                chosen_features=chosen,
                rejected_features=rejected,
                source="correction",
                context={"event_id": event.event_id()},
            )
        )

    # 2. Accept/reject pairs within a decision group.
    if include_accept_reject_pairs:
        key_of = group_fn or _default_group
        grouped: dict[str, list[tuple[bool, dict[str, float]]]] = defaultdict(list)
        for event in ordered:
            value = event.context.get(output_value_key)
            if value is None:
                continue
            grouped[key_of(event)].append(
                (not event.is_override, dict(feature_fn(value, event.context)))
            )
        for _, members in sorted(grouped.items()):
            ups = [feats for is_up, feats in members if is_up]
            downs = [feats for is_up, feats in members if not is_up]
            for chosen in ups:
                for rejected in downs:
                    if chosen == rejected:
                        continue
                    prefs.append(
                        Preference(
                            chosen_features=chosen,
                            rejected_features=rejected,
                            source="accept_reject",
                        )
                    )

    # De-duplicate identical pairs (deterministically keep first occurrence).
    seen: set[str] = set()
    unique: list[Preference] = []
    for pref in prefs:
        token = pref.key()
        if token in seen:
            continue
        seen.add(token)
        unique.append(pref)
    return unique


def default_candidate_features(candidate: Any) -> dict[str, float]:
    """A sensible default featurizer for a Prompt 14 :class:`~ai.rag.Candidate`.

    Uses only advisory, ranking-time signals: the model's own ``self_confidence``,
    whether the proposal is retrieval-grounded, the verifier's
    ``posterior_confidence`` (treated here purely as a feature, never as an
    override), and the number of cited analogues.
    """

    posterior = getattr(candidate, "posterior_confidence", None)
    cited = getattr(candidate, "cited_analogue_ids", None) or []
    return {
        "self_confidence": float(getattr(candidate, "self_confidence", 0.0) or 0.0),
        "retrieval_supported": 1.0 if getattr(candidate, "retrieval_supported", False) else 0.0,
        "posterior_confidence": float(posterior) if posterior is not None else 0.0,
        "n_cited_analogues": float(len(cited)),
    }


# --------------------------------------------------------------------------- #
# The reward model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RewardModel:
    """A learned Bradley-Terry reward over a fixed, standardized feature vector.

    :meth:`score` returns the raw reward ``r(x)``; only *differences* between
    candidates are meaningful (the intercept is not identifiable under pairwise
    training and is omitted). :meth:`acceptance_score` maps the reward through a
    sigmoid for a bounded ranking score -- a relative, not calibrated, probability.
    """

    feature_names: tuple[str, ...]
    weights: tuple[float, ...]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]

    def _standardize(self, features: Mapping[str, float]) -> np.ndarray:
        raw = np.array([float(features.get(name, 0.0)) for name in self.feature_names])
        return (raw - np.array(self.feature_means)) / np.array(self.feature_scales)

    def score(self, features: Mapping[str, float]) -> float:
        """The raw reward ``r(x) = w · standardize(x)`` (higher = more preferred)."""

        if not self.feature_names:
            return 0.0
        return float(self._standardize(features) @ np.array(self.weights))

    def acceptance_score(self, features: Mapping[str, float]) -> float:
        """``sigmoid(score)`` in (0, 1) -- a relative ranking score, not a calibrated
        probability (the reward has no identifiable intercept)."""

        return float(_sigmoid(np.array([self.score(features)]))[0])

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "weights": list(self.weights),
            "feature_means": list(self.feature_means),
            "feature_scales": list(self.feature_scales),
        }


@dataclass(frozen=True)
class RewardModelRun:
    """The reproducible record of training a :class:`RewardModel`."""

    model: RewardModel
    n_preferences: int
    feature_names: tuple[str, ...]
    pairwise_accuracy: float
    final_loss: float
    l2: float
    lr: float
    epochs: int
    source_histogram: Mapping[str, int]
    git_sha: str
    created_utc: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.as_dict(),
            "n_preferences": self.n_preferences,
            "feature_names": list(self.feature_names),
            "pairwise_accuracy": self.pairwise_accuracy,
            "final_loss": self.final_loss,
            "l2": self.l2,
            "lr": self.lr,
            "epochs": self.epochs,
            "source_histogram": dict(sorted(self.source_histogram.items())),
            "git_sha": self.git_sha,
            "created_utc": self.created_utc,
        }


def _stack_matrices(
    prefs: Sequence[Preference], names: Sequence[str]
) -> tuple[np.ndarray, np.ndarray]:
    chosen = np.array([[float(p.chosen_features.get(n, 0.0)) for n in names] for p in prefs])
    rejected = np.array([[float(p.rejected_features.get(n, 0.0)) for n in names] for p in prefs])
    return chosen, rejected


def _fit_reward_weights(
    diffs: np.ndarray,
    weights: np.ndarray,
    sample_weights: np.ndarray,
    *,
    l2: float,
    lr: float,
    epochs: int,
) -> np.ndarray:
    """Deterministic full-batch Bradley-Terry fit (numpy GD with L2).

    Minimises ``-mean(w · log sigmoid(diffs · weights)) + (l2/2)·||weights||^2``,
    where each row of ``diffs`` is ``standardize(chosen) - standardize(rejected)``.
    No randomness -- reproducible by construction.
    """

    n = max(1, diffs.shape[0])
    wsum = float(np.sum(sample_weights)) or 1.0
    for _ in range(epochs):
        prob = _sigmoid(diffs @ weights)
        grad = -(diffs.T @ (sample_weights * (1.0 - prob))) / wsum + l2 * weights / n
        weights = weights - lr * grad
    return weights


def train_reward_model(
    preferences: Iterable[Preference],
    *,
    feature_names: Sequence[str] | None = None,
    l2: float = 1.0,
    lr: float = 0.5,
    epochs: int = 2000,
    git_sha: str | None = None,
    clock: Callable[[], str] = _now_iso,
) -> RewardModelRun:
    """Fit a Bradley-Terry reward model on a preference dataset.

    ``feature_names`` defaults to the sorted union of every feature seen across all
    pairs. Features are standardized (mean/scale fit on the pooled chosen+rejected
    rows); the per-feature mean cancels in every pairwise difference, so only the
    scale affects training. Raises :class:`RewardModelError` on an empty dataset.
    """

    prefs = list(preferences)
    if not prefs:
        raise RewardModelError("cannot train a reward model on an empty preference dataset")

    if feature_names is None:
        keys: set[str] = set()
        for pref in prefs:
            keys.update(pref.chosen_features)
            keys.update(pref.rejected_features)
        names = tuple(sorted(keys))
    else:
        names = tuple(feature_names)
    if not names:
        raise RewardModelError("no features found in the preference dataset")

    chosen, rejected = _stack_matrices(prefs, names)
    pooled = np.vstack([chosen, rejected])
    means = pooled.mean(axis=0)
    scales = pooled.std(axis=0)
    scales = np.where(scales < 1e-8, 1.0, scales)

    diffs = (chosen - means) / scales - (rejected - means) / scales
    sample_weights = np.array([float(p.weight) for p in prefs])
    weights = _fit_reward_weights(
        diffs, np.zeros(len(names)), sample_weights, l2=l2, lr=lr, epochs=epochs
    )

    margins = diffs @ weights
    prob = _sigmoid(margins)
    final_loss = float(-np.mean(np.log(np.clip(prob, 1e-12, 1.0))))
    pairwise_accuracy = float(
        np.mean(np.where(margins > 0, 1.0, np.where(margins < 0, 0.0, 0.5)))
    )

    source_hist: dict[str, int] = {}
    for pref in prefs:
        source_hist[pref.source] = source_hist.get(pref.source, 0) + 1

    model = RewardModel(
        feature_names=names,
        weights=tuple(float(x) for x in weights),
        feature_means=tuple(float(x) for x in means),
        feature_scales=tuple(float(x) for x in scales),
    )
    return RewardModelRun(
        model=model,
        n_preferences=len(prefs),
        feature_names=names,
        pairwise_accuracy=pairwise_accuracy,
        final_loss=final_loss,
        l2=float(l2),
        lr=float(lr),
        epochs=int(epochs),
        source_histogram=dict(sorted(source_hist.items())),
        git_sha=git_sha if git_sha is not None else current_git_sha(),
        created_utc=clock(),
    )


# --------------------------------------------------------------------------- #
# Advisory candidate ranking (verifier still arbitrates)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RankedByReward:
    """A candidate annotated with its advisory reward and verifier verdict."""

    candidate: Any
    reward: float
    accepted: bool  # the Prompt 7 verifier's verdict -- authoritative
    rank: int

    def as_dict(self) -> dict[str, Any]:
        ref = getattr(self.candidate, "smiles", None)
        return {
            "candidate_ref": ref if ref is not None else repr(self.candidate),
            "reward": self.reward,
            "accepted": self.accepted,
            "rank": self.rank,
        }


def _default_accepted(candidate: Any) -> bool:
    return bool(getattr(candidate, "accepted", False))


def rank_candidates(
    candidates: Iterable[Any],
    model: RewardModel,
    *,
    feature_fn: CandidateFeaturizer = default_candidate_features,
    accepted_fn: Callable[[Any], bool] = _default_accepted,
    respect_verifier: bool = True,
) -> list[RankedByReward]:
    """Order candidates by advisory reward, **without overriding the verifier**.

    When ``respect_verifier`` is set (the default), every verifier-*accepted*
    candidate is ranked strictly above every *rejected* one; the reward only orders
    candidates *within* the same verdict class. The reward thus reprioritises what
    the science already permits -- it can never promote a verifier-rejected
    structure above an accepted one. Set ``respect_verifier=False`` only for offline
    analysis of the reward signal in isolation.
    """

    scored = [
        (candidate, model.score(feature_fn(candidate)), bool(accepted_fn(candidate)))
        for candidate in candidates
    ]
    if respect_verifier:
        scored.sort(key=lambda row: (row[2], row[1]), reverse=True)
    else:
        scored.sort(key=lambda row: row[1], reverse=True)
    return [
        RankedByReward(candidate=candidate, reward=float(reward), accepted=accepted, rank=index)
        for index, (candidate, reward, accepted) in enumerate(scored)
    ]


# --------------------------------------------------------------------------- #
# Annotation-queue prioritization (Prompt 16)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PrioritizedItem:
    """An active-learning item annotated with its computed labelling priority."""

    item: Any
    priority: float
    predicted_acceptance: float | None
    severity: float
    rank: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_hash": getattr(self.item, "record_hash", None),
            "priority": self.priority,
            "predicted_acceptance": self.predicted_acceptance,
            "severity": self.severity,
            "rank": self.rank,
        }


def _default_severity(item: Any) -> float:
    return float(getattr(item, "severity", 0.0) or 0.0)


def _record_key(item: Any) -> str:
    return str(getattr(item, "record_hash", "") or "")


def reward_scorer(model: RewardModel, feature_fn: CandidateFeaturizer) -> Callable[[Any], float]:
    """Compose a ``model`` + ``feature_fn`` into a single ``obj -> reward`` callable.

    Pass the result as ``reward_fn`` to :func:`prioritize_annotation_queue` when the
    queued objects can be featurized for the reward model.
    """

    def _score(obj: Any) -> float:
        return model.score(feature_fn(obj))

    return _score


def prioritize_annotation_queue(
    items: Iterable[Any],
    *,
    reward_fn: Callable[[Any], float] | None = None,
    severity_fn: Callable[[Any], float] = _default_severity,
    reward_weight: float = 0.5,
) -> list[PrioritizedItem]:
    """Order an active-learning queue so the most informative items are labelled first.

    Priority blends two signals in ``[0, 1]``: the item's ``severity`` and (when a
    ``reward_fn`` is supplied) ``1 - sigmoid(reward)`` -- i.e. how likely the model
    is to be *wrong*. Severe cases the reward model would likely get wrong rise to
    the top. With no ``reward_fn`` this degrades gracefully to pure severity order.
    ``reward_weight`` (in ``[0, 1]``) is the convex weight on the reward term.
    """

    if not 0.0 <= reward_weight <= 1.0:
        raise RewardModelError("reward_weight must be in [0, 1]")

    rows: list[tuple[Any, float, float | None, float]] = []
    for item in items:
        severity = float(severity_fn(item))
        if reward_fn is None:
            predicted_acceptance: float | None = None
            priority = severity
        else:
            reward = float(reward_fn(item))
            predicted_acceptance = float(_sigmoid(np.array([reward]))[0])
            priority = (1.0 - reward_weight) * severity + reward_weight * (
                1.0 - predicted_acceptance
            )
        rows.append((item, priority, predicted_acceptance, severity))

    rows.sort(key=lambda row: (-row[1], _record_key(row[0])))
    return [
        PrioritizedItem(
            item=item,
            priority=float(priority),
            predicted_acceptance=predicted_acceptance,
            severity=float(severity),
            rank=index,
        )
        for index, (item, priority, predicted_acceptance, severity) in enumerate(rows)
    ]
