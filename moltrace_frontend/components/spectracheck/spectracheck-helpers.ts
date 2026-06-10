import { ApiError, sanitizePublicApiErrorMessage } from "@/lib/api/client"

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
  return "Sign in to access live MolTrace data."
}

export function formatApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiError && (err.status === 401 || err.status === 403)) return authErrorMessage()
  if (err instanceof ApiError && err.status === 404) {
    // FastAPI returns {"detail":"Not Found"} for an unmatched route — the only
    // 404 that means "endpoint not available". Surface any other 404 detail
    // (e.g. "Project not found.") instead of mislabeling a resource error.
    const detail =
      err.data && typeof err.data === "object" && typeof (err.data as { detail?: unknown }).detail === "string"
        ? (err.data as { detail: string }).detail.trim()
        : ""
    if (detail && detail.toLowerCase() !== "not found") {
      return sanitizePublicApiErrorMessage(detail, 404)
    }
    return "Backend endpoint not available yet."
  }
  if (err instanceof Error) {
    return sanitizePublicApiErrorMessage(err.message, err instanceof ApiError ? err.status : undefined)
  }
  return sanitizePublicApiErrorMessage(fallback)
}
