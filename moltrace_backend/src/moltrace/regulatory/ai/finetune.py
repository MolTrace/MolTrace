"""LoRA fine-tuning for narrative quality — the regulated math stays frozen (Prompt 15).

Roadmap Layer 3 (Domain Fine-Tuning), narrative ONLY. Improve submission-grade drafting by
fine-tuning the narrative model (or training a reranker) on accumulated, human-APPROVED regulatory
narratives — CTD 3.2 sections, OOS investigation reports, justification texts. The deterministic
math is **never** fine-tuned and never altered.

HARD RULES (zero-tolerance, enforced + guard-tested):
  * NEVER fine-tune anything that produces a number, limit, threshold, or classification — those
    stay in the deterministic engine. :func:`build_snapshot` only admits APPROVED narrative edits
    (Prompt 16 ``ReviewKind.NARRATIVE_EDIT`` with a human-final correction) and refuses any example
    whose decision type is a frozen (deterministic/classification) type; :func:`finetune_narrative`
    re-asserts the snapshot is narrative-only before any training. This module imports none of the
    deterministic engines (M7/CPCA/Q3*/Q6A), so it cannot touch a regulated number.
  * Train only on APPROVED text (never a draft the reviewer rejected without correction).
  * Promotion is gated by a Prompt-17-style evaluation over NARRATIVE metrics — they must improve
    with ZERO regression on citation correctness (the deterministic calc-error / formula-coverage
    hard gates do not apply to a narrative adapter).
  * No confidential data in git or logs — identifiers are masked into the snapshot, and
    :meth:`Snapshot.as_dict` omits the narrative bodies (only hashes + provenance + counts).

The heavy training backend (Modal + torch + peft) is optional and lazy; without it
:class:`FineTuneUnavailable` is raised. The snapshot build, leak-proof K-fold orchestration,
registration, and promotion gate are pure-Python and run offline with an injected trainer — so the
mechanism is testable today and the actual training is deferred until an approved-narrative corpus
exists (3–5 paying customers).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from moltrace.regulatory.ai.active_learning import LabeledExample, ReviewKind, ReviewLog
from moltrace.regulatory.ai.registry import (
    ArtifactKind,
    ArtifactStatus,
    Registry,
    RegistryEntry,
)
from moltrace.regulatory.infra import RegulatoryMetricVector, content_hash

__all__ = [
    "DEFAULT_LORA_TARGET_MODULES",
    "DEFAULT_MODAL_GPU_USD_PER_HOUR",
    "FROZEN_DECISION_TYPES",
    "NARRATIVE_DECISION_TYPES",
    "FineTuneError",
    "FineTuneUnavailable",
    "FinalAdapter",
    "FineTuneRun",
    "FoldMetrics",
    "FoldTrainer",
    "LoRAConfig",
    "NarrativeExample",
    "NarrativeOnlyError",
    "Snapshot",
    "build_snapshot",
    "finetune_narrative",
    "mask_identifiers",
    "narrative_promotion_gate",
    "register_narrative_adapter",
]

DEFAULT_LORA_TARGET_MODULES = ("q_proj", "k_proj", "v_proj", "out_proj")
DEFAULT_MODAL_GPU_USD_PER_HOUR = 2.78
_EPS = 1e-9

#: Narrative decision types the adapter MAY learn from (drafting that benefits from learning).
NARRATIVE_DECISION_TYPES = frozenset(
    {
        "narrative",
        "narrative_edit",
        "ctd_section",
        "ctd_module3_3s3",
        "ctd_module3_3p5",
        "oos_report",
        "oos_investigation",
        "justification",
    }
)
#: Deterministic / classification decision types that must NEVER be fine-tuned (frozen math).
FROZEN_DECISION_TYPES = frozenset(
    {
        "m7_classification",
        "cpca_classification",
        "cpca_cumulative_risk",
        "q3a_thresholds",
        "q3b_thresholds",
        "q3c_residual_solvent_pde",
        "q3d_elemental_assessment",
        "q6a_specification",
    }
)

#: Narrative quality metrics + their direction (a Prompt-17 subset; calc/coverage are NOT here).
_HIGHER_IS_BETTER = frozenset(
    {"narrative_acceptance_rate", "citation_correctness", "needs_review_precision"}
)
_LOWER_IS_BETTER = frozenset({"mean_edit_distance", "hallucination_rate"})


class FineTuneError(RuntimeError):
    """Base class for narrative fine-tuning errors."""


class FineTuneUnavailable(FineTuneError):
    """Raised when the training backend (Modal / torch / peft) is not installed."""


class NarrativeOnlyError(FineTuneError):
    """Raised on any attempt to put a frozen (deterministic/classification) example in training."""


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# --------------------------------------------------------------------------- #
# Identifier masking (no confidential data into the snapshot / logs)
# --------------------------------------------------------------------------- #
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Batch/lot/application identifiers like "B-2026-014", "LOT 12345", "ANDA-211234".
_IDENTIFIER_RE = re.compile(r"\b(?:[A-Z]{1,4}-?\d{2,}(?:-\d+)*|LOT[ -]?\d+)\b")


def mask_identifiers(text: str, *, extra_identifiers: Sequence[str] = ()) -> str:
    """Best-effort redaction of confidential identifiers from narrative text before training.

    Masks any caller-supplied identifier (e.g. patient/site/product/codename), then email addresses
    and batch/lot/application identifiers. Caller identifiers are redacted FIRST so a whole literal
    is removed before the built-in regexes could fragment it and leak a confidential remainder.
    Production use should layer a vetted PII/identifier policy on top; this is the always-on
    baseline so confidential tokens never reach the snapshot or logs.
    """

    masked = text
    for identifier in extra_identifiers:
        if identifier:
            masked = masked.replace(identifier, "[REDACTED]")
    masked = _EMAIL_RE.sub("[EMAIL]", masked)
    masked = _IDENTIFIER_RE.sub("[ID]", masked)
    return masked


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LoRAConfig:
    r: int = 8
    alpha: int = 16
    dropout: float = 0.05
    learning_rate: float = 2e-4
    epochs: int = 3
    target_modules: tuple[str, ...] = DEFAULT_LORA_TARGET_MODULES


@dataclass(frozen=True)
class NarrativeExample:
    """One APPROVED narrative training pair (draft -> human-final), masked + provenance-tagged."""

    train_hash: str
    source_example_id: str  # the Prompt 16 LabeledExample id
    decision_type: str
    draft: str  # the AI draft (masked) — what the model learns FROM
    approved_text: str  # the human-approved narrative (masked) — the label
    citations: tuple[str, ...]
    reviewer_id: str
    approved_utc: str
    group_key: str  # leak-proof CV grouping (a dossier/document never straddles folds)

    def as_dict(self) -> dict[str, Any]:
        return {
            "train_hash": self.train_hash,
            "source_example_id": self.source_example_id,
            "decision_type": self.decision_type,
            "citations": list(self.citations),
            "reviewer_id": self.reviewer_id,
            "approved_utc": self.approved_utc,
            "group_key": self.group_key,
        }


@dataclass(frozen=True)
class Snapshot:
    """An immutable, content-hashed snapshot of approved narratives with approval provenance."""

    snapshot_hash: str
    row_count: int
    examples: tuple[NarrativeExample, ...]
    train_hashes: tuple[str, ...]  # sorted; the training-set identity
    per_decision_type: dict[str, int]
    record_groups: dict[str, str]  # train_hash -> group_key (leak-proof CV)
    n_groups: int
    masked: bool
    provenance: tuple[dict[str, str], ...]  # who approved each example, when
    git_sha: str
    created_utc: str

    def as_dict(self) -> dict[str, Any]:
        # NB: the narrative bodies are intentionally omitted (no confidential text in logs/git).
        return {
            "snapshot_hash": self.snapshot_hash,
            "row_count": self.row_count,
            "train_hashes": list(self.train_hashes),
            "per_decision_type": dict(self.per_decision_type),
            "n_groups": self.n_groups,
            "masked": self.masked,
            "provenance": [dict(p) for p in self.provenance],
            "git_sha": self.git_sha,
            "created_utc": self.created_utc,
        }


@dataclass(frozen=True)
class FoldMetrics:
    """Per-fold narrative-quality metrics (the reviewer-acceptance proxy + drafting fidelity)."""

    fold: int
    n_train: int
    n_eval: int
    reviewer_acceptance_proxy: float  # higher is better
    mean_edit_distance: float  # lower is better — distance from draft to approved final
    citation_correctness: float  # higher is better — must never regress on promotion
    gpu_hours: float


@dataclass(frozen=True)
class FinalAdapter:
    path: str
    sha256: str
    gpu_hours: float


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, var**0.5


@dataclass(frozen=True)
class FineTuneRun:
    """The K-fold CV outcome + final adapter + cost — the registrable run."""

    snapshot_hash: str
    base_model_id: str
    semantic_version: str
    lora_config: LoRAConfig
    k_folds: int
    seed: int
    row_count: int
    fold_metrics: tuple[FoldMetrics, ...]
    acceptance_mean: float
    acceptance_std: float
    edit_distance_mean: float
    edit_distance_std: float
    citation_correctness_mean: float
    citation_correctness_std: float
    gpu_hours: float
    cost_usd: float
    adapter_path: str | None
    adapter_sha256: str | None
    git_sha: str
    created_utc: str
    manifest: dict[str, Any] = field(default_factory=dict)

    def metric_vector(self) -> RegulatoryMetricVector:
        """The narrative metric vector the Prompt-17 promotion gate consumes."""

        return RegulatoryMetricVector(
            narrative_acceptance_rate=self.acceptance_mean,
            mean_edit_distance=self.edit_distance_mean,
            citation_correctness=self.citation_correctness_mean,
            metadata={"snapshot_hash": self.snapshot_hash, "base_model_id": self.base_model_id},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_hash": self.snapshot_hash,
            "base_model_id": self.base_model_id,
            "semantic_version": self.semantic_version,
            "k_folds": self.k_folds,
            "row_count": self.row_count,
            "acceptance_mean": self.acceptance_mean,
            "edit_distance_mean": self.edit_distance_mean,
            "citation_correctness_mean": self.citation_correctness_mean,
            "gpu_hours": self.gpu_hours,
            "cost_usd": self.cost_usd,
            "adapter_sha256": self.adapter_sha256,
            "git_sha": self.git_sha,
            "created_utc": self.created_utc,
        }


# --------------------------------------------------------------------------- #
# Trainer protocol (the heavy backend is injected; default is unavailable)
# --------------------------------------------------------------------------- #
@runtime_checkable
class FoldTrainer(Protocol):
    """Trains the narrative LoRA adapter / reranker. The default needs Modal+torch+peft; inject."""

    def train_and_eval(
        self,
        *,
        fold: int,
        train: Sequence[NarrativeExample],
        eval: Sequence[NarrativeExample],
        base_model_id: str,
        lora_config: LoRAConfig,
    ) -> FoldMetrics: ...

    def fit_final(
        self,
        *,
        train: Sequence[NarrativeExample],
        base_model_id: str,
        lora_config: LoRAConfig,
        out_dir: Path,
    ) -> FinalAdapter: ...


class _UnavailableTrainer:
    """The default trainer — the real LoRA backend (Modal/torch/peft) is not wired up here."""

    def _unavailable(self) -> FineTuneUnavailable:
        return FineTuneUnavailable(
            "narrative LoRA training backend (Modal + torch + peft) is not available; inject a "
            "FoldTrainer. Training is deferred until an approved-narrative corpus exists."
        )

    def train_and_eval(self, **_: Any) -> FoldMetrics:
        raise self._unavailable()

    def fit_final(self, **_: Any) -> FinalAdapter:
        raise self._unavailable()


# --------------------------------------------------------------------------- #
# Leak-proof grouped K-fold (whole dossiers land in one fold)
# --------------------------------------------------------------------------- #
def _assign_folds(
    train_hashes: Sequence[str], k: int, seed: int, *, groups: Mapping[str, str]
) -> list[list[str]]:
    """Partition into k folds by GROUP (seeded hash) so a dossier never straddles train/eval."""

    members: dict[str, list[str]] = {}
    for train_hash in train_hashes:
        members.setdefault(groups.get(train_hash, train_hash), []).append(train_hash)
    folds: list[list[str]] = [[] for _ in range(k)]
    for group_key in sorted(members):
        digest = hashlib.sha256(f"{group_key}|{seed}".encode()).hexdigest()
        folds[int(digest[:16], 16) % k].extend(members[group_key])
    for fold in folds:
        fold.sort()
    return folds


# --------------------------------------------------------------------------- #
# Snapshot build (approved-only, masked, hashed)
# --------------------------------------------------------------------------- #
def _normalize_decision_type(value: str) -> str:
    return str(value).strip().lower()


def _decision_type(example: LabeledExample) -> str:
    return _normalize_decision_type(
        example.context.get("decision_type") or example.inputs.get("decision_type") or "narrative"
    )


def _group_key(example: LabeledExample) -> str:
    for source in (example.context, example.inputs):
        for key in ("dossier", "dossier_id", "document_id", "section"):
            value = source.get(key)
            if value:
                return str(value)
    return example.example_id


def build_snapshot(
    source: ReviewLog | Iterable[LabeledExample],
    *,
    mask: bool = True,
    extra_identifiers: Sequence[str] = (),
    git_sha: str = "unknown",
    created_utc: str | None = None,
) -> Snapshot:
    """Freeze APPROVED narratives into an immutable, hashed snapshot with approval provenance.

    Only Prompt 16 ``NARRATIVE_EDIT`` examples that carry a human-final correction are admitted
    (approved-only). A NARRATIVE_EDIT mislabelled with a frozen (deterministic) decision type is
    rejected with :class:`NarrativeOnlyError` — the math is never trained. Confidential identifiers
    are masked before anything is stored.
    """

    candidates = source.examples() if isinstance(source, ReviewLog) else list(source)
    examples: list[NarrativeExample] = []
    for ex in candidates:
        if ex.review_kind is not ReviewKind.NARRATIVE_EDIT:
            continue  # HARD RULE: classification adjudications / triage overrides never train
        approved = "" if ex.human_final is None else str(ex.human_final)
        if not approved.strip():
            continue  # approved-only: a reject-without-correction has no human-final text
        decision_type = _decision_type(ex)  # normalised (lower/stripped)
        # ALLOWLIST (fail-closed): only an approved NARRATIVE decision type may train — anything
        # else (a frozen deterministic/classification type, an alias, or an unknown label) is
        # refused, so the regulated math can never be fine-tuned even via a non-canonical label.
        if decision_type not in NARRATIVE_DECISION_TYPES:
            frozen = " (a frozen deterministic/classification type)" if (
                decision_type in FROZEN_DECISION_TYPES
            ) else ""
            raise NarrativeOnlyError(
                f"refusing to train on decision type {decision_type!r}{frozen} "
                f"(example {ex.example_id}); only approved NARRATIVE decision types may be "
                f"fine-tuned ({sorted(NARRATIVE_DECISION_TYPES)}) — the math is never fine-tuned"
            )
        draft = "" if ex.ai_output is None else str(ex.ai_output)
        raw_citations = tuple(str(c) for c in (ex.context.get("citations") or ()))
        if mask:
            draft = mask_identifiers(draft, extra_identifiers=extra_identifiers)
            approved = mask_identifiers(approved, extra_identifiers=extra_identifiers)
            citations = tuple(
                mask_identifiers(c, extra_identifiers=extra_identifiers) for c in raw_citations
            )
        else:
            citations = raw_citations
        train_hash = content_hash(
            {
                "decision_type": decision_type,
                "draft": draft,
                "approved_text": approved,
                "citations": list(citations),
            }
        )
        examples.append(
            NarrativeExample(
                train_hash=train_hash,
                source_example_id=ex.example_id,
                decision_type=decision_type,
                draft=draft,
                approved_text=approved,
                citations=citations,
                reviewer_id=ex.reviewer_id,
                approved_utc=ex.created_utc,
                group_key=_group_key(ex),
            )
        )

    # de-duplicate by train_hash (idempotent), then canonicalise ordering by hash
    unique: dict[str, NarrativeExample] = {}
    for example in examples:
        unique.setdefault(example.train_hash, example)
    ordered = tuple(sorted(unique.values(), key=lambda e: e.train_hash))

    train_hashes = tuple(e.train_hash for e in ordered)
    record_groups = {e.train_hash: e.group_key for e in ordered}
    per_decision_type: dict[str, int] = {}
    for e in ordered:
        per_decision_type[e.decision_type] = per_decision_type.get(e.decision_type, 0) + 1
    snapshot_hash = content_hash(
        {"train_hashes": list(train_hashes), "per_decision_type": per_decision_type}
    )
    provenance = tuple(
        {"source_example_id": e.source_example_id, "reviewer_id": e.reviewer_id,
         "approved_utc": e.approved_utc}
        for e in ordered
    )
    return Snapshot(
        snapshot_hash=snapshot_hash,
        row_count=len(ordered),
        examples=ordered,
        train_hashes=train_hashes,
        per_decision_type=per_decision_type,
        record_groups=record_groups,
        n_groups=len(set(record_groups.values())),
        masked=mask,
        provenance=provenance,
        git_sha=git_sha,
        created_utc=created_utc or _now_iso(),
    )


def _assert_narrative_only(snapshot: Snapshot) -> None:
    """Re-assert the snapshot trains on NARRATIVE text only (allowlist) — never deterministic math.

    Fail-closed against a directly-constructed snapshot: any decision type not on the narrative
    allowlist (a frozen/deterministic type, an alias, or an unknown label) is rejected.
    """

    offenders = sorted(
        {
            e.decision_type
            for e in snapshot.examples
            if _normalize_decision_type(e.decision_type) not in NARRATIVE_DECISION_TYPES
        }
    )
    if offenders:
        raise NarrativeOnlyError(
            f"snapshot contains non-narrative decision types {offenders}; "
            "the regulated math must never be fine-tuned"
        )


# --------------------------------------------------------------------------- #
# Fine-tune (K-fold CV per GAMP 5 D11) + register (Prompt 13) + promote (Prompt 17)
# --------------------------------------------------------------------------- #
def finetune_narrative(
    snapshot: Snapshot,
    base_model_id: str,
    *,
    k_folds: int = 5,
    lora_config: LoRAConfig | None = None,
    trainer: FoldTrainer | None = None,
    seed: int = 0,
    semantic_version: str = "0.1.0",
    gpu_cost_per_hour: float = DEFAULT_MODAL_GPU_USD_PER_HOUR,
    adapter_dir: str | Path | None = None,
    git_sha: str = "unknown",
    created_utc: str | None = None,
) -> FineTuneRun:
    """LoRA fine-tune the narrative head (or a reranker) with leak-proof K-fold CV per GAMP 5 D11.

    Re-asserts the snapshot is narrative-only, then runs grouped K-fold CV tracking the
    narrative-quality metrics (reviewer-acceptance proxy, edit distance to final, citation
    correctness), fits the final adapter, and logs the Modal GPU cost. The training itself is
    delegated to the injected ``trainer``; with none the backend is :class:`FineTuneUnavailable`.
    The math is untouched — this returns a narrative adapter run, registered separately.
    """

    _assert_narrative_only(snapshot)  # HARD RULE re-check before any training
    if snapshot.row_count == 0:
        raise FineTuneError("cannot fine-tune on an empty snapshot")
    if snapshot.n_groups < 2:
        raise FineTuneError(
            f"need >= 2 leak-proof CV groups (distinct dossiers/documents) for K-fold "
            f"cross-validation, got {snapshot.n_groups}"
        )
    lora_config = lora_config or LoRAConfig()
    trainer = trainer or _UnavailableTrainer()
    by_hash = {e.train_hash: e for e in snapshot.examples}
    folds = _assign_folds(snapshot.train_hashes, k_folds, seed, groups=snapshot.record_groups)

    fold_metrics: list[FoldMetrics] = []
    for i, eval_hashes in enumerate(folds):
        if not eval_hashes:
            continue
        eval_set = [by_hash[h] for h in eval_hashes]
        train_set = [by_hash[h] for h in snapshot.train_hashes if h not in set(eval_hashes)]
        if not train_set:
            continue
        fold_metrics.append(
            trainer.train_and_eval(
                fold=i,
                train=train_set,
                eval=eval_set,
                base_model_id=base_model_id,
                lora_config=lora_config,
            )
        )

    if not fold_metrics:
        raise FineTuneError("no fold produced metrics; add more grouped examples for K-fold CV")
    acceptance_mean, acceptance_std = _mean_std([m.reviewer_acceptance_proxy for m in fold_metrics])
    edit_mean, edit_std = _mean_std([m.mean_edit_distance for m in fold_metrics])
    cc_mean, cc_std = _mean_std([m.citation_correctness for m in fold_metrics])

    out_dir = Path(adapter_dir) if adapter_dir is not None else Path("adapters")
    final = trainer.fit_final(
        train=list(snapshot.examples),
        base_model_id=base_model_id,
        lora_config=lora_config,
        out_dir=out_dir / snapshot.snapshot_hash.replace(":", "_"),
    )
    gpu_hours = sum(m.gpu_hours for m in fold_metrics) + final.gpu_hours

    return FineTuneRun(
        snapshot_hash=snapshot.snapshot_hash,
        base_model_id=base_model_id,
        semantic_version=semantic_version,
        lora_config=lora_config,
        k_folds=k_folds,
        seed=seed,
        row_count=snapshot.row_count,
        fold_metrics=tuple(fold_metrics),
        acceptance_mean=acceptance_mean,
        acceptance_std=acceptance_std,
        edit_distance_mean=edit_mean,
        edit_distance_std=edit_std,
        citation_correctness_mean=cc_mean,
        citation_correctness_std=cc_std,
        gpu_hours=gpu_hours,
        cost_usd=gpu_hours * gpu_cost_per_hour,
        adapter_path=final.path,
        adapter_sha256=final.sha256,
        git_sha=git_sha,
        created_utc=created_utc or _now_iso(),
    )


def narrative_promotion_gate(
    candidate: RegulatoryMetricVector, incumbent: RegulatoryMetricVector
) -> tuple[bool, list[str]]:
    """Promote iff narrative metrics improve with ZERO regression on citation correctness.

    A Prompt-17-style dominance gate scoped to NARRATIVE metrics: the deterministic calc-error /
    formula-coverage hard gates do not apply to a narrative adapter (it produces no regulated
    number). Citation correctness is a hard no-regression blocker.
    """

    reasons: list[str] = []
    cc_c, cc_i = candidate.citation_correctness, incumbent.citation_correctness
    if cc_c is None:
        # Cannot certify "zero regression on citation correctness" if it was never measured.
        return False, ["citation_correctness not measured on the candidate; cannot certify it"]
    if cc_i is not None and cc_c < cc_i - _EPS:
        return False, [f"citation_correctness regressed {cc_i} -> {cc_c} (hard blocker)"]

    improvements = 0
    regressions = 0
    for metric in (*_HIGHER_IS_BETTER, *_LOWER_IS_BETTER):
        c = getattr(candidate, metric, None)
        i = getattr(incumbent, metric, None)
        if c is None or i is None:
            continue
        progress = (c - i) if metric in _HIGHER_IS_BETTER else (i - c)
        if progress > _EPS:
            improvements += 1
        elif progress < -_EPS:
            regressions += 1
            reasons.append(f"{metric} regressed")
    passed = regressions == 0 and improvements >= 1
    if not passed and not reasons:
        reasons.append("no narrative metric improved")
    return passed, reasons


def register_narrative_adapter(
    run: FineTuneRun,
    *,
    registry: Registry,
    name: str,
    semver: str | None = None,
    incumbent_metrics: RegulatoryMetricVector | None = None,
    dataset_tag: str | None = None,
) -> RegistryEntry:
    """Register the narrative adapter (Prompt 13) with full lineage; gate promotion (Prompt 17).

    Always registered as a CANDIDATE with its snapshot/base-model/metrics lineage. If an incumbent
    is supplied and :func:`narrative_promotion_gate` passes, it is promoted to SHADOW (testing);
    PRODUCTION always requires a human sign-off and is never automatic. The artifact kind is
    NARRATIVE_ADAPTER — never a rule engine.
    """

    entry = registry.register_artifact(
        kind=ArtifactKind.NARRATIVE_ADAPTER,
        name=name,
        semver=semver or run.semantic_version,
        status=ArtifactStatus.CANDIDATE,
        notes=(
            f"LoRA narrative adapter; snapshot={run.snapshot_hash}; base={run.base_model_id}; "
            f"{run.k_folds}-fold CV; cost=${run.cost_usd:.2f}"
        ),
        extra={
            "snapshot_hash": run.snapshot_hash,
            "base_model_id": run.base_model_id,
            "dataset_tag": dataset_tag,
            "metrics": run.metric_vector().as_dict(),
            "adapter_sha256": run.adapter_sha256,
            "cost_usd": run.cost_usd,
        },
    )
    if incumbent_metrics is not None:
        promotable, gate_reasons = narrative_promotion_gate(run.metric_vector(), incumbent_metrics)
        if promotable:
            registry.set_status(
                entry.entry_id,
                ArtifactStatus.SHADOW,
                reason="narrative metrics improved, citation correctness no-regression",
            )
        else:
            registry.get(entry.entry_id).extra["promotion_blocked"] = gate_reasons
    return entry
