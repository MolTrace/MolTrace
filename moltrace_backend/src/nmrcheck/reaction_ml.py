"""Repho Phase C — the governed capability seam for heavy-ML reaction extras.

Phase C (R12-R15) deliberately breaks the lightweight/CPU-deployable default: GNN yield models
(torch), retrosynthesis (aizynthfinder), forward prediction (rxn4chemistry / transformers), and
SDL robotics. This module is the single seam through which every one of those capabilities is
allowed into the product, under one contract — **the heavy model is always a guest**:

1. **Default-off.** Each capability has its own environment flag; nothing heavy activates
   implicitly. The flags mirror the R8 agent's opt-in (`MOLTRACE_REACTION_AGENT`) semantics.
2. **Probed, never imported.** Heavy dependencies are site-installed accelerators discovered via
   ``importlib.util.find_spec`` at decision time — exactly the house pattern of the optional
   ``rag`` / ``infra`` / ``docx`` groups. Importing this module never imports torch et al., so the
   default CI job and every Phase-A/B path are untouched.
3. **Gated by promotion evidence.** A capability that replaces frozen math (the GNN yield
   surrogate) additionally requires a recorded **R11 benchmark gate pass** (exit code 0 against
   the frozen, checksummed gold set) naming the exact model version. No evidence, no activation —
   a heavy model cannot be selected just because it is installed and flagged on.
4. **Provenance on every decision.** ``resolve_backend`` returns an auditable record of *why* the
   heavy path was (or was not) taken — flag value, probe results, evidence reference — for the
   caller to persist (the Annex-22 habit applied to ML enablement).
5. **Honest fallback.** When a capability is off/absent, the decision names the Phase-A/B path
   that runs instead (or states plainly that the capability is unavailable) — never a silent
   degradation and never a crash.

Pure: no DB / HTTP / clock / randomness; probes and environment are injectable for tests.
"""

from __future__ import annotations

import importlib.util
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

ENGINE = "reaction_ml.v1"

_TRUTHY = {"1", "true", "yes", "on"}

# The R11 CI contract (reaction_eval.EXIT_OK) — promotion evidence must carry a 0 exit code.
_PROMOTION_EXIT_OK = 0
# reaction_eval.gold_set_checksum emits exactly this shape.
_GOLD_CHECKSUM_RE = re.compile(r"sha256:[0-9a-f]{64}")


class CapabilityUnavailableError(Exception):
    """Raised when a heavy capability is required but disabled, absent, or unevidenced."""


@dataclass(frozen=True)
class CapabilitySpec:
    """One heavy capability's contract: flag, dependency probe set, fallback, governance."""

    name: str
    flag_env: str
    required_modules: tuple[str, ...]
    description: str
    fallback: str
    requires_promotion_evidence: bool = False
    install_hint: str = ""


CAPABILITIES: dict[str, CapabilitySpec] = {
    spec.name: spec
    for spec in (
        CapabilitySpec(
            name="yield_gnn",
            flag_env="MOLTRACE_REACTION_YIELD_GNN",
            required_modules=("torch",),
            description=(
                "R12 — graph-neural yield/selectivity predictor with MC-Dropout uncertainty."
            ),
            fallback=(
                "Phase-A surrogate: sklearn GP when installed, else the zero-dependency "
                "k-NN rule-based surrogate — always available."
            ),
            # Replaces frozen math, so it must have beaten the incumbent on the frozen benchmark.
            requires_promotion_evidence=True,
            install_hint="pip install torch  (site-installed; never a core dependency)",
        ),
        CapabilitySpec(
            name="retrosynthesis",
            flag_env="MOLTRACE_REACTION_RETRO",
            required_modules=("aizynthfinder",),
            description="R13 — AiZynthFinder MCTS retrosynthesis with green/safety route overlays.",
            fallback=(
                "None — retrosynthesis has no lightweight equivalent; the capability reports "
                "unavailable and the UI hides the surface."
            ),
            install_hint="pip install aizynthfinder  (site-installed; never a core dependency)",
        ),
        CapabilitySpec(
            name="forward_prediction",
            flag_env="MOLTRACE_REACTION_FORWARD",
            required_modules=("rxn4chemistry", "transformers"),
            description=(
                "R14 — forward reaction prediction + condition recommendation, cross-checked "
                "against the frozen safety/green engines."
            ),
            fallback=(
                "None — forward prediction has no lightweight equivalent; the capability reports "
                "unavailable and the UI hides the surface."
            ),
            install_hint=(
                "pip install rxn4chemistry  OR  pip install transformers "
                "(either backend satisfies the probe)"
            ),
        ),
        CapabilitySpec(
            name="sdl_execution",
            flag_env="MOLTRACE_REACTION_SDL",
            required_modules=(),  # gated by flag + a connected driver, not by a python package
            description=(
                "R15 — self-driving-lab execution behind the hardware-abstraction layer; "
                "manual mode is the default everywhere."
            ),
            fallback="Manual make/test/learn — the R5 half-closed loop, unchanged.",
        ),
    )
}

