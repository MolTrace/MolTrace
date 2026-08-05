# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository shape

Two-app monorepo. There is no root-level build — each app is driven from its own directory.

- `moltrace_backend/` — FastAPI service, Python package name `nmrcheck` (app title "NMRCheck API"), managed with **uv**.
- `moltrace_frontend/` — Next.js 16 / React 19 App Router app serving both the public marketing site and the signed-in product, managed with **pnpm**.

## Commands

### Backend (`cd moltrace_backend`)

```bash
uv sync --frozen --extra fid --extra dev      # install (fid = nmrglue FID parsing, dev = pytest/mypy/ruff)
uv run alembic upgrade head                   # migrate (SQLite by default; see caveat below)
uv run python -m uvicorn nmrcheck.main:app --host 127.0.0.1 --port 8000 --reload
uv run rq worker moltrace                     # background-job worker (needs Redis)

uv run pytest                                 # full suite; `-m 'not slow'` is already in addopts
uv run pytest tests/test_api.py               # one file
uv run pytest tests/test_api.py::test_name     # one test
uv run pytest -m slow                          # opt into the >30s regression guards
uv run ruff check src tests
uv run mypy                                    # strict; packages = ["nmrcheck"]
```

Run tests **serially locally** for clean debugging. CI shards with `pytest-split` (`uv run --with pytest-split pytest -n auto --splits 4 --group N`) — `pytest-split` and `pytest-timeout` are pulled in just-in-time via `uv run --with` and are deliberately absent from `pyproject.toml`.

Slow numerical tests must keep the BLAS thread pins (`OMP_NUM_THREADS=1` etc., see `ci-cd.yml`). Without them, OpenBLAS initialised before `execnet` forks crashes xdist workers on Linux while passing on macOS/ARM.

### Frontend (`cd moltrace_frontend`)

```bash
pnpm install
pnpm dev            # :3000
pnpm build          # NOTE: next.config.mjs sets typescript.ignoreBuildErrors — build does NOT typecheck
pnpm typecheck      # tsc --noEmit — the real type gate
pnpm lint           # eslint .
pnpm test           # vitest (watch); CI uses `pnpm test -- --run`
pnpm vitest path/to/file.test.tsx --run   # single file
pnpm generate:openapi                      # regenerate the FE↔BE contract; backend must be on :8000
```

Node 22.14.0 / pnpm 11.0.3 are pinned in `engines`.

### Whitepapers

`make -C whitepaper-build all` (Pandoc + XeLaTeX / Typst).

## Architecture

### The deterministic-first contract

This is the organising principle of the whole codebase, and most review comments trace back to it:

- **The deterministic verifier is the sole arbiter of correctness.** `moltrace.spectroscopy.verification.verify_structure` runs four independent tests and combines them via a Bayesian log-odds update. AI never overrides it — the RLHF reward model may only reorder *within* a verifier verdict class, and LLM `self_confidence` is never used as the verifier prior.
- **Regulated numbers come from a version-pinned rule engine**, never an LLM. Every regulatory result carries its `rule_set_version` and source-guidance citations. Unknown inputs return explicit `matched=false` / warnings — never a guessed limit.
- **Compliance language is always "designed to support."** Part 11 / GAMP 5 / SOC 2 / ICH are framed as controls that help customers meet a standard; no function emits a self-compliance claim. SOC 2 is not held.
- Every regulatory result carries `human_review_required=True`.

### Backend layers

- `src/nmrcheck/` — the HTTP layer. `api.py` is a **~31k-line monolith** holding a single `router = APIRouter()` plus `create_app()`; `models.py` (~17k lines) holds Pydantic models and `orm.py` (~7k) the SQLAlchemy tables. `main.py` is a thin 45-line entrypoint. Alongside it sit ~145 focused modules: auth (`security.py`, `authz.py`, `session_store.py`, `mfa_*.py`, `oidc_client.py`, `scim_store.py`), science engines (`gsd.py`, `fid.py`, `dp4_scoring.py`, `nmr2d_*.py`), and the Repho reaction engines (`reaction_*.py`).
- `src/moltrace/spectroscopy/` — modular NMR/MS science (peaks, multiplet, predict, verification, similarity, nus, integration, qnmr, classify) plus the AI model lifecycle (`ai/ eval/ data/ feedback/ ops/`) and the HMAC-chained `audit/`.
- `src/moltrace/regulatory/` — the deterministic ICH/FDA/EMA engine (`impurities/ specifications/ stability/ ctd/ quality/`) plus `data/` (licence-aware guidance corpus), `intelligence/` (grounded RAG), `ai/ compliance/ eval/ ops/`.

**Access gates are attached at `include_router` time**, not per-endpoint (`_baseline_access_gate` in `api.py`). A new endpoint inherits the baseline gate automatically — but resource-level authorization is *not* inherited. Every endpoint touching a dossier, campaign, or registry record must apply its own owner/team scope check and return a **non-leaking 404** (indistinguishable from "does not exist") rather than 403.

### Frontend layers

