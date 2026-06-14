import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { SignInForm } from "@/components/marketing/sign-in-form"

const mockApiFetch = vi.hoisted(() => vi.fn<(path: string, init?: unknown) => Promise<unknown>>())
const push = vi.hoisted(() => vi.fn())

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
}))

const assignMock = vi.fn()

describe("SignInForm — SSO", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
    push.mockReset()
    assignMock.mockReset()
    window.localStorage.clear()
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { assign: assignMock, href: "http://localhost:3000/sign-in", origin: "http://localhost:3000" },
    })
  })

  it("starts SSO via a full-page navigation to the same-origin proxy login path (lowercased slug)", async () => {
    const user = userEvent.setup()
    render(<SignInForm />)
    await user.type(screen.getByLabelText("Organization sign-in ID"), "Acme")
    await user.click(screen.getByRole("button", { name: /Sign in with SSO/ }))
    expect(assignMock).toHaveBeenCalledWith("/api/backend/auth/sso/acme/login")
    expect(mockApiFetch).not.toHaveBeenCalled() // NOT a fetch — a top-level navigation
  })

  it("pre-fills the org slug from the ?sso deep link", () => {
    render(<SignInForm ssoSlug="acme" />)
    expect(screen.getByLabelText("Organization sign-in ID")).toHaveValue("acme")
  })

  it("shows the non-leaky banner when ?sso_error=1 is set", () => {
    render(<SignInForm ssoError />)
    expect(screen.getByText(/SSO sign-in could not be completed/i)).toBeInTheDocument()
  })

  it("steers an enforce-SSO 403 to the SSO message instead of a generic error", async () => {
    const user = userEvent.setup()
    const { ApiError } = await import("@/lib/api/client")
    mockApiFetch.mockRejectedValue(new ApiError(403, { detail: "x" }, "You do not have access to perform this action."))
    render(<SignInForm />)
    await user.type(screen.getByLabelText("Email"), "newhire@acme.com")
    await user.type(screen.getByLabelText("Password"), "hunter2")
    await user.click(screen.getByRole("button", { name: "Sign In" }))
    await waitFor(() => expect(screen.getByText(/Single sign-on is required for your organization/i)).toBeInTheDocument())
    expect(screen.queryByText(/do not have access/i)).not.toBeInTheDocument()
  })

  it("password sign-in still stores the session and routes to the dashboard", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValue({
      access_token: "pw-token",
      user: { id: 1, email: "a@b.com", is_admin: false, is_verified: true },
    })
    render(<SignInForm />)
    await user.type(screen.getByLabelText("Email"), "a@b.com")
    await user.type(screen.getByLabelText("Password"), "pw")
    await user.click(screen.getByRole("button", { name: "Sign In" }))
    await waitFor(() => expect(push).toHaveBeenCalledWith("/dashboard"))
    expect(window.localStorage.getItem("moltrace.access_token")).toBe("pw-token")
  })
})
