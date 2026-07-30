import { ApiError } from "@/lib/api/client"

export const PROCESSED_NMR_BACKEND_MSG =
  "Processed-spectrum preview and analysis are not available on this MolTrace instance yet. Contact your MolTrace administrator to enable them."

export const RAW_FID_BACKEND_MSG =
  "Raw FID preview and processing are not available on this MolTrace instance yet. Contact your MolTrace administrator to enable them."

export function isMissingNmrEndpoint(err: unknown): boolean {
  if (err instanceof ApiError) {
    if (err.status === 404) return true
  }
  return false
}
