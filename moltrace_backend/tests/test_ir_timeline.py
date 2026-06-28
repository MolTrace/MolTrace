"""IR notification-timeline engine (Security Prompt 20).

Validates the processor-vs-controller obligation computation + deadline evaluation —
the "notifications meet deadlines" acceptance criterion, made concrete and testable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from nmrcheck import ir_timeline as ir

_T0 = datetime(2026, 6, 26, 9, 0, 0, tzinfo=UTC)


def _by_key(obligations):
    return {o.key: o for o in obligations}


# --------------------------------------------------------------------------- processor hat


def test_processor_binding_deadline_is_notify_controller():
    obs = _by_key(
        ir.compute_obligations(
            _T0, role="processor", personal_data_breach=True, processor_sla_hours=24
        )
    )
    # MolTrace's binding obligation: notify the controller within the DPA SLA.
    assert obs["processor_notify_controller"].owner == "moltrace"
    assert obs["processor_notify_controller"].due_at == _T0 + timedelta(hours=24)
    assert obs["processor_notify_controller"].hard is True
    # The SA notification is the CONTROLLER's duty — tracked, but not MolTrace-owned.
    assert obs["controller_notify_sa"].owner == "controller (customer)"
    assert obs["controller_notify_sa"].hard is False
    # Art. 33(5) internal documentation always present for a personal-data breach.
    assert "internal_breach_record" in obs


def test_processor_does_not_emit_a_moltrace_sa_or_data_subject_duty():
    obs = ir.compute_obligations(_T0, role="processor", personal_data_breach=True)
    moltrace_owned = {o.key for o in obs if o.owner == "moltrace"}
    # MolTrace (as processor) never directly owns the SA / data-subject notification.
    assert "controller_notify_data_subjects" not in moltrace_owned
    assert all(o.owner != "moltrace" or o.key != "controller_notify_sa" for o in obs)


def test_controller_awareness_anchors_downstream_sa_clock():
    awareness = _T0 + timedelta(hours=10)
    obs = _by_key(
        ir.compute_obligations(
            _T0, role="processor", personal_data_breach=True, controller_awareness_at=awareness
        )
    )
    assert obs["controller_notify_sa"].due_at == awareness + timedelta(hours=72)


# --------------------------------------------------------------------------- controller hat


def test_controller_hat_owns_72h_sa_and_data_subject():
    obs = _by_key(
        ir.compute_obligations(
            _T0, role="controller", personal_data_breach=True, high_risk_to_subjects=True
        )
    )
    assert obs["controller_notify_sa"].owner == "moltrace"
    assert obs["controller_notify_sa"].due_at == _T0 + timedelta(hours=72)
    # Art. 34 data-subject communication has no fixed hour → due_at None (human-judged).
    assert obs["controller_notify_data_subjects"].due_at is None


def test_low_risk_controller_breach_has_no_data_subject_duty():
    obs = _by_key(
        ir.compute_obligations(
            _T0, role="controller", personal_data_breach=True, high_risk_to_subjects=False
        )
    )
    assert "controller_notify_data_subjects" not in obs


def test_non_personal_data_incident_has_no_gdpr_obligation():
    assert ir.compute_obligations(_T0, role="processor", personal_data_breach=False) == []


# --------------------------------------------------------------------------- evaluation


def test_evaluate_met_missed_overdue_pending():
    obs = ir.compute_obligations(
        _T0, role="processor", personal_data_breach=True, processor_sla_hours=24
    )
    # Notified on time (within 24h) → met; nothing else done yet.
    done = {"processor_notify_controller": _T0 + timedelta(hours=5)}
    statuses = {s.obligation.key: s for s in ir.evaluate(obs, done, now=_T0 + timedelta(hours=6))}
    assert statuses["processor_notify_controller"].state == "met"
    assert statuses["internal_breach_record"].state == "pending"  # due at 24h, now 6h
    assert statuses["controller_notify_sa"].state == "informational"  # customer's duty

    # Late notification → missed; the still-undone internal record is now overdue.
    late = {"processor_notify_controller": _T0 + timedelta(hours=30)}
    later = {s.obligation.key: s for s in ir.evaluate(obs, late, now=_T0 + timedelta(hours=40))}
    assert later["processor_notify_controller"].state == "missed"
    assert later["internal_breach_record"].state == "overdue"


def test_manual_state_for_without_undue_delay():
    obs = ir.compute_obligations(
        _T0, role="controller", personal_data_breach=True, high_risk_to_subjects=True
    )
    statuses = {s.obligation.key: s for s in ir.evaluate(obs, {}, now=_T0 + timedelta(hours=1))}
    # No fixed deadline → "manual" until a human records completion.
    assert statuses["controller_notify_data_subjects"].state == "manual"
    done = {"controller_notify_data_subjects": _T0 + timedelta(hours=2)}
    s2 = {s.obligation.key: s for s in ir.evaluate(obs, done, now=_T0 + timedelta(hours=3))}
    assert s2["controller_notify_data_subjects"].state == "met"


def test_all_deadlines_met_helper():
    obs = ir.compute_obligations(_T0, role="processor", personal_data_breach=True)
    on_time = {
        "processor_notify_controller": _T0 + timedelta(hours=2),
        "internal_breach_record": _T0 + timedelta(hours=2),
    }
    assert ir.all_deadlines_met(ir.evaluate(obs, on_time, now=_T0 + timedelta(hours=3))) is True
    # One missed → not all met.
    assert (
        ir.all_deadlines_met(ir.evaluate(obs, {}, now=_T0 + timedelta(hours=100))) is False
    )


def test_all_deadlines_met_ignores_non_moltrace_overdue():
    # Another party's (the controller's) overdue hard obligation must NOT flip
    # MolTrace's own acceptance check.
    other = ir.NotificationObligation(
        key="x",
        recipient="supervisory authority",
        basis="b",
        due_at=_T0,
        hard=True,
        owner="controller (customer)",
    )
    statuses = ir.evaluate([other], {}, now=_T0 + timedelta(hours=10))
    assert statuses[0].state == "overdue"
    assert ir.all_deadlines_met(statuses) is True


def test_extra_regime_overlay():
    obs = _by_key(
        ir.compute_obligations(
            _T0,
            role="controller",
            personal_data_breach=True,
            extra_regime_hours={"hipaa_individuals": 1440},  # 60 days
        )
    )
    assert obs["overlay_hipaa_individuals"].due_at == _T0 + timedelta(hours=1440)


def test_naive_datetime_coerced_to_utc():
    naive = datetime(2026, 6, 26, 9, 0, 0)  # no tzinfo
    obs = ir.compute_obligations(naive, role="controller", personal_data_breach=True)
    assert _by_key(obs)["controller_notify_sa"].due_at.tzinfo is not None
