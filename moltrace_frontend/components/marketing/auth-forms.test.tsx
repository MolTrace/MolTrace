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
          email: "user@example.com",
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
      target: { value: "user@example.com" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "StrongPassword123!" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }))

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/dashboard"))

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe("/api/backend/auth/sign-in")
    expect(JSON.parse(String(init.body))).toEqual({
      email: "user@example.com",
      password: "StrongPassword123!",
    })
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe("admin-token")
    expect(JSON.parse(window.localStorage.getItem(AUTH_USER_STORAGE_KEY) || "{}")).toMatchObject({
      email: "user@example.com",
      is_admin: true,
    })
    expect(screen.getByRole("status")).toHaveTextContent("Signed in with admin access.")
  })

  it("shows a credential-focused message when sign-in fails", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(
        { detail: "Sign in to access live MolTrace data." },
        { status: 401, statusText: "Unauthorized" }
      )
    )
    vi.stubGlobal("fetch", fetchMock)

    render(<SignInForm />)

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "chemist@example.com" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "WrongPassword123!" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We couldn't sign you in. Check your email and password, then try again."
    )
    expect(mocks.push).not.toHaveBeenCalled()
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

describe("password show/hide toggle", () => {
  it("toggles the sign-in password field between masked and visible", () => {
    render(<SignInForm />)

    const password = screen.getByLabelText("Password")
    // Masked by default — the toggle advertises the action it will perform.
    expect(password).toHaveAttribute("type", "password")
    const toggle = screen.getByRole("button", { name: "Show password" })
    expect(toggle).toHaveAttribute("type", "button")
    expect(toggle).toHaveAttribute("aria-pressed", "false")

    // Reveal.
    fireEvent.click(toggle)
    expect(password).toHaveAttribute("type", "text")
    const hideToggle = screen.getByRole("button", { name: "Hide password" })
    expect(hideToggle).toHaveAttribute("aria-pressed", "true")

    // Hide again — round-trips to the original state.
    fireEvent.click(hideToggle)
    expect(password).toHaveAttribute("type", "password")
    expect(screen.getByRole("button", { name: "Show password" })).toHaveAttribute(
      "aria-pressed",
      "false"
    )
  })

  it("does not submit the form when the toggle is clicked", () => {
    const fetchMock = vi.fn()
    vi.stubGlobal("fetch", fetchMock)

    render(<SignInForm />)
    fireEvent.click(screen.getByRole("button", { name: "Show password" }))

    // type="button" must keep the toggle from submitting the surrounding form.
    expect(fetchMock).not.toHaveBeenCalled()
    expect(mocks.push).not.toHaveBeenCalled()
  })

  it("toggles the two sign-up password fields independently", () => {
    render(<SignUpForm />)

    const password = screen.getByLabelText("Password")
    const confirm = screen.getByLabelText("Confirm password")
    expect(password).toHaveAttribute("type", "password")
    expect(confirm).toHaveAttribute("type", "password")

    // Two toggles, in DOM order: [0] = password, [1] = confirm.
    const toggles = screen.getAllByRole("button", { name: "Show password" })
    expect(toggles).toHaveLength(2)

    // Reveal only the first; the confirm field must stay masked.
    fireEvent.click(toggles[0])
    expect(password).toHaveAttribute("type", "text")
    expect(confirm).toHaveAttribute("type", "password")
    // Exactly one field is now revealed.
    expect(screen.getAllByRole("button", { name: "Show password" })).toHaveLength(1)
    expect(screen.getAllByRole("button", { name: "Hide password" })).toHaveLength(1)
  })
})
