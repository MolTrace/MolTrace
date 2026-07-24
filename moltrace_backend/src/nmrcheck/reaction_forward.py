"""Repho R14 — forward reaction prediction + condition recommendation (cross-checked, advisory).

A forward model predicts likely products (and a condition recommender suggests how to run the
reaction). Under the Phase-C contract the model is a guest: it is probed and flagged
(``MOLTRACE_REACTION_FORWARD`` + rxn4chemistry **or** transformers — either backend satisfies the
probe), and **every prediction passes through the frozen engines before a chemist sees it** —
the R6 structural safety screen over reactants, reagents, and each predicted product (fail-safe:
unparseable → *unknown, requires review*), and the R1 CHEM21 greenness of any suggested solvent.
The cross-check **annotates, never filters**: a hazardous prediction is shown flagged, because
hiding it would misrepresent what the model believes the chemistry will do.

There is no lightweight forward-prediction fallback — absent the extras, the capability reports
*unavailable* plainly and the surface stays hidden.

Validation: :func:`topk_accuracy` computes top-1/top-k accuracy against a held-out eval file
(USPTO-style), canonical-SMILES matched; an unparseable prediction is counted **wrong**, never
silently skipped (a model does not get credit for output the toolkit cannot read).

Pure: no DB / HTTP / clock / randomness; RDKit lazy; heavy backends injectable for tests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import reaction_ml, reaction_safety
from .reaction_green import _solvent_greenness

ENGINE = "reaction_forward.v1"

FORWARD_DISCLAIMER = (
    "Forward predictions and condition suggestions are machine proposals annotated by the frozen "
    "safety and green-chemistry engines. They are advisory decision support, never a synthesis "
    "instruction; a qualified chemist must review every prediction, and flagged chemistry is "
    "surfaced rather than hidden."
)


class ReactionForwardError(Exception):
    """Raised on a malformed prediction payload or a failed adapter call."""


# Mirrors reaction_safety._RANK exactly. A severity this map does not know (including "critical"
# if the engine's vocabulary ever grows) must NEVER read as milder than what was screened, so an
# unrecognised label is treated as maximally severe rather than dropped.
_RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_UNKNOWN_RISK = "unknown"


def _risk_rank(risk: str) -> int:
    if risk == _UNKNOWN_RISK:
        return _RISK_RANK["critical"] + 1  # unknown outranks everything: never silently clear
    return _RISK_RANK.get(risk, _RISK_RANK["critical"] + 1)


def _aggregate_screens(
    base: Mapping[str, Any], product_screens: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Combine the reactant/reagent screen with per-product screens, fail-safe.

    Mirrors ``reaction_safety.screen_reaction``'s aggregation with two deliberate strengthenings:

    1. The worst risk wins across the FULL severity vocabulary (low < medium < high < critical),
       and an unknown/unrecognised severity outranks all of them. The aggregate can therefore
       never read milder than any component screen — the failure mode where a *critical* product
       silently aggregates to *low*.
    2. **Unreadable species surface as unknown, not low.** The frozen engine drops ``unknown``
       species risks before aggregating and falls back to ``low`` when nothing is left, so a
       reactant RDKit cannot parse disappears from ``base["overall_risk"]`` as long as one
       sibling parses. Here the per-species records are re-read directly, so an unparseable
       reactant or reagent cannot be laundered into a clean verdict. The frozen engine is left
       untouched — the strengthening belongs in the overlay that consumes it.
    """

    base_species = base.get("species") or []
    base_unreadable = any(
        (not species.get("parsed", False))
        or str(species.get("overall_risk") or _UNKNOWN_RISK) == _UNKNOWN_RISK
        for species in base_species
    )
    base_risk = _UNKNOWN_RISK if base_unreadable else str(base.get("overall_risk") or _UNKNOWN_RISK)
    risks = [base_risk] + [
        str(screen.get("overall_risk") or _UNKNOWN_RISK) for screen in product_screens
    ]
    overall = max(risks, key=_risk_rank)
    any_unparsed = base_unreadable or any(
        not screen.get("parsed", False) for screen in product_screens
    )
    any_flagged = any(screen.get("flagged_groups") for screen in product_screens)
    groups = set(base.get("energetic_groups_found") or [])
    for screen in product_screens:
        groups.update(flag.get("key") for flag in screen.get("flagged_groups") or [])
    return {
        "overall_risk": overall,
        "requires_expert_review": (
            bool(base.get("requires_expert_review"))
            or any_unparsed
            or any_flagged
            or overall != "low"
        ),
        "energetic_groups_found": sorted(g for g in groups if g),
    }


