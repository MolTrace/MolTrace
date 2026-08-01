# MolTrace — Standalone Modules Program

**Goal:** make SpectraCheck (analytical evidence), Regentry (regulatory insight) and Repho (reaction prediction & optimization) each function as an independent, separately sellable, separately usable product — without breaking the connected platform for customers who buy more than one.

**Status of this document:** plan of record. Phases are ordered, lane-separated (backend / frontend / docs-GTM), and each carries a runnable acceptance test. Every work item is tagged **ADD / MODIFY / REDESIGN / REBUILD / ALREADY OK** against what is in the repo today.

**Canonical module keys — reuse, do not invent:** `spectracheck` | `regulatory_hub` | `reaction_optimization`
(`ProductProgramKey`, [models.py:5895](moltrace_backend/src/nmrcheck/models.py))

---

## Part 0 — What "standalone" has to mean

Eight gates. A module is standalone when it passes all eight, and the CI matrix in Layer 0.F proves it on every commit.

| # | Gate | Test |
|---|---|---|
| **G1** | **Independent activation** | A new account reaches a real first result — verified spectrum / impurity assessment / optimization proposal — with no sibling module licensed and no sibling module's entity created. |
| **G2** | **Entitlement-true surface** | Nav, routes, deep links, dashboard, search and mobile show only what is licensed. Zero dead links, zero permanently-empty top-level nav items. |
| **G3** | **Server-authoritative authorization** | A spectroscopy-only principal calling a regulatory route is denied by the server, not by the UI. Enforcement is default-deny: a new unclassified route fails closed. |
| **G4** | **Module-owned primitives** | Each module owns its workspace root, collaboration/review/approval, audit chain, e-signature path and report/export — none borrowed from a sibling. |
| **G5** | **Documented degradation** | Every cross-module surface has one declared behaviour: *hide*, *degrade to manual input*, or *inert "available with X"*. No spinner that resolves to an error. |
| **G6** | **Independently qualifiable** | Per-module validation package, all-public gold set, per-module Part 11 controls assessment — inspectable without pulling the other two modules into scope. |
| **G7** | **Portable in and out** | Module-native import **and** lossless open export (JCAMP-DX/nmrML; eCTD-ready; ORD/CSV), available in the browser tier. Standalone is not a trap. |
| **G8** | **Commercially self-contained** | Own SKU, published price, trial, per-module metering, and upgrade-to-second-module as a **configuration change with zero data migration** — same schema, same database, no re-implementation. |

---

## Part 1 — Where we actually stand

Nine parallel audits, including live probes against a running instance. Headline verdict per module:

| Module | Data-boundary readiness | Product readiness | The real blocker |
|---|---|---|---|
| **SpectraCheck** | **Highest.** Zero foreign keys point *outward* from any spectroscopy table; 15 point *inward*, all nullable `SET NULL`. Minimal path (raw FID → evidence report) needs only an authenticated user, a writable vault and a SMILES string. | Medium | Packaging, not coupling. Plus the qNMR purity engine — the headline ±0.5% claim — **has no HTTP route at all**. |
| **Regentry** | **High.** Every headline calculator is stateless and dossier-free: verified live on an empty database returning correct Q3A/B bands, M7 class 2, CPCA category 1 (AI 26.5 ng/day). | Low–Medium | Empty database = empty product (no seeder anywhere), four headline jobs are library-only with no route, and reference data is globally writable. |
| **Repho** | **High.** 35 reaction tables, exactly two carry a SpectraCheck FK, both nullable. Manual outcome entry is already a first-class path. | Medium | The build spec **explicitly declares it un-sellable standalone**, and `scikit-learn` is absent from the production image so every "Bayesian optimization" run silently returns `rule_based_fallback`. |

### The three findings that reframe the work

**1. Entitlements are 100% bookkeeping and 0% enforcement — proven, not inferred.** With all three programs set `enabled=False` (module-readiness correctly reporting `disabled_by_entitlement`), a plain user still received 200 on `GET /spectracheck/sessions`, 200 on `GET /regulatory/dossiers`, 200 on `GET /reaction-projects` and 201 on `POST /reaction-projects`. Every reference to `TenantEntitlementORM` outside the ORM lives in `tenant_saas_store.py` plus admin CRUD.

**2. No request can answer "which tenant is this."** `AccessContext` carries only `user | system_api_key | raw_token` ([api.py:1065](moltrace_backend/src/nmrcheck/api.py)). `rate_limit.py:18-20` states it in a code comment: *"Tenant == user today."* Worse, `tenants` and `organizations` are two disconnected identity spaces with no FK between them — there is nothing to resolve a licence against.

**3. The collaboration layer is SpectraCheck-only by NOT-NULL foreign key.** `project_permissions`, `session_reviewers`, `evidence_comments`, `review_tasks`, `approval_records`, `report_locks`, `secure_share_links` all hard-require `spectracheck_projects`/`spectracheck_sessions` ([orm.py:1104–1256](moltrace_backend/src/nmrcheck/orm.py)). **A Regentry-only or Repho-only customer today has no team RBAC, no approvals, no report locks and no share links.** This is the single largest rebuild in the program.

### Live defects found in passing — fix regardless of the standalone decision

These are not standalone work. Three are security or data-integrity issues.

| Sev | Defect | Evidence |
|---|---|---|
| **Critical** | Any authenticated non-admin can read **and create** entitlements for any tenant. `x-tenant-id` is a self-asserted header only checked for equality against the path id. A customer can mint their own licence rows. | [api.py:13234](moltrace_backend/src/nmrcheck/api.py), `POST /tenants/{id}/entitlements` [api.py:15912](moltrace_backend/src/nmrcheck/api.py) |
| **Critical** | `GET /regulatory/action-items` **500s permanently** after any ICH Q3D elemental assessment — the store writes `action_type="elemental_impurity_review"`, which is not a member of `RegulatoryActionType`. The module's task inbox is poisoned by a headline job. | [regulatory_compliance_store.py:1141](moltrace_backend/src/nmrcheck/regulatory_compliance_store.py) vs [models.py:2874](moltrace_backend/src/nmrcheck/models.py) |
| **Critical** | All regulatory reference data is global and writable by any authenticated non-admin. Verified: a rule set created by user *bob* and marked active silently changed user *alice*'s residual-solvent verdict — toluene flagged class 1 at 1 ppm instead of ICH Q3C's 890 ppm. | `regulatory_rule_sets` [orm.py:4866](moltrace_backend/src/nmrcheck/orm.py) — no owner/tenant column |
| **Critical** | Managed files and artifacts are hardcoded to local filesystem. On Cloud Run they are lost on instance recycle. Only `raw_archives` has a GCS backend. | [orchestration_store.py:344](moltrace_backend/src/nmrcheck/orchestration_store.py) |
| **High** | `report_sha256` prefers a **client-supplied** hash over the server computation — a caller can post a report body with an arbitrary digest. | [spectracheck_store.py:980](moltrace_backend/src/nmrcheck/spectracheck_store.py) |
| **High** | `scikit-learn` is not in the production image, so `reaction_bo` takes the `sklearn_unavailable` branch and returns `model_type="rule_based_fallback"` on every run. We are shipping k-NN labelled "Gaussian process EI". | [Dockerfile:30](moltrace_backend/Dockerfile), [reaction_bo.py:958](moltrace_backend/src/nmrcheck/reaction_bo.py) |
| **High** | `POST /regulatory/action-items` accepts a `dossier_id` the caller does not own (cross-owner write); and a dossier-less action item is created 201 then permanently invisible to its creator. | [api.py:22469](moltrace_backend/src/nmrcheck/api.py), [regulatory_compliance_store.py:597](moltrace_backend/src/nmrcheck/regulatory_compliance_store.py) |
| **Medium** | New users see fabricated demo data — "23 active", "7 in review", reviewer "Dr. Chen" — substituted whenever live data is unavailable. A GxP buyer seeing invented review counts on first login is a trust failure. | [dashboard-v0.tsx:167](moltrace_frontend/components/dashboard/dashboard-v0.tsx) |

