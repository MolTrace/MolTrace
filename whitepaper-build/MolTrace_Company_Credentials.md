---
title: "MolTrace — Company Credentials"
subtitle: "Partner / Customer Logo Bar · About MolTrace · Trust Seals · Press"
version: "2026-06-07"
audience: "Procurement, due-diligence reviewers, partnership leads, press"
length: "Drop-in front-matter block for white papers, decks, and gated downloads"
---

# MolTrace — Company Credentials

A drop-in front-matter block. Render at the top of any white paper, deck, or gated download. Replace bracketed placeholders with current values before publication.

---

## Partner & Customer Logo Bar

> **Trusted by:**
>
> ```
> ┌────────────────────────────────────────────────────────────────────┐
> │  [Tenant Logo 1]   [Tenant Logo 2]   [Tenant Logo 3]   [Tenant 4]  │
> │  [Tenant Logo 5]   [Tenant Logo 6]   [Tenant Logo 7]   [Tenant 8]  │
> └────────────────────────────────────────────────────────────────────┘
>
> Pilot program participants in pharmaceutical R&D, CRO, biotech, and academic
> analytical chemistry. Public logos shown with tenant consent. Reach out for
> a confidential customer reference call.
> ```

### Logo policy

1. **Public.** Logos shown openly in white papers, decks, and the marketing site after written tenant consent (signed `Tenant_Logo_Consent.docx`).
2. **Confidential reference.** Tenants who decline public listing may agree to confidential customer-reference calls; the tenant is named only after a mutual NDA is in place.
3. **Anonymised.** Tenants who decline both still contribute aggregated, anonymised case data to the cross-tenant ROI rollups (see `MolTrace_ROI_Methodology.md` §6).

### Logo bar SVG placeholder

Replace `assets/logo-bar.svg` with the production asset before publication. The placeholder spec:

- Format: SVG with each logo as a child `<g>` element
- Dimensions: 1600 × 200 px, evenly spaced
- Logo height: 80 px
- Background: transparent
- Filename: `assets/logo-bar.svg`

---

## About MolTrace

**MolTrace Technologies, Inc.** is a venture-backed scientific intelligence company building the audit-ready evidence engine for pharmaceutical R&D. Our platform — SpectraCheck, Regentry, and Reaction Optimization — closes the loop between raw analytical data and regulatory-ready decisions, with every numerical claim along the way reachable and reproducible.

### Quick facts (replace with current values)

| Fact | Value |
|---|---|
| Founded | [Year] |
| Headquarters | [City, State, Country] |
| Team size | [n] employees · [n] PhD-level scientists |
| Stage | [Pre-seed / Seed / Series A / …] |
| Lead investor(s) | [Investor Name(s)] |
| Customer count | [n] tenants across pharma, biotech, CRO, academic |
| Compliance posture | SOC 2 Type II · ICH Compliant · GDPR Ready · GxP Validated |
| Open-source contributions | RDKit · nmrglue · mzML community |
| Press contact | press@moltrace.tech (placeholder — replace) |
| Pilot inquiries | pilots@moltrace.tech (placeholder — replace) |

### Mission

> *"Every scientific decision in pharmaceutical R&D should be reachable from its raw data, reproducible at any future point, and reviewable by both an inspector and an analyst."*

### Founding insight

The pharmaceutical R&D toolchain was assembled, layer by layer, over thirty years of incremental vendor releases. Each layer is excellent at its own job; the layers do not know about each other. The result is an analytical-chemistry workflow where:

- The 1H NMR processor doesn't know what the LC-MS feature detector picked
- The LC-MS feature detector doesn't know what the candidate-comparison engine ranked
- The candidate-comparison engine doesn't know what the regulatory-affairs reviewer will be asked
- None of them know that the FDA's 2025 AI Credibility Framework wants the whole chain reproducible

MolTrace was founded to build **one platform** where the layers know about each other — and where the chain of custody from raw FID to regulatory dossier is reachable by hyperlink end-to-end.

### Architectural commitments

1. **Evidence-first.** Every number is reachable to its source.
2. **Human-in-the-loop, never autonomous.** AI accelerates; humans decide.
3. **Open-science under the hood.** RDKit, nmrglue, mzML, FastAPI — no proprietary file-format lock-in.
4. **Multi-modal by default.** NMR + LC-MS + HRMS + MS/MS are one evidence stack, not separate apps.
5. **Reproducible by construction.** Datasets and model runs are versioned by content hash; every analysis carries a content-hashed output contract that a continuous-integration determinism gate proves regenerates byte-for-byte. A versioned, append-only model registry and a provenance-emitting inference router record exactly which model produced each prediction.

