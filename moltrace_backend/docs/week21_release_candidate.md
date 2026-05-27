
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

## Cross-stack release-health contract guardrails

```bash
./scripts/run_release_health_contract_guardrails.sh
```

This release gate runs the backend release-health contract regression together
with the frontend release-health parser and Deployment Settings rendering tests.
It protects the shared `/admin/release-health` diagnostic contract so new CI
artifacts stay synchronized between backend payloads, the frontend parser, and
the admin UI. It remains a reporting-only guardrail and does not change
SpectraCheck spectra, raw-FID processing, processed-spectrum behavior, or
runtime Prompt 1/2 activation.

## Reviewer guardrail workflow

Run this workflow whenever a change touches raw-FID Prompt 1/2 diagnostics,
release-health payloads, Deployment Settings health rendering, CI artifact
names, or the Week 21 release checklist itself:

```bash
./scripts/run_prompt_sidecar_guardrails.sh
./scripts/run_release_health_contract_guardrails.sh
```

The Prompt sidecar guardrail protects SpectraCheck behavior: Prompt 1/2
diagnostics may remain available as hidden or admin-visible QA metadata, but
they must not change plotted spectra, peak markers, phase correction, baseline
correction, legends, processed-spectrum analysis, or raw-FID runtime output.

The release-health guardrail protects the admin/reporting contract: backend
payload fields, frontend parsing, and Deployment Settings display must stay in
sync whenever diagnostic artifacts evolve.

Treat failures as follows:
- Prompt sidecar failure: stop the release review until the diagnostic change is
  proven metadata-only or a separate manual runtime-promotion phase is opened.
- Release-health failure: update the backend contract, frontend parser, tests,
  and docs together so `/admin/release-health` remains coherent.
- Scientific or spectrum-rendering failure: do not patch around it in this
  checklist; fix the affected SpectraCheck regression in the owning test suite.

Passing this workflow does not activate Prompt 1/2 for runtime spectra. It only
confirms the current reporting-only boundary is intact.

## CI artifacts map

Use this map during release review before opening the detailed artifact
sections below:

| Artifact | Open this when | Primary files | Release decision |
| --- | --- | --- | --- |
| `raw-fid-prompt-release-readiness` | You need the fastest one-page Prompt 1/2 readiness summary. | `raw_fid_prompt_release_readiness.md` | Reviewer-facing summary only; runtime activation stays blocked. |
| `raw-fid-prompt-shadow-comparison` | You need sidecar-vs-legacy fixture deltas. | `raw_fid_prompt_shadow_comparison_summary.json`, `raw_fid_prompt_shadow_comparison_summary.csv` | Read-only comparison evidence; do not use it to drive plotted spectra. |
| `raw-fid-prompt-provenance-checksums` | You need fixture/report hashes for audit trails. | `raw_fid_prompt_sidecar_provenance_checksums.json`, `raw_fid_prompt_sidecar_provenance_checksums.csv` | Audit evidence only; investigate hash drift before release. |
| `raw-fid-prompt-manual-promotion-gate` | You need the detailed manual-promotion gate diagnostics. | Raw FID Prompt JSON/CSV fixture reports. | May show `review_required` without failing CI; `activation_allowed=false` must remain in effect. |

All four artifacts are diagnostic release evidence. None of them may activate
Prompt 1/2 for SpectraCheck runtime spectra, raw-FID plotting, processed
analysis, peak markers, legends, phase correction, or baseline correction.

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
