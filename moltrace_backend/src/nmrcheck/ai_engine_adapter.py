"""The single import boundary between the API layer and the MolTrace AI/ML layer.

Before this module existed, `moltrace.spectroscopy.ai` — the inference router, the
model registry, the evaluation harness — was reachable from exactly one HTTP route,
while 76 AI/ML routes recorded model behaviour that no model had produced:
``ai_inference_store._extract_confidence`` read ``confidence_score`` out of the
*request body*, and fell back to a hard-coded ``0.82`` when the caller omitted it.
The governance surface was correct and audit-grade; it simply had nothing under it.

This module is the wire. Three rules, in priority order:

1. **Fail loud, degrade recorded.** When an engine cannot run, this module raises
   :class:`EngineUnavailable`. It never substitutes a caller-supplied number for a
   computed one, and it never invents one — that is the failure mode it exists to end.
2. **Provenance is mandatory.** Every :class:`EngineResult` carries the
   ``model_versions`` map of everything that touched the number: each component
   keyed by name, mapped to the version it ran at — a registry artifact's SHA-256
   on the routed-prediction path, a pinned method tag for a published algorithm
   (DP4 reports ``{"dp4_scoring": "smith_goodman_2010"}``). A result with an empty
   map is rejected here, not stored with a gap.
3. **Lazy import.** ``moltrace.spectroscopy.ai`` pulls RDKit and optionally torch.
   Everything is imported inside the function that needs it, so the ~800-route app
   still builds in environments without the ML extras.

The stores stay free of ``moltrace`` imports: they receive results, never engines.
This module owns no science — the confidence scale lives in
:mod:`moltrace.spectroscopy.ai.confidence`, the promotion rule in
:mod:`moltrace.spectroscopy.eval.harness`. It only carries values across the seam.
"""

from __future__ import annotations

import math
import weakref
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "MODEL_DERIVED_REQUEST_KEYS",
    "DominanceVerdict",
    "EngineInputError",
    "EngineResult",
    "EngineUnavailable",
    "PromotionRecord",
    "RegistryView",
    "assert_no_model_derived_inputs",
    "dominance_verdict",
    "engine_backed_services",
    "is_engine_backed",
    "promote_to_serving",
    "registry_views",
    "run_prediction",
]


class EngineError(RuntimeError):
    """Base class for every failure crossing the seam."""


class EngineUnavailable(EngineError):
    """The engine could not be run (missing dependency, no registered artifact).

    Callers must surface this as a failure. Falling back to a caller-supplied
    number would reintroduce exactly the defect this module removes.
    """


class EngineInputError(EngineError):
    """The request lacks an input the engine needs, or supplies one it must compute itself."""


#: Keys a caller may **not** supply for an engine-backed service: each one is a
#: number the engine derives. Accepting them would let a client dictate the
#: confidence, the uncertainty or the domain assessment recorded against a model.
MODEL_DERIVED_REQUEST_KEYS: frozenset[str] = frozenset(
    {
        "confidence_score",
        "mock_confidence_score",
        "score",
        "uncertainty_json",
        "ood_status",
        "model_versions",
    }
)

#: Service keys this adapter can actually execute. A service absent from this map
#: is not engine-backed *yet*; its predictions are recorded with no confidence and
#: a warning naming the cause, rather than with a fabricated one.
_RUNNERS: dict[str, str] = {
    "nmr_shift_prediction": "_run_shift_prediction",
    "nmr_candidate_ranking": "_run_candidate_ranking",
}


@dataclass(frozen=True)
class EngineResult:
    """One engine execution, with everything the product surface needs to record it."""

    output: dict[str, Any]
    #: ``None`` when the engine ran but the result does not support a confidence —
    #: an abstention, never a default. A number here was computed, not assumed.
    confidence: float | None
    uncertainty: dict[str, Any]
    ood_status: str
    model_versions: dict[str, str]
    engine: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DominanceVerdict:
    """The promotion decision for a deployment candidate, and why.

    ``applicable`` separates "this gate says no" from "this gate has no opinion".
    The ML factory serves several task families — a reaction-yield surrogate is not
    scored on ``false_confirmation_rate``, which is a structure-verification metric —
    so a gate that cannot compare must stand aside and say so, not refuse. A gate
    that refuses everything it does not understand is a gate teams route around.
    """

    passed: bool
    applicable: bool
    reason: str
    compared_metrics: tuple[str, ...]
    regressions: tuple[str, ...]
    improvements: tuple[str, ...]


