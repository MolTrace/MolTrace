import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DashboardV0 } from "@/components/dashboard/dashboard-v0"

const mockApiFetch = vi.fn<(path: string) => Promise<unknown>>()

/** Which products the deployment serves; every test starts with all three. */
let includedModules = new Set(["spectracheck", "regulatory_hub", "reaction_optimization"])
vi.mock("@/src/lib/modules/included-modules-provider", () => ({
  useIncludedModules: () => ({
    isIncluded: (key: string) => includedModules.has(key),
    displayNames: {
      spectracheck: "SpectraCheck",
      regulatory_hub: "Regentry",
      reaction_optimization: "Repho",
    },
  }),
}))

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
    includedModules = new Set(["spectracheck", "regulatory_hub", "reaction_optimization"])
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

  // ---------------------------------------------------------------------
  // No invented numbers. Every mock in this file resolves to
  // `available: false` / `metrics: null`, so this whole describe block runs in
  // exactly the state a first-login GxP buyer hits when the backend is not
  // reachable yet. The dashboard used to fill that state with plausible
  // fiction -- 23 active analyses, 7 in review, 94.2 % model confidence, and
  // five activity rows reviewed by "Dr. Chen" -- which is indistinguishable
  // from real data on the screen where trust is established.
  // ---------------------------------------------------------------------

  it("shows no fabricated KPI numbers when live data is unavailable", async () => {
    render(<DashboardV0 />)

    // Let the mocked fetches settle first, like every other test here. Without
    // it the assertions race a dozen in-flight promises and the teardown waits
    // on them.
    await waitFor(() => {
      expect(screen.getByText("Active Analyses")).toBeInTheDocument()
    })
    for (const invented of ["23", "7", "12", "156", "94.2%"]) {
      expect(
        screen.queryByText(invented, { selector: "div.font-mono" }),
        `the dashboard rendered ${invented} with no live data behind it`,
      ).not.toBeInTheDocument()
    }
  })

  it("invents no reviewers, samples or analysis ids", async () => {
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByText("Active Analyses")).toBeInTheDocument()
    })
    for (const invented of [
      "Dr. Chen",
      "Dr. Patel",
      "Dr. Kim",
      "API-Q4-BATCH-12",
      "MET-STUDY-089",
      "NMR-2024-0847",
    ]) {
      expect(
        screen.queryByText(invented),
        `the dashboard invented ${invented}`,
      ).not.toBeInTheDocument()
    }
  })

  it("never reports a green system state it cannot observe", async () => {
    /* The worst of the fabrications, and a different kind from the counts: a
       made-up "23" is wrong, but a made-up "healthy" is wrong in the
       reassuring direction, on the signal a reviewer would act on. */
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByText("Active Analyses")).toBeInTheDocument()
    })
    /* A filter chip may legitimately be labelled "Succeeded" -- it names a
       choice, not a state of the system. What must not appear is a *status
       display* asserting green, so allow matches inside an interactive control
       and forbid them anywhere else. */
    for (const el of screen.queryAllByText(/^(healthy|succeeded)$/i)) {
      expect(
        el.closest("button"),
        `"${el.textContent}" is rendered as a status, not a filter control`,
      ).not.toBeNull()
    }
  })

  it("says the number is unavailable rather than omitting the tile", async () => {
    /* Hiding the tile would be its own dishonesty -- the reader cannot tell a
       metric that is zero from one that could not be loaded. The card stays,
       the number becomes an explicit dash. */
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByText("Active Analyses")).toBeInTheDocument()
    })
    expect(screen.getAllByText("—", { selector: "div.font-mono" }).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/not available|unavailable|couldn't load/i).length).toBeGreaterThan(0)
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

  // ── What a single-product deployment sees ──────────────────────────────────────────────────
  // The dashboard is the one page that reaches into all three products, so it is where an absent
  // module shows up worst: a section that opens onto nothing, and a panel of "—".

  it("drops the Regulatory section entirely when the workspace has no Regentry", async () => {
    includedModules = new Set(["spectracheck"])
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByText("Active Analyses")).toBeInTheDocument()
    })
    expect(
      screen.queryByRole("button", { name: /Collapse Regulatory section/i }),
    ).not.toBeInTheDocument()
    expect(screen.queryByText("Regulatory compliance")).not.toBeInTheDocument()
    expect(screen.queryByText("Regulatory Surveillance")).not.toBeInTheDocument()
    // The sections it DOES own are untouched.
    expect(
      screen.getByRole("button", { name: /Collapse Operations section/i }),
    ).toBeInTheDocument()
  })

  it("hides the cross-module panel when there is only one product to cross", async () => {
    includedModules = new Set(["spectracheck"])
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByText("Active Analyses")).toBeInTheDocument()
    })
    expect(screen.queryByText("Cross-Module Command Center")).not.toBeInTheDocument()
    expect(screen.queryByText("Core module activity")).not.toBeInTheDocument()
    // The tiles that would have read "—" are gone with it.
    expect(screen.queryByText("linked regulatory action items")).not.toBeInTheDocument()
    expect(screen.queryByText("reaction constraints created")).not.toBeInTheDocument()
  })

  it("gives a reaction-only workspace a section about its own product", async () => {
    includedModules = new Set(["reaction_optimization"])
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Collapse Reactions section/i })).toBeInTheDocument()
    })
    // DashboardSection renders its description more than once, so assert at-least-one.
    expect(screen.getAllByText("Reaction optimization projects in flight.").length).toBeGreaterThan(0)
    // ...and nothing about the products it doesn't have.
    expect(screen.queryByRole("button", { name: /Collapse Regulatory section/i })).not.toBeInTheDocument()
    expect(screen.queryByText("Cross-Module Command Center")).not.toBeInTheDocument()
  })

  it("hides the Reactions section when the workspace has no Repho", async () => {
    includedModules = new Set(["spectracheck", "regulatory_hub"])
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByText("Active Analyses")).toBeInTheDocument()
    })
    expect(screen.queryByRole("button", { name: /Collapse Reactions section/i })).not.toBeInTheDocument()
  })

  it("renumbers the section eyebrows to match what is actually rendered", async () => {
    // With Regentry absent the old hardcoded eyebrows read "01, 02, 04, 05" — a gap where a
    // section the customer never bought used to be.
    includedModules = new Set(["spectracheck"])
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByText("01 · Dashboard")).toBeInTheDocument()
    })
    expect(screen.getByText("02 · Spectroscopy")).toBeInTheDocument()
    expect(screen.getByText("03 · Operations")).toBeInTheDocument()
    expect(screen.getByText("04 · Activity")).toBeInTheDocument()
    expect(screen.queryByText("05 · Activity")).not.toBeInTheDocument()
    expect(screen.queryByText(/· Regulatory/)).not.toBeInTheDocument()
    expect(screen.queryByText(/· Reactions/)).not.toBeInTheDocument()
  })

  it("numbers all six sections in order when the workspace has every product", async () => {
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByText("01 · Dashboard")).toBeInTheDocument()
    })
    expect(screen.getByText("02 · Spectroscopy")).toBeInTheDocument()
    expect(screen.getByText("03 · Regulatory")).toBeInTheDocument()
    expect(screen.getByText("04 · Reactions")).toBeInTheDocument()
    expect(screen.getByText("05 · Operations")).toBeInTheDocument()
    expect(screen.getByText("06 · Activity")).toBeInTheDocument()
  })

  it("keeps the cross-module panel for two products, showing only their tiles and their counts", async () => {
    includedModules = new Set(["spectracheck", "regulatory_hub"])
    render(<DashboardV0 />)

    await waitFor(() => {
      expect(screen.getByText("Cross-Module Command Center")).toBeInTheDocument()
    })
    expect(screen.getByText("linked regulatory action items")).toBeInTheDocument()
    // Repho's tile — and Repho's share of the activity count — are excluded, so the badge reads
    // 3 (2 SpectraCheck + 1 Regentry) rather than the server's all-products total of 5.
    expect(screen.queryByText("reaction constraints created")).not.toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText("3 opens")).toBeInTheDocument()
    })
    expect(screen.queryByText("5 opens")).not.toBeInTheDocument()
    // And the copy names only what this workspace has. (The description is assembled from two
    // nodes, so match on the element's own combined text.)
    expect(
      screen.getByText((_t, el) => el?.textContent?.startsWith("How SpectraCheck and Regentry connect.") === true, {
        selector: "div,p",
      }),
    ).toBeInTheDocument()
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
