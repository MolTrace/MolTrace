import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { SSOConnectionsWorkspace } from "@/components/admin/sso-connections-workspace"
import type { components } from "@/src/lib/api/schema"

const mockApiFetch = vi.hoisted(() => vi.fn<(path: string, init?: unknown) => Promise<unknown>>())

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

type SSOConnection = components["schemas"]["SSOConnectionOut"]

const CONN: SSOConnection = {
  id: 5,
  organization_id: 12,
  slug: "acme",
  display_name: "Acme Okta",
  protocol: "oidc",
  issuer: "https://acme.okta.com",
  client_id: "0oaCID",
  email_domains: ["acme.com"],
  enabled: true,
  enforce_sso: false,
  created_at: "2026-06-12T00:00:00Z",
  updated_at: "2026-06-12T00:00:00Z",
}

/** GET list returns `rows`; any mutation resolves `{}`. */
function withList(rows: SSOConnection[]) {
  mockApiFetch.mockImplementation((path: string, init?: unknown) => {
    const method = (init as { method?: string } | undefined)?.method ?? "GET"
    if (path === "/auth/sso/connections" && method === "GET") {
      return Promise.resolve({ connections: rows })
    }
    return Promise.resolve({})
  })
}

function lastCall(predicate: (path: string, init: { method?: string; body?: Record<string, unknown> }) => boolean) {
  const calls = mockApiFetch.mock.calls as Array<[string, { method?: string; body?: Record<string, unknown> }]>
  return [...calls].reverse().find(([p, i]) => predicate(p, i ?? {}))
}

describe("SSOConnectionsWorkspace", () => {
  beforeEach(() => mockApiFetch.mockReset())

  it("lists connections and never surfaces a client secret value", async () => {
    withList([CONN])
    render(<SSOConnectionsWorkspace />)
    await waitFor(() => expect(screen.getByText("Acme Okta")).toBeInTheDocument())
    const row = screen.getByTestId("sso-row-5")
    expect(within(row).getByText("acme")).toBeInTheDocument()
    expect(within(row).getByText("enabled")).toBeInTheDocument()
    // create form's secret field is empty (write-only; API never returns a secret)
    expect((screen.getByLabelText(/Client secret/) as HTMLInputElement).value).toBe("")
  })

  it("creates a connection with the correct POST body", async () => {
    const user = userEvent.setup()
    withList([])
    render(<SSOConnectionsWorkspace />)
    await waitFor(() => expect(screen.getByText(/No SSO connections yet/)).toBeInTheDocument())

    await user.type(screen.getByLabelText("Organization ID"), "12")
    await user.type(screen.getByLabelText("Slug"), "acme")
    await user.type(screen.getByLabelText("Display name"), "Acme Okta")
    await user.type(screen.getByLabelText("Issuer"), "https://acme.okta.com")
    await user.type(screen.getByLabelText("Client ID"), "0oaCID")
    await user.type(screen.getByLabelText(/Client secret/), "super-secret")
    await user.type(screen.getByLabelText("Email domains"), "acme.com")
    await user.click(screen.getByRole("button", { name: "Create connection" }))

    await waitFor(() => {
      const post = lastCall((p, i) => p === "/auth/sso/connections" && i.method === "POST")
      expect(post).toBeTruthy()
      expect(post![1].body).toMatchObject({
        organization_id: 12,
        slug: "acme",
        display_name: "Acme Okta",
        issuer: "https://acme.okta.com",
        client_id: "0oaCID",
        client_secret: "super-secret",
        email_domains: ["acme.com"],
        enabled: true,
        enforce_sso: false,
      })
    })
  })

  it("blocks a create with an invalid slug (no POST)", async () => {
    const user = userEvent.setup()
    withList([])
    render(<SSOConnectionsWorkspace />)
    await waitFor(() => expect(screen.getByText(/No SSO connections yet/)).toBeInTheDocument())

    await user.type(screen.getByLabelText("Organization ID"), "12")
    await user.type(screen.getByLabelText("Slug"), "Acme_Corp") // invalid: uppercase + underscore
    await user.type(screen.getByLabelText("Display name"), "Acme")
    await user.type(screen.getByLabelText("Issuer"), "https://acme.okta.com")
    await user.type(screen.getByLabelText("Client ID"), "cid")
    await user.type(screen.getByLabelText(/Client secret/), "s")
    await user.click(screen.getByRole("button", { name: "Create connection" }))

    expect(screen.getByText(/Slug must be lowercase/)).toBeInTheDocument()
    expect(lastCall((p, i) => p === "/auth/sso/connections" && i.method === "POST")).toBeUndefined()
  })

  it("edit omits a blank client_secret from the PATCH (keeps the stored secret)", async () => {
    const user = userEvent.setup()
    withList([CONN])
    render(<SSOConnectionsWorkspace />)
    await waitFor(() => expect(screen.getByText("Acme Okta")).toBeInTheDocument())

    await user.click(screen.getByRole("button", { name: "Edit acme" }))
    const display = screen.getByLabelText("Display name")
    await user.clear(display)
    await user.type(display, "Acme Renamed")
    await user.click(screen.getByRole("button", { name: "Save changes" }))

    await waitFor(() => {
      const patch = lastCall((p, i) => p === "/auth/sso/connections/5" && i.method === "PATCH")
      expect(patch).toBeTruthy()
      expect("client_secret" in (patch![1].body ?? {})).toBe(false)
      expect(patch![1].body).toMatchObject({ display_name: "Acme Renamed" })
    })
  })

  it("warns that password login will be blocked when enforce-SSO is toggled on", async () => {
    const user = userEvent.setup()
    withList([])
    render(<SSOConnectionsWorkspace />)
    await waitFor(() => expect(screen.getByText(/No SSO connections yet/)).toBeInTheDocument())

    await user.type(screen.getByLabelText("Email domains"), "acme.com")
    await user.click(screen.getByRole("switch", { name: /Enforce SSO/ }))
    expect(screen.getByText(/Password login will be blocked/)).toBeInTheDocument()
    expect(screen.getByText(/acme\.com must sign in through the identity provider/)).toBeInTheDocument()
  })

  it("deletes a connection after confirmation", async () => {
    const user = userEvent.setup()
    vi.spyOn(window, "confirm").mockReturnValue(true)
    withList([CONN])
    render(<SSOConnectionsWorkspace />)
    await waitFor(() => expect(screen.getByText("Acme Okta")).toBeInTheDocument())

    await user.click(screen.getByRole("button", { name: "Delete acme" }))
    await waitFor(() => {
      const del = lastCall((p, i) => p === "/auth/sso/connections/5" && i.method === "DELETE")
      expect(del).toBeTruthy()
    })
  })
})
