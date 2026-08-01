# Landed → frontend: module entitlements now enforce (backend)

**From:** backend session, 2026-07-31
**Answers:** `moltrace_frontend/docs/handoff_entitlement_enforcement.md`
**Contract:** `moltrace_frontend/src/lib/api/schema.d.ts` regenerated + committed with this change.

## Decisions made (handoff item 2)

- **Default policy — allow-by-default, honoring explicit denials.** A program with no entitlement
  row stays open; a program is denied only when every entitlement row that exists for it has
  `enabled=false`. No existing tenant is locked out on ship. The payload states this via
  `default_policy: "allow"` so the client never has to assume it.
- **Tenant binding — derived from organization membership.** A new nullable edge
  `organizations.tenant_id` binds an org to a SaaS tenant. The caller's tenant(s) = their active
  `team_members` orgs → each org's `tenant_id`. The `x-tenant-id` header is honored only when it
  names one of the caller's own tenants; a self-asserted foreign tenant is rejected (item 1).
- **Granularity — per program** (`spectracheck`, `regulatory_hub`, `reaction_optimization`). This
  is what the nav gates on. `feature_key` is unchanged and not yet used by the gate.
- **Read vs write — writes/new work are gated; reads are preserved.** A denied tenant keeps
  read access (`GET`/`HEAD`) to records it already created (ALCOA+/Part 11 retention); only
  mutating methods (`POST`/`PUT`/`PATCH`/`DELETE`) to the module are refused.

## Is it live? Not until an operator links orgs + records a denial.

Every existing organization has `tenant_id = NULL`, so it resolves to **no tenant → allow-by-default
everywhere**. Enforcement becomes real for a tenant only once an operator (super-admin) both:
1. binds the tenant's org(s): `PUT /tenants/{tenant_id}/organizations/{organization_id}`, and
2. records an explicit denial: `POST /tenants/{tenant_id}/entitlements` with `enabled=false` for the
   program.

So this change cannot lock anyone out on deploy; it activates deliberately, per tenant.

## Endpoints + dependencies

- **Enforcement** is two router-level dependencies on the main router (cover every detail/child
  route in one place, keyed on the route path template):
  - `_tenant_membership_gate` — item 1: `/tenants/{tenant_id}/…` requires membership of that tenant
    (super-admin/system unrestricted) → else **403**.
  - `_module_entitlement_gate` — item 3: a write to a module the caller's tenant is explicitly
    denied → **403 `module_not_entitled`**.
- **`GET /tenants`** — now membership-scoped for a normal user (returns only their tenants, no
  longer a blanket 403); operators still see all. This is what lets the client render its licensing
  readout for the caller's own org.
- **`GET /tenants/{tenant_id}/entitlements`** — unchanged shape (raw rows), now membership-gated.
- **`GET /tenants/{tenant_id}/effective-entitlements`** *(new, item 4)* — per-program effective
  state, distinguishes denied from unconfigured:
  ```json
  {
    "tenant_id": 1,
    "default_policy": "allow",
    "programs": [
      { "program": "spectracheck",          "display_name": "SpectraCheck",          "entitled": true,  "explicit": false },
      { "program": "regulatory_hub",         "display_name": "Regentry",              "entitled": true,  "explicit": false },
      { "program": "reaction_optimization",  "display_name": "Reaction Optimization", "entitled": false, "explicit": true  }
    ]
  }
  ```
  `entitled` is what to gate on; `explicit=true` means it's a real decision (a row exists), so a
  `false` is a denial rather than the default.
- **`PUT /tenants/{tenant_id}/organizations/{organization_id}`** *(new)* — super-admin binds an org
  to a tenant; returns the `OrganizationRecord` (now carries `tenant_id`). This is the operator
  activation step, not a client action.

## The 403 shape (item 3) — and the proxy note

```json
{ "detail": { "code": "module_not_entitled", "program": "reaction_optimization" } }
```
plus a response header `X-Module-Not-Entitled: reaction_optimization`.

Important: the **backend** already sanitizes 401/403 bodies (`_safe_http_exception_detail`) — it now
has an explicit allowance for `module_not_entitled` (like the existing feature-flag carve-out), so
the machine-readable `detail` survives. The **Next proxy** (`app/api/backend/[...path]/route.ts`)
also sanitizes 401/403 bodies; the header is there precisely so the client can read the signal even
if the proxy strips the body. Decide on the FE side whether to (a) allow this `detail` shape through
the proxy, or (b) read the `X-Module-Not-Entitled` header. Either works.

## Frontend work (handoff item 6)

1. `schema.d.ts` is already regenerated and committed — no need to re-run `generate:openapi` for this.
2. Gate nav items / route entry on `isProgramEnabled` — the call sites that should exist and don't.
   Prefer driving it from `GET …/effective-entitlements` (`entitled` per program) rather than the
   raw rows, so "denied" vs "unconfigured" is unambiguous. Drop the permissive `programEnabled()`
   "absent = enabled" logic in favor of the server's `entitled` flag.
3. Handle the 403 `module_not_entitled` with a real "not licensed for your organization" state
   (read `detail.code` and/or the `X-Module-Not-Entitled` header), not a generic error.
4. Remove the interim "does not restrict module access on this yet" footnote and restore the
   "access" wording in `tenant-selector.tsx`, `dashboard-v0.tsx`,
   `mobile-tenant-summary-workspace.tsx`.
5. `licensingConfigured` can be replaced by `default_policy` + the per-program `explicit`/`entitled`
   flags from `effective-entitlements`.

## Coverage + known follow-ups (not yet gated)

The path→program map (`_module_program_for_path`) gates: `/reaction-*` → reaction_optimization;
`/regulatory/*` (minus the mis-filed `/regulatory/impurities` and `/regulatory/spc`, which are
spectral) and `/ctd-module3-bundles` → regulatory_hub; `/spectracheck/*`, `/analyze*`, `/spectrum/*`
→ spectracheck. Deliberately **not** yet gated (documented, safe under allow-by-default):

- the remaining legacy analysis prefixes beyond `/analyze` and `/spectrum` (`/nmr/*`, `/fid/*`,
  `/carbon13/*`, `/ms/*`, …) — extend the map when ready;
- the `nmr2d_router` (`/nmr2d/*`) — mounted with its own gate, not the main router's;
- cross-module routes (`/bridges/*`, `/cross-module/*`) — need an "either vs both" policy;
- `PATCH /tenant-entitlements/{entitlement_id}` membership authorization (still uses its existing
  `x-tenant-id`↔row scope check; the read hole on `/tenants/{tenant_id}/…` is what item 1 closed).

Extend `_module_program_for_path` (the single source of truth), not the decorators.
