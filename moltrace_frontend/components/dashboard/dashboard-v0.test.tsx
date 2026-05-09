import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DashboardV0 } from "@/components/dashboard/dashboard-v0"

const mockApiFetch = vi.fn<(path: string) => Promise<unknown>>()

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
  })

  it("shows subtle summary unavailable message and keeps dashboard content", async () => {
    const user = userEvent.setup()
    render(<DashboardV0 />)

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument()
    expect(screen.getByText("Active Analyses")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /Expand Operations section/i }))

    await waitFor(() => {
      expect(screen.getByText("Connector and ingestion summary")).toBeInTheDocument()
      expect(
        screen.getByText("Connector and ingestion summary unavailable for now.")
      ).toBeInTheDocument()
    })
  })
})
