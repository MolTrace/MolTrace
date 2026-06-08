#!/usr/bin/env bash
# Watch the latest GitHub Actions run for this checkout's current branch.
#
# Blocks until the run finishes, then:
#   - on failure: prints the failing step's log inline so you don't have
#     to leave the terminal to diagnose
#   - on either outcome: fires a macOS notification (silent no-op on
#     non-mac systems)
#   - exits with the run's own status code so you can chain it
#     (`./scripts/ci-watch.sh && say "ci green"` etc.)
#
# Usage:
#   ./scripts/ci-watch.sh                    # current branch
#   ./scripts/ci-watch.sh main               # explicit branch
#   ./scripts/ci-watch.sh main ci-cd.yml     # branch + workflow file
#
# Requires the GitHub CLI (`brew install gh && gh auth login`).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI not installed. Run: brew install gh && gh auth login" >&2
  exit 127
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "error: gh CLI not authenticated. Run: gh auth login" >&2
  exit 1
fi

branch="${1:-$(git -C "${ROOT_DIR}" rev-parse --abbrev-ref HEAD)}"
workflow="${2:-}"

# Find the latest run for this branch (any status, including queued or
# in-progress) — picking the newest entry means we follow the run that
# was triggered by the most recent push.
list_args=(--branch "${branch}" --limit 1 --json databaseId,status,conclusion,name,headSha)
if [ -n "${workflow}" ]; then
  list_args+=(--workflow "${workflow}")
fi

run_json="$(gh run list "${list_args[@]}" 2>/dev/null || true)"
run_id="$(printf '%s' "${run_json}" | jq -r '.[0].databaseId // empty')"

if [ -z "${run_id}" ]; then
  echo "no runs found for branch '${branch}'${workflow:+ (workflow: ${workflow})}" >&2
  exit 1
fi

run_sha="$(printf '%s' "${run_json}" | jq -r '.[0].headSha // empty' | cut -c1-7)"
run_name="$(printf '%s' "${run_json}" | jq -r '.[0].name // empty')"

echo "watching run ${run_id} (${run_name} @ ${run_sha}) on '${branch}'…"

# `--exit-status` makes gh exit non-zero if the run failed; we intercept
# so we can still surface logs and notify regardless of outcome.
status=0
gh run watch "${run_id}" --exit-status || status=$?

if [ "${status}" -ne 0 ]; then
  echo ""
  echo "── failing step log ──────────────────────────────────────────────"
  gh run view "${run_id}" --log-failed 2>&1 || true
  echo "── end of failing step log ───────────────────────────────────────"
fi

# macOS native notification. `osascript` is absent on Linux/WSL, so the
# `command -v` guard means this script stays portable.
if command -v osascript >/dev/null 2>&1; then
  if [ "${status}" -eq 0 ]; then
    msg="✓ Run ${run_id} on '${branch}' passed"
  else
    msg="✗ Run ${run_id} on '${branch}' failed — see terminal"
  fi
  osascript -e "display notification \"${msg}\" with title \"MolTrace CI\"" >/dev/null 2>&1 || true
fi

exit "${status}"