---

## Part 2 — Competitive read → the six rules we build to

Fourteen vendors researched. The market consolidated underneath us: Mestrelab/Mnova is majority-owned by **Bruker** (SciY), **Revvity** agreed to acquire ACD/Labs (2025-11-10), **Siemens** closed its $5.1B Dotmatics acquisition (2025-07-01). Vendor neutrality is now a live procurement argument, not a marketing line.

| Rule | Adopted from / against | Why |
|---|---|---|
| **1. Platform + separately licensed apps on one shared data model** | **Adopt — Veeva.** Vault RIM applications "share a common data model… run in one Vault" and are usable alone or together; expansion is cross-sell, not migration. | The only pattern where a standalone SKU and a suite strategy are compatible. We already have the scaffolding (`ProductProgramKey`, cross-program transition models, `module_order`). |
| **2. No prerequisite-licence matrix** | **Reject — Mnova.** "Mnova Verify requires both Mnova NMR and Mnova NMRPredict licenses." Wanting only qNMR costs $1,880/yr; only Verify costs $2,820/yr — at which point the $2,250 Suite is cheaper. That is the design intent. | The most attackable feature of the incumbent set. One MolTrace entitlement must cover the whole advertised job. Say so in writing. |
| **3. Compliance floor in every SKU, including the cheapest** | **Adopt — Veeva** (validation documentation bundled per release). **Reject — ACD/Labs**, who state "it is the ultimate responsibility of the user to validate," selling IQ/OQ/PQ scripts as a service. Mnova has **no locatable Part 11 posture at all**. | This is where a single-module MolTrace beats a point tool on substance, not price. Never sell the validation package separately. |
| **4. Lossless open export from every module, in the browser** | **Reject — both.** Mnova is `.mnova`-first with a documented *subset* export to JCAMP-DX/NMReDATA. ACD/Labs export is "desktop applications only" — their web tier cannot export at all — and AnIML/nmrML/mzML are absent entirely. | Asymmetric portability is how these products stay bought, and "standalone" reads as "trapped in a small silo" unless we invert it. |
| **5. Regulation-anchored SKU boundaries** | **Adopt — Lhasa/Instem/Freyr**, who let a named guideline define the product. **Reject** Lhasa's gating *below* product level ("a Sarah Nexus license with the mutagenicity model enabled"). | A QA lead buys "the thing that closes our Part 11 gap," not "an NMR module." It also anchors value far above Mnova's $940 price point. |
| **6. Published price, named seats, no licence daemon** | **Adopt — Mestrelab's transparency** (the only vendor in the category publishing list prices). **Reject** their MLicServer, Schrödinger's License Manager, and Waters' per-instrument/per-brand licensing. | Browser-native means entitlements resolve server-side. Commit in writing that price never depends on which spectrometer produced the data. |

**Where a standalone MolTrace SKU is strictly better:** every SKU ships the audit floor; no dependency matrix; POC in days not a procurement cycle; upgrade is an entitlement flip; lossless export; vendor-neutral in a consolidating market; price independent of instrument count or brand.

**Where we are weaker, and what must be true to win anyway:**
- Mnova has ~20 years of processing maturity and runs offline on air-gapped GMP instrument workstations. We cannot. → Win on the regulated workflow around the spectrum, not on processing nostalgia.
- Vendor-format ingestion breadth is table stakes (ACD/Labs cites 150+). One unreadable dataset in a first meeting ends it. → Ingestion breadth is a standalone-SKU requirement, not a nice-to-have.
- Lhasa's models are regulator-accepted; ours are not. → Never imply substitution. Position Regentry as the controlled-record layer *around* Derek/Sarah, with connectors.
- SOC 2 is not yet held. → Keep all public framing at **"designed to support"** — never a held certification.
- Repho executes nothing and has no robotics partnerships. → Sell the half-closed loop as the compliance posture it is.

---

## Wave 0 — Platform Core & Enforcement

Shared work, done once. **Nothing in Waves 1–3 is safe to ship before Layers 0.A–0.C land.**

### Layer 0.A — Trust: close the holes before licensing becomes load-bearing
**Lane: backend.** A licence system built on a self-asserted header is theatre.

- **MODIFY** — Stop trusting `x-tenant-id`. Replace `_require_tenant_scope_header` ([api.py:13234](moltrace_backend/src/nmrcheck/api.py)) with server-side resolution; treat the header purely as a UI hint that must *match* the derived value.
- **MODIFY** — Gate every write on the entitlement surface (`POST /tenants/{id}/entitlements`, `PATCH /tenant-entitlements/{id}`, `POST|PATCH /feature-flags`) behind `require_admin`.
- **MODIFY** — Gate `POST /regulatory/jurisdictions`, `/regulatory/rule-sets` and `/regulatory/sources/upload` behind `require_admin`, matching the surveillance-config precedent at [api.py:18030](moltrace_backend/src/nmrcheck/api.py).
- **MODIFY** — Fix the `elemental_impurity_review` vocabulary bug and add an invariant test that every `action_type` literal reaching the store is a member of `RegulatoryActionType`.
- **MODIFY** — Always compute `report_sha256` server-side; 400 on client mismatch rather than accepting it.

**Done when:** a non-admin user receives 403 on every entitlement and reference-data write; `GET /regulatory/action-items` returns 200 after a Q3D assessment; a report posted with a bogus digest stores the server digest.

