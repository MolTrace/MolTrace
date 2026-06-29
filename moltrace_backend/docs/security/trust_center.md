# MolTrace Trust Center

**Security Prompt 22.** The customer-facing security posture summary + sub-processor
register — the content a published Trust Center page serves so prospects can self-serve
trust artifacts. (Publishing this as a web page at moltrace.co is operational/front-end;
this file is the source content.)

> **Compliance framing.** MolTrace ships controls **designed to support** SOC 2, ISO
> 27001, 21 CFR Part 11, GxP, and GDPR workflows. These controls **support, and do not
> by themselves certify,** a customer's compliance posture; the overall compliance
> determination and computerized-system validation remain the customer's responsibility.
> **MolTrace does not currently hold a SOC 2 report or an ISO 27001 certificate.**

## Certifications & framework status

| Framework | Status |
|---|---|
| SOC 2 Type II | **Pursuing** — controls designed to support the Trust Services Criteria; not yet audited/held |
| ISO/IEC 27001:2022 | **Mapped / aligned** to Annex A; not yet certified |
| ISO/IEC 27017 + 27018 | Cloud / PII-in-cloud extensions — would accompany an ISO 27001 certification |
| 21 CFR Part 11 / GAMP 5 / ALCOA+ | Controls **designed to support**; customer owns validation/SOPs |
| GDPR | Processor controls **designed to support** the customer's Art. 33/34 obligations |

A live control-coverage map (machine-checked) backs these claims:
[`compliance_controls_map.md`](compliance_controls_map.md) /
[`compliance/controls.json`](../../../compliance/controls.json).

## Security posture at a glance

- **Access** — per-organization OpenID Connect SSO + SCIM auto-provision/deprovision,
  MFA (TOTP + WebAuthn/passkeys) with step-up re-auth, deny-by-default policy-as-code
  authorization, Argon2id password hashing, rotating refresh tokens with reuse detection.
- **Data protection** — field-level envelope encryption (KMS-wrapped AES-256-GCM, BYOK
  seam), HSTS/TLS 1.3, per-tenant isolation, ALCOA+ controlled records, a write-once raw
  vault.
- **Integrity & traceability** — a tamper-evident hash-chained audit ledger, 21 CFR
  Part 11 e-signatures, a GAMP 5 / CSA validation lifecycle.
- **Detection & response** — SIEM security detections (impossible travel, privilege
  escalation, cross-tenant access, audit-chain break), an incident-response program with
  a GDPR breach-notification deadline engine, coordinated vulnerability disclosure
  ([security.txt](https://moltrace.co/.well-known/security.txt) + a
  [VDP](vulnerability_disclosure_policy.md)).
- **Secure delivery** — secret-scanning + SAST + SCA + IaC CI gates, a signed supply
  chain (SBOM + SLSA provenance, verify-at-deploy), SHA-pinned least-privilege CI, CSPM
  IaC drift detection.
- **Resilience** — documented RTO/RPO with a restore-integrity verifier and restore-drill
  runbook.

Full document set under [`docs/security/`](.): threat model, pen-test program, findings
register, SIEM detections, incident response + runbooks + breach notification, zero-trust
infra, backup/DR, WAF runbook, OWASP API Top-10, secure-SDLC gates, supply-chain
provenance.

## Sub-processor register

MolTrace uses the following sub-processors. (Customers are notified of material changes
per their DPA; this list is the in-repo source for the published register.)

| Sub-processor | Purpose | Data handled | Region/notes |
|---|---|---|---|
| **Render** | Backend API hosting + managed Postgres + second-region FE mirror | All tenant data at rest, the audit ledger, security events, encrypted IdP/MFA secrets, the raw-data vault | DB reached over an internal connection string; provider holds its own SOC 2/ISO attestations |
| **Vercel** | Primary frontend hosting (moltrace.co) | Browser session traffic / proxied API requests; no first-party database | — |
| **Customer-configured IdP** (e.g. Okta, Microsoft Entra) | Enterprise SSO (OIDC) + SCIM provisioning | Authentication assertions + provisioning lifecycle | Customer-owned federation, not MolTrace-operated |
| **GitHub** | Source hosting + CI/CD (Actions) | Source code + build artifacts; CI secrets (deploy hooks); keyless Sigstore provenance — **no production tenant data** | — |
| **Hosted SIEM + paging** _(operational, optional)_ | Security-alert log ingest + 24/7 on-call | Forwarded security-alert logs | e.g. Datadog/Splunk + PagerDuty/Opsgenie; configured per deployment |

## Requesting trust artifacts

Security questions, the disclosure policy, and (when available) audit reports under NDA:
report security issues per [`SECURITY.md`](../../../SECURITY.md) /
[security.txt](https://moltrace.co/.well-known/security.txt); commercial/trust inquiries
to the contact published on moltrace.co. A published Trust Center page (self-serve
artifacts + the live sub-processor list) is the operational front-end of this content.
