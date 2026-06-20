# FE Handoff — Validation lifecycle (GAMP 5 / CSA, Security Prompt 13, backend v0.52.0)

**Scope for the FE session:** `moltrace_frontend/` only. Backend is committed. Additive — folds into
the existing **Validation Center** surface; no new top-level nav.

## Contract delta (by name)

New endpoints (both `require_access_context`):

| Method | Path | Body / response | Purpose |
|---|---|---|---|
| `POST` | `/system-releases/{release_id}/evidence` | `ReleaseEvidenceIngestRequest` → `SystemReleaseRecord` | Ingest CI test/risk summaries into a release. **409/400** if the release is already approved/released. |
| `GET` | `/system-releases/{release_id}/validation-package` | → `ValidationPackage` | Regenerable GAMP 5 / CSA package for the release. |

New schema components:
- `ReleaseEvidenceIngestRequest` — `{ test_summary_json: object, risk_summary_json: object,
  source: "ci"|"manual" = "ci", metadata_json: object }`.
- `ValidationPackage` — `{ package_metadata, requirement_risk_test_traceability, iq_oq_pq_evidence,
  risk_summary, change_control_state, signatures: object[], notice: string }` (all nested objects).

## Behavioral change the UI must handle — validated-state change control
Once a validation project is **approved/archived** or attached to an **approved/released** system
release, any change to it or its children (URS / functional spec / risk / test protocol / test case)
**requires a reason**. Supply it as `metadata_json.reason_for_change` on the existing create/update
calls; otherwise the request returns **400** ("…a reason_for_change is required…"). Draft /
in-progress projects are unaffected.
- Recommend: when the project is in a validated state, prompt the user for a "Reason for change"
  before any edit and pass it in `metadata_json.reason_for_change`. Surface the 400 message inline.

## Steps
1. `cd moltrace_frontend`
2. `npm run generate:openapi` — regenerates `src/lib/api/schema.d.ts` (binding contract). Commit it
   from the FE session; the backend session did not touch it.
3. **Validation package view:** on a system release, add a "Validation package" panel calling
   `GET /system-releases/{id}/validation-package`. Render:
   - `requirement_risk_test_traceability` (matrix + coverage + gaps; show `status` =
     `complete` / `gaps_identified` / `no_traceability_generated`),
   - `iq_oq_pq_evidence` (OQ pass/fail + counts; render IQ/PQ `status: "customer_supplied"` as an
     explicit "customer responsibility" badge — never as passed),
   - `change_control_state` (validated / change_controlled, open_deviation_count),
   - `signatures` (release approval manifestations), and the `notice` verbatim.
4. **CI evidence:** optional admin "Attach CI evidence" action calling `POST …/evidence` (or document
   it for the CI pipeline — a GitHub Actions step POSTs parsed pytest/coverage JSON). Surface the
   409/400 when the release is already approved.
5. **Change-control reason:** add the `reason_for_change` prompt for edits to validated projects (see above).
6. **Verify** on the dev server: ingest evidence → fetch the package → confirm OQ counts + the notice;
   approve the project → confirm a child edit without a reason returns 400 and with one returns 201.

## Grounding
Keep the "**supports GAMP 5 / CSA, not compliant-for-you**" framing — the package carries a `notice`
field; surface it verbatim. Present IQ/PQ as customer-supplied, and the package as an *evidence
assembly* that accelerates the customer's CSV, not a completed qualification.
