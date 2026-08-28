# FE handoff — `confidence_source` on AI predictions

Shows a reader whether a prediction's confidence was computed by this platform or supplied by
the caller. Backend is landed; this is the display work.

## 1. Where

`cd moltrace_frontend`. The surfaces that already read a prediction's confidence:

- `components/ai/ai-predictions-workspace.tsx`
- `components/ai/ai-prediction-detail-workspace.tsx`
- `src/lib/ai/prediction-confidence.ts` — the existing `readConfidence` / `describeScale` helpers

## 2. Regenerate the contract first

```
pnpm generate:openapi        # backend must be running on :8000
```

Contracts-first: the field exists in the backend already, and the frontend cannot type it until
`src/lib/api/schema.d.ts` is regenerated.

## 3. Contract delta, by name

Three response models gain one optional field each — nothing is renamed or removed:

| model | field | type |
|---|---|---|
| `PredictionResponse` (POST `/ai/predictions`) | `confidence_source` | `"engine" \| "caller_supplied" \| null` |
| `PredictionRun` | `confidence_source` | same |
| `PredictionResult` | `confidence_source` | same |

Values:

- `"engine"` — a model this platform ran produced the figure.
- `"caller_supplied"` — the figure came from the request's own `request_json`. It is recorded
  but **cannot approve the prediction**: such runs are forced to `requires_review` and carry a
  warning saying the platform did not compute the number.
- `null` — no confidence was recorded, or the row predates the field. Not a third source: it
  means unknown, and unknown provenance is a reason to show less, never more.

## 4. What to render

Beside the confidence figure, wherever it appears. This is the same rule §3.2 of
`fe_handoff_ai_engine_seam.md` already sets for `uncertainty.scale`: never render a confidence
without what qualifies it.

- `caller_supplied` — label it plainly as supplied with the request, not measured. It should not
  be drawn in the same visual weight as a computed figure, and it must never render as a
  proportional bar.
- `engine` — render as today.
- `null` — render the number with no source claim. Do not fall back to "engine".

Status is already `requires_review` for every caller-supplied run, so the existing review
affordance is the action; the label explains why it is there.

## 5. Verification

```
pnpm typecheck && pnpm lint && pnpm vitest --run
```

A/B probe against a nonexistent id to confirm the request shape is still accepted (422 means a
bad shape, 404 means the shape was valid). Then check both cases end to end:

- an engine-backed service (`nmr_candidate_ranking`) returns `confidence_source: "engine"`;
- an engine-less service (`reaction_outcome_predictor`) with `confidence_score` in
  `request_json` returns `"caller_supplied"`, `status: "requires_review"`, and the warning.

Backend tests covering this: `tests/test_ai_engine_seam_api.py::test_the_confidence_source_is_recorded_and_returned`
and `::test_a_caller_supplied_confidence_cannot_approve_its_own_prediction`.
