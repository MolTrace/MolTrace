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
    CrossModalEvidence,
    FinalAdapter,
    FineTuneError,
    FineTuneUnavailable,
    FoldResult,
    HPOTrial,
    InMemoryActiveLearningQueue,
    IntraSpectralEvidence,
    Snapshot,
    build_training_snapshot,
    calibration_report,
    detect_contradictions,
    finetune_lora,
    fit_platt_scaling,
    fit_temperature_scaling,
    optimize_hyperparameters,
    register_if_eligible,
    train_contradiction_detector,
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
# Leak-proof GroupKFold cross-validation (Prompt 22b)
#
# Multiple spectra of the same molecule/batch must never straddle a CV fold,
# otherwise the cross-validated metrics leak train info into eval and read
# optimistically. Records grow a grouping key (molecule skeleton = InChIKey
# connectivity block); whole groups are assigned to a fold. Records with no
# grouping signal (the legacy fixtures) fall back to the per-record split, so
# nothing about the historical behaviour changes.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _GroupedExample:
    """A NormalizedRecord-compatible duck type that also carries an InChIKey,
    so leak-proof GroupKFold grouping engages."""

    record_hash: str
    source_key: str
    modality: Modality
    spectrum: dict | None
    inchikey: str


def _grouped_examples(n_mol: int, scans_per_mol: int) -> list[_GroupedExample]:
    """``n_mol`` molecules, each with ``scans_per_mol`` spectra that share one
    InChIKey connectivity block (first 14 chars) but have distinct record hashes."""

    out: list[_GroupedExample] = []
    for m in range(n_mol):
        block = f"MOL{m:011d}"  # exactly 14 chars -> the grouping key
        for s in range(scans_per_mol):
            out.append(
                _GroupedExample(
                    record_hash=f"sha256:mol{m:03d}scan{s:03d}",
                    source_key="nmrshiftdb2",
                    modality=Modality.NMR_1H,
                    spectrum={"nucleus": "1H", "field_mhz": 400.0, "ppm": [1.0], "intensity": [1.0]},
                    inchikey=f"{block}-{m:04d}{s:07d}-N",
                )
            )
    return out


def test_grouped_cv_keeps_every_molecule_in_one_fold(tmp_path) -> None:
    # 10 molecules x 3 scans: under per-record CV a molecule would almost surely
    # split across folds; grouped CV must keep all of a molecule's scans together.
    examples = _grouped_examples(n_mol=10, scans_per_mol=3)
    snap = build_training_snapshot(examples, gold_checksum=_gold().checksum())
    assert snap.record_groups is not None  # grouping engaged
    assert snap.n_groups == 10
    assert snap.row_count == 30

    trainer = _FakeTrainer()
    finetune_lora(
        snap,
        _BASE_ID,
        k_folds=5,
        trainer=trainer,
        adapter_cache_dir_override=tmp_path,
        nucleus="1H",
        git_sha="abc1234",
    )
    group_of = snap.record_groups
    # No molecule's scans appear on both the eval and train side of any fold.
    for _fold, train_hashes, eval_hashes in trainer.fold_calls:
        eval_groups = {group_of[h] for h in eval_hashes}
        train_groups = {group_of[h] for h in train_hashes}
        assert eval_groups.isdisjoint(train_groups)
    # And the eval folds still partition the corpus exactly (complete + disjoint).
    eval_sets = [set(call[2]) for call in trainer.fold_calls]
    union: set[str] = set().union(*eval_sets)
    assert sum(len(s) for s in eval_sets) == snap.row_count == len(union)


