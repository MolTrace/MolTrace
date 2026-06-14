# FE Handoff — MFA & passkeys (TOTP + WebAuthn) + step-up — Security Prompt 3 (v0.42.0)

**From:** backend session · **To:** frontend session · **Scope:** wire the MFA enrollment/management
UI, the **MFA-at-login** challenge branch, and the **step-up** ceremony the FE must run before any
signing or admin-mutating action. Backend is complete + tested (`tests/test_mfa.py`).

Work in `moltrace_frontend/` only. Do **not** edit `moltrace_backend/`.

> **Design intent (integrate, don't clutter):** MFA enrollment/management folds into the existing
> **account/security settings** surface; the login challenge reuses the existing `/login` page; the
> step-up ceremony is a modal invoked before signing/admin actions and on a `401 step_up_required`.
> **No new top-level nav.**

---

## 1. Regenerate the typed schema (binding contract — do this first)

```bash
cd moltrace_backend && uv run uvicorn 'nmrcheck.api:create_app' --factory --port 8000   # Terminal A
cd moltrace_frontend && pnpm generate:openapi                                            # Terminal B
```
Commit the regenerated `moltrace_frontend/src/lib/api/schema.d.ts`.

## 2. Env contract (must match the SPA origin or all passkeys fail)

The backend pins WebAuthn server-side: `WEBAUTHN_RP_ID` (e.g. `moltrace.co` / `localhost`) and
`WEBAUTHN_ORIGIN` (full scheme+host, e.g. `https://moltrace.co`) **must** equal what the browser
serves the SPA from. A mismatch silently breaks every passkey ceremony.

## 3. MFA-at-login (the 202 branch)

`POST /auth/login` (and `/auth/sign-in`, `/auth/token`) now returns **HTTP 202** instead of a token
when a second factor is required:
```jsonc
// 202 MfaChallengeResponse
{ "mfa_required": true, "mfa_token": "<one-time, NOT a bearer>", "factors": ["webauthn","totp","recovery"],
  "webauthn_options": { /* navigator.credentials.get() options, if a passkey exists */ },
  "enrollment_required": false }
```
The SPA must branch on 202:
- **TOTP:** prompt for a code → `POST /auth/mfa/login/totp { mfa_token, code }` → `200` AccessTokenResponse.
- **Passkey:** `navigator.credentials.get({ publicKey: fromBase64(webauthn_options) })` → serialize the
  assertion → `POST /auth/mfa/login/webauthn { mfa_token, assertion }` → `200`.
- **Recovery:** `POST /auth/mfa/login/recovery { mfa_token, code }` → `200`.

The `mfa_token` is **not** a bearer — it only works on `/auth/mfa/login/*`. On `200`, store the
returned `access_token` exactly like a normal login.

## 4. Step-up (REQUIRED before signing & admin actions)

Privileged routes (e-signature create `POST /esignatures/records`, admin MFA-policy, …) now return
**`401 { "detail": "step_up_required" }`** when the session hasn't recently re-authenticated. On that
detail (distinct from a normal auth 401), run the step-up ceremony, then retry the original request:

1. `POST /auth/step-up/options` → `{ factors, webauthn_options? }`.
2. Complete one factor (server enforces the strongest available — no downgrade):
   - `POST /auth/step-up/webauthn { assertion }`  (passkey, aal2 — preferred)
   - `POST /auth/step-up/totp { code }`           (aal1)
   - `POST /auth/step-up/password { password }`   (**only** if the user has no stronger factor)
   Each returns `StepUpResult { stepped_up, factor, aal, expires_at }`. Step-up is valid ~5 min.
3. Retry the gated request. **Proactively** step-up right before opening a signing/admin modal so the
   user isn't bounced by a 401. Recovery codes are **never** accepted for step-up.

## 5. Enrollment & management (account → security settings)

All management endpoints require a fresh step-up first (enrollment-hijack guard); a brand-new user
with no factor uses **password step-up** to bootstrap.
- **TOTP:** `POST /auth/mfa/totp/enroll` → `{ otpauth_uri }` (render as a QR; also offer manual key) →
  user enters a code → `POST /auth/mfa/totp/confirm { code }` → `{ confirmed, recovery_codes? }`.
  **Show the 10 recovery codes once** (returned only on the user's first factor) with a download/copy
  prompt. `DELETE /auth/mfa/totp` removes it.
- **Passkey:** `POST /auth/mfa/webauthn/register/options` → `navigator.credentials.create({ publicKey })`
  → `POST /auth/mfa/webauthn/register/verify { credential, nickname? }`. List/rename/delete via
  `GET/PATCH/DELETE /auth/mfa/webauthn/credentials[/{id}]`.
- **Recovery:** `POST /auth/mfa/recovery/regenerate` → new batch (shown once; invalidates the old).
- **Status:** `GET /auth/mfa/status` → `{ factors, totp_confirmed, passkey_count, recovery_remaining,
  org_mfa_required, in_grace }` — use it to drive the "your org requires MFA — enroll now" banner.

## 6. Admin: per-tenant policy

`GET /admin/mfa/policy/{organization_id}` and `PUT` (admin + step-up) set `mfa_required`,
`grace_period_days`, `allowed_factors`, `enforce_for_sso`, `require_step_up_for_signing`. Fold into the
existing admin/tenant-settings surface.

## 7. Verification
- Confirm `schema.d.ts` exposes the `/auth/mfa/*`, `/auth/step-up/*`, `/admin/mfa/policy/*` paths and
  the `MfaChallengeResponse` / `StepUpResult` / `MfaStatusResponse` components.
- Mirror the backend states (`tests/test_mfa.py`): 202-login branch, the three login-verify paths, the
  step-up-before-signing 401→ceremony→retry, recovery one-time display, and the passkey ceremonies
  (use a browser virtual authenticator for E2E).
