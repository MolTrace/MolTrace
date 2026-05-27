#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/moltrace_backend"
FRONTEND_DIR="${ROOT_DIR}/moltrace_frontend"

if [[ ! -d "${BACKEND_DIR}" || ! -d "${FRONTEND_DIR}" ]]; then
  echo "Release-health guardrails require a monorepo checkout with moltrace_backend and moltrace_frontend." >&2
  echo "Resolved root: ${ROOT_DIR}" >&2
  exit 2
fi

echo "==> Backend release-health contract guardrails"
(
  cd "${BACKEND_DIR}"
  PYTHONPATH=src uv run pytest -q tests/test_week21_release_health.py
)

echo "==> Frontend release-health parser and Deployment Settings guardrails"
(
  cd "${FRONTEND_DIR}"
  pnpm test:release-health
)

echo "Release-health contract guardrails passed."
