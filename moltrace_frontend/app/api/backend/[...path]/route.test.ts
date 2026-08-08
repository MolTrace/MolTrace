import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { NextRequest } from "next/server"

import { GET } from "./route"

/**
 * The proxy sanitizes 401/403 bodies so internal auth detail cannot reach a
 * browser, and passes through only the machine-readable codes the backend marks
 * public. That is security-relevant and had no test at all.
 *
 * The property worth locking is that it FAILS CLOSED: an unrecognised code is
 * stripped, not forwarded. A future backend can add a public code without this
 * list, and the worst outcome must be a client that cannot distinguish the case —
 * never a client that receives an internal one.
 */

const fetchMock = vi.fn()

function upstream(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

// The handler reads `request.nextUrl.search`, so it needs a NextRequest rather
// than a bare Request.
function request(path = "http://localhost:3000/api/backend/anything") {
  return new NextRequest(new URL(path))
}

const params = Promise.resolve({ path: ["anything"] })

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock)
  fetchMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("backend proxy — 401/403 sanitization", () => {
  it("passes a public code through, with its own copy as the detail", async () => {
    fetchMock.mockResolvedValueOnce(
      upstream(401, { code: "step_up_required", detail: "A fresh authentication step is required." }),
    )
    const res = await GET(request(), { params })
    const body = (await res.json()) as { code?: string; detail?: string }

    expect(res.status).toBe(401)
    expect(body.code).toBe("step_up_required")
    // The backend's prose is not written for this surface; the client branches on
    // the code, so the detail is replaced rather than forwarded.
    expect(body.detail).not.toBe("A fresh authentication step is required.")
  })

  it("passes a public code on a 403 — the case the old detail-matching dropped", async () => {
    fetchMock.mockResolvedValueOnce(
      upstream(403, { code: "product_not_in_plan", detail: "The product is not part of this plan." }),
    )
    const res = await GET(request(), { params })
    const body = (await res.json()) as { code?: string }

    expect(res.status).toBe(403)
    // Previously the sanitizer only inspected 401, so every 403 arrived generic
    // and the four upgrade states were indistinguishable from "access denied".
    expect(body.code).toBe("product_not_in_plan")
  })

  it("strips a code it does not recognise, rather than forwarding it", async () => {
    fetchMock.mockResolvedValueOnce(
      upstream(403, { code: "internal_policy_engine_denied", detail: "user 42 lacks scope admin:write" }),
    )
    const res = await GET(request(), { params })
    const body = (await res.json()) as { code?: string; detail?: string }

    expect(body.code).toBeUndefined()
    expect(body.detail).not.toContain("user 42")
    expect(body.detail).not.toContain("admin:write")
  })

  it("sanitizes a 401 that carries no code at all", async () => {
    fetchMock.mockResolvedValueOnce(upstream(401, { detail: "token signature mismatch for kid=abc" }))
    const res = await GET(request(), { params })
    const body = (await res.json()) as { detail?: string }

    expect(body.detail).not.toContain("kid=abc")
  })

  it("does not touch a successful response", async () => {
    fetchMock.mockResolvedValueOnce(upstream(200, { ok: true, internal_note: "kept" }))
    const res = await GET(request(), { params })
    const body = (await res.json()) as { ok?: boolean; internal_note?: string }

    expect(res.status).toBe(200)
    expect(body.ok).toBe(true)
    expect(body.internal_note).toBe("kept")
  })
})
