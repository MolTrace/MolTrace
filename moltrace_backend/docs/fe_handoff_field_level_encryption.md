# FE Handoff — Security Prompt 7: Field-level encryption via KMS

**TL;DR: no frontend action required.** Backend-internal at-rest encryption change. No route,
request/response model, status code, or `schema.d.ts` contract changed. `/openapi.json` is
unchanged — nothing to regenerate.

## What changed (backend only)

Secrets stored at rest (SSO IdP client secrets, MFA TOTP seeds) are now protected with
**envelope encryption** (`field_crypto` + `kms`): a fresh per-record AES-256-GCM data key,
itself wrapped by a key-encryption key (KEK). The ciphertext is a self-describing envelope
(`mtenc.v2.<key_id>.…`) carrying the algorithm and KEK key id, so the KEK can be **rotated**
without re-encrypting data, with a **BYOK / cloud-KMS seam** for customer-managed keys.

Pre-existing ciphertext (the old format) is transparently detected and still decrypts, then
upgrades to the envelope format on next write — no migration, no user impact.

The encrypted values live in the same `Text` columns as before; only the bytes inside them
changed. There is **no schema change and no API surface change** — the SSO login flow, MFA
enrollment/login, and every other endpoint behave identically.

## Verification

- `schema.d.ts`: **do not regenerate** — `/openapi.json` unchanged.
- Backend suite green incl. `tests/test_field_crypto.py` (envelope round-trip, legacy
  back-compat, KEK rotation, tamper/wrong-key auth failure, BYOK seam) and the SSO/MFA suites.

No FE checklist items. Logged for the BE→FE record only.
