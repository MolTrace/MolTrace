
# Week 21 Release Candidate Checklist

## Scientific regression checks

Run:

```bash
PYTHONPATH=src uv run pytest tests/test_week21_scientific_regression.py
```

These tests check:
- invalid SMILES fails validation
- malformed NMR text fails validation
- ethanol analysis remains consistent
- processed CSV peak picking finds more than solvent/water
- tobramycin peak table retains the expected reference peak count
- Bruker and Varian/Agilent raw FID zip detection works
- invalid and unsafe zip uploads fail safely

## Full regression suite

```bash
PYTHONPATH=src uv run pytest
```

## Local DB reset

```bash
PYTHONPATH=src python -m nmrcheck.cli reset-dev-db
```

This command only works for local SQLite databases.

## Release health

Admin endpoint:

```text
GET /admin/release-health
```

It reports:
- release version/stage
- startup issues
- database status
- Redis status
- FID optional dependency readiness
- supported raw FID vendors
- value dashboard metrics
- recommended smoke tests
