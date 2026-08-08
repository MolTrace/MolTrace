# FE handoff — the candidate-ranking panel needs its coverage

**Backend change:** `31f16bd`..HEAD (see the DP4 commit)
**Panel affected:** `components/spectracheck/spectracheck-evidence-panels.tsx`,
`DP4RankingPanel` (reads `payload.dp4_ranking`, renders `row.dp4_probability`)
**Contract impact:** none — `dp4_ranking` is `list[dict[str, Any]]`, untyped in
`schema.d.ts`. No regeneration needed. New keys are additive; nothing was removed
or renamed.

---

## Why

The panel currently renders `dp4_probability` and the RMS error. Both are more
confident than the underlying numbers support, in two independent ways.

**1. The RMS error stops responding to error.** It is computed only over peaks
that paired within ±0.3 ppm, so peaks the prediction missed badly are excluded.
Measured on twelve 1H shifts, one candidate, observed = truth + N(0, err):

| true RMSE | reported RMSE | matched |
|---|---|---|
| 0.140 | 0.118 | 11/12 |
| 0.540 | 0.203 | 8/12 |
| 1.068 | 0.151 | 6/12 |
| 2.418 | 0.154 | 6/12 |

A seventeen-fold degradation in the real fit moves the displayed number from
0.118 to 0.154. The only thing that moved was the matched count — which the row
emitted with **no denominator**, so `6` looked the same as 6 of 6.

**2. The probability is a ranking, not a calibrated posterior.** The DP4 σ/ν are
the residual distribution of DFT-computed shifts; production predicts shifts with
an empirical RDKit model whose measured error on real paired spectra is 2.25×–7.72× σ.
The ordering is sound. "94% likely to be this structure" is not.

## What is new on each row

| key | type | meaning |
|---|---|---|
| `observed_peak_count` | int | the denominator for `matched_peaks` |
| `matched_fraction` | float 0–1 | `matched_peaks / observed_peak_count` |
| `low_coverage` | bool | true below 0.75 matched |
| `error_basis` | `"matched_peaks_only"` | what MAE/RMSE are computed over |
| `probability_is_calibrated` | `false` | always false today |
| `probability_basis` | string | a sentence explaining what the number is |
| `notes` | string[] | gains a coverage sentence when `low_coverage` |

Two analysis-level entries also appear in `warnings` when a ranking exists: one
stating the ranking is not a calibrated probability, and — when the leader is
low-coverage — one naming its matched count.

## What to change

1. **Never render `rms_error_ppm` or `mean_abs_error_ppm` without the coverage
   beside it.** Show `matched_peaks` / `observed_peak_count` adjacent, not in a
   tooltip. The error figure alone is the misleading artefact.
2. **Relabel the probability column.** It is a relative ranking across the
   candidates supplied. Avoid "probability", "confidence", "likelihood that this
   is correct". Something like **"Match rank (relative)"** with
   `probability_basis` as the help text. Do not print `dp4_probability` as a
   percentage next to the word "probability".
3. **Mark `low_coverage` rows visibly** — the row is not merely less certain, its
   error figure is measuring a different (smaller) thing than the reader assumes.
4. **Keep the ordering.** The ranking still identifies the correct candidate;
   there is a test for that. This is a labelling and disclosure change, not a
   deprecation.
5. Existing keys are unchanged, so nothing breaks if you ship (1) and (2) first.

## Verify

```bash
cd moltrace_frontend
pnpm vitest components/spectracheck/spectracheck-evidence-panels.test.tsx --run
```

The existing fixture at `spectracheck-evidence-panels.test.tsx:260` has rows with
only the old keys. Add `observed_peak_count`, `matched_fraction` and
`low_coverage` to it and assert the panel renders coverage for a low-coverage row
— a fixture without the new keys will otherwise keep passing while the panel
silently renders nothing for them.

## What the backend deliberately did NOT do

Invent a corrected σ. The true value is *bracketed* by the two measurements
(2.25× censored, 7.72× uncensored), not pinned — the censored figure drops every
badly-predicted peak, the uncensored one greedily pairs distant ones. Substituting
a round number for a measured distribution is a mistake this codebase has already
shipped once. The number is labelled rather than silently rescaled.
