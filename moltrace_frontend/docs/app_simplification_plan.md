# MolTrace — App Simplification & IA Reorganization (FE build plan)

**Owner:** frontend session (`moltrace_frontend/` only). No backend/contract changes — this is a
UI/IA program, not a feature program. If any phase needs a real contract change, stop and raise a
backend handoff first.

**Goal.** Make MolTrace feel like a product a pharma R&D scientist or QA/regulatory reviewer can use
without a tour — by (a) organizing navigation around *jobs*, not endpoints, and (b) removing the
"backend-surfacing" that makes screens read like an internal admin tool.

**Why now.** The app grew feature-by-feature. Symptoms: a whole Validation Center with no nav entry;
forms that mirror API request bodies (raw integer IDs, content hashes, JSON textareas); internal
enum vocabulary in dropdowns; "Developer JSON" tabs as first-class UI; status shown "as returned by
the API." Each is individually small; together they make the product feel unfinished.

---

## Quality bar (every phase is held to this)

Ultramodern, standard, and instantly understandable. A first-time user should never be confused or
need a tour. Use conventional SaaS patterns (no bespoke widgets where a standard one exists), generous
whitespace, one clear primary action per surface, and **concise microcopy** — cut long descriptions to
a short line; let structure and labels carry meaning. The three flagship modules — **SpectraCheck**,
**Regentry**, **Repho** — are first-class throughout and get the redesign treatment, not just the
compliance surfaces.

## Operating principles (the rules every phase enforces)

1. **Navigate by job-to-be-done, not by feature or endpoint.** Group destinations by what the user
   is trying to accomplish. Two audiences: people *doing the science* and people *governing it*.
2. **Never make a user type a machine value.** No raw IDs, foreign keys, hashes, or JSON. Use
   searchable object pickers; derive or default everything else.
3. **Server-authoritative for anything the user doesn't own.** Timestamps, hashes, who/when, content
   digests — display them, never collect them. (The e-signature signer-identity change is the model.)
4. **Speak the user's language, not the schema's.** "Reviewed by," not `signature_meaning: reviewed`.
   Friendly, color-coded status — never a raw enum string.
5. **Progressive disclosure + concise copy.** 5–7 primary destinations; everything else lives *inside*
   a section and appears when relevant. Cut verbose in-UI explanations to one short line; raw/power-user
   surfaces hide behind an explicit toggle, off by default.
6. **Some "features" are an endpoint with a form.** Fold them into the real workflow, or move them out
   of the human UI entirely (e.g. CI evidence ingest is a pipeline action, not a paste box).
7. **Modules are the product.** SpectraCheck, Regentry, Repho are named, top-level, and consistent with
   each other in layout, header, and interaction — the same skeleton, themed per module.

## How we run each phase (same loop as the handoffs)

`scope the surfaces → build → verify (tsc + eslint + vitest + live :8000 where relevant + a visual
where it changed) → commit FE-only with explicit pathspec → record memory → I suggest the next build.`

Guardrails: keep `schema.d.ts` untouched (no contract changes); preserve the "supports … not
compliant-for-you" compliance framing on regulated surfaces; no removed capability — only relocated,
derived, or demoted. Each phase ships independently and is revertible on its own.

---

## Phase 1 — Navigation & IA regroup

**Outcome.** The three flagship modules are named and front-and-center; every surface has a home; the
sidebar becomes job-based groups instead of a growing flat list.

**Problem with today's sidebar:** only *one* module is present — and mislabeled "Programs" (→ `/spectracheck`).
**Repho** (`/reactions`), **Regentry** (`/regulatory`), **Validation Center** (`/validation-center`) and
**e-Signatures** have **no nav entry at all** — they're URL-only.

