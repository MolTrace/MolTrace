"""Narrative preference / reward model (Prompt 22, Phase 5) — TEXT quality only.

From accepted-vs-edited narratives, builds an RLHF-style preference dataset and trains a Bradley-
Terry reward model that scores draft quality by likely reviewer acceptance, used to rank candidate
narratives and prioritise the Prompt 16 narrative review queue.

STRICT (guard-tested): the reward scores TEXT quality ONLY. Its features are a fixed text-only
allowlist (citations present/correct, length, structure) — it can never read or influence a number,
limit, threshold, or classification (those belong to the deterministic engine). Classification /
triage feedback never enters the preference dataset. The model is a lightweight, dependency-free
logistic — no torch, runs offline.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from moltrace.regulatory.feedback.capture import FeedbackEvent, FeedbackVerdict, OutputKind

__all__ = [
    "NARRATIVE_FEATURE_NAMES",
    "NarrativeRewardModel",
    "Preference",
    "RankedNarrative",
    "RewardModelError",
    "RewardModelRun",
    "build_preference_dataset",
    "default_narrative_features",
    "prioritize_narrative_queue",
    "rank_narratives",
    "train_narrative_reward_model",
]

#: The ONLY features the narrative reward model may use — all text quality, no regulated values.
NARRATIVE_FEATURE_NAMES: tuple[str, ...] = (
    "has_citation",
    "citation_count",
    "length",
    "sentence_count",
    "avg_word_len",
)


class RewardModelError(RuntimeError):
    """Raised on an empty/invalid preference set or a non-text feature in the narrative reward."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _assert_text_only(features: Mapping[str, float]) -> None:
    extra = set(features) - set(NARRATIVE_FEATURE_NAMES)
    if extra:
        raise RewardModelError(
            f"non-text features in the narrative reward model: {sorted(extra)}; this model scores "
            "TEXT quality only and must never read a number/limit/classification"
        )


def default_narrative_features(text: Any) -> dict[str, float]:
    """Text-quality features for a narrative draft — citations, length, structure. TEXT only."""

    t = str(text)
    markers = re.findall(r"\[S\d+\]", t)
    words = re.findall(r"[A-Za-z]+", t)
    sentences = [s for s in re.split(r"[.!?]+", t) if s.strip()]
    return {
        "has_citation": 1.0 if markers else 0.0,
        "citation_count": float(len(markers)),
        "length": float(len(t)) / 1000.0,
        "sentence_count": float(len(sentences)),
        "avg_word_len": (sum(len(w) for w in words) / len(words)) if words else 0.0,
    }


@dataclass(frozen=True)
class Preference:
    """A pairwise preference: the chosen narrative is preferred over the rejected one."""

    chosen_features: Mapping[str, float]
    rejected_features: Mapping[str, float]
    source: str  # 'edit' | 'accept_reject'
    weight: float = 1.0


def build_preference_dataset(
    events: Iterable[FeedbackEvent],
    *,
    feature_fn: Callable[[Any], Mapping[str, float]] = default_narrative_features,
) -> list[Preference]:
    """Build the NARRATIVE preference dataset from feedback (accepted/edited > draft/rejected).

    Only NARRATIVE feedback contributes — classification / triage events are ignored, so a regulated
    classification can never become a narrative-reward training signal. An EDIT pairs the corrected
    text (chosen) over the draft (rejected); accepts pair over rejects within the same output_ref.
    """

    narrative = [e for e in events if e.output_kind is OutputKind.NARRATIVE]
    prefs: list[Preference] = []

    for e in narrative:
        if e.verdict is FeedbackVerdict.EDIT and e.corrected_text:
            draft = e.context.get("draft", e.output_ref)
            prefs.append(
                Preference(
                    chosen_features=dict(feature_fn(e.corrected_text)),
                    rejected_features=dict(feature_fn(draft)),
                    source="edit",
                )
            )

    # accept/reject pairs within the same output_ref bucket (an accepted draft > a rejected one)
    by_ref: dict[str, dict[str, list[FeedbackEvent]]] = {}
    for e in narrative:
        bucket = by_ref.setdefault(e.output_ref, {"accept": [], "reject": []})
        if e.verdict is FeedbackVerdict.ACCEPT:
            bucket["accept"].append(e)
        elif e.verdict is FeedbackVerdict.REJECT:
            bucket["reject"].append(e)
    for bucket in by_ref.values():
        for accepted in bucket["accept"]:
            for rejected in bucket["reject"]:
                chosen = accepted.context.get("draft", accepted.output_ref)
                rejected_text = rejected.context.get("draft", rejected.output_ref)
                prefs.append(
                    Preference(
                        chosen_features=dict(feature_fn(chosen)),
                        rejected_features=dict(feature_fn(rejected_text)),
                        source="accept_reject",
                    )
                )
    return prefs


@dataclass(frozen=True)
class NarrativeRewardModel:
    """A Bradley-Terry reward over TEXT features: higher score == more likely reviewer-accepted."""

    feature_names: tuple[str, ...]
    weights: tuple[float, ...]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]

    def _standardize(self, features: Mapping[str, float]) -> list[float]:
        _assert_text_only(features)
        return [
            (float(features.get(name, 0.0)) - mean) / scale
            for name, mean, scale in zip(
                self.feature_names, self.feature_means, self.feature_scales, strict=True
            )
        ]

    def score(self, features: Mapping[str, float]) -> float:
        """Raw reward r(x) = w · standardize(x). TEXT features only (raises otherwise)."""

        return sum(w * x for w, x in zip(self.weights, self._standardize(features), strict=True))

    def acceptance_score(self, features: Mapping[str, float]) -> float:
        """sigmoid(score) in (0, 1) — a relative likely-acceptance ranking, not calibrated."""

        return 1.0 / (1.0 + math.exp(-self.score(features)))


