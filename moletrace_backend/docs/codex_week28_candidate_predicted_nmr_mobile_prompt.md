# Codex Week 28 Prompt: Candidate-Specific Predicted NMR + Mobile UI

Goal: add candidate-specific predicted NMR matching and mobile-friendly analysis UI improvements.

Do not add MS features, reaction optimization, regulatory features, or candidate ranking outside the requested predicted-NMR evidence layer. Do not alter raw FID processing, auto-phase, Bernstein baseline logic, real-spectrum viewer behavior, existing 1H/13C evidence, DEPT/APT, 2D, candidate comparison, or spectral similarity except where directly integrated.

Required endpoints:

```text
POST /prediction/nmr/preview
POST /prediction/nmr/match
POST /prediction/nmr/match/evidence
```

Required UI:

- Add `Candidate-specific Predicted NMR Matching` after `Spectral Similarity Scoring` and before `Processed spectrum upload`.
- Use current `nmrText`, `carbon13Text`, and selected `nmr2dFile` as read-only evidence.
- Add mobile CSS for max-width 760px with scrollable navigation, full-width controls, 16px inputs, and scrollable tables.

Required tests:

```text
tests/test_week28_candidate_predicted_nmr.py
tests/test_week28_prediction_api.py
tests/test_week28_mobile_ui.py
```

Focused verification:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/test_week28_candidate_predicted_nmr.py \
  tests/test_week28_mobile_ui.py \
  tests/test_week28_prediction_api.py \
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
grep -R "prediction/nmr\|PredictedNMR\|candidate_predicted\|nmr_prediction\|Candidate-specific Predicted" src/nmrcheck tests docs README.md || true
```
