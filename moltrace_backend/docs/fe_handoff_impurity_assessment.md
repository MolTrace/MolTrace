# FE Handoff — Impurity Assessment endpoint + UI (v0.23.1)

**From:** backend session · **To:** frontend session · **Scope:** one new
authenticated route, `POST /regulatory/impurities/assess`, that exposes the
Regulatory Hub's five deterministic impurity engines (ICH Q3A/B, Q3C, Q3D, M7,
FDA CPCA) + nitrosamine cumulative risk as **one unified report**. Additive — no
existing route changed. Includes the **single-panel UI redesign spec** (§5).

Work in `moltrace_frontend/` only. Do **not** edit `moltrace_backend/`.

> **Design intent:** this is deliberately **one endpoint → one panel**, not five
> screens. It lands as a subsection of the existing **Regulatory Hub** product
> (path `/regulatory/...`). **No new top-level nav.**

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
- `POST /regulatory/impurities/assess`

**New component schemas**
- Request: `ImpurityAssessRequest`, `ImpuritySolventInput`, `ImpurityElementInput`,
  `ImpurityStructuralInput`
- Response: `ImpurityAssessResult`, `ImpurityThresholdsOut`, `ImpuritySolventOut`,
  `ImpurityElementOut`, `ImpurityStructuralOut`, `ImpurityCPCAOut`,
  `ImpurityCumulativeRiskOut`

## 3. Auth

Standard authenticated route (`require_access_context`) — same credential as the
other `/spectrum/*` and `/regulatory/*` calls (system `x-api-key` or a user Bearer
token). Unauthenticated → `401`. Non-positive `daily_dose_g` → `422`.

## 4. Request / response shapes

### Request — `ImpurityAssessRequest`

Only `daily_dose_g` is required; every impurity list is optional (an empty request
still returns the Q3A/B thresholds for the dose).

```jsonc
{
  "daily_dose_g": 1.0,                       // > 0, ≤ 100 (g/day)
  "route": "oral",                           // "oral" | "parenteral" | "inhalation" | "cutaneous"
  "substance_type": "drug_substance",        // "drug_substance" | "drug_product"
  "duration_months": 120,                    // M7 staged-TTC band; default 120 (>1–10 yr)
  "residual_solvents": [                      // ICH Q3C
    { "identifier": "methanol", "measured_ppm": 2000.0 }  // identifier = name | CAS | SMILES
  ],
  "elemental_impurities": [                   // ICH Q3D
    { "element": "Pb", "measured_ppm": 0.3 }  // element = symbol | name
  ],
  "structural_impurities": [                  // ICH M7 (+ CPCA if nitrosamine)
    {
      "smiles": "CN(C)N=O",
      "name": "NDMA",
      "measured_ng_per_day": 50.0,           // feeds nitrosamine cumulative risk
      "in_silico_expert": null,              // "positive" | "negative" | null (M7 (Q)SAR)
      "in_silico_statistical": null,
      "experimental_ames": null,
      "experimental_carcinogen": null
    }
  ]
}
```

### Response — `ImpurityAssessResult`

```jsonc
{
  "daily_dose_g": 1.0, "route": "oral", "substance_type": "drug_substance", "duration_months": 120,

  "thresholds": {                            // ICH Q3A/B — always present
    "substance_type": "drug_substance",
    "reporting_percent": 0.05,
    "identification_percent": 0.10,
    "qualification_percent": 0.10,
    "regulatory_basis": "ICH Q3A(R2): Impurities in New Drug Substances",
    "table_reference": "ICH Q3A(R2) Attachment 1"
  },

  "residual_solvents": [{                     // ICH Q3C — one per input
    "identifier": "methanol", "matched": true, "solvent_name": "Methanol",
    "class_number": 2, "pde_mg_per_day": 30.0, "concentration_limit_ppm": 3000.0,
    "measured_ppm": 2000.0, "permitted_ppm": 30000.0,   // Option 2, dose-scaled
    "passed": true, "margin_ppm": 28000.0,
    "regulatory_basis": "ICH Q3C(R8): Impurities: Guideline for Residual Solvents"
  }],
  // matched:false ⇒ unknown solvent (render as "not in encoded subset", NOT a fail).

  "elemental_impurities": [{                  // ICH Q3D — one per input
    "element": "Pb", "element_class": "1", "route_data_available": true,
    "pde_ug_per_day": 5.0, "permitted_concentration_ppm": 5.0,
    "control_threshold_ppm": 1.5, "measured_ppm": 0.3, "passed": true,
    "regulatory_basis": "ICH Q3D(R2): Guideline for Elemental Impurities"
  }],
  // route_data_available:false ⇒ cutaneous PDE not encoded (limits null) — show a note.

  "structural_impurities": [{                 // ICH M7 (+ CPCA) — one per input
    "smiles": "CN(C)N=O", "name": "NDMA",
    "m7_class": 2, "m7_ttc_ug_per_day": null, "coc_flag": true,
    "expert_review_required": true,
    "regulatory_action_required": "Compound-specific acceptable intake (AI) required; …",
    "cpca": {                                 // present ONLY when a nitrosamine
      "category": 1, "ai_limit_ng_per_day": 26.5, "potency_score": 1,
      "coc_flag": true, "measured_ng_per_day": 50.0, "within_ai_limit": false,
      "regulatory_basis": "FDA Nitrosamine Guidance Rev 2 …"
    },
    "regulatory_basis": "ICH M7(R2): …"
  }],

  "nitrosamine_cumulative_risk": {            // present iff ≥1 nitrosamine with measured_ng_per_day
    "total_risk_ratio": 1.887, "passes": false, "n_components": 1   // must be < 1
  },

  "rule_set_versions": { "q3ab": "sha256:…", "q3c": "sha256:…", "q3d": "sha256:…",
                         "m7": "sha256:…", "cpca": "sha256:…" },   // show in an "evidence/audit" affordance

  "disclaimer": "Decision-support only, NOT a regulatory determination. …",
  "human_review_required": true,             // ALWAYS true — see §5
  "warnings": []                             // per-impurity issues (unknown element, bad SMILES, …)
}
```