**Shipped structure** (grouped, module-forward):
- **Modules** — SpectraCheck `/spectracheck`, Regentry `/regulatory`, Repho `/reactions` (each with a one-line descriptor)
- **Workspace** — Dashboard, Projects, Compounds & Batches, Action Queue, Review
- **Validation Center** — Overview `/validation-center`, Controlled Records, e-Signatures, System Releases
- **AI / ML** — AI / ML Governance `/ai`, Model Factory `/ml`
- **Knowledge & Analytics** — Knowledge Library `/knowledge`, Reports `/reports`, Automation ROI `/roi`
- **Team / Admin / Settings** — existing, gated

Each group gets a section eyebrow (full-opacity for AA); the brand mark links Home; precise
most-specific active-state; `aria-label`/`role="group"` for landmark + collapsed-icon names.

**Deferred to the Phase 2 audit (don't guess — likely keep-and-home vs remove/redirect):**
`/platform` (marketing surface; the in-app logo already links Home), `/validation` (legacy validation-
*runs* list — easily confused with Validation Center), `/batches` (today covered by Compounds & Batches
→ `/compounds`). The audit decides whether each is surfaced or retired.

**Steps**
1. Add the IA map to this doc (current routes → group) as the source of truth.
2. Refactor `components/app/app-sidebar.tsx` to render collapsible groups with section headers; keep
   icons; preserve active-state logic (incl. `adminPathActive`).
3. Add the missing entry points (Validation Center; Regulatory if absent) under the right group.
4. Optional: a small "command palette" (⌘K) already exists in the topbar — make sure the new
   destinations are searchable there too.

**Verify** — every route reachable from the nav; active highlight correct on nested routes; mobile
bottom-nav still coherent; vitest for the sidebar; visual check of the grouped sidebar.

**Done when** — no destination requires typing a URL; sidebar is groups, not a flat 10+ list.
**Next →** Phase 2 (audit), to plan the de-surfacing with the full picture.

---

## Phase 2 — Backend-surfacing audit (inventory)

**Outcome.** One ranked inventory that drives Phases 3–7. No UI change — this is the plan.

**Steps**
1. Sweep every workspace for plumbing leaks and tag each occurrence:
   `HIDE` · `DERIVE` · `REPLACE-WITH-PICKER` · `READ-ONLY` · `HUMANIZE` · `MOVE-TO-API` · `REMOVE`.
2. Categories to find: raw ID/FK text inputs; content-hash inputs; JSON textareas; internal enum
   dropdowns; "Developer JSON" / raw-payload tabs; "status as returned by API"; endpoint-shaped forms.
3. Rank by leak severity × surface traffic. Output a table (file · line · field · tag · note).
4. (This is a good multi-agent sweep — fan out one reader per workspace cluster.)

**Verify** — spot-check 10% of findings against the live UI; confirm each tag is actionable.
**Done when** — the audit table is committed and each later phase can be scoped from it.
**Next →** Phase 3 (entity pickers) — the highest-leverage `REPLACE-WITH-PICKER` items first.

---

## Phase 3 — Entity pickers (kill raw ID / foreign-key inputs)

**Outcome.** Users pick real objects (search by name/code), never type integer IDs.

**Steps**
1. Build a reusable `EntityPicker` (searchable combobox; takes a fetcher + render; returns the id).
2. Adopt it for the worst offenders from the audit: validation `target_id`/`resource_id`/
   `requirement_id`/`validation_project_id`; e-sign `target_type`+`target_id`; reaction `bo_run_id`;
   release `validation_project_id`.
3. Keep a "by ID (advanced)" fallback behind the dev toggle (Phase 6) for support.

**Verify** — picker resolves to the same id the old input sent; vitest for the component + one adopter
per cluster; live-smoke one create end-to-end.
**Done when** — no primary form asks for a bare integer/FK.
**Next →** Phase 4 (read-only server values) — the inputs next to those IDs that the server owns anyway.

---

## Phase 4 — Server-authoritative, read-only values

**Outcome.** The UI stops collecting things the server sets; it displays them instead.

**Steps**
1. From the audit `READ-ONLY`/`HIDE` items, remove inputs for content hashes, timestamps, who/when,
   and any server-derived field; render them as labeled read-only values (or drop entirely).
2. Strip these from request bodies (already started for e-sign signer identity; extend to controlled
   records, releases, validation children).
3. Confirm `extra="forbid"` fields are never sent.

**Verify** — create/edit still succeed with the slimmer bodies (live-smoke); tsc/eslint/vitest.
**Done when** — every form collects only user-authored intent.
**Next →** Phase 5 (vocabulary & status) — now that fields are fewer, make the remaining ones speak human.

---

## Phase 5 — Vocabulary & status humanization

**Outcome.** Internal enums become friendly labels; status becomes a consistent, color-coded badge.

**Steps**
1. Build a shared label/badge dictionary (`lib/ui/status.ts`): enum value → `{ label, tone }`, reusing
   the `--mt-*-ink` token rules so colored text stays AA in both themes.
2. Replace raw status strings ("status as returned by the API") and internal enum displays across
   validation / regulatory / reaction / ai surfaces.
3. Keep the raw value available on hover/title for traceability.

**Verify** — a snapshot/test of the dictionary; visual check across a few surfaces; contrast holds in
both themes.
**Done when** — no screen shows a bare enum token to a user.
**Next →** Phase 6 (developer mode) — corral whatever raw output remains.

---

## Phase 6 — Developer-mode gate

**Outcome.** Raw JSON and developer panels are opt-in, not first-class.

**Steps**
1. Add an app-level "Developer mode" toggle (per-user, persisted; default off).
2. Gate every "Developer JSON" tab / raw-payload panel / by-ID fallback behind it
   (reaction-project-detail, validation-project-detail, system-releases, etc.).
3. Hidden by default → primary UI gets quieter immediately.

**Verify** — toggle persists; gated panels absent by default, present when on; vitest for the gate.
**Done when** — a first-time user never sees a JSON blob in a primary flow.
**Next →** Phase 7 (endpoint-forms) — remove the surfaces that shouldn't be human-facing at all.

---

## Phase 7 — Fold endpoint-forms into workflows / move to API

**Outcome.** "A form for an endpoint" either becomes part of a real workflow or leaves the human UI.

**Steps**
1. From the audit `MOVE-TO-API`/`REMOVE` items: demote pipeline actions (e.g. CI evidence ingest)
   to documented API/CI integrations + a read-only status in the UI.
2. Merge thin CRUD pages into their parent workflow (create-in-context instead of a standalone form).
3. Document any endpoint intentionally left UI-less.

**Verify** — the workflow path still reaches the capability; nothing orphaned; live-smoke.
**Done when** — every remaining form maps to a human task, not an HTTP route.
**Next →** Phase 8 (polish).

---

## Phase 8 — Empty states, progressive disclosure, responsive & a11y

**Outcome.** The simplified app feels finished.

**Steps**
1. Real empty states for every list/section (what it is + the one action to start).
2. Collapse rarely-used controls under "Advanced"; lead with the common path.
3. Responsive + dark/light + keyboard/focus pass on the reorganized surfaces (reuse the ink-token
   contrast work).

**Verify** — vitest + a responsive/dark-mode visual sweep of the top surfaces.
**Done when** — top flows are clean on mobile and dark mode, with sensible empties.
**Next →** program complete; fold the net changes into the white papers + README (BE/docs session) and
re-baseline the GSD A/B fixture if any detector UI moved.

---

## Sequencing summary

```
1 Nav/IA  →  2 Audit  →  3 Pickers  →  4 Read-only  →  5 Vocabulary  →  6 Dev-mode  →  7 De-form  →  8 Polish
   (frame)    (plan)      (reuse)       (slim bodies)   (humanize)        (hide raw)     (remove)       (finish)
```

Phases 1, 5, 6, 8 are low-risk and shippable anytime. 3–4 and 7 touch request bodies — live-smoke each.
Start with Phase 1 (visible win, sets the structure); it makes the rest easier to scope.
