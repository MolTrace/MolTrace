# Handoff → backend: make module entitlements actually enforce

**From:** frontend session, 2026-07-31
**Status:** frontend is ready and waiting; nothing here is implemented server-side yet.

## The problem

The tenant dropdown, the dashboard deployment card and the mobile tenant summary
all render a per-module licensing readout (SpectraCheck / Regentry / Repho). It
enforces nothing. Specifically:

1. `isProgramEnabled` and `isFeatureEnabled` are exported from
   `src/lib/tenant/tenant-context.tsx` and have **zero call sites** in the whole
   repo. Nothing is gated on them.
2. `programEnabled()` returns `true` when the entitlement list contains no
   matching record, so "no entitlement configured" and "explicitly granted" are
   indistinguishable to the UI.
3. Even a `false` entitlement would not stop anyone: the module routes, the nav
   and every API call remain reachable.

The frontend has been made honest about this in the meantime — the licensing
section is hidden entirely when the organization has no entitlement records, the
badges read "licensed / not licensed" rather than "enabled / locked", and a
footnote states that access is not restricted on this basis yet. **That copy
should be removed as part of landing this work.**

## Why this needs the backend first

Per the repo's contracts-first rule, the FastAPI routes and models change and
`schema.d.ts` is regenerated *before* any frontend work. More importantly, this
cannot be a frontend-only feature: client-side gating is a UI convenience, not a
control. If the API still serves a module's data to an unentitled tenant, hiding
the nav item changes nothing that matters.

There is also a prerequisite the frontend cannot satisfy alone — see item 1.

## Checklist

### 1. Establish the tenant on the request (prerequisite)

Today the tenant is asserted by the client via an `x-tenant-id` header, which a
caller can set to anything. Enforcement built on a self-asserted header is not
enforcement. Resolve the tenant server-side from the authenticated principal
(the access token's claims or the session record), and treat any client-supplied
`x-tenant-id` as a *request* that must be authorized against that principal's
memberships — reject with 403 when it does not match.

This is the single blocking item; everything below depends on it.

### 2. Decide the enforcement semantics

Answer these explicitly, because the frontend currently assumes the permissive
reading of each:

- **Absent record** — does "no entitlement row for program X" mean granted or
  denied? The client currently treats it as granted. Deny-by-default is the safer
  contract, but it will lock every existing tenant on the day it ships unless
  entitlements are backfilled first.
- **Granularity** — is entitlement per `program` (`spectracheck`,
  `regulatory_hub`, `reaction_optimization`), per `feature_key`, or both? The
  client models both and uses neither.
- **Read vs write** — does an unentitled tenant lose read access to data it
  created while previously entitled, or only the ability to create new work?
  Losing read access to existing records has records-retention implications
  (ALCOA+ / Part 11): data a regulated customer is obliged to retain must stay
  retrievable.
- **Expiry** — `TenantEntitlementRecord` carries `status`, and a lapsed licence
  is different from a never-granted one. Does `status` participate, or only
  `enabled`?

### 3. Enforce in the API

Add a dependency that resolves the caller's tenant (item 1), looks up the
entitlement for the program owning the route, and rejects when not entitled.
Apply it to every module-owned router — SpectraCheck sessions/analysis,
regulatory dossiers/action queue, reaction optimization runs/advisor — not only
to the list endpoints, or the detail routes stay open.

Return **403** with a machine-readable body so the client can distinguish this
from an auth failure:

```json
{ "detail": { "code": "module_not_entitled", "program": "reaction_optimization" } }
```

Note: the Next proxy at `app/api/backend/[...path]/route.ts` sanitizes 401/403
bodies. If the client needs to read `code`, either that sanitization needs an
allowance for this shape, or the signal has to travel another way — worth
agreeing before you pick the response format.

### 4. Expose the effective entitlement

`GET /tenants/{id}/entitlements` already exists. Confirm it returns a row per
program for the resolved tenant, including explicit denials, so the client can
tell "denied" from "unconfigured" — which is exactly the distinction it cannot
make today. If deny-by-default is chosen in item 2, say so in the payload
(e.g. a `default_policy` field) rather than leaving the client to assume.

### 5. Regenerate the contract

From `moltrace_frontend/`, with the backend running:

```
npm run generate:openapi
```

Writes `src/lib/api/schema.d.ts`. Commit it with the backend change.

### 6. Tell the frontend what landed

Hand back: the endpoint(s) and dependency name, the exact 403 body shape, the
answers to item 2, and whether entitlements are now backfilled for existing
tenants. The frontend work is then:

- gate nav items and route entry on `isProgramEnabled` (the call sites that
  should exist and do not)
- handle the 403 with a real "not licensed for your organization" state instead
  of a generic error
- delete the "does not restrict module access on this yet" footnote and restore
  the "access" wording in `components/app/tenant-selector.tsx`,
  `components/dashboard/dashboard-v0.tsx` and
  `components/admin/mobile-tenant-summary-workspace.tsx`
- drop `licensingConfigured` from the tenant context if item 4 makes it moot

## Related

- `MolTrace_Standalone_Modules_Plan.md` (repo root) — the commercial goal this
  serves: each module independently sellable.
- `src/lib/tenant/tenant-context.tsx` — `programEnabled` / `featureEnabled`,
  the permissive defaults described above.