@dataclass(frozen=True)
class RewardModelRun:
    model: NarrativeRewardModel
    n_preferences: int
    feature_names: tuple[str, ...]
    pairwise_accuracy: float
    final_loss: float
    git_sha: str
    created_utc: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_preferences": self.n_preferences,
            "feature_names": list(self.feature_names),
            "pairwise_accuracy": self.pairwise_accuracy,
            "final_loss": self.final_loss,
            "weights": list(self.model.weights),
            "git_sha": self.git_sha,
            "created_utc": self.created_utc,
        }


def _vec(features: Mapping[str, float], names: Sequence[str]) -> list[float]:
    return [float(features.get(n, 0.0)) for n in names]


def train_narrative_reward_model(
    preferences: Iterable[Preference],
    *,
    feature_names: Sequence[str] = NARRATIVE_FEATURE_NAMES,
    l2: float = 1.0,
    lr: float = 0.5,
    epochs: int = 500,
    git_sha: str = "unknown",
    now: str | None = None,
) -> RewardModelRun:
    """Fit a Bradley-Terry pairwise-logistic reward over TEXT features (pure Python, no deps)."""

    prefs = list(preferences)
    if not prefs:
        raise RewardModelError("cannot train a reward model with no preferences")
    names = tuple(feature_names)
    _assert_text_only({n: 0.0 for n in names})  # STRICT: model features stay on the text allowlist
    for p in prefs:  # STRICT: every preference must be text-only
        _assert_text_only(p.chosen_features)
        _assert_text_only(p.rejected_features)

    all_vecs = [_vec(p.chosen_features, names) for p in prefs] + [
        _vec(p.rejected_features, names) for p in prefs
    ]
    cols = list(zip(*all_vecs, strict=True))
    means = [sum(c) / len(c) for c in cols]
    scales = [
        ((sum((x - m) ** 2 for x in c) / len(c)) ** 0.5) or 1.0
        for c, m in zip(cols, means, strict=True)
    ]

    def std(features: Mapping[str, float]) -> list[float]:
        return [
            (features.get(n, 0.0) - m) / s for n, m, s in zip(names, means, scales, strict=True)
        ]

    w = [0.0] * len(names)
    final_loss = 0.0
    for _ in range(epochs):
        grad = [0.0] * len(names)
        final_loss = 0.0
        for p in prefs:
            diff = [
                a - b
                for a, b in zip(std(p.chosen_features), std(p.rejected_features), strict=True)
            ]
            s = sum(wi * di for wi, di in zip(w, diff, strict=True))
            prob = 1.0 / (1.0 + math.exp(-s))
            final_loss += -math.log(max(prob, 1e-12)) * p.weight
            g = (prob - 1.0) * p.weight
            for j in range(len(w)):
                grad[j] += g * diff[j]
        for j in range(len(w)):
            w[j] -= lr * (grad[j] / len(prefs) + l2 * w[j] / len(prefs))

    model = NarrativeRewardModel(names, tuple(w), tuple(means), tuple(scales))
    correct = sum(
        1 for p in prefs if model.score(p.chosen_features) > model.score(p.rejected_features)
    )
    return RewardModelRun(
        model=model,
        n_preferences=len(prefs),
        feature_names=names,
        pairwise_accuracy=correct / len(prefs),
        final_loss=final_loss / len(prefs),
        git_sha=git_sha,
        created_utc=now or _now_iso(),
    )


@dataclass(frozen=True)
class RankedNarrative:
    text: str
    reward: float
    acceptance: float
    rank: int


def rank_narratives(
    candidates: Iterable[str],
    model: NarrativeRewardModel,
    *,
    feature_fn: Callable[[Any], Mapping[str, float]] = default_narrative_features,
) -> list[RankedNarrative]:
    """Rank candidate narrative TEXTS best-first by reward (text only, never a classification)."""

    scored = [
        (text, model.score(feature_fn(text)), model.acceptance_score(feature_fn(text)))
        for text in candidates
    ]
    scored.sort(key=lambda t: -t[1])
    return [RankedNarrative(text, reward, acc, i) for i, (text, reward, acc) in enumerate(scored)]


def prioritize_narrative_queue(
    candidates: Iterable[Any],
    model: NarrativeRewardModel | None = None,
    *,
    feature_fn: Callable[[Any], Mapping[str, float]] = default_narrative_features,
    text_of: Callable[[Any], str] = lambda c: " ".join(getattr(c, "variants", []) or [str(c)]),
    reward_weight: float = 0.5,
) -> list[tuple[Any, float]]:
    """Prioritise the Prompt 16 narrative review queue, most-informative first.

    Blends each candidate's disagreement (variance across its variants) with (1 - predicted
    acceptance) from the reward model — a low-acceptance draft is the most informative to review.
    With no model it degrades to pure disagreement ordering. Returns ``(candidate, priority)`` desc.
    """

    from moltrace.regulatory.ai.active_learning import narrative_disagreement

    ranked: list[tuple[Any, float]] = []
    for cand in candidates:
        variants = list(getattr(cand, "variants", []) or [])
        disagreement = narrative_disagreement(variants) if variants else 0.0
        if model is None:
            priority = disagreement
        else:
            acceptance = model.acceptance_score(feature_fn(text_of(cand)))
            priority = (1.0 - reward_weight) * disagreement + reward_weight * (1.0 - acceptance)
        ranked.append((cand, priority))
    ranked.sort(key=lambda t: -t[1])
    return ranked
