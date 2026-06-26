# SIEM & Security Detections

**Security Prompt 19.** MolTrace turns its immutable `SecurityEvent` stream + the
tamper-evident audit chain into near-real-time **detections**, and ships
high-severity alerts to a pluggable **SIEM sink**. Four detections are wired:
impossible travel, privilege escalation, cross-tenant access, and audit-chain breaks.

> **Honest boundary.** Shipping logs to a *hosted* SIEM (Datadog / Splunk / Elastic)
> and the *24/7 on-call rotation* (PagerDuty / Opsgenie) are **operational** — they
> live in those vendors' consoles, not this repo. What ships in-repo: the immutable
> structured security-event stream, the four detection rules, the alert sink seam
> (stdout JSON + optional webhook), the admin scan endpoints, and the staging-test
> scenarios that prove each detection fires. The detection logic is in
> [`detections.py`](../../src/nmrcheck/detections.py).

## Immutable logs → SIEM

Security-relevant events are recorded as `SecurityEvent` rows (`security_events`),
each of which also writes a paired entry into the **tamper-evident audit chain**
(`operations_store.create_security_event` → a hash-chained `audit_events` row), so
the security log is itself integrity-protected (Prompt 10). The export path to a SIEM
is the platform log drain: every shipped alert is written as a single structured JSON
line to **stdout** (`{"siem_alert": {...}}`), which Render / Vercel forward to their
log drains and on to any SIEM. A configured webhook additionally pushes high-severity
alerts (below).

## The four detections

| Detection | Signal | Severity | Logic |
|---|---|---|---|
| **impossible_travel** | `login_success` events (with client IP) | warning | same actor, two logins from *different* source IPs within `IMPOSSIBLE_TRAVEL_WINDOW_SECONDS` (default 300s) |
| **privilege_escalation** | `privilege_escalation` events | error | a user's `is_admin` flips on (emitted at the admin-grant seams) |
| **cross_tenant_access** | `cross_tenant_denied` events | warning | an actor accrues ≥ `CROSS_TENANT_DENIED_THRESHOLD` (default 5) owner-denied accesses within `CROSS_TENANT_WINDOW_SECONDS` (default 600s) |
| **audit_chain_break** | `verify_audit_chain` result | critical | the audit ledger fails full-walk verification (per-row hash / anchor / head) |

**impossible_travel is an IP-velocity heuristic, not geo-distance.** Without geo/ASN
enrichment we cannot compute km/h, so the rule flags any source-IP change inside a
window too short to plausibly relocate. Geo enrichment (resolve IP → city, compute a
real velocity) is a documented seam, not yet wired — so a user on a mobile network
flipping carrier IPs can false-positive; tune the window or add geo to sharpen it.

## Emission seams (where the events come from)

Emission is best-effort (never breaks the request; swallows all errors) and gated by
`SECURITY_SIEM_ENABLED` (default on). Wired in `api.py`:

- **login_success** (+ client IP via the XFF-aware `rate_limit._client_ip`) at the
  three password login routes (`/auth/login`, `/auth/sign-in`, `/auth/token`).
  *Seam not yet wired:* the MFA-completion and SSO-callback login routes — a follow-up
  so impossible-travel also covers federated / second-factor logins.
- **cross_tenant_denied** at the three owner-scoped deny branches
  (`require_dossier_access`, `require_reaction_access`, `_readable_via_parent_dossier`).
  Note this fires for *any* owner-scoped 404 (including a genuinely-missing id) — which
  is correct for **enumeration** detection (probing ids you don't own, whether or not
  they exist, is the signal). Skipped for anonymous/system-key callers (they can't trip
  the actor-keyed detector). *Seam:* the generic `gate()` deny path (used by new
  owned/role-scoped endpoints) is not yet wired — fold it in as those endpoints grow.
- **privilege_escalation** at the three login auto-grant sites (admin-email promotion).
  *Seam:* the explicit admin grant/revoke route already writes an `admin_action`
  audit event; folding it into this detection is a follow-up.

## Admin endpoints

Both `require_admin` (system key or admin), under the router default-deny gate:

- `GET /admin/security/alerts` — run the detections over the recent window + verify
  the audit chain; return the current alerts (read-only, does **not** ship).
- `POST /admin/security/detections/run` — run the scan **and ship** high-severity
  (error/critical) alerts to the SIEM sink. This is the hook a scheduler / cron calls;
  continuous 24/7 scanning is the operational piece.

## The SIEM sink

`detections.get_sink(settings)` returns a composite sink: **always** a
`JsonStdoutSink` (structured JSON to stdout → log drain), **plus** a `WebhookSink`
when `SECURITY_ALERT_WEBHOOK_URL` is set (POSTs the alert JSON, 5s timeout,
best-effort — never raises). Only **error/critical** alerts are shipped; info/warning
stay queryable in the event stream + the `GET …/alerts` view.

## Settings

| Env | Default | Meaning |
|---|---|---|
| `SECURITY_SIEM_ENABLED` | `true` | gate emission + detection |
| `SECURITY_ALERT_WEBHOOK_URL` | `""` | webhook sink for high-severity alerts |
| `SECURITY_DETECTION_WINDOW_MINUTES` | `1440` | scan lookback |
| `SECURITY_DETECTION_SCAN_LIMIT` | `5000` | max events per scan |
| `IMPOSSIBLE_TRAVEL_WINDOW_SECONDS` | `300` | impossible-travel window |
| `CROSS_TENANT_DENIED_THRESHOLD` | `5` | cross-tenant alert threshold |
| `CROSS_TENANT_WINDOW_SECONDS` | `600` | cross-tenant window |

## Operational TODOs (outside this repo)

- Ship the stdout JSON stream to a hosted SIEM and wire **24/7 on-call** routing of
  the webhook alerts (PagerDuty/Opsgenie).
- Schedule `POST /admin/security/detections/run` (cron) for continuous scanning; the
  audit-chain reconcile seam (`reconcile_audit_chain`, with this module's sink as
  `alert_fn`) is the other natural scheduled hook.
- Geo/ASN enrichment for true impossible-travel; MFA/SSO login-event emission.

## Coverage

`tests/test_security_detections.py` (rule units + sinks) and
`tests/test_security_detections_api.py` (the four detection scenarios end-to-end —
6 cases — through the admin endpoints: login×2 → impossible travel; owner-denied probing → cross-tenant;
seeded escalation → privilege escalation; tampered audit row → audit-chain break,
shipped to the sink).
