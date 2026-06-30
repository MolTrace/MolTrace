"""Unit tests for the Repho R10 warm-start priors engine (pure: no DB/HTTP/clock/randomness)."""

from __future__ import annotations

import pytest

from nmrcheck.reaction_priors import (
    CampaignObservation,
    ReactionPriorError,
    assert_no_gold_leakage,
    build_snapshot,
    fit_warm_start_prior,
    prior_mean,
    rank_candidates_by_prior,
    warm_start_initialization,
)


def _obs(oid: str, catalyst: str, objective: float, *, verified: bool = True, campaign: str = "camp-A"):
    return CampaignObservation(
        observation_id=oid,
        features={"catalyst": catalyst},
        objective=objective,
        verified=verified,
        source_campaign=campaign,
    )


# --- build_snapshot: integrity (gold exclusion, verified-only, hash, lineage) ----------------
def test_snapshot_excludes_gold_set_by_id():
    obs = [_obs("o1", "Cat-A", 80), _obs("gold-1", "Cat-A", 99), _obs("o2", "Cat-B", 40)]
    snap = build_snapshot(obs, gold_set_ids={"gold-1"})
    ids = {row["observation_id"] for row in snap.observations}
    assert ids == {"o1", "o2"}
    assert snap.excluded_gold_count == 1
    # The independent re-check also passes.
    assert_no_gold_leakage(snap, {"gold-1"})


def test_snapshot_drops_unverified_by_default():
    obs = [_obs("o1", "Cat-A", 80), _obs("o2", "Cat-B", 40, verified=False)]
    snap = build_snapshot(obs)
    assert {row["observation_id"] for row in snap.observations} == {"o1"}
    assert snap.excluded_unverified_count == 1


def test_snapshot_is_content_addressed_and_order_independent():
    a = [_obs("o1", "Cat-A", 80), _obs("o2", "Cat-B", 40)]
    b = [_obs("o2", "Cat-B", 40), _obs("o1", "Cat-A", 80)]  # same data, different order
    assert build_snapshot(a).content_hash == build_snapshot(b).content_hash
    # Changing a value changes the hash.
    c = [_obs("o1", "Cat-A", 81), _obs("o2", "Cat-B", 40)]
    assert build_snapshot(c).content_hash != build_snapshot(a).content_hash
    assert build_snapshot(a).content_hash.startswith("sha256:")


def test_snapshot_carries_mandatory_lineage():
    snap = build_snapshot([_obs("o1", "Cat-A", 80)], source="campaign-export")
    assert snap.lineage["source"] == "campaign-export"
    assert snap.lineage["observation_count"] == 1
    assert "camp-A" in snap.lineage["source_campaigns"]


def test_empty_snapshot_after_filtering_raises():
    with pytest.raises(ReactionPriorError):
        build_snapshot([_obs("o1", "Cat-A", 80, verified=False)])  # all unverified -> empty


# --- fit_warm_start_prior: prior mean + lineage gate -----------------------------------------
def test_prior_mean_reflects_feature_signal():
    # Cat-A consistently high, Cat-B consistently low.
    obs = [
        _obs("a1", "Cat-A", 85),
        _obs("a2", "Cat-A", 90),
        _obs("b1", "Cat-B", 30),
        _obs("b2", "Cat-B", 25),
    ]
    prior = fit_warm_start_prior(build_snapshot(obs))
    assert prior_mean(prior, {"catalyst": "Cat-A"}) > prior_mean(prior, {"catalyst": "Cat-B"})
    # An unseen feature value falls back to the global mean.
    assert prior_mean(prior, {"catalyst": "Cat-Z"}) == prior.global_mean


def test_fit_refuses_snapshot_without_lineage():
    snap = build_snapshot([_obs("o1", "Cat-A", 80)])
    snap.lineage = {}  # tamper: strip lineage
    with pytest.raises(ReactionPriorError):
        fit_warm_start_prior(snap)


def test_augmentation_is_best_first():
    obs = [_obs("lo", "Cat-B", 20), _obs("hi", "Cat-A", 95), _obs("mid", "Cat-C", 55)]
    prior = fit_warm_start_prior(build_snapshot(obs))
    aug = warm_start_initialization(prior)
    assert [row["observation_id"] for row in aug] == ["hi", "mid", "lo"]
    assert [row["observation_id"] for row in warm_start_initialization(prior, max_points=1)] == ["hi"]


