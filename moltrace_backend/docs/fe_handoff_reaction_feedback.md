# FE Handoff — Repho R9: chemist feedback → preference re-ranker → A/B gate

**Backend status:** shipped (engine `5666fe6`, wiring `9aa5691`). New owner-scoped routes under the
reaction-project surface. Do this in `moltrace_frontend/`.

> What it is: chemists give **structured feedback** (accept / edit / reject + a reason taxonomy) on
> proposals; that feedback trains an **advisory** preference re-ranker (re-orders proposals by likely
> acceptance, never overrides the optimiser), and an **A/B promotion gate** decides — as
> decision-support — whether a challenger model may replace the champion. A **safety ("unsafe")**
> rejection is high-signal: it routes to strengthen the R6 safety screen and is **excluded** from
> preference learning. Nothing auto-deploys.
>
> Principle: **integrate, don't clutter** — fold into the existing recommendations / advisor UI in
> `components/reaction-optimization/`; no new top-level nav.

## 1. Regenerate the typed contract first
```bash
# backend on :8000, then in moltrace_frontend/
npm run generate:openapi   # picks up the 4 new routes + their models
```
New models: `ReactionFeedbackCreateRequest`, `ReactionFeedbackRecord`, `ReactionPreferenceRanking`
(+ `…RankedItem`), `ReactionABEvaluateRequest` (+ `ReactionModelMetricsInput`),
`ReactionABPromotionVerdict`.

## 2. Endpoints (all owner-scoped; non-leaking 404)
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/reaction-projects/{id}/feedback` | `ReactionFeedbackCreateRequest` | `ReactionFeedbackRecord` (201) |
| GET | `/reaction-projects/{id}/feedback` | — | `ReactionFeedbackRecord[]` |
| GET | `/reaction-projects/{id}/preference-ranking` | — | `ReactionPreferenceRanking` |
| POST | `/reaction-projects/{id}/ab-promotion/evaluate` | `ReactionABEvaluateRequest` | `ReactionABPromotionVerdict` |

- **422** on a `reject` with no (or an invalid) `reason`.
- **404** (non-leaking) for a non-owner.

## 3. Key semantics
- **Feedback** — `decision ∈ {accept, edit, reject}`; `reason ∈ {unsafe, infeasible_on_our_kit,
  reagent_unavailable, cost, lower_confidence_than_stated, wrong_precedent, other}` (required on
  reject). Send `proposal_ref` (the candidate/recommendation id), optional `features` (the candidate's
  conditions — feeds the re-ranker), and `model_version` (what produced the proposal). The response
  flags `is_safety_signal` / `routes_to_safety_hardening` / `is_preference_learnable` — surface that an
  unsafe rejection went to the safety gate and is **not** used to re-rank.
- **Preference ranking** — `advisory: true`. Each `ranked[]` item carries `acceptance_score`,
  `original_rank` (the optimiser's own rank — show both; the re-rank is a suggestion), and
  `conditions_json`. `bo_run_id` is null until a BO run exists. Never present this as the optimiser's
  decision.
- **A/B gate** — pure decision-support; **deploys nothing**. `promotable` is true only when
  `safety_regression` is false **and** `dominates` is true; `requires_human_signoff` and
  `rollback_available` are always true. `reasons[]` explains the verdict; `excluded_metrics[]` lists
  metrics dropped (unknown direction / not comparable). Render it as a gated recommendation a human
  must approve — never an auto-promote button.

## 4. Suggested UI
1. **Feedback control on each proposal** — accept / edit / reject buttons + a reason dropdown
   (required on reject) + optional free-text. On submit, POST `…/feedback` with the candidate's
   `proposal_ref`, `features` (its conditions), and the `model_version`. Show the safety-routing note
   when `is_safety_signal`.
2. **"Likely acceptance" re-rank** — an optional toggle on the recommendations list that calls
   `…/preference-ranking` and re-orders by `acceptance_score`, **keeping the optimiser's `original_rank`
   visible** (badge: "BO #3 · likely-accept 0.82").
3. **A/B compare panel** (advisory) — paste/select a champion + challenger metric vector + recall →
   POST `…/ab-promotion/evaluate` → render the verdict with the `reasons[]`, the safety/dominance
   flags, and a clear "requires human sign-off — does not deploy" banner.

## 5. Verify (FE session)
- `npm run test` (vitest/jsdom); mock `apiFetch`.
- Live-curl `:8000`: sign up → project (+ design-space + completed experiments + a BO run) →
  POST `…/feedback` (accept; reject+cost; reject+unsafe → check `is_preference_learnable:false`) →
  GET `…/preference-ranking` → POST `…/ab-promotion/evaluate` (regressed recall → `promotable:false`).

## 6. Notes
- The preference re-ranker and A/B gate are **advisory** — the optimiser and the human stay in charge.
- A safety rejection never trains the re-ranker; it hardens R6. Keep that distinction visible.
