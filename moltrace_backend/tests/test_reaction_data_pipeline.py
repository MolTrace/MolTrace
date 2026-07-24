"""Unit tests for the Phase-C data pipeline (pure; license gate, splits, leak checks)."""

from __future__ import annotations

import pytest

from nmrcheck.reaction_data_pipeline import (
    LICENSE_REGISTRY,
    ReactionDataError,
    ReactionRecord,
    assert_no_benchmark_leakage,
    assert_usage_allowed,
    assign_splits,
    validate_records,
    verify_manifest,
)


# --- license gate (fail-closed) ---------------------------------------------------------------
def test_unknown_dataset_is_refused():
    with pytest.raises(ReactionDataError, match="not in the license registry"):
        assert_usage_allowed("mystery_corpus", "training")


def test_commercial_corpora_are_prohibited():
    for dataset in ("reaxys", "pistachio", "brethericks"):
        with pytest.raises(ReactionDataError, match="prohibited"):
            assert_usage_allowed(dataset, "benchmark")


def test_benchmark_only_datasets_refuse_training_but_allow_benchmark():
    with pytest.raises(ReactionDataError, match="benchmark-only"):
        assert_usage_allowed("buchwald_hartwig_hte", "training")
    with pytest.raises(ReactionDataError, match="benchmark-only"):
        assert_usage_allowed("suzuki_miyaura_hte", "warm_start")
    entry = assert_usage_allowed("buchwald_hartwig_hte", "benchmark")
    assert entry.usage == "benchmark_only"


def test_open_datasets_allow_training():
    entry = assert_usage_allowed("ord", "training")
    assert entry.share_alike is True  # CC-BY-SA is carried on the registry entry
    assert_usage_allowed("uspto_50k", "training")


def test_unknown_purpose_is_refused():
    with pytest.raises(ReactionDataError, match="Unknown data purpose"):
        assert_usage_allowed("ord", "vibes")


# --- record validation ------------------------------------------------------------------------
def _record(rid: str, *, smiles: str = "CCO", y: float | None = 80.0, dataset: str = "ord"):
    return ReactionRecord(
        record_id=rid,
        dataset=dataset,
        reactants_smiles=(smiles,),
        products_smiles=("CCOC(C)=O",),
        yield_percent=y,
    )


def test_validate_canonicalises_and_keeps_good_rows():
    valid, rejected = validate_records([_record("r1", smiles="OCC")])  # OCC == CCO
    assert rejected == []
    assert valid[0].reactants_smiles == ("CCO",)  # canonical form


def test_validate_rejects_duplicates_bad_yield_unknown_dataset_and_bad_smiles():
    rows = [
        _record("r1"),
        _record("r1"),  # duplicate id
        _record("r2", y=float("nan")),
        _record("r3", y=250.0),
        _record("r4", dataset="mystery"),
        _record("r5", smiles="not-a-smiles"),
    ]
    valid, rejected = validate_records(rows)
    assert [r.record_id for r in valid] == ["r1"]
    reasons = {item["record_id"]: " ".join(item["reasons"]) for item in rejected}
    assert "duplicate" in reasons["r1"]
    assert "non-finite" in reasons["r2"]
    assert "out of range" in reasons["r3"]
    # Unknown datasets are now refused by the license gate itself, not a softer local check.
    assert "not in the license registry" in reasons["r4"]
    assert "unparseable" in reasons["r5"]


# --- frozen splits + benchmark hold-out --------------------------------------------------------
_IDS = [f"rec-{i:03d}" for i in range(60)]


def test_splits_are_deterministic_and_order_independent():
    a = assign_splits(_IDS, seed=7)
    b = assign_splits(list(reversed(_IDS)), seed=7)
    assert a.checksum == b.checksum
    assert a.splits == b.splits
    # A different seed produces a different assignment.
    c = assign_splits(_IDS, seed=8)
    assert c.checksum != a.checksum


def test_every_record_lands_in_exactly_one_split():
    manifest = assign_splits(_IDS, seed=7)
    all_ids = [rid for ids in manifest.splits.values() for rid in ids]
    assert sorted(all_ids) == sorted(_IDS)
    assert set(manifest.splits) == {"train", "val", "test"}


def test_benchmark_ids_are_held_out_with_normalisation():
    manifest = assign_splits(_IDS, seed=7, benchmark_ids={" rec-001 ", "rec-002"})
    assert manifest.held_out_benchmark == ["rec-001", "rec-002"]
    for ids in manifest.splits.values():
        assert "rec-001" not in ids and "rec-002" not in ids
    assert_no_benchmark_leakage(manifest, {"rec-001", "rec-002"})


def test_leak_check_fires_on_a_contaminated_manifest():
    manifest = assign_splits(_IDS, seed=7)
    with pytest.raises(ReactionDataError, match="leaked"):
        assert_no_benchmark_leakage(manifest, {_IDS[0]})  # id present in a split


def test_duplicate_and_empty_ids_are_refused():
    with pytest.raises(ReactionDataError, match="Duplicate"):
        assign_splits(["a", "a"], seed=1)
    with pytest.raises(ReactionDataError, match="Empty"):
        assign_splits(["a", " "], seed=1)


def test_fraction_validation():
    with pytest.raises(ReactionDataError, match="sum to 1"):
        assign_splits(_IDS, seed=1, fractions={"train": 0.5, "test": 0.4})
    with pytest.raises(ReactionDataError, match="positive"):
        assign_splits(_IDS, seed=1, fractions={"train": 1.5, "test": -0.5})


def test_all_records_held_out_is_refused():
    with pytest.raises(ReactionDataError, match="refusing to freeze"):
        assign_splits(["a", "b"], seed=1, benchmark_ids={"a", "b"})


def test_manifest_verifies_and_refuses_drift():
    manifest = assign_splits(_IDS, seed=7)
    payload = manifest.as_dict()
    parsed = verify_manifest(payload)
    assert parsed.checksum == manifest.checksum
    payload["splits"]["train"] = payload["splits"]["train"][:-1]  # tamper
    with pytest.raises(ReactionDataError, match="drift"):
        verify_manifest(payload)


def test_registry_covers_the_spec_datasets():
    for dataset in ("ord", "uspto_50k", "buchwald_hartwig_hte", "reaxys", "brethericks"):
        assert dataset in LICENSE_REGISTRY
