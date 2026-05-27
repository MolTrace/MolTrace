#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/moltrace_backend"
FRONTEND_DIR="${ROOT_DIR}/moltrace_frontend"

if [[ ! -d "${BACKEND_DIR}" || ! -d "${FRONTEND_DIR}" ]]; then
  echo "Prompt sidecar guardrails require a monorepo checkout with moltrace_backend and moltrace_frontend." >&2
  echo "Resolved root: ${ROOT_DIR}" >&2
  exit 2
fi

echo "==> Backend raw-FID Prompt sidecar metadata-only guardrails"
(
  cd "${BACKEND_DIR}"
  PYTHONPATH=src uv run pytest -q \
    tests/test_nmr_frontend_upload_api.py::test_nmr_raw_fid_prompt_sidecar_api_contract_is_metadata_only \
    tests/test_fid.py::test_raw_fid_vault_prompt_sidecar_is_metadata_only_and_non_disruptive
)

echo "==> Frontend SpectraCheck Prompt sidecar visibility guardrails"
(
  cd "${FRONTEND_DIR}"
  pnpm test:spectracheck-sidecar
)

echo "Prompt sidecar guardrails passed."