@dataclass
class ForwardPrediction:
    """One model proposal: predicted products (+ optional confidence and conditions)."""

    products_smiles: list[str]
    confidence: float | None = None
    conditions: dict[str, Any] = field(default_factory=dict)
    source: str = "model"


def cross_check_prediction(
    reactants_smiles: Sequence[str],
    prediction: ForwardPrediction,
    *,
    reagents_smiles: Sequence[str] = (),
) -> dict[str, Any]:
    """Annotate a prediction with the frozen R6 safety screen + R1 solvent greenness.

    The reaction-level screen covers reactants, reagents, and every predicted product; a solvent
    named in the suggested conditions is scored against the CHEM21 table. Nothing is filtered —
    a flagged proposal is returned flagged so the chemist sees exactly what the model proposed.
    """

    if not prediction.products_smiles:
        raise ReactionForwardError("Prediction carries no products.")
    # screen_reaction takes a single product; screen every predicted product and aggregate with
    # the same fail-safe rules (worst risk wins; unparseable or flagged -> requires review).
    base = reaction_safety.screen_reaction(
        reactant_smiles=list(reactants_smiles),
        reagent_smiles=list(reagents_smiles),
        product_smiles=None,
    )
    product_screens = [
        reaction_safety.screen_smiles(product) for product in prediction.products_smiles
    ]
    screen = _aggregate_screens(base, product_screens)
    solvent = prediction.conditions.get("solvent")
    solvent_greenness: float | None = None
    warnings: list[str] = []
    if solvent:
        solvent_greenness = _solvent_greenness(str(solvent), {})
        if solvent_greenness is None:
            warnings.append(f"Suggested solvent {solvent!r} is not in the CHEM21 table.")
    if prediction.confidence is not None and not (0.0 <= float(prediction.confidence) <= 1.0):
        warnings.append(f"Model confidence {prediction.confidence!r} is outside [0, 1].")

    return {
        "products_smiles": list(prediction.products_smiles),
        "confidence": prediction.confidence,
        "conditions": dict(prediction.conditions),
        "source": prediction.source,
        "safety": {
            "overall_risk": screen["overall_risk"],
            "requires_expert_review": screen["requires_expert_review"],
            "energetic_groups_found": screen.get("energetic_groups_found"),
        },
        "solvent_greenness": solvent_greenness,
        "warnings": warnings,
        "human_review_required": True,
        "disclaimer": FORWARD_DISCLAIMER,
        "engine": ENGINE,
    }


def predict_forward(
    reactants_smiles: Sequence[str],
    *,
    reagents_smiles: Sequence[str] = (),
    top_k: int = 5,
    probe: Callable[[str], bool] | None = None,
    env: Mapping[str, str] | None = None,
    _backend: Callable[[Sequence[str], Sequence[str], int], list[ForwardPrediction]] | None = None,
) -> dict[str, Any]:
    """Run the governed forward-prediction pipeline: capability gate → model → frozen cross-check.

    ``_backend`` is the injectable model seam (tests exercise the governance + cross-check through
    a fake); the default resolves a site-installed backend (rxn4chemistry, else transformers).
    """

    status = reaction_ml.require_capability("forward_prediction", probe=probe, env=env)
    backend = _backend or _resolve_live_backend()
    try:
        predictions = backend(list(reactants_smiles), list(reagents_smiles), top_k)
    except reaction_ml.CapabilityUnavailableError:
        raise
    except Exception as exc:
        raise ReactionForwardError(f"Forward-prediction backend failed: {exc}") from exc
    if not predictions:
        raise ReactionForwardError("Forward-prediction backend returned no candidates.")

    checked = [
        cross_check_prediction(
            reactants_smiles, prediction, reagents_smiles=reagents_smiles
        )
        for prediction in predictions[:top_k]
    ]
    return {
        "reactants_smiles": list(reactants_smiles),
        "reagents_smiles": list(reagents_smiles),
        "predictions": checked,
        "capability_provenance": status.as_dict(),
        "human_review_required": True,
        "disclaimer": FORWARD_DISCLAIMER,
        "engine": ENGINE,
    }


def _resolve_live_backend():  # pragma: no cover - requires a site-installed extra
    import importlib.util  # noqa: PLC0415

    if importlib.util.find_spec("rxn4chemistry") is not None:
        return _rxn4chemistry_backend
    return _transformers_backend


