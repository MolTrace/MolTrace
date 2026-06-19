# FE Handoff — Security Prompt 10: Tamper-evident audit chain

**TL;DR: no FE component work required.** Two new **admin-only** ops endpoints were added; the only
FE action is an optional `schema.d.ts` regen so the typed client knows them. No existing
route/model/status changed; existing audit endpoints are byte-identical.

## What changed (backend only)

`audit_events` rows are now linked into a tamper-evident **SHA-256 hash chain** (each row stores
`prev_hash` + `entry_hash` over a canonical serialization), with periodic **HMAC-signed anchors**
(`audit_checkpoints`). Chaining happens transparently in a `before_flush` listener, so every audit
write is covered. The existing `AuditEventRecord` read model is **unchanged** (the chain columns
are not projected into it), so `/audit`, `/audit/events`, and `/admin/audit/search` responses are
identical.

## New endpoints (both `require_admin`)

| Method | Path | Response model | Purpose |
|---|---|---|---|
| GET | `/admin/audit/verify` | `AuditChainVerification` | Full re-walk of the chain + anchor verification; `{ok, verified_count, total_chained, first_break_seq, anchors_ok, anchor_count, detail, key_id}`. |
| POST | `/admin/audit/anchor` | `AuditAnchorRecord \| null` | Seal a signed checkpoint over the chain since the last anchor (null if nothing new). |

## FE checklist

1. **Regenerate the typed client** (per the contracts-first rule): with the backend running,
   `cd moltrace_frontend && npm run generate:openapi` so `src/lib/api/schema.d.ts` picks up the two
   routes + `AuditChainVerification` / `AuditAnchorRecord`. **No component changes required.**
2. **(Optional, future)** these fold naturally into the existing **admin/ops** surface as an
   "audit integrity" panel — a "Verify chain" button (GET verify) showing `ok` / first break, and an
   "Anchor now" action. No new top-level nav (integrate-not-clutter). Not required for this prompt.

Both endpoints are admin-only and return admin-only models — there is no end-user surface and no
change to any existing screen.
