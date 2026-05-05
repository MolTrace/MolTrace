# Week 27: Spectral Similarity Scoring

## Purpose

This layer adds spectral similarity scoring across:

- 1H NMR
- 13C NMR
- processed 2D NMR peak tables: COSY, HSQC, HMQC, HMBC

It supports comparing an observed spectrum against a reference, prediction, literature spectrum, previous run, or candidate-specific simulated spectrum.

## Methods

### 1H NMR

- vector similarity using Gaussian-smoothed chemical-shift vectors
- set similarity using greedy Gaussian peak matching
- integrations are represented by repeated shifts in the set score

### 13C NMR

- chemical-shift-only vector similarity
- chemical-shift set matching
- intensities are not treated as quantitative carbon counts

### 2D NMR

- cross-peak set matching
- COSY uses 1H/1H tolerances
- HSQC/HMQC/HMBC use 1H/13C tolerances
- near-diagonal COSY peaks are excluded from connectivity similarity

## Endpoints

```text
POST /similarity/score
POST /similarity/score/evidence
```

## UI

The Analysis tab includes:

```text
Spectral Similarity Scoring
```

It appears after Candidate Comparison and before Processed spectrum upload.

## Limitations

This is a transparent confidence aid and ranking signal, not a full forward-prediction engine and not final structure confirmation. Predicted spectra can be supplied later by a candidate-specific prediction module.