### Layer 0.B — Identity: give a request a tenant *(deferred — Decision 3)*
**Lane: backend.** **Off the critical path.** Every paid SKU is a dedicated deployment whose modules come from the deployment profile, so the gate needs no tenant resolution. This layer is required before the pooled academic/trial tier and before per-tenant metering — build it then, not now.

- **ADD** — `organizations.tenant_id` nullable indexed FK → `tenants.id`, with a unique index (one org maps to at most one tenant). Real alembic revision + dev backfill; validate the migration in isolation by driving `m.upgrade()` with an Operations context.
- **ADD** — `AccessContext.tenant_id` (and `organization_ids`), populated in `get_optional_access_context` from the derived chain: bearer token → `users.email` → `team_members(status='active').organization_id` → `organizations.tenant_id`. Derived **server-side only**.
- **ADD** — The missing alembic revision creating `tenants` / `tenant_environments` / `subscription_plans` / `tenant_entitlements` / `feature_flags`. These tables exist in production **only** because `create_all` runs at boot — a constraint added later would never land.
- **MODIFY** — Widen `rate_limit._resolve_key` to `tenant:{id}:…` as its own docstring anticipates.

**Done when:** an authenticated request exposes a server-derived `tenant_id`; a user with no org membership resolves to `None` and is handled explicitly; the new migration applies cleanly to a copy of production.

### Layer 0.C — Licence: resolve it, enforce it, prove it
**Lane: backend.** This is the spine of the whole program.

**Resolution rule:** effective modules = **deployment profile ∩ tenant entitlements**. Per Decision 3 every paid SKU is a dedicated deployment, so the profile alone decides and the gate works with *no tenant resolution at all* — which is both simpler and stronger than a database lookup, because there is no tenant binding to get wrong. Entitlements refine the profile later, for pooled deployments only.

- **ADD** — `MOLTRACE_ENABLED_MODULES` setting (default: all three), validated against `ProductProgramKey` at startup and surfaced in `validate_startup_settings`. This is the SKU boundary for every dedicated deployment.
- **ADD** — `nmrcheck/module_access.py`: `MODULE_ROUTE_PREFIXES` (first match wins, mirroring `rate_limit._SENSITIVE_PREFIXES`), `module_for_route(path) -> ProductProgramKey | None`, and an explicit `MODULE_EXEMPT_PREFIXES` for auth/system/admin/tenants/analytics. `reaction_access.is_reaction_gated_path` ([reaction_access.py:164](moltrace_backend/src/nmrcheck/reaction_access.py)) is the working template.
- **REDESIGN** — Enforcement is **fail-closed**, cut over in three deliberate steps (Decision 1): (1) ship the gate in **observe mode** — compute the decision, emit an audit line, deny nothing; (2) read the observations and run the backfill; (3) flip to deny. Observe mode turns a risky cutover into a data-driven one and costs almost nothing. *This is the shape of our own "tests can encode the bug" lesson — write the invariant first, then re-baseline visibly.*
- *(pooled tier — deferred with 0.B)* **ADD** — Effective-entitlement resolver: `enabled = any(row.enabled and row.is_effective(now) for row in rows)`. `effective_start`/`effective_end` are stored today but **never evaluated** — a trial that ended in 2025 still reads as enabled.
- *(pooled tier — deferred with 0.B)* **MODIFY** — `tenant_entitlements` has **no uniqueness constraint**, and enablement is `any(...)`, so one stale `enabled=True` row silently re-enables a disabled module. Add `UniqueConstraint(tenant_id, feature_key)` and upsert.
- *(pooled tier — deferred with 0.B)* **REDESIGN** — Absent row = not licensed, with a one-time backfill writing `enabled=True` rows for every existing tenant. Keep the informational readiness report fail-open, but add a `source` field (`entitlement` | `default_open` | `deployment_profile`) so "licensed" is distinguishable from "never configured".
- **ADD** — `_module_entitlement_gate` as a **second router-level dependency** at [api.py:29998](moltrace_backend/src/nmrcheck/api.py), mirroring how `_baseline_access_gate` is attached. Also attach to `nmr2d_router` (unambiguously spectracheck); deliberately exempt `scim_router`.
- **ADD** — Error semantics: 403 with detail exactly `module_not_licensed`, program name carried in an `X-MolTrace-Module` **header** (the frontend proxy forwards headers untouched but rewrites bodies).
- **ADD** — The classification regression test, cloning the two-layer pattern from `tests/test_reaction_access.py`: walk `app.routes`, flatten each `route.dependant` tree, assert the gate appears on every path where `module_for_route` is non-null and does **not** appear on exempt paths, plus a floor assertion so the map cannot silently shrink.
- **ADD** — `GET /me/capabilities`: licensed modules, effective dates, and the honest per-capability readout (the `reaction-capabilities` precedent already exists).
- **ADD** — Metering from the gate: it resolves `program` on every request, so emit one server-side usage row. Add a `program` column to `usage_events` now and `tenant_id` with 0.B (today it has neither, and the only writer is a client-driven browser POST).

**Done when:** with `MOLTRACE_ENABLED_MODULES=spectracheck`, a plain user receives 403 `module_not_licensed` on `GET /regulatory/dossiers` and 200 on `GET /spectracheck/sessions`; a newly added unclassified route fails the classification test.

### Layer 0.D — Surface: make the UI tell the truth
**Lane: frontend.** Starts only after 0.C ships and `schema.d.ts` is regenerated.

The good news: `TenantProvider` **already** fetches entitlements and derives `moduleAccess` for exactly the canonical keys ([tenant-context.tsx](moltrace_frontend/src/lib/tenant/tenant-context.tsx)). The bad news: `isProgramEnabled`/`isFeatureEnabled` have **zero consumers repo-wide**.

