# Week 26: Candidate Comparison Engine

## Purpose

This layer compares multiple proposed structures against the same NMR evidence stack.

Supported evidence layers:

- 1H NMR text
- 13C NMR text
- optional DEPT/APT peak table
- optional processed 2D NMR peak table

## Endpoints

```text
POST /candidates/compare
POST /candidates/compare/evidence
```

`/candidates/compare` accepts JSON candidates and text evidence. `/candidates/compare/evidence` accepts multipart form data so the same candidate list can include selected DEPT/APT and 2D files.

## Candidate Input Format

```text
Proposed product | CCO | proposed
Starting material | CO | starting material
Side product | CCCO | impurity
```

## Scoring

The score is transparent and heuristic. It combines:

- structure parse validity
- 1H evidence score
- 13C evidence score
- DEPT/APT consistency score when supplied
- 2D NMR evidence score when supplied

Structure validity alone is capped as weak support. The engine reports ranked candidates, score breakdowns, contradictions, ambiguity alerts, and human-review notes.

## Limitations

Candidate comparison is evidence ranking, not final structure confirmation. DEPT/APT and 2D evidence are currently global support layers; future work should add atom-level predicted shifts and graph-level assignment matching.
