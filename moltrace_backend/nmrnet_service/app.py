"""NMRNet GPU inference microservice (deployment scaffold).

This file runs **in the NMRNet container** (Python 3.8 + CUDA 11.6 + torch
1.13.1 + the Colin-Jay/NMRNet package), NOT in the main MolTrace backend. It
exposes the tiny HTTP contract the MolTrace-side client
(``moltrace.spectroscopy.predict.nmrnet_client``) speaks:

    POST /predict
    request : {"symbols": [...], "coordinates": [[x,y,z],...], "nuclei": [...]}
    response: {"shifts": {"<atom_index>": [predicted_ppm, uncertainty_ppm], ...}}

Two integration points (`_load_model`, `_run_inference`) must be filled with the
exact calls from the repo's ``demo/notebook/NMRNet.ipynb``. They raise
``NotImplementedError`` until you do — the service never returns fabricated
shifts. The featurisation and HTTP plumbing around them are real.

Recipe to transcribe from the notebook (verbatim cells):
  1. build the model + load the checkpoint from MOLTRACE_NMRNET_WEIGHTS;
  2. build the atoms/coords dataset + collator (rcut local environments,
     multi-conformer augmentation);
  3. forward:  net_output = model(**batch, features_only=True,
                                   classification_head_name='nmr_head')
               predict = target_scaler.inverse_transform(
                             net_output[0].view(-1, num_classes).cpu())
  4. average the augmented conformers:  d = predict.reshape(-1, K).mean(axis=1)
  5. reference σ→δ for the trained nucleus (liquid-state nmrshiftdb2 checkpoint
     bakes this into target_scaler; the solid-state demo used δ = 29.91 − 0.987σ).

Run:  uvicorn app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="NMRNet inference service", version="0.1.0")

_MODEL: Any = None  # populated at startup by _load_model()


class PredictRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1)
    coordinates: list[list[float]] = Field(..., min_length=1)
    nuclei: list[str] = Field(default_factory=lambda: ["1H", "13C"])


class PredictResponse(BaseModel):
    # {atom_index (as str): [predicted_ppm, uncertainty_ppm]}
    shifts: dict[str, list[float]]


# --------------------------------------------------------------------------- #
# Integration points — fill from demo/notebook/NMRNet.ipynb
# --------------------------------------------------------------------------- #
def _load_model() -> Any:
    """Build the NMRNet model and load the checkpoint (MOLTRACE_NMRNET_WEIGHTS)."""

    weights = os.environ.get("MOLTRACE_NMRNET_WEIGHTS")
    if not weights:
        raise RuntimeError("MOLTRACE_NMRNET_WEIGHTS is not set")
    # TODO(integration): transcribe the model construction + checkpoint load from
    # the notebook (unicore task/model build + load_state_dict), e.g.:
    #     import torch; from unicore import ...
    #     model = build_nmrnet(args); model.load_state_dict(torch.load(weights)); model.eval()
    #     return {"model": model, "target_scaler": target_scaler, "args": args, "K": 4}
    raise NotImplementedError(
        "Fill _load_model() with the NMRNet build + checkpoint load from "
        "demo/notebook/NMRNet.ipynb (see module docstring, step 1)."
    )


def _run_inference(
    model: Any, symbols: list[str], coordinates: list[list[float]], nuclei: list[str]
) -> dict[int, tuple[float, float]]:
    """Run NMRNet on one molecule; return {atom_index: (ppm, uncertainty_ppm)}.

    The input is already the atoms + 3D coordinates NMRNet consumes (the MolTrace
    wrapper does the RDKit embed). Build the batch, run the documented forward,
    inverse-transform, average conformers, reference σ→δ, and map results to the
    H/C atom indices for the requested ``nuclei``.
    """

    raise NotImplementedError(
        "Fill _run_inference() with the dataset/collator + forward pass from "
        "demo/notebook/NMRNet.ipynb (see module docstring, steps 2-5)."
    )


# --------------------------------------------------------------------------- #
# HTTP plumbing (real)
# --------------------------------------------------------------------------- #
@app.on_event("startup")
def _startup() -> None:
    global _MODEL
    _MODEL = _load_model()


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": _MODEL is not None}


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    if len(request.symbols) != len(request.coordinates):
        # Mirror the wrapper's contract: symbols and coords are 1:1 per atom.
        raise ValueError("symbols and coordinates must have equal length")
    result = _run_inference(
        _MODEL, request.symbols, request.coordinates, request.nuclei
    )
    return PredictResponse(
        shifts={str(i): [ppm, unc] for i, (ppm, unc) in result.items()}
    )
