"""5-layer inference router with exact provenance (Prompt 13, Roadmap Layers 1-3).

SpectraCheck composes three shift-prediction layers behind one call and records,
for every prediction, exactly which artifact produced each number and why one was
chosen over another:

* **Layer 3 -- LoRA fine-tuned** (Prompt 15): used for an atom only when a
  ``production`` LoRA adapter exists for its nucleus AND the atom's
  conformer-ensemble uncertainty (Prompt 6) is at/below the adapter's *validated*
  confidence band.
* **Layer 1 -- NMRNet pretrained** (Prompt 6): otherwise.
* **Fallback -- HOSE-code** (Prompt 6): when NMRNet is unavailable.

:meth:`InferenceRouter.predict_shifts_routed` returns a :class:`RoutedPrediction`
carrying, per atom, the prediction + uncertainty + the layer used, plus a single
``model_versions`` dict of every artifact id + SHA-256 that touched the result.
That dict is the provenance handoff to the Prompt 12 audit trail: it feeds an
:class:`~moltrace.spectroscopy.audit.trail.AuditEntry`'s ``model_versions``
verbatim -- one prediction, one immutable provenance record -- so the result is
reproducible bit-for-bit from the registry + lineage.

Device strategy is delegated to :func:`predict_shifts` (Prompt 6): it resolves
CUDA -> MPS -> CPU and falls back MPS -> CPU on a kernel miss; this module sets
``PYTORCH_ENABLE_MPS_FALLBACK=1`` on import for parity. The router never imports
torch directly and runs on a CPU-only host (where it routes through the HOSE
fallback).
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from moltrace.spectroscopy.ai.registry import ModelRegistry, ModelRole

# Parity with Prompt 6: allow torch ops unimplemented on MPS to fall back to CPU.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

__all__ = [
    "InferenceRouter",
    "Layer",
    "RoutedAtomPrediction",
    "RoutedPrediction",
]


class Layer(StrEnum):
    """Which prediction layer produced an atom's number."""

    LORA_FINETUNED = "layer3_lora_finetuned"
    NMRNET_PRETRAINED = "layer1_nmrnet_pretrained"
    HOSE_FALLBACK = "fallback_hose"


# A LoRA adapter inference hook (Prompt 15, not yet implemented). Called as
# ``lora_predict_fn(smiles, nucleus, adapter=<ModelEntry>, device=<str|None>)``
# and returns ``{atom_index: (predicted_ppm, uncertainty_ppm)}``.
LoraPredictFn = Callable[..., Mapping[int, tuple[float, float]]]
# The Prompt 6 base predictor signature (injectable for tests).
PredictFn = Callable[..., Any]


@dataclass(frozen=True)
class RoutedAtomPrediction:
    """One atom's routed prediction with the layer + artifact that produced it."""

    atom_index: int
    element: str
    nucleus: str
    predicted_ppm: float
    uncertainty_ppm: float
    layer: Layer
    model_id: str | None
    reason: str


