import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { MobileBottomNav } from "@/src/components/app-shell/MobileBottomNav"
import MobilePage from "@/app/mobile/page"
import { MobileCommandCenter } from "@/src/components/mobile/MobileCommandCenter"
import { MobileRegulatoryQueue } from "@/src/components/mobile/MobileRegulatoryQueue"

let mockPathname = "/dashboard"
const mockSearchParams = new URLSearchParams("sessionId=s-1&reactionProjectId=rp-1&reportId=r-1")
const mockApiFetch = vi.fn<(path: string) => Promise<unknown>>()

function installDeviceMode({
  width,
  coarsePointer,
  noHover,
  touchPoints = coarsePointer ? 5 : 0,
  platform = coarsePointer ? "iPhone" : "Win32",
  userAgent = coarsePointer
    ? "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148"
    : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}: {
  width: number
  coarsePointer: boolean
  noHover: boolean
  touchPoints?: number
  platform?: string
  userAgent?: string
}) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width })
  Object.defineProperty(window.navigator, "platform", { configurable: true, value: platform })
  Object.defineProperty(window.navigator, "userAgent", { configurable: true, value: userAgent })
  Object.defineProperty(window.navigator, "maxTouchPoints", {
    configurable: true,
    value: touchPoints,
  })
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn((query: string) => {
      const matches =
        query.includes("max-width")
          ? width < 768
          : query === "(pointer: coarse)"
            ? coarsePointer
            : query === "(hover: none)"
              ? noHover
              : false

      return {
        matches,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }
    }),
  })
}

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useSearchParams: () => mockSearchParams,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}))

vi.mock("next/dynamic", () => ({
  __esModule: true,
  default: () =>
    function PlotMock() {
      return <div data-testid="plotly-mock" />
    },
}))

vi.mock("@/lib/api/client", () => ({
  apiFetch: (path: string) => mockApiFetch(path),
}))

describe("mobile QA", () => {
  beforeEach(() => {
    mockPathname = "/dashboard"
    mockApiFetch.mockReset()
    mockApiFetch.mockImplementation(async (path: string) => {
      if (path === "/mobile/command-center") {
        return {
          status: "ok",
          spectracheck_summary_json: { status: "ready" },
          regulatory_summary_json: { status: "pending" },
          reaction_summary_json: { status: "queued" },
        }
      }
      if (path === "/mobile/spectracheck/sessions/s-1/summary") {
        return { sample_session_status: "Open", latest_qc_status: "Pass", report_readiness: "Ready" }
      }
      if (path === "/mobile/action-queue") {
        return {
          items: [
            {
              id: 1,
              title: "Regulatory action",
              severity: "high",
              status: "open",
              dossier_title: "Dossier A",
              source_evidence: "Evidence A",
              due_date: "2026-01-01",
              human_review_required: true,
            },
          ],
        }
      }
      if (path === "/mobile/reactions/rp-1/summary") {
        return { pending_recommendations_count: 2, regulatory_constraints: ["constraint-a"] }
      }
      if (path === "/mobile/reports/r-1/preview") {
        return { report_title: "Report 1", review_status: "in_review" }
      }
      return {}
    })
    Object.defineProperty(window.navigator, "onLine", { configurable: true, value: true })
    installDeviceMode({ width: 390, coarsePointer: true, noHover: true })
  })

  it("renders mobile bottom nav", () => {
    render(<MobileBottomNav />)
    expect(screen.getByLabelText("Mobile bottom navigation")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Landing/ })).toHaveAttribute("href", "/")
    expect(screen.getByText("Dashboard")).toBeInTheDocument()
    expect(screen.getByText("SpectraCheck")).toBeInTheDocument()
  })

  it("renders program order as SpectraCheck, Regulatory Hub, Reaction Optimization", async () => {
    render(<MobileCommandCenter />)
    await waitFor(() => {
      expect(screen.getByText("1. SpectraCheck")).toBeInTheDocument()
      expect(screen.getByText("2. Regulatory Hub")).toBeInTheDocument()
      expect(screen.getByText("3. Reaction Optimization")).toBeInTheDocument()
    })
  })

  it("renders dashboard mobile command center and mobile cards", async () => {
    render(<MobilePage />)
    await waitFor(() => {
      expect(screen.getAllByText("Mobile Command Center").length).toBeGreaterThan(0)
      expect(screen.getByText("Mobile SpectraCheck Review")).toBeInTheDocument()
      expect(screen.getByText("Mobile Regulatory Action Queue")).toBeInTheDocument()
      expect(screen.getByText("Mobile Reaction Approval Board")).toBeInTheDocument()
    })
  })

  it("does not render mobile-only command surfaces on desktop mode", async () => {
    installDeviceMode({ width: 500, coarsePointer: false, noHover: false })
    render(<MobilePage />)

    await waitFor(() => {
      expect(screen.getByText("Desktop Workspace")).toBeInTheDocument()
    })
    expect(screen.queryByText("Mobile Command Center")).not.toBeInTheDocument()
    expect(screen.queryByText("Mobile SpectraCheck Review")).not.toBeInTheDocument()
    expect(screen.queryByText("Mobile Regulatory Action Queue")).not.toBeInTheDocument()
  })

  it("renders offline banner on mobile regulatory queue", async () => {
    Object.defineProperty(window.navigator, "onLine", { configurable: true, value: false })
    render(<MobileRegulatoryQueue />)
    await waitFor(() => {
      expect(screen.getByText("Draft only. This action is not final until synced.")).toBeInTheDocument()
    })
  })
})
