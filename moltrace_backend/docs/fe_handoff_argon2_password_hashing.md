# FE Handoff — Security Prompt 6: Argon2id credential hashing

**TL;DR: no frontend action required.** Backend-internal credential-hashing upgrade. No route,
request/response model, status code, or `schema.d.ts` contract changed. `/openapi.json` is
unchanged — nothing to regenerate.

## What changed (backend only)

Passwords are now hashed with **Argon2id** (a memory-hard KDF per the §7 crypto-binding table)
instead of PBKDF2-HMAC-SHA256. Existing PBKDF2 hashes still verify (no user is locked out) and
are **transparently re-hashed to Argon2id on the next successful login** — no migration, no
forced reset, invisible to the user and the FE. High-entropy random tokens (session/refresh
tokens, MFA recovery codes, share links) keep their fast SHA-256 digest — unchanged.

An optional, KMS-held **pepper** (`PASSWORD_PEPPER` env) can be configured server-side; it is
invisible to the client.

## Observable behavior — unchanged

| Flow | Before | After |
|---|---|---|
| Sign-up / login / password reset | 200/201 + bearer | identical |
| Wrong password | 401 | identical |
| A user whose hash predates this change | logs in normally | logs in normally (hash silently upgraded) |

The only difference a user could notice is a few extra tens of milliseconds on the password
verify step (Argon2id is deliberately slower than PBKDF2) — well within normal login latency and
not something the FE handles differently.

## Verification

- `schema.d.ts`: **do not regenerate** — `/openapi.json` unchanged.
- Backend suite green incl. `tests/test_password_hashing.py` (Argon2id format, legacy-PBKDF2
  verify + rehash-on-login migration, pepper round-trip, wrong-password rejection).

No FE checklist items. Logged for the BE→FE record only.