def engine_backed_services() -> frozenset[str]:
    """Service keys this adapter can execute."""

    return frozenset(_RUNNERS)


def is_engine_backed(service_key: str) -> bool:
    return service_key in _RUNNERS


def assert_no_model_derived_inputs(service_key: str, request_json: Mapping[str, Any]) -> None:
    """Refuse a request that supplies a number the engine is responsible for computing.

    Only enforced for engine-backed services: for the rest there is nothing to
    contradict yet, and rejecting the key would break existing callers without
    making any recorded number more trustworthy.
    """

    if not is_engine_backed(service_key):
        return
    supplied = sorted(MODEL_DERIVED_REQUEST_KEYS.intersection(request_json))
    if supplied:
        raise EngineInputError(
            f"{', '.join(supplied)} cannot be supplied for {service_key!r} — these are "
            "derived by the prediction engine, and a submitted value would be recorded "
            "as if the model had produced it."
        )


def run_prediction(
    service_key: str,
    request_json: Mapping[str, Any],
    *,
    session_factory: Any = None,
) -> EngineResult:
    """Execute ``service_key`` against ``request_json`` and return a complete result.

    ``session_factory`` is the app's session maker; the model registry is resolved
    from its bound engine so a routed prediction's provenance points at the same
    artifacts the product surface lists. Omit it and the registry falls back to an
    empty in-memory store — the prediction still runs and still records explicit
    ``unregistered:*`` provenance markers rather than pretending it was registered.

    Raises :class:`EngineInputError` for a bad request, :class:`EngineUnavailable`
    when the engine cannot run, and :class:`KeyError` for a service that is not
    engine-backed (guard with :func:`is_engine_backed` first).
    """

    runner = _RUNNERS[service_key]
    result: EngineResult = globals()[runner](request_json, session_factory)
    if not result.model_versions:
        raise EngineUnavailable(
            f"{service_key!r} produced a result with no model provenance; refusing to "
            "record a number that cannot be traced to an artifact."
        )
    return result


# --------------------------------------------------------------------------- #
# Runners
# --------------------------------------------------------------------------- #
def _run_shift_prediction(
    request_json: Mapping[str, Any], session_factory: Any = None
) -> EngineResult:
    """Route a shift prediction through the 3-layer :class:`InferenceRouter`."""

    smiles = request_json.get("smiles")
    if not isinstance(smiles, str) or not smiles.strip():
        raise EngineInputError("nmr_shift_prediction requires a non-empty 'smiles' string.")

    nuclei_raw = request_json.get("nuclei", ["1H", "13C"])
    if not isinstance(nuclei_raw, list) or not all(isinstance(n, str) for n in nuclei_raw):
        raise EngineInputError("'nuclei' must be a list of nucleus strings, e.g. ['1H', '13C'].")
    nuclei = tuple(nuclei_raw) or ("1H", "13C")

    try:
        from moltrace.spectroscopy.ai.confidence import routed_prediction_confidence
        from moltrace.spectroscopy.ai.registry import ModelRegistry
        from moltrace.spectroscopy.ai.router import InferenceRouter
    except ImportError as exc:  # pragma: no cover - exercised only without the ML extras
        raise EngineUnavailable(f"the shift-prediction engine is not installed: {exc}") from exc

    router = InferenceRouter(ModelRegistry(_registry_store(session_factory)))
    try:
        routed = router.predict_shifts_routed(smiles, nuclei)
    except Exception as exc:  # noqa: BLE001 - any engine failure is an engine failure
        raise EngineUnavailable(f"shift prediction failed: {exc}") from exc

    summary = routed_prediction_confidence(routed)
    output = {
        "smiles": routed.smiles,
        "nuclei": list(routed.nuclei),
        "base_method": routed.base_method,
        "device": routed.device,
        "layers_used": [str(layer) for layer in routed.layers_used],
        "shifts": [
            {
                "atom_index": p.atom_index,
                "element": p.element,
                "nucleus": p.nucleus,
                "predicted_ppm": p.predicted_ppm,
                "uncertainty_ppm": p.uncertainty_ppm,
                "layer": str(p.layer),
                "model_id": p.model_id,
                "reason": p.reason,
            }
            for p in routed.predictions
        ],
    }
    return EngineResult(
        output=output,
        confidence=summary.score,
        uncertainty=summary.uncertainty,
        ood_status=summary.ood_status,
        model_versions=dict(routed.model_versions),
        engine="moltrace.spectroscopy.ai.router.InferenceRouter",
        warnings=summary.warnings,
        notes=(
            "Confidence is on the deterministic verifier's quality scale; it summarises "
            "predicted uncertainty and is not a probability that the structure is correct.",
        ),
    )


