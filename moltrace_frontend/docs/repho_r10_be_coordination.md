# Repho R10 — FE→BE coordination notes

The R10 FE (warm-start priors) is shipped and works end-to-end against the current backend. These
are **informational** notes for the BE session — none block R10.

## 1. The constant record disclaimer is false for preview-fit priors

`ReactionWarmStartPriorRecord.disclaimer` is the constant `_DISCLAIMER`
(`reaction_priors_store.py`), which asserts the prior "is fit only from owned,
SpectraCheck-verified data" — but a `require_verified:false` build admits unverified observations,
and the record still carries the same verbatim text (plus the unconditional audit message
"fit from verified campaign data" at the `message=` call site).

- **FE mitigation (done):** the FE reads the persisted truth — `lineage.verified_only` — and for a
  preview fit renders a destructive "preview — unverified data admitted" badge + amber rebuild
  warning, suppresses the (false) verbatim disclaimer, brands the success toast as PREVIEW, and
  qualifies the warm-start re-rank note.
- **Optional BE cleanup:** make the record `disclaimer` and the audit `message` dynamic on
  `require_verified` so the server-side text is also accurate for preview fits.

## 2. Non-owned `source_project_ids` → 404 is unverifiable in dev

With dev auth off, `owner_scope_id` collapses, so the ownership guard
(`reaction_priors_store.py` ~109–112) never fires and a bogus source id falls through to the
empty-snapshot **400** instead. The guard is correct in source; just noting the live 404 path needs
an authed environment to exercise.

## 3. Smoke-data gotchas (for anyone re-running §5 by hand)

- The score function keys on the **objective-profile**: without one the project falls back to
  `multi_objective` and `_score_outcome` returns None for simple outcomes → every observation is
  skipped → 400 "Snapshot is empty…". POST `…/objective-profile` first.
- `maximize_yield` reads `outcome_json.yield_percent` (NOT `yield`).
- "Verified" = `linked_spectracheck_session_id` set OR an `outcome_confirmation` key in the
  experiment's `metadata_json`.
