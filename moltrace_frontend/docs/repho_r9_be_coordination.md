# Repho R9 — FE→BE coordination notes

The R9 FE (chemist feedback → preference re-rank → A/B gate) is shipped and works end-to-end against
the current backend. These are **informational** notes for the BE session — none block R9.

## 1. `proposal_ref` id-space: preference-ranking uses the acquisition-candidate id, not the recommendation id

`GET …/preference-ranking` builds each ranked item's `proposal_ref` from `str(candidate.id)`
(`ReactionAcquisitionCandidateORM`, see `reaction_feedback_store.preference_ranking`). The FE renders
proposals from `GET …/recommendations` (`ReactionRecommendationORM`), whose row `id` is a **different
id space** (separate table, separate autoincrement). On a fresh project the two sequences can
coincide (both `15,16,17`), which masks the difference in a simple smoke test, but across projects
they diverge.

- **FE mitigation (done, no BE change needed):** the "likely-acceptance" re-rank joins the ranking
  onto the recommendation cards by **`conditions_json` content** (`canonicalConditionsKey`), not by id,
  so it is robust to the id-space mismatch. Feedback learning is already features-based
  (`predict_acceptance(model, features)`), so feedback POSTed with the recommendation id as
  `proposal_ref` still trains correctly (the handoff allows "the candidate/recommendation id").
- **Optional BE cleanup (nice-to-have):** if you'd prefer a canonical id join, have
  `preference_ranking` emit `proposal_ref = str(recommendation.id)` (map `rank→original_rank`,
  `conditions_json→features`), or persist a `candidate_id ↔ recommendation_id` link in
  `reaction_bo` (the two rows are created adjacently). Then the FE could key by id again.

## 2. Optional FE follow-up (not a BE item): reload durability of the per-proposal feedback note

`GET …/feedback` (history) is contracted but not yet consumed by the FE — the per-card "recorded /
routed-to-safety / preference-learnable" note is session-only and resets on reload (the durable
record persists server-side, so this is a re-display gap only). A future FE pass can load
`GET …/feedback` in `load()` and seed the per-card result by the same `conditions_json` join.

## 3. A/B `directions` vocabulary

The A/B engine's `_direction` only honours the tokens **`higher` / `lower`** (anything else excludes
the metric). The FE normalizes friendly synonyms (`maximize`/`max` → `higher`, `minimize`/`min` →
`lower`) before POSTing. No BE change needed — just noting the contract so it isn't "fixed" to
maximize/minimize.
