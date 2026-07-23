# Zero-Trust Infrastructure Posture

**Security Prompt 18.** MolTrace's hosted product runs on **managed cloud** — Google
Cloud (project `moltrace-prod`, region `us-central1`: the backend API on **Cloud Run**,
managed Postgres 16 on **Cloud SQL**, the raw-data vault on **Cloud Storage**, secrets in
**Secret Manager**, field-encryption keys in **Cloud KMS**) and Vercel (frontend,
moltrace.co). On managed serverless infrastructure, much of "zero-trust infrastructure" —
CIS *host* hardening, physical security, runtime-protection agents — is **owned by the
platform**, and the rest — the VPC, cloud IAM, ingress policy — is **configured
operationally against the cloud APIs**, not declared in this repository.

> **Platform of record:** Google Cloud, since the July 2026 Render → GCP migration.
> The root `render.yaml` is **stale legacy** and no longer describes production; the
> authoritative topology is the verified
> [GCP deploy runbook](../../deploy/README.md).

This runbook states the **honest posture**: what is enforced in-repo (and therefore
auditable here), what the platform owns, what is operational config, and what remains an
open gap. It is the infrastructure companion to the [threat model](threat_model.md), the
[secure-SDLC gates](../security_sdlc_gates.md), the
[supply-chain provenance](../supply_chain_provenance.md) doc, and the in-repo
[CSPM IaC drift gate](../../../infra/cspm/README.md).

## Shared-responsibility map

| Zero-trust control | Owner | Status |
|---|---|---|
| **IaC posture scoring + drift detection** (CSPM-lite) | In-repo | ✅ `infra/cspm/` + the `iac` CI job — continuously scored, **drift-alerted** (fails CI on any new HIGH/CRITICAL IaC misconfig). Scope caveat: it sees the *repo's* declarative files, not the live GCP project (see below) |
| **Least-privilege CI / no long-lived keys** | In-repo | ✅ keyless Sigstore OIDC signing, per-job `permissions:`, SHA-pinned actions, **keyless WIF backend deploy** (P15 + this prompt) |
| **No committed secrets** | In-repo | ✅ gitleaks over **full git history** (P8), env-required admin default, Secret Manager–injected DB/API creds |
| **Tamper-resistant pipeline** (pinned actions, no `pull_request_target`) | In-repo | ✅ every `uses:` SHA-pinned (9 distinct actions); deploy/attest gated to `push`→`main` |
| **Network segmentation** | Google Cloud (operational) | ✅ dedicated VPC (`moltrace-vpc` / `moltrace-subnet`, `10.10.0.0/24`); the Cloud Run service is the **only** public surface; Postgres and the vault are not internet-reachable |
| **Private networking / VPC peering** | Google Cloud (operational) | ✅ **implemented** — Cloud SQL has **no public IP** (`--no-assign-ip`) and lives on a private IP behind a VPC peering to `servicenetworking`; Cloud Run reaches it via **Direct VPC egress** (`--vpc-egress private-ranges-only`). Configured by `gcloud`, not declared in-repo |
| **Cloud IAM (no long-lived keys)** | In-repo + Google Cloud | ✅ backend deploy is **keyless Workload Identity Federation** — GitHub's OIDC token is exchanged for `moltrace-deployer@`; **no service-account key exists** to steal. Runtime SA `moltrace-run@` holds three narrow roles. The Vercel FE still deploys via an opaque hook secret |
| **CIS host / OS hardening** | Google Cloud | Platform — Cloud Run manages the sandboxed host; we run no VMs. **But** the container's own OS layer is now first-party (see below) |
| **Physical / data-center security** | Google Cloud | Platform — Google-operated `us-central1` (United States); nothing in this repo's scope |
| **Container/image vulnerability scanning** | In-repo | ❌ **Open gap** — applicable since the Cloud Run migration. Trivy `config` scans the Dockerfile for *misconfiguration*; **nothing scans the built image for CVEs**. See "Container image scanning" below |
| **Runtime protection (RASP/agent)** | Operational | TODO — app-layer compensating controls exist (rate limiter, audit chain, fail-closed gates); a runtime agent is a platform/operational add |
| **CSPM auto-remediation** | Operational | TODO — drift is **scored + alerted (fail-closed)** in-repo today; safe auto-remediation of cloud-account drift is an operational add |

