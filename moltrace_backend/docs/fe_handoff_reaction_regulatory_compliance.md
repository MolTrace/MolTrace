# FE Handoff — Repho R4: Regulatory-Compliance Evaluation (closed-loop, read side)

**Backend status:** shipped (`fdd35b1`, engine `86b6f6e`). New owner-scoped GET endpoint. Do this
in `moltrace_frontend/`.

> What it does: evaluates a reaction project's **recorded experiment outcomes** against its
> **active injected regulatory constraints** (e.g. an ICH impurity limit) and reports which
> experiments breach a limit, with provenance back to the regulatory source. This is the
> enforced end of the Regentry→Repho loop. NOTE: the Bayesian optimizer predicts a scalarized
> score (not per-field outcomes), so this is evaluated against *real measured outcomes*, not at
> recommendation time — do not present it as "the optimizer filtered these."
>
> Principle: **integrate, don't clutter** — fold into the existing
> `components/reaction-optimization/` workspace (alongside the existing regulatory-constraints
> editor from Phase 7.4); no new top-level nav.

## 1. Regenerate the typed contract first
```bash
# backend on :8000, then in moltrace_frontend/
npm run generate:openapi   # picks up /regulatory-compliance + ReactionRegulatoryCompliance* models
```

## 2. Endpoint (owner-scoped, nested under the project)
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/reaction-projects/{id}/regulatory-compliance` | — | `ReactionRegulatoryComplianceReport` |

Non-owner → non-leaking **404** (owner/system/admin only).

## 3. Shape
**`ReactionRegulatoryComplianceReport`:**
```jsonc
{
  "reaction_project_id": 12,
  "enforced_constraint_count": 1,          // constraints with a numeric limit that were applied
  "active_constraint_ids": [5],
  "constraint_bases": ["ICH Q3B(R2) identification threshold"],
  "experiments_evaluated": 2,              // experiments that have a recorded outcome
  "non_compliant_experiment_count": 1,     // count with a hard (high/critical) violation
  "items": [
    {
      "experiment_id": 41, "experiment_code": "E-bad", "status": "completed",
      "feasible": false, "hard_block": true, "penalty": 1.0,
      "violations": [{
        "constraint_id": 5, "constraint_type": "impurity_limit",
        "objective_field": "impurity_percent", "comparator": "max",
        "predicted_value": 0.40, "limit_value": 0.15, "limit_unit": "percent",
        "basis": "ICH Q3B(R2) identification threshold", "severity": "high", "is_hard": true,
        "source_action_item_ids": [3]
      }],
      "unmeasured": []
    }
  ],
  "notes": []     // advisory messages, e.g. "no numeric limits active" / "no outcomes to evaluate"
}
```

## 4. Suggested UI
1. **Compliance summary card** — `experiments_evaluated`, `non_compliant_experiment_count` (red if
   > 0), `constraint_bases` as chips. Surface `notes` (especially the advisory "no numeric limits"
   case — see §5).
2. **Per-experiment table** — one row per `items[]`: experiment code + a status badge
   (`hard_block` → red "Non-compliant", a violation but `feasible` → amber "Flagged", else green
   "Within limits"). Expand to show each violation: `objective_field` `comparator` `limit_value`
   `limit_unit`, the measured `predicted_value`, the `basis`, and the `source_action_item_ids`
   (link back to the regulatory action item / dossier).
3. List `unmeasured` fields as "not measured for this experiment" (advisory — a limit existed but
   the outcome had no value for that field; never shown as passing).

## 5. How a constraint becomes enforceable (important)
A constraint is only enforced if its `constraint_json` carries a numeric `limit_value` (+ optional
`objective_field`/`comparator`/`limit_unit`/`limit_basis`; default field per `constraint_type`,
e.g. `impurity_limit` → `impurity_percent` / `max`). These numbers arrive two ways: (1) the
`/bridges/regulatory-to-reaction` bridge now **auto-derives** the ICH threshold from the dossier's
impurity action item into the constraint at creation, and (2) the existing **regulatory-constraints
structured editor** (Phase 7.4) lets a reviewer set/adjust them by hand — so the editor and this
compliance panel are two halves of one workflow. Bridge-created constraints are `draft` until
activated (status → `active` via the editor's PATCH), at which point they are enforced.

## 6. Verify (FE session)
- `npm run test` (vitest/jsdom) for the panel; mock `apiFetch`.
- Live-curl `:8000`: sign up → project → POST `/regulatory-constraints` with
  `constraint_json={limit_value:0.15, objective_field:"impurity_percent", comparator:"max"}`,
  `severity:"high"`, `status:"active"` → POST two experiments (impurity 0.05 and 0.40) →
  GET `/regulatory-compliance` → one row non-compliant with the violation + provenance.

## 7. Notes
- Only `active`/`reviewed` constraints with a numeric limit are enforced; `draft`/`archived` and
  limitless constraints are advisory (report says so in `notes`).
- `high`/`critical` severity → hard (non-compliant); `info`/`warning` → soft (flagged, penalised).
