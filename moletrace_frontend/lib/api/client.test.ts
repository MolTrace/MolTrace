import { afterEach, describe, expect, it, vi } from "vitest"
import { ApiError, AUTH_TOKEN_STORAGE_KEY, apiFetch, buildApiPath } from "@/lib/api/client"

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe("apiFetch", () => {
  it("builds proxy paths", () => {
    expect(buildApiPath("/openapi.json")).toBe("/api/backend/openapi.json")
    expect(buildApiPath("openapi.json")).toBe("/api/backend/openapi.json")
  })

  it("uses /api/backend as the frontend base path", async () => {
    const fetchMock = vi.fn(async () => {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    })
    vi.stubGlobal("fetch", fetchMock)

    await apiFetch<{ ok: boolean }>("/openapi.json")

    const [url] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe("/api/backend/openapi.json")
  })

  it("adds the stored auth token to API requests", async () => {
    const fetchMock = vi.fn(async () => {
      return new Response(JSON.stringify({ email: "admin@example.com" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    })
    vi.stubGlobal("fetch", fetchMock)
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, "admin-token")

    await apiFetch<{ email: string }>("/auth/me")

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const headers = init.headers as Headers
    expect(headers.get("authorization")).toBe("Bearer admin-token")
  })

  it("does not set content-type for FormData", async () => {
    const fetchMock = vi.fn(async () => {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    })
    vi.stubGlobal("fetch", fetchMock)

    const formData = new FormData()
    formData.append("sample_id", "SAMPLE-001")

    await apiFetch<{ ok: boolean }>("/prediction/nmr/match/evidence", {
      method: "POST",
      body: formData,
    })

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const headers = init.headers as Headers
    expect(headers.has("content-type")).toBe(false)
  })

  it("throws ApiError on non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        return new Response(JSON.stringify({ detail: "Authentication required." }), {
          status: 401,
          statusText: "Unauthorized",
          headers: { "content-type": "application/json" },
        })
      })
    )

    await expect(apiFetch("/protected")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      data: { detail: "Authentication required." },
    } satisfies Partial<ApiError>)
  })
})
