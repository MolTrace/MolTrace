# OWASP API Security Top-10 (2023) — coverage map (Security Prompt 16)

How MolTrace's controls map to the OWASP API Security Top-10. P16 newly enforces the
resource-consumption controls; most other items were already addressed by earlier security prompts.
This is the ASVS-aligned review artefact — these controls **support** an ASVS posture; a formal,
third-party ASVS assessment + the edge WAF rollout (`waf_edge_runbook.md`) remain operator
follow-ups.

| API risk | Status | Control |
|---|---|---|
| **API1 — Broken Object Level Authorization** | Covered | P5 deny-by-default policy engine (`authz.py`) + `_baseline_access_gate`; per-owner scoping (e.g. dossiers via `created_by_user_id` + non-leaking 404s). |
| **API2 — Broken Authentication** | Covered | Argon2id (P6), MFA + step-up (TOTP/WebAuthn), rotating refresh tokens with reuse detection, SSO/OIDC; abuse-prone auth endpoints now also rate-limited (P16). |
| **API3 — Broken Object Property Level Authorization** | Covered | Pydantic request models with `ConfigDict(extra="forbid")` (mass-assignment defense) on the request surface; server-authoritative fields (e.g. e-signature signer, soft-delete actor) never trust client-supplied identity. |
| **API4 — Unrestricted Resource Consumption** | **Newly enforced (P16)** | In-app per-tenant + per-route **rate limiter** (token bucket, 429 + `Retry-After`/`X-RateLimit-*`); **global request-body-size guard** (413, multipart exempt); existing upload caps (`raw_archive_max_bytes/files`, allowed-extension allowlist) and list-result bounds (`limit ≤ 500`). |
| **API5 — Broken Function Level Authorization** | Covered | `require_admin` / `require_step_up` gates; policy engine decides per-endpoint; new endpoints inherit the baseline gate by default. |
| **API6 — Unrestricted Access to Sensitive Business Flows** | Partial | The auth-endpoint rate limits (P16) throttle credential-stuffing / reset-spam / enumeration; richer bot/anomaly detection is an edge-WAF concern (runbook). |
| **API7 — Server-Side Request Forgery** | Mapped | Outbound fetches are limited to configured providers (SSO discovery/JWKS over allow-listed issuers; no user-controlled URL fetch in the request path). Re-review on any new outbound-fetch feature. |
| **API8 — Security Misconfiguration** | Covered | Security response headers + HSTS (P9), secret-scanning + SAST/SCA/IaC CI gates (P8/P14), signed supply chain (P15), CORS allow-list, sanitized error bodies (no secret/credential leakage). |
| **API9 — Improper Inventory Management** | Covered | OpenAPI schema is the binding contract (regenerated per change); CHANGELOG + per-prompt docs; CycloneDX SBOM per build (P15). |
| **API10 — Unsafe Consumption of APIs** | Mapped | Third-party integrations (SSO IdP, Sigstore) are validated (JWKS id_token verification, keyless attestation verify); SCA tracks third-party dependency advisories (P14). |

## Output encoding

FastAPI serializes responses as JSON (auto-encoded — no injection surface). The one raw-HTML surface,
the e-signature manifestation (`esign.render_manifestation_html`), HTML-escapes every interpolated
value. No other endpoint reflects unescaped user input into HTML.

## Deliberately deferred / edge

- **WAF (OWASP CRS, IP reputation, L7 DDoS, bot rules)** — network-edge control (Render has no
  built-in WAF); delivered as the Cloudflare/Vercel runbook, not faked in-app.
- **Cross-instance rate limiting** — the in-process store is per-worker; a Redis-backed
  `RateLimitStore` is the documented drop-in if the backend scales beyond one worker.
- **Formal ASVS audit + DAST** — operator follow-ups (DAST also deferred in `security_sdlc_gates.md`
  pending a preview environment).
