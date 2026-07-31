# Frontend handoff — standalone modules (Wave 0, Layers 0.A + 0.C)

**From:** backend session. **Commits:** `590c001` (trust hardening), `4b5c24c` (module enforcement).
**Backend status:** merged to `main`, full suite green (3251 passed, 9 skipped).
**Frontend scope:** consume the new contract. The full Layer 0.D scope lives in
`MolTrace_Standalone_Modules_Plan.md`; this handoff covers only what the backend change unblocks.

---

## What changed on the server

A deployment now declares which products it serves via `MOLTRACE_ENABLED_MODULES`
(`spectracheck` | `regulatory_hub` | `reaction_optimization`; defaults to all three). A
router-level gate refuses routes belonging to a product the deployment does not serve.

**This is live enforcement, not a readout.** On a `spectracheck`-only deployment,
`GET /regulatory/dossiers` returns `403` to an authenticated caller — regardless of what the UI
shows. The frontend's job is now to stop offering what the server will refuse.

---

## Task 1 — Regenerate the typed contract *(prerequisite for everything below)*

```bash
cd /Users/michaelhotor/MolTrace/moltrace_backend && .venv/bin/uvicorn nmrcheck.main:app --port 8000
```

Then, in a second shell:

```bash
cd /Users/michaelhotor/MolTrace/moltrace_frontend && npm run generate:openapi
```

Writes `moltrace_frontend/src/lib/api/schema.d.ts`.

**Contract delta by name:**

| Kind | Name | Note |
|---|---|---|
| New path | `GET /system/capabilities` | authenticated |
| New schema | `SystemCapabilities` | `{ modules: ModuleCapability[] }` |
| New schema | `ModuleCapability` | `{ module, display_name, included }` |
| Changed enum | `RegulatoryActionType` | gained `elemental_impurity_review` |

**Done when:** `grep -c "SystemCapabilities" src/lib/api/schema.d.ts` is non-zero and
`grep -c "elemental_impurity_review" src/lib/api/schema.d.ts` is non-zero.

---

## Task 2 — Add the missing regulatory action type to the filter

A backend bug meant `GET /regulatory/action-items` returned a sanitized 500 forever after any ICH
Q3D elemental assessment: the store wrote `action_type="elemental_impurity_review"`, which was not
a declared type. The type is now declared, so the list works again — but the frontend filter
dropdown still doesn't offer it.

- **File:** `moltrace_frontend/components/regulatory-hub/regulatory-action-queue.tsx:131`
- **Change:** add `"elemental_impurity_review"` to the `REGULATORY_ACTION_TYPES` array, after
  `"residual_solvent_review"` (matching backend order).
- **No label map needed** — `labelFromSnake` (same file, line 163) already renders it as
  "elemental impurity review", and existing rows already display correctly via line 574. The only
  gap is that users cannot *filter* by it.

**Done when:** the Action Queue type filter lists "elemental impurity review", and selecting it
filters rather than returning everything.

---

## Task 3 — Read what the workspace actually includes

**Endpoint:** `GET /system/capabilities` (requires auth)

```jsonc
{
  "modules": [
    { "module": "spectracheck",          "display_name": "SpectraCheck",          "included": true  },
    { "module": "regulatory_hub",        "display_name": "Regentry",              "included": false },
    { "module": "reaction_optimization", "display_name": "Reaction Optimization", "included": false }
  ]
}
```

All three products are **always listed**, each with an `included` flag — deliberately, so the UI
can show an honest "not included in this workspace" state rather than silently omitting things.

Recommended shape: one provider/hook (e.g. `useIncludedModules()`) fetched once at shell mount,
exposing `isIncluded(key)`. Mirror the existing `developer-mode-provider` pattern.

**Important — this replaces the entitlement guess, it does not extend it.**
`src/lib/tenant/tenant-context.tsx` derives `moduleAccess` from
`GET /tenants/{id}/entitlements` and fails **open** (no matching row ⇒ enabled). Two problems:
that endpoint is now operator-only (`590c001`), so ordinary users get 403 and fall back to
"everything enabled"; and entitlement rows enforce nothing anyway. `/system/capabilities` is the
authoritative answer. Treat `moduleAccess` as legacy and drive UI decisions from the new hook.

**Done when:** with the backend started as `MOLTRACE_ENABLED_MODULES=spectracheck ...`, the hook
reports exactly one included product.

---

## Task 4 — Distinguish "not in your plan" from "not allowed"

A refused product route returns:

- **Status:** `403`
- **Body:** `{"detail": "module_not_licensed"}`
- **Header:** `X-MolTrace-Module: regulatory_hub` (the product that was refused)

**Use the header.** I verified the proxy at `moltrace_frontend/app/api/backend/[...path]/route.ts`
builds `responseHeaders` from the upstream response and preserves them even on the sanitized
branch — so `X-MolTrace-Module` **already reaches the browser today with no proxy change.** The
body is still replaced with the generic access-denied string on that path.

*Optional, cleaner:* extend the existing 401 passthrough (route.ts ~line 109) to also allow
`"detail":"module_not_licensed"` through on 403, so the code is available in the body too. Purely
additive — the same pattern already ships for the 401 codes.

Central handling belongs in `apiFetch`: on a 403 carrying that header, raise a distinct
"module not included" signal rather than a generic access error, so callers can render the
upgrade state instead of an error toast.

**Done when:** on a `spectracheck`-only backend, a Regentry request surfaces as a
"not included" state, not "You do not have access to perform this action."

---

## Task 5 — Stop offering what the server will refuse

This is the substantive Layer 0.D work; full detail in the plan. Ordered by user-visible impact:

1. **Sidebar** — `moltrace_frontend/components/app/app-sidebar.tsx:60`. `navGroups` is a static
   literal listing all three products. Filter by `isIncluded`, and drop a group entirely when it
   empties. Note `/review` and `/reports` are SpectraCheck-only surfaces sitting in generic nav
   groups — a Regentry-only buyer currently gets two permanently empty top-level items.
2. **Nav is defined in four places** and will drift: the sidebar, `MobileBottomNav`, the command
   palette in `app-topbar.tsx`, and a dead second shell at `components/app-shell/AppShell.tsx`.
   Extract one route→module map first, then gate from it.
3. **Cross-module cards** mounted unconditionally inside module workspaces — the
   SpectraCheck→Regentry impact card, the Regentry→Repho handoff card, the reaction regulatory
   panels. Each needs a declared behaviour: hide, or an inert "available with <product>" tile.
   Never a spinner that resolves to an error.
4. **Shell-wide fetches** — `OverviewDataProvider` requests SpectraCheck sessions on every page
   for every tenant, and the topbar requests regulatory notifications app-wide. Guard both.
5. **Dashboard** — five hardcoded sections, no reaction section at all, and a Cross-Module
   Command Center that renders "—" for absent products.

---

## Verification: run the whole thing single-module

```bash
cd /Users/michaelhotor/MolTrace/moltrace_backend && \
  MOLTRACE_ENABLED_MODULES=spectracheck .venv/bin/uvicorn nmrcheck.main:app --port 8000
```

A SpectraCheck-only session should show one product in the nav, no Regentry/Repho entries, no
cross-module cards, no Action Queue, **and zero failed requests in the console**. The console is
the real test — a UI that hides a product but still fetches its data has not been gated.

---

## Not in scope for this handoff

- Per-tenant entitlements (deferred with tenant binding — see Decision 3 in the plan). Today the
  SKU boundary is the deployment, so `/system/capabilities` is deployment-scoped, not per-user.
- Per-module metering. The gate resolves the product per request but does not yet emit usage rows.
