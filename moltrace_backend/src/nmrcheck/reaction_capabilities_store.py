"""Repho Phase C — the HTTP-facing capability readout (stateless; models co-located).

One thin seam over :mod:`nmrcheck.reaction_ml`: render the governed heavy-ML capability table
(``yield_gnn`` / ``retrosynthesis`` / ``forward_prediction`` / ``sdl_execution``) for an ops/admin
surface, plus the site-level SDL opt-in status. The engine stays pure; nothing here touches the DB.

Response models are co-located here (off the contended ``models.py``, per the R4 precedent).

Two truths this surface must state honestly (they are by design, not bugs):

* ``yield_gnn`` reports ``active=False`` with reason ``"no benchmark promotion evidence
  supplied"`` even when its flag is on and torch is installed — the readout passes no promotion
  evidence, because activation is a per-call decision bound to a specific gate artifact
  (``reaction_eval.promotion_evidence``), never a standing global state.
* ``retrosynthesis`` and ``forward_prediction`` have no lightweight fallback: when their extras
  are absent they are *unavailable*, and the UI should hide those surfaces rather than degrade.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import reaction_ml, reaction_sdl

_DISCLAIMER = (
    "Heavy-ML reaction capabilities are optional, default-off extras governed by per-deployment "
    "flags, dependency probes, and (where frozen math is replaced) a recorded benchmark-gate "
    "pass. This readout reports what this deployment has actually enabled; nothing heavy "
    "activates implicitly."
)


# --------------------------------------------------------------------------- #
# API models (co-located).
# --------------------------------------------------------------------------- #
class ReactionCapabilityStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: bool
    available: bool
    active: bool
    missing_modules: list[str] = Field(default_factory=list)
    reason: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    engine: str


class ReactionCapabilityReadout(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: list[ReactionCapabilityStatus]
    disclaimer: str = _DISCLAIMER


class ReactionSdlSiteStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    capability: ReactionCapabilityStatus
    execution_surface_wired: bool = False
    detail: str
    disclaimer: str = reaction_sdl.SDL_DISCLAIMER


# --------------------------------------------------------------------------- #
# Store functions (stateless — no DB).
# --------------------------------------------------------------------------- #
def capability_readout() -> ReactionCapabilityReadout:
    return ReactionCapabilityReadout(
        capabilities=[
            ReactionCapabilityStatus(**status.as_dict())
            for status in reaction_ml.all_capability_statuses()
        ]
    )


def sdl_site_status() -> ReactionSdlSiteStatus:
    enabled = reaction_sdl.sdl_site_enabled(env=os.environ)
    status = reaction_ml.capability_status("sdl_execution")
    if enabled:
        detail = (
            "SDL is enabled at this site. No HTTP execution surface is wired: arming and step "
            "execution require a bound site driver, persisted journal anchoring, and the "
            "human-approval/safety-gate linkage — manual make/test/learn remains the path."
        )
    else:
        detail = "SDL is not enabled at this site (set MOLTRACE_REACTION_SDL=1 to opt in)."
    return ReactionSdlSiteStatus(
        enabled=enabled,
        capability=ReactionCapabilityStatus(**status.as_dict()),
        execution_surface_wired=False,
        detail=detail,
    )
