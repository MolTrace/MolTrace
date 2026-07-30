# FE Handoff — Spectrum retrieval: per-nucleus coverage on each hit

**Backend status:** shipped (`11da4da` per-nucleus index + coverage fields, `7f3437e`
asymmetric penalty; encoder `43f24df`, corpus converter `5a45356`).
Two additive fields on `SpectrumRetrieveHit`. No new routes, no new nav, no request-shape
change. Do this in `moltrace_frontend/`.

> Principle: **integrate, don't clutter** — this is two extra columns / one badge inside
> the existing `components/spectracheck/spectrum-retrieve-panel.tsx` table. Nothing new
> is surfaced anywhere else.

## 0. Why this exists (read before designing the cell)

The reference index is now built **per nucleus**, because 82% of reference spectra in the
public shift databases record only ¹H or only ¹³C. A hit's distance is the mean over the
nuclei the query and that reference **share**, plus a penalty for query nuclei the
reference lacks.

The consequence that matters for the UI: **part of a distance can be the penalty rather
than measured disagreement.** A reference identical on the one nucleus it carries reports a distance
that is *entirely* penalty with **zero** measured disagreement in it — `0.05` for a
carbon-only reference, `0.25` for a proton-only one, against a both-nuclei query. That is
not the same evidence as the same number measured across both nuclei, and today's panel
renders them identically. A scientist reading a small distance cannot currently tell
whether the proton spectrum agreed, or was never in the reference at all.

## 1. Regenerate the typed contract first

```bash
npm run generate:openapi
```

With the backend on `:8000`. This is the binding step — do not hand-edit `schema.d.ts`.
Afterwards `components["schemas"]["SpectrumRetrieveHit"]` must read:

```ts
SpectrumRetrieveHit: {
    id: string;
    l2_distance: number;
    /** Nuclei Compared */
    nuclei_compared?: string[];
    /** Nuclei Absent */
    nuclei_absent?: string[];
};
```

If the two fields are absent after regenerating, the backend you generated against is
older than `11da4da` — check it out and restart before continuing.

## 2. Contract delta

| Field | Type | Meaning |
|---|---|---|
| `nuclei_compared` | `string[]` | Nuclei that actually contributed distance for this hit. Values: `"1h"`, `"13c"`. |
| `nuclei_absent` | `string[]` | Nuclei the **query** had that this reference does not carry. Same value domain. |

Both default to `[]`. **Empty means "this index does not report coverage", not "nothing
matched"** — a single-index deployment returns empty for every hit, so the UI must treat
empty as *unknown* and fall back to today's rendering, never render "matched on nothing".

Unchanged: `id`, `l2_distance` (still ascending, lower = closer), `method` (still the
literal `"vector_l2"` — deliberately not renamed, so your `result.method === "vector_l2"`
branch at line 267/270 keeps working), `index_size`, `top_k`, `warnings`, and the whole
request body.

One value change worth knowing even though no code should depend on it: `l2_distance` is
now a **true** L2 distance. It was previously FAISS's *squared* L2 surfaced under that
name. Ordering is identical (√ is monotonic) and there is no threshold anywhere in the FE,
so `hit.l2_distance.toFixed(4)` needs no change — the numbers are simply smaller than
before for the same data. Do not add a hard-coded cutoff on this value; see §5.

## 3. Response shape (real payload from the live 42,449-molecule index)

Both-nuclei query — every hit compared on both, nothing absent:

```jsonc
{
  "query_source": "shifts",
  "method": "vector_l2",
  "index_available": true,
  "index_size": 42449,
  "top_k": 3,
  "results": [
    { "id": "nmrshiftdb2:10009222", "l2_distance": 0.1337,
      "nuclei_compared": ["1h", "13c"], "nuclei_absent": [] },
    { "id": "nmrshiftdb2:20000223", "l2_distance": 0.2639,
      "nuclei_compared": ["1h", "13c"], "nuclei_absent": [] }
  ],
  "warnings": []
}
```

The case the UI needs to distinguish — a ¹³C-only reference matched by a query that also
had protons. Its distance is *mostly the penalty*:

```jsonc
{ "id": "nmrshiftdb2:20208905", "l2_distance": 0.0500,
  "nuclei_compared": ["13c"], "nuclei_absent": ["1h"] }
```

And a ¹³C-only **query** — nothing is "absent", because the query never had protons to
compare:

```jsonc
{ "id": "nmrshiftdb2:20208905", "l2_distance": 0.0848,
  "nuclei_compared": ["13c"], "nuclei_absent": [] }
```

Note the asymmetry: `nuclei_absent` is relative to **the query**, not to a complete
spectrum. A ¹³C-only query produces `nuclei_absent: []` on every hit. Do not render
"missing ¹H" in that case — nothing is missing; the user simply did not run that
experiment.

## 4. What to build

In `components/spectracheck/spectrum-retrieve-panel.tsx`:

1. **A "Matched on" column** after `L2 distance` (line ~296 header, ~313 cell). Render
   `nuclei_compared` in plain language, not the wire keys: `1h` → `¹H`, `13c` → `¹³C`;
   both → `¹H + ¹³C`. When `nuclei_compared` is empty, render `—`.
2. **A partial-coverage marker** when `nuclei_absent.length > 0`. A muted badge or an
   asterisk on the distance cell, with a title/tooltip along the lines of
   *"This reference has no ¹H data, so only its ¹³C was compared — part of the distance
   reflects the missing data rather than disagreement."* The two directions are not
   equally weighted: a reference missing ¹³C is penalised five times as heavily as one
   missing ¹H, because ¹³C carries more structural information — do not imply the two are
   equivalent. Keep the wording plain: no `nuclei_absent`, no field names, no "penalty
   term", per the no-backend-jargon rule.
3. **Leave the sort alone.** The defensive ascending sort at line 211 is still correct;
   the backend still returns ascending and lower is still closer.
4. **Footer copy** (line ~324) currently reads "lower L2 = closer; corroborate against the
   observed spectrum". Extend it to note that some references carry only one nucleus, so
   a close match on one nucleus is weaker corroboration than a close match on both.

Do **not** add a similarity threshold, a colour band, or a pass/fail on `l2_distance`.
There is no calibrated cutoff and inventing one in the UI would assert a confidence the
backend does not compute.

## 5. Verification

1. `npm run generate:openapi`, then `npx tsc --noEmit` — the panel must compile with the
   two new optional fields.
2. Unit-test the cell with all four coverage shapes above, including the empty/unknown
   case (a single-index deployment) and the ¹³C-only-query case where `nuclei_absent` is
   `[]` but `nuclei_compared` is one nucleus. The second is the one most likely to be
   rendered wrong as "missing data".
3. Live check against a running backend with the per-nucleus index configured
   (`MOLTRACE_SIMILARITY_INDEX` → the manifest written by
   `scripts/build_similarity_index.py`): POST `/spectrum/retrieve` with `shifts_13c` only
   and confirm every row shows "matched on ¹³C" with no partial-coverage marker; then post
   both `shifts_1h` and `shifts_13c` and confirm rows whose reference lacks protons do get
   the marker.

## 6. Out of scope here

`/spectrum/reason` (`SpectrumReasonAnalogue`) also carries `l2_distance` and a derived
`similarity`, and its query encoder buckets peaks into a **single** nucleus, so its
analogues are always single-nucleus comparisons. Coverage fields were not added there. If the reasoner's analogue table needs the same disambiguation, that is a
separate backend change — raise it rather than deriving coverage in the FE.
