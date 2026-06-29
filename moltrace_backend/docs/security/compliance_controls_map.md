# Compliance Controls Map (SOC 2 + ISO 27001)

**Security Prompt 22.** A readable map of MolTrace's in-repo security controls to the
**SOC 2 Trust Services Criteria** and **ISO/IEC 27001:2022 Annex A**. The
machine-checkable source of truth is [`compliance/controls.json`](../../../compliance/controls.json)
(validated by [`validate_controls.py`](../../../compliance/validate_controls.py) — every
cited evidence path must resolve, so this map can't silently rot).

> **This is a control-coverage / readiness self-assessment — NOT an attestation.**
> SOC 2 and ISO 27001 are *audited* outcomes: an independent CPA's report (SOC 2
> Type I = design; Type II = operating effectiveness over a window) or an accredited
> body's certificate (ISO 27001). **MolTrace does not currently hold a SOC 2 report or
> an ISO 27001 certificate.** The controls below are **designed to support** those
> frameworks; only an auditor's report/certificate confers assurance. Per MolTrace's
> standing rule, SOC 2/ISO/Part 11/GxP/GDPR are framed "designed to support", never as
> held facts.

## Framework status

| Framework | Status |
|---|---|
| SOC 2 Type II | **Not held** — designed to support; pursuing |
| ISO/IEC 27001:2022 | **Not held** — controls mapped to / aligned with Annex A |
| ISO/IEC 27017 + 27018 (cloud / PII extensions) | **Not held** — would be certified alongside an ISO 27001 ISMS |

## In-repo controls → criteria

Each control links to its evidence in the register. SOC 2 codes: **CC1–CC9** (common
criteria) + **A1** Availability · **C1** Confidentiality · **PI1** Processing Integrity ·
**P1** Privacy. ISO 27001:2022 Annex A themes: **A.5** Organizational · **A.6** People ·
**A.7** Physical · **A.8** Technological.

| Control | SOC 2 | ISO A.x | Built in |
|---|---|---|---|
| RBAC deny-by-default policy-decision point | CC6 | A.5, A.8 | P5 |
| Argon2id password hashing | CC6 | A.8 | P6 |
| Field-level envelope encryption + KMS/BYOK seam | CC6, C1 | A.8 | P7 |
| Committed-secret scanning + secrets-management seam | CC6, CC8 | A.8 | P8 |
| TLS / transport security headers | CC6 | A.8 | P9 |
| Tamper-evident audit hash chain | CC7, PI1 | A.8 | P10 |
| 21 CFR Part 11 e-signature binding & manifestation | CC6, PI1 | A.8 | P11 |
| ALCOA+ controlled-records primitives | PI1, C1 | A.8 | P12 |
| GAMP 5 / CSA validation lifecycle + change control | CC8, PI1 | A.8 | P13 |
| Secure-SDLC CI gates (SAST/SCA/IaC) | CC8 | A.8 | P14 |
| Signed supply chain (SBOM + SLSA + verify-at-deploy) | CC8 | A.8 | P15 |
| Per-tenant + per-route rate limiting + body guard | CC6, CC7, A1 | A.8 | P16 |
| Coordinated vulnerability disclosure + pen-test program | CC4, CC7 | A.5, A.8 | P17 |
| Zero-trust infra: CSPM IaC drift + least-privilege CI | CC7, CC8 | A.8 | P18 |
| Security detections engine + SIEM sink | CC7 | A.8 | P19 |
| Incident-response program + GDPR breach engine | CC7, P1 | A.5 | P20 |
| Backup / DR restore-integrity verifier | A1, CC7 | A.5, A.8 | P21 |
| Enterprise SSO (OIDC) + encrypted IdP secrets | CC6 | A.5, A.8 | — |
| SCIM 2.0 provisioning (auto-deprovision) | CC6 | A.5 | — |
| MFA / passkeys / step-up | CC6 | A.8 | — |
| Session hardening (rotating refresh + reuse detection) | CC6 | A.8 | — |

**Coverage:** the product strongly evidences SOC 2 **CC6** (logical access),
**CC7** (system operations / detection / IR), **CC8** (change management), and
**Processing Integrity** + **Availability**, plus ISO 27001 **A.8** (technological) and
the technical slice of **A.5**.

## Inherited & operational controls (not in-repo evidence)

These complete the picture but are **not** product controls — the register marks them
`inherited` or `operational`, and they are evidenced by a sub-processor's attestation or
by management process, not by code:

| Control | Type | Provided by | SOC 2 / ISO |
|---|---|---|---|
| Physical & data-center security | inherited | Render + Vercel (their SOC 2 / ISO attestations) | CC6 / A.7 |
| HR screening, security-awareness training | operational | internal HR process | CC1 / A.6 |
| Governance, risk register & risk assessment | operational | management process | CC1, CC3 / A.5 |
| Vendor / sub-processor risk management + DPAs | operational | vendor-risk register + DPAs | CC9 / A.5 |
| Continuous-compliance tooling + the audits | operational | Vanta/Drata + an independent auditor | CC4 / A.5 |
| 24/7 on-call paging + hosted SIEM ingest | operational | PagerDuty/Opsgenie + Datadog/Splunk (in-repo detections feed these) | CC7 / A.8 |

## How this is used

A continuous-compliance platform (Vanta/Drata) maps its automated evidence collectors
onto this register; the audit then tests operating effectiveness. The register's
fail-on-drift validator keeps the control→evidence links honest between audits. See the
customer-facing [Trust Center](trust_center.md) for the posture summary + sub-processor
list.