@dataclass(frozen=True)
class RoutedPrediction:
    """A routed shift prediction plus its complete, deterministic provenance.

    ``model_versions`` maps every artifact id that touched the result to its
    SHA-256; pass it straight into the Prompt 12 audit entry.
    """

    smiles: str
    nuclei: tuple[str, ...]
    device: str
    base_method: str  # 'nmrnet' | 'hose_fallback' (the Prompt 6 base path)
    predictions: tuple[RoutedAtomPrediction, ...]
    model_versions: dict[str, str]
    layers_used: tuple[Layer, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _default_predict_fn(*args: Any, **kwargs: Any) -> Any:
    """Lazy default base predictor -- imports Prompt 6 only when actually called.

    Keeps :mod:`router` import-light (no rdkit/torch at import time) and lets the
    NMRNet/LoRA branches be exercised with injected fakes on a CPU-only host.
    """

    from moltrace.spectroscopy.predict.nmrnet_wrapper import predict_shifts

    return predict_shifts(*args, **kwargs)


class InferenceRouter:
    """Compose Layer 3 (LoRA) / Layer 1 (NMRNet) / fallback (HOSE) with provenance."""

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        predict_fn: PredictFn | None = None,
        lora_predict_fn: LoraPredictFn | None = None,
    ) -> None:
        self.registry = registry
        self._predict_fn = predict_fn if predict_fn is not None else _default_predict_fn
        self._lora_predict_fn = lora_predict_fn

    def predict_shifts_routed(
        self,
        smiles: str,
        nuclei: Sequence[str] = ("1H", "13C"),
        device: str | None = None,
    ) -> RoutedPrediction:
        """Predict shifts for ``smiles`` and route each atom to the best layer.

        Resolution per atom (see module docstring): Layer 3 LoRA -> Layer 1
        NMRNet -> HOSE fallback. The returned ``model_versions`` is complete
        (every contributing artifact) and deterministic (sorted), so identical
        inputs + registry state yield an identical provenance record.
        """

        base = self._predict_fn(smiles, tuple(nuclei), device=device)
        warnings: list[str] = list(getattr(base, "warnings", []) or [])
        base_method = getattr(base, "method", "hose_fallback")
        base_device = getattr(base, "device", "cpu")

        # Resolve the production artifacts once (deterministic registry reads).
        hose_kb = self.registry.resolve(ModelRole.HOSE_KB, None)
        checkpoint_for: dict[str, Any] = {}
        lora_for: dict[str, Any] = {}
        lora_cache: dict[str, Mapping[int, tuple[float, float]]] = {}

        used: dict[str, str] = {}
        predictions: list[RoutedAtomPrediction] = []

        for atom in getattr(base, "shifts", []) or []:
            nuc = atom.nucleus
            if nuc not in checkpoint_for:
                checkpoint_for[nuc] = self.registry.resolve(ModelRole.NMRNET_CHECKPOINT, nuc)
                lora_for[nuc] = self.registry.resolve(ModelRole.LORA_ADAPTER, nuc)

            routed = self._route_atom(
                atom=atom,
                base_method=base_method,
                base_device=base_device,
                smiles=smiles,
                checkpoint=checkpoint_for[nuc],
                lora=lora_for[nuc],
                hose_kb=hose_kb,
                lora_cache=lora_cache,
                used=used,
                warnings=warnings,
            )
            predictions.append(routed)

        if not predictions:
            warnings.append("router produced no predictions (no shifts from base predictor)")

        layers_used = tuple(sorted({p.layer for p in predictions}))
        return RoutedPrediction(
            smiles=smiles,
            nuclei=tuple(nuclei),
            device=base_device,
            base_method=base_method,
            predictions=tuple(predictions),
            model_versions=dict(sorted(used.items())),
            layers_used=layers_used,
            warnings=tuple(warnings),
        )

    # -- per-atom resolution -------------------------------------------------- #
    def _route_atom(
        self,
        *,
        atom: Any,
        base_method: str,
        base_device: str,
        smiles: str,
        checkpoint: Any,
        lora: Any,
        hose_kb: Any,
        lora_cache: dict[str, Mapping[int, tuple[float, float]]],
        used: dict[str, str],
        warnings: list[str],
    ) -> RoutedAtomPrediction:
        nuc = atom.nucleus

        # Layer 3 -- LoRA, gated by the conformer-ensemble uncertainty band.
        if base_method == "nmrnet" and lora is not None and self._lora_predict_fn is not None:
            band = lora.confidence_band_ppm
            unc = float(atom.uncertainty_ppm)
            if band is None:
                msg = f"lora adapter {lora.model_id!r} has no confidence_band_ppm; skipping LoRA"
                if msg not in warnings:
                    warnings.append(msg)
            elif math.isfinite(unc) and unc <= float(band):
                lora_pred = self._lora_for_nucleus(smiles, nuc, lora, base_device, lora_cache)
                if atom.atom_index in lora_pred:
                    lp, lu = lora_pred[atom.atom_index]
                    # LoRA composes on its base checkpoint -> both touch the result.
                    self._record(
                        used, warnings, entry=lora, role=ModelRole.LORA_ADAPTER, nucleus=nuc
                    )
                    self._record_parent(
                        used, warnings, lora=lora, checkpoint=checkpoint, nucleus=nuc
                    )
                    reason = (
                        f"layer3 lora: ensemble uncertainty {unc:.3f} "
                        f"<= band {float(band):.3f} ppm"
                    )
                    return RoutedAtomPrediction(
                        atom_index=atom.atom_index,
                        element=atom.element,
                        nucleus=nuc,
                        predicted_ppm=float(lp),
                        uncertainty_ppm=float(lu),
                        layer=Layer.LORA_FINETUNED,
                        model_id=lora.model_id,
                        reason=reason,
                    )

        # Layer 1 -- NMRNet pretrained.
        if base_method == "nmrnet":
            model_id = self._record(
                used, warnings, entry=checkpoint, role=ModelRole.NMRNET_CHECKPOINT, nucleus=nuc
            )
            reason = "layer1 nmrnet pretrained"
            if lora is not None and lora.confidence_band_ppm is not None:
                unc = float(atom.uncertainty_ppm)
                if not math.isfinite(unc):
                    reason = (
                        "layer1 nmrnet: ensemble uncertainty NaN "
                        "(single conformer) -> LoRA band not met"
                    )
                elif unc > float(lora.confidence_band_ppm):
                    reason = (
                        f"layer1 nmrnet: ensemble uncertainty {unc:.3f} > lora band "
                        f"{float(lora.confidence_band_ppm):.3f} ppm"
                    )
            return RoutedAtomPrediction(
                atom_index=atom.atom_index,
                element=atom.element,
                nucleus=nuc,
                predicted_ppm=float(atom.predicted_ppm),
                uncertainty_ppm=float(atom.uncertainty_ppm),
                layer=Layer.NMRNET_PRETRAINED,
                model_id=model_id,
                reason=reason,
            )

        # Fallback -- HOSE-code.
        model_id = self._record(used, warnings, entry=hose_kb, role=ModelRole.HOSE_KB, nucleus=None)
        return RoutedAtomPrediction(
            atom_index=atom.atom_index,
            element=atom.element,
            nucleus=nuc,
            predicted_ppm=float(atom.predicted_ppm),
            uncertainty_ppm=float(atom.uncertainty_ppm),
            layer=Layer.HOSE_FALLBACK,
            model_id=model_id,
            reason="fallback hose-code (nmrnet unavailable)",
        )

    def _lora_for_nucleus(
        self,
        smiles: str,
        nucleus: str,
        lora: Any,
        device: str,
        cache: dict[str, Mapping[int, tuple[float, float]]],
    ) -> Mapping[int, tuple[float, float]]:
        if nucleus not in cache:
            assert self._lora_predict_fn is not None  # guarded by caller
            cache[nucleus] = dict(
                self._lora_predict_fn(smiles, nucleus, adapter=lora, device=device)
            )
        return cache[nucleus]

    # -- provenance accounting ------------------------------------------------ #
    @staticmethod
    def _record(
        used: dict[str, str],
        warnings: list[str],
        *,
        entry: Any,
        role: ModelRole,
        nucleus: str | None,
    ) -> str | None:
        """Record one contributing artifact's ``model_id -> sha256`` and return the id.

        When the contributing artifact is not registered, record an explicit
        ``unregistered:*`` marker (so provenance stays complete) and warn, rather
        than silently dropping it.
        """

        if entry is not None:
            used[entry.model_id] = entry.artifact_sha256
            return entry.model_id
        key = f"unregistered:{role.value}:{nucleus or 'all'}"
        used[key] = "unknown"
        msg = (
            f"no production {role.value} registered for nucleus={nucleus or 'all'}; "
            "provenance marked unregistered"
        )
        if msg not in warnings:
            warnings.append(msg)
        return key

    def _record_parent(
        self,
        used: dict[str, str],
        warnings: list[str],
        *,
        lora: Any,
        checkpoint: Any,
        nucleus: str,
    ) -> None:
        """Record the base checkpoint a LoRA adapter composes on."""

        parent = None
        if lora.parent_base_id:
            parent = self.registry.store.get_entry(lora.parent_base_id)
        if parent is None:
            parent = checkpoint
        self._record(
            used, warnings, entry=parent, role=ModelRole.NMRNET_CHECKPOINT, nucleus=nucleus
        )
