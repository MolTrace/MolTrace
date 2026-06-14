import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ScimProvisioningSection } from "@/components/admin/scim-provisioning-section"

const mockApiFetch = vi.hoisted(() => vi.fn<(path: string, init?: unknown) => Promise<unknown>>())

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

const INFO = {
  connection_id: 5,
  token_prefix: "scim_AbC",
  created_at: "2026-06-14T00:00:00Z",
  last_used_at: null,
  expires_at: null,
}
const ISSUED = {
  token: "scim_AbCsecretplaintext999",
  token_prefix: "scim_AbC",
  connection_id: 5,
  created_at: "2026-06-14T00:00:00Z",
  expires_at: null,
}

const methodOf = (i?: unknown) => (i as { method?: string } | undefined)?.method ?? "GET"

describe("ScimProvisioningSection", () => {
  beforeEach(() => mockApiFetch.mockReset())

  it("gates the section when the connection is disabled (no fetch)", () => {
    render(<ScimProvisioningSection connectionId={5} enabled={false} />)
    expect(screen.getByText(/SCIM provisioning is disabled/i)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Generate SCIM token/i })).not.toBeInTheDocument()
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  it("shows Generate when no token, then reveals the plaintext exactly once on issue", async () => {
    const user = userEvent.setup()
    const { ApiError } = await import("@/lib/api/client")
    let hasToken = false
    mockApiFetch.mockImplementation(async (_p, i) => {
      const m = methodOf(i)
      if (m === "GET") {
        if (hasToken) return INFO
        throw new ApiError(404, { detail: "no token" }, "Not found")
      }
      if (m === "POST") {
        hasToken = true
        return ISSUED
      }
      return {}
    })

    render(<ScimProvisioningSection connectionId={5} enabled />)
    await waitFor(() => expect(screen.getByRole("button", { name: /Generate SCIM token/i })).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: /Generate SCIM token/i }))

    await waitFor(() => expect(screen.getByText("scim_AbCsecretplaintext999")).toBeInTheDocument())
    expect(screen.getByText(/won't be shown again/i)).toBeInTheDocument()
    // POST hit the right endpoint; the live status now reflects an active token
    expect(mockApiFetch).toHaveBeenCalledWith("/auth/sso/connections/5/scim-token", expect.objectContaining({ method: "POST" }))
    expect(screen.getByText("token active")).toBeInTheDocument()
  })

  it("renders a live token's prefix + status without leaking the plaintext, with rotate/revoke", async () => {
    mockApiFetch.mockImplementation(async (_p, i) => {
      if (methodOf(i) === "GET") return INFO
      return {}
    })
    render(<ScimProvisioningSection connectionId={5} enabled />)
    await waitFor(() => expect(screen.getByText("token active")).toBeInTheDocument())
    expect(screen.getByText(/scim_AbC/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Rotate" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Revoke" })).toBeInTheDocument()
    // GET (ScimTokenInfo) carries no plaintext — nothing secret rendered
    expect(screen.queryByText(/secretplaintext/)).not.toBeInTheDocument()
  })

  it("revokes via DELETE after confirmation", async () => {
    const user = userEvent.setup()
    vi.spyOn(window, "confirm").mockReturnValue(true)
    mockApiFetch.mockImplementation(async (_p, i) => {
      if (methodOf(i) === "DELETE") return { detail: "revoked" }
      return INFO // GET — live token present (reload after delete is a no-op for this assertion)
    })
    render(<ScimProvisioningSection connectionId={5} enabled />)
    await waitFor(() => expect(screen.getByRole("button", { name: "Revoke" })).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: "Revoke" }))
    await waitFor(() =>
      expect(
        mockApiFetch.mock.calls.some(([p, i]) => p === "/auth/sso/connections/5/scim-token" && methodOf(i) === "DELETE"),
      ).toBe(true),
    )
    expect(window.confirm).toHaveBeenCalled()
  })

  it("treats a DELETE 404 as already-revoked (no error; refreshes to the no-token state)", async () => {
    const user = userEvent.setup()
    const { ApiError } = await import("@/lib/api/client")
    vi.spyOn(window, "confirm").mockReturnValue(true)
    mockApiFetch.mockImplementation(async (_p, i) => {
      // DELETE 404 = token already gone (concurrent revoke). GET returns the live
      // token at mount; revoke clears it client-side without a reload.
      if (methodOf(i) === "DELETE") throw new ApiError(404, { detail: "no live token" }, "Not found")
      return INFO
    })
    render(<ScimProvisioningSection connectionId={5} enabled />)
    await waitFor(() => expect(screen.getByRole("button", { name: "Revoke" })).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: "Revoke" }))
    // already gone → no error, and the card refreshes to the "Generate" (no-token) state
    await waitFor(() => expect(screen.getByRole("button", { name: /Generate SCIM token/i })).toBeInTheDocument())
    expect(screen.queryByText(/Could not revoke/i)).not.toBeInTheDocument()
    expect(screen.queryByText("token active")).not.toBeInTheDocument()
  })

  it("surfaces the 409 'just issued; retry' conflict on rotate", async () => {
    const user = userEvent.setup()
    const { ApiError } = await import("@/lib/api/client")
    mockApiFetch.mockImplementation(async (_p, i) => {
      const m = methodOf(i)
      if (m === "GET") return INFO
      if (m === "POST") {
        throw new ApiError(
          409,
          { detail: "A SCIM token was just issued for this connection; retry." },
          "A SCIM token was just issued for this connection; retry.",
        )
      }
      return {}
    })
    render(<ScimProvisioningSection connectionId={5} enabled />)
    await waitFor(() => expect(screen.getByRole("button", { name: "Rotate" })).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: "Rotate" }))
    await waitFor(() => expect(screen.getByText(/just issued for this connection; retry/i)).toBeInTheDocument())
  })
})
