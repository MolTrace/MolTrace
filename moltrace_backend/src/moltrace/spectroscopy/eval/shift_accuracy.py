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
    "ErrorModelFit",
    "split_records",
    "split_records_three_way",
    "evaluate_shift_accuracy",
    "fit_error_model",
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


def split_records_three_way(
    records: Sequence[Mapping[str, Any]],
    *,
    calibration_fraction: float = 0.10,
    test_fraction: float = 0.10,
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """Split by molecule into (train, calibration, test), deterministically.

    Conformal prediction needs a calibration set disjoint from *both* the training
    data and the split coverage is measured on — calibrate and evaluate on the same
    atoms and the interval is fitted to the errors it is then scored against, so the
    coverage guarantee measures nothing.

    **Do not build this by calling :func:`split_records` twice.** The split is a
    deterministic function of the molecule hash, so re-splitting a held-out set with
    the same hash puts *every* record on one side: each one already sits below the
    first threshold, so it also sits below any larger second threshold. That returns
    an empty calibration set — silently, if nobody checks. The three bands here are
    cut from one hash in a single pass, which is the only way to keep them disjoint.
    """

    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError(f"calibration_fraction must be in (0, 1); got {calibration_fraction}")
    if not 0.0 < test_fraction < 1.0:
        raise ValueError(f"test_fraction must be in (0, 1); got {test_fraction}")
    if calibration_fraction + test_fraction >= 1.0:
        raise ValueError(
            f"calibration_fraction + test_fraction must leave a training split; got "
            f"{calibration_fraction} + {test_fraction}"
        )

    test_cut = int(test_fraction * (1 << 32))
    calibration_cut = test_cut + int(calibration_fraction * (1 << 32))
    train: list[Mapping[str, Any]] = []
    calibration: list[Mapping[str, Any]] = []
    test: list[Mapping[str, Any]] = []
    for record in records:
        digest = hashlib.sha256(_record_key(record).encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big")
        if bucket < test_cut:
            test.append(record)
        elif bucket < calibration_cut:
            calibration.append(record)
        else:
            train.append(record)
    return train, calibration, test


@dataclass(frozen=True)
class ShiftAccuracyReport:
    """Measured accuracy on a held-out split. Every figure is reproducible."""

    per_nucleus: dict[str, dict[str, float]]
    calibration: list[dict[str, float]]
    n_train_molecules: int
    n_test_molecules: int
    n_train_references: int
    signed_errors: dict[str, list[float]] = field(default_factory=dict)
    """Matched-only ``predicted − observed`` per nucleus; the input to :func:`fit_error_model`."""
    sigma_error_pairs: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    """Matched-only ``(reported_sigma_ppm, absolute_error_ppm)`` per nucleus.

    The input to :func:`~moltrace.spectroscopy.eval.conformal.fit_conformal`. Kept
    paired rather than as two lists because the whole point is the *relationship*:
    :attr:`calibration` measured that a reported σ ≤ 0.5 ppm on ¹³C carries a mean
    error of 0.76 ppm, and a conformal band can only repair that if it knows which
    error went with which claim.

    Element-prior atoms are excluded — they report no σ, so there is nothing to
    calibrate against, and treating an abstention as a σ of zero would fabricate the
    most confident possible claim out of the least confident state.
    """
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "per_nucleus": self.per_nucleus,
            "calibration": self.calibration,
            "n_train_molecules": self.n_train_molecules,
            "n_test_molecules": self.n_test_molecules,
            "n_train_references": self.n_train_references,
            "n_signed_errors": {k: len(v) for k, v in self.signed_errors.items()},
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
    signed: dict[str, list[float]] = {}
    sigma_pairs: dict[str, list[tuple[float, float]]] = {}
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
            if matched:
                # Signed, matched-only — the input fit_error_model needs. An
                # element-prior atom is an abstention, not a prediction.
                signed.setdefault(nucleus, []).append(predicted - observed)
                if math.isfinite(sigma):
                    sigma_pairs.setdefault(nucleus, []).append(
                        (sigma, abs(predicted - observed))
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
        signed_errors=signed,
        sigma_error_pairs=sigma_pairs,
        n_train_molecules=len(train),
        n_test_molecules=len(test),
        n_train_references=kb.reference_count,
        notes=notes,
    )


@dataclass(frozen=True)
class ErrorModelFit:
    """A Student's-t fit to a predictor's *signed* shift errors, per nucleus.

    Why this matters, mechanically
    ------------------------------
    DP4 (``nmrcheck.dp4_scoring``) scores a candidate as
    ``∏_k (1 − T_ν(|Δ_k| / σ))`` using the **published** Smith & Goodman scale and
    degrees of freedom — σ = 2.306 ppm / ν = 11.38 for ¹³C. Those constants were
    fit to **GIAO-DFT** shift errors. Applying them to a *different* predictor
    assumes the two share an error distribution, and that assumption is testable.

    ν is the load-bearing parameter. It sets how surprising a large deviation is:
    ν ≈ 12 is near-Gaussian, so a big outlier is treated as near-impossible and
    drives that candidate's probability toward zero; ν ≈ 1 is Cauchy-like, where
    large deviations are an ordinary occurrence. Score a heavy-tailed predictor
    with a thin-tailed model and a **single** badly-predicted atom annihilates the
    *correct* candidate — a false rejection, produced confidently.

    A caveat this fit cannot separate on its own
    --------------------------------------------
    A heavy tail measured against NMRShiftDB2 is part genuine prediction failure
    and part **label noise**: the reference data is community-submitted and
    contains mis-assignments, and a 146 ppm ¹³C "error" is far more likely a bad
    database record than a real prediction. Both inflate the tail. So this is
    evidence that the published ν is wrong *for this predictor on this data* — not
    a finished replacement constant. Treat it as a measurement, not a patch.
    """

    nucleus: str
    n: int
    scale: float
    """Fitted Student's-t scale (ppm) — the analogue of DP4's σ."""
    dof: float
    """Fitted degrees of freedom — the analogue of DP4's ν. Low = heavy tails."""
    loc: float
    mae: float
    rmse: float
    published_scale: float
    published_dof: float

    @property
    def rmse_over_mae(self) -> float:
        """Tail indicator: ≈1.25 for a Gaussian, higher as tails fatten."""

        return self.rmse / self.mae if self.mae else float("nan")

    def as_dict(self) -> dict[str, Any]:
        return {
            "nucleus": self.nucleus,
            "n": self.n,
            "fitted_scale_ppm": self.scale,
            "fitted_dof": self.dof,
            "fitted_loc_ppm": self.loc,
            "mae_ppm": self.mae,
            "rmse_ppm": self.rmse,
            "rmse_over_mae": self.rmse_over_mae,
            "published_scale_ppm": self.published_scale,
            "published_dof": self.published_dof,
            "scale_ratio": self.scale / self.published_scale
            if self.published_scale
            else float("nan"),
            "dof_ratio": self.dof / self.published_dof if self.published_dof else float("nan"),
        }


def fit_error_model(
    signed_errors: Mapping[str, Sequence[float]],
) -> dict[str, ErrorModelFit]:
    """Fit a Student's t to each nucleus's signed errors and compare to DP4's.

    ``signed_errors`` maps a nucleus to ``predicted − observed`` values, matched
    atoms only: an element-prior atom is an abstention, not a prediction, and
    folding it in would measure coverage rather than the error model.
    """

    from scipy import stats  # SciPy is already a core dependency.

    from nmrcheck.literature_data import dp4_nu, dp4_sigma

    fits: dict[str, ErrorModelFit] = {}
    for nucleus, values in sorted(signed_errors.items()):
        errors = [float(v) for v in values if math.isfinite(v)]
        if len(errors) < 50:
            continue
        dof, loc, scale = stats.t.fit(errors)
        abs_errors = [abs(e) for e in errors]
        fits[nucleus] = ErrorModelFit(
            nucleus=nucleus,
            n=len(errors),
            scale=float(scale),
            dof=float(dof),
            loc=float(loc),
            mae=statistics.fmean(abs_errors),
            rmse=math.sqrt(statistics.fmean(e * e for e in errors)),
            published_scale=float(dp4_sigma(nucleus)),  # type: ignore[arg-type]
            published_dof=float(dp4_nu(nucleus)),  # type: ignore[arg-type]
        )
    return fits


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
