"""LoRA domain fine-tuning pipeline (Prompt 15, Roadmap Layer 3).

Once enough reviewer-validated in-house spectra have accumulated (Prompt 16 /
Prompt 20), SpectraCheck fine-tunes a small **LoRA adapter** on top of the
pretrained Layer-1 shift predictor / embedding head (Prompt 6) so the system
adapts to a lab's own chemistry without retraining — or trusting — the base
model. The adapter is trained on Modal, validated by K-fold cross-validation
(GAMP 5 Appendix D11), and only registered through the Prompt 17 dominance gate.

Three stages, three functions:

* :func:`build_training_snapshot` — freeze the validated-example set into an
  **immutable, content-addressed snapshot** (hash + row count + per-class /
  nucleus / field / solvent distributions). The snapshot hash is the
  ``training_data_lineage`` recorded in the registry (Prompt 13).
* :func:`finetune_lora` — train only the adapter (the base is frozen) with
  reproducible **K-fold cross-validation**: per-fold ¹H/¹³C MAE, calibration, and
  coverage, aggregated mean ± std, with the GPU-hours and Modal cost logged. The
  adapter + the full run manifest (hyperparameters, per-fold metrics, snapshot
  hash, base id, code git SHA) are saved.
* :func:`register_if_eligible` — compute the Prompt 17 metric vector on the frozen
  gold set, call the dominance gate, register the adapter as ``candidate``
  **always**, promote it to ``shadow`` only if it does not regress, and **never**
  auto-promote to ``production`` (that needs human sign-off).

Hard rules (enforced here, not just documented)
------------------------------------------------
1. **Never train on the gold / holdout set (Prompt 17).** Enforced by *hash
   exclusion*: :func:`build_training_snapshot` drops any example whose
   ``record_hash`` is in the holdout, and both it and :func:`finetune_lora`
   re-assert via :func:`assert_training_excludes_holdout` that the frozen
   snapshot does not intersect the holdout — so even a hand-built snapshot cannot
   leak. The snapshot is additionally *bound to the gold-set checksum*, and
   :func:`register_if_eligible` refuses to register if the run was validated
   against a different gold set than the one it is gated on.
2. **Lineage is mandatory.** No adapter is registered without a snapshot hash,
   per-fold metrics, and the code git SHA.
3. **Weights / adapters are cached out of git** (reuse the Prompt 6 cache policy:
   ``$MOLTRACE_LORA_CACHE`` else ``~/.cache/moltrace/lora``).

Optional dependencies
---------------------
Actual training needs ``torch`` + ``peft`` + ``modal`` (none vendored). Following
the house pattern (``rag.py`` / ``nmrnet_wrapper.py``), those are imported
**lazily** inside the default trainer, which raises :class:`FineTuneUnavailable`
with an actionable message when they are absent and **never fabricates** metrics
or an adapter. The orchestration (snapshotting, fold partitioning, aggregation,
gating, registration) is pure-Python and fully unit-testable by injecting a
trainer, so this module imports and runs on a CPU-only host with none of the
heavy deps installed.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from moltrace.spectroscopy.ai.registry import (
    ModelRegistry,
    ModelRole,
    ModelStatus,
    TrainingDataLineage,
)
from moltrace.spectroscopy.data.datasets_pipeline import (
    HoldoutLeakageError,
    Splits,
    assert_training_excludes_holdout,
)
from moltrace.spectroscopy.eval.harness import (
    METRIC_DIRECTIONS,
    GoldMetricVector,
    GoldSet,
    ModelBundle,
    dominates,
    evaluate,
)
from moltrace.spectroscopy.infra.contract import content_hash
from moltrace.spectroscopy.infra.versioning import current_git_sha

__all__ = [
    "DEFAULT_LORA_TARGET_MODULES",
    "DEFAULT_MODAL_GPU_USD_PER_HOUR",
    "FineTuneError",
    "FineTuneRun",
    "FineTuneUnavailable",
    "FinalAdapter",
    "FoldMetrics",
    "FoldResult",
    "FoldTrainer",
    "LoRAConfig",
    "Snapshot",
    "TrainingExample",
    "adapter_cache_dir",
    "build_training_snapshot",
    "finetune_lora",
    "register_if_eligible",
]

# Modal A100-40GB on-demand rate (USD/GPU-hour); override per deployment. With the
# ~$200/run target this is ~72 GPU-hours, comfortable for K-fold + a final fit.
DEFAULT_MODAL_GPU_USD_PER_HOUR = 2.78

# Default LoRA injection points. NMRNet is a Uni-Mol / SE(3) Transformer
# (nmrnet_wrapper.py), so the attention projections are the natural adapter
# targets; tune to the actual base via the ``target_modules`` argument.
DEFAULT_LORA_TARGET_MODULES: tuple[str, ...] = ("q_proj", "k_proj", "v_proj", "out_proj")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class FineTuneError(RuntimeError):
    """Base class for fine-tuning pipeline errors."""


class FineTuneUnavailable(FineTuneError):
    """Raised when the training backend (torch / peft / Modal) cannot be used."""


# --------------------------------------------------------------------------- #
# The training example contract (duck-typed; NormalizedRecord satisfies it)
# --------------------------------------------------------------------------- #
@runtime_checkable
class TrainingExample(Protocol):
    """The minimum a validated example must expose to be snapshotted.

    :class:`moltrace.spectroscopy.data.datasets_pipeline.NormalizedRecord`
    satisfies this protocol; any equivalent record does too.
    """

    record_hash: str
    source_key: str
    modality: Any
    spectrum: Mapping[str, Any] | None


# --------------------------------------------------------------------------- #
# Immutable training snapshot
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Snapshot:
    """A frozen, content-addressed view of the validated-example set.

    ``snapshot_hash`` is a deterministic ``sha256:<hex>`` over the sorted record
    hashes + the composition + the bound ``gold_checksum`` (NOT over ``git_sha``
    or ``created_utc``, which are provenance, not identity) — so freezing the same
    validated set against the same holdout always yields the same hash. This hash
    is the ``training_data_lineage.dataset_snapshot_hash`` in the registry.
    """

    snapshot_hash: str
    row_count: int
    record_hashes: tuple[str, ...]  # sorted; the immutable training-set identity
    per_class_counts: dict[str, int]  # by modality
    nucleus_distribution: dict[str, int]
    field_distribution: dict[str, int]
    solvent_distribution: dict[str, int]
    source_distribution: dict[str, int]
    gold_checksum: str | None  # the holdout/gold-set this snapshot excludes against
    n_excluded_for_holdout: int
    git_sha: str
    created_utc: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_hash": self.snapshot_hash,
            "row_count": self.row_count,
            "per_class_counts": dict(self.per_class_counts),
            "nucleus_distribution": dict(self.nucleus_distribution),
            "field_distribution": dict(self.field_distribution),
            "solvent_distribution": dict(self.solvent_distribution),
            "source_distribution": dict(self.source_distribution),
            "gold_checksum": self.gold_checksum,
            "n_excluded_for_holdout": self.n_excluded_for_holdout,
            "git_sha": self.git_sha,
            "created_utc": self.created_utc,
        }


def _modality_str(modality: Any) -> str:
    return getattr(modality, "value", None) or str(modality)


def _spectrum_of(rec: Any) -> Mapping[str, Any]:
    spectrum = getattr(rec, "spectrum", None)
    return spectrum if isinstance(spectrum, Mapping) else {}


def _nucleus_of(rec: Any) -> str:
    nuc = _spectrum_of(rec).get("nucleus")
    if nuc:
        return str(nuc)
    modality = _modality_str(rec.modality).upper()
    if "1H" in modality:
        return "1H"
    if "13C" in modality:
        return "13C"
    return "unknown"


def _field_of(rec: Any) -> str:
    field_mhz = _spectrum_of(rec).get("field_mhz")
    return str(field_mhz) if field_mhz is not None else "unknown"


def _solvent_of(rec: Any) -> str:
    solvent = _spectrum_of(rec).get("solvent")
    return str(solvent) if solvent else "unknown"


def _counts(items: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return dict(sorted(out.items()))


def build_training_snapshot(
    examples: Iterable[TrainingExample],
    *,
    splits: Splits | None = None,
    holdout_exclusion_hashes: Iterable[str] | None = None,
    gold_checksum: str | None = None,
    git_sha: str | None = None,
    created_utc: str | None = None,
) -> Snapshot:
    """Freeze ``examples`` into an immutable, content-addressed :class:`Snapshot`.

    Holdout records are removed by *hash exclusion* (the Prompt 17 holdout is
    sacred): any example whose ``record_hash`` is in ``splits.
    holdout_exclusion_hashes`` (or the explicit ``holdout_exclusion_hashes`` set)
    is dropped, and the retained set is then re-checked via
    :func:`assert_training_excludes_holdout` — so no holdout row can survive.

    ``gold_checksum`` binds the snapshot to the gold/holdout set it was built
    against (typically ``GoldSet.checksum()``); :func:`register_if_eligible`
    verifies the gate uses that same gold set. Pass it (or a ``splits``) to make
    the binding auditable.
    """

    exclusion: set[str] = set()
    if splits is not None:
        exclusion |= set(splits.holdout_exclusion_hashes)
    if holdout_exclusion_hashes is not None:
        exclusion |= set(holdout_exclusion_hashes)

    materialized = list(examples)
    retained = [rec for rec in materialized if rec.record_hash not in exclusion]
    retained_hashes = sorted(rec.record_hash for rec in retained)
    n_excluded = len(materialized) - len(retained)

    # Proof the exclusion held — belt-and-suspenders over the filter above.
    if splits is not None:
        assert_training_excludes_holdout(retained_hashes, splits)
    elif exclusion:
        leaked = set(retained_hashes) & exclusion
        if leaked:  # pragma: no cover - the filter above guarantees this is empty
            raise HoldoutLeakageError(
                f"{len(leaked)} holdout record hash(es) survived snapshot exclusion"
            )

    per_class = _counts(_modality_str(rec.modality) for rec in retained)
    nucleus = _counts(_nucleus_of(rec) for rec in retained)
    field_dist = _counts(_field_of(rec) for rec in retained)
    solvent = _counts(_solvent_of(rec) for rec in retained)
    source = _counts(getattr(rec, "source_key", "unknown") for rec in retained)

    body = {
        "record_hashes": retained_hashes,
        "row_count": len(retained_hashes),
        "per_class_counts": per_class,
        "nucleus_distribution": nucleus,
        "field_distribution": field_dist,
        "solvent_distribution": solvent,
        "source_distribution": source,
        "gold_checksum": gold_checksum,
    }
    snapshot_hash = content_hash(body)

    return Snapshot(
        snapshot_hash=snapshot_hash,
        row_count=len(retained_hashes),
        record_hashes=tuple(retained_hashes),
        per_class_counts=per_class,
        nucleus_distribution=nucleus,
        field_distribution=field_dist,
        solvent_distribution=solvent,
        source_distribution=source,
        gold_checksum=gold_checksum,
        n_excluded_for_holdout=n_excluded,
        git_sha=git_sha if git_sha is not None else current_git_sha(),
        created_utc=created_utc if created_utc is not None else datetime.now(UTC).isoformat(),
    )


# --------------------------------------------------------------------------- #
# LoRA config + per-fold results
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LoRAConfig:
    """LoRA hyper-parameters. Low rank; train only the adapter, freeze the base."""

    r: int = 8  # low rank (8-16)
    alpha: int = 16
    dropout: float = 0.05
    target_modules: tuple[str, ...] = DEFAULT_LORA_TARGET_MODULES

    def as_dict(self) -> dict[str, Any]:
        return {
            "r": self.r,
            "alpha": self.alpha,
            "dropout": self.dropout,
            "target_modules": list(self.target_modules),
        }


@dataclass(frozen=True)
class FoldResult:
    """What a trainer returns for one trained-and-evaluated fold."""

    mae_1h: float
    mae_13c: float
    calibration: float  # e.g. ECE on the held-out fold (lower = better)
    coverage: float  # fraction of atoms with a calibrated prediction (higher = better)
    gpu_hours: float


@dataclass(frozen=True)
class FoldMetrics:
    """One fold's recorded metrics (FoldResult + the fold's shape)."""

    fold: int
    n_train: int
    n_eval: int
    mae_1h: float
    mae_13c: float
    calibration: float
    coverage: float
    gpu_hours: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "fold": self.fold,
            "n_train": self.n_train,
            "n_eval": self.n_eval,
            "mae_1h": self.mae_1h,
            "mae_13c": self.mae_13c,
            "calibration": self.calibration,
            "coverage": self.coverage,
            "gpu_hours": self.gpu_hours,
        }


@dataclass(frozen=True)
class FinalAdapter:
    """The deliverable adapter a trainer produces from the full training set."""

    path: str
    sha256: str  # "sha256:<hex>" content address of the adapter artifact
    gpu_hours: float
    confidence_band_ppm: float | None = None  # validated max uncertainty (ppm)


# --------------------------------------------------------------------------- #
# The trainer seam (default = Modal/peft; injectable for tests + custom runtimes)
# --------------------------------------------------------------------------- #
@runtime_checkable
class FoldTrainer(Protocol):
    """Trains the LoRA adapter. The default runs on Modal; inject your own."""

    def train_and_eval(
        self,
        *,
        fold: int,
        train_hashes: Sequence[str],
        eval_hashes: Sequence[str],
        base_model_id: str,
        lora_config: LoRAConfig,
        snapshot: Snapshot,
    ) -> FoldResult: ...

    def fit_final(
        self,
        *,
        train_hashes: Sequence[str],
        base_model_id: str,
        lora_config: LoRAConfig,
        snapshot: Snapshot,
        out_dir: Path,
    ) -> FinalAdapter: ...


class _ModalLoRATrainer:
    """Default trainer: LoRA fine-tuning on Modal with ``peft`` + ``torch``.

    Deps are imported lazily; when any is missing this raises
    :class:`FineTuneUnavailable` (mirroring ``NMRNetUnavailable``). The model
    forward + Modal app wiring is an integration point filled when the deps and a
    Modal token are present — this wrapper never fabricates metrics or an adapter.
    """

    _REQUIRED = ("modal", "torch", "peft")

    def __init__(self, *, gpu: str = "A100-40GB", app_name: str = "moltrace-lora") -> None:
        self.gpu = gpu
        self.app_name = app_name

    def _require(self) -> None:
        missing = [m for m in self._REQUIRED if importlib.util.find_spec(m) is None]
        if missing:
            raise FineTuneUnavailable(
                "LoRA fine-tuning requires "
                + ", ".join(self._REQUIRED)
                + f" (missing: {', '.join(missing)}). Install the training extra and "
                "configure a Modal token; see the Roadmap Layer 3 runbook."
            )

    def train_and_eval(self, **_: Any) -> FoldResult:
        self._require()
        raise FineTuneUnavailable(  # integration point — fill from the Modal app
            "Modal LoRA fold training is an unfilled integration point "
            "(deps present; wire the Modal app + peft training loop)."
        )

    def fit_final(self, **_: Any) -> FinalAdapter:
        self._require()
        raise FineTuneUnavailable(
            "Modal LoRA final fit is an unfilled integration point "
            "(deps present; wire the Modal app + peft training loop)."
        )


# --------------------------------------------------------------------------- #
# Cache (out of git — reuse the Prompt 6 cache policy)
# --------------------------------------------------------------------------- #
def adapter_cache_dir() -> Path:
    """Where adapters are cached. ``$MOLTRACE_LORA_CACHE`` else ``~/.cache/...``."""

    return Path(
        os.environ.get("MOLTRACE_LORA_CACHE", Path.home() / ".cache" / "moltrace" / "lora")
    )


def _slug(*parts: str) -> str:
    return "__".join(re.sub(r"[^A-Za-z0-9._-]+", "-", part) for part in parts)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


# --------------------------------------------------------------------------- #
# Fold partition + aggregation
# --------------------------------------------------------------------------- #
def _assign_folds(record_hashes: Sequence[str], k: int, seed: int) -> list[list[str]]:
    """Deterministically partition record hashes into ``k`` folds (seeded hash)."""

    folds: list[list[str]] = [[] for _ in range(k)]
    for record_hash in sorted(record_hashes):
        digest = hashlib.sha256(f"{record_hash}|{seed}".encode()).hexdigest()
        folds[int(digest[:16], 16) % k].append(record_hash)
    return folds


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    vals = list(values)
    if not vals:
        return 0.0, 0.0
    return float(statistics.fmean(vals)), float(statistics.pstdev(vals))


@dataclass(frozen=True)
class FineTuneRun:
    """The complete, reproducible record of one fine-tuning run."""

    snapshot_hash: str
    base_model_id: str
    semantic_version: str
    nucleus: str | None
    lora_config: LoRAConfig
    k_folds: int
    seed: int
    row_count: int
    fold_metrics: tuple[FoldMetrics, ...]
    mae_1h_mean: float
    mae_1h_std: float
    mae_13c_mean: float
    mae_13c_std: float
    calibration_mean: float
    calibration_std: float
    coverage_mean: float
    coverage_std: float
    gpu_hours: float
    cost_usd: float
    adapter_path: str | None
    adapter_sha256: str | None
    confidence_band_ppm: float | None
    gold_checksum: str | None
    git_sha: str
    created_utc: str
    manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def run_id(self) -> str:
        """Deterministic content address of the full run manifest."""

        return content_hash(self.manifest)


def finetune_lora(
    snapshot: Snapshot,
    base_model_id: str,
    k_folds: int = 5,
    target_modules: Sequence[str] | None = None,
    *,
    lora_config: LoRAConfig | None = None,
    splits: Splits | None = None,
    trainer: FoldTrainer | None = None,
    seed: int = 0,
    semantic_version: str = "0.1.0",
    nucleus: str | None = None,
    gpu_cost_per_hour: float = DEFAULT_MODAL_GPU_USD_PER_HOUR,
    git_sha: str | None = None,
    adapter_cache_dir_override: str | Path | None = None,
    created_utc: str | None = None,
) -> FineTuneRun:
    """Train a LoRA adapter on ``snapshot`` over the frozen ``base_model_id``.

    LoRA trains *only* the adapter (low rank ``r`` 8-16; the base is frozen). For
    each of ``k_folds`` folds the trainer trains on the other folds and evaluates
    on the held-out one — recording per-fold ¹H/¹³C MAE, calibration, and
    coverage — then a final adapter is fit on the full set. Per-fold metrics are
    aggregated mean ± std, and the actual GPU-hours + Modal cost are logged
    (target ~$200/run). The adapter is saved under the out-of-git cache and the
    full run manifest (hyper-params, per-fold metrics, snapshot hash, base id,
    code git SHA) is attached.

    The training backend is injectable (``trainer``); the default runs on Modal
    with ``peft`` + ``torch`` and raises :class:`FineTuneUnavailable` when those
    are absent. Passing ``splits`` re-asserts the holdout exclusion on the frozen
    snapshot before any training starts (so a hand-built snapshot cannot leak).
    """

    if k_folds < 2:
        raise FineTuneError("k_folds must be >= 2 for cross-validation")

    # Hard rule re-assert: refuse to train if the snapshot touches the holdout.
    if splits is not None:
        assert_training_excludes_holdout(snapshot.record_hashes, splits)

    cfg = lora_config or LoRAConfig()
    if target_modules is not None:
        cfg = replace(cfg, target_modules=tuple(target_modules))
    if not (8 <= cfg.r <= 16):  # low-rank discipline (spec: r = 8-16)
        raise FineTuneError(f"LoRA rank r must be in [8, 16]; got {cfg.r}")

    trainer = trainer or _ModalLoRATrainer()
    resolved_git_sha = git_sha if git_sha is not None else current_git_sha()

    folds = _assign_folds(snapshot.record_hashes, k_folds, seed)
    fold_metrics: list[FoldMetrics] = []
    total_gpu_hours = 0.0
    for i in range(k_folds):
        eval_hashes = tuple(folds[i])
        train_hashes = tuple(h for j, fold in enumerate(folds) if j != i for h in fold)
        result = trainer.train_and_eval(
            fold=i,
            train_hashes=train_hashes,
            eval_hashes=eval_hashes,
            base_model_id=base_model_id,
            lora_config=cfg,
            snapshot=snapshot,
        )
        total_gpu_hours += result.gpu_hours
        fold_metrics.append(
            FoldMetrics(
                fold=i,
                n_train=len(train_hashes),
                n_eval=len(eval_hashes),
                mae_1h=result.mae_1h,
                mae_13c=result.mae_13c,
                calibration=result.calibration,
                coverage=result.coverage,
                gpu_hours=result.gpu_hours,
            )
        )

    # Final deliverable adapter: fit on the full training set, cached out of git.
    cache_root = (
        Path(adapter_cache_dir_override) if adapter_cache_dir_override else adapter_cache_dir()
    )
    out_dir = cache_root / _slug(base_model_id, snapshot.snapshot_hash, semantic_version)
    final = trainer.fit_final(
        train_hashes=snapshot.record_hashes,
        base_model_id=base_model_id,
        lora_config=cfg,
        snapshot=snapshot,
        out_dir=out_dir,
    )
    total_gpu_hours += final.gpu_hours
    cost_usd = total_gpu_hours * gpu_cost_per_hour

    mae_1h_mean, mae_1h_std = _mean_std([f.mae_1h for f in fold_metrics])
    mae_13c_mean, mae_13c_std = _mean_std([f.mae_13c for f in fold_metrics])
    cal_mean, cal_std = _mean_std([f.calibration for f in fold_metrics])
    cov_mean, cov_std = _mean_std([f.coverage for f in fold_metrics])

    adapter_sha256 = final.sha256 or (
        _file_sha256(Path(final.path)) if final.path and Path(final.path).exists() else None
    )

    confidence_band_ppm = final.confidence_band_ppm
    if confidence_band_ppm is None:  # fall back to the validated CV band for this nucleus
        if nucleus == "1H":
            confidence_band_ppm = mae_1h_mean + mae_1h_std
        elif nucleus == "13C":
            confidence_band_ppm = mae_13c_mean + mae_13c_std

    manifest: dict[str, Any] = {
        "snapshot_hash": snapshot.snapshot_hash,
        "base_model_id": base_model_id,
        "semantic_version": semantic_version,
        "nucleus": nucleus,
        "lora_config": cfg.as_dict(),
        "k_folds": k_folds,
        "seed": seed,
        "row_count": snapshot.row_count,
        "fold_metrics": [f.as_dict() for f in fold_metrics],
        "aggregate": {
            "mae_1h_mean": mae_1h_mean,
            "mae_1h_std": mae_1h_std,
            "mae_13c_mean": mae_13c_mean,
            "mae_13c_std": mae_13c_std,
            "calibration_mean": cal_mean,
            "calibration_std": cal_std,
            "coverage_mean": cov_mean,
            "coverage_std": cov_std,
        },
        "gpu_hours": total_gpu_hours,
        "cost_usd": cost_usd,
        "gpu_cost_per_hour": gpu_cost_per_hour,
        # NB: the adapter's *content* identity (adapter_sha256) is part of the
        # run identity, but its filesystem location is environment-specific
        # provenance — it is excluded here so ``run_id`` is path-independent and
        # reproducible. The path is preserved on ``FineTuneRun.adapter_path`` and
        # recorded in the registry ``extra``.
        "adapter_sha256": adapter_sha256,
        "confidence_band_ppm": confidence_band_ppm,
        "gold_checksum": snapshot.gold_checksum,
        "git_sha": resolved_git_sha,
    }

    return FineTuneRun(
        snapshot_hash=snapshot.snapshot_hash,
        base_model_id=base_model_id,
        semantic_version=semantic_version,
        nucleus=nucleus,
        lora_config=cfg,
        k_folds=k_folds,
        seed=seed,
        row_count=snapshot.row_count,
        fold_metrics=tuple(fold_metrics),
        mae_1h_mean=mae_1h_mean,
        mae_1h_std=mae_1h_std,
        mae_13c_mean=mae_13c_mean,
        mae_13c_std=mae_13c_std,
        calibration_mean=cal_mean,
        calibration_std=cal_std,
        coverage_mean=cov_mean,
        coverage_std=cov_std,
        gpu_hours=total_gpu_hours,
        cost_usd=cost_usd,
        adapter_path=str(out_dir),
        adapter_sha256=adapter_sha256,
        confidence_band_ppm=confidence_band_ppm,
        gold_checksum=snapshot.gold_checksum,
        git_sha=resolved_git_sha,
        created_utc=created_utc if created_utc is not None else datetime.now(UTC).isoformat(),
        manifest=manifest,
    )


# --------------------------------------------------------------------------- #
# Gated registration (Prompt 17 dominance gate + Prompt 13 registry)
# --------------------------------------------------------------------------- #
def _vector_from_snapshot(metric_snapshot: Mapping[str, float]) -> GoldMetricVector | None:
    """Rebuild a comparable :class:`GoldMetricVector` from a stored metric snapshot.

    Returns ``None`` unless every comparable metric is present (an incomplete
    snapshot can't be a valid dominance incumbent).
    """

    if not all(name in metric_snapshot for name in METRIC_DIRECTIONS):
        return None
    return GoldMetricVector(**{name: float(metric_snapshot[name]) for name in METRIC_DIRECTIONS})


def _resolve_incumbent(
    registry: ModelRegistry,
    *,
    nucleus: str | None,
    incumbent_metrics: GoldMetricVector | None,
    incumbent_bundle: ModelBundle | None,
    gold_set: GoldSet,
    k: int,
) -> GoldMetricVector | None:
    if incumbent_metrics is not None:
        return incumbent_metrics
    if incumbent_bundle is not None:
        return evaluate(incumbent_bundle, gold_set, k=k)
    entry = registry.resolve(ModelRole.LORA_ADAPTER, nucleus)
    if entry is None:
        return None
    return _vector_from_snapshot(entry.metric_snapshot)


def register_if_eligible(
    run: FineTuneRun,
    *,
    registry: ModelRegistry,
    gold_set: GoldSet,
    candidate_bundle: ModelBundle,
    incumbent_metrics: GoldMetricVector | None = None,
    incumbent_bundle: ModelBundle | None = None,
    tolerances: Mapping[str, float] | None = None,
    k: int = 5,
    dataset_tag: str | None = None,
    source: str | None = None,
) -> str | None:
    """Gate, then register the run's adapter; return its ``model_id`` (or ``None``).

    Computes the Prompt 17 metric vector for ``candidate_bundle`` (a model built
    from this run's adapter) on the frozen ``gold_set``, calls the dominance gate
    against the current incumbent, and:

    * registers the adapter as ``candidate`` **always** (with full lineage:
      snapshot hash, per-fold metrics, code git SHA — hard rule 2),
    * promotes it to ``shadow`` **only if** it dominates the incumbent (no
      regression, strict gain on >=1 metric, zero safety-critical regression),
    * **never** auto-promotes to ``production`` (human sign-off required).

    Returns ``None`` (registers nothing) only if the run produced no adapter
    artifact. The ``candidate_bundle`` is injected because building it requires
    loading the base + adapter (torch); production wires it from the adapter,
    tests pass a controlled bundle.
    """

    if not run.adapter_sha256:
        return None

    # Hard rule 1 (binding): the run must have been validated against THIS gold set.
    if run.gold_checksum and run.gold_checksum != gold_set.checksum():
        raise FineTuneError(
            "run.gold_checksum does not match the gating gold set; the adapter was "
            "validated against a different holdout — refusing to register"
        )

    candidate = evaluate(candidate_bundle, gold_set, k=k)
    incumbent = _resolve_incumbent(
        registry,
        nucleus=run.nucleus,
        incumbent_metrics=incumbent_metrics,
        incumbent_bundle=incumbent_bundle,
        gold_set=gold_set,
        k=k,
    )
    passed = True if incumbent is None else dominates(candidate, incumbent, tolerances)[0]

    lineage = TrainingDataLineage(
        dataset_snapshot_hash=run.snapshot_hash,
        row_count=run.row_count,
        dataset_tag=dataset_tag,
        source=source,
        notes=(
            f"LoRA r={run.lora_config.r} alpha={run.lora_config.alpha}; "
            f"{run.k_folds}-fold CV; git_sha={run.git_sha}"
        ),
    )
    entry = registry.register_artifact(
        role=ModelRole.LORA_ADAPTER,
        semantic_version=run.semantic_version,
        artifact_sha256=run.adapter_sha256,
        training_data_lineage=lineage,
        metric_snapshot=candidate.metric_items(),  # the 12 comparable floats only
        nucleus=run.nucleus,
        parent_base_id=run.base_model_id,
        confidence_band_ppm=run.confidence_band_ppm,
        status=ModelStatus.CANDIDATE,
        extra={
            "snapshot_hash": run.snapshot_hash,
            "gold_checksum": run.gold_checksum,
            "git_sha": run.git_sha,
            "k_folds": run.k_folds,
            "gpu_hours": run.gpu_hours,
            "cost_usd": run.cost_usd,
            "run_id": run.run_id,
            "adapter_path": run.adapter_path,
            "cv_aggregate": run.manifest.get("aggregate", {}),
            "promotable": passed,
        },
    )

    if passed:  # shadow only — never production (human sign-off gate)
        registry.set_status(
            entry.model_id,
            ModelStatus.SHADOW,
            reason="passed Prompt 17 dominance gate; shadow pending human production sign-off",
        )

    return entry.model_id
