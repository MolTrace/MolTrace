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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import numpy as np
from scipy.optimize import minimize_scalar

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
from moltrace.spectroscopy.infra.eval import expected_calibration_error, f1_score
from moltrace.spectroscopy.infra.versioning import current_git_sha

if TYPE_CHECKING:
    from moltrace.spectroscopy.infra.tracking import ExperimentTracker
    from moltrace.spectroscopy.verification import VerificationResult

__all__ = [
    "DEFAULT_LORA_TARGET_MODULES",
    "DEFAULT_MODAL_GPU_USD_PER_HOUR",
    "ActiveLearningItem",
    "ActiveLearningQueue",
    "CalibratedBundle",
    "CalibrationHead",
    "ContradictionExample",
    "ContradictionFoldMetrics",
    "ContradictionModel",
    "ContradictionModelRun",
    "ContradictionReport",
    "ContradictionSignal",
    "CrossModalEvidence",
    "FineTuneError",
    "FineTuneRun",
    "FineTuneUnavailable",
    "FinalAdapter",
    "FoldMetrics",
    "FoldResult",
    "FoldTrainer",
    "HPOSampler",
    "HPOSearchSpace",
    "HPOStudy",
    "HPOTrial",
    "InMemoryActiveLearningQueue",
    "IntraSpectralEvidence",
    "LoRAConfig",
    "Snapshot",
    "TrainingExample",
    "adapter_cache_dir",
    "build_training_snapshot",
    "calibration_report",
    "default_hpo_search_space",
    "detect_contradictions",
    "finetune_lora",
    "fit_platt_scaling",
    "fit_temperature_scaling",
    "optimize_hyperparameters",
    "register_if_eligible",
    "train_contradiction_detector",
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
    # Leak-proof CV grouping (Prompt 22b): ``record_hash -> group key`` so every
    # spectrum of a molecule/batch is kept in one fold (GroupKFold). ``None`` means
    # no grouping signal was present, so the split reduces to the per-record split.
    record_groups: Mapping[str, str] | None = None
    n_groups: int = 0  # distinct CV groups (== row_count when ungrouped)

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
            "cv_strategy": "group_kfold" if self.record_groups is not None else "kfold",
            "n_groups": self.n_groups,
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


def _group_of(rec: Any) -> str | None:
    """The leak-proof CV grouping key for a record (mirrors ``datasets_pipeline._skeleton``).

    Spectra that share a key must never straddle a cross-validation fold; otherwise
    K-fold CV leaks information between train and eval and reports optimistic,
    untrustworthy metrics — the classic batch-leakage failure of naive CV, where
    multiple scans of one batch/sample land on both sides of the split. We prefer an
    explicit batch/sample identifier when the record carries one, then fall back to
    the molecule skeleton (the InChIKey connectivity block, first 14 chars) so every
    spectrum of a molecule — and every scan of one physical sample/batch — is
    grouped together. Returns ``None`` when no grouping signal exists, in which case
    the record becomes its own group and the partition reduces to the per-record split.
    """

    for attr in ("group_key", "sample_id", "batch_key"):
        val = getattr(rec, attr, None)
        if val:
            return str(val)
    inchikey = getattr(rec, "inchikey", None) or _spectrum_of(rec).get("inchikey")
    if inchikey:
        return str(inchikey)[:14]
    return None


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

    # Leak-proof CV grouping: map every retained record to its molecule/batch group
    # (falling back to the bare record hash when no grouping signal exists). When no
    # record carries a grouping signal the map is the identity and we leave the
    # snapshot ungrouped, so the data-identity hash and the per-record fold split are
    # both unchanged — grouping only ever *tightens* CV, never silently shifts it.
    group_map = {rec.record_hash: (_group_of(rec) or rec.record_hash) for rec in retained}
    grouped = any(group != rh for rh, group in group_map.items())
    n_groups = len(set(group_map.values()))

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
    if grouped:  # only perturb the data-identity hash when grouping actually applies
        body["record_groups"] = sorted(group_map.items())
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
        record_groups=dict(sorted(group_map.items())) if grouped else None,
        n_groups=n_groups,
    )


