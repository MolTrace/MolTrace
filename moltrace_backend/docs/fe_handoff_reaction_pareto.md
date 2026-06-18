# FE Handoff — Repho R2: Multi-Objective Pareto Front + Hypervolume

**Backend status:** shipped (commit `12d5434`). A Bayesian-optimization run on a
**`multi_objective`** project now computes a true non-dominated (Pareto) front +
hypervolume and returns it inside the existing run **`diagnostics_json`** — **no new
endpoint, no new model, no schema change**. Math is frozen (pure NumPy; deterministic).
Do this in `moltrace_frontend/`.

> **No `npm run generate:openapi` needed.** The front rides inside
> `ReactionBayesianOptimizationRun.diagnostics_json` (already typed as a free-form object
> in `schema.d.ts`). Read it as `run.diagnostics_json.pareto_front`.

---

## 1. Where it is

Any run from `POST /reaction-projects/{id}/optimization/bo/run` (or `GET
…/optimization/bo/runs/{bo_run_id}`) whose objective profile is `multi_objective` and
has **≥2 weighted objectives** and **≥2 completed experiments carrying all of them**:

```jsonc
// run.diagnostics_json.pareto_front  (null otherwise)
{
  "objectives": ["yield", "selectivity", "impurity", "conversion"],
  "hypervolume": 1234567.0,
  "hypervolume_method": "exact_2d",          // or "monte_carlo" for >2 objectives
  "reference_point": [0,0,0,0],
  "pareto_size": 2,
  "evaluated_experiment_count": 5,
  "knee_experiment_id": 41,                  // best-balanced trade-off (may be null)
  "members": [
    {
      "experiment_id": 41,
      "experiment_code": "BO-4",
      "objectives": { "yield": 85, "selectivity": 85, "impurity": 3, "conversion": 95 },  // RAW values
      "non_dominated": true
    },
    // … one per evaluated experiment
  ],
  "note": "Non-dominated set over the weighted multi-objective dimensions … Advisory; requires human review."
}
```

Key points:
- `members[].objectives` are **raw** outcome values (impurity is the real impurity %, not
  inverted). The dominance/hypervolume math runs in maximize-space internally (impurity →
  `100 − impurity`, E-factor → a 0–100 score) but you display the raw values.
- `non_dominated: true` ⇒ the experiment is on the Pareto front.
- `knee_experiment_id` is the recommended balanced pick; highlight it.
- `pareto_front` is **`null`** for single-objective campaigns or when there isn't enough
  multi-objective data — render the existing scalar view in that case.

## 2. Suggested UI (fold into the existing reaction-optimization workspace)

1. **Pareto plot** — a 2-D scatter (Plotly, already in the layer) of two chosen objectives;
   plot all `members`, emphasize `non_dominated` points + connect them as the front, and
   ring the `knee_experiment_id`. Offer an objective-pair selector when `objectives.length > 2`
   (a 3-D Plotly scatter is fine for exactly 3).
2. **KPIs** — `hypervolume` (with a small "method: exact/monte-carlo" caption) and
   `pareto_size` as headline numbers; trend `hypervolume` across a project's BO runs to show
   convergence.
3. **Condition matrix** — add a "Pareto" badge column driven by `members[].non_dominated`.
4. Keep the advisory framing (`note`) visible; this is decision-support, human-reviewed.

## 3. Verify (FE session)
- `npm run test` (vitest/jsdom) for the new chart/badge components; mock `apiFetch`.
- Live-curl `:8000`: sign up → create `multi_objective` project → design-space + objective-profile
  → ≥2 completed experiments with yield/selectivity/impurity/conversion → run BO → confirm
  `diagnostics_json.pareto_front.members` + `non_dominated` flags render.

## 4. Notes
- The hypervolume reference is the maximize-space origin (0 per objective), so the indicator
  is comparable across runs of the **same** objective set; don't compare across different
  objective sets.
- Weighting green objectives (`e_factor_weight` / `atom_economy_weight` / `green_score_weight`
  in the objective profile, R1) automatically adds those dimensions to the front.
