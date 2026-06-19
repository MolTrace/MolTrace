# FE Handoff — 21 CFR Part 11 e-signature hardening (Security Prompt 11, backend v0.50.0)

**Scope for the FE session:** `moltrace_frontend/` only. The backend changes are already committed.
This is a **hardening** of the *existing* e-signature surface — there is **no new top-level nav and no
new feature**. Fold the new verify/manifestation affordances into the existing signature UI.

## What changed on the backend (contract delta by name)

The existing `POST /esignatures/records` is unchanged in *shape* but changed in *meaning*, and two
read endpoints were added. New/changed schema components:

1. `ElectronicSignatureRecord` (response) — gained **3 additive, optional** fields:
   - `signer_user_id: number | null` — the authenticated principal who actually signed (§11.100).
   - `record_content_hash: string | null` — `"sha256:"+64hex` of the signed record snapshot, or
     `null` for "unbound" targets / legacy rows (§11.70).
   - `signature_digest: string | null` — the content-bound digest, or `null` (legacy/unbound).
2. `ESignatureVerification` (NEW) — `{ signature_id, bound: boolean, valid: boolean|null,
   hash_matches: boolean|null, content_matches: boolean|null, record_content_hash: string|null,
   recomputed_content_hash: string|null, reason: string }`.
3. `ESignatureManifestation` (NEW) — `{ printed_name, signer_email, signature_meaning, meaning_label,
   signed_at_utc, reason, target_type, target_id, record_content_hash, signature_digest,
   authentication_method, step_up_factor, step_up_aal, attestation_text, compliance_notice }`.

### Behavioral changes the UI must reflect
- **Signer identity is server-authoritative.** `signer_name`/`signer_email` are still in the
  `POST` request body (back-compat) but the server **ignores** them and signs as the authenticated
  user. Recommend: stop collecting "who is signing" in the form (it's the logged-in user); keep
  `reason` + `signature_meaning`. If you keep the field, label it read-only as the current user.
- **Signing still requires a fresh step-up.** `POST /esignatures/records` returns **401** with
  `detail: "step_up_required"` when step-up is stale — drive your existing `withStepUp` retry
  (same flow as other signing-gated actions). The `/api/backend` proxy passes this detail through.

## New endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/esignatures/records/{id}/verify?recompute=true` | bearer | §11.70 integrity check. `recompute=true` re-snapshots the live record to detect post-signing changes. |
| `GET` | `/esignatures/records/{id}/manifestation?format=json\|html` | bearer | §11.50 manifestation. `format=html` returns a self-contained printable block (browser print → PDF). |

## Steps

1. **`cd moltrace_frontend`**
2. **Regenerate the typed contract:** `npm run generate:openapi`
   (this hits the backend `/openapi.json` and rewrites `src/lib/api/schema.d.ts` — the binding
   contract). Commit `schema.d.ts` from the FE session; the backend session deliberately did **not**
   touch it.
3. **Signature panel:** on each signature, surface a **"Verify"** affordance calling
   `GET …/{id}/verify?recompute=true`. Render:
   - `bound === false` → badge "Unbound (legacy)" (neutral, not an error).
   - `valid === true` → "Verified ✓".
   - `valid === false` → "Integrity check failed" — distinguish `reason: "digest_mismatch"`
     (record/row tampered) vs `reason: "record_content_changed"` (the signed record was edited
     after signing).
4. **Manifestation:** add a **"View / Print signature"** action that opens
   `GET …/{id}/manifestation?format=html` (printable §11.50 stamp) or renders the JSON variant
   inline (use `attestation_text` + `meaning_label` + `signed_at_utc`; always show
   `compliance_notice`).
5. **Signing form:** drop client-entered signer name/email (or render read-only as the current user);
   keep `signature_meaning` (Literal: reviewed/approved/rejected/authored/verified/released/locked/
   override/other) and `reason`.
6. **Verify:** with the dev server on `:3000`, sign a controlled record, confirm the 401→step-up→201
   flow, then Verify shows "Verified ✓" and Print shows the manifestation. Vitest/jsdom is fine for
   the panel rendering if a preview server isn't available.

## Grounding / compliance copy
Keep the **"supports 21 CFR Part 11, not compliant-for-you"** framing. The manifestation already
carries a `compliance_notice` — surface it verbatim; do not upgrade it to "compliant".
