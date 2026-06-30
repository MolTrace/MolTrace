"""Repho R10 — warm-start transfer-learning priors (pure, frozen, content-addressed).

A new optimisation campaign should need fewer experiments when it can warm-start from accumulated,
SpectraCheck-verified data on *related* chemistry. This engine does two things, deterministically:

1. ``build_snapshot`` freezes accumulated campaign observations into an **immutable, content-hashed
   snapshot** (DVC-style) with **mandatory lineage**. Two integrity rules are enforced here, not
   downstream: only **verified** observations are admitted, and any observation in the **R11 gold
   set is excluded by id (hash-exclusion)** so the warm-start prior can never train on the
   benchmark it will later be judged against.

2. ``fit_warm_start_prior`` derives an informative GP prior from a snapshot — a prior-mean function
   (a global mean plus shrinkage-smoothed per-feature offsets) and a set of relevant prior
   observations to seed a cold-start optimiser. ``prior_mean`` is the mean function; the
   ``augmentation`` is the relevant-data initialisation. It refuses a snapshot without lineage.

Pure: no DB / HTTP / clock / randomness — same inputs always produce the same snapshot hash and the
same prior. The wiring (a follow-up) reads verified campaign data, persists the snapshot + prior
(**weights/snapshots out of git** — gitignore the patterns first), and feeds ``reaction_bo``.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

ENGINE = "reaction_priors.v1"
_DEFAULT_PRIOR_STRENGTH = 4.0


@dataclass(frozen=True)
class CampaignObservation:
    """One accumulated, evaluated experiment from a (related) campaign."""

    observation_id: str
    features: Mapping[str, Any]
    objective: float
    verified: bool = False
    source_campaign: str | None = None


@dataclass
class WarmStartSnapshot:
    content_hash: str
    observations: list[dict[str, Any]]
    objective_target: float | None
    lineage: dict[str, Any]
    excluded_gold_count: int
    excluded_unverified_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "observation_count": len(self.observations),
            "objective_target": self.objective_target,
            "lineage": self.lineage,
            "excluded_gold_count": self.excluded_gold_count,
            "excluded_unverified_count": self.excluded_unverified_count,
            "engine": ENGINE,
        }


@dataclass
class WarmStartPrior:
    snapshot_hash: str
    global_mean: float
    feature_offsets: dict[str, dict[str, float]]
    augmentation: list[dict[str, Any]]
    prior_strength: float
    lineage: dict[str, Any]
    trained_n: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_hash": self.snapshot_hash,
            "global_mean": self.global_mean,
            "feature_offsets": self.feature_offsets,
            "augmentation_count": len(self.augmentation),
            "prior_strength": self.prior_strength,
            "lineage": self.lineage,
            "trained_n": self.trained_n,
            "engine": ENGINE,
        }


class ReactionPriorError(Exception):
    """Raised on an integrity violation (gold-set leak, missing lineage, empty snapshot)."""


# --------------------------------------------------------------------------- #
# 1. Snapshot — verified-only, gold-excluded, content-hashed, lineage-bearing.
# --------------------------------------------------------------------------- #
def build_snapshot(
    observations: Iterable[CampaignObservation],
    *,
    gold_set_ids: Iterable[str] = (),
    objective_target: float | None = None,
    require_verified: bool = True,
    source: str | None = None,
) -> WarmStartSnapshot:
    """Freeze accumulated campaign data into an immutable, hashed, lineage-bearing snapshot.

    Excludes any observation in ``gold_set_ids`` (hash-exclusion — the warm-start prior must never
    see the R11 gold set) and, when ``require_verified``, any unverified observation. Raises if a
    gold-set id survives filtering (fail-loud) or the snapshot would be empty.
    """

    # Ids are normalised the SAME way on both sides so a whitespace/Unicode variant of a gold id
    # is still excluded — under-exclusion would leak the benchmark, which is the worst case.
    gold = frozenset(_normalize_id(item) for item in gold_set_ids)
    target = None if objective_target is None else _canonical_number(objective_target)
    kept: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    excluded_gold = 0
    excluded_unverified = 0
    for obs in observations:
        obs_id = _normalize_id(obs.observation_id)
        if obs_id in gold:
            excluded_gold += 1
            continue
        if require_verified and not obs.verified:
            excluded_unverified += 1
            continue
        if obs_id in seen_ids:
            # observation_id is THE exclusion key; duplicates make 'exclude by id' ambiguous.
            raise ReactionPriorError(f"Duplicate observation id in snapshot input: {obs_id!r}")
        seen_ids.add(obs_id)
        kept.append(
            {
                "observation_id": obs_id,
                "features": _canonical_features(obs.features),
                "objective": _canonical_number(obs.objective),
                "source_campaign": obs.source_campaign,
            }
        )

    if not kept:
        raise ReactionPriorError("Snapshot is empty after verified/gold filtering.")

    # Ids are unique (duplicates rejected above), so sorting by id is a total order and the hash
    # is permutation-independent. Values are canonical JSON-native scalars, so the hash is faithful.
    kept.sort(key=lambda row: row["observation_id"])
    content_hash = _content_hash(kept, target)
    lineage = {
        "source": source,
        "engine": ENGINE,
        "observation_count": len(kept),
        "source_campaigns": sorted(
            {str(row["source_campaign"]) for row in kept if row["source_campaign"] is not None}
        ),
        "excluded_gold_count": excluded_gold,
        "excluded_unverified_count": excluded_unverified,
        "verified_only": require_verified,
        "gold_set_size": len(gold),
    }
    return WarmStartSnapshot(
        content_hash=content_hash,
        observations=kept,
        objective_target=target,
        lineage=lineage,
        excluded_gold_count=excluded_gold,
        excluded_unverified_count=excluded_unverified,
    )


def assert_no_gold_leakage(snapshot: WarmStartSnapshot, gold_set_ids: Iterable[str]) -> None:
    """Independent re-check that no gold-set id is present (callable by the R11 eval gate)."""

    gold = frozenset(_normalize_id(item) for item in gold_set_ids)
    leaked = sorted(
        row["observation_id"]
        for row in snapshot.observations
        if _normalize_id(row["observation_id"]) in gold
    )
    if leaked:
        raise ReactionPriorError(f"Gold-set observations present in snapshot: {leaked}")


# --------------------------------------------------------------------------- #
# 2. Warm-start prior — mean function + relevant-data augmentation.
# --------------------------------------------------------------------------- #
def fit_warm_start_prior(
    snapshot: WarmStartSnapshot,
    *,
    prior_strength: float = _DEFAULT_PRIOR_STRENGTH,
    max_augmentation: int | None = None,
) -> WarmStartPrior:
    """Derive an informative prior from a snapshot.

    The prior-mean function is a global mean plus shrinkage-smoothed per-feature-value offsets
    (each offset is pulled toward 0 by ``prior_strength`` pseudo-observations, so a rarely-seen
    feature value contributes little). The augmentation is the snapshot's observations, ordered
    best-objective-first, used to seed a cold-start optimiser with relevant prior evidence.
    """

    if not snapshot.lineage:
        raise ReactionPriorError("Refusing to fit a prior from a snapshot without lineage.")
    rows = snapshot.observations
    if not rows:
        raise ReactionPriorError("Cannot fit a prior from an empty snapshot.")

    objectives = [float(row["objective"]) for row in rows]
    global_mean = sum(objectives) / len(objectives)

    # Per-feature-value accumulators: sum of (objective - global_mean), count.
    sums: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        delta = float(row["objective"]) - global_mean
        for name, value in row["features"].items():
            bucket = _bucket(value)
            per_feature = sums.setdefault(str(name), {})
            acc = per_feature.setdefault(bucket, [0.0, 0.0])
            acc[0] += delta
            acc[1] += 1.0
    feature_offsets: dict[str, dict[str, float]] = {}
    for name, buckets in sums.items():
        feature_offsets[name] = {
            bucket: total / (count + prior_strength)  # shrink toward 0 for sparse buckets
            for bucket, (total, count) in buckets.items()
        }

    augmentation = sorted(rows, key=lambda row: float(row["objective"]), reverse=True)
    if max_augmentation is not None:
        augmentation = augmentation[:max_augmentation]

    return WarmStartPrior(
        snapshot_hash=snapshot.content_hash,
        global_mean=global_mean,
        feature_offsets=feature_offsets,
        augmentation=[dict(row) for row in augmentation],
        prior_strength=prior_strength,
        lineage=snapshot.lineage,
        trained_n=len(rows),
    )


def prior_mean(prior: WarmStartPrior, features: Mapping[str, Any]) -> float:
    """The GP prior-mean at a candidate: global mean plus the mean of its known feature offsets."""

    offsets: list[float] = []
    for name, value in features.items():
        per_feature = prior.feature_offsets.get(str(name))
        if not per_feature:
            continue
        offset = per_feature.get(_bucket(value))
        if offset is not None:
            offsets.append(offset)
    if not offsets:
        return prior.global_mean
    return prior.global_mean + sum(offsets) / len(offsets)


def warm_start_initialization(
    prior: WarmStartPrior, *, max_points: int | None = None
) -> list[dict[str, Any]]:
    """The relevant prior observations (best-first) to seed a cold-start optimiser."""

    points = prior.augmentation
    if max_points is not None:
        points = points[:max_points]
    return [dict(point) for point in points]


def rank_candidates_by_prior(
    prior: WarmStartPrior, candidates: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Rank candidate conditions by the prior-mean (warm-start ordering). Ties keep input order."""

    scored: list[tuple[int, float, dict[str, Any]]] = []
    for index, candidate in enumerate(candidates):
        # Distinguish "features key absent" (the candidate IS the feature map) from "present but
        # empty" — an explicit empty dict must NOT fall back to leaking the candidate's outer keys.
        raw = candidate["features"] if "features" in candidate else candidate
        features = dict(raw or {})
        scored.append((index, prior_mean(prior, features), dict(candidate)))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [{**candidate, "prior_mean": score} for _, score, candidate in scored]


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _normalize_id(value: Any) -> str:
    """Normalise an id the same way on both sides of gold-exclusion (NFC + strip)."""

    return unicodedata.normalize("NFC", str(value)).strip()


