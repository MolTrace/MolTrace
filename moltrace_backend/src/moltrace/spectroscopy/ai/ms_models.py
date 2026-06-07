"""MS / structure-ranking pretrained models (Prompt 21, Phase 1 MS side).

Prompt 6 covers the NMR shift predictor. This module completes the Phase-1
pretrained-foundation layer with the MS/MS and candidate-ranking models a
combined NMR/MS product needs, fusing orthogonal evidence into one calibrated
candidate ranking — which the **independent** Prompt 7 verifier
(:func:`moltrace.spectroscopy.verification.verify_structure`) then arbitrates.

1. **CSI:FingerID** (MS/MS -> structure). :func:`predict_msms_candidates` wraps
   SIRIUS / CSI:FingerID through its *documented* interface (a configured REST
   service or CLI binary); it does **not** reimplement or bundle SIRIUS, and
   respects its licence/terms. The backend is injectable (and absent on a
   plain CPU-only host, where the wrapper returns ``available=False`` rather than
   failing). Refs: Dührkop et al., *PNAS* 2015 (CSI:FingerID); Dührkop et al.,
   *Nat. Methods* 2019 (SIRIUS 4).

2. **METLIN retention-time corroboration.** :func:`predict_retention_times`
   (pluggable predictor) + :func:`rt_corroboration` — a candidate whose predicted
   RT is inconsistent with the observed RT is **down-weighted**, an orthogonal
   corroboration signal, never a hard filter.

3. **DP4-AI candidate ranking.** :func:`dp4_candidate_posterior` **reuses** the
   existing, validated DP4 implementation (``nmrcheck.dp4_scoring`` — Smith &
   Goodman 2010 σ/ν) to return a calibrated posterior over NMR candidates. We
   integrate the in-house DP4 rather than reimplementing it.

:func:`fuse_candidates` combines NMR (DP4) + MS/MS (CSI:FingerID) + RT into one
calibrated ranking (RT as a multiplicative down-weight); the output is candidates
+ scores **only** — decision-support. Each model is registered in the Prompt 13
registry (:func:`register_ms_models`) with version + SHA-256. Device strategy
mirrors Prompt 6 (``PYTORCH_ENABLE_MPS_FALLBACK=1``; MPS -> CPU) for any local
PyTorch model.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from moltrace.spectroscopy.ai.registry import (
    ModelEntry,
    ModelRegistry,
    ModelRole,
    TrainingDataLineage,
)
from moltrace.spectroscopy.infra.contract import content_hash

# Parity with Prompt 6: allow torch ops unimplemented on MPS to fall back to CPU.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

__all__ = [
    "CSIFingerIDUnavailable",
    "CandidatePosterior",
    "FingerIDResult",
    "MSCandidate",
    "MSModelsError",
    "MSMSSpectrum",
    "NMRCandidate",
    "RankedCandidate",
    "arbitrate",
    "dp4_candidate_posterior",
    "fuse_candidates",
    "predict_msms_candidates",
    "predict_retention_times",
    "register_ms_models",
    "rt_corroboration",
]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class MSModelsError(RuntimeError):
    """Base class for MS-models errors."""


class CSIFingerIDUnavailable(MSModelsError):
    """Raised when CSI:FingerID is required but no backend is configured."""


# --------------------------------------------------------------------------- #
# Inputs / records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MSMSSpectrum:
    """An MS/MS spectrum to elucidate."""

    peaks: tuple[tuple[float, float], ...]  # (m/z, intensity)
    precursor_mz: float | None = None
    adduct: str = "[M+H]+"
    ionization: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MSCandidate:
    """A structure candidate proposed by an MS/MS -> structure model."""

    smiles: str
    score: float  # model score (higher = better); scale is model-specific
    source: str = "csi_fingerid"
    inchikey: str | None = None
    rank: int = 0


@dataclass(frozen=True)
class FingerIDResult:
    """CSI:FingerID output: ranked candidates (+ optional fingerprint)."""

    available: bool
    candidates: tuple[MSCandidate, ...]
    backend: str
    model_version: str | None = None
    fingerprint: tuple[float, ...] | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class NMRCandidate:
    """A candidate structure with predicted shifts for one nucleus (DP4 input)."""

    candidate_id: str
    predicted_shifts_ppm: tuple[float, ...]
    smiles: str | None = None


@dataclass(frozen=True)
class CandidatePosterior:
    """A candidate's DP4 posterior (reuses the in-house dp4_scoring)."""

    candidate_id: str
    smiles: str | None
    dp4_probability: float
    matched_peaks: int
    mae_ppm: float
    rms_ppm: float
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RankedCandidate:
    """A fused, calibrated candidate ranking (decision-support only)."""

    candidate_id: str
    smiles: str | None
    combined_score: float  # calibrated: sums to 1.0 across the returned candidates
    signals: Mapping[str, float]  # per-signal contributions (nmr_dp4, msms, rt_corroboration)
    rank: int
    notes: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# 1. CSI:FingerID (MS/MS -> structure) -- licence-respecting wrapper
