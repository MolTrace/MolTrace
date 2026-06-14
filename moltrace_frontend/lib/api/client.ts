export class ApiError extends Error {
  status: number
  data: unknown

  constructor(status: number, data: unknown, message?: string) {
    super(message || `Request failed with status ${status}`)
    this.name = "ApiError"
    this.status = status
    this.data = data
  }
}

const DEFAULT_API_BASE = "/api/backend"

function publicApiBase() {
  const configuredBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim()
  if (!configuredBase) return DEFAULT_API_BASE
  if (/^https?:\/\//i.test(configuredBase)) return DEFAULT_API_BASE
  return configuredBase
}

export const API_BASE = publicApiBase()
export const AUTH_TOKEN_STORAGE_KEY = "moltrace.access_token"
export const AUTH_USER_STORAGE_KEY = "moltrace.user"
export const TENANT_ID_STORAGE_KEY = "moltrace.current_tenant_id"
export const REFRESH_TOKEN_STORAGE_KEY = "moltrace.refresh_token"
export const ACCESS_EXPIRES_STORAGE_KEY = "moltrace.access_expires_at"
export const CLIENT_ID_STORAGE_KEY = "moltrace.client_id"

/** Stable machine codes the backend returns (as a 401 `detail`) for the rotating
 *  refresh family. The /api/backend proxy passes these through verbatim. */
export const SESSION_ERROR_CODES = {
  EXPIRED: "token_expired",
  INVALID: "token_invalid",
  REUSE: "token_reuse_detected",
} as const
export const GENERIC_REQUEST_FAILURE_MESSAGE = "Request could not be completed. Please try again."
const BACKEND_CONNECTION_FAILURE_MESSAGE = "Backend connection failed. Please retry in a moment."

const INTERNAL_ERROR_MESSAGE_PATTERN =
  /(backend\s+requires\s+authentication|for\s+local\s+development|disable\s+backend\s+auth|disable_auth|disable_backend_auth|todo:|authorization\s*:\s*bearer|bearer\s*<\s*token\s*>|bearer\s+token|x-api-key|api[_\s-]?key|\b(?:get|post|put|patch|delete)\s+\/[a-z0-9]|\/api\/backend\/|raw\s+prompt|system\s+prompt|developer\s+prompt|chain[_\s-]?of[_\s-]?thought|\bcot\b|reasoning[_\s-]?trace|credential\s*[:=]|secret\s*[:=]|password\s*[:=]|private[_\s-]?key|service[_\s-]?account|traceback\s+\(most\s+recent\s+call\s+last\)|\bfile\s+"[^"]+")/i
const NETWORK_ERROR_MESSAGE_PATTERN = /failed\s+to\s+fetch|network\s*error|load\s+failed/i
const HTML_ERROR_MESSAGE_PATTERN = /<\s*(?:!doctype|html|head|body|title|style|script)\b/i
const GATEWAY_ERROR_MESSAGE_PATTERN =
  /\b(?:502|503|504)\b|bad\s+gateway|service\s+unavailable|gateway\s+timeout|powered\s+by\s+render|render.?s\s+documentation/i

type ApiRequestInit = Omit<RequestInit, "body"> & {
  body?: unknown
}

export function buildApiPath(path: string) {
  const normalizedBase = API_BASE.replace(/\/$/, "")
  const normalizedPath = path.startsWith("/") ? path : `/${path}`
  return `${normalizedBase}${normalizedPath}`
}

export function readStoredAuthToken() {
  if (typeof window === "undefined") return null

  try {
    return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

export function readStoredTenantId() {
  if (typeof window === "undefined") return null

  try {
    const tenantId = window.localStorage.getItem(TENANT_ID_STORAGE_KEY)
    if (!tenantId || tenantId === "local-development") return null
    return tenantId
  } catch {
    return null
  }
}

export function readStoredRefreshToken() {
  if (typeof window === "undefined") return null
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

/** True when the stored access token's expiry is past (small skew), so we can
 *  refresh proactively rather than waiting for a guaranteed 401. */
function isAccessExpired(skewMs = 5000): boolean {
  if (typeof window === "undefined") return false
  try {
    const raw = window.localStorage.getItem(ACCESS_EXPIRES_STORAGE_KEY)
    if (!raw) return false
    const at = Date.parse(raw)
    return Number.isFinite(at) && at - skewMs <= Date.now()
  } catch {
    return false
  }
}

/** A stable per-install id sent as `X-Client-Id` for optional device binding. */
export function getOrCreateClientId(): string {
  if (typeof window === "undefined") return ""
  try {
    let id = window.localStorage.getItem(CLIENT_ID_STORAGE_KEY)
    if (!id) {
      id =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `cid-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
      window.localStorage.setItem(CLIENT_ID_STORAGE_KEY, id)
    }
    return id
  } catch {
    return ""
  }
}

/** Low-level token writer — used by the high-level storeAuthSession and by the
 *  refresh-rotation path. Stores whatever is provided; leaves the rest. */
export function writeAuthTokens(
  accessToken: string,
  refreshToken?: string | null,
  accessExpiresAt?: string | null,
) {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, accessToken)
    if (refreshToken) window.localStorage.setItem(REFRESH_TOKEN_STORAGE_KEY, refreshToken)
    if (accessExpiresAt) window.localStorage.setItem(ACCESS_EXPIRES_STORAGE_KEY, accessExpiresAt)
  } catch {
    // private-mode / quota — ignore
  }
}

/** Clear the whole token family (access + refresh + expiry + user) — the hard
 *  logout used when refresh fails (expired / invalid / reuse-detected). */
export function clearStoredTokens() {
  if (typeof window === "undefined") return
  for (const key of [
    AUTH_TOKEN_STORAGE_KEY,
    REFRESH_TOKEN_STORAGE_KEY,
    ACCESS_EXPIRES_STORAGE_KEY,
    AUTH_USER_STORAGE_KEY,
  ]) {
    try {
      window.localStorage.removeItem(key)
    } catch {
      // ignore
    }
  }
}

function isFormDataBody(body: unknown): body is FormData {
  return typeof FormData !== "undefined" && body instanceof FormData
}

function isBodyInit(body: unknown): body is BodyInit {
  return (
    typeof body === "string" ||
    isFormDataBody(body) ||
    (typeof Blob !== "undefined" && body instanceof Blob) ||
    (typeof ArrayBuffer !== "undefined" && body instanceof ArrayBuffer) ||
    (typeof URLSearchParams !== "undefined" && body instanceof URLSearchParams) ||
    (typeof ReadableStream !== "undefined" && body instanceof ReadableStream)
  )
}

async function readResponseData(response: Response) {
  const contentType = response.headers.get("content-type") || ""
  if (contentType.includes("application/json")) {
    return response.json()
  }
  return response.text()
}

function formatDetailValue(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{ type, loc, msg, ... }, ...]
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item
        if (item && typeof item === "object") {
          const record = item as Record<string, unknown>
          const msg = typeof record.msg === "string" ? record.msg : null
          const loc = Array.isArray(record.loc)
            ? record.loc.filter((p) => typeof p === "string" || typeof p === "number").join(".")
            : null
          if (msg) return loc ? `${loc}: ${msg}` : msg
          if (typeof record.message === "string") return record.message
        }
        return ""
      })
      .filter(Boolean)
    if (messages.length > 0) return messages.join("; ")
  }
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>
    if (typeof record.msg === "string") return record.msg
    if (typeof record.message === "string") return record.message
    try {
      return JSON.stringify(detail)
    } catch {
      return fallback
    }
  }
  return fallback
}

function messageFromErrorData(data: unknown, fallback: string) {
  if (data && typeof data === "object") {
    if ("detail" in data) {
      return formatDetailValue((data as { detail: unknown }).detail, fallback)
    }
    if ("message" in data) return String((data as { message: unknown }).message)
    if ("error" in data) {
      const error = (data as { error: unknown }).error
      if (typeof error === "string") return error
      if (error && typeof error === "object" && "message" in error) {
        return String((error as { message: unknown }).message)
      }
    }
  }
  if (typeof data === "string" && data.trim()) return data
  return fallback
}

function authFailureMessage(status: number) {
  if (status === 403) return "You do not have access to perform this action."
  return "Sign in to access live MolTrace data."
}

export function sanitizePublicApiErrorMessage(
  message: string,
  status?: number,
  fallback = GENERIC_REQUEST_FAILURE_MESSAGE
) {
  if (status === 401 || status === 403) return authFailureMessage(status)

  const candidate = message.trim()
  if (!candidate) return fallback
  if (NETWORK_ERROR_MESSAGE_PATTERN.test(candidate)) return BACKEND_CONNECTION_FAILURE_MESSAGE
  if (status === 502 || status === 503 || status === 504) return BACKEND_CONNECTION_FAILURE_MESSAGE
  if (HTML_ERROR_MESSAGE_PATTERN.test(candidate) && GATEWAY_ERROR_MESSAGE_PATTERN.test(candidate)) {
    return BACKEND_CONNECTION_FAILURE_MESSAGE
  }
  if (candidate.startsWith("<") && HTML_ERROR_MESSAGE_PATTERN.test(candidate)) return fallback
  if (INTERNAL_ERROR_MESSAGE_PATTERN.test(candidate)) return fallback
  return candidate
}

function detailOf(data: unknown): string {
  if (data && typeof data === "object" && typeof (data as { detail?: unknown }).detail === "string") {
    return (data as { detail: string }).detail
  }
  return ""
}

// Auth-issuing routes must NOT trigger a refresh-retry: a 401 there is a real auth
// failure (bad credentials / spent code), and /auth/refresh itself would recurse.
const NO_REFRESH_PATH = /^\/auth\/(refresh|login|sign-in|sign-up|token|mfa\/login|sso\/exchange|logout)\b/

function eligibleForRefresh(path: string): boolean {
  const p = path.startsWith("/") ? path : `/${path}`
  return !NO_REFRESH_PATH.test(p) && Boolean(readStoredRefreshToken())
}

let refreshInFlight: Promise<string | null> | null = null

async function doRefresh(): Promise<string | null> {
  const refreshToken = readStoredRefreshToken()
  if (!refreshToken) return null

  let response: Response
  try {
    response = await fetch(buildApiPath("/auth/refresh"), {
      method: "POST",
      headers: { "content-type": "application/json", "x-client-id": getOrCreateClientId() },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    })
  } catch {
    return null // network blip — keep tokens; the original request surfaces its own error
  }

  if (response.ok) {
    const data = (await readResponseData(response)) as
      | { access_token?: string; refresh_token?: string | null; expires_at?: string | null }
      | null
    if (data && typeof data.access_token === "string") {
      writeAuthTokens(data.access_token, data.refresh_token ?? null, data.expires_at ?? null)
      return data.access_token
    }
    return null
  }

  // Any refresh failure ends the session (expired / invalid / reuse) — clear the
  // whole family and never retry. reuse is the same outcome plus a louder signal.
  const data = await readResponseData(response)
  const reason = detailOf(data) || "expired"
  clearStoredTokens()
  if (typeof window !== "undefined") {
    try {
      window.dispatchEvent(new CustomEvent("moltrace:auth-reset", { detail: { reason } }))
    } catch {
      // ignore
    }
  }
  return null
}

/** Single-flight refresh: concurrent 401s share ONE /auth/refresh — a second
 *  concurrent refresh of the same token trips server-side reuse detection. */
export function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

function buildHeaders(init: ApiRequestInit, requestBody: unknown): Headers {
  const headers = new Headers(init.headers)
  if (!headers.has("authorization")) {
    const token = readStoredAuthToken()
    if (token) headers.set("authorization", `Bearer ${token}`)
  }
  if (!headers.has("x-tenant-id")) {
    const tenantId = readStoredTenantId()
    if (tenantId) headers.set("x-tenant-id", tenantId)
  }
  if (!headers.has("x-client-id")) {
    const clientId = getOrCreateClientId()
    if (clientId) headers.set("x-client-id", clientId)
  }
  if (requestBody !== undefined && !isFormDataBody(requestBody) && !headers.has("content-type")) {
    headers.set("content-type", "application/json")
  }
  return headers
}

export async function apiFetch<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const requestBody = init.body
  const body: BodyInit | undefined =
    requestBody === undefined ? undefined : isBodyInit(requestBody) ? requestBody : JSON.stringify(requestBody)

  const callerSetAuth = new Headers(init.headers).has("authorization")
  const isStreamBody =
    typeof ReadableStream !== "undefined" && requestBody instanceof ReadableStream

  // Proactive: if we know the access token is already expired and a refresh token
  // exists, rotate first instead of burning a guaranteed 401.
  let refreshed = false
  if (!callerSetAuth && eligibleForRefresh(path) && isAccessExpired()) {
    await refreshAccessToken()
    refreshed = true
  }

  let response = await fetch(buildApiPath(path), { ...init, headers: buildHeaders(init, requestBody), body, cache: "no-store" })

  // Reactive: a non-step-up 401 on a product route → refresh once, then retry.
  // Skip if we already rotated proactively this call (a fresh token won't be
  // helped by another rotation, and re-refreshing would burn a token needlessly).
  if (response.status === 401 && !callerSetAuth && !isStreamBody && !refreshed && eligibleForRefresh(path)) {
    const data = await readResponseData(response)
    if (detailOf(data) === "step_up_required") {
      // re-auth signal handled by withStepUp, not a stale access token
      throw new ApiError(401, data, sanitizePublicApiErrorMessage(messageFromErrorData(data, response.statusText), 401))
    }
    const newToken = await refreshAccessToken()
    if (!newToken) {
      throw new ApiError(401, data, sanitizePublicApiErrorMessage(messageFromErrorData(data, response.statusText), 401))
    }
    response = await fetch(buildApiPath(path), { ...init, headers: buildHeaders(init, requestBody), body, cache: "no-store" })
  }

  if (!response.ok) {
    const data = await readResponseData(response)
    const rawMessage = messageFromErrorData(data, response.statusText)
    const message = sanitizePublicApiErrorMessage(rawMessage, response.status)
    throw new ApiError(response.status, data, message)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return readResponseData(response) as Promise<T>
}
