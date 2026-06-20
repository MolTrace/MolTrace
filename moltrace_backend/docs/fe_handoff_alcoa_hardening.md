# FE Handoff — ALCOA+ hardening (Security Prompt 12, backend v0.51.0)

**Scope for the FE session:** `moltrace_frontend/` only. Backend is committed. This is a small,
additive contract change on the **Validation Center → Controlled Records** surface — no new nav.

## Contract delta (by name)

`ControlledRecord` (response) gained **3 additive, optional** fields:
- `reason_for_change: string | null` — the *why* of the last regulated change (lock/archive).
- `deleted_at: string | null` — set when the record has been archived (soft-deleted).
- `deleted_by: string | null` — the authenticated principal who archived it (server-set).

`GET /controlled-records` gained a query param:
- `include_deleted: boolean` (default `false`) — when false, archived/soft-deleted records are
  excluded; pass `true` to show them (e.g. an "Archived / deleted" audit view).

## Behavioral changes the UI should reflect
- **Archive is now a soft-delete.** After `POST /controlled-records/{id}/archive`, the record
  disappears from the default list (it is *retained*, not destroyed). Surface an "Include
  archived/deleted" toggle that re-fetches with `?include_deleted=true`; render
  `deleted_at`/`deleted_by`/`reason_for_change` on those rows.
- **Reason is enforced server-side.** Archive/lock already require a `reason` (the form should keep
  it required). A blank/whitespace-only reason now returns **422** — show the validation message.
- **No timestamp inputs.** Do not send `created_at`/`updated_at`/`deleted_at` in any create/edit
  body — they are server-authoritative and rejected (`extra="forbid"`).

## Steps
1. `cd moltrace_frontend`
2. `npm run generate:openapi` — regenerates `src/lib/api/schema.d.ts` (the binding contract). Commit
   it from the FE session; the backend session did not touch it.
3. Controlled-records list: add the "Include archived/deleted" toggle (`?include_deleted=true`) and
   render the new fields on archived rows.
4. Keep the archive/lock `reason` field required; surface the 422 reason-required message.
5. Verify on the dev server (`:3000`): create → archive a controlled record → confirm it leaves the
   default list and reappears with the toggle, showing reason/deleted_by/deleted_at. Vitest/jsdom is
   fine for panel rendering if a preview server isn't available.

## Grounding
Keep the "**supports ALCOA+ / 21 CFR Part 11, not compliant-for-you**" framing. Present archived
records as *retained and reversible-by-record*, not "deleted".