# --------------------------------------------------------------------------- #
CSIBackend = Callable[[MSMSSpectrum], Sequence[Any]]


def _resolve_csi_backend() -> tuple[CSIBackend | None, str]:
    """Resolve a CSI:FingerID backend from the environment, or ``(None, ...)``.

    Honours ``MOLTRACE_SIRIUS_REST_URL`` (a running SIRIUS REST service) or
    ``MOLTRACE_SIRIUS_BINARY`` (a local SIRIUS CLI). We call SIRIUS through its
    documented interface only -- never reimplementing or bundling it -- so the
    operator supplies their own licence-compliant install / login.
    """

    rest = os.environ.get("MOLTRACE_SIRIUS_REST_URL")
    if rest:  # pragma: no cover - requires a running SIRIUS service
        return _sirius_rest_backend(rest), f"sirius-rest:{rest}"
    binary = os.environ.get("MOLTRACE_SIRIUS_BINARY")
    if binary:  # pragma: no cover - requires a local SIRIUS install
        return _sirius_cli_backend(binary), f"sirius-cli:{binary}"
    return None, "none"


def _sirius_rest_backend(url: str) -> CSIBackend:  # pragma: no cover - network I/O
    raise CSIFingerIDUnavailable(
        "SIRIUS REST integration is configured but not implemented in this build; "
        "inject a backend= callable or wire the documented SIRIUS REST endpoint."
    )


def _sirius_cli_backend(binary: str) -> CSIBackend:  # pragma: no cover - subprocess
    raise CSIFingerIDUnavailable(
        "SIRIUS CLI integration is configured but not implemented in this build; "
        "inject a backend= callable or wire the documented SIRIUS CLI."
    )


def _to_candidate(item: Any, source: str) -> MSCandidate:
    if isinstance(item, MSCandidate):
        return item
    smiles, score = item[0], item[1]
    return MSCandidate(smiles=str(smiles), score=float(score), source=source)


def predict_msms_candidates(
    spectrum: MSMSSpectrum,
    *,
    backend: CSIBackend | None = None,
    top_k: int = 10,
    model_version: str | None = None,
) -> FingerIDResult:
    """Run CSI:FingerID on an MS/MS spectrum -> ranked candidate structures.

    ``backend`` is a callable ``MSMSSpectrum -> [(smiles, score), ...]`` (or
    ``[MSCandidate, ...]``); when ``None`` it is resolved from the environment.
    On a host with no configured/usable backend the result is
    ``available=False`` (graceful on a CPU-only host) rather than an exception.
    """

    resolved = backend
    backend_name = "injected"
    if resolved is None:
        resolved, backend_name = _resolve_csi_backend()
    if resolved is None:
        return FingerIDResult(
            available=False,
            candidates=(),
            backend=backend_name,
            warnings=(
                "CSI:FingerID backend not configured; set MOLTRACE_SIRIUS_REST_URL / "
                "MOLTRACE_SIRIUS_BINARY or pass backend=.",
            ),
        )

    raw = list(resolved(spectrum))
    candidates = [_to_candidate(item, "csi_fingerid") for item in raw]
    candidates.sort(key=lambda c: c.score, reverse=True)
    ranked = tuple(
        MSCandidate(c.smiles, c.score, c.source, _inchikey(c.smiles, c.inchikey), rank=i + 1)
        for i, c in enumerate(candidates[: max(0, top_k)])
    )
    return FingerIDResult(
        available=True, candidates=ranked, backend=backend_name, model_version=model_version
    )


def _inchikey(smiles: str, existing: str | None) -> str | None:
    if existing:
        return existing
    try:
        from rdkit import Chem, RDLogger

        RDLogger.DisableLog("rdApp.*")
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return Chem.InchiToInchiKey(Chem.MolToInchi(mol)) or None
    except Exception:  # pragma: no cover - rdkit is core; defensive only
        return None


# --------------------------------------------------------------------------- #
# 2. METLIN retention-time corroboration
# --------------------------------------------------------------------------- #
RTPredictor = Callable[[str], float]