def _run_candidate_ranking(
    request_json: Mapping[str, Any], session_factory: Any = None
) -> EngineResult:
    """Rank candidates by DP4 posterior, reusing the validated in-house implementation."""

    observed = request_json.get("observed_shifts_ppm")
    raw_candidates = request_json.get("candidates")
    nucleus = request_json.get("nucleus", "13C")

    if not isinstance(observed, list) or not observed:
        raise EngineInputError(
            "nmr_candidate_ranking requires a non-empty 'observed_shifts_ppm' list."
        )
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise EngineInputError("nmr_candidate_ranking requires a non-empty 'candidates' list.")
    if nucleus not in {"1H", "13C"}:
        raise EngineInputError("'nucleus' must be '1H' or '13C'.")

    try:
        from moltrace.spectroscopy.ai.ms_models import NMRCandidate, dp4_candidate_posterior
    except ImportError as exc:  # pragma: no cover - exercised only without the ML extras
        raise EngineUnavailable(f"the candidate-ranking engine is not installed: {exc}") from exc

    candidates = []
    for index, raw in enumerate(raw_candidates):
        if not isinstance(raw, dict):
            raise EngineInputError(f"candidate {index} is not an object.")
        shifts = raw.get("predicted_shifts_ppm")
        if not isinstance(shifts, list) or not shifts:
            raise EngineInputError(f"candidate {index} has no 'predicted_shifts_ppm'.")
        candidates.append(
            NMRCandidate(
                candidate_id=str(raw.get("candidate_id", index)),
                predicted_shifts_ppm=tuple(float(s) for s in shifts),
                smiles=raw.get("smiles"),
            )
        )

    try:
        posteriors = dp4_candidate_posterior(
            observed_shifts_ppm=[float(v) for v in observed],
            candidates=candidates,
            nucleus=str(nucleus),
        )
    except Exception as exc:  # noqa: BLE001
        raise EngineUnavailable(f"candidate ranking failed: {exc}") from exc

    if not posteriors:
        raise EngineUnavailable("candidate ranking produced no posteriors.")

    ranked = sorted(posteriors, key=lambda p: p.dp4_probability, reverse=True)
    top = ranked[0]

    # DP4 distributes probability *across* the candidate set, so a set of one always
    # scores 1.0 -- an arithmetic identity, not evidence. Reporting it as confidence
    # would put a maximum-certainty number above every review threshold on the
    # strength of having nothing to compare against. The fit statistics still stand.
    single_candidate = len(ranked) < 2
    confidence: float | None = None if single_candidate else float(top.dp4_probability)
    caveats = [
        "DP4 is a closed-world posterior: it distributes probability across the "
        "candidates supplied and assumes the correct structure is among them. It is "
        "not evidence that the candidate set is exhaustive.",
    ]
    if single_candidate:
        caveats.append(
            "Only one candidate was supplied, so the posterior is 1.0 by construction "
            "and carries no confidence. Judge the fit by the reported deviations, or "
            "supply the alternatives this candidate should be discriminated against."
        )

    return EngineResult(
        output={
            "nucleus": nucleus,
            "candidates": [
                {
                    "candidate_id": p.candidate_id,
                    "smiles": p.smiles,
                    "dp4_probability": p.dp4_probability,
                    "matched_peaks": p.matched_peaks,
                    "mae_ppm": p.mae_ppm,
                    "rms_ppm": p.rms_ppm,
                    "notes": list(p.notes),
                }
                for p in ranked
            ],
        },
        confidence=confidence,
        uncertainty={
            "matched_peaks": top.matched_peaks,
            "mae_ppm": top.mae_ppm,
            "rms_ppm": top.rms_ppm,
            "n_candidates": len(ranked),
            "scale": "dp4_posterior",
        },
        ood_status="not_assessed",
        model_versions={"dp4_scoring": "smith_goodman_2010"},
        engine="moltrace.spectroscopy.ai.ms_models.dp4_candidate_posterior",
        warnings=tuple(caveats),
        notes=(
            "Ranking is advisory. The deterministic verifier remains the arbiter of "
            "whether a structure is confirmed.",
        ),
    )


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
# Keyed by the engine *object*, not its id(): the test suite swaps a fresh engine onto
# the app per test, and an id() key can be handed out again after the old engine is
# collected — which would return a store bound to a dead engine.
_REGISTRY_STORES: MutableMapping[Any, Any] = weakref.WeakKeyDictionary()


