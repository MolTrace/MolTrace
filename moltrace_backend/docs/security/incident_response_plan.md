# Incident Response Plan

**Security Prompt 20.** How MolTrace detects, triages, contains, eradicates, recovers
from, and learns from a security incident — and how it meets its **breach-notification
deadlines**. This plan is written so an on-call engineer can execute it; the concrete
per-incident steps are in [`incident_runbooks.md`](incident_runbooks.md) and the
notification timing is in [`breach_notification.md`](breach_notification.md).

> **Honest boundary.** The **24/7 on-call rotation** (PagerDuty/Opsgenie), the **hosted
> SIEM**, and the **edge WAF** are operational/platform-owned, not in-repo. What ships
> in-repo and is cited below: the [detection rules + scan endpoints](siem_detections.md),
> the immutable [SecurityEvent stream + tamper-evident audit chain](#evidence-collection)
> for evidence, the [containment levers](#containment) (real admin endpoints / store
> functions), the [notification deadline engine](#notification--breach-reporting)
> (`ir_timeline.py`), and the [post-incident corrective-action register](security_findings_register.md).
> Compliance regimes (GDPR Art. 33/34, 21 CFR Part 11/ALCOA+) are **designed to support**,
> never held attestations — the controller (customer) owns its own compliance
> determination (see [`breach_notification.md`](breach_notification.md)).

## Severity tiers

| Tier | Definition | Examples | Target response |
|---|---|---|---|
| **SEV1 — Critical** | Confirmed breach of customer/regulated data, or integrity compromise of the audit ledger | `audit_chain_break`; confirmed cross-tenant data exfiltration; system-API-key or audit-signing-key compromise; ransomware | Immediate; incident commander paged 24×7 |
| **SEV2 — High** | Credible account/credential compromise or privilege abuse; suspected data exposure | `privilege_escalation`; `impossible_travel` on an admin; a leaked SCIM bearer | < 1 hour |
| **SEV3 — Moderate** | Contained probing / abuse with no confirmed data impact | `cross_tenant_access` enumeration; sustained rate-limit abuse; a single suspicious login | < 1 business day |
| **SEV4 — Low / informational** | Anomaly under investigation, no confirmed impact | a one-off `impossible_travel` warning; a scanner report via the [VDP](vulnerability_disclosure_policy.md) | Best-effort; triage into the queue |

Severity is re-assessed at each lifecycle stage as facts emerge; a SEV3 that turns out
to have touched personal data escalates to SEV1.

## Roles

- **Incident Commander (IC)** — owns the incident end-to-end; the single decision-maker.
- **Communications Lead** — drafts internal + customer/regulator notifications; owns the
  [notification timeline](breach_notification.md).
- **Scribe** — maintains the incident timeline (the Art. 33(5) record): every action +
  timestamp, drawn from the audit chain + SecurityEvent stream.
- **Subject-matter responders** — engineers who execute containment/eradication.
- **DPO / privacy contact** — makes the notifiable-breach + high-risk risk calls (this is
  a human judgment, not automated).

_(On a small team one person wears several hats; the roles are responsibilities, not
headcount.)_

## Lifecycle

```
 1 Detect → 2 Triage → 3 Contain → 4 Eradicate → 5 Recover → 6 Notify → 7 Post-incident
```

### 1. Detect

Signals (see [`siem_detections.md`](siem_detections.md)): the four detections
(`impossible_travel`, `privilege_escalation`, `cross_tenant_access`, `audit_chain_break`)
via `GET /admin/security/alerts` / `POST /admin/security/detections/run` → the SIEM sink;
rate-limit `SecurityEvent`s; the audit-chain reconciliation sweep; a
[VDP](vulnerability_disclosure_policy.md) report; or a sub-processor/platform notice.
**Record the detection timestamp** — it anchors the entire notification timeline (it is
MolTrace's "awareness" moment under GDPR Art. 33(2)).

### 2. Triage

Classify severity (table above) and answer the gating questions: *did this involve
personal data? whose (customer-controlled → MolTrace is a processor; MolTrace's own →
controller)? is there a high risk to data subjects?* Open a register row at triage time
so the SLA clock is visible ([`security_findings_register.md`](security_findings_register.md)).

### 3. Contain

Stop the bleeding with the [levers below](#containment) before eradicating. Containment
precedes root-cause analysis.

### 4. Eradicate

Remove the foothold: rotate the compromised credential/key, revoke the access path, patch
the vulnerability, purge attacker-created artifacts (preserving evidence first).

### 5. Recover

Restore normal operation; re-anchor the audit chain if the signing key rotated
(`POST /admin/audit/anchor`); confirm the detections are clean; monitor for recurrence.

### 6. Notify

Run the [breach-notification workflow](breach_notification.md): compute the deadlines with
`ir_timeline.compute_obligations(...)`, and — for a personal-data breach of **customer**
data — notify the **customer (controller) without undue delay** within the DPA SLA so they
can meet their own Art. 33/34 obligations. **MolTrace does not notify the supervisory
authority or data subjects for customer data** — that is the controller's call.

### <a id="post-incident"></a>7. Post-incident

Within 5 business days of closure, run a blameless **post-incident review** (template
below): timeline, root cause, what detected/contained it, what didn't, corrective actions.
Each corrective action becomes a [register](security_findings_register.md) row (CVSS
severity → SLA), closed only with remediation evidence. Sign off the closed incident
record with a [Part 11 e-signature](#sign-off) for a verifiable, immutable closure.

## <a id="containment"></a>Containment levers (in-repo)

| Lever | How | Use for |
|---|---|---|
| Revoke a session family | `session_store.revoke_family_by_refresh` / `revoke_family_by_access` | a stolen/leaked bearer (reuse-detection auto-revokes the family) |
| Revoke ALL of a user's tokens | `database.revoke_all_user_tokens` | account/credential compromise (user-wide kill switch) |
| Disable / deprovision a user | `scim_store._set_active(active=False)` (also cuts sessions) | compromised or offboarded account |
| Demote a compromised admin | `POST /admin/users/{id}/demote` (audited) | reverse a `privilege_escalation` |
| Revoke a SCIM bearer | `DELETE /auth/sso/connections/{id}/scim-token` | leaked org provisioning token |
| Kill an SSO connection | `DELETE /auth/sso/connections/{id}` | compromised IdP federation |
| Force enforce-SSO / lock local password | `PATCH /auth/sso/connections/{id}` (`enforce_sso`) | compromised local credential |
| Rotate the system API key | re-generate `API_KEY` in the Render console | suspected break-glass key compromise |
| Rotate the audit signing key | rotate `AUDIT_SIGNING_KEY`, then re-anchor | suspected audit-chain tamper |
| Throttle / WAF | rate limiter (`RATE_LIMIT_*`) + the [edge-WAF runbook](waf_edge_runbook.md) | DoS / volumetric abuse |

## <a id="evidence-collection"></a>Evidence collection (in-repo, forensic-grade)

- **Tamper-evident audit chain** — `GET /admin/audit/verify` (per-row SHA-256 chain + HMAC
  anchors + signed head) proves integrity; `GET /admin/audit/search` for actor/entity
  forensic queries; `POST /admin/audit/anchor` to seal a checkpoint.
- **SecurityEvent stream** — `GET /security/events` (filterable) + `GET /security/summary`:
  the immutable security log (each row also writes a paired audit-chain entry).
- **Debug bundles** — `POST /admin/debug-bundles` → downloadable forensic snapshot.
- **Reversible retention** — soft-delete (`alcoa.py`, no hard-delete; `reason_for_change` +
  server `deleted_by`) preserves records through an incident; `?include_deleted=true`
  surfaces them. Do not destroy evidence during eradication.
- **Signature integrity** — `esign.verify_signature` proves a signed/approved record was
  not altered post-signature.

## <a id="sign-off"></a>Post-incident sign-off

Closure is anchored on two existing systems: (1) a **Part 11 e-signature** (`esign.py`,
step-up-stamped, content-bound, server-principal signer) on the closed incident record —
an immutable, verifiable approval; and (2) the **[security findings register](security_findings_register.md)**,
where each root-cause/corrective action is a tracked row closed only with evidence (fixing
commit/PR + regression test + re-test).

## <a id="notification--breach-reporting"></a>Notification & breach reporting

See [`breach_notification.md`](breach_notification.md) for the GDPR Art. 33/34 workflow and
the `ir_timeline.py` deadline engine. The headline: **MolTrace is a processor for customer
data** → it notifies the **customer** within the DPA SLA; the customer owns the 72-hour
supervisory-authority clock.

## Cadence: tabletop exercises & post-incident reviews

- **Quarterly tabletop** — walk one scenario (rotate: audit-chain break, admin ATO,
  cross-tenant exfil, key compromise) end-to-end against this plan; time the simulated
  notification against the engine; record gaps as register rows. _(Running the exercise is
  operational; the [template](#tabletop-exercise-template) is in-repo.)_
- **Post-incident review** — after every real SEV1/SEV2, blameless, within 5 business days.

### <a id="tabletop-exercise-template"></a>Tabletop exercise template

```
Scenario: <e.g. audit_chain_break detected at 02:14 UTC>
Participants / roles: IC / Comms / Scribe / DPO
Inject timeline: <what facts are revealed when>
Decisions to exercise: severity? personal data? processor or controller? high-risk?
Containment walked: <levers from the table>
Notification dry-run: ir_timeline.compute_obligations(detected_at=..., role=..., ...)
                      → were the simulated notices inside the deadlines?
Gaps found → register rows: <MT-VULN-...>
```

### Post-incident review template

```
Incident: <id>   Severity: <SEVn>   Detected: <ts>   Closed: <ts>
Timeline (from audit chain + SecurityEvent stream): <ts → action>
Root cause: <the failure, not the person>
Detection: what fired (or should have)?   Containment: what worked?
Personal data involved? role (processor/controller)? notifications & deadlines met?
Corrective actions → register rows (CVSS severity → SLA, evidence-closed):
Lessons → threat-model / detection / runbook updates:
Sign-off: <Part 11 e-signature on this record>
```

## Cross-references

[`siem_detections.md`](siem_detections.md) ·
[`incident_runbooks.md`](incident_runbooks.md) ·
[`breach_notification.md`](breach_notification.md) ·
[`threat_model.md`](threat_model.md) ·
[`vulnerability_disclosure_policy.md`](vulnerability_disclosure_policy.md) ·
[`security_findings_register.md`](security_findings_register.md) ·
[`zero_trust_infra.md`](zero_trust_infra.md) ·
[`waf_edge_runbook.md`](waf_edge_runbook.md)
