# Codex prompt — Week 39 LC-MS Consensus → Unified Candidate Confidence Bridge

You are hardening the Week 39 SpectraCheck/NMRCheck layer.

## Goal

Connect Week 38 LC-MS feature-family consensus evidence into unified candidate confidence and regulatory-ready reports without making autonomous identity claims.

## Files to inspect

- `src/nmrcheck/lcms_confidence_bridge.py`
- `src/nmrcheck/unified_confidence.py`
- `src/nmrcheck/regulatory_report.py`
- `src/nmrcheck/models.py`
- `src/nmrcheck/api.py`
- `src/nmrcheck/web.py`
- `tests/test_week39_lcms_confidence_bridge.py`
- `tests/test_week39_lcms_bridge_ui.py`
- `tests/test_week39_lcms_bridge_api.py`

## Required behavior

- Accept a full Week 38 consensus result, a Week 38 consensus request, or Week 38 family table text.
- Score candidate theoretical adduct m/z against eligible feature-family anchors.
- Treat promoted LC-MS feature families as candidate-supporting evidence only.
- Mark candidate-level contradictions when promoted family m/z/adduct evidence does not match a candidate.
- Preserve family table/result provenance and bridge hashes in report output.
- Keep all score components transparent and inspectable.

## Do not add yet

- proprietary vendor raw parsing
- MS-Numpress decoding
- retention-index prediction
- ion mobility / CCS scoring
- full isotope convolution
- database/library search
- generative unknown-compound proposal
- nonlinear RT warping
- DIA deconvolution
- autonomous candidate identity claims
- automatic regulatory approval

## Test command

```bash
PYTHONPATH=src pytest -q \
  tests/test_week39_lcms_confidence_bridge.py \
  tests/test_week39_lcms_bridge_ui.py \
  tests/test_week39_lcms_bridge_api.py \
  tests/test_week38_lcms_feature_family_consensus.py \
  tests/test_week33_unified_confidence.py \
  tests/test_week34_regulatory_report.py
```

API tests require the web/API dependencies, including SQLAlchemy.