### Leadership

> Replace with current org chart. The white paper publication SLA is: leadership table must be accurate within 30 days of any senior departure or new hire.

| Name | Role | Background |
|---|---|---|
| [Founder Name] | CEO | [Background — PhD field, prior company] |
| [Co-Founder Name] | CTO | [Background] |
| [Co-Founder Name] | CSO | [Background — preferably NMR / MS depth] |
| [Head of Regulatory] | VP Regulatory Affairs | [Background — FDA / EMA experience] |
| [Head of Sales] | VP GTM | [Background] |
| [Head of Engineering] | VP Engineering | [Background] |

### Advisors & Scientific Advisory Board

> Replace with current SAB. Format: Name, Affiliation, area of focus.

- [SAB Member 1] — [Affiliation] — [Area: e.g. computational NMR, DP5 methodology]
- [SAB Member 2] — [Affiliation] — [Area]
- [SAB Member 3] — [Affiliation] — [Area]

### Technology stack

| Layer | Technology |
|---|---|
| Application UI | Next.js 15 · React 19 · TypeScript · Tailwind · shadcn/ui · Plotly |
| API | FastAPI (Python 3.13) · Pydantic |
| Cheminformatics | RDKit |
| NMR ingestion | nmrglue · custom Bruker / Agilent-Varian parsers |
| MS ingestion | mzML / mzXML community standards |
| Database | PostgreSQL (production) · SQLite (local dev) |
| Background jobs | Queue + worker pool |
| Authentication | Tenant-aware opaque bearer sessions · per-organization OpenID Connect SSO (PKCE · JIT provisioning · optional enforce-SSO) · SCIM 2.0 auto-provisioning/deprovisioning · MFA (TOTP + WebAuthn/passkeys) with per-tenant enforcement + step-up re-auth for signing/admin · short-lived access + rotating refresh tokens (reuse detection, immediate revocation) · centralized policy-as-code authorization (deny-by-default policy engine, every decision server-side) · role-based access |
| Hosting | Vercel (frontend) · Render / Railway (backend) · S3-compatible raw vault |
| Observability | Audit-event ledger · request-trace IDs · per-tenant dashboards |
| Reproducibility & MLOps | Content-addressed dataset versioning · experiment / run tracking (params, metrics, dataset-version tag, git SHA, model checksum) · fail-loud data-validation gates (optional DVC · MLflow · Great Expectations) · versioned model registry + 5-layer inference router provenance · licence-clean public-datasets corpus with a frozen holdout · dominance-gated model promotion (ten-metric checksum-locked gold-set eval) · LoRA domain fine-tuning with Bayesian hyper-parameter optimisation (optional Optuna), a confidence-calibration head, and calibration as a hard promotion gate · learned contradiction detection feeding an active-learning queue |

### Open-source contributions

MolTrace's posture is *build on open science where it exists, contribute back where we can*. Active contributions:

- **nmrglue** — Bruker / Agilent edge-case patches
- **RDKit** — chemistry helper extensions (atom-environment fingerprints relevant to the predicted-NMR layer)
- **mzML community** — clarifications + community-test contributions

> Replace with the current contribution list and pull-request links before publication.

### Compliance & audit posture

- **SOC 2 Type II** — independent audit on a 12-month cycle (auditor: [Auditor Name])
- **ICH Q2(R2)** — analytical-procedures validation aligned, including the audit-event ledger, immutable raw vault, and ALCOA+ data-integrity primitives; the platform also generates a deterministic, content-hash-keyed ICH Q2(R2) report stub per analysis
- **GAMP 5 (Appendix D11)** — the platform generates a versioned, byte-reproducible Computerised System Validation document skeleton (intended use, GxP-risk class, requirements-traceability matrix, IQ/OQ/PQ evidence slots) to accelerate customer CSV; the overall compliance determination remains the regulated user's responsibility
- **GDPR** — tenant-private data segregation, right-to-erasure tooling, EU-region data residency
- **GxP Validated** — Computer System Validation (CSV) documentation available under NDA
- **HIPAA-aligned (US)** — for tenants handling protected health information
- **21 CFR Part 11 (US)** — electronic-records / electronic-signatures compliance for FDA-regulated workflows

Replace specific certifications with current attestations as they are renewed.

### Awards & recognition

> Replace with current awards. Examples to populate as won:

- [Award name, year, awarding body]
- [Press mention, publication, year]

### Press

> Replace with current press kit links.

