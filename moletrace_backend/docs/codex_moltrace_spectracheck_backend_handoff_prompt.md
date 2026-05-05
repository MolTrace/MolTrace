# Codex Handoff Prompt: MolTrace SpectraCheck Backend Contract

You are working on the MolTrace backend in the `week10` FastAPI project.

Do not modify frontend files unless explicitly asked.

Goal: preserve and extend the stable SpectraCheck backend endpoint:

```text
POST /prediction/nmr/match/evidence
```

Rules:

1. Do not rename existing response fields. Preserve the legacy `label` field.
2. Prefer the MolTrace `evidence_label` field for UI-safe scientific language.
3. Allowed `evidence_label` values are:
   - `best_supported`
   - `plausible`
   - `requires_review`
   - `conflicting_evidence`
   - `insufficient_evidence`
   - `invalid_structure`
4. Do not claim identification or confirmation.
5. Keep `human_review_required=true` and `human_review_status=pending_review` unless a real review workflow updates it.
6. Preserve `input_provenance` SHA-256 hashes for submitted text and uploaded evidence files.
7. Return structured JSON for errors with `error`, `warnings`, `notes`, and `limitations`.
8. Keep the endpoint compatible with multipart `FormData` from the Next.js frontend proxy.
9. Keep existing endpoints and tests working.

Relevant files:

```text
src/nmrcheck/models.py
src/nmrcheck/candidate_predicted.py
src/nmrcheck/api.py
tests/test_week28_candidate_predicted_nmr.py
tests/test_week28_prediction_api.py
docs/moltrace_spectracheck_backend_contract.md
```

Focused test command:

```bash
PYTHONPATH=src uv run pytest -q tests/test_week28_candidate_predicted_nmr.py tests/test_week28_prediction_api.py
```

Backend run command:

```bash
PYTHONPATH=src uv run uvicorn nmrcheck.web:app --reload --host 0.0.0.0 --port 8000
```

Direct API smoke test:

```bash
curl -X POST http://localhost:8000/prediction/nmr/match/evidence \
  -H 'x-api-key: test-key' \
  -F 'sample_id=frontend-test-001' \
  -F 'solvent=CDCl3' \
  -F $'candidates_text=Ethanol | CCO | proposed\nMethanol | CO | starting material\nPropanol | CCCO | possible impurity' \
  -F 'observed_proton_text=1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)' \
  -F 'observed_carbon13_text=13C NMR (101 MHz, CDCl3) delta 58.3, 18.2.'
```

Expected behavior:

- Ethanol should rank as the best-supported candidate for the default demo evidence.
- The response must include `input_provenance` entries with 64-character SHA-256 hashes.
- The result must include `limitations` and human-review fields.
- The frontend should render `evidence_label`, `total_score`, evidence summaries, warnings, contradictions, and optional Developer JSON.