## What's enforced in-repo

### 1. IaC posture scoring + drift detection (CSPM-lite)

The `iac` job in `.github/workflows/security-scan.yml` runs Trivy `config` over the
repository's declarative infrastructure — the GitHub Actions workflows, the backend
[`Dockerfile`](../../Dockerfile), and the legacy `render.yaml` still sitting at the root.
Beyond Trivy's own CRITICAL hard-block, the
[`infra/cspm/score_iac_posture.py`](../../../infra/cspm/score_iac_posture.py) gate
scores the result against a **committed baseline** and **fails CI on any new
HIGH/CRITICAL misconfiguration** not already accepted. The baseline
(`iac_posture_baseline.json`) is currently **empty — a clean posture**. This is the
"posture continuously scored, drift alerted" half of the prompt's acceptance
criterion; accepting a finding is a deliberate, reviewed `--update` with a
justification, mirroring the [`.trivyignore` VEX register](../../../.trivyignore).

**Honest scope limit.** This gate scores *files in this repo*. The production GCP
topology — VPC, Cloud SQL flags, bucket policy, IAM bindings, Cloud Run flags — is
created by **imperative `gcloud` commands** recorded in the
[deploy runbook](../../deploy/README.md), not by Terraform or Config Connector. There is
therefore **no declarative artifact for the live cloud posture to be scored against**, and
in-console drift would not fail CI. Closing that is an operational add (see TODOs).

### 2. Least-privilege, keyless, tamper-resistant pipeline

- **No long-lived signing keys.** Provenance signing is fully keyless: the `attest`
  job mints a short-lived Fulcio cert via GitHub Actions OIDC (`id-token: write`) —
  no stored key, no external account (P15).
- **No long-lived deploy keys.** The `deploy-backend` job authenticates to Google Cloud
  the same way: GitHub's OIDC token is exchanged through **Workload Identity Federation**
  (pool `github`, provider `github-oidc`, restricted to
  `assertion.repository == 'MolTrace/MolTrace'`) for short-lived
  `moltrace-deployer@moltrace-prod` credentials. **No service-account JSON key exists**
  anywhere — not in CI, not in a password manager, not on a laptop. This is materially
  stronger than the deploy-hook secrets it replaced: the trust is bound to a *repository
  and workflow identity* and the credential expires in minutes, so exfiltrating a repo
  secret no longer yields deploy authority.
- **Least-privilege tokens.** `ci-cd.yml` defaults to `permissions: { contents: read }`;
  only `attest` (`id-token`/`attestations: write`), `verify-provenance`
  (`attestations: read`) and `deploy-backend` (`id-token: write`, for the WIF exchange)
  scope up. `security-scan.yml` adds only `security-events: write` (SARIF upload);
  `secret-scan.yml` is `contents: read` only.
- **Pinned actions.** Every `uses:` is pinned to a 40-char **commit SHA** (with the
  human-readable tag in a trailing comment for Dependabot), so a hijacked upstream
  tag can't flow into CI. This closes the P14-deferred pinning follow-up.
- **No `pull_request_target`.** All workflows use the safe `pull_request`; deploy and
  attestation jobs are gated to `push` on `main`, so a PR can neither deploy nor mint
  an attestation.

### 3. No long-lived human or cloud credentials in the repo

- Every runtime secret lives in **Secret Manager** and is mounted by reference at deploy
  time (`gcloud run deploy --set-secrets DATABASE_URL=DATABASE_URL:latest,…`), never as a
  literal: the DB connection string, `API_KEY`, `ADMIN_EMAILS`, `AUDIT_SIGNING_KEY`,
  `SSO_ENCRYPTION_KEY`, `MFA_ENCRYPTION_KEY`, `PASSWORD_PEPPER`. The field-encryption
  master key is held in **Cloud KMS**, wrapping the envelope keys used by the P7
  field-crypto module.
- **Backend deploy authority is keyless** — Workload Identity Federation, no stored
  service-account key (section 2). The Vercel FE deploy is still an opaque hook URL held
  as a GitHub repo secret; no Vercel account admin key is in CI either.
