# Week 24.3: Auto Phase and Bernstein Baseline

## Raw FID Defaults

Raw Bruker and Varian/Agilent 1D FID processing defaults to:

```text
phase_mode=auto
baseline_correction=bernstein
baseline_order=3
display_mode=real
vertical_gain=1.0
debug_preview=false
```

Raw uploads are treated as immutable source data. The uploaded `.zip`,
`.tar.gz`, or `.tgz` archive is SHA-256 hashed, safety-inspected, stored in the
configured local raw data vault (`RAW_DATA_VAULT_DIR`, default
`raw_data_vault/`), and never overwritten by preview, analysis, phase
correction, baseline correction, referencing, peak picking, or report
generation. Processing artifacts are derivative metadata.

Processing order is:

```text
read raw FID
vendor correction / digital filter correction
apodization / zero filling
Fourier transform
phase correction
real spectrum extraction
Bernstein baseline correction
baseline QA
peak picking
real-spectrum viewer
```

Human review remains required before raw FID-derived interpretation is used in a
final report.

## Baseline Correction

Bernstein baseline correction normalizes the ppm/x axis to `t in [0, 1]`, fits
the Bernstein polynomial basis with order 3 by default, selects conservative
low-envelope baseline points to avoid obvious peaks, and uses
`numpy.linalg.lstsq` when NumPy is available. No SciPy dependency is required.

The correction returns corrected points, coefficients, baseline-point counts,
QA, and warnings. `preserve` and `none` modes keep intensities unchanged.

## Phase Correction

Automatic phase correction operates on the complex spectrum before real
extraction. It tries nmrglue `autops` ACME first, then peak-minima, then falls
back to an internal conservative grid search. Metadata records phase mode,
p0/p1, score, correction-applied status, solver, and warnings.

## Processed Spectra

Processed uploaded spectra are not baseline corrected by default:

```text
processed_baseline_correction=none
processed_baseline_order=3
```

If a reviewer explicitly selects processed-file Bernstein correction, the
corrected evidence trace is used and the metadata records that correction.

## Viewer Stability

The main viewer preserves real evidence intensity. Vertical gain only changes
the Plotly y-axis range. Reviewer marker actions and weak-peak/display toggles
update the existing Plotly instance instead of rebuilding the whole spectrum
preview, reducing blinking during review. `raw_preview_points` is omitted unless
`debug_preview=true`.

## Evidence Package

`GET /fid/runs/{run_id}/package` exports a zip evidence package containing:

- `analysis.json`
- `processing_metadata.json`
- `raw_upload_provenance.json`
- the original raw archive when its SHA-256 can be verified in immutable storage

If the raw archive is unavailable locally, the package includes a note and the
provenance JSON needed to verify the expected SHA-256/object key.
