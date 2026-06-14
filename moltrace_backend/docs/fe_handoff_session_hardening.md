# FE Handoff — Session & token hardening (rotating refresh) — Security Prompt 4 (v0.43.0)

**From:** backend session · **To:** frontend session · **Scope:** store the new **refresh token**
and call `POST /auth/refresh` to rotate it when the access token nears expiry or a request 401s.
The access bearer you already use is **unchanged** — this is additive.

Work in `moltrace_frontend/` only. Do **not** edit `moltrace_backend/`.

---

## 1. Regenerate the typed schema (binding contract — do this first)

```bash
cd moltrace_backend && uv run uvicorn 'nmrcheck.api:create_app' --factory --port 8000   # Terminal A
cd moltrace_frontend && pnpm generate:openapi                                            # Terminal B
```
Commit the regenerated `schema.d.ts`.

## 2. What changed (additive)

Every login response (`/auth/login`, `/auth/sign-in`, `/auth/sign-up`, `/auth/token`, the
`/auth/mfa/login/*` verify routes, and the SSO `/auth/sso/exchange`) now also returns:
```jsonc
{ "access_token": "…", "token_type": "bearer", "expires_at": "…", "user": {…},
  "refresh_token": "…",            // NEW — store securely (see §4)
  "refresh_expires_at": "…" }      // NEW
```
The `access_token` and how you send it (`Authorization: Bearer`) are **identical to today**.

## 3. The refresh flow

- **`POST /auth/refresh`** body `{ "refresh_token": "…" }` → returns a **new** `AccessTokenResponse`
  (new `access_token` **and** new `refresh_token` — it rotates). The old access token and old
  refresh token are now dead; replace both in storage.
- Call it when the access token is near/at expiry, or once on a `401` from a product route, then
  retry the original request with the new access token.
- **`POST /auth/refresh/revoke`** body `{ "refresh_token": "…" }` → revokes the whole session
  (logout-everywhere for that login).
- **`POST /auth/logout`** (with the access bearer) now revokes the **entire family** — the refresh
  token is dead too.

### Error codes (the `detail` field is a stable machine code)
- `401 { "detail": "token_expired" }` → refresh idle/absolute window elapsed → send the user to log
  in again (benign).
- `401 { "detail": "token_invalid" }` → unknown/garbage refresh → log in again.
- `401 { "detail": "token_reuse_detected" }` → **a spent refresh was replayed (possible theft).**
  The whole family is revoked server-side. Treat as a **hard logout**: clear all tokens, force a
  fresh login, optionally warn the user.

## 4. Storage + behavior guidance
- Store the refresh token as securely as the platform allows (httpOnly cookie if the proxy sets it,
  otherwise the most protected store available — it is higher-value than the short access token).
- **Single-flight the refresh:** if multiple requests 401 at once, run **one** `/auth/refresh` and
  queue the rest behind it — concurrent refreshes of the same token trip reuse detection and log the
  user out. (The backend tolerates a tight double-submit, but don't rely on it.)
- On `token_reuse_detected`, do **not** retry — clear everything and re-authenticate.
- A short access TTL is recommended in prod (`ACCESS_TOKEN_TTL_MINUTES=15`); design the client to
  refresh transparently rather than assuming a 7-day access token.

## 5. Optional: device binding
If `SESSION_DEVICE_BINDING_ENABLED=true` server-side, the refresh family is bound to a coarse device
signal (`User-Agent` + an optional `X-Client-Id` header). Send a **stable** `X-Client-Id` (e.g. a
persisted install UUID) on login **and** on `/auth/refresh`; a changed fingerprint revokes the
family. Off by default — no action needed unless your deployment enables it.

## 6. Verification
- Confirm `schema.d.ts` exposes `POST /auth/refresh` + `/auth/refresh/revoke` and the new optional
  `refresh_token` / `refresh_expires_at` fields on the auth responses.
- Mirror the backend states from `moltrace_backend/tests/test_session_hardening.py`: rotation
  replaces both tokens; reuse → hard logout; logout/revoke kill the refresh; idle/absolute →
  re-login.
