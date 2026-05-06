import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { AUTH_TOKEN_STORAGE_KEY, AUTH_USER_STORAGE_KEY } from "@/lib/api/client"
import { SignInForm } from "@/components/marketing/sign-in-form"
import { SignUpForm } from "@/components/marketing/sign-up-form"

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}))

afterEach(() => {
  vi.restoreAllMocks()
  mocks.push.mockReset()
  window.localStorage.clear()
})

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
    ...init,
  })
}

describe("landing page auth forms", () => {
  it("signs in from the landing page and stores admin access", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        access_token: "admin-token",
        token_type: "bearer",
        expires_at: "2026-05-02T18:00:00Z",
        user: {
          id: 1,
          email: "admin@example.com",
          is_admin: true,
          is_verified: true,
        },
        requires_email_verification: false,
        detail: "Signed in.",
      })
    )
    vi.stubGlobal("fetch", fetchMock)

    render(<SignInForm />)

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "admin@example.com" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "StrongPassword123!" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }))

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/dashboard"))

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe("/api/backend/auth/sign-in")
    expect(JSON.parse(String(init.body))).toEqual({
      email: "admin@example.com",
      password: "StrongPassword123!",
    })
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("admin-token")
    expect(JSON.parse(window.localStorage.getItem(AUTH_USER_STORAGE_KEY) || "{}")).toMatchObject({
      email: "admin@example.com",
      is_admin: true,
    })
    expect(screen.getByRole("status")).toHaveTextContent("Signed in with admin access.")
  })

  it("creates an account from the landing page and stores the session", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        {
          access_token: "new-user-token",
          token_type: "bearer",
          expires_at: "2026-05-02T18:00:00Z",
          user: {
            id: 2,
            email: "chemist@example.com",
            is_admin: false,
            is_verified: true,
          },
          requires_email_verification: false,
          detail: "Account created.",
        },
        { status: 201 }
      )
    )
    vi.stubGlobal("fetch", fetchMock)

    render(<SignUpForm />)

    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Ada Chemist" },
    })
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "chemist@example.com" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "StrongPassword123!" },
    })
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "StrongPassword123!" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create account" }))

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/dashboard"))

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe("/api/backend/auth/sign-up")
    expect(JSON.parse(String(init.body))).toEqual({
      name: "Ada Chemist",
      email: "chemist@example.com",
      password: "StrongPassword123!",
      passwordConfirm: "StrongPassword123!",
    })
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("new-user-token")
  })

  it("rejects mismatched sign-up passwords before calling the backend", async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    render(<SignUpForm />)

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "chemist@example.com" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "StrongPassword123!" },
    })
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "DifferentPassword123!" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Create account" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Password confirmation does not match password."
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