- **MODIFY** — Lift the proxy's passthrough block above the `if (status === 401)` branch so `module_not_licensed` survives ([route.ts:118](moltrace_frontend/app/api/backend/[...path]/route.ts) currently replaces every 403 body with a generic string).
- **MODIFY** — `programEnabled()` fails **open** (`if (matches.length === 0) return true`). Invert to fail-closed once entitlements have loaded, with an explicit `loading` tri-state so the UI shows a skeleton rather than flashing "locked". Distinguish *unknown* from *empty*: a fetch failure must render a degraded shell, not the full platform.
- **REDESIGN** — One `lib/nav/module-routes.ts` as the single source of truth. There are **four** independent nav definitions today (sidebar, mobile bottom nav, command palette, plus a dead second shell) that will drift the moment gating lands. Delete `components/app-shell/AppShell.tsx`.
- **REDESIGN** — Resolve the duplicate `src/app` tree (78 mirrored pages, some shims, some full copies). Doing entitlement work across two half-authoritative trees guarantees an ungated copy survives.
- **ADD** — `<ModuleGate module="…">` + `useModuleAccess(key)`, mirroring the existing `developer-mode-provider` pattern. Apply at three altitudes: nav filtering, cross-module card wrapping, per-route guard.
- **ADD** — `middleware.ts` with the route→module map; 302 unlicensed module routes to a "not included in your plan" page. There is no middleware and no route guard of any kind today.
- **MODIFY** — Make the app shell's blanket fetches conditional: `OverviewDataProvider` fetches SpectraCheck sessions on **every page for every tenant**; the topbar fetches regulatory notifications app-wide.
- **REDESIGN** — Drive dashboard sections from entitlements. Today: five hardcoded sections, **no reaction section at all**, and a Cross-Module Command Center rendering "—" for absent modules.
- **REBUILD** — Replace fabricated demo data with per-module first-run empty states (`components/ui/empty.tsx` already exists and is used in ~20 workspaces).

**Done when:** a SpectraCheck-only session shows one module in the nav, no Regentry/Repho entries, no cross-module cards, no Action Queue, and a first-run empty state with "Upload a spectrum" — with zero failed requests in the console.

### Layer 0.E — Carve-out: shared primitives that are secretly SpectraCheck's
**Lane: backend.** The largest rebuild; can run in parallel with 0.D.

> **Re-sequenced.** The collaboration layer exists so a *team* can act on a subject — but Regentry dossiers and Repho campaigns were single-user owned, so generalizing review-tasks and permissions onto them would have produced a queue only one person could ever see. Team **ownership** is the prerequisite, and it delivers the commercial outcome ("sellable to a team") at a fraction of the risk. Regulatory ownership landed first; the polymorphic carve-out below now has something to attach to.
>
> **Done — Regentry team ownership.** `regulatory_dossiers.organization_id` (nullable, migration `0032`), stamped from the creator's sole active organization; `dossier_owned_by`, the dossier list, and the policy engine all widened in lockstep so the queue can never show a row that 404s when opened. New PDP policy `permit-org-member-dossier-rw` with a pure `_shares_owner_org` condition — membership is resolved in the store and passed through `Resource.attrs`, keeping conditions database-free. NULL organization preserves creator-only behaviour exactly, so no existing row changed and no backfill was needed. Shared membership helper: `org_membership.py`.
>
> **Next in 0.E:** the same ownership change for `reaction_projects` (structurally identical), then the polymorphic `(subject_type, subject_id)` work below.

