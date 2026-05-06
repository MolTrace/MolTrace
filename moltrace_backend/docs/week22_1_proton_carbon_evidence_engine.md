# Week 22.1: ¹H + ¹³C Spectral Evidence Engine

This package refactors the Week 22 carbon-13 MVP into a more general evidence-first layer for both proton and carbon NMR.

## Why this exists

Recent NMR structure-elucidation methods emphasize standardized peak-level evidence, robust chemical-shift matching, solvent/impurity handling, and human-reviewable confidence rather than rigid exact matching. This package moves NMRCheck in that direction.

## New modules

- `nmr_tables.py`: shared ¹H/¹³C solvent, water, impurity, and chemical-region windows.
- `evidence.py`: dependency-free spectral evidence scoring utilities.
- `proton.py`: ¹H evidence engine.
- rebuilt `carbon13.py`: richer ¹³C evidence engine.

## New/updated endpoints

- `POST /proton/evidence`
- `POST /carbon13/evidence`
- existing `POST /carbon13/validate`
- existing `POST /carbon13/analyze`
- existing `POST /carbon13/upload`

## ¹H evidence features

- Parses realistic ¹H NMR text.
- Classifies each peak by region.
- Flags solvent/water-region peaks.
- Compares total integration and non-solvent integration against SMILES-derived H counts.
- Accounts for labile/exchangeable hydrogens.
- Produces an overall ¹H evidence score.

## ¹³C evidence features

- Parses ¹³C NMR text and CSV/TSV/JSON peak tables.
- Flags likely solvent carbon signals.
- Classifies carbon chemical-shift regions.
- Computes expected carbon environment summary from SMILES.
- Supports optional DEPT/APT-like carbon type labels: `C`, `CH`, `CH2`, `CH3`.
- Produces carbon count, region, solvent exclusion, DEPT/APT, and overall ¹³C evidence scores.

## Development notes

Run focused tests:

```bash
PYTHONPATH=src pytest -q tests/test_week22_1_proton_carbon_evidence.py tests/test_week22_carbon13.py
```

Run full app after dependencies are installed:

```bash
uv sync --extra dev --extra fid
PYTHONPATH=src uv run uvicorn nmrcheck.web:app --reload
```
