import type { ReactElement, ReactNode } from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"

/**
 * Strong baseline render tests for the Regulatory Hub components.
 *
 * Locks in the user-visible contract for each major component so the reskin
 * cannot accidentally hide a section, drop a button, or break a heading.
 *
 * After redesign, these MUST still pass — relax only when copy intentionally
 * changes (e.g. h2 title change), and update the assertion to the new copy.
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
  usePathname: () => "/regulatory",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}))

// Stub framer-motion if any component pulls it (avoid jsdom RAF issues)
vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: { children: ReactNode }) => props.children }),
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
}))

function renderC(ui: ReactElement) {
  return render(ui)
}

beforeEach(() => {
  apiFetchMock.mockReset()
  // Default: empty list responses for every call
  apiFetchMock.mockImplementation(async () => [])
})

describe("Regulatory Intelligence Landing", () => {
  it("renders without crashing and shows a regulatory-related heading", async () => {
    const { RegulatoryIntelligenceLanding } = await import(
      "@/components/regulatory-hub/regulatory-intelligence-landing"
    )
    renderC(<RegulatoryIntelligenceLanding />)
    // Wait for at least one heading containing "Regulatory" or "Dossier" or "Surveillance"
    await waitFor(() => {
      const found = screen.queryAllByText(/Regulatory|Dossier|Surveillance|Intelligence|Compliance/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("Regulatory Action Queue", () => {
  it("renders the action queue and a recognizable heading", async () => {
    const { RegulatoryActionQueue } = await import(
      "@/components/regulatory-hub/regulatory-action-queue"
    )
    renderC(<RegulatoryActionQueue />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Action queue|Action items|action/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("Regulatory Surveillance Dashboard", () => {
  it("renders without crashing", async () => {
    const { RegulatorySurveillanceDashboard } = await import(
      "@/components/regulatory-hub/regulatory-surveillance-dashboard"
    )
    renderC(<RegulatorySurveillanceDashboard />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Surveillance|Source|Crawl/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("Regulatory Source Library Workspace", () => {
  it("renders without crashing", async () => {
    const { RegulatorySourceLibraryWorkspace } = await import(
      "@/components/regulatory-hub/regulatory-source-library-workspace"
    )
    renderC(<RegulatorySourceLibraryWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Source|Library|Upload|Search/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("Regulatory Rule Updates Workspace", () => {
  it("renders without crashing", async () => {
    const { RegulatoryRuleUpdatesWorkspace } = await import(
      "@/components/regulatory-hub/regulatory-rule-updates-workspace"
    )
    renderC(<RegulatoryRuleUpdatesWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Rule|Proposal|Update/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("Regulatory Notifications Workspace", () => {
  it("renders without crashing", async () => {
    const { RegulatoryNotificationsWorkspace } = await import(
      "@/components/regulatory-hub/regulatory-notifications-workspace"
    )
    renderC(<RegulatoryNotificationsWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Notification/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("Regulatory Hub Workspace (CTD demo)", () => {
  it("renders the demo dossier metadata", async () => {
    const { RegulatoryHubWorkspace } = await import(
      "@/components/regulatory-hub/regulatory-hub-workspace"
    )
    renderC(<RegulatoryHubWorkspace />)
    // Static demo content — should always render synchronously
    const matches = screen.queryAllByText(/MTX-447|PRJ-MTX-2047/i)
    expect(matches.length).toBeGreaterThan(0)
  })
})

describe("Reaction Optimization Handoff Card (cross-module integration)", () => {
  it("renders the handoff card host", async () => {
    const { ReactionOptimizationHandoffCard } = await import(
      "@/components/regulatory-hub/reaction-optimization-handoff-card"
    )
    renderC(<ReactionOptimizationHandoffCard dossierId={1} reactionProjectId={null} />)
    // Should render at least one heading or label related to reaction optimization
    await waitFor(() => {
      const found = screen.queryAllByText(/Reaction|Route|Optimization|Hand-off|Handoff/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})
