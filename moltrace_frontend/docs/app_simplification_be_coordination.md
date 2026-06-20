# App Simplification — backend-coordination handoff

The 8-phase **App Simplification** program is complete on the frontend (see
`app_simplification_plan.md` + `app_simplification_audit.md`). Four items remain
that the FE **cannot** finish alone: each needs a backend contract decision or a
new list endpoint first. This doc states, per item: the exact FE location, the
current behavior, the **question for the backend**, and **what the FE will do**
once the backend answers. (FE = `moltrace_frontend/`, owned by the FE session;
nothing here edits the backend — it's the brief to hand the BE session.)

---

## 1. Server-owned hash inputs (Phase 4 — deferred)

Three forms ask the user to **type a hash the server arguably owns**. All are
optional today (omitted from the body when blank), so they don't currently
break anything — but typing a SHA-256 by hand is exactly the "backend
surfacing" P4 targets.

| Form | FE file:line | Field sent |
|---|---|---|
| Controlled-record create / new-version / lock | `components/validation/controlled-records-workspace.tsx` — inputs ~443 / ~533 / ~563; body `optionalHash(...)` at 232 / 267 / 307 | `content_hash` |
| SpectraCheck confidence "compose" form | `components/spectracheck/spectracheck-confidence-suite.tsx` — input ~2166; queue hashes already flow as `queue_raw_data_sha256` (~963) | `raw_data_sha256` |
| Dossier qNMR / method-validation | `components/regulatory-hub/regulatory-dossier-workspace.tsx` — input ~4208; body `if (mvSourceHash.trim()) metadataQnmr.source_hash = …` (1627) | `metadata_json.source_hash` |

**Question for backend:** for each endpoint, does the server **compute the
digest from the uploaded/linked content** (and ignore/overwrite a client value),
or does it **rely on the client** to supply it (e.g. for ALCOA integrity of
externally-held content)?

**FE follow-up:**
- *Server computes it* → FE removes the manual input and shows the
  server-returned hash read-only (display, not input).
- *Client must supply it* → keep as-is; it's a legitimate integrity affordance,
  not backend-surfacing. (Optionally add a "compute from file" helper later.)

---

## 2. validation-project `steps_json` → array-of-steps editor (Phase 7 — bespoke)

`components/validation/validation-project-detail-workspace.tsx` (~883–932) posts
`steps_json` (an **array of step objects**) plus FK-id arrays
`linked_requirement_ids_json`, `linked_risk_ids_json`, `evidence_file_ids_json`,
`evidence_artifact_ids_json`. The structured `JsonObjectField` built in Phase 7
handles flat objects, **not arrays of objects**, so this needs a bespoke editor.

**Question for backend:** (a) confirm the **shape of one step object** (which
fields, types, which required); (b) do owner-scoped **list endpoints** exist for
requirements, risks, evidence files, and evidence artifacts (to drive
`MultiEntityPicker`s for the id arrays)?

**FE follow-up:** build a repeatable step-row editor (add/remove/reorder step
objects) + `MultiEntityPicker`s for the four id arrays; keep the assembled JSON
byte-equivalent.

---

## 3. dossier AI-governance create — id-lists + objects (Phase 3/7 — bespoke)

`components/regulatory-hub/regulatory-dossier-workspace.tsx` (~4590–4622) posts
`evidence_item_ids_json` and `validation_record_ids_json` as **comma/newline
integer lists** (`parseCommaSeparatedInts`, 1774/1777) plus
`explainability_summary_json` / notes objects.

**Question for backend:** are there **owner-scoped list endpoints** for
**evidence items** and **validation records** the FE can query to populate
`MultiEntityPicker`s? (If not, this is a backend-gap — see item 4.)

**FE follow-up:** id-lists → `MultiEntityPicker` (named chips); objects →
`JsonObjectField`. Same request body.

---

## 4. Backend-gap pickers — missing list endpoints (Phase 3 — `MOVE_TO_API`)

Several raw integer-ID inputs can't become `EntityPicker`s because **no list
endpoint exists** to enumerate the options (recorded in the audit's
"Backend-gap raw-IDs" section). Known gaps:

- knowledge **extraction-run / record / source / target** ids
- tenant **data-integrity** and **inspection-package** id-arrays
- type-scoped **target / resource** ids (vary by selected type)

**Question for backend:** can owner/tenant-scoped **GET list endpoints** be added
for these entities (id + human label, paginated)?

**FE follow-up:** add a loader in `lib/ui/entity-options.ts` per entity and swap
each raw integer `<Input>` for an `EntityPicker` (the Phase 3 pattern).

---

### Notes for whoever picks this up
- Contracts-first: update FastAPI routes/models and regenerate
  `moltrace_frontend/src/lib/api/schema.d.ts` **before** the FE swaps the control.
- Every FE change here stays display/contract-preserving — the goal is to stop
  surfacing raw IDs/hashes/JSON, never to change what's sent on the wire.
- Preserve the "supports … not compliant-for-you" 21 CFR Part 11 framing on the
  controlled-records / hash surfaces.