- **REBUILD** — Polymorphic `(subject_type, subject_id)` on the collaboration layer, using the pattern the compliance floor already uses (`electronic_signature_records.target_type/target_id`). Retain the legacy spectracheck FK nullable for back-compat; register the existing spectracheck path first so nothing regresses. Without this, Regentry-only and Repho-only SKUs have no approvals, no reviewers, no share links.
- **MODIFY** — `ai_governance_records.dossier_id`, `qnmr_compliance_profiles.dossier_id` and `analytical_method_validation_profiles.dossier_id` are all **NOT NULL** → a SpectraCheck-only SKU loses AI governance and its own qNMR method metrology. Make nullable + add the polymorphic subject alternative, with a store guard requiring exactly one.
- **ADD** — A content-bound e-signature path for module reports. `_BINDABLE_TARGET_TYPES` is `{controlled_record, system_release}` only, so signing a SpectraCheck report today yields an **unbound** signature.
- **MODIFY** — `_validated_program_order` raises unless the order is *exactly* the three-module triple ([product_orchestration_store.py:1093](moltrace_backend/src/nmrcheck/product_orchestration_store.py)), making a one- or two-module deployment inexpressible. Relax to a subset + relative-order check.
- **REDESIGN** — `cross_module_command_center_summaries` and `compact_module_summaries` hardcode one column per module **in the schema**. Replace with a single `module_summaries_json` keyed by program key.
- **MODIFY** — Hoist the four duplicated copies of the module list (`product_orchestration_store`, `tenant_saas_store`, `golden_pilot_store`, `mobile_store`) into one canonical tuple before adding any filter logic.
- **MODIFY** — Add a canonicalisation helper for the three divergent key vocabularies (`ProductProgramKey`, `AIEvidenceModule`, the frontend's `reactioniq`). Do not renumber the enums — `AIEvidenceModule` values are persisted.

**Done when:** a review task, approval and share link can be created against a regulatory dossier and a reaction project; program order accepts `["spectracheck"]`.

### Layer 0.F — Anti-rot: the mechanism that keeps this true in six months
**Lane: both.** *Backend half landed — `tests/test_single_module_deployments.py`.*

- **DONE (backend)** — Single-module matrix: boots the app once per product and asserts (a) disabled products' routes return `module_not_licensed`, (b) no 5xx anywhere. Two tiers, because exhaustiveness costs ~2 minutes: a fast guard over the nine cross-product aggregation surfaces plus a served-routes floor (27s, every commit), and an exhaustive sweep of all ~163 parameterless GETs per configuration behind the existing `slow` marker (66s, sharded CI job).
- **Finding worth recording:** all three single-product configurations already return **zero 5xx** across every parameterless GET. The cross-module machinery — bridges, command centre, product registry, mobile aggregation — degrades cleanly when a sibling's data cannot exist. That reframes Layer 0.E: the missing collaboration primitives for Regentry/Repho are a *feature* gap, not a crash risk, so 0.E can be sequenced by commercial need rather than urgency.
- **The floor matters as much as the ceiling:** the sweep also asserts ≥100 routes still serve, so a map that accidentally claimed everything for one product could not pass by refusing everything.
- **ADD (frontend)** — the rendered nav contains no unlicensed entry, and no cross-module card mounts.
- **ADD** — Per-module smoke: the G1 activation path for each module runs green in single-module mode.
- **MODIFY** — Existing tests pin the three-module shape (`test_phase60_product_orchestration_api.py`, `test_phase64_tenant_saas_api.py`, `test_phase61_mobile_pwa_api.py`). Keep them as the all-modules variant; add single-module variants; change positional `modules[2]` lookups to key lookups. Re-baseline deliberately, with a comment.

**Done when:** CI fails if a new route is unclassified, if a nav item leaks, or if any single-module boot 5xxes.

---

## Wave 1 — SpectraCheck standalone: *"Analytical evidence, sold alone"*

**Buyer:** the Mnova/ACD-Labs replacement buyer — discovery chemistry labs, small biotechs, CROs running NMR characterization. **Job:** raw FID/MS in → processed, assigned, verified, quantitated, reviewed, e-signed evidence report out.

Coupling is already near-zero. The work is *completing the product*, not disentangling it.

**Phase 1.1 — Wire the headline capability (backend).**
- **ADD** — `POST /spectrum/qnmr/purity` (internal-standard and PULCON) and `POST /spectrum/qnmr/multiplet-ranking`. The engine is fully implemented in `moltrace/spectroscopy/qnmr/purity.py` with literature grounding and an auditable result — and is **unreachable from any endpoint**. The only qNMR surface today is dossier-gated. This is the single highest-value standalone gap: we advertise ±0.5% qNMR purity and ship no route to it.
- **MODIFY** — Promote `nmrglue` and `numpy` to core dependencies. Reading a vendor FID is not an optional feature of a spectroscopy product; today a base install cannot read a Bruker FID.
- **MODIFY** — Split qNMR *method metrology* (analytical target profile, validation parameters, uncertainty) from the *dossier readiness verdict*; make `dossier_id` nullable and add a session-scoped route reporting `q2_q14_readiness_status="not_assessed"`.
- **Done when:** a fresh account computes a qNMR purity result from an uploaded FID with no dossier, no compound and no sibling module.

**Phase 1.2 — Close the evidence chain (backend).**
- **MODIFY** — Add nullable `spectracheck_session_id` to `fid_runs`/`nmr2d_runs`. Today the FID path lands in `analyses`/`fid_runs` with **no FK to any SpectraCheck session**, so raw-FID evidence never enters the review → approve → release → sign chain.
- **ADD** — Promote a report to a controlled record so the Part 11 §11.70 content-bound signature works end to end (depends on Layer 0.E).
- **MODIFY** — Alias project/sample creation under the module prefix (`POST /spectracheck/projects`), so the module's surface is self-describing in the OpenAPI.
- **Done when:** a raw FID run appears as session evidence and its report carries a content-bound signature.

**Phase 1.3 — Make it deployable alone (backend).**
- **CRITICAL / MODIFY** — Generalise the raw-vault backend abstraction to managed files and artifacts. Today they are local-filesystem only and are **lost on Cloud Run instance recycle**.
- **REDESIGN** — Split `api.py` into per-module `APIRouter` modules using `nmr2d_routes.py` as the template; `create_app` becomes a composer that mounts only enabled modules. Do it mechanically, one prefix block at a time, with a route-count regression test.
- **REDESIGN** — Module-tagged table metadata so `init_db` can create a subset. The FK graph already permits it: no spectroscopy table points outward, so spectroscopy + platform is closed under FK.
- **MODIFY** — Gate the boot seeders on the enabled-module set; move the program-registry seeder out of the module that imports reaction code (it runs on every boot today).
- **MODIFY** — Default `rate_limit_enabled=True` and a non-zero body cap in production. A standalone SpectraCheck exposes multi-megabyte uploads and a per-call-expensive reasoning endpoint with abuse protections **off by default**.
- **Done when:** `create_app(modules={'spectracheck'})` yields a spectroscopy-only OpenAPI and a database with only spectroscopy + platform tables.

**Phase 1.4 — Honest capability + interop (backend, then docs).**
- **MODIFY** — Resolve the NMRNet integration point: it raises unconditionally, and the client module its own README tells you to configure **does not exist**. Either write it or state plainly that shift prediction is the HOSE/NMRShiftDB2 topological predictor.
- **ADD** — Ship the HOSE knowledge base as a deploy-time artifact (GCS + gcsfuse), honouring the CC-BY-SA never-commit rule. Today shift prediction runs on a tiny hand-curated seed table.
- **ADD** — **G7 export**: lossless JCAMP-DX and nmrML from the browser tier. This is rule 4 and a headline differentiator against both incumbents.
- **ADD** — Ingestion-breadth test matrix across Bruker/Varian/JEOL fixtures. One unreadable dataset in a first meeting ends the deal.
- **Done when:** a customer round-trips a spectrum out to nmrML and back with no loss, and the capability readout states exactly which predictor answered.

**Phase 1.5 — Cross-module degradation (frontend).**
- **MODIFY** — Regulatory Impact card → **hide** when `regulatory_hub` unlicensed. (Also fix its filter: it requests a `spectracheck_session_id` query param the route does not declare, so it silently lists every bridge in scope.)
- **MODIFY** — Linked-compound card → **degrade** to a free-text sample/compound label. The evidence chain only ever needs a SMILES string, never a `compound_entities` row.
- **MODIFY** — `/review` and `/reports` are 100% SpectraCheck but sit in the generic Workspace/Knowledge nav groups. Tag them `spectracheck` — otherwise a Regentry-only buyer gets two permanently empty top-level nav items.
- **Done when:** the SpectraCheck workspace renders with zero cross-module requests in single-module mode.

**Phase 1.6 — Qualify it alone (docs-GTM).**
- **MODIFY** — Re-base the blocking gold set on **all-public** data (NMRShiftDB2 + HMDB + BMRB/2DNMRGym), with the 20 in-house spectra as an optional site-specific extension. A promotion gate an auditor cannot re-run is not a gate.
- **MODIFY** — Split the Phase-0 e2e smoke test: a standalone SpectraCheck e2e ending at the versioned output contract with 10× byte-identical determinism (the SKU's CI gate), plus a separate contract test against an in-repo Regulatory Hub fake. **Never let the standalone build depend on the real second module.**
- **ADD** — A shippable qNMR validation package using traceable CRMs, so the ±0.5% claim has evidence that travels with the SKU and can be re-run at a customer site as PQ. Today it is validated only against AIST SDBS data that cannot be redistributed.
- **MODIFY** — Datasheet: advertise the spec's **7** net-new rows, none of which need another module. Move "PAT bridge" and "closed-loop integration" into a clearly labelled *"with Repho"* column. The deck currently sells both inside the SpectraCheck-only tier.

---

## Wave 2 — Regentry standalone: *"Regulatory insight, sold alone"*

**Buyer:** regulatory affairs and CMC — the Lhasa point-tool buyer and the Veeva-adjacent account. The spec already states the intent: *"A chemist can upload a new synthetic impurity and get an ICH M7 classification in seconds, without building a full CTD submission."*

The calculators are genuinely standalone. The product around them is not.

**Phase 2.1 — Un-poison and scope the data (backend).** *(0.A covers the action-item bug and the write gates.)*
- **REDESIGN** — Add owner/tenant scoping to the four reference tables with a NULL "global" tier, and make rule-set resolution match *global OR caller-owned*. Publish the built-in ICH engines as the immutable global tier. Until this lands, one customer's rule set changes another's verdicts.
- **REDESIGN** — Dossier ownership is per-**user** with no team sharing, and system-key-created dossiers are invisible to every human non-admin. Add `organization_id` + a collaborator-role condition in the PDP; give integration writes an explicit owner. A regulatory-affairs *team* cannot currently collaborate on a dossier.
- **Done when:** two users in one organization share a dossier; a foreign rule set cannot alter your assessment.

**Phase 2.2 — Empty database must not mean empty product (backend).**
- **ADD** — A first-run seeder (idempotent console script or data migration): standard jurisdictions (FDA/EMA/PMDA/HC/MHRA/ICH), one "ICH deterministic engines" global rule set whose child rules mirror the code-resident Q3A/B, Q3C and CPCA tables carrying their content-hash version as provenance, and stub source documents per guideline (title/version/effective date/URL — no redistributed text). **No seeder exists anywhere today**, so the jurisdiction map 404s and Q&A returns `insufficient_sources` on a fresh install.
- **ADD** — `pypdf` to runtime dependencies. PDF source uploads currently produce **zero** citations — the only realistic format for official guidance registers hash-only. Also raise the 60k-char excerpt cap and the 8-chunk citation cap; a full ICH guideline exceeds both.
- **Done when:** a fresh tenant runs an impurity assessment, sees populated jurisdictions, and gets ≥1 citation from an uploaded guideline PDF.

**Phase 2.3 — Wire the four missing headline jobs (backend).**
Four jobs named in the module's own value proposition are **library-only with no HTTP route**: ICH Q6A specification building, ICH Q1A stability protocols, the FDA two-phase OOS investigation, and the ICH M4Q Module-3 narrative generator. The wired "CTD Module 3" route is a thin bundle assembler that stitches existing dossier children, not the rich generator.
- **ADD** — Four stateless POSTs following the `/regulatory/impurities/assess` pattern exactly: typed models, deterministic engine call, `rule_set_version` echo, verbatim disclaimer, `human_review_required=true`, one audit event. Contracts-first, then `schema.d.ts`, then frontend.
- **Done when:** each of the four returns a deterministic, citation-carrying result on an empty database.

**Phase 2.4 — Source-agnostic intake (backend, then frontend).**
The spec assumes impurity data arrives from SpectraCheck. A standalone Regentry needs its own front door.
- **ADD** — First-class impurity-profile intake: SMILES/structure paste, CSV/XLSX impurity table upload, HPLC/LC-MS area-percent import, LIMS/ELN mapping. Validate all through one schema so the engine and the CTD generator are source-agnostic, and record intake provenance in the Annex 22 record.
- **Done when:** a full impurity assessment → CTD Module 3 section runs from a pasted CSV with no analytical module licensed.

**Phase 2.5 — Degradation + surface (frontend).**
- **MODIFY** — Reaction-optimization handoff card (3 mounts) and CTD bundle sections sourced from spectroscopy reports → **inert "available with …"** or hidden.
- **MODIFY** — `POST /bridges/regulatory-to-reaction` 400s when Repho is absent. Mirror the spectroscopy→regulatory pattern, which correctly degrades to 201 with `bridge_status="blocked"` and a warning.
- **ADD** — A Regentry-native review queue and reports surface (depends on 0.E), since `/review` and `/reports` are SpectraCheck-only.
- **Done when:** the dossier workspace renders complete in single-module mode.

**Phase 2.6 — Qualify it alone (docs-GTM).**
- **MODIFY** — Re-base the **blocking** promotion gate on fully public evidence that ships with the product: ICH Q3A/B/Q3C/Q3D worked examples, ICH M7 Q&A, the FDA NDSRI database, EMA Nitrosamines Q&A, Hypothesis property invariants, and the formula→citation map. Demote the "50 historical anonymised CTD reports" comparison to a soft metric a customer supplies at PQ — no pre-customer SKU has that data.
- **ADD** — A standalone e2e: SMILES + daily dose in → Q3A/B + Q3C/Q3D + M7 class + CPCA category/AI limit + cumulative risk → report out, byte-identical across 10 runs, with no analytical input at all.
- **MODIFY** — State the dual-(Q)SAR composition explicitly: our expert-rule alert engine + a statistical model as the in-product pair, **plus optional connectors for customer-licensed Derek/Sarah**. Add domain-of-applicability output (Tanimoto < 0.4 → out-of-domain, mandatory expert review). Never imply substitution for a regulator-accepted model.
- **MODIFY** — Reword the "600+ docs in RAG" claim to corpus coverage the product can *index*, not content it redistributes. Ship the FDA public-domain corpus plus an ingestion tool the customer runs against official sources in their own tenant.

---

## Wave 3 — Repho standalone: *"Reaction outcome prediction & optimization, sold alone"*

**Buyer:** process chemistry, HTE, CDMO — competing with Schrödinger/Synthia, Atinary and ACD/Labs Katalyst D2D.

**The blocker was a stated position, not a technical one — and it is now overturned (Decision 2).** The build spec says: *"This integration is the architectural reason ReactionIQ cannot be sold standalone — it requires the Spectroscopy module to be operational."* That conflates two different loops:

- the **automated closed loop** (robot → spectroscopy verifies → optimizer designs the next plate, sub-30-min round trip) — genuinely requires SpectraCheck, and stays the bundle-only upsell;
- the **DMTA decision loop** (design → propose → record outcomes → analyze → propose next) — requires only outcome data, which can be typed, imported from CSV, or read from an HPLC/LC-MS export.

The code already supports the second: `outcome_json` is accepted directly on experiment create, `confirm-outcome` takes a reviewer-typed `confirmed_outcome_json` with no extraction run and no session, both SpectraCheck FKs are nullable, and both call sites early-return on `None`.

**This strengthens the moat rather than diluting it.** Standalone Repho becomes the land motion into process-chemistry and CDMO accounts that would never start with spectroscopy — and the loop becomes an upsell with a captive installed base to sell into. The mechanism is the provenance field itself: a standalone customer sees `provenance: customer-supplied` on every result they hand-enter, and the bundle turns that into `provenance: spectracheck-verified` with a latency number. The upgrade argument is *in the product*, measured, rather than asserted in a deck.

**Phase 3.1 — Declare and complete the bring-your-own-analytics path (backend, then docs).**
- **ADD** — A vendor-agnostic "verified result" adapter satisfying the same contract with `provenance="customer-supplied"`: manual/CSV/LIMS entry of yield, purity and conversion per well, plus HPLC/LC-MS result-file import.
- **ADD** — Make `provenance` a first-class, displayed, audited field on every outcome — not a metadata afterthought. It is simultaneously the honesty mechanism and the upgrade argument.
- **MODIFY** — Re-scope the standalone SKU as spec steps 1–14 with human-in-the-loop test/analyze; keep the sub-30-minute automated round trip as a **bundle-only** upsell.
- **MODIFY** — Amend the build spec's standalone claim at source, so the document and the product stop disagreeing.
- **Done when:** a campaign reaches a proposed next batch from CSV-entered outcomes with no analytical module, and every outcome record displays and audits its provenance.

**Phase 3.2 — Ship the optimizer we advertise (backend).**
- **MODIFY** — Promote `scikit-learn` to a core dependency (or a `bo` extra the Dockerfile installs). It is a ~10 MB wheel with no CUDA tail — utterly unlike torch — and it is the difference between shipping a GP surrogate and shipping a k-NN heuristic labelled "Gaussian process EI".
- **MODIFY** — Surface `fallback_reason` prominently in the model-diagnostics card, not buried in a diagnostics blob.
- **Done when:** a BO run reports a real surrogate `model_type`, and any fallback is visible in the UI.

**Phase 3.3 — Make it a team product (backend).**
- **ADD** — `organization_id` on `reaction_projects` plus an org-membership arm in the access predicate. **No reaction table has any org/team/tenant column**, so a five-chemist reaction-only customer must share one login. This is a hard commercial blocker with nothing to do with the other modules.
- **ADD** — ALCOA soft-delete / `reason_for_change` on reaction records, extending the existing controlled-records pattern. Today the honest answer to "how do I retire a mistaken experiment?" is "PATCH status to excluded, with no reason captured."
- **ADD** — A Repho-owned hash-chained audit + e-signature component (campaign, proposed batch, safety-gate decision + signer, result ingestion, model versions), so the SKU passes a Part 11 controls assessment without inheriting SpectraCheck's chain.
- **Done when:** two chemists in one org share a campaign, and a retired experiment carries a captured reason.

**Phase 3.4 — Module-local constraints (backend, then frontend).**
- **ADD** — A constraint editor plus a small embedded reference table (ICH M7 TTC 1.5 µg/day, Q3A/B thresholds, GSK/ACS GCI solvent greenness ranks — all factual published data) so BO constraints can be entered or defaulted without Regentry. Keep the Regentry contract as an optional **provider that overrides** local values, recording which provider was used in the campaign audit record either way.
- **Done when:** a regulation-aware optimization runs with locally-entered limits and the audit record names the constraint source.

**Phase 3.5 — Schema + degradation (backend/frontend).**
- **ADD** — A squashed reaction baseline migration. The 35 reaction core tables have **no creating migration** — only deltas — so a fresh reaction-only Postgres cannot be built by alembic at all.
- **MODIFY** — In the reaction-only baseline, keep the two SpectraCheck **columns** but omit the FK **constraints** (both are already nullable and both call sites early-return on `None`), so a reaction-only schema does not drag in seven SpectraCheck tables.
- **MODIFY** — Regulatory compliance/constraints panels → inert "available with Regentry"; PAT bridge card → hidden.
- **Done when:** `alembic upgrade reaction@head` builds a working reaction-only database.

**Phase 3.6 — Honest claims (docs-GTM).**
- **MODIFY** — Split the Tier-1 acceptance table into **standalone-core** rows (retrosynthesis, forward top-1/top-5, condition top-1, yield MAE/ECE on Buchwald-Hartwig, EDBO+ experiments-to-target, Pareto hypervolume, green metrics, plate export) and **bundle-only** rows (PAT round-trip, closed-loop SDL). Publish the standalone set as the SKU's qualifiable acceptance criteria.
- **MODIFY** — Publish two metric sets. The headline "4 hr iteration" and "15–25 experiments" are loop-derived. **Never quote loop numbers on a single-module datasheet.**
- **MODIFY** — Rewrite the process-safety acceptance row against a public citable hazard set (GHS + NFPA 704 + NIST WebBook). The current criterion names a copyrighted reference the spec's own prompt forbids encoding — and safety-flag recall is a *blocking* promotion metric, so its ground truth must be legally shippable.
- **MODIFY** — The promotion gate's gold set is 1 task with 8 simulated observations, and the benchmark directory does not exist. Either grow it to a real held-out set or downgrade the public claim from "benchmark promotion gate" to "promotion-gate scaffold". Do not sell "gated by a frozen benchmark" on 8 synthetic points.

---

## Wave 4 — Packaging, pricing, GTM

**Phase 4.1 — SKU matrix (docs-GTM).** Three standalone SKUs + two bundles, mapped onto the deck's existing tiers. The deck already sells "SpectraCheck only" at $50–100K as the entry tier and makes bottom-up SpectraCheck the Phase-1 motion — **standalone is already the stated GTM; the product is what has to catch up.** Reconcile the tension the deck carries: the financial model assumes "3 modules priced as platform" while the entry SKU is single-module. Add explicit standalone unit economics per module (list price, AI-compute overage basis, gross margin, expected attach rate).

**Phase 4.2 — Pricing model (docs-GTM).**
- Base environment fee + named seats, **per module, with pooling across modules** — Veeva's shape without Veeva's multiplication penalty, where one person touching three applications pays three times.
- A credit pool for genuinely variable-cost surfaces (propose-next cycles, warm-start fits, advisor calls, batch prediction) — Schrödinger's instrument, metered server-side with a live balance, **no licence daemon**.
- A free academic tier for SpectraCheck separated by organisation type, not by crippled features — the TopSpin playbook. Compliance floor in, validation package out. Renewable academic/government/non-profit licence, not an open-ended promise. **Gated on pooled infrastructure (Decision 3)** — until then, manually provision a handful of named labs.
- Published list prices for the self-serve tier; **"from $X"** for Regentry and Repho (Decision 4). Essentially nobody in this category publishes; only Mestrelab does, proving it can be done without harm. Lead the page with the regulated-workflow framing, never a feature list — Mnova's $940/yr is the anchor we are arguing against.
- Written commitments: no prerequisite licences, no per-model gating, no per-instrument or per-brand pricing, validation package included in every SKU.

**Phase 4.3 — Trial & upgrade surfaces (both lanes).** Seeded demo tenant per module, sample datasets, guided first run. Upgrade adds a module to `MOLTRACE_ENABLED_MODULES` and redeploys — **zero data migration**, because the schema and database are already shared; the customer's existing records simply become linkable. Expose it as an honest locked-module state plus a "request access" flow — never nagware. Then prove the claim: a migration-free upgrade rehearsal (spectracheck-only deployment → add `regulatory_hub` → existing sessions link to a new dossier) belongs in the CI matrix alongside 0.F.

**Phase 4.4 — Marketing surface (frontend/docs).** Three per-module product pages already exist, are canonical and sit in the sitemap at priority 0.9 — a real head start. But: the copy sells one integrated platform, the module cards are numbered "Module 01/02/03" with SpectraCheck badged "Start Here", Regentry's own thesis is that spectroscopy flows into it, and there is **no pricing page and no comparison page** — every module CTA funnels to the same generic demo request.
- **ADD** — `/pricing` with per-module anchors; per-module comparison pages (vs Mnova/ACD; vs Lhasa/Veeva; vs Schrödinger/Synthia/Atinary); module-scoped demo CTAs. Register each in both `next.config.mjs` MARKETING_PATHS **and** `app/sitemap.ts` or it will be uncached and unindexed.
- **MODIFY** — Give each module page its own `SoftwareApplication` JSON-LD node (`isPartOf` the platform) so a module can rank as its own product. Today one node covers everything.
- **MODIFY** — Demote cross-module sections to a labelled "Works better with" band rather than the value proposition.
- **ALREADY OK / KEEP** — All compliance framing stays **"designed to support"**. SOC 2 is not held.

---

## Sequencing

```
 Wave 0.A ──── 0.C ──┬── 0.D (frontend) ──┐
  (trust)   (profile │                    ├── 0.F (anti-rot CI)
             + gate) └── 0.E (carve-out) ─┘
                              │
      ┌───────────────────────┼───────────────────────┐
   Wave 1                  Wave 2                  Wave 3
 SpectraCheck             Regentry                  Repho
      └───────────────────────┼───────────────────────┘
                        Wave 4 (packaging / GTM)

Deferred to the pooled-tier program (Decision 3):
  0.B tenant binding → full entitlement resolution → shared-DB tenancy
  → free academic tier
```

**First two weeks — the demonstrable slice.** Layer 0.A (trust fixes, ~2 days), then Layer 0.C through the deployment profile + route→module gate + classification test, then Phase 1.1 (wire qNMR). Decision 3 takes tenant binding off this path, which is what makes the slice fit in two weeks.

That produces the first honest demo: *a SpectraCheck-only deployment that computes a qNMR purity result from a raw FID and is server-side denied from every regulatory and reaction route* — G1 and G3 satisfied, on real infrastructure, with a CI job proving it stays true.

**Session discipline:** backend and frontend lanes never share a session. Contracts-first — FastAPI routes and models, regenerate `moltrace_frontend/src/lib/api/schema.d.ts`, then frontend. Commit with an explicit pathspec.

---

## Decisions — made 2026-07-26

Guiding principle: **the moat is the loop structure *plus* the standalone architecture.** Each decision was taken so that standalone strengthens the loop rather than competing with it.

**1. Fail-closed, cut over in three steps.** Enforcement is default-deny — the only posture that makes G3 true, since a fail-open-with-a-flag system silently un-gates the moment a tenant is created without rows. But we ship the gate in **observe mode** first (compute + audit the decision, deny nothing), read the observations, run the backfill, then flip. Cheap, and it turns a risky cutover into a data-driven one.

**2. Overturn the "cannot be sold standalone" position — yes.** Repho ships standalone as spec steps 1–14 with bring-your-own-analytics; the automated closed loop stays bundle-only. The spec conflated the automated loop with the DMTA decision loop, and the code already supports the second. See Wave 3 for why this *strengthens* the moat: the standalone SKU is the land motion, and the `provenance` field makes the loop's value measurable from inside the product.

**3. Deployment shape — dedicated per customer for every paid SKU; pooled tenancy only for free/trial, and only later.**
- **Now:** one Cloud Run service + one database per customer. This is what the schema honestly supports (`tenant_id` on 19 of 263 tables and on **no** science, evidence or compliance table), and in regulated pharma it is a *selling point* — data residency, validated state, per-customer qualification scope. It also makes G6 nearly free: the qualification scope literally is the deployment.
- **Margin control:** a shared Cloud SQL *instance* with a database per customer for smaller accounts; a dedicated instance only at enterprise. Isolation stays at the database level, so no cross-customer rows ever share a table and the isolation claim stays true.
- **Consequence:** the SKU boundary is `MOLTRACE_ENABLED_MODULES`, not a database lookup — which removes tenant binding (0.B) from the critical path and is why the first slice is two weeks rather than six.
- **Later, as its own program:** `tenant_id` + row-level filters on the science/evidence/compliance tables, then pooled deployments, then the free academic tier. **Do not sell shared-database multi-tenancy until that lands** — we cannot substantiate the isolation claim today.

**4. Publish pricing — with a split.** List prices for the self-serve tier (SpectraCheck standalone, academic); **"from $X"** anchors for Regentry and Repho, where ACV genuinely varies with validation scope. Mestrelab proves publishing shortens cycles, but Mnova's $940/yr is a brutal anchor — so the pricing page must lead with the regulated-workflow framing (Part 11 floor, validation package included, no prerequisite licences), never a feature list.

**6. Repo structure — modular separation inside one codebase; no parallel "standalone" folder.** A forked tree would break the upgrade story that Decision 3 sells: "add a module, change configuration, migrate no data" only holds while standalone and connected are the same code on the same schema. It would also institutionalise a failure mode we already have in miniature — the duplicate `src/app` tree (78 mirrored pages) and four independent nav definitions, which the audit flagged precisely because *"doing entitlement work across two half-authoritative trees guarantees an ungated copy survives."* The isolation people want from a folder comes instead from per-module routers, module-tagged table metadata, and a `create_app(modules={...})` composer — enforced by the classification test and the single-module CI matrix, which fail loudly where a folder convention would fail silently. Target layout (extending the split `src/moltrace/spectroscopy` and `src/moltrace/regulatory` already begin):

```
src/moltrace/{spectroscopy,regulatory,reaction}/       engines
src/nmrcheck/
  api.py                                               → shrinks to the create_app composer
  routes/{spectroscopy,regulatory,reaction,platform}.py
  orm/{spectroscopy,regulatory,reaction,platform}.py
  module_access.py                                     route→module map + gate
```

Sequencing matters: the **gate** (0.C) makes a module sellable without moving a line of code; the **split** (Phase 1.3) makes the deployment lean afterwards. Sell first, refactor second.

**5. Free academic tier for SpectraCheck — yes, with two guardrails.** Separated by organisation type, not crippled features (the TopSpin playbook). Guardrails: (a) it runs on pooled infrastructure, so it lands *after* Decision 3's later program — until then run a manually provisioned program for a handful of named labs; (b) the compliance floor is included but the *validation package* is not, which is the honest line to draw and costs academics nothing. Scope the no-sunset commitment to "free for academic/government/non-profit on a renewable licence" — not "free forever for anyone who signs up".

---

*Grounded in nine parallel codebase audits (including live probes against a running instance), the three v2.2 build specs, the 2026 investor deck, and a fourteen-vendor competitive scan.*