def _rxn4chemistry_backend(
    reactants: Sequence[str], reagents: Sequence[str], top_k: int
) -> list[ForwardPrediction]:  # pragma: no cover - requires the site-installed extra + API key
    import os  # noqa: PLC0415

    from rxn4chemistry import RXN4ChemistryWrapper  # noqa: PLC0415

    api_key = os.environ.get("RXN4CHEMISTRY_API_KEY", "")
    if not api_key:
        raise reaction_ml.CapabilityUnavailableError(
            "forward_prediction: RXN4CHEMISTRY_API_KEY is not configured."
        )
    wrapper = RXN4ChemistryWrapper(api_key=api_key)
    smiles = ".".join(list(reactants) + list(reagents))
    response = wrapper.predict_reaction(smiles)
    results = wrapper.get_predict_reaction_results(response["prediction_id"])
    attempts = results["response"]["payload"]["attempts"][:top_k]
    return [
        ForwardPrediction(
            products_smiles=[attempt["smiles"].split(">>")[-1]],
            confidence=attempt.get("confidence"),
            source="rxn4chemistry",
        )
        for attempt in attempts
    ]


def _transformers_backend(
    reactants: Sequence[str], reagents: Sequence[str], top_k: int
) -> list[ForwardPrediction]:  # pragma: no cover - requires the site-installed extra + weights
    import os  # noqa: PLC0415

    from transformers import pipeline  # noqa: PLC0415

    model_path = os.environ.get("MOLTRACE_FORWARD_MODEL_PATH", "")
    if not model_path:
        raise reaction_ml.CapabilityUnavailableError(
            "forward_prediction: MOLTRACE_FORWARD_MODEL_PATH is not configured "
            "(weights are site-installed, never bundled)."
        )
    generator = pipeline("text2text-generation", model=model_path)
    prompt = ".".join(list(reactants) + list(reagents))
    outputs = generator(prompt, num_return_sequences=top_k, num_beams=max(top_k, 5))
    return [
        ForwardPrediction(
            products_smiles=[str(output["generated_text"]).strip()],
            source="molecular_transformer",
        )
        for output in outputs
    ]


# --------------------------------------------------------------------------- #
# Validation: top-k accuracy on a held-out eval set (USPTO-style).
# --------------------------------------------------------------------------- #
def _load_rdkit():
    try:
        from rdkit import Chem  # noqa: PLC0415

        return Chem
    except ImportError:
        return None


def _canonical(chem: Any, smiles: str) -> str | None:
    # An empty/whitespace SMILES is not a molecule. RDKit's ``MolFromSmiles("")`` returns an
    # *empty mol* rather than None, which would canonicalize back to "" and let a blank truth
    # match a blank prediction — so refuse before the toolkit ever sees it.
    if not smiles.strip():
        return None
    if chem is None:
        return smiles.strip()
    mol = chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    canonical = chem.MolToSmiles(mol)
    return canonical or None


def topk_accuracy(
    cases: Sequence[Mapping[str, Any]],
    *,
    ks: Sequence[int] = (1, 5),
) -> dict[str, Any]:
    """Top-k accuracy over eval cases ``{"predictions": [smiles...], "truth": smiles}``.

    Matching is canonical-SMILES equality (RDKit when available; honest raw-string fallback is
    reported in the result). An unparseable prediction counts as wrong; an unparseable TRUTH makes
    the case invalid and is reported — a benchmark row the toolkit cannot read must not silently
    score either way.
    """

    if not cases:
        raise ReactionForwardError("No evaluation cases.")
    if not ks or any(isinstance(k, bool) or not isinstance(k, int) or k < 1 for k in ks):
        raise ReactionForwardError(f"ks must be one or more positive integers, got {list(ks)!r}.")
    chem = _load_rdkit()
    max_k = max(ks)
    hits = {k: 0 for k in ks}
    invalid: list[int] = []
    scored = 0
    for index, case in enumerate(cases):
        truth = _canonical(chem, str(case.get("truth") or ""))
        if truth is None:
            invalid.append(index)
            continue
        scored += 1
        predictions = [str(p) for p in case.get("predictions") or []][:max_k]
        canon = [_canonical(chem, p) for p in predictions]
        for k in ks:
            if any(c is not None and c == truth for c in canon[:k]):
                hits[k] += 1
    if not scored:
        raise ReactionForwardError("Every evaluation case was invalid; refusing to report.")
    return {
        "n_cases": len(cases),
        "n_scored": scored,
        "invalid_case_indices": invalid,
        "canonicalized": chem is not None,
        "accuracy": {f"top_{k}": hits[k] / scored for k in ks},
        "engine": ENGINE,
    }