- `app/` at the project root is the **active App Router tree**. `src/app/` is a **non-routed mirror** kept for a future migration — Next.js resolves `app/` at the root when it exists, so `src/app/` files never render and have already drifted from their root counterparts. Edit `app/`.
- Both `components/`+`lib/` (root) and `src/components/`+`src/lib/` are live and imported. The `@/*` alias maps to `./*`, so `@/components/…` is the root tree and `@/src/lib/…` is the src tree. Check which one an existing import uses before adding a sibling.
- `app/api/backend/[...path]/route.ts` is a same-origin proxy to FastAPI. The browser **always** calls `/api/backend/*`; `lib/api/client.ts` deliberately ignores an absolute `NEXT_PUBLIC_API_BASE_URL`. The proxy also **sanitizes 401/403 response bodies**, with one allowlist: a 401 whose `detail` is exactly `step_up_required`, `token_expired`, `token_invalid`, or `token_reuse_detected` passes through verbatim (the step-up and rotating-refresh flows depend on it). Every other `detail` on a 401/403 is replaced, so distinguish those cases by status code, not message.

### The FE↔BE contract

`src/lib/api/schema.d.ts` (generated from `/openapi.json` by openapi-typescript) is the binding contract. **Contracts first**: for any change crossing the boundary, update the FastAPI routes/models and regenerate the schema *before* touching the frontend.

A recurring bug class: the FE sends a key a Pydantic model rejects under `extra=forbid` → a 100% 422 rate. Diagnose by A/B-posting to a nonexistent id — 422 means bad shape, 404 means the shape was valid.

## Database and migrations

`DATABASE_URL` unset → `sqlite:///./nmrcheck.sqlite3`, so the backend runs with zero external services.

**Alembic migrations are Postgres deltas over an ORM-created schema — they cannot bootstrap a fresh database.** The app builds the schema at startup via `init_db()` → `create_all()`, and Alembic is then `stamp`ed. Tests likewise build via `create_all()` + `_ensure_sqlite_schema()` (`src/nmrcheck/database.py`), not by running migrations. A migration that relaxes a constraint also needs its SQLite-side counterpart (`_sqlite_make_column_nullable`).

In production, migrations run as the one-off Cloud Run job `moltrace-migrate` — **never chained into the start command** (that would race across autoscaled instances).

`tests/conftest.py` builds the ~800-route app **once per xdist worker** (`routed_app`) and swaps a fresh seeded SQLite DB onto `app.state.session_factory` per test. If you add a startup seed step to `create_app`'s lifespan, mirror it in `seed_database()` — the lifespan closes over the build-time factory, not `app.state`.

## Deploy and CI

- Frontend → **Vercel** (`moltrace.co`). Vercel auto-deploy is disabled (`vercel.json` `git.deploymentEnabled: false`); only green CI reaches production, via the deploy hook in `ci-cd.yml`. A `git push` alone therefore ships nothing — ask the maintainer for the manual deploy procedure rather than guessing at CLI flags.
- Backend → **Google Cloud Run** (service `moltrace-backend`, project `moltrace-prod`, us-central1) via keyless Workload Identity Federation, sequence build → migrate job → new revision.
- Database → **Cloud SQL for PostgreSQL 16** on a private IP over Direct VPC egress.
- `render.yaml` and any Render references are **legacy** — production has been GCP since July 2026. Verify infra facts against the README, not against older docs.

Gates in `ci-cd.yml` that block the deploy jobs: both test suites, `uv run moltrace-deployment-gate --self-check` (fail-closed: dominance / audit-chain / tests-green / data-leakage), `uv run python -m moltrace.regulatory.ops --self-check`, and SBOM + SLSA provenance verification. The slow backend suite runs on pushes to `main` as an independent signal and does **not** block.

Security scanning lives in separate workflows — `secret-scan.yml` (gitleaks, mirrored by the opt-in pre-commit hook) and `security-scan.yml` (Semgrep SAST, Trivy SCA + IaC). These only block a merge if added as required status checks; check the branch protection settings before assuming a finding is enforcing. Trivy suppressions live in the repo-root `.trivyignore` — prefer a real version bump over a suppression when the bump is low-risk.

CI runs Python **3.13.5** while local may be newer — 3.13 evaluates annotations eagerly, so dropping an import used only inside an annotation passes locally and fails CI at collection.

## Conventions

- **Conventional commits** (`type(scope): summary`), matching the existing history.
- **No backend jargon in user-visible copy** — no endpoint paths, HTTP verbs, status codes, `_json` field names, or the word "backend" in strings a user reads. Humanize the *display* only; never rename wire keys.
- Keep the root `README.md` and the six `whitepaper-build/` papers current in the same change as any significant development.
- Add the ignore pattern in the same change as anything generated (weights, `hose_kb*.json`, caches, DBs). Do **not** blanket-ignore `*.output` — those are legitimate Bruker fixtures.
- Bounds and thresholds come from the measured data distribution, not round numbers, and a rejection message should name its cause.
- A test asserting current behaviour may be encoding the bug. When fixing science, write the invariant test first, then re-baseline visibly.

## Licensing

Source-available under **BUSL 1.1**, not open source — the repository is public, production use requires a commercial license, and each version converts to Apache 2.0 on 2030-06-23. Code contributions require a signed CLA (`CONTRIBUTING.md`).

## Where to look

- `moltrace_backend/CHANGELOG.md` — the authoritative record of what actually shipped (in-code version numbers are not unified across the two apps).
- `moltrace_backend/docs/` — 82 design and handoff documents.
- `RELEASE_GUARDRAILS.md`, `SECURITY.md`, `compliance/`.