- **Runtime least privilege.** The Cloud Run service runs as `moltrace-run@` with exactly
  three roles — `cloudsql.client`, `secretmanager.secretAccessor`, `storage.objectAdmin` —
  and the deployer identity is separate from the runtime identity. This is operational
  IAM recorded in the [deploy runbook](../../deploy/README.md), not something this repo
  can enforce.
- The application admin allowlist defaults **empty / env-required** (no built-in admin).
- gitleaks scans the **full history** on every push (P8), so a committed secret blocks
  the build.

## Network & segmentation reality

The Cloud Run service `moltrace-backend` (uvicorn, health check `/health`, port 8080) is
the **only** internet-reachable component. It is deliberately `--allow-unauthenticated`,
because it serves a browser application — authentication and authorization are app-layer
(deny-by-default PDP, MFA/step-up, rotating sessions), not network-layer.

Everything behind it is private:

- **Cloud SQL `moltrace-db`** (Postgres 16) has **no public IP** at all. It sits on a
  private address inside `moltrace-vpc` via a VPC peering to `servicenetworking`, and the
  service reaches it over **Direct VPC egress** (`--network moltrace-vpc --subnet
  moltrace-subnet --vpc-egress private-ranges-only`) — no Serverless VPC connector, no
  public path to disable. This is a genuine improvement over the previous PaaS posture,
  where private networking was unimplemented and the DB's external-access toggle was a
  console setting nothing in the repo could assert.
- **The raw-data vault** is a Cloud Storage bucket (`gs://moltrace-raw-vault`) created
  with **uniform bucket-level access**, **public-access prevention**, and object
  versioning; only the runtime service account can read or write it.
- **Scaling shape:** `--cpu 2 --memory 2Gi --concurrency 80 --min-instances 0
  --max-instances 2`. Two consequences worth stating plainly: the service **scales to
  zero** (no idle host to attack, but also cold starts), and there can be **up to two
  instances**, so in-process state is no longer guaranteed to be a single process. The
  token-bucket rate limiter keeps its buckets per-process, so under fan-out the effective
  ceiling is up to 2× the nominal rate; `rate_limit.py` already isolates this behind a
  `RateLimitStore` protocol so a shared store can drop in. See the
  [WAF edge runbook](waf_edge_runbook.md).

Two production targets fan out from one gated `main` push: Vercel (FE) and Cloud Run (BE,
plus the `moltrace-migrate` Cloud Run Job that applies Alembic deltas before the revision
rolls). The VPC, peering, IAM bindings, bucket policy and Cloud Run flags are **operational
`gcloud` config** recorded in the [deploy runbook](../../deploy/README.md), not declared in
this repository.

The app sits behind Google's managed front end (hence
`RATE_LIMIT_TRUST_FORWARDED_FOR=true`) — and that edge has **no WAF**. The native option is
now **Cloud Armor**, which is available but **not enabled**, and which requires an external
HTTPS load balancer in front of the service; that residual is covered by the
[WAF edge runbook](waf_edge_runbook.md).

One more consequence of moving to a serverless container: **Cloud Run's filesystem is
ephemeral**, so the local raw-vault's `0o444` write-once mode is a *local-dev* construct
that does not apply in production (`RAW_VAULT_BACKEND=gcs`). Object immutability in
production is bucket-side configuration — versioning and public-access prevention today —
not a filesystem permission bit, and not something this repo enforces.

## Container image scanning — applicable now, and NOT yet wired (open gap)

Earlier revisions of this runbook recorded container scanning as an honest **N/A**: Render
built a slug from buildpacks and no Dockerfile was tracked. **That is no longer true, and
the N/A is withdrawn.**

MolTrace now builds and ships a first-party container image. [`moltrace_backend/Dockerfile`](../../Dockerfile)
is a two-stage build on `python:3.13-slim`; Cloud Build pushes it to Artifact Registry as
`us-central1-docker.pkg.dev/moltrace-prod/moltrace/backend:<sha>`, and `gcloud run deploy`
rolls that exact digest. The same image backs the API, the migration job, and (when
enabled) the worker.

**What is covered today**

