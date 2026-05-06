# Week 33: Unified Candidate Confidence Engine

Week 33 adds the first unified decision layer for SpectraCheck/NMRCheck. It combines the current orthogonal evidence streams into one transparent candidate ranking:

- candidate-specific predicted NMR
- HRMS exact mass
- MS1 adduct/isotope inference
- processed MS/MS annotation
- MS/MS fragmentation-tree reasoning

The module does not replace the individual evidence engines. It calls them through their existing request/response contracts, reads their outputs, and reports agreement, missing layers, contradictions, ambiguity, and reviewer priorities.

## New module

- `src/nmrcheck/unified_confidence.py`

## New endpoints

- `POST /confidence/candidates/unified`
- `POST /confidence/candidates/unified/evidence`

## New UI section

- `Unified Candidate Confidence Engine`

Placement:

```text
MS/MS Fragmentation-Tree + Diagnostic Neutral-Loss Reasoning
Unified Candidate Confidence Engine
Processed spectrum upload
```

## Scoring

Default layer weights:

- candidate-specific predicted NMR: `0.36`
- HRMS exact mass: `0.20`
- MS1 adduct/isotope inference: `0.10`
- processed MS/MS annotation: `0.16`
- MS/MS fragmentation tree: `0.18`

Scores are normalized over available layers. Agreement across independent layers adds a small boost; contradiction flags and sparse evidence reduce confidence.

## Candidate labels

- `high_confidence_candidate`
- `moderate_confidence_candidate`
- `low_confidence_candidate`
- `conflicting_evidence`
- `insufficient_evidence`
- `invalid_structure`

## Important limitation

The confidence score is a transparent decision-support score. It is not proof of identity and is not a calibrated DP4/DP5 probability. Human review is required, especially when evidence streams disagree or top candidates are close.

## Stable-state protection

This layer is additive and should not alter raw FID preservation, the real-spectrum viewer, auto-phase, Bernstein baseline correction, 1H/13C evidence, DEPT/APT, 2D NMR, HRMS, MS1 adduct inference, processed MS/MS annotation, fragmentation-tree reasoning, authentication, admin, review, audit, or report flows.
