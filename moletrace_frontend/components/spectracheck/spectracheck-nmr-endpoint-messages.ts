import { ApiError } from "@/lib/api/client"

export const PROCESSED_NMR_BACKEND_MSG =
  "Backend endpoint not available yet. Ask Codex to add /nmr/processed/preview and /nmr/processed/analyze."

export const RAW_FID_BACKEND_MSG =
  "Backend endpoint not available yet. Ask Codex to add /nmr/raw-fid/preview and /nmr/raw-fid/process."

export function isMissingNmrEndpoint(err: unknown): boolean {
  if (err instanceof ApiError) {
    if (err.status === 404) return true
  }
  return false
}
