# FE Handoff — Enterprise SSO (OIDC federation) — Security Prompt 1 (v0.40.0)

**From:** backend session · **To:** frontend session · **Scope:** wire up the new
**per-organization OpenID Connect SSO** backend — an admin connection-management panel,
the public login-redirect entry point, and the SPA callback that trades a one-time code
for a session. Backend is complete, migrated (`0017_sso_connections`), and tested
(`tests/test_auth_sso_oidc_api.py`, 9 tests).

Work in `moltrace_frontend/` only. Do **not** edit `moltrace_backend/`.

> **Design intent (integrate, don't clutter):** SSO is an **auth-layer** capability. The
> admin connection manager folds into the existing **admin / tenant-ops** surface (alongside
> team/organization management) — **no new top-level nav**. The login flow reuses the existing
> `/login` page (add an "SSO" entry point + the `?sso_error=1` state). The callback is a thin
> headless route, not a new screen.

---

## 1. Regenerate the typed schema (binding contract — do this first)

```bash
# Terminal A — serve the backend OpenAPI on :8000
cd moltrace_backend
uv run uvicorn 'nmrcheck.api:create_app' --factory --port 8000

# Terminal B — regenerate the typed schema into the FE
cd moltrace_frontend
pnpm generate:openapi
#   → openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.d.ts
```

Commit the regenerated `moltrace_frontend/src/lib/api/schema.d.ts` with your FE work.

## 2. Contract delta (what the regenerate adds)

**New paths**
- `GET    /auth/sso/connections` — list connections (admin). Optional `?organization_id=`.
- `POST   /auth/sso/connections` — create a connection (admin). → `201`.
- `GET    /auth/sso/connections/{connection_id}` — read one (admin).
- `PATCH  /auth/sso/connections/{connection_id}` — partial update (admin).
- `DELETE /auth/sso/connections/{connection_id}` — delete (admin).
- `GET    /auth/sso/{slug}/login` — **browser redirect** to the IdP (public; not an XHR — see §4c).
- `GET    /auth/sso/callback` — the IdP lands here; it 302-redirects to the SPA (public; you do
  not call this directly).
- `POST   /auth/sso/exchange` — trade the one-time code for a bearer session (public).

**New component schemas**
- `SSOConnectionCreate`, `SSOConnectionUpdate`, `SSOConnectionOut`, `SSOConnectionList`,
  `SSOExchangeRequest`. **`SSOConnectionOut` never includes the client secret** — there is no
  read-back of a stored secret by design; rotation is write-only via `PATCH { client_secret }`.

## 3. Auth

- **Connection CRUD** is admin-gated (`require_admin`): system `x-api-key` **or** an admin user
  Bearer token. A non-admin Bearer → `403`; unauthenticated → `401`.
- **Login / callback / exchange** are **public** (the user has no session yet).
- `POST /auth/sso/exchange` returns the standard `AccessTokenResponse`
  (`{ access_token, token_type: "bearer", expires_at, user }`) — store and use it exactly like
  the password-login response.

## 4. Request / response shapes & the login flow

### 4a. Create a connection — `POST /auth/sso/connections` (admin)

```jsonc
{
  "organization_id": 12,                 // the org this IdP federates (must exist)
  "slug": "acme",                        // URL-safe; used in /auth/sso/acme/login. ^[a-z0-9][a-z0-9-]*[a-z0-9]$
  "display_name": "Acme Okta",
  "issuer": "https://acme.okta.com",     // OIDC issuer (discovery is /.well-known/openid-configuration)
  "client_id": "0oa1b2c3...",
  "client_secret": "super-secret",       // stored AES-256-GCM encrypted; never returned
  "email_domains": ["acme.com"],         // [] = any domain allowed; otherwise the asserted email must match
  "enabled": true,
  "enforce_sso": false                   // true = block password login for these domains (see §5)
}
```

Response is `SSOConnectionOut` (no `client_secret`). Duplicate `slug` → `400`.

**Register the redirect URI with the IdP:** the backend computes it server-side as
`{BASE_URL}/auth/sso/callback` (never client-supplied). The admin must add that exact URI to
the IdP app's allowed redirect URIs. Surface this value in the panel as copy-to-clipboard help
text (derive from the backend's configured base URL / your deployment's known API origin).

### 4b. Update — `PATCH /auth/sso/connections/{id}` (admin)

All fields optional. Sending `client_secret` **rotates** it (re-encrypted); omitting it leaves
the stored secret untouched. Toggle `enabled` / `enforce_sso` here.

### 4c. The login flow (the important part)

```
[user clicks "Sign in with SSO"]
      │  full-page navigation (NOT fetch/XHR — this is a 302 chain to a third-party IdP)
      ▼
GET {API}/auth/sso/{slug}/login   ──302──▶  IdP authorize page  ──(user authenticates)──┐
                                                                                          │
GET {API}/auth/sso/callback?state&code  ◀───────────────────302 from IdP─────────────────┘
      │  backend validates + JIT-provisions, then 302s to the SPA:
      ▼
{FRONTEND_BASE_URL}/auth/sso/callback?code=<one-time-code>     (success)
   …or…  {FRONTEND_BASE_URL}/login?sso_error=1                 (any failure)
```

**You build two things on the SPA side:**

1. **An SSO entry point** — e.g. a button/link that does a **full-page navigation** to
   `${API_BASE}/auth/sso/${slug}/login` (do **not** `fetch()` it — it must be a top-level
   browser navigation so the IdP redirect chain works and cookies/redirects land in the address
   bar). How the user picks `slug`: either an email-first step ("enter work email" → look up the
   org's slug) or a tenant-specific deep link. Simplest first cut: a configured slug per tenant
   subdomain, or an admin-provided "Sign in with {display_name}" link.

2. **A callback route** at `/auth/sso/callback` that:
   - reads `code` from the query string,
   - `POST`s it to `/auth/sso/exchange` → `{ "code": "<one-time-code>" }`,
   - on `200`, stores the returned `access_token` exactly like password login and redirects into
     the app,
   - on `400` (invalid/expired/already-used code), redirects to `/login?sso_error=1`.

   The exchange code is **single-use and short-lived** (the login flow expires in 10 min). Don't
   render it; immediately exchange and discard.

3. **`/login` honors `?sso_error=1`** — show a non-leaky banner ("SSO sign-in could not be
   completed — please try again or use your password"). The backend deliberately does **not**
   leak the specific reason (bad domain, expired, IdP error) to the browser.

### 4d. Exchange — `POST /auth/sso/exchange`

```jsonc
// request
{ "code": "<one-time-code-from-callback-query>" }

// 200 — same shape as /auth/login
{ "access_token": "…", "token_type": "bearer", "expires_at": "2026-06-20T…Z",
  "user": { "id": 42, "email": "newhire@acme.com", "is_admin": false, … } }
```

JIT: a first-time SSO user is auto-created (verified, no usable password) and added as an
**active member** of the connection's organization. No pre-provisioning needed.

## 5. enforce-SSO interaction with password login

When a connection has `enabled && enforce_sso` and its `email_domains` cover a user's email,
the password endpoints **reject** that user with **`403`** and detail:
*"Single sign-on is required for your organization. Please sign in through your identity
provider."* This affects `POST /auth/login`, `POST /auth/sign-in`, and `POST /auth/token`.

**FE behavior:** on a `403` from the login form, detect this case and steer the user to the SSO
entry point instead of showing a generic "wrong password" error. (You can branch on the detail
string, or — cleaner — when you know the org is SSO-enforced, hide the password form and show
only the SSO button.)

## 6. Suggested UI

**Admin → SSO connections panel** (folds into admin/tenant-ops, no new top-level nav):
- Table from `GET /auth/sso/connections`: `display_name`, `slug`, `issuer`, `email_domains`,
  `enabled`, `enforce_sso`.
- Create/edit form per §4a/§4b. Show the **redirect URI to register** as copy-to-clipboard help.
  `client_secret` is a write-only field ("leave blank to keep current") — never display a stored
  secret (the API doesn't return one).
- A clear **enforce-SSO** toggle with a warning ("password login will be blocked for
  {email_domains}").

**Login page:** an SSO entry point (§4c) and the `?sso_error=1` banner (§4d).

## 7. Verification

- After regenerating, confirm `schema.d.ts` exposes the 8 `/auth/sso/*` paths and the
  `SSOConnection*` / `SSOExchangeRequest` components, and that `SSOConnectionOut` has **no**
  `client_secret` property.
- Backend behavior (mirror these in FE states) is covered by
  `moltrace_backend/tests/test_auth_sso_oidc_api.py`: admin CRUD + secret-never-leaked, admin
  gating (`403`), duplicate slug (`400`), full JIT login, single-use exchange code, email-domain
  gating, IdP-error redirect, and enforce-SSO blocking password login.
- The callback and login redirects target `FRONTEND_BASE_URL` (set on the backend). In local dev
  that defaults to `http://localhost:3000`; make sure your dev origin matches or set
  `FRONTEND_BASE_URL` accordingly when running the backend.
