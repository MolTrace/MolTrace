# FE Handoff — Repho R5: Half-closed DMTA loop (propose-next)

**Backend status:** shipped (wiring `f07f09dc`, engine `09f340a7`). New owner-scoped route on the
optimization-cycle surface. Do this in `moltrace_frontend/`.

> What it is: the design-make-test-analyze loop is now **metered and human-gated**. A reviewer
> records a cycle decision; only a `continue_optimization` decision unlocks **proposing the next
> batch**. Proposing is decision-support — it creates a NEW **draft** cycle and **executes
> nothing**; execution still needs a human to commit an execution batch (guarded by the R6 safety
> gate). Never present propose-next as "running" the next experiments.
>
> Principle: **integrate, don't clutter** — fold into the existing optimization-cycle UI in
> `components/reaction-optimization/`; no new top-level nav.

## 1. Regenerate the typed contract first
```bash
# backend on :8000, then in moltrace_frontend/
npm run generate:openapi   # picks up the /propose-next route
```

## 2. Endpoint (owner-scoped; nested under the cycle)
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/reaction-optimization-cycles/{cycle_id}/propose-next` | `ReactionBayesianOptimizationRunRequest` (all fields defaulted — `{}` is valid) | `ReactionOptimizationCycle` (201, a **new draft** cycle) |

- **409** when the loop may not propose (no decision yet, or latest decision is `pause` / `stop_*` /
  `revise_*` / `requires_review`) — the `detail` carries the human-readable reason.
- **404** (non-leaking) for a non-owner.

## 3. Response shape (the new draft cycle)
A normal `ReactionOptimizationCycle` with `status: "draft"`, a fresh `bo_run_id`, and a
`metadata_json` carrying:
```jsonc
{
  "cycle_metrics": {
    "metrics": { "latency_seconds": null, "phase_latencies_seconds": {},
                 "experiments_to_target": null, "best_objective": null, "target_met": false,
                 "total_experiments": 0, "new_experiments": 5 },
    "provenance": { "bo_run_id": 42, "surrogate_model_version": "…",
                    "spectracheck_session_ids": [], "spectracheck_model_version_ids": [] },
    "dmta_sequence": ["propose","safety_gate","make","test","learn","decision"],
    "engine": "reaction_loop.v1"
  },
  "proposed_from_cycle_id": 41,
  "propose_next": { "allowed": true, "reason": "…",
                    "requires_human_signoff_before_execution": true,
                    "execution_blocked_by_safety": false, "safety_gate_status": "clear" },
  "note": "Proposed next batch (decision-support). Execution requires human signoff …"
}
```

## 4. Suggested UI
1. **"Propose next batch" action** on a cycle — enabled only when the cycle's latest decision is
   `continue_optimization` (otherwise show why it's disabled, or let the click surface the 409
   reason). POST `{}` (or pass BO params: `algorithm`, `batch_size`, `safety_aware`…). On success,
   route the user to the new draft cycle.
2. **Loop-metrics readout** on a cycle — render `metadata_json.cycle_metrics.metrics`
   (experiments-to-target, latency, best/target gap) as the "how fast / how far" of the campaign.
3. **Half-closed banner** — on the proposed draft cycle, show the `note` + `propose_next` flags:
   "execution requires signoff", and if `execution_blocked_by_safety` is true, link to the
   `…/safety-gate` (the batch can't go planned/running until the rejected screening is resolved).
4. **DMTA stepper** (optional) — visualize `cycle_metrics.dmta_sequence`
   (propose → safety_gate → make → test → learn → decision) with the per-phase latencies.

## 5. Verify (FE session)
- `npm run test` (vitest/jsdom); mock `apiFetch`.
- Live-curl `:8000`: sign up → project (+ design-space + objective + one completed experiment) →
  create a cycle → record a `continue_optimization` decision → POST `…/propose-next` → a new
  **draft** cycle with `cycle_metrics`; then record `pause` on a cycle → propose-next → **409**.

## 6. Notes
- Proposing is the **only** automated loop step. Make / test / learn remain human/manual (SDL
  automation is a Phase-C add, R15).
- Execution of any proposed batch is still hard-gated by R6 (a rejected safety screening → 409 at
  the execution-batch commit). Surface that path from here.
