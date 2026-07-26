# Proton-inventory accuracy (Phase 1) — FE→BE coordination notes

All six FE items from the handoff are shipped. These are **informational** — none block the change.

## 1. Please do add per-row `severity` (you offered it; we now want it)

Handoff §4 said: *"colour a row amber if and only if a backend `warnings[]` entry refers to that
row… If you want a cleaner contract than string-matching, ask the backend session for per-row
`severity`."*

We took the string-matching route for now, but anchored rather than fuzzy: the FE matches
`warning.toLowerCase().startsWith("observed {key} integration")`, which is exactly how
`build_proton_inventory` phrases every per-bucket warning. It is exported and unit-tested
(`warningRefersToInventoryRow`).

**The risk we are carrying:** any future warning that refers to a bucket but is phrased differently
(a different call site, a reworded message, a bucket key containing a space) will silently stop
colouring its row — a warning that *should* be amber rendering neutral. That is a fail-open on an
evidence panel, so a structured field is genuinely better than prose parsing here.

Suggested minimal shape (additive, keeps `warnings[]` as-is):

```jsonc
"row_severity": { "labile": "warning", "total": "warning" }   // key → "warning" | "info"
```

The FE will switch to it and keep the string matcher only as a fallback.

## 2. A row can be discrepant, unflagged, and therefore visually silent

Because we removed the client-side `|Δ| >= 1.0` rule (correctly — it was a second copy of your
threshold), a row whose Δ is large but which the backend did not warn about now renders with no
visual signal at all. Today that is right for the CD₃OD labile case (suppressed on purpose, and the
`notes[]` entry explains it). It would be wrong if a bucket is ever discrepant *and* uncovered by
the warning generator.

We deliberately did **not** re-add any client-side significance judgement to paper over this — that
would recreate the exact drift the handoff removed. Per-row `severity` (item 1) closes it properly.

## 3. `integration_h` is the reported integral, not the "raw" one

Handoff §6 asked us not to present the impurity `∫ H` column as if it were on the inventory scale.
We relabelled it **"Reported ∫ H"** (not "Raw"): `reconcile_proton_peaks_with_reference_text`
overwrites `integration_h` with the reference-text value and moves the spectrum-parsed value to
`spectrum_integration_h`, so on a text-guided run "raw" would have been inaccurate.

When Phase 2 emits both values plus `overlaps_analyte`, we will show them side by side and can drop
the qualifier.

Note the same field is rendered under a bare `∫ H` header in three other tables
(`LabileHydrogenPanel`, the enriched-peak table, `PredictedVsObservedPanel`). Those were outside
this handoff's scope and are unchanged; worth a consistent convention in Phase 2.

## 4. Row order is now derived from `bucket_hierarchy`, not hard-coded

The FE no longer relies on its static row list to express structure: it renders each sub-count
directly beneath its declared parent and falls back to a flat row when the parent is not on screen.
So adding a new entry to `bucket_hierarchy` will nest correctly with no FE change — but a parent key
that never appears as its own row will render its children un-nested (by design, rather than
indenting them under an unrelated row).
