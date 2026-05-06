# Codex prompt — Week 37 LC-MS Feature Grouping + Blank Subtraction + RT Alignment

You are working on the SpectraCheck codebase. Implement and harden Week 37 without changing stable contracts from Weeks 21–36.

## Goal

Add a conservative LC-MS feature-table QC layer after Week 36 feature detection:

```text
LC-MS import bridge
→ feature detection + XIC + peak purity
→ feature grouping + blank subtraction + RT alignment
→ downstream HRMS/MS/MS/unified confidence/report workflows
```

## Required behavior

1. Preserve raw/source data immutability.
2. Use the existing `detect_lcms_features` function for per-run feature detection.
3. Accept sample, blank, QC, and reference roles.
4. Align retention times with a transparent shift value, not hidden warping.
5. Group features by m/z and aligned RT.
6. Report sample area, blank area, blank ratio, and blank-subtracted area.
7. Flag blank-like/background-like features instead of silently dropping them.
8. Annotate isotope/adduct/in-source-loss feature-family relationships as review hints only.
9. Preserve run SHA-256 hashes and settings for the report composer.
10. Add UI placement after Week 36 and before processed spectrum upload.

## Do not add yet

- proprietary vendor raw parsing;
- MS-Numpress decoding;
- full chromatographic deconvolution/warping;
- retention-index calibration;
- database/library search;
- generative unknown-compound proposals;
- global UI redesign.

## Tests to run

```bash
PYTHONPATH=src uv run pytest -q \
  tests/test_week37_lcms_feature_grouping.py \
  tests/test_week37_lcms_grouping_ui.py \
  tests/test_week37_lcms_grouping_api.py \
  tests/test_week36_lcms_feature_detection.py \
  tests/test_week36_lcms_feature_ui.py \
  tests/test_week35_lcms_import_bridge.py \
  tests/test_week35_lcms_ui.py
```

Then run full tests and compile:

```bash
PYTHONPATH=src uv run pytest -q
PYTHONPATH=src uv run python -m compileall src/nmrcheck
```

## Acceptance criteria

- The new endpoints return grouped feature tables with alignment summaries.
- Blank-like features are explicitly labelled.
- Sample-enriched features are preserved for downstream scoring.
- UI placement is stable.
- The existing Week 35 and Week 36 tests still pass.
