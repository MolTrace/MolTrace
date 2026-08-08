"""Derive a calibrated-scale confidence from a routed prediction (L0, Part C).

The AI/ML product surface needs one number per prediction. Until now it took that
number from the request body, which meant the platform recorded confidences it had
never computed. This module computes it — and computes it on **the arbiter's own
scale**, so a confidence shown to a user is the same quantity the deterministic
verifier weighs evidence by, not a second, incompatible notion of certainty.

The mapping is :func:`~moltrace.spectroscopy.verification.scorer._significance_from_sigma`
(``significance = 8·σ_ref/(σ_ref + σ)`` with σ_ref = 0.10 ppm ¹H / 2.0 ppm ¹³C)
followed by the scorer's own ``quality = tanh(significance / 3)``. Two consequences
are deliberate:

* A prediction at exactly the reference uncertainty scores **0.870**, not 1.0.
  Perfect confidence would require σ → 0, which no real predictor achieves.
* At the ¹³C uncertainty measured in production before the HOSE knowledge base
  landed (median σ = 35 ppm) this returns **0.143** — an abstention wearing a
  number, correctly reported as such. That is the point: the degradation is now
  *aggregated* rather than left in a per-atom warning string nobody read.

Nothing here decides anything. The verifier remains the sole arbiter of
correctness; this is a reporting scale, and every value it produces travels with
the ``model_versions`` provenance of the prediction it summarises.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

# Single source of truth for the uncertainty → significance mapping: the module
# the arbiter itself uses. Importing it (rather than restating the constants)
# means a change to the arbiter's scale cannot silently desynchronise the number
# shown to users from the number the verifier reasons with.
from moltrace.spectroscopy.verification.scorer import (
    _SIGMA_REF_PPM,
    _significance_from_sigma,
)

__all__ = [
    "PredictionConfidence",
    "confidence_from_sigma",
    "routed_prediction_confidence",
]

#: Median predicted σ (ppm) above which a nucleus is reported as out-of-domain.
#: Derived from the measured distribution, not chosen: DP4's published ¹³C error
#: scale is 2.306 ppm (``dp4_scoring``), and a predictor whose *median* σ exceeds
#: the error model that consumes it cannot discriminate between candidates at all.
#: The ¹H entry is the same ratio applied to that nucleus' reference scale.
OOD_SIGMA_PPM: dict[str, float] = {"13C": 2.306, "1H": 0.115}

#: Share of atoms resolved by the HOSE fallback above which the prediction is
#: reported as ``possible_ood``. Half the atoms is the point at which the routed
#: result is no longer characterised by the layer it nominally ran on.
OOD_FALLBACK_FRACTION = 0.5


@dataclass(frozen=True)
class PredictionConfidence:
    """A routed prediction summarised for the product surface.

    ``score`` is on the verifier's quality scale (0–1). ``uncertainty`` carries the
    distribution behind it, because a single number is not a defensible claim on
    its own — the σ distribution is what a reviewer actually needs.
    """

    score: float
    ood_status: str  # 'in_domain' | 'possible_ood' | 'out_of_domain' | 'not_assessed'
    uncertainty: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)


def confidence_from_sigma(sigma: float, nucleus: str) -> float:
    """One atom's confidence on the arbiter's quality scale.

    Returns 0.0 for a non-finite or non-positive σ: a prediction with no usable
    uncertainty contributes no confidence rather than a default one.
    """

    if sigma is None or not math.isfinite(float(sigma)) or float(sigma) <= 0.0:
        return 0.0
    return float(math.tanh(_significance_from_sigma(float(sigma), nucleus) / 3.0))


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values)) if values else float("nan")


def _percentile(values: Sequence[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    idx = (pct / 100.0) * (len(ordered) - 1)
    lo = int(math.floor(idx))
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return float(ordered[lo] * (1.0 - frac) + ordered[hi] * frac)


def routed_prediction_confidence(routed: Any) -> PredictionConfidence:
    """Summarise a :class:`~moltrace.spectroscopy.ai.router.RoutedPrediction`.

    ``routed`` is duck-typed (``.predictions`` of atoms carrying ``nucleus``,
    ``uncertainty_ppm`` and ``layer``) so this module stays importable without
    pulling the router's transitive dependencies.

    Refusal path first: a prediction with no atoms yields score 0.0 and
    ``not_assessed`` with a warning naming the cause — never a default confidence.
    """

    atoms = tuple(getattr(routed, "predictions", ()) or ())
    warnings: list[str] = []
    if not atoms:
        return PredictionConfidence(
            score=0.0,
            ood_status="not_assessed",
            uncertainty={"n_atoms": 0},
            warnings=("prediction produced no atoms; confidence not assessed",),
        )

    per_nucleus_sigma: dict[str, list[float]] = {}
    qualities: list[float] = []
    fallback_atoms = 0
    layer_counts: dict[str, int] = {}

    for atom in atoms:
        nucleus = str(getattr(atom, "nucleus", "1H"))
        sigma = float(getattr(atom, "uncertainty_ppm", float("nan")))
        layer = str(getattr(getattr(atom, "layer", ""), "value", getattr(atom, "layer", "")))
        layer_counts[layer] = layer_counts.get(layer, 0) + 1
        if "hose" in layer:
            fallback_atoms += 1
        qualities.append(confidence_from_sigma(sigma, nucleus))
        if math.isfinite(sigma):
            per_nucleus_sigma.setdefault(nucleus, []).append(sigma)

    n_atoms = len(atoms)
    non_finite = n_atoms - sum(len(v) for v in per_nucleus_sigma.values())
    if non_finite:
        warnings.append(
            f"{non_finite} of {n_atoms} atoms reported no usable uncertainty "
            "(single conformer); they contribute zero confidence"
        )

    sigma_summary: dict[str, Any] = {}
    ood_nuclei: list[str] = []
    for nucleus, sigmas in sorted(per_nucleus_sigma.items()):
        median = _median(sigmas)
        sigma_summary[nucleus] = {
            "n": len(sigmas),
            "median_sigma_ppm": round(median, 4),
            "p90_sigma_ppm": round(_percentile(sigmas, 90.0), 4),
            "reference_sigma_ppm": _SIGMA_REF_PPM.get(nucleus),
        }
        threshold = OOD_SIGMA_PPM.get(nucleus)
        if threshold is not None and math.isfinite(median) and median > threshold:
            ood_nuclei.append(nucleus)
            warnings.append(
                f"{nucleus} median predicted uncertainty {median:.2f} ppm exceeds the "
                f"{threshold} ppm error-model scale that consumes it; this prediction "
                "cannot discriminate between candidates"
            )

    fallback_fraction = fallback_atoms / n_atoms
    if fallback_fraction > OOD_FALLBACK_FRACTION:
        warnings.append(
            f"{fallback_fraction:.0%} of atoms resolved through the HOSE fallback "
            "rather than the routed layer"
        )

    if ood_nuclei:
        ood_status = "out_of_domain"
    elif fallback_fraction > OOD_FALLBACK_FRACTION:
        ood_status = "possible_ood"
    else:
        ood_status = "in_domain"

    uncertainty = {
        "n_atoms": n_atoms,
        "per_nucleus": sigma_summary,
        "fallback_fraction": round(fallback_fraction, 4),
        "layer_counts": dict(sorted(layer_counts.items())),
        "scale": "verifier_quality",
    }
    return PredictionConfidence(
        score=round(sum(qualities) / n_atoms, 6),
        ood_status=ood_status,
        uncertainty=uncertainty,
        warnings=tuple(warnings) + tuple(getattr(routed, "warnings", ()) or ()),
    )