@dataclass(frozen=True)
class PromotionRecord:
    """The outcome of promoting an artifact to serving in the science registry."""

    model_id: str
    role: str
    nucleus: str | None
    semantic_version: str
    artifact_sha256: str
    superseded_model_id: str | None
    registered: bool  # False when the entry already existed and was only promoted


@dataclass(frozen=True)
class RegistryView:
    """A registry entry's product-facing facts, for one artifact."""

    model_id: str
    status: str
    role: str
    nucleus: str | None


def promote_to_serving(
    *,
    session_factory: Any,
    role: str,
    semantic_version: str,
    artifact_sha256: str,
    dataset_snapshot_hash: str,
    dataset_row_count: int,
    nucleus: str | None = None,
    dataset_tag: str | None = None,
    dataset_source: str | None = None,
    confidence_band_ppm: float | None = None,
    reason: str | None = None,
) -> PromotionRecord:
    """Register (if needed) and promote an artifact to ``production`` in the registry.

    This is what makes the inference router resolve the artifact: it resolves on
    (role, nucleus) among entries whose *current* status is production, and promoting
    one auto-retires the incumbent as an appended event. Re-promoting an entry that is
    already production is refused by the registry's transition rules, and that refusal
    is surfaced rather than swallowed — silently accepting it would report a promotion
    that did not happen.

    A durable store is required. Promoting into an in-memory registry would report
    success and change nothing about what serves traffic, which is the exact class of
    defect this whole seam exists to remove.
    """

    from moltrace.spectroscopy.ai.registry import (
        InMemoryRegistryStore,
        ModelRegistry,
        ModelRole,
        ModelStatus,
        RegistryError,
        TrainingDataLineage,
        build_model_entry,
    )

    store = _registry_store(session_factory)
    if isinstance(store, InMemoryRegistryStore):
        raise EngineUnavailable(
            "the model registry has no durable store on this deployment, so promoting "
            "an artifact would not change what serves predictions"
        )

    try:
        model_role = ModelRole(role)
    except ValueError as exc:
        raise EngineInputError(f"{role!r} is not a model role the router resolves") from exc

    registry = ModelRegistry(store)
    entry = build_model_entry(
        role=model_role,
        semantic_version=semantic_version,
        artifact_sha256=artifact_sha256,
        training_data_lineage=TrainingDataLineage(
            dataset_snapshot_hash=dataset_snapshot_hash,
            row_count=int(dataset_row_count),
            dataset_tag=dataset_tag,
            source=dataset_source,
        ),
        nucleus=nucleus,
        confidence_band_ppm=confidence_band_ppm,
    )

    incumbent = registry.resolve(model_role, nucleus)
    existing = store.get_entry(entry.model_id)
    registered = False
    if existing is None:
        registry.register(entry)
        registered = True
    elif existing.artifact_sha256 != artifact_sha256:
        # The registry is append-only precisely so this cannot be papered over: the
        # same version pointing at different bytes means one of the two is not what
        # was reviewed.
        raise EngineInputError(
            f"{entry.model_id!r} is already registered against a different artifact "
            "hash; register a new semantic version rather than reusing this one"
        )

    try:
        registry.promote(entry.model_id, reason=reason)
    except RegistryError as exc:
        raise EngineInputError(str(exc)) from exc

    superseded = (
        incumbent.model_id
        if incumbent is not None and incumbent.model_id != entry.model_id
        else None
    )
    assert registry.current_status(entry.model_id) is ModelStatus.PRODUCTION
    return PromotionRecord(
        model_id=entry.model_id,
        role=model_role.value,
        nucleus=nucleus,
        semantic_version=semantic_version,
        artifact_sha256=artifact_sha256,
        superseded_model_id=superseded,
        registered=registered,
    )


