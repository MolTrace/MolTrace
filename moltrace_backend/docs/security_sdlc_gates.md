# Secure-SDLC CI gates (Security Prompt 14)

MolTrace gates every change to `main` with automated security scanning in GitHub Actions. The gates
are **standalone workflows** (no `needs:` coupling to `ci-cd.yml`) so a test failure can never skip a
security gate and the workflow files never contend.

## The gate suite

| Gate | Workflow · job | Tool | Prompt |
|---|---|---|---|
| **Secret scanning** | `secret-scan.yml` · `gitleaks` | gitleaks (pinned + checksum) | P8 |
| **SAST** | `security-scan.yml` · `sast` | Semgrep (`p/python`, `p/javascript`, `p/typescript`, `p/owasp-top-ten`, `p/react`) | P14 |
| **SCA** (deps + license) | `security-scan.yml` · `sca` | Trivy `fs` (vuln + license) over `uv.lock` + `pnpm-lock.yaml` | P14 |
| **IaC** | `security-scan.yml` · `iac` | Trivy `config` over `render.yaml` blueprints + workflows | P14 |

All four run on `push` to `main`, on `pull_request` to `main`, and on `workflow_dispatch`.

## Severity policy — criticals block, the rest is tracked

- **CRITICAL → blocks.** Each `security-scan.yml` job runs a *gate* pass that exits non-zero on a
  CRITICAL (Semgrep ERROR-severity) finding. gitleaks blocks on **any** committed secret.
- **HIGH / MEDIUM / LOW → reported + tracked, not blocking.** Each job also runs a *report* pass that
  uploads **SARIF** to the GitHub **Security → Code scanning** tab, where findings are triaged and
  tracked to closure. This keeps the build green on pre-existing lower-severity findings while making
  them visible and owned.

Rationale: a hard block on every HIGH would red-line the build on day one (e.g. transitive
dependency advisories) and pressure teams to disable the gate. Blocking on CRITICAL only, with
HIGH+ tracked under an SLA, is the CSA/secure-SDLC-aligned posture.

## Triage SLAs (findings → closure)

| Severity | Triage (acknowledge + assign) | Remediation target |
|---|---|---|
| Critical | 24 h | 7 days (or documented compensating control + risk acceptance) |
| High | 3 business days | 30 days |
| Medium | 10 business days | 90 days |
| Low / informational | best-effort | next dependency-maintenance cycle |

Findings live in the **Security → Code scanning** tab (SARIF) and are closed there (fixed,
risk-accepted with justification, or dismissed as false-positive with a reason). A committed secret
(gitleaks) is always treated as a Critical: rotate the credential, then purge history.

## Making the gates block merge

Each job is a normal status check. To **block merge** on a gate, add it as a *required status check*
under **Settings → Branches → branch protection for `main`** (the same one-time step used for the
gitleaks gate): `gitleaks (full history)`, `SAST · Semgrep`, `SCA · Trivy (deps + license)`,
`IaC · Trivy config`. Because `deploy` in `ci-cd.yml` only runs on a green push to `main`, a blocked
PR cannot merge and therefore cannot deploy — so requiring the checks blocks both merge and deploy.

## Deferred / follow-ups (honest scope)

- **DAST on preview deploys** — deferred. The deploy model is Vercel + Render *production* targets
  (no ephemeral per-PR preview environment is wired), so there is no isolated URL to run an
  authenticated DAST pass against without risking production. The seam: once a preview/staging
  environment exists, add a `dast` job (e.g. OWASP ZAP baseline) gated to that URL. Tracked as a
  follow-up rather than faked against production.
- **Tool-version pinning** — Semgrep runs via `uvx` (latest compatible) and Trivy via the
  `aquasecurity/trivy-action` tag. For full supply-chain hardening, pin Semgrep to an exact version
  and the Trivy action to a commit SHA (mirroring the gitleaks version+checksum pin). Newer scanners
  generally mean *more* coverage, so unpinned scanners fail safe (toward more findings), but pinning
  makes the gate reproducible.
- **Known tracked findings at introduction** — `pnpm audit` currently reports HIGH advisories
  (including a Next.js middleware-bypass fixed in `next >= 16.2.5`); these are HIGH, so they are
  tracked (not blocking) and should be remediated by a dependency bump in the frontend per the SLA.