# --------------------------------------------------------------------------- #
# LoRA config + per-fold results
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LoRAConfig:
    """LoRA hyper-parameters. Low rank; train only the adapter, freeze the base.

    ``r`` / ``alpha`` / ``dropout`` / ``learning_rate`` / ``epochs`` are the five
    knobs the Prompt 22 Bayesian HPO (:func:`optimize_hyperparameters`) searches;
    the best config it finds is what :func:`finetune_lora` then trains.
    """

    r: int = 8  # low rank (8-16)
    alpha: int = 16
    dropout: float = 0.05
    learning_rate: float = 2e-4
    epochs: int = 3
    target_modules: tuple[str, ...] = DEFAULT_LORA_TARGET_MODULES

    def as_dict(self) -> dict[str, Any]:
        return {
            "r": self.r,
            "alpha": self.alpha,
            "dropout": self.dropout,
            "learning_rate": self.learning_rate,
            "epochs": self.epochs,
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
def _assign_folds(
    record_hashes: Sequence[str],
    k: int,
    seed: int,
    *,
    groups: Mapping[str, str] | None = None,
) -> list[list[str]]:
    """Deterministically partition record hashes into ``k`` folds (seeded hash).

    When ``groups`` maps ``record_hash -> group key`` (e.g. the molecule skeleton),
    whole *groups* are assigned to a fold so every spectrum of a molecule/batch lands
    in exactly one fold — leak-proof **GroupKFold** cross-validation that prevents
    train/eval leakage across batches. With ``groups=None`` each record is its own
    group, which reproduces the historical per-record split byte-for-byte (the group
    key is then the record hash itself, so the seeded digest is unchanged).
    """

    def _key(record_hash: str) -> str:
        if groups is None:
            return record_hash
        return groups.get(record_hash, record_hash)

    # Bucket records by group key so co-grouped spectra never straddle a fold.
    members: dict[str, list[str]] = {}
    for record_hash in sorted(record_hashes):
        members.setdefault(_key(record_hash), []).append(record_hash)

    folds: list[list[str]] = [[] for _ in range(k)]
    for group_key in sorted(members):
        digest = hashlib.sha256(f"{group_key}|{seed}".encode()).hexdigest()
        folds[int(digest[:16], 16) % k].extend(members[group_key])
    for fold in folds:
        fold.sort()  # canonical order within each fold, independent of group order
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
    hpo_study: HPOStudy | None = None,
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

    Hyper-parameters come from (in priority order) an explicit ``lora_config``,
    else the best config of a Prompt 22 ``hpo_study`` (:func:`optimize_hyperparameters`),
    else the defaults. When an ``hpo_study`` is supplied its identity + best
    trial are recorded in the manifest, so the run is traceable back to the search
    that produced its hyper-parameters.
    """

    if k_folds < 2:
        raise FineTuneError("k_folds must be >= 2 for cross-validation")

    # Hard rule re-assert: refuse to train if the snapshot touches the holdout.
    if splits is not None:
        assert_training_excludes_holdout(snapshot.record_hashes, splits)

    if lora_config is not None:
        cfg = lora_config
    elif hpo_study is not None:  # the best config the Bayesian HPO selected
        cfg = hpo_study.best_config
    else:
        cfg = LoRAConfig()
    if target_modules is not None:
        cfg = replace(cfg, target_modules=tuple(target_modules))
    if not (8 <= cfg.r <= 16):  # low-rank discipline (spec: r = 8-16)
        raise FineTuneError(f"LoRA rank r must be in [8, 16]; got {cfg.r}")

    trainer = trainer or _ModalLoRATrainer()
    resolved_git_sha = git_sha if git_sha is not None else current_git_sha()

    # Leak-proof CV: when the snapshot carries grouping, need >= k whole groups.
    if snapshot.record_groups is not None and snapshot.n_groups < k_folds:
        raise FineTuneError(
            f"leak-proof CV needs >= k_folds ({k_folds}) molecule groups; "
            f"snapshot has {snapshot.n_groups}"
        )
    folds = _assign_folds(snapshot.record_hashes, k_folds, seed, groups=snapshot.record_groups)
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
        "cv": {
            "strategy": "group_kfold" if snapshot.record_groups is not None else "kfold",
            "group_key": "molecule_skeleton",
            "n_groups": (
                snapshot.n_groups if snapshot.record_groups is not None else snapshot.row_count
            ),
        },
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
        "hpo": (
            {
                "study_id": hpo_study.study_id,
                "sampler": hpo_study.sampler,
                "n_trials": hpo_study.n_trials,
                "objective": hpo_study.objective,
                "best_params": dict(hpo_study.best_params),
                "best_value": hpo_study.best_value,
            }
            if hpo_study is not None
            else None
        ),
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
    max_ece: float | None = None,
    calibration_head: CalibrationHead | None = None,
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
      regression, strict gain on >=1 metric, zero safety-critical regression)
      **and** passes the absolute calibration gate,
    * **never** auto-promotes to ``production`` (human sign-off required).

    **Calibration is a first-class acceptance gate (Prompt 22).** If ``max_ece``
    is given, an adapter whose gold-set Expected Calibration Error exceeds it is
    **not promotable even if it dominates on accuracy** — a model that is "more
    accurate" but lies about its confidence is never shadowed. When a
    ``calibration_head`` (:func:`fit_temperature_scaling` / :func:`fit_platt_scaling`)
    is supplied, the candidate's per-record confidences are calibrated through it
    *before* the gold-set ECE is measured, so the gate sees the calibrated model.

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

    # Calibration head (if any) rewrites the per-record confidence so the gold-set
    # ECE below reflects the *calibrated* model — calibration is gated, not cosmetic.
    bundle = candidate_bundle if calibration_head is None else CalibratedBundle(
        candidate_bundle, calibration_head
    )
    candidate = evaluate(bundle, gold_set, k=k)
    incumbent = _resolve_incumbent(
        registry,
        nucleus=run.nucleus,
        incumbent_metrics=incumbent_metrics,
        incumbent_bundle=incumbent_bundle,
        gold_set=gold_set,
        k=k,
    )
    dominated = True if incumbent is None else dominates(candidate, incumbent, tolerances)[0]
    # Absolute calibration gate: miscalibrated => not promotable, regardless of accuracy.
    ece_gate_passed = max_ece is None or candidate.ece <= max_ece
    passed = dominated and ece_gate_passed

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
            "dominated_incumbent": dominated,
            "ece": candidate.ece,
            "max_ece": max_ece,
            "ece_gate_passed": ece_gate_passed,
            "calibrated": calibration_head is not None,
            "calibration": calibration_head.as_dict() if calibration_head is not None else None,
            "promotable": passed,
        },
    )

    if passed:  # shadow only — never production (human sign-off gate)
        registry.set_status(
            entry.model_id,
            ModelStatus.SHADOW,
            reason=(
                "passed Prompt 17 dominance + calibration gates; "
                "shadow pending human production sign-off"
            ),
        )

    return entry.model_id


# --------------------------------------------------------------------------- #
# Bayesian hyper-parameter optimization (Prompt 22, Optuna)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HPOSearchSpace:
    """The bounded search space for the five LoRA knobs the HPO tunes.

    Ranges are deliberately conservative: ``r`` stays inside the [8, 16] low-rank
    discipline :func:`finetune_lora` enforces, and the rest cover the usual LoRA
    operating band. Override per base model / dataset.
    """

    r: tuple[int, int] = (8, 16)
    alpha: tuple[int, int] = (8, 64)
    dropout: tuple[float, float] = (0.0, 0.2)
    learning_rate: tuple[float, float] = (1e-5, 1e-3)  # sampled log-uniform
    epochs: tuple[int, int] = (1, 5)

    def as_dict(self) -> dict[str, Any]:
        return {
            "r": list(self.r),
            "alpha": list(self.alpha),
            "dropout": list(self.dropout),
            "learning_rate": list(self.learning_rate),
            "epochs": list(self.epochs),
        }


def default_hpo_search_space() -> HPOSearchSpace:
    """The default LoRA HPO search space (see :class:`HPOSearchSpace`)."""

    return HPOSearchSpace()


@dataclass(frozen=True)
class HPOTrial:
    """One evaluated HPO trial: the sampled params and the objective value."""

    number: int
    params: dict[str, Any]
    value: float
    state: str = "complete"

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "params": dict(self.params),
            "value": self.value,
            "state": self.state,
        }


@runtime_checkable
class HPOSampler(Protocol):
    """The optimizer seam. The default is Optuna TPE; inject your own for tests.

    ``optimize`` proposes up to ``n_trials`` parameter dicts (drawn from
    ``search_space``), calls ``objective`` on each (lower is better), and returns
    the evaluated :class:`HPOTrial` records in trial order.
    """

    def optimize(
        self,
        objective: Callable[[Mapping[str, Any]], float],
        *,
        search_space: HPOSearchSpace,
        n_trials: int,
        seed: int,
    ) -> list[HPOTrial]: ...


class _OptunaSampler:
    """Default HPO sampler: Optuna Bayesian optimization with a seeded TPE sampler.

    ``optuna`` is imported lazily (mirroring :class:`_ModalLoRATrainer`); when it
    is absent this raises :class:`FineTuneUnavailable` rather than silently falling
    back to a grid — the Prompt 22 mandate is Bayesian search, not a sweep. Seeding
    ``TPESampler`` makes the study reproducible.
    """

    name = "optuna-tpe"

    def _require(self) -> Any:
        if importlib.util.find_spec("optuna") is None:
            raise FineTuneUnavailable(
                "Bayesian HPO requires optuna (missing). Install the training extra, "
                "or inject an HPOSampler. See the Roadmap Phase 4 runbook."
            )
        import optuna

        return optuna

    def optimize(
        self,
        objective: Callable[[Mapping[str, Any]], float],
        *,
        search_space: HPOSearchSpace,
        n_trials: int,
        seed: int,
    ) -> list[HPOTrial]:
        optuna = self._require()
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study = optuna.create_study(
            direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed)
        )

        def _optuna_objective(trial: Any) -> float:
            params = {
                "r": trial.suggest_int("r", *search_space.r),
                "alpha": trial.suggest_int("alpha", *search_space.alpha),
                "dropout": trial.suggest_float("dropout", *search_space.dropout),
                "learning_rate": trial.suggest_float(
                    "learning_rate", *search_space.learning_rate, log=True
                ),
                "epochs": trial.suggest_int("epochs", *search_space.epochs),
            }
            return objective(params)

        study.optimize(_optuna_objective, n_trials=n_trials)
        return [
            HPOTrial(
                number=int(t.number),
                params=dict(t.params),
                value=float(t.value),
                state=str(t.state.name).lower(),
            )
            for t in study.trials
            if t.value is not None
        ]


@dataclass(frozen=True)
class HPOStudy:
    """The reproducible record of one Bayesian HPO study (Prompt 22).

    Carries every trial, the best config, the sampler + seed + search space, and a
    content-addressed ``study_id`` so the search that produced
    :func:`finetune_lora`'s hyper-parameters is auditable and re-runnable.
    """

    study_name: str
    base_model_id: str
    snapshot_hash: str
    nucleus: str | None
    sampler: str
    direction: str
    objective: str
    seed: int
    n_trials: int
    trials: tuple[HPOTrial, ...]
    best_trial: HPOTrial
    best_params: dict[str, Any]
    best_config: LoRAConfig
    best_value: float
    search_space: dict[str, Any]
    git_sha: str
    created_utc: str
    manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def study_id(self) -> str:
        """Deterministic content address of the study (excludes wall-clock time)."""

        return content_hash(self.manifest)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.manifest)


def _config_from_params(params: Mapping[str, Any], target_modules: tuple[str, ...]) -> LoRAConfig:
    """Build a LoRAConfig from a sampled params dict (rank clamped to [8, 16])."""

    r = min(16, max(8, int(params["r"])))  # respect the low-rank discipline
    return LoRAConfig(
        r=r,
        alpha=int(params["alpha"]),
        dropout=float(params["dropout"]),
        learning_rate=float(params["learning_rate"]),
        epochs=int(params["epochs"]),
        target_modules=target_modules,
    )


def _cv_fold_aggregate(
    trainer: FoldTrainer,
    folds: Sequence[Sequence[str]],
    *,
    base_model_id: str,
    lora_config: LoRAConfig,
    snapshot: Snapshot,
) -> dict[str, float]:
    """Run K-fold CV for one config and return the aggregate metrics (mean ± std)."""

    k = len(folds)
    results: list[FoldResult] = []
    for i in range(k):
        eval_hashes = tuple(folds[i])
        train_hashes = tuple(h for j, fold in enumerate(folds) if j != i for h in fold)
        results.append(
            trainer.train_and_eval(
                fold=i,
                train_hashes=train_hashes,
                eval_hashes=eval_hashes,
                base_model_id=base_model_id,
                lora_config=lora_config,
                snapshot=snapshot,
            )
        )
    mae_1h_mean, mae_1h_std = _mean_std([r.mae_1h for r in results])
    mae_13c_mean, mae_13c_std = _mean_std([r.mae_13c for r in results])
    cal_mean, cal_std = _mean_std([r.calibration for r in results])
    cov_mean, cov_std = _mean_std([r.coverage for r in results])
    return {
        "mae_1h_mean": mae_1h_mean,
        "mae_1h_std": mae_1h_std,
        "mae_13c_mean": mae_13c_mean,
        "mae_13c_std": mae_13c_std,
        "calibration_mean": cal_mean,
        "calibration_std": cal_std,
        "coverage_mean": cov_mean,
        "coverage_std": cov_std,
    }


def optimize_hyperparameters(
    snapshot: Snapshot,
    base_model_id: str,
    *,
    trainer: FoldTrainer | None = None,
    k_folds: int = 5,
    n_trials: int = 10,
    search_space: HPOSearchSpace | None = None,
    sampler: HPOSampler | None = None,
    tracker: ExperimentTracker | None = None,
    target_modules: Sequence[str] | None = None,
    splits: Splits | None = None,
    nucleus: str | None = None,
    seed: int = 0,
    study_name: str = "lora-hpo",
    git_sha: str | None = None,
    created_utc: str | None = None,
) -> HPOStudy:
    """Bayesian-optimize the LoRA hyper-parameters; return a reproducible study.

    Replaces grid search with **Optuna Bayesian HPO** (default) over rank, alpha,
    dropout, learning-rate, and epochs, budgeted to ``n_trials`` (~10, not a
    sweep). Each trial trains a ``k_folds`` K-fold CV with the injected ``trainer``
    and is scored by a mean-CV-error + calibration objective (lower is better).
    **Every trial is logged to the Prompt 19 tracker** when one is given, and the
    full study (all trials, best config, sampler, seed, search space) is returned
    as a content-addressed :class:`HPOStudy` so it is reproducible. The best config
    is what :func:`finetune_lora` then trains and registers.

    The same hard rules as :func:`finetune_lora` hold: K-fold CV, and — when
    ``splits`` is given — the holdout exclusion is re-asserted before any trial.
    """

    if k_folds < 2:
        raise FineTuneError("k_folds must be >= 2 for cross-validation")
    if n_trials < 1:
        raise FineTuneError("n_trials must be >= 1")
    if splits is not None:  # hard rule 1: never search against the holdout
        assert_training_excludes_holdout(snapshot.record_hashes, splits)

    space = search_space or default_hpo_search_space()
    sampler = sampler or _OptunaSampler()
    trainer = trainer or _ModalLoRATrainer()
    resolved_git_sha = git_sha if git_sha is not None else current_git_sha()
    modules = tuple(target_modules) if target_modules is not None else DEFAULT_LORA_TARGET_MODULES
    # Leak-proof CV: when the snapshot carries grouping, need >= k whole groups.
    if snapshot.record_groups is not None and snapshot.n_groups < k_folds:
        raise FineTuneError(
            f"leak-proof CV needs >= k_folds ({k_folds}) molecule groups; "
            f"snapshot has {snapshot.n_groups}"
        )
    folds = _assign_folds(snapshot.record_hashes, k_folds, seed, groups=snapshot.record_groups)
    sampler_name = getattr(sampler, "name", sampler.__class__.__name__)
    objective_desc = "mean_cv_mae_plus_calibration"

    counter = {"n": 0}

    def _objective(params: Mapping[str, Any]) -> float:
        cfg = _config_from_params(params, modules)
        agg = _cv_fold_aggregate(
            trainer, folds, base_model_id=base_model_id, lora_config=cfg, snapshot=snapshot
        )
        score = 0.5 * (agg["mae_1h_mean"] + agg["mae_13c_mean"]) + agg["calibration_mean"]
        idx = counter["n"]
        counter["n"] += 1
        if tracker is not None:  # Prompt 19: log every trial
            with tracker.start_run(
                run_name=f"{study_name}-trial-{idx}",
                params={**cfg.as_dict(), "k_folds": k_folds, "seed": seed},
                tags={"kind": "lora-hpo", "study": study_name, "base_model_id": base_model_id},
            ) as handle:
                handle.set_dataset_version(snapshot.snapshot_hash)
                handle.log_metrics({**agg, "cv_score": score})
        return score

    trials = sampler.optimize(_objective, search_space=space, n_trials=n_trials, seed=seed)
    if not trials:  # pragma: no cover - a sampler must evaluate at least one trial
        raise FineTuneError("HPO produced no completed trials")

    best = min(trials, key=lambda t: (t.value, t.number))
    best_config = _config_from_params(best.params, modules)

    manifest: dict[str, Any] = {
        "study_name": study_name,
        "base_model_id": base_model_id,
        "snapshot_hash": snapshot.snapshot_hash,
        "nucleus": nucleus,
        "sampler": sampler_name,
        "direction": "minimize",
        "objective": objective_desc,
        "seed": seed,
        "n_trials": len(trials),
        "k_folds": k_folds,
        "cv": {
            "strategy": "group_kfold" if snapshot.record_groups is not None else "kfold",
            "group_key": "molecule_skeleton",
            "n_groups": (
                snapshot.n_groups if snapshot.record_groups is not None else snapshot.row_count
            ),
        },
        "search_space": space.as_dict(),
        "trials": [t.as_dict() for t in trials],
        "best_trial": best.as_dict(),
        "best_params": dict(best.params),
        "best_config": best_config.as_dict(),
        "best_value": best.value,
        "gold_checksum": snapshot.gold_checksum,
        "git_sha": resolved_git_sha,
    }

    return HPOStudy(
        study_name=study_name,
        base_model_id=base_model_id,
        snapshot_hash=snapshot.snapshot_hash,
        nucleus=nucleus,
        sampler=sampler_name,
        direction="minimize",
        objective=objective_desc,
        seed=seed,
        n_trials=len(trials),
        trials=tuple(trials),
        best_trial=best,
        best_params=dict(best.params),
        best_config=best_config,
        best_value=best.value,
        search_space=space.as_dict(),
        git_sha=resolved_git_sha,
        created_utc=created_utc if created_utc is not None else datetime.now(UTC).isoformat(),
        manifest=manifest,
    )


# --------------------------------------------------------------------------- #
# Confidence-calibration head (Prompt 22)
# --------------------------------------------------------------------------- #
_CAL_EPS = 1e-6


def _logit(p: np.ndarray) -> np.ndarray:
    clipped = np.clip(p, _CAL_EPS, 1.0 - _CAL_EPS)
    return np.log(clipped / (1.0 - clipped))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))


def _fit_logistic_regression(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    l2: float = 1.0,
    iters: int = 2000,
    lr: float = 0.5,
) -> tuple[np.ndarray, float]:
    """Deterministic full-batch logistic-regression fit (numpy GD with L2).

    Returns ``(weights, bias)``. No randomness — reproducible by construction.
    """

    x = np.asarray(features, dtype=float)
    y = np.asarray(labels, dtype=float)
    if x.ndim != 2:
        x = x.reshape(len(y), -1)
    n, d = x.shape
    weights = np.zeros(d)
    bias = 0.0
    for _ in range(iters):
        prob = _sigmoid(x @ weights + bias)
        error = prob - y
        weights = weights - lr * (x.T @ error / n + l2 * weights / n)
        bias = bias - lr * float(np.mean(error))
    return weights, bias


@dataclass(frozen=True)
class CalibrationHead:
    """A learned post-hoc confidence calibrator (Prompt 22).

    Maps a raw model confidence ``p`` in [0, 1] to a calibrated confidence so that
    a stated 80% corresponds to ~80% empirical accuracy. Three forms:

    * ``temperature`` — single-parameter temperature scaling on the logit
      (``sigmoid(logit(p) / T)``; Guo et al., ICML 2017);
    * ``platt`` — two-parameter Platt scaling (``sigmoid(a * logit(p) + b)``);
    * ``identity`` — pass-through (no calibration).

    Fit with :func:`fit_temperature_scaling` / :func:`fit_platt_scaling`; validate
    against ECE with :func:`calibration_report`.
    """

    method: str
    temperature: float = 1.0
    a: float = 1.0
    b: float = 0.0

    def calibrate(self, confidences: Sequence[float]) -> list[float]:
        p = np.asarray(list(confidences), dtype=float)
        if p.size == 0:
            return []
        if self.method == "identity":
            out = np.clip(p, 0.0, 1.0)
        elif self.method == "temperature":
            out = _sigmoid(_logit(p) / self.temperature)
        elif self.method == "platt":
            out = _sigmoid(self.a * _logit(p) + self.b)
        else:  # pragma: no cover - guarded by the fit functions
            raise FineTuneError(f"unknown calibration method {self.method!r}")
        return [float(x) for x in np.clip(out, 0.0, 1.0)]

    def tag(self) -> str:
        if self.method == "temperature":
            return f"temperature:T={self.temperature:.4g}"
        if self.method == "platt":
            return f"platt:a={self.a:.4g},b={self.b:.4g}"
        return self.method

    def as_dict(self) -> dict[str, Any]:
        return {"method": self.method, "temperature": self.temperature, "a": self.a, "b": self.b}


@dataclass(frozen=True)
class CalibratedBundle:
    """Wrap a :class:`ModelBundle`, rewriting each prediction's confidence via a head.

    Used by :func:`register_if_eligible` so the gold-set ECE measures the
    *calibrated* model. Everything else about each prediction is untouched.
    """

    inner: ModelBundle
    head: CalibrationHead

    @property
    def model_versions(self) -> Mapping[str, str]:
        return {**dict(self.inner.model_versions), "calibration": self.head.tag()}

    def predict(self, record: Any) -> Any:
        pred = self.inner.predict(record)
        calibrated = self.head.calibrate([pred.confidence])[0]
        return replace(pred, confidence=calibrated)


def fit_temperature_scaling(
    confidences: Sequence[float], correct: Sequence[bool]
) -> CalibrationHead:
    """Fit temperature scaling (minimise NLL of correctness over the temperature).

    A single scalar ``T`` is optimised by bounded scalar minimisation
    (deterministic). ``T > 1`` softens over-confident predictions; ``T < 1``
    sharpens under-confident ones.
    """

    conf = np.asarray(list(confidences), dtype=float)
    corr = np.asarray(list(correct), dtype=float)
    if conf.shape != corr.shape:
        raise FineTuneError("confidences and correct must be the same length")
    if conf.size == 0:
        raise FineTuneError("calibration requires at least one prediction")
    z = _logit(conf)

    def _nll(temp: float) -> float:
        q = np.clip(_sigmoid(z / temp), _CAL_EPS, 1.0 - _CAL_EPS)
        return float(-np.mean(corr * np.log(q) + (1.0 - corr) * np.log(1.0 - q)))

    res = minimize_scalar(_nll, bounds=(0.05, 100.0), method="bounded")
    return CalibrationHead(method="temperature", temperature=float(res.x))


def fit_platt_scaling(confidences: Sequence[float], correct: Sequence[bool]) -> CalibrationHead:
    """Fit two-parameter Platt scaling (logistic regression on the logit of ``p``)."""

    conf = np.asarray(list(confidences), dtype=float)
    corr = np.asarray(list(correct), dtype=float)
    if conf.shape != corr.shape:
        raise FineTuneError("confidences and correct must be the same length")
    if conf.size == 0:
        raise FineTuneError("calibration requires at least one prediction")
    z = _logit(conf).reshape(-1, 1)
    weights, bias = _fit_logistic_regression(z, corr, l2=1e-3)
    return CalibrationHead(method="platt", a=float(weights[0]), b=float(bias))


def calibration_report(
    head: CalibrationHead,
    confidences: Sequence[float],
    correct: Sequence[bool],
    *,
    n_bins: int = 10,
) -> dict[str, Any]:
    """ECE before vs after applying ``head`` — the calibration acceptance evidence."""

    corr = [bool(c) for c in correct]
    before = expected_calibration_error(list(confidences), corr, n_bins=n_bins)
    after = expected_calibration_error(head.calibrate(confidences), corr, n_bins=n_bins)
    return {
        "method": head.method,
        "ece_before": float(before),
        "ece_after": float(after),
        "n": len(corr),
        "head": head.as_dict(),
    }


# --------------------------------------------------------------------------- #
# Contradiction detection (Prompt 22) — complements the Prompt 7 verifier
# --------------------------------------------------------------------------- #
# First-order multiplicity -> implied number of coupling partners (the n+1 rule).
_MULTIPLICITY_NEIGHBORS: dict[str, int] = {
    "s": 0,
    "singlet": 0,
    "d": 1,
    "doublet": 1,
    "t": 2,
    "triplet": 2,
    "q": 3,
    "quartet": 3,
    "p": 4,
    "quint": 4,
    "quintet": 4,
    "pentet": 4,
    "sext": 5,
    "sextet": 5,
    "sept": 6,
    "septet": 6,
    "heptet": 6,
}


@dataclass(frozen=True)
class IntraSpectralEvidence:
    """Within-one-spectrum observables used to flag internal inconsistencies."""

    proton_integration_sum: float | None = None
    expected_proton_count: int | None = None
    multiplicity: str | None = None
    n_coupling_neighbors: int | None = None
    shift_ppm: float | None = None
    nucleus: str | None = None
    shift_window: tuple[float, float] | None = None

    def features(self) -> dict[str, float]:
        """A numeric feature vector for the learned contradiction model."""

        feats: dict[str, float] = {}
        if self.proton_integration_sum is not None and self.expected_proton_count is not None:
            denom = max(abs(float(self.expected_proton_count)), 1.0)
            abs_err = abs(float(self.proton_integration_sum) - float(self.expected_proton_count))
            feats["integration_abs_error"] = abs_err
            feats["integration_rel_error"] = abs_err / denom
        if self.multiplicity is not None and self.n_coupling_neighbors is not None:
            implied = _MULTIPLICITY_NEIGHBORS.get(self.multiplicity.strip().lower())
            if implied is not None:
                feats["multiplicity_neighbor_mismatch"] = float(
                    abs(implied - int(self.n_coupling_neighbors))
                )
        if self.shift_ppm is not None and self.shift_window is not None:
            lo, hi = self.shift_window
            below = max(0.0, float(lo) - float(self.shift_ppm))
            above = max(0.0, float(self.shift_ppm) - float(hi))
            feats["shift_window_excess"] = below + above
        return feats


@dataclass(frozen=True)
class CrossModalEvidence:
    """Cross-modality agreement (NMR vs MS vs RT — Prompt 21)."""

    nmr_top_id: str | None = None
    ms_top_id: str | None = None
    rt_corroborated: bool | None = None
    notes: str = ""

    def features(self) -> dict[str, float]:
        feats: dict[str, float] = {}
        if self.nmr_top_id is not None and self.ms_top_id is not None:
            feats["nmr_ms_disagree"] = 0.0 if self.nmr_top_id == self.ms_top_id else 1.0
        if self.rt_corroborated is not None:
            feats["rt_disagree"] = 0.0 if self.rt_corroborated else 1.0
        return feats


@dataclass(frozen=True)
class ContradictionSignal:
    """One flagged inconsistency: what kind, how severe (0..1), and why."""

    kind: str
    severity: float
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "severity": self.severity, "detail": self.detail}


@dataclass(frozen=True)
class ContradictionReport:
    """The contradiction signals for one record + the reviewer/active-learning view."""

    record_hash: str | None
    signals: tuple[ContradictionSignal, ...]
    contradiction_threshold: float = 0.5

    @property
    def max_severity(self) -> float:
        return max((s.severity for s in self.signals), default=0.0)

    @property
    def is_contradiction(self) -> bool:
        return self.max_severity >= self.contradiction_threshold

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(s.kind for s in self.signals)

    def to_reviewer_dict(self) -> dict[str, Any]:
        """A compact, human-facing summary to surface to the reviewer."""

        return {
            "record_hash": self.record_hash,
            "is_contradiction": self.is_contradiction,
            "max_severity": self.max_severity,
            "signals": [s.as_dict() for s in self.signals],
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_hash": self.record_hash,
            "contradiction_threshold": self.contradiction_threshold,
            "is_contradiction": self.is_contradiction,
            "max_severity": self.max_severity,
            "signals": [s.as_dict() for s in self.signals],
        }


@dataclass(frozen=True)
class ActiveLearningItem:
    """A hard case routed to the Prompt 16 active-learning queue."""

    record_hash: str
    reason: str
    severity: float
    kinds: tuple[str, ...]
    created_utc: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_hash": self.record_hash,
            "reason": self.reason,
            "severity": self.severity,
            "kinds": list(self.kinds),
            "created_utc": self.created_utc,
        }


@runtime_checkable
class ActiveLearningQueue(Protocol):
    """The Prompt 16 active-learning sink. Inject your own; default is in-memory."""

    def enqueue(self, item: ActiveLearningItem) -> None: ...


class InMemoryActiveLearningQueue:
    """A simple de-duplicating queue (keeps the highest-severity item per record)."""

    def __init__(self) -> None:
        self._items: dict[str, ActiveLearningItem] = {}

    def enqueue(self, item: ActiveLearningItem) -> None:
        current = self._items.get(item.record_hash)
        if current is None or item.severity > current.severity:
            self._items[item.record_hash] = item

    @property
    def items(self) -> list[ActiveLearningItem]:
        return sorted(self._items.values(), key=lambda it: (-it.severity, it.record_hash))


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def detect_contradictions(
    *,
    record_hash: str | None = None,
    verification_results: Sequence[VerificationResult] | None = None,
    cross_modal: CrossModalEvidence | None = None,
    intra_spectral: IntraSpectralEvidence | None = None,
    model: ContradictionModel | None = None,
    queue: ActiveLearningQueue | None = None,
    contradiction_threshold: float = 0.5,
    integration_tolerance: float = 0.5,
    created_utc: str | None = None,
) -> ContradictionReport:
    """Flag internal spectral inconsistencies — complementing the Prompt 7 verifier.

    Deterministic rules surface (a) **no single structure explains the data** (no
    Prompt 7 verdict is ``consistent``), (b) **cross-modal disagreement** (NMR vs
    MS top candidate, or RT not corroborated — Prompt 21), and (c) **intra-spectral**
    impossibilities (integration vs proton count, multiplicity vs coupling
    neighbors, shift outside its plausible window). An optional trained
    :class:`ContradictionModel` adds a learned signal. This does **not** replace
    the deterministic verifier; it complements it, surfaces contradictions to the
    reviewer (:meth:`ContradictionReport.to_reviewer_dict`), and feeds hard cases
    to the Prompt 16 active-learning ``queue``.
    """

    signals: list[ContradictionSignal] = []

    # (a) No single structure explains the spectra (Prompt 7 verdicts).
    if verification_results:
        verdicts = [vr.verdict for vr in verification_results]
        if verdicts and not any(v == "consistent" for v in verdicts):
            n_incon = sum(1 for v in verdicts if v == "inconsistent")
            severity = _clip01(0.6 + 0.4 * (n_incon / len(verdicts)))
            signals.append(
                ContradictionSignal(
                    kind="no_consistent_structure",
                    severity=severity,
                    detail=(
                        f"{len(verdicts)} candidate structure(s) evaluated; none consistent "
                        f"({n_incon} inconsistent). No single structure explains the data."
                    ),
                )
            )

    # (b) Cross-modal disagreement (NMR vs MS vs RT, Prompt 21).
    if cross_modal is not None:
        if (
            cross_modal.nmr_top_id is not None
            and cross_modal.ms_top_id is not None
            and cross_modal.nmr_top_id != cross_modal.ms_top_id
        ):
            signals.append(
                ContradictionSignal(
                    kind="nmr_ms_disagreement",
                    severity=0.8,
                    detail=(
                        f"NMR best candidate {cross_modal.nmr_top_id!r} != "
                        f"MS best candidate {cross_modal.ms_top_id!r}."
                    ),
                )
            )
        if cross_modal.rt_corroborated is False:
            signals.append(
                ContradictionSignal(
                    kind="rt_disagreement",
                    severity=0.6,
                    detail="Retention time does not corroborate the proposed structure.",
                )
            )

    # (c) Intra-spectral impossibilities.
    if intra_spectral is not None:
        ev = intra_spectral
        if ev.proton_integration_sum is not None and ev.expected_proton_count is not None:
            denom = max(abs(float(ev.expected_proton_count)), 1.0)
            rel = abs(float(ev.proton_integration_sum) - float(ev.expected_proton_count)) / denom
            if rel > integration_tolerance:
                signals.append(
                    ContradictionSignal(
                        kind="integration_mismatch",
                        severity=_clip01(rel),
                        detail=(
                            f"Integration sum {ev.proton_integration_sum} vs expected "
                            f"{ev.expected_proton_count} H (rel. error {rel:.2f})."
                        ),
                    )
                )
        if ev.multiplicity is not None and ev.n_coupling_neighbors is not None:
            implied = _MULTIPLICITY_NEIGHBORS.get(ev.multiplicity.strip().lower())
            if implied is not None and implied != int(ev.n_coupling_neighbors):
                signals.append(
                    ContradictionSignal(
                        kind="multiplicity_mismatch",
                        severity=_clip01(0.5 + 0.1 * abs(implied - int(ev.n_coupling_neighbors))),
                        detail=(
                            f"Multiplicity {ev.multiplicity!r} implies {implied} coupling "
                            f"neighbor(s) but {ev.n_coupling_neighbors} are present."
                        ),
                    )
                )
        if ev.shift_ppm is not None and ev.shift_window is not None:
            lo, hi = ev.shift_window
            if float(ev.shift_ppm) < float(lo) or float(ev.shift_ppm) > float(hi):
                excess = max(float(lo) - float(ev.shift_ppm), float(ev.shift_ppm) - float(hi))
                span = max(float(hi) - float(lo), 1e-6)
                signals.append(
                    ContradictionSignal(
                        kind="shift_out_of_range",
                        severity=_clip01(0.5 + 0.5 * (excess / span)),
                        detail=(
                            f"Shift {ev.shift_ppm} ppm outside the plausible window "
                            f"[{lo}, {hi}] for {ev.nucleus or 'this nucleus'}."
                        ),
                    )
                )

    # (d) Learned signal from the trained contradiction model (optional).
    if model is not None:
        feats: dict[str, float] = {}
        if intra_spectral is not None:
            feats.update(intra_spectral.features())
        if cross_modal is not None:
            feats.update(cross_modal.features())
        if feats:
            prob = model.predict_proba(feats)
            if prob >= contradiction_threshold:
                signals.append(
                    ContradictionSignal(
                        kind="learned_contradiction",
                        severity=_clip01(prob),
                        detail=f"Trained contradiction model probability {prob:.2f}.",
                    )
                )

    signals.sort(key=lambda s: (-s.severity, s.kind))
    report = ContradictionReport(
        record_hash=record_hash,
        signals=tuple(signals),
        contradiction_threshold=contradiction_threshold,
    )

    if queue is not None and report.is_contradiction and record_hash is not None:
        queue.enqueue(
            ActiveLearningItem(
                record_hash=record_hash,
                reason=report.signals[0].kind,
                severity=report.max_severity,
                kinds=report.kinds,
                created_utc=(
                    created_utc if created_utc is not None else datetime.now(UTC).isoformat()
                ),
            )
        )

    return report


@runtime_checkable
class ContradictionExample(Protocol):
    """A labeled training example for the contradiction model.

    ``features`` is a ``{name: value}`` map (e.g. from
    :meth:`IntraSpectralEvidence.features` merged with
    :meth:`CrossModalEvidence.features`); ``label`` is ``True`` iff the case is a
    genuine internal contradiction; ``record_hash`` is its dataset identity (used
    for fold assignment + holdout exclusion).
    """

    record_hash: str
    label: bool
    features: Mapping[str, float]


def _standardizer(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-feature mean + scale (std with a floor) for standardization."""

    means = x.mean(axis=0)
    scales = x.std(axis=0)
    scales = np.where(scales < 1e-8, 1.0, scales)
    return means, scales


def _feature_matrix(
    by_hash: Mapping[str, ContradictionExample],
    hashes: Sequence[str],
    names: Sequence[str],
) -> np.ndarray:
    return np.array([[float(by_hash[h].features.get(n, 0.0)) for n in names] for h in hashes])


def _label_vector(by_hash: Mapping[str, ContradictionExample], hashes: Sequence[str]) -> np.ndarray:
    return np.array([1.0 if by_hash[h].label else 0.0 for h in hashes])


@dataclass(frozen=True)
class ContradictionModel:
    """A calibrated logistic contradiction classifier (Prompt 22).

    Operates on a fixed, sorted ``feature_names`` vector (standardized internally);
    :meth:`predict_proba` returns a temperature-calibrated probability that the
    case is internally contradictory.
    """

    feature_names: tuple[str, ...]
    weights: tuple[float, ...]
    bias: float
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    calibration: CalibrationHead
    threshold: float = 0.5

    def _vector(self, features: Mapping[str, float]) -> np.ndarray:
        raw = np.array([float(features.get(name, 0.0)) for name in self.feature_names])
        return (raw - np.array(self.feature_means)) / np.array(self.feature_scales)

    def predict_proba(self, features: Mapping[str, float]) -> float:
        if not self.feature_names:
            return 0.0
        z = float(self._vector(features) @ np.array(self.weights) + self.bias)
        raw = float(_sigmoid(np.array([z]))[0])
        return float(self.calibration.calibrate([raw])[0])

    def flag(self, features: Mapping[str, float], *, threshold: float | None = None) -> bool:
        gate = self.threshold if threshold is None else threshold
        return self.predict_proba(features) >= gate

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_names": list(self.feature_names),
            "weights": list(self.weights),
            "bias": self.bias,
            "feature_means": list(self.feature_means),
            "feature_scales": list(self.feature_scales),
            "calibration": self.calibration.as_dict(),
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class ContradictionFoldMetrics:
    """One CV fold's classification metrics for the contradiction model."""

    fold: int
    n_train: int
    n_eval: int
    precision: float
    recall: float
    f1: float
    ece: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "fold": self.fold,
            "n_train": self.n_train,
            "n_eval": self.n_eval,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "ece": self.ece,
        }


