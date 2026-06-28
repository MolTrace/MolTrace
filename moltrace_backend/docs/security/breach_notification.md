# Breach-Notification Workflow

**Security Prompt 20.** How MolTrace meets its breach-notification obligations and **gives
its customers what they need to meet theirs**, on a clock. Part of the
[incident-response plan](incident_response_plan.md); the timing is computed by the
`ir_timeline.py` deadline engine.

> **Compliance framing.** These controls are **designed to support** GDPR Art. 33/34 (and
> other regimes); MolTrace does not claim to *be* GDPR-compliant or to *guarantee* a
> customer's compliance. The overall determination — including whether a breach is
> notifiable and to whom — is the **controller's** (the customer's) responsibility.

## The load-bearing distinction: processor vs. controller

| Data | MolTrace's role | MolTrace's obligation | Who notifies the regulator / individuals |
|---|---|---|---|
| **Customer** personal data (dossiers, spectra, user records the customer controls) | **Processor** (GDPR Art. 4(8)/28) | **Art. 33(2): notify the controller (customer) _without undue delay_** — a contractual DPA window | The **customer** (controller): Art. 33(1) 72h to the SA; Art. 34 to data subjects |
| **MolTrace's own** data (its employees, account admins, billing contacts, its staff's security logs) | **Controller** | **Art. 33(1): notify the SA within 72h** of awareness; **Art. 34**: notify data subjects if high risk | MolTrace |

**The trap to avoid:** never say "MolTrace will notify the supervisory authority within 72
hours" or "MolTrace will notify affected data subjects" *for customer data*. That over-claims
a legal role MolTrace does not hold and could mislead a customer into thinking its own duty is
discharged. MolTrace's deliverable for customer data is a **prompt, contractually-defined
notice to the customer** with enough facts for the customer to run its own Art. 33/34 process.

**Sub-processor chain:** if a MolTrace sub-processor (e.g. the cloud host) breaches, it
notifies MolTrace without undue delay → MolTrace notifies the customer → the customer's clock
starts. The chain must preserve the timeline.

## When does the clock start? ("awareness")

Under GDPR, the clock starts on **becoming aware** = a *reasonable degree of certainty* that a
security incident led to personal data being compromised — not the first anomaly. A short
investigation period to establish that certainty is permitted, but must itself begin without
undue delay. **For MolTrace (processor), awareness = the detection timestamp** of an incident
affecting customer data (a SIEM detection, an audit-chain alert, intrusion/exfil evidence, or
a sub-processor notice). **Record it** — it anchors the whole timeline and any "reasons for
delay."

## Decision tree

```
Incident detected (record timestamp = awareness)
│
├─ Personal data involved?  ── No ──▶ Document internally (Art. 33(5)); no notification. Done.
│        │ Yes
│        ▼
├─ Whose data?
│    ├─ Customer-controlled  ▶ role = PROCESSOR ▶ notify the CUSTOMER within the DPA SLA,
│    │                                              with the Art. 33(3) facts you can determine.
│    │                                              The customer decides SA / data-subject notice.
│    └─ MolTrace's own        ▶ role = CONTROLLER ▶ Risk to individuals?
│                                                     ├─ No risk  ▶ document only (Art. 33(5))
│                                                     ├─ Risk     ▶ notify SA ≤ 72h (Art. 33(1))
│                                                     └─ HIGH risk▶ + notify data subjects
│                                                                   without undue delay (Art. 34),
│                                                                   unless an Art. 34(3) exemption
│                                                                   (encryption / mitigation /
│                                                                   disproportionate effort) applies.
▼
Always: maintain the internal breach record (Art. 33(5)) — facts, effects, remedial action —
even when nothing is notified.
```

## Computing the deadlines — `ir_timeline.py`

The engine turns the awareness timestamp + the human risk decisions into concrete deadlines
and tracks met/missed. It is **decision-support** — it does not decide notifiability and sends
nothing.

```python
from datetime import datetime, timezone
from nmrcheck import ir_timeline as ir

detected_at = datetime(2026, 6, 26, 9, 0, tzinfo=timezone.utc)  # awareness

# Customer-data breach → MolTrace is the processor; commit to a 24h DPA notice window.
obligations = ir.compute_obligations(
    detected_at,
    role="processor",
    personal_data_breach=True,
    processor_sla_hours=24,
    controller_awareness_at=None,   # set once the customer is notified, to show their 72h clock
)
# When notices go out, evaluate:
statuses = ir.evaluate(
    obligations,
    {"processor_notify_controller": datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)},
    now=datetime(2026, 6, 26, 15, 0, tzinfo=timezone.utc),
)
assert ir.all_deadlines_met(statuses)   # the "notifications meet deadlines" check
```

- **`role="processor"`** (customer data) → MolTrace's one hard, owned deadline is
  `processor_notify_controller` = awareness + the DPA SLA (default 24h; commit the real number
  in the DPA). The customer's `controller_notify_sa` (72h) is shown as **informational**, not a
  MolTrace deadline.
- **`role="controller"`** (MolTrace's own data) → `controller_notify_sa` = awareness + 72h
  (hard); `controller_notify_data_subjects` is **manual** (no fixed hour — "without undue
  delay", a human risk call).
- **`internal_breach_record`** (Art. 33(5)) is always produced for a personal-data breach.
- **`extra_regime_hours`** adds non-GDPR overlays (HIPAA 60 days, US state caps, SEC 4-business-day,
  NIS2/DORA, or a stricter contractual SLA). GDPR is the backbone; the binding number MolTrace
  operates to is the DPA-stated processor SLA.

States from `evaluate(...)`: `met` · `missed` (completed late) · `overdue` (past due, not done)
· `pending` (not yet due) · `manual` (no fixed deadline) · `informational` (another party's
duty). `all_deadlines_met()` is True when no MolTrace-owned hard obligation is missed/overdue.

## What goes in the notice (Art. 33(3))

MolTrace's notice to the customer should front-load the fields the controller needs, even if
some are still "to be determined" (phased notification, Art. 33(4), is allowed — incomplete
facts are no excuse to wait):

1. **Nature** of the breach — incl., where possible, categories + approximate number of data
   subjects and of records concerned.
2. **Contact point** (DPO / security contact) for more information.
3. **Likely consequences** (the risk/impact assessment).
4. **Measures taken or proposed** to address it and mitigate adverse effects (the containment
   from the [runbook](incident_runbooks.md)).

For a MolTrace-as-controller data-subject communication (Art. 34(2)), use the same fields
2–4 in clear, plain language (the categories/numbers element is not required).

## Honest boundaries

- **Sending** notices (email, regulator portals, customer comms) and the **24/7 on-call**
  rotation are operational — in-repo we ship the deadline engine, the decision tree, the
  evidence sources, and this workflow.
- The notifiable-breach and high-risk judgments are **human** decisions (DPO/privacy contact);
  the engine computes timing, not legal conclusions.
- These controls **support** the customer's GDPR obligations; they do not discharge them.

See also: [`incident_response_plan.md`](incident_response_plan.md) ·
[`incident_runbooks.md`](incident_runbooks.md) · [`siem_detections.md`](siem_detections.md).
