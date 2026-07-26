# Proton-inventory accuracy (Phase 1) — FE→BE coordination notes

All six FE items from the handoff are shipped. These are **informational** — none block the change.

## 1. Per-row `severity` — the FE is already wired; the field is all that is missing

Handoff §4 said: *"colour a row amber if and only if a backend `warnings[]` entry refers to that
row… If you want a cleaner contract than string-matching, ask the backend session for per-row
`severity`."*

**We want it, and the FE now reads it already.** `inventoryFlaggedRows()` prefers a structured
`proton_inventory.row_severity` map and falls back to prose matching when it is absent. Ship the
field whenever convenient — no coordinated FE release is required, and no FE change either.

### The contract the FE honours today

```jsonc
"row_severity": {           // bucket key → severity
  "labile": "info",         // "info"     → NOT flagged (renders neutral)
  "aromatic": "warning",    // "warning"  → flagged (amber)
  "total": "error"          // "error" / "critical" → also flagged
}
```

Semantics the FE implements (all unit-tested in `spectracheck-proton-inventory.test.tsx`):

- Values are matched case-insensitively. `warning` / `error` / `critical` flag the row; `info`
  explicitly does not.
- **Structured wins over prose.** If `row_severity` names at least one row with a string value,
  the prose matcher is not consulted at all — so a map in which every row is `info` is an
  affirmative "nothing is wrong here", and a stale/reworded warning string can no longer re-flag a
  row you have cleared.
- Absent / `null` / `{}` / non-object / non-string values fall back to prose, so partial or
  malformed data degrades to today's behaviour rather than silently clearing every row.
- Keys the FE does not render are ignored; rows missing from the map are simply unflagged.

### Why this matters (the risk we were carrying)

The prose matcher anchors on `warning.toLowerCase().startsWith("observed {key} integration")`,
which is exactly how `build_proton_inventory` phrases every per-bucket warning today. But it is a
fail-OPEN contract: a warning from a different call site, a reworded message, or a bucket key
containing a space silently stops colouring its row — a real disagreement rendering neutral on an
evidence panel. The structured field removes that failure mode entirely.

## 2. A row can be discrepant, unflagged, and therefore visually silent

> Largely closed by item 1 once `row_severity` ships — a bucket you consider discrepant can be
> marked `warning` even when you choose not to emit prose for it.

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