@dataclass(frozen=True)
class ContradictionModelRun:
    """The reproducible record of training the contradiction model (Prompt 22)."""

    snapshot_hash: str
    feature_names: tuple[str, ...]
    k_folds: int
    seed: int
    row_count: int
    n_positive: int
    fold_metrics: tuple[ContradictionFoldMetrics, ...]
    precision_mean: float
    recall_mean: float
    f1_mean: float
    f1_std: float
    ece_oof: float
    ece_calibrated: float
    max_ece: float
    calibration_passed: bool
    model: ContradictionModel
    gold_checksum: str | None
    git_sha: str
    created_utc: str
    manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def run_id(self) -> str:
        """Deterministic content address of the full training manifest."""

        return content_hash(self.manifest)


def train_contradiction_detector(
    examples: Sequence[ContradictionExample],
    *,
    feature_names: Sequence[str] | None = None,
    k_folds: int = 5,
    seed: int = 0,
    l2: float = 1.0,
    iters: int = 2000,
    lr: float = 0.5,
    threshold: float = 0.5,
    max_ece: float = 0.1,
    snapshot: Snapshot | None = None,
    splits: Splits | None = None,
    holdout_exclusion_hashes: Iterable[str] | None = None,
    gold_checksum: str | None = None,
    git_sha: str | None = None,
    created_utc: str | None = None,
) -> ContradictionModelRun:
    """Train the contradiction classifier with K-fold CV, calibration, and lineage.

    A calibrated logistic model over the contradiction features, trained under the
    same Prompt 15 hard rules: **K-fold CV** (k=5) for honest metrics, **gold/holdout
    hash-exclusion** (the model never trains on the frozen holdout), and **full
    lineage** (feature set, per-fold precision/recall/F1/ECE, code git SHA, dataset
    hash). Out-of-fold predictions are temperature-calibrated and the calibrated
    ECE is an acceptance gate (``max_ece``): a contradiction model that lies about
    its confidence is not acceptable.
    """

    if k_folds < 2:
        raise FineTuneError("k_folds must be >= 2 for cross-validation")

    # Hard rule 1: exclude the holdout by record hash.
    exclusion: set[str] = set()
    if splits is not None:
        exclusion |= set(splits.holdout_exclusion_hashes)
    if holdout_exclusion_hashes is not None:
        exclusion |= set(holdout_exclusion_hashes)
    retained = [ex for ex in examples if ex.record_hash not in exclusion]
    if splits is not None:
        assert_training_excludes_holdout([ex.record_hash for ex in retained], splits)
    if len(retained) < k_folds:
        raise FineTuneError(
            f"need >= k_folds ({k_folds}) examples after holdout exclusion; got {len(retained)}"
        )

    if feature_names is not None:
        names = tuple(feature_names)
    else:
        keys: set[str] = set()
        for ex in retained:
            keys |= set(ex.features.keys())
        names = tuple(sorted(keys))
    if not names:
        raise FineTuneError("contradiction examples expose no features")

    record_hashes = [ex.record_hash for ex in retained]
    by_hash = {ex.record_hash: ex for ex in retained}
    x_all = _feature_matrix(by_hash, record_hashes, names)
    y_all = _label_vector(by_hash, record_hashes)

    # Leak-proof CV: group co-molecule/co-batch contradiction examples into one fold.
    cd_group_map = {ex.record_hash: (_group_of(ex) or ex.record_hash) for ex in retained}
    cd_grouped = any(group != rh for rh, group in cd_group_map.items())
    cd_n_groups = len(set(cd_group_map.values()))
    if cd_grouped and cd_n_groups < k_folds:
        raise FineTuneError(
            f"leak-proof CV needs >= k_folds ({k_folds}) molecule groups; got {cd_n_groups}"
        )
    folds = _assign_folds(
        record_hashes, k_folds, seed, groups=cd_group_map if cd_grouped else None
    )
    fold_metrics: list[ContradictionFoldMetrics] = []
    oof_conf: list[float] = []
    oof_correct: list[bool] = []
    for i, fold in enumerate(folds):
        eval_hashes = list(fold)
        train_hashes = [h for j, f in enumerate(folds) if j != i for h in f]
        if not eval_hashes or not train_hashes:
            continue
        x_tr = _feature_matrix(by_hash, train_hashes, names)
        y_tr = _label_vector(by_hash, train_hashes)
        means, scales = _standardizer(x_tr)
        w, b = _fit_logistic_regression((x_tr - means) / scales, y_tr, l2=l2, iters=iters, lr=lr)
        x_ev = _feature_matrix(by_hash, eval_hashes, names)
        y_ev = _label_vector(by_hash, eval_hashes)
        prob = _sigmoid(((x_ev - means) / scales) @ w + b)
        pred = (prob >= 0.5).astype(float)
        tp = int(np.sum((pred == 1) & (y_ev == 1)))
        fp = int(np.sum((pred == 1) & (y_ev == 0)))
        fn = int(np.sum((pred == 0) & (y_ev == 1)))
        prf = f1_score(tp, fp, fn)
        conf = np.where(pred == 1, prob, 1.0 - prob)  # predicted-class confidence
        correct = pred == y_ev
        for c, ok in zip(conf, correct, strict=True):
            oof_conf.append(float(c))
            oof_correct.append(bool(ok))
        ece = float(
            expected_calibration_error([float(c) for c in conf], [bool(o) for o in correct])
        )
        fold_metrics.append(
            ContradictionFoldMetrics(
                fold=i,
                n_train=len(train_hashes),
                n_eval=len(eval_hashes),
                precision=prf.precision,
                recall=prf.recall,
                f1=prf.f1,
                ece=ece,
            )
        )

    # Calibrate on pooled out-of-fold predictions; the calibrated ECE is the gate.
    head = fit_temperature_scaling(oof_conf, oof_correct)
    ece_oof = float(expected_calibration_error(oof_conf, oof_correct))
    ece_calibrated = float(expected_calibration_error(head.calibrate(oof_conf), oof_correct))

    # Final model: fit on all retained data, standardized.
    means_all, scales_all = _standardizer(x_all)
    w_all, b_all = _fit_logistic_regression(
        (x_all - means_all) / scales_all, y_all, l2=l2, iters=iters, lr=lr
    )
    model = ContradictionModel(
        feature_names=names,
        weights=tuple(float(v) for v in w_all),
        bias=float(b_all),
        feature_means=tuple(float(v) for v in means_all),
        feature_scales=tuple(float(v) for v in scales_all),
        calibration=head,
        threshold=threshold,
    )

    precision_mean, _ = _mean_std([f.precision for f in fold_metrics])
    recall_mean, _ = _mean_std([f.recall for f in fold_metrics])
    f1_mean, f1_std = _mean_std([f.f1 for f in fold_metrics])
    calibration_passed = ece_calibrated <= max_ece
    resolved_git_sha = git_sha if git_sha is not None else current_git_sha()
    resolved_snapshot_hash = (
        snapshot.snapshot_hash
        if snapshot is not None
        else content_hash({"record_hashes": sorted(record_hashes), "features": list(names)})
    )
    resolved_gold = gold_checksum
    if resolved_gold is None and snapshot is not None:
        resolved_gold = snapshot.gold_checksum

    manifest: dict[str, Any] = {
        "kind": "contradiction_detector",
        "snapshot_hash": resolved_snapshot_hash,
        "feature_names": list(names),
        "k_folds": k_folds,
        "cv": {
            "strategy": "group_kfold" if cd_grouped else "kfold",
            "group_key": "molecule_skeleton",
            "n_groups": cd_n_groups,
        },
        "seed": seed,
        "row_count": len(retained),
        "n_positive": int(y_all.sum()),
        "hyperparams": {"l2": l2, "iters": iters, "lr": lr, "threshold": threshold},
        "fold_metrics": [f.as_dict() for f in fold_metrics],
        "aggregate": {
            "precision_mean": precision_mean,
            "recall_mean": recall_mean,
            "f1_mean": f1_mean,
            "f1_std": f1_std,
        },
        "ece_oof": ece_oof,
        "ece_calibrated": ece_calibrated,
        "max_ece": max_ece,
        "calibration_passed": calibration_passed,
        "calibration": head.as_dict(),
        "model": model.as_dict(),
        "gold_checksum": resolved_gold,
        "git_sha": resolved_git_sha,
    }

    return ContradictionModelRun(
        snapshot_hash=resolved_snapshot_hash,
        feature_names=names,
        k_folds=k_folds,
        seed=seed,
        row_count=len(retained),
        n_positive=int(y_all.sum()),
        fold_metrics=tuple(fold_metrics),
        precision_mean=precision_mean,
        recall_mean=recall_mean,
        f1_mean=f1_mean,
        f1_std=f1_std,
        ece_oof=ece_oof,
        ece_calibrated=ece_calibrated,
        max_ece=max_ece,
        calibration_passed=calibration_passed,
        model=model,
        gold_checksum=resolved_gold,
        git_sha=resolved_git_sha,
        created_utc=created_utc if created_utc is not None else datetime.now(UTC).isoformat(),
        manifest=manifest,
    )
