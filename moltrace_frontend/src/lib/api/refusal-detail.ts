/**
 * Some refusals have to be read verbatim.
 *
 * The shared error formatter deliberately genericises messages so a raw server string never
 * lands in front of a user — and for 502/503/504 it replaces the text outright with a
 * connection message. That is right for an unreachable service and wrong for the two refusals
 * here, where the server has said something specific and actionable:
 *
 * - a prediction 503 that means *the engine could not run* — the request was valid, so the
 *   answer is a retry, not a correction, and "could not reach the service" misnames the cause;
 * - an approval 400 that names the safety-critical metric a candidate regressed on, and by how
 *   much. Collapsing that into a generic failure would hide the one fact the reviewer needs.
 *
 * The raw body survives on the error, so the detail is read from there. Duck-typed on purpose:
 * both `lib/api/client` and `src/lib/api/client` define their own `ApiError`, and an
 * `instanceof` check against one silently fails for the other.
 */

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export function readErrorStatus(err: unknown): number | null {
  if (!isRecord(err)) return null
  const status = err.status
  return typeof status === "number" && Number.isFinite(status) ? status : null
}

/**
 * The server's own `detail` for a refusal at `status`, or null.
 *
 * Returns null when `detail` is not a plain string — a list of field errors is the validation
 * shape, which belongs to per-field messages rather than a verbatim banner.
 */
export function readRefusalDetail(err: unknown, status: number): string | null {
  if (readErrorStatus(err) !== status) return null
  if (!isRecord(err)) return null
  const data = err.data
  if (!isRecord(data)) return null
  const detail = data.detail
  if (typeof detail !== "string") return null
  const trimmed = detail.trim()
  return trimmed.length > 0 ? trimmed : null
}
