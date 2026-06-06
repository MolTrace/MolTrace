"""Phase 0 evaluation framework -- the single source of truth for "better".

Every later phase (model selection, calibration work, regression gates, the
Prompt 17 active-learning loop) compares candidates through *these* metrics, so
they are defined here once, as pure functions with literature citations, and
unit-tested against hand-computed fixtures.

Metrics implemented
-------------------
* :func:`rmse` -- root-mean-square error for chemical-shift prediction (ppm).
* :func:`f1_score` / :func:`peak_detection_f1` / :func:`classification_f1` --
  precision / recall / F1 for peak picking and peak classification
  (van Rijsbergen, *Information Retrieval*, 2nd ed., 1979).
* :func:`top_k_accuracy` -- fraction of queries whose true answer appears in the
  top-k ranked candidates (standard retrieval metric).
* :func:`bedroc` -- Boltzmann-Enhanced Discrimination of ROC, an
  early-recognition metric for ranked candidate lists
  (Truchon & Bayly, *J. Chem. Inf. Model.* 2007, 47, 488-508).
* :func:`expected_calibration_error` -- ECE with equal-width binning
  (Guo, Pleiss, Sun & Weinberger, "On Calibration of Modern Neural Networks",
  *ICML* 2017).

All functions are pure (no I/O, no globals) and deterministic.  numpy and scipy
are core dependencies of this package (transitive, hard, via lmfit), so they are
imported unconditionally.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

__all__ = [
    "PRF",
    "MetricVector",
    "bedroc",
    "classification_f1",
    "expected_calibration_error",
    "f1_score",
    "peak_detection_f1",
    "reliability_bins",
    "rmse",
    "top_k_accuracy",
]


# --------------------------------------------------------------------------- #
# Result containers
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PRF:
    """Precision / recall / F1 plus the confusion counts they were derived from."""

    precision: float
    recall: float
    f1: float
    true_positives: int
    false_positives: int
    false_negatives: int

    def as_dict(self) -> dict[str, float]:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "true_positives": float(self.true_positives),
            "false_positives": float(self.false_positives),
            "false_negatives": float(self.false_negatives),
        }


@dataclass(frozen=True)
class MetricVector:
    """The standard Phase-0 metric vector logged for every experiment run.

    Fields are optional so a run can report only the metrics it measured.
    :meth:`as_dict` flattens to a ``{str: float}`` map suitable for direct
    logging to MLflow / the native run store (see :mod:`.tracking`).
    """

    rmse: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    bedroc: float | None = None
    ece: float | None = None
    top_k: Mapping[int, float] | None = field(default=None)

    def as_dict(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for name in ("rmse", "precision", "recall", "f1", "bedroc", "ece"):
            value = getattr(self, name)
            if value is not None:
                out[name] = float(value)
        if self.top_k:
            for k, acc in self.top_k.items():
                out[f"top_{int(k)}_accuracy"] = float(acc)
        return out


# --------------------------------------------------------------------------- #
# Regression error
# --------------------------------------------------------------------------- #
def rmse(predicted: Sequence[float], reference: Sequence[float]) -> float:
    """Root-mean-square error between paired predictions and references.

    Used for chemical-shift accuracy (ppm) once predicted peaks have been paired
    to reference peaks.  ``predicted`` and ``reference`` must be the same length
    and already aligned element-wise.

    Raises
    ------
    ValueError
        If the inputs are empty, mismatched in length, or non-finite.
    """

    pred = np.asarray(predicted, dtype=float)
    ref = np.asarray(reference, dtype=float)
    if pred.shape != ref.shape:
        raise ValueError(f"length mismatch: {pred.shape} vs {ref.shape}")
    if pred.size == 0:
        raise ValueError("rmse requires at least one paired observation")
    if not (np.all(np.isfinite(pred)) and np.all(np.isfinite(ref))):
        raise ValueError("rmse inputs must be finite")
    return float(np.sqrt(np.mean((pred - ref) ** 2)))


# --------------------------------------------------------------------------- #
# Precision / recall / F1
# --------------------------------------------------------------------------- #
def f1_score(true_positives: int, false_positives: int, false_negatives: int) -> PRF:
    """Precision / recall / F1 from raw confusion counts (van Rijsbergen 1979).

    F1 is the harmonic mean of precision and recall.  By convention, precision
    and recall are 0.0 when their denominators are 0 (no predictions / no
    references), which makes F1 0.0 -- the standard degenerate-case handling.
    """

    tp = int(true_positives)
    fp = int(false_positives)
    fn = int(false_negatives)
    if tp < 0 or fp < 0 or fn < 0:
        raise ValueError("confusion counts must be non-negative")
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return PRF(precision, recall, f1, tp, fp, fn)


def peak_detection_f1(
    predicted_positions: Sequence[float],
    reference_positions: Sequence[float],
    *,
    tolerance: float,
) -> PRF:
    """F1 for peak picking using optimal 1-to-1 matching within ``tolerance``.

    A predicted peak matches a reference peak when their positions differ by no
    more than ``tolerance`` (same units as the positions, typically ppm).  The
    globally optimal matching that maximises the number of true positives is
    found with the Hungarian algorithm (:func:`scipy.optimize.linear_sum_assignment`)
    so that, e.g., two nearby predictions cannot both claim one reference.

    * matched pairs within tolerance -> true positives
    * unmatched predictions          -> false positives
    * unmatched references           -> false negatives
    """

    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
    pred = np.asarray(predicted_positions, dtype=float)
    ref = np.asarray(reference_positions, dtype=float)
    if pred.size and not np.all(np.isfinite(pred)):
        raise ValueError("predicted positions must be finite")
    if ref.size and not np.all(np.isfinite(ref)):
        raise ValueError("reference positions must be finite")

    n_pred = int(pred.size)
    n_ref = int(ref.size)
    if n_pred == 0 or n_ref == 0:
        return f1_score(0, n_pred, n_ref)

    cost = np.abs(pred[:, None] - ref[None, :])
    # Forbid matches outside tolerance by making them prohibitively expensive.
    big = float(cost.max()) + tolerance + 1.0
    masked = np.where(cost <= tolerance, cost, big)
    rows, cols = linear_sum_assignment(masked)
    tp = int(np.sum(masked[rows, cols] <= tolerance))
    fp = n_pred - tp
    fn = n_ref - tp
    return f1_score(tp, fp, fn)


def classification_f1(
    predicted_labels: Sequence[Hashable],
    true_labels: Sequence[Hashable],
    *,
    labels: Sequence[Hashable] | None = None,
    average: str = "macro",
) -> PRF:
    """Multiclass precision / recall / F1 for peak classification.

    ``average="micro"`` pools confusion counts across classes (equivalent to
    accuracy for single-label problems); ``average="macro"`` averages the
    per-class F1 unweighted (the default, so rare classes count equally).  The
    returned confusion counts are always the micro (pooled) totals regardless of
    averaging, matching scikit-learn's convention.
    """

    if len(predicted_labels) != len(true_labels):
        raise ValueError("predicted_labels and true_labels must be the same length")
    if not true_labels:
        raise ValueError("classification_f1 requires at least one label")
    if average not in ("macro", "micro"):
        raise ValueError("average must be 'macro' or 'micro'")

    if labels is not None:
        classes = list(labels)
    else:
        classes = sorted(set(true_labels) | set(predicted_labels), key=str)

    micro_tp = micro_fp = micro_fn = 0
    per_class_f1: list[float] = []
    per_class_p: list[float] = []
    per_class_r: list[float] = []
    pairs = list(zip(predicted_labels, true_labels, strict=True))
    for cls in classes:
        tp = sum(1 for p, t in pairs if p == cls and t == cls)
        fp = sum(1 for p, t in pairs if p == cls and t != cls)
        fn = sum(1 for p, t in pairs if p != cls and t == cls)
        micro_tp += tp
        micro_fp += fp
        micro_fn += fn
        prf = f1_score(tp, fp, fn)
        per_class_f1.append(prf.f1)
        per_class_p.append(prf.precision)
        per_class_r.append(prf.recall)

    if average == "micro":
        return f1_score(micro_tp, micro_fp, micro_fn)
    # macro
    precision = float(np.mean(per_class_p)) if per_class_p else 0.0
    recall = float(np.mean(per_class_r)) if per_class_r else 0.0
    f1 = float(np.mean(per_class_f1)) if per_class_f1 else 0.0
    return PRF(precision, recall, f1, micro_tp, micro_fp, micro_fn)


# --------------------------------------------------------------------------- #
# Ranked-retrieval metrics
# --------------------------------------------------------------------------- #
def top_k_accuracy(
    ranked_candidates: Sequence[Sequence[Hashable]],
    targets: Sequence[Hashable],
    k: int,
) -> float:
    """Fraction of queries whose target appears in the first ``k`` candidates.

    ``ranked_candidates[i]`` is the ranked candidate list for query ``i``
    (best first); ``targets[i]`` is that query's correct answer.
    """

    if k < 1:
        raise ValueError("k must be >= 1")
    if len(ranked_candidates) != len(targets):
        raise ValueError("ranked_candidates and targets must be the same length")
    if not targets:
        raise ValueError("top_k_accuracy requires at least one query")
    hits = 0
    for candidates, target in zip(ranked_candidates, targets, strict=True):
        if target in list(candidates)[:k]:
            hits += 1
    return hits / len(targets)


def bedroc(scores: Sequence[float], labels: Sequence[int], *, alpha: float = 20.0) -> float:
    """Boltzmann-Enhanced Discrimination of ROC (Truchon & Bayly, JCIM 2007).

    An early-recognition metric for a single ranked list: actives that rank near
    the top are rewarded far more than actives near the bottom, controlled by
    ``alpha`` (larger ``alpha`` = stronger emphasis on the very top; the JCIM
    paper's default of 20 means ~80% of the score comes from the top ~8%).

    Parameters
    ----------
    scores:
        Predicted scores; higher = predicted more likely to be active.
    labels:
        Binary ground truth aligned with ``scores`` (1 = active, 0 = inactive).
    alpha:
        Early-recognition weighting parameter (must be > 0).

    Returns
    -------
    float
        BEDROC in [0, 1]; 1.0 when all actives are ranked first, ~R_a-dependent
        small value for random ranking.  Implements Eq. (36) of the paper (the
        same closed form used by RDKit / DeepChem).
    """

    if alpha <= 0:
        raise ValueError("alpha must be > 0")
    score_arr = np.asarray(scores, dtype=float)
    label_arr = np.asarray(labels)
    if score_arr.shape != label_arr.shape:
        raise ValueError("scores and labels must be the same length")
    if score_arr.size == 0:
        raise ValueError("bedroc requires at least one observation")
    if not np.all(np.isin(label_arr, (0, 1))):
        raise ValueError("labels must be 0/1")

    big_n = int(score_arr.size)
    n = int(label_arr.sum())
    if n == 0:
        raise ValueError("bedroc is undefined with no actives")
    if n == big_n:
        # Every compound is active -> perfect early recognition by definition.
        return 1.0

    # Rank actives (1-indexed) after sorting by descending score. A stable sort
    # keeps the result deterministic for tied scores.
    order = np.argsort(-score_arr, kind="stable")
    active_ranks = np.nonzero(label_arr[order] == 1)[0] + 1  # 1-indexed positions

    r_a = n / big_n
    sum_exp = float(np.sum(np.exp(-alpha * active_ranks / big_n)))
    random_sum = r_a * (1.0 - math.exp(-alpha)) / (math.exp(alpha / big_n) - 1.0)
    factor = r_a * math.sinh(alpha / 2.0) / (
        math.cosh(alpha / 2.0) - math.cosh(alpha / 2.0 - alpha * r_a)
    )
    constant = 1.0 / (1.0 - math.exp(alpha * (1.0 - r_a)))
    return sum_exp * factor / random_sum + constant


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Bin:
    lower: float
    upper: float
    count: int
    accuracy: float
    confidence: float


def reliability_bins(
    confidences: Sequence[float],
    correct: Sequence[bool],
    *,
    n_bins: int = 10,
) -> list[_Bin]:
    """Per-bin accuracy/confidence for a reliability diagram (equal-width bins).

    Bins partition [0, 1] as ``[0, 1/M], (1/M, 2/M], ..., ((M-1)/M, 1]`` so that
    both confidence 0 and confidence 1 are covered.  Empty bins are returned with
    count 0 and accuracy/confidence 0.0.
    """

    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    conf = np.asarray(confidences, dtype=float)
    corr = np.asarray(correct, dtype=bool)
    if conf.shape != corr.shape:
        raise ValueError("confidences and correct must be the same length")
    if conf.size == 0:
        raise ValueError("calibration requires at least one prediction")
    if np.any(conf < 0.0) or np.any(conf > 1.0):
        raise ValueError("confidences must lie in [0, 1]")

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[_Bin] = []
    for m in range(n_bins):
        lo, hi = float(edges[m]), float(edges[m + 1])
        mask = (conf >= lo) & (conf <= hi) if m == 0 else (conf > lo) & (conf <= hi)
        count = int(np.sum(mask))
        if count:
            accuracy = float(np.mean(corr[mask]))
            confidence = float(np.mean(conf[mask]))
        else:
            accuracy = confidence = 0.0
        bins.append(_Bin(lo, hi, count, accuracy, confidence))
    return bins


def expected_calibration_error(
    confidences: Sequence[float],
    correct: Sequence[bool],
    *,
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error with equal-width binning (Guo et al., ICML 2017).

    ECE = sum_m (|B_m| / N) * |acc(B_m) - conf(B_m)|, the sample-weighted average
    gap between bin accuracy and bin confidence.  0.0 = perfectly calibrated.

    ``confidences`` are the model's predicted probability for its chosen class
    (in [0, 1]); ``correct[i]`` is whether prediction ``i`` was actually right.
    """

    bins = reliability_bins(confidences, correct, n_bins=n_bins)
    total = sum(b.count for b in bins)
    if total == 0:  # pragma: no cover - guarded by reliability_bins
        raise ValueError("calibration requires at least one prediction")
    return float(sum(b.count / total * abs(b.accuracy - b.confidence) for b in bins))
