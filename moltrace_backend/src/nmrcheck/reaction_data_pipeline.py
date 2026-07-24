"""Repho Phase C foundation — license-aware reaction-data ingestion + frozen splits.

Heavy-ML models (R12-R14) are only as trustworthy as the data discipline beneath them, so the
pipeline enforces three things *in the engine*, not in reviewer diligence:

1. **License awareness, fail-closed.** Every dataset must be registered with its license and an
   allowed-usage class before a single record is ingested. Commercial corpora (Reaxys, Pistachio)
   are refused for any purpose; Bretherick's is refused outright (copyrighted compilation — R6's
   rules are built from public GHS/structural motifs instead); the published HTE benchmarks
   (Buchwald-Hartwig, Suzuki-Miyaura) are **benchmark-only** — usable to judge a model, never to
   train one. An unregistered dataset is refused, never assumed open.
2. **Frozen, seeded, order-independent splits.** Split assignment is a pure function of
   ``sha256(seed:record_id)`` — the same records produce the same split in any order, on any
   machine, with no RNG state. The resulting manifest is content-hashed (the R11 checksum
   discipline) and verification **refuses to run on drift**.
3. **Benchmark hash-exclusion.** Ids named as benchmark/gold observations are excluded from every
   training-side split by normalised id (the R10 rule: NFC + strip on both sides) and a leak check
   can be re-run independently at any time.

Pure: no DB / HTTP / clock / randomness (the split "randomness" is a content hash). RDKit is
lazily imported for SMILES canonicalisation and validation degrades honestly without it.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

ENGINE = "reaction_data_pipeline.v1"

USAGE_TRAINING_AND_BENCHMARK = "training_and_benchmark"
USAGE_BENCHMARK_ONLY = "benchmark_only"
USAGE_PROHIBITED = "prohibited"

_TRAIN_SIDE_PURPOSES = {"training", "pretraining", "fine_tuning", "warm_start"}
_BENCHMARK_PURPOSES = {"benchmark", "evaluation"}


class ReactionDataError(Exception):
    """Raised on a license refusal, a malformed manifest, or a split-integrity failure."""


@dataclass(frozen=True)
class DatasetLicense:
    dataset: str
    license: str
    usage: str  # USAGE_* above
    citation: str = ""
    attribution_required: bool = False
    share_alike: bool = False
    note: str = ""


# License registry — data facts per the build spec's corrected, license-tagged table.
LICENSE_REGISTRY: dict[str, DatasetLicense] = {
    entry.dataset: entry
    for entry in (
        DatasetLicense(
            dataset="ord",
            license="CC-BY-SA-4.0 (data); Apache-2.0 (software)",
            usage=USAGE_TRAINING_AND_BENCHMARK,
            citation="Kearnes et al., JACS 143, 18820 (2021)",
            attribution_required=True,
            share_alike=True,
            note="Share-alike: derived published datasets must carry the same license.",
        ),
        DatasetLicense(
            dataset="uspto_50k",
            license="open",
            usage=USAGE_TRAINING_AND_BENCHMARK,
            citation="Lowe, USPTO reaction extraction",
        ),
        DatasetLicense(
            dataset="uspto_full",
            license="open",
            usage=USAGE_TRAINING_AND_BENCHMARK,
            citation="Lowe, USPTO reaction extraction",
        ),
        DatasetLicense(
            dataset="buchwald_hartwig_hte",
            license="open (published dataset)",
            usage=USAGE_BENCHMARK_ONLY,
            citation=(
                "Ahneman et al., Science 360, 186 (2018); see also Chuang & Keiser, "
                "Science (2018) on descriptor leakage"
            ),
            note="Held-out reproduction benchmark — never trained on (hash-excluded).",
        ),
        DatasetLicense(
            dataset="suzuki_miyaura_hte",
            license="open (published dataset)",
            usage=USAGE_BENCHMARK_ONLY,
            note="Held-out cross-coupling benchmark — never trained on (hash-excluded).",
        ),
        DatasetLicense(
            dataset="nist_webbook",
            license="open",
            usage=USAGE_TRAINING_AND_BENCHMARK,
            note="Thermochemistry background for the R6 exothermicity context.",
        ),
        DatasetLicense(
            dataset="reaxys",
            license="commercial",
            usage=USAGE_PROHIBITED,
            note="License-gate before any query; never ingest, never bundle.",
        ),
        DatasetLicense(
            dataset="pistachio",
            license="commercial",
            usage=USAGE_PROHIBITED,
            note="License-gate before any query; never ingest, never bundle.",
        ),
        DatasetLicense(
            dataset="brethericks",
            license="copyrighted compilation",
            usage=USAGE_PROHIBITED,
            note="Background reading only; R6 encodes public GHS/structural motifs instead.",
        ),
    )
}


def assert_usage_allowed(dataset: str, purpose: str) -> DatasetLicense:
    """Fail-closed license gate: refuse unknown datasets, prohibited corpora, and any
    training-side use of a benchmark-only dataset."""

    entry = LICENSE_REGISTRY.get(dataset)
    if entry is None:
        raise ReactionDataError(
            f"Dataset {dataset!r} is not in the license registry; refusing to ingest. "
            "Register it with its license and allowed usage first."
        )
    if entry.usage == USAGE_PROHIBITED:
        raise ReactionDataError(
            f"Dataset {dataset!r} ({entry.license}) is prohibited: {entry.note or 'license-gated.'}"
        )
    if purpose in _TRAIN_SIDE_PURPOSES and entry.usage == USAGE_BENCHMARK_ONLY:
        raise ReactionDataError(
            f"Dataset {dataset!r} is benchmark-only; training-side use ({purpose!r}) is refused "
            "so a model is never judged on data it trained from."
        )
    if purpose not in _TRAIN_SIDE_PURPOSES | _BENCHMARK_PURPOSES:
        raise ReactionDataError(f"Unknown data purpose {purpose!r}.")
    return entry


# --------------------------------------------------------------------------- #
# Records + validation.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReactionRecord:
    record_id: str
    dataset: str
    reactants_smiles: tuple[str, ...]
    products_smiles: tuple[str, ...]
    conditions: Mapping[str, Any] = field(default_factory=dict)
    yield_percent: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _load_rdkit():
    try:
        from rdkit import Chem  # noqa: PLC0415 (lazy: canonicalisation is optional)

        return Chem
    except ImportError:
        return None


def _canonical_smiles(chem: Any, smiles: str) -> str | None:
    mol = chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    return chem.MolToSmiles(mol)


def validate_records(
    records: Iterable[ReactionRecord],
    *,
    canonicalize: bool = True,
    purpose: str = "training",
) -> tuple[list[ReactionRecord], list[dict[str, Any]]]:
    """Validate + (optionally) canonicalise records. Returns ``(valid, rejected)``.

    Rejections carry the record id and every reason — bad rows are surfaced, never silently
    dropped or silently kept. The license gate is enforced per record for ``purpose``.

    When RDKit is unavailable, SMILES canonicalisation and structural parsing CANNOT run; that
    is reported explicitly as a synthetic rejection entry with ``record_id=None`` so a caller
    never mistakes 'not canonicalised' for 'canonicalised and clean'. Structural validation
    (ids, dataset licence, yield range) is unaffected.
    """

    chem = _load_rdkit() if canonicalize else None
    valid: list[ReactionRecord] = []
    rejected: list[dict[str, Any]] = []
    if canonicalize and chem is None:
        rejected.append(
            {
                "record_id": None,
                "reasons": [
                    "rdkit unavailable: SMILES were NOT canonicalised or structurally "
                    "validated; treat kept records as unverified chemistry"
                ],
            }
        )
    seen: set[str] = set()
    for record in records:
        reasons: list[str] = []
        rid = _normalize_id(record.record_id)
        if not rid:
            reasons.append("empty record_id")
        elif rid in seen:
            reasons.append(f"duplicate record_id {rid!r}")
        # The license gate binds HERE, at the record level — an unregistered, prohibited, or
        # benchmark-only-for-training row is rejected rather than admitted for a later caller to
        # (maybe) check. Ingestion is where the licence promise is actually kept.
        try:
            assert_usage_allowed(record.dataset, purpose)
        except ReactionDataError as exc:
            reasons.append(str(exc))
        if not record.reactants_smiles:
            reasons.append("no reactants")
        if record.yield_percent is not None:
            y = record.yield_percent
            if not isinstance(y, (int, float)) or not math.isfinite(float(y)):
                reasons.append(f"non-finite yield {y!r}")
            elif not (0.0 <= float(y) <= 105.0):
                # >100 happens with quantitation error; >105 is treated as corrupt.
                reasons.append(f"yield out of range: {y!r}")

        reactants = record.reactants_smiles
        products = record.products_smiles
        if chem is not None:
            canon_reactants: list[str] = []
            for smiles in record.reactants_smiles:
                canon = _canonical_smiles(chem, smiles)
                if canon is None:
                    reasons.append(f"unparseable reactant SMILES {smiles!r}")
                else:
                    canon_reactants.append(canon)
            canon_products: list[str] = []
            for smiles in record.products_smiles:
                canon = _canonical_smiles(chem, smiles)
                if canon is None:
                    reasons.append(f"unparseable product SMILES {smiles!r}")
                else:
                    canon_products.append(canon)
            reactants = tuple(canon_reactants)
            products = tuple(canon_products)

        if reasons:
            rejected.append({"record_id": record.record_id, "reasons": reasons})
            continue
        seen.add(rid)
        valid.append(
            ReactionRecord(
                record_id=rid,
                dataset=record.dataset,
                reactants_smiles=tuple(reactants),
                products_smiles=tuple(products),
                conditions=dict(record.conditions),
                yield_percent=(
                    float(record.yield_percent) if record.yield_percent is not None else None
                ),
                metadata=dict(record.metadata),
            )
        )
    return valid, rejected


# --------------------------------------------------------------------------- #
# Frozen, seeded, order-independent splits with benchmark hash-exclusion.
# --------------------------------------------------------------------------- #
@dataclass
class SplitManifest:
    seed: int
    fractions: dict[str, float]
    splits: dict[str, list[str]]  # split name -> sorted record ids
    held_out_benchmark: list[str]
    checksum: str
    lineage: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "fractions": dict(self.fractions),
            "splits": {name: list(ids) for name, ids in self.splits.items()},
            "held_out_benchmark": list(self.held_out_benchmark),
            "checksum": self.checksum,
            "lineage": dict(self.lineage),
            "engine": ENGINE,
        }


def _normalize_id(value: Any) -> str:
    """Normalise an id the same way on both sides of exclusion (the R10 rule: NFC + strip)."""

    return unicodedata.normalize("NFC", str(value)).strip()


def _split_fraction(seed: int, record_id: str) -> float:
    """Deterministic position in [0, 1) from a content hash — no RNG, no order dependence."""

    digest = hashlib.sha256(f"{seed}:{record_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _manifest_checksum(body: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {k: body[k] for k in sorted(body) if k != "checksum"},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assign_splits(
    record_ids: Iterable[str],
    *,
    seed: int,
    fractions: Mapping[str, float] | None = None,
    benchmark_ids: Iterable[str] = (),
    source: str | None = None,
) -> SplitManifest:
    """Assign records to frozen splits; benchmark ids are held out of every split.

    Fractions default to ``{"train": 0.8, "val": 0.1, "test": 0.1}``; they must be positive and
    sum to 1. Duplicate record ids are refused (assignment "by id" must be unambiguous — the R10
    lesson). Assignment is a pure content-hash function, so any permutation of the same ids
    yields byte-identical splits and an identical manifest checksum.
    """

    fracs = dict(fractions) if fractions is not None else {"train": 0.8, "val": 0.1, "test": 0.1}
    if not fracs or any(f <= 0 or not math.isfinite(f) for f in fracs.values()):
        raise ReactionDataError("Split fractions must be positive and finite.")
    if abs(sum(fracs.values()) - 1.0) > 1e-9:
        raise ReactionDataError(f"Split fractions must sum to 1, got {sum(fracs.values())!r}.")

    # Hash with the SAME int the manifest records, or the frozen manifest could not
    # reproduce its own splits (e.g. a float/str seed hashing differently than int(seed)).
    seed = int(seed)
    gold = {_normalize_id(item) for item in benchmark_ids}
    seen: set[str] = set()
    held_out: list[str] = []
    splits: dict[str, list[str]] = {name: [] for name in fracs}
    boundaries: list[tuple[str, float]] = []
    cumulative = 0.0
    for name in sorted(fracs):  # deterministic boundary order
        cumulative += fracs[name]
        boundaries.append((name, cumulative))

    for raw_id in record_ids:
        rid = _normalize_id(raw_id)
        if not rid:
            raise ReactionDataError("Empty record id in split input.")
        if rid in seen:
            raise ReactionDataError(f"Duplicate record id in split input: {rid!r}")
        seen.add(rid)
        if rid in gold:
            held_out.append(rid)
            continue
        fraction = _split_fraction(seed, rid)
        for name, upper in boundaries:
            if fraction < upper or name == boundaries[-1][0]:
                splits[name].append(rid)
                break

    if not any(splits.values()):
        raise ReactionDataError("No records remain after benchmark hold-out; refusing to freeze.")

    for ids in splits.values():
        ids.sort()
    held_out.sort()
    body: dict[str, Any] = {
        "seed": int(seed),
        "fractions": {k: float(v) for k, v in sorted(fracs.items())},
        "splits": splits,
        "held_out_benchmark": held_out,
        "lineage": {
            "source": source,
            "engine": ENGINE,
            "record_count": sum(len(v) for v in splits.values()),
            "held_out_count": len(held_out),
            "benchmark_id_count": len(gold),
        },
    }
    checksum = _manifest_checksum(body)
    return SplitManifest(
        seed=int(seed),
        fractions=body["fractions"],
        splits=splits,
        held_out_benchmark=held_out,
        checksum=checksum,
        lineage=body["lineage"],
    )


def verify_manifest(manifest: Mapping[str, Any]) -> SplitManifest:
    """Re-parse + re-checksum a frozen manifest; refuse to run on drift (the R11 posture)."""

    recorded = str(manifest.get("checksum") or "")
    if not recorded:
        raise ReactionDataError("Split manifest carries no checksum; refusing.")
    body = {
        "seed": manifest.get("seed"),
        "fractions": manifest.get("fractions"),
        "splits": manifest.get("splits"),
        "held_out_benchmark": manifest.get("held_out_benchmark"),
        "lineage": manifest.get("lineage"),
    }
    actual = _manifest_checksum(body)
    if actual != recorded:
        raise ReactionDataError(
            f"Split-manifest drift: recorded {recorded} != computed {actual}; refusing. "
            "Re-freeze deliberately if the change is intended."
        )
    splits_raw = manifest.get("splits")
    if not isinstance(splits_raw, Mapping) or not splits_raw:
        raise ReactionDataError("Split manifest has no splits.")
    return SplitManifest(
        seed=int(manifest["seed"]),
        fractions={str(k): float(v) for k, v in dict(manifest["fractions"]).items()},
        splits={str(k): [str(i) for i in v] for k, v in splits_raw.items()},
        held_out_benchmark=[str(i) for i in manifest.get("held_out_benchmark") or []],
        checksum=recorded,
        lineage=dict(manifest.get("lineage") or {}),
    )


def assert_no_benchmark_leakage(
    manifest: SplitManifest, benchmark_ids: Iterable[str]
) -> None:
    """Independent leak re-check: no benchmark id may appear in ANY split (normalised match)."""

    gold = {_normalize_id(item) for item in benchmark_ids}
    leaked: list[str] = []
    for name, ids in manifest.splits.items():
        for rid in ids:
            if _normalize_id(rid) in gold:
                leaked.append(f"{name}:{rid}")
    if leaked:
        raise ReactionDataError(f"Benchmark ids leaked into training splits: {sorted(leaked)}")


def training_ids(manifest: SplitManifest, *, train_split: str = "train") -> list[str]:
    """The train-side ids. Raises rather than returning [] when the split does not exist.

    A silent empty list would read as 'no training data' instead of 'you named the split
    something else', which is exactly how a training run ends up quietly using nothing.
    """

    if train_split not in manifest.splits:
        raise ReactionDataError(
            f"Split {train_split!r} is not in the manifest (have: {sorted(manifest.splits)})."
        )
    return list(manifest.splits[train_split])
