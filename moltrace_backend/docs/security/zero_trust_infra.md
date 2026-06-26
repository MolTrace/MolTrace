# Zero-Trust Infrastructure Posture

**Security Prompt 18.** MolTrace's hosted product runs on **managed PaaS** — Render
(backend API + a second-region frontend mirror + managed Postgres) and Vercel
(primary frontend). On a PaaS, much of "zero-trust infrastructure" — private
networking, network segmentation, cloud IAM, CIS *host* hardening, runtime-protection
agents — is **provided or owned by the platform**, not declared in this repository.

This runbook states the **honest posture**: what is enforced in-repo (and therefore
auditable here), what the platform owns, and what remains an operational TODO. It is
the infrastructure companion to the [threat model](threat_model.md), the
[secure-SDLC gates](../security_sdlc_gates.md), the
[supply-chain provenance](../supply_chain_provenance.md) doc, and the in-repo
[CSPM IaC drift gate](../../../infra/cspm/README.md).

## Shared-responsibility map

| Zero-trust control | Owner | Status |
|---|---|---|
| **IaC posture scoring + drift detection** (CSPM-lite) | In-repo | ✅ `infra/cspm/` + the `iac` CI job — continuously scored, **drift-alerted** (fails CI on any new HIGH/CRITICAL IaC misconfig) |
| **Least-privilege CI / no long-lived keys** | In-repo | ✅ keyless Sigstore OIDC signing, per-job `permissions:`, SHA-pinned actions, deploy via opaque hooks (P15 + this prompt) |
| **No committed secrets** | In-repo | ✅ gitleaks over **full git history** (P8), env-required admin default, platform-injected DB/API creds |
| **Tamper-resistant pipeline** (pinned actions, no `pull_request_target`) | In-repo | ✅ every `uses:` SHA-pinned (9 distinct actions); deploy/attest gated to `push`→`main` |
| **Network segmentation** | Render/Vercel | Platform — single public API worker + managed Postgres over an internal connection string (only private resource); no internal services exposed |
| **Private networking / VPC peering** | Render | Platform-config — not declared in `render.yaml` |
| **Cloud IAM (no long-lived human keys)** | Render/Vercel/GitHub consoles | Operational — no cloud-provider admin keys live in CI (deploy is via per-service hook URLs held as repo secrets) |
| **CIS host / OS hardening** | Render/Vercel | Platform — the PaaS builds and hardens the runtime image/host; we don't manage VMs |
| **Container/image scanning** | — | **N/A** — MolTrace ships **no Dockerfile**; Render builds the slug from `runtime: python`/`node` buildpacks. See "No image to scan" below |
| **Runtime protection (RASP/agent)** | Operational | TODO — app-layer compensating controls exist (rate limiter, audit chain, fail-closed gates); a runtime agent is a platform/operational add |
| **CSPM auto-remediation** | Operational | TODO — drift is **scored + alerted (fail-closed)** in-repo today; safe auto-remediation of cloud-account drift is an operational add |

## What's enforced in-repo

### 1. IaC posture scoring + drift detection (CSPM-lite)

The `iac` job in `.github/workflows/security-scan.yml` runs Trivy `config` over the
declarative infrastructure (`render.yaml` blueprints + the GitHub Actions workflows).
Beyond Trivy's own CRITICAL hard-block, the
[`infra/cspm/score_iac_posture.py`](../../../infra/cspm/score_iac_posture.py) gate
scores the result against a **committed baseline** and **fails CI on any new
HIGH/CRITICAL misconfiguration** not already accepted. The baseline
(`iac_posture_baseline.json`) is currently **empty — a clean posture**. This is the
"posture continuously scored, drift alerted" half of the prompt's acceptance
criterion; accepting a finding is a deliberate, reviewed `--update` with a
justification, mirroring the [`.trivyignore` VEX register](../../../.trivyignore).

### 2. Least-privilege, keyless, tamper-resistant pipeline

- **No long-lived signing keys.** Provenance signing is fully keyless: the `attest`
  job mints a short-lived Fulcio cert via GitHub Actions OIDC (`id-token: write`) —
  no stored key, no external account (P15).
- **Least-privilege tokens.** `ci-cd.yml` defaults to `permissions: { contents: read }`;
  only `attest` (`id-token`/`attestations: write`) and `verify-provenance`
  (`attestations: read`) scope up. `security-scan.yml` adds only `security-events:
  write` (SARIF upload); `secret-scan.yml` is `contents: read` only.
- **Pinned actions.** Every `uses:` is pinned to a 40-char **commit SHA** (with the
  human-readable tag in a trailing comment for Dependabot), so a hijacked upstream
  tag can't flow into CI. This closes the P14-deferred pinning follow-up.
- **No `pull_request_target`.** All workflows use the safe `pull_request`; deploy and
  attestation jobs are gated to `push` on `main`, so a PR can neither deploy nor mint
  an attestation.

### 3. No long-lived human or cloud credentials in the repo

- DB connection string is **platform-injected** (`fromDatabase`), never a literal.
- The backend `API_KEY` is **platform-generated** (`generateValue: true`).
- Deploy authority is delegated to **opaque per-service deploy-hook URLs** held as
  GitHub repo secrets — no Render/Vercel account admin keys in CI.
- The application admin allowlist defaults **empty / env-required** (no built-in admin).
- gitleaks scans the **full history** on every push (P8), so a committed secret blocks
  the build.

## Network & segmentation reality

A single Render `starter` backend web worker (one uvicorn process, public, health
check `/health`) fronts the API. The only private backing resource is the managed
Postgres (`moltrace-db`), reached over Render's **internal connection string** — it is
a backing service for the backend, not an internet-exposed deploy target. Three real
production targets fan out from one gated `main` push (Vercel primary FE, Render
second-region FE mirror, Render BE API). VPC/peering, the DB's external-access toggle,
and Render's "Auto-Deploy = No" toggles are **platform-side config** not expressible in
`render.yaml`. The app sits behind Render's edge proxy (hence
`RATE_LIMIT_TRUST_FORWARDED_FOR=true`) — and that edge has **no WAF**, the documented
residual covered by the [WAF edge runbook](waf_edge_runbook.md).

## No image to scan (honest N/A)

"Container/image scanning + runtime protection" assumes a container artifact. MolTrace
builds **none**: Render's `runtime: python` / `runtime: node` buildpacks build the slug
internally and there is **no tracked Dockerfile**. So there is no first-party image
layer to scan in CI, and host/OS hardening (CIS) is the platform's responsibility. The
seam, if MolTrace ever containerizes: add a Trivy `image` scan of the built image to
`ci-cd.yml` (mirroring the existing `fs`/`config` scans) and fold its findings into the
same CSPM drift baseline.

## Operational TODOs (outside this repo, honestly scoped)

- **Cloud-account CSPM + safe auto-remediation.** The in-repo gate scores and alerts on
  *IaC* drift fail-closed; continuous scoring of the live Render/Vercel/GitHub account
  configuration (and auto-remediation where safe) is an operational add against those
  consoles' APIs.
- **Runtime protection agent.** App-layer controls (token-bucket rate limiter, body-size
  guard, tamper-evident audit chain, fail-closed release gates, deny-by-default authz)
  are the compensating controls today; a host/runtime security agent is a platform add.
- **Private networking hardening.** Restricting the managed DB's external access and any
  VPC/peering is platform-config to be set in the Render console.
- **Branch protection.** The scanning gates (gitleaks, SAST, SCA, IaC + CSPM drift) only
  *block merge* once added as **required status checks** on `main` — a one-time GitHub
  setting (noted in each workflow header).
