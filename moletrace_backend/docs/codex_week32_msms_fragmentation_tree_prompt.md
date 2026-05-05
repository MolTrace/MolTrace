# Codex Prompt: Week 32 MS/MS Fragmentation-Tree + Diagnostic Neutral-Loss Reasoning

Goal: verify, harden, and polish the Week 32 processed MS/MS fragmentation-tree reasoning layer.

Do not add raw vendor LC-MS/MS parsing, mzML parsing, database search, generative unknown-compound proposals, or global UI redesign. Do not change the stable NMR stack, raw FID viewer, baseline/phase correction, HRMS layer, adduct/isotope layer, or processed MS/MS annotation beta unless a bug is directly caused by this tree layer.

Scientific rule: MS/MS fragmentation-tree evidence supports or weakens a candidate, but it does not prove final connectivity or stereochemistry. Final interpretation must combine HRMS, adduct/isotope evidence, 1H/13C/2D NMR, predicted NMR matching, and human review.

Endpoints:

```text
POST /ms/msms/fragmentation-tree
POST /ms/msms/fragmentation-tree/evidence
```

Focused verification:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/test_week32_fragmentation_tree.py \
  tests/test_week32_fragmentation_tree_ui.py \
  tests/test_week32_fragmentation_tree_api.py \
  tests/test_week31_adduct_isotope.py \
  tests/test_week31_adduct_ui.py \
  tests/test_week31_adduct_api.py \
  tests/test_week30_msms_annotation.py \
  tests/test_week30_msms_ui.py \
  tests/test_week30_msms_api.py \
  tests/test_week29_hrms_exact_mass.py \
  tests/test_week29_hrms_ui.py \
  tests/test_week29_hrms_api.py
```

Full verification:

```bash
PYTHONPATH=src uv run pytest -q
PYTHONPATH=src uv run python -m compileall src/nmrcheck
grep -R "fragmentation-tree\|Fragmentation-Tree\|MSMSFragmentation\|diagnostic_hits\|contradiction_flags" src/nmrcheck tests docs README.md || true
```
