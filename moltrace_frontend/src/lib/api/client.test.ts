import { afterEach, describe, expect, it, vi } from "vitest"
import {
  API_BASE,
  ApiError,
  AUTH_TOKEN_STORAGE_KEY,
  GENERIC_REQUEST_FAILURE_MESSAGE,
  apiFetch,
  buildApiPath,
  sanitizePublicApiErrorMessage,
} from "@/src/lib/api/client"

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
  window.localStorage.clear()
})

describe("src api client", () => {
  it("builds proxy paths", () => {
    expect(API_BASE).toBe("/api/backend")
    expect(buildApiPath("/openapi.json")).toBe("/api/backend/openapi.json")
  })

  it("keeps browser requests on the Next proxy even if a backend URL is configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://moltrace-backend.onrender.com")
    vi.resetModules()

    const client = await import("@/src/lib/api/client")

    expect(client.API_BASE).toBe("/api/backend")
    expect(client.buildApiPath("/nmr/processed/preview")).toBe("/api/backend/nmr/processed/preview")
  })

  it("adds the stored auth token to API requests", async () => {
    const fetchMock = vi.fn(async () => {
      return new Response(JSON.stringify({ email: "user@example.com" }), {
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
      message: "Sign in to access live MolTrace data.",
    } satisfies Partial<ApiError>)
  })

  it("redacts backend auth guidance from public error messages", async () => {
    const leakyDetail = [
      ["Backend", "requires", "authentication."].join(" "),
      ["For", "local", "development,"].join(" "),
      "disable backend auth temporarily.",
      ["Authorization:", "Bearer", "<" + "token" + ">"].join(" "),
    ].join(" ")

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        return new Response(JSON.stringify({ detail: leakyDetail }), {
          status: 401,
          statusText: "Unauthorized",
          headers: { "content-type": "application/json" },
        })
      })
    )

    await expect(apiFetch("/protected")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: "Sign in to access live MolTrace data.",
    } satisfies Partial<ApiError>)
  })

  it("redacts internal prompt and credential markers from non-auth messages", () => {
    const leakyMessage = [
      ["raw", "prompt"].join(" "),
      "included",
      "with",
      ["api", "key"].join(" "),
      "guidance.",
    ].join(" ")

    expect(sanitizePublicApiErrorMessage(leakyMessage, 500)).toBe(GENERIC_REQUEST_FAILURE_MESSAGE)
    expect(sanitizePublicApiErrorMessage("POST /private-endpoint failed.", 400)).toBe(
      GENERIC_REQUEST_FAILURE_MESSAGE
    )
  })

  it("replaces raw network fetch failures with user-friendly copy", () => {
    expect(sanitizePublicApiErrorMessage("Failed to fetch")).toBe(
      "Backend connection failed. Please retry in a moment."
    )
  })

  it("replaces provider gateway HTML with user-friendly copy", async () => {
    const renderErrorPage =
      '<!DOCTYPE html><html><head><title>502</title></head><body><h1>Bad Gateway</h1><p>Powered by Render</p></body></html>'

    expect(sanitizePublicApiErrorMessage(renderErrorPage, 502)).toBe(
      "Backend connection failed. Please retry in a moment."
    )

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        return new Response(renderErrorPage, {
          status: 502,
          statusText: "Bad Gateway",
          headers: { "content-type": "text/html" },
        })
      })
    )

    await expect(apiFetch("/nmr/raw-fid/preview")).rejects.toMatchObject({
      name: "ApiError",
      status: 502,
      message: "Backend connection failed. Please retry in a moment.",
    } satisfies Partial<ApiError>)
  })
})
