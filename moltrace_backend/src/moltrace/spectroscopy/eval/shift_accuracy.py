"""Held-out accuracy evaluation for the HOSE-code shift predictor (B5).

The point of this module is to let MolTrace *state its own error bar* rather than
quote someone else's benchmark. Published model MAEs describe that model on its
own test distribution; they are not a property of this product, and presenting
them as one is the failure mode this program was written to stop.

Leakage is the whole design problem
-----------------------------------
The knowledge base is built from NMRShiftDB2. Score the predictor on NMRShiftDB2
molecules already in the table and every atom finds its own reference: the error
collapses toward zero and the number is worthless. So evaluation splits **by
molecule** — deterministically, so a published figure can be reproduced — builds
the table from the training split alone, and scores the disjoint remainder.

What is reported, and why not just MAE
--------------------------------------
* **The distribution** (median, p90, p95, max), because MAE hides exactly the tail
  where a wrong structure gets confirmed.
* **Coverage** — the share of atoms that matched a real environment rather than
  falling back to the element average. An error computed only over matched atoms
  would flatter a sparse table, so both are reported and the element-prior atoms
  are scored too.
* **Calibration** — the predictor reports a per-atom σ, and that σ is what DP4's
  error model and the verifier's significance mapping both consume. If σ does not
  track the actual error, every downstream probability is arithmetic without
  evidence no matter how good the headline MAE looks.

Pure: no ORM, no HTTP, no clock, no randomness. The split is content-hashed, not
sampled, so it does not depend on a seed or on iteration order.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from moltrace.spectroscopy.predict.nmrnet_wrapper import (
    KnowledgeBase,
    build_knowledge_base,
    hose_code,
    molecule_from_record,
)

__all__ = [
    "ShiftAccuracyReport",
    "split_records",
    "evaluate_shift_accuracy",
]

#: σ bin edges (ppm) for the calibration table. Chosen to straddle DP4's own
#: scales — 0.185 ppm (¹H) and 2.306 ppm (¹³C) — since the question the table
#: answers is whether a reported σ is trustworthy at the width DP4 assumes.
_SIGMA_BINS: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0, 10.0, 25.0)


def _record_key(record: Mapping[str, Any]) -> str:
    """Stable identity for a molecule record — the thing a split must not straddle."""

    return str(record.get("molblock") or record.get("smiles") or "")


def split_records(
    records: Sequence[Mapping[str, Any]], test_fraction: float = 0.1
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Split by molecule into (train, test), deterministically.

    Assignment is by SHA-256 of the record's molecule, not by sampling: identical
    input gives an identical split on any machine and in any order, which is what
    makes a published number reproducible. Every record sharing a molecule lands
    on the same side, so the same structure can never appear in both.
    """

    if not 0.0 < test_fraction < 1.0:
        raise ValueError(f"test_fraction must be in (0, 1); got {test_fraction}")

    threshold = int(test_fraction * (1 << 32))
    train: list[Mapping[str, Any]] = []
    test: list[Mapping[str, Any]] = []
    for record in records:
        digest = hashlib.sha256(_record_key(record).encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big")
        (test if bucket < threshold else train).append(record)
    return train, test


@dataclass(frozen=True)
class ShiftAccuracyReport:
    """Measured accuracy on a held-out split. Every figure is reproducible."""

    per_nucleus: dict[str, dict[str, float]]
    calibration: list[dict[str, float]]
    n_train_molecules: int
    n_test_molecules: int
    n_train_references: int
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "per_nucleus": self.per_nucleus,
            "calibration": self.calibration,
            "n_train_molecules": self.n_train_molecules,
            "n_test_molecules": self.n_test_molecules,
            "n_train_references": self.n_train_references,
            "notes": list(self.notes),
        }


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return float(ordered[index])


