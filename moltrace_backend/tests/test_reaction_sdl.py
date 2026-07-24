"""Unit tests for R15 SDL (pure; simulated driver, injected clock, every interlock exercised)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nmrcheck.reaction_sdl import (
    MODE_AUTONOMOUS,
    MODE_MANUAL,
    MODE_SUPERVISED,
    ExecutionEnvelope,
    SDLController,
    SDLInterlockError,
    SDLStep,
    SimulatedDriver,
    sdl_site_enabled,
)

_T0 = datetime(2026, 7, 1, 9, 0, 0)


def _envelope(**overrides) -> ExecutionEnvelope:
    defaults = dict(
        approved_by="dr.chemist",
        expires_at=_T0 + timedelta(hours=2),
        allowed_actions=frozenset({"dispense", "heat", "stir", "sample", "analyze"}),
        max_temperature_c=120.0,
        max_volume_ml=50.0,
        max_steps=10,
    )
    defaults.update(overrides)
    return ExecutionEnvelope(**defaults)


_APPROVAL = {"execution_batch_id": 42, "approved_by": "dr.chemist"}


def _armed(
    driver: SimulatedDriver | None = None,
    *,
    mode: str = MODE_AUTONOMOUS,
    envelope: ExecutionEnvelope | None = None,
    watchdog_s: float = 60.0,
) -> tuple[SDLController, SimulatedDriver]:
    driver = driver or SimulatedDriver()
    controller = SDLController(driver, site_enabled=True, watchdog_timeout_s=watchdog_s)
    controller.arm(
        operator="op.human",
        mode=mode,
        envelope=envelope or _envelope(),
        safety_gate_status="clear",
        execution_approval=_APPROVAL,
        now=_T0,
    )
    return controller, driver


def _step(step_id: str = "s1", action: str = "heat", **params) -> SDLStep:
    return SDLStep(step_id=step_id, action=action, parameters=params)


# --- arming interlocks -------------------------------------------------------------------------
def test_site_flag_off_refuses_arming():
    controller = SDLController(SimulatedDriver(), site_enabled=False)
    with pytest.raises(SDLInterlockError, match="not enabled at this site"):
        controller.arm(
            operator="op",
            mode=MODE_AUTONOMOUS,
            envelope=_envelope(),
            safety_gate_status="clear",
            execution_approval=_APPROVAL,
            now=_T0,
        )


def test_manual_mode_is_the_default_and_cannot_be_armed():
    controller = SDLController(SimulatedDriver(), site_enabled=True)
    assert controller.mode == MODE_MANUAL
    with pytest.raises(SDLInterlockError, match="Manual mode is the default"):
        controller.arm(
            operator="op",
            mode=MODE_MANUAL,
            envelope=_envelope(),
            safety_gate_status="clear",
            execution_approval=_APPROVAL,
            now=_T0,
        )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (dict(safety_gate_status="review_pending"), "requires 'clear'"),
        (dict(safety_gate_status="blocked"), "requires 'clear'"),
        (dict(execution_approval=None), "no execution approval"),
        (dict(execution_approval={"approved_by": "x"}), "no execution batch"),
        (dict(execution_approval={"execution_batch_id": 1, "approved_by": " "}), "no human"),
        (dict(operator="  "), "named human operator"),
        (dict(mode="warp"), "Unknown autonomy mode"),
    ],
)
def test_arming_interlocks(kwargs, match):
    controller = SDLController(SimulatedDriver(), site_enabled=True)
    base = dict(
        operator="op",
        mode=MODE_AUTONOMOUS,
        envelope=_envelope(),
        safety_gate_status="clear",
        execution_approval=_APPROVAL,
        now=_T0,
    )
    base.update(kwargs)
    with pytest.raises(SDLInterlockError, match=match):
        controller.arm(**base)


def test_expired_envelope_and_unhealthy_driver_refuse_arming():
    controller = SDLController(SimulatedDriver(), site_enabled=True)
    with pytest.raises(SDLInterlockError, match="expired"):
        controller.arm(
            operator="op",
            mode=MODE_AUTONOMOUS,
            envelope=_envelope(expires_at=_T0 - timedelta(minutes=1)),
            safety_gate_status="clear",
            execution_approval=_APPROVAL,
            now=_T0,
        )
    sick = SimulatedDriver()
    sick.fail()
    with pytest.raises(SDLInterlockError, match="unhealthy"):
        SDLController(sick, site_enabled=True).arm(
            operator="op",
            mode=MODE_AUTONOMOUS,
            envelope=_envelope(),
            safety_gate_status="clear",
            execution_approval=_APPROVAL,
            now=_T0,
        )


def test_envelope_actions_must_be_within_driver_capabilities():
    driver = SimulatedDriver(capabilities=frozenset({"dispense"}))
    with pytest.raises(SDLInterlockError, match="cannot perform"):
        SDLController(driver, site_enabled=True).arm(
            operator="op",
            mode=MODE_AUTONOMOUS,
            envelope=_envelope(allowed_actions=frozenset({"dispense", "heat"})),
            safety_gate_status="clear",
            execution_approval=_APPROVAL,
            now=_T0,
        )


# --- per-step interlocks -----------------------------------------------------------------------
def test_autonomous_steps_execute_within_the_envelope():
    controller, driver = _armed()
    result = controller.run_step(
        _step("s1", "analyze"), safety_gate_status="clear", now=_T0 + timedelta(seconds=10)
    )
    assert result.ok is True
    assert driver.executed[0].step_id == "s1"
    assert controller.steps_run == 1


def test_unarmed_controller_executes_nothing():
    controller = SDLController(SimulatedDriver(), site_enabled=True)
    with pytest.raises(SDLInterlockError, match="not armed"):
        controller.run_step(_step(), safety_gate_status="clear", now=_T0)


def test_gate_flip_mid_run_aborts_and_disarms():
    controller, driver = _armed()
    with pytest.raises(SDLInterlockError, match="run aborted"):
        controller.run_step(
            _step(), safety_gate_status="blocked", now=_T0 + timedelta(seconds=5)
        )
    assert controller.armed is False
    assert controller.mode == MODE_MANUAL
    assert driver.aborted is True
    events = [entry["event"] for entry in controller.journal]
    assert "aborted" in events and "disarmed" in events


def test_envelope_expiry_mid_run_aborts():
    controller, _ = _armed(envelope=_envelope(expires_at=_T0 + timedelta(minutes=1)))
    with pytest.raises(SDLInterlockError, match="expired"):
        controller.run_step(
            _step(), safety_gate_status="clear", now=_T0 + timedelta(minutes=2)
        )
    assert controller.armed is False


def test_watchdog_timeout_aborts():
    controller, _ = _armed(watchdog_s=30.0)
    with pytest.raises(SDLInterlockError, match="watchdog"):
        controller.run_step(
            _step(), safety_gate_status="clear", now=_T0 + timedelta(minutes=5)
        )
    assert controller.armed is False


def test_heartbeat_keeps_the_watchdog_alive():
    controller, _ = _armed(watchdog_s=30.0)
    controller.heartbeat(_T0 + timedelta(seconds=25))
    result = controller.run_step(
        _step("s1", "analyze"), safety_gate_status="clear", now=_T0 + timedelta(seconds=50)
    )
    assert result.ok is True


def test_out_of_envelope_action_and_caps_abort():
    controller, _ = _armed(envelope=_envelope(allowed_actions=frozenset({"heat"})))
    with pytest.raises(SDLInterlockError, match="outside the approved envelope"):
        controller.run_step(_step("s1", "dispense"), safety_gate_status="clear", now=_T0)
    assert controller.armed is False  # envelope violations are fail-closed

    controller2, _ = _armed()
    with pytest.raises(SDLInterlockError, match="exceeds the envelope cap"):
        controller2.run_step(
            _step("s1", "heat", temperature_c=300.0), safety_gate_status="clear", now=_T0
        )
    assert controller2.armed is False


def test_step_budget_exhaustion_aborts():
    controller, _ = _armed(envelope=_envelope(max_steps=1))
    controller.run_step(_step("s1", "analyze"), safety_gate_status="clear", now=_T0)
    with pytest.raises(SDLInterlockError, match="budget exhausted"):
        controller.run_step(_step("s2", "analyze"), safety_gate_status="clear", now=_T0)


def test_supervised_mode_requires_per_step_confirmation():
    controller, _ = _armed(mode=MODE_SUPERVISED)
    with pytest.raises(SDLInterlockError, match="confirmation for every step"):
        controller.run_step(_step(), safety_gate_status="clear", now=_T0)
    result = controller.run_step(
        _step(), safety_gate_status="clear", now=_T0, confirmed_by="op.human"
    )
    assert result.ok is True


def test_driver_failure_aborts_and_hands_back_to_the_human():
    driver = SimulatedDriver()
    controller, _ = _armed(driver)
    driver.fail()  # instrument fault after arming
    with pytest.raises(SDLInterlockError, match="unhealthy"):
        controller.run_step(_step(), safety_gate_status="clear", now=_T0)
    assert controller.armed is False


# --- journal ----------------------------------------------------------------------------------
def test_journal_chain_verifies_and_detects_tampering():
    controller, _ = _armed()
    controller.run_step(_step("s1", "analyze"), safety_gate_status="clear", now=_T0)
    controller.run_step(_step("s2", "sample"), safety_gate_status="clear", now=_T0)
    assert controller.verify_journal() is True
    # Tamper with a recorded step after the fact.
    controller._journal[1]["payload"]["step_id"] = "forged"
    assert controller.verify_journal() is False


def test_simulated_driver_is_deterministic():
    a = SimulatedDriver(seed=1).execute(_step("s1", "analyze"))
    b = SimulatedDriver(seed=1).execute(_step("s1", "analyze"))
    c = SimulatedDriver(seed=2).execute(_step("s1", "analyze"))
    assert a.data["yield_percent"] == b.data["yield_percent"]
    assert a.data["yield_percent"] != c.data["yield_percent"]


# --- site enablement ---------------------------------------------------------------------------
def test_sdl_site_enabled_reads_the_capability_flag():
    assert sdl_site_enabled(env={}) is False
    assert sdl_site_enabled(env={"MOLTRACE_REACTION_SDL": "1"}) is True


# --- remediation-verification regressions (adversarial re-review) -------------------------------
@pytest.mark.parametrize(
    "overrides",
    [
        {"max_temperature_c": float("nan")},
        {"max_volume_ml": float("nan")},
        {"max_steps": float("nan")},
        {"max_temperature_c": float("inf")},
        {"max_volume_ml": "hot"},
    ],
)
def test_non_finite_envelope_caps_are_refused_at_validation(overrides):
    """A NaN cap passes every ORDERING check, then silently disables its own bound.

    `NaN <= 0` is False, so a bounds-only validate() lets it through; `value > NaN` is also
    False, so check_step then waves every parameter past that cap. The caps must be screened
    for finiteness, not just for sign.
    """

    envelope = _envelope(**overrides)
    with pytest.raises(SDLInterlockError):
        envelope.validate()
    controller = SDLController(SimulatedDriver(), site_enabled=True)
    with pytest.raises(SDLInterlockError):
        controller.arm(
            operator="op.human",
            mode=MODE_AUTONOMOUS,
            envelope=envelope,
            safety_gate_status="clear",
            execution_approval=_APPROVAL,
            now=_T0,
        )
    assert controller.armed is False


def test_backwards_clock_raises_the_interlock_error_not_an_attribute_error():
    """abort() nulls `_last_seen_at`; reading it afterwards would skip the caller's handler."""

    controller, driver = _armed()
    controller.run_step(_step("s1"), safety_gate_status="clear", now=_T0 + timedelta(seconds=10))
    with pytest.raises(SDLInterlockError, match="moved backwards"):
        controller.run_step(_step("s2"), safety_gate_status="clear", now=_T0 + timedelta(seconds=5))
    assert controller.armed is False
    assert driver.aborted is True