# forward_prediction is satisfied by ANY ONE of its probed modules (rxn4chemistry OR transformers).
_ANY_ONE_MODULE: frozenset[str] = frozenset({"forward_prediction"})


def _module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _flag_on(spec: CapabilitySpec, env: Mapping[str, str]) -> bool:
    return env.get(spec.flag_env, "").strip().lower() in _TRUTHY


def _valid_promotion_evidence(
    evidence: Mapping[str, Any] | None,
    *,
    expected_gold_checksum: str | None = None,
    expected_model_version: str | None = None,
) -> tuple[bool, str]:
    """Validate an R11 gate-pass record, strictly.

    Types are checked before values: the genuine producer
    (:class:`nmrcheck.reaction_eval.GateOutcome`) emits an ``int`` exit code and a
    ``sha256:<64-hex>`` digest, so anything else did not come from the gate and is refused rather
    than coerced. Notably ``exit_code=False`` equals ``0`` in Python — a mis-mapped "passed" flag
    whose ``False`` means FAILURE must not read as a pass.

    When the caller knows the frozen gold set and/or the model being activated, passing
    ``expected_*`` binds the evidence to them: a real digest from a *different* benchmark, or a
    gate pass earned by a *different* model version, is refused.
    """

    if not isinstance(evidence, Mapping):
        return False, "no benchmark promotion evidence supplied"

    exit_code = evidence.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        return False, f"promotion evidence exit_code {exit_code!r} is not an int"
    if exit_code != _PROMOTION_EXIT_OK:
        return False, f"promotion evidence exit_code is {exit_code!r}, not 0"

    checksum = evidence.get("gold_checksum")
    if not isinstance(checksum, str) or not _GOLD_CHECKSUM_RE.fullmatch(checksum):
        return False, (
            f"promotion evidence gold_checksum {checksum!r} is not a sha256:<64-hex> digest"
        )
    if expected_gold_checksum is not None and checksum != expected_gold_checksum:
        return False, (
            "promotion evidence was earned against a different gold set "
            f"({checksum} != {expected_gold_checksum})"
        )

    model_version = evidence.get("model_version")
    if not isinstance(model_version, str) or not model_version.strip():
        return False, f"promotion evidence model_version {model_version!r} is not a named string"
    if expected_model_version is not None and model_version.strip() != expected_model_version:
        return False, (
            f"promotion evidence names model {model_version.strip()!r}, "
            f"not the model being activated ({expected_model_version!r})"
        )
    return True, "benchmark promotion evidence verified"


@dataclass
class CapabilityStatus:
    name: str
    enabled: bool
    available: bool
    active: bool
    missing_modules: list[str]
    reason: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "available": self.available,
            "active": self.active,
            "missing_modules": list(self.missing_modules),
            "reason": self.reason,
            "provenance": dict(self.provenance),
            "engine": ENGINE,
        }


@dataclass
class BackendDecision:
    """The auditable outcome of a heavy-vs-fallback selection."""

    capability: str
    backend: str  # "heavy" | "fallback" | "unavailable"
    reason: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "backend": self.backend,
            "reason": self.reason,
            "provenance": dict(self.provenance),
            "engine": ENGINE,
        }


