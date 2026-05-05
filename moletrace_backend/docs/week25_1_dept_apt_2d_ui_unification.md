# Week 25.1: Unified DEPT/APT + 2D NMR Evidence Studio UI

## Purpose

DEPT/APT and 2D NMR now share one evidence studio inside the Analysis tab, immediately after the 13C NMR section and before processed spectrum upload.

## UX Rule

These evidence layers are interpreted together:

- DEPT/APT provides carbon-type evidence.
- COSY provides 1H-1H connectivity evidence.
- HSQC/HMQC provides direct 1H-13C attachment evidence.
- HMBC provides long-range 1H-13C connectivity evidence.

The UI explicitly states that DEPT/APT and 2D NMR evidence are supportive connectivity evidence and require human review.

## UI Behavior

The studio has two side-by-side panels:

1. DEPT / APT carbon-type evidence
2. 2D correlation evidence

DEPT/APT can be previewed or analyzed independently. 2D NMR can be previewed independently, or analyzed with the selected DEPT/APT file attached as optional carbon-type context.

HSQC/HMQC can use DEPT/APT to flag support or conflict. HMBC uses DEPT/APT as contextual evidence only, because quaternary carbon correlations can be valid long-range HMBC targets.

## Guardrails

This UI pass does not add scientific modules, MS features, candidate ranking, raw FID processing, auto-phase changes, Bernstein baseline changes, or real-spectrum viewer behavior changes.
