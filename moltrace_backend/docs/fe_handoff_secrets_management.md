# FE Handoff — Security Prompt 8: Secrets management

**TL;DR: no frontend action required.** This is CI tooling + a backend config seam. No route,
request/response model, status code, or `schema.d.ts` contract changed. `/openapi.json` is
unchanged — nothing to regenerate.

## What changed (backend / CI only)

- A **secret-scanning CI gate** (`.github/workflows/secret-scan.yml`, gitleaks) now blocks the
  build on any committed secret, plus a matching **pre-commit hook** (`.pre-commit-config.yaml`).
- A **secrets-provider seam** (`nmrcheck.secrets_provider`) is the single read-point for
  credential-class env vars (DATABASE_URL, REDIS_URL, API_KEY, SSO/MFA encryption keys, password
  pepper). The default backend reads `os.environ` exactly as before; a managed store
  (Vault / AWS / GCP) and short-lived dynamic DB credentials are a documented swap point behind
  `SECRETS_BACKEND` (no behavior change in v1).

There is no schema change and no API surface change — every endpoint behaves identically.

## For frontend developers (local tooling, optional)

If you commit from the repo root and want the same secret-scan safety locally:

```
pipx install pre-commit && pre-commit install
```

This is optional and affects only local commits; it does not change any app behavior.

## Verification

- `schema.d.ts`: **do not regenerate** — `/openapi.json` unchanged.
- Backend suite green incl. `tests/test_secrets_provider.py`.

No FE checklist items. Logged for the BE→FE record only.
