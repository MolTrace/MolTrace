# FE handoff — `POST /spectrum/reason` (Prompt 14 RAG reasoner)

**Backend release:** v0.16.1 · **Date:** 2026-06-07 · **Scope:** frontend wiring only.

The backend now exposes the Prompt 14 retrieval-augmented reasoner as a typed
endpoint. This is a **new endpoint** — no existing contract changed. The binding
contract is the regenerated OpenAPI schema; everything below is a guide to it.

---

## 1. Regenerate the typed contract (do this first)

From `moltrace_frontend/`, with the backend running locally (or pointed at a
deployment whose `/openapi.json` includes v0.16.1):

```bash
npm run generate:openapi
```

This rewrites `moltrace_frontend/src/lib/api/schema.d.ts`. Confirm these five
component schemas now exist:

- `SpectrumReasonRequest`
- `SpectrumReasonResult`
- `SpectrumReasonAnalogue`
- `SpectrumReasonCandidate`
- `SpectrumReasonAudit`

…and the path `"/spectrum/reason"` (POST) is present.

## 2. Contract delta (names to consume)

| Direction | Type | Notes |
|---|---|---|
| Request | `SpectrumReasonRequest` | paired spectrum arrays + retrieval/proposal params |
| Response | `SpectrumReasonResult` | retrieval + reasoning, both individually gated |
| nested | `SpectrumReasonAnalogue` | one retrieved precedent (`result.retrieved[]`) |
| nested | `SpectrumReasonCandidate` | one proposed structure (`result.candidates[]` / `result.rejected[]`) |
| nested | `SpectrumReasonAudit` | compact audit summary (`result.audit`, nullable) |

## 3. Request shape

```jsonc
{
  "ppm_axis":   [/* float[], length 16..524288 */],
  "intensity":  [/* float[], same length as ppm_axis */],
  "nucleus":    "1H",            // "1H" | "13C" (default "1H")
  "solvent":    "CDCl3",         // optional, "" default, max 64 chars
  "field_mhz":  500.0,           // optional, (0, 2000], default 500
  "top_k":      50,              // retrieval depth, 1..1000, default 50
  "max_candidates": 5,           // 1..20, default 5
  "allowed_licenses": null       // optional string[] (licence-aware retrieval); null = keep all
}
```

- A **real spectrum** (paired `ppm_axis` + `intensity`, identical to
  `/spectrum/analyze/gsd`) is required: the verifier scores each candidate
  against it. Reuse whatever array source already feeds the GSD analyze call.
- `ppm_axis` and `intensity` must be the **same length** (else `400`); each must
  be ≥ 16 points (else `422`).

## 4. Response shape

```jsonc
{
  "query_nucleus": "1H",
  "index_available":   true,     // false => similarity index not configured server-side
  "reasoner_available": true,    // false => model backend (anthropic + key) not available
  "index_size": 45000,
  "top_k": 50,
  "max_candidates": 5,
  "truncated": false,            // retrieval context hit the token budget
  "retrieved": [                 // precedent analogues (present whenever index_available)
    {
      "analogue_id": "nmrshiftdb2:12345",
      "smiles": "c1ccccc1",
      "similarity": 0.83,        // bounded (0,1], 1.0 = identical encoding
      "l2_distance": 0.21,
      "rank": 0,
      "license": "CC-BY-SA",
      "shift_summary": null,
      "multiplet_summary": null,
      "source": "nmrshiftdb2"
    }
  ],
  "candidates": [                // VERIFIER-ACCEPTED, ranked by posterior_confidence desc
    {
      "smiles": "c1ccccc1",
      "rationale": "ring shifts match the benzene precedent",
      "cited_analogue_ids": ["nmrshiftdb2:12345"],
      "cited_valid_ids":    ["nmrshiftdb2:12345"],
      "self_confidence": 0.95,   // ADVISORY ONLY — do not present as the score
      "retrieval_supported": true,
      "posterior_confidence": 0.88,  // verifier (authoritative)
      "verdict": "consistent",
      "accepted": true,
      "dropped_reason": null
    }
  ],
  "rejected": [                  // guard-dropped / verifier-rejected, for transparency
    { "smiles": "CCO", "accepted": false, "dropped_reason": "hallucination_guard", "...": "..." }
  ],
  "audit": {                     // null when reasoning did not run
    "model": "claude-opus-4-8",
    "retrieved_ids": ["nmrshiftdb2:12345", "..."],
    "retry_used": false,
    "parsed_candidate_count": 2,
    "dropped_candidate_count": 1,
    "accepted_candidate_count": 1
  },
  "warnings": ["..."]
}
```

### UI guidance

- **Two independent capability flags.** Render on `index_available` and
  `reasoner_available` separately:
  - `index_available=false` → similarity index not configured server-side; show an
    empty/"retrieval unavailable" state (no `retrieved`, no `candidates`).
  - `index_available=true, reasoner_available=false` → show the **retrieved**
    precedent list; the reasoning panel shows "reasoning model unavailable" (this
    is the expected state until `ANTHROPIC_API_KEY` is configured for the env).
  - both true → full result.
- **Score = `posterior_confidence` / `verdict`, never `self_confidence`.** The
  model's `self_confidence` is advisory; the verifier is the arbiter. Present the
  posterior (and verdict) as the candidate's confidence; treat `self_confidence`
  as a dim secondary signal at most.
- `candidates` is the actionable list (accepted, already ranked). `rejected` is
  optional transparency detail (collapsed by default is fine) — `dropped_reason`
  explains why (`hallucination_guard`, `invalid_smiles`, `verifier_error:*`, or a
  non-`consistent` verdict).
- Surface `warnings` (e.g. license allow-list drops, truncation, backend-
  unavailable notes) as non-blocking info.

## 5. Status codes

- `200` — success (including the graceful `index_available=false` /
  `reasoner_available=false` states; check the flags, not the status).
- `400` — `ppm_axis`/`intensity` length mismatch, or the query spectrum could not
  be encoded/retrieved.
- `422` — request validation (array too short, `top_k`/`max_candidates` out of
  range, unknown nucleus).
- `401`/`403` — missing/invalid `x-api-key` (same auth as every other endpoint).

## 6. Verify

1. `npm run generate:openapi` succeeds and the five schemas + path appear in
   `schema.d.ts`.
2. Type-check the FE (`tsc` / your usual command) against the new types.
3. Smoke the graceful path first: a valid request against a backend with no index
   returns `200` with `index_available=false` — wire your empty state to that.

---

### Notes for the FE session (not action items)

- Server config lives entirely on the backend: `MOLTRACE_SIMILARITY_INDEX`
  (the FAISS index), optional `MOLTRACE_SIMILARITY_METADATA` (id→SMILES/license
  sidecar), and `ANTHROPIC_API_KEY` (the reasoner). The FE only consumes the two
  capability flags — it does not need to know about these env vars.
- The full system/user prompt and raw completion(s) are captured server-side
  (library `RAGAudit` + the `spectrum.reason` audit event); the response `audit`
  is the compact summary intended for the UI.