def registry_views(session_factory: Any, model_ids: Sequence[str]) -> dict[str, RegistryView]:
    """Look up the live registry facts for ``model_ids``, skipping unknown ids.

    Used to render the product's artifact listing from the registry rather than from a
    stale copy, so what a reviewer sees as deployed is what the router would resolve.
    Returns an empty mapping when the registry is unavailable: a read path must not
    fail because an enrichment could not be computed.
    """

    wanted = {mid for mid in model_ids if mid}
    if not wanted:
        return {}
    try:
        from moltrace.spectroscopy.ai.registry import InMemoryRegistryStore, ModelRegistry

        store = _registry_store(session_factory)
        if isinstance(store, InMemoryRegistryStore):
            return {}
        registry = ModelRegistry(store)
        return {
            entry.model_id: RegistryView(
                model_id=entry.model_id,
                status=registry.current_status(entry.model_id).value,
                role=entry.role.value,
                nucleus=entry.nucleus,
            )
            for entry in store.all_entries()
            if entry.model_id in wanted
        }
    except Exception:  # noqa: BLE001 - enrichment is best-effort by design
        return {}


def _registry_store(session_factory: Any = None) -> Any:
    """The durable registry store, bound to the app's engine when one is available.

    Falls back to an in-memory store so a prediction still runs (and still records
    its ``unregistered:*`` provenance markers) on a host with no configured database.
    Stores are cached per engine: :class:`SqlAlchemyRegistryStore` creates its two
    append-only tables on construction, which is idempotent but not free.
    """

    from moltrace.spectroscopy.ai.registry import InMemoryRegistryStore, SqlAlchemyRegistryStore

    engine = getattr(session_factory, "kw", {}).get("bind") if session_factory else None
    if engine is None:
        return InMemoryRegistryStore()
    store = _REGISTRY_STORES.get(engine)
    if store is None:
        store = SqlAlchemyRegistryStore(engine)
        _REGISTRY_STORES[engine] = store
    return store


