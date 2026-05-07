import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { MobileBottomNav } from "@/src/components/app-shell/MobileBottomNav"
import MobilePage from "@/app/mobile/page"
import { MobileCommandCenter } from "@/src/components/mobile/MobileCommandCenter"
import { MobileRegulatoryQueue } from "@/src/components/mobile/MobileRegulatoryQueue"

let mockPathname = "/dashboard"
const mockSearchParams = new URLSearchParams("sessionId=s-1&reactionProjectId=rp-1&reportId=r-1")
const mockApiFetch = vi.fn<(path: string) => Promise<unknown>>()

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
  })

  it("renders mobile bottom nav", () => {
    render(<MobileBottomNav />)
    expect(screen.getByLabelText("Mobile bottom navigation")).toBeInTheDocument()
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
    expect(screen.getAllByText("Mobile Command Center").length).toBeGreaterThan(0)
    await waitFor(() => {
      expect(screen.getByText("Mobile SpectraCheck Review")).toBeInTheDocument()
      expect(screen.getByText("Mobile Regulatory Action Queue")).toBeInTheDocument()
      expect(screen.getByText("Mobile Reaction Approval Board")).toBeInTheDocument()
    })
  })

  it("renders offline banner on mobile regulatory queue", async () => {
    Object.defineProperty(window.navigator, "onLine", { configurable: true, value: false })
    render(<MobileRegulatoryQueue />)
    await waitFor(() => {
      expect(screen.getByText("Draft only. This action is not final until synced.")).toBeInTheDocument()
    })
  })
})
