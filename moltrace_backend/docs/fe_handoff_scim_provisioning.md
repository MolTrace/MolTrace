# FE Handoff — SCIM 2.0 provisioning (admin token management) — Security Prompt 2 (v0.41.0)

**From:** backend session · **To:** frontend session · **Scope:** the SCIM **`/scim/v2`** API is
machine-facing (Okta/Entra call it directly — **no FE work there**). What the FE owns is the
**admin token-management UI** on the existing SSO connection panel: issue / show-status / rotate /
revoke the per-connection SCIM bearer that the IdP stores.

Work in `moltrace_frontend/` only. Do **not** edit `moltrace_backend/`.

> **Design intent (integrate, don't clutter):** this is a small addition to the **admin SSO
> connection** surface from Prompt 1 — a "SCIM provisioning" subsection on each connection's
> detail/edit view. **No new top-level nav.**

---

## 1. Regenerate the typed schema (binding contract — do this first)

```bash
# Terminal A — serve the backend OpenAPI on :8000
cd moltrace_backend
uv run uvicorn 'nmrcheck.api:create_app' --factory --port 8000

# Terminal B — regenerate the typed schema into the FE
cd moltrace_frontend
pnpm generate:openapi   # openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.d.ts
```

Commit the regenerated `moltrace_frontend/src/lib/api/schema.d.ts` with your FE work.

## 2. Contract delta (admin token routes — the only FE-facing surface)

All three are **admin-gated** (system `x-api-key` or an admin Bearer; non-admin → `403`).

- `POST   /auth/sso/connections/{connection_id}/scim-token` → **`201`** `ScimTokenIssueResponse`.
  Mints (and rotates — revoke-then-issue) the connection's SCIM bearer. **`token` (plaintext) is
  returned exactly once** and is never re-readable. `404` if the connection doesn't exist.
- `GET    /auth/sso/connections/{connection_id}/scim-token` → **`200`** `ScimTokenInfo` (prefix +
  `created_at`/`last_used_at`/`expires_at`, **no plaintext**) or `404` if no live token.
- `DELETE /auth/sso/connections/{connection_id}/scim-token` → **`200`** `MessageResponse`; `404`
  if there's no live token to revoke.

**New component schemas:** `ScimTokenIssueResponse` (`token`, `token_prefix`, `connection_id`,
`created_at`, `expires_at?`) and `ScimTokenInfo` (same minus `token`).

The `/scim/v2/*` paths also appear in the OpenAPI doc but are **machine-facing** — the FE does not
call them.

## 3. Suggested UI (admin → SSO connection detail → "SCIM provisioning" subsection)

- **No live token:** a "Generate SCIM token" button → `POST`. On success, show the `token` **once**
  in a copy-to-clipboard box with a clear "copy now — it won't be shown again" warning, plus the
  two values the IdP admin needs to paste into Okta/Entra:
  - **SCIM base URL:** `{API_ORIGIN}/scim/v2`
  - **Bearer token:** the returned `token`.
- **Live token exists** (`GET` returns `200`): show `token_prefix` (e.g. `scim_AbC…`), `created_at`,
  and `last_used_at` ("last sync") — never the secret. Offer **Rotate** (`POST` again; warn the old
  token stops working immediately) and **Revoke** (`DELETE`).
- Gate the whole subsection behind the connection being **enabled** (disabling the SSO connection
  also disables SCIM — a revoked/disabled state should be reflected).

## 4. How it fits together (context, no FE work needed here)

The IdP authenticates to `/scim/v2` with the bearer above; every operation is scoped to that
connection's organization. Provisioning **creates/links** users (linking when the email already
exists — users are global, membership is per-org); **deprovisioning is soft** — `active:false` or
`DELETE` disables the account, marks the org membership inactive, and revokes the user's sessions
immediately, but never deletes an audit-linked user (21 CFR Part 11 / GxP). A user employed by two
orgs is only globally disabled once **both** IdPs deprovision them.

## 5. Verification

- After regenerating, confirm `schema.d.ts` exposes the three `/auth/sso/connections/{id}/scim-token`
  operations and the `ScimTokenIssueResponse` / `ScimTokenInfo` components, and that `ScimTokenInfo`
  has **no** `token` field.
- Backend behavior is covered by `moltrace_backend/tests/test_scim_provisioning_api.py` (admin
  gating, plaintext-once, rotation invalidates the old token) — mirror the issue/rotate/revoke
  states in the UI.