def test_snapshot_hash_commits_to_cv_grouping() -> None:
    # Identical record hashes + identical composition, but different molecule
    # grouping must yield a different data-identity hash (the hash commits to CV
    # grouping); the ungrouped path leaves identity untouched.
    base = dict(
        source_key="nmrshiftdb2",
        modality=Modality.NMR_1H,
        spectrum={"nucleus": "1H", "field_mhz": 400.0, "ppm": [1.0], "intensity": [1.0]},
    )
    hashes = [f"sha256:rec{i:03d}" for i in range(4)]
    blocks_a = ["AAAAAAAAAAAAAA", "AAAAAAAAAAAAAA", "BBBBBBBBBBBBBB", "BBBBBBBBBBBBBB"]
    blocks_b = ["AAAAAAAAAAAAAA", "BBBBBBBBBBBBBB", "CCCCCCCCCCCCCC", "DDDDDDDDDDDDDD"]
    a = [
        _GroupedExample(h, inchikey=f"{bk}-{i}", **base)
        for i, (h, bk) in enumerate(zip(hashes, blocks_a, strict=True))
    ]
    b = [
        _GroupedExample(h, inchikey=f"{bk}-{i}", **base)
        for i, (h, bk) in enumerate(zip(hashes, blocks_b, strict=True))
    ]

    snap_a = build_training_snapshot(a, gold_checksum="sha256:g")
    snap_b = build_training_snapshot(b, gold_checksum="sha256:g")
    assert snap_a.record_hashes == snap_b.record_hashes  # same training-set identity by hash
    assert (snap_a.n_groups, snap_b.n_groups) == (2, 4)
    assert snap_a.snapshot_hash != snap_b.snapshot_hash  # ...but grouping changes data identity

    # Ungrouped path: no grouping signal -> record_groups None, n_groups == rows.
    plain = build_training_snapshot(_examples(4), gold_checksum="sha256:g")
    assert plain.record_groups is None
    assert plain.n_groups == 4


def test_ungrouped_folds_match_legacy_per_record_split() -> None:
    # The group-aware partitioner must reproduce the historical per-record seeded
    # split byte-for-byte when no grouping is supplied (groups=None).
    from moltrace.spectroscopy.ai.finetune import _assign_folds

    hashes = [f"sha256:rec{i:03d}" for i in range(12)]
    k, seed = 5, 0
    legacy: list[list[str]] = [[] for _ in range(k)]
    for h in sorted(hashes):
        digest = hashlib.sha256(f"{h}|{seed}".encode()).hexdigest()
        legacy[int(digest[:16], 16) % k].append(h)

    assert _assign_folds(hashes, k, seed) == legacy
    assert _assign_folds(hashes, k, seed, groups=None) == legacy


def test_assign_folds_keeps_whole_groups_together() -> None:
    # The single partitioner feeds every CV loop, including the contradiction
    # detector's *out-of-fold* calibration head (it temperature-scales pooled OOF
    # predictions). So proving no group straddles two folds here proves that head
    # is calibrated leak-proof too: no molecule contributes to both a fold's
    # trained model and its own out-of-fold score.
    from moltrace.spectroscopy.ai.finetune import _assign_folds

    groups = {f"sha256:g{g}r{r}": f"GROUP{g}" for g in range(4) for r in range(3)}
    folds = _assign_folds(list(groups), k=3, seed=0, groups=groups)

    flat = [h for fold in folds for h in fold]
    assert sorted(flat) == sorted(groups)  # complete
    assert len(flat) == len(set(flat)) == 12  # disjoint
    for g in range(4):  # each group lives in exactly one fold
        members = {h for h, gk in groups.items() if gk == f"GROUP{g}"}
        holding = [i for i, fold in enumerate(folds) if members & set(fold)]
        assert len(holding) == 1, f"GROUP{g} leaked across folds {holding}"


def test_grouped_cv_requires_at_least_k_groups(tmp_path) -> None:
    # 3 molecules but k=5 -> cannot form 5 leak-proof folds.
    snap = build_training_snapshot(
        _grouped_examples(n_mol=3, scans_per_mol=4), gold_checksum=_gold().checksum()
    )
    assert snap.n_groups == 3 and snap.row_count == 12
    with pytest.raises(FineTuneError, match="molecule groups"):
        finetune_lora(
            snap,
            _BASE_ID,
            k_folds=5,
            trainer=_FakeTrainer(),
            adapter_cache_dir_override=tmp_path,
            nucleus="1H",
        )


def test_manifest_records_cv_strategy(tmp_path) -> None:
    snap_g = build_training_snapshot(
        _grouped_examples(n_mol=6, scans_per_mol=2), gold_checksum=_gold().checksum()
    )
    run_g = finetune_lora(
        snap_g,
        _BASE_ID,
        k_folds=3,
        trainer=_FakeTrainer(),
        adapter_cache_dir_override=tmp_path / "g",
        nucleus="1H",
        git_sha="abc1234",
    )
    assert run_g.manifest["cv"] == {
        "strategy": "group_kfold",
        "group_key": "molecule_skeleton",
        "n_groups": 6,
    }

    snap_p = build_training_snapshot(_examples(12), gold_checksum=_gold().checksum())
    run_p = finetune_lora(
        snap_p,
        _BASE_ID,
        k_folds=5,
        trainer=_FakeTrainer(),
        adapter_cache_dir_override=tmp_path / "p",
        nucleus="13C",
        git_sha="abc1234",
    )
    assert run_p.manifest["cv"]["strategy"] == "kfold"
    assert run_p.manifest["cv"]["n_groups"] == 12  # each record its own group


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


