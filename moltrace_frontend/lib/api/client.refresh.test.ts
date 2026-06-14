import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { apiFetch, ApiError } from "@/lib/api/client"

// Drives apiFetch's rotating-refresh logic by stubbing the global fetch.

type Call = { url: string; method: string; headers: Headers; body: string | null }
let calls: Call[] = []

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })
}

const mockFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(input)
  calls.push({
    url,
    method: init?.method ?? "GET",
    headers: new Headers(init?.headers),
    body: typeof init?.body === "string" ? init.body : null,
  })
  // default — overridden per test via mockFetch.mockImplementation
  return jsonResponse(200, {})
})

function refreshCalls() {
  return calls.filter((c) => c.url.includes("/auth/refresh"))
}
function productCalls() {
  return calls.filter((c) => !c.url.includes("/auth/refresh"))
}
function seed(access: string | null, refresh: string | null) {
  if (access) window.localStorage.setItem("moltrace.access_token", access)
  if (refresh) window.localStorage.setItem("moltrace.refresh_token", refresh)
}

beforeEach(() => {
  calls = []
  window.localStorage.clear()
  vi.stubGlobal("fetch", mockFetch)
  mockFetch.mockReset()
})
afterEach(() => vi.unstubAllGlobals())

describe("apiFetch — rotating refresh", () => {
  it("single-flights one /auth/refresh for concurrent 401s, rotates both tokens, and retries", async () => {
    mockFetch.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push({ url, method: init?.method ?? "GET", headers: new Headers(init?.headers), body: null })
      if (url.includes("/auth/refresh")) {
        return jsonResponse(200, { access_token: "new-access", refresh_token: "new-refresh", expires_at: "2099-01-01T00:00:00Z" })
      }
      const auth = new Headers(init?.headers).get("authorization")
      return auth === "Bearer new-access" ? jsonResponse(200, { ok: true }) : jsonResponse(401, { detail: "not authenticated" })
    })
    seed("old-access", "old-refresh")

    const [a, b] = await Promise.all([apiFetch<{ ok: boolean }>("/projects"), apiFetch<{ ok: boolean }>("/reaction-projects")])

    expect(a.ok).toBe(true)
    expect(b.ok).toBe(true)
    expect(refreshCalls().length).toBe(1) // single-flight
    expect(window.localStorage.getItem("moltrace.access_token")).toBe("new-access")
    expect(window.localStorage.getItem("moltrace.refresh_token")).toBe("new-refresh")
  })

  it("treats token_reuse_detected as a hard logout — clears the family, no retry, fires auth-reset", async () => {
    let resetReason: string | undefined
    const onReset = (e: Event) => {
      resetReason = (e as CustomEvent<{ reason?: string }>).detail?.reason
    }
    window.addEventListener("moltrace:auth-reset", onReset)
    mockFetch.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      calls.push({ url, method: init?.method ?? "GET", headers: new Headers(init?.headers), body: null })
      if (url.includes("/auth/refresh")) return jsonResponse(401, { detail: "token_reuse_detected" })
      return jsonResponse(401, { detail: "not authenticated" })
    })
    seed("old-access", "old-refresh")

    await expect(apiFetch("/projects")).rejects.toBeInstanceOf(ApiError)
    expect(window.localStorage.getItem("moltrace.access_token")).toBeNull()
    expect(window.localStorage.getItem("moltrace.refresh_token")).toBeNull()
    expect(resetReason).toBe("token_reuse_detected")
    expect(productCalls().length).toBe(1) // NOT retried
    window.removeEventListener("moltrace:auth-reset", onReset)
  })

  it("does not refresh on auth-issuing routes (recursion guard)", async () => {
    mockFetch.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), method: init?.method ?? "GET", headers: new Headers(init?.headers), body: null })
      return jsonResponse(401, { detail: "invalid credentials" })
    })
    seed("old-access", "old-refresh")
    await expect(apiFetch("/auth/login", { method: "POST", body: { email: "a", password: "b" } })).rejects.toBeInstanceOf(ApiError)
    expect(refreshCalls().length).toBe(0)
  })

  it("does not refresh a step_up_required 401 (handled by withStepUp)", async () => {
    mockFetch.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), method: init?.method ?? "GET", headers: new Headers(init?.headers), body: null })
      return jsonResponse(401, { detail: "step_up_required" })
    })
    seed("old-access", "old-refresh")
    await expect(apiFetch("/esignatures/records", { method: "POST", body: {} })).rejects.toMatchObject({
      status: 401,
      data: { detail: "step_up_required" },
    })
    expect(refreshCalls().length).toBe(0)
  })

  it("sends a stable X-Client-Id on every request", async () => {
    mockFetch.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), method: init?.method ?? "GET", headers: new Headers(init?.headers), body: null })
      return jsonResponse(200, {})
    })
    await apiFetch("/projects")
    await apiFetch("/reaction-projects")
    const cid1 = calls[0].headers.get("x-client-id")
    const cid2 = calls[1].headers.get("x-client-id")
    expect(cid1).toBeTruthy()
    expect(cid1).toBe(cid2)
  })
})
