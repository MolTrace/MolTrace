# Week 31: Adduct + Isotope Pattern Inference Layer

## Purpose

Week 31 adds a processed MS1 / HRMS interpretation layer between exact-mass matching and processed MS/MS annotation.

The layer infers:

- isotope clusters;
- likely charge state;
- M+1 and M+2 relative isotope percentages;
- rough carbon-count estimate from M+1 intensity;
- chlorine-, bromine-, sulfur-, and silicon-like M+2 signatures;
- paired adduct peaks for the same neutral mass;
- likely precursor adduct hypotheses;
- bounded formula candidates per adduct.

## New Module

```text
src/nmrcheck/adduct_inference.py
```

## New Endpoints

```text
POST /ms/adducts/infer
POST /ms/adducts/infer/evidence
```

## UI Placement

```text
HRMS / Exact-Mass Constraint Layer
Adduct + Isotope Pattern Inference
Processed MS/MS Annotation Beta
Processed spectrum upload
```

## Input

Use processed centroid MS1/HRMS peak tables:

```text
m/z,intensity
47.04914,100
48.05249,2.3
69.03109,24
```

CSV, TSV, and whitespace rows are accepted. Use the Week 35 LC-MS/MS import bridge to extract peak-list views from mzML/mzXML or source files.

## Scientific Design

Adduct and isotope inference is a triage layer. It can propose plausible ion assignments, isotope signatures, and formula candidates, but it does not prove molecular identity. Use it with HRMS exact mass, MS/MS fragments, NMR evidence, and human review.

## Stable-State Rule

This layer is additive and must not alter:

- real-spectrum viewer;
- raw FID processing;
- auto-phase;
- Bernstein baseline correction;
- 1H evidence;
- 13C evidence;
- DEPT/APT;
- 2D NMR;
- candidate comparison;
- spectral similarity;
- candidate-specific predicted NMR;
- HRMS exact-mass candidate matching;
- processed MS/MS annotation;
- authentication/admin flows.

## New Tests

```text
tests/test_week31_adduct_isotope.py
tests/test_week31_adduct_ui.py
tests/test_week31_adduct_api.py
```
