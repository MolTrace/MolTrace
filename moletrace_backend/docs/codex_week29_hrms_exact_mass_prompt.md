# Codex Week 29 Prompt: HRMS / Exact-Mass Constraint Layer

Goal: verify, harden, and polish the HRMS exact-mass constraint layer.

Do not add full MS/MS annotation, raw LC-MS vendor parsing, reaction optimization, regulatory features, or global UI redesign. Do not alter raw FID processing, auto-phase, Bernstein baseline correction, real-spectrum viewer behavior, 1H evidence, 13C evidence, DEPT/APT, 2D evidence, candidate comparison, spectral similarity, candidate-specific predicted NMR, authentication/admin flows, or review/audit/report flows.

Scientific rule: HRMS exact mass is an orthogonal constraint layer. It can rule formulas/candidates in or out by ppm error, adduct, isotope hints, and DBE/IHD, but it does not prove connectivity or stereochemistry. It must be combined with NMR evidence and human review.

Required endpoints:

```text
POST /ms/hrms/candidates/match
POST /ms/hrms/candidates/match/evidence
POST /ms/hrms/formulas/search
```

Focused verification:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/test_week29_hrms_exact_mass.py \
  tests/test_week29_hrms_ui.py \
  tests/test_week29_hrms_api.py \
  tests/test_week28_candidate_predicted_nmr.py \
  tests/test_week28_mobile_ui.py \
  tests/test_week27_spectral_similarity.py \
  tests/test_week26_candidate_comparison.py \
  tests/test_week25_dept_apt.py \
  tests/test_week23_nmr2d.py \
  tests/test_week22_carbon13.py
```

Full verification:

```bash
PYTHONPATH=src uv run pytest -q
PYTHONPATH=src uv run python -m compileall src/nmrcheck
grep -R "ms/hrms\|HRMS\|exact_mass\|adduct\|DBE\|isotope" src/nmrcheck tests docs README.md || true
```