- **Dockerfile misconfiguration** — Trivy `config` in the `iac` job scans the Dockerfile
  (that is a *misconfiguration* check: build-practice rules, not CVEs). The image already
  applies the expected hardening: a non-root `app` user (uid 10001), the build toolchain
  discarded with the build stage, and lockfile-frozen (`uv sync --frozen`) installs.
- **Declared dependencies** — Trivy `fs` in the `sca` job reads `uv.lock` and
  `pnpm-lock.yaml`, blocking on CRITICAL (with the [`.trivyignore`](../../../.trivyignore)
  VEX register for accepted findings).

**What is NOT covered — the gap**

Nothing scans the **built image**. That leaves the image's **OS layer** unexamined: the
`python:3.13-slim` base and the runtime packages installed into it (`libgomp1`,
`libxrender1`, `libxext6`, plus their transitive Debian dependencies). Those CVEs are
invisible to a lockfile-based `fs` scan, and they are now *first-party* — a stale base
image is our unpatched surface, not the platform's. This is a **real, currently-missing
control**, tracked as such in the table above.

**The seam (concrete, not hypothetical)**

1. In `deploy-backend` (`.github/workflows/ci-cd.yml`), between *Build + push image
   (Cloud Build)* and *Deploy new revision*, add a Trivy **`image`** scan of `$IMAGE`,
   mirroring the existing two-pass shape: a HIGH,CRITICAL SARIF report pass plus a
   CRITICAL `exit-code: 1` gate pass. Placement matters — it must run **before**
   `gcloud run deploy`, so a vulnerable image cannot roll, and before the
   `moltrace-migrate` execution if it should block the whole release.
2. Or enable **Artifact Analysis** (Artifact Registry automatic vulnerability scanning) on
   the `moltrace` repo for continuous, out-of-band rescanning of already-pushed digests —
   this catches CVEs *disclosed after* the build, which a build-time scan structurally
   cannot.
3. Do both, ideally, and fold the findings into the same CSPM drift baseline discipline:
   accepted image findings recorded with a justification rather than silently ignored.
4. Patching is a **rebuild** — bump the base image and redeploy; there is no in-place
   `apt upgrade` on an immutable revision.

**Host/OS below the container is still Google's.** Cloud Run manages the sandboxed
execution environment and the physical estate; CIS *host* hardening remains
platform-owned. The line has simply moved: everything **inside** the image is ours.

## Open gaps and TODOs (honestly scoped)

**In-repo (we own these):**

- **Container image vulnerability scanning.** Not wired. This is the one control the
  platform migration *created*; the seam is spelled out above.
- **Branch protection.** The scanning gates (gitleaks, SAST, SCA, IaC + CSPM drift) only
  *block merge* once added as **required status checks** on `main` — a one-time GitHub
  setting (noted in each workflow header).
- **Retire `render.yaml`.** It is stale legacy that no longer describes production, yet it
  is still scanned by the `iac` job. Leaving it invites reading it as current.

**Operational / platform (outside this repo):**

- **Declarative IaC for the GCP topology.** The live posture is built by imperative
  `gcloud`, so the CSPM gate has nothing to score it against. Expressing the VPC, Cloud
  SQL, bucket, IAM and Cloud Run config as Terraform (or Config Connector) would bring the
  production posture *inside* the existing drift gate.
- **Cloud-account CSPM + safe auto-remediation.** Continuous scoring of the live
  GCP/Vercel/GitHub account configuration — org policies, IAM bindings, bucket and Cloud
  SQL settings — and auto-remediation where safe. Security Command Center is the native
  GCP option; the in-repo gate covers only repository files.
- **Edge WAF (Cloud Armor).** Available, not enabled; requires an external HTTPS load
  balancer in front of Cloud Run, after which ingress can also be restricted to
  `internal-and-cloud-load-balancing`. See the [WAF edge runbook](waf_edge_runbook.md).
- **Runtime protection agent.** App-layer controls (token-bucket rate limiter, body-size
  guard, tamper-evident audit chain, fail-closed release gates, deny-by-default authz) are
  the compensating controls today. Note that Cloud Run does not accept host-level agents at
  all, so this is a sidecar/eBPF-free design question, not a "install the agent" task.
- **Shared rate-limit state.** With `--max-instances 2` the in-process limiter is
  per-instance; a Redis-backed store (Memorystore) is deliberately deferred on cost.
