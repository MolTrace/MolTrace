# Incident Runbooks

**Security Prompt 20.** Concrete, executable runbooks per incident type, each keyed to a
real [detection signal](siem_detections.md) and the in-repo [containment levers /
evidence sources](incident_response_plan.md#containment). Follow the
[IR lifecycle](incident_response_plan.md#lifecycle); record the **detection timestamp**
(GDPR "awareness") and run the [notification workflow](breach_notification.md) whenever
personal data may be involved.

> All `/admin/*` and `/security/*` endpoints below require an admin or the system key.
> "Operational" steps (paging, console actions, sending notices) happen outside the repo.

---

## R1 — Audit-chain break (integrity / tampering) · SEV1

**Trigger:** `audit_chain_break` (critical) from `POST /admin/security/detections/run`, or
`GET /admin/audit/verify` returns `ok=false`. Integrity of the ALCOA+/Part 11 ledger is in
question.

1. **Triage.** `GET /admin/audit/verify` → note `detail`, `first_break_seq`, `anchors_ok`,
   `key_id`. A `key_id` showing the dev-fallback key in prod is itself the finding.
2. **Contain.** Treat the DB + the `AUDIT_SIGNING_KEY` as suspect. If key compromise is
   plausible, **rotate `AUDIT_SIGNING_KEY`** and restrict DB write access. Do **not** delete
   or "fix" any row — the break IS the evidence.
3. **Collect evidence.** Snapshot via `POST /admin/debug-bundles`; `GET /admin/audit/search`
   around `first_break_seq`; export the `GET /security/events` window. Preserve (soft-delete
   only).
4. **Eradicate / recover.** Identify the write path that broke the chain; once integrity is
   restored, `POST /admin/audit/anchor` to seal a fresh checkpoint with the rotated key.
5. **Notify.** If tampered records contain personal data → personal-data breach; run
   [breach-notification](breach_notification.md). Tampering of regulated records may also
   carry **Part 11/GxP** customer obligations — notify the customer regardless.

## R2 — Account takeover (impossible travel) · SEV2

**Trigger:** `impossible_travel` (warning) — same actor, two logins from different IPs in a
short window. Escalate to SEV1 if the account is an admin or touched regulated data.

1. **Triage.** `GET /security/events?event_type=login_success&actor_email=<user>` to see the
   IP/time history; `GET /admin/audit/search` for what the session did.
2. **Contain.** **`database.revoke_all_user_tokens`** for the user (kills every session);
   if SSO-federated, consider **enforce-SSO** / disabling the local password
   (`PATCH /auth/sso/connections/{id}`). Force a credential reset (operational).
3. **Eradicate.** Confirm MFA is enrolled/enforced; check for attacker-created API
   tokens/admin grants (see R3).
4. **Notify.** If the attacker could read personal/regulated data in-session → run the
   breach workflow.

## R3 — Privilege escalation · SEV2 (SEV1 if abused)

**Trigger:** `privilege_escalation` (error, shipped) — a user's `is_admin` flipped on.

1. **Triage.** Was the grant expected? `GET /admin/audit/search` for `admin.*` events around
   the time; check the `is_admin_email` allowlist (an attacker controlling an admin-listed
   email auto-grants on login — the threat-model crown jewel).
2. **Contain.** **`POST /admin/users/{id}/demote`**; revoke the user's tokens
   (`revoke_all_user_tokens`); if the allowlist was poisoned, correct the
   `IS_ADMIN_EMAIL`/`ADMIN_EMAILS` config (operational).
3. **Eradicate.** Audit everything the elevated account did; reverse unauthorized changes.
4. **Notify.** Per data touched.

## R4 — Cross-tenant probing / data-exfil attempt · SEV3 (SEV1 if successful)

**Trigger:** `cross_tenant_access` (warning) — an actor accrued ≥ threshold owner-denied
accesses (enumeration). The deny-by-default authz **blocked** these (non-leaking 404), so by
default it is a *probing* signal, not a confirmed breach.

1. **Triage.** `GET /security/events?event_type=cross_tenant_denied&actor_email=<user>` for
   the probed resources; confirm via `GET /admin/audit/search` that no cross-tenant read
   actually *succeeded* (it should not — the gate denies).
2. **Contain.** Revoke the actor's tokens; disable the account if malicious
   (`scim_store._set_active(False)`); rate-limit/WAF if volumetric.
3. **Eradicate.** If any read *did* succeed, that is a tenant-isolation gap — open a SEV1, add
   the missing `require_dossier_access`/ownership gate (see the
   [new-surface checklist](threat_model.md#new-surface-checklist)), and treat as a breach.
4. **Notify.** Only if a cross-tenant read succeeded (personal data of another tenant).

## R5 — Credential / key / secret compromise · SEV1–SEV2

**Trigger:** a leaked secret (gitleaks, a VDP report, anomalous use of the system key or a
SCIM bearer).

1. **Contain by rotating the specific secret:** system API key (Render console) · SCIM bearer
   (`DELETE …/scim-token`) · IdP client secret (`PATCH …/connections/{id}`) · `AUDIT_SIGNING_KEY`
   · `API_KEY`. Revoke affected sessions.
2. **Eradicate.** Purge the secret from history if committed (gitleaks scans full history);
   find what the secret could access and audit it.
3. **Notify.** Per data the secret could reach.

## R6 — Denial of service / abuse · SEV2–SEV3

**Trigger:** sustained `rate_limit` `SecurityEvent`s; latency/availability alerts.

1. **Contain.** The in-app rate limiter (`RATE_LIMIT_*`) throttles per-principal/route; for
   volumetric/cross-instance attacks invoke the **[edge WAF runbook](waf_edge_runbook.md)**
   (Cloudflare/Vercel — operational). `MAX_REQUEST_BODY_BYTES` bounds oversized bodies.
2. **Eradicate.** Block the source at the edge; tune limits.
3. **Notify.** DoS alone is usually not a personal-data breach (no confidentiality loss) —
   but document it (Art. 33(5)) and watch for it masking a parallel intrusion.

## R7 — External vulnerability report · SEV varies

**Trigger:** a report via the [VDP](vulnerability_disclosure_policy.md) (GitHub advisory /
security@moltrace.co / security.txt).

1. **Triage** per the VDP severity rubric; if it evidences an *active* compromise, branch to
   the matching runbook above and treat as an incident, not just a finding.
2. Track in the [findings register](security_findings_register.md); coordinated disclosure
   per the VDP.

---

## Every runbook ends the same way

Close via the [post-incident review](incident_response_plan.md#post-incident) → corrective
actions become [register](security_findings_register.md) rows → **Part 11 e-signature** on the
closed record. Update this runbook + the [threat model](threat_model.md) + the
[detections](siem_detections.md) with anything the incident taught you.
