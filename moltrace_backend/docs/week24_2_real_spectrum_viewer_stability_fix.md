# Week 24.2: Real Spectrum Viewer Stability Fix

## Problem Fixed

The previous locked-display patch could make spectra look unrealistic by
applying display transformations such as fitted-baseline subtraction and signed
asinh compression to the plotted main trace. That made peaks look warped and
made gain changes feel like they were changing the underlying spectrum.

## Current Rule

The main spectrum plot always uses original evidence intensity values.

```text
preview_points = downsample(original_trace)
peak picking = original_trace
reports = original_trace
viewer gain = y-axis range only
```

## What Changed

- Locked/asinh display transforms are disabled by default.
- Deprecated `display_mode=locked` maps back to `real`.
- `raw_preview_points` is returned only when `debug_preview=true`.
- Downsampling uses min/max buckets to preserve narrow peaks.
- Viewer vertical gain changes only the y-axis range.
- Plotly uses `scattergl` for larger traces.
- Weak-peak magnifier data is optional display-only metadata/inset data and
  never replaces the main trace or peak-picking evidence.

## API Controls

Processed spectrum and raw FID routes default to:

```text
display_mode=real
vertical_gain=1.0
debug_preview=false
```

Optional weak-peak assistance:

```text
display_mode=magnifier
```

For compatibility, `display_mode=weak_peak_magnifier` is accepted as an alias
for `magnifier`.

## Scientific Rationale

Real NMR spectra can contain noise, solvent signals, impurities, overlap, and
field artifacts. The viewer preserves those features instead of forcing an
idealized trace. Interpretation and matching stay based on traceable spectral
evidence, not a transformed display layer.
