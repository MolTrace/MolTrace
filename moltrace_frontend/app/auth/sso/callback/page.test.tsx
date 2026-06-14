import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import SsoCallbackPage from "@/app/auth/sso/callback/page"

const mockApiFetch = vi.hoisted(() => vi.fn<(path: string, init?: unknown) => Promise<unknown>>())
const replace = vi.hoisted(() => vi.fn())
const codeRef = vi.hoisted(() => ({ value: "good-code" as string | null }))

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => ({ get: (k: string) => (k === "code" ? codeRef.value : null) }),
}))

const SESSION = {
  access_token: "sso-token",
  token_type: "bearer",
  expires_at: "2026-06-20T00:00:00Z",
  user: { id: 42, email: "newhire@acme.com", is_admin: false, is_verified: true },
}

describe("SsoCallbackPage", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
    replace.mockReset()
    codeRef.value = "good-code"
    window.localStorage.clear()
  })

  it("exchanges the code, stores the session, and redirects to /dashboard", async () => {
    mockApiFetch.mockResolvedValue(SESSION)
    render(<SsoCallbackPage />)

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"))
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/auth/sso/exchange",
      expect.objectContaining({ method: "POST", body: { code: "good-code" } }),
    )
    expect(window.localStorage.getItem("moltrace.access_token")).toBe("sso-token")
    expect(window.localStorage.getItem("moltrace.user")).toContain("newhire@acme.com")
  })

  it("bounces to /login?sso_error=1 when the code is missing (no exchange)", async () => {
    codeRef.value = null
    render(<SsoCallbackPage />)
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?sso_error=1"))
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  it("bounces to /login?sso_error=1 when the exchange fails (400 invalid/expired code)", async () => {
    const { ApiError } = await import("@/lib/api/client")
    mockApiFetch.mockRejectedValue(new ApiError(400, { detail: "x" }, "Bad code"))
    render(<SsoCallbackPage />)
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?sso_error=1"))
    expect(window.localStorage.getItem("moltrace.access_token")).toBeNull()
  })

  it("never renders the one-time code", () => {
    render(<SsoCallbackPage />)
    expect(screen.queryByText(/good-code/)).not.toBeInTheDocument()
    expect(screen.getByText(/Completing single sign-on/i)).toBeInTheDocument()
  })
})
