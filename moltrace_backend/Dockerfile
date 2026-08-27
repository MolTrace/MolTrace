# syntax=docker/dockerfile:1
#
# MolTrace backend image (FastAPI API + RQ worker share this one image).
#   * API:    default CMD -> uvicorn nmrcheck.main:app  (listens on $PORT, default 8080)
#   * Worker: override command -> python -m nmrcheck.worker
#   * Migrations: run SEPARATELY (Cloud Run Job / compose one-shot) -- never in CMD,
#     or every autoscaled instance races `alembic upgrade head`.
#
# Build context is moltrace_backend/. Verify locally or via `gcloud builds submit`.

# ---------- build stage ----------
FROM python:3.13-slim AS build

# uv provides fast, lockfile-frozen installs (the same resolver CI runs).
#
# PINNED BY DIGEST, and the tag is only there to be readable — Docker resolves the
# digest and ignores it. This was `:latest`, which made the installer the one
# mutable third-party input to a production image in a pipeline that otherwise
# pins its GitHub Actions by SHA, verifies SLSA provenance as a release gate and
# publishes a CycloneDX SBOM. Not hypothetical: the tag was republished as 0.12.5
# on 2026-08-14 19:24 UTC, so images built either side of that afternoon were
# resolved by different uv binaries. The SBOM records the packages that came out,
# never the resolver that chose them, so nothing downstream would have shown it.
#
# Bumping uv is now a visible commit: pick the version, read its digest with
#   docker buildx imagetools inspect ghcr.io/astral-sh/uv:<version>
# and edit both halves of this reference together.
COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Build toolchain for any dependency that ships an sdist instead of a manylinux
# wheel (e.g. lttbc's C extension, cffi behind argon2-cffi). Discarded with this stage.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Resolve dependencies first so this layer caches until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra fid --extra gcs --no-install-project

# 2) Add the source and install the project itself.
COPY . .
RUN uv sync --frozen --no-dev --extra fid --extra gcs

# ---------- runtime stage ----------
FROM python:3.13-slim

# Shared libraries the scientific stack loads at runtime:
#   libgomp1  -> OpenMP for faiss-cpu / scipy / rdkit
#   libxrender1, libxext6 -> rdkit drawing/molops
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 libxrender1 libxext6 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 app

WORKDIR /app
COPY --from=build --chown=app:app /app /app

# HOSE-code knowledge base. `COPY . .` in the build stage already carried
# data/hose/ across, so this only points the predictor at it.
#
# Present  -> full NMRShiftDB2 table: ~0% element-prior fallback, median 13C
#             uncertainty 1.88 ppm (below DP4's 2.306 ppm scale). +14 MB image,
#             ~1 s one-off load.
# Absent   -> bundled 16-molecule seed table: ~23-44% of atoms fall to a bare
#             element prior and median 13C uncertainty is ~35 ppm. The service
#             still starts and every prediction reports its own coverage, so this
#             degrades visibly — but it is not a production state.
#
# See data/hose/README.md to build it. The file is gitignored (NMRShiftDB2
# derivative, CC BY-SA — see NOTICE), so it must be placed in the build context
# before `gcloud builds submit`.
# Conformal shift calibration. Unlike the HOSE table this one IS in the repository
# (4.7 KB of residual quantiles, reconstructing nothing of NMRShiftDB2 -- see
# data/conformal/README.md), so `COPY . .` always carries it and there is nothing to
# stage. Without it the verifier weighs every matched resonance on the predictor's
# claimed sigma, which held-out measurement showed is differentially mis-scaled --
# half-width/sigma running 8.66x down to 1.77x where a correct sigma gives a constant,
# and worst in the tight bins the arbiter leans on hardest. /health reports it.
ENV PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production \
    PYTHONUNBUFFERED=1 \
    MOLTRACE_HOSE_KB=/app/data/hose/hose_index.json.gz \
    MOLTRACE_CONFORMAL_CALIBRATION=/app/data/conformal/shift_calibration.json \
    PORT=8080

# Fail the build when the knowledge base is absent: a clean CI checkout lacks the
# gitignored table, and the resulting image would silently serve the seed
# predictor in production (the exact failure the block above describes). CI
# stages the file from gs://moltrace-model-weights/hose/ before building; a
# deliberately degraded local image needs --build-arg REQUIRE_HOSE_KB=0.
ARG REQUIRE_HOSE_KB=1
RUN if [ "$REQUIRE_HOSE_KB" = "1" ] && [ ! -s "$MOLTRACE_HOSE_KB" ]; then \
      echo "ERROR: $MOLTRACE_HOSE_KB is missing or empty in the build context." \
           "Stage data/hose/hose_index.json.gz before building, or pass" \
           "--build-arg REQUIRE_HOSE_KB=0 for a seed-table dev image." >&2; \
      exit 1; \
    fi

# Build provenance. `current_git_sha()` (spectroscopy/infra/versioning.py:109) resolves
# $MOLTRACE_GIT_SHA -> `git rev-parse` -> the literal "unknown", and never raises. In this
# image the middle step cannot succeed: .dockerignore:4 excludes .git/, and the runtime
# stage is a bare `python` base with no git installed. Nothing set the variable, so every
# RegistryEntry.code_sha in production has been "unknown" — the one field that says which
# code produced a regulated result.
#
# Deliberately defaulted to EMPTY rather than to the image tag. An empty value is falsy in
# Python, so it falls through to the honest "unknown"; baking the `_TAG` default of "latest"
# would instead stamp every record with a plausible-looking value that is not a revision.
# A degenerate provenance field must look degenerate.
#
# Placed last so it invalidates no earlier layer: this argument changes on every commit.
ARG MOLTRACE_GIT_SHA=""
ENV MOLTRACE_GIT_SHA=${MOLTRACE_GIT_SHA}

USER app
EXPOSE 8080

# `sh -c` so Cloud Run's injected $PORT is honored (it is not always 8080).
CMD ["sh", "-c", "exec python -m uvicorn nmrcheck.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
