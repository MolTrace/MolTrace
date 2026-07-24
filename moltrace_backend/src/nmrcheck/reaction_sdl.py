"""Repho R15 — self-driving-lab (SDL) hardware-abstraction layer (fail-closed autonomy ladder).

The full-automation variant of the R5 half-closed DMTA loop, built on one principle: **more
automation never means fewer checks**. Climbing the autonomy ladder automates the *make/test*
steps — it never removes an interlock:

* ``manual`` (the default, everywhere) — the SDL layer refuses to execute anything; the loop runs
  exactly as in R5 (human make/test, safety-gated execution batches).
* ``supervised`` — the robot executes, but **every step** requires a fresh human confirmation.
* ``autonomous`` — the robot executes a batch inside a **human-approved execution envelope**
  (action allowlist, temperature/volume caps, step budget, expiry) without per-step confirmation.

To run even one step, ALL of the following must hold, and any of them failing mid-run aborts and
disarms (the R8 lesson — a gate can only tighten, never relax):

1. the site flag (``MOLTRACE_REACTION_SDL``) is on — SDL is opt-in per deployment;
2. a named human **armed** the controller with an explicit envelope (arming expires);
3. the R6 safety gate is ``clear`` — re-checked on *every* step, not just at arming;
4. a human-committed execution approval (the R5/R6 batch contract) is on record;
5. the driver is healthy and the **dead-man watchdog** heartbeat is fresh;
6. the step is inside the envelope (allowed action, within caps, within the step budget).

Every transition and step is written to a **tamper-evident hash-chained journal** (the Annex-22
habit applied to physical execution): each entry commits to its predecessor's hash, so an
after-the-fact edit breaks verification.

The hardware seam is :class:`InstrumentDriver`; :class:`SimulatedDriver` is a deterministic
implementation so the entire ladder is demoable and testable without a robot. Site drivers plug in
per deployment. Pure: no DB / HTTP / clock (every timestamp is injected) / randomness (the
simulator is hash-deterministic).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from . import reaction_ml

ENGINE = "reaction_sdl.v1"

MODE_MANUAL = "manual"
MODE_SUPERVISED = "supervised"
MODE_AUTONOMOUS = "autonomous"
_MODES = (MODE_MANUAL, MODE_SUPERVISED, MODE_AUTONOMOUS)

SDL_DISCLAIMER = (
    "SDL execution is a hardware-automation layer under the same safety, regulatory, and "
    "human-approval gates as manual execution. Manual mode is the default; autonomy automates "
    "make/test inside a human-approved envelope and never bypasses a gate."
)

_GENESIS = "sha256:" + hashlib.sha256(b"reaction_sdl.v1:genesis").hexdigest()


class SDLInterlockError(Exception):
    """Raised when an interlock refuses an operation (arming, execution, or configuration)."""


# --------------------------------------------------------------------------- #
# Hardware seam.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SDLStep:
    step_id: str
    action: str  # e.g. dispense | heat | stir | sample | analyze
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    step_id: str
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class InstrumentDriver(Protocol):
    """What a site-specific robot driver must provide. The engine never imports vendor SDKs."""

    def capabilities(self) -> frozenset[str]: ...

    def healthy(self) -> bool: ...

    def execute(self, step: SDLStep) -> StepResult: ...

    def abort(self) -> None: ...


class SimulatedDriver:
    """Deterministic simulated instrument — the whole ladder runs without hardware.

    Results are pure functions of ``(seed, step_id, action)`` via a content hash, so demos and
    tests are reproducible on any machine.
    """

    def __init__(self, *, seed: int = 20260615, capabilities: frozenset[str] | None = None) -> None:
        self.seed = seed
        self._capabilities = capabilities or frozenset(
            {"dispense", "heat", "stir", "sample", "analyze"}
        )
        self._healthy = True
        self.aborted = False
        self.executed: list[SDLStep] = []

    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    def healthy(self) -> bool:
        return self._healthy

    def fail(self) -> None:  # test/demo hook: simulate an instrument fault
        self._healthy = False

    def execute(self, step: SDLStep) -> StepResult:
        if not self._healthy:
            return StepResult(step_id=step.step_id, ok=False, error="instrument fault")
        self.executed.append(step)
        digest = hashlib.sha256(f"{self.seed}:{step.step_id}:{step.action}".encode()).digest()
        fraction = int.from_bytes(digest[:8], "big") / float(1 << 64)
        data: dict[str, Any] = {"simulated": True}
        if step.action == "analyze":
            data["yield_percent"] = round(20.0 + 75.0 * fraction, 2)
        return StepResult(step_id=step.step_id, ok=True, data=data)

    def abort(self) -> None:
        self.aborted = True


# --------------------------------------------------------------------------- #
# The human-approved execution envelope.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ExecutionEnvelope:
    approved_by: str
    expires_at: datetime
    allowed_actions: frozenset[str]
    max_temperature_c: float
    max_volume_ml: float
    max_steps: int

    def validate(self) -> None:
        if not self.approved_by.strip():
            raise SDLInterlockError("Envelope has no approving human.")
        if not self.allowed_actions:
            raise SDLInterlockError("Envelope allows no actions.")
        # The caps must be finite BEFORE they are compared. Ordering checks alone are not a
        # screen: `NaN <= 0` is False, so a NaN cap would pass validate() and then silently
        # disable its bound in check_step (`value > NaN` is also False). Guarding only the step
        # parameters and not the envelope itself leaves the same hole on the other side.
        for label, cap in (
            ("step budget", self.max_steps),
            ("temperature cap", self.max_temperature_c),
            ("volume cap", self.max_volume_ml),
        ):
            if isinstance(cap, bool) or not isinstance(cap, (int, float)):
                raise SDLInterlockError(f"Envelope {label} {cap!r} is not numeric.")
            if not math.isfinite(float(cap)):
                raise SDLInterlockError(f"Envelope {label} {cap!r} is not finite.")
        if self.max_steps <= 0:
            raise SDLInterlockError("Envelope step budget must be positive.")
        if self.max_temperature_c <= 0 or self.max_volume_ml <= 0:
            raise SDLInterlockError("Envelope caps must be positive.")

    def check_step(self, step: SDLStep) -> None:
        if step.action not in self.allowed_actions:
            raise SDLInterlockError(
                f"Action {step.action!r} is outside the approved envelope "
                f"(allowed: {sorted(self.allowed_actions)})."
            )
        for label, cap in (
            ("temperature_c", self.max_temperature_c),
            ("volume_ml", self.max_volume_ml),
        ):
            raw = step.parameters.get(label)
            if raw is None:
                continue
            # A non-numeric or non-finite parameter is refused rather than compared: NaN fails
            # EVERY comparison, so `NaN > cap` is False and an unchecked value would execute.
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise SDLInterlockError(
                    f"Step {label} {raw!r} is not numeric; refusing to execute."
                ) from exc
            if not math.isfinite(value):
                raise SDLInterlockError(
                    f"Step {label} {raw!r} is not finite; refusing to execute."
                )
            if value > cap:
                raise SDLInterlockError(
                    f"Step {label} {raw!r} exceeds the envelope cap {cap}."
                )


def _step_result_shape_error(result: Any, step: SDLStep) -> str | None:
    """Return why ``result`` is not a usable :class:`StepResult`, or None when it is fine."""

    for attr, kind in (("step_id", str), ("ok", bool), ("data", Mapping)):
        if not hasattr(result, attr):
            return f"missing {attr!r}"
        value = getattr(result, attr)
        if kind is bool:
            if not isinstance(value, bool):
                return f"{attr!r} is {value!r}, not a bool"
        elif not isinstance(value, kind):
            return f"{attr!r} is {value!r}, not a {kind.__name__}"
    if result.step_id != step.step_id:
        return f"step_id {result.step_id!r} does not match the requested step {step.step_id!r}"
    error = getattr(result, "error", None)
    if error is not None and not isinstance(error, str):
        return f"'error' is {error!r}, neither None nor a string"
    return None


def _valid_execution_approval(approval: Mapping[str, Any] | None) -> tuple[bool, str]:
    """The R5/R6 contract: a human must have committed the execution batch being automated."""

    if not isinstance(approval, Mapping):
        return False, "no execution approval supplied"
    if not str(approval.get("approved_by") or "").strip():
        return False, "execution approval names no human approver"
    if approval.get("execution_batch_id") in (None, ""):
        return False, "execution approval references no execution batch"
    return True, "execution approval verified"


# --------------------------------------------------------------------------- #
# The controller — interlocks + tamper-evident journal.
# --------------------------------------------------------------------------- #
class SDLController:
    """Fail-closed SDL execution controller. Times are injected; it never reads a clock."""

    def __init__(
        self,
        driver: InstrumentDriver,
        *,
        site_enabled: bool,
        watchdog_timeout_s: float = 60.0,
    ) -> None:
        self.driver = driver
        self.site_enabled = bool(site_enabled)
        self.watchdog_timeout = timedelta(seconds=float(watchdog_timeout_s))
        self.mode = MODE_MANUAL
        self.armed = False
        self.envelope: ExecutionEnvelope | None = None
        self.operator: str | None = None
        self.steps_run = 0
        self._last_heartbeat: datetime | None = None
        self._last_seen_at: datetime | None = None
        self._journal: list[dict[str, Any]] = []

    # -- journal ------------------------------------------------------------ #
    def _record(self, event: str, payload: Mapping[str, Any], at: datetime) -> None:
        prev_hash = self._journal[-1]["entry_hash"] if self._journal else _GENESIS
        body = {
            "index": len(self._journal),
            "at": at.isoformat(),
            "event": event,
            # DEEP copy, not dict(): a one-level copy leaves nested lists/dicts aliased to the
            # caller's objects, so mutating one after the fact would silently change what the
            # committed chain says while every recomputed hash still matched.
            "payload": copy.deepcopy(dict(payload)),
            "prev_hash": prev_hash,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
        entry_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self._journal.append({**body, "entry_hash": entry_hash})

    @property
    def journal(self) -> list[dict[str, Any]]:
        # Deep-copied: a caller holding the returned list must not be able to mutate the payloads
        # the chain commits to (which would let a tamper pass verification via shared references).
        return [
            {**entry, "payload": copy.deepcopy(entry.get("payload") or {})}
            for entry in self._journal
        ]

    @property
    def journal_head(self) -> dict[str, Any]:
        """The anchor a caller must persist externally to make truncation detectable.

        A hash chain proves that entry *n* follows entry *n-1*; it cannot, on its own, prove that
        entry *n* was the LAST one — lopping entries off the tail leaves a perfectly valid chain.
        Persisting this head (count + final hash) elsewhere and passing it back to
        :meth:`verify_journal` closes that gap.
        """

        return {
            "entry_count": len(self._journal),
            "head_hash": self._journal[-1]["entry_hash"] if self._journal else _GENESIS,
        }

    def verify_journal(
        self,
        *,
        expected_entry_count: int | None = None,
        expected_head_hash: str | None = None,
    ) -> bool:
        """Recompute the hash chain; False on any tampering (edit, deletion, reorder).

        Pass the previously-persisted :attr:`journal_head` values to additionally detect **tail
        truncation**, which the chain alone cannot reveal.
        """

        prev_hash = _GENESIS
        for index, entry in enumerate(self._journal):
            body = {
                "index": entry.get("index"),
                "at": entry.get("at"),
                "event": entry.get("event"),
                "payload": entry.get("payload"),
                "prev_hash": entry.get("prev_hash"),
            }
            canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
            expected = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if (
                entry.get("index") != index
                or entry.get("prev_hash") != prev_hash
                or entry.get("entry_hash") != expected
            ):
                return False
            prev_hash = entry["entry_hash"]
        if expected_entry_count is not None and len(self._journal) != expected_entry_count:
            return False
        if expected_head_hash is not None and prev_hash != expected_head_hash:
            return False
        return True

    # -- arming -------------------------------------------------------------- #
    def arm(
        self,
        *,
        operator: str,
        mode: str,
        envelope: ExecutionEnvelope,
        safety_gate_status: str,
        execution_approval: Mapping[str, Any] | None,
        now: datetime,
    ) -> dict[str, Any]:
        """Arm the controller. Every interlock is checked here AND re-checked per step."""

        if not self.site_enabled:
            raise SDLInterlockError(
                "SDL is not enabled at this site (set MOLTRACE_REACTION_SDL=1 to opt in)."
            )
        if mode not in _MODES:
            raise SDLInterlockError(f"Unknown autonomy mode {mode!r}.")
        if mode == MODE_MANUAL:
            raise SDLInterlockError(
                "Manual mode is the default and needs no arming — the SDL layer executes nothing."
            )
        if not operator.strip():
            raise SDLInterlockError("Arming requires a named human operator.")
        envelope.validate()
        if envelope.expires_at <= now:
            raise SDLInterlockError("Envelope is already expired.")
        if str(safety_gate_status).lower() != "clear":
            raise SDLInterlockError(
                f"Safety gate is {safety_gate_status!r}; arming requires 'clear'."
            )
        approval_ok, approval_reason = _valid_execution_approval(execution_approval)
        if not approval_ok:
            raise SDLInterlockError(f"Execution approval invalid: {approval_reason}.")
        if not self.driver.healthy():
            raise SDLInterlockError("Instrument driver reports unhealthy.")
        missing = envelope.allowed_actions - self.driver.capabilities()
        if missing:
            raise SDLInterlockError(
                f"Envelope allows action(s) the driver cannot perform: {sorted(missing)}."
            )

        self.mode = mode
        self.armed = True
        self.envelope = envelope
        self.operator = operator
        self.steps_run = 0
        self._last_heartbeat = now
        self._last_seen_at = now
        provenance = {
            "operator": operator,
            "mode": mode,
            "approved_by": envelope.approved_by,
            "envelope_expires_at": envelope.expires_at.isoformat(),
            "allowed_actions": sorted(envelope.allowed_actions),
            "max_temperature_c": envelope.max_temperature_c,
            "max_volume_ml": envelope.max_volume_ml,
            "max_steps": envelope.max_steps,
            "safety_gate_status": safety_gate_status,
            "execution_approval": dict(execution_approval or {}),
            "disclaimer": SDL_DISCLAIMER,
            "engine": ENGINE,
        }
        self._record("armed", provenance, now)
        return provenance

    def heartbeat(self, now: datetime) -> None:
        """Refresh the dead-man watchdog. Rejected — and aborts — if time moved backwards.

        The heartbeat shares ONE monotonic timeline with :meth:`run_step` (``_last_seen_at``).
        Without that, an unvalidated heartbeat is a hole straight through the watchdog: a single
        future-dated beat makes ``now - _last_heartbeat`` negative forever after, so the watchdog
        can never expire again no matter how long the operator is actually gone. Advancing the
        shared clock instead means a future-dated beat immediately makes every genuinely-timed
        step non-monotonic — the failure is loud and fail-closed, not silent.
        """

        if not self.armed:
            return
        last_seen = self._last_seen_at
        if last_seen is not None and now < last_seen:
            self.abort(reason="non-monotonic clock (heartbeat)", now=last_seen)
            raise SDLInterlockError(
                f"Heartbeat time moved backwards ({now.isoformat()} < "
                f"{last_seen.isoformat()}); controller aborted and disarmed."
            )
        self._last_heartbeat = now
        self._last_seen_at = now

    def disarm(self, *, reason: str, now: datetime) -> None:
        if self.armed or self.mode != MODE_MANUAL:
            self._record("disarmed", {"reason": reason}, now)
        self.armed = False
        self.mode = MODE_MANUAL
        self.envelope = None
        self.operator = None
        self._last_heartbeat = None
        self._last_seen_at = None

    def abort(self, *, reason: str, now: datetime) -> None:
        """Immediate stop: disarm FIRST, then abort the instrument. Always safe to call.

        Disarming precedes the driver call deliberately — a driver whose ``abort()`` raises must
        never leave the controller armed and able to run another step. The driver failure is
        journalled and re-raised after the controller is already safe.
        """

        self._record("aborted", {"reason": reason}, now)
        self.disarm(reason=f"aborted: {reason}", now=now)
        try:
            self.driver.abort()
        except Exception as exc:  # noqa: BLE001 - the controller is already disarmed
            self._record("driver_abort_failed", {"reason": reason, "error": str(exc)}, now)
            raise SDLInterlockError(
                f"Controller disarmed, but the driver failed to abort: {exc}. "
                "Physically verify the instrument."
            ) from exc

    # -- execution ------------------------------------------------------------ #
    def run_step(
        self,
        step: SDLStep,
        *,
        safety_gate_status: str,
        now: datetime,
        confirmed_by: str | None = None,
    ) -> StepResult:
        """Execute ONE step through every interlock. Any violation aborts fail-closed."""

        if not self.armed or self.envelope is None:
            raise SDLInterlockError("Controller is not armed (manual mode executes nothing).")
        # Time only moves forward. A backwards `now` would otherwise un-expire an envelope and
        # reset the watchdog, so it is refused (and aborts) rather than trusted.
        # Bind before aborting: abort() -> disarm() sets `_last_seen_at` to None, so reading the
        # attribute afterwards would raise AttributeError and skip the caller's fail-closed
        # SDLInterlockError handler entirely.
        last_seen = self._last_seen_at
        if last_seen is not None and now < last_seen:
            self.abort(reason="non-monotonic clock", now=last_seen)
            raise SDLInterlockError(
                f"Injected time moved backwards ({now.isoformat()} < "
                f"{last_seen.isoformat()}); run aborted and controller disarmed."
            )
        self._last_seen_at = now
        # The safety gate is re-checked on EVERY step and can only tighten (the R8 lesson):
        # any non-clear reading mid-run aborts the campaign, it never merely warns.
        if str(safety_gate_status).lower() != "clear":
            self.abort(reason=f"safety gate became {safety_gate_status!r} mid-run", now=now)
            raise SDLInterlockError(
                f"Safety gate is {safety_gate_status!r}; run aborted and controller disarmed."
            )
        if self.envelope.expires_at <= now:
            self.abort(reason="envelope expired", now=now)
            raise SDLInterlockError("Envelope expired; run aborted and controller disarmed.")
        if (
            self._last_heartbeat is None
            or now - self._last_heartbeat > self.watchdog_timeout
        ):
            self.abort(reason="watchdog heartbeat lost", now=now)
            raise SDLInterlockError(
                "Dead-man watchdog expired; run aborted and controller disarmed."
            )
        if self.steps_run >= self.envelope.max_steps:
            self.abort(reason="step budget exhausted", now=now)
            raise SDLInterlockError("Envelope step budget exhausted; controller disarmed.")
        if not self.driver.healthy():
            self.abort(reason="driver unhealthy", now=now)
            raise SDLInterlockError("Instrument driver unhealthy; run aborted.")
        try:
            self.envelope.check_step(step)
        except SDLInterlockError as exc:
            self.abort(reason=f"envelope violation: {exc}", now=now)
            raise
        if self.mode == MODE_SUPERVISED and not (confirmed_by or "").strip():
            raise SDLInterlockError(
                "Supervised mode requires a named human confirmation for every step."
            )

        try:
            result = self.driver.execute(step)
        except Exception as exc:  # noqa: BLE001 - a raising driver must not leave us armed
            self._record(
                "step_exception",
                {"step_id": step.step_id, "action": step.action, "error": str(exc)},
                now,
            )
            self.abort(reason=f"driver raised on step {step.step_id!r}: {exc}", now=now)
            raise SDLInterlockError(
                f"Driver raised executing step {step.step_id!r}: {exc}; controller disarmed."
            ) from exc
        # A driver that RETURNS garbage is as dangerous as one that raises: the step already ran
        # on real hardware, so a shape error here must journal and abort, not surface as an
        # unhandled AttributeError that leaves the controller armed and the step unrecorded.
        shape_error = _step_result_shape_error(result, step)
        if shape_error is not None:
            self._record(
                "step_malformed_result",
                {"step_id": step.step_id, "action": step.action, "error": shape_error},
                now,
            )
            self.abort(
                reason=f"driver returned a malformed result for step {step.step_id!r}", now=now
            )
            raise SDLInterlockError(
                f"Driver returned a malformed result for step {step.step_id!r}: {shape_error}; "
                "the step may have executed — controller disarmed, physically verify the "
                "instrument."
            )
        self.steps_run += 1
        self._last_heartbeat = now
        self._record(
            "step",
            {
                "step_id": step.step_id,
                "action": step.action,
                "parameters": dict(step.parameters),
                "ok": result.ok,
                "data": dict(result.data),
                "error": result.error,
                "confirmed_by": confirmed_by,
                "mode": self.mode,
                "steps_run": self.steps_run,
            },
            now,
        )
        if not result.ok:
            # A deviation is never retried blind: abort, hold, and hand back to the human.
            self.abort(reason=f"step {step.step_id!r} failed: {result.error}", now=now)
        return result


# --------------------------------------------------------------------------- #
# Site enablement helper (the reaction_ml flag, honestly surfaced).
# --------------------------------------------------------------------------- #
def sdl_site_enabled(
    *,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Whether this deployment has opted into SDL (``MOLTRACE_REACTION_SDL``)."""

    status = reaction_ml.capability_status("sdl_execution", env=env)
    return status.enabled and status.available
