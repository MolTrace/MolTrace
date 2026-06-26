# MolTrace Threat Model (STRIDE)

**Security Prompt 17.** A living, code-grounded threat model of the MolTrace
backend attack surface, organized by trust boundary and by STRIDE category
(**S**poofing, **T**ampering, **R**epudiation, **I**nformation disclosure,
**D**enial of service, **E**levation of privilege). It is the reference for the
pre-major-release and new-surface threat-modeling required by the
[pen-test program runbook](pentest_program.md), and the
[new-surface checklist](#new-surface-checklist) at the bottom is the gate authors
run before shipping a new external surface.

This document describes controls that **support** regulated workflows; it is not a
compliance attestation. Cited file paths are under `moltrace_backend/src/nmrcheck/`
unless noted and are accurate as of this release — treat them as starting points,
not guarantees, when reviewing.

## System context & trust boundaries

```
 Internet ──▶ platform edge (Render / Vercel reverse proxy) ──▶ single uvicorn FastAPI worker
                                                                  │
   ┌──────────────────────────────────────────────────────────────┼───────────────────────────┐
   │ default-deny router gate (_baseline_access_gate)              │                           │
   │   public allow-list ─┐    authenticated ─┐   admin/system ─┐  │                           │
   ▼                      ▼                    ▼                 ▼  ▼                           ▼
 IdP (OIDC, outbound)  SCIM (inbound machine) DB (SQLAlchemy)  KMS/KEK (envelope crypto)  raw-vault FS (write-once)
```

Key trust boundaries:

- **Internet → app.** No network-edge WAF on the hosted platform (the in-app
  token-bucket limiter in `rate_limit.py` is the only abuse control; see the
  [WAF edge runbook](waf_edge_runbook.md)). Client IP is only trustworthy when
  `rate_limit_trust_forwarded_for` is set (first `X-Forwarded-For` hop, behind a
  trusted proxy).
- **Unauthenticated → authenticated.** Every router route crosses
  `_baseline_access_gate` (deny-by-default); only `PUBLIC_ROUTE_PATHS` is exempt.
  A new route inherits the gate and fails closed (401) unless its template is
  explicitly added to the public allow-list (pinned by
  `test_authz_route_regression_api`).
- **User → admin/system.** `authz.principal_from_access_context` collapses the
  system api key → SYSTEM (unrestricted), `is_admin` → ADMIN (unrestricted), else
  USER (owner-scoped).
- **Session bearer / step-up.** Opaque access + rotating refresh tokens stored only
  as SHA-256 digests (`session_store.py`); signing/admin actions require a fresh
  step-up stamp (`require_step_up`).
- **App ↔ IdP (OIDC)**, **IdP/provisioning → app (SCIM)**, **app ↔ KMS** (envelope
  crypto), **app ↔ DB**, **app ↔ write-once raw vault** (`raw_vault.py`),
  **CI/CD → deploy** (Sigstore provenance gate).
- **Audit ledger.** `audit_events` + anchors + chain head are immutable (no delete
  path); integrity rests on a per-row SHA-256 chain + HMAC anchors keyed by
  `AUDIT_SIGNING_KEY`.

## Assets worth protecting

Password hashes (Argon2id, optional KMS pepper); access/refresh tokens & session
families (digest-at-rest); MFA secrets (TOTP seeds AES-256-GCM at rest, WebAuthn
keys + sign counts, recovery-code digests); IdP client secrets + per-connection
SCIM bearers; envelope-crypto key material (KEK, `AUDIT_SIGNING_KEY`, system
api-key, pepper); e-signature records (content-bound digests + §11.50
manifestations); the tamper-evident audit ledger; the write-once raw spectra vault;
per-user tenant isolation (dossiers/projects scoped by `created_by_user_id`); and
the CI signing identity + deploy-hook secrets.

## STRIDE by surface

Each row: the threat, the control already in place, and the **residual risk** a
pen test / review should probe.

### Auth & session (`security.py`, `session_store.py`)

- **S — credential spoofing.** Login returns an identical 401 for bad-password vs
  unverified-email (no user-enumeration oracle). Argon2id hashing with legacy
  PBKDF2 verify + rehash-on-login. *Residual:* `is_admin` is auto-granted at login
  when the email matches `is_admin_email` — the admin-email allowlist is a
  high-value target; keep it tightly held and out of config dumps. A federated
  tenant with a weak *local* password is a parallel spoofing path unless enforce-SSO
  + local-factor enforcement are both set.
- **T — token tampering.** Access/refresh tokens are opaque and stored only as
  SHA-256 digests; refresh rotation with reuse-detection revokes the whole family.
- **E — elevation.** `local_auth_disabled=True` makes *every* request a system
  principal — a deployment-config crown jewel; must never be set in a multi-tenant
  prod.

### SSO / OIDC (`oidc_client.py`, `sso_store.py`)

- **S/T — token forgery.** `id_token` signature/iss/aud/exp/nonce validated against
  the IdP JWKS; Authorization Code + PKCE; one-time exchange code → bearer.
  *Residual:* JIT provisioning trusts IdP-asserted identity — a compromised IdP or a
  mis-scoped `slug` is an account-takeover path; enforce-SSO + connection scoping
  are the mitigations.

### SCIM provisioning (`scim_store.py`, `scim_router`)

- **S — bearer theft.** A per-connection SCIM bearer (SHA-256 digest at rest,
  org-scoped) authorizes an org's entire user lifecycle. *Residual:* a leaked SCIM
  bearer = full org provisioning (create/disable users → indirect ATO); tokens have
  optional expiry only and the fast kill-switch is disabling the SSO connection.
  Rotate SCIM tokens; prefer short expiries. The SCIM router is also rate-limited
  (`_abuse_rate_limit_gate`).

### MFA / step-up (`mfa_totp.py`, `mfa_webauthn.py`, `mfa_store.py`)

- **S — second-factor bypass / brute force.** The login challenge is burned
  *before* factor verification (closes the brute-force oracle); TOTP has a
  last-used-step replay guard; WebAuthn requires user verification + detects
  sign-count clones. Recovery codes are valid for login but **never** for step-up,
  so a stolen recovery code cannot reach signing. *Residual:* enrollment/recovery
  flows are the soft underbelly — probe recovery-code generation and re-enrollment.

### E-signature (Part 11) (`esign.py`)

- **R/T — repudiation / signature transfer.** Signer identity is the **server
  principal** (client-supplied name/email ignored); the signature digest binds a
  SHA-256 of the exact signed record (§11.70 non-transferable); step-up factor/AAL
  is stamped. *Residual:* legacy unbound signatures honestly return `bound=False`
  and the manifestation flags them "not cryptographically verifiable" — ensure the
  UI never presents an unbound signature as verified.

### Dossier RBAC / tenant isolation (`authz.py`, `require_dossier_access`)

- **I — cross-tenant read/write.** Deny-by-default PDP with non-leaking 404s; dossier
  reads *and* writes (incl. by-child-id) go through ownership checks. *Residual:* the
  per-user model is only as good as gate coverage — **any new dossier-touching or
  child-producing route must apply `require_dossier_access` /
  `_readable_via_parent_dossier`** (three query-param leaks were found and closed in
  v0.23.x; assume the next one is one forgotten gate away). This is the #1 thing the
  new-surface checklist guards.

### Secure share links — anonymous capability URLs (`collaboration_store.py`)

- **I — anonymous read of shared content.** `GET /share-links/{token}` is public
  (`PUBLIC_ROUTE_PATHS`): the unguessable token in the path *is* the bearer — a
  distinct anonymous-bearer trust boundary, no session required. *Control:* a
  high-entropy token, plus expiry and revocation on the share-link record.
  *Residual:* a capability URL leaks through browser referer headers, proxy/access
  logs, and chat/email forwarding; if token entropy is weak it is enumerable. A pen
  test should probe token entropy, expiry enforcement, revocation, and whether a
  revoked/expired token still discloses the record. It is IP-rate-limited like other
  public routes, but rate limiting is not a substitute for entropy.

### Rate-limit / abuse (`rate_limit.py`)

- **D — resource exhaustion.** In-app token bucket keyed `principal|ip × route`,
  429 + `Retry-After`; tight policies on `/auth/*`; body-size guard (413). Bucket map
  bounded (100k, idle/LRU eviction) so the limiter isn't itself a memory sink.
  *Residual:* limiter is in-process + fail-open and single-worker-consistent only; a
  distributed flood across many keys is the edge WAF's job, which **does not exist**
  on the hosted platform — a documented residual DoS exposure. The body-size guard
  **exempts multipart**, so a large upload is bounded by `raw_archive_max_bytes` (a
  2 GB default, validated `>= 1`) — but that cap is enforced **after** the full body
  is buffered, not as a pre-stream edge limit, so a flood of large uploads can still
  cause transient memory pressure before rejection; the edge/proxy upload limit (see
  the [WAF edge runbook](waf_edge_runbook.md)) is the real mitigation.

### File upload + write-once raw vault (`raw_vault.py`)

- **T/D — traversal / zip-bomb / tamper.** Archive parsing enforces safe member
  names (no path traversal), rejects symlinks/devices, and caps bytes/files/
  uncompressed size (zip-bomb defense). Uploaded archives are `chmod 0o444` and
  SHA-256-verified on every read. *Residual:* integrity rests on filesystem
  read-only + hash-on-read; an attacker with host/FS access bypasses read-only and
  the only detection is the at-read hash check (blocks processing, not deletion).

### Audit ledger (`audit_chain.py`)

- **T/R — ledger forgery.** Per-row SHA-256 chain + HMAC-sealed anchors + a signed
  high-water mark (insert/edit/delete/reorder/truncate all break recomputation),
  covering ~244 write sites via one `before_flush` listener;
  `GET /admin/audit/verify` + a reconciliation job alert on breaks. *Residual:* the
  whole non-repudiation guarantee reduces to **`AUDIT_SIGNING_KEY` secrecy** — the
  dev fallback key must never reach prod; an attacker with both DB write *and* the
  signing key can re-forge the chain.

### Supply chain / CI (`.github/workflows/`)

- **T/E — build tampering.** SBOM per build, SLSA provenance signed keylessly via
  Sigstore, a `verify-provenance` gate the deploy job `needs:`; workflows are
  push/PR on `main` only (no `pull_request_target`, so no fork-secret exposure);
  least-privilege token scoping. *Residual:* the platform rebuilds the artifact
  downstream **outside** the attested boundary — provenance attests the SBOM/source
  at the gated commit, not the deployed binary (documented honest gap).

### Admin surface (`require_admin`, `require_admin_step_up`)

- **E — privilege escalation.** SYSTEM (x-api-key, compared with `hmac.compare_digest`)
  is unrestricted and bypasses rate limits **and** step-up (the audited break-glass
  path). ADMIN is unrestricted on the PDP and bypasses rate limits, but
  admin-mutating / signing actions **still require a fresh step-up**
  (`require_admin_step_up` — only the system api key bypasses it; an admin *user* has
  no step-up special-case). *Residual:* the x-api-key and the `is_admin_email`
  allowlist are the crown-jewel elevation targets — an attacker who controls an
  admin-listed email or the system key escalates fully.

## <a id="new-surface-checklist"></a>New-surface threat-model checklist

Run this before shipping a **new externally reachable surface** (a new route family,
auth path, integration boundary, or upload). Capture the answers in the PR; anything
unmitigated becomes an entry in the
[security findings register](security_findings_register.md).

- [ ] **Auth floor.** Does the route sit on the gated `router` (inherits
      `_baseline_access_gate`)? If it must be public, is its template added to
      `PUBLIC_ROUTE_PATHS` *and* the pinned regression test — a deliberate, reviewed
      act? (Avoid `app.get`, which bypasses the gate and the rate limiter.)
- [ ] **Tenant isolation.** Does it touch dossiers/projects/analyses or any
      owner-scoped resource? If so, does it apply `require_dossier_access` /
      `_readable_via_parent_dossier` / an ownership check, returning a **non-leaking
      404** (never 403-with-detail) for cross-tenant access?
- [ ] **Privilege.** Admin/system-only? Gated by `require_admin` /
      `require_admin_step_up`? Does a privileged or signing action require step-up?
- [ ] **Input & abuse.** Untrusted input validated (Pydantic `extra="forbid"`)? Is
      it covered by the rate limiter (on `router`, not a bypassing sub-app)? Does it
      accept an upload — and if so, are size/zip-bomb/traversal caps applied (it is
      **not** covered by the multipart-exempt body-size guard)?
- [ ] **Secrets & crypto.** Does it read/write a secret (IdP secret, MFA seed, token)?
      Is it routed through envelope encryption (`field_crypto`) and never logged?
- [ ] **Auditability.** Do state changes land in the audit chain (covered
      automatically by the `before_flush` listener — confirm the write goes through
      the ORM session, not a raw bypass)?
- [ ] **Disclosure surface.** Do error paths leak stack traces, internal ids, or
      cross-tenant existence? Are 401/403 bodies sanitized?
- [ ] **STRIDE pass.** Walk S/T/R/I/D/E for the new trust boundary; record residual
      risk + the accepted justification.
