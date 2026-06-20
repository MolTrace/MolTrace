# FE Handoff — Repho R6: Structural Safety Screening + Review Gate

**Backend status:** shipped (`27fbc46`, engine `328b40a`). New table + 5 routes under the
reaction PDP/owner gate. Do this in `moltrace_frontend/`.

> **Decision-support only.** This is a structural (RDKit-SMARTS) energetic/reactive-group
> screen — NOT a safety determination. Surface the returned `disclaimer` verbatim and never
> present a "clear" result as a safety clearance. Distinct from the existing
> *safety-constraint profile* (manual operating limits) — this is a new, separate panel.
>
> Principle: **integrate, don't clutter** — fold into the existing
> `components/reaction-optimization/` workspace; no new top-level nav.

## 1. Regenerate the typed contract first
```bash
# backend on :8000, then in moltrace_frontend/
npm run generate:openapi   # picks up /safety-screenings, /safety-gate + ReactionSafety* models
```

## 2. Endpoints (all owner-scoped + nested under the project)
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/reaction-projects/{id}/safety-screenings` | `ReactionSafetyScreenRequest` | `ReactionSafetyScreening` (201) |
| GET | `/reaction-projects/{id}/safety-screenings` | — | `ReactionSafetyScreening[]` |
| GET | `/reaction-projects/{id}/safety-screenings/{screening_id}` | — | `ReactionSafetyScreening` (404 if not in project) |
| POST | `/reaction-projects/{id}/safety-screenings/{screening_id}/review` | `ReactionSafetyReviewRequest` | `ReactionSafetyScreening` |
| GET | `/reaction-projects/{id}/safety-gate` | — | `ReactionSafetyGateStatus` |

A non-owner gets a non-leaking **404** on all of these (owner/system/admin only).

## 3. Shapes
**`ReactionSafetyScreenRequest`:**
```jsonc
{
  "reactant_smiles": ["CCN=[N+]=[N-]"],   // SMILES per species
  "reagent_smiles": [],
  "product_smiles": null,
  "label": "Step 3 azide displacement"
}
```
**`ReactionSafetyScreening`** (response): `id`, `overall_risk` (`low|medium|high|critical|unknown`),
`requires_expert_review`, `review_status` (`not_required|pending|approved|rejected`),
`review_note`, `reviewed_by_user_id`, `reviewed_at`, `created_at`, `disclaimer`, and
`result_json` — the engine output: `species[]` (each `{role, smiles, parsed, flagged_groups[],
overall_risk}`), `energetic_groups_found[]`, where each flagged group is
`{key, label, severity, count, mitigation}`.

**`ReactionSafetyReviewRequest`:** `{ "decision": "approved" | "rejected", "note": "PHA done…" }`.

**`ReactionSafetyGateStatus`:** `{ reaction_project_id, status: "clear" | "review_pending" |
"blocked", screenings_total, blocking_screening_ids[], summary }`.

## 4. Gate semantics (drive a banner from `/safety-gate`)
- **clear** — no screening needs review (green).
- **review_pending** — at least one flagged screening awaits a verdict (amber; "N screenings
  await expert review before execution").
- **blocked** — at least one screening was **rejected** (red; hard stop — "do not proceed
  without a qualified process-safety sign-off").
- A benign structure → `requires_expert_review:false`, `review_status:"not_required"` (no gate hold).

## 5. Suggested UI
1. **Project gate banner** — poll `/safety-gate`; colour + summary by `status`; list the
   `blocking_screening_ids` as quick links.
2. **Screenings list** — risk badge per row; expand to show each species' `flagged_groups`
   (label + severity + **mitigation** note). Always render the `disclaimer`.
3. **Review action** — for a `pending` screening, an Approve / Reject control with a required
   note; POST to `…/review`. Gate this control to qualified reviewers in your role model.
4. **Run a screen** — a form taking SMILES (prefill from the project's compounds/experiments
   where available) + an optional label.

## 6. Verify (FE session)
- `npm run test` (vitest/jsdom) for the panel/banner; mock `apiFetch`.
- Live-curl `:8000`: sign up → project → POST a screen for `CCN=[N+]=[N-]` (azide → critical,
  `review_pending`) → POST review `approved` → `/safety-gate` returns `clear`; POST a second
  screen + review `rejected` → gate `blocked`.

## 7. Notes
- Screening is **deterministic** (RDKit SMARTS; no model).
- **The gate is now enforced server-side at the execution-commit point.** While any screening
  for the project stands **rejected** (gate `blocked`), committing a reaction execution batch to
  `planned`/`running` is refused with **HTTP 409** — at the batch endpoints *and* at the
  item-driven auto-promotion path (adding/marking a `planned`/`running` item that would promote a
  draft batch). `draft` batches, outcome-recording transitions (`completed`/`failed`/…), and
  projects with no rejected screening are unaffected. A merely *pending* screening stays advisory
  (it does not 409). On a 409, surface the `safety-gate` banner and the `detail` message (it names
  the rejected screening ids). BO-run *recommendation generation* remains advisory by design.
- Quantitative predictions (exothermicity, gas evolution, DSC onset) are out of this slice.