**Graceful degradation (important for UI):** the endpoint **never 500s on a bad
impurity**. An unknown element, an invalid SMILES, or residual solvents on the
cutaneous route are reported in `warnings` and the offending item is omitted from
its list (an unknown *solvent* is still returned with `matched:false`). Render
`warnings` as inline non-blocking notices, not errors.

## 5. UI redesign spec — one "Impurity Assessment" panel (no clutter)

Goal: surface all five engines through **one input form → one tabbed report**, as a
subsection of the **Regulatory Hub**. Do **not** add five nav items.

**Input (one card):**
- Daily dose (g/day), route (segmented control: oral / parenteral / inhalation /
  cutaneous), substance type (drug substance / drug product), treatment duration
  (months, with a helper showing the M7 band).
- Three optional repeatable rows: **Residual solvents** (name/CAS/SMILES + ppm),
  **Elemental impurities** (element + ppm), **Structural impurities** (SMILES +
  name; advanced disclosure for the four M7 (Q)SAR/experimental calls + ng/day).
- One **Assess** button → single POST.

**Report (one panel, tabbed or stacked sections, only render sections with data):**
1. **Thresholds** (Q3A/B) — always shown; reporting / identification / qualification %.
2. **Residual solvents** (Q3C) — table: solvent, class, permitted ppm, measured,
   pass/fail chip, margin. `matched:false` → muted "unknown — verify against Q3C".
3. **Elemental impurities** (Q3D) — table: element, class, permitted ppm, control
   threshold, measured, pass/fail. `route_data_available:false` → "cutaneous PDE not encoded".
4. **Structural impurities** (M7) — per row: M7 class badge (1–5), TTC, CoC flag,
   recommended action. If `cpca` present, an inline **Nitrosamine (CPCA)** block:
   category 1–5, AI limit (ng/day), within-limit chip.
5. **Nitrosamine cumulative risk** — the ratio with a hard **< 1** gate indicator.

**Cross-cutting (non-negotiable):**
- Surface `disclaimer` prominently (a persistent banner on the report) and render a
  **"Requires qualified sign-off"** state driven by `human_review_required` (always
  true) — e.g. a review/acknowledge affordance before any export.
- Pass/fail chips: `passed:true` → ok; `false` → warn; `null` → neutral "not measured".
- Expose `rule_set_versions` + each row's `regulatory_basis` in an "audit/evidence"
  popover (traceability is a selling point).
- `warnings[]` → inline notices, never blocking.

## 6. Verify

```bash
cd moltrace_frontend
pnpm generate:openapi          # schema.d.ts now types ImpurityAssessRequest/Result
pnpm test                      # if you add a component/contract test
pnpm dev                       # exercise the panel against a local backend (:3000 → :8000)
```

Backend contract is locked + tested (`tests/test_regulatory_impurities_assess_api.py`,
10 tests green) and the path + schemas are in `/openapi.json`.

---

## Addendum — Phase 2b contract delta (v0.23.3): product dose on the dossier

The **dossier** is now where the product's daily dose lives, so all of its impurity
assessments are dose-consistent. **Additive + backward-compatible** (nullable) — regenerate
`schema.d.ts` and surface the two new dossier fields.

- **`RegulatoryDossier` / `RegulatoryDossierCreate` / `RegulatoryDossierUpdate`** gain:
  - **`max_daily_dose_g`** *(optional, `0 < x ≤ 100`, g/day)* — the product max daily dose.
  - **`substance_type`** *(optional, `"drug_substance" | "drug_product"`)*.
  Add both to the dossier create/edit form (a "Product dosing" group). They drive every
  impurity assessment under the dossier.
- **`POST …/{id}/impurity-risk-register`** — when no tenant rule matches, the
  `threshold_triggered` band (reporting / identification / qualification) is computed from
  the **ICH Q3A/B** engine using the dossier's dose + substance type (no per-call input
  needed). `ImpurityRiskRegisterCreate.daily_dose_g` stays as an optional **override**.
- **`POST …/{id}/residual-solvent-assessment`** — when the dossier has a dose, the Q3C
  engine default uses the **dose-scaled Option-2** limit; the match's `limit_basis` says
  which option was used.
- **`metadata_json.m7`** *(on the impurity-register response record)* — a SMILES
  `structural_assignment` adds `{ m7_class, ttc_ug_per_day, coc_flag, expert_review_required,
  regulatory_basis, rule_set_version }`. Surface it as an "ICH M7 class" badge if useful.

Omitting the dossier dose reproduces the prior dose-unaware behaviour exactly.