def capability_status(
    name: str,
    *,
    promotion_evidence: Mapping[str, Any] | None = None,
    expected_gold_checksum: str | None = None,
    expected_model_version: str | None = None,
    probe: Callable[[str], bool] | None = None,
    env: Mapping[str, str] | None = None,
) -> CapabilityStatus:
    """The full activation picture for one capability — every input is injectable for tests."""

    spec = CAPABILITIES.get(name)
    if spec is None:
        raise KeyError(f"Unknown reaction ML capability {name!r}")
    probe = probe or _module_available
    environment = env if env is not None else os.environ

    enabled = _flag_on(spec, environment)
    probed = {module: bool(probe(module)) for module in spec.required_modules}
    if spec.name in _ANY_ONE_MODULE and spec.required_modules:
        available = any(probed.values())
        missing = [] if available else list(spec.required_modules)
    else:
        available = all(probed.values())
        missing = [module for module, ok in probed.items() if not ok]

    evidence_ok = True
    evidence_reason = "no promotion evidence required"
    if spec.requires_promotion_evidence:
        evidence_ok, evidence_reason = _valid_promotion_evidence(
            promotion_evidence,
            expected_gold_checksum=expected_gold_checksum,
            expected_model_version=expected_model_version,
        )

    active = enabled and available and evidence_ok
    if not enabled:
        reason = f"disabled — set {spec.flag_env}=1 to opt in (default off)"
    elif not available:
        reason = f"dependencies missing: {missing}. {spec.install_hint}".strip()
    elif not evidence_ok:
        reason = evidence_reason
    else:
        reason = "active"

    provenance: dict[str, Any] = {
        "flag_env": spec.flag_env,
        "flag_value": environment.get(spec.flag_env, ""),
        "probed_modules": probed,
        "requires_promotion_evidence": spec.requires_promotion_evidence,
        "promotion_evidence": evidence_reason,
    }
    if spec.requires_promotion_evidence and isinstance(promotion_evidence, Mapping):
        provenance["promotion_model_version"] = promotion_evidence.get("model_version")
        provenance["promotion_gold_checksum"] = promotion_evidence.get("gold_checksum")
    return CapabilityStatus(
        name=spec.name,
        enabled=enabled,
        available=available,
        active=active,
        missing_modules=missing,
        reason=reason,
        provenance=provenance,
    )


def resolve_backend(
    name: str,
    *,
    promotion_evidence: Mapping[str, Any] | None = None,
    expected_gold_checksum: str | None = None,
    expected_model_version: str | None = None,
    probe: Callable[[str], bool] | None = None,
    env: Mapping[str, str] | None = None,
) -> BackendDecision:
    """Pick heavy vs fallback for a capability, with the decision's full provenance.

    ``heavy`` only when the flag is on, every dependency is present, and (where required) the
    R11 promotion evidence verifies. Otherwise ``fallback`` when a Phase-A/B path exists, else
    ``unavailable`` — stated plainly, never silently degraded.
    """

    status = capability_status(
        name,
        promotion_evidence=promotion_evidence,
        expected_gold_checksum=expected_gold_checksum,
        expected_model_version=expected_model_version,
        probe=probe,
        env=env,
    )
    spec = CAPABILITIES[name]
    if status.active:
        return BackendDecision(
            capability=name,
            backend="heavy",
            reason=f"{spec.description} ACTIVE: {status.reason}",
            provenance=status.as_dict(),
        )
    has_fallback = not spec.fallback.startswith("None")
    return BackendDecision(
        capability=name,
        backend="fallback" if has_fallback else "unavailable",
        reason=f"{status.reason}. Fallback: {spec.fallback}",
        provenance=status.as_dict(),
    )


def require_capability(
    name: str,
    *,
    promotion_evidence: Mapping[str, Any] | None = None,
    expected_gold_checksum: str | None = None,
    expected_model_version: str | None = None,
    probe: Callable[[str], bool] | None = None,
    env: Mapping[str, str] | None = None,
) -> CapabilityStatus:
    """Return the status if the capability is ACTIVE; raise with the honest reason otherwise."""

    status = capability_status(
        name,
        promotion_evidence=promotion_evidence,
        expected_gold_checksum=expected_gold_checksum,
        expected_model_version=expected_model_version,
        probe=probe,
        env=env,
    )
    if not status.active:
        raise CapabilityUnavailableError(f"{name}: {status.reason}")
    return status


def all_capability_statuses(
    *,
    probe: Callable[[str], bool] | None = None,
    env: Mapping[str, str] | None = None,
) -> list[CapabilityStatus]:
    """Status of every Phase-C capability (for an ops/enablement readout)."""

    return [
        capability_status(name, probe=probe, env=env) for name in sorted(CAPABILITIES)
    ]
