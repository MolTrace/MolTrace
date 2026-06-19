# FE Handoff — Repho R3: HTE/DoE Plate Designs

**Backend status:** shipped (`d0c2b94`, engine `443e927`). New table + 4 routes under the
reaction PDP/owner gate. Do this in `moltrace_frontend/`.

> Principle: **integrate, don't clutter** — fold into the existing
> `components/reaction-optimization/` workspace; no new top-level nav.

## 1. Regenerate the typed contract first
```bash
# backend on :8000, then in moltrace_frontend/
npm run generate:openapi   # picks up the new /plate-designs routes + ReactionPlateDesign* models
```

## 2. Endpoints (all owner-scoped + nested under the project)
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/reaction-projects/{id}/plate-designs` | `ReactionPlateDesignRequest` | `ReactionPlateDesign` (201) |
| GET | `/reaction-projects/{id}/plate-designs` | — | `ReactionPlateDesign[]` |
| GET | `/reaction-projects/{id}/plate-designs/{plate_design_id}` | — | `ReactionPlateDesign` (404 if not in project) |
| GET | `/reaction-projects/{id}/plate-designs/{plate_design_id}/export?target=csv\|json` | — | `{target, content}` (string) |

A non-owner gets a non-leaking **404** on all of these (owner/system/admin only).

## 3. Shapes
**`ReactionPlateDesignRequest`:**
```jsonc
{
  "plate_format": "96",            // "24" | "96" | "384"
  "strategy": "sobol",             // "sobol" | "lhs" | "factorial" | "bo_init" (15-25-well seed)
  "numeric_json": { "temperature_c": [40, 80] },   // name -> [low, high]
  "categorical_json": { "solvent": ["MeCN", "THF", "DMF"] },
  "boolean_json": ["inert_atmosphere"],
  "fixed_json": { "base": "K2CO3" },               // applied to every well
  "excluded_json": [ { "solvent": "DMF" } ],        // combinations to drop
  "seed": 20260615                                  // deterministic
}
```
**`ReactionPlateDesign`** (response): `id`, `plate_format`, `strategy`, `well_count`,
`design_json` (the plate: `wells: [{ well_id: "A1", conditions: {...} }]`, `dimensions`,
`capacity`, `provenance`), `warnings` (e.g. factorial truncation, unrecognized inputs),
`notes`, `human_review_required`.

## 4. Suggested UI
1. **Plate-map grid** — render `design_json.wells` as the physical 8×12 / 4×6 / 16×24 grid
   (well_id → cell); color cells by a chosen condition dimension; tooltip the full conditions.
2. **Design controls** — plate-format + strategy selectors; **prefill `numeric_json`/`categorical_json`/
   `boolean_json` from the project's design space** (the design-space panel already has the
   variables), plus fixed/excluded editors.
3. **Export buttons** — call `…/export?target=csv|json`, take the `content` string, and offer it
   as a file download (Blob). Mention these feed lab robotics (Mettler-Toledo/Chemspeed/Unchained
   are thin server-side adapters atop CSV/JSON — coming later).
4. Surface `warnings` (truncation/empty) and the advisory `notes`.

## 5. Verify (FE session)
- `npm run test` (vitest/jsdom) for the grid/controls; mock `apiFetch`.
- Live-curl `:8000`: sign up → create project → POST a `sobol` 96-well design → GET it → export csv/json.

## 6. Notes
- Designs are **deterministic** for a given request + `seed` (re-POSTing the same body reproduces the plate).
- `bo_init` caps at ~20 wells (the BO seed population); other strategies fill the plate.
- A plate links to a project; a later slice connects it to an execution batch (reuse the existing
  `/reaction-execution-batches` flow).