def predict_retention_times(
    candidates: Mapping[str, str],
    *,
    predictor: RTPredictor | None = None,
) -> dict[str, float | None]:
    """Predict retention time (min) for each candidate ``{id: smiles}``.

    ``predictor`` is a pluggable METLIN-style model ``smiles -> RT``; when absent
    every RT is ``None`` (corroboration then abstains). Per-candidate failures
    degrade to ``None`` rather than aborting the batch.
    """

    out: dict[str, float | None] = {}
    for cid, smiles in candidates.items():
        if predictor is None:
            out[cid] = None
            continue
        try:
            out[cid] = float(predictor(smiles))
        except Exception:  # pragma: no cover - predictor robustness
            out[cid] = None
    return out


def rt_corroboration(
    candidate_rts: Mapping[str, float | None],
    observed_rt: float | None,
    *,
    tolerance_min: float = 0.5,
) -> dict[str, float]:
    """Down-weight candidates whose predicted RT is inconsistent with ``observed_rt``.

    Returns a multiplicative weight in ``(0, 1]`` per candidate: a Gaussian in the
    RT residual (1.0 at a perfect match, decaying with ``tolerance_min``). When
    the observed RT or a candidate's predicted RT is unknown, the weight is 1.0
    (neutral — corroboration abstains, never invents penalties).
    """

    tol = max(float(tolerance_min), 1e-6)
    weights: dict[str, float] = {}
    for cid, predicted in candidate_rts.items():
        if observed_rt is None or predicted is None:
            weights[cid] = 1.0
            continue
        z = (float(predicted) - float(observed_rt)) / tol
        weights[cid] = math.exp(-0.5 * z * z)
    return weights


