# Ops — Secrets Management (Security Prompt 8)

How MolTrace resolves credential-class secrets, and how to adopt a managed secrets store
(HashiCorp Vault / AWS Secrets Manager / GCP Secret Manager) or dynamic short-lived database
credentials **without changing application code** — the provider interface is the swap point.

## The seam

`nmrcheck.secrets_provider` is the single read-point for secrets:

- `resolve_secret(name, *, default=None)` — `os.getenv(name) or default` semantics (empty string
  collapses to `default`). Used for `REDIS_URL`, `API_KEY`, `SSO_ENCRYPTION_KEY`,
  `MFA_ENCRYPTION_KEY`, `PASSWORD_PEPPER`.
- `resolve_secret_strict(name, default=None)` — two-arg `os.getenv` semantics (default applied
  only when the key is **absent**, not when empty). Used for `DATABASE_URL`.
- `SECRETS_BACKEND` env var selects the backend; unset/`env`/unknown → the `EnvSecretsProvider`
  (reads `os.environ`). This is the v1 default and is byte-for-byte identical to the prior
  `os.getenv(...)` reads — so nothing changes operationally until you opt in.

A backend implements one method:

```python
class SecretsProvider(Protocol):
    def get(self, name: str) -> str | None: ...   # value, or None on miss — never raises
```

Returning `None` on a miss lets `resolve_secret` apply the caller's `default` uniformly, so a
managed backend degrades exactly like `os.getenv`.

## Adopting a managed store (v2)

1. Implement a backend class with `get(self, name) -> str | None`.
2. Register it in `secrets_provider._BACKENDS`, e.g. `_BACKENDS["vault"] = VaultSecretsProvider`.
   Import the cloud SDK **inside** the backend module so it is only loaded when selected (v1
   ships no cloud SDK).
3. Set `SECRETS_BACKEND=vault` (or `aws` / `gcp`) in the deployment environment.

Sketch backends:

- **HashiCorp Vault** — `hvac` client; `VAULT_ADDR` + AppRole (`VAULT_ROLE_ID` /
  `VAULT_SECRET_ID`) or Kubernetes auth; `get("API_KEY")` reads e.g.
  `secret/data/moltrace/API_KEY`.
- **AWS Secrets Manager** — `boto3` `secretsmanager.get_secret_value`; IAM role on the task; the
  secret name maps to a secret id / prefix.
- **GCP Secret Manager** — `google-cloud-secret-manager`; `access_secret_version` on
  `projects/<p>/secrets/<name>/versions/latest`; workload-identity auth.

## Dynamic, short-lived database credentials (Vault DB secrets engine)

For `DATABASE_URL`, a Vault backend's `get("DATABASE_URL")` can call the **database secrets
engine** role (`database/creds/moltrace-app`) to mint a short-TTL user/password and assemble a
`postgresql://v-<role>-<random>:<short-pw>@host/db` connection string on each fetch. Operational
notes:

- Set the lease TTL / max-TTL on the Vault role; plan lease **renewal vs. re-fetch** on
  reconnect.
- `get_settings()` is `@lru_cache`d, so a process re-fetch on lease expiry needs a cache clear or
  a worker recycle — this is the one operational caveat to schedule around rotation.
- Ad-hoc DB scripts that use `get_settings().database_url` inherit dynamic creds for free;
  anything reading bare `os.environ["DATABASE_URL"]` bypasses the seam — always go through
  settings / the provider.

## What ops configure today (v1, env backend)

- Keep secrets in Render's secret store / GitHub Actions Secrets (already the case).
- `.env*` stays git-ignored; only `.env*.example` templates are tracked.
- `SECRETS_BACKEND` unset ⇒ the env backend ⇒ behavior identical to before this change.
- Production startup guards still require `API_KEY`, `SSO_ENCRYPTION_KEY`, and
  `MFA_ENCRYPTION_KEY` to resolve to non-empty values regardless of backend.

## Secret scanning (no secret in code/config)

- CI: `.github/workflows/secret-scan.yml` runs **gitleaks** (pinned + checksum-verified binary)
  over the full git history and **blocks the build** on any finding (`--exit-code 1`).
- Local: `.pre-commit-config.yaml` runs the same gitleaks version on staged changes
  (`pipx install pre-commit && pre-commit install`).
- Both read the single-sourced `.gitleaks.toml` allowlist (audit-confirmed dev placeholders,
  test fixtures, templates, generated files only).
- If a scan ever surfaces a **real** credential: rotate it at the source, purge from history if
  warranted, and only then add a precise allowlist entry for a confirmed false positive — never
  broaden a regex to mask a live secret.
