# FE handoff — proton-inventory accuracy (Phase 1)

Backend changes are landed and green. These are the frontend follow-ups. All of
them are **additive payload reads** — no existing field changed name or type, so
the app keeps working if you land them incrementally.

Scope: `moltrace_frontend/components/spectracheck/spectracheck-evidence-panels.tsx`
(plus `spectracheck-raw-fid-section.tsx`, which renders the same inventory shape).

---

## 0. Regenerate the typed contract first

```bash
cd moltrace_frontend && npm run generate:openapi
```

The backend added fields to the `proton_inventory` payload and one field to
`StructureSummary`. Nothing was removed.

---

## 1. Stop asserting "(structure-capped)" — read it from the payload

**Today:** `spectracheck-evidence-panels.tsx:358` hardcodes the row label

```ts
{ key: "anomeric_or_olefinic", label: "Anomeric / olefinic (structure-capped)" }
```

That label was a static string claiming a guarantee the payload could not
substantiate — and for aromatic-protected sugars no cap was in fact applied, so
the UI asserted something false.

**New field** on `proton_inventory`:

```jsonc
"anomeric_cap": {
  "applied": true,                                   // bool
  "limit": 2,                                        // int | null — max H the structure supports
  "method": "structural_anomeric_olefinic_budget",   // string
  "reassigned_h": 8.0                                // float — integration moved out of the bucket
}
```

**Do:** label the row plainly `"Anomeric / olefinic"`. When `applied` is true,
show a small annotation such as
`capped at {limit} H — {reassigned_h} H reassigned` (a tooltip or a muted
suffix). When `applied` is false, show no cap claim at all.

---

## 2. Nest the sub-count rows so the table sums to its own total

**New field** on `proton_inventory`:

```jsonc
"bucket_hierarchy": { "carbohydrate_sugar": "aliphatic", "carboxylic_acid": "labile" }
```

`carbohydrate_sugar` is a **sub-count of** `aliphatic`, and `carboxylic_acid` a
sub-count of `labile` — they are not sibling classes. Rendering them as peers
(current behaviour, `:359` and `:362`) means the visible rows do not add up to
the Grand total row, and a reviewer double-counts the sugar-backbone protons.

**Do:** indent/nest any row whose key appears in `bucket_hierarchy` under its
parent row, and exclude nested rows from any client-side column summing.

---

## 3. Render confirmations as confirmations, not warnings

**New field** on `proton_inventory`: `"notes": string[]`

`warnings[]` keeps its meaning (something disagrees with the structure).
`notes[]` is the new positive channel — observations that AGREE with the
structure and were previously either silent or, worse, rendered amber.

The motivating case: in CD₃OD or D₂O the labile OH/NH exchange for deuterium, so
their absence is the **expected** result. The backend now suppresses the labile
shortfall warning and emits instead:

> CD3OD exchanges NH/OH/SH protons for deuterium, so the 6 labile H are expected
> to be absent from the 1H spectrum. Observed 0.0 H — consistent with exchange.

**Do:** render `notes[]` in a neutral/positive style (not `--mt-amber`),
visually distinct from `warnings[]` at `:518-524`.

---

## 4. Stop duplicating the significance threshold

**Today:** `:459` re-implements the backend's rule client-side:

```ts
const deltaColor = delta !== null && Math.abs(delta) >= 1.0 ? "var(--mt-amber)" : undefined
```

That is a second, independent copy of a scientific threshold. It will drift the
moment the backend adopts a nucleus- or molecule-size-dependent tolerance (0.5 H
of rounding on a 63 H molecule is not the same as on a 6 H one).

**Do:** colour a row amber if and only if a backend `warnings[]` entry refers to
that row, rather than recomputing the threshold. (If you want a cleaner contract
than string-matching, ask the backend session for per-row `severity` — it is a
small addition and I would rather add it than have you parse prose.)

---

## 5. Aldehyde row is now checkable

`expected` and `deltas` now include an `aldehyde` key (backed by a new
`aldehyde_proton_count` on `StructureSummary`). The row previously rendered
`exp —, Δ —` permanently. No FE change needed beyond confirming the row picks up
the new key — just don't special-case it as un-checkable any more.

---

## 6. Impurity integrals: know which basis you are showing

Unchanged for now, but be aware: the impurity table's `integration_h` is the raw
parsed integral, while the inventory uses `inventory_integration_h` (0.0 for
solvent-excluded peaks). They are rendered side by side under identical "∫ H"
headers, which is why a solvent-residual row could read 26.00 H next to a 63.0 H
text total. Phase 2 will emit both values plus an `overlaps_analyte` flag; until
then, do not present the impurity ∫ H column as if it were on the inventory's
proton scale.

---

## 7. `structure_assignment` — ignore it for now

`proton_inventory.structure_assignment` is `null` unless the backend is run
with `MOLTRACE_STRUCTURE_ASSIGNMENT=1`. It carries a second, independent view
of the same spectrum produced by a structure-constrained global assignment
(each proton environment's count is a hard constraint, so it cannot
over-assign a class). It exists so the two routes can be compared on real data
before either drives the UI.

**Do:** nothing yet — just don't crash on the key being present or null. When
we promote it, the shape is `{feasible, total_cost, class_rollup, environments,
flows, contaminant_h, exchanged_h, unexplained_h, notes}` and `class_rollup`
is directly comparable to the `observed` block.

## Verification

Point the FE at a 1H analysis of an aromatic-protected aminoglycoside in CD₃OD
(e.g. a per-Cbz tobramycin derivative). Expected after these changes:

| Row | Observed | Expected | Δ |
|---|---|---|---|
| Aromatic | 35.0 | 35 | 0.0 |
| Anomeric / olefinic | 2.0 | 2 | 0.0 |
| ↳ Sugar backbone (nested) | 18.0 | — | — |
| Aliphatic | 26.0 | 26 | 0.0 |
| Labile | 0.0 | 6 | −6.0 |

- **Zero** amber warnings.
- One neutral note explaining the CD₃OD exchange.
- Cap annotation reading `capped at 2 H — 8.0 H reassigned`.
- Labile confidence **95%** (was 33%).
