# Codex handoff — Week 38 LC-MS feature-family consensus

You are hardening Week 38 of SpectraCheck/NMRCheck.

## Goal

Improve `src/nmrcheck/lcms_consensus.py`, the API routes, and the UI section without changing the core scope.

Week 38 should score Week 37 grouped LC-MS features into feature-family-level consensus evidence using:

- blank-subtraction / background gates
- peak-purity support
- approximate isotope-envelope agreement
- adduct-pair consistency
- in-source-loss relationships
- MS/MS precursor linkage

## Do not add

Do not add any of the following in this hardening pass:

- proprietary vendor raw parsing
- MS-Numpress decoding
- full isotope convolution engine
- retention-index prediction
- nonlinear chromatographic warping
- database/library search
- generative unknown-compound proposal
- DIA deconvolution
- ion mobility / CCS scoring
- global UI redesign
- black-box identity claims

## Preserve behavior

Keep the module conservative:

- promoted feature family means “ready for downstream candidate scoring after human review”
- promoted feature family does not mean molecular identity proof
- blank-like/background-like anchors must fail or require review
- isotope/adduct/loss evidence must remain interpretable
- all outputs need evidence summaries and warnings

## Tests to preserve

Keep these focused tests passing:

```text
tests/test_week38_lcms_feature_family_consensus.py
tests/test_week38_lcms_consensus_ui.py
tests/test_week38_lcms_consensus_api.py
```

Also run recent LC-MS regressions:

```text
tests/test_week37_lcms_feature_grouping.py
tests/test_week37_lcms_grouping_ui.py
tests/test_week36_lcms_feature_detection.py
tests/test_week36_lcms_feature_ui.py
tests/test_week35_lcms_import_bridge.py
```

## Suggested hardening tasks

1. Add richer unit tests for chlorine/bromine formulas where M+2 is prominent.
2. Add more edge-case tests for feature-table parsing.
3. Improve adduct-pair role naming when the anchor is not `[M+H]+`.
4. Add optional reviewer override metadata, but do not silently override contradictions.
5. Improve UI copy-to-report provenance so the exact settings are copied with the table.
6. Add structured export for promoted feature families for future unified-confidence integration.

## Acceptance criteria

- API contract remains stable.
- UI section remains after Week 37 and before processed spectrum upload.
- Full grouped result, explicit groups, and feature-table text all work.
- No raw data mutation.
- No identity proof language.
- Human review remains explicit.
