# Codex Prompt: Week 34 Regulatory-ready Structure Elucidation Report Composer

Goal: verify, harden, and polish the regulatory-ready structure elucidation report composer.

Do not add new structure elucidation detectors, raw vendor MS parsing, mzML parsing, generative unknown-structure proposals, or global UI redesigns. Do not change raw FID processing, real-spectrum viewing, baseline correction, auto phase, 1H/13C evidence, DEPT/APT, 2D NMR, HRMS, adduct inference, MS/MS annotation, fragmentation-tree reasoning, or unified confidence unless a bug is directly caused by the report composer.

Scientific/product rule: this module is a governance and report-composition layer. It must not claim autonomous regulatory approval. It should create an audit-ready, human-reviewable structure elucidation record with provenance hashes, evidence summaries, contradictions, missing evidence, and an explicit release gate.

Endpoints to verify:

- `POST /reports/structure-elucidation/compose`
- `POST /reports/structure-elucidation/compose/evidence`
- `POST /reports/structure-elucidation/compose/html`

Focused tests:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/test_week34_regulatory_report.py \
  tests/test_week34_report_ui.py \
  tests/test_week34_report_api.py \
  tests/test_week33_unified_confidence.py \
  tests/test_week33_unified_ui.py \
  tests/test_week32_fragmentation_tree.py \
  tests/test_week32_fragmentation_tree_ui.py \
  tests/test_week31_adduct_isotope.py \
  tests/test_week31_adduct_ui.py \
  tests/test_week30_msms_annotation.py \
  tests/test_week30_msms_ui.py \
  tests/test_week29_hrms_exact_mass.py \
  tests/test_week29_hrms_ui.py
```