# --------------------------------------------------------------------------- #
# Prompt 22 — Bayesian HPO (Optuna): test doubles
# --------------------------------------------------------------------------- #
class _ConfigSensitiveTrainer:
    """Trainer whose CV error depends on LoRA rank, giving HPO a clear optimum (r=12)."""

    def __init__(self) -> None:
        self.ranks_seen: list[int] = []

    def train_and_eval(self, *, fold, train_hashes, eval_hashes, base_model_id, lora_config, snapshot):
        self.ranks_seen.append(lora_config.r)
        penalty = abs(lora_config.r - 12) * 0.05  # minimised at r = 12
        return FoldResult(
            mae_1h=0.10 + penalty,
            mae_13c=1.00 + penalty,
            calibration=0.03,
            coverage=0.97,
            gpu_hours=1.0,
        )

    def fit_final(self, *, train_hashes, base_model_id, lora_config, snapshot, out_dir):
        return FinalAdapter(path="", sha256="sha256:cfg", gpu_hours=1.0)


class _GridSampler:
    """A deterministic ``HPOSampler`` test double (evaluates a fixed param grid).

    Stands in for Optuna so the orchestration is unit-testable without the dep.
    """

    name = "grid-test"

    def __init__(self, grid: list[dict]) -> None:
        self.grid = grid
        self.seen_seed: int | None = None

    def optimize(self, objective, *, search_space, n_trials, seed):
        self.seen_seed = seed
        return [
            HPOTrial(number=i, params=dict(params), value=objective(params))
            for i, params in enumerate(self.grid[:n_trials])
        ]


def _hpo_grid() -> list[dict]:
    """Ten candidate configs; only one has the optimal rank (r=12)."""

    rs = [8, 9, 10, 11, 12, 13, 14, 15, 16, 11]
    return [
        {"r": r, "alpha": 16, "dropout": 0.05, "learning_rate": 2e-4, "epochs": 3} for r in rs
    ]


class _RunHandle:
    """Records what a single tracked run captured (Prompt 19 tracker double)."""

    def __init__(self, recorder, run_name, params, tags) -> None:
        self.recorder = recorder
        self.run_name = run_name
        self.params = params
        self.tags = tags
        self.metrics: dict = {}
        self.dataset_version: str | None = None

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        self.recorder.runs.append(self)
        return False

    def set_dataset_version(self, version) -> None:
        self.dataset_version = version

    def log_metrics(self, metrics, *, step=None) -> None:
        self.metrics.update(dict(metrics))

    def log_params(self, params) -> None:
        self.params.update(dict(params))


class _FakeTracker:
    """An ExperimentTracker double that records each ``start_run`` block."""

    def __init__(self) -> None:
        self.runs: list[_RunHandle] = []

    def start_run(self, run_name=None, *, params=None, tags=None):
        return _RunHandle(self, run_name, dict(params or {}), dict(tags or {}))


# --------------------------------------------------------------------------- #
# Prompt 22 — Bayesian HPO: behaviour
# --------------------------------------------------------------------------- #
def test_hpo_runs_budget_logs_every_trial_and_picks_best() -> None:
    snap = build_training_snapshot(_examples(12), gold_checksum=_gold().checksum())
    tracker = _FakeTracker()
    trainer = _ConfigSensitiveTrainer()

    study = optimize_hyperparameters(
        snap,
        _BASE_ID,
        trainer=trainer,
        sampler=_GridSampler(_hpo_grid()),
        n_trials=10,
        k_folds=5,
        tracker=tracker,
        git_sha="abc1234",
    )

    # ~10 trials (a budget, not a sweep) — every trial recorded in the study
    assert study.n_trials == 10
    assert len(study.trials) == 10
    # Bayesian search selects the optimum the trainer encodes
    assert study.best_config.r == 12
    assert study.best_params["r"] == 12
    assert study.sampler == "grid-test"
    # every trial logged to the Prompt 19 tracker, bound to the dataset snapshot
    assert len(tracker.runs) == 10
    assert all(r.dataset_version == snap.snapshot_hash for r in tracker.runs)
    assert all("cv_score" in r.metrics for r in tracker.runs)
    assert all("r" in r.params for r in tracker.runs)
    # 5-fold CV ran for each of the 10 trials (GAMP 5 D11)
    assert len(trainer.ranks_seen) == 10 * 5