- **Press kit:** [press.moltrace.tech URL placeholder]
- **Brand assets:** [brand.moltrace.tech URL placeholder]
- **Recent coverage:** [Curated list — replace with current]
- **Media inquiries:** press@moltrace.tech (placeholder)

---

## How to embed this block

### In a markdown white paper

Add at the bottom of the document, before the references section:

```markdown
---

## Partner & Customer Logo Bar

![](assets/logo-bar.svg)

## About MolTrace

MolTrace Technologies, Inc. is a venture-backed scientific intelligence
company building the audit-ready evidence engine for pharmaceutical R&D…

[…compressed About MolTrace block from above, ~150 words…]
```

### In a deck

Render the logo bar on slide 3 (right after the title slide and the "Why now" slide). Render the About MolTrace block on the second-to-last slide (right before the call-to-action / pilot-engagement slide).

### In a gated download landing page

Render the logo bar inline above the gate (so the prospect sees it before being asked for an email). Render the About MolTrace block on the post-download confirmation page.

---

## Logo asset checklist (before publishing any tenant logo)

- [ ] Written tenant consent on file (`Tenant_Logo_Consent_<tenant>_<YYYYMMDD>.docx`)
- [ ] Logo file received in vector format (SVG or EPS); fallback PNG at ≥ 1024 px
- [ ] Logo received from the tenant's brand / marketing contact, not from a sales contact
- [ ] Logo rendered against MolTrace's white background passes 4.5:1 contrast
- [ ] Logo appears within the standard logo-bar SVG at the agreed position
- [ ] Tenant's brand-portal terms reviewed (some require approval-per-publication)
- [ ] Tenant given final preview link before any external rollout

---

## Boilerplate copy snippets

Short, medium, and long-form About-MolTrace strings for use in different contexts:

**Short (one sentence, 50 words):**

> MolTrace is an AI-native scientific intelligence platform for pharmaceutical R&D, combining a 40-layer NMR + MS evidence engine, an immutable raw-data vault, and FDA AI Credibility Framework–aligned reporting — so every analytical claim in a regulatory submission is reachable, reproducible, and reviewable.

**Medium (three sentences, 100 words):**

> MolTrace builds the audit-ready evidence engine for pharmaceutical R&D. Our platform — SpectraCheck, Regentry, and Reaction Optimization — closes the loop between raw analytical data and regulatory-ready decisions across NMR, LC-MS, HRMS, and MS/MS, with every numerical claim along the way reachable from a single click. The company is venture-backed, headquartered in [City], with SOC 2 Type II compliance, ICH Q2(R2) alignment, and an architecture engineered to satisfy the FDA's 2025 AI Credibility Framework and the EMA AI reflection paper.

**Long (six sentences, 200 words):**

> MolTrace Technologies, Inc. is a venture-backed scientific intelligence company building the audit-ready evidence engine for pharmaceutical R&D. Our platform fuses NMR (1H, 13C, 2D), raw FID processing, HRMS, MS/MS, and LC-MS feature data into a single forty-layer evidence stack, with an immutable SHA-256-hashed raw archive, citation-linked chemical-shift windows, and a human-in-the-loop release gate aligned with the FDA's January 2025 AI Credibility Framework and the EMA reflection paper on AI in medicinal product lifecycle. Founded by analytical chemists and software engineers from pharmaceutical and biotech backgrounds, the company is headquartered in [City] with a global remote engineering team and a Scientific Advisory Board that includes domain leaders in computational NMR, regulatory affairs, and reaction optimisation. Our technology stack is built on community-supported open science (RDKit, nmrglue, mzML) wrapped in the multi-tenant, audit-first SaaS architecture pharma R&D now requires. MolTrace is operational with [n] tenants across pharmaceutical R&D, biotech, contract research organisations, and academic analytical chemistry. Pilot programs run on a thirty-day cycle and convert order-of-magnitude ROI claims into measured tenant-specific evidence per the published `MolTrace_ROI_Methodology.md` measurement protocol.

---

## Companion documents

- **MolTrace White Paper — Hybrid** — comprehensive technical + business overview
- **MolTrace White Paper — Sales** — business case forward
- **MolTrace White Paper — Technical** — extended scientific foundations
- **MolTrace Executive One-Pager** — single-page summary
- **MolTrace ROI Methodology** — measurement protocol for tenant data

*© 2026 MolTrace Technologies, Inc. Replace all bracketed placeholders with current values before any external publication. Logo and credentials accuracy is the responsibility of the publishing team; the last-verified-on date should be recorded in every external use.*
