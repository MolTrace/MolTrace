# Week 25: Guarded 2D NMR Evidence Engine

This release adds a protected 2D NMR evidence layer without changing the stable
1D/FID pipeline.

## Protection Harness

- 2D support is behind `ENABLE_2D_NMR`.
- Processed-table contour preview is separately guarded by
  `ENABLE_2D_CONTOUR_PREVIEW`.
- Raw 2D FID/SER beta access is separately guarded by
  `ENABLE_RAW_2D_FID_BETA` and defaults to off.
- Existing ¹H, ¹³C, processed spectrum, raw FID, viewer, report, and review
  outputs are covered by regression tests.
- The database change is additive: a separate `nmr2d_runs` table stores 2D
  reports and review status.
- 2D parser, analyzer, routes, models, UI, and tests live in separate modules.

## Supported Inputs

Processed peak tables are supported for:

- COSY: ¹H-¹H scalar connectivity evidence.
- HSQC / HMQC: direct ¹H-¹³C attachment evidence.
- HMBC: long-range ¹H-¹³C connectivity evidence.

Accepted formats are `.csv`, `.tsv`, and `.json`. Common columns such as
`f1`, `f2`, `h1_ppm`, `h2_ppm`, `proton_ppm`, `carbon_ppm`, `intensity`, and
`assignment` are recognized. When intensity values are present, an optional
lightweight contour preview can be returned.

## Endpoints

- `GET /nmr2d/status`
- `POST /nmr2d/preview`
- `POST /nmr2d/analyze`
- `GET /nmr2d/runs/{run_id}`
- `GET /nmr2d/runs/{run_id}/report`
- `POST /nmr2d/raw/preview`

The raw 2D route is a guarded stub. Raw 2D FID/SER processing is intentionally
deferred.

When `ENABLE_2D_NMR=false`, protected 2D endpoints return a clear feature-flag
error and the UI hides the 2D navigation and section. Local development defaults
to `ENABLE_2D_NMR=true`; deployment examples may explicitly set it according to
release policy.

## Evidence Model

2D cross-peaks are scored as supporting evidence only. The analyzer links
cross-peaks to the current ¹H and ¹³C text context when provided, summarizes
experiment diversity, checks rough structure consistency, and requires human
review for final interpretation.

The engine does not claim final automated assignment, does not use 13C
intensity as carbon-count evidence, and does not modify existing 1D evidence
traces.

## UI

When `ENABLE_2D_NMR=true`, the dashboard shows a separate "2D NMR" section
with:

- processed 2D peak-table upload
- experiment selector
- optional contour preview
- preview and analyze actions
- a raw 2D status action explaining the guarded stub

When the feature flag is off, the UI section and navigation entry remain hidden.
When `ENABLE_2D_CONTOUR_PREVIEW=false`, the contour checkbox is disabled. When
`ENABLE_RAW_2D_FID_BETA=false`, the raw 2D status action is disabled and the API
returns a clear beta-disabled response.

## Limitations

- Raw 2D FID/SER production processing is not included.
- Contour preview is generated only from processed table points with intensity.
- Correlation scoring is evidence-supportive and must be reviewed by a chemist.
