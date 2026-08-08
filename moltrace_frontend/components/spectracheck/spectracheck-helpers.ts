import { ApiError, sanitizePublicApiErrorMessage } from "@/lib/api/client"
import { readUpgradeRefusal, upgradeCopy } from "@/lib/api/upgrade-state"

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
  // A closed product is not a sign-in problem, and this formatter is used by ~104
  // surfaces — so until now every one of them answered "Sign in to access live
  // MolTrace data" to a user whose administrator simply had not switched a
  // product on. Telling someone to sign in when they are already signed in, and
  // when signing in again cannot possibly help, is the worst of the four wrong
  // guesses the single generic lock produced.
  //
  // Checked before the 401/403 branch precisely because that branch would
  // otherwise swallow it. Falls through untouched when the refusal is not one of
  // the four, so ordinary auth failures still read as they did.
  const refusal = readUpgradeRefusal(err)
  if (refusal) return upgradeCopy(refusal).title

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
    return "This capability is not available on this MolTrace instance yet."
  }
  if (err instanceof Error) {
    return sanitizePublicApiErrorMessage(err.message, err instanceof ApiError ? err.status : undefined)
  }
  return sanitizePublicApiErrorMessage(fallback)
}
