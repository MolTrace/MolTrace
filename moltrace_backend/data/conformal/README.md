# Conformal shift calibration

`shift_calibration.json` is the fitted split-conformal calibration the structure verifier
scores matched resonances against. Point `MOLTRACE_CONFORMAL_CALIBRATION` at it.

## Why it exists

The shift predictor's reported σ is differentially mis-scaled. Held-out measurement put the
half-width/σ ratio between 8.66× and 1.77× across bins, where a correctly scaled σ would give a
constant — and it is worst in the tight bins, which is exactly where `_significance_from_sigma`
weighted evidence most heavily. A conformal interval carries a distribution-free coverage
guarantee instead, so a matched resonance's evidence weight comes from an interval that
actually holds its stated rate.

Absent this file the verifier still produces a verdict, on the σ basis, and each result's
`details.significance_basis` says which basis scored it. The weaker basis is reported, never
silently substituted.

## Measured coverage

Fitted at target 0.90 on a three-way molecule-level hash split of NMRShiftDB2
(train 39,628 / calibration 5,040 / evaluation 4,950 molecules — the calibration split is never
scored, the evaluation split is seen by neither the HOSE table nor the bands):

| nucleus | n      | empirical coverage | median half-width |
|---------|--------|--------------------|-------------------|
| ¹³C     | 36,844 | 0.9003             | 4.72 ppm          |
| ¹H      | 12,508 | 0.9061             | 0.397 ppm         |

`worst_deficit` is 0.0 — both nuclei meet or exceed the 0.90 guarantee, with no pooled fallback
and no atom left without an interval.

A target-0.95 fit was measured at the same time and **not** deployed: it undershoots on ¹³C
(0.9472, `worst_deficit` 0.0028) and its intervals are wider (median ¹³C half-width 6.23 ppm),
which makes the evidence weighting less discriminating while failing the rate it advertises.

## Re-deriving it

```
uv run python scripts/measure_conformal_calibration.py --out report.json
```

Needs the 284 MB NMReDATA export at `~/.cache/moltrace/nmrshiftdb2/nmrshiftdb2.nmredata.sd`.
Take `report.json`'s `conformal_90.calibration` verbatim. Never re-split a hash split: the
script cuts all three splits from one hash in a single pass, and the obvious two-call version
returns an empty calibration set.

## What this file contains

Twenty quantiles of the predictor's own residual distribution, binned by nucleus and predicted
σ. It carries no shift values, no structures and no records from NMRShiftDB2, and nothing of the
source database can be reconstructed from it — unlike `data/hose/`, which is a genuine
NMRShiftDB2 derivative and is gitignored for that reason.

`CALIBRATION_VERSION` and the content fingerprint are both checked on load: a file fitted by a
different procedure, or edited after fitting, is refused rather than used.
