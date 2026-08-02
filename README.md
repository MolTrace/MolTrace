# MolTrace

> The unified intelligence platform for chemical and pharmaceutical R&D — one audit-grade evidence stack from the first hit spectrum to the IND dossier.

![Python](https://img.shields.io/badge/Python-3.13_runtime-3776AB?logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178C6?logo=typescript&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Frontend: Vercel](https://img.shields.io/badge/Frontend-Vercel-000000?logo=vercel&logoColor=white)
![Backend: Google Cloud Run](https://img.shields.io/badge/Backend-Cloud_Run-4285F4?logo=googlecloud&logoColor=white)
![License: BUSL 1.1](https://img.shields.io/badge/License-BUSL_1.1-4B5563)

> **License.** MolTrace is **source-available, not open source.** The code is published under the [Business Source License 1.1](LICENSE) so you can read, audit, evaluate, and test it — but **production use requires a commercial license** (contact [licensing@moltrace.co](mailto:licensing@moltrace.co)). Each version converts to Apache 2.0 four years after release. See [`LICENSE`](LICENSE), [`NOTICE`](NOTICE), [`SECURITY.md`](SECURITY.md), and [`CONTRIBUTING.md`](CONTRIBUTING.md).

MolTrace is an AI-native scientific intelligence platform that confirms structures, profiles impurities, and optimizes reaction routes — without ever losing the trail back to the raw data. It is built for pharmaceutical R&D teams, regulatory affairs professionals, CRO/analytical labs, and academic researchers who need evidence they can defend.

The platform is architected **deterministic-first**: regulated math and classifications are computed by a version-pinned rule engine, an auditable verifier is the sole arbiter of correctness, and AI is strictly advisory — it proposes, the science decides.

> **Status.** MolTrace runs as a hosted product at [moltrace.co](https://moltrace.co) — frontend on **Vercel**, backend on **Google Cloud Run** with **Cloud SQL** (migrated off Render in July 2026). `moltrace_backend/CHANGELOG.md` is the authoritative per-release record of what shipped; the repo's in-code version numbers are not yet unified across the two apps, so treat the CHANGELOG as the source of truth for "what's in production."

## The platform

MolTrace presents three modules around one unified evidence trail, with a closed loop: spectroscopy evidence becomes ICH-classified regulatory action items, which become reaction-optimization constraints, which inform the next experiment — all linked by recipe-hash reproducibility and an ALCOA+ audit ledger. The three modules are surfaced in a single tabbed Programs workspace in the signed-in app.

### SpectraCheck — Spectroscopy Intelligence
*Route: `/spectracheck` (marketing page at `/spectroscopy`)*

Raw FID → processed spectrum → peaks classified by category, with audit-grade fit metrics per peak.

- **GSD deconvolution** (Prompt-3 pseudo-Voigt forward/backward region fit) over levels 1–5, via `POST /spectrum/analyze/gsd`.
- **Multiplet detection and J-coupling recovery** with opt-in conformer-averaged Karplus ³J refinement (Haasnoot–de Leeuw–Altona generalized relation + Boltzmann conformer-population weighting), via `POST /spectrum/analyze/multiplets`.
- **Chemical-shift prediction** from the NMRNet SE(3)-equivariant model (optional, lazily-loaded torch backend) behind an always-available HOSE-code / NMRShiftDB2 topological fallback, via `POST /spectrum/predict/shifts`.
- **LC-MS / MS/MS evidence studios** with CSI:FingerID (MS/MS → structure via SIRIUS, optional), retention-time corroboration, and DP4-AI posterior scoring; candidates fuse into one calibrated ranking.
- **FAISS spectrum retrieval** (Gaussian-smoothed 256-D encoding + HNSW index, Kuhn–Munkres set similarity) via `POST /spectrum/retrieve`, plus retrieval-augmented reasoning via `POST /spectrum/reason`. Indexes are built **per nucleus**: 82% of reference spectra in public shift databases record only ¹H or only ¹³C, and a single combined index ranks those entries by their missing nucleus instead of by chemistry, so a ¹³C-only query could not reach a both-nuclei reference at all. A query is compared only on the nuclei it shares with each candidate, with a measured coverage penalty.
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
- **True multi-objective Pareto front + hypervolume** — the non-dominated experiments, an exact 2-D / deterministic Monte-Carlo (≥3-D) hypervolume indicator, and a knee-point trade-off pick (pure NumPy, no BoTorch), surfaced in the BO-run diagnostics (`nmrcheck/reaction_pareto.py`; advisory).
- **Regulatory constraints from Regentry** — a dossier's ICH impurity action items are injected as reaction constraints, and a project's recorded experiment outcomes are evaluated against those limits (`…/regulatory-compliance`), flagging non-compliant experiments with provenance back to the source action item (`nmrcheck/reaction_regulatory_constraints.py`; a high/critical limit → non-compliant, lower tiers → an advisory penalty). The closed loop: regulatory action item → reaction constraint → flagged result → next experiment.
- **Uncertainty quantification** on each iteration with model-diagnostics.
- **Automated next-experiment recommendations** over a batch of candidate experiments per optimization cycle.
- **Green-chemistry metrics** — Sheldon E-factor (simple & complete), atom economy, process mass intensity (PMI), reaction mass efficiency (RME), and a CHEM21-derived solvent green-score — computed per experiment from RDKit + transparent arithmetic, and selectable as optimization objectives (`minimize_e_factor`, `maximize_atom_economy`, `maximize_green_score`) alongside yield and selectivity.
- **HTE / DoE plate design** — generate a deterministic 24/96/384-well experiment plate over the project's design space (Sobol or Latin-hypercube space-filling, full-factorial, or a Bayesian-optimization seed set), with fixed conditions, excluded combinations, and CSV/JSON export for lab robotics (`nmrcheck/reaction_hte.py`; pure NumPy/SciPy, reproducible per seed).
- **Structural process-safety screening** — a deterministic RDKit-SMARTS screen for energetic/reactive functional groups (azide, peroxide, diazo, poly-nitro, perchlorate, tetrazole, …) with a conservative risk tier and a fail-safe, human-in-the-loop review gate: a flagged structure is never silently cleared, holds the project's `safety-gate` at *review_pending* until a qualified reviewer signs off, and a rejection hard-blocks (`nmrcheck/reaction_safety.py`; decision-support only, not a safety determination).
- **Half-closed DMTA loop** — a metered, human-gated design-make-test-analyze loop over optimization cycles: only a `continue_optimization` cycle decision unlocks `POST …/optimization-cycles/{id}/propose-next`, which proposes the next batch as a **draft** cycle metered with loop metrics (latency, experiments-to-target) and BO/SpectraCheck provenance. **Nothing auto-executes** — execution still requires human signoff and a clear safety gate (`nmrcheck/reaction_loop.py`; the SpectraCheck-verified outcome closes test→learn).
- **Math-frozen reaction-planning agent** — an optional, default-off Claude advisor that orchestrates the reaction engines as tool calls. It plans, narrates, and re-ranks candidates with citations but **never computes a quantitative value**: every yield, score, cost, green metric, or safety verdict comes from a frozen deterministic tool and is recorded as tool-call provenance (the model's prose is never the source of a number). A fail-closed safety pre-check gates the action tools, and the agent degrades to the deterministic rule-based advisor when no API key is configured (`nmrcheck/reaction_agent.py`; opt-in, decision-support only, always human-reviewed).
- **Chemist feedback → preference re-ranker → A/B promotion gate** — chemists accept/edit/reject proposals with a reason taxonomy; the feedback trains an **advisory** preference re-ranker that re-orders proposals by likely acceptance (it annotates, never overrides the optimiser), and a champion-vs-challenger A/B gate decides — as decision-support — whether a new model may replace the incumbent (promotable only with no safety-flag-recall regression **and** metric-vector dominance; never auto-deploys, always rollback-able). A safety (`unsafe`) rejection is high-signal: it routes to strengthen the safety screen and is excluded from preference learning (`nmrcheck/reaction_feedback.py`; advisory, human-gated).
- **Warm-start transfer-learning priors** — a new campaign warm-starts from accumulated, **verified** (SpectraCheck-linked or reviewer-confirmed) data on the chemist's **related, owned** campaigns, so it reaches the target in fewer experiments. Building a prior freezes that data into an immutable, content-hashed, lineage-bearing snapshot (the frozen evaluation gold set is excluded by id), fits a prior mean, and offers an **advisory** re-ranking of the next batch by likely success. Source campaigns are owner-checked (a non-owned source is a non-leaking 404), and the prior is fit only from owned data, never the gold set (`nmrcheck/reaction_priors.py`; advisory, weights in the DB not git).
- **Frozen benchmark + fail-closed promotion gate** — every recommender change is measured against an immutable, content-checksummed gold set before it can ship. The harness scores recommendation quality, calibration, and hypervolume, and adds a **blocking safety-flag-recall dimension**: a candidate that misses hazards the incumbent caught cannot be promoted no matter how much its accuracy improved. Results are bound to the gold-set checksum (a result computed against a different benchmark is refused), missing metrics fail closed rather than defaulting to "best", and the CI job exits non-zero on a blocked or malformed run (`nmrcheck/reaction_eval.py`, `nmrcheck/reaction_eval_cli.py`, `.github/workflows/reaction-benchmark-gate.yml`).
- **Heavy-ML extras, governed as guests (default-off)** — GNN yield prediction, MCTS retrosynthesis, transformer forward prediction, and self-driving-lab execution ship as **optional, feature-flagged** capabilities behind a single seam. Nothing heavy activates implicitly: each capability has its own env flag, its dependencies are *probed* (`importlib.util.find_spec`) rather than imported, and a capability that replaces frozen math additionally requires a recorded benchmark-gate pass **bound to** that gold-set checksum and that model version. Every decision returns auditable provenance, and when a capability is off the fallback it names is the lightweight path that was already running — never a silent degradation. `torch`, `aizynthfinder`, `transformers`, and `rxn4chemistry` remain site-installed extras, not core dependencies (`nmrcheck/reaction_ml.py`; see [`docs/reaction_phase_c_heavy_ml.md`](moltrace_backend/docs/reaction_phase_c_heavy_ml.md)). The lightweight halves are served per project (owner-scoped): `…/yield-predictions` (surrogate fit on the project's own recorded experiments, with the backend decision recorded verbatim), `…/route-scores` (a supplied route scored by the frozen safety + green engines, reagents included), `…/forward-checks` (a supplied prediction cross-checked before anyone acts on it), plus a global `/reaction-capabilities` readout and a read-only `/reaction-sdl/status`; the generative heavy endpoints are deliberately unwired until the extras and an off-request worker exist.
  - **Yield/selectivity GNN** — message-passing net with MC-Dropout uncertainty, sealed checkpoints (weights *and* metadata SHA-verified; never committed), degrading to a Gaussian-process surrogate and finally to a zero-dependency k-NN surrogate, so Repho is never without a model (`nmrcheck/reaction_yield_models.py`).
  - **Retrosynthesis** — provider-agnostic route model with the frozen safety and green engines overlaid on every proposed route, screening reagents as well as molecules, and refusing to report atom economy it cannot honestly compute (`nmrcheck/reaction_retro.py`).
  - **Forward prediction** — predicted products are cross-checked against the frozen safety/green engines before a chemist sees them; an unrecognised risk level is treated as worse than critical, never better than low (`nmrcheck/reaction_forward.py`).
  - **Self-driving lab** — a hardware-abstraction layer behind arm/heartbeat/disarm interlocks, a bounds-checked execution envelope that refuses non-finite parameters, and a tamper-evident hash-chained journal verified by both head hash and entry count. Manual mode is the default everywhere (`nmrcheck/reaction_sdl.py`; decision-support, human-gated).
  - **Dataset licensing & leakage control** — an unregistered reaction dataset cannot be ingested at all; benchmark-only corpora are held out of training, prohibited commercial sources are refused outright, and reproducible content-addressed splits keep the evaluation gold set out of every training path (`nmrcheck/reaction_data_pipeline.py`).
- **Structure & reaction-scheme service** — structures and reaction schemes drawn in Reaction Studio are captured as an MDL molfile or RXN block and read by **RDKit**, not trusted from the browser's drawing engine: two chemistry engines disagreeing silently is a failure a regulated workspace cannot absorb. `POST /reactions/structures/validate` returns canonical SMILES, an InChIKey (only for a single, fully-defined structure — never for a reaction or an R-group drawing), atom/bond counts and reaction component counts, and **says in plain language whatever checking the structure changed** — hydrogen counts, charges, unpaired electrons — instead of sanitizing silently; a structure that fails its checks is still a successful request, with the verdict in the body rather than in a status code. Schemes attach to a project (`…/schemes`) retaining **both** the block as drawn (the audit record) and RDKit's normalized form (what downstream chemistry computes on), owner-scoped like the rest of Repho and archived-rather-than-deleted under the ALCOA+ soft-delete pattern; `…/smarts-match` reuses the safety screen's matcher so the product keeps one SMARTS engine. Canonical output is pinned by test to agree with the compound registry's canonicalizer — a second canonicalizer is the same drift risk as a second drawing engine (`nmrcheck/reaction_structures.py`; the registry remains the home of a *registered compound*, and a reaction is deliberately not a compound structure). Validation itself ships in **every** SKU rather than with Repho: reading a drawing is a shared chemistry primitive, and Regentry needs it to show a chemist what RDKit read back from an impurity drawing *before* that structure becomes an ICH M7 verdict. Attaching a scheme to a campaign stays licensed to Repho. The drawing canvas now calls these routes: a capture is checked before anything can be stored, the verdict — canonical form, counts, and every warning, rendered in the service's own words — is shown beside the drawing, and a scheme attaches to and is listed on its project with a reason-gated archive. A drawn motif can also be matched against structures the chemist supplies; that surface is bounded to exactly those structures and says so on screen, and it reports a target RDKit could not read as *unread* rather than as a miss — "nothing matched" across a set that was never searched is the false negative a chemist would act on.
- A **compound-linking panel** and regulatory-constraints panel tie experiments back to the evidence trail.
- Backend engines: `nmrcheck/reaction_bo.py` (`run_bayesian_optimization`), `nmrcheck/reaction_green.py` (green-chemistry metrics), `nmrcheck/reaction_hte.py` (HTE/DoE plate design), `nmrcheck/reaction_safety.py` (structural safety screening), `nmrcheck/reaction_structures.py` (structure & reaction-scheme validation/canonicalization), `nmrcheck/reaction_regulatory_constraints.py` (regulatory-constraint enforcement), `nmrcheck/reaction_loop.py` (DMTA loop metering + propose-next gate), `nmrcheck/reaction_agent.py` (math-frozen, tool-calling advisor agent), `nmrcheck/reaction_feedback.py` (chemist feedback / preference re-ranker / A/B promotion gate), `nmrcheck/reaction_priors.py` (warm-start transfer-learning priors), `nmrcheck/reaction_eval.py` (frozen benchmark + promotion gate), and the default-off heavy-ML seam `nmrcheck/reaction_ml.py` with `reaction_yield_models.py` / `reaction_retro.py` / `reaction_forward.py` / `reaction_sdl.py` / `reaction_data_pipeline.py`.

## Architecture

MolTrace is a two-app monorepo:

- **Backend** (`moltrace_backend/`) — a single FastAPI service (package `nmrcheck`, app title "NMRCheck API"). The HTTP layer (`src/nmrcheck/`) carries routes, Pydantic models, SQLAlchemy ORM, Alembic migrations, auth, and RQ/Redis background jobs; `api.py` is a large monolithic module. Two modular science packages sit under `src/moltrace/`: `moltrace.spectroscopy` (NMR/MS science + AI model lifecycle) and `moltrace.regulatory` (the ICH/FDA impurity engine).
- **Frontend** (`moltrace_frontend/`) — a single Next.js 16 / React 19 App Router app serving both the public marketing site and the signed-in product from one codebase, with an installable PWA shell.

**The science layer** (`moltrace.spectroscopy`) is deterministic and verifier-centered: `verify_structure` runs four independent tests (PredictionBounds, Assignments, HSQC2DRanges, MSMoleculeMatch) and combines them via a Bayesian log-odds update into an auditable posterior. This deterministic verifier is the **sole arbiter** of correctness across the whole stack.

**The AI model lifecycle** (`moltrace.spectroscopy.ai/eval/data/feedback/ops`) adds a versioned append-only model registry, a provenance-emitting inference router (LoRA fine-tuned → NMRNet pretrained → deterministic HOSE fallback) that records per-prediction the layer used and why, an evaluation harness with a dominance gate over a checksum-locked gold set, LoRA fine-tuning, Bayesian HPO (Optuna), confidence calibration with ECE as a promotion gate, closed-loop RLHF/A-B testing (a Bradley–Terry reward model that only re-ranks *within* a verifier verdict class), active learning, and a fail-closed four-check deployment gate (dominance / audit-chain / tests-green / data-leakage) wired into CI.

**The regulatory engine** (`moltrace.regulatory`) is deterministic-first throughout: regulated numbers come from a version-pinned rule engine tied to a named guidance revision, with content-addressed rule-set/corpus/gold versioning and fail-loud input validation. A versioned, append-only registry (`moltrace.regulatory.ai`) pins each rule-set to its guidance revision, effective date, and GxP validation record, and a **deterministic-first router** sends every quantitative or classification task (ICH thresholds, Q3C/Q3D PDEs, M7 class, CPCA category) to the rule engine — never an LLM — reserving language models for narrative drafting, retrieval, and triage; every result carries its exact `rule_set_version`, model versions, and source-guidance citations for the audit trail. That retrieval path is a licence-aware RAG search over the ICH/FDA/EMA/WHO guidance corpus (`moltrace.regulatory.data` + `moltrace.regulatory.intelligence`): a versioned ingestion pipeline keeps FDA public-domain text redistributable while holding copyrighted ICH/EMA/WHO text internal-only with minimal, cited excerpts, and answers are grounded **only** in retrieved chunks with explicit citations — any regulated number defers to the deterministic engines, never to the model, with a post-hoc check that flags a fabricated number or an invalid citation. Unknowns return explicit `matched=false` / warnings, never a fabricated limit. AI-assisted regulatory decisions are additionally wrapped in a tamper-evident, hash-chained governance record (`moltrace.regulatory.compliance`) — documented intended use, logged model version, calibrated confidence, feature attribution, and human-in-the-loop gating that blocks high-risk decisions until a person approves — **designed to support the direction of EU GMP _Draft_ Annex 22 (July 2025); the Annex is in draft and not in force, so this is decision-support governance, not a compliance claim.** A new engine version ships only through a **zero-tolerance evaluation gate** (`moltrace.regulatory.eval`): it must reproduce every regulated number exactly (zero calculation errors), implement 100% of in-scope formulas, regress no citation, and dominate the incumbent's metric vector on a SHA-256-checksummed gold set — the objective, per-version acceptance evidence a GxP validation package consumes directly.

**The audit trail** (`moltrace.spectroscopy.audit`) is an HMAC-SHA256-chained, tamper-evident log with §11.50/§11.70 e-signatures, a 7-year retention floor, and model-weight checksum capture — controls built to *support* 21 CFR Part 11. The HMAC chain key is supplied via `MOLTRACE_AUDIT_HMAC_KEY`.

**Identity & access** is opaque-bearer-token auth over hashed sessions, with per-user and per-tenant scoping enforced server-side (regulatory dossiers, for example, are owner-scoped with non-leaking 404s). For enterprise tenants, MolTrace federates identity via **per-organization OpenID Connect SSO** (`nmrcheck.oidc_client` / `nmrcheck.sso_store`): Authorization Code + PKCE (S256), JWKS id_token validation, just-in-time user/team provisioning gated by allowed email domains, and an optional **enforce-SSO** mode that blocks password login for governed domains. The same connections expose a **SCIM 2.0** endpoint (`nmrcheck.scim_store`, `/scim/v2`) so Okta/Entra can auto-provision and — critically — **auto-deprovision** users; deprovisioning is *soft* (disable + immediate session revocation, never deleting an audit-linked user) so the §11.10(d)/§11.200 access controls hold without breaking record traceability. Layered on top is **MFA** (`nmrcheck.mfa_store`): RFC 6238 **TOTP** plus phishing-resistant **WebAuthn/passkeys (FIDO2)** with one-time recovery codes, **per-tenant enforcement**, and **step-up re-authentication** required before admin and e-signature/signing operations (the §11.200 contemporaneous re-auth) — federation may stand in for entry, but signing always demands a fresh local factor. Sessions are hardened (`nmrcheck.session_store`): a short-lived opaque access bearer plus a **rotating, single-use refresh token** grouped into a login family, with **reuse detection** (a replayed refresh revokes the whole family), idle + absolute timeouts, optional device binding, and **immediate** server-side revocation (a revoked family dies on the next request, not at token expiry). User passwords are hashed with **Argon2id** (`nmrcheck.security`) — a memory-hard KDF (64 MiB, t=3) with a unique salt and an optional KMS-held pepper; pre-existing PBKDF2 hashes still verify and transparently upgrade to Argon2id on the next successful login. IdP client secrets are AES-256-GCM encrypted at rest (TOTP secrets under a separate key); SCIM bearer tokens, refresh tokens, and recovery codes are high-entropy random values stored as SHA-256 digests; passkeys store only public key material. Unique user identification plus enforced, lifecycle-managed, step-up-gated, revocable access control are the controls that *support* 21 CFR Part 11.

All browser→backend traffic is proxied same-origin; the binding FE↔BE contract is the generated `src/lib/api/schema.d.ts` (OpenAPI → TypeScript).

```
                          ┌─────────────────────────────────────────────┐
  Browser  ──HTTPS──▶     │  Next.js (Vercel) — moltrace.co              │
                          │  /api/backend/[...path]  same-origin proxy   │
                          └───────────────────────┬─────────────────────┘
                                                  │  forwards /api/backend/*
                                                  ▼
                          ┌─────────────────────────────────────────────┐
                          │  FastAPI (Cloud Run — moltrace-backend)      │
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
                          │ (Cloud SQL, │   │  + e-sigs (Part 11-supporting)│
                          │ private IP) │   │                               │
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
- SQLAlchemy 2.x + Alembic (PostgreSQL via psycopg v3 in prod, SQLite in tests; 30 migrations)
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
- **Google Cloud** (project `moltrace-prod`, us-central1) — Cloud Run (FastAPI, scale-to-zero) · Cloud SQL for PostgreSQL 16 on a **private IP** reached via Direct VPC egress · Cloud Storage (immutable raw-FID vault, model weights, DVC remote) · Secret Manager · Cloud KMS (field-encryption key) · Artifact Registry + Cloud Build
- **Vercel** — frontend at `moltrace.co`; **GitHub Actions** — CI/CD, deploying the backend keylessly via Workload Identity Federation
- `infra` extra (optional, not installed in CI/prod): MLflow, DVC, Great Expectations, pandas, boto3
- `gcs` extra (optional): `google-cloud-storage` for the GCS raw-vault backend
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
│   ├── next.config.mjs · vercel.json
├── whitepaper-build/          # six white-paper .md sources + Pandoc/Typst PDF build (Makefile)
├── moltrace_docs/             # empty Astro/Starlight build mirror (real site: docs.moltrace.co)
├── scripts/                   # CI watch, release guardrails, playbook generator
├── tests/contracts/           # cross-cutting release-health contract fixtures
├── moltrace_backend/deploy/   # GCP runbook + docker-compose dev stack (Dockerfile, cloudbuild.yaml one level up)
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

Key environment variables (in production these are injected from **Secret Manager**; see `moltrace_backend/deploy/README.md` for the deployed set):

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
| `NEXT_PUBLIC_API_BASE_URL` | frontend | Public API base. Note: the browser always calls the same-origin `/api/backend` proxy — an absolute URL here is deliberately ignored by `lib/api/client.ts`. |
| `RAW_VAULT_BACKEND` / `RAW_VAULT_BUCKET` | backend | Storage backend for the immutable raw-FID vault: `local` (default, filesystem) or `gcs` + a bucket. **Serverless deploys must use `gcs`** — Cloud Run's filesystem is ephemeral. |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_TRUST_FORWARDED_FOR` | backend | API abuse protection; trust `X-Forwarded-For` when behind the Cloud Run edge. |
| `ADMIN_EMAILS` | backend | Comma-separated admin allow-list. **No admin exists unless this is set** — the code default is empty. |

## Deployment

Deployment targets are defined in `.github/workflows/ci-cd.yml`; the backend runbook lives in [`moltrace_backend/deploy/README.md`](moltrace_backend/deploy/README.md).

- **Frontend → Vercel** at `moltrace.co` / `www.moltrace.co`, reaching the API through the same-origin `/api/backend` proxy.
- **Backend → Google Cloud Run** (service `moltrace-backend`, project `moltrace-prod`, us-central1), from a multi-stage container built by **Cloud Build** and stored in **Artifact Registry**. Scale-to-zero; health-checks hit `/health`.
- **Database → Cloud SQL for PostgreSQL 16** on a **private IP with no public interface**, reached over **Direct VPC egress** (no billable VPC connector). Credentials come from **Secret Manager**.
- **Object storage → Cloud Storage** — the write-once raw-FID vault (versioned), model weights, and the DVC remote.

**Migrations are a separate, gated step — never chained into the start command** (on Cloud Run that would race across every autoscaled instance). They run as the one-off Cloud Run job `moltrace-migrate` (`alembic upgrade head`). Note that on a *brand-new* database `upgrade head` cannot bootstrap the schema: the migrations are deltas over an ORM-created schema, so the app builds it at startup (`init_db()` → `create_all()`, 260 tables) and Alembic is then `stamp`ed.

CI runs frontend (vitest) and backend (pytest) tests independently, then SBOM + SLSA attestation + provenance verification and a fail-closed deployment gate (`uv run moltrace-deployment-gate --self-check`) — and only then deploys, **only on push to `main`**. The backend deploy authenticates via **Workload Identity Federation** (keyless — no stored service-account key) and runs build → migrate → new revision. Vercel auto-deploy is disabled (`git.deploymentEnabled: false`) so only green CI reaches production.

## Testing & quality gates

Correctness is enforced, not assumed:

- **~187 backend `test_*.py` files** plus the frontend Vitest suite, run independently in CI.
- **Fail-closed four-check deployment gate** (dominance / audit-chain / tests-green / data-leakage) — `moltrace-deployment-gate` must pass before any deploy hook fires.
- **Two regulatory zero-tolerance hard gates** — calculation error rate must be 0 and formula coverage must be 100%.
- **GSD A/B regression fixture** guards detector drift between the legacy and GSD pipelines.

## Documentation

- **Product docs:** [docs.moltrace.co](https://docs.moltrace.co) (a separate Astro/Starlight site; the in-repo `moltrace_docs/` is an empty build mirror).
- **Engineering docs:** `moltrace_backend/docs/` (48 design/handoff documents) and `moltrace_backend/CHANGELOG.md` — the authoritative per-release record of what shipped.
- **White papers:** six markdown sources in `whitepaper-build/` (White Paper, Sales, Technical, Executive One-Pager, ROI Methodology, Company Credentials) with a Pandoc + XeLaTeX / Typst PDF build (`make -C whitepaper-build all`).

## Compliance & disclaimers

MolTrace is built deliberately around a few non-negotiable principles:

- **Decision-support only.** Every regulatory result carries `human_review_required=True` and a disclaimer. The unified confidence engine never asserts identity; outputs are decision support, not proof of identity and not a calibrated DP4/DP5 probability.
- **The deterministic verifier is the sole arbiter.** Regulated numbers and classifications come from a version-pinned rule engine tied to a named guidance revision. AI — LLM proposals, the reward model, self-confidence — is strictly advisory and can **never override the science**. The reward model can only reorder *within* a verifier verdict class; LLM `self_confidence` is never used as the verifier prior.
- **Qualified human sign-off is required.** No regulatory document or dossier artifact is released without explicit, qualified-reviewer sign-off, recorded with identity, role, timestamp, and artefact hash.
- **Supports, not "compliant."** MolTrace's controls are built to **SUPPORT** 21 CFR Part 11 and GAMP 5 — *"these controls help customers meet 21 CFR Part 11 — MolTrace does not claim the product is itself compliant. Full computerized-system validation, SOPs, and identity management remain the customer's responsibility."* No function emits a self-compliance claim.
- **Not a finished filing.** Outputs are decision-support inputs to be reviewed and signed off by a qualified toxicologist or regulatory-affairs professional; they are not submission-ready filings. (This README-level note: MolTrace does not constitute legal advice.)

Marketing metrics (e.g. accuracy and throughput figures) are positioning copy and should be treated as such, not as independently verified guarantees.

## Access, contributing & security

- **Hosted product.** MolTrace runs as a multi-tenant hosted application at [moltrace.co](https://moltrace.co), with authentication (password or per-organization OpenID Connect SSO, with optional enforce-SSO and SCIM 2.0 auto-provisioning/deprovisioning), MFA (TOTP + WebAuthn/passkeys) with per-tenant enforcement and step-up re-auth for signing/admin, rotating refresh tokens with reuse detection and immediate revocation, centralized policy-as-code authorization (a deny-by-default policy engine deciding every access server-side from the authenticated principal), Argon2id password hashing (memory-hard, with transparent upgrade of legacy hashes), field-level envelope encryption of secrets at rest (per-record AES-256-GCM data keys wrapped by a KMS key-encryption key, with key rotation and a customer-managed-key/BYOK seam), secure-SDLC CI gates (secret-scanning via gitleaks in CI + pre-commit, SAST via Semgrep, dependency+license SCA and IaC scanning via Trivy — criticals block merge/deploy, lower-severity findings are reported as SARIF to the Security tab and tracked to closure under triage SLAs), a signed supply chain (a CycloneDX SBOM emitted per build for backend + frontend, SLSA build provenance signed keylessly via Sigstore, and a verify-at-deploy gate that refuses to fire the deploy hooks unless the provenance verifies — provenance queryable per release), a zero-trust CI/CD pipeline (every GitHub Action pinned to a commit SHA + least-privilege workflow tokens) with continuous IaC posture scoring and drift detection (CSPM), per-tenant + per-route API rate limiting (an in-app token-bucket limiter keyed by principal/IP × route, returning 429 with Retry-After/X-RateLimit headers, with abuse throttles recorded as security events) and a request-body-size guard (multipart uploads exempt), a published coordinated **vulnerability-disclosure policy** (an RFC 9116 `/.well-known/security.txt`, safe harbor, and CVSS-rated severity/remediation SLAs) backed by a STRIDE threat model and an annual / pre-release penetration-testing program whose findings are tracked to remediation evidence — complemented at the edge by a documented Cloudflare/Vercel WAF runbook, HSTS + security response headers over TLS 1.3, a tamper-evident hash-chained audit ledger (per-row prev-hash + periodic HMAC-signed anchors + a signed high-water mark + an admin verification endpoint), SIEM security detections over the event stream + the chain (impossible travel, privilege escalation, cross-tenant access, and audit-chain breaks) shipping high-severity alerts to a pluggable sink (structured stdout for the platform log drain + an optional webhook), a documented incident-response program (severity tiers, detection-keyed runbooks, and a GDPR Art. 33/34 breach-notification workflow with a notification-deadline engine that reflects MolTrace's processor role — it notifies the customer-controller, who owns the 72-hour supervisory-authority clock), backup & disaster-recovery resilience (documented RTO/RPO + a restore drill whose restore-integrity verifier re-runs the audit-chain verification against the restored database to prove it is intact and un-tampered — cross-region/immutable backup storage is operational), a personal-data map with DSAR / right-to-erasure planning that honestly separates **erasure** from **pseudonymisation** (a tokenised record is still personal data, so it is reported as retained-and-restricted, never as deleted) and states plainly that identity cannot be erased from the append-only audit ledger — with crypto-shredding documented as the enabling seam — plus an honest single-region residency posture (no tenant region pinning today), per-tenant scoping, 21 CFR Part 11-supporting electronic signatures (server-authoritative signer identity from the authenticated principal — never client-supplied — a SHA-256 record-content binding so a signature cannot be transferred to a different record or version, a durable §11.50 manifestation, and an integrity-verification endpoint), ALCOA+ data-integrity primitives on regulated records (reason-for-change captured in a queryable field, reversible-by-record soft-deletes attributed to the authenticated principal — no hard deletes — server-sourced timestamps, and a fail-closed write-once raw-data vault), a GAMP 5 / CSA validation lifecycle (a regenerable per-release validation package — requirement→risk→test traceability + IQ/OQ/PQ-from-CI evidence + release signatures — and validated-state change control that requires a reason-for-change once a project is approved/released), a machine-checked SOC 2 / ISO 27001 control-evidence register (each in-repo control mapped to its evidence file, validated so the map can't drift) plus a customer Trust Center with a sub-processor register — SOC 2/ISO are designed-to-support, not yet held — and CORS allow-lists. Access is via the hosted product, not a public self-serve install.
- **Contributions.** MolTrace is **source-available, not open source** (see License below). Bug reports and feature requests are welcome via GitHub issues; code contributions require a signed CLA so the work stays relicensable. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Security.** Report suspected vulnerabilities **privately** — use GitHub's *Security → Report a vulnerability*, or email [security@moltrace.co](mailto:security@moltrace.co). Do **not** open public issues for security reports. See [`SECURITY.md`](SECURITY.md).

## License

MolTrace is **source-available, not open source.** It is licensed under the **Business Source License 1.1** — see [`LICENSE`](LICENSE).

- **You may** read, copy, modify, and make **non-production** use of the code (evaluation, development, testing, research, security review).
- **Production use requires a commercial license.** For commercial licensing, contact [licensing@moltrace.co](mailto:licensing@moltrace.co).
- **Change Date.** Each released version converts to the **Apache License 2.0** on 2030-06-23 (four years after first public release).
- **Third-party components and vendored test data** retain their own licenses; see [`NOTICE`](NOTICE) and the per-directory fixture READMEs.

For security disclosure see [`SECURITY.md`](SECURITY.md); for contribution terms see [`CONTRIBUTING.md`](CONTRIBUTING.md).
