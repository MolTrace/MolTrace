# Data Residency & Region Pinning

**Security Prompt 23.** Where MolTrace tenant data actually lives today, what "region
pinning" would require, and the honest gap between the two.

> **Honest boundary.** MolTrace today runs as a **single-region** deployment in
> **`us-central1` (United States)**. There is **no tenant-level region pinning** in the
> product: every tenant's data lives in the same managed database in the same US region.
> Multi-region residency is an **infrastructure + product change**, not a configuration
> flag — so a customer with an **EU-residency requirement cannot be satisfied today**, and
> this page says so rather than implying a capability.

## Where data lives today

Production runs on **Google Cloud, project `moltrace-prod`, region `us-central1`
(United States)** — migrated off Render in July 2026.

| Data | Where | Notes |
|---|---|---|
| All tenant data at rest, the audit ledger, security events, encrypted IdP/MFA secrets | **Cloud SQL for PostgreSQL 16**, private IP, reached via Direct VPC egress | `us-central1`; no public IP |
| Raw-data vault (vendor archives) | **Cloud Storage** (`RAW_VAULT_BACKEND=gcs`) — immutable by bucket policy | `us-central1`. (The local filesystem `0o444` write-once mode applies only to non-serverless deployments; Cloud Run's filesystem is ephemeral.) |
| Backend API | **Cloud Run** (FastAPI, scale-to-zero) | `us-central1`; see [`zero_trust_infra.md`](zero_trust_infra.md) |
| Secrets / key material | **Secret Manager** + **Cloud KMS** (field-encryption key) | `us-central1` |
| Primary frontend | **Vercel** (`moltrace.co`) | Edge-distributed static/SSR; stores no first-party database |
| Source, CI, build artifacts | **GitHub Actions** (+ Artifact Registry / Cloud Build) | No production tenant data |

> ℹ️ The legacy `render.yaml` blueprints have been **deleted** from the repo (they described the
> retired Render setup). Treat the README deployment section + this page as authoritative.

Sub-processors and what each handles are enumerated in the
[Trust Center register](trust_center.md#sub-processor-register). Cross-border transfer
questions are answered from that register plus the customer's DPA.

## What "region-pinned tenant data" would require

Pinning a tenant to a region is not a per-row setting; it needs all four:

1. **A regional data plane** — a database (and object store) per region, provisioned in
   that region, with backups and DR restores that stay in-region
   (see [`backup_dr.md`](backup_dr.md) — cross-region backup replication is itself still
   an operational seam).
2. **A tenant→region binding** — an authoritative mapping, resolved *before* any data
   access, so a request for tenant X is routed to X's regional store and can never
   silently fall back to another region.
3. **Request routing + a fail-closed guard** — the edge routes by tenant region; a lookup
   that cannot resolve a region must **fail closed**, never default to the home region.
4. **Residency-aware ancillary paths** — the pieces that quietly cross regions otherwise:
   log/SIEM forwarding, email delivery, backups, exports, support tooling, and any
   AI/model call. Each is a residency leak if left unpinned.

## Honest status of each piece

| Requirement | Status |
|---|---|
| Regional data plane | **Not implemented** — single region |
| Tenant→region binding | **Not implemented** — no region attribute on the tenant model |
| Region-aware routing + fail-closed guard | **Not implemented** |
| Residency-aware logging / backup / email / AI paths | **Not implemented** (single region today, so nothing crosses — but nothing enforces it either) |
| Sub-processor transparency | ✅ [Trust Center register](trust_center.md#sub-processor-register) |
| Data map (what personal data exists, where) | ✅ [`privacy_data_map.md`](privacy_data_map.md) |

## Interim posture (what a customer can rely on today)

- A single, named region for all tenant data — **`us-central1`, United States** — stated
  plainly rather than implied to be configurable.
- **Cross-border transfer:** because the region is in the US, processing of EU personal
  data involves a third-country transfer under GDPR Chapter V. The transfer mechanism the
  customer relies on (SCCs, and/or the EU–US Data Privacy Framework where the sub-processor
  is certified) is set in the customer's DPA. **This repo asserts no transfer mechanism on
  the customer's behalf** — it is a contractual determination, not a product control.
- Encryption at rest and in transit, field-level envelope encryption for classified
  secrets, and per-user isolation enforced server-side by a deny-by-default policy engine.
- A published sub-processor register, so cross-border processing by sub-processors is
  visible and answerable per data subject under Art. 15(1)(c).
- A documented [personal-data map](privacy_data_map.md) and DSAR/erasure workflow.

**What a customer should not infer:** that data can be pinned to their region on request,
or that a residency commitment can be met by configuration today. It cannot — it requires
the build above.

## Cross-references

[`privacy_data_map.md`](privacy_data_map.md) · [`trust_center.md`](trust_center.md) ·
[`zero_trust_infra.md`](zero_trust_infra.md) · [`backup_dr.md`](backup_dr.md) ·
[`breach_notification.md`](breach_notification.md)