def test_hpo_study_is_reproducible() -> None:
    snap = build_training_snapshot(_examples(12), gold_checksum=_gold().checksum())
    common = dict(n_trials=10, k_folds=5, git_sha="abc1234")
    s1 = optimize_hyperparameters(
        snap, _BASE_ID, trainer=_ConfigSensitiveTrainer(),
        sampler=_GridSampler(_hpo_grid()), created_utc="t1", **common,
    )
    s2 = optimize_hyperparameters(
        snap, _BASE_ID, trainer=_ConfigSensitiveTrainer(),
        sampler=_GridSampler(_hpo_grid()), created_utc="t2", **common,
    )
    # content-addressed + time-independent => the search is reproducible
    assert s1.study_id == s2.study_id
    assert s1.as_dict()["best_config"]["r"] == 12
    assert len(s1.as_dict()["trials"]) == 10


def test_hpo_best_config_feeds_finetune_lora(tmp_path) -> None:
    snap = build_training_snapshot(_examples(12), gold_checksum=_gold().checksum())
    study = optimize_hyperparameters(
        snap, _BASE_ID, trainer=_ConfigSensitiveTrainer(),
        sampler=_GridSampler(_hpo_grid()), n_trials=10, k_folds=5, git_sha="abc1234",
    )

    run = finetune_lora(
        snap, _BASE_ID, k_folds=2, hpo_study=study, trainer=_FakeTrainer(),
        adapter_cache_dir_override=tmp_path, git_sha="abc1234",
    )
    # Prompt 15 trains and registers exactly the HPO-selected best config
    assert run.lora_config.r == 12
    # the run is traceable back to the search that produced its hyper-parameters
    assert run.manifest["hpo"]["study_id"] == study.study_id
    assert run.manifest["hpo"]["best_params"]["r"] == 12
    assert run.manifest["hpo"]["sampler"] == "grid-test"


def test_hpo_requires_optuna_when_no_sampler_injected() -> None:
    snap = build_training_snapshot(_examples(6), gold_checksum=_gold().checksum())
    # the default sampler is Optuna; absent it raises (no silent grid fallback)
    with pytest.raises(FineTuneUnavailable):
        optimize_hyperparameters(snap, _BASE_ID, trainer=_FakeTrainer(), n_trials=2, k_folds=2)


def test_hpo_validates_kfolds_and_trials() -> None:
    snap = build_training_snapshot(_examples(6), gold_checksum=_gold().checksum())
    with pytest.raises(FineTuneError):
        optimize_hyperparameters(
            snap, _BASE_ID, trainer=_FakeTrainer(), sampler=_GridSampler(_hpo_grid()), k_folds=1
        )
    with pytest.raises(FineTuneError):
        optimize_hyperparameters(
            snap, _BASE_ID, trainer=_FakeTrainer(), sampler=_GridSampler(_hpo_grid()), n_trials=0
        )


# --------------------------------------------------------------------------- #
# Prompt 22 — confidence-calibration head
# --------------------------------------------------------------------------- #
def test_temperature_and_platt_scaling_reduce_ece() -> None:
    # Overconfident: a stated 0.9 confidence but only 7/12 are actually correct.
    confidences = [0.9] * 12
    correct = [True] * 7 + [False] * 5

    temp = fit_temperature_scaling(confidences, correct)
    rep_t = calibration_report(temp, confidences, correct, n_bins=10)
    assert rep_t["method"] == "temperature"
    assert rep_t["ece_before"] > 0.2  # badly miscalibrated to start
    assert rep_t["ece_after"] < rep_t["ece_before"]
    assert rep_t["ece_after"] < 0.1  # 0.9 -> ~0.58 (the empirical accuracy)

    platt = fit_platt_scaling(confidences, correct)
    rep_p = calibration_report(platt, confidences, correct, n_bins=10)
    assert rep_p["method"] == "platt"
    assert rep_p["ece_after"] <= rep_p["ece_before"] + 1e-9
    # the head maps a raw confidence into [0, 1]
    assert 0.0 <= temp.calibrate([0.9])[0] <= 1.0


