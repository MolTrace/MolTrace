# Week 28: Candidate-Specific Predicted NMR Matching + Mobile UI

## Purpose

Week 28 adds a candidate-specific predicted NMR matching layer and improves mobile usability in the analysis workspace.

The new layer predicts approximate 1H, 13C, and direct HSQC-style C-H correlations for each candidate SMILES and compares those predictions with observed evidence.

## New modules

```text
src/nmrcheck/nmr_prediction.py
src/nmrcheck/candidate_predicted.py
```

## New endpoints

```text
POST /prediction/nmr/preview
POST /prediction/nmr/match
POST /prediction/nmr/match/evidence
```

## New UI section

```text
Candidate-specific Predicted NMR Matching
```

The section appears in the Analysis tab after Spectral Similarity Scoring and before Processed spectrum upload.

## Prediction status

The bundled predictor is a transparent RDKit atom-environment heuristic. It is useful for beta testing the API, UI, and scoring workflow, but it is not a replacement for production-grade ML/DFT prediction.

Future upgrades can add external predictors while preserving the current API contract.

## Scoring

The matcher currently supports:

- observed 1H text vs predicted candidate 1H shifts
- observed 13C text vs predicted candidate 13C shifts
- observed HSQC/HMQC-like 2D cross-peaks vs predicted direct C-H cross-peaks

Results include:

- ranked candidates
- score breakdowns
- predicted shifts
- contradictions
- ambiguity alerts
- reviewer notes

## Mobile UI improvements

The app now has additional responsive CSS for phones:

- sticky, horizontally scrollable navigation
- single-column analysis panels
- full-width buttons
- mobile-safe 16px form inputs
- horizontally scrollable tables
- tighter cards and metrics
- smaller spectrum controls

## Stable-state rule

This package is additive. It should not alter:

- real-spectrum viewer
- raw FID processing
- auto-phase
- Bernstein baseline correction
- 1H evidence
- 13C evidence
- DEPT/APT
- 2D NMR evidence
- spectral similarity
- candidate comparison
