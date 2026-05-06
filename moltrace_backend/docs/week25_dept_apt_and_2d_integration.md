# Week 25: DEPT/APT Carbon-Type Evidence and 2D NMR Integration

## Scope

This release adds a dedicated DEPT/APT evidence layer for processed carbon-type peak tables and connects it to the existing 13C and 2D NMR evidence workflows.

No MS features, candidate ranking, raw 2D FID production processing, real-spectrum viewer redesign, or raw FID phase/baseline behavior changes are included.

## DEPT/APT Behavior

- DEPT-90 positive peaks support CH carbons. Missing, absent, or negative DEPT-90 peaks are not treated as definitive contradictions unless the user explicitly labels a carbon type.
- DEPT-135 negative peaks support CH2. Positive peaks support CH or CH3, but DEPT-135 alone does not separate CH from CH3.
- APT separates CH/CH3 from CH2/quaternary groups, but sign convention varies by processing. Assignments remain ambiguous unless the user supplies an explicit convention or explicit `carbon_type`.
- Quaternary carbons may be absent from DEPT spectra, so missing DEPT peaks are reported as review notes rather than fatal errors.

## Supported Models

The DEPT/APT layer uses:

- `DeptAptPeak`
- `DeptAptPreviewReport`
- `DeptAptAnalyzeResult`

Supported experiment labels are `DEPT90`, `DEPT135`, `DEPT`, `APT`, and `UNKNOWN`.

Supported carbon-type labels are `C`, `CH`, `CH2`, `CH3`, `CH_OR_CH3`, and `CH2_OR_C`.

## Supported Table Formats

CSV, TSV, and JSON peak tables are supported.

Shift aliases:

- `shift_ppm`
- `ppm`
- `shift`
- `delta`
- `carbon_ppm`
- `c_ppm`

Phase aliases:

- `phase`
- `sign`
- `polarity`
- `direction`

Carbon-type aliases:

- `carbon_type`
- `dept`
- `apt`
- `multiplicity`
- `attached_h`
- `type_label`

## Endpoints

New endpoints:

```text
POST /carbon13/dept/preview
POST /carbon13/dept/analyze
```

Updated endpoint:

```text
POST /nmr2d/analyze
```

The 2D endpoint now accepts optional `dept_apt_file`, `dept_apt_experiment_type`, and `apt_positive` form fields.

## 2D Integration

HSQC and HMQC use DEPT/APT as direct-attachment carbon-type cross-checks. A matched quaternary `C` label is flagged as a conflict because HSQC/HMQC correlations represent direct 1H-13C attachment evidence.

HMBC uses DEPT/APT only as contextual carbon-type evidence. Quaternary carbon correlations are valid HMBC long-range targets and are not treated as conflicts.

COSY ignores DEPT/APT evidence because it is a 1H-1H connectivity experiment.

## Reports and UI

Reports include DEPT/APT experiment type, typed peak count, type summary, matched 13C count, consistency score, APT convention warnings, HSQC/HMQC support/conflict counts, HMBC contextual counts, and human review status when DEPT/APT is used with 2D NMR.

The UI now presents DEPT/APT and processed 2D NMR together in the Analysis-tab DEPT/APT + 2D NMR Evidence Studio, immediately after the 13C section. The 1H, 13C, processed-spectrum, raw FID, phase/baseline, and viewer inputs are reused read-only and are not modified by DEPT/APT or 2D actions.

## Limitations

- DEPT/APT peak tables must already be processed; raw DEPT/APT FID processing is not implemented.
- APT sign convention must be confirmed by the user or treated as ambiguous.
- DEPT-135 positive peaks remain CH-or-CH3 evidence, not a definitive CH versus CH3 assignment.
- 2D NMR and DEPT/APT evidence remains supportive and requires human review.
