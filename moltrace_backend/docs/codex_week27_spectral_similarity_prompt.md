# Codex Prompt: Week 27 Spectral Similarity Scoring

Use this prompt after applying `nmrcheck_week27_spectral_similarity_scoring.zip`.

```text
You are working on the SpectraCheck / CheminSight repo.

Goal:
Verify, harden, and polish spectral similarity scoring across 1H, 13C, and 2D NMR.

Do not add MS features.
Do not add raw 2D FID.
Do not redesign the UI globally.
Do not alter raw FID processing, auto-phase, Bernstein baseline, real-spectrum viewer, 1H/13C evidence, DEPT/APT, 2D evidence, or candidate comparison unless a bug is directly related to spectral similarity.

Scientific/product rule:
Spectral similarity is a confidence aid and ranking signal. It must not claim final structure confirmation. It should expose vector scores, set-matching scores, matches, unmatched peaks, warnings, and human-review notes.

Files to inspect:
- src/nmrcheck/spectral_similarity.py
- src/nmrcheck/models.py
- src/nmrcheck/api.py
- src/nmrcheck/web.py
- src/nmrcheck/evidence.py
- src/nmrcheck/nmr2d.py
- tests/test_week27_spectral_similarity.py
- tests/test_week27_spectral_similarity_ui.py
- tests/test_week27_spectral_similarity_api.py

Endpoints to verify:
- POST /similarity/score
- POST /similarity/score/evidence

Required behavior:
1. 1H similarity uses Gaussian-smoothed vector similarity, greedy Gaussian set matching, and integration-aware repeated-shift set representation.
2. 13C similarity uses chemical-shift-only vector similarity and set matching with no quantitative 13C intensity assumption.
3. 2D similarity uses cross-peak set matching; COSY uses 1H/1H tolerances; HSQC/HMQC/HMBC use 1H/13C tolerances; diagonal COSY peaks are excluded.
4. Overall score combines only available layers.
5. Returned output must include overall_score, label, layer scores, vector_score, set_score, matched_count, unmatched observed/reference counts, peak/cross-peak matches, warnings, and notes.
6. Similarity scoring must not mutate existing evidence inputs.
7. UI must appear in Analysis tab after Candidate Comparison and before Processed spectrum upload.
8. UI must use current 1H/13C text as observed spectra and separate fields for reference spectra.
9. Optional observed/reference 2D files must be supported.
10. Existing stable tests must still pass.

Run focused tests:
PYTHONPATH=src uv run pytest -q tests/test_week27_spectral_similarity.py tests/test_week27_spectral_similarity_ui.py tests/test_week27_spectral_similarity_api.py tests/test_week26_candidate_comparison.py tests/test_week25_dept_apt.py tests/test_week23_nmr2d.py tests/test_week22_carbon13.py

Run full tests:
PYTHONPATH=src uv run pytest -q

Compile:
PYTHONPATH=src uv run python -m compileall src/nmrcheck

Search:
grep -R "similarity/score\|SpectralSimilarity\|score_proton_similarity\|score_nmr2d_similarity" src/nmrcheck tests docs README.md || true

Acceptance criteria:
- 1H/13C/2D similarity scoring works.
- Vector and set scores are both visible where applicable.
- 2D cross-peak matching works.
- UI placement is correct.
- Existing candidate and evidence modules are unchanged.
- Focused tests pass.
- Full tests pass or unrelated failures are documented.

Return:
1. Files changed
2. Endpoints verified
3. UI changes verified
4. Tests added/updated
5. Test results
6. Known limitations
7. Exact local commands I should run
```