# --------------------------------------------------------------------------- #
# 3. DP4-AI candidate posterior -- REUSES the in-house dp4_scoring
# --------------------------------------------------------------------------- #
def dp4_candidate_posterior(
    *,
    observed_shifts_ppm: Sequence[float],
    candidates: Sequence[NMRCandidate],
    nucleus: str,
    pairing_tolerance_ppm: float | None = None,
) -> list[CandidatePosterior]:
    """Calibrated DP4 posterior over NMR candidates (reuses ``nmrcheck.dp4_scoring``).

    Delegates to the validated, in-house ``dp4_probabilities`` (Smith & Goodman
    2010 σ/ν); the returned probabilities sum to 1.0 across candidates.
    """

    from nmrcheck.dp4_scoring import dp4_probabilities  # local import: avoids cycle

    if not candidates:
        return []
    scores = dp4_probabilities(
        observed_shifts_ppm=list(observed_shifts_ppm),
        candidate_predicted_shifts_ppm=[list(c.predicted_shifts_ppm) for c in candidates],
        nucleus=nucleus,  # type: ignore[arg-type]
        pairing_tolerance_ppm=pairing_tolerance_ppm,
    )
    out: list[CandidatePosterior] = []
    for score in scores:
        cand = candidates[score.candidate_index]
        out.append(
            CandidatePosterior(
                candidate_id=cand.candidate_id,
                smiles=cand.smiles,
                dp4_probability=float(score.probability),
                matched_peaks=int(score.matched_peaks),
                mae_ppm=float(score.mean_abs_error_ppm),
                rms_ppm=float(score.rms_error_ppm),
                notes=tuple(score.notes),
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Fusion: NMR (DP4) + MS/MS (CSI) + RT -> one calibrated ranking
# --------------------------------------------------------------------------- #
_DEFAULT_SIGNAL_WEIGHTS = {"nmr_dp4": 0.5, "msms": 0.5}


def _minmax_normalise(values: Mapping[str, float]) -> dict[str, float]:
    """Map scores to [0, 1] (best -> 1). Equal scores -> all 1.0."""

    if not values:
        return {}
    lo = min(values.values())
    hi = max(values.values())
    if hi - lo < 1e-12:
        return {k: 1.0 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def fuse_candidates(
    *,
    dp4: Mapping[str, float] | None = None,
    msms: Mapping[str, float] | None = None,
    rt_weights: Mapping[str, float] | None = None,
    smiles: Mapping[str, str] | None = None,
    weights: Mapping[str, float] | None = None,
) -> list[RankedCandidate]:
    """Fuse orthogonal signals into one calibrated candidate ranking.

    ``dp4`` (a calibrated posterior) and ``msms`` (CSI scores, min-max normalised
    to a relative [0,1]) are combined by a weighted mean over the signals present
    for each candidate (weights renormalised when a signal is missing). ``rt_weights``
    multiply the result (RT corroboration is a down-weight, never a hard filter).
    The combined scores are normalised to sum to 1.0 across candidates.

    Output is candidates + scores only — decision-support. The Prompt 7 verifier
    remains the arbiter of pass/fail (:func:`arbitrate`).
    """

    if not dp4 and not msms:
        raise MSModelsError("fuse_candidates needs at least one of dp4= or msms=")
    sig_weights = {**_DEFAULT_SIGNAL_WEIGHTS, **(dict(weights) if weights else {})}
    msms_norm = _minmax_normalise(msms or {})
    ids = sorted(set(dp4 or {}) | set(msms or {}))

    raw: dict[str, float] = {}
    breakdown: dict[str, dict[str, float]] = {}
    for cid in ids:
        present: dict[str, float] = {}
        if dp4 is not None and cid in dp4:
            present["nmr_dp4"] = float(dp4[cid])
        if cid in msms_norm:
            present["msms"] = float(msms_norm[cid])
        wsum = sum(sig_weights.get(s, 0.0) for s in present) or 1.0
        base = sum(sig_weights.get(s, 0.0) * val for s, val in present.items()) / wsum
        rt_w = float(rt_weights.get(cid, 1.0)) if rt_weights else 1.0
        raw[cid] = base * rt_w
        breakdown[cid] = {**present, "rt_corroboration": rt_w}

    total = sum(raw.values())
    ranked = sorted(ids, key=lambda c: raw[c], reverse=True)
    out: list[RankedCandidate] = []
    for i, cid in enumerate(ranked):
        combined = (raw[cid] / total) if total > 0 else 0.0
        out.append(
            RankedCandidate(
                candidate_id=cid,
                smiles=(smiles or {}).get(cid),
                combined_score=combined,
                signals=breakdown[cid],
                rank=i + 1,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Verifier handoff -- the Prompt 7 verifier remains the arbiter
# --------------------------------------------------------------------------- #
def _default_verifier(spectrum: Any, smiles: str, **kwargs: Any) -> Any:
    from moltrace.spectroscopy.verification.scorer import verify_structure

    return verify_structure(spectrum, smiles, **kwargs)


def arbitrate(
    spectrum: Any,
    candidate_smiles: str,
    *,
    prior_confidence: float = 0.5,
    options: Any = None,
    verifier: Callable[..., Any] | None = None,
) -> Any:
    """Hand a (fused) top candidate to the Prompt 7 verifier — the arbiter.

    The fused ranking is decision-support; the deterministic verifier
    (:func:`moltrace.spectroscopy.verification.verify_structure`) makes the
    authoritative pass/fail call. ``verifier`` is injectable for testing.
    """

    verify = verifier or _default_verifier
    return verify(spectrum, candidate_smiles, prior_confidence=prior_confidence, options=options)


# --------------------------------------------------------------------------- #
# Prompt 13 registry integration
# --------------------------------------------------------------------------- #
def _external_lineage(source: str, note: str) -> TrainingDataLineage:
    return TrainingDataLineage(
        dataset_snapshot_hash=f"external:{source}",
        row_count=0,
        source=source,
        notes=note,
    )


def register_ms_models(
    registry: ModelRegistry,
    *,
    csi_version: str,
    csi_sha256: str,
    rt_version: str,
    rt_sha256: str,
    dp4_version: str = "dp4-smith-goodman-2010",
    dp4_sha256: str | None = None,
    promote: bool = False,
) -> dict[ModelRole, ModelEntry]:
    """Register the three MS / ranking models in the Prompt 13 registry.

    Each entry carries a semantic version + SHA-256 (CSI:FingerID and METLIN-RT
    are external pretrained artifacts; DP4-AI is the in-house ``dp4_scoring`` code,
    addressed by a deterministic content hash of its parameters). When
    ``promote`` is set the entries are promoted to ``production``.
    """

    if dp4_sha256 is None:
        dp4_sha256 = content_hash({"dp4": dp4_version, "method": "smith_goodman_2010_t_dist"})

    specs = [
        (ModelRole.CSI_FINGERID, csi_version, csi_sha256, "csi_fingerid",
         "SIRIUS / CSI:FingerID pretrained (Dührkop et al.)"),
        (ModelRole.RT_PREDICTOR, rt_version, rt_sha256, "metlin",
         "METLIN-style retention-time predictor"),
        (ModelRole.DP4_RANKER, dp4_version, dp4_sha256, "dp4_scoring",
         "in-house DP4 (Smith & Goodman 2010); reused, not retrained"),
    ]
    out: dict[ModelRole, ModelEntry] = {}
    for role, version, sha, source, note in specs:
        entry = registry.register_artifact(
            role=role,
            semantic_version=version,
            artifact_sha256=sha,
            training_data_lineage=_external_lineage(source, note),
        )
        if promote:
            registry.promote(entry.model_id)
        out[role] = entry
    return out
