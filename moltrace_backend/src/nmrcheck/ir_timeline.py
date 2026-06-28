"""Incident-response notification-timeline engine (Security Prompt 20).

Given an incident's detection timestamp + a breach classification, computes the
notification obligations an incident commander must hit and evaluates whether each
was met — so notifications meet their deadlines.

**The load-bearing distinction is processor vs. controller.** For *customer* personal
data, MolTrace is a **processor** (GDPR Art. 4(8)/28), so its binding obligation is
**Art. 33(2)**: notify the **controller (the customer) without undue delay** — a
contractual window in the DPA — *not* the 72-hours-to-supervisory-authority duty,
which is the controller's (Art. 33(1)). For data MolTrace itself controls (its own
staff / account-admin / billing / security-log data) it wears the **controller** hat
directly and carries the Art. 33(1) 72h SA duty + Art. 34 data-subject duty.

This engine is **decision-support**: it computes deadlines + flags met / missed /
overdue / pending so a responder can see the clock. It does NOT decide whether a
breach is notifiable (a human risk assessment) and does NOT send anything. It is
"designed to support" the customer's GDPR Art. 33/34 obligations; the compliance
determination is the controller's. Library-only — see docs/security/incident_response_plan.md
and docs/security/breach_notification.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

# GDPR Art. 33(1): controller → supervisory authority, outer bound 72h from awareness.
GDPR_SA_HOURS = 72
# Common enterprise DPA ask for the processor→controller notice (Art. 33(2)). The real
# number is whatever MolTrace commits to in the DPA; 24h is the conservative default.
DEFAULT_PROCESSOR_SLA_HOURS = 24

BreachRole = Literal["processor", "controller"]
ObligationState = Literal["met", "missed", "overdue", "pending", "manual", "informational"]


@dataclass(frozen=True)
class NotificationObligation:
    """One notification/documentation obligation arising from an incident."""

    key: str
    recipient: str
    basis: str
    due_at: datetime | None  # None = "without undue delay" (human-judged, no fixed hour)
    hard: bool  # a hard regulatory/contractual deadline vs. an advisory target
    owner: str  # who is accountable: "moltrace" or "controller (customer)"
    note: str = ""


@dataclass
class ObligationStatus:
    obligation: NotificationObligation
    completed_at: datetime | None
    state: ObligationState


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def compute_obligations(
    detected_at: datetime,
    *,
    role: BreachRole,
    personal_data_breach: bool,
    high_risk_to_subjects: bool = False,
    processor_sla_hours: int = DEFAULT_PROCESSOR_SLA_HOURS,
    controller_awareness_at: datetime | None = None,
    extra_regime_hours: dict[str, int] | None = None,
) -> list[NotificationObligation]:
    """Compute the obligations for an incident.

    ``role`` is which hat MolTrace wears for *this incident's* data (processor for
    customer data, controller for MolTrace's own). ``personal_data_breach`` and
    ``high_risk_to_subjects`` are the human risk-assessment inputs (this engine does
    not decide them). ``controller_awareness_at`` (when MolTrace's notice reached the
    customer) anchors the customer's downstream 72h clock when known. ``extra_regime_hours``
    adds jurisdiction/contract overlays (e.g. {"hipaa_individuals": 1440} for 60 days).
    """
    detected_at = _utc(detected_at)
    obligations: list[NotificationObligation] = []

    # Art. 33(5): document EVERY personal-data breach internally, notifiable or not.
    if personal_data_breach:
        obligations.append(
            NotificationObligation(
                key="internal_breach_record",
                recipient="internal breach register",
                basis="GDPR Art. 33(5) — document facts, effects, remedial action",
                due_at=detected_at + timedelta(hours=processor_sla_hours),
                hard=True,
                owner="moltrace",
                note="Required even when no external notification is sent.",
            )
        )

    if role == "processor":
        # MolTrace's actual binding deadline: notify the controller (customer).
        if personal_data_breach:
            obligations.append(
                NotificationObligation(
                    key="processor_notify_controller",
                    recipient="controller (customer)",
                    basis="GDPR Art. 33(2) + DPA SLA — notify controller without undue delay",
                    due_at=detected_at + timedelta(hours=processor_sla_hours),
                    hard=True,
                    owner="moltrace",
                    note=(
                        "MolTrace's binding obligation. The customer (controller) then "
                        "owns the Art. 33(1) SA notification and any Art. 34 data-subject "
                        "communication — those are NOT MolTrace's to make for customer data."
                    ),
                )
            )
            # Informational: the customer's downstream clock (not MolTrace's deadline).
            sa_due = (
                _utc(controller_awareness_at) + timedelta(hours=GDPR_SA_HOURS)
                if controller_awareness_at is not None
                else None
            )
            obligations.append(
                NotificationObligation(
                    key="controller_notify_sa",
                    recipient="supervisory authority",
                    basis="GDPR Art. 33(1) — controller's 72h clock (from its awareness)",
                    due_at=sa_due,
                    hard=False,
                    owner="controller (customer)",
                    note="Situational awareness; the customer is accountable, not MolTrace.",
                )
            )
    else:  # controller — MolTrace's own data
        if personal_data_breach:
            obligations.append(
                NotificationObligation(
                    key="controller_notify_sa",
                    recipient="supervisory authority",
                    basis="GDPR Art. 33(1) — notify SA, outer bound 72h from awareness",
                    due_at=detected_at + timedelta(hours=GDPR_SA_HOURS),
                    hard=True,
                    owner="moltrace",
                    note="72h is the outer bound under 'without undue delay', not a grace period.",
                )
            )
        if high_risk_to_subjects:
            obligations.append(
                NotificationObligation(
                    key="controller_notify_data_subjects",
                    recipient="affected data subjects",
                    basis="GDPR Art. 34(1) — high risk → communicate without undue delay",
                    due_at=None,  # no fixed hour; human-judged (expedite if it mitigates harm)
                    hard=False,
                    owner="moltrace",
                    note="Art. 34(3) exemptions may apply (encryption / mitigation).",
                )
            )

    for label, hours in (extra_regime_hours or {}).items():
        obligations.append(
            NotificationObligation(
                key=f"overlay_{label}",
                recipient=label,
                basis="jurisdiction/contract overlay (configured)",
                due_at=detected_at + timedelta(hours=int(hours)),
                hard=True,
                owner="moltrace",
                note="Non-GDPR overlay supplied by the operator.",
            )
        )
    return obligations


def evaluate(
    obligations: list[NotificationObligation],
    completed: dict[str, datetime] | None,
    *,
    now: datetime,
) -> list[ObligationStatus]:
    """Evaluate each obligation against when (if) it was completed.

    ``completed`` maps an obligation ``key`` to the timestamp it was discharged.
    States: met / missed (completed late) / overdue (past due, not done) / pending
    (not yet due) / manual (no fixed deadline — human-judged) / informational (another
    party's duty, tracked for awareness).
    """
    completed = completed or {}
    now = _utc(now)
    out: list[ObligationStatus] = []
    for ob in obligations:
        done = completed.get(ob.key)
        done = _utc(done) if done is not None else None
        if not ob.hard and ob.owner != "moltrace":
            state: ObligationState = "informational"
        elif ob.due_at is None:
            state = "met" if done is not None else "manual"
        elif done is not None:
            state = "met" if done <= ob.due_at else "missed"
        elif now > ob.due_at:
            state = "overdue"
        else:
            state = "pending"
        out.append(ObligationStatus(obligation=ob, completed_at=done, state=state))
    return out


def all_deadlines_met(statuses: list[ObligationStatus]) -> bool:
    """True if no MolTrace-owned hard obligation is missed or overdue — the
    'notifications meet deadlines' acceptance check. Filters by owner so another
    party's (the controller's) missed deadline can never flip MolTrace's own check."""
    return not any(
        s.state in ("missed", "overdue") and s.obligation.owner == "moltrace"
        for s in statuses
    )
