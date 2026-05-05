# MolTrace SpectraCheck Backend Contract

## Purpose

This contract stabilizes the first frontend-connected SpectraCheck vertical slice.

The endpoint ranks candidate structures against observed NMR evidence using candidate-specific predicted 1H, 13C, and optional HSQC/HMQC-style direct C-H context. It does not identify or confirm a structure. It returns evidence ranking that must remain human-reviewable.

## Endpoint

```text
POST /prediction/nmr/match/evidence
```

## Request

Content type: `multipart/form-data`

Fields:

- `candidates_text` required string. One candidate per line. Accepted formats: `SMILES`, `name | SMILES`, or `name | SMILES | role`.
- `observed_proton_text` optional string.
- `observed_carbon13_text` optional string.
- `solvent` optional string.
- `sample_id` optional string.
- `observed_nmr2d_file` optional uploaded processed 2D NMR peak table.
- `nmr2d_experiment_type` optional string such as `HSQC` or `HMQC`.

Example:

```bash
curl -X POST http://localhost:8000/prediction/nmr/match/evidence \
  -H 'x-api-key: test-key' \
  -F 'sample_id=frontend-test-001' \
  -F 'solvent=CDCl3' \
  -F $'candidates_text=Ethanol | CCO | proposed\nMethanol | CO | starting material\nPropanol | CCCO | possible impurity' \
  -F 'observed_proton_text=1H NMR (400 MHz, CDCl3) delta 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)' \
  -F 'observed_carbon13_text=13C NMR (101 MHz, CDCl3) delta 58.3, 18.2.'
```

## Response

Response model: `CandidatePredictedNMRMatchResult`

Important top-level fields:

- `sample_id`
- `solvent`
- `candidate_count`
- `best_candidate`
- `ranked_candidates`
- `ambiguity_alerts`
- `evidence_layers_used`
- `notes`
- `warnings`
- `limitations`
- `input_provenance`
- `human_review_required`
- `human_review_status`
- `metadata`

Important candidate fields:

- `rank`
- `name`
- `role`
- `smiles`
- `label`
- `evidence_label`
- `total_score`
- `prediction`
- `proton_similarity`
- `carbon13_similarity`
- `nmr2d_similarity`
- `evidence_summary`
- `contradictions`
- `warnings`
- `limitations`
- `human_review_required`
- `human_review_status`
- `metadata`

The legacy `label` field is preserved for compatibility. MolTrace frontend code should prefer `evidence_label` for review-safe presentation.

Allowed `evidence_label` values:

- `best_supported`
- `plausible`
- `requires_review`
- `conflicting_evidence`
- `insufficient_evidence`
- `invalid_structure`

Example response excerpt:

```json
{
  "sample_id": "frontend-test-001",
  "solvent": "CDCl3",
  "candidate_count": 3,
  "best_candidate": {
    "rank": 1,
    "name": "Ethanol",
    "role": "proposed",
    "smiles": "CCO",
    "label": "best_predicted_match",
    "evidence_label": "best_supported",
    "total_score": 0.87,
    "evidence_summary": ["Predicted 1H match score: 0.82.", "Predicted 13C match score: 0.95."],
    "contradictions": [],
    "human_review_required": true,
    "human_review_status": "pending_review"
  },
  "evidence_layers_used": ["1H predicted-match", "13C predicted-match"],
  "warnings": [],
  "limitations": [
    "Candidate-specific predicted NMR matching is ranking evidence, not final structure identification."
  ],
  "input_provenance": [
    {
      "field_name": "candidates_text",
      "source": "form",
      "sha256": "64-character-sha256",
      "size_bytes": 117
    }
  ],
  "human_review_required": true,
  "human_review_status": "pending_review"
}
```

## Structured Errors

Malformed candidate text, invalid form fields, and unparseable 2D files return HTTP 400 with structured JSON under `detail`:

```json
{
  "detail": {
    "error": {
      "code": "invalid_candidates_text",
      "message": "No candidate structures were found. Enter one SMILES per line or use name | SMILES | role."
    },
    "warnings": ["No candidate structures were found. Enter one SMILES per line or use name | SMILES | role."],
    "notes": ["Candidate-specific predicted NMR matching returns ranking evidence and requires human review."],
    "limitations": ["Candidate-specific predicted NMR matching is ranking evidence, not final structure identification."]
  }
}
```

## OpenAPI Notes

The endpoint remains OpenAPI-compatible through FastAPI's generated schema. The multipart form fields appear in the operation request body, and `CandidatePredictedNMRMatchResult` documents the stable response fields.

OpenAPI generation:

```bash
PYTHONPATH=src uv run uvicorn nmrcheck.web:app --reload --host 0.0.0.0 --port 8000
curl http://localhost:8000/openapi.json
```

## Tests

Focused tests:

```bash
PYTHONPATH=src uv run pytest -q tests/test_week28_candidate_predicted_nmr.py tests/test_week28_prediction_api.py
```

The tests cover:

- candidate ranking unit behavior
- review-safe `evidence_label`
- limitations and human review flags
- multipart API submission
- input provenance SHA-256 hashes
- structured 400 errors
- OpenAPI schema fields

## Known Limitations

- The predictor is a transparent RDKit heuristic, not a production ML or DFT predictor.
- 2D matching currently supports direct HSQC/HMQC-style C-H context. COSY and HMBC candidate-specific prediction is not implemented.
- Text parsers can miss overlapping peaks, solvent/impurity peaks, exchangeable protons, stereochemical effects, and concentration-dependent shifts.
- Results are evidence ranking only and require human review before report signoff.
