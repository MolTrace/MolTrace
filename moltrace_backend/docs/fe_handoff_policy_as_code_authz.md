# FE Handoff — Security Prompt 5: Policy-as-code authorization

**TL;DR: no frontend action required.** This is a backend-internal authorization
centralization. No route signature, request/response model, status code, or
`schema.d.ts`-affecting contract changed. `/openapi.json` is unchanged, so there is nothing
to regenerate.

## What changed (backend only)

Authorization decisions that were scattered across route dependencies and inline store-scope
checks are now made by one embedded, Cedar-style policy-decision point (`nmrcheck/authz.py`,
`authz.authorize`). The existing gates (`require_dossier_access`, `require_admin`,
`_readable_via_parent_dossier`, `_user_scope_for_context`) were refactored to **delegate** to
it. The encoded rules are byte-identical to before:

- a **system api key** and an **admin** user are unrestricted;
- a **user** may read/write only resources they own (`created_by_user_id == user_id`);
- a non-owner read returns the same **non-leaking 404** as a missing resource;
- a privilege/role gate returns **403**.

## The one behavior to be aware of (already matches today's contract)

A new **router-level default-deny baseline** now applies to every route on the main API
router: any route that is not in an explicit public allow-list requires an authenticated
principal. For the FE this changes nothing — every product route already required auth, and
the public set is exactly what it was (health/system probes, `/auth/*` login-family,
`/fid/presets`, `/share-links/{token}`). The only observable effect is defensive: a future
backend route that forgets its auth dependency now returns **401** to an anonymous caller
instead of leaking, rather than the FE having to defend against it.

Status codes the FE already handles are unchanged:

| Situation | Status | Notes |
|---|---|---|
| Anonymous → any product route | `401` | unchanged (`PUBLIC_AUTH_REQUIRED_DETAIL`) |
| Authenticated non-owner → someone else's dossier | `404` | unchanged, non-leaking |
| Non-admin → admin route | `403` | unchanged (`PUBLIC_ACCESS_DENIED_DETAIL`) |
| Owner / admin / system → owned/admin route | `200` | unchanged |

## Verification

- `schema.d.ts`: **do not regenerate** — `/openapi.json` is unchanged.
- Backend suite (incl. `tests/test_authz_policy_matrix.py`,
  `tests/test_authz_route_regression_api.py`, and all dossier/admin/auth scoping tests) is green.

No FE checklist items. File logged for the BE→FE record only.