# --------------------------------------------------------------------------- #
# Promotion gate
# --------------------------------------------------------------------------- #
def dominance_verdict(
    candidate: Mapping[str, Any], incumbent: Mapping[str, Any] | None
) -> DominanceVerdict:
    """Apply the evaluation harness's promotion rule to two stored metric mappings.

    Reuses the harness's metric directions, safety-critical set and tolerances so
    there is exactly one definition of "better" in the platform. Comparison is over
    the metrics present in *both* mappings — a metric nobody reported is not
    silently treated as perfect.

    Three outcomes, not two:

    * **Not applicable** — no incumbent (a first model is a baseline decision), or
      the two evaluations report no metric this gate knows how to compare.
    * **Refused** — a regression beyond tolerance, no improvement anywhere, or a
      safety-critical metric that *one* side reports and the other does not. That
      last case is the asymmetric hole: dropping ``ece`` from the new evaluation
      must not be a way to stop being measured on it.
    * **Passed** — at least one strict improvement and no regression.
    """

    from moltrace.spectroscopy.eval.harness import (
        DEFAULT_TOLERANCES,
        METRIC_DIRECTIONS,
        SAFETY_CRITICAL,
        MetricDirection,
    )

    if not incumbent:
        return DominanceVerdict(
            passed=False,
            applicable=False,
            reason=(
                "no deployed model for this task to compare against; the first evaluated "
                "model is a baseline decision, not a promotion"
            ),
            compared_metrics=(),
            regressions=(),
            improvements=(),
        )

    shared = [
        name
        for name in METRIC_DIRECTIONS
        if _is_number(candidate.get(name)) and _is_number(incumbent.get(name))
    ]

    # One side reports a metric that may never regress and the other does not.
    # Checked before the empty-intersection exit, so dropping the metric entirely
    # is not a way around the gate.
    asymmetric = sorted(
        name
        for name in SAFETY_CRITICAL
        if _is_number(candidate.get(name)) != _is_number(incumbent.get(name))
    )
    if asymmetric:
        return DominanceVerdict(
            passed=False,
            applicable=True,
            reason=(
                f"only one of the two evaluations reports {', '.join(asymmetric)}, so the "
                "metric that may never regress cannot be compared; re-run the evaluation "
                "reporting it on both"
            ),
            compared_metrics=tuple(shared),
            regressions=(),
            improvements=(),
        )

    if not shared:
        return DominanceVerdict(
            passed=False,
            applicable=False,
            reason=(
                "the two evaluations report no metric this promotion gate compares; "
                "approval rests on the recorded evaluation and the reviewer's sign-off"
            ),
            compared_metrics=(),
            regressions=(),
            improvements=(),
        )

    regressions: list[str] = []
    improvements: list[str] = []
    for name in shared:
        direction = METRIC_DIRECTIONS[name]
        tolerance = 0.0 if name in SAFETY_CRITICAL else float(DEFAULT_TOLERANCES.get(name, 0.0))
        raw = float(candidate[name]) - float(incumbent[name])
        improvement = raw if direction is MetricDirection.HIGHER_BETTER else -raw
        if improvement < -tolerance:
            regressions.append(
                f"{name} {float(incumbent[name]):.4g} → {float(candidate[name]):.4g}"
                + (" (may not regress at all)" if name in SAFETY_CRITICAL else "")
            )
        elif improvement > 0.0:
            improvements.append(name)

    if regressions:
        return DominanceVerdict(
            passed=False,
            applicable=True,
            reason="the candidate regresses against the deployed model on "
            + "; ".join(regressions),
            compared_metrics=tuple(shared),
            regressions=tuple(regressions),
            improvements=tuple(improvements),
        )
    if not improvements:
        return DominanceVerdict(
            passed=False,
            applicable=True,
            reason=(
                "the candidate matches the deployed model on every compared metric and "
                "improves none of them; there is nothing to promote"
            ),
            compared_metrics=tuple(shared),
            regressions=(),
            improvements=(),
        )
    scope = (
        ""
        if SAFETY_CRITICAL.intersection(shared)
        else " (no safety-critical metric was reported for this task)"
    )
    return DominanceVerdict(
        passed=True,
        applicable=True,
        reason="the candidate improves on "
        + ", ".join(improvements)
        + " with no regression"
        + scope,
        compared_metrics=tuple(shared),
        regressions=(),
        improvements=tuple(improvements),
    )


def _is_number(value: Any) -> bool:
    """A value the promotion gate can actually compare.

    NaN is excluded deliberately: it passes ``isinstance`` but every comparison
    against it is False, so a NaN metric would look *present* to the asymmetry check
    while silently registering neither a regression nor an improvement — a gate that
    reports itself as applied while guarding nothing.
    """

    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    return math.isfinite(float(value))