def _canonical_number(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ReactionPriorError(f"Numeric value must be finite, got {value!r}")
    return number + 0.0  # collapse signed zero (-0.0 -> 0.0) for a stable bucket/hash


def _canonical_value(value: Any) -> Any:
    """Admit only JSON-native scalars so the content hash is a faithful, collision-free fingerprint.

    bool is checked before int (``bool`` is a subclass of ``int``). Non-native types (date, Decimal,
    bytes, list, dict, custom objects) are rejected fail-loud — the caller must pass clean
    conditions, so a date and its ISO string can never silently hash alike.
    """

    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _canonical_number(value)
    raise ReactionPriorError(
        "Feature value must be a JSON-native scalar (str/int/float/bool/None); "
        f"got {type(value).__name__}"
    )


def _canonical_features(features: Mapping[str, Any]) -> dict[str, Any]:
    return {str(name): _canonical_value(features[name]) for name in sorted(features, key=str)}


def _bucket(value: Any) -> str:
    if isinstance(value, bool):
        return f"bool:{value}"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            rounded = round(float(value), 1) + 0.0  # collapse signed zero
        except (TypeError, ValueError):
            return f"raw:{value!r}"
        return f"num:{rounded}"
    return f"cat:{value!r}"


def _content_hash(rows: list[dict[str, Any]], objective_target: float | None) -> str:
    # No default= : rows hold only canonical JSON-native scalars, so json raises (fail-loud) rather
    # than silently stringifying a non-native value into a hash collision.
    payload = json.dumps(
        {"observations": rows, "objective_target": objective_target, "engine": ENGINE},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
