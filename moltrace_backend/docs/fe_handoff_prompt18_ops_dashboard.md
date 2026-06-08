# FE Handoff — Prompt 18 Ops Dashboard endpoints (v0.21.1)

**From:** backend session · **To:** frontend session · **Scope:** two new
read-only, **admin-gated** GET routes that surface the Prompt 18 MLOps layer
(release-control posture + model lineage) for the dashboard. Additive — no
existing route changed.

Work in `moltrace_frontend/` only. Do **not** edit `moltrace_backend/`.

---

## 1. Regenerate the typed schema (binding contract — do this first)

The contract is `GET /openapi.json` on the backend. Regenerate `schema.d.ts` from it:

```bash
# Terminal A — serve the backend OpenAPI on :8000 (the regenerate script targets it)
cd moltrace_backend
uv run uvicorn 'nmrcheck.api:create_app' --factory --port 8000

# Terminal B — regenerate the typed schema into the FE
cd moltrace_frontend
pnpm generate:openapi
#   → runs: openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.d.ts
```

Commit the regenerated `moltrace_frontend/src/lib/api/schema.d.ts` with your FE work.

## 2. Contract delta (what the regenerate adds)

**New paths**
- `GET /admin/ops/deployment-gate`
- `GET /admin/ops/model-lineage`

**New component schemas**
- `OpsDeploymentGateStatus`, `OpsDeploymentGateCheck`
- `OpsModelLineageResponse`, `OpsModelLineageRow`

## 3. Auth

Both routes are **admin-only** (`require_admin`). Send the admin credential the
other `/admin/*` calls use (system `x-api-key`, or an admin user Bearer token).
Unauthenticated → `401`; non-admin → `403`. Gate the dashboard route accordingly.

## 4. Request / response shapes

### `GET /admin/ops/deployment-gate` → `OpsDeploymentGateStatus`

No params. Computed live (no model artifacts required).

```jsonc
{
  "fails_closed": true,                 // invariant — render as the headline guarantee
  "self_check_passed": true,            // gate machinery verified fail-closed this request
  "self_check_failures": [],            // string[] — non-empty only if the gate logic regressed
  "checks": [                           // the four-check release policy
    { "name": "dominance",    "description": "Prompt 17 dominance gate — no regression on safety-critical metrics" },
    { "name": "audit_chain",  "description": "Prompt 12 audit chain verifies — provenance intact" },
    { "name": "tests_green",  "description": "the functional + unit test suite is green" },
    { "name": "data_leakage", "description": "data-leakage check — the candidate never trained on the gold set" }
  ],
  "output_contract_schema_version": "1.0.0",
  "monitoring_thresholds": {            // dict<string, number> — for the drift-config panel
    "psi_warn": 0.1, "psi_breach": 0.25,
    "override_trend_warn": 0.05, "override_trend_breach": 0.1,
    "confidence_trend_warn": 0.05, "confidence_trend_breach": 0.1,
    "slo_p50_ms": 800.0, "slo_p95_ms": 2000.0
  },
  "data_mode": "live",
  "generated_at": "2026-06-08T12:00:00Z"
}
```

### `GET /admin/ops/model-lineage` → `OpsModelLineageResponse`

No params. Reads the model registry; **empty until a registry is wired + a model
is promoted** (current state on all deployments).

```jsonc
{
  "rows": [                             // OpsModelLineageRow[] — empty for now
    {
      "model_id": "lora_adapter:13C:1.0.0",
      "role": "lora_adapter",
      "nucleus": "13C",                 // string | null
      "semantic_version": "1.0.0",
      "artifact_sha256": "sha256:…",
      "training_snapshot_hash": "sha256:…",
      "metric_vector": { "top1_accuracy": 0.91 },   // dict<string, number>
      "promoted_utc": "2026-06-08T…",   // string | null (ISO)
      "promotion_reason": "dominance gate passed",  // string | null
      "supersedes": null,               // string | null (prior production model_id)
      "drift_status": "unknown"         // "ok" | "warn" | "breach" | "unknown"
    }
  ],
  "registry_configured": false,         // false now → show the empty-state note
  "note": "No model registry is configured on this deployment yet; …",  // string | null
  "data_mode": "live",
  "generated_at": "2026-06-08T12:00:00Z"
}
```

## 5. UI guidance

- **Release-control panel** ← `deployment-gate`: headline "Fails closed ✓"
  (`fails_closed`), a green/red chip from `self_check_passed` (list
  `self_check_failures` if any), the four `checks` as the policy, and the
  `monitoring_thresholds` in a drift-config sub-panel.
- **Model-lineage table** ← `model-lineage`: one row per production model. When
  `registry_configured` is `false`, render the empty state using `note` (don't
  show a blank table). Map `drift_status` to a colour chip.

## 6. Verify

1. `schema.d.ts` includes the four new types; the FE typechecks against them.
2. With admin creds: `GET /admin/ops/deployment-gate` → `200`, `self_check_passed: true`.
3. With admin creds: `GET /admin/ops/model-lineage` → `200`, `registry_configured: false`, `rows: []`.
4. Without creds: both → `401`/`403`.

## 7. Not in scope yet (deferred backend prompt)

The **live drift panels** (input-PSI / confidence / override-rate / latency over
real production telemetry) need a training baseline + assembled telemetry that are
not yet plumbed into the API. The gate posture + lineage contract ship now; a
`GET /admin/ops/drift` endpoint will follow once those data sources are wired.
Design the dashboard so a drift panel can slot in later, but don't block on it.
