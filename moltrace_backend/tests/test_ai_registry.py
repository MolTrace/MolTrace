"""Unit tests for the append-only model registry (Prompt 13, registry.py).

The same suite runs against BOTH persistence backends -- the in-memory store and
the SQLAlchemy store over a file-backed SQLite database (the exact code path that
drives PostgreSQL in production) -- so round-trip, append-only, and supersession
semantics are proven independent of the backend, on a CPU-only host with no real
database server.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from moltrace.spectroscopy.ai.registry import (
    AppendOnlyViolation,
    InMemoryRegistryStore,
    InvalidStatusTransition,
    ModelRegistry,
    ModelRole,
    ModelStatus,
    SqlAlchemyRegistryStore,
    TrainingDataLineage,
    build_model_entry,
)
from moltrace.spectroscopy.infra.eval import MetricVector

_LINEAGE = TrainingDataLineage(
    dataset_snapshot_hash="sha256:dataset-abc",
    row_count=12345,
    dataset_tag="nmrshiftdb2-2026Q2",
    source="nmrshiftdb2",
)


@pytest.fixture(params=["memory", "sqlalchemy"])
def registry(request, tmp_path) -> ModelRegistry:
    if request.param == "memory":
        store = InMemoryRegistryStore()
    else:
        store = SqlAlchemyRegistryStore(f"sqlite:///{tmp_path}/ai_registry.db")
    return ModelRegistry(store)


def _checkpoint(version: str, nucleus: str = "13C", *, status=ModelStatus.CANDIDATE):
    return build_model_entry(
        role=ModelRole.NMRNET_CHECKPOINT,
        nucleus=nucleus,
        semantic_version=version,
        artifact_sha256=f"sha256:ckpt-{nucleus}-{version}",
        training_data_lineage=_LINEAGE,
        metric_snapshot=MetricVector(rmse=1.098, f1=0.91),
        status=status,
        created_utc=datetime(2026, 6, 7, 12, 0, 0, tzinfo=UTC),
    )


# --------------------------------------------------------------------------- #
# Round-trip
# --------------------------------------------------------------------------- #
def test_round_trips_entry_with_lineage_and_metric_snapshot(registry) -> None:
    entry = registry.register(_checkpoint("1.0.0"))
    got = registry.get(entry.model_id)

    assert got.model_id == "nmrnet_checkpoint:13C:1.0.0"
    assert got.role is ModelRole.NMRNET_CHECKPOINT
    assert got.nucleus == "13C"
    assert got.artifact_sha256 == "sha256:ckpt-13C-1.0.0"
    # lineage round-trips field-for-field
    assert got.training_data_lineage.dataset_snapshot_hash == "sha256:dataset-abc"
    assert got.training_data_lineage.row_count == 12345
    assert got.training_data_lineage.source == "nmrshiftdb2"
    # metric snapshot round-trips (MetricVector normalised to {str: float}, None dropped)
    assert got.metric_snapshot == {"rmse": 1.098, "f1": 0.91}
    # the content address survives the round-trip losslessly (incl. SQLite path)
    assert got.entry_hash() == entry.entry_hash()
    assert got.entry_hash().startswith("sha256:")


def test_metric_snapshot_accepts_plain_mapping(registry) -> None:
    entry = registry.register_artifact(
        role=ModelRole.HOSE_KB,
        semantic_version="3.1.0",
        artifact_sha256="sha256:hosekb",
        training_data_lineage=_LINEAGE,
        metric_snapshot={"rmse": 1.5, "f1": 0.8, "unused": None},
    )
    assert registry.get(entry.model_id).metric_snapshot == {"rmse": 1.5, "f1": 0.8}


# --------------------------------------------------------------------------- #
# Append-only semantics
# --------------------------------------------------------------------------- #
def test_register_is_append_only(registry) -> None:
    registry.register(_checkpoint("1.0.0"))
    with pytest.raises(AppendOnlyViolation):
        registry.register(_checkpoint("1.0.0"))  # same model_id -> rejected


def test_entries_are_immutable() -> None:
    entry = _checkpoint("1.0.0")
    with pytest.raises(FrozenInstanceError):
        entry.artifact_sha256 = "sha256:tampered"  # type: ignore[misc]


def test_unknown_model_raises_keyerror(registry) -> None:
    with pytest.raises(KeyError):
        registry.get("does-not-exist")


# --------------------------------------------------------------------------- #
# resolve(role, nucleus) -> current production artifact
# --------------------------------------------------------------------------- #
def test_resolve_returns_only_production_and_is_per_nucleus(registry) -> None:
    c13 = registry.register(_checkpoint("1.0.0", "13C"))
    h1 = registry.register(_checkpoint("1.0.0", "1H"))

    # candidate, not yet production
    assert registry.resolve(ModelRole.NMRNET_CHECKPOINT, "13C") is None

    registry.promote(c13.model_id)
    resolved = registry.resolve(ModelRole.NMRNET_CHECKPOINT, "13C")
    assert resolved is not None and resolved.model_id == c13.model_id

    # 1H is independent of 13C
    assert registry.resolve(ModelRole.NMRNET_CHECKPOINT, "1H") is None
    registry.promote(h1.model_id)
    assert registry.resolve(ModelRole.NMRNET_CHECKPOINT, "1H").model_id == h1.model_id
    assert registry.resolve(ModelRole.NMRNET_CHECKPOINT, "13C").model_id == c13.model_id

    # a role with nothing registered resolves to None
    assert registry.resolve(ModelRole.LORA_ADAPTER, "13C") is None


# --------------------------------------------------------------------------- #
# Supersession (new versions supersede; tracked from the append-only log)
# --------------------------------------------------------------------------- #
def test_promoting_v2_supersedes_v1(registry) -> None:
    v1 = registry.register(_checkpoint("1.0.0"))
    registry.promote(v1.model_id)
    v2 = registry.register(_checkpoint("2.0.0"))
    registry.promote(v2.model_id)

    # v2 is now production; v1 was auto-retired
    assert registry.current_status(v1.model_id) is ModelStatus.RETIRED
    assert registry.current_status(v2.model_id) is ModelStatus.PRODUCTION
    assert registry.resolve(ModelRole.NMRNET_CHECKPOINT, "13C").model_id == v2.model_id

    lin_v2 = registry.list_lineage(v2.model_id)
    assert lin_v2.supersedes == v1.model_id
    assert lin_v2.superseded_by is None

    lin_v1 = registry.list_lineage(v1.model_id)
    assert lin_v1.superseded_by == v2.model_id
    assert lin_v1.supersedes is None
    # the supersession is recorded as an appended retire event with a reason
    reasons = [t.reason for t in lin_v1.status_history]
    assert any(r and "superseded by" in r for r in reasons)


def test_list_lineage_status_history_in_order(registry) -> None:
    entry = registry.register(_checkpoint("1.0.0"))
    registry.set_status(entry.model_id, ModelStatus.SHADOW)
    registry.promote(entry.model_id, reason="passed gate")

    lineage = registry.list_lineage(entry.model_id)
    assert [t.to_status for t in lineage.status_history] == [
        ModelStatus.CANDIDATE,  # initial registration event
        ModelStatus.SHADOW,
        ModelStatus.PRODUCTION,
    ]
    assert lineage.current_status is ModelStatus.PRODUCTION
    assert lineage.training_data_lineage.row_count == 12345


# --------------------------------------------------------------------------- #
# Lifecycle state machine
# --------------------------------------------------------------------------- #
def test_invalid_transitions_are_rejected(registry) -> None:
    entry = registry.register(_checkpoint("1.0.0"))

    # same-status is not a transition
    with pytest.raises(InvalidStatusTransition):
        registry.set_status(entry.model_id, ModelStatus.CANDIDATE)

    # retired is terminal
    registry.retire(entry.model_id)
    assert registry.current_status(entry.model_id) is ModelStatus.RETIRED
    with pytest.raises(InvalidStatusTransition):
        registry.promote(entry.model_id)


# --------------------------------------------------------------------------- #
# Deterministic content addressing (store-independent)
# --------------------------------------------------------------------------- #
def test_entry_hash_is_deterministic_and_content_sensitive() -> None:
    a = _checkpoint("1.0.0")
    b = _checkpoint("1.0.0")  # identical provenance + fixed created_utc
    assert a.entry_hash() == b.entry_hash()

    c = build_model_entry(
        role=ModelRole.NMRNET_CHECKPOINT,
        nucleus="13C",
        semantic_version="1.0.0",
        artifact_sha256="sha256:DIFFERENT",
        training_data_lineage=_LINEAGE,
        metric_snapshot=MetricVector(rmse=1.098, f1=0.91),
        created_utc=datetime(2026, 6, 7, 12, 0, 0, tzinfo=UTC),
    )
    assert c.entry_hash() != a.entry_hash()
