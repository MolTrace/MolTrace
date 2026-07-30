import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DashboardV0 } from "@/components/dashboard/dashboard-v0"

const mockApiFetch = vi.fn<(path: string) => Promise<unknown>>()

function installDesktopMode() {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 500 })
  Object.defineProperty(window.navigator, "platform", { configurable: true, value: "Win32" })
  Object.defineProperty(window.navigator, "userAgent", {
    configurable: true,
    value: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
  })
  Object.defineProperty(window.navigator, "maxTouchPoints", { configurable: true, value: 0 })
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn((query: string) => ({
      matches: query.includes("max-width"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

vi.mock("next/link", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock("@/components/app/backend-status-indicator", () => ({
  BackendStatusIndicator: () => <span>Backend status</span>,
}))

vi.mock("@/src/components/mobile/MobileCommandCenter", () => ({
  MobileCommandCenter: () => <div>Mobile Command Center</div>,
}))

vi.mock("@/components/regulatory-hub/regulatory-notifications-compact-card", () => ({
  RegulatoryNotificationsCompactCard: () => <div>Regulatory Notifications</div>,
}))

vi.mock("@/components/app/overview-data-context", () => ({
  useOverviewData: () => ({
    loading: false,
    metrics: null,
    recentActivityMerged: [],
    sessionsDataAvailable: false,
    recentActivity: [],
    jobsDataAvailable: false,
    recentJobs: [],
    workflowRunsDataAvailable: false,
    workflowStatusSummary: null,
    sessions: [],
  }),
}))

vi.mock("@/src/lib/dashboard/dashboard-qc-alerts", () => ({
  fetchDashboardQcAlertsAggregate: vi.fn(async () => ({ available: false })),
}))
vi.mock("@/src/lib/dashboard/dashboard-collaboration-aggregate", () => ({
  fetchDashboardCollaborationAggregate: vi.fn(async () => ({ available: false })),
}))
vi.mock("@/src/lib/dashboard/dashboard-method-health", () => ({
  fetchDashboardMethodHealthAggregate: vi.fn(async () => ({ available: false })),
}))
vi.mock("@/src/lib/dashboard/dashboard-operations-summary", () => ({
  fetchDashboardOperationsSummary: vi.fn(async () => ({ available: false })),
}))
vi.mock("@/src/lib/dashboard/dashboard-regulatory-summary", () => ({
  fetchDashboardRegulatorySummary: vi.fn(async () => ({ available: false })),
}))
vi.mock("@/src/lib/dashboard/dashboard-regulatory-compliance-card", () => ({
  fetchRegulatoryComplianceCardData: vi.fn(async () => ({ available: false })),
}))
vi.mock("@/src/lib/dashboard/dashboard-regulatory-surveillance-summary", () => ({
  fetchDashboardRegulatorySurveillanceSummary: vi.fn(async () => ({ available: false })),
}))
vi.mock("@/src/lib/dashboard/dashboard-compound-registry-summary", () => ({
  fetchDashboardCompoundRegistrySummary: vi.fn(async () => ({ available: false })),
}))
vi.mock("@/src/lib/dashboard/dashboard-roi-snapshot", () => ({
  fetchDashboardRoiSnapshot: vi.fn(async () => null),
}))
vi.mock("@/src/lib/dashboard/dashboard-ml-factory-health", () => ({
  fetchDashboardMlFactoryRollup: vi.fn(async () => ({ available: false })),
}))
vi.mock("@/src/lib/dashboard/dashboard-ai-inference-summary", () => ({
  fetchDashboardAiInferenceSummary: vi.fn(async () => ({ available: false })),
}))
vi.mock("@/src/lib/dashboard/dashboard-cross-module-command-center", () => ({
  fetchDashboardCrossModuleCommandCenter: vi.fn(async () => ({ available: false, warnings: [], sourceEndpoint: "" })),
}))
vi.mock("@/src/lib/dashboard/dashboard-core-module-activity", () => ({
  fetchDashboardCoreModuleActivity: vi.fn(async () => ({
    available: true,
    total: 5,
    warnings: [],
    rows: [
      {
        module: "spectracheck",
        label: "SpectraCheck",
        count: 2,
        latestAt: "2026-05-20T12:00:00Z",
      },
      {
        module: "regulatory_hub",
        label: "Regentry",
        count: 1,
        latestAt: "2026-05-20T12:05:00Z",
      },
      {
        module: "reactioniq",
        label: "Repho",
        count: 2,
        latestAt: "2026-05-20T12:10:00Z",
      },
    ],
  })),
}))

vi.mock("@/lib/api/client", () => ({
  AUTH_USER_STORAGE_KEY: "moltrace-auth-user",
  ApiError: class MockApiError extends Error {
    data?: unknown
    constructor(message: string, data?: unknown) {
      super(message)
      this.data = data
    }
  },
  apiFetch: (path: string) => mockApiFetch(path),
}))

describe("DashboardV0 connector/ingestion fallback", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
    mockApiFetch.mockRejectedValue(new Error("backend unavailable"))
    installDesktopMode()
    window.localStorage.clear()
  })

  it("shows subtle summary unavailable message and keeps dashboard content", async () => {
    render(<DashboardV0 />)

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument()
    expect(screen.getByText("Active Analyses")).toBeInTheDocument()

    // Operations opens by default now — no expand click needed.
    await waitFor(() => {
      expect(screen.getByText("Connector and ingestion summary")).toBeInTheDocument()
      expect(
        screen.getByText("Live connector and ingestion data isn't available right now.")
      ).toBeInTheDocument()
    })
  })

  it("does not render the mobile command center in desktop mode", () => {
    render(<DashboardV0 />)

    expect(screen.queryByText("Mobile Command Center")).not.toBeInTheDocument()
  })

  it("opens every section by default so each area shows its content", () => {
    render(<DashboardV0 />)

    for (const section of ["Overview", "Science", "Regulatory", "Operations", "Recent Activity"]) {
      expect(
        screen.getByRole("button", { name: new RegExp(`Collapse ${section} section`, "i") }),
      ).toBeInTheDocument()
    }
  })

  it("keeps section cards visible with placeholder values when live data is unavailable", async () => {
    render(<DashboardV0 />)

    await waitFor(() => {
      // Science cards render even though every fetch failed.
      expect(screen.getByText("ML factory health")).toBeInTheDocument()
      expect(screen.getByText("AI inference summary")).toBeInTheDocument()
      expect(screen.getByText("Compound Registry")).toBeInTheDocument()
      // Regulatory cards likewise. ("Regentry" also names a core-module-activity
      // row, so assert at-least-one rather than exactly-one.)
      expect(screen.getAllByText("Regentry").length).toBeGreaterThan(0)
      expect(screen.getByText("Regulatory compliance")).toBeInTheDocument()
      expect(screen.getByText("Regulatory Surveillance")).toBeInTheDocument()
      expect(
        screen.getByText("Live regulatory surveillance data isn't available right now."),
      ).toBeInTheDocument()
    })
  })

  it("surfaces testing-phase core module activity in the cross-module command center", async () => {
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByText("Core module activity")).toBeInTheDocument()
      expect(screen.getAllByText("SpectraCheck").length).toBeGreaterThan(0)
      expect(screen.getAllByText("Regentry").length).toBeGreaterThan(0)
      expect(screen.getAllByText("Repho").length).toBeGreaterThan(0)
      expect(screen.getByText("5 opens")).toBeInTheDocument()
    })
  })

  it("collapses and expands all sections with the header controls", async () => {
    const user = userEvent.setup()
    render(<DashboardV0 />)

    await user.click(screen.getByRole("button", { name: /^Collapse all$/i }))
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Expand Operations section/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole("button", { name: /^Expand all$/i }))
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Collapse Operations section/i })).toBeInTheDocument()
    })
  })

  it("remembers a collapsed section across a remount", async () => {
    const user = userEvent.setup()
    const { unmount } = render(<DashboardV0 />)

    await user.click(screen.getByRole("button", { name: /Collapse Science section/i }))
    unmount()

    render(<DashboardV0 />)
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Expand Science section/i })).toBeInTheDocument()
    })
  })
})
