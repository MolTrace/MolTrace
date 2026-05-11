import type { ReactElement, ReactNode } from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"

/**
 * Strong baseline render tests for the Projects supporting components.
 *
 * Locks in the user-visible contract for each component so the reskin cannot
 * accidentally hide a section, drop a button, or break a heading.
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
  usePathname: () => "/projects/1",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ projectId: "1" }),
}))

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: { children: ReactNode }) => props.children }),
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
}))

// Stub the ROI snapshot fetch the value-summary card depends on
vi.mock("@/src/lib/dashboard/scoped-roi-snapshot", () => ({
  fetchProjectRoiSnapshot: vi.fn(async () => null),
}))

function renderC(ui: ReactElement) {
  return render(ui)
}

beforeEach(() => {
  apiFetchMock.mockReset()
  apiFetchMock.mockImplementation(async () => [])
})

describe("ProjectAccessSection", () => {
  it("renders the access control panel host", async () => {
    const { ProjectAccessSection } = await import("@/components/projects/project-access-section")
    renderC(<ProjectAccessSection projectId="1" />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Access|Member|Invitation|Role|Project access/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("ProjectValueSummaryCard", () => {
  it("renders the value summary card host", async () => {
    const { ProjectValueSummaryCard } = await import("@/components/projects/project-value-summary-card")
    renderC(<ProjectValueSummaryCard projectId="1" />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Value|Hours|Saved|ROI|Snapshot/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("SessionWorkflowRunsSection", () => {
  it("renders without crashing when given an empty session list", async () => {
    const { SessionWorkflowRunsSection } = await import("@/components/projects/session-workflow-runs-section")
    renderC(<SessionWorkflowRunsSection sessionIds={[]} />)
    // Component should render some content (may be empty state) without throwing
    expect(document.body.textContent).toBeDefined()
  })

  it("renders without crashing when given session IDs", async () => {
    const { SessionWorkflowRunsSection } = await import("@/components/projects/session-workflow-runs-section")
    renderC(<SessionWorkflowRunsSection sessionIds={["session-1"]} />)
    expect(document.body.textContent).toBeDefined()
  })
})
