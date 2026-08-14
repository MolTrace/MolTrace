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

# uv provides fast, lockfile-frozen installs (matches CI + Render).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
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
ENV PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production \
    PYTHONUNBUFFERED=1 \
    MOLTRACE_HOSE_KB=/app/data/hose/hose_index.json.gz \
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

USER app
EXPOSE 8080

# `sh -c` so Cloud Run's injected $PORT is honored (it is not always 8080).
CMD ["sh", "-c", "exec python -m uvicorn nmrcheck.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
