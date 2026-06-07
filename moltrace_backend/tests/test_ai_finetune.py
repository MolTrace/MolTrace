"""Unit tests for the LoRA domain fine-tuning pipeline (Prompt 15, finetune.py).

These run on a CPU-only host with **no** torch / peft / Modal installed: the
training backend is injected as a fake, so the snapshotting, K-fold
cross-validation, aggregation, holdout-exclusion guard, and the gated
registration are all exercised without the heavy deps. Covered:

* immutable, content-addressed training snapshot (identity = data, not provenance);
* gold/holdout-set exclusion enforced by hash (snapshot + a hand-built snapshot);
* reproducible K-fold CV with per-fold + aggregate (mean ± std) metrics;
* GPU-hours + Modal cost logged;
* gated registration: candidate always, shadow iff it dominates, NEVER production;
* gold-set checksum binding; no-adapter -> no registration; deps-absent default.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from moltrace.spectroscopy.ai.finetune import (
    FinalAdapter,
    FineTuneError,
    FineTuneUnavailable,
    FoldResult,
    Snapshot,
    build_training_snapshot,
    finetune_lora,
    register_if_eligible,
)
from moltrace.spectroscopy.ai.registry import (
    InMemoryRegistryStore,
    ModelRegistry,
    ModelRole,
    ModelStatus,
)
from moltrace.spectroscopy.data.datasets_pipeline import (
    HoldoutLeakageError,
    Modality,
    Splits,
)
from moltrace.spectroscopy.eval.harness import (
    CallableBundle,
    GoldRecord,
    GoldSet,
    Prediction,
    evaluate,
)

_BASE_ID = "nmrnet_checkpoint:13C:1.0.0"


# --------------------------------------------------------------------------- #
# Fixtures: validated examples, splits, a gold set, fake trainer, fake bundles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Example:
    """A NormalizedRecord-compatible duck type for snapshotting."""

    record_hash: str
    source_key: str
    modality: Modality
    spectrum: dict | None


def _examples(n: int, *, start: int = 0) -> list[_Example]:
    out: list[_Example] = []
    for i in range(start, start + n):
        is_h = i % 2 == 0
        out.append(
            _Example(
                record_hash=f"sha256:rec{i:03d}",
                source_key="nmrshiftdb2" if is_h else "in_house",
                modality=Modality.NMR_1H if is_h else Modality.NMR_13C,
                spectrum={
                    "nucleus": "1H" if is_h else "13C",
                    "field_mhz": 400.0 if is_h else 100.0,
                    "ppm": [1.0, 2.0],
                    "intensity": [1.0, 0.5],
                },
            )
        )
    return out


def _splits(holdout: list[str]) -> Splits:
    return Splits(
        seed=0,
        ratios=(0.8, 0.1, 0.1),
        train=(),
        val=(),
        test=(),
        test_checksum="sha256:test",
        holdout_exclusion_hashes=frozenset(holdout),
        n_computed_excluded_for_holdout=0,
        created_utc="2026-06-07T00:00:00+00:00",
    )


_GOLD_RECORDS = (
    GoldRecord("g1", "in_house", "K1", {"1H": [1.0], "13C": [50.0]}, True, "K1", {"ppm": [1.0]}),
    GoldRecord("g2", "in_house", "K2", {"1H": [2.0], "13C": [60.0]}, True, "K2", {"ppm": [2.0]}),
    GoldRecord("g3", "in_house", "K3", {"1H": [3.0], "13C": [70.0]}, False, "KW", {"ppm": [3.0]}),
    GoldRecord("g4", "in_house", "K4", {"1H": [4.0], "13C": [80.0]}, False, "KW2", {"ppm": [4.0]}),
)


def _gold() -> GoldSet:
    gs = GoldSet("ft-gold", _GOLD_RECORDS)
    return GoldSet("ft-gold", _GOLD_RECORDS, expected_checksum=gs.checksum(), expected_size=4)


def _perfect_predict(rec: GoldRecord) -> Prediction:
    return Prediction(
        ranked_candidates=(rec.true_inchikey,),
        predicted_shifts=dict(rec.reference_shifts),
        confidence=0.9,
        confirmed=rec.reviewer_verdict,
        retrieved=(rec.true_inchikey,),
        uncertainty=0.1,
        latency_ms=10.0,
    )


def _weak_predict(rec: GoldRecord) -> Prediction:
    ranked = ("KX",) if rec.identifier == "g4" else (rec.true_inchikey,)
    shifts = {k: [v + 0.5 for v in vs] for k, vs in rec.reference_shifts.items()}
    return Prediction(ranked, shifts, 0.6, rec.reviewer_verdict, (rec.true_inchikey,), 0.5, 20.0)


def _perfect_bundle() -> CallableBundle:
    return CallableBundle(_perfect_predict, {"lora_adapter:13C:0.1.0": "sha256:cand"})


def _weak_bundle() -> CallableBundle:
    return CallableBundle(_weak_predict, {"lora_adapter:13C:0.1.0": "sha256:cand"})


class _FakeTrainer:
    """A deterministic trainer that writes a tiny adapter and reports cheap metrics."""

    def __init__(self, *, gpu_per_fold: float = 2.0, final_gpu: float = 4.0) -> None:
        self.gpu_per_fold = gpu_per_fold
        self.final_gpu = final_gpu
        self.fold_calls: list[tuple[int, tuple[str, ...], tuple[str, ...]]] = []
        self.final_calls: list[tuple[str, ...]] = []

    def train_and_eval(self, *, fold, train_hashes, eval_hashes, base_model_id, lora_config, snapshot):
        self.fold_calls.append((fold, tuple(train_hashes), tuple(eval_hashes)))
        return FoldResult(
            mae_1h=0.15 + 0.01 * fold,  # vary per fold so std > 0
            mae_13c=1.2 + 0.10 * fold,
            calibration=0.04,
            coverage=0.98,
            gpu_hours=self.gpu_per_fold,
        )

    def fit_final(self, *, train_hashes, base_model_id, lora_config, snapshot, out_dir):
        self.final_calls.append(tuple(train_hashes))
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        artifact = out / "adapter_model.safetensors"
        payload = f"{base_model_id}|{snapshot.snapshot_hash}".encode()
        artifact.write_bytes(payload)
        sha = "sha256:" + hashlib.sha256(payload).hexdigest()
        return FinalAdapter(path=str(artifact), sha256=sha, gpu_hours=self.final_gpu)


class _NoArtifactTrainer(_FakeTrainer):
    def fit_final(self, **_):
        return FinalAdapter(path="", sha256="", gpu_hours=self.final_gpu)


def _make_run(tmp_path, *, gold_checksum, trainer=None, k_folds=5, nucleus="13C", version="0.1.0"):
    snap = build_training_snapshot(_examples(12), gold_checksum=gold_checksum)
    return finetune_lora(
        snap,
        _BASE_ID,
        k_folds=k_folds,
        trainer=trainer or _FakeTrainer(),
        adapter_cache_dir_override=tmp_path,
        nucleus=nucleus,
        semantic_version=version,
        git_sha="abc1234",
    )


# --------------------------------------------------------------------------- #
# build_training_snapshot
# --------------------------------------------------------------------------- #
def test_snapshot_excludes_holdout_and_records_composition() -> None:
    examples = _examples(10)
    holdout = [examples[0].record_hash, examples[3].record_hash]
    snap = build_training_snapshot(
        examples, splits=_splits(holdout), gold_checksum="sha256:gold"
    )

    assert snap.n_excluded_for_holdout == 2
    assert snap.row_count == 8
    assert set(snap.record_hashes).isdisjoint(holdout)  # holdout never trained on
    assert snap.snapshot_hash.startswith("sha256:")
    assert snap.gold_checksum == "sha256:gold"
    # composition is captured for audit
    assert sum(snap.per_class_counts.values()) == 8
    assert set(snap.nucleus_distribution) <= {"1H", "13C"}
    assert "400.0" in snap.field_distribution or "100.0" in snap.field_distribution


def test_snapshot_hash_is_data_identity_not_provenance() -> None:
    examples = _examples(6)
    a = build_training_snapshot(examples, gold_checksum="sha256:g", git_sha="aaa", created_utc="t1")
    b = build_training_snapshot(examples, gold_checksum="sha256:g", git_sha="bbb", created_utc="t2")
    # identical data + gold binding -> identical hash regardless of git_sha / timestamp
    assert a.snapshot_hash == b.snapshot_hash
    # one more example -> different identity
    c = build_training_snapshot(_examples(7), gold_checksum="sha256:g")
    assert c.snapshot_hash != a.snapshot_hash
    # different gold binding -> different identity
    d = build_training_snapshot(examples, gold_checksum="sha256:other")
    assert d.snapshot_hash != a.snapshot_hash


# --------------------------------------------------------------------------- #
# finetune_lora: K-fold CV + cost
# --------------------------------------------------------------------------- #
def test_kfold_partition_is_complete_disjoint_and_reproducible(tmp_path) -> None:
    t1 = _FakeTrainer()
    run1 = _make_run(tmp_path / "a", gold_checksum=_gold().checksum(), trainer=t1)

    assert len(run1.fold_metrics) == 5
    assert [f.fold for f in run1.fold_metrics] == [0, 1, 2, 3, 4]
    # every fold's eval set is non-empty and train+eval == row_count
    for f in run1.fold_metrics:
        assert f.n_eval > 0
        assert f.n_train + f.n_eval == run1.row_count
    # the eval folds partition the corpus exactly (complete + disjoint)
    eval_sets = [set(call[2]) for call in t1.fold_calls]
    union: set[str] = set().union(*eval_sets)
    assert sum(len(s) for s in eval_sets) == run1.row_count == len(union)
    # final fit uses the full training set (== the union of every eval fold)
    assert set(t1.final_calls[0]) == union

    # reproducible: same seed -> identical partition, aggregates, and run_id
    t2 = _FakeTrainer()
    run2 = _make_run(tmp_path / "b", gold_checksum=_gold().checksum(), trainer=t2)
    assert t1.fold_calls == t2.fold_calls
    assert run1.run_id == run2.run_id


def test_aggregates_and_cost_are_logged(tmp_path) -> None:
    run = _make_run(tmp_path, gold_checksum=_gold().checksum())

    expected_1h = sum(0.15 + 0.01 * i for i in range(5)) / 5
    assert run.mae_1h_mean == pytest.approx(expected_1h)
    assert run.mae_1h_std > 0  # folds vary -> non-zero spread
    assert run.mae_13c_std > 0
    assert run.calibration_mean == pytest.approx(0.04)
    assert run.coverage_mean == pytest.approx(0.98)

    # GPU-hours = 5 folds * 2.0 + final 4.0 = 14.0; cost = hours * rate
    assert run.gpu_hours == pytest.approx(5 * 2.0 + 4.0)
    assert run.cost_usd == pytest.approx(run.gpu_hours * run.manifest["gpu_cost_per_hour"])

    # full manifest carries the lineage the registry needs
    m = run.manifest
    assert m["snapshot_hash"] == run.snapshot_hash
    assert m["base_model_id"] == _BASE_ID
    assert m["git_sha"] == "abc1234"
    assert m["lora_config"]["r"] == 8
    assert len(m["fold_metrics"]) == 5 and "aggregate" in m
    # adapter saved out of git, content-addressed
    assert run.adapter_sha256.startswith("sha256:")
    assert Path(run.adapter_path).exists()
    # 13C run derives a validated confidence band from CV when trainer omits it
    assert run.confidence_band_ppm == pytest.approx(run.mae_13c_mean + run.mae_13c_std)


def test_finetune_refuses_a_snapshot_that_touches_the_holdout(tmp_path) -> None:
    leaked = "sha256:rec000"
    tainted = Snapshot(
        snapshot_hash="sha256:tainted",
        row_count=1,
        record_hashes=(leaked,),
        per_class_counts={"nmr_1h": 1},
        nucleus_distribution={"1H": 1},
        field_distribution={"400.0": 1},
        solvent_distribution={"unknown": 1},
        source_distribution={"nmrshiftdb2": 1},
        gold_checksum="sha256:gold",
        n_excluded_for_holdout=0,
        git_sha="abc",
        created_utc="t",
    )
    with pytest.raises(HoldoutLeakageError):
        finetune_lora(
            tainted,
            _BASE_ID,
            k_folds=2,
            trainer=_FakeTrainer(),
            splits=_splits([leaked]),
            adapter_cache_dir_override=tmp_path,
        )


def test_finetune_validates_kfolds_and_rank(tmp_path) -> None:
    snap = build_training_snapshot(_examples(6), gold_checksum=_gold().checksum())
    with pytest.raises(FineTuneError):
        finetune_lora(snap, _BASE_ID, k_folds=1, trainer=_FakeTrainer())
    from moltrace.spectroscopy.ai.finetune import LoRAConfig

    with pytest.raises(FineTuneError):
        finetune_lora(
            snap, _BASE_ID, k_folds=2, lora_config=LoRAConfig(r=4), trainer=_FakeTrainer()
        )
    with pytest.raises(FineTuneError):
        finetune_lora(
            snap, _BASE_ID, k_folds=2, lora_config=LoRAConfig(r=32), trainer=_FakeTrainer()
        )


def test_default_trainer_unavailable_without_torch_peft_modal(tmp_path) -> None:
    snap = build_training_snapshot(_examples(4), gold_checksum=_gold().checksum())
    with pytest.raises(FineTuneUnavailable):
        finetune_lora(snap, _BASE_ID, k_folds=2, adapter_cache_dir_override=tmp_path)


# --------------------------------------------------------------------------- #
# register_if_eligible: the dominance gate + lifecycle
# --------------------------------------------------------------------------- #
def test_no_incumbent_registers_candidate_then_shadow(tmp_path) -> None:
    registry = ModelRegistry(InMemoryRegistryStore())
    run = _make_run(tmp_path, gold_checksum=_gold().checksum())

    model_id = register_if_eligible(
        run,
        registry=registry,
        gold_set=_gold(),
        candidate_bundle=_perfect_bundle(),
        dataset_tag="in-house-2026Q2",
        source="in_house",
    )
    assert model_id == "lora_adapter:13C:0.1.0"

    entry = registry.get(model_id)
    assert entry.role is ModelRole.LORA_ADAPTER
    assert entry.status is ModelStatus.CANDIDATE  # declared at registration
    assert registry.current_status(model_id) is ModelStatus.SHADOW  # promoted, no incumbent
    # full lineage recorded (hard rule 2)
    assert entry.training_data_lineage.dataset_snapshot_hash == run.snapshot_hash
    assert entry.training_data_lineage.row_count == run.row_count
    assert entry.parent_base_id == _BASE_ID
    assert set(entry.metric_snapshot) >= {"top1_accuracy", "ece", "false_confirmation_rate"}
    assert entry.extra["gpu_hours"] == run.gpu_hours
    assert entry.extra["cost_usd"] == run.cost_usd
    assert entry.extra["promotable"] is True
    # NEVER production
    assert registry.resolve(ModelRole.LORA_ADAPTER, "13C") is None


def test_dominating_candidate_is_promoted_to_shadow(tmp_path) -> None:
    registry = ModelRegistry(InMemoryRegistryStore())
    run = _make_run(tmp_path, gold_checksum=_gold().checksum())

    candidate = evaluate(_perfect_bundle(), _gold())
    weaker_incumbent = replace(candidate, top1_accuracy=candidate.top1_accuracy - 0.2)

    model_id = register_if_eligible(
        run,
        registry=registry,
        gold_set=_gold(),
        candidate_bundle=_perfect_bundle(),
        incumbent_metrics=weaker_incumbent,
    )
    assert registry.current_status(model_id) is ModelStatus.SHADOW
    assert registry.get(model_id).extra["promotable"] is True
    assert registry.resolve(ModelRole.LORA_ADAPTER, "13C") is None  # never production


def test_regressing_candidate_registers_candidate_only(tmp_path) -> None:
    registry = ModelRegistry(InMemoryRegistryStore())
    run = _make_run(tmp_path, gold_checksum=_gold().checksum())

    candidate = evaluate(_weak_bundle(), _gold())
    stronger_incumbent = replace(candidate, top1_accuracy=candidate.top1_accuracy + 0.1)

    model_id = register_if_eligible(
        run,
        registry=registry,
        gold_set=_gold(),
        candidate_bundle=_weak_bundle(),
        incumbent_metrics=stronger_incumbent,
    )
    assert registry.current_status(model_id) is ModelStatus.CANDIDATE  # not promoted
    assert registry.get(model_id).extra["promotable"] is False
    assert registry.resolve(ModelRole.LORA_ADAPTER, "13C") is None


def test_gold_checksum_binding_mismatch_refuses_registration(tmp_path) -> None:
    registry = ModelRegistry(InMemoryRegistryStore())
    run = _make_run(tmp_path, gold_checksum="sha256:DIFFERENT-HOLDOUT")
    with pytest.raises(FineTuneError):
        register_if_eligible(
            run, registry=registry, gold_set=_gold(), candidate_bundle=_perfect_bundle()
        )
    assert registry.list_entries() == []  # nothing registered


def test_no_adapter_artifact_registers_nothing(tmp_path) -> None:
    registry = ModelRegistry(InMemoryRegistryStore())
    run = _make_run(tmp_path, gold_checksum=_gold().checksum(), trainer=_NoArtifactTrainer())
    assert run.adapter_sha256 is None

    model_id = register_if_eligible(
        run, registry=registry, gold_set=_gold(), candidate_bundle=_perfect_bundle()
    )
    assert model_id is None
    assert registry.list_entries() == []
