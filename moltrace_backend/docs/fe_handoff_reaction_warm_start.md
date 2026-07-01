# FE Handoff — Repho R10: warm-start transfer-learning priors

**Backend status:** shipped (engine `7d8e997`, wiring `c066484`). New owner-scoped routes under the
reaction-project surface. Do this in `moltrace_frontend/`.

> What it is: a new campaign can **warm-start** from the chemist's accumulated, **verified**
> (SpectraCheck-linked or reviewer-confirmed) data on **related, owned** campaigns — so it reaches the
> target in fewer experiments. Building a prior freezes that data into a content-hashed, lineage-bearing
> snapshot (the frozen evaluation gold set is excluded), fits a prior, and offers an **advisory**
> re-ranking of the next BO batch by likely success. Nothing auto-deploys; the prior never overrides
> the optimiser.
>
> Principle: **integrate, don't clutter** — fold into the existing reaction-optimization UI in
> `components/reaction-optimization/`; no new top-level nav.

## 1. Regenerate the typed contract first
```bash
# backend on :8000, then in moltrace_frontend/
npm run generate:openapi   # picks up the 3 new routes + their models
```
New models: `ReactionWarmStartBuildRequest`, `ReactionWarmStartPriorRecord`,
`ReactionWarmStartRanking` (+ `…RankedItem`).

## 2. Endpoints (all owner-scoped; non-leaking 404)
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/reaction-projects/{id}/warm-start/prior` | `ReactionWarmStartBuildRequest` | `ReactionWarmStartPriorRecord` (201) |
| GET | `/reaction-projects/{id}/warm-start/prior` | — | `ReactionWarmStartPriorRecord` (404 if none) |
| GET | `/reaction-projects/{id}/warm-start/ranking` | — | `ReactionWarmStartRanking` |

- **404** (non-leaking) for a non-owner **and** for any `source_project_ids` entry the caller does not
  own (cross-tenant guard — a prior can only be built from campaigns you own).
- **400** when there's no admissible data (no verified experiments, duplicate observation ids, or a
  non-native condition value).

## 3. Request + key semantics
`ReactionWarmStartBuildRequest`:
- `source_project_ids: int[]` — campaigns to learn from. **Default = this project** (intra-campaign
  warm-start); add related **owned** campaigns for transfer learning. A non-owned id → 404.
- `gold_set_observation_ids: string[]` — observations to exclude (the R11 benchmark). Observation ids
  are `"{source_project_id}:{experiment_id}"`. Empty until R11 lands.
- `objective_target: number | null` — the campaign target (recorded in the snapshot).
- `require_verified: boolean` (default `true`) — admit only SpectraCheck-verified / reviewer-confirmed
  outcomes. Set `false` only for a preview on unconfirmed data.

`ReactionWarmStartPriorRecord` carries `snapshot_hash`, `lineage` (source campaigns, counts, verified),
`trained_n`, `excluded_gold_count`, `excluded_unverified_count`, `global_mean`, `feature_offsets`, and
`objective_target`. Surface the lineage so a reviewer sees exactly what the prior was fit from.

`ReactionWarmStartRanking` is `advisory: true`. Each `ranked[]` item has `prior_mean`, `original_rank`
(the optimiser's own rank — show both), and `conditions_json`. `prior_id`/`bo_run_id` are null until a
prior/BO run exists.

## 4. Suggested UI
1. **"Warm-start from related campaigns"** action when starting a campaign — a picker of the chemist's
   **owned** campaigns → POST `…/warm-start/prior` → show the fitted prior's **lineage** (trained_n,
   source campaigns, excluded gold/unverified counts, `snapshot_hash`) so it's auditable.
2. **Warm-start re-rank** — an optional toggle on the recommendations list that calls
   `…/warm-start/ranking` and re-orders by `prior_mean`, **keeping the optimiser's `original_rank`
   visible** ("BO #4 · prior 0.71"). Advisory only.
3. **Empty states** — `GET …/prior` 404 → "no warm-start prior yet"; `ranked: []` (no BO run) → prompt
   to run a BO batch first.

## 5. Verify (FE session)
- `npm run test` (vitest/jsdom); mock `apiFetch`.
- Live-curl `:8000`: sign up → project (+ design-space + a few completed experiments with
  `metadata_json.outcome_confirmation` so they count as verified) → POST `…/warm-start/prior` (see
  `trained_n`) → run a BO batch → GET `…/warm-start/ranking` (candidates carry `prior_mean`). Then try a
  `source_project_ids` id you don't own → **404**.

## 6. Notes
- The prior is **advisory** and fit only from **owned, verified** data, never the gold set — keep those
  guarantees visible in the UI.
- Frozen weights live in the DB, not git; there's nothing for the FE to download.
