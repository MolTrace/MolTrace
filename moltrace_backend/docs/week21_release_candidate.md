
# Week 21 Release Candidate Checklist

## Scientific regression checks

Run:

```bash
PYTHONPATH=src uv run pytest tests/test_week21_scientific_regression.py
```

These tests check:
- invalid SMILES fails validation
- malformed NMR text fails validation
- ethanol analysis remains consistent
- processed CSV peak picking finds more than solvent/water
- tobramycin peak table retains the expected reference peak count
- Bruker and Varian/Agilent raw FID zip detection works
- invalid and unsafe zip uploads fail safely

## Full regression suite

```bash
PYTHONPATH=src uv run pytest
```

## Raw FID Prompt sidecar smoke

```bash
PYTHONPATH=src uv run moltrace-raw-fid-sidecar-report --limit 1 --no-include-varian --quiet --smoke
```

This smoke check verifies that the Prompt 1/2 Bruker/Varian FID reader,
phase, and baseline fixture report remains diagnostic-only: hidden metadata,
legacy visible pipeline unchanged, and no activation of the sidecar output.
Scientific fixture rows may still require review without failing this smoke
check.

## Cross-stack Prompt sidecar guardrails

```bash
./scripts/run_prompt_sidecar_guardrails.sh
```

This release gate runs the backend raw-FID API/vault metadata-only tests and
the frontend SpectraCheck Prompt sidecar visibility tests together. It protects
the current rule that Prompt 1/2 output may be shown as QA metadata only and
must not drive plotted points, peak markers, phase correction, baseline
correction, legends, or processed-spectrum behavior without a separate manual
promotion phase.

The manual promotion policy is defined in
`docs/raw_fid_prompt_manual_promotion_design.md`.

## Raw FID Prompt manual-promotion gate diagnostic

CI also runs a separate non-blocking manual-promotion gate diagnostic:

```bash
PYTHONPATH=src uv run moltrace-raw-fid-sidecar-report \
  --limit 20 \
  --include-varian \
  --quiet \
  --promotion-gate \
  --output-dir reports/raw_fid_prompt_manual_promotion_gate
```

The GitHub Actions step uses `if: always()` and `continue-on-error: true`, then
uploads the JSON/CSV report as the `raw-fid-prompt-manual-promotion-gate`
artifact. This report is a promotion checklist only. It may show
`review_required` while the build still passes, and it must keep
`activation_allowed=false` until a separate manual promotion is designed and
reviewed.

The manual-promotion gate currently covers:
- Prompt sidecar availability
- peak-count agreement with fixture references
- ppm-axis endpoint agreement within 0.01 ppm
- phase-angle delta within 5 degrees
- expected baseline method by nucleus
- deterministic fingerprint hash presence
- runtime target within 3000 ms per fixture
- no runtime activation from fixture diagnostics

## Raw FID Prompt provenance checksum artifact

CI uploads a second non-blocking audit artifact:

```bash
PYTHONPATH=src uv run moltrace-raw-fid-sidecar-report \
  --limit 20 \
  --include-varian \
  --quiet \
  --output-dir reports/raw_fid_prompt_provenance_checksums
```

The artifact is named `raw-fid-prompt-provenance-checksums`. It contains the
fixture report JSON/CSV, plus `raw_fid_prompt_sidecar_provenance_checksums.json`
and `raw_fid_prompt_sidecar_provenance_checksums.csv` with report-export hashes,
fixture archive hashes, and the provenance fingerprints used for audit trails.

## Raw FID Prompt shadow comparison artifact

CI uploads a third non-blocking review artifact:

```bash
PYTHONPATH=src uv run moltrace-raw-fid-sidecar-report \
  --limit 20 \
  --include-varian \
  --quiet \
  --output-dir reports/raw_fid_prompt_shadow_comparison
```

The artifact is named `raw-fid-prompt-shadow-comparison`. It contains only
`raw_fid_prompt_shadow_comparison_summary.json` and
`raw_fid_prompt_shadow_comparison_summary.csv`, a compact summary of Prompt
1/2 sidecar-vs-legacy fixture deltas for release review.

This artifact is read-only release evidence. It must not be interpreted as
runtime activation, and it must keep `runtime_activation_allowed=false`.
Promotion remains blocked until a separate manual runtime promotion is
implemented, reviewed, and protected by the guardrail suite.

## Raw FID Prompt release readiness artifact

CI uploads one reviewer-facing markdown summary that combines the manual
promotion gate, provenance hashes, shadow-comparison status, summary counts,
runtime-effect policy, and a compact fixture snapshot:

```bash
PYTHONPATH=src uv run moltrace-raw-fid-sidecar-report \
  --limit 20 \
  --include-varian \
  --quiet \
  --output-dir reports/raw_fid_prompt_release_readiness
```

The artifact is named `raw-fid-prompt-release-readiness`. It contains
`raw_fid_prompt_release_readiness.md` only. This file is intended for release
reviewers who need a single readable Prompt 1/2 readiness page without opening
the JSON/CSV diagnostics.

This artifact is read-only release evidence. It must not be interpreted as
runtime activation, and it must keep `runtime_activation_allowed=false`.
Promotion remains blocked until a separate manual runtime promotion is
implemented, reviewed, and protected by the guardrail suite.

## Release-health sidecar contract

The `/admin/release-health` `raw_fid_prompt_sidecar_smoke` payload is a shared
contract between backend diagnostics, CI release checks, and the frontend
Deployment Settings health panel. Keep the contract fixture at
`tests/contracts/release-health/raw_fid_prompt_sidecar_smoke.v1.json` in sync
with backend and frontend tests before renaming or removing fields.

Required top-level fields include `status`, `policy`,
`active_visible_pipeline`, `prompt_pipeline_active`, `failure_scope`,
`ci_command`, `admin_report_endpoint`, `manual_promotion_gate`,
`provenance_checksum_artifact`, `shadow_comparison_artifact`,
`release_readiness_artifact`, and `runtime_effect`.

This contract is reporting-only. It must continue to state that the active
visible pipeline is `legacy`, Prompt 1/2 is inactive for runtime spectra, and
processed spectrum behavior remains untouched until a later manual promotion
phase explicitly changes that policy.

## Local DB reset

```bash
PYTHONPATH=src python -m nmrcheck.cli reset-dev-db
```

This command only works for local SQLite databases.

## Release health

Admin endpoint:

```text
GET /admin/release-health
```

It reports:
- release version/stage
- startup issues
- database status
- Redis status
- FID optional dependency readiness
- supported raw FID vendors
- value dashboard metrics
- recommended smoke tests
- raw FID Prompt sidecar reporting-only smoke status
- raw FID Prompt manual-promotion gate metadata, including the non-blocking CI
  artifact name and command, while keeping runtime activation disabled
- raw FID Prompt provenance checksum artifact metadata for fixture/report audit
  trails
- raw FID Prompt shadow comparison artifact metadata for compact release review
  while keeping runtime activation disabled
- raw FID Prompt release readiness markdown artifact metadata for one-page
  review of gate, provenance, and shadow-comparison status
- raw FID Prompt activation-readiness policy remains reporting-only; detailed
  readiness gates are emitted by the CI artifact and admin fixture report
