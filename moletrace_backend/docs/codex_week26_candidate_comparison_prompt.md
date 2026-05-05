# Codex Prompt: Week 26 Candidate Comparison Engine

Use this prompt after applying `nmrcheck_week26_candidate_comparison_engine.zip`.

```text
You are working on the SpectraCheck / CheminSight repo.

Goal:
Verify, harden, and polish the Candidate Comparison Engine.

Important:
Do not add MS features.
Do not redesign the UI globally.
Do not alter raw FID processing, auto-phase, Bernstein baseline, real-spectrum viewer, 1H, 13C, DEPT/APT, or 2D behavior unless a bug is directly related to candidate comparison.

Scientific/product rule:
Candidate comparison is evidence ranking, not final structure confirmation. The system must compare proposed products, regioisomers, starting materials, side products, and likely impurities against the same 1H, 13C, DEPT/APT, and 2D NMR evidence stack. It must surface contradictions and ambiguity instead of overclaiming.

Required behavior:
1. Candidate comparison must be additive.
2. Candidate comparison must rank multiple SMILES against the same evidence stack.
3. It must support 1H NMR text, 13C NMR text, optional DEPT/APT files, and optional processed 2D NMR files.
4. It must return ranked candidates, best candidate, score breakdown, evidence layers used, contradictions, ambiguity alerts, and human-review notes.
5. It must not claim final confirmation.
6. It must not mutate 1H, 13C, DEPT/APT, 2D, FID, or spectrum viewer state.
7. It must keep the current real-spectrum viewer behavior intact: no display transform should affect evidence scoring.
8. It must remain compatible with the unified DEPT/APT + 2D NMR Evidence Studio UI.

Files to inspect:
- src/nmrcheck/candidate.py
- src/nmrcheck/models.py
- src/nmrcheck/api.py
- src/nmrcheck/web.py
- tests/test_week26_candidate_comparison.py
- tests/test_week26_candidate_ui.py
- tests/test_week25_dept_apt.py
- tests/test_week23_nmr2d.py
- tests/test_week22_carbon13.py
- docs/week26_candidate_comparison_engine.md

Endpoints to verify:
- POST /candidates/compare
- POST /candidates/compare/evidence

UI placement:
- Candidate Comparison Engine should appear in the Analysis tab.
- It should appear after the DEPT/APT + 2D NMR Evidence Studio.
- It should appear before Processed spectrum upload.
- It should use current 1H and 13C text as read-only evidence.
- It should include selected DEPT/APT and 2D files when present.
- Candidate input format should support: name | SMILES | role

Tests to add or strengthen:
1. Candidate parser handles name | SMILES | role.
2. Candidate parser rejects empty input.
3. Ethanol ranks above methanol/propanol for ethanol 1H/13C evidence.
4. Invalid SMILES is labeled invalid_structure and score 0.
5. Ambiguity alert appears when top scores are close.
6. /candidates/compare works with JSON.
7. /candidates/compare/evidence works with multipart form.
8. Candidate UI is after DEPT/APT+2D and before processed spectrum.
9. Existing 1H/13C/DEPT/APT/2D tests still pass.
10. Candidate comparison does not change outputs of existing stable endpoints.

Run:
PYTHONPATH=src uv run pytest -q tests/test_week26_candidate_comparison.py tests/test_week26_candidate_ui.py tests/test_week25_dept_apt.py tests/test_week23_nmr2d.py tests/test_week22_carbon13.py

Then run:
PYTHONPATH=src uv run pytest -q

Compile:
PYTHONPATH=src uv run python -m compileall src/nmrcheck

Search:
grep -R "Candidate Comparison\|candidates/compare\|CandidateComparison\|compare_candidates" src/nmrcheck tests docs README.md || true

Acceptance criteria:
- Candidate ranking works.
- Score breakdown is transparent.
- UI placement is correct.
- Existing stable behavior is unchanged.
- Focused tests pass.
- Full tests pass or unrelated failures are documented.
- No MS, HRMS, reaction optimization, or regulatory features are added in this task.

Return:
1. Files changed
2. Endpoints verified
3. UI changes verified
4. Tests added/updated
5. Test results
6. Known limitations
7. Exact local commands I should run
```