def test_calibration_length_mismatch_and_empty_raise() -> None:
    with pytest.raises(FineTuneError):
        fit_temperature_scaling([0.9, 0.8], [True])
    with pytest.raises(FineTuneError):
        fit_platt_scaling([], [])


# --------------------------------------------------------------------------- #
# Prompt 22 — calibration is a first-class promotion gate
# --------------------------------------------------------------------------- #
def test_miscalibrated_candidate_is_not_promotable_even_if_dominant(tmp_path) -> None:
    registry = ModelRegistry(InMemoryRegistryStore())
    run = _make_run(tmp_path, gold_checksum=_gold().checksum())

    # perfect_bundle is always top1-correct (dominates with no incumbent) but states
    # 0.9 confidence => gold ECE = |1.0 - 0.9| = 0.1, which fails a 0.05 gate.
    model_id = register_if_eligible(
        run,
        registry=registry,
        gold_set=_gold(),
        candidate_bundle=_perfect_bundle(),
        max_ece=0.05,
    )
    entry = registry.get(model_id)
    assert entry.extra["ece"] == pytest.approx(0.1)
    assert entry.extra["dominated_incumbent"] is True  # it IS more accurate
    assert entry.extra["ece_gate_passed"] is False
    assert entry.extra["promotable"] is False
    # miscalibrated => stays CANDIDATE, never shadowed
    assert registry.current_status(model_id) is ModelStatus.CANDIDATE


def test_calibrated_candidate_passes_the_ece_gate(tmp_path) -> None:
    registry = ModelRegistry(InMemoryRegistryStore())
    run = _make_run(tmp_path, gold_checksum=_gold().checksum())

    # a looser absolute gate the raw 0.1 ECE clears -> promotable
    model_id = register_if_eligible(
        run,
        registry=registry,
        gold_set=_gold(),
        candidate_bundle=_perfect_bundle(),
        max_ece=0.2,
    )
    entry = registry.get(model_id)
    assert entry.extra["ece_gate_passed"] is True
    assert entry.extra["promotable"] is True
    assert registry.current_status(model_id) is ModelStatus.SHADOW


def test_calibration_head_rewrites_confidence_for_the_gate(tmp_path) -> None:
    registry = ModelRegistry(InMemoryRegistryStore())
    run = _make_run(tmp_path, gold_checksum=_gold().checksum())

    # The model is perfectly accurate (accuracy 1.0) but under-confident at 0.9.
    # A head fit on (0.9 -> all correct) sharpens confidence toward 1.0, so the
    # calibrated gold ECE drops below a strict 0.05 gate the raw model would fail.
    head = fit_temperature_scaling([0.9, 0.9, 0.9, 0.9], [True, True, True, True])
    model_id = register_if_eligible(
        run,
        registry=registry,
        gold_set=_gold(),
        candidate_bundle=_perfect_bundle(),
        calibration_head=head,
        max_ece=0.05,
    )
    entry = registry.get(model_id)
    assert entry.extra["calibrated"] is True
    assert entry.extra["calibration"]["method"] == "temperature"
    assert entry.extra["ece"] < 0.05  # measured on the calibrated model
    assert entry.extra["ece_gate_passed"] is True
    assert registry.current_status(model_id) is ModelStatus.SHADOW


# --------------------------------------------------------------------------- #
# Prompt 22 — contradiction detection: test doubles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _VR:
    """A VerificationResult duck type (the detector reads only ``verdict``)."""

    verdict: str


@dataclass(frozen=True)
class _CEx:
    """A ContradictionExample duck type."""

    record_hash: str
    label: bool
    features: dict