def evaluate_shift_accuracy(
    *,
    train: Sequence[Mapping[str, Any]],
    test: Sequence[Mapping[str, Any]],
    knowledge_base: KnowledgeBase | None = None,
) -> ShiftAccuracyReport:
    """Build a table from ``train`` and score it against ``test``.

    ``test`` records supply the ground truth: their own assignments are never
    indexed, so each predicted shift is compared against a value the table has
    not seen.
    """

    if not test:
        raise ValueError("evaluate_shift_accuracy needs a non-empty test split")
    if not train:
        raise ValueError("evaluate_shift_accuracy needs a non-empty train split")

    kb = knowledge_base if knowledge_base is not None else build_knowledge_base(train)

    # nucleus -> lists of (abs_error, sigma, matched)
    errors: dict[str, list[tuple[float, float, bool]]] = {}
    skipped = 0

    for record in test:
        mol_h = molecule_from_record(record)
        if mol_h is None:
            skipped += 1
            continue
        n_atoms = mol_h.GetNumAtoms()
        for assignment in record.get("assignments", []):
            nucleus = str(assignment.get("nucleus", ""))
            atom_index = int(assignment.get("atom_index", -1))
            if not (0 <= atom_index < n_atoms):
                continue
            try:
                observed = float(assignment["shift_ppm"])
            except (KeyError, TypeError, ValueError):
                continue

            hit = kb.lookup(nucleus, hose_code(mol_h, atom_index))
            if hit is not None:
                predicted, sigma, _sphere, _n = hit
                matched = True
            else:
                predicted = kb.priors.get(nucleus, float("nan"))
                sigma = float("nan")
                matched = False
            if not math.isfinite(predicted):
                continue
            errors.setdefault(nucleus, []).append(
                (abs(predicted - observed), sigma, matched)
            )

    per_nucleus: dict[str, dict[str, float]] = {}
    for nucleus, rows in sorted(errors.items()):
        all_ae = [ae for ae, _s, _m in rows]
        matched_ae = [ae for ae, _s, m in rows if m]
        prior_ae = [ae for ae, _s, m in rows if not m]
        per_nucleus[nucleus] = {
            "n_atoms": float(len(rows)),
            "n_matched": float(len(matched_ae)),
            "n_element_prior": float(len(prior_ae)),
            "coverage": len(matched_ae) / len(rows) if rows else 0.0,
            "mae_ppm": statistics.fmean(all_ae) if all_ae else float("nan"),
            "median_ae_ppm": _percentile(all_ae, 0.5),
            "p90_ae_ppm": _percentile(all_ae, 0.90),
            "p95_ae_ppm": _percentile(all_ae, 0.95),
            "max_ae_ppm": max(all_ae) if all_ae else float("nan"),
            # Reported separately because the element-prior atoms are an
            # abstention, and averaging them into one headline number hides both
            # how good the lookup is and how often it is unavailable.
            "matched_mae_ppm": statistics.fmean(matched_ae) if matched_ae else float("nan"),
            "element_prior_mae_ppm": statistics.fmean(prior_ae) if prior_ae else float("nan"),
        }

    calibration = _calibration_table(errors)

    notes: list[str] = []
    if skipped:
        notes.append(f"{skipped} test record(s) skipped: molecule could not be parsed.")
    notes.append(
        "Held-out by molecule (SHA-256 of the structure), so no test molecule is in "
        "the knowledge base. Element-prior atoms are scored, not dropped."
    )

    return ShiftAccuracyReport(
        per_nucleus=per_nucleus,
        calibration=calibration,
        n_train_molecules=len(train),
        n_test_molecules=len(test),
        n_train_references=kb.reference_count,
        notes=notes,
    )


def _calibration_table(
    errors: Mapping[str, Sequence[tuple[float, float, bool]]],
) -> list[dict[str, float]]:
    """Does a reported σ predict the actual error?

    Grouped over matched atoms only: an element-prior atom reports the element's
    whole range as its σ, which is an honest abstention rather than a calibration
    claim, so including it would say more about coverage than about calibration.
    """

    rows: list[dict[str, float]] = []
    for nucleus, entries in sorted(errors.items()):
        matched = [(ae, s) for ae, s, m in entries if m and math.isfinite(s)]
        if not matched:
            continue
        edges = [0.0, *_SIGMA_BINS, float("inf")]
        for low, high in zip(edges, edges[1:], strict=False):
            bucket = [(ae, s) for ae, s in matched if low <= s < high]
            if not bucket:
                continue
            rows.append(
                {
                    "nucleus": nucleus,  # type: ignore[dict-item]
                    "sigma_bin": f"{low:g}-{high:g}",  # type: ignore[dict-item]
                    "n": float(len(bucket)),
                    "mean_sigma_ppm": statistics.fmean(s for _ae, s in bucket),
                    "mean_abs_error_ppm": statistics.fmean(ae for ae, _s in bucket),
                    "median_abs_error_ppm": _percentile([ae for ae, _s in bucket], 0.5),
                }
            )
    return rows
