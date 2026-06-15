# MolTrace

> The unified intelligence platform for chemical and pharmaceutical R&D — one audit-grade evidence stack from the first hit spectrum to the IND dossier.

![Python](https://img.shields.io/badge/Python-3.13_runtime-3776AB?logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?logo=typescript&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Frontend: Vercel](https://img.shields.io/badge/Frontend-Vercel-000000?logo=vercel&logoColor=white)
![Backend: Render](https://img.shields.io/badge/Backend-Render-46E3B7?logo=render&logoColor=white)

MolTrace is an AI-native scientific intelligence platform that confirms structures, profiles impurities, and optimizes reaction routes — without ever losing the trail back to the raw data. It is built for pharmaceutical R&D teams, regulatory affairs professionals, CRO/analytical labs, and academic researchers who need evidence they can defend.

The platform is architected **deterministic-first**: regulated math and classifications are computed by a version-pinned rule engine, an auditable verifier is the sole arbiter of correctness, and AI is strictly advisory — it proposes, the science decides.

> **Status.** MolTrace runs as a hosted product at [moltrace.co](https://moltrace.co) (frontend on Vercel, backend on Render). `moltrace_backend/CHANGELOG.md` is the authoritative per-release record of what shipped; the repo's in-code version numbers are not yet unified across the two apps, so treat the CHANGELOG as the source of truth for "what's in production."

## The platform

MolTrace presents three modules around one unified evidence trail, with a closed loop: spectroscopy evidence becomes ICH-classified regulatory action items, which become reaction-optimization constraints, which inform the next experiment — all linked by recipe-hash reproducibility and an ALCOA+ audit ledger. The three modules are surfaced in a single tabbed Programs workspace in the signed-in app.

### SpectraCheck — Spectroscopy Intelligence
*Route: `/spectracheck` (marketing page at `/spectroscopy`)*

Raw FID → processed spectrum → peaks classified by category, with audit-grade fit metrics per peak.

- **GSD deconvolution** (Prompt-3 pseudo-Voigt forward/backward region fit) over levels 1–5, via `POST /spectrum/analyze/gsd`.
- **Multiplet detection and J-coupling recovery** with opt-in conformer-averaged Karplus ³J refinement (Haasnoot–de Leeuw–Altona generalized relation + Boltzmann conformer-population weighting), via `POST /spectrum/analyze/multiplets`.
- **Chemical-shift prediction** from the NMRNet SE(3)-equivariant model (optional, lazily-loaded torch backend) behind an always-available HOSE-code / NMRShiftDB2 topological fallback, via `POST /spectrum/predict/shifts`.
- **LC-MS / MS/MS evidence studios** with CSI:FingerID (MS/MS → structure via SIRIUS, optional), retention-time corroboration, and DP4-AI posterior scoring; candidates fuse into one calibrated ranking.
- **FAISS spectrum retrieval** (Gaussian-smoothed 256-D encoding + HNSW index, Kuhn–Munkres set similarity) via `POST /spectrum/retrieve`, plus retrieval-augmented reasoning via `POST /spectrum/reason`.
- **Quantitative integration and qNMR purity** (Sum / Edited Sum / Peaks; internal-standard + PULCON with GUM uncertainty), NUS reconstruction (IST-S baseline + optional JTF-Net), and a Fulmer/Gottlieb-backed solvent/impurity classifier.

### Regentry — ICH · FDA · EMA
*Route: `/regulatory-hub` (in-app: a tab in the Programs workspace)*

Closes the loop between spectroscopy evidence and regulatory action: dossiers, traceability, an ALCOA+ audit ledger, and ICH Q2(R2) alignment. Every classification is deterministic and tied to a content-hashed `rule_set_version`.

- **ICH Q3A/B** threshold calculator and **Q3C(R8)** residual-solvent classifier over a curated 44-solvent subset of the ICH Q3C(R8) table (all Class 1, the common Class 2, and representative Class 3 solvents); solvents outside the subset return `matched=false`, never a guessed limit.
- **ICH Q3D(R2)** elemental-impurity PDEs (oral / parenteral / inhalation routes encoded; cutaneous explicitly returns *not-encoded*).
- **ICH M7(R2)** mutagenic-impurity classifier and the flagship **FDA/EMA CPCA nitrosamine** potency classifier with the FDA Rev-2 cumulative-risk rule (`sum(measured/AI) < 1`).
- **Unified assessment** via `POST /regulatory/impurities/assess` plus per-dossier sub-resources, action queue, change/rule-update workspaces, source library + version timeline, and surveillance dashboard.
- **CTD Module 3** bundle generation and a nitrosamine cumulative-risk rollup card.
- **Process capability & SPC trending** — a stateless `POST /regulatory/spc/analyze` and a dossier **Process Capability** panel chart a parameter's measurement series: capability indices (Cp/Cpk/Pp/Ppk/Cpm) against spec limits, plus Western Electric / Nelson / Montgomery, CUSUM, and EWMA signals, surfacing the early-warning lead when drift is flagged before an out-of-spec point. Maps to FDA Stage-3 Continued Process Verification / ICH Q6A; decision-support, never a batch disposition.
- **EU GMP _Draft_ Annex 22 AI-decision governance** — a tamper-evident, hash-chained per-dossier AI-decision log with human-in-the-loop gating on high-risk decisions (`GET`/`POST /regulatory/dossiers/{id}/ai-decisions`, `…/verify`); the CPCA, M7, and Q3D classifications auto-record their decisions, risk-tiered. The Annex is in draft and not in force — decision-support governance, not a compliance claim.
- **Owner-scoped dossiers.** Dossier reads and writes are scoped per user (a system key or admin is unrestricted); a non-owner gets a non-leaking 404, so dossier evidence stays isolated.
- Two **zero-tolerance hard gates** guard the engine: calculation error rate must be 0 and formula coverage must be 100%.

### Repho — Reaction Optimization
*Route: `/reaction-optimization`*

Turns regulatory action items into reaction-optimization constraints: Bayesian, ML-guided next-experiment recommendations under impurity limits.

- **Gaussian-process surrogate modelling** with Bayesian multi-objective optimization (yield / selectivity / impurity level).
- **Regulatory impurity constraints as hard limits**, fed directly from Regentry.
- **Uncertainty quantification** on each iteration with model-diagnostics.
- **Automated next-experiment recommendations** over a batch of candidate experiments per optimization cycle.
- A **compound-linking panel** and regulatory-constraints panel tie experiments back to the evidence trail.
- Backend engine: `nmrcheck/reaction_bo.py` (`run_bayesian_optimization`).

## Architecture

MolTrace is a two-app monorepo:

- **Backend** (`moltrace_backend/`) — a single FastAPI service (package `nmrcheck`, app title "NMRCheck API"). The HTTP layer (`src/nmrcheck/`) carries routes, Pydantic models, SQLAlchemy ORM, Alembic migrations, auth, and RQ/Redis background jobs; `api.py` is a large monolithic module. Two modular science packages sit under `src/moltrace/`: `moltrace.spectroscopy` (NMR/MS science + AI model lifecycle) and `moltrace.regulatory` (the ICH/FDA impurity engine).
- **Frontend** (`moltrace_frontend/`) — a single Next.js 16 / React 19 App Router app serving both the public marketing site and the signed-in product from one codebase, with an installable PWA shell.

**The science layer** (`moltrace.spectroscopy`) is deterministic and verifier-centered: `verify_structure` runs four independent tests (PredictionBounds, Assignments, HSQC2DRanges, MSMoleculeMatch) and combines them via a Bayesian log-odds update into an auditable posterior. This deterministic verifier is the **sole arbiter** of correctness across the whole stack.

**The AI model lifecycle** (`moltrace.spectroscopy.ai/eval/data/feedback/ops`) adds a versioned append-only model registry, a provenance-emitting inference router (LoRA fine-tuned → NMRNet pretrained → deterministic HOSE fallback) that records per-prediction the layer used and why, an evaluation harness with a dominance gate over a checksum-locked gold set, LoRA fine-tuning, Bayesian HPO (Optuna), confidence calibration with ECE as a promotion gate, closed-loop RLHF/A-B testing (a Bradley–Terry reward model that only re-ranks *within* a verifier verdict class), active learning, and a fail-closed four-check deployment gate (dominance / audit-chain / tests-green / data-leakage) wired into CI.

**The regulatory engine** (`moltrace.regulatory`) is deterministic-first throughout: regulated numbers come from a version-pinned rule engine tied to a named guidance revision, with content-addressed rule-set/corpus/gold versioning and fail-loud input validation. A versioned, append-only registry (`moltrace.regulatory.ai`) pins each rule-set to its guidance revision, effective date, and GxP validation record, and a **deterministic-first router** sends every quantitative or classification task (ICH thresholds, Q3C/Q3D PDEs, M7 class, CPCA category) to the rule engine — never an LLM — reserving language models for narrative drafting, retrieval, and triage; every result carries its exact `rule_set_version`, model versions, and source-guidance citations for the audit trail. That retrieval path is a licence-aware RAG search over the ICH/FDA/EMA/WHO guidance corpus (`moltrace.regulatory.data` + `moltrace.regulatory.intelligence`): a versioned ingestion pipeline keeps FDA public-domain text redistributable while holding copyrighted ICH/EMA/WHO text internal-only with minimal, cited excerpts, and answers are grounded **only** in retrieved chunks with explicit citations — any regulated number defers to the deterministic engines, never to the model, with a post-hoc check that flags a fabricated number or an invalid citation. Unknowns return explicit `matched=false` / warnings, never a fabricated limit. AI-assisted regulatory decisions are additionally wrapped in a tamper-evident, hash-chained governance record (`moltrace.regulatory.compliance`) — documented intended use, logged model version, calibrated confidence, feature attribution, and human-in-the-loop gating that blocks high-risk decisions until a person approves — **designed to support the direction of EU GMP _Draft_ Annex 22 (July 2025); the Annex is in draft and not in force, so this is decision-support governance, not a compliance claim.** A new engine version ships only through a **zero-tolerance evaluation gate** (`moltrace.regulatory.eval`): it must reproduce every regulated number exactly (zero calculation errors), implement 100% of in-scope formulas, regress no citation, and dominate the incumbent's metric vector on a SHA-256-checksummed gold set — the objective, per-version acceptance evidence a GxP validation package consumes directly.

**The audit trail** (`moltrace.spectroscopy.audit`) is an HMAC-SHA256-chained, tamper-evident log with §11.50/§11.70 e-signatures, a 7-year retention floor, and model-weight checksum capture — controls built to *support* 21 CFR Part 11. The HMAC chain key is supplied via `MOLTRACE_AUDIT_HMAC_KEY`.

**Identity & access** is opaque-bearer-token auth over hashed sessions, with per-user and per-tenant scoping enforced server-side (regulatory dossiers, for example, are owner-scoped with non-leaking 404s). For enterprise tenants, MolTrace federates identity via **per-organization OpenID Connect SSO** (`nmrcheck.oidc_client` / `nmrcheck.sso_store`): Authorization Code + PKCE (S256), JWKS id_token validation, just-in-time user/team provisioning gated by allowed email domains, and an optional **enforce-SSO** mode that blocks password login for governed domains. The same connections expose a **SCIM 2.0** endpoint (`nmrcheck.scim_store`, `/scim/v2`) so Okta/Entra can auto-provision and — critically — **auto-deprovision** users; deprovisioning is *soft* (disable + immediate session revocation, never deleting an audit-linked user) so the §11.10(d)/§11.200 access controls hold without breaking record traceability. Layered on top is **MFA** (`nmrcheck.mfa_store`): RFC 6238 **TOTP** plus phishing-resistant **WebAuthn/passkeys (FIDO2)** with one-time recovery codes, **per-tenant enforcement**, and **step-up re-authentication** required before admin and e-signature/signing operations (the §11.200 contemporaneous re-auth) — federation may stand in for entry, but signing always demands a fresh local factor. Sessions are hardened (`nmrcheck.session_store`): a short-lived opaque access bearer plus a **rotating, single-use refresh token** grouped into a login family, with **reuse detection** (a replayed refresh revokes the whole family), idle + absolute timeouts, optional device binding, and **immediate** server-side revocation (a revoked family dies on the next request, not at token expiry). IdP client secrets are AES-256-GCM encrypted at rest (TOTP secrets under a separate key); SCIM bearer tokens, refresh tokens, and recovery codes are stored as SHA-256 digests; passkeys store only public key material. Unique user identification plus enforced, lifecycle-managed, step-up-gated, revocable access control are the controls that *support* 21 CFR Part 11.

All browser→backend traffic is proxied same-origin; the binding FE↔BE contract is the generated `src/lib/api/schema.d.ts` (OpenAPI → TypeScript).

```
                          ┌─────────────────────────────────────────────┐
  Browser  ──HTTPS──▶     │  Next.js (Vercel) — moltrace.co              │
                          │  /api/backend/[...path]  same-origin proxy   │
                          └───────────────────────┬─────────────────────┘
                                                  │  forwards /api/backend/*
                                                  ▼
                          ┌─────────────────────────────────────────────┐
                          │  FastAPI  (Render — moltrace-backend)        │
                          │  nmrcheck.main:app   /health                 │
                          ├──────────────┬───────────────┬──────────────┤
                          │ spectroscopy │  AI model     │  regulatory  │
                          │ science      │  lifecycle    │  engine      │
                          │ (verifier =  │  (advisory,   │  (det. rule  │
                          │  arbiter)    │   never wins) │   engine)    │
                          └──────┬───────┴───────┬───────┴──────┬───────┘
                                 │               │              │
                                 ▼               ▼              ▼
                          ┌─────────────┐   ┌──────────────────────────────┐
                          │  Postgres   │   │  HMAC-chained audit log       │
                          │ (Render db) │   │  + e-sigs (Part 11-supporting)│
                          └─────────────┘   └──────────────────────────────┘
```

The FE↔BE contract pipeline: FastAPI `/openapi.json` → `pnpm generate:openapi` (openapi-typescript) → `moltrace_frontend/src/lib/api/schema.d.ts`.

## Tech stack

**Frontend**
- Next.js 16.2.4 (App Router, RSC), React 19, TypeScript 5.7.3
- Tailwind CSS v4 (CSS-first via `@tailwindcss/postcss`, no `tailwind.config.js`) + shadcn/ui (new-york style) on ~27 Radix UI primitives
- Plotly (`plotly.js-dist-min` + `react-plotly.js`) for scientific spectra/chromatogram/MS plots; Recharts for dashboard charts
- Three.js via `@react-three/fiber` + `drei` (marketing hero molecule)
- `react-hook-form` + `zod`, `zustand`, `next-themes`, `sonner`, `cmdk`, `vaul`, `embla-carousel`
- Installable PWA: `app/manifest.ts` + a hand-written `public/sw.js` service worker
- pnpm 11.0.3, Node 22.14.0; Vitest 4.x, Playwright; openapi-typescript 7.x

**Backend**
- Python ≥3.11 (deployed on 3.13.5); FastAPI ≥0.115,<1.0, Pydantic v2
- SQLAlchemy 2.x + Alembic (PostgreSQL via psycopg v3 in prod, SQLite in tests; 20 migrations)
- uv package manager + hatchling build backend; ruff + mypy (strict)
- RQ ≥2.0 + Redis for queued background jobs
- `pyjwt[crypto]` (RS256/ES256 OIDC id_token verification) + `cryptography` (AES-256-GCM secret encryption) for enterprise SSO; `pyotp` (RFC 6238 TOTP) + `webauthn` (py_webauthn, FIDO2 passkeys) for MFA

**ML + science**
- RDKit ≥2025.9.1 (structure parsing/standardisation), numpy/scipy/lmfit (deconvolution, fitting)
- faiss-cpu (HNSW spectrum retrieval) + lttbc (downsampling)
- Optional/lazy: nmrglue (FID parsing — Bruker/Agilent), torch/peft/modal (NMRNet, JTF-Net, LoRA), Optuna (HPO), matchms, SIRIUS/CSI:FingerID
- Optional RAG (spectroscopy): Anthropic Claude (`claude-opus-4-8`) wrapped over the FAISS index with a cite-or-drop hallucination guard. The `anthropic` package is an **undeclared dependency** and `ANTHROPIC_API_KEY` must be set; `/spectrum/reason` only enables when both are present, and the deterministic verifier remains the arbiter.
- Optional RAG (regulatory): a declared `rag` extra (`anthropic`, `openai`) powers the guidance-corpus search in `moltrace.regulatory.intelligence` (Claude `claude-sonnet-4-6` synthesis + `text-embedding-3-small` vectors). It is fully optional — the engine and its tests run offline on a zero-dependency lexical retriever + deterministic extractive synthesis — and regulated numbers always defer to the deterministic engines.

**Infra**
- Render — FastAPI web service (plan `starter`) + a second-region FE mirror (plan `starter`) + managed Postgres `moltrace-db` (plan `basic-256mb`); Vercel (primary frontend); GitHub Actions (CI/CD)
- `infra` extra (optional, not installed in CI/prod): MLflow, DVC, Great Expectations, pandas, boto3
- Pandoc + XeLaTeX / Typst for white-paper PDF builds

## Repository layout

```
MolTrace/
├── moltrace_backend/          # FastAPI service `nmrcheck` (uv + hatchling)
│   ├── src/nmrcheck/          #   HTTP layer: api.py (large monolith), models.py, orm.py, main.py,
│   │                          #   security, RQ jobs + legacy ¹H/¹³C/LC-MS evidence engine, dossier stores
│   ├── src/moltrace/
│   │   ├── spectroscopy/      #   modular NMR/MS science (peaks, multiplet, predict, verification,
│   │   │                      #   similarity, nus, integration, qnmr, classify) + ai/ eval/ data/
│   │   │                      #   feedback/ ops/ audit/ infra/  (the AI model lifecycle)
│   │   └── regulatory/        #   deterministic-first ICH/FDA/EMA/WHO engine: impurities/ specifications/
│   │                          #   stability/ ctd/ quality/ (OOS + SPC) + data/ (versioned licence-aware
│   │                          #   corpus) + intelligence/ (grounded RAG search) + ai/ compliance/ eval/ infra/
│   ├── alembic/               #   14 migrations (0001–0014)
│   ├── tests/                 #   ~187 test_*.py files
│   ├── docs/                  #   48 design/handoff docs
│   ├── pyproject.toml · uv.lock · CHANGELOG.md · NOTICE
├── moltrace_frontend/         # Next.js 16 / React 19 app (pnpm)
│   ├── app/                   #   active App Router tree (marketing + signed-in routes)
│   │   └── api/backend/[...path]/route.ts   # same-origin proxy to FastAPI
│   ├── components/            #   marketing/, programs/, spectracheck/, regulatory-hub/,
│   │                          #   reaction-optimization/, science/, dashboard/, ui/
│   ├── src/lib/api/           #   client.ts + generated schema.d.ts (FE↔BE contract)
│   ├── next.config.mjs · vercel.json · render.yaml
├── whitepaper-build/          # six white-paper .md sources + Pandoc/Typst PDF build (Makefile)
├── moltrace_docs/             # empty Astro/Starlight build mirror (real site: docs.moltrace.co)
├── scripts/                   # CI watch, release guardrails, playbook generator
├── tests/contracts/           # cross-cutting release-health contract fixtures
├── render.yaml                # Render blueprint: backend + FE mirror + Postgres
├── .github/workflows/ci-cd.yml
├── RELEASE_GUARDRAILS.md · MolTrace_WhitePaper_Maintenance.md
```

## Getting started

### Prerequisites
- **Python ≥3.11** (3.13 recommended) and [uv](https://github.com/astral-sh/uv)
- **Node 22.14.0** and **pnpm 11.0.3** (`corepack enable`)
- Optional: PostgreSQL and Redis for production-like runs. The backend runs with **zero external services out of the box** — with `DATABASE_URL` unset, settings default to `sqlite:///./nmrcheck.sqlite3`, so the migration + uvicorn steps below work as written. Redis is only needed for queued background jobs.

### Backend (uv)

```bash
cd moltrace_backend

# install deps (with dev tooling + FID parsing extra)
uv sync --frozen --extra fid --extra dev

# apply database migrations (uses settings.database_url; SQLite by default)
uv run alembic upgrade head

# run the API (defaults to :8000 locally; add --reload for local dev)
uv run python -m uvicorn nmrcheck.main:app --host 127.0.0.1 --port 8000 --reload

# (optional) run a background-job worker — needs Redis on QUEUE_NAME=moltrace
uv run rq worker moltrace

# run the test suite (slow tests excluded by default)
uv run pytest          # CI uses: uv run pytest -n auto
```

`uv sync` editable-installs both `src/nmrcheck` and `src/moltrace`, so tests import them with no `PYTHONPATH` shim. Optional extras: `'.[fid]'` (nmrglue FID parsing), `'.[dev]'` (pytest/mypy/ruff/httpx), `'.[infra]'` (MLflow/DVC/Great Expectations adapters).

### Frontend (pnpm)

```bash
cd moltrace_frontend

pnpm install

pnpm dev          # next dev (local dev server on :3000)
pnpm build        # next build
pnpm start        # next start

pnpm lint         # eslint .
pnpm typecheck    # tsc --noEmit  (next build itself does NOT typecheck)
pnpm test         # vitest
```

The FE proxies all `/api/backend/*` traffic to the backend. The proxy route defaults to `http://127.0.0.1:8000` (and rewrites `localhost`→`127.0.0.1`); override it for a non-default backend by setting `API_BASE_URL` in `moltrace_frontend/.env.local`.

### Regenerate the FE↔BE contract

The typed schema is the binding contract — regenerate it whenever backend routes/models change. **The backend must be running on `:8000` first:**

```bash
cd moltrace_frontend
pnpm generate:openapi
# openapi-typescript http://localhost:8000/openapi.json -o src/lib/api/schema.d.ts
```

For local development, run both apps: the backend on `:8000` and the frontend on `:3000`.

## Configuration

Key environment variables (see `render.yaml` for the full set):

| Variable | Scope | Purpose |
|---|---|---|
| `DATABASE_URL` | backend | Postgres DSN in prod; unset → SQLite default for local runs. |
| `API_KEY` | backend | API authentication key. |
| `ALLOWED_ORIGINS` | backend | CORS allow-list. |
| `ALLOWED_UPLOAD_TYPES` | backend | Permitted upload MIME types. |
| `EMAIL_BACKEND` / `REQUIRE_VERIFIED_EMAIL` | backend | Email + account-verification behavior. |
| `QUEUE_NAME` | backend | RQ queue name (default `moltrace`). |
| `MOLTRACE_AUDIT_HMAC_KEY` | backend | Key for the HMAC-chained audit ledger. |
| `SSO_ENCRYPTION_KEY` | backend | AES-256-GCM key for encrypting SSO IdP client secrets at rest. **Required before any tenant onboards SSO** (a loud dev-only fallback is used otherwise). |
| `BASE_URL` / `FRONTEND_BASE_URL` | backend | API origin (used to compute the OIDC callback redirect URI) and SPA origin (where the SSO callback lands). |
| `ANTHROPIC_API_KEY` | backend | Enables the optional RAG `/spectrum/reason` path (with the undeclared `anthropic` package). |
| `API_BASE_URL` | frontend | Backend target for the same-origin proxy (local + root deploy). |
| `NEXT_PUBLIC_API_BASE_URL` | frontend | Public API base. **Divergence to note:** `moltrace_frontend/render.yaml` sets it to `/api/backend`, while the root `render.yaml` points it at the full backend URL. |

## Deployment

Deployment is split across real production targets, defined in `render.yaml` (root) and `.github/workflows/ci-cd.yml`:

- **Frontend → Vercel** at `moltrace.co` / `www.moltrace.co`. A second-region frontend mirror (`moltrace-frontend1`, Render plan `starter`) also runs on Render with health-check path `/api/app-version`.
- **Backend → Render** (`moltrace-backend.onrender.com`, plan `starter`), built with `uv sync --frozen --no-dev --extra fid` and started with the chained command:
  ```bash
  uv run alembic upgrade head && uv run python -m uvicorn nmrcheck.main:app --host 0.0.0.0 --port $PORT
  ```
  DB migrations apply automatically through this start command — there is no separate migration step. Health-checks hit `/health`.
- **Database → Render-managed Postgres** (`moltrace-db`, plan `basic-256mb`), injected into the backend as `DATABASE_URL`.

CI runs frontend (vitest) and backend (pytest) tests independently, then a fail-closed deployment gate (`uv run moltrace-deployment-gate --self-check`), and only then fires the Vercel and Render deploy hooks — **only on push to `main`**. Platform auto-deploy is disabled (Vercel `git.deploymentEnabled: false`; Render Auto-Deploy off) so only green CI reaches production.

## Testing & quality gates

Correctness is enforced, not assumed:

- **~187 backend `test_*.py` files** plus the frontend Vitest suite, run independently in CI.
- **Fail-closed four-check deployment gate** (dominance / audit-chain / tests-green / data-leakage) — `moltrace-deployment-gate` must pass before any deploy hook fires.
- **Two regulatory zero-tolerance hard gates** — calculation error rate must be 0 and formula coverage must be 100%.
- **GSD A/B regression fixture** guards detector drift between the legacy and GSD pipelines.

## Documentation

- **Product docs:** [docs.moltrace.co](https://docs.moltrace.co) (a separate Astro/Starlight site; the in-repo `moltrace_docs/` is an empty build mirror).
- **Engineering docs:** `moltrace_backend/docs/` (48 design/handoff documents) and `moltrace_backend/CHANGELOG.md` — the authoritative per-release record of what shipped.
- **White papers:** six markdown sources in `whitepaper-build/` (White Paper, Sales, Technical, Executive One-Pager, ROI Methodology, Company Credentials) with a Pandoc + XeLaTeX / Typst PDF build (`make -C whitepaper-build all`). `MolTrace_WhitePaper_Maintenance.md` (repo root) is the per-trigger update matrix.

## Compliance & disclaimers

MolTrace is built deliberately around a few non-negotiable principles:

- **Decision-support only.** Every regulatory result carries `human_review_required=True` and a disclaimer. The unified confidence engine never asserts identity; outputs are decision support, not proof of identity and not a calibrated DP4/DP5 probability.
- **The deterministic verifier is the sole arbiter.** Regulated numbers and classifications come from a version-pinned rule engine tied to a named guidance revision. AI — LLM proposals, the reward model, self-confidence — is strictly advisory and can **never override the science**. The reward model can only reorder *within* a verifier verdict class; LLM `self_confidence` is never used as the verifier prior.
- **Qualified human sign-off is required.** No regulatory document or dossier artifact is released without explicit, qualified-reviewer sign-off, recorded with identity, role, timestamp, and artefact hash.
- **Supports, not "compliant."** MolTrace's controls are built to **SUPPORT** 21 CFR Part 11 and GAMP 5 — *"these controls help customers meet 21 CFR Part 11 — MolTrace does not claim the product is itself compliant. Full computerized-system validation, SOPs, and identity management remain the customer's responsibility."* No function emits a self-compliance claim.
- **Not a finished filing.** Outputs are decision-support inputs to be reviewed and signed off by a qualified toxicologist or regulatory-affairs professional; they are not submission-ready filings. (This README-level note: MolTrace does not constitute legal advice.)

Marketing metrics (e.g. accuracy and throughput figures) are positioning copy and should be treated as such, not as independently verified guarantees.

## Access, contributing & security

- **Hosted product.** MolTrace runs as a multi-tenant hosted application at [moltrace.co](https://moltrace.co), with authentication (password or per-organization OpenID Connect SSO, with optional enforce-SSO and SCIM 2.0 auto-provisioning/deprovisioning), MFA (TOTP + WebAuthn/passkeys) with per-tenant enforcement and step-up re-auth for signing/admin, rotating refresh tokens with reuse detection and immediate revocation, centralized policy-as-code authorization (a deny-by-default policy engine deciding every access server-side from the authenticated principal), per-tenant scoping, identity+role e-signatures, and CORS allow-lists. Access is via the hosted product, not a public self-serve install.
- **Contributions.** This is a proprietary, all-rights-reserved repository (see below); external contributions and issues are not solicited here.
- **Security.** Report any suspected security issue privately to the MolTrace maintainers rather than opening a public issue.

## License / status

**No license file is present in this repository.** In the absence of an explicit license, all rights are reserved and the code is proprietary by default — it is not licensed for reuse, modification, or redistribution unless and until a `LICENSE` is added. The backend ships a `NOTICE` file with third-party attributions (e.g. NMRNet, MIT), which provides attribution only and is **not** a project license.