# --- Acceptance: warm-start reaches target in fewer experiments than cold-start ---------------
def test_warm_start_reaches_target_in_fewer_experiments_than_cold_start():
    # Prior fit on a RELATED campaign where Cat-A is the winning catalyst.
    related = [
        _obs("r1", "Cat-A", 88),
        _obs("r2", "Cat-A", 92),
        _obs("r3", "Cat-B", 41),
        _obs("r4", "Cat-C", 35),
    ]
    prior = fit_warm_start_prior(build_snapshot(related))

    # A held-out NEW task with the same structure (Cat-A is best). The candidate pool is given in
    # an order where the good Cat-A candidates are NOT first, so cold-start (in-order) is slow.
    pool = [
        {"id": "c1", "features": {"catalyst": "Cat-C"}, "true_objective": 33},
        {"id": "c2", "features": {"catalyst": "Cat-B"}, "true_objective": 44},
        {"id": "c3", "features": {"catalyst": "Cat-A"}, "true_objective": 87},  # a winner, but 3rd
        {"id": "c4", "features": {"catalyst": "Cat-A"}, "true_objective": 90},
    ]
    target = 80.0

    def experiments_to_target(order: list[dict]) -> int:
        for i, candidate in enumerate(order, start=1):
            if candidate["true_objective"] >= target:
                return i
        return len(order) + 1  # never reached

    cold_start_order = pool  # evaluate in the given order (no prior knowledge)
    warm_start_order = rank_candidates_by_prior(prior, pool)  # best-predicted first

    cold = experiments_to_target(cold_start_order)
    warm = experiments_to_target(warm_start_order)
    assert warm < cold  # the warm-started campaign reaches target in fewer experiments
    assert warm == 1  # the prior puts a Cat-A winner first


# --- integrity hardening (adversarial-review regressions) ------------------------------------
def test_non_native_feature_value_is_rejected():
    import datetime

    bad = CampaignObservation("o1", {"when": datetime.date(2024, 1, 1)}, 80, verified=True)
    with pytest.raises(ReactionPriorError):
        build_snapshot([bad])
    bad2 = CampaignObservation("o2", {"lst": [1, 2]}, 80, verified=True)
    with pytest.raises(ReactionPriorError):
        build_snapshot([bad2])


def test_native_types_do_not_collide_in_hash():
    # int 1 vs str "1" as a feature value must hash differently (JSON distinguishes them).
    h_int = build_snapshot([CampaignObservation("o", {"x": 1}, 50, verified=True)]).content_hash
    h_str = build_snapshot([CampaignObservation("o", {"x": "1"}, 50, verified=True)]).content_hash
    assert h_int != h_str


def test_duplicate_observation_id_is_rejected():
    obs = [_obs("dup", "Cat-A", 10), _obs("dup", "Cat-B", 20)]
    with pytest.raises(ReactionPriorError):
        build_snapshot(obs)


def test_gold_exclusion_normalises_ids():
    # A gold id with surrounding whitespace must still exclude the matching observation.
    snap = build_snapshot([_obs("g1", "Cat-A", 80), _obs("o2", "Cat-B", 40)], gold_set_ids={" g1 "})
    assert {row["observation_id"] for row in snap.observations} == {"o2"}
    assert snap.excluded_gold_count == 1


def test_signed_zero_does_not_change_hash():
    pos = build_snapshot([CampaignObservation("o", {"x": 0.0}, 0.0, verified=True)]).content_hash
    neg = build_snapshot([CampaignObservation("o", {"x": -0.0}, -0.0, verified=True)]).content_hash
    assert pos == neg


def test_rank_with_explicit_empty_features_uses_global_mean():
    prior = fit_warm_start_prior(build_snapshot([_obs("a", "Cat-A", 90), _obs("b", "Cat-B", 30)]))
    # An explicit empty features dict must NOT leak the candidate's outer keys (id) into the score.
    ranked = rank_candidates_by_prior(prior, [{"id": "z", "features": {}}])
    assert ranked[0]["prior_mean"] == prior.global_mean


def test_rank_candidates_attaches_prior_mean_and_is_deterministic():
    prior = fit_warm_start_prior(build_snapshot([_obs("a", "Cat-A", 90), _obs("b", "Cat-B", 30)]))
    pool = [{"id": "x", "features": {"catalyst": "Cat-B"}}, {"id": "y", "features": {"catalyst": "Cat-A"}}]
    ranked = rank_candidates_by_prior(prior, pool)
    assert [c["id"] for c in ranked] == ["y", "x"]
    assert all("prior_mean" in c for c in ranked)
    assert rank_candidates_by_prior(prior, pool) == ranked  # deterministic
