# FE handoff — SIEM security detections (Security Prompt 19)

**Scope:** backend-only this prompt. These are **admin-internal** endpoints; there is
no required FE work now. This handoff records the contract so a future admin/SecOps
console can surface alerts.

## Contract delta (backend, shipped)

New **admin-only** endpoints (require system key or admin; default-deny gated):

1. `GET /admin/security/alerts` → `DetectionScanResult`
   Runs the four detections over the recent `SecurityEvent` window + verifies the
   audit chain; returns current alerts. Read-only (does not ship to the SIEM sink).
2. `POST /admin/security/detections/run` → `DetectionScanResult`
   Same scan, but also ships high-severity (error/critical) alerts to the SIEM sink.
   The hook a scheduler/cron calls.

New response models:

```ts
type DetectionId = "impossible_travel" | "privilege_escalation"
                 | "cross_tenant_access" | "audit_chain_break";

interface SecurityAlert {
  detection: DetectionId;
  severity: "info" | "warning" | "error" | "critical";
  actor_email: string | null;
  message: string;
  first_seen: string | null;   // ISO datetime
  last_seen: string | null;
  event_count: number;
  evidence: Record<string, unknown>;
}

interface DetectionScanResult {
  generated_at: string;        // ISO datetime
  window_minutes: number;
  events_scanned: number;
  alerts: SecurityAlert[];
  shipped: number;
  audit_chain_ok: boolean;
}
```

`SecurityEventType` gained two values: `cross_tenant_denied`, `privilege_escalation`
(relevant if the FE renders the existing `GET /security/events` list).

## To regenerate the typed schema (when/if FE exposes this)

From `moltrace_frontend/`: `npm run generate:openapi` (FastAPI `/openapi.json` →
`src/lib/api/schema.d.ts`). The new endpoints + `DetectionScanResult` / `SecurityAlert`
will appear; nothing else changed contract-wise. No FE build is required until an
admin console consumes them.

## Suggested (future) FE surface

A SecOps panel in the admin area: a `DetectionScanResult` table grouped by
`detection`, severity-colored, with `evidence` expandable; a "Run scan" button →
`POST …/detections/run`. Not in scope now.

Backend reference: [`docs/security/siem_detections.md`](security/siem_detections.md).
