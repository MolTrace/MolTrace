# FE handoff — Repho Phase C surfaces (yield predictions · route scores · forward checks · capability readout)

Backend has wired the Phase-C engines to HTTP. **Only the surfaces usable with no heavy dependency
are exposed** — the generative heavy paths (AiZynth route proposal, RXN/transformers forward
prediction, torch GNN training) are deliberately NOT wired; the capability readout tells the FE
which surfaces to hide. Work in `moltrace_frontend/` only.

## 0. Regenerate the contract first

```bash
cd moltrace_frontend
npm run generate:openapi
```

New in `schema.d.ts`: 11 routes and their co-located models (`ReactionYieldPredictionRequest/Run/Item`,
`ReactionRouteScoreRequest/Record`, `ReactionForwardCheckRequest/Record`,
`ReactionCapabilityReadout/Status`, `ReactionSdlSiteStatus`).

## 1. Capability readout — the surface-hiding signal

**`GET /reaction-capabilities`** (any authenticated user) →
`{ capabilities: [{name, enabled, available, active, missing_modules, reason, provenance, engine}], disclaimer }`.

Names: `forward_prediction`, `retrosynthesis`, `sdl_execution`, `yield_gnn` (sorted).

- Use `available` to decide whether a heavy-generation surface would even be possible on this
  deployment; today all heavy extras are absent, so treat this readout as "why the Generate
  buttons don't exist yet". **Do not** build UI that calls unwired generation endpoints.
- `yield_gnn.active` is `false` by design even when its flag is on (activation requires a
  benchmark-gate artifact, per call, never a standing state). Don't surface it as an error.
- Reasonable placement: a small "ML capabilities" info panel under the existing developer-mode
  gate (Phase-6 pattern), NOT a new top-level surface.

**`GET /reaction-sdl/status`** (any authenticated user) →
`{ enabled, capability, execution_surface_wired: false, detail, disclaimer }`.
`execution_surface_wired` is hard `false` — there are no SDL execution routes; show status only.

## 2. Yield predictions (R12) — Optimization tab

All owner-scoped (non-leaking 404), under `/reaction-projects/{id}`:

1. **`POST …/yield-predictions`** — body
   `{ conditions: [{...}, …] (1–200), require_verified?: bool=false, metadata_json?: {} }`.
   Fits the lightweight surrogate on the project's own completed experiments (those with a
   numeric `outcome_json.yield_percent`) and predicts each condition set. → `201`
   `{ id, backend, trained_n, require_verified, predictions: [{conditions, mean, std, backend,
   n_samples, warnings[]}], capability_provenance, created_at, metadata_json, disclaimer }`.
2. **`GET …/yield-predictions`** — list, newest first.
3. **`GET …/yield-predictions/{run_id}`** — one run; 404 if not this project's.

FE notes:
- **Always render `backend`** ("k-NN surrogate" / "GP surrogate") and the `std` as an uncertainty
  band — the honesty contract is that a user can see which model produced the number.
- `predictions[].warnings` lists conditions the model could not represent
  (`temperature_c=<missing>` etc.) — surface them; a warned prediction is *disclosed-degraded*,
  not clean.
- Errors: `400` with detail `"Cannot fit on zero examples."` when the project has no usable
  completed experiments (or none verified when `require_verified`) — show as guidance
  ("record completed experiments with yields first"), not a failure toast.
- Natural home: a "Predict yield" card on the Optimization tab beside the R10 warm-start card;
  prefill the conditions editor from the project's design-space variables (R3 pattern).

## 3. Route scores (R13) — a "Routes" panel

1. **`POST …/route-scores`** — body `{ route: {smiles, children[], reagents[], solvent?},
   label?: "", route_format?: "native"|"aizynth", metadata_json?: {} }`. → `201`
   `{ id, label, route, score, mermaid, human_review_required: true, created_at, metadata_json,
   disclaimer }`.
2. **`GET …/route-scores`** — list, newest first.
3. **`GET …/route-scores/{score_id}`**.

`score` shape: `{ route_score, score_components: {safety, brevity, atom_economy?,
solvent_greenness?}, safety: {worst_risk, screens[], requires_expert_review}, steps[],
step_count, max_depth, starting_materials, mean_atom_economy_percent, mean_solvent_greenness,
warnings[], human_review_required, disclaimer, engine }`.

FE notes:
- `mermaid` is a ready-to-render Mermaid `graph TD` string — the app already renders mermaid.
- Risk badge from `safety.worst_risk` using the R6 tier colors; `unknown` renders as
  *worse* than critical (unreviewable), never as neutral.
- `screens[]` includes `role: "molecule" | "reagent"` — reagent hits matter, show them.
- Errors: `400` for a malformed route tree (missing SMILES etc.) — inline validation message.
- **No route generation.** Do not add a "Propose routes" button; input is paste/build-a-tree.

## 4. Forward checks (R14) — near the safety panel

1. **`POST …/forward-checks`** — body `{ reactants_smiles[] (1–50), products_smiles[] (1–50),
   reagents_smiles?[], confidence?: number, conditions?: {}, source?: "external",
   label?: "", metadata_json?: {} }`. → `201` `{ id, label, reactants_smiles, reagents_smiles,
   result, human_review_required: true, created_at, metadata_json, disclaimer }`.
2. **`GET …/forward-checks`** — list. 3. **`GET …/forward-checks/{check_id}`**.

`result` shape: `{ products_smiles, confidence, conditions, source, safety: {overall_risk,
requires_expert_review, energetic_groups_found}, solvent_greenness, warnings[],
human_review_required, disclaimer, engine }`.

FE notes:
- Framing: "check a predicted/planned product before acting on it" — the value proposition is
  that model confidence is NOT a safety opinion; show `confidence` and the safety verdict
  side-by-side.
- `422` when `products_smiles` is empty (schema); `400` for engine-level refusals.

## 5. Verification

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/reaction-capabilities | jq '.capabilities[].name'
# then exercise one POST per surface against a seeded project and confirm the 201 bodies above
```

Backend tests: `tests/test_reaction_{capabilities,yield,retro,forward}_api.py` (28 tests) show
exact request/response pairs for every case including the 400/404/422 paths.

## 6. Constraints carried from the module docs

- Every surface is decision-support: keep `disclaimer` text verbatim where shown, always render
  `human_review_required` affordances (the R6/R8 pattern).
- Integrate into existing reaction-project tabs — no new top-level nav.
- Do not build UI for: SDL arming/execution, route proposal, forward generation, GNN training.
  They do not exist server-side; the capability readout is their honest face.
