# FE Handoff — Dossier nitrosamine cumulative-risk rollup (v0.23.5)

**From:** backend session · **To:** frontend session · **Scope:** one new
authenticated read route, `GET /regulatory/dossiers/{id}/nitrosamine-cumulative-risk`,
that rolls a dossier's nitrosamine watches up into one FDA-Rev-2 cumulative-risk
verdict (`sum(measured / AI limit)` must be `< 1`), plus one **additive optional field**
(`measured_ng_per_day`) on the existing nitrosamine-watch create request. Additive — no
existing route changed, no migration.

Work in `moltrace_frontend/` only. Do **not** edit `moltrace_backend/`.

> **Design intent:** this folds into the existing **Regentry** dossier workspace
> as one **cumulative-risk summary card** beside the nitrosamine-watch list. **No new
> top-level nav.** It is the dossier-level companion to the per-call cumulative risk
> already surfaced by the Impurity Assessment panel (`POST /regulatory/impurities/assess`).

---

## 1. Regenerate the typed schema (binding contract — do this first)

```bash
# Terminal A — serve the backend OpenAPI on :8000
cd moltrace_backend
uv run uvicorn 'nmrcheck.api:create_app' --factory --port 8000

# Terminal B — regenerate the typed schema into the FE
cd moltrace_frontend
pnpm generate:openapi
#   → openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.d.ts
```

Commit the regenerated `moltrace_frontend/src/lib/api/schema.d.ts` with your FE work.

## 2. Contract delta (what the regenerate adds)

**New path**
- `GET /regulatory/dossiers/{dossier_id}/nitrosamine-cumulative-risk`

**Changed request schema (additive, optional)**
- `NitrosamineWatchRequest` gains `measured_ng_per_day?: number` (≥ 0) — the measured
  ng/day for that watch's structure. Existing create calls are unaffected.

**New response component schemas**
- `DossierNitrosamineCumulativeRisk` (the rollup)
- `DossierNitrosamineRiskComponent` (one included assessment)
- `DossierNitrosamineExcludedAssessment` (one excluded assessment + reason)

## 3. Auth

Standard authenticated route (`require_access_context`) — same credential as the other
`/regulatory/*` calls (system `x-api-key` or a user Bearer token). Unauthenticated →
`401`. Unknown `dossier_id` → `404`.

## 4. Request / response shapes

### 4a. Feeding the rollup — `POST /regulatory/dossiers/{id}/nitrosamine-watch`

A watch contributes to the cumulative sum only when it carries **both**:
1. a **parseable nitrosamine** `structure_text` (a SMILES the CPCA engine recognises, so
   an AI limit is derived), **and**
2. a `measured_ng_per_day`.

```jsonc
{
  "structure_text": "CN(C)N=O",     // NDMA — parses as a nitrosamine → CPCA Cat 1, AI 26.5 ng/day
  "measured_ng_per_day": 10.0,      // NEW optional field; ≥ 0
  "compound_id": 1,                 // existing optional fields unchanged
  "batch_id": 1
}
```

Watches with no `measured_ng_per_day`, or whose `structure_text` is free text / not a
nitrosamine, are still created — they are just listed under `excluded` in the rollup
(never silently dropped).

### 4b. The rollup — `GET /regulatory/dossiers/{id}/nitrosamine-cumulative-risk`

```jsonc
{
  "dossier_id": 12,
  "total_risk_ratio": 0.7547,       // sum(measured / AI limit) across included components
  "passes": true,                   // total_risk_ratio < 1.0  (FDA Nitrosamine Guidance Rev 2)
  "n_components": 2,
  "components": [
    {
      "assessment_id": 34,          // the nitrosamine-watch assessment row
      "structure_text": "CN(C)N=O",
      "category": 1,                // FDA CPCA potency category
      "ai_limit_ng_per_day": 26.5,
      "measured_ng_per_day": 10.0,
      "risk_ratio": 0.3774          // measured / ai_limit
    }
    // … one per included watch
  ],
  "excluded": [
    { "assessment_id": 40, "reason": "no measured ng/day recorded on this nitrosamine watch." },
    { "assessment_id": 41, "reason": "structure is not a parseable nitrosamine; no CPCA AI limit to score against." }
  ],
  "n_excluded": 2,
  "regulatory_basis": "FDA Nitrosamine Guidance …",
  "disclaimer": "… decision-support … not a regulatory determination.",
  "notes": [ "Cumulative risk = sum(measured / AI limit) …; must be < 1 (FDA …)." ],
  "human_review_required": true
}
```

**Empty / nothing-qualifying dossier:** `total_risk_ratio` = `0.0`, `passes` = `true`,
`n_components` = `0`, with a leading note: *"No nitrosamine watch on this dossier carries
both a CPCA AI limit and a measured ng/day; cumulative risk is 0 by default."* Render this
as a neutral "not yet assessed" state, **not** a green pass.

## 5. Suggested UI (Regentry → dossier → nitrosamine section)

- A **cumulative-risk card** above/beside the existing nitrosamine-watch list:
  - Headline verdict from `passes` + `total_risk_ratio` — e.g. **"Cumulative risk
    0.75 — within limit (< 1)"** (pass) vs **"1.51 — exceeds limit"** (fail). Treat the
    empty/zero-component case as a distinct muted "not yet assessed" state per §4b.
  - `n_components` included / `n_excluded` excluded as a small caption; expand to show the
    `excluded` reasons so reviewers see exactly what is **not** counted.
  - Per-component table from `components`: structure, CPCA `category`, `ai_limit_ng_per_day`,
    `measured_ng_per_day`, `risk_ratio`.
- Add `measured_ng_per_day` to the **nitrosamine-watch create form** so a watch can be
  entered with its measured level in one step.
- Always surface `disclaimer` / `human_review_required` — decision-support, not a
  determination (consistent with the Impurity Assessment panel).

## 6. Verification

- After regenerating, confirm `schema.d.ts` exposes
  `paths['/regulatory/dossiers/{dossier_id}/nitrosamine-cumulative-risk']['get']` and the
  `DossierNitrosamineCumulativeRisk` component.
- Backend behaviour is covered by
  `moltrace_backend/tests/test_regulatory_nitrosamine_cumulative_risk_api.py` (pass / fail /
  exclusions / empty / 404) — mirror those cases in the FE for the card's states.
