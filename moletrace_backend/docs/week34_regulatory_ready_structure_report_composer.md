# Week 34: Regulatory-ready Structure Elucidation Report Composer

Week 34 turns the unified NMR/MS candidate-confidence result into a structured, audit-ready report.

The report composer is a governance layer, not a new detector. It consumes the Week 33 unified confidence output, or runs the Week 33 engine from a supplied unified request, and creates a human-reviewable record containing ranked candidates, evidence-layer coverage, contradictions, ambiguity alerts, missing evidence, source-file provenance, processing history, and release gates.

## New module

- `src/nmrcheck/regulatory_report.py`

## New endpoints

- `POST /reports/structure-elucidation/compose`
- `POST /reports/structure-elucidation/compose/evidence`
- `POST /reports/structure-elucidation/compose/html`

## New UI section

- `Regulatory-ready Structure Elucidation Report Composer`

Placement:

```text
Unified Candidate Confidence Engine
Regulatory-ready Structure Elucidation Report Composer
Processed spectrum upload
```

## Provenance hashes

The composed report includes SHA-256 hashes for:

- report request
- unified confidence result
- processing history
- final report payload
- rendered HTML report

## Release gates

- `requires_human_review`
- `approved_for_release`
- `blocked_by_contradictions`
- `insufficient_evidence`

## Report statuses

- `draft_requires_review`
- `review_ready`
- `approved_for_release`
- `blocked_by_contradictions`
- `insufficient_evidence`

## Limitations

This package does not add raw vendor MS parsing, mzML parsing, database dereplication, generative unknown-structure proposals, legally binding e-signature infrastructure, or validated GLP/GMP compliance. Those require separate validation and organization-specific SOPs.