def test_future_dated_heartbeat_cannot_permanently_defeat_the_watchdog():
    """One unvalidated future beat makes `now - last_heartbeat` negative forever after.

    The heartbeat shares run_step's monotonic timeline, so a future beat makes every
    genuinely-timed step non-monotonic — loud and fail-closed, not a silently dead watchdog.
    """

    controller, driver = _armed(watchdog_s=60.0)
    controller.heartbeat(_T0 + timedelta(days=365))
    with pytest.raises(SDLInterlockError, match="moved backwards"):
        controller.run_step(
            _step("s1"), safety_gate_status="clear", now=_T0 + timedelta(seconds=30)
        )
    assert controller.armed is False
    assert driver.aborted is True


def test_backwards_heartbeat_aborts_rather_than_rewinding_the_clock():
    controller, driver = _armed()
    controller.heartbeat(_T0 + timedelta(seconds=30))
    with pytest.raises(SDLInterlockError, match="moved backwards"):
        controller.heartbeat(_T0 + timedelta(seconds=5))
    assert controller.armed is False
    assert driver.aborted is True


def test_journal_payloads_are_deep_copied_not_one_level_copied():
    """A one-level copy leaves nested objects aliased to the caller's own references."""

    controller = SDLController(SimulatedDriver(), site_enabled=True)
    # arm() RETURNS the provenance dict it also committed; the nested list must not be shared.
    provenance = controller.arm(
        operator="op.human",
        mode=MODE_AUTONOMOUS,
        envelope=_envelope(),
        safety_gate_status="clear",
        execution_approval=_APPROVAL,
        now=_T0,
    )
    provenance["allowed_actions"].append("detonate")
    assert "detonate" not in controller.journal[0]["payload"]["allowed_actions"]

    step = SDLStep(step_id="s1", action="heat", parameters={"profile": {"temperature_c": 80}})
    controller.run_step(step, safety_gate_status="clear", now=_T0 + timedelta(seconds=10))
    entry = controller.journal[-1]
    entry["payload"]["parameters"]["profile"]["temperature_c"] = 999
    assert controller.journal[-1]["payload"]["parameters"]["profile"]["temperature_c"] == 80
    assert controller.verify_journal() is True


class _MalformedDriver(SimulatedDriver):
    """Returns garbage instead of raising — the step still ran on real hardware."""

    def execute(self, step):  # type: ignore[override]
        self.executed.append(step)
        return {"ok": True}  # not a StepResult


def test_malformed_driver_result_journals_and_aborts():
    controller, driver = _armed(_MalformedDriver())
    with pytest.raises(SDLInterlockError, match="malformed result"):
        controller.run_step(_step("s1"), safety_gate_status="clear", now=_T0 + timedelta(seconds=5))
    assert controller.armed is False
    assert driver.aborted is True
    events = [entry["event"] for entry in controller.journal]
    assert "step_malformed_result" in events
    assert controller.verify_journal() is True
