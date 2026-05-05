import { ApiError } from "@/lib/api/client"

/** First pipe-delimited SMILES-like token from candidate lines (e.g. `Ethanol | CCO | proposed`). */
export function extractFirstSmiles(candidatesText: string): string {
  const line = candidatesText.split(/\r?\n/).find((l) => l.trim().length > 0)
  if (!line) return ""
  const parts = line.split("|").map((p) => p.trim())
  if (parts.length >= 2 && parts[1].length > 0) return parts[1]
  const m = line.match(/\b([A-Za-z0-9@+\-=().#/]{2,})\b/)
  return m?.[1] ?? ""
}

export function authErrorMessage(): string {
  return "Backend requires authentication. For local development, disable backend auth temporarily or add login/token handling. TODO: Add login flow and attach Authorization: Bearer <token> when backend auth is enabled."
}

export function formatApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return authErrorMessage()
  if (err instanceof ApiError && err.status === 404) return "Backend endpoint not available yet."
  return err instanceof Error ? err.message : fallback
}
