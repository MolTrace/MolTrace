# FE Handoff — Repho R1: Green Chemistry Metrics

**Backend status:** shipped behind the standard reaction PDP gate at backend
`>= v0.45.0` (this change). New tables + 6 endpoints + 3 new green optimization
objectives. **Math is frozen** (deterministic, no LLM). This is a frontend
work-list for the separate FE session — do it in `moltrace_frontend/`.

> Principle reminder: **integrate, don't clutter.** Fold green metrics into the
> existing `components/reaction-optimization/` surfaces (the program workspace,
> the condition matrix, recommendation cards, and the
> `reaction-regulatory-constraints-panel`). **No new top-level nav.**

---

## 1. Regenerate the typed contract FIRST

The backend OpenAPI is the binding contract. Before touching any FE code:

```bash
# backend running on :8000, then in moltrace_frontend/
npm run generate:openapi   # FastAPI /openapi.json -> src/lib/api/schema.d.ts
```

After regen, `schema.d.ts` will contain the new paths and the `ReactionGreen*`
component schemas. Type all calls off `paths[...]` / `components["schemas"]` — do
not hand-write types.

---

## 2. Contract delta (by name)

### New endpoints (all under the existing reaction PDP gate; same auth as cost/safety profile)

| Method | Path | Request model | Response model |
|---|---|---|---|
| POST | `/reaction-projects/{id}/green-profile` | `ReactionGreenProfileCreate` | `ReactionGreenProfile` (201) |
| GET | `/reaction-projects/{id}/green-profile` | — | `ReactionGreenProfile` (404 if none) |
| PATCH | `/reaction-projects/{id}/green-profile` | `ReactionGreenProfileUpdate` | `ReactionGreenProfile` (404 if none) |
| POST | `/reaction-projects/{id}/experiments/{experiment_id}/green-metrics` | `ReactionGreenMetricsRequest` | `ReactionGreenAssessment` (201; 404 if experiment missing) |
| GET | `/reaction-projects/{id}/experiments/{experiment_id}/green-metrics` | — | `ReactionGreenAssessment` (404 if no assessment) |
| POST | `/reaction-projects/{id}/green-compare` | `ReactionGreenCompareRequest` | `ReactionGreenCompareResult` (200) |

### New optimization objectives

`ReactionObjective` and `ReactionObjectiveProfileType` literals gained:
`minimize_e_factor`, `maximize_atom_economy`, `maximize_green_score`. These are
selectable in the **objective profile** (`POST …/objective-profile`) exactly like
`maximize_yield`, and feed the existing Bayesian-optimization run.

For **multi-objective** campaigns, green metrics participate only when you set a
weight in `objective-profile.weights_json` — any of `e_factor_weight`,
`atom_economy_weight`, `green_score_weight` (default `0.0`, so existing campaigns
are unchanged). The objective summary in BO diagnostics now echoes these weights.

### `ReactionOutcome` gained fields

`e_factor`, `atom_economy_percent`, `pmi`, `rme_percent`, `green_score` (all
optional; percent fields 0–100, ratios ≥ 0). These appear on experiment
`outcome_json` and can be set directly or auto-populated (see `persist_to_outcome`).

---

## 3. Request/response shapes

**`ReactionGreenMetricsRequest`** (compute green metrics for an experiment):
```jsonc
{
  "product_smiles": "CCO",        // optional; used (with RDKit) for atom economy
  "product_mw": null,             // optional alternative to product_smiles
  "product_mass_g": 100.0,        // required for E-factor/PMI/RME
  "components": [                  // materials going IN
    { "name": "acetaldehyde", "role": "reactant", "smiles": "CC=O", "equivalents": 1.0, "mass_g": 120.0 },
    { "name": "THF", "role": "solvent", "mass_g": 500.0 },
    { "name": "K2CO3", "role": "reagent", "mass_g": 50.0 }
  ],
  // role ∈ reactant | reagent | catalyst | solvent | workup | other
  "energy_intensity_kwh_per_kg": null,   // optional pass-through (not derived)
  "water_usage_l_per_kg": null,
  "hazardous_waste_kg_per_kg": null,
  "persist_to_outcome": false,    // if true, writes e_factor/atom_economy/pmi/rme/green_score
                                  // onto the experiment outcome (clamped to model bounds) for BO
  "metadata_json": {}
}
```

**`ReactionGreenAssessment`** response: `metrics_json` (the computed metrics —
keys: `e_factor`, `e_factor_simple`, `e_factor_complete`, `pmi`, `rme_percent`,
`atom_economy_percent`, `green_score`, …), `inputs_json`, `provenance_json`
(`formula_version`, `solvent_table_version`, `citations`, `definitions`),
`warnings` (human-readable strings for missing/unrecognized inputs), `notes`,
`human_review_required`.

**`ReactionGreenProfileCreate`**: `solvent_greenness_json` (per-project overrides —
solvent name → 0–100 greenness, or → `[S, H, E]` triple), `default_assumptions_json`,
`solvent_table_version` (default `"chem21-2016"`), `metadata_json`.

**`ReactionGreenCompareRequest`**: `{ "experiment_ids": [1, 2, 3] }` →
`ReactionGreenCompareResult` with `entries[]` (each `available` true/false +
`metrics_json`) and `best_by_metric_json` (per-metric winner; min for E-factor/PMI,
max for atom economy/RME/green_score).

---

## 4. Suggested UI work (fold into existing panels)

1. **Green panel** in the program workspace: render the latest
   `ReactionGreenAssessment.metrics_json` for the selected experiment (E-factor,
   PMI, atom economy, RME, solvent green-score) with the `provenance_json`
   citations in a tooltip and `warnings` surfaced inline.
2. **Condition matrix**: add a `green_score` (and/or E-factor) column when present
   on outcomes; color via the same accent tokens.
3. **Objective selector**: add the 3 green objectives to the objective-profile
   editor; for multi-objective, expose the three optional green weight sliders.
4. **Recommendation cards**: show `green_score` alongside predicted yield when the
   outcome carries it.
5. **Regulatory constraints panel**: green metrics are a scale-up/regulatory
   deliverable — surface them where the dossier handoff lives.

Reuse Recharts/Plotly already in the layer; no new charting deps.

---

## 5. Verify (FE session)

- `npm run test` (vitest/jsdom) for any new component; mock `apiFetch`.
- Live-curl the backend on :8000 to confirm the contract end-to-end (sign up →
  create project → create experiment → POST green-metrics → GET green-metrics →
  green-compare).
- Confirm `schema.d.ts` types resolve with no `any` casts at the call sites.

---

## 6. Notes / gotchas

- **Solvent names** are matched case-insensitively against the built-in CHEM21
  table (+ common aliases: `MeCN`, `EtOAc`, `IPA`, `DCM`, `2-MeTHF`, …). Unknown
  solvents are excluded from `green_score` and produce a `warnings` entry — show it.
- **Atom economy** needs RDKit-parseable SMILES (or an explicit `product_mw`);
  if absent, the metric is omitted with a warning (not an error).
- A green assessment is **append-only** per experiment; GET returns the latest.
- The `/reaction-experiments/{id}` GET (top-level) already returns the updated
  `outcome_json` after a `persist_to_outcome` compute.
