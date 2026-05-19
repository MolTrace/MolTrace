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

function publicApiBase(): string {
  const configuredBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim()
  if (!configuredBase) return DEFAULT_API_BASE
  if (/^https?:\/\//i.test(configuredBase)) return DEFAULT_API_BASE
  return configuredBase
}

export const API_BASE = publicApiBase()
export const AUTH_TOKEN_STORAGE_KEY = "moltrace.access_token"
export const AUTH_USER_STORAGE_KEY = "moltrace.user"
export const TENANT_ID_STORAGE_KEY = "moltrace.current_tenant_id"
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

async function parseResponseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") || ""
  if (contentType.includes("application/json")) {
    return response.json()
  }
  return response.text()
}

function resolveErrorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object") {
    if ("detail" in data) return String((data as { detail: unknown }).detail)
    if ("message" in data) return String((data as { message: unknown }).message)
    if ("error" in data) {
      const error = (data as { error: unknown }).error
      if (typeof error === "string") return error
      if (error && typeof error === "object" && "message" in error) {
        return String((error as { message: unknown }).message)
      }
    }
  }
  if (typeof data === "string" && data.trim().length > 0) return data
  return fallback
}

function authFailureMessage(status: number): string {
  if (status === 403) return "You do not have access to perform this action."
  return "Sign in to access live MolTrace data."
}

export function sanitizePublicApiErrorMessage(
  message: string,
  status?: number,
  fallback = GENERIC_REQUEST_FAILURE_MESSAGE
): string {
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

export async function apiFetch<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const requestBody = init.body
  let body: BodyInit | undefined

  if (!headers.has("authorization")) {
    const token = readStoredAuthToken()
    if (token) headers.set("authorization", `Bearer ${token}`)
  }

  if (!headers.has("x-tenant-id")) {
    const tenantId = readStoredTenantId()
    if (tenantId) headers.set("x-tenant-id", tenantId)
  }

  if (requestBody !== undefined && !isFormDataBody(requestBody) && !headers.has("content-type")) {
    headers.set("content-type", "application/json")
  }

  if (requestBody !== undefined) {
    body = isBodyInit(requestBody) ? requestBody : JSON.stringify(requestBody)
  }

  const response = await fetch(buildApiPath(path), {
    ...init,
    headers,
    body,
    cache: "no-store",
  })

  if (!response.ok) {
    const data = await parseResponseBody(response)
    const rawMessage = resolveErrorMessage(data, response.statusText)
    const message = sanitizePublicApiErrorMessage(rawMessage, response.status)
    throw new ApiError(response.status, data, message)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await parseResponseBody(response)) as T
}
