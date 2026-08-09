# FE handoff — the AI/ML surface now shows computed numbers, not submitted ones

**Backend commits:** `c2b4214` (L0/C1+C3+C5, the seam) and `e7ec706` (L0/C2, registry link).
**Contract change:** additive. Nothing existing was removed or renamed, so today's frontend keeps
working unchanged — but three panels are now showing fields that used to be absent, and one is
showing a *refusal* it has never had to render.

## Why this matters for the interface

Until these commits the AI governance screens displayed values the caller had submitted. The
platform recorded that a model was calibrated; it could not calibrate one. A confidence of `0.82`
appeared whenever a request omitted one — the same shape, in the same field, as a measured number.

So the interface work here is not "surface new fields." It is: **stop presenting a recorded number
and a computed number identically.** Every item below exists to make that distinction visible.

---

## 1. Regenerate the contract first

```bash
cd moltrace_backend && uv run python -m uvicorn nmrcheck.main:app --host 127.0.0.1 --port 8000
```

```bash
cd moltrace_frontend && pnpm generate:openapi
```

The backend must be on `:8000` for the second command. Do not hand-edit
`src/lib/api/schema.d.ts` — it is generated.

## 2. Contract delta, by name

**`ModelArtifact`** — four new nullable fields:

| Field | Type | Meaning |
|---|---|---|
| `registry_model_id` | `string \| null` | The registry entry the inference router resolves. `null` = **not serving traffic**, whatever `status` says. |
| `registry_status` | `"candidate" \| "shadow" \| "production" \| "retired" \| null` | The registry's **live** status, not a copy. A superseded artifact reads `retired`. |
| `registry_role` | `string \| null` | e.g. `nmrnet_checkpoint`, `lora_adapter`, `hose_kb`. |
| `registry_nucleus` | `string \| null` | e.g. `13C`. `null` = serves every nucleus. |

**`RegistryPromotionRequest`** — new model. Required: `role`, `semantic_version`,
`dataset_snapshot_hash`, `dataset_row_count`. Optional: `nucleus`, `dataset_tag`,
`dataset_source`, `artifact_sha256` (64 hex chars), `confidence_band_ppm` (> 0).

**`DeploymentCandidateApprovalRequest`** — one new optional field:
`registry_promotion: RegistryPromotionRequest | null`.

**`PredictionResponse` / `PredictionRun`** — no schema change, but the *values* changed:
`confidence_score` is now `null` far more often, `uncertainty` carries a `scale` discriminator
(`"verifier_quality"` or `"dp4_posterior"`), and `metadata_json.provenance` carries
`{engine, model_versions}` when an engine ran.

## 3. What to build

**3.1 — The artifact list must distinguish approved from serving.** `status: "approved"` with
`registry_model_id: null` means *approved for the product, not answering predictions*. Today the
UI would show that as deployed. Render two separate states; `registry_status` is the authoritative
one for "is this live", and when it disagrees with `status`, `registry_status` wins.

**3.2 — Never render a confidence without its scale.** `uncertainty.scale` says what the number
means, and the two are not comparable:

- `"verifier_quality"` — the deterministic verifier's own quality scale. **0.870 is the score at
  the reference uncertainty, not a ceiling**; 1.0 is unreachable. Do not draw it as a percentage
  bar against 100%, which would make every real prediction look poor.
- `"dp4_posterior"` — a closed-world probability across the candidate set supplied.

**3.3 — `confidence_score: null` is a result, not an empty state.** It means the engine ran and
declined to report a confidence (e.g. DP4 over a single candidate, where the posterior is 1.0 by
construction). Those responses come back `status: "requires_review"` with a warning that names the
cause. Show the warning; do not render an empty gauge or "—".

**3.4 — Show provenance.** `metadata_json.provenance.model_versions` maps each component that
touched the number to the version it ran at — a registry artifact's SHA-256 on the routed-prediction
path, a pinned method tag elsewhere (DP4 ranking reports `dp4_scoring: smith_goodman_2010`). Render
it as name/version pairs; the value is not always a hash, so do not label the column "checksum" or
truncate it like one. This is the audit answer to "which model produced this", and there is nowhere
in the UI showing it today.

**3.5 — Two new refusals to render.**
- `POST /ai/predictions` → **503** when the engine cannot run. The caller's request was valid;
  offer a retry, not a correction. (Note the `/api/backend` proxy sanitizes 401/403 bodies but not
  503, so the detail text passes through.)
- `POST /ml/deployment-candidates/{id}/approve` → **400** when the candidate regresses on a
  safety-critical metric. The detail names the metric and the delta — surface it verbatim next to
  the metrics table rather than as a generic toast.

**3.6 — Promotion is an explicit second step, not a checkbox.** When a reviewer approves, the
`registry_promotion` block is what makes the model serve traffic. It needs facts the artifact row
does not carry (role, nucleus, data lineage), so the form must collect them and must not default
them. Approving *without* the block is a legitimate and common choice — approved, not serving — and
the response's `notes` say which happened. Read `notes` for the `Metric comparison:` /
`Metric comparison skipped:` line and show it; a skipped check must not read as an endorsement.

## 4. Verification

```bash
cd moltrace_frontend && pnpm typecheck && pnpm lint && pnpm test -- --run
```

Then, against a local backend, confirm by hand:

1. Approve a candidate **without** `registry_promotion` → artifact shows approved, not serving.
2. Approve a second candidate for the same task with a worse `ece` → 400, metric named in the panel.
3. Approve with `registry_promotion` → `registry_status: "production"`; approve a third and the
   second flips to `"retired"` on its own.
4. `POST /ai/predictions` for `nmr_candidate_ranking` with one candidate → `confidence_score: null`,
   `requires_review`, warning rendered.
5. Same call with `confidence_score` inside `request_json` → 400 naming the key. (This is the
   `extra=forbid`-adjacent trap: the key is rejected by the *engine*, not by the model, so the
   status is 400 rather than 422.)

## 5. Out of scope

The two regulatory intelligence routes (`/regulatory/intelligence/search` and `/explain`) are
**not** shipped and should not be designed against yet. There is no indexed guidance corpus, so
they would search nothing. Tracked as C4 in `docs/ai_ml_layer_upgrade_program.md`.