def _contradiction_examples(n_pos: int = 20, n_neg: int = 20) -> list[_CEx]:
    """A separable labelled set: contradictions disagree across modality + over-integrate."""

    out: list[_CEx] = []
    for i in range(n_pos):
        out.append(
            _CEx(
                f"sha256:pos{i:03d}",
                True,
                {"nmr_ms_disagree": 1.0, "integration_rel_error": 0.80 + 0.01 * i},
            )
        )
    for i in range(n_neg):
        out.append(
            _CEx(
                f"sha256:neg{i:03d}",
                False,
                {"nmr_ms_disagree": 0.0, "integration_rel_error": 0.02 * i},
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Prompt 22 — deterministic contradiction rules (complement the Prompt 7 verifier)
# --------------------------------------------------------------------------- #
def test_detect_contradictions_flags_each_kind() -> None:
    # (a) no single structure is consistent
    r = detect_contradictions(verification_results=[_VR("inconsistent"), _VR("inconclusive")])
    assert "no_consistent_structure" in r.kinds
    # ...but a single consistent verdict clears it
    r = detect_contradictions(verification_results=[_VR("consistent"), _VR("inconsistent")])
    assert "no_consistent_structure" not in r.kinds

    # (b) cross-modal: NMR top != MS top
    r = detect_contradictions(cross_modal=CrossModalEvidence(nmr_top_id="A", ms_top_id="B"))
    assert "nmr_ms_disagreement" in r.kinds
    # (b) cross-modal: retention time does not corroborate
    r = detect_contradictions(cross_modal=CrossModalEvidence(rt_corroborated=False))
    assert "rt_disagreement" in r.kinds

    # (c) intra-spectral: integration vs proton count
    r = detect_contradictions(
        intra_spectral=IntraSpectralEvidence(proton_integration_sum=4.0, expected_proton_count=12)
    )
    assert "integration_mismatch" in r.kinds
    # (c) intra-spectral: multiplicity (triplet => 2 neighbours) vs reality (3)
    r = detect_contradictions(
        intra_spectral=IntraSpectralEvidence(multiplicity="t", n_coupling_neighbors=3)
    )
    assert "multiplicity_mismatch" in r.kinds
    # (c) intra-spectral: shift outside its plausible window
    r = detect_contradictions(
        intra_spectral=IntraSpectralEvidence(
            shift_ppm=15.0, shift_window=(0.0, 12.0), nucleus="1H"
        )
    )
    assert "shift_out_of_range" in r.kinds


def test_detect_contradictions_surfaces_to_reviewer_and_active_learning_queue() -> None:
    queue = InMemoryActiveLearningQueue()
    report = detect_contradictions(
        record_hash="sha256:recX",
        cross_modal=CrossModalEvidence(nmr_top_id="A", ms_top_id="B"),
        queue=queue,
        created_utc="2026-06-07T00:00:00+00:00",
    )
    # severity 0.8 >= 0.5 -> a contradiction
    assert report.is_contradiction is True
    rd = report.to_reviewer_dict()
    assert rd["record_hash"] == "sha256:recX"
    assert rd["is_contradiction"] is True
    assert any(s["kind"] == "nmr_ms_disagreement" for s in rd["signals"])
    # the hard case is fed to the Prompt 16 active-learning queue
    assert len(queue.items) == 1
    item = queue.items[0]
    assert item.record_hash == "sha256:recX"
    assert item.severity == pytest.approx(0.8)
    assert "nmr_ms_disagreement" in item.kinds


def test_detect_contradictions_below_threshold_is_not_queued() -> None:
    queue = InMemoryActiveLearningQueue()
    report = detect_contradictions(
        record_hash="sha256:recY",
        # rel error 1/12 ~ 0.083 < 0.5 tolerance -> no signal at all
        intra_spectral=IntraSpectralEvidence(proton_integration_sum=11.0, expected_proton_count=12),
        queue=queue,
    )
    assert report.is_contradiction is False
    assert report.signals == ()
    assert queue.items == []


# --------------------------------------------------------------------------- #
# Prompt 22 — the trained contradiction model (K-fold CV + calibration + lineage)
# --------------------------------------------------------------------------- #
def test_train_contradiction_detector_cv_calibration_and_lineage() -> None:
    examples = _contradiction_examples(20, 20)
    run = train_contradiction_detector(
        examples, k_folds=5, seed=0, git_sha="abc1234", created_utc="t1", gold_checksum="sha256:gold"
    )

    # K-fold CV (GAMP 5 D11) with honest per-fold metrics
    assert run.k_folds == 5
    assert len(run.fold_metrics) == 5
    assert run.row_count == 40
    assert run.n_positive == 20
    assert run.feature_names == ("integration_rel_error", "nmr_ms_disagree")  # sorted
    assert run.f1_mean > 0.8  # learns the separation

    # calibrated ECE is a first-class acceptance gate
    assert run.calibration_passed is True
    assert run.ece_calibrated <= run.max_ece

    # full lineage (hard rule 2)
    m = run.manifest
    assert m["kind"] == "contradiction_detector"
    assert m["git_sha"] == "abc1234"
    assert m["gold_checksum"] == "sha256:gold"
    assert m["feature_names"] == ["integration_rel_error", "nmr_ms_disagree"]
    assert len(m["fold_metrics"]) == 5

    # reproducible identity (created_utc is provenance, not part of run_id)
    run2 = train_contradiction_detector(
        examples, k_folds=5, seed=0, git_sha="abc1234", created_utc="t2", gold_checksum="sha256:gold"
    )
    assert run.run_id == run2.run_id

    # the trained model discriminates clear cases
    assert run.model.flag({"nmr_ms_disagree": 1.0, "integration_rel_error": 0.9}) is True
    assert run.model.flag({"nmr_ms_disagree": 0.0, "integration_rel_error": 0.0}) is False


def test_train_contradiction_detector_excludes_holdout() -> None:
    examples = _contradiction_examples(20, 20)
    holdout = [examples[0].record_hash, examples[1].record_hash, examples[20].record_hash]
    run = train_contradiction_detector(
        examples, k_folds=5, holdout_exclusion_hashes=holdout, git_sha="x", created_utc="t"
    )
    # the holdout never enters training (hard rule 1)
    assert run.row_count == 40 - 3


def test_train_contradiction_detector_validates_inputs() -> None:
    with pytest.raises(FineTuneError):  # fewer than k_folds examples
        train_contradiction_detector(_contradiction_examples(2, 1), k_folds=5)
    with pytest.raises(FineTuneError):  # examples expose no features
        train_contradiction_detector(
            [_CEx(f"sha256:e{i}", i % 2 == 0, {}) for i in range(6)], k_folds=5
        )


@dataclass(frozen=True)
class _GroupedCEx:
    """A ContradictionExample duck type that also carries an InChIKey (grouped CV)."""

    record_hash: str
    label: bool
    features: dict
    inchikey: str


def _grouped_contradiction_examples(n_mol: int, scans_per_mol: int) -> list[_GroupedCEx]:
    out: list[_GroupedCEx] = []
    for m in range(n_mol):
        block = f"CMOL{m:010d}"  # exactly 14 chars
        label = m % 2 == 0
        for s in range(scans_per_mol):
            out.append(
                _GroupedCEx(
                    record_hash=f"sha256:cmol{m:02d}scan{s:02d}",
                    label=label,
                    features={
                        "nmr_ms_disagree": 1.0 if label else 0.0,
                        "integration_rel_error": 0.80 if label else 0.05,
                    },
                    inchikey=f"{block}-{m}{s}",
                )
            )
    return out


def test_contradiction_detector_uses_grouped_cv() -> None:
    # 6 molecules x 4 scans -> grouped CV with 6 leak-proof groups.
    run = train_contradiction_detector(
        _grouped_contradiction_examples(n_mol=6, scans_per_mol=4), k_folds=3, seed=0
    )
    assert run.manifest["cv"] == {
        "strategy": "group_kfold",
        "group_key": "molecule_skeleton",
        "n_groups": 6,
    }
    assert run.row_count == 24


def test_contradiction_detector_requires_at_least_k_groups() -> None:
    # 2 molecules but k=3 -> too few groups for leak-proof CV (even with 10 rows).
    with pytest.raises(FineTuneError, match="molecule groups"):
        train_contradiction_detector(
            _grouped_contradiction_examples(n_mol=2, scans_per_mol=5), k_folds=3, seed=0
        )


def test_detect_contradictions_adds_learned_model_signal() -> None:
    run = train_contradiction_detector(_contradiction_examples(20, 20), k_folds=5)

    # a clear positive by the trained model's features -> a learned signal appears
    report = detect_contradictions(
        record_hash="sha256:hardcase",
        cross_modal=CrossModalEvidence(nmr_top_id="A", ms_top_id="B"),
        intra_spectral=IntraSpectralEvidence(proton_integration_sum=2.0, expected_proton_count=12),
        model=run.model,
    )
    assert "learned_contradiction" in report.kinds  # only the model can emit this

    # a clear negative -> the model adds nothing
    report_neg = detect_contradictions(
        cross_modal=CrossModalEvidence(nmr_top_id="A", ms_top_id="A"),
        intra_spectral=IntraSpectralEvidence(proton_integration_sum=12.0, expected_proton_count=12),
        model=run.model,
    )
    assert "learned_contradiction" not in report_neg.kinds
