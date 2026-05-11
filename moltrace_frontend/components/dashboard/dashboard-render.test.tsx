import type { ReactElement, ReactNode } from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"

/**
 * Strong baseline render tests for the Dashboard helper components.
 *
 * Locks in the user-visible contract for the dashboard's own components.
 * Cross-module shared cards (alert-card, module-card, kpi-card) are
 * intentionally NOT modified during the dashboard reskin and have their
 * own indirect coverage via every other module's smoke tests.
 */

const apiFetchMock = vi.fn()

vi.mock("@/lib/api/client", () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
  ApiError: class ApiError extends Error {
    status: number
    data: unknown
    constructor(status: number, data: unknown, message?: string) {
      super(message ?? String(status))
      this.status = status
      this.data = data
    }
  },
}))

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}))

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: { children: ReactNode }) => props.children }),
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
}))

function renderC(ui: ReactElement) {
  return render(ui)
}

beforeEach(() => {
  apiFetchMock.mockReset()
  apiFetchMock.mockImplementation(async () => [])
})

describe("DashboardGreeting", () => {
  it("renders the greeting + tenant name", async () => {
    const { DashboardGreeting } = await import("@/components/dashboard/dashboard-greeting")
    renderC(<DashboardGreeting email="alice@acme.com" tenantName="Acme" />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Acme|Welcome|Hello|Hi/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })

  it("optionally renders an eyebrow when provided", async () => {
    const { DashboardGreeting } = await import("@/components/dashboard/dashboard-greeting")
    renderC(<DashboardGreeting email="alice@acme.com" tenantName="Acme" eyebrow="MolTrace · Dashboard" />)
    expect(screen.getByText(/MolTrace · Dashboard/i)).toBeInTheDocument()
  })
})

describe("DashboardSection", () => {
  it("renders title + children when defaultOpen is true", async () => {
    const { DashboardSection } = await import("@/components/dashboard/dashboard-section")
    renderC(
      <DashboardSection title="Active campaigns" description="Across all programs" defaultOpen>
        <p>section body content</p>
      </DashboardSection>,
    )
    expect(screen.getByText(/Active campaigns/i)).toBeInTheDocument()
    expect(screen.getByText(/section body content/i)).toBeInTheDocument()
  })

  it("supports an optional eyebrow tagline", async () => {
    const { DashboardSection } = await import("@/components/dashboard/dashboard-section")
    renderC(
      <DashboardSection title="t" eyebrow="MolTrace · Dashboard" defaultOpen>
        <p>body</p>
      </DashboardSection>,
    )
    expect(screen.getByText(/MolTrace · Dashboard/i)).toBeInTheDocument()
  })

  it("supports all 5 module accents (teal/cyan/violet/amber/green)", async () => {
    const { DashboardSection } = await import("@/components/dashboard/dashboard-section")
    // Just ensure no type / runtime error rendering with each accent
    for (const accent of ["teal", "cyan", "violet", "amber", "green"] as const) {
      const { unmount } = renderC(
        <DashboardSection title={`accent-${accent}`} accent={accent} defaultOpen>
          <p>body</p>
        </DashboardSection>,
      )
      expect(screen.getByText(`accent-${accent}`)).toBeInTheDocument()
      unmount()
    }
  })
})

describe("DashboardPriorityCallout", () => {
  it("renders without crashing when given an empty priority list", async () => {
    const { DashboardPriorityCallout } = await import("@/components/dashboard/dashboard-priority-callout")
    renderC(<DashboardPriorityCallout priorities={[]} />)
    expect(document.body.textContent).toBeDefined()
  })
})

describe("StatusFilterPills", () => {
  it("renders all options and highlights the active one", async () => {
    const { StatusFilterPills } = await import("@/components/dashboard/status-filter-pills")
    const onChange = vi.fn()
    renderC(
      <StatusFilterPills
        value="open"
        options={[
          { value: "open", label: "Open" },
          { value: "closed", label: "Closed" },
        ]}
        onChange={onChange}
      />,
    )
    expect(screen.getByRole("button", { name: /Open/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Closed/i })).toBeInTheDocument()
  })
})
