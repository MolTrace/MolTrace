# Week 29: HRMS / Exact-Mass Constraint Layer

## Purpose

Week 29 adds the first mass-spectrometry constraint layer.

The goal is not full LC-MS/MS annotation yet. The goal is a stable bridge between NMR evidence, candidate-specific predicted NMR, and HRMS exact mass.

This layer constrains candidate structures using:

- observed HRMS m/z
- adduct and ion mode
- ppm error
- neutral formula
- DBE / IHD
- approximate M+1 / M+2 isotope hints
- candidate SMILES exact masses

## New Module

```text
src/nmrcheck/hrms.py
```

## New Endpoints

```text
POST /ms/hrms/candidates/match
POST /ms/hrms/candidates/match/evidence
POST /ms/hrms/formulas/search
```

## New UI Section

```text
HRMS / Exact-Mass Constraint Layer
```

It appears in the Analysis tab after Candidate-specific Predicted NMR Matching and before Processed spectrum upload.

## Supported Adducts

```text
[M+H]+
[M+Na]+
[M+K]+
[M+NH4]+
[M-H]-
[M+Cl]-
[M+FA-H]-
[M+Ac-H]-
M
```

## Why This Layer Comes Before MS/MS

Exact mass and formula constraints are a safe first MS layer. They are easier to validate than full MS/MS structural annotation and immediately improve candidate review by ruling formulas/candidates in or out by ppm error and isotope hints.

## Literature-Driven Design Takeaways

- Exact mass from HRMS can determine or strongly constrain elemental composition for small molecules.
- Isotope patterns, especially chlorine and bromine M+2 behavior, are useful formula sanity checks.
- NMR-Solver-style workflows benefit from candidate ranking and interpretable spectral matching, while HRMS provides an orthogonal formula filter.
- Modern MS workflows have raw-data access and metadata-fragmentation challenges, so this package starts with auditable text/form-data HRMS evidence.
- Defensive programming and current-state guards are required so MS additions do not destabilize NMR processing and viewing.

## Limitations

This is not full MS/MS annotation. It does not yet:

- parse raw mzML/vendor MS files;
- perform chromatographic peak detection;
- infer adducts automatically from full spectra;
- generate fragmentation trees;
- perform database search;
- predict MS/MS fragments.
